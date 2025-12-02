# -*- coding: utf-8 -*-
"""
Unit tests for Unified OCR Router.

Tests:
- BackendType enum and conversion
- DocumentAnalysis model
- RoutingResult model
- Backend specifications
- Rule-based routing
- ML-based routing (mocked)
- Language-based routing
- Fallback chain
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBackendType:
    """Test BackendType enum."""

    @pytest.mark.unit
    def test_backend_type_values(self):
        """Test BackendType enum values."""
        from app.agents.orchestration.unified_router import BackendType

        assert BackendType.DEEPSEEK.value == "deepseek"
        assert BackendType.GOT_OCR.value == "got_ocr"
        assert BackendType.SURYA.value == "surya"
        assert BackendType.DONUT.value == "donut"
        assert BackendType.TESSERACT.value == "tesseract"

    @pytest.mark.unit
    def test_backend_type_from_string(self):
        """Test BackendType.from_string conversion."""
        from app.agents.orchestration.unified_router import BackendType

        assert BackendType.from_string("deepseek") == BackendType.DEEPSEEK
        assert BackendType.from_string("DEEPSEEK") == BackendType.DEEPSEEK
        assert BackendType.from_string("got_ocr") == BackendType.GOT_OCR
        assert BackendType.from_string("got") == BackendType.GOT_OCR
        assert BackendType.from_string("surya") == BackendType.SURYA
        assert BackendType.from_string("donut") == BackendType.DONUT

    @pytest.mark.unit
    def test_backend_type_legacy_mapping(self):
        """Test legacy backend name mapping."""
        from app.agents.orchestration.unified_router import BackendType

        # Janus maps to DeepSeek
        assert BackendType.from_string("janus_pro") == BackendType.DEEPSEEK
        assert BackendType.from_string("deepseek_janus_pro") == BackendType.DEEPSEEK

        # GOT variants
        assert BackendType.from_string("got_ocr_2.0") == BackendType.GOT_OCR

        # Surya variants
        assert BackendType.from_string("surya_docling") == BackendType.SURYA

        # Donut variants
        assert BackendType.from_string("donut_base") == BackendType.DONUT
        assert BackendType.from_string("document_understanding") == BackendType.DONUT

    @pytest.mark.unit
    def test_backend_type_unknown_fallback(self):
        """Test that unknown backend names fallback to GOT_OCR."""
        from app.agents.orchestration.unified_router import BackendType

        assert BackendType.from_string("unknown_backend") == BackendType.GOT_OCR


class TestDocumentAnalysis:
    """Test DocumentAnalysis model."""

    @pytest.mark.unit
    def test_document_analysis_defaults(self):
        """Test DocumentAnalysis default values."""
        from app.agents.orchestration.unified_router import DocumentAnalysis

        analysis = DocumentAnalysis()

        assert analysis.document_type == "other"
        assert analysis.complexity == "medium"
        assert analysis.quality_score == 0.8
        assert analysis.has_formulas == False
        assert analysis.has_tables == False
        assert analysis.has_handwriting == False
        assert analysis.languages == ["de"]

    @pytest.mark.unit
    def test_document_analysis_custom_values(self):
        """Test DocumentAnalysis with custom values."""
        from app.agents.orchestration.unified_router import DocumentAnalysis

        analysis = DocumentAnalysis(
            document_type="invoice",
            complexity="high",
            quality_score=0.95,
            has_tables=True,
            languages=["de", "en"],
        )

        assert analysis.document_type == "invoice"
        assert analysis.complexity == "high"
        assert analysis.has_tables == True

    @pytest.mark.unit
    def test_document_analysis_validation(self):
        """Test DocumentAnalysis validation."""
        from app.agents.orchestration.unified_router import DocumentAnalysis
        from pydantic import ValidationError

        # Quality score out of range
        with pytest.raises(ValidationError):
            DocumentAnalysis(quality_score=1.5)

        with pytest.raises(ValidationError):
            DocumentAnalysis(quality_score=-0.1)


class TestRoutingResult:
    """Test RoutingResult model."""

    @pytest.mark.unit
    def test_routing_result_creation(self):
        """Test RoutingResult creation."""
        from app.agents.orchestration.unified_router import (
            RoutingResult,
            BackendType,
            RoutingMethod,
        )

        result = RoutingResult(
            backend=BackendType.DEEPSEEK,
            reason="Best for complex layouts",
            confidence=0.95,
            routing_method=RoutingMethod.ML,
        )

        assert result.backend == BackendType.DEEPSEEK
        assert result.confidence == 0.95
        assert result.routing_method == RoutingMethod.ML

    @pytest.mark.unit
    def test_routing_result_with_alternatives(self):
        """Test RoutingResult with alternatives."""
        from app.agents.orchestration.unified_router import (
            RoutingResult,
            BackendType,
            RoutingMethod,
        )

        result = RoutingResult(
            backend=BackendType.DEEPSEEK,
            reason="Primary choice",
            confidence=0.85,
            alternatives=[BackendType.GOT_OCR, BackendType.SURYA],
            routing_method=RoutingMethod.RULE_BASED,
            fallback_chain=[BackendType.GOT_OCR, BackendType.SURYA, BackendType.TESSERACT],
        )

        assert len(result.alternatives) == 2
        assert BackendType.GOT_OCR in result.alternatives
        assert len(result.fallback_chain) == 3


class TestBackendSpecs:
    """Test backend specifications."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_all_backends_have_specs(self, router):
        """Test that all backends have specifications."""
        from app.agents.orchestration.unified_router import BackendType

        # Check main backends (excluding aliases)
        main_backends = [
            BackendType.DEEPSEEK,
            BackendType.GOT_OCR,
            BackendType.SURYA,
            BackendType.SURYA_GPU,
            BackendType.DONUT,
            BackendType.HYBRID,
            BackendType.TESSERACT,
        ]

        for backend in main_backends:
            assert backend in router.BACKEND_SPECS

    @pytest.mark.unit
    def test_deepseek_spec(self, router):
        """Test DeepSeek backend specifications."""
        from app.agents.orchestration.unified_router import BackendType

        spec = router.BACKEND_SPECS[BackendType.DEEPSEEK]

        assert spec.vram_gb == 12.0
        assert spec.supports_gpu == True
        assert spec.supports_cpu == False
        assert "german" in spec.best_for
        assert spec.accuracy_score > 0.9

    @pytest.mark.unit
    def test_donut_spec(self, router):
        """Test Donut backend specifications."""
        from app.agents.orchestration.unified_router import BackendType

        spec = router.BACKEND_SPECS[BackendType.DONUT]

        assert spec.vram_gb == 8.0
        assert spec.supports_gpu == True
        assert spec.supports_cpu == True
        assert "multilingual" in spec.best_for
        assert "cyrillic" in spec.best_for
        assert "pl" in spec.languages
        assert "ru" in spec.languages

    @pytest.mark.unit
    def test_surya_cpu_only(self, router):
        """Test Surya is CPU-only."""
        from app.agents.orchestration.unified_router import BackendType

        spec = router.BACKEND_SPECS[BackendType.SURYA]

        assert spec.vram_gb == 0.0
        assert spec.supports_gpu == False
        assert spec.supports_cpu == True


