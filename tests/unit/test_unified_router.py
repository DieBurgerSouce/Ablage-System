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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
