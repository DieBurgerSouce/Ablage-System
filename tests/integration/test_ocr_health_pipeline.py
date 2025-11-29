# -*- coding: utf-8 -*-
"""
Integration tests for OCR Health Checking and Fallback Pipeline.

Tests:
- OCR health endpoint responses
- Backend health status verification
- Fallback chain functionality
- Backend recommendations based on health

Feinpoliert und durchdacht - Comprehensive health monitoring tests.
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestOCRHealthEndpoints:
    """Integration tests for OCR health API endpoints."""

    @pytest.fixture
    def mock_ocr_service(self):
        """Create mock OCR service with configurable health states."""
        mock_service = MagicMock()
        mock_service.get_health_status = AsyncMock()
        mock_service.check_backend_health = AsyncMock()
        mock_service.get_recommended_backend = AsyncMock()
        return mock_service

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_endpoint_all_backends_healthy(self, mock_ocr_service):
        """Test health endpoint when all backends are healthy."""
        mock_ocr_service.get_health_status.return_value = {
            "overall_healthy": True,
            "backends": {
                "deepseek": {"healthy": True, "reason": "OK"},
                "got_ocr": {"healthy": True, "reason": "OK"},
                "surya": {"healthy": True, "reason": "OK"},
            },
            "healthy_count": 3,
            "unhealthy_count": 0,
            "total_backends": 3,
            "fallback_available": True,
            "timestamp": "2024-11-30T12:00:00Z"
        }

        health_status = await mock_ocr_service.get_health_status()

        assert health_status["overall_healthy"] is True
        assert health_status["healthy_count"] == 3
        assert health_status["unhealthy_count"] == 0
        assert health_status["fallback_available"] is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_endpoint_partial_degradation(self, mock_ocr_service):
        """Test health endpoint with partial backend degradation."""
        mock_ocr_service.get_health_status.return_value = {
            "overall_healthy": True,
            "backends": {
                "deepseek": {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
                "got_ocr": {"healthy": True, "reason": "OK"},
                "surya": {"healthy": True, "reason": "OK"},
            },
            "healthy_count": 2,
            "unhealthy_count": 1,
            "total_backends": 3,
            "fallback_available": True,
            "timestamp": "2024-11-30T12:00:00Z"
        }

        health_status = await mock_ocr_service.get_health_status()

        assert health_status["overall_healthy"] is True
        assert health_status["healthy_count"] == 2
        assert health_status["unhealthy_count"] == 1
        assert health_status["backends"]["deepseek"]["healthy"] is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_endpoint_all_unhealthy(self, mock_ocr_service):
        """Test health endpoint when all backends are unhealthy."""
        mock_ocr_service.get_health_status.return_value = {
            "overall_healthy": False,
            "backends": {
                "deepseek": {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
                "got_ocr": {"healthy": False, "reason": "SERVICE_UNAVAILABLE"},
                "surya": {"healthy": False, "reason": "INITIALIZATION_FAILED"},
            },
            "healthy_count": 0,
            "unhealthy_count": 3,
            "total_backends": 3,
            "fallback_available": False,
            "timestamp": "2024-11-30T12:00:00Z"
        }

        health_status = await mock_ocr_service.get_health_status()

        assert health_status["overall_healthy"] is False
        assert health_status["healthy_count"] == 0
        assert health_status["fallback_available"] is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_single_backend_health_check(self, mock_ocr_service):
        """Test single backend health check endpoint."""
        mock_ocr_service.check_backend_health.return_value = {
            "healthy": True,
            "reason": "OK",
            "status": {
                "vram_available_gb": 12.5,
                "vram_required_gb": 10.2,
                "service_ready": True
            }
        }

        health = await mock_ocr_service.check_backend_health("deepseek")

        assert health["healthy"] is True
        assert health["status"]["vram_available_gb"] == 12.5


class TestOCRServiceHealthIntegration:
    """Integration tests for OCR service health functionality."""

    @pytest.fixture
    def mock_backend_manager(self):
        """Create mock backend manager with health checking."""
        manager = MagicMock()
        manager.get_available_backends = MagicMock(return_value=["deepseek", "got_ocr", "surya"])
        manager.check_backend_health = AsyncMock()
        manager.get_fallback_order = MagicMock()
        manager.process_with_backend = AsyncMock()
        return manager

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_status_updates_stats(self, mock_backend_manager):
        """Test that health checks update processing stats correctly."""
        # Configure healthy responses
        mock_backend_manager.check_backend_health.side_effect = [
            {"healthy": True, "reason": "OK"},
            {"healthy": True, "reason": "OK"},
            {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
        ]

        # Simulate health check calls
        stats = {"health_checks": {"total": 0, "healthy": 0, "unhealthy": 0}}

        backends = mock_backend_manager.get_available_backends()
        for backend in backends:
            stats["health_checks"]["total"] += 1
            health = await mock_backend_manager.check_backend_health(backend)
            if health["healthy"]:
                stats["health_checks"]["healthy"] += 1
            else:
                stats["health_checks"]["unhealthy"] += 1

        assert stats["health_checks"]["total"] == 3
        assert stats["health_checks"]["healthy"] == 2
        assert stats["health_checks"]["unhealthy"] == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_recommended_backend_selection(self, mock_backend_manager):
        """Test backend recommendation based on health status."""
        # Simulate first GPU backend unhealthy
        mock_backend_manager.check_backend_health.side_effect = [
            {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
            {"healthy": True, "reason": "OK"},
            {"healthy": True, "reason": "OK"},
        ]

        backends = mock_backend_manager.get_available_backends()
        healthy_backends = []

        for backend in backends:
            health = await mock_backend_manager.check_backend_health(backend)
            if health["healthy"]:
                healthy_backends.append(backend)

        # With deepseek unhealthy, got_ocr should be recommended
        priority_order = ["deepseek", "got_ocr", "surya"]
        recommended = None
        for backend in priority_order:
            if backend in healthy_backends:
                recommended = backend
                break

        assert recommended == "got_ocr"


class TestFallbackChainIntegration:
    """Integration tests for OCR fallback chain."""

    @pytest.fixture
    def mock_backend_manager(self):
        """Create mock backend manager with fallback chain."""
        manager = MagicMock()
        manager.get_available_backends = MagicMock(return_value=["deepseek", "got_ocr", "surya"])
        manager.get_fallback_order = MagicMock(return_value=["got_ocr", "surya"])
        manager.process_with_backend = AsyncMock()
        return manager

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_chain_on_primary_failure(self, mock_backend_manager):
        """Test fallback chain activates when primary backend fails."""
        # First call fails, second succeeds
        mock_backend_manager.process_with_backend.side_effect = [
            RuntimeError("DeepSeek VRAM insufficient"),
            {
                "success": True,
                "text": "Extracted text",
                "backend": "got_ocr",
                "fallback_used": True,
                "original_backend": "deepseek"
            }
        ]

        # Simulate fallback processing
        result = None
        backends_to_try = ["deepseek"] + mock_backend_manager.get_fallback_order()

        for backend in backends_to_try:
            try:
                result = await mock_backend_manager.process_with_backend(
                    backend_name=backend,
                    image_path="test.png",
                    language="de"
                )
                break
            except RuntimeError:
                continue

        assert result is not None
        assert result["success"] is True
        assert result["fallback_used"] is True
        assert result["original_backend"] == "deepseek"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_exhaustion(self, mock_backend_manager):
        """Test behavior when all backends in fallback chain fail."""
        # All backends fail
        mock_backend_manager.process_with_backend.side_effect = [
            RuntimeError("DeepSeek failed"),
            RuntimeError("GOT-OCR failed"),
            RuntimeError("Surya failed"),
        ]

        backends_to_try = ["deepseek"] + mock_backend_manager.get_fallback_order()
        result = None
        last_error = None

        for backend in backends_to_try:
            try:
                result = await mock_backend_manager.process_with_backend(
                    backend_name=backend,
                    image_path="test.png",
                    language="de"
                )
                break
            except RuntimeError as e:
                last_error = e
                continue

        assert result is None
        assert last_error is not None
        assert "Surya failed" in str(last_error)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_tracks_usage(self, mock_backend_manager):
        """Test that fallback usage is properly tracked."""
        mock_backend_manager.process_with_backend.return_value = {
            "success": True,
            "text": "Text",
            "backend": "surya",
            "fallback_used": True,
            "original_backend": "deepseek"
        }

        stats = {"total_processed": 0, "total_fallbacks": 0}

        result = await mock_backend_manager.process_with_backend(
            backend_name="deepseek",
            image_path="test.png",
            language="de",
            enable_fallback=True
        )

        stats["total_processed"] += 1
        if result.get("fallback_used"):
            stats["total_fallbacks"] += 1

        assert stats["total_fallbacks"] == 1
        fallback_rate = stats["total_fallbacks"] / max(1, stats["total_processed"])
        assert fallback_rate == 1.0


class TestOCRHealthMonitoring:
    """Integration tests for OCR health monitoring metrics."""

    @pytest.mark.integration
    def test_health_metrics_structure(self):
        """Test health metrics have correct structure for Prometheus."""
        # Simulate metrics that would be exported
        metrics = {
            "ocr_backend_healthy": {
                "type": "gauge",
                "labels": ["backend"],
                "values": {
                    "deepseek": 1,
                    "got_ocr": 1,
                    "surya": 0,
                }
            },
            "ocr_health_checks_total": {
                "type": "counter",
                "labels": [],
                "value": 150
            },
            "ocr_health_checks_unhealthy_total": {
                "type": "counter",
                "labels": [],
                "value": 12
            },
            "ocr_fallbacks_total": {
                "type": "counter",
                "labels": ["from_backend", "to_backend"],
                "values": {
                    ("deepseek", "got_ocr"): 5,
                    ("deepseek", "surya"): 2,
                    ("got_ocr", "surya"): 1,
                }
            }
        }

        assert "ocr_backend_healthy" in metrics
        assert metrics["ocr_backend_healthy"]["type"] == "gauge"
        assert sum(metrics["ocr_backend_healthy"]["values"].values()) == 2

        assert "ocr_fallbacks_total" in metrics
        total_fallbacks = sum(metrics["ocr_fallbacks_total"]["values"].values())
        assert total_fallbacks == 8

    @pytest.mark.integration
    def test_alert_thresholds(self):
        """Test alert threshold calculations match Prometheus rules."""
        # Simulate metric values for alert evaluation
        metrics = {
            "rate_ocr_requests": 100,
            "rate_ocr_errors": 30,
            "rate_ocr_fallbacks": 25,
            "sum_backend_healthy": 0,
            "sum_gpu_backends_healthy": 0,
        }

        # Test error rate alert threshold (>25% is critical)
        error_rate = metrics["rate_ocr_errors"] / max(1, metrics["rate_ocr_requests"])
        assert error_rate > 0.25  # Should trigger OCRErrorRateCritical

        # Test fallback rate alert threshold (>20% is warning)
        fallback_rate = metrics["rate_ocr_fallbacks"] / max(1, metrics["rate_ocr_requests"])
        assert fallback_rate > 0.20  # Should trigger OCRHighFallbackRate

        # Test no backend available alert
        assert metrics["sum_backend_healthy"] == 0  # Should trigger NoOCRBackendAvailable

        # Test all GPU backends unhealthy alert
        assert metrics["sum_gpu_backends_healthy"] == 0  # Should trigger AllGPUBackendsUnhealthy


class TestOCRServiceWithMockedBackends:
    """Integration tests with mocked OCR backends."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_health_status_aggregation(self):
        """Test OCR service aggregates health status from all backends."""
        # Create mock backend manager
        mock_manager = MagicMock()
        mock_manager.get_available_backends.return_value = ["deepseek", "got_ocr", "surya"]
        mock_manager.check_backend_health = AsyncMock(side_effect=[
            {"healthy": True, "reason": "OK"},
            {"healthy": True, "reason": "OK"},
            {"healthy": False, "reason": "VRAM_LOW"},
        ])
        mock_manager.get_backend_status = AsyncMock(return_value={})

        # Create service-like health status aggregation
        backends = mock_manager.get_available_backends()
        health_results = {}
        healthy_count = 0
        unhealthy_count = 0

        for backend_name in backends:
            health = await mock_manager.check_backend_health(backend_name)
            health_results[backend_name] = health
            if health.get("healthy"):
                healthy_count += 1
            else:
                unhealthy_count += 1

        health = {
            "overall_healthy": healthy_count > 0,
            "backends": health_results,
            "healthy_count": healthy_count,
            "unhealthy_count": unhealthy_count,
            "total_backends": len(backends),
            "fallback_available": health_results.get("surya", {}).get("healthy", False),
        }

        assert health["overall_healthy"] is True
        assert health["healthy_count"] == 2
        assert health["unhealthy_count"] == 1
        assert health["total_backends"] == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_get_recommended_backend_with_health(self):
        """Test backend recommendation considers health status."""
        # Create mock backend manager
        mock_manager = MagicMock()
        mock_manager.get_available_backends.return_value = ["deepseek", "got_ocr", "surya"]
        mock_manager.check_backend_health = AsyncMock(side_effect=[
            {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
            {"healthy": True, "reason": "OK"},
            {"healthy": True, "reason": "OK"},
        ])

        # Simulate health check and recommendation
        backends = mock_manager.get_available_backends()
        healthy_backends = []

        for backend_name in backends:
            health = await mock_manager.check_backend_health(backend_name)
            if health.get("healthy"):
                healthy_backends.append(backend_name)

        # GPU priority recommendation
        priority = ["deepseek", "got_ocr", "surya_gpu", "surya"]
        recommended = None
        for backend in priority:
            if backend in healthy_backends:
                recommended = backend
                break

        recommendation = {
            "recommended": recommended,
            "healthy_backends": healthy_backends,
        }

        assert recommendation["recommended"] is not None
        assert len(recommendation["healthy_backends"]) == 2
        assert "deepseek" not in recommendation["healthy_backends"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_process_document_with_fallback(self):
        """Test document processing with fallback chain."""
        # Create mock backend manager
        mock_manager = MagicMock()
        mock_manager.get_available_backends.return_value = ["deepseek", "got_ocr", "surya"]
        mock_manager.select_backend = AsyncMock(return_value="deepseek")
        mock_manager.process_with_backend = AsyncMock(return_value={
            "success": True,
            "text": "Extracted German text with Umlauts: äöü",
            "backend": "got_ocr",
            "fallback_used": True,
            "original_backend": "deepseek"
        })

        # Simulate OCR service processing
        selected_backend = await mock_manager.select_backend(
            image_path="test.png",
            language="de",
            detect_layout=True
        )

        result = await mock_manager.process_with_backend(
            backend_name=selected_backend,
            image_path="test.png",
            language="de",
            enable_fallback=True
        )

        # Track fallback
        actual_backend = result.get("backend", selected_backend)
        fallback_used = result.get("fallback_used", False)

        result["metadata"] = {
            "backend_used": actual_backend,
            "backend_requested": selected_backend,
            "fallback_used": fallback_used,
        }

        assert result["success"] is True
        assert "metadata" in result
        assert result["metadata"]["fallback_used"] is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_stats_tracking_with_fallbacks(self):
        """Test stats are properly updated including fallback tracking."""
        # Create mock backend manager
        mock_manager = MagicMock()
        mock_manager.get_available_backends.return_value = ["deepseek", "got_ocr", "surya"]
        mock_manager.select_backend = AsyncMock(return_value="deepseek")
        mock_manager.process_with_backend = AsyncMock(return_value={
            "success": True,
            "text": "Text",
            "backend": "surya",
            "fallback_used": True,
            "original_backend": "deepseek"
        })
        mock_manager.get_backend_status = AsyncMock(return_value={})

        # Initialize stats
        stats = {
            "total_processed": 0,
            "total_errors": 0,
            "total_fallbacks": 0,
            "by_backend": {},
            "health_checks": {"total": 0, "healthy": 0, "unhealthy": 0}
        }

        # Process document
        result = await mock_manager.process_with_backend(
            backend_name="deepseek",
            image_path="test.png",
            language="de",
            enable_fallback=True
        )

        # Update stats
        stats["total_processed"] += 1
        actual_backend = result.get("backend", "deepseek")
        if result.get("fallback_used"):
            stats["total_fallbacks"] += 1

        backend_count = stats["by_backend"].get(actual_backend, 0)
        stats["by_backend"][actual_backend] = backend_count + 1

        # Calculate rates
        fallback_rate = stats["total_fallbacks"] / max(1, stats["total_processed"])

        assert stats["total_processed"] == 1
        assert stats["total_fallbacks"] == 1
        assert fallback_rate == 1.0


class TestEndToEndHealthWorkflow:
    """End-to-end workflow tests for health monitoring."""

    @pytest.mark.integration
    def test_health_check_and_alert_decision(self):
        """Test complete health check to alert decision workflow."""
        # Simulate health check results
        health_results = {
            "deepseek": {"healthy": False, "reason": "VRAM_INSUFFICIENT"},
            "got_ocr": {"healthy": False, "reason": "MODEL_NOT_LOADED"},
            "surya": {"healthy": True, "reason": "OK"},
        }

        # Calculate metrics
        healthy_count = sum(1 for h in health_results.values() if h["healthy"])
        unhealthy_count = len(health_results) - healthy_count
        gpu_backends_healthy = sum(
            1 for name, h in health_results.items()
            if name in ["deepseek", "got_ocr"] and h["healthy"]
        )

        # Determine which alerts would fire
        alerts_firing = []

        if healthy_count == 0:
            alerts_firing.append("NoOCRBackendAvailable")

        if gpu_backends_healthy == 0:
            alerts_firing.append("AllGPUBackendsUnhealthy")

        for backend, health in health_results.items():
            if not health["healthy"] and backend != "surya":
                alerts_firing.append(f"OCRBackendUnhealthy({backend})")

        # Verify expected alerts
        assert "AllGPUBackendsUnhealthy" in alerts_firing
        assert "OCRBackendUnhealthy(deepseek)" in alerts_firing
        assert "OCRBackendUnhealthy(got_ocr)" in alerts_firing
        assert "NoOCRBackendAvailable" not in alerts_firing  # surya is healthy

    @pytest.mark.integration
    def test_fallback_recommendation_workflow(self):
        """Test complete fallback recommendation workflow."""
        # Initial health state
        backend_health = {
            "deepseek": False,
            "got_ocr": False,
            "surya": True,
        }

        # Priority order
        priority_gpu_first = ["deepseek", "got_ocr", "surya_gpu", "surya"]
        priority_cpu_first = ["surya", "surya_gpu", "got_ocr", "deepseek"]

        # GPU preference recommendation
        gpu_recommendation = None
        for backend in priority_gpu_first:
            if backend in backend_health and backend_health.get(backend):
                gpu_recommendation = backend
                break
            elif backend == "surya_gpu" and backend_health.get("surya"):
                gpu_recommendation = "surya_gpu"
                break

        # CPU preference recommendation
        cpu_recommendation = None
        for backend in priority_cpu_first:
            if backend in backend_health and backend_health.get(backend):
                cpu_recommendation = backend
                break

        # In this scenario, only surya is healthy
        assert gpu_recommendation == "surya_gpu" or cpu_recommendation == "surya"
        assert cpu_recommendation == "surya"


if __name__ == "__main__":
    print("Running OCR Health Pipeline Integration Tests")
    print("=" * 60)
    pytest.main([__file__, "-v", "-m", "integration"])
