"""
Tests for GPU Batch Processing.

Tests batch processing stability and performance:
- Batch stability over consecutive runs
- VRAM stability (no memory leaks)
- Throughput measurement
- Optimal batch size determination
"""

import os
import sys
import time
import pytest
import pytest_asyncio
from pathlib import Path
from typing import List

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.asyncio]


class TestBatchStability:
    """Test batch processing stability."""

    @pytest.mark.asyncio
    async def test_surya_gpu_batch_stability(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test SuryaGPU batch stability over multiple runs."""
        import torch
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Record initial memory
        initial_memory = torch.cuda.memory_allocated() / (1024**3)

        # Run 5 consecutive batches
        for batch_num in range(5):
            result = await agent.process({
                "document_id": f"batch_{batch_num}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })
            assert result.get("success") is True or result.get("status") == "success"

        # Check memory hasn't grown significantly
        final_memory = torch.cuda.memory_allocated() / (1024**3)
        growth = final_memory - initial_memory

        assert growth < 2.0, f"Memory grew {growth:.2f}GB over 5 batches - possible leak"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_got_ocr_batch_stability(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test GOT-OCR batch stability over multiple runs."""
        import torch
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        initial_memory = torch.cuda.memory_allocated() / (1024**3)

        # Run 5 consecutive batches
        for batch_num in range(5):
            result = await agent.process({
                "document_id": f"batch_{batch_num}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })
            assert result.get("success") is True or result.get("status") == "success"

        final_memory = torch.cuda.memory_allocated() / (1024**3)
        growth = final_memory - initial_memory

        assert growth < 2.0, f"Memory grew {growth:.2f}GB over 5 batches - possible leak"

        await agent.cleanup()


class TestVRAMStability:
    """Test VRAM remains stable during extended processing."""

    @pytest.mark.asyncio
    async def test_no_memory_leak_on_repeated_processing(
        self, gpu_context, requires_8gb_vram, test_images_dir
    ):
        """Test for memory leaks on 10 consecutive runs."""
        import torch
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Warm up
        await agent.process({
            "document_id": "warmup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Record baseline
        baseline = torch.cuda.memory_allocated() / (1024**3)
        peak_memory = baseline

        # Run 10 times
        for i in range(10):
            await agent.process({
                "document_id": f"leak_test_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

            current = torch.cuda.memory_allocated() / (1024**3)
            peak_memory = max(peak_memory, current)

        # Final check
        final = torch.cuda.memory_allocated() / (1024**3)
        growth = final - baseline

        # Allow 0.5GB growth for internal caching
        assert growth < 0.5, f"Memory grew {growth:.2f}GB over 10 runs"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_vram_returns_to_baseline_after_cleanup(
        self, gpu_context, requires_8gb_vram, test_images_dir
    ):
        """Test that VRAM returns close to baseline after cleanup."""
        import torch
        import gc
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        # Force clean state
        torch.cuda.empty_cache()
        gc.collect()
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Create and use agent
        agent = SuryaGPUAgent()
        await agent.process({
            "document_id": "test",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Memory should be higher
        during = torch.cuda.memory_allocated() / (1024**3)
        assert during > baseline

        # Cleanup
        await agent.cleanup()
        torch.cuda.empty_cache()
        gc.collect()

        # Check return to baseline
        after = torch.cuda.memory_allocated() / (1024**3)
        remaining = after - baseline

        # Should return within 1GB of baseline
        assert remaining < 1.0, f"Memory not released: {remaining:.2f}GB remaining"


class TestThroughputMeasurement:
    """Test throughput and performance measurement."""

    @pytest.mark.asyncio
    async def test_surya_gpu_throughput(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Measure SuryaGPU throughput (pages per second)."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()
        num_iterations = 5

        # Warm up
        await agent.process({
            "document_id": "warmup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Time processing
        start_time = time.perf_counter()

        for i in range(num_iterations):
            await agent.process({
                "document_id": f"perf_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

        elapsed = time.perf_counter() - start_time
        throughput = num_iterations / elapsed

        print(f"\nSuryaGPU Throughput: {throughput:.2f} pages/second")

        # Should achieve at least 1 page/second
        assert throughput >= 1.0, f"Throughput {throughput:.2f} p/s too low"

        await agent.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        sys.platform == "win32" and os.environ.get("RUN_GOT_OCR_GPU_TESTS") != "1",
        reason=(
            "GOT-OCR image-token-Mismatch unter Windows (Known Issue) - "
            "in WSL2/Docker ausfuehren oder RUN_GOT_OCR_GPU_TESTS=1 setzen"
        ),
    )
    async def test_got_ocr_throughput(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Measure GOT-OCR throughput (pages per second)."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()
        num_iterations = 5

        # Warm up
        await agent.process({
            "document_id": "warmup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Time processing
        start_time = time.perf_counter()

        for i in range(num_iterations):
            await agent.process({
                "document_id": f"perf_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

        elapsed = time.perf_counter() - start_time
        throughput = num_iterations / elapsed

        print(f"\nGOT-OCR Throughput: {throughput:.2f} pages/second")

        # Should achieve at least 1 page/second
        assert throughput >= 1.0, f"Throughput {throughput:.2f} p/s too low"

        await agent.cleanup()


class TestOptimalBatchSize:
    """Test optimal batch size determination."""

    @pytest.mark.asyncio
    async def test_gpu_manager_batch_size_calculation(self, gpu_context):
        """Test GPUManager calculates sensible batch sizes."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Check batch sizes for each backend
        deepseek_batch = manager.get_optimal_batch_size("deepseek")
        got_ocr_batch = manager.get_optimal_batch_size("got_ocr")
        surya_gpu_batch = manager.get_optimal_batch_size("surya_gpu")
        donut_batch = manager.get_optimal_batch_size("donut")

        # All should be at least 1
        assert deepseek_batch >= 1
        assert got_ocr_batch >= 1
        assert surya_gpu_batch >= 1
        assert donut_batch >= 1

        # Surya should allow largest batches (smallest memory footprint)
        assert surya_gpu_batch >= got_ocr_batch

        # DeepSeek should have smallest batches (largest memory footprint)
        assert deepseek_batch <= got_ocr_batch

    @pytest.mark.asyncio
    async def test_recovery_manager_batch_optimization(self, gpu_context):
        """Test GPURecoveryManager tracks optimal batch sizes."""
        from app.core.gpu_recovery import GPURecoveryManager

        manager = GPURecoveryManager()

        # Initial optimal sizes from config
        initial_deepseek = manager.get_optimal_batch_size("deepseek")
        assert initial_deepseek == 4  # Default from config

        # Simulate OOM reducing batch size
        manager._reduce_batch_size("deepseek", 4)
        new_deepseek = manager.get_optimal_batch_size("deepseek")
        assert new_deepseek == 2  # Reduced by 50%

        # Further reduction
        manager._reduce_batch_size("deepseek", 2)
        final_deepseek = manager.get_optimal_batch_size("deepseek")
        assert final_deepseek == 1  # Minimum


class TestBackendResourceAllocation:
    """Test GPU resource allocation for backends."""

    @pytest.mark.asyncio
    async def test_gpu_manager_allocation(self, gpu_context):
        """Test GPUManager allocation for backends."""
        from app.gpu_manager import GPUManager

        if not gpu_context.cuda_available:
            pytest.skip("CUDA not available")

        manager = GPUManager()

        # Check availability
        status = manager.check_availability()
        assert status["available"] is True

        # Allocate for surya (CPU, should always succeed)
        result = manager.allocate_for_backend("surya")
        assert result["success"] is True
        assert result["mode"] == "cpu"

        # Deallocate
        manager.deallocate_backend("surya")

    @pytest.mark.asyncio
    async def test_gpu_manager_vram_requirements(self, gpu_context):
        """Test that VRAM requirements are correctly configured."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Check all backends are registered
        required_backends = ["deepseek", "got_ocr", "surya_gpu", "donut", "surya"]
        for backend in required_backends:
            assert backend in manager.backend_requirements, f"Missing {backend}"

        # Check VRAM values
        assert manager.backend_requirements["deepseek"] == 12.0
        assert manager.backend_requirements["got_ocr"] == 10.0
        assert manager.backend_requirements["surya_gpu"] == 8.0
        assert manager.backend_requirements["donut"] == 8.0
        assert manager.backend_requirements["surya"] == 0.0  # CPU

    @pytest.mark.asyncio
    async def test_allocation_with_insufficient_vram(self, gpu_context):
        """Test allocation failure when VRAM insufficient."""
        from app.gpu_manager import GPUManager
        from unittest.mock import patch

        manager = GPUManager()

        # Mock low VRAM
        with patch.object(manager, 'check_availability') as mock_check:
            mock_check.return_value = {
                "available": True,
                "free_gb": 5.0,  # Not enough for deepseek
            }

            result = manager.allocate_for_backend("deepseek")
            assert result["success"] is False
            assert "insufficient" in result.get("reason", "").lower() or "Insufficient" in result.get("reason", "")
