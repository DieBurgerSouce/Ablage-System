# -*- coding: utf-8 -*-
"""Unit tests for Event Sourcing Services (EventStore, SnapshotService, ProjectionService)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from app.services.event_sourcing.event_store import EventStore, StoredEvent
from app.services.event_sourcing.snapshot_service import SnapshotService, SnapshotData
from app.services.event_sourcing.projection_service import ProjectionService


# ============================================================================
# EventStore Tests
# ============================================================================


@pytest.mark.asyncio
async def test_event_store_append():
    """Test EventStore appends event with auto-incremented sequence."""
    # Arrange
    mock_db = AsyncMock()
    event_store = EventStore()

    aggregate_type = "document"
    aggregate_id = uuid4()
    event_type = "document_created"
    event_data = {"filename": "test.pdf", "status": "pending"}
    company_id = uuid4()
    user_id = uuid4()
    correlation_id = uuid4()

    # Mock der max sequence query - gibt 5 zurück, next sollte 6 sein
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Mock flush und refresh
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    # Mock das erstellte Event mit created_at
    mock_event = MagicMock()
    mock_event.id = uuid4()
    mock_event.created_at = datetime.now(timezone.utc)

    def mock_add(event):
        """Simuliert db.add und setzt Event-Attribute."""
        event.id = mock_event.id
        event.created_at = mock_event.created_at

    mock_db.add = MagicMock(side_effect=mock_add)

    # SHA-256 Hash-Chain: previous chain_hash muss ein gueltiger Hash-String
    # sein (sonst bricht die Verkettung mit int+str). Bei seq>1 fragt der
    # EventStore den vorherigen chain_hash via _get_previous_chain_hash ab.
    event_store._get_previous_chain_hash = AsyncMock(return_value="0" * 64)

    # Act
    stored_event = await event_store.append(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_data=event_data,
        company_id=company_id,
        user_id=user_id,
        correlation_id=correlation_id,
        db=mock_db,
    )

    # Assert
    assert stored_event.aggregate_type == aggregate_type
    assert stored_event.aggregate_id == aggregate_id
    assert stored_event.event_type == event_type
    assert stored_event.event_data == event_data
    assert stored_event.sequence_number == 6  # max(5) + 1
    assert stored_event.correlation_id == correlation_id
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_store_get_events():
    """Test EventStore retrieves events for aggregate."""
    # Arrange
    mock_db = AsyncMock()
    event_store = EventStore()

    aggregate_type = "invoice"
    aggregate_id = uuid4()
    company_id = uuid4()

    # Mock 3 Events
    mock_events = []
    for i in range(1, 4):
        mock_event = MagicMock()
        mock_event.id = uuid4()
        mock_event.aggregate_type = aggregate_type
        mock_event.aggregate_id = aggregate_id
        mock_event.sequence_number = i
        mock_event.event_type = f"invoice_event_{i}"
        mock_event.event_data = {"step": i}
        mock_event.metadata = {}
        mock_event.correlation_id = None
        mock_event.causation_id = None
        mock_event.user_id = uuid4()
        mock_event.created_at = datetime.now(timezone.utc)
        mock_events.append(mock_event)

    # Mock query result
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_events
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Act
    events = await event_store.get_events(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        company_id=company_id,
        after_sequence=0,
        db=mock_db,
    )

    # Assert
    assert len(events) == 3
    assert events[0].sequence_number == 1
    assert events[1].sequence_number == 2
    assert events[2].sequence_number == 3
    assert all(isinstance(e, StoredEvent) for e in events)


@pytest.mark.asyncio
async def test_event_store_correlation_id():
    """Test EventStore retrieves events linked via correlation_id."""
    # Arrange
    mock_db = AsyncMock()
    event_store = EventStore()

    correlation_id = uuid4()

    # Mock Events mit gleicher correlation_id
    mock_events = []
    for i in range(3):
        mock_event = MagicMock()
        mock_event.id = uuid4()
        mock_event.aggregate_type = "document"
        mock_event.aggregate_id = uuid4()  # Unterschiedliche Aggregates
        mock_event.sequence_number = 1
        mock_event.event_type = f"event_{i}"
        mock_event.event_data = {}
        mock_event.metadata = {}
        mock_event.correlation_id = correlation_id
        mock_event.causation_id = None
        mock_event.user_id = uuid4()
        mock_event.created_at = datetime.now(timezone.utc) + timedelta(seconds=i)
        mock_events.append(mock_event)

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_events
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)

    company_id = uuid4()

    # Act
    events = await event_store.get_events_by_correlation(
        correlation_id=correlation_id,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert len(events) == 3
    assert all(e.correlation_id == correlation_id for e in events)


@pytest.mark.asyncio
async def test_event_store_aggregate_type_whitelist():
    """Test EventStore rejects invalid aggregate types."""
    # Arrange
    mock_db = AsyncMock()
    event_store = EventStore()

    invalid_type = "malicious_type"

    # Act & Assert
    with pytest.raises(ValueError, match="Ungültiger Aggregat-Typ"):
        await event_store.append(
            aggregate_type=invalid_type,
            aggregate_id=uuid4(),
            event_type="test",
            event_data={},
            company_id=uuid4(),
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_event_store_multi_tenant():
    """Test EventStore company isolation works."""
    # Arrange
    mock_db = AsyncMock()
    event_store = EventStore()

    company_id = uuid4()
    aggregate_id = uuid4()

    # Mock max sequence (company isolation wird in DB query gemacht, hier testen wir nur den Call)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_event = MagicMock()
    mock_event.id = uuid4()
    mock_event.created_at = datetime.now(timezone.utc)

    def mock_add(event):
        event.id = mock_event.id
        event.created_at = mock_event.created_at
        # Verify company_id ist gesetzt
        assert event.company_id == company_id

    mock_db.add = MagicMock(side_effect=mock_add)

    # Act
    stored_event = await event_store.append(
        aggregate_type="document",
        aggregate_id=aggregate_id,
        event_type="test",
        event_data={},
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    mock_db.add.assert_called_once()


# ============================================================================
# SnapshotService Tests
# ============================================================================


@pytest.mark.asyncio
async def test_snapshot_creation():
    """Test SnapshotService creates snapshot from events."""
    # Arrange
    mock_db = AsyncMock()
    snapshot_service = SnapshotService()

    aggregate_type = "document"
    aggregate_id = uuid4()
    state = {"status": "completed", "ocr_text": "Test", "confidence": 0.95}
    sequence_number = 42
    company_id = uuid4()

    # Mock get_latest_snapshot - kein vorheriger Snapshot
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_snapshot = MagicMock()
    mock_snapshot.id = uuid4()
    mock_snapshot.created_at = datetime.now(timezone.utc)

    def mock_add(snapshot):
        snapshot.id = mock_snapshot.id
        snapshot.created_at = mock_snapshot.created_at

    mock_db.add = MagicMock(side_effect=mock_add)

    # Act
    snapshot = await snapshot_service.create_snapshot(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        state=state,
        sequence_number=sequence_number,
        company_id=company_id,
        db=mock_db,
    )

    # Assert
    assert isinstance(snapshot, SnapshotData)
    assert snapshot.aggregate_type == aggregate_type
    assert snapshot.aggregate_id == aggregate_id
    assert snapshot.state == state
    assert snapshot.sequence_number == sequence_number
    assert snapshot.version == 1  # Erste Version
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_snapshot_auto_trigger():
    """Test SnapshotService triggers snapshot after 50 events."""
    # Arrange
    mock_db = AsyncMock()
    snapshot_service = SnapshotService()

    aggregate_id = uuid4()
    company_id = uuid4()

    # Mock get_latest_snapshot - kein Snapshot vorhanden
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    # Act & Assert - sollte bei 49 false sein
    should_create_49 = await snapshot_service.should_create_snapshot(
        aggregate_type="document",
        aggregate_id=aggregate_id,
        current_sequence=49,
        company_id=company_id,
        db=mock_db,
    )
    assert should_create_49 is False

    # Sollte bei 50 true sein
    should_create_50 = await snapshot_service.should_create_snapshot(
        aggregate_type="document",
        aggregate_id=aggregate_id,
        current_sequence=50,
        company_id=company_id,
        db=mock_db,
    )
    assert should_create_50 is True

    # Sollte bei >50 auch true sein
    should_create_100 = await snapshot_service.should_create_snapshot(
        aggregate_type="document",
        aggregate_id=aggregate_id,
        current_sequence=100,
        company_id=company_id,
        db=mock_db,
    )
    assert should_create_100 is True


@pytest.mark.asyncio
async def test_snapshot_cleanup():
    """Test SnapshotService cleans up old snapshots (keeps last 5)."""
    # Arrange
    mock_db = AsyncMock()
    snapshot_service = SnapshotService()

    aggregate_type = "invoice"
    aggregate_id = uuid4()
    company_id = uuid4()

    # Mock 10 Snapshots (sorted by sequence_number DESC)
    mock_snapshots = []
    for i in range(10, 0, -1):  # 10 down to 1
        mock_snap = MagicMock()
        mock_snap.id = uuid4()
        mock_snap.sequence_number = i * 50
        mock_snapshots.append(mock_snap)

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_snapshots
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    # Mock delete calls
    delete_calls = []
    async def mock_delete(snapshot):
        delete_calls.append(snapshot)
    mock_db.delete = mock_delete

    # Act
    deleted_count = await snapshot_service.cleanup_old_snapshots(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        company_id=company_id,
        keep_count=5,
        db=mock_db,
    )

    # Assert
    assert deleted_count == 5  # Sollte 5 alte loeschen (behalten 5 neueste)
    assert len(delete_calls) == 5


@pytest.mark.asyncio
async def test_snapshot_aggregate_type_whitelist():
    """Test SnapshotService validates aggregate types."""
    # Arrange
    mock_db = AsyncMock()
    snapshot_service = SnapshotService()

    # Act & Assert
    with pytest.raises(ValueError, match="Ungültiger Aggregat-Typ"):
        await snapshot_service.create_snapshot(
            aggregate_type="invalid_type",
            aggregate_id=uuid4(),
            state={},
            sequence_number=1,
            company_id=uuid4(),
            db=mock_db,
        )


# ============================================================================
# ProjectionService Tests
# ============================================================================


@pytest.mark.asyncio
async def test_projection_replay():
    """Test ProjectionService replays events from last snapshot."""
    # Arrange
    mock_db = AsyncMock()
    projection_service = ProjectionService()

    aggregate_id = uuid4()
    company_id = uuid4()
    snapshot_seq = 50

    # Mock snapshot
    mock_snapshot = SnapshotData(
        snapshot_id=uuid4(),
        aggregate_type="document",
        aggregate_id=aggregate_id,
        sequence_number=snapshot_seq,
        state={"status": "processing", "ocr_text": None},
        version=1,
        created_at=datetime.now(timezone.utc),
    )

    # Mock events nach Snapshot
    mock_event = StoredEvent(
        event_id=uuid4(),
        aggregate_type="document",
        aggregate_id=aggregate_id,
        sequence_number=51,
        event_type="document_ocr_completed",
        event_data={"text": "Rechnung", "confidence": 0.98},
        metadata={},
        correlation_id=None,
        causation_id=None,
        user_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )

    with patch.object(projection_service.snapshot_service, 'get_latest_snapshot',
                     new=AsyncMock(return_value=mock_snapshot)):
        with patch.object(projection_service.event_store, 'get_events',
                         new=AsyncMock(return_value=[mock_event])):
            # Act
            state = await projection_service.project(
                aggregate_type="document",
                aggregate_id=aggregate_id,
                company_id=company_id,
                db=mock_db,
            )

    # Assert
    assert state["status"] == "completed"  # Event sollte status geaendert haben
    assert state["ocr_text"] == "Rechnung"
    assert state["ocr_confidence"] == 0.98


@pytest.mark.asyncio
async def test_projection_temporal_query():
    """Test ProjectionService queries state at specific sequence."""
    # Arrange
    mock_db = AsyncMock()
    projection_service = ProjectionService()

    aggregate_id = uuid4()
    company_id = uuid4()
    target_seq = 2

    # Mock events 1-3
    events = [
        StoredEvent(
            event_id=uuid4(),
            aggregate_type="invoice",
            aggregate_id=aggregate_id,
            sequence_number=1,
            event_type="invoice_created",
            event_data={"invoice_number": "INV-001", "amount": 100.0},
            metadata={},
            correlation_id=None,
            causation_id=None,
            user_id=uuid4(),
            created_at=datetime.now(timezone.utc),
        ),
        StoredEvent(
            event_id=uuid4(),
            aggregate_type="invoice",
            aggregate_id=aggregate_id,
            sequence_number=2,
            event_type="payment_received",
            event_data={"amount": 50.0, "received_at": "2026-01-28T10:00:00Z"},
            metadata={},
            correlation_id=None,
            causation_id=None,
            user_id=uuid4(),
            created_at=datetime.now(timezone.utc),
        ),
        StoredEvent(
            event_id=uuid4(),
            aggregate_type="invoice",
            aggregate_id=aggregate_id,
            sequence_number=3,
            event_type="invoice_paid",
            event_data={"paid_at": "2026-01-28T11:00:00Z"},
            metadata={},
            correlation_id=None,
            causation_id=None,
            user_id=uuid4(),
            created_at=datetime.now(timezone.utc),
        ),
    ]

    with patch.object(projection_service.snapshot_service, 'get_latest_snapshot',
                     new=AsyncMock(return_value=None)):
        with patch.object(projection_service.event_store, 'get_events',
                         new=AsyncMock(return_value=events)):
            # Act - Zustand bei Sequenz 2 (vor invoice_paid)
            state = await projection_service.project_at_sequence(
                aggregate_type="invoice",
                aggregate_id=aggregate_id,
                target_sequence=target_seq,
                company_id=company_id,
                db=mock_db,
            )

    # Assert
    assert state["status"] == "open"  # Noch nicht paid (Sequenz 3)
    assert state["amount"] == 100.0
    assert state["paid_amount"] == 50.0  # Payment received wurde angewendet
    assert len(state["payments"]) == 1


@pytest.mark.asyncio
async def test_projection_from_scratch():
    """Test ProjectionService projects from scratch without snapshot."""
    # Arrange
    mock_db = AsyncMock()
    projection_service = ProjectionService()

    aggregate_id = uuid4()
    company_id = uuid4()

    # Mock kein Snapshot
    with patch.object(projection_service.snapshot_service, 'get_latest_snapshot',
                     new=AsyncMock(return_value=None)):
        # Mock Events
        events = [
            StoredEvent(
                event_id=uuid4(),
                aggregate_type="alert",
                aggregate_id=aggregate_id,
                sequence_number=1,
                event_type="alert_created",
                event_data={"category": "fraud", "severity": "high"},
                metadata={},
                correlation_id=None,
                causation_id=None,
                user_id=uuid4(),
                created_at=datetime.now(timezone.utc),
            ),
            StoredEvent(
                event_id=uuid4(),
                aggregate_type="alert",
                aggregate_id=aggregate_id,
                sequence_number=2,
                event_type="alert_acknowledged",
                event_data={"user_id": str(uuid4()), "timestamp": "2026-01-28T10:00:00Z"},
                metadata={},
                correlation_id=None,
                causation_id=None,
                user_id=uuid4(),
                created_at=datetime.now(timezone.utc),
            ),
        ]

        with patch.object(projection_service.event_store, 'get_events',
                         new=AsyncMock(return_value=events)):
            # Act
            state = await projection_service.project(
                aggregate_type="alert",
                aggregate_id=aggregate_id,
                company_id=company_id,
                db=mock_db,
            )

    # Assert
    assert state["category"] == "fraud"
    assert state["severity"] == "high"
    assert state["status"] == "acknowledged"
    assert "acknowledged_at" in state
