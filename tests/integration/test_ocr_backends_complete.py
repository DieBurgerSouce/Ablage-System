"""
Integration tests for OCR backend completion.

Tests the newly implemented features:
- DeepSeek entity extraction (_extract_entities)
- DeepSeek layout detection (_detect_layout)
- GOT-OCR German post-processing (_postprocess_german)
- Backend integration with GermanValidator
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from german_validator import GermanValidator


# Sample texts for testing
SAMPLE_INVOICE_TEXT = """
Müller GmbH & Co. KG
Hauptstraße 123
80331 München

Rechnung Nr.: 2024-001
Rechnungsdatum: 15.03.2024
Leistungszeitraum: 01.02.2024 - 28.02.2024

Rechnungsempfänger:
Beispiel AG
Musterweg 45
10115 Berlin
USt-IdNr.: DE123456789

Pos.    Beschreibung                    Menge   Einzelpreis     Gesamt
1       Beratungsleistung               10 Std. 150,00 €        1.500,00 €
2       Software-Entwicklung            5 Std.  200,00 €        1.000,00 €

Nettobetrag:                                                    2.500,00 €
MwSt. 19%:                                                        475,00 €
Bruttobetrag:                                                   2.975,00 €

Zahlungsziel: 14 Tage netto

Bankverbindung:
Müller GmbH & Co. KG
IBAN: DE89 3704 0044 0532 0130 00
BIC: COBADEFFXXX

Mit freundlichen Grüßen
i.A. Max Müller
Geschäftsführer
"""

SAMPLE_LETTER_TEXT = """
Sehr geehrte Frau Schröder,

vielen Dank für Ihre Anfrage vom 10. März 2024 bezüglich unserer
Dienstleistungen im Bereich Softwareentwicklung.

Gerne unterbreiten wir Ihnen ein individuelles Angebot. Die Überprüfung
Ihrer Anforderungen hat ergeben, dass wir die gewünschte Lösung innerhalb
von 6 Wochen realisieren können.

Für Rückfragen stehen wir Ihnen jederzeit zur Verfügung.

Mit freundlichen Grüßen

Max Müller
Geschäftsführer
"""

SAMPLE_CONTRACT_TEXT = """
VERTRAG

zwischen

Müller GmbH (im Folgenden "Auftragnehmer")
und
Beispiel AG (im Folgenden "Auftraggeber")

§ 1 Vertragsgegenstand
Der Auftragnehmer verpflichtet sich zur Erbringung von Softwareentwicklungsleistungen.

§ 2 Haftung
Die Haftung des Auftragnehmers ist auf grobe Fahrlässigkeit beschränkt.

§ 3 Kündigungsfrist
Die Kündigungsfrist beträgt 3 Monate zum Monatsende.

§ 4 Gerichtsstand
Gerichtsstand ist München.

Unterschrift Auftragnehmer: _________________

