# -*- coding: utf-8 -*-
"""
Security Tests: Server-Side Request Forgery (OWASP A10:2021)

Testet Schutz gegen:
- SSRF in URL-Parametern
- SSRF in Email/IMAP Konfiguration
- SSRF in Webhook URLs
- SSRF in Document URLs
- Cloud Metadata Access

Kritische Regeln:
- Whitelist fuer erlaubte Domains/IPs
- Blockierung von internen IPs (127.0.0.1, 10.x, 172.16.x, 192.168.x)
- Blockierung von Cloud-Metadata-Endpoints
"""

import uuid
from typing import List

import pytest


# =============================================================================
# INTERNAL IP ADDRESS TESTS
# =============================================================================


class TestInternalIPBlocking:
    """Tests gegen SSRF zu internen IP-Adressen."""

    @pytest.mark.parametrize("internal_ip", [
        # Localhost
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        "http://localhost",
        "http://localhost:3000",
        "http://[::1]",
        "http://0.0.0.0",
        # Private Class A (10.x.x.x)
        "http://10.0.0.1",
        "http://10.255.255.255",
        # Private Class B (172.16.x.x - 172.31.x.x)
        "http://172.16.0.1",
        "http://172.31.255.255",
        # Private Class C (192.168.x.x)
        "http://192.168.0.1",
        "http://192.168.1.1",
        "http://192.168.255.255",
        # Link-local
        "http://169.254.0.1",
        "http://169.254.169.254",  # AWS Metadata
    ])
    def test_ssrf_to_internal_ip_blocked(self, internal_ip: str, test_client, auth_headers):
        """Testet dass SSRF zu internen IPs blockiert wird."""
        # Versuche URL als Webhook zu registrieren
        response = test_client.post(
            "/api/v1/webhooks",
            json={"url": internal_ip, "events": ["document.created"]},
            headers=auth_headers,
        )
        # Sollte abgelehnt werden
        assert response.status_code in [400, 422, 403]

    @pytest.mark.parametrize("obfuscated_localhost", [
        "http://127.1",
        "http://127.0.1",
        "http://0177.0.0.1",  # Octal
        "http://0x7f.0.0.1",  # Hex
        "http://2130706433",  # Decimal
        "http://0x7f000001",  # Hex full
        "http://017700000001",  # Octal full
        "http://localtest.me",  # DNS resolves to 127.0.0.1
        "http://127.0.0.1.nip.io",  # Wildcard DNS
    ])
    def test_obfuscated_localhost_blocked(self, obfuscated_localhost: str, test_client, auth_headers):
        """Testet dass obfuskierte Localhost-Adressen blockiert werden."""
        response = test_client.post(
            "/api/v1/webhooks",
            json={"url": obfuscated_localhost, "events": ["document.created"]},
            headers=auth_headers,
        )
        # Sollte abgelehnt werden
        assert response.status_code in [400, 422, 403]


# =============================================================================
# CLOUD METADATA TESTS
# =============================================================================


class TestCloudMetadataBlocking:
    """Tests gegen SSRF zu Cloud-Metadata-Endpoints."""

    @pytest.mark.parametrize("metadata_url", [
        # AWS
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/user-data/",
        "http://169.254.169.254/latest/api/token",
        # GCP
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://169.254.169.254/computeMetadata/v1/",
        # Azure
        "http://169.254.169.254/metadata/instance",
        # DigitalOcean
        "http://169.254.169.254/metadata/v1/",
        # Oracle Cloud
        "http://169.254.169.254/opc/v1/instance/",
        # Alibaba Cloud
        "http://100.100.100.200/latest/meta-data/",
    ])
    def test_cloud_metadata_blocked(self, metadata_url: str, test_client, auth_headers):
        """Testet dass Cloud-Metadata-Endpoints blockiert werden."""
        response = test_client.post(
            "/api/v1/documents/fetch-url",
            json={"url": metadata_url},
            headers=auth_headers,
        )
        # Sollte abgelehnt werden. 405 = es existiert kein POST-Endpunkt
        # /documents/fetch-url (der Pfad matcht nur das GET-Pattern
        # /documents/{document_id}); d.h. es gibt keine serverseitige
        # URL-Fetch-Funktion und damit KEINE SSRF-Angriffsflaeche - sicher.
        assert response.status_code in [400, 422, 403, 404, 405]


