# -*- coding: utf-8 -*-
"""
Unit tests for Rate Limiting Configuration.

Tests for:
- Rate limit key functions
- Redis rate limit storage
- Rate limit tiers
- IP whitelist management
- Rate limit metrics
- German error messages
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from fastapi import Request
from fastapi.responses import JSONResponse


class TestRateLimitKeyFunctions:
    """Tests for rate limit key extraction functions."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.client = Mock()
        request.client.host = "192.168.1.100"
        # Properly mock headers to return None for missing keys
        request.headers = Mock()
        request.headers.get = Mock(return_value=None)
        return request

    def test_get_user_identifier_with_user(self, mock_request):
        """Test user identifier when user is authenticated."""
        mock_request.state.user = Mock()
        mock_request.state.user.id = "user123"

        from app.core.rate_limiting import get_user_identifier
        identifier = get_user_identifier(mock_request)

        assert identifier == "user:user123"

    def test_get_user_identifier_without_user(self, mock_request):
        """Test user identifier falls back to IP when not authenticated."""
        mock_request.state.user = None

        from app.core.rate_limiting import get_user_identifier
        identifier = get_user_identifier(mock_request)

        # Returns client.host since no X-Forwarded-For and client is not trusted proxy
        assert identifier == "ip:192.168.1.100"

    def test_get_ip_identifier(self, mock_request):
        """Test IP identifier extraction."""
        from app.core.rate_limiting import get_ip_identifier
        identifier = get_ip_identifier(mock_request)

        # Returns client.host since no proxy headers
        assert identifier == "192.168.1.100"


class TestRateLimitTier:
    """Tests for RateLimitTier configurations."""

    def test_login_rate_limit(self):
        """Test login rate limit configuration."""
        # G07: Per-IP-Login-Limit bewusst auf "5/minute" gesetzt (von "10/minute"
        # verschaerft), konsistent mit MAX_FAILED_ATTEMPTS=5. Frueher "5/15minutes".
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.LOGIN == "5/minute"

    def test_register_rate_limit(self):
        """Test registration rate limit configuration."""
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.REGISTER == "3/hour"

    def test_ocr_free_tier_limits(self):
        """Test OCR free tier limits."""
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.OCR_FREE_HOURLY == "10/hour"
        assert RateLimitTier.OCR_FREE_DAILY == "50/day"

    def test_ocr_premium_tier_limits(self):
        """Test OCR premium tier limits."""
        from app.core.rate_limiting import RateLimitTier
        assert RateLimitTier.OCR_PREMIUM_HOURLY == "100/hour"
        assert RateLimitTier.OCR_PREMIUM_DAILY == "1000/day"

    def test_health_check_high_limit(self):
        """Test health check has high limit."""
        from app.core.rate_limiting import RateLimitTier
        assert "1000" in RateLimitTier.HEALTH_CHECK


class TestIPWhitelist:
    """Tests for IP whitelist management."""

    @pytest.fixture
    def whitelist(self):
        """Create a fresh IP whitelist."""
        from app.core.rate_limiting import IPWhitelist
        return IPWhitelist()

    def test_default_whitelist_includes_localhost(self, whitelist):
        """Test that localhost is whitelisted by default."""
        assert whitelist.is_whitelisted("127.0.0.1") is True
        assert whitelist.is_whitelisted("::1") is True

    def test_add_ip_to_whitelist(self, whitelist):
        """Test adding IP to whitelist."""
        whitelist.add("10.0.0.1")
        assert whitelist.is_whitelisted("10.0.0.1") is True

    def test_remove_ip_from_whitelist(self, whitelist):
        """Test removing IP from whitelist."""
        whitelist.add("10.0.0.1")
        whitelist.remove("10.0.0.1")
        assert whitelist.is_whitelisted("10.0.0.1") is False

    def test_get_all_whitelisted(self, whitelist):
        """Test getting all whitelisted IPs."""
        whitelist.add("10.0.0.1")
        all_ips = whitelist.get_all()

        assert "127.0.0.1" in all_ips
        assert "10.0.0.1" in all_ips

    def test_unknown_ip_not_whitelisted(self, whitelist):
        """Test that unknown IP is not whitelisted."""
        assert whitelist.is_whitelisted("8.8.8.8") is False


