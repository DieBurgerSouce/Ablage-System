"""
Erweiterte Unit Tests fuer Security Headers Middleware.

Tests fuer CSP-Direktiven, Permissions-Policy, HSTS-Konfiguration,
Cross-Origin-Policies und Edge Cases.

P1-10: Security Headers Hardening
"""

import pytest
from unittest.mock import patch, Mock, MagicMock
from starlette.testclient import TestClient
from starlette.responses import Response, JSONResponse, StreamingResponse
from fastapi import FastAPI, HTTPException
import re

from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    create_security_headers_middleware,
)


class TestCSPDirectiveValidation:
    """Tests fuer Content-Security-Policy Direktiven."""

    @pytest.fixture
    def app_with_csp(self):
        """Erstelle App mit aktiviertem CSP."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, enable_csp=True)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        return app

    @pytest.fixture
    def client(self, app_with_csp):
        return TestClient(app_with_csp)

    def test_csp_contains_script_src_self(self, client):
        """CSP sollte script-src 'self' enthalten."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "script-src" in csp
        assert "'self'" in csp

    def test_csp_contains_object_src_none(self, client):
        """CSP sollte object-src 'none' enthalten (Flash/Plugin-Schutz)."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "object-src 'none'" in csp

    def test_csp_contains_base_uri_self(self, client):
        """CSP sollte base-uri 'self' enthalten (base tag Schutz)."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "base-uri 'self'" in csp

    def test_csp_contains_form_action_self(self, client):
        """CSP sollte form-action 'self' enthalten (Form-Hijacking-Schutz)."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "form-action 'self'" in csp

    def test_csp_contains_upgrade_insecure_requests(self, client):
        """CSP sollte upgrade-insecure-requests enthalten."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "upgrade-insecure-requests" in csp

    def test_csp_allows_data_uri_for_images(self, client):
        """CSP sollte data: URIs fuer Bilder erlauben."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "img-src" in csp
        assert "data:" in csp

    def test_csp_allows_blob_for_images(self, client):
        """CSP sollte blob: URIs fuer Bilder erlauben."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "blob:" in csp

    def test_csp_connect_src_self(self, client):
        """CSP sollte connect-src 'self' fuer API-Aufrufe enthalten."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "connect-src" in csp

    def test_csp_font_src_self(self, client):
        """CSP sollte font-src 'self' enthalten."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "font-src 'self'" in csp

    def test_csp_style_src_allows_inline_for_swagger(self, client):
        """CSP sollte 'unsafe-inline' fuer Swagger UI erlauben."""
        response = client.get("/test")
        csp = response.headers.get("Content-Security-Policy")

        assert "style-src" in csp
        assert "'unsafe-inline'" in csp


class TestCSPDebugMode:
    """Tests fuer CSP im Debug-Modus."""

    def test_csp_relaxed_in_debug_mode(self):
        """CSP sollte im Debug-Modus localhost erlauben."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = True

            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, enable_csp=True)

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            csp = response.headers.get("Content-Security-Policy")
            assert csp is not None
            assert "localhost" in csp

    def test_csp_allows_websocket_localhost_in_debug(self):
        """CSP sollte WebSocket zu localhost im Debug erlauben."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = True

            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, enable_csp=True)

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            csp = response.headers.get("Content-Security-Policy")
            assert "ws://localhost" in csp


class TestCSPReportOnlyMode:
    """Tests fuer CSP Report-Only Modus."""

    def test_csp_report_only_uses_correct_header(self):
        """Report-Only sollte korrekten Header verwenden."""
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware, enable_csp=True, csp_report_only=True
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Should use Report-Only header instead of enforcing
        assert response.headers.get("Content-Security-Policy-Report-Only") is not None
        assert response.headers.get("Content-Security-Policy") is None


