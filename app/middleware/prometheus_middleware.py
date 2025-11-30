"""
Prometheus HTTP Middleware für Ablage-System.

Automatisches Tracking aller HTTP Requests:
- Request Count
- Request Duration
- Response Status Codes
- Active Requests
- Request/Response Size

Feinpoliert und durchdacht - Enterprise-grade HTTP Metriken.
"""

import time
from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
import structlog

from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger(__name__)


# =============================================================================
# PROMETHEUS HTTP METRIKEN
# =============================================================================

# Request Counter
http_requests_total = Counter(
    "ablage_http_requests_total",
    "Gesamtzahl HTTP Requests",
    ["method", "endpoint", "status_code"]
)

# Request Duration
http_request_duration_seconds = Histogram(
    "ablage_http_request_duration_seconds",
    "HTTP Request Dauer in Sekunden",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Active Requests
http_requests_in_progress = Gauge(
    "ablage_http_requests_in_progress",
    "Anzahl aktiver HTTP Requests",
    ["method", "endpoint"]
)

# Request Size
http_request_size_bytes = Histogram(
    "ablage_http_request_size_bytes",
    "HTTP Request Größe in Bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

# Response Size
http_response_size_bytes = Histogram(
    "ablage_http_response_size_bytes",
    "HTTP Response Größe in Bytes",
    ["method", "endpoint"],
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

# Error Counter
http_errors_total = Counter(
    "ablage_http_errors_total",
    "HTTP Fehler nach Typ",
    ["method", "endpoint", "error_type"]
)

# Slow Request Counter
http_slow_requests_total = Counter(
    "ablage_http_slow_requests_total",
    "Langsame Requests (> Schwelle)",
    ["method", "endpoint"]
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Prometheus HTTP Metrics Middleware.

    Trackt automatisch alle HTTP Requests mit:
    - Anzahl Requests nach Method, Endpoint, Status
    - Request/Response Latenz
    - Request/Response Größe
    - Aktive Requests
    - Fehler nach Typ
    - Langsame Requests
    """

    # Konfiguration
    SLOW_REQUEST_THRESHOLD_SECONDS = 5.0
    EXCLUDE_PATHS = {"/health", "/metrics", "/metrics/prometheus", "/docs", "/openapi.json"}

    def __init__(
        self,
        app,
        slow_request_threshold: float = 5.0,
        exclude_paths: Optional[set] = None
    ):
        """
        Initialisiere Prometheus Middleware.

        Args:
            app: ASGI Application
            slow_request_threshold: Schwelle für langsame Requests in Sekunden
            exclude_paths: Pfade die nicht getrackt werden sollen
        """
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold
        self.exclude_paths = exclude_paths or self.EXCLUDE_PATHS

        logger.info(
            "prometheus_middleware_initialized",
            slow_threshold=slow_request_threshold,
            excluded_paths=list(self.exclude_paths)
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Verarbeite Request und sammle Metriken.

        Args:
            request: Eingehender Request
            call_next: Nächste Middleware/Handler

        Returns:
            Response mit Metriken
        """
        # Hole Request-Infos
        method = request.method
        path = request.url.path

        # Normalisiere Pfad (ersetze IDs mit Placeholder)
        endpoint = self._normalize_path(request)

        # Skip excluded paths
        if path in self.exclude_paths:
            return await call_next(request)

        # Track request start
        start_time = time.perf_counter()

        # Increment in-progress gauge
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        # Request Size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                http_request_size_bytes.labels(
                    method=method, endpoint=endpoint
                ).observe(int(content_length))
            except ValueError:
                pass

        status_code = 500
        error_type = None

        try:
            # Process request
            response = await call_next(request)
            status_code = response.status_code

            # Response Size
            response_size = response.headers.get("content-length")
            if response_size:
                try:
                    http_response_size_bytes.labels(
                        method=method, endpoint=endpoint
                    ).observe(int(response_size))
                except ValueError:
                    pass

            return response

        except Exception as e:
            status_code = 500
            error_type = type(e).__name__

            # Track error
            http_errors_total.labels(
                method=method,
                endpoint=endpoint,
                error_type=error_type
            ).inc()

            raise

        finally:
            # Calculate duration
            duration = time.perf_counter() - start_time

            # Record metrics
            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code)
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            # Decrement in-progress gauge
            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

            # Track slow requests
            if duration > self.slow_request_threshold:
                http_slow_requests_total.labels(
                    method=method,
                    endpoint=endpoint
                ).inc()

                logger.warning(
                    "slow_request_detected",
                    method=method,
                    endpoint=endpoint,
                    duration_seconds=duration,
                    threshold=self.slow_request_threshold
                )

            # Track errors
            if status_code >= 400 and error_type is None:
                error_type = f"http_{status_code}"
                http_errors_total.labels(
                    method=method,
                    endpoint=endpoint,
                    error_type=error_type
                ).inc()

    def _normalize_path(self, request: Request) -> str:
        """
        Normalisiere Request-Pfad für Metriken.

        Ersetzt dynamische Segmente (UUIDs, IDs) mit Platzhaltern
        um Kardinalitäts-Explosion zu vermeiden.

        Args:
            request: HTTP Request

        Returns:
            Normalisierter Pfad
        """
        # Try to get matched route
        if hasattr(request, "app") and hasattr(request.app, "routes"):
            for route in request.app.routes:
                match, scope = route.matches(request.scope)
                if match == Match.FULL:
                    return route.path

        # Fallback: Manuelles Normalisieren
        path = request.url.path

        # Ersetze UUIDs mit Placeholder
        import re
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        path = re.sub(uuid_pattern, '{id}', path, flags=re.IGNORECASE)

        # Ersetze numerische IDs mit Placeholder
        numeric_id_pattern = r'/\d+(?=/|$)'
        path = re.sub(numeric_id_pattern, '/{id}', path)

        return path


def create_prometheus_middleware(
    slow_request_threshold: float = 5.0,
    exclude_paths: Optional[set] = None
) -> type:
    """
    Factory für Prometheus Middleware mit Konfiguration.

    Args:
        slow_request_threshold: Schwelle für langsame Requests
        exclude_paths: Pfade die nicht getrackt werden sollen

    Returns:
        Konfigurierte Middleware-Klasse
    """
    class ConfiguredPrometheusMiddleware(PrometheusMiddleware):
        def __init__(self, app):
            super().__init__(
                app,
                slow_request_threshold=slow_request_threshold,
                exclude_paths=exclude_paths
            )

    return ConfiguredPrometheusMiddleware
