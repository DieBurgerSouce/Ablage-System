"""
OCR Result Caching Service.

Cached OCR-Ergebnisse in Redis, um wiederholte Verarbeitung
identischer Dokumente zu vermeiden.

Cache-Key basiert auf:
- Datei-Hash (SHA256)
- OCR-Backend
- Sprache
- Optionen

Feinpoliert und durchdacht - Ressourcenschonende OCR.
"""

import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class OCRCacheService:
    """
    Service für OCR-Ergebnis-Caching.

    Speichert OCR-Ergebnisse in Redis basierend auf Datei-Hash,
    um teure Wiederverarbeitung zu vermeiden.
    """

    def __init__(self, redis_client: Any = None):
        """
        Initialize OCRCacheService.

        Args:
            redis_client: Redis client instance (lazy loaded wenn None)
        """
        self._redis = redis_client
        self._prefix = "ocr_cache:"
        self._stats_prefix = "ocr_cache_stats:"
        self._default_ttl = 86400  # 24 Stunden
        self._enabled = True

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

        Args:
            file_hash: SHA256 hash of file content
            backend: OCR backend used
            language: Target language
            options_hash: Hash of additional options

        Returns:
            Full cache key
        """
        key_parts = [self._prefix, file_hash, backend, language]
        if options_hash:
            key_parts.append(options_hash)
        return ":".join(key_parts)

    def _hash_options(self, options: Optional[Dict[str, Any]]) -> str:
        """Hash options dict for cache key."""
        if not options:
            return ""
        # Sortiere Keys für konsistente Hashes
        sorted_opts = json.dumps(options, sort_keys=True)
        return hashlib.md5(sorted_opts.encode()).hexdigest()[:8]

    async def get_cached_result(
        self,
        content: bytes,
        backend: str,
        language: str = "de",
        options: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached OCR result if available.

        Args:
            content: File content bytes
            backend: OCR backend to use
            language: Target language
            options: Additional OCR options

        Returns:
            Cached result dict or None
        """
        if not self._enabled:
            return None

        redis = await self._get_redis()
        if not redis:
            return None

        file_hash = self._compute_file_hash(content)
        options_hash = self._hash_options(options)
        cache_key = self._make_cache_key(file_hash, backend, language, options_hash)

        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                # Update stats
                await self._record_hit(file_hash)
                logger.debug(
                    "ocr_cache_hit",
                    file_hash=file_hash[:16],
                    backend=backend,
                    cached_at=data.get("cached_at"),
                )
                return data.get("result")
            else:
                await self._record_miss(file_hash)
        except Exception as e:
            logger.warning("ocr_cache_get_error", error=str(e))

        return None

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
        Cache OCR result.

        Args:
            content: File content bytes
            backend: OCR backend used
            result: OCR result to cache
            language: Target language
            options: Additional OCR options
            ttl: Cache TTL in seconds (default 24h)

        Returns:
            True if cached successfully
        """
        if not self._enabled:
            return False

        redis = await self._get_redis()
        if not redis:
            return False

        file_hash = self._compute_file_hash(content)
        options_hash = self._hash_options(options)
        cache_key = self._make_cache_key(file_hash, backend, language, options_hash)
        cache_ttl = ttl or self._default_ttl

        try:
            cache_data = {
                "result": result,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "file_hash": file_hash,
                "backend": backend,
                "language": language,
                "options": options,
            }
            await redis.set(cache_key, json.dumps(cache_data), ex=cache_ttl)
            logger.debug(
                "ocr_result_cached",
                file_hash=file_hash[:16],
                backend=backend,
                ttl=cache_ttl,
            )
            return True
        except Exception as e:
            logger.warning("ocr_cache_set_error", error=str(e))
            return False

    async def invalidate(
        self,
        content: bytes,
        backend: Optional[str] = None,
        language: Optional[str] = None
    ) -> int:
        """
        Invalidate cached results for a file.

        Args:
            content: File content bytes
            backend: Optional specific backend to invalidate
            language: Optional specific language to invalidate

        Returns:
            Number of keys deleted
        """
        redis = await self._get_redis()
        if not redis:
            return 0

        file_hash = self._compute_file_hash(content)

        # Build pattern for deletion
        if backend and language:
            pattern = self._make_cache_key(file_hash, backend, language, "*")
        elif backend:
            pattern = f"{self._prefix}{file_hash}:{backend}:*"
        elif language:
            pattern = f"{self._prefix}{file_hash}:*:{language}:*"
        else:
            pattern = f"{self._prefix}{file_hash}:*"

        try:
            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await redis.delete(*keys)
                logger.info(
                    "ocr_cache_invalidated",
                    file_hash=file_hash[:16],
                    keys_deleted=deleted,
                )
                return deleted
            return 0
        except Exception as e:
            logger.warning("ocr_cache_invalidate_error", error=str(e))
            return 0

    async def _record_hit(self, file_hash: str) -> None:
        """Record cache hit in stats."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.incr(f"{self._stats_prefix}hits")
                await redis.incr(f"{self._stats_prefix}hits:{file_hash[:8]}")
            except Exception:
                pass

    async def _record_miss(self, file_hash: str) -> None:
        """Record cache miss in stats."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.incr(f"{self._stats_prefix}misses")
            except Exception:
                pass

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate
        """
        redis = await self._get_redis()
        if not redis:
            return {"enabled": False, "redis_available": False}

        try:
            hits = int(await redis.get(f"{self._stats_prefix}hits") or 0)
            misses = int(await redis.get(f"{self._stats_prefix}misses") or 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0

            return {
                "enabled": self._enabled,
                "redis_available": True,
                "hits": hits,
                "misses": misses,
                "total_requests": total,
                "hit_rate_percent": round(hit_rate, 2),
                "default_ttl_seconds": self._default_ttl,
            }
        except Exception as e:
            logger.warning("ocr_cache_stats_error", error=str(e))
            return {"enabled": self._enabled, "error": str(e)}

    async def clear_stats(self) -> bool:
        """Clear cache statistics."""
        redis = await self._get_redis()
        if not redis:
            return False

        try:
            await redis.delete(f"{self._stats_prefix}hits")
            await redis.delete(f"{self._stats_prefix}misses")
            logger.info("ocr_cache_stats_cleared")
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
