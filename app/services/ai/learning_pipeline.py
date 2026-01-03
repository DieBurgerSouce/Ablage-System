# -*- coding: utf-8 -*-
"""
AILearningPipeline - Self-Learning aus User-Feedback.

Verarbeitet Korrekturen und Ablehnungen um die KI-Modelle
kontinuierlich zu verbessern:
- Verarbeitet Feedback-Queue
- Aktualisiert Modell-Gewichtungen
- Passt Confidence-Thresholds dynamisch an
- Generiert Accuracy-Reports

Feinpoliert und durchdacht - Enterprise Self-Learning.
"""

from __future__ import annotations

import statistics
import threading
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AIConfidenceThreshold,
    AIDecision,
    AILearningFeedback,
)
from app.services.ai.decision_service import (
    DecisionType,
    FeedbackType,
    ReviewAction,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

FEEDBACK_PROCESSED = Counter(
    "ai_feedback_processed_total",
    "Anzahl verarbeiteter Feedback-Eintraege",
    ["decision_type", "feedback_type"]
)

LEARNING_BATCH_SIZE = Histogram(
    "ai_learning_batch_size",
    "Groesse der Learning-Batches",
    buckets=[1, 5, 10, 50, 100, 500]
)

THRESHOLD_ADJUSTMENTS = Counter(
    "ai_threshold_adjustments_total",
    "Anzahl der Threshold-Anpassungen",
    ["decision_type", "direction"]
)

ACCURACY_RATE = Gauge(
    "ai_accuracy_rate",
    "Aktuelle Accuracy-Rate",
    ["decision_type"]
)


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class LearningStats:
    """Statistiken fuer Self-Learning."""
    decision_type: DecisionType
    total_decisions: int = 0
    auto_applied: int = 0
    reviewed: int = 0
    approved: int = 0
    corrected: int = 0
    rejected: int = 0
    accuracy_rate: float = 0.0
    correction_rate: float = 0.0
    rejection_rate: float = 0.0
    avg_confidence: float = 0.0


@dataclass
class ThresholdAdjustment:
    """Vorgeschlagene Threshold-Anpassung."""
    decision_type: DecisionType
    current_auto: float
    current_suggest: float
    suggested_auto: float
    suggested_suggest: float
    reason: str
    confidence: float


@dataclass
class LearningBatchResult:
    """Ergebnis eines Learning-Batches."""
    batch_id: str
    processed_count: int
    decision_types: Dict[str, int]
    threshold_adjustments: List[ThresholdAdjustment]
    processing_time_ms: int


class AILearningPipeline:
    """
    Self-Learning Pipeline fuer KI-Entscheidungen.

    Verarbeitet Feedback und passt Thresholds dynamisch an.
    """

    # Konfiguration
    MIN_SAMPLES_FOR_ADJUSTMENT = 20  # Min Samples bevor Threshold angepasst wird
    ACCURACY_TARGET = 0.90  # Ziel-Accuracy
    MAX_THRESHOLD_CHANGE = 0.05  # Max Aenderung pro Iteration
    FEEDBACK_WEIGHT_DECAY = 0.95  # Aelteres Feedback hat weniger Gewicht

    def __init__(self) -> None:
        """Initialisiert die Pipeline."""
        pass

    async def get_learning_stats(
        self,
        db: AsyncSession,
        decision_type: Optional[DecisionType] = None,
        company_id: Optional[uuid.UUID] = None,
        days: int = 30,
    ) -> List[LearningStats]:
        """
        Berechnet Learning-Statistiken.

        Args:
            db: Database Session
            decision_type: Optional Filter
            company_id: Optional Company-Filter
            days: Zeitraum in Tagen

        Returns:
            Liste von LearningStats pro DecisionType
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Basis-Query
        base_query = select(AIDecision).where(
            and_(
                AIDecision.is_final == True,
                AIDecision.created_at >= cutoff,
            )
        )

        if company_id:
            base_query = base_query.where(AIDecision.company_id == company_id)

        if decision_type:
            base_query = base_query.where(AIDecision.decision_type == decision_type.value)

        result = await db.execute(base_query)
        decisions = result.scalars().all()

        # Gruppiere nach DecisionType
        by_type: Dict[str, List[AIDecision]] = {}
        for d in decisions:
            if d.decision_type not in by_type:
                by_type[d.decision_type] = []
            by_type[d.decision_type].append(d)

        stats: List[LearningStats] = []

        for dt_value, dt_decisions in by_type.items():
            try:
                dt = DecisionType(dt_value)
            except ValueError:
                continue

            total = len(dt_decisions)
            auto = sum(1 for d in dt_decisions if d.auto_applied)
            reviewed = sum(1 for d in dt_decisions if d.reviewed_by_id)
            approved = sum(
                1 for d in dt_decisions
                if d.review_action == ReviewAction.APPROVED.value
            )
            corrected = sum(
                1 for d in dt_decisions
                if d.review_action == ReviewAction.MODIFIED.value
            )
            rejected = sum(
                1 for d in dt_decisions
                if d.review_action == ReviewAction.REJECTED.value
            )

            # Accuracy = (Auto + Approved) / Total
            accuracy = (auto + approved) / total if total > 0 else 0.0

            # Correction Rate = Corrected / Reviewed
            correction_rate = corrected / reviewed if reviewed > 0 else 0.0

            # Rejection Rate = Rejected / Reviewed
            rejection_rate = rejected / reviewed if reviewed > 0 else 0.0

            # Durchschnittliche Confidence
            avg_conf = statistics.mean(
                d.confidence for d in dt_decisions
            ) if dt_decisions else 0.0

            s = LearningStats(
                decision_type=dt,
                total_decisions=total,
                auto_applied=auto,
                reviewed=reviewed,
                approved=approved,
                corrected=corrected,
                rejected=rejected,
                accuracy_rate=round(accuracy, 4),
                correction_rate=round(correction_rate, 4),
                rejection_rate=round(rejection_rate, 4),
                avg_confidence=round(avg_conf, 4),
            )
            stats.append(s)

            # Prometheus Gauge aktualisieren
            ACCURACY_RATE.labels(decision_type=dt.value).set(accuracy)

        return stats

    async def process_feedback_queue(
        self,
        db: AsyncSession,
        batch_size: int = 100,
    ) -> LearningBatchResult:
        """
        Verarbeitet unverarbeitete Feedback-Eintraege.

        Args:
            db: Database Session
            batch_size: Max Anzahl zu verarbeitender Eintraege

        Returns:
            LearningBatchResult
        """
        import time
        start_time = time.perf_counter()

        batch_id = str(uuid.uuid4())[:8]

        # Lade unverarbeitetes Feedback
        query = select(AILearningFeedback).where(
            AILearningFeedback.processed_for_learning == False
        ).order_by(AILearningFeedback.created_at).limit(batch_size)

        result = await db.execute(query)
        feedback_items = result.scalars().all()

        LEARNING_BATCH_SIZE.observe(len(feedback_items))

        if not feedback_items:
            return LearningBatchResult(
                batch_id=batch_id,
                processed_count=0,
                decision_types={},
                threshold_adjustments=[],
                processing_time_ms=0,
            )

        # Gruppiere nach DecisionType
        by_type: Dict[str, List[AILearningFeedback]] = {}
        for fb in feedback_items:
            # Lade zugehoerige Decision
            dec_result = await db.execute(
                select(AIDecision).where(AIDecision.id == fb.ai_decision_id)
            )
            decision = dec_result.scalar_one_or_none()
            if decision:
                if decision.decision_type not in by_type:
                    by_type[decision.decision_type] = []
                by_type[decision.decision_type].append(fb)

        # Markiere als verarbeitet
        for fb in feedback_items:
            fb.processed_for_learning = True
            fb.processed_at = datetime.now(timezone.utc)
            fb.learning_batch_id = batch_id

        await db.commit()

        # Metriken
        for dt_value, items in by_type.items():
            for fb in items:
                FEEDBACK_PROCESSED.labels(
                    decision_type=dt_value,
                    feedback_type=fb.feedback_type,
                ).inc()

        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        return LearningBatchResult(
            batch_id=batch_id,
            processed_count=len(feedback_items),
            decision_types={k: len(v) for k, v in by_type.items()},
            threshold_adjustments=[],
            processing_time_ms=processing_time_ms,
        )

    def _calculate_optimal_threshold(
        self,
        decisions: List[AIDecision],
        current_auto: float,
        current_suggest: float,
    ) -> Tuple[float, float, str]:
        """
        Berechnet optimale Thresholds basierend auf Feedback.

        Returns:
            Tuple (suggested_auto, suggested_suggest, reason)
        """
        if len(decisions) < self.MIN_SAMPLES_FOR_ADJUSTMENT:
            return current_auto, current_suggest, "Nicht genuegend Samples"

        # Analysiere Auto-Applied Decisions
        auto_decisions = [d for d in decisions if d.auto_applied]
        reviewed_decisions = [d for d in decisions if d.reviewed_by_id]

        # Berechne Accuracy fuer Auto-Applied
        auto_correct = sum(
            1 for d in auto_decisions
            if d.review_action is None or d.review_action == ReviewAction.APPROVED.value
        )
        auto_accuracy = auto_correct / len(auto_decisions) if auto_decisions else 1.0

        # Berechne Accuracy fuer Suggested
        suggested = [d for d in reviewed_decisions if d.confidence >= current_suggest and d.confidence < current_auto]
        suggested_correct = sum(
            1 for d in suggested
            if d.review_action == ReviewAction.APPROVED.value
        )
        suggested_accuracy = suggested_correct / len(suggested) if suggested else 0.5

        new_auto = current_auto
        new_suggest = current_suggest
        reason = "Keine Anpassung erforderlich"

        # Wenn Auto-Accuracy zu niedrig -> Threshold erhoehen
        if auto_accuracy < self.ACCURACY_TARGET and auto_decisions:
            # Finde Confidence bei der Accuracy gut ist
            sorted_by_conf = sorted(auto_decisions, key=lambda d: d.confidence, reverse=True)
            for i, d in enumerate(sorted_by_conf):
                subset = sorted_by_conf[:i + 1]
                subset_accuracy = sum(
                    1 for x in subset
                    if x.review_action is None or x.review_action == ReviewAction.APPROVED.value
                ) / len(subset)
                if subset_accuracy >= self.ACCURACY_TARGET:
                    new_auto = min(d.confidence + 0.02, 0.99)
                    break

            new_auto = min(new_auto, current_auto + self.MAX_THRESHOLD_CHANGE)
            reason = f"Auto-Accuracy ({auto_accuracy:.1%}) unter Ziel ({self.ACCURACY_TARGET:.0%})"

        # Wenn Suggested gut funktioniert -> Threshold senken
        elif suggested_accuracy > self.ACCURACY_TARGET and len(suggested) > 10:
            new_suggest = max(current_suggest - 0.02, 0.5)
            reason = f"Suggested-Accuracy ({suggested_accuracy:.1%}) ueber Ziel"

        return new_auto, new_suggest, reason

    async def suggest_threshold_adjustments(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        days: int = 30,
    ) -> List[ThresholdAdjustment]:
        """
        Schlaegt Threshold-Anpassungen vor.

        Args:
            db: Database Session
            company_id: Optional Company-Filter
            days: Zeitraum fuer Analyse

        Returns:
            Liste von ThresholdAdjustment Vorschlaegen
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Lade aktuelle Thresholds
        threshold_query = select(AIConfidenceThreshold)
        if company_id:
            threshold_query = threshold_query.where(
                AIConfidenceThreshold.company_id == company_id
            )
        result = await db.execute(threshold_query)
        thresholds = {t.decision_type: t for t in result.scalars().all()}

        adjustments: List[ThresholdAdjustment] = []

        for dt in DecisionType:
            # Lade Decisions
            query = select(AIDecision).where(
                and_(
                    AIDecision.decision_type == dt.value,
                    AIDecision.is_final == True,
                    AIDecision.created_at >= cutoff,
                )
            )
            if company_id:
                query = query.where(AIDecision.company_id == company_id)

            result = await db.execute(query)
            decisions = result.scalars().all()

            if len(decisions) < self.MIN_SAMPLES_FOR_ADJUSTMENT:
                continue

            # Aktuelle Thresholds
            current = thresholds.get(dt.value)
            current_auto = current.auto_threshold if current else 0.95
            current_suggest = current.suggest_threshold if current else 0.80

            # Berechne optimale Thresholds
            new_auto, new_suggest, reason = self._calculate_optimal_threshold(
                decisions, current_auto, current_suggest
            )

            # Nur hinzufuegen wenn Aenderung vorgeschlagen
            if new_auto != current_auto or new_suggest != current_suggest:
                adjustments.append(
                    ThresholdAdjustment(
                        decision_type=dt,
                        current_auto=current_auto,
                        current_suggest=current_suggest,
                        suggested_auto=round(new_auto, 3),
                        suggested_suggest=round(new_suggest, 3),
                        reason=reason,
                        confidence=0.7,  # Basis-Confidence fuer Vorschlag
                    )
                )

        return adjustments

    async def apply_threshold_adjustment(
        self,
        db: AsyncSession,
        adjustment: ThresholdAdjustment,
        company_id: Optional[uuid.UUID] = None,
        updated_by_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Wendet eine Threshold-Anpassung an.

        Args:
            db: Database Session
            adjustment: Anzuwendende Anpassung
            company_id: Company-ID
            updated_by_id: User-ID des Ausfuehrenden

        Returns:
            True bei Erfolg
        """
        # Suche existierenden Threshold
        query = select(AIConfidenceThreshold).where(
            and_(
                AIConfidenceThreshold.decision_type == adjustment.decision_type.value,
                AIConfidenceThreshold.company_id == company_id,
            )
        )
        result = await db.execute(query)
        threshold = result.scalar_one_or_none()

        if threshold:
            # Update
            threshold.auto_threshold = adjustment.suggested_auto
            threshold.suggest_threshold = adjustment.suggested_suggest
            threshold.updated_by_id = updated_by_id
            threshold.updated_at = datetime.now(timezone.utc)
        else:
            # Insert
            threshold = AIConfidenceThreshold(
                id=uuid.uuid4(),
                company_id=company_id,
                decision_type=adjustment.decision_type.value,
                auto_threshold=adjustment.suggested_auto,
                suggest_threshold=adjustment.suggested_suggest,
                is_enabled=True,
                allow_auto_apply=True,
                updated_by_id=updated_by_id,
            )
            db.add(threshold)

        await db.commit()

        # Metriken
        direction = "up" if adjustment.suggested_auto > adjustment.current_auto else "down"
        THRESHOLD_ADJUSTMENTS.labels(
            decision_type=adjustment.decision_type.value,
            direction=direction,
        ).inc()

        logger.info(
            "threshold_adjusted",
            decision_type=adjustment.decision_type.value,
            old_auto=adjustment.current_auto,
            new_auto=adjustment.suggested_auto,
            old_suggest=adjustment.current_suggest,
            new_suggest=adjustment.suggested_suggest,
            reason=adjustment.reason,
        )

        return True

    async def generate_accuracy_report(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Generiert einen Genauigkeits-Report.

        Args:
            db: Database Session
            company_id: Optional Company-Filter
            days: Zeitraum

        Returns:
            Report als Dictionary
        """
        stats = await self.get_learning_stats(db, company_id=company_id, days=days)
        adjustments = await self.suggest_threshold_adjustments(db, company_id, days)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "company_id": str(company_id) if company_id else None,
            "summary": {
                "total_decision_types": len(stats),
                "overall_accuracy": 0.0,
                "overall_correction_rate": 0.0,
                "pending_adjustments": len(adjustments),
            },
            "by_decision_type": [],
            "suggested_adjustments": [],
        }

        # Gesamt-Statistiken
        total_decisions = sum(s.total_decisions for s in stats)
        total_correct = sum(s.auto_applied + s.approved for s in stats)
        total_corrected = sum(s.corrected for s in stats)
        total_reviewed = sum(s.reviewed for s in stats)

        if total_decisions > 0:
            report["summary"]["overall_accuracy"] = round(
                total_correct / total_decisions, 4
            )
        if total_reviewed > 0:
            report["summary"]["overall_correction_rate"] = round(
                total_corrected / total_reviewed, 4
            )

        # Details pro Typ
        for s in stats:
            report["by_decision_type"].append({
                "decision_type": s.decision_type.value,
                "total_decisions": s.total_decisions,
                "auto_applied": s.auto_applied,
                "reviewed": s.reviewed,
                "approved": s.approved,
                "corrected": s.corrected,
                "rejected": s.rejected,
                "accuracy_rate": s.accuracy_rate,
                "correction_rate": s.correction_rate,
                "avg_confidence": s.avg_confidence,
            })

        # Anpassungs-Vorschlaege
        for a in adjustments:
            report["suggested_adjustments"].append({
                "decision_type": a.decision_type.value,
                "current_auto_threshold": a.current_auto,
                "current_suggest_threshold": a.current_suggest,
                "suggested_auto_threshold": a.suggested_auto,
                "suggested_suggest_threshold": a.suggested_suggest,
                "reason": a.reason,
            })

        return report


# Singleton-Instanz mit Thread-Safety
_ai_learning_pipeline: Optional[AILearningPipeline] = None
_ai_learning_pipeline_lock = threading.Lock()


def get_ai_learning_pipeline() -> AILearningPipeline:
    """Factory fuer AILearningPipeline Singleton mit Thread-Safety (Double-Check Locking)."""
    global _ai_learning_pipeline
    if _ai_learning_pipeline is None:
        with _ai_learning_pipeline_lock:
            # Double-Check Locking: Erneut pruefen nach Lock-Erwerb
            if _ai_learning_pipeline is None:
                _ai_learning_pipeline = AILearningPipeline()
    return _ai_learning_pipeline
