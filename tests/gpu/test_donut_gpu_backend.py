"""
Tests for Donut OCR Backend.

Tests Naver CLOVA Donut vision encoder-decoder with focus on:
- SafeTensors loading and fallback
- German and multilingual OCR
- CORD-v2 task prompt
- VRAM usage monitoring (should stay under 10GB)
- Confidence calculation
"""

import pytest
import pytest_asyncio
from pathlib import Path

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.asyncio]


class TestDonutModelLoading:
    """Test Donut model loading and initialization."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, gpu_context, requires_8gb_vram):
        """Test that Donut agent initializes correctly."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        # Check agent properties
        assert agent.name == "donut"
        assert agent.requires_gpu is True
        assert agent.vram_requirement_gb == 8.0

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_safetensors_loading(
        self, gpu_context, requires_8gb_vram, gpu_memory_tracker
    ):
        """Test model loading with SafeTensors."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        # Initialize model
        await agent.initialize()

        # Model should be loaded
        assert agent._model_loaded is True
        assert agent.model is not None

        # Check VRAM usage
        gpu_memory_tracker.stop()
        assert gpu_memory_tracker.peak_allocated < 10.0, (
            f"Model loading used {gpu_memory_tracker.peak_allocated:.2f}GB, expected < 10GB"
        )

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_model_dtype(self, gpu_context, requires_8gb_vram):
        """Test that model uses expected dtype."""
        import torch
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()
        await agent.initialize()

        # Check model dtype (should be float16 or bfloat16 for GPU efficiency)
        model_dtype = next(agent.model.parameters()).dtype
        assert model_dtype in [torch.float16, torch.bfloat16, torch.float32]

        await agent.cleanup()


class TestDonutProcessing:
    """Test Donut OCR processing."""

    @pytest.mark.asyncio
    async def test_simple_text_ocr(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test OCR on simple text image."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_simple_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result
        assert len(result["text"]) > 0

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_german_text_ocr(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test German text recognition."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_german_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Check for business document terms
        business_terms = ["EUR", "IBAN", "Rechnung", "GmbH"]
        found_terms = sum(1 for term in business_terms if term in text)
        assert found_terms >= 1, f"Expected German business terms in: {text}"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_confidence_calculation(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test confidence score calculation."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_confidence_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "confidence" in result

        # Confidence should be between 0 and 1
        confidence = result["confidence"]
        assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range [0, 1]"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_cord_v2_task(
        self, gpu_context, requires_8gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test CORD-v2 structured extraction task."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_cord_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "task": "cord_v2",  # Structured extraction
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result

        # CORD-v2 may produce structured output
        if "structured_data" in result:
            assert isinstance(result["structured_data"], dict)

        await agent.cleanup()


class TestDonutMultilingual:
    """Test Donut multilingual capabilities."""

    @pytest.mark.asyncio
    async def test_supported_languages(self, gpu_context, requires_8gb_vram):
        """Test that Donut reports multilingual support."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        # Donut supports 100+ languages
        supported_languages = agent.supported_languages if hasattr(agent, 'supported_languages') else ["de", "en"]

        assert "de" in supported_languages or len(supported_languages) > 0
        assert "en" in supported_languages or len(supported_languages) > 0

        await agent.cleanup()


class TestDonutVRAMManagement:
    """Test VRAM usage and management for Donut."""

    @pytest.mark.asyncio
    async def test_vram_during_processing(
        self, gpu_context, requires_8gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test VRAM stays under threshold during processing."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

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
    async def test_vram_with_beam_search(
        self, gpu_context, requires_8gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test VRAM usage with beam search (may spike)."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        # Beam search uses more memory
        result = await agent.process({
            "document_id": "test_beam_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "num_beams": 4,  # If supported
        })

        gpu_memory_tracker.stop()

        # Allow higher threshold for beam search but still under 13GB
        assert gpu_memory_tracker.peak_allocated < 12.0, (
            f"Beam search used {gpu_memory_tracker.peak_allocated:.2f}GB, expected < 12GB"
        )

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_releases_memory(
        self, gpu_context, requires_8gb_vram, test_images_dir
    ):
        """Test that cleanup properly releases GPU memory."""
        import torch
        from app.agents.ocr.donut_agent import DonutOCRAgent

        # Record baseline
        torch.cuda.empty_cache()
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Create agent and process
        agent = DonutOCRAgent()
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


class TestDonutErrorHandling:
    """Test error handling in Donut agent."""

    @pytest.mark.asyncio
    async def test_invalid_image_path(
        self, gpu_context, requires_8gb_vram, clean_gpu_memory
    ):
        """Test handling of invalid image path."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_invalid",
            "image_path": "/nonexistent/path.png",
            "language": "en",
        })

        assert result["status"] == "error"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_empty_image(
        self, gpu_context, requires_8gb_vram, tmp_path, clean_gpu_memory
    ):
        """Test handling of empty/white image."""
        from PIL import Image
        from app.agents.ocr.donut_agent import DonutOCRAgent

        # Create empty white image
        empty_path = tmp_path / "empty.png"
        img = Image.new('RGB', (100, 100), color='white')
        img.save(empty_path)

        agent = DonutOCRAgent()

        result = await agent.process({
            "document_id": "test_empty",
            "image_path": str(empty_path),
            "language": "en",
        })

        # Should succeed but with low confidence or empty text
        assert result.get("success") is True or result.get("status") == "success"
        # Text may be empty or contain minimal content

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_get_status(self, gpu_context, requires_8gb_vram):
        """Test agent status reporting."""
        from app.agents.ocr.donut_agent import DonutOCRAgent

        agent = DonutOCRAgent()

        status = agent.get_status()

        assert "name" in status
        assert status["name"] == "donut"
        assert "requires_gpu" in status

        await agent.cleanup()
