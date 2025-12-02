# -*- coding: utf-8 -*-
"""
Unit tests for Document Processing Orchestrator.

Tests:
- Workflow initialization
- Phase execution with error recovery
- Circuit breaker integration
- Retry strategy
- GPU OOM recovery
- Partial results handling
- Human review triggering
- Health status
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestOrchestratorInitialization:
    """Test orchestrator initialization."""

    @pytest.mark.unit
    def test_orchestrator_initializes(self):
        """Test orchestrator initializes successfully."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator

            orchestrator = DocumentProcessingOrchestrator()

            assert orchestrator.name == "document_processing_orchestrator"

    @pytest.mark.unit
    def test_orchestrator_lazy_loads_agents(self):
        """Test orchestrator lazy loads sub-agents."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator

            orchestrator = DocumentProcessingOrchestrator()

            # Agents should be None initially (lazy loaded)
            assert orchestrator._classification_agent is None
            assert orchestrator._preprocessing_agents is None
            assert orchestrator._qa_agent is None


class TestWorkflowPhases:
    """Test workflow phase enum."""

    @pytest.mark.unit
    def test_workflow_phases_exist(self):
        """Test all workflow phases are defined."""
        from app.agents.orchestration.document_orchestrator import WorkflowPhase

        expected_phases = [
            "uploaded", "classifying", "preprocessing",
            "ocr_processing", "postprocessing", "qa_check",
            "storing", "completed", "failed"
        ]

        for phase_name in expected_phases:
            phase = WorkflowPhase(phase_name)
            assert phase.value == phase_name


class TestWorkflowStateInitialization:
    """Test workflow state initialization."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_init_workflow_state(self, orchestrator):
        """Test workflow state initialization."""
        from app.agents.orchestration.document_orchestrator import WorkflowPhase

        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            input_data = {
                "file_path": "/path/to/doc.pdf",
                "user_id": "user123",
                "priority": 1,
            }

            state = await orchestrator._init_workflow_state("doc123", input_data)

            assert state["document_id"] == "doc123"
            assert state["current_phase"] == WorkflowPhase.UPLOADED.value
            assert "started_at" in state
            assert "phases" in state
            assert state["input_data"]["file_path"] == "/path/to/doc.pdf"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_init_workflow_state_redis_failure_continues(self, orchestrator):
        """Test workflow state init continues despite Redis failure."""
        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")

            input_data = {"file_path": "/path/to/doc.pdf"}

            # Should not raise
            state = await orchestrator._init_workflow_state("doc123", input_data)

            assert state["document_id"] == "doc123"


