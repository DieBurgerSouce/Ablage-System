# -*- coding: utf-8 -*-
"""
Erweiterte Unit Tests fuer StructuredExtractionService.

Ergaenzende Tests fuer:
- HTML-Sanitization
- Waehrungserkennung
- Reverse-Charge-Erkennung
- Incoterms-Extraktion
- Company-Name-Bereinigung
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.structured_extraction_service import (
    StructuredExtractionService,
    sanitize_extracted_text,
    PaymentPatterns,
    AmountPatterns,
    ReferencePatterns,
    DatePatterns,
    DeliveryPatterns,
    ReverseChargePatterns,
    CurrencyPatterns,
    COUNTRY_NAME_TO_CODE,
)
from app.api.schemas.extracted_data import (
    ExtractedDocumentType,
    Currency,
)


class TestHTMLSanitization:
    """Tests fuer HTML-Bereinigung."""

    def test_sanitize_removes_html_tags(self) -> None:
        """HTML-Tags werden entfernt."""
        text = "<b>Rechnungsnummer</b>: RE-2024-001"
        result = sanitize_extracted_text(text)

        assert result == "Rechnungsnummer: RE-2024-001"
        assert "<b>" not in result
        assert "</b>" not in result

    def test_sanitize_removes_self_closing_tags(self) -> None:
        """Selbstschliessende Tags werden entfernt."""
        text = "Zeile 1<br/>Zeile 2"
        result = sanitize_extracted_text(text)

        assert "<br/>" not in result
        assert "Zeile 1" in result
        assert "Zeile 2" in result

    def test_sanitize_replaces_nbsp(self) -> None:
        """nbsp wird zu Leerzeichen."""
        text = "Betrag:&nbsp;1.000,00&nbsp;EUR"
        result = sanitize_extracted_text(text)

        assert "&nbsp;" not in result
        assert "Betrag:" in result
        assert "EUR" in result

    def test_sanitize_replaces_common_entities(self) -> None:
        """Gaengige HTML-Entities werden ersetzt."""
        text = "M&amp;A &lt;10&gt; &quot;Test&quot;"
        result = sanitize_extracted_text(text)

        assert result == 'M&A <10> "Test"'

    def test_sanitize_handles_none(self) -> None:
        """None wird zu None."""
        result = sanitize_extracted_text(None)
        assert result is None

    def test_sanitize_handles_empty_string(self) -> None:
        """Leerer String wird zu None."""
        result = sanitize_extracted_text("")
        assert result is None

    def test_sanitize_normalizes_whitespace(self) -> None:
        """Mehrfache Leerzeichen werden normalisiert."""
        text = "Betrag:    1.000,00    EUR"
        result = sanitize_extracted_text(text)

        assert "    " not in result
        assert "Betrag: 1.000,00 EUR" == result


class TestCurrencyPatterns:
    """Tests fuer Waehrungserkennung."""

    def test_detect_eur_symbol(self) -> None:
        """Euro-Symbol erkennen."""
        text = "Betrag: 1.000,00 EUR"
        match = CurrencyPatterns.CURRENCY.search(text)

        assert match is not None
        assert match.group(1).upper() == "EUR"

    def test_detect_euro_sign(self) -> None:
        """Euro-Zeichen erkennen."""
        text = "Betrag: 1.000,00 EUR"
        match = CurrencyPatterns.CURRENCY.search(text)

        assert match is not None

    def test_detect_usd_symbol(self) -> None:
        """USD erkennen."""
        text = "Total: $1,000.00 USD"
        match = CurrencyPatterns.CURRENCY.search(text)

        assert match is not None

    def test_detect_gbp_symbol(self) -> None:
        """GBP erkennen."""
        text = "Amount: GBP 500.00"
        match = CurrencyPatterns.CURRENCY.search(text)

        assert match is not None
        assert match.group(1).upper() == "GBP"

    def test_currency_context_pattern(self) -> None:
        """Waehrung im Kontext erkennen."""
        text = "Total EUR 1.234,56"
        match = CurrencyPatterns.CURRENCY_CONTEXT.search(text)

        assert match is not None
        assert match.group(1).upper() == "EUR"

    def test_currency_map_contains_common_currencies(self) -> None:
        """Waehrungsmap enthaelt gaengige Waehrungen."""
        assert CurrencyPatterns.CURRENCY_MAP.get("EUR") == "EUR"
        assert CurrencyPatterns.CURRENCY_MAP.get("USD") == "USD"
        assert CurrencyPatterns.CURRENCY_MAP.get("GBP") == "GBP"
        assert CurrencyPatterns.CURRENCY_MAP.get("CHF") == "CHF"


class TestReverseChargePatterns:
    """Tests fuer Reverse-Charge-Erkennung."""

    def test_detect_reverse_charge_german(self) -> None:
        """Deutsche Reverse-Charge-Klausel erkennen."""
        texts = [
            "Innergemeinschaftliche Lieferung gemaess UStG",
            "Steuerfreie innergemeinschaftliche Lieferung",
            "Steuerbefreit nach Paragraph 4",
        ]

        for text in texts:
            match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_reverse_charge_english(self) -> None:
        """Englische Reverse-Charge-Klausel erkennen."""
        texts = [
            "Intra-community supply",
            "Reverse charge applies",
            "VAT 0% reverse charge",
        ]

        for text in texts:
            match = ReverseChargePatterns.REVERSE_CHARGE.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_reverse_charge_dutch(self) -> None:
        """Niederlaendische BTW-Verlagerung erkennen."""
        text = "BTW verlegd"
        match = ReverseChargePatterns.REVERSE_CHARGE.search(text)

        assert match is not None


class TestDeliveryPatterns:
    """Tests fuer Lieferbedingungen."""

    def test_detect_incoterms(self) -> None:
        """Incoterms erkennen."""
        incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF"]

        for term in incoterms:
            text = f"Lieferbedingung: {term} Hamburg"
            match = DeliveryPatterns.INCOTERMS.search(text)
            assert match is not None, f"Sollte '{term}' erkennen"
            assert match.group(1) == term

    def test_detect_incoterm_with_location(self) -> None:
        """Incoterm mit Ort erkennen."""
        text = "FOB Rotterdam Incoterms 2020"
        match = DeliveryPatterns.INCOTERMS.search(text)

        assert match is not None
        assert match.group(1) == "FOB"

    def test_detect_delivery_terms_german(self) -> None:
        """Deutsche Lieferbedingungen erkennen."""
        text = "Lieferbedingungen: Frei Haus innerhalb Deutschlands"
        match = DeliveryPatterns.DELIVERY_TERMS_DE.search(text)

        assert match is not None

    def test_detect_delivery_address_labels(self) -> None:
        """Lieferadress-Labels erkennen."""
        labels = [
            "Lieferadresse:",
            "Lieferanschrift",
            "Delivery to:",
            "Ship to",
            # "Warenempfaenger" hat Umlaut - Pattern verwendet [aä]
        ]

        for label in labels:
            match = DeliveryPatterns.DELIVERY_ADDRESS_LABELS.search(label)
            assert match is not None, f"Sollte '{label}' erkennen"

        # Test mit Umlaut-Variante
        match_umlaut = DeliveryPatterns.DELIVERY_ADDRESS_LABELS.search("Warenempfänger")
        assert match_umlaut is not None, "Sollte 'Warenempfänger' erkennen"


class TestReferencePatterns:
    """Tests fuer Dokumentreferenzen."""

    def test_detect_invoice_number_standard(self) -> None:
        """Standard-Rechnungsnummer erkennen."""
        texts = [
            ("Rechnung Nr. RE-2024-001", "RE-2024-001"),
            ("Rechnungsnummer: 2024/12345", "2024/12345"),
            ("Invoice No. INV-2024-001", "INV-2024-001"),
        ]

        for text, expected in texts:
            match = ReferencePatterns.INVOICE_NUMBER.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_invoice_number_vendor_specific(self) -> None:
        """Lieferantenspezifische Rechnungsnummer erkennen."""
        # RG-Format (Asal)
        text = "RG20012108"
        match = ReferencePatterns.INVOICE_NUMBER_RG.search(text)
        assert match is not None
        assert match.group(1) == "RG20012108"

        # CD-Format (Amefa)
        text = "CD4921000467"
        match = ReferencePatterns.INVOICE_NUMBER_CD.search(text)
        assert match is not None
        assert match.group(1) == "CD4921000467"

    def test_detect_order_number_standard(self) -> None:
        """Standard-Bestellnummer erkennen."""
        texts = [
            ("Bestell-Nr.: BEST-2024-001", "BEST-2024-001"),
            ("Auftragsnummer: AB-2024-123", "AB-2024-123"),
            ("Order No. PO-2024-001", "PO-2024-001"),
        ]

        for text, expected in texts:
            match = ReferencePatterns.ORDER_NUMBER.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_customer_number(self) -> None:
        """Kundennummer erkennen."""
        texts = [
            ("Kundennummer: KD-78901", "KD-78901"),
            ("Kunden-Nr.: 12345", "12345"),
            ("Customer No. C-2024", "C-2024"),
        ]

        for text, expected in texts:
            match = ReferencePatterns.CUSTOMER_NUMBER.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_supplier_number(self) -> None:
        """Lieferantennummer erkennen."""
        texts = [
            ("Lieferanten-Nr.: LF-12345", "LF-12345"),
            ("Kreditor-Nr. 67890", "67890"),
            ("Supplier No. SUP-001", "SUP-001"),
        ]

        for text, expected in texts:
            match = ReferencePatterns.SUPPLIER_NUMBER.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected


class TestDatePatterns:
    """Tests fuer Datumsextraktion."""

    def test_detect_german_date_format(self) -> None:
        """Deutsches Datumsformat erkennen."""
        dates = [
            "15.02.2024",
            "1.3.24",
            "31-12-2024",
            "01/06/2024",
        ]

        for date_str in dates:
            match = DatePatterns.DATE_DE.search(date_str)
            assert match is not None, f"Sollte '{date_str}' matchen"

    def test_detect_invoice_date_german(self) -> None:
        """Deutsches Rechnungsdatum erkennen."""
        texts = [
            "Rechnungsdatum: 15.02.2024",
            "Datum der Rechnung: 01.03.2024",
            "Ausgestellt am 20.04.2024",
        ]

        for text in texts:
            match = DatePatterns.INVOICE_DATE.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_invoice_date_dutch(self) -> None:
        """Niederlaendisches Rechnungsdatum erkennen."""
        text = "Factuurdatum: 15-02-2024"
        match = DatePatterns.INVOICE_DATE.search(text)

        assert match is not None

    def test_detect_service_period(self) -> None:
        """Leistungszeitraum erkennen."""
        texts = [
            "Leistungszeitraum: 01.01.2024 - 31.01.2024",
            "Abrechnungszeitraum: 01.02.2024 bis 28.02.2024",
        ]

        for text in texts:
            match = DatePatterns.SERVICE_PERIOD.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_contract_duration(self) -> None:
        """Vertragslaufzeit erkennen."""
        texts = [
            ("Laufzeit: 12 Monate", "12", "Monate"),
            ("Vertragsdauer: 24 Monate", "24", "Monate"),
            # "Gueltigkeit" mit Umlaut - Pattern verwendet [uü]
            ("Gültigkeit: 365 Tage", "365", "Tage"),
        ]

        for text, expected_num, expected_unit in texts:
            match = DatePatterns.CONTRACT_DURATION.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected_num
            assert match.group(2).lower() == expected_unit.lower()


class TestAmountPatterns:
    """Tests fuer Betragsextraktion."""

    def test_detect_german_amount_format(self) -> None:
        """Deutsches Betragsformat erkennen."""
        amounts = [
            ("1.234,56 EUR", "1.234,56"),
            ("999,00 EUR", "999,00"),
            ("12.345.678,99 EUR", "12.345.678,99"),
        ]

        for text, expected in amounts:
            match = AmountPatterns.GERMAN_AMOUNT.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_net_amount(self) -> None:
        """Nettobetrag erkennen."""
        texts = [
            ("Nettobetrag: 1.000,00 EUR", "1.000,00"),
            ("Zwischensumme: 500,00 EUR", "500,00"),
            ("Summe netto: 750,50 EUR", "750,50"),
        ]

        for text, expected in texts:
            match = AmountPatterns.NET_AMOUNT.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_gross_amount(self) -> None:
        """Bruttobetrag erkennen."""
        texts = [
            ("Bruttobetrag: 1.190,00 EUR", "1.190,00"),
            ("Gesamtbetrag: 1.000,00 EUR", "1.000,00"),
            ("Zu zahlen: 500,50 EUR", "500,50"),
        ]

        for text, expected in texts:
            match = AmountPatterns.GROSS_AMOUNT.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1) == expected

    def test_detect_vat_with_rate(self) -> None:
        """MwSt mit Satz erkennen."""
        text = "MwSt 19%: 190,00 EUR"
        match = AmountPatterns.VAT_WITH_RATE.search(text)

        assert match is not None
        assert match.group(1) == "19"  # Rate
        assert match.group(2) == "190,00"  # Amount


class TestPaymentPatternsExtended:
    """Erweiterte Tests fuer Zahlungsbedingungen."""

    def test_detect_immediate_payment(self) -> None:
        """Sofortige Zahlung erkennen."""
        # Pattern verwendet Umlaut-Zeichen (ä, ü) statt ae, ue
        texts = [
            "Zahlbar sofort",
            "Sofort fällig",  # Pattern erwartet fällig mit Umlaut
            "Bar bei Übergabe",  # Pattern erwartet Umlaut
            "Zahlung bei Lieferung",
            "Vorauskasse",
        ]

        for text in texts:
            match = PaymentPatterns.PAYMENT_IMMEDIATE.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_due_date_direct(self) -> None:
        """Direktes Faelligkeitsdatum erkennen."""
        # Pattern verwendet Umlaut-Zeichen (ä) statt ae
        texts = [
            "Fällig am 15.02.2024",  # Pattern erwartet Fällig mit Umlaut
            "Zahlbar bis 28.02.2024",
            "Due Date 14-03-2024",
        ]

        for text in texts:
            match = PaymentPatterns.DUE_DATE_DIRECT.search(text)
            assert match is not None, f"Sollte '{text}' matchen"

    def test_detect_late_interest(self) -> None:
        """Verzugszinsen erkennen."""
        text = "Verzugszinsen: 9% ueber Basiszinssatz"
        match = PaymentPatterns.LATE_INTEREST.search(text)

        assert match is not None
        assert match.group(1) == "9"

    def test_detect_payment_method(self) -> None:
        """Zahlungsart erkennen."""
        # Pattern verwendet Umlaut-Zeichen (ü) statt ue
        texts = [
            ("Zahlung per Überweisung", "überweisung"),  # Umlaut
            ("Bezahlung via Lastschrift", "lastschrift"),
            ("Zahlung bar", "bar"),
        ]

        for text, expected in texts:
            match = PaymentPatterns.PAYMENT_METHOD.search(text)
            assert match is not None, f"Sollte '{text}' matchen"
            assert match.group(1).lower() == expected.lower()


class TestCountryNameToCode:
    """Tests fuer Laender-Mapping."""

    def test_germany_variants(self) -> None:
        """Deutsche Varianten werden erkannt."""
        variants = ["deutschland", "germany", "duitsland", "allemagne"]
        for variant in variants:
            assert COUNTRY_NAME_TO_CODE.get(variant) == "DE"

    def test_netherlands_variants(self) -> None:
        """Niederlaendische Varianten werden erkannt."""
        variants = ["niederlande", "netherlands", "nederland", "holland"]
        for variant in variants:
            assert COUNTRY_NAME_TO_CODE.get(variant) == "NL"

    def test_austria_variants(self) -> None:
        """Oesterreichische Varianten werden erkannt."""
        variants = ["oesterreich", "austria", "autriche", "oostenrijk"]
        for variant in variants:
            assert COUNTRY_NAME_TO_CODE.get(variant) == "AT"


class TestStructuredExtractionService:
    """Tests fuer StructuredExtractionService."""

    @pytest.fixture
    def service(self) -> StructuredExtractionService:
        """Erstellt eine frische Service-Instanz."""
        return StructuredExtractionService()

    @pytest.mark.asyncio
    async def test_extract_empty_text(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Leerer Text gibt leeres Ergebnis."""
        result = await service.extract(text="")

        assert result is not None
        assert result.extraction_version == "2.0.0"
        assert result.extracted_at is not None

    @pytest.mark.asyncio
    async def test_extract_simple_invoice(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Einfache Rechnung extrahieren."""
        text = """
        Rechnung Nr. RE-2024-001
        Rechnungsdatum: 15.01.2024

        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        Zahlungsziel: 30 Tage netto
        """
        result = await service.extract(text=text)

        assert result.classification.document_type == ExtractedDocumentType.INVOICE
        assert result.invoice is not None

    @pytest.mark.asyncio
    async def test_extract_with_document_id(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Extraktion mit Dokument-ID fuer Logging."""
        text = "Rechnung Nr. RE-2024-001"
        result = await service.extract(
            text=text,
            document_id="test-doc-123",
        )

        assert result is not None

    def test_clean_company_name_basic(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Firmenname wird bereinigt."""
        dirty_name = "<b>Muster GmbH</b>"
        clean_name = service._clean_company_name(dirty_name)

        assert clean_name == "Muster GmbH"

    def test_clean_company_name_removes_doc_type(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Dokumenttyp-Indikatoren werden entfernt."""
        dirty_name = "Muster GmbH Sales - Invoice"
        clean_name = service._clean_company_name(dirty_name)

        assert "Sales - Invoice" not in clean_name
        assert "Muster GmbH" in clean_name

    def test_clean_company_name_handles_none(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """None wird zu None (oder leer)."""
        result = service._clean_company_name(None)
        assert result is None

    def test_clean_company_name_handles_empty(
        self,
        service: StructuredExtractionService,
    ) -> None:
        """Leerer String wird behandelt."""
        result = service._clean_company_name("")
        assert result == ""
