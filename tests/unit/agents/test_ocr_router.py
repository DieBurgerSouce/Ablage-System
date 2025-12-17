# -*- coding: utf-8 -*-
"""
Unit tests for OCR Backend Router.

Tests:
- Backend capabilities configuration
- Rule-based routing
- ML-based routing (mocked)
- Resource status handling
- Load balancing
- Training feedback collection
- Backend recommendations
- Statistics tracking
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestBackendCapabilities:
    """Test BACKEND_CAPABILITIES configuration."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_all_backends_have_capabilities(self, router):
        """Test that all expected backends have capabilities defined."""
        expected_backends = ["deepseek", "got_ocr", "surya", "surya_gpu", "hybrid"]

        for backend in expected_backends:
            assert backend in router.BACKEND_CAPABILITIES

    @pytest.mark.unit
    def test_deepseek_capabilities(self, router):
        """Test DeepSeek backend capabilities."""
        caps = router.BACKEND_CAPABILITIES["deepseek"]

        assert caps["vram_gb"] == 12
        assert caps["accuracy_score"] == 0.96
        assert "complex_layouts" in caps["best_for"]
        assert "fraktur" in caps["best_for"]
        assert caps["german_label"] == "DeepSeek-Janus-Pro"

    @pytest.mark.unit
    def test_got_ocr_capabilities(self, router):
        """Test GOT-OCR capabilities."""
        caps = router.BACKEND_CAPABILITIES["got_ocr"]

        assert caps["vram_gb"] == 10
        assert caps["avg_speed_pages_per_sec"] == 6.0
        assert "high_throughput" in caps["best_for"]

    @pytest.mark.unit
    def test_surya_is_cpu_only(self, router):
        """Test Surya is CPU-only backend."""
        caps = router.BACKEND_CAPABILITIES["surya"]

        assert caps["vram_gb"] == 0
        assert "cpu_only" in caps["best_for"]

    @pytest.mark.unit
    def test_hybrid_has_highest_accuracy(self, router):
        """Test Hybrid mode has highest accuracy."""
        caps = router.BACKEND_CAPABILITIES["hybrid"]

        assert caps["accuracy_score"] == 0.98
        # Should be slowest (runs multiple backends)
        assert caps["avg_speed_pages_per_sec"] < 1.0


