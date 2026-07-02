# -*- coding: utf-8 -*-
"""
Case Comparator Service - Ähnliche Faelle finden und vergleichen.

Enterprise Feature: "Basierend auf 47 ähnlichen Faellen..."

Features:
- Ähnliche historische Faelle finden
- Ergebnisse vergleichen
- Erfolgswahrscheinlichkeit ableiten
- Lerneffekte visualisieren

Vision: Zeige dem User wie ähnliche Faelle in der Vergangenheit behandelt wurden.
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
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIDecision, Document

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

CASE_COMPARISONS_GENERATED = Counter(
    "case_comparisons_generated_total",
    "Total case comparisons generated",
    ["decision_type"]
)

SIMILAR_CASES_FOUND = Histogram(
    "similar_cases_found_count",
    "Number of similar cases found",
    ["decision_type"],
    buckets=[0, 1, 5, 10, 25, 50, 100, 250, 500, 1000]
)


# =============================================================================
# Enums
# =============================================================================

class SimilarityLevel(str, Enum):
    """Grad der Ähnlichkeit."""
    EXACT = "exact"           # Praktisch identisch (>95%)
    VERY_HIGH = "very_high"   # Sehr ähnlich (85-95%)
    HIGH = "high"             # Ähnlich (70-85%)
    MODERATE = "moderate"     # Maessig ähnlich (50-70%)
    LOW = "low"               # Wenig ähnlich (30-50%)


class OutcomeType(str, Enum):
    """Ergebnis des ähnlichen Falls."""
    AUTO_APPROVED = "auto_approved"     # Automatisch angewendet
    MANUALLY_APPROVED = "manually_approved"  # Manuell genehmigt
    MODIFIED = "modified"               # Modifiziert
    REJECTED = "rejected"               # Abgelehnt


# =============================================================================
# TypedDicts
# =============================================================================

class SimilarityScoreDict(TypedDict):
    """Ähnlichkeits-Score Aufschluesselung."""
    overall: float
    decision_type_match: float
    entity_match: float
    amount_similarity: float
    time_proximity: float
    feature_overlap: float


class SimilarCaseDict(TypedDict):
    """Ein ähnlicher Fall."""
    case_id: str
    decision_id: str
    document_id: Optional[str]
    similarity_score: float
    similarity_level: str
    similarity_breakdown: SimilarityScoreDict
    decision_type: str
    decision_value: Dict[str, Any]
    confidence: float
    outcome: str
    review_action: Optional[str]
    created_at: str
    entity_name: Optional[str]
    amount: Optional[float]


class CaseComparisonDict(TypedDict):
    """Vergleich mit ähnlichen Faellen."""
    id: str
    source_decision_id: str
    total_similar_cases: int
    cases_by_outcome: Dict[str, int]
    average_similarity: float
    success_rate: float
    predicted_outcome: str
    prediction_confidence: float
    similar_cases: List[SimilarCaseDict]
    insights: List[str]
    generated_at: str


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SimilarityScore:
    """Detaillierter Ähnlichkeits-Score."""
    overall: float = 0.0
    decision_type_match: float = 0.0
    entity_match: float = 0.0
    amount_similarity: float = 0.0
    time_proximity: float = 0.0
    feature_overlap: float = 0.0

    def to_dict(self) -> SimilarityScoreDict:
        """Konvertiert zu Dictionary."""
        return SimilarityScoreDict(
            overall=self.overall,
            decision_type_match=self.decision_type_match,
            entity_match=self.entity_match,
            amount_similarity=self.amount_similarity,
            time_proximity=self.time_proximity,
            feature_overlap=self.feature_overlap,
        )


@dataclass
class SimilarCase:
    """Ein ähnlicher historischer Fall."""
    case_id: UUID = field(default_factory=uuid4)
    decision_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    similarity_score: float = 0.0
    similarity_level: SimilarityLevel = SimilarityLevel.MODERATE
    similarity_breakdown: SimilarityScore = field(default_factory=SimilarityScore)
    decision_type: str = ""
    decision_value: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    outcome: OutcomeType = OutcomeType.AUTO_APPROVED
    review_action: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entity_name: Optional[str] = None
    amount: Optional[Decimal] = None

    def to_dict(self) -> SimilarCaseDict:
        """Konvertiert zu Dictionary."""
        return SimilarCaseDict(
            case_id=str(self.case_id),
            decision_id=str(self.decision_id) if self.decision_id else "",
            document_id=str(self.document_id) if self.document_id else None,
            similarity_score=self.similarity_score,
            similarity_level=self.similarity_level.value,
            similarity_breakdown=self.similarity_breakdown.to_dict(),
            decision_type=self.decision_type,
            decision_value=self.decision_value,
            confidence=self.confidence,
            outcome=self.outcome.value,
            review_action=self.review_action,
            created_at=self.created_at.isoformat(),
            entity_name=self.entity_name,
            amount=float(self.amount) if self.amount else None,
        )


@dataclass
class CaseComparison:
    """Vollständiger Vergleich mit ähnlichen Faellen."""
    id: UUID = field(default_factory=uuid4)
    source_decision_id: Optional[UUID] = None
    total_similar_cases: int = 0
    cases_by_outcome: Dict[str, int] = field(default_factory=dict)
    average_similarity: float = 0.0
    success_rate: float = 0.0  # Rate der erfolgreichen Entscheidungen
    predicted_outcome: str = ""
    prediction_confidence: float = 0.0
    similar_cases: List[SimilarCase] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> CaseComparisonDict:
        """Konvertiert zu Dictionary."""
        return CaseComparisonDict(
            id=str(self.id),
            source_decision_id=str(self.source_decision_id) if self.source_decision_id else "",
            total_similar_cases=self.total_similar_cases,
            cases_by_outcome=self.cases_by_outcome,
            average_similarity=self.average_similarity,
            success_rate=self.success_rate,
            predicted_outcome=self.predicted_outcome,
            prediction_confidence=self.prediction_confidence,
            similar_cases=[c.to_dict() for c in self.similar_cases],
            insights=self.insights,
            generated_at=self.generated_at.isoformat(),
        )


# =============================================================================
# Case Comparator Service
# =============================================================================

class CaseComparator:
    """
    Service zum Finden und Vergleichen ähnlicher Faelle.

    Hilft Benutzern zu verstehen wie ähnliche Faelle
    in der Vergangenheit behandelt wurden.
    """

    # Gewichte für Ähnlichkeitsberechnung
    SIMILARITY_WEIGHTS = {
        "decision_type": 0.30,
        "entity": 0.20,
        "amount": 0.20,
        "time": 0.10,
        "features": 0.20,
    }

    # Minimum Ähnlichkeit für Einbeziehung
    MIN_SIMILARITY = 0.30

    # Maximum Faelle zurückgeben
    MAX_SIMILAR_CASES = 50

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    async def compare(
        self,
        db: AsyncSession,
        decision_id: UUID,
        max_cases: int = 10,
        min_similarity: float = MIN_SIMILARITY,
    ) -> CaseComparison:
        """
        Vergleicht eine Entscheidung mit ähnlichen historischen Faellen.

        Args:
            db: Database Session
            decision_id: ID der zu vergleichenden Entscheidung
            max_cases: Maximale Anzahl zurückzugebender Faelle
            min_similarity: Minimale Ähnlichkeit (0-1)

        Returns:
            CaseComparison mit allen ähnlichen Faellen
        """
        logger.info(
            "comparing_cases",
            decision_id=str(decision_id),
            max_cases=max_cases,
        )

        # Quell-Entscheidung laden
        source_decision = await self._load_decision(db, decision_id)
        if not source_decision:
            return self._create_empty_comparison(decision_id)

        # Ähnliche Faelle finden
        similar_cases = await self._find_similar_cases(
            db, source_decision, max_cases, min_similarity
        )

        # Statistiken berechnen
        outcome_counts = self._count_outcomes(similar_cases)
        avg_similarity = self._calculate_average_similarity(similar_cases)
        success_rate = self._calculate_success_rate(similar_cases)

        # Vorhersage ableiten
        predicted_outcome, prediction_confidence = self._predict_outcome(similar_cases)

        # Insights generieren
        insights = self._generate_insights(source_decision, similar_cases, outcome_counts)

        comparison = CaseComparison(
            source_decision_id=decision_id,
            total_similar_cases=len(similar_cases),
            cases_by_outcome=outcome_counts,
            average_similarity=avg_similarity,
            success_rate=success_rate,
            predicted_outcome=predicted_outcome,
            prediction_confidence=prediction_confidence,
            similar_cases=similar_cases[:max_cases],
            insights=insights,
        )

        CASE_COMPARISONS_GENERATED.labels(
            decision_type=source_decision.decision_type,
        ).inc()

        SIMILAR_CASES_FOUND.labels(
            decision_type=source_decision.decision_type,
        ).observe(len(similar_cases))

        logger.info(
            "case_comparison_completed",
            decision_id=str(decision_id),
            similar_cases_found=len(similar_cases),
            success_rate=success_rate,
            predicted_outcome=predicted_outcome,
        )

        return comparison

    async def find_similar(
        self,
        db: AsyncSession,
        decision_type: str,
        company_id: UUID,
        features: Dict[str, Any],
        max_cases: int = 10,
    ) -> List[SimilarCase]:
        """
        Findet ähnliche Faelle basierend auf Features (ohne bestehende Entscheidung).

        Args:
            db: Database Session
            decision_type: Typ der Entscheidung
            company_id: Company-ID
            features: Features zum Vergleichen
            max_cases: Maximale Anzahl Faelle

        Returns:
            Liste ähnlicher Faelle
        """
        # Kandidaten laden
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)

        query = select(AIDecision).where(
            and_(
                AIDecision.decision_type == decision_type,
                AIDecision.company_id == company_id,
                AIDecision.is_final == True,
                AIDecision.created_at >= cutoff,
            )
        ).limit(1000)  # Performance-Limit

        result = await db.execute(query)
        candidates = result.scalars().all()

        # Ähnlichkeit berechnen
        similar_cases = []
        for candidate in candidates:
            similarity = self._calculate_feature_similarity(features, candidate.features_used or {})

            if similarity >= self.MIN_SIMILARITY:
                outcome = self._determine_outcome(candidate)
                level = self._similarity_to_level(similarity)

                similar_cases.append(SimilarCase(
                    decision_id=candidate.id,
                    document_id=candidate.document_id,
                    similarity_score=similarity,
                    similarity_level=level,
                    similarity_breakdown=SimilarityScore(
                        overall=similarity,
                        decision_type_match=1.0,
                        feature_overlap=similarity,
                    ),
                    decision_type=candidate.decision_type,
                    decision_value=candidate.decision_value or {},
                    confidence=candidate.confidence,
                    outcome=outcome,
                    review_action=candidate.review_action,
                    created_at=candidate.created_at,
                ))

        # Sortieren nach Ähnlichkeit
        similar_cases.sort(key=lambda c: c.similarity_score, reverse=True)

        return similar_cases[:max_cases]

    async def _load_decision(
        self,
        db: AsyncSession,
        decision_id: UUID,
    ) -> Optional[AIDecision]:
        """Laedt eine Entscheidung."""
        query = select(AIDecision).where(AIDecision.id == decision_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _find_similar_cases(
        self,
        db: AsyncSession,
        source: AIDecision,
        max_cases: int,
        min_similarity: float,
    ) -> List[SimilarCase]:
        """Findet ähnliche Faelle für eine Entscheidung."""
        # Zeitfenster für Suche
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)

        # Kandidaten laden (gleicher Typ, gleiche Company)
        query = select(AIDecision).where(
            and_(
                AIDecision.decision_type == source.decision_type,
                AIDecision.company_id == source.company_id,
                AIDecision.id != source.id,
                AIDecision.is_final == True,
                AIDecision.created_at >= cutoff,
            )
        ).limit(self.MAX_SIMILAR_CASES * 10)  # 10x mehr laden für Filterung

        result = await db.execute(query)
        candidates = result.scalars().all()

        similar_cases = []

        for candidate in candidates:
            # Ähnlichkeit berechnen
            similarity_breakdown = self._calculate_similarity(source, candidate)

            if similarity_breakdown.overall >= min_similarity:
                outcome = self._determine_outcome(candidate)
                level = self._similarity_to_level(similarity_breakdown.overall)

                # Entity-Name aus Document laden (wenn vorhanden)
                entity_name = None
                amount = None

                decision_value = candidate.decision_value or {}
                if "entity_name" in decision_value:
                    entity_name = decision_value["entity_name"]
                if "amount" in decision_value:
                    try:
                        amount = Decimal(str(decision_value["amount"]))
                    except (ValueError, TypeError) as e:
                        logger.debug(
                            "case_comparator_amount_parse_skipped",
                            error_type=type(e).__name__,
                        )

                similar_cases.append(SimilarCase(
                    decision_id=candidate.id,
                    document_id=candidate.document_id,
                    similarity_score=similarity_breakdown.overall,
                    similarity_level=level,
                    similarity_breakdown=similarity_breakdown,
                    decision_type=candidate.decision_type,
                    decision_value=decision_value,
                    confidence=candidate.confidence,
                    outcome=outcome,
                    review_action=candidate.review_action,
                    created_at=candidate.created_at,
                    entity_name=entity_name,
                    amount=amount,
                ))

        # Sortieren nach Ähnlichkeit
        similar_cases.sort(key=lambda c: c.similarity_score, reverse=True)

        return similar_cases[:self.MAX_SIMILAR_CASES]

    def _calculate_similarity(
        self,
        source: AIDecision,
        candidate: AIDecision,
    ) -> SimilarityScore:
        """Berechnet detaillierte Ähnlichkeit zwischen zwei Entscheidungen."""
        score = SimilarityScore()

        # Decision Type (sollte immer 1.0 sein, da wir vorfiltern)
        score.decision_type_match = 1.0 if source.decision_type == candidate.decision_type else 0.0

        # Entity Match
        source_value = source.decision_value or {}
        candidate_value = candidate.decision_value or {}

        if source_value.get("entity_id") and candidate_value.get("entity_id"):
            score.entity_match = 1.0 if source_value["entity_id"] == candidate_value["entity_id"] else 0.0
        else:
            score.entity_match = 0.5  # Unbekannt

        # Amount Similarity
        source_amount = source_value.get("amount")
        candidate_amount = candidate_value.get("amount")

        if source_amount and candidate_amount:
            try:
                s_amt = float(source_amount)
                c_amt = float(candidate_amount)
                if max(s_amt, c_amt) > 0:
                    diff_ratio = abs(s_amt - c_amt) / max(s_amt, c_amt)
                    score.amount_similarity = max(0, 1 - diff_ratio)
                else:
                    score.amount_similarity = 1.0
            except (ValueError, TypeError):
                score.amount_similarity = 0.5
        else:
            score.amount_similarity = 0.5

        # Time Proximity (aeltere Faelle weniger relevant)
        if source.created_at and candidate.created_at:
            days_diff = abs((source.created_at - candidate.created_at).days)
            score.time_proximity = max(0, 1 - (days_diff / 365))
        else:
            score.time_proximity = 0.5

        # Feature Overlap
        source_features = source.features_used or {}
        candidate_features = candidate.features_used or {}
        score.feature_overlap = self._calculate_feature_similarity(source_features, candidate_features)

        # Gesamt-Score berechnen
        score.overall = (
            score.decision_type_match * self.SIMILARITY_WEIGHTS["decision_type"] +
            score.entity_match * self.SIMILARITY_WEIGHTS["entity"] +
            score.amount_similarity * self.SIMILARITY_WEIGHTS["amount"] +
            score.time_proximity * self.SIMILARITY_WEIGHTS["time"] +
            score.feature_overlap * self.SIMILARITY_WEIGHTS["features"]
        )

        return score

    def _calculate_feature_similarity(
        self,
        features1: Dict[str, Any],
        features2: Dict[str, Any],
    ) -> float:
        """Berechnet Ähnlichkeit zwischen Feature-Sets."""
        if not features1 or not features2:
            return 0.5

        # Gemeinsame Keys
        keys1 = set(features1.keys())
        keys2 = set(features2.keys())

        common_keys = keys1.intersection(keys2)
        all_keys = keys1.union(keys2)

        if not all_keys:
            return 0.5

        # Jaccard-Ähnlichkeit für Keys
        key_similarity = len(common_keys) / len(all_keys)

        # Wert-Ähnlichkeit für gemeinsame Keys
        if common_keys:
            value_matches = 0
            for key in common_keys:
                if features1[key] == features2[key]:
                    value_matches += 1
                elif isinstance(features1[key], (int, float)) and isinstance(features2[key], (int, float)):
                    # Numerische Werte: Relative Ähnlichkeit
                    max_val = max(abs(features1[key]), abs(features2[key]), 1)
                    diff_ratio = abs(features1[key] - features2[key]) / max_val
                    if diff_ratio < 0.2:  # < 20% Unterschied
                        value_matches += 0.8
                    elif diff_ratio < 0.5:
                        value_matches += 0.5

            value_similarity = value_matches / len(common_keys)
        else:
            value_similarity = 0

        # Kombinierte Ähnlichkeit
        return (key_similarity * 0.4) + (value_similarity * 0.6)

    def _determine_outcome(self, decision: AIDecision) -> OutcomeType:
        """Bestimmt das Ergebnis einer Entscheidung."""
        if decision.auto_applied:
            return OutcomeType.AUTO_APPROVED
        elif decision.review_action == "approved":
            return OutcomeType.MANUALLY_APPROVED
        elif decision.review_action == "modified":
            return OutcomeType.MODIFIED
        elif decision.review_action == "rejected":
            return OutcomeType.REJECTED
        else:
            return OutcomeType.AUTO_APPROVED  # Default

    def _similarity_to_level(self, similarity: float) -> SimilarityLevel:
        """Konvertiert Ähnlichkeits-Score zu Level."""
        if similarity >= 0.95:
            return SimilarityLevel.EXACT
        elif similarity >= 0.85:
            return SimilarityLevel.VERY_HIGH
        elif similarity >= 0.70:
            return SimilarityLevel.HIGH
        elif similarity >= 0.50:
            return SimilarityLevel.MODERATE
        else:
            return SimilarityLevel.LOW

    def _count_outcomes(self, cases: List[SimilarCase]) -> Dict[str, int]:
        """Zaehlt Ergebnisse."""
        counts: Dict[str, int] = {}
        for case in cases:
            outcome = case.outcome.value
            counts[outcome] = counts.get(outcome, 0) + 1
        return counts

    def _calculate_average_similarity(self, cases: List[SimilarCase]) -> float:
        """Berechnet durchschnittliche Ähnlichkeit."""
        if not cases:
            return 0.0
        return sum(c.similarity_score for c in cases) / len(cases)

    def _calculate_success_rate(self, cases: List[SimilarCase]) -> float:
        """Berechnet Erfolgsrate (Auto + Approved)."""
        if not cases:
            return 0.0

        successful = sum(
            1 for c in cases
            if c.outcome in [OutcomeType.AUTO_APPROVED, OutcomeType.MANUALLY_APPROVED]
        )
        return successful / len(cases)

    def _predict_outcome(
        self,
        cases: List[SimilarCase],
    ) -> Tuple[str, float]:
        """Sagt Ergebnis basierend auf ähnlichen Faellen vorher."""
        if not cases:
            return "unknown", 0.0

        # Gewichtete Abstimmung (ähnlichere Faelle zaehlen mehr)
        outcome_scores: Dict[str, float] = {}

        for case in cases:
            outcome = case.outcome.value
            weight = case.similarity_score
            outcome_scores[outcome] = outcome_scores.get(outcome, 0) + weight

        if not outcome_scores:
            return "unknown", 0.0

        # Bestes Ergebnis
        best_outcome = max(outcome_scores, key=outcome_scores.get)
        total_weight = sum(outcome_scores.values())

        confidence = outcome_scores[best_outcome] / total_weight if total_weight > 0 else 0

        return best_outcome, confidence

    def _generate_insights(
        self,
        source: AIDecision,
        cases: List[SimilarCase],
        outcome_counts: Dict[str, int],
    ) -> List[str]:
        """Generiert Insights basierend auf dem Vergleich."""
        insights = []

        total_cases = len(cases)
        if total_cases == 0:
            insights.append("Keine ähnlichen Faelle gefunden. Dies ist ein neuartiger Fall.")
            return insights

        # Anzahl ähnlicher Faelle
        insights.append(f"Basierend auf {total_cases} ähnlichen Faellen aus der Vergangenheit.")

        # Erfolgsrate
        success_count = outcome_counts.get("auto_approved", 0) + outcome_counts.get("manually_approved", 0)
        success_rate = success_count / total_cases

        if success_rate >= 0.9:
            insights.append(f"{success_rate*100:.0f}% der ähnlichen Faelle wurden genehmigt.")
        elif success_rate >= 0.7:
            insights.append(f"{success_rate*100:.0f}% Genehmigungsrate bei ähnlichen Faellen.")
        elif success_rate < 0.5:
            rejected = outcome_counts.get("rejected", 0)
            insights.append(f"Achtung: {rejected} von {total_cases} ähnlichen Faellen wurden abgelehnt.")

        # Modifizierungen
        modified = outcome_counts.get("modified", 0)
        if modified > 0:
            insights.append(f"{modified} ähnliche Faelle wurden modifiziert - manuelle Prüfung empfohlen.")

        # Confidence-Vergleich
        avg_confidence = sum(c.confidence for c in cases) / total_cases if cases else 0
        if source.confidence > avg_confidence * 1.1:
            insights.append("Die aktuelle Konfidenz ist überdurchschnittlich hoch.")
        elif source.confidence < avg_confidence * 0.9:
            insights.append("Die aktuelle Konfidenz ist unterdurchschnittlich - zusätzliche Prüfung empfohlen.")

        return insights

    def _create_empty_comparison(self, decision_id: UUID) -> CaseComparison:
        """Erstellt einen leeren Vergleich."""
        return CaseComparison(
            source_decision_id=decision_id,
            insights=["Entscheidung nicht gefunden."],
        )


# =============================================================================
# Singleton
# =============================================================================

_case_comparator: Optional[CaseComparator] = None


def get_case_comparator() -> CaseComparator:
    """Gibt die Singleton-Instanz zurück."""
    global _case_comparator
    if _case_comparator is None:
        _case_comparator = CaseComparator()
    return _case_comparator
