"""Tests for ERP Base Connector.

Testet die abstrakte Basisklasse und gemeinsame Funktionalitaet
fuer alle ERP-Connectoren.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.datetime_utils import utc_now

from app.services.erp.base_connector import (
    ERPConnector,
    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
    ERPConflict,
)


# =============================================================================
# Test Fixtures
# =============================================================================


class ConcreteERPConnector(ERPConnector):
    """Concrete implementation for testing abstract base class."""

    async def connect(self) -> bool:
        self._status = ERPConnectionStatus.CONNECTED
        return True

    async def disconnect(self) -> None:
        self._status = ERPConnectionStatus.DISCONNECTED

    async def test_connection(self) -> bool:
        return self._status == ERPConnectionStatus.CONNECTED

    async def get_version(self) -> str:
        return "1.0.0"

    async def sync_customers(
        self, direction=ERPSyncDirection.PULL, since=None, batch_size=None
    ) -> ERPSyncResult:
        return self._create_sync_result(ERPEntity.CUSTOMER, direction)

    async def get_customer(self, erp_id: str):
        return {"id": erp_id, "name": "Test Customer"}

    async def create_customer(self, data):
        return "123"

    async def update_customer(self, erp_id: str, data):
        return True

    async def sync_suppliers(
        self, direction=ERPSyncDirection.PULL, since=None, batch_size=None
    ) -> ERPSyncResult:
        return self._create_sync_result(ERPEntity.SUPPLIER, direction)

    async def get_supplier(self, erp_id: str):
        return {"id": erp_id, "name": "Test Supplier"}

    async def create_supplier(self, data):
        return "456"

    async def update_supplier(self, erp_id: str, data):
        return True

    async def sync_invoices(
        self, direction=ERPSyncDirection.PULL, since=None, batch_size=None
    ) -> ERPSyncResult:
        return self._create_sync_result(ERPEntity.INVOICE, direction)

    async def get_invoice(self, erp_id: str):
        return {"id": erp_id, "number": "INV-001"}

    async def update_payment_status(self, erp_id, status, payment_date=None, amount=None):
        return True

    async def attach_document(self, entity, erp_id, document_data, filename, mime_type):
        return True

    async def get_attachments(self, entity, erp_id):
        return []


@pytest.fixture
def erp_config():
    """Create a test ERP configuration."""
    return ERPConnectionConfig(
        id=uuid4(),
        company_id=uuid4(),
        erp_type="test",
        name="Test ERP",
        url="https://erp.example.com",
        database="testdb",
        username="testuser",
        api_key="testkey",
        sync_direction=ERPSyncDirection.BIDIRECTIONAL,
        sync_interval_minutes=15,
        enabled_entities=[ERPEntity.CUSTOMER, ERPEntity.INVOICE],
        max_requests_per_minute=60,
        batch_size=100,
    )


@pytest.fixture
def connector(erp_config):
    """Create a test connector instance."""
    return ConcreteERPConnector(erp_config)


# =============================================================================
# ERPConnectionConfig Tests
# =============================================================================


class TestERPConnectionConfig:
    """Tests for ERPConnectionConfig dataclass."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = ERPConnectionConfig()

        assert config.erp_type == "odoo"
        assert config.sync_direction == ERPSyncDirection.BIDIRECTIONAL
        assert config.sync_interval_minutes == 15
        assert config.max_requests_per_minute == 60
        assert config.batch_size == 100
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 5
        assert config.connect_timeout_seconds == 30
        assert config.read_timeout_seconds == 60
        assert config.is_active is True

    def test_custom_values(self, erp_config):
        """Test that custom values are set correctly."""
        assert erp_config.erp_type == "test"
        assert erp_config.name == "Test ERP"
        assert erp_config.url == "https://erp.example.com"
        assert erp_config.database == "testdb"
        assert erp_config.username == "testuser"
        assert erp_config.api_key == "testkey"

    def test_enabled_entities_default(self):
        """Test default enabled entities."""
        config = ERPConnectionConfig()

        assert ERPEntity.CUSTOMER in config.enabled_entities
        assert ERPEntity.SUPPLIER in config.enabled_entities
        assert ERPEntity.INVOICE in config.enabled_entities