class TestRateLimitMetrics:
    """Tests for RateLimitMetrics tracking."""

    @pytest.fixture
    def metrics(self):
        """Create a fresh metrics instance."""
        from app.core.rate_limiting import RateLimitMetrics
        return RateLimitMetrics()

    def test_initial_metrics_are_zero(self, metrics):
        """Test that initial metrics are zero."""
        stats = metrics.get_stats()

        assert stats["total_requests"] == 0
        assert stats["rate_limited_requests"] == 0
        assert stats["whitelisted_requests"] == 0
        assert stats["errors"] == 0

    def test_record_request(self, metrics):
        """Test recording a request."""
        metrics.record_request()
        metrics.record_request()

        stats = metrics.get_stats()
        assert stats["total_requests"] == 2

    def test_record_rate_limited(self, metrics):
        """Test recording rate limited request."""
        metrics.record_rate_limited()

        stats = metrics.get_stats()
        assert stats["rate_limited_requests"] == 1

    def test_record_whitelisted(self, metrics):
        """Test recording whitelisted request."""
        metrics.record_whitelisted()

        stats = metrics.get_stats()
        assert stats["whitelisted_requests"] == 1

    def test_record_error(self, metrics):
        """Test recording error."""
        metrics.record_error()

        stats = metrics.get_stats()
        assert stats["errors"] == 1

    def test_rate_limit_percentage(self, metrics):
        """Test rate limit percentage calculation."""
        metrics.record_request()
        metrics.record_request()
        metrics.record_request()
        metrics.record_request()
        metrics.record_rate_limited()

        stats = metrics.get_stats()
        assert stats["rate_limit_percentage"] == 25.0  # 1 of 4

    def test_rate_limit_percentage_zero_requests(self, metrics):
        """Test percentage with zero requests."""
        stats = metrics.get_stats()
        assert stats["rate_limit_percentage"] == 0

    def test_reset(self, metrics):
        """Test resetting metrics."""
        metrics.record_request()
        metrics.record_rate_limited()
        metrics.record_error()

        metrics.reset()

        stats = metrics.get_stats()
        assert stats["total_requests"] == 0
        assert stats["rate_limited_requests"] == 0
        assert stats["errors"] == 0


class TestTimeKeyFunctions:
    """Tests for time-based key generation functions."""

    def test_current_hour_key_format(self):
        """Test hour key format (YYYYMMDDHH)."""
        from app.core.rate_limiting import _get_current_hour_key
        key = _get_current_hour_key()

        assert len(key) == 10
        assert key.isdigit()

    def test_current_day_key_format(self):
        """Test day key format (YYYYMMDD)."""
        from app.core.rate_limiting import _get_current_day_key
        key = _get_current_day_key()

        assert len(key) == 8
        assert key.isdigit()

    def test_current_minute_key_format(self):
        """Test minute key format (YYYYMMDDHHmm)."""
        from app.core.rate_limiting import _get_current_minute_key
        key = _get_current_minute_key()

        assert len(key) == 12
        assert key.isdigit()

    def test_next_hour_reset_is_future(self):
        """Test that next hour reset is in the future."""
        from app.core.rate_limiting import _get_next_hour_reset
        reset = _get_next_hour_reset()

        assert reset > datetime.now(timezone.utc)
        assert reset.minute == 0
        assert reset.second == 0

    def test_next_day_reset_is_future(self):
        """Test that next day reset is in the future."""
        from app.core.rate_limiting import _get_next_day_reset
        reset = _get_next_day_reset()

        assert reset > datetime.now(timezone.utc)
        assert reset.hour == 0
        assert reset.minute == 0

    def test_next_minute_reset_is_future(self):
        """Test that next minute reset is in the future."""
        from app.core.rate_limiting import _get_next_minute_reset
        reset = _get_next_minute_reset()

        assert reset > datetime.now(timezone.utc)
        assert reset.second == 0


