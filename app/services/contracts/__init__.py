# -*- coding: utf-8 -*-
"""
Contract AI Services for Ablage-System.

Vision 2.0 Feature: Intelligente Vertragsanalyse
Unterstuetzt:
- Automatische Vertragsklausel-Extraktion (NLP)
- Vertragstyp-Klassifikation
- Pflichten-Tracking mit Erinnerungen
- Fristen-Management
- Risiko-Bewertung
- Versionsvergleich
- Vertragsverlaengerungs-Warnungen (Phase 1.1)

Contract Management V2 (Phase 5):
- Klauselerkennung mit strukturierter Extraktion
- Markt-Benchmark-Vergleiche
- Auto-Kuendigung mit deutschen Vorlagen
- Kostenanalyse und Optimierung

Feinpoliert und durchdacht.
"""

from app.services.contracts.contract_extraction_service import ContractExtractionService
from app.services.contracts.contract_classification_service import ContractClassificationService
from app.services.contracts.contract_obligation_tracker import ContractObligationTracker
from app.services.contracts.contract_deadline_service import ContractDeadlineService
from app.services.contracts.contract_risk_scorer import ContractRiskScorer
from app.services.contracts.contract_comparison_service import ContractComparisonService
from app.services.contracts.contract_renewal_service import (
    ContractRenewalService,
    ContractAlertCodes,
    get_contract_renewal_service,
)

# V2 Enhancements (Phase 5)
from app.services.contracts.clause_recognition_service import (
    ClauseRecognitionService,
    get_clause_recognition_service,
)
from app.services.contracts.contract_benchmark_service import (
    ContractBenchmarkService,
    get_contract_benchmark_service,
)
from app.services.contracts.auto_cancellation_service import (
    AutoCancellationService,
    get_auto_cancellation_service,
)
from app.services.contracts.contract_cost_analyzer import (
    ContractCostAnalyzer,
    get_contract_cost_analyzer,
)

__all__ = [
    # Original services
    "ContractExtractionService",
    "ContractClassificationService",
    "ContractObligationTracker",
    "ContractDeadlineService",
    "ContractRiskScorer",
    "ContractComparisonService",
    "ContractRenewalService",
    "ContractAlertCodes",
    "get_contract_renewal_service",
    # V2 Enhancements
    "ClauseRecognitionService",
    "get_clause_recognition_service",
    "ContractBenchmarkService",
    "get_contract_benchmark_service",
    "AutoCancellationService",
    "get_auto_cancellation_service",
    "ContractCostAnalyzer",
    "get_contract_cost_analyzer",
]