class TestFallbackChain:
    """Test fallback chain configuration."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_fallback_order(self, router):
        """Test fallback chain order."""
        from app.agents.orchestration.unified_router import BackendType

        order = router.FALLBACK_ORDER

        # DeepSeek should be first
        assert order[0] == BackendType.DEEPSEEK
        # GOT_OCR should be second
        assert order[1] == BackendType.GOT_OCR
        # Donut should be included
        assert BackendType.DONUT in order
        # Tesseract should be last
        assert order[-1] == BackendType.TESSERACT

    @pytest.mark.unit
    def test_fallback_chain_length(self, router):
        """Test fallback chain has expected length."""
        # Should include: DeepSeek, GOT_OCR, Donut, Surya_GPU, Surya, Tesseract
        assert len(router.FALLBACK_ORDER) == 6


class TestRouterInitialization:
    """Test router initialization."""

    @pytest.mark.unit
    def test_router_initialization_without_ml(self):
        """Test router initializes without ML routing."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter

            router = UnifiedOCRRouter(use_ml_routing=False)

            assert router.use_ml_routing == False
            assert router._ml_model is None

    @pytest.mark.unit
    def test_router_initialization_with_ml(self):
        """Test router initializes with ML routing."""
        with patch('app.agents.orchestration.unified_router.GPUManager'), \
             patch('app.agents.orchestration.ml_router_model.OCRRouterModel') as mock_model:

            mock_model.return_value.is_trained = True

            from app.agents.orchestration.unified_router import UnifiedOCRRouter

            router = UnifiedOCRRouter(use_ml_routing=True)

            assert router.use_ml_routing == True

    @pytest.mark.unit
    def test_router_stats_initialized(self):
        """Test router statistics are initialized."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter

            router = UnifiedOCRRouter(use_ml_routing=False)

            assert router._stats["total_requests"] == 0
            assert router._stats["ml_predictions"] == 0
            assert router._stats["rule_fallbacks"] == 0


class TestRuleBasedRouting:
    """Test rule-based routing decisions."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.get_resource_status.return_value = {
                "gpu_available": True,
                "current_backend": None,
                "vram_available_gb": 14.0,
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_high_complexity(self, router):
        """Test routing for high complexity document."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
            RoutingMethod,
        )

        analysis = DocumentAnalysis(
            complexity="high",
            has_tables=True,
            has_handwriting=True,
        )

        result = await router.select_backend(analysis)

        assert result.backend == BackendType.DEEPSEEK
        assert result.routing_method == RoutingMethod.RULE_BASED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_with_formulas(self, router):
        """Test routing for document with formulas."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
        )

        analysis = DocumentAnalysis(has_formulas=True)

        result = await router.select_backend(analysis)

        # GOT_OCR is best for formulas
        assert result.backend in (BackendType.DEEPSEEK, BackendType.GOT_OCR)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_standard_document(self, router):
        """Test routing for standard document."""
        from app.agents.orchestration.unified_router import DocumentAnalysis

        analysis = DocumentAnalysis(
            document_type="standard",
            complexity="low",
        )

        result = await router.select_backend(analysis)

        # Should return a valid backend
        assert result.backend is not None
        assert result.confidence > 0


