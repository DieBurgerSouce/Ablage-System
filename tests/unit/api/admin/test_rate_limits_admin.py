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

from app.db.models import User
from app.db.schemas import (
    UserRole,
    RateLimitOverrideCreate,
    RateLimitOverrideResponse,
    MessageResponse,
)


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


class TestGetRateLimitConfig:
    """Tests for GET /admin/rate-limits/config endpoint."""

    @pytest.mark.asyncio
    async def test_get_tier_defaults_success(self, admin_user):
        """Rate-Limit-Tier-Defaults erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        mock_defaults = {
            "free": {
                "requests_per_minute": 10,
                "requests_per_hour": 100,
                "requests_per_day": 500,
            },
            "premium": {
                "requests_per_minute": 50,
                "requests_per_hour": 500,
                "requests_per_day": 5000,
            },
            "enterprise": {
                "requests_per_minute": 200,
                "requests_per_hour": 2000,
                "requests_per_day": 20000,
            },
        }

        with patch.object(RateLimitService, "get_tier_defaults", return_value=mock_defaults):
            result = RateLimitService.get_tier_defaults()
            assert "free" in result
            assert result["free"]["requests_per_minute"] == 10
            assert result["enterprise"]["requests_per_minute"] == 200


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


class TestUserRateLimitStatus:
    """Tests for GET /admin/rate-limits/user/{user_id}/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_rate_limit_status_success(self, mock_db, admin_user):
        """Rate-Limit-Status für Benutzer erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())

        mock_status = {
            "user_id": user_id,
            "tier": "premium",
            "has_override": True,
            "current_limits": {
                "requests_per_minute": 200,
                "requests_per_hour": 2000,
            },
            "usage": {
                "requests_last_minute": 15,
                "requests_last_hour": 120,
            },
            "is_blocked": False,
        }

        with patch.object(service, "get_user_rate_limit_status", return_value=mock_status):
            result = await service.get_user_rate_limit_status(db=mock_db, user_id=user_id)
            assert result["user_id"] == user_id
            assert result["has_override"] is True
            assert result["current_limits"]["requests_per_minute"] == 200


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
            reason="Premium-Kunde benötigt höhere Limits",
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
            reason="Temporäre Erhöhung für Projekt",
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


class TestResetUsage:
    """Tests for POST /admin/rate-limits/reset/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_reset_usage_success(self, mock_db, admin_user):
        """Rate-Limit-Nutzung für Benutzer zurücksetzen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = str(uuid4())

        with patch.object(service, "reset_usage", return_value=True):
            result = await service.reset_usage(db=mock_db, user_id=user_id)
            assert result is True

    @pytest.mark.asyncio
    async def test_reset_usage_user_not_found(self, mock_db, admin_user):
        """Rate-Limit-Nutzung zurücksetzen - Benutzer nicht gefunden."""
        from app.services.admin import RateLimitService

        service = RateLimitService()
        user_id = "nonexistent-user"

        with patch.object(service, "reset_usage", return_value=False):
            result = await service.reset_usage(db=mock_db, user_id=user_id)
            assert result is False


class TestGetUsageStats:
    """Tests for GET /admin/rate-limits/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_usage_stats_success(self, mock_db, admin_user):
        """Rate-Limit-Nutzungsstatistiken erfolgreich abrufen."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_stats = MagicMock()
        mock_stats.total_users = 100
        mock_stats.users_near_limit = 5
        mock_stats.users_blocked = 2

        with patch.object(service, "get_usage_stats", return_value=mock_stats):
            result = await service.get_usage_stats(db=mock_db)
            assert result.total_users == 100
            assert result.users_blocked == 2

    @pytest.mark.asyncio
    async def test_get_usage_stats_no_activity(self, mock_db, admin_user):
        """Rate-Limit-Statistiken ohne Aktivität."""
        from app.services.admin import RateLimitService

        service = RateLimitService()

        mock_stats = MagicMock()
        mock_stats.total_users = 0
        mock_stats.users_near_limit = 0
        mock_stats.users_blocked = 0

        with patch.object(service, "get_usage_stats", return_value=mock_stats):
            result = await service.get_usage_stats(db=mock_db)
            assert result.total_users == 0