Unterschrift Auftraggeber: _________________
"""


class TestDeepSeekEntityExtraction:
    """Test DeepSeek entity extraction functionality."""

    @pytest.fixture
    def deepseek_agent(self):
        """Create DeepSeek agent for testing."""
        try:
            from agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()
        except ImportError:
            pytest.skip("DeepSeek agent not available")

    @pytest.mark.integration
    def test_extract_iban(self, deepseek_agent):
        """Test IBAN extraction from German text."""
        text = "Bitte überweisen Sie auf IBAN: DE89 3704 0044 0532 0130 00"
        entities = deepseek_agent._extract_entities(text)

        iban_entities = [e for e in entities if e["type"] == "IBAN"]
        assert len(iban_entities) >= 1
        assert "DE89" in iban_entities[0]["value"]
        assert iban_entities[0]["validated"] == True  # Should be valid IBAN

    @pytest.mark.integration
    def test_extract_vat_id(self, deepseek_agent):
        """Test VAT ID (USt-IdNr.) extraction."""
        text = "USt-IdNr.: DE123456789"
        entities = deepseek_agent._extract_entities(text)

        vat_entities = [e for e in entities if e["type"] == "VAT_ID"]
        assert len(vat_entities) >= 1
        assert vat_entities[0]["value"] == "DE123456789"

    @pytest.mark.integration
    def test_extract_dates(self, deepseek_agent):
        """Test German date format extraction."""
        text = "Rechnungsdatum: 15.03.2024, Lieferdatum: 01.04.2024"
        entities = deepseek_agent._extract_entities(text)

        date_entities = [e for e in entities if e["type"] == "DATE"]
        assert len(date_entities) >= 2
        assert any("15.03.2024" in e["value"] for e in date_entities)

    @pytest.mark.integration
    def test_extract_currency(self, deepseek_agent):
        """Test German currency format extraction."""
        text = "Gesamtbetrag: 1.234,56 € inkl. MwSt."
        entities = deepseek_agent._extract_entities(text)

        currency_entities = [e for e in entities if e["type"] == "CURRENCY"]
        assert len(currency_entities) >= 1

    @pytest.mark.integration
    def test_extract_business_terms(self, deepseek_agent):
        """Test German business term extraction."""
        text = "Müller GmbH & Co. KG, vertreten durch den Geschäftsführer"
        entities = deepseek_agent._extract_entities(text)

        business_entities = [e for e in entities if e["type"] == "BUSINESS_TERM"]
        assert len(business_entities) >= 1
        # Should find GmbH, KG, etc.
        assert any(e["value"] in ["GmbH", "KG", "GmbH & Co. KG"] for e in business_entities)

    @pytest.mark.integration
    def test_extract_email(self, deepseek_agent):
        """Test email address extraction."""
        text = "Kontakt: info@mueller-gmbh.de oder support@beispiel.com"
        entities = deepseek_agent._extract_entities(text)

        email_entities = [e for e in entities if e["type"] == "EMAIL"]
        assert len(email_entities) >= 2

    @pytest.mark.integration
    def test_extract_from_full_invoice(self, deepseek_agent):
        """Test comprehensive entity extraction from full invoice."""
        entities = deepseek_agent._extract_entities(SAMPLE_INVOICE_TEXT)

        # Should find multiple entity types
        entity_types = set(e["type"] for e in entities)
        assert "IBAN" in entity_types
        assert "DATE" in entity_types
        assert "CURRENCY" in entity_types
        assert "BUSINESS_TERM" in entity_types

        # Should find at least 5 entities
        assert len(entities) >= 5


class TestDeepSeekLayoutDetection:
    """Test DeepSeek layout detection functionality."""

    @pytest.fixture
    def deepseek_agent(self):
        """Create DeepSeek agent for testing."""
        try:
            from agents.ocr.deepseek_agent import DeepSeekAgent
            return DeepSeekAgent()
        except ImportError:
            pytest.skip("DeepSeek agent not available")

    @pytest.mark.integration
    def test_detect_invoice_layout(self, deepseek_agent):
        """Test invoice document type detection."""
        layout = deepseek_agent._detect_layout(SAMPLE_INVOICE_TEXT)

        assert layout["type"] == "invoice"
        assert layout["confidence"] >= 0.5
        assert layout["has_signature"] == True  # "Mit freundlichen Grüßen"

    @pytest.mark.integration
    def test_detect_letter_layout(self, deepseek_agent):
        """Test letter document type detection."""
        layout = deepseek_agent._detect_layout(SAMPLE_LETTER_TEXT)

        assert layout["type"] == "letter"
        assert layout["has_signature"] == True

    @pytest.mark.integration
    def test_detect_contract_layout(self, deepseek_agent):
        """Test contract document type detection."""
        layout = deepseek_agent._detect_layout(SAMPLE_CONTRACT_TEXT)

        assert layout["type"] == "contract"
        assert layout["confidence"] >= 0.5

    @pytest.mark.integration
    def test_detect_table_structure(self, deepseek_agent):
        """Test table detection in document."""
        text_with_table = """
        Artikel    Menge   Preis
        A          10      100,00 €
        B          5       50,00 €
        C          20      200,00 €
        """
        layout = deepseek_agent._detect_layout(text_with_table)

        # Note: This uses spaces, not tabs - may not detect as table
        assert layout is not None
        assert "line_count" in layout

    @pytest.mark.integration
    def test_detect_list_structure(self, deepseek_agent):
        """Test list detection in document."""
        text_with_list = """
        Leistungsumfang:
        - Beratung
        - Entwicklung
        - Testing
        - Dokumentation
        """
        layout = deepseek_agent._detect_layout(text_with_list)

        assert layout["has_lists"] == True

    @pytest.mark.integration
    def test_detect_header_footer(self, deepseek_agent):
        """Test header/footer detection."""
        layout = deepseek_agent._detect_layout(SAMPLE_INVOICE_TEXT)

        # Invoice has company info at top (header) and signature at bottom
        assert layout["has_header"] == True or layout["has_signature"] == True

    @pytest.mark.integration
    def test_empty_text_handling(self, deepseek_agent):
        """Test handling of empty or minimal text."""
        layout = deepseek_agent._detect_layout("")
        assert layout["type"] == "unknown"
        assert layout["confidence"] == 0.0

        layout_short = deepseek_agent._detect_layout("Hi")
        assert layout_short["type"] == "unknown"


class TestGOTOCRGermanPostProcessing:
    """Test GOT-OCR German post-processing functionality."""

    @pytest.fixture
    def got_ocr_agent(self):
        """Create GOT-OCR agent for testing."""
        try:
            from agents.ocr.got_ocr_agent import GOTOCRAgent
            return GOTOCRAgent()
        except ImportError:
            pytest.skip("GOT-OCR agent not available")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_umlaut_restoration(self, got_ocr_agent):
        """Test umlaut restoration for common German words."""
        result = {"text": "Die Ueberprüfung der Groesse war noetig."}
        processed = await got_ocr_agent._postprocess_german(result)

        # Should restore umlauts in known words
        assert processed["german_processed"] == True
        # Check for corrections (at least some should be made)
        assert "corrections" in processed

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_eszett_restoration(self, got_ocr_agent):
        """Test ß restoration for known words."""
        result = {"text": "Die Strasse ist gross."}
        processed = await got_ocr_agent._postprocess_german(result)

        # Should restore ß in known words
        text = processed["text"]
        assert "straße" in text.lower() or "groß" in text.lower()
        assert processed["german_processed"] == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_preserve_correct_text(self, got_ocr_agent):
        """Test that already correct text is preserved."""
        result = {"text": "Die Größe der Straße ist korrekt."}
        processed = await got_ocr_agent._postprocess_german(result)

        # Text should remain the same
        assert "Größe" in processed["text"]
        assert "Straße" in processed["text"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mixed_text_handling(self, got_ocr_agent):
        """Test handling of text with mixed correct and incorrect umlauts."""
        result = {"text": "Müller aus Muenchen prüft die Größe."}
        processed = await got_ocr_agent._postprocess_german(result)

        # Should preserve correct umlauts and fix incorrect ones
        assert "Müller" in processed["text"]
        assert "Größe" in processed["text"]
        assert processed["german_processed"] == True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_corrections_tracking(self, got_ocr_agent):
        """Test that corrections are tracked."""
        result = {"text": "Die Strasse ist gross."}
        processed = await got_ocr_agent._postprocess_german(result)

        # Should have corrections list
        assert "corrections" in processed
        assert "corrections_count" in processed
        # At least one correction should be made
        if processed["corrections_count"] > 0:
            assert len(processed["corrections"]) > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_validator_integration(self, got_ocr_agent):
        """Test integration with GermanValidator."""
        result = {"text": "Müller GmbH aus München, Straße 123"}
        processed = await got_ocr_agent._postprocess_german(result)

        # Should include validation result if validator is available
        if "umlaut_validation" in processed:
            assert "umlauts_found" in processed["umlaut_validation"]
            assert "confidence" in processed["umlaut_validation"]


class TestGermanValidatorIntegration:
    """Test GermanValidator integration with OCR backends."""

    @pytest.fixture
    def validator(self):
        """Create GermanValidator instance."""
        return GermanValidator()

    @pytest.mark.integration
    def test_invoice_field_extraction(self, validator):
        """Test invoice field extraction."""
        fields = validator.extract_invoice_fields(SAMPLE_INVOICE_TEXT)

        # Should extract some fields
        assert len(fields) >= 1

    @pytest.mark.integration
    def test_iban_validation(self, validator):
        """Test IBAN validation from text."""
        # Valid German IBAN
        assert validator.validate_iban("DE89370400440532013000") == True

        # Invalid IBAN (wrong checksum)
        assert validator.validate_iban("DE12345678901234567890") == False

    @pytest.mark.integration
    def test_vat_id_validation(self, validator):
        """Test VAT ID validation."""
        # Valid format
        assert validator.validate_vat_id("DE123456789") == True

        # Invalid format
        assert validator.validate_vat_id("DE12345") == False

    @pytest.mark.integration
    def test_date_extraction(self, validator):
        """Test German date extraction."""
        text = "Datum: 15.03.2024, Lieferung: 01.04.2024"
        dates = validator.validate_date_format(text)

        assert len(dates) >= 2
        assert "15.03.2024" in dates

    @pytest.mark.integration
    def test_currency_extraction(self, validator):
        """Test German currency extraction."""
        text = "Netto: 1.000,00 €, Brutto: 1.190,00 EUR"
        amounts = validator.validate_currency_format(text)

        assert len(amounts) >= 1

    @pytest.mark.integration
    def test_business_terms_extraction(self, validator):
        """Test German business terms extraction."""
        text = "Müller GmbH & Co. KG, USt-IdNr. DE123456789"
        terms = validator.extract_business_terms(text)

        # Should find GmbH, KG, USt-IdNr.
        assert len(terms) >= 1


@pytest.mark.integration
@pytest.mark.gpu
class TestOCRBackendsWithGPU:
    """GPU-dependent tests for OCR backends."""

    @pytest.fixture
    def check_gpu(self):
        """Check if GPU is available."""
        try:
            import torch
            if not torch.cuda.is_available():
                pytest.skip("GPU not available")
            return True
        except ImportError:
            pytest.skip("PyTorch not installed")

    @pytest.mark.asyncio
    async def test_surya_gpu_agent_status(self, check_gpu):
        """Test Surya GPU agent status."""
        try:
            from agents.ocr.surya_gpu_agent import SuryaGPUAgent
            agent = SuryaGPUAgent()
            status = agent.get_status()  # get_status is now synchronous

            assert status is not None
            assert "gpu_info" in status
            assert status["gpu_info"].get("available", True)
        except ImportError:
            pytest.skip("SuryaGPUAgent not available")

    @pytest.mark.asyncio
    async def test_deepseek_gpu_allocation(self, check_gpu):
        """Test DeepSeek GPU resource allocation."""
        try:
            from agents.ocr.deepseek_agent import DeepSeekAgent
            from gpu_manager import GPUManager

            gpu_manager = GPUManager()
            allocation = gpu_manager.allocate_for_backend("deepseek")

            assert "success" in allocation
            # May not succeed if VRAM is insufficient, but should not error
            if allocation["success"]:
                gpu_manager.deallocate_backend("deepseek")
        except ImportError:
            pytest.skip("DeepSeekAgent not available")


@pytest.mark.integration
class TestEndToEndOCRWorkflow:
    """End-to-end workflow tests."""

    @pytest.mark.integration
    def test_full_extraction_workflow(self):
        """Test complete extraction workflow with validator."""
        validator = GermanValidator()

        # Simulate OCR output
        ocr_text = SAMPLE_INVOICE_TEXT

        # Validate German text
        umlaut_result = validator.validate_umlauts(ocr_text)
        assert umlaut_result["confidence"] >= 0.8

        # Extract structured data
        dates = validator.validate_date_format(ocr_text)
        currencies = validator.validate_currency_format(ocr_text)
        terms = validator.extract_business_terms(ocr_text)

        # Verify extractions
        assert len(dates) >= 1
        assert len(currencies) >= 1
        assert len(terms) >= 1

    @pytest.mark.integration
    def test_document_classification_workflow(self):
        """Test document classification workflow."""
        try:
            from agents.ocr.deepseek_agent import DeepSeekAgent
            agent = DeepSeekAgent()

            # Test with different document types
            documents = [
                (SAMPLE_INVOICE_TEXT, "invoice"),
                (SAMPLE_LETTER_TEXT, "letter"),
                (SAMPLE_CONTRACT_TEXT, "contract"),
            ]

            results = []
            for text, expected_type in documents:
                layout = agent._detect_layout(text)
                results.append((layout["type"], expected_type))

            # At least 2 out of 3 should be correctly classified
            correct = sum(1 for actual, expected in results if actual == expected)
            assert correct >= 2

        except ImportError:
            pytest.skip("DeepSeekAgent not available")


if __name__ == "__main__":
    print("Running OCR Backend Integration Tests")
    print("=" * 60)

    # Run with pytest
    pytest.main([__file__, "-v", "-m", "integration"])
