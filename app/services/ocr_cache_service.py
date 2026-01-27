"""
OCR Result Caching Service.

Multi-Level Caching für OCR-Ergebnisse:
- L1 Cache: In-Memory (TTLCache) für häufig abgerufene Dokumente
- L2 Cache: Redis für persistente Speicherung

Cache-Key basiert auf:
- Datei-Hash (SHA256)
- OCR-Backend
- Sprache

Feinpoliert und durchdacht - Ressourcenschonende OCR.
Performance: orjson für 10-15% schnellere JSON-Serialisierung.
"""

import asyncio
import hashlib
import sys
import threading
from typing import Any, Optional, Dict, List, Union

# JSON-serializable types
JsonValue = Union[str, int, float, bool, None, Dict[str, "JsonValue"], List["JsonValue"]]
JsonSerializable = Union[Dict[str, JsonValue], List[JsonValue], str, int, float, bool, None]
from datetime import datetime, timezone
from collections import OrderedDict
import time

import structlog

# Verwende orjson für schnellere JSON-Serialisierung (10-15% Speedup)
try:
    import orjson

    def json_dumps(obj: JsonSerializable, sort_keys: bool = False) -> str:
        """Fast JSON serialization using orjson.

        Args:
            obj: Object to serialize (must be JSON-serializable)
            sort_keys: Sort dictionary keys (uses OPT_SORT_KEYS)
        """
        options = orjson.OPT_SORT_KEYS if sort_keys else 0
        return orjson.dumps(obj, option=options).decode("utf-8")

    def json_loads(s: str) -> JsonSerializable:
        """Fast JSON deserialization using orjson."""
        return orjson.loads(s)

    JSON_LIB = "orjson"
except ImportError:
    import json

    def json_dumps(obj: JsonSerializable, sort_keys: bool = False) -> str:
        """Fallback JSON serialization using stdlib."""
        return json.dumps(obj, sort_keys=sort_keys)

    def json_loads(s: str) -> JsonSerializable:
        """Fallback JSON deserialization using stdlib."""
        return json.loads(s)

    JSON_LIB = "json"

from app.core.config import settings

logger = structlog.get_logger(__name__)


# =============================================================================
# L1 Cache - In-Memory TTL Cache
# =============================================================================

