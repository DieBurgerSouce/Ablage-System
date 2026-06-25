# -*- coding: utf-8 -*-
"""Unit-Tests fuer den geteilten ReDoS-sicheren Regex-Helfer.

Schuetzt gegen den dokumentierten api-Hang/DoS (KNOWN_ISSUES 2026-06-21):
user-gelieferte Regex-Patterns mit catastrophic backtracking duerfen NIE
unbegrenzt CPU spinnen. Vier Rule/Condition-Evaluatoren fuehrten bisher
`re.search`/`re.match` auf user-Patterns OHNE Schutz aus.
"""

import time

from app.core.safe_regex import (
    MAX_REGEX_LENGTH,
    is_regex_safe,
    safe_match,
    safe_search,
)


class TestIsRegexSafe:
    """Statische Validierung von Patterns vor der Ausfuehrung."""

    def test_rejects_nested_quantifier_redos_pattern(self) -> None:
        safe, msg = is_regex_safe("(a+)+$")
        assert safe is False
        assert msg  # nichtleere Begruendung

    def test_rejects_overlong_pattern(self) -> None:
        safe, msg = is_regex_safe("a" * (MAX_REGEX_LENGTH + 1))
        assert safe is False

    def test_accepts_normal_pattern(self) -> None:
        safe, msg = is_regex_safe(r"Rechnung\s+\d{1,6}")
        assert safe is True
        assert msg == ""

    def test_rejects_invalid_regex_syntax(self) -> None:
        safe, _ = is_regex_safe("(unclosed")
        assert safe is False


class TestSafeSearch:
    """`safe_search` ist ein Drop-in fuer `re.search` mit ReDoS-Schutz."""

    def test_catastrophic_pattern_returns_none_without_hanging(self) -> None:
        # (a+)+$ gegen einen langen Nicht-Match-String = klassischer ReDoS.
        # Muss sofort/innerhalb des Timeouts zurueckkehren (kein CPU-Spin).
        start = time.monotonic()
        result = safe_search("(a+)+$", "a" * 64 + "!", timeout=1.0)
        elapsed = time.monotonic() - start
        assert result is None  # unsicheres Pattern -> kein Match
        assert elapsed < 3.0  # KEIN Hang (grosse Marge ueber dem Timeout)

    def test_normal_pattern_matches(self) -> None:
        result = safe_search("Rechnung", "Das ist eine Rechnung Nr. 5")
        assert result is not None
        assert result.group(0) == "Rechnung"

    def test_no_match_returns_none(self) -> None:
        assert safe_search("XYZ", "abc") is None

    def test_flags_are_applied(self) -> None:
        import re as _re

        assert safe_search("rechnung", "RECHNUNG", flags=_re.IGNORECASE) is not None


class TestSafeMatch:
    """`safe_match` ist ein Drop-in fuer `re.match` (verankert) mit Schutz."""

    def test_catastrophic_pattern_bounded(self) -> None:
        start = time.monotonic()
        result = safe_match("(a+)+$", "a" * 64 + "!", timeout=1.0)
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 3.0

    def test_normal_anchored_match(self) -> None:
        result = safe_match("Rechnung", "Rechnung 5")
        assert result is not None
