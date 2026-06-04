# -*- coding: utf-8 -*-
"""
Feedback Learning Service für Ablage-System OCR.

Implementiert Self-Learning durch Korrektur-Feedback:
- Analyse von Benutzer-Korrekturen
- Fehler-Pattern-Erkennung pro Backend
- Dynamische Backend-Gewichtung basierend auf Korrektur-Historie
- Automatische Integration in OCR-Router-Entscheidungen

Feinpoliert und durchdacht - Enterprise-grade Self-Learning OCR.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import copy
import json
import threading
import asyncio

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRValidationCorrection,
    OCRBackendStatsDaily,
    CorrectionType,
)
from app.core.config import settings
from app.ml.metrics import get_ml_metrics
from app.core.safe_errors import safe_error_log
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)

# Distributed Lock Konfiguration
FEEDBACK_PROCESSING_LOCK_KEY = "lock:feedback_learning:processing"
FEEDBACK_LOCK_TTL_SECONDS = 300  # 5 Minuten


# =============================================================================
# Learned Patterns
# =============================================================================

@dataclass
class BackendErrorPattern:
    """Fehler-Pattern für ein Backend."""
    backend_name: str
    total_corrections: int = 0
    correction_types: Dict[str, int] = field(default_factory=dict)
    field_errors: Dict[str, int] = field(default_factory=dict)
    umlaut_errors: int = 0
    number_errors: int = 0
    date_errors: int = 0
    currency_errors: int = 0
    confidence_when_wrong: List[float] = field(default_factory=list)

    @property
    def error_rate_score(self) -> float:
        """Berechnet gewichteten Error-Rate-Score (0-1, niedriger ist besser)."""
        if self.total_corrections == 0:
            return 0.0

        # Gewichtung nach Schwere
        # NOTE: CorrectionType hat nur: UMLAUT, DATE, AMOUNT, NAME, IBAN, VAT_ID, GENERAL
        weights = {
            CorrectionType.UMLAUT.value: 2.0,      # Umlaute sind kritisch
            CorrectionType.AMOUNT.value: 2.0,      # Geldbetraege/Zahlen kritisch
            CorrectionType.IBAN.value: 2.0,        # Bankdaten kritisch
            CorrectionType.VAT_ID.value: 1.8,      # USt-IdNr wichtig
            CorrectionType.DATE.value: 1.5,        # Daten wichtig
            CorrectionType.NAME.value: 1.0,        # Namen/Felder
            CorrectionType.GENERAL.value: 0.5,     # Allgemeine Korrekturen
        }

        weighted_sum = sum(
            count * weights.get(corr_type, 1.0)
            for corr_type, count in self.correction_types.items()
        )

        # Normalisiere auf 0-1 basierend auf gewichtetem Durchschnitt
        max_weight = max(weights.values())
        normalized = weighted_sum / (self.total_corrections * max_weight)
        return min(1.0, normalized)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "backend_name": self.backend_name,
            "total_corrections": self.total_corrections,
            "correction_types": self.correction_types,
            "field_errors": self.field_errors,
            "umlaut_errors": self.umlaut_errors,
            "number_errors": self.number_errors,
            "date_errors": self.date_errors,
            "currency_errors": self.currency_errors,
            "error_rate_score": round(self.error_rate_score, 4),
            "avg_confidence_when_wrong": (
                sum(self.confidence_when_wrong) / len(self.confidence_when_wrong)
                if self.confidence_when_wrong else None
            ),
        }


@dataclass
class LearnedBackendWeights:
    """Gelernte Gewichtungen für Backend-Auswahl."""
    weights: Dict[str, float]
    last_updated: datetime
    samples_analyzed: int
    confidence: float  # Wie vertrauenswürdig sind die Gewichtungen

    def get_weight(self, backend: str) -> float:
        """Holt Gewichtung für Backend (Default: 1.0)."""
        return self.weights.get(backend, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
            "last_updated": self.last_updated.isoformat(),
            "samples_analyzed": self.samples_analyzed,
            "confidence": round(self.confidence, 4),
        }


class FeedbackLearningService:
    """
    Service für Self-Learning basierend auf Korrektur-Feedback.

    Analysiert Benutzer-Korrekturen und leitet daraus optimale
    Backend-Gewichtungen ab.
    """

    # Mindest-Anzahl Korrekturen für zuverlässige Gewichtungen
    MIN_CORRECTIONS_FOR_CONFIDENCE = 50

    # Standard-Gewichtungen (vor Learning)
    DEFAULT_WEIGHTS = {
        "deepseek-janus-pro": 1.0,
        "got-ocr-2.0": 0.95,
        "surya-gpu": 0.90,
        "surya": 0.85,
    }

    # Feld-spezifische Backend-Präferenzen (können durch Learning überschrieben werden)
    FIELD_PREFERENCES = {
        "invoice_number": ["deepseek-janus-pro", "got-ocr-2.0"],
        "date": ["deepseek-janus-pro", "got-ocr-2.0"],
        "amount": ["deepseek-janus-pro", "got-ocr-2.0"],
        "iban": ["deepseek-janus-pro"],
        "address": ["deepseek-janus-pro", "surya-gpu"],
    }

    def __init__(self):
        """Initialisiere Feedback Learning Service."""
        self._cached_weights: Optional[LearnedBackendWeights] = None
        self._cache_ttl = timedelta(minutes=15)
        self._last_cache_update: Optional[datetime] = None
        self._cache_lock = threading.Lock()  # Thread-safe Cache-Zugriff
        self._redis = None

        logger.info("feedback_learning_service_initialized")

    async def _get_redis(self):
        """Lazy-load Redis connection für Distributed Locking."""
        if self._redis is None:
            from app.core.redis_state import RedisStateManager
            self._redis = RedisStateManager.get_instance()
            await self._redis.connect()
        return self._redis

    async def _acquire_distributed_lock(self, lock_key: str, ttl_seconds: int = 300) -> bool:
        """Versucht Distributed Lock zu erwerben.

        Args:
            lock_key: Redis Key für Lock
            ttl_seconds: Lock Timeout in Sekunden

        Returns:
            True wenn Lock erworben, False sonst
        """
        try:
            redis = await self._get_redis()
            # NX = nur setzen wenn nicht existiert (atomic)
            acquired = await redis._redis.set(
                lock_key,
                "locked",
                ex=ttl_seconds,
                nx=True
            )
            return bool(acquired)
        except Exception as e:
            logger.warning("distributed_lock_acquire_failed", lock_key=lock_key, **safe_error_log(e))
            return False

    async def _release_distributed_lock(self, lock_key: str) -> None:
        """Gibt Distributed Lock frei."""
        try:
            redis = await self._get_redis()
            await redis._redis.delete(lock_key)
        except Exception as e:
            logger.warning("distributed_lock_release_failed", lock_key=lock_key, **safe_error_log(e))

    # =========================================================================
    # CORRECTION ANALYSIS
    # =========================================================================

    async def analyze_corrections(
        self,
        db: AsyncSession,
        days: int = 30
    ) -> Dict[str, BackendErrorPattern]:
        """
        Analysiert Korrekturen der letzten N Tage pro Backend.

        Args:
            db: Datenbank-Session
            days: Anzahl Tage für Analyse

        Returns:
            Dict mit BackendErrorPattern pro Backend
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(OCRValidationCorrection)
            .where(OCRValidationCorrection.created_at >= since)
            .order_by(desc(OCRValidationCorrection.created_at))
        )
        corrections = list(result.scalars().all())

        # Gruppiere nach Backend
        patterns: Dict[str, BackendErrorPattern] = {}
        for correction in corrections:
            backend = correction.backend_used
            if backend not in patterns:
                patterns[backend] = BackendErrorPattern(backend_name=backend)

            pattern = patterns[backend]
            pattern.total_corrections += 1

            # Zähle Korrekturtypen
            corr_type = correction.correction_type or CorrectionType.GENERAL.value
            pattern.correction_types[corr_type] = (
                pattern.correction_types.get(corr_type, 0) + 1
            )

            # Feld-spezifische Fehler
            if correction.field_corrected:
                pattern.field_errors[correction.field_corrected] = (
                    pattern.field_errors.get(correction.field_corrected, 0) + 1
                )

            # Spezifische Fehlertypen
            # NOTE: CorrectionType hat nur: UMLAUT, DATE, AMOUNT, NAME, IBAN, VAT_ID, GENERAL
            # number_errors und currency_errors werden beide durch AMOUNT abgedeckt
            if corr_type == CorrectionType.UMLAUT.value:
                pattern.umlaut_errors += 1
            elif corr_type == CorrectionType.DATE.value:
                pattern.date_errors += 1
            elif corr_type == CorrectionType.AMOUNT.value:
                # AMOUNT deckt sowohl Zahlen als auch Währungen ab
                pattern.number_errors += 1
                pattern.currency_errors += 1

            # Confidence wenn falsch
            if correction.confidence_before is not None:
                pattern.confidence_when_wrong.append(correction.confidence_before)

        logger.info(
            "corrections_analyzed",
            backends=list(patterns.keys()),
            total_corrections=len(corrections),
            days=days
        )

        return patterns

    async def get_learned_weights(
        self,
        db: AsyncSession,
        force_refresh: bool = False
    ) -> LearnedBackendWeights:
        """
        Berechnet optimale Backend-Gewichtungen basierend auf Korrektur-Historie.

        Thread-safe mit Lock für Cache-Zugriff.

        Args:
            db: Datenbank-Session
            force_refresh: Cache umgehen

        Returns:
            LearnedBackendWeights mit optimierten Gewichtungen
        """
        now = datetime.now(timezone.utc)

        # Thread-safe Cache prüfen
        with self._cache_lock:
            if (
                not force_refresh
                and self._cached_weights
                and self._last_cache_update
                and (now - self._last_cache_update) < self._cache_ttl
            ):
                # WICHTIG: Kopie zurückgeben, nicht Referenz!
                # Verhindert dass externe Änderungen den Cache korrumpieren
                return copy.deepcopy(self._cached_weights)

        # Analysiere Korrekturen (ausserhalb Lock - kann lange dauern)
        patterns = await self.analyze_corrections(db, days=30)

        # Berechne Gewichtungen
        weights = dict(self.DEFAULT_WEIGHTS)
        total_corrections = sum(p.total_corrections for p in patterns.values())

        for backend, pattern in patterns.items():
            if backend not in weights:
                weights[backend] = 1.0

            if pattern.total_corrections > 0:
                # Reduziere Gewichtung basierend auf Error-Rate
                error_penalty = pattern.error_rate_score * 0.3
                weights[backend] = max(0.5, weights[backend] - error_penalty)

        # Normalisiere auf 0.5-1.0 Range
        if weights:
            max_weight = max(weights.values())
            min_weight = min(weights.values())
            if max_weight > min_weight:
                for backend in weights:
                    # Skaliere auf 0.5-1.0
                    normalized = (weights[backend] - min_weight) / (max_weight - min_weight)
                    weights[backend] = 0.5 + (normalized * 0.5)

        # Confidence basierend auf Datenmenge
        confidence = min(1.0, total_corrections / self.MIN_CORRECTIONS_FOR_CONFIDENCE)

        learned = LearnedBackendWeights(
            weights=weights,
            last_updated=now,
            samples_analyzed=total_corrections,
            confidence=confidence,
        )

        # Thread-safe Cache aktualisieren
        with self._cache_lock:
            self._cached_weights = learned
            self._last_cache_update = now

        logger.info(
            "learned_weights_calculated",
            weights=weights,
            samples=total_corrections,
            confidence=confidence
        )

        return learned

    async def get_backend_recommendation(
        self,
        db: AsyncSession,
        document_type: Optional[str] = None,
        has_umlauts: bool = False,
        has_tables: bool = False,
        fields_needed: Optional[List[str]] = None
    ) -> Tuple[str, float]:
        """
        Empfiehlt bestes Backend basierend auf gelernten Patterns.

        Args:
            db: Datenbank-Session
            document_type: Dokumenttyp
            has_umlauts: Enthält Umlaute
            has_tables: Enthält Tabellen
            fields_needed: Benötigte Felder

        Returns:
            Tuple von (backend_name, confidence)
        """
        learned = await self.get_learned_weights(db)
        patterns = await self.analyze_corrections(db, days=30)

        # Starte mit gelernten Gewichtungen
        scores = dict(learned.weights)

        # Adjustiere basierend auf Dokumenteigenschaften
        if has_umlauts:
            # Backends mit weniger Umlaut-Fehlern bevorzugen
            for backend, pattern in patterns.items():
                if backend in scores and pattern.total_corrections > 0:
                    umlaut_error_rate = pattern.umlaut_errors / pattern.total_corrections
                    scores[backend] *= (1.0 - umlaut_error_rate * 0.5)

        if has_tables:
            # DeepSeek und GOT-OCR für Tabellen
            for backend in ["deepseek-janus-pro", "got-ocr-2.0"]:
                if backend in scores:
                    scores[backend] *= 1.1

        if fields_needed:
            # Feld-spezifische Präferenzen
            for field in fields_needed:
                preferred = self.FIELD_PREFERENCES.get(field, [])
                for backend in preferred:
                    if backend in scores:
                        scores[backend] *= 1.05

        # Normalisiere und finde bestes Backend
        if scores:
            best_backend = max(scores, key=scores.get)
            confidence = scores[best_backend] / max(scores.values())
            return best_backend, confidence

        return "deepseek-janus-pro", 0.5

    # =========================================================================
    # FEEDBACK PROCESSING (Self-Learning Loop)
    # =========================================================================

    async def process_unprocessed_corrections(
        self,
        db: AsyncSession,
        batch_size: int = 100
    ) -> int:
        """
        Verarbeitet noch nicht verarbeitete Korrekturen für Self-Learning.

        Diese Methode wird periodisch von einem Celery Task aufgerufen.
        Verwendet Distributed Locking um Race Conditions zu vermeiden.

        Args:
            db: Datenbank-Session
            batch_size: Anzahl zu verarbeitender Korrekturen

        Returns:
            Anzahl verarbeiteter Korrekturen
        """
        # Distributed Lock erwerben - verhindert parallele Verarbeitung
        lock_acquired = await self._acquire_distributed_lock(
            FEEDBACK_PROCESSING_LOCK_KEY,
            ttl_seconds=FEEDBACK_LOCK_TTL_SECONDS
        )

        if not lock_acquired:
            logger.info("feedback_processing_skipped_lock_held")
            return 0

        try:
            # Hole unverarbeitete Korrekturen
            result = await db.execute(
                select(OCRValidationCorrection)
                .where(
                    and_(
                        OCRValidationCorrection.applies_to_training == True,
                        OCRValidationCorrection.learning_processed == False
                    )
                )
                .order_by(OCRValidationCorrection.created_at)
                .limit(batch_size)
            )
            corrections = list(result.scalars().all())

            if not corrections:
                return 0

            now = datetime.now(timezone.utc)
            processed = 0

            # Gruppiere Korrekturen nach Backend
            surya_corrections = [
                c for c in corrections
                if c.backend_used in ("surya", "surya-gpu")
            ]
            other_corrections = [
                c for c in corrections
                if c.backend_used not in ("surya", "surya-gpu")
            ]

            # Verarbeite Surya-Korrekturen mit spezifischer Logik
            if surya_corrections:
                try:
                    # Konvertiere hochwertige Korrekturen zu Training Samples
                    high_quality_surya = [
                        c for c in surya_corrections
                        if c.confidence_before is not None
                        and c.confidence_before >= 0.5  # Mittlere+ Confidence
                        and c.corrected_text  # Hat korrigierten Text
                        and len(c.corrected_text) >= 10  # Genug Kontext
                    ]

                    if high_quality_surya:
                        conversion_stats = await self.convert_corrections_to_training_samples(
                            db=db,
                            corrections=high_quality_surya,
                            verify_quality=True,
                        )
                        logger.info(
                            "surya_corrections_converted",
                            samples_created=conversion_stats.get("samples_created", 0),
                            samples_updated=conversion_stats.get("samples_updated", 0),
                        )

                except Exception as e:
                    logger.warning(
                        "surya_training_sample_conversion_failed",
                        **safe_error_log(e),
                    )

            # Markiere alle Korrekturen als verarbeitet
            for correction in corrections:
                try:
                    # Aktualisiere Error-Pattern-Statistiken intern
                    # (wird für Weights-Berechnung verwendet)

                    # Markiere als verarbeitet
                    correction.learning_processed = True
                    correction.learning_processed_at = now

                    # Flush nach jedem Sample - ermöglicht Rollback bei Fehler
                    await db.flush()
                    processed += 1

                    # Prometheus-Metrik für verarbeitete Korrekturen
                    try:
                        metrics = get_ml_metrics()
                        # Korrekturtyp bestimmen basierend auf backend und Inhalt
                        correction_type = "general"
                        if correction.backend_used in ("surya", "surya-gpu"):
                            # Prüfe ob Umlaut-Korrektur
                            if correction.corrected_text and any(
                                umlaut in correction.corrected_text.lower()
                                for umlaut in ["ä", "ö", "ü", "ß"]
                            ):
                                correction_type = "umlaut"
                        metrics.record_surya_correction_processed(correction_type)
                    except Exception:
                        pass  # Metriken sind nicht kritisch

                except Exception as e:
                    logger.error(
                        "correction_processing_failed",
                        correction_id=str(correction.id)[:8],
                        **safe_error_log(e)
                    )
                    # Rollback nur für dieses Sample, nicht den ganzen Batch
                    await db.rollback()

            await db.commit()

            # Prüfe ob Retraining empfohlen wird (nach Batch-Verarbeitung)
            if surya_corrections and len(surya_corrections) >= 10:
                try:
                    # Prometheus-Metrik: Retraining-Check durchgeführt
                    metrics = get_ml_metrics()
                    metrics.record_surya_retraining_check()

                    recommendation = await self.get_surya_retraining_recommendation(db=db)
                    if recommendation.get("should_retrain"):
                        logger.warning(
                            "surya_retraining_recommended",
                            urgency=recommendation.get("urgency"),
                            reasons=recommendation.get("reasons"),
                        )
                        # Prometheus-Metrik: Retraining empfohlen
                        urgency = recommendation.get("urgency", "unknown")
                        metrics.record_surya_retraining_triggered(
                            reason=f"auto_{urgency}"
                        )
                except Exception as e:
                    logger.debug(
                        "retraining_check_failed",
                        **safe_error_log(e),
                    )

            # Thread-safe Cache invalidieren
            with self._cache_lock:
                self._cached_weights = None
                self._last_cache_update = None

            logger.info(
                "corrections_processed",
                processed=processed,
                total=len(corrections)
            )

            return processed

        finally:
            # Lock immer freigeben
            await self._release_distributed_lock(FEEDBACK_PROCESSING_LOCK_KEY)

    # =========================================================================
    # DAILY STATS AGGREGATION
    # =========================================================================

    async def aggregate_daily_stats(
        self,
        db: AsyncSession,
        date: Optional[datetime] = None
    ) -> List[OCRBackendStatsDaily]:
        """
        Aggregiert tägliche Statistiken pro Backend.

        Args:
            db: Datenbank-Session
            date: Datum für Aggregation (Default: gestern)

        Returns:
            Liste der erstellten/aktualisierten Stats
        """
        if date is None:
            date = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=1)

        end_date = date + timedelta(days=1)

        # Hole Korrekturen des Tages
        corrections_result = await db.execute(
            select(OCRValidationCorrection)
            .where(
                and_(
                    OCRValidationCorrection.created_at >= date,
                    OCRValidationCorrection.created_at < end_date
                )
            )
        )
        corrections = list(corrections_result.scalars().all())

        # Gruppiere nach Backend
        backend_corrections: Dict[str, List[OCRValidationCorrection]] = defaultdict(list)
        for corr in corrections:
            backend_corrections[corr.backend_used].append(corr)

        stats_created: List[OCRBackendStatsDaily] = []

        for backend, corrs in backend_corrections.items():
            # Aggregiere Korrekturtypen
            correction_types = defaultdict(int)
            for corr in corrs:
                corr_type = corr.correction_type or CorrectionType.GENERAL.value
                correction_types[corr_type] += 1

            # Prüfe ob Stats für diesen Tag/Backend existieren
            existing_result = await db.execute(
                select(OCRBackendStatsDaily)
                .where(
                    and_(
                        OCRBackendStatsDaily.backend_name == backend,
                        OCRBackendStatsDaily.report_date == date
                    )
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # Update existierende Stats
                existing.corrections_count = len(corrs)
                existing.correction_types = dict(correction_types)
                stats_created.append(existing)
            else:
                # Neue Stats erstellen
                stats = OCRBackendStatsDaily(
                    backend_name=backend,
                    report_date=date,
                    corrections_count=len(corrs),
                    correction_types=dict(correction_types),
                )
                db.add(stats)
                stats_created.append(stats)

        await db.commit()

        logger.info(
            "daily_stats_aggregated",
            date=date.isoformat(),
            backends=len(stats_created)
        )

        return stats_created

    async def get_trend_data(
        self,
        db: AsyncSession,
        backend: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Holt Trend-Daten für Dashboard-Visualisierung.

        Args:
            db: Datenbank-Session
            backend: Optional - Filter nach Backend
            days: Anzahl Tage

        Returns:
            Liste von Datenpunkten pro Tag
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        query = (
            select(OCRBackendStatsDaily)
            .where(OCRBackendStatsDaily.report_date >= since)
            .order_by(OCRBackendStatsDaily.report_date)
        )

        if backend:
            query = query.where(OCRBackendStatsDaily.backend_name == backend)

        result = await db.execute(query)
        stats = list(result.scalars().all())

        # Formatiere für Frontend
        trend_data = []
        for stat in stats:
            trend_data.append({
                "date": stat.report_date.isoformat() if stat.report_date else None,
                "backend": stat.backend_name,
                "samples_processed": stat.samples_processed or 0,
                "avg_cer": stat.avg_cer,
                "avg_wer": stat.avg_wer,
                "avg_umlaut_accuracy": stat.avg_umlaut_accuracy,
                "corrections_count": stat.corrections_count or 0,
            })

        return trend_data


    # =========================================================================
    # SURYA-SPECIFIC FEEDBACK PROCESSING (Continuous Improvement Loop)
    # =========================================================================

    async def get_surya_corrections(
        self,
        db: AsyncSession,
        days: int = 7,
        min_confidence: float = 0.0,
        unprocessed_only: bool = True,
    ) -> List[OCRValidationCorrection]:
        """
        Holt Surya-spezifische Korrekturen für Training.

        Filtert nach Surya und Surya-GPU Backends.

        Args:
            db: Datenbank-Session
            days: Anzahl Tage zurück
            min_confidence: Minimale Confidence vor Korrektur
            unprocessed_only: Nur unverarbeitete Korrekturen

        Returns:
            Liste der Surya-Korrektionen
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        conditions = [
            OCRValidationCorrection.backend_used.in_(["surya", "surya-gpu"]),
            OCRValidationCorrection.created_at >= since,
        ]

        if min_confidence > 0:
            conditions.append(
                OCRValidationCorrection.confidence_before >= min_confidence
            )

        if unprocessed_only:
            conditions.append(
                OCRValidationCorrection.processed_for_learning == False
            )

        result = await db.execute(
            select(OCRValidationCorrection)
            .where(and_(*conditions))
            .order_by(desc(OCRValidationCorrection.created_at))
        )
        corrections = list(result.scalars().all())

        logger.info(
            "surya_corrections_fetched",
            count=len(corrections),
            days=days,
            unprocessed_only=unprocessed_only,
        )

        return corrections

    async def analyze_surya_umlaut_errors(
        self,
        db: AsyncSession,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Detaillierte Analyse von Surya Umlaut-Fehlern.

        Kategorisiert Fehler nach Umlaut-Typ und identifiziert
        häufige Verwechslungen.

        Args:
            db: Datenbank-Session
            days: Anzahl Tage für Analyse

        Returns:
            Umlaut-Fehler-Analyse mit Statistiken
        """
        corrections = await self.get_surya_corrections(
            db, days=days, unprocessed_only=False
        )

        # Initialisiere Statistiken
        umlaut_chars = list("aouAOUß")
        umlaut_stats = {
            "total_corrections": len(corrections),
            "umlaut_corrections": 0,
            "per_umlaut": {
                "ä": {"count": 0, "confusions": {}},
                "ö": {"count": 0, "confusions": {}},
                "ü": {"count": 0, "confusions": {}},
                "Ä": {"count": 0, "confusions": {}},
                "Ö": {"count": 0, "confusions": {}},
                "Ü": {"count": 0, "confusions": {}},
                "ß": {"count": 0, "confusions": {}},
            },
            "common_patterns": [],
        }

        # Analysiere Korrektionen
        confusion_patterns: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for correction in corrections:
            if correction.correction_type == CorrectionType.UMLAUT.value:
                umlaut_stats["umlaut_corrections"] += 1

                # Extrahiere Original und Korrektur
                original = correction.original_text or ""
                corrected = correction.corrected_text or ""

                # Finde Umlaut-Verwechslungen
                for i, (orig_char, corr_char) in enumerate(zip(original, corrected)):
                    if corr_char in umlaut_stats["per_umlaut"]:
                        if orig_char != corr_char:
                            umlaut_stats["per_umlaut"][corr_char]["count"] += 1
                            confusion_patterns[corr_char][orig_char] += 1

        # Aggregiere Top-Verwechslungen
        for umlaut, confusions in confusion_patterns.items():
            top_confusions = sorted(
                confusions.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            umlaut_stats["per_umlaut"][umlaut]["confusions"] = dict(top_confusions)

        # Identifiziere häufigste Muster
        all_patterns = []
        for umlaut, confusions in confusion_patterns.items():
            for wrong_char, count in confusions.items():
                all_patterns.append({
                    "correct": umlaut,
                    "wrong": wrong_char,
                    "count": count,
                })

        umlaut_stats["common_patterns"] = sorted(
            all_patterns,
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        logger.info(
            "surya_umlaut_analysis_completed",
            total_corrections=umlaut_stats["total_corrections"],
            umlaut_corrections=umlaut_stats["umlaut_corrections"],
        )

        return umlaut_stats

    async def convert_corrections_to_training_samples(
        self,
        db: AsyncSession,
        corrections: List[OCRValidationCorrection],
        verify_quality: bool = True,
    ) -> Dict[str, Any]:
        """
        Konvertiert Surya-Korrektionen zu Training Samples.

        Erstellt oder aktualisiert OCRTrainingSample Einträge
        mit korrigiertem Text als Ground Truth.

        Args:
            db: Datenbank-Session
            corrections: Liste der zu konvertierenden Korrektionen
            verify_quality: Qualitätsprüfung aktivieren

        Returns:
            Konvertierungs-Statistiken
        """
        from app.db.models import OCRTrainingSample


        stats = {
            "corrections_processed": 0,
            "samples_created": 0,
            "samples_updated": 0,
            "skipped_low_quality": 0,
            "errors": [],
        }

        now = datetime.now(timezone.utc)

        for correction in corrections:
            try:
                # Qualitätsprüfung
                if verify_quality:
                    if not correction.corrected_text:
                        stats["skipped_low_quality"] += 1
                        continue
                    if len(correction.corrected_text) < 5:
                        stats["skipped_low_quality"] += 1
                        continue

                # Prüfe ob Sample mit diesem Dokument existiert
                if correction.document_id:
                    existing_result = await db.execute(
                        select(OCRTrainingSample).where(
                            OCRTrainingSample.document_id == correction.document_id
                        )
                    )
                    existing_sample = existing_result.scalar_one_or_none()

                    if existing_sample:
                        # Update existierendes Sample
                        if correction.field_corrected:
                            # Update spezifisches Feld
                            extracted = existing_sample.extracted_fields or {}
                            extracted[correction.field_corrected] = correction.corrected_text
                            existing_sample.extracted_fields = extracted
                        else:
                            # Update Ground Truth Text
                            existing_sample.ground_truth_text = correction.corrected_text

                        existing_sample.updated_at = now
                        existing_sample.status = "annotated"
                        stats["samples_updated"] += 1
                    else:
                        # Erstelle neues Sample
                        new_sample = OCRTrainingSample(
                            document_id=correction.document_id,
                            ground_truth_text=correction.corrected_text,
                            status="pending_verification",
                            source="user_correction",
                            language="de",
                            has_umlauts=any(
                                c in (correction.corrected_text or "")
                                for c in "äöüÄÖÜß"
                            ),
                            notes=f"Aus Korrektur {correction.id}",
                        )
                        db.add(new_sample)
                        stats["samples_created"] += 1

                # Markiere Korrektur als verarbeitet
                correction.processed_for_learning = True
                correction.processed_at = now
                stats["corrections_processed"] += 1

            except Exception as e:
                stats["errors"].append({
                    "correction_id": str(correction.id),
                    "error": safe_error_detail(e, "Vorgang"),
                })
                logger.error(
                    "correction_conversion_failed",
                    correction_id=str(correction.id)[:8],
                    **safe_error_log(e),
                )

        await db.commit()

        logger.info(
            "corrections_converted_to_samples",
            processed=stats["corrections_processed"],
            created=stats["samples_created"],
            updated=stats["samples_updated"],
        )

        return stats

    async def get_surya_retraining_recommendation(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Empfehlung für Surya-Retraining basierend auf Feedback.

        Analysiert aktuelle Korrektur-Trends und gibt
        Retraining-Empfehlung mit Dringlichkeit.

        Args:
            db: Datenbank-Session

        Returns:
            Retraining-Empfehlung mit Metriken
        """
        # Hole aktuelle Korrektur-Statistiken
        corrections_7d = await self.get_surya_corrections(
            db, days=7, unprocessed_only=False
        )
        corrections_30d = await self.get_surya_corrections(
            db, days=30, unprocessed_only=False
        )

        # Umlaut-Fehler-Analyse
        umlaut_analysis = await self.analyze_surya_umlaut_errors(db, days=30)

        # Berechne Metriken
        corrections_7d_count = len(corrections_7d)
        corrections_30d_count = len(corrections_30d)
        umlaut_error_rate = (
            umlaut_analysis["umlaut_corrections"] / umlaut_analysis["total_corrections"]
            if umlaut_analysis["total_corrections"] > 0
            else 0.0
        )

        # Bestimme Dringlichkeit
        should_retrain = False
        urgency = "low"
        reasons = []

        # Bedingung 1: Viele Korrektionen in 7 Tagen
        if corrections_7d_count >= 30:
            should_retrain = True
            urgency = "medium"
            reasons.append(f"{corrections_7d_count} Korrektionen in 7 Tagen")

        # Bedingung 2: Hohe Umlaut-Fehlerrate
        if umlaut_error_rate > 0.3:  # >30% der Fehler sind Umlaute
            should_retrain = True
            urgency = "high"
            reasons.append(f"Umlaut-Fehlerrate bei {umlaut_error_rate:.1%}")

        # Bedingung 3: Steigende Trend
        weekly_rate = corrections_7d_count / 7 if corrections_7d_count > 0 else 0
        monthly_rate = corrections_30d_count / 30 if corrections_30d_count > 0 else 0
        if weekly_rate > monthly_rate * 1.5:
            should_retrain = True
            reasons.append("Steigende Korrektur-Rate")

        return {
            "should_retrain": should_retrain,
            "urgency": urgency,
            "reasons": reasons,
            "metrics": {
                "corrections_7d": corrections_7d_count,
                "corrections_30d": corrections_30d_count,
                "umlaut_error_rate": umlaut_error_rate,
                "weekly_correction_rate": weekly_rate,
                "monthly_correction_rate": monthly_rate,
            },
            "umlaut_analysis": {
                "total_umlaut_errors": umlaut_analysis["umlaut_corrections"],
                "common_patterns": umlaut_analysis["common_patterns"][:5],
            },
        }


# Singleton
_feedback_learning_service: Optional[FeedbackLearningService] = None


def get_feedback_learning_service() -> FeedbackLearningService:
    """Gibt FeedbackLearningService-Singleton zurück."""
    global _feedback_learning_service
    if _feedback_learning_service is None:
        _feedback_learning_service = FeedbackLearningService()
    return _feedback_learning_service