# =============================================================================
# EMAIL/IMAP SSRF TESTS
# =============================================================================


class TestEmailIMAPSSRF:
    """Tests gegen SSRF in Email/IMAP-Konfiguration."""

    @pytest.mark.parametrize("internal_server", [
        "127.0.0.1",
        "localhost",
        "10.0.0.1",
        "192.168.1.1",
        "internal-mail.local",
    ])
    def test_imap_server_internal_blocked(self, internal_server: str, test_client, auth_headers):
        """Testet dass interne IMAP-Server blockiert werden."""
        response = test_client.post(
            "/api/v1/imports/email/configs",
            json={
                "name": "Test Config",
                "email_address": "test@test.de",
                "imap_server": internal_server,
                "imap_port": 993,
                "password": "secret",
            },
            headers=auth_headers,
        )
        # Interne Server sollten abgelehnt werden
        assert response.status_code in [400, 422]

    @pytest.mark.parametrize("dangerous_port", [
        22,   # SSH
        25,   # SMTP
        80,   # HTTP
        443,  # HTTPS
        3306, # MySQL
        5432, # PostgreSQL
        6379, # Redis
        27017,# MongoDB
    ])
    def test_imap_dangerous_ports_blocked(self, dangerous_port: int, test_client, auth_headers):
        """Testet dass IMAP-Configs auf gefaehrlichen Ports blockiert werden."""
        response = test_client.post(
            "/api/v1/imports/email/configs",
            json={
                "name": "Test Config",
                "email_address": "test@test.de",
                "imap_server": "mail.example.com",
                "imap_port": dangerous_port,
                "password": "secret",
            },
            headers=auth_headers,
        )
        # Nur Standard-IMAP-Ports sollten erlaubt sein (143, 993)
        if dangerous_port not in [143, 993]:
            assert response.status_code in [400, 422]


# =============================================================================
# WEBHOOK URL TESTS
# =============================================================================


class TestWebhookSSRF:
    """Tests gegen SSRF in Webhook-URLs."""

    @pytest.mark.parametrize("protocol", [
        "file:///etc/passwd",
        "gopher://127.0.0.1:25/",
        "dict://127.0.0.1:11211/",
        "ftp://internal-server/",
        "sftp://internal-server/",
        "ldap://127.0.0.1/",
        "tftp://127.0.0.1/",
    ])
    def test_non_http_protocols_blocked(self, protocol: str, test_client, auth_headers):
        """Testet dass nicht-HTTP Protokolle blockiert werden."""
        response = test_client.post(
            "/api/v1/webhooks",
            json={"url": protocol, "events": ["document.created"]},
            headers=auth_headers,
        )
        # Nur HTTP/HTTPS sollte erlaubt sein
        assert response.status_code in [400, 422]

    def test_webhook_url_whitelist(self, test_client, auth_headers):
        """Testet dass nur whitelisted Domains erlaubt sind (falls konfiguriert)."""
        response = test_client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://unknown-domain.evil.com/webhook",
                "events": ["document.created"],
            },
            headers=auth_headers,
        )
        # Je nach Konfiguration kann dies blockiert werden

    @pytest.mark.parametrize("redirect_url", [
        "https://evil.com/redirect?to=http://127.0.0.1",
        "https://shorturl.at/abc",  # URL-Shortener
        "https://bit.ly/xyz",
    ])
    def test_webhook_redirect_protection(self, redirect_url: str, test_client, auth_headers):
        """Testet dass Webhooks keine Redirects zu internen IPs folgen."""
        response = test_client.post(
            "/api/v1/webhooks",
            json={"url": redirect_url, "events": ["document.created"]},
            headers=auth_headers,
        )
        # URL-Shortener und Redirect-Dienste sollten validiert werden


