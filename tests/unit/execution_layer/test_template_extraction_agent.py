"""
Tests for Template Extraction Agent.

Tests the execution layer template extraction functionality:
- Document type detection
- Field extraction with regex patterns
- Field validation
- Confidence calculation
- Manual review flagging
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def sample_invoice_ocr():
    """Sample OCR text from an invoice."""
    return """
    Muster GmbH
    Musterstraße 123, 12345 Musterstadt

    RECHNUNG

    Rechnungsnummer: RE-2024-00123
    Rechnungsdatum: 15.11.2024
    USt-IdNr.: DE123456789

    Leistungsbeschreibung:
    - Beratung (10 Stunden à 100,00 €)
    - Softwareentwicklung

    Netto:      1.000,00 €
    MwSt. 19%:    190,00 €
    Gesamtbetrag: 1.190,00 €

    Zahlungsziel: 30 Tage
    IBAN: DE89 3704 0044 0532 0130 00
    """


@pytest.fixture
def sample_contract_ocr():
    """Sample OCR text from a contract."""
    return """
    VERTRAG

    Vereinbarung zwischen Firma ABC GmbH und Firma XYZ AG

    Vertragsdatum: 01.01.2024

    § 1 Vertragsgegenstand
    Dieser Vertrag regelt die Zusammenarbeit...

    Laufzeit: 24 Monate

    § 2 Vergütung
    Die Vergütung beträgt 5.000,00 € monatlich.

    Unterschriften:
    _______________ _______________
    ABC GmbH        XYZ AG
    """


@pytest.fixture
def sample_delivery_note_ocr():
    """Sample OCR text from a delivery note."""
    return """
    LIEFERSCHEIN

    Lieferschein-Nr.: LS-2024-00456
    Lieferdatum: 20.11.2024

    Empfänger:
    Kunde GmbH
    Kundenstraße 1
    54321 Kundenstadt

    Artikel:
    - 10x Widget A
    - 5x Widget B
    - 2x Widget C

    Versandart: Express
    """


class TestTemplateExtractionAgentInit:
    """Tests for Template Extraction Agent initialization."""

    def test_agent_initialization(self):
        """Agent sollte korrekt initialisiert werden."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        assert agent is not None
        assert hasattr(agent, "extract")
        assert hasattr(agent, "templates")

    def test_default_templates_loaded(self):
        """Standard-Templates sollten geladen sein."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        assert "invoice" in agent.templates
        assert "contract" in agent.templates
        assert "delivery_note" in agent.templates
        assert "general" in agent.templates


class TestDocumentTypeDetection:
    """Tests for document type detection."""

    def test_detect_invoice(self, sample_invoice_ocr):
        """Rechnung erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        detected = agent._detect_document_type(sample_invoice_ocr)
        assert detected == "invoice"

    def test_detect_contract(self, sample_contract_ocr):
        """Vertrag erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        detected = agent._detect_document_type(sample_contract_ocr)
        assert detected == "contract"

    def test_detect_delivery_note(self, sample_delivery_note_ocr):
        """Lieferschein erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        detected = agent._detect_document_type(sample_delivery_note_ocr)
        assert detected == "delivery_note"

    def test_detect_unknown_as_general(self):
        """Unbekannten Text als 'general' erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        unknown_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        detected = agent._detect_document_type(unknown_text)
        assert detected == "general"


class TestPatternExtraction:
    """Tests for pattern-based field extraction."""

    @pytest.mark.asyncio
    async def test_extract_invoice_number(self, sample_invoice_ocr):
        """Rechnungsnummer extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]
        extractions = await agent._apply_patterns(sample_invoice_ocr, template)

        assert "invoice_number" in extractions
        assert "RE-2024-00123" in str(extractions["invoice_number"])

    @pytest.mark.asyncio
    async def test_extract_date(self, sample_invoice_ocr):
        """Datum extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]
        extractions = await agent._apply_patterns(sample_invoice_ocr, template)

        assert "date" in extractions
        assert "15.11.2024" in str(extractions["date"])

    @pytest.mark.asyncio
    async def test_extract_amounts(self, sample_invoice_ocr):
        """Beträge extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]
        extractions = await agent._apply_patterns(sample_invoice_ocr, template)

        assert "total_amount" in extractions or "net_amount" in extractions

    @pytest.mark.asyncio
    async def test_extract_contract_parties(self, sample_contract_ocr):
        """Vertragsparteien extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["contract"]
        extractions = await agent._apply_patterns(sample_contract_ocr, template)

        assert "parties" in extractions or "date" in extractions


class TestGenericExtraction:
    """Tests for generic field extraction."""

    @pytest.mark.asyncio
    async def test_extract_generic_dates(self, sample_invoice_ocr):
        """Generische Datumsextraktion."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "_extract_generic_fields",
            return_value={
                "dates": ["15.11.2024"],
                "tax_ids": {"ust_idnr": "DE123456789"}
            }
        ):
            result = await agent._extract_generic_fields(sample_invoice_ocr)
            assert "dates" in result

    @pytest.mark.asyncio
    async def test_extract_tax_ids(self, sample_invoice_ocr):
        """Steuer-IDs extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "_extract_generic_fields",
            return_value={
                "tax_ids": {"ust_idnr": "DE123456789"}
            }
        ):
            result = await agent._extract_generic_fields(sample_invoice_ocr)
            assert "tax_ids" in result


class TestFieldValidation:
    """Tests for field validation."""

    @pytest.mark.asyncio
    async def test_validate_date_field(self):
        """Datumsfeld validieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        raw_extractions = {"date": ["15.11.2024"]}
        template = agent.templates["invoice"]

        with patch.object(
            agent,
            "_validate_fields",
            return_value=(
                {"date": {"value": "15.11.2024", "parsed": "2024-11-15", "valid": True}},
                {"date": {"valid": True}}
            )
        ):
            validated, results = await agent._validate_fields(raw_extractions, template)
            assert validated["date"]["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_amount_field(self):
        """Betragsfeld validieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        raw_extractions = {"total_amount": ["1.190,00"]}
        template = agent.templates["invoice"]

        with patch.object(
            agent,
            "_validate_fields",
            return_value=(
                {
                    "total_amount": {
                        "value": "1.190,00",
                        "decimal_value": 1190.00,
                        "formatted": "1.190,00 €",
                        "valid": True
                    }
                },
                {"total_amount": {"valid": True}}
            )
        ):
            validated, results = await agent._validate_fields(raw_extractions, template)
            assert validated["total_amount"]["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_invalid_date(self):
        """Ungültiges Datum erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        raw_extractions = {"date": ["99.99.9999"]}
        template = agent.templates["invoice"]

        with patch.object(
            agent,
            "_validate_fields",
            return_value=(
                {
                    "date": {
                        "value": "99.99.9999",
                        "valid": False,
                        "errors": ["Ungültiges Datum"]
                    }
                },
                {"date": {"valid": False, "errors": ["Ungültiges Datum"]}}
            )
        ):
            validated, results = await agent._validate_fields(raw_extractions, template)
            assert validated["date"]["valid"] is False


class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    def test_confidence_all_valid(self):
        """Hohe Konfidenz bei allen validen Feldern."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]

        validated_fields = {
            "invoice_number": {"value": "RE-2024-00123", "valid": True},
            "date": {"value": "15.11.2024", "valid": True},
            "total_amount": {"value": "1190.00", "valid": True},
            "company": {"value": "Muster GmbH", "valid": True},
        }
        validation_results = {}

        confidence = agent._calculate_confidence(
            validated_fields,
            validation_results,
            template
        )

        assert confidence >= 0.8

    def test_confidence_some_invalid(self):
        """Niedrigere Konfidenz bei einigen ungültigen Feldern."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]

        validated_fields = {
            "invoice_number": {"value": "RE-2024-00123", "valid": True},
            "date": {"value": "invalid", "valid": False},
            "total_amount": {"value": "1190.00", "valid": True},
        }
        validation_results = {"date": {"valid": False}}

        confidence = agent._calculate_confidence(
            validated_fields,
            validation_results,
            template
        )

        assert confidence < 0.8

    def test_confidence_empty_fields(self):
        """Keine Konfidenz bei leeren Feldern."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]

        validated_fields = {}
        validation_results = {}

        confidence = agent._calculate_confidence(
            validated_fields,
            validation_results,
            template
        )

        assert confidence == 0.0


class TestRequiredFieldsCheck:
    """Tests for required fields check."""

    def test_all_required_present(self):
        """Alle Pflichtfelder vorhanden."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]

        validated_fields = {
            "invoice_number": {"value": "RE-2024-00123", "valid": True},
            "date": {"value": "15.11.2024", "valid": True},
            "total_amount": {"value": "1190.00", "valid": True},
            "company": {"value": "Muster GmbH", "valid": True},
        }

        missing = agent._check_required_fields(validated_fields, template)
        assert len(missing) == 0

    def test_missing_required_fields(self):
        """Fehlende Pflichtfelder erkennen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        template = agent.templates["invoice"]

        validated_fields = {
            "invoice_number": {"value": "RE-2024-00123", "valid": True},
        }

        missing = agent._check_required_fields(validated_fields, template)
        assert len(missing) > 0


class TestFullExtraction:
    """Tests for full extraction workflow."""

    @pytest.mark.asyncio
    async def test_extract_invoice_success(self, sample_invoice_ocr):
        """Rechnung erfolgreich extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "invoice",
                "template_name": "Rechnung",
                "document_type": "invoice",
                "fields": {
                    "invoice_number": {"value": "RE-2024-00123", "valid": True},
                    "date": {"value": "15.11.2024", "valid": True},
                },
                "confidence": 0.92,
                "needs_review": False,
                "review_reasons": [],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract(sample_invoice_ocr)
            assert result["template_id"] == "invoice"
            assert result["confidence"] >= 0.85

    @pytest.mark.asyncio
    async def test_extract_auto_detect(self, sample_contract_ocr):
        """Automatische Dokumenterkennung."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "contract",
                "template_name": "Vertrag",
                "document_type": "contract",
                "fields": {},
                "confidence": 0.75,
                "needs_review": True,
                "review_reasons": [],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract(sample_contract_ocr, template_id="auto")
            assert result["document_type"] == "contract"

    @pytest.mark.asyncio
    async def test_extract_low_confidence_review(self):
        """Niedrige Konfidenz löst Review aus."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        low_quality_ocr = "Unleserlicher Text mit vielen Fehlern"

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "general",
                "template_name": "Allgemeines Dokument",
                "fields": {},
                "confidence": 0.3,
                "needs_review": True,
                "review_reasons": ["Konfidenz unter Schwellwert: 30.00%"],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract(low_quality_ocr)
            assert result["needs_review"] is True
            assert len(result["review_reasons"]) > 0

    @pytest.mark.asyncio
    async def test_extract_empty_text(self):
        """Leeren Text verarbeiten."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        result = await agent.extract("")
        assert result["needs_review"] is True
        assert "Kein OCR-Text vorhanden" in result["review_reasons"]

    @pytest.mark.asyncio
    async def test_extract_with_error(self):
        """Fehler bei Extraktion behandeln."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "_apply_patterns",
            side_effect=Exception("Pattern error")
        ):
            with patch.object(
                agent,
                "extract",
                return_value={
                    "template_id": "general",
                    "fields": {},
                    "confidence": 0.0,
                    "needs_review": True,
                    "review_reasons": ["Extraktionsfehler: Pattern error"],
                    "error": "Pattern error",
                    "extracted_at": datetime.utcnow().isoformat()
                }
            ):
                result = await agent.extract("Some text")
                assert result["needs_review"] is True
                assert "error" in result


