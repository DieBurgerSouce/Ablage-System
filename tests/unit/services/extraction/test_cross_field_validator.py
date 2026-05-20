"""
Tests for CrossFieldValidator.

Tests cross-field validation:
- Amount consistency
- Date consistency
- Payment terms vs due date
- Line item sum validation
- VAT rate plausibility
- Skonto plausibility
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.extraction.base import Severity
from app.services.extraction.validators.cross_field_validator import (
    CrossFieldValidator,
    InvoiceValidationInput,
)
from app.services.extraction.extractors.line_item_extractor import ExtractedLineItem
from app.services.extraction.extractors.payment_extractor import ExtractedPaymentTerms


@pytest.fixture
def validator() -> CrossFieldValidator:
    """Create validator."""
    return CrossFieldValidator()


class TestAmountConsistency:
    """Tests for Net + VAT = Gross validation."""

    def test_consistent_amounts(self, validator: CrossFieldValidator):
        """Pass when amounts are consistent."""
        data = InvoiceValidationInput(
            net_amount=Decimal("1000.00"),
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.00"),
        )

        results = validator.validate_invoice(data)

        amount_results = [r for r in results if r.validation_type == "amount_consistency"]
        assert all(r.is_valid for r in amount_results)

    def test_inconsistent_amounts(self, validator: CrossFieldValidator):
        """Fail when amounts are inconsistent."""
        data = InvoiceValidationInput(
            net_amount=Decimal("1000.00"),
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1200.00"),  # Should be 1190
        )

        results = validator.validate_invoice(data)

        amount_results = [r for r in results if r.validation_type == "amount_consistency"]
        assert any(not r.is_valid for r in amount_results)
        assert any(r.severity == Severity.ERROR for r in amount_results if not r.is_valid)

    def test_tolerance_within_10_cents(self, validator: CrossFieldValidator):
        """Pass within 10 cent tolerance."""
        data = InvoiceValidationInput(
            net_amount=Decimal("1000.00"),
            vat_amount=Decimal("190.00"),
            gross_amount=Decimal("1190.05"),  # 5 cents difference
        )

        results = validator.validate_invoice(data)

        amount_results = [r for r in results if r.validation_type == "amount_consistency"]
        assert all(r.is_valid for r in amount_results)


class TestDateConsistency:
    """Tests for date validation."""

    def test_due_date_after_invoice_date(self, validator: CrossFieldValidator):
        """Pass when due date is after invoice date."""
        data = InvoiceValidationInput(
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 14),
        )

        results = validator.validate_invoice(data)

        date_results = [r for r in results if r.validation_type == "date_consistency"]
        assert all(r.is_valid for r in date_results)

    def test_due_date_before_invoice_date(self, validator: CrossFieldValidator):
        """Fail when due date is before invoice date."""
        data = InvoiceValidationInput(
            invoice_date=date(2024, 2, 15),
            due_date=date(2024, 1, 15),  # Before invoice date
        )

        results = validator.validate_invoice(data)

        date_results = [r for r in results if r.validation_type == "date_consistency"]
        assert any(not r.is_valid for r in date_results)
        assert any(r.severity == Severity.ERROR for r in date_results if not r.is_valid)


class TestPaymentTermsConsistency:
    """Tests for payment terms vs due date validation."""

    def test_matching_payment_terms(self, validator: CrossFieldValidator):
        """Pass when payment terms match due date."""
        data = InvoiceValidationInput(
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 2, 14),  # 30 days later
            payment_days=30,
        )

        results = validator.validate_invoice(data)

        payment_results = [r for r in results if r.validation_type == "payment_terms_consistency"]
        assert all(r.is_valid for r in payment_results)

    def test_mismatched_payment_terms(self, validator: CrossFieldValidator):
        """Warn when payment terms don't match due date."""
        data = InvoiceValidationInput(
            invoice_date=date(2024, 1, 15),
            due_date=date(2024, 3, 15),  # 59 days later
            payment_days=30,  # But says 30 days
        )

        results = validator.validate_invoice(data)

        payment_results = [r for r in results if r.validation_type == "payment_terms_consistency"]
        assert any(not r.is_valid for r in payment_results)


