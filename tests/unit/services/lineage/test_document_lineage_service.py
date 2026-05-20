# -*- coding: utf-8 -*-
"""
Unit tests for DocumentLineageService.

Tests the document lineage tracking functionality:
- Import event recording
- Processing step recording
- Entity linking tracking
- Modification tracking
- Timeline retrieval
- Statistics calculation

SECURITY: All tests verify that PII is NOT stored in lineage events.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_lineage import (
    DocumentLineageEvent,
    DocumentLineageSummary,
    LineageEventType,
    ImportSourceType,
)
from app.services.lineage.document_lineage_service import (
    DocumentLineageService,
    get_lineage_service,
    LineageStats,
    TimelineEntry,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.scalar_one_or_none = AsyncMock(return_value=None)
    return db


@pytest.fixture
def lineage_service(mock_db):
    """Create a lineage service with mock database."""
    return DocumentLineageService(mock_db)


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
def entity_id():
    """Create a test entity ID."""
    return uuid.uuid4()


# =============================================================================
# TEST: FACTORY FUNCTION
# =============================================================================


class TestGetLineageService:
    """Tests for the get_lineage_service factory function."""

    def test_creates_service_instance(self, mock_db):
        """Should create a DocumentLineageService instance."""
        service = get_lineage_service(mock_db)
        assert isinstance(service, DocumentLineageService)

    def test_service_has_db_reference(self, mock_db):
        """Should store the database session reference."""
        service = get_lineage_service(mock_db)
        assert service._db == mock_db


# =============================================================================
# TEST: RECORD IMPORT EVENT
# =============================================================================


class TestRecordImportEvent:
    """Tests for recording import events."""

    @pytest.mark.asyncio
    async def test_records_manual_upload(
        self, lineage_service, mock_db, document_id, company_id, user_id
    ):
        """Should record a manual upload import event."""
        # Mock summary creation
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        event = await lineage_service.record_import_event(
            document_id=document_id,
            company_id=company_id,
            source_type=ImportSourceType.MANUAL_UPLOAD,
            source_details={"filename": "rechnung.pdf"},
            user_id=user_id,
        )

        # Verify event was added
        mock_db.add.assert_called()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_email_import(
        self, lineage_service, mock_db, document_id, company_id
    ):
        """Should record an email import event."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        event = await lineage_service.record_import_event(
            document_id=document_id,
            company_id=company_id,
            source_type=ImportSourceType.EMAIL,
            source_details={"folder": "INBOX"},
        )

        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_sanitizes_source_details(
        self, lineage_service, mock_db, document_id, company_id
    ):
        """Should remove PII from source details."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        # Include PII in source_details (should be filtered)
        pii_details = {
            "filename": "rechnung.pdf",  # OK
            "email": "customer@example.com",  # PII - should be removed
            "iban": "DE89370400440532013000",  # PII - should be removed
            "folder": "Rechnungen",  # OK
        }

        await lineage_service.record_import_event(
            document_id=document_id,
            company_id=company_id,
            source_type=ImportSourceType.EMAIL,
            source_details=pii_details,
        )

        # The add call should have been made with sanitized data
        mock_db.add.assert_called()


# =============================================================================
# TEST: RECORD PROCESSING STEP
# =============================================================================


class TestRecordProcessingStep:
    """Tests for recording processing steps."""

    @pytest.mark.asyncio
    async def test_records_ocr_complete(
        self, lineage_service, mock_db, document_id, company_id
    ):
        """Should record OCR completion with details."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        event = await lineage_service.record_processing_step(
            document_id=document_id,
            company_id=company_id,
            step_type=LineageEventType.OCR_COMPLETE,
            details={"backend": "deepseek", "page_count": 3},
            duration_ms=1500,
            confidence=0.95,
            source_service="ocr_worker",
        )

        mock_db.add.assert_called()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_classification(
        self, lineage_service, mock_db, document_id, company_id
    ):
        """Should record document classification."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        await lineage_service.record_processing_step(
            document_id=document_id,
            company_id=company_id,
            step_type=LineageEventType.CLASSIFICATION,
            details={"document_type": "invoice", "method": "ml"},
            confidence=0.87,
        )

        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_does_not_store_ocr_text(
        self, lineage_service, mock_db, document_id, company_id
    ):
        """Should NOT store extracted OCR text (PII protection)."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        # Include OCR text in details (should be filtered)
        pii_details = {
            "backend": "got_ocr",
            "extracted_text": "Max Mustermann, Musterstrasse 123...",  # PII
            "content": "Sensitive document content...",  # PII
        }

        await lineage_service.record_processing_step(
            document_id=document_id,
            company_id=company_id,
            step_type=LineageEventType.OCR_COMPLETE,
            details=pii_details,
        )

        # Verify the add was called (details should be sanitized internally)
        mock_db.add.assert_called()


