"""
Regressionstest fuer den systemischen Logger-Bug rund um ``safe_error_log``.

Hintergrund (Welle 6c + Folge-Welle):
``app.core.safe_errors.safe_error_log(e)`` liefert IMMER ein Dict, das bereits
den Schluessel ``error_type`` enthaelt. Logger-Aufrufe der Form

    logger.error("...", error_type=type(e).__name__, **safe_error_log(e))

uebergaben ``error_type`` damit DOPPELT und crashten ZUR LAUFZEIT im jeweiligen
except-Handler mit:

    TypeError: ... got multiple values for keyword argument 'error_type'

Dadurch wurde der Original-Fehler maskiert und ein neuer TypeError geworfen.

Die Produktion nutzt durchgaengig ``structlog`` (``structlog.get_logger(...)``),
dessen Bound-Logger beliebige Keyword-Argumente akzeptieren. Genau deshalb ist
die doppelte ``error_type``-Bindung dort der reale Crash-Pfad. Dieser Test
modelliert daher bewusst structlog (nicht stdlib ``logging``).

Der Test fixiert:
  1. die Invariante: ``error_type`` ist immer Teil des safe_error_log-Dicts,
  2. dass der alte (fehlerhafte) Aufruf-Stil garantiert den TypeError ausloest,
  3. dass der korrigierte Aufruf-Stil sauber loggt (inkl. error_type) ohne Crash.
"""

from __future__ import annotations

import structlog

import pytest

from app.core.safe_errors import safe_error_log


def test_safe_error_log_always_provides_error_type_key() -> None:
    """safe_error_log liefert ``error_type`` IMMER selbst (Ursache des Bugs)."""
    try:
        raise ValueError("kaputt")
    except ValueError as exc:
        payload = safe_error_log(exc)

    assert "error_type" in payload
    assert payload["error_type"] == "ValueError"
    # error_id ist zur Korrelation immer vorhanden
    assert "error_id" in payload


def _log_buggy(logger, exc: Exception) -> None:
    """Reproduziert den alten, fehlerhaften Aufruf-Stil (error_type doppelt)."""
    logger.error("op_failed", error_type=type(exc).__name__, **safe_error_log(exc))


def _log_fixed(logger, exc: Exception) -> None:
    """Korrigierter Aufruf-Stil: error_type kommt ausschliesslich aus safe_error_log."""
    logger.error("op_failed", **safe_error_log(exc))


def test_buggy_call_shape_raises_on_duplicate_error_type_kwarg() -> None:
    """Der alte Stil MUSS am doppelten ``error_type``-Argument crashen.

    Die Kollision entsteht bereits bei der Argument-Bindung des Aufrufs: ein
    explizites ``error_type=`` plus ein ``**mapping``, das ``error_type`` ebenfalls
    enthaelt. CPython meldet dies -- je nach Aufruf-Form -- als ``TypeError``
    ("got multiple values for keyword argument 'error_type'") oder ``KeyError``.
    Beides ist exakt der Produktions-Crash, der den Original-Fehler maskierte.

    Wir verwenden eine stellvertretende ``error``-Methode mit derselben
    Signatur-Form (`event` + ``**kwargs``) wie ein structlog-Bound-Logger, damit
    der Test backend-/konfigurationsunabhaengig deterministisch ist.
    """

    class _BoundLoggerLike:
        def error(self, event: str, /, **kwargs: object) -> None:  # pragma: no cover - body irrelevant
            return None

    logger = _BoundLoggerLike()
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with pytest.raises((TypeError, KeyError)) as excinfo:
            _log_buggy(logger, exc)

    assert "error_type" in str(excinfo.value)


def test_fixed_call_shape_logs_without_typeerror() -> None:
    """Der korrigierte Stil loggt sauber inkl. error_type, ohne TypeError."""
    logger = structlog.get_logger("ablage.regression.fixed")

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with structlog.testing.capture_logs() as captured:
            # Darf NICHT werfen.
            _log_fixed(logger, exc)

    assert len(captured) == 1
    entry = captured[0]
    assert entry["event"] == "op_failed"
    assert entry["log_level"] == "error"
    # error_type wurde von safe_error_log beigesteuert.
    assert entry["error_type"] == "RuntimeError"
    assert "error_id" in entry
