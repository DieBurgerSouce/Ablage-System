"""
GPU Prometheus Metrics Service.

Exportiert GPU-spezifische Metriken für Prometheus:
- VRAM-Nutzung und -Verfügbarkeit
- OCR-Verarbeitungszeiten pro Backend
- Batch-Processing-Statistiken
- OOM-Errors und Recovery
- Model-Ladezeiten

Feinpoliert und durchdacht - Enterprise GPU Monitoring.
"""

import time
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from io import StringIO

import structlog
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# GPU METRICS REGISTRY
# =============================================================================

# Separate Registry für GPU-Metriken (ermöglicht isoliertes Scraping)
GPU_REGISTRY = CollectorRegistry()


# =============================================================================
# GPU HARDWARE METRICS
# =============================================================================

# GPU Memory Usage (Bytes)
gpu_memory_used_bytes = Gauge(
    "ablage_gpu_memory_used_bytes",
    "GPU Speicher belegt in Bytes",
    ["device"],
    registry=GPU_REGISTRY,
)

# GPU Memory Total (Bytes)
gpu_memory_total_bytes = Gauge(
    "ablage_gpu_memory_total_bytes",
    "GPU Speicher gesamt in Bytes",
    ["device"],
    registry=GPU_REGISTRY,
)

# GPU Memory Percentage
gpu_memory_percent = Gauge(
    "ablage_gpu_memory_percent",
    "GPU Speicher Nutzung in Prozent",
    ["device"],
    registry=GPU_REGISTRY,
)

# GPU Memory Available (Bytes)
gpu_memory_available_bytes = Gauge(
    "ablage_gpu_memory_available_bytes",
    "GPU Speicher verfügbar in Bytes",
    ["device"],
    registry=GPU_REGISTRY,
)

# GPU Availability
gpu_available = Gauge(
    "ablage_gpu_available",
    "GPU verfügbar (1=ja, 0=nein)",
    registry=GPU_REGISTRY,
)

# GPU Info
gpu_info = Info(
    "ablage_gpu",
    "GPU Informationen",
    registry=GPU_REGISTRY,
)


# =============================================================================
# OCR PROCESSING METRICS
# =============================================================================

# OCR Requests Total
ocr_requests_total = Counter(
    "ablage_ocr_requests_total",
    "Gesamtzahl OCR-Anfragen",
    ["backend", "status"],
    registry=GPU_REGISTRY,
)

