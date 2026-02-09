# -*- coding: utf-8 -*-
"""
Unit tests for L1 LRU Cache.

Tests the in-process LRU cache implementation including:
- Basic get/set operations
- TTL expiration
- LRU eviction policy
- Pattern-based invalidation
- Thread safety
- Statistics tracking
"""

import pytest
import time
import threading
from app.core.cache import LRUCache


class TestLRUCache:
    """Test suite for LRUCache."""

    def test_basic_get_set(self):
        """Test basic get/set operations."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        # Set value
        cache.set("key1", "value1")

        # Get value
        assert cache.get("key1") == "value1"

        # Get non-existent key
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = LRUCache(maxsize=10, default_ttl=1)  # 1 second TTL

        # Set value
        cache.set("key1", "value1", ttl=1)

        # Should exist immediately
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert cache.get("key1") is None

    def test_custom_ttl(self):
        """Test custom TTL override."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        # Set with custom short TTL
        cache.set("key1", "value1", ttl=1)

        # Should exist
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = LRUCache(maxsize=3, default_ttl=60)

        # Fill cache
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # All should exist
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

        # Add fourth item - should evict LRU (key1, since we just accessed key2 and key3)
        # Actually, we accessed all three, so key1 is oldest in access order
        cache.set("key4", "value4")

        # key1 should be evicted
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_invalidate(self):
        """Test single key invalidation."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Invalidate key1
        cache.invalidate("key1")

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_invalidate_pattern(self):
        """Test pattern-based invalidation."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        cache.set("cache:user:123", "value1")
        cache.set("cache:user:456", "value2")
        cache.set("cache:doc:789", "value3")

        # Invalidate all user keys
        deleted = cache.invalidate_pattern("cache:user:*")

        assert deleted == 2
        assert cache.get("cache:user:123") is None
        assert cache.get("cache:user:456") is None
        assert cache.get("cache:doc:789") == "value3"

    def test_clear(self):
        """Test cache clear."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.stats().size == 0

    def test_stats(self):
        """Test statistics tracking."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        # Set values
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Hits
        cache.get("key1")
        cache.get("key2")

        # Misses
        cache.get("nonexistent1")
        cache.get("nonexistent2")

        stats = cache.stats()

        assert stats.hits == 2
        assert stats.misses == 2
        assert stats.hit_rate == 0.5
        assert stats.size == 2
        assert stats.maxsize == 10

    def test_thread_safety(self):
        """Test thread-safe operations."""
        cache = LRUCache(maxsize=100, default_ttl=60)
        errors = []

        def worker(worker_id: int):
            try:
                for i in range(10):
                    key = f"key_{worker_id}_{i}"
                    cache.set(key, f"value_{worker_id}_{i}")
                    value = cache.get(key)
                    assert value == f"value_{worker_id}_{i}"
            except Exception as e:
                errors.append(e)

        # Spawn 10 threads
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0

        # Stats should reflect operations
        stats = cache.stats()
        assert stats.size <= 100

    def test_complex_values(self):
        """Test caching of complex values (dicts, lists)."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        # Dict
        cache.set("dict", {"key": "value", "nested": {"a": 1}})
        assert cache.get("dict") == {"key": "value", "nested": {"a": 1}}

        # List
        cache.set("list", [1, 2, 3, {"nested": "value"}])
        assert cache.get("list") == [1, 2, 3, {"nested": "value"}]

        # None
        cache.set("none", None)
        assert cache.get("none") is None

    def test_overwrite(self):
        """Test overwriting existing keys."""
        cache = LRUCache(maxsize=10, default_ttl=60)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Overwrite
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

        # Size should not increase
        assert cache.stats().size == 1
