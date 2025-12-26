# -*- coding: utf-8 -*-
"""
Property-Based Tests for PaddleOCR-VL Experimental Agent.

Feature: paddleocr-vl-evaluation
Tests correctness properties for PaddleOCR-VL experimental agent.
"""

import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from app.agents.ocr.paddle_ocr_vl_agent_experimental import (
    PaddleOCRVLAgentExperimental,
)


# =============================================================================
# Property 3: VRAM Threshold Warning
# =============================================================================

@settings(max_examples=100, deadline=10000)
@given(
    # Generate VRAM values in GB (0.0 to 20.0 GB range)
    vram_reserved_gb=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    vram_allocated_gb=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    total_vram_gb=st.floats(min_value=16.0, max_value=24.0, allow_nan=False, allow_infinity=False),
)
def test_vram_threshold_warning(
    vram_reserved_gb: float,
    vram_allocated_gb: float,
    total_vram_gb: float,
):
    """
    Feature: paddleocr-vl-evaluation, Property 3: VRAM Threshold Warning
    Validates: Requirements 3.3

    Property: For any VRAM measurement exceeding 14GB (14336MB), the Evaluation_System
    SHALL log a warning and set `exceeded_threshold=True` in the VRAMMetrics.

    This property tests that:
    1. When VRAM reserved > 14GB, exceeded_threshold is True
    2. When VRAM reserved <= 14GB, exceeded_threshold is False
    3. The threshold is consistently applied at 14.0 GB
    """
    # Mock torch.cuda to simulate VRAM measurements
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        # Setup mock CUDA availability
        mock_torch.cuda.is_available.return_value = True

        # Setup mock VRAM measurements (convert GB to bytes)
        mock_torch.cuda.memory_allocated.return_value = int(vram_allocated_gb * 1024**3)
        mock_torch.cuda.memory_reserved.return_value = int(vram_reserved_gb * 1024**3)

        # Setup mock device properties
        mock_device_props = Mock()
        mock_device_props.total_memory = int(total_vram_gb * 1024**3)
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        # Create agent instance
        agent = PaddleOCRVLAgentExperimental()

        # Get VRAM usage
        vram_metrics = agent.get_vram_usage()

        # Property assertions
        THRESHOLD_GB = 14.0

        # Check that exceeded_threshold is correctly set
        if vram_reserved_gb > THRESHOLD_GB:
            assert vram_metrics["exceeded_threshold"] is True, (
                f"Expected exceeded_threshold=True when VRAM reserved "
                f"({vram_reserved_gb:.2f} GB) > {THRESHOLD_GB} GB, "
                f"but got {vram_metrics['exceeded_threshold']}"
            )
        else:
            assert vram_metrics["exceeded_threshold"] is False, (
                f"Expected exceeded_threshold=False when VRAM reserved "
                f"({vram_reserved_gb:.2f} GB) <= {THRESHOLD_GB} GB, "
                f"but got {vram_metrics['exceeded_threshold']}"
            )

        # Verify metrics are correctly reported
        assert "reserved_gb" in vram_metrics
        assert "allocated_gb" in vram_metrics
        assert "total_gb" in vram_metrics
        assert "usage_percent" in vram_metrics

        # Verify values are within reasonable bounds
        assert vram_metrics["reserved_gb"] >= 0.0
        assert vram_metrics["allocated_gb"] >= 0.0
        assert vram_metrics["total_gb"] >= 0.0
        assert 0.0 <= vram_metrics["usage_percent"] <= 100.0


# =============================================================================
# Edge Cases for VRAM Threshold
# =============================================================================

