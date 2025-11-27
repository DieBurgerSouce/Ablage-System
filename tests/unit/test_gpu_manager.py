"""
Unit tests for GPU resource management.

Tests GPU detection, VRAM allocation, batch size calculation,
and OOM error recovery without requiring actual GPU hardware.
"""

import pytest
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from gpu_manager import GPUManager


@pytest.mark.unit
class TestGPUManager:
    """Test GPU resource management."""

    def setup_method(self):
        """Setup before each test."""
        self.gpu_manager = GPUManager()

    def test_gpu_detection(self):
        """Test that GPU can be detected."""
        status = self.gpu_manager.check_availability()

        assert "available" in status
        assert "reason" in status or "gpu_name" in status

        if status["available"]:
            assert status["total_gb"] > 0
            assert "gpu_name" in status
            print(f"[OK] GPU detected: {status['gpu_name']}")
        else:
            print(f"[!] No GPU: {status['reason']}")

    def test_vram_allocation(self):
        """Test VRAM allocation logic."""
        # Try to allocate for GOT-OCR
        result = self.gpu_manager.allocate_for_backend("got_ocr")

        assert "success" in result

        if result["success"]:
            assert result["backend"] == "got_ocr"
            if result.get("mode") != "cpu":
                assert result.get("allocated_gb", 0) > 0

            # Cleanup
            self.gpu_manager.deallocate_backend("got_ocr")

    def test_batch_size_calculation(self):
        """Test optimal batch size calculation."""
        batch_size = self.gpu_manager.get_optimal_batch_size("got_ocr")

        assert isinstance(batch_size, int)
        assert 1 <= batch_size <= 32
        print(f"[OK] Optimal batch size: {batch_size}")

    def test_oom_recovery(self):
        """Test OOM error recovery."""
        recovery_result = self.gpu_manager.handle_oom_error()

        assert "recovered" in recovery_result
        assert "message" in recovery_result or "error" in recovery_result

    @pytest.mark.parametrize(
        "backend,expected_min_gb",
        [
            ("deepseek", 12),
            ("got_ocr", 10),
            ("surya", 0),
        ],
    )
    def test_backend_vram_requirements(self, backend: str, expected_min_gb: int):
        """Test that backend VRAM requirements are correctly defined."""
        # Backend requirements are stored as instance attribute, not module-level constant
        assert backend in self.gpu_manager.backend_requirements
        assert self.gpu_manager.backend_requirements[backend] == expected_min_gb

    def test_allocate_multiple_backends(self):
        """Test allocating multiple backends simultaneously."""
        # Allocate first backend
        result1 = self.gpu_manager.allocate_for_backend("surya")
        assert result1["success"]

        # Allocate second backend
        result2 = self.gpu_manager.allocate_for_backend("got_ocr")
        assert "success" in result2

        # Cleanup
        self.gpu_manager.deallocate_backend("surya")
        if result2["success"]:
            self.gpu_manager.deallocate_backend("got_ocr")

    @pytest.mark.gpu
    def test_actual_gpu_memory_check(self):
        """Test actual GPU memory detection (requires GPU)."""
        status = self.gpu_manager.check_availability()

        if not status["available"]:
            pytest.skip("GPU not available")

        # Should have RTX 4080 with ~16GB
        assert status["total_gb"] >= 15.0
        assert status["total_gb"] <= 17.0
        assert "RTX" in status["gpu_name"] or "4080" in status["gpu_name"]
