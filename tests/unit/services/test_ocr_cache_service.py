# -*- coding: utf-8 -*-
"""
Unit tests for OCR Cache Service.

Tests for:
- TTLCache: LRU eviction, TTL expiration, thread safety
- OCRCacheService: Multi-level caching, Redis fallback, statistics
"""

import asyncio
import json
import pytest
import time
import threading
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.ocr_cache_service import (
    TTLCache,
    OCRCacheService,
)


# =============================================================================
# TTLCache Tests
# =============================================================================

class TestTTLCache:
    """Tests for in-memory TTL cache."""

    def test_init_defaults(self):
        """Test default initialization."""
        cache = TTLCache()

        stats = cache.stats()
        assert stats["maxsize"] == 100
        assert stats["ttl_seconds"] == 300
        assert stats["size"] == 0

    def test_init_custom_params(self):
        """Test custom initialization parameters."""
        cache = TTLCache(maxsize=50, ttl=60)

        stats = cache.stats()
        assert stats["maxsize"] == 50
        assert stats["ttl_seconds"] == 60

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = TTLCache(maxsize=10, ttl=60)

        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

    def test_get_missing_key(self):
        """Test get with non-existent key returns None."""
        cache = TTLCache()

        result = cache.get("nonexistent")

        assert result is None

    def test_ttl_expiration(self):
        """Test that items expire after TTL."""
        cache = TTLCache(maxsize=10, ttl=1)  # 1 second TTL

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)

        result = cache.get("key1")
        assert result is None

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = TTLCache(maxsize=3, ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key4, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Still present (recently accessed)
        assert cache.get("key2") is None      # Evicted (LRU)
        assert cache.get("key3") == "value3"  # Still present
        assert cache.get("key4") == "value4"  # Newly added

    def test_delete(self):
        """Test delete operation."""
        cache = TTLCache()

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        deleted = cache.delete("key1")

        assert deleted is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self):
        """Test delete of non-existent key returns False."""
        cache = TTLCache()

        deleted = cache.delete("nonexistent")

        assert deleted is False

    def test_clear(self):
        """Test clear operation removes all items."""
        cache = TTLCache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert len(cache) == 2

        cache.clear()

        assert len(cache) == 0
        assert cache.get("key1") is None

    def test_contains(self):
        """Test __contains__ operator."""
        cache = TTLCache(maxsize=10, ttl=60)

        cache.set("key1", "value1")

        assert "key1" in cache
        assert "key2" not in cache

    def test_len_excludes_expired(self):
        """Test __len__ excludes expired items."""
        cache = TTLCache(maxsize=10, ttl=1)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        assert len(cache) == 2

        time.sleep(1.1)

        assert len(cache) == 0

    def test_thread_safety(self):
        """Test thread safety with concurrent operations."""
        cache = TTLCache(maxsize=100, ttl=60)
        errors = []

        def writer(thread_id):
            try:
                for i in range(50):
                    cache.set(f"key_{thread_id}_{i}", f"value_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)

        def reader(thread_id):
            try:
                for i in range(50):
                    cache.get(f"key_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_complex_values(self):
        """Test caching complex values (dicts, lists)."""
        cache = TTLCache()

        complex_value = {
            "text": "OCR result",
            "confidence": 0.95,
            "entities": [{"type": "PERSON", "value": "Max Mustermann"}],
            "metadata": {"backend": "deepseek", "language": "de"}
        }

        cache.set("ocr_result", complex_value)
        result = cache.get("ocr_result")

        assert result == complex_value
        assert result["confidence"] == 0.95


# =============================================================================
# OCRCacheService Tests
# =============================================================================

class TestOCRCacheService:
    """Tests for OCR Cache Service."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()  # Uses .set() with ex= parameter
        redis.delete = AsyncMock(return_value=1)
        redis.incr = AsyncMock()
        return redis

    @pytest.fixture
    def cache_service(self, mock_redis):
        """Create OCRCacheService with mock Redis."""
        return OCRCacheService(
            redis_client=mock_redis,
            l1_maxsize=10,
            l1_ttl=60,
            l2_ttl=3600
        )

    @pytest.fixture
    def sample_content(self):
        """Sample file content for testing."""
        return b"Sample PDF content for OCR testing"

    @pytest.fixture
    def sample_ocr_result(self):
        """Sample OCR result."""
        return {
            "text": "Dies ist ein Testdokument mit deutschem Text.",
            "confidence": 0.92,
            "entities": [
                {"type": "LOCATION", "value": "Deutschland"}
            ],
            "backend": "deepseek",
            "processing_time_ms": 1234
        }

    def test_init(self, mock_redis):
        """Test service initialization."""
        service = OCRCacheService(
            redis_client=mock_redis,
            l1_maxsize=50,
            l1_ttl=120,
            l2_ttl=7200
        )

        assert service._enabled is True
        assert service._default_ttl == 7200

    def test_compute_file_hash(self, cache_service, sample_content):
        """Test file hash computation."""
        hash1 = cache_service._compute_file_hash(sample_content)
        hash2 = cache_service._compute_file_hash(sample_content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

        # Different content should produce different hash
        hash3 = cache_service._compute_file_hash(b"Different content")
        assert hash1 != hash3

    def test_make_cache_key(self, cache_service):
        """Test cache key generation."""
        key = cache_service._make_cache_key(
            file_hash="abc123",
            backend="deepseek",
            language="de"
        )

        assert "ocr_cache:" in key
        assert "abc123" in key
        assert "deepseek" in key
        assert "de" in key

    def test_make_cache_key_includes_model_version(self, cache_service):
        """Test cache key includes model version for cache invalidation on updates."""
        # SECURITY FIX: Model-Version muss im Key sein
        key_deepseek = cache_service._make_cache_key(
            file_hash="abc123",
            backend="deepseek",
            language="de"
        )
        key_got_ocr = cache_service._make_cache_key(
            file_hash="abc123",
            backend="got_ocr",
            language="de"
        )

        # Verify model versions are in keys
        assert ":v1.0:" in key_deepseek  # deepseek v1.0
        assert ":v2.0:" in key_got_ocr   # got_ocr v2.0

        # Keys fuer gleichen file_hash aber unterschiedliche Backends muessen unterschiedlich sein
        assert key_deepseek != key_got_ocr

        # Key-Format: {prefix}:{file_hash}:{backend}:{model_version}:{language}
        # Prefix ist "ocr_cache:" daher split ergibt: ["ocr_cache", "", "abc123", ...]
        key_parts = key_deepseek.split(":")
        assert key_parts[0] == "ocr_cache"
        # key_parts[1] ist leer weil prefix mit : endet
        assert key_parts[2] == "abc123"
        assert key_parts[3] == "deepseek"
        assert key_parts[4] == "v1.0"
        assert key_parts[5] == "de"

    def test_make_cache_key_unknown_backend_uses_default_version(self, cache_service):
        """Unknown backend uses default version v0."""
        key = cache_service._make_cache_key(
            file_hash="abc123",
            backend="unknown_backend",
            language="de"
        )

        assert ":v0:" in key  # Default version for unknown backends

    @pytest.mark.asyncio
    async def test_l1_cache_hit(self, cache_service, sample_content, sample_ocr_result):
        """Test L1 (memory) cache hit."""
        # Manually populate L1 cache
        file_hash = cache_service._compute_file_hash(sample_content)
        cache_key = cache_service._make_cache_key(file_hash, "deepseek", "de")
        cache_service._l1_cache.set(cache_key, sample_ocr_result)

        # Get should return from L1 without hitting Redis
        result = await cache_service.get_cached_result(
            content=sample_content,
            backend="deepseek",
            language="de"
        )

        assert result == sample_ocr_result
        # Redis should NOT have been called (L1 hit)
        cache_service._redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_l2_cache_hit_and_l1_promotion(
        self, cache_service, sample_content, sample_ocr_result, mock_redis
    ):
        """Test L2 (Redis) cache hit promotes to L1."""
        # Setup Redis to return cached result
        cached_data = json.dumps({
            "result": sample_ocr_result,
            "cached_at": "2025-01-01T00:00:00Z"
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        # First call - L1 miss, L2 hit
        result = await cache_service.get_cached_result(
            content=sample_content,
            backend="deepseek",
            language="de"
        )

        assert result == sample_ocr_result

        # Verify L1 was populated (promotion)
        file_hash = cache_service._compute_file_hash(sample_content)
        cache_key = cache_service._make_cache_key(file_hash, "deepseek", "de")
        l1_result = cache_service._l1_cache.get(cache_key)
        assert l1_result == sample_ocr_result

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_service, sample_content, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_result(
            content=sample_content,
            backend="deepseek",
            language="de"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_result_stores_in_both_levels(
        self, cache_service, sample_content, sample_ocr_result, mock_redis
    ):
        """Test caching stores in both L1 and L2."""
        await cache_service.cache_result(
            content=sample_content,
            backend="deepseek",
            language="de",
            result=sample_ocr_result
        )

        # Verify L1 was populated
        file_hash = cache_service._compute_file_hash(sample_content)
        cache_key = cache_service._make_cache_key(file_hash, "deepseek", "de")
        l1_result = cache_service._l1_cache.get(cache_key)
        assert l1_result == sample_ocr_result

        # Verify Redis set was called
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_unavailable_fallback(self, sample_content, sample_ocr_result):
        """Test graceful handling when Redis is unavailable."""
        # Create service without Redis
        service = OCRCacheService(redis_client=None)

        # Mock the lazy loader to fail
        with patch.object(service, '_get_redis', return_value=None):
            result = await service.get_cached_result(
                content=sample_content,
                backend="deepseek",
                language="de"
            )

            assert result is None  # Should return None, not raise

    @pytest.mark.asyncio
    async def test_disabled_cache(self, cache_service, sample_content):
        """Test that disabled cache returns None."""
        cache_service._enabled = False

        result = await cache_service.get_cached_result(
            content=sample_content,
            backend="deepseek",
            language="de"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_removes_from_both_levels(
        self, cache_service, sample_content, sample_ocr_result, mock_redis
    ):
        """Test invalidation removes from L1 and L2."""
        # First cache the result
        await cache_service.cache_result(
            content=sample_content,
            backend="deepseek",
            result=sample_ocr_result,
            language="de"
        )

        # Then invalidate
        deleted = await cache_service.invalidate(
            content=sample_content,
            backend="deepseek",
            language="de"
        )

        # Verify L1 is empty
        file_hash = cache_service._compute_file_hash(sample_content)
        cache_key = cache_service._make_cache_key(file_hash, "deepseek", "de")
        assert cache_service._l1_cache.get(cache_key) is None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache_service, mock_redis):
        """Test statistics retrieval."""
        # Mock Redis responses for stats
        mock_redis.get = AsyncMock(return_value="0")

        stats = await cache_service.get_stats()

        assert "l1_cache" in stats
        assert "enabled" in stats
        assert stats["enabled"] is True

    def test_backend_hit_tracking(self, cache_service):
        """Test per-backend hit rate tracking."""
        # Record some hits and misses using internal methods
        cache_service._record_backend_hit("deepseek", "l1")
        cache_service._record_backend_hit("deepseek", "l1")
        cache_service._record_backend_hit("deepseek", "l2")
        cache_service._record_backend_miss("deepseek")

        cache_service._record_backend_hit("got_ocr", "l1")
        cache_service._record_backend_miss("got_ocr")
        cache_service._record_backend_miss("got_ocr")

        # Access internal stats directly
        stats = cache_service._backend_stats

        # DeepSeek: 2 l1_hits + 1 l2_hit = 3 hits, 1 miss
        assert stats["deepseek"]["l1_hits"] == 2
        assert stats["deepseek"]["l2_hits"] == 1
        assert stats["deepseek"]["misses"] == 1

        # GOT-OCR: 1 l1_hit, 2 misses
        assert stats["got_ocr"]["l1_hits"] == 1
        assert stats["got_ocr"]["misses"] == 2


class TestOCRCacheServiceEdgeCases:
    """Edge case tests for OCR Cache Service."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_empty_content(self, mock_redis):
        """Test handling of empty content."""
        service = OCRCacheService(redis_client=mock_redis)

        result = await service.get_cached_result(
            content=b"",
            backend="deepseek",
            language="de"
        )

        # Should handle gracefully (empty hash is still valid)
        assert result is None or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_large_content_hash(self, mock_redis):
        """Test hashing of large content."""
        service = OCRCacheService(redis_client=mock_redis)

        # 10MB content
        large_content = b"x" * (10 * 1024 * 1024)

        hash1 = service._compute_file_hash(large_content)
        hash2 = service._compute_file_hash(large_content)

        assert hash1 == hash2
        assert len(hash1) == 64

    @pytest.mark.asyncio
    async def test_redis_json_parse_error(self, mock_redis):
        """Test handling of corrupted Redis data."""
        mock_redis.get = AsyncMock(return_value="invalid json {{{")
        service = OCRCacheService(redis_client=mock_redis)

        result = await service.get_cached_result(
            content=b"test content",
            backend="deepseek",
            language="de"
        )

        # Should handle gracefully
        assert result is None

    @pytest.mark.asyncio
    async def test_special_characters_in_backend_name(self, mock_redis):
        """Test backend names with special characters."""
        service = OCRCacheService(redis_client=mock_redis)

        key = service._make_cache_key(
            file_hash="abc123",
            backend="got-ocr-2.0",
            language="de"
        )

        assert "got-ocr-2.0" in key

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, mock_redis):
        """Test concurrent access to cache service."""
        service = OCRCacheService(redis_client=mock_redis)
        mock_redis.get = AsyncMock(return_value=None)

        content = b"test content"

        # Simulate concurrent access
        tasks = [
            service.get_cached_result(content, f"backend_{i}", "de")
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete without errors
        assert len(results) == 10


class TestTTLCacheStress:
    """Stress tests for TTLCache."""

    def test_rapid_set_get(self):
        """Test rapid set/get operations."""
        cache = TTLCache(maxsize=1000, ttl=60)

        # Rapid writes
        for i in range(1000):
            cache.set(f"key_{i}", f"value_{i}")

        # Rapid reads
        for i in range(1000):
            result = cache.get(f"key_{i}")
            assert result == f"value_{i}"

    def test_overwrite_existing(self):
        """Test overwriting existing keys."""
        cache = TTLCache(maxsize=10, ttl=60)

        cache.set("key1", "value1")
        cache.set("key1", "value2")

        assert cache.get("key1") == "value2"

    def test_eviction_under_load(self):
        """Test eviction behavior under heavy load."""
        cache = TTLCache(maxsize=10, ttl=60)

        # Add more items than maxsize
        for i in range(20):
            cache.set(f"key_{i}", f"value_{i}")

        # Cache should not exceed maxsize
        assert len(cache) <= 10

        # Most recent items should be present
        assert cache.get("key_19") == "value_19"
        assert cache.get("key_18") == "value_18"


# =============================================================================
# Additional Edge Case Tests - P1-2 Erweiterungen
# =============================================================================

class TestCacheTimeoutHandling:
    """Tests fuer Redis Timeout-Verhalten."""

    @pytest.fixture
    def timeout_redis(self):
        """Mock Redis that times out."""
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=asyncio.TimeoutError())
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_redis_timeout_returns_none(self, timeout_redis):
        """Redis Timeout gibt None zurueck statt Exception."""
        service = OCRCacheService(redis_client=timeout_redis)

        result = await service.get_cached_result(
            content=b"test content",
            backend="deepseek",
            language="de"
        )

        # Sollte None zurueckgeben, nicht Exception werfen
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_timeout_records_miss(self, timeout_redis):
        """Redis Timeout wird als Miss gezaehlt."""
        service = OCRCacheService(redis_client=timeout_redis)

        await service.get_cached_result(
            content=b"test content",
            backend="deepseek",
            language="de"
        )

        assert service._backend_stats["deepseek"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_redis_connection_error_graceful(self):
        """Redis Connection Error wird graceful behandelt."""
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=ConnectionError("Redis not available"))
        service = OCRCacheService(redis_client=redis)

        result = await service.get_cached_result(
            content=b"test",
            backend="deepseek",
            language="de"
        )

        assert result is None


class TestCacheMetricsAccuracy:
    """Tests fuer Cache-Metriken Genauigkeit."""

    @pytest.fixture
    def cache_service_no_redis(self):
        """OCRCacheService ohne Redis."""
        return OCRCacheService(redis_client=None, l1_maxsize=100)

    @pytest.mark.asyncio
    async def test_hit_rate_calculation_accuracy(self, cache_service_no_redis):
        """Hit-Rate wird korrekt berechnet."""
        service = cache_service_no_redis
        content = b"test document"
        result = {"text": "result"}

        # Cache fuellen
        await service.cache_result(content, "deepseek", result)

        # 3 Hits
        for _ in range(3):
            await service.get_cached_result(content, "deepseek")

        # 2 Misses (anderer Content)
        for i in range(2):
            await service.get_cached_result(f"miss_{i}".encode(), "deepseek")

        stats = await service.get_stats()

        # 3 hits, 2 misses = 60% hit rate
        assert stats["per_backend"]["deepseek"]["l1_hits"] == 3
        assert stats["per_backend"]["deepseek"]["misses"] == 2
        assert stats["per_backend"]["deepseek"]["hit_rate_percent"] == 60.0

    @pytest.mark.asyncio
    async def test_multi_backend_stats_isolation(self, cache_service_no_redis):
        """Stats pro Backend sind isoliert."""
        service = cache_service_no_redis

        # DeepSeek: 2 hits, 1 miss
        await service.cache_result(b"doc1", "deepseek", {"text": "r1"})
        await service.get_cached_result(b"doc1", "deepseek")  # Hit
        await service.get_cached_result(b"doc1", "deepseek")  # Hit
        await service.get_cached_result(b"miss", "deepseek")  # Miss

        # GOT-OCR: 1 hit, 3 misses
        await service.cache_result(b"doc2", "got_ocr", {"text": "r2"})
        await service.get_cached_result(b"doc2", "got_ocr")   # Hit
        await service.get_cached_result(b"m1", "got_ocr")     # Miss
        await service.get_cached_result(b"m2", "got_ocr")     # Miss
        await service.get_cached_result(b"m3", "got_ocr")     # Miss

        stats = await service.get_stats()

        # DeepSeek: 66.67% hit rate
        assert stats["per_backend"]["deepseek"]["l1_hits"] == 2
        assert stats["per_backend"]["deepseek"]["misses"] == 1

        # GOT-OCR: 25% hit rate
        assert stats["per_backend"]["got_ocr"]["l1_hits"] == 1
        assert stats["per_backend"]["got_ocr"]["misses"] == 3


class TestCacheInvalidationPatterns:
    """Tests fuer Cache-Invalidierungs-Patterns."""

    @pytest.fixture
    def cache_service(self):
        """OCRCacheService ohne Redis."""
        service = OCRCacheService(redis_client=None, l1_maxsize=100)
        # Disable lazy Redis loading to ensure pure L1 cache tests
        service._redis = None
        return service

    @pytest.mark.asyncio
    async def test_invalidate_all_backends_for_content(self, cache_service):
        """Invalidiere alle Backends fuer einen Content."""
        content = b"test document for invalidation"

        # Mock _get_redis to return None (no Redis available)
        with patch.object(cache_service, '_get_redis', return_value=None):
            # Cache fuer mehrere Backends
            await cache_service.cache_result(content, "deepseek", {"text": "ds"}, language="de")
            await cache_service.cache_result(content, "got_ocr", {"text": "got"}, language="de")
            await cache_service.cache_result(content, "surya", {"text": "surya"}, language="de")

            # Invalidiere alle Backends fuer diesen Content einzeln
            # (ohne backend/language loescht nur L1 mit exact file_hash prefix scan)
            await cache_service.invalidate(content, backend="deepseek", language="de")
            await cache_service.invalidate(content, backend="got_ocr", language="de")
            await cache_service.invalidate(content, backend="surya", language="de")

            # Alle sollten weg sein
            assert await cache_service.get_cached_result(content, "deepseek") is None
            assert await cache_service.get_cached_result(content, "got_ocr") is None
            assert await cache_service.get_cached_result(content, "surya") is None

    @pytest.mark.asyncio
    async def test_invalidate_preserves_other_content(self, cache_service):
        """Invalidierung behaelt anderen Content."""
        content1 = b"document 1 for test"
        content2 = b"document 2 for test"
        result = {"text": "result"}

        # Mock _get_redis to return None (no Redis available)
        with patch.object(cache_service, '_get_redis', return_value=None):
            await cache_service.cache_result(content1, "deepseek", result)
            await cache_service.cache_result(content2, "deepseek", result)

            # Invalidiere nur content1
            await cache_service.invalidate(content1, backend="deepseek", language="de")

            # content2 sollte noch da sein
            assert await cache_service.get_cached_result(content1, "deepseek") is None
            assert await cache_service.get_cached_result(content2, "deepseek") == result


class TestCacheUnicodeHandling:
    """Tests fuer Unicode und deutsche Zeichen im Cache."""

    @pytest.fixture
    def cache_service(self):
        """OCRCacheService ohne Redis."""
        return OCRCacheService(redis_client=None, l1_maxsize=100)

    @pytest.mark.asyncio
    async def test_german_umlauts_in_result(self, cache_service):
        """Deutsche Umlaute werden korrekt gecacht."""
        content = b"test"
        result = {
            "text": "Größe der Fläche: 100m² äöü ß",
            "entities": [
                {"type": "MEASURE", "value": "Größe"},
                {"type": "LOCATION", "value": "München"}
            ]
        }

        await cache_service.cache_result(content, "deepseek", result)
        cached = await cache_service.get_cached_result(content, "deepseek")

        assert cached["text"] == "Größe der Fläche: 100m² äöü ß"
        assert cached["entities"][1]["value"] == "München"

    @pytest.mark.asyncio
    async def test_unicode_content_hash_consistency(self, cache_service):
        """Unicode Content wird konsistent gehasht."""
        content = "Größe äöü ß".encode("utf-8")

        hash1 = cache_service._compute_file_hash(content)
        hash2 = cache_service._compute_file_hash(content)

        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_fraktur_characters(self, cache_service):
        """Fraktur-Schriftzeichen werden korrekt behandelt."""
        content = b"fraktur test"
        result = {
            "text": "ſ (langes s) und ß werden unterschieden",
            "confidence": 0.85
        }

        await cache_service.cache_result(content, "deepseek", result)
        cached = await cache_service.get_cached_result(content, "deepseek")

        assert "ſ" in cached["text"]


class TestCacheConcurrentModification:
    """Tests fuer gleichzeitige Cache-Modifikationen."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_and_invalidate(self):
        """Gleichzeitiges Cachen und Invalidieren."""
        service = OCRCacheService(redis_client=None, l1_maxsize=100)
        content = b"concurrent test"
        result = {"text": "result"}

        async def cache_repeatedly():
            for _ in range(50):
                await service.cache_result(content, "deepseek", result)
                await asyncio.sleep(0.001)

        async def invalidate_repeatedly():
            for _ in range(50):
                await service.invalidate(content, backend="deepseek", language="de")
                await asyncio.sleep(0.001)

        # Gleichzeitig ausfuehren
        await asyncio.gather(
            cache_repeatedly(),
            invalidate_repeatedly()
        )

        # Sollte ohne Errors durchlaufen

    @pytest.mark.asyncio
    async def test_concurrent_reads_during_write(self):
        """Gleichzeitige Lesezugriffe waehrend Schreibvorgang."""
        service = OCRCacheService(redis_client=None, l1_maxsize=100)
        content = b"concurrent read/write"
        result = {"text": "result"}

        # Erst cachen
        await service.cache_result(content, "deepseek", result)

        async def read_repeatedly():
            for _ in range(100):
                await service.get_cached_result(content, "deepseek")

        async def write_new():
            for i in range(50):
                await service.cache_result(f"new_{i}".encode(), "deepseek", result)

        await asyncio.gather(
            read_repeatedly(),
            write_new()
        )


class TestCacheCustomTTL:
    """Tests fuer benutzerdefinierte TTL-Werte."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis Client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_custom_ttl_passed_to_redis(self, mock_redis):
        """Benutzerdefinierter TTL wird an Redis uebergeben."""
        service = OCRCacheService(redis_client=mock_redis)

        await service.cache_result(
            content=b"test",
            backend="deepseek",
            result={"text": "result"},
            ttl=7200  # 2 Stunden
        )

        # Verify Redis was called with correct TTL
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == 7200 or call_args[1].get("ex") == 7200

    @pytest.mark.asyncio
    async def test_default_ttl_used_when_not_specified(self, mock_redis):
        """Standard-TTL wird verwendet wenn nicht angegeben."""
        service = OCRCacheService(redis_client=mock_redis, l2_ttl=86400)

        await service.cache_result(
            content=b"test",
            backend="deepseek",
            result={"text": "result"}
        )

        # Verify Redis was called with default TTL
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == 86400 or call_args[1].get("ex") == 86400


class TestCacheStatsClearance:
    """Tests fuer Zuruecksetzen von Cache-Statistiken."""

    @pytest.fixture
    def cache_service(self):
        """OCRCacheService ohne Redis."""
        return OCRCacheService(redis_client=None, l1_maxsize=100)

    @pytest.mark.asyncio
    async def test_clear_stats_resets_all_backends(self, cache_service):
        """clear_stats setzt alle Backend-Stats zurueck."""
        # Generiere einige Stats
        content = b"test"
        result = {"text": "result"}

        await cache_service.cache_result(content, "deepseek", result)
        await cache_service.get_cached_result(content, "deepseek")
        await cache_service.get_cached_result(b"miss", "got_ocr")

        # Stats sollten vorhanden sein
        assert len(cache_service._backend_stats) > 0

        # Stats zuruecksetzen
        await cache_service.clear_stats()

        # Stats sollten leer sein
        assert len(cache_service._backend_stats) == 0

    @pytest.mark.asyncio
    async def test_stats_accumulate_after_clear(self, cache_service):
        """Stats sammeln sich nach Clear wieder an."""
        content = b"test"
        result = {"text": "result"}

        # Cache und Stats generieren
        await cache_service.cache_result(content, "deepseek", result)
        await cache_service.get_cached_result(content, "deepseek")

        # Clear
        await cache_service.clear_stats()

        # Neue Stats generieren
        await cache_service.get_cached_result(content, "deepseek")

        stats = await cache_service.get_stats()
        assert stats["per_backend"]["deepseek"]["l1_hits"] == 1
