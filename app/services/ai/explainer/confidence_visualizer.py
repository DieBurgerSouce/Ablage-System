# -*- coding: utf-8 -*-
"""
Confidence Visualizer Service - Confidence-Score Breakdown.

Enterprise Feature: Visualisierung wie sich Confidence zusammensetzt.

Features:
- Komponenten-Aufschluesselung
- Historische Confidence-Entwicklung
- Kalibrierungsanzeige
- Vergleich mit Durchschnitt

Vision: "85% Confidence setzt sich zusammen aus..."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIDecision

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

CONFIDENCE_BREAKDOWNS_GENERATED = Counter(
    "confidence_breakdowns_generated_total",
    "Total confidence breakdowns generated",
    ["decision_type"]
)


# =============================================================================
# Enums
# =============================================================================

class ConfidenceLevel(str, Enum):
    """Confidence-Level Kategorien."""
    VERY_HIGH = "very_high"   # 95%+
    HIGH = "high"             # 85-95%
    MEDIUM = "medium"         # 70-85%
    LOW = "low"               # 50-70%
    VERY_LOW = "very_low"     # <50%


class ComponentType(str, Enum):
    """Typ der Confidence-Komponente."""
    MODEL_OUTPUT = "model_output"         # Direkte Modell-Ausgabe
    CALIBRATION = "calibration"           # Kalibrierungsanpassung
    HISTORICAL = "historical"             # Historische Genauigkeit
    ENSEMBLE = "ensemble"                 # Ensemble-Beitrag
    FEATURE_QUALITY = "feature_quality"   # Feature-Qualität
    DATA_COVERAGE = "data_coverage"       # Datenabdeckung


class TrendDirection(str, Enum):
    """Trend-Richtung."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


# =============================================================================
# TypedDicts
# =============================================================================

class ConfidenceComponentDict(TypedDict):
    """Eine Confidence-Komponente."""
    component_type: str
    name: str
    contribution: float
    raw_value: float
    weight: float
    description: str


class HistoricalDataPointDict(TypedDict):
    """Historischer Datenpunkt."""
    date: str
    confidence: float
    accuracy: float
    sample_size: int


class ConfidenceBreakdownDict(TypedDict):
    """Vollständige Confidence-Aufschluesselung."""
    id: str
    decision_id: Optional[str]
    decision_type: str
    final_confidence: float
    confidence_level: str
    components: List[ConfidenceComponentDict]
    calibration_adjustment: float
    historical_accuracy: float
    sample_size: int
    trend: str
    historical_data: List[HistoricalDataPointDict]
    comparison_to_average: float
    generated_at: str


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConfidenceComponent:
    """Eine Komponente der Confidence."""
    component_type: ComponentType
    name: str
    contribution: float  # Beitrag zur Gesamt-Confidence (0-1)
    raw_value: float     # Rohwert vor Gewichtung
    weight: float        # Gewichtung (0-1)
    description: str

    def to_dict(self) -> ConfidenceComponentDict:
        """Konvertiert zu Dictionary."""
        return ConfidenceComponentDict(
            component_type=self.component_type.value,
            name=self.name,
            contribution=self.contribution,
            raw_value=self.raw_value,
            weight=self.weight,
            description=self.description,
        )


@dataclass
class HistoricalDataPoint:
    """Historischer Datenpunkt."""
    date: datetime
    confidence: float
    accuracy: float
    sample_size: int

    def to_dict(self) -> HistoricalDataPointDict:
        """Konvertiert zu Dictionary."""
        return HistoricalDataPointDict(
            date=self.date.isoformat(),
            confidence=self.confidence,
            accuracy=self.accuracy,
            sample_size=self.sample_size,
        )


@dataclass
class ConfidenceBreakdown:
    """Vollständige Aufschluesselung einer Confidence."""
    id: UUID = field(default_factory=uuid4)
    decision_id: Optional[UUID] = None
    decision_type: str = ""
    final_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM

    # Komponenten
    components: List[ConfidenceComponent] = field(default_factory=list)

    # Kalibrierung
    calibration_adjustment: float = 0.0  # Anpassung durch Kalibrierung

    # Historische Daten
    historical_accuracy: float = 0.0     # Historische Genauigkeit bei dieser Confidence
    sample_size: int = 0                  # Anzahl historischer Faelle
    trend: TrendDirection = TrendDirection.STABLE
    historical_data: List[HistoricalDataPoint] = field(default_factory=list)

    # Vergleich
    comparison_to_average: float = 0.0   # Abweichung vom Durchschnitt

    # Metadata
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> ConfidenceBreakdownDict:
        """Konvertiert zu Dictionary."""
        return ConfidenceBreakdownDict(
            id=str(self.id),
            decision_id=str(self.decision_id) if self.decision_id else None,
            decision_type=self.decision_type,
            final_confidence=self.final_confidence,
            confidence_level=self.confidence_level.value,
            components=[c.to_dict() for c in self.components],
            calibration_adjustment=self.calibration_adjustment,
            historical_accuracy=self.historical_accuracy,
            sample_size=self.sample_size,
            trend=self.trend.value,
            historical_data=[h.to_dict() for h in self.historical_data],
            comparison_to_average=self.comparison_to_average,
            generated_at=self.generated_at.isoformat(),
        )


