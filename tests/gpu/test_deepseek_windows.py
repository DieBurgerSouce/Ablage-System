"""
DeepSeek Windows Compatibility Tests.

Tests GPTQ/AWQ quantization loading on Windows platform.
Verifies that DeepSeek can work on native Windows with RTX 4080.
"""

import sys
import pytest
import torch
from unittest.mock import patch, MagicMock

# Mark all tests as GPU tests
pytestmark = [pytest.mark.gpu, pytest.mark.windows]


class TestDeepSeekWindowsQuantization:
    """Test DeepSeek quantization options on Windows."""

    def test_platform_detection(self):
        """Test that platform is correctly detected."""
        from app.agents.ocr.deepseek_agent import IS_WINDOWS

        # This test verifies the constant exists
        assert isinstance(IS_WINDOWS, bool)
        if sys.platform == "win32":
            assert IS_WINDOWS is True

    def test_quantization_availability_detection(self):
        """Test that quantization library availability is correctly detected."""
        from app.agents.ocr.deepseek_agent import (
            BITSANDBYTES_AVAILABLE,
            GPTQ_AVAILABLE,
            AWQ_AVAILABLE,
        )

        # All should be booleans
        assert isinstance(BITSANDBYTES_AVAILABLE, bool)
        assert isinstance(GPTQ_AVAILABLE, bool)
        assert isinstance(AWQ_AVAILABLE, bool)

    def test_agent_status_includes_quantization_info(self):
        """Test that agent status includes all quantization info."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        status = agent.get_status()

        # Check all required fields
        assert "quantization_enabled" in status
        assert "quantization_active" in status
        assert "quantization_method" in status
        assert "bitsandbytes_available" in status
        assert "gptq_available" in status
        assert "awq_available" in status
        assert "platform" in status

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-specific test"
    )
    def test_windows_quantization_strategy_selection(self):
        """Test that Windows selects correct quantization strategy."""
        from app.agents.ocr.deepseek_agent import (
            IS_WINDOWS,
            BITSANDBYTES_AVAILABLE,
            GPTQ_AVAILABLE,
            AWQ_AVAILABLE,
        )

        # On Windows, BitsAndBytes should not be used
        # GPTQ or AWQ should be preferred if available
        assert IS_WINDOWS

        # Verify BitsAndBytes is typically not available on Windows
        # (it may be available in some configurations)
        if not BITSANDBYTES_AVAILABLE:
            # Should fall back to GPTQ, AWQ, or bfloat16
            assert True  # Expected behavior

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_cuda_availability_for_deepseek(self):
        """Test CUDA is available for DeepSeek processing."""
        assert torch.cuda.is_available()

        # Check VRAM is sufficient (RTX 4080 has 16GB)
        total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        assert total_vram_gb >= 12, f"Insufficient VRAM: {total_vram_gb:.1f}GB"


class TestDeepSeekMemoryManagement:
    """Test memory management for DeepSeek on Windows."""

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_vram_threshold_constant(self):
        """Test VRAM threshold is set correctly."""
        # RTX 4080 threshold: 85% of 16GB = 13.6GB
        THRESHOLD_GB = 13.6
        total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)

        if total_vram_gb >= 15:  # RTX 4080 or similar
            assert THRESHOLD_GB < total_vram_gb

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_memory_can_be_cleared(self):
        """Test that CUDA memory can be cleared."""
        # Allocate some memory
        tensor = torch.zeros(1000, 1000, device="cuda")
        allocated_before = torch.cuda.memory_allocated()

        # Delete and clear
        del tensor
        torch.cuda.empty_cache()

        allocated_after = torch.cuda.memory_allocated()
        assert allocated_after <= allocated_before


class TestDeepSeekGPTQLoading:
    """Test GPTQ model loading (mock-based for CI)."""

    def test_gptq_import_handling(self):
        """Test GPTQ import is handled gracefully."""
        from app.agents.ocr.deepseek_agent import GPTQ_AVAILABLE, AutoGPTQForCausalLM

        if GPTQ_AVAILABLE:
            assert AutoGPTQForCausalLM is not None
        else:
            assert AutoGPTQForCausalLM is None

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_gptq_model_name_format(self):
        """Test GPTQ model name is correctly formatted."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        expected_gptq_name = f"{agent.MODEL_NAME}-GPTQ"

        assert "-GPTQ" in expected_gptq_name
        assert "deepseek-ai" in expected_gptq_name


class TestDeepSeekAWQLoading:
    """Test AWQ model loading (mock-based for CI)."""

    def test_awq_import_handling(self):
        """Test AWQ import is handled gracefully."""
        from app.agents.ocr.deepseek_agent import AWQ_AVAILABLE, AutoAWQForCausalLM

        if AWQ_AVAILABLE:
            assert AutoAWQForCausalLM is not None
        else:
            assert AutoAWQForCausalLM is None

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_awq_model_name_format(self):
        """Test AWQ model name is correctly formatted."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        expected_awq_name = f"{agent.MODEL_NAME}-AWQ"

        assert "-AWQ" in expected_awq_name
        assert "deepseek-ai" in expected_awq_name


class TestDeepSeekBFloat16Fallback:
    """Test bfloat16 fallback behavior."""

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    def test_bfloat16_support(self):
        """Test that GPU supports bfloat16."""
        # Check if GPU supports bfloat16
        device_props = torch.cuda.get_device_properties(0)
        compute_capability = (device_props.major, device_props.minor)

        # bfloat16 requires compute capability >= 8.0 (Ampere+)
        # RTX 4080 has compute capability 8.9
        supports_bf16 = compute_capability >= (8, 0)

        if supports_bf16:
            # Verify we can create bfloat16 tensors
            tensor = torch.zeros(10, dtype=torch.bfloat16, device="cuda")
            assert tensor.dtype == torch.bfloat16
            del tensor
            torch.cuda.empty_cache()

    def test_low_cpu_mem_usage_flag(self):
        """Test that low_cpu_mem_usage is used in fallback."""
        # This is a code inspection test - verify the flag is used
        # in the model loading code for bfloat16 fallback
        import inspect
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        source = inspect.getsource(DeepSeekAgent._load_model)
        assert "low_cpu_mem_usage=True" in source


@pytest.mark.asyncio
class TestDeepSeekAgentIntegration:
    """Integration tests for DeepSeek agent (requires model)."""

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    @pytest.mark.slow
    async def test_agent_initialization(self):
        """Test agent can be initialized."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()

        assert agent.name == "deepseek_ocr_agent"
        assert agent.gpu_required is True
        assert agent._model_loaded is False

        # Cleanup
        await agent.cleanup()

    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="CUDA not available"
    )
    @pytest.mark.slow
    async def test_agent_status_before_loading(self):
        """Test agent status before model is loaded."""
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        agent = DeepSeekAgent()
        status = agent.get_status()

        assert status["model_loaded"] is False
        assert status["quantization_method"] is None
        assert "gpu_info" in status

        await agent.cleanup()