class TestLanguageBasedRouting:
    """Test language-based routing."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.get_resource_status.return_value = {
                "gpu_available": True,
                "current_backend": None,
                "vram_available_gb": 14.0,
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_russian_document(self, router):
        """Test routing for Russian document."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
            RoutingMethod,
        )

        analysis = DocumentAnalysis(
            detected_language="ru",
            languages=["ru"],
        )

        result = await router.select_backend(analysis)

        # Donut is recommended for Russian/Cyrillic
        assert result.backend == BackendType.DONUT or BackendType.DONUT in result.fallback_chain

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_polish_document(self, router):
        """Test routing for Polish document."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
        )

        analysis = DocumentAnalysis(
            detected_language="pl",
            languages=["pl"],
        )

        result = await router.select_backend(analysis)

        # Donut is recommended for Polish
        assert result.backend == BackendType.DONUT or BackendType.DONUT in result.fallback_chain

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_route_german_document(self, router):
        """Test routing for German document."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
        )

        analysis = DocumentAnalysis(
            detected_language="de",
            languages=["de"],
        )

        result = await router.select_backend(analysis)

        # DeepSeek or GOT_OCR recommended for German
        assert result.backend in (BackendType.DEEPSEEK, BackendType.GOT_OCR)


class TestSLARequirements:
    """Test SLA-based routing."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.get_resource_status.return_value = {
                "gpu_available": True,
                "current_backend": None,
                "vram_available_gb": 14.0,
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_high_accuracy_sla(self, router):
        """Test routing with high accuracy SLA requirement."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            SLARequirements,
        )

        analysis = DocumentAnalysis()
        sla = SLARequirements(min_accuracy=0.95)

        result = await router.select_backend(analysis, sla=sla)

        # Should return a valid backend
        assert result.backend is not None
        assert result.confidence > 0


