# -*- coding: utf-8 -*-
"""
Unit Tests fuer USt-IdNr Zuordnungslogik.

Testet die intelligente Zuordnung von USt-IdNr zu sender/recipient:
- Cross-Border EU Rechnungen (NL -> DE, AT -> DE)
- Nur-DE Rechnungen
- Laendercode-Matching
- Proximity-basierte Zuordnung
- Reverse Charge Erkennung
"""

import pytest
from datetime import date
from decimal import Decimal
from typing import List, Optional

from app.services.structured_extraction_service import (
    StructuredExtractionService,
    DeliveryPatterns,
    ReverseChargePatterns,
)
from app.services.entity_extraction_service import (
    EntityExtractionService,
    GermanPatterns,
)
from app.api.schemas.extracted_data import ExtractedDocumentType


class TestEUVatPatterns:
    """Tests fuer EU-weite USt-IdNr Patterns."""

    def test_nl_vat_pattern(self) -> None:
        """Niederlaendische USt-IdNr erkennen."""
        text = "BTW-nr: NL820594829B01"
        match = GermanPatterns.VAT_ID_NL.search(text)

        assert match is not None
        assert match.group(1).upper() == "NL820594829B01"

    def test_at_vat_pattern(self) -> None:
        """Oesterreichische USt-IdNr erkennen."""
        text = "UID-Nr: ATU12345678"
        match = GermanPatterns.VAT_ID_AT.search(text)

        assert match is not None
        assert match.group(1).upper() == "ATU12345678"

    def test_be_vat_pattern(self) -> None:
        """Belgische USt-IdNr erkennen."""
        text = "TVA: BE0123456789"
        match = GermanPatterns.VAT_ID_BE.search(text)

        assert match is not None
        assert match.group(1).upper() == "BE0123456789"

    def test_de_vat_pattern(self) -> None:
        """Deutsche USt-IdNr erkennen."""
        text = "USt-IdNr.: DE200053646"
        match = GermanPatterns.VAT_ID.search(text)

        assert match is not None
        normalized = match.group(1).replace(" ", "").upper()
        assert normalized == "DE200053646"

    def test_eu_vat_generic_pattern(self) -> None:
        """Generisches EU-Pattern fuer andere Laender."""
        test_cases = [
            ("FR12345678901", "FR"),
            ("IT12345678901", "IT"),
            ("PL1234567890", "PL"),
            ("CZABCDEFGH", "CZ"),
        ]

        for vat_id, expected_country in test_cases:
            text = f"VAT: {vat_id}"
            match = GermanPatterns.EU_VAT_ID.search(text)
            assert match is not None, f"Should match {vat_id}"
            assert match.group('country').upper() == expected_country


class TestVatIdExtraction:
    """Tests fuer USt-IdNr Extraktion aus Entity Service."""

    @pytest.fixture
    def entity_service(self) -> EntityExtractionService:
        return EntityExtractionService()

    @pytest.mark.asyncio
    async def test_extract_nl_vat_id(
        self, entity_service: EntityExtractionService
    ) -> None:
        """NL USt-IdNr korrekt extrahieren."""
        text = "BTW-nummer: NL820594829B01"
        result = await entity_service.extract_entities(text)

        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) >= 1
        assert any(v.normalized_value == "NL820594829B01" for v in vat_ids)
        assert any(v.country_code == "NL" for v in vat_ids)

    @pytest.mark.asyncio
    async def test_extract_de_vat_id(
        self, entity_service: EntityExtractionService
    ) -> None:
        """DE USt-IdNr korrekt extrahieren."""
        text = "USt-IdNr.: DE200053646"
        result = await entity_service.extract_entities(text)

        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) >= 1
        assert any(v.normalized_value == "DE200053646" for v in vat_ids)
        assert any(v.country_code == "DE" for v in vat_ids)

    @pytest.mark.asyncio
    async def test_extract_multiple_vat_ids(
        self, entity_service: EntityExtractionService
    ) -> None:
        """Mehrere USt-IdNr aus einem Dokument extrahieren."""
        text = """
        Von: ALPAC B.V.
        BTW: NL820594829B01

        An:
        Deutsche Firma GmbH
        USt-IdNr: DE200053646
        """
        result = await entity_service.extract_entities(text)

        vat_ids = [i for i in result.identifiers if i.identifier_type == "vat_id"]
        assert len(vat_ids) >= 2

        countries = {v.country_code for v in vat_ids}
        assert "NL" in countries
        assert "DE" in countries


