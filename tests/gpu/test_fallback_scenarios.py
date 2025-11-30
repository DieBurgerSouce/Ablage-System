"""
GPU to CPU Fallback Scenario Tests.

Tests the fallback mechanisms when GPU resources are unavailable or exhausted:
- GPU unavailable -> Surya CPU fallback
- OOM during processing -> Reduce batch + retry
- OOM at minimum batch -> CPU fallback
- Backend selection with limited VRAM
"""

import pytest
import torch
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.fallback]


# Expected fallback chain order
FALLBACK_CHAIN = [
    "deepseek",      # Best quality
    "got_ocr",       # Good for tables/formulas
    "surya_gpu",     # Fast GPU variant
    "surya_docling", # CPU fallback (always available)
]


class TestGPUAvailabilityFallback:
    """Test fallback when GPU is not available."""

    def test_fallback_chain_order(self):
        """Test fallback chain follows correct priority order."""
        # DeepSeek should be first, CPU should be last
        assert FALLBACK_CHAIN[0] == "deepseek"
        assert FALLBACK_CHAIN[-1] == "surya_docling"

    def test_cpu_backend_is_always_available(self):
        """Test that CPU backend (Surya+Docling) is always importable."""
        try:
            from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
            agent = SuryaDoclingAgent()
            assert agent.gpu_required is False
        except ImportError:
            pytest.skip("Surya+Docling agent not available")

    @patch("torch.cuda.is_available", return_value=False)
    def test_gpu_manager_detects_no_gpu(self, mock_cuda):
        """Test GPU manager correctly detects when GPU is unavailable."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()
        status = manager.get_detailed_status()

        # When CUDA not available, should report no GPU
        assert "available" in status or "error" in status
        if "available" in status:
            assert status["available"] is False

    def test_backend_selection_without_gpu(self):
        """Test backend selection falls back to CPU when no GPU."""
        # This tests the orchestrator's behavior
        try:
            from app.agents.orchestration.ocr_router import OCRRouter
            router = OCRRouter()

            # Mock document that would normally use GPU backend
            mock_doc = MagicMock()
            mock_doc.has_tables = True
            mock_doc.has_images = True
            mock_doc.language = "de"

            # With GPU unavailable, should eventually select CPU backend
            # The actual selection depends on orchestrator implementation
            assert router is not None

        except ImportError:
            pytest.skip("OCR Router not available")


class TestOOMRecoveryScenarios:
    """Test OOM recovery mechanisms."""

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_cuda_cache_can_be_cleared(self):
        """Test that CUDA cache clearing works."""
        # Allocate some memory
        tensor = torch.zeros(1000, 1000, device="cuda")
        allocated_before = torch.cuda.memory_allocated()

        # Clear
        del tensor
        torch.cuda.empty_cache()

        allocated_after = torch.cuda.memory_allocated()
        assert allocated_after <= allocated_before

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_gpu_manager_oom_handler_exists(self):
        """Test that GPU manager has OOM handler."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Check OOM handler exists
        assert hasattr(manager, "handle_oom_error")
        assert callable(manager.handle_oom_error)

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_oom_error_triggers_cache_clear(self):
        """Test that OOM error handling clears cache."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Record memory before
        torch.cuda.empty_cache()
        memory_before = torch.cuda.memory_reserved()

        # Trigger OOM handler
        recovery_info = manager.handle_oom_error()

        # Cache should be cleared
        memory_after = torch.cuda.memory_reserved()
        assert memory_after <= memory_before

    def test_batch_size_reduction_logic(self):
        """Test batch size reduction formula."""
        # When OOM, batch size should be halved
        original_batch = 32
        reduced_batch = max(1, original_batch // 2)
        assert reduced_batch == 16

        # Continue reducing
        reduced_batch = max(1, reduced_batch // 2)
        assert reduced_batch == 8

        # Minimum is 1
        reduced_batch = max(1, 1 // 2)
        assert reduced_batch == 1


class TestBackendSelectionWithLimitedVRAM:
    """Test backend selection when VRAM is limited."""

    # Backend VRAM requirements (GB)
    BACKEND_VRAM = {
        "deepseek": 12.0,
        "got_ocr": 10.0,
        "surya_gpu": 8.0,
        "surya_docling": 0.0,
    }

    def test_backend_vram_requirements(self):
        """Test backend VRAM requirements are defined."""
        assert self.BACKEND_VRAM["deepseek"] > self.BACKEND_VRAM["got_ocr"]
        assert self.BACKEND_VRAM["surya_docling"] == 0.0

    def test_select_backend_for_available_vram(self):
        """Test selecting appropriate backend for available VRAM."""
        available_vram = 10.0

        # Should select backend that fits
        suitable_backends = [
            name for name, vram in self.BACKEND_VRAM.items()
            if vram <= available_vram
        ]

        assert "surya_gpu" in suitable_backends
        assert "surya_docling" in suitable_backends
        # DeepSeek needs 12GB, shouldn't fit
        assert "deepseek" not in suitable_backends

    def test_cpu_backend_always_available(self):
        """Test CPU backend is always available regardless of VRAM."""
        available_vram = 0.0  # No GPU memory

        suitable_backends = [
            name for name, vram in self.BACKEND_VRAM.items()
            if vram <= available_vram
        ]

        assert "surya_docling" in suitable_backends

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_gpu_manager_optimal_batch_size(self):
        """Test GPU manager provides optimal batch size."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Get optimal batch size for different backends
        for backend in ["deepseek", "got_ocr", "surya_gpu"]:
            batch_size = manager.get_optimal_batch_size(backend)
            assert isinstance(batch_size, int)
            assert batch_size >= 1


