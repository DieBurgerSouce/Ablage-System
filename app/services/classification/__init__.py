# -*- coding: utf-8 -*-
"""
Multi-Dimensional Document Classification Services.

Vision 2.0 Feature: Intelligente Dokumentenklassifikation
Klassifiziert Dokumente nach mehreren Dimensionen:
- Dokumenttyp (Invoice, Contract, Order, etc.)
- Dringlichkeit (Immediate, Normal, CanWait)
- Abteilung/Zuständigkeit (Buchhaltung, Einkauf, Vertrieb, etc.)
- Vertraulichkeit (Public, Internal, Confidential, StrictlyConfidential)

Feinpoliert und durchdacht.
"""

from app.services.classification.urgency_classifier import (
    UrgencyClassifier,
    UrgencyLevel,
    UrgencyClassificationResult,
)
from app.services.classification.department_router import (
    DepartmentRouter,
    Department,
    DepartmentRoutingResult,
)
from app.services.classification.confidentiality_classifier import (
    ConfidentialityClassifier,
    ConfidentialityLevel,
    ConfidentialityClassificationResult,
)
from app.services.classification.multi_label_classifier import (
    MultiLabelClassifier,
    MultiLabelClassificationResult,
    get_multi_label_classifier,
)

__all__ = [
    # Urgency
    "UrgencyClassifier",
    "UrgencyLevel",
    "UrgencyClassificationResult",
    # Department
    "DepartmentRouter",
    "Department",
    "DepartmentRoutingResult",
    # Confidentiality
    "ConfidentialityClassifier",
    "ConfidentialityLevel",
    "ConfidentialityClassificationResult",
    # Multi-Label
    "MultiLabelClassifier",
    "MultiLabelClassificationResult",
    "get_multi_label_classifier",
]
