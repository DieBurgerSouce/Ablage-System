# -*- coding: utf-8 -*-
"""
Decision Explainer Service - Erklaerbare KI-Entscheidungen.

Enterprise Feature: Transparenz bei allen KI-Entscheidungen.

Features:
- Faktor-basierte Erklaerungen
- Feature-Importance Visualisierung
- Kontrafaktische Erklaerungen ("Wenn X anders waere...")
- Audit-Trail Integration

Vision: "Warum wurde dieses Dokument als Betrug markiert?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, TypedDict, Union
from uuid import UUID, uuid4

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIDecision

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

EXPLANATIONS_GENERATED = Counter(
    "xai_explanations_generated_total",
    "Total explanations generated",
    ["explanation_type", "decision_type"]
)

EXPLANATION_GENERATION_TIME = Histogram(
    "xai_explanation_generation_seconds",
    "Time to generate explanations",
    ["explanation_type"]
)


# =============================================================================
# Enums
# =============================================================================

class ExplanationType(str, Enum):
    """Typ der Erklaerung."""
    FACTOR_BASED = "factor_based"       # Faktor-gewichtete Erklaerung
    RULE_BASED = "rule_based"           # Regel-basierte Erklaerung
    EXAMPLE_BASED = "example_based"     # Beispiel-basierte Erklaerung
    COUNTERFACTUAL = "counterfactual"   # Kontrafaktische Erklaerung
    NATURAL_LANGUAGE = "natural_language"  # Natuerlichsprachliche Erklaerung


class FactorDirection(str, Enum):
    """Richtung des Einflusses."""
    POSITIVE = "positive"   # Unterstuetzt die Entscheidung
    NEGATIVE = "negative"   # Spricht gegen die Entscheidung
    NEUTRAL = "neutral"     # Kein signifikanter Einfluss


class ConfidenceImpact(str, Enum):
    """Auswirkung auf Confidence."""
    STRONG_INCREASE = "strong_increase"   # +20% oder mehr
    MODERATE_INCREASE = "moderate_increase"  # +5-20%
    SLIGHT_INCREASE = "slight_increase"   # +1-5%
    NO_CHANGE = "no_change"
    SLIGHT_DECREASE = "slight_decrease"
    MODERATE_DECREASE = "moderate_decrease"
    STRONG_DECREASE = "strong_decrease"


# =============================================================================
# TypedDicts
# =============================================================================

class ExplanationFactorDict(TypedDict):
    """Ein Erklaerungsfaktor."""
    factor_name: str
    factor_value: str
    weight: float
    direction: str
    impact: str
    description: str
    evidence: JSONDict


class CounterfactualDict(TypedDict):
    """Kontrafaktische Erklaerung."""
    condition: str
    original_value: str
    alternative_value: str
    result_change: str
    confidence_change: float


class DecisionExplanationDict(TypedDict):
    """Vollstaendige Erklaerung einer Entscheidung."""
    id: str
    decision_id: str
    explanation_type: str
    decision_type: str
    decision_value: JSONDict
    confidence: float
    summary: str
    detailed_explanation: str
    factors: List[ExplanationFactorDict]
    counterfactuals: List[CounterfactualDict]
    similar_cases_count: int
    audit_trail: List[JSONDict]
    generated_at: str


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExplanationFactor:
    """Ein Faktor der zur Entscheidung beigetragen hat."""
    factor_name: str
    factor_value: str
    weight: float  # -1.0 bis 1.0
    direction: FactorDirection
    impact: ConfidenceImpact
    description: str
    evidence: JSONDict = field(default_factory=dict)

    def to_dict(self) -> ExplanationFactorDict:
        """Konvertiert zu Dictionary."""
        return ExplanationFactorDict(
            factor_name=self.factor_name,
            factor_value=self.factor_value,
            weight=self.weight,
            direction=self.direction.value,
            impact=self.impact.value,
            description=self.description,
            evidence=self.evidence,
        )


@dataclass
class Counterfactual:
    """Eine kontrafaktische Erklaerung."""
    condition: str
    original_value: str
    alternative_value: str
    result_change: str
    confidence_change: float  # Wie wuerde sich Confidence aendern

    def to_dict(self) -> CounterfactualDict:
        """Konvertiert zu Dictionary."""
        return CounterfactualDict(
            condition=self.condition,
            original_value=self.original_value,
            alternative_value=self.alternative_value,
            result_change=self.result_change,
            confidence_change=self.confidence_change,
        )


@dataclass
class DecisionExplanation:
    """Vollstaendige Erklaerung einer KI-Entscheidung."""
    id: UUID = field(default_factory=uuid4)
    decision_id: Optional[UUID] = None
    explanation_type: ExplanationType = ExplanationType.FACTOR_BASED
    decision_type: str = ""
    decision_value: JSONDict = field(default_factory=dict)
    confidence: float = 0.0

    # Erklaerungen
    summary: str = ""
    detailed_explanation: str = ""
    factors: List[ExplanationFactor] = field(default_factory=list)
    counterfactuals: List[Counterfactual] = field(default_factory=list)

    # Kontext
    similar_cases_count: int = 0
    audit_trail: List[JSONDict] = field(default_factory=list)

    # Metadata
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> DecisionExplanationDict:
        """Konvertiert zu Dictionary."""
        return DecisionExplanationDict(
            id=str(self.id),
            decision_id=str(self.decision_id) if self.decision_id else "",
            explanation_type=self.explanation_type.value,
            decision_type=self.decision_type,
            decision_value=self.decision_value,
            confidence=self.confidence,
            summary=self.summary,
            detailed_explanation=self.detailed_explanation,
            factors=[f.to_dict() for f in self.factors],
            counterfactuals=[c.to_dict() for c in self.counterfactuals],
            similar_cases_count=self.similar_cases_count,
            audit_trail=self.audit_trail,
            generated_at=self.generated_at.isoformat(),
        )


# =============================================================================
# Decision Explainer Service
# =============================================================================

class DecisionExplainer:
    """
    Service zur Erklaerung von KI-Entscheidungen.

    Generiert verstaendliche Erklaerungen fuer:
    - Kategorisierungen
    - Anomalie-Erkennungen
    - Matching-Entscheidungen
    - Vorhersagen

    Prinzipien:
    - Transparenz: Alle Faktoren werden offengelegt
    - Verstaendlichkeit: Deutsche natuerlichsprachliche Erklaerungen
    - Nachvollziehbarkeit: Audit-Trail fuer Compliance
    """

    # Faktor-Gewichte fuer verschiedene Entscheidungstypen
    FACTOR_WEIGHTS = {
        "categorization": {
            "document_type_keywords": 0.35,
            "entity_match": 0.25,
            "historical_pattern": 0.20,
            "amount_range": 0.10,
            "date_pattern": 0.10,
        },
        "accounting": {
            "account_suggestion": 0.40,
            "tax_rate_match": 0.25,
            "historical_booking": 0.20,
            "amount_validation": 0.15,
        },
        "matching": {
            "amount_match": 0.35,
            "date_proximity": 0.25,
            "entity_match": 0.25,
            "reference_match": 0.15,
        },
        "anomaly": {
            "statistical_deviation": 0.40,
            "pattern_break": 0.30,
            "frequency_anomaly": 0.20,
            "context_mismatch": 0.10,
        },
        "duplicate": {
            "content_similarity": 0.35,
            "metadata_match": 0.25,
            "timing_proximity": 0.20,
            "entity_match": 0.20,
        },
    }

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def explain(
        self,
        db: AsyncSession,
        decision_id: UUID,
        include_counterfactuals: bool = True,
        include_similar_cases: bool = True,
    ) -> DecisionExplanation:
        """
        Generiert Erklaerung fuer eine Entscheidung.

        Args:
            db: Database Session
            decision_id: ID der zu erklaerenden Entscheidung
            include_counterfactuals: Kontrafaktische Erklaerungen generieren
            include_similar_cases: Aehnliche Faelle einbeziehen

        Returns:
            DecisionExplanation mit allen Details
        """
        import time
        start_time = time.perf_counter()

        logger.info(
            "generating_explanation",
            decision_id=str(decision_id),
        )

        # Entscheidung laden
        decision = await self._load_decision(db, decision_id)
        if not decision:
            logger.warning("decision_not_found", decision_id=str(decision_id))
            return self._create_not_found_explanation(decision_id)

        # Faktoren extrahieren
        factors = self._extract_factors(decision)

        # Zusammenfassung generieren
        summary = self._generate_summary(decision, factors)

        # Detaillierte Erklaerung
        detailed = self._generate_detailed_explanation(decision, factors)

        # Kontrafaktische Erklaerungen
        counterfactuals = []
        if include_counterfactuals:
            counterfactuals = self._generate_counterfactuals(decision, factors)

        # Aehnliche Faelle
        similar_count = 0
        if include_similar_cases:
            similar_count = await self._count_similar_cases(db, decision)

        # Audit-Trail
        audit_trail = self._build_audit_trail(decision)

        explanation = DecisionExplanation(
            decision_id=decision_id,
            explanation_type=ExplanationType.FACTOR_BASED,
            decision_type=decision.decision_type,
            decision_value=decision.decision_value or {},
            confidence=decision.confidence,
            summary=summary,
            detailed_explanation=detailed,
            factors=factors,
            counterfactuals=counterfactuals,
            similar_cases_count=similar_count,
            audit_trail=audit_trail,
        )

        duration = time.perf_counter() - start_time

        EXPLANATIONS_GENERATED.labels(
            explanation_type=ExplanationType.FACTOR_BASED.value,
            decision_type=decision.decision_type,
        ).inc()

        EXPLANATION_GENERATION_TIME.labels(
            explanation_type=ExplanationType.FACTOR_BASED.value,
        ).observe(duration)

        logger.info(
            "explanation_generated",
            decision_id=str(decision_id),
            factor_count=len(factors),
            counterfactual_count=len(counterfactuals),
            duration_seconds=duration,
        )

        return explanation

    async def explain_batch(
        self,
        db: AsyncSession,
        decision_ids: List[UUID],
    ) -> List[DecisionExplanation]:
        """Erklaert mehrere Entscheidungen."""
        explanations = []
        for decision_id in decision_ids:
            explanation = await self.explain(
                db, decision_id,
                include_counterfactuals=False,  # Performance
                include_similar_cases=False,
            )
            explanations.append(explanation)
        return explanations

    async def _load_decision(
        self,
        db: AsyncSession,
        decision_id: UUID,
    ) -> Optional[AIDecision]:
        """Laedt eine Entscheidung aus der DB."""
        query = select(AIDecision).where(AIDecision.id == decision_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _extract_factors(self, decision: AIDecision) -> List[ExplanationFactor]:
        """Extrahiert Erklaerungsfaktoren aus einer Entscheidung."""
        factors = []

        # Faktoren aus stored explanation
        stored_explanation = decision.explanation or {}

        if "factors" in stored_explanation:
            for factor_data in stored_explanation["factors"]:
                factors.append(ExplanationFactor(
                    factor_name=factor_data.get("name", "Unbekannt"),
                    factor_value=str(factor_data.get("value", "")),
                    weight=factor_data.get("weight", 0.0),
                    direction=self._determine_direction(factor_data.get("weight", 0)),
                    impact=self._determine_impact(factor_data.get("weight", 0)),
                    description=factor_data.get("description", ""),
                    evidence=factor_data.get("evidence", {}),
                ))

        # Faktoren aus features_used
        features = decision.features_used or {}
        weights = self.FACTOR_WEIGHTS.get(decision.decision_type, {})

        for feature_name, feature_value in features.items():
            if feature_name in weights:
                weight = weights[feature_name]

                # Normalisieren auf -1 bis 1 basierend auf Confidence-Beitrag
                normalized_weight = weight * (2 * decision.confidence - 1)

                factors.append(ExplanationFactor(
                    factor_name=self._translate_feature_name(feature_name),
                    factor_value=str(feature_value),
                    weight=normalized_weight,
                    direction=self._determine_direction(normalized_weight),
                    impact=self._determine_impact(weight),
                    description=self._generate_factor_description(feature_name, feature_value),
                    evidence={"raw_value": feature_value, "base_weight": weight},
                ))

        # Sortieren nach absolutem Gewicht
        factors.sort(key=lambda f: abs(f.weight), reverse=True)

        return factors

    def _determine_direction(self, weight: float) -> FactorDirection:
        """Bestimmt die Richtung basierend auf dem Gewicht."""
        if weight > 0.1:
            return FactorDirection.POSITIVE
        elif weight < -0.1:
            return FactorDirection.NEGATIVE
        else:
            return FactorDirection.NEUTRAL

    def _determine_impact(self, weight: float) -> ConfidenceImpact:
        """Bestimmt den Impact basierend auf dem Gewicht."""
        abs_weight = abs(weight)

        if abs_weight >= 0.3:
            return ConfidenceImpact.STRONG_INCREASE if weight > 0 else ConfidenceImpact.STRONG_DECREASE
        elif abs_weight >= 0.15:
            return ConfidenceImpact.MODERATE_INCREASE if weight > 0 else ConfidenceImpact.MODERATE_DECREASE
        elif abs_weight >= 0.05:
            return ConfidenceImpact.SLIGHT_INCREASE if weight > 0 else ConfidenceImpact.SLIGHT_DECREASE
        else:
            return ConfidenceImpact.NO_CHANGE

    def _translate_feature_name(self, feature_name: str) -> str:
        """Uebersetzt technische Feature-Namen ins Deutsche."""
        translations = {
            "document_type_keywords": "Dokumenttyp-Schluesselwoerter",
            "entity_match": "Geschaeftspartner-Uebereinstimmung",
            "historical_pattern": "Historisches Muster",
            "amount_range": "Betragsbereich",
            "date_pattern": "Datumsmuster",
            "account_suggestion": "Kontovorschlag",
            "tax_rate_match": "Steuersatz-Uebereinstimmung",
            "historical_booking": "Historische Buchung",
            "amount_validation": "Betragsvalidierung",
            "amount_match": "Betrags-Uebereinstimmung",
            "date_proximity": "Datumsnaehe",
            "reference_match": "Referenz-Uebereinstimmung",
            "statistical_deviation": "Statistische Abweichung",
            "pattern_break": "Musterbruch",
            "frequency_anomaly": "Haeufigkeitsanomalie",
            "context_mismatch": "Kontext-Diskrepanz",
            "content_similarity": "Inhaltsaehnlichkeit",
            "metadata_match": "Metadaten-Uebereinstimmung",
            "timing_proximity": "Zeitliche Naehe",
        }
        return translations.get(feature_name, feature_name)

    def _generate_factor_description(self, feature_name: str, feature_value: JSONValue) -> str:
        """Generiert eine natuerlichsprachliche Beschreibung fuer einen Faktor."""
        descriptions = {
            "document_type_keywords": f"Schluesselwoerter im Dokument deuten auf diesen Typ hin: {feature_value}",
            "entity_match": f"Geschaeftspartner wurde mit {feature_value}% Sicherheit erkannt",
            "historical_pattern": f"Aehnliche Dokumente wurden historisch so kategorisiert: {feature_value}",
            "amount_range": f"Betrag liegt im erwarteten Bereich: {feature_value}",
            "amount_match": f"Betraege stimmen zu {feature_value}% ueberein",
            "date_proximity": f"Datumsnaehe: {feature_value} Tage Differenz",
            "statistical_deviation": f"Statistische Abweichung: {feature_value} Standardabweichungen",
            "pattern_break": f"Musterbruch erkannt: {feature_value}",
            "content_similarity": f"Inhaltsaehnlichkeit: {feature_value}%",
        }
        return descriptions.get(feature_name, f"Wert: {feature_value}")

    def _generate_summary(
        self,
        decision: AIDecision,
        factors: List[ExplanationFactor],
    ) -> str:
        """Generiert eine kurze Zusammenfassung der Entscheidung."""
        confidence_text = self._confidence_to_text(decision.confidence)
        decision_type_text = self._decision_type_to_text(decision.decision_type)

        # Top-Faktoren
        top_positive = [f for f in factors if f.direction == FactorDirection.POSITIVE][:2]
        top_negative = [f for f in factors if f.direction == FactorDirection.NEGATIVE][:1]

        summary_parts = [
            f"Diese {decision_type_text} wurde mit {confidence_text} Sicherheit ({decision.confidence*100:.0f}%) getroffen."
        ]

        if top_positive:
            factor_names = ", ".join(f.factor_name for f in top_positive)
            summary_parts.append(f"Hauptgruende: {factor_names}.")

        if top_negative:
            summary_parts.append(f"Bedenken: {top_negative[0].factor_name}.")

        return " ".join(summary_parts)

    def _generate_detailed_explanation(
        self,
        decision: AIDecision,
        factors: List[ExplanationFactor],
    ) -> str:
        """Generiert eine ausfuehrliche Erklaerung."""
        lines = []

        decision_value = decision.decision_value or {}
        decision_type_text = self._decision_type_to_text(decision.decision_type)

        lines.append(f"## {decision_type_text}")
        lines.append("")

        if decision_value:
            lines.append("### Ergebnis")
            for key, value in decision_value.items():
                lines.append(f"- **{key}**: {value}")
            lines.append("")

        lines.append("### Einflussfaktoren")
        lines.append("")

        for factor in factors[:5]:  # Top 5 Faktoren
            direction_icon = "+" if factor.direction == FactorDirection.POSITIVE else "-" if factor.direction == FactorDirection.NEGATIVE else "="
            lines.append(f"**{direction_icon} {factor.factor_name}** (Gewicht: {abs(factor.weight)*100:.0f}%)")
            lines.append(f"  - {factor.description}")
            lines.append("")

        if decision.confidence >= 0.95:
            lines.append("### Bewertung")
            lines.append("Diese Entscheidung wurde automatisch angewendet, da die Konfidenz sehr hoch ist.")
        elif decision.confidence >= 0.8:
            lines.append("### Bewertung")
            lines.append("Diese Entscheidung wird als Vorschlag angezeigt und wartet auf Bestaetigung.")
        else:
            lines.append("### Bewertung")
            lines.append("Diese Entscheidung erfordert manuelle Pruefung aufgrund niedriger Konfidenz.")

        return "\n".join(lines)

    def _generate_counterfactuals(
        self,
        decision: AIDecision,
        factors: List[ExplanationFactor],
    ) -> List[Counterfactual]:
        """Generiert kontrafaktische Erklaerungen."""
        counterfactuals = []

        # Fuer jeden wichtigen negativen Faktor
        negative_factors = [f for f in factors if f.direction == FactorDirection.NEGATIVE]

        for factor in negative_factors[:2]:
            # "Wenn dieser Faktor anders waere..."
            counterfactuals.append(Counterfactual(
                condition=f"Wenn {factor.factor_name} besser waere",
                original_value=factor.factor_value,
                alternative_value="hoeherer Wert",
                result_change="Konfidenz wuerde steigen",
                confidence_change=abs(factor.weight) * 0.5,  # Geschaetzte Aenderung
            ))

        # Konfidenz-Schwelle
        if 0.8 <= decision.confidence < 0.95:
            needed_increase = 0.95 - decision.confidence
            counterfactuals.append(Counterfactual(
                condition="Fuer automatische Anwendung",
                original_value=f"{decision.confidence*100:.0f}%",
                alternative_value="95%+",
                result_change="Entscheidung wuerde automatisch angewendet",
                confidence_change=needed_increase,
            ))

        return counterfactuals

    async def _count_similar_cases(
        self,
        db: AsyncSession,
        decision: AIDecision,
    ) -> int:
        """Zaehlt aehnliche historische Faelle."""
        from sqlalchemy import func

        # Gleicher Entscheidungstyp, aehnliches Ergebnis
        query = select(func.count()).where(
            and_(
                AIDecision.decision_type == decision.decision_type,
                AIDecision.company_id == decision.company_id,
                AIDecision.is_final == True,
                AIDecision.id != decision.id,
            )
        )

        result = await db.execute(query)
        return result.scalar_one_or_none() or 0

    def _build_audit_trail(self, decision: AIDecision) -> List[JSONDict]:
        """Erstellt den Audit-Trail fuer die Entscheidung."""
        trail = []

        # Erstellung
        trail.append({
            "timestamp": decision.created_at.isoformat() if decision.created_at else "",
            "event": "decision_created",
            "description": "KI-Entscheidung erstellt",
            "details": {
                "decision_type": decision.decision_type,
                "confidence": decision.confidence,
                "auto_applied": decision.auto_applied,
            },
        })

        # Review
        if decision.reviewed_at:
            trail.append({
                "timestamp": decision.reviewed_at.isoformat(),
                "event": "decision_reviewed",
                "description": f"Entscheidung wurde reviewed: {decision.review_action}",
                "details": {
                    "action": decision.review_action,
                    "reviewer_id": str(decision.reviewed_by_id) if decision.reviewed_by_id else None,
                },
            })

        return trail

    def _confidence_to_text(self, confidence: float) -> str:
        """Konvertiert Confidence zu deutschem Text."""
        if confidence >= 0.95:
            return "sehr hoher"
        elif confidence >= 0.85:
            return "hoher"
        elif confidence >= 0.70:
            return "mittlerer"
        elif confidence >= 0.50:
            return "niedriger"
        else:
            return "sehr niedriger"

    def _decision_type_to_text(self, decision_type: str) -> str:
        """Konvertiert Decision-Type zu deutschem Text."""
        translations = {
            "categorization": "Kategorisierung",
            "accounting": "Buchhaltungsentscheidung",
            "matching": "Zuordnungsentscheidung",
            "anomaly": "Anomalie-Erkennung",
            "prediction": "Vorhersage",
            "duplicate": "Duplikat-Erkennung",
        }
        return translations.get(decision_type, "Entscheidung")

    def _create_not_found_explanation(self, decision_id: UUID) -> DecisionExplanation:
        """Erstellt eine Erklaerung fuer nicht gefundene Entscheidungen."""
        return DecisionExplanation(
            decision_id=decision_id,
            explanation_type=ExplanationType.NATURAL_LANGUAGE,
            summary="Entscheidung nicht gefunden.",
            detailed_explanation="Die angeforderte KI-Entscheidung konnte nicht in der Datenbank gefunden werden.",
        )


# =============================================================================
# Singleton
# =============================================================================

_decision_explainer: Optional[DecisionExplainer] = None


def get_decision_explainer() -> DecisionExplainer:
    """Gibt die Singleton-Instanz zurueck."""
    global _decision_explainer
    if _decision_explainer is None:
        _decision_explainer = DecisionExplainer()
    return _decision_explainer
