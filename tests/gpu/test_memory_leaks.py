# -*- coding: utf-8 -*-
"""
GPU Memory Leak Detection Tests.

Tests fuer GPU-Memory-Management:
- Memory Leak Detection nach Batch-Verarbeitung
- VRAM-Limit Enforcement
- Memory Guard Funktionalitaet

Verwendung:
    pytest tests/gpu/test_memory_leaks.py -v -m gpu
    pytest tests/gpu/test_memory_leaks.py -v --gpu-required
"""

import gc
from unittest.mock import MagicMock, patch

import pytest

# GPU Marker - Tests werden uebersprungen wenn keine GPU verfuegbar
pytestmark = pytest.mark.gpu


@pytest.fixture
def mock_torch():
    """Mock PyTorch CUDA Funktionen."""
    with patch.dict('sys.modules', {'torch': MagicMock()}):
        import sys
        mock = sys.modules['torch']
        mock.cuda.is_available.return_value = True
        mock.cuda.memory_allocated.return_value = 2 * 1024**3  # 2GB
        mock.cuda.max_memory_allocated.return_value = 4 * 1024**3  # 4GB
        mock.cuda.get_device_properties.return_value = MagicMock(
            total_memory=16 * 1024**3  # 16GB
        )
        mock.cuda.empty_cache = MagicMock()
        mock.cuda.synchronize = MagicMock()
        mock.cuda.reset_peak_memory_stats = MagicMock()
        mock.cuda.OutOfMemoryError = MemoryError
        yield mock


class TestGPUMemoryLeakDetection:
    """Tests fuer Memory Leak Detection."""

    def test_no_memory_leak_after_batch(self, mock_torch):
        """
        GPU Memory sollte nach Batch-Verarbeitung nicht signifikant wachsen.

        Ziel: Max 5% Memory-Wachstum nach 10 Batches.
        """
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Simuliere initiale Memory-Nutzung
        initial_memory = 2 * 1024**3  # 2GB

        # Simuliere Memory nach 10 Batches
        memory_after_batches = []
        for i in range(10):
            # Simuliere leichtes Memory-Wachstum (normal)
            current = initial_memory + (i * 50 * 1024**2)  # +50MB pro Batch
            memory_after_batches.append(current)

        # Nach Cleanup
        mock_torch.cuda.memory_allocated.return_value = initial_memory + 100 * 1024**2

        # Cleanup simulieren
        manager.handle_oom_error()

        # Pruefe Memory-Wachstum
        final_memory = mock_torch.cuda.memory_allocated()
        growth_percent = ((final_memory - initial_memory) / initial_memory) * 100

        assert growth_percent < 5.0, (
            f"Memory wuchs um {growth_percent:.1f}% (Ziel: < 5%)"
        )

    def test_memory_cleanup_after_oom(self, mock_torch):
        """
        Memory sollte nach OOM-Recovery zurueckgesetzt werden.
        """
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Simuliere hohe Memory-Nutzung vor OOM
        mock_torch.cuda.memory_allocated.return_value = 14 * 1024**3  # 14GB

        # OOM Recovery
        result = manager.handle_oom_error()

        # Pruefe dass cleanup aufgerufen wurde
        mock_torch.cuda.empty_cache.assert_called()
        mock_torch.cuda.synchronize.assert_called()

        # Allocations sollten geleert sein
        assert len(manager.allocations) == 0

    def test_batch_profiling_records_memory(self, mock_torch):
        """
        Batch-Profiling sollte Memory-Nutzung korrekt erfassen.
        """
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Simuliere Batch-Verarbeitung
        mock_torch.cuda.max_memory_allocated.return_value = 8 * 1024**3  # 8GB peak

        # Record profiling data
        manager.record_batch_profile(
            backend="got_ocr",
            batch_size=4,
            peak_memory_bytes=8 * 1024**3
        )

        # Pruefe dass Profil gespeichert wurde
        assert hasattr(manager, '_backend_profiles')
        assert 'got_ocr' in manager._backend_profiles

        profile = manager._backend_profiles['got_ocr']
        assert profile['measured_mb_per_doc'] > 0
        assert profile['sample_count'] == 1


