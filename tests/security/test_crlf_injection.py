# -*- coding: utf-8 -*-
"""
Security Tests: CRLF Injection (CWE-113)

Tests protection against HTTP Response Splitting and Header Injection:
- CRLF in request headers
- CRLF in response headers
- CRLF in redirect URLs
- CRLF in cookie values
- CRLF in filename headers

Critical Rules from CLAUDE.md:
- "ALWAYS sanitize user input in headers"
- "Prevent CRLF injection (CWE-113)"
"""

import urllib.parse
from typing import Any

import pytest


# =============================================================================
# CRLF PAYLOADS
# =============================================================================


CRLF_PAYLOADS = [
    # Basic CRLF
    "test\r\nX-Injected: true",
    "test\nX-Injected: true",
    "test\rX-Injected: true",

    # URL-encoded CRLF
    "test%0d%0aX-Injected: true",
    "test%0aX-Injected: true",
    "test%0dX-Injected: true",

    # Double URL-encoded
    "test%250d%250aX-Injected: true",

    # Mixed encoding
    "test%0d\nX-Injected: true",
    "test\r%0aX-Injected: true",

    # Unicode CRLF variants
    "test\u000d\u000aX-Injected: true",
    "test\u0085X-Injected: true",  # NEL (Next Line)
    "test\u2028X-Injected: true",  # Line Separator
    "test\u2029X-Injected: true",  # Paragraph Separator

    # Tab-based header injection
    "test\tX-Injected: true",
    "test%09X-Injected: true",
]

# Payloads, die als ROHER HTTP-Header-Wert ueber den Client gesendet werden
# koennen. RFC 7230 erlaubt in Header-Werten nur sichtbares ASCII plus
# Leerzeichen/Tab; httpx/der ASGI-Transport lehnt Nicht-ASCII-Zeilentrenner
# (NEL , LS  , PS  ) bereits CLIENT-SEITIG mit UnicodeEncodeError
# ab - das prueft die Encoding-Grenze des Clients, NICHT die Sanitisierung des
# Servers (CWE-113). Fuer rohe Request-Header ist der echte, transportierbare
# Angriffsvektor ASCII-CR/LF/Tab; genau den decken diese Payloads ab. Die
# vollstaendige CRLF_PAYLOADS-Liste (inkl. Unicode + URL-encoded) bleibt fuer die
# Query-/Body-/Filename-Tests aktiv, wo die Werte URL-kodiert uebertragbar sind
# und der Server die Sanitisierung beweisen muss.
RAW_HEADER_CRLF_PAYLOADS = [p for p in CRLF_PAYLOADS if p.isascii()]

COOKIE_INJECTION_PAYLOADS = [
    "test\r\nSet-Cookie: session=hijacked",
    "test%0d%0aSet-Cookie: session=hijacked",
    "test\r\nSet-Cookie: admin=true; Path=/",
    "test%0d%0aSet-Cookie: admin=true; HttpOnly",
]

CONTENT_INJECTION_PAYLOADS = [
    "test\r\n\r\n<html><script>alert('XSS')</script></html>",
    "test%0d%0a%0d%0a<html>Injected Content</html>",
    "test\r\n\r\n{\"injected\": true}",
    "test%0d%0a%0d%0a<!DOCTYPE html>",
]

REDIRECT_INJECTION_PAYLOADS = [
    "test\r\nLocation: http://evil.com",
    "test%0d%0aLocation: http://evil.com",
    "test\nLocation: http://attacker.com/phishing",
    "//evil.com%0d%0aX-Injected: true",
]


# =============================================================================
# REQUEST HEADER INJECTION TESTS
# =============================================================================


