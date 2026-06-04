"""GPU Backpressure Middleware.

Implementiert VRAM-basiertes Throttling um GPU-Überlastung zu vermeiden.
Verzögert oder blockt GPU-intensive Requests wenn VRAM knapp wird.
"""

import time
from typing import Callable, Optional, Set

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# GPU-intensive Endpoints
GPU_ENDPOINTS: Set[str] = {
    "/api/v1/ocr",
    "/api/v1/ocr/process",
    "/api/v1/embeddings",
    "/api/v1/documents/batch/ocr",
}

# VRAM Schwellenwerte (als Prozent des Gesamt-VRAM)
VRAM_THRESHOLD_WARN = 0.70      # 70% - Warnung loggen
VRAM_THRESHOLD_QUEUE = 0.80    # 80% - Requests verlangsamen
VRAM_THRESHOLD_REJECT = 0.90   # 90% - Neue Requests ablehnen

# Maximale Wartezeit beim Queueing (Sekunden)
MAX_QUEUE_WAIT = 30.0

# Prüfintervall für VRAM (Sekunden)
VRAM_CHECK_INTERVAL = 1.0


class GPUMetrics:
    """Sammelt GPU-Metriken.

    Wrapper für nvidia-smi / pynvml.
    """

    def __init__(self):
        self._initialized = False
        self._nvml_available = False
        self._last_check = 0.0
        self._cached_usage = 0.0
        self._cached_total = 16 * 1024 * 1024 * 1024  # Default 16GB

        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            self._nvml_available = True
            self._initialized = True
            logger.info("gpu_metrics_initialized", backend="pynvml")
        except Exception as e:
            logger.warning(
                "gpu_metrics_unavailable",
                **safe_error_log(e),
                hint="Install pynvml: pip install pynvml"
            )

    def get_vram_usage(self) -> float:
        """Hole aktuelle VRAM-Auslastung als Prozent (0-1).

        Cached für VRAM_CHECK_INTERVAL Sekunden.
        """
        now = time.time()

        # Cache verwenden wenn noch gültig
        if now - self._last_check < VRAM_CHECK_INTERVAL:
            return self._cached_usage / self._cached_total if self._cached_total > 0 else 0.0

        if not self._nvml_available:
            # Fallback: Verwende PyTorch wenn verfügbar
            try:
                import torch
                if torch.cuda.is_available():
                    self._cached_usage = torch.cuda.memory_allocated()
                    self._cached_total = torch.cuda.get_device_properties(0).total_memory
                    self._last_check = now
                    return self._cached_usage / self._cached_total
            except Exception as e:
                logger.debug(
                    "pytorch_vram_check_failed",
                    error_type=type(e).__name__,
                )
            return 0.0

        try:
            handle = self._nvml.nvmlDeviceGetHandleByIndex(0)
            info = self._nvml.nvmlDeviceGetMemoryInfo(handle)
            self._cached_usage = info.used
            self._cached_total = info.total
            self._last_check = now
            return info.used / info.total

        except Exception as e:
            logger.warning("vram_check_failed", **safe_error_log(e))
            return 0.0

    def get_vram_info(self) -> dict:
        """Hole detaillierte VRAM-Informationen."""
        usage = self.get_vram_usage()
        return {
            "usage_percent": round(usage * 100, 1),
            "used_bytes": self._cached_usage,
            "total_bytes": self._cached_total,
            "available_bytes": self._cached_total - self._cached_usage,
            "available_gb": round((self._cached_total - self._cached_usage) / (1024**3), 2)
        }


# Globale GPU-Metriken Instanz
_gpu_metrics: Optional[GPUMetrics] = None


def get_gpu_metrics() -> GPUMetrics:
    """Hole oder erstelle GPU-Metriken Instanz."""
    global _gpu_metrics
    if _gpu_metrics is None:
        _gpu_metrics = GPUMetrics()
    return _gpu_metrics


