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
    OCRResult,
    OCRValidationCorrection,
)
from app.db.models_ocr_feedback import (
    OCRCorrectionFeedback,
    OCRBackendPerformance,
    CorrectionType,
    FeedbackStatus,
)
from app.core.redis_state import RedisStateManager
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class LearningMode(str, Enum):
    """Learning-Modus des Systems."""
    AGGRESSIVE = "aggressive"  # Jede Korrektur fliesst sofort ein
    CAUTIOUS = "cautious"      # Nur verifizierte Korrekturen
    BATCH = "batch"            # Batch-Learning (täglich)
    REALTIME = "realtime"      # Sofortige Verarbeitung ohne Batching


class ModelVersion(str, Enum):
    """OCR-Modell Versionen für A/B Testing."""
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
        """Prüfen ob es eine grosse Korrektur ist."""
        if not self.original_value or not self.corrected_value:
            return True
        # Levenshtein-ähnliche Heuristik
        len_diff = abs(len(self.original_value) - len(self.corrected_value))
        max_len = max(len(self.original_value), len(self.corrected_value), 1)
        return len_diff / max_len > 0.3


@dataclass
class ModelPerformanceMetrics:
    """Performance-Metriken für ein Modell."""
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
        """Gesamtqualitäts-Score (0-1)."""
        # Gewichtete Kombination aus mehreren Faktoren
        accuracy_weight = 0.4
        confidence_weight = 0.3
        speed_weight = 0.15
        calibration_weight = 0.15

        accuracy_score = self.accuracy_rate
        confidence_score = self.avg_confidence
        # Speed: Normalisiert auf 0-1 (unter 2s = 1.0, über 10s = 0)
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
    """Konfiguration für A/B Test."""
    test_id: str
    baseline_version: ModelVersion
    candidate_version: ModelVersion
    traffic_split: float = 0.1  # 10% Traffic für Kandidat
    min_samples: int = 100
    max_duration_days: int = 7
    significance_threshold: float = 0.05
    rollback_threshold: float = -0.05  # Rollback wenn Kandidat >5% schlechter
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        """Prüfen ob Test abgelaufen."""
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
                        except ValueError as e:
                            # Behalte Default bei invalidem persistierten Wert
                            logger.debug("learning_mode_invalid_default", error_type=type(e).__name__)
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
                logger.warning("failed_to_load_learning_state", **safe_error_log(e))
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
            logger.error("failed_to_persist_adjustments", **safe_error_log(e))

    async def apply_immediate_correction(
        self,
        db: AsyncSession,
        feedback: CorrectionFeedback,
        entity_id: Optional[UUID] = None,
    ) -> bool:
        """
        Sofortige Korrektur-Anwendung (REALTIME Modus).

        Aktualisiert Confidence in Redis und speichert
        lieferantenspezifische Korrektur-Hinweise.
        """
        try:
            redis = RedisStateManager.get_instance()
            await redis.connect()

            # Update field confidence immediately
            confidence_key = f"ocr:confidence:{feedback.ocr_backend}:{feedback.field_name}"
            current = await redis._redis.get(confidence_key)
            current_conf = float(current) if current else feedback.original_confidence

            # Faster convergence: alpha 0.15 instead of 0.1
            alpha = 0.15
            if feedback.is_major_correction:
                # Stronger adjustment for major corrections
                new_confidence = current_conf * (1 - alpha * 2)
            else:
                new_confidence = current_conf * (1 - alpha) + alpha * 0.95

            await redis._redis.setex(
                confidence_key,
                timedelta(days=7),
                str(round(new_confidence, 4)),
            )

            # Store supplier-specific hint
            if entity_id:
                supplier_key = f"ocr:supplier:{entity_id}:field:{feedback.field_name}"
                hint_data = {
                    "corrected_value": feedback.corrected_value,
                    "correction_type": feedback.correction_type,
                    "confidence_adjustment": round(new_confidence, 4),
                    "timestamp": feedback.timestamp.isoformat(),
                }
                await redis._redis.setex(
                    supplier_key,
                    timedelta(days=30),
                    json.dumps(hint_data),
                )

            logger.info(
                "Sofortige Korrektur angewendet",
                field=feedback.field_name,
                backend=feedback.ocr_backend,
                old_conf=round(current_conf, 4),
                new_conf=round(new_confidence, 4),
            )
            return True
        except Exception as exc:
            logger.error(
                "ocr_realtime_correction_failed",
                **safe_error_log(exc, context="Sofortige Korrektur"),
            )
            return False

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

            # 3. Training Sample erstellen (für späteren Batch-Train)
            if self._learning_mode == LearningMode.AGGRESSIVE:
                sample_id = await self._create_training_sample(feedback)
                result["training_sample_id"] = str(sample_id) if sample_id else None

            # 4. A/B Test Metriken aktualisieren
            await self._update_ab_test_metrics(feedback)

            # 5. Prüfe ob Rollback noetig
            rollback_needed = await self._check_rollback_conditions()
            if rollback_needed:
                result["rollback_triggered"] = True
                await self._perform_rollback()

            # 6. Persistiere Änderungen
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
            logger.error("correction_processing_failed", **safe_error_log(e))
            result["processed"] = False
            result["error"] = safe_error_detail(e, "OCR-Learning")

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
        # Hohe Confidence + Korrektur = stärkere Anpassung
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

            # Exponential Moving Average für sanfte Anpassung
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
        Speichere Korrektur-Feedback für späteres Training.

        Persistiert sowohl in Redis (für schnelle Batch-Verarbeitung)
        als auch in PostgreSQL (für langfristige ML-Analyse).
        """
        feedback_id: Optional[UUID] = None

        try:
            # 1. Persistiere in PostgreSQL (langfristig, keine TTL)
            feedback_id = await self._persist_feedback_to_db(feedback)

            # 2. Speichere auch in Redis für schnelle Batch-Verarbeitung
            redis = RedisStateManager.get_instance()
            await redis.connect()

            queue_key = "ocr_learning:correction_queue"
            feedback_data = {
                "document_id": str(feedback.document_id),
                "field_name": feedback.field_name,
                "original_value": feedback.original_value[:1000],  # Limit für Redis
                "corrected_value": feedback.corrected_value[:1000],
                "ocr_backend": feedback.ocr_backend,
                "original_confidence": feedback.original_confidence,
                "correction_type": feedback.correction_type,
                "user_id": str(feedback.user_id) if feedback.user_id else None,
                "timestamp": feedback.timestamp.isoformat(),
                "learning_mode": self._learning_mode.value,
                "db_feedback_id": str(feedback_id) if feedback_id else None,
            }

            await redis._redis.lpush(queue_key, json.dumps(feedback_data))
            await redis._redis.ltrim(queue_key, 0, 9999)

            logger.debug(
                "correction_feedback_queued",
                document_id=str(feedback.document_id),
                field=feedback.field_name,
                db_id=str(feedback_id) if feedback_id else None,
            )

            return feedback_id or feedback.document_id

        except Exception as e:
            logger.warning("failed_to_queue_training_feedback", **safe_error_log(e))
            return feedback_id  # Rückgabe DB-ID wenn verfügbar

    async def _persist_feedback_to_db(
        self,
        feedback: CorrectionFeedback,
    ) -> Optional[UUID]:
        """
        Persistiere OCR-Korrektur in PostgreSQL für langfristige Analyse.

        Ermöglicht:
        - ML-Training auf historischen Daten (kein 30d Redis TTL)
        - SQL-Analysen pro Backend/Dokumenttyp
        - Compliance-Anforderungen (Audit-Trail)
        """
        import uuid
        try:
            # Hole Document für company_id und document_type
            doc_query = select(Document).where(Document.id == feedback.document_id)
            doc_result = await self._db.execute(doc_query)
            doc = doc_result.scalar_one_or_none()

            if not doc:
                logger.warning(
                    "feedback_document_not_found",
                    document_id=str(feedback.document_id),
                )
                return None

            # Bestimme Korrektur-Typ
            correction_type = CorrectionType.TEXT
            if feedback.correction_type == "amount":
                correction_type = CorrectionType.AMOUNT
            elif feedback.correction_type == "date":
                correction_type = CorrectionType.DATE
            elif feedback.correction_type == "entity":
                correction_type = CorrectionType.ENTITY

            # Berechne Edit-Distance (Levenshtein-Heuristik)
            edit_distance = self._calculate_edit_distance(
                feedback.original_value,
                feedback.corrected_value,
            )

            # Bestimme Fehler-Kategorie
            error_category = self._detect_error_category(
                feedback.original_value,
                feedback.corrected_value,
            )

            # Kalibrierte Confidence berechnen
            calibrated_confidence = self.get_calibrated_confidence(
                feedback.ocr_backend,
                feedback.field_name,
                feedback.original_confidence,
            )

            # Extrahiere Backend-Version aus OCR-Ergebnis
            backend_version = None
            ocr_result_query = select(OCRResult).where(
                and_(
                    OCRResult.document_id == feedback.document_id,
                    OCRResult.backend == feedback.ocr_backend,
                )
            ).order_by(OCRResult.created_at.desc()).limit(1)
            ocr_result = await self._db.execute(ocr_result_query)
            ocr_result_row = ocr_result.scalar_one_or_none()

            if ocr_result_row and ocr_result_row.detected_layout:
                # Backend-Version kann in detected_layout.metadata gespeichert sein
                layout_meta = ocr_result_row.detected_layout.get("metadata", {})
                backend_version = layout_meta.get("backend_version") or layout_meta.get("model_version")

            # Fallback: Version aus document_metadata extrahieren
            if not backend_version and doc.document_metadata:
                backend_version = doc.document_metadata.get("ocr_backend_version")

            # Erstelle Feedback-Eintrag
            db_feedback = OCRCorrectionFeedback(
                id=uuid.uuid4(),
                document_id=feedback.document_id,
                company_id=doc.company_id,
                user_id=feedback.user_id,
                backend=feedback.ocr_backend,
                backend_version=backend_version,
                field_name=feedback.field_name,
                original_value=feedback.original_value,
                corrected_value=feedback.corrected_value,
                correction_type=correction_type.value,
                confidence_before=feedback.original_confidence,
                confidence_after=calibrated_confidence,
                document_type=doc.document_type.value if doc.document_type else None,
                error_category=error_category,
                edit_distance=edit_distance,
                status=FeedbackStatus.PENDING.value,
                verification_source="user_correction",
                metadata={
                    "learning_mode": self._learning_mode.value,
                    "is_major_correction": feedback.is_major_correction,
                },
            )

            self._db.add(db_feedback)
            await self._db.flush()

            logger.info(
                "ocr_feedback_persisted_to_db",
                feedback_id=str(db_feedback.id),
                document_id=str(feedback.document_id),
                backend=feedback.ocr_backend,
                field=feedback.field_name,
                error_category=error_category,
            )

            return db_feedback.id

        except Exception as e:
            logger.error(
                "failed_to_persist_feedback_to_db",
                **safe_error_log(e),
                document_id=str(feedback.document_id),
            )
            return None

    def _calculate_edit_distance(self, original: str, corrected: str) -> int:
        """
        Berechne Levenshtein Edit-Distance.

        Vereinfachte Implementierung für Performance.
        """
        if not original:
            return len(corrected) if corrected else 0
        if not corrected:
            return len(original)

        # Einfache Implementierung (O(n*m))
        m, n = len(original), len(corrected)

        # Optimierung: Bei grossen Unterschieden abbrechen
        if abs(m - n) > 50:
            return abs(m - n)

        # Begrenze auf max 200 Zeichen für Performance
        original = original[:200]
        corrected = corrected[:200]
        m, n = len(original), len(corrected)

        # DP-Matrix
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                cost = 0 if original[i - 1] == corrected[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # Deletion
                    dp[i][j - 1] + 1,      # Insertion
                    dp[i - 1][j - 1] + cost  # Substitution
                )

        return dp[m][n]

    def _detect_error_category(self, original: str, corrected: str) -> Optional[str]:
        """
        Erkennt die Fehler-Kategorie basierend auf Original und Korrektur.

        Kategorien:
        - umlaut: Umlaut-Fehler (ae->ä, oe->ö, ue->ü)
        - digit_swap: Ziffern vertauscht (1<->7, 0<->O)
        - ocr_noise: Rauschen/Artefakte
        - case: Gross-/Kleinschreibung
        - spacing: Leerzeichen-Probleme
        - unknown: Nicht kategorisierbar
        """
        if not original or not corrected:
            return "unknown"

        original_lower = original.lower()
        corrected_lower = corrected.lower()

        # Umlaut-Erkennung
        umlaut_mappings = [
            ("ae", "ä"), ("oe", "ö"), ("ue", "ü"),
            ("ss", "ß"), ("Ae", "Ä"), ("Oe", "Ö"), ("Ue", "Ü"),
        ]
        for ascii_form, umlaut in umlaut_mappings:
            if ascii_form in original and umlaut in corrected:
                return "umlaut"
            if umlaut in original and ascii_form in corrected:
                return "umlaut"

        # Ziffern-Fehler
        digit_confusions = [
            ("0", "O"), ("0", "o"), ("1", "l"), ("1", "I"),
            ("5", "S"), ("8", "B"), ("6", "b"),
        ]
        for d1, d2 in digit_confusions:
            if d1 in original and d2 in corrected:
                return "digit_swap"
            if d2 in original and d1 in corrected:
                return "digit_swap"

        # Case-Unterschied
        if original_lower == corrected_lower and original != corrected:
            return "case"

        # Spacing-Unterschied
        if original.replace(" ", "") == corrected.replace(" ", ""):
            return "spacing"

        # OCR-Noise (Sonderzeichen, kurze Artefakte)
        noise_chars = set(".,;:!?'\"()[]{}<>|\\/@#$%^&*~`")
        if any(c in noise_chars for c in original) or len(original) <= 2:
            return "ocr_noise"

        return "unknown"

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
            traffic_split: Anteil Traffic für Kandidat (0.0 - 0.5)
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

        # Initialisiere Metriken für Kandidat
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
        document_id: Optional[UUID] = None,
    ) -> ModelVersion:
        """
        Wähle Modell-Version (für A/B Testing).

        Verwendet deterministisches Hashing basierend auf document_id,
        um konsistente A/B-Zuweisung pro Dokument zu gewährleisten.
        Dies ermöglicht reproduzierbare Tests.

        Args:
            test_id: Optional - Spezifischer Test
            document_id: Optional - Dokument-ID für deterministisches Routing

        Returns:
            Zu verwendende Modell-Version
        """
        import hashlib

        if self._active_ab_tests is None:
            return ModelVersion.BASELINE

        # Erzeuge deterministischen Hash-Wert (0-99) basierend auf document_id
        # Dies stellt sicher, dass dasselbe Dokument immer dieselbe Variante bekommt
        if document_id:
            hash_input = str(document_id).encode()
            hash_value = int(hashlib.md5(hash_input).hexdigest()[:8], 16) % 100
        else:
            # Fallback: Hash basierend auf aktuellem Timestamp (weniger deterministisch)
            # Nur verwenden wenn keine document_id verfügbar
            import time
            hash_input = f"{time.time_ns()}".encode()
            hash_value = int(hashlib.md5(hash_input).hexdigest()[:8], 16) % 100

        if test_id and test_id in self._active_ab_tests:
            config = self._active_ab_tests[test_id]
            # traffic_split ist 0.0-1.0, hash_value ist 0-99
            if hash_value < (config.traffic_split * 100):
                return config.candidate_version

        # Default: Baseline oder aktiver Test
        for config in self._active_ab_tests.values():
            if not config.is_expired:
                if hash_value < (config.traffic_split * 100):
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

        # Für Baseline (immer aktualisieren)
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

        # Prüfe Mindestsamples
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
        Beende A/B Test und führe Aktion aus.

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
        Prüfe ob automatischer Rollback noetig.

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
        """Führe Rollback durch."""
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

        # Zaehle OCR-Korrektur-Feedbacks aus DB (persistent)
        feedback_count_query = select(func.count(OCRCorrectionFeedback.id))
        feedback_count = (await self._db.execute(feedback_count_query)).scalar() or 0

        # Zaehle nach Status
        pending_query = select(func.count(OCRCorrectionFeedback.id)).where(
            OCRCorrectionFeedback.status == FeedbackStatus.PENDING.value
        )
        pending_count = (await self._db.execute(pending_query)).scalar() or 0

        processed_query = select(func.count(OCRCorrectionFeedback.id)).where(
            OCRCorrectionFeedback.status == FeedbackStatus.PROCESSED.value
        )
        processed_count = (await self._db.execute(processed_query)).scalar() or 0

        # Alte Korrektur-Statistiken (OCRValidationCorrection)
        correction_query = select(func.count(OCRValidationCorrection.id))
        correction_count = (await self._db.execute(correction_query)).scalar() or 0

        # Backend-Statistiken aus DB
        backend_stats = await self._get_backend_stats_from_db()

        return {
            "learning_mode": self._learning_mode.value,
            "training_samples": feedback_count,
            "total_corrections": correction_count,
            "total_feedbacks": feedback_count,
            "pending_feedbacks": pending_count,
            "processed_feedbacks": processed_count,
            "legacy_corrections": correction_count,
            "backend_adjustments": (self._backend_adjustments or {}).copy(),
            "field_adjustments": {k: dict(v) for k, v in (self._field_adjustments or {}).items()},
            "backend_stats": backend_stats,
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

    async def _get_backend_stats_from_db(self) -> Dict[str, Any]:
        """
        Hole Backend-Statistiken aus OCRCorrectionFeedback Tabelle.

        Returns:
            Dictionary mit Backend-spezifischen Statistiken
        """
        try:
            # Aggregiere nach Backend
            stats_query = (
                select(
                    OCRCorrectionFeedback.backend,
                    func.count(OCRCorrectionFeedback.id).label("total"),
                    func.avg(OCRCorrectionFeedback.confidence_before).label("avg_conf_before"),
                    func.avg(OCRCorrectionFeedback.confidence_after).label("avg_conf_after"),
                    func.count(OCRCorrectionFeedback.id).filter(
                        OCRCorrectionFeedback.error_category == "umlaut"
                    ).label("umlaut_errors"),
                    func.count(OCRCorrectionFeedback.id).filter(
                        OCRCorrectionFeedback.error_category == "digit_swap"
                    ).label("digit_errors"),
                )
                .group_by(OCRCorrectionFeedback.backend)
            )

            result = await self._db.execute(stats_query)
            rows = result.all()

            backend_stats = {}
            for row in rows:
                backend_stats[row.backend] = {
                    "total_corrections": row.total,
                    "avg_confidence_before": float(row.avg_conf_before) if row.avg_conf_before else None,
                    "avg_confidence_after": float(row.avg_conf_after) if row.avg_conf_after else None,
                    "umlaut_error_count": row.umlaut_errors,
                    "digit_error_count": row.digit_errors,
                }

            return backend_stats

        except Exception as e:
            logger.warning("failed_to_get_backend_stats", **safe_error_log(e))
            return {}

    async def calculate_backend_performance(
        self,
        backend: Optional[str] = None,
        period_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Berechne und persistiere Backend-Performance-Metriken.

        Args:
            backend: Optional - Filter auf spezifisches Backend
            period_days: Zeitraum in Tagen

        Returns:
            Liste mit Performance-Metriken pro Backend/Feld
        """
        import uuid
        from datetime import datetime, timezone

        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)
        period_end = datetime.now(timezone.utc)

        try:
            # Aggregiere Korrekturen
            query = (
                select(
                    OCRCorrectionFeedback.backend,
                    OCRCorrectionFeedback.field_name,
                    OCRCorrectionFeedback.document_type,
                    func.count(OCRCorrectionFeedback.id).label("total_corrections"),
                    func.avg(OCRCorrectionFeedback.confidence_before).label("avg_conf_before"),
                    func.count(OCRCorrectionFeedback.id).filter(
                        OCRCorrectionFeedback.error_category == "umlaut"
                    ).label("umlaut_errors"),
                    func.count(OCRCorrectionFeedback.id).filter(
                        OCRCorrectionFeedback.error_category == "digit_swap"
                    ).label("digit_errors"),
                )
                .where(
                    and_(
                        OCRCorrectionFeedback.created_at >= period_start,
                        OCRCorrectionFeedback.created_at <= period_end,
                    )
                )
                .group_by(
                    OCRCorrectionFeedback.backend,
                    OCRCorrectionFeedback.field_name,
                    OCRCorrectionFeedback.document_type,
                )
            )

            if backend:
                query = query.where(OCRCorrectionFeedback.backend == backend)

            result = await self._db.execute(query)
            rows = result.all()

            # Aggregiere Dokument-Zähler pro Backend/Dokumenttyp für correction_rate
            doc_count_query = (
                select(
                    Document.ocr_backend_used,
                    Document.document_type,
                    func.count(Document.id).label("doc_count"),
                )
                .where(
                    and_(
                        Document.processed_date >= period_start,
                        Document.processed_date <= period_end,
                        Document.ocr_backend_used.isnot(None),
                    )
                )
                .group_by(Document.ocr_backend_used, Document.document_type)
            )
            doc_count_result = await self._db.execute(doc_count_query)
            doc_counts = {
                (r.ocr_backend_used, str(r.document_type) if r.document_type else None): r.doc_count
                for r in doc_count_result.all()
            }

            performance_records = []

            for row in rows:
                total = row.total_corrections
                umlaut_rate = row.umlaut_errors / total if total > 0 else 0.0
                digit_rate = row.digit_errors / total if total > 0 else 0.0

                # Berechne empfohlene Confidence-Anpassung
                avg_conf = float(row.avg_conf_before) if row.avg_conf_before else 0.0
                # Mehr Korrekturen = niedrigere Confidence
                adjustment = -0.05 * (total / 100)  # -5% pro 100 Korrekturen

                # Hole Dokument-Anzahl für Backend/Dokumenttyp aus aggregierten Counts
                total_docs = doc_counts.get((row.backend, row.document_type), 0)
                # Berechne Korrekturrate (Korrekturen / Dokumente)
                correction_rate = (total / total_docs) if total_docs > 0 else 0.0

                # Erstelle oder aktualisiere Performance-Record
                perf_record = OCRBackendPerformance(
                    id=uuid.uuid4(),
                    backend=row.backend,
                    field_name=row.field_name,
                    document_type=row.document_type,
                    company_id=None,  # Global, nicht company-spezifisch
                    total_corrections=total,
                    total_documents=total_docs,
                    correction_rate=correction_rate,
                    avg_confidence_before=avg_conf,
                    avg_confidence_adjustment=adjustment,
                    umlaut_error_rate=umlaut_rate,
                    digit_error_rate=digit_rate,
                    period_start=period_start,
                    period_end=period_end,
                )

                # Upsert (Insert or Update)
                stmt = pg_insert(OCRBackendPerformance).values(
                    id=perf_record.id,
                    backend=perf_record.backend,
                    field_name=perf_record.field_name,
                    document_type=perf_record.document_type,
                    company_id=perf_record.company_id,
                    total_corrections=perf_record.total_corrections,
                    total_documents=perf_record.total_documents,
                    correction_rate=perf_record.correction_rate,
                    avg_confidence_before=perf_record.avg_confidence_before,
                    avg_confidence_adjustment=perf_record.avg_confidence_adjustment,
                    umlaut_error_rate=perf_record.umlaut_error_rate,
                    digit_error_rate=perf_record.digit_error_rate,
                    period_start=perf_record.period_start,
                    period_end=perf_record.period_end,
                ).on_conflict_do_update(
                    constraint="uq_backend_performance_period",
                    set_={
                        "total_corrections": perf_record.total_corrections,
                        "total_documents": perf_record.total_documents,
                        "correction_rate": perf_record.correction_rate,
                        "avg_confidence_before": perf_record.avg_confidence_before,
                        "avg_confidence_adjustment": perf_record.avg_confidence_adjustment,
                        "umlaut_error_rate": perf_record.umlaut_error_rate,
                        "digit_error_rate": perf_record.digit_error_rate,
                        "calculated_at": datetime.now(timezone.utc),
                    }
                )

                await self._db.execute(stmt)

                performance_records.append({
                    "backend": row.backend,
                    "field_name": row.field_name,
                    "document_type": row.document_type,
                    "total_corrections": total,
                    "avg_confidence_before": avg_conf,
                    "recommended_adjustment": adjustment,
                    "umlaut_error_rate": umlaut_rate,
                    "digit_error_rate": digit_rate,
                })

            await self._db.commit()

            logger.info(
                "backend_performance_calculated",
                records=len(performance_records),
                period_days=period_days,
            )

            return performance_records

        except Exception as e:
            logger.error("failed_to_calculate_backend_performance", **safe_error_log(e))
            await self._db.rollback()
            return []

    async def mark_feedbacks_processed(
        self,
        feedback_ids: List[UUID],
    ) -> int:
        """
        Markiere Feedbacks als verarbeitet.

        Args:
            feedback_ids: Liste von Feedback-IDs

        Returns:
            Anzahl aktualisierter Records
        """
        if not feedback_ids:
            return 0

        try:
            stmt = (
                update(OCRCorrectionFeedback)
                .where(OCRCorrectionFeedback.id.in_(feedback_ids))
                .values(
                    status=FeedbackStatus.PROCESSED.value,
                    processed_at=datetime.now(timezone.utc),
                )
            )

            result = await self._db.execute(stmt)
            await self._db.commit()

            logger.info(
                "feedbacks_marked_processed",
                count=result.rowcount,
            )

            return result.rowcount

        except Exception as e:
            logger.error("failed_to_mark_feedbacks_processed", **safe_error_log(e))
            await self._db.rollback()
            return 0

    async def get_pending_feedbacks(
        self,
        limit: int = 100,
        backend: Optional[str] = None,
    ) -> List[OCRCorrectionFeedback]:
        """
        Hole ausstehende Feedbacks für Batch-Verarbeitung.

        Args:
            limit: Maximale Anzahl
            backend: Optional - Filter auf Backend

        Returns:
            Liste von OCRCorrectionFeedback Objekten
        """
        try:
            query = (
                select(OCRCorrectionFeedback)
                .where(OCRCorrectionFeedback.status == FeedbackStatus.PENDING.value)
                .order_by(OCRCorrectionFeedback.created_at)
                .limit(limit)
            )

            if backend:
                query = query.where(OCRCorrectionFeedback.backend == backend)

            result = await self._db.execute(query)
            return list(result.scalars().all())

        except Exception as e:
            logger.error("failed_to_get_pending_feedbacks", **safe_error_log(e))
            return []


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
