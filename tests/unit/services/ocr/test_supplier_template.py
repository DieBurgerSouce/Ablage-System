# -*- coding: utf-8 -*-
"""
Unit Tests fuer SupplierTemplateService.

Testet:
- Template CRUD (Create, Read, Update, Delete)
- Template-Matching (Entity, Text-Anker, Header-Pattern)
- Template-basierte Extraktion (BoundingBox, Anker, Regex)
- Preprocessing-Schritte
- Feld-Validierung
- Statistiken
"""

import pytest
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ocr.supplier_template_service import (
    SupplierTemplateService,
    FieldDefinition,
    ExtractionResult,
    TemplateMatchResult,
    TemplateExtractionResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> SupplierTemplateService:
    """Erstelle Service-Instanz."""
    return SupplierTemplateService(db=mock_db)


@pytest.fixture
def mock_template() -> MagicMock:
    """Mock OCR-Template."""
    template = MagicMock()
    template.id = uuid.uuid4()
    template.entity_id = uuid.uuid4()
    template.company_id = uuid.uuid4()
    template.name = "Test Template"
    template.document_type = "invoice_incoming"
    template.matching_strategy = "combined"
    template.text_anchors = ["Müller GmbH", "Rechnungsnummer"]
    template.header_patterns = [r"Rechnung\s+Nr"]
    template.field_definitions = [
        {"name": "invoice_number", "type": "anchor_relative", "anchor_text": "Rechnungsnummer:"},
        {"name": "total_amount", "type": "regex", "regex_pattern": r"Gesamtbetrag:\s*([\d.,]+\s*€)"},
    ]
    template.is_active = True
    template.auto_apply = True
    template.is_verified = True
    template.usage_count = 10
    template.successful_extractions = 8
    template.failed_extractions = 2
    template.training_document_count = 5
    template.average_confidence = 0.85
    template.last_used_at = datetime.now(timezone.utc)
    template.version = 1
    return template


# =============================================================================
# Template CRUD Tests
# =============================================================================


class TestTemplateCRUD:
    """Tests fuer Template-Erstellung und -Verwaltung."""

    @pytest.mark.asyncio
    async def test_create_template(
        self, service: SupplierTemplateService, mock_db: AsyncMock
    ) -> None:
        """Template wird erstellt und in DB gespeichert."""
        entity_id = uuid.uuid4()
        company_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await service.create_template(
            entity_id=entity_id,
            company_id=company_id,
            user_id=user_id,
            name="Test Template",
            document_type="invoice_incoming",
            text_anchors=["Müller GmbH"],
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_template(
        self, service: SupplierTemplateService, mock_db: AsyncMock, mock_template: MagicMock
    ) -> None:
        """Template wird per ID abgerufen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.get_template(mock_template.id, mock_template.company_id)

        assert result is mock_template

    @pytest.mark.asyncio
    async def test_get_template_not_found(
        self, service: SupplierTemplateService, mock_db: AsyncMock
    ) -> None:
        """Nicht existentes Template ergibt None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_template(uuid.uuid4(), uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_template(
        self, service: SupplierTemplateService, mock_db: AsyncMock, mock_template: MagicMock
    ) -> None:
        """Template wird soft-deleted (is_active = False)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.delete_template(mock_template.id, mock_template.company_id)

        assert result is True
        assert mock_template.is_active is False

    @pytest.mark.asyncio
    async def test_delete_template_not_found(
        self, service: SupplierTemplateService, mock_db: AsyncMock
    ) -> None:
        """Loeschen eines nicht existenten Templates ergibt False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.delete_template(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_update_template(
        self, service: SupplierTemplateService, mock_db: AsyncMock, mock_template: MagicMock
    ) -> None:
        """Template wird aktualisiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.update_template(
            mock_template.id, mock_template.company_id,
            name="Neuer Name",
            description="Beschreibung",
        )

        assert result is not None
        assert mock_template.name == "Neuer Name"

    @pytest.mark.asyncio
    async def test_update_template_version_increment(
        self, service: SupplierTemplateService, mock_db: AsyncMock, mock_template: MagicMock
    ) -> None:
        """Version wird bei Feld-Aenderungen erhoeht."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result
        old_version = mock_template.version

        await service.update_template(
            mock_template.id, mock_template.company_id,
            field_definitions=[{"name": "new_field"}],
        )

        assert mock_template.version == old_version + 1


# =============================================================================
# Extraction Tests
# =============================================================================


class TestFieldExtraction:
    """Tests fuer Feld-Extraktion."""

    @pytest.mark.asyncio
    async def test_extract_by_anchor(self, service: SupplierTemplateService) -> None:
        """Extraktion per Anker-Text."""
        field_def = {
            "name": "invoice_number",
            "type": "anchor_relative",
            "anchor_text": "Rechnungsnummer:",
        }
        ocr_result = {
            "full_text": "Rechnungsnummer: RE-2024-001\nDatum: 15.03.2024",
        }

        value, confidence = service._extract_by_anchor(field_def, ocr_result)

        assert value == "RE-2024-001"
        assert confidence > 0.0

    @pytest.mark.asyncio
    async def test_extract_by_anchor_not_found(
        self, service: SupplierTemplateService
    ) -> None:
        """Extraktion per Anker-Text wenn Anker nicht gefunden."""
        field_def = {
            "name": "invoice_number",
            "type": "anchor_relative",
            "anchor_text": "XYZ-Anker:",
        }
        ocr_result = {"full_text": "Rechnungsnummer: RE-2024-001"}

        value, confidence = service._extract_by_anchor(field_def, ocr_result)

        assert value is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_by_regex(self, service: SupplierTemplateService) -> None:
        """Extraktion per Regex-Pattern."""
        field_def = {
            "name": "total_amount",
            "type": "regex",
            "regex_pattern": r"Gesamtbetrag:\s*([\d.,]+\s*€)",
        }
        ocr_result = {
            "full_text": "Netto: 100,00 €\nGesamtbetrag: 119,00 €",
        }

        value, confidence = service._extract_by_regex(field_def, ocr_result)

        assert value is not None
        assert "119,00" in value
        assert confidence > 0.0

    @pytest.mark.asyncio
    async def test_extract_by_regex_no_match(
        self, service: SupplierTemplateService
    ) -> None:
        """Regex ohne Treffer ergibt None."""
        field_def = {
            "name": "field",
            "type": "regex",
            "regex_pattern": r"NICHT_VORHANDEN:\s*(\d+)",
        }
        ocr_result = {"full_text": "Normaler Text"}

        value, confidence = service._extract_by_regex(field_def, ocr_result)

        assert value is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_by_bounding_box(
        self, service: SupplierTemplateService
    ) -> None:
        """Extraktion per Bounding Box."""
        field_def = {
            "name": "field",
            "type": "bounding_box",
            "coordinates": {"x": 100, "y": 200, "width": 200, "height": 30},
        }
        ocr_result = {
            "blocks": [
                {"text": "RE-2024", "coordinates": {"x": 120, "y": 210}, "confidence": 0.9},
            ],
        }

        value, confidence, coords = service._extract_by_bounding_box(field_def, ocr_result)

        assert value == "RE-2024"
        assert confidence > 0.0

    @pytest.mark.asyncio
    async def test_extract_by_bounding_box_no_coords(
        self, service: SupplierTemplateService
    ) -> None:
        """Extraktion ohne Koordinaten ergibt None."""
        field_def = {"name": "field", "type": "bounding_box"}
        ocr_result = {"blocks": []}

        value, confidence, coords = service._extract_by_bounding_box(field_def, ocr_result)

        assert value is None


# =============================================================================
# Preprocessing Tests
# =============================================================================


class TestPreprocessing:
    """Tests fuer Preprocessing-Schritte."""

    def test_trim(self, service: SupplierTemplateService) -> None:
        """Trim entfernt Leerzeichen."""
        assert service._apply_preprocessing("  hello  ", ["trim"]) == "hello"

    def test_uppercase(self, service: SupplierTemplateService) -> None:
        """Uppercase konvertiert zu Grossbuchstaben."""
        assert service._apply_preprocessing("hello", ["uppercase"]) == "HELLO"

    def test_lowercase(self, service: SupplierTemplateService) -> None:
        """Lowercase konvertiert zu Kleinbuchstaben."""
        assert service._apply_preprocessing("HELLO", ["lowercase"]) == "hello"

    def test_remove_prefix(self, service: SupplierTemplateService) -> None:
        """remove_prefix entfernt Praefix."""
        result = service._apply_preprocessing("RE-2024", ["remove_prefix:RE-"])
        assert result == "2024"

    def test_remove_suffix(self, service: SupplierTemplateService) -> None:
        """remove_suffix entfernt Suffix."""
        result = service._apply_preprocessing("100,00€", ["remove_suffix:€"])
        assert result == "100,00"

    def test_extract_number(self, service: SupplierTemplateService) -> None:
        """extract_number extrahiert nur Zahlen."""
        result = service._apply_preprocessing("Preis: 19,99 €", ["extract_number"])
        assert result == "19,99"

    def test_normalize_german_number(self, service: SupplierTemplateService) -> None:
        """normalize_german_number konvertiert deutsches Zahlenformat."""
        result = service._apply_preprocessing(
            "1.234,56", ["normalize_german_number"]
        )
        assert result == "1234.56"

    def test_multiple_steps(self, service: SupplierTemplateService) -> None:
        """Mehrere Preprocessing-Schritte werden sequentiell angewendet."""
        result = service._apply_preprocessing(
            "  HELLO  ", ["trim", "lowercase"]
        )
        assert result == "hello"


# =============================================================================
# Template Matching Tests
# =============================================================================


class TestTemplateMatching:
    """Tests fuer Template-Matching."""

    @pytest.mark.asyncio
    async def test_no_templates_available(
        self, service: SupplierTemplateService, mock_db: AsyncMock
    ) -> None:
        """Kein Match wenn keine Templates vorhanden."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        result = await service.find_matching_template(
            document_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
        )

        assert result.matched is False

    @pytest.mark.asyncio
    async def test_match_score_calculation(
        self, service: SupplierTemplateService, mock_template: MagicMock
    ) -> None:
        """Match-Score wird korrekt berechnet."""
        entity_id = mock_template.entity_id
        ocr_text = "Müller GmbH\nRechnungsnummer: RE-001\nRechnung Nr 123"

        score, strategy, details = await service._calculate_match_score(
            mock_template, ocr_text, entity_id
        )

        assert score > 0.0
        assert details["entity_match"] is True

    @pytest.mark.asyncio
    async def test_match_score_no_entity(
        self, service: SupplierTemplateService, mock_template: MagicMock
    ) -> None:
        """Match-Score ohne Entity-Match."""
        score, strategy, details = await service._calculate_match_score(
            mock_template, "Müller GmbH", uuid.uuid4()  # Andere Entity
        )

        assert details["entity_match"] is False
        # Score kommt nur aus text_anchors
        assert score >= 0.0


# =============================================================================
# DataClass Tests
# =============================================================================


class TestDataClasses:
    """Tests fuer Datenklassen."""

    def test_field_definition(self) -> None:
        """FieldDefinition hat korrekte Defaults."""
        fd = FieldDefinition(name="test", label="Test", extraction_type="regex")
        assert fd.page == 1
        assert fd.required is False
        assert fd.confidence_boost == 0.0

    def test_extraction_result(self) -> None:
        """ExtractionResult wird korrekt erstellt."""
        result = ExtractionResult(
            field_name="invoice_number",
            value="RE-001",
            confidence=0.9,
            source="template",
        )
        assert result.validation_passed is True
        assert result.raw_value is None

    def test_template_match_result_no_match(self) -> None:
        """TemplateMatchResult fuer keinen Treffer."""
        result = TemplateMatchResult(matched=False)
        assert result.template is None
        assert result.confidence == 0.0

    def test_template_extraction_result(self) -> None:
        """TemplateExtractionResult wird korrekt erstellt."""
        result = TemplateExtractionResult(
            template_id=uuid.uuid4(),
            template_name="Test",
            match_confidence=0.9,
            extractions=[],
            overall_confidence=0.85,
            used_template=True,
            fields_extracted=3,
            fields_failed=1,
            processing_time_ms=50,
        )
        assert result.used_template is True
        assert result.fields_extracted == 3
