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
        "Character Error Rate (CER) fuer OCR-Ergebnisse",
        ["backend", "document_type"],
        buckets=[0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5],
        registry=ML_REGISTRY,
    )

    OCR_WER = Histogram(
        "ocr_word_error_rate",
        "Word Error Rate (WER) fuer OCR-Ergebnisse",
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
        Erfasse Ground-Truth-basierte Qualitaetsmetriken.

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
            logger.debug("gpu_metriken_update_fehlgeschlagen", error=str(e))

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
