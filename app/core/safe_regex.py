# -*- coding: utf-8 -*-
"""ReDoS-sicherer Regex-Helfer (geteilt).

Schuetzt gegen den dokumentierten api-Hang/DoS (KNOWN_ISSUES 2026-06-21):
user-gelieferte Regex-Patterns koennen via catastrophic backtracking einen
CPU-Spin ausloesen (z. B. `(a+)+$` gegen einen langen Nicht-Match-String).
Python's `re` hat KEIN eingebautes Timeout, daher kombinieren wir:

1. **Statische Validierung** (`is_regex_safe`): Laengen-Cap + Denylist
   bekannter ReDoS-Muster + Compile-Check.
2. **Ausfuehrungs-Timeout** (`safe_search`/`safe_match`): Backstop ueber
   einen ThreadPoolExecutor, falls ein Pattern die Denylist passiert,
   aber dennoch langsam ist.

Diese Logik existierte bereits in `app/services/rules/business_rules_engine.py`,
wurde aber NICHT von den uebrigen Rule/Condition-Evaluatoren genutzt
(notification/rule_engine, auto_filing, workflow/condition_evaluator,
imports/import_rule_service). Dieser Modul konsolidiert sie (DRY) als
Drop-in-Ersatz fuer `re.search`/`re.match` auf user-kontrollierten Patterns.

Bewusst nur Standardbibliothek (re, concurrent.futures, logging) — kein
App-Import, damit der Helfer ueberall ohne Zyklen nutzbar und isoliert
testbar ist.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximale Pattern-Laenge (Schutz vor Ressourcen-Erschoepfung).
MAX_REGEX_LENGTH: int = 200

# Maximale Ausfuehrungszeit pro Regex-Operation (Sekunden).
REGEX_TIMEOUT_SECONDS: float = 1.0

# Bekannte ReDoS-gefaehrliche Muster (catastrophic backtracking).
DANGEROUS_REGEX_PATTERNS: Tuple[str, ...] = (
    r"\(\.\*\)\+",      # (.*)+
    r"\(\.\+\)\+",      # (.+)+
    r"\(\.\*\)\*",      # (.*)*
    r"\(\.\+\)\*",      # (.+)*
    r"\+\+",            # ++
    r"\*\*",            # **
    r"\{\d+,\}\+",      # {n,}+
    r"\(\[.+\]\+\)\+",  # ([...]+)+
    r"\(\w\+\)\+",      # (\w+)+
    r"\(\d\+\)\+",      # (\d+)+
    r"\(\s\+\)\+",      # (\s+)+
    # Allgemein: Gruppe, deren Inhalt mit *|+ endet, gefolgt von *|+ aussen.
    # Faengt (a+)+, (a*)*, (a+)*, (.*)+, ([a-z]*)+, (\w+)*, ((a+)+)+ etc. ab.
    r"\([^()]*[*+]\)[*+]",
    # Char-Klasse mit verschachteltem Quantifier: ([...]*)+ / ([...]+)+
    r"\(\[[^\]]*\][*+]\)[*+]",
    # Ueberlappende Alternation mit Quantifier: (a|a)+ / (a|aa)+
    r"\([^)]*\|[^)]*\)[*+]",
    # Gruppe mit innerem *|+ und {n,}-Wiederholung: (.*a){10,}
    r"\([^()]*[*+][^()]*\)\{\d+,?\d*\}",
)


def is_regex_safe(pattern: str) -> Tuple[bool, str]:
    """Validiert ein Regex-Pattern gegen ReDoS-Angriffe.

    Args:
        pattern: Das zu pruefende Pattern.

    Returns:
        Tupel (is_safe, error_message). Bei is_safe=True ist error_message "".
    """
    if len(pattern) > MAX_REGEX_LENGTH:
        return False, f"Regex zu lang (max {MAX_REGEX_LENGTH} Zeichen)"

    for dangerous in DANGEROUS_REGEX_PATTERNS:
        if re.search(dangerous, pattern):
            return False, "Gefaehrliches Regex-Pattern erkannt (ReDoS-Risiko)"

    try:
        re.compile(pattern)
    except re.error as exc:
        return False, f"Ungueltiges Regex-Pattern: {exc}"

    return True, ""


def _run_with_timeout(
    func: Callable[[], Optional["re.Match[str]"]],
    pattern: str,
    text: str,
    timeout: float,
) -> Optional["re.Match[str]"]:
    """Fuehrt eine Regex-Operation mit hartem Timeout aus.

    Gibt bei Timeout oder re.error None zurueck (fail-safe: kein Match).
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            logger.warning(
                "regex_timeout pattern_length=%d text_length=%d",
                len(pattern),
                len(text),
            )
            return None
        except re.error:
            return None


def safe_search(
    pattern: str,
    text: str,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SECONDS,
) -> Optional["re.Match[str]"]:
    """ReDoS-sicherer Ersatz fuer `re.search`.

    Validiert das Pattern (Denylist + Laengen-Cap); unsichere Patterns
    liefern None (kein Match). Sichere Patterns laufen mit Timeout-Backstop.
    """
    safe, _msg = is_regex_safe(pattern)
    if not safe:
        return None
    return _run_with_timeout(
        lambda: re.search(pattern, text, flags), pattern, text, timeout
    )


def safe_match(
    pattern: str,
    text: str,
    flags: int = 0,
    timeout: float = REGEX_TIMEOUT_SECONDS,
) -> Optional["re.Match[str]"]:
    """ReDoS-sicherer Ersatz fuer `re.match` (verankert am String-Anfang)."""
    safe, _msg = is_regex_safe(pattern)
    if not safe:
        return None
    return _run_with_timeout(
        lambda: re.match(pattern, text, flags), pattern, text, timeout
    )
