"""
Idempotency Service für sichere Wiederholungen von API-Aufrufen.

Verhindert doppelte Verarbeitung bei Netzwerkfehlern oder Client-Retries.
Speichert Ergebnisse in Redis mit konfigurierbarem TTL.

Feinpoliert und durchdacht - Robuste API-Operationen.
"""

from typing import Optional, Any, Dict, Callable, TypeVar
from functools import wraps
import json
import hashlib
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class IdempotencyService:
    """
    Service für Idempotency-Key-Verwaltung.

    Speichert Ergebnisse von API-Aufrufen in Redis,
    um bei wiederholten Requests das gleiche Ergebnis zurückzugeben.
    """

    def __init__(self, redis_client: Any = None):
        """
        Initialize IdempotencyService.

        Args:
            redis_client: Redis client instance (wird lazy geladen wenn None)
        """
        self._redis = redis_client
        self._prefix = "idempotency:"
        self._default_ttl = 86400  # 24 Stunden

    async def _get_redis(self) -> Any:
        """Get Redis client, lazy loading if needed."""
        if self._redis is None:
            from app.core.rate_limiting import get_redis_storage
            self._redis = await get_redis_storage()
        return self._redis

    def _make_cache_key(self, idempotency_key: str, user_id: Optional[str] = None) -> str:
        """
        Create cache key for idempotency storage.

        Args:
            idempotency_key: Client-provided idempotency key
            user_id: Optional user ID for scoping

        Returns:
            Full cache key
        """
        if user_id:
            return f"{self._prefix}{user_id}:{idempotency_key}"
        return f"{self._prefix}{idempotency_key}"

    async def get_cached_response(
        self,
        idempotency_key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached response for idempotency key.

        Args:
            idempotency_key: Client-provided idempotency key
            user_id: Optional user ID for scoping

        Returns:
            Cached response dict or None
        """
        redis = await self._get_redis()
        if not redis:
            return None

        cache_key = self._make_cache_key(idempotency_key, user_id)

        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                logger.debug(
                    "idempotency_cache_hit",
                    key=idempotency_key,
                    cached_at=data.get("cached_at"),
                )
                return data
        except Exception as e:
            logger.warning("idempotency_cache_get_error", error=str(e))

        return None

    async def cache_response(
        self,
        idempotency_key: str,
        response_data: Dict[str, Any],
        status_code: int = 200,
        user_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache response for idempotency key.

        Args:
            idempotency_key: Client-provided idempotency key
            response_data: Response data to cache
            status_code: HTTP status code
            user_id: Optional user ID for scoping
            ttl: Cache TTL in seconds (default 24h)

        Returns:
            True if cached successfully
        """
        redis = await self._get_redis()
        if not redis:
            return False

        cache_key = self._make_cache_key(idempotency_key, user_id)
        cache_ttl = ttl or self._default_ttl

        try:
            cache_data = {
                "response": response_data,
                "status_code": status_code,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "idempotency_key": idempotency_key,
            }
            await redis.set(cache_key, json.dumps(cache_data), ex=cache_ttl)
            logger.debug(
                "idempotency_response_cached",
                key=idempotency_key,
                ttl=cache_ttl,
            )
            return True
        except Exception as e:
            logger.warning("idempotency_cache_set_error", error=str(e))
            return False

    async def is_request_in_progress(
        self,
        idempotency_key: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Check if a request with this key is currently being processed.

        Uses a separate lock key to prevent race conditions.

        Args:
            idempotency_key: Client-provided idempotency key
            user_id: Optional user ID for scoping

        Returns:
            True if request is in progress
        """
        redis = await self._get_redis()
        if not redis:
            return False

        lock_key = f"{self._prefix}lock:{user_id or 'anon'}:{idempotency_key}"

        try:
            exists = await redis.exists(lock_key)
            return bool(exists)
        except Exception as e:
            logger.warning("idempotency_lock_check_error", error=str(e))
            return False

    async def acquire_lock(
        self,
        idempotency_key: str,
        user_id: Optional[str] = None,
        lock_ttl: int = 300  # 5 Minuten
    ) -> bool:
        """
        Acquire processing lock for idempotency key.

        Args:
            idempotency_key: Client-provided idempotency key
            user_id: Optional user ID for scoping
            lock_ttl: Lock TTL in seconds

        Returns:
            True if lock acquired
        """
        redis = await self._get_redis()
        if not redis:
            return True  # Ohne Redis, erlaube Verarbeitung

        lock_key = f"{self._prefix}lock:{user_id or 'anon'}:{idempotency_key}"

        try:
            # SET NX (nur wenn nicht existiert)
            acquired = await redis.set(lock_key, "processing", ex=lock_ttl, nx=True)
            if acquired:
                logger.debug("idempotency_lock_acquired", key=idempotency_key)
            return bool(acquired)
        except Exception as e:
            logger.warning("idempotency_lock_acquire_error", error=str(e))
            return True  # Bei Fehler, erlaube Verarbeitung

    async def release_lock(
        self,
        idempotency_key: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Release processing lock for idempotency key.

        Args:
            idempotency_key: Client-provided idempotency key
            user_id: Optional user ID for scoping
        """
        redis = await self._get_redis()
        if not redis:
            return

        lock_key = f"{self._prefix}lock:{user_id or 'anon'}:{idempotency_key}"

        try:
            await redis.delete(lock_key)
            logger.debug("idempotency_lock_released", key=idempotency_key)
        except Exception as e:
            logger.warning("idempotency_lock_release_error", error=str(e))


# Singleton instance
_idempotency_service: Optional[IdempotencyService] = None


def get_idempotency_service() -> IdempotencyService:
    """Get singleton IdempotencyService instance."""
    global _idempotency_service
    if _idempotency_service is None:
        _idempotency_service = IdempotencyService()
    return _idempotency_service


async def check_idempotency(
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
) -> Optional[Dict[str, Any]]:
    """
    FastAPI Dependency für Idempotency-Check.

    Prüft ob ein Request mit diesem Key bereits verarbeitet wurde.
    Gibt das gecachte Ergebnis zurück, falls vorhanden.

    Args:
        request: FastAPI Request
        idempotency_key: Idempotency-Key Header
        x_idempotency_key: Alternative X-Idempotency-Key Header

    Returns:
        Cached response dict if exists, None otherwise
    """
    key = idempotency_key or x_idempotency_key

    if not key:
        # Kein Idempotency-Key, normale Verarbeitung
        return None

    service = get_idempotency_service()

    # Versuche User-ID aus Request zu bekommen
    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = str(request.state.user.id)

    # Prüfe Cache
    cached = await service.get_cached_response(key, user_id)
    if cached:
        return cached

    # Prüfe ob Request in Bearbeitung
    if await service.is_request_in_progress(key, user_id):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "request_in_progress",
                "nachricht": "Ein Request mit diesem Idempotency-Key wird gerade verarbeitet. "
                            "Bitte warten Sie und versuchen Sie es erneut.",
                "idempotency_key": key,
            }
        )

    # Speichere Key im Request State für späteren Cache
    request.state.idempotency_key = key
    request.state.idempotency_user_id = user_id

    return None


def generate_idempotency_key(
    *args: Any,
    prefix: str = "auto"
) -> str:
    """
    Generate idempotency key from request parameters.

    Useful for client-side key generation.

    Args:
        *args: Values to include in key
        prefix: Key prefix

    Returns:
        Generated idempotency key
    """
    content = ":".join(str(arg) for arg in args)
    hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{prefix}_{hash_value}"
