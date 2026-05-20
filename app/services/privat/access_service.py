"""Service für Zugriffsverwaltung auf Privat-Spaces."""

import uuid
from datetime import datetime
from app.core.datetime_utils import utc_now
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatSpace, PrivatSpaceAccess, User
from app.db.schemas import (
    PrivatSpaceAccessCreate,
    PrivatSpaceAccessUpdate,
    PrivatSpaceAccessResponse,
    PrivatAccessLevel,
)

logger = structlog.get_logger(__name__)


class PrivatAccessService:
    """Service für Zugriffsberechtigungen auf Privat-Spaces."""

    async def grant_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatSpaceAccessCreate,
        granted_by: uuid.UUID,
    ) -> PrivatSpaceAccess:
        """Gewährt einem Benutzer Zugriff auf einen Space.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Zugriffs-Daten
            granted_by: ID des gewährenden Benutzers

        Returns:
            Erstellte Berechtigung
        """
        # Prüfe ob bereits Zugriff existiert
        existing = await self.get_access(db, space_id, data.user_id)
        if existing:
            # Update bestehende Berechtigung
            existing.access_level = data.access_level.value
            existing.granted_by = granted_by
            existing.expires_at = None  # SECURITY: Reset wenn reaktiviert!
            await db.commit()
            await db.refresh(existing)
            return existing

        access = PrivatSpaceAccess(
            id=uuid.uuid4(),
            space_id=space_id,
            user_id=data.user_id,
            access_level=data.access_level.value,
            granted_by=granted_by,
            created_at=utc_now(),
        )

        db.add(access)
        await db.commit()
        await db.refresh(access)

        logger.info(
            "privat_access_granted",
            space_id=str(space_id),
            user_id=str(data.user_id),
            access_level=data.access_level.value,
            granted_by=str(granted_by),
        )

        return access

    async def get_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[PrivatSpaceAccess]:
        """Holt die Berechtigung eines Benutzers für einen Space.

        SECURITY: Validiert expires_at - abgelaufene Berechtigungen werden ignoriert!

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID

        Returns:
            Berechtigung oder None (auch wenn abgelaufen)
        """
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # SECURITY: expires_at Validierung - abgelaufene Zugriffe ignorieren!
        result = await db.execute(
            select(PrivatSpaceAccess).where(
                PrivatSpaceAccess.space_id == space_id,
                PrivatSpaceAccess.user_id == user_id,
                # SECURITY: expires_at check - None = kein Ablauf, sonst Datum prüfen
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        return result.scalar_one_or_none()

    async def list_space_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> List[PrivatSpaceAccessResponse]:
        """Listet alle aktiven Berechtigungen für einen Space.

        SECURITY: Filtert abgelaufene Zugriffe aus (CWE-200 Prevention)!

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Liste von aktiven Berechtigungen (ohne abgelaufene)
        """
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # SECURITY: Nur aktive (nicht-abgelaufene) Zugriffe zurückgeben
        result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space_id,
                # SECURITY: expires_at check - abgelaufene Zugriffe ausfiltern
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
            .order_by(PrivatSpaceAccess.created_at)
        )

        accesses = result.scalars().all()
        return [
            PrivatSpaceAccessResponse(
                id=access.id,
                space_id=access.space_id,
                user_id=access.user_id,
                access_level=PrivatAccessLevel(access.access_level),
                granted_by=access.granted_by,
                created_at=access.created_at,
                expires_at=access.expires_at,
                is_active=True,  # Nur aktive (nicht-abgelaufene) werden zurückgegeben
            )
            for access in accesses
        ]

    async def update_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        data: PrivatSpaceAccessUpdate,
    ) -> Optional[PrivatSpaceAccess]:
        """Aktualisiert eine Berechtigung.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID
            data: Update-Daten

        Returns:
            Aktualisierte Berechtigung oder None
        """
        access = await self.get_access(db, space_id, user_id)
        if not access:
            return None

        if data.access_level:
            access.access_level = data.access_level.value

        await db.commit()
        await db.refresh(access)

        logger.info(
            "privat_access_updated",
            space_id=str(space_id),
            user_id=str(user_id),
            access_level=access.access_level,
        )

        return access

    async def revoke_access(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Entzieht einem Benutzer den Zugriff (Soft-Revoke via expires_at).

        SECURITY: Verwendet Soft-Revoke statt Hard-Delete für:
        - Audit-Trail Compliance (GDPR)
        - Wiederherstellbarkeit
        - Nachvollziehbarkeit von Zugriffsänderungen

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        from datetime import timezone
        access = await self.get_access(db, space_id, user_id)
        if not access:
            return False

        # SECURITY: Soft-Revoke - setze expires_at auf jetzt
        # Dadurch wird der Zugriff sofort ungültig, aber der Record bleibt erhalten
        access.expires_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "privat_access_revoked",
            space_id=str(space_id),
            user_id=str(user_id),
            revoked_at=str(access.expires_at),
        )

        return True

    async def check_permission(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        required_level: PrivatAccessLevel,
    ) -> bool:
        """Prüft ob ein Benutzer die erforderliche Berechtigung hat.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            user_id: Benutzer-ID
            required_level: Erforderliche Zugriffsebene

        Returns:
            True wenn Zugriff erlaubt
        """
        # Prüfe ob Owner
        space_result = await db.execute(
            select(PrivatSpace).where(PrivatSpace.id == space_id)
        )
        space = space_result.scalar_one_or_none()

        if not space:
            return False

        if space.owner_id == user_id:
            return True

        # Prüfe explizite Berechtigung
        access = await self.get_access(db, space_id, user_id)
        if not access:
            return False

        # Level-Hierarchie
        level_hierarchy = {
            PrivatAccessLevel.READ.value: 1,
            PrivatAccessLevel.WRITE.value: 2,
            PrivatAccessLevel.ADMIN.value: 3,
        }

        required = level_hierarchy.get(required_level.value, 1)
        granted = level_hierarchy.get(access.access_level, 0)

        return granted >= required

    async def get_user_accessible_spaces(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[uuid.UUID]:
        """Holt alle Space-IDs auf die ein Benutzer Zugriff hat.

        SECURITY: Nur nicht-abgelaufene Zugriffe werden berücksichtigt!

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID

        Returns:
            Liste von Space-IDs
        """
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # Eigene Spaces
        owned_result = await db.execute(
            select(PrivatSpace.id).where(PrivatSpace.owner_id == user_id)
        )
        owned = [row[0] for row in owned_result]

        # Geteilte Spaces - SECURITY: expires_at Validierung!
        shared_result = await db.execute(
            select(PrivatSpaceAccess.space_id)
            .where(
                PrivatSpaceAccess.user_id == user_id,
                # SECURITY: expires_at check - nur gültige Zugriffe
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        shared = [row[0] for row in shared_result]

        return list(set(owned + shared))
