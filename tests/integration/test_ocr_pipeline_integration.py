# -*- coding: utf-8 -*-
"""
Integration Tests fuer OCR Pipeline.

Testet die OCR-Pipeline-Bausteine inklusive:
- Fallback Chain
- Confidence Service
- Circuit Breaker Integration
- GPU Memory Guard

W3 (2026-06-12): Komplett auf die ECHTEN Vertraege modernisiert (28 Drift-
Failures). Die alte Fassung testete nie existierende APIs:
- ConfidenceService.determine_confidence_level/make_quality_decision ->
  real: classify_confidence / determine_quality_decision (Tuple-Rueckgabe)
- QualityDecision.REVIEW/RETRY -> real: REQUEST_REVIEW/RETRY_DIFFERENT_BACKEND
- ConfidenceMetrics(raw_confidence=...) -> real: 14-Feld-Dataclass aus
  analyze_ocr_result(confidence, confidence_details, backend)
- FallbackChain.select_backend/get_backend_priority -> real:
  get_enabled_backends(gpu_available, available_vram_gb)
- FallbackResult verlangt fallback_reasons + total_time_ms
- BackendConfig nutzt vram_gb (nicht min_vram_gb)
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

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
)
from app.services.fallback_chain import (
    FallbackChain,
    FallbackResult,
    BackendConfig,
)


def _fallback_result(**overrides) -> FallbackResult:
    """Baut ein gueltiges FallbackResult (echter Pflichtfeld-Satz)."""
    defaults = dict(
        success=True,
        text="Test OCR Text mit Umlauten: äöü",
        confidence=0.88,
        final_backend="deepseek",
        backends_tried=["deepseek"],
        fallbacks_occurred=0,
        fallback_reasons=[],
        total_time_ms=120,
    )
    defaults.update(overrides)
    return FallbackResult(**defaults)


# =============================================================================
# Confidence Service Tests
# =============================================================================


class TestConfidenceService:
    """Tests fuer ConfidenceService (echter Vertrag)."""

    @pytest.fixture
    def service(self) -> ConfidenceService:
        """Erstelle ConfidenceService Instanz."""
        return ConfidenceService()

    def test_classify_confidence_excellent(self, service) -> None:
        """Teste Confidence Level EXCELLENT (>= 0.95)."""
        assert service.classify_confidence(0.97) == ConfidenceLevel.EXCELLENT

    def test_classify_confidence_high(self, service) -> None:
        """Teste Confidence Level HIGH (>= 0.85)."""
        assert service.classify_confidence(0.88) == ConfidenceLevel.HIGH

    def test_classify_confidence_medium(self, service) -> None:
        """Teste Confidence Level MEDIUM (>= 0.70)."""
        assert service.classify_confidence(0.75) == ConfidenceLevel.MEDIUM

    def test_classify_confidence_low(self, service) -> None:
        """Teste Confidence Level LOW (>= 0.50)."""
        assert service.classify_confidence(0.55) == ConfidenceLevel.LOW

    def test_classify_confidence_very_low(self, service) -> None:
        """Teste Confidence Level VERY_LOW (< 0.50)."""
        assert service.classify_confidence(0.35) == ConfidenceLevel.VERY_LOW

    def test_quality_decision_accept(self, service) -> None:
        """ACCEPT bei hoher Confidence ohne Auffaelligkeiten."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.92, min_confidence=0.85, low_confidence_ratio=0.05
        )
        assert decision == QualityDecision.ACCEPT
        assert should_fallback is False
        assert reason is None

    def test_quality_decision_review(self, service) -> None:
        """REQUEST_REVIEW bei vielen niedrig-konfidenten Tokens."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.72, min_confidence=0.50, low_confidence_ratio=0.40
        )
        assert decision == QualityDecision.REQUEST_REVIEW
        assert should_fallback is False
        assert reason is not None and "Tokens" in reason

    def test_quality_decision_retry(self, service) -> None:
        """RETRY_DIFFERENT_BACKEND unter der Fallback-Schwelle (0.65)."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.58, min_confidence=0.50, low_confidence_ratio=0.10
        )
        assert decision == QualityDecision.RETRY_DIFFERENT_BACKEND
        assert should_fallback is True
        assert "Fallback-Schwelle" in (reason or "")

    def test_quality_decision_reject(self, service) -> None:
        """REJECT unter der Ablehnungsschwelle (0.30)."""
        decision, should_fallback, reason = service.determine_quality_decision(
            confidence=0.25, min_confidence=0.20, low_confidence_ratio=0.50
        )
        assert decision == QualityDecision.REJECT
        assert should_fallback is True
        assert "Ablehnungsschwelle" in (reason or "")

    def test_should_trigger_fallback_below_threshold(self, service) -> None:
        """Fallback-Trigger bei niedriger Confidence (via Metriken)."""
        metrics = service.analyze_ocr_result(confidence=0.55, backend="surya")
        should_fallback, reason = service.should_trigger_fallback(metrics)
        assert should_fallback is True
        assert reason  # deutscher Begruendungstext

    def test_should_not_trigger_fallback_above_threshold(self, service) -> None:
        """Kein Fallback bei hoher Confidence."""
        metrics = service.analyze_ocr_result(confidence=0.90, backend="surya")
        should_fallback, reason = service.should_trigger_fallback(metrics)
        assert should_fallback is False
        assert reason == ""

    def test_should_trigger_fallback_document_type_rule(self, service) -> None:
        """Dokumenttyp-Regel: Rechnungen brauchen >= 0.80."""
        metrics = service.analyze_ocr_result(confidence=0.75, backend="surya")
        should_fallback, reason = service.should_trigger_fallback(
            metrics, document_type="invoice"
        )
        assert should_fallback is True
        assert "invoice" in reason

    def test_analyze_ocr_result(self, service) -> None:
        """OCR-Ergebnis-Analyse liefert vollstaendige Metriken."""
        metrics = service.analyze_ocr_result(
            confidence=0.88,
            confidence_details={
                "mean_confidence": 0.88,
                "min_confidence": 0.70,
                "total_tokens": 100,
                "low_confidence_count": 5,
                "method": "token_logits",
                "token_confidences": [0.88, 0.90, 0.70, 0.95],
            },
            backend="deepseek",
        )

        assert metrics.overall_confidence == 0.88
        assert metrics.backend == "deepseek"
        assert metrics.confidence_level == ConfidenceLevel.HIGH
        assert metrics.quality_decision == QualityDecision.ACCEPT
        assert metrics.total_tokens == 100
        assert metrics.low_confidence_ratio == 0.05
        assert metrics.should_fallback is False

    def test_aggregate_confidences(self, service) -> None:
        """Aggregation mehrerer Backend-Ergebnisse (weighted_average)."""
        results = [
            {"backend": "deepseek-janus-pro", "confidence": 0.90},
            {"backend": "got-ocr-2.0", "confidence": 0.85},
        ]

        aggregated = service.aggregate_confidences(results)

        assert aggregated.backends_used == ["deepseek-janus-pro", "got-ocr-2.0"]
        # Gewichteter Durchschnitt liegt zwischen den Einzelwerten
        assert 0.85 <= aggregated.aggregated_confidence <= 0.90
        assert aggregated.best_backend == "deepseek-janus-pro"
        assert aggregated.worst_backend == "got-ocr-2.0"
        assert 0.0 <= aggregated.agreement_score <= 1.0


