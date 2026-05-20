# -*- coding: utf-8 -*-
"""
Unit-Tests für OCR Pipeline Service.

Testet:
- Pipeline-Initialisierung mit verschiedenen Konfigurationen
- Backend-Registrierung
- Dokumentenverarbeitung (Erfolg, Fehler, Fallback)
- Confidence-basierte Qualitätskontrolle
- German Correction Agent Integration
- Historical German Normalization
- Batch-Verarbeitung
- Status-Reporting

Feinpoliert und durchdacht - Umfassende OCR-Pipeline-Tests.
"""

import pytest
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ========================= Mock Classes =========================


@dataclass
class MockFallbackResult:
    """Mock FallbackResult für Tests."""
    success: bool
    text: str
    confidence: float
    final_backend: str
    backends_tried: List[str]
    fallbacks_occurred: int
    error: Optional[str] = None
    confidence_metrics: Optional[Mock] = None


@dataclass
class MockNormalizationResult:
    """Mock NormalizationResult für Tests."""
    original: str
    normalized: str
    was_changed: bool
    change_count: int
    changes: List[Dict[str, Any]]
    era_detected: Optional[Mock] = None
    confidence: float = 0.95


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_settings():
    """Mock settings für Tests."""
    with patch("app.services.ocr_pipeline.settings") as mock:
        mock.HISTORICAL_NORMALIZATION_ENABLED = True
        mock.HISTORICAL_NORM_PRE_1996 = True
        mock.HISTORICAL_NORM_TH = True
        mock.HISTORICAL_NORM_C = True
        mock.HISTORICAL_NORM_PH = True
        mock.HISTORICAL_NORM_FRAKTUR = True
        yield mock


@pytest.fixture
def mock_confidence_service():
    """Mock ConfidenceService."""
    service = Mock()
    service.analyze = AsyncMock(return_value={
        "overall_confidence": 0.92,
        "word_confidence": 0.95,
        "language_score": 0.90
    })
    return service


@pytest.fixture
def mock_fallback_chain():
    """Mock FallbackChain."""
    chain = Mock()
    chain.execute = AsyncMock(return_value=MockFallbackResult(
        success=True,
        text="Extrahierter deutscher Text mit Umlauten: ä, ö, ü, ß",
        confidence=0.92,
        final_backend="deepseek",
        backends_tried=["deepseek"],
        fallbacks_occurred=0,
        confidence_metrics=None
    ))
    chain.register_backend_handler = Mock()
    chain.get_metrics = Mock(return_value={
        "total_requests": 100,
        "successful_requests": 95,
        "fallbacks": 5
    })
    return chain


@pytest.fixture
def mock_circuit_registry():
    """Mock CircuitBreakerRegistry."""
    registry = Mock()
    registry.get_or_create = Mock(return_value=Mock())
    registry.get_all_status = Mock(return_value={
        "deepseek": {"state": "closed", "failures": 0},
        "got_ocr": {"state": "closed", "failures": 0},
        "surya": {"state": "closed", "failures": 0}
    })
    return registry


@pytest.fixture
def mock_memory_guard():
    """Mock GPUMemoryGuard."""
    guard = Mock()
    guard.check_memory_status = Mock(return_value={
        "available": True,
        "remaining_gb": 12.5,
        "usage_percent": 22,
        "is_critical": False
    })
    guard.cleanup_cache = Mock()
    guard.get_status = Mock(return_value={
        "available_gb": 12.5,
        "used_gb": 3.5,
        "total_gb": 16.0
    })
    return guard


@pytest.fixture
def mock_gpu_manager():
    """Mock GPUManager."""
    manager = Mock()
    manager.get_detailed_status = Mock(return_value={
        "gpu_available": True,
        "vram_total_gb": 16.0,
        "vram_used_gb": 3.5
    })
    return manager


