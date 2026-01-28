# -*- coding: utf-8 -*-
"""
Unit-Tests für Zero-Touch OCR Services.

Testet:
- Confidence Aggregation (high/medium/low confidence)
- Auto-Filing (folder assignment, entity matching)
- Business Object Creation (InvoiceTracking)
- Zero-Touch Orchestrator (full pipeline)
- Statistics and Metrics

Feinpoliert und durchdacht - Zero-Touch Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.zero_touch.confidence_aggregator import (
    ConfidenceAggregator,
    AggregatedConfidence,
    ConfidenceBreakdown,
    DEFAULT_WEIGHTS,
)
from app.services.zero_touch.auto_filing_service import (
    AutoFilingService,
    FilingResult,
    DEFAULT_FOLDER_MAPPING,
)
from app.services.zero_touch.business_object_factory import (
    BusinessObjectFactory,
    BusinessObjectResult,
)
from app.services.zero_touch.zero_touch_orchestrator import (
    ZeroTouchOrchestrator,
    ZeroTouchResult,
    ZeroTouchStats,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def sample_entity_id() -> UUID:
    """Provide sample entity UUID."""
    return uuid4()


@pytest.fixture
def sample_document_id() -> UUID:
    """Provide sample document UUID."""
    return uuid4()


@pytest.fixture
def sample_company_id() -> UUID:
    """Provide sample company UUID."""
    return uuid4()


# ========================= ConfidenceAggregator Tests =========================


class TestConfidenceAggregator:
    """Tests für Confidence Aggregation Service."""

    def test_confidence_aggregation_high_confidence(self):
        """Confidence > 0.9 sollte auto-processable sein."""
        # Arrange
        aggregator = ConfidenceAggregator(auto_threshold=0.90)

        # Act
        result = aggregator.aggregate(
            ocr_conf=0.95,
            class_conf=0.92,
            extract_conf=0.93,
            entity_conf=0.91,
        )

        # Assert
        assert result.auto_processable is True
        assert result.overall >= 0.90
        assert len(result.breakdown) == 4
        assert all(b.confidence >= 0.90 for b in result.breakdown)

    def test_confidence_aggregation_low_confidence(self):
        """Confidence < 0.7 sollte in Review Queue gehen."""
        # Arrange
        aggregator = ConfidenceAggregator(auto_threshold=0.90)

        # Act
        result = aggregator.aggregate(
            ocr_conf=0.65,
            class_conf=0.68,
            extract_conf=0.60,
            entity_conf=0.55,
        )

        # Assert
        assert result.auto_processable is False
        assert result.overall < 0.70
        assert result.threshold == 0.90

    def test_confidence_aggregation_medium_confidence(self):
        """Confidence 0.7-0.9 sollte Review triggern."""
        # Arrange
        aggregator = ConfidenceAggregator(auto_threshold=0.90)

        # Act
        result = aggregator.aggregate(
            ocr_conf=0.82,
            class_conf=0.85,
            extract_conf=0.78,
            entity_conf=0.80,
        )

        # Assert
        assert result.auto_processable is False
        assert 0.70 <= result.overall < 0.90

    def test_confidence_aggregation_without_entity(self):
        """Aggregation ohne Entity Confidence sollte funktionieren."""
        # Arrange
        aggregator = ConfidenceAggregator()

        # Act
        result = aggregator.aggregate(
            ocr_conf=0.95,
            class_conf=0.92,
            extract_conf=0.93,
            entity_conf=None,  # Kein Entity Matching
        )

        # Assert
        assert result is not None
        assert len(result.breakdown) == 3  # Nur OCR, Class, Extract
        # Gewichte sollten redistributed sein
        total_weight = sum(b.weight for b in result.breakdown)
        assert 0.99 <= total_weight <= 1.01

    def test_confidence_weights_sum_to_one(self):
        """Gewichtungen sollten zu 1.0 summieren."""
        # Arrange
        total = sum(DEFAULT_WEIGHTS.values())

        # Assert
        assert 0.99 <= total <= 1.01

    def test_update_threshold(self):
        """Threshold-Update sollte funktionieren."""
        # Arrange
        aggregator = ConfidenceAggregator(auto_threshold=0.90)

        # Act
        aggregator.update_threshold(0.85)

        result = aggregator.aggregate(
            ocr_conf=0.87,
            class_conf=0.86,
            extract_conf=0.88,
        )

        # Assert
        assert result.threshold == 0.85
        assert result.auto_processable is True  # 0.87 > 0.85

    def test_invalid_confidence_value(self):
        """Ungültige Confidence-Werte sollten ValueError werfen."""
        # Arrange
        aggregator = ConfidenceAggregator()

        # Act & Assert
        with pytest.raises(ValueError, match="Ungültiger Confidence-Wert"):
            aggregator.aggregate(
                ocr_conf=1.5,  # Invalid
                class_conf=0.9,
                extract_conf=0.9,
            )


# ========================= AutoFilingService Tests =========================


class TestAutoFilingService:
    """Tests für Auto-Filing Service."""

    @pytest.mark.asyncio
    async def test_auto_filing_assigns_folder(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Dokumente sollten korrektem Ordner zugewiesen werden."""
        # Arrange
        service = AutoFilingService()

        # Act
        result = await service.determine_filing(
            document_id=sample_document_id,
            classification_type="invoice",
            entity_id=None,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result is not None
        assert result.folder_name == "Rechnungen"
        assert result.confidence >= 0.80
        assert "Dokument vom Typ" in result.reason

    @pytest.mark.asyncio
    async def test_auto_filing_entity_matching(
        self, mock_db_session, sample_document_id, sample_entity_id, sample_company_id
    ):
        """Dokumente sollten mit Entity verknüpft werden."""
        # Arrange
        service = AutoFilingService()

        # Mock Entity
        mock_entity = Mock()
        mock_entity.id = sample_entity_id
        mock_entity.name = "Test GmbH"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_entity)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await service.determine_filing(
            document_id=sample_document_id,
            classification_type="invoice",
            entity_id=sample_entity_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result is not None
        assert result.folder_name == "Test GmbH"
        assert result.confidence >= 0.95
        assert "Geschaeftspartner" in result.reason

    @pytest.mark.asyncio
    async def test_auto_filing_unknown_type(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Unbekannte Dokumententypen sollten in 'Sonstiges' abgelegt werden."""
        # Arrange
        service = AutoFilingService()

        # Act
        result = await service.determine_filing(
            document_id=sample_document_id,
            classification_type="unknown_type",
            entity_id=None,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result is not None
        assert result.folder_name == "Sonstiges"
        assert "Unbekannter Dokumententyp" in result.reason


# ========================= BusinessObjectFactory Tests =========================


class TestBusinessObjectFactory:
    """Tests für Business Object Factory."""

    @pytest.mark.asyncio
    async def test_business_object_creation(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """InvoiceTracking sollte aus Extraktionsdaten erstellt werden."""
        # Arrange
        factory = BusinessObjectFactory()

        # Mock Document
        mock_document = Mock()
        mock_document.id = sample_document_id
        mock_document.filename = "rechnung.pdf"

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(side_effect=[mock_document, None])
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        extracted_fields = {
            "invoice_number": {"value": "RE-2024-001", "confidence": 0.95},
            "amount": {"value": "1250.50", "confidence": 0.92},
            "currency": {"value": "EUR", "confidence": 1.0},
            "due_date": {"value": "2024-12-31", "confidence": 0.88},
            "vendor_name": {"value": "Test GmbH", "confidence": 0.90},
        }

        # Act
        result = await factory.create_business_object(
            document_id=sample_document_id,
            classification_type="invoice",
            extracted_fields=extracted_fields,
            entity_id=None,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is True
        assert result.object_type == "invoice"
        assert result.object_id is not None

    @pytest.mark.asyncio
    async def test_business_object_creation_unknown_type(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Unbekannte Dokumententypen sollten Fehler zurückgeben."""
        # Arrange
        factory = BusinessObjectFactory()

        # Act
        result = await factory.create_business_object(
            document_id=sample_document_id,
            classification_type="unknown_type",
            extracted_fields={},
            entity_id=None,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is False
        assert "Unbekannter Dokumententyp" in result.error

    @pytest.mark.asyncio
    async def test_business_object_already_exists(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Existierendes InvoiceTracking sollte wiederverwendet werden."""
        # Arrange
        factory = BusinessObjectFactory()

        # Mock Document
        mock_document = Mock()
        mock_document.id = sample_document_id

        # Mock existing InvoiceTracking
        existing_invoice_id = uuid4()
        mock_invoice = Mock()
        mock_invoice.id = existing_invoice_id

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(side_effect=[mock_document, mock_invoice])
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await factory.create_business_object(
            document_id=sample_document_id,
            classification_type="invoice",
            extracted_fields={},
            entity_id=None,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is True
        assert result.object_id == existing_invoice_id


# ========================= ZeroTouchOrchestrator Tests =========================


class TestZeroTouchOrchestrator:
    """Tests für Zero-Touch Orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_full_pipeline(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Vollständige Pipeline sollte erfolgreich durchlaufen."""
        # Arrange
        orchestrator = ZeroTouchOrchestrator(confidence_threshold=0.90)

        # Mock Document
        mock_document = Mock()
        mock_document.id = sample_document_id
        mock_document.company_id = sample_company_id
        mock_document.status = "completed"
        mock_document.document_type = "invoice"
        mock_document.ocr_confidence = 0.95
        mock_document.business_entity_id = None
        mock_document.document_metadata = {
            "classification_confidence": 0.92,
            "extracted_fields": {
                "invoice_number": {"value": "RE-001", "confidence": 0.95},
                "amount": {"value": "1000.00", "confidence": 0.93},
            },
        }

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_document)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await orchestrator.process_document(
            document_id=sample_document_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is True
        assert result.document_id == sample_document_id
        assert result.overall_confidence >= 0.90
        assert result.auto_processable is True
        assert result.classification_type == "invoice"

    @pytest.mark.asyncio
    async def test_orchestrator_handles_ocr_failure(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """OCR-Fehler sollten graceful behandelt werden."""
        # Arrange
        orchestrator = ZeroTouchOrchestrator()

        # Mock Document mit pending Status
        mock_document = Mock()
        mock_document.id = sample_document_id
        mock_document.company_id = sample_company_id
        mock_document.status = "pending"  # OCR nicht abgeschlossen

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_document)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await orchestrator.process_document(
            document_id=sample_document_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is False
        assert "noch nicht abgeschlossen" in result.error_message

    @pytest.mark.asyncio
    async def test_zero_touch_statistics(
        self, mock_db_session, sample_company_id
    ):
        """Statistiken sollten korrekt berechnet werden."""
        # Arrange
        orchestrator = ZeroTouchOrchestrator()

        # Mock empty result
        mock_result = Mock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        stats = await orchestrator.get_stats(
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert stats.total_processed == 0
        assert stats.auto_processed == 0
        assert stats.auto_rate == 0.0
        assert stats.avg_confidence == 0.0
        assert stats.avg_processing_ms == 0
        assert stats.by_type == {}

    @pytest.mark.asyncio
    async def test_orchestrator_low_confidence_requires_review(
        self, mock_db_session, sample_document_id, sample_company_id
    ):
        """Niedrige Confidence sollte manuelles Review erfordern."""
        # Arrange
        orchestrator = ZeroTouchOrchestrator(confidence_threshold=0.90)

        # Mock Document mit niedriger Confidence
        mock_document = Mock()
        mock_document.id = sample_document_id
        mock_document.company_id = sample_company_id
        mock_document.status = "completed"
        mock_document.document_type = "invoice"
        mock_document.ocr_confidence = 0.65  # Niedrig
        mock_document.business_entity_id = None
        mock_document.document_metadata = {
            "classification_confidence": 0.60,
            "extracted_fields": {
                "invoice_number": {"value": "RE-001", "confidence": 0.55},
            },
        }

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_document)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await orchestrator.process_document(
            document_id=sample_document_id,
            company_id=sample_company_id,
            db=mock_db_session,
        )

        # Assert
        assert result.success is True
        assert result.auto_processable is False
        assert result.overall_confidence < 0.70
        assert result.business_object_created is False
