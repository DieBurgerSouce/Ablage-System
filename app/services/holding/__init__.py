"""
Holding Services Module.

Services fuer Multi-Company/Holding-Funktionen:
- Konsolidierte KPIs ueber alle Firmen
- Intercompany-Abstimmung und -Eliminierung
- Konzernabschluss-Vorbereitung

Created: 2026-01-19
Updated: 2026-01-21 (Phase 5.3 IC Reconciliation)
"""

from app.services.holding.holding_kpi_service import HoldingKPIService
from app.services.holding.intercompany_reconciliation_service import (
    IntercompanyReconciliationService,
    get_intercompany_reconciliation_service,
    ICTransactionType,
    ReconciliationStatus,
    DifferenceType,
    ICTransaction,
    ICBalance,
    ReconciliationDifference,
    EliminationEntry,
    ReconciliationReport,
)

__all__ = [
    # KPI Service
    "HoldingKPIService",
    # IC Reconciliation Service
    "IntercompanyReconciliationService",
    "get_intercompany_reconciliation_service",
    # Enums
    "ICTransactionType",
    "ReconciliationStatus",
    "DifferenceType",
    # Data Classes
    "ICTransaction",
    "ICBalance",
    "ReconciliationDifference",
    "EliminationEntry",
    "ReconciliationReport",
]
