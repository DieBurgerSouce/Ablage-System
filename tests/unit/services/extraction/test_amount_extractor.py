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