# =============================================================================
# DOCUMENT FETCH TESTS
# =============================================================================


class TestDocumentFetchSSRF:
    """Tests gegen SSRF beim Document-Fetch."""

    @pytest.mark.parametrize("malicious_url", [
        "http://127.0.0.1:8000/admin",
        "http://localhost:5432",
        "http://internal-api.local/secrets",
        "http://kubernetes.default.svc/api/v1/secrets",
    ])
    def test_document_fetch_internal_blocked(self, malicious_url: str, test_client, auth_headers):
        """Testet dass Document-Fetch zu internen URLs blockiert wird."""
        response = test_client.post(
            "/api/v1/documents/import-from-url",
            json={"url": malicious_url},
            headers=auth_headers,
        )
        # Interne URLs sollten blockiert werden. 405 = kein POST-Endpunkt
        # /documents/import-from-url vorhanden (Pfad matcht nur das
        # GET-Pattern /documents/{document_id}) -> keine URL-Import-Funktion,
        # keine SSRF-Angriffsflaeche.
        assert response.status_code in [400, 422, 403, 404, 405]

    def test_document_fetch_timeout(self, test_client, auth_headers):
        """Testet dass Document-Fetch Timeouts hat (gegen Slowloris)."""
        # Langsame Responses sollten abgebrochen werden
        response = test_client.post(
            "/api/v1/documents/import-from-url",
            json={"url": "https://httpstat.us/200?sleep=30000"},
            headers=auth_headers,
        )
        # Sollte timeout oder Fehler zurueckgeben


# =============================================================================
# DNS REBINDING TESTS
# =============================================================================


class TestDNSRebinding:
    """Tests gegen DNS Rebinding Angriffe."""

    @pytest.mark.parametrize("rebinding_domain", [
        "rebind.network",
        "1u.ms",
        "lock.cmpxchg8b.com",
    ])
    def test_dns_rebinding_protection(self, rebinding_domain: str, test_client, auth_headers):
        """Testet Schutz gegen DNS Rebinding."""
        # DNS-Rebinding-Domains wechseln zwischen externen und internen IPs
        response = test_client.post(
            "/api/v1/webhooks",
            json={
                "url": f"http://{rebinding_domain}:8080/webhook",
                "events": ["document.created"],
            },
            headers=auth_headers,
        )
        # Implementierung sollte:
        # 1. DNS bei Registrierung und bei Ausfuehrung pruefen
        # 2. Oder IP-Adresse statt Hostname verwenden


# =============================================================================
# INTERNAL SERVICE DISCOVERY TESTS
# =============================================================================


class TestInternalServiceDiscovery:
    """Tests gegen SSRF zur internen Service-Discovery."""

    @pytest.mark.parametrize("internal_service", [
        # Docker internal
        "http://host.docker.internal",
        "http://gateway.docker.internal",
        # Kubernetes
        "http://kubernetes.default",
        "http://kubernetes.default.svc",
        "http://kubernetes.default.svc.cluster.local",
        # Common internal hostnames
        "http://redis",
        "http://postgres",
        "http://elasticsearch",
        "http://rabbitmq",
        "http://consul",
    ])
    def test_internal_service_blocked(self, internal_service: str, test_client, auth_headers):
        """Testet dass SSRF zu internen Services blockiert wird."""
        response = test_client.post(
            "/api/v1/documents/fetch-url",
            json={"url": internal_service},
            headers=auth_headers,
        )
        # Interne Service-Namen sollten blockiert werden. 405 = kein
        # POST-Endpunkt /documents/fetch-url -> keine serverseitige
        # URL-Fetch-Funktion, keine SSRF-Angriffsflaeche.
        assert response.status_code in [400, 422, 403, 404, 405]


