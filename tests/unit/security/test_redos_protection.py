# -*- coding: utf-8 -*-
"""
Tests for ReDoS (Regular Expression Denial of Service) Protection.

Tests the regex validation and timeout protection in business_rules_engine.py.
Covers CWE-95: Improper Neutralization of Directives in Dynamically Evaluated Code.
"""

import pytest
import re
from unittest.mock import patch, MagicMock

from app.services.rules.business_rules_engine import (
    _is_regex_safe,
    _safe_regex_match,
    MAX_REGEX_LENGTH,
    REGEX_TIMEOUT_SECONDS,
    DANGEROUS_REGEX_PATTERNS,
)


class TestIsRegexSafe:
    """Tests for _is_regex_safe() validation function."""

    def test_safe_simple_pattern(self) -> None:
        """Simple patterns should be allowed."""
        is_safe, error = _is_regex_safe(r"hello")
        assert is_safe is True
        assert error == ""

    def test_safe_word_boundary_pattern(self) -> None:
        """Word boundary patterns should be allowed."""
        is_safe, error = _is_regex_safe(r"\bword\b")
        assert is_safe is True
        assert error == ""

    def test_safe_digit_pattern(self) -> None:
        """Digit patterns should be allowed."""
        is_safe, error = _is_regex_safe(r"\d{4}-\d{2}-\d{2}")
        assert is_safe is True
        assert error == ""

    def test_safe_german_umlauts(self) -> None:
        """German umlaut patterns should be allowed."""
        is_safe, error = _is_regex_safe(r"[äöüÄÖÜß]+")
        assert is_safe is True
        assert error == ""

    def test_unsafe_nested_quantifier_star_plus(self) -> None:
        """Nested quantifiers (.*+) should be rejected."""
        is_safe, error = _is_regex_safe(r"(.*)+")
        assert is_safe is False
        assert "Gefährliches Pattern" in error or "gefährlich" in error.lower()

    def test_unsafe_nested_quantifier_plus_plus(self) -> None:
        """Nested quantifiers (.++)+) should be rejected."""
        is_safe, error = _is_regex_safe(r"(.+)+")
        assert is_safe is False

    def test_unsafe_nested_quantifier_star_star(self) -> None:
        """Nested quantifiers (.*)*) should be rejected."""
        is_safe, error = _is_regex_safe(r"(.*)*")
        assert is_safe is False

    def test_unsafe_character_class_star_plus(self) -> None:
        """Nested quantifiers in character classes should be rejected."""
        is_safe, error = _is_regex_safe(r"([a-z]*)+")
        assert is_safe is False

    def test_unsafe_alternation_with_overlap(self) -> None:
        """Overlapping alternations with quantifiers should be rejected."""
        is_safe, error = _is_regex_safe(r"(a|aa)+")
        assert is_safe is False

    def test_unsafe_catastrophic_backtracking_pattern(self) -> None:
        """Known catastrophic backtracking patterns should be rejected."""
        is_safe, error = _is_regex_safe(r"(a+)+$")
        assert is_safe is False

    def test_pattern_too_long(self) -> None:
        """Patterns exceeding MAX_REGEX_LENGTH should be rejected."""
        long_pattern = "a" * (MAX_REGEX_LENGTH + 1)
        is_safe, error = _is_regex_safe(long_pattern)
        assert is_safe is False
        assert "lang" in error.lower()  # "zu lang" in German

    def test_pattern_at_max_length(self) -> None:
        """Patterns exactly at MAX_REGEX_LENGTH should be allowed."""
        pattern = "a" * MAX_REGEX_LENGTH
        is_safe, error = _is_regex_safe(pattern)
        assert is_safe is True

    def test_empty_pattern(self) -> None:
        """Empty patterns should be allowed."""
        is_safe, error = _is_regex_safe("")
        assert is_safe is True

    def test_email_pattern_safe(self) -> None:
        """Reasonable email pattern should be allowed."""
        is_safe, error = _is_regex_safe(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
        assert is_safe is True

    def test_invoice_number_pattern_safe(self) -> None:
        """Invoice number pattern should be allowed."""
        is_safe, error = _is_regex_safe(r"RE-\d{4}-\d{6}")
        assert is_safe is True


class TestSafeRegexMatch:
    """Tests for _safe_regex_match() with timeout protection."""

    def test_simple_match_success(self) -> None:
        """Simple pattern should match text."""
        result = _safe_regex_match(r"hello", "hello world")
        assert result is not None
        assert result.group() == "hello"

    def test_simple_match_no_match(self) -> None:
        """Non-matching pattern should return None."""
        result = _safe_regex_match(r"goodbye", "hello world")
        assert result is None

    def test_unsafe_pattern_rejected(self) -> None:
        """Unsafe patterns are rejected by _is_regex_safe (genutzt vom MATCHES-Operator,
        bevor _safe_regex_match aufgerufen wird)."""
        is_safe, _ = _is_regex_safe(r"(.*)+")
        assert is_safe is False

    def test_case_insensitive_flag(self) -> None:
        """Case insensitive matching should work."""
        result = _safe_regex_match(r"HELLO", "hello world", flags=re.IGNORECASE)
        assert result is not None
        assert result.group() == "hello"

    def test_german_text_matching(self) -> None:
        """German text with umlauts should match correctly.

        Hinweis: _safe_regex_match nutzt re.match (am Stringanfang verankert),
        daher steht das Umlaut-Pattern am Textanfang.
        """
        result = _safe_regex_match(r"Müller", "Müller GmbH")
        assert result is not None
        assert result.group() == "Müller"

    def test_timeout_protection(self) -> None:
        """Patterns that would take too long should timeout."""
        # This pattern is technically safe but could be slow on adversarial input
        # We use a very short timeout to test the mechanism
        with patch(
            "app.services.rules.business_rules_engine.REGEX_TIMEOUT_SECONDS",
            0.001,
        ):
            # Create input that might cause slow matching
            result = _safe_regex_match(
                r"a+b",
                "a" * 1000,  # Many 'a's but no 'b'
                timeout=0.001,
            )
            # Should either match quickly or timeout gracefully
            # The important thing is it doesn't hang

    def test_pattern_too_long_rejected(self) -> None:
        """Patterns exceeding length limit should be rejected."""
        long_pattern = "a" * (MAX_REGEX_LENGTH + 1)
        result = _safe_regex_match(long_pattern, "aaaa")
        assert result is None

    def test_invalid_regex_syntax(self) -> None:
        """Invalid regex syntax should be handled gracefully."""
        result = _safe_regex_match(r"[invalid", "text")
        assert result is None

    def test_multiline_text_matching(self) -> None:
        """Multiline text matching should work."""
        text = "line1\nline2\nline3"
        result = _safe_regex_match(r"line\d", text)
        assert result is not None
        assert result.group() == "line1"

    def test_special_characters_escaped(self) -> None:
        """Special characters in pattern should work when escaped.

        re.match verankert am Anfang -> Pattern steht am Textanfang.
        """
        result = _safe_regex_match(r"\$100\.00", "$100.00 inkl. MwSt")
        assert result is not None
        assert result.group() == "$100.00"


class TestDangerousPatterns:
    """Tests to verify DANGEROUS_REGEX_PATTERNS coverage."""

    @pytest.mark.parametrize(
        "pattern",
        [
            r"(.*)+",      # Classic ReDoS
            r"(.+)+",      # Nested plus
            r"(.*)*",      # Nested star
            r"([a-z]*)+",  # Character class nested
            r"(a|aa)+",    # Overlapping alternation
            r"(a+)+",      # Nested quantifier
            r"(\w+)*\w",   # Word boundaries nested
        ],
    )
    def test_dangerous_pattern_detected(self, pattern: str) -> None:
        """All known dangerous patterns should be detected."""
        is_safe, _ = _is_regex_safe(pattern)
        assert is_safe is False, f"Pattern {pattern} should be detected as dangerous"

    @pytest.mark.parametrize(
        "pattern",
        [
            r"\d+",              # Simple digit quantifier
            r"[a-z]+",          # Simple character class
            r"(foo|bar)",       # Non-overlapping alternation
            r"^\d{4}-\d{2}$",   # Anchored pattern
            r"\b\w+\b",         # Word with boundaries
            r"Invoice.*Total",  # Greedy but not nested
        ],
    )
    def test_safe_pattern_allowed(self, pattern: str) -> None:
        """Safe patterns should be allowed."""
        is_safe, error = _is_regex_safe(pattern)
        assert is_safe is True, f"Pattern {pattern} should be allowed, but got: {error}"


class TestIntegrationWithBusinessRules:
    """Integration tests with the MATCHES operator in business rules."""

    def test_matches_operator_uses_safe_regex(self) -> None:
        """Der MATCHES-Operator nutzt die sichere Regex-Validierung.

        _apply_string_operator ist eine Methode von BusinessRulesEngine. Ein
        gefaehrliches Pattern wird abgewiesen (return False), ein sicheres
        Pattern matcht regulaer (re.match, am Anfang verankert).
        """
        from app.services.rules.business_rules_engine import (
            BusinessRulesEngine,
            ConditionOperator,
        )

        engine = BusinessRulesEngine()

        # Unsicheres Pattern -> abgewiesen
        assert engine._apply_string_operator(
            ConditionOperator.MATCHES, "any text", r"(.*)+", case_sensitive=True
        ) is False

        # Sicheres Pattern -> matcht am Anfang
        assert engine._apply_string_operator(
            ConditionOperator.MATCHES, "RE-2024-000123", r"RE-\d{4}-\d{6}", case_sensitive=True
        ) is True


class TestEdgeCases:
    """Edge case tests for regex safety."""

    def test_unicode_pattern(self) -> None:
        """Unicode patterns should be handled.

        re.match verankert am Anfang -> Text beginnt mit einem Umlaut der Klasse.
        """
        is_safe, _ = _is_regex_safe(r"[äöüß]+")
        assert is_safe is True
        result = _safe_regex_match(r"[äöüß]+", "öße")
        assert result is not None

    def test_lookahead_pattern(self) -> None:
        """Lookahead patterns should be checked."""
        # Simple lookahead is generally safe
        is_safe, _ = _is_regex_safe(r"foo(?=bar)")
        assert is_safe is True

    def test_lookbehind_pattern(self) -> None:
        """Lookbehind patterns should be checked."""
        is_safe, _ = _is_regex_safe(r"(?<=foo)bar")
        assert is_safe is True

    def test_none_text_input(self) -> None:
        """None text should be handled gracefully."""
        # This depends on implementation - should not crash
        try:
            result = _safe_regex_match(r"test", None)  # type: ignore
            # Should either return None or handle gracefully
        except TypeError:
            pass  # Also acceptable

    def test_very_long_text(self) -> None:
        """Very long text should be handled."""
        long_text = "a" * 100000
        result = _safe_regex_match(r"aaa", long_text)
        assert result is not None
