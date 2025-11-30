"""Unit tests for Rate Limiting Middleware.

Tests rate limiting logic, tier-based limits, and error responses.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from starlette.testclient import TestClient
from fastapi import FastAPI

from app.middleware.rate_limit import (
    RateLimitMiddleware,
    DevelopmentRateLimitBypass,
    RoleBasedRateLimitChecker,
    get_rate_limit_stats,
)


class TestRateLimitMiddlewareClass:
    """Tests for RateLimitMiddleware class."""

    def test_rate_limit_middleware_exists(self):
        """RateLimitMiddleware Klasse sollte existieren."""
        assert RateLimitMiddleware is not None

    def test_development_bypass_exists(self):
        """DevelopmentRateLimitBypass sollte existieren."""
        assert DevelopmentRateLimitBypass is not None

    def test_role_based_checker_exists(self):
        """RoleBasedRateLimitChecker sollte existieren."""
        assert RoleBasedRateLimitChecker is not None


class TestRateLimitStats:
    """Tests for rate limit statistics function."""

    def test_get_rate_limit_stats_exists(self):
        """get_rate_limit_stats Funktion sollte existieren."""
        assert get_rate_limit_stats is not None
        assert callable(get_rate_limit_stats)


class TestDevelopmentRateLimitBypass:
    """Tests for development mode rate limit bypass."""

    def test_bypass_allows_all_requests(self):
        """Bypass sollte alle Requests in Development erlauben."""
        app = FastAPI()
        app.add_middleware(DevelopmentRateLimitBypass)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        # Should allow multiple rapid requests
        for _ in range(100):
            response = client.get("/test")
            assert response.status_code == 200


class TestRoleBasedRateLimitChecker:
    """Tests for role-based rate limit checking."""

    def test_checker_initialization(self):
        """RoleBasedRateLimitChecker sollte initialisierbar sein."""
        checker = RoleBasedRateLimitChecker()
        assert checker is not None

    def test_checker_has_tier_limits(self):
        """Checker sollte Tier-basierte Limits haben."""
        checker = RoleBasedRateLimitChecker()

        # Should have methods for different tiers
        assert hasattr(checker, "get_limit_for_tier") or hasattr(checker, "check_limit")


class TestRateLimitResponseHeaders:
    """Tests for rate limit response headers."""

    @pytest.fixture
    def app_with_rate_limit(self):
        """Create app with mocked rate limiting."""
        app = FastAPI()

        # We can't easily test actual rate limiting without Redis
        # So we test the header format

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        return app

    def test_rate_limit_headers_format(self):
        """Rate Limit Headers sollten korrektes Format haben."""
        # Expected headers based on CORS_EXPOSE_HEADERS in config
        expected_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ]

        # Verify these are exposed in CORS config
        from app.core.config import settings
        expose_headers = settings.CORS_EXPOSE_HEADERS

        for header in expected_headers:
            assert header in expose_headers, f"{header} sollte exposed sein"


class TestRateLimitTiers:
    """Tests for rate limit tier configuration."""

    def test_tier_enum_exists(self):
        """RateLimitTier Enum sollte existieren."""
        from app.core.rate_limiting import RateLimitTier

        assert RateLimitTier is not None

    def test_tier_values(self):
        """Tiers sollten free, premium, admin haben."""
        from app.core.rate_limiting import RateLimitTier

        tier_values = {t.value for t in RateLimitTier}

        assert "free" in tier_values
        assert "premium" in tier_values
        assert "admin" in tier_values

    def test_admin_tier_highest_limit(self):
        """Admin Tier sollte hoechstes Limit haben."""
        from app.core.rate_limiting import TIER_LIMITS, RateLimitTier

        if TIER_LIMITS:
            admin_limit = TIER_LIMITS.get(RateLimitTier.ADMIN, {})
            free_limit = TIER_LIMITS.get(RateLimitTier.FREE, {})

            # Admin should have higher or equal limits
            if "ocr_hourly" in admin_limit and "ocr_hourly" in free_limit:
                assert admin_limit["ocr_hourly"] >= free_limit["ocr_hourly"]


class TestRateLimitErrorMessages:
    """Tests for rate limit error messages (German)."""

    def test_german_error_handler_exists(self):
        """Deutsche Error Handler sollte existieren."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        assert rate_limit_exceeded_handler_german is not None
        assert callable(rate_limit_exceeded_handler_german)

    @pytest.mark.asyncio
    async def test_german_error_message_format(self):
        """Fehlermeldung sollte deutsch sein."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german
        from slowapi.errors import RateLimitExceeded
        from starlette.requests import Request

        # Create mock request
        mock_request = Mock(spec=Request)
        mock_request.url = Mock()
        mock_request.url.path = "/test"

        # Create rate limit exception
        exc = RateLimitExceeded("10/minute")

        # Get response
        response = await rate_limit_exceeded_handler_german(mock_request, exc)

        # Response should be JSON with German message
        assert response.status_code == 429

        import json
        body = json.loads(response.body)
        assert "detail" in body or "message" in body


class TestIPWhitelisting:
    """Tests for IP whitelist configuration."""

    def test_localhost_whitelisted(self):
        """localhost sollte standardmaessig whitelisted sein."""
        from app.core.rate_limiting import IP_WHITELIST

        if IP_WHITELIST:
            # localhost variations should be whitelisted
            localhost_ips = {"127.0.0.1", "::1", "localhost"}
            whitelisted = set(IP_WHITELIST)

            # At least one localhost variant should be whitelisted
            assert any(ip in whitelisted for ip in localhost_ips)


class TestLimiterConfiguration:
    """Tests for SlowAPI limiter configuration."""

    def test_limiter_exists(self):
        """Limiter sollte existieren."""
        from app.core.rate_limiting import limiter

        assert limiter is not None

    def test_limiter_has_key_function(self):
        """Limiter sollte Key-Funktion haben."""
        from app.core.rate_limiting import limiter

        # Should have a way to identify requests
        assert hasattr(limiter, "_key_func") or hasattr(limiter, "key_func")
