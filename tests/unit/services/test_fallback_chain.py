# -*- coding: utf-8 -*-
"""
Unit tests for OCR Fallback Chain Service.

Tests fallback chain functionality:
- Backend configuration and priority
- Confidence-based fallback triggering
- Error handling and timeout management
- GPU availability filtering
- Metrics collection
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.fallback_chain import (
    FallbackChain,
    FallbackResult,
    FallbackReason,
    BackendConfig,
    get_fallback_chain,
)


class TestFallbackReason:
    """Tests for FallbackReason enum."""

    def test_all_reasons_defined(self):
        """Test all fallback reasons are defined."""
        assert FallbackReason.LOW_CONFIDENCE.value == "low_confidence"
        assert FallbackReason.BACKEND_ERROR.value == "backend_error"
        assert FallbackReason.TIMEOUT.value == "timeout"
        assert FallbackReason.GPU_OOM.value == "gpu_oom"
        assert FallbackReason.MODEL_UNAVAILABLE.value == "model_unavailable"
        assert FallbackReason.CIRCUIT_OPEN.value == "circuit_open"
        assert FallbackReason.MANUAL.value == "manual"


class TestBackendConfig:
    """Tests for BackendConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = BackendConfig(
            name="test-backend",
            priority=1,
            requires_gpu=True,
            vram_gb=8.0
        )

        assert config.name == "test-backend"
        assert config.priority == 1
        assert config.requires_gpu is True
        assert config.vram_gb == 8.0
        assert config.min_confidence_threshold == 0.65
        assert config.timeout_seconds == 120.0
        assert config.enabled is True
        assert config.strengths == []

    def test_custom_values(self):
        """Test custom configuration values."""
        config = BackendConfig(
            name="custom-backend",
            priority=2,
            requires_gpu=False,
            vram_gb=0.0,
            min_confidence_threshold=0.80,
            timeout_seconds=60.0,
            enabled=False,
            strengths=["german", "tables"]
        )

        assert config.min_confidence_threshold == 0.80
        assert config.timeout_seconds == 60.0
        assert config.enabled is False
        assert "german" in config.strengths


