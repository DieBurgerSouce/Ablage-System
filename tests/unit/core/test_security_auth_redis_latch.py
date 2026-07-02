"""
Tests für W2.2 — Redis-Fail-closed-Robustheit in ``app.core.security_auth``.

Deckt ab:
- ``_get_redis_client``: TTL-Backoff statt permanentem Latch (monotone Uhr).
  Nach einem Verbindungsfehler wird für <30 s NICHT erneut verbunden, danach
  wird ein Reconnect versucht (früher: permanent unavailable bis Neustart).
- ``is_token_blacklisted_redis``: genau EIN sofortiger Retry bei transientem
  Redis-Fehler; scheitert auch der Retry (oder ist der Fehler nicht transient),
  bleibt die fail-closed-Semantik (HTTP 503) vollständig erhalten.

Die Tests folgen dem Muster der bestehenden security_auth-Tests
(``unittest.mock`` mit ``AsyncMock``/``patch``; kein fakeredis).
"""

import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core import security_auth as sa  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_redis_globals():
    """Modul-Globals vor/nach jedem Test sichern und wiederherstellen.

    Verhindert, dass die (bewusst prozessweiten) Redis-Client-/Backoff-Globals
    zwischen Tests lecken.
    """
    orig_client = sa._redis_client
    orig_available = sa._redis_available
    orig_backoff = sa._redis_backoff_until
    # Sauberer Ausgangszustand für Determinismus.
    sa._redis_client = None
    sa._redis_available = None
    sa._redis_backoff_until = None
    try:
        yield
    finally:
        sa._redis_client = orig_client
        sa._redis_available = orig_available
        sa._redis_backoff_until = orig_backoff


class TestBackoffConfiguration:
    """Konfigurations-Invarianten des Robustheits-Fixes."""

    def test_backoff_constant_is_sane(self):
        assert sa.REDIS_RECONNECT_BACKOFF_SECONDS == 30.0

    def test_transient_errors_include_connection_and_timeout(self):
        # Builtins müssen immer als transient gelten (Retry-würdig).
        assert ConnectionError in sa._TRANSIENT_REDIS_ERRORS
        assert TimeoutError in sa._TRANSIENT_REDIS_ERRORS
        # Nicht-transiente Fehler dürfen NICHT enthalten sein.
        assert RuntimeError not in sa._TRANSIENT_REDIS_ERRORS


@pytest.mark.asyncio
class TestGetRedisClientBackoff:
    """(c) TTL-Backoff statt permanentem Latch."""

    async def test_no_permanent_latch_reconnect_after_backoff(self):
        """Fehler -> <30 s kein Reconnect -> nach Ablauf Reconnect erfolgreich."""
        with patch("app.core.redis_state.RedisStateManager") as MockRSM, \
                patch.object(sa, "time") as mock_time:
            manager = MagicMock()
            manager.connect = AsyncMock(side_effect=ConnectionError("redis down"))
            manager.ping = AsyncMock(return_value=True)
            manager._redis = object()  # Sentinel-Client
            MockRSM.get_instance.return_value = manager

            # Call 1 (t=1000): Verbindung schlägt fehl -> None, Backoff = 1030.
            mock_time.monotonic.return_value = 1000.0
            r1 = await sa._get_redis_client()
            assert r1 is None
            assert sa._redis_available is False
            assert sa._redis_backoff_until == 1000.0 + sa.REDIS_RECONNECT_BACKOFF_SECONDS

            # Call 2 (t=1010 < 1030): innerhalb Backoff -> None, KEIN Reconnect.
            MockRSM.get_instance.reset_mock()
            mock_time.monotonic.return_value = 1010.0
            r2 = await sa._get_redis_client()
            assert r2 is None
            MockRSM.get_instance.assert_not_called()  # Backoff aktiv

            # Call 3 (t=1031 > 1030): Backoff abgelaufen -> Reconnect, jetzt Erfolg.
            manager.connect = AsyncMock()  # Verbindung klappt nun
            mock_time.monotonic.return_value = 1031.0
            r3 = await sa._get_redis_client()
            assert r3 is manager._redis
            assert sa._redis_available is True
            assert sa._redis_backoff_until is None
            MockRSM.get_instance.assert_called()  # Reconnect wurde versucht

    async def test_manual_unavailable_without_backoff_stays_none(self):
        """Extern gesetztes _redis_available=False (ohne Backoff) bleibt hart None.

        Bewahrt die bestehende Test-Semantik (kein unerwarteter Auto-Reconnect).
        """
        sa._redis_client = None
        sa._redis_available = False
        sa._redis_backoff_until = None
        with patch("app.core.redis_state.RedisStateManager") as MockRSM:
            result = await sa._get_redis_client()
            assert result is None
            MockRSM.get_instance.assert_not_called()