class TestPermissionsPolicyValidation:
    """Tests fuer Permissions-Policy Header."""

    @pytest.fixture
    def client(self):
        """Erstelle Test-Client."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        return TestClient(app)

    def test_permissions_policy_disables_camera(self, client):
        """Permissions-Policy sollte camera deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "camera=()" in pp

    def test_permissions_policy_disables_microphone(self, client):
        """Permissions-Policy sollte microphone deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "microphone=()" in pp

    def test_permissions_policy_disables_geolocation(self, client):
        """Permissions-Policy sollte geolocation deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "geolocation=()" in pp

    def test_permissions_policy_disables_payment(self, client):
        """Permissions-Policy sollte payment API deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "payment=()" in pp

    def test_permissions_policy_disables_usb(self, client):
        """Permissions-Policy sollte USB API deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "usb=()" in pp

    def test_permissions_policy_disables_midi(self, client):
        """Permissions-Policy sollte MIDI API deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "midi=()" in pp

    def test_permissions_policy_disables_sync_xhr(self, client):
        """Permissions-Policy sollte sync-xhr deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "sync-xhr=()" in pp

    def test_permissions_policy_disables_accelerometer(self, client):
        """Permissions-Policy sollte accelerometer deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "accelerometer=()" in pp

    def test_permissions_policy_disables_gyroscope(self, client):
        """Permissions-Policy sollte gyroscope deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "gyroscope=()" in pp

    def test_permissions_policy_disables_magnetometer(self, client):
        """Permissions-Policy sollte magnetometer deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "magnetometer=()" in pp

    def test_permissions_policy_disables_xr_spatial_tracking(self, client):
        """Permissions-Policy sollte xr-spatial-tracking deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "xr-spatial-tracking=()" in pp

    def test_permissions_policy_disables_screen_wake_lock(self, client):
        """Permissions-Policy sollte screen-wake-lock deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "screen-wake-lock=()" in pp

    def test_permissions_policy_disables_display_capture(self, client):
        """Permissions-Policy sollte display-capture deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "display-capture=()" in pp

    def test_permissions_policy_disables_publickey_credentials(self, client):
        """Permissions-Policy sollte publickey-credentials-get deaktivieren."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        assert "publickey-credentials-get=()" in pp

    def test_permissions_policy_format_valid(self, client):
        """Permissions-Policy sollte korrektes Format haben."""
        response = client.get("/test")
        pp = response.headers.get("Permissions-Policy")

        # Should be comma-separated
        assert ", " in pp

        # Each directive should have ()
        directives = pp.split(", ")
        for directive in directives:
            assert "=" in directive
            assert "()" in directive


class TestHSTSConfigurationExtended:
    """Erweiterte Tests fuer HSTS Konfiguration."""

    def test_hsts_max_age_default(self):
        """HSTS max-age sollte standardmaessig 1 Jahr sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            # 31536000 = 1 year in seconds
            assert "max-age=31536000" in hsts

    def test_hsts_custom_max_age(self):
        """HSTS max-age sollte konfigurierbar sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(
                SecurityHeadersMiddleware,
                enable_hsts=True,
                hsts_max_age=15768000,  # 6 months
            )

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            assert "max-age=15768000" in hsts

    def test_hsts_includes_subdomains(self):
        """HSTS sollte includeSubDomains enthalten."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            assert "includeSubDomains" in hsts

    def test_hsts_includes_preload(self):
        """HSTS sollte preload Direktive enthalten."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            assert "preload" in hsts


class TestCrossOriginPolicies:
    """Tests fuer Cross-Origin Policies."""

    @pytest.fixture
    def client(self):
        """Erstelle Test-Client."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        return TestClient(app)

    def test_cross_origin_opener_policy_same_origin(self, client):
        """COOP sollte same-origin sein."""
        response = client.get("/test")

        coop = response.headers.get("Cross-Origin-Opener-Policy")
        assert coop == "same-origin"

    def test_cross_origin_resource_policy_same_origin(self, client):
        """CORP sollte same-origin sein."""
        response = client.get("/test")

        corp = response.headers.get("Cross-Origin-Resource-Policy")
        assert corp == "same-origin"


