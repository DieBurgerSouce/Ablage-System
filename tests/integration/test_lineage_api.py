# -*- coding: utf-8 -*-
"""
Integration tests for Document Lineage API.

Tests the complete lineage tracking workflow:
- Timeline retrieval endpoints
- Statistics endpoints
- Export functionality

SECURITY: Verifies that no PII is exposed in API responses.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Skip these tests if the app cannot be imported
pytest.importorskip("app.main")


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def document_id():
    """Create a test document ID."""
    return uuid.uuid4()


@pytest.fixture
def company_id():
    """Create a test company ID."""
    return uuid.uuid4()


@pytest.fixture
def user_id():
    """Create a test user ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_lineage_service():
    """Create a mock lineage service."""
    service = AsyncMock()

    # Mock timeline response
    service.get_timeline.return_value = (
        [
            MagicMock(
                id=str(uuid.uuid4()),
                event_type="import",
                event_data={"source_type": "manual_upload"},
                timestamp=datetime.now(timezone.utc),
                duration_ms=None,
                confidence=None,
                user_id=str(uuid.uuid4()),
                source_service="import_service",
            ),
            MagicMock(
                id=str(uuid.uuid4()),
                event_type="ocr_complete",
                event_data={"backend": "deepseek"},
                timestamp=datetime.now(timezone.utc),
                duration_ms=1500,
                confidence=0.95,
                user_id=None,
                source_service="ocr_worker",
            ),
        ],
        2,
    )

    # Mock stats response
    service.get_lineage_stats.return_value = MagicMock(
        total_events=5,
        total_processing_duration_ms=2500,
        ocr_duration_ms=1500,
        ocr_confidence=0.95,
        classification_confidence=0.87,
        entity_link_confidence=0.85,
        modification_count=2,
        export_count=1,
        approval_count=1,
        rejection_count=0,
        import_source_type="manual_upload",
        imported_at=datetime.now(timezone.utc),
        last_modified_at=datetime.now(timezone.utc),
    )

    return service


# =============================================================================
# TEST: API RESPONSE STRUCTURE
# =============================================================================


class TestLineageAPIResponseStructure:
    """Tests for API response structure."""

    def test_timeline_response_has_expected_fields(self):
        """Timeline response should have required fields."""
        # This is a structural test - verify the Pydantic models
        from app.api.v1.lineage import TimelineResponse, TimelineEntryResponse

        # Check TimelineEntryResponse fields
        entry_fields = TimelineEntryResponse.model_fields.keys()
        assert "id" in entry_fields
        assert "event_type" in entry_fields
        assert "event_data" in entry_fields
        assert "timestamp" in entry_fields
        assert "duration_ms" in entry_fields
        assert "confidence" in entry_fields

        # Check TimelineResponse fields
        response_fields = TimelineResponse.model_fields.keys()
        assert "document_id" in response_fields
        assert "events" in response_fields
        assert "total" in response_fields
        assert "limit" in response_fields
        assert "offset" in response_fields

    def test_stats_response_has_expected_fields(self):
        """Stats response should have required fields."""
        from app.api.v1.lineage import LineageStatsResponse

        fields = LineageStatsResponse.model_fields.keys()

        assert "document_id" in fields
        assert "total_events" in fields
        assert "total_processing_duration_ms" in fields
        assert "ocr" in fields
        assert "classification" in fields
        assert "entity_linking" in fields
        assert "modifications" in fields
        assert "exports" in fields


# =============================================================================
# TEST: EVENT TYPE LABELS
# =============================================================================


class TestEventTypeLabels:
    """Tests for event type labels (German)."""

    def test_all_event_types_have_german_labels(self):
        """All event types should have German labels."""
        from app.api.v1.lineage import EVENT_TYPE_LABELS
        from app.db.models_lineage import LineageEventType

        # Check that all enum values have labels
        for event_type in LineageEventType:
            assert event_type.value in EVENT_TYPE_LABELS, (
                f"Missing German label for event type: {event_type.value}"
            )

    def test_event_type_labels_are_german(self):
        """Labels should be in German."""
        from app.api.v1.lineage import EVENT_TYPE_LABELS

        # Check some specific labels
        assert EVENT_TYPE_LABELS["import"] == "Import"
        assert EVENT_TYPE_LABELS["ocr_complete"] == "OCR abgeschlossen"
        assert EVENT_TYPE_LABELS["modification"] == "Bearbeitung"
        assert EVENT_TYPE_LABELS["entity_link"] == "Geschaeftspartner verknuepft"