# =============================================================================
# Confidence Visualizer Service
# =============================================================================

class ConfidenceVisualizer:
    """
    Service zur Visualisierung von Confidence-Scores.

    Zeigt transparent wie sich ein Confidence-Score zusammensetzt
    und wie zuverlaessig er historisch war.
    """

    # Standard-Gewichte für Komponenten
    DEFAULT_WEIGHTS = {
        ComponentType.MODEL_OUTPUT: 0.50,
        ComponentType.FEATURE_QUALITY: 0.20,
        ComponentType.DATA_COVERAGE: 0.15,
        ComponentType.HISTORICAL: 0.15,
    }

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def breakdown(
        self,
        db: AsyncSession,
        decision_id: UUID,
        include_history: bool = True,
        history_days: int = 30,
    ) -> ConfidenceBreakdown:
        """
        Erstellt Confidence-Aufschluesselung.

        Args:
            db: Database Session
            decision_id: ID der Entscheidung
            include_history: Historische Daten einbeziehen
            history_days: Zeitraum für Historie

        Returns:
            ConfidenceBreakdown mit allen Details
        """
        logger.info(
            "generating_confidence_breakdown",
            decision_id=str(decision_id),
        )

        # Entscheidung laden
        decision = await self._load_decision(db, decision_id)
        if not decision:
            return self._create_empty_breakdown(decision_id)

        # Komponenten analysieren
        components = self._analyze_components(decision)

        # Kalibrierungsanpassung
        calibration_adj = self._calculate_calibration_adjustment(decision)

        # Historische Genauigkeit
        historical_acc, sample_size = await self._get_historical_accuracy(
            db, decision.decision_type, decision.company_id
        )

        # Trend berechnen
        trend = TrendDirection.STABLE
        historical_data = []
        if include_history:
            historical_data = await self._get_historical_data(
                db, decision.decision_type, decision.company_id, history_days
            )
            trend = self._calculate_trend(historical_data)

        # Vergleich mit Durchschnitt
        avg_confidence = await self._get_average_confidence(
            db, decision.decision_type, decision.company_id
        )
        comparison = decision.confidence - avg_confidence if avg_confidence else 0

        # Confidence Level bestimmen
        confidence_level = self._determine_confidence_level(decision.confidence)

        breakdown = ConfidenceBreakdown(
            decision_id=decision_id,
            decision_type=decision.decision_type,
            final_confidence=decision.confidence,
            confidence_level=confidence_level,
            components=components,
            calibration_adjustment=calibration_adj,
            historical_accuracy=historical_acc,
            sample_size=sample_size,
            trend=trend,
            historical_data=historical_data,
            comparison_to_average=comparison,
        )

        CONFIDENCE_BREAKDOWNS_GENERATED.labels(
            decision_type=decision.decision_type,
        ).inc()

        return breakdown

    async def breakdown_by_type(
        self,
        db: AsyncSession,
        company_id: UUID,
        decision_type: str,
        days: int = 30,
    ) -> ConfidenceBreakdown:
        """
        Erstellt aggregierte Confidence-Aufschluesselung für einen Typ.

        Args:
            db: Database Session
            company_id: Company-ID
            decision_type: Entscheidungstyp
            days: Zeitraum

        Returns:
            Aggregierte ConfidenceBreakdown
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Alle Entscheidungen dieses Typs
        query = select(AIDecision).where(
            and_(
                AIDecision.company_id == company_id,
                AIDecision.decision_type == decision_type,
                AIDecision.created_at >= cutoff,
            )
        )

        result = await db.execute(query)
        decisions = result.scalars().all()

        if not decisions:
            return self._create_empty_breakdown(None, decision_type)

        # Durchschnittliche Confidence
        avg_confidence = sum(d.confidence for d in decisions) / len(decisions)

        # Komponenten aggregieren
        components = self._aggregate_components(decisions)

        # Historische Daten
        historical_data = await self._get_historical_data(
            db, decision_type, company_id, days
        )

        # Historische Genauigkeit
        historical_acc, sample_size = await self._get_historical_accuracy(
            db, decision_type, company_id
        )

        trend = self._calculate_trend(historical_data)

        return ConfidenceBreakdown(
            decision_type=decision_type,
            final_confidence=avg_confidence,
            confidence_level=self._determine_confidence_level(avg_confidence),
            components=components,
            historical_accuracy=historical_acc,
            sample_size=sample_size,
            trend=trend,
            historical_data=historical_data,
        )

    async def _load_decision(
        self,
        db: AsyncSession,
        decision_id: UUID,
    ) -> Optional[AIDecision]:
        """Laedt eine Entscheidung."""
        query = select(AIDecision).where(AIDecision.id == decision_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _analyze_components(self, decision: AIDecision) -> List[ConfidenceComponent]:
        """Analysiert die Confidence-Komponenten einer Entscheidung."""
        components = []

        features = decision.features_used or {}
        explanation = decision.explanation or {}

        # Model Output
        model_conf = decision.confidence
        if decision.calibrated_confidence:
            model_conf = decision.confidence / (1 + abs(decision.confidence - decision.calibrated_confidence))

        components.append(ConfidenceComponent(
            component_type=ComponentType.MODEL_OUTPUT,
            name="Modell-Konfidenz",
            contribution=model_conf * self.DEFAULT_WEIGHTS[ComponentType.MODEL_OUTPUT],
            raw_value=model_conf,
            weight=self.DEFAULT_WEIGHTS[ComponentType.MODEL_OUTPUT],
            description=f"Direkte Ausgabe des KI-Modells: {model_conf*100:.0f}%",
        ))

        # Feature Quality
        feature_count = len(features)
        feature_quality = min(1.0, feature_count / 10)  # Max bei 10 Features

        components.append(ConfidenceComponent(
            component_type=ComponentType.FEATURE_QUALITY,
            name="Feature-Qualität",
            contribution=feature_quality * self.DEFAULT_WEIGHTS[ComponentType.FEATURE_QUALITY],
            raw_value=feature_quality,
            weight=self.DEFAULT_WEIGHTS[ComponentType.FEATURE_QUALITY],
            description=f"{feature_count} Features verwendet",
        ))

        # Data Coverage
        data_coverage = 0.7  # Default
        if "data_coverage" in explanation:
            data_coverage = explanation["data_coverage"]

        components.append(ConfidenceComponent(
            component_type=ComponentType.DATA_COVERAGE,
            name="Datenabdeckung",
            contribution=data_coverage * self.DEFAULT_WEIGHTS[ComponentType.DATA_COVERAGE],
            raw_value=data_coverage,
            weight=self.DEFAULT_WEIGHTS[ComponentType.DATA_COVERAGE],
            description=f"Trainingsdaten-Abdeckung: {data_coverage*100:.0f}%",
        ))

        # Kalibrierung
        if decision.calibrated_confidence:
            calibration_factor = decision.calibrated_confidence / decision.confidence if decision.confidence > 0 else 1
            components.append(ConfidenceComponent(
                component_type=ComponentType.CALIBRATION,
                name="Kalibrierung",
                contribution=(calibration_factor - 1) * 0.1,
                raw_value=calibration_factor,
                weight=0.0,  # Multiplikativ, nicht additiv
                description=f"Kalibrierungsfaktor: {calibration_factor:.2f}x",
            ))

        return components

    def _aggregate_components(
        self,
        decisions: List[AIDecision],
    ) -> List[ConfidenceComponent]:
        """Aggregiert Komponenten über mehrere Entscheidungen."""
        if not decisions:
            return []

        # Sammle alle Komponenten
        all_components: Dict[ComponentType, List[ConfidenceComponent]] = {}

        for decision in decisions:
            components = self._analyze_components(decision)
            for comp in components:
                if comp.component_type not in all_components:
                    all_components[comp.component_type] = []
                all_components[comp.component_type].append(comp)

        # Durchschnitte berechnen
        aggregated = []
        for comp_type, comps in all_components.items():
            avg_contribution = sum(c.contribution for c in comps) / len(comps)
            avg_raw = sum(c.raw_value for c in comps) / len(comps)
            weight = comps[0].weight

            aggregated.append(ConfidenceComponent(
                component_type=comp_type,
                name=comps[0].name,
                contribution=avg_contribution,
                raw_value=avg_raw,
                weight=weight,
                description=f"Durchschnitt aus {len(comps)} Entscheidungen",
            ))

        return aggregated

    def _calculate_calibration_adjustment(self, decision: AIDecision) -> float:
        """Berechnet die Kalibrierungsanpassung."""
        if not decision.calibrated_confidence:
            return 0.0

        return decision.calibrated_confidence - decision.confidence

    async def _get_historical_accuracy(
        self,
        db: AsyncSession,
        decision_type: str,
        company_id: Optional[UUID],
    ) -> Tuple[float, int]:
        """Berechnet historische Genauigkeit."""
        # Entscheidungen die reviewed wurden
        query = select(AIDecision).where(
            and_(
                AIDecision.decision_type == decision_type,
                AIDecision.is_final == True,
                AIDecision.reviewed_by_id.isnot(None),
            )
        )

        if company_id:
            query = query.where(AIDecision.company_id == company_id)

        result = await db.execute(query)
        decisions = result.scalars().all()

        if not decisions:
            return 0.0, 0

        # Genauigkeit = (Auto-Applied + Approved) / Total
        correct = sum(1 for d in decisions if d.auto_applied or d.review_action == "approved")
        accuracy = correct / len(decisions)

        return accuracy, len(decisions)

    async def _get_historical_data(
        self,
        db: AsyncSession,
        decision_type: str,
        company_id: Optional[UUID],
        days: int,
    ) -> List[HistoricalDataPoint]:
        """Laedt historische Daten für Trend-Analyse."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        query = select(
            func.date(AIDecision.created_at).label("date"),
            func.avg(AIDecision.confidence).label("avg_confidence"),
            func.count().label("count"),
        ).where(
            and_(
                AIDecision.decision_type == decision_type,
                AIDecision.created_at >= cutoff,
            )
        ).group_by(
            func.date(AIDecision.created_at)
        ).order_by(
            func.date(AIDecision.created_at)
        )

        if company_id:
            query = query.where(AIDecision.company_id == company_id)

        result = await db.execute(query)
        rows = result.all()

        historical_data = []
        for row in rows:
            historical_data.append(HistoricalDataPoint(
                date=datetime.combine(row.date, datetime.min.time()).replace(tzinfo=timezone.utc),
                confidence=float(row.avg_confidence) if row.avg_confidence else 0,
                accuracy=0.0,  # Müsste separat berechnet werden
                sample_size=row.count,
            ))

        return historical_data

    async def _get_average_confidence(
        self,
        db: AsyncSession,
        decision_type: str,
        company_id: Optional[UUID],
    ) -> float:
        """Berechnet durchschnittliche Confidence."""
        query = select(func.avg(AIDecision.confidence)).where(
            AIDecision.decision_type == decision_type
        )

        if company_id:
            query = query.where(AIDecision.company_id == company_id)

        result = await db.execute(query)
        avg = result.scalar_one_or_none()

        return float(avg) if avg else 0.0

    def _calculate_trend(
        self,
        historical_data: List[HistoricalDataPoint],
    ) -> TrendDirection:
        """Berechnet Trend aus historischen Daten."""
        if len(historical_data) < 3:
            return TrendDirection.STABLE

        # Einfache lineare Regression
        n = len(historical_data)
        x_mean = n / 2
        y_values = [h.confidence for h in historical_data]
        y_mean = sum(y_values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(y_values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return TrendDirection.STABLE

        slope = numerator / denominator

        # Normalisierte Steigung
        if y_mean != 0:
            normalized_slope = slope / y_mean
        else:
            normalized_slope = slope

        if normalized_slope > 0.02:
            return TrendDirection.IMPROVING
        elif normalized_slope < -0.02:
            return TrendDirection.DECLINING
        else:
            return TrendDirection.STABLE

    def _determine_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Bestimmt das Confidence-Level."""
        if confidence >= 0.95:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.70:
            return ConfidenceLevel.MEDIUM
        elif confidence >= 0.50:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def _create_empty_breakdown(
        self,
        decision_id: Optional[UUID],
        decision_type: str = "",
    ) -> ConfidenceBreakdown:
        """Erstellt eine leere Breakdown."""
        return ConfidenceBreakdown(
            decision_id=decision_id,
            decision_type=decision_type,
            confidence_level=ConfidenceLevel.VERY_LOW,
        )


# =============================================================================
# Singleton
# =============================================================================

_confidence_visualizer: Optional[ConfidenceVisualizer] = None


def get_confidence_visualizer() -> ConfidenceVisualizer:
    """Gibt die Singleton-Instanz zurück."""
    global _confidence_visualizer
    if _confidence_visualizer is None:
        _confidence_visualizer = ConfidenceVisualizer()
    return _confidence_visualizer
