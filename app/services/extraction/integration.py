"""
Integration Layer for Enhanced Extraction.

Provides an adapter to integrate the new extraction modules
with the existing StructuredExtractionService.

Can be enabled via feature flag for gradual rollout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

import structlog

from app.services.extraction.base import ExtractionConfig
from app.services.extraction.extractors.payment_extractor import (
    ExtractedPaymentTerms,
    PaymentTermsExtractor,
)
from app.services.extraction.extractors.amount_extractor import (
    AmountExtractionResult,
    SmartAmountExtractor,
)
from app.services.extraction.extractors.line_item_extractor import (
    EnhancedLineItemExtractor,
    ExtractedLineItem,
)
from app.services.extraction.validators.cross_field_validator import (
    CrossFieldValidator,
    InvoiceValidationInput,
    ValidationResult,
)
from app.services.extraction.config import get_default_config
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# Feature flag for enabling new extraction
ENABLE_ENHANCED_EXTRACTION = os.getenv("ENABLE_ENHANCED_EXTRACTION", "true").lower() == "true"


@dataclass
class EnhancedExtractionResult:
    """Combined result from all enhanced extractors."""

    # Payment terms
    payment_terms: Optional[ExtractedPaymentTerms] = None

    # Amounts
    amounts: Optional[AmountExtractionResult] = None

    # Line items
    line_items: List[ExtractedLineItem] = field(default_factory=list)

    # Validation
    validations: List[ValidationResult] = field(default_factory=list)
    is_valid: bool = True

    # Overall quality
    overall_confidence: float = 0.0
    needs_review: bool = False
    extraction_warnings: List[str] = field(default_factory=list)


class EnhancedExtractionAdapter:
    """
    Adapter for integrating enhanced extraction with existing services.

    Usage:
        adapter = EnhancedExtractionAdapter()

        # Extract all data
        result = adapter.extract_all(text, invoice_date=invoice_date, tables=tables)

        # Or extract components individually
        payment = adapter.extract_payment_terms(text, invoice_date)
        amounts = adapter.extract_amounts(text)
        items = adapter.extract_line_items(tables)

        # Validate
        validations = adapter.validate(result)
    """

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or get_default_config()
        self._payment_extractor: Optional[PaymentTermsExtractor] = None
        self._amount_extractor: Optional[SmartAmountExtractor] = None
        self._line_item_extractor: Optional[EnhancedLineItemExtractor] = None
        self._validator: Optional[CrossFieldValidator] = None

    @property
    def payment_extractor(self) -> PaymentTermsExtractor:
        """Lazy-load payment extractor."""
        if self._payment_extractor is None:
            self._payment_extractor = PaymentTermsExtractor(self.config)
        return self._payment_extractor

    @property
    def amount_extractor(self) -> SmartAmountExtractor:
        """Lazy-load amount extractor."""
        if self._amount_extractor is None:
            self._amount_extractor = SmartAmountExtractor(self.config)
        return self._amount_extractor

    @property
    def line_item_extractor(self) -> EnhancedLineItemExtractor:
        """Lazy-load line item extractor."""
        if self._line_item_extractor is None:
            self._line_item_extractor = EnhancedLineItemExtractor(self.config)
        return self._line_item_extractor

    @property
    def validator(self) -> CrossFieldValidator:
        """Lazy-load validator."""
        if self._validator is None:
            self._validator = CrossFieldValidator(self.config)
        return self._validator

    def extract_all(
        self,
        text: str,
        invoice_date: Optional[date] = None,
        tables: Optional[List[Any]] = None,
    ) -> EnhancedExtractionResult:
        """
        Run all extractors and validations.

        Args:
            text: Document text
            invoice_date: Invoice date for due date calculation
            tables: Table structures for line item extraction

        Returns:
            Combined extraction result
        """
        result = EnhancedExtractionResult()

        try:
            # 1. Extract payment terms
            result.payment_terms = self.extract_payment_terms(text, invoice_date)
            if result.payment_terms.extraction_warnings:
                result.extraction_warnings.extend(result.payment_terms.extraction_warnings)
            if result.payment_terms.needs_review:
                result.needs_review = True

            # 2. Extract amounts
            result.amounts = self.extract_amounts(text)
            if result.amounts.extraction_warnings:
                result.extraction_warnings.extend(result.amounts.extraction_warnings)
            if not result.amounts.is_consistent:
                result.needs_review = True

            # 3. Extract line items mit Text-Fallback
            line_items: List[ExtractedLineItem] = []

            if tables:
                line_items = self.extract_line_items(tables)
                logger.debug(
                    "table_extraction_result",
                    item_count=len(line_items),
                    has_quality_issues=self._has_low_quality_items(line_items),
                )

            # Fallback: Wenn keine oder schlechte Line Items, versuche Text-Extraktion
            if not line_items or self._has_low_quality_items(line_items):
                text_items = self.line_item_extractor.extract_from_text(text)
                logger.debug(
                    "text_extraction_fallback",
                    table_items=len(line_items),
                    text_items=len(text_items),
                )

                if text_items and self._is_better_extraction(text_items, line_items):
                    logger.info(
                        "using_text_extraction_over_tables",
                        reason="text_extraction_better_quality",
                        table_items=len(line_items),
                        text_items=len(text_items),
                    )
                    line_items = text_items

            result.line_items = line_items

            # 4. Validate
            result.validations, result.is_valid = self.validate(result, invoice_date)

            # 5. Calculate overall confidence
            result.overall_confidence = self._calculate_overall_confidence(result)

            logger.info(
                "enhanced_extraction_complete",
                has_payment_terms=result.payment_terms.payment_days is not None,
                has_amounts=result.amounts.gross_amount is not None,
                line_item_count=len(result.line_items),
                is_valid=result.is_valid,
                confidence=result.overall_confidence,
            )

        except Exception as e:
            logger.exception("enhanced_extraction_error", **safe_error_log(e))
            result.extraction_warnings.append(f"Extraktionsfehler: {e}")
            result.needs_review = True

        return result

    def extract_payment_terms(
        self,
        text: str,
        invoice_date: Optional[date] = None,
    ) -> ExtractedPaymentTerms:
        """Extract payment terms from text."""
        return self.payment_extractor.extract(text, invoice_date)

    def extract_amounts(self, text: str) -> AmountExtractionResult:
        """Extract amounts from text."""
        return self.amount_extractor.extract(text)

    def extract_line_items(
        self,
        tables: List[Any],
    ) -> List[ExtractedLineItem]:
        """Extract line items from tables."""
        return self.line_item_extractor.extract_from_tables(tables)

    def validate(
        self,
        result: EnhancedExtractionResult,
        invoice_date: Optional[date] = None,
    ) -> tuple[List[ValidationResult], bool]:
        """
        Run validations on extraction result.

        Returns:
            Tuple of (validation_results, all_valid)
        """
        # Build validation input
        validation_input = InvoiceValidationInput(
            invoice_date=invoice_date,
            due_date=result.payment_terms.due_date if result.payment_terms else None,
            net_amount=result.amounts.net_amount if result.amounts else None,
            vat_amount=result.amounts.vat_amount if result.amounts else None,
            gross_amount=result.amounts.gross_amount if result.amounts else None,
            vat_rate=result.amounts.vat_rate if result.amounts else None,
            payment_terms=result.payment_terms,
            line_items=result.line_items,
        )

        # validate_all returns (all_valid, results), swap to (results, all_valid)
        all_valid, results = self.validator.validate_all(validation_input)
        return (results, all_valid)

    def _calculate_overall_confidence(
        self,
        result: EnhancedExtractionResult,
    ) -> float:
        """Calculate overall extraction confidence."""
        confidence = 0.5  # Base

        # Payment terms contribution
        if result.payment_terms:
            confidence += result.payment_terms.confidence * 0.2

        # Amounts contribution
        if result.amounts:
            if result.amounts.gross_amount:
                confidence += result.amounts.gross_confidence * 0.2
            if result.amounts.is_consistent:
                confidence += 0.1

        # Line items contribution
        if result.line_items:
            avg_item_confidence = sum(i.confidence for i in result.line_items) / len(result.line_items)
            confidence += avg_item_confidence * 0.1

        # Validation penalty
        error_count = sum(
            1 for v in result.validations
            if not v.is_valid and v.severity.value == "error"
        )
        confidence -= error_count * 0.1

        return max(0.1, min(0.99, confidence))

    def _has_low_quality_items(self, items: List[ExtractedLineItem]) -> bool:
        """
        Prüft ob die extrahierten Items verdächtig schlecht sind.

        Erkennt typische Probleme wie:
        - Header-Text in Beschreibung
        - Null-Preise
        - Unplausible Werte
        """
        if not items:
            return True

        # Header-Begriffe die NICHT in Beschreibungen vorkommen sollten
        header_indicators = [
            'description', 'beschreibung', 'quantity', 'menge',
            'amount', 'betrag', 'price', 'preis', 'no.', 'nr.',
            'unit', 'einheit', 'total', 'summe', 'pos.', 'artikel',
            'article', 'item', 'position'
        ]

        for item in items:
            desc_lower = (item.description or "").lower().strip()

            # Prüfe auf Header-Text in Beschreibung
            # Aber nur wenn die Beschreibung SEHR kurz ist (wahrscheinlich nur Header)
            if len(desc_lower) < 20:
                for header in header_indicators:
                    if header in desc_lower:
                        logger.debug(
                            "low_quality_header_in_description",
                            description=item.description,
                            header_found=header,
                        )
                        return True

            # Null-Preise bei vorhandenem Gesamtpreis = verdächtig
            if item.total_price == Decimal(0) and item.unit_price == Decimal(0):
                logger.debug(
                    "low_quality_zero_prices",
                    description=item.description,
                )
                return True

            # Unplausible Mengen (z.B. "1.3" statt "384")
            if item.quantity and item.quantity < Decimal(1) and item.quantity > Decimal(0):
                logger.debug(
                    "low_quality_fractional_quantity",
                    quantity=str(item.quantity),
                    description=item.description,
                )
                return True

        return False

    def _is_better_extraction(
        self,
        new_items: List[ExtractedLineItem],
        old_items: List[ExtractedLineItem],
    ) -> bool:
        """
        Vergleicht zwei Extraktionen und entscheidet welche besser ist.

        Kriterien:
        - Weniger Qualitätsprobleme
        - Höhere Confidence-Werte
        - Plausiblere Preise/Mengen
        """
        if not new_items:
            return False
        if not old_items:
            return True

        # Wenn alte Items Qualitätsprobleme haben, neue aber nicht
        old_has_issues = self._has_low_quality_items(old_items)
        new_has_issues = self._has_low_quality_items(new_items)

        if old_has_issues and not new_has_issues:
            return True
        if new_has_issues and not old_has_issues:
            return False

        # Vergleiche durchschnittliche Confidence
        old_confidence = sum(i.confidence for i in old_items) / len(old_items)
        new_confidence = sum(i.confidence for i in new_items) / len(new_items)

        if new_confidence > old_confidence + 0.1:
            return True

        # Vergleiche ob Preise plausibel sind (nicht 0)
        old_has_prices = any(
            i.total_price and i.total_price > Decimal(0) for i in old_items
        )
        new_has_prices = any(
            i.total_price and i.total_price > Decimal(0) for i in new_items
        )

        if new_has_prices and not old_has_prices:
            return True

        return False


def convert_to_schema_line_item(
    item: ExtractedLineItem,
) -> Dict[str, Any]:
    """
    Convert enhanced ExtractedLineItem to schema format.

    For compatibility with existing ExtractedInvoiceData.line_items.
    """
    return {
        "position": item.position,
        "description": item.description,
        "quantity": float(item.quantity) if item.quantity else None,
        "unit": item.unit,
        "unit_price": float(item.unit_price) if item.unit_price else None,
        "total_price": float(item.total_price) if item.total_price else None,
        "vat_rate": float(item.vat_rate) if item.vat_rate else None,
        "article_number": item.article_number,
    }


def apply_enhanced_extraction(
    text: str,
    invoice_date: Optional[date] = None,
    tables: Optional[List[Any]] = None,
    existing_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply enhanced extraction and merge with existing data.

    This is the main entry point for integrating with StructuredExtractionService.

    Args:
        text: Document text
        invoice_date: Invoice date
        tables: Table structures
        existing_data: Data extracted by existing service

    Returns:
        Merged data dictionary
    """
    if not ENABLE_ENHANCED_EXTRACTION:
        logger.debug("enhanced_extraction_disabled")
        return existing_data or {}

    adapter = EnhancedExtractionAdapter()
    result = adapter.extract_all(text, invoice_date, tables)

    # Start with existing data
    merged = dict(existing_data) if existing_data else {}

    # Override/add payment terms if enhanced extraction found them
    if result.payment_terms and result.payment_terms.payment_days is not None:
        merged["payment_days"] = result.payment_terms.payment_days
        merged["due_date"] = result.payment_terms.due_date
        merged["is_immediate_payment"] = result.payment_terms.is_immediate
        merged["is_prepayment"] = result.payment_terms.is_prepayment

        if result.payment_terms.discount_tiers:
            best = result.payment_terms.best_discount
            if best:
                merged["discount_percent"] = float(best.percent)
                merged["discount_days"] = best.days

    # Override/add amounts if enhanced extraction found them
    if result.amounts:
        if result.amounts.net_amount and (
            "net_amount" not in merged or
            result.amounts.net_confidence > 0.7
        ):
            merged["net_amount"] = float(result.amounts.net_amount)

        if result.amounts.gross_amount and (
            "gross_amount" not in merged or
            result.amounts.gross_confidence > 0.7
        ):
            merged["gross_amount"] = float(result.amounts.gross_amount)

        if result.amounts.vat_amount and (
            "vat_amount" not in merged or
            result.amounts.vat_confidence > 0.7
        ):
            merged["vat_amount"] = float(result.amounts.vat_amount)

        if result.amounts.vat_rate:
            merged["vat_rate"] = float(result.amounts.vat_rate)

    # Override/add line items if enhanced extraction found more
    if result.line_items:
        existing_items = merged.get("line_items", [])
        if len(result.line_items) >= len(existing_items):
            merged["line_items"] = [
                convert_to_schema_line_item(item)
                for item in result.line_items
            ]

    # Add validation results
    merged["_enhanced_validation"] = [
        {
            "field": v.field_name,
            "type": v.validation_type,
            "is_valid": v.is_valid,
            "message": v.message,
            "severity": v.severity.value,
        }
        for v in result.validations
    ]

    # Add warnings
    if result.extraction_warnings:
        existing_warnings = merged.get("extraction_warnings", [])
        merged["extraction_warnings"] = existing_warnings + result.extraction_warnings

    # Update needs_review flag
    if result.needs_review:
        merged["needs_review"] = True

    # Update confidence (average with existing)
    existing_confidence = merged.get("extraction_confidence", 0.5)
    merged["extraction_confidence"] = (existing_confidence + result.overall_confidence) / 2

    return merged


# Singleton adapter
_adapter: Optional[EnhancedExtractionAdapter] = None


def get_enhanced_extraction_adapter() -> EnhancedExtractionAdapter:
    """Get singleton adapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = EnhancedExtractionAdapter()
    return _adapter