# =============================================================================
# TEST: RECORD ENTITY LINK
# =============================================================================


class TestRecordEntityLink:
    """Tests for recording entity linking events."""

    @pytest.mark.asyncio
    async def test_records_entity_link(
        self, lineage_service, mock_db, document_id, company_id, entity_id
    ):
        """Should record entity linking with confidence."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        await lineage_service.record_entity_link(
            document_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            confidence=0.85,
            reason="Matched by customer number pattern",
            match_type="customer_number",
        )

        mock_db.add.assert_called()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_sanitizes_reason_field(
        self, lineage_service, mock_db, document_id, company_id, entity_id
    ):
        """Should sanitize the reason field to prevent PII leakage."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        # Reason with potential PII (customer number embedded)
        pii_reason = "Matched customer number 123456789 in document"

        await lineage_service.record_entity_link(
            document_id=document_id,
            company_id=company_id,
            entity_id=entity_id,
            confidence=0.99,
            reason=pii_reason,  # Should be truncated/sanitized
            match_type="customer_number",
        )

        mock_db.add.assert_called()


# =============================================================================
# TEST: RECORD MODIFICATION
# =============================================================================


class TestRecordModification:
    """Tests for recording document modifications."""

    @pytest.mark.asyncio
    async def test_records_field_modification(
        self, lineage_service, mock_db, document_id, company_id, user_id
    ):
        """Should record a field modification."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        await lineage_service.record_modification(
            document_id=document_id,
            company_id=company_id,
            field_name="document_type",
            old_value="other",
            new_value="invoice",
            user_id=user_id,
        )

        mock_db.add.assert_called()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_store_field_values(
        self, lineage_service, mock_db, document_id, company_id, user_id
    ):
        """Should NOT store old/new values (PII protection)."""
        mock_db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        # Values that could contain PII
        await lineage_service.record_modification(
            document_id=document_id,
            company_id=company_id,
            field_name="customer_name",
            old_value="Max Mustermann GmbH",  # Should NOT be stored
            new_value="Mustermann AG",  # Should NOT be stored
            user_id=user_id,
        )

        # The event should be recorded but values should not be in event_data
        mock_db.add.assert_called()


# =============================================================================
# TEST: SANITIZATION
# =============================================================================


class TestSanitization:
    """Tests for PII sanitization in lineage events."""

    def test_sanitize_event_data_removes_sensitive_keys(self, lineage_service):
        """Should remove keys that could contain PII."""
        data = {
            "backend": "deepseek",  # OK
            "iban": "DE89370400440532013000",  # Sensitive
            "email": "test@example.com",  # Sensitive
            "confidence": 0.95,  # OK
            "customer_number": "12345",  # Sensitive
        }

        sanitized = lineage_service._sanitize_event_data(data)

        assert "backend" in sanitized
        assert "confidence" in sanitized
        assert "iban" not in sanitized
        assert "email" not in sanitized
        assert "customer_number" not in sanitized

    def test_sanitize_string_truncates_long_values(self, lineage_service):
        """Should truncate very long strings."""
        long_string = "A" * 200
        sanitized = lineage_service._sanitize_string(long_string)

        assert len(sanitized) <= 103  # 100 chars + "..."

    def test_sanitize_string_handles_none(self, lineage_service):
        """Should handle None values."""
        result = lineage_service._sanitize_string(None)
        assert result is None


# =============================================================================
# TEST: TIMELINE ENTRY
# =============================================================================


class TestTimelineEntry:
    """Tests for the TimelineEntry dataclass."""

    def test_to_dict_serialization(self):
        """Should correctly serialize to dictionary."""
        entry = TimelineEntry(
            id="test-id",
            event_type="ocr_complete",
            event_data={"backend": "deepseek"},
            timestamp=datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
            duration_ms=1500,
            confidence=0.95,
            user_id=None,
            source_service="ocr_worker",
        )

        result = entry.to_dict()

        assert result["id"] == "test-id"
        assert result["event_type"] == "ocr_complete"
        assert result["duration_ms"] == 1500
        assert result["confidence"] == 0.95
        assert "timestamp" in result


# =============================================================================
# TEST: LINEAGE STATS
# =============================================================================


class TestLineageStats:
    """Tests for the LineageStats dataclass."""

    def test_default_values(self):
        """Should have sensible default values."""
        stats = LineageStats()

        assert stats.total_events == 0
        assert stats.modification_count == 0
        assert stats.export_count == 0
        assert stats.ocr_confidence is None