class TTLCache:
    """
    Thread-safe In-Memory Cache mit TTL und Memory-Limit.

    Verwendet OrderedDict für LRU-Eviction und TTL-basierte Expiration.
    Optional: Memory-basiertes Eviction wenn max_memory_mb gesetzt.
    """

    # Default memory limit: 256 MB für L1 Cache
    DEFAULT_MAX_MEMORY_MB = 256

    def __init__(
        self,
        maxsize: int = 100,
        ttl: int = 300,
        max_memory_mb: Optional[float] = None
    ):
        """
        Initialize TTLCache.

        Args:
            maxsize: Maximum number of items in cache
            ttl: Time-to-live in seconds (default 5 minutes)
            max_memory_mb: Maximum memory usage in MB (default: 256MB)
        """
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._max_memory_bytes = int((max_memory_mb or self.DEFAULT_MAX_MEMORY_MB) * 1024 * 1024)
        self._current_memory_bytes = 0
        self._lock = threading.RLock()

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes."""
        try:
            # sys.getsizeof gives shallow size, add estimate for nested objects
            base_size = sys.getsizeof(value)
            if isinstance(value, dict):
                # Estimate dict content size
                for k, v in value.items():
                    base_size += sys.getsizeof(k) + self._estimate_size(v)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    base_size += self._estimate_size(item)
            elif isinstance(value, str):
                # String memory is already captured by getsizeof
                pass
            return base_size
        except Exception as e:
            logger.debug(
                "cache_size_estimation_failed",
                error_type=type(e).__name__,
            )
            # Fallback: assume 1KB per item
            return 1024

    def get(self, key: str) -> Optional[Any]:
        """Get item from cache if not expired."""
        with self._lock:
            if key not in self._cache:
                return None

            item = self._cache[key]
            if time.time() > item['expires']:
                # Expired - update memory tracking
                self._current_memory_bytes -= item.get('size_bytes', 0)
                del self._cache[key]
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            return item['value']

    def set(self, key: str, value: Any) -> None:
        """Set item in cache with TTL and memory limit enforcement."""
        with self._lock:
            # Estimate size of new item
            item_size = self._estimate_size(value)

            # Remove existing item if updating (to adjust memory tracking)
            if key in self._cache:
                old_item = self._cache[key]
                self._current_memory_bytes -= old_item.get('size_bytes', 0)
                del self._cache[key]

            # Evict oldest items if at capacity (count-based)
            while len(self._cache) >= self._maxsize:
                _, evicted = self._cache.popitem(last=False)
                self._current_memory_bytes -= evicted.get('size_bytes', 0)

            # Evict oldest items if memory limit exceeded
            while (self._current_memory_bytes + item_size > self._max_memory_bytes
                   and len(self._cache) > 0):
                _, evicted = self._cache.popitem(last=False)
                self._current_memory_bytes -= evicted.get('size_bytes', 0)

            self._cache[key] = {
                'value': value,
                'expires': time.time() + self._ttl,
                'created': time.time(),
                'size_bytes': item_size,
            }
            self._current_memory_bytes += item_size

    def delete(self, key: str) -> bool:
        """Delete item from cache."""
        with self._lock:
            if key in self._cache:
                item = self._cache[key]
                self._current_memory_bytes -= item.get('size_bytes', 0)
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
            self._current_memory_bytes = 0

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def __len__(self) -> int:
        """Return number of non-expired items."""
        with self._lock:
            now = time.time()
            # Clean expired entries
            expired = [k for k, v in self._cache.items() if now > v['expires']]
            for k in expired:
                item = self._cache[k]
                self._current_memory_bytes -= item.get('size_bytes', 0)
                del self._cache[k]
            return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics including memory usage."""
        with self._lock:
            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl_seconds": self._ttl,
                "memory_bytes": self._current_memory_bytes,
                "memory_mb": round(self._current_memory_bytes / (1024 * 1024), 2),
                "max_memory_mb": round(self._max_memory_bytes / (1024 * 1024), 2),
                "memory_usage_percent": round(
                    (self._current_memory_bytes / self._max_memory_bytes) * 100, 2
                ) if self._max_memory_bytes > 0 else 0,
            }