class TestRouterInitialization:
    """Test router initialization."""

    @pytest.mark.unit
    def test_router_init_without_ml(self):
        """Test router initializes without ML routing."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter

            router = OCRBackendRouter(use_ml_routing=False)

            assert router.use_ml_routing == False
            assert router._ml_model is None
            assert router._ml_trainer is None

    @pytest.mark.unit
    def test_router_init_with_ml(self):
        """Test router initializes with ML routing."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'), \
             patch('app.agents.orchestration.ml_router_model.OCRRouterModel') as mock_model, \
             patch('app.agents.orchestration.ml_trainer.MLRouterTrainer') as mock_trainer:

            mock_model.return_value.is_trained = True
            mock_trainer.return_value.model = mock_model.return_value

            from app.agents.orchestration.ocr_router import OCRBackendRouter

            router = OCRBackendRouter(use_ml_routing=True)

            assert router.use_ml_routing == True

    @pytest.mark.unit
    def test_router_stats_initialized(self):
        """Test routing statistics are initialized."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter

            router = OCRBackendRouter(use_ml_routing=False)

            assert router._routing_stats["total_requests"] == 0
            assert router._routing_stats["ml_predictions"] == 0
            assert router._routing_stats["rule_fallbacks"] == 0
            assert "backend_selections" in router._routing_stats


class TestRuleBasedRouting:
    """Test rule-based routing decisions."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_document_with_tables(self, router):
        """Test routing for document with tables."""
        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            result = await router._rule_based_selection(
                metadata={"has_tables": True},
                sla={},
                preferences={},
            )

            assert result["backend"] == "deepseek"
            # Reason kann _with_learning Suffix haben wenn Learning aktiviert
            assert "complex_layout_with_tables" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_document_with_handwriting(self, router):
        """Test routing for document with handwriting."""
        result = await router._rule_based_selection(
            metadata={"has_handwriting": True},
            sla={},
            preferences={},
        )

        assert result["backend"] == "deepseek"
        # Reason kann _with_learning Suffix haben wenn Learning aktiviert
        assert "handwriting_detected" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_contract_document(self, router):
        """Test routing for contract document (critical)."""
        result = await router._rule_based_selection(
            metadata={"document_type": "contract"},
            sla={},
            preferences={},
        )

        assert result["backend"] == "hybrid"
        assert "critical" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_high_complexity(self, router):
        """Test routing for high complexity document."""
        result = await router._rule_based_selection(
            metadata={"complexity": "high"},
            sla={},
            preferences={},
        )

        assert result["backend"] == "deepseek"
        assert "complexity" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_low_quality(self, router):
        """Test routing for low quality document."""
        result = await router._rule_based_selection(
            metadata={"quality_score": 0.5},
            sla={},
            preferences={},
        )

        assert result["backend"] == "deepseek"
        assert "quality" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_gpu_unavailable(self, router):
        """Test routing when GPU is unavailable."""
        with patch.object(router.gpu_manager, 'check_availability') as mock_check:
            mock_check.return_value = {"available": False}

            result = await router._rule_based_selection(
                metadata={},
                sla={},
                preferences={},
            )

            assert result["backend"] == "surya"
            assert "gpu_unavailable" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_fast_sla(self, router):
        """Test routing with fast SLA requirement."""
        result = await router._rule_based_selection(
            metadata={},
            sla={"max_processing_time_seconds": 5},
            preferences={},
        )

        assert result["backend"] == "got_ocr"
        assert "fast" in result["reason"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_user_preference(self, router):
        """Test routing respects user preference."""
        result = await router._rule_based_selection(
            metadata={},
            sla={},
            preferences={"preferred_backend": "surya"},
        )

        assert result["backend"] == "surya"
        assert result["reason"] == "user_preference"
        assert result["confidence"] == 1.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_standard_document(self, router):
        """Test routing for standard document."""
        result = await router._rule_based_selection(
            metadata={},
            sla={},
            preferences={},
        )

        assert result["backend"] == "got_ocr"
        # Reason kann _with_learning Suffix haben wenn Learning aktiviert
        assert "standard_document" in result["reason"]


class TestLoadBalancing:
    """Test load balancing functionality."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_critical_queue_fallback(self, router):
        """Test critical queue triggers CPU fallback."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.LOAD_BALANCING_ENABLED = True
            mock_settings.QUEUE_LENGTH_THRESHOLD_CRITICAL = 100
            mock_settings.QUEUE_LENGTH_THRESHOLD_HIGH = 50

            resource_status = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 150,
                "queue_lengths": {"ocr_high": 100, "ocr_normal": 50},
            }

            result = await router._check_load_balancing(
                resource_status, {}, {}, {}
            )

            assert result is not None
            assert result["backend"] == "surya"
            assert result["load_balanced"] == True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_high_queue_fast_backend(self, router):
        """Test high queue uses faster backend."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.LOAD_BALANCING_ENABLED = True
            mock_settings.QUEUE_LENGTH_THRESHOLD_CRITICAL = 100
            mock_settings.QUEUE_LENGTH_THRESHOLD_HIGH = 50

            resource_status = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 60,
                "queue_lengths": {"ocr_high": 35, "ocr_normal": 25},
            }

            result = await router._check_load_balancing(
                resource_status, {}, {}, {}
            )

            assert result is not None
            assert result["backend"] == "got_ocr"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_balancing_disabled(self, router):
        """Test load balancing can be disabled."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.LOAD_BALANCING_ENABLED = False

            resource_status = {
                "queue_length": 150,
                "queue_lengths": {},
            }

            result = await router._check_load_balancing(
                resource_status, {}, {}, {}
            )

            assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_preference_overrides_load_balancing(self, router):
        """Test user preference overrides load balancing."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.LOAD_BALANCING_ENABLED = True
            mock_settings.QUEUE_LENGTH_THRESHOLD_CRITICAL = 100

            resource_status = {
                "queue_length": 150,
                "queue_lengths": {},
            }

            preferences = {"preferred_backend": "deepseek"}

            result = await router._check_load_balancing(
                resource_status, {}, {}, preferences
            )

            # User preference should skip load balancing
            assert result is None


class TestProcessMethod:
    """Test the process method."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_returns_valid_result(self, router):
        """Test process returns valid routing result."""
        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            input_data = {
                "document_metadata": {
                    "document_type": "invoice",
                    "has_tables": True,
                },
            }

            result = await router.process(input_data)

            assert "backend" in result
            assert "reason" in result
            assert "confidence" in result
            assert result["backend"] in router.BACKEND_CAPABILITIES

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_updates_stats(self, router):
        """Test process updates routing statistics."""
        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            initial_count = router._routing_stats["total_requests"]

            await router.process({"document_metadata": {}})

            assert router._routing_stats["total_requests"] == initial_count + 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_requires_document_metadata(self, router):
        """Test process requires document_metadata."""
        from app.agents.base import AgentProcessingError

        with pytest.raises((AgentProcessingError, KeyError, ValueError)):
            await router.process({})


