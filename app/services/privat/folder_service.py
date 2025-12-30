"""Service fuer die Verwaltung privater Ordner."""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatFolder, PrivatDocument
from app.db.schemas import (
    PrivatFolderCreate,
    PrivatFolderUpdate,
    PrivatFolderResponse,
    PrivatFolderTree,
)

logger = structlog.get_logger(__name__)


class PrivatFolderService:
    """Service fuer Privat-Ordner CRUD und Baumstruktur."""

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatFolderCreate,
    ) -> PrivatFolder:
        """Erstellt einen neuen Ordner.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Ordner-Daten

        Returns:
            Erstellter Ordner
        """
        # Berechne Pfad und Level
        path = ""
        level = 0

        if data.parent_id:
            parent = await self.get_by_id(db, data.parent_id)
            if parent:
                path = f"{parent.path}/{data.parent_id}"
                level = parent.level + 1

        folder = PrivatFolder(
            id=uuid.uuid4(),
            space_id=space_id,
            parent_id=data.parent_id,
            name=data.name,
            description=data.description,
            color=data.color,
            icon=data.icon,
            path=path,
            level=level,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(folder)
        await db.commit()
        await db.refresh(folder)

        logger.info(
            "privat_folder_created",
            folder_id=str(folder.id),
            space_id=str(space_id),
            parent_id=str(data.parent_id) if data.parent_id else None,
        )

        return folder

    async def get_by_id(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
    ) -> Optional[PrivatFolder]:
        """Holt einen Ordner nach ID.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID

        Returns:
            Ordner oder None
        """
        result = await db.execute(
            select(PrivatFolder).where(PrivatFolder.id == folder_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatFolder]:
        """IDOR-sichere Methode: Holt Ordner nur wenn User Zugriff hat.

        SECURITY: Gibt einheitlich None zurueck bei:
        - Ordner existiert nicht
        - User hat keinen Zugriff

        Dies verhindert Information Disclosure ueber Existenz von Ordnern.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Ordner wenn vorhanden und Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # Join mit Space um Owner zu pruefen
        result = await db.execute(
            select(PrivatFolder, PrivatSpace)
            .join(PrivatSpace, PrivatFolder.space_id == PrivatSpace.id)
            .where(PrivatFolder.id == folder_id)
        )
        row = result.first()

        if not row:
            return None

        folder, space = row

        # Owner hat immer Zugriff
        if space.owner_id == requesting_user_id:
            return folder

        # Pruefe explizite Berechtigung
        now = datetime.utcnow()
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now,
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            # SECURITY: Log IDOR-Versuch ohne sensible Details
            logger.warning(
                "idor_folder_attempt_blocked",
                folder_id=str(folder_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return folder

    async def get_space_folders(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        parent_id: Optional[uuid.UUID] = None,
    ) -> List[PrivatFolder]:
        """Holt alle Ordner eines Spaces auf einer Ebene.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            parent_id: Optional Parent-ID fuer Unterordner

        Returns:
            Liste von Ordnern
        """
        query = (
            select(PrivatFolder)
            .where(
                PrivatFolder.space_id == space_id,
                PrivatFolder.parent_id == parent_id,
            )
            .order_by(PrivatFolder.name)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_folder_tree(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> List[PrivatFolderTree]:
        """Holt die komplette Ordnerstruktur als Baum.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Liste von Ordnern mit children
        """
        # Alle Ordner des Spaces laden
        query = (
            select(PrivatFolder)
            .where(PrivatFolder.space_id == space_id)
            .order_by(PrivatFolder.level, PrivatFolder.name)
        )
        result = await db.execute(query)
        folders = list(result.scalars().all())

        # Dokumente pro Ordner zaehlen
        doc_counts = await self._get_document_counts(db, space_id)

        # Baum aufbauen
        folder_map: dict[uuid.UUID, PrivatFolderTree] = {}
        root_folders: List[PrivatFolderTree] = []

        for folder in folders:
            tree_node = PrivatFolderTree(
                id=folder.id,
                space_id=folder.space_id,
                parent_id=folder.parent_id,
                name=folder.name,
                description=folder.description,
                color=folder.color,
                icon=folder.icon,
                path=folder.path,
                level=folder.level,
                created_at=folder.created_at,
                updated_at=folder.updated_at,
                children=[],
                document_count=doc_counts.get(folder.id, 0),
            )
            folder_map[folder.id] = tree_node

        # Hierarchie aufbauen
        for folder in folders:
            tree_node = folder_map[folder.id]
            if folder.parent_id and folder.parent_id in folder_map:
                folder_map[folder.parent_id].children.append(tree_node)
            else:
                root_folders.append(tree_node)

        return root_folders

    async def _get_document_counts(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> dict[uuid.UUID, int]:
        """Holt Dokumentenzaehler pro Ordner.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Dict mit folder_id -> count
        """
        query = (
            select(
                PrivatDocument.folder_id,
                func.count(PrivatDocument.id).label("count")
            )
            .where(
                PrivatDocument.space_id == space_id,
                PrivatDocument.folder_id.isnot(None),
            )
            .group_by(PrivatDocument.folder_id)
        )

        result = await db.execute(query)
        return {row.folder_id: row.count for row in result}

    async def update(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
        data: PrivatFolderUpdate,
    ) -> Optional[PrivatFolder]:
        """Aktualisiert einen Ordner.

        SECURITY FIX 23-1: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Ordnerstrukturen entstehen

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            data: Update-Daten

        Returns:
            Aktualisierter Ordner oder None
        """
        # SECURITY FIX 23-1: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatFolder)
            .where(PrivatFolder.id == folder_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Ordnerstruktur!
        )
        folder = result.scalar_one_or_none()
        if not folder:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Bei Parent-Aenderung Pfad und Level neu berechnen
        if "parent_id" in update_data:
            new_parent_id = update_data["parent_id"]
            if new_parent_id:
                parent = await self.get_by_id(db, new_parent_id)
                if parent:
                    folder.path = f"{parent.path}/{new_parent_id}"
                    folder.level = parent.level + 1
            else:
                folder.path = ""
                folder.level = 0

        for key, value in update_data.items():
            if key != "parent_id" or value is not None:
                setattr(folder, key, value)

        folder.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(folder)

        logger.info(
            "privat_folder_updated",
            folder_id=str(folder_id),
        )

        return folder

    async def delete(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
        recursive: bool = False,
    ) -> bool:
        """Loescht einen Ordner.

        SECURITY FIX 23-2: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            recursive: Auch Unterordner und Dokumente loeschen?

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Ordner nicht leer und nicht recursive
        """
        # SECURITY FIX 23-2: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatFolder)
            .where(PrivatFolder.id == folder_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        folder = result.scalar_one_or_none()
        if not folder:
            return False

        # Pruefe auf Unterordner
        children = await self.get_space_folders(db, folder.space_id, folder_id)
        if children and not recursive:
            raise ValueError("Ordner enthaelt Unterordner. Nutze recursive=True")

        # Pruefe auf Dokumente
        doc_count = await db.execute(
            select(func.count(PrivatDocument.id))
            .where(PrivatDocument.folder_id == folder_id)
        )
        if doc_count.scalar() > 0 and not recursive:
            raise ValueError("Ordner enthaelt Dokumente. Nutze recursive=True")

        if recursive:
            # Rekursiv loeschen
            for child in children:
                await self.delete(db, child.id, recursive=True)

            # Dokumente verschieben (in Space-Root)
            await db.execute(
                PrivatDocument.__table__.update()
                .where(PrivatDocument.folder_id == folder_id)
                .values(folder_id=None)
            )

        await db.delete(folder)
        await db.commit()

        logger.info(
            "privat_folder_deleted",
            folder_id=str(folder_id),
            recursive=recursive,
        )

        return True

    async def move_with_access_check(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
        new_parent_id: Optional[uuid.UUID],
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatFolder]:
        """SECURITY FIX 20-2/20-3: Atomare Move-Operation mit Access-Check.

        TOCTOU-sicher: Access-Check und Move in einer atomaren Operation.
        Verhindert IDOR durch Validierung dass new_parent_id im gleichen Space liegt.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            new_parent_id: Neuer Parent (None fuer Root)
            requesting_user_id: ID des anfragenden Users

        Returns:
            Aktualisierter Ordner oder None wenn kein Zugriff

        Raises:
            ValueError: Bei ungueltigem Zielordner oder Zirkularitaet
        """
        # SECURITY: Hole Quell-Ordner mit Access-Check (atomar)
        folder = await self.get_by_id_with_access_check(db, folder_id, requesting_user_id)
        if not folder:
            return None

        # Validiere Zielordner
        if new_parent_id:
            new_parent = await self.get_by_id(db, new_parent_id)
            if not new_parent:
                raise ValueError("Zielordner nicht gefunden")

            # SECURITY FIX 20-3: Pruefe dass new_parent im GLEICHEN Space liegt
            # Verhindert IDOR - User kann keine Ordner in fremde Spaces verschieben
            if new_parent.space_id != folder.space_id:
                logger.warning(
                    "idor_folder_move_cross_space_blocked",
                    folder_id=str(folder_id),
                    folder_space_id=str(folder.space_id),
                    target_space_id=str(new_parent.space_id),
                    requesting_user_id=str(requesting_user_id),
                )
                raise ValueError("Zielordner nicht gefunden oder in anderem Space")

            # Pruefe Zirkularitaet
            if new_parent_id == folder_id:
                raise ValueError("Ordner kann nicht in sich selbst verschoben werden")

            if new_parent.path and str(folder_id) in new_parent.path:
                raise ValueError("Ordner kann nicht in Unterordner verschoben werden")

            folder.parent_id = new_parent_id
            folder.path = f"{new_parent.path}/{new_parent_id}"
            folder.level = new_parent.level + 1
        else:
            folder.parent_id = None
            folder.path = ""
            folder.level = 0

        folder.updated_at = datetime.utcnow()

        # Aktualisiere Pfade aller Unterordner
        await self._update_children_paths(db, folder)

        await db.commit()
        await db.refresh(folder)

        logger.info(
            "privat_folder_moved",
            folder_id=str(folder_id),
            new_parent_id=str(new_parent_id) if new_parent_id else None,
            requesting_user_id=str(requesting_user_id),
        )

        return folder

    async def move(
        self,
        db: AsyncSession,
        folder_id: uuid.UUID,
        new_parent_id: Optional[uuid.UUID],
    ) -> Optional[PrivatFolder]:
        """Verschiebt einen Ordner in einen anderen Parent.

        DEPRECATED: Nutze move_with_access_check() fuer IDOR-sichere Operationen.

        Args:
            db: Datenbank-Session
            folder_id: Ordner-ID
            new_parent_id: Neuer Parent (None fuer Root)

        Returns:
            Aktualisierter Ordner oder None
        """
        folder = await self.get_by_id(db, folder_id)
        if not folder:
            return None

        # Validiere: Nicht in sich selbst oder Unterordner verschieben
        if new_parent_id:
            new_parent = await self.get_by_id(db, new_parent_id)
            if not new_parent:
                raise ValueError("Zielordner nicht gefunden")

            # Pruefe Zirkularitaet
            if new_parent_id == folder_id:
                raise ValueError("Ordner kann nicht in sich selbst verschoben werden")

            if new_parent.path and str(folder_id) in new_parent.path:
                raise ValueError("Ordner kann nicht in Unterordner verschoben werden")

            folder.parent_id = new_parent_id
            folder.path = f"{new_parent.path}/{new_parent_id}"
            folder.level = new_parent.level + 1
        else:
            folder.parent_id = None
            folder.path = ""
            folder.level = 0

        folder.updated_at = datetime.utcnow()

        # Aktualisiere Pfade aller Unterordner
        await self._update_children_paths(db, folder)

        await db.commit()
        await db.refresh(folder)

        logger.info(
            "privat_folder_moved",
            folder_id=str(folder_id),
            new_parent_id=str(new_parent_id) if new_parent_id else None,
        )

        return folder

    async def _update_children_paths(
        self,
        db: AsyncSession,
        parent: PrivatFolder,
    ) -> None:
        """Aktualisiert die Pfade aller Unterordner rekursiv.

        Args:
            db: Datenbank-Session
            parent: Parent-Ordner
        """
        children = await self.get_space_folders(db, parent.space_id, parent.id)

        for child in children:
            child.path = f"{parent.path}/{parent.id}"
            child.level = parent.level + 1
            child.updated_at = datetime.utcnow()
            await self._update_children_paths(db, child)
