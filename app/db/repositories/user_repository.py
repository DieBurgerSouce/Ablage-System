"""
User Repository für Benutzer-spezifische Datenbankoperationen.

Erweitert BaseRepository um benutzer-spezifische Queries.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.repositories.base import BaseRepository
from app.db.models import User

logger = structlog.get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Repository für Benutzer-Operationen.

    Erweitert BaseRepository um:
    - Authentifizierungs-Queries
    - Status-Verwaltung
    - Aktivitätstracking
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert das User Repository."""
        super().__init__(db, User)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Findet Benutzer nach E-Mail-Adresse.

        Args:
            email: E-Mail-Adresse (case-insensitive)

        Returns:
            Benutzer oder None
        """
        result = await self.db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Findet Benutzer nach Benutzername.

        Args:
            username: Benutzername (case-insensitive)

        Returns:
            Benutzer oder None
        """
        result = await self.db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_active_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        Lädt alle aktiven Benutzer.

        Args:
            skip: Offset für Pagination
            limit: Maximale Anzahl

        Returns:
            Liste von aktiven Benutzern
        """
        query = select(User).where(User.is_active == True)
        query = query.order_by(User.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_superusers(self) -> List[User]:
        """
        Lädt alle Superuser/Administratoren.

        Returns:
            Liste von Superusern
        """
        result = await self.db.execute(
            select(User).where(
                and_(User.is_superuser == True, User.is_active == True)
            )
        )
        return list(result.scalars().all())

    async def update_last_login(self, user_id: UUID) -> bool:
        """
        Aktualisiert den letzten Login-Zeitpunkt.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        result = await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def update_last_activity(self, user_id: UUID) -> bool:
        """
        Aktualisiert den letzten Aktivitätszeitpunkt.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        result = await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_activity_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def deactivate(self, user_id: UUID) -> bool:
        """
        Deaktiviert einen Benutzer.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.is_active = False
        await self.db.commit()

        logger.info(
            "user_deactivated",
            user_id=str(user_id)
        )

        return True

    async def activate(self, user_id: UUID) -> bool:
        """
        Aktiviert einen Benutzer.

        Args:
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.is_active = True
        await self.db.commit()

        logger.info(
            "user_activated",
            user_id=str(user_id)
        )

        return True

    async def get_inactive_users(
        self,
        days_inactive: int = 90
    ) -> List[User]:
        """
        Findet inaktive Benutzer (für GDPR-Cleanup).

        Args:
            days_inactive: Anzahl Tage ohne Aktivität

        Returns:
            Liste inaktiver Benutzer
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_inactive)

        result = await self.db.execute(
            select(User).where(
                and_(
                    User.is_active == True,
                    or_(
                        User.last_activity_at < cutoff,
                        and_(
                            User.last_activity_at.is_(None),
                            User.last_login < cutoff
                        )
                    )
                )
            )
        )
        return list(result.scalars().all())

    async def get_users_scheduled_for_deletion(self) -> List[User]:
        """
        Findet Benutzer, deren Löschung geplant ist (GDPR).

        Returns:
            Liste von Benutzern mit geplanter Löschung
        """
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(User).where(
                and_(
                    User.deletion_scheduled_for.isnot(None),
                    User.deletion_scheduled_for <= now,
                    User.deletion_confirmed == True
                )
            )
        )
        return list(result.scalars().all())

    async def search(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20
    ) -> List[User]:
        """
        Sucht Benutzer nach Name, E-Mail oder Benutzername.

        Args:
            query: Suchbegriff
            skip: Offset für Pagination
            limit: Maximale Anzahl

        Returns:
            Liste von Benutzern
        """
        search_term = f"%{query.lower()}%"

        result = await self.db.execute(
            select(User).where(
                or_(
                    func.lower(User.email).like(search_term),
                    func.lower(User.username).like(search_term),
                    func.lower(User.full_name).like(search_term)
                )
            )
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_tier(self, tier: str) -> int:
        """
        Zählt Benutzer nach Tier.

        Args:
            tier: Tier-Name (free, premium, admin)

        Returns:
            Anzahl der Benutzer
        """
        result = await self.db.execute(
            select(func.count()).select_from(User).where(User.tier == tier)
        )
        return result.scalar() or 0

    async def get_user_stats(self) -> dict:
        """
        Ermittelt Benutzerstatistiken.

        Returns:
            Dictionary mit Statistiken
        """
        # Gesamtzahl
        total = await self.count()

        # Aktive Benutzer
        active_result = await self.db.execute(
            select(func.count()).select_from(User).where(User.is_active == True)
        )
        active = active_result.scalar() or 0

        # Superuser
        superuser_result = await self.db.execute(
            select(func.count()).select_from(User).where(User.is_superuser == True)
        )
        superusers = superuser_result.scalar() or 0

        # Neue Benutzer (letzte 30 Tage)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        new_result = await self.db.execute(
            select(func.count()).select_from(User).where(
                User.created_at >= thirty_days_ago
            )
        )
        new_users = new_result.scalar() or 0

        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "superusers": superusers,
            "new_last_30_days": new_users,
        }