@pytest.mark.asyncio
class TestIsTokenBlacklistedRedisRetry:
    """(a)/(b)/(d) Single-Retry + erhaltene fail-closed-Semantik."""

    async def test_transient_error_then_success_no_503(self):
        """(a) 1. Fehler (transient) -> Retry -> Erfolg = kein 503."""
        mock_redis = AsyncMock()
        # 1. Aufruf wirft transienten Fehler, 2. Aufruf liefert 0 (nicht gelistet).
        mock_redis.exists = AsyncMock(side_effect=[ConnectionError("blip"), 0])

        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await sa.is_token_blacklisted_redis("jti-transient-ok")

        assert result is False  # kein 503, korrekt "nicht geblacklisted"
        assert mock_redis.exists.await_count == 2  # Erstversuch + genau 1 Retry

    async def test_transient_error_then_retry_detects_blacklist(self):
        """(d) Nach transientem Fehler + Retry wird ein gelisteter Token abgelehnt."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=[TimeoutError("blip"), 1])

        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await sa.is_token_blacklisted_redis("jti-blacklisted-after-retry")

        assert result is True
        assert mock_redis.exists.await_count == 2

    async def test_both_attempts_fail_transient_raises_503(self):
        """(b) Beide Versuche scheitern (transient) -> fail-closed 503 bleibt."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=ConnectionError("still down"))

        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=mock_redis)), \
                patch.object(sa, "TOKEN_BLACKLIST_FAIL_CLOSED", True):
            with pytest.raises(HTTPException) as exc_info:
                await sa.is_token_blacklisted_redis("jti-fail-closed")

        assert exc_info.value.status_code == 503
        assert mock_redis.exists.await_count == 2  # genau 1 Retry, dann 503

    async def test_non_transient_error_does_not_retry_and_raises_503(self):
        """Nicht-transienter Fehler -> KEIN Retry -> fail-closed 503."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=RuntimeError("logic error"))

        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=mock_redis)), \
                patch.object(sa, "TOKEN_BLACKLIST_FAIL_CLOSED", True):
            with pytest.raises(HTTPException) as exc_info:
                await sa.is_token_blacklisted_redis("jti-non-transient")

        assert exc_info.value.status_code == 503
        assert mock_redis.exists.await_count == 1  # kein Retry bei nicht-transient

    async def test_blacklisted_token_still_rejected_happy_path(self):
        """(d) Ohne Fehler wird ein gelisteter Token weiterhin abgelehnt."""
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)

        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=mock_redis)):
            result = await sa.is_token_blacklisted_redis("jti-listed")

        assert result is True
        assert mock_redis.exists.await_count == 1

    async def test_fail_closed_when_client_unavailable(self):
        """Redis-Client None + fail-closed -> 503 (unveränderte Semantik)."""
        with patch.object(sa, "_get_redis_client", AsyncMock(return_value=None)), \
                patch.object(sa, "TOKEN_BLACKLIST_FAIL_CLOSED", True):
            with pytest.raises(HTTPException) as exc_info:
                await sa.is_token_blacklisted_redis("jti-no-client")

        assert exc_info.value.status_code == 503
