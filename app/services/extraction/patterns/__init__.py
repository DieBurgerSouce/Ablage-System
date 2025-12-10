"""
Extraction patterns for German documents.

This module provides regex patterns and pattern classes for extracting:
- Payment terms (Zahlungsziele, Skonto)
- Amounts (Beträge)
- Dates (Daten)
- References (Rechnungs-/Bestellnummern)
"""

from app.services.extraction.patterns.payment_patterns import (
    PaymentPatterns,
    get_payment_patterns,
)
from app.services.extraction.patterns.amount_patterns import (
    AmountPatterns,
    get_amount_patterns,
)
from app.services.extraction.patterns.date_patterns import (
    DatePatterns,
    get_date_patterns,
)
from app.services.extraction.patterns.reference_patterns import (
    ReferencePatterns,
    get_reference_patterns,
)

__all__ = [
    "PaymentPatterns",
    "get_payment_patterns",
    "AmountPatterns",
    "get_amount_patterns",
    "DatePatterns",
    "get_date_patterns",
    "ReferencePatterns",
    "get_reference_patterns",
]