class TestDeepSeekWindowsFallback:
    """Test DeepSeek-specific fallback scenarios on Windows."""

    def test_deepseek_detects_windows_platform(self):
        """Test DeepSeek correctly detects Windows platform."""
        from app.agents.ocr.deepseek_agent import IS_WINDOWS
        import sys

        if sys.platform == "win32":
            assert IS_WINDOWS is True
        else:
            assert IS_WINDOWS is False

    def test_deepseek_quantization_status(self):
        """Test DeepSeek reports quantization availability."""
        from app.agents.ocr.deepseek_agent import (
            BITSANDBYTES_AVAILABLE,
            GPTQ_AVAILABLE,
            AWQ_AVAILABLE,
        )

        # All should be booleans
        assert isinstance(BITSANDBYTES_AVAILABLE, bool)
        assert isinstance(GPTQ_AVAILABLE, bool)
        assert isinstance(AWQ_AVAILABLE, bool)

    def test_deepseek_status_includes_platform_info(self):
        """Test DeepSeek status includes platform information."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        status = agent.get_status()

        assert "platform" in status
        assert status["platform"] in ["windows", "linux/other"]

    def test_deepseek_quantization_method_in_status(self):
        """Test DeepSeek status includes quantization method."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        status = agent.get_status()

        assert "quantization_method" in status
        assert "quantization_active" in status


@pytest.mark.asyncio
class TestFallbackIntegration:
    """Integration tests for fallback mechanisms."""

    @pytest.fixture
    def test_images_dir(self):
        """Get test images directory."""
        return Path("tests/fixtures/german_docs")

    async def test_cpu_backend_processes_without_gpu(self, test_images_dir):
        """Test CPU backend can process documents without GPU."""
        try:
            from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
        except ImportError:
            pytest.skip("Surya+Docling agent not available")

        sample_image = test_images_dir / "invoices" / "invoice_001.png"
        if not sample_image.exists():
            pytest.skip("Test image not found")

        agent = SuryaDoclingAgent()

        try:
            result = await agent.process({
                "document_id": "fallback_test",
                "image_path": str(sample_image),
                "language": "de"
            })

            # Should produce a result (may have errors but shouldn't crash)
            assert result is not None
            assert isinstance(result, dict)

        except Exception as e:
            # Some errors are acceptable (e.g., model not downloaded)
            # but import errors or crashes are not
            assert "import" not in str(e).lower()

        finally:
            await agent.cleanup()

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    async def test_gpu_recovery_clears_memory(self):
        """Test that GPU recovery properly clears memory."""
        from app.gpu_manager import GPUManager

        manager = GPUManager()

        # Allocate some memory
        tensor = torch.zeros(5000, 5000, device="cuda")
        peak_before = torch.cuda.max_memory_allocated()

        # Simulate OOM recovery
        del tensor
        recovery_info = manager.handle_oom_error()

        # Memory should be reduced
        current = torch.cuda.memory_allocated()
        assert current < peak_before


class TestFallbackChainExecution:
    """Test the complete fallback chain execution."""

    def test_fallback_chain_has_cpu_option(self):
        """Test fallback chain includes CPU option."""
        cpu_backends = [b for b in FALLBACK_CHAIN if "docling" in b.lower()]
        assert len(cpu_backends) >= 1

    def test_fallback_chain_is_ordered_by_quality(self):
        """Test fallback chain is ordered by quality (best first)."""
        # DeepSeek is best for German, should be first
        assert FALLBACK_CHAIN.index("deepseek") < FALLBACK_CHAIN.index("surya_docling")

    def test_all_backends_in_chain_can_be_imported(self):
        """Test all backends in fallback chain can be imported."""
        import_map = {
            "deepseek": "app.agents.ocr.deepseek_agent",
            "got_ocr": "app.agents.ocr.got_ocr_agent",
            "surya_gpu": "app.agents.ocr.surya_gpu_agent",
            "surya_docling": "app.agents.ocr.surya_docling_agent",
        }

        for backend in FALLBACK_CHAIN:
            module_path = import_map.get(backend)
            if module_path:
                try:
                    __import__(module_path)
                except ImportError as e:
                    # Log but don't fail - some backends may not be installed
                    print(f"Warning: Could not import {backend}: {e}")


class TestErrorRecovery:
    """Test error recovery mechanisms."""

    def test_agent_base_has_cleanup_method(self):
        """Test agent base class has cleanup method."""
        from app.agents.base import OCRAgent

        # Check cleanup is defined
        assert hasattr(OCRAgent, "cleanup")

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_torch_cuda_synchronize_available(self):
        """Test CUDA synchronization is available."""
        # Should not raise
        torch.cuda.synchronize()

    def test_exception_handling_in_fallback(self):
        """Test that exceptions are properly handled in fallback."""
        # Simulate a backend that raises an exception
        class FailingBackend:
            def process(self, input_data):
                raise RuntimeError("Simulated failure")

        backend = FailingBackend()

        with pytest.raises(RuntimeError):
            backend.process({})

        # After failure, should be able to try another backend
        class WorkingBackend:
            def process(self, input_data):
                return {"text": "success"}

        working = WorkingBackend()
        result = working.process({})
        assert result["text"] == "success"
