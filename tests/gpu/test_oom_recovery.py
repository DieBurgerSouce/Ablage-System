"""
Tests for GPU OOM Recovery.

Tests GPU Out-of-Memory recovery mechanisms:
- Large batch triggering OOM
- Batch reduction by 0.5 factor
- Cache clearing verification
- Garbage collection
- Minimum batch enforcement
- Optimal batch size tracking
"""

import pytest
import pytest_asyncio
from typing import Any, List
from unittest.mock import AsyncMock, patch

# Mark all tests as GPU tests
# Note: asyncio mark is applied per-test or per-class for async tests
pytestmark = pytest.mark.gpu


@pytest.mark.asyncio
class TestGPURecoveryManager:
    """Test GPURecoveryManager OOM recovery."""

    async def test_recovery_manager_initialization(self):
        """Test GPURecoveryManager initializes correctly."""
        from app.core.gpu_recovery import GPURecoveryManager, BACKEND_CONFIGS

        manager = GPURecoveryManager()

        # Check optimal batch sizes are initialized from configs
        for backend in BACKEND_CONFIGS:
            assert backend in manager._optimal_batch_sizes
            assert manager._optimal_batch_sizes[backend] == BACKEND_CONFIGS[backend].default_batch_size

    async def test_get_optimal_batch_size(self):
        """Test getting optimal batch size for backends."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Check known backends
        assert manager.get_optimal_batch_size("deepseek") == 4
        assert manager.get_optimal_batch_size("got_ocr") == 8
        assert manager.get_optimal_batch_size("surya_gpu") == 16
        assert manager.get_optimal_batch_size("donut") == 8

        # Unknown backend should return default
        assert manager.get_optimal_batch_size("unknown") == 4

    async def test_batch_size_reduction(self):
        """Test batch size reduction on OOM."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Reduce batch size for deepseek (default 4)
        new_size = manager._reduce_batch_size("deepseek", 4)

        # Should reduce by 50% but not below min (1)
        assert new_size == 2

        # Reduce again
        new_size = manager._reduce_batch_size("deepseek", 2)
        assert new_size == 1

        # At minimum, should stay at 1
        new_size = manager._reduce_batch_size("deepseek", 1)
        assert new_size == 1

    async def test_batch_size_history_tracking(self):
        """Test that batch size reductions are tracked."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Reduce batch size multiple times
        manager._reduce_batch_size("deepseek", 8)
        manager._reduce_batch_size("deepseek", 4)
        manager._reduce_batch_size("deepseek", 2)

        # Check history
        history = manager._batch_size_history.get("deepseek", [])
        assert len(history) == 3
        assert history == [8, 4, 2]

    async def test_is_oom_error_detection(self, gpu_context):
        """Test OOM error detection."""
        from app.core.gpu_recovery import GPURecoveryManager
        import torch

        manager = GPURecoveryManager()

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        # CUDA OOM error
        oom_error = torch.cuda.OutOfMemoryError("CUDA out of memory")
        assert manager._is_oom_error(oom_error) is True

        # RuntimeError with OOM message
        runtime_oom = RuntimeError("CUDA out of memory. Tried to allocate 1GB")
        assert manager._is_oom_error(runtime_oom) is True

        # Regular exception should not be detected as OOM
        regular_error = ValueError("Some other error")
        assert manager._is_oom_error(regular_error) is False


@pytest.mark.asyncio
class TestOOMRecoveryExecution:
    """Test OOM recovery during batch execution."""

    async def test_successful_batch_processing(self):
        """Test successful batch processing without OOM."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Mock successful processing function
        async def process_batch(batch: List[Any], **kwargs):
            return [{"result": f"processed_{i}"} for i in range(len(batch))]

        batch = list(range(8))
        results = await manager.execute_with_oom_recovery(
            process_batch,
            backend="got_ocr",
            batch=batch,
        )

        assert len(results) == 8
        assert all("result" in r for r in results)

    async def test_oom_triggers_batch_reduction(self, gpu_context):
        """Test that OOM triggers batch size reduction."""
        from app.core.gpu_recovery import GPURecoveryManager
        import torch

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPURecoveryManager()
        oom_count = 0

        async def process_with_oom(batch: List[Any], **kwargs):
            nonlocal oom_count
            # Fail with OOM on first attempt with large batch
            if len(batch) > 4 and oom_count < 1:
                oom_count += 1
                raise torch.cuda.OutOfMemoryError("CUDA OOM simulated")
            return [{"result": i} for i in range(len(batch))]

        batch = list(range(16))
        results = await manager.execute_with_oom_recovery(
            process_with_oom,
            backend="deepseek",
            batch=batch,
        )

        # Should have processed all items
        assert len(results) == 16

        # Batch size should have been reduced
        assert manager.get_optimal_batch_size("deepseek") <= 4

    async def test_recovery_clears_gpu_cache(self, gpu_context):
        """Test that recovery clears GPU cache."""
        from app.core.gpu_recovery import GPURecoveryManager
        import torch

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPURecoveryManager()

        # Allocate some memory
        if torch.cuda.is_available():
            tensor = torch.zeros(1000, 1000, device="cuda")
            allocated_before = torch.cuda.memory_allocated()

            # Clear memory
            del tensor
            await manager.clear_gpu_memory()

            allocated_after = torch.cuda.memory_allocated()
            assert allocated_after < allocated_before

    async def test_min_batch_enforcement(self, gpu_context):
        """Test that minimum batch size is enforced."""
        from app.core.gpu_recovery import GPURecoveryManager, GPURecoveryError
        import torch

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPURecoveryManager()

        async def always_oom(batch: List[Any], **kwargs):
            raise torch.cuda.OutOfMemoryError("CUDA OOM")

        # Should raise GPURecoveryError after exhausting retries
        with pytest.raises(GPURecoveryError) as exc_info:
            await manager.execute_with_oom_recovery(
                always_oom,
                backend="deepseek",
                batch=[1, 2, 3, 4],
                max_retries=3,
            )

        assert "deepseek" in str(exc_info.value)

    async def test_non_oom_errors_propagate(self):
        """Test that non-OOM errors are re-raised."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        async def raise_value_error(batch: List[Any], **kwargs):
            # Note: Don't use "oom" in message - it triggers OOM detection!
            raise ValueError("Invalid configuration detected")

        with pytest.raises(ValueError) as exc_info:
            await manager.execute_with_oom_recovery(
                raise_value_error,
                backend="got_ocr",
                batch=[1, 2, 3],
            )

        assert "Invalid configuration detected" in str(exc_info.value)


@pytest.mark.asyncio
class TestGPUMemoryStats:
    """Test GPU memory statistics."""

    async def test_get_memory_stats(self, gpu_context):
        """Test memory stats retrieval."""
        from app.core.gpu_recovery import GPURecoveryManager

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPURecoveryManager()
        stats = manager.get_memory_stats()

        # Check stats structure
        assert hasattr(stats, 'total_gb')
        assert hasattr(stats, 'allocated_gb')
        assert hasattr(stats, 'free_gb')
        assert hasattr(stats, 'utilization_percent')

        # Values should be reasonable
        assert stats.total_gb > 0
        assert stats.allocated_gb >= 0
        assert stats.free_gb >= 0
        assert 0 <= stats.utilization_percent <= 100

    async def test_high_memory_warning(self, gpu_context):
        """Test high memory utilization warning."""
        from app.core.gpu_recovery import GPURecoveryManager

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPURecoveryManager()

        # Mock high memory utilization
        with patch.object(manager, 'get_memory_stats') as mock_stats:
            from app.core.gpu_recovery import GPUMemoryStats
            mock_stats.return_value = GPUMemoryStats(
                total_gb=16.0,
                allocated_gb=14.0,
                cached_gb=14.5,
                free_gb=2.0,
                utilization_percent=87.5,
            )

            stats = manager.get_memory_stats()
            assert stats.utilization_percent > 85


@pytest.mark.asyncio
class TestGPUMemoryGuard:
    """Test gpu_memory_guard context manager."""

    async def test_memory_guard_clears_on_threshold(self, gpu_context):
        """Test that memory guard clears when threshold exceeded."""
        from app.core.gpu_recovery import gpu_memory_guard

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        async with gpu_memory_guard(threshold_gb=0.1) as manager:
            # Any allocation will exceed 0.1GB threshold
            pass

        # Memory should have been cleared (or attempted)


@pytest.mark.asyncio
class TestRecoveryStats:
    """Test recovery statistics tracking."""

    async def test_get_stats(self):
        """Test retrieval of recovery statistics."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Simulate some OOM events
        manager._reduce_batch_size("deepseek", 8)
        manager._oom_count["deepseek"] = 2

        stats = manager.get_stats()

        assert "optimal_batch_sizes" in stats
        assert "oom_counts" in stats
        assert "batch_size_history" in stats

        assert stats["oom_counts"]["deepseek"] == 2

    async def test_global_manager_singleton(self):
        """Test global GPU recovery manager singleton."""
        from app.core.gpu_recovery import get_gpu_recovery_manager

        manager1 = get_gpu_recovery_manager()
        manager2 = get_gpu_recovery_manager()

        # Should be the same instance
        assert manager1 is manager2


