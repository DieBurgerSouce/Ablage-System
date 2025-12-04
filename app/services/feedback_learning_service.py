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
import json

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    OCRValidationCorrection,
    OCRBackendStatsDaily,
    CorrectionType,
)

logger = structlog.get_logger(__name__)


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
        weights = {
            CorrectionType.UMLAUT.value: 2.0,      # Umlaute sind kritisch
            CorrectionType.CURRENCY.value: 2.0,    # Geldbeträge kritisch
            CorrectionType.NUMBER.value: 1.5,      # Zahlen wichtig
            CorrectionType.DATE.value: 1.5,        # Daten wichtig
            CorrectionType.FIELD.value: 1.0,       # Feld-Korrekturen
            CorrectionType.SPELLING.value: 0.5,    # Rechtschreibung weniger kritisch
            CorrectionType.FORMATTING.value: 0.3,  # Format am wenigsten kritisch
            CorrectionType.GENERAL.value: 0.5,
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

        logger.info("feedback_learning_service_initialized")

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
            if corr_type == CorrectionType.UMLAUT.value:
                pattern.umlaut_errors += 1
            elif corr_type == CorrectionType.NUMBER.value:
                pattern.number_errors += 1
            elif corr_type == CorrectionType.DATE.value:
                pattern.date_errors += 1
            elif corr_type == CorrectionType.CURRENCY.value:
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

        Args:
            db: Datenbank-Session
            force_refresh: Cache umgehen

        Returns:
            LearnedBackendWeights mit optimierten Gewichtungen
        """
        now = datetime.now(timezone.utc)

        # Cache prüfen
        if (
            not force_refresh
            and self._cached_weights
            and self._last_cache_update
            and (now - self._last_cache_update) < self._cache_ttl
        ):
            return self._cached_weights

        # Analysiere Korrekturen
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

        # Cache aktualisieren
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

        Args:
            db: Datenbank-Session
            batch_size: Anzahl zu verarbeitender Korrekturen

        Returns:
            Anzahl verarbeiteter Korrekturen
        """
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

        for correction in corrections:
            try:
                # Hier könnte zusätzliche Verarbeitung stattfinden:
                # - Training Sample erstellen wenn genug Kontext
                # - Pattern-Datenbank aktualisieren
                # - Model Fine-Tuning Queue

                # Markiere als verarbeitet
                correction.learning_processed = True
                correction.learning_processed_at = now
                processed += 1

            except Exception as e:
                logger.error(
                    "correction_processing_failed",
                    correction_id=str(correction.id)[:8],
                    error=str(e)
                )

        await db.commit()

        # Cache invalidieren für neue Gewichtungen
        self._cached_weights = None
        self._last_cache_update = None

        logger.info(
            "corrections_processed",
            processed=processed,
            total=len(corrections)
        )

        return processed

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


# Singleton
_feedback_learning_service: Optional[FeedbackLearningService] = None


def get_feedback_learning_service() -> FeedbackLearningService:
    """Gibt FeedbackLearningService-Singleton zurück."""
    global _feedback_learning_service
    if _feedback_learning_service is None:
        _feedback_learning_service = FeedbackLearningService()
    return _feedback_learning_service
