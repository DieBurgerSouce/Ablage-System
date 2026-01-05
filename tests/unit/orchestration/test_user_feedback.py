"""Unit tests for UserFeedback."""

import pytest
import sys
from pathlib import Path
from io import StringIO

# Add orchestration to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / ".claude" / "orchestration"))

from user_feedback import UserFeedback, DisplayMode, OrchestrationFeedback


class TestUserFeedback:
    """Test suite for user feedback display."""

    def test_show_routing_decision_formats_correctly(self, user_feedback):
        """Should format routing decision for display."""
        # Capture output
        import sys
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_routing_decision(
            model="sonnet",
            confidence=0.87,
            reasoning="Standard implementation task",
            files=3
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        # Should contain key information
        assert "sonnet" in result.lower() or "SONNET" in result
        assert "87" in result or "0.87" in result  # Confidence
        # German language markers
        assert any(word in result.lower() for word in ["modell", "confidence", "begründung"])

    def test_display_mode_affects_output(self, user_feedback):
        """Display mode should affect formatting."""
        user_feedback.set_display_mode(DisplayMode.DARK)

        # Dark mode should be set
        assert user_feedback.current_mode == DisplayMode.DARK

        # Change to light mode
        user_feedback.set_display_mode(DisplayMode.LIGHT)
        assert user_feedback.current_mode == DisplayMode.LIGHT

    def test_token_savings_calculation_display(self, user_feedback):
        """Should display token savings accurately."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_token_savings(
            tokens_used=1000,
            tokens_baseline=5000
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        # Should show 80% savings (4000 / 5000)
        assert "80" in result or "4000" in result

    def test_quality_score_display(self, user_feedback):
        """Should display quality scores formatted correctly."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_quality_score(
            score=0.92,
            checks_passed=5,
            checks_failed=1
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        assert "0.92" in result or "92" in result
        assert "5" in result  # Checks passed
        assert "1" in result  # Checks failed

    def test_escalation_notice_display(self, user_feedback):
        """Should display escalation notices."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_escalation_notice(
            from_model="haiku",
            to_model="sonnet",
            reason="Quality validation failed"
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        assert "haiku" in result.lower()
        assert "sonnet" in result.lower()
        assert "quality" in result.lower() or "qualität" in result.lower()

    def test_orchestration_feedback_structure(self):
        """OrchestrationFeedback should have all required fields."""
        feedback = OrchestrationFeedback(
            model_used="sonnet",
            confidence=0.85,
            reasoning="Test reasoning",
            quality_score=0.90,
            tokens_used=1000,
            tokens_saved=4000,
            escalated=False
        )

        assert feedback.model_used == "sonnet"
        assert feedback.confidence == 0.85
        assert feedback.reasoning == "Test reasoning"
        assert feedback.quality_score == 0.90
        assert feedback.tokens_used == 1000
        assert feedback.tokens_saved == 4000
        assert feedback.escalated is False

    def test_german_language_output(self, user_feedback):
        """User feedback should be in German."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_routing_decision(
            model="opus",
            confidence=0.95,
            reasoning="Complex architecture task",
            files=5
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        # Check for German language markers
        german_words = ["modell", "confidence", "begründung", "dateien", "einsparung"]
        has_german = any(word in result.lower() for word in german_words)
        assert has_german, f"Output should be in German: {result}"

    def test_model_icons_display(self, user_feedback):
        """Should display model-specific icons."""
        old_stdout = sys.stdout

        for model, expected_icon in [("opus", "🧠"), ("sonnet", "⚙️"), ("haiku", "✨")]:
            sys.stdout = output = StringIO()
            user_feedback.show_routing_decision(model, 0.90, "Test", 1)
            sys.stdout = old_stdout
            result = output.getvalue()

            assert expected_icon in result, f"Expected icon {expected_icon} for {model}"

    def test_display_mode_enum_values(self):
        """DisplayMode should have all required values."""
        assert hasattr(DisplayMode, 'DARK')
        assert hasattr(DisplayMode, 'LIGHT')
        assert hasattr(DisplayMode, 'WHITESCREEN')
        assert hasattr(DisplayMode, 'BLACKSCREEN')

    def test_cache_hit_notification(self, user_feedback):
        """Should display cache hit notifications."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_cache_hit(
            decision_count=2,
            relevance_score=0.85
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        assert "2" in result  # Decision count
        assert "cache" in result.lower() or "entscheidung" in result.lower()

    def test_summary_display(self, user_feedback):
        """Should display summary statistics."""
        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_summary(
            total_tasks=100,
            avg_quality=0.92,
            token_savings_pct=0.55,
            escalation_rate=0.08
        )

        sys.stdout = old_stdout
        result = output.getvalue()

        assert "100" in result  # Total tasks
        assert "92" in result or "0.92" in result  # Quality
        assert "55" in result or "0.55" in result  # Savings
        assert "8" in result or "0.08" in result  # Escalation

    def test_verbose_mode_toggle(self, user_feedback):
        """Should support verbose/quiet modes."""
        user_feedback.set_verbose(True)
        assert user_feedback.verbose is True

        user_feedback.set_verbose(False)
        assert user_feedback.verbose is False

    def test_quiet_mode_suppresses_output(self, user_feedback):
        """Quiet mode should suppress non-critical output."""
        user_feedback.set_verbose(False)

        old_stdout = sys.stdout
        sys.stdout = output = StringIO()

        user_feedback.show_routing_decision("haiku", 0.80, "Simple task", 1)

        sys.stdout = old_stdout
        result = output.getvalue()

        # Quiet mode should produce minimal output
        assert len(result) < 200  # Arbitrary threshold for "minimal"
