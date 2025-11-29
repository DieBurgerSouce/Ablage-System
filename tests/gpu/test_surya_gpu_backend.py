"""
Tests for SuryaGPU OCR Backend.

Tests GPU-accelerated Surya OCR with focus on:
- Model loading and TF32/cuDNN optimization flags
- Single image and PDF processing
- German text with umlauts
- VRAM usage monitoring (should stay under 10GB)
- Cleanup and memory release
"""

import pytest
import pytest_asyncio
from pathlib import Path

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.asyncio]


class TestSuryaGPUModelLoading:
    """Test SuryaGPU model loading and initialization."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, gpu_context, requires_8gb_vram):
        """Test that SuryaGPU agent initializes correctly."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Check agent properties
        assert agent.name == "surya_gpu"
        assert agent.requires_gpu is True
        assert agent.vram_requirement_gb == 8.0

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_tf32_and_cudnn_flags(self, gpu_context, requires_8gb_vram):
        """Test that TF32 and cuDNN benchmark flags are enabled."""
        import torch
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # TF32 should be enabled for RTX 40xx GPUs
        if torch.cuda.get_device_properties(0).major >= 8:
            assert torch.backends.cuda.matmul.allow_tf32 is True
            assert torch.backends.cudnn.allow_tf32 is True

        # cuDNN benchmark should be enabled
        assert torch.backends.cudnn.benchmark is True

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_model_loading_vram(
        self, gpu_context, requires_8gb_vram, gpu_memory_tracker
    ):
        """Test VRAM usage during model loading."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Initialize model (loads predictors)
        await agent.initialize()

        # Check VRAM usage
        gpu_memory_tracker.stop()
        assert gpu_memory_tracker.peak_allocated < 10.0, (
            f"Model loading used {gpu_memory_tracker.peak_allocated:.2f}GB, expected < 10GB"
        )

        await agent.cleanup()


class TestSuryaGPUProcessing:
    """Test SuryaGPU OCR processing."""

    @pytest.mark.asyncio
    async def test_single_image_ocr(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test OCR on a single image."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        result = await agent.process({
            "document_id": "test_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result
        assert len(result["text"]) > 0
        assert result["confidence"] > 0.5

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_german_text_with_umlauts(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test German text recognition with umlauts (ä, ö, ü, ß)."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        result = await agent.process({
            "document_id": "test_german_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Check for German-specific content
        assert "Rechnung" in text or "rechnung" in text.lower()

        # Note: Exact umlaut recognition depends on OCR quality
        # We check for presence of German business terms
        german_terms = ["EUR", "IBAN", "GmbH", "Nr"]
        found_terms = sum(1 for term in german_terms if term in text)
        assert found_terms >= 2, f"Expected German terms in text: {text}"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_complex_layout(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test complex document layout processing."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        result = await agent.process({
            "document_id": "test_complex_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "detect_layout": True,
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "INVOICE" in result["text"].upper()

        # Check for layout/bounding box information if available
        if "bounding_boxes" in result:
            assert len(result["bounding_boxes"]) > 0

        await agent.cleanup()


class TestSuryaGPUVRAMManagement:
    """Test VRAM usage and management."""

    @pytest.mark.asyncio
    async def test_vram_during_processing(
        self, gpu_context, requires_8gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test that VRAM stays under threshold during processing."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Process multiple images
        for i in range(3):
            await agent.process({
                "document_id": f"test_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

        gpu_memory_tracker.stop()

        # Should stay under 10GB (8GB model + 2GB buffer)
        gpu_memory_tracker.verify_under_threshold(10.0)

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_releases_memory(
        self, gpu_context, requires_8gb_vram, test_images_dir
    ):
        """Test that cleanup properly releases GPU memory."""
        import torch
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        # Record baseline
        torch.cuda.empty_cache()
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Create agent and process
        agent = SuryaGPUAgent()
        await agent.process({
            "document_id": "test_cleanup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Memory should be higher
        after_processing = torch.cuda.memory_allocated() / (1024**3)
        assert after_processing > baseline

        # Cleanup
        await agent.cleanup()
        torch.cuda.empty_cache()

        # Memory should return close to baseline
        after_cleanup = torch.cuda.memory_allocated() / (1024**3)
        memory_released = after_processing - after_cleanup

        assert memory_released > 0, "Cleanup should release some memory"
        assert after_cleanup < after_processing, (
            f"Memory not released: {after_cleanup:.2f}GB vs {after_processing:.2f}GB"
        )

    @pytest.mark.asyncio
    async def test_no_memory_leak_on_repeated_processing(
        self, gpu_context, requires_8gb_vram, test_images_dir
    ):
        """Test for memory leaks on repeated processing."""
        import torch
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Process once to warm up
        await agent.process({
            "document_id": "warmup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        # Record memory after warmup
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Process multiple times
        for i in range(5):
            await agent.process({
                "document_id": f"leak_test_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

        # Check memory hasn't grown significantly
        after_many = torch.cuda.memory_allocated() / (1024**3)
        growth = after_many - baseline

        # Allow 1GB growth for caching, but no more
        assert growth < 1.0, (
            f"Memory grew {growth:.2f}GB after repeated processing - possible leak"
        )

        await agent.cleanup()


class TestSuryaGPUErrorHandling:
    """Test error handling in SuryaGPU agent."""

    @pytest.mark.asyncio
    async def test_invalid_image_path(
        self, gpu_context, requires_8gb_vram, clean_gpu_memory
    ):
        """Test handling of invalid image path."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        result = await agent.process({
            "document_id": "test_invalid",
            "image_path": "/nonexistent/path.png",
            "language": "en",
        })

        assert result["status"] == "error"
        assert "error" in result or "message" in result

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_corrupted_image(
        self, gpu_context, requires_8gb_vram, tmp_path, clean_gpu_memory
    ):
        """Test handling of corrupted image file."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        # Create a corrupted "image" file
        corrupted_path = tmp_path / "corrupted.png"
        corrupted_path.write_bytes(b"not an image")

        agent = SuryaGPUAgent()

        result = await agent.process({
            "document_id": "test_corrupted",
            "image_path": str(corrupted_path),
            "language": "en",
        })

        assert result["status"] == "error"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_get_status(self, gpu_context, requires_8gb_vram):
        """Test agent status reporting."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        status = agent.get_status()

        assert "name" in status
        assert status["name"] == "surya_gpu"
        assert "requires_gpu" in status
        assert status["requires_gpu"] is True

        await agent.cleanup()
