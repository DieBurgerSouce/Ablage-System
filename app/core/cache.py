# -*- coding: utf-8 -*-
"""
Redis Cache Decorator fuer API Endpoints.

Ermoeglicht einfaches Caching von API-Responses:
- L1: In-process LRU Cache (sub-ms latency)
- L2: Redis Cache (distributed)
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
import threading
import time
import fnmatch
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar, Union, List, Dict, Any
from functools import wraps
from datetime import datetime
from collections import OrderedDict

from pydantic import BaseModel, Field, field_validator, ValidationError

from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Type variable fuer generische Decorator
T = TypeVar("T")


# =============================================================================
# Cache Statistics
# =============================================================================

@dataclass
class CacheStats:
    """Cache-Statistiken Dataclass."""

    hits: int = 0
    misses: int = 0
    size: int = 0
    maxsize: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Berechne Hit-Rate als Anteil (0.0 - 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


# =============================================================================
# L1 In-Process LRU Cache (sub-ms latency)
# =============================================================================

class LRUCache:
    """Thread-safe L1 in-process LRU cache with TTL.

    Features:
    - Least Recently Used eviction policy
    - TTL-based expiration
    - Thread-safe operations with RLock
    - Hit/miss tracking for metrics
    - Pattern-based invalidation (fnmatch)

    Performance:
    - GET: O(1) average, ~0.01-0.1ms
    - SET: O(1) average, ~0.01-0.1ms
    - INVALIDATE_PATTERN: O(n) where n is number of keys

    Typical use:
    - Cache frequently accessed, small objects (user settings, config)
    - Reduce Redis latency for hot data
    - First-level cache in multi-tier architecture
    """

    def __init__(self, maxsize: int = 1024, default_ttl: int = 60):
        """Initialize LRU cache.

        Args:
            maxsize: Maximum number of entries (LRU eviction when full)
            default_ttl: Default TTL in seconds
        """
        self._cache: OrderedDict = OrderedDict()
        self._ttls: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            # Check if key exists
            if key not in self._cache:
                self._misses += 1
                return None

            # Check TTL
            expiry = self._ttls.get(key)
            if expiry and time.time() > expiry:
                # Expired - remove
                del self._cache[key]
                del self._ttls[key]
                self._misses += 1
                return None

            # Move to end (mark as recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default_ttl if None)
        """
        with self._lock:
            # Remove oldest if at capacity
            if key not in self._cache and len(self._cache) >= self._maxsize:
                # Evict LRU (first item in OrderedDict)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._ttls.pop(oldest_key, None)
                self._evictions += 1

            # Set value and TTL
            self._cache[key] = value
            self._cache.move_to_end(key)

            ttl_seconds = ttl if ttl is not None else self._default_ttl
            self._ttls[key] = time.time() + ttl_seconds

    def invalidate(self, key: str) -> None:
        """Remove specific key from cache.

        Args:
            key: Cache key to remove
        """
        with self._lock:
            self._cache.pop(key, None)
            self._ttls.pop(key, None)

    def invalidate_pattern(self, pattern: str) -> int:
        """Remove all keys matching pattern (fnmatch-style).

        Args:
            pattern: Pattern to match (e.g., "cache:user:*")

        Returns:
            Number of keys removed
        """
        with self._lock:
            keys_to_remove = [
                key for key in self._cache.keys()
                if fnmatch.fnmatch(key, pattern)
            ]

            for key in keys_to_remove:
                del self._cache[key]
                self._ttls.pop(key, None)

            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._ttls.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats dataclass with hits, misses, size, maxsize, evictions
        """
        with self._lock:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                size=len(self._cache),
                maxsize=self._maxsize,
                evictions=self._evictions,
            )


# Global L1 cache instance
_l1_cache = LRUCache(maxsize=2048, default_ttl=30)


def get_l1_cache() -> LRUCache:
    """Get global L1 cache instance.

    Returns:
        Global LRUCache instance
    """
    return _l1_cache


# =============================================================================
# Pydantic Validierungsmodelle fuer sichere JSON-Deserialisierung
# =============================================================================

# Erlaubte primitive Typen fuer Cache-Werte
CacheValueType = Union[str, int, float, bool, None, List[object], Dict[str, object]]


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


def _validate_cache_depth(data: object, current_depth: int = 0, max_depth: int = 20) -> bool:
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


def _validate_cached_value(data: object) -> CacheValueType:
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


def _serialize_value(value: object) -> str:
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
            **safe_error_log(e),
            value_preview=value[:100] if len(value) > 100 else value
        )
        return value

    except (ValidationError, ValueError) as e:
        logger.warning(
            "cache_deserialize_validation_error",
            **safe_error_log(e),
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
                from app.core.safe_errors import safe_error_detail
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
                    **safe_error_log(e),
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
                    **safe_error_log(e),
                    function=func.__name__
                )

            return result

        return wrapper
    return decorator


def cache_multi_tier(
    l1_ttl: int = 30,
    l2_ttl: int = 300,
    key_prefix: str = "",
    user_specific: bool = False,
    user_id_kwarg: str = "current_user"
):
    """Multi-tier cache decorator: L1 (in-process) -> L2 (Redis) -> source.

    Cache hierarchy:
    1. L1 (in-process LRU): ~0.01-0.1ms latency, limited capacity
    2. L2 (Redis): ~1-5ms latency, distributed, larger capacity
    3. Source: Database/API call

    On cache hit:
    - L1 hit: Return immediately (~0.01ms)
    - L2 hit: Populate L1, return (~1-5ms)

    On cache miss:
    - Call source function
    - Populate both L1 and L2

    Args:
        l1_ttl: L1 cache TTL in seconds (default: 30s)
        l2_ttl: L2 (Redis) cache TTL in seconds (default: 300s)
        key_prefix: Cache key prefix
        user_specific: Enable user-specific caching
        user_id_kwarg: Kwarg name for user object

    Usage:
        @cache_multi_tier(l1_ttl=30, l2_ttl=300, key_prefix="settings")
        async def get_user_settings(db: AsyncSession, current_user: User):
            ...

        @cache_multi_tier(l1_ttl=60, l2_ttl=600, key_prefix="config", user_specific=True)
        async def get_system_config(db: AsyncSession, current_user: User):
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
                prefix=f"{key_prefix}:{func.__name__}" if key_prefix else func.__name__,
                args=args,
                kwargs=kwargs,
                user_id=user_id
            )

            # L1 Check (in-process, fast)
            l1_result = _l1_cache.get(cache_key)
            if l1_result is not None:
                logger.debug(
                    "cache_l1_hit",
                    key=cache_key[:50],
                    function=func.__name__
                )
                return l1_result

            # L2 Check (Redis)
            try:
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                l2_start = time.time()
                cached_value = await redis_manager._redis.get(cache_key)
                l2_latency = time.time() - l2_start

                if cached_value is not None:
                    logger.debug(
                        "cache_l2_hit",
                        key=cache_key[:50],
                        function=func.__name__,
                        l2_latency_ms=round(l2_latency * 1000, 2)
                    )

                    # Deserialize and populate L1
                    result = _deserialize_value(cached_value)
                    _l1_cache.set(cache_key, result, l1_ttl)

                    # Record metrics
                    try:
                        from app.core.business_metrics import record_api_cache_operation
                        record_api_cache_operation("l2_hit", func.__name__)
                    except Exception:
                        pass

                    return result

            except Exception as e:
                # Redis nicht verfuegbar - continue to source
                logger.debug(
                    "cache_l2_miss_error",
                    **safe_error_log(e),
                    function=func.__name__
                )

            # Cache Miss - call source
            logger.debug(
                "cache_miss_all_tiers",
                key=cache_key[:50],
                function=func.__name__
            )

            result = await func(*args, **kwargs)

            # Populate L1 (fast, in-process)
            _l1_cache.set(cache_key, result, l1_ttl)

            # Populate L2 (Redis, distributed)
            try:
                from app.core.redis_state import RedisStateManager
                redis_manager = RedisStateManager.get_instance()
                await redis_manager._ensure_connection()

                serialized = _serialize_value(result)
                await redis_manager._redis.setex(cache_key, l2_ttl, serialized)

                logger.debug(
                    "cache_set_both_tiers",
                    key=cache_key[:50],
                    l1_ttl=l1_ttl,
                    l2_ttl=l2_ttl,
                    function=func.__name__
                )

                # Record metrics
                try:
                    from app.core.business_metrics import record_api_cache_operation
                    record_api_cache_operation("miss", func.__name__)
                except Exception:
                    pass

            except Exception as e:
                # L2 write failed - not critical (L1 still populated)
                logger.warning(
                    "cache_l2_write_failed",
                    **safe_error_log(e),
                    function=func.__name__
                )

            return result

        return wrapper
    return decorator


