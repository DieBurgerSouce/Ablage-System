"""
Tests fuer Tenant Rate Limits API Endpoints.

Testet Multi-Tenant Rate Limiting Konfiguration und Metriken.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status


class TestTenantRateLimitsAPI:
    """Tests fuer Tenant Rate Limits API."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user (non-admin)."""
        user = MagicMock()
        user.id = uuid4()
        # B1: User-Modell hat keine company-Spalte; Rolle ist is_superuser.
        # Explizit False setzen, sonst liefert MagicMock ein truthy Attribut
        # und die 403-Admin-Guards feuern nicht.
        user.is_superuser = False
        # B1: company_id wird ueber get_user_company_id() (UserCompany) aufgeloest,
        # nicht ueber ein User-Attribut. Wert nur als Referenz fuer Permission-Tests.
        user.company_id = uuid4()
        return user

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.is_superuser = True
        user.company_id = uuid4()
        return user

    @pytest.fixture
    def mock_rate_limit_service(self):
        """Mock TenantRateLimitService."""
        service = AsyncMock()
        service.get_company_limits.return_value = {
            "company_id": str(uuid4()),
            "company_name": "Test Company",
            "subscription_tier": "professional",
            "subscription_expires_at": None,
            "tier_defaults": {
                "requests_per_minute": 100,
                "requests_per_hour": 2000,
                "requests_per_day": 20000,
                "ocr_requests_per_hour": 200,
                "batch_requests_per_hour": 50,
                "burst_limit": 20,
                "max_users": 10,
                "max_documents_per_month": 5000,
                "max_storage_gb": 50,
                "features": ["fraud_detection", "holding_view"],
            },
            "custom_limits": [],
            "max_users": 10,
            "max_documents_per_month": 5000,
            "max_storage_gb": 50,
            "features_enabled": ["fraud_detection"],
        }
        service.get_usage_summary.return_value = {
            "company_id": str(uuid4()),
            "period_type": "daily",
            "data_points": 30,
            "total_requests": 15000,
            "rate_limited_requests": 50,
            "rate_limit_percentage": 0.33,
            "avg_response_time_ms": 120.5,
            "documents_processed": 500,
            "pages_processed": 2500,
            "storage_used_bytes": 1073741824,
            "active_users": 5,
            "timeline": [],
        }
        service.get_violation_history.return_value = []
        service.check_rate_limit.return_value = {
            "allowed": True,
            "remaining": 95,
            "limit": 100,
            "reset_at": datetime.now(timezone.utc).isoformat(),
            "limit_type": "requests_per_minute",
            "retry_after": None,
        }
        return service

    # ==================== Get Own Limits Tests ====================

    @pytest.mark.asyncio
    async def test_get_own_limits_success(
        self,
        mock_user: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """Eigene Rate Limits abrufen."""
        from app.api.v1.tenant_rate_limits import get_own_limits

        # B1: company_id wird ueber get_user_company_id() (UserCompany-Tabelle)
        # aufgeloest, nicht ueber ein User-Attribut. Im Unit-Test mocken.
        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ), patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=mock_user.company_id),
        ):
            result = await get_own_limits(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["subscription_tier"] == "professional"
        assert result["tier_defaults"]["requests_per_minute"] == 100

    @pytest.mark.asyncio
    async def test_get_own_limits_no_company(self) -> None:
        """Fehler wenn User keine Company hat."""
        from app.api.v1.tenant_rate_limits import get_own_limits
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.is_superuser = False

        # B1: Keine Firmenzuordnung -> get_user_company_id() liefert None.
        with patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_own_limits(
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 400
        assert "Keine Company" in exc_info.value.detail

    # ==================== Get Company Limits Tests (Admin) ====================

    @pytest.mark.asyncio
    async def test_get_company_limits_as_admin(
        self,
        mock_admin: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """Admin kann fremde Company-Limits abrufen."""
        from app.api.v1.tenant_rate_limits import get_company_limits

        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ):
            result = await get_company_limits(
                company_id=company_id,
                current_user=mock_admin,
                db=AsyncMock(),
            )

        assert result["subscription_tier"] == "professional"
        mock_rate_limit_service.get_company_limits.assert_called_once_with(company_id)

    @pytest.mark.asyncio
    async def test_get_company_limits_non_admin_forbidden(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Nicht-Admin darf keine fremden Limits abrufen."""
        from app.api.v1.tenant_rate_limits import get_company_limits
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_company_limits(
                company_id=uuid4(),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 403
        assert "Administratoren" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_company_limits_not_found(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Fehler bei nicht gefundener Company."""
        from app.api.v1.tenant_rate_limits import get_company_limits
        from fastapi import HTTPException

        mock_service = AsyncMock()
        mock_service.get_company_limits.side_effect = ValueError("Company nicht gefunden")

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_company_limits(
                    company_id=uuid4(),
                    current_user=mock_admin,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 404

    # ==================== Update Limit Tests (Admin) ====================

    @pytest.mark.asyncio
    async def test_update_company_limit_as_admin(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Admin kann Custom Limit erstellen."""
        from app.api.v1.tenant_rate_limits import update_company_limit, UpdateLimitRequest

        mock_service = AsyncMock()
        mock_limit = MagicMock()
        mock_limit.id = uuid4()
        mock_limit.endpoint_pattern = "/api/v1/documents/*"
        mock_limit.requests_per_minute = 200
        mock_limit.requests_per_hour = 4000
        mock_limit.requests_per_day = 40000
        mock_limit.burst_limit = 30
        mock_limit.is_custom = True
        mock_service.update_company_limit.return_value = mock_limit

        mock_db = AsyncMock()

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_service,
        ):
            result = await update_company_limit(
                company_id=uuid4(),
                request=UpdateLimitRequest(
                    endpoint_pattern="/api/v1/documents/*",
                    requests_per_minute=200,
                ),
                current_user=mock_admin,
                db=mock_db,
            )

        assert result.requests_per_minute == 200
        assert result.is_custom is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_limit_non_admin_forbidden(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Nicht-Admin darf keine Limits aendern."""
        from app.api.v1.tenant_rate_limits import update_company_limit, UpdateLimitRequest
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_company_limit(
                company_id=uuid4(),
                request=UpdateLimitRequest(
                    endpoint_pattern="/api/v1/documents/*",
                    requests_per_minute=200,
                ),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 403

    # ==================== Reset Limits Tests (Admin) ====================

    @pytest.mark.asyncio
    async def test_reset_company_limits_as_admin(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Admin kann Custom Limits zuruecksetzen."""
        from app.api.v1.tenant_rate_limits import reset_company_limits

        mock_service = AsyncMock()
        mock_service.reset_to_tier_defaults.return_value = 3  # 3 Limits geloescht

        mock_db = AsyncMock()
        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_service,
        ):
            result = await reset_company_limits(
                company_id=company_id,
                current_user=mock_admin,
                db=mock_db,
            )

        assert "3 Custom-Limits gelöscht" in result["message"]
        assert result["company_id"] == str(company_id)
        mock_db.commit.assert_called_once()

    # ==================== Usage Metrics Tests ====================

    @pytest.mark.asyncio
    async def test_get_usage_metrics_own_company(
        self,
        mock_user: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """User kann eigene Usage-Metriken abrufen."""
        from app.api.v1.tenant_rate_limits import get_usage_metrics

        # Company IDs muessen uebereinstimmen (eigene Company)
        company_id = mock_user.company_id

        # B1: Permission-Check vergleicht get_user_company_id() == company_id.
        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ), patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=company_id),
        ):
            result = await get_usage_metrics(
                company_id=company_id,
                period_type="daily",
                days_back=30,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["period_type"] == "daily"
        assert result["total_requests"] == 15000

    @pytest.mark.asyncio
    async def test_get_usage_metrics_foreign_company_forbidden(
        self,
        mock_user: MagicMock,
    ) -> None:
        """User darf keine fremden Metriken abrufen."""
        from app.api.v1.tenant_rate_limits import get_usage_metrics
        from fastapi import HTTPException

        # Andere Company ID als die eigene des Users
        foreign_company_id = uuid4()

        # B1: Permission-Check vergleicht get_user_company_id() != company_id.
        # Eigene Company (!= foreign) liefern, damit der 403-Pfad greift.
        with patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=mock_user.company_id),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_usage_metrics(
                    company_id=foreign_company_id,
                    period_type="daily",
                    days_back=30,
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_usage_metrics_admin_any_company(
        self,
        mock_admin: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """Admin kann Metriken jeder Company abrufen."""
        from app.api.v1.tenant_rate_limits import get_usage_metrics

        foreign_company_id = uuid4()

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ):
            result = await get_usage_metrics(
                company_id=foreign_company_id,
                period_type="monthly",
                days_back=90,
                current_user=mock_admin,
                db=AsyncMock(),
            )

        assert result is not None

    # ==================== Violations Tests ====================

    @pytest.mark.asyncio
    async def test_get_violations(
        self,
        mock_admin: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """Violations abrufen."""
        from app.api.v1.tenant_rate_limits import get_violations

        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ):
            result = await get_violations(
                company_id=company_id,
                hours_back=24,
                limit=100,
                current_user=mock_admin,
                db=AsyncMock(),
            )

        assert isinstance(result, list)
        mock_rate_limit_service.get_violation_history.assert_called_once()

    # ==================== Check Rate Limit Tests ====================

    @pytest.mark.asyncio
    async def test_check_rate_limit(
        self,
        mock_user: MagicMock,
        mock_rate_limit_service: AsyncMock,
    ) -> None:
        """Rate Limit Check."""
        from app.api.v1.tenant_rate_limits import check_rate_limit

        # B1: company_id wird ueber get_user_company_id() aufgeloest.
        with patch(
            "app.api.v1.tenant_rate_limits.TenantRateLimitService",
            return_value=mock_rate_limit_service,
        ), patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=mock_user.company_id),
        ):
            result = await check_rate_limit(
                endpoint="/api/v1/documents",
                method="GET",
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["allowed"] is True
        assert result["remaining"] == 95
        assert result["limit"] == 100

    @pytest.mark.asyncio
    async def test_check_rate_limit_no_company(self) -> None:
        """Fehler wenn User keine Company hat."""
        from app.api.v1.tenant_rate_limits import check_rate_limit
        from fastapi import HTTPException

        mock_user = MagicMock()
        mock_user.is_superuser = False

        # B1: Keine Firmenzuordnung -> get_user_company_id() liefert None.
        with patch(
            "app.api.v1.tenant_rate_limits.get_user_company_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(
                    endpoint="/api/v1/documents",
                    method="GET",
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 400


class TestSubscriptionsAPI:
    """Tests fuer Subscriptions API."""

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.is_superuser = True
        user.company_id = uuid4()
        return user

    @pytest.fixture
    def mock_company(self):
        """Mock Company."""
        company = MagicMock()
        company.id = uuid4()
        company.name = "Test Company"
        company.subscription_tier = "professional"
        company.subscription_started_at = datetime.now(timezone.utc)
        company.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)
        company.billing_email = "billing@test.com"
        company.billing_address = {"street": "Test St 1", "city": "Berlin", "postal_code": "10115"}
        company.payment_method = "invoice"
        company.max_users = 10
        company.max_documents_per_month = 5000
        company.max_storage_gb = 50
        company.features_enabled = ["fraud_detection"]
        return company

    @pytest.mark.asyncio
    async def test_get_own_subscription(
        self,
        mock_company: MagicMock,
    ) -> None:
        """Eigene Subscription abrufen."""
        from app.api.v1.subscriptions import get_own_subscription

        mock_user = MagicMock()
        mock_user.current_company_id = mock_company.id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_db.execute.return_value = mock_result

        result = await get_own_subscription(
            current_user=mock_user,
            db=mock_db,
        )

        assert result.subscription_tier == "professional"
        assert result.is_expired is False

    @pytest.mark.asyncio
    async def test_get_available_tiers(self) -> None:
        """Verfuegbare Tiers abrufen."""
        from app.api.v1.subscriptions import get_available_tiers

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_available_tiers(db=mock_db)

        assert len(result) >= 4  # free, basic, professional, enterprise
        tier_names = [t.tier for t in result]
        assert "free" in tier_names
        assert "enterprise" in tier_names

    @pytest.mark.asyncio
    async def test_get_subscription_statistics_admin_only(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Nur Admins koennen Statistiken sehen."""
        from app.api.v1.subscriptions import get_subscription_statistics

        mock_db = AsyncMock()
        # Mock all count queries
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute.return_value = mock_result

        result = await get_subscription_statistics(
            current_user=mock_admin,
            db=mock_db,
        )

        assert result.total_companies == 10

    @pytest.mark.asyncio
    async def test_get_subscription_statistics_non_admin_forbidden(self) -> None:
        """Nicht-Admin bekommt 403."""
        from app.api.v1.subscriptions import get_subscription_statistics
        from fastapi import HTTPException

        mock_user = MagicMock()
        # B1: Admin-Rolle ist is_superuser, nicht is_admin. Explizit False,
        # sonst liefert MagicMock truthy und der 403-Guard feuert nicht.
        mock_user.is_superuser = False

        with pytest.raises(HTTPException) as exc_info:
            await get_subscription_statistics(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_change_subscription_tier(
        self,
        mock_admin: MagicMock,
        mock_company: MagicMock,
    ) -> None:
        """Subscription Tier aendern."""
        from app.api.v1.subscriptions import change_subscription_tier, ChangeTierRequest

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_db.execute.return_value = mock_result

        result = await change_subscription_tier(
            company_id=mock_company.id,
            request=ChangeTierRequest(new_tier="enterprise"),
            current_user=mock_admin,
            db=mock_db,
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_subscription(
        self,
        mock_admin: MagicMock,
        mock_company: MagicMock,
    ) -> None:
        """Subscription verlaengern."""
        from app.api.v1.subscriptions import extend_subscription, ExtendSubscriptionRequest

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_db.execute.return_value = mock_result

        result = await extend_subscription(
            company_id=mock_company.id,
            request=ExtendSubscriptionRequest(months=12),
            current_user=mock_admin,
            db=mock_db,
        )

        assert result is not None
        mock_db.commit.assert_called_once()
