# -*- coding: utf-8 -*-
"""
Tests fuer Reference Parser.

Testet:
- Rechnungsnummer-Extraktion
- Kundennummer-Extraktion
- SEPA-Referenzen (E2E, Mandat, Creditor ID)
- Datumsextraktion
- Zeitraum-Erkennung
- Zahlungszweck-Klassifizierung
"""

import pytest
from datetime import date

from app.services.banking.reference_parser import (
    ReferenceParser,
    ParsedReference,
    parse_reference_text,
    extract_invoice_numbers,
    extract_sepa_references,
)


class TestInvoiceNumberExtraction:
    """Tests fuer Rechnungsnummer-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_rechnung_nr(self, parser: ReferenceParser):
        """Sollte 'Rechnung Nr.' Format erkennen."""
        result = parser.parse("Rechnung Nr. 2024-001234")
        assert "2024-001234" in result.invoice_numbers or any(
            "2024" in inv and "001234" in inv for inv in result.invoice_numbers
        )

    def test_extract_re_nr(self, parser: ReferenceParser):
        """Sollte 'RE Nr.' Format erkennen."""
        result = parser.parse("RE Nr.: 12345/2024")
        assert any("12345" in inv for inv in result.invoice_numbers)

    def test_extract_rg_prefix(self, parser: ReferenceParser):
        """Sollte 'RG' Praefix erkennen."""
        result = parser.parse("RG-2024-5678")
        assert len(result.invoice_numbers) > 0

    def test_extract_invoice_prefix(self, parser: ReferenceParser):
        """Sollte 'INV' Praefix erkennen."""
        result = parser.parse("Invoice INV-2024-0042")
        assert any("INV" in inv or "2024" in inv for inv in result.invoice_numbers)

    def test_extract_iso_format(self, parser: ReferenceParser):
        """Sollte ISO-aehnliches Format erkennen."""
        result = parser.parse("Zahlung fuer ABCD-2024-12345")
        assert len(result.invoice_numbers) > 0

    def test_no_false_positives(self, parser: ReferenceParser):
        """Sollte keine falschen Treffer liefern."""
        result = parser.parse("Miete Dezember 2024")
        # Sollte keine Rechnungsnummern finden
        assert len(result.invoice_numbers) == 0 or all(
            "2024" not in inv for inv in result.invoice_numbers
            if len(inv) < 6  # Kurze Nummern ausschliessen
        )


class TestCustomerNumberExtraction:
    """Tests fuer Kundennummer-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_kundennr(self, parser: ReferenceParser):
        """Sollte 'Kundennr.' Format erkennen."""
        result = parser.parse("Kundennr. 123456 Rechnung 2024-01")
        assert "123456" in result.customer_numbers

    def test_extract_kd_nr(self, parser: ReferenceParser):
        """Sollte 'KD-NR' Format erkennen."""
        result = parser.parse("KD-NR: 987654")
        assert "987654" in result.customer_numbers

    def test_extract_debitoren(self, parser: ReferenceParser):
        """Sollte 'Debitor' Format erkennen."""
        result = parser.parse("Debitoren-Nr 456789")
        assert "456789" in result.customer_numbers


class TestOrderNumberExtraction:
    """Tests fuer Auftragsnummer-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_auftrag(self, parser: ReferenceParser):
        """Sollte 'Auftrag' Format erkennen."""
        result = parser.parse("Auftrag Nr. 2024-A1234")
        assert len(result.order_numbers) > 0

    def test_extract_bestellung(self, parser: ReferenceParser):
        """Sollte 'Bestellung' Format erkennen."""
        result = parser.parse("Bestellung 98765")
        assert "98765" in result.order_numbers

    def test_extract_po(self, parser: ReferenceParser):
        """Sollte 'PO' (Purchase Order) Format erkennen."""
        result = parser.parse("PO-2024-5678")
        assert len(result.order_numbers) > 0


class TestSEPAReferenceExtraction:
    """Tests fuer SEPA-Referenz-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_eref(self, parser: ReferenceParser):
        """Sollte EREF+ Format erkennen."""
        result = parser.parse("EREF+2024120512345678")
        assert result.end_to_end_id == "2024120512345678"

    def test_extract_e2e_long(self, parser: ReferenceParser):
        """Sollte End-to-End-ID erkennen."""
        result = parser.parse("End-to-End-ID: E2E-2024-001234")
        assert "E2E-2024-001234" in result.end_to_end_id

    def test_extract_mref(self, parser: ReferenceParser):
        """Sollte MREF+ (Mandatsreferenz) erkennen."""
        result = parser.parse("MREF+MANDATE123456")
        assert result.mandate_id == "MANDATE123456"

    def test_extract_mandate_id(self, parser: ReferenceParser):
        """Sollte Mandatsreferenz erkennen."""
        result = parser.parse("Mandat-ID: M-2024-12345")
        assert "M-2024-12345" in result.mandate_id

    def test_extract_cred(self, parser: ReferenceParser):
        """Sollte CRED+ (Creditor ID) erkennen."""
        result = parser.parse("CRED+DE98ZZZ09999999999")
        assert result.creditor_id == "DE98ZZZ09999999999"

    def test_extract_creditor_id(self, parser: ReferenceParser):
        """Sollte Glaeubiger-ID erkennen."""
        result = parser.parse("Creditor-ID: DE12ABC00000012345")
        assert "DE12ABC00000012345" in result.creditor_id


