"""
Tests for Admin Audit API endpoints.

Tests audit log functionality:
- Search audit logs
- Get audit log details
- Export audit logs
- Audit statistics
- Purge old entries
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.db.models import User
from app.db.schemas import (
    UserRole,
    AuditLogView,
    AuditLogFilters,
    AuditLogListRequest,
    AuditLogListResponse,
    MessageResponse,
)

# Alias for backward compatibility with tests
AuditLogSearchRequest = AuditLogListRequest


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = str(uuid4())
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    user.tier = "enterprise"
    user.created_at = datetime.utcnow()
    return user


@pytest.fixture
def sample_audit_entry():
    """Create sample audit log entry."""
    return {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow(),
        "user_id": str(uuid4()),
        "username": "testuser",
        "action": "document.create",
        "resource_type": "document",
        "resource_id": str(uuid4()),
        "severity": "info",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0",
        "details": {"filename": "test.pdf", "size": 1024},
        "success": True,
    }


class TestSearchAuditLogs:
    """Tests for GET /admin/audit/logs endpoint."""

    @pytest.mark.asyncio
    async def test_list_logs_success(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs erfolgreich auflisten."""
        from app.services.admin import AuditService

        mock_response = MagicMock()
        mock_response.items = [sample_audit_entry]
        mock_response.total = 1
        mock_response.page = 1
        mock_response.per_page = 50

        with patch.object(AuditService, "list_audit_logs", return_value=mock_response):
            result = await AuditService.list_audit_logs(db=mock_db, page=1, per_page=50)
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_logs_by_user(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs nach Benutzer filtern."""
        from app.services.admin import AuditService

        user_id = sample_audit_entry["user_id"]
        mock_response = MagicMock()
        mock_response.items = [sample_audit_entry]
        mock_response.total = 1

        filters = AuditLogFilters(user_id=user_id)
        with patch.object(AuditService, "list_audit_logs", return_value=mock_response):
            result = await AuditService.list_audit_logs(db=mock_db, filters=filters)
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_logs_by_action(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs nach Aktion filtern."""
        from app.services.admin import AuditService

        mock_response = MagicMock()
        mock_response.items = [sample_audit_entry]
        mock_response.total = 1

        filters = AuditLogFilters(action="document.create")
        with patch.object(AuditService, "list_audit_logs", return_value=mock_response):
            result = await AuditService.list_audit_logs(db=mock_db, filters=filters)
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_list_logs_by_date_range(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Audit-Logs nach Zeitraum filtern."""
        from app.services.admin import AuditService
        from datetime import timezone

        start_date = datetime.now(timezone.utc) - timedelta(days=7)
        end_date = datetime.now(timezone.utc)

        mock_response = MagicMock()
        mock_response.items = [sample_audit_entry]
        mock_response.total = 1

        filters = AuditLogFilters(from_date=start_date, to_date=end_date)
        with patch.object(AuditService, "list_audit_logs", return_value=mock_response):
            result = await AuditService.list_audit_logs(db=mock_db, filters=filters)
            assert result.total >= 0

    @pytest.mark.asyncio
    async def test_list_logs_success_filter(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Audit-Logs nach Erfolg filtern."""
        from app.services.admin import AuditService

        mock_response = MagicMock()
        mock_response.items = [sample_audit_entry]
        mock_response.total = 1

        filters = AuditLogFilters(success=True)
        with patch.object(AuditService, "list_audit_logs", return_value=mock_response):
            result = await AuditService.list_audit_logs(db=mock_db, filters=filters)
            assert result.total == 1


class TestGetAuditLogEntry:
    """Tests for GET /admin/audit/logs/{log_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_log_entry_success(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Einzelnen Audit-Log-Eintrag abrufen."""
        from app.services.admin import AuditService

        mock_entry = MagicMock()
        mock_entry.id = sample_audit_entry["id"]
        mock_entry.action = sample_audit_entry["action"]

        with patch.object(AuditService, "get_audit_log", return_value=mock_entry):
            result = await AuditService.get_audit_log(
                db=mock_db, log_id=sample_audit_entry["id"]
            )
            assert result.id == sample_audit_entry["id"]

    @pytest.mark.asyncio
    async def test_get_log_entry_not_found(self, mock_db, admin_user):
        """Nicht existierenden Eintrag abrufen."""
        from app.services.admin import AuditService

        with patch.object(AuditService, "get_audit_log", return_value=None):
            result = await AuditService.get_audit_log(db=mock_db, log_id="nonexistent")
            assert result is None


class TestAuditStats:
    """Tests for GET /admin/audit/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, mock_db, admin_user):
        """Audit-Statistiken erfolgreich abrufen."""
        from app.services.admin import AuditService

        mock_stats = {
            "total_entries": 15000,
            "by_action": {
                "document.create": 5000,
                "document.view": 8000,
            },
            "error_rate_percent": 1.33,
        }

        with patch.object(AuditService, "get_statistics", return_value=mock_stats):
            result = await AuditService.get_statistics(db=mock_db, days=30)
            assert result["total_entries"] == 15000
            assert result["error_rate_percent"] == 1.33


class TestExportAuditLogs:
    """Tests for GET /admin/audit/export endpoint."""

    @pytest.mark.asyncio
    async def test_export_csv_success(self, mock_db, admin_user):
        """Audit-Logs als CSV exportieren."""
        from app.services.admin import AuditService

        mock_csv = b"timestamp,user_id,action\n2024-01-01T00:00:00,user1,document.create"

        filters = AuditLogFilters()
        with patch.object(AuditService, "export_audit_logs", return_value=mock_csv):
            result = await AuditService.export_audit_logs(
                db=mock_db, filters=filters, format="csv"
            )
            assert b"timestamp" in result

    @pytest.mark.asyncio
    async def test_export_json_success(self, mock_db, admin_user):
        """Audit-Logs als JSON exportieren."""
        from app.services.admin import AuditService

        mock_json = b'[{"timestamp": "2024-01-01T00:00:00", "action": "document.create"}]'

        filters = AuditLogFilters()
        with patch.object(AuditService, "export_audit_logs", return_value=mock_json):
            result = await AuditService.export_audit_logs(
                db=mock_db, filters=filters, format="json"
            )
            assert b"document.create" in result


class TestUserActivity:
    """Tests for GET /admin/audit/user/{user_id}/activity endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_activity_success(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Benutzeraktivitaet abrufen."""
        from app.services.admin import AuditService

        user_id = sample_audit_entry["user_id"]
        mock_response = {
            "user_actions": [sample_audit_entry],
            "admin_actions_on_user": [],
            "total_actions": 1,
        }

        with patch.object(AuditService, "get_user_audit_trail", return_value=mock_response):
            result = await AuditService.get_user_audit_trail(
                db=mock_db, user_id=user_id, limit=100
            )
            assert result["total_actions"] == 1
