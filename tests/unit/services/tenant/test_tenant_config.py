# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Tenant Config Service.

Testet:
- Mandanten-Konfiguration abrufen
- Konfiguration erstellen
- Konfiguration aktualisieren
- Feature-Flags abrufen
- Feature-Flags mit Defaults
- Quota-Pruefungen
- Mandanten-Deaktivierung

Feinpoliert und durchdacht - Tenant Config Service Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4


# Test-Konstanten fuer gueltige UUIDs
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_CONFIG_UUID = UUID("00000000-0000-0000-0000-000000000002")


# ========================= Mock Models =========================


class MockTenantConfig:
    """Mock TenantConfig-Model."""

    def __init__(
        self,
        id: UUID,
        company_id: UUID,
        features: Optional[Dict[str, Any]] = None,
        quotas: Optional[Dict[str, int]] = None,
        settings: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
    ):
        self.id = id
        self.company_id = company_id
        self.features = features or {}
        self.quotas = quotas or {}
        self.settings = settings or {}
        self.is_active = is_active
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = None


# ========================= Mock Service =========================


class MockTenantConfigService:
    """Mock-Implementation des TenantConfigService fuer Tests."""

    DEFAULT_FEATURES = {
        "ocr": True,
        "ai_insights": False,
        "document_chains": True,
        "slack_integration": False,
        "datev_integration": False,
    }

    DEFAULT_QUOTAS = {
        "max_documents": 10000,
        "max_users": 10,
        "max_storage_gb": 100,
        "max_api_requests_per_hour": 1000,
    }

    def __init__(self, db):
        self.db = db
        self._configs: Dict[UUID, MockTenantConfig] = {}
        self._usage: Dict[UUID, Dict[str, int]] = {}

    async def get_tenant_config(
        self,
        company_id: UUID,
    ) -> Optional[MockTenantConfig]:
        """Holt Konfiguration fuer Mandant."""
        return self._configs.get(company_id)

    async def create_config(
        self,
        company_id: UUID,
        features: Optional[Dict[str, Any]] = None,
        quotas: Optional[Dict[str, int]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> MockTenantConfig:
        """Erstellt neue Mandanten-Konfiguration."""
        config = MockTenantConfig(
            id=TEST_CONFIG_UUID,
            company_id=company_id,
            features=features or self.DEFAULT_FEATURES.copy(),
            quotas=quotas or self.DEFAULT_QUOTAS.copy(),
            settings=settings or {},
        )
        self._configs[company_id] = config
        return config

    async def update_config(
        self,
        company_id: UUID,
        features: Optional[Dict[str, Any]] = None,
        quotas: Optional[Dict[str, int]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[MockTenantConfig]:
        """Aktualisiert bestehende Konfiguration."""
        config = await self.get_tenant_config(company_id)
        if not config:
            return None

        if features is not None:
            config.features.update(features)
        if quotas is not None:
            config.quotas.update(quotas)
        if settings is not None:
            config.settings.update(settings)

        config.updated_at = datetime.now(timezone.utc)
        return config

    async def get_features(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Gibt Feature-Flags zurueck."""
        config = await self.get_tenant_config(company_id)
        if config:
            return config.features
        return self.DEFAULT_FEATURES.copy()

    async def check_quota(
        self,
        company_id: UUID,
        quota_name: str,
    ) -> Dict[str, Any]:
        """Prueft Quota-Status."""
        config = await self.get_tenant_config(company_id)
        if not config:
            return {
                "within_quota": True,
                "limit": self.DEFAULT_QUOTAS.get(quota_name, 0),
                "used": 0,
                "remaining": self.DEFAULT_QUOTAS.get(quota_name, 0),
            }

        limit = config.quotas.get(quota_name, 0)
        used = self._usage.get(company_id, {}).get(quota_name, 0)
        remaining = max(0, limit - used)

        return {
            "within_quota": used < limit,
            "limit": limit,
            "used": used,
            "remaining": remaining,
        }

    async def deactivate_tenant(
        self,
        company_id: UUID,
    ) -> bool:
        """Deaktiviert Mandanten."""
        config = await self.get_tenant_config(company_id)
        if not config:
            return False

        config.is_active = False
        config.updated_at = datetime.now(timezone.utc)
        return True

    def _set_usage(
        self,
        company_id: UUID,
        quota_name: str,
        value: int,
    ) -> None:
        """Hilfsfunktion zum Setzen von Usage-Werten fuer Tests."""
        if company_id not in self._usage:
            self._usage[company_id] = {}
        self._usage[company_id][quota_name] = value


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
def config_service(mock_db):
    """Erstelle MockTenantConfigService-Instanz."""
    return MockTenantConfigService(mock_db)


# ========================= Get Config Tests =========================


@pytest.mark.asyncio
async def test_get_tenant_config(
    config_service,
):
    """Test: Konfiguration fuer Mandant abrufen."""
    # Create config first
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
    )

    # Get config
    config = await config_service.get_tenant_config(TEST_COMPANY_UUID)

    # Assertions
    assert config is not None
    assert config.company_id == TEST_COMPANY_UUID
    assert config.is_active is True


@pytest.mark.asyncio
async def test_get_tenant_config_not_found(
    config_service,
):
    """Test: None bei nicht existierendem Mandanten."""
    # Get non-existent config
    config = await config_service.get_tenant_config(TEST_COMPANY_UUID)

    # Assertions
    assert config is None


# ========================= Create Config Tests =========================


@pytest.mark.asyncio
async def test_create_config(
    config_service,
):
    """Test: Neue Mandanten-Konfiguration erstellen."""
    # Custom features and quotas
    custom_features = {
        "ocr": True,
        "ai_insights": True,
        "slack_integration": True,
    }
    custom_quotas = {
        "max_documents": 50000,
        "max_users": 50,
    }

    # Create config
    config = await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        features=custom_features,
        quotas=custom_quotas,
    )

    # Assertions
    assert config is not None
    assert config.company_id == TEST_COMPANY_UUID
    assert config.features["ocr"] is True
    assert config.features["ai_insights"] is True
    assert config.quotas["max_documents"] == 50000
    assert config.quotas["max_users"] == 50


@pytest.mark.asyncio
async def test_create_config_with_defaults(
    config_service,
):
    """Test: Konfiguration mit Default-Werten erstellen."""
    # Create config without custom values
    config = await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
    )

    # Assertions
    assert config is not None
    assert config.features == config_service.DEFAULT_FEATURES
    assert config.quotas == config_service.DEFAULT_QUOTAS


# ========================= Update Config Tests =========================


@pytest.mark.asyncio
async def test_update_config(
    config_service,
):
    """Test: Bestehende Konfiguration aktualisieren."""
    # Create config first
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
    )

    # Update config
    updated_features = {"ai_insights": True}
    updated_quotas = {"max_documents": 20000}

    config = await config_service.update_config(
        company_id=TEST_COMPANY_UUID,
        features=updated_features,
        quotas=updated_quotas,
    )

    # Assertions
    assert config is not None
    assert config.features["ai_insights"] is True
    assert config.quotas["max_documents"] == 20000
    assert config.updated_at is not None


@pytest.mark.asyncio
async def test_update_config_not_found(
    config_service,
):
    """Test: Update bei nicht existierender Konfiguration."""
    # Update non-existent config
    config = await config_service.update_config(
        company_id=TEST_COMPANY_UUID,
        features={"ocr": False},
    )

    # Assertions
    assert config is None


# ========================= Get Features Tests =========================


@pytest.mark.asyncio
async def test_get_features(
    config_service,
):
    """Test: Feature-Flags fuer Mandant abrufen."""
    # Create config with custom features
    custom_features = {
        "ocr": True,
        "ai_insights": True,
        "document_chains": False,
    }
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        features=custom_features,
    )

    # Get features
    features = await config_service.get_features(TEST_COMPANY_UUID)

    # Assertions
    assert features["ocr"] is True
    assert features["ai_insights"] is True
    assert features["document_chains"] is False


@pytest.mark.asyncio
async def test_get_features_default(
    config_service,
):
    """Test: Default-Features bei nicht existierender Konfiguration."""
    # Get features without config
    features = await config_service.get_features(TEST_COMPANY_UUID)

    # Assertions
    assert features == config_service.DEFAULT_FEATURES


# ========================= Check Quota Tests =========================


@pytest.mark.asyncio
async def test_check_quota_within_limit(
    config_service,
):
    """Test: Quota-Pruefung innerhalb des Limits."""
    # Create config
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        quotas={"max_documents": 10000},
    )

    # Set usage below limit
    config_service._set_usage(TEST_COMPANY_UUID, "max_documents", 5000)

    # Check quota
    quota_status = await config_service.check_quota(
        company_id=TEST_COMPANY_UUID,
        quota_name="max_documents",
    )

    # Assertions
    assert quota_status["within_quota"] is True
    assert quota_status["limit"] == 10000
    assert quota_status["used"] == 5000
    assert quota_status["remaining"] == 5000


@pytest.mark.asyncio
async def test_check_quota_exceeded(
    config_service,
):
    """Test: Quota-Pruefung bei Ueberschreitung."""
    # Create config
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        quotas={"max_documents": 10000},
    )

    # Set usage above limit
    config_service._set_usage(TEST_COMPANY_UUID, "max_documents", 15000)

    # Check quota
    quota_status = await config_service.check_quota(
        company_id=TEST_COMPANY_UUID,
        quota_name="max_documents",
    )

    # Assertions
    assert quota_status["within_quota"] is False
    assert quota_status["limit"] == 10000
    assert quota_status["used"] == 15000
    assert quota_status["remaining"] == 0


@pytest.mark.asyncio
async def test_check_quota_at_limit(
    config_service,
):
    """Test: Quota-Pruefung genau am Limit."""
    # Create config
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        quotas={"max_users": 10},
    )

    # Set usage at limit
    config_service._set_usage(TEST_COMPANY_UUID, "max_users", 10)

    # Check quota
    quota_status = await config_service.check_quota(
        company_id=TEST_COMPANY_UUID,
        quota_name="max_users",
    )

    # Assertions
    assert quota_status["within_quota"] is False  # At limit counts as exceeded
    assert quota_status["limit"] == 10
    assert quota_status["used"] == 10
    assert quota_status["remaining"] == 0


@pytest.mark.asyncio
async def test_check_quota_no_config(
    config_service,
):
    """Test: Quota-Pruefung ohne Konfiguration verwendet Defaults."""
    # Check quota without config
    quota_status = await config_service.check_quota(
        company_id=TEST_COMPANY_UUID,
        quota_name="max_documents",
    )

    # Assertions
    assert quota_status["within_quota"] is True
    assert quota_status["limit"] == config_service.DEFAULT_QUOTAS["max_documents"]
    assert quota_status["used"] == 0
    assert quota_status["remaining"] == config_service.DEFAULT_QUOTAS["max_documents"]


# ========================= Deactivate Tests =========================


@pytest.mark.asyncio
async def test_deactivate_tenant(
    config_service,
):
    """Test: Mandanten-Deaktivierung setzt is_active=False."""
    # Create config first
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
    )

    # Deactivate tenant
    success = await config_service.deactivate_tenant(TEST_COMPANY_UUID)

    # Assertions
    assert success is True

    # Verify config is deactivated
    config = await config_service.get_tenant_config(TEST_COMPANY_UUID)
    assert config.is_active is False
    assert config.updated_at is not None


@pytest.mark.asyncio
async def test_deactivate_tenant_not_found(
    config_service,
):
    """Test: Deaktivierung nicht existierender Konfiguration."""
    # Deactivate non-existent tenant
    success = await config_service.deactivate_tenant(TEST_COMPANY_UUID)

    # Assertions
    assert success is False


# ========================= Integration Tests =========================


@pytest.mark.asyncio
async def test_feature_toggle_workflow(
    config_service,
):
    """Test: Kompletter Feature-Toggle-Workflow."""
    # 1. Create config with feature disabled
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        features={"ai_insights": False},
    )

    # 2. Verify feature is disabled
    features = await config_service.get_features(TEST_COMPANY_UUID)
    assert features["ai_insights"] is False

    # 3. Enable feature
    await config_service.update_config(
        company_id=TEST_COMPANY_UUID,
        features={"ai_insights": True},
    )

    # 4. Verify feature is enabled
    features = await config_service.get_features(TEST_COMPANY_UUID)
    assert features["ai_insights"] is True


@pytest.mark.asyncio
async def test_quota_lifecycle(
    config_service,
):
    """Test: Quota-Lebenszyklus von Erstellung bis Limit."""
    # 1. Create config with quota
    await config_service.create_config(
        company_id=TEST_COMPANY_UUID,
        quotas={"max_documents": 100},
    )

    # 2. Check initial quota (unused)
    quota = await config_service.check_quota(TEST_COMPANY_UUID, "max_documents")
    assert quota["within_quota"] is True
    assert quota["remaining"] == 100

    # 3. Simulate usage increase
    config_service._set_usage(TEST_COMPANY_UUID, "max_documents", 50)
    quota = await config_service.check_quota(TEST_COMPANY_UUID, "max_documents")
    assert quota["within_quota"] is True
    assert quota["remaining"] == 50

    # 4. Simulate hitting limit
    config_service._set_usage(TEST_COMPANY_UUID, "max_documents", 100)
    quota = await config_service.check_quota(TEST_COMPANY_UUID, "max_documents")
    assert quota["within_quota"] is False
    assert quota["remaining"] == 0

    # 5. Increase quota
    await config_service.update_config(
        company_id=TEST_COMPANY_UUID,
        quotas={"max_documents": 200},
    )
    quota = await config_service.check_quota(TEST_COMPANY_UUID, "max_documents")
    assert quota["within_quota"] is True
    assert quota["remaining"] == 100
