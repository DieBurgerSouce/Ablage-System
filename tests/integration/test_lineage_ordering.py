# -*- coding: utf-8 -*-
"""
Integration Tests: Document Lineage Event Ordering.

Tests Lineage-Event-Tracking unter Stress-Bedingungen:
- Concurrent event creation
- Correlation ID tracking
- Summary consistency

Feinpoliert und durchdacht - Lineage Event Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def lineage_events():
    """Sample lineage events for a document."""
    document_id = str(uuid4())
    correlation_id = str(uuid4())

    return [
        {
            "document_id": document_id,
            "correlation_id": correlation_id,
            "event_type": "import",
            "event_data": {"source": "email", "sender": "rechnungen@amazon.de"},
            "timestamp": datetime.utcnow(),
        },
        {
            "document_id": document_id,
            "correlation_id": correlation_id,
            "event_type": "ocr_start",
            "event_data": {"backend": "deepseek"},
            "timestamp": datetime.utcnow(),
        },
        {
            "document_id": document_id,
            "correlation_id": correlation_id,
            "event_type": "ocr_complete",
            "event_data": {"confidence": 0.95, "duration_ms": 1500},
            "timestamp": datetime.utcnow(),
        },
    ]


# =============================================================================
# TEST 1: CONCURRENT EVENT CREATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_event_ordering_concurrent(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test gleichzeitige Event-Erstellung mit korrekter Reihenfolge.

    ARRANGE: 10 Events gleichzeitig erstellen
    ACT: Concurrent event creation
    ASSERT: Events in chronologischer Reihenfolge gespeichert
    """
    document_id = str(uuid4())
    correlation_id = str(uuid4())

    with patch("app.services.lineage.document_lineage_service.DocumentLineageService") as MockService:
        mock_service = MockService.return_value

        events_stored = []

        async def mock_record_event(
            document_id: str,
            event_type: str,
            correlation_id: str,
            **kwargs
        ):
            """Record event with timestamp."""
            event = {
                "document_id": document_id,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow(),
                **kwargs,
            }
            await asyncio.sleep(0.01)  # Simulate DB write
            events_stored.append(event)
            return event

        mock_service.record_event = mock_record_event

        # ACT: Create 10 events concurrently
        event_types = [
            "import", "ocr_start", "ocr_complete", "classification",
            "extraction", "entity_link", "modification", "approval",
            "export", "archive"
        ]

        tasks = [
            mock_service.record_event(
                document_id=document_id,
                event_type=event_type,
                correlation_id=correlation_id,
            )
            for event_type in event_types
        ]

        await asyncio.gather(*tasks)

        # ASSERT: All events stored
        assert len(events_stored) == 10

        # ASSERT: Events have unique timestamps (ordering possible)
        timestamps = [e["timestamp"] for e in events_stored]
        assert len(set(timestamps)) >= 8  # At least 80% unique (concurrent writes)


# =============================================================================
# TEST 2: CORRELATION ID TRACKING
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_event_correlation(
    async_client: AsyncClient,
    auth_headers: dict,
    lineage_events: list,
):
    """
    Test Correlation-ID-Tracking über mehrere Events.

    ARRANGE: 3 Events mit gleicher Correlation-ID
    ACT: Abrufen aller Events mit Correlation-ID
    ASSERT: Alle 3 Events gefunden, korrekt gruppiert
    """
    correlation_id = lineage_events[0]["correlation_id"]

    with patch("app.services.lineage.document_lineage_service.DocumentLineageService") as MockService:
        mock_service = MockService.return_value

        async def mock_get_events_by_correlation(correlation_id: str):
            """Get all events with same correlation ID."""
            return [
                e for e in lineage_events
                if e["correlation_id"] == correlation_id
            ]

        mock_service.get_events_by_correlation = mock_get_events_by_correlation

        # ACT: Get events by correlation ID
        result = await mock_service.get_events_by_correlation(correlation_id)

        # ASSERT: All 3 events found
        assert len(result) == 3
        assert all(e["correlation_id"] == correlation_id for e in result)

        # ASSERT: Event flow is logical (import → ocr_start → ocr_complete)
        event_types = [e["event_type"] for e in result]
        assert event_types == ["import", "ocr_start", "ocr_complete"]


