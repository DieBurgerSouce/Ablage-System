"""Query Cache - Redis-basiertes Caching fuer NLQ-Queries."""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


@dataclass
class CachedResult:
    """Gecachtes Query-Ergebnis."""

    query_hash: str
    natural_query: str
    generated_sql: str
    columns: List[str]
    rows: List[List[Any]]  # JSON-serializable
    visualization_type: str
    text_summary: str
    total_rows: int
    confidence: float
    cached_at: float  # Unix timestamp


class QueryCache:
    """Redis-based cache for NLQ query results.

    Cache Strategy:
        - Cache key: SHA256 hash of (natural_query + company_id)
        - TTL: 5 minutes (configurable)
        - Invalidation: Manual or TTL expiry
    """

    DEFAULT_TTL_SECONDS: int = 300  # 5 minutes

    def __init__(self, redis: Redis):
        """Initialize query cache.

        Args:
            redis: Redis async client
        """
        self.redis = redis
        self._key_prefix = "nlq:cache:"

    def _compute_hash(self, natural_query: str, company_id: str) -> str:
        """Compute cache key hash.

        Args:
            natural_query: Natural language query
            company_id: Company ID for multi-tenant isolation

        Returns:
            SHA256 hash as cache key
        """
        # Normalize query (lowercase, strip whitespace)
        normalized = natural_query.lower().strip()
        # Include company_id for multi-tenant isolation
        key_data = f"{normalized}:{company_id}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    async def get_cached(
        self, natural_query: str, company_id: str
    ) -> Optional[CachedResult]:
        """Get cached query result.

        Args:
            natural_query: Natural language query
            company_id: Company ID

        Returns:
            CachedResult if found, None otherwise
        """
        query_hash = self._compute_hash(natural_query, company_id)
        cache_key = f"{self._key_prefix}{query_hash}"

        try:
            cached_data = await self.redis.get(cache_key)
            if not cached_data:
                logger.debug("cache_miss", query_hash=query_hash)
                return None

            # Deserialize
            data: Dict[str, Any] = json.loads(cached_data)
            result = CachedResult(**data)

            logger.info(
                "cache_hit",
                query_hash=query_hash,
                total_rows=result.total_rows,
            )
            return result

        except Exception as e:
            logger.warning(
                "cache_get_failed",
                query_hash=query_hash,
                error=str(e),
            )
            return None

    async def set_cached(
        self,
        natural_query: str,
        company_id: str,
        generated_sql: str,
        columns: List[str],
        rows: List[tuple],
        visualization_type: str,
        text_summary: str,
        confidence: float,
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Cache query result.

        Args:
            natural_query: Natural language query
            company_id: Company ID
            generated_sql: Generated SQL
            columns: Result columns
            rows: Result rows
            visualization_type: Recommended visualization
            text_summary: Text summary
            confidence: Query confidence
            ttl: Time to live in seconds
        """
        import time

        query_hash = self._compute_hash(natural_query, company_id)
        cache_key = f"{self._key_prefix}{query_hash}"

        # Convert rows to JSON-serializable format
        json_rows: List[List[Any]] = [list(row) for row in rows]

        cached_result = CachedResult(
            query_hash=query_hash,
            natural_query=natural_query,
            generated_sql=generated_sql,
            columns=columns,
            rows=json_rows,
            visualization_type=visualization_type,
            text_summary=text_summary,
            total_rows=len(rows),
            confidence=confidence,
            cached_at=time.time(),
        )

        try:
            # Serialize to JSON
            cache_data = json.dumps(asdict(cached_result))

            # Store with TTL
            await self.redis.setex(cache_key, ttl, cache_data)

            logger.info(
                "cache_set",
                query_hash=query_hash,
                ttl=ttl,
                total_rows=len(rows),
            )

        except Exception as e:
            logger.warning(
                "cache_set_failed",
                query_hash=query_hash,
                error=str(e),
            )

    async def invalidate_cached(
        self, natural_query: str, company_id: str
    ) -> bool:
        """Invalidate cached query result.

        Args:
            natural_query: Natural language query
            company_id: Company ID

        Returns:
            True if cache entry was deleted
        """
        query_hash = self._compute_hash(natural_query, company_id)
        cache_key = f"{self._key_prefix}{query_hash}"

        try:
            deleted = await self.redis.delete(cache_key)
            if deleted:
                logger.info("cache_invalidated", query_hash=query_hash)
            return bool(deleted)

        except Exception as e:
            logger.warning(
                "cache_invalidate_failed",
                query_hash=query_hash,
                error=str(e),
            )
            return False

    async def invalidate_all(self, company_id: str) -> int:
        """Invalidate all cached queries for a company.

        Args:
            company_id: Company ID

        Returns:
            Number of cache entries deleted
        """
        try:
            # Scan for all cache keys (note: this is O(N) operation)
            pattern = f"{self._key_prefix}*"
            deleted_count = 0

            async for key in self.redis.scan_iter(match=pattern):
                # Note: We can't filter by company_id in key,
                # so we delete all NLQ cache entries
                await self.redis.delete(key)
                deleted_count += 1

            logger.info(
                "cache_invalidate_all",
                company_id=company_id,
                deleted_count=deleted_count,
            )
            return deleted_count

        except Exception as e:
            logger.warning(
                "cache_invalidate_all_failed",
                company_id=company_id,
                error=str(e),
            )
            return 0

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache stats
        """
        try:
            pattern = f"{self._key_prefix}*"
            cache_keys = [
                key async for key in self.redis.scan_iter(match=pattern)
            ]
            total_entries = len(cache_keys)

            # Get memory usage (approximate)
            total_size = 0
            for key in cache_keys[:100]:  # Sample first 100 keys
                size = await self.redis.memory_usage(key) or 0
                total_size += size

            avg_size = total_size // len(cache_keys) if cache_keys else 0
            estimated_total_size = avg_size * total_entries

            return {
                "total_entries": total_entries,
                "estimated_size_bytes": estimated_total_size,
                "estimated_size_mb": round(
                    estimated_total_size / (1024 * 1024), 2
                ),
            }

        except Exception as e:
            logger.warning("cache_stats_failed", error=str(e))
            return {"total_entries": 0, "estimated_size_bytes": 0}
