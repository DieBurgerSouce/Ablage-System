# -*- coding: utf-8 -*-
"""
Unit-Tests für Audit Service.

Testet:
- Audit-Log-Listung mit Filterung und Paginierung
- Audit-Log-Einzelabfrage
- Admin-Action-Listung
- User-Audit-Trail (kombiniert)
- Export-Funktionen (CSV, JSON)
- Statistik-Generierung
- Sortierung und Filter

Feinpoliert und durchdacht - Enterprise-grade Audit-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
import csv
import json
import io


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_user():
    """Create sample user object."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    return user


@pytest.fixture
def sample_admin():
    """Create sample admin user object."""
    admin = Mock()
    admin.id = uuid4()
    admin.email = "admin@example.com"
    admin.is_active = True
    admin.is_superuser = True
    return admin


@pytest.fixture
def sample_audit_log():
    """Create sample audit log object."""
    log = Mock()
    log.id = uuid4()
    log.user_id = uuid4()
    log.action = "document.read"
    log.resource_type = "document"
    log.resource_id = str(uuid4())  # UUID als String, nicht "doc-123"
    log.ip_address = "192.168.1.100"
    log.user_agent = "Mozilla/5.0"
    log.success = True
    log.error_message = None
    log.audit_metadata = {"extra": "data"}
    log.created_at = datetime.now(timezone.utc)
    return log


@pytest.fixture
def sample_admin_action():
    """Create sample admin action object."""
    action = Mock()
    action.id = uuid4()
    action.admin_id = uuid4()
    action.target_user_id = uuid4()
    action.action = "user.deactivated"
    action.action_details = {"reason": "Verdaechtige Aktivitaet"}
    action.ip_address = "10.0.0.1"
    action.user_agent = "Admin Console"
    action.created_at = datetime.now(timezone.utc)
    return action


@pytest.fixture
def audit_log_filters():
    """Create sample audit log filters."""
    from app.db.schemas import AuditLogFilters

    return AuditLogFilters(
        action="document.read",
        resource_type="document"
    )


# ========================= List Audit Logs Tests =========================