# =============================================================================
# Fallback Chain Tests
# =============================================================================


class TestFallbackChain:
    """Tests fuer FallbackChain (echter Vertrag)."""

    @pytest.fixture
    def fallback_chain(self) -> FallbackChain:
        """Erstelle FallbackChain Instanz (ohne Circuit Breaker)."""
        return FallbackChain(enable_circuit_breaker=False)

    def test_default_backend_order(self, fallback_chain) -> None:
        """Standard-Backends nach Prioritaet sortiert, DeepSeek zuerst."""
        backends = fallback_chain.get_enabled_backends(
            gpu_available=True, available_vram_gb=16.0
        )

        assert len(backends) >= 3
        assert backends[0].name == "deepseek-janus-pro"
        priorities = [b.priority for b in backends]
        assert priorities == sorted(priorities)

    def test_backend_selection_with_gpu_available(self, fallback_chain) -> None:
        """Mit GPU + viel VRAM ist das Top-Backend ein GPU-Backend."""
        backends = fallback_chain.get_enabled_backends(
            gpu_available=True, available_vram_gb=14.0
        )

        assert backends[0].requires_gpu is True
        assert backends[0].name in ["deepseek-janus-pro", "got-ocr-2.0"]

    def test_backend_selection_without_gpu(self, fallback_chain) -> None:
        """Ohne GPU bleibt nur der CPU-Fallback (surya)."""
        backends = fallback_chain.get_enabled_backends(
            gpu_available=False, available_vram_gb=0.0
        )

        assert [b.name for b in backends] == ["surya"]
        assert backends[0].requires_gpu is False

    def test_backend_selection_with_limited_vram(self, fallback_chain) -> None:
        """Mit nur 3 GB VRAM passen keine grossen GPU-Backends mehr."""
        backends = fallback_chain.get_enabled_backends(
            gpu_available=True, available_vram_gb=3.0
        )

        names = [b.name for b in backends]
        assert "deepseek-janus-pro" not in names
        assert "got-ocr-2.0" not in names
        assert "surya" in names  # CPU-Fallback immer dabei

    @pytest.mark.asyncio
    async def test_execute_with_mock_handler(self) -> None:
        """Ausfuehrung mit registriertem Mock-Handler."""
        chain = FallbackChain(
            backends=[
                BackendConfig(
                    name="test_backend",
                    priority=1,
                    requires_gpu=False,
                    vram_gb=0.0,
                    min_confidence_threshold=0.5,
                )
            ],
            enable_circuit_breaker=False,
        )
        # Echter Handler-Vertrag: dict MUSS success enthalten
        mock_handler = AsyncMock(return_value={
            "success": True,
            "text": "Erkannter Text",
            "confidence": 0.92,
        })
        chain.register_backend_handler("test_backend", mock_handler)

        result = await chain.execute(
            document_id="doc_001",
            image_path="/path/to/image.png",
            language="de",
            preferred_backend="test_backend",
            gpu_available=False,
        )

        assert result.success is True
        assert result.final_backend == "test_backend"
        assert result.text == "Erkannter Text"
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(self) -> None:
        """Fallback bei niedriger Confidence des ersten Backends."""
        chain = FallbackChain(
            backends=[
                BackendConfig(
                    name="backend1", priority=1, requires_gpu=False,
                    vram_gb=0.0, min_confidence_threshold=0.65,
                ),
                BackendConfig(
                    name="backend2", priority=2, requires_gpu=False,
                    vram_gb=0.0, min_confidence_threshold=0.65,
                ),
            ],
            enable_circuit_breaker=False,
        )

        async def low_confidence_handler(**kwargs):
            return {"success": True, "text": "Text", "confidence": 0.40}

        async def high_confidence_handler(**kwargs):
            return {"success": True, "text": "Better Text", "confidence": 0.90}

        chain.register_backend_handler("backend1", low_confidence_handler)
        chain.register_backend_handler("backend2", high_confidence_handler)

        result = await chain.execute(
            document_id="doc_001",
            image_path="/path/to/image.png",
            gpu_available=False,
        )

        # Confidence-Fallback: backend1 (0.40) -> backend2 (0.90)
        assert result.backends_tried == ["backend1", "backend2"]
        assert result.fallbacks_occurred >= 1
        assert result.final_backend == "backend2"
        assert result.success is True
        assert result.fallback_reasons[0]["reason"] == "low_confidence"