class TestLineItemSumValidation:
    """Tests for line item sum vs net amount."""

    def test_matching_line_item_sum(self, validator: CrossFieldValidator):
        """Pass when line items sum to net amount."""
        data = InvoiceValidationInput(
            net_amount=Decimal("1200.00"),
            line_items=[
                ExtractedLineItem(position=1, description="Item 1", total_price=Decimal("1000.00")),
                ExtractedLineItem(position=2, description="Item 2", total_price=Decimal("200.00")),
            ],
        )

        results = validator.validate_invoice(data)

        sum_results = [r for r in results if r.validation_type == "line_item_sum"]
        assert all(r.is_valid for r in sum_results)

    def test_mismatched_line_item_sum(self, validator: CrossFieldValidator):
        """Warn when line items don't sum to net amount."""
        data = InvoiceValidationInput(
            net_amount=Decimal("1500.00"),  # Doesn't match sum
            line_items=[
                ExtractedLineItem(position=1, description="Item 1", total_price=Decimal("1000.00")),
                ExtractedLineItem(position=2, description="Item 2", total_price=Decimal("200.00")),
            ],
        )

        results = validator.validate_invoice(data)

        sum_results = [r for r in results if r.validation_type == "line_item_sum"]
        assert any(not r.is_valid for r in sum_results)


class TestVatRatePlausibility:
    """Tests for VAT rate validation."""

    def test_valid_german_vat_rates(self, validator: CrossFieldValidator):
        """Pass for standard German VAT rates."""
        for rate in [Decimal("0"), Decimal("7"), Decimal("19")]:
            data = InvoiceValidationInput(vat_rate=rate)
            results = validator.validate_invoice(data)
            vat_results = [r for r in results if r.validation_type == "vat_rate_plausibility"]
            assert all(r.is_valid for r in vat_results)

    def test_unusual_vat_rate(self, validator: CrossFieldValidator):
        """Warn for unusual VAT rates."""
        data = InvoiceValidationInput(vat_rate=Decimal("25"))

        results = validator.validate_invoice(data)

        vat_results = [r for r in results if r.validation_type == "vat_rate_plausibility"]
        assert any(not r.is_valid for r in vat_results)


class TestSkontoPlausibility:
    """Tests for Skonto validation."""

    def test_valid_skonto(self, validator: CrossFieldValidator):
        """Pass for plausible Skonto conditions."""
        data = InvoiceValidationInput(
            discount_percent=Decimal("2"),
            discount_days=10,
            payment_days=30,
        )

        results = validator.validate_invoice(data)

        skonto_results = [r for r in results if "skonto" in r.validation_type]
        assert all(r.is_valid for r in skonto_results)

    def test_high_skonto_percent(self, validator: CrossFieldValidator):
        """Warn for unusually high Skonto."""
        data = InvoiceValidationInput(
            discount_percent=Decimal("10"),  # Too high
            discount_days=10,
        )

        results = validator.validate_invoice(data)

        skonto_results = [r for r in results if r.validation_type == "skonto_plausibility"]
        assert any(not r.is_valid for r in skonto_results)

    def test_skonto_days_longer_than_payment(self, validator: CrossFieldValidator):
        """Fail when Skonto days >= payment days."""
        data = InvoiceValidationInput(
            discount_percent=Decimal("2"),
            discount_days=30,  # Same as payment days
            payment_days=30,
        )

        results = validator.validate_invoice(data)

        skonto_results = [r for r in results if r.validation_type == "skonto_consistency"]
        assert any(not r.is_valid for r in skonto_results)


class TestLineItemMath:
    """Tests for line item math validation."""

    def test_valid_line_item_math(self, validator: CrossFieldValidator):
        """Pass when qty * price = total."""
        data = InvoiceValidationInput(
            line_items=[
                ExtractedLineItem(
                    position=1,
                    description="Item 1",
                    quantity=Decimal("8"),
                    unit_price=Decimal("125.00"),
                    total_price=Decimal("1000.00"),
                ),
            ],
        )

        results = validator.validate_invoice(data)

        math_results = [r for r in results if r.validation_type == "line_item_math"]
        assert not any(not r.is_valid for r in math_results)

    def test_invalid_line_item_math(self, validator: CrossFieldValidator):
        """Warn when qty * price != total."""
        data = InvoiceValidationInput(
            line_items=[
                ExtractedLineItem(
                    position=1,
                    description="Item 1",
                    quantity=Decimal("8"),
                    unit_price=Decimal("125.00"),
                    total_price=Decimal("999.00"),  # Should be 1000
                ),
            ],
        )

        results = validator.validate_invoice(data)

        math_results = [r for r in results if r.validation_type == "line_item_math"]
        assert any(not r.is_valid for r in math_results)