# OCR Processing Duration
ocr_processing_duration_seconds = Histogram(
    "ablage_ocr_processing_duration_seconds",
    "OCR-Verarbeitungsdauer in Sekunden",
    ["backend"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    registry=GPU_REGISTRY,
)

# OCR Documents per Batch
ocr_batch_size = Histogram(
    "ablage_ocr_batch_size",
    "Dokumente pro OCR-Batch",
    ["backend"],
    buckets=[1, 2, 4, 8, 16, 32, 64],
    registry=GPU_REGISTRY,
)

# OCR Errors
ocr_errors_total = Counter(
    "ablage_ocr_errors_total",
    "OCR-Fehler nach Typ",
    ["backend", "error_type"],
    registry=GPU_REGISTRY,
)

# OCR Confidence Scores
ocr_confidence_score = Histogram(
    "ablage_ocr_confidence_score",
    "OCR Confidence Score (0-1)",
    ["backend"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
    registry=GPU_REGISTRY,
)


# =============================================================================
# OOM AND RECOVERY METRICS
# =============================================================================

# OOM Errors Total
gpu_oom_errors_total = Counter(
    "ablage_gpu_oom_errors_total",
    "GPU Out-of-Memory Fehler",
    ["backend"],
    registry=GPU_REGISTRY,
)

# OOM Recoveries
gpu_oom_recoveries_total = Counter(
    "ablage_gpu_oom_recoveries_total",
    "Erfolgreiche OOM-Recoveries",
    ["backend", "strategy"],
    registry=GPU_REGISTRY,
)

# Memory Cleanups
gpu_memory_cleanups_total = Counter(
    "ablage_gpu_memory_cleanups_total",
    "GPU Memory Cleanup Operationen",
    ["trigger"],
    registry=GPU_REGISTRY,
)


# =============================================================================
# MODEL LOADING METRICS
# =============================================================================

# Model Load Time
model_load_duration_seconds = Histogram(
    "ablage_model_load_duration_seconds",
    "Model-Ladezeit in Sekunden",
    ["model_name"],
    buckets=[1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=GPU_REGISTRY,
)

# Models Loaded
models_loaded_total = Counter(
    "ablage_models_loaded_total",
    "Geladene Modelle",
    ["model_name", "status"],
    registry=GPU_REGISTRY,
)

# Models Currently Loaded (Gauge)
models_loaded_current = Gauge(
    "ablage_models_loaded_current",
    "Aktuell geladene Modelle",
    ["model_name"],
    registry=GPU_REGISTRY,
)


# =============================================================================
# CACHE METRICS
# =============================================================================

# OCR Cache Hits/Misses
ocr_cache_operations_total = Counter(
    "ablage_ocr_cache_operations_total",
    "OCR Cache Operationen",
    ["operation", "level"],  # operation: hit/miss, level: l1/l2
    registry=GPU_REGISTRY,
)

# OCR Cache Size
ocr_cache_size_items = Gauge(
    "ablage_ocr_cache_size_items",
    "Anzahl Items im OCR Cache",
    ["level"],
    registry=GPU_REGISTRY,
)


# =============================================================================
# WORKER METRICS
# =============================================================================

# Active GPU Tasks
gpu_tasks_active = Gauge(
    "ablage_gpu_tasks_active",
    "Aktive GPU-Tasks",
    ["worker"],
    registry=GPU_REGISTRY,
)

# GPU Task Queue Length
gpu_task_queue_length = Gauge(
    "ablage_gpu_task_queue_length",
    "Tasks in GPU-Warteschlange",
    registry=GPU_REGISTRY,
)


# =============================================================================
# ADAPTIVE BATCH PROCESSING METRICS (für Hysterese-Tracking)
# =============================================================================

# Consecutive successes since last OOM
adaptive_batch_consecutive_successes = Gauge(
    "ablage_adaptive_batch_consecutive_successes",
    "Aufeinanderfolgende erfolgreiche Batches seit letztem OOM",
    registry=GPU_REGISTRY,
)

# Current effective max batch size
adaptive_batch_effective_max = Gauge(
    "ablage_adaptive_batch_effective_max",
    "Aktuelle effektive maximale Batch-Größe",
    ["backend"],
    registry=GPU_REGISTRY,
)

# Hysteresis increase count
adaptive_batch_hysteresis_increases = Counter(
    "ablage_adaptive_batch_hysteresis_increases",
    "Anzahl der Hysterese-basierten Batch-Size-Erhöhungen",
    ["backend"],
    registry=GPU_REGISTRY,
)

# Peak memory per operation
ocr_peak_memory_bytes = Histogram(
    "ablage_ocr_peak_memory_bytes",
    "Peak GPU-Speicher pro OCR-Operation in Bytes",
    ["backend"],
    buckets=[
        1 * 1024**3,   # 1 GB
        2 * 1024**3,   # 2 GB
        4 * 1024**3,   # 4 GB
        6 * 1024**3,   # 6 GB
        8 * 1024**3,   # 8 GB
        10 * 1024**3,  # 10 GB
        12 * 1024**3,  # 12 GB
        14 * 1024**3,  # 14 GB
        16 * 1024**3,  # 16 GB
    ],
    registry=GPU_REGISTRY,
)

# Memory Guard Status (0=ok, 1=warning, 2=critical)
gpu_memory_guard_status = Gauge(
    "ablage_gpu_memory_guard_status",
    "Memory Guard Status (0=OK, 1=Warnung, 2=Kritisch)",
    registry=GPU_REGISTRY,
)


# =============================================================================
# GPU METRICS SERVICE
# =============================================================================

class GPUMetricsService:
    """
    Service für GPU Prometheus Metriken.

    Features:
    - Automatische GPU-Status-Aktualisierung
    - Thread-safe Metrik-Updates
    - Separates Registry für isoliertes Scraping
    - Integration mit gpu_manager
    """

    def __init__(self, update_interval: int = 15):
        """
        Initialize GPU Metrics Service.

        Args:
            update_interval: Interval für automatische Updates in Sekunden
        """
        self._update_interval = update_interval
        self._running = False
        self._update_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_update: Optional[datetime] = None

        # Initial GPU info update
        self._update_gpu_info()

        logger.info(
            "gpu_metrics_service_initialized",
            update_interval=update_interval,
        )

    def _update_gpu_info(self) -> None:
        """Update static GPU information."""
        try:
            import torch

            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)

                gpu_available.set(1)
                gpu_info.info({
                    "device_name": device_name,
                    "compute_capability": f"{props.major}.{props.minor}",
                    "total_memory_gb": str(round(props.total_memory / 1024**3, 2)),
                    "multi_processor_count": str(props.multi_processor_count),
                    "cuda_version": torch.version.cuda or "unknown",
                })
            else:
                gpu_available.set(0)
                gpu_info.info({
                    "device_name": "none",
                    "compute_capability": "0.0",
                    "total_memory_gb": "0",
                    "cuda_version": "unavailable",
                })
        except Exception as e:
            logger.warning("gpu_info_update_failed", error=str(e))
            gpu_available.set(0)

    def update_gpu_memory_metrics(self) -> Dict[str, Any]:
        """
        Update GPU memory metrics.

        Returns:
            Current memory stats
        """
        with self._lock:
            try:
                import torch

                if not torch.cuda.is_available():
                    return {"available": False}

                device = "cuda:0"

                # Get memory stats
                total = torch.cuda.get_device_properties(0).total_memory
                allocated = torch.cuda.memory_allocated(0)
                reserved = torch.cuda.memory_reserved(0)
                free = total - allocated

                # Update gauges
                gpu_memory_total_bytes.labels(device=device).set(total)
                gpu_memory_used_bytes.labels(device=device).set(allocated)
                gpu_memory_available_bytes.labels(device=device).set(free)
                gpu_memory_percent.labels(device=device).set(
                    round((allocated / total) * 100, 2)
                )

                self._last_update = datetime.now(timezone.utc)

                return {
                    "available": True,
                    "total_bytes": total,
                    "used_bytes": allocated,
                    "reserved_bytes": reserved,
                    "free_bytes": free,
                    "usage_percent": round((allocated / total) * 100, 2),
                }

            except Exception as e:
                logger.warning("gpu_memory_metrics_update_failed", error=str(e))
                return {"available": False, "error": str(e)}

    def record_ocr_request(
        self,
        backend: str,
        status: str,
        duration_seconds: float,
        batch_size: int = 1,
        confidence: Optional[float] = None,
    ) -> None:
        """
        Record OCR request metrics.

        Args:
            backend: OCR backend name
            status: success or error
            duration_seconds: Processing time
            batch_size: Number of documents in batch
            confidence: Average confidence score
        """
        ocr_requests_total.labels(backend=backend, status=status).inc()
        ocr_processing_duration_seconds.labels(backend=backend).observe(duration_seconds)
        ocr_batch_size.labels(backend=backend).observe(batch_size)

        if confidence is not None:
            ocr_confidence_score.labels(backend=backend).observe(confidence)

        logger.debug(
            "ocr_request_recorded",
            backend=backend,
            status=status,
            duration=duration_seconds,
            batch_size=batch_size,
        )

    def record_ocr_error(self, backend: str, error_type: str) -> None:
        """Record OCR error."""
        ocr_errors_total.labels(backend=backend, error_type=error_type).inc()

    def record_oom_error(self, backend: str) -> None:
        """Record OOM error."""
        gpu_oom_errors_total.labels(backend=backend).inc()
        gpu_memory_cleanups_total.labels(trigger="oom").inc()

        logger.warning("gpu_oom_recorded", backend=backend)

    def record_oom_recovery(self, backend: str, strategy: str) -> None:
        """Record successful OOM recovery."""
        gpu_oom_recoveries_total.labels(backend=backend, strategy=strategy).inc()

    def record_model_load(
        self,
        model_name: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """
        Record model loading metrics.

        Args:
            model_name: Name of the model
            duration_seconds: Load time
            success: Whether loading succeeded
        """
        model_load_duration_seconds.labels(model_name=model_name).observe(duration_seconds)
        models_loaded_total.labels(
            model_name=model_name,
            status="success" if success else "failure"
        ).inc()

        if success:
            models_loaded_current.labels(model_name=model_name).set(1)

        logger.info(
            "model_load_recorded",
            model_name=model_name,
            duration=duration_seconds,
            success=success,
        )

    def record_model_unload(self, model_name: str) -> None:
        """Record model unload."""
        models_loaded_current.labels(model_name=model_name).set(0)

    def record_cache_operation(
        self,
        operation: str,
        level: str,
    ) -> None:
        """
        Record cache operation.

        Args:
            operation: hit or miss
            level: l1 or l2
        """
        ocr_cache_operations_total.labels(operation=operation, level=level).inc()

    def update_cache_size(self, l1_size: int, l2_size: Optional[int] = None) -> None:
        """Update cache size metrics."""
        ocr_cache_size_items.labels(level="l1").set(l1_size)
        if l2_size is not None:
            ocr_cache_size_items.labels(level="l2").set(l2_size)

    def record_memory_cleanup(self, trigger: str) -> None:
        """Record memory cleanup operation."""
        gpu_memory_cleanups_total.labels(trigger=trigger).inc()

    def update_worker_metrics(
        self,
        worker_name: str,
        active_tasks: int,
        queue_length: int,
    ) -> None:
        """Update worker-related metrics."""
        gpu_tasks_active.labels(worker=worker_name).set(active_tasks)
        gpu_task_queue_length.set(queue_length)

    def record_peak_memory(self, backend: str, peak_bytes: int) -> None:
        """
        Record peak GPU memory usage for OCR operation.

        Args:
            backend: OCR backend name
            peak_bytes: Peak memory in bytes
        """
        ocr_peak_memory_bytes.labels(backend=backend).observe(peak_bytes)

    def update_adaptive_batch_metrics(
        self,
        backend: str,
        consecutive_successes: int,
        effective_max_batch: int,
    ) -> None:
        """
        Update adaptive batch processing metrics.

        Args:
            backend: OCR backend name
            consecutive_successes: Number of successful batches since last OOM
            effective_max_batch: Current effective maximum batch size
        """
        adaptive_batch_consecutive_successes.set(consecutive_successes)
        adaptive_batch_effective_max.labels(backend=backend).set(effective_max_batch)

    def record_hysteresis_increase(self, backend: str) -> None:
        """Record a hysteresis-based batch size increase."""
        adaptive_batch_hysteresis_increases.labels(backend=backend).inc()

    def update_memory_guard_status(self, status: int) -> None:
        """
        Update memory guard status.

        Args:
            status: 0=OK, 1=Warning, 2=Critical
        """
        gpu_memory_guard_status.set(status)

    def get_metrics(self) -> bytes:
        """
        Get all GPU metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string
        """
        # Update memory metrics before generating output
        self.update_gpu_memory_metrics()

        return generate_latest(GPU_REGISTRY)

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST

    def get_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary as JSON.

        Returns:
            Summary dict
        """
        memory_stats = self.update_gpu_memory_metrics()

        return {
            "gpu": memory_stats,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "registry": "gpu_metrics",
        }

    def start_auto_update(self) -> None:
        """Start automatic metrics update thread."""
        if self._running:
            return

        self._running = True
        self._update_thread = threading.Thread(
            target=self._auto_update_loop,
            daemon=True,
            name="gpu-metrics-updater",
        )
        self._update_thread.start()

        logger.info("gpu_metrics_auto_update_started")

    def stop_auto_update(self) -> None:
        """Stop automatic metrics update thread."""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=5.0)
            self._update_thread = None

        logger.info("gpu_metrics_auto_update_stopped")

    def _auto_update_loop(self) -> None:
        """Background thread for automatic updates."""
        while self._running:
            try:
                self.update_gpu_memory_metrics()
            except Exception as e:
                logger.warning("gpu_metrics_auto_update_error", error=str(e))

            time.sleep(self._update_interval)


# =============================================================================
# SINGLETON AND CONVENIENCE FUNCTIONS
# =============================================================================

_gpu_metrics_service: Optional[GPUMetricsService] = None


def get_gpu_metrics_service() -> GPUMetricsService:
    """Get singleton GPUMetricsService instance."""
    global _gpu_metrics_service
    if _gpu_metrics_service is None:
        _gpu_metrics_service = GPUMetricsService()
    return _gpu_metrics_service


def record_ocr_metrics(
    backend: str,
    duration_seconds: float,
    success: bool,
    batch_size: int = 1,
    confidence: Optional[float] = None,
) -> None:
    """Convenience function to record OCR metrics."""
    service = get_gpu_metrics_service()
    service.record_ocr_request(
        backend=backend,
        status="success" if success else "error",
        duration_seconds=duration_seconds,
        batch_size=batch_size,
        confidence=confidence,
    )


def record_oom_event(backend: str, recovered: bool = False, strategy: str = "batch_reduction") -> None:
    """Convenience function to record OOM events."""
    service = get_gpu_metrics_service()
    service.record_oom_error(backend)
    if recovered:
        service.record_oom_recovery(backend, strategy)


def record_model_load_metrics(model_name: str, duration_seconds: float, success: bool) -> None:
    """Convenience function to record model load metrics."""
    service = get_gpu_metrics_service()
    service.record_model_load(model_name, duration_seconds, success)


def record_peak_memory(backend: str, peak_bytes: int) -> None:
    """Convenience function to record peak GPU memory usage."""
    service = get_gpu_metrics_service()
    service.record_peak_memory(backend, peak_bytes)


def update_adaptive_batch_stats(
    backend: str,
    consecutive_successes: int,
    effective_max_batch: int,
) -> None:
    """Convenience function to update adaptive batch processing stats."""
    service = get_gpu_metrics_service()
    service.update_adaptive_batch_metrics(backend, consecutive_successes, effective_max_batch)


def update_memory_guard_status(is_critical: bool = False, is_warning: bool = False) -> None:
    """Convenience function to update memory guard status."""
    service = get_gpu_metrics_service()
    if is_critical:
        status = 2
    elif is_warning:
        status = 1
    else:
        status = 0
    service.update_memory_guard_status(status)
