"""
Tests for SmartAmountExtractor.

Tests context-aware amount extraction:
- Labeled amounts (Netto, Brutto, MwSt)
- Unlabeled amounts with inference
- VAT rate detection
- Consistency validation
"""

from decimal import Decimal

import pytest

from app.services.extraction.extractors.amount_extractor import (
    AmountExtractionResult,
    SmartAmountExtractor,
)


@pytest.fixture
def extractor() -> SmartAmountExtractor:
    """Create amount extractor."""
    return SmartAmountExtractor()


class TestLabeledAmounts:
    """Tests for explicitly labeled amounts."""

    def test_netto_betrag(self, extractor: SmartAmountExtractor):
        """Extract labeled Nettobetrag."""
        text = "Nettobetrag: 1.000,00 EUR"
        result = extractor.extract(text)

        assert result.net_amount == Decimal("1000.00")
        assert result.net_confidence >= 0.8

    def test_brutto_betrag(self, extractor: SmartAmountExtractor):
        """Extract labeled Bruttobetrag."""
        text = "Bruttobetrag: 1.190,00 EUR"
        result = extractor.extract(text)

        assert result.gross_amount == Decimal("1190.00")
        assert result.gross_confidence >= 0.8

    def test_mwst_with_rate(self, extractor: SmartAmountExtractor):
        """Extract MwSt with rate."""
        text = "MwSt 19%: 190,00 EUR"
        result = extractor.extract(text)

        assert result.vat_amount == Decimal("190.00")
        assert result.vat_rate == Decimal("19")

    def test_gesamt_betrag(self, extractor: SmartAmountExtractor):
        """Extract Gesamtbetrag as gross."""
        text = "Gesamtbetrag: 1.190,00 EUR"
        result = extractor.extract(text)

        assert result.gross_amount == Decimal("1190.00")

    def test_zu_zahlen(self, extractor: SmartAmountExtractor):
        """Extract 'zu zahlen' as gross."""
        text = "Zu zahlen: 1.190,00 EUR"
        result = extractor.extract(text)

        assert result.gross_amount == Decimal("1190.00")


class TestGermanNumberFormats:
    """Tests for German number format parsing."""

    def test_thousands_separator(self, extractor: SmartAmountExtractor):
        """Parse German thousands separator (1.234,56)."""
        text = "Nettobetrag: 12.345,67 EUR"
        result = extractor.extract(text)

        assert result.net_amount == Decimal("12345.67")

    def test_no_thousands_separator(self, extractor: SmartAmountExtractor):
        """Parse without thousands separator (1234,56)."""
        text = "Nettobetrag: 1234,56 EUR"
        result = extractor.extract(text)

        assert result.net_amount == Decimal("1234.56")

    def test_euro_symbol(self, extractor: SmartAmountExtractor):
        """Parse with € symbol."""
        text = "Bruttobetrag: 1.190,00 €"
        result = extractor.extract(text)

        assert result.gross_amount == Decimal("1190.00")


class TestMathematicalInference:
    """Tests for mathematical inference."""

    def test_infer_gross_from_net_vat(self, extractor: SmartAmountExtractor):
        """Infer gross from net + vat."""
        text = """
        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("1000.00")
        assert result.vat_amount == Decimal("190.00")
        # Gross should be inferred
        assert result.gross_amount == Decimal("1190.00")
        assert result.inferred_from_math

    def test_infer_vat_from_net_gross(self, extractor: SmartAmountExtractor):
        """Infer VAT from gross - net."""
        text = """
        Nettobetrag: 1.000,00 EUR
        Bruttobetrag: 1.190,00 EUR
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("1000.00")
        assert result.gross_amount == Decimal("1190.00")
        # VAT should be inferred
        assert result.vat_amount == Decimal("190.00")


class TestVatRateInference:
    """Tests for VAT rate inference."""

    def test_infer_19_percent(self, extractor: SmartAmountExtractor):
        """Infer 19% from amounts."""
        text = """
        Nettobetrag: 1.000,00 EUR
        MwSt: 190,00 EUR
        """
        result = extractor.extract(text)

        assert result.vat_rate == Decimal("19")

    def test_infer_7_percent(self, extractor: SmartAmountExtractor):
        """Infer 7% from amounts."""
        text = """
        Nettobetrag: 1.000,00 EUR
        MwSt: 70,00 EUR
        """
        result = extractor.extract(text)

        assert result.vat_rate == Decimal("7")


class TestConsistencyValidation:
    """Tests for amount consistency validation."""

    def test_consistent_amounts(self, extractor: SmartAmountExtractor):
        """Consistent amounts should pass."""
        text = """
        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR
        """
        result = extractor.extract(text)

        assert result.is_consistent

    def test_inconsistent_amounts_warning(self, extractor: SmartAmountExtractor):
        """Inconsistent amounts should be flagged."""
        text = """
        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.200,00 EUR
        """
        result = extractor.extract(text)

        assert not result.is_consistent
        assert len(result.extraction_warnings) > 0


