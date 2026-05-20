"""
Payment Terms Extractor.

Extracts and validates payment terms from German documents:
- Payment days (Zahlungsziel)
- Discount tiers (Skonto)
- Due dates (Fälligkeitsdatum)
- Special conditions (Vorauskasse, Monatsende, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

import structlog

from app.services.extraction.base import DiscountTier, ExtractionConfig
from app.core.safe_errors import safe_error_log
from app.services.extraction.config import (
    MAX_PAYMENT_DAYS,
    MAX_SKONTO_DAYS,
    MAX_SKONTO_PERCENT,
)
from app.services.extraction.patterns.payment_patterns import (

    PaymentPatterns,
    calculate_end_of_month,
    extract_all_discount_tiers,
    is_end_of_month,
    is_immediate_payment,
    is_prepayment,
    parse_explicit_due_date,
)

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedPaymentTerms:
    """Structured payment terms extraction result."""

    # Core payment information
    payment_days: Optional[int] = None
    """Number of days for payment (e.g., 30 for "NET 30")."""

    due_date: Optional[date] = None
    """Calculated or explicit due date."""

    # Payment type flags
    is_immediate: bool = False
    """Payment is due immediately."""

    is_prepayment: bool = False
    """Prepayment/proforma is required."""

    is_end_of_month: bool = False
    """Payment due at end of month."""

    is_end_of_following_month: bool = False
    """Payment due at end of following month."""

    # Discount information
    discount_tiers: List[DiscountTier] = field(default_factory=list)
    """Discount tiers (e.g., 2% if paid within 10 days)."""

    # Additional info
    payment_method: Optional[str] = None
    """Detected payment method (Überweisung, Nachnahme, etc.)."""

    late_interest_rate: Optional[Decimal] = None
    """Late payment interest rate (Verzugszinsen)."""

    # Quality metrics
    confidence: float = 0.0
    """Overall extraction confidence 0.0 - 1.0."""

    needs_review: bool = False
    """Flag indicating human review recommended."""

    extraction_warnings: List[str] = field(default_factory=list)
    """Warnings encountered during extraction."""

    raw_text: Optional[str] = None
    """Original text that was matched."""

    @property
    def has_skonto(self) -> bool:
        """Check if any discount is available."""
        return any(tier.percent > 0 for tier in self.discount_tiers)

    @property
    def best_discount(self) -> Optional[DiscountTier]:
        """Get the best available discount (highest percentage)."""
        valid_tiers = [t for t in self.discount_tiers if t.percent > 0]
        return max(valid_tiers, key=lambda t: t.percent) if valid_tiers else None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "payment_days": self.payment_days,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "is_immediate": self.is_immediate,
            "is_prepayment": self.is_prepayment,
            "is_end_of_month": self.is_end_of_month,
            "discount_tiers": [
                {"percent": float(t.percent), "days": t.days}
                for t in self.discount_tiers
            ],
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "warnings": self.extraction_warnings,
        }


class PaymentTermsExtractor:
    """
    Extract and validate payment terms from text.

    Handles:
    - Standard payment days ("Zahlbar innerhalb 30 Tagen")
    - International formats ("NET 30", "2/10 net 30")
    - Immediate payment ("sofort fällig", "Vorauskasse")
    - End of month terms
    - Multiple discount tiers
    - Due date calculation and validation
    """

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or ExtractionConfig()
        self.patterns = PaymentPatterns()

    def extract(
        self,
        text: str,
        invoice_date: Optional[date] = None,
    ) -> ExtractedPaymentTerms:
        """
        Extract payment terms from text.

        Args:
            text: Document text
            invoice_date: Invoice date for due date calculation

        Returns:
            Structured payment terms
        """
        result = ExtractedPaymentTerms()

        try:
            # Step 1: Check for prepayment (highest priority)
            if is_prepayment(text):
                result.is_prepayment = True
                result.is_immediate = True
                result.payment_days = 0
                result.confidence = 0.90
                result.raw_text = self._find_prepayment_text(text)
                logger.debug("payment_prepayment_detected", raw_text=result.raw_text)
                return result

            # Step 2: Check for immediate payment
            if is_immediate_payment(text):
                result.is_immediate = True
                result.payment_days = 0
                result.confidence = 0.85
                result.raw_text = self._find_immediate_text(text)
                logger.debug("payment_immediate_detected", raw_text=result.raw_text)
                return result

            # Step 3: Extract discount tiers
            result.discount_tiers = extract_all_discount_tiers(text)
            if result.discount_tiers:
                # Get net days from last tier (e.g., "netto 30")
                net_tier = next(
                    (t for t in result.discount_tiers if t.percent == 0),
                    None,
                )
                if net_tier:
                    result.payment_days = net_tier.days

            # Step 4: Extract payment days (if not from discount)
            if result.payment_days is None:
                result.payment_days = self._extract_payment_days(text)

            # Step 5: Check end of month patterns
            result.is_end_of_month = is_end_of_month(text)
            if result.is_end_of_month:
                # Check if following month
                result.is_end_of_following_month = self._is_following_month(text)

            # Step 6: Calculate due date
            if invoice_date:
                result.due_date = self._calculate_due_date(
                    invoice_date,
                    result.payment_days,
                    result.is_end_of_month,
                    result.is_end_of_following_month,
                )

            # Step 7: Extract explicit due date (may override calculated)
            explicit_due = parse_explicit_due_date(text, invoice_date.year if invoice_date else None)
            if explicit_due:
                # Validate against calculated
                if result.due_date and self.config.validate_due_date:
                    diff = abs((explicit_due - result.due_date).days)
                    if diff > self.config.due_date_tolerance_days:
                        result.extraction_warnings.append(
                            f"Berechnetes Fälligkeitsdatum ({result.due_date}) "
                            f"weicht von explizitem ({explicit_due}) ab ({diff} Tage)"
                        )
                        result.needs_review = True
                result.due_date = explicit_due

            # Step 8: Extract late interest rate
            result.late_interest_rate = self._extract_late_interest(text)

            # Step 9: Validate results
            self._validate_results(result)

            # Step 10: Calculate confidence
            result.confidence = self._calculate_confidence(result)

        except Exception as e:
            logger.exception("payment_extraction_error", **safe_error_log(e))
            result.extraction_warnings.append(f"Extraktionsfehler: {e}")
            result.needs_review = True

        return result

    def _extract_payment_days(self, text: str) -> Optional[int]:
        """Extract payment days from various patterns."""
        # Try patterns in order of specificity
        for pattern in [
            self.patterns.PAYMENT_DAYS_BASIC,
            self.patterns.PAYMENT_DAYS_NET,
            self.patterns.PAYMENT_DAYS_ALT,
            self.patterns.PAYMENT_DAYS_RELATIVE,
        ]:
            match = pattern.search(text)
            if match:
                days = int(match.group("days"))
                # Accept any positive value - validation/warning happens later
                if days > 0:
                    return days

        return None

    def _is_following_month(self, text: str) -> bool:
        """Check if end of following month."""
        return bool(self.patterns.END_OF_FOLLOWING_MONTH.search(text))

    def _calculate_due_date(
        self,
        invoice_date: date,
        payment_days: Optional[int],
        is_eom: bool,
        is_following_eom: bool,
    ) -> Optional[date]:
        """Calculate due date from invoice date and terms."""
        if is_following_eom:
            return calculate_end_of_month(invoice_date, following=True)
        if is_eom:
            return calculate_end_of_month(invoice_date, following=False)
        if payment_days is not None:
            return invoice_date + timedelta(days=payment_days)
        return None

    def _extract_late_interest(self, text: str) -> Optional[Decimal]:
        """Extract late payment interest rate."""
        match = self.patterns.LATE_INTEREST.search(text)
        if match:
            rate_str = match.group("rate").replace(",", ".")
            return Decimal(rate_str)
        return None

    def _find_prepayment_text(self, text: str) -> Optional[str]:
        """Find the prepayment indicator text."""
        match = self.patterns.PREPAYMENT.search(text)
        return match.group() if match else None

    def _find_immediate_text(self, text: str) -> Optional[str]:
        """Find the immediate payment text."""
        match = self.patterns.PAYMENT_IMMEDIATE.search(text)
        return match.group() if match else None

    def _validate_results(self, result: ExtractedPaymentTerms) -> None:
        """Validate extracted results and add warnings."""
        # Validate payment days
        if result.payment_days is not None:
            if result.payment_days > MAX_PAYMENT_DAYS:
                result.extraction_warnings.append(
                    f"Ungewoehnlich langes Zahlungsziel: {result.payment_days} Tage"
                )
                result.needs_review = True
            elif result.payment_days < 0:
                result.extraction_warnings.append(
                    f"Negatives Zahlungsziel: {result.payment_days} Tage"
                )
                result.needs_review = True

        # Validate discount tiers
        for tier in result.discount_tiers:
            if tier.percent > MAX_SKONTO_PERCENT:
                result.extraction_warnings.append(
                    f"Ungewoehnlich hoher Skonto: {tier.percent}%"
                )
                result.needs_review = True

            if tier.days > MAX_SKONTO_DAYS and tier.percent > 0:
                result.extraction_warnings.append(
                    f"Ungewoehnlich lange Skontofrist: {tier.days} Tage"
                )
                result.needs_review = True

            # Skonto days should be less than payment days
            if (
                result.payment_days is not None and
                tier.percent > 0 and
                tier.days >= result.payment_days
            ):
                result.extraction_warnings.append(
                    f"Skontofrist ({tier.days} Tage) >= Zahlungsziel ({result.payment_days} Tage)"
                )
                result.needs_review = True

        # Validate due date
        if result.due_date:
            today = date.today()
            if result.due_date < today - timedelta(days=365):
                result.extraction_warnings.append(
                    f"Fälligkeitsdatum liegt mehr als 1 Jahr in der Vergangenheit"
                )
                result.needs_review = True

    def _calculate_confidence(self, result: ExtractedPaymentTerms) -> float:
        """Calculate overall extraction confidence."""
        confidence = 0.5  # Base confidence

        # Boost for found values
        if result.payment_days is not None or result.is_immediate or result.is_prepayment:
            confidence += 0.2

        if result.due_date:
            confidence += 0.1

        if result.discount_tiers:
            confidence += 0.1

        # Reduce for warnings
        confidence -= len(result.extraction_warnings) * 0.1

        # Reduce if needs review
        if result.needs_review:
            confidence -= 0.1

        return max(0.1, min(0.99, confidence))


# Singleton instance
_payment_extractor: Optional[PaymentTermsExtractor] = None


def get_payment_extractor() -> PaymentTermsExtractor:
    """Get singleton payment extractor instance."""
    global _payment_extractor
    if _payment_extractor is None:
        _payment_extractor = PaymentTermsExtractor()
    return _payment_extractor
