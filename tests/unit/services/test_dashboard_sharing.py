# -*- coding: utf-8 -*-
"""
Tests fuer Dashboard Sharing Service.

Testet:
- Dashboard-Freigabe erstellen
- Freigabe entfernen
- Berechtigung aendern
- Zugriffspruefung
- Audit-Trail
- Ablaufdatum-Handling
"""

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_dashboard_share import DashboardShare, DashboardShareAudit
from app.services.dashboard.sharing_service import DashboardSharingService


@pytest.fixture
def dashboard_id():
    """Test Dashboard ID."""
    return uuid4()


@pytest.fixture
def owner_id():
    """Dashboard Owner User ID."""
    return uuid4()


@pytest.fixture
def viewer_id():
    """Viewer User ID."""
    return uuid4()


@pytest.fixture
def editor_id():
    """Editor User ID."""
    return uuid4()


@pytest.fixture
def db_session(test_db):
    """Alias auf die echte PostgreSQL-Session (conftest `test_db`).

    Die Tests benoetigen eine echte async DB-Session (JSONB/UUID-Typen). Ist
    keine Test-DB erreichbar, ueberspringt `test_db` sauber (kein gruen-biegen).
    """
    return test_db


@pytest.mark.asyncio
class TestDashboardSharingService:
    """Tests fuer DashboardSharingService."""

    async def test_share_dashboard_new(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Neue Dashboard-Freigabe erstellen."""
        service = DashboardSharingService(db_session)

        # Freigabe erstellen
        share = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        assert share is not None
        assert share.dashboard_id == dashboard_id
        assert share.shared_with_user_id == viewer_id
        assert share.shared_by_user_id == owner_id
        assert share.permission == "view"
        assert share.is_active is True
        assert share.expires_at is None

        # Audit-Eintrag pruefen
        stmt = select(DashboardShareAudit).where(
            DashboardShareAudit.dashboard_share_id == share.id
        )
        result = await db_session.execute(stmt)
        audit = result.scalar_one_or_none()

        assert audit is not None
        assert audit.action == "shared"
        assert audit.dashboard_id == dashboard_id
        assert audit.performed_by_id == owner_id
        assert audit.details["permission"] == "view"
        assert audit.details["user_id"] == str(viewer_id)

    async def test_share_dashboard_with_expiry(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Dashboard-Freigabe mit Ablaufdatum."""
        service = DashboardSharingService(db_session)
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        share = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
            expires_at=expires_at,
        )

        assert share.expires_at is not None
        assert abs((share.expires_at - expires_at).total_seconds()) < 1

    async def test_share_dashboard_update_existing(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Bestehende Freigabe aktualisieren."""
        service = DashboardSharingService(db_session)

        # Erste Freigabe
        share1 = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        # Berechtigung aendern
        share2 = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="edit",
            shared_by=owner_id,
        )

        # Sollte dieselbe Freigabe sein
        assert share1.id == share2.id
        assert share2.permission == "edit"

        # Zwei Audit-Eintraege: "shared" und "permission_changed"
        stmt = select(DashboardShareAudit).where(
            DashboardShareAudit.dashboard_share_id == share1.id
        )
        result = await db_session.execute(stmt)
        audits = list(result.scalars().all())

        assert len(audits) == 2
        assert audits[0].action == "shared"
        assert audits[1].action == "permission_changed"
        assert audits[1].details["new_permission"] == "edit"

    async def test_unshare_dashboard(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Dashboard-Freigabe entfernen."""
        service = DashboardSharingService(db_session)

        # Freigabe erstellen
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        # Freigabe entfernen
        result = await service.unshare_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            performed_by=owner_id,
        )

        assert result is True

        # Freigabe sollte is_active=False haben
        stmt = select(DashboardShare).where(
            DashboardShare.dashboard_id == dashboard_id,
            DashboardShare.shared_with_user_id == viewer_id,
        )
        result = await db_session.execute(stmt)
        share = result.scalar_one_or_none()

        assert share is not None
        assert share.is_active is False

        # Audit-Eintrag "unshared" pruefen
        stmt = select(DashboardShareAudit).where(
            DashboardShareAudit.action == "unshared"
        )
        result = await db_session.execute(stmt)
        audit = result.scalar_one_or_none()

        assert audit is not None
        assert audit.dashboard_id == dashboard_id

    async def test_unshare_nonexistent(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Nicht existierende Freigabe entfernen."""
        service = DashboardSharingService(db_session)

        result = await service.unshare_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            performed_by=owner_id,
        )

        assert result is False

    async def test_update_permission(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Berechtigung einer Freigabe aendern."""
        service = DashboardSharingService(db_session)

        # Freigabe erstellen
        share = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        # Berechtigung aendern
        updated = await service.update_permission(
            share_id=share.id,
            permission="edit",
            performed_by=owner_id,
        )

        assert updated is not None
        assert updated.permission == "edit"

        # Audit pruefen
        stmt = select(DashboardShareAudit).where(
            DashboardShareAudit.action == "permission_changed"
        )
        result = await db_session.execute(stmt)
        audit = result.scalar_one_or_none()

        assert audit is not None
        assert audit.details["old_permission"] == "view"
        assert audit.details["new_permission"] == "edit"

    async def test_list_shares(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
        editor_id,
    ):
        """Test: Alle Freigaben eines Dashboards auflisten."""
        service = DashboardSharingService(db_session)

        # Zwei Freigaben erstellen
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=editor_id,
            permission="edit",
            shared_by=owner_id,
        )

        # Auflisten
        shares = await service.list_shares(dashboard_id=dashboard_id)

        assert len(shares) == 2
        permissions = {share.permission for share in shares}
        assert permissions == {"view", "edit"}

    async def test_list_shares_excludes_expired(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
        editor_id,
    ):
        """Test: Abgelaufene Freigaben werden nicht aufgelistet."""
        service = DashboardSharingService(db_session)

        # Aktive Freigabe
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        # Abgelaufene Freigabe
        expired = datetime.now(timezone.utc) - timedelta(days=1)
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=editor_id,
            permission="edit",
            shared_by=owner_id,
            expires_at=expired,
        )

        # Nur die aktive Freigabe sollte erscheinen
        shares = await service.list_shares(dashboard_id=dashboard_id)

        assert len(shares) == 1
        assert shares[0].shared_with_user_id == viewer_id

    async def test_get_shared_dashboards(
        self,
        db_session: AsyncSession,
        owner_id,
        viewer_id,
    ):
        """Test: Alle mit Benutzer geteilten Dashboards."""
        service = DashboardSharingService(db_session)

        dashboard1 = uuid4()
        dashboard2 = uuid4()

        # Zwei Dashboards mit Benutzer teilen
        await service.share_dashboard(
            dashboard_id=dashboard1,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )
        await service.share_dashboard(
            dashboard_id=dashboard2,
            user_id=viewer_id,
            permission="edit",
            shared_by=owner_id,
        )

        # Geteilte Dashboards abrufen
        shared = await service.get_shared_dashboards(user_id=viewer_id)

        assert len(shared) == 2
        dashboard_ids = {item["dashboard_id"] for item in shared}
        assert str(dashboard1) in dashboard_ids
        assert str(dashboard2) in dashboard_ids

    async def test_check_access_granted(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Zugriffspruefung - Zugriff gewaehrt."""
        service = DashboardSharingService(db_session)

        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="edit",
            shared_by=owner_id,
        )

        permission = await service.check_access(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
        )

        assert permission == "edit"

    async def test_check_access_denied(
        self,
        db_session: AsyncSession,
        dashboard_id,
        viewer_id,
    ):
        """Test: Zugriffspruefung - Kein Zugriff."""
        service = DashboardSharingService(db_session)

        permission = await service.check_access(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
        )

        assert permission is None

    async def test_check_access_expired(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Zugriffspruefung - Abgelaufen."""
        service = DashboardSharingService(db_session)

        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
            expires_at=expired,
        )

        permission = await service.check_access(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
        )

        assert permission is None

    async def test_unique_constraint(
        self,
        db_session: AsyncSession,
        dashboard_id,
        owner_id,
        viewer_id,
    ):
        """Test: Eindeutigkeit Dashboard-Benutzer-Paar."""
        service = DashboardSharingService(db_session)

        # Erste Freigabe
        share1 = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="view",
            shared_by=owner_id,
        )

        # Zweite Freigabe sollte die erste aktualisieren
        share2 = await service.share_dashboard(
            dashboard_id=dashboard_id,
            user_id=viewer_id,
            permission="edit",
            shared_by=owner_id,
        )

        # Sollte dieselbe ID sein
        assert share1.id == share2.id

        # Nur ein Eintrag in der Datenbank
        stmt = select(DashboardShare).where(
            DashboardShare.dashboard_id == dashboard_id,
            DashboardShare.shared_with_user_id == viewer_id,
        )
        result = await db_session.execute(stmt)
        shares = list(result.scalars().all())

        assert len(shares) == 1