async def cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Hole einen Wert aus dem L2-Redis-Cache.

    Args:
        key: Cache-Schluessel

    Returns:
        Gespeicherter Wert als Dict oder None
    """
    # Check L1 first
    l1_value = _l1_cache.get(key)
    if l1_value is not None:
        return l1_value

    # Check L2 (Redis)
    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        raw = await redis_manager._redis.get(key)
        if raw is None:
            return None

        value = json.loads(raw)
        # Populate L1
        _l1_cache.set(key, value, ttl=30)
        return value
    except Exception as e:
        logger.debug("cache_get_failed", key=key[:50], error_type=type(e).__name__)
        return None


async def cache_set(key: str, value: Dict[str, Any], ttl: int = 300) -> None:
    """Speichere einen Wert im L1- und L2-Cache.

    Args:
        key: Cache-Schluessel
        value: Zu speichernder Wert (JSON-serialisierbar)
        ttl: Time-to-live in Sekunden
    """
    # Set L1
    _l1_cache.set(key, value, ttl=min(ttl, 60))

    # Set L2 (Redis)
    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        serialized = json.dumps(value, default=str)
        await redis_manager._redis.set(key, serialized, ex=ttl)
        logger.debug("cache_set", key=key[:50], ttl=ttl)
    except Exception as e:
        logger.debug("cache_set_failed", key=key[:50], error_type=type(e).__name__)


async def invalidate_cache(pattern: str) -> int:
    """
    Invalidiere Cache-Eintraege nach Pattern in L1 und L2.

    Invalidiert beide Cache-Tiers:
    - L1 (in-process): Pattern-based removal
    - L2 (Redis): Scan and delete

    Args:
        pattern: Redis Key Pattern (z.B. "cache:stats:*")

    Returns:
        Anzahl geloeschter Keys (L2)
    """
    # Invalidate L1 (in-process)
    l1_deleted = _l1_cache.invalidate_pattern(pattern)
    if l1_deleted > 0:
        logger.debug(
            "cache_l1_invalidated",
            pattern=pattern,
            deleted_count=l1_deleted
        )

    # Invalidate L2 (Redis)
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
                l1_deleted=l1_deleted,
                l2_deleted=len(keys_to_delete)
            )
            return len(keys_to_delete)

        return 0

    except Exception as e:
        logger.warning("cache_invalidation_failed", **safe_error_log(e), pattern=pattern)
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
    Hole Cache-Statistiken (L2 only, legacy).

    DEPRECATED: Use get_cache_metrics() for multi-tier stats.

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
        logger.warning("cache_stats_failed", **safe_error_log(e))
        return {"error": safe_error_detail(e, "Vorgang")}


async def get_cache_metrics() -> Dict[str, Dict[str, Any]]:
    """Get comprehensive cache metrics for all tiers.

    Returns multi-tier cache statistics:
    - L1: In-process LRU cache stats (hits, misses, size)
    - L2: Redis cache stats (key counts, memory usage)

    Returns:
        Dict with "l1" and "l2" keys containing respective stats
    """
    l1_stats = _l1_cache.stats()
    metrics = {
        "l1": {
            "hits": l1_stats.hits,
            "misses": l1_stats.misses,
            "hit_rate": l1_stats.hit_rate,
            "size": l1_stats.size,
            "maxsize": l1_stats.maxsize,
            "evictions": l1_stats.evictions,
        },
        "l2": {}
    }

    # L2 (Redis) stats
    try:
        from app.core.redis_state import RedisStateManager
        from app.core.safe_errors import safe_error_detail

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

        metrics["l2"] = {
            "prefix_counts": prefix_counts,
            "total_keys": sum(prefix_counts.values()),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
        }

    except Exception as e:
        logger.warning("cache_l2_stats_failed", **safe_error_log(e))
        metrics["l2"] = {"error": safe_error_detail(e, "Redis Stats")}

    return metrics
