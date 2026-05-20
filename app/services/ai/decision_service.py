# -*- coding: utf-8 -*-
"""
AIDecisionService - Zentraler Autonomie-Controller.

Koordiniert alle KI-Entscheidungen mit Confidence-basierter Autonomie:
- 95%+ Konfidenz: Automatisch verarbeiten (Audit-Log)
- 80-95% Konfidenz: Vorschlag mit 1-Click Bestätigung
- <80% Konfidenz: Manuelle Review Queue

Feinpoliert und durchdacht - Enterprise-Grade AI Governance.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional, Union

# JSON-compatible value type for JSONB columns (decision_value, explanation, features)
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]

# Callback type for auto-applying decisions
ApplyCallback = Callable[[JSONDict], Awaitable[None]]

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (

    AIConfidenceThreshold,
    AIDecision,
    AILearningFeedback,
    Document,
    User,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken - Enterprise AI Monitoring
# =============================================================================

AI_DECISIONS_TOTAL = Counter(
    "ai_decisions_total",
    "Anzahl der KI-Entscheidungen",
    ["decision_type", "confidence_level", "auto_applied"]
)

AI_DECISION_CONFIDENCE = Histogram(
    "ai_decision_confidence",
    "Confidence-Werte der KI-Entscheidungen",
    ["decision_type"],
    buckets=[0.0, 0.3, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0]
)

AI_DECISION_DURATION = Histogram(
    "ai_decision_duration_seconds",
    "Dauer der KI-Entscheidung in Sekunden",
    ["decision_type"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

AI_PENDING_REVIEWS = Gauge(
    "ai_pending_reviews_total",
    "Anzahl der ausstehenden Reviews",
    ["decision_type"]
)

AI_FEEDBACK_TOTAL = Counter(
    "ai_feedback_total",
    "Anzahl der Feedback-Einträge",
    ["decision_type", "feedback_type"]
)


# =============================================================================
# Enums und Dataclasses
# =============================================================================

class DecisionType(str, Enum):
    """Typen von KI-Entscheidungen."""
    CATEGORIZATION = "categorization"
    ACCOUNTING = "accounting"
    MATCHING = "matching"
    ANOMALY = "anomaly"
    PREDICTION = "prediction"
    DUPLICATE = "duplicate"


class ConfidenceLevel(str, Enum):
    """Autonomie-Level basierend auf Konfidenz."""
    AUTO = "auto"      # 95%+: Automatisch anwenden
    SUGGEST = "suggest"  # 80-95%: Vorschlagen
    MANUAL = "manual"    # <80%: Manuelle Prüfung


class ReviewAction(str, Enum):
    """Mögliche Review-Aktionen."""
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class FeedbackType(str, Enum):
    """Typen von Self-Learning Feedback."""
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


@dataclass
class ThresholdConfig:
    """Schwellenwert-Konfiguration für einen Decision-Type."""
    decision_type: DecisionType
    auto_threshold: float  # Ab hier automatisch (default 0.95)
    suggest_threshold: float  # Ab hier vorschlagen (default 0.80)
    is_enabled: bool = True
    allow_auto_apply: bool = True


@dataclass
class AIDecisionResult:
    """Ergebnis einer KI-Entscheidung."""
    decision_id: uuid.UUID
    decision_type: DecisionType
    decision_value: JSONDict
    confidence: float
    calibrated_confidence: Optional[float]
    confidence_level: ConfidenceLevel
    auto_applied: bool
    requires_review: bool
    explanation: Optional[JSONDict] = None
    model_version: Optional[str] = None
    processing_time_ms: int = 0


@dataclass
class PendingReview:
    """Review-Item in der Queue."""
    decision_id: uuid.UUID
    decision_type: DecisionType
    document_id: Optional[uuid.UUID]
    decision_value: JSONDict
    confidence: float
    confidence_level: ConfidenceLevel
    explanation: Optional[JSONDict]
    created_at: datetime


# =============================================================================
# Default Thresholds (werden aus DB überschrieben)
# =============================================================================

DEFAULT_THRESHOLDS: Dict[DecisionType, ThresholdConfig] = {
    DecisionType.CATEGORIZATION: ThresholdConfig(
        decision_type=DecisionType.CATEGORIZATION,
        auto_threshold=0.95,
        suggest_threshold=0.80,
        allow_auto_apply=True,
    ),
    DecisionType.ACCOUNTING: ThresholdConfig(
        decision_type=DecisionType.ACCOUNTING,
        auto_threshold=0.90,
        suggest_threshold=0.75,
        allow_auto_apply=False,  # Buchhaltung braucht Bestätigung
    ),
    DecisionType.MATCHING: ThresholdConfig(
        decision_type=DecisionType.MATCHING,
        auto_threshold=0.95,
        suggest_threshold=0.85,
        allow_auto_apply=True,
    ),
    DecisionType.ANOMALY: ThresholdConfig(
        decision_type=DecisionType.ANOMALY,
        auto_threshold=0.85,
        suggest_threshold=0.70,
        allow_auto_apply=False,  # Anomalien immer reviewen
    ),
    DecisionType.PREDICTION: ThresholdConfig(
        decision_type=DecisionType.PREDICTION,
        auto_threshold=0.80,
        suggest_threshold=0.60,
        allow_auto_apply=False,  # Vorhersagen sind informativ
    ),
    DecisionType.DUPLICATE: ThresholdConfig(
        decision_type=DecisionType.DUPLICATE,
        auto_threshold=0.90,
        suggest_threshold=0.75,
        allow_auto_apply=True,
    ),
}


class AIDecisionService:
    """
    Zentraler Controller für KI-Autonomie.

    Koordiniert Entscheidungen, speichert Audit-Trail und
    verarbeitet Self-Learning Feedback.
    """

    # Cache für Thresholds (1 Minute TTL) - Thread-Safe
    _threshold_cache: Dict[Optional[uuid.UUID], Dict[DecisionType, ThresholdConfig]] = {}
    _threshold_cache_time: Dict[Optional[uuid.UUID], datetime] = {}
    _cache_lock = threading.Lock()  # THREAD-SAFETY FIX: Lock für Cache-Operationen
    _CACHE_TTL_SECONDS = 60
    _MAX_CACHE_SIZE = 1000  # MEMORY LEAK FIX: Max Cache-Einträge
    _last_cleanup: datetime = datetime.min.replace(tzinfo=timezone.utc)
    _CLEANUP_INTERVAL_SECONDS = 300  # Cleanup alle 5 Minuten

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._model_version = "1.0.0"

    @classmethod
    def _cleanup_expired_cache(cls) -> None:
        """MEMORY LEAK FIX: Entfernt abgelaufene Cache-Einträge (Thread-Safe).

        Wird periodisch aufgerufen um Memory Leaks zu verhindern.
        Entfernt Einträge die aelter als TTL sind.
        """
        now = datetime.now(timezone.utc)

        # Quick check ohne Lock (Double-Check Pattern)
        if (now - cls._last_cleanup).total_seconds() < cls._CLEANUP_INTERVAL_SECONDS:
            return

        # THREAD-SAFETY FIX: Lock für Cache-Modifikation
        with cls._cache_lock:
            # Double-Check nach Lock-Erwerb
            if (now - cls._last_cleanup).total_seconds() < cls._CLEANUP_INTERVAL_SECONDS:
                return

            cls._last_cleanup = now

            # Abgelaufene Keys finden
            expired_keys = [
                key for key, cache_time in cls._threshold_cache_time.items()
                if (now - cache_time).total_seconds() >= cls._CACHE_TTL_SECONDS
            ]

            # Abgelaufene Einträge entfernen
            for key in expired_keys:
                cls._threshold_cache.pop(key, None)
                cls._threshold_cache_time.pop(key, None)

            # Falls Cache immer noch zu gross, aelteste Einträge entfernen
            if len(cls._threshold_cache) > cls._MAX_CACHE_SIZE:
                # Sortiere nach Alter und entferne aelteste
                sorted_keys = sorted(
                    cls._threshold_cache_time.keys(),
                    key=lambda k: cls._threshold_cache_time.get(k, datetime.min.replace(tzinfo=timezone.utc))
                )
                keys_to_remove = sorted_keys[:len(cls._threshold_cache) - cls._MAX_CACHE_SIZE]
                for key in keys_to_remove:
                    cls._threshold_cache.pop(key, None)
                    cls._threshold_cache_time.pop(key, None)

            if expired_keys or len(cls._threshold_cache) > cls._MAX_CACHE_SIZE:
                logger.debug(
                    "threshold_cache_cleanup",
                    expired_removed=len(expired_keys),
                    current_size=len(cls._threshold_cache),
                )

    # =========================================================================
    # Threshold Management
    # =========================================================================

    async def get_thresholds(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[DecisionType, ThresholdConfig]:
        """
        Laedt Konfidenz-Schwellenwerte (cached).

        Args:
            db: Database Session
            company_id: Optional Company-ID für mandantenspezifische Thresholds

        Returns:
            Dict mit ThresholdConfig pro DecisionType
        """
        # MEMORY LEAK FIX: Periodisches Cache-Cleanup
        self._cleanup_expired_cache()

        now = datetime.now(timezone.utc)
        cache_key = company_id

        # Check Cache
        if cache_key in self._threshold_cache:
            cache_time = self._threshold_cache_time.get(cache_key, datetime.min.replace(tzinfo=timezone.utc))
            if (now - cache_time).total_seconds() < self._CACHE_TTL_SECONDS:
                return self._threshold_cache[cache_key]

        # Lade aus DB
        query = select(AIConfidenceThreshold).where(
            or_(
                AIConfidenceThreshold.company_id == company_id,
                AIConfidenceThreshold.company_id.is_(None),
            )
        )
        result = await db.execute(query)
        db_thresholds = result.scalars().all()

        # Merge mit Defaults (company-spezifisch überschreibt global)
        thresholds = dict(DEFAULT_THRESHOLDS)
        for t in db_thresholds:
            try:
                dt = DecisionType(t.decision_type)
                # Company-spezifische Thresholds haben Priorität
                if t.company_id == company_id or dt not in thresholds:
                    thresholds[dt] = ThresholdConfig(
                        decision_type=dt,
                        auto_threshold=t.auto_threshold or 0.95,
                        suggest_threshold=t.suggest_threshold or 0.80,
                        is_enabled=t.is_enabled if t.is_enabled is not None else True,
                        allow_auto_apply=t.allow_auto_apply if t.allow_auto_apply is not None else True,
                    )
            except ValueError as e:
                logger.warning(
                    "unknown_decision_type",
                    decision_type=t.decision_type,
                    error_type=type(e).__name__,
                )

        # Update Cache
        self._threshold_cache[cache_key] = thresholds
        self._threshold_cache_time[cache_key] = now

        return thresholds

    def determine_confidence_level(
        self,
        confidence: float,
        threshold_config: ThresholdConfig,
    ) -> ConfidenceLevel:
        """
        Bestimmt das Autonomie-Level basierend auf Konfidenz.

        Args:
            confidence: Konfidenz-Wert (0.0-1.0)
            threshold_config: Schwellenwert-Konfiguration

        Returns:
            ConfidenceLevel (AUTO, SUGGEST, MANUAL)
        """
        if not threshold_config.is_enabled:
            return ConfidenceLevel.MANUAL

        if confidence >= threshold_config.auto_threshold:
            return ConfidenceLevel.AUTO
        elif confidence >= threshold_config.suggest_threshold:
            return ConfidenceLevel.SUGGEST
        else:
            return ConfidenceLevel.MANUAL

    # =========================================================================
    # Decision Making
    # =========================================================================

    async def make_decision(
        self,
        db: AsyncSession,
        decision_type: DecisionType,
        decision_value: JSONDict,
        confidence: float,
        document_id: Optional[uuid.UUID] = None,
        company_id: Optional[uuid.UUID] = None,
        explanation: Optional[JSONDict] = None,
        features_used: Optional[JSONDict] = None,
        calibrated_confidence: Optional[float] = None,
        apply_callback: Optional[ApplyCallback] = None,
    ) -> AIDecisionResult:
        """
        Erstellt eine KI-Entscheidung mit Autonomie-Logik.

        Args:
            db: Database Session
            decision_type: Typ der Entscheidung
            decision_value: Entscheidungs-Inhalt (JSON)
            confidence: Konfidenz-Wert (0.0-1.0)
            document_id: Optional Dokument-ID
            company_id: Optional Company-ID
            explanation: Optional Erklärung (Explainable AI)
            features_used: Optional verwendete Features
            calibrated_confidence: Optional kalibrierte Konfidenz
            apply_callback: Optional Callback zum automatischen Anwenden

        Returns:
            AIDecisionResult mit allen Details
        """
        start_time = time.perf_counter()

        # Lade Thresholds
        thresholds = await self.get_thresholds(db, company_id)
        threshold_config = thresholds.get(decision_type, DEFAULT_THRESHOLDS[decision_type])

        # Bestimme Confidence Level
        effective_confidence = calibrated_confidence if calibrated_confidence is not None else confidence
        confidence_level = self.determine_confidence_level(effective_confidence, threshold_config)

        # Entscheide ob automatisch anwenden
        auto_applied = False
        requires_review = True

        if confidence_level == ConfidenceLevel.AUTO and threshold_config.allow_auto_apply:
            auto_applied = True
            requires_review = False
        elif confidence_level == ConfidenceLevel.SUGGEST:
            requires_review = True
        else:  # MANUAL
            requires_review = True

        # Erstelle Entscheidung
        decision = AIDecision(
            id=uuid.uuid4(),
            company_id=company_id,
            document_id=document_id,
            decision_type=decision_type.value,
            decision_value=decision_value,
            confidence=confidence,
            calibrated_confidence=calibrated_confidence,
            confidence_level=confidence_level.value,
            explanation=explanation,
            features_used=features_used,
            model_version=self._model_version,
            auto_applied=auto_applied,
            requires_review=requires_review,
            is_final=auto_applied,  # Final wenn automatisch angewendet
        )

        db.add(decision)

        # DATA CONSISTENCY FIX: flush() vor Callback ausführen
        # Dies stellt sicher, dass:
        # 1. decision.id generiert ist (für Logging und Referenzen)
        # 2. Callback kann auf konsistenten DB-Zustand zugreifen
        # 3. Bei Callback-Fehler kann die gesamte Transaktion zurückgerollt werden
        await db.flush()

        # Wenn Auto-Apply und Callback vorhanden, ausführen
        if auto_applied and apply_callback is not None:
            try:
                await apply_callback(decision_value)
                logger.info(
                    "ai_decision_auto_applied",
                    decision_id=str(decision.id),
                    decision_type=decision_type.value,
                    confidence=effective_confidence,
                )
            except Exception as e:
                logger.error(
                    "ai_decision_auto_apply_failed",
                    decision_id=str(decision.id),
                    **safe_error_log(e),
                )
                # Bei Fehler: Nicht als applied markieren
                decision.auto_applied = False
                decision.requires_review = True
                decision.is_final = False
                auto_applied = False
                requires_review = True

        await db.commit()
        await db.refresh(decision)

        # Timing
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        decision.processing_time_ms = processing_time_ms
        await db.commit()

        # Metriken
        AI_DECISIONS_TOTAL.labels(
            decision_type=decision_type.value,
            confidence_level=confidence_level.value,
            auto_applied=str(auto_applied).lower(),
        ).inc()

        AI_DECISION_CONFIDENCE.labels(
            decision_type=decision_type.value,
        ).observe(effective_confidence)

        AI_DECISION_DURATION.labels(
            decision_type=decision_type.value,
        ).observe(processing_time_ms / 1000)

        logger.info(
            "ai_decision_created",
            decision_id=str(decision.id),
            decision_type=decision_type.value,
            confidence=confidence,
            calibrated_confidence=calibrated_confidence,
            confidence_level=confidence_level.value,
            auto_applied=auto_applied,
            requires_review=requires_review,
            processing_time_ms=processing_time_ms,
        )

        return AIDecisionResult(
            decision_id=decision.id,
            decision_type=decision_type,
            decision_value=decision_value,
            confidence=confidence,
            calibrated_confidence=calibrated_confidence,
            confidence_level=confidence_level,
            auto_applied=auto_applied,
            requires_review=requires_review,
            explanation=explanation,
            model_version=self._model_version,
            processing_time_ms=processing_time_ms,
        )

    # =========================================================================
    # Review Management
    # =========================================================================

    async def get_pending_reviews(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        decision_type: Optional[DecisionType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[PendingReview]:
        """
        Listet ausstehende Reviews.

        Args:
            db: Database Session
            company_id: Optional Filter nach Company
            decision_type: Optional Filter nach Typ
            limit: Max Anzahl
            offset: Offset für Paginierung

        Returns:
            Liste von PendingReview Items
        """
        query = select(AIDecision).where(
            and_(
                AIDecision.requires_review == True,
                AIDecision.is_final == False,
            )
        )

        if company_id:
            query = query.where(AIDecision.company_id == company_id)
        if decision_type:
            query = query.where(AIDecision.decision_type == decision_type.value)

        query = query.order_by(AIDecision.created_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        decisions = result.scalars().all()

        return [
            PendingReview(
                decision_id=d.id,
                decision_type=DecisionType(d.decision_type),
                document_id=d.document_id,
                decision_value=d.decision_value or {},
                confidence=d.confidence,
                confidence_level=ConfidenceLevel(d.confidence_level),
                explanation=d.explanation,
                created_at=d.created_at,
            )
            for d in decisions
        ]

    async def review_decision(
        self,
        db: AsyncSession,
        decision_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        action: ReviewAction,
        modified_value: Optional[JSONDict] = None,
        comment: Optional[str] = None,
    ) -> bool:
        """
        Reviewed eine KI-Entscheidung.

        Args:
            db: Database Session
            decision_id: ID der Entscheidung
            reviewer_id: ID des Reviewers
            action: Review-Aktion (approved, rejected, modified)
            modified_value: Bei MODIFIED: Korrigierter Wert
            comment: Optional Kommentar

        Returns:
            True bei Erfolg
        """
        # Lade Entscheidung
        result = await db.execute(
            select(AIDecision).where(AIDecision.id == decision_id)
        )
        decision = result.scalar_one_or_none()

        if not decision:
            logger.warning(
                "ai_decision_not_found",
                decision_id=str(decision_id),
            )
            return False

        # Update Decision
        decision.reviewed_by_id = reviewer_id
        decision.reviewed_at = datetime.now(timezone.utc)
        decision.review_action = action.value
        decision.review_comment = comment
        decision.requires_review = False
        decision.is_final = True

        if action == ReviewAction.MODIFIED and modified_value:
            decision.modified_value = modified_value

        # Erstelle Learning Feedback
        feedback_type = FeedbackType.APPROVED
        if action == ReviewAction.REJECTED:
            feedback_type = FeedbackType.REJECTED
        elif action == ReviewAction.MODIFIED:
            feedback_type = FeedbackType.CORRECTED

        feedback = AILearningFeedback(
            id=uuid.uuid4(),
            ai_decision_id=decision_id,
            company_id=decision.company_id,
            feedback_type=feedback_type.value,
            original_value=decision.decision_value,
            corrected_value=modified_value if action == ReviewAction.MODIFIED else None,
            correction_reason=comment,
            corrector_id=reviewer_id,
            processed_for_learning=False,
        )

        db.add(feedback)
        await db.commit()

        # Metriken
        AI_FEEDBACK_TOTAL.labels(
            decision_type=decision.decision_type,
            feedback_type=feedback_type.value,
        ).inc()

        logger.info(
            "ai_decision_reviewed",
            decision_id=str(decision_id),
            reviewer_id=str(reviewer_id),
            action=action.value,
            feedback_type=feedback_type.value,
        )

        return True

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_accuracy_stats(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
        decision_type: Optional[DecisionType] = None,
        days: int = 30,
    ) -> JSONDict:
        """
        Berechnet Genauigkeits-Statistiken.

        Args:
            db: Database Session
            company_id: Optional Filter nach Company
            decision_type: Optional Filter nach Typ
            days: Zeitraum in Tagen

        Returns:
            Dict mit Statistiken
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Basis-Query: Abgeschlossene Entscheidungen
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

        total = len(decisions)
        auto_applied = sum(1 for d in decisions if d.auto_applied)
        reviewed = sum(1 for d in decisions if d.reviewed_by_id is not None)
        approved = sum(1 for d in decisions if d.review_action == ReviewAction.APPROVED.value)
        rejected = sum(1 for d in decisions if d.review_action == ReviewAction.REJECTED.value)
        modified = sum(1 for d in decisions if d.review_action == ReviewAction.MODIFIED.value)

        # Accuracy = (Auto-Applied + Approved) / Total
        accuracy = ((auto_applied + approved) / total * 100) if total > 0 else 0.0

        # Durchschnittliche Confidence
        avg_confidence = sum(d.confidence for d in decisions) / total if total > 0 else 0.0

        return {
            "period_days": days,
            "total_decisions": total,
            "auto_applied": auto_applied,
            "reviewed": reviewed,
            "approved": approved,
            "rejected": rejected,
            "modified": modified,
            "accuracy_percent": round(accuracy, 2),
            "avg_confidence": round(avg_confidence, 4),
            "auto_apply_rate": round(auto_applied / total * 100, 2) if total > 0 else 0.0,
        }

    async def get_pending_review_count(
        self,
        db: AsyncSession,
        company_id: Optional[uuid.UUID] = None,
    ) -> Dict[DecisionType, int]:
        """
        Zaehlt ausstehende Reviews pro Typ.

        Args:
            db: Database Session
            company_id: Optional Filter nach Company

        Returns:
            Dict mit Counts pro DecisionType
        """
        from sqlalchemy import func

        query = (
            select(AIDecision.decision_type, func.count(AIDecision.id))
            .where(
                and_(
                    AIDecision.requires_review == True,
                    AIDecision.is_final == False,
                )
            )
            .group_by(AIDecision.decision_type)
        )

        if company_id:
            query = query.where(AIDecision.company_id == company_id)

        result = await db.execute(query)
        rows = result.all()

        counts: Dict[DecisionType, int] = {}
        for row in rows:
            try:
                dt = DecisionType(row[0])
                counts[dt] = row[1]
                # Update Prometheus Gauge
                AI_PENDING_REVIEWS.labels(decision_type=dt.value).set(row[1])
            except ValueError as e:
                logger.debug("skip_invalid_decision_type", error_type=type(e).__name__, decision_type_value=row[0])

        return counts


# Singleton-Instanz mit Thread-Safety
_ai_decision_service: Optional[AIDecisionService] = None
_service_lock = threading.Lock()


def get_ai_decision_service() -> AIDecisionService:
    """Factory für AIDecisionService Singleton (Thread-safe)."""
    global _ai_decision_service
    if _ai_decision_service is None:
        with _service_lock:
            # Double-check locking pattern
            if _ai_decision_service is None:
                _ai_decision_service = AIDecisionService()
    return _ai_decision_service
