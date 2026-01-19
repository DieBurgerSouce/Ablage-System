"""
Self-Learning OCR Service

Automatisches Lernen aus User-Korrekturen mit:
- Echtzeit-Feedback Integration
- Confidence-Adjustment basierend auf Korrekturen
- A/B Testing neuer Modell-Versionen
- Automatischer Rollback bei Verschlechterung
- Aggressive Learning (jede Korrektur fliesst ein)

Enterprise-Grade Self-Learning OCR System.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
import asyncio

from sqlalchemy import select, and_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
import structlog
import json

from app.db.models import (
    Document,
    OCRValidationCorrection,
)
from app.core.redis_state import RedisStateManager

logger = structlog.get_logger(__name__)


class LearningMode(str, Enum):
    """Learning-Modus des Systems."""
    AGGRESSIVE = "aggressive"  # Jede Korrektur fliesst sofort ein
    CAUTIOUS = "cautious"      # Nur verifizierte Korrekturen
    BATCH = "batch"            # Batch-Learning (taeglich)


class ModelVersion(str, Enum):
    """OCR-Modell Versionen fuer A/B Testing."""
    BASELINE = "baseline"
    CANDIDATE_A = "candidate_a"
    CANDIDATE_B = "candidate_b"


@dataclass
class CorrectionFeedback:
    """User-Korrektur Feedback."""
    document_id: UUID
    field_name: str
    original_value: str
    corrected_value: str
    ocr_backend: str
    original_confidence: float
    user_id: Optional[UUID] = None
    correction_type: str = "text"  # text, amount, date, entity
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_major_correction(self) -> bool:
        """Pruefen ob es eine grosse Korrektur ist."""
        if not self.original_value or not self.corrected_value:
            return True
        # Levenshtein-aehnliche Heuristik
        len_diff = abs(len(self.original_value) - len(self.corrected_value))
        max_len = max(len(self.original_value), len(self.corrected_value), 1)
        return len_diff / max_len > 0.3


@dataclass
class ModelPerformanceMetrics:
    """Performance-Metriken fuer ein Modell."""
    version: ModelVersion
    total_documents: int = 0
    corrections_count: int = 0
    major_corrections: int = 0
    avg_confidence: float = 0.0
    accuracy_rate: float = 1.0
    confidence_calibration_error: float = 0.0
    processing_time_avg_ms: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def correction_rate(self) -> float:
        """Korrekturrate berechnen."""
        if self.total_documents == 0:
            return 0.0
        return self.corrections_count / self.total_documents

    @property
    def quality_score(self) -> float:
        """Gesamtqualitaets-Score (0-1)."""
        # Gewichtete Kombination aus mehreren Faktoren
        accuracy_weight = 0.4
        confidence_weight = 0.3
        speed_weight = 0.15
        calibration_weight = 0.15

        accuracy_score = self.accuracy_rate
        confidence_score = self.avg_confidence
        # Speed: Normalisiert auf 0-1 (unter 2s = 1.0, ueber 10s = 0)
        speed_score = max(0, min(1.0, 1.0 - (self.processing_time_avg_ms - 2000) / 8000))
        # Calibration: Niedriger ECE ist besser
        calibration_score = max(0, 1.0 - self.confidence_calibration_error * 2)

        return (
            accuracy_score * accuracy_weight +
            confidence_score * confidence_weight +
            speed_score * speed_weight +
            calibration_score * calibration_weight
        )


@dataclass
class ABTestConfig:
    """Konfiguration fuer A/B Test."""
    test_id: str
    baseline_version: ModelVersion
    candidate_version: ModelVersion
    traffic_split: float = 0.1  # 10% Traffic fuer Kandidat
    min_samples: int = 100
    max_duration_days: int = 7
    significance_threshold: float = 0.05
    rollback_threshold: float = -0.05  # Rollback wenn Kandidat >5% schlechter
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        """Pruefen ob Test abgelaufen."""
        max_end = self.started_at + timedelta(days=self.max_duration_days)
        return datetime.now(timezone.utc) > max_end


@dataclass
class ABTestResult:
    """Ergebnis eines A/B Tests."""
    test_id: str
    baseline_metrics: ModelPerformanceMetrics
    candidate_metrics: ModelPerformanceMetrics
    improvement_percent: float
    is_significant: bool
    recommendation: str  # "promote", "rollback", "continue"
    confidence_level: float


# ============================================================================
# DATABASE MODELS FOR PERSISTENCE
# ============================================================================

# Note: These would normally be in app/db/models.py
# For now, we use the existing metadata JSONB on other tables or a separate
# key-value store pattern

CONFIDENCE_ADJUSTMENTS_KEY = "ocr_learning_confidence_adjustments"
AB_TESTS_KEY = "ocr_learning_ab_tests"
MODEL_METRICS_KEY = "ocr_learning_model_metrics"
LEARNING_MODE_KEY = "ocr_learning_mode"


class SelfLearningOCRService:
    """
    Self-Learning OCR Service.

    Automatisches Lernen aus User-Korrekturen mit aggressive learning mode.

    WICHTIG: Diese Klasse ist NICHT thread-safe und sollte pro Request
    neu instanziiert werden (via get_self_learning_service).
    """

    def __init__(
        self,
        db: AsyncSession,
        learning_mode: LearningMode = LearningMode.AGGRESSIVE,
    ):
        self._db = db
        self._learning_mode = learning_mode
        self._lock = asyncio.Lock()

        # In-Memory Cache (wird bei Bedarf aus DB geladen)
        self._backend_adjustments: Optional[Dict[str, float]] = None
        self._field_adjustments: Optional[Dict[str, Dict[str, float]]] = None
        self._active_ab_tests: Optional[Dict[str, ABTestConfig]] = None
        self._model_metrics: Optional[Dict[ModelVersion, ModelPerformanceMetrics]] = None

    @property
    def learning_mode(self) -> LearningMode:
        """Aktueller Learning-Modus."""
        return self._learning_mode

    @learning_mode.setter
    def learning_mode(self, value: LearningMode) -> None:
        """Learning-Modus setzen."""
        self._learning_mode = value

    # =========================================================================
    # PERSISTENCE LAYER
    # =========================================================================

    async def _load_state_from_db(self) -> None:
        """Lade persistierten State aus Redis."""
        async with self._lock:
            if self._backend_adjustments is not None:
                return  # Already loaded

            try:
                # Load confidence adjustments from Redis
                redis = RedisStateManager.get_instance()
                await redis.connect()

                data = await redis._redis.get(CONFIDENCE_ADJUSTMENTS_KEY)

                if data:
                    stored = json.loads(data)
                    self._backend_adjustments = stored.get("backend", {})
                    self._field_adjustments = stored.get("field", {})

                    # Lade persistierten Learning-Modus
                    stored_mode = stored.get("learning_mode")
                    if stored_mode:
                        try:
                            self._learning_mode = LearningMode(stored_mode)
                        except ValueError:
                            pass  # Behalte Default bei invalidem Wert
                else:
                    self._backend_adjustments = {}
                    self._field_adjustments = {}

                # Initialize model metrics
                self._model_metrics = {
                    ModelVersion.BASELINE: ModelPerformanceMetrics(version=ModelVersion.BASELINE),
                }

                # Initialize AB tests
                self._active_ab_tests = {}

            except Exception as e:
                logger.warning("failed_to_load_learning_state", error=str(e))
                self._backend_adjustments = {}
                self._field_adjustments = {}
                self._model_metrics = {
                    ModelVersion.BASELINE: ModelPerformanceMetrics(version=ModelVersion.BASELINE),
                }
                self._active_ab_tests = {}

    async def _persist_adjustments(self) -> None:
        """Persistiere Confidence-Adjustments und Learning-Modus in Redis."""
        if self._backend_adjustments is None:
            return

        try:
            # Speichere State in Redis (persistiert und schnell)
            data = {
                "backend": self._backend_adjustments,
                "field": self._field_adjustments,
                "learning_mode": self._learning_mode.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            redis = RedisStateManager.get_instance()
            await redis.connect()

            # Setze mit langer TTL (30 Tage) - wird bei jedem Update erneuert
            await redis._redis.setex(
                CONFIDENCE_ADJUSTMENTS_KEY,
                timedelta(days=30),
                json.dumps(data),
            )

            logger.debug(
                "ocr_learning_state_persisted",
                backends=len(self._backend_adjustments),
                fields=sum(len(f) for f in self._field_adjustments.values()),
            )

        except Exception as e:
            logger.error("failed_to_persist_adjustments", error=str(e))

    # =========================================================================
    # FEEDBACK INTEGRATION (Aggressive Learning)
    # =========================================================================

    async def process_correction(
        self,
        feedback: CorrectionFeedback,
    ) -> Dict[str, Any]:
        """
        Verarbeite User-Korrektur und passe System an.

        Im AGGRESSIVE Modus wird sofort gelernt.

        Args:
            feedback: User-Korrektur Feedback

        Returns:
            Dictionary mit Anpassungs-Ergebnissen
        """
        await self._load_state_from_db()

        result: Dict[str, Any] = {
            "processed": True,
            "learning_mode": self._learning_mode.value,
            "adjustments": [],
            "rollback_triggered": False,
        }

        try:
            # 1. Confidence-Adjustment berechnen
            confidence_adjustment = self._calculate_confidence_adjustment(feedback)
            result["confidence_adjustment"] = confidence_adjustment

            # 2. Backend-spezifisches Adjustment
            await self._update_backend_adjustment(
                backend=feedback.ocr_backend,
                field=feedback.field_name,
                adjustment=confidence_adjustment,
            )
            result["adjustments"].append({
                "type": "backend_confidence",
                "backend": feedback.ocr_backend,
                "field": feedback.field_name,
                "value": confidence_adjustment,
            })

            # 3. Training Sample erstellen (fuer spaeteren Batch-Train)
            if self._learning_mode == LearningMode.AGGRESSIVE:
                sample_id = await self._create_training_sample(feedback)
                result["training_sample_id"] = str(sample_id) if sample_id else None

            # 4. A/B Test Metriken aktualisieren
            await self._update_ab_test_metrics(feedback)

            # 5. Pruefe ob Rollback noetig
            rollback_needed = await self._check_rollback_conditions()
            if rollback_needed:
                result["rollback_triggered"] = True
                await self._perform_rollback()

            # 6. Persistiere Aenderungen
            await self._persist_adjustments()

            logger.info(
                "correction_processed",
                document_id=str(feedback.document_id),
                field=feedback.field_name,
                backend=feedback.ocr_backend,
                is_major=feedback.is_major_correction,
                adjustment=confidence_adjustment,
            )

        except Exception as e:
            logger.error("correction_processing_failed", error=str(e))
            result["processed"] = False
            result["error"] = str(e)

        return result

    def _calculate_confidence_adjustment(
        self,
        feedback: CorrectionFeedback,
    ) -> float:
        """
        Berechne Confidence-Adjustment basierend auf Korrektur.

        Negative Werte = Confidence zu hoch
        Positive Werte = Confidence zu niedrig (selten bei Korrekturen)
        """
        if feedback.is_major_correction:
            # Grosse Korrektur = Confidence war zu hoch
            adjustment = -0.15 * (1 - feedback.original_confidence)
        else:
            # Kleine Korrektur = Moderate Anpassung
            adjustment = -0.05 * (1 - feedback.original_confidence)

        # Skalierung basierend auf urspruenglicher Confidence
        # Hohe Confidence + Korrektur = staerkere Anpassung
        if feedback.original_confidence > 0.9:
            adjustment *= 1.5
        elif feedback.original_confidence > 0.8:
            adjustment *= 1.2

        return max(-0.3, min(0.1, adjustment))

    async def _update_backend_adjustment(
        self,
        backend: str,
        field: str,
        adjustment: float,
    ) -> None:
        """Aktualisiere Backend-spezifische Adjustments (thread-safe)."""
        async with self._lock:
            if self._backend_adjustments is None:
                self._backend_adjustments = {}
            if self._field_adjustments is None:
                self._field_adjustments = {}

            # Exponential Moving Average fuer sanfte Anpassung
            alpha = 0.1  # Learning Rate

            # Backend-Level Adjustment
            current_backend = self._backend_adjustments.get(backend, 0.0)
            self._backend_adjustments[backend] = current_backend + alpha * adjustment

            # Field-Level Adjustment
            if backend not in self._field_adjustments:
                self._field_adjustments[backend] = {}
            current_field = self._field_adjustments[backend].get(field, 0.0)
            self._field_adjustments[backend][field] = current_field + alpha * adjustment

    async def _create_training_sample(
        self,
        feedback: CorrectionFeedback,
    ) -> Optional[UUID]:
        """
        Speichere Korrektur-Feedback fuer spaeteres Training.

        NOTE: Training Samples werden aktuell nur in Redis gecacht,
        da das OCRTrainingSample Model ein anderes Schema hat (fuer Benchmarking).
        Fuer vollstaendiges Training-Tracking sollte ein dediziertes
        OCRCorrectionFeedback Model erstellt werden.
        """
        try:
            # Speichere Korrektur-Feedback in Redis fuer Batch-Verarbeitung
            redis = RedisStateManager.get_instance()
            await redis.connect()

            # Key fuer Korrektur-Queue
            queue_key = "ocr_learning:correction_queue"
            feedback_data = {
                "document_id": str(feedback.document_id),
                "field_name": feedback.field_name,
                "original_value": feedback.original_value[:1000],  # Limit fuer Redis
                "corrected_value": feedback.corrected_value[:1000],
                "ocr_backend": feedback.ocr_backend,
                "original_confidence": feedback.original_confidence,
                "correction_type": feedback.correction_type,
                "user_id": str(feedback.user_id) if feedback.user_id else None,
                "timestamp": feedback.timestamp.isoformat(),
                "learning_mode": self._learning_mode.value,
            }

            # Fuege zur Queue hinzu (LPUSH fuer FIFO)
            await redis._redis.lpush(queue_key, json.dumps(feedback_data))

            # Begrenze Queue-Groesse auf 10000 Eintraege
            await redis._redis.ltrim(queue_key, 0, 9999)

            logger.debug(
                "correction_feedback_queued",
                document_id=str(feedback.document_id),
                field=feedback.field_name,
            )

            return feedback.document_id  # Rueckgabe der Document-ID als Referenz

        except Exception as e:
            logger.warning("failed_to_queue_training_feedback", error=str(e))
            return None

    # =========================================================================
    # CONFIDENCE CALIBRATION
    # =========================================================================

    def get_calibrated_confidence(
        self,
        backend: str,
        field: str,
        raw_confidence: float,
    ) -> float:
        """
        Liefere kalibrierte Confidence basierend auf gelernten Adjustments.

        Args:
            backend: OCR Backend Name
            field: Feld-Name (z.B. "amount", "date", "vendor")
            raw_confidence: Urspruengliche Confidence vom Backend

        Returns:
            Kalibrierte Confidence (0.0 - 1.0)
        """
        if self._backend_adjustments is None:
            return raw_confidence

        # Backend-Level Adjustment
        backend_adj = self._backend_adjustments.get(backend, 0.0)

        # Field-Level Adjustment (wenn vorhanden)
        field_adj = 0.0
        if self._field_adjustments and backend in self._field_adjustments:
            field_adj = self._field_adjustments[backend].get(field, 0.0)

        # Kombiniere Adjustments
        calibrated = raw_confidence + backend_adj + field_adj

        # Clamp auf [0, 1]
        return max(0.0, min(1.0, calibrated))

    async def get_confidence_statistics(
        self,
        backend: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Liefere Confidence-Statistiken.

        Args:
            backend: Optional - Filter nach Backend

        Returns:
            Statistik-Dictionary
        """
        await self._load_state_from_db()

        stats: Dict[str, Any] = {
            "backend_adjustments": (self._backend_adjustments or {}).copy(),
            "field_adjustments": {k: dict(v) for k, v in (self._field_adjustments or {}).items()},
            "learning_mode": self._learning_mode.value,
        }

        if backend:
            stats["backend_adjustments"] = {
                backend: (self._backend_adjustments or {}).get(backend, 0.0)
            }
            stats["field_adjustments"] = {
                backend: dict((self._field_adjustments or {}).get(backend, {}))
            }

        return stats

    # =========================================================================
    # A/B TESTING
    # =========================================================================

    async def start_ab_test(
        self,
        test_id: str,
        candidate_version: ModelVersion,
        traffic_split: float = 0.1,
        min_samples: int = 100,
        max_duration_days: int = 7,
    ) -> ABTestConfig:
        """
        Starte neuen A/B Test.

        Args:
            test_id: Eindeutige Test-ID
            candidate_version: Zu testende Modell-Version
            traffic_split: Anteil Traffic fuer Kandidat (0.0 - 0.5)
            min_samples: Minimale Samples vor Auswertung
            max_duration_days: Maximale Test-Dauer

        Returns:
            A/B Test Konfiguration
        """
        await self._load_state_from_db()

        config = ABTestConfig(
            test_id=test_id,
            baseline_version=ModelVersion.BASELINE,
            candidate_version=candidate_version,
            traffic_split=min(0.5, max(0.01, traffic_split)),
            min_samples=min_samples,
            max_duration_days=max_duration_days,
        )

        if self._active_ab_tests is None:
            self._active_ab_tests = {}
        self._active_ab_tests[test_id] = config

        # Initialisiere Metriken fuer Kandidat
        if self._model_metrics is None:
            self._model_metrics = {}
        if candidate_version not in self._model_metrics:
            self._model_metrics[candidate_version] = ModelPerformanceMetrics(
                version=candidate_version
            )

        logger.info(
            "ab_test_started",
            test_id=test_id,
            candidate=candidate_version.value,
            traffic_split=traffic_split,
        )

        return config

    def select_model_version(
        self,
        test_id: Optional[str] = None,
    ) -> ModelVersion:
        """
        Waehle Modell-Version (fuer A/B Testing).

        Args:
            test_id: Optional - Spezifischer Test

        Returns:
            Zu verwendende Modell-Version
        """
        import random

        if self._active_ab_tests is None:
            return ModelVersion.BASELINE

        if test_id and test_id in self._active_ab_tests:
            config = self._active_ab_tests[test_id]
            if random.random() < config.traffic_split:
                return config.candidate_version

        # Default: Baseline oder aktiver Test
        for config in self._active_ab_tests.values():
            if not config.is_expired:
                if random.random() < config.traffic_split:
                    return config.candidate_version

        return ModelVersion.BASELINE

    async def _update_ab_test_metrics(
        self,
        feedback: CorrectionFeedback,
    ) -> None:
        """Aktualisiere A/B Test Metriken."""
        if self._model_metrics is None:
            self._model_metrics = {
                ModelVersion.BASELINE: ModelPerformanceMetrics(version=ModelVersion.BASELINE),
            }

        # Fuer Baseline (immer aktualisieren)
        baseline = self._model_metrics.get(ModelVersion.BASELINE)
        if baseline is None:
            baseline = ModelPerformanceMetrics(version=ModelVersion.BASELINE)
            self._model_metrics[ModelVersion.BASELINE] = baseline

        baseline.total_documents += 1
        baseline.corrections_count += 1
        if feedback.is_major_correction:
            baseline.major_corrections += 1
        # Recalculate accuracy
        if baseline.total_documents > 0:
            baseline.accuracy_rate = 1 - (baseline.corrections_count / baseline.total_documents)
        baseline.last_updated = datetime.now(timezone.utc)

    async def evaluate_ab_test(
        self,
        test_id: str,
    ) -> Optional[ABTestResult]:
        """
        Evaluiere A/B Test und liefere Ergebnis.

        Args:
            test_id: Test-ID

        Returns:
            Test-Ergebnis oder None wenn nicht genug Daten
        """
        await self._load_state_from_db()

        if self._active_ab_tests is None or test_id not in self._active_ab_tests:
            return None

        config = self._active_ab_tests[test_id]

        if self._model_metrics is None:
            return None

        baseline_metrics = self._model_metrics.get(ModelVersion.BASELINE)
        candidate_metrics = self._model_metrics.get(config.candidate_version)

        if not baseline_metrics or not candidate_metrics:
            return None

        # Pruefe Mindestsamples
        total_samples = baseline_metrics.total_documents + candidate_metrics.total_documents
        if total_samples < config.min_samples:
            return ABTestResult(
                test_id=test_id,
                baseline_metrics=baseline_metrics,
                candidate_metrics=candidate_metrics,
                improvement_percent=0.0,
                is_significant=False,
                recommendation="continue",
                confidence_level=0.0,
            )

        # Berechne Improvement
        baseline_quality = baseline_metrics.quality_score
        candidate_quality = candidate_metrics.quality_score

        if baseline_quality > 0:
            improvement = (candidate_quality - baseline_quality) / baseline_quality
        else:
            improvement = 0.0

        # Bestimme Empfehlung
        if improvement < config.rollback_threshold:
            recommendation = "rollback"
        elif improvement > config.significance_threshold:
            recommendation = "promote"
        else:
            recommendation = "continue"

        # Einfache Signifikanz-Heuristik
        is_significant = abs(improvement) > config.significance_threshold
        confidence_level = min(1.0, total_samples / (config.min_samples * 2))

        return ABTestResult(
            test_id=test_id,
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            improvement_percent=improvement * 100,
            is_significant=is_significant,
            recommendation=recommendation,
            confidence_level=confidence_level,
        )

    async def end_ab_test(
        self,
        test_id: str,
        action: str = "rollback",  # "promote" oder "rollback"
    ) -> Dict[str, Any]:
        """
        Beende A/B Test und fuehre Aktion aus.

        Args:
            test_id: Test-ID
            action: "promote" (Kandidat wird Baseline) oder "rollback"

        Returns:
            Ergebnis-Dictionary
        """
        await self._load_state_from_db()

        if self._active_ab_tests is None or test_id not in self._active_ab_tests:
            return {"success": False, "error": "Test nicht gefunden"}

        config = self._active_ab_tests[test_id]
        result = await self.evaluate_ab_test(test_id)

        if action == "promote" and result and self._model_metrics is not None:
            # Kandidat wird neue Baseline
            self._model_metrics[ModelVersion.BASELINE] = ModelPerformanceMetrics(
                version=ModelVersion.BASELINE,
                total_documents=0,  # Reset
            )
            logger.info(
                "model_promoted",
                test_id=test_id,
                candidate=config.candidate_version.value,
                improvement=result.improvement_percent,
            )

        # Test entfernen
        del self._active_ab_tests[test_id]

        return {
            "success": True,
            "test_id": test_id,
            "action": action,
            "result": {
                "improvement_percent": result.improvement_percent if result else 0,
                "recommendation": result.recommendation if result else "unknown",
            },
        }

    # =========================================================================
    # AUTOMATIC ROLLBACK
    # =========================================================================

    async def _check_rollback_conditions(self) -> bool:
        """
        Pruefe ob automatischer Rollback noetig.

        Returns:
            True wenn Rollback empfohlen
        """
        if self._active_ab_tests is None:
            return False

        for test_id in self._active_ab_tests:
            result = await self.evaluate_ab_test(test_id)
            if result and result.recommendation == "rollback":
                logger.warning(
                    "rollback_condition_detected",
                    test_id=test_id,
                    improvement=result.improvement_percent,
                )
                return True
        return False

    async def _perform_rollback(self) -> None:
        """Fuehre Rollback durch."""
        if self._active_ab_tests is None:
            return

        # Beende alle aktiven Tests mit Rollback
        for test_id in list(self._active_ab_tests.keys()):
            await self.end_ab_test(test_id, action="rollback")

        # Reset Adjustments (konservativ)
        # Behalte nur leicht negative Adjustments
        if self._backend_adjustments:
            for backend in self._backend_adjustments:
                adj = self._backend_adjustments[backend]
                self._backend_adjustments[backend] = max(-0.1, min(0.0, adj))

        await self._persist_adjustments()
        logger.warning("rollback_performed")

    # =========================================================================
    # LEARNING STATISTICS
    # =========================================================================

    async def get_learning_statistics(self) -> Dict[str, Any]:
        """
        Liefere umfassende Learning-Statistiken.

        Returns:
            Statistik-Dictionary
        """
        await self._load_state_from_db()

        # Zaehle Training Samples
        sample_count_query = select(func.count(OCRTrainingSample.id)).where(
            OCRTrainingSample.ocr_backend != "__system__"  # Exclude markers
        )
        sample_count = (await self._db.execute(sample_count_query)).scalar() or 0

        # Korrektur-Statistiken
        correction_query = select(func.count(OCRValidationCorrection.id))
        correction_count = (await self._db.execute(correction_query)).scalar() or 0

        return {
            "learning_mode": self._learning_mode.value,
            "training_samples": sample_count,
            "total_corrections": correction_count,
            "backend_adjustments": (self._backend_adjustments or {}).copy(),
            "field_adjustments": {k: dict(v) for k, v in (self._field_adjustments or {}).items()},
            "active_ab_tests": [
                {
                    "test_id": test_id,
                    "candidate": config.candidate_version.value,
                    "traffic_split": config.traffic_split,
                    "started_at": config.started_at.isoformat(),
                    "is_expired": config.is_expired,
                }
                for test_id, config in (self._active_ab_tests or {}).items()
            ],
            "model_metrics": {
                version.value: {
                    "total_documents": metrics.total_documents,
                    "corrections_count": metrics.corrections_count,
                    "accuracy_rate": metrics.accuracy_rate,
                    "quality_score": metrics.quality_score,
                }
                for version, metrics in (self._model_metrics or {}).items()
            },
        }


def get_self_learning_service(db: AsyncSession) -> SelfLearningOCRService:
    """
    Erstelle neue Self-Learning Service Instanz.

    WICHTIG: Jeder Request bekommt eine eigene Instanz.
    Der State wird aus der Datenbank geladen (lazy).

    Args:
        db: Database Session

    Returns:
        SelfLearningOCRService Instance
    """
    return SelfLearningOCRService(
        db=db,
        learning_mode=LearningMode.AGGRESSIVE,
    )
