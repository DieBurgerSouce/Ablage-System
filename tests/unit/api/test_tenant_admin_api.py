"""
Unit tests fuer Tenant Admin API.

Testet Admin-Endpunkte fuer Mandanten-Verwaltung.
"""

import pytest
from uuid import uuid4
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_tenant_config import TenantConfig
from app.db.models_user import User


@pytest.fixture
def mock_superuser() -> User:
    """Erstellt einen Mock Superuser."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "admin@example.com"
    user.is_superuser = True
    user.is_active = True
    return user


@pytest.fixture
def mock_tenant_config() -> TenantConfig:
    """Erstellt eine Mock TenantConfig."""
    config = MagicMock(spec=TenantConfig)
    config.id = uuid4()
    config.company_id = uuid4()
    config.features = {"ocr_enabled": True}
    config.quotas = {"documents_per_month": 10000}
    config.branding = {"logo_url": "https://example.com/logo.png"}
    config.is_active = True
    return config


class TestTenantAdminAPI:
    """Tests fuer Tenant Admin API."""

    @pytest.mark.asyncio
    async def test_get_tenant_config_success(
        self,
        mock_superuser: User,
        mock_tenant_config: TenantConfig,
    ) -> None:
        """Test: Erfolgreicher Abruf der Mandanten-Konfiguration."""
        company_id = mock_tenant_config.company_id

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.get_tenant_config.return_value = mock_tenant_config
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import get_tenant_config

            result = await get_tenant_config(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            assert result.company_id == company_id
            assert result.features == mock_tenant_config.features
            assert result.is_active is True

    @pytest.mark.asyncio
    async def test_get_tenant_config_not_found(
        self,
        mock_superuser: User,
    ) -> None:
        """Test: 404 wenn Konfiguration nicht gefunden."""
        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory, pytest.raises(Exception) as exc_info:
            # Mock Service - keine Konfiguration
            mock_service = AsyncMock()
            mock_service.get_tenant_config.return_value = None
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import get_tenant_config

            await get_tenant_config(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

        # Erwarte HTTPException mit 404
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_tenant_config_success(
        self,
        mock_superuser: User,
        mock_tenant_config: TenantConfig,
    ) -> None:
        """Test: Erfolgreiche Aktualisierung der Konfiguration."""
        company_id = mock_tenant_config.company_id

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.create_or_update_config.return_value = mock_tenant_config
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import (
                update_tenant_config,
                TenantConfigUpdate,
            )

            update = TenantConfigUpdate(
                features={"datev_integration": True},
            )

            result = await update_tenant_config(
                company_id=company_id,
                update=update,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            assert result.company_id == company_id
            mock_service.create_or_update_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_features_success(
        self,
        mock_superuser: User,
    ) -> None:
        """Test: Erfolgreicher Abruf der Feature-Flags."""
        company_id = uuid4()
        features = {"ocr_enabled": True, "datev_integration": False}

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.get_tenant_features.return_value = features
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import get_tenant_features

            result = await get_tenant_features(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            assert result.company_id == company_id
            assert result.features == features

    @pytest.mark.asyncio
    async def test_get_tenant_usage_success(
        self,
        mock_superuser: User,
        mock_tenant_config: TenantConfig,
    ) -> None:
        """Test: Erfolgreicher Abruf der Quota-Nutzung."""
        company_id = mock_tenant_config.company_id

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.get_tenant_config.return_value = mock_tenant_config
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import get_tenant_usage

            result = await get_tenant_usage(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            assert result.company_id == company_id
            assert result.quotas == mock_tenant_config.quotas
            assert "usage_summary" in result.model_dump()

    @pytest.mark.asyncio
    async def test_deactivate_tenant_success(
        self,
        mock_superuser: User,
    ) -> None:
        """Test: Erfolgreiche Deaktivierung eines Mandanten."""
        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.deactivate_tenant.return_value = True
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import deactivate_tenant

            await deactivate_tenant(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            mock_service.deactivate_tenant.assert_called_once_with(company_id)

    @pytest.mark.asyncio
    async def test_activate_tenant_success(
        self,
        mock_superuser: User,
    ) -> None:
        """Test: Erfolgreiche Aktivierung eines Mandanten."""
        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory:
            # Mock Service
            mock_service = AsyncMock()
            mock_service.activate_tenant.return_value = True
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import activate_tenant

            await activate_tenant(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

            mock_service.activate_tenant.assert_called_once_with(company_id)

    @pytest.mark.asyncio
    async def test_deactivate_tenant_failure(
        self,
        mock_superuser: User,
    ) -> None:
        """Test: Fehler bei Deaktivierung."""
        company_id = uuid4()

        with patch(
            "app.api.v1.tenant_admin.get_current_superuser",
            return_value=mock_superuser,
        ), patch(
            "app.api.v1.tenant_admin.get_tenant_config_service"
        ) as mock_service_factory, pytest.raises(Exception) as exc_info:
            # Mock Service - Fehler
            mock_service = AsyncMock()
            mock_service.deactivate_tenant.return_value = False
            mock_service_factory.return_value = mock_service

            # Test Request
            from app.api.v1.tenant_admin import deactivate_tenant

            await deactivate_tenant(
                company_id=company_id,
                db=AsyncMock(spec=AsyncSession),
                current_user=mock_superuser,
            )

        # Erwarte HTTPException mit 500
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