# =============================================================================
# FallbackResult Tests
# =============================================================================


class TestFallbackResult:
    """Tests fuer FallbackResult Dataclass."""

    def test_successful_result(self) -> None:
        """Teste erfolgreiches Ergebnis."""
        result = _fallback_result(confidence=0.92)

        assert result.success is True
        assert result.confidence == 0.92
        assert len(result.backends_tried) == 1
        assert result.to_dict()["confidence"] == 0.92

    def test_failed_result_with_fallbacks(self) -> None:
        """Teste fehlgeschlagenes Ergebnis mit Fallbacks."""
        result = _fallback_result(
            success=False,
            text="",
            confidence=0.0,
            final_backend="none",
            backends_tried=["deepseek", "got-ocr", "surya"],
            fallbacks_occurred=3,
            fallback_reasons=[
                {"backend": "deepseek", "reason": "low_confidence"},
                {"backend": "got-ocr", "reason": "backend_error"},
            ],
            error="All backends failed",
        )

        assert result.success is False
        assert result.fallbacks_occurred == 3
        assert "All backends failed" in result.error
        assert len(result.fallback_reasons) == 2


# =============================================================================
# OCR Pipeline Tests
# =============================================================================


def _make_pipeline_mocks():
    """Erstellt die Mock-Instanzen fuer die Pipeline-Abhaengigkeiten."""
    mock_chain_instance = Mock()
    mock_chain_instance.execute = AsyncMock(return_value=_fallback_result())
    mock_chain_instance.get_metrics = Mock(return_value={})
    mock_chain_instance.register_backend_handler = Mock()

    mock_conf_instance = Mock()

    mock_cb_instance = Mock()
    mock_cb_instance.get_or_create = Mock()
    mock_cb_instance.get_all_status = Mock(return_value={})

    mock_guard_instance = Mock()
    mock_guard_instance.check_memory_status = Mock(return_value={
        "available": True,
        "remaining_gb": 10.0,
        "is_critical": False,
    })
    mock_guard_instance.get_status = Mock(return_value={})
    mock_guard_instance.cleanup_cache = Mock()

    return mock_chain_instance, mock_conf_instance, mock_cb_instance, mock_guard_instance


