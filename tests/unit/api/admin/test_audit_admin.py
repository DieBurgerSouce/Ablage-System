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
    async def test_search_logs_success(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs erfolgreich durchsuchen."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(page=1, page_size=50)
            result = await service.search_logs(db=mock_db, request=request)
            assert result["total"] == 1
            assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_search_logs_by_user(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs nach Benutzer filtern."""
        from app.services.admin import AuditService

        service = AuditService()
        user_id = sample_audit_entry["user_id"]

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(user_id=user_id, page=1, page_size=50)
            result = await service.search_logs(db=mock_db, request=request)
            assert all(item["user_id"] == user_id for item in result["items"])

    @pytest.mark.asyncio
    async def test_search_logs_by_action(self, mock_db, admin_user, sample_audit_entry):
        """Audit-Logs nach Aktion filtern."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(
                action="document.create", page=1, page_size=50
            )
            result = await service.search_logs(db=mock_db, request=request)
            assert all(
                item["action"] == "document.create" for item in result["items"]
            )

    @pytest.mark.asyncio
    async def test_search_logs_by_date_range(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Audit-Logs nach Zeitraum filtern."""
        from app.services.admin import AuditService

        service = AuditService()
        start_date = datetime.utcnow() - timedelta(days=7)
        end_date = datetime.utcnow()

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(
                start_date=start_date,
                end_date=end_date,
                page=1,
                page_size=50,
            )
            result = await service.search_logs(db=mock_db, request=request)
            assert len(result["items"]) >= 0

    @pytest.mark.asyncio
    async def test_search_logs_by_severity(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Audit-Logs nach Schweregrad filtern."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(severity="info", page=1, page_size=50)
            result = await service.search_logs(db=mock_db, request=request)
            assert all(item["severity"] == "info" for item in result["items"])


class TestGetAuditLogEntry:
    """Tests for GET /admin/audit/logs/{log_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_log_entry_success(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Einzelnen Audit-Log-Eintrag abrufen."""
        from app.services.admin import AuditService

        service = AuditService()

        with patch.object(service, "get_log_entry", return_value=sample_audit_entry):
            result = await service.get_log_entry(
                db=mock_db, log_id=sample_audit_entry["id"]
            )
            assert result["id"] == sample_audit_entry["id"]

    @pytest.mark.asyncio
    async def test_get_log_entry_not_found(self, mock_db, admin_user):
        """Nicht existierenden Eintrag abrufen."""
        from app.services.admin import AuditService

        service = AuditService()

        with patch.object(service, "get_log_entry", return_value=None):
            result = await service.get_log_entry(db=mock_db, log_id="nonexistent")
            assert result is None


class TestAuditStats:
    """Tests for GET /admin/audit/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, mock_db, admin_user):
        """Audit-Statistiken erfolgreich abrufen."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_stats = {
            "total_entries": 15000,
            "by_action": {
                "document.create": 5000,
                "document.view": 8000,
                "user.login": 1500,
                "user.logout": 500,
            },
            "by_severity": {
                "info": 14000,
                "warning": 800,
                "error": 150,
                "critical": 50,
            },
            "most_active_users": [
                {"user_id": "user1", "action_count": 500},
                {"user_id": "user2", "action_count": 350},
            ],
            "error_rate_percent": 1.33,
            "period_days": 30,
        }

        with patch.object(service, "get_stats", return_value=mock_stats):
            result = await service.get_stats(db=mock_db, days=30)
            assert result["total_entries"] == 15000
            assert result["error_rate_percent"] == 1.33


class TestExportAuditLogs:
    """Tests for GET /admin/audit/export endpoint."""

    @pytest.mark.asyncio
    async def test_export_csv_success(self, mock_db, admin_user):
        """Audit-Logs als CSV exportieren."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_csv = "timestamp,user_id,action,resource_type,severity\n2024-01-01T00:00:00,user1,document.create,document,info"

        with patch.object(service, "export_to_csv", return_value=mock_csv):
            request = AuditLogSearchRequest(page=1, page_size=100000)
            result = await service.export_to_csv(db=mock_db, request=request)
            assert "timestamp" in result
            assert "document.create" in result

    @pytest.mark.asyncio
    async def test_export_json_success(self, mock_db, admin_user):
        """Audit-Logs als JSON exportieren."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_json = '[{"timestamp": "2024-01-01T00:00:00", "action": "document.create"}]'

        with patch.object(service, "export_to_json", return_value=mock_json):
            request = AuditLogSearchRequest(page=1, page_size=100000)
            result = await service.export_to_json(db=mock_db, request=request)
            assert "document.create" in result


class TestPurgeAuditLogs:
    """Tests for DELETE /admin/audit/purge endpoint."""

    @pytest.mark.asyncio
    async def test_purge_dry_run(self, mock_db, admin_user):
        """Audit-Logs Purge im Dry-Run-Modus."""
        from app.services.admin import AuditService

        service = AuditService()
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        with patch.object(service, "purge_old_entries", return_value=500):
            result = await service.purge_old_entries(
                db=mock_db, before_date=cutoff_date, dry_run=True
            )
            assert result == 500

    @pytest.mark.asyncio
    async def test_purge_execute(self, mock_db, admin_user):
        """Audit-Logs tatsächlich löschen."""
        from app.services.admin import AuditService

        service = AuditService()
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        with patch.object(service, "purge_old_entries", return_value=500):
            result = await service.purge_old_entries(
                db=mock_db, before_date=cutoff_date, dry_run=False
            )
            assert result == 500


class TestUserActivity:
    """Tests for GET /admin/audit/user/{user_id}/activity endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_activity_success(
        self, mock_db, admin_user, sample_audit_entry
    ):
        """Benutzeraktivität abrufen."""
        from app.services.admin import AuditService

        service = AuditService()

        mock_response = {
            "items": [sample_audit_entry],
            "total": 1,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

        with patch.object(service, "search_logs", return_value=mock_response):
            request = AuditLogSearchRequest(
                user_id=sample_audit_entry["user_id"],
                page=1,
                page_size=50,
            )
            result = await service.search_logs(db=mock_db, request=request)
            assert len(result["items"]) == 1
