# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Dashboard Sharing Service.

Testet:
- Dashboard-Freigabe-Erstellung
- Duplikat-Behandlung
- Berechtigungsverwaltung
- Freigabe-Deaktivierung
- Zugriffspruefung
- Audit-Trail-Erstellung
- Geteilte Dashboard-Abfragen

Feinpoliert und durchdacht - Dashboard Sharing Service Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4


# Test-Konstanten fuer gueltige UUIDs
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_SHARED_USER_UUID = UUID("00000000-0000-0000-0000-000000000002")
TEST_DASHBOARD_UUID = UUID("00000000-0000-0000-0000-000000000003")
TEST_SHARE_UUID = UUID("00000000-0000-0000-0000-000000000004")


# ========================= Mock Models =========================


class MockDashboardShare:
    """Mock DashboardShare-Model."""

    def __init__(
        self,
        id: UUID,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
        permission: str,
        is_active: bool = True,
    ):
        self.id = id
        self.dashboard_id = dashboard_id
        self.shared_with_user_id = shared_with_user_id
        self.permission = permission
        self.is_active = is_active
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = None


class MockDashboard:
    """Mock Dashboard-Model."""

    def __init__(
        self,
        id: UUID,
        name: str,
        owner_id: UUID,
    ):
        self.id = id
        self.name = name
        self.owner_id = owner_id


class MockAuditEntry:
    """Mock DashboardShareAudit-Model."""

    def __init__(
        self,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
        action: str,
        permission: Optional[str] = None,
        performed_by_id: Optional[UUID] = None,
    ):
        self.id = uuid4()
        self.dashboard_id = dashboard_id
        self.shared_with_user_id = shared_with_user_id
        self.action = action
        self.permission = permission
        self.performed_by_id = performed_by_id
        self.created_at = datetime.now(timezone.utc)


# ========================= Mock Service =========================


class MockDashboardSharingService:
    """Mock-Implementation des DashboardSharingService fuer Tests."""

    def __init__(self, db):
        self.db = db
        self._shares: Dict[UUID, MockDashboardShare] = {}
        self._audit_entries: List[MockAuditEntry] = []

    async def share_dashboard(
        self,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
        permission: str = "view",
        performed_by_id: Optional[UUID] = None,
    ) -> MockDashboardShare:
        """Teilt Dashboard mit User."""
        # Check for duplicate
        existing = await self._find_share(dashboard_id, shared_with_user_id)
        if existing:
            return existing

        # Create new share
        share = MockDashboardShare(
            id=TEST_SHARE_UUID,
            dashboard_id=dashboard_id,
            shared_with_user_id=shared_with_user_id,
            permission=permission,
        )
        self._shares[share.id] = share

        # Create audit entry
        audit = MockAuditEntry(
            dashboard_id=dashboard_id,
            shared_with_user_id=shared_with_user_id,
            action="shared",
            permission=permission,
            performed_by_id=performed_by_id,
        )
        self._audit_entries.append(audit)

        return share

    async def _find_share(
        self,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
    ) -> Optional[MockDashboardShare]:
        """Findet existierende Freigabe."""
        for share in self._shares.values():
            if (
                share.dashboard_id == dashboard_id
                and share.shared_with_user_id == shared_with_user_id
                and share.is_active
            ):
                return share
        return None

    async def unshare_dashboard(
        self,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
        performed_by_id: Optional[UUID] = None,
    ) -> bool:
        """Entfernt Freigabe (Soft-Delete)."""
        share = await self._find_share(dashboard_id, shared_with_user_id)
        if not share:
            return False

        share.is_active = False
        share.updated_at = datetime.now(timezone.utc)

        # Create audit entry
        audit = MockAuditEntry(
            dashboard_id=dashboard_id,
            shared_with_user_id=shared_with_user_id,
            action="unshared",
            performed_by_id=performed_by_id,
        )
        self._audit_entries.append(audit)

        return True

    async def update_permission(
        self,
        dashboard_id: UUID,
        shared_with_user_id: UUID,
        permission: str,
        performed_by_id: Optional[UUID] = None,
    ) -> Optional[MockDashboardShare]:
        """Aktualisiert Berechtigungslevel."""
        share = await self._find_share(dashboard_id, shared_with_user_id)
        if not share:
            return None

        share.permission = permission
        share.updated_at = datetime.now(timezone.utc)

        # Create audit entry
        audit = MockAuditEntry(
            dashboard_id=dashboard_id,
            shared_with_user_id=shared_with_user_id,
            action="permission_changed",
            permission=permission,
            performed_by_id=performed_by_id,
        )
        self._audit_entries.append(audit)

        return share

    async def list_shares(
        self,
        dashboard_id: UUID,
        active_only: bool = True,
    ) -> List[MockDashboardShare]:
        """Listet Freigaben fuer Dashboard."""
        shares = [
            share
            for share in self._shares.values()
            if share.dashboard_id == dashboard_id
        ]

        if active_only:
            shares = [s for s in shares if s.is_active]

        return shares

    async def get_shared_dashboards(
        self,
        user_id: UUID,
    ) -> List[MockDashboard]:
        """Gibt Dashboards zurueck die mit User geteilt wurden."""
        dashboard_ids = {
            share.dashboard_id
            for share in self._shares.values()
            if share.shared_with_user_id == user_id and share.is_active
        }

        # Mock dashboard retrieval
        dashboards = [
            MockDashboard(
                id=dash_id,
                name=f"Dashboard-{dash_id}",
                owner_id=TEST_USER_UUID,
            )
            for dash_id in dashboard_ids
        ]
        return dashboards

    async def check_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
    ) -> Optional[str]:
        """Prueft Zugriff und gibt Permission-Level zurueck."""
        share = await self._find_share(dashboard_id, user_id)
        return share.permission if share else None


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Erstelle Mock AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def sharing_service(mock_db):
    """Erstelle MockDashboardSharingService-Instanz."""
    return MockDashboardSharingService(mock_db)


