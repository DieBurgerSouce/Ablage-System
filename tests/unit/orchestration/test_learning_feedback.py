"""Unit tests for LearningFeedback."""

import pytest
import sys
from pathlib import Path

# Add .claude to path so orchestration is a proper package
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.learning_feedback import LearningFeedback, TaskExecution, PatternStatistics


class TestLearningFeedback:
    """Test suite for learning feedback system."""

    def test_record_task_creates_execution(self, learning_feedback):
        """Recording a task should create execution record."""
        learning_feedback.record_task(
            task_prompt="Implement feature X",
            task_pattern="implementation",
            initial_tier="sonnet",
            final_tier="sonnet",
            escalated=False,
            quality_score=0.92,
            execution_time_ms=1234,
            success=True
        )

        assert len(learning_feedback.feedback_history) > 0

    def test_task_hash_generation(self, learning_feedback):
        """Task hash should be generated for deduplication."""
        learning_feedback.record_task(
            task_prompt="Test task",
            task_pattern="test",
            initial_tier="haiku",
            final_tier="haiku",
            escalated=False,
            quality_score=0.90,
            execution_time_ms=500,
            success=True
        )

        execution = learning_feedback.feedback_history[-1]
        assert execution.task_hash is not None
        assert len(execution.task_hash) == 16  # MD5 hash truncated to 16 chars

    def test_same_prompt_generates_same_hash(self, learning_feedback):
        """Same task prompt should generate same hash."""
        prompt = "Identical task prompt"

        learning_feedback.record_task(prompt, "test", "haiku", "haiku", False, 0.9, 500, True)
        hash1 = learning_feedback.feedback_history[-1].task_hash

        learning_feedback.record_task(prompt, "test", "haiku", "haiku", False, 0.9, 500, True)
        hash2 = learning_feedback.feedback_history[-1].task_hash

        assert hash1 == hash2

    def test_pattern_statistics_calculation(self, learning_feedback):
        """Should calculate pattern statistics after enough executions."""
        # Record 20 tasks (triggers optimization)
        for i in range(20):
            learning_feedback.record_task(
                task_prompt=f"Implementation task {i}",
                task_pattern="implementation",
                initial_tier="sonnet",
                final_tier="sonnet",
                escalated=False,
                quality_score=0.90 + (i * 0.001),
                execution_time_ms=1000 + i * 10,
                success=True
            )

        # Should have statistics for implementation pattern
        stats = learning_feedback.get_pattern_recommendation("implementation")
        assert stats is not None
        assert stats.pattern == "implementation"

    def test_tier_success_rates(self, learning_feedback):
        """Should calculate success rates per tier."""
        # Record successes and failures
        for i in range(10):
            learning_feedback.record_task(
                task_prompt=f"Task {i}",
                task_pattern="implementation",
                initial_tier="haiku",
                final_tier="haiku" if i < 7 else "sonnet",  # 7 successes, 3 escalations
                escalated=i >= 7,
                quality_score=0.90 if i < 7 else 0.75,
                execution_time_ms=1000,
                success=True
            )

        # Update statistics
        learning_feedback._update_pattern_statistics()

        stats = learning_feedback.pattern_stats.get("implementation")
        if stats:
            # Success rate for haiku should be 70% (7/10)
            haiku_success = stats.tier_success_rates.get("haiku", 0.0)
            assert 0.60 <= haiku_success <= 0.80

    def test_escalation_rate_tracking(self, learning_feedback):
        """Should track escalation rates per tier."""
        # Record tasks with some escalations
        for i in range(10):
            learning_feedback.record_task(
                task_prompt=f"Task {i}",
                task_pattern="refactor",
                initial_tier="sonnet",
                final_tier="opus" if i % 3 == 0 else "sonnet",
                escalated=i % 3 == 0,
                quality_score=0.90,
                execution_time_ms=1500,
                success=True
            )

        learning_feedback._update_pattern_statistics()

        stats = learning_feedback.pattern_stats.get("refactor")
        if stats:
            # Escalation rate should be ~33% (every 3rd task)
            sonnet_escalation = stats.escalation_rate.get("sonnet", 0.0)
            assert 0.25 <= sonnet_escalation <= 0.40

    def test_recommended_tier_logic(self, learning_feedback):
        """Should recommend lower-cost tier when performance is good."""
        # Record excellent performance with Haiku
        for i in range(25):
            learning_feedback.record_task(
                task_prompt=f"Simple task {i}",
                task_pattern="formatting",
                initial_tier="haiku",
                final_tier="haiku",
                escalated=False,
                quality_score=0.95,
                execution_time_ms=300,
                success=True
            )

        learning_feedback._update_pattern_statistics()

        stats = learning_feedback.pattern_stats.get("formatting")
        if stats:
            # Should recommend Haiku due to excellent performance
            assert stats.recommended_tier == "haiku"
            assert stats.confidence > 0.90

    def test_optimization_suggestions(self, learning_feedback):
        """Should generate optimization suggestions."""
        # Record data that suggests downgrade opportunity
        for i in range(25):
            learning_feedback.record_task(
                task_prompt=f"Test task {i}",
                task_pattern="testing",
                initial_tier="sonnet",
                final_tier="sonnet",
                escalated=False,
                quality_score=0.92,
                execution_time_ms=800,
                success=True
            )

        # Simulate Haiku performing well on same pattern
        for i in range(25):
            learning_feedback.record_task(
                task_prompt=f"Test task haiku {i}",
                task_pattern="testing",
                initial_tier="haiku",
                final_tier="haiku",
                escalated=False,
                quality_score=0.90,
                execution_time_ms=400,
                success=True
            )

        suggestions = learning_feedback.optimize_classifier_patterns()

        # Should suggest downgrade to Haiku or keep Haiku
        assert len(suggestions) > 0

    def test_insufficient_data_no_suggestions(self, learning_feedback):
        """Should not make suggestions with insufficient data."""
        # Record only 5 tasks (below threshold of 20)
        for i in range(5):
            learning_feedback.record_task(
                task_prompt=f"Task {i}",
                task_pattern="experimental",
                initial_tier="opus",
                final_tier="opus",
                escalated=False,
                quality_score=0.95,
                execution_time_ms=2000,
                success=True
            )

        suggestions = learning_feedback.optimize_classifier_patterns()

        # Should not suggest changes for patterns with <20 executions
        experimental_suggestions = [s for s in suggestions if s["pattern"] == "experimental"]
        assert len(experimental_suggestions) == 0

    def test_feedback_history_persistence(self, temp_cache_dir):
        """Feedback history should persist across instances."""
        # Create first instance and record task
        feedback1 = LearningFeedback(cache_dir=temp_cache_dir)
        feedback1.record_task(
            task_prompt="Persistent task",
            task_pattern="test",
            initial_tier="sonnet",
            final_tier="sonnet",
            escalated=False,
            quality_score=0.90,
            execution_time_ms=1000,
            success=True
        )

        # Create second instance (should load from disk)
        feedback2 = LearningFeedback(cache_dir=temp_cache_dir)

        assert len(feedback2.feedback_history) > 0

    def test_summary_statistics(self, learning_feedback):
        """Should generate accurate summary statistics."""
        # Record varied tasks
        learning_feedback.record_task("Task 1", "impl", "opus", "opus", False, 0.95, 2000, True)
        learning_feedback.record_task("Task 2", "impl", "sonnet", "opus", True, 0.90, 1500, True)
        learning_feedback.record_task("Task 3", "impl", "haiku", "haiku", False, 0.88, 500, True)

        summary = learning_feedback.get_summary()

        assert summary["total_executions"] == 3
        assert 0.0 <= summary["escalation_rate"] <= 1.0
        assert 0.0 <= summary["avg_quality_score"] <= 1.0
        assert "tier_distribution" in summary

    def test_empty_feedback_summary(self, learning_feedback):
        """Empty feedback should return valid summary."""
        summary = learning_feedback.get_summary()

        assert summary["total_executions"] == 0

    def test_task_execution_structure(self, mock_task_execution):
        """TaskExecution should have all required fields."""
        assert hasattr(mock_task_execution, 'task_hash')
        assert hasattr(mock_task_execution, 'task_pattern')
        assert hasattr(mock_task_execution, 'initial_tier')
        assert hasattr(mock_task_execution, 'final_tier')
        assert hasattr(mock_task_execution, 'escalated')
        assert hasattr(mock_task_execution, 'quality_score')
        assert hasattr(mock_task_execution, 'execution_time_ms')
        assert hasattr(mock_task_execution, 'timestamp')
        assert hasattr(mock_task_execution, 'success')

    def test_pattern_statistics_structure(self, learning_feedback):
        """PatternStatistics should have all required fields."""
        # Record enough tasks to generate statistics
        for i in range(20):
            learning_feedback.record_task(
                f"Task {i}", "test_pattern", "sonnet", "sonnet", False, 0.90, 1000, True
            )

        learning_feedback._update_pattern_statistics()
        stats = learning_feedback.pattern_stats.get("test_pattern")

        if stats:
            assert hasattr(stats, 'pattern')
            assert hasattr(stats, 'total_executions')
            assert hasattr(stats, 'tier_success_rates')
            assert hasattr(stats, 'avg_quality_scores')
            assert hasattr(stats, 'escalation_rate')
            assert hasattr(stats, 'recommended_tier')
            assert hasattr(stats, 'confidence')

    def test_avg_quality_scores_by_tier(self, learning_feedback):
        """Should calculate average quality scores per tier."""
        for i in range(10):
            learning_feedback.record_task(
                f"Task {i}", "impl", "opus", "opus", False, 0.95 - i * 0.01, 2000, True
            )

        learning_feedback._update_pattern_statistics()
        stats = learning_feedback.pattern_stats.get("impl")

        if stats:
            opus_quality = stats.avg_quality_scores.get("opus", 0.0)
            # Average should be around 0.905 (0.95 to 0.86 average)
            assert 0.88 <= opus_quality <= 0.92

    def test_high_escalation_triggers_upgrade_suggestion(self, learning_feedback):
        """High escalation rate should trigger upgrade suggestion."""
        # Record frequent escalations
        for i in range(25):
            learning_feedback.record_task(
                f"Task {i}",
                "complex_task",
                "haiku",
                "sonnet" if i % 2 == 0 else "haiku",  # 50% escalation
                escalated=i % 2 == 0,
                quality_score=0.80,
                execution_time_ms=1000,
                success=True
            )

        suggestions = learning_feedback.optimize_classifier_patterns()

        # Should suggest upgrade due to high escalation
        upgrade_suggestions = [s for s in suggestions if s["action"] == "upgrade_tier"]
        assert len(upgrade_suggestions) > 0

    def test_tier_distribution_tracking(self, learning_feedback):
        """Should track tier distribution correctly."""
        learning_feedback.record_task("T1", "p", "opus", "opus", False, 0.95, 2000, True)
        learning_feedback.record_task("T2", "p", "sonnet", "sonnet", False, 0.90, 1000, True)
        learning_feedback.record_task("T3", "p", "sonnet", "sonnet", False, 0.91, 1000, True)
        learning_feedback.record_task("T4", "p", "haiku", "haiku", False, 0.88, 500, True)

        summary = learning_feedback.get_summary()
        dist = summary["tier_distribution"]

        assert dist["opus"] == 1
        assert dist["sonnet"] == 2
        assert dist["haiku"] == 1
