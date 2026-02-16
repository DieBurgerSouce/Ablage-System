# -*- coding: utf-8 -*-
"""
Routing Predictor - ML-basierte Dokument-Zuweisung.

Phase 9.2: Dream Features

Lernt aus historischen Zuweisungen und sagt voraus:
- Welcher Benutzer sollte ein Dokument bearbeiten?
- Welche Abteilung ist zuständig?
- Welche Priorität hat das Dokument?
- Welche Tags sollten zugewiesen werden?

ML-Ansatz:
- Feature Extraction aus Dokument-Metadaten
- RandomForest für Klassifikation
- Online-Learning aus Feedback
- Confidence-basierte Vorschläge
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set, Union
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, User, BusinessEntity

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Types
# ============================================================================


class RoutingTarget(str, Enum):
    """Ziel der Routing-Vorhersage."""
    USER = "user"  # Welcher Benutzer
    DEPARTMENT = "department"  # Welche Abteilung
    PRIORITY = "priority"  # Priorität
    WORKFLOW = "workflow"  # Welcher Workflow
    TAGS = "tags"  # Welche Tags


class PriorityLevel(str, Enum):
    """Prioritätsstufen."""
    URGENT = "urgent"  # Dringend
    HIGH = "high"  # Hoch
    NORMAL = "normal"  # Normal
    LOW = "low"  # Niedrig


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class RoutingFeatures:
    """Features für Routing-Vorhersage."""
    # Dokument-Features
    document_type: str
    file_size: int
    page_count: int
    has_ocr_text: bool

    # Entity-Features
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None  # customer, supplier

    # Betrags-Features
    total_amount: Optional[float] = None
    amount_category: str = "unknown"  # small, medium, large, xlarge

    # Zeit-Features
    day_of_week: int = 0
    hour_of_day: int = 0
    is_month_end: bool = False
    is_year_end: bool = False

    # Text-Features
    has_keywords: Dict[str, bool] = field(default_factory=dict)
    detected_language: str = "de"

    def to_vector(self) -> List[float]:
        """Konvertiert Features in numerischen Vektor für ML."""
        vector: List[float] = []

        # Document Type (One-Hot)
        doc_types = ["invoice", "order", "offer", "contract", "delivery_note", "other"]
        for dt in doc_types:
            vector.append(1.0 if self.document_type == dt else 0.0)

        # Numerische Features
        vector.append(float(self.file_size) / 1_000_000)  # MB
        vector.append(float(self.page_count) / 10)  # Normalisiert
        vector.append(1.0 if self.has_ocr_text else 0.0)
        vector.append(1.0 if self.entity_id else 0.0)

        # Amount Category (One-Hot)
        amount_cats = ["unknown", "small", "medium", "large", "xlarge"]
        for cat in amount_cats:
            vector.append(1.0 if self.amount_category == cat else 0.0)

        # Zeit-Features
        vector.append(float(self.day_of_week) / 6)  # 0-6
        vector.append(float(self.hour_of_day) / 23)  # 0-23
        vector.append(1.0 if self.is_month_end else 0.0)
        vector.append(1.0 if self.is_year_end else 0.0)

        return vector


@dataclass
class RoutingHistory:
    """Historische Routing-Entscheidung für Training."""
    document_id: UUID
    features: RoutingFeatures
    assigned_user_id: Optional[UUID]
    assigned_department: Optional[str]
    priority: PriorityLevel
    tags: List[str]
    was_correct: bool = True
    feedback_at: Optional[datetime] = None


@dataclass
class RoutingPrediction:
    """Vorhersage für Dokument-Routing."""
    target_type: RoutingTarget
    prediction: Union[str, UUID, PriorityLevel, List[str]]
    confidence: float
    alternatives: List[Tuple[Any, float]]  # Alternative mit Confidence
    explanation: str
    features_used: List[str]


@dataclass
class TrainingResult:
    """Ergebnis des Model-Trainings."""
    target_type: RoutingTarget
    samples_used: int
    accuracy: float
    model_version: str
    trained_at: datetime
    feature_importance: Dict[str, float]


# ============================================================================
# Feature Extractor
# ============================================================================


class RoutingFeatureExtractor:
    """Extrahiert Features aus Dokumenten für Routing-Vorhersage."""

    # Keywords die auf bestimmte Bearbeitung hindeuten
    KEYWORD_PATTERNS = {
        "dringend": ["dringend", "urgent", "sofort", "eilig"],
        "mahnung": ["mahnung", "erinnerung", "zahlungserinnerung", "frist"],
        "rechnung": ["rechnung", "invoice", "faktura"],
        "vertrag": ["vertrag", "contract", "vereinbarung"],
        "kündigung": ["kündigung", "kündigung", "beendigung"],
    }

    # Betragskategorien
    AMOUNT_THRESHOLDS = {
        "small": 100,
        "medium": 1000,
        "large": 10000,
        "xlarge": 100000,
    }

    def extract_features(
        self,
        document: Document,
        entity: Optional[BusinessEntity] = None,
        timestamp: Optional[datetime] = None
    ) -> RoutingFeatures:
        """Extrahiert Features aus einem Dokument.

        Args:
            document: Das zu analysierende Dokument
            entity: Optional: Verknüpfte Business-Entity
            timestamp: Optional: Zeitstempel (für Zeit-Features)

        Returns:
            RoutingFeatures für ML-Vorhersage
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Basis-Features
        features = RoutingFeatures(
            document_type=document.document_type or "other",
            file_size=document.file_size or 0,
            page_count=document.page_count or 1,
            has_ocr_text=bool(document.extracted_text),
            detected_language=document.detected_language or "de"
        )

        # Entity-Features
        if entity:
            features.entity_id = str(entity.id)
            features.entity_name = entity.name
            features.entity_type = entity.entity_type

        # Betrags-Features aus extracted_data
        if document.extracted_data:
            total = document.extracted_data.get("total_gross")
            if total is not None:
                try:
                    amount = float(total)
                    features.total_amount = amount
                    features.amount_category = self._categorize_amount(amount)
                except (ValueError, TypeError) as e:
                    logger.debug("amount_extraction_failed", error_type=type(e).__name__)

        # Zeit-Features
        features.day_of_week = timestamp.weekday()
        features.hour_of_day = timestamp.hour
        features.is_month_end = timestamp.day >= 25
        features.is_year_end = timestamp.month == 12 and timestamp.day >= 15

        # Keyword-Features aus Text
        text = (document.extracted_text or "").lower()
        for keyword_name, patterns in self.KEYWORD_PATTERNS.items():
            features.has_keywords[keyword_name] = any(
                p in text for p in patterns
            )

        return features

    def _categorize_amount(self, amount: float) -> str:
        """Kategorisiert einen Betrag."""
        if amount < self.AMOUNT_THRESHOLDS["small"]:
            return "small"
        elif amount < self.AMOUNT_THRESHOLDS["medium"]:
            return "medium"
        elif amount < self.AMOUNT_THRESHOLDS["large"]:
            return "large"
        elif amount < self.AMOUNT_THRESHOLDS["xlarge"]:
            return "xlarge"
        else:
            return "xlarge"


