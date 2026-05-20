# -*- coding: utf-8 -*-
"""
Finance Services Package.

Enterprise-Grade Finanzmanagement für Ablage-System:
- Budget-Verwaltung mit Kostenstellen
- Soll/Ist-Vergleiche und Abweichungsanalysen
- Automatische Kategorisierung aus OCR-Daten
- Alert-System bei Budget-Überschreitung
- 3-Way PO-Matching (Bestellung-Lieferschein-Rechnung)

Phase 2.1-2.2 der Feature-Roadmap (Januar-Februar 2026).
"""

from .budget_service import (
    BudgetService,
    get_budget_service,
    BudgetFilter,
    BudgetSummary,
    BudgetVarianceReport,
    BudgetCreateRequest,
    BudgetLineCreateRequest,
    AllocationCreateRequest,
    KostenstelleCreateRequest,
)

from .po_matching_service import (
    POMatchingService,
    get_po_matching_service,
    MatchCreateRequest,
    MatchFilter,
    MatchStatistics,
    AddDocumentRequest,
)

from .recurring_invoice_service import (
    RecurringInvoiceService,
    get_recurring_invoice_service,
)

from .ust_voranmeldung_service import (
    UStVoranmeldungService,
    get_ust_voranmeldung_service,
)

from .bwa_service import (
    BWAService,
    get_bwa_service,
)

from .cashflow_forecast_service import (
    CashflowForecastService,
    get_cashflow_forecast_service,
)

__all__ = [
    "BudgetService",
    "get_budget_service",
    "BudgetFilter",
    "BudgetSummary",
    "BudgetVarianceReport",
    "BudgetCreateRequest",
    "BudgetLineCreateRequest",
    "AllocationCreateRequest",
    "KostenstelleCreateRequest",
    "POMatchingService",
    "get_po_matching_service",
    "MatchCreateRequest",
    "MatchFilter",
    "MatchStatistics",
    "AddDocumentRequest",
    "RecurringInvoiceService",
    "get_recurring_invoice_service",
    "UStVoranmeldungService",
    "get_ust_voranmeldung_service",
    "BWAService",
    "get_bwa_service",
    "CashflowForecastService",
    "get_cashflow_forecast_service",
]