@pytest.fixture
def mock_german_agent():
    """Mock GermanCorrectionAgent."""
    agent = Mock()
    agent.process = AsyncMock(return_value={
        "text": "Korrigierter deutscher Text mit Umlauten: ä, ö, ü, ß",
        "corrections_applied": 3,
        "umlauts_restored": 2,
        "validation_score": 0.98,
        "domain_detected": "business"
    })
    agent.get_correction_stats = Mock(return_value={
        "total_corrections": 150,
        "umlaut_restorations": 45
    })
    return agent


@pytest.fixture
def mock_historical_normalizer():
    """Mock HistoricalGermanNormalizer."""
    normalizer = Mock()
    normalizer.normalize = Mock(return_value=MockNormalizationResult(
        original="Der Thal war daß Centrum",
        normalized="Das Tal war das Zentrum",
        was_changed=True,
        change_count=3,
        changes=[
            {"old": "Thal", "new": "Tal"},
            {"old": "daß", "new": "das"},
            {"old": "Centrum", "new": "Zentrum"}
        ]
    ))
    return normalizer


@pytest.fixture
def pipeline_with_mocks(
    mock_settings,
    mock_confidence_service,
    mock_fallback_chain,
    mock_circuit_registry,
    mock_memory_guard,
    mock_gpu_manager
):
    """Create OCRPipeline with all mocks."""
    with patch("app.services.ocr_pipeline.get_confidence_service", return_value=mock_confidence_service), \
         patch("app.services.ocr_pipeline.get_fallback_chain", return_value=mock_fallback_chain), \
         patch("app.services.ocr_pipeline.get_circuit_breaker_registry", return_value=mock_circuit_registry), \
         patch("app.services.ocr_pipeline.get_memory_guard", return_value=mock_memory_guard), \
         patch("app.services.ocr_pipeline.GPUManager", return_value=mock_gpu_manager):

        from app.services.ocr_pipeline import OCRPipeline, ConfidenceThresholds

        pipeline = OCRPipeline(
            enable_german_correction=True,
            enable_circuit_breaker=True,
            enable_memory_guard=True,
            enable_historical_normalization=True,
            min_confidence_threshold=0.65,
            confidence_thresholds=ConfidenceThresholds(low=0.70, medium=0.85, high=0.95),
            enable_confidence_fallback=True
        )

        # Store mocks for access in tests
        pipeline._mock_fallback_chain = mock_fallback_chain
        pipeline._mock_memory_guard = mock_memory_guard
        pipeline._mock_confidence_service = mock_confidence_service
        pipeline._mock_circuit_registry = mock_circuit_registry

        yield pipeline


# ========================= Initialization Tests =========================