class TestRedisRateLimitStorage:
    """Tests for Redis rate limit storage backend."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.aclose = AsyncMock()

        pipeline = AsyncMock()
        pipeline.incr = Mock()
        pipeline.expire = Mock()
        pipeline.execute = AsyncMock(return_value=[1])
        redis.pipeline = Mock(return_value=pipeline)

        return redis

    @pytest.mark.asyncio
    async def test_storage_connection(self, mock_redis):
        """Test storage connection."""
        with patch("app.core.rate_limiting.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            from app.core.rate_limiting import RedisRateLimitStorage
            storage = RedisRateLimitStorage("redis://localhost:6379")
            await storage.connect()

            assert storage.is_available is True

    @pytest.mark.asyncio
    async def test_storage_connection_failure(self):
        """Test storage handles connection failure."""
        with patch("app.core.rate_limiting.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(side_effect=Exception("Connection failed"))

            from app.core.rate_limiting import RedisRateLimitStorage
            storage = RedisRateLimitStorage("redis://localhost:6379")
            await storage.connect()

            assert storage.is_available is False

    @pytest.mark.asyncio
    async def test_storage_disconnect(self, mock_redis):
        """Test storage disconnection."""
        with patch("app.core.rate_limiting.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            from app.core.rate_limiting import RedisRateLimitStorage
            storage = RedisRateLimitStorage("redis://localhost:6379")
            await storage.connect()
            await storage.disconnect()

            assert storage.is_available is False

    @pytest.mark.asyncio
    async def test_increment_when_available(self, mock_redis):
        """Test increment when Redis is available."""
        with patch("app.core.rate_limiting.aioredis") as mock_aioredis:
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            from app.core.rate_limiting import RedisRateLimitStorage
            storage = RedisRateLimitStorage("redis://localhost:6379")
            await storage.connect()

            result = await storage.increment("test_key", 60)

            assert result == 1

    @pytest.mark.asyncio
    async def test_increment_when_unavailable(self):
        """Test increment returns 0 when Redis unavailable (fail-open)."""
        from app.core.rate_limiting import RedisRateLimitStorage
        storage = RedisRateLimitStorage("redis://localhost:6379")
        # Don't connect - simulating unavailable

        result = await storage.increment("test_key", 60)

        assert result == 0  # Fail-open behavior


class TestGermanErrorMessages:
    """Tests for German error message handler."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request for error handler."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user = None
        request.url = Mock()
        request.url.path = "/api/v1/documents"
        request.client = Mock()
        request.client.host = "192.168.1.100"
        return request

    def test_german_error_response(self, mock_request):
        """Test that error response is in German."""
        from slowapi.errors import RateLimitExceeded
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            # Create a mock Limit object
            mock_limit = Mock()
            mock_limit.error_message = None
            mock_limit.limit = "10/minute"

            exc = RateLimitExceeded(mock_limit)
            exc.retry_after = 60

            response = rate_limit_exceeded_handler_german(mock_request, exc)

        assert response.status_code == 429
        # Check response is JSONResponse
        assert isinstance(response, JSONResponse)

    def test_error_includes_retry_after(self, mock_request):
        """Test that error includes retry-after header."""
        from slowapi.errors import RateLimitExceeded
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            # Create a mock Limit object
            mock_limit = Mock()
            mock_limit.error_message = None
            mock_limit.limit = "10/minute"

            exc = RateLimitExceeded(mock_limit)
            exc.retry_after = 120

            response = rate_limit_exceeded_handler_german(mock_request, exc)

        assert "Retry-After" in response.headers


