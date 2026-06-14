"""
Unit tests fuer TenantConfigService.

Testet Feature-Flags, Quotas und Mandanten-Verwaltung.
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base
from app.db.models_tenant_config import TenantConfig
from app.services.tenant.tenant_config_service import TenantConfigService


@pytest_asyncio.fixture
async def async_db(test_db) -> AsyncGenerator[AsyncSession, None]:
    """Liefert die kanonische PostgreSQL-Async-Session aus conftest (``test_db``).

    Vorher nutzte diese Datei ``sqlite+aiosqlite:///:memory:`` - aiosqlite ist
    im Backend-Container nicht installiert (ModuleNotFoundError) und die Modelle
    nutzen ohnehin PostgreSQL-spezifische Typen (JSONB, UUID). ``test_db``
    ueberspringt sauber, wenn keine DB erreichbar ist (CI-only).
    """
    yield test_db


@pytest.fixture
def tenant_service(async_db: AsyncSession) -> TenantConfigService:
    """Erstellt eine TenantConfigService Instanz."""
    return TenantConfigService(async_db)


@pytest.fixture
def company_id() -> str:
    """Erstellt eine Test-Mandanten-ID."""
    return uuid4()


class TestTenantConfigService:
    """Tests fuer TenantConfigService."""

    @pytest.mark.asyncio
    async def test_get_tenant_config_not_found(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: get_tenant_config gibt None wenn nicht gefunden."""
        result = await tenant_service.get_tenant_config(company_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_tenant_config(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Erstellen einer neuen Mandanten-Konfiguration."""
        features = {"ocr_enabled": True, "max_users": 50}
        quotas = {"documents_per_month": 10000}
        branding = {"logo_url": "https://example.com/logo.png"}

        config = await tenant_service.create_or_update_config(
            company_id=company_id,
            features=features,
            quotas=quotas,
            branding=branding,
        )

        assert config is not None
        assert config.company_id == company_id
        assert config.features == features
        assert config.quotas == quotas
        assert config.branding == branding
        assert config.is_active is True

    @pytest.mark.asyncio
    async def test_update_tenant_config(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Aktualisieren einer bestehenden Konfiguration."""
        # Erstelle initiale Konfiguration
        initial_features = {"ocr_enabled": True}
        await tenant_service.create_or_update_config(
            company_id=company_id,
            features=initial_features,
        )

        # Aktualisiere Features
        updated_features = {"max_users": 100}
        config = await tenant_service.create_or_update_config(
            company_id=company_id,
            features=updated_features,
        )

        # Features sollten gemerged sein
        assert config.features is not None
        assert config.features["ocr_enabled"] is True
        assert config.features["max_users"] == 100

    @pytest.mark.asyncio
    async def test_get_tenant_features(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Abrufen von Feature-Flags."""
        features = {
            "ocr_enabled": True,
            "datev_integration": False,
            "max_users": 50,  # Kein boolean, sollte gefiltert werden
        }

        await tenant_service.create_or_update_config(
            company_id=company_id,
            features=features,
        )

        result = await tenant_service.get_tenant_features(company_id)

        # Nur boolean Features
        assert result == {
            "ocr_enabled": True,
            "datev_integration": False,
        }

    @pytest.mark.asyncio
    async def test_get_tenant_features_empty(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Leere Feature-Flags wenn keine Konfiguration."""
        result = await tenant_service.get_tenant_features(company_id)
        assert result == {}

    @pytest.mark.asyncio
    async def test_check_tenant_quota_within_limit(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Quota-Pruefung innerhalb des Limits."""
        quotas = {"documents_per_month": 10000}
        await tenant_service.create_or_update_config(
            company_id=company_id,
            quotas=quotas,
        )

        result = await tenant_service.check_tenant_quota(
            company_id=company_id,
            resource="documents_per_month",
            current_usage=5000,
        )

        assert result["within_quota"] is True
        assert result["limit"] == 10000
        assert result["usage"] == 5000
        assert result["remaining"] == 5000

    @pytest.mark.asyncio
    async def test_check_tenant_quota_exceeded(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Quota-Pruefung ueber dem Limit."""
        quotas = {"documents_per_month": 10000}
        await tenant_service.create_or_update_config(
            company_id=company_id,
            quotas=quotas,
        )

        result = await tenant_service.check_tenant_quota(
            company_id=company_id,
            resource="documents_per_month",
            current_usage=15000,
        )

        assert result["within_quota"] is False
        assert result["limit"] == 10000
        assert result["usage"] == 15000
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_check_tenant_quota_unlimited(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Quota-Pruefung ohne Limit."""
        # Keine Quotas definiert
        result = await tenant_service.check_tenant_quota(
            company_id=company_id,
            resource="documents_per_month",
            current_usage=999999,
        )

        assert result["within_quota"] is True
        assert result["limit"] == -1  # Unbegrenzt
        assert result["remaining"] == -1

    @pytest.mark.asyncio
    async def test_deactivate_tenant(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Deaktivieren eines Mandanten."""
        # Erstelle aktiven Mandanten
        await tenant_service.create_or_update_config(company_id=company_id)

        # Deaktiviere
        success = await tenant_service.deactivate_tenant(company_id)
        assert success is True

        # Pruefe Status
        config = await tenant_service.get_tenant_config(company_id)
        assert config is not None
        assert config.is_active is False

    @pytest.mark.asyncio
    async def test_activate_tenant(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Aktivieren eines Mandanten."""
        # Erstelle deaktivierten Mandanten
        await tenant_service.deactivate_tenant(company_id)

        # Aktiviere
        success = await tenant_service.activate_tenant(company_id)
        assert success is True

        # Pruefe Status
        config = await tenant_service.get_tenant_config(company_id)
        assert config is not None
        assert config.is_active is True

    @pytest.mark.asyncio
    async def test_quota_check_resource_not_limited(
        self,
        tenant_service: TenantConfigService,
        company_id: str,
    ) -> None:
        """Test: Quota-Pruefung fuer nicht limitierte Ressource."""
        quotas = {"documents_per_month": 10000}
        await tenant_service.create_or_update_config(
            company_id=company_id,
            quotas=quotas,
        )

        # Pruefe andere Ressource (nicht in quotas)
        result = await tenant_service.check_tenant_quota(
            company_id=company_id,
            resource="storage_gb",
            current_usage=1000,
        )

        assert result["within_quota"] is True
        assert result["limit"] == -1  # Nicht limitiert
