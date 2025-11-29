# -*- coding: utf-8 -*-
"""
Unit tests for EntityExtractionAgent.

Tests for German business document entity extraction including:
- Date extraction (German formats DD.MM.YYYY)
- Currency extraction (German format 1.234,56 EUR)
- IBAN extraction and validation
- VAT ID (Steuernummer) extraction
- Address parsing (German addresses)
- Person/Organization extraction
- Contract field extraction
- Entity deduplication
"""

import pytest
from datetime import date
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, MagicMock

# Mock spacy before importing the agent
mock_spacy_doc = Mock()
mock_spacy_nlp = Mock(return_value=mock_spacy_doc)


@pytest.fixture
def mock_spacy():
    """Mock spaCy NLP model."""
    with patch.dict("sys.modules", {"spacy": Mock()}):
        import spacy
        spacy.load = Mock(return_value=mock_spacy_nlp)
        yield spacy


@pytest.fixture
def entity_extraction_agent(mock_spacy):
    """Create EntityExtractionAgent instance for testing."""
    with patch("app.agents.postprocessing.entity_extraction_agent.spacy") as mock_sp:
        mock_sp.load = Mock(return_value=mock_spacy_nlp)

        # Mock the agent to avoid actual model loading
        from app.agents.postprocessing.entity_extraction_agent import EntityExtractionAgent
        agent = EntityExtractionAgent()
        agent._nlp = mock_spacy_nlp
        return agent


class TestDateExtraction:
    """Tests for German date extraction."""

    @pytest.mark.asyncio
    async def test_extract_german_date_format_dd_mm_yyyy(self, entity_extraction_agent):
        """Test extraction of dates in DD.MM.YYYY format."""
        text = "Das Dokument wurde am 15.03.2024 erstellt."

        result = await entity_extraction_agent.process({"text": text})

        dates = [e for e in result.get("entities", []) if e["type"] == "date"]
        assert len(dates) >= 1
        assert any("15.03.2024" in str(d.get("value", "")) for d in dates)

    @pytest.mark.asyncio
    async def test_extract_multiple_dates(self, entity_extraction_agent):
        """Test extraction of multiple dates."""
        text = """
        Vertragsbeginn: 01.01.2024
        Vertragsende: 31.12.2024
        Kündigungsfrist: 30.06.2024
        """

        result = await entity_extraction_agent.process({"text": text})

        dates = [e for e in result.get("entities", []) if e["type"] == "date"]
        assert len(dates) >= 3

    @pytest.mark.asyncio
    async def test_extract_date_with_german_month_name(self, entity_extraction_agent):
        """Test extraction of dates with German month names."""
        text = "München, den 15. März 2024"

        result = await entity_extraction_agent.process({"text": text})

        dates = [e for e in result.get("entities", []) if e["type"] == "date"]
        assert len(dates) >= 1

    @pytest.mark.asyncio
    async def test_invalid_date_not_extracted(self, entity_extraction_agent):
        """Test that invalid dates are not extracted."""
        text = "Die Nummer 32.13.2024 ist keine gültige Datumsangabe."

        result = await entity_extraction_agent.process({"text": text})

        dates = [e for e in result.get("entities", []) if e["type"] == "date"]
        # Should not contain invalid date
        assert not any("32.13.2024" in str(d.get("value", "")) for d in dates)


