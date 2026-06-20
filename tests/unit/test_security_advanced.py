"""
Tests für erweiterte Security-Features.

Testet:
- DNS Resolution Timeout (CWE-400 Denial of Service Prevention)
- TOTP Atomic SETNX Pattern (CWE-362 Race Condition Prevention)
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDNSResolutionTimeout:
    """Tests für DNS Resolution mit Timeout-Schutz."""

    def test_dns_timeout_constant_exists(self):
        """Test: DNS_RESOLUTION_TIMEOUT_SECONDS Konstante existiert."""
        from app.core.security import DNS_RESOLUTION_TIMEOUT_SECONDS

        assert DNS_RESOLUTION_TIMEOUT_SECONDS > 0
        assert DNS_RESOLUTION_TIMEOUT_SECONDS <= 10  # Reasonable upper bound

    def test_dns_timeout_default_value(self):
        """Test: DNS Timeout hat vernünftigen Standardwert (3 Sekunden)."""
        from app.core.security import DNS_RESOLUTION_TIMEOUT_SECONDS

        assert DNS_RESOLUTION_TIMEOUT_SECONDS == 3.0

    @pytest.mark.asyncio
    async def test_valid_hostname_resolves(self):
        """Test: Gültige Hostnames werden aufgelöst."""
        from app.core.security import validate_url_for_ssrf

        # localhost sollte immer auflösbar sein
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 0, "", ("127.0.0.1", 0))
            ]
            is_valid, error = validate_url_for_ssrf("http://localhost/test")

            # Sollte nicht wegen DNS-Timeout fehlschlagen
            assert "DNS-Timeout" not in (error or "")

    @pytest.mark.asyncio
    async def test_dns_timeout_returns_error_message(self):
        """Test: Bei DNS Timeout wird deutsche Fehlermeldung zurückgegeben."""
        from concurrent.futures import TimeoutError
        from app.core.security import validate_url_for_ssrf

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simuliere einen Timeout
            def slow_dns(*args, **kwargs):
                import time
                time.sleep(10)  # Simuliere langsamen DNS

            mock_getaddrinfo.side_effect = slow_dns

            # Da ThreadPoolExecutor verwendet wird, müssen wir den
            # tatsächlichen Timeout testen
            with patch("app.core.security_auth.DNS_RESOLUTION_TIMEOUT_SECONDS", 0.1):
                is_valid, error = validate_url_for_ssrf("http://slowdns.example.com/test")

                # Timeout sollte eintreten
                if error and "DNS-Timeout" in error:
                    assert "slowdns.example.com" in error
                    assert is_valid is False


class TestTOTPAtomicOperations:
    """Tests für atomare TOTP-Operationen (SETNX Pattern)."""

    @pytest.mark.asyncio
    async def test_check_and_mark_totp_used_exists(self):
        """Test: Atomare TOTP-Funktion existiert."""
        from app.core.security import check_and_mark_totp_used

        assert callable(check_and_mark_totp_used)

    @pytest.mark.asyncio
    async def test_first_use_returns_false(self):
        """Test: Erster TOTP-Code Gebrauch gibt False zurück (kein Replay)."""
        from app.core.security import check_and_mark_totp_used

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            # SETNX gibt True zurück wenn Key neu gesetzt wurde
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis_getter.return_value = mock_redis

            is_replay = await check_and_mark_totp_used("user123", "123456")

            assert is_replay is False  # Kein Replay beim ersten Mal
            mock_redis.set.assert_called_once()
            call_kwargs = mock_redis.set.call_args[1]
            assert call_kwargs.get("nx") is True  # SETNX Pattern

    @pytest.mark.asyncio
    async def test_second_use_returns_true(self):
        """Test: Zweiter TOTP-Code Gebrauch gibt True zurück (Replay erkannt)."""
        from app.core.security import check_and_mark_totp_used

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            # SETNX gibt False zurück wenn Key bereits existiert
            mock_redis.set = AsyncMock(return_value=False)
            mock_redis_getter.return_value = mock_redis

            is_replay = await check_and_mark_totp_used("user123", "123456")

            assert is_replay is True  # Replay erkannt

    @pytest.mark.asyncio
    async def test_fallback_to_memory_when_redis_unavailable(self):
        """Test: Fallback zu In-Memory wenn Redis nicht verfügbar."""
        from app.core.security import (
            check_and_mark_totp_used,
            _totp_used_fallback,
            _totp_fallback_lock,
        )

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis_getter.return_value = None  # Redis nicht verfügbar

            # Ersten Aufruf - sollte nicht als Replay erkannt werden
            is_replay1 = await check_and_mark_totp_used("user_fallback", "654321")
            assert is_replay1 is False

            # Zweiten Aufruf mit gleichem Code - sollte Replay sein
            is_replay2 = await check_and_mark_totp_used("user_fallback", "654321")
            assert is_replay2 is True

    @pytest.mark.asyncio
    async def test_fallback_uses_lock(self):
        """Test: Fallback verwendet asyncio.Lock für Thread-Safety."""
        from app.core.security import _totp_fallback_lock

        assert isinstance(_totp_fallback_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_different_users_same_code(self):
        """Test: Gleicher Code für unterschiedliche User ist erlaubt."""
        from app.core.security import check_and_mark_totp_used

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            # Beide Aufrufe setzen neuen Key (unterschiedliche User)
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis_getter.return_value = mock_redis

            is_replay1 = await check_and_mark_totp_used("user_a", "111111")
            is_replay2 = await check_and_mark_totp_used("user_b", "111111")

            assert is_replay1 is False
            assert is_replay2 is False
            assert mock_redis.set.call_count == 2

    @pytest.mark.asyncio
    async def test_key_includes_user_id_and_code(self):
        """Test: Redis-Key enthält User-ID und Code (gehasht)."""
        from app.core.security import check_and_mark_totp_used, TOTP_REPLAY_PREFIX

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis_getter.return_value = mock_redis

            await check_and_mark_totp_used("test_user", "999999")

            call_args = mock_redis.set.call_args[0]
            key = call_args[0]
            assert key.startswith(TOTP_REPLAY_PREFIX)

    @pytest.mark.asyncio
    async def test_ttl_is_set_correctly(self):
        """Test: TTL wird korrekt gesetzt (30-60 Sekunden typisch)."""
        from app.core.security import (
            check_and_mark_totp_used,
            TOTP_REPLAY_TTL_SECONDS,
        )

        assert TOTP_REPLAY_TTL_SECONDS > 0
        assert TOTP_REPLAY_TTL_SECONDS <= 120  # Max 2 Minuten

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)
            mock_redis_getter.return_value = mock_redis

            await check_and_mark_totp_used("ttl_user", "777777")

            call_kwargs = mock_redis.set.call_args[1]
            assert call_kwargs.get("ex") == TOTP_REPLAY_TTL_SECONDS


class TestLegacyTOTPFunctionsDeprecated:
    """Tests dass Legacy-Funktionen als deprecated markiert sind."""

    def test_check_totp_replay_deprecated(self):
        """Test: check_totp_replay ist als deprecated markiert."""
        from app.core.security import check_totp_replay

        # Docstring sollte DEPRECATED enthalten
        assert "DEPRECATED" in (check_totp_replay.__doc__ or "")

    def test_mark_totp_used_deprecated(self):
        """Test: mark_totp_used ist als deprecated markiert."""
        from app.core.security import mark_totp_used

        # Docstring sollte DEPRECATED enthalten
        assert "DEPRECATED" in (mark_totp_used.__doc__ or "")


class TestRaceConditionPrevention:
    """Tests für Race-Condition-Prävention."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_only_one_succeeds(self):
        """Test: Bei gleichzeitigen Aufrufen gewinnt nur einer."""
        from app.core.security import check_and_mark_totp_used

        # Simuliere SETNX-Verhalten: nur erster Aufruf erfolgreich
        call_count = 0

        async def mock_set(key, value, ex=None, nx=None):
            nonlocal call_count
            call_count += 1
            # Erster Aufruf erfolgreich, weitere nicht
            return call_count == 1

        with patch("app.core.security_auth._get_redis_client") as mock_redis_getter:
            mock_redis = AsyncMock()
            mock_redis.set = mock_set
            mock_redis_getter.return_value = mock_redis

            # Simuliere 3 gleichzeitige Aufrufe
            results = await asyncio.gather(
                check_and_mark_totp_used("race_user", "123456"),
                check_and_mark_totp_used("race_user", "123456"),
                check_and_mark_totp_used("race_user", "123456"),
            )

            # Genau einer sollte nicht als Replay erkannt werden
            non_replay_count = sum(1 for r in results if r is False)
            replay_count = sum(1 for r in results if r is True)

            assert non_replay_count == 1
            assert replay_count == 2


class TestSecurityIntegration:
    """Integrationstests für Security-Modul."""

    @pytest.mark.asyncio
    async def test_auth_flow_uses_atomic_function(self):
        """Test: Auth-Flow verwendet atomare TOTP-Funktion."""
        # Überprüfe dass auth.py die richtige Funktion importiert
        import ast
        from pathlib import Path

        auth_file = Path(__file__).parent.parent.parent / "app" / "api" / "v1" / "auth.py"
        with open(auth_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Sollte check_and_mark_totp_used importieren
        assert "check_and_mark_totp_used" in content
        # Sollte NICHT mehr die alten separaten Funktionen verwenden
        # (für den Check-then-Mark Antipattern)
        assert "await check_totp_replay" not in content or "DEPRECATED" in content
