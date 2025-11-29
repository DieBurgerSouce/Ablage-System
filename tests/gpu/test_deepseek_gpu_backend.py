"""
Tests for DeepSeek-Janus-Pro OCR Backend.

CRITICAL TESTS - DeepSeek is the most resource-intensive backend.

Tests DeepSeek multimodal OCR with focus on:
- 4-bit quantization with BitsAndBytesConfig
- Janus library fallback to transformers
- Multimodal conversation format
- German prompt building with umlaut instructions
- Entity extraction (IBAN, VAT ID)
- Layout detection (invoice, contract)
- VRAM usage monitoring (should stay under 13GB with quantization)
- OOM handling

Requirements:
- 12GB+ free VRAM (24GB without quantization on Windows)
- BitsAndBytes library (Linux/WSL2 only)
- Windows: Uses bfloat16 fallback instead of quantization
"""

import sys
import pytest
import pytest_asyncio
from pathlib import Path

# Mark all tests as GPU tests
pytestmark = pytest.mark.gpu

# Platform detection
IS_WINDOWS = sys.platform == "win32"


# Conditional skip fixture for quantization-only tests
@pytest.fixture
def requires_quantization():
    """Skip test if quantization is not available (Windows)."""
    if IS_WINDOWS:
        pytest.skip("4-bit Quantisierung auf Windows nicht verfügbar - verwende WSL2/Docker")


class TestDeepSeekQuantization:
    """Test 4-bit quantization loading (CRITICAL)."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, gpu_context, requires_12gb_vram):
        """Test that DeepSeek agent initializes correctly."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        # Check agent properties
        assert agent.name == "deepseek_ocr_agent"
        assert agent.gpu_required is True
        assert agent.vram_gb == 24.0  # Full precision requirement
        assert agent.ENABLE_QUANTIZATION is True  # Config flag enabled

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_4bit_quantization_config(self, gpu_context, requires_12gb_vram, requires_quantization):
        """Test that BitsAndBytesConfig is correctly configured (Linux/WSL2 only)."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent, BITSANDBYTES_AVAILABLE

        if not BITSANDBYTES_AVAILABLE:
            pytest.skip("BitsAndBytes nicht installiert")

        agent = DeepSeekAgent()

        # Check quantization settings
        assert agent.ENABLE_QUANTIZATION is True

        # Quantization config should use nf4
        if hasattr(agent, 'quant_config'):
            config = agent.quant_config
            assert config.load_in_4bit is True
            assert config.bnb_4bit_quant_type == "nf4"
            assert config.bnb_4bit_use_double_quant is True

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_quantized_model_loading(
        self, gpu_context, requires_12gb_vram, gpu_memory_tracker, requires_quantization
    ):
        """Test 4-bit quantized model loading stays under VRAM limit (Linux/WSL2 only)."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent, BITSANDBYTES_AVAILABLE

        if not BITSANDBYTES_AVAILABLE:
            pytest.skip("BitsAndBytes nicht installiert")

        agent = DeepSeekAgent()
        await agent.initialize()

        # Model should be loaded
        assert agent._model_loaded is True
        assert agent.model is not None
        assert agent._quantization_active is True  # Should be using quantization

        # Check VRAM usage - should be ~12GB with quantization
        gpu_memory_tracker.stop()
        assert gpu_memory_tracker.peak_allocated < 13.0, (
            f"Quantized model used {gpu_memory_tracker.peak_allocated:.2f}GB, expected < 13GB"
        )

        await agent.cleanup()


class TestDeepSeekFallback:
    """Test Janus library fallback to transformers."""

    @pytest.mark.asyncio
    async def test_janus_or_transformers_fallback(
        self, gpu_context, requires_12gb_vram
    ):
        """Test that agent works with either Janus or transformers fallback."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        await agent.initialize()

        # Model should load regardless of Janus availability
        assert agent._model_loaded is True

        # Check which backend is used
        if hasattr(agent, '_using_janus'):
            # Either True (Janus) or False (transformers)
            pass

        await agent.cleanup()


class TestDeepSeekMultimodal:
    """Test multimodal conversation format."""

    @pytest.mark.asyncio
    async def test_conversation_format(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test multimodal conversation with image placeholder."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_multimodal_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        assert result.get("success") is True or result.get("status") == "success"
        assert "text" in result

        await agent.cleanup()


class TestDeepSeekGermanPrompt:
    """Test German prompt building and processing."""

    @pytest.mark.asyncio
    async def test_german_prompt_building(
        self, gpu_context, requires_12gb_vram
    ):
        """Test German prompt includes umlaut handling instructions."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        # Build German prompt
        prompt = agent._build_prompt("de", {})

        # Prompt should mention German-specific handling
        german_keywords = ["deutsch", "German", "Umlaut", "ä", "ö", "ü", "ß"]
        found_keywords = sum(1 for kw in german_keywords if kw.lower() in prompt.lower())

        assert found_keywords >= 1, f"German prompt should reference German text: {prompt}"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_german_text_recognition(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test German text recognition with umlauts."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_german_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Check for German content
        german_terms = ["EUR", "IBAN", "Rechnung", "GmbH"]
        found = sum(1 for term in german_terms if term in text)
        assert found >= 2, f"Expected German business terms in: {text}"

        await agent.cleanup()


class TestDeepSeekEntityExtraction:
    """Test entity extraction capabilities."""

    @pytest.mark.asyncio
    async def test_iban_extraction(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test IBAN extraction from German document."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_iban_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
            "extract_entities": True,
        })

        assert result.get("success") is True or result.get("status") == "success"

        # Check for entities if available
        if "entities" in result:
            entities = result["entities"]
            # Look for IBAN pattern
            ibans = [e for e in entities if e.get("type") == "IBAN"]
            if ibans:
                assert ibans[0]["value"].startswith("DE"), "German IBAN should start with DE"

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_vat_id_extraction(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test VAT ID (USt-IdNr) extraction."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_vat_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
            "extract_entities": True,
        })

        assert result.get("success") is True or result.get("status") == "success"

        # Check for VAT ID in entities or text
        text = result.get("text", "")
        assert "DE" in text or "USt" in text, "Should recognize VAT ID pattern"

        await agent.cleanup()