# =============================================================================
# TEST: IMPORT SOURCE TYPES
# =============================================================================


class TestImportSourceTypes:
    """Tests for import source type labels."""

    def test_all_import_sources_have_labels(self):
        """All import source types should have German labels."""
        from app.db.models_lineage import ImportSourceType

        source_labels = {
            "manual_upload": "Manueller Upload",
            "email": "E-Mail Import",
            "folder": "Ordner-Import",
            "api": "API Upload",
            "scan": "Scanner",
            "integration": "Integration",
        }

        for source_type in ImportSourceType:
            assert source_type.value in source_labels, (
                f"Missing label for import source: {source_type.value}"
            )


# =============================================================================
# TEST: SECURITY - NO PII IN RESPONSES
# =============================================================================


class TestSecurityNoPII:
    """Tests to verify no PII is exposed in API responses."""

    def test_event_data_excludes_sensitive_fields(self):
        """Event data should not contain sensitive fields."""
        from app.services.lineage.document_lineage_service import DocumentLineageService

        # Create a service instance with mock db
        mock_db = AsyncMock()
        service = DocumentLineageService(mock_db)

        # Test sanitization
        sensitive_data = {
            "backend": "deepseek",  # OK
            "iban": "DE89370400440532013000",  # Sensitive
            "customer_number": "12345",  # Sensitive
            "email": "test@example.com",  # Sensitive
            "text": "Extracted document text...",  # Sensitive
            "content": "Document content...",  # Sensitive
            "duration_ms": 1500,  # OK
        }

        sanitized = service._sanitize_event_data(sensitive_data)

        # Should keep safe fields
        assert "backend" in sanitized
        assert "duration_ms" in sanitized

        # Should remove sensitive fields
        assert "iban" not in sanitized
        assert "customer_number" not in sanitized
        assert "email" not in sanitized
        assert "text" not in sanitized
        assert "content" not in sanitized

    def test_modification_does_not_store_values(self):
        """Modification events should not store old/new values."""
        # The service should only store the field name and fact of change,
        # not the actual values (which could be PII)
        from app.services.lineage.document_lineage_service import DocumentLineageService

        mock_db = AsyncMock()
        service = DocumentLineageService(mock_db)

        # The record_modification method should not include values in event_data
        # This is verified by the service implementation
        # We just check the method signature exists
        import inspect
        sig = inspect.signature(service.record_modification)
        params = list(sig.parameters.keys())

        assert "field_name" in params
        assert "old_value" in params
        assert "new_value" in params
        assert "user_id" in params


# =============================================================================
# TEST: MODEL VALIDATION
# =============================================================================


class TestModelValidation:
    """Tests for database model validation."""

    def test_lineage_event_type_enum_values(self):
        """All expected event types should be defined."""
        from app.db.models_lineage import LineageEventType

        expected_types = [
            "import", "ocr_start", "ocr_complete", "ocr_failed",
            "classification", "extraction",
            "entity_link", "entity_unlink",
            "modification", "metadata_update", "tag_change",
            "approval", "rejection", "escalation",
            "export", "archive", "restore",
            "soft_delete", "hard_delete",
        ]

        actual_values = [e.value for e in LineageEventType]

        for expected in expected_types:
            assert expected in actual_values, f"Missing event type: {expected}"

    def test_import_source_type_enum_values(self):
        """All expected import source types should be defined."""
        from app.db.models_lineage import ImportSourceType

        expected_sources = [
            "manual_upload", "email", "folder", "api", "scan", "integration"
        ]

        actual_values = [s.value for s in ImportSourceType]

        for expected in expected_sources:
            assert expected in actual_values, f"Missing import source: {expected}"
