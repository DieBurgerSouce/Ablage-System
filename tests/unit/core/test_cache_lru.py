"""
Unit tests für LRUCache (L1 Cache).

Testet LRU-Cache mit TTL, Eviction, Pattern-Invalidation.
"""
import pytest
import asyncio
import time
from typing import Optional, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from threading import Thread

from app.core.cache import (
    LRUCache,
    cache_multi_tier,
    CacheStats
)


class TestLRUCache:
    """Tests für LRUCache."""

    @pytest.fixture
    def cache(self) -> LRUCache:
        """LRUCache Instanz mit kleinem maxsize."""
        return LRUCache(maxsize=5, default_ttl=60)

    @pytest.fixture
    def large_cache(self) -> LRUCache:
        """LRUCache mit größerem maxsize."""
        return LRUCache(maxsize=100, default_ttl=300)

    # -------------------------------------------------------------------------
    # Basic Get/Set Tests
    # -------------------------------------------------------------------------

    def test_basic_set_and_get(self, cache: LRUCache) -> None:
        """Basis Set/Get Operationen."""
        # Arrange & Act
        cache.set("key1", "value1")
        result = cache.get("key1")

        # Assert
        assert result == "value1"

    def test_get_nonexistent_key(self, cache: LRUCache) -> None:
        """Get für nicht existierenden Key gibt None zurück."""
        result = cache.get("nonexistent")
        assert result is None

    def test_set_overwrites_existing_key(self, cache: LRUCache) -> None:
        """Set überschreibt existierenden Key."""
        # Arrange
        cache.set("key1", "value1")

        # Act
        cache.set("key1", "value2")
        result = cache.get("key1")

        # Assert
        assert result == "value2"

    def test_set_with_custom_ttl(self, cache: LRUCache) -> None:
        """Set mit custom TTL."""
        # Arrange & Act
        cache.set("key1", "value1", ttl=120)
        result = cache.get("key1")

        # Assert
        assert result == "value1"
        # TTL ist gesetzt (wird in TTL tests weiter geprüft)

    # -------------------------------------------------------------------------
    # TTL Expiration Tests
    # -------------------------------------------------------------------------

    def test_ttl_expiration(self, cache: LRUCache) -> None:
        """Items mit abgelaufenem TTL werden nicht zurückgegeben."""
        # Arrange
        cache.set("key1", "value1", ttl=1)  # 1 Sekunde TTL

        # Act
        time.sleep(1.5)  # Warte bis TTL abgelaufen
        result = cache.get("key1")

        # Assert
        assert result is None

    def test_ttl_not_expired(self, cache: LRUCache) -> None:
        """Items mit nicht abgelaufenem TTL werden zurückgegeben."""
        # Arrange
        cache.set("key1", "value1", ttl=10)  # 10 Sekunden TTL

        # Act
        time.sleep(0.5)  # Warte kurz
        result = cache.get("key1")

        # Assert
        assert result == "value1"

    def test_default_ttl_used(self, cache: LRUCache) -> None:
        """Default TTL wird verwendet wenn kein custom TTL angegeben."""
        # Arrange
        cache.set("key1", "value1")  # Nutzt default_ttl=60

        # Act
        result = cache.get("key1")

        # Assert
        assert result == "value1"

    # -------------------------------------------------------------------------
    # LRU Eviction Tests
    # -------------------------------------------------------------------------

    def test_lru_eviction_when_full(self, cache: LRUCache) -> None:
        """LRU eviction entfernt ältesten Eintrag wenn Cache voll."""
        # Arrange
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")
        cache.set("key5", "value5")

        # Act
        cache.set("key6", "value6")  # Cache ist voll, key1 sollte evicted werden

        # Assert
        assert cache.get("key1") is None  # Ältester entfernt
        assert cache.get("key6") == "value6"
        assert cache.get("key2") == "value2"  # Andere noch da

    def test_lru_access_updates_order(self, cache: LRUCache) -> None:
        """Zugriff auf Key aktualisiert LRU-Reihenfolge."""
        # Arrange
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")
        cache.set("key5", "value5")

        # Act
        _ = cache.get("key1")  # Greife auf key1 zu, macht ihn "recently used"
        cache.set("key6", "value6")  # key2 sollte jetzt evicted werden

        # Assert
        assert cache.get("key1") == "value1"  # key1 noch da wegen Zugriff
        assert cache.get("key2") is None  # key2 evicted

    def test_maxsize_enforcement(self, cache: LRUCache) -> None:
        """Cache hält sich an maxsize."""
        # Arrange
        maxsize = 5

        # Act
        for i in range(10):
            cache.set(f"key{i}", f"value{i}")

        # Assert
        # Nur die letzten 5 sollten noch da sein
        assert cache.get("key0") is None
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None
        assert cache.get("key4") is None
        assert cache.get("key5") == "value5"
        assert cache.get("key9") == "value9"

    # -------------------------------------------------------------------------
    # Invalidation Tests
    # -------------------------------------------------------------------------

    def test_invalidate_by_key(self, cache: LRUCache) -> None:
        """Invalidate entfernt spezifischen Key."""
        # Arrange
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Act
        cache.invalidate("key1")

        # Assert
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_invalidate_nonexistent_key(self, cache: LRUCache) -> None:
        """Invalidate für nicht existierenden Key wirft keinen Fehler."""
        # Act & Assert (sollte nicht crashen)
        cache.invalidate("nonexistent")

    def test_invalidate_pattern_simple(self, cache: LRUCache) -> None:
        """Invalidate pattern entfernt matching keys."""
        # Arrange
        cache.set("user:123:profile", "data1")
        cache.set("user:123:settings", "data2")
        cache.set("user:456:profile", "data3")

        # Act
        cache.invalidate_pattern("user:123:*")

        # Assert
        assert cache.get("user:123:profile") is None
        assert cache.get("user:123:settings") is None
        assert cache.get("user:456:profile") == "data3"

    def test_invalidate_pattern_complex(self, cache: LRUCache) -> None:
        """Invalidate pattern mit komplexerem Muster."""
        # Arrange
        cache.set("doc:1:metadata", "data1")
        cache.set("doc:2:metadata", "data2")
        cache.set("doc:1:content", "data3")
        cache.set("folder:1:list", "data4")

        # Act
        cache.invalidate_pattern("doc:*:metadata")

        # Assert
        assert cache.get("doc:1:metadata") is None
        assert cache.get("doc:2:metadata") is None
        assert cache.get("doc:1:content") == "data3"
        assert cache.get("folder:1:list") == "data4"

    def test_clear_all(self, cache: LRUCache) -> None:
        """Clear entfernt alle Einträge."""
        # Arrange
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Act
        cache.clear()

        # Assert
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    # -------------------------------------------------------------------------
    # Stats Tests
    # -------------------------------------------------------------------------

    def test_stats_hit_tracking(self, cache: LRUCache) -> None:
        """Stats tracken Cache-Hits korrekt."""
        # Arrange
        cache.set("key1", "value1")

        # Act
        _ = cache.get("key1")  # Hit
        _ = cache.get("key1")  # Hit
        stats = cache.stats()

        # Assert
        assert stats.hits >= 2

    def test_stats_miss_tracking(self, cache: LRUCache) -> None:
        """Stats tracken Cache-Misses korrekt."""
        # Arrange
        cache.set("key1", "value1")

        # Act
        _ = cache.get("key2")  # Miss
        _ = cache.get("key3")  # Miss
        stats = cache.stats()

        # Assert
        assert stats.misses >= 2

    def test_stats_hit_rate_calculation(self, cache: LRUCache) -> None:
        """Stats berechnen Hit-Rate korrekt."""
        # Arrange
        cache.set("key1", "value1")

        # Act
        _ = cache.get("key1")  # Hit
        _ = cache.get("key1")  # Hit
        _ = cache.get("key2")  # Miss
        stats = cache.stats()

        # Assert
        # 2 hits, 1 miss = 66.6% hit rate
        assert stats.hit_rate > 0.6
        assert stats.hit_rate < 0.7

    def test_stats_size_tracking(self, cache: LRUCache) -> None:
        """Stats tracken aktuelle Cache-Größe."""
        # Arrange & Act
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        stats = cache.stats()

        # Assert
        assert stats.size == 2

    def test_stats_after_eviction(self, cache: LRUCache) -> None:
        """Stats korrekt nach Eviction."""
        # Arrange
        for i in range(10):  # Cache hat maxsize=5
            cache.set(f"key{i}", f"value{i}")

        # Act
        stats = cache.stats()

        # Assert
        assert stats.size <= 5
        assert stats.evictions > 0

    # -------------------------------------------------------------------------
    # Thread Safety Tests
    # -------------------------------------------------------------------------

    def test_concurrent_access(self, large_cache: LRUCache) -> None:
        """Concurrent Access ist thread-safe."""
        # Arrange
        num_threads = 10
        operations_per_thread = 100

        def worker(thread_id: int) -> None:
            for i in range(operations_per_thread):
                key = f"thread{thread_id}:key{i}"
                large_cache.set(key, f"value{i}")
                _ = large_cache.get(key)

        # Act
        threads: List[Thread] = []
        for i in range(num_threads):
            thread = Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Assert
        stats = large_cache.stats()
        # Sollte keine Crashes geben und Stats sollten plausibel sein
        assert stats.hits > 0
        assert stats.size > 0

    def test_concurrent_invalidation(self, large_cache: LRUCache) -> None:
        """Concurrent Invalidation ist thread-safe."""
        # Arrange
        for i in range(50):
            large_cache.set(f"key{i}", f"value{i}")

        def invalidate_worker() -> None:
            for i in range(10):
                large_cache.invalidate(f"key{i}")

        def get_worker() -> None:
            for i in range(50):
                _ = large_cache.get(f"key{i}")

        # Act
        threads: List[Thread] = []
        for _ in range(5):
            threads.append(Thread(target=invalidate_worker))
            threads.append(Thread(target=get_worker))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Assert (sollte nicht crashen)
        stats = large_cache.stats()
        assert stats is not None

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    def test_set_with_none_value(self, cache: LRUCache) -> None:
        """Set mit None als Value."""
        # Arrange & Act
        cache.set("key1", None)
        result = cache.get("key1")

        # Assert
        assert result is None

    def test_large_value_storage(self, cache: LRUCache) -> None:
        """Speicherung großer Values."""
        # Arrange
        large_value = "x" * 10000  # 10KB String

        # Act
        cache.set("large_key", large_value)
        result = cache.get("large_key")

        # Assert
        assert result == large_value

    def test_special_characters_in_keys(self, cache: LRUCache) -> None:
        """Keys mit Sonderzeichen."""
        # Arrange
        special_keys = [
            "key:with:colons",
            "key/with/slashes",
            "key-with-dashes",
            "key.with.dots",
            "key_with_underscores"
        ]

        # Act & Assert
        for key in special_keys:
            cache.set(key, "value")
            assert cache.get(key) == "value"

    def test_numeric_values(self, cache: LRUCache) -> None:
        """Numerische Values."""
        # Arrange & Act
        cache.set("int_key", 42)
        cache.set("float_key", 3.14)

        # Assert
        assert cache.get("int_key") == 42
        assert cache.get("float_key") == 3.14

    def test_dict_values(self, cache: LRUCache) -> None:
        """Dict als Value."""
        # Arrange
        value = {"name": "Test", "count": 5}

        # Act
        cache.set("dict_key", value)
        result = cache.get("dict_key")

        # Assert
        assert result == value
        assert result["name"] == "Test"

    def test_list_values(self, cache: LRUCache) -> None:
        """List als Value."""
        # Arrange
        value = [1, 2, 3, 4, 5]

        # Act
        cache.set("list_key", value)
        result = cache.get("list_key")

        # Assert
        assert result == value
        assert len(result) == 5