class TestMLBasedRouting:
    """Test ML-based routing (mocked)."""

    @pytest.fixture
    def router_with_ml(self):
        """Create router with mocked ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager') as mock_gm, \
             patch('app.agents.orchestration.ml_router_model.OCRRouterModel') as mock_model, \
             patch('app.agents.orchestration.ml_trainer.MLRouterTrainer') as mock_trainer:

            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }

            mock_model_instance = MagicMock()
            mock_model_instance.is_trained = True
            mock_model_instance.predict.return_value = {
                "backend": "deepseek",
                "confidence": 0.92,
                "reason": "ML-Routing",
                "alternatives": [{"backend": "got_ocr"}],
            }

            mock_trainer.return_value.model = mock_model_instance

            from app.agents.orchestration.ocr_router import OCRBackendRouter

            router = OCRBackendRouter(use_ml_routing=True)
            router._ml_model = mock_model_instance

            return router

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ml_routing_used_when_available(self, router_with_ml):
        """Test ML routing is used when trained model available."""
        with patch.object(router_with_ml, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            result = await router_with_ml._ml_based_selection(
                metadata={"document_type": "invoice"},
                sla={},
                preferences={},
                resource_status=mock_status.return_value,
            )

            assert result["backend"] == "deepseek"
            assert result["routing_method"] == "ml"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ml_routing_gpu_fallback(self, router_with_ml):
        """Test ML routing falls back when GPU unavailable."""
        router_with_ml._ml_model.predict.return_value = {
            "backend": "deepseek",  # GPU backend
            "confidence": 0.92,
        }

        resource_status = {
            "gpu_available": False,
            "gpu_memory_available_gb": 0,
        }

        result = await router_with_ml._ml_based_selection(
            metadata={},
            sla={},
            preferences={},
            resource_status=resource_status,
        )

        # Should fallback to CPU backend
        assert result["backend"] == "surya"


class TestBackendInfo:
    """Test backend information methods."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_backend_info(self, router):
        """Test getting backend info."""
        info = router.get_backend_info("deepseek")

        assert info is not None
        assert info["german_label"] == "DeepSeek-Janus-Pro"
        assert info["vram_gb"] == 12

    @pytest.mark.unit
    def test_get_backend_info_invalid(self, router):
        """Test getting info for invalid backend."""
        info = router.get_backend_info("invalid_backend")

        assert info == {}

    @pytest.mark.unit
    def test_rank_backends_by_speed(self, router):
        """Test ranking backends by speed."""
        ranked = router.rank_backends_by_speed()

        # got_ocr should be fastest (6.0 pages/sec)
        assert ranked[0] == "got_ocr"
        # hybrid should be slowest (0.8 pages/sec)
        assert ranked[-1] == "hybrid"

    @pytest.mark.unit
    def test_rank_backends_by_accuracy(self, router):
        """Test ranking backends by accuracy."""
        ranked = router.rank_backends_by_accuracy()

        # hybrid should be most accurate (0.98)
        assert ranked[0] == "hybrid"
        # surya should be least accurate (0.88)
        assert ranked[-1] == "surya"


