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
from typing import Any, Callable, Optional, TypeVar, Union, List, Dict
from functools import wraps
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, ValidationError

logger = structlog.get_logger(__name__)

# Type variable fuer generische Decorator
T = TypeVar("T")


# =============================================================================
# Pydantic Validierungsmodelle fuer sichere JSON-Deserialisierung
# =============================================================================

# Erlaubte primitive Typen fuer Cache-Werte
CacheValueType = Union[str, int, float, bool, None, List[Any], Dict[str, Any]]


class DatetimeCacheValue(BaseModel):
    """Validierungsschema fuer serialisierte datetime-Objekte."""
    datetime_value: str = Field(..., alias="__datetime__", min_length=1)

    model_config = {"populate_by_name": True}

    @field_validator("datetime_value")
    @classmethod
    def validate_iso_format(cls, v: str) -> str:
        """Validiere ISO-8601 Datumsformat."""
        try:
            datetime.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError(f"Ungueltiges Datumsformat: {v}")


class CacheValueSchema(BaseModel):
    """Validierungsschema fuer Cache-Werte.

    Validiert die Struktur von gecachten Daten:
    - Primitive Typen (str, int, float, bool, None)
    - Listen und Dicts
    - Spezielle datetime-Objekte

    Verhindert:
    - Unerwartete Typen
    - Zu tief verschachtelte Strukturen (max_depth)
    """
    value: CacheValueType

    model_config = {"extra": "forbid"}


def _validate_cache_depth(data: Any, current_depth: int = 0, max_depth: int = 20) -> bool:
    """Pruefe maximale Verschachtelungstiefe von Cache-Daten.

    Verhindert DoS-Angriffe durch extrem tief verschachtelte JSON-Strukturen.

    Args:
        data: Zu pruefende Daten
        current_depth: Aktuelle Tiefe
        max_depth: Maximale erlaubte Tiefe

    Returns:
        True wenn Tiefe OK, False wenn zu tief
    """
    if current_depth > max_depth:
        return False

    if isinstance(data, dict):
        return all(
            _validate_cache_depth(v, current_depth + 1, max_depth)
            for v in data.values()
        )
    elif isinstance(data, list):
        return all(
            _validate_cache_depth(item, current_depth + 1, max_depth)
            for item in data
        )
    return True


def _validate_cached_value(data: Any) -> CacheValueType:
    """Validiere deserialisierte Cache-Daten mit Pydantic.

    Args:
        data: Deserialisierte JSON-Daten

    Returns:
        Validierte Daten

    Raises:
        ValidationError: Bei Validierungsfehlern
    """
    # Pruefe Verschachtelungstiefe
    if not _validate_cache_depth(data):
        raise ValueError("Cache-Daten ueberschreiten maximale Verschachtelungstiefe")

    # Spezialfall: datetime-Objekte
    if isinstance(data, dict) and "__datetime__" in data and len(data) == 1:
        validated = DatetimeCacheValue.model_validate(data)
        return {"__datetime__": validated.datetime_value}

    # Normale Cache-Werte
    CacheValueSchema(value=data)
    return data


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


