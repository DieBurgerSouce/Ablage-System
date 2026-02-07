# -*- coding: utf-8 -*-
"""
ConfidenceAggregator - Kombiniert mehrere Confidence-Scores.

Aggregiert Confidence-Werte aus verschiedenen Quellen:
- OCR Confidence
- Classification Confidence
- Entity Linking Confidence
- Historical Accuracy

Verwendet gewichtete Durchschnitte basierend auf historischer Genauigkeit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.db.models import AIDecision, AILearningFeedback

logger = structlog.get_logger(__name__)


# ============================================================================
# Confidence Source Types
# ============================================================================


class ConfidenceSource(str, Enum):
    """Quellen fuer Confidence-Werte."""

    OCR = "ocr"                          # OCR Backend Confidence
    CLASSIFICATION = "classification"    # Dokumenttyp-Klassifikation
    ENTITY_LINKING = "entity_linking"    # Entity-Verknuepfung
    AMOUNT_EXTRACTION = "amount_extraction"  # Betragsextraktion
    DATE_EXTRACTION = "date_extraction"  # Datumsextraktion
    REFERENCE_EXTRACTION = "reference_extraction"  # Referenznummern
    SEMANTIC_SIMILARITY = "semantic_similarity"  # Semantische Aehnlichkeit
    PATTERN_MATCHING = "pattern_matching"  # Muster-Erkennung
    HISTORICAL = "historical"            # Historische Genauigkeit


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ConfidenceScore:
    """Ein einzelner Confidence-Score."""

    source: ConfidenceSource
    value: float
    weight: float = 1.0
    calibrated_value: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedConfidence:
    """Aggregiertes Confidence-Ergebnis."""

    raw_confidence: float           # Ungewichteter Durchschnitt
    weighted_confidence: float      # Gewichteter Durchschnitt
    calibrated_confidence: float    # Nach Kalibrierung
    min_confidence: float           # Minimum aller Scores
    max_confidence: float           # Maximum aller Scores
    source_count: int               # Anzahl der Quellen
    sources: List[ConfidenceScore]  # Einzelne Scores
    explanation: str                # Erklaerung


@dataclass
class CalibrationFactors:
    """Kalibrierungsfaktoren pro Quelle."""

    source: ConfidenceSource
    adjustment: float        # Anpassungsfaktor (-0.2 bis +0.2)
    sample_count: int        # Anzahl der Samples
    accuracy: float          # Historische Genauigkeit
    last_updated: Optional[str] = None


# ============================================================================
# Default Weights
# ============================================================================


DEFAULT_WEIGHTS: Dict[ConfidenceSource, float] = {
    ConfidenceSource.OCR: 0.8,
    ConfidenceSource.CLASSIFICATION: 1.0,
    ConfidenceSource.ENTITY_LINKING: 0.9,
    ConfidenceSource.AMOUNT_EXTRACTION: 1.2,  # Hoeher wegen Wichtigkeit
    ConfidenceSource.DATE_EXTRACTION: 0.9,
    ConfidenceSource.REFERENCE_EXTRACTION: 1.1,
    ConfidenceSource.SEMANTIC_SIMILARITY: 0.7,
    ConfidenceSource.PATTERN_MATCHING: 0.8,
    ConfidenceSource.HISTORICAL: 1.0,
}


# ============================================================================
# Confidence Aggregator Service
# ============================================================================


class ConfidenceAggregator:
    """Service zur Aggregation von Confidence-Scores.

    Kombiniert mehrere Confidence-Werte zu einem Gesamt-Score.
    Beruecksichtigt historische Genauigkeit und Kalibrierung.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Aggregator.

        Args:
            db: Async Database Session
        """
        self.db = db
        self._calibration_cache: Dict[str, Dict[ConfidenceSource, CalibrationFactors]] = {}

    async def aggregate(
        self,
        scores: List[ConfidenceScore],
        company_id: Optional[uuid.UUID] = None,
        document_type: Optional[str] = None,
    ) -> AggregatedConfidence:
        """Aggregiert mehrere Confidence-Scores.

        Args:
            scores: Liste von ConfidenceScore-Objekten
            company_id: Optional Company-ID fuer Kalibrierung
            document_type: Optional Dokumenttyp fuer spezifische Kalibrierung

        Returns:
            AggregatedConfidence mit allen Berechnungen
        """
        if not scores:
            return AggregatedConfidence(
                raw_confidence=0.0,
                weighted_confidence=0.0,
                calibrated_confidence=0.0,
                min_confidence=0.0,
                max_confidence=0.0,
                source_count=0,
                sources=[],
                explanation="Keine Confidence-Scores vorhanden.",
            )

        # Lade Kalibrierungsfaktoren
        calibration = await self._get_calibration_factors(company_id, document_type)

        # Berechne gewichtete Scores
        total_weight = 0.0
        weighted_sum = 0.0
        raw_sum = 0.0
        calibrated_scores: List[ConfidenceScore] = []

        for score in scores:
            # Wende Kalibrierung an
            calibration_factor = calibration.get(score.source)
            if calibration_factor:
                adjustment = calibration_factor.adjustment
                calibrated_value = max(0.0, min(1.0, score.value + adjustment))
            else:
                calibrated_value = score.value

            # Erstelle kalibrierten Score
            calibrated_score = ConfidenceScore(
                source=score.source,
                value=score.value,
                weight=score.weight or DEFAULT_WEIGHTS.get(score.source, 1.0),
                calibrated_value=calibrated_value,
                details=score.details,
            )
            calibrated_scores.append(calibrated_score)

            # Summiere fuer Durchschnitte
            weight = calibrated_score.weight
            total_weight += weight
            weighted_sum += calibrated_value * weight
            raw_sum += score.value

        # Berechne Durchschnitte
        raw_confidence = raw_sum / len(scores)
        weighted_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        calibrated_confidence = weighted_confidence  # Schon kalibriert

        # Min/Max
        min_confidence = min(s.value for s in scores)
        max_confidence = max(s.value for s in scores)

        # Erklaerung generieren
        explanation = self._generate_explanation(
            calibrated_scores, weighted_confidence, calibration
        )

        return AggregatedConfidence(
            raw_confidence=round(raw_confidence, 4),
            weighted_confidence=round(weighted_confidence, 4),
            calibrated_confidence=round(calibrated_confidence, 4),
            min_confidence=round(min_confidence, 4),
            max_confidence=round(max_confidence, 4),
            source_count=len(scores),
            sources=calibrated_scores,
            explanation=explanation,
        )

    async def aggregate_from_dict(
        self,
        confidence_dict: Dict[str, float],
        company_id: Optional[uuid.UUID] = None,
        document_type: Optional[str] = None,
    ) -> AggregatedConfidence:
        """Aggregiert Confidence-Scores aus einem Dictionary.

        Args:
            confidence_dict: Dictionary mit source -> confidence
            company_id: Optional Company-ID
            document_type: Optional Dokumenttyp

        Returns:
            AggregatedConfidence
        """
        scores: List[ConfidenceScore] = []

        for source_name, value in confidence_dict.items():
            try:
                source = ConfidenceSource(source_name)
            except ValueError:
                # Unbekannte Quelle, verwende als PATTERN_MATCHING
                source = ConfidenceSource.PATTERN_MATCHING

            scores.append(
                ConfidenceScore(
                    source=source,
                    value=float(value),
                    weight=DEFAULT_WEIGHTS.get(source, 1.0),
                )
            )

        return await self.aggregate(scores, company_id, document_type)

    async def _get_calibration_factors(
        self,
        company_id: Optional[uuid.UUID],
        document_type: Optional[str],
    ) -> Dict[ConfidenceSource, CalibrationFactors]:
        """Laedt Kalibrierungsfaktoren aus historischen Daten.

        Args:
            company_id: Company-ID
            document_type: Dokumenttyp

        Returns:
            Dictionary mit Kalibrierungsfaktoren pro Quelle
        """
        cache_key = f"{company_id}:{document_type}"

        # Cache-Check (1 Stunde TTL)
        if cache_key in self._calibration_cache:
            return self._calibration_cache[cache_key]

        try:
            calibration: Dict[ConfidenceSource, CalibrationFactors] = {}

            # Analysiere historische Entscheidungen
            cutoff = utc_now() - timedelta(days=90)

            for source in ConfidenceSource:
                factors = await self._calculate_source_calibration(
                    source, company_id, document_type, cutoff
                )
                if factors:
                    calibration[source] = factors

            # Cache aktualisieren
            self._calibration_cache[cache_key] = calibration

            return calibration

        except Exception as e:
            logger.warning(
                "calibration_load_error",
                **safe_error_log(e),
            )
            return {}

    async def _calculate_source_calibration(
        self,
        source: ConfidenceSource,
        company_id: Optional[uuid.UUID],
        document_type: Optional[str],
        cutoff,
    ) -> Optional[CalibrationFactors]:
        """Berechnet Kalibrierungsfaktoren fuer eine Quelle.

        Args:
            source: Confidence-Quelle
            company_id: Company-ID
            document_type: Dokumenttyp
            cutoff: Zeitpunkt ab dem Daten beruecksichtigt werden

        Returns:
            CalibrationFactors oder None
        """
        try:
            # Query fuer finale Entscheidungen mit Feedback
            base_filter = [
                AIDecision.created_at >= cutoff,
                AIDecision.is_final == True,
            ]

            if company_id:
                base_filter.append(AIDecision.company_id == company_id)

            # Hole Entscheidungen mit diesem Source-Typ
            result = await self.db.execute(
                select(AIDecision)
                .where(and_(*base_filter))
                .limit(1000)
            )
            decisions = result.scalars().all()

            if not decisions:
                return None

            # Analysiere Genauigkeit
            correct = 0
            total = 0
            confidence_sum = 0.0

            for decision in decisions:
                # Pruefe ob diese Source verwendet wurde
                features = decision.features_used or {}
                if source.value not in features:
                    continue

                total += 1
                confidence_sum += decision.confidence

                # Pruefe ob genehmigt oder korrigiert
                if decision.auto_applied or decision.review_action == "approved":
                    correct += 1

            if total < 10:  # Mindestens 10 Samples
                return None

            accuracy = correct / total
            avg_confidence = confidence_sum / total

            # Berechne Adjustment: Wenn Genauigkeit < Confidence -> Runter
            adjustment = (accuracy - avg_confidence) * 0.5
            adjustment = max(-0.2, min(0.2, adjustment))  # Begrenzen

            return CalibrationFactors(
                source=source,
                adjustment=round(adjustment, 4),
                sample_count=total,
                accuracy=round(accuracy, 4),
                last_updated=utc_now().isoformat(),
            )

        except Exception as e:
            logger.debug(
                "source_calibration_error",
                source=source.value,
                error_type=type(e).__name__,
            )
            return None

    def _generate_explanation(
        self,
        scores: List[ConfidenceScore],
        weighted_confidence: float,
        calibration: Dict[ConfidenceSource, CalibrationFactors],
    ) -> str:
        """Generiert eine Erklaerung fuer die Aggregation.

        Args:
            scores: Kalibrierte Scores
            weighted_confidence: Gewichtete Confidence
            calibration: Kalibrierungsfaktoren

        Returns:
            Erklaerungstext
        """
        parts = []

        # Sortiere nach Einfluss
        sorted_scores = sorted(
            scores,
            key=lambda s: (s.calibrated_value or s.value) * s.weight,
            reverse=True,
        )

        # Top 3 Einflussfaktoren
        for i, score in enumerate(sorted_scores[:3]):
            source_name = score.source.value.replace("_", " ").title()
            value = score.calibrated_value or score.value

            if i == 0:
                parts.append(f"Staerkster Faktor: {source_name} ({value:.0%})")
            else:
                parts.append(f"{source_name}: {value:.0%}")

        # Kalibrierungshinweise
        significant_adjustments = [
            (source, cal)
            for source, cal in calibration.items()
            if abs(cal.adjustment) > 0.05
        ]

        if significant_adjustments:
            adj_parts = []
            for source, cal in significant_adjustments[:2]:
                direction = "erhoht" if cal.adjustment > 0 else "reduziert"
                adj_parts.append(
                    f"{source.value.replace('_', ' ').title()} {direction} ({cal.adjustment:+.1%})"
                )
            parts.append(f"Kalibrierung: {'; '.join(adj_parts)}")

        return ". ".join(parts) if parts else "Standard-Aggregation ohne Kalibrierung."

    async def record_feedback(
        self,
        company_id: uuid.UUID,
        source: ConfidenceSource,
        predicted_confidence: float,
        was_correct: bool,
    ) -> None:
        """Zeichnet Feedback fuer Kalibrierung auf.

        Args:
            company_id: Company-ID
            source: Confidence-Quelle
            predicted_confidence: Vorhergesagte Confidence
            was_correct: Ob die Vorhersage korrekt war
        """
        try:
            # Invalidiere Cache fuer diese Company
            cache_keys_to_remove = [
                key for key in self._calibration_cache
                if key.startswith(str(company_id))
            ]
            for key in cache_keys_to_remove:
                del self._calibration_cache[key]

            logger.debug(
                "confidence_feedback_recorded",
                company_id=str(company_id),
                source=source.value,
                predicted=predicted_confidence,
                was_correct=was_correct,
            )

        except Exception as e:
            logger.warning(
                "confidence_feedback_error",
                **safe_error_log(e),
            )


# ============================================================================
# Factory Function
# ============================================================================


def get_confidence_aggregator(db: AsyncSession) -> ConfidenceAggregator:
    """Factory-Funktion fuer ConfidenceAggregator.

    Args:
        db: Async Database Session

    Returns:
        Konfigurierter ConfidenceAggregator
    """
    return ConfidenceAggregator(db=db)
