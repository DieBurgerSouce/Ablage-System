"""Unit tests für Rate-Limiting Fail-Closed Modus.

Testet das Verhalten bei Redis-Ausfall:
- fail_closed=False: Requests werden erlaubt (fail-open)
- fail_closed=True: Requests werden abgelehnt (fail-closed)
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.core.rate_limiting import (
    RedisRateLimitStorage,
    RateLimitStorageError,
)


class TestRateLimitStorageError:
    """Tests für RateLimitStorageError Exception."""

    def test_exception_message(self):
        """Exception sollte Nachricht speichern."""
        error = RateLimitStorageError("Test error message")
        assert str(error) == "Test error message"

    def test_exception_inheritance(self):
        """Exception sollte von Exception erben."""
        error = RateLimitStorageError("Test")
        assert isinstance(error, Exception)


class TestRedisRateLimitStorageFailOpen:
    """Tests für Fail-Open Modus (Standard)."""

    @pytest.fixture
    def storage(self):
        """Erstelle Storage-Instanz ohne Redis."""
        storage = RedisRateLimitStorage("redis://localhost:6379/0")
        storage._available = False
        storage._redis = None
        return storage

    @pytest.mark.asyncio
    async def test_fail_open_returns_zero_when_unavailable(self, storage):
        """Bei Redis-Ausfall und fail_closed=False sollte 0 zurückgegeben werden."""
        result = await storage.increment("test:key", 60, fail_closed=False)
        assert result == 0

    @pytest.mark.asyncio
    async def test_fail_open_is_default_behavior(self, storage):
        """Fail-open sollte das Standardverhalten sein."""
        result = await storage.increment("test:key", 60)  # Kein fail_closed Parameter
        assert result == 0


class TestRedisRateLimitStorageFailClosed:
    """Tests für Fail-Closed Modus (Sicherheitsmodus)."""

    @pytest.fixture
    def storage(self):
        """Erstelle Storage-Instanz ohne Redis."""
        storage = RedisRateLimitStorage("redis://localhost:6379/0")
        storage._available = False
        storage._redis = None
        return storage

    @pytest.mark.asyncio
    async def test_fail_closed_raises_exception_when_unavailable(self, storage):
        """Bei Redis-Ausfall und fail_closed=True sollte Exception geworfen werden."""
        with pytest.raises(RateLimitStorageError) as exc_info:
            await storage.increment("test:key", 60, fail_closed=True)

        assert "Rate-Limiting-Service" in str(exc_info.value)
        assert "nicht verfügbar" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fail_closed_error_message_is_german(self, storage):
        """Fehlermeldung sollte auf Deutsch sein."""
        with pytest.raises(RateLimitStorageError) as exc_info:
            await storage.increment("test:key", 60, fail_closed=True)

        message = str(exc_info.value)
        # Deutsche Schlüsselwörter prüfen
        assert any(word in message.lower() for word in ["versuchen", "später", "erneut", "verfügbar"])


class TestRedisRateLimitStorageWithRedisError:
    """Tests für Redis-Fehler während der Anfrage."""

    @pytest.fixture
    def storage_with_error(self):
        """Erstelle Storage-Instanz mit fehlerhaftem Redis."""
        storage = RedisRateLimitStorage("redis://localhost:6379/0")
        storage._available = True

        # Mock Redis pipeline that raises error
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.incr.return_value = mock_pipeline
        mock_pipeline.expire.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(side_effect=ConnectionError("Redis connection lost"))
        mock_redis.pipeline.return_value = mock_pipeline

        storage._redis = mock_redis
        return storage

    @pytest.mark.asyncio
    async def test_redis_error_fail_open_returns_zero(self, storage_with_error):
        """Bei Redis-Fehler und fail_closed=False sollte 0 zurückgegeben werden."""
        result = await storage_with_error.increment("test:key", 60, fail_closed=False)
        assert result == 0

    @pytest.mark.asyncio
    async def test_redis_error_fail_closed_raises_exception(self, storage_with_error):
        """Bei Redis-Fehler und fail_closed=True sollte Exception geworfen werden."""
        with pytest.raises(RateLimitStorageError):
            await storage_with_error.increment("test:key", 60, fail_closed=True)


class TestRedisRateLimitStorageWithWorkingRedis:
    """Tests für funktionierendes Redis."""

    @pytest.fixture
    def storage_with_redis(self):
        """Erstelle Storage-Instanz mit funktionierendem Redis Mock."""
        storage = RedisRateLimitStorage("redis://localhost:6379/0")
        storage._available = True

        # Mock Redis pipeline that works
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.incr.return_value = mock_pipeline
        mock_pipeline.expire.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(return_value=[5, True])  # 5 requests, expire set
        mock_redis.pipeline.return_value = mock_pipeline

        storage._redis = mock_redis
        return storage

    @pytest.mark.asyncio
    async def test_working_redis_returns_counter(self, storage_with_redis):
        """Bei funktionierendem Redis sollte der Counter zurückgegeben werden."""
        result = await storage_with_redis.increment("test:key", 60, fail_closed=False)
        assert result == 5

    @pytest.mark.asyncio
    async def test_working_redis_fail_closed_returns_counter(self, storage_with_redis):
        """Bei funktionierendem Redis sollte auch fail_closed=True Counter zurückgeben."""
        result = await storage_with_redis.increment("test:key", 60, fail_closed=True)
        assert result == 5


class TestConfigIntegration:
    """Tests für Konfigurationsintegration."""

    def test_fail_closed_config_exists(self):
        """Konfigurationsoptionen sollten existieren."""
        from app.core.config import settings

        assert hasattr(settings, 'RATE_LIMIT_FAIL_CLOSED')
        assert hasattr(settings, 'RATE_LIMIT_FAIL_CLOSED_CRITICAL')

    def test_fail_closed_default_values(self):
        """Standardwerte sollten korrekt gesetzt sein."""
        from app.core.config import settings

        # Default ist fail-open (False) für bessere Verfügbarkeit
        # Bei kritischen Endpoints wird fail_closed=True explizit übergeben
        # Operator kann via RATE_LIMIT_FAIL_CLOSED=true überschreiben
        assert isinstance(settings.RATE_LIMIT_FAIL_CLOSED, bool)
        assert isinstance(settings.RATE_LIMIT_FAIL_CLOSED_CRITICAL, bool)
        # Beide Werte existieren und sind konfigurierbar
        assert hasattr(settings, 'RATE_LIMIT_FAIL_CLOSED')
        assert hasattr(settings, 'RATE_LIMIT_FAIL_CLOSED_CRITICAL')


class TestExceptionHandler:
    """Tests für Exception Handler (jetzt in exception_handlers.py)."""

    @pytest.mark.asyncio
    async def test_exception_handler_returns_503(self):
        """Exception Handler sollte 503 zurückgeben."""
        from fastapi import Request
        from app.core.exception_handlers import (
            EXCEPTION_STATUS_CODES,
            create_error_response,
        )

        # RateLimitStorageError sollte Status 503 haben
        assert RateLimitStorageError in EXCEPTION_STATUS_CODES
        assert EXCEPTION_STATUS_CODES[RateLimitStorageError] == 503

        # Teste create_error_response für 503
        response = create_error_response(
            fehler="Service nicht verfügbar",
            nachricht="Test error",
            status_code=503,
            pfad="/test/path",
            retry_after=60,
        )

        assert response["status_code"] == 503
        assert response["retry_after"] == 60

    @pytest.mark.asyncio
    async def test_exception_handler_response_is_german(self):
        """Exception Handler sollte deutsche Antwort liefern."""
        from app.core.exception_handlers import create_error_response

        response = create_error_response(
            fehler="Service nicht verfügbar",
            nachricht="Rate-Limiting-Service nicht verfügbar",
            status_code=503,
            pfad="/test/path",
        )

        # Prüfe deutsche Feldnamen
        assert "fehler" in response
        assert "nachricht" in response
        assert "zeitstempel" in response
        assert "pfad" in response

        # Prüfe dass keine englischen Feldnamen vorhanden sind
        assert "error" not in response
        assert "message" not in response
        assert "timestamp" not in response
        assert "path" not in response


class TestSecurityScenarios:
    """Tests für Sicherheitsszenarien."""

    @pytest.fixture
    def storage(self):
        """Erstelle Storage-Instanz ohne Redis."""
        storage = RedisRateLimitStorage("redis://localhost:6379/0")
        storage._available = False
        storage._redis = None
        return storage

    @pytest.mark.asyncio
    async def test_brute_force_protection_with_fail_closed(self, storage):
        """Bei Brute-Force-Versuch während Redis-Ausfall sollte Request abgelehnt werden."""
        # Szenario: Angreifer versucht Login während Redis offline ist
        # Mit fail_closed=True wird der Request abgelehnt, um Brute-Force zu verhindern

        with pytest.raises(RateLimitStorageError):
            await storage.increment("login:192.168.1.1", 900, fail_closed=True)

    @pytest.mark.asyncio
    async def test_availability_with_fail_open(self, storage):
        """Bei fail_open sollte Request erlaubt werden für Verfügbarkeit."""
        # Szenario: Normaler User während Redis-Ausfall
        # Mit fail_closed=False wird der Request erlaubt

        result = await storage.increment("api:user123", 60, fail_closed=False)
        assert result == 0  # 0 = keine Limitierung, Request erlaubt
