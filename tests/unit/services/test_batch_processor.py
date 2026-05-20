# -*- coding: utf-8 -*-
"""
Tests für den Batch Processor Service.

Testet:
- BatchSizeCache (TTL-basiertes Caching)
- DynamicBatchSizer (VRAM-Monitoring, OOM-Recovery)
- BatchProcessor (Batch-Verarbeitung, Chunking, Fehlerbehandlung)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio
import time
from pathlib import Path

from app.services.batch_processor import (
    BatchSizeCache,
    CachedBatchSize,
    DynamicBatchSizer,
    BatchProcessor,
    get_batch_size_cache,
)


class TestCachedBatchSize:
    """Tests für CachedBatchSize Dataclass."""

    def test_cached_batch_size_creation(self):
        """Test CachedBatchSize creation."""
        cached = CachedBatchSize(
            batch_size=8,
            calculated_at=time.monotonic(),
            source="adaptive",
            available_vram_gb=10.5
        )

        assert cached.batch_size == 8
        assert cached.source == "adaptive"
        assert cached.available_vram_gb == 10.5


class TestBatchSizeCache:
    """Tests für BatchSizeCache."""

    def test_default_initialization(self):
        """Test default cache initialization."""
        cache = BatchSizeCache()

        assert cache._ttl == 30.0
        assert cache._hits == 0
        assert cache._misses == 0
        assert len(cache._cache) == 0

    def test_custom_ttl_initialization(self):
        """Test custom TTL initialization."""
        cache = BatchSizeCache(ttl_seconds=60.0)

        assert cache._ttl == 60.0

    def test_ttl_capped_at_max(self):
        """TTL should be capped at MAX_TTL_SECONDS."""
        cache = BatchSizeCache(ttl_seconds=999.0)

        assert cache._ttl == BatchSizeCache.MAX_TTL_SECONDS

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = BatchSizeCache()

        cache.set(batch_size=16, backend="deepseek", source="adaptive", available_vram_gb=12.0)

        cached = cache.get("deepseek")

        assert cached is not None
        assert cached.batch_size == 16
        assert cached.source == "adaptive"
        assert cached.available_vram_gb == 12.0

    def test_cache_miss_returns_none(self):
        """Non-existent key should return None."""
        cache = BatchSizeCache()

        result = cache.get("nonexistent")

        assert result is None
        assert cache._misses == 1

    def test_cache_hit_increments_counter(self):
        """Cache hit should increment hits counter."""
        cache = BatchSizeCache()
        cache.set(batch_size=8, backend="test")

        cache.get("test")

        assert cache._hits == 1

    def test_cache_expiration(self):
        """Cache should expire after TTL."""
        cache = BatchSizeCache(ttl_seconds=0.1)  # 100ms TTL
        cache.set(batch_size=8, backend="test")

        # Wait for expiration
        time.sleep(0.15)

        result = cache.get("test")

        assert result is None
        assert cache._misses == 1

    def test_invalidate_specific_backend(self):
        """Test invalidating specific backend."""
        cache = BatchSizeCache()
        cache.set(batch_size=8, backend="deepseek")
        cache.set(batch_size=4, backend="got_ocr")

        count = cache.invalidate("deepseek")

        assert count == 1
        assert cache.get("deepseek") is None
        assert cache.get("got_ocr") is not None

    def test_invalidate_all(self):
        """Test invalidating all entries."""
        cache = BatchSizeCache()
        cache.set(batch_size=8, backend="deepseek")
        cache.set(batch_size=4, backend="got_ocr")

        count = cache.invalidate()

        assert count == 2
        assert len(cache._cache) == 0

    def test_get_stats(self):
        """Test statistics reporting."""
        cache = BatchSizeCache(ttl_seconds=30.0)
        cache.set(batch_size=8, backend="test")
        cache.get("test")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["ttl_seconds"] == 30.0
        assert "test" in stats["cached_backends"]


class TestGetBatchSizeCache:
    """Tests für Singleton Accessor."""

    def test_returns_cache_instance(self):
        """Should return BatchSizeCache instance."""
        cache = get_batch_size_cache()

        assert isinstance(cache, BatchSizeCache)

    def test_returns_same_instance(self):
        """Should return same singleton instance."""
        cache1 = get_batch_size_cache()
        cache2 = get_batch_size_cache()

        assert cache1 is cache2


class TestDynamicBatchSizer:
    """Tests für DynamicBatchSizer."""

    def test_initialization(self):
        """Test default initialization."""
        sizer = DynamicBatchSizer()

        assert sizer.max_batch_size == 32
        assert sizer.min_batch_size == 1
        assert sizer._current_batch_size == 32
        assert sizer._oom_count == 0
        assert sizer._warmup_completed is False

    def test_custom_initialization(self):
        """Test custom initialization."""
        sizer = DynamicBatchSizer(max_batch_size=16, min_batch_size=2)

        assert sizer.max_batch_size == 16
        assert sizer.min_batch_size == 2

    @patch("app.services.batch_processor.torch.cuda.is_available")
    def test_get_optimal_batch_size_no_gpu(self, mock_cuda):
        """Without GPU, should return small batch size."""
        mock_cuda.return_value = False
        sizer = DynamicBatchSizer(max_batch_size=32)

        batch_size = sizer.get_optimal_batch_size()

        assert batch_size <= 4

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.torch.cuda.get_device_properties")
    @patch("app.services.batch_processor.torch.cuda.memory_allocated")
    @patch("app.services.batch_processor.torch.cuda.memory_reserved")
    def test_get_optimal_batch_size_with_gpu(
        self, mock_reserved, mock_allocated, mock_props, mock_cuda
    ):
        """With GPU, should calculate based on available VRAM."""
        mock_cuda.return_value = True

        # Mock 16GB total, 4GB used
        mock_device_props = MagicMock()
        mock_device_props.total_memory = 16 * 1024**3
        mock_props.return_value = mock_device_props
        mock_allocated.return_value = 4 * 1024**3
        mock_reserved.return_value = 4 * 1024**3

        sizer = DynamicBatchSizer(max_batch_size=32)

        batch_size = sizer.get_optimal_batch_size()

        # Should return a reasonable batch size based on 12GB free
        assert batch_size >= 1
        assert batch_size <= 32

    def test_record_oom_reduces_batch_size(self):
        """OOM should halve batch size."""
        sizer = DynamicBatchSizer(max_batch_size=16, min_batch_size=1)
        sizer._current_batch_size = 16

        new_size = sizer.record_oom()

        assert new_size == 8
        assert sizer._oom_count == 1

    def test_record_oom_respects_minimum(self):
        """OOM should not go below minimum batch size."""
        sizer = DynamicBatchSizer(max_batch_size=4, min_batch_size=2)
        sizer._current_batch_size = 2

        new_size = sizer.record_oom()

        # Should stay at minimum
        assert new_size == 2

    def test_record_success_updates_memory(self):
        """Success should update measured memory per doc."""
        sizer = DynamicBatchSizer()

        # Simulate 400MB used for 4 docs
        sizer.record_success(
            batch_size=4,
            backend="deepseek",
            memory_used=400 * 1024**2
        )

        # Should record ~100MB per doc
        assert "deepseek" in sizer._measured_memory_per_doc
        expected_per_doc = 100 * 1024**2
        assert abs(sizer._measured_memory_per_doc["deepseek"] - expected_per_doc) < 1000

    def test_record_success_reduces_oom_count(self):
        """Success should slowly reduce OOM count."""
        sizer = DynamicBatchSizer()
        sizer._oom_count = 2

        sizer.record_success(batch_size=4, backend="test", memory_used=100 * 1024**2)

        assert sizer._oom_count < 2

    @patch("app.services.batch_processor.torch.cuda.is_available")
    def test_get_vram_status_no_gpu(self, mock_cuda):
        """VRAM status without GPU."""
        mock_cuda.return_value = False
        sizer = DynamicBatchSizer()

        status = sizer.get_vram_status()

        assert status["available"] is False

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.torch.cuda.get_device_properties")
    @patch("app.services.batch_processor.torch.cuda.memory_allocated")
    @patch("app.services.batch_processor.torch.cuda.memory_reserved")
    def test_get_vram_status_with_gpu(
        self, mock_reserved, mock_allocated, mock_props, mock_cuda
    ):
        """VRAM status with GPU."""
        mock_cuda.return_value = True

        mock_device_props = MagicMock()
        mock_device_props.total_memory = 16 * 1024**3
        mock_props.return_value = mock_device_props
        mock_allocated.return_value = 8 * 1024**3  # 50% used
        mock_reserved.return_value = 8 * 1024**3

        sizer = DynamicBatchSizer()

        status = sizer.get_vram_status()

        assert status["available"] is True
        assert status["total_gb"] == 16.0
        assert status["allocated_gb"] == 8.0
        assert status["usage_percent"] == 50.0
        assert status["status"] == "safe"

    @patch("app.services.batch_processor.torch.cuda.is_available")
    def test_warmup_without_gpu(self, mock_cuda):
        """Warmup should complete without GPU."""
        mock_cuda.return_value = False
        sizer = DynamicBatchSizer()

        sizer.warmup(backend="test")

        assert sizer._warmup_completed is True


class TestBatchProcessor:
    """Tests für BatchProcessor."""

    @pytest.fixture
    def mock_backend_manager(self):
        """Create mock backend manager."""
        manager = MagicMock()
        manager.select_backend = AsyncMock(return_value="deepseek")
        manager.process_with_backend = AsyncMock(return_value={
            "success": True,
            "text": "OCR Result",
            "confidence": 0.95
        })
        return manager

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    def test_initialization_no_gpu(self, mock_cuda, mock_backend_manager):
        """Test initialization without GPU."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=8)

        assert processor.max_batch_size == 8
        assert processor._use_adaptive is False

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    def test_calculate_optimal_batch_size_cpu(self, mock_cuda, mock_backend_manager):
        """Optimal batch size on CPU should be limited."""
        mock_cuda.return_value = False

        # psutil is imported inside the function, mock it at psutil module level
        with patch("psutil.cpu_count") as mock_cpu:
            mock_cpu.return_value = 8

            processor = BatchProcessor(mock_backend_manager, max_batch_size=16)

            # Should use CPU cores (limited to 4)
            assert processor.optimal_batch_size <= 4

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_batch_success(self, mock_cuda, mock_backend_manager):
        """Test successful batch processing."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        file_paths = ["/tmp/doc1.pdf", "/tmp/doc2.pdf"]

        result = await processor.process_batch(file_paths)

        assert result["success"] is True
        assert result["total"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_batch_with_progress_callback(self, mock_cuda, mock_backend_manager):
        """Test batch processing with progress callback."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=2)

        progress_updates = []

        async def progress_callback(update):
            progress_updates.append(update)

        file_paths = ["/tmp/doc1.pdf", "/tmp/doc2.pdf", "/tmp/doc3.pdf"]

        await processor.process_batch(file_paths, progress_callback=progress_callback)

        # Should have received progress updates
        assert len(progress_updates) >= 1

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_batch_handles_errors(self, mock_cuda, mock_backend_manager):
        """Test batch processing with document errors."""
        mock_cuda.return_value = False

        # Make backend fail for one document
        call_count = 0

        async def process_side_effect(backend, path, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Processing failed")
            return {"success": True, "text": "Result"}

        mock_backend_manager.process_with_backend.side_effect = process_side_effect

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        file_paths = ["/tmp/doc1.pdf", "/tmp/doc2.pdf", "/tmp/doc3.pdf"]

        result = await processor.process_batch(file_paths)

        # Should have processed all but doc2 should have error
        assert result["total"] == 3

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_single_document(self, mock_cuda, mock_backend_manager):
        """Test processing single document."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        result = await processor._process_single(
            "/tmp/doc.pdf", backend="deepseek", language="de"
        )

        assert result["file"] == "/tmp/doc.pdf"
        assert result["file_name"] == "doc.pdf"

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_single_auto_backend(self, mock_cuda, mock_backend_manager):
        """Test auto backend selection."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        await processor._process_single(
            "/tmp/doc.pdf", backend="auto", language="de"
        )

        # Should have called select_backend
        mock_backend_manager.select_backend.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_single_error_handling(self, mock_cuda, mock_backend_manager):
        """Test error handling in single document processing."""
        mock_cuda.return_value = False

        mock_backend_manager.process_with_backend.side_effect = Exception("OCR failed")

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        result = await processor._process_single(
            "/tmp/doc.pdf", backend="deepseek", language="de"
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_directory_not_found(self, mock_cuda, mock_backend_manager):
        """Test processing non-existent directory."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        with pytest.raises(ValueError, match="Directory not found"):
            await processor.process_directory("/nonexistent/path")

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_directory_no_matching_files(self, mock_cuda, mock_backend_manager, tmp_path):
        """Test processing directory with no matching files."""
        mock_cuda.return_value = False

        # Create empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        result = await processor.process_directory(str(empty_dir), pattern="*.pdf")

        assert result["success"] is False
        assert result["total"] == 0

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    def test_cleanup(self, mock_cuda, mock_backend_manager):
        """Test resource cleanup."""
        mock_cuda.return_value = False

        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        processor.cleanup()

        # Executor should be shut down
        # No assertion needed - just ensure no exceptions


class TestBatchProcessorOOMRecovery:
    """Tests für OOM Recovery in BatchProcessor."""

    @pytest.fixture
    def mock_backend_manager(self):
        """Create mock backend manager."""
        manager = MagicMock()
        manager.select_backend = AsyncMock(return_value="deepseek")
        manager.process_with_backend = AsyncMock(return_value={
            "success": True,
            "text": "OCR Result"
        })
        return manager

    def test_dynamic_sizer_oom_reduces_batch(self):
        """Test that DynamicBatchSizer reduces batch size on OOM."""
        sizer = DynamicBatchSizer(max_batch_size=16, min_batch_size=1)

        # Initial batch size
        original = sizer._current_batch_size
        assert original == 16

        # Record OOM
        new_size = sizer.record_oom()

        # Should be halved
        assert new_size == 8
        assert sizer._oom_count == 1

        # Record another OOM
        new_size = sizer.record_oom()

        # Should be halved again
        assert new_size == 4
        assert sizer._oom_count == 2

    def test_oom_count_affects_optimal_batch_calculation(self):
        """OOM count should affect optimal batch calculation."""
        sizer = DynamicBatchSizer(max_batch_size=32, min_batch_size=1)

        # Record several OOMs
        sizer.record_oom()
        sizer.record_oom()

        # OOM count should be 2
        assert sizer._oom_count == 2

        # Current batch size should have been reduced
        assert sizer._current_batch_size <= 8


class TestBatchSizeCacheIntegration:
    """Integration Tests für Cache mit BatchProcessor."""

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    def test_batch_processor_uses_cache(self, mock_cuda):
        """BatchProcessor should use cache for batch size calculation."""
        mock_cuda.return_value = False

        # Clear global cache
        import app.services.batch_processor as bp
        bp._batch_size_cache = None

        mock_backend_manager = MagicMock()

        processor = BatchProcessor(mock_backend_manager, max_batch_size=8)

        # First calculation
        size1 = processor._calculate_optimal_batch_size("test_backend")

        # Second calculation should hit cache
        cache = get_batch_size_cache()
        cache_before = cache._hits

        size2 = processor._calculate_optimal_batch_size("test_backend")

        # Should have cache hit
        assert cache._hits == cache_before + 1
        assert size1 == size2


class TestEdgeCases:
    """Edge Case Tests."""

    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    def test_dynamic_sizer_zero_memory_per_doc(self, mock_cuda):
        """Zero memory per doc should not cause division by zero."""
        mock_cuda.return_value = False

        sizer = DynamicBatchSizer()
        sizer._measured_memory_per_doc["test"] = 0

        # Should handle gracefully
        batch_size = sizer.get_optimal_batch_size("test")

        assert batch_size >= 1

    def test_batch_size_cache_empty_backend_name(self):
        """Empty backend name should work."""
        cache = BatchSizeCache()

        cache.set(batch_size=4, backend="")

        result = cache.get("")

        assert result is not None
        assert result.batch_size == 4

    @pytest.mark.asyncio
    @patch("app.services.batch_processor.torch.cuda.is_available")
    @patch("app.services.batch_processor.ADAPTIVE_BATCH_AVAILABLE", False)
    async def test_process_batch_empty_list(self, mock_cuda):
        """Processing empty file list should handle gracefully."""
        mock_cuda.return_value = False

        mock_backend_manager = MagicMock()
        processor = BatchProcessor(mock_backend_manager, max_batch_size=4)

        result = await processor.process_batch([])

        assert result["total"] == 0
        assert result["successful"] == 0