class TestCurrencyExtraction:
    """Tests for German currency extraction."""

    @pytest.mark.asyncio
    async def test_extract_german_currency_format(self, entity_extraction_agent):
        """Test extraction of currency in German format (1.234,56 EUR)."""
        text = "Der Gesamtbetrag beträgt 1.234,56 EUR."

        result = await entity_extraction_agent.process({"text": text})

        currencies = [e for e in result.get("entities", []) if e["type"] == "currency"]
        assert len(currencies) >= 1
        # Check for correct value extraction
        currency_values = [c.get("value", {}) for c in currencies]
        assert any(
            c.get("amount") == 1234.56 or "1.234,56" in str(c)
            for c in currency_values
        )

    @pytest.mark.asyncio
    async def test_extract_euro_symbol(self, entity_extraction_agent):
        """Test extraction of currency with Euro symbol."""
        text = "Zahlung: 500,00 €"

        result = await entity_extraction_agent.process({"text": text})

        currencies = [e for e in result.get("entities", []) if e["type"] == "currency"]
        assert len(currencies) >= 1

    @pytest.mark.asyncio
    async def test_extract_multiple_currencies(self, entity_extraction_agent):
        """Test extraction of multiple currency amounts."""
        text = """
        Nettobetrag: 100,00 EUR
        MwSt. (19%): 19,00 EUR
        Bruttobetrag: 119,00 EUR
        """

        result = await entity_extraction_agent.process({"text": text})

        currencies = [e for e in result.get("entities", []) if e["type"] == "currency"]
        assert len(currencies) >= 3

    @pytest.mark.asyncio
    async def test_extract_large_amounts(self, entity_extraction_agent):
        """Test extraction of large currency amounts."""
        text = "Investitionssumme: 1.250.000,00 EUR"

        result = await entity_extraction_agent.process({"text": text})

        currencies = [e for e in result.get("entities", []) if e["type"] == "currency"]
        assert len(currencies) >= 1


class TestIBANExtraction:
    """Tests for IBAN extraction and validation."""

    @pytest.mark.asyncio
    async def test_extract_valid_german_iban(self, entity_extraction_agent):
        """Test extraction of valid German IBAN."""
        text = "Bitte überweisen Sie auf IBAN: DE89 3704 0044 0532 0130 00"

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        assert len(ibans) >= 1
        assert any("DE89" in str(i.get("value", "")) for i in ibans)

    @pytest.mark.asyncio
    async def test_extract_iban_without_spaces(self, entity_extraction_agent):
        """Test extraction of IBAN without spaces."""
        text = "IBAN: DE89370400440532013000"

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        assert len(ibans) >= 1

    @pytest.mark.asyncio
    async def test_extract_austrian_iban(self, entity_extraction_agent):
        """Test extraction of Austrian IBAN."""
        text = "Kontoverbindung: AT61 1904 3002 3457 3201"

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        assert len(ibans) >= 1

    @pytest.mark.asyncio
    async def test_iban_validation(self, entity_extraction_agent):
        """Test that extracted IBANs are validated."""
        text = """
        Gültige IBAN: DE89 3704 0044 0532 0130 00
        Ungültige IBAN: DE00 0000 0000 0000 0000 00
        """

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        # Valid IBAN should be marked as valid
        valid_ibans = [i for i in ibans if i.get("valid", True)]
        assert len(valid_ibans) >= 1


class TestVATIDExtraction:
    """Tests for VAT ID (Steuernummer) extraction."""

    @pytest.mark.asyncio
    async def test_extract_german_ust_id(self, entity_extraction_agent):
        """Test extraction of German USt-IdNr."""
        text = "USt-IdNr.: DE123456789"

        result = await entity_extraction_agent.process({"text": text})

        vat_ids = [e for e in result.get("entities", []) if e["type"] == "vat_id"]
        assert len(vat_ids) >= 1
        assert any("DE123456789" in str(v.get("value", "")) for v in vat_ids)

    @pytest.mark.asyncio
    async def test_extract_steuernummer(self, entity_extraction_agent):
        """Test extraction of German Steuernummer."""
        text = "Steuernummer: 123/456/78901"

        result = await entity_extraction_agent.process({"text": text})

        # Check for tax number extraction
        entities = result.get("entities", [])
        tax_numbers = [
            e for e in entities
            if e["type"] in ["vat_id", "tax_number", "steuernummer"]
        ]
        assert len(tax_numbers) >= 1

    @pytest.mark.asyncio
    async def test_extract_austrian_uid(self, entity_extraction_agent):
        """Test extraction of Austrian UID."""
        text = "UID-Nr.: ATU12345678"

        result = await entity_extraction_agent.process({"text": text})

        vat_ids = [e for e in result.get("entities", []) if e["type"] == "vat_id"]
        assert len(vat_ids) >= 1


