# -*- coding: utf-8 -*-
"""
Prometheus Metriken für Celery Worker.

Exponiert Celery Task-Metriken für Prometheus auf Port 8001:
- Task Counter (gestartet, erfolgreich, fehlgeschlagen, wiederholt)
- Task Dauer Histogram
- GPU Speicher Gauge
- Worker Status
- Queue Längen

Feinpoliert und durchdacht - Enterprise Celery Monitoring.
"""

import threading
import time
from typing import Any, Dict, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import structlog

from prometheus_client import (
    Counter, Histogram, Gauge, Info,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

logger = structlog.get_logger(__name__)

# =============================================================================
# PROMETHEUS REGISTRY (separiert vom Haupt-Backend)
# =============================================================================

CELERY_REGISTRY = CollectorRegistry()

# =============================================================================
# TASK METRIKEN
# =============================================================================

# Task Counter
celery_tasks_total = Counter(
    "ablage_celery_tasks_total",
    "Gesamtzahl Celery Tasks nach Status",
    ["task_name", "queue", "status"],
    registry=CELERY_REGISTRY
)

# Task Dauer Histogram
celery_task_duration_seconds = Histogram(
    "ablage_celery_task_duration_seconds",
    "Celery Task Dauer in Sekunden",
    ["task_name", "queue"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
    registry=CELERY_REGISTRY
)

# Aktive Tasks
celery_tasks_active = Gauge(
    "ablage_celery_tasks_active",
    "Anzahl aktiver Celery Tasks",
    ["task_name", "queue"],
    registry=CELERY_REGISTRY
)

# Retries
celery_task_retries_total = Counter(
    "ablage_celery_task_retries_total",
    "Anzahl Task Retries",
    ["task_name", "queue"],
    registry=CELERY_REGISTRY
)

# Task Exceptions
celery_task_exceptions_total = Counter(
    "ablage_celery_task_exceptions_total",
    "Anzahl Task Exceptions nach Typ",
    ["task_name", "exception_type"],
    registry=CELERY_REGISTRY
)

# =============================================================================
# GPU METRIKEN
# =============================================================================

# GPU Speicher
celery_gpu_memory_bytes = Gauge(
    "ablage_celery_gpu_memory_bytes",
    "GPU Speicherverbrauch in Bytes",
    ["type"],  # allocated, reserved, total
    registry=CELERY_REGISTRY
)

# GPU Auslastung
celery_gpu_utilization_percent = Gauge(
    "ablage_celery_gpu_utilization_percent",
    "GPU Auslastung in Prozent",
    registry=CELERY_REGISTRY
)

# OOM Events
celery_gpu_oom_events_total = Counter(
    "ablage_celery_gpu_oom_events_total",
    "Anzahl GPU Out-of-Memory Events",
    ["task_name"],
    registry=CELERY_REGISTRY
)

# GPU Lock
celery_gpu_lock_wait_seconds = Histogram(
    "ablage_celery_gpu_lock_wait_seconds",
    "Wartezeit auf GPU Lock in Sekunden",
    ["task_name"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=CELERY_REGISTRY
)

celery_gpu_lock_held = Gauge(
    "ablage_celery_gpu_lock_held",
    "GPU Lock aktuell gehalten (1) oder frei (0)",
    registry=CELERY_REGISTRY
)

# =============================================================================
# WORKER METRIKEN
# =============================================================================

# Worker Info
celery_worker_info = Info(
    "ablage_celery_worker",
    "Celery Worker Informationen",
    registry=CELERY_REGISTRY
)

# Worker Status
celery_worker_up = Gauge(
    "ablage_celery_worker_up",
    "Worker Status (1=aktiv, 0=inaktiv)",
    registry=CELERY_REGISTRY
)

# Worker Uptime
celery_worker_uptime_seconds = Gauge(
    "ablage_celery_worker_uptime_seconds",
    "Worker Uptime in Sekunden",
    registry=CELERY_REGISTRY
)

# Tasks verarbeitet seit Start
celery_worker_tasks_processed_total = Counter(
    "ablage_celery_worker_tasks_processed_total",
    "Gesamtzahl verarbeiteter Tasks seit Worker-Start",
    registry=CELERY_REGISTRY
)

# Worker Pool Info
celery_worker_pool_size = Gauge(
    "ablage_celery_worker_pool_size",
    "Worker Pool Größe",
    registry=CELERY_REGISTRY
)

celery_worker_prefetch_count = Gauge(
    "ablage_celery_worker_prefetch_count",
    "Worker Prefetch Multiplier",
    registry=CELERY_REGISTRY
)

# =============================================================================
# QUEUE METRIKEN
# =============================================================================

celery_queue_length = Gauge(
    "ablage_celery_queue_length",
    "Anzahl Tasks in Queue",
    ["queue_name"],
    registry=CELERY_REGISTRY
)

# =============================================================================
# HELPER FUNKTIONEN
# =============================================================================

_worker_start_time: Optional[float] = None
_task_start_times: Dict[str, float] = {}


def record_task_started(task_id: str, task_name: str, queue: str = "default") -> None:
    """Task gestartet - Metriken aktualisieren."""
    celery_tasks_total.labels(
        task_name=task_name, queue=queue, status="started"
    ).inc()
    celery_tasks_active.labels(task_name=task_name, queue=queue).inc()
    _task_start_times[task_id] = time.time()


def record_task_succeeded(task_id: str, task_name: str, queue: str = "default") -> None:
    """Task erfolgreich - Metriken aktualisieren."""
    celery_tasks_total.labels(
        task_name=task_name, queue=queue, status="succeeded"
    ).inc()
    celery_tasks_active.labels(task_name=task_name, queue=queue).dec()
    celery_worker_tasks_processed_total.inc()

    # Duration berechnen
    start_time = _task_start_times.pop(task_id, None)
    if start_time:
        duration = time.time() - start_time
        celery_task_duration_seconds.labels(
            task_name=task_name, queue=queue
        ).observe(duration)


def record_task_failed(
    task_id: str,
    task_name: str,
    queue: str = "default",
    exception_type: str = "unknown"
) -> None:
    """Task fehlgeschlagen - Metriken aktualisieren."""
    celery_tasks_total.labels(
        task_name=task_name, queue=queue, status="failed"
    ).inc()
    celery_tasks_active.labels(task_name=task_name, queue=queue).dec()
    celery_task_exceptions_total.labels(
        task_name=task_name, exception_type=exception_type
    ).inc()

    # Duration berechnen (auch bei Fehler)
    start_time = _task_start_times.pop(task_id, None)
    if start_time:
        duration = time.time() - start_time
        celery_task_duration_seconds.labels(
            task_name=task_name, queue=queue
        ).observe(duration)


def record_task_retried(task_id: str, task_name: str, queue: str = "default") -> None:
    """Task Retry - Metriken aktualisieren."""
    celery_tasks_total.labels(
        task_name=task_name, queue=queue, status="retried"
    ).inc()
    celery_task_retries_total.labels(task_name=task_name, queue=queue).inc()


def record_gpu_oom(task_name: str) -> None:
    """GPU OOM Event aufzeichnen."""
    celery_gpu_oom_events_total.labels(task_name=task_name).inc()


def record_gpu_lock_wait(task_name: str, wait_time: float) -> None:
    """GPU Lock Wartezeit aufzeichnen."""
    celery_gpu_lock_wait_seconds.labels(task_name=task_name).observe(wait_time)


def set_gpu_lock_status(held: bool) -> None:
    """GPU Lock Status setzen."""
    celery_gpu_lock_held.set(1 if held else 0)


def update_gpu_metrics() -> None:
    """GPU Metriken aktualisieren."""
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated()
            reserved = torch.cuda.memory_reserved()
            total = torch.cuda.get_device_properties(0).total_memory

            celery_gpu_memory_bytes.labels(type="allocated").set(allocated)
            celery_gpu_memory_bytes.labels(type="reserved").set(reserved)
            celery_gpu_memory_bytes.labels(type="total").set(total)

            # Auslastung berechnen
            utilization = (allocated / total) * 100 if total > 0 else 0
            celery_gpu_utilization_percent.set(utilization)
    except Exception as e:
        # Z.2 FIX: Erhöhtes Log-Level für bessere Sichtbarkeit in Monitoring
        logger.warning("gpu_metrics_update_failed", error=str(e))


def update_queue_metrics(app: Any) -> None:
    """Queue Längen aktualisieren."""
    try:
        inspect = app.control.inspect()
        queues = inspect.active_queues() or {}

        for worker, worker_queues in queues.items():
            for q in worker_queues:
                queue_name = q.get("name", "unknown")
                # Nutze Redis LLEN um Queue-Länge zu bekommen
                try:
                    from redis import Redis
                    from app.core.config import settings
                    redis = Redis.from_url(settings.CELERY_BROKER_URL)
                    length = redis.llen(queue_name) or 0
                    celery_queue_length.labels(queue_name=queue_name).set(length)
                except Exception as e:
                    # Z.2 FIX: Erhöhtes Log-Level für bessere Sichtbarkeit in Monitoring
                    logger.warning("queue_length_check_failed", queue=queue_name, error=str(e))
    except Exception as e:
        # Z.2 FIX: Erhöhtes Log-Level für bessere Sichtbarkeit in Monitoring
        logger.warning("queue_metrics_update_failed", error=str(e))


def init_worker_metrics(
    hostname: str,
    pool_size: int = 1,
    prefetch: int = 1
) -> None:
    """Worker Metriken initialisieren."""
    global _worker_start_time
    _worker_start_time = time.time()

    celery_worker_info.info({
        "hostname": hostname,
        "pool": "solo",
        "version": "5.3"
    })
    celery_worker_up.set(1)
    celery_worker_pool_size.set(pool_size)
    celery_worker_prefetch_count.set(prefetch)


def update_worker_uptime() -> None:
    """Worker Uptime aktualisieren."""
    global _worker_start_time
    if _worker_start_time:
        uptime = time.time() - _worker_start_time
        celery_worker_uptime_seconds.set(uptime)


def shutdown_worker_metrics() -> None:
    """Worker Metriken bei Shutdown."""
    celery_worker_up.set(0)


# =============================================================================
# HTTP SERVER FÜR PROMETHEUS SCRAPING
# =============================================================================

class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP Handler für Prometheus Metriken."""

    def do_GET(self) -> None:
        """GET /metrics - Prometheus Metriken."""
        if self.path == "/metrics":
            # GPU und Uptime Metriken aktualisieren
            update_gpu_metrics()
            update_worker_uptime()

            # Metriken generieren
            output = generate_latest(CELERY_REGISTRY)

            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass


_metrics_server: Optional[HTTPServer] = None
_metrics_thread: Optional[threading.Thread] = None


def start_metrics_server(port: int = 8001) -> None:
    """
    Starte HTTP Server für Prometheus Metriken.

    Args:
        port: Port für Metriken-Server (default: 8001)
    """
    global _metrics_server, _metrics_thread

    if _metrics_server is not None:
        logger.warning("metrics_server_already_running")
        return

    try:
        _metrics_server = HTTPServer(("0.0.0.0", port), MetricsHandler)
        _metrics_thread = threading.Thread(
            target=_metrics_server.serve_forever,
            daemon=True
        )
        _metrics_thread.start()

        logger.info("celery_metrics_server_started", port=port)

    except Exception as e:
        logger.error("celery_metrics_server_start_failed", error=str(e))


def stop_metrics_server() -> None:
    """Stoppe Metriken-Server."""
    global _metrics_server, _metrics_thread

    if _metrics_server is not None:
        _metrics_server.shutdown()
        _metrics_server = None
        _metrics_thread = None
        logger.info("celery_metrics_server_stopped")
