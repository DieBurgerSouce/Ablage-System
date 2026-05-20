# -*- coding: utf-8 -*-
"""
Dashboard Sharing Service für Ablage-System.

Service für persistente Dashboard-Freigaben:
- Dashboard-Sharing mit Benutzern
- Berechtigungsverwaltung (view/edit)
- Audit-Trail aller Freigabe-Aktionen
- Zugriffsprüfung
- Ablaufdatum-Verwaltung

Feinpoliert und durchdacht - Enterprise-grade Dashboard Sharing Service.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models_dashboard_share import DashboardShare, DashboardShareAudit

logger = structlog.get_logger(__name__)


class DashboardSharingService:
    """
    Service für persistente Dashboard-Freigaben.

    Features:
    - Dashboard mit Benutzern teilen
    - Berechtigungen verwalten (view/edit)
    - Freigaben entfernen
    - Audit-Trail für alle Aktionen
    - Zugriffsprüfung
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den DashboardSharingService.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    async def share_dashboard(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        permission: str,
        shared_by: UUID,
        expires_at: Optional[datetime] = None,
    ) -> DashboardShare:
        """
        Teilt ein Dashboard mit einem Benutzer.

        Args:
            dashboard_id: ID des Dashboards
            user_id: ID des Benutzers der Zugriff erhält
            permission: Berechtigungsstufe (view oder edit)
            shared_by: ID des Benutzers der das Dashboard teilt
            expires_at: Optionales Ablaufdatum

        Returns:
            Erstellte DashboardShare-Instanz

        Raises:
            Exception: Bei Datenbankfehlern
        """
        try:
            # Prüfen ob bereits eine Freigabe existiert
            existing_stmt = select(DashboardShare).where(
                and_(
                    DashboardShare.dashboard_id == dashboard_id,
                    DashboardShare.shared_with_user_id == user_id,
                )
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update bestehende Freigabe
                existing.permission = permission
                existing.is_active = True
                existing.expires_at = expires_at
                share = existing

                # Audit: permission_changed
                await self._create_audit(
                    dashboard_share_id=share.id,
                    dashboard_id=dashboard_id,
                    action="permission_changed",
                    performed_by=shared_by,
                    details={
                        "new_permission": permission,
                        "user_id": str(user_id),
                        "expires_at": expires_at.isoformat() if expires_at else None,
                    },
                )

                logger.info(
                    "dashboard_share_updated",
                    dashboard_id=str(dashboard_id),
                    user_id=str(user_id),
                    permission=permission,
                    shared_by=str(shared_by),
                )
            else:
                # Neue Freigabe erstellen
                share = DashboardShare(
                    dashboard_id=dashboard_id,
                    shared_with_user_id=user_id,
                    shared_by_user_id=shared_by,
                    permission=permission,
                    expires_at=expires_at,
                )
                self.db.add(share)
                await self.db.flush()

                # Audit: shared
                await self._create_audit(
                    dashboard_share_id=share.id,
                    dashboard_id=dashboard_id,
                    action="shared",
                    performed_by=shared_by,
                    details={
                        "permission": permission,
                        "user_id": str(user_id),
                        "expires_at": expires_at.isoformat() if expires_at else None,
                    },
                )

                logger.info(
                    "dashboard_shared",
                    dashboard_id=str(dashboard_id),
                    user_id=str(user_id),
                    permission=permission,
                    shared_by=str(shared_by),
                )

            await self.db.commit()
            return share

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "dashboard_share_failed",
                **safe_error_log(e),
                dashboard_id=str(dashboard_id),
                user_id=str(user_id),
            )
            raise

    async def unshare_dashboard(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        performed_by: UUID,
    ) -> bool:
        """
        Entfernt die Freigabe eines Dashboards.

        Verwendet Soft-Delete (is_active=False).

        Args:
            dashboard_id: ID des Dashboards
            user_id: ID des Benutzers dessen Zugriff entfernt wird
            performed_by: ID des Benutzers der die Aktion durchführt

        Returns:
            True wenn Freigabe gefunden und deaktiviert, False sonst
        """
        try:
            stmt = select(DashboardShare).where(
                and_(
                    DashboardShare.dashboard_id == dashboard_id,
                    DashboardShare.shared_with_user_id == user_id,
                    DashboardShare.is_active == True,  # noqa: E712
                )
            )
            result = await self.db.execute(stmt)
            share = result.scalar_one_or_none()

            if not share:
                logger.warning(
                    "dashboard_share_not_found",
                    dashboard_id=str(dashboard_id),
                    user_id=str(user_id),
                )
                return False

            # Soft-Delete
            share.is_active = False

            # Audit: unshared
            await self._create_audit(
                dashboard_share_id=share.id,
                dashboard_id=dashboard_id,
                action="unshared",
                performed_by=performed_by,
                details={
                    "user_id": str(user_id),
                },
            )

            await self.db.commit()

            logger.info(
                "dashboard_unshared",
                dashboard_id=str(dashboard_id),
                user_id=str(user_id),
                performed_by=str(performed_by),
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "dashboard_unshare_failed",
                **safe_error_log(e),
                dashboard_id=str(dashboard_id),
                user_id=str(user_id),
            )
            raise

    async def update_permission(
        self,
        share_id: UUID,
        permission: str,
        performed_by: UUID,
    ) -> Optional[DashboardShare]:
        """
        Aktualisiert die Berechtigung einer Freigabe.

        Args:
            share_id: ID der Freigabe
            permission: Neue Berechtigungsstufe (view oder edit)
            performed_by: ID des Benutzers der die Änderung durchführt

        Returns:
            Aktualisierte DashboardShare-Instanz oder None
        """
        try:
            stmt = select(DashboardShare).where(
                and_(
                    DashboardShare.id == share_id,
                    DashboardShare.is_active == True,  # noqa: E712
                )
            )
            result = await self.db.execute(stmt)
            share = result.scalar_one_or_none()

            if not share:
                logger.warning("dashboard_share_not_found", share_id=str(share_id))
                return None

            old_permission = share.permission
            share.permission = permission

            # Audit: permission_changed
            await self._create_audit(
                dashboard_share_id=share.id,
                dashboard_id=share.dashboard_id,
                action="permission_changed",
                performed_by=performed_by,
                details={
                    "old_permission": old_permission,
                    "new_permission": permission,
                    "user_id": str(share.shared_with_user_id),
                },
            )

            await self.db.commit()

            logger.info(
                "dashboard_share_permission_updated",
                share_id=str(share_id),
                old_permission=old_permission,
                new_permission=permission,
                performed_by=str(performed_by),
            )

            return share

        except Exception as e:
            await self.db.rollback()
            logger.error(
                "dashboard_share_permission_update_failed",
                **safe_error_log(e),
                share_id=str(share_id),
            )
            raise

    async def list_shares(self, dashboard_id: UUID) -> List[DashboardShare]:
        """
        Listet alle aktiven Freigaben eines Dashboards.

        Args:
            dashboard_id: ID des Dashboards

        Returns:
            Liste von DashboardShare-Instanzen
        """
        try:
            stmt = (
                select(DashboardShare)
                .where(
                    and_(
                        DashboardShare.dashboard_id == dashboard_id,
                        DashboardShare.is_active == True,  # noqa: E712
                        or_(
                            DashboardShare.expires_at.is_(None),
                            DashboardShare.expires_at > datetime.now(timezone.utc),
                        ),
                    )
                )
                .order_by(DashboardShare.created_at.desc())
            )
            result = await self.db.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error(
                "dashboard_shares_list_failed",
                **safe_error_log(e),
                dashboard_id=str(dashboard_id),
            )
            raise

    async def get_shared_dashboards(self, user_id: UUID) -> List[Dict[str, object]]:
        """
        Listet alle Dashboards die mit einem Benutzer geteilt wurden.

        Args:
            user_id: ID des Benutzers

        Returns:
            Liste von Dicts mit Dashboard-Informationen
        """
        try:
            stmt = (
                select(DashboardShare)
                .where(
                    and_(
                        DashboardShare.shared_with_user_id == user_id,
                        DashboardShare.is_active == True,  # noqa: E712
                        or_(
                            DashboardShare.expires_at.is_(None),
                            DashboardShare.expires_at > datetime.now(timezone.utc),
                        ),
                    )
                )
                .order_by(DashboardShare.created_at.desc())
            )
            result = await self.db.execute(stmt)
            shares = result.scalars().all()

            return [
                {
                    "dashboard_id": str(share.dashboard_id),
                    "permission": share.permission,
                    "shared_by_user_id": str(share.shared_by_user_id),
                    "created_at": share.created_at.isoformat(),
                    "expires_at": (
                        share.expires_at.isoformat() if share.expires_at else None
                    ),
                }
                for share in shares
            ]

        except Exception as e:
            logger.error(
                "shared_dashboards_list_failed",
                **safe_error_log(e),
                user_id=str(user_id),
            )
            raise

    async def check_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
    ) -> Optional[str]:
        """
        Prüft Zugriffsrecht eines Benutzers auf ein Dashboard.

        Args:
            dashboard_id: ID des Dashboards
            user_id: ID des Benutzers

        Returns:
            Berechtigungsstufe (view oder edit) oder None
        """
        try:
            stmt = select(DashboardShare.permission).where(
                and_(
                    DashboardShare.dashboard_id == dashboard_id,
                    DashboardShare.shared_with_user_id == user_id,
                    DashboardShare.is_active == True,  # noqa: E712
                    or_(
                        DashboardShare.expires_at.is_(None),
                        DashboardShare.expires_at > datetime.now(timezone.utc),
                    ),
                )
            )
            result = await self.db.execute(stmt)
            permission = result.scalar_one_or_none()

            return permission

        except Exception as e:
            logger.error(
                "dashboard_access_check_failed",
                **safe_error_log(e),
                dashboard_id=str(dashboard_id),
                user_id=str(user_id),
            )
            raise

    async def _create_audit(
        self,
        dashboard_share_id: Optional[UUID],
        dashboard_id: UUID,
        action: str,
        performed_by: UUID,
        details: Optional[Dict[str, object]] = None,
    ) -> None:
        """
        Erstellt einen Audit-Eintrag.

        Args:
            dashboard_share_id: Optional ID der Freigabe
            dashboard_id: ID des Dashboards
            action: Aktion (shared, unshared, permission_changed)
            performed_by: ID des Benutzers
            details: Optionale zusätzliche Details
        """
        audit = DashboardShareAudit(
            dashboard_share_id=dashboard_share_id,
            dashboard_id=dashboard_id,
            action=action,
            performed_by_id=performed_by,
            details=details,
        )
        self.db.add(audit)
        await self.db.flush()


def get_sharing_service(db: AsyncSession) -> DashboardSharingService:
    """
    Factory für DashboardSharingService.

    Args:
        db: AsyncSession für Datenbankzugriff

    Returns:
        DashboardSharingService-Instanz
    """
    return DashboardSharingService(db)
