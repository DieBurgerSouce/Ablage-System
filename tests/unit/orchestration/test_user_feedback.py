"""Unit tests for UserFeedback."""

import pytest
import sys
from pathlib import Path
from io import StringIO

# Add .claude to path so orchestration is a proper package
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.user_feedback import UserFeedback, DisplayMode, OrchestrationFeedback


class TestUserFeedback:
    """Test suite for user feedback display."""

    def test_show_routing_decision_formats_correctly(self, user_feedback):
        """Should format routing decision for display."""
        # Capture stderr (where UserFeedback outputs)
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_routing_decision(
            model="sonnet",
            confidence=0.87,
            reasoning="Standard implementation task",
            files=3
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        # Should contain key information
        assert "sonnet" in result.lower() or "SONNET" in result
        assert "87" in result  # Confidence
        # German language markers
        assert any(word in result.lower() for word in ["modell", "confidence", "begründung"])

    def test_display_mode_affects_output(self, user_feedback):
        """Display mode should affect formatting."""
        # Test minimal mode
        feedback_minimal = UserFeedback(mode=DisplayMode.MINIMAL)
        assert feedback_minimal.mode == DisplayMode.MINIMAL

        # Test detailed mode
        feedback_detailed = UserFeedback(mode=DisplayMode.DETAILED)
        assert feedback_detailed.mode == DisplayMode.DETAILED

        # Capture and compare output lengths
        old_stderr = sys.stderr

        sys.stderr = output_minimal = StringIO()
        feedback_minimal.show_routing_decision("sonnet", 0.87, "Test", 3)
        sys.stderr = old_stderr
        minimal_output = output_minimal.getvalue()

        sys.stderr = output_detailed = StringIO()
        feedback_detailed.show_routing_decision("sonnet", 0.87, "Test", 3)
        sys.stderr = old_stderr
        detailed_output = output_detailed.getvalue()

        # Detailed should have more output
        assert len(detailed_output) >= len(minimal_output)

    def test_token_savings_calculation(self, user_feedback):
        """Should calculate token savings accurately."""
        # Test internal savings calculation
        assert user_feedback._calculate_savings("opus") == 0  # No savings vs Opus
        assert user_feedback._calculate_savings("sonnet") == 80  # 80% savings
        assert user_feedback._calculate_savings("haiku") == 95  # 95% savings

    def test_show_quality_result_display(self, user_feedback):
        """Should display quality results correctly."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_quality_result(
            model="sonnet",
            quality_score=0.92
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "0.92" in result or "92" in result
        assert "quality" in result.lower() or "gut" in result.lower()

    def test_escalation_display(self, user_feedback):
        """Should display escalation notices."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_escalation(
            from_model="haiku",
            to_model="sonnet",
            reason="Quality validation failed",
            quality_score=0.75
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "haiku" in result.lower()
        assert "sonnet" in result.lower()
        assert "eskalation" in result.lower() or "quality" in result.lower()

    def test_orchestration_feedback_structure(self):
        """OrchestrationFeedback should have all required fields."""
        feedback = OrchestrationFeedback(
            model="sonnet",
            confidence=0.85,
            reasoning="Test reasoning",
            quality_score=0.90,
            escalated_from="haiku",
            cache_hit=True,
            files_affected=5,
            estimated_tokens=1000
        )

        assert feedback.model == "sonnet"
        assert feedback.confidence == 0.85
        assert feedback.reasoning == "Test reasoning"
        assert feedback.quality_score == 0.90
        assert feedback.escalated_from == "haiku"
        assert feedback.cache_hit is True
        assert feedback.files_affected == 5
        assert feedback.estimated_tokens == 1000

    def test_german_language_output(self, user_feedback):
        """User feedback should be in German."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_routing_decision(
            model="opus",
            confidence=0.95,
            reasoning="Complex architecture task",
            files=5
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        # Check for German language markers
        german_words = ["modell", "confidence", "begründung", "dateien", "einsparung"]
        has_german = any(word in result.lower() for word in german_words)
        assert has_german, f"Output should be in German: {result}"

    def test_model_icons_display(self, user_feedback):
        """Should display model-specific icons."""
        old_stderr = sys.stderr

        for model, expected_icon in [("opus", "🧠"), ("sonnet", "⚙️"), ("haiku", "✨")]:
            sys.stderr = output = StringIO()
            user_feedback.show_routing_decision(model, 0.90, "Test", 1)
            sys.stderr = old_stderr
            result = output.getvalue()

            assert expected_icon in result, f"Expected icon {expected_icon} for {model}"

    def test_display_mode_enum_values(self):
        """DisplayMode should have all required values."""
        # Actual enum values (not DARK/LIGHT like UI modes)
        assert hasattr(DisplayMode, 'MINIMAL')
        assert hasattr(DisplayMode, 'STANDARD')
        assert hasattr(DisplayMode, 'DETAILED')

    def test_cache_hit_displayed_in_routing(self, user_feedback):
        """Should display cache hit in routing decision."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_routing_decision(
            model="sonnet",
            confidence=0.85,
            reasoning="Test",
            files=1,
            cache_hit=True
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        # Cache hit should be displayed
        assert "cache" in result.lower() or "♻️" in result

    def test_files_affected_displayed(self, user_feedback):
        """Should display number of affected files."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_routing_decision(
            model="sonnet",
            confidence=0.85,
            reasoning="Test",
            files=10,
            estimated_tokens=5000
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        # Files count should be displayed
        assert "10" in result
        # Estimated tokens should be displayed
        assert "5,000" in result or "5000" in result

    def test_model_formatting(self, user_feedback):
        """Should format model names consistently."""
        formatted = user_feedback._format_model("sonnet")
        assert "SONNET" in formatted
        assert "⚙️" in formatted

    def test_savings_calculation_unknown_model(self, user_feedback):
        """Unknown model should return 0 savings."""
        savings = user_feedback._calculate_savings("unknown_model")
        assert savings == 0

    def test_quality_result_excellent_score(self, user_feedback):
        """Excellent quality score should show appropriate emoji."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_quality_result("sonnet", quality_score=0.98)

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "✅" in result
        assert "exzellent" in result.lower()

    def test_quality_result_poor_score(self, user_feedback):
        """Poor quality score should show warning."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_quality_result("haiku", quality_score=0.65)

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "❌" in result
        assert "unzureichend" in result.lower()

    def test_minimal_mode_output_shorter(self):
        """Minimal mode should produce shorter output."""
        feedback_minimal = UserFeedback(mode=DisplayMode.MINIMAL)
        feedback_detailed = UserFeedback(mode=DisplayMode.DETAILED)

        old_stderr = sys.stderr

        sys.stderr = output_minimal = StringIO()
        feedback_minimal.show_routing_decision("haiku", 0.80, "Simple task", 1)
        sys.stderr = old_stderr
        minimal_result = output_minimal.getvalue()

        sys.stderr = output_detailed = StringIO()
        feedback_detailed.show_routing_decision("haiku", 0.80, "Simple task", 1)
        sys.stderr = old_stderr
        detailed_result = output_detailed.getvalue()

        # Minimal should be shorter
        assert len(minimal_result) < len(detailed_result)

    def test_create_feedback_display_factory(self):
        """Factory function should create UserFeedback instances."""
        from orchestration.user_feedback import create_feedback_display

        feedback_minimal = create_feedback_display("minimal")
        assert feedback_minimal.mode == DisplayMode.MINIMAL

        feedback_detailed = create_feedback_display("detailed")
        assert feedback_detailed.mode == DisplayMode.DETAILED

        # Invalid mode should default to detailed
        feedback_invalid = create_feedback_display("invalid_mode")
        assert feedback_invalid.mode == DisplayMode.DETAILED

    def test_escalation_with_quality_score(self, user_feedback):
        """Escalation should include quality score."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_escalation(
            from_model="haiku",
            to_model="sonnet",
            reason="Quality unter Schwellwert",
            quality_score=0.72
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "0.72" in result or "72" in result

    def test_quality_result_with_escalation_info(self, user_feedback):
        """Quality result should show escalation source if provided."""
        old_stderr = sys.stderr
        sys.stderr = output = StringIO()

        user_feedback.show_quality_result(
            model="sonnet",
            quality_score=0.88,
            escalated_from="haiku"
        )

        sys.stderr = old_stderr
        result = output.getvalue()

        assert "haiku" in result.lower()
        assert "eskaliert" in result.lower() or "⬆️" in result
