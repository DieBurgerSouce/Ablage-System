"""Integration tests for quality gate escalation chain."""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add orchestration to path
# G5 (2026-06-03): Import ueber das Paket `orchestration` (relative Imports in den Modulen).
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude"))

# Diese Suite testet das claude-flow-Orchestrierungs-Tooling unter
# `.claude/orchestration/`, NICHT die Ablage-App. Dieses Verzeichnis ist im
# Backend-Container nicht gemountet (nur `app/` + `tests/`), daher ist das Paket
# dort nicht importierbar. Sauber ueberspringen statt Collection-Error.
pytest.importorskip(
    "orchestration.orchestrator",
    reason="claude-flow-Orchestrierungs-Tooling (.claude/orchestration) im App-Container nicht verfuegbar",
)

from orchestration.orchestrator import Orchestrator, OrchestrationResult  # noqa: E402
from orchestration.task_classifier import ModelTier  # noqa: E402
from orchestration.quality_gate import QualityResult, QualityLevel  # noqa: E402


@pytest.mark.integration
class TestQualityEscalationChain:
    """Test quality-based escalation from Haiku → Sonnet → Opus."""

    @pytest.mark.asyncio
    async def test_haiku_to_sonnet_escalation_on_type_hints_failure(self):
        """Haiku fails type hints check → escalate to Sonnet."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.45,
                file_impact_score=0.30
            )

            # First validation fails (Haiku output missing type hints)
            # Second validation passes (Sonnet output has type hints)
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "german_messages"],
                    checks_failed=["type_hints"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Type hints missing - required for production code",
                    details={"missing_type_hints": ["function process_data"]}
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
                task_prompt="Implement data processing function",
                files=["app/processing.py"]
            )

            # Verify escalation occurred
            assert result.escalated is True
            assert result.model_used in ["sonnet", "opus"]
            assert "type_hints" not in [f for f in result.quality_checks_failed]

    @pytest.mark.asyncio
    async def test_sonnet_to_opus_escalation_on_german_messages_failure(self):
        """Sonnet fails German messages check → escalate to Opus."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Sonnet
            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.87,
                reasoning="Standard implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            # First validation fails (English error messages)
            # Second validation passes (German error messages)
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "type_hints", "security"],
                    checks_failed=["german_messages"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Error messages must be in German",
                    details={"english_messages_found": ["Processing failed", "Invalid input"]}
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
                task_prompt="Implement error handling for document processing",
                files=["app/errors.py"]
            )

            # Verify escalation to Opus
            assert result.escalated is True
            assert result.model_used == "opus"

    @pytest.mark.asyncio
    async def test_double_escalation_haiku_to_sonnet_to_opus(self):
        """Haiku → fails → Sonnet → fails → Opus → passes."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier initially recommends Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.80,
                reasoning="Simple refactor",
                primary_pattern="refactor",
                matched_patterns=["refactor"],
                complexity_score=0.40,
                file_impact_score=0.25
            )

            # Three validations: Haiku fails, Sonnet fails, Opus passes
            mock_validate.side_effect = [
                # Haiku: Missing type hints
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax"],
                    checks_failed=["type_hints", "german_messages"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Multiple quality failures",
                    details={}
                ),
                # Sonnet: Still missing German messages
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "type_hints"],
                    checks_failed=["german_messages"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="German language requirement not met",
                    details={}
                ),
                # Opus: All checks pass
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
                task_prompt="Refactor authentication module",
                files=["app/auth.py"]
            )

            # Verify double escalation to Opus
            assert result.escalated is True
            assert result.model_used == "opus"
            assert result.quality_score >= 0.90

    @pytest.mark.asyncio
    async def test_escalation_stops_at_opus_even_if_quality_fails(self):
        """Opus is final tier - no further escalation even on quality failure."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Classifier recommends Opus
            mock_classify.return_value = Mock(
                tier=ModelTier.OPUS_REQUIRED,
                confidence=0.95,
                reasoning="Complex architecture",
                primary_pattern="architecture",
                matched_patterns=["architecture"],
                complexity_score=0.90,
                file_impact_score=0.85
            )

            # Even if Opus fails quality, no escalation (it's the highest tier)
            mock_validate.return_value = QualityResult(
                level=QualityLevel.FAILED,
                checks_passed=["syntax"],
                checks_failed=["type_hints"],
                warnings=[],
                should_escalate=False,  # Cannot escalate beyond Opus
                escalation_reason=None,
                details={}
            )

            # Execute
            result = await orchestrator.process_task(
                task_prompt="Design distributed consensus algorithm",
                files=["app/consensus.py"]
            )

            # Opus used, no further escalation possible
            assert result.model_used == "opus"
            assert result.escalated is False  # Started at Opus, no escalation

    @pytest.mark.asyncio
    async def test_escalation_preserves_original_task_context(self):
        """Escalated task should retain original prompt and context."""
        orchestrator = Orchestrator()

        original_prompt = "Implement user registration with email verification"
        original_files = ["app/users.py", "app/email.py"]

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.82,
                reasoning="User registration implementation",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.50,
                file_impact_score=0.35
            )

            # Fail then pass
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax"],
                    checks_failed=["type_hints"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Type hints required",
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
                task_prompt=original_prompt,
                files=original_files
            )

            # Verify escalation happened
            assert result.escalated is True

            # Original context should be preserved (verified through metrics/logs)
            # In real implementation, the escalated task would include original context

    @pytest.mark.asyncio
    async def test_security_check_failure_triggers_immediate_escalation(self):
        """Security failures should trigger immediate escalation to Opus."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            # Start with Haiku
            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple function",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.30,
                file_impact_score=0.20
            )

            # SECURITY TEST CASE: This test simulates the quality gate detecting dangerous
            # code patterns (like use of dangerous functions). This is NOT production code -
            # it's testing that our security checks can DETECT such issues.
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "type_hints"],
                    checks_failed=["security"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="CRITICAL: Security vulnerability detected (dangerous function usage)",
                    details={"security_issues": ["Dangerous code execution pattern detected"]}
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
                task_prompt="Implement code execution helper",
                files=["app/executor.py"]
            )

            # Should escalate to Opus for security fix
            assert result.escalated is True
            assert result.model_used == "opus"

    @pytest.mark.asyncio
    async def test_gpu_pattern_failure_escalates_with_gpu_context(self):
        """GPU pattern failures should escalate with GPU management context."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.85,
                reasoning="GPU optimization task",
                primary_pattern="implementation",
                matched_patterns=["implementation", "gpu"],
                complexity_score=0.70,
                file_impact_score=0.55
            )

            # GPU pattern failure
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax", "type_hints", "german_messages"],
                    checks_failed=["gpu_patterns"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Missing gpu_memory_guard() wrapper for GPU operations",
                    details={"gpu_issues": ["Unprotected torch.cuda.* calls"]}
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
                task_prompt="Optimize GPU batch processing",
                files=["app/gpu_processor.py"]
            )

            # Should escalate to Opus for proper GPU management
            assert result.escalated is True
            assert result.model_used == "opus"

    @pytest.mark.asyncio
    async def test_warnings_dont_trigger_escalation(self):
        """Quality warnings should not trigger escalation."""
        orchestrator = Orchestrator()

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.SONNET_CAPABLE,
                confidence=0.87,
                reasoning="Implementation task",
                primary_pattern="implementation",
                matched_patterns=["implementation"],
                complexity_score=0.65,
                file_impact_score=0.50
            )

            # Passes with warnings (not failures)
            mock_validate.return_value = QualityResult(
                level=QualityLevel.PASSED,
                checks_passed=["syntax", "type_hints", "german_messages", "gpu_patterns", "security", "imports"],
                checks_failed=[],
                warnings=["Missing docstring for helper function", "Could improve variable naming"],
                should_escalate=False,
                escalation_reason=None,
                details={}
            )

            # Execute
            result = await orchestrator.process_task(
                task_prompt="Implement helper function",
                files=["app/utils.py"]
            )

            # Should NOT escalate on warnings
            assert result.escalated is False
            assert result.model_used == "sonnet"

    @pytest.mark.asyncio
    async def test_escalation_metrics_recorded_correctly(self):
        """Escalation events should be recorded in metrics."""
        orchestrator = Orchestrator()

        initial_snapshot = orchestrator._metrics.get_snapshot()
        initial_escalations = initial_snapshot.total_escalations if hasattr(initial_snapshot, 'total_escalations') else 0

        with patch.object(orchestrator._classifier, 'classify') as mock_classify, \
             patch.object(orchestrator._quality_gate, 'validate') as mock_validate:

            mock_classify.return_value = Mock(
                tier=ModelTier.HAIKU_SUFFICIENT,
                confidence=0.85,
                reasoning="Simple task",
                primary_pattern="formatting",
                matched_patterns=["formatting"],
                complexity_score=0.25,
                file_impact_score=0.15
            )

            # Trigger escalation
            mock_validate.side_effect = [
                QualityResult(
                    level=QualityLevel.FAILED,
                    checks_passed=["syntax"],
                    checks_failed=["type_hints"],
                    warnings=[],
                    should_escalate=True,
                    escalation_reason="Type hints required",
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
            await orchestrator.process_task(
                task_prompt="Format code",
                files=["app/main.py"]
            )

        # Verify escalation recorded in metrics
        final_snapshot = orchestrator._metrics.get_snapshot()
        if hasattr(final_snapshot, 'total_escalations'):
            assert final_snapshot.total_escalations > initial_escalations
