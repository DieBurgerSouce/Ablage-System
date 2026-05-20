"""
Extraction Module - Modulare Pattern Library für Document Extraction.

Dieses Modul bietet layout-unabhängige Extraktion für:
- Payment Terms (Zahlungsziele, Skonto)
- Amounts (Netto, Brutto, MwSt)
- Line Items (Positionen)
- Cross-Field Validation

Designed für CPU-Systeme ohne LLM-Abhängigkeit.

Usage:
    from app.services.extraction import (
        EnhancedExtractionAdapter,
        apply_enhanced_extraction,
    )

    # Full extraction
    adapter = EnhancedExtractionAdapter()
    result = adapter.extract_all(text, invoice_date=date, tables=tables)

    # Or use the convenience function
    merged_data = apply_enhanced_extraction(text, invoice_date, tables, existing_data)
"""

from app.services.extraction.base import (
    AmountType,
    Currency,
    DiscountTier,
    DocumentAmounts,
    ExtractionConfig,
    ExtractedAmount,
    Pattern,
    PatternMatch,
    PatternRegistry,
    Severity,
    ValidationResult,
    parse_german_decimal,
)

from app.services.extraction.extractors import (
    EnhancedLineItemExtractor,
    ExtractedLineItem,
    ExtractedPaymentTerms,
    PaymentTermsExtractor,
    SmartAmountExtractor,
)

from app.services.extraction.validators import (
    CrossFieldValidator,
    InvoiceValidationInput,
)

from app.services.extraction.extractors.amount_extractor import (
    AmountExtractionResult,
)

from app.services.extraction.integration import (
    EnhancedExtractionAdapter,
    EnhancedExtractionResult,
    apply_enhanced_extraction,
    get_enhanced_extraction_adapter,
    convert_to_schema_line_item,
    ENABLE_ENHANCED_EXTRACTION,
)

from app.services.extraction.config import (
    get_default_config,
    GERMAN_VAT_RATES,
)

__all__ = [
    # Base types
    "PatternMatch",
    "PatternRegistry",
    "Pattern",
    "ExtractedAmount",
    "ExtractionConfig",
    "AmountType",
    "Currency",
    "DiscountTier",
    "DocumentAmounts",
    "Severity",
    "ValidationResult",
    "parse_german_decimal",
    # Extractors
    "PaymentTermsExtractor",
    "ExtractedPaymentTerms",
    "SmartAmountExtractor",
    "EnhancedLineItemExtractor",
    "ExtractedLineItem",
    # Validators
    "CrossFieldValidator",
    "InvoiceValidationInput",
    "AmountExtractionResult",
    # Integration
    "EnhancedExtractionAdapter",
    "EnhancedExtractionResult",
    "apply_enhanced_extraction",
    "get_enhanced_extraction_adapter",
    "convert_to_schema_line_item",
    "ENABLE_ENHANCED_EXTRACTION",
    # Config
    "get_default_config",
    "GERMAN_VAT_RATES",
]