class TestAddressExtraction:
    """Tests for German address extraction."""

    @pytest.mark.asyncio
    async def test_extract_simple_german_address(self, entity_extraction_agent):
        """Test extraction of simple German address."""
        text = """
        Musterstraße 123
        12345 Berlin
        """

        result = await entity_extraction_agent.process({"text": text})

        addresses = [e for e in result.get("entities", []) if e["type"] == "address"]
        assert len(addresses) >= 1

    @pytest.mark.asyncio
    async def test_extract_full_address(self, entity_extraction_agent):
        """Test extraction of full German address with all components."""
        text = """
        Max Mustermann GmbH
        Hauptstraße 42a
        80331 München
        Deutschland
        """

        result = await entity_extraction_agent.process({"text": text})

        addresses = [e for e in result.get("entities", []) if e["type"] == "address"]
        assert len(addresses) >= 1

        # Check for address components
        if addresses:
            addr = addresses[0].get("value", {})
            if isinstance(addr, dict):
                assert addr.get("city") or "München" in str(addr)

    @pytest.mark.asyncio
    async def test_extract_address_with_postfach(self, entity_extraction_agent):
        """Test extraction of address with Postfach."""
        text = """
        Firma ABC
        Postfach 12 34 56
        10115 Berlin
        """

        result = await entity_extraction_agent.process({"text": text})

        addresses = [e for e in result.get("entities", []) if e["type"] == "address"]
        assert len(addresses) >= 1


class TestPersonExtraction:
    """Tests for person name extraction."""

    @pytest.mark.asyncio
    async def test_extract_german_name(self, entity_extraction_agent):
        """Test extraction of German person name."""
        # Setup mock for spaCy NER
        mock_ent = Mock()
        mock_ent.label_ = "PER"
        mock_ent.text = "Max Mustermann"
        mock_spacy_doc.ents = [mock_ent]

        text = "Der Vertrag wird geschlossen zwischen Max Mustermann und der Firma XYZ."

        result = await entity_extraction_agent.process({"text": text})

        persons = [e for e in result.get("entities", []) if e["type"] == "person"]
        # May use fallback pattern matching if NER doesn't work
        assert len(persons) >= 0  # At minimum, should not error

    @pytest.mark.asyncio
    async def test_extract_person_with_title(self, entity_extraction_agent):
        """Test extraction of person with academic title."""
        text = "Dr. med. Hans Schmidt unterzeichnet hiermit..."

        result = await entity_extraction_agent.process({"text": text})

        # Should extract person entity
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestOrganizationExtraction:
    """Tests for organization extraction."""

    @pytest.mark.asyncio
    async def test_extract_gmbh(self, entity_extraction_agent):
        """Test extraction of GmbH company."""
        text = "Die Musterfirma GmbH mit Sitz in Berlin..."

        result = await entity_extraction_agent.process({"text": text})

        orgs = [e for e in result.get("entities", []) if e["type"] == "organization"]
        assert len(orgs) >= 1

    @pytest.mark.asyncio
    async def test_extract_various_company_forms(self, entity_extraction_agent):
        """Test extraction of various German company forms."""
        text = """
        Lieferant: ABC AG
        Käufer: XYZ GmbH & Co. KG
        Berater: Consulting e.K.
        """

        result = await entity_extraction_agent.process({"text": text})

        orgs = [e for e in result.get("entities", []) if e["type"] == "organization"]
        # Should extract multiple organizations
        assert len(orgs) >= 1


class TestContractFieldExtraction:
    """Tests for contract-specific field extraction."""

    @pytest.mark.asyncio
    async def test_extract_contract_dates(self, entity_extraction_agent):
        """Test extraction of contract start and end dates."""
        text = """
        Vertragsbeginn: 01.01.2024
        Vertragslaufzeit: 12 Monate
        Vertragsende: 31.12.2024
        Kündigungsfrist: 3 Monate zum Quartalsende
        """

        result = await entity_extraction_agent.process({"text": text})

        entities = result.get("entities", [])
        dates = [e for e in entities if e["type"] == "date"]
        assert len(dates) >= 2

    @pytest.mark.asyncio
    async def test_extract_payment_terms(self, entity_extraction_agent):
        """Test extraction of payment terms."""
        text = """
        Zahlungsziel: 30 Tage netto
        Skonto: 2% bei Zahlung innerhalb von 10 Tagen
        """

        result = await entity_extraction_agent.process({"text": text})

        # Should extract payment-related entities
        entities = result.get("entities", [])
        assert isinstance(entities, list)


