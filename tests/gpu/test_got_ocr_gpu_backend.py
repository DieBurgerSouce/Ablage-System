"""
Tests for GOT-OCR 2.0 Backend.

Tests GOT-OCR transformer-based OCR with focus on:
- bfloat16 model loading
- Multiple output formats (plain, markdown, latex)
- Regional OCR with crop coordinates
- German text post-processing
- VRAM usage monitoring (should stay under 11GB)
"""

import pytest
import pytest_asyncio
from pathlib import Path

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.asyncio]


class TestGOTOCRModelLoading:
    """Test GOT-OCR model loading and initialization."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, gpu_context, requires_10gb_vram):
        """Test that GOT-OCR agent initializes correctly."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        # Check agent properties
        assert agent.name == "got_ocr"
        assert agent.requires_gpu is True
        assert agent.vram_requirement_gb == 10.0

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_bfloat16_model_loading(
        self, gpu_context, requires_10gb_vram, gpu_memory_tracker
    ):
        """Test model loading with bfloat16 dtype."""
        import torch
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()
        await agent.initialize()

        # Model should be loaded
        assert agent._model_loaded is True
        assert agent.model is not None

        # Check dtype is bfloat16
        model_dtype = next(agent.model.parameters()).dtype
        assert model_dtype == torch.bfloat16, (
            f"Expected bfloat16, got {model_dtype}"
        )

        # Check VRAM usage
        gpu_memory_tracker.stop()
        assert gpu_memory_tracker.peak_allocated < 11.0, (
            f"Model loading used {gpu_memory_tracker.peak_allocated:.2f}GB, expected < 11GB"
        )

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_device_map_auto(self, gpu_context, requires_10gb_vram):
        """Test that model uses device_map='auto'."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()
        await agent.initialize()

        # Model should be on CUDA
        device = next(agent.model.parameters()).device
        assert device.type == "cuda", f"Model on {device}, expected CUDA"

        await agent.cleanup()


class TestGOTOCROutputFormats:
    """Test GOT-OCR output format options."""

    @pytest.mark.asyncio
    async def test_plain_text_output(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test plain text output format."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_plain_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
            "output_format": "plain",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result
        text = result["text"]

        # Plain text should not have markdown formatting
        assert "**" not in text  # No bold
        assert "```" not in text  # No code blocks

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_markdown_output(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test markdown output format."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_markdown_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "output_format": "markdown",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result
        # Markdown format may include formatting

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_latex_output(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test LaTeX output format for formulas."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_latex_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "output_format": "latex",
        })

        assert result.get("success") is True or result.get("status") == "success"
        # LaTeX output handling

        await agent.cleanup()


class TestGOTOCRGermanProcessing:
    """Test GOT-OCR German text processing."""

    @pytest.mark.asyncio
    async def test_german_text_recognition(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test German text recognition with umlauts."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_german_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Check for German content
        german_indicators = ["EUR", "IBAN", "Rechnung", "GmbH", "Müller", "Größe"]
        found = sum(1 for ind in german_indicators if ind in text)
        assert found >= 2, f"Expected German terms in: {text}"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_german_postprocessing(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test German post-processing for umlaut restoration."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_german_post_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
            "apply_postprocessing": True,
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Post-processing should help with umlaut recognition
        # Check that common patterns are recognized
        assert len(text) > 0

        await agent.cleanup()


class TestGOTOCRRegionalOCR:
    """Test GOT-OCR regional/crop OCR feature."""

    @pytest.mark.asyncio
    async def test_regional_ocr(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test OCR on specific region of image."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_region_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "region": {
                "x1": 0,
                "y1": 0,
                "x2": 1200,
                "y2": 100,  # Just header area
            },
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Should get header text only
        assert "INVOICE" in text.upper()

        await agent.cleanup()


class TestGOTOCRVRAMManagement:
    """Test VRAM usage and management for GOT-OCR."""

    @pytest.mark.asyncio
    async def test_vram_during_processing(
        self, gpu_context, requires_10gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test VRAM stays under threshold during processing."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        # Process multiple images
        for i in range(3):
            await agent.process({
                "document_id": f"test_{i}",
                "image_path": str(test_images_dir / "simple_text.png"),
                "language": "en",
            })

        gpu_memory_tracker.stop()

        # Should stay under 11GB (10GB model + 1GB buffer)
        gpu_memory_tracker.verify_under_threshold(11.0)

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_vram_threshold_critical(
        self, gpu_context, requires_10gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test that processing stays under 85% VRAM threshold."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_vram_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
        })

        gpu_memory_tracker.stop()

        # Critical threshold is 13.6GB (85% of 16GB)
        gpu_memory_tracker.verify_under_threshold(13.6)

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_releases_memory(
        self, gpu_context, requires_10gb_vram, test_images_dir
    ):
        """Test that cleanup properly releases GPU memory."""
        import torch
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        # Record baseline
        torch.cuda.empty_cache()
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Create agent and process
        agent = GOTOCRAgent()
        await agent.process({
            "document_id": "test_cleanup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        after_processing = torch.cuda.memory_allocated() / (1024**3)

        # Cleanup
        await agent.cleanup()
        torch.cuda.empty_cache()

        after_cleanup = torch.cuda.memory_allocated() / (1024**3)

        # Memory should be released
        assert after_cleanup < after_processing, (
            f"Memory not released: {after_cleanup:.2f}GB vs {after_processing:.2f}GB"
        )


class TestGOTOCRErrorHandling:
    """Test error handling in GOT-OCR agent."""

    @pytest.mark.asyncio
    async def test_invalid_image_path(
        self, gpu_context, requires_10gb_vram, clean_gpu_memory
    ):
        """Test handling of invalid image path."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_invalid",
            "image_path": "/nonexistent/path.png",
            "language": "en",
        })

        assert result["status"] == "error"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_invalid_output_format(
        self, gpu_context, requires_10gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test handling of invalid output format."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        result = await agent.process({
            "document_id": "test_invalid_format",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
            "output_format": "invalid_format",
        })

        # Should either default to plain or return error
        assert result["status"] in ["success", "error"]

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_get_status(self, gpu_context, requires_10gb_vram):
        """Test agent status reporting."""
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        agent = GOTOCRAgent()

        status = agent.get_status()

        assert "name" in status
        assert status["name"] == "got_ocr"
        assert "requires_gpu" in status
        assert status["requires_gpu"] is True

        await agent.cleanup()