class TestFrameOptionsConfiguration:
    """Tests fuer X-Frame-Options Konfiguration."""

    def test_frame_options_default_deny(self):
        """X-Frame-Options sollte standardmaessig DENY sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_frame_options_sameorigin_configurable(self):
        """X-Frame-Options sollte auf SAMEORIGIN konfigurierbar sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, frame_options="SAMEORIGIN")

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


class TestReferrerPolicyConfiguration:
    """Tests fuer Referrer-Policy Konfiguration."""

    def test_referrer_policy_default(self):
        """Referrer-Policy sollte strict-origin-when-cross-origin sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        rp = response.headers.get("Referrer-Policy")
        assert rp == "strict-origin-when-cross-origin"

    def test_referrer_policy_configurable(self):
        """Referrer-Policy sollte konfigurierbar sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, referrer_policy="no-referrer")

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        rp = response.headers.get("Referrer-Policy")
        assert rp == "no-referrer"


class TestSecurityHeadersOnErrors:
    """Tests fuer Security Headers bei Fehler-Responses."""

    def test_security_headers_on_404(self):
        """Security Headers sollten bei 404 vorhanden sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        response = client.get("/nonexistent")

        assert response.status_code == 404
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_exception(self):
        """Security Headers sollten bei Exceptions vorhanden sein."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=500, detail="Internal Error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        assert response.status_code == 500
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


class TestSecurityHeadersOnDifferentResponseTypes:
    """Tests fuer Security Headers bei verschiedenen Response-Typen."""

    def test_security_headers_on_json_response(self):
        """Security Headers bei JSON Response."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/json")
        async def json_endpoint():
            return {"data": "test"}

        client = TestClient(app)
        response = client.get("/json")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_streaming_response(self):
        """Security Headers bei Streaming Response."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        async def generate():
            yield b"chunk1"
            yield b"chunk2"

        @app.get("/stream")
        async def stream_endpoint():
            return StreamingResponse(generate(), media_type="application/octet-stream")

        client = TestClient(app)
        response = client.get("/stream")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_security_headers_on_empty_response(self):
        """Security Headers bei leerer Response (204 No Content)."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.delete("/resource")
        async def delete_endpoint():
            return Response(status_code=204)

        client = TestClient(app)
        response = client.delete("/resource")

        assert response.status_code == 204
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


class TestHeaderValueInjectionPrevention:
    """Tests gegen Header-Value-Injection."""

    def test_request_id_no_newline_injection(self):
        """Request-ID sollte keine Newline-Injection erlauben."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        # Try to inject a header via X-Request-ID
        malicious_id = "valid-id\r\nX-Injected: malicious"
        response = client.get("/test", headers={"X-Request-ID": malicious_id})

        # The response should not have an X-Injected header
        assert response.headers.get("X-Injected") is None


class TestAllSecurityHeadersPresent:
    """Verifiziere dass alle wichtigen Security Headers vorhanden sind."""

    def test_all_essential_headers_present(self):
        """Alle essentiellen Security Headers sollten vorhanden sein (ohne HSTS)."""
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware, enable_hsts=False, enable_csp=True
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Headers die immer vorhanden sein sollten (HSTS nur in Production)
        essential_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "X-DNS-Prefetch-Control",
            "X-Download-Options",
            "X-Permitted-Cross-Domain-Policies",
            "Content-Security-Policy",
            "Permissions-Policy",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
            "X-Request-ID",
        ]

        missing_headers = []
        for header in essential_headers:
            if response.headers.get(header) is None:
                missing_headers.append(header)

        assert (
            len(missing_headers) == 0
        ), f"Fehlende Security Headers: {missing_headers}"

    def test_hsts_present_in_production_mode(self):
        """HSTS sollte in Production-Modus vorhanden sein."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(
                SecurityHeadersMiddleware, enable_hsts=True, enable_csp=True
            )

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            hsts = response.headers.get("Strict-Transport-Security")
            assert hsts is not None, "HSTS sollte in Production vorhanden sein"

    def test_no_server_header_leak(self):
        """Server Header sollte nicht sensitive Informationen enthalten."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        server = response.headers.get("Server")
        if server:
            # Should not reveal detailed version info
            assert "python" not in server.lower() or "uvicorn" in server.lower()


