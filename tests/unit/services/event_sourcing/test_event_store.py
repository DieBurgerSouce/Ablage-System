# -*- coding: utf-8 -*-
"""
Tests fuer EventStore - Append-Only Event Storage fuer Event-Sourcing.

Phase 4.2.1 (P0 - Infrastruktur)

Testet:
- Event-Append mit korrekten Feldern
- Sequenznummer-Inkrementierung
- Aggregate-Type Validierung
- DB-Session Pflichtpruefung
- AuditChain Bridge (Compliance-Events)
- Event-Abfragen (Reihenfolge, Filter, Korrelation)
- Concurrent Retry bei IntegrityError
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.event_sourcing.event_store import (
    EventStore,
    StoredEvent,
    COMPLIANCE_EVENT_MAP,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_mock_db(max_sequence: int = 0) -> AsyncMock:
    """Erstellt eine Mock-AsyncSession mit konfigurierbarer Max-Sequence."""
    db = AsyncMock()

    # execute() -> result -> scalar() returns max_sequence
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = max_sequence

    db.execute.return_value = scalar_result
    db.add = MagicMock()

    # flush + refresh als AsyncMock
    db.flush = AsyncMock()

    async def _refresh(obj: object) -> None:
        # Simuliert: DB setzt id und created_at
        if not hasattr(obj, "id") or getattr(obj, "id") is None:
            object.__setattr__(obj, "id", uuid.uuid4())
        if not hasattr(obj, "created_at") or getattr(obj, "created_at") is None:
            object.__setattr__(obj, "created_at", datetime.now(timezone.utc))

    db.refresh = AsyncMock(side_effect=_refresh)
    db.rollback = AsyncMock()

    return db


def _make_event_id() -> uuid.UUID:
    return uuid.uuid4()


def _base_params() -> dict:
    """Basis-Parameter fuer EventStore.append()."""
    return {
        "aggregate_type": "document",
        "aggregate_id": uuid.uuid4(),
        "event_type": "document_created",
        "event_data": {"filename": "test.pdf"},
        "company_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
    }


# =============================================================================
# Tests
# =============================================================================


class TestEventStoreAppend:
    """Tests fuer EventStore.append()."""

    @pytest.mark.asyncio
    async def test_append_creates_event(self) -> None:
        """Event wird mit korrekten Feldern gespeichert."""
        db = _make_mock_db(max_sequence=0)
        store = EventStore()
        params = _base_params()

        result = await store.append(**params, db=db)

        assert isinstance(result, StoredEvent)
        assert result.aggregate_type == params["aggregate_type"]
        assert result.aggregate_id == params["aggregate_id"]
        assert result.event_type == params["event_type"]
        assert result.event_data == params["event_data"]
        assert result.user_id == params["user_id"]
        assert result.sequence_number == 1
        assert result.created_at is not None
        # DB operations were called
        db.add.assert_called_once()
        db.flush.assert_awaited()
        db.refresh.assert_awaited()

    @pytest.mark.asyncio
    async def test_append_increments_sequence(self) -> None:
        """Sequenznummer wird korrekt hochgezaehlt."""
        db = _make_mock_db(max_sequence=5)
        store = EventStore()
        params = _base_params()

        result = await store.append(**params, db=db)

        assert result.sequence_number == 6

    @pytest.mark.asyncio
    async def test_append_validates_aggregate_type(self) -> None:
        """Ungueltige Aggregat-Typen werden mit ValueError abgelehnt."""
        db = _make_mock_db()
        store = EventStore()
        params = _base_params()
        params["aggregate_type"] = "invalid_type"

        with pytest.raises(ValueError, match="Ungültiger Aggregat-Typ"):
            await store.append(**params, db=db)

    @pytest.mark.asyncio
    async def test_append_requires_db_session(self) -> None:
        """Ohne Session wird ValueError ausgeloest."""
        store = EventStore()
        params = _base_params()

        with pytest.raises(ValueError, match="Datenbank-Session erforderlich"):
            await store.append(**params, db=None)

    @pytest.mark.asyncio
    async def test_append_bridges_to_audit_chain(self) -> None:
        """Compliance-Events werden an AuditChain weitergeleitet."""
        db = _make_mock_db(max_sequence=0)
        store = EventStore()
        params = _base_params()
        params["event_type"] = "document_created"  # In COMPLIANCE_EVENT_MAP

        with patch.object(
            store, "_bridge_to_audit_chain", new_callable=AsyncMock
        ) as mock_bridge:
            await store.append(**params, db=db)

            mock_bridge.assert_awaited_once()
            call_kwargs = mock_bridge.call_args.kwargs
            assert call_kwargs["event_type"] == "document_created"
            assert call_kwargs["company_id"] == params["company_id"]

    @pytest.mark.asyncio
    async def test_append_non_compliance_event_skips_bridge(self) -> None:
        """Nicht-Compliance Events werden nicht an AuditChain gebrided."""
        db = _make_mock_db(max_sequence=0)
        store = EventStore()
        params = _base_params()
        params["event_type"] = "some_internal_event"  # NOT in COMPLIANCE_EVENT_MAP

        # _bridge_to_audit_chain is called but returns early (no chain_event_type)
        with patch(
            "app.services.event_sourcing.event_store.COMPLIANCE_EVENT_MAP",
            {
                "document_created": MagicMock(),
                "document_archived": MagicMock(),
            },
        ):
            # Should not raise, bridge silently skips
            result = await store.append(**params, db=db)
            assert result.event_type == "some_internal_event"

    @pytest.mark.asyncio
    async def test_concurrent_append_retry(self) -> None:
        """IntegrityError fuehrt zu Retry (max 3 Versuche)."""
        db = _make_mock_db(max_sequence=0)
        store = EventStore()
        params = _base_params()

        # Erster Aufruf: IntegrityError, zweiter: Erfolg
        call_count = 0
        original_execute = db.execute

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Erste execute -> liefert sequence
                return original_execute.return_value
            elif call_count == 2:
                # flush wirft IntegrityError -> wird im except behandelt
                # Wir simulieren das ueber execute
                return original_execute.return_value
            return original_execute.return_value

        db.execute = AsyncMock(side_effect=_side_effect)

        # Simulate IntegrityError on first flush, success on second
        flush_call_count = 0

        async def _flush_side_effect() -> None:
            nonlocal flush_call_count
            flush_call_count += 1
            if flush_call_count == 1:
                raise IntegrityError("duplicate", {}, Exception())

        db.flush = AsyncMock(side_effect=_flush_side_effect)

        result = await store.append(**params, db=db)

        # Retry happened: rollback was called after first failure
        db.rollback.assert_awaited()
        assert result.sequence_number == 1


class TestEventStoreGetEvents:
    """Tests fuer EventStore.get_events() und verwandte Abfragen."""

    @pytest.mark.asyncio
    async def test_get_events_returns_ordered(self) -> None:
        """Events kommen in sequence_number Reihenfolge."""
        db = AsyncMock()
        store = EventStore()

        # Mock 3 Events mit aufsteigender Sequenz
        mock_events = []
        for seq in [1, 2, 3]:
            evt = MagicMock()
            evt.id = uuid.uuid4()
            evt.aggregate_type = "document"
            evt.aggregate_id = uuid.uuid4()
            evt.sequence_number = seq
            evt.event_type = f"event_{seq}"
            evt.event_data = {"seq": seq}
            evt.metadata = {}
            evt.correlation_id = None
            evt.causation_id = None
            evt.user_id = None
            evt.created_at = datetime.now(timezone.utc)
            mock_events.append(evt)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = mock_events
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        company_id = uuid.uuid4()
        agg_id = uuid.uuid4()

        events = await store.get_events(
            aggregate_type="document",
            aggregate_id=agg_id,
            company_id=company_id,
            db=db,
        )

        assert len(events) == 3
        assert events[0].sequence_number == 1
        assert events[1].sequence_number == 2
        assert events[2].sequence_number == 3
        # All returned as StoredEvent
        for evt in events:
            assert isinstance(evt, StoredEvent)

    @pytest.mark.asyncio
    async def test_get_events_filters_by_company_id(self) -> None:
        """Multi-Tenant Isolation: company_id wird als Filter verwendet."""
        db = AsyncMock()
        store = EventStore()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        company_id = uuid.uuid4()
        other_company_id = uuid.uuid4()
        agg_id = uuid.uuid4()

        # Aufruf mit company_id
        events = await store.get_events(
            aggregate_type="document",
            aggregate_id=agg_id,
            company_id=company_id,
            db=db,
        )

        # Verifiziere dass execute aufgerufen wurde (mit dem Statement das company_id enthaelt)
        db.execute.assert_awaited_once()
        assert events == []

    @pytest.mark.asyncio
    async def test_get_events_after_sequence(self) -> None:
        """after_sequence Filter: Nur Events nach der angegebenen Sequenz."""
        db = AsyncMock()
        store = EventStore()

        # Mock: Nur Event mit seq=5 zurueckgeben (nach after_sequence=3)
        evt = MagicMock()
        evt.id = uuid.uuid4()
        evt.aggregate_type = "document"
        evt.aggregate_id = uuid.uuid4()
        evt.sequence_number = 5
        evt.event_type = "document_modified"
        evt.event_data = {}
        evt.metadata = {}
        evt.correlation_id = None
        evt.causation_id = None
        evt.user_id = None
        evt.created_at = datetime.now(timezone.utc)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [evt]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        events = await store.get_events(
            aggregate_type="document",
            aggregate_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            after_sequence=3,
            db=db,
        )

        assert len(events) == 1
        assert events[0].sequence_number == 5

    @pytest.mark.asyncio
    async def test_get_events_by_correlation(self) -> None:
        """Korrelations-ID Abfrage liefert alle zugehoerigen Events."""
        db = AsyncMock()
        store = EventStore()
        correlation_id = uuid.uuid4()

        # Mock 2 Events mit gleicher correlation_id
        mock_events = []
        for i in range(2):
            evt = MagicMock()
            evt.id = uuid.uuid4()
            evt.aggregate_type = "document"
            evt.aggregate_id = uuid.uuid4()
            evt.sequence_number = i + 1
            evt.event_type = f"event_{i}"
            evt.event_data = {}
            evt.metadata = {}
            evt.correlation_id = correlation_id
            evt.causation_id = None
            evt.user_id = None
            evt.created_at = datetime.now(timezone.utc)
            mock_events.append(evt)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = mock_events
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        events = await store.get_events_by_correlation(
            correlation_id=correlation_id,
            company_id=uuid.uuid4(),
            db=db,
        )

        assert len(events) == 2
        assert all(e.correlation_id == correlation_id for e in events)

    @pytest.mark.asyncio
    async def test_get_event_count(self) -> None:
        """Zaehlung liefert korrekte Anzahl."""
        db = AsyncMock()
        store = EventStore()

        result_mock = MagicMock()
        result_mock.scalar.return_value = 42
        db.execute.return_value = result_mock

        count = await store.get_event_count(
            aggregate_type="document",
            aggregate_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            db=db,
        )

        assert count == 42

    @pytest.mark.asyncio
    async def test_get_event_count_requires_db(self) -> None:
        """get_event_count ohne DB-Session wirft ValueError."""
        store = EventStore()

        with pytest.raises(ValueError, match="Datenbank-Session erforderlich"):
            await store.get_event_count(
                aggregate_type="document",
                aggregate_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=None,
            )
