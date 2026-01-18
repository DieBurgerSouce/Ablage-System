# -*- coding: utf-8 -*-
"""
Finance Services Package.

Enterprise-Grade Finanzmanagement fuer Ablage-System:
- Budget-Verwaltung mit Kostenstellen
- Soll/Ist-Vergleiche und Abweichungsanalysen
- Automatische Kategorisierung aus OCR-Daten
- Alert-System bei Budget-Ueberschreitung

Phase 2.1 der Feature-Roadmap (Januar 2026).
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
]