class TestMiddlewareInitialization:
    """Tests fuer Middleware-Initialisierung."""

    def test_middleware_initializes_with_correct_defaults(self):
        """Middleware sollte mit korrekten Standardwerten initialisieren."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            middleware = SecurityHeadersMiddleware(app, enable_hsts=True, enable_csp=True)

            # Verify initialization
            assert middleware.enable_hsts is True
            assert middleware.enable_csp is True
            assert middleware.hsts_max_age == 31536000  # 1 year
            assert middleware.frame_options == "DENY"
            assert middleware.content_type_options == "nosniff"
            assert middleware.referrer_policy == "strict-origin-when-cross-origin"

    def test_middleware_respects_debug_for_hsts(self):
        """HSTS sollte in DEBUG deaktiviert sein auch wenn explizit aktiviert."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = True

            app = FastAPI()
            middleware = SecurityHeadersMiddleware(app, enable_hsts=True)

            assert middleware.enable_hsts is False


class TestConfigurationCombinations:
    """Tests fuer verschiedene Konfigurationskombinationen."""

    def test_minimal_security_config(self):
        """Minimale Sicherheitskonfiguration."""
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware, enable_hsts=False, enable_csp=False
        )

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Basic headers should still be present
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

        # Optional headers should be absent
        assert response.headers.get("Content-Security-Policy") is None

    def test_maximum_security_config(self):
        """Maximale Sicherheitskonfiguration."""
        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.DEBUG = False

            app = FastAPI()
            app.add_middleware(
                SecurityHeadersMiddleware,
                enable_hsts=True,
                hsts_max_age=63072000,  # 2 years
                enable_csp=True,
                frame_options="DENY",
                referrer_policy="no-referrer",
            )

            @app.get("/test")
            async def test_endpoint():
                return {"status": "ok"}

            client = TestClient(app)
            response = client.get("/test")

            # All headers should be present
            assert response.headers.get("Strict-Transport-Security") is not None
            assert response.headers.get("Content-Security-Policy") is not None
            assert response.headers.get("Referrer-Policy") == "no-referrer"


class TestHTTPMethodsSecurityHeaders:
    """Tests dass Security Headers fuer alle HTTP-Methoden gesetzt werden."""

    @pytest.fixture
    def client(self):
        """Erstelle Test-Client mit allen HTTP-Methoden."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/resource")
        async def get_resource():
            return {"method": "GET"}

        @app.post("/resource")
        async def post_resource():
            return {"method": "POST"}

        @app.put("/resource")
        async def put_resource():
            return {"method": "PUT"}

        @app.delete("/resource")
        async def delete_resource():
            return {"method": "DELETE"}

        @app.patch("/resource")
        async def patch_resource():
            return {"method": "PATCH"}

        @app.options("/resource")
        async def options_resource():
            return {"method": "OPTIONS"}

        return TestClient(app)

    def test_security_headers_on_get(self, client):
        """GET sollte Security Headers haben."""
        response = client.get("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_post(self, client):
        """POST sollte Security Headers haben."""
        response = client.post("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_put(self, client):
        """PUT sollte Security Headers haben."""
        response = client.put("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_delete(self, client):
        """DELETE sollte Security Headers haben."""
        response = client.delete("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_patch(self, client):
        """PATCH sollte Security Headers haben."""
        response = client.patch("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_security_headers_on_options(self, client):
        """OPTIONS sollte Security Headers haben."""
        response = client.options("/resource")
        assert response.headers.get("X-Frame-Options") == "DENY"
