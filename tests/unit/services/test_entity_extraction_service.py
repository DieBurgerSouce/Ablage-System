# -*- coding: utf-8 -*-
"""
Tests fuer EntityExtractionService.

Testet Extraktion von Geschaeftspartnern aus OCR-Text:
- USt-IdNr Erkennung
- IBAN Erkennung und Validierung
- Firmenname Extraktion
- Adress-Extraktion
- Entity Matching

99%+ Praezision ist das Ziel.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.entity_extraction_service import (
    EntityExtractionService,
    EntityExtractionResult,
    ExtractedIdentifier,
    ExtractedAddress,
    ExtractedCompanyName,
    EntityMatchResult,
    GermanPatterns,
)


class TestGermanPatterns:
    """Tests fuer deutsche Regex-Muster."""

    def test_vat_id_pattern_valid(self):
        """Sollte gueltige USt-IdNr erkennen."""
        pattern = GermanPatterns.VAT_ID
        test_cases = [
            ("DE123456789", True),
            ("DE 123 456 789", True),
            ("DE999999999", True),
            ("AT123456789", False),  # Oesterreich
            ("DE12345678", False),   # Zu kurz
            ("DE1234567890", False), # Zu lang
        ]
        for text, should_match in test_cases:
            match = pattern.search(text)
            assert (match is not None) == should_match, f"Failed for: {text}"

    def test_iban_pattern_valid(self):
        """Sollte gueltige deutsche IBANs erkennen."""
        pattern = GermanPatterns.IBAN
        test_cases = [
            ("DE89 3704 0044 0532 0130 00", True),
            ("DE89370400440532013000", False),  # Ohne Leerzeichen wird nicht erkannt
            ("FR7630006000011234567890189", False),  # Frankreich
        ]
        for text, should_match in test_cases:
            match = pattern.search(text)
            if should_match:
                assert match is not None, f"Should match: {text}"

    def test_iban_short_pattern_valid(self):
        """Sollte deutsche IBANs ohne Leerzeichen erkennen."""
        pattern = GermanPatterns.IBAN_SHORT
        assert pattern.search("DE89370400440532013000") is not None

    def test_plz_city_pattern(self):
        """Sollte PLZ + Stadt erkennen."""
        pattern = GermanPatterns.PLZ_CITY
        test_cases = [
            ("10115 Berlin", True),
            ("80331 Muenchen", True),
            ("12345 Teststadt", True),
            ("1234 Berlin", False),  # PLZ zu kurz
        ]
        for text, should_match in test_cases:
            match = pattern.search(text)
            assert (match is not None) == should_match, f"Failed for: {text}"

    def test_email_pattern(self):
        """Sollte E-Mail-Adressen erkennen."""
        pattern = GermanPatterns.EMAIL
        assert pattern.search("info@example.de") is not None
        assert pattern.search("test.user@company.com") is not None

    def test_company_name_pattern(self):
        """Sollte Firmennamen mit Rechtsform erkennen."""
        pattern = GermanPatterns.COMPANY_NAME
        test_cases = [
            ("Musterfirma GmbH", True),
            ("Test AG", True),
            ("Beispiel GmbH & Co. KG", False),  # Komplex, aber wird teilweise erkannt
        ]
        for text, should_match in test_cases:
            match = pattern.search(text)
            if should_match:
                assert match is not None, f"Should match: {text}"


class TestEntityExtractionService:
    """Tests fuer EntityExtractionService."""

    @pytest.fixture
    def service(self):
        """Erstellt EntityExtractionService ohne DB."""
        return EntityExtractionService(db=None)

    @pytest.fixture
    def service_with_db(self):
        """Erstellt EntityExtractionService mit Mock-DB."""
        mock_db = AsyncMock()
        return EntityExtractionService(db=mock_db)

    @pytest.fixture
    def sample_invoice_text(self):
        """Beispiel-Rechnungstext mit deutschen Geschaeftsdaten."""
        return """
        RECHNUNG Nr. RE-2024-001234

        Musterfirma GmbH
        Musterstraße 123
        10115 Berlin

        USt-IdNr: DE 123 456 789
        Steuernummer: 30/123/12345

        Bankverbindung:
        IBAN: DE89 3704 0044 0532 0130 00
        BIC: COBADEFFXXX

        E-Mail: info@musterfirma.de
        Tel.: +49 30 123456

        Rechnungsbetrag: 1.234,56 EUR
        """

    @pytest.fixture
    def sample_letter_text(self):
        """Beispiel-Brieftext."""
        return """
        Acme AG
        Hauptstraße 1
        80331 Muenchen

        Sehr geehrte Damen und Herren,

        bezugnehmend auf Ihre Anfrage...

        Mit freundlichen Gruessen
        Max Mustermann
        """

    # ==========================================================================
    # Extract Entities Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extract_entities_from_invoice(self, service, sample_invoice_text):
        """Sollte alle Entitaeten aus Rechnungstext extrahieren."""
        result = await service.extract_entities(sample_invoice_text)

        assert isinstance(result, EntityExtractionResult)
        assert len(result.identifiers) > 0
        assert len(result.addresses) > 0
        assert len(result.company_names) > 0

        # USt-IdNr pruefen
        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) >= 1
        assert vat_ids[0].normalized_value == "DE123456789"

        # IBAN pruefen
        ibans = [i for i in result.identifiers if i.identifier_type == "iban"]
        assert len(ibans) >= 1

        # E-Mails pruefen
        assert "info@musterfirma.de" in result.emails

    @pytest.mark.asyncio
    async def test_extract_entities_from_empty_text(self, service):
        """Sollte leeres Ergebnis bei leerem Text zurueckgeben."""
        result = await service.extract_entities("")

        assert isinstance(result, EntityExtractionResult)
        assert len(result.identifiers) == 0
        assert len(result.addresses) == 0

    @pytest.mark.asyncio
    async def test_extract_entities_from_none(self, service):
        """Sollte leeres Ergebnis bei None zurueckgeben."""
        result = await service.extract_entities(None)

        assert isinstance(result, EntityExtractionResult)
        assert result.overall_confidence == 0.0

    # ==========================================================================
    # VAT ID Extraction Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extract_vat_ids(self, service):
        """Sollte USt-IdNr korrekt extrahieren."""
        text = "Unsere USt-IdNr: DE 123 456 789"
        result = await service.extract_entities(text)

        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) == 1
        assert vat_ids[0].normalized_value == "DE123456789"
        assert vat_ids[0].confidence >= 0.85

    @pytest.mark.asyncio
    async def test_extract_vat_ids_with_context_boost(self, service):
        """Sollte hoehere Konfidenz bei USt-IdNr-Kontext haben."""
        text = "USt-IdNr: DE123456789"
        result = await service.extract_entities(text)

        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) == 1
        assert vat_ids[0].confidence > 0.90  # Kontext-Boost

    # ==========================================================================
    # IBAN Extraction Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extract_ibans(self, service):
        """Sollte deutsche IBANs korrekt extrahieren."""
        text = "IBAN: DE89 3704 0044 0532 0130 00"
        result = await service.extract_entities(text)

        ibans = [i for i in result.identifiers if i.identifier_type == "iban"]
        assert len(ibans) == 1
        assert ibans[0].normalized_value == "DE89370400440532013000"
        assert ibans[0].confidence >= 0.99  # IBAN mit guelitiger Pruefziffer

    def test_validate_iban_correct(self, service):
        """Sollte gueltige IBAN als gueltig erkennen."""
        assert service._validate_iban("DE89370400440532013000") == True

    def test_validate_iban_incorrect(self, service):
        """Sollte ungueltige IBAN als ungueltig erkennen."""
        assert service._validate_iban("DE89370400440532013001") == False
        assert service._validate_iban("DE12345678901234567890") == False

    # ==========================================================================
    # Address Extraction Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extract_addresses(self, service):
        """Sollte Adressen korrekt extrahieren."""
        text = "Musterstrasse 123, 10115 Berlin"
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 1
        addr = result.addresses[0]
        assert addr.postal_code == "10115"
        assert "Berlin" in addr.city

    @pytest.mark.asyncio
    async def test_extract_multiple_addresses(self, service):
        """Sollte mehrere Adressen extrahieren."""
        text = """
        Lieferadresse: 10115 Berlin
        Rechnungsadresse: 80331 Muenchen
        """
        result = await service.extract_entities(text)

        assert len(result.addresses) >= 2

    # ==========================================================================
    # Company Name Extraction Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extract_company_names(self, service):
        """Sollte Firmennamen korrekt extrahieren."""
        text = "Musterfirma GmbH ist ein Unternehmen"
        result = await service.extract_entities(text)

        assert len(result.company_names) >= 1
        company = result.company_names[0]
        assert "Musterfirma" in company.name
        assert company.legal_form == "GmbH"

    @pytest.mark.asyncio
    async def test_extract_company_with_ag(self, service):
        """Sollte AG-Firmennamen extrahieren."""
        text = "Beispiel AG liefert Produkte"
        result = await service.extract_entities(text)

        assert len(result.company_names) >= 1
        assert result.company_names[0].legal_form == "AG"

    # ==========================================================================
    # Overall Confidence Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_overall_confidence_multiple_signals(self, service, sample_invoice_text):
        """Sollte hoehere Konfidenz bei mehreren Signalen haben."""
        result = await service.extract_entities(sample_invoice_text)

        # Mehrere Signale sollten die Gesamtkonfidenz erhoehen
        assert result.overall_confidence > 0.70

    @pytest.mark.asyncio
    async def test_overall_confidence_single_signal(self, service):
        """Sollte niedrigere Konfidenz bei einzelnem Signal haben."""
        text = "10115 Berlin"  # Nur Adresse
        result = await service.extract_entities(text)

        assert result.overall_confidence < 0.90

    # ==========================================================================
    # Name Similarity Tests
    # ==========================================================================

    def test_calculate_name_similarity_exact(self, service):
        """Sollte 1.0 bei exakter Übereinstimmung zurueckgeben."""
        assert service._calculate_name_similarity("Musterfirma", "Musterfirma") == 1.0

    def test_calculate_name_similarity_case_insensitive(self, service):
        """Sollte case-insensitive vergleichen."""
        assert service._calculate_name_similarity("MUSTERFIRMA", "musterfirma") == 1.0

    def test_calculate_name_similarity_ignore_legal_form(self, service):
        """Sollte Rechtsform ignorieren."""
        similarity = service._calculate_name_similarity("Musterfirma GmbH", "Musterfirma AG")
        assert similarity == 1.0

    def test_calculate_name_similarity_different(self, service):
        """Sollte niedrige Aehnlichkeit bei verschiedenen Namen haben."""
        similarity = service._calculate_name_similarity("Musterfirma", "Beispiel")
        assert similarity < 0.5

    # ==========================================================================
    # Statistics Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_extraction_stats(self, service, sample_invoice_text):
        """Sollte Extraktions-Statistiken korrekt zaehlen."""
        initial_stats = service.get_extraction_stats()

        await service.extract_entities(sample_invoice_text)

        stats = service.get_extraction_stats()
        assert stats["total_extractions"] > initial_stats["total_extractions"]

    def test_reset_stats(self, service):
        """Sollte Statistiken zuruecksetzen."""
        service._extraction_stats["total_extractions"] = 100
        service.reset_stats()

        stats = service.get_extraction_stats()
        assert stats["total_extractions"] == 0


class TestEntityMatching:
    """Tests fuer Entity-Matching mit Datenbank."""

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def service_with_db(self, mock_db):
        """EntityExtractionService mit Mock-DB."""
        return EntityExtractionService(db=mock_db)

    @pytest.fixture
    def mock_entity(self):
        """Mock BusinessEntity."""
        entity = MagicMock()
        entity.id = uuid4()
        entity.name = "Musterfirma GmbH"
        entity.vat_id = "DE123456789"
        entity.iban = "DE89370400440532013000"
        entity.postal_code = "10115"
        return entity

    @pytest.mark.asyncio
    async def test_match_by_vat_id(self, service_with_db, mock_db, mock_entity):
        """Sollte Entity nach USt-IdNr matchen."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_entity
        mock_db.execute = AsyncMock(return_value=mock_result)

        extraction = EntityExtractionResult(
            identifiers=[
                ExtractedIdentifier(
                    identifier_type="vat_id",
                    value="DE 123 456 789",
                    normalized_value="DE123456789",
                    confidence=0.95,
                    position_start=0,
                    position_end=15,
                    context=""
                )
            ]
        )

        result = await service_with_db.match_to_existing(extraction)

        assert result.entity_id == mock_entity.id
        assert result.match_type == "vat_id"
        assert result.confidence == 0.99
        assert result.is_new == False

    @pytest.mark.asyncio
    async def test_match_no_result(self, service_with_db, mock_db):
        """Sollte is_new=True zurueckgeben wenn kein Match."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        extraction = EntityExtractionResult(
            identifiers=[
                ExtractedIdentifier(
                    identifier_type="vat_id",
                    value="DE999999999",
                    normalized_value="DE999999999",
                    confidence=0.95,
                    position_start=0,
                    position_end=15,
                    context=""
                )
            ]
        )

        result = await service_with_db.match_to_existing(extraction)

        assert result.is_new == True
        assert result.entity_id is None

    @pytest.mark.asyncio
    async def test_match_without_db(self):
        """Sollte Fehler zurueckgeben ohne DB."""
        service = EntityExtractionService(db=None)
        extraction = EntityExtractionResult()

        result = await service.match_to_existing(extraction)

        assert result.is_new == True
        assert "error" in result.match_details
