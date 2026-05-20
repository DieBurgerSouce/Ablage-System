"""
Tests for PaymentTermsExtractor.

Tests all payment pattern variants:
- Basic German patterns
- International NET patterns
- Stepped discounts (2/10 net 30)
- End of month
- Immediate/prepayment
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.extraction.extractors.payment_extractor import (
    ExtractedPaymentTerms,
    PaymentTermsExtractor,
)


@pytest.fixture
def extractor() -> PaymentTermsExtractor:
    """Create payment terms extractor."""
    return PaymentTermsExtractor()


class TestBasicPaymentDays:
    """Tests for basic German payment day patterns."""

    def test_zahlbar_innerhalb_30_tagen(self, extractor: PaymentTermsExtractor):
        """Standard German: Zahlbar innerhalb 30 Tagen."""
        text = "Zahlungsbedingungen: Zahlbar innerhalb von 30 Tagen"
        result = extractor.extract(text)

        assert result.payment_days == 30
        assert not result.is_immediate
        assert not result.is_prepayment

    def test_zahlungsziel_14_tage(self, extractor: PaymentTermsExtractor):
        """Zahlungsziel: 14 Tage netto."""
        text = "Zahlungsziel: 14 Tage netto"
        result = extractor.extract(text)

        assert result.payment_days == 14

    def test_netto_60_tage(self, extractor: PaymentTermsExtractor):
        """Netto 60 Tage."""
        text = "netto 60 Tage"
        result = extractor.extract(text)

        assert result.payment_days == 60


class TestInternationalPatterns:
    """Tests for international payment patterns."""

    def test_net_30(self, extractor: PaymentTermsExtractor):
        """NET 30 pattern."""
        text = "Payment terms: NET 30"
        result = extractor.extract(text)

        assert result.payment_days == 30

    def test_netto_30(self, extractor: PaymentTermsExtractor):
        """Netto 30."""
        text = "Netto 30 Tage"
        result = extractor.extract(text)

        assert result.payment_days == 30


class TestImmediatePayment:
    """Tests for immediate payment patterns."""

    def test_sofort_faellig(self, extractor: PaymentTermsExtractor):
        """Sofort fällig."""
        text = "Der Rechnungsbetrag ist sofort fällig"
        result = extractor.extract(text)

        assert result.is_immediate
        assert result.payment_days == 0

    def test_zahlbar_sofort(self, extractor: PaymentTermsExtractor):
        """Zahlbar sofort."""
        text = "Zahlbar sofort"
        result = extractor.extract(text)

        assert result.is_immediate

    def test_zahlung_bei_lieferung(self, extractor: PaymentTermsExtractor):
        """Zahlung bei Lieferung."""
        text = "Zahlung bei Lieferung"
        result = extractor.extract(text)

        assert result.is_immediate


class TestPrepayment:
    """Tests for prepayment patterns."""

    def test_vorauskasse(self, extractor: PaymentTermsExtractor):
        """Vorauskasse."""
        text = "Bitte Vorauskasse"
        result = extractor.extract(text)

        assert result.is_prepayment
        assert result.is_immediate

    def test_vorkasse(self, extractor: PaymentTermsExtractor):
        """Vorkasse erforderlich."""
        text = "Vorkasse erforderlich"
        result = extractor.extract(text)

        assert result.is_prepayment


class TestSkontoPatterns:
    """Tests for discount (Skonto) patterns."""

    def test_skonto_2_percent_10_days(self, extractor: PaymentTermsExtractor):
        """2% Skonto bei Zahlung innerhalb 10 Tagen."""
        text = "2% Skonto bei Zahlung innerhalb 10 Tagen, 30 Tage netto"
        result = extractor.extract(text)

        assert len(result.discount_tiers) >= 1
        assert result.has_skonto
        best = result.best_discount
        assert best is not None
        assert best.percent == Decimal("2")
        assert best.days == 10

    def test_stepped_discount_2_10_net_30(self, extractor: PaymentTermsExtractor):
        """International stepped: 2/10 net 30."""
        text = "Zahlungsbedingungen: 2/10 net 30"
        result = extractor.extract(text)

        assert len(result.discount_tiers) >= 1
        # Should have discount tier + net tier
        discount_tier = next((t for t in result.discount_tiers if t.percent > 0), None)
        assert discount_tier is not None
        assert discount_tier.percent == Decimal("2")
        assert discount_tier.days == 10
        assert result.payment_days == 30


class TestDueDateCalculation:
    """Tests for due date calculation."""

    def test_due_date_from_invoice_date(self, extractor: PaymentTermsExtractor):
        """Calculate due date from invoice date + payment days."""
        text = "Zahlbar innerhalb 30 Tagen"
        invoice_date = date(2024, 1, 15)

        result = extractor.extract(text, invoice_date=invoice_date)

        assert result.due_date == date(2024, 2, 14)

    def test_due_date_immediate(self, extractor: PaymentTermsExtractor):
        """Immediate payment has no due date offset."""
        text = "Sofort fällig"
        invoice_date = date(2024, 1, 15)

        result = extractor.extract(text, invoice_date=invoice_date)

        assert result.is_immediate
        # Due date should be invoice date for immediate
        assert result.due_date is None or result.due_date == invoice_date


class TestEndOfMonth:
    """Tests for end of month patterns."""

    def test_zahlbar_zum_monatsende(self, extractor: PaymentTermsExtractor):
        """Zahlbar zum Monatsende."""
        text = "Zahlbar zum Monatsende"
        result = extractor.extract(text)

        assert result.is_end_of_month

    def test_bis_ende_des_monats(self, extractor: PaymentTermsExtractor):
        """Bis Ende des Monats."""
        text = "Zahlung bis Ende des Monats"
        result = extractor.extract(text)

        assert result.is_end_of_month


class TestValidation:
    """Tests for extraction validation."""

    def test_unusually_long_payment_days_warning(self, extractor: PaymentTermsExtractor):
        """Warn on unusually long payment terms."""
        text = "Zahlbar innerhalb 365 Tagen"
        result = extractor.extract(text)

        # Should extract but flag as needing review
        assert result.payment_days == 365
        assert result.needs_review
        assert len(result.extraction_warnings) > 0

    def test_skonto_longer_than_payment_warning(self, extractor: PaymentTermsExtractor):
        """Warn if Skonto days >= payment days."""
        text = "3% Skonto innerhalb 30 Tagen, netto 30 Tage"
        result = extractor.extract(text)

        # Skonto days shouldn't be >= payment days
        assert result.needs_review or len(result.extraction_warnings) > 0


class TestConfidence:
    """Tests for confidence scoring."""

    def test_high_confidence_clear_pattern(self, extractor: PaymentTermsExtractor):
        """Clear patterns should have high confidence."""
        text = "Zahlungsziel: 30 Tage netto"
        result = extractor.extract(text)

        assert result.confidence >= 0.7

    def test_prepayment_high_confidence(self, extractor: PaymentTermsExtractor):
        """Prepayment should have high confidence."""
        text = "Vorauskasse erforderlich"
        result = extractor.extract(text)

        assert result.confidence >= 0.8