def _minimal_pipeline(**overrides) -> OCRPipeline:
    """Pipeline mit allen Zusatz-Stufen deaktiviert (reine Kern-Pipeline)."""
    kwargs = dict(
        enable_german_correction=False,
        enable_circuit_breaker=True,
        enable_memory_guard=True,
        enable_historical_normalization=False,
        enable_entity_extraction=False,
        enable_structured_extraction=False,
        enable_preprocessing=False,
        enable_document_dna=False,
        enable_cross_validation=False,
        enable_confidence_fallback=False,
    )
    kwargs.update(overrides)
    return OCRPipeline(**kwargs)


class TestOCRPipeline:
    """Tests fuer OCRPipeline."""

    @pytest.fixture
    def pipeline(self):
        """Erstelle Pipeline mit Mocks."""
        mock_chain, mock_conf, mock_cb, mock_guard = _make_pipeline_mocks()
        with patch('app.services.ocr_pipeline.get_fallback_chain', return_value=mock_chain), \
             patch('app.services.ocr_pipeline.get_confidence_service', return_value=mock_conf), \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry', return_value=mock_cb), \
             patch('app.services.ocr_pipeline.get_memory_guard', return_value=mock_guard):
            yield _minimal_pipeline()

    @pytest.mark.asyncio
    async def test_process_document_success(self, pipeline) -> None:
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
    async def test_process_returns_pipeline_result(self, pipeline) -> None:
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
    async def test_process_with_preferred_backend(self, pipeline) -> None:
        """Teste Verarbeitung mit bevorzugtem Backend."""
        result = await pipeline.process(
            document_id="doc_001",
            image_path="/path/to/image.png",
            preferred_backend="got-ocr"
        )

        assert result.success is True
        # preferred_backend wird an die Fallback Chain durchgereicht
        call_kwargs = pipeline.fallback_chain.execute.call_args.kwargs
        assert call_kwargs.get("preferred_backend") == "got-ocr"

    def test_get_status(self, pipeline) -> None:
        """Teste Status-Abfrage."""
        status = pipeline.get_status()

        assert "pipeline" in status
        assert "fallback_chain" in status
        assert "circuit_breakers" in status
        assert status["pipeline"]["circuit_breaker_enabled"] is True

    def test_pipeline_configuration(self, pipeline) -> None:
        """Teste Pipeline-Konfiguration."""
        assert pipeline.enable_circuit_breaker is True
        assert pipeline.enable_memory_guard is True
        assert pipeline.enable_german_correction is False


# =============================================================================
# OCRPipelineResult Tests
# =============================================================================