class TestRequestHeaderInjection:
    """Tests against CRLF injection in request headers."""

    @pytest.mark.parametrize("payload", RAW_HEADER_CRLF_PAYLOADS)
    def test_crlf_in_custom_header(self, payload: str, test_client, auth_headers) -> None:
        """Test CRLF injection in custom request headers."""
        headers = {**auth_headers, "X-Custom-Header": payload}

        response = test_client.get("/api/v1/documents", headers=headers)

        # Response should not contain injected headers
        assert "X-Injected" not in response.headers, \
            f"Injizierter Header sollte nicht in Response erscheinen: {payload}"

        # Should not cause server error
        assert response.status_code != 500, \
            f"CRLF sollte keinen Server-Fehler verursachen: {payload}"

    @pytest.mark.parametrize("payload", RAW_HEADER_CRLF_PAYLOADS)
    def test_crlf_in_accept_header(self, payload: str, test_client, auth_headers) -> None:
        """Test CRLF injection in Accept header."""
        headers = {**auth_headers, "Accept": f"application/json{payload}"}

        response = test_client.get("/api/v1/documents", headers=headers)

        assert "X-Injected" not in response.headers
        assert response.status_code != 500

    @pytest.mark.parametrize("payload", RAW_HEADER_CRLF_PAYLOADS)
    def test_crlf_in_user_agent(self, payload: str, test_client, auth_headers) -> None:
        """Test CRLF injection in User-Agent header."""
        headers = {**auth_headers, "User-Agent": f"TestClient/1.0 {payload}"}

        response = test_client.get("/api/v1/documents", headers=headers)

        assert "X-Injected" not in response.headers
        assert response.status_code != 500


# =============================================================================
# RESPONSE HEADER INJECTION TESTS
# =============================================================================


