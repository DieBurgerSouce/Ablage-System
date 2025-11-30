"""
Request Size Limit Middleware.

Prüft Content-Length Header VOR dem Upload,
um große Requests früh abzulehnen und Ressourcen zu schonen.

Feinpoliert und durchdacht - Sicherheit durch frühe Validierung.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from typing import Callable, Optional
import structlog

logger = structlog.get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware zur Begrenzung der Request-Größe.

    Prüft den Content-Length Header BEVOR die Daten hochgeladen werden.
    Dies verhindert DoS-Angriffe durch übermäßig große Uploads.

    Attributes:
        max_size_bytes: Maximale erlaubte Request-Größe in Bytes
        upload_paths: Pfade, die als Upload-Endpoints gelten (höheres Limit möglich)
        upload_max_size_bytes: Maximale Größe für Upload-Endpoints
    """

    def __init__(
        self,
        app: Callable,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10MB default für normale Requests
        upload_max_size_bytes: int = 50 * 1024 * 1024,  # 50MB für Uploads
        upload_paths: Optional[list[str]] = None,
    ):
        """
        Initialize Request Size Limit Middleware.

        Args:
            app: ASGI application
            max_size_bytes: Max size for regular requests (default 10MB)
            upload_max_size_bytes: Max size for upload endpoints (default 50MB)
            upload_paths: List of path prefixes for upload endpoints
        """
        super().__init__(app)
        self.max_size_bytes = max_size_bytes
        self.upload_max_size_bytes = upload_max_size_bytes
        self.upload_paths = upload_paths or [
            "/api/v1/documents/upload",
            "/api/v1/ocr/process",
            "/api/v1/ocr/preview/upload",
            "/documents/upload",
            "/ocr/process",
        ]

    def _is_upload_path(self, path: str) -> bool:
        """Check if the request path is an upload endpoint."""
        return any(path.startswith(upload_path) for upload_path in self.upload_paths)

    def _get_max_size(self, path: str) -> int:
        """Get the maximum allowed size for this path."""
        if self._is_upload_path(path):
            return self.upload_max_size_bytes
        return self.max_size_bytes

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes as human-readable string."""
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f}KB"
        return f"{size_bytes}B"

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Process the request and check size limits.

        Prüft Content-Length Header vor dem Weiterleiten des Requests.
        """
        # Skip size check for methods without body
        if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            return await call_next(request)

        # Get Content-Length header
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                size = int(content_length)
                max_size = self._get_max_size(request.url.path)

                if size > max_size:
                    logger.warning(
                        "request_too_large",
                        path=request.url.path,
                        content_length=size,
                        max_allowed=max_size,
                        client_ip=request.client.host if request.client else "unknown",
                    )

                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "request_too_large",
                            "nachricht": f"Anfrage zu groß: {self._format_size(size)}. "
                                        f"Maximum: {self._format_size(max_size)}",
                            "max_bytes": max_size,
                            "max_formatted": self._format_size(max_size),
                            "received_bytes": size,
                            "received_formatted": self._format_size(size),
                        },
                        headers={
                            "X-Max-Content-Length": str(max_size),
                        }
                    )
            except ValueError:
                # Invalid Content-Length header
                logger.warning(
                    "invalid_content_length",
                    content_length=content_length,
                    path=request.url.path,
                )

        return await call_next(request)


def create_request_size_middleware(
    max_size_mb: int = 10,
    upload_max_size_mb: int = 50,
) -> type[RequestSizeLimitMiddleware]:
    """
    Factory function to create configured RequestSizeLimitMiddleware.

    Args:
        max_size_mb: Max size in MB for regular requests
        upload_max_size_mb: Max size in MB for upload endpoints

    Returns:
        Configured middleware class
    """
    class ConfiguredRequestSizeLimitMiddleware(RequestSizeLimitMiddleware):
        def __init__(self, app: Callable):
            super().__init__(
                app,
                max_size_bytes=max_size_mb * 1024 * 1024,
                upload_max_size_bytes=upload_max_size_mb * 1024 * 1024,
            )

    return ConfiguredRequestSizeLimitMiddleware
