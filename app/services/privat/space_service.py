"""Service fuer die Verwaltung privater Bereiche (Spaces)."""

import uuid
from datetime import datetime
from app.core.datetime_utils import utc_now
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    PrivatSpace,
    PrivatSpaceAccess,
    PrivatFolder,
    PrivatDocument,
    PrivatDeadline,
    User,
)
from app.db.schemas import (
    PrivatSpaceCreate,
    PrivatSpaceUpdate,
    PrivatSpaceResponse,
    PrivatSpaceWithStats,
    PrivatSpaceListResponse,
    PrivatSpaceType,
)

logger = structlog.get_logger(__name__)


class PrivatSpaceService:
    """Service fuer Privat-Space CRUD und Statistiken."""

    async def create_personal_space(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        data: PrivatSpaceCreate,
    ) -> PrivatSpace:
        """Erstellt einen persoenlichen Space fuer einen Benutzer.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            data: Space-Daten

        Returns:
            Erstellter Space
        """
        space = PrivatSpace(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            space_type=PrivatSpaceType.PERSONAL.value,
            owner_id=user_id,
            company_id=None,
            # is_active is now a property derived from deleted_at (None = active)
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(space)
        await db.commit()
        await db.refresh(space)

        logger.info(
            "privat_space_created",
            space_id=str(space.id),
            user_id=str(user_id),
            space_type="personal",
        )

        return space

    async def create_shared_space(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        created_by: uuid.UUID,
        data: PrivatSpaceCreate,
    ) -> PrivatSpace:
        """Erstellt einen geteilten Space fuer eine Firma.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            created_by: Ersteller-ID
            data: Space-Daten

        Returns:
            Erstellter Space
        """
        space = PrivatSpace(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            space_type=PrivatSpaceType.SHARED.value,
            owner_id=created_by,
            company_id=company_id,
            # is_active is now a property derived from deleted_at (None = active)
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(space)
        await db.commit()
        await db.refresh(space)

        logger.info(
            "privat_space_created",
            space_id=str(space.id),
            company_id=str(company_id),
            space_type="shared",
        )

        return space

    async def get_by_id(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Optional[PrivatSpace]:
        """Holt einen Space nach ID.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Space oder None
        """
        result = await db.execute(
            select(PrivatSpace).where(PrivatSpace.id == space_id)
        )
        return result.scalar_one_or_none()

    async def get_with_access_check(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        required_level: str = "read",
    ) -> Optional[PrivatSpace]:
        """Holt Space mit atomarer Access-Validierung (TOCTOU-sicher).

        SECURITY FIX (Iteration 19): Kombiniert Space-Abruf und Access-Check
        in einer atomaren Operation, um TOCTOU Race Conditions zu verhindern.

        CWE-367 Prevention: Kein separater get_by_id() nach check_access() mehr
        noetig - diese Methode gibt den Space direkt zurueck wenn Zugriff erlaubt.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID die Zugriff benoetigt
            required_level: Erforderliche Zugriffsebene (read, write, manage, admin)

        Returns:
            Space wenn Zugriff erlaubt, None wenn Space nicht existiert
            oder kein Zugriff

        Raises:
            Keine - gibt None zurueck bei fehlendem Zugriff (Caller entscheidet
            ob 403 oder 404)
        """
        # Hole Space in einer atomaren Query
        space = await self.get_by_id(db, space_id)
        if not space:
            return None

        # Owner hat immer vollen Zugriff
        if space.owner_id == user_id:
            return space

        # Pruefe explizite Berechtigung mit expires_at Validierung
        from datetime import timezone
        now = datetime.now(timezone.utc)

        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space_id,
                PrivatSpaceAccess.user_id == user_id,
                PrivatSpaceAccess.is_active == True,
                # SECURITY: expires_at check
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            return None

        # Pruefe Zugriffsebene
        level_hierarchy = {
            "read": 1,
            "write": 2,
            "manage": 3,
            "admin": 4,
        }

        # Normalisiere PrivatAccessLevel zu String
        access_level_str = access.access_level
        if hasattr(access_level_str, "value"):
            access_level_str = access_level_str.value

        required_level_str = required_level
        if hasattr(required_level_str, "value"):
            required_level_str = required_level_str.value

        user_level = level_hierarchy.get(access_level_str, 0)
        needed_level = level_hierarchy.get(required_level_str, 0)

        if user_level >= needed_level:
            return space

        return None

    async def get_user_spaces(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        include_shared: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatSpaceListResponse:
        """Holt alle Spaces eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            include_shared: Geteilte Spaces einschliessen?
            page: Seitennummer
            page_size: Elemente pro Seite

        Returns:
            Paginierte Liste von Spaces mit Statistiken
        """
        # Basis-Query: Eigene Spaces (Soft-Delete Check)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        conditions = [
            PrivatSpace.owner_id == user_id,
            PrivatSpace.deleted_at == None,  # Soft-Delete Check
        ]

        if include_shared:
            # Auch Spaces, auf die der User Zugriff hat
            # SECURITY: Nur nicht-abgelaufene Access-Eintraege zaehlen!
            access_subquery = (
                select(PrivatSpaceAccess.space_id)
                .where(
                    PrivatSpaceAccess.user_id == user_id,
                    # SECURITY: expires_at check - None = kein Ablauf, sonst Datum pruefen
                    or_(
                        PrivatSpaceAccess.expires_at == None,
                        PrivatSpaceAccess.expires_at > now
                    ),
                )
            )
            conditions = [
                PrivatSpace.deleted_at == None,  # Soft-Delete Check
                (PrivatSpace.owner_id == user_id) |
                (PrivatSpace.id.in_(access_subquery))
            ]

        # Count total
        count_query = select(func.count(PrivatSpace.id)).where(and_(*conditions))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch spaces
        offset = (page - 1) * page_size
        query = (
            select(PrivatSpace)
            .where(and_(*conditions))
            .order_by(PrivatSpace.name)
            .offset(offset)
            .limit(page_size)
        )

        result = await db.execute(query)
        spaces = result.scalars().all()

        # Sammle Statistiken fuer jeden Space
        items = []
        for space in spaces:
            stats = await self.get_space_stats(db, space.id)
            items.append(PrivatSpaceWithStats(
                id=space.id,
                name=space.name,
                description=space.description,
                space_type=PrivatSpaceType(space.space_type),
                owner_id=space.owner_id,
                company_id=space.company_id,
                is_active=space.is_active,
                created_at=space.created_at,
                updated_at=space.updated_at,
                **stats,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatSpaceListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_space_stats(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> dict:
        """Holt Statistiken fuer einen Space.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Dict mit Statistiken
        """
        # Ordner zaehlen
        folder_count_result = await db.execute(
            select(func.count(PrivatFolder.id))
            .where(PrivatFolder.space_id == space_id)
        )
        folder_count = folder_count_result.scalar() or 0

        # Dokumente zaehlen und Groesse summieren
        doc_result = await db.execute(
            select(
                func.count(PrivatDocument.id),
                func.coalesce(func.sum(PrivatDocument.file_size), 0)
            )
            .where(PrivatDocument.space_id == space_id)
        )
        doc_row = doc_result.one()
        document_count = doc_row[0] or 0
        total_size_bytes = doc_row[1] or 0

        # Offene Fristen zaehlen
        from datetime import date
        deadline_result = await db.execute(
            select(func.count(PrivatDeadline.id))
            .where(
                PrivatDeadline.space_id == space_id,
                PrivatDeadline.is_completed == False,
                PrivatDeadline.due_date >= date.today(),
            )
        )
        pending_deadlines = deadline_result.scalar() or 0

        return {
            "folder_count": folder_count,
            "document_count": document_count,
            "total_size_bytes": total_size_bytes,
            "pending_deadlines": pending_deadlines,
        }

    async def update(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatSpaceUpdate,
    ) -> Optional[PrivatSpace]:
        """Aktualisiert einen Space.

        SECURITY FIX 23-3: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Space-Konfiguration entstehen

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Update-Daten

        Returns:
            Aktualisierter Space oder None
        """
        # SECURITY FIX 23-3: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatSpace)
            .where(PrivatSpace.id == space_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Space-Daten!
        )
        space = result.scalar_one_or_none()
        if not space:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(space, key, value)

        space.updated_at = utc_now()

        await db.commit()
        await db.refresh(space)

        logger.info(
            "privat_space_updated",
            space_id=str(space_id),
        )

        return space

    async def delete(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Loescht einen Space.

        SECURITY FIX 23-4: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            soft_delete: Soft-Delete (deaktivieren) oder hard delete

        Returns:
            True wenn erfolgreich
        """
        # SECURITY FIX 23-4: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatSpace)
            .where(PrivatSpace.id == space_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        space = result.scalar_one_or_none()
        if not space:
            return False

        if soft_delete:
            # Soft-Delete: Set deleted_at timestamp (is_active property returns False)
            space.deleted_at = utc_now()
            space.updated_at = utc_now()
            await db.commit()
        else:
            await db.delete(space)
            await db.commit()

        logger.info(
            "privat_space_deleted",
            space_id=str(space_id),
            soft_delete=soft_delete,
        )

        return True

    async def check_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        required_level: str = "read",
    ) -> bool:
        """Prueft ob ein Benutzer Zugriff auf einen Space hat.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID
            required_level: Erforderliche Zugriffsebene (read, write, admin)

        Returns:
            True wenn Zugriff erlaubt
        """
        space = await self.get_by_id(db, space_id)
        if not space:
            return False

        # Owner hat immer vollen Zugriff
        if space.owner_id == user_id:
            return True

        # Pruefe explizite Berechtigung
        # SECURITY: expires_at Validierung - abgelaufene Zugriffe ignorieren!
        from datetime import timezone
        now = datetime.now(timezone.utc)

        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space_id,
                PrivatSpaceAccess.user_id == user_id,
                # SECURITY: expires_at check - None = kein Ablauf, sonst Datum pruefen
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            return False

        # Level-Hierarchie: admin > write > read
        level_hierarchy = {"read": 1, "write": 2, "admin": 3}
        required = level_hierarchy.get(required_level, 1)
        granted = level_hierarchy.get(access.access_level, 0)

        return granted >= required
