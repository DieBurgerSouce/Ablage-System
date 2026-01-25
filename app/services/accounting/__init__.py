# -*- coding: utf-8 -*-
"""
Accounting Services Module.

Integrierte Buchhaltung fuer das Ablage-System:
- Offene Posten (Debitoren/Kreditoren)
- USt-Voranmeldung
- Einnahmen-Ueberschuss-Rechnung (EUER)
- Automatische Buchungsvorschlaege (NEU: Januar 2026)
- (Geplant: GuV/Bilanz)

GoBD-konform und Enterprise-Ready.
"""

from app.services.accounting.open_items_service import (
    OpenItemsService,
    get_open_items_service,
    OpenItem,
    OpenItemsReport,
    OpenItemType,
    PaymentPriority,
    EntityBalance,
)

from app.services.accounting.vat_service import (
    VATService,
    get_vat_service,
    VATReport,
    VATSummary,
    VATLineItem,
    VATRate,
    VATReportPeriod,
    VAT_KENNZIFFERN,
)

from app.services.accounting.eur_service import (
    EURService,
    get_eur_service,
    EURReport,
    EURLineItem,
    EURCategorySummary,
    IncomeCategory,
    ExpenseCategory,
)

from app.services.accounting.auto_booking_service import (
    AutoBookingService,
    get_auto_booking_service,
    BookingSuggestion,
    AutoBookingResult,
    BookingConfidence,
    BookingType,
    BookingPattern,
    TaxCode,
)

__all__ = [
    # Open Items
    "OpenItemsService",
    "get_open_items_service",
    "OpenItem",
    "OpenItemsReport",
    "OpenItemType",
    "PaymentPriority",
    "EntityBalance",
    # VAT
    "VATService",
    "get_vat_service",
    "VATReport",
    "VATSummary",
    "VATLineItem",
    "VATRate",
    "VATReportPeriod",
    "VAT_KENNZIFFERN",
    # EUR
    "EURService",
    "get_eur_service",
    "EURReport",
    "EURLineItem",
    "EURCategorySummary",
    "IncomeCategory",
    "ExpenseCategory",
    # Auto-Booking
    "AutoBookingService",
    "get_auto_booking_service",
    "BookingSuggestion",
    "AutoBookingResult",
    "BookingConfidence",
    "BookingType",
    "BookingPattern",
    "TaxCode",
]