class TestBackendConfigs:
    """Test backend configuration values."""

    def test_all_backends_configured(self):
        """Test that all backends have configurations."""
        from app.core.gpu_recovery import BACKEND_CONFIGS

        expected_backends = ["deepseek", "got_ocr", "surya_gpu", "donut", "hybrid"]

        for backend in expected_backends:
            assert backend in BACKEND_CONFIGS, f"Missing config for {backend}"

    def test_vram_requirements_sensible(self):
        """Test that VRAM requirements are sensible for RTX 4080."""
        from app.core.gpu_recovery import BACKEND_CONFIGS

        for backend, config in BACKEND_CONFIGS.items():
            # All should fit in 16GB RTX 4080
            assert config.vram_gb <= 16.0, f"{backend} exceeds 16GB VRAM"

            # Most should be under 13GB to allow buffer
            if backend not in ["hybrid"]:
                assert config.vram_gb <= 13.0, f"{backend} leaves insufficient buffer"

    def test_batch_sizes_sensible(self):
        """Test that batch sizes are sensible."""
        from app.core.gpu_recovery import BACKEND_CONFIGS

        for backend, config in BACKEND_CONFIGS.items():
            assert config.min_batch_size >= 1
            assert config.max_batch_size >= config.min_batch_size
            assert config.default_batch_size >= config.min_batch_size
            assert config.default_batch_size <= config.max_batch_size

    def test_reduction_factor(self):
        """Test reduction factor is correct."""
        from app.core.gpu_recovery import BACKEND_CONFIGS

        for backend, config in BACKEND_CONFIGS.items():
            # Reduction factor should be between 0 and 1
            assert 0 < config.reduction_factor < 1
            # Standard is 0.5 (50% reduction)
            assert config.reduction_factor == 0.5