class TestFallbackResult:
    """Tests for FallbackResult dataclass."""

    def test_success_result(self):
        """Test successful fallback result."""
        result = FallbackResult(
            success=True,
            text="Extracted text content",
            confidence=0.95,
            final_backend="deepseek-janus-pro",
            backends_tried=["deepseek-janus-pro"],
            fallbacks_occurred=0,
            fallback_reasons=[],
            total_time_ms=1500
        )

        assert result.success is True
        assert result.confidence == 0.95
        assert result.fallbacks_occurred == 0

    def test_fallback_result(self):
        """Test result with fallbacks."""
        result = FallbackResult(
            success=True,
            text="Extracted text content",
            confidence=0.72,
            final_backend="got-ocr-2.0",
            backends_tried=["deepseek-janus-pro", "got-ocr-2.0"],
            fallbacks_occurred=1,
            fallback_reasons=[{
                "backend": "deepseek-janus-pro",
                "reason": "low_confidence",
                "details": "Confidence unter Schwellenwert"
            }],
            total_time_ms=3500
        )

        assert result.success is True
        assert result.fallbacks_occurred == 1
        assert len(result.backends_tried) == 2

    def test_failure_result(self):
        """Test failed fallback result."""
        result = FallbackResult(
            success=False,
            text="",
            confidence=0.0,
            final_backend="none",
            backends_tried=["deepseek-janus-pro", "got-ocr-2.0", "surya"],
            fallbacks_occurred=3,
            fallback_reasons=[
                {"backend": "deepseek-janus-pro", "reason": "backend_error"},
                {"backend": "got-ocr-2.0", "reason": "timeout"},
                {"backend": "surya", "reason": "backend_error"}
            ],
            total_time_ms=5000,
            error="Alle Backends fehlgeschlagen"
        )

        assert result.success is False
        assert result.error is not None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = FallbackResult(
            success=True,
            text="Test",
            confidence=0.85,
            final_backend="surya",
            backends_tried=["surya"],
            fallbacks_occurred=0,
            fallback_reasons=[],
            total_time_ms=500
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["success"] is True
        assert result_dict["confidence"] == 0.85
        assert result_dict["final_backend"] == "surya"


class TestFallbackChain:
    """Tests for FallbackChain class."""

    @pytest.fixture
    def mock_confidence_service(self):
        """Create mock confidence service."""
        service = Mock()
        service.analyze_ocr_result = Mock(return_value=Mock(
            confidence=0.85,
            to_dict=Mock(return_value={"confidence": 0.85})
        ))
        service.should_trigger_fallback = Mock(return_value=(False, None))
        return service

    @pytest.fixture
    def fallback_chain(self, mock_confidence_service):
        """Create fallback chain with mock dependencies."""
        return FallbackChain(
            confidence_service=mock_confidence_service,
            max_fallbacks=3
        )

    @pytest.fixture
    def custom_backends(self):
        """Create custom backend configurations."""
        return [
            BackendConfig(
                name="primary-backend",
                priority=1,
                requires_gpu=True,
                vram_gb=12.0
            ),
            BackendConfig(
                name="secondary-backend",
                priority=2,
                requires_gpu=True,
                vram_gb=8.0
            ),
            BackendConfig(
                name="cpu-fallback",
                priority=3,
                requires_gpu=False,
                vram_gb=0.0
            ),
        ]

    # =========================================================================
    # Initialization Tests
    # =========================================================================

    def test_initialization_default_backends(self, mock_confidence_service):
        """Test initialization with default backends."""
        chain = FallbackChain(confidence_service=mock_confidence_service)

        assert len(chain.backends) > 0
        assert chain.max_fallbacks == 3

    def test_initialization_custom_backends(self, custom_backends, mock_confidence_service):
        """Test initialization with custom backends."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        assert len(chain.backends) == 3
        assert chain.backends[0].name == "primary-backend"

    def test_backends_sorted_by_priority(self, mock_confidence_service):
        """Test backends are sorted by priority."""
        backends = [
            BackendConfig(name="low", priority=3, requires_gpu=False, vram_gb=0),
            BackendConfig(name="high", priority=1, requires_gpu=True, vram_gb=8),
            BackendConfig(name="medium", priority=2, requires_gpu=True, vram_gb=4),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        assert chain.backends[0].name == "high"
        assert chain.backends[1].name == "medium"
        assert chain.backends[2].name == "low"

    # =========================================================================
    # Backend Handler Registration
    # =========================================================================

    def test_register_backend_handler(self, fallback_chain):
        """Test backend handler registration."""
        async def mock_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.9}

        fallback_chain.register_backend_handler("test-backend", mock_handler)

        assert "test-backend" in fallback_chain._backend_handlers

    # =========================================================================
    # Enabled Backends Filtering
    # =========================================================================

    def test_get_enabled_backends_all_gpu(self, custom_backends, mock_confidence_service):
        """Test getting enabled backends when GPU available."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        enabled = chain.get_enabled_backends(gpu_available=True, available_vram_gb=16.0)

        assert len(enabled) == 3

    def test_get_enabled_backends_no_gpu(self, custom_backends, mock_confidence_service):
        """Test getting enabled backends when GPU not available."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        enabled = chain.get_enabled_backends(gpu_available=False, available_vram_gb=0.0)

        assert len(enabled) == 1
        assert enabled[0].name == "cpu-fallback"

    def test_get_enabled_backends_limited_vram(self, custom_backends, mock_confidence_service):
        """Test getting enabled backends with limited VRAM."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        enabled = chain.get_enabled_backends(gpu_available=True, available_vram_gb=10.0)

        # Should exclude primary-backend (12GB) but include secondary (8GB) and CPU
        assert len(enabled) == 2
        assert all(b.vram_gb <= 10.0 for b in enabled)

    def test_get_enabled_backends_disabled_excluded(self, mock_confidence_service):
        """Test disabled backends are excluded."""
        backends = [
            BackendConfig(name="enabled", priority=1, requires_gpu=False, vram_gb=0, enabled=True),
            BackendConfig(name="disabled", priority=2, requires_gpu=False, vram_gb=0, enabled=False),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        enabled = chain.get_enabled_backends()

        assert len(enabled) == 1
        assert enabled[0].name == "enabled"

    # =========================================================================
    # Execute Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_execute_success_first_backend(self, fallback_chain, mock_confidence_service):
        """Test successful execution on first backend."""
        async def mock_handler(**kwargs):
            return {
                "success": True,
                "text": "Extracted text",
                "confidence": 0.92,
                "confidence_details": {}
            }

        # Register handler for first backend
        first_backend = fallback_chain.backends[0].name
        fallback_chain.register_backend_handler(first_backend, mock_handler)

        result = await fallback_chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png",
            language="de"
        )

        assert result.success is True
        assert result.final_backend == first_backend
        assert result.fallbacks_occurred == 0

    @pytest.mark.asyncio
    async def test_execute_fallback_on_low_confidence(self, mock_confidence_service):
        """Test fallback triggered by low confidence."""
        # Configure confidence service to trigger fallback on first backend
        call_count = 0

        def mock_should_fallback(metrics, document_type=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (True, "Confidence zu niedrig")
            return (False, None)

        mock_confidence_service.should_trigger_fallback = mock_should_fallback

        backends = [
            BackendConfig(name="first", priority=1, requires_gpu=False, vram_gb=0),
            BackendConfig(name="second", priority=2, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service,
            max_fallbacks=3
        )

        async def mock_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.65}

        chain.register_backend_handler("first", mock_handler)
        chain.register_backend_handler("second", mock_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        assert result.success is True
        assert result.fallbacks_occurred == 1
        assert len(result.backends_tried) == 2

    @pytest.mark.asyncio
    async def test_execute_fallback_on_backend_error(self, mock_confidence_service):
        """Test fallback triggered by backend error."""
        backends = [
            BackendConfig(name="failing", priority=1, requires_gpu=False, vram_gb=0),
            BackendConfig(name="working", priority=2, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service,
            max_fallbacks=3
        )

        async def failing_handler(**kwargs):
            raise Exception("Backend fehlgeschlagen")

        async def working_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.85}

        chain.register_backend_handler("failing", failing_handler)
        chain.register_backend_handler("working", working_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        assert result.success is True
        assert result.final_backend == "working"
        assert result.fallbacks_occurred == 1
        assert any(r["reason"] == "backend_error" for r in result.fallback_reasons)

    @pytest.mark.asyncio
    async def test_execute_fallback_on_timeout(self, mock_confidence_service):
        """Test fallback triggered by timeout."""
        backends = [
            BackendConfig(name="slow", priority=1, requires_gpu=False, vram_gb=0, timeout_seconds=0.1),
            BackendConfig(name="fast", priority=2, requires_gpu=False, vram_gb=0, timeout_seconds=10.0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service,
            max_fallbacks=3
        )

        async def slow_handler(**kwargs):
            await asyncio.sleep(10)  # Will timeout
            return {"success": True, "text": "Slow", "confidence": 0.9}

        async def fast_handler(**kwargs):
            return {"success": True, "text": "Fast", "confidence": 0.85}

        chain.register_backend_handler("slow", slow_handler)
        chain.register_backend_handler("fast", fast_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        assert result.success is True
        assert result.final_backend == "fast"
        assert any(r["reason"] == "timeout" for r in result.fallback_reasons)

    @pytest.mark.asyncio
    async def test_execute_no_backends_available(self, mock_confidence_service):
        """Test execution when no backends available."""
        backends = [
            BackendConfig(name="gpu-only", priority=1, requires_gpu=True, vram_gb=16.0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png",
            gpu_available=False  # No GPU
        )

        assert result.success is False
        assert result.error == "Keine Backends verfügbar"

    @pytest.mark.asyncio
    async def test_execute_all_backends_fail(self, mock_confidence_service):
        """Test execution when all backends fail."""
        backends = [
            BackendConfig(name="backend1", priority=1, requires_gpu=False, vram_gb=0),
            BackendConfig(name="backend2", priority=2, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service,
            max_fallbacks=3
        )

        async def failing_handler(**kwargs):
            raise Exception("Fehler")

        chain.register_backend_handler("backend1", failing_handler)
        chain.register_backend_handler("backend2", failing_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        assert result.success is False
        assert len(result.backends_tried) == 2

    @pytest.mark.asyncio
    async def test_execute_with_preferred_backend(self, mock_confidence_service):
        """Test execution with preferred backend."""
        backends = [
            BackendConfig(name="default", priority=1, requires_gpu=False, vram_gb=0),
            BackendConfig(name="preferred", priority=2, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        async def mock_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.9}

        chain.register_backend_handler("default", mock_handler)
        chain.register_backend_handler("preferred", mock_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png",
            preferred_backend="preferred"
        )

        # Should try preferred first
        assert result.backends_tried[0] == "preferred"

    @pytest.mark.asyncio
    async def test_execute_max_fallbacks_limit(self, mock_confidence_service):
        """Test max fallbacks limit is respected."""
        mock_confidence_service.should_trigger_fallback = Mock(return_value=(True, "Always fallback"))

        backends = [
            BackendConfig(name="b1", priority=1, requires_gpu=False, vram_gb=0),
            BackendConfig(name="b2", priority=2, requires_gpu=False, vram_gb=0),
            BackendConfig(name="b3", priority=3, requires_gpu=False, vram_gb=0),
            BackendConfig(name="b4", priority=4, requires_gpu=False, vram_gb=0),
            BackendConfig(name="b5", priority=5, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service,
            max_fallbacks=2  # Allow only 2 fallbacks (3 total attempts)
        )

        async def mock_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.5}

        for backend in backends:
            chain.register_backend_handler(backend.name, mock_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        # Should only try max_fallbacks + 1 backends
        assert len(result.backends_tried) <= 3

    @pytest.mark.asyncio
    async def test_execute_gpu_oom_detection(self, mock_confidence_service):
        """Test GPU OOM error is detected correctly."""
        backends = [
            BackendConfig(name="oom-backend", priority=1, requires_gpu=True, vram_gb=8),
            BackendConfig(name="cpu-backend", priority=2, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        async def oom_handler(**kwargs):
            # Use "OOM" in message to trigger gpu_oom detection
            raise RuntimeError("GPU OOM: CUDA out of memory")

        async def cpu_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.8}

        chain.register_backend_handler("oom-backend", oom_handler)
        chain.register_backend_handler("cpu-backend", cpu_handler)

        result = await chain.execute(
            document_id="doc-123",
            image_path="/path/to/image.png"
        )

        assert result.success is True
        assert any(r["reason"] == "gpu_oom" for r in result.fallback_reasons)

    # =========================================================================
    # Metrics Tests
    # =========================================================================

    def test_get_metrics(self, fallback_chain):
        """Test metrics collection."""
        metrics = fallback_chain.get_metrics()

        assert "backends" in metrics
        assert "total_fallbacks" in metrics
        assert "total_calls" in metrics

    @pytest.mark.asyncio
    async def test_metrics_updated_after_execute(self, mock_confidence_service):
        """Test metrics are updated after execution."""
        backends = [
            BackendConfig(name="test-backend", priority=1, requires_gpu=False, vram_gb=0),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence_service
        )

        async def mock_handler(**kwargs):
            return {"success": True, "text": "Test", "confidence": 0.9}

        chain.register_backend_handler("test-backend", mock_handler)

        # Execute multiple times
        for _ in range(5):
            await chain.execute(
                document_id="doc-123",
                image_path="/path/to/image.png"
            )

        metrics = chain.get_metrics()

        assert metrics["backends"]["test-backend"]["total_calls"] == 5
        assert metrics["backends"]["test-backend"]["successes"] == 5

    # =========================================================================
    # Backend Reordering Tests
    # =========================================================================

    def test_reorder_by_preference_found(self, custom_backends, mock_confidence_service):
        """Test reordering when preferred backend exists."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        reordered = chain._reorder_by_preference(
            custom_backends,
            "cpu-fallback"
        )

        assert reordered[0].name == "cpu-fallback"

    def test_reorder_by_preference_not_found(self, custom_backends, mock_confidence_service):
        """Test reordering when preferred backend not found."""
        chain = FallbackChain(
            backends=custom_backends,
            confidence_service=mock_confidence_service
        )

        reordered = chain._reorder_by_preference(
            custom_backends,
            "nonexistent-backend"
        )

        # Order should be unchanged
        assert reordered[0].name == custom_backends[0].name


class TestFallbackChainSingleton:
    """Tests for singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Test get_fallback_chain returns singleton."""
        # Reset singleton for test
        import app.services.fallback_chain as chain_module
        chain_module._fallback_chain = None

        chain1 = get_fallback_chain()
        chain2 = get_fallback_chain()

        assert chain1 is chain2

        # Reset singleton after test
        chain_module._fallback_chain = None


class TestFallbackChainIntegration:
    """Integration-style tests for FallbackChain."""

    @pytest.mark.asyncio
    async def test_realistic_ocr_workflow(self):
        """Test realistic OCR workflow with fallbacks."""
        # Mock confidence service with realistic behavior
        mock_confidence = Mock()
        mock_confidence.analyze_ocr_result = Mock(return_value=Mock(
            confidence=0.85,
            to_dict=Mock(return_value={"confidence": 0.85})
        ))

        # First backend has low confidence, second succeeds
        confidence_calls = [0]

        def mock_should_fallback(metrics, document_type=None):
            confidence_calls[0] += 1
            if confidence_calls[0] == 1:
                return (True, "DeepSeek confidence zu niedrig für Tabellen")
            return (False, None)

        mock_confidence.should_trigger_fallback = mock_should_fallback

        backends = [
            BackendConfig(
                name="deepseek-janus-pro",
                priority=1,
                requires_gpu=True,
                vram_gb=12.0,
                strengths=["handwriting", "fraktur"]
            ),
            BackendConfig(
                name="got-ocr-2.0",
                priority=2,
                requires_gpu=True,
                vram_gb=10.0,
                strengths=["tables", "formulas"]
            ),
        ]

        chain = FallbackChain(
            backends=backends,
            confidence_service=mock_confidence
        )

        async def deepseek_handler(**kwargs):
            return {
                "success": True,
                "text": "Tabelle nicht gut erkannt",
                "confidence": 0.55
            }

        async def got_handler(**kwargs):
            return {
                "success": True,
                "text": "Tabelle korrekt extrahiert\n| A | B |\n| 1 | 2 |",
                "confidence": 0.92
            }

        chain.register_backend_handler("deepseek-janus-pro", deepseek_handler)
        chain.register_backend_handler("got-ocr-2.0", got_handler)

        result = await chain.execute(
            document_id="invoice-456",
            image_path="/documents/invoice.png",
            language="de",
            document_type="invoice"
        )

        assert result.success is True
        assert result.final_backend == "got-ocr-2.0"
        assert result.fallbacks_occurred == 1
        assert "Tabelle" in result.text
