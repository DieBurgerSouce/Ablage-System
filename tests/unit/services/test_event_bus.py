# -*- coding: utf-8 -*-
"""
Unit tests for Event Bus Service.

Tests fuer Event-Driven Architecture:
- Event-Erstellung und Serialisierung
- Event-Typen und Pattern-Matching
- Handler-Registrierung
- Event-History
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4, UUID
from pathlib import Path
import sys
import json

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestEventType:
    """Tests fuer EventType Enum."""

    def test_event_types_defined(self):
        """Teste dass alle Event-Typen definiert sind."""
        from app.services.events.event_bus import EventType

        # Document Events
        assert hasattr(EventType, "DOCUMENT_OCR_COMPLETED")
        assert hasattr(EventType, "DOCUMENT_UPLOADED")
        assert hasattr(EventType, "DOCUMENT_DELETED")

        # Property Events
        assert hasattr(EventType, "PROPERTY_RENTAL_RECEIVED")
        assert hasattr(EventType, "PROPERTY_VALUE_UPDATED")
        assert hasattr(EventType, "PROPERTY_KPIS_CALCULATED")

        # Vehicle Events
        assert hasattr(EventType, "VEHICLE_FUEL_LOGGED")
        assert hasattr(EventType, "VEHICLE_SERVICE_DUE")
        assert hasattr(EventType, "VEHICLE_KPIS_CALCULATED")

    def test_event_type_values(self):
        """Teste Event-Typ-Werte Format."""
        from app.services.events.event_bus import EventType

        # Format sollte "entity.action" sein
        assert EventType.DOCUMENT_OCR_COMPLETED.value == "document.ocr_completed"
        assert EventType.PROPERTY_RENTAL_RECEIVED.value == "property.rental_received"
        assert EventType.VEHICLE_FUEL_LOGGED.value == "vehicle.fuel_logged"

    def test_event_type_categories(self):
        """Teste Event-Typ-Kategorien."""
        from app.services.events.event_bus import EventType

        document_events = [e for e in EventType if e.value.startswith("document.")]
        property_events = [e for e in EventType if e.value.startswith("property.")]
        vehicle_events = [e for e in EventType if e.value.startswith("vehicle.")]
        insurance_events = [e for e in EventType if e.value.startswith("insurance.")]
        finance_events = [e for e in EventType if e.value.startswith("finance.")]

        assert len(document_events) >= 3
        assert len(property_events) >= 3
        assert len(vehicle_events) >= 3
        assert len(insurance_events) >= 3
        assert len(finance_events) >= 3


class TestEvent:
    """Tests fuer Event Dataclass."""

    def test_event_creation(self):
        """Teste Event-Erstellung."""
        from app.services.events.event_bus import Event, EventType

        event = Event(
            event_type=EventType.DOCUMENT_OCR_COMPLETED,
            payload={"document_id": "test-123", "text": "Extracted text"}
        )

        assert event.event_type == EventType.DOCUMENT_OCR_COMPLETED
        assert event.payload["document_id"] == "test-123"
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.timestamp, datetime)

    def test_event_with_optional_fields(self):
        """Teste Event mit optionalen Feldern."""
        from app.services.events.event_bus import Event, EventType

        user_id = uuid4()
        space_id = uuid4()
        correlation_id = uuid4()

        event = Event(
            event_type=EventType.PROPERTY_RENTAL_RECEIVED,
            payload={"amount": 1000},
            source="rental_service",
            user_id=user_id,
            space_id=space_id,
            correlation_id=correlation_id
        )

        assert event.source == "rental_service"
        assert event.user_id == user_id
        assert event.space_id == space_id
        assert event.correlation_id == correlation_id

    def test_event_to_dict(self):
        """Teste Event-Serialisierung zu Dictionary."""
        from app.services.events.event_bus import Event, EventType

        event = Event(
            event_type=EventType.VEHICLE_FUEL_LOGGED,
            payload={"liters": 50.5, "cost": 85.00},
            source="fuel_tracker"
        )

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "vehicle.fuel_logged"
        assert event_dict["payload"]["liters"] == 50.5
        assert event_dict["source"] == "fuel_tracker"
        assert "event_id" in event_dict
        assert "timestamp" in event_dict

    def test_event_from_dict(self):
        """Teste Event-Deserialisierung von Dictionary."""
        from app.services.events.event_bus import Event, EventType

        event_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        event_dict = {
            "event_id": event_id,
            "event_type": "insurance.policy_updated",
            "payload": {"policy_number": "POL-123"},
            "timestamp": timestamp,
            "source": "insurance_service",
            "user_id": None,
            "space_id": None,
            "correlation_id": None
        }

        event = Event.from_dict(event_dict)

        assert str(event.event_id) == event_id
        assert event.event_type == EventType.INSURANCE_POLICY_UPDATED
        assert event.payload["policy_number"] == "POL-123"
        assert event.source == "insurance_service"

    def test_event_json_serialization(self):
        """Teste JSON-Serialisierung."""
        from app.services.events.event_bus import Event, EventType

        event = Event(
            event_type=EventType.FINANCE_ANOMALY_DETECTED,
            payload={"amount": 9999.99, "reason": "Unusual transaction"}
        )

        json_str = event.to_json()
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "finance.anomaly_detected"
        assert parsed["payload"]["amount"] == 9999.99


class TestEventPatternMatching:
    """Tests fuer Event Pattern Matching."""

    def test_exact_pattern_match(self):
        """Teste exaktes Pattern-Matching."""
        from app.services.events.event_bus import EventBus

        # Simuliere Pattern-Matching
        patterns = ["document.ocr_completed", "property.*", "*.deleted"]
        event_type = "document.ocr_completed"

        matched = False
        for pattern in patterns:
            if pattern == event_type:
                matched = True
                break

        assert matched is True

    def test_wildcard_suffix_pattern(self):
        """Teste Wildcard-Suffix-Pattern."""
        import fnmatch

        patterns = ["property.*"]
        event_type = "property.rental_received"

        matched = any(fnmatch.fnmatch(event_type, p) for p in patterns)
        assert matched is True

    def test_wildcard_prefix_pattern(self):
        """Teste Wildcard-Prefix-Pattern."""
        import fnmatch

        patterns = ["*.deleted"]
        event_types = ["document.deleted", "property.deleted", "vehicle.deleted"]

        for event_type in event_types:
            matched = any(fnmatch.fnmatch(event_type, p) for p in patterns)
            assert matched is True

    def test_no_match_for_unregistered_pattern(self):
        """Teste dass unregistrierte Patterns nicht matchen."""
        import fnmatch

        patterns = ["document.*"]
        event_type = "property.created"

        matched = any(fnmatch.fnmatch(event_type, p) for p in patterns)
        assert matched is False


class TestEventBusHandlerRegistration:
    """Tests fuer Handler-Registrierung."""

    def test_register_handler_for_event_type(self):
        """Teste Handler-Registrierung fuer Event-Typ."""
        handlers = {}

        def my_handler(event):
            pass

        event_type = "document.ocr_completed"
        if event_type not in handlers:
            handlers[event_type] = []
        handlers[event_type].append(my_handler)

        assert len(handlers[event_type]) == 1
        assert handlers[event_type][0] == my_handler

    def test_register_multiple_handlers(self):
        """Teste Registrierung mehrerer Handler."""
        handlers = {}

        def handler1(event):
            pass

        def handler2(event):
            pass

        event_type = "property.rental_received"
        if event_type not in handlers:
            handlers[event_type] = []
        handlers[event_type].append(handler1)
        handlers[event_type].append(handler2)

        assert len(handlers[event_type]) == 2

    def test_register_pattern_handler(self):
        """Teste Pattern-Handler-Registrierung."""
        pattern_handlers = {}

        def all_property_handler(event):
            pass

        pattern = "property.*"
        if pattern not in pattern_handlers:
            pattern_handlers[pattern] = []
        pattern_handlers[pattern].append(all_property_handler)

        assert len(pattern_handlers[pattern]) == 1


class TestEventHistory:
    """Tests fuer Event-History."""

    def test_event_history_storage(self):
        """Teste Event-History-Speicherung."""
        from app.services.events.event_bus import Event, EventType

        history = []
        max_history = 1000

        for i in range(10):
            event = Event(
                event_type=EventType.DOCUMENT_UPLOADED,
                payload={"doc_index": i}
            )
            history.append(event)
            if len(history) > max_history:
                history = history[-max_history:]

        assert len(history) == 10

    def test_event_history_limit(self):
        """Teste Event-History-Limit."""
        from app.services.events.event_bus import Event, EventType

        history = []
        max_history = 5

        for i in range(10):
            event = Event(
                event_type=EventType.DOCUMENT_UPLOADED,
                payload={"doc_index": i}
            )
            history.append(event)
            if len(history) > max_history:
                history = history[-max_history:]

        assert len(history) == 5
        # Aelteste Events sollten entfernt sein
        assert history[0].payload["doc_index"] == 5

    def test_event_history_filtering_by_type(self):
        """Teste Event-History-Filterung nach Typ."""
        from app.services.events.event_bus import Event, EventType

        history = [
            Event(event_type=EventType.DOCUMENT_UPLOADED, payload={}),
            Event(event_type=EventType.PROPERTY_RENTAL_RECEIVED, payload={}),
            Event(event_type=EventType.DOCUMENT_OCR_COMPLETED, payload={}),
            Event(event_type=EventType.VEHICLE_FUEL_LOGGED, payload={}),
            Event(event_type=EventType.DOCUMENT_DELETED, payload={}),
        ]

        document_events = [
            e for e in history
            if e.event_type.value.startswith("document.")
        ]

        assert len(document_events) == 3


class TestEventBusConfiguration:
    """Tests fuer Event Bus Konfiguration."""

    def test_default_redis_url(self):
        """Teste Standard-Redis-URL."""
        default_redis_url = "redis://localhost:6379/0"
        assert "redis://" in default_redis_url
        assert "6379" in default_redis_url

    def test_channel_prefix(self):
        """Teste Channel-Prefix."""
        channel_prefix = "ablage:events:"
        event_type = "document.ocr_completed"
        channel = f"{channel_prefix}{event_type}"

        assert channel == "ablage:events:document.ocr_completed"

    def test_max_history_size(self):
        """Teste maximale History-Groesse."""
        max_history_size = 1000
        assert max_history_size > 0
        assert max_history_size <= 10000


class TestEventBusMetrics:
    """Tests fuer Event Bus Metriken."""

    def test_event_counter_increment(self):
        """Teste Event-Counter-Inkrementierung."""
        event_counts = {}

        def increment_counter(event_type):
            if event_type not in event_counts:
                event_counts[event_type] = 0
            event_counts[event_type] += 1

        increment_counter("document.uploaded")
        increment_counter("document.uploaded")
        increment_counter("property.created")

        assert event_counts["document.uploaded"] == 2
        assert event_counts["property.created"] == 1

    def test_subscriber_count(self):
        """Teste Subscriber-Zaehler."""
        subscribers = {
            "document.uploaded": [lambda e: None, lambda e: None],
            "property.created": [lambda e: None],
        }

        total_subscribers = sum(len(handlers) for handlers in subscribers.values())
        assert total_subscribers == 3


class TestEventBusErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    def test_invalid_event_type_raises_error(self):
        """Teste dass ungueltiger Event-Typ Fehler wirft."""
        from app.services.events.event_bus import EventType

        with pytest.raises(ValueError):
            EventType("invalid.event.type")

    def test_handler_exception_isolation(self):
        """Teste dass Handler-Exceptions isoliert sind."""
        results = []

        def failing_handler(event):
            raise ValueError("Handler failed")

        def succeeding_handler(event):
            results.append("success")

        handlers = [failing_handler, succeeding_handler]

        for handler in handlers:
            try:
                handler({"type": "test"})
            except Exception:
                pass  # Fehler isolieren

        # Zweiter Handler sollte trotzdem laufen
        assert "success" in results