class TestListAuditLogs:
    """Tests for listing audit logs."""

    @pytest.mark.asyncio
    async def test_list_audit_logs_basic(self, mock_db, sample_audit_log, sample_user):
        """Basis-Listung sollte funktionieren."""
        from app.services.admin.audit_service import AuditService

        # Mock query results
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = [sample_audit_log]

        mock_users_result = Mock()
        mock_users_result.scalars.return_value.all.return_value = [sample_user]

        mock_action_result = Mock()
        mock_action_result.all.return_value = [("document.read", 5)]

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_users_result,
            mock_action_result
        ]

        # Patch the user_id to match
        sample_audit_log.user_id = sample_user.id

        result = await AuditService.list_audit_logs(mock_db, page=1, per_page=50)

        assert result.total == 1
        assert result.page == 1
        assert len(result.logs) == 1

    @pytest.mark.asyncio
    async def test_list_audit_logs_with_filters(self, mock_db, sample_audit_log, sample_user):
        """Filterung sollte angewendet werden."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import AuditLogFilters

        filters = AuditLogFilters(
            action="document.read",
            resource_type="document",
            success=True
        )

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = [sample_audit_log]

        mock_users_result = Mock()
        mock_users_result.scalars.return_value.all.return_value = []

        mock_action_result = Mock()
        mock_action_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_users_result,
            mock_action_result
        ]

        result = await AuditService.list_audit_logs(mock_db, filters=filters)

        assert result.total == 1
        # Verify filter was applied (check execute was called)
        assert mock_db.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_list_audit_logs_pagination(self, mock_db, sample_audit_log, sample_user):
        """Paginierung sollte korrekt funktionieren."""
        from app.services.admin.audit_service import AuditService

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 100

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = [sample_audit_log]

        mock_users_result = Mock()
        mock_users_result.scalars.return_value.all.return_value = []

        mock_action_result = Mock()
        mock_action_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_users_result,
            mock_action_result
        ]

        result = await AuditService.list_audit_logs(mock_db, page=2, per_page=20)

        assert result.total == 100
        assert result.page == 2
        assert result.per_page == 20
        assert result.total_pages == 5

    @pytest.mark.asyncio
    async def test_list_audit_logs_empty(self, mock_db):
        """Leere Ergebnisse sollten funktionieren."""
        from app.services.admin.audit_service import AuditService

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_action_result = Mock()
        mock_action_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_action_result
        ]

        result = await AuditService.list_audit_logs(mock_db)

        assert result.total == 0
        assert len(result.logs) == 0
        assert result.total_pages == 1


# ========================= Get Audit Log Tests =========================


class TestGetAuditLog:
    """Tests for retrieving single audit log."""

    @pytest.mark.asyncio
    async def test_get_audit_log_found(self, mock_db, sample_audit_log, sample_user):
        """Vorhandener Log sollte zurückgegeben werden."""
        from app.services.admin.audit_service import AuditService

        mock_log_result = Mock()
        mock_log_result.scalar_one_or_none.return_value = sample_audit_log

        mock_user_result = Mock()
        mock_user_result.scalar_one_or_none.return_value = sample_user

        mock_db.execute.side_effect = [mock_log_result, mock_user_result]

        sample_audit_log.user_id = sample_user.id

        result = await AuditService.get_audit_log(mock_db, sample_audit_log.id)

        assert result is not None
        assert result.action == "document.read"
        assert result.user_email == sample_user.email

    @pytest.mark.asyncio
    async def test_get_audit_log_not_found(self, mock_db):
        """Nicht vorhandener Log sollte None zurückgeben."""
        from app.services.admin.audit_service import AuditService

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await AuditService.get_audit_log(mock_db, uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_audit_log_without_user(self, mock_db, sample_audit_log):
        """Log ohne User sollte funktionieren."""
        from app.services.admin.audit_service import AuditService

        sample_audit_log.user_id = None

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_audit_log
        mock_db.execute.return_value = mock_result

        result = await AuditService.get_audit_log(mock_db, sample_audit_log.id)

        assert result is not None
        assert result.user_email is None


# ========================= List Admin Actions Tests =========================


class TestListAdminActions:
    """Tests for listing admin actions."""

    @pytest.mark.asyncio
    async def test_list_admin_actions_basic(self, mock_db, sample_admin_action, sample_admin, sample_user):
        """Basis-Listung von Admin-Aktionen."""
        from app.services.admin.audit_service import AuditService

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_actions_result = Mock()
        mock_actions_result.scalars.return_value.all.return_value = [sample_admin_action]

        mock_users_result = Mock()
        mock_users_result.scalars.return_value.all.return_value = [sample_admin, sample_user]

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_actions_result,
            mock_users_result
        ]

        sample_admin_action.admin_id = sample_admin.id
        sample_admin_action.target_user_id = sample_user.id

        result = await AuditService.list_admin_actions(mock_db)

        assert result["total"] == 1
        assert len(result["actions"]) == 1

    @pytest.mark.asyncio
    async def test_list_admin_actions_with_filters(self, mock_db, sample_admin_action):
        """Filterung von Admin-Aktionen."""
        from app.services.admin.audit_service import AuditService

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_actions_result = Mock()
        mock_actions_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_actions_result]

        result = await AuditService.list_admin_actions(
            mock_db,
            admin_id=uuid4(),
            action="user.deactivated"
        )

        assert result["total"] == 0


# ========================= User Audit Trail Tests =========================


class TestUserAuditTrail:
    """Tests for user audit trail."""

    @pytest.mark.asyncio
    async def test_get_user_audit_trail(self, mock_db, sample_audit_log, sample_admin_action, sample_admin):
        """Kombinierter Audit-Trail eines Benutzers."""
        from app.services.admin.audit_service import AuditService

        user_id = uuid4()

        mock_audit_result = Mock()
        mock_audit_result.scalars.return_value.all.return_value = [sample_audit_log]

        mock_admin_result = Mock()
        mock_admin_result.scalars.return_value.all.return_value = [sample_admin_action]

        mock_admins_result = Mock()
        mock_admins_result.scalars.return_value.all.return_value = [sample_admin]

        mock_db.execute.side_effect = [
            mock_audit_result,
            mock_admin_result,
            mock_admins_result
        ]

        sample_admin_action.admin_id = sample_admin.id

        result = await AuditService.get_user_audit_trail(mock_db, user_id)

        assert result["user_id"] == str(user_id)
        assert result["user_action_count"] == 1
        assert result["admin_action_count"] == 1
        assert len(result["entries"]) == 2

    @pytest.mark.asyncio
    async def test_get_user_audit_trail_empty(self, mock_db):
        """Leerer Audit-Trail."""
        from app.services.admin.audit_service import AuditService

        user_id = uuid4()

        mock_audit_result = Mock()
        mock_audit_result.scalars.return_value.all.return_value = []

        mock_admin_result = Mock()
        mock_admin_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_audit_result, mock_admin_result]

        result = await AuditService.get_user_audit_trail(mock_db, user_id)

        assert result["user_action_count"] == 0
        assert result["admin_action_count"] == 0


# ========================= Export Tests =========================


class TestExportAuditLogs:
    """Tests for audit log export."""

    def test_export_to_csv_format(self, sample_audit_log, sample_user):
        """CSV-Export sollte korrektes Format haben."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import AuditLogView

        resource_uuid = uuid4()
        log_view = AuditLogView(
            id=sample_audit_log.id,
            user_id=sample_user.id,
            user_email=sample_user.email,
            action="document.read",
            resource_type="document",
            resource_id=resource_uuid,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            success=True,
            error_message=None,
            metadata={},
            created_at=datetime.now(timezone.utc)
        )

        csv_bytes = AuditService._export_to_csv([log_view])

        # Decode and parse
        csv_content = csv_bytes.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Check header
        assert rows[0][0] == "ID"
        assert rows[0][4] == "Aktion"

        # Check data row
        assert rows[1][4] == "document.read"
        assert rows[1][8] == "Ja"  # success

    def test_export_to_csv_failure_status(self, sample_audit_log, sample_user):
        """CSV-Export sollte Fehler-Status korrekt anzeigen."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import AuditLogView

        resource_uuid = uuid4()
        log_view = AuditLogView(
            id=sample_audit_log.id,
            user_id=sample_user.id,
            user_email=sample_user.email,
            action="document.delete",
            resource_type="document",
            resource_id=resource_uuid,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            success=False,
            error_message="Permission denied",
            metadata={},
            created_at=datetime.now(timezone.utc)
        )

        csv_bytes = AuditService._export_to_csv([log_view])
        csv_content = csv_bytes.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        assert rows[1][8] == "Nein"  # failure
        assert rows[1][9] == "Permission denied"

    def test_export_to_json_format(self, sample_audit_log, sample_user):
        """JSON-Export sollte korrektes Format haben."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import AuditLogView

        resource_uuid = uuid4()
        log_view = AuditLogView(
            id=sample_audit_log.id,
            user_id=sample_user.id,
            user_email=sample_user.email,
            action="document.read",
            resource_type="document",
            resource_id=resource_uuid,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            success=True,
            error_message=None,
            metadata={"key": "value"},
            created_at=datetime.now(timezone.utc)
        )

        json_bytes = AuditService._export_to_json([log_view])
        data = json.loads(json_bytes.decode('utf-8'))

        assert len(data) == 1
        assert data[0]["action"] == "document.read"
        assert data[0]["success"] is True
        assert data[0]["metadata"]["key"] == "value"

    def test_export_empty_logs(self):
        """Export leerer Logs sollte funktionieren."""
        from app.services.admin.audit_service import AuditService

        csv_bytes = AuditService._export_to_csv([])
        json_bytes = AuditService._export_to_json([])

        # CSV should have header only
        csv_content = csv_bytes.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 1  # Header only

        # JSON should be empty array
        data = json.loads(json_bytes.decode('utf-8'))
        assert data == []