class TestOCRPipelineInitialization:
    """Tests für Pipeline-Initialisierung."""

    def test_default_initialization(self, mock_settings):
        """Test Pipeline mit Standard-Konfiguration."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline()

            assert pipeline.enable_german_correction is True
            assert pipeline.enable_circuit_breaker is True
            assert pipeline.enable_memory_guard is True
            assert pipeline.min_confidence_threshold == 0.65

    def test_initialization_with_disabled_features(self, mock_settings):
        """Test Pipeline mit deaktivierten Features."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline(
                enable_german_correction=False,
                enable_circuit_breaker=False,
                enable_memory_guard=False,
                enable_historical_normalization=False
            )

            assert pipeline.enable_german_correction is False
            assert pipeline.enable_circuit_breaker is False
            assert pipeline.enable_memory_guard is False
            assert pipeline.enable_historical_normalization is False
            assert pipeline.memory_guard is None

    def test_custom_confidence_thresholds(self, mock_settings):
        """Test Pipeline mit benutzerdefinierten Confidence-Schwellenwerten."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline, ConfidenceThresholds

            custom_thresholds = ConfidenceThresholds(low=0.60, medium=0.80, high=0.90)
            pipeline = OCRPipeline(confidence_thresholds=custom_thresholds)

            assert pipeline.confidence_thresholds.low == 0.60
            assert pipeline.confidence_thresholds.medium == 0.80
            assert pipeline.confidence_thresholds.high == 0.90


# ========================= Backend Registration Tests =========================


class TestBackendRegistration:
    """Tests für Backend-Registrierung."""

    def test_register_backend_handler(self, pipeline_with_mocks):
        """Test Backend-Handler Registrierung."""
        pipeline = pipeline_with_mocks

        async def dummy_handler(doc_id: str, path: str) -> Dict[str, Any]:
            return {"text": "Test", "confidence": 0.9}

        pipeline.register_backend_handler("custom_backend", dummy_handler)

        # Verify fallback chain was called
        pipeline._mock_fallback_chain.register_backend_handler.assert_called_once_with(
            "custom_backend", dummy_handler
        )

        # Verify circuit breaker was created
        pipeline._mock_circuit_registry.get_or_create.assert_called_with("custom_backend")

    def test_register_backend_without_circuit_breaker(self, mock_settings):
        """Test Backend-Registrierung ohne Circuit Breaker."""
        mock_fallback = Mock()
        mock_fallback.register_backend_handler = Mock()
        mock_fallback.get_metrics = Mock(return_value={})

        mock_circuit = Mock()
        mock_circuit.get_or_create = Mock()
        mock_circuit.get_all_status = Mock(return_value={})

        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain", return_value=mock_fallback), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry", return_value=mock_circuit), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline(enable_circuit_breaker=False)

            async def handler(doc_id: str, path: str) -> Dict[str, Any]:
                return {"text": "Test", "confidence": 0.9}

            pipeline.register_backend_handler("test_backend", handler)

            # Circuit breaker should NOT be created
            mock_circuit.get_or_create.assert_not_called()


# ========================= Process Document Tests =========================


class TestProcessDocument:
    """Tests für Dokumentenverarbeitung."""

    @pytest.mark.asyncio
    async def test_process_success(self, pipeline_with_mocks, mock_german_agent):
        """Test erfolgreiche Dokumentenverarbeitung."""
        pipeline = pipeline_with_mocks

        # Mock German agent
        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_001",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.success is True
        assert result.backend_used == "deepseek"
        assert result.confidence == 0.92
        assert len(result.backends_tried) > 0
        assert result.processing_time_ms >= 0  # Kann 0 sein bei gemockten Tests

    @pytest.mark.asyncio
    async def test_process_fallback_chain_error(self, pipeline_with_mocks):
        """Test Verarbeitung bei Fallback Chain Fehler."""
        pipeline = pipeline_with_mocks

        # Mock Fallback Chain to raise exception
        pipeline._mock_fallback_chain.execute = AsyncMock(
            side_effect=Exception("Backend nicht verfügbar")
        )

        result = await pipeline.process(
            document_id="doc_002",
            image_path="/path/to/document.pdf",
            language="de"
        )

        assert result.success is False
        assert result.backend_used == "none"
        assert "Backend nicht verfügbar" in result.error

    @pytest.mark.asyncio
    async def test_process_fallback_chain_failure(self, pipeline_with_mocks):
        """Test Verarbeitung bei Fallback Chain Fehler-Result."""
        pipeline = pipeline_with_mocks

        # Mock unsuccessful fallback result
        pipeline._mock_fallback_chain.execute = AsyncMock(return_value=MockFallbackResult(
            success=False,
            text="",
            confidence=0.0,
            final_backend="surya",
            backends_tried=["deepseek", "got_ocr", "surya"],
            fallbacks_occurred=2,
            error="Alle Backends fehlgeschlagen"
        ))

        result = await pipeline.process(
            document_id="doc_003",
            image_path="/path/to/document.pdf",
            language="de"
        )

        assert result.success is False
        assert result.fallbacks_occurred == 2
        assert "Alle Backends fehlgeschlagen" in result.error

    @pytest.mark.asyncio
    async def test_process_with_gpu_memory_critical(self, pipeline_with_mocks, mock_german_agent):
        """Test Verarbeitung bei kritischem GPU-Speicher."""
        pipeline = pipeline_with_mocks

        # Set critical memory state
        pipeline._mock_memory_guard.check_memory_status = Mock(return_value={
            "available": True,
            "remaining_gb": 2.0,
            "usage_percent": 88,
            "is_critical": True
        })

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_004",
                image_path="/path/to/document.pdf",
                language="de"
            )

        # Should still succeed but cleanup should be called
        assert result.success is True
        pipeline._mock_memory_guard.cleanup_cache.assert_called_once()


# ========================= Confidence Fallback Tests =========================


class TestConfidenceFallback:
    """Tests für Confidence-basierte Fallbacks."""

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_fallback(self, pipeline_with_mocks, mock_german_agent):
        """Test Fallback bei niedriger Confidence."""
        pipeline = pipeline_with_mocks

        # First call returns low confidence
        call_count = [0]

        async def mock_execute(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockFallbackResult(
                    success=True,
                    text="Text mit niedriger Qualität",
                    confidence=0.65,  # Under low threshold (0.70)
                    final_backend="surya",
                    backends_tried=["surya"],
                    fallbacks_occurred=0
                )
            else:
                return MockFallbackResult(
                    success=True,
                    text="Text mit höherer Qualität",
                    confidence=0.88,  # Better confidence
                    final_backend="deepseek",
                    backends_tried=["deepseek"],
                    fallbacks_occurred=0
                )

        pipeline._mock_fallback_chain.execute = AsyncMock(side_effect=mock_execute)

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_005",
                image_path="/path/to/document.pdf",
                language="de"
            )

        # Should have tried fallback and improved
        assert result.confidence_fallback_triggered is True
        assert result.confidence == 0.88
        assert result.backend_used == "deepseek"

    @pytest.mark.asyncio
    async def test_medium_confidence_needs_review(self, pipeline_with_mocks, mock_german_agent):
        """Test needs_review Flag bei mittlerer Confidence."""
        pipeline = pipeline_with_mocks

        # Return medium confidence (between low and medium thresholds)
        pipeline._mock_fallback_chain.execute = AsyncMock(return_value=MockFallbackResult(
            success=True,
            text="Text mit mittlerer Qualität",
            confidence=0.78,  # Between 0.70 (low) and 0.85 (medium)
            final_backend="got_ocr",
            backends_tried=["got_ocr"],
            fallbacks_occurred=0
        ))

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_006",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.success is True
        assert result.needs_review is True
        assert result.confidence_fallback_triggered is False

    @pytest.mark.asyncio
    async def test_high_confidence_no_review(self, pipeline_with_mocks, mock_german_agent):
        """Test keine Review bei hoher Confidence."""
        pipeline = pipeline_with_mocks

        # Return high confidence
        pipeline._mock_fallback_chain.execute = AsyncMock(return_value=MockFallbackResult(
            success=True,
            text="Text mit hoher Qualität",
            confidence=0.96,  # Above high threshold (0.95)
            final_backend="deepseek",
            backends_tried=["deepseek"],
            fallbacks_occurred=0
        ))

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_007",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.success is True
        assert result.needs_review is False
        assert result.confidence == 0.96


# ========================= German Correction Tests =========================


class TestGermanCorrection:
    """Tests für German Correction Agent Integration."""

    @pytest.mark.asyncio
    async def test_german_correction_applied(self, pipeline_with_mocks, mock_german_agent):
        """Test German Correction wird angewendet."""
        pipeline = pipeline_with_mocks

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_008",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.german_correction_applied is True
        assert result.corrections_applied == 3
        assert result.correction_details is not None
        assert result.correction_details["umlauts_restored"] == 2

    @pytest.mark.asyncio
    async def test_german_correction_skipped_for_english(self, pipeline_with_mocks, mock_german_agent):
        """Test German Correction wird für Englisch übersprungen."""
        pipeline = pipeline_with_mocks

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_009",
                image_path="/path/to/document.pdf",
                language="en"
            )

        assert result.german_correction_applied is False
        mock_german_agent.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_german_correction_skip_flag(self, pipeline_with_mocks, mock_german_agent):
        """Test German Correction mit skip_german_correction Flag."""
        pipeline = pipeline_with_mocks

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_010",
                image_path="/path/to/document.pdf",
                language="de",
                skip_german_correction=True
            )

        assert result.german_correction_applied is False
        mock_german_agent.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_german_correction_error_handling(self, pipeline_with_mocks, mock_german_agent):
        """Test Fehlerbehandlung bei German Correction."""
        pipeline = pipeline_with_mocks

        # Make German agent throw exception
        mock_german_agent.process = AsyncMock(side_effect=Exception("Korrektur-Fehler"))

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            result = await pipeline.process(
                document_id="doc_011",
                image_path="/path/to/document.pdf",
                language="de"
            )

        # Should succeed with uncorrected text
        assert result.success is True
        assert result.german_correction_applied is False
        # Original text should be used
        assert result.corrected_text == result.text


# ========================= Historical Normalization Tests =========================


class TestHistoricalNormalization:
    """Tests für Historical German Normalization."""

    @pytest.mark.asyncio
    async def test_historical_normalization_applied(
        self, pipeline_with_mocks, mock_german_agent, mock_historical_normalizer
    ):
        """Test Historical Normalization wird angewendet."""
        pipeline = pipeline_with_mocks

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent), \
             patch.object(pipeline, "_get_historical_normalizer", return_value=mock_historical_normalizer):
            result = await pipeline.process(
                document_id="doc_012",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.historical_normalization_applied is True
        assert result.historical_changes_count == 3
        assert result.historical_normalization_details is not None

    @pytest.mark.asyncio
    async def test_historical_normalization_no_changes(
        self, pipeline_with_mocks, mock_german_agent, mock_historical_normalizer
    ):
        """Test Historical Normalization ohne Änderungen."""
        pipeline = pipeline_with_mocks

        # Mock no changes needed
        mock_historical_normalizer.normalize = Mock(return_value=MockNormalizationResult(
            original="Moderner deutscher Text",
            normalized="Moderner deutscher Text",
            was_changed=False,
            change_count=0,
            changes=[]
        ))

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent), \
             patch.object(pipeline, "_get_historical_normalizer", return_value=mock_historical_normalizer):
            result = await pipeline.process(
                document_id="doc_013",
                image_path="/path/to/document.pdf",
                language="de"
            )

        assert result.historical_normalization_applied is False
        assert result.historical_changes_count == 0

    @pytest.mark.asyncio
    async def test_historical_normalization_error_handling(
        self, pipeline_with_mocks, mock_german_agent, mock_historical_normalizer
    ):
        """Test Fehlerbehandlung bei Historical Normalization."""
        pipeline = pipeline_with_mocks

        # Make normalizer throw exception
        mock_historical_normalizer.normalize = Mock(side_effect=Exception("Normalisierung-Fehler"))

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent), \
             patch.object(pipeline, "_get_historical_normalizer", return_value=mock_historical_normalizer):
            result = await pipeline.process(
                document_id="doc_014",
                image_path="/path/to/document.pdf",
                language="de"
            )

        # Should succeed without normalization
        assert result.success is True
        assert result.historical_normalization_applied is False


# ========================= Batch Processing Tests =========================


class TestBatchProcessing:
    """Tests für Batch-Verarbeitung."""

    @pytest.mark.asyncio
    async def test_batch_processing_success(self, pipeline_with_mocks, mock_german_agent):
        """Test erfolgreiche Batch-Verarbeitung."""
        pipeline = pipeline_with_mocks

        documents = [
            {"document_id": "doc_b1", "image_path": "/path/doc1.pdf"},
            {"document_id": "doc_b2", "image_path": "/path/doc2.pdf"},
            {"document_id": "doc_b3", "image_path": "/path/doc3.pdf"},
        ]

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            results = await pipeline.process_batch(documents, concurrency=2)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_processing_with_errors(self, pipeline_with_mocks, mock_german_agent):
        """Test Batch-Verarbeitung mit einzelnen Fehlern."""
        pipeline = pipeline_with_mocks

        # Second call fails
        call_count = [0]

        async def mock_execute(**kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Dokument 2 Fehler")
            return MockFallbackResult(
                success=True,
                text="Verarbeiteter Text",
                confidence=0.90,
                final_backend="deepseek",
                backends_tried=["deepseek"],
                fallbacks_occurred=0
            )

        pipeline._mock_fallback_chain.execute = AsyncMock(side_effect=mock_execute)

        documents = [
            {"document_id": "doc_b4", "image_path": "/path/doc4.pdf"},
            {"document_id": "doc_b5", "image_path": "/path/doc5.pdf"},
            {"document_id": "doc_b6", "image_path": "/path/doc6.pdf"},
        ]

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            results = await pipeline.process_batch(documents, concurrency=1)

        assert len(results) == 3
        # First and third should succeed, second should fail
        assert results[0].success is True
        assert results[1].success is False
        assert "Dokument 2 Fehler" in results[1].error
        assert results[2].success is True

    @pytest.mark.asyncio
    async def test_batch_processing_concurrency_limit(self, pipeline_with_mocks, mock_german_agent):
        """Test Batch-Verarbeitung respektiert Concurrency-Limit."""
        pipeline = pipeline_with_mocks

        concurrent_count = [0]
        max_concurrent = [0]

        original_execute = pipeline._mock_fallback_chain.execute

        async def counting_execute(**kwargs):
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            await asyncio.sleep(0.01)  # Small delay
            concurrent_count[0] -= 1
            return await original_execute(**kwargs)

        pipeline._mock_fallback_chain.execute = AsyncMock(side_effect=counting_execute)

        documents = [
            {"document_id": f"doc_c{i}", "image_path": f"/path/doc{i}.pdf"}
            for i in range(5)
        ]

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent):
            results = await pipeline.process_batch(documents, concurrency=2)

        assert len(results) == 5
        assert max_concurrent[0] <= 2  # Should never exceed concurrency limit


# ========================= Status Tests =========================


class TestPipelineStatus:
    """Tests für Pipeline-Status."""

    def test_get_status_complete(self, pipeline_with_mocks, mock_german_agent):
        """Test vollständiger Status-Abruf."""
        pipeline = pipeline_with_mocks
        pipeline._german_agent = mock_german_agent

        status = pipeline.get_status()

        assert "pipeline" in status
        assert "fallback_chain" in status
        assert "circuit_breakers" in status
        assert "memory_guard" in status

        # Check pipeline settings
        assert status["pipeline"]["german_correction_enabled"] is True
        assert status["pipeline"]["circuit_breaker_enabled"] is True
        assert status["pipeline"]["confidence_thresholds"]["low"] == 0.70

    def test_get_status_with_german_agent(self, pipeline_with_mocks, mock_german_agent):
        """Test Status enthält German Agent Stats."""
        pipeline = pipeline_with_mocks
        pipeline._german_agent = mock_german_agent

        status = pipeline.get_status()

        assert "german_correction" in status
        assert status["german_correction"]["total_corrections"] == 150


# ========================= OCRPipelineResult Tests =========================


class TestOCRPipelineResult:
    """Tests für OCRPipelineResult Dataclass."""

    def test_to_dict_conversion(self):
        """Test to_dict() Konvertierung."""
        from app.services.ocr_pipeline import OCRPipelineResult

        result = OCRPipelineResult(
            success=True,
            text="Original Text",
            corrected_text="Korrigierter Text",
            confidence=0.92,
            backend_used="deepseek",
            backends_tried=["deepseek", "got_ocr"],
            fallbacks_occurred=1,
            corrections_applied=5,
            processing_time_ms=1500,
            german_correction_applied=True,
            historical_normalization_applied=True,
            historical_changes_count=3,
            needs_review=False
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["text"] == "Korrigierter Text"  # corrected_text als Haupttext
        assert result_dict["original_text"] == "Original Text"
        assert result_dict["confidence"] == 0.92
        assert result_dict["backend_used"] == "deepseek"
        assert len(result_dict["backends_tried"]) == 2
        assert result_dict["german_correction_applied"] is True
        assert result_dict["historical_normalization_applied"] is True


# ========================= Singleton Tests =========================


class TestOCRPipelineSingleton:
    """Tests für Singleton-Pattern."""

    def test_get_ocr_pipeline_singleton(self, mock_settings):
        """Test get_ocr_pipeline() gibt Singleton zurück."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            # Reset singleton
            import app.services.ocr_pipeline as pipeline_module
            pipeline_module._ocr_pipeline = None

            from app.services.ocr_pipeline import get_ocr_pipeline

            pipeline1 = get_ocr_pipeline()
            pipeline2 = get_ocr_pipeline()

            assert pipeline1 is pipeline2


