# -*- coding: utf-8 -*-
"""
AI Explainability Protocol - Einheitliches Erklaerungsformat.

Definiert das standardisierte Format fuer KI-Erklaerungen
ueber alle AI-Services hinweg (Tagging, Risk Scoring, OCR,
Buchungsvorschlaege, Mahnwesen, etc.).

Feinpoliert und durchdacht - Enterprise-grade XAI Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Union
from uuid import UUID


class DecisionType(str, Enum):
    """Typ der KI-Entscheidung."""
    CLASSIFICATION = "classification"
    RISK_ASSESSMENT = "risk_assessment"
    OCR_EXTRACTION = "ocr_extraction"
    BOOKING_SUGGESTION = "booking_suggestion"
    DUNNING_RECOMMENDATION = "dunning_recommendation"
    ANOMALY_DETECTION = "anomaly_detection"
    ENTITY_LINKING = "entity_linking"
    DUPLICATE_DETECTION = "duplicate_detection"
    FRAUD_DETECTION = "fraud_detection"
    CASHFLOW_PREDICTION = "cashflow_prediction"


# Type alias for alternative decision values
AlternativeValue = Union[str, int, float, bool, None]


@dataclass
class ExplanationFactor:
    """Ein Faktor, der zur KI-Entscheidung beigetragen hat."""

    name: str
    value: str
    importance: float  # 0.0 - 1.0
    description: str  # German

    def to_dict(self) -> Dict[str, Union[str, float]]:
        """Serialisiert den Faktor als Dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "importance": self.importance,
            "description": self.description,
        }


@dataclass
class ExplanationResult:
    """Ergebnis einer KI-Erklaerung fuer eine einzelne Entscheidung."""

    decision_type: DecisionType
    service_name: str
    decision_summary: str  # German, z.B. "Dokument als Rechnung klassifiziert"
    confidence: float
    factors: List[ExplanationFactor]
    model_used: Optional[str] = None
    alternative_decisions: List[Dict[str, AlternativeValue]] = field(
        default_factory=list
    )
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Union[str, float, None, List[Dict[str, Union[str, float]]], List[Dict[str, AlternativeValue]]]]:
        """Serialisiert das Ergebnis als Dictionary."""
        return {
            "decision_type": self.decision_type.value,
            "service_name": self.service_name,
            "decision_summary": self.decision_summary,
            "confidence": self.confidence,
            "factors": [f.to_dict() for f in self.factors],
            "model_used": self.model_used,
            "alternative_decisions": self.alternative_decisions,
            "created_at": self.created_at or datetime.now(timezone.utc).isoformat(),
        }
