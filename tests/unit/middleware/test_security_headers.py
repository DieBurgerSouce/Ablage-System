"""Unit tests for Security Headers Middleware.

Tests that all security headers are correctly added to responses.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient
from fastapi import FastAPI

from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    create_security_headers_middleware,
)


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def app_with_middleware(self):
        """Create FastAPI app with SecurityHeadersMiddleware."""
        app = FastAPI()

        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_hsts=False,  # Disable for tests without HTTPS
            enable_csp=True,
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        return app

    @pytest.fixture
    def client(self, app_with_middleware):
        """Create test client."""
        return TestClient(app_with_middleware)

    def test_x_content_type_options_header(self, client):
        """Response sollte X-Content-Type-Options: nosniff haben."""
        response = client.get("/test")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options_header(self, client):
        """Response sollte X-Frame-Options: DENY haben."""
        response = client.get("/test")

        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection_header(self, client):
        """Response sollte X-XSS-Protection Header haben."""
        response = client.get("/test")

        xss_header = response.headers.get("X-XSS-Protection")
        assert xss_header is not None
        assert "1" in xss_header
        assert "mode=block" in xss_header

    def test_referrer_policy_header(self, client):
        """Response sollte Referrer-Policy Header haben."""
        response = client.get("/test")

        referrer_policy = response.headers.get("Referrer-Policy")
        assert referrer_policy is not None
        assert "strict-origin" in referrer_policy.lower()

    def test_x_dns_prefetch_control_header(self, client):
        """Response sollte X-DNS-Prefetch-Control: off haben."""
        response = client.get("/test")

        assert response.headers.get("X-DNS-Prefetch-Control") == "off"

    def test_x_download_options_header(self, client):
        """Response sollte X-Download-Options: noopen haben."""
        response = client.get("/test")

        assert response.headers.get("X-Download-Options") == "noopen"

    def test_x_permitted_cross_domain_policies_header(self, client):
        """Response sollte X-Permitted-Cross-Domain-Policies: none haben."""
        response = client.get("/test")

        assert response.headers.get("X-Permitted-Cross-Domain-Policies") == "none"

    def test_content_security_policy_header(self, client):
        """Response sollte Content-Security-Policy Header haben."""
        response = client.get("/test")

        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src" in csp
        assert "script-src" in csp

    def test_permissions_policy_header(self, client):
        """Response sollte Permissions-Policy Header haben."""
        response = client.get("/test")

        permissions = response.headers.get("Permissions-Policy")
        assert permissions is not None
        # Should disable dangerous features
        assert "camera=()" in permissions
        assert "microphone=()" in permissions
        assert "geolocation=()" in permissions

    def test_cross_origin_opener_policy_header(self, client):
        """Response sollte Cross-Origin-Opener-Policy Header haben."""
        response = client.get("/test")

        coop = response.headers.get("Cross-Origin-Opener-Policy")
        assert coop == "same-origin"

    def test_cross_origin_resource_policy_header(self, client):
        """Response sollte Cross-Origin-Resource-Policy Header haben."""
        response = client.get("/test")

        corp = response.headers.get("Cross-Origin-Resource-Policy")
        assert corp == "same-origin"

    def test_request_id_header(self, client):
        """Response sollte X-Request-ID Header haben."""
        response = client.get("/test")

        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        # Should be a valid UUID-like string
        assert len(request_id) > 0


class TestHSTSConfiguration:
    """Tests for HSTS header configuration."""

    def test_hsts_disabled_by_default_in_debug(self):
        """HSTS sollte in Debug-Modus deaktiviert sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = True

            app = FastAPI()
            app.add_middleware(
                SecurityHeadersMiddleware,
                enable_hsts=True,  # Try to enable
            )

            @app.get("/test")
            async def test_endpoint():
                return {"message": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            # HSTS should NOT be present in debug mode
            hsts = response.headers.get("Strict-Transport-Security")
            assert hsts is None

    def test_hsts_enabled_in_production(self):
        """HSTS sollte in Production aktiviert sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(
                SecurityHeadersMiddleware,
                enable_hsts=True,
            )

            @app.get("/test")
            async def test_endpoint():
                return {"message": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            assert hsts is not None
            assert "max-age=" in hsts
            assert "includeSubDomains" in hsts


class TestCSPConfiguration:
    """Tests for Content-Security-Policy configuration."""

    def test_csp_includes_default_src(self):
        """CSP sollte default-src 'self' enthalten."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, enable_csp=True)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers.get("Content-Security-Policy")
        assert "default-src 'self'" in csp

    def test_csp_includes_frame_ancestors_none(self):
        """CSP sollte frame-ancestors 'none' enthalten (Clickjacking-Schutz)."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, enable_csp=True)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers.get("Content-Security-Policy")
        assert "frame-ancestors 'none'" in csp

    def test_csp_disabled_when_false(self):
        """CSP sollte deaktivierbar sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, enable_csp=False)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        csp = response.headers.get("Content-Security-Policy")
        assert csp is None


class TestMiddlewareFactory:
    """Tests for middleware factory function."""

    def test_create_security_headers_middleware_returns_class(self):
        """Factory sollte Middleware-Klasse zurueckgeben."""
        middleware_class = create_security_headers_middleware(
            enable_hsts=True,
            enable_csp=True,
        )

        assert middleware_class is not None
        assert issubclass(middleware_class, SecurityHeadersMiddleware)

    def test_factory_creates_configured_middleware(self):
        """Factory sollte konfigurierte Middleware erstellen."""
        middleware_class = create_security_headers_middleware(
            enable_hsts=False,
            enable_csp=False,
        )

        app = FastAPI()
        app.add_middleware(middleware_class)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # CSP should be disabled
        assert response.headers.get("Content-Security-Policy") is None


class TestRequestIdHandling:
    """Tests for X-Request-ID handling."""

    def test_preserves_existing_request_id(self):
        """Middleware sollte existierende Request-ID beibehalten."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        custom_request_id = "my-custom-request-id-12345"
        response = client.get("/test", headers={"X-Request-ID": custom_request_id})

        assert response.headers.get("X-Request-ID") == custom_request_id

    def test_generates_request_id_when_missing(self):
        """Middleware sollte Request-ID generieren wenn fehlend."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")  # No X-Request-ID header

        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        # Should be UUID format (36 chars with dashes)
        assert len(request_id) == 36
