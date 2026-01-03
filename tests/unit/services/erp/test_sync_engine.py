"""Tests for ERP Sync Engine.

Testet die Sync-Engine mit Konflikt-Erkennung und -Aufloesung.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.erp.sync_engine import (
    SyncEngine,
    SyncType,
    SyncStrategy,
    SyncRecord,
    SyncBatch,
    create_sync_engine,
)
from app.services.erp.base_connector import (
    ERPConnectionConfig,
    ERPConnectionStatus,
    ERPSyncDirection,
    ERPSyncResult,
    ERPEntity,
)
from app.services.erp.field_mapping import EntityMappingService


# =============================================================================
# Test Fixtures
# =============================================================================


class MockConnector:
    """Mock ERP Connector for testing."""

    def __init__(self, config=None):
        self.config = config or ERPConnectionConfig(
            erp_type="mock",
            name="Mock ERP",
            url="http://mock.erp",
        )
        self._status = ERPConnectionStatus.CONNECTED
        self.erp_type = "mock"

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def sync_customers(self, direction=None, since=None):
        return ERPSyncResult(
            entity=ERPEntity.CUSTOMER,
            direction=direction or ERPSyncDirection.PULL,
            success=True,
            records_synced=5,
            records=[
                {"id": "1", "name": "Customer 1", "email": "c1@example.com"},
                {"id": "2", "name": "Customer 2", "email": "c2@example.com"},
            ],
        )

    async def sync_suppliers(self, direction=None, since=None):
        return ERPSyncResult(
            entity=ERPEntity.SUPPLIER,
            direction=direction or ERPSyncDirection.PULL,
            success=True,
            records=[
                {"id": "101", "name": "Supplier A", "email": "s1@example.com"},
            ],
        )

    async def sync_invoices(self, direction=None, since=None):
        return ERPSyncResult(
            entity=ERPEntity.INVOICE,
            direction=direction or ERPSyncDirection.PULL,
            success=True,
            records=[
                {"id": "inv-1", "number": "INV-001", "amount": 1000.00},
                {"id": "inv-2", "number": "INV-002", "amount": 2500.00},
            ],
        )

    def _create_sync_result(self, entity, direction, success=True, error_message=None):
        import uuid
        return ERPSyncResult(
            entity=entity,
            direction=direction,
            success=success,
            started_at=datetime.now(timezone.utc),
            error_message=error_message,
            sync_id=str(uuid.uuid4()),
        )

    def _complete_sync_result(self, result):
        result.completed_at = datetime.now(timezone.utc)
        if result.started_at:
            result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        return result


@pytest.fixture
def mock_connector():
    """Create a mock connector."""
    return MockConnector()


@pytest.fixture
def mapping_service():
    """Create a mapping service."""
    return EntityMappingService()


@pytest.fixture
def sync_engine(mock_connector, mapping_service):
    """Create a sync engine with mock connector."""
    return SyncEngine(mock_connector, mapping_service)


# =============================================================================
# SyncRecord Tests
# =============================================================================


class TestSyncRecord:
    """Tests for SyncRecord dataclass."""

    def test_creation(self):
        """Test SyncRecord creation."""
        record = SyncRecord(
            local_id="local-1",
            remote_id="remote-1",
            local_data={"name": "Local"},
            remote_data={"name": "Remote"},
        )

        assert record.local_id == "local-1"
        assert record.remote_id == "remote-1"
        assert record.local_data["name"] == "Local"
        assert record.remote_data["name"] == "Remote"

    def test_default_values(self):
        """Test default values."""
        record = SyncRecord()

        assert record.local_id is None
        assert record.remote_id is None
        assert record.local_data == {}
        assert record.remote_data == {}
        assert record.action is None


# =============================================================================
# SyncBatch Tests
# =============================================================================


class TestSyncBatch:
    """Tests for SyncBatch dataclass."""

    def test_creation(self):
        """Test SyncBatch creation."""
        batch = SyncBatch(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            sync_type=SyncType.DELTA,
        )

        assert batch.entity == ERPEntity.CUSTOMER
        assert batch.direction == ERPSyncDirection.PULL
        assert batch.sync_type == SyncType.DELTA
        assert batch.to_create == []
        assert batch.to_update == []
        assert batch.conflicts == []


# =============================================================================
# SyncEngine Initialization Tests
# =============================================================================


class TestSyncEngineInit:
    """Tests for SyncEngine initialization."""

    def test_default_strategy(self, mock_connector):
        """Test default conflict strategy."""
        engine = SyncEngine(mock_connector)

        assert engine.strategy == SyncStrategy.LAST_WRITE_WINS

    def test_custom_strategy(self, mock_connector):
        """Test custom conflict strategy."""
        engine = SyncEngine(mock_connector, strategy=SyncStrategy.LOCAL_WINS)

        assert engine.strategy == SyncStrategy.LOCAL_WINS

    def test_default_mapping_service(self, mock_connector):
        """Test default mapping service creation."""
        engine = SyncEngine(mock_connector)

        assert engine.mapping_service is not None


# =============================================================================
# SyncEngine Sync Tests
# =============================================================================


class TestSyncEntitySync:
    """Tests for sync_entity method."""

    @pytest.mark.asyncio
    async def test_sync_entity_customer(self, sync_engine):
        """Test syncing customer entity."""
        result = await sync_engine.sync_entity(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
        )

        assert isinstance(result, ERPSyncResult)
        assert result.entity == ERPEntity.CUSTOMER
        assert result.success is True
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_sync_entity_invoice(self, sync_engine):
        """Test syncing invoice entity."""
        result = await sync_engine.sync_entity(
            entity=ERPEntity.INVOICE,
            direction=ERPSyncDirection.PULL,
            sync_type=SyncType.FULL,
        )

        assert result.entity == ERPEntity.INVOICE
        assert result.success is True

    @pytest.mark.asyncio
    async def test_sync_entity_with_local_records(self, sync_engine):
        """Test sync with provided local records."""
        local_records = [
            {"id": "1", "erp_id": "remote-1", "name": "Customer 1"},
            {"id": "2", "erp_id": "remote-2", "name": "Customer 2"},
        ]

        result = await sync_engine.sync_entity(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.BIDIRECTIONAL,
            local_records=local_records,
        )

        assert result.success is True


# =============================================================================
# Conflict Detection Tests
# =============================================================================


class TestConflictDetection:
    """Tests for conflict detection."""

    def test_is_conflict_both_modified(self, sync_engine):
        """Test conflict when both sides modified after last sync."""
        now = datetime.now(timezone.utc)
        sync_engine.connector.config.last_sync_at = now - timedelta(hours=1)

        local = {"updated_at": now}
        remote = {"write_date": now.isoformat()}

        is_conflict = sync_engine._is_conflict(local, remote)

        assert is_conflict is True

    def test_is_conflict_only_local_modified(self, sync_engine):
        """Test no conflict when only local modified."""
        now = datetime.now(timezone.utc)
        sync_engine.connector.config.last_sync_at = now - timedelta(hours=1)

        local = {"updated_at": now}
        remote = {"write_date": (now - timedelta(hours=2)).isoformat()}

        is_conflict = sync_engine._is_conflict(local, remote)

        assert is_conflict is False

    def test_is_conflict_no_last_sync(self, sync_engine):
        """Test no conflict when no last sync."""
        sync_engine.connector.config.last_sync_at = None

        local = {"updated_at": datetime.now(timezone.utc)}
        remote = {"write_date": datetime.now(timezone.utc).isoformat()}

        is_conflict = sync_engine._is_conflict(local, remote)

        assert is_conflict is False


# =============================================================================
# Conflict Resolution Tests
# =============================================================================


class TestConflictResolution:
    """Tests for conflict resolution."""

    @pytest.mark.asyncio
    async def test_resolve_last_write_wins_local(self, mock_connector, mapping_service):
        """Test last-write-wins with local winning."""
        engine = SyncEngine(mock_connector, mapping_service, SyncStrategy.LAST_WRITE_WINS)

        now = datetime.now(timezone.utc)
        record = SyncRecord(
            local_id="1",
            remote_id="remote-1",
            local_data={"updated_at": now},
            remote_data={"write_date": (now - timedelta(hours=1)).isoformat()},
        )

        await engine._handle_conflict(ERPEntity.CUSTOMER, record)

        assert record.action == "push"

    @pytest.mark.asyncio
    async def test_resolve_last_write_wins_remote(self, mock_connector, mapping_service):
        """Test last-write-wins with remote winning."""
        engine = SyncEngine(mock_connector, mapping_service, SyncStrategy.LAST_WRITE_WINS)

        now = datetime.now(timezone.utc)
        record = SyncRecord(
            local_id="1",
            remote_id="remote-1",
            local_data={"updated_at": now - timedelta(hours=1)},
            remote_data={"write_date": now.isoformat()},
        )

        await engine._handle_conflict(ERPEntity.CUSTOMER, record)

        assert record.action == "pull"

    @pytest.mark.asyncio
    async def test_resolve_local_wins(self, mock_connector, mapping_service):
        """Test local-wins strategy."""
        engine = SyncEngine(mock_connector, mapping_service, SyncStrategy.LOCAL_WINS)

        record = SyncRecord(local_id="1", remote_id="remote-1")

        await engine._handle_conflict(ERPEntity.CUSTOMER, record)

        assert record.action == "push"

    @pytest.mark.asyncio
    async def test_resolve_remote_wins(self, mock_connector, mapping_service):
        """Test remote-wins strategy."""
        engine = SyncEngine(mock_connector, mapping_service, SyncStrategy.REMOTE_WINS)

        record = SyncRecord(local_id="1", remote_id="remote-1")

        await engine._handle_conflict(ERPEntity.CUSTOMER, record)

        assert record.action == "pull"

    @pytest.mark.asyncio
    async def test_resolve_queue_for_review(self, mock_connector, mapping_service):
        """Test queue-for-review strategy."""
        engine = SyncEngine(mock_connector, mapping_service, SyncStrategy.QUEUE_FOR_REVIEW)

        record = SyncRecord(local_id="1", remote_id="remote-1")

        await engine._handle_conflict(ERPEntity.CUSTOMER, record)

        assert record.action == "queue"


# =============================================================================
# Checksum Tests
# =============================================================================


class TestChecksums:
    """Tests for checksum functionality."""

    def test_compute_checksum(self):
        """Test checksum computation."""
        data = {"name": "Test", "email": "test@example.com"}

        checksum = SyncEngine.compute_checksum(data)

        assert len(checksum) == 64  # SHA-256
        assert checksum.isalnum()

    def test_checksum_deterministic(self):
        """Test that checksum is deterministic."""
        data = {"name": "Test", "email": "test@example.com"}

        checksum1 = SyncEngine.compute_checksum(data)
        checksum2 = SyncEngine.compute_checksum(data)

        assert checksum1 == checksum2

    def test_checksum_different_for_different_data(self):
        """Test that different data produces different checksum."""
        data1 = {"name": "Test1"}
        data2 = {"name": "Test2"}

        checksum1 = SyncEngine.compute_checksum(data1)
        checksum2 = SyncEngine.compute_checksum(data2)

        assert checksum1 != checksum2

    def test_has_changed(self):
        """Test change detection."""
        old = SyncEngine.compute_checksum({"name": "Old"})
        new = SyncEngine.compute_checksum({"name": "New"})

        assert SyncEngine.has_changed(old, new) is True
        assert SyncEngine.has_changed(old, old) is False
        assert SyncEngine.has_changed(None, new) is True


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateSyncEngine:
    """Tests for create_sync_engine factory."""

    def test_create_with_defaults(self, mock_connector):
        """Test creating engine with defaults."""
        engine = create_sync_engine(mock_connector)

        assert isinstance(engine, SyncEngine)
        assert engine.strategy == SyncStrategy.LAST_WRITE_WINS

    def test_create_with_custom_strategy(self, mock_connector):
        """Test creating engine with custom strategy."""
        engine = create_sync_engine(
            mock_connector,
            strategy=SyncStrategy.QUEUE_FOR_REVIEW,
        )

        assert engine.strategy == SyncStrategy.QUEUE_FOR_REVIEW


# =============================================================================
# Batch Processing Tests
# =============================================================================


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.mark.asyncio
    async def test_prepare_batch_pull(self, sync_engine):
        """Test preparing pull batch."""
        local_records = []
        remote_records = [
            {"id": 1, "name": "Customer 1"},
            {"id": 2, "name": "Customer 2"},
        ]

        batch = await sync_engine._prepare_batch(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            sync_type=SyncType.DELTA,
            local_records=local_records,
            remote_records=remote_records,
        )

        assert len(batch.to_create) == 2
        assert len(batch.to_update) == 0

    @pytest.mark.asyncio
    async def test_prepare_batch_with_updates(self, sync_engine):
        """Test preparing batch with updates."""
        local_records = [
            {"id": "local-1", "erp_id": "1", "name": "Old Name"},
        ]
        remote_records = [
            {"id": "1", "name": "New Name"},
        ]

        batch = await sync_engine._prepare_batch(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            sync_type=SyncType.DELTA,
            local_records=local_records,
            remote_records=remote_records,
        )

        assert len(batch.to_update) == 1
        assert len(batch.to_create) == 0


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests for sync enums."""

    def test_sync_type_values(self):
        """Test SyncType values."""
        assert SyncType.FULL.value == "full"
        assert SyncType.DELTA.value == "delta"
        assert SyncType.MANUAL.value == "manual"

    def test_sync_strategy_values(self):
        """Test SyncStrategy values."""
        assert SyncStrategy.LAST_WRITE_WINS.value == "last_write_wins"
        assert SyncStrategy.LOCAL_WINS.value == "local_wins"
        assert SyncStrategy.REMOTE_WINS.value == "remote_wins"
        assert SyncStrategy.QUEUE_FOR_REVIEW.value == "queue_for_review"


