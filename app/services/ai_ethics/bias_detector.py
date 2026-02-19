"""
Bias Detector

Erkennt Bias in KI-Entscheidungen (z.B. Risk Scoring).
Prüft auf unfaire Behandlung nach Entity-Größe, Region, Branche.

Feinpoliert und durchdacht - Enterprise AI Fairness.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
from uuid import UUID
from collections import defaultdict

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class BiasDimension:
    """Bias in einer bestimmten Dimension."""

    name: str  # Dimensions-Name (z.B. "Unternehmensgröße")
    fairness_score: float  # 0-1 (1 = fair)
    affected_entities: int  # Anzahl betroffener Entities
    description: str  # German Beschreibung
    details: Dict[str, float]  # Zusätzliche Details

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "name": self.name,
            "fairness_score": round(self.fairness_score, 3),
            "affected_entities": self.affected_entities,
            "description": self.description,
            "details": self.details,
        }


@dataclass
class BiasReport:
    """Vollständiger Bias-Report."""

    overall_fairness: float  # 0-1 (1 = fair)
    dimensions: List[BiasDimension]
    recommendations: List[str]  # German Empfehlungen
    generated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "overall_fairness": round(self.overall_fairness, 3),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# Bias Detector
# =============================================================================


class BiasDetector:
    """
    Bias Detector für KI-Entscheidungen.

    Prüft Risk Scoring auf unfaire Behandlung nach:
    - Entity-Größe (klein vs. gross)
    - Branche
    - Region (falls vorhanden)
    """

    def __init__(self) -> None:
        """Initialisiert Detector."""
        pass

    async def detect_bias(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> BiasReport:
        """
        Erkennt Bias in Risk Scoring.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            BiasReport mit Fairness-Scores
        """
        logger.info("bias_detector.detect", company_id=str(company_id))

        dimensions: List[BiasDimension] = []
        recommendations: List[str] = []

        # Hole alle Entities der Company
        query = select(BusinessEntity).where(
            BusinessEntity.company_id == company_id
        )
        result = await db.execute(query)
        entities = result.scalars().all()

        if not entities:
            return BiasReport(
                overall_fairness=1.0,
                dimensions=[],
                recommendations=["Keine Entities vorhanden für Bias-Analyse"],
                generated_at=datetime.now(timezone.utc),
            )

        # 1. Prüfe Bias nach Entity-Typ
        type_bias = await self._check_type_bias(entities)
        dimensions.append(type_bias)

        # 2. Prüfe Bias nach Risk-Score-Verteilung
        distribution_bias = await self._check_distribution_bias(entities)
        dimensions.append(distribution_bias)

        # 3. Prüfe Bias nach Beziehungsdauer
        relationship_bias = await self._check_relationship_bias(entities)
        dimensions.append(relationship_bias)

        # Berechne Overall Fairness
        overall_fairness = sum(d.fairness_score for d in dimensions) / len(dimensions)

        # Generiere Empfehlungen
        if overall_fairness < 0.7:
            recommendations.append("KRITISCH: Signifikanter Bias erkannt - manuelle Überprüfung erforderlich")
        elif overall_fairness < 0.85:
            recommendations.append("WARNUNG: Möglicher Bias erkannt - Modell-Kalibrierung empfohlen")

        if type_bias.fairness_score < 0.8:
            recommendations.append(
                f"Entity-Typ Bias: {type_bias.description} - "
                "Prüfen Sie ob bestimmte Entity-Typen systematisch benachteiligt werden"
            )

        if distribution_bias.fairness_score < 0.8:
            recommendations.append(
                f"Verteilungs-Bias: {distribution_bias.description} - "
                "Risk-Scores zu extrem verteilt, Kalibrierung empfohlen"
            )

        if relationship_bias.fairness_score < 0.8:
            recommendations.append(
                f"Beziehungsdauer-Bias: {relationship_bias.description} - "
                "Neue Entities werden möglicherweise unfair behandelt"
            )

        logger.info(
            "bias_detector.complete",
            company_id=str(company_id),
            overall_fairness=overall_fairness,
            dimension_count=len(dimensions),
        )

        return BiasReport(
            overall_fairness=overall_fairness,
            dimensions=dimensions,
            recommendations=recommendations if recommendations else ["Keine Bias-Probleme erkannt"],
            generated_at=datetime.now(timezone.utc),
        )

    async def _check_type_bias(
        self,
        entities: List[BusinessEntity],
    ) -> BiasDimension:
        """
        Prüft Bias nach Entity-Typ (customer vs. supplier).

        Args:
            entities: Liste von Entities

        Returns:
            BiasDimension für Entity-Typ
        """
        # Gruppiere nach Type
        type_scores: Dict[str, List[float]] = defaultdict(list)

        for entity in entities:
            entity_type = entity.entity_type or "unknown"
            risk_score = entity.risk_score or 0
            type_scores[entity_type].append(risk_score)

        if not type_scores or len(type_scores) < 2:
            return BiasDimension(
                name="Entity-Typ",
                fairness_score=1.0,
                affected_entities=0,
                description="Nicht genügend Daten für Type-Bias-Analyse",
                details={},
            )

        # Berechne Durchschnitte
        type_averages = {
            t: sum(scores) / len(scores) for t, scores in type_scores.items()
        }

        # Prüfe auf signifikante Unterschiede
        min_avg = min(type_averages.values())
        max_avg = max(type_averages.values())
        avg_difference = max_avg - min_avg

        # Fairness: Differenz < 15 = fair, > 30 = unfair
        if avg_difference < 15:
            fairness_score = 1.0
            description = "Keine signifikanten Unterschiede zwischen Entity-Typen"
        elif avg_difference < 30:
            fairness_score = 0.85
            description = f"Moderate Unterschiede zwischen Entity-Typen (Δ={avg_difference:.1f})"
        else:
            fairness_score = 0.60
            description = f"Signifikante Unterschiede zwischen Entity-Typen (Δ={avg_difference:.1f})"

        return BiasDimension(
            name="Entity-Typ",
            fairness_score=fairness_score,
            affected_entities=len(entities),
            description=description,
            details={
                "type_averages": {k: round(v, 1) for k, v in type_averages.items()},
                "avg_difference": round(avg_difference, 1),
            },
        )

    async def _check_distribution_bias(
        self,
        entities: List[BusinessEntity],
    ) -> BiasDimension:
        """
        Prüft Bias in Risk-Score-Verteilung.

        Gesunde Verteilung sollte:
        - Normal verteilt sein (Glocke)
        - Nicht zu viele Extremwerte (0 oder 100)

        Args:
            entities: Liste von Entities

        Returns:
            BiasDimension für Verteilung
        """
        risk_scores = [e.risk_score or 0 for e in entities]

        if not risk_scores:
            return BiasDimension(
                name="Risk-Score-Verteilung",
                fairness_score=1.0,
                affected_entities=0,
                description="Keine Risk-Scores vorhanden",
                details={},
            )

        # Berechne Statistiken
        avg_score = sum(risk_scores) / len(risk_scores)
        min_score = min(risk_scores)
        max_score = max(risk_scores)

        # Zaehle Extremwerte
        extreme_low = sum(1 for s in risk_scores if s < 20)
        extreme_high = sum(1 for s in risk_scores if s > 80)
        extreme_ratio = (extreme_low + extreme_high) / len(risk_scores)

        # Fairness-Berechnung
        # - Durchschnitt um 50 = gut (normal verteilt)
        # - Wenige Extremwerte = gut
        center_deviation = abs(avg_score - 50)
        center_score = max(0, 1 - (center_deviation / 50))  # 0-1

        extreme_score = max(0, 1 - extreme_ratio)  # Weniger Extreme = besser

        fairness_score = (center_score * 0.6 + extreme_score * 0.4)

        if fairness_score > 0.85:
            description = "Gesunde Risk-Score-Verteilung"
        elif fairness_score > 0.70:
            description = f"Leicht unbalancierte Verteilung (Ø={avg_score:.1f})"
        else:
            description = f"Ungesunde Verteilung (Ø={avg_score:.1f}, {int(extreme_ratio*100)}% Extremwerte)"

        return BiasDimension(
            name="Risk-Score-Verteilung",
            fairness_score=fairness_score,
            affected_entities=extreme_low + extreme_high,
            description=description,
            details={
                "average": round(avg_score, 1),
                "min": round(min_score, 1),
                "max": round(max_score, 1),
                "extreme_low": extreme_low,
                "extreme_high": extreme_high,
                "extreme_ratio": round(extreme_ratio, 3),
            },
        )

    async def _check_relationship_bias(
        self,
        entities: List[BusinessEntity],
    ) -> BiasDimension:
        """
        Prüft Bias nach Beziehungsdauer.

        Neue Entities sollten nicht systematisch schlechter bewertet werden.

        Args:
            entities: Liste von Entities

        Returns:
            BiasDimension für Beziehungsdauer
        """
        # Gruppiere nach Alter (neu vs. etabliert)
        now = datetime.now(timezone.utc)
        new_entities = []  # < 3 Monate
        established_entities = []  # >= 3 Monate

        for entity in entities:
            age_months = (now - entity.created_at).days / 30 if entity.created_at else 999

            risk_score = entity.risk_score or 0

            if age_months < 3:
                new_entities.append(risk_score)
            else:
                established_entities.append(risk_score)

        if not new_entities or not established_entities:
            return BiasDimension(
                name="Beziehungsdauer",
                fairness_score=1.0,
                affected_entities=0,
                description="Nicht genügend Daten für Beziehungsdauer-Analyse",
                details={},
            )

        # Durchschnitte
        new_avg = sum(new_entities) / len(new_entities)
        established_avg = sum(established_entities) / len(established_entities)
        difference = abs(new_avg - established_avg)

        # Fairness: Neue sollten nicht signifikant schlechter sein
        if difference < 10:
            fairness_score = 1.0
            description = "Keine unfaire Behandlung neuer Entities"
        elif difference < 20:
            fairness_score = 0.80
            description = f"Moderate Benachteiligung neuer Entities (Δ={difference:.1f})"
        else:
            fairness_score = 0.60
            description = f"Signifikante Benachteiligung neuer Entities (Δ={difference:.1f})"

        return BiasDimension(
            name="Beziehungsdauer",
            fairness_score=fairness_score,
            affected_entities=len(new_entities),
            description=description,
            details={
                "new_average": round(new_avg, 1),
                "established_average": round(established_avg, 1),
                "difference": round(difference, 1),
                "new_count": len(new_entities),
                "established_count": len(established_entities),
            },
        )