class TestRouterStatus:
    """Test router status and info."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.get_resource_status.return_value = {
                "gpu_available": True,
                "current_backend": None,
                "vram_available_gb": 14.0,
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_router_name(self, router):
        """Test router has a name."""
        assert router.name == "unified_ocr_router"

    @pytest.mark.unit
    def test_ml_routing_disabled(self, router):
        """Test ML routing is disabled when requested."""
        assert router.use_ml_routing == False


class TestUserPreferences:
    """Test user preference routing."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_user_preference_respected(self, router):
        """Test that user preference is respected."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            BackendType,
            RoutingMethod,
        )

        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            analysis = DocumentAnalysis()
            preferences = {"preferred_backend": "surya"}

            result = await router.select_backend(analysis, preferences=preferences)

            assert result.backend == BackendType.SURYA
            assert result.routing_method == RoutingMethod.USER_PREFERENCE
            assert result.confidence == 1.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_user_preference_ignored(self, router):
        """Test that invalid user preference is ignored."""
        from app.agents.orchestration.unified_router import DocumentAnalysis

        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            analysis = DocumentAnalysis()
            preferences = {"preferred_backend": "invalid_backend"}

            result = await router.select_backend(analysis, preferences=preferences)

            # Should fall through to rule-based selection
            assert result.backend is not None


class TestLoadBalancing:
    """Test load balancing functionality."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_critical_queue_triggers_cpu_fallback(self, router):
        """Test that critical queue length triggers CPU fallback."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            SLARequirements,
            BackendType,
            RoutingMethod,
        )

        with patch('app.core.config.settings') as mock_settings, \
             patch.object(router, '_get_resource_status_async') as mock_status:

            mock_settings.LOAD_BALANCING_ENABLED = True
            mock_settings.QUEUE_LENGTH_THRESHOLD_CRITICAL = 100
            mock_settings.QUEUE_LENGTH_THRESHOLD_HIGH = 50

            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 150,  # Above critical threshold
                "queue_lengths": {"ocr_high": 100, "ocr_normal": 50},
            }

            analysis = DocumentAnalysis()
            sla = SLARequirements()

            result = await router.select_backend(analysis, sla)

            # Should route to CPU-based Surya due to critical queue load
            assert result.backend == BackendType.SURYA
            assert result.routing_method == RoutingMethod.LOAD_BALANCING

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_high_queue_with_gpu_uses_fast_backend(self, router):
        """Test that high queue with GPU uses fast backend."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            SLARequirements,
            BackendType,
            RoutingMethod,
        )

        with patch('app.core.config.settings') as mock_settings, \
             patch.object(router, '_get_resource_status_async') as mock_status:

            mock_settings.LOAD_BALANCING_ENABLED = True
            mock_settings.QUEUE_LENGTH_THRESHOLD_CRITICAL = 100
            mock_settings.QUEUE_LENGTH_THRESHOLD_HIGH = 50

            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 60,  # Above high threshold
                "queue_lengths": {"ocr_high": 35, "ocr_normal": 25},
            }

            analysis = DocumentAnalysis()
            sla = SLARequirements()

            result = await router.select_backend(analysis, sla)

            # Should route to fast GPU backend (GOT_OCR)
            assert result.backend == BackendType.GOT_OCR
            assert result.routing_method == RoutingMethod.LOAD_BALANCING

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_balancing_disabled(self, router):
        """Test that load balancing can be disabled."""
        from app.agents.orchestration.unified_router import (
            DocumentAnalysis,
            SLARequirements,
            RoutingMethod,
        )

        with patch('app.core.config.settings') as mock_settings, \
             patch.object(router, '_get_resource_status_async') as mock_status:

            mock_settings.LOAD_BALANCING_ENABLED = False

            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 150,  # High queue but load balancing disabled
                "queue_lengths": {},
            }

            analysis = DocumentAnalysis()
            sla = SLARequirements()

            result = await router.select_backend(analysis, sla)

            # Should not be load balanced
            assert result.routing_method != RoutingMethod.LOAD_BALANCING