class TestCheckRateLimitBudget:
    """Tests for rate limit budget checking."""

    @pytest.mark.asyncio
    async def test_budget_when_redis_unavailable(self):
        """Test budget check returns available when Redis unavailable (fail-open)."""
        # Dieser Test prueft den Fail-OPEN-Pfad (graceful degradation). Die Quelle
        # entscheidet anhand settings.RATE_LIMIT_FAIL_CLOSED; im Container ist das
        # True (-> wuerde RateLimitStorageError werfen). Fuer den Fail-Open-Vertrag
        # explizit auf False patchen. (Den Fail-CLOSED-Pfad deckt
        # test_rate_limiting_fail_closed.py ab.)
        with patch("app.core.rate_limiting.settings.RATE_LIMIT_FAIL_CLOSED", False), \
             patch("app.core.rate_limiting.get_redis_storage", AsyncMock(return_value=None)):
            from app.core.rate_limiting import check_rate_limit_budget

            result = await check_rate_limit_budget("user123", "ocr", "free")

        assert result["available"] is True
        assert "unavailable" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_budget_free_tier_limits(self):
        """Test budget returns correct limits for free tier."""
        mock_storage = AsyncMock()
        mock_storage.is_available = True
        mock_storage._redis = AsyncMock()
        mock_storage._redis.get = AsyncMock(return_value="5")

        with patch("app.core.rate_limiting.get_redis_storage", AsyncMock(return_value=mock_storage)):
            from app.core.rate_limiting import check_rate_limit_budget

            result = await check_rate_limit_budget("user123", "ocr", "free")

        assert "remaining" in result
        assert "limit" in result


class TestIncrementRateLimitUsage:
    """Tests for rate limit usage incrementing."""

    @pytest.mark.asyncio
    async def test_increment_when_redis_unavailable(self):
        """Test increment returns False when Redis unavailable."""
        with patch("app.core.rate_limiting.get_redis_storage", AsyncMock(return_value=None)):
            from app.core.rate_limiting import increment_rate_limit_usage

            result = await increment_rate_limit_usage("user123", "ocr")

        assert result is False

    @pytest.mark.asyncio
    async def test_increment_success(self):
        """Test successful increment."""
        mock_storage = AsyncMock()
        mock_storage.is_available = True
        mock_storage.increment = AsyncMock(return_value=1)

        with patch("app.core.rate_limiting.get_redis_storage", AsyncMock(return_value=mock_storage)):
            from app.core.rate_limiting import increment_rate_limit_usage

            result = await increment_rate_limit_usage("user123", "ocr")

        assert result is True


class TestGetRateLimitInfo:
    """Tests for getting rate limit info."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user = None
        request.client = Mock()
        request.client.host = "192.168.1.100"
        return request

    def test_get_info_unauthenticated(self, mock_request):
        """Test info for unauthenticated user."""
        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            with patch("app.core.rate_limiting.ip_whitelist") as mock_whitelist:
                mock_whitelist.is_whitelisted.return_value = False

                from app.core.rate_limiting import get_rate_limit_info
                info = get_rate_limit_info(mock_request)

        assert info["user_id"] is None
        assert info["user_tier"] == "free"
        assert info["ip_address"] == "192.168.1.100"

    def test_get_info_authenticated(self, mock_request):
        """Test info for authenticated user."""
        mock_request.state.user = Mock()
        mock_request.state.user.id = "user123"
        mock_request.state.user.tier = "premium"

        with patch("app.core.rate_limiting.get_remote_address", return_value="192.168.1.100"):
            with patch("app.core.rate_limiting.ip_whitelist") as mock_whitelist:
                mock_whitelist.is_whitelisted.return_value = False

                from app.core.rate_limiting import get_rate_limit_info
                info = get_rate_limit_info(mock_request)

        assert info["user_id"] == "user123"
        assert info["user_tier"] == "premium"


class TestWhitelistBypass:
    """Tests for whitelist bypass functionality."""

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/v1/test"
        request.client = Mock()
        request.client.host = "127.0.0.1"
        return request

    def test_is_whitelisted_ip(self, mock_request):
        """Test checking if IP is whitelisted."""
        with patch("app.core.rate_limiting.get_remote_address", return_value="127.0.0.1"):
            from app.core.rate_limiting import is_whitelisted_ip
            result = is_whitelisted_ip(mock_request)

        assert result is True  # localhost is whitelisted by default

    def test_non_whitelisted_ip(self, mock_request):
        """Test non-whitelisted IP."""
        with patch("app.core.rate_limiting.get_remote_address", return_value="8.8.8.8"):
            with patch("app.core.rate_limiting.ip_whitelist") as mock_whitelist:
                mock_whitelist.is_whitelisted.return_value = False

                from app.core.rate_limiting import is_whitelisted_ip
                result = is_whitelisted_ip(mock_request)

        assert result is False