class TestBackendRecommendations:
    """Test backend recommendation system."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_recommendations_structure(self, router):
        """Test recommendations return structure."""
        result = router.get_backend_recommendations({"document_type": "invoice"})

        assert "recommendations" in result
        assert "best_backend" in result
        assert len(result["recommendations"]) > 0

    @pytest.mark.unit
    def test_recommendations_include_scores(self, router):
        """Test recommendations include scores."""
        result = router.get_backend_recommendations({"document_type": "invoice"})

        for backend, info in result["recommendations"].items():
            assert "score" in info
            assert "german_label" in info
            assert "description" in info
            assert 0 <= info["score"] <= 1

    @pytest.mark.unit
    def test_contract_recommends_hybrid(self, router):
        """Test contract documents recommend hybrid."""
        result = router.get_backend_recommendations({"document_type": "contract"})

        # Hybrid should have high score for contracts
        hybrid_score = result["recommendations"]["hybrid"]["score"]
        assert hybrid_score >= 0.5

    @pytest.mark.unit
    def test_handwriting_recommends_deepseek(self, router):
        """Test handwriting documents recommend deepseek."""
        result = router.get_backend_recommendations({"has_handwriting": True})

        deepseek_score = result["recommendations"]["deepseek"]["score"]
        # DeepSeek should have higher score for handwriting
        assert deepseek_score >= 0.5


class TestAvailableBackends:
    """Test getting available backends."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_all_backends(self, router):
        """Test getting all backends."""
        backends = router.get_available_backends()

        assert len(backends) == len(router.BACKEND_CAPABILITIES)

    @pytest.mark.unit
    def test_filter_gpu_backends(self, router):
        """Test filtering GPU backends."""
        backends = router.get_available_backends(gpu_required=True)

        for name, info in backends.items():
            assert info["requires_gpu"] == True

    @pytest.mark.unit
    def test_filter_cpu_backends(self, router):
        """Test filtering CPU backends."""
        backends = router.get_available_backends(gpu_required=False)

        for name, info in backends.items():
            assert info["requires_gpu"] == False


class TestRoutingStats:
    """Test routing statistics."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_routing_stats(self, router):
        """Test getting routing statistics."""
        stats = router.get_routing_stats()

        assert "total_requests" in stats
        assert "ml_predictions" in stats
        assert "rule_fallbacks" in stats
        assert "backend_selections" in stats

    @pytest.mark.unit
    def test_initial_stats_zero(self, router):
        """Test initial statistics are zero."""
        stats = router.get_routing_stats()

        assert stats["total_requests"] == 0
        assert stats["ml_predictions"] == 0
        assert stats["rule_fallbacks"] == 0


class TestMLRoutingAvailability:
    """Test ML routing availability."""

    @pytest.mark.unit
    def test_ml_not_available_when_disabled(self):
        """Test ML not available when disabled."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            router = OCRBackendRouter(use_ml_routing=False)

            assert router.is_ml_routing_available() == False

    @pytest.mark.unit
    def test_ml_not_available_without_trained_model(self):
        """Test ML not available without trained model."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'), \
             patch('app.agents.orchestration.ml_router_model.OCRRouterModel') as mock_model, \
             patch('app.agents.orchestration.ml_trainer.MLRouterTrainer') as mock_trainer:

            mock_model_instance = MagicMock()
            mock_model_instance.is_trained = False
            mock_trainer.return_value.model = mock_model_instance

            from app.agents.orchestration.ocr_router import OCRBackendRouter
            router = OCRBackendRouter(use_ml_routing=True)

            assert router.is_ml_routing_available() == False


class TestTrainingFeedback:
    """Test training feedback collection."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.ocr_router.GPUManager'):
            from app.agents.orchestration.ocr_router import OCRBackendRouter
            return OCRBackendRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_feedback_without_trainer_does_not_fail(self, router):
        """Test feedback collection without trainer doesn't fail."""
        # Should not raise
        router.collect_training_feedback(
            document_id="doc123",
            document_metadata={"document_type": "invoice"},
            selected_backend="deepseek",
            processing_result={"success": True, "confidence": 0.95},
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