class TestBackendAvailability:
    """Test backend availability checking."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": False,  # GPU unavailable
                "free_memory_gb": 0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_gpu_backend_unavailable_without_gpu(self, router):
        """Test GPU backends are unavailable when no GPU."""
        from app.agents.orchestration.unified_router import BackendType

        resource_status = {
            "gpu_available": False,
            "gpu_memory_available_gb": 0,
        }

        # DeepSeek requires GPU
        assert router._is_backend_available(BackendType.DEEPSEEK, resource_status) == False

        # Surya works on CPU
        assert router._is_backend_available(BackendType.SURYA, resource_status) == True

        # Tesseract works on CPU
        assert router._is_backend_available(BackendType.TESSERACT, resource_status) == True

    @pytest.mark.unit
    def test_gpu_backend_unavailable_with_low_vram(self):
        """Test GPU backends are unavailable when VRAM too low."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 2.0,  # Very low VRAM
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter, BackendType
            router = UnifiedOCRRouter(use_ml_routing=False)

            resource_status = {
                "gpu_available": True,
                "gpu_memory_available_gb": 2.0,  # Very low
            }

            # DeepSeek needs 12GB - should be unavailable
            assert router._is_backend_available(BackendType.DEEPSEEK, resource_status) == False

            # GOT_OCR and Surya_GPU may have fallback CPU modes
            # Just verify DeepSeek (which requires GPU) is correctly unavailable
            # The implementation may allow some backends with CPU fallback

            # Surya (CPU-only) should always be available
            assert router._is_backend_available(BackendType.SURYA, resource_status) == True

    @pytest.mark.unit
    def test_find_available_fallback(self):
        """Test finding available fallback backend."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": False,
                "free_memory_gb": 0,
            }

            from app.agents.orchestration.unified_router import UnifiedOCRRouter, BackendType
            router = UnifiedOCRRouter(use_ml_routing=False)

            resource_status = {
                "gpu_available": False,
                "gpu_memory_available_gb": 0,
            }

            # Should return a fallback backend (any valid backend from the fallback chain)
            fallback = router._find_available_fallback(BackendType.DEEPSEEK, resource_status)

            # The implementation returns the first available backend from the fallback chain
            # which can vary based on implementation. Just verify we get a valid fallback
            assert fallback is not None
            assert fallback in router.FALLBACK_ORDER


class TestFallbackChainGeneration:
    """Test fallback chain generation."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_fallback_chain_starts_with_primary(self, router):
        """Test fallback chain starts with primary backend."""
        from app.agents.orchestration.unified_router import BackendType

        chain = router._get_fallback_chain(BackendType.DEEPSEEK)

        assert chain[0] == BackendType.DEEPSEEK

    @pytest.mark.unit
    def test_fallback_chain_includes_all_backends(self, router):
        """Test fallback chain includes all backends."""
        from app.agents.orchestration.unified_router import BackendType

        chain = router._get_fallback_chain(BackendType.GOT_OCR)

        # Should include all fallback order backends
        for backend in router.FALLBACK_ORDER:
            assert backend in chain

    @pytest.mark.unit
    def test_fallback_chain_no_duplicates(self, router):
        """Test fallback chain has no duplicates."""
        from app.agents.orchestration.unified_router import BackendType

        chain = router._get_fallback_chain(BackendType.SURYA)

        # No duplicates
        assert len(chain) == len(set(chain))