class TestCacheMultiTierDecorator:
    """Tests für @cache_multi_tier Decorator."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        return redis

    # -------------------------------------------------------------------------
    # L1 Hit Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l1_cache_hit(self, mock_redis: AsyncMock) -> None:
        """L1 Cache Hit vermeidet L2/DB Zugriff."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        cache.set("test:key", "cached_value")

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            return "db_value"

        # Act
        result = await expensive_function("key")

        # Assert
        assert result == "cached_value"
        # Redis sollte nicht abgefragt worden sein
        mock_redis.get.assert_not_called()

    # -------------------------------------------------------------------------
    # L2 Hit Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l2_cache_hit(self, mock_redis: AsyncMock) -> None:
        """L2 Cache Hit vermeidet DB Zugriff und füllt L1."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        mock_redis.get.return_value = b'"redis_value"'  # JSON serialized

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            return "db_value"

        # Act
        result = await expensive_function("key")

        # Assert
        assert result == "redis_value"
        # L1 sollte jetzt auch den Wert haben
        assert cache.get("test:key") == "redis_value"

    # -------------------------------------------------------------------------
    # Cache Miss Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cache_miss_calls_function(self, mock_redis: AsyncMock) -> None:
        """Cache Miss führt Funktion aus und füllt beide Caches."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        mock_redis.get.return_value = None

        call_count = 0

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return "db_value"

        # Act
        result = await expensive_function("key")

        # Assert
        assert result == "db_value"
        assert call_count == 1
        # Beide Caches sollten gefüllt sein
        assert cache.get("test:key") == "db_value"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_subsequent_calls_use_cache(self, mock_redis: AsyncMock) -> None:
        """Zweiter Aufruf nutzt L1 Cache."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        mock_redis.get.return_value = None

        call_count = 0

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"db_value_{call_count}"

        # Act
        result1 = await expensive_function("key")
        result2 = await expensive_function("key")

        # Assert
        assert result1 == "db_value_1"
        assert result2 == "db_value_1"  # Cached value
        assert call_count == 1  # Nur einmal aufgerufen

    # -------------------------------------------------------------------------
    # Multiple Keys Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_different_keys_cached_separately(self, mock_redis: AsyncMock) -> None:
        """Verschiedene Keys werden separat gecached."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        mock_redis.get.return_value = None

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            return f"value_{key}"

        # Act
        result1 = await expensive_function("key1")
        result2 = await expensive_function("key2")

        # Assert
        assert result1 == "value_key1"
        assert result2 == "value_key2"
        assert cache.get("test:key1") == "value_key1"
        assert cache.get("test:key2") == "value_key2"

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_redis_failure_fallback(self, mock_redis: AsyncMock) -> None:
        """Redis Fehler führt zu Fallback auf DB."""
        # Arrange
        cache = LRUCache(maxsize=10, default_ttl=60)
        mock_redis.get.side_effect = Exception("Redis down")

        @cache_multi_tier(
            key_prefix="test",
            ttl=300,
            l1_cache=cache,
            redis=mock_redis
        )
        async def expensive_function(key: str) -> str:
            return "db_value"

        # Act
        result = await expensive_function("key")

        # Assert
        assert result == "db_value"
        # L1 sollte trotzdem gefüllt sein
        assert cache.get("test:key") == "db_value"


class TestCacheStats:
    """Tests für CacheStats Dataclass."""

    def test_cache_stats_initialization(self) -> None:
        """CacheStats korrekt initialisiert."""
        stats = CacheStats(
            hits=100,
            misses=50,
            size=75,
            maxsize=100,
            evictions=25
        )

        assert stats.hits == 100
        assert stats.misses == 50
        assert stats.size == 75
        assert stats.maxsize == 100
        assert stats.evictions == 25

    def test_cache_stats_hit_rate(self) -> None:
        """CacheStats berechnet hit_rate."""
        stats = CacheStats(
            hits=80,
            misses=20,
            size=50,
            maxsize=100,
            evictions=0
        )

        assert stats.hit_rate == 0.8

    def test_cache_stats_zero_requests(self) -> None:
        """CacheStats mit zero requests."""
        stats = CacheStats(
            hits=0,
            misses=0,
            size=0,
            maxsize=100,
            evictions=0
        )

        # hit_rate sollte 0.0 sein bei 0 requests
        assert stats.hit_rate == 0.0
