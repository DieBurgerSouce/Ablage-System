"""Unit tests für CSRF Middleware.

Testet Double-Submit-Cookie-Pattern CSRF-Schutz.
"""

import pytest
from unittest.mock import patch
from starlette.testclient import TestClient
from fastapi import FastAPI

from app.middleware.csrf import (
    CSRFMiddleware,
    CSRF_HEADER_NAME,
    CSRF_COOKIE_NAME,
    get_csrf_token_response,
)


class TestCSRFMiddleware:
    """Tests für CSRFMiddleware."""

    @pytest.fixture
    def app_with_csrf(self):
        """Erstelle FastAPI-App mit CSRFMiddleware."""
        app = FastAPI()

        app.add_middleware(
            CSRFMiddleware,
            enabled=True,
            cookie_secure=False,  # Für Tests ohne HTTPS
            cookie_samesite="lax",
            bearer_token_bypass=True,
        )

        @app.get("/test")
        async def test_get():
            return {"message": "ok"}

        @app.post("/test")
        async def test_post():
            return {"message": "created"}

        @app.put("/test")
        async def test_put():
            return {"message": "updated"}

        @app.delete("/test")
        async def test_delete():
            return {"message": "deleted"}

        @app.get("/api/v1/auth/csrf-token")
        async def csrf_token():
            return get_csrf_token_response()

        return app

    @pytest.fixture
    def app_with_csrf_disabled(self):
        """Erstelle FastAPI-App mit deaktiviertem CSRF."""
        app = FastAPI()

        app.add_middleware(
            CSRFMiddleware,
            enabled=False,
        )

        @app.post("/test")
        async def test_post():
            return {"message": "created"}

        return app

    @pytest.fixture
    def client(self, app_with_csrf):
        """Erstelle Test-Client."""
        return TestClient(app_with_csrf)

    @pytest.fixture
    def client_disabled(self, app_with_csrf_disabled):
        """Erstelle Test-Client mit deaktiviertem CSRF."""
        return TestClient(app_with_csrf_disabled)

    # ==================== GET Request Tests ====================

    def test_get_request_sets_csrf_cookie(self, client):
        """GET-Request sollte CSRF-Cookie setzen."""
        response = client.get("/test")

        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_get_request_csrf_cookie_has_value(self, client):
        """CSRF-Cookie sollte einen Wert haben."""
        response = client.get("/test")

        csrf_token = response.cookies.get(CSRF_COOKIE_NAME)
        assert csrf_token is not None
        assert len(csrf_token) == 64  # 32 bytes hex = 64 chars

    def test_get_request_succeeds_without_csrf_token(self, client):
        """GET-Request sollte ohne CSRF-Token erfolgreich sein."""
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "ok"}

    # ==================== POST Request Tests ====================

    def test_post_request_fails_without_csrf_token(self, client):
        """POST-Request ohne CSRF-Token sollte fehlschlagen."""
        response = client.post("/test")

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]

    def test_post_request_fails_with_invalid_csrf_token(self, client):
        """POST-Request mit ungültigem CSRF-Token sollte fehlschlagen."""
        # Erst GET um Cookie zu bekommen
        client.get("/test")

        # POST mit falschem Token
        response = client.post(
            "/test",
            headers={CSRF_HEADER_NAME: "invalid_token"}
        )

        assert response.status_code == 403

    def test_post_request_succeeds_with_valid_csrf_token(self, client):
        """POST-Request mit gültigem CSRF-Token sollte erfolgreich sein."""
        # Erst GET um Cookie zu bekommen
        get_response = client.get("/test")
        csrf_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        # POST mit korrektem Token im Header
        response = client.post(
            "/test",
            headers={CSRF_HEADER_NAME: csrf_token}
        )

        assert response.status_code == 200
        assert response.json() == {"message": "created"}

    # ==================== PUT/DELETE Request Tests ====================

    def test_put_request_succeeds_with_valid_csrf_token(self, client):
        """PUT-Request mit gültigem CSRF-Token sollte erfolgreich sein."""
        get_response = client.get("/test")
        csrf_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        response = client.put(
            "/test",
            headers={CSRF_HEADER_NAME: csrf_token}
        )

        assert response.status_code == 200
        assert response.json() == {"message": "updated"}

    def test_delete_request_fails_without_csrf_token(self, client):
        """DELETE-Request ohne CSRF-Token sollte fehlschlagen."""
        response = client.delete("/test")

        assert response.status_code == 403

    def test_delete_request_succeeds_with_valid_csrf_token(self, client):
        """DELETE-Request mit gültigem CSRF-Token sollte erfolgreich sein."""
        get_response = client.get("/test")
        csrf_token = get_response.cookies.get(CSRF_COOKIE_NAME)

        response = client.delete(
            "/test",
            headers={CSRF_HEADER_NAME: csrf_token}
        )

        assert response.status_code == 200
        assert response.json() == {"message": "deleted"}

    # ==================== Bearer Token Bypass Tests ====================

    def test_post_succeeds_with_bearer_token_no_csrf(self, client):
        """POST mit Bearer-Token sollte ohne CSRF-Token erfolgreich sein."""
        response = client.post(
            "/test",
            headers={"Authorization": "Bearer some_jwt_token"}
        )

        assert response.status_code == 200
        assert response.json() == {"message": "created"}

    def test_put_succeeds_with_bearer_token_no_csrf(self, client):
        """PUT mit Bearer-Token sollte ohne CSRF-Token erfolgreich sein."""
        response = client.put(
            "/test",
            headers={"Authorization": "Bearer some_jwt_token"}
        )

        assert response.status_code == 200

    def test_delete_succeeds_with_bearer_token_no_csrf(self, client):
        """DELETE mit Bearer-Token sollte ohne CSRF-Token erfolgreich sein."""
        response = client.delete(
            "/test",
            headers={"Authorization": "Bearer some_jwt_token"}
        )

        assert response.status_code == 200

    # ==================== Disabled CSRF Tests ====================

    def test_post_succeeds_when_csrf_disabled(self, client_disabled):
        """POST sollte erfolgreich sein wenn CSRF deaktiviert ist."""
        response = client_disabled.post("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "created"}

    # ==================== CSRF Token Endpoint Tests ====================

    def test_csrf_token_endpoint_returns_token(self, client):
        """CSRF-Token-Endpoint sollte Token zurückgeben."""
        response = client.get("/api/v1/auth/csrf-token")

        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data
        assert "header_name" in data
        assert data["header_name"] == CSRF_HEADER_NAME

    def test_csrf_token_has_correct_length(self, client):
        """CSRF-Token sollte korrekte Länge haben."""
        response = client.get("/api/v1/auth/csrf-token")

        data = response.json()
        assert len(data["csrf_token"]) == 64  # 32 bytes hex


class TestCSRFTokenGeneration:
    """Tests für CSRF-Token-Generierung."""

    def test_get_csrf_token_response_returns_dict(self):
        """get_csrf_token_response sollte Dict zurückgeben."""
        response = get_csrf_token_response()

        assert isinstance(response, dict)
        assert "csrf_token" in response
        assert "header_name" in response
        assert "cookie_name" in response

    def test_csrf_tokens_are_unique(self):
        """Jedes Token sollte eindeutig sein."""
        tokens = [get_csrf_token_response()["csrf_token"] for _ in range(100)]

        assert len(set(tokens)) == 100  # Alle unique

    def test_csrf_token_is_cryptographically_random(self):
        """Token sollte kryptographisch sicher sein (ausreichende Länge)."""
        response = get_csrf_token_response()

        # 32 bytes = 256 bits Entropie
        assert len(response["csrf_token"]) == 64


class TestCSRFExemptPaths:
    """Tests für CSRF-Ausnahmepfade."""

    @pytest.fixture
    def app_with_exempt_paths(self):
        """App mit benutzerdefinierten Ausnahmepfaden."""
        app = FastAPI()

        app.add_middleware(
            CSRFMiddleware,
            enabled=True,
            cookie_secure=False,
            exempt_paths={"/custom-exempt"},
        )

        @app.post("/custom-exempt")
        async def exempt_endpoint():
            return {"message": "exempt"}

        @app.post("/not-exempt")
        async def not_exempt_endpoint():
            return {"message": "not exempt"}

        return app

    @pytest.fixture
    def client(self, app_with_exempt_paths):
        """Test-Client."""
        return TestClient(app_with_exempt_paths)

    def test_exempt_path_succeeds_without_csrf(self, client):
        """Ausgenommener Pfad sollte ohne CSRF-Token funktionieren."""
        response = client.post("/custom-exempt")

        assert response.status_code == 200
        assert response.json() == {"message": "exempt"}

    def test_non_exempt_path_requires_csrf(self, client):
        """Nicht-ausgenommener Pfad sollte CSRF-Token erfordern."""
        response = client.post("/not-exempt")

        assert response.status_code == 403


class TestCSRFErrorMessages:
    """Tests für CSRF-Fehlermeldungen."""

    @pytest.fixture
    def client(self):
        """Test-Client mit CSRF."""
        app = FastAPI()
        app.add_middleware(CSRFMiddleware, enabled=True, cookie_secure=False)

        @app.post("/test")
        async def test_post():
            return {"message": "ok"}

        return TestClient(app)

    def test_csrf_error_message_is_german(self, client):
        """CSRF-Fehlermeldung sollte auf Deutsch sein."""
        response = client.post("/test")

        assert response.status_code == 403
        detail = response.json()["detail"]
        # Prüfe auf deutsche Wörter
        assert "CSRF" in detail
        assert any(word in detail.lower() for word in ["bitte", "seite", "laden"])

    def test_csrf_error_includes_hint(self, client):
        """CSRF-Fehler sollte Hinweis enthalten."""
        response = client.post("/test")

        data = response.json()
        assert "hint" in data
        assert CSRF_HEADER_NAME in data["hint"]

    def test_csrf_error_includes_error_code(self, client):
        """CSRF-Fehler sollte Error-Code enthalten."""
        response = client.post("/test")

        data = response.json()
        assert "error_code" in data
        assert data["error_code"] == "CSRF_VALIDATION_FAILED"
