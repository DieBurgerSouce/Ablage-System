"""HTTP Caching Middleware.

Implementiert ETag und Cache-Control Header fuer effizientes
Browser- und CDN-Caching.
"""

import hashlib
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Set

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Standard Cache-Dauern (in Sekunden)
CACHE_DURATIONS: Dict[str, int] = {
    "static": 86400 * 30,     # 30 Tage fuer statische Assets
    "api_list": 60,           # 1 Minute fuer Listen
    "api_detail": 300,        # 5 Minuten fuer Details
    "health": 0,              # Kein Caching fuer Health
    "search": 30,             # 30 Sekunden fuer Suche
}

# Pfade die gecacht werden
CACHEABLE_PATTERNS: Dict[str, str] = {
    "/api/v1/documents": "api_list",
    "/api/v1/search": "search",
    "/static": "static",
    "/api/v1/documents/": "api_detail",  # Mit ID
}

# Pfade die nie gecacht werden
NO_CACHE_PATHS: Set[str] = {
    "/health",
    "/readiness",
    "/metrics",
    "/api/v1/auth",
    "/api/v1/ocr",  # OCR-Ergebnisse sind dynamisch
}


class HTTPCachingMiddleware(BaseHTTPMiddleware):
    """Middleware fuer HTTP Caching mit ETag und Cache-Control.

    Features:
    - ETag basierend auf Response-Body Hash
    - If-None-Match Support (304 Not Modified)
    - Konfigurierbare Cache-Control Header
    - Vary Header fuer korrektes CDN-Verhalten
    """

    def __init__(
        self,
        app: ASGIApp,
        default_max_age: int = 60,
        private_by_default: bool = True
    ):
        """Initialisiert HTTP Caching Middleware.

        Args:
            app: ASGI Application
            default_max_age: Standard Cache-Dauer in Sekunden
            private_by_default: True fuer private, False fuer public cache
        """
        super().__init__(app)
        self.default_max_age = default_max_age
        self.private_by_default = private_by_default

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit Cache-Logik."""
        # Nur GET und HEAD cachen
        if request.method not in ("GET", "HEAD"):
            response = await call_next(request)
            response.headers["cache-control"] = "no-store"
            return response

        # No-Cache Pfade
        path = request.url.path
        if any(path.startswith(nc) for nc in NO_CACHE_PATHS):
            response = await call_next(request)
            response.headers["cache-control"] = "no-store"
            return response

        # If-None-Match Header (fuer 304 Responses)
        if_none_match = request.headers.get("if-none-match")

        # Response holen
        response = await call_next(request)

        # Nur 200 OK cachen
        if response.status_code != 200:
            return response

        # Body extrahieren fuer ETag-Berechnung
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # ETag generieren
        etag = self._generate_etag(body)

        # 304 Not Modified wenn ETag matched
        if if_none_match and if_none_match == etag:
            return Response(
                status_code=304,
                headers={
                    "etag": etag,
                    "cache-control": response.headers.get(
                        "cache-control",
                        self._get_cache_control(path)
                    )
                }
            )

        # Cache-Control Header setzen
        cache_control = self._get_cache_control(path)

        # Response Headers aktualisieren
        headers = dict(response.headers)
        headers["etag"] = etag
        headers["cache-control"] = cache_control
        headers["vary"] = "Accept, Accept-Encoding, Authorization"

        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )

    def _generate_etag(self, body: bytes) -> str:
        """Generiere ETag aus Body-Hash.

        Verwendet MD5 fuer Geschwindigkeit (nicht kryptographisch).
        """
        hash_value = hashlib.md5(body).hexdigest()[:16]
        return f'"{hash_value}"'

    def _get_cache_control(self, path: str) -> str:
        """Ermittle Cache-Control Header fuer Pfad."""
        # Cache-Typ finden
        cache_type = None
        for pattern, ct in CACHEABLE_PATTERNS.items():
            if path.startswith(pattern):
                cache_type = ct
                break

        max_age = CACHE_DURATIONS.get(cache_type, self.default_max_age)
        visibility = "private" if self.private_by_default else "public"

        if max_age == 0:
            return "no-cache, no-store, must-revalidate"

        return f"{visibility}, max-age={max_age}, must-revalidate"


class ConditionalCacheMiddleware(BaseHTTPMiddleware):
    """Einfachere Middleware nur fuer ETag-basiertes Conditional GET.

    Weniger Overhead als HTTPCachingMiddleware, nur fuer 304-Support.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit ETag-Validierung."""
        if request.method not in ("GET", "HEAD"):
            return await call_next(request)

        if_none_match = request.headers.get("if-none-match")

        response = await call_next(request)

        if response.status_code != 200:
            return response

        # Body fuer ETag
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # ETag berechnen
        hash_value = hashlib.md5(body).hexdigest()[:16]
        etag = f'"{hash_value}"'

        # 304 wenn matched
        if if_none_match and if_none_match == etag:
            return Response(status_code=304, headers={"etag": etag})

        headers = dict(response.headers)
        headers["etag"] = etag

        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )


def create_http_caching_middleware(
    default_max_age: int = 60,
    private_by_default: bool = True
) -> Callable:
    """Factory fuer HTTP Caching Middleware."""
    class ConfiguredHTTPCachingMiddleware(HTTPCachingMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(
                app,
                default_max_age=default_max_age,
                private_by_default=private_by_default
            )

    return ConfiguredHTTPCachingMiddleware
