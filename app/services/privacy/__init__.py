# -*- coding: utf-8 -*-
"""
Privacy Services for Ablage-System.

Vision 2.0 Feature: Datenschutz-by-Design
Unterstützt:
- Automatische PII-Erkennung (IBAN, Namen, Steuer-IDs)
- Maskierung sensitiver Daten
- Pseudonymisierung
- Consent-Management
- Privacy-Audit
- Differential Privacy (Phase 5)
- Privacy Budget Tracking (Phase 5)

Feinpoliert und durchdacht.
"""

from app.services.privacy.pii_detection_service import PIIDetectionService
from app.services.privacy.pii_masking_service import PIIMaskingService
from app.services.privacy.differential_privacy_service import (
    DifferentialPrivacyService,
    DPResult,
    DPConfig,
    DPMechanism,
    QueryType,
    SensitivityLevel,
    get_dp_service,
)
from app.services.privacy.privacy_budget_tracker import (
    PrivacyBudgetTracker,
    BudgetStatus,
    BudgetConfig,
    BudgetExhaustedError,
    get_budget_tracker,
)

__all__ = [
    # PII Services
    "PIIDetectionService",
    "PIIMaskingService",
    # Differential Privacy (Phase 5)
    "DifferentialPrivacyService",
    "DPResult",
    "DPConfig",
    "DPMechanism",
    "QueryType",
    "SensitivityLevel",
    "get_dp_service",
    # Privacy Budget (Phase 5)
    "PrivacyBudgetTracker",
    "BudgetStatus",
    "BudgetConfig",
    "BudgetExhaustedError",
    "get_budget_tracker",
]