class TestResponseHeaderInjection:
    """Tests against CRLF injection that affects response headers."""

    @pytest.mark.parametrize("payload", COOKIE_INJECTION_PAYLOADS)
    def test_no_cookie_injection_via_headers(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF cannot inject Set-Cookie headers."""
        headers = {**auth_headers, "X-Custom": payload}

        response = test_client.get("/api/v1/documents", headers=headers)

        # Check for injected cookies
        cookies = response.cookies
        assert "hijacked" not in str(cookies), \
            "Injiziertes Cookie sollte nicht gesetzt werden"

        # Check for Set-Cookie in unusual places
        assert "Set-Cookie" not in str(response.headers).replace("set-cookie", "").replace("Set-Cookie:", "x:"), \
            "Set-Cookie sollte nicht durch Injection erscheinen"

    @pytest.mark.parametrize("payload", CONTENT_INJECTION_PAYLOADS)
    def test_no_body_injection_via_headers(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF cannot inject response body content."""
        headers = {**auth_headers, "X-Custom": payload}

        response = test_client.get("/api/v1/documents", headers=headers)

        # Check that injected content is not in body
        assert "<script>" not in response.text, \
            "Injiziertes Script sollte nicht im Response-Body erscheinen"
        assert "Injected Content" not in response.text, \
            "Injizierter Inhalt sollte nicht im Response-Body erscheinen"


# =============================================================================
# REDIRECT INJECTION TESTS
# =============================================================================


class TestRedirectInjection:
    """Tests against CRLF injection in redirects."""

    @pytest.mark.parametrize("payload", REDIRECT_INJECTION_PAYLOADS)
    def test_no_redirect_injection_in_url(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in URL parameters cannot cause malicious redirects."""
        response = test_client.get(
            f"/api/v1/auth/callback?state={urllib.parse.quote(payload)}",
            headers=auth_headers,
            follow_redirects=False,
        )

        if response.status_code in [301, 302, 303, 307, 308]:
            location = response.headers.get("Location", "")

            # Should not redirect to attacker site
            assert "evil.com" not in location, \
                "Redirect sollte nicht auf bösartige Seite zeigen"
            assert "attacker.com" not in location, \
                "Redirect sollte nicht auf Angreifer-Seite zeigen"

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_header_injection_in_redirect_url(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in redirect URL parameter cannot inject headers."""
        encoded = urllib.parse.quote(payload)

        response = test_client.get(
            f"/api/v1/redirect?url=https://example.com/{encoded}",
            headers=auth_headers,
            follow_redirects=False,
        )

        # Check for injected headers
        assert "X-Injected" not in response.headers

        # Request should be rejected or sanitized
        assert response.status_code in [400, 422, 404, 301, 302, 303, 307, 308]


# =============================================================================
# FILENAME HEADER INJECTION TESTS
# =============================================================================


class TestFilenameHeaderInjection:
    """Tests against CRLF injection in Content-Disposition headers."""

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_injection_in_download_filename(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in filename cannot inject headers."""
        # Request a file download with CRLF in filename
        response = test_client.get(
            f"/api/v1/documents/download?filename={urllib.parse.quote(payload)}",
            headers=auth_headers,
        )

        # Check Content-Disposition header is safe
        content_disp = response.headers.get("Content-Disposition", "")

        assert "X-Injected" not in content_disp, \
            "Content-Disposition sollte keine injizierten Header enthalten"

        # Newlines should be stripped from filename
        if "filename=" in content_disp:
            assert "\r" not in content_disp, \
                "Content-Disposition sollte keine CR enthalten"
            assert "\n" not in content_disp, \
                "Content-Disposition sollte keine LF enthalten"

    @pytest.mark.parametrize("malicious_filename", [
        'test.pdf\r\nX-Injected: true',
        'test.pdf%0d%0aX-Injected: true',
        'test"; filename="evil.exe',
        'test.pdf\r\n\r\n<html>',
    ])
    def test_upload_filename_sanitized(self, malicious_filename: str, test_client, auth_headers) -> None:
        """Test that uploaded filenames with CRLF are sanitized."""
        response = test_client.post(
            "/api/v1/documents/upload",
            files={"file": (malicious_filename, b"test content", "application/pdf")},
            headers=auth_headers,
        )

        # Should not cause server error
        assert response.status_code != 500

        # If accepted, filename should be sanitized
        if response.status_code in [200, 201]:
            data = response.json()
            stored_filename = data.get("filename", "")

            assert "\r" not in stored_filename, \
                "Gespeicherter Dateiname sollte keine CR enthalten"
            assert "\n" not in stored_filename, \
                "Gespeicherter Dateiname sollte keine LF enthalten"
            assert "X-Injected" not in stored_filename, \
                "Gespeicherter Dateiname sollte keine Header-Injection enthalten"


# =============================================================================
# QUERY PARAMETER INJECTION TESTS
# =============================================================================


class TestQueryParameterInjection:
    """Tests against CRLF injection in query parameters."""

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_injection_via_search_param(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in search parameters cannot inject headers."""
        encoded = urllib.parse.quote(payload)

        response = test_client.get(
            f"/api/v1/documents?search={encoded}",
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers
        assert response.status_code != 500

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_injection_via_filter_param(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in filter parameters cannot inject headers."""
        encoded = urllib.parse.quote(payload)

        response = test_client.get(
            f"/api/v1/documents?document_type={encoded}",
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers
        assert response.status_code != 500


# =============================================================================
# POST BODY INJECTION TESTS
# =============================================================================


class TestPostBodyInjection:
    """Tests against CRLF injection in POST body fields."""

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_injection_via_json_field(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in JSON fields cannot inject headers."""
        response = test_client.post(
            "/api/v1/folders",
            json={"name": payload, "description": "test"},
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers
        assert response.status_code != 500

    @pytest.mark.parametrize("payload", CRLF_PAYLOADS)
    def test_no_injection_via_form_field(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in form fields cannot inject headers."""
        response = test_client.post(
            "/api/v1/documents/search",
            data={"query": payload},
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers
        assert response.status_code != 500


# =============================================================================
# LOGGING INJECTION TESTS
# =============================================================================


class TestLoggingInjection:
    """Tests against CRLF injection that could affect logs."""

    @pytest.mark.parametrize("payload", [
        "test\r\n[ERROR] Fake error injected",
        "test\n[CRITICAL] System compromised",
        "test%0d%0a[WARN] Injected warning",
    ])
    def test_no_log_injection_via_header(self, payload: str, test_client, auth_headers, log_capture) -> None:
        """Test that CRLF in headers cannot inject fake log entries."""
        headers = {**auth_headers, "X-Request-ID": payload}

        test_client.get("/api/v1/documents", headers=headers)

        log_output = log_capture.getvalue()

        # Fake log entries should not appear as separate lines
        assert "[ERROR] Fake error" not in log_output, \
            "Gefälschter Log-Eintrag sollte nicht erscheinen"
        assert "[CRITICAL] System compromised" not in log_output, \
            "Gefälschter kritischer Log-Eintrag sollte nicht erscheinen"


# =============================================================================
# WEBSOCKET INJECTION TESTS
# =============================================================================


# G5 (2026-06-03): Der Platzhalter `test_no_injection_via_ws_header`
# (@pytest.mark.skip("stub")) wurde ERSATZLOS entfernt. CRLF-Header-Injection auf
# WebSocket-Ebene laesst sich mit dem Starlette-TestClient/httpx nicht sinnvoll
# provozieren (Header-Werte werden vor dem Senden validiert; der ASGI-Server
# splittet keine CRLF-Header). Die HTTP-Header-/Query-/Body-CRLF-Tests oben
# decken die relevante Anwendungslogik ab.


# =============================================================================
# EMAIL HEADER INJECTION TESTS
# =============================================================================


class TestEmailHeaderInjection:
    """Tests against CRLF injection in email-related functionality."""

    @pytest.mark.parametrize("payload", [
        "test@example.com\r\nBcc: attacker@evil.com",
        "test@example.com%0d%0aBcc: attacker@evil.com",
        "test@example.com\nCc: attacker@evil.com",
        "test@example.com\r\nSubject: Hijacked",
    ])
    def test_no_email_header_injection(self, payload: str, test_client, auth_headers) -> None:
        """Test that CRLF in email addresses cannot inject email headers."""
        response = test_client.post(
            "/api/v1/notifications/send",
            json={"email": payload, "message": "Test notification"},
            headers=auth_headers,
        )

        # Should reject invalid email or sanitize
        if response.status_code in [200, 202]:
            # If accepted, email should be validated
            # (Bcc injection should not work)
            pass
        else:
            # Erwartet: abgelehnt mit 400/422, oder die Angriffsflaeche
            # existiert gar nicht (404 = Pfad fehlt, 405 = Methode am Pfad
            # nicht erlaubt). 405 ist sicherheitstechnisch gleichwertig zu
            # 404: es gibt keinen POST-Endpunkt, der beliebige
            # Empfaenger-Adressen in E-Mail-Header schreibt.
            assert response.status_code in [400, 422, 404, 405]


# =============================================================================
# EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in CRLF injection prevention."""

    def test_null_byte_injection(self, test_client, auth_headers) -> None:
        """Test that null bytes don't enable CRLF injection."""
        payload = "test\x00\r\nX-Injected: true"

        response = test_client.get(
            "/api/v1/documents",
            headers={**auth_headers, "X-Custom": payload},
        )

        assert "X-Injected" not in response.headers
        assert response.status_code != 500

    def test_double_encoding_blocked(self, test_client, auth_headers) -> None:
        """Test that double URL encoding doesn't bypass CRLF protection."""
        payload = "test%250d%250aX-Injected: true"  # Double encoded

        response = test_client.get(
            f"/api/v1/documents?search={payload}",
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers

    def test_mixed_encoding_blocked(self, test_client, auth_headers) -> None:
        """Test that mixed encoding doesn't bypass protection."""
        payload = "test%0d\nX-Injected: true"  # Mixed: URL-encoded CR + literal LF

        response = test_client.get(
            f"/api/v1/documents?search={urllib.parse.quote(payload)}",
            headers=auth_headers,
        )

        assert "X-Injected" not in response.headers


# =============================================================================
# FIXTURES
# =============================================================================
# Der ``log_capture``-Fixture wird aus conftest.py bezogen. Die frueher hier
# definierte Modul-Variante forderte das Argument ``mocker`` (pytest-mock) an -
# das Plugin ist nicht installiert -> "fixture 'mocker' not found" ERROR bei
# allen TestLoggingInjection-Tests. Der conftest-Fixture leistet dasselbe ohne
# diese Abhaengigkeit, daher wurde die lokale Duplikat-Definition entfernt.
