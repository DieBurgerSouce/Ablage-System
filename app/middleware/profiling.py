# -*- coding: utf-8 -*-
"""
Profiling Middleware.

Automatisches Request-Timing fuer alle API-Endpoints.
Integriert sich mit dem ProfilingService fuer:
- Latenz-Tracking
- Slow-Request-Erkennung
- Memory-Profiling (optional)

Uses pure ASGI pattern for proper WebSocket and redirect handling.
"""

import time
from typing import Callable, Optional, Set

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.profiling_service import ProfilingLevel, get_profiling_service

logger = structlog.get_logger(__name__)


class ProfilingMiddleware:
    """
    Middleware fuer automatisches Performance-Profiling.

    Features:
    - Misst Latenz aller Requests
    - Integriert mit ProfilingService
    - Konfigurierbare Ausschluss-Pfade
    - Optionales Memory-Tracking
    - Proper WebSocket and redirect handling via pure ASGI
    """

    def __init__(
        self,
        app: ASGIApp,
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
        self.app = app
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Process ASGI request with profiling.

        Properly handles HTTP, WebSocket, and lifespan events.
        """
        # Only profile HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Skip excluded paths
        if any(path.startswith(excluded) for excluded in self._excluded_paths):
            await self.app(scope, receive, send)
            return

        # Get profiling service
        service = get_profiling_service()

        # Skip wenn Profiling deaktiviert
        if service.profiling_level == ProfilingLevel.OFF:
            await self.app(scope, receive, send)
            return

        # Extract metadata from scope
        method = scope.get("method", "UNKNOWN")
        query_string = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        query_params = query_string if query_string else None

        # Get request_id from state if available
        request_id = None
        state = scope.get("state", {})
        if isinstance(state, dict):
            request_id = state.get("request_id")

        user_id = None

        # Memory vor Request (optional)
        memory_before = None
        if self._track_memory and service.profiling_level in (ProfilingLevel.DETAILED, ProfilingLevel.FULL):
            try:
                import psutil
                memory_before = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.debug(
                    "memory_profiling_failed",
                    phase="before_request",
                    error_type=type(e).__name__,
                )

        # Start Timer
        start_time = time.perf_counter()

        # Track response status
        status_code = 500  # Default to error
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                response_started = True
                # Add timing header
                headers = list(message.get("headers", []))
                duration_ms = (time.perf_counter() - start_time) * 1000
                headers.append((b"x-response-time", f"{duration_ms:.2f}ms".encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            # Bei Exception trotzdem tracken
            duration_ms = (time.perf_counter() - start_time) * 1000
            service.record_request(
                endpoint=path,
                method=method,
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
            except Exception as e:
                logger.debug(
                    "memory_profiling_failed",
                    phase="after_request",
                    error_type=type(e).__name__,
                )

        # Request aufzeichnen
        service.record_request(
            endpoint=path,
            method=method,
            duration_ms=duration_ms,
            status_code=status_code,
            request_id=request_id,
            user_id=user_id,
            query_params=query_params,
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
        )
