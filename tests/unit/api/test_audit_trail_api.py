# -*- coding: utf-8 -*-
"""Unit Tests fuer Audit Trail Visualisierung API.

Vision 2026+ Feature #19: Visuelle Timeline aller Dokumenten-Aktionen
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.audit_trail_visualization import (
    AuditTrailEventSchema,
    AuditTrailResponse,
    AuditTrailStatsSchema,
    EVENT_TYPE_CONFIG,
    router,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def mock_user() -> MagicMock:
    """Mock User Objekt."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.company_id = uuid.uuid4()
    return user


@pytest.fixture
def document_id() -> uuid.UUID:
    """Test Document ID."""
    return uuid.uuid4()


@pytest.fixture
def entity_id() -> uuid.UUID:
    """Test Entity ID."""
    return uuid.uuid4()


@pytest.fixture
def company_id() -> uuid.UUID:
    """Test Company ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_audit_event() -> Dict[str, Any]:
    """Beispiel Audit-Event Daten."""
    return {
        "id": uuid.uuid4(),
        "event_type": "document_viewed",
        "title": "Dokument angesehen",
        "target_type": "document",
        "target_id": uuid.uuid4(),
        "target_name": "Rechnung_2026_001.pdf",
        "actor_id": uuid.uuid4(),
        "actor_name": "Max Mustermann",
        "actor_email": "max@example.com",
        "timestamp": datetime.now(timezone.utc),
        "icon": "Eye",
        "color": "gray",
        "is_important": False,
    }


# =============================================================================
# Test: Event Type Configuration
# =============================================================================


class TestEventTypeConfig:
    """Tests fuer EVENT_TYPE_CONFIG."""

    def test_event_config_exists(self) -> None:
        """EVENT_TYPE_CONFIG ist nicht leer."""
        assert len(EVENT_TYPE_CONFIG) > 0

    def test_all_events_have_required_fields(self) -> None:
        """Alle Events haben erforderliche Felder."""
        required_fields = ["title", "icon", "color", "important"]

        for event_type, config in EVENT_TYPE_CONFIG.items():
            for field in required_fields:
                assert field in config, f"{event_type} fehlt Feld: {field}"

    def test_document_events_exist(self) -> None:
        """Dokument-Events existieren."""
        document_events = [
            "document_created",
            "document_viewed",
            "document_downloaded",
            "document_updated",
            "document_deleted",
        ]
        for event in document_events:
            assert event in EVENT_TYPE_CONFIG, f"Event fehlt: {event}"

    def test_ocr_events_exist(self) -> None:
        """OCR-Events existieren."""
        ocr_events = ["ocr_started", "ocr_completed", "ocr_failed"]
        for event in ocr_events:
            assert event in EVENT_TYPE_CONFIG, f"Event fehlt: {event}"

    def test_approval_events_exist(self) -> None:
        """Genehmigungs-Events existieren."""
        approval_events = [
            "approval_requested",
            "approval_approved",
            "approval_rejected",
        ]
        for event in approval_events:
            assert event in EVENT_TYPE_CONFIG, f"Event fehlt: {event}"

    def test_german_titles(self) -> None:
        """Alle Titel sind auf Deutsch."""
        german_words = ["Dokument", "erstellt", "angesehen", "heruntergeladen", "OCR", "Genehmigung"]

        titles = [config["title"] for config in EVENT_TYPE_CONFIG.values()]
        all_titles_text = " ".join(titles)

        # Mindestens einige deutsche Woerter sollten vorkommen
        found_german = any(word in all_titles_text for word in german_words)
        assert found_german, "Titel sollten auf Deutsch sein"

    def test_important_events_marked(self) -> None:
        """Wichtige Events sind markiert."""
        important_events = [
            "document_created",
            "document_deleted",
            "approval_approved",
            "approval_rejected",
        ]

        for event in important_events:
            if event in EVENT_TYPE_CONFIG:
                assert EVENT_TYPE_CONFIG[event]["important"] is True, f"{event} sollte important=True sein"

    def test_colors_are_valid(self) -> None:
        """Farben sind gueltige Tailwind-Farben."""
        valid_colors = {"green", "blue", "red", "yellow", "orange", "gray", "purple", "cyan"}

        for event_type, config in EVENT_TYPE_CONFIG.items():
            assert config["color"] in valid_colors, f"{event_type} hat ungueltige Farbe: {config['color']}"


# =============================================================================
# Test: Pydantic Schemas
# =============================================================================


class TestAuditTrailEventSchema:
    """Tests fuer AuditTrailEventSchema."""

    def test_schema_creation(self, sample_audit_event: Dict[str, Any]) -> None:
        """Schema kann erstellt werden."""
        event = AuditTrailEventSchema(**sample_audit_event)

        assert event.event_type == "document_viewed"
        assert event.title == "Dokument angesehen"
        assert event.icon == "Eye"
        assert event.is_important is False

    def test_schema_with_minimal_fields(self) -> None:
        """Schema mit minimalen Pflichtfeldern."""
        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_viewed",
            title="Dokument angesehen",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
        )

        assert event.event_type == "document_viewed"
        assert event.actor_id is None
        assert event.changes is None

    def test_schema_with_changes(self) -> None:
        """Schema mit Aenderungs-Delta."""
        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_updated",
            title="Dokument aktualisiert",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            changes={
                "old": {"status": "draft"},
                "new": {"status": "published"},
            },
        )

        assert event.changes is not None
        assert "old" in event.changes
        assert "new" in event.changes

    def test_schema_with_metadata(self) -> None:
        """Schema mit Metadaten."""
        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_downloaded",
            title="Dokument heruntergeladen",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            metadata={"browser": "Chrome", "os": "Windows"},
        )

        assert event.ip_address == "192.168.1.100"
        assert event.metadata["browser"] == "Chrome"


class TestAuditTrailResponse:
    """Tests fuer AuditTrailResponse."""

    def test_response_creation(self, sample_audit_event: Dict[str, Any]) -> None:
        """Response kann erstellt werden."""
        event = AuditTrailEventSchema(**sample_audit_event)

        response = AuditTrailResponse(
            events=[event],
            total=1,
            limit=50,
            offset=0,
            has_more=False,
            summary={"document_viewed": 1},
        )

        assert len(response.events) == 1
        assert response.total == 1
        assert response.has_more is False

    def test_response_empty(self) -> None:
        """Leere Response."""
        response = AuditTrailResponse(
            events=[],
            total=0,
            limit=50,
            offset=0,
            has_more=False,
        )

        assert len(response.events) == 0
        assert response.summary == {}

    def test_response_with_pagination(self, sample_audit_event: Dict[str, Any]) -> None:
        """Response mit Paginierung."""
        events = [
            AuditTrailEventSchema(**{**sample_audit_event, "id": uuid.uuid4()})
            for _ in range(10)
        ]

        response = AuditTrailResponse(
            events=events,
            total=50,
            limit=10,
            offset=0,
            has_more=True,
            summary={"document_viewed": 50},
        )

        assert len(response.events) == 10
        assert response.total == 50
        assert response.has_more is True


class TestAuditTrailStatsSchema:
    """Tests fuer AuditTrailStatsSchema."""

    def test_stats_creation(self) -> None:
        """Stats Schema kann erstellt werden."""
        stats = AuditTrailStatsSchema(
            total_events=1000,
            unique_actors=25,
            events_by_type={"document_viewed": 500, "document_updated": 300, "approval_approved": 200},
            events_by_day=[
                {"date": "2026-01-28", "count": 100},
                {"date": "2026-01-27", "count": 150},
            ],
            most_active_users=[
                {"user_id": str(uuid.uuid4()), "name": "User 1", "count": 200},
                {"user_id": str(uuid.uuid4()), "name": "User 2", "count": 150},
            ],
            date_range={"from": "2026-01-01", "to": "2026-01-31"},
        )

        assert stats.total_events == 1000
        assert stats.unique_actors == 25
        assert len(stats.events_by_type) == 3


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_handles_unicode_in_names(self) -> None:
        """Verarbeitet Unicode in Namen."""
        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_created",
            title="Dokument erstellt",
            target_type="document",
            target_id=uuid.uuid4(),
            target_name="Rechnung_Müller_GmbH_äöü.pdf",
            actor_name="Jürgen Böhm",
            timestamp=datetime.now(timezone.utc),
        )

        assert "ü" in event.target_name
        assert "ö" in event.actor_name

    def test_handles_empty_changes(self) -> None:
        """Verarbeitet leere Changes."""
        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_updated",
            title="Dokument aktualisiert",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            changes={},
        )

        assert event.changes == {}

    def test_handles_large_metadata(self) -> None:
        """Verarbeitet grosse Metadaten."""
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(100)}

        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_exported",
            title="Dokument exportiert",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            metadata=large_metadata,
        )

        assert len(event.metadata) == 100

    def test_handles_future_timestamps(self) -> None:
        """Verarbeitet zukuenftige Timestamps."""
        future_time = datetime.now(timezone.utc) + timedelta(days=365)

        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="approval_requested",
            title="Genehmigung angefragt",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=future_time,
        )

        assert event.timestamp > datetime.now(timezone.utc)

    def test_handles_old_timestamps(self) -> None:
        """Verarbeitet alte Timestamps."""
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)

        event = AuditTrailEventSchema(
            id=uuid.uuid4(),
            event_type="document_created",
            title="Dokument erstellt",
            target_type="document",
            target_id=uuid.uuid4(),
            timestamp=old_time,
        )

        assert event.timestamp.year == 2020


# =============================================================================
# Test: Summary Aggregation
# =============================================================================


class TestSummaryAggregation:
    """Tests fuer Summary-Aggregation."""

    def test_summary_counts_event_types(self) -> None:
        """Summary zaehlt Event-Typen korrekt."""
        summary = {
            "document_viewed": 100,
            "document_downloaded": 50,
            "document_updated": 25,
            "approval_approved": 10,
        }

        response = AuditTrailResponse(
            events=[],
            total=185,
            limit=50,
            offset=0,
            has_more=True,
            summary=summary,
        )

        assert sum(response.summary.values()) == 185
        assert response.summary["document_viewed"] == 100

    def test_summary_with_zero_counts(self) -> None:
        """Summary mit Null-Counts."""
        summary = {
            "document_viewed": 0,
            "document_updated": 0,
        }

        response = AuditTrailResponse(
            events=[],
            total=0,
            limit=50,
            offset=0,
            has_more=False,
            summary=summary,
        )

        assert response.total == 0
        assert sum(response.summary.values()) == 0


# =============================================================================
# Test: Icon and Color Mapping
# =============================================================================


class TestIconAndColorMapping:
    """Tests fuer Icon und Farb-Mapping."""

    def test_important_events_have_distinct_colors(self) -> None:
        """Wichtige Events haben unterscheidbare Farben."""
        important_events = [k for k, v in EVENT_TYPE_CONFIG.items() if v["important"]]

        colors = [EVENT_TYPE_CONFIG[e]["color"] for e in important_events]

        # Nicht alle wichtigen Events sollten die gleiche Farbe haben
        assert len(set(colors)) > 1

    def test_delete_events_are_red(self) -> None:
        """Loesch-Events sind rot."""
        delete_events = [k for k in EVENT_TYPE_CONFIG.keys() if "deleted" in k]

        for event in delete_events:
            assert EVENT_TYPE_CONFIG[event]["color"] == "red"

    def test_create_events_are_green(self) -> None:
        """Erstellungs-Events sind gruen."""
        create_events = [k for k in EVENT_TYPE_CONFIG.keys() if "created" in k or "uploaded" in k]

        for event in create_events:
            if event in EVENT_TYPE_CONFIG:
                assert EVENT_TYPE_CONFIG[event]["color"] == "green"

    def test_all_icons_are_strings(self) -> None:
        """Alle Icons sind Strings (Lucide Namen)."""
        for event_type, config in EVENT_TYPE_CONFIG.items():
            assert isinstance(config["icon"], str)
            assert len(config["icon"]) > 0


# =============================================================================
# Test: Date Range Filtering
# =============================================================================


class TestDateRangeFiltering:
    """Tests fuer Datumsbereichs-Filterung."""

    def test_stats_date_range_format(self) -> None:
        """Datumsbereich hat korrektes Format."""
        stats = AuditTrailStatsSchema(
            total_events=100,
            unique_actors=10,
            events_by_type={},
            events_by_day=[],
            most_active_users=[],
            date_range={"from": "2026-01-01", "to": "2026-01-31"},
        )

        assert "from" in stats.date_range
        assert "to" in stats.date_range
        assert stats.date_range["from"] < stats.date_range["to"]

    def test_events_by_day_structure(self) -> None:
        """Events-by-day hat korrekte Struktur."""
        events_by_day = [
            {"date": "2026-01-28", "count": 100},
            {"date": "2026-01-27", "count": 150},
            {"date": "2026-01-26", "count": 80},
        ]

        stats = AuditTrailStatsSchema(
            total_events=330,
            unique_actors=20,
            events_by_type={},
            events_by_day=events_by_day,
            most_active_users=[],
            date_range={"from": "2026-01-26", "to": "2026-01-28"},
        )

        assert len(stats.events_by_day) == 3
        assert all("date" in d for d in stats.events_by_day)
        assert all("count" in d for d in stats.events_by_day)
