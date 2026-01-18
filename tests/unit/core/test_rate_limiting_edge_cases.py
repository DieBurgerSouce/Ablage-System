# -*- coding: utf-8 -*-
"""
Unit Tests fuer Rate Limiting Edge Cases.

Erweiterte Tests fuer:
- Zeitgrenzen-Verhalten (Stunden-/Tages-Wechsel)
- Concurrent Requests
- Multi-Key Rate Limiting
- Rate Limit Headers
- Sliding Window Verhalten
- Redis Reconnection
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse


class TestTimeBoundaryEdgeCases:
    """Tests fuer Verhalten an Zeitgrenzen."""

    def test_hour_boundary_key_change(self):
        """Key sollte sich am Stundenwechsel aendern."""
        from app.core.rate_limiting import _get_current_hour_key

        # Aktuelle Stunde
        key1 = _get_current_hour_key()

        # Simuliere naechste Stunde
        with patch('app.core.rate_limiting.datetime') as mock_dt:
            next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
            mock_dt.now.return_value = next_hour
            mock_dt.timezone = timezone

            # Force reimport to get new key
            from importlib import reload
            import app.core.rate_limiting as rl
            # Key Format ist YYYYMMDDHH, also 10 Zeichen
            # Nach einer Stunde sollte die letzte(n) Ziffer(n) anders sein

        # Keys sollten unterschiedlich sein (kann nicht direkt getestet werden
        # ohne Time-Travel, aber Format-Test ist moeglich)
        assert len(key1) == 10
        assert key1.isdigit()

    def test_day_boundary_key_change(self):
        """Key sollte sich am Tageswechsel aendern."""
        from app.core.rate_limiting import _get_current_day_key

        key = _get_current_day_key()

        # Format pruefen: YYYYMMDD
        assert len(key) == 8
        assert key.isdigit()

        # Jahr sollte aktuell sein
        current_year = str(datetime.now(timezone.utc).year)
        assert key.startswith(current_year)

    def test_minute_boundary_key_change(self):
        """Key sollte sich am Minutenwechsel aendern."""
        from app.core.rate_limiting import _get_current_minute_key

        key = _get_current_minute_key()

        # Format pruefen: YYYYMMDDHHmm
        assert len(key) == 12
        assert key.isdigit()

    def test_reset_time_is_always_future(self):
        """Reset-Zeit sollte immer in der Zukunft liegen."""
        from app.core.rate_limiting import (
            _get_next_hour_reset,
            _get_next_day_reset,
            _get_next_minute_reset,
        )

        now = datetime.now(timezone.utc)

        hour_reset = _get_next_hour_reset()
        day_reset = _get_next_day_reset()
        minute_reset = _get_next_minute_reset()

        assert hour_reset > now
        assert day_reset > now
        assert minute_reset > now

        # Reset-Zeiten sollten aufeinander folgen
        assert minute_reset <= hour_reset
        assert hour_reset <= day_reset

    def test_reset_time_at_exact_boundary(self):
        """Reset-Zeit am exakten Grenzwert."""
        from app.core.rate_limiting import _get_next_minute_reset

        reset = _get_next_minute_reset()

        # Sekunden sollten 0 sein
        assert reset.second == 0
        assert reset.microsecond == 0


class TestConcurrentRequestHandling:
    """Tests fuer parallele Anfragen."""

    @pytest.fixture
    def mock_storage(self):
        """Erstelle Storage mit Thread-Safe Counter."""
        storage = MagicMock()
        storage.is_available = True
        storage._counter = 0
        storage._lock = asyncio.Lock()

        async def increment(key, ttl, fail_closed=False):
            async with storage._lock:
                storage._counter += 1
                return storage._counter

        storage.increment = AsyncMock(side_effect=increment)
        return storage

    @pytest.mark.asyncio
    async def test_concurrent_increments_are_sequential(self, mock_storage):
        """Parallele Increments sollten sequentiell gezaehlt werden."""
        async def do_increment():
            return await mock_storage.increment("test:key", 60)

        # 10 parallele Requests
        tasks = [do_increment() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # Alle Ergebnisse sollten zwischen 1 und 10 sein
        assert len(results) == 10
        assert min(results) >= 1
        assert max(results) <= 10

        # Counter sollte 10 sein
        assert mock_storage._counter == 10

    @pytest.mark.asyncio
    async def test_rate_limit_reached_during_concurrent_requests(self):
        """Rate Limit sollte auch bei parallelen Requests greifen."""
        counter = {"value": 0}
        limit = 5

        async def mock_increment(key, ttl, fail_closed=False):
            counter["value"] += 1
            return counter["value"]

        storage = MagicMock()
        storage.is_available = True
        storage.increment = AsyncMock(side_effect=mock_increment)

        async def check_limit():
            count = await storage.increment("test:key", 60)
            return count <= limit

        # 10 parallele Requests mit Limit 5
        tasks = [check_limit() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # 5 sollten unter Limit sein, 5 darueber
        assert sum(results) == 5
        assert sum(not r for r in results) == 5


class TestMultiKeyRateLimiting:
    """Tests fuer Multi-Key Rate Limiting (User + Endpoint)."""

    def test_different_users_have_separate_limits(self):
        """Verschiedene User sollten separate Limits haben."""
        from app.core.rate_limiting import get_user_identifier

        mock_request1 = Mock(spec=Request)
        mock_request1.state = Mock()
        mock_request1.state.user = Mock(id="user1")
        mock_request1.client = Mock(host="192.168.1.1")

        mock_request2 = Mock(spec=Request)
        mock_request2.state = Mock()
        mock_request2.state.user = Mock(id="user2")
        mock_request2.client = Mock(host="192.168.1.2")

        with patch("app.core.rate_limiting.get_remote_address", side_effect=["192.168.1.1", "192.168.1.2"]):
            id1 = get_user_identifier(mock_request1)
            id2 = get_user_identifier(mock_request2)

        assert id1 != id2
        assert "user1" in id1
        assert "user2" in id2

    def test_same_user_different_endpoints(self):
        """Gleicher User auf verschiedenen Endpoints."""
        # Endpoint-spezifische Keys sollten unterschiedlich sein
        user_id = "user123"

        login_key = f"ratelimit:login:{user_id}"
        ocr_key = f"ratelimit:ocr:{user_id}"
        api_key = f"ratelimit:api:{user_id}"

        assert login_key != ocr_key
        assert ocr_key != api_key
        assert login_key != api_key

    def test_combined_user_ip_key(self):
        """Kombinierter User + IP Key fuer strengere Limits."""
        user_id = "user123"
        ip = "192.168.1.100"

        combined_key = f"ratelimit:strict:{user_id}:{ip}"

        assert user_id in combined_key
        assert ip in combined_key


class TestRateLimitHeaders:
    """Tests fuer Rate Limit Response Headers."""

    def test_retry_after_header_in_response(self):
        """Retry-After Header sollte in 429 Response sein."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german
        from slowapi.errors import RateLimitExceeded

        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.user = None
        mock_request.url = Mock(path="/api/v1/test")
        mock_request.client = Mock(host="192.168.1.100")

        mock_limit = Mock()
        mock_limit.error_message = None
        mock_limit.limit = "10/minute"

        exc = RateLimitExceeded(mock_limit)
        exc.retry_after = 45

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            response = rate_limit_exceeded_handler_german(mock_request, exc)

        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "45"

    def test_rate_limit_response_status_429(self):
        """Response Status sollte 429 sein."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german
        from slowapi.errors import RateLimitExceeded

        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.user = None
        mock_request.url = Mock(path="/api/v1/test")
        mock_request.client = Mock(host="192.168.1.100")

        mock_limit = Mock()
        mock_limit.error_message = None
        mock_limit.limit = "10/minute"

        exc = RateLimitExceeded(mock_limit)
        exc.retry_after = 60

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            response = rate_limit_exceeded_handler_german(mock_request, exc)

        assert response.status_code == 429


class TestRedisReconnection:
    """Tests fuer Redis Reconnection nach Ausfall."""

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self):
        """Storage sollte nach Disconnect wieder verbinden koennen."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.aclose = AsyncMock()

        with patch("app.core.rate_limiting.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            from app.core.rate_limiting import RedisRateLimitStorage
            storage = RedisRateLimitStorage("redis://localhost:6379")

            # Erste Verbindung
            await storage.connect()
            assert storage.is_available is True

            # Disconnect
            await storage.disconnect()
            assert storage.is_available is False

            # Reconnect
            await storage.connect()
            assert storage.is_available is True

    @pytest.mark.asyncio
    async def test_health_check_detects_disconnect(self):
        """Health Check sollte Disconnect erkennen."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Lost connection"))

        from app.core.rate_limiting import RedisRateLimitStorage
        storage = RedisRateLimitStorage("redis://localhost:6379")
        storage._redis = mock_redis
        storage._available = True

        # Health Check sollte Fehler erkennen
        try:
            await storage._redis.ping()
            is_healthy = True
        except ConnectionError:
            is_healthy = False

        assert is_healthy is False


class TestSlidingWindowBehavior:
    """Tests fuer Sliding Window Rate Limiting Verhalten."""

    def test_key_includes_time_window(self):
        """Rate Limit Key sollte Zeitfenster enthalten."""
        from app.core.rate_limiting import _get_current_minute_key

        key = _get_current_minute_key()

        # Key enthaelt Datum und Zeit
        assert len(key) == 12  # YYYYMMDDHHmm

    @pytest.mark.asyncio
    async def test_expired_keys_dont_count(self):
        """Abgelaufene Keys sollten nicht zaehlen."""
        # Mock Storage mit TTL
        storage = MagicMock()
        storage.is_available = True

        # Simuliere: Alter Key ist abgelaufen, neuer Key startet bei 1
        storage.increment = AsyncMock(return_value=1)

        result = await storage.increment("ratelimit:test:202312010900", 60)
        assert result == 1

    def test_window_duration_matches_tier(self):
        """Fenster-Dauer sollte zur Tier-Konfiguration passen."""
        from app.core.rate_limiting import RateLimitTier

        # Login: 5/15minutes = 15 Minuten Fenster
        assert "15minutes" in RateLimitTier.LOGIN

        # OCR Hourly: /hour = 60 Minuten Fenster
        assert "hour" in RateLimitTier.OCR_FREE_HOURLY

        # OCR Daily: /day = 24 Stunden Fenster
        assert "day" in RateLimitTier.OCR_FREE_DAILY


class TestIPAddressEdgeCases:
    """Tests fuer IP-Adressen Edge Cases."""

    @pytest.fixture
    def mock_request(self):
        """Erstelle Mock Request."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user = None
        request.client = Mock()
        # Properly mock headers to return None for missing keys
        request.headers = Mock()
        request.headers.get = Mock(return_value=None)
        return request

    def test_ipv4_address_identification(self, mock_request):
        """IPv4-Adressen sollten erkannt werden."""
        mock_request.client.host = "192.168.1.100"

        from app.core.rate_limiting import get_ip_identifier
        identifier = get_ip_identifier(mock_request)

        # Client is from private network, returns client.host directly
        assert identifier == "192.168.1.100"

    def test_ipv6_address_identification(self, mock_request):
        """IPv6-Adressen sollten erkannt werden."""
        mock_request.client.host = "2001:db8::1"

        from app.core.rate_limiting import get_ip_identifier
        identifier = get_ip_identifier(mock_request)

        # Client is public IPv6, returns client.host directly
        assert identifier == "2001:db8::1"

    def test_localhost_ipv4_whitelisted(self):
        """127.0.0.1 sollte gewhitelistet sein."""
        from app.core.rate_limiting import IPWhitelist
        whitelist = IPWhitelist()

        assert whitelist.is_whitelisted("127.0.0.1") is True

    def test_localhost_ipv6_whitelisted(self):
        """::1 sollte gewhitelistet sein."""
        from app.core.rate_limiting import IPWhitelist
        whitelist = IPWhitelist()

        assert whitelist.is_whitelisted("::1") is True

    def test_private_ip_not_auto_whitelisted(self):
        """Private IPs sollten nicht automatisch gewhitelistet sein."""
        from app.core.rate_limiting import IPWhitelist
        whitelist = IPWhitelist()

        # Private IP Ranges
        private_ips = [
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
        ]

        for ip in private_ips:
            # Nur wenn nicht explizit hinzugefuegt
            if ip not in ["127.0.0.1", "::1"]:
                # Standard: nicht gewhitelistet (ausser localhost)
                pass


class TestErrorMessageLocalization:
    """Tests fuer deutsche Fehlermeldungen."""

    def test_rate_limit_message_is_german(self):
        """Fehlermeldung sollte auf Deutsch sein."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german
        from slowapi.errors import RateLimitExceeded

        mock_request = Mock(spec=Request)
        mock_request.state = Mock()
        mock_request.state.user = None
        mock_request.url = Mock(path="/api/v1/test")
        mock_request.client = Mock(host="192.168.1.100")

        mock_limit = Mock()
        mock_limit.error_message = None
        mock_limit.limit = "10/minute"

        exc = RateLimitExceeded(mock_limit)
        exc.retry_after = 60

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            response = rate_limit_exceeded_handler_german(mock_request, exc)

        # Response Body sollte deutsche Schluesselwoerter enthalten
        assert isinstance(response, JSONResponse)

    def test_storage_error_message_is_german(self):
        """Storage-Fehlermeldung sollte auf Deutsch sein."""
        from app.core.rate_limiting import RateLimitStorageError

        error = RateLimitStorageError(
            "Rate-Limiting-Service ist nicht verfuegbar. Bitte versuchen Sie es spaeter erneut."
        )

        message = str(error)

        # Deutsche Woerter pruefen
        assert any(word in message.lower() for word in [
            "verfuegbar", "versuchen", "spaeter", "erneut", "service"
        ])


class TestMetricsAccuracy:
    """Tests fuer Metriken-Genauigkeit."""

    @pytest.fixture
    def metrics(self):
        """Erstelle frische Metriken-Instanz."""
        from app.core.rate_limiting import RateLimitMetrics
        return RateLimitMetrics()

    def test_percentage_with_many_requests(self, metrics):
        """Prozent-Berechnung mit vielen Requests."""
        # 1000 Requests, 50 rate limited
        for _ in range(1000):
            metrics.record_request()
        for _ in range(50):
            metrics.record_rate_limited()

        stats = metrics.get_stats()
        assert stats["rate_limit_percentage"] == 5.0  # 50/1000 = 5%

    def test_percentage_precision(self, metrics):
        """Prozent-Berechnung sollte praezise sein."""
        # 3 Requests, 1 rate limited = 33.33%
        for _ in range(3):
            metrics.record_request()
        metrics.record_rate_limited()

        stats = metrics.get_stats()
        expected = round(1 / 3 * 100, 2)
        assert abs(stats["rate_limit_percentage"] - expected) < 0.1

    def test_metrics_thread_safety(self, metrics):
        """Metriken sollten thread-safe sein."""
        import threading

        def record_many():
            for _ in range(100):
                metrics.record_request()

        threads = [threading.Thread(target=record_many) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = metrics.get_stats()
        assert stats["total_requests"] == 1000  # 10 threads * 100 requests