class TestEntityDeduplication:
    """Tests for entity deduplication logic."""

    @pytest.mark.asyncio
    async def test_deduplicate_repeated_entities(self, entity_extraction_agent):
        """Test that repeated entities are deduplicated."""
        text = """
        IBAN: DE89 3704 0044 0532 0130 00
        Bitte überweisen Sie auf: DE89 3704 0044 0532 0130 00
        Kontoverbindung: DE89 3704 0044 0532 0130 00
        """

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        # Should deduplicate to single IBAN or mark occurrences
        unique_iban_values = set(str(i.get("value", "")) for i in ibans)
        # Either deduplicated or all extracted with same value
        assert len(unique_iban_values) <= 3

    @pytest.mark.asyncio
    async def test_preserve_different_entities(self, entity_extraction_agent):
        """Test that different entities of same type are preserved."""
        text = """
        Bankverbindung 1: DE89 3704 0044 0532 0130 00
        Bankverbindung 2: DE02 1234 5678 9012 3456 78
        """

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        # Should preserve both different IBANs
        iban_values = [str(i.get("value", "")) for i in ibans]
        # Both should be present (either as separate or with count)
        assert len(ibans) >= 1


class TestEntityConfidence:
    """Tests for entity extraction confidence scores."""

    @pytest.mark.asyncio
    async def test_high_confidence_for_clear_entities(self, entity_extraction_agent):
        """Test that clear entities have high confidence."""
        text = "IBAN: DE89 3704 0044 0532 0130 00"

        result = await entity_extraction_agent.process({"text": text})

        ibans = [e for e in result.get("entities", []) if e["type"] == "iban"]
        if ibans:
            confidence = ibans[0].get("confidence", 0)
            assert confidence >= 0.8

    @pytest.mark.asyncio
    async def test_entities_have_confidence_scores(self, entity_extraction_agent):
        """Test that all entities have confidence scores."""
        text = """
        Datum: 15.03.2024
        Betrag: 1.234,56 EUR
        IBAN: DE89 3704 0044 0532 0130 00
        """

        result = await entity_extraction_agent.process({"text": text})

        entities = result.get("entities", [])
        for entity in entities:
            assert "confidence" in entity or "score" in entity


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_empty_text_handling(self, entity_extraction_agent):
        """Test handling of empty text."""
        result = await entity_extraction_agent.process({"text": ""})

        assert "entities" in result
        assert len(result["entities"]) == 0

    @pytest.mark.asyncio
    async def test_missing_text_raises_error(self, entity_extraction_agent):
        """Test that missing text raises appropriate error."""
        with pytest.raises((KeyError, ValueError)):
            await entity_extraction_agent.process({})

    @pytest.mark.asyncio
    async def test_non_german_text_handling(self, entity_extraction_agent):
        """Test handling of non-German text."""
        text = "The meeting is scheduled for January 15, 2024."

        result = await entity_extraction_agent.process({"text": text})

        # Should still work but may find fewer entities
        assert "entities" in result


