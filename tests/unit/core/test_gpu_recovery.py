"""
Tests für gpu_recovery.py - GPU OOM Recovery Manager.

Testet:
- GPUBackendConfig und GPUMemoryStats Dataclasses
- GPURecoveryManager Methoden
- OOM Recovery Logik
- GPU Memory Guard Context Manager
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from dataclasses import asdict

from app.core.gpu_recovery import (
    # Classes and dataclasses
    GPUBackendConfig,
    GPUMemoryStats,
    GPURecoveryError,
    GPURecoveryManager,
    # Functions
    gpu_memory_guard,
    get_gpu_recovery_manager,
    # Constants
    BACKEND_CONFIGS,
    MAX_VRAM_USAGE_GB,
    TORCH_AVAILABLE,
)


# ==================== Dataclass Tests ====================


class TestGPUBackendConfig:
    """Tests für GPUBackendConfig dataclass."""

    def test_default_values(self):
        """GPUBackendConfig hat korrekte Standardwerte."""
        config = GPUBackendConfig(default_batch_size=8)

        assert config.default_batch_size == 8
        assert config.min_batch_size == 1
        assert config.max_batch_size == 32
        assert config.vram_gb == 0.0
        assert config.reduction_factor == 0.5

    def test_custom_values(self):
        """GPUBackendConfig akzeptiert benutzerdefinierte Werte."""
        config = GPUBackendConfig(
            default_batch_size=16,
            min_batch_size=4,
            max_batch_size=64,
            vram_gb=12.0,
            reduction_factor=0.75,
        )

        assert config.default_batch_size == 16
        assert config.min_batch_size == 4
        assert config.max_batch_size == 64
        assert config.vram_gb == 12.0
        assert config.reduction_factor == 0.75


class TestGPUMemoryStats:
    """Tests für GPUMemoryStats dataclass."""

    def test_default_values(self):
        """GPUMemoryStats hat korrekte Standardwerte (alle 0)."""
        stats = GPUMemoryStats()

        assert stats.total_gb == 0.0
        assert stats.allocated_gb == 0.0
        assert stats.cached_gb == 0.0
        assert stats.free_gb == 0.0
        assert stats.utilization_percent == 0.0

    def test_custom_values(self):
        """GPUMemoryStats akzeptiert benutzerdefinierte Werte."""
        stats = GPUMemoryStats(
            total_gb=16.0,
            allocated_gb=8.0,
            cached_gb=2.0,
            free_gb=8.0,
            utilization_percent=50.0,
        )

        assert stats.total_gb == 16.0
        assert stats.allocated_gb == 8.0
        assert stats.free_gb == 8.0
        assert stats.utilization_percent == 50.0


# ==================== Constants Tests ====================


class TestBackendConfigs:
    """Tests für Backend-Konfigurationen."""

    def test_all_backends_have_configs(self):
        """Alle erwarteten Backends haben Konfigurationen."""
        expected_backends = ["deepseek", "got_ocr", "surya_gpu", "donut", "hybrid"]

        for backend in expected_backends:
            assert backend in BACKEND_CONFIGS
            config = BACKEND_CONFIGS[backend]
            assert isinstance(config, GPUBackendConfig)

    def test_deepseek_config_values(self):
        """DeepSeek-Konfiguration hat erwartete Werte."""
        config = BACKEND_CONFIGS["deepseek"]

        assert config.default_batch_size == 4
        assert config.min_batch_size == 1
        assert config.max_batch_size == 8
        assert config.vram_gb == 12.0

    def test_max_vram_threshold(self):
        """MAX_VRAM_USAGE_GB ist korrekt (85% von 16GB)."""
        assert MAX_VRAM_USAGE_GB == 13.6


# ==================== GPURecoveryError Tests ====================


class TestGPURecoveryError:
    """Tests für GPURecoveryError."""

    def test_error_stores_backend_and_reason(self):
        """GPURecoveryError speichert Backend und Grund."""
        error = GPURecoveryError(backend="deepseek", reason="OOM nach 3 Versuchen")

        assert error.backend == "deepseek"
        assert error.reason == "OOM nach 3 Versuchen"

    def test_error_message_is_german(self):
        """GPURecoveryError hat deutsche Fehlermeldung."""
        error = GPURecoveryError(backend="got_ocr", reason="Test")

        assert "fehlgeschlagen" in str(error).lower()
        assert "got_ocr" in str(error)


# ==================== GPURecoveryManager Tests ====================


class TestGPURecoveryManager:
    """Tests für GPURecoveryManager."""

    def test_initialization(self):
        """GPURecoveryManager initialisiert korrekt."""
        manager = GPURecoveryManager()

        assert isinstance(manager._batch_size_history, dict)
        assert isinstance(manager._optimal_batch_sizes, dict)
        assert isinstance(manager._oom_count, dict)
        assert manager._last_memory_stats is None

    def test_initial_optimal_batch_sizes(self):
        """Initiale optimale Batch-Größen entsprechen Backend-Defaults."""
        manager = GPURecoveryManager()

        for backend, config in BACKEND_CONFIGS.items():
            assert manager._optimal_batch_sizes[backend] == config.default_batch_size

    def test_get_optimal_batch_size_known_backend(self):
        """get_optimal_batch_size gibt korrekte Größe für bekanntes Backend."""
        manager = GPURecoveryManager()

        size = manager.get_optimal_batch_size("deepseek")
        assert size == 4  # DeepSeek default

    def test_get_optimal_batch_size_unknown_backend(self):
        """get_optimal_batch_size gibt Fallback für unbekanntes Backend."""
        manager = GPURecoveryManager()

        size = manager.get_optimal_batch_size("unknown_backend")
        assert size == 4  # Default fallback

    def test_reduce_batch_size(self):
        """_reduce_batch_size reduziert korrekt."""
        manager = GPURecoveryManager()

        # Deepseek mit reduction_factor 0.5
        new_size = manager._reduce_batch_size("deepseek", 8)
        assert new_size == 4  # 8 * 0.5

        # Nochmal reduzieren
        new_size = manager._reduce_batch_size("deepseek", 4)
        assert new_size == 2  # 4 * 0.5

    def test_reduce_batch_size_respects_minimum(self):
        """_reduce_batch_size respektiert Minimum."""
        manager = GPURecoveryManager()

        # Deepseek min_batch_size ist 1
        new_size = manager._reduce_batch_size("deepseek", 1)
        assert new_size == 1  # Kann nicht unter 1

    def test_reduce_batch_size_tracks_history(self):
        """_reduce_batch_size speichert History."""
        manager = GPURecoveryManager()

        manager._reduce_batch_size("deepseek", 8)
        manager._reduce_batch_size("deepseek", 4)

        assert "deepseek" in manager._batch_size_history
        assert 8 in manager._batch_size_history["deepseek"]
        assert 4 in manager._batch_size_history["deepseek"]

    def test_get_stats(self):
        """get_stats gibt korrekte Statistiken."""
        manager = GPURecoveryManager()
        manager._reduce_batch_size("deepseek", 8)
        manager._oom_count["deepseek"] = 2

        stats = manager.get_stats()

        assert "optimal_batch_sizes" in stats
        assert "oom_counts" in stats
        assert "batch_size_history" in stats
        assert stats["oom_counts"]["deepseek"] == 2


class TestGPURecoveryManagerMemory:
    """Tests für GPURecoveryManager Memory-Methoden."""

    def test_get_memory_stats_without_gpu(self):
        """get_memory_stats gibt leere Stats ohne GPU."""
        manager = GPURecoveryManager()

        # Mock torch.cuda.is_available to return False
        with patch('app.core.gpu_recovery.TORCH_AVAILABLE', False):
            stats = manager.get_memory_stats()

        assert stats.total_gb == 0.0
        assert stats.allocated_gb == 0.0

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch nicht verfügbar")
    def test_get_memory_stats_with_gpu_mock(self):
        """get_memory_stats gibt korrekte Stats mit GPU (mock)."""
        manager = GPURecoveryManager()

        with patch('app.core.gpu_recovery.torch') as mock_torch:
            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.get_device_properties.return_value.total_memory = 16 * 1024**3
            mock_torch.cuda.memory_allocated.return_value = 8 * 1024**3
            mock_torch.cuda.memory_reserved.return_value = 10 * 1024**3

            stats = manager.get_memory_stats()

            assert stats.total_gb == 16.0
            assert stats.allocated_gb == 8.0
            assert stats.free_gb == 8.0

    @pytest.mark.asyncio
    async def test_clear_gpu_memory_without_gpu(self):
        """clear_gpu_memory funktioniert ohne GPU."""
        manager = GPURecoveryManager()

        with patch('app.core.gpu_recovery.TORCH_AVAILABLE', False):
            stats = await manager.clear_gpu_memory()

        assert stats.total_gb == 0.0


class TestGPURecoveryManagerOOMDetection:
    """Tests für OOM-Erkennung."""

    def test_is_oom_error_without_torch(self):
        """_is_oom_error gibt False ohne torch."""
        manager = GPURecoveryManager()

        with patch('app.core.gpu_recovery.TORCH_AVAILABLE', False):
            result = manager._is_oom_error(RuntimeError("Some error"))

        assert result is False

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch nicht verfügbar")
    def test_is_oom_error_with_cuda_oom(self):
        """_is_oom_error erkennt CUDA OOM."""
        import torch
        manager = GPURecoveryManager()

        # Mock CUDA OOM
        mock_error = torch.cuda.OutOfMemoryError("CUDA out of memory")
        result = manager._is_oom_error(mock_error)

        assert result is True

    def test_is_oom_error_with_oom_message(self):
        """_is_oom_error erkennt OOM in Fehlermeldung."""
        manager = GPURecoveryManager()

        if TORCH_AVAILABLE:
            oom_errors = [
                RuntimeError("CUDA out of memory"),
                RuntimeError("Out of memory allocation"),
                RuntimeError("OOM error occurred"),
            ]

            for error in oom_errors:
                result = manager._is_oom_error(error)
                assert result is True

    def test_is_oom_error_non_oom(self):
        """_is_oom_error erkennt Nicht-OOM-Fehler."""
        manager = GPURecoveryManager()

        if TORCH_AVAILABLE:
            non_oom_errors = [
                RuntimeError("File not found"),
                ValueError("Invalid value"),
                TypeError("Type mismatch"),
            ]

            for error in non_oom_errors:
                result = manager._is_oom_error(error)
                assert result is False


# ==================== execute_with_oom_recovery Tests ====================


class TestExecuteWithOOMRecovery:
    """Tests für execute_with_oom_recovery."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty(self):
        """Leerer Batch gibt leere Liste zurück."""
        manager = GPURecoveryManager()

        async def mock_func(batch):
            return batch

        result = await manager.execute_with_oom_recovery(
            mock_func, backend="deepseek", batch=[]
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_successful_processing(self):
        """Erfolgreiche Verarbeitung ohne OOM."""
        manager = GPURecoveryManager()

        async def mock_func(batch):
            return [f"processed_{item}" for item in batch]

        batch = ["doc1", "doc2", "doc3"]
        result = await manager.execute_with_oom_recovery(
            mock_func, backend="deepseek", batch=batch
        )

        assert len(result) == 3
        assert "processed_doc1" in result

    @pytest.mark.asyncio
    async def test_oom_recovery_reduces_batch_size(self):
        """OOM Recovery reduziert Batch-Größe."""
        manager = GPURecoveryManager()
        call_count = 0
        batch_sizes_used = []

        async def mock_func_with_oom(batch):
            nonlocal call_count
            call_count += 1
            batch_sizes_used.append(len(batch))

            if call_count == 1:
                # Erste Ausführung: OOM simulieren
                raise RuntimeError("CUDA out of memory")

            return [f"processed_{item}" for item in batch]

        # Mock _is_oom_error to return True for our mock error
        with patch.object(manager, '_is_oom_error', return_value=True):
            with patch.object(manager, 'clear_gpu_memory', new_callable=AsyncMock):
                with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
                    batch = ["doc1", "doc2", "doc3", "doc4"]
                    result = await manager.execute_with_oom_recovery(
                        mock_func_with_oom, backend="deepseek", batch=batch
                    )

        # Nach OOM sollte Batch-Größe reduziert worden sein
        assert manager.get_optimal_batch_size("deepseek") < 4

    @pytest.mark.asyncio
    async def test_non_oom_error_is_raised(self):
        """Nicht-OOM-Fehler werden weitergegeben."""
        manager = GPURecoveryManager()

        async def mock_func_with_error(batch):
            raise ValueError("Invalid input")

        with patch.object(manager, '_is_oom_error', return_value=False):
            with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
                with pytest.raises(ValueError) as exc_info:
                    await manager.execute_with_oom_recovery(
                        mock_func_with_error,
                        backend="deepseek",
                        batch=["doc1"],
                    )

                assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises_error(self):
        """Überschreiten von max_retries wirft GPURecoveryError."""
        manager = GPURecoveryManager()

        async def mock_func_always_oom(batch):
            raise RuntimeError("CUDA out of memory")

        with patch.object(manager, '_is_oom_error', return_value=True):
            with patch.object(manager, 'clear_gpu_memory', new_callable=AsyncMock):
                with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
                    with pytest.raises(GPURecoveryError) as exc_info:
                        await manager.execute_with_oom_recovery(
                            mock_func_always_oom,
                            backend="deepseek",
                            batch=["doc1"],
                            max_retries=3,
                        )

                    assert exc_info.value.backend == "deepseek"


# ==================== GPU Memory Guard Tests ====================


class TestGPUMemoryGuard:
    """Tests für gpu_memory_guard Context Manager."""

    @pytest.mark.asyncio
    async def test_guard_yields_manager(self):
        """gpu_memory_guard gibt Manager zurück."""
        async with gpu_memory_guard() as manager:
            assert isinstance(manager, GPURecoveryManager)

    @pytest.mark.asyncio
    async def test_guard_clears_memory_when_threshold_exceeded(self):
        """gpu_memory_guard löscht Speicher bei Überschreitung."""
        with patch.object(GPURecoveryManager, 'get_memory_stats') as mock_stats:
            with patch.object(GPURecoveryManager, 'clear_gpu_memory', new_callable=AsyncMock) as mock_clear:
                # Simuliere hohe Speichernutzung nach Verarbeitung
                mock_stats.side_effect = [
                    GPUMemoryStats(allocated_gb=5.0),  # Vorher
                    GPUMemoryStats(allocated_gb=15.0),  # Nachher (über Threshold)
                ]

                async with gpu_memory_guard(threshold_gb=13.6):
                    pass  # Verarbeitung simulieren

                # clear_gpu_memory sollte aufgerufen worden sein
                mock_clear.assert_called_once()


# ==================== Global Manager Tests ====================


class TestGetGPURecoveryManager:
    """Tests für get_gpu_recovery_manager."""

    def test_returns_manager_instance(self):
        """get_gpu_recovery_manager gibt Manager-Instanz zurück."""
        manager = get_gpu_recovery_manager()

        assert isinstance(manager, GPURecoveryManager)

    def test_returns_same_instance(self):
        """get_gpu_recovery_manager gibt dieselbe Instanz zurück (Singleton)."""
        manager1 = get_gpu_recovery_manager()
        manager2 = get_gpu_recovery_manager()

        assert manager1 is manager2


# ==================== Integration-Style Tests ====================


class TestIntegrationScenarios:
    """Integration-Style Tests mit realistischen Szenarien."""

    @pytest.mark.asyncio
    async def test_batch_processing_workflow(self):
        """Vollständiger Batch-Processing Workflow."""
        manager = GPURecoveryManager()
        processed_items = []

        async def process_batch(batch):
            processed_items.extend(batch)
            return [{"status": "ok", "item": item} for item in batch]

        with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
            documents = [f"doc_{i}" for i in range(10)]
            results = await manager.execute_with_oom_recovery(
                process_batch, backend="deepseek", batch=documents
            )

            assert len(results) == 10
            assert len(processed_items) == 10

    @pytest.mark.asyncio
    async def test_recovery_with_gradual_success(self):
        """Recovery mit schrittweisem Erfolg nach OOM."""
        manager = GPURecoveryManager()
        attempts = []

        async def process_with_recovery(batch):
            attempts.append(len(batch))

            # Erste zwei Versuche: OOM bei großen Batches
            if len(batch) > 2 and len(attempts) <= 2:
                raise RuntimeError("CUDA out of memory")

            return [{"processed": item} for item in batch]

        with patch.object(manager, '_is_oom_error', side_effect=lambda e: "out of memory" in str(e).lower()):
            with patch.object(manager, 'clear_gpu_memory', new_callable=AsyncMock):
                with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
                    documents = [f"doc_{i}" for i in range(6)]
                    results = await manager.execute_with_oom_recovery(
                        process_with_recovery,
                        backend="deepseek",
                        batch=documents,
                        max_retries=5,
                    )

                    assert len(results) == 6

    def test_stats_after_multiple_operations(self):
        """Statistiken nach mehreren Operationen."""
        manager = GPURecoveryManager()

        # Simuliere mehrere OOM-Ereignisse
        manager._reduce_batch_size("deepseek", 8)
        manager._reduce_batch_size("deepseek", 4)
        manager._oom_count["deepseek"] = 2
        manager._reduce_batch_size("got_ocr", 16)
        manager._oom_count["got_ocr"] = 1

        stats = manager.get_stats()

        assert stats["oom_counts"]["deepseek"] == 2
        assert stats["oom_counts"]["got_ocr"] == 1
        assert len(stats["batch_size_history"]["deepseek"]) == 2
        assert len(stats["batch_size_history"]["got_ocr"]) == 1


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests für Randfälle."""

    def test_manager_with_unknown_backend(self):
        """Manager funktioniert mit unbekanntem Backend."""
        manager = GPURecoveryManager()

        size = manager.get_optimal_batch_size("totally_unknown_backend")
        assert size == 4  # Default fallback

        new_size = manager._reduce_batch_size("totally_unknown_backend", 4)
        assert new_size == 2  # 4 * 0.5

    @pytest.mark.asyncio
    async def test_batch_with_single_item(self):
        """Verarbeitung mit einzelnem Item."""
        manager = GPURecoveryManager()

        async def process(batch):
            return batch

        with patch.object(manager, 'get_memory_stats', return_value=GPUMemoryStats()):
            result = await manager.execute_with_oom_recovery(
                process, backend="deepseek", batch=["single"]
            )

            assert result == ["single"]

    def test_memory_stats_defaults_on_exception(self):
        """get_memory_stats gibt Defaults bei Exception."""
        manager = GPURecoveryManager()

        with patch('app.core.gpu_recovery.TORCH_AVAILABLE', True):
            with patch('app.core.gpu_recovery.torch') as mock_torch:
                mock_torch.cuda.is_available.return_value = True
                mock_torch.cuda.get_device_properties.side_effect = RuntimeError("GPU error")

                stats = manager.get_memory_stats()

                assert stats.total_gb == 0.0