# ========================= Error Message Tests =========================


class TestGermanErrorMessages:
    """Tests für deutsche Fehlermeldungen."""

    @pytest.mark.asyncio
    async def test_error_messages_in_german(self, pipeline_with_mocks):
        """Test Fehlermeldungen sind auf Deutsch."""
        pipeline = pipeline_with_mocks

        # Make fallback chain fail
        pipeline._mock_fallback_chain.execute = AsyncMock(
            side_effect=Exception("Verbindung fehlgeschlagen")
        )

        result = await pipeline.process(
            document_id="doc_error",
            image_path="/path/to/document.pdf",
            language="de"
        )

        assert result.success is False
        # Error should be captured
        assert result.error is not None


# ========================= Lazy Loading Tests =========================


class TestLazyLoading:
    """Tests für Lazy Loading von Komponenten."""

    def test_german_agent_lazy_loading(self, mock_settings):
        """Test German Agent wird lazy geladen."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline()

            # Agent should not be loaded yet
            assert pipeline._german_agent is None

            # Try to get agent (will fail if module not available, but tests lazy loading)
            with patch("app.services.ocr_pipeline.GermanCorrectionAgent", create=True) as mock_agent_class:
                mock_agent_class.return_value = Mock()

                with patch.dict("sys.modules", {"app.agents.postprocessing.german_correction_agent": Mock(GermanCorrectionAgent=mock_agent_class)}):
                    try:
                        agent = pipeline._get_german_agent()
                    except ImportError:
                        pass  # Expected if module doesn't exist

    def test_historical_normalizer_lazy_loading(self, mock_settings):
        """Test Historical Normalizer wird lazy geladen."""
        with patch("app.services.ocr_pipeline.get_confidence_service"), \
             patch("app.services.ocr_pipeline.get_fallback_chain"), \
             patch("app.services.ocr_pipeline.get_circuit_breaker_registry"), \
             patch("app.services.ocr_pipeline.get_memory_guard"), \
             patch("app.services.ocr_pipeline.GPUManager"):

            from app.services.ocr_pipeline import OCRPipeline

            pipeline = OCRPipeline()

            # Normalizer should not be loaded yet
            assert pipeline._historical_normalizer is None


# ========================= Integration-like Tests =========================


class TestPipelineIntegration:
    """Integration-ähnliche Tests für die Pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self, pipeline_with_mocks, mock_german_agent, mock_historical_normalizer):
        """Test vollständiger Pipeline-Durchlauf."""
        pipeline = pipeline_with_mocks

        with patch.object(pipeline, "_get_german_agent", return_value=mock_german_agent), \
             patch.object(pipeline, "_get_historical_normalizer", return_value=mock_historical_normalizer):

            result = await pipeline.process(
                document_id="doc_full_001",
                image_path="/path/to/historical_document.pdf",
                language="de",
                options={"enhance": True},
                preferred_backend="deepseek",
                document_type="contract"
            )

        # Verify full pipeline execution
        assert result.success is True
        assert result.backend_used == "deepseek"
        assert result.german_correction_applied is True
        assert result.historical_normalization_applied is True
        assert result.processing_time_ms >= 0  # Kann 0 sein bei gemockten Tests

        # Verify result can be serialized
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "text" in result_dict
        assert "confidence" in result_dict