class OCRCacheService:
    """
    Multi-Level OCR-Ergebnis-Caching Service.

    Cache-Hierarchie:
    - L1: In-Memory TTLCache (5 Minuten, 100 Einträge)
    - L2: Redis (24 Stunden, unbegrenzt)

    Bei L1-Hit: Sofortige Rückgabe (< 1ms)
    Bei L1-Miss, L2-Hit: Redis-Lookup + L1-Promotion
    Bei L2-Miss: OCR-Verarbeitung erforderlich

    Optimierungen:
    - Vereinfachtes Key-Schema (ohne options_hash)
    - Per-Backend Hit-Rate Tracking
    - LRU-Eviction im L1 Cache
    - SECURITY FIX: Model-Version im Cache-Key (verhindert stale results nach Model-Update)
    """

    # Konfiguration - Performance-optimiert
    L1_MAXSIZE = 200      # Maximum L1 Cache Einträge (erhöht von 100)
    L1_TTL = 3600         # L1 TTL: 1 Stunde (erhöht von 5 Minuten für bessere Hit-Rate)
    L1_MAX_MEMORY_MB = 256  # Maximum L1 Memory: 256 MB
    L2_TTL = 86400        # L2 TTL: 24 Stunden

    # SECURITY FIX: Model-Versionen - bei Update hier inkrementieren!
    # Alle caches für betroffenes Backend werden automatisch invalidiert
    MODEL_VERSIONS: Dict[str, str] = {
        "deepseek": "v1.0",      # DeepSeek-Janus-Pro
        "got_ocr": "v2.0",       # GOT-OCR 2.0
        "surya": "v1.1",         # Surya + Docling
        "surya_gpu": "v1.1",     # Surya GPU Variant
        "donut": "v1.0",         # Donut Agent
        "hybrid": "v1.0",        # Hybrid/Ensemble
        "easyocr": "v1.0",       # EasyOCR (wenn hinzugefügt)
    }

    def __init__(
        self,
        redis_client: Any = None,
        l1_maxsize: int = L1_MAXSIZE,
        l1_ttl: int = L1_TTL,
        l1_max_memory_mb: float = L1_MAX_MEMORY_MB,
        l2_ttl: int = L2_TTL
    ):
        """
        Initialize OCRCacheService with Multi-Level Caching.

        Args:
            redis_client: Redis client instance (lazy loaded wenn None)
            l1_maxsize: Maximum L1 cache entries
            l1_ttl: L1 TTL in seconds
            l1_max_memory_mb: Maximum L1 memory in MB (default: 256MB)
            l2_ttl: L2 (Redis) TTL in seconds
        """
        # L1 Cache (Memory) - with count AND memory limit
        self._l1_cache = TTLCache(maxsize=l1_maxsize, ttl=l1_ttl, max_memory_mb=l1_max_memory_mb)

        # L2 Cache (Redis)
        self._redis = redis_client
        self._prefix = "ocr_cache:"
        self._stats_prefix = "ocr_cache_stats:"
        self._default_ttl = l2_ttl
        self._enabled = True

        # Per-Backend Stats
        self._backend_stats: Dict[str, Dict[str, int]] = {}
        self._stats_lock = threading.Lock()

        logger.info(
            "ocr_cache_service_initialized",
            l1_maxsize=l1_maxsize,
            l1_ttl=l1_ttl,
            l1_max_memory_mb=l1_max_memory_mb,
            l2_ttl=l2_ttl
        )

    async def _get_redis(self) -> Optional[Any]:
        """Get Redis client, lazy loading if needed."""
        if self._redis is None:
            try:
                from app.core.rate_limiting import get_redis_storage
                self._redis = await get_redis_storage()
            except Exception as e:
                logger.warning("ocr_cache_redis_unavailable", error=str(e))
                return None
        return self._redis

    def _compute_file_hash(self, content: bytes) -> str:
        """
        Compute SHA256 hash of file content.

        Args:
            content: File content bytes

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(content).hexdigest()

    def _make_cache_key(
        self,
        file_hash: str,
        backend: str,
        language: str,
        options_hash: str = ""
    ) -> str:
        """
        Create cache key for OCR result.

        SECURITY FIX: Inkludiert Model-Version im Key, damit bei Model-Updates
        automatisch neue OCR-Ergebnisse generiert werden (keine stale results).

        Key-Format: {prefix}:{file_hash}:{backend}:{model_version}:{language}[:options_hash]

        Args:
            file_hash: SHA256 hash of file content
            backend: OCR backend used
            language: Target language
            options_hash: Hash of additional options

        Returns:
            Full cache key
        """
        # Model-Version aus Dictionary holen (Default "v0" falls unbekannt)
        model_version = self.MODEL_VERSIONS.get(backend.lower(), "v0")

        key_parts = [self._prefix, file_hash, backend, model_version, language]
        if options_hash:
            key_parts.append(options_hash)
        return ":".join(key_parts)

    async def get_cached_result(
        self,
        content: bytes,
        backend: str,
        language: str = "de",
        options: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached OCR result using Multi-Level Cache.

        Cache Lookup Order:
        1. L1 (Memory) - instant lookup
        2. L2 (Redis) - network lookup + L1 promotion

        Args:
            content: File content bytes
            backend: OCR backend to use
            language: Target language
            options: Additional OCR options (ignored for key, kept for compatibility)

        Returns:
            Cached result dict or None
        """
        if not self._enabled:
            return None

        file_hash = self._compute_file_hash(content)
        # Vereinfachter Key: nur hash:backend:language (ohne options)
        cache_key = self._make_cache_key(file_hash, backend, language)

        # Step 1: L1 Cache Lookup (Memory)
        l1_result = self._l1_cache.get(cache_key)
        if l1_result is not None:
            self._record_backend_hit(backend, "l1")
            await self._record_hit(file_hash)
            logger.debug(
                "ocr_cache_l1_hit",
                file_hash=file_hash[:16],
                backend=backend,
            )
            return l1_result

        # Step 2: L2 Cache Lookup (Redis)
        redis = await self._get_redis()
        if not redis:
            self._record_backend_miss(backend)
            return None

        try:
            # Timeout von 2 Sekunden für Redis-Abfrage verhindert Blockierung
            cached = await asyncio.wait_for(redis.get(cache_key), timeout=2.0)
            if cached:
                data = json_loads(cached)
                result = data.get("result")

                # L1 Promotion - speichere in Memory Cache
                if result:
                    self._l1_cache.set(cache_key, result)

                self._record_backend_hit(backend, "l2")
                await self._record_hit(file_hash)
                logger.debug(
                    "ocr_cache_l2_hit",
                    file_hash=file_hash[:16],
                    backend=backend,
                    cached_at=data.get("cached_at"),
                    promoted_to_l1=True,
                )
                return result
            else:
                self._record_backend_miss(backend)
                await self._record_miss(file_hash)
        except asyncio.TimeoutError:
            logger.warning(
                "ocr_cache_redis_timeout",
                cache_key=cache_key[:32],
                timeout_seconds=2.0,
            )
            self._record_backend_miss(backend)
        except Exception as e:
            logger.warning("ocr_cache_get_error", error=str(e))
            self._record_backend_miss(backend)

        return None

    def _record_backend_hit(self, backend: str, level: str) -> None:
        """Record cache hit for specific backend and level."""
        with self._stats_lock:
            if backend not in self._backend_stats:
                self._backend_stats[backend] = {
                    "l1_hits": 0,
                    "l2_hits": 0,
                    "misses": 0,
                }
            if level == "l1":
                self._backend_stats[backend]["l1_hits"] += 1
            elif level == "l2":
                self._backend_stats[backend]["l2_hits"] += 1

        # Record to Prometheus
        try:
            from app.services.gpu_metrics_service import get_gpu_metrics_service
            metrics = get_gpu_metrics_service()
            metrics.record_cache_operation(operation="hit", level=level)
        except Exception as e:
            logger.debug(
                "cache_metrics_recording_failed",
                operation="hit",
                level=level,
                error_type=type(e).__name__,
            )

    def _record_backend_miss(self, backend: str) -> None:
        """Record cache miss for specific backend."""
        with self._stats_lock:
            if backend not in self._backend_stats:
                self._backend_stats[backend] = {
                    "l1_hits": 0,
                    "l2_hits": 0,
                    "misses": 0,
                }
            self._backend_stats[backend]["misses"] += 1

        # Record to Prometheus
        try:
            from app.services.gpu_metrics_service import get_gpu_metrics_service
            metrics = get_gpu_metrics_service()
            metrics.record_cache_operation(operation="miss", level="l2")
        except Exception as e:
            logger.debug(
                "cache_metrics_recording_failed",
                operation="miss",
                level="l2",
                error_type=type(e).__name__,
            )

    async def cache_result(
        self,
        content: bytes,
        backend: str,
        result: Dict[str, Any],
        language: str = "de",
        options: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache OCR result in both L1 (Memory) and L2 (Redis).

        Args:
            content: File content bytes
            backend: OCR backend used
            result: OCR result to cache
            language: Target language
            options: Additional OCR options (stored but not in key)
            ttl: L2 Cache TTL in seconds (default 24h)

        Returns:
            True if cached successfully in at least L1
        """
        if not self._enabled:
            return False

        file_hash = self._compute_file_hash(content)
        # Vereinfachter Key: nur hash:backend:language
        cache_key = self._make_cache_key(file_hash, backend, language)
        cache_ttl = ttl or self._default_ttl

        # Step 1: L1 Cache (Memory) - always store
        self._l1_cache.set(cache_key, result)
        l1_success = True

        # Step 2: L2 Cache (Redis) - store if available
        l2_success = False
        redis = await self._get_redis()
        if redis:
            try:
                cache_data = {
                    "result": result,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "file_hash": file_hash,
                    "backend": backend,
                    "language": language,
                    "options": options,
                }
                await redis.set(cache_key, json_dumps(cache_data), ex=cache_ttl)
                l2_success = True
            except Exception as e:
                logger.warning("ocr_cache_l2_set_error", error=str(e))

        logger.debug(
            "ocr_result_cached",
            file_hash=file_hash[:16],
            backend=backend,
            l1_success=l1_success,
            l2_success=l2_success,
            l2_ttl=cache_ttl if l2_success else None,
        )

        return l1_success or l2_success

    async def invalidate(
        self,
        content: bytes,
        backend: Optional[str] = None,
        language: Optional[str] = None
    ) -> int:
        """
        Invalidate cached results for a file in both L1 and L2 cache.

        Args:
            content: File content bytes
            backend: Optional specific backend to invalidate
            language: Optional specific language to invalidate

        Returns:
            Number of keys deleted (L1 + L2 combined)
        """
        file_hash = self._compute_file_hash(content)
        deleted_count = 0

        # Step 1: Invalidate L1 Cache (Memory)
        # Build specific key if backend and language provided
        if backend and language:
            l1_key = self._make_cache_key(file_hash, backend, language)
            if self._l1_cache.delete(l1_key):
                deleted_count += 1
                logger.debug(
                    "ocr_cache_l1_invalidated",
                    file_hash=file_hash[:16],
                    backend=backend,
                    language=language,
                )
        else:
            # Clear all L1 entries for this file (scan through cache)
            # Note: L1 cache is small, full scan is acceptable
            with self._l1_cache._lock:
                keys_to_delete = [
                    k for k in self._l1_cache._cache.keys()
                    if k.startswith(f"{self._prefix}{file_hash}:")
                ]
                for k in keys_to_delete:
                    del self._l1_cache._cache[k]
                    deleted_count += 1
            if keys_to_delete:
                logger.debug(
                    "ocr_cache_l1_bulk_invalidated",
                    file_hash=file_hash[:16],
                    keys_deleted=len(keys_to_delete),
                )

        # Step 2: Invalidate L2 Cache (Redis)
        redis = await self._get_redis()
        if not redis:
            return deleted_count

        # Build pattern for deletion
        # Key-Format: {prefix}:{file_hash}:{backend}:{model_version}:{language}[:options_hash]
        if backend and language:
            # Spezifisch: exakte Key mit Wildcard für options
            pattern = self._make_cache_key(file_hash, backend, language, "*")
        elif backend:
            # Alle Sprachen für dieses Backend (version ist Teil des Keys)
            pattern = f"{self._prefix}{file_hash}:{backend}:*"
        elif language:
            # Alle Backends für diese Sprache (muss alle Backends/Versionen matchen)
            pattern = f"{self._prefix}{file_hash}:*:*:{language}*"
        else:
            # Alle Caches für diesen File-Hash
            pattern = f"{self._prefix}{file_hash}:*"

        try:
            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                l2_deleted = await redis.delete(*keys)
                deleted_count += l2_deleted
                logger.info(
                    "ocr_cache_invalidated",
                    file_hash=file_hash[:16],
                    l1_deleted=deleted_count - l2_deleted,
                    l2_deleted=l2_deleted,
                    total_deleted=deleted_count,
                )
            return deleted_count
        except Exception as e:
            logger.warning("ocr_cache_invalidate_error", error=str(e))
            return deleted_count

    async def _record_hit(self, file_hash: str) -> None:
        """Record cache hit in stats."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.incr(f"{self._stats_prefix}hits")
                await redis.incr(f"{self._stats_prefix}hits:{file_hash[:8]}")
            except Exception as e:
                # Stats-Fehler sind nicht kritisch, aber loggen für Debugging
                logger.debug(
                    "ocr_cache_stats_hit_failed",
                    file_hash=file_hash[:8],
                    error=str(e),
                )

    async def _record_miss(self, file_hash: str) -> None:
        """Record cache miss in stats."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.incr(f"{self._stats_prefix}misses")
            except Exception as e:
                # Stats-Fehler sind nicht kritisch, aber loggen für Debugging
                logger.debug(
                    "ocr_cache_stats_miss_failed",
                    file_hash=file_hash[:8],
                    error=str(e),
                )

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive multi-level cache statistics.

        Returns:
            Dict with L1 stats, L2 stats, per-backend stats, and overall metrics
        """
        # L1 Cache Stats (Memory)
        l1_stats = self._l1_cache.stats()

        # Per-Backend Stats (local tracking)
        with self._stats_lock:
            backend_stats = {}
            for backend, stats in self._backend_stats.items():
                total_hits = stats["l1_hits"] + stats["l2_hits"]
                total_requests = total_hits + stats["misses"]
                hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
                backend_stats[backend] = {
                    "l1_hits": stats["l1_hits"],
                    "l2_hits": stats["l2_hits"],
                    "misses": stats["misses"],
                    "total_requests": total_requests,
                    "hit_rate_percent": round(hit_rate, 2),
                }

        # L2 Cache Stats (Redis)
        redis = await self._get_redis()
        if not redis:
            return {
                "enabled": self._enabled,
                "redis_available": False,
                "l1_cache": l1_stats,
                "l2_cache": {"available": False},
                "per_backend": backend_stats,
            }

        try:
            l2_hits = int(await redis.get(f"{self._stats_prefix}hits") or 0)
            l2_misses = int(await redis.get(f"{self._stats_prefix}misses") or 0)
            l2_total = l2_hits + l2_misses
            l2_hit_rate = (l2_hits / l2_total * 100) if l2_total > 0 else 0

            # Aggregate totals from per-backend stats
            total_l1_hits = sum(s.get("l1_hits", 0) for s in backend_stats.values())
            total_l2_hits = sum(s.get("l2_hits", 0) for s in backend_stats.values())
            total_misses = sum(s.get("misses", 0) for s in backend_stats.values())
            total_requests = total_l1_hits + total_l2_hits + total_misses

            overall_hit_rate = (
                ((total_l1_hits + total_l2_hits) / total_requests * 100)
                if total_requests > 0 else 0
            )

            return {
                "enabled": self._enabled,
                "redis_available": True,
                "l1_cache": {
                    **l1_stats,
                    "hits": total_l1_hits,
                    "description": "In-Memory TTL Cache (schnellste Antwortzeit)",
                },
                "l2_cache": {
                    "available": True,
                    "hits": l2_hits,
                    "misses": l2_misses,
                    "total_requests": l2_total,
                    "hit_rate_percent": round(l2_hit_rate, 2),
                    "ttl_seconds": self._default_ttl,
                    "description": "Redis Cache (persistente Speicherung)",
                },
                "per_backend": backend_stats,
                "overall": {
                    "total_l1_hits": total_l1_hits,
                    "total_l2_hits": total_l2_hits,
                    "total_misses": total_misses,
                    "total_requests": total_requests,
                    "combined_hit_rate_percent": round(overall_hit_rate, 2),
                },
            }
        except Exception as e:
            logger.warning("ocr_cache_stats_error", error=str(e))
            return {
                "enabled": self._enabled,
                "error": str(e),
                "l1_cache": l1_stats,
                "per_backend": backend_stats,
            }

    async def clear_stats(self) -> bool:
        """Clear all cache statistics (L1, L2, and per-backend)."""
        # Clear per-backend stats (local)
        with self._stats_lock:
            self._backend_stats.clear()

        # Clear L2 stats (Redis)
        redis = await self._get_redis()
        if not redis:
            logger.info("ocr_cache_local_stats_cleared")
            return True  # Local stats cleared successfully

        try:
            await redis.delete(f"{self._stats_prefix}hits")
            await redis.delete(f"{self._stats_prefix}misses")
            logger.info("ocr_cache_all_stats_cleared")
            return True
        except Exception as e:
            logger.warning("ocr_cache_stats_clear_error", error=str(e))
            return False


# Singleton instance
_ocr_cache_service: Optional[OCRCacheService] = None


def get_ocr_cache_service() -> OCRCacheService:
    """Get singleton OCRCacheService instance."""
    global _ocr_cache_service
    if _ocr_cache_service is None:
        _ocr_cache_service = OCRCacheService()
    return _ocr_cache_service


async def get_cached_ocr_result(
    content: bytes,
    backend: str,
    language: str = "de",
    options: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Convenience function to get cached OCR result."""
    return await get_ocr_cache_service().get_cached_result(
        content, backend, language, options
    )


async def cache_ocr_result(
    content: bytes,
    backend: str,
    result: Dict[str, Any],
    language: str = "de",
    options: Optional[Dict[str, Any]] = None,
    ttl: Optional[int] = None
) -> bool:
    """Convenience function to cache OCR result."""
    return await get_ocr_cache_service().cache_result(
        content, backend, result, language, options, ttl
    )
