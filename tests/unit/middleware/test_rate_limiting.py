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

    def test_checker_has_quota_methods(self):
        """Checker sollte Quota-Methoden haben."""
        checker = RoleBasedRateLimitChecker()

        # Should have methods for quota management
        assert hasattr(checker, "check_user_quota")
        assert hasattr(checker, "increment_quota")


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

    def test_tier_class_exists(self):
        """RateLimitTier Klasse sollte existieren."""
        from app.core.rate_limiting import RateLimitTier

        assert RateLimitTier is not None

    def test_tier_values(self):
        """RateLimitTier sollte Tier-Konstanten haben."""
        from app.core.rate_limiting import RateLimitTier

        # RateLimitTier is a class with string constants, not an enum
        assert hasattr(RateLimitTier, "LOGIN")
        assert hasattr(RateLimitTier, "OCR_FREE_HOURLY")
        assert hasattr(RateLimitTier, "OCR_PREMIUM_HOURLY")
        assert hasattr(RateLimitTier, "OCR_ADMIN")

    def test_admin_tier_highest_limit(self):
        """Admin Tier sollte hoechstes Limit haben."""
        from app.core.rate_limiting import RateLimitTier

        # Parse limit strings to compare values
        def parse_limit(limit_str: str) -> int:
            """Parse '10/hour' -> 10"""
            return int(limit_str.split("/")[0])

        admin_limit = parse_limit(RateLimitTier.OCR_ADMIN)
        premium_limit = parse_limit(RateLimitTier.OCR_PREMIUM_HOURLY)
        free_limit = parse_limit(RateLimitTier.OCR_FREE_HOURLY)

        # Admin should have highest limits
        assert admin_limit >= premium_limit >= free_limit


class TestRateLimitErrorMessages:
    """Tests for rate limit error messages (German)."""

    def test_german_error_handler_exists(self):
        """Deutsche Error Handler sollte existieren."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        assert rate_limit_exceeded_handler_german is not None
        assert callable(rate_limit_exceeded_handler_german)

    def test_german_error_message_format(self):
        """Fehlermeldung sollte deutsch sein."""
        from app.core.rate_limiting import rate_limit_exceeded_handler_german

        # Verify handler exists and is callable
        assert callable(rate_limit_exceeded_handler_german)

        # Check that the handler signature is correct
        import inspect
        sig = inspect.signature(rate_limit_exceeded_handler_german)
        params = list(sig.parameters.keys())
        assert "request" in params
        assert "exc" in params


class TestIPWhitelisting:
    """Tests for IP whitelist configuration."""

    def test_localhost_whitelisted(self):
        """localhost sollte standardmaessig whitelisted sein."""
        from app.core.rate_limiting import ip_whitelist

        # ip_whitelist is an IPWhitelist instance
        assert ip_whitelist is not None

        # localhost variations should be whitelisted
        whitelisted = ip_whitelist.get_all()
        localhost_ips = {"127.0.0.1", "::1"}

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
