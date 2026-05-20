"""
Smart Amount Extractor.

Context-aware extraction of monetary amounts:
- Labeled amounts (Netto, Brutto, MwSt)
- Unlabeled amounts with positional inference
- VAT rate detection
- Consistency validation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Set

import structlog

from app.services.extraction.base import (
    AmountType,
    Currency,
    DocumentAmounts,
    ExtractionConfig,
    ExtractedAmount,
)
from app.services.extraction.config import (
    GERMAN_VAT_RATES,
    MAX_AMOUNT_VALUE,
    MIN_AMOUNT_VALUE,
)
from app.services.extraction.patterns.amount_patterns import (

    AmountPatterns,
    extract_all_amounts,
    extract_vat_rate,
)

logger = structlog.get_logger(__name__)


@dataclass
class AmountExtractionResult:
    """Result of amount extraction with inference."""

    # Document-level amounts
    net_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None

    # Confidence scores
    net_confidence: float = 0.0
    gross_confidence: float = 0.0
    vat_confidence: float = 0.0

    # All extracted amounts (for debugging/reference)
    all_amounts: List[ExtractedAmount] = field(default_factory=list)

    # Quality metrics
    is_consistent: bool = True
    """Whether Net + VAT = Gross within tolerance."""

    inferred_from_math: bool = False
    """Whether any amount was inferred mathematically."""

    extraction_warnings: List[str] = field(default_factory=list)

    def to_document_amounts(self) -> DocumentAmounts:
        """Convert to DocumentAmounts dataclass."""
        return DocumentAmounts(
            net_amount=self.net_amount,
            gross_amount=self.gross_amount,
            vat_amount=self.vat_amount,
            vat_rate=self.vat_rate,
            net_confidence=self.net_confidence,
            gross_confidence=self.gross_confidence,
            vat_confidence=self.vat_confidence,
            all_amounts=self.all_amounts,
        )


class SmartAmountExtractor:
    """
    Extract and infer document amounts with context awareness.

    Strategies:
    1. Use labeled amounts (highest confidence)
    2. Positional inference (right-aligned amounts often totals)
    3. Mathematical inference (Net + VAT = Gross)
    4. VAT rate inference from common rates
    """

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or ExtractionConfig()
        self.patterns = AmountPatterns()

    def extract(self, text: str) -> AmountExtractionResult:
        """
        Extract all amounts with smart inference.

        Args:
            text: Document text

        Returns:
            AmountExtractionResult with inferred amounts
        """
        result = AmountExtractionResult()

        try:
            # Step 1: Extract all amounts with context
            result.all_amounts = extract_all_amounts(
                text,
                context_window=self.config.context_window,
            )

            # Filter implausible amounts
            result.all_amounts = self._filter_amounts(result.all_amounts)

            logger.debug(
                "amounts_extracted",
                count=len(result.all_amounts),
                labeled=sum(1 for a in result.all_amounts if a.amount_type != AmountType.UNKNOWN),
            )

            # Step 2: Use labeled amounts (highest confidence)
            self._apply_labeled_amounts(result)

            # Step 3: Positional inference for missing amounts
            self._apply_positional_inference(result)

            # Step 4: Mathematical inference
            self._apply_mathematical_inference(result)

            # Step 5: VAT rate inference
            self._infer_vat_rate(result, text)

            # Step 6: Reverse Charge handling
            # (must be before consistency check)
            self._handle_reverse_charge(result, text)

            # Step 7: Validate consistency
            self._validate_consistency(result)

        except Exception as e:
            logger.exception("amount_extraction_error", **safe_error_log(e))
            result.extraction_warnings.append(f"Extraktionsfehler: {e}")

        return result

    def _filter_amounts(self, amounts: List[ExtractedAmount]) -> List[ExtractedAmount]:
        """Filter out implausible amounts."""
        filtered = []
        for amount in amounts:
            # Skip amounts outside valid range
            if amount.value < MIN_AMOUNT_VALUE:
                continue
            if amount.value > MAX_AMOUNT_VALUE:
                continue
            # Skip amounts with very low confidence
            if amount.confidence < self.config.min_amount_confidence:
                continue
            filtered.append(amount)
        return filtered

    def _apply_labeled_amounts(self, result: AmountExtractionResult) -> None:
        """Apply amounts that were explicitly labeled."""
        # Collect candidates for each type
        net_candidates: List[ExtractedAmount] = []
        gross_candidates: List[ExtractedAmount] = []
        vat_candidates: List[ExtractedAmount] = []

        for amount in result.all_amounts:
            # Skip obviously wrong amounts (too small to be invoice amounts)
            if amount.value < Decimal("1"):
                continue

            if amount.amount_type == AmountType.NET and amount.confidence >= 0.7:
                net_candidates.append(amount)
            elif amount.amount_type == AmountType.GROSS and amount.confidence >= 0.7:
                gross_candidates.append(amount)
            elif amount.amount_type == AmountType.VAT and amount.confidence >= 0.7:
                vat_candidates.append(amount)

        # Select best NET: prefer higher confidence, then higher value
        if net_candidates:
            # Sort by confidence desc, then by value desc (larger amounts more likely correct)
            net_candidates.sort(key=lambda a: (a.confidence, a.value), reverse=True)
            best = net_candidates[0]
            result.net_amount = best.value
            result.net_confidence = best.confidence
            logger.debug(
                "labeled_net_applied",
                value=best.value,
                confidence=best.confidence,
            )

        # Select best GROSS: prefer higher confidence, then higher value (gross > net)
        if gross_candidates:
            # Filter out unlikely gross values (gross should be > net if net is known)
            if result.net_amount:
                gross_candidates = [
                    a for a in gross_candidates
                    if a.value >= result.net_amount
                ] or gross_candidates  # Keep all if filter removes everything
            # Sort by confidence desc, then by value desc
            gross_candidates.sort(key=lambda a: (a.confidence, a.value), reverse=True)
            best = gross_candidates[0]
            result.gross_amount = best.value
            result.gross_confidence = best.confidence
            logger.debug(
                "labeled_gross_applied",
                value=best.value,
                confidence=best.confidence,
            )

        # Select best VAT: prefer with rate, then higher confidence
        if vat_candidates:
            # Prefer VAT amounts with explicit rate
            with_rate = [a for a in vat_candidates if a.vat_rate]
            if with_rate:
                with_rate.sort(key=lambda a: a.confidence, reverse=True)
                best = with_rate[0]
            else:
                vat_candidates.sort(key=lambda a: a.confidence, reverse=True)
                best = vat_candidates[0]
            result.vat_amount = best.value
            result.vat_confidence = best.confidence
            if best.vat_rate:
                result.vat_rate = best.vat_rate
            logger.debug(
                "labeled_vat_applied",
                value=best.value,
                rate=best.vat_rate,
                confidence=best.confidence,
            )

    def _apply_positional_inference(self, result: AmountExtractionResult) -> None:
        """Infer amounts from position (right-aligned amounts are often totals)."""
        if result.gross_amount is not None:
            return  # Already have gross

        # Find right-aligned amounts (potential totals)
        right_amounts = [
            a for a in result.all_amounts
            if a.line_position == "right" and a.amount_type == AmountType.UNKNOWN
        ]

        if not right_amounts:
            return

        # Sort by position (later = more likely to be total)
        right_amounts.sort(key=lambda a: a.position[0], reverse=True)

        # Take the last (lowest on page) large right-aligned amount as gross
        for amount in right_amounts:
            # Skip if it's likely a VAT amount (near VAT indicators)
            if self._is_likely_vat_context(amount):
                continue

            # Skip if significantly smaller than other amounts (might be VAT)
            if result.net_amount and amount.value < result.net_amount * Decimal("0.5"):
                continue

            result.gross_amount = amount.value
            result.gross_confidence = 0.60  # Lower confidence for inferred
            logger.debug(
                "positional_gross_inferred",
                value=amount.value,
                position=amount.position,
            )
            break

    def _is_likely_vat_context(self, amount: ExtractedAmount) -> bool:
        """Check if amount context suggests VAT."""
        context = (amount.context_before + amount.context_after).lower()
        vat_indicators = {"mwst", "ust", "steuer", "vat", "tax", "%"}
        return any(ind in context for ind in vat_indicators)

    def _apply_mathematical_inference(self, result: AmountExtractionResult) -> None:
        """Infer missing amounts using math: Net + VAT = Gross."""
        # Case 1: Have Net and VAT, missing Gross
        if (
            result.net_amount is not None and
            result.vat_amount is not None and
            result.gross_amount is None
        ):
            result.gross_amount = result.net_amount + result.vat_amount
            result.gross_confidence = 0.80
            result.inferred_from_math = True
            logger.debug(
                "gross_inferred_from_math",
                net=result.net_amount,
                vat=result.vat_amount,
                gross=result.gross_amount,
            )

        # Case 2: Have Net and Gross, missing VAT
        elif (
            result.net_amount is not None and
            result.gross_amount is not None and
            result.vat_amount is None
        ):
            result.vat_amount = result.gross_amount - result.net_amount
            result.vat_confidence = 0.80
            result.inferred_from_math = True
            logger.debug(
                "vat_inferred_from_math",
                gross=result.gross_amount,
                net=result.net_amount,
                vat=result.vat_amount,
            )

        # Case 3: Have VAT and Gross, missing Net
        elif (
            result.vat_amount is not None and
            result.gross_amount is not None and
            result.net_amount is None
        ):
            result.net_amount = result.gross_amount - result.vat_amount
            result.net_confidence = 0.80
            result.inferred_from_math = True
            logger.debug(
                "net_inferred_from_math",
                gross=result.gross_amount,
                vat=result.vat_amount,
                net=result.net_amount,
            )

    def _infer_vat_rate(self, result: AmountExtractionResult, text: str) -> None:
        """Infer VAT rate from amounts or text."""
        # Already have rate from labeled amount
        if result.vat_rate is not None:
            return

        # Try to extract rate from text
        rate = extract_vat_rate(text)
        if rate is not None:
            result.vat_rate = rate
            return

        # Infer from Net and VAT amounts
        if result.net_amount and result.vat_amount and result.net_amount > 0:
            calculated_rate = (result.vat_amount / result.net_amount) * 100

            # Round to nearest common rate
            for common_rate in GERMAN_VAT_RATES:
                if abs(calculated_rate - common_rate) <= Decimal("0.5"):
                    result.vat_rate = common_rate
                    logger.debug(
                        "vat_rate_inferred",
                        calculated=calculated_rate,
                        matched=common_rate,
                    )
                    return

            # Rate doesn't match common rates
            result.extraction_warnings.append(
                f"Berechneter MwSt-Satz ({calculated_rate:.1f}%) "
                f"entspricht keinem Standardsatz"
            )

    def _validate_consistency(self, result: AmountExtractionResult) -> None:
        """Validate that Net + VAT = Gross within tolerance."""
        if not (result.net_amount and result.vat_amount and result.gross_amount):
            return

        expected_gross = result.net_amount + result.vat_amount
        diff = abs(expected_gross - result.gross_amount)

        if diff > self.config.amount_tolerance:
            result.is_consistent = False
            result.extraction_warnings.append(
                f"Betragsinkonsistenz: {result.net_amount} + {result.vat_amount} = "
                f"{expected_gross} (erwartet: {result.gross_amount}, "
                f"Differenz: {diff})"
            )
            logger.warning(
                "amount_inconsistency",
                net=result.net_amount,
                vat=result.vat_amount,
                expected=expected_gross,
                actual=result.gross_amount,
                diff=diff,
            )

    # =========================================================================
    # REVERSE CHARGE HANDLING
    # =========================================================================

    # Indikatoren für Reverse Charge / innergemeinschaftliche Lieferung
    REVERSE_CHARGE_INDICATORS: frozenset[str] = frozenset([
        "reverse charge",
        "steuerschuldnerschaft",
        "innergemeinschaftliche lieferung",
        "intra-community",
        "intracommunautaire",
        "btw verlegd",  # Dutch
        "vat exempt",
        "0% vat",
        "0% mwst",
        "vat 0%",
        "mwst 0%",
        "exempt from vat",
        "steuerfreie lieferung",
        "tax exempt",
    ])

    # Pattern für EU VAT-IDs (ausser DE)
    _EU_VAT_ID_PATTERN = re.compile(
        r'\b(AT|BE|BG|CY|CZ|DK|EE|FI|FR|GR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK)'
        r'[A-Z0-9]{8,12}\b',
        re.IGNORECASE,
    )
    _DE_VAT_ID_PATTERN = re.compile(r'\bDE\d{9}\b', re.IGNORECASE)

    def _detect_reverse_charge(self, text: str) -> bool:
        """
        Detect if invoice is Reverse Charge (no VAT applies).

        Indicators:
        - "Reverse Charge" explicit mention
        - "Steuerschuldnerschaft des Leistungsempfängers"
        - "innergemeinschaftliche Lieferung"
        - "BTW verlegd" (Dutch)
        - "0% MwSt" or "VAT 0%"
        - Cross-border VAT-IDs (EU sender + DE recipient)
        """
        text_lower = text.lower()

        # Check explicit indicators
        if any(ind in text_lower for ind in self.REVERSE_CHARGE_INDICATORS):
            return True

        # Check for cross-border EU transaction (implied reverse charge)
        # If we have both a non-DE EU VAT-ID AND a DE VAT-ID, it's likely intra-EU
        has_eu_vat = self._EU_VAT_ID_PATTERN.search(text) is not None
        has_de_vat = self._DE_VAT_ID_PATTERN.search(text) is not None

        if has_eu_vat and has_de_vat:
            logger.debug(
                "cross_border_eu_transaction_detected",
                eu_vat=has_eu_vat,
                de_vat=has_de_vat,
            )
            return True

        return False

    def _handle_reverse_charge(
        self,
        result: AmountExtractionResult,
        text: str,
    ) -> None:
        """
        Reclassify amounts when Reverse Charge applies.

        In Reverse Charge scenarios:
        - No VAT on invoice
        - "Total" = Net amount (not Gross)
        - Gross should be None or same as Net

        Only applies when:
        - Reverse Charge indicator is present
        - VAT amount is None or 0

        Handles two cases:
        1. Gross present, Net missing/small -> Move Gross to Net
        2. Net == Gross (same value) -> Keep Net, clear Gross
        """
        # Check if Reverse Charge applies
        if not self._detect_reverse_charge(text):
            return

        # Check if VAT is missing or zero (required for Reverse Charge)
        vat_missing_or_zero = (
            result.vat_amount is None or
            result.vat_amount == Decimal("0")
        )

        if not vat_missing_or_zero:
            # Has VAT amount > 0, not a Reverse Charge scenario
            return

        # Case 1: Gross present, Net missing/small - swap them
        if (
            result.gross_amount is not None
            and (result.net_amount is None or result.net_amount < Decimal("1"))
        ):
            logger.info(
                "reverse_charge_detected",
                case="gross_to_net",
                gross_was=result.gross_amount,
                net_was=result.net_amount,
            )

            # "Total" was actually Net in Reverse Charge context
            result.net_amount = result.gross_amount
            result.net_confidence = result.gross_confidence
            # Bei Reverse Charge: Brutto = Netto (nicht None!)
            result.gross_amount = result.net_amount
            result.gross_confidence = result.net_confidence

            # Explicitly set VAT to 0
            result.vat_amount = Decimal("0")
            result.vat_rate = Decimal("0")
            result.vat_confidence = 0.8

            result.extraction_warnings.append(
                "Reverse Charge erkannt: Brutto = Netto (MwSt entfaellt)"
            )

        # Case 2: Net == Gross (both same value) - keep both
        elif (
            result.net_amount is not None
            and result.gross_amount is not None
            and result.net_amount == result.gross_amount
        ):
            logger.info(
                "reverse_charge_detected",
                case="net_equals_gross",
                net=result.net_amount,
                gross=result.gross_amount,
            )

            # Bei Reverse Charge: Brutto = Netto BEHALTEN (nicht löschen!)
            # result.gross_amount bleibt unverändert

            # Ensure VAT is set to 0
            if result.vat_amount is None:
                result.vat_amount = Decimal("0")
            result.vat_rate = Decimal("0")
            result.vat_confidence = 0.8

            result.extraction_warnings.append(
                "Reverse Charge erkannt: Brutto = Netto (MwSt entfaellt)"
            )


# Singleton instance
_amount_extractor: Optional[SmartAmountExtractor] = None


def get_amount_extractor() -> SmartAmountExtractor:
    """Get singleton amount extractor instance."""
    global _amount_extractor
    if _amount_extractor is None:
        _amount_extractor = SmartAmountExtractor()
    return _amount_extractor