class TestComplexInvoice:
    """Tests with realistic invoice text."""

    def test_full_invoice_extraction(self, extractor: SmartAmountExtractor):
        """Extract all amounts from realistic invoice."""
        text = """
        RECHNUNG Nr. RE-2024-001234

        Pos.  Beschreibung                    Menge   Preis      Gesamt
        1     Beratungsleistung IT            8 Std   125,00     1.000,00
        2     Softwarelizenz                  1       200,00       200,00

        Nettobetrag:                                            1.200,00 EUR
        MwSt 19%:                                                 228,00 EUR
        Bruttobetrag:                                           1.428,00 EUR

        Zahlbar innerhalb 30 Tagen.
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("1200.00")
        assert result.vat_amount == Decimal("228.00")
        assert result.gross_amount == Decimal("1428.00")
        assert result.vat_rate == Decimal("19")
        assert result.is_consistent


class TestReverseCharge:
    """Tests for Reverse Charge / innergemeinschaftliche Lieferung."""

    def test_dutch_reverse_charge_with_btw_verlegd(self, extractor: SmartAmountExtractor):
        """Dutch invoice with BTW verlegd - Total should be Net, no Gross."""
        text = """
        INVOICE
        VAT Reg. No. 820594829B01
        VAT Registration No. DE200053646

        Total EUR 1.305,60

        Payment Terms: Netto 10 dagen
        BTW verlegd / Reverse Charge
        """
        result = extractor.extract(text)

        # Total sollte als Netto erkannt werden bei Reverse Charge
        assert result.net_amount == Decimal("1305.60")
        # Gross sollte None sein
        assert result.gross_amount is None
        # VAT sollte explizit 0 sein
        assert result.vat_amount == Decimal("0")
        assert result.vat_rate == Decimal("0")

    def test_reverse_charge_explicit_mention(self, extractor: SmartAmountExtractor):
        """Invoice with explicit Reverse Charge mention."""
        text = """
        Rechnung

        Gesamtbetrag: 5.000,00 EUR

        Reverse Charge - Steuerschuldnerschaft des Leistungsempfängers
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("5000.00")
        assert result.gross_amount is None
        assert result.vat_amount == Decimal("0")

    def test_innergemeinschaftliche_lieferung(self, extractor: SmartAmountExtractor):
        """German text for intra-community delivery."""
        text = """
        Rechnung Nr. 2024-001

        Total: 2.500,00 EUR

        Innergemeinschaftliche Lieferung - steuerfreie Lieferung
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("2500.00")
        assert result.gross_amount is None

    def test_cross_border_vat_ids_detected(self, extractor: SmartAmountExtractor):
        """EU VAT-ID + DE VAT-ID implies Reverse Charge."""
        text = """
        Supplier: Company BV
        VAT: NL123456789B01

        Customer: German GmbH
        VAT: DE123456789

        Gesamtbetrag: 3.750,00 EUR
        """
        result = extractor.extract(text)

        # Cross-border EU transaction should be detected as Reverse Charge
        assert result.net_amount == Decimal("3750.00")
        assert result.gross_amount is None

    def test_normal_german_invoice_not_affected(self, extractor: SmartAmountExtractor):
        """Normal German invoice with VAT should work unchanged."""
        text = """
        RECHNUNG

        Nettobetrag: 1.000,00 EUR
        MwSt 19%: 190,00 EUR
        Bruttobetrag: 1.190,00 EUR

        Zahlbar innerhalb 14 Tagen.
        """
        result = extractor.extract(text)

        # Normal invoice should have all amounts
        assert result.net_amount == Decimal("1000.00")
        assert result.vat_amount == Decimal("190.00")
        assert result.gross_amount == Decimal("1190.00")
        assert result.vat_rate == Decimal("19")
        assert result.is_consistent

    def test_vat_exempt_zero_percent(self, extractor: SmartAmountExtractor):
        """Invoice with explicit 0% VAT mention."""
        text = """
        Invoice Total: 800,00 EUR
        VAT 0%: 0,00 EUR

        Tax exempt delivery
        """
        result = extractor.extract(text)

        assert result.net_amount == Decimal("800.00")
        assert result.gross_amount is None


class TestPaymentTermsNotAmount:
    """Tests to ensure payment terms are not extracted as amounts."""

    def test_netto_dagen_not_amount(self, extractor: SmartAmountExtractor):
        """'Netto 10 dagen' should NOT extract 10 as net amount."""
        text = """
        Total EUR 1.305,60

        Payment Terms: Netto 10 dagen
        """
        result = extractor.extract(text)

        # 10 sollte NICHT als Nettobetrag extrahiert werden
        assert result.net_amount != Decimal("10")
        assert result.net_amount != Decimal("10.00")

    def test_netto_tage_not_amount(self, extractor: SmartAmountExtractor):
        """'Netto 30 Tage' should NOT extract 30 as net amount."""
        text = """
        Gesamtbetrag: 2.500,00 EUR

        Zahlungsziel: Netto 30 Tage
        """
        result = extractor.extract(text)

        assert result.net_amount != Decimal("30")
        assert result.net_amount != Decimal("30.00")

    def test_payment_days_not_net_amount(self, extractor: SmartAmountExtractor):
        """Payment days in various formats should not be net amount."""
        text = """
        Total: 999,99 EUR

        Zahlbar netto 14 days
        """
        result = extractor.extract(text)

        assert result.net_amount != Decimal("14")
        assert result.net_amount != Decimal("14.00")