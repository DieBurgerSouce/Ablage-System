# -*- coding: utf-8 -*-
"""
Unit tests for Cache Warming Service.

Tests cache warming functionality including:
- Recent documents warming
- Active user warming
- System config warming
- Error handling
- Invalidation
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cache.cache_warming_service import CacheWarmingService
from app.db.models import Document, User
from app.core.cache import get_l1_cache


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = Mock(spec=AsyncSession)
    return db


@pytest.fixture
def warming_service(mock_db):
    """Cache warming service instance."""
    return CacheWarmingService(mock_db)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear L1 cache before each test."""
    cache = get_l1_cache()
    cache.clear()
    yield
    cache.clear()


class TestCacheWarmingService:
    """Test suite for CacheWarmingService."""

    @pytest.mark.asyncio
    async def test_warm_recent_documents_success(self, warming_service, mock_db):
        """Test warming recent documents cache."""
        # Mock documents
        mock_docs = []
        for i in range(5):
            doc = Mock(spec=Document)
            doc.id = f"doc-{i}"
            doc.filename = f"test-{i}.pdf"
            doc.document_type = "invoice"
            doc.status = "completed"
            doc.page_count = 1
            doc.ocr_backend_used = "deepseek"
            doc.upload_date = datetime.utcnow()
            doc.updated_at = datetime.utcnow()
            doc.deleted_at = None
            mock_docs.append(doc)

        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_docs

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Warm cache
        count = await warming_service._warm_recent_documents(limit=10)

        # Verify
        assert count == 5

        # Check L1 cache populated
        cache = get_l1_cache()
        for i in range(5):
            key = f"cache:doc:doc-{i}"
            cached = cache.get(key)
            assert cached is not None
            assert cached["filename"] == f"test-{i}.pdf"

    @pytest.mark.asyncio
    async def test_warm_active_users_success(self, warming_service, mock_db):
        """Test warming active user settings cache."""
        # Mock users
        mock_users = []
        for i in range(3):
            user = Mock(spec=User)
            user.id = f"user-{i}"
            user.email = f"user{i}@example.com"
            user.username = f"user{i}"
            user.is_active = True
            user.is_superuser = False
            user.preferred_language = "de"
            user.preferred_ocr_backend = "auto"
            user.daily_quota = 100
            user.documents_processed_today = 10
            user.totp_enabled = False
            user.updated_at = datetime.utcnow()
            mock_users.append(user)

        # Mock query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_users

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Warm cache
        count = await warming_service._warm_active_user_settings()

        # Verify
        assert count == 3

        # Check L1 cache populated
        cache = get_l1_cache()
        for i in range(3):
            key = f"cache:user:user-{i}"
            cached = cache.get(key)
            assert cached is not None
            assert cached["email"] == f"user{i}@example.com"

    @pytest.mark.asyncio
    async def test_warm_system_config_success(self, warming_service):
        """Test warming system configuration cache."""
        # Warm cache
        count = await warming_service._warm_system_config()

        # Verify
        assert count == 1

        # Check L1 cache populated
        cache = get_l1_cache()
        key = "cache:stats:system_config"
        cached = cache.get(key)
        assert cached is not None
        assert "ocr_backends_available" in cached
        assert cached["default_ocr_backend"] == "auto"

    @pytest.mark.asyncio
    async def test_warm_caches_all(self, warming_service, mock_db):
        """Test warming all caches."""
        # Mock empty results
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Warm all caches
        results = await warming_service.warm_caches()

        # Verify
        assert "recent_documents" in results
        assert "active_users" in results
        assert "system_config" in results
        assert "total" in results
        assert results["total"] >= 0

    @pytest.mark.asyncio
    async def test_warm_recent_documents_error_handling(self, warming_service, mock_db):
        """Test error handling in recent documents warming."""
        # Mock database error
        mock_db.execute = AsyncMock(side_effect=Exception("Database error"))

        # Should not raise exception
        count = await warming_service._warm_recent_documents()

        # Should return 0 on error
        assert count == 0

    @pytest.mark.asyncio
    async def test_warm_active_users_error_handling(self, warming_service, mock_db):
        """Test error handling in active users warming."""
        # Mock database error
        mock_db.execute = AsyncMock(side_effect=Exception("Database error"))

        # Should not raise exception
        count = await warming_service._warm_active_user_settings()

        # Should return 0 on error
        assert count == 0

    @pytest.mark.asyncio
    async def test_invalidate_warmed_caches(self, warming_service):
        """Test invalidation of warmed caches."""
        cache = get_l1_cache()

        # Populate cache
        cache.set("cache:doc:123", {"id": "123"})
        cache.set("cache:user:456", {"id": "456"})
        cache.set("cache:stats:system_config", {"config": "value"})

        # Invalidate
        results = await warming_service.invalidate_warmed_caches()

        # Verify
        assert results["documents"] == 1
        assert results["users"] == 1
        assert results["system"] == 1
        assert results["total"] == 3

        # Check cache is empty
        assert cache.get("cache:doc:123") is None
        assert cache.get("cache:user:456") is None
        assert cache.get("cache:stats:system_config") is None

    @pytest.mark.asyncio
    async def test_warm_caches_partial_failure(self, warming_service, mock_db):
        """Test that partial failures don't stop cache warming."""
        # Mock database to fail for documents but succeed for users
        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call (documents)
                raise Exception("Document query failed")
            # Second call (users) - return empty result
            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_db.execute = mock_execute

        # Warm caches
        results = await warming_service.warm_caches()

        # Verify
        assert results["recent_documents"] == 0  # Failed
        assert results["active_users"] == 0  # Succeeded but empty
        assert results["system_config"] == 1  # Succeeded