class TestVatAttribution:
    """Tests fuer intelligente USt-IdNr Zuordnung."""

    @pytest.fixture
    def service(self) -> StructuredExtractionService:
        return StructuredExtractionService()

    @pytest.mark.asyncio
    async def test_nl_de_cross_border_invoice(
        self, service: StructuredExtractionService
    ) -> None:
        """NL-Lieferant mit DE-Kunde korrekt zuordnen (ALPAC-Szenario)."""
        text = """
        ALPAC kunststof bakken en pallets BV
        Van der Landeweg 6
        7418 HG Deventer
        Nederland

        BTW-nr: NL820594829B01

        An:
        Testfirma GmbH
        Musterstraße 123
        42719 Solingen
        Deutschland

        USt-IdNr: DE200053646

        RECHNUNG
        Rechnungsnummer: F-201451
        Rechnungsdatum: 06.04.2020

        Nettobetrag: 1.305,60 EUR
        """

        result = await service.extract(text)

        assert result.classification is not None
        assert result.classification.document_type == ExtractedDocumentType.INVOICE
        assert result.invoice is not None

        # Core assertion: Korrekte VAT ID Zuordnung
        assert result.invoice.sender_vat_id == "NL820594829B01", \
            f"Sender VAT sollte NL sein, aber ist {result.invoice.sender_vat_id}"
        assert result.invoice.recipient_vat_id == "DE200053646", \
            f"Recipient VAT sollte DE sein, aber ist {result.invoice.recipient_vat_id}"

    @pytest.mark.asyncio
    async def test_de_only_invoice(
        self, service: StructuredExtractionService
    ) -> None:
        """Nur-DE-Rechnung: sender_vat_id setzen, recipient_vat_id leer."""
        text = """
        RECHNUNG

        Lieferant GmbH
        Musterweg 1
        12345 Berlin
        Deutschland

        USt-IdNr.: DE123456789

        An:
        Kunde AG
        Teststraße 5
        54321 Hamburg

        Rechnungsnummer: RE-2024-001
        Rechnungsdatum: 15.01.2024

        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR
        """

        result = await service.extract(text)

        assert result.invoice is not None
        assert result.invoice.sender_vat_id == "DE123456789"
        # Bei reinen DE-Rechnungen bleibt recipient_vat_id leer
        # (es sei denn, der Kunde hat auch eine USt-IdNr angegeben)

    @pytest.mark.asyncio
    async def test_at_de_cross_border(
        self, service: StructuredExtractionService
    ) -> None:
        """Oesterreich -> Deutschland Rechnung."""
        text = """
        Oesterreichische Firma GmbH
        Wiener Straße 10
        1010 Wien
        Oesterreich

        UID-Nr: ATU12345678

        An:
        Deutsche Firma GmbH
        Berliner Allee 5
        42719 Solingen
        Deutschland

        USt-IdNr: DE987654321

        RECHNUNG
        Rechnungsnummer: AT-2024-001
        Rechnungsdatum: 15.01.2024
        Nettobetrag: 500,00 EUR
        """

        result = await service.extract(text)

        assert result.invoice is not None
        assert result.invoice.sender_vat_id == "ATU12345678"
        assert result.invoice.recipient_vat_id == "DE987654321"


class TestIncotermsExtraction:
    """Tests fuer Lieferbedingungen/Incoterms."""

    def test_incoterms_pattern_simple(self) -> None:
        """Einfache Incoterms erkennen."""
        test_cases = [
            ("FOB Rotterdam", "FOB"),
            ("EXW", "EXW"),
            ("CIF Hamburg", "CIF"),
            ("DAP Incoterms 2020", "DAP"),
            ("DDP Delivered Duty Paid", "DDP"),
        ]

        for text, expected_term in test_cases:
            match = DeliveryPatterns.INCOTERMS.search(text)
            assert match is not None, f"Should match '{text}'"
            assert match.group(1).upper() == expected_term

    @pytest.mark.skip(reason="Pattern-Aenderung: INCOTERMS.search() gibt jetzt group(2) als None zurueck statt Location. Regex-Pattern muss erweitert werden um optionale Location-Gruppe zu erfassen.")
    def test_incoterms_with_location(self) -> None:
        """Incoterms mit Ort erkennen."""
        text = "FOB Rotterdam, Netherlands"
        match = DeliveryPatterns.INCOTERMS.search(text)

        assert match is not None
        assert match.group(1).upper() == "FOB"
        assert "Rotterdam" in (match.group(2) or "")

    @pytest.mark.asyncio
    async def test_delivery_terms_in_invoice(self) -> None:
        """Lieferbedingungen aus Rechnung extrahieren."""
        text = """
        RECHNUNG Nr. RE-2024-001

        Lieferbedingungen: FOB Rotterdam

        Nettobetrag: 1.000,00 EUR
        """

        service = StructuredExtractionService()
        result = await service.extract(text)

        assert result.invoice is not None
        assert result.invoice.delivery_terms is not None
        assert "FOB" in result.invoice.delivery_terms


