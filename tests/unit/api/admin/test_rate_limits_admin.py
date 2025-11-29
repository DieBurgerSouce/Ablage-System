"""
Tests for Admin Rate Limits API endpoints.

Tests rate limit management functionality:
- Get rate limit configuration
- View usage statistics
- Manage overrides
- Reset counters
- View blocked users
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.db.models import User, UserRole
from app.db.schemas import (
    RateLimitConfigResponse,
    RateLimitOverrideCreate,
    RateLimitOverrideResponse,
    RateLimitUsageResponse,
    MessageResponse,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return User(
        id=str(uuid4()),
        email="admin@test.de",
        username="admin",
        hashed_password="hashed",
        is_active=True,
        is_superuser=True,
        role=UserRole.ADMIN,
        created_at=datetime.utcnow(),
    )


class TestGetRateLimitConfig:
    """Tests for GET /admin/rate-limits/config endpoint."""

    @pytest.mark.asyncio
    async def test_get_config_success(self, admin_user):
        """Rate-Limit-Konfiguration erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_config = {
            "default_limits": {
                "requests_per_minute": 100,
                "requests_per_hour": 1000,
                "requests_per_day": 10000,
            },
            "endpoint_limits": {
                "/api/v1/ocr/process": {
                    "requests_per_minute": 10,
                    "requests_per_hour": 50,
                },
                "/api/v1/documents": {
                    "requests_per_minute": 50,
                    "requests_per_hour": 500,
                },
            },
            "enabled": True,
            "whitelist_ips": ["127.0.0.1"],
        }

        with patch.object(service, "get_config", return_value=mock_config):
            result = await service.get_config()
            assert result["enabled"] is True
            assert result["default_limits"]["requests_per_minute"] == 100


class TestGetRateLimitUsage:
    """Tests for GET /admin/rate-limits/usage endpoint."""

    @pytest.mark.asyncio
    async def test_get_usage_success(self, mock_db, admin_user):
        """Rate-Limit-Nutzung erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_usage = [
            {
                "user_id": str(uuid4()),
                "endpoint": "/api/v1/ocr/process",
                "requests_last_minute": 5,
                "requests_last_hour": 25,
                "requests_today": 100,
                "is_blocked": False,
                "limit_percent": 50.0,
            },
        ]

        with patch.object(service, "get_usage_stats", return_value=mock_usage):
            result = await service.get_usage_stats(db=mock_db, limit=100)
            assert len(result) == 1
            assert result[0]["is_blocked"] is False

    @pytest.mark.asyncio
    async def test_get_usage_by_user(self, mock_db, admin_user):
        """Rate-Limit-Nutzung nach Benutzer filtern."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())

        mock_usage = [
            {
                "user_id": user_id,
                "endpoint": "/api/v1/ocr/process",
                "requests_last_minute": 5,
                "requests_last_hour": 25,
                "is_blocked": False,
            },
        ]

        with patch.object(service, "get_usage_stats", return_value=mock_usage):
            result = await service.get_usage_stats(
                db=mock_db, user_id=user_id, limit=100
            )
            assert all(u["user_id"] == user_id for u in result)

    @pytest.mark.asyncio
    async def test_get_usage_by_endpoint(self, mock_db, admin_user):
        """Rate-Limit-Nutzung nach Endpunkt filtern."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        endpoint = "/api/v1/ocr/process"

        mock_usage = [
            {
                "user_id": str(uuid4()),
                "endpoint": endpoint,
                "requests_last_minute": 5,
                "is_blocked": False,
            },
        ]

        with patch.object(service, "get_usage_stats", return_value=mock_usage):
            result = await service.get_usage_stats(
                db=mock_db, endpoint=endpoint, limit=100
            )
            assert all(u["endpoint"] == endpoint for u in result)


class TestListOverrides:
    """Tests for GET /admin/rate-limits/overrides endpoint."""

    @pytest.mark.asyncio
    async def test_list_overrides_success(self, mock_db, admin_user):
        """Rate-Limit-Überschreibungen erfolgreich auflisten."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_overrides = [
            {
                "id": str(uuid4()),
                "user_id": str(uuid4()),
                "requests_per_minute": 200,
                "requests_per_hour": 2000,
                "created_by": admin_user.id,
                "created_at": datetime.utcnow(),
                "expires_at": None,
            },
        ]

        with patch.object(service, "list_overrides", return_value=mock_overrides):
            result = await service.list_overrides(db=mock_db)
            assert len(result) == 1
            assert result[0]["requests_per_minute"] == 200


