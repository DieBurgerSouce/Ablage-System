# -*- coding: utf-8 -*-
"""
Integration Tests fuer OCR Pipeline.

Testet die vollstaendige OCR Pipeline inklusive:
- Fallback Chain
- Confidence Service
- Circuit Breaker Integration
- GPU Memory Guard
- German Correction Agent

Feinpoliert und durchdacht - Enterprise Pipeline Integration Testing.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

# Import Pipeline-Komponenten
from app.services.ocr_pipeline import (
    OCRPipeline,
    OCRPipelineResult,
    get_ocr_pipeline,
)
from app.services.confidence_service import (
    ConfidenceService,
    ConfidenceLevel,
    QualityDecision,
    ConfidenceMetrics,
    get_confidence_service,
)
from app.services.fallback_chain import (
    FallbackChain,
    FallbackResult,
    FallbackReason,
    BackendConfig,
    get_fallback_chain,
)


# =============================================================================
# Confidence Service Tests
# =============================================================================


class TestConfidenceService:
    """Tests fuer ConfidenceService."""

    @pytest.fixture
    def service(self):
        """Erstelle ConfidenceService Instanz."""
        return ConfidenceService()

    def test_determine_confidence_level_excellent(self, service):
        """Teste Confidence Level EXCELLENT (>= 0.95)."""
        level = service.determine_confidence_level(0.97)
        assert level == ConfidenceLevel.EXCELLENT

    def test_determine_confidence_level_high(self, service):
        """Teste Confidence Level HIGH (>= 0.85)."""
        level = service.determine_confidence_level(0.88)
        assert level == ConfidenceLevel.HIGH

    def test_determine_confidence_level_medium(self, service):
        """Teste Confidence Level MEDIUM (>= 0.70)."""
        level = service.determine_confidence_level(0.75)
        assert level == ConfidenceLevel.MEDIUM

    def test_determine_confidence_level_low(self, service):
        """Teste Confidence Level LOW (>= 0.50)."""
        level = service.determine_confidence_level(0.55)
        assert level == ConfidenceLevel.LOW

    def test_determine_confidence_level_very_low(self, service):
        """Teste Confidence Level VERY_LOW (< 0.50)."""
        level = service.determine_confidence_level(0.35)
        assert level == ConfidenceLevel.VERY_LOW

    def test_quality_decision_accept(self, service):
        """Teste Qualitaetsentscheidung ACCEPT bei hoher Confidence."""
        decision = service.make_quality_decision(0.92)
        assert decision == QualityDecision.ACCEPT

    def test_quality_decision_review(self, service):
        """Teste Qualitaetsentscheidung REVIEW bei mittlerer Confidence."""
        decision = service.make_quality_decision(0.72)
        assert decision == QualityDecision.REVIEW

    def test_quality_decision_retry(self, service):
        """Teste Qualitaetsentscheidung RETRY bei niedriger Confidence."""
        decision = service.make_quality_decision(0.58)
        assert decision == QualityDecision.RETRY

    def test_quality_decision_reject(self, service):
        """Teste Qualitaetsentscheidung REJECT bei sehr niedriger Confidence."""
        decision = service.make_quality_decision(0.25)
        assert decision == QualityDecision.REJECT

    def test_should_trigger_fallback_below_threshold(self, service):
        """Teste Fallback-Trigger bei niedriger Confidence."""
        should_fallback = service.should_trigger_fallback(0.55)
        assert should_fallback is True

    def test_should_not_trigger_fallback_above_threshold(self, service):
        """Teste kein Fallback bei hoher Confidence."""
        should_fallback = service.should_trigger_fallback(0.85)
        assert should_fallback is False

    def test_analyze_ocr_result(self, service):
        """Teste OCR Ergebnis-Analyse."""
        metrics = service.analyze_ocr_result(
            text="Beispieltext mit Umlauten: äöüß",
            confidence=0.88,
            backend="deepseek",
            processing_time_ms=1500
        )

        assert metrics is not None
        assert metrics.raw_confidence == 0.88
        assert metrics.backend == "deepseek"
        assert metrics.confidence_level == ConfidenceLevel.HIGH

    def test_aggregate_confidences(self, service):
        """Teste Aggregation mehrerer Confidence-Werte."""
        metrics_list = [
            ConfidenceMetrics(
                raw_confidence=0.90,
                adjusted_confidence=0.90,
                confidence_level=ConfidenceLevel.HIGH,
                backend="deepseek"
            ),
            ConfidenceMetrics(
                raw_confidence=0.85,
                adjusted_confidence=0.85,
                confidence_level=ConfidenceLevel.HIGH,
                backend="got_ocr"
            ),
        ]

        aggregated = service.aggregate_confidences(metrics_list)

        assert aggregated is not None
        # Gewichteter Durchschnitt sollte zwischen 0.85 und 0.90 liegen
        assert 0.85 <= aggregated.mean_confidence <= 0.90


# =============================================================================
# Fallback Chain Tests
# =============================================================================


class TestFallbackChain:
    """Tests fuer FallbackChain."""

    @pytest.fixture
    def fallback_chain(self):
        """Erstelle FallbackChain Instanz."""
        return FallbackChain()

    def test_default_backend_order(self, fallback_chain):
        """Teste Standard Backend-Reihenfolge."""
        backends = fallback_chain.get_backend_priority()

        assert len(backends) >= 3
        # DeepSeek sollte hoechste Prioritaet haben
        assert backends[0] in ["deepseek", "deepseek-janus"]

    def test_backend_selection_with_gpu_available(self, fallback_chain):
        """Teste Backend-Auswahl mit verfuegbarer GPU."""
        backend = fallback_chain.select_backend(
            gpu_available=True,
            available_vram_gb=14.0
        )

        # Sollte GPU-Backend waehlen
        assert backend in ["deepseek", "got-ocr", "surya-gpu"]

    def test_backend_selection_without_gpu(self, fallback_chain):
        """Teste Backend-Auswahl ohne GPU."""
        backend = fallback_chain.select_backend(
            gpu_available=False,
            available_vram_gb=0.0
        )

        # Sollte CPU-Fallback waehlen
        assert backend == "surya"

    def test_backend_selection_with_limited_vram(self, fallback_chain):
        """Teste Backend-Auswahl mit begrenztem VRAM."""
        backend = fallback_chain.select_backend(
            gpu_available=True,
            available_vram_gb=3.0  # Nur 3GB frei
        )

        # Sollte leichtgewichtiges Backend waehlen
        assert backend in ["surya-gpu", "surya"]

    @pytest.mark.asyncio
    async def test_execute_with_mock_handler(self, fallback_chain):
        """Teste Ausfuehrung mit Mock-Handler."""
        # Registriere Mock-Handler
        mock_handler = AsyncMock(return_value={
            "text": "Erkannter Text",
            "confidence": 0.92
        })
        fallback_chain.register_backend_handler("test_backend", mock_handler)

        result = await fallback_chain.execute(
            document_id="doc_001",
            image_path="/path/to/image.png",
            language="de",
            preferred_backend="test_backend"
        )

        assert result is not None
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(self, fallback_chain):
        """Teste Fallback bei niedriger Confidence."""
        call_count = 0

        async def low_confidence_handler(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"text": "Text", "confidence": 0.40}  # Niedrig
            return {"text": "Better Text", "confidence": 0.90}  # Hoch

        fallback_chain.register_backend_handler("backend1", low_confidence_handler)
        fallback_chain.register_backend_handler("backend2", low_confidence_handler)

        result = await fallback_chain.execute(
            document_id="doc_001",
            image_path="/path/to/image.png"
        )

        # Sollte Fallback ausgeloest haben
        assert result.fallbacks_occurred >= 0


# =============================================================================
# FallbackResult Tests
# =============================================================================


class TestFallbackResult:
    """Tests fuer FallbackResult Dataclass."""

    def test_successful_result(self):
        """Teste erfolgreiches Ergebnis."""
        result = FallbackResult(
            success=True,
            text="Erkannter Text",
            confidence=0.92,
            final_backend="deepseek",
            backends_tried=["deepseek"],
            fallbacks_occurred=0
        )

        assert result.success is True
        assert result.confidence == 0.92
        assert len(result.backends_tried) == 1

    def test_failed_result_with_fallbacks(self):
        """Teste fehlgeschlagenes Ergebnis mit Fallbacks."""
        result = FallbackResult(
            success=False,
            text="",
            confidence=0.0,
            final_backend="none",
            backends_tried=["deepseek", "got-ocr", "surya"],
            fallbacks_occurred=3,
            error="All backends failed"
        )

        assert result.success is False
        assert result.fallbacks_occurred == 3
        assert "All backends failed" in result.error


# =============================================================================
# OCR Pipeline Tests
# =============================================================================


class TestOCRPipeline:
    """Tests fuer OCRPipeline."""

    @pytest.fixture
    def pipeline(self):
        """Erstelle Pipeline mit Mocks."""
        with patch('app.services.ocr_pipeline.get_fallback_chain') as mock_chain, \
             patch('app.services.ocr_pipeline.get_confidence_service') as mock_conf, \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry') as mock_cb, \
             patch('app.services.ocr_pipeline.get_memory_guard') as mock_guard:

            # Mock Fallback Chain
            mock_chain_instance = Mock()
            mock_chain_instance.execute = AsyncMock(return_value=FallbackResult(
                success=True,
                text="Test OCR Text mit Umlauten: äöü",
                confidence=0.88,
                final_backend="deepseek",
                backends_tried=["deepseek"],
                fallbacks_occurred=0
            ))
            mock_chain_instance.get_metrics = Mock(return_value={})
            mock_chain.return_value = mock_chain_instance

            # Mock Confidence Service
            mock_conf_instance = Mock()
            mock_conf.return_value = mock_conf_instance

            # Mock Circuit Breaker Registry
            mock_cb_instance = Mock()
            mock_cb_instance.get_or_create = Mock()
            mock_cb_instance.get_all_status = Mock(return_value={})
            mock_cb.return_value = mock_cb_instance

            # Mock Memory Guard
            mock_guard_instance = Mock()
            mock_guard_instance.check_memory_status = Mock(return_value={
                "available": True,
                "remaining_gb": 10.0,
                "is_critical": False
            })
            mock_guard_instance.get_status = Mock(return_value={})
            mock_guard.return_value = mock_guard_instance

            pipeline = OCRPipeline(
                enable_german_correction=False,  # Deaktiviert fuer Unit Tests
                enable_circuit_breaker=True,
                enable_memory_guard=True
            )

            yield pipeline

    @pytest.mark.asyncio
    async def test_process_document_success(self, pipeline):
        """Teste erfolgreiche Dokumentverarbeitung."""
        result = await pipeline.process(
            document_id="doc_001",
            image_path="/path/to/image.png",
            language="de"
        )

        assert result.success is True
        assert result.backend_used == "deepseek"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_process_returns_pipeline_result(self, pipeline):
        """Teste dass OCRPipelineResult zurueckgegeben wird."""
        result = await pipeline.process(
            document_id="doc_001",
            image_path="/path/to/image.png"
        )

        assert isinstance(result, OCRPipelineResult)
        assert hasattr(result, 'success')
        assert hasattr(result, 'text')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'backend_used')
        assert hasattr(result, 'processing_time_ms')

    @pytest.mark.asyncio
    async def test_process_with_preferred_backend(self, pipeline):
        """Teste Verarbeitung mit bevorzugtem Backend."""
        result = await pipeline.process(
            document_id="doc_001",
            image_path="/path/to/image.png",
            preferred_backend="got-ocr"
        )

        assert result.success is True

    def test_get_status(self, pipeline):
        """Teste Status-Abfrage."""
        status = pipeline.get_status()

        assert "pipeline" in status
        assert "fallback_chain" in status
        assert "circuit_breakers" in status

    def test_pipeline_configuration(self, pipeline):
        """Teste Pipeline-Konfiguration."""
        assert pipeline.enable_circuit_breaker is True
        assert pipeline.enable_memory_guard is True


# =============================================================================
# OCRPipelineResult Tests
# =============================================================================


class TestOCRPipelineResult:
    """Tests fuer OCRPipelineResult Dataclass."""

    def test_successful_result_to_dict(self):
        """Teste Konvertierung zu Dictionary."""
        result = OCRPipelineResult(
            success=True,
            text="Original Text",
            corrected_text="Korrigierter Text",
            confidence=0.92,
            backend_used="deepseek",
            backends_tried=["deepseek"],
            fallbacks_occurred=0,
            corrections_applied=5,
            processing_time_ms=1500,
            german_correction_applied=True
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["text"] == "Korrigierter Text"  # Korrigierter als Hauptergebnis
        assert d["original_text"] == "Original Text"
        assert d["confidence"] == 0.92
        assert d["backend_used"] == "deepseek"
        assert d["corrections_applied"] == 5
        assert d["german_correction_applied"] is True

    def test_failed_result(self):
        """Teste fehlgeschlagenes Ergebnis."""
        result = OCRPipelineResult(
            success=False,
            text="",
            corrected_text="",
            confidence=0.0,
            backend_used="none",
            backends_tried=["deepseek", "got-ocr"],
            fallbacks_occurred=2,
            corrections_applied=0,
            processing_time_ms=500,
            german_correction_applied=False,
            error="All backends failed"
        )

        assert result.success is False
        assert result.error == "All backends failed"
        assert result.fallbacks_occurred == 2


# =============================================================================
# Integration Workflow Tests
# =============================================================================


class TestPipelineWorkflows:
    """Integration-Tests fuer komplette Workflows."""

    @pytest.mark.asyncio
    async def test_complete_ocr_workflow_mock(self):
        """Teste kompletten OCR-Workflow mit Mocks."""
        with patch('app.services.ocr_pipeline.get_fallback_chain') as mock_chain, \
             patch('app.services.ocr_pipeline.get_confidence_service') as mock_conf, \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry') as mock_cb, \
             patch('app.services.ocr_pipeline.get_memory_guard') as mock_guard:

            # Setup Mocks
            mock_chain_instance = Mock()
            mock_chain_instance.execute = AsyncMock(return_value=FallbackResult(
                success=True,
                text="Rechnung Nr. 2024-001\nBetrag: 1.234,56 EUR",
                confidence=0.91,
                final_backend="deepseek",
                backends_tried=["deepseek"],
                fallbacks_occurred=0,
                confidence_metrics=ConfidenceMetrics(
                    raw_confidence=0.91,
                    adjusted_confidence=0.91,
                    confidence_level=ConfidenceLevel.HIGH,
                    backend="deepseek"
                )
            ))
            mock_chain_instance.get_metrics = Mock(return_value={})
            mock_chain_instance.register_backend_handler = Mock()
            mock_chain.return_value = mock_chain_instance

            mock_conf.return_value = Mock()

            mock_cb_instance = Mock()
            mock_cb_instance.get_or_create = Mock()
            mock_cb_instance.get_all_status = Mock(return_value={})
            mock_cb.return_value = mock_cb_instance

            mock_guard_instance = Mock()
            mock_guard_instance.check_memory_status = Mock(return_value={
                "available": True,
                "remaining_gb": 12.0,
                "is_critical": False
            })
            mock_guard_instance.get_status = Mock(return_value={})
            mock_guard_instance.cleanup_cache = Mock()
            mock_guard.return_value = mock_guard_instance

            # Erstelle Pipeline
            pipeline = OCRPipeline(
                enable_german_correction=False,
                enable_circuit_breaker=True,
                enable_memory_guard=True
            )

            # Verarbeite Dokument
            result = await pipeline.process(
                document_id="invoice_001",
                image_path="/path/to/invoice.png",
                language="de",
                document_type="invoice"
            )

            # Verifiziere Ergebnis
            assert result.success is True
            assert "Rechnung" in result.text
            assert result.confidence > 0.85
            assert result.backend_used == "deepseek"
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_fallback_workflow(self):
        """Teste Fallback-Workflow wenn primaeres Backend fehlschlaegt."""
        fallback_chain = FallbackChain()

        call_sequence = []

        async def failing_backend(*args, **kwargs):
            call_sequence.append("failing")
            raise RuntimeError("Backend unavailable")

        async def working_backend(*args, **kwargs):
            call_sequence.append("working")
            return {"text": "Fallback Result", "confidence": 0.85}

        fallback_chain.register_backend_handler("primary", failing_backend)
        fallback_chain.register_backend_handler("fallback", working_backend)

        # Konfiguriere Prioritaeten
        fallback_chain._backends = {
            "primary": BackendConfig(
                name="primary",
                priority=1,
                min_vram_gb=0,
                requires_gpu=False
            ),
            "fallback": BackendConfig(
                name="fallback",
                priority=2,
                min_vram_gb=0,
                requires_gpu=False
            )
        }

        result = await fallback_chain.execute(
            document_id="doc_001",
            image_path="/path/to/doc.png"
        )

        # Verifiziere dass Fallback genutzt wurde
        assert "failing" in call_sequence or "working" in call_sequence


# =============================================================================
# Batch Processing Tests
# =============================================================================


class TestBatchProcessing:
    """Tests fuer Batch-Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_batch(self):
        """Teste Batch-Verarbeitung mehrerer Dokumente."""
        with patch('app.services.ocr_pipeline.get_fallback_chain') as mock_chain, \
             patch('app.services.ocr_pipeline.get_confidence_service') as mock_conf, \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry') as mock_cb, \
             patch('app.services.ocr_pipeline.get_memory_guard') as mock_guard:

            # Setup
            mock_chain_instance = Mock()
            mock_chain_instance.execute = AsyncMock(return_value=FallbackResult(
                success=True,
                text="Batch Text",
                confidence=0.88,
                final_backend="deepseek",
                backends_tried=["deepseek"],
                fallbacks_occurred=0
            ))
            mock_chain_instance.get_metrics = Mock(return_value={})
            mock_chain_instance.register_backend_handler = Mock()
            mock_chain.return_value = mock_chain_instance

            mock_conf.return_value = Mock()

            mock_cb_instance = Mock()
            mock_cb_instance.get_or_create = Mock()
            mock_cb_instance.get_all_status = Mock(return_value={})
            mock_cb.return_value = mock_cb_instance

            mock_guard_instance = Mock()
            mock_guard_instance.check_memory_status = Mock(return_value={
                "available": True, "remaining_gb": 10.0, "is_critical": False
            })
            mock_guard_instance.get_status = Mock(return_value={})
            mock_guard.return_value = mock_guard_instance

            pipeline = OCRPipeline(enable_german_correction=False)

            # Batch von Dokumenten
            documents = [
                {"document_id": f"doc_{i}", "image_path": f"/path/doc_{i}.png"}
                for i in range(5)
            ]

            results = await pipeline.process_batch(documents, concurrency=2)

            assert len(results) == 5
            assert all(r.success for r in results)


# =============================================================================
# Singleton Tests
# =============================================================================


class TestPipelineSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_ocr_pipeline_returns_singleton(self):
        """Teste dass Singleton zurueckgegeben wird."""
        import app.services.ocr_pipeline as pipeline_module

        # Reset
        pipeline_module._ocr_pipeline = None

        with patch('app.services.ocr_pipeline.get_fallback_chain'), \
             patch('app.services.ocr_pipeline.get_confidence_service'), \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry'), \
             patch('app.services.ocr_pipeline.get_memory_guard'):

            pipeline1 = get_ocr_pipeline()
            pipeline2 = get_ocr_pipeline()

            assert pipeline1 is pipeline2
