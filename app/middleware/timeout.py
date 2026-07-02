"""Request Timeout Middleware.

Implementiert konfigurierbare Timeouts für HTTP-Requests
mit Unterstützung für Endpoint-spezifische Werte.
"""

import asyncio
from typing import Callable, Dict, Optional, Set

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Standard-Timeout in Sekunden
DEFAULT_TIMEOUT = 30.0

# Endpoint-spezifische Timeouts
ENDPOINT_TIMEOUTS: Dict[str, float] = {
    # OCR-Verarbeitung braucht länger
    "/api/v1/ocr": 300.0,  # 5 Minuten
    "/api/v1/ocr/process": 300.0,

    # Batch-Operationen
    "/api/v1/documents/batch": 120.0,  # 2 Minuten
    "/api/v1/search": 60.0,  # 1 Minute für komplexe Suchen

    # Quick endpoints
    "/health": 5.0,
    "/readiness": 5.0,
    "/metrics": 10.0,

    # Export kann dauern
    "/api/v1/documents/export": 180.0,  # 3 Minuten

    # Admin-Operationen
    "/api/v1/admin": 60.0,
}

# Pfade ohne Timeout (für SSE, WebSockets)
NO_TIMEOUT_PATHS: Set[str] = {
    "/api/v1/events",
    "/api/v1/ws",
}


class TimeoutError(Exception):
    """Request hat Timeout überschritten."""
    pass


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware für Request-Timeouts.

    Features:
    - Konfigurierbare Standard- und Endpoint-spezifische Timeouts
    - Graceful Timeout Handling mit 504 Response
    - X-Request-Timeout Header Unterstützung
    - Logging bei Timeouts
    """

    def __init__(
        self,
        app: ASGIApp,
        default_timeout: float = DEFAULT_TIMEOUT,
        endpoint_timeouts: Optional[Dict[str, float]] = None,
        allow_header_override: bool = False,
        max_timeout: float = 600.0  # 10 Minuten max
    ):
        """Initialisiert Timeout Middleware.

        Args:
            app: ASGI Application
            default_timeout: Standard-Timeout in Sekunden
            endpoint_timeouts: Dict mit Endpoint-spezifischen Timeouts
            allow_header_override: Erlaube Timeout-Override via Header
            max_timeout: Maximaler erlaubter Timeout
        """
        super().__init__(app)
        self.default_timeout = default_timeout
        self.endpoint_timeouts = endpoint_timeouts or ENDPOINT_TIMEOUTS
        self.allow_header_override = allow_header_override
        self.max_timeout = max_timeout

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit Timeout."""
        path = request.url.path

        # Kein Timeout für bestimmte Pfade
        if any(path.startswith(ntp) for ntp in NO_TIMEOUT_PATHS):
            return await call_next(request)

        # Timeout ermitteln
        timeout = self._get_timeout(request, path)

        try:
            # Request mit Timeout ausführen
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout
            )

            # Timeout-Info in Response Header
            response.headers["X-Request-Timeout"] = str(timeout)
            return response

        except asyncio.TimeoutError:
            logger.warning(
                "request_timeout",
                path=path,
                method=request.method,
                timeout_seconds=timeout,
                client_ip=request.client.host if request.client else "unknown"
            )

            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request-Timeout überschritten",
                    "error_code": "REQUEST_TIMEOUT",
                    "detail": f"Der Request hat das Timeout von {timeout}s überschritten",
                    "timeout_seconds": timeout
                },
                headers={
                    "X-Request-Timeout": str(timeout),
                    "Retry-After": str(min(timeout, 60))
                }
            )

    def _get_timeout(self, request: Request, path: str) -> float:
        """Ermittle Timeout für Request.

        Priorität:
        1. Header-Override (wenn erlaubt)
        2. Exakter Pfad-Match
        3. Prefix-Match
        4. Standard-Timeout
        """
        # Header-Override prüfen
        if self.allow_header_override:
            header_timeout = request.headers.get("X-Request-Timeout")
            if header_timeout:
                try:
                    timeout = float(header_timeout)
                    return min(timeout, self.max_timeout)
                except ValueError as e:
                    logger.debug(
                        "timeout_header_parse_failed",
                        error_type=type(e).__name__,
                        header_value=header_timeout
                    )

        # Exakter Match
        if path in self.endpoint_timeouts:
            return self.endpoint_timeouts[path]

        # Prefix-Match (längster Match gewinnt)
        best_match = None
        best_length = 0
        for endpoint, timeout in self.endpoint_timeouts.items():
            if path.startswith(endpoint) and len(endpoint) > best_length:
                best_match = timeout
                best_length = len(endpoint)

        if best_match is not None:
            return best_match

        return self.default_timeout


class GracefulTimeoutMiddleware(TimeoutMiddleware):
    """Erweiterte Timeout Middleware mit Graceful Shutdown Support.

    Versucht laufende Requests zu beenden bevor Timeout erzwungen wird.
    """

    def __init__(
        self,
        app: ASGIApp,
        default_timeout: float = DEFAULT_TIMEOUT,
        grace_period: float = 5.0,
        **kwargs
    ):
        """Initialisiert Graceful Timeout Middleware.

        Args:
            app: ASGI Application
            default_timeout: Standard-Timeout
            grace_period: Zusätzliche Zeit für Cleanup nach Timeout
        """
        super().__init__(app, default_timeout=default_timeout, **kwargs)
        self.grace_period = grace_period

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit Graceful Timeout."""
        path = request.url.path

        if any(path.startswith(ntp) for ntp in NO_TIMEOUT_PATHS):
            return await call_next(request)

        timeout = self._get_timeout(request, path)

        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=timeout
            )
            response.headers["X-Request-Timeout"] = str(timeout)
            return response

        except asyncio.TimeoutError:
            logger.warning(
                "request_timeout_graceful",
                path=path,
                method=request.method,
                timeout_seconds=timeout,
                grace_period=self.grace_period
            )

            # Grace Period für Cleanup
            try:
                await asyncio.sleep(self.grace_period)
            except asyncio.CancelledError:
                pass  # Grace-Period-Sleep abgebrochen: direkt mit Timeout-Antwort fortfahren

            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request-Timeout überschritten",
                    "error_code": "REQUEST_TIMEOUT",
                    "detail": f"Der Request hat das Timeout von {timeout}s überschritten",
                    "timeout_seconds": timeout,
                    "graceful_shutdown": True
                },
                headers={
                    "X-Request-Timeout": str(timeout),
                    "Retry-After": str(min(timeout, 60))
                }
            )


def create_timeout_middleware(
    default_timeout: float = DEFAULT_TIMEOUT,
    endpoint_timeouts: Optional[Dict[str, float]] = None
) -> type:
    """Factory für Timeout Middleware."""
    class ConfiguredTimeoutMiddleware(TimeoutMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(
                app,
                default_timeout=default_timeout,
                endpoint_timeouts=endpoint_timeouts or ENDPOINT_TIMEOUTS
            )

    return ConfiguredTimeoutMiddleware