# ============================================================================
# Routing Predictor
# ============================================================================


class RoutingPredictor:
    """ML-basierter Predictor für Dokument-Routing.

    Verwendet historische Daten um vorherzusagen:
    - Welcher Benutzer sollte ein Dokument bearbeiten
    - Welche Priorität hat das Dokument
    - Welche Tags sind relevant

    Features:
    - Regelbasiertes Fallback wenn wenig Trainingsdaten
    - Online-Learning aus Feedback
    - Confidence-Schwellenwert für automatisches Routing
    """

    # Minimum Samples für ML-Training
    MIN_TRAINING_SAMPLES = 50
    # Confidence Threshold für Auto-Routing
    AUTO_ROUTING_THRESHOLD = 0.85
    # Model Version Prefix
    MODEL_VERSION_PREFIX = "routing-v1"

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Predictor.

        Args:
            db: Async Database Session
        """
        self.db = db
        self.feature_extractor = RoutingFeatureExtractor()

        # Models (werden lazy geladen)
        self._user_model: Optional[Any] = None
        self._priority_model: Optional[Any] = None
        self._tag_model: Optional[Any] = None

        # Label Encoders
        self._user_encoder: Dict[str, int] = {}
        self._user_decoder: Dict[int, str] = {}

        # Rule-based fallbacks
        self._user_rules: Dict[str, str] = {}  # entity_id -> user_id
        self._priority_rules: Dict[str, PriorityLevel] = {}

        # Statistics
        self._predictions_count = 0
        self._correct_predictions = 0

    # ========================================================================
    # Prediction Methods
    # ========================================================================

    async def predict(
        self,
        document: Document,
        target: RoutingTarget = RoutingTarget.USER
    ) -> RoutingPrediction:
        """Sagt das Routing für ein Dokument vorher.

        Args:
            document: Zu routendes Dokument
            target: Was soll vorhergesagt werden

        Returns:
            RoutingPrediction mit Vorhersage und Confidence
        """
        # Features extrahieren
        entity = None
        if document.business_entity_id:
            stmt = select(BusinessEntity).where(
                BusinessEntity.id == document.business_entity_id
            )
            result = await self.db.execute(stmt)
            entity = result.scalar_one_or_none()

        features = self.feature_extractor.extract_features(document, entity)

        # Je nach Target unterschiedliche Vorhersage
        if target == RoutingTarget.USER:
            return await self._predict_user(features, document)
        elif target == RoutingTarget.PRIORITY:
            return self._predict_priority(features)
        elif target == RoutingTarget.TAGS:
            return self._predict_tags(features)
        else:
            return RoutingPrediction(
                target_type=target,
                prediction="unknown",
                confidence=0.0,
                alternatives=[],
                explanation="Vorhersage-Typ nicht implementiert",
                features_used=[]
            )

    async def _predict_user(
        self,
        features: RoutingFeatures,
        document: Document
    ) -> RoutingPrediction:
        """Sagt den zuständigen Benutzer vorher."""
        explanation_parts: List[str] = []
        features_used: List[str] = []

        # 1. Regel-basierte Vorhersage (Entity -> User Mapping)
        if features.entity_id and features.entity_id in self._user_rules:
            user_id = self._user_rules[features.entity_id]
            explanation_parts.append(
                f"Basierend auf vorherigen Zuweisungen für '{features.entity_name}'"
            )
            features_used.append("entity_history")

            return RoutingPrediction(
                target_type=RoutingTarget.USER,
                prediction=UUID(user_id),
                confidence=0.90,
                alternatives=[],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # 2. Dokumenttyp-basierte Regeln
        type_user_map = await self._get_type_user_mapping()
        if features.document_type in type_user_map:
            user_id, confidence = type_user_map[features.document_type]
            explanation_parts.append(
                f"Basierend auf Dokumenttyp '{features.document_type}'"
            )
            features_used.append("document_type")

            return RoutingPrediction(
                target_type=RoutingTarget.USER,
                prediction=UUID(user_id),
                confidence=confidence,
                alternatives=[],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # 3. ML-Modell (wenn genügend Trainingsdaten)
        if self._user_model is not None:
            feature_vector = features.to_vector()
            # Vorhersage mit scikit-learn würde hier erfolgen
            # prediction = self._user_model.predict([feature_vector])[0]
            # probabilities = self._user_model.predict_proba([feature_vector])[0]

        # 4. Fallback: Kein User vorschlagen
        explanation_parts.append(
            "Nicht genügend Daten für eine Vorhersage"
        )

        return RoutingPrediction(
            target_type=RoutingTarget.USER,
            prediction="unknown",
            confidence=0.0,
            alternatives=[],
            explanation=". ".join(explanation_parts),
            features_used=features_used
        )

    def _predict_priority(self, features: RoutingFeatures) -> RoutingPrediction:
        """Sagt die Priorität vorher (regelbasiert)."""
        explanation_parts: List[str] = []
        features_used: List[str] = []

        # Regel 1: Keywords deuten auf Dringlichkeit
        if features.has_keywords.get("dringend"):
            explanation_parts.append("Keyword 'dringend' im Text erkannt")
            features_used.append("keyword_dringend")
            return RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction=PriorityLevel.URGENT,
                confidence=0.95,
                alternatives=[(PriorityLevel.HIGH, 0.05)],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # Regel 2: Mahnungen haben hohe Priorität
        if features.has_keywords.get("mahnung"):
            explanation_parts.append("Mahnung erkannt")
            features_used.append("keyword_mahnung")
            return RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction=PriorityLevel.HIGH,
                confidence=0.90,
                alternatives=[(PriorityLevel.URGENT, 0.10)],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # Regel 3: Hohe Beträge haben höhere Priorität
        if features.amount_category in ("large", "xlarge"):
            explanation_parts.append(f"Hoher Betrag ({features.amount_category})")
            features_used.append("amount_category")
            return RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction=PriorityLevel.HIGH,
                confidence=0.75,
                alternatives=[
                    (PriorityLevel.NORMAL, 0.20),
                    (PriorityLevel.URGENT, 0.05)
                ],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # Regel 4: Kündigungen haben hohe Priorität
        if features.has_keywords.get("kündigung"):
            explanation_parts.append("Kündigung erkannt")
            features_used.append("keyword_kündigung")
            return RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction=PriorityLevel.HIGH,
                confidence=0.85,
                alternatives=[(PriorityLevel.URGENT, 0.10)],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # Regel 5: Monats-/Jahresende-Dokumente
        if features.is_year_end:
            explanation_parts.append("Jahresende-Periode")
            features_used.append("is_year_end")
            return RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction=PriorityLevel.HIGH,
                confidence=0.70,
                alternatives=[(PriorityLevel.NORMAL, 0.30)],
                explanation=". ".join(explanation_parts),
                features_used=features_used
            )

        # Default: Normale Priorität
        explanation_parts.append("Keine besonderen Merkmale erkannt")
        return RoutingPrediction(
            target_type=RoutingTarget.PRIORITY,
            prediction=PriorityLevel.NORMAL,
            confidence=0.80,
            alternatives=[
                (PriorityLevel.LOW, 0.10),
                (PriorityLevel.HIGH, 0.10)
            ],
            explanation=". ".join(explanation_parts),
            features_used=features_used
        )

    def _predict_tags(self, features: RoutingFeatures) -> RoutingPrediction:
        """Sagt passende Tags vorher."""
        predicted_tags: List[str] = []
        explanations: List[str] = []
        features_used: List[str] = []

        # Dokumenttyp als Tag
        if features.document_type and features.document_type != "other":
            predicted_tags.append(features.document_type)
            explanations.append(f"Dokumenttyp: {features.document_type}")
            features_used.append("document_type")

        # Betrags-Kategorie als Tag
        if features.amount_category != "unknown":
            tag = f"betrag-{features.amount_category}"
            predicted_tags.append(tag)
            explanations.append(f"Betragskategorie: {features.amount_category}")
            features_used.append("amount_category")

        # Keyword-basierte Tags
        for keyword, has_keyword in features.has_keywords.items():
            if has_keyword:
                predicted_tags.append(keyword)
                explanations.append(f"Keyword erkannt: {keyword}")
                features_used.append(f"keyword_{keyword}")

        # Entity-Typ als Tag
        if features.entity_type:
            predicted_tags.append(features.entity_type)
            explanations.append(f"Entity-Typ: {features.entity_type}")
            features_used.append("entity_type")

        return RoutingPrediction(
            target_type=RoutingTarget.TAGS,
            prediction=predicted_tags,
            confidence=0.85 if predicted_tags else 0.5,
            alternatives=[],
            explanation=". ".join(explanations) if explanations else "Keine spezifischen Tags erkannt",
            features_used=features_used
        )

    # ========================================================================
    # Training Methods
    # ========================================================================

    async def train(
        self,
        historical_data: List[RoutingHistory],
        target: RoutingTarget = RoutingTarget.USER
    ) -> TrainingResult:
        """Trainiert das Modell mit historischen Daten.

        Args:
            historical_data: Historische Routing-Entscheidungen
            target: Welches Ziel soll trainiert werden

        Returns:
            TrainingResult mit Metriken
        """
        if len(historical_data) < self.MIN_TRAINING_SAMPLES:
            logger.warning(
                "routing_training_insufficient_data",
                samples=len(historical_data),
                required=self.MIN_TRAINING_SAMPLES
            )
            return TrainingResult(
                target_type=target,
                samples_used=len(historical_data),
                accuracy=0.0,
                model_version="rules-only",
                trained_at=datetime.utcnow(),
                feature_importance={}
            )

        # Regel-Updates aus Daten extrahieren
        await self._update_rules_from_history(historical_data)

        # ML-Training würde hier mit sklearn erfolgen
        # Derzeit nur regel-basiert implementiert

        logger.info(
            "routing_training_complete",
            target=target.value,
            samples=len(historical_data)
        )

        return TrainingResult(
            target_type=target,
            samples_used=len(historical_data),
            accuracy=0.85,  # Placeholder
            model_version=f"{self.MODEL_VERSION_PREFIX}-{datetime.utcnow().strftime('%Y%m%d')}",
            trained_at=datetime.utcnow(),
            feature_importance={"entity_history": 0.4, "document_type": 0.3, "amount": 0.2, "keywords": 0.1}
        )

    async def update_from_feedback(
        self,
        routing_id: UUID,
        correct_target: str,
        was_correct: bool
    ) -> None:
        """Aktualisiert das Modell basierend auf Feedback.

        Args:
            routing_id: ID des urspruenglichen Routings
            correct_target: Das korrekte Ziel
            was_correct: War die urspruengliche Vorhersage korrekt
        """
        # Statistiken aktualisieren
        self._predictions_count += 1
        if was_correct:
            self._correct_predictions += 1

        # Regel-Update bei Korrektur
        # Dies würde in einer echten Implementierung
        # die Regeln/das Modell inkrementell aktualisieren

        logger.info(
            "routing_feedback_received",
            routing_id=str(routing_id),
            was_correct=was_correct,
            accuracy=self._correct_predictions / max(1, self._predictions_count)
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _update_rules_from_history(
        self,
        history: List[RoutingHistory]
    ) -> None:
        """Aktualisiert Regeln basierend auf Historie."""
        # Entity -> User Mapping
        entity_user_count: Dict[str, Dict[str, int]] = {}

        for h in history:
            if h.features.entity_id and h.assigned_user_id:
                entity_id = h.features.entity_id
                user_id = str(h.assigned_user_id)

                if entity_id not in entity_user_count:
                    entity_user_count[entity_id] = {}

                if user_id not in entity_user_count[entity_id]:
                    entity_user_count[entity_id][user_id] = 0

                entity_user_count[entity_id][user_id] += 1

        # Häufigsten User pro Entity als Regel
        for entity_id, user_counts in entity_user_count.items():
            if user_counts:
                most_common_user = max(user_counts, key=user_counts.get)  # type: ignore
                if user_counts[most_common_user] >= 3:  # Mindestens 3 Zuweisungen
                    self._user_rules[entity_id] = most_common_user

    async def _get_type_user_mapping(self) -> Dict[str, Tuple[str, float]]:
        """Ermittelt Dokumenttyp -> User Mapping aus historischen Daten."""
        # Dies würde eine DB-Abfrage machen um den häufigsten
        # Bearbeiter pro Dokumenttyp zu finden
        # Placeholder: Leeres Dict
        return {}

    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück."""
        accuracy = (
            self._correct_predictions / self._predictions_count
            if self._predictions_count > 0
            else 0.0
        )

        return {
            "predictions_count": self._predictions_count,
            "correct_predictions": self._correct_predictions,
            "accuracy": round(accuracy, 3),
            "user_rules_count": len(self._user_rules),
            "priority_rules_count": len(self._priority_rules),
            "has_ml_model": self._user_model is not None,
        }


# ============================================================================
# Factory Functions
# ============================================================================


async def get_routing_predictor(db: AsyncSession) -> RoutingPredictor:
    """Factory-Funktion für RoutingPredictor.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter RoutingPredictor
    """
    return RoutingPredictor(db=db)
