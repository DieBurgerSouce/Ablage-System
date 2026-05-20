"""
Cross-Field Validator.

Validates consistency across extracted fields:
- Amount consistency (Net + VAT = Gross)
- Date consistency (Invoice < Due)
- Payment terms vs due date
- Line item sum vs totals
- VAT rate plausibility
- Skonto plausibility
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog

from app.services.extraction.base import (
    ExtractionConfig,
    Severity,
    ValidationResult,
)
from app.services.extraction.config import (
    GERMAN_VAT_RATES,
    MAX_PAYMENT_DAYS,
    MAX_SKONTO_DAYS,
    MAX_SKONTO_PERCENT,
)
from app.services.extraction.extractors.line_item_extractor import ExtractedLineItem
from app.services.extraction.extractors.payment_extractor import ExtractedPaymentTerms
from app.services.extraction.extractors.amount_extractor import AmountExtractionResult

logger = structlog.get_logger(__name__)


@dataclass
class InvoiceValidationInput:
    """Input data for invoice validation."""

    # Dates
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None

    # Amounts
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None

    # Payment
    payment_terms: Optional[ExtractedPaymentTerms] = None
    payment_days: Optional[int] = None
    discount_percent: Optional[Decimal] = None
    discount_days: Optional[int] = None

    # Line items
    line_items: List[ExtractedLineItem] = field(default_factory=list)

    # References
    invoice_number: Optional[str] = None
    iban: Optional[str] = None


class CrossFieldValidator:
    """
    Validates consistency across extracted fields.

    All validation results include German messages for user display.
    """

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or ExtractionConfig()

    def validate_invoice(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """
        Run all invoice validations.

        Args:
            data: Invoice data to validate

        Returns:
            List of validation results (both passed and failed)
        """
        results: List[ValidationResult] = []

        # 1. Amount consistency
        results.extend(self._validate_amount_consistency(data))

        # 2. Date consistency
        results.extend(self._validate_date_consistency(data))

        # 3. Payment terms vs due date
        results.extend(self._validate_payment_terms_consistency(data))

        # 4. Line item sum
        results.extend(self._validate_line_item_totals(data))

        # 5. VAT rate plausibility
        results.extend(self._validate_vat_rate(data))

        # 6. Skonto plausibility
        results.extend(self._validate_skonto(data))

        # 7. Line item math
        results.extend(self._validate_line_item_math(data))

        return results

    def validate_all(
        self,
        data: InvoiceValidationInput,
    ) -> tuple[bool, List[ValidationResult]]:
        """
        Run all validations and return overall status.

        Returns:
            Tuple of (all_valid, results)
        """
        results = self.validate_invoice(data)
        has_errors = any(
            not r.is_valid and r.severity == Severity.ERROR
            for r in results
        )
        return (not has_errors, results)

    def _validate_amount_consistency(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate: Net + VAT = Gross within tolerance."""
        results: List[ValidationResult] = []

        if not (data.net_amount and data.vat_amount and data.gross_amount):
            return results

        expected_gross = data.net_amount + data.vat_amount
        diff = abs(expected_gross - data.gross_amount)

        if diff > self.config.amount_tolerance:
            results.append(ValidationResult(
                is_valid=False,
                field_name="gross_amount",
                validation_type="amount_consistency",
                message=(
                    f"Betragsinkonsistenz: {data.net_amount} + "
                    f"{data.vat_amount} = {expected_gross}, "
                    f"aber Bruttobetrag ist {data.gross_amount} "
                    f"(Differenz: {diff})"
                ),
                severity=Severity.ERROR,
                suggested_fix=f"Bruttobetrag sollte {expected_gross} sein",
                details={
                    "net": float(data.net_amount),
                    "vat": float(data.vat_amount),
                    "expected_gross": float(expected_gross),
                    "actual_gross": float(data.gross_amount),
                    "diff": float(diff),
                },
            ))
        else:
            results.append(ValidationResult(
                is_valid=True,
                field_name="gross_amount",
                validation_type="amount_consistency",
                message="Betraege konsistent (Netto + MwSt = Brutto)",
                severity=Severity.INFO,
            ))

        return results

    def _validate_date_consistency(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate: Invoice date <= Due date."""
        results: List[ValidationResult] = []

        if not (data.invoice_date and data.due_date):
            return results

        if data.due_date < data.invoice_date:
            results.append(ValidationResult(
                is_valid=False,
                field_name="due_date",
                validation_type="date_consistency",
                message=(
                    f"Fälligkeitsdatum ({data.due_date}) liegt vor "
                    f"Rechnungsdatum ({data.invoice_date})"
                ),
                severity=Severity.ERROR,
                suggested_fix=(
                    f"Fälligkeitsdatum sollte nach {data.invoice_date} liegen"
                ),
            ))
        else:
            days_diff = (data.due_date - data.invoice_date).days
            results.append(ValidationResult(
                is_valid=True,
                field_name="due_date",
                validation_type="date_consistency",
                message=f"Datumsreihenfolge korrekt ({days_diff} Tage Zahlungsfrist)",
                severity=Severity.INFO,
            ))

        return results

    def _validate_payment_terms_consistency(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate payment terms match due date."""
        results: List[ValidationResult] = []

        payment_days = data.payment_days
        if data.payment_terms:
            payment_days = data.payment_terms.payment_days

        if not (data.invoice_date and data.due_date and payment_days):
            return results

        expected_due = data.invoice_date + timedelta(days=payment_days)
        diff_days = abs((expected_due - data.due_date).days)

        if diff_days > self.config.due_date_tolerance_days:
            results.append(ValidationResult(
                is_valid=False,
                field_name="payment_terms",
                validation_type="payment_terms_consistency",
                message=(
                    f"Zahlungsziel ({payment_days} Tage) ergibt "
                    f"Fälligkeitsdatum {expected_due}, "
                    f"aber angegeben ist {data.due_date} "
                    f"({diff_days} Tage Abweichung)"
                ),
                severity=Severity.WARNING,
                details={
                    "payment_days": payment_days,
                    "expected_due": expected_due.isoformat(),
                    "actual_due": data.due_date.isoformat(),
                    "diff_days": diff_days,
                },
            ))
        else:
            results.append(ValidationResult(
                is_valid=True,
                field_name="payment_terms",
                validation_type="payment_terms_consistency",
                message="Zahlungsziel und Fälligkeitsdatum stimmen überein",
                severity=Severity.INFO,
            ))

        return results

    def _validate_line_item_totals(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate sum of line items equals net amount."""
        results: List[ValidationResult] = []

        if not data.line_items or not data.net_amount:
            return results

        # Calculate sum of line items
        line_sum = sum(
            item.total_price for item in data.line_items
            if item.total_price is not None
        )

        if line_sum == 0:
            return results

        # Calculate tolerance
        tolerance_percent = self.config.line_item_sum_tolerance_percent / 100
        tolerance = max(
            data.net_amount * tolerance_percent,
            Decimal("2.00"),  # Minimum 2 EUR tolerance
        )

        diff = abs(line_sum - data.net_amount)

        if diff > tolerance:
            results.append(ValidationResult(
                is_valid=False,
                field_name="line_items",
                validation_type="line_item_sum",
                message=(
                    f"Summe der Positionen ({line_sum}) weicht von "
                    f"Nettobetrag ({data.net_amount}) ab "
                    f"(Differenz: {diff})"
                ),
                severity=Severity.WARNING,
                suggested_fix="Positionen oder Nettobetrag prüfen",
                details={
                    "line_sum": float(line_sum),
                    "net_amount": float(data.net_amount),
                    "diff": float(diff),
                    "item_count": len(data.line_items),
                },
            ))
        else:
            results.append(ValidationResult(
                is_valid=True,
                field_name="line_items",
                validation_type="line_item_sum",
                message=(
                    f"Positionssumme ({line_sum}) entspricht "
                    f"Nettobetrag ({data.net_amount})"
                ),
                severity=Severity.INFO,
            ))

        return results

    def _validate_vat_rate(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate VAT rate is plausible."""
        results: List[ValidationResult] = []

        if data.vat_rate is None:
            return results

        if data.vat_rate not in GERMAN_VAT_RATES:
            results.append(ValidationResult(
                is_valid=False,
                field_name="vat_rate",
                validation_type="vat_rate_plausibility",
                message=(
                    f"MwSt-Satz {data.vat_rate}% ist kein "
                    f"deutscher Standardsatz (0%, 7%, 19%)"
                ),
                severity=Severity.WARNING,
                suggested_fix="MwSt-Satz prüfen",
            ))
        else:
            results.append(ValidationResult(
                is_valid=True,
                field_name="vat_rate",
                validation_type="vat_rate_plausibility",
                message=f"MwSt-Satz {data.vat_rate}% ist plausibel",
                severity=Severity.INFO,
            ))

        return results

    def _validate_skonto(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate skonto conditions are plausible."""
        results: List[ValidationResult] = []

        discount_percent = data.discount_percent
        discount_days = data.discount_days
        payment_days = data.payment_days

        if data.payment_terms:
            if data.payment_terms.discount_tiers:
                best = data.payment_terms.best_discount
                if best:
                    discount_percent = best.percent
                    discount_days = best.days
            payment_days = data.payment_terms.payment_days

        if discount_percent is None or discount_days is None:
            return results

        # Check discount percentage
        if discount_percent > MAX_SKONTO_PERCENT:
            results.append(ValidationResult(
                is_valid=False,
                field_name="discount_percent",
                validation_type="skonto_plausibility",
                message=f"Ungewoehnlich hoher Skonto: {discount_percent}%",
                severity=Severity.WARNING,
            ))

        # Check discount days
        if discount_days > MAX_SKONTO_DAYS:
            results.append(ValidationResult(
                is_valid=False,
                field_name="discount_days",
                validation_type="skonto_plausibility",
                message=f"Ungewoehnlich lange Skontofrist: {discount_days} Tage",
                severity=Severity.WARNING,
            ))

        # Check discount days < payment days
        if payment_days and discount_days >= payment_days:
            results.append(ValidationResult(
                is_valid=False,
                field_name="discount_days",
                validation_type="skonto_consistency",
                message=(
                    f"Skontofrist ({discount_days} Tage) >= "
                    f"Zahlungsziel ({payment_days} Tage)"
                ),
                severity=Severity.ERROR,
                suggested_fix="Skontofrist sollte kürzer als Zahlungsziel sein",
            ))

        if not any(not r.is_valid for r in results):
            results.append(ValidationResult(
                is_valid=True,
                field_name="skonto",
                validation_type="skonto_plausibility",
                message=f"Skonto plausibel: {discount_percent}% bei {discount_days} Tagen",
                severity=Severity.INFO,
            ))

        return results

    def _validate_line_item_math(
        self,
        data: InvoiceValidationInput,
    ) -> List[ValidationResult]:
        """Validate qty * unit_price = total for each line item."""
        results: List[ValidationResult] = []

        for idx, item in enumerate(data.line_items):
            if not item.validate_math():
                expected = item.quantity * item.unit_price if item.quantity and item.unit_price else None
                results.append(ValidationResult(
                    is_valid=False,
                    field_name=f"line_item_{idx + 1}",
                    validation_type="line_item_math",
                    message=(
                        f"Position {idx + 1}: "
                        f"{item.quantity} x {item.unit_price} = {expected}, "
                        f"aber angegeben ist {item.total_price}"
                    ),
                    severity=Severity.WARNING,
                    details={
                        "position": idx + 1,
                        "description": item.description[:50],
                        "quantity": float(item.quantity) if item.quantity else None,
                        "unit_price": float(item.unit_price) if item.unit_price else None,
                        "total_price": float(item.total_price) if item.total_price else None,
                    },
                ))

        return results


# Singleton instance
_validator: Optional[CrossFieldValidator] = None


def get_cross_field_validator() -> CrossFieldValidator:
    """Get singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = CrossFieldValidator()
    return _validator