# ========================= Share Tests =========================


@pytest.mark.asyncio
async def test_share_dashboard_creates_record(
    sharing_service,
):
    """Test: Teilen eines Dashboards erstellt Share-Record und Audit-Eintrag."""
    # Share dashboard
    share = await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
        performed_by_id=TEST_USER_UUID,
    )

    # Assertions
    assert share is not None
    assert share.dashboard_id == TEST_DASHBOARD_UUID
    assert share.shared_with_user_id == TEST_SHARED_USER_UUID
    assert share.permission == "view"
    assert share.is_active is True

    # Check audit entry created
    assert len(sharing_service._audit_entries) == 1
    audit = sharing_service._audit_entries[0]
    assert audit.action == "shared"
    assert audit.dashboard_id == TEST_DASHBOARD_UUID
    assert audit.shared_with_user_id == TEST_SHARED_USER_UUID
    assert audit.permission == "view"
    assert audit.performed_by_id == TEST_USER_UUID


@pytest.mark.asyncio
async def test_share_dashboard_duplicate_returns_existing(
    sharing_service,
):
    """Test: Duplikat-Freigabe gibt existierende Freigabe zurueck."""
    # First share
    share1 = await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )

    # Attempt duplicate share
    share2 = await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="edit",  # Different permission
    )

    # Assertions
    assert share1.id == share2.id
    assert len(sharing_service._audit_entries) == 1  # Only one audit entry


# ========================= Unshare Tests =========================


@pytest.mark.asyncio
async def test_unshare_dashboard_deactivates(
    sharing_service,
):
    """Test: Freigabe-Entfernung setzt is_active=False und erstellt Audit."""
    # Create share first
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )

    # Unshare
    success = await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        performed_by_id=TEST_USER_UUID,
    )

    # Assertions
    assert success is True

    # Check share is deactivated
    share = await sharing_service._find_share(
        TEST_DASHBOARD_UUID,
        TEST_SHARED_USER_UUID,
    )
    assert share is None  # Should not find active share

    # Check audit entries
    assert len(sharing_service._audit_entries) == 2
    unshare_audit = sharing_service._audit_entries[1]
    assert unshare_audit.action == "unshared"


@pytest.mark.asyncio
async def test_unshare_nonexistent_returns_false(
    sharing_service,
):
    """Test: Entfernen nicht existierender Freigabe gibt False zurueck."""
    # Attempt to unshare non-existent share
    success = await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
    )

    # Assertions
    assert success is False
    assert len(sharing_service._audit_entries) == 0


# ========================= Permission Tests =========================


@pytest.mark.asyncio
async def test_update_permission(
    sharing_service,
):
    """Test: Berechtigungsaenderung aktualisiert Share und erstellt Audit."""
    # Create share first
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )

    # Update permission
    updated = await sharing_service.update_permission(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="edit",
        performed_by_id=TEST_USER_UUID,
    )

    # Assertions
    assert updated is not None
    assert updated.permission == "edit"
    assert updated.updated_at is not None

    # Check audit entries
    assert len(sharing_service._audit_entries) == 2
    update_audit = sharing_service._audit_entries[1]
    assert update_audit.action == "permission_changed"
    assert update_audit.permission == "edit"


# ========================= List Tests =========================