# =============================================================================
# Fetch Remote Tests (Sprint 5: ERP Sync Implementation)
# =============================================================================


class TestFetchRemote:
    """Tests for _fetch_remote method - verifying actual record retrieval."""

    @pytest.mark.asyncio
    async def test_fetch_remote_customers_returns_records(self, sync_engine):
        """Test _fetch_remote returns actual customer records."""
        records = await sync_engine._fetch_remote(
            entity=ERPEntity.CUSTOMER,
            sync_type=SyncType.FULL,
        )

        assert len(records) == 2
        assert records[0]["id"] == "1"
        assert records[0]["name"] == "Customer 1"
        assert records[1]["id"] == "2"

    @pytest.mark.asyncio
    async def test_fetch_remote_suppliers_returns_records(self, sync_engine):
        """Test _fetch_remote returns actual supplier records."""
        records = await sync_engine._fetch_remote(
            entity=ERPEntity.SUPPLIER,
            sync_type=SyncType.DELTA,
        )

        assert len(records) == 1
        assert records[0]["id"] == "101"
        assert records[0]["name"] == "Supplier A"

    @pytest.mark.asyncio
    async def test_fetch_remote_invoices_returns_records(self, sync_engine):
        """Test _fetch_remote returns actual invoice records."""
        records = await sync_engine._fetch_remote(
            entity=ERPEntity.INVOICE,
            sync_type=SyncType.FULL,
        )

        assert len(records) == 2
        assert records[0]["number"] == "INV-001"
        assert records[1]["amount"] == 2500.00

    @pytest.mark.asyncio
    async def test_fetch_remote_unsupported_entity_returns_empty(self, sync_engine):
        """Test _fetch_remote returns empty for unsupported entity."""
        records = await sync_engine._fetch_remote(
            entity=ERPEntity.ORDER,
            sync_type=SyncType.FULL,
        )

        assert records == []

    @pytest.mark.asyncio
    async def test_fetch_remote_with_since_datetime(self, sync_engine):
        """Test _fetch_remote passes since parameter correctly."""
        since = datetime.now(timezone.utc) - timedelta(hours=1)

        records = await sync_engine._fetch_remote(
            entity=ERPEntity.CUSTOMER,
            sync_type=SyncType.DELTA,
            since=since,
        )

        assert len(records) == 2  # Mock returns same records regardless of since

    @pytest.mark.asyncio
    async def test_sync_entity_uses_fetched_records(self, sync_engine):
        """Test that sync_entity properly uses records from _fetch_remote."""
        result = await sync_engine.sync_entity(
            entity=ERPEntity.CUSTOMER,
            direction=ERPSyncDirection.PULL,
            sync_type=SyncType.FULL,
        )

        assert result.success is True
        # Should have created 2 records (no local records to match against)
        assert result.records_created == 2
