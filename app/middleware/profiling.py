# -*- coding: utf-8 -*-
"""
Profiling Middleware.

Automatisches Request-Timing fuer alle API-Endpoints.
Integriert sich mit dem ProfilingService fuer:
- Latenz-Tracking
- Slow-Request-Erkennung
- Memory-Profiling (optional)
"""

import time
from typing import Callable, Optional, Set

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.profiling_service import ProfilingLevel, get_profiling_service

logger = structlog.get_logger(__name__)


class ProfilingMiddleware(BaseHTTPMiddleware):
    """
    Middleware fuer automatisches Performance-Profiling.

    Features:
    - Misst Latenz aller Requests
    - Integriert mit ProfilingService
    - Konfigurierbare Ausschluss-Pfade
    - Optionales Memory-Tracking
    """

    def __init__(
        self,
        app,
        excluded_paths: Optional[Set[str]] = None,
        track_memory: bool = False,
    ):
        """
        Initialisiere Profiling Middleware.

        Args:
            app: ASGI Application
            excluded_paths: Pfade die nicht getracked werden
            track_memory: Memory-Nutzung tracken (Performance-Overhead!)
        """
        super().__init__(app)
        self._excluded_paths = excluded_paths or {
            "/health",
            "/api/v1/health",
            "/metrics",
            "/api/v1/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }
        self._track_memory = track_memory

        logger.info(
            "profiling_middleware_initialized",
            excluded_paths=len(self._excluded_paths),
            track_memory=track_memory,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Verarbeite Request und tracke Performance.

        Args:
            request: Eingehender Request
            call_next: Naechste Middleware/Handler

        Returns:
            Response
        """
        # Excluded Paths ueberspringen
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self._excluded_paths):
            return await call_next(request)

        # Profiling Service
        service = get_profiling_service()

        # Skip wenn Profiling deaktiviert
        if service.profiling_level == ProfilingLevel.OFF:
            return await call_next(request)

        # Request-Metadaten
        request_id = getattr(request.state, "request_id", None)
        user_id = None
        try:
            if hasattr(request.state, "user") and request.state.user:
                user_id = str(request.state.user.id)
        except Exception:
            pass

        query_params = str(request.query_params) if request.query_params else None

        # Memory vor Request (optional)
        memory_before = None
        if self._track_memory and service.profiling_level in (ProfilingLevel.DETAILED, ProfilingLevel.FULL):
            try:
                import psutil

                memory_before = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        # Start Timer
        start_time = time.perf_counter()

        # Request ausfuehren
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Bei Exception trotzdem tracken
            duration_ms = (time.perf_counter() - start_time) * 1000
            service.record_request(
                endpoint=path,
                method=request.method,
                duration_ms=duration_ms,
                status_code=500,
                request_id=request_id,
                user_id=user_id,
                query_params=query_params,
                memory_before_mb=memory_before,
            )
            raise

        # Dauer berechnen
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Memory nach Request (optional)
        memory_after = None
        if self._track_memory and memory_before is not None:
            try:
                import psutil

                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        # Request aufzeichnen
        service.record_request(
            endpoint=path,
            method=request.method,
            duration_ms=duration_ms,
            status_code=status_code,
            request_id=request_id,
            user_id=user_id,
            query_params=query_params,
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
        )

        # Optional: Timing in Response Header
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response
