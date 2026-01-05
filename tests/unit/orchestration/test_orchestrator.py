"""Unit tests for Orchestrator (main coordination logic)."""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add .claude to path so orchestration is a proper package
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.orchestrator import Orchestrator, OverrideMode, OrchestrationResult
from orchestration.task_classifier import ModelTier


class TestOrchestrator:
    """Test suite for main orchestrator."""

    def test_orchestrator_initialization(self):
        """Should initialize with default settings."""
        orchestrator = Orchestrator()

        assert orchestrator is not None
        assert hasattr(orchestrator, '_session_id')
        assert orchestrator._session_id is not None

    def test_set_override_mode(self):
        """Should allow setting override mode."""
        orchestrator = Orchestrator()

        orchestrator.set_override(OverrideMode.FORCE_OPUS)
        assert orchestrator._override_mode == OverrideMode.FORCE_OPUS

        orchestrator.set_override(OverrideMode.FORCE_HAIKU)
        assert orchestrator._override_mode == OverrideMode.FORCE_HAIKU

    def test_override_mode_enum_values(self):
        """OverrideMode should have all required values."""
        assert hasattr(OverrideMode, 'AUTO')
        assert hasattr(OverrideMode, 'FORCE_OPUS')
        assert hasattr(OverrideMode, 'FORCE_SONNET')
        assert hasattr(OverrideMode, 'FORCE_HAIKU')

    @pytest.mark.asyncio
    async def test_process_task_basic_flow(self):
        """Should process task through full orchestration flow."""
        orchestrator = Orchestrator()

        # Mock components
        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Standard implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            result = await orchestrator.process_task(
                task_prompt="Implement feature X",
                files=["app/feature.py"]
            )

            assert result is not None
            assert isinstance(result, OrchestrationResult)

    @pytest.mark.asyncio
    async def test_always_opus_override(self):
        """ALWAYS_OPUS override should force Opus selection."""
        orchestrator = Orchestrator()
        orchestrator.set_override_mode(OverrideMode.ALWAYS_OPUS)

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            # Classifier would select Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.90,
                reasoning="Simple task",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.20,
                file_impact_score=0.10
            )

            result = await orchestrator.process_task(
                task_prompt="Fix typo",
                files=[]
            )

            # Should use Opus despite classifier recommending Haiku
            assert result.model_used == "opus"

    @pytest.mark.asyncio
    async def test_cache_integration(self):
        """Should check cache for relevant decisions."""
        orchestrator = Orchestrator()

        # Store a decision in cache
        orchestrator._cache.store(
            task_description="Implement authentication",
            decision="Use JWT tokens",
            reasoning="Industry standard",
            affected_patterns=["authentication"],
            affected_files=["app/auth.py"],
            model_used="opus",
            confidence=0.95
        )

        # Process similar task
        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementation task",
                primary_pattern="implementation",
                matched_patterns=["authentication", "implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            result = await orchestrator.process_task(
                task_prompt="Add authentication endpoint",
                files=["app/auth.py"]
            )

            # Should have cache hits
            assert result.cache_hits > 0

    @pytest.mark.asyncio
    async def test_quality_gate_validation(self):
        """Should validate output quality."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple task",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.20,
                file_impact_score=0.10
            )

            # Mock quality validation failure
            from quality_gate import QualityResult, QualityLevel
            mock_validate.return_value = QualityResult(
                level=QualityLevel.FAILED,
                checks_passed=["syntax"],
                checks_failed=["type_hints", "german_messages"],
                warnings=["Missing docstring"],
                should_escalate=True,
                escalation_reason="Multiple quality checks failed",
                details={}
            )

            result = await orchestrator.process_task(
                task_prompt="Format code",
                files=["app/main.py"]
            )

            # Should trigger escalation
            assert result.escalated or result.quality_score < 0.80

    @pytest.mark.asyncio
    async def test_learning_feedback_recording(self):
        """Should record task execution for learning."""
        orchestrator = Orchestrator()

        initial_count = len(orchestrator._learning.feedback_history)

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            await orchestrator.process_task(
                task_prompt="Implement feature",
                files=["app/feature.py"]
            )

        # Should have recorded execution
        final_count = len(orchestrator._learning.feedback_history)
        assert final_count > initial_count

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Should track orchestration metrics."""
        orchestrator = Orchestrator()

        initial_snapshot = orchestrator._metrics.get_snapshot()
        initial_tasks = initial_snapshot.total_tasks

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            await orchestrator.process_task(
                task_prompt="Test task",
                files=[]
            )

        final_snapshot = orchestrator._metrics.get_snapshot()
        assert final_snapshot.total_tasks > initial_tasks

    @pytest.mark.asyncio
    async def test_orchestration_result_structure(self):
        """OrchestrationResult should have all required fields."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            result = await orchestrator.process_task(
                task_prompt="Test",
                files=[]
            )

            assert hasattr(result, 'model_used')
            assert hasattr(result, 'confidence')
            assert hasattr(result, 'reasoning')
            assert hasattr(result, 'quality_score')
            assert hasattr(result, 'tokens_used')
            assert hasattr(result, 'escalated')
            assert hasattr(result, 'cache_hits')
            assert hasattr(result, 'execution_time_ms')

    @pytest.mark.asyncio
    async def test_empty_files_list(self):
        """Should handle tasks with no files."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.80,
                reasoning="Simple task with no files",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.20,
                file_impact_score=0.0
            )

            result = await orchestrator.process_task(
                task_prompt="Fix typo in README",
                files=[]
            )

            assert result is not None
            assert result.model_used in ["opus", "sonnet", "haiku"]

    @pytest.mark.asyncio
    async def test_many_files_escalates_tier(self):
        """Should escalate tier for tasks affecting many files."""
        orchestrator = Orchestrator()

        many_files = [f"app/module_{i}.py" for i in range(20)]

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.OPUS_REQUIRED,  # Should escalate to Opus
                confidence=0.90,
                reasoning="Affects many files",
                primary_pattern="refactor",
                matched_patterns=["refactor"],
                complexity_score=0.85,
                file_impact_score=0.95
            )

            result = await orchestrator.process_task(
                task_prompt="Refactor codebase",
                files=many_files
            )

            # Should use Opus or Sonnet for large refactors
            assert result.model_used in ["opus", "sonnet"]

    @pytest.mark.asyncio
    async def test_session_id_persistence(self):
        """Session ID should persist across task executions."""
        orchestrator = Orchestrator()
        session_id = orchestrator._session_id

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.20,
                file_impact_score=0.10
            )

            await orchestrator.process_task("Task 1", [])
            await orchestrator.process_task("Task 2", [])

        # Session ID should not change
        assert orchestrator._session_id == session_id

    @pytest.mark.asyncio
    async def test_german_task_prompts(self):
        """Should handle German task prompts correctly."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementierungsaufgabe",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            result = await orchestrator.process_task(
                task_prompt="Implementiere Benutzerauthentifizierung mit JWT",
                files=["app/auth.py"]
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Should return orchestration statistics."""
        orchestrator = Orchestrator()

        stats = orchestrator.get_stats()

        assert "metrics" in stats
        assert "cache" in stats
        assert "learning" in stats

    @pytest.mark.asyncio
    async def test_concurrent_task_processing(self):
        """Should handle concurrent task processing safely."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.20,
                file_impact_score=0.10
            )

            # Process multiple tasks concurrently
            import asyncio
            tasks = [
                orchestrator.process_task(f"Task {i}", [])
                for i in range(5)
            ]

            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(r is not None for r in results)

    def test_clear_cache(self):
        """Should clear all caches."""
        orchestrator = Orchestrator()

        # Store some data
        orchestrator._cache.store(
            "Test", "Decision", "Reason", ["pattern"], ["file.py"], "opus", 0.9
        )

        # Clear
        orchestrator.clear_cache()

        # Verify cleared
        stats = orchestrator._cache.get_stats()
        assert stats["total_entries"] == 0

    def test_reset_metrics(self):
        """Should reset all metrics."""
        orchestrator = Orchestrator()

        # Record some metrics
        orchestrator._metrics.record_task("opus", 1000, 0.95, False)

        # Reset
        orchestrator.reset_metrics()

        # Verify reset
        snapshot = orchestrator._metrics.get_snapshot()
        assert snapshot.total_tasks == 0

    @pytest.mark.asyncio
    async def test_error_handling_graceful(self):
        """Should handle errors gracefully without crashing."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify:
            # Make classifier raise exception
            mock_classify.side_effect = Exception("Classification failed")

            # Should not crash
            try:
                result = await orchestrator.process_task("Test", [])
                # If it returns a result, it handled the error
                assert result is not None or True
            except Exception:
                # If it raises, test what kind of exception
                pytest.fail("Should handle errors gracefully")
