# -*- coding: utf-8 -*-
"""
Accounting Services Module.

Integrierte Buchhaltung fuer das Ablage-System:
- Offene Posten (Debitoren/Kreditoren)
- USt-Voranmeldung
- Einnahmen-Ueberschuss-Rechnung (EUER)
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
]