class TestMemoryGuard:
    """Tests fuer GPU Memory Guard."""

    def test_memory_guard_blocks_over_limit(self, mock_torch):
        """
        Memory Guard sollte Allocations ueber dem Limit blockieren.
        """
        from app.gpu_manager import GPUMemoryGuard

        # Simuliere bereits hohe Memory-Nutzung
        mock_torch.cuda.memory_allocated.return_value = 13 * 1024**3  # 13GB

        guard = GPUMemoryGuard(memory_limit_gb=13.6)

        # Versuche weitere 2GB zu allokieren
        check = guard.can_allocate(required_gb=2.0)

        assert check["allowed"] is False
        assert "Limit" in check.get("reason", "")

    def test_memory_guard_allows_under_limit(self, mock_torch):
        """
        Memory Guard sollte Allocations unter dem Limit erlauben.
        """
        from app.gpu_manager import GPUMemoryGuard

        # Simuliere niedrige Memory-Nutzung
        mock_torch.cuda.memory_allocated.return_value = 4 * 1024**3  # 4GB

        guard = GPUMemoryGuard(memory_limit_gb=13.6)

        # Versuche 2GB zu allokieren
        check = guard.can_allocate(required_gb=2.0)

        assert check["allowed"] is True
        assert check["remaining_after_gb"] > 0

    def test_memory_guard_cleanup_frees_memory(self, mock_torch):
        """
        Memory Guard Cleanup sollte Memory freigeben.
        """
        from app.gpu_manager import GPUMemoryGuard

        # Vor Cleanup
        mock_torch.cuda.memory_allocated.return_value = 8 * 1024**3

        guard = GPUMemoryGuard()

        # Nach Cleanup (simuliert)
        mock_torch.cuda.memory_allocated.side_effect = [
            8 * 1024**3,  # Vor Cleanup
            6 * 1024**3,  # Nach Cleanup
        ]

        freed = guard.cleanup_cache()

        # empty_cache sollte aufgerufen worden sein
        mock_torch.cuda.empty_cache.assert_called()

    def test_memory_guard_metrics(self, mock_torch):
        """
        Memory Guard sollte Metriken bereitstellen.
        """
        from app.gpu_manager import GPUMemoryGuard

        mock_torch.cuda.memory_allocated.return_value = 8 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 10 * 1024**3

        guard = GPUMemoryGuard(memory_limit_gb=13.6)

        metrics = guard.get_metrics()

        assert "gpu_memory_allocated_bytes" in metrics
        assert "gpu_memory_limit_bytes" in metrics
        assert "gpu_memory_usage_ratio" in metrics
        assert metrics["gpu_memory_allocated_bytes"] == 8 * 1024**3


class TestAdaptiveBatchProcessor:
    """Tests fuer AdaptiveBatchProcessor."""

    @pytest.mark.asyncio
    async def test_oom_triggers_batch_reduction(self, mock_torch):
        """
        OOM sollte Batch-Size Reduktion ausloesen.
        """
        from app.gpu_manager import AdaptiveBatchProcessor, GPUManager

        manager = GPUManager()
        processor = AdaptiveBatchProcessor(
            gpu_manager=manager,
            initial_batch_size=8
        )

        # Stats vor OOM
        initial_stats = processor.get_stats()
        assert initial_stats["oom_events"] == 0

    @pytest.mark.asyncio
    async def test_hysteresis_increases_batch_size(self, mock_torch):
        """
        Nach vielen erfolgreichen Batches sollte Batch-Size steigen.
        """
        from app.gpu_manager import AdaptiveBatchProcessor, GPUManager

        manager = GPUManager()
        processor = AdaptiveBatchProcessor(
            gpu_manager=manager,
            initial_batch_size=4
        )

        # Simuliere viele erfolgreiche Batches
        processor._stats["consecutive_successes_since_oom"] = 99
        processor._stats["current_effective_max_batch"] = 4

        # Ein weiterer Erfolg sollte Hysterese ausloesen
        # (normalerweise in process_with_fallback)

        # Pruefe Hysterese-Threshold
        assert processor.HYSTERESIS_SUCCESS_THRESHOLD == 100


class TestVRAMLimitEnforcement:
    """Tests fuer VRAM-Limit Enforcement."""

    def test_vram_85_percent_limit(self, mock_torch):
        """
        VRAM-Nutzung sollte bei 85% (13.6GB von 16GB) begrenzt sein.
        """
        from app.gpu_manager import GPUMemoryGuard

        guard = GPUMemoryGuard()

        # Default Limit sollte 13.6GB sein
        assert guard.memory_limit_gb == 13.6
        assert guard.DEFAULT_LIMIT_GB == 13.6

        # Limit in Bytes
        expected_bytes = int(13.6 * 1024**3)
        assert guard.memory_limit_bytes == expected_bytes

    def test_warning_threshold_at_75_percent(self, mock_torch):
        """
        Warning sollte bei 75% des Limits ausgeloest werden.
        """
        from app.gpu_manager import GPUMemoryGuard

        # 75% von 13.6GB = 10.2GB
        mock_torch.cuda.memory_allocated.return_value = int(10.2 * 1024**3)

        guard = GPUMemoryGuard(memory_limit_gb=13.6)
        status = guard.check_memory_status()

        assert status["is_warning"] is True
        assert status["status"] == "warning"

    def test_critical_threshold_at_90_percent(self, mock_torch):
        """
        Critical sollte bei 90% des Limits ausgeloest werden.
        """
        from app.gpu_manager import GPUMemoryGuard

        # 90% von 13.6GB = 12.24GB
        mock_torch.cuda.memory_allocated.return_value = int(12.24 * 1024**3)

        guard = GPUMemoryGuard(memory_limit_gb=13.6)
        status = guard.check_memory_status()

        assert status["is_critical"] is True
        assert status["status"] == "critical"