# =============================================================================
# ERPSyncResult Tests
# =============================================================================


class TestERPSyncResult:
    """Tests for ERPSyncResult dataclass."""

    def test_creation(self):
        """Test ERPSyncResult creation."""
        result = ERPSyncResult(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            success=True,
            records_synced=10,
            records_created=5,
            records_updated=5,
        )

        assert result.entity == ERPEntity.CUSTOMER
        assert result.direction == ERPSyncDirection.PULL
        assert result.success is True
        assert result.records_synced == 10
        assert result.records_created == 5
        assert result.records_updated == 5

    def test_to_dict(self):
        """Test ERPSyncResult to_dict conversion."""
        now = datetime.utcnow()
        result = ERPSyncResult(
            entity=ERPEntity.INVOICE,
            direction=ERPSyncDirection.PUSH,
            success=False,
            error_message="Test error",
            started_at=now,
            completed_at=now,
        )

        result_dict = result.to_dict()

        assert result_dict["entity"] == "invoice"
        assert result_dict["direction"] == "push"
        assert result_dict["success"] is False
        assert result_dict["error_message"] == "Test error"
        assert result_dict["started_at"] == now.isoformat()

    def test_default_values(self):
        """Test ERPSyncResult default values."""
        result = ERPSyncResult(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            success=True,
        )

        assert result.records_synced == 0
        assert result.records_created == 0
        assert result.records_updated == 0
        assert result.records_deleted == 0
        assert result.records_failed == 0
        assert result.conflicts_detected == 0
        assert result.conflicts_resolved == 0


# =============================================================================
# ERPConflict Tests
# =============================================================================


class TestERPConflict:
    """Tests for ERPConflict dataclass."""

    def test_creation(self):
        """Test ERPConflict creation."""
        conflict = ERPConflict(
            id="conflict-1",
            entity=ERPEntity.CUSTOMER,
            local_id="local-123",
            remote_id="remote-456",
            local_data={"name": "Local Name"},
            remote_data={"name": "Remote Name"},
        )

        assert conflict.id == "conflict-1"
        assert conflict.entity == ERPEntity.CUSTOMER
        assert conflict.local_id == "local-123"
        assert conflict.remote_id == "remote-456"
        assert conflict.local_data == {"name": "Local Name"}
        assert conflict.remote_data == {"name": "Remote Name"}

    def test_to_dict(self):
        """Test ERPConflict to_dict conversion."""
        now = datetime.utcnow()
        conflict = ERPConflict(
            id="conflict-1",
            entity=ERPEntity.INVOICE,
            local_id="local-123",
            remote_id="remote-456",
            local_data={},
            remote_data={},
            detected_at=now,
            resolution="local_wins",
            resolved_at=now,
        )

        conflict_dict = conflict.to_dict()

        assert conflict_dict["id"] == "conflict-1"
        assert conflict_dict["entity"] == "invoice"
        assert conflict_dict["resolution"] == "local_wins"
        assert conflict_dict["detected_at"] == now.isoformat()


# =============================================================================
# ERPConnector Base Tests
# =============================================================================


