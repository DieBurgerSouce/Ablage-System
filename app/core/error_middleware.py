"""Standardisierte Fehler-Middleware fuer die FastAPI-Anwendung.

Faengt alle Exceptions ab und wandelt sie in einheitliche
StandardErrorResponse-Objekte um. Fuegt Korrelations-IDs hinzu
fuer verteiltes Tracing.

Feinpoliert und durchdacht.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.error_catalog import (
    EXCEPTION_TO_ERROR_CODE,
    get_error_definition,
)
from app.core.exceptions import AblageSystemException

logger = structlog.get_logger(__name__)

# HTTP status derivation map for legacy exception error codes
_LEGACY_STATUS_MAP: Dict[str, int] = {
    "E400": 400,
    "E403": 403,
    "E404": 404,
    "E023": 429,
}


class ErrorStandardizationMiddleware(BaseHTTPMiddleware):
    """Middleware fuer standardisierte Fehlerbehandlung.

    Features:
    - Faengt alle Exceptions ab
    - Wandelt in StandardErrorResponse um
    - Fuegt X-Correlation-ID Header hinzu
    - Loggt mit correlation_id fuer Tracing
    - Mappt Exception-Typen auf Fehlercodes
    - Deutsche message_de + Englische message
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Generate correlation ID (use existing if provided in header)
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        # Store in request state for downstream use
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            # Add correlation ID to all responses
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except AblageSystemException as exc:
            # Known application exception
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_error_response(
                exc=exc,
                correlation_id=correlation_id,
                request_path=str(request.url.path),
                duration_ms=duration_ms,
            )

        except Exception as exc:
            # Unknown/unexpected exception
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return self._build_generic_error_response(
                exc=exc,
                correlation_id=correlation_id,
                request_path=str(request.url.path),
                duration_ms=duration_ms,
            )

    def _build_error_response(
        self,
        exc: AblageSystemException,
        correlation_id: str,
        request_path: str,
        duration_ms: int,
    ) -> JSONResponse:
        """Erstellt eine standardisierte Fehlerantwort aus AblageSystemException."""
        exc_class_name = type(exc).__name__
        catalog_code = EXCEPTION_TO_ERROR_CODE.get(exc_class_name)
        error_def = get_error_definition(catalog_code) if catalog_code else None

        if error_def is not None:
            error_code = error_def.code
            message_de = error_def.message_de
            message_en = error_def.message_en
            http_status = error_def.http_status
        else:
            # Fallback to exception's own fields
            raw_code = exc.error_code if exc.error_code else "SYS-001"
            error_code = f"ERR-{raw_code}" if not raw_code.startswith("ERR-") else raw_code
            message_de = exc.user_message_de
            message_en = exc.message
            http_status = self._derive_http_status(exc.error_code)

        # Convert details values to str to satisfy Dict[str, str] contract
        details: Optional[Dict[str, str]] = None
        if exc.details:
            details = {k: str(v) for k, v in exc.details.items()}

        body = {
            "error_code": error_code,
            "message": message_en,
            "message_de": message_de,
            "correlation_id": correlation_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request_path,
        }

        logger.warning(
            "api_error",
            error_code=error_code,
            correlation_id=correlation_id,
            path=request_path,
            duration_ms=duration_ms,
            exception_type=exc_class_name,
        )

        return JSONResponse(
            status_code=http_status,
            content=body,
            headers={"X-Correlation-ID": correlation_id},
        )

    def _build_generic_error_response(
        self,
        exc: Exception,
        correlation_id: str,
        request_path: str,
        duration_ms: int,
    ) -> JSONResponse:
        """Erstellt eine generische Fehlerantwort fuer unbekannte Exceptions."""
        logger.error(
            "unhandled_api_error",
            correlation_id=correlation_id,
            path=request_path,
            duration_ms=duration_ms,
            exception_type=type(exc).__name__,
            error=str(exc),
        )

        body = {
            "error_code": "ERR-SYS-001",
            "message": "Internal server error",
            "message_de": "Interner Systemfehler",
            "correlation_id": correlation_id,
            "details": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request_path,
        }

        return JSONResponse(
            status_code=500,
            content=body,
            headers={"X-Correlation-ID": correlation_id},
        )

    @staticmethod
    def _derive_http_status(error_code: str) -> int:
        """Leitet HTTP-Status aus dem alten Fehlercode ab."""
        return _LEGACY_STATUS_MAP.get(error_code, 500)
