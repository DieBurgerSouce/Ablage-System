"""Document Access Logging Middleware - GoBD Compliance.

Automatisches Logging von Dokumentzugriffen:
- Interceptiert alle Dokument-bezogenen API-Aufrufe
- Protokolliert Zugriffe in document_access_logs
- Unterstuetzt Request-Korrelation via X-Request-ID

WICHTIG: Dieses Middleware loggt nur erfolgreich abgeschlossene Requests.
Fehlgeschlagene Requests werden separat behandelt.
"""

import uuid
import re
from typing import Optional, Callable, Awaitable
from contextvars import ContextVar

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentAccessType

logger = structlog.get_logger(__name__)

# Context variable for tracking current request's document access
current_document_access: ContextVar[Optional[dict]] = ContextVar(
    'current_document_access', default=None
)


# Patterns for document-related endpoints
DOCUMENT_ACCESS_PATTERNS = [
    # View document metadata
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})$'), 'GET', DocumentAccessType.VIEW.value),
    # Download document file
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/download$'), 'GET', DocumentAccessType.DOWNLOAD.value),
    # Preview/thumbnail
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/preview$'), 'GET', DocumentAccessType.PREVIEW.value),
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/thumbnail$'), 'GET', DocumentAccessType.PREVIEW.value),
    # OCR text
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/ocr$'), 'GET', DocumentAccessType.OCR_ACCESS.value),
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/text$'), 'GET', DocumentAccessType.OCR_ACCESS.value),
    # Export
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/export$'), 'POST', DocumentAccessType.EXPORT.value),
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/export/.*$'), 'GET', DocumentAccessType.EXPORT.value),
    # Share
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/share$'), 'POST', DocumentAccessType.SHARE.value),
    # Metadata update (allowed in GoBD!)
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})$'), 'PATCH', DocumentAccessType.METADATA_UPDATE.value),
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})$'), 'PUT', DocumentAccessType.METADATA_UPDATE.value),
    # Annotations
    (re.compile(r'^/api/v1/documents/([a-f0-9-]{36})/annotations$'), 'POST', DocumentAccessType.ANNOTATION.value),
]


def extract_document_access_info(path: str, method: str) -> Optional[tuple[str, str]]:
    """Extrahiert Document-ID und Access-Type aus dem Request-Pfad.

    Args:
        path: Request-Pfad (z.B. /api/v1/documents/123-abc/download)
        method: HTTP-Methode (GET, POST, etc.)

    Returns:
        Tuple (document_id, access_type) oder None wenn kein Match
    """
    for pattern, expected_method, access_type in DOCUMENT_ACCESS_PATTERNS:
        if method.upper() == expected_method:
            match = pattern.match(path)
            if match:
                document_id = match.group(1)
                return (document_id, access_type)
    return None


class DocumentAccessLoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware fuer automatisches Document Access Logging.

    Interceptiert Requests zu Dokument-Endpoints und loggt Zugriffe.
    Das eigentliche Logging erfolgt NACH erfolgreichem Response.
    """

    def __init__(
        self,
        app: ASGIApp,
        get_db: Callable[[], Awaitable[AsyncSession]],
    ):
        """
        Args:
            app: FastAPI Application
            get_db: Async function that returns a database session
        """
        super().__init__(app)
        self.get_db = get_db

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Verarbeitet den Request und loggt Dokumentzugriffe."""

        # Extract document access info from path
        access_info = extract_document_access_info(
            request.url.path,
            request.method
        )

        if not access_info:
            # No document access to log
            return await call_next(request)

        document_id, access_type = access_info

        # Get request metadata
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent")

        # Store access info in context for potential use by endpoints
        current_document_access.set({
            "document_id": document_id,
            "access_type": access_type,
            "request_id": request_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })

        try:
            # Process the request
            response = await call_next(request)

            # Only log successful accesses (2xx responses)
            if 200 <= response.status_code < 300:
                await self._log_access(
                    request=request,
                    document_id=document_id,
                    access_type=access_type,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True,
                    bytes_transferred=self._get_content_length(response),
                )
            elif response.status_code >= 400:
                # Log failed access attempts for security auditing
                await self._log_access(
                    request=request,
                    document_id=document_id,
                    access_type=access_type,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=False,
                    error_message=f"HTTP {response.status_code}",
                )

            return response

        except Exception as e:
            # Log failed access due to exception
            await self._log_access(
                request=request,
                document_id=document_id,
                access_type=access_type,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                error_message=str(e)[:500],
            )
            raise

        finally:
            # Clear context
            current_document_access.set(None)

    async def _log_access(
        self,
        request: Request,
        document_id: str,
        access_type: str,
        request_id: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        success: bool,
        error_message: Optional[str] = None,
        bytes_transferred: Optional[int] = None,
    ) -> None:
        """Loggt den Dokumentzugriff in die Datenbank."""
        try:
            # Get user_id and company_id from request state (set by auth middleware)
            user_id = getattr(request.state, 'user_id', None)
            company_id = getattr(request.state, 'company_id', None)

            if not company_id:
                # Can't log without company context
                logger.warning(
                    "document_access_log_skipped_no_company",
                    document_id=document_id,
                    access_type=access_type,
                )
                return

            # Import here to avoid circular imports
            from app.services.document_access_service import document_access_service

            async with self.get_db() as db:
                await document_access_service.log_access(
                    db=db,
                    document_id=uuid.UUID(document_id),
                    company_id=uuid.UUID(str(company_id)),
                    access_type=access_type,
                    user_id=uuid.UUID(str(user_id)) if user_id else None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                    success=success,
                    error_message=error_message,
                    bytes_transferred=bytes_transferred,
                )

        except Exception as e:
            # Log error but don't fail the request
            logger.error(
                "document_access_log_failed",
                document_id=document_id,
                error=str(e),
            )

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extrahiert die Client-IP unter Beruecksichtigung von Proxies."""
        # Check X-Forwarded-For header (reverse proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client
        if request.client:
            return request.client.host

        return None

    def _get_content_length(self, response: Response) -> Optional[int]:
        """Extrahiert die Content-Length aus dem Response."""
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                return int(content_length)
            except ValueError:
                pass
        return None


def get_current_document_access() -> Optional[dict]:
    """Gibt die Document-Access-Info des aktuellen Requests zurueck.

    Kann von Endpoints genutzt werden um auf Access-Kontext zuzugreifen.
    """
    return current_document_access.get()