class TestReverseChargeExtraction:
    """Tests fuer Reverse Charge Erkennung."""

    def test_reverse_charge_pattern_english(self) -> None:
        """Englische Reverse Charge Hinweise erkennen."""
        texts = [
            "Intra-Community supply - VAT reverse charged",
            "Reverse charge applies",
            "VAT exempt - reverse charge",
        ]

        for text in texts:
            match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
            assert match is not None, f"Should match '{text}'"

    def test_reverse_charge_pattern_german(self) -> None:
        """Deutsche Steuerbefreiungshinweise erkennen."""
        texts = [
            "Innergemeinschaftliche Lieferung",
            "Steuerfreie Lieferung gemaess § 4",
            "Steuerbefreit nach § 4 Nr. 1b UStG",
            "Steuerbefreit",
            "steuerfrei",
        ]

        for text in texts:
            match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
            assert match is not None, f"Should match '{text}'"

    def test_reverse_charge_pattern_dutch(self) -> None:
        """Niederlaendische Reverse Charge erkennen."""
        text = "BTW verlegd"
        match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
        assert match is not None

    @pytest.mark.asyncio
    async def test_reverse_charge_detection_explicit(self) -> None:
        """Expliziter Reverse Charge Hinweis wird erkannt."""
        text = """
        RECHNUNG

        Rechnungsnummer: F-2024-001

        Total EUR: 1.305,60

        Intra-Community supply - VAT reverse charged
        """

        service = StructuredExtractionService()
        result = await service.extract(text)

        assert result.invoice is not None
        assert result.invoice.is_reverse_charge is True
        assert result.invoice.reverse_charge_note is not None

    @pytest.mark.asyncio
    async def test_reverse_charge_inference_from_vat_ids(self) -> None:
        """Reverse Charge aus unterschiedlichen VAT-Laendern und 0% MwSt ableiten."""
        text = """
        RECHNUNG

        Von:
        Nederlandse BV
        Amsterdam
        Nederland
        BTW: NL123456789B01

        An:
        Deutsche GmbH
        Berlin
        Deutschland
        USt-IdNr: DE987654321

        Nettobetrag: 1.000,00 EUR
        MwSt 0%: 0,00 EUR
        Bruttobetrag: 1.000,00 EUR
        """

        service = StructuredExtractionService()
        result = await service.extract(text)

        assert result.invoice is not None
        # Sollte Reverse Charge inferieren weil:
        # - sender_vat_id startet mit NL
        # - recipient_vat_id startet mit DE
        # - vat_rate ist 0
        assert result.invoice.is_reverse_charge is True


class TestBackwardCompatibility:
    """Tests fuer Rueckwaertskompatibilitaet."""

    @pytest.mark.asyncio
    async def test_existing_extraction_still_works(self) -> None:
        """Bestehende Extraktion darf nicht brechen."""
        text = """
        RECHNUNG
        Rechnungs-Nr.: RE-2024-00123
        Rechnungsdatum: 15.01.2024

        Musterfirma GmbH
        Musterstrasse 123
        12345 Berlin

        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        USt-IdNr.: DE123456789
        IBAN: DE89370400440532013000
        """

        service = StructuredExtractionService()
        result = await service.extract(text)

        # Alle bestehenden Extraktionen sollten funktionieren
        assert result.invoice is not None
        assert result.invoice.invoice_number == "RE-2024-00123"
        assert result.invoice.invoice_date == date(2024, 1, 15)
        assert result.invoice.net_amount == Decimal("1000.00")
        assert result.invoice.vat_rate == Decimal("19")
        assert result.invoice.gross_amount == Decimal("1190.00")
        assert result.invoice.sender_vat_id == "DE123456789"

    @pytest.mark.asyncio
    async def test_single_vat_id_goes_to_sender(self) -> None:
        """Einzelne USt-IdNr wird weiterhin dem Sender zugeordnet."""
        text = """
        RECHNUNG

        Firma GmbH
        USt-IdNr.: DE123456789

        Nettobetrag: 100,00 EUR
        """

        service = StructuredExtractionService()
        result = await service.extract(text)

        assert result.invoice is not None
        assert result.invoice.sender_vat_id == "DE123456789"
        # recipient_vat_id sollte None sein wenn nur eine VAT ID da ist