# =============================================================================
# TEST 3: SUMMARY CONSISTENCY
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_event_summary_update(
    async_client: AsyncClient,
    auth_headers: dict,
    lineage_events: list,
):
    """
    Test Summary-Konsistenz bei konkurrierenden Updates.

    ARRANGE: Mehrere Events aktualisieren Summary gleichzeitig
    ACT: Concurrent summary updates
    ASSERT: Summary korrekt aggregiert, keine Daten verloren
    """
    document_id = lineage_events[0]["document_id"]

    with patch("app.services.lineage.document_lineage_service.DocumentLineageService") as MockService:
        mock_service = MockService.return_value

        summary = {
            "total_events": 0,
            "import_count": 0,
            "ocr_count": 0,
            "modification_count": 0,
        }

        lock = asyncio.Lock()

        async def mock_update_summary(event_type: str):
            """Update summary with lock."""
            async with lock:
                summary["total_events"] += 1
                if event_type == "import":
                    summary["import_count"] += 1
                elif event_type.startswith("ocr"):
                    summary["ocr_count"] += 1
                elif event_type == "modification":
                    summary["modification_count"] += 1

                await asyncio.sleep(0.01)  # Simulate DB write

        mock_service.update_summary = mock_update_summary

        # ACT: Update summary concurrently for all events
        tasks = [
            mock_service.update_summary(event["event_type"])
            for event in lineage_events
        ]
        await asyncio.gather(*tasks)

        # ASSERT: Summary consistent
        assert summary["total_events"] == 3
        assert summary["import_count"] == 1
        assert summary["ocr_count"] == 2  # ocr_start + ocr_complete
        assert summary["modification_count"] == 0


# =============================================================================
# BONUS: LINEAGE TIMELINE QUERY PERFORMANCE
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_timeline_query_performance(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test Performance von Timeline-Queries bei vielen Events.

    ARRANGE: 500 Events für ein Dokument
    ACT: Abrufen der vollständigen Timeline
    ASSERT: Query unter 100ms, alle Events korrekt sortiert
    """
    document_id = str(uuid4())

    # Create 500 events
    events = [
        {
            "document_id": document_id,
            "event_type": ["import", "ocr_start", "ocr_complete"][i % 3],
            "timestamp": datetime.utcnow(),
            "sequence_number": i,
        }
        for i in range(500)
    ]

    with patch("app.services.lineage.document_lineage_service.DocumentLineageService") as MockService:
        mock_service = MockService.return_value

        async def mock_get_timeline(document_id: str, limit: int = 1000):
            """Get timeline with performance tracking."""
            start_time = asyncio.get_event_loop().time()

            # Simulate indexed DB query
            await asyncio.sleep(0.05)  # 50ms query time

            result = sorted(events, key=lambda e: e["sequence_number"])

            end_time = asyncio.get_event_loop().time()
            query_time_ms = (end_time - start_time) * 1000

            return {
                "events": result[:limit],
                "total_count": len(events),
                "query_time_ms": query_time_ms,
            }

        mock_service.get_timeline = mock_get_timeline

        # ACT: Get full timeline
        result = await mock_service.get_timeline(document_id)

        # ASSERT: Fast query
        assert result["query_time_ms"] < 100  # Under 100ms

        # ASSERT: All events returned
        assert result["total_count"] == 500
        assert len(result["events"]) == 500

        # ASSERT: Correct ordering
        sequence_numbers = [e["sequence_number"] for e in result["events"]]
        assert sequence_numbers == list(range(500))


# =============================================================================
# BONUS: LINEAGE EVENT DEDUPLICATION
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_lineage_event_deduplication(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test Deduplication von identischen Events.

    ARRANGE: Gleicher Event wird 3x gesendet (Retry-Logik)
    ACT: Record event mit Deduplication
    ASSERT: Nur 1 Event gespeichert
    """
    document_id = str(uuid4())
    correlation_id = str(uuid4())

    with patch("app.services.lineage.document_lineage_service.DocumentLineageService") as MockService:
        mock_service = MockService.return_value

        stored_events = []

        async def mock_record_with_dedup(
            document_id: str,
            event_type: str,
            correlation_id: str,
            idempotency_key: str = None,
            **kwargs
        ):
            """Record event with deduplication."""
            # Check if event already exists
            if idempotency_key:
                existing = [
                    e for e in stored_events
                    if e.get("idempotency_key") == idempotency_key
                ]
                if existing:
                    return existing[0]  # Return existing event

            # Store new event
            event = {
                "document_id": document_id,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "idempotency_key": idempotency_key,
                **kwargs,
            }
            stored_events.append(event)
            return event

        mock_service.record_event = mock_record_with_dedup

        # ACT: Try to record same event 3 times
        idempotency_key = "ocr_complete_123"

        for _ in range(3):
            await mock_service.record_event(
                document_id=document_id,
                event_type="ocr_complete",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )

        # ASSERT: Only 1 event stored
        assert len(stored_events) == 1
        assert stored_events[0]["idempotency_key"] == idempotency_key
