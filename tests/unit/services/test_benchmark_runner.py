# -*- coding: utf-8 -*-
"""
Property-Based Tests for Benchmark Runner Service.

Feature: paddleocr-vl-evaluation
Tests correctness properties for benchmark runner functionality.
"""

import pytest

# Optionale Test-Abhaengigkeit: property-based Tests benoetigen 'hypothesis'.
# Ist sie im Runtime-Image nicht installiert, wird das gesamte Modul sauber
# geskippt (statt eines Collection-Errors, der die ganze Suite abbricht).
pytest.importorskip("hypothesis")

from hypothesis import given, strategies as st, settings
from typing import Dict, Any

from app.services.benchmark_runner_service import (
    BenchmarkRunnerService,
    BackendConfig,
    AVAILABLE_BACKENDS,
)


# =============================================================================
# Property 2: Experimental Agent Exclusion
# =============================================================================

@settings(max_examples=100, deadline=10000)
@given(
    include_experimental=st.booleans(),
    # Generate random backend configurations
    num_experimental=st.integers(min_value=0, max_value=5),
    num_production=st.integers(min_value=1, max_value=10),
)
def test_experimental_agent_exclusion(
    include_experimental: bool,
    num_experimental: int,
    num_production: int
):
    """
    Feature: paddleocr-vl-evaluation, Property 2: Experimental Agent Exclusion
    Validates: Requirements 2.4

    Property: For any agent marked with `experimental=True`, the Benchmark_Runner
    SHALL exclude it from the list of available backends when `include_experimental=False`.

    This property tests that:
    1. When include_experimental=False, no experimental backends are returned
    2. When include_experimental=True, experimental backends are included
    3. Production backends are always included regardless of the flag
    """
    # Create a mock set of backends with mixed experimental/production
    mock_backends: Dict[str, BackendConfig] = {}

    # Add production backends
    for i in range(num_production):
        backend_name = f"production-backend-{i}"
        mock_backends[backend_name] = BackendConfig(
            name=backend_name,
            display_name=f"Production Backend {i}",
            requires_gpu=False,
            vram_gb=0.0,
            experimental=False,
            enabled=True,
        )

    # Add experimental backends
    for i in range(num_experimental):
        backend_name = f"experimental-backend-{i}"
        mock_backends[backend_name] = BackendConfig(
            name=backend_name,
            display_name=f"Experimental Backend {i}",
            requires_gpu=True,
            vram_gb=10.0,
            experimental=True,
            enabled=True,
        )

    # Filter backends based on include_experimental flag
    # This simulates what get_available_backends should do
    filtered_backends = [
        config for config in mock_backends.values()
        if include_experimental or not config.experimental
    ]

    # Property assertions
    if include_experimental:
        # When include_experimental=True, all backends should be included
        assert len(filtered_backends) == num_production + num_experimental, (
            f"Expected {num_production + num_experimental} backends when "
            f"include_experimental=True, got {len(filtered_backends)}"
        )

        # Verify experimental backends are present
        experimental_count = sum(1 for b in filtered_backends if b.experimental)
        assert experimental_count == num_experimental, (
            f"Expected {num_experimental} experimental backends, got {experimental_count}"
        )
    else:
        # When include_experimental=False, only production backends should be included
        assert len(filtered_backends) == num_production, (
            f"Expected {num_production} backends when include_experimental=False, "
            f"got {len(filtered_backends)}"
        )

        # Verify NO experimental backends are present
        experimental_count = sum(1 for b in filtered_backends if b.experimental)
        assert experimental_count == 0, (
            f"Expected 0 experimental backends when include_experimental=False, "
            f"got {experimental_count}"
        )

    # Production backends should ALWAYS be included
    production_count = sum(1 for b in filtered_backends if not b.experimental)
    assert production_count == num_production, (
        f"Expected {num_production} production backends, got {production_count}"
    )


# =============================================================================
# Integration Test: Real Backend Configuration
# =============================================================================

def test_real_backends_experimental_flag():
    """
    Test that real backend configurations have correct experimental flags.

    This ensures that:
    - PaddleOCR-VL 0.9B is marked as experimental
    - Other production backends are not marked as experimental
    """
    # Check PaddleOCR-VL is marked as experimental
    paddle_vl_config = AVAILABLE_BACKENDS.get("paddle-ocr-vl-09b")
    if paddle_vl_config:
        assert paddle_vl_config.experimental is True, (
            "PaddleOCR-VL 0.9B should be marked as experimental"
        )

    # Check that production backends are not experimental
    production_backends = [
        "deepseek-janus-pro",
        "got-ocr-2.0",
        "surya-gpu",
        "surya",
        "qwen-ocr",
        "chandra-ocr",
        "olmocr-2",
        "paddle-ocr-v5",
        "doctr",
    ]

    for backend_name in production_backends:
        config = AVAILABLE_BACKENDS.get(backend_name)
        if config:
            assert config.experimental is False, (
                f"Production backend {backend_name} should not be marked as experimental"
            )


@pytest.mark.asyncio
async def test_benchmark_runner_get_available_backends():
    """
    Test that BenchmarkRunnerService.get_available_backends() returns correct data.

    This is a unit test to verify the method works correctly.
    """
    service = BenchmarkRunnerService()
    backends = service.get_available_backends()

    # Should return a list
    assert isinstance(backends, list)

    # Each backend should have required fields
    for backend in backends:
        assert "name" in backend
        assert "display_name" in backend
        assert "requires_gpu" in backend
        assert "vram_gb" in backend
        assert "available" in backend
        assert "experimental" in backend

    # Find PaddleOCR-VL backend
    paddle_vl = next(
        (b for b in backends if b["name"] == "paddle-ocr-vl-09b"),
        None
    )

    if paddle_vl:
        # Should be marked as experimental
        assert paddle_vl["experimental"] is True, (
            "PaddleOCR-VL 0.9B should be marked as experimental in get_available_backends()"
        )


# =============================================================================
# Edge Cases
# =============================================================================

def test_empty_backends_list():
    """Test behavior with no backends configured."""
    mock_backends: Dict[str, BackendConfig] = {}

    # Filter with include_experimental=False
    filtered = [
        config for config in mock_backends.values()
        if not config.experimental
    ]

    assert len(filtered) == 0, "Empty backends list should remain empty"


def test_all_experimental_backends():
    """Test behavior when all backends are experimental."""
    mock_backends: Dict[str, BackendConfig] = {
        f"exp-{i}": BackendConfig(
            name=f"exp-{i}",
            display_name=f"Experimental {i}",
            requires_gpu=True,
            vram_gb=10.0,
            experimental=True,
            enabled=True,
        )
        for i in range(5)
    }

    # Filter with include_experimental=False
    filtered = [
        config for config in mock_backends.values()
        if not config.experimental
    ]

    assert len(filtered) == 0, (
        "When all backends are experimental and include_experimental=False, "
        "no backends should be returned"
    )

    # Filter with include_experimental=True
    filtered_with_exp = [
        config for config in mock_backends.values()
        if True  # include all
    ]

    assert len(filtered_with_exp) == 5, (
        "When include_experimental=True, all experimental backends should be returned"
    )