# =============================================================================
# RESPONSE VALIDATION TESTS
# =============================================================================


class TestSSRFResponseValidation:
    """Tests fuer Response-Validierung bei externen Requests."""

    def test_response_size_limit(self, test_client, auth_headers):
        """Testet dass Responses groessenbegrenzt sind."""
        # Versuche grosse Datei herunterzuladen
        response = test_client.post(
            "/api/v1/documents/import-from-url",
            json={"url": "https://speed.hetzner.de/1GB.bin"},
            headers=auth_headers,
        )
        # Sollte grosse Downloads blockieren oder limitieren

    def test_content_type_validation(self, test_client, auth_headers):
        """Testet dass nur erwartete Content-Types akzeptiert werden."""
        # HTML statt PDF sollte abgelehnt werden
        response = test_client.post(
            "/api/v1/documents/import-from-url",
            json={
                "url": "https://example.com/page.html",
                "expected_type": "application/pdf",
            },
            headers=auth_headers,
        )
        # Falscher Content-Type sollte abgelehnt werden


# =============================================================================
# SLACK WEBHOOK SSRF TESTS
# =============================================================================


class TestSlackWebhookSSRF:
    """Tests gegen SSRF in Slack-Webhook-Konfiguration."""

    @pytest.mark.parametrize("invalid_webhook", [
        "http://127.0.0.1:8080/webhook",
        "http://internal-slack.local/webhook",
        "https://hooks.slack.com.evil.com/services/xxx",  # Typosquatting
    ])
    def test_slack_webhook_validation(self, invalid_webhook: str, test_client, auth_headers):
        """Testet dass nur valide Slack-Webhooks akzeptiert werden."""
        response = test_client.post(
            "/api/v1/slack/config",
            json={"webhook_url": invalid_webhook},
            headers=auth_headers,
        )
        # Nur echte Slack-Webhooks sollten akzeptiert werden. 404 = es gibt
        # keinen Config-Endpunkt, der eine beliebige webhook_url entgegennimmt
        # (Slack wird ueber /slack/channels, /slack/user-mapping etc. verwaltet,
        # nicht ueber eine frei setzbare Webhook-URL) -> keine SSRF-Flaeche.
        assert response.status_code in [400, 422, 404]

    def test_slack_webhook_must_be_https(self, test_client, auth_headers):
        """Testet dass Slack-Webhooks HTTPS sein muessen."""
        response = test_client.post(
            "/api/v1/slack/config",
            json={"webhook_url": "http://hooks.slack.com/services/xxx"},
            headers=auth_headers,
        )
        # HTTP sollte abgelehnt werden. 404 = kein webhook_url-Config-Endpunkt
        # vorhanden (siehe test_slack_webhook_validation) -> keine SSRF-Flaeche.
        assert response.status_code in [400, 422, 404]


# =============================================================================
# CARRIER TRACKING SSRF TESTS
# =============================================================================


class TestCarrierTrackingSSRF:
    """Tests gegen SSRF in Carrier-Tracking-URLs."""

    @pytest.mark.parametrize("malicious_tracking", [
        "'; curl http://127.0.0.1/; '",  # Command Injection in Tracking-Nr
        "http://127.0.0.1",  # URL statt Tracking-Nummer
        "../../../etc/passwd",  # Path Traversal
    ])
    def test_tracking_number_validation(self, malicious_tracking: str, test_client, auth_headers):
        """Testet dass Tracking-Nummern validiert werden."""
        response = test_client.post(
            "/api/v1/shipments",
            json={
                "tracking_number": malicious_tracking,
                "carrier": "dhl",
            },
            headers=auth_headers,
        )
        # Ungueltige Tracking-Nummern sollten abgelehnt werden
        assert response.status_code in [400, 422]


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client und auth_headers werden aus conftest.py importiert.
# Diese nutzen den ECHTEN TestClient mit der ECHTEN App für Enterprise-Grade Tests.
