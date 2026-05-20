"""
Extraction configuration.

Centralized configuration for all extraction modules.
"""

from decimal import Decimal
from typing import FrozenSet

from app.services.extraction.base import ExtractionConfig


def get_default_config() -> ExtractionConfig:
    """Get default extraction configuration for German documents."""
    return ExtractionConfig(
        context_window=30,
        min_amount_confidence=0.5,
        header_keyword_threshold=2,
        header_search_depth=5,
        validate_due_date=True,
        due_date_tolerance_days=3,
        amount_tolerance=Decimal("0.10"),
        line_item_sum_tolerance_percent=Decimal("1.0"),
    )


# Common German VAT rates
GERMAN_VAT_RATES: FrozenSet[Decimal] = frozenset([
    Decimal("0"),      # Tax exempt
    Decimal("7"),      # Reduced rate (food, books, etc.)
    Decimal("19"),     # Standard rate
])

# Austrian VAT rates (for completeness)
AUSTRIAN_VAT_RATES: FrozenSet[Decimal] = frozenset([
    Decimal("0"),
    Decimal("10"),     # Reduced
    Decimal("13"),     # Intermediate
    Decimal("20"),     # Standard
])

# Swiss VAT rates
SWISS_VAT_RATES: FrozenSet[Decimal] = frozenset([
    Decimal("0"),
    Decimal("2.6"),    # Reduced (2025)
    Decimal("3.8"),    # Special (accommodation)
    Decimal("8.1"),    # Standard (2025)
])

# Maximum plausible values
MAX_SKONTO_PERCENT = Decimal("5")      # 5% is already generous
MAX_SKONTO_DAYS = 30                   # More than 30 days is unusual
MAX_PAYMENT_DAYS = 180                 # 6 months is extreme
MIN_AMOUNT_VALUE = Decimal("0.01")     # Minimum amount to consider
MAX_AMOUNT_VALUE = Decimal("100000000")  # 100M EUR sanity check

# Line item validation
MIN_DESCRIPTION_LENGTH = 3
MAX_DESCRIPTION_LENGTH = 500
MAX_QUANTITY = Decimal("1000000")
MAX_UNIT_PRICE = Decimal("10000000")

# Summary row indicators (case-insensitive)
SUMMARY_ROW_INDICATORS: FrozenSet[str] = frozenset([
    "summe",
    "gesamt",
    "total",
    "zwischensumme",
    "subtotal",
    "netto",
    "brutto",
    "mwst",
    "ust",
    "mehrwertsteuer",
    "endbetrag",
    "übertrag",
    "saldo",
    "rechnungsbetrag",
])
