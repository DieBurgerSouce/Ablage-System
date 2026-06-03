"""End-to-end integration tests for orchestration system."""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

# Add orchestration to path
# G5 (2026-06-03): Import ueber das Paket `orchestration`, nicht die Module flach.
# `.claude/orchestration/orchestrator.py` nutzt relative Imports (from .task_classifier);
# ein flacher Import bricht mit "attempted relative import with no known parent package".
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude"))

from orchestration.orchestrator import Orchestrator, OverrideMode, OrchestrationResult
from orchestration.task_classifier import TaskClassifier, ModelTier
from orchestration.quality_gate import QualityGate, QualityResult, QualityLevel
from orchestration.decision_cache import DecisionCache


@pytest.mark.integration
class TestOrchestrationE2E:
    """Test complete orchestration workflow end-to-end."""

    @pytest.mark.asyncio
    async def test_simple_task_haiku_workflow_complete(self):
        """Test: Simple task → Haiku → Quality OK → Complete."""
        orchestrator = Orchestrator()

        # Simple typo fix should route to Haiku
        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.90,
                reasoning="Simple typo fix",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.15,
                file_impact_score=0.05
            )

            # Quality gate passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute
            result = await orchestrator.process_task(
                task_prompt="Fix typo in README.md line 42",
                files=["README.md"]
            )

            # Verify workflow completed successfully
            assert result is not None
            assert isinstance(result, OrchestrationResult)
            assert result.model_used == "haiku"
            assert result.escalated is False
            assert result.quality_score >= 0.90

    @pytest.mark.asyncio
    async def test_complex_task_opus_workflow_with_caching(self):
        """Test: Complex task → Opus → Quality OK → Cache decision → Complete."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Opus for complex architecture
            mock_classify.return_value = Mock(
                tier=ModelTier.OPUS_REQUIRED,
                confidence=0.95,
                reasoning="Complex distributed system design",
                primary_pattern="architecture",
                matched_patterns=["architecture", "distributed"],
                complexity_score=0.92,
                file_impact_score=0.85
            )

            # Quality gate passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute complex task
            result = await orchestrator.process_task(
                task_prompt="Design distributed consensus algorithm with Byzantine fault tolerance",
                files=["app/core/consensus.py", "app/core/distributed.py"]
            )

            # Verify Opus was used and decision cached
            assert result.model_used == "opus"
            assert result.escalated is False

            # Verify decision was cached (check cache stats)
            cache_stats = orchestrator._cache.get_stats()
            assert cache_stats["total_entries"] > 0

    @pytest.mark.asyncio
    async def test_haiku_quality_failure_escalates_to_sonnet(self):
        """Test: Haiku → Quality Fails → Sonnet → Quality OK → Complete."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier initially recommends Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Standard implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.55,
                file_impact_score=0.40
            )

            # First call: Quality gate fails for Haiku (missing type hints)
            # Second call: Quality gate passes for Sonnet
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "german_messages"],
                    checks_failed=["type_hints"],
                    warnings=["Missing docstring"],
                    should_escalate=True,
                    escalation_reason="Type hints missing - critical for Haiku tier",
                    details={}
                ),
                QualityResult(
                    level=QualityLevel.PASSED,
                    checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                    checks_failed=[],
                    warnings=[],
                    should_escalate=False,
                    escalation_reason=None,
                    details={}
                )
            ]

            # Execute
            result = await orchestrator.process_task(
                task_prompt="Implement user authentication endpoint",
                files=["app/api/auth.py"]
            )

            # Verify escalation happened
            assert result.escalated is True
            # After escalation from Haiku, should use Sonnet
            assert result.model_used in ["sonnet", "opus"]

    @pytest.mark.asyncio
    async def test_sonnet_with_cached_opus_decisions(self):
        """Test: Sonnet task reuses cached Opus decisions from similar tasks."""
        orchestrator = Orchestrator()

        # First, store an Opus decision
        orchestrator._cache.store(
            task_description="Implement authentication with JWT",
            decision="Use JWT tokens with bcrypt password hashing",
            reasoning="Industry standard, secure, well-tested libraries available",
            affected_patterns=["authentication", "security"],
            affected_files=["app/auth.py"],
            model_used="opus",
            confidence=0.95
        )

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Sonnet for similar task
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.87,
                reasoning="Authentication implementation",
                primary_pattern="implementation",
                matched_patterns=["authentication", "implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            # Quality gate passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute similar authentication task
            result = await orchestrator.process_task(
                task_prompt="Add JWT authentication to login endpoint",
                files=["app/api/login.py", "app/auth.py"]
            )

            # Verify Sonnet used and cache was hit
            assert result.model_used == "sonnet"
            assert result.cache_hits > 0  # Should have found cached Opus decision

    @pytest.mark.asyncio
    async def test_concurrent_task_processing_no_conflicts(self):
        """Test: Multiple tasks processed concurrently without conflicts."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Different complexity tasks
            def classify_side_effect(prompt, files):
                if "typo" in prompt.lower():
                    return Mock(
                        tier=ModelTier.HAIKU_SUFFICIENT,
                        confidence=0.90,
                        reasoning="Simple fix",
                        primary_pattern="formatting",
                        matched_patterns=["formatting"],
                        complexity_score=0.15,
                        file_impact_score=0.05
                    )
                elif "authentication" in prompt.lower():
                    return Mock(
                        tier=ModelTier.SONNET_CAPABLE,
                        confidence=0.85,
                        reasoning="Standard implementation",
                        primary_pattern="implementation",
                        matched_patterns=["implementation"],
                        complexity_score=0.65,
                        file_impact_score=0.50
                    )
                else:
                    return Mock(
                        tier=ModelTier.OPUS_REQUIRED,
                        confidence=0.92,
                        reasoning="Complex architecture",
                        primary_pattern="architecture",
                        matched_patterns=["architecture"],
                        complexity_score=0.88,
                        file_impact_score=0.80
                    )

            mock_classify.side_effect = classify_side_effect

            # Quality gate always passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Process multiple tasks concurrently
            tasks = [
                orchestrator.process_task("Fix typo in README", []),
                orchestrator.process_task("Implement authentication endpoint", ["app/api/auth.py"]),
                orchestrator.process_task("Design distributed cache architecture", ["app/cache/"]),
                orchestrator.process_task("Fix another typo in docs", []),
                orchestrator.process_task("Add unit tests for service", ["tests/test_service.py"]),
            ]

            results = await asyncio.gather(*tasks)

            # Verify all tasks completed successfully
            assert len(results) == 5
            assert all(isinstance(r, OrchestrationResult) for r in results)

            # Verify tier distribution
            haiku_count = sum(1 for r in results if r.model_used == "haiku")
            sonnet_count = sum(1 for r in results if r.model_used == "sonnet")
            opus_count = sum(1 for r in results if r.model_used == "opus")

            # Should have mix of tiers
            assert haiku_count > 0
            assert sonnet_count > 0 or opus_count > 0

    @pytest.mark.asyncio
    async def test_override_mode_bypasses_classification(self):
        """Test: Override mode forces specific model regardless of classification."""
        orchestrator = Orchestrator()
        orchestrator.set_override_mode(OverrideMode.ALWAYS_OPUS)

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier would recommend Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.95,
                reasoning="Simple formatting",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.10,
                file_impact_score=0.02
            )

            # Quality gate passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute simple task
            result = await orchestrator.process_task(
                task_prompt="Fix whitespace in code",
                files=[]
            )

            # Should use Opus despite Haiku being sufficient
            assert result.model_used == "opus"

    @pytest.mark.asyncio
    async def test_german_language_task_handling(self):
        """Test: German task prompts processed correctly with quality validation."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # German implementation task
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.88,
                reasoning="Implementierungsaufgabe mit Authentifizierung",
                primary_pattern="implementation",
                matched_patterns=["implementation", "authentication"],
                complexity_score=0.68,
                file_impact_score=0.55
            )

            # Quality gate validates German messages
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute German task
            result = await orchestrator.process_task(
                task_prompt="Implementiere Benutzerauthentifizierung mit JWT-Tokens und bcrypt Passwort-Hashing",
                files=["app/auth.py", "app/api/login.py"]
            )

            # Verify task completed successfully
            assert result is not None
            assert result.model_used in ["sonnet", "opus"]
            assert result.quality_score >= 0.80

    @pytest.mark.asyncio
    async def test_many_files_escalates_to_higher_tier(self):
        """Test: Tasks affecting many files escalate to higher tier."""
        orchestrator = Orchestrator()

        many_files = [f"app/module_{i}.py" for i in range(25)]

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Large refactoring should escalate to Opus
            mock_classify.return_value = Mock(
                tier=ModelTier.OPUS_REQUIRED,
                confidence=0.93,
                reasoning="Large-scale refactoring affecting 25 files",
                primary_pattern="refactor",
                matched_patterns=["refactor"],
                complexity_score=0.90,
                file_impact_score=0.98
            )

            # Quality gate passes
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute large refactor
            result = await orchestrator.process_task(
                task_prompt="Refactor authentication system across entire codebase",
                files=many_files
            )

            # Should use Opus or Sonnet for large changes
            assert result.model_used in ["opus", "sonnet"]

    @pytest.mark.asyncio
    async def test_metrics_recorded_throughout_workflow(self):
        """Test: Metrics correctly recorded during task execution."""
        orchestrator = Orchestrator()

        initial_snapshot = orchestrator._metrics.get_snapshot()
        initial_tasks = initial_snapshot.total_tasks

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="Implementation task",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute task
            await orchestrator.process_task(
                task_prompt="Test metrics recording",
                files=[]
            )

        # Verify metrics updated
        final_snapshot = orchestrator._metrics.get_snapshot()
        assert final_snapshot.total_tasks > initial_tasks
        assert final_snapshot.total_tasks == initial_tasks + 1

    @pytest.mark.asyncio
    async def test_learning_feedback_recorded_after_execution(self):
        """Test: Learning feedback recorded for pattern optimization."""
        orchestrator = Orchestrator()

        initial_count = len(orchestrator._learning.feedback_history)

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.90,
                reasoning="Simple formatting",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.15,
                file_impact_score=0.05
            )

            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=[],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute task
            await orchestrator.process_task(
                task_prompt="Format code with Black",
                files=["app/main.py"]
            )

        # Verify learning feedback recorded
        final_count = len(orchestrator._learning.feedback_history)
        assert final_count > initial_count