class TestERPConnector:
    """Tests for ERPConnector abstract base class."""

    @pytest.mark.asyncio
    async def test_initial_status(self, connector):
        """Test initial connection status."""
        assert connector.status == ERPConnectionStatus.DISCONNECTED
        assert connector.last_error is None

    @pytest.mark.asyncio
    async def test_connect(self, connector):
        """Test connect method."""
        result = await connector.connect()

        assert result is True
        assert connector.status == ERPConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_disconnect(self, connector):
        """Test disconnect method."""
        await connector.connect()
        await connector.disconnect()

        assert connector.status == ERPConnectionStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_test_connection(self, connector):
        """Test test_connection method."""
        # Not connected
        assert await connector.test_connection() is False

        # Connected
        await connector.connect()
        assert await connector.test_connection() is True

    @pytest.mark.asyncio
    async def test_get_version(self, connector):
        """Test get_version method."""
        version = await connector.get_version()
        assert version == "1.0.0"

    @pytest.mark.asyncio
    async def test_sync_customers(self, connector):
        """Test sync_customers method."""
        result = await connector.sync_customers()

        assert isinstance(result, ERPSyncResult)
        assert result.entity == ERPEntity.CUSTOMER
        assert result.direction == ERPSyncDirection.PULL

    @pytest.mark.asyncio
    async def test_sync_suppliers(self, connector):
        """Test sync_suppliers method."""
        result = await connector.sync_suppliers(direction=ERPSyncDirection.PUSH)

        assert isinstance(result, ERPSyncResult)
        assert result.entity == ERPEntity.SUPPLIER
        assert result.direction == ERPSyncDirection.PUSH

    @pytest.mark.asyncio
    async def test_sync_invoices(self, connector):
        """Test sync_invoices method."""
        result = await connector.sync_invoices()

        assert isinstance(result, ERPSyncResult)
        assert result.entity == ERPEntity.INVOICE

    @pytest.mark.asyncio
    async def test_get_customer(self, connector):
        """Test get_customer method."""
        customer = await connector.get_customer("123")

        assert customer is not None
        assert customer["id"] == "123"
        assert customer["name"] == "Test Customer"

    @pytest.mark.asyncio
    async def test_create_customer(self, connector):
        """Test create_customer method."""
        customer_id = await connector.create_customer({"name": "New Customer"})

        assert customer_id == "123"

    @pytest.mark.asyncio
    async def test_update_customer(self, connector):
        """Test update_customer method."""
        result = await connector.update_customer("123", {"name": "Updated"})

        assert result is True

    @pytest.mark.asyncio
    async def test_attach_document(self, connector):
        """Test attach_document method."""
        result = await connector.attach_document(
            entity=ERPEntity.INVOICE,
            erp_id="123",
            document_data=b"test",
            filename="test.pdf",
            mime_type="application/pdf",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_get_attachments(self, connector):
        """Test get_attachments method."""
        attachments = await connector.get_attachments(
            entity=ERPEntity.INVOICE,
            erp_id="123",
        )

        assert isinstance(attachments, list)


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_check_allowed(self, connector):
        """Test rate limit check when allowed."""
        assert connector._check_rate_limit() is True
        assert connector._request_count == 1

    def test_rate_limit_check_blocked(self, connector):
        """Test rate limit check when blocked."""
        # Simulate max requests
        connector._request_count = connector.config.max_requests_per_minute
        connector._rate_limit_reset = utc_now() + timedelta(minutes=1)

        assert connector._check_rate_limit() is False
        assert connector.status == ERPConnectionStatus.RATE_LIMITED

    def test_rate_limit_reset(self, connector):
        """Test rate limit reset after timeout."""
        # Set request count
        connector._request_count = 50
        connector._rate_limit_reset = utc_now() - timedelta(seconds=1)

        # Should reset
        assert connector._check_rate_limit() is True
        assert connector._request_count == 1


# =============================================================================
# Conflict Detection Tests
# =============================================================================


class TestConflictDetection:
    """Tests for conflict detection."""

    @pytest.mark.asyncio
    async def test_detect_conflicts_no_conflicts(self, connector):
        """Test conflict detection with no conflicts."""
        connector.config.last_sync_at = datetime.utcnow() - timedelta(hours=1)

        local_records = [
            {"id": "1", "erp_id": "remote-1", "updated_at": datetime.utcnow() - timedelta(hours=2)}
        ]
        remote_records = [
            {"id": "remote-1", "write_date": (datetime.utcnow() - timedelta(hours=2)).isoformat()}
        ]

        conflicts = await connector.detect_conflicts(
            ERPEntity.CUSTOMER,
            local_records,
            remote_records,
        )

        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_detect_conflicts_with_conflict(self, connector):
        """Test conflict detection with actual conflict."""
        connector.config.last_sync_at = datetime.utcnow() - timedelta(hours=1)

        # Both modified after last sync
        now = datetime.utcnow()
        local_records = [
            {"id": "1", "erp_id": "remote-1", "updated_at": now}
        ]
        remote_records = [
            {"id": "remote-1", "write_date": now.isoformat()}
        ]

        conflicts = await connector.detect_conflicts(
            ERPEntity.CUSTOMER,
            local_records,
            remote_records,
        )

        assert len(conflicts) == 1
        assert conflicts[0].entity == ERPEntity.CUSTOMER
        assert conflicts[0].local_id == "1"
        assert conflicts[0].remote_id == "remote-1"

    @pytest.mark.asyncio
    async def test_resolve_conflict_local_wins(self, connector):
        """Test resolving conflict with local_wins."""
        conflict = ERPConflict(
            id="conflict-1",
            entity=ERPEntity.CUSTOMER,
            local_id="local-1",
            remote_id="remote-1",
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
        )

        result = await connector.resolve_conflict(conflict, "local_wins")

        assert result is True
        assert conflict.resolution == "local_wins"
        assert conflict.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resolve_conflict_invalid_resolution(self, connector):
        """Test resolving conflict with invalid resolution."""
        conflict = ERPConflict(
            id="conflict-1",
            entity=ERPEntity.CUSTOMER,
            local_id="local-1",
            remote_id="remote-1",
            local_data={},
            remote_data={},
        )

        result = await connector.resolve_conflict(conflict, "invalid")

        assert result is False


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for helper methods."""

    def test_create_sync_result(self, connector):
        """Test _create_sync_result helper."""
        result = connector._create_sync_result(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
        )

        assert isinstance(result, ERPSyncResult)
        assert result.entity == ERPEntity.CUSTOMER
        assert result.direction == ERPSyncDirection.PULL
        assert result.success is True
        assert result.started_at is not None
        assert result.sync_id is not None

    def test_create_sync_result_with_error(self, connector):
        """Test _create_sync_result helper with error."""
        result = connector._create_sync_result(
            entity=ERPEntity.INVOICE,
            direction=ERPSyncDirection.PUSH,
            success=False,
            error_message="Test error",
        )

        assert result.success is False
        assert result.error_message == "Test error"

    def test_complete_sync_result(self, connector):
        """Test _complete_sync_result helper."""
        result = connector._create_sync_result(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
        )

        completed = connector._complete_sync_result(result)

        assert completed.completed_at is not None
        assert completed.duration_seconds >= 0


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests for ERP enums."""

    def test_sync_direction_values(self):
        """Test ERPSyncDirection values."""
        assert ERPSyncDirection.PUSH.value == "push"
        assert ERPSyncDirection.PULL.value == "pull"
        assert ERPSyncDirection.BIDIRECTIONAL.value == "bidirectional"

    def test_connection_status_values(self):
        """Test ERPConnectionStatus values."""
        assert ERPConnectionStatus.CONNECTED.value == "connected"
        assert ERPConnectionStatus.DISCONNECTED.value == "disconnected"
        assert ERPConnectionStatus.ERROR.value == "error"
        assert ERPConnectionStatus.AUTHENTICATING.value == "authenticating"
        assert ERPConnectionStatus.RATE_LIMITED.value == "rate_limited"

    def test_entity_values(self):
        """Test ERPEntity values."""
        assert ERPEntity.CUSTOMER.value == "customer"
        assert ERPEntity.SUPPLIER.value == "supplier"
        assert ERPEntity.INVOICE.value == "invoice"
        assert ERPEntity.PAYMENT.value == "payment"
        assert ERPEntity.PRODUCT.value == "product"
        assert ERPEntity.DOCUMENT.value == "document"
        assert ERPEntity.ORDER.value == "order"
