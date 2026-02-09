"""
Tenant-Kontext-Middleware fuer Multi-Tenancy mit Row-Level Security.

Diese Middleware extrahiert die Mandanten-ID aus dem Request-Kontext
und propagiert sie fuer nachgelagerte Services und RLS-Policies.
"""

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from typing import Set
from uuid import UUID

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Tenant-Kontext-Middleware fuer Multi-Tenancy mit Row-Level Security.

    Extrahiert die Mandanten-ID aus dem Request und setzt den Kontext
    fuer nachgelagerte Services. Die eigentliche RLS-Session-Variable
    wird auf Datenbankebene in der Session-Dependency gesetzt.

    Features:
    - Extrahiert tenant_id aus request.state (gesetzt von CompanyContextMiddleware)
    - Setzt request.state.tenant_id fuer nachgelagerte Services
    - Validiert Mandanten-Kontext fuer geschuetzte Routen
    - Exempt-Liste fuer oeffentliche Endpunkte
    """

    # Pfade die keinen Mandanten-Kontext benoetigen
    EXEMPT_PATHS: Set[str] = {
        "/api/v1/health",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Verarbeitet jeden Request und setzt den Mandanten-Kontext.

        Args:
            request: Eingehender HTTP Request
            call_next: Naechster Handler in der Middleware-Chain

        Returns:
            HTTP Response
        """
        path = request.url.path

        # Pruefe ob Pfad vom Mandanten-Kontext ausgenommen ist
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)

        try:
            # Hole tenant_id aus request.state (gesetzt von CompanyContextMiddleware oder JWT)
            tenant_id = getattr(request.state, "company_id", None)

            if tenant_id:
                # Validiere dass es eine gueltige UUID ist
                if isinstance(tenant_id, str):
                    tenant_id = UUID(tenant_id)

                # Setze tenant_id fuer nachgelagerte Services
                request.state.tenant_id = tenant_id

                logger.debug(
                    "tenant_context_set",
                    tenant_id=str(tenant_id),
                    path=path,
                )
            else:
                # Kein Mandanten-Kontext fuer geschuetzte Routen
                logger.warning(
                    "missing_tenant_context",
                    path=path,
                    method=request.method,
                )

            return await call_next(request)

        except ValueError as e:
            # Ungueltige UUID
            logger.error(
                "invalid_tenant_id",
                **safe_error_log(e),
                path=path,
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Ungueltige Mandanten-ID"},
            )
        except Exception as e:
            # Unerwarteter Fehler
            logger.error(
                "tenant_context_error",
                **safe_error_log(e),
                path=path,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Fehler bei Mandanten-Kontext-Verarbeitung"},
            )
