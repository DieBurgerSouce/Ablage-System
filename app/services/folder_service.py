"""Folder Service - Geschäftliche Ordnerverwaltung.

Bietet hierarchische Ordnerverwaltung mit:
- CRUD-Operationen für Ordner
- Hierarchie-Navigation (Tree, Breadcrumbs)
- Dokument-Zuordnung
- Berechtigungsvererbung
- Drag-Drop Reorganisation
- Company-Scoping (Multi-Tenancy)
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, User
from app.db.models_folder import (
    Folder,
    FolderDocument,
    FolderPermission,
    FolderPermissionLevel,
    FolderType,
)

logger = structlog.get_logger(__name__)


class FolderService:
    """Service für die Verwaltung geschäftlicher Ordner.

    Alle Operationen sind company-scoped für Multi-Tenancy.
    """

    # ================================================================
    # CRUD
    # ================================================================

    async def create_folder(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        name: str,
        created_by_id: UUID,
        parent_id: Optional[UUID] = None,
        description: Optional[str] = None,
        icon: str = "Folder",
        color: Optional[str] = None,
        folder_type: str = FolderType.GESCHAEFTLICH.value,
        folder_metadata: Optional[Dict] = None,
    ) -> Folder:
        """Erstellt einen neuen Ordner.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID für Multi-Tenancy
            name: Ordnername
            created_by_id: ID des erstellenden Users
            parent_id: ID des übergeordneten Ordners (None = Root)
            description: Optionale Beschreibung
            icon: Icon-Name (default: Folder)
            color: Hex-Farbcode
            folder_type: Ordnertyp
            folder_metadata: Erweiterbare Metadaten

        Returns:
            Erstellter Ordner

        Raises:
            ValueError: Wenn parent_id ungültig oder nicht in gleicher Company
        """
        # Berechne Pfad und Level
        path = ""
        level = 0

        if parent_id:
            parent = await self._get_folder_internal(db, parent_id, company_id)
            if not parent:
                raise ValueError("Übergeordneter Ordner nicht gefunden")
            path = f"{parent.path}/"
            level = parent.level + 1

        # WICHTIG (Bug-Fix 2026-06-13): Die ID explizit VOR dem ersten flush()
        # erzeugen, damit der Materialized Path (Spalte ``path`` ist NOT NULL)
        # bereits beim INSERT gesetzt ist. Frueher wurde ``folder.path`` erst NACH
        # ``db.flush()`` gesetzt -> der erste INSERT schrieb ``path=NULL`` und lief
        # gegen eine IntegrityError (NotNullViolation) -> 500 bei JEDER
        # Ordner-Erstellung gegen eine echte DB (in Unit-Tests durch gemocktes
        # ``flush`` verdeckt).
        folder_id = uuid4()
        materialized_path = f"{path}{folder_id}" if parent_id else str(folder_id)

        folder = Folder(
            id=folder_id,
            company_id=company_id,
            parent_id=parent_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            folder_type=folder_type,
            folder_metadata=folder_metadata or {},
            path=materialized_path,
            level=level,
            created_by_id=created_by_id,
        )

        db.add(folder)
        await db.flush()

        # Subfolder-Count des Parents aktualisieren
        if parent_id:
            await self._increment_subfolder_count(db, parent_id, 1)

        # Admin-Berechtigung für Ersteller setzen
        permission = FolderPermission(
            folder_id=folder.id,
            user_id=created_by_id,
            permission_level=FolderPermissionLevel.ADMIN.value,
            inherited=False,
            granted_by_id=created_by_id,
        )
        db.add(permission)

        await db.flush()

        logger.info(
            "folder_created",
            folder_id=str(folder.id),
            name=name,
            parent_id=str(parent_id) if parent_id else None,
            company_id=str(company_id),
        )

        return folder

    async def get_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[Folder]:
        """Einzelnen Ordner abrufen mit Berechtigungsprüfung.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            company_id: Firmen-ID
            user_id: User-ID für Zugriffsprüfung

        Returns:
            Ordner oder None
        """
        if not await self.check_folder_access(db, folder_id, user_id, "read"):
            return None

        return await self._get_folder_internal(db, folder_id, company_id)

    async def update_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
        user_id: UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        folder_type: Optional[str] = None,
        folder_metadata: Optional[Dict] = None,
    ) -> Optional[Folder]:
        """Ordner aktualisieren.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            company_id: Firmen-ID
            user_id: User-ID für Zugriffsprüfung

        Returns:
            Aktualisierter Ordner oder None

        Raises:
            PermissionError: Wenn User keine Schreibberechtigung hat
            ValueError: Wenn Ordner gesperrt ist
        """
        if not await self.check_folder_access(db, folder_id, user_id, "write"):
            raise PermissionError("Keine Berechtigung zum Bearbeiten dieses Ordners")

        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return None

        if folder.is_locked:
            raise ValueError("Ordner ist gesperrt und kann nicht bearbeitet werden")

        if name is not None:
            folder.name = name
        if description is not None:
            folder.description = description
        if icon is not None:
            folder.icon = icon
        if color is not None:
            folder.color = color
        if folder_type is not None:
            folder.folder_type = folder_type
        if folder_metadata is not None:
            folder.folder_metadata = folder_metadata

        await db.flush()

        logger.info("folder_updated", folder_id=str(folder_id), name=folder.name)
        return folder

    async def soft_delete_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Ordner weich löschen (Soft Delete).

        Löscht auch alle Unterordner rekursiv.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            company_id: Firmen-ID
            user_id: User-ID

        Returns:
            True wenn erfolgreich gelöscht
        """
        if not await self.check_folder_access(db, folder_id, user_id, "admin"):
            raise PermissionError("Keine Berechtigung zum Löschen dieses Ordners")

        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return False

        if folder.is_locked:
            raise ValueError("Gesperrter Ordner kann nicht gelöscht werden")

        now = datetime.now(timezone.utc)

        # Alle Unterordner per Materialized Path finden und löschen
        descendant_query = (
            select(Folder)
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.path.like(f"{folder.path}/%"),
                    Folder.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(descendant_query)
        descendants = result.scalars().all()

        for desc in descendants:
            desc.deleted_at = now

        folder.deleted_at = now

        # Parent subfolder_count aktualisieren
        if folder.parent_id:
            await self._increment_subfolder_count(db, folder.parent_id, -1)

        await db.flush()

        logger.info(
            "folder_deleted",
            folder_id=str(folder_id),
            descendants_deleted=len(descendants),
        )
        return True

    # ================================================================
    # Hierarchie
    # ================================================================

    async def get_folder_tree(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        parent_id: Optional[UUID] = None,
        max_depth: int = 10,
    ) -> List[Dict]:
        """Ordnerbaum als verschachtelte Struktur abrufen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: User-ID
            parent_id: Start-Ordner (None = Root)
            max_depth: Maximale Verschachtelungstiefe

        Returns:
            Liste von Ordner-Dicts mit 'children' Attribut
        """
        # Alle Ordner der Company laden
        query = (
            select(Folder)
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.deleted_at.is_(None),
                )
            )
            .order_by(Folder.level, Folder.sort_order, Folder.name)
        )

        result = await db.execute(query)
        all_folders = result.scalars().all()

        # Berechtigungen prüfen
        accessible_ids = set()
        for f in all_folders:
            if await self.check_folder_access(db, f.id, user_id, "read"):
                accessible_ids.add(f.id)

        # Baum aufbauen
        folder_map: Dict[Optional[UUID], List[Dict]] = {}
        for f in all_folders:
            if f.id not in accessible_ids:
                continue
            node = {
                "id": str(f.id),
                "name": f.name,
                "icon": f.icon,
                "color": f.color,
                "folder_type": f.folder_type,
                "level": f.level,
                "document_count": f.document_count,
                "subfolder_count": f.subfolder_count,
                "is_locked": f.is_locked,
                "children": [],
            }
            pid = f.parent_id
            if pid not in folder_map:
                folder_map[pid] = []
            folder_map[pid].append(node)

        def _build_tree(pid: Optional[UUID], depth: int) -> List[Dict]:
            if depth > max_depth:
                return []
            nodes = folder_map.get(pid, [])
            for node in nodes:
                node["children"] = _build_tree(UUID(node["id"]), depth + 1)
            return nodes

        return _build_tree(parent_id, 0)

    async def get_breadcrumbs(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
    ) -> List[Dict]:
        """Breadcrumb-Pfad vom Root bis zum Ordner.

        Args:
            db: Datenbank-Session
            folder_id: Ziel-Ordner
            company_id: Firmen-ID

        Returns:
            Liste von {id, name} Dicts vom Root zum Ziel
        """
        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return []

        # Pfad-IDs aus Materialized Path extrahieren
        path_ids = folder.path.split("/")

        if not path_ids:
            return []

        # Alle Ordner im Pfad laden
        query = (
            select(Folder.id, Folder.name, Folder.icon)
            .where(
                and_(
                    Folder.id.in_([UUID(pid) for pid in path_ids if pid]),
                    Folder.company_id == company_id,
                )
            )
        )
        result = await db.execute(query)
        folder_map = {str(row.id): {"id": str(row.id), "name": row.name, "icon": row.icon} for row in result}

        # In Pfad-Reihenfolge zurückgeben
        return [folder_map[pid] for pid in path_ids if pid in folder_map]

    async def move_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        new_parent_id: Optional[UUID],
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[Folder]:
        """Ordner in einen anderen Ordner verschieben.

        Aktualisiert Materialized Paths aller Nachkommen.

        Args:
            db: Datenbank-Session
            folder_id: Zu verschiebender Ordner
            new_parent_id: Neuer Eltern-Ordner (None = Root)
            company_id: Firmen-ID
            user_id: User-ID

        Returns:
            Verschobener Ordner

        Raises:
            ValueError: Wenn Verschiebung einen Zyklus erzeugen wuerde
        """
        if not await self.check_folder_access(db, folder_id, user_id, "admin"):
            raise PermissionError("Keine Berechtigung zum Verschieben")

        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return None

        if folder.is_locked:
            raise ValueError("Gesperrter Ordner kann nicht verschoben werden")

        # Zyklus-Prüfung: new_parent darf kein Nachkomme von folder sein
        if new_parent_id:
            new_parent = await self._get_folder_internal(db, new_parent_id, company_id)
            if not new_parent:
                raise ValueError("Ziel-Ordner nicht gefunden")
            if str(folder_id) in new_parent.path.split("/"):
                raise ValueError("Ordner kann nicht in seinen eigenen Unterordner verschoben werden")

        old_path = folder.path
        old_parent_id = folder.parent_id

        # Neuen Pfad berechnen
        if new_parent_id:
            new_parent = await self._get_folder_internal(db, new_parent_id, company_id)
            new_path = f"{new_parent.path}/{folder.id}"
            new_level = new_parent.level + 1
        else:
            new_path = str(folder.id)
            new_level = 0

        # Ordner aktualisieren
        folder.parent_id = new_parent_id
        folder.path = new_path
        folder.level = new_level

        # Alle Nachkommen: Pfad und Level aktualisieren
        descendant_query = (
            select(Folder)
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.path.like(f"{old_path}/%"),
                    Folder.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(descendant_query)
        descendants = result.scalars().all()

        level_diff = new_level - (folder.level if folder.level else 0)
        for desc in descendants:
            desc.path = desc.path.replace(old_path, new_path, 1)
            desc.level = desc.level + level_diff

        # Subfolder-Counts aktualisieren
        if old_parent_id:
            await self._increment_subfolder_count(db, old_parent_id, -1)
        if new_parent_id:
            await self._increment_subfolder_count(db, new_parent_id, 1)

        await db.flush()

        logger.info(
            "folder_moved",
            folder_id=str(folder_id),
            old_parent=str(old_parent_id),
            new_parent=str(new_parent_id),
            descendants_updated=len(descendants),
        )
        return folder

    # ================================================================
    # Dokument-Zuordnung
    # ================================================================

    async def add_document_to_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        document_id: UUID,
        user_id: UUID,
        company_id: UUID,
        is_primary: bool = True,
    ) -> FolderDocument:
        """Dokument einem Ordner zuordnen.

        Args:
            db: Datenbank-Session
            folder_id: Ziel-Ordner
            document_id: Dokument-ID
            user_id: User-ID
            company_id: Firmen-ID
            is_primary: Ob dies der Hauptordner ist

        Returns:
            FolderDocument-Zuordnung
        """
        if not await self.check_folder_access(db, folder_id, user_id, "write"):
            raise PermissionError("Keine Berechtigung für diesen Ordner")

        # Prüfen ob Zuordnung bereits existiert
        existing = await db.execute(
            select(FolderDocument).where(
                and_(
                    FolderDocument.folder_id == folder_id,
                    FolderDocument.document_id == document_id,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Dokument ist bereits in diesem Ordner")

        # Wenn primary: andere primary-Zuordnungen entfernen
        if is_primary:
            await db.execute(
                update(FolderDocument)
                .where(
                    and_(
                        FolderDocument.document_id == document_id,
                        FolderDocument.is_primary.is_(True),
                    )
                )
                .values(is_primary=False)
            )

        folder_doc = FolderDocument(
            folder_id=folder_id,
            document_id=document_id,
            is_primary=is_primary,
            added_by_id=user_id,
        )
        db.add(folder_doc)

        # Document-Count aktualisieren
        await self._increment_document_count(db, folder_id, 1)

        await db.flush()

        logger.info(
            "document_added_to_folder",
            folder_id=str(folder_id),
            document_id=str(document_id),
        )
        return folder_doc

    async def remove_document_from_folder(
        self,
        db: AsyncSession,
        folder_id: UUID,
        document_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Dokument aus Ordner entfernen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            document_id: Dokument-ID
            user_id: User-ID

        Returns:
            True wenn erfolgreich entfernt
        """
        if not await self.check_folder_access(db, folder_id, user_id, "write"):
            raise PermissionError("Keine Berechtigung für diesen Ordner")

        result = await db.execute(
            delete(FolderDocument).where(
                and_(
                    FolderDocument.folder_id == folder_id,
                    FolderDocument.document_id == document_id,
                )
            )
        )

        if result.rowcount > 0:
            await self._increment_document_count(db, folder_id, -1)
            await db.flush()
            logger.info(
                "document_removed_from_folder",
                folder_id=str(folder_id),
                document_id=str(document_id),
            )
            return True
        return False

    async def get_folder_documents(
        self,
        db: AsyncSession,
        folder_id: UUID,
        user_id: UUID,
        company_id: UUID,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Document], int]:
        """Dokumente eines Ordners mit Pagination abrufen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            user_id: User-ID
            company_id: Firmen-ID
            page: Seitennummer
            per_page: Einträge pro Seite

        Returns:
            Tuple aus (Dokument-Liste, Gesamtanzahl)
        """
        if not await self.check_folder_access(db, folder_id, user_id, "read"):
            return [], 0

        # Count
        count_query = (
            select(func.count(FolderDocument.id))
            .where(FolderDocument.folder_id == folder_id)
        )
        total = (await db.execute(count_query)).scalar() or 0

        # Documents
        query = (
            select(Document)
            .join(FolderDocument, FolderDocument.document_id == Document.id)
            .where(FolderDocument.folder_id == folder_id)
            .order_by(FolderDocument.sort_order, Document.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        return list(documents), total

    async def move_document_between_folders(
        self,
        db: AsyncSession,
        document_id: UUID,
        source_folder_id: UUID,
        target_folder_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Dokument von einem Ordner in einen anderen verschieben.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            source_folder_id: Quell-Ordner
            target_folder_id: Ziel-Ordner
            user_id: User-ID
            company_id: Firmen-ID

        Returns:
            True wenn erfolgreich
        """
        # Berechtigungen für beide Ordner prüfen
        if not await self.check_folder_access(db, source_folder_id, user_id, "write"):
            raise PermissionError("Keine Berechtigung für den Quell-Ordner")
        if not await self.check_folder_access(db, target_folder_id, user_id, "write"):
            raise PermissionError("Keine Berechtigung für den Ziel-Ordner")

        # Zuordnung aktualisieren
        result = await db.execute(
            update(FolderDocument)
            .where(
                and_(
                    FolderDocument.folder_id == source_folder_id,
                    FolderDocument.document_id == document_id,
                )
            )
            .values(folder_id=target_folder_id)
        )

        if result.rowcount > 0:
            await self._increment_document_count(db, source_folder_id, -1)
            await self._increment_document_count(db, target_folder_id, 1)
            await db.flush()
            logger.info(
                "document_moved",
                document_id=str(document_id),
                source=str(source_folder_id),
                target=str(target_folder_id),
            )
            return True
        return False

    # ================================================================
    # Berechtigungen
    # ================================================================

    async def check_folder_access(
        self,
        db: AsyncSession,
        folder_id: UUID,
        user_id: UUID,
        required_level: str = "read",
    ) -> bool:
        """Prüft ob User die erforderliche Berechtigung für den Ordner hat.

        Berechtigungshierarchie: admin > write > read

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            user_id: User-ID
            required_level: Mindestberechtigung (read/write/admin)

        Returns:
            True wenn berechtigt
        """
        level_hierarchy = {
            FolderPermissionLevel.READ.value: 1,
            FolderPermissionLevel.WRITE.value: 2,
            FolderPermissionLevel.ADMIN.value: 3,
        }

        required_rank = level_hierarchy.get(required_level, 1)

        # Direkte oder vererbte Berechtigung suchen
        query = (
            select(FolderPermission.permission_level)
            .where(
                and_(
                    FolderPermission.folder_id == folder_id,
                    FolderPermission.user_id == user_id,
                )
            )
        )
        result = await db.execute(query)
        permission = result.scalar_one_or_none()

        if permission:
            return level_hierarchy.get(permission, 0) >= required_rank

        # Fallback: Über Materialized Path des Ordners prüfen
        folder_query = select(Folder.path).where(Folder.id == folder_id)
        folder_result = await db.execute(folder_query)
        folder_path = folder_result.scalar_one_or_none()

        if not folder_path:
            return False

        # Ancestor-Ordner aus Pfad extrahieren und Berechtigungen prüfen
        path_parts = folder_path.split("/")
        ancestor_ids = [UUID(p) for p in path_parts if p and p != str(folder_id)]

        if not ancestor_ids:
            return False

        ancestor_perm_query = (
            select(func.max(FolderPermission.permission_level))
            .where(
                and_(
                    FolderPermission.folder_id.in_(ancestor_ids),
                    FolderPermission.user_id == user_id,
                )
            )
        )
        result = await db.execute(ancestor_perm_query)
        inherited_level = result.scalar_one_or_none()

        if inherited_level:
            return level_hierarchy.get(inherited_level, 0) >= required_rank

        return False

    async def set_folder_permission(
        self,
        db: AsyncSession,
        folder_id: UUID,
        target_user_id: UUID,
        permission_level: str,
        granted_by_id: UUID,
        company_id: UUID,
        propagate: bool = True,
    ) -> FolderPermission:
        """Berechtigung für einen Ordner setzen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            target_user_id: User der die Berechtigung erhält
            permission_level: Berechtigungsstufe
            granted_by_id: User der die Berechtigung erteilt
            company_id: Firmen-ID
            propagate: Berechtigung an Unterordner vererben

        Returns:
            Erstellte/Aktualisierte Berechtigung
        """
        if not await self.check_folder_access(db, folder_id, granted_by_id, "admin"):
            raise PermissionError("Nur Admins können Berechtigungen vergeben")

        # Upsert: Existierende Berechtigung aktualisieren oder neue erstellen
        existing = await db.execute(
            select(FolderPermission).where(
                and_(
                    FolderPermission.folder_id == folder_id,
                    FolderPermission.user_id == target_user_id,
                )
            )
        )
        perm = existing.scalar_one_or_none()

        if perm:
            perm.permission_level = permission_level
            perm.inherited = False
            perm.inherited_from_id = None
            perm.granted_by_id = granted_by_id
        else:
            perm = FolderPermission(
                folder_id=folder_id,
                user_id=target_user_id,
                permission_level=permission_level,
                inherited=False,
                granted_by_id=granted_by_id,
            )
            db.add(perm)

        # Vererbung an Unterordner
        if propagate:
            await self._propagate_permission(
                db, folder_id, target_user_id, permission_level, granted_by_id, company_id
            )

        await db.flush()

        logger.info(
            "folder_permission_set",
            folder_id=str(folder_id),
            user_id=str(target_user_id),
            level=permission_level,
        )
        return perm

    async def get_folder_permissions(
        self,
        db: AsyncSession,
        folder_id: UUID,
    ) -> List[FolderPermission]:
        """Alle Berechtigungen eines Ordners abrufen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID

        Returns:
            Liste der Berechtigungen
        """
        query = (
            select(FolderPermission)
            .where(FolderPermission.folder_id == folder_id)
            .order_by(FolderPermission.permission_level.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    # ================================================================
    # Suche & Sortierung
    # ================================================================

    async def search_folders(
        self,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        query_text: str,
        folder_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Folder], int]:
        """Ordner suchen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: User-ID
            query_text: Suchbegriff
            folder_type: Optionaler Typ-Filter
            page: Seitennummer
            per_page: Einträge pro Seite

        Returns:
            Tuple (Ergebnisse, Gesamtanzahl)
        """
        conditions = [
            Folder.company_id == company_id,
            Folder.deleted_at.is_(None),
            Folder.name.ilike(f"%{query_text}%"),
        ]

        if folder_type:
            conditions.append(Folder.folder_type == folder_type)

        # Count
        count_q = select(func.count(Folder.id)).where(and_(*conditions))
        total = (await db.execute(count_q)).scalar() or 0

        # Results
        query = (
            select(Folder)
            .where(and_(*conditions))
            .order_by(Folder.name)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await db.execute(query)
        folders = result.scalars().all()

        return list(folders), total

    async def reorder_folders(
        self,
        db: AsyncSession,
        parent_id: Optional[UUID],
        company_id: UUID,
        user_id: UUID,
        folder_order: List[UUID],
    ) -> bool:
        """Ordner innerhalb eines Parents neu sortieren.

        Args:
            db: Datenbank-Session
            parent_id: Eltern-Ordner (None = Root)
            company_id: Firmen-ID
            user_id: User-ID
            folder_order: Liste von Ordner-IDs in gewünschter Reihenfolge

        Returns:
            True wenn erfolgreich
        """
        for idx, fid in enumerate(folder_order):
            await db.execute(
                update(Folder)
                .where(
                    and_(
                        Folder.id == fid,
                        Folder.company_id == company_id,
                        Folder.parent_id == parent_id if parent_id else Folder.parent_id.is_(None),
                    )
                )
                .values(sort_order=idx)
            )

        await db.flush()
        logger.info("folders_reordered", parent_id=str(parent_id), count=len(folder_order))
        return True

    # ================================================================
    # Statistiken
    # ================================================================

    async def get_folder_stats(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
    ) -> Dict:
        """Statistiken für einen Ordner abrufen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            company_id: Firmen-ID

        Returns:
            Dict mit Statistiken
        """
        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return {}

        # Rekursive Dokumenten-Anzahl über Materialized Path
        total_docs_query = (
            select(func.count(FolderDocument.id))
            .join(Folder, Folder.id == FolderDocument.folder_id)
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.path.like(f"{folder.path}%"),
                    Folder.deleted_at.is_(None),
                )
            )
        )
        total_docs = (await db.execute(total_docs_query)).scalar() or 0

        # Rekursive Unterordner-Anzahl
        total_subfolders_query = (
            select(func.count(Folder.id))
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.path.like(f"{folder.path}/%"),
                    Folder.deleted_at.is_(None),
                )
            )
        )
        total_subfolders = (await db.execute(total_subfolders_query)).scalar() or 0

        return {
            "folder_id": str(folder_id),
            "name": folder.name,
            "direct_documents": folder.document_count,
            "direct_subfolders": folder.subfolder_count,
            "total_documents_recursive": total_docs,
            "total_subfolders_recursive": total_subfolders,
            "level": folder.level,
            "is_locked": folder.is_locked,
        }

    # ================================================================
    # Interne Hilfsmethoden
    # ================================================================

    async def _get_folder_internal(
        self,
        db: AsyncSession,
        folder_id: UUID,
        company_id: UUID,
    ) -> Optional[Folder]:
        """Interner Abruf ohne Berechtigungsprüfung."""
        query = (
            select(Folder)
            .where(
                and_(
                    Folder.id == folder_id,
                    Folder.company_id == company_id,
                    Folder.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _increment_subfolder_count(
        self,
        db: AsyncSession,
        folder_id: UUID,
        delta: int,
    ) -> None:
        """Subfolder-Count atomar aktualisieren."""
        await db.execute(
            update(Folder)
            .where(Folder.id == folder_id)
            .values(subfolder_count=Folder.subfolder_count + delta)
        )

    async def _increment_document_count(
        self,
        db: AsyncSession,
        folder_id: UUID,
        delta: int,
    ) -> None:
        """Document-Count atomar aktualisieren."""
        await db.execute(
            update(Folder)
            .where(Folder.id == folder_id)
            .values(document_count=Folder.document_count + delta)
        )

    async def _propagate_permission(
        self,
        db: AsyncSession,
        folder_id: UUID,
        user_id: UUID,
        permission_level: str,
        granted_by_id: UUID,
        company_id: UUID,
    ) -> None:
        """Berechtigung an alle Unterordner vererben."""
        folder = await self._get_folder_internal(db, folder_id, company_id)
        if not folder:
            return

        # Alle Unterordner per Materialized Path
        descendant_query = (
            select(Folder.id)
            .where(
                and_(
                    Folder.company_id == company_id,
                    Folder.path.like(f"{folder.path}/%"),
                    Folder.deleted_at.is_(None),
                )
            )
        )
        result = await db.execute(descendant_query)
        descendant_ids = [row.id for row in result]

        for desc_id in descendant_ids:
            # Upsert für vererbte Berechtigung
            existing = await db.execute(
                select(FolderPermission).where(
                    and_(
                        FolderPermission.folder_id == desc_id,
                        FolderPermission.user_id == user_id,
                        FolderPermission.inherited.is_(True),
                    )
                )
            )
            perm = existing.scalar_one_or_none()

            if perm:
                perm.permission_level = permission_level
                perm.inherited_from_id = folder_id
            else:
                # Nur vererben wenn keine direkte Berechtigung existiert
                direct = await db.execute(
                    select(FolderPermission).where(
                        and_(
                            FolderPermission.folder_id == desc_id,
                            FolderPermission.user_id == user_id,
                            FolderPermission.inherited.is_(False),
                        )
                    )
                )
                if not direct.scalar_one_or_none():
                    new_perm = FolderPermission(
                        folder_id=desc_id,
                        user_id=user_id,
                        permission_level=permission_level,
                        inherited=True,
                        inherited_from_id=folder_id,
                        granted_by_id=granted_by_id,
                    )
                    db.add(new_perm)


# Singleton
_folder_service: Optional[FolderService] = None


def get_folder_service() -> FolderService:
    """Singleton-Instanz des FolderService."""
    global _folder_service
    if _folder_service is None:
        _folder_service = FolderService()
    return _folder_service