def _deserialize_value(value: str) -> CacheValueType:
    """Deserialisiere und validiere Wert aus Redis.

    Verwendet Pydantic-Validierung fuer sichere Deserialisierung:
    - Prueft Datentypen
    - Validiert datetime-Format
    - Begrenzt Verschachtelungstiefe (DoS-Schutz)

    Args:
        value: Serialisierter JSON-String aus Redis

    Returns:
        Validierte Daten oder None bei leerem Input
    """
    if not value:
        return None

    try:
        data = json.loads(value)

        # Validiere mit Pydantic
        validated_data = _validate_cached_value(data)

        # Handle datetime nach Validierung
        if isinstance(validated_data, dict) and "__datetime__" in validated_data:
            return datetime.fromisoformat(validated_data["__datetime__"])

        return validated_data

    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "cache_deserialize_json_error",
            error=str(e),
            value_preview=value[:100] if len(value) > 100 else value
        )
        return value

    except (ValidationError, ValueError) as e:
        logger.warning(
            "cache_deserialize_validation_error",
            error=str(e),
            value_preview=value[:100] if len(value) > 100 else value
        )
        # Bei Validierungsfehlern Cache-Eintrag verwerfen
        return None


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
                ).hexdigest()[:16]  # 16 chars = 64 bits to reduce collision risk
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
                ).hexdigest()[:16]  # 16 chars = 64 bits to reduce collision risk
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
                import time as time_module
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                read_start = time_module.perf_counter()
                cached_value = await redis_manager._redis.get(cache_key)
                read_latency = time_module.perf_counter() - read_start

                # Record cache latency
                try:
                    from app.core.business_metrics import (
                        record_api_cache_operation,
                        record_api_cache_latency,
                    )
                    record_api_cache_latency("read", read_latency)
                except Exception as e:
                    logger.debug(
                        "metrics_recording_failed",
                        operation="cache_read_latency",
                        error_type=type(e).__name__,
                    )

                if cached_value is not None:
                    logger.debug(
                        "cache_hit",
                        key=cache_key[:50],
                        function=func.__name__
                    )
                    # Record cache hit
                    try:
                        record_api_cache_operation("hit", func.__name__)
                    except Exception as e:
                        logger.debug(
                            "metrics_recording_failed",
                            operation="cache_hit",
                            error_type=type(e).__name__,
                        )
                    return _deserialize_value(cached_value)

                logger.debug(
                    "cache_miss",
                    key=cache_key[:50],
                    function=func.__name__
                )
                # Record cache miss
                try:
                    record_api_cache_operation("miss", func.__name__)
                except Exception as e:
                    logger.debug(
                        "metrics_recording_failed",
                        operation="cache_miss",
                        error_type=type(e).__name__,
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
                import time as time_module
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                serialized = _serialize_value(result)
                write_start = time_module.perf_counter()
                await redis_manager._redis.setex(cache_key, ttl, serialized)
                write_latency = time_module.perf_counter() - write_start

                # Record write latency
                try:
                    from app.core.business_metrics import record_api_cache_latency
                    record_api_cache_latency("write", write_latency)
                except Exception as e:
                    logger.debug(
                        "metrics_recording_failed",
                        operation="cache_write_latency",
                        error_type=type(e).__name__,
                    )

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


async def invalidate_user_cache(user_id: str, cascade: bool = True) -> dict:
    """
    Invalidiere alle Cache-Eintraege eines Users mit optionaler Cascade.

    Mit cascade=True werden auch abhaengige Caches invalidiert:
    - User-spezifische Caches (user:{user_id})
    - User's Dokument-Caches (owner_id)
    - Search/Facets Caches (koennten User-Daten enthalten)
    - Stats Caches (User-spezifische Statistiken)

    Args:
        user_id: User ID
        cascade: Ob abhaengige Caches auch invalidiert werden (default: True)

    Returns:
        Dict mit Anzahl geloeschter Keys pro Kategorie
    """
    result = {
        "user": 0,
        "documents": 0,
        "search": 0,
        "facets": 0,
        "stats": 0,
        "total": 0
    }

    # User-spezifische Cache-Eintraege
    user_patterns = [
        f"cache:*:user:{user_id}:*",
        f"cache:user:{user_id}:*",
        f"*:owner_id:{user_id}:*",
    ]

    for pattern in user_patterns:
        result["user"] += await invalidate_cache(pattern)

    if cascade:
        # User's Dokument-Caches (besitzte Dokumente)
        result["documents"] += await invalidate_cache(f"cache:doc:*:owner:{user_id}:*")

        # Search-Caches (koennten User-spezifische Ergebnisse enthalten)
        result["search"] += await invalidate_cache(f"cache:search:*:user:{user_id}:*")

        # Facets-Caches (User-spezifische Facetten)
        result["facets"] += await invalidate_cache(f"cache:facets:*:user:{user_id}:*")

        # Stats-Caches (User-spezifische Statistiken)
        result["stats"] += await invalidate_cache(f"cache:stats:*:user:{user_id}:*")
        result["stats"] += await invalidate_cache(f"cache:stats:*:owner:{user_id}:*")

        logger.info(
            "user_cache_cascade_invalidation",
            user_id=user_id,
            deleted=result
        )

    result["total"] = sum(v for k, v in result.items() if k != "total")

    return result


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