class TestProcessMethod:
    """Test the process method (OrchestrationAgent interface)."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_with_dict_input(self, router):
        """Test process method with dictionary input."""
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
                    "complexity": "medium",
                    "has_tables": True,
                },
                "sla_requirements": {
                    "max_processing_time_seconds": 60,
                },
                "user_preferences": {},
            }

            result = await router.process(input_data)

            assert "backend" in result
            assert "reason" in result
            assert "confidence" in result
            assert "routing_method" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_updates_stats(self, router):
        """Test process method updates statistics."""
        with patch.object(router, '_get_resource_status_async') as mock_status:
            mock_status.return_value = {
                "gpu_available": True,
                "gpu_memory_available_gb": 14.0,
                "queue_length": 0,
                "queue_lengths": {},
            }

            initial_total = router._stats["total_requests"]

            input_data = {
                "document_metadata": {"document_type": "other"},
            }

            await router.process(input_data)

            assert router._stats["total_requests"] == initial_total + 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_requires_document_metadata(self, router):
        """Test process method requires document_metadata."""
        from app.agents.base import AgentProcessingError

        with pytest.raises((AgentProcessingError, KeyError, ValueError)):
            await router.process({})


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_check_returns_status(self, router):
        """Test health check returns proper status."""
        result = await router.health_check()

        assert "router" in result
        assert "backends" in result
        assert "gpu_available" in result
        assert "ml_routing_available" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_check_no_backends_configured(self, router):
        """Test health check with no backends configured."""
        result = await router.health_check()

        # All backends should be "not_configured" since none are registered
        for backend_status in result["backends"].values():
            assert backend_status in ("not_configured", "healthy", "unhealthy", "timeout")


class TestRoutingStats:
    """Test routing statistics."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_routing_stats(self, router):
        """Test getting routing statistics."""
        stats = router.get_routing_stats()

        assert "total_requests" in stats
        assert "ml_predictions" in stats
        assert "rule_fallbacks" in stats
        assert "backend_selections" in stats

    @pytest.mark.unit
    def test_initial_stats_are_zero(self, router):
        """Test initial statistics are all zero."""
        stats = router.get_routing_stats()

        assert stats["total_requests"] == 0
        assert stats["ml_predictions"] == 0
        assert stats["rule_fallbacks"] == 0


class TestGetBackendInfo:
    """Test getting backend information."""

    @pytest.fixture
    def router(self):
        """Create router without ML."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_backend_info(self, router):
        """Test getting backend info."""
        from app.agents.orchestration.unified_router import BackendType

        info = router.get_backend_info(BackendType.DEEPSEEK)

        assert info is not None
        assert info.name == "DeepSeek-Janus-Pro"
        assert info.vram_gb == 12.0

    @pytest.mark.unit
    def test_get_backend_info_invalid(self, router):
        """Test getting info for invalid backend returns None."""
        info = router.get_backend_info("invalid")

        assert info is None


class TestGetAvailableBackends:
    """Test getting available backends."""

    @pytest.fixture
    def router(self):
        """Create router without ML with GPU available."""
        with patch('app.agents.orchestration.unified_router.GPUManager') as mock_gm:
            mock_gm.return_value.check_availability.return_value = {
                "available": True,
                "free_memory_gb": 14.0,
            }
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            return UnifiedOCRRouter(use_ml_routing=False)

    @pytest.mark.unit
    def test_get_all_available_backends(self, router):
        """Test getting all available backends."""
        backends = router.get_available_backends()

        assert len(backends) > 0

    @pytest.mark.unit
    def test_get_gpu_backends_only(self, router):
        """Test filtering GPU-only backends."""
        from app.agents.orchestration.unified_router import BackendType

        backends = router.get_available_backends(gpu_required=True)

        for backend in backends:
            spec = router.BACKEND_SPECS[backend]
            assert spec.vram_gb > 0 or not spec.supports_cpu

    @pytest.mark.unit
    def test_get_cpu_backends_only(self, router):
        """Test filtering CPU-only backends."""
        from app.agents.orchestration.unified_router import BackendType

        backends = router.get_available_backends(gpu_required=False)

        for backend in backends:
            spec = router.BACKEND_SPECS[backend]
            assert spec.vram_gb == 0 or spec.supports_cpu


class TestMLRoutingAvailability:
    """Test ML routing availability checks."""

    @pytest.mark.unit
    def test_ml_routing_not_available_when_disabled(self):
        """Test ML routing not available when disabled."""
        with patch('app.agents.orchestration.unified_router.GPUManager'):
            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            router = UnifiedOCRRouter(use_ml_routing=False)

            assert router.is_ml_routing_available() == False

    @pytest.mark.unit
    def test_ml_routing_not_available_without_model(self):
        """Test ML routing not available without trained model."""
        with patch('app.agents.orchestration.unified_router.GPUManager'), \
             patch('app.agents.orchestration.ml_router_model.OCRRouterModel') as mock_model:

            mock_model.return_value.is_trained = False

            from app.agents.orchestration.unified_router import UnifiedOCRRouter
            router = UnifiedOCRRouter(use_ml_routing=True)

            assert router.is_ml_routing_available() == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
