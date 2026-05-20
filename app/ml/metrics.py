# -*- coding: utf-8 -*-
"""
Prometheus Metriken für ML-Routing.

Erfasst:
- Routing-Entscheidungen und Latenz
- Backend-Auslastung und Fehler
- Drift-Scores und Warnungen
- A/B Test Ergebnisse
- Modell-Performance

Feinpoliert und durchdacht - Observability für ML in Produktion.
"""

import inspect
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

# Thread-Safety für Singleton
_ml_metrics_lock = threading.Lock()

# Optional Prometheus integration
PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.info("prometheus_client nicht installiert - Metriken deaktiviert")


# =============================================================================
# Metric Definitions
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Registry für alle ML-Metriken
    ML_REGISTRY = CollectorRegistry()

    # -------------------------------------------------------------------------
    # Routing Metriken
    # -------------------------------------------------------------------------

    ROUTING_REQUESTS_TOTAL = Counter(
        "ml_routing_requests_total",
        "Gesamtzahl der Routing-Anfragen",
        ["method", "backend", "status"],
        registry=ML_REGISTRY,
    )

    ROUTING_LATENCY = Histogram(
        "ml_routing_latency_seconds",
        "Latenz der Routing-Entscheidung",
        ["method"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        registry=ML_REGISTRY,
    )

    ROUTING_CONFIDENCE = Histogram(
        "ml_routing_confidence",
        "Konfidenz der Routing-Entscheidung",
        ["backend"],
        buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Backend Metriken
    # -------------------------------------------------------------------------

    BACKEND_REQUESTS_TOTAL = Counter(
        "ocr_backend_requests_total",
        "Gesamtzahl der Backend-Anfragen",
        ["backend", "status", "language"],
        registry=ML_REGISTRY,
    )

    BACKEND_PROCESSING_TIME = Histogram(
        "ocr_backend_processing_seconds",
        "Verarbeitungszeit pro Backend",
        ["backend"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        registry=ML_REGISTRY,
    )

    BACKEND_ACCURACY = Histogram(
        "ocr_backend_accuracy",
        "OCR-Genauigkeit pro Backend",
        ["backend", "document_type"],
        buckets=[0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.99],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Ground-Truth Quality Metriken (NEU)
    # -------------------------------------------------------------------------

    OCR_CER = Histogram(
        "ocr_character_error_rate",
        "Character Error Rate (CER) für OCR-Ergebnisse",
        ["backend", "document_type"],
        buckets=[0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5],
        registry=ML_REGISTRY,
    )

    OCR_WER = Histogram(
        "ocr_word_error_rate",
        "Word Error Rate (WER) für OCR-Ergebnisse",
        ["backend", "document_type"],
        buckets=[0.01, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5],
        registry=ML_REGISTRY,
    )

    OCR_UMLAUT_ACCURACY = Histogram(
        "ocr_umlaut_accuracy",
        "Deutsche Umlaut-Erkennungsgenauigkeit",
        ["backend"],
        buckets=[0.8, 0.85, 0.9, 0.95, 0.97, 0.99, 1.0],
        registry=ML_REGISTRY,
    )

    OCR_BENCHMARK_SAMPLES = Counter(
        "ocr_benchmark_samples_total",
        "Anzahl der Benchmark-Samples pro Backend",
        ["backend", "document_type", "difficulty"],
        registry=ML_REGISTRY,
    )

    BACKEND_QUEUE_SIZE = Gauge(
        "ocr_backend_queue_size",
        "Aktuelle Queue-Größe pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    BACKEND_ACTIVE_REQUESTS = Gauge(
        "ocr_backend_active_requests",
        "Aktive Anfragen pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # OCR Backend Health & Fallback Metriken (NEU - Infrastructure Hardening)
    # -------------------------------------------------------------------------

    OCR_BACKEND_HEALTHY = Gauge(
        "ablage_ocr_backend_healthy",
        "OCR Backend Health Status (1=healthy, 0=unhealthy)",
        ["backend"],
        registry=ML_REGISTRY,
    )

    OCR_QUEUE_LENGTH = Gauge(
        "ablage_ocr_queue_length",
        "Anzahl der Dokumente in der OCR-Verarbeitungs-Queue",
        registry=ML_REGISTRY,
    )

    OCR_FALLBACKS_TOTAL = Counter(
        "ablage_ocr_fallbacks_total",
        "Gesamtzahl der OCR Backend-Fallbacks",
        ["from_backend", "to_backend"],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Confidence Calibration Metriken
    # -------------------------------------------------------------------------

    CALIBRATION_ECE = Gauge(
        "ocr_calibration_ece",
        "Expected Calibration Error (ECE) pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    CALIBRATION_MCE = Gauge(
        "ocr_calibration_mce",
        "Maximum Calibration Error (MCE) pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    CALIBRATION_BRIER_SCORE = Gauge(
        "ocr_calibration_brier_score",
        "Brier Score pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    CALIBRATION_SAMPLES = Counter(
        "ocr_calibration_samples_total",
        "Gesamtzahl der Kalibrierungssamples",
        ["backend", "is_correct"],
        registry=ML_REGISTRY,
    )

    CALIBRATION_OVERCONFIDENCE = Gauge(
        "ocr_calibration_overconfidence_ratio",
        "Anteil überconfidenter Vorhersagen pro Backend",
        ["backend"],
        registry=ML_REGISTRY,
    )

    CALIBRATION_LAST_RETRAIN = Gauge(
        "ocr_calibration_last_retrain_timestamp",
        "Zeitstempel des letzten Calibration-Retrainings",
        ["backend"],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Drift Metriken
    # -------------------------------------------------------------------------

    DRIFT_SCORE = Gauge(
        "ml_drift_score",
        "Aktueller Drift-Score",
        ["feature"],
        registry=ML_REGISTRY,
    )

    DRIFT_OVERALL = Gauge(
        "ml_drift_overall_score",
        "Gesamter Drift-Score",
        registry=ML_REGISTRY,
    )

    DRIFT_ALERTS = Counter(
        "ml_drift_alerts_total",
        "Anzahl der Drift-Warnungen",
        ["severity"],
        registry=ML_REGISTRY,
    )

    DRIFT_LAST_CHECK = Gauge(
        "ml_drift_last_check_timestamp",
        "Zeitstempel der letzten Drift-Prüfung",
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # A/B Test Metriken
    # -------------------------------------------------------------------------

    AB_EXPERIMENT_SAMPLES = Counter(
        "ml_ab_experiment_samples_total",
        "Gesamtzahl der Experiment-Samples",
        ["experiment_id", "variant"],
        registry=ML_REGISTRY,
    )

    AB_EXPERIMENT_CONVERSIONS = Counter(
        "ml_ab_experiment_conversions_total",
        "Erfolgreiche Conversions pro Variante",
        ["experiment_id", "variant"],
        registry=ML_REGISTRY,
    )

    AB_ACTIVE_EXPERIMENTS = Gauge(
        "ml_ab_active_experiments",
        "Anzahl aktiver Experimente",
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Modell Metriken
    # -------------------------------------------------------------------------

    MODEL_VERSION = Info(
        "ml_model_version",
        "Aktive Modell-Version",
        registry=ML_REGISTRY,
    )

    MODEL_PREDICTIONS_TOTAL = Counter(
        "ml_model_predictions_total",
        "Gesamtzahl der Modell-Vorhersagen",
        ["model_name", "prediction"],
        registry=ML_REGISTRY,
    )

    MODEL_INFERENCE_TIME = Histogram(
        "ml_model_inference_seconds",
        "Inferenz-Zeit des ML-Modells",
        ["model_name"],
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # GPU Metriken (für ML-Modelle)
    # -------------------------------------------------------------------------

    GPU_MEMORY_USED = Gauge(
        "ml_gpu_memory_used_bytes",
        "Verwendeter GPU-Speicher",
        ["device"],
        registry=ML_REGISTRY,
    )

    GPU_MEMORY_TOTAL = Gauge(
        "ml_gpu_memory_total_bytes",
        "Gesamt GPU-Speicher",
        ["device"],
        registry=ML_REGISTRY,
    )

    GPU_UTILIZATION = Gauge(
        "ml_gpu_utilization_percent",
        "GPU-Auslastung in Prozent",
        ["device"],
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Surya Continuous Improvement Metriken
    # -------------------------------------------------------------------------

    # Aktive Model-Version
    SURYA_MODEL_VERSION_INFO = Info(
        "surya_model_version",
        "Aktive Surya Model-Version",
        registry=ML_REGISTRY,
    )

    SURYA_MODEL_VERSION_ACTIVE = Gauge(
        "surya_model_version_active",
        "Aktivierte Surya-Version (1=aktiv, 0=inaktiv)",
        ["version"],
        registry=ML_REGISTRY,
    )

    # Qualitäts-Gauges für aktives Modell
    SURYA_CER_GAUGE = Gauge(
        "surya_cer",
        "Character Error Rate des aktiven Surya-Modells",
        registry=ML_REGISTRY,
    )

    SURYA_WER_GAUGE = Gauge(
        "surya_wer",
        "Word Error Rate des aktiven Surya-Modells",
        registry=ML_REGISTRY,
    )

    SURYA_UMLAUT_ACCURACY_GAUGE = Gauge(
        "surya_umlaut_accuracy",
        "Umlaut-Genauigkeit des aktiven Surya-Modells (Ziel: 100%)",
        registry=ML_REGISTRY,
    )

    SURYA_ESZETT_ACCURACY_GAUGE = Gauge(
        "surya_eszett_accuracy",
        "Eszett (SS) Genauigkeit des aktiven Surya-Modells",
        registry=ML_REGISTRY,
    )

    # Training Metriken
    SURYA_TRAINING_RUNS_TOTAL = Counter(
        "surya_training_runs_total",
        "Gesamtzahl der Surya Training-Durchlaeufe",
        ["status", "trigger_reason"],
        registry=ML_REGISTRY,
    )

    SURYA_TRAINING_SAMPLES_TOTAL = Counter(
        "surya_training_samples_total",
        "Gesamtzahl der Surya Training-Samples",
        ["sample_type"],  # umlaut, fraktur, normal
        registry=ML_REGISTRY,
    )

    SURYA_TRAINING_EPOCHS_TOTAL = Counter(
        "surya_training_epochs_total",
        "Gesamtzahl der trainierten Epochen",
        registry=ML_REGISTRY,
    )

    SURYA_TRAINING_DURATION = Histogram(
        "surya_training_duration_seconds",
        "Dauer eines Surya Training-Durchlaufs",
        buckets=[60, 300, 600, 1800, 3600, 7200, 14400],  # 1min bis 4h
        registry=ML_REGISTRY,
    )

    SURYA_TRAINING_LOSS = Gauge(
        "surya_training_loss",
        "Aktueller Training-Loss",
        ["loss_type"],  # training, validation
        registry=ML_REGISTRY,
    )

    # Retraining Trigger Metriken
    SURYA_RETRAINING_CHECKS_TOTAL = Counter(
        "surya_retraining_checks_total",
        "Anzahl der Retraining-Condition-Checks",
        registry=ML_REGISTRY,
    )

    SURYA_RETRAINING_TRIGGERED_TOTAL = Counter(
        "surya_retraining_triggered_total",
        "Anzahl der ausgeloesten Retrainings",
        ["reason"],  # correction_threshold, quality_degradation, scheduled, manual
        registry=ML_REGISTRY,
    )

    SURYA_CORRECTIONS_PENDING = Gauge(
        "surya_corrections_pending",
        "Anzahl ausstehender Korrekturen für Surya",
        registry=ML_REGISTRY,
    )

    SURYA_CORRECTIONS_PROCESSED_TOTAL = Counter(
        "surya_corrections_processed_total",
        "Anzahl verarbeiteter Surya-Korrekturen",
        ["correction_type"],  # umlaut, date, amount, general
        registry=ML_REGISTRY,
    )

    # A/B Testing Metriken
    SURYA_AB_TESTS_ACTIVE = Gauge(
        "surya_ab_tests_active",
        "Anzahl aktiver Surya A/B Tests",
        registry=ML_REGISTRY,
    )

    SURYA_AB_TEST_SAMPLES = Counter(
        "surya_ab_test_samples_total",
        "Anzahl Samples pro A/B Test Gruppe",
        ["test_id", "group"],  # control, treatment
        registry=ML_REGISTRY,
    )

    SURYA_AB_TEST_DECISIONS = Counter(
        "surya_ab_test_decisions_total",
        "Anzahl A/B Test Entscheidungen",
        ["winner"],  # control, treatment, inconclusive
        registry=ML_REGISTRY,
    )

    # Rollback Metriken
    SURYA_ROLLBACKS_TOTAL = Counter(
        "surya_rollbacks_total",
        "Anzahl der Surya Model Rollbacks",
        ["reason"],  # umlaut_degradation, cer_increase, manual
        registry=ML_REGISTRY,
    )

    SURYA_ROLLBACK_LAST_TIMESTAMP = Gauge(
        "surya_rollback_last_timestamp",
        "Zeitstempel des letzten Rollbacks",
        registry=ML_REGISTRY,
    )

    # Benchmark Metriken
    SURYA_BENCHMARK_RUNS_TOTAL = Counter(
        "surya_benchmark_runs_total",
        "Anzahl der Surya Benchmark-Durchlaeufe",
        ["benchmark_type"],  # full, umlaut_focus, quick
        registry=ML_REGISTRY,
    )

    SURYA_BENCHMARK_DURATION = Histogram(
        "surya_benchmark_duration_seconds",
        "Dauer eines Benchmark-Durchlaufs",
        buckets=[10, 30, 60, 120, 300, 600],
        registry=ML_REGISTRY,
    )

    # Model Versioning Metriken
    SURYA_VERSIONS_TOTAL = Gauge(
        "surya_versions_total",
        "Gesamtzahl der Surya Model-Versionen",
        registry=ML_REGISTRY,
    )

    SURYA_CHECKPOINT_SIZE_MB = Gauge(
        "surya_checkpoint_size_mb",
        "Gesamtgröße aller Surya Checkpoints in MB",
        registry=ML_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # OCR-spezifische Metrics (Phase 2 Enterprise)
    # -------------------------------------------------------------------------

    OCR_INFERENCE_TIME = Histogram(
        "ocr_inference_time_seconds",
        "Inference time for OCR processing (token generation)",
        ["backend"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        registry=ML_REGISTRY,
    )

    OCR_GPU_VRAM_ALLOCATED = Gauge(
        "ocr_gpu_vram_allocated_bytes",
        "VRAM currently allocated for OCR processing",
        ["backend"],
        registry=ML_REGISTRY,
    )

    OCR_CONFIDENCE_SCORE = Histogram(
        "ocr_confidence_score",
        "OCR confidence score distribution",
        ["backend"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
        registry=ML_REGISTRY,
    )

    OCR_FALLBACK_COUNT = Counter(
        "ocr_fallback_count",
        "Number of OCR backend fallbacks",
        ["from_backend", "to_backend", "reason"],
        registry=ML_REGISTRY,
    )

    OCR_OOM_ERRORS_TOTAL = Counter(
        "ocr_oom_errors_total",
        "Total GPU out-of-memory errors during OCR",
        ["backend"],
        registry=ML_REGISTRY,
    )

    OCR_POSTPROCESSOR_ERRORS_TOTAL = Counter(
        "ocr_postprocessor_errors_total",
        "Total errors during OCR text postprocessing",
        ["backend", "postprocessor"],
        registry=ML_REGISTRY,
    )


# =============================================================================
# Metric Recording Functions
# =============================================================================

class MLMetrics:
    """
    Zentrale Klasse für ML-Metriken.

    Kapselt alle Prometheus-Operationen und bietet
    Fallback wenn Prometheus nicht verfügbar.
    """

    def __init__(self) -> None:
        """Initialisiere MLMetrics."""
        self.enabled = PROMETHEUS_AVAILABLE
        self._backend_active: Dict[str, int] = {}

        if self.enabled:
            logger.info("Prometheus ML-Metriken aktiviert")
        else:
            logger.info("Prometheus nicht verfügbar - Metriken nur als Logs")

    # -------------------------------------------------------------------------
    # Routing Metriken
    # -------------------------------------------------------------------------

    def record_routing_request(
        self,
        method: str,
        backend: str,
        status: str,
        latency_seconds: float,
        confidence: float,
    ) -> None:
        """
        Erfasse Routing-Anfrage.

        Args:
            method: Routing-Methode (ml, rule_based, fallback)
            backend: Gewähltes Backend
            status: success oder error
            latency_seconds: Latenz in Sekunden
            confidence: Konfidenz der Entscheidung
        """
        if self.enabled:
            ROUTING_REQUESTS_TOTAL.labels(
                method=method, backend=backend, status=status
            ).inc()
            ROUTING_LATENCY.labels(method=method).observe(latency_seconds)
            ROUTING_CONFIDENCE.labels(backend=backend).observe(confidence)
        else:
            logger.debug(
                f"Routing: {method} -> {backend} ({status}), "
                f"latency={latency_seconds:.3f}s, confidence={confidence:.2f}"
            )

    @contextmanager
    def measure_routing_time(self, method: str):
        """Context Manager zur Zeitmessung."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            if self.enabled:
                ROUTING_LATENCY.labels(method=method).observe(duration)

    # -------------------------------------------------------------------------
    # Backend Metriken
    # -------------------------------------------------------------------------

    def record_backend_request(
        self,
        backend: str,
        status: str,
        language: str,
        processing_time: float,
        accuracy: Optional[float] = None,
        document_type: str = "unknown",
    ) -> None:
        """
        Erfasse Backend-Anfrage.

        Args:
            backend: Backend-Name
            status: success oder error
            language: Dokumentsprache
            processing_time: Verarbeitungszeit in Sekunden
            accuracy: OCR-Genauigkeit (optional)
            document_type: Dokumenttyp
        """
        if self.enabled:
            BACKEND_REQUESTS_TOTAL.labels(
                backend=backend, status=status, language=language
            ).inc()
            BACKEND_PROCESSING_TIME.labels(backend=backend).observe(processing_time)

            if accuracy is not None:
                BACKEND_ACCURACY.labels(
                    backend=backend, document_type=document_type
                ).observe(accuracy)
        else:
            logger.debug(
                f"Backend {backend}: {status}, "
                f"time={processing_time:.2f}s, accuracy={accuracy}"
            )

    def record_quality_metrics(
        self,
        backend: str,
        cer: float,
        wer: float,
        umlaut_accuracy: float,
        document_type: str = "unknown",
        difficulty: str = "medium",
    ) -> None:
        """
        Erfasse Ground-Truth-basierte Qualitätsmetriken.

        Args:
            backend: Backend-Name
            cer: Character Error Rate (0-1)
            wer: Word Error Rate (0-1)
            umlaut_accuracy: Umlaut-Genauigkeit (0-1)
            document_type: Dokumenttyp
            difficulty: Schwierigkeitsgrad
        """
        if self.enabled:
            OCR_CER.labels(
                backend=backend, document_type=document_type
            ).observe(cer)
            OCR_WER.labels(
                backend=backend, document_type=document_type
            ).observe(wer)
            OCR_UMLAUT_ACCURACY.labels(
                backend=backend
            ).observe(umlaut_accuracy)
            OCR_BENCHMARK_SAMPLES.labels(
                backend=backend,
                document_type=document_type,
                difficulty=difficulty,
            ).inc()
        else:
            logger.debug(
                f"Quality metrics: {backend} CER={cer:.4f}, "
                f"WER={wer:.4f}, Umlaut={umlaut_accuracy:.4f}"
            )

    def set_backend_queue_size(self, backend: str, size: int) -> None:
        """Setze aktuelle Queue-Größe."""
        if self.enabled:
            BACKEND_QUEUE_SIZE.labels(backend=backend).set(size)

    # -------------------------------------------------------------------------
    # OCR Backend Health & Fallback Metriken
    # -------------------------------------------------------------------------

    def set_backend_healthy(self, backend: str, healthy: bool) -> None:
        """
        Setze Health-Status für OCR Backend.

        Args:
            backend: Backend-Name (deepseek, got_ocr, surya, etc.)
            healthy: True wenn Backend gesund, False sonst
        """
        if self.enabled:
            OCR_BACKEND_HEALTHY.labels(backend=backend).set(1 if healthy else 0)
        else:
            logger.debug("backend_health_status", backend=backend, healthy=healthy)

    def set_ocr_queue_length(self, length: int) -> None:
        """
        Setze aktuelle OCR Queue-Länge.

        Args:
            length: Anzahl der Dokumente in der Queue
        """
        if self.enabled:
            OCR_QUEUE_LENGTH.set(length)
        else:
            logger.debug("ocr_queue_length", length=length)

    def record_backend_fallback(self, from_backend: str, to_backend: str) -> None:
        """
        Erfasse OCR Backend-Fallback.

        Args:
            from_backend: Original Backend das fehlgeschlagen ist
            to_backend: Fallback Backend das verwendet wird
        """
        if self.enabled:
            OCR_FALLBACKS_TOTAL.labels(
                from_backend=from_backend,
                to_backend=to_backend,
            ).inc()
            logger.info(
                "ocr_backend_fallback",
                from_backend=from_backend,
                to_backend=to_backend,
            )
        else:
            logger.warning(
                "ocr_backend_fallback",
                from_backend=from_backend,
                to_backend=to_backend,
            )

    def inc_backend_active(self, backend: str) -> None:
        """Erhöhe aktive Anfragen."""
        self._backend_active[backend] = self._backend_active.get(backend, 0) + 1
        if self.enabled:
            BACKEND_ACTIVE_REQUESTS.labels(backend=backend).inc()

    def dec_backend_active(self, backend: str) -> None:
        """Verringere aktive Anfragen."""
        self._backend_active[backend] = max(0, self._backend_active.get(backend, 0) - 1)
        if self.enabled:
            BACKEND_ACTIVE_REQUESTS.labels(backend=backend).dec()

    @contextmanager
    def track_backend_request(self, backend: str, language: str = "de"):
        """Context Manager für Backend-Tracking."""
        self.inc_backend_active(backend)
        start = time.time()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            self.dec_backend_active(backend)
            duration = time.time() - start
            self.record_backend_request(
                backend=backend,
                status=status,
                language=language,
                processing_time=duration,
            )

    # -------------------------------------------------------------------------
    # Drift Metriken
    # -------------------------------------------------------------------------

    def record_drift_score(
        self,
        overall_score: float,
        feature_scores: Dict[str, float],
        severity: str,
    ) -> None:
        """
        Erfasse Drift-Scores.

        Args:
            overall_score: Gesamter Drift-Score
            feature_scores: Scores pro Feature
            severity: Schweregrad
        """
        if self.enabled:
            DRIFT_OVERALL.set(overall_score)
            DRIFT_LAST_CHECK.set_to_current_time()

            for feature, score in feature_scores.items():
                DRIFT_SCORE.labels(feature=feature).set(score)

            if severity != "none":
                DRIFT_ALERTS.labels(severity=severity).inc()
        else:
            logger.info("drift_score_recorded", overall_score=round(overall_score, 3), severity=severity)

    # -------------------------------------------------------------------------
    # Confidence Calibration Metriken
    # -------------------------------------------------------------------------

    def record_calibration_sample(
        self,
        backend: str,
        is_correct: bool,
    ) -> None:
        """
        Erfasse Kalibrierungssample.

        Args:
            backend: Backend-Name
            is_correct: War die OCR-Vorhersage korrekt?
        """
        if self.enabled:
            CALIBRATION_SAMPLES.labels(
                backend=backend,
                is_correct=str(is_correct).lower(),
            ).inc()
        else:
            logger.debug("calibration_sample", backend=backend, is_correct=is_correct)

    def update_calibration_metrics(
        self,
        backend: str,
        ece: float,
        mce: float,
        brier_score: float,
        overconfidence_ratio: float,
    ) -> None:
        """
        Aktualisiere Calibration-Metriken für ein Backend.

        Args:
            backend: Backend-Name
            ece: Expected Calibration Error
            mce: Maximum Calibration Error
            brier_score: Brier Score
            overconfidence_ratio: Anteil überconfidenter Vorhersagen
        """
        if self.enabled:
            CALIBRATION_ECE.labels(backend=backend).set(ece)
            CALIBRATION_MCE.labels(backend=backend).set(mce)
            CALIBRATION_BRIER_SCORE.labels(backend=backend).set(brier_score)
            CALIBRATION_OVERCONFIDENCE.labels(backend=backend).set(overconfidence_ratio)
            CALIBRATION_LAST_RETRAIN.labels(backend=backend).set_to_current_time()
        else:
            logger.info(
                "calibration_metrics_updated",
                backend=backend,
                ece=round(ece, 4),
                mce=round(mce, 4),
                brier_score=round(brier_score, 4),
            )

    # -------------------------------------------------------------------------
    # A/B Test Metriken
    # -------------------------------------------------------------------------

    def record_ab_sample(
        self,
        experiment_id: str,
        variant: str,
        success: bool,
    ) -> None:
        """
        Erfasse A/B Test Sample.

        Args:
            experiment_id: Experiment-ID
            variant: Varianten-Name
            success: Erfolgreiche Conversion?
        """
        if self.enabled:
            AB_EXPERIMENT_SAMPLES.labels(
                experiment_id=experiment_id, variant=variant
            ).inc()

            if success:
                AB_EXPERIMENT_CONVERSIONS.labels(
                    experiment_id=experiment_id, variant=variant
                ).inc()
        else:
            logger.debug("ab_sample_recorded", experiment_id=experiment_id, variant=variant, success=success)

    def set_active_experiments(self, count: int) -> None:
        """Setze Anzahl aktiver Experimente."""
        if self.enabled:
            AB_ACTIVE_EXPERIMENTS.set(count)

    # -------------------------------------------------------------------------
    # Modell Metriken
    # -------------------------------------------------------------------------

    def set_model_version(self, version: str, model_name: str = "ocr_router") -> None:
        """Setze aktive Modell-Version."""
        if self.enabled:
            MODEL_VERSION.info({
                "version": version,
                "model_name": model_name,
            })

    def record_model_prediction(
        self,
        model_name: str,
        prediction: str,
        inference_time: float,
    ) -> None:
        """
        Erfasse Modell-Vorhersage.

        Args:
            model_name: Modell-Name
            prediction: Vorhersage
            inference_time: Inferenz-Zeit in Sekunden
        """
        if self.enabled:
            MODEL_PREDICTIONS_TOTAL.labels(
                model_name=model_name, prediction=prediction
            ).inc()
            MODEL_INFERENCE_TIME.labels(model_name=model_name).observe(inference_time)

    @contextmanager
    def measure_inference_time(self, model_name: str):
        """Context Manager für Inferenz-Zeitmessung."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            if self.enabled:
                MODEL_INFERENCE_TIME.labels(model_name=model_name).observe(duration)

    # -------------------------------------------------------------------------
    # GPU Metriken
    # -------------------------------------------------------------------------

    def update_gpu_metrics(self) -> None:
        """Aktualisiere GPU-Metriken."""
        if not self.enabled:
            return

        try:
            import torch


            if torch.cuda.is_available():
                for device_id in range(torch.cuda.device_count()):
                    device = f"cuda:{device_id}"

                    # Memory
                    mem_used = torch.cuda.memory_allocated(device_id)
                    mem_total = torch.cuda.get_device_properties(device_id).total_memory

                    GPU_MEMORY_USED.labels(device=device).set(mem_used)
                    GPU_MEMORY_TOTAL.labels(device=device).set(mem_total)

                    # Utilization (approximation based on memory)
                    utilization = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                    GPU_UTILIZATION.labels(device=device).set(utilization)

        except ImportError:
            pass
        except Exception as e:
            logger.debug("gpu_metriken_update_fehlgeschlagen", **safe_error_log(e))

    # -------------------------------------------------------------------------
    # Surya Continuous Improvement Metriken
    # -------------------------------------------------------------------------

    def update_surya_model_metrics(
        self,
        version: str,
        cer: float,
        wer: float,
        umlaut_accuracy: float,
        eszett_accuracy: Optional[float] = None,
        is_production: bool = False,
    ) -> None:
        """
        Aktualisiere Surya Model-Qualitätsmetriken.

        Args:
            version: Model-Version (z.B. "v1.2.3_20241215")
            cer: Character Error Rate (Ziel: < 0.03)
            wer: Word Error Rate (Ziel: < 0.08)
            umlaut_accuracy: Umlaut-Genauigkeit (Ziel: 1.0 = 100%)
            eszett_accuracy: Eszett (SS) Genauigkeit (optional)
            is_production: Ist dies das Produktions-Modell?
        """
        if self.enabled:
            # Model Info
            SURYA_MODEL_VERSION_INFO.info({
                "version": version,
                "is_production": str(is_production).lower(),
            })
            SURYA_MODEL_VERSION_ACTIVE.labels(version=version).set(1 if is_production else 0)

            # Qualitätsmetriken
            SURYA_CER_GAUGE.set(cer)
            SURYA_WER_GAUGE.set(wer)
            SURYA_UMLAUT_ACCURACY_GAUGE.set(umlaut_accuracy)

            if eszett_accuracy is not None:
                SURYA_ESZETT_ACCURACY_GAUGE.set(eszett_accuracy)

            logger.info(
                "surya_model_metrics_updated",
                version=version,
                cer=round(cer, 4),
                wer=round(wer, 4),
                umlaut_accuracy=round(umlaut_accuracy, 4),
                is_production=is_production,
            )
        else:
            logger.info(
                "surya_model_metrics",
                version=version,
                cer=round(cer, 4),
                wer=round(wer, 4),
                umlaut_accuracy=round(umlaut_accuracy, 4),
            )

    def record_surya_training_run(
        self,
        status: str,
        trigger_reason: str,
        duration_seconds: Optional[float] = None,
        epochs: int = 0,
    ) -> None:
        """
        Erfasse Surya Training-Durchlauf.

        Args:
            status: Status (completed, failed, cancelled)
            trigger_reason: Grund (scheduled, correction_threshold, quality_degradation, manual)
            duration_seconds: Dauer in Sekunden
            epochs: Anzahl der trainierten Epochen
        """
        if self.enabled:
            SURYA_TRAINING_RUNS_TOTAL.labels(
                status=status,
                trigger_reason=trigger_reason,
            ).inc()

            if duration_seconds is not None:
                SURYA_TRAINING_DURATION.observe(duration_seconds)

            if epochs > 0:
                SURYA_TRAINING_EPOCHS_TOTAL.inc(epochs)

            logger.info(
                "surya_training_run_recorded",
                status=status,
                trigger_reason=trigger_reason,
                duration_seconds=duration_seconds,
                epochs=epochs,
            )
        else:
            logger.info(
                "surya_training_run",
                status=status,
                trigger_reason=trigger_reason,
            )

    def record_surya_training_sample(
        self,
        sample_type: str,
        count: int = 1,
    ) -> None:
        """
        Erfasse Surya Training-Samples.

        Args:
            sample_type: Typ (umlaut, fraktur, normal)
            count: Anzahl der Samples
        """
        if self.enabled:
            SURYA_TRAINING_SAMPLES_TOTAL.labels(sample_type=sample_type).inc(count)
        else:
            logger.debug("surya_training_sample", sample_type=sample_type, count=count)

    def update_surya_training_loss(
        self,
        training_loss: float,
        validation_loss: Optional[float] = None,
    ) -> None:
        """
        Aktualisiere Surya Training-Loss.

        Args:
            training_loss: Aktueller Training-Loss
            validation_loss: Aktueller Validation-Loss
        """
        if self.enabled:
            SURYA_TRAINING_LOSS.labels(loss_type="training").set(training_loss)
            if validation_loss is not None:
                SURYA_TRAINING_LOSS.labels(loss_type="validation").set(validation_loss)
        else:
            logger.debug(
                "surya_training_loss",
                training_loss=round(training_loss, 4),
                validation_loss=round(validation_loss, 4) if validation_loss else None,
            )

    def record_surya_retraining_check(self) -> None:
        """Erfasse dass ein Retraining-Condition-Check durchgeführt wurde."""
        if self.enabled:
            SURYA_RETRAINING_CHECKS_TOTAL.inc()

    def record_surya_retraining_triggered(self, reason: str) -> None:
        """
        Erfasse dass ein Retraining getriggert wurde.

        Args:
            reason: Grund (correction_threshold, quality_degradation, scheduled, manual)
        """
        if self.enabled:
            SURYA_RETRAINING_TRIGGERED_TOTAL.labels(reason=reason).inc()
            logger.info("surya_retraining_triggered", reason=reason)
        else:
            logger.info("surya_retraining_triggered", reason=reason)

    def update_surya_corrections_pending(self, count: int) -> None:
        """
        Setze Anzahl ausstehender Surya-Korrekturen.

        Args:
            count: Anzahl der Korrekturen
        """
        if self.enabled:
            SURYA_CORRECTIONS_PENDING.set(count)

    def record_surya_correction_processed(self, correction_type: str) -> None:
        """
        Erfasse verarbeitete Surya-Korrektur.

        Args:
            correction_type: Typ (umlaut, date, amount, general)
        """
        if self.enabled:
            SURYA_CORRECTIONS_PROCESSED_TOTAL.labels(correction_type=correction_type).inc()
        else:
            logger.debug("surya_correction_processed", correction_type=correction_type)

    def set_surya_ab_tests_active(self, count: int) -> None:
        """
        Setze Anzahl aktiver Surya A/B Tests.

        Args:
            count: Anzahl aktiver Tests
        """
        if self.enabled:
            SURYA_AB_TESTS_ACTIVE.set(count)

    def record_surya_ab_test_sample(
        self,
        test_id: str,
        group: str,
    ) -> None:
        """
        Erfasse Sample für Surya A/B Test.

        Args:
            test_id: Test-ID
            group: Gruppe (control, treatment)
        """
        if self.enabled:
            SURYA_AB_TEST_SAMPLES.labels(test_id=test_id, group=group).inc()
        else:
            logger.debug("surya_ab_test_sample", test_id=test_id, group=group)

    def record_surya_ab_test_decision(self, winner: str) -> None:
        """
        Erfasse A/B Test Entscheidung.

        Args:
            winner: Gewinner (control, treatment, inconclusive)
        """
        if self.enabled:
            SURYA_AB_TEST_DECISIONS.labels(winner=winner).inc()
            logger.info("surya_ab_test_decision", winner=winner)
        else:
            logger.info("surya_ab_test_decision", winner=winner)

    def record_surya_rollback(self, reason: str) -> None:
        """
        Erfasse Surya Model Rollback.

        Args:
            reason: Grund (umlaut_degradation, cer_increase, manual)
        """
        if self.enabled:
            SURYA_ROLLBACKS_TOTAL.labels(reason=reason).inc()
            SURYA_ROLLBACK_LAST_TIMESTAMP.set_to_current_time()
            logger.warning("surya_rollback_recorded", reason=reason)
        else:
            logger.warning("surya_rollback", reason=reason)

    def record_surya_benchmark(
        self,
        benchmark_type: str,
        duration_seconds: float,
        cer: Optional[float] = None,
        wer: Optional[float] = None,
        umlaut_accuracy: Optional[float] = None,
    ) -> None:
        """
        Erfasse Surya Benchmark-Durchlauf.

        Args:
            benchmark_type: Typ (full, umlaut_focus, quick)
            duration_seconds: Dauer in Sekunden
            cer: Gemessene Character Error Rate
            wer: Gemessene Word Error Rate
            umlaut_accuracy: Gemessene Umlaut-Genauigkeit
        """
        if self.enabled:
            SURYA_BENCHMARK_RUNS_TOTAL.labels(benchmark_type=benchmark_type).inc()
            SURYA_BENCHMARK_DURATION.observe(duration_seconds)

            logger.info(
                "surya_benchmark_completed",
                benchmark_type=benchmark_type,
                duration_seconds=round(duration_seconds, 2),
                cer=round(cer, 4) if cer else None,
                wer=round(wer, 4) if wer else None,
                umlaut_accuracy=round(umlaut_accuracy, 4) if umlaut_accuracy else None,
            )
        else:
            logger.info(
                "surya_benchmark",
                benchmark_type=benchmark_type,
                duration_seconds=round(duration_seconds, 2),
            )

    def update_surya_versioning_metrics(
        self,
        total_versions: int,
        total_checkpoint_size_mb: float,
    ) -> None:
        """
        Aktualisiere Surya Versioning-Metriken.

        Args:
            total_versions: Gesamtzahl der Model-Versionen
            total_checkpoint_size_mb: Gesamtgröße aller Checkpoints in MB
        """
        if self.enabled:
            SURYA_VERSIONS_TOTAL.set(total_versions)
            SURYA_CHECKPOINT_SIZE_MB.set(total_checkpoint_size_mb)
        else:
            logger.debug(
                "surya_versioning_metrics",
                total_versions=total_versions,
                total_checkpoint_size_mb=round(total_checkpoint_size_mb, 2),
            )

    # -------------------------------------------------------------------------
    # OCR Phase 2 Metriken
    # -------------------------------------------------------------------------

    def record_ocr_inference_time(
        self,
        backend: str,
        inference_time_seconds: float,
    ) -> None:
        """
        Erfasse OCR Inference-Zeit.

        Args:
            backend: Backend-Name (deepseek, surya, got_ocr)
            inference_time_seconds: Inferenz-Zeit in Sekunden
        """
        if self.enabled:
            OCR_INFERENCE_TIME.labels(backend=backend).observe(inference_time_seconds)
        else:
            logger.debug(
                "ocr_inference_time",
                backend=backend,
                inference_time_seconds=round(inference_time_seconds, 3),
            )

    def set_ocr_gpu_vram_allocated(
        self,
        backend: str,
        vram_bytes: int,
    ) -> None:
        """
        Setze aktuell allokierten VRAM für OCR Backend.

        Args:
            backend: Backend-Name
            vram_bytes: VRAM in Bytes
        """
        if self.enabled:
            OCR_GPU_VRAM_ALLOCATED.labels(backend=backend).set(vram_bytes)
        else:
            logger.debug(
                "ocr_gpu_vram_allocated",
                backend=backend,
                vram_mb=round(vram_bytes / (1024 * 1024), 2),
            )

    def record_ocr_confidence_score(
        self,
        backend: str,
        confidence: float,
    ) -> None:
        """
        Erfasse OCR Confidence Score.

        Args:
            backend: Backend-Name
            confidence: Confidence Score (0.0 - 1.0)
        """
        if self.enabled:
            OCR_CONFIDENCE_SCORE.labels(backend=backend).observe(confidence)
        else:
            logger.debug(
                "ocr_confidence_score",
                backend=backend,
                confidence=round(confidence, 3),
            )

    def record_ocr_fallback(
        self,
        from_backend: str,
        to_backend: str,
        reason: str,
    ) -> None:
        """
        Erfasse OCR Backend-Fallback mit Grund.

        Args:
            from_backend: Original Backend
            to_backend: Fallback Backend
            reason: Grund für Fallback (oom, timeout, error)
        """
        if self.enabled:
            OCR_FALLBACK_COUNT.labels(
                from_backend=from_backend,
                to_backend=to_backend,
                reason=reason,
            ).inc()
            logger.info(
                "ocr_fallback_recorded",
                from_backend=from_backend,
                to_backend=to_backend,
                reason=reason,
            )
        else:
            logger.warning(
                "ocr_fallback",
                from_backend=from_backend,
                to_backend=to_backend,
                reason=reason,
            )

    def record_ocr_oom_error(self, backend: str) -> None:
        """
        Erfasse GPU Out-of-Memory Fehler.

        Args:
            backend: Backend das OOM hatte
        """
        if self.enabled:
            OCR_OOM_ERRORS_TOTAL.labels(backend=backend).inc()
            logger.error(
                "ocr_oom_error_recorded",
                backend=backend,
            )
        else:
            logger.error(
                "ocr_oom_error",
                backend=backend,
            )

    def record_ocr_postprocessor_error(
        self,
        backend: str,
        postprocessor: str,
    ) -> None:
        """
        Erfasse Postprocessor-Fehler.

        Args:
            backend: OCR Backend
            postprocessor: Name des Postprocessors (german_text, etc.)
        """
        if self.enabled:
            OCR_POSTPROCESSOR_ERRORS_TOTAL.labels(
                backend=backend,
                postprocessor=postprocessor,
            ).inc()
            logger.warning(
                "ocr_postprocessor_error_recorded",
                backend=backend,
                postprocessor=postprocessor,
            )
        else:
            logger.warning(
                "ocr_postprocessor_error",
                backend=backend,
                postprocessor=postprocessor,
            )

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def get_metrics(self) -> bytes:
        """Hole alle Metriken als Prometheus-Format."""
        if self.enabled:
            return generate_latest(ML_REGISTRY)
        else:
            return b"# Prometheus not available\n"

    def get_content_type(self) -> str:
        """Hole Content-Type für Metriken."""
        if self.enabled:
            return CONTENT_TYPE_LATEST
        else:
            return "text/plain"


# Singleton instance
_ml_metrics: Optional[MLMetrics] = None


def get_ml_metrics() -> MLMetrics:
    """Hole globale MLMetrics Instanz (thread-safe)."""
    global _ml_metrics
    if _ml_metrics is not None:
        return _ml_metrics
    with _ml_metrics_lock:
        if _ml_metrics is None:
            logger.info("ml_metrics_initialisierung")
            _ml_metrics = MLMetrics()
    return _ml_metrics


# =============================================================================
# Decorators
# =============================================================================

def track_routing(method: str = "unknown"):
    """Decorator zum Tracking von Routing-Funktionen."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = get_ml_metrics()
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                # Extract info from result if possible
                backend = getattr(result, 'backend', 'unknown')
                if hasattr(backend, 'value'):
                    backend = backend.value
                confidence = getattr(result, 'confidence', 0.0)

                metrics.record_routing_request(
                    method=method,
                    backend=str(backend),
                    status="success",
                    latency_seconds=duration,
                    confidence=confidence,
                )
                return result
            except Exception as e:
                duration = time.time() - start
                metrics.record_routing_request(
                    method=method,
                    backend="error",
                    status="error",
                    latency_seconds=duration,
                    confidence=0.0,
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            metrics = get_ml_metrics()
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start

                backend = getattr(result, 'backend', 'unknown')
                if hasattr(backend, 'value'):
                    backend = backend.value
                confidence = getattr(result, 'confidence', 0.0)

                metrics.record_routing_request(
                    method=method,
                    backend=str(backend),
                    status="success",
                    latency_seconds=duration,
                    confidence=confidence,
                )
                return result
            except Exception:
                duration = time.time() - start
                metrics.record_routing_request(
                    method=method,
                    backend="error",
                    status="error",
                    latency_seconds=duration,
                    confidence=0.0,
                )
                raise

        if hasattr(func, '__wrapped__'):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_ocr_processing(backend: str):
    """Decorator zum Tracking von OCR-Verarbeitung."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = get_ml_metrics()
            with metrics.track_backend_request(backend):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            metrics = get_ml_metrics()
            with metrics.track_backend_request(backend):
                return func(*args, **kwargs)

        if hasattr(func, '__wrapped__'):
            return async_wrapper
        return sync_wrapper

    return decorator
