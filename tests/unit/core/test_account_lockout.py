"""Unit tests für Account-Lockout-System.

Testet Brute-Force-Schutz mit exponentiellem Backoff.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

from app.core.account_lockout import (
    check_account_lockout,
    record_failed_attempt,
    reset_failed_attempts,
    admin_unlock_account,
    get_lockout_status,
    _calculate_lockout_duration,
    _create_identifier,
    _format_lockout_message,
    MAX_FAILED_ATTEMPTS,
    ALERT_THRESHOLD,
    _failed_attempts_fallback,
    _lockout_until_fallback,
    AccountLockoutStorageError,
)


class TestLockoutDurationCalculation:
    """Tests für Sperrdauer-Berechnung."""

    def test_no_lockout_under_max_attempts(self):
        """Unter MAX_FAILED_ATTEMPTS sollte keine Sperre erfolgen."""
        for attempts in range(1, MAX_FAILED_ATTEMPTS):
            duration = _calculate_lockout_duration(attempts)
            assert duration == 0, f"Attempt {attempts} should not trigger lockout"

    def test_lockout_at_max_attempts(self):
        """Bei MAX_FAILED_ATTEMPTS sollte 1 Minute Sperre erfolgen."""
        duration = _calculate_lockout_duration(MAX_FAILED_ATTEMPTS)
        assert duration == 60  # 1 Minute

    def test_exponential_backoff(self):
        """Exponentielle Erhöhung der Sperrdauer."""
        assert _calculate_lockout_duration(5) == 60    # 1 Minute
        assert _calculate_lockout_duration(6) == 300   # 5 Minuten
        assert _calculate_lockout_duration(7) == 900   # 15 Minuten
        assert _calculate_lockout_duration(8) == 3600  # 1 Stunde

    def test_max_lockout_duration(self):
        """Sperrdauer sollte bei 1 Stunde gedeckelt sein."""
        assert _calculate_lockout_duration(100) == 3600
        assert _calculate_lockout_duration(1000) == 3600


class TestIdentifierCreation:
    """Tests für Identifier-Erstellung."""

    def test_identifier_with_ip_and_username(self):
        """Identifier sollte IP und Username kombinieren."""
        identifier = _create_identifier("192.168.1.1", "test@example.com")

        assert "ip:192.168.1.1" in identifier
        assert "user:test@example.com" in identifier

    def test_identifier_with_ip_only(self):
        """Identifier nur mit IP sollte funktionieren."""
        identifier = _create_identifier("192.168.1.1", None)

        assert "ip:192.168.1.1" in identifier
        assert "user:" not in identifier

    def test_identifier_with_username_only(self):
        """Identifier nur mit Username sollte funktionieren."""
        identifier = _create_identifier(None, "test@example.com")

        assert "ip:" not in identifier
        assert "user:test@example.com" in identifier

    def test_identifier_normalizes_username(self):
        """Username sollte lowercase normalisiert werden."""
        identifier = _create_identifier(None, "Test@Example.COM")

        assert "user:test@example.com" in identifier

    def test_empty_identifier(self):
        """Ohne IP und Username sollte 'unknown' zurückgeben."""
        identifier = _create_identifier(None, None)

        assert identifier == "unknown"


class TestLockoutMessage:
    """Tests für Lockout-Nachrichten."""

    def test_message_hours(self):
        """Nachricht sollte Stunden korrekt anzeigen."""
        message = _format_lockout_message(3600)

        assert "1 Stunde" in message
        assert "gesperrt" in message.lower()

    def test_message_minutes(self):
        """Nachricht sollte Minuten korrekt anzeigen."""
        message = _format_lockout_message(300)

        assert "5 Minute" in message

    def test_message_seconds(self):
        """Nachricht sollte Sekunden korrekt anzeigen."""
        message = _format_lockout_message(30)

        assert "30 Sekunden" in message


class TestAccountLockoutInMemory:
    """Tests für Account-Lockout mit In-Memory-Fallback."""

    @pytest.fixture(autouse=True)
    def clear_fallback(self):
        """Fallback-Dicts vor jedem Test leeren."""
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()
        yield
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()

    @pytest.fixture
    def mock_redis_unavailable(self):
        """Mock Redis als nicht verfügbar."""
        with patch("app.core.account_lockout._get_redis_client", new_callable=AsyncMock) as mock:
            mock.return_value = None
            yield mock

    @pytest.mark.asyncio
    async def test_first_failed_attempt(self, mock_redis_unavailable):
        """Erster Fehlversuch sollte gezählt werden."""
        # Use fail_closed=False to test in-memory fallback behavior
        attempts, is_locked, duration = await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False  # Allow fallback to in-memory
        )

        assert attempts == 1
        assert is_locked is False
        assert duration is None

    @pytest.mark.asyncio
    async def test_lockout_after_max_attempts(self, mock_redis_unavailable):
        """Nach MAX_FAILED_ATTEMPTS sollte Sperre erfolgen."""
        # Simulate 5 failed attempts with fail_closed=False for in-memory fallback
        for i in range(MAX_FAILED_ATTEMPTS - 1):
            await record_failed_attempt(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=False
            )

        # The 5th attempt should trigger lockout
        attempts, is_locked, duration = await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert attempts == MAX_FAILED_ATTEMPTS
        assert is_locked is True
        assert duration == 60  # 1 Minute

    @pytest.mark.asyncio
    async def test_check_lockout_when_locked(self, mock_redis_unavailable):
        """Gesperrtes Konto sollte als gesperrt erkannt werden."""
        identifier = _create_identifier("192.168.1.1", "test@example.com")
        _lockout_until_fallback[identifier] = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Use fail_closed=False to test in-memory fallback behavior
        is_locked, remaining, message = await check_account_lockout(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert is_locked is True
        assert remaining is not None
        assert remaining > 0
        assert remaining <= 300
        assert message is not None

    @pytest.mark.asyncio
    async def test_check_lockout_when_not_locked(self, mock_redis_unavailable):
        """Nicht gesperrtes Konto sollte als nicht gesperrt erkannt werden."""
        # Use fail_closed=False to test in-memory fallback behavior
        is_locked, remaining, message = await check_account_lockout(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert is_locked is False
        assert remaining is None
        assert message is None

    @pytest.mark.asyncio
    async def test_reset_clears_attempts(self, mock_redis_unavailable):
        """Reset sollte Fehlversuche löschen."""
        # Record some attempts with fail_closed=False for in-memory fallback
        await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )
        await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        # Reset
        success = await reset_failed_attempts(ip="192.168.1.1", username="test@example.com")

        assert success is True

        # Check status
        status = await get_lockout_status(ip="192.168.1.1", username="test@example.com")
        assert status["failed_attempts"] == 0

    @pytest.mark.asyncio
    async def test_admin_unlock(self, mock_redis_unavailable):
        """Admin-Unlock sollte Sperre aufheben."""
        identifier = _create_identifier("192.168.1.1", "test@example.com")
        _lockout_until_fallback[identifier] = datetime.now(timezone.utc) + timedelta(hours=1)
        _failed_attempts_fallback[identifier] = 10

        success = await admin_unlock_account(
            ip="192.168.1.1",
            username="test@example.com",
            admin_user="admin@example.com"
        )

        assert success is True

        # Verify unlock using fail_closed=False for in-memory fallback
        is_locked, _, _ = await check_account_lockout(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )
        assert is_locked is False

    @pytest.mark.asyncio
    async def test_expired_lockout_is_cleared(self, mock_redis_unavailable):
        """Abgelaufene Sperre sollte automatisch aufgehoben werden."""
        identifier = _create_identifier("192.168.1.1", "test@example.com")
        # Set lockout in the past
        _lockout_until_fallback[identifier] = datetime.now(timezone.utc) - timedelta(minutes=1)

        # Use fail_closed=False for in-memory fallback
        is_locked, _, _ = await check_account_lockout(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert is_locked is False
        # Verify expired lockout was removed
        assert identifier not in _lockout_until_fallback

    @pytest.mark.asyncio
    async def test_get_lockout_status(self, mock_redis_unavailable):
        """Status-Abfrage sollte alle Details enthalten."""
        identifier = _create_identifier("192.168.1.1", "test@example.com")
        _failed_attempts_fallback[identifier] = 3
        _lockout_until_fallback[identifier] = datetime.now(timezone.utc) + timedelta(minutes=5)

        status = await get_lockout_status(
            ip="192.168.1.1",
            username="test@example.com"
        )

        assert status["failed_attempts"] == 3
        assert status["is_locked"] is True
        assert status["remaining_seconds"] is not None
        assert status["max_attempts_before_lock"] == MAX_FAILED_ATTEMPTS


class TestAlertThreshold:
    """Tests für Alert-Schwellwert."""

    @pytest.fixture(autouse=True)
    def clear_fallback(self):
        """Fallback-Dicts vor jedem Test leeren."""
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()
        yield
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()

    @pytest.fixture
    def mock_redis_unavailable(self):
        """Mock Redis als nicht verfügbar."""
        with patch("app.core.account_lockout._get_redis_client", new_callable=AsyncMock) as mock:
            mock.return_value = None
            yield mock

    @pytest.mark.asyncio
    async def test_alert_at_threshold(self, mock_redis_unavailable, caplog):
        """Bei ALERT_THRESHOLD sollte Warnung geloggt werden."""
        # Simulate attempts up to alert threshold using fail_closed=False
        for i in range(ALERT_THRESHOLD - 1):
            await record_failed_attempt(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=False
            )

        # This should trigger the alert
        with patch("app.core.account_lockout.logger") as mock_logger:
            await record_failed_attempt(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=False
            )

            # Check that error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "brute_force" in call_args[0][0]


class TestMultipleIdentifiers:
    """Tests für verschiedene Identifier-Kombinationen."""

    @pytest.fixture(autouse=True)
    def clear_fallback(self):
        """Fallback-Dicts vor jedem Test leeren."""
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()
        yield
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()

    @pytest.fixture
    def mock_redis_unavailable(self):
        """Mock Redis als nicht verfügbar."""
        with patch("app.core.account_lockout._get_redis_client", new_callable=AsyncMock) as mock:
            mock.return_value = None
            yield mock

    @pytest.mark.asyncio
    async def test_different_ips_tracked_separately(self, mock_redis_unavailable):
        """Verschiedene IPs sollten separat getrackt werden."""
        await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )
        await record_failed_attempt(
            ip="192.168.1.2",
            username="test@example.com",
            fail_closed=False
        )

        status1 = await get_lockout_status(ip="192.168.1.1", username="test@example.com")
        status2 = await get_lockout_status(ip="192.168.1.2", username="test@example.com")

        # Each should have 1 attempt (they're tracked by IP+username combination)
        assert status1["failed_attempts"] == 1
        assert status2["failed_attempts"] == 1

    @pytest.mark.asyncio
    async def test_different_users_tracked_separately(self, mock_redis_unavailable):
        """Verschiedene Benutzer sollten separat getrackt werden."""
        await record_failed_attempt(
            ip="192.168.1.1",
            username="user1@example.com",
            fail_closed=False
        )
        await record_failed_attempt(
            ip="192.168.1.1",
            username="user1@example.com",
            fail_closed=False
        )
        await record_failed_attempt(
            ip="192.168.1.1",
            username="user2@example.com",
            fail_closed=False
        )

        status1 = await get_lockout_status(ip="192.168.1.1", username="user1@example.com")
        status2 = await get_lockout_status(ip="192.168.1.1", username="user2@example.com")

        assert status1["failed_attempts"] == 2
        assert status2["failed_attempts"] == 1


class TestFailClosedMode:
    """Tests für Fail-Closed Modus bei Redis-Ausfall."""

    @pytest.fixture(autouse=True)
    def clear_fallback(self):
        """Fallback-Dicts vor jedem Test leeren."""
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()
        yield
        _failed_attempts_fallback.clear()
        _lockout_until_fallback.clear()

    @pytest.fixture
    def mock_redis_unavailable(self):
        """Mock Redis als nicht verfügbar."""
        with patch("app.core.account_lockout._get_redis_client", new_callable=AsyncMock) as mock:
            mock.return_value = None
            yield mock

    @pytest.mark.asyncio
    async def test_check_lockout_fail_closed_raises_exception(self, mock_redis_unavailable):
        """Bei fail_closed=True und Redis-Ausfall sollte Exception geworfen werden."""
        with pytest.raises(AccountLockoutStorageError) as exc_info:
            await check_account_lockout(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=True
            )

        assert "nicht verfügbar" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_check_lockout_fail_open_uses_fallback(self, mock_redis_unavailable):
        """Bei fail_closed=False sollte In-Memory-Fallback verwendet werden."""
        # Should NOT raise exception
        is_locked, remaining, message = await check_account_lockout(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert is_locked is False
        assert remaining is None
        assert message is None

    @pytest.mark.asyncio
    async def test_record_failed_attempt_fail_closed_raises_exception(self, mock_redis_unavailable):
        """Bei fail_closed=True und Redis-Ausfall sollte Exception geworfen werden."""
        with pytest.raises(AccountLockoutStorageError) as exc_info:
            await record_failed_attempt(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=True
            )

        assert "nicht verfügbar" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_record_failed_attempt_fail_open_uses_fallback(self, mock_redis_unavailable):
        """Bei fail_closed=False sollte In-Memory-Fallback verwendet werden."""
        # Should NOT raise exception
        attempts, is_locked, duration = await record_failed_attempt(
            ip="192.168.1.1",
            username="test@example.com",
            fail_closed=False
        )

        assert attempts == 1
        assert is_locked is False

    @pytest.mark.asyncio
    async def test_fail_closed_default_from_settings(self, mock_redis_unavailable):
        """fail_closed=None sollte Default aus Settings verwenden."""
        with patch("app.core.account_lockout.settings") as mock_settings:
            mock_settings.RATE_LIMIT_FAIL_CLOSED_CRITICAL = True

            with pytest.raises(AccountLockoutStorageError):
                await check_account_lockout(
                    ip="192.168.1.1",
                    username="test@example.com",
                    fail_closed=None  # Should use settings default
                )

    @pytest.mark.asyncio
    async def test_fail_closed_error_message_is_german(self, mock_redis_unavailable):
        """Fehlermeldung sollte auf Deutsch sein."""
        with pytest.raises(AccountLockoutStorageError) as exc_info:
            await check_account_lockout(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=True
            )

        error_message = str(exc_info.value).lower()
        # Check for German words
        assert any(word in error_message for word in [
            "anmeldung", "verfügbar", "versuchen", "erneut"
        ])

    @pytest.mark.asyncio
    async def test_redis_available_returns_early(self):
        """Bei verfügbarem Redis sollte keine Exception geworfen werden."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.core.account_lockout._get_redis_client", new_callable=AsyncMock) as mock:
            mock.return_value = mock_redis

            # Should NOT raise exception even with fail_closed=True
            is_locked, remaining, message = await check_account_lockout(
                ip="192.168.1.1",
                username="test@example.com",
                fail_closed=True
            )

            assert is_locked is False