def test_vram_threshold_exactly_14gb():
    """Test behavior when VRAM is exactly at the 14GB threshold."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True

        # Exactly 14GB reserved
        mock_torch.cuda.memory_allocated.return_value = int(10.0 * 1024**3)
        mock_torch.cuda.memory_reserved.return_value = int(14.0 * 1024**3)

        mock_device_props = Mock()
        mock_device_props.total_memory = int(16.0 * 1024**3)
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        agent = PaddleOCRVLAgentExperimental()
        vram_metrics = agent.get_vram_usage()

        # At exactly 14GB, should NOT exceed threshold (threshold is >14, not >=14)
        assert vram_metrics["exceeded_threshold"] is False, (
            "At exactly 14GB, exceeded_threshold should be False"
        )


def test_vram_threshold_just_above_14gb():
    """Test behavior when VRAM is just above the 14GB threshold."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True

        # Just above 14GB (14.01 GB)
        mock_torch.cuda.memory_allocated.return_value = int(10.0 * 1024**3)
        mock_torch.cuda.memory_reserved.return_value = int(14.01 * 1024**3)

        mock_device_props = Mock()
        mock_device_props.total_memory = int(16.0 * 1024**3)
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        agent = PaddleOCRVLAgentExperimental()
        vram_metrics = agent.get_vram_usage()

        # Just above 14GB should exceed threshold
        assert vram_metrics["exceeded_threshold"] is True, (
            "At 14.01GB, exceeded_threshold should be True"
        )


def test_vram_threshold_just_below_14gb():
    """Test behavior when VRAM is just below the 14GB threshold."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True

        # Just below 14GB (13.99 GB)
        mock_torch.cuda.memory_allocated.return_value = int(10.0 * 1024**3)
        mock_torch.cuda.memory_reserved.return_value = int(13.99 * 1024**3)

        mock_device_props = Mock()
        mock_device_props.total_memory = int(16.0 * 1024**3)
        mock_torch.cuda.get_device_properties.return_value = mock_device_props

        agent = PaddleOCRVLAgentExperimental()
        vram_metrics = agent.get_vram_usage()

        # Just below 14GB should NOT exceed threshold
        assert vram_metrics["exceeded_threshold"] is False, (
            "At 13.99GB, exceeded_threshold should be False"
        )


def test_vram_no_cuda_available():
    """Test behavior when CUDA is not available."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = False

        agent = PaddleOCRVLAgentExperimental()
        vram_metrics = agent.get_vram_usage()

        # Should return error state
        assert "error" in vram_metrics
        assert vram_metrics["exceeded_threshold"] is False
        assert vram_metrics["reserved_gb"] == 0.0


def test_vram_cuda_error():
    """Test behavior when CUDA operations raise an error."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.memory_allocated.side_effect = RuntimeError("CUDA error")

        agent = PaddleOCRVLAgentExperimental()
        vram_metrics = agent.get_vram_usage()

        # Should return error state
        assert "error" in vram_metrics
        assert vram_metrics["exceeded_threshold"] is False


# =============================================================================
# Integration Test: Experimental Flag
# =============================================================================

def test_experimental_flag_is_set():
    """Test that the experimental flag is properly set on the agent class."""
    # Check class attribute
    assert hasattr(PaddleOCRVLAgentExperimental, "experimental")
    assert PaddleOCRVLAgentExperimental.experimental is True

    # Check instance
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = False
        agent = PaddleOCRVLAgentExperimental()

        # Verify experimental flag in status
        status = agent.get_status()
        assert status["experimental"] is True


def test_agent_initialization_without_gpu():
    """Test that agent can be initialized without GPU."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = False

        agent = PaddleOCRVLAgentExperimental()

        assert agent.name == "paddle_ocr_vl_agent_experimental"
        assert agent.gpu_required is False  # Should be False when CUDA not available
        assert agent.vram_gb == 0  # Should be 0 when CUDA not available


def test_agent_initialization_with_gpu():
    """Test that agent can be initialized with GPU."""
    with patch("app.agents.ocr.paddle_ocr_vl_agent_experimental.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = True

        agent = PaddleOCRVLAgentExperimental()

        assert agent.name == "paddle_ocr_vl_agent_experimental"
        assert agent.gpu_required is True  # Should be True when CUDA available
        assert agent.vram_gb == 10.0  # Should be VRAM_REQUIRED_GB when CUDA available