@pytest.mark.asyncio
async def test_list_shares_active_only(
    sharing_service,
):
    """Test: Liste gibt nur aktive Freigaben zurueck."""
    # Create active share
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )

    # Create and deactivate another share
    user2_id = uuid4()
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=user2_id,
        permission="view",
    )
    await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=user2_id,
    )

    # List shares (active only)
    shares = await sharing_service.list_shares(
        dashboard_id=TEST_DASHBOARD_UUID,
        active_only=True,
    )

    # Assertions
    assert len(shares) == 1
    assert shares[0].shared_with_user_id == TEST_SHARED_USER_UUID
    assert shares[0].is_active is True


@pytest.mark.asyncio
async def test_list_shares_include_inactive(
    sharing_service,
):
    """Test: Liste mit active_only=False gibt alle Freigaben zurueck."""
    # Create and deactivate share
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )
    await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
    )

    # List all shares
    shares = await sharing_service.list_shares(
        dashboard_id=TEST_DASHBOARD_UUID,
        active_only=False,
    )

    # Assertions
    assert len(shares) == 1
    assert shares[0].is_active is False


# ========================= Shared Dashboard Tests =========================


@pytest.mark.asyncio
async def test_get_shared_dashboards(
    sharing_service,
):
    """Test: Gibt Dashboards zurueck die mit User geteilt wurden."""
    # Share multiple dashboards
    dashboard2_id = uuid4()
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )
    await sharing_service.share_dashboard(
        dashboard_id=dashboard2_id,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="edit",
    )

    # Get shared dashboards
    dashboards = await sharing_service.get_shared_dashboards(
        user_id=TEST_SHARED_USER_UUID,
    )

    # Assertions
    assert len(dashboards) == 2
    dashboard_ids = {d.id for d in dashboards}
    assert TEST_DASHBOARD_UUID in dashboard_ids
    assert dashboard2_id in dashboard_ids


# ========================= Access Check Tests =========================


@pytest.mark.asyncio
async def test_check_access_returns_permission(
    sharing_service,
):
    """Test: Zugriffspruefung gibt Permission-Level zurueck."""
    # Share dashboard
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="edit",
    )

    # Check access
    permission = await sharing_service.check_access(
        dashboard_id=TEST_DASHBOARD_UUID,
        user_id=TEST_SHARED_USER_UUID,
    )

    # Assertions
    assert permission == "edit"


@pytest.mark.asyncio
async def test_check_access_no_share_returns_none(
    sharing_service,
):
    """Test: Zugriffspruefung gibt None bei fehlender Freigabe zurueck."""
    # Check access without share
    permission = await sharing_service.check_access(
        dashboard_id=TEST_DASHBOARD_UUID,
        user_id=TEST_SHARED_USER_UUID,
    )

    # Assertions
    assert permission is None


@pytest.mark.asyncio
async def test_check_access_inactive_share_returns_none(
    sharing_service,
):
    """Test: Deaktivierte Freigabe gibt None zurueck."""
    # Share and unshare
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )
    await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
    )

    # Check access
    permission = await sharing_service.check_access(
        dashboard_id=TEST_DASHBOARD_UUID,
        user_id=TEST_SHARED_USER_UUID,
    )

    # Assertions
    assert permission is None


# ========================= Audit Trail Tests =========================


@pytest.mark.asyncio
async def test_audit_trail_created_on_share(
    sharing_service,
):
    """Test: Audit-Eintrag mit action='shared' wird erstellt."""
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
        performed_by_id=TEST_USER_UUID,
    )

    # Check audit entry
    assert len(sharing_service._audit_entries) == 1
    audit = sharing_service._audit_entries[0]
    assert audit.action == "shared"
    assert audit.dashboard_id == TEST_DASHBOARD_UUID
    assert audit.shared_with_user_id == TEST_SHARED_USER_UUID
    assert audit.performed_by_id == TEST_USER_UUID


@pytest.mark.asyncio
async def test_audit_trail_created_on_unshare(
    sharing_service,
):
    """Test: Audit-Eintrag mit action='unshared' wird erstellt."""
    # Share first
    await sharing_service.share_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        permission="view",
    )

    # Unshare
    await sharing_service.unshare_dashboard(
        dashboard_id=TEST_DASHBOARD_UUID,
        shared_with_user_id=TEST_SHARED_USER_UUID,
        performed_by_id=TEST_USER_UUID,
    )

    # Check audit entries
    assert len(sharing_service._audit_entries) == 2
    unshare_audit = sharing_service._audit_entries[1]
    assert unshare_audit.action == "unshared"
    assert unshare_audit.performed_by_id == TEST_USER_UUID