# ========================= Statistics Tests =========================


class TestStatistics:
    """Tests for audit log statistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, mock_db, sample_user):
        """Statistik-Generierung."""
        from app.services.admin.audit_service import AuditService

        # Mock all statistic queries
        mock_total = Mock()
        mock_total.scalar.return_value = 100

        mock_by_action = Mock()
        mock_by_action.all.return_value = [("document.read", 50), ("user.login", 30)]

        mock_by_resource = Mock()
        mock_by_resource.all.return_value = [("document", 70), ("user", 30)]

        mock_success = Mock()
        mock_success.all.return_value = [(True, 95), (False, 5)]

        mock_users = Mock()
        mock_users.all.return_value = [(sample_user.id, 50)]

        mock_users_detail = Mock()
        mock_users_detail.scalars.return_value.all.return_value = [sample_user]

        mock_admin_count = Mock()
        mock_admin_count.scalar.return_value = 20

        mock_db.execute.side_effect = [
            mock_total,
            mock_by_action,
            mock_by_resource,
            mock_success,
            mock_users,
            mock_users_detail,
            mock_admin_count
        ]

        result = await AuditService.get_statistics(mock_db, days=30)

        assert result["period_days"] == 30
        assert result["total_entries"] == 100
        assert result["success_count"] == 95
        assert result["failure_count"] == 5
        assert result["admin_action_count"] == 20
        assert "document.read" in result["by_action"]

    @pytest.mark.asyncio
    async def test_get_statistics_empty(self, mock_db):
        """Statistik bei leeren Daten."""
        from app.services.admin.audit_service import AuditService

        mock_total = Mock()
        mock_total.scalar.return_value = 0

        mock_empty = Mock()
        mock_empty.all.return_value = []

        mock_admin_count = Mock()
        mock_admin_count.scalar.return_value = 0

        mock_db.execute.side_effect = [
            mock_total,
            mock_empty,  # by_action
            mock_empty,  # by_resource
            mock_empty,  # success
            mock_empty,  # users
            mock_admin_count
        ]

        result = await AuditService.get_statistics(mock_db)

        assert result["total_entries"] == 0
        assert result["success_count"] == 0
        assert result["failure_count"] == 0
        assert result["most_active_users"] == []


# ========================= Sorting Tests =========================


class TestSorting:
    """Tests for sorting functionality."""

    @pytest.mark.asyncio
    async def test_sort_ascending(self, mock_db):
        """Aufsteigende Sortierung."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import SortOrder

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_action_result = Mock()
        mock_action_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_action_result
        ]

        result = await AuditService.list_audit_logs(
            mock_db,
            sort_by="created_at",
            sort_order=SortOrder.ASC
        )

        # Verify query was made (sorting is applied in query)
        assert mock_db.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_sort_descending(self, mock_db):
        """Absteigende Sortierung (Standard)."""
        from app.services.admin.audit_service import AuditService
        from app.db.schemas import SortOrder

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_logs_result = Mock()
        mock_logs_result.scalars.return_value.all.return_value = []

        mock_action_result = Mock()
        mock_action_result.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count_result,
            mock_logs_result,
            mock_action_result
        ]

        result = await AuditService.list_audit_logs(
            mock_db,
            sort_order=SortOrder.DESC
        )

        assert mock_db.execute.call_count == 3
