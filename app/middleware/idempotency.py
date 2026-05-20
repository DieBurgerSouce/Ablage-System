"""Idempotency Middleware.

Verhindert doppelte Verarbeitung von Requests durch Tracking
von Idempotency-Keys. Speichert Responses für Wiederholung.
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional, Set, Union

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Header für Idempotency Key
IDEMPOTENCY_HEADER = "Idempotency-Key"

# Standard TTL für gespeicherte Responses (24 Stunden)
DEFAULT_TTL_SECONDS = 86400

# Methoden die Idempotency unterstützen
IDEMPOTENT_METHODS: Set[str] = {"POST", "PUT", "PATCH"}

# Maximale Key-Länge
MAX_KEY_LENGTH = 256


class InMemoryIdempotencyStore:
    """Einfacher In-Memory Store für Idempotency-Daten.

    Für Produktion sollte Redis verwendet werden.
    """

    def __init__(self, ttl: int = DEFAULT_TTL_SECONDS):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl

    def _cleanup_expired(self) -> None:
        """Entferne abgelaufene Einträge."""
        now = time.time()
        expired = [
            key for key, data in self._store.items()
            if data.get("expires_at", 0) < now
        ]
        for key in expired:
            del self._store[key]

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Hole gespeicherte Response."""
        self._cleanup_expired()

        data = self._store.get(key)
        if not data:
            return None

        if data.get("expires_at", 0) < time.time():
            del self._store[key]
            return None

        return data

    async def set(
        self,
        key: str,
        status_code: int,
        body: bytes,
        headers: Dict[str, str],
        in_progress: bool = False
    ) -> None:
        """Speichere Response."""
        self._store[key] = {
            "status_code": status_code,
            "body": body,
            "headers": headers,
            "in_progress": in_progress,
            "expires_at": time.time() + self._ttl,
            "created_at": time.time()
        }

    async def mark_in_progress(self, key: str) -> bool:
        """Markiere Request als in Bearbeitung.

        Returns:
            True wenn erfolgreich, False wenn bereits in Bearbeitung
        """
        existing = await self.get(key)
        if existing:
            if existing.get("in_progress"):
                return False
            # Bereits fertig - direkt Response zurückgeben
            return True

        await self.set(key, 0, b"", {}, in_progress=True)
        return True

    async def clear_in_progress(self, key: str) -> None:
        """Entferne in_progress Markierung."""
        if key in self._store:
            del self._store[key]