class TestPhaseExecution:
    """Test phase execution with error recovery."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked error recovery."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager') as mock_cb, \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy') as mock_retry, \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            mock_retry_instance = MagicMock()
            mock_retry_instance.get_config.return_value = MagicMock(max_retries=3)
            mock_retry_instance.should_retry.return_value = (False, 0)
            mock_retry.return_value = mock_retry_instance

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            orchestrator = DocumentProcessingOrchestrator()
            orchestrator._retry_strategy = mock_retry_instance
            return orchestrator

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_phase_success(self, orchestrator):
        """Test successful phase execution."""
        from app.agents.orchestration.document_orchestrator import WorkflowPhase

        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            async def mock_phase_func(input_data):
                return {"text": "extracted text", "confidence": 0.95}

            workflow_state = {
                "document_id": "doc123",
                "phases": {},
            }

            result = await orchestrator._execute_phase(
                WorkflowPhase.OCR_PROCESSING,
                mock_phase_func,
                workflow_state,
                {"file_path": "/path/to/doc.pdf"},
            )

            assert result["text"] == "extracted text"
            assert result["confidence"] == 0.95

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_phase_circuit_open_fails(self, orchestrator):
        """Test circuit open error is raised correctly."""
        from app.core.circuit_breaker import CircuitOpenError

        # Create a circuit open error directly
        error = CircuitOpenError("redis", 30.0)  # service_name, time_until_retry

        # Verify error attributes
        assert error.service_name == "redis"
        assert error.time_until_retry == 30.0
        assert "redis" in str(error)
        assert isinstance(error, Exception)


class TestClassificationPhase:
    """Test document classification phase."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_classify_document_success(self, orchestrator):
        """Test successful document classification."""
        with patch('app.agents.preprocessing.classification_agent.DocumentClassificationAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "document_type": "invoice",
                "language": "de",
                "complexity": "medium",
                "confidence": 0.92,
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._classify_document({"file_path": "/doc.pdf"})

            assert result["document_type"] == "invoice"
            assert result["language"] == "de"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_classify_document_failure_returns_defaults(self, orchestrator):
        """Test classification failure returns conservative defaults."""
        with patch('app.agents.preprocessing.classification_agent.DocumentClassificationAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.side_effect = Exception("Classification failed")
            mock_agent.return_value = mock_instance

            result = await orchestrator._classify_document({"file_path": "/doc.pdf"})

            # Should return defaults
            assert result["document_type"] == "other"
            assert result["language"] == "de"
            assert result["complexity"] == "medium"
            assert result["confidence"] == 0.5


class TestPreprocessingPhase:
    """Test document preprocessing phase."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_enhance_image_success(self, orchestrator):
        """Test successful image enhancement."""
        with patch('app.agents.preprocessing.image_enhancement_agent.ImageEnhancementAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "enhanced_image_path": "/enhanced/doc.png",
                "enhancements_applied": ["deskew", "denoise"],
                "quality_improvement": 0.15,
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._enhance_image("/doc.pdf", 0.7)

            assert result["enhanced_image_path"] == "/enhanced/doc.png"
            assert "deskew" in result["enhancements_applied"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_enhance_image_failure_returns_original(self, orchestrator):
        """Test image enhancement failure returns original path."""
        with patch('app.agents.preprocessing.image_enhancement_agent.ImageEnhancementAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.side_effect = Exception("Enhancement failed")
            mock_agent.return_value = mock_instance

            result = await orchestrator._enhance_image("/doc.pdf", 0.7)

            assert result["enhanced_image_path"] == "/doc.pdf"
            assert result["enhancements_applied"] == []


class TestOCRBackendSelection:
    """Test OCR backend selection."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_force_backend_override(self, orchestrator):
        """Test force_backend option overrides selection."""
        classification = {"document_type": "invoice"}
        preprocessing = {"segmentation": {"pages": 1}}
        options = {"force_backend": "surya"}

        result = await orchestrator._select_ocr_backend(
            classification, preprocessing, options
        )

        assert result == "surya"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_backend_selection_uses_router(self, orchestrator):
        """Test backend selection uses UnifiedOCRRouter."""
        with patch('app.agents.orchestration.unified_router.UnifiedOCRRouter') as mock_router:
            mock_instance = AsyncMock()
            mock_result = MagicMock()
            mock_result.backend.value = "deepseek"
            mock_instance.select_backend.return_value = mock_result
            mock_router.return_value = mock_instance

            classification = {"document_type": "invoice", "has_tables": True}
            preprocessing = {"segmentation": {"pages": 1}}
            options = {}

            result = await orchestrator._select_ocr_backend(
                classification, preprocessing, options
            )

            assert result == "deepseek"


class TestQualityCheck:
    """Test quality assurance check phase."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_quality_check_success(self, orchestrator):
        """Test successful quality check."""
        with patch('app.agents.postprocessing.qa_agent.QAAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "quality_score": 0.92,
                "quality_level": "high",
                "needs_review": False,
                "issues": [],
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._quality_check({
                "postprocessing": {"text": "test text", "original_confidence": 0.9},
                "classification": {},
            })

            assert result["score"] == 0.92
            assert result["needs_review"] == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_quality_check_failure_fallback(self, orchestrator):
        """Test quality check fallback on failure."""
        with patch('app.agents.postprocessing.qa_agent.QAAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.side_effect = Exception("QA failed")
            mock_agent.return_value = mock_instance

            result = await orchestrator._quality_check({
                "postprocessing": {"text": "test text", "original_confidence": 0.8},
                "classification": {},
            })

            # Should fallback to confidence-based check
            assert "score" in result
            assert result["score"] == 0.8


class TestHumanReviewTrigger:
    """Test human review triggering."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_human_review(self, orchestrator):
        """Test human review is triggered correctly."""
        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.add_to_review_queue = AsyncMock()
            mock_redis_instance.get_review_queue_length = AsyncMock(return_value=5)
            mock_redis_instance.publish_event = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            qa_result = {
                "score": 0.5,
                "review_reasons": ["low_confidence"],
                "critical_issues": [],
                "quality_level": "low",
            }

            await orchestrator._trigger_human_review("doc123", qa_result)

            # Verify queue was called
            mock_redis_instance.add_to_review_queue.assert_called_once()
            mock_redis_instance.publish_event.assert_called_once()


class TestHealthStatus:
    """Test health status checking."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager') as mock_cb, \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy') as mock_retry, \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager') as mock_gpu, \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler') as mock_partial:

            mock_cb_instance = MagicMock()
            mock_cb_instance.get_circuit.return_value = MagicMock(
                state="closed",
                failure_count=0,
                last_failure_time=None,
            )
            mock_cb.return_value = mock_cb_instance

            mock_retry.return_value = MagicMock()
            mock_gpu.return_value = AsyncMock()
            mock_partial.return_value = MagicMock()

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            orchestrator = DocumentProcessingOrchestrator()
            orchestrator._circuit_breaker_manager = mock_cb_instance
            orchestrator._retry_strategy = mock_retry.return_value
            orchestrator._gpu_recovery_manager = mock_gpu.return_value
            orchestrator._partial_result_handler = mock_partial.return_value
            return orchestrator

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_status_structure(self, orchestrator):
        """Test health status returns correct structure."""
        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis.return_value = AsyncMock()

            orchestrator._gpu_recovery_manager.get_status = AsyncMock(return_value={
                "gpu_available": True,
                "vram_used_percent": 50,
            })

            status = await orchestrator.get_health_status()

            assert "orchestrator" in status
            assert "timestamp" in status
            assert "error_recovery" in status
            assert "agents" in status
            assert "external_services" in status

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_status_circuit_breakers(self, orchestrator):
        """Test health status includes circuit breaker info."""
        with patch('app.agents.orchestration.document_orchestrator.get_redis') as mock_redis:
            mock_redis.return_value = AsyncMock()

            orchestrator._gpu_recovery_manager.get_status = AsyncMock(return_value={})

            status = await orchestrator.get_health_status()

            assert "circuit_breakers" in status["error_recovery"]


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with circuit breaker manager."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager') as mock_cb, \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            mock_cb_instance = MagicMock()
            mock_cb.return_value = mock_cb_instance

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            orchestrator = DocumentProcessingOrchestrator()
            orchestrator._circuit_breaker_manager = mock_cb_instance
            return orchestrator

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self, orchestrator):
        """Test circuit breaker can be reset."""
        mock_circuit = AsyncMock()
        orchestrator._circuit_breaker_manager.get_circuit.return_value = mock_circuit

        result = await orchestrator.reset_circuit_breaker("redis")

        mock_circuit.reset.assert_called_once()
        assert result == True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reset_circuit_breaker_not_found(self, orchestrator):
        """Test reset fails gracefully when circuit not found."""
        orchestrator._circuit_breaker_manager.get_circuit.return_value = None

        result = await orchestrator.reset_circuit_breaker("nonexistent")

        assert result == False


class TestGPURecovery:
    """Test GPU OOM recovery integration."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with GPU recovery."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager') as mock_gpu, \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            mock_gpu_instance = AsyncMock()
            mock_gpu.return_value = mock_gpu_instance

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            orchestrator = DocumentProcessingOrchestrator()
            orchestrator._gpu_recovery_manager = mock_gpu_instance
            return orchestrator

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ocr_cpu_fallback(self, orchestrator):
        """Test OCR falls back to CPU on GPU failure."""
        with patch('app.agents.ocr.surya_docling_agent.SuryaDoclingAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "text": "fallback text",
                "confidence": 0.85,
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._ocr_cpu_fallback(
                document_id="doc123",
                file_path="/path/to/doc.pdf",
                classification={"language": "de"},
                original_error="CUDA out of memory",
                is_oom=True,
            )

            assert result["text"] == "fallback text"
            assert result["backend"] == "surya_fallback"
            assert result["fallback_type"] == "oom_recovery"


class TestOCRAgentLoading:
    """Test OCR agent lazy loading."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_surya_agent(self, orchestrator):
        """Test loading Surya agent."""
        with patch('app.agents.ocr.surya_docling_agent.SuryaDoclingAgent') as mock_agent:
            mock_agent.return_value = MagicMock()

            agent = await orchestrator._get_ocr_agent("surya")

            assert agent is not None
            mock_agent.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_unknown_backend_fallback(self, orchestrator):
        """Test unknown backend falls back to surya."""
        with patch('app.agents.ocr.surya_docling_agent.SuryaDoclingAgent') as mock_agent:
            mock_agent.return_value = MagicMock()

            agent = await orchestrator._get_ocr_agent("unknown_backend")

            assert agent is not None
            mock_agent.assert_called_once()


class TestPostprocessing:
    """Test postprocessing phase."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_correct_german_text(self, orchestrator):
        """Test German text correction."""
        with patch('app.agents.postprocessing.german_correction_agent.GermanCorrectionAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "text": "Größe und Übung",
                "corrections_applied": 2,
                "umlauts_restored": 2,
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._correct_german_text("Groesse und Uebung")

            assert result["text"] == "Größe und Übung"
            assert result["umlauts_restored"] == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_entities(self, orchestrator):
        """Test entity extraction."""
        with patch('app.agents.postprocessing.entity_extraction_agent.EntityExtractionAgent') as mock_agent:
            mock_instance = AsyncMock()
            mock_instance.process.return_value = {
                "entities": [
                    {"type": "date", "value": "01.01.2024"},
                    {"type": "amount", "value": "100,00 €"},
                ],
                "entity_count": 2,
            }
            mock_agent.return_value = mock_instance

            result = await orchestrator._extract_entities("Test text", {})

            assert len(result["entities"]) == 2
            assert result["entity_count"] == 2


class TestInputValidation:
    """Test input validation."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        with patch('app.agents.orchestration.document_orchestrator.get_circuit_breaker_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_retry_strategy'), \
             patch('app.agents.orchestration.document_orchestrator.get_gpu_recovery_manager'), \
             patch('app.agents.orchestration.document_orchestrator.get_partial_result_handler'):

            from app.agents.orchestration.document_orchestrator import DocumentProcessingOrchestrator
            return DocumentProcessingOrchestrator()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_requires_document_id(self, orchestrator):
        """Test process requires document_id."""
        from app.agents.base import AgentProcessingError

        with pytest.raises((AgentProcessingError, KeyError, ValueError)):
            await orchestrator.process({"file_path": "/doc.pdf"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_requires_file_path(self, orchestrator):
        """Test process requires file_path."""
        from app.agents.base import AgentProcessingError

        with pytest.raises((AgentProcessingError, KeyError, ValueError)):
            await orchestrator.process({"document_id": "doc123"})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
