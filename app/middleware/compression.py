"""Response Compression Middleware.

Komprimiert HTTP-Responses mit gzip oder brotli basierend auf
Accept-Encoding Header und Content-Type.
"""

import gzip
import io
from typing import Callable, Optional, Set

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Content-Types die komprimiert werden sollten
COMPRESSIBLE_TYPES: Set[str] = {
    "application/json",
    "application/javascript",
    "text/html",
    "text/css",
    "text/plain",
    "text/xml",
    "application/xml",
    "image/svg+xml",
    "application/ld+json",
}

# Mindestgröße für Kompression (in Bytes)
MIN_SIZE_FOR_COMPRESSION: int = 1000

# Maximale Größe für Kompression (große Dateien nicht komprimieren)
MAX_SIZE_FOR_COMPRESSION: int = 10 * 1024 * 1024  # 10MB


class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware für Response-Kompression.

    Unterstützt gzip Kompression. Brotli kann hinzugefügt werden
    wenn die brotli-Bibliothek installiert ist.

    Args:
        app: ASGI Application
        minimum_size: Mindestgröße für Kompression (default: 1000)
        compression_level: gzip Level 1-9 (default: 6)
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = MIN_SIZE_FOR_COMPRESSION,
        compression_level: int = 6,
        exclude_paths: Optional[Set[str]] = None
    ):
        super().__init__(app)
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        self.exclude_paths = exclude_paths or {"/health", "/metrics"}

        # Brotli verfügbar?
        try:
            import brotli
            self.brotli_available = True
        except ImportError:
            self.brotli_available = False
            logger.debug("brotli_not_available", hint="pip install brotli")

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request und komprimiere Response wenn möglich."""
        # Ausgeschlossene Pfade überspringen
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Accept-Encoding Header prüfen
        accept_encoding = request.headers.get("accept-encoding", "")
        supports_brotli = "br" in accept_encoding and self.brotli_available
        supports_gzip = "gzip" in accept_encoding

        if not (supports_brotli or supports_gzip):
            return await call_next(request)

        response = await call_next(request)

        # Bereits komprimiert?
        if response.headers.get("content-encoding"):
            return response

        # Content-Type prüfen
        content_type = response.headers.get("content-type", "")
        base_content_type = content_type.split(";")[0].strip()

        if base_content_type not in COMPRESSIBLE_TYPES:
            return response

        # StreamingResponse nicht komprimieren (zu komplex)
        if isinstance(response, StreamingResponse):
            return response

        # Body extrahieren
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Größe prüfen
        if len(body) < self.minimum_size:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        if len(body) > MAX_SIZE_FOR_COMPRESSION:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Komprimieren
        compressed_body: bytes
        encoding: str

        if supports_brotli:
            import brotli
            compressed_body = brotli.compress(body, quality=4)
            encoding = "br"
        else:
            buf = io.BytesIO()
            with gzip.GzipFile(
                mode="wb",
                fileobj=buf,
                compresslevel=self.compression_level
            ) as f:
                f.write(body)
            compressed_body = buf.getvalue()
            encoding = "gzip"

        # Nur verwenden wenn kleiner
        if len(compressed_body) >= len(body):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        # Neue Response mit Kompression
        headers = dict(response.headers)
        headers["content-encoding"] = encoding
        headers["content-length"] = str(len(compressed_body))
        headers["vary"] = "Accept-Encoding"

        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )


def create_compression_middleware(
    minimum_size: int = MIN_SIZE_FOR_COMPRESSION,
    compression_level: int = 6
) -> Callable:
    """Factory für Compression Middleware.

    Args:
        minimum_size: Mindestgröße für Kompression
        compression_level: gzip Level (1-9)

    Returns:
        Middleware-Klasse
    """
    class ConfiguredCompressionMiddleware(CompressionMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(
                app,
                minimum_size=minimum_size,
                compression_level=compression_level
            )

    return ConfiguredCompressionMiddleware