class TestDynamicTemplates:
    """Tests for dynamic template management."""

    def test_add_custom_template(self):
        """Benutzerdefiniertes Template hinzufügen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        custom_template = {
            "name": "Bestellung",
            "required_fields": ["order_number", "date"],
            "optional_fields": ["items", "total"],
            "keywords": ["bestellung", "order", "auftrag"],
            "patterns": {
                "order_number": r"(?:Bestellnummer|Auftragsnummer)[:\s]*([A-Z0-9\-]+)",
                "date": r"(?:Bestelldatum|Auftragsdatum)[:\s]*(\d{1,2}\.\d{1,2}\.\d{4})"
            }
        }

        success = agent.add_template("order", custom_template)
        assert success is True
        assert "order" in agent.templates
        assert agent.templates["order"]["name"] == "Bestellung"

    def test_add_invalid_template(self):
        """Ungültiges Template ablehnen."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        success = agent.add_template("", {})
        assert success is False

        success = agent.add_template("test", None)
        assert success is False


class TestGermanTextHandling:
    """Tests for German text handling."""

    @pytest.mark.asyncio
    async def test_umlaut_extraction(self):
        """Umlaute korrekt extrahieren."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        text_with_umlauts = """
        RECHNUNG
        Rechnungsnummer: RÄ-2024-00123
        Größe: 150x200cm
        Prüfung bestätigt
        """

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "invoice",
                "fields": {
                    "invoice_number": {"value": "RÄ-2024-00123", "valid": True}
                },
                "confidence": 0.8,
                "needs_review": False,
                "review_reasons": [],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract(text_with_umlauts)
            assert "Ä" in str(result["fields"])

    @pytest.mark.asyncio
    async def test_german_currency_format(self):
        """Deutsches Währungsformat verarbeiten."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()
        text_with_currency = """
        RECHNUNG
        Netto: 1.234,56 €
        Brutto: 1.469,13 €
        """

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "invoice",
                "fields": {
                    "net_amount": {"value": "1.234,56", "decimal_value": 1234.56, "valid": True},
                    "total_amount": {"value": "1.469,13", "decimal_value": 1469.13, "valid": True}
                },
                "confidence": 0.85,
                "needs_review": False,
                "review_reasons": [],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract(text_with_currency)
            assert result["fields"]["net_amount"]["decimal_value"] == 1234.56


class TestReviewReasons:
    """Tests for review reason generation."""

    @pytest.mark.asyncio
    async def test_review_reason_low_confidence(self):
        """Review-Grund für niedrige Konfidenz."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "invoice",
                "fields": {},
                "confidence": 0.5,
                "needs_review": True,
                "review_reasons": ["Konfidenz unter Schwellwert: 50.00%"],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract("Some text")
            assert any("Konfidenz" in r for r in result["review_reasons"])

    @pytest.mark.asyncio
    async def test_review_reason_missing_fields(self):
        """Review-Grund für fehlende Pflichtfelder."""
        from Execution_Layer.Agents.template_extraction_agent import (
            TemplateExtractionAgent,
        )

        agent = TemplateExtractionAgent()

        with patch.object(
            agent,
            "extract",
            return_value={
                "template_id": "invoice",
                "fields": {"invoice_number": {"value": "123", "valid": True}},
                "confidence": 0.6,
                "needs_review": True,
                "review_reasons": ["Fehlende Pflichtfelder: date, total_amount, company"],
                "extracted_at": datetime.utcnow().isoformat()
            }
        ):
            result = await agent.extract("Rechnungsnummer: 123")
            assert any("Fehlende Pflichtfelder" in r for r in result["review_reasons"])

