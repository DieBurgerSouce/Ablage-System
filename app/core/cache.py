# -*- coding: utf-8 -*-
"""
Redis Cache Decorator fuer API Endpoints.

Ermoeglicht einfaches Caching von API-Responses:
- TTL-basiertes Caching
- User-spezifisches Caching
- Cache Invalidation
- Graceful Degradation bei Redis-Ausfall

Feinpoliert und durchdacht - Enterprise Caching.
"""

import json
import hashlib
import os
import structlog
from typing import Any, Callable, Optional, TypeVar, Union
from functools import wraps
from datetime import datetime

logger = structlog.get_logger(__name__)

# Type variable fuer generische Decorator
T = TypeVar("T")


def _get_int_env(key: str, default: int) -> int:
    """Hole Integer aus Umgebungsvariable mit Default."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


class CacheConfig:
    """
    Cache Konfiguration.

    TTL-Werte sind konfigurierbar via Umgebungsvariablen:
    - CACHE_DEFAULT_TTL: Standard-TTL (default: 300s)
    - CACHE_SHORT_TTL: Kurzer TTL (default: 60s)
    - CACHE_MEDIUM_TTL: Mittlerer TTL (default: 300s)
    - CACHE_LONG_TTL: Langer TTL (default: 1800s)
    - CACHE_STATS_TTL: Statistiken-TTL (default: 120s)
    """

    # Standard TTLs in Sekunden - konfigurierbar via Environment
    DEFAULT_TTL = _get_int_env("CACHE_DEFAULT_TTL", 300)     # 5 Minuten
    SHORT_TTL = _get_int_env("CACHE_SHORT_TTL", 60)          # 1 Minute
    MEDIUM_TTL = _get_int_env("CACHE_MEDIUM_TTL", 300)       # 5 Minuten
    LONG_TTL = _get_int_env("CACHE_LONG_TTL", 1800)          # 30 Minuten
    STATS_TTL = _get_int_env("CACHE_STATS_TTL", 120)         # 2 Minuten

    # Cache Key Prefixes
    PREFIX_DOCUMENT = "cache:doc"
    PREFIX_STATS = "cache:stats"
    PREFIX_SEARCH = "cache:search"
    PREFIX_FACETS = "cache:facets"
    PREFIX_USER = "cache:user"


def _serialize_value(value: Any) -> str:
    """Serialisiere Wert fuer Redis."""
    if isinstance(value, datetime):
        return json.dumps({"__datetime__": value.isoformat()})

    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        # Fallback: String-Konvertierung
        return json.dumps(str(value))


def _deserialize_value(value: str) -> Any:
    """Deserialisiere Wert aus Redis."""
    if not value:
        return None

    try:
        data = json.loads(value)

        # Handle datetime
        if isinstance(data, dict) and "__datetime__" in data:
            return datetime.fromisoformat(data["__datetime__"])

        return data
    except (json.JSONDecodeError, TypeError):
        return value


def _generate_cache_key(
    prefix: str,
    args: tuple,
    kwargs: dict,
    user_id: Optional[str] = None
) -> str:
    """
    Generiere deterministischen Cache Key.

    Args:
        prefix: Key Prefix
        args: Positionsargumente
        kwargs: Keyword-Argumente
        user_id: Optional User-ID fuer user-spezifisches Caching

    Returns:
        Cache Key String
    """
    key_parts = [prefix]

    # User-spezifisch wenn angegeben
    if user_id:
        key_parts.append(f"user:{user_id}")

    # Positionsargumente
    for i, arg in enumerate(args):
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(f"arg{i}:{arg}")
        else:
            # Hash komplexe Objekte
            try:
                arg_hash = hashlib.md5(
                    json.dumps(arg, sort_keys=True, default=str).encode()
                ).hexdigest()[:8]
                key_parts.append(f"arg{i}:{arg_hash}")
            except Exception:
                key_parts.append(f"arg{i}:obj")

    # Keyword-Argumente (sortiert fuer Konsistenz)
    for k, v in sorted(kwargs.items()):
        # Skip db und user dependencies
        if k in ("db", "current_user", "request"):
            continue

        if isinstance(v, (str, int, float, bool, type(None))):
            key_parts.append(f"{k}:{v}")
        else:
            try:
                v_hash = hashlib.md5(
                    json.dumps(v, sort_keys=True, default=str).encode()
                ).hexdigest()[:8]
                key_parts.append(f"{k}:{v_hash}")
            except Exception:
                key_parts.append(f"{k}:obj")

    return ":".join(key_parts)


def redis_cache(
    ttl: int = CacheConfig.DEFAULT_TTL,
    prefix: str = "cache",
    user_specific: bool = False,
    user_id_kwarg: str = "current_user"
):
    """
    Redis Cache Decorator fuer async Funktionen.

    Features:
    - Automatisches Caching mit TTL
    - User-spezifisches Caching (optional)
    - Graceful Degradation bei Redis-Ausfall
    - Logging von Cache Hits/Misses

    Args:
        ttl: Time-to-Live in Sekunden
        prefix: Cache Key Prefix
        user_specific: Separater Cache pro User
        user_id_kwarg: Name des User-Kwargs (fuer user_specific)

    Usage:
        @redis_cache(ttl=300, prefix="stats")
        async def get_document_stats(db: AsyncSession, current_user: User):
            ...

        @redis_cache(ttl=120, prefix="facets", user_specific=True)
        async def get_search_facets(db: AsyncSession, current_user: User):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Extrahiere User ID wenn user_specific
            user_id = None
            if user_specific:
                user_obj = kwargs.get(user_id_kwarg)
                if user_obj and hasattr(user_obj, "id"):
                    user_id = str(user_obj.id)

            # Generiere Cache Key
            cache_key = _generate_cache_key(
                prefix=f"{prefix}:{func.__name__}",
                args=args,
                kwargs=kwargs,
                user_id=user_id
            )

            # Versuche aus Cache zu laden
            try:
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                cached_value = await redis_manager._redis.get(cache_key)

                if cached_value is not None:
                    logger.debug(
                        "cache_hit",
                        key=cache_key[:50],
                        function=func.__name__
                    )
                    return _deserialize_value(cached_value)

                logger.debug(
                    "cache_miss",
                    key=cache_key[:50],
                    function=func.__name__
                )

            except Exception as e:
                # Redis nicht verfuegbar - continue without cache
                logger.warning(
                    "cache_read_failed",
                    error=str(e),
                    function=func.__name__
                )

            # Cache Miss oder Redis nicht verfuegbar - Funktion ausfuehren
            result = await func(*args, **kwargs)

            # Ergebnis cachen
            try:
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                serialized = _serialize_value(result)
                await redis_manager._redis.setex(cache_key, ttl, serialized)

                logger.debug(
                    "cache_set",
                    key=cache_key[:50],
                    ttl=ttl,
                    function=func.__name__
                )

            except Exception as e:
                # Cache Write fehlgeschlagen - nicht kritisch
                logger.warning(
                    "cache_write_failed",
                    error=str(e),
                    function=func.__name__
                )

            return result

        return wrapper
    return decorator