class GPUBackpressureMiddleware(BaseHTTPMiddleware):
    """Middleware für GPU-basiertes Backpressure.

    Features:
    - VRAM-Monitoring mit konfigurierbaren Schwellenwerten
    - Request-Queueing bei hoher Last
    - Request-Ablehnung bei kritischer Last
    - Retry-After Header für Clients
    - Metriken-Export für Monitoring
    """

    def __init__(
        self,
        app: ASGIApp,
        warn_threshold: float = VRAM_THRESHOLD_WARN,
        queue_threshold: float = VRAM_THRESHOLD_QUEUE,
        reject_threshold: float = VRAM_THRESHOLD_REJECT,
        max_queue_wait: float = MAX_QUEUE_WAIT,
        gpu_endpoints: Optional[Set[str]] = None
    ):
        """Initialisiert GPU Backpressure Middleware.

        Args:
            app: ASGI Application
            warn_threshold: VRAM % ab der gewarnt wird
            queue_threshold: VRAM % ab der Requests verlangsamt werden
            reject_threshold: VRAM % ab der Requests abgelehnt werden
            max_queue_wait: Maximale Wartezeit in Sekunden
            gpu_endpoints: Set von GPU-intensiven Endpoints
        """
        super().__init__(app)
        self.warn_threshold = warn_threshold
        self.queue_threshold = queue_threshold
        self.reject_threshold = reject_threshold
        self.max_queue_wait = max_queue_wait
        self.gpu_endpoints = gpu_endpoints or GPU_ENDPOINTS
        self.metrics = get_gpu_metrics()

        # Statistiken
        self._queued_count = 0
        self._rejected_count = 0
        self._processed_count = 0

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit GPU Backpressure."""
        path = request.url.path

        # Nur GPU-Endpoints prüfen
        if not any(path.startswith(ep) for ep in self.gpu_endpoints):
            return await call_next(request)

        # VRAM prüfen
        vram_usage = self.metrics.get_vram_usage()

        # Kritisch: Ablehnen
        if vram_usage >= self.reject_threshold:
            self._rejected_count += 1
            logger.warning(
                "gpu_backpressure_reject",
                path=path,
                vram_percent=round(vram_usage * 100, 1),
                threshold_percent=round(self.reject_threshold * 100, 1),
                rejected_total=self._rejected_count
            )

            vram_info = self.metrics.get_vram_info()
            return JSONResponse(
                status_code=503,
                content={
                    "error": "GPU-Ressourcen überlastet",
                    "error_code": "GPU_OVERLOADED",
                    "detail": f"VRAM-Auslastung bei {vram_info['usage_percent']}%",
                    "vram_info": vram_info,
                    "retry_after_seconds": 30
                },
                headers={
                    "Retry-After": "30",
                    "X-GPU-VRAM-Usage": str(vram_info["usage_percent"])
                }
            )

        # Hoch: Verlangsamen (Warten bis VRAM sinkt)
        if vram_usage >= self.queue_threshold:
            self._queued_count += 1
            wait_start = time.time()
            waited = 0.0

            logger.info(
                "gpu_backpressure_queue",
                path=path,
                vram_percent=round(vram_usage * 100, 1),
                queued_total=self._queued_count
            )

            # Warte bis VRAM sinkt oder Timeout
            while vram_usage >= self.queue_threshold:
                if waited >= self.max_queue_wait:
                    # Timeout - als überlastet behandeln
                    vram_info = self.metrics.get_vram_info()
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": "GPU-Wartezeit überschritten",
                            "error_code": "GPU_QUEUE_TIMEOUT",
                            "detail": f"VRAM blieb {waited:.0f}s bei {vram_info['usage_percent']}%",
                            "waited_seconds": round(waited, 1),
                            "retry_after_seconds": 30
                        },
                        headers={
                            "Retry-After": "30",
                            "X-GPU-VRAM-Usage": str(vram_info["usage_percent"])
                        }
                    )

                # Kurz warten und erneut prüfen
                import asyncio

                await asyncio.sleep(VRAM_CHECK_INTERVAL)
                waited = time.time() - wait_start
                vram_usage = self.metrics.get_vram_usage()

            if waited > 0:
                logger.info(
                    "gpu_backpressure_queue_released",
                    path=path,
                    waited_seconds=round(waited, 1),
                    vram_percent=round(vram_usage * 100, 1)
                )

        # Warnung loggen wenn über Schwelle
        if vram_usage >= self.warn_threshold:
            logger.debug(
                "gpu_vram_warning",
                vram_percent=round(vram_usage * 100, 1),
                threshold_percent=round(self.warn_threshold * 100, 1)
            )

        # Request verarbeiten
        self._processed_count += 1
        response = await call_next(request)

        # VRAM-Info in Header
        vram_info = self.metrics.get_vram_info()
        response.headers["X-GPU-VRAM-Usage"] = str(vram_info["usage_percent"])
        response.headers["X-GPU-VRAM-Available-GB"] = str(vram_info["available_gb"])

        return response

    def get_stats(self) -> dict:
        """Hole Backpressure-Statistiken."""
        return {
            "queued_count": self._queued_count,
            "rejected_count": self._rejected_count,
            "processed_count": self._processed_count,
            "current_vram": self.metrics.get_vram_info()
        }


def create_gpu_backpressure_middleware(
    reject_threshold: float = VRAM_THRESHOLD_REJECT,
    queue_threshold: float = VRAM_THRESHOLD_QUEUE
) -> type:
    """Factory für GPU Backpressure Middleware."""
    class ConfiguredGPUBackpressureMiddleware(GPUBackpressureMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(
                app,
                reject_threshold=reject_threshold,
                queue_threshold=queue_threshold
            )

    return ConfiguredGPUBackpressureMiddleware