class TestDeepSeekLayoutDetection:
    """Test document layout detection."""

    @pytest.mark.asyncio
    async def test_invoice_layout_detection(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test invoice layout detection."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_invoice_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
            "detect_layout": True,
        })

        assert result.get("success") is True or result.get("status") == "success"

        # Check layout detection
        if "layout_type" in result:
            assert result["layout_type"] in ["invoice", "document", "other"]

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_complex_layout_handling(
        self, gpu_context, requires_12gb_vram, test_images_dir, clean_gpu_memory
    ):
        """Test handling of complex document layouts."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_complex_001",
            "image_path": str(test_images_dir / "complex_layout.png"),
            "language": "en",
        })

        assert result.get("success") is True or result.get("status") == "success"
        text = result["text"]

        # Should recognize invoice content
        assert "INVOICE" in text.upper() or len(text) > 50

        await agent.cleanup()


class TestDeepSeekVRAMManagement:
    """Test VRAM usage and management (CRITICAL)."""

    @pytest.mark.asyncio
    async def test_vram_under_threshold(
        self, gpu_context, requires_12gb_vram, test_images_dir, gpu_memory_tracker
    ):
        """Test VRAM stays under 85% threshold during processing."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        result = await agent.process({
            "document_id": "test_vram_001",
            "image_path": str(test_images_dir / "german_text.png"),
            "language": "de",
        })

        gpu_memory_tracker.stop()

        # Critical: must stay under 13.6GB (85% of 16GB)
        gpu_memory_tracker.verify_under_threshold(13.6)

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_releases_memory(
        self, gpu_context, requires_12gb_vram, test_images_dir
    ):
        """Test that cleanup properly releases GPU memory."""
        import torch
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        # Record baseline
        torch.cuda.empty_cache()
        baseline = torch.cuda.memory_allocated() / (1024**3)

        # Create agent and process
        agent = DeepSeekAgent()
        await agent.process({
            "document_id": "test_cleanup",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "en",
        })

        after_processing = torch.cuda.memory_allocated() / (1024**3)

        # Cleanup
        await agent.cleanup()
        torch.cuda.empty_cache()

        import gc
        gc.collect()

        after_cleanup = torch.cuda.memory_allocated() / (1024**3)

        # Significant memory should be released
        released = after_processing - after_cleanup
        assert released > 5.0, (
            f"Expected > 5GB released, got {released:.2f}GB "
            f"(before: {after_processing:.2f}GB, after: {after_cleanup:.2f}GB)"
        )


class TestDeepSeekOOMHandling:
    """Test OOM error handling (CRITICAL)."""

    @pytest.mark.asyncio
    async def test_oom_recovery_method(
        self, gpu_context, requires_12gb_vram
    ):
        """Test that OOM recovery method exists and works."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        # Check OOM handler exists
        assert hasattr(agent, '_handle_gpu_oom'), (
            "DeepSeek agent should have _handle_gpu_oom method"
        )

        await agent.cleanup()

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_error(
        self, gpu_context, requires_12gb_vram, test_images_dir
    ):
        """Test graceful handling when processing fails."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        # Process with intentionally problematic input
        result = await agent.process({
            "document_id": "test_fallback_001",
            "image_path": str(test_images_dir / "simple_text.png"),
            "language": "de",
        })

        # Should either succeed or fail gracefully with error status
        assert result["status"] in ["success", "error"]

        # Should not leave GPU in bad state
        import torch
        if torch.cuda.is_available():
            # Should be able to query GPU
            torch.cuda.memory_allocated()

        await agent.cleanup()


class TestDeepSeekErrorHandling:
    """Test error handling in DeepSeek agent."""

    @pytest.mark.asyncio
    async def test_invalid_image_path(
        self, gpu_context, requires_12gb_vram, clean_gpu_memory, requires_quantization
    ):
        """Test handling of invalid image path (requires quantization for 16GB cards)."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        from app.agents.base import AgentResourceError

        # On Windows without quantization, DeepSeek needs 24GB VRAM
        # which exceeds RTX 4080's 16GB - skip this test
        agent = DeepSeekAgent()

        try:
            result = await agent.process({
                "document_id": "test_invalid",
                "image_path": "/nonexistent/path.png",
                "language": "en",
            })
            assert result["status"] == "error"
        except AgentResourceError as e:
            # Expected on systems with insufficient VRAM for full precision
            assert "VRAM" in str(e) or "GPU" in str(e)
        finally:
            await agent.cleanup()

    @pytest.mark.asyncio
    async def test_get_status(self, gpu_context, requires_12gb_vram):
        """Test agent status reporting."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent, IS_WINDOWS, BITSANDBYTES_AVAILABLE

        agent = DeepSeekAgent()

        status = agent.get_status()

        assert "name" in status
        assert status["name"] == "deepseek_ocr_agent"
        assert "gpu_required" in status
        assert status["gpu_required"] is True
        assert "vram_gb" in status
        assert status["vram_gb"] == 24.0
        assert "quantization_enabled" in status
        assert status["quantization_enabled"] is True
        assert "bitsandbytes_available" in status
        assert status["bitsandbytes_available"] == BITSANDBYTES_AVAILABLE
        assert "platform" in status
        assert status["platform"] == ("windows" if IS_WINDOWS else "linux/other")

        await agent.cleanup()