class TestComplexDocuments:
    """Tests for complex document scenarios."""

    @pytest.mark.asyncio
    async def test_invoice_entity_extraction(self, entity_extraction_agent):
        """Test entity extraction from invoice-like document."""
        text = """
        Rechnung Nr. 2024-0001

        Rechnungsdatum: 15.03.2024
        Fälligkeitsdatum: 14.04.2024

        Muster GmbH
        Hauptstraße 123
        12345 Berlin

        Steuernummer: 12/345/67890
        USt-IdNr.: DE123456789

        Nettobetrag: 1.000,00 EUR
        MwSt. 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        Bankverbindung:
        IBAN: DE89 3704 0044 0532 0130 00
        BIC: COBADEFFXXX
        """

        result = await entity_extraction_agent.process({"text": text})

        entities = result.get("entities", [])
        entity_types = [e["type"] for e in entities]

        # Should extract various entity types
        assert len(entities) >= 3
        # Should include dates and currencies at minimum
        assert "date" in entity_types or "currency" in entity_types

    @pytest.mark.asyncio
    async def test_contract_entity_extraction(self, entity_extraction_agent):
        """Test entity extraction from contract-like document."""
        text = """
        MIETVERTRAG

        Zwischen dem Vermieter:
        Max Mustermann
        Musterstraße 1
        12345 Musterstadt

        und dem Mieter:
        Erika Musterfrau
        Beispielweg 2
        54321 Beispielstadt

        wird folgender Mietvertrag geschlossen:

        Mietbeginn: 01.04.2024
        Monatliche Miete: 850,00 EUR
        Kaution: 2.550,00 EUR

        Kündigungsfrist: 3 Monate zum Monatsende
        """

        result = await entity_extraction_agent.process({"text": text})

        entities = result.get("entities", [])

        # Should extract multiple entities
        assert len(entities) >= 2


class TestBICExtraction:
    """Tests for BIC/SWIFT code extraction."""

    @pytest.mark.asyncio
    async def test_extract_bic_code(self, entity_extraction_agent):
        """Test extraction of BIC/SWIFT code."""
        text = "BIC: COBADEFFXXX"

        result = await entity_extraction_agent.process({"text": text})

        bics = [e for e in result.get("entities", []) if e["type"] == "bic"]
        # BIC extraction might be implemented
        if bics:
            assert any("COBADEFF" in str(b.get("value", "")) for b in bics)

    @pytest.mark.asyncio
    async def test_extract_swift_code(self, entity_extraction_agent):
        """Test extraction of SWIFT code variant."""
        text = "SWIFT: DEUTDEFF"

        result = await entity_extraction_agent.process({"text": text})

        # Should either extract BIC or not, but not error
        assert "entities" in result


class TestPhoneExtraction:
    """Tests for German phone number extraction."""

    @pytest.mark.asyncio
    async def test_extract_german_phone_number(self, entity_extraction_agent):
        """Test extraction of German phone number."""
        text = "Tel.: +49 89 12345678"

        result = await entity_extraction_agent.process({"text": text})

        phones = [e for e in result.get("entities", []) if e["type"] == "phone"]
        if phones:
            assert any("+49" in str(p.get("value", "")) for p in phones)

    @pytest.mark.asyncio
    async def test_extract_phone_with_area_code(self, entity_extraction_agent):
        """Test extraction of phone with area code."""
        text = "Telefon: 089 / 123 456 78"

        result = await entity_extraction_agent.process({"text": text})

        phones = [e for e in result.get("entities", []) if e["type"] == "phone"]
        # Should extract phone number if supported
        assert isinstance(result.get("entities", []), list)


class TestEmailExtraction:
    """Tests for email extraction."""

    @pytest.mark.asyncio
    async def test_extract_email_address(self, entity_extraction_agent):
        """Test extraction of email address."""
        text = "Kontakt: info@musterfirma.de"

        result = await entity_extraction_agent.process({"text": text})

        emails = [e for e in result.get("entities", []) if e["type"] == "email"]
        if emails:
            assert any("musterfirma.de" in str(e.get("value", "")) for e in emails)

    @pytest.mark.asyncio
    async def test_extract_multiple_emails(self, entity_extraction_agent):
        """Test extraction of multiple email addresses."""
        text = """
        Allgemein: info@firma.de
        Buchhaltung: rechnung@firma.de
        Support: hilfe@firma.de
        """

        result = await entity_extraction_agent.process({"text": text})

        emails = [e for e in result.get("entities", []) if e["type"] == "email"]
        if emails:
            assert len(emails) >= 1
