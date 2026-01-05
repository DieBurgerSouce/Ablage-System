"""Unit tests for OrchestrationValidator."""

import pytest
import sys
from pathlib import Path

# Add .claude to path so orchestration is a proper package
_claude_path = str(Path(__file__).parent.parent.parent.parent / ".claude")
if _claude_path not in sys.path:
    sys.path.insert(0, _claude_path)

from orchestration.validators import OrchestrationValidator, ValidationError


class TestOrchestrationValidator:
    """Test suite for validation logic."""

    def test_validate_tier_accepts_valid_tiers(self):
        """Should accept valid tier values."""
        for tier in ["opus", "sonnet", "haiku"]:
            error = OrchestrationValidator.validate_tier(tier)
            assert error is None

    def test_validate_tier_rejects_invalid_tier(self):
        """Should reject invalid tier values."""
        error = OrchestrationValidator.validate_tier("invalid_tier")
        assert error is not None
        assert error.severity == "critical"
        assert "invalid_tier" in error.message_de.lower()

    def test_validate_tier_rejects_non_string(self):
        """Should reject non-string tier values."""
        error = OrchestrationValidator.validate_tier(123)
        assert error is not None
        assert error.severity == "critical"
        assert "string" in error.message_de.lower()

    def test_validate_confidence_accepts_valid_range(self):
        """Should accept confidence values between 0.0 and 1.0."""
        for confidence in [0.0, 0.5, 0.75, 0.99, 1.0]:
            error = OrchestrationValidator.validate_confidence(confidence)
            assert error is None

    def test_validate_confidence_rejects_below_zero(self):
        """Should reject negative confidence values."""
        error = OrchestrationValidator.validate_confidence(-0.1)
        assert error is not None
        assert error.severity == "high"
        assert "0.0 und 1.0" in error.message_de

    def test_validate_confidence_rejects_above_one(self):
        """Should reject confidence values above 1.0."""
        error = OrchestrationValidator.validate_confidence(1.5)
        assert error is not None
        assert error.severity == "high"
        assert "0.0 und 1.0" in error.message_de

    def test_validate_confidence_rejects_non_numeric(self):
        """Should reject non-numeric confidence values."""
        error = OrchestrationValidator.validate_confidence("high")
        assert error is not None
        assert error.severity == "critical"
        assert "numerisch" in error.message_de

    def test_validate_file_paths_accepts_valid_paths(self):
        """Should accept valid file path lists."""
        valid_paths = ["app/main.py", "tests/test_main.py", "README.md"]
        error = OrchestrationValidator.validate_file_paths(valid_paths)
        assert error is None

    def test_validate_file_paths_rejects_non_list(self):
        """Should reject non-list file paths."""
        error = OrchestrationValidator.validate_file_paths("not_a_list")
        assert error is not None
        assert error.severity == "critical"
        assert "liste" in error.message_de.lower()

    def test_validate_file_paths_rejects_path_traversal(self):
        """Should reject file paths with path traversal attempts."""
        malicious_paths = ["../../../etc/passwd"]
        error = OrchestrationValidator.validate_file_paths(malicious_paths)
        assert error is not None
        assert error.severity == "critical"
        assert "traversal" in error.message_de.lower()

    def test_validate_file_paths_rejects_absolute_paths(self):
        """Should reject absolute file paths."""
        absolute_paths = ["/etc/passwd"]
        error = OrchestrationValidator.validate_file_paths(absolute_paths)
        assert error is not None
        assert error.severity == "critical"

    def test_validate_file_paths_rejects_backslashes(self):
        """Should reject file paths with backslashes (Windows style)."""
        windows_paths = ["app\\main.py"]
        error = OrchestrationValidator.validate_file_paths(windows_paths)
        assert error is not None
        assert error.severity == "critical"

    def test_validate_task_prompt_accepts_valid_prompts(self):
        """Should accept valid task prompts."""
        valid_prompts = [
            "Fix typo in README",
            "Implement user authentication with JWT tokens",
            "Design distributed caching system"
        ]
        for prompt in valid_prompts:
            error = OrchestrationValidator.validate_task_prompt(prompt)
            assert error is None

    def test_validate_task_prompt_rejects_too_short(self):
        """Should reject prompts that are too short."""
        error = OrchestrationValidator.validate_task_prompt("Fix", min_length=5)
        assert error is not None
        assert error.severity == "high"
        assert "zu kurz" in error.message_de

    def test_validate_task_prompt_rejects_non_string(self):
        """Should reject non-string prompts."""
        error = OrchestrationValidator.validate_task_prompt(12345)
        assert error is not None
        assert error.severity == "critical"
        assert "string" in error.message_de.lower()

    def test_validate_task_prompt_strips_whitespace(self):
        """Should strip whitespace when checking length."""
        error = OrchestrationValidator.validate_task_prompt("   ABC   ", min_length=5)
        assert error is not None  # "ABC" is only 3 chars after strip

    def test_validate_tokens_accepts_valid_counts(self):
        """Should accept valid token counts."""
        for tokens in [0, 100, 1000, 10000, 100000]:
            error = OrchestrationValidator.validate_tokens(tokens)
            assert error is None

    def test_validate_tokens_rejects_negative(self):
        """Should reject negative token counts."""
        error = OrchestrationValidator.validate_tokens(-100)
        assert error is not None
        assert error.severity == "critical"
        assert "negativ" in error.message_de

    def test_validate_tokens_rejects_non_integer(self):
        """Should reject non-integer token counts."""
        error = OrchestrationValidator.validate_tokens(100.5)
        assert error is not None
        assert error.severity == "critical"
        assert "integer" in error.message_de.lower()

    def test_validate_tokens_rejects_excessive_counts(self):
        """Should reject excessively large token counts."""
        error = OrchestrationValidator.validate_tokens(2000000, max_tokens=1000000)
        assert error is not None
        assert error.severity == "high"
        assert "zu hoch" in error.message_de

    def test_validation_error_structure(self):
        """ValidationError should have all required fields."""
        error = ValidationError(
            field="test_field",
            message_de="Test-Nachricht",
            severity="high"
        )

        assert error.field == "test_field"
        assert error.message_de == "Test-Nachricht"
        assert error.severity == "high"

    def test_custom_field_name_in_tier_validation(self):
        """Should use custom field name in error message."""
        error = OrchestrationValidator.validate_tier("invalid", field_name="model_tier")
        assert error is not None
        assert "model_tier" in error.message_de

    def test_custom_field_name_in_confidence_validation(self):
        """Should use custom field name in error message."""
        error = OrchestrationValidator.validate_confidence(-0.5, field_name="quality_score")
        assert error is not None
        assert "quality_score" in error.message_de

    def test_validate_file_paths_with_mixed_issues(self):
        """Should catch first issue in file path list."""
        # First path is valid, second has path traversal
        mixed_paths = ["app/main.py", "../etc/passwd"]
        error = OrchestrationValidator.validate_file_paths(mixed_paths)
        assert error is not None
        assert error.severity == "critical"

    def test_validate_file_paths_with_non_string_element(self):
        """Should reject file path list with non-string elements."""
        mixed_types = ["app/main.py", 123, "tests/test.py"]
        error = OrchestrationValidator.validate_file_paths(mixed_types)
        assert error is not None
        assert error.severity == "high"
        assert "string" in error.message_de.lower()

    def test_empty_file_paths_list_is_valid(self):
        """Empty file paths list should be valid."""
        error = OrchestrationValidator.validate_file_paths([])
        assert error is None

    def test_validate_tokens_with_custom_max(self):
        """Should use custom max_tokens parameter."""
        error = OrchestrationValidator.validate_tokens(5000, max_tokens=1000)
        assert error is not None
        assert error.severity == "high"

    def test_validation_error_severity_levels(self):
        """ValidationError should support all severity levels."""
        severities = ["critical", "high", "medium", "low"]
        for severity in severities:
            error = ValidationError(
                field="test",
                message_de="Test",
                severity=severity
            )
            assert error.severity == severity

    def test_german_error_messages_comprehensive(self):
        """All error messages should be in German."""
        # Test various validation failures
        errors = [
            OrchestrationValidator.validate_tier("invalid"),
            OrchestrationValidator.validate_confidence(2.0),
            OrchestrationValidator.validate_file_paths(["../evil"]),
            OrchestrationValidator.validate_task_prompt(""),
            OrchestrationValidator.validate_tokens(-1)
        ]

        for error in errors:
            if error is not None:
                # Check for German language markers (umlauts, German words)
                message = error.message_de
                german_indicators = ["muss", "nicht", "zwischen", "ungültig", "ü", "ä", "ö", "ß"]
                has_german = any(indicator in message.lower() for indicator in german_indicators)
                assert has_german, f"Error message not in German: {message}"

    def test_validate_tier_case_sensitive(self):
        """Tier validation should be case sensitive."""
        error = OrchestrationValidator.validate_tier("Opus")  # Capital O
        assert error is not None
        assert error.severity == "critical"

    def test_validate_confidence_integer_acceptable(self):
        """Integer confidence values (0 or 1) should be acceptable."""
        error_zero = OrchestrationValidator.validate_confidence(0)
        error_one = OrchestrationValidator.validate_confidence(1)

        assert error_zero is None
        assert error_one is None

    def test_validation_error_field_name_in_message(self):
        """Validation errors should include field name in message."""
        error = OrchestrationValidator.validate_tier("invalid", field_name="selected_tier")
        assert error is not None
        assert "selected_tier" in error.message_de

    def test_file_paths_index_in_error_message(self):
        """File path errors should include array index."""
        paths = ["valid.py", 123]  # Second element is invalid
        error = OrchestrationValidator.validate_file_paths(paths)
        assert error is not None
        assert "[1]" in error.field  # Index of invalid element