class RedisIdempotencyStore:
    """Redis-basierter Store für Idempotency-Daten.

    Empfohlen für Produktion mit mehreren Instanzen.
    """

    def __init__(
        self,
        redis_client: "redis.asyncio.Redis[bytes]",
        ttl: int = DEFAULT_TTL_SECONDS,
        prefix: str = "idempotency:"
    ):
        self._redis = redis_client
        self._ttl = ttl
        self._prefix = prefix

    def _key(self, idempotency_key: str) -> str:
        """Generiere Redis-Key."""
        return f"{self._prefix}{idempotency_key}"

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Hole gespeicherte Response aus Redis."""
        data = await self._redis.get(self._key(key))
        if not data:
            return None

        return json.loads(data)

    async def set(
        self,
        key: str,
        status_code: int,
        body: bytes,
        headers: Dict[str, str],
        in_progress: bool = False
    ) -> None:
        """Speichere Response in Redis."""
        data = {
            "status_code": status_code,
            "body": body.decode("utf-8", errors="replace") if body else "",
            "headers": headers,
            "in_progress": in_progress,
            "created_at": time.time()
        }
        await self._redis.setex(
            self._key(key),
            self._ttl,
            json.dumps(data)
        )

    async def mark_in_progress(self, key: str) -> bool:
        """Markiere Request als in Bearbeitung (atomic mit SETNX)."""
        redis_key = self._key(key)

        # Prüfe ob bereits existiert
        existing = await self._redis.get(redis_key)
        if existing:
            data = json.loads(existing)
            if data.get("in_progress"):
                return False
            return True  # Bereits fertig

        # Versuche in_progress zu setzen (atomic)
        result = await self._redis.setnx(redis_key, json.dumps({
            "in_progress": True,
            "created_at": time.time()
        }))

        if result:
            await self._redis.expire(redis_key, 60)  # 60s timeout für in_progress
            return True

        return False

    async def clear_in_progress(self, key: str) -> None:
        """Entferne in_progress Markierung."""
        await self._redis.delete(self._key(key))


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware für Request-Idempotency.

    Verwendet Idempotency-Key Header um doppelte Requests zu erkennen
    und gecachte Responses zurückzugeben.

    Features:
    - In-Progress Detection (409 Conflict bei gleichzeitigem Request)
    - Response Caching (gleiche Response bei Wiederholung)
    - Automatische Key-Generierung wenn nicht vorhanden
    """

    def __init__(
        self,
        app: ASGIApp,
        store: Optional[Union["InMemoryIdempotencyStore", "RedisIdempotencyStore"]] = None,
        require_key: bool = False,
        auto_generate_key: bool = True,
        exclude_paths: Optional[Set[str]] = None
    ):
        """Initialisiert Idempotency Middleware.

        Args:
            app: ASGI Application
            store: IdempotencyStore (InMemory oder Redis)
            require_key: Erfordere Idempotency-Key Header
            auto_generate_key: Generiere Key automatisch wenn nicht vorhanden
            exclude_paths: Pfade die ausgeschlossen werden
        """
        super().__init__(app)
        self.store = store or InMemoryIdempotencyStore()
        self.require_key = require_key
        self.auto_generate_key = auto_generate_key
        self.exclude_paths = exclude_paths or {"/health", "/metrics"}

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Verarbeite Request mit Idempotency-Logik."""
        # Nur für bestimmte Methoden
        if request.method not in IDEMPOTENT_METHODS:
            return await call_next(request)

        # Ausgeschlossene Pfade
        if any(request.url.path.startswith(ep) for ep in self.exclude_paths):
            return await call_next(request)

        # Idempotency Key extrahieren oder generieren
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)

        if not idempotency_key:
            if self.require_key:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Idempotency-Key Header erforderlich",
                        "error_code": "MISSING_IDEMPOTENCY_KEY"
                    }
                )
            elif self.auto_generate_key:
                # Key aus Request-Daten generieren
                idempotency_key = await self._generate_key(request)
            else:
                return await call_next(request)

        # Key validieren
        if len(idempotency_key) > MAX_KEY_LENGTH:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Idempotency-Key zu lang (max {MAX_KEY_LENGTH})",
                    "error_code": "INVALID_IDEMPOTENCY_KEY"
                }
            )

        # Scope-spezifischen Key erstellen (inkl. User wenn authentifiziert)
        scoped_key = self._scope_key(request, idempotency_key)

        # Prüfe auf bestehende Response
        cached = await self.store.get(scoped_key)
        if cached:
            if cached.get("in_progress"):
                # Request noch in Bearbeitung
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "Request wird bereits verarbeitet",
                        "error_code": "REQUEST_IN_PROGRESS"
                    },
                    headers={"Retry-After": "5"}
                )

            # Gecachte Response zurückgeben
            logger.debug(
                "idempotency_cache_hit",
                idempotency_key=idempotency_key[:32]
            )
            return Response(
                content=cached.get("body", b""),
                status_code=cached.get("status_code", 200),
                headers=cached.get("headers", {}),
                media_type="application/json"
            )

        # Als in_progress markieren
        success = await self.store.mark_in_progress(scoped_key)
        if not success:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "Request wird bereits verarbeitet",
                    "error_code": "REQUEST_IN_PROGRESS"
                },
                headers={"Retry-After": "5"}
            )

        try:
            # Request verarbeiten
            response = await call_next(request)

            # Nur erfolgreiche Responses cachen
            if 200 <= response.status_code < 300:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                headers = dict(response.headers)
                headers["X-Idempotency-Key"] = idempotency_key

                await self.store.set(
                    scoped_key,
                    response.status_code,
                    body,
                    headers,
                    in_progress=False
                )

                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type
                )
            else:
                # Fehler nicht cachen, in_progress entfernen
                await self.store.clear_in_progress(scoped_key)
                return response

        except Exception as e:
            # Bei Fehler in_progress entfernen
            await self.store.clear_in_progress(scoped_key)
            raise

    async def _generate_key(self, request: Request) -> str:
        """Generiere Idempotency Key aus Request-Daten."""
        # Body lesen (nur einmal möglich, daher in state speichern)
        body = await request.body()

        # Hash aus Methode + Pfad + Body
        data = f"{request.method}:{request.url.path}:{body.decode('utf-8', errors='replace')}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _scope_key(self, request: Request, key: str) -> str:
        """Erstelle Scope-spezifischen Key (inkl. User-ID wenn vorhanden)."""
        user_id = getattr(request.state, "user_id", "anonymous")
        return f"{user_id}:{request.method}:{request.url.path}:{key}"


def create_idempotency_middleware(
    store: Optional[Union["InMemoryIdempotencyStore", "RedisIdempotencyStore"]] = None,
    require_key: bool = False
) -> type:
    """Factory für Idempotency Middleware."""
    class ConfiguredIdempotencyMiddleware(IdempotencyMiddleware):
        def __init__(self, app: ASGIApp):
            super().__init__(
                app,
                store=store,
                require_key=require_key
            )

    return ConfiguredIdempotencyMiddleware