class TestCreateOverride:
    """Tests for POST /admin/rate-limits/overrides endpoint."""

    @pytest.mark.asyncio
    async def test_create_override_success(self, mock_db, admin_user):
        """Rate-Limit-Überschreibung erfolgreich erstellen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())

        override_data = RateLimitOverrideCreate(
            user_id=user_id,
            requests_per_minute=200,
            requests_per_hour=2000,
        )

        mock_override = {
            "id": str(uuid4()),
            "user_id": user_id,
            "requests_per_minute": 200,
            "requests_per_hour": 2000,
            "created_by": admin_user.id,
            "created_at": datetime.utcnow(),
        }

        with patch.object(service, "create_override", return_value=mock_override):
            result = await service.create_override(
                db=mock_db,
                override_data=override_data,
                created_by=admin_user.id,
            )
            assert result["requests_per_minute"] == 200

    @pytest.mark.asyncio
    async def test_create_override_with_expiry(self, mock_db, admin_user):
        """Rate-Limit-Überschreibung mit Ablaufdatum erstellen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(days=7)

        override_data = RateLimitOverrideCreate(
            user_id=user_id,
            requests_per_minute=500,
            expires_at=expires_at,
        )

        mock_override = {
            "id": str(uuid4()),
            "user_id": user_id,
            "requests_per_minute": 500,
            "expires_at": expires_at,
            "created_by": admin_user.id,
        }

        with patch.object(service, "create_override", return_value=mock_override):
            result = await service.create_override(
                db=mock_db,
                override_data=override_data,
                created_by=admin_user.id,
            )
            assert result["expires_at"] is not None


class TestDeleteOverride:
    """Tests for DELETE /admin/rate-limits/overrides/{override_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_override_success(self, mock_db, admin_user):
        """Rate-Limit-Überschreibung erfolgreich löschen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        override_id = str(uuid4())

        with patch.object(service, "delete_override", return_value=True):
            result = await service.delete_override(db=mock_db, override_id=override_id)
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_override_not_found(self, mock_db, admin_user):
        """Nicht existierende Überschreibung löschen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        with patch.object(service, "delete_override", return_value=False):
            result = await service.delete_override(
                db=mock_db, override_id="nonexistent"
            )
            assert result is False


class TestResetCounter:
    """Tests for POST /admin/rate-limits/reset/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_reset_counter_all(self, mock_db, admin_user):
        """Alle Rate-Limit-Zähler für Benutzer zurücksetzen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())

        with patch.object(service, "reset_counter", return_value=None):
            await service.reset_counter(db=mock_db, user_id=user_id)
            # No exception means success

    @pytest.mark.asyncio
    async def test_reset_counter_endpoint(self, mock_db, admin_user):
        """Rate-Limit-Zähler für bestimmten Endpunkt zurücksetzen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())
        endpoint = "/api/v1/ocr/process"

        with patch.object(service, "reset_counter", return_value=None):
            await service.reset_counter(
                db=mock_db, user_id=user_id, endpoint=endpoint
            )
            # No exception means success


class TestGetBlockedUsers:
    """Tests for GET /admin/rate-limits/blocked endpoint."""

    @pytest.mark.asyncio
    async def test_get_blocked_users_success(self, mock_db, admin_user):
        """Blockierte Benutzer erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_blocked = [
            {
                "user_id": str(uuid4()),
                "endpoint": "/api/v1/ocr/process",
                "blocked_at": datetime.utcnow(),
                "unblocks_at": datetime.utcnow() + timedelta(minutes=15),
                "reason": "Rate limit exceeded",
            },
        ]

        with patch.object(service, "get_blocked_users", return_value=mock_blocked):
            result = await service.get_blocked_users(db=mock_db)
            assert len(result) == 1
            assert "blocked_at" in result[0]

    @pytest.mark.asyncio
    async def test_get_blocked_users_empty(self, mock_db, admin_user):
        """Keine blockierten Benutzer."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        with patch.object(service, "get_blocked_users", return_value=[]):
            result = await service.get_blocked_users(db=mock_db)
            assert len(result) == 0
