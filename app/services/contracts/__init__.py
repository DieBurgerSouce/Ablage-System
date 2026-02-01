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

__all__ = [
    "ContractExtractionService",
    "ContractClassificationService",
    "ContractObligationTracker",
    "ContractDeadlineService",
    "ContractRiskScorer",
    "ContractComparisonService",
    "ContractRenewalService",
    "ContractAlertCodes",
    "get_contract_renewal_service",
]