async def invalidate_cache(pattern: str) -> int:
    """
    Invalidiere Cache-Eintraege nach Pattern.

    Args:
        pattern: Redis Key Pattern (z.B. "cache:stats:*")

    Returns:
        Anzahl geloeschter Keys
    """
    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        keys_to_delete = []
        async for key in redis_manager._redis.scan_iter(match=pattern):
            keys_to_delete.append(key)

        if keys_to_delete:
            await redis_manager._redis.delete(*keys_to_delete)
            logger.info(
                "cache_invalidated",
                pattern=pattern,
                deleted_count=len(keys_to_delete)
            )
            return len(keys_to_delete)

        return 0

    except Exception as e:
        logger.warning("cache_invalidation_failed", error=str(e), pattern=pattern)
        return 0


async def invalidate_user_cache(user_id: str) -> int:
    """
    Invalidiere alle Cache-Eintraege eines Users.

    Args:
        user_id: User ID

    Returns:
        Anzahl geloeschter Keys
    """
    return await invalidate_cache(f"cache:*:user:{user_id}:*")


async def invalidate_document_cache(document_id: str, cascade: bool = True) -> dict:
    """
    Invalidiere alle Cache-Eintraege fuer ein Dokument.

    Mit cascade=True werden auch abhaengige Caches invalidiert:
    - Document cache
    - Search cache (weil Dokument in Suchergebnissen)
    - Facets cache (weil Facetten sich aendern koennten)
    - Stats cache (weil Statistiken sich aendern)

    Args:
        document_id: Document ID
        cascade: Ob abhaengige Caches auch invalidiert werden (default: True)

    Returns:
        Dict mit Anzahl geloeschter Keys pro Kategorie
    """
    result = {
        "document": 0,
        "search": 0,
        "facets": 0,
        "stats": 0,
        "total": 0
    }

    # Direct document cache
    patterns_doc = [
        f"cache:doc:{document_id}:*",
        f"*:doc_id:{document_id}:*",
        f"*:document_id:{document_id}:*",
    ]

    for pattern in patterns_doc:
        result["document"] += await invalidate_cache(pattern)

    # Cascade invalidation - invalidate dependent caches
    if cascade:
        # Search cache (all search results may contain this document)
        result["search"] += await invalidate_cache("cache:search:*")

        # Facets cache (document changes may affect facet counts)
        result["facets"] += await invalidate_cache("cache:facets:*")

        # Stats cache (document changes affect statistics)
        result["stats"] += await invalidate_cache("cache:stats:*")

        logger.info(
            "cache_cascade_invalidation",
            document_id=document_id,
            deleted=result
        )

    result["total"] = sum(result.values()) - result["total"]  # Don't double-count

    return result