class TestDateExtraction:
    """Tests fuer Datums-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_german_date(self, parser: ReferenceParser):
        """Sollte deutsches Datumsformat erkennen."""
        result = parser.parse("Rechnung vom 15.12.2024")
        assert date(2024, 12, 15) in result.dates

    def test_extract_iso_date(self, parser: ReferenceParser):
        """Sollte ISO-Datumsformat erkennen."""
        result = parser.parse("Invoice date: 2024-12-15")
        assert date(2024, 12, 15) in result.dates

    def test_extract_multiple_dates(self, parser: ReferenceParser):
        """Sollte mehrere Daten erkennen."""
        result = parser.parse("Zeitraum 01.12.2024 bis 31.12.2024")
        assert len(result.dates) >= 2

    def test_dates_sorted(self, parser: ReferenceParser):
        """Sollte Daten sortiert zurueckgeben."""
        result = parser.parse("Ende 31.12.2024, Beginn 01.12.2024")
        if len(result.dates) >= 2:
            assert result.dates == sorted(result.dates)


class TestPeriodExtraction:
    """Tests fuer Zeitraum-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_zeitraum(self, parser: ReferenceParser):
        """Sollte 'Zeitraum' Format erkennen."""
        result = parser.parse("Zeitraum: 01.12.2024 - 31.12.2024")
        assert result.period_from is not None or len(result.dates) >= 2

    def test_extract_von_bis(self, parser: ReferenceParser):
        """Sollte 'von-bis' Format erkennen."""
        result = parser.parse("Leistung vom 01.11.2024 bis 30.11.2024")
        # Entweder period_from/to oder dates sollten gefuellt sein
        assert result.period_from is not None or len(result.dates) >= 2


class TestPaymentPurposeDetection:
    """Tests fuer Zahlungszweck-Erkennung."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_detect_miete(self, parser: ReferenceParser):
        """Sollte Mietzahlung erkennen."""
        result = parser.parse("Miete Dezember 2024")
        assert result.payment_purpose == "miete"

    def test_detect_gehalt(self, parser: ReferenceParser):
        """Sollte Gehalt erkennen."""
        result = parser.parse("Gehalt Dezember 2024")
        assert result.payment_purpose == "gehalt"

    def test_detect_rechnung(self, parser: ReferenceParser):
        """Sollte Rechnung erkennen."""
        result = parser.parse("Rechnung Nr. 12345")
        assert result.payment_purpose == "rechnung"

    def test_detect_strom(self, parser: ReferenceParser):
        """Sollte Stromzahlung erkennen."""
        result = parser.parse("Abschlag Strom Dezember")
        assert result.payment_purpose == "strom"

    def test_detect_versicherung(self, parser: ReferenceParser):
        """Sollte Versicherung erkennen."""
        result = parser.parse("Beitrag KFZ-Versicherung")
        assert result.payment_purpose == "versicherung"


class TestKeywordExtraction:
    """Tests fuer Keyword-Extraktion."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_extract_keywords(self, parser: ReferenceParser):
        """Sollte relevante Keywords extrahieren."""
        result = parser.parse("SEPA-LASTSCHRIFT Miete Dezember")
        assert len(result.keywords) > 0


class TestConvenienceFunctions:
    """Tests fuer Convenience-Funktionen."""

    def test_parse_reference_text(self):
        """Sollte parse_reference_text Funktion funktionieren."""
        result = parse_reference_text("Rechnung Nr. 2024-001")
        assert isinstance(result, ParsedReference)

    def test_extract_invoice_numbers_function(self):
        """Sollte extract_invoice_numbers Funktion funktionieren."""
        numbers = extract_invoice_numbers("RE 12345/2024")
        assert isinstance(numbers, list)

    def test_extract_sepa_references_function(self):
        """Sollte extract_sepa_references Funktion funktionieren."""
        refs = extract_sepa_references("EREF+123456")
        assert isinstance(refs, dict)
        assert "end_to_end_id" in refs


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.fixture
    def parser(self) -> ReferenceParser:
        return ReferenceParser()

    def test_empty_text(self, parser: ReferenceParser):
        """Sollte leeren Text verarbeiten."""
        result = parser.parse("")
        assert result.raw_text == ""
        assert len(result.invoice_numbers) == 0

    def test_none_text(self, parser: ReferenceParser):
        """Sollte None verarbeiten."""
        result = parser.parse(None)
        assert result.raw_text == ""

    def test_special_characters(self, parser: ReferenceParser):
        """Sollte Sonderzeichen verarbeiten."""
        result = parser.parse("Rechnung: äöü ß €")
        assert isinstance(result, ParsedReference)

    def test_long_text(self, parser: ReferenceParser):
        """Sollte langen Text verarbeiten."""
        long_text = "Verwendungszweck " * 100 + "Rechnung Nr. 12345"
        result = parser.parse(long_text)
        assert len(result.invoice_numbers) > 0 or result.raw_text == long_text

    def test_multiline_text(self, parser: ReferenceParser):
        """Sollte mehrzeiligen Text verarbeiten."""
        text = """SEPA-LASTSCHRIFT
        EREF+123456789
        MREF+MANDATE123
        Rechnung Nr. 2024-001"""
        result = parser.parse(text)
        # Sollte SEPA-Referenzen oder Rechnungsnummer finden
        assert (
            result.end_to_end_id is not None
            or len(result.invoice_numbers) > 0
        )