class TestOCRPipelineResult:
    """Tests fuer OCRPipelineResult Dataclass."""

    def test_successful_result_to_dict(self) -> None:
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

    def test_failed_result(self) -> None:
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
    async def test_complete_ocr_workflow_mock(self) -> None:
        """Teste kompletten OCR-Workflow mit Mocks."""
        mock_chain, mock_conf, mock_cb, mock_guard = _make_pipeline_mocks()
        mock_chain.execute = AsyncMock(return_value=_fallback_result(
            text="Rechnung Nr. 2024-001\nBetrag: 1.234,56 EUR",
            confidence=0.91,
        ))

        with patch('app.services.ocr_pipeline.get_fallback_chain', return_value=mock_chain), \
             patch('app.services.ocr_pipeline.get_confidence_service', return_value=mock_conf), \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry', return_value=mock_cb), \
             patch('app.services.ocr_pipeline.get_memory_guard', return_value=mock_guard):

            pipeline = _minimal_pipeline()

            result = await pipeline.process(
                document_id="invoice_001",
                image_path="/path/to/invoice.png",
                language="de",
                document_type="invoice"
            )

        assert result.success is True
        assert "Rechnung" in result.text
        assert result.confidence > 0.85
        assert result.backend_used == "deepseek"
        assert result.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_fallback_workflow(self) -> None:
        """Teste Fallback-Workflow wenn primaeres Backend fehlschlaegt."""
        chain = FallbackChain(
            backends=[
                BackendConfig(
                    name="primary", priority=1, requires_gpu=False,
                    vram_gb=0.0, min_confidence_threshold=0.5,
                ),
                BackendConfig(
                    name="fallback", priority=2, requires_gpu=False,
                    vram_gb=0.0, min_confidence_threshold=0.5,
                ),
            ],
            enable_circuit_breaker=False,
        )

        call_sequence = []

        async def failing_backend(**kwargs):
            call_sequence.append("failing")
            raise RuntimeError("Backend unavailable")

        async def working_backend(**kwargs):
            call_sequence.append("working")
            return {"success": True, "text": "Fallback Result", "confidence": 0.85}

        chain.register_backend_handler("primary", failing_backend)
        chain.register_backend_handler("fallback", working_backend)

        result = await chain.execute(
            document_id="doc_001",
            image_path="/path/to/doc.png",
            gpu_available=False,
        )

        # Primaeres Backend versucht, dann Fallback genutzt
        assert call_sequence == ["failing", "working"]
        assert result.success is True
        assert result.final_backend == "fallback"
        assert result.fallbacks_occurred >= 1
        assert result.fallback_reasons  # Grund dokumentiert


# =============================================================================
# Batch Processing Tests
# =============================================================================


class TestBatchProcessing:
    """Tests fuer Batch-Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_batch(self) -> None:
        """Teste Batch-Verarbeitung mehrerer Dokumente."""
        mock_chain, mock_conf, mock_cb, mock_guard = _make_pipeline_mocks()
        mock_chain.execute = AsyncMock(return_value=_fallback_result(
            text="Batch Text",
        ))

        with patch('app.services.ocr_pipeline.get_fallback_chain', return_value=mock_chain), \
             patch('app.services.ocr_pipeline.get_confidence_service', return_value=mock_conf), \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry', return_value=mock_cb), \
             patch('app.services.ocr_pipeline.get_memory_guard', return_value=mock_guard):

            pipeline = _minimal_pipeline()

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

    def test_get_ocr_pipeline_returns_singleton(self) -> None:
        """Teste dass Singleton zurueckgegeben wird."""
        import app.services.ocr_pipeline as pipeline_module

        # Reset
        pipeline_module._ocr_pipeline = None

        mock_chain, mock_conf, mock_cb, mock_guard = _make_pipeline_mocks()
        with patch('app.services.ocr_pipeline.get_fallback_chain', return_value=mock_chain), \
             patch('app.services.ocr_pipeline.get_confidence_service', return_value=mock_conf), \
             patch('app.services.ocr_pipeline.get_circuit_breaker_registry', return_value=mock_cb), \
             patch('app.services.ocr_pipeline.get_memory_guard', return_value=mock_guard):

            pipeline1 = get_ocr_pipeline()
            pipeline2 = get_ocr_pipeline()

            assert pipeline1 is pipeline2

        # Aufräumen: globalen Singleton zuruecksetzen (Mock nicht leaken)
        pipeline_module._ocr_pipeline = None