async def invalidate_search_cache() -> int:
    """
    Invalidiere alle Search-Caches.

    Sollte aufgerufen werden nach:
    - Dokument-Upload
    - Dokument-Loeschung
    - Embedding-Regeneration
    - Index-Rebuild

    Returns:
        Anzahl geloeschter Keys
    """
    total = 0
    total += await invalidate_cache("cache:search:*")
    total += await invalidate_cache("cache:facets:*")

    logger.info("search_cache_invalidated", deleted_count=total)
    return total


async def invalidate_all_caches() -> dict:
    """
    Invalidiere ALLE Caches (Nuclear Option).

    Sollte nur bei kritischen Fehlern oder nach Migrationen verwendet werden.

    Returns:
        Dict mit Anzahl geloeschter Keys pro Kategorie
    """
    result = {
        "document": await invalidate_cache("cache:doc:*"),
        "search": await invalidate_cache("cache:search:*"),
        "facets": await invalidate_cache("cache:facets:*"),
        "stats": await invalidate_cache("cache:stats:*"),
        "user": await invalidate_cache("cache:user:*"),
    }
    result["total"] = sum(result.values())

    logger.warning("all_caches_invalidated", deleted=result)
    return result


async def invalidate_on_document_change(
    document_id: str,
    change_type: str = "update"
) -> dict:
    """
    Zentrale Invalidation-Funktion fuer Dokument-Aenderungen.

    Rufe diese Funktion auf nach:
    - document.save() / update
    - document.delete()
    - OCR completion
    - Embedding update

    Args:
        document_id: Document ID
        change_type: Art der Aenderung (create, update, delete, ocr, embedding)

    Returns:
        Dict mit Invalidation-Statistiken
    """
    # Alle Aenderungstypen erfordern vollstaendige Cascade-Invalidation
    result = await invalidate_document_cache(document_id, cascade=True)

    logger.info(
        "document_change_cache_invalidation",
        document_id=document_id,
        change_type=change_type,
        deleted=result
    )

    return result


async def get_cache_stats() -> dict:
    """
    Hole Cache-Statistiken.

    Returns:
        Dict mit Cache-Metriken
    """
    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        # Zaehle Keys nach Prefix
        prefix_counts = {}
        prefixes = ["cache:stats", "cache:facets", "cache:search", "cache:doc", "cache:user"]

        for prefix in prefixes:
            count = 0
            async for _ in redis_manager._redis.scan_iter(match=f"{prefix}:*"):
                count += 1
            prefix_counts[prefix] = count

        # Redis Info
        info = await redis_manager._redis.info("memory")

        return {
            "prefix_counts": prefix_counts,
            "total_cached_keys": sum(prefix_counts.values()),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
        }

    except Exception as e:
        logger.warning("cache_stats_failed", error=str(e))
        return {"error": str(e)}
