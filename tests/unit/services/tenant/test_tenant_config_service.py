# -*- coding: utf-8 -*-
"""Unit tests for TenantConfigService."""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tenant.tenant_config_service import (
    TenantConfigService,
    get_tenant_config_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> TenantConfigService:
    return TenantConfigService(mock_db)


def _make_tenant_config(
    company_id: "uuid4" = None,
    is_active: bool = True,
    features: dict = None,
    quotas: dict = None,
    branding: dict = None,
) -> MagicMock:
    config = MagicMock()
    config.company_id = company_id or uuid4()
    config.is_active = is_active
    config.features = features or {}
    config.quotas = quotas or {}
    config.branding = branding or {}
    return config


# ---------------------------------------------------------------------------
# get_tenant_config
# ---------------------------------------------------------------------------


class TestGetTenantConfig:
    @pytest.mark.asyncio
    async def test_returns_config_when_found(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        company_id = uuid4()
        expected_config = _make_tenant_config(company_id=company_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_tenant_config(company_id)

        assert result is expected_config
        assert result.company_id == company_id
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_tenant_config(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_exception(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        """Database failure should be caught and return None."""
        mock_db.execute = AsyncMock(side_effect=Exception("Connection lost"))

        result = await service.get_tenant_config(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_active_config(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_tenant_config(uuid4())
        assert result.is_active is True


# ---------------------------------------------------------------------------
# create_or_update_config
# ---------------------------------------------------------------------------


class TestCreateOrUpdateConfig:
    @pytest.mark.asyncio
    async def test_creates_new_config_when_none_exists(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        """When no config exists, a new TenantConfig should be created."""
        company_id = uuid4()

        # get_tenant_config returns None (no existing config)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # We need to mock db.add, commit, refresh
        new_config = MagicMock()
        new_config.company_id = company_id
        new_config.features = {"ocr_enabled": True}

        mock_db.commit = AsyncMock()

        # patch TenantConfig constructor
        with patch(
            "app.services.tenant.tenant_config_service.TenantConfig"
        ) as MockTenantConfig:
            MockTenantConfig.return_value = new_config
            mock_db.refresh = AsyncMock()

            result = await service.create_or_update_config(
                company_id=company_id,
                features={"ocr_enabled": True},
            )

        mock_db.add.assert_called_once_with(new_config)
        mock_db.commit.assert_awaited_once()
        assert result is new_config

    @pytest.mark.asyncio
    async def test_updates_existing_config_features(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        """Existing config features should be merged (not replaced)."""
        company_id = uuid4()
        existing = _make_tenant_config(
            company_id=company_id,
            features={"ocr_enabled": True, "banking": False},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.create_or_update_config(
            company_id=company_id,
            features={"banking": True, "alerts": True},
        )

        # Features should be merged
        assert result.features == {
            "ocr_enabled": True,
            "banking": True,
            "alerts": True,
        }
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_config_quotas(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        company_id = uuid4()
        existing = _make_tenant_config(
            company_id=company_id,
            quotas={"documents_per_month": 1000},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service.create_or_update_config(
            company_id=company_id,
            quotas={"users": 50},
        )

        assert result.quotas == {
            "documents_per_month": 1000,
            "users": 50,
        }

    @pytest.mark.asyncio
    async def test_raises_value_error_on_db_failure(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        """DB commit failure should raise ValueError with message."""
        company_id = uuid4()

        # get_tenant_config succeeds (returns None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.tenant.tenant_config_service.TenantConfig"
        ) as MockTC:
            MockTC.return_value = MagicMock()
            mock_db.commit = AsyncMock(side_effect=Exception("constraint violation"))
            mock_db.rollback = AsyncMock()

            with pytest.raises(ValueError, match="Fehler beim Speichern"):
                await service.create_or_update_config(company_id=company_id)

            mock_db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_tenant_features
# ---------------------------------------------------------------------------


class TestGetTenantFeatures:
    @pytest.mark.asyncio
    async def test_returns_boolean_features(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(
            features={"ocr_enabled": True, "banking": False, "max_size": 100},
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_tenant_features(uuid4())

        # Only boolean features should be returned
        assert result == {"ocr_enabled": True, "banking": False}
        assert "max_size" not in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_config(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_tenant_features(uuid4())
        assert result == {}


# ---------------------------------------------------------------------------
# check_tenant_quota
# ---------------------------------------------------------------------------


class TestCheckTenantQuota:
    @pytest.mark.asyncio
    async def test_within_quota(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(quotas={"documents_per_month": 1000})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_tenant_quota(uuid4(), "documents_per_month", 500)

        assert result["within_quota"] is True
        assert result["limit"] == 1000
        assert result["usage"] == 500
        assert result["remaining"] == 500

    @pytest.mark.asyncio
    async def test_over_quota(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(quotas={"documents_per_month": 100})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_tenant_quota(uuid4(), "documents_per_month", 150)

        assert result["within_quota"] is False
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_no_config_returns_unlimited(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_tenant_quota(uuid4(), "documents_per_month", 500)

        assert result["within_quota"] is True
        assert result["limit"] == -1

    @pytest.mark.asyncio
    async def test_undefined_resource_returns_unlimited(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(quotas={"documents_per_month": 100})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_tenant_quota(uuid4(), "api_calls", 9999)

        assert result["within_quota"] is True
        assert result["limit"] == -1


# ---------------------------------------------------------------------------
# deactivate_tenant / activate_tenant
# ---------------------------------------------------------------------------


class TestTenantActivation:
    @pytest.mark.asyncio
    async def test_deactivate_existing_tenant(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        result = await service.deactivate_tenant(uuid4())

        assert result is True
        assert config.is_active is False

    @pytest.mark.asyncio
    async def test_activate_existing_tenant(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        config = _make_tenant_config(is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        result = await service.activate_tenant(uuid4())

        assert result is True
        assert config.is_active is True

    @pytest.mark.asyncio
    async def test_deactivate_returns_false_on_error(
        self, service: TenantConfigService, mock_db: AsyncMock
    ) -> None:
        mock_db.execute = AsyncMock(side_effect=Exception("DB error"))
        mock_db.rollback = AsyncMock()

        # get_tenant_config catches the exception and returns None,
        # then deactivate creates a new config but commit fails
        # Actually, the first execute will raise, get_tenant_config catches it
        # and returns None. Then it tries to create + commit.
        # Let's make commit also fail:
        mock_db.commit = AsyncMock(side_effect=Exception("DB error"))

        result = await service.deactivate_tenant(uuid4())

        assert result is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_tenant_config_service(self) -> None:
        mock_db = AsyncMock()
        svc = get_tenant_config_service(mock_db)
        assert isinstance(svc, TenantConfigService)
        assert svc.db is mock_db
