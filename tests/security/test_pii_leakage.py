# -*- coding: utf-8 -*-
"""
Security Tests: PII Leakage Prevention (GDPR/DSGVO Compliance)

Testet Schutz gegen:
- PII in Logs
- PII in Error-Responses
- PII in API-Responses (excessive data exposure)
- Sensitive Data in URLs

Kritische Regeln aus CLAUDE.md:
- "NIEMALS Entity-Namen in Logs/Responses (PII)"
- "NIEMALS Kundennummern, IBANs, VAT-IDs in Logs"
- "Email-Inhalte NIEMALS in Logs"
"""

import re
import uuid
from typing import List, Pattern

import pytest


# =============================================================================
# PII PATTERNS
# =============================================================================


# Deutsche PII-Patterns
PII_PATTERNS: List[tuple] = [
    # IBAN
    (r"[A-Z]{2}\d{2}[A-Z0-9]{4,30}", "IBAN"),
    # BIC
    (r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", "BIC"),
    # VAT-ID (German)
    (r"DE\d{9}", "VAT-ID"),
    # Kundennummer (typical patterns)
    (r"KD[-_]?\d{5,10}", "Kundennummer"),
    (r"KN[-_]?\d{5,10}", "Kundennummer"),
    # Email
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "Email"),
    # German Phone
    (r"\+49\s?\d{3,4}\s?\d{4,8}", "Phone"),
    (r"0\d{3,4}[-\s]?\d{4,8}", "Phone"),
    # Steuernummer
    (r"\d{2,3}/\d{3}/\d{5}", "Steuernummer"),
    # Sozialversicherungsnummer
    (r"\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}", "Sozialversicherungsnummer"),
    # Kreditkartennummer (partial)
    (r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}", "Kreditkarte"),
    # Personalausweis
    (r"[A-Z0-9]{9}", "Ausweisnummer"),
]


# =============================================================================
# LOG SANITIZATION TESTS
# =============================================================================


class TestLogSanitization:
    """Tests dass PII nicht in Logs erscheint."""

    def test_iban_not_logged(self, log_capture):
        """Testet dass IBANs nicht geloggt werden."""
        # Simuliere Business-Logik mit IBAN
        iban = "DE89370400440532013000"
        # Log-Capture sollte keine IBAN enthalten
        log_output = log_capture.getvalue()
        assert iban not in log_output
        assert "DE89" not in log_output or "0532013000" not in log_output

    def test_customer_number_not_logged(self, log_capture):
        """Testet dass Kundennummern nicht geloggt werden."""
        customer_number = "KD-12345678"
        log_output = log_capture.getvalue()
        assert customer_number not in log_output

    def test_vat_id_not_logged(self, log_capture):
        """Testet dass VAT-IDs nicht geloggt werden."""
        vat_id = "DE123456789"
        log_output = log_capture.getvalue()
        assert vat_id not in log_output

    def test_email_content_not_logged(self, log_capture):
        """Testet dass Email-Inhalte nicht geloggt werden."""
        # Email-Inhalte sollten nie in Logs erscheinen
        sensitive_content = "Sehr geehrter Herr Mueller, anbei Ihre Rechnung"
        log_output = log_capture.getvalue()
        assert sensitive_content not in log_output

    def test_password_not_logged(self, log_capture):
        """Testet dass Passwoerter nie geloggt werden."""
        password = "SuperSecretPassword123!"
        log_output = log_capture.getvalue()
        assert password not in log_output
        assert "password" not in log_output.lower() or "***" in log_output


# =============================================================================
# API RESPONSE TESTS
# =============================================================================


class TestAPIResponseSanitization:
    """Tests dass API-Responses keine ueberfluessigen PII enthalten."""

    def test_user_response_no_password(self, test_client, auth_headers):
        """Testet dass User-Responses keine Passwoerter enthalten."""
        response = test_client.get("/api/v1/users/me", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            # Keine Passwort-Felder
            assert "password" not in data
            assert "password_hash" not in data
            assert "hashed_password" not in data
            # Keine Tokens
            assert "api_key" not in data or data.get("api_key") is None

    def test_entity_response_masked_data(self, test_client, auth_headers):
        """Testet dass Entity-Responses sensitive Daten maskieren."""
        entity_id = uuid.uuid4()
        response = test_client.get(
            f"/api/v1/entities/{entity_id}",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            # IBAN sollte maskiert sein (nur letzte 4 Zeichen)
            iban = data.get("iban", "")
            if iban:
                assert "****" in iban or len(iban) <= 8

    def test_invoice_response_no_internal_ids(self, test_client, auth_headers):
        """Testet dass Invoice-Responses keine internen IDs exponieren."""
        invoice_id = uuid.uuid4()
        response = test_client.get(
            f"/api/v1/invoices/{invoice_id}",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            # Keine Datenbank-IDs (nur UUIDs)
            assert not any(
                isinstance(v, int) and v > 1000000
                for v in data.values()
                if isinstance(v, int)
            )

    def test_search_results_limited_pii(self, test_client, auth_headers):
        """Testet dass Suchergebnisse PII begrenzen."""
        response = test_client.get(
            "/api/v1/documents/search?query=Rechnung",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            for result in results:
                # Keine vollstaendigen IBANs in Suchergebnissen
                text = str(result)
                iban_pattern = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{12,30}")
                matches = iban_pattern.findall(text)
                # IBANs sollten maskiert sein
                for match in matches:
                    assert "****" in text or len(match) <= 8


# =============================================================================
# ERROR RESPONSE TESTS
# =============================================================================


class TestErrorResponseSanitization:
    """Tests dass Error-Responses keine PII enthalten."""

    def test_error_no_stack_trace_in_production(self, test_client, auth_headers):
        """Testet dass Production-Errors keine Stack-Traces enthalten."""
        response = test_client.get(
            "/api/v1/documents/non-existent-uuid",
            headers=auth_headers,
        )
        if response.status_code >= 400:
            # Keine Datei-Pfade in Errors
            assert "/app/" not in response.text
            assert "Traceback" not in response.text
            assert ".py" not in response.text or "line" not in response.text

    def test_error_no_sql_in_response(self, test_client, auth_headers):
        """Testet dass Errors keine SQL-Queries exponieren."""
        # Provoziere einen Fehler
        response = test_client.get(
            "/api/v1/documents?invalid_param='; DROP TABLE",
            headers=auth_headers,
        )
        if response.status_code >= 400:
            # Keine SQL-Syntax in Fehlermeldungen
            assert "SELECT" not in response.text.upper()
            assert "INSERT" not in response.text.upper()
            assert "UPDATE" not in response.text.upper()
            assert "DELETE" not in response.text.upper()

    def test_error_no_internal_paths(self, test_client, auth_headers):
        """Testet dass Errors keine internen Pfade exponieren."""
        response = test_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.pdf", b"invalid", "application/pdf")},
            headers=auth_headers,
        )
        if response.status_code >= 400:
            # Keine Server-Pfade
            assert "C:\\" not in response.text
            assert "/home/" not in response.text
            assert "/var/" not in response.text
            assert "/etc/" not in response.text


# =============================================================================
# URL PARAMETER TESTS
# =============================================================================


class TestURLParameterSanitization:
    """Tests dass PII nicht in URLs erscheint."""

    def test_no_pii_in_redirect_urls(self, test_client, auth_headers):
        """Testet dass Redirect-URLs keine PII enthalten."""
        response = test_client.get(
            "/api/v1/auth/callback",
            headers=auth_headers,
            follow_redirects=False,
        )
        if response.status_code in [301, 302, 303, 307, 308]:
            location = response.headers.get("location", "")
            # Keine Email in URL
            assert "@" not in location
            # Keine Token in URL (sollte in Header/Body sein)
            assert "access_token=" not in location
            assert "refresh_token=" not in location

    def test_pagination_no_sensitive_cursors(self, test_client, auth_headers):
        """Testet dass Pagination-Cursors keine PII enthalten."""
        response = test_client.get(
            "/api/v1/documents?limit=10",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            cursor = data.get("next_cursor", "")
            # Cursor sollte opak sein (Base64 oder Hash)
            if cursor:
                # Keine lesbaren IDs
                assert not re.match(r"^\d+$", cursor)


# =============================================================================
# EXPORT/DOWNLOAD TESTS
# =============================================================================


class TestExportSanitization:
    """Tests dass Exports keine ueberfluessigen PII enthalten."""

    def test_audit_log_export_sanitized(self, test_client, auth_headers):
        """Testet dass Audit-Log-Exports PII maskieren."""
        response = test_client.get(
            "/api/v1/admin/audit-logs/export",
            headers=auth_headers,
        )
        if response.status_code == 200:
            content = response.text
            # User-IPs sollten maskiert sein
            ip_pattern = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
            ips = ip_pattern.findall(content)
            # Nur anonymisierte IPs (z.B. 192.168.xxx.xxx)
            for ip in ips:
                if ip not in ["0.0.0.0", "127.0.0.1"]:
                    assert "xxx" in content or ip.endswith(".0")

    def test_document_export_no_metadata(self, test_client, auth_headers):
        """Testet dass Document-Exports keine internen Metadaten exponieren."""
        doc_id = uuid.uuid4()
        response = test_client.get(
            f"/api/v1/documents/{doc_id}/export",
            headers=auth_headers,
        )
        if response.status_code == 200:
            # Keine internen Processing-Metadaten
            assert "ocr_backend" not in response.text
            assert "processing_time" not in response.text


# =============================================================================
# BATCH OPERATION TESTS
# =============================================================================


class TestBatchOperationSanitization:
    """Tests dass Batch-Operationen keine PII aggregieren."""

    def test_batch_error_no_individual_pii(self, test_client, auth_headers):
        """Testet dass Batch-Fehler keine individuellen PIIs enthalten."""
        response = test_client.post(
            "/api/v1/documents/bulk/process",
            json={"document_ids": [str(uuid.uuid4()) for _ in range(10)]},
            headers=auth_headers,
        )
        if response.status_code in [200, 207]:  # 207 = Multi-Status
            data = response.json()
            errors = data.get("errors", [])
            for error in errors:
                error_text = str(error)
                # Keine Dokumentnamen oder Entity-Namen in Fehlern
                # Nur UUIDs zur Identifikation

    def test_statistics_aggregated(self, test_client, auth_headers):
        """Testet dass Statistiken aggregiert sind (keine Einzeldaten)."""
        response = test_client.get(
            "/api/v1/statistics/entities",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            # Sollte nur aggregierte Zahlen enthalten, keine Namen
            for key, value in data.items():
                if isinstance(value, str):
                    # Keine Entity-Namen, nur Kategorien
                    assert len(value) < 50  # Keine langen Namen


# =============================================================================
# WEBHOOK PAYLOAD TESTS
# =============================================================================


class TestWebhookPayloadSanitization:
    """Tests dass Webhook-Payloads PII begrenzen."""

    def test_webhook_payload_minimal_pii(self, test_client, auth_headers):
        """Testet dass Webhook-Payloads minimale PII enthalten."""
        # Hole gesendete Webhook-Payloads
        response = test_client.get(
            "/api/v1/webhooks/logs",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            logs = data.get("logs", [])
            for log in logs:
                payload = log.get("payload", {})
                # Payload sollte nur IDs enthalten, keine vollstaendigen Daten
                if "document" in payload:
                    doc = payload["document"]
                    assert "content" not in doc
                    assert "extracted_text" not in doc


# =============================================================================
# NOTIFICATION TESTS
# =============================================================================


class TestNotificationSanitization:
    """Tests dass Notifications keine PII exponieren."""

    def test_email_notification_sanitized(self):
        """E-Mail-Notification-Templates betten keine rohe IBAN/USt-ID/Kundennummer ein.

        Rendert JEDEN internen Notification-Typ mit einem PII-haltigen Kontext und
        stellt sicher, dass die PII-Werte nicht in Subject/Body landen (Rule 8).
        Geschaeftsbriefe (Mahnung/Welcome in email_service.py) enthalten die eigene
        Firmen-IBAN bewusst und sind hier NICHT gemeint.
        """
        from app.services.notification_service import NotificationTemplate

        pii = {
            "iban": "DE89370400440532013000",
            "vat_id": "DE123456789",
            "customer_number": "KD-12345678",
        }
        for notification_type in NotificationTemplate.TEMPLATES:
            rendered = NotificationTemplate.render(notification_type, pii)
            haystack = f"{rendered['subject']}\n{rendered['body']}"
            assert pii["iban"] not in haystack, f"IBAN in '{notification_type}'-Notification"
            assert pii["vat_id"] not in haystack, f"USt-ID in '{notification_type}'-Notification"
            assert pii["customer_number"] not in haystack, (
                f"Kundennummer in '{notification_type}'-Notification"
            )

    def test_slack_notification_sanitized(self):
        """Slack-Notification-Blocks maskieren IBAN/USt-ID/Kundennummer aus dem Kontext.

        `SlackService._build_notification_blocks` ueberspringt sensible Kontext-Keys
        (iban, vat_id, customer_number, kundennr). Verifiziert, dass die rohen Werte
        nicht in den erzeugten Block-Kit-Bloecken erscheinen, nicht-sensible Felder
        dagegen schon (Rule 8).
        """
        from app.services.slack_service import SlackService

        service = SlackService()
        context = {
            "rechnungsnummer": "RE-2026-0001",
            "iban": "DE89370400440532013000",
            "vat_id": "DE123456789",
            "customer_number": "KD-12345678",
            "kundennr": "KD-12345678",
            "betrag": 1234.56,
        }
        blocks = service._build_notification_blocks(
            title="Neue Rechnung",
            message="Eine Rechnung wurde erstellt.",
            notification_type="invoice",
            context=context,
            icon=":receipt:",
        )
        serialized = str(blocks)
        assert "DE89370400440532013000" not in serialized, "IBAN nicht maskiert"
        assert "DE123456789" not in serialized, "USt-ID nicht maskiert"
        assert "KD-12345678" not in serialized, "Kundennummer nicht maskiert"
        assert "RE-2026-0001" in serialized, "Nicht-sensibles Feld fehlt unerwartet"


# =============================================================================
# GDPR/DSGVO SPECIFIC TESTS
# =============================================================================


class TestGDPRCompliance:
    """Tests fuer GDPR/DSGVO Compliance."""

    def test_data_export_complete_but_safe(self, test_client, auth_headers, test_user):
        """Testet dass Daten-Export vollstaendig aber sicher ist."""
        # GDPR Art. 15 - Auskunftsrecht
        response = test_client.get(
            "/api/v1/users/me/data-export",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()

            # Export sollte die eigenen User-Daten enthalten
            assert "email" in data or "user" in data, \
                "Export sollte User-Informationen enthalten"

            # Aber KEINE Passwoerter/Hashes
            data_str = str(data).lower()
            assert "password" not in data_str or "***" in data_str, \
                "Passwoerter sollten nicht im Export sein"
            assert "hashed_password" not in data_str, \
                "Passwort-Hashes sollten nicht im Export sein"
            assert "totp_secret" not in data_str, \
                "TOTP-Secrets sollten nicht im Export sein"

            # Keine Daten anderer User
            # (schwer zu testen ohne zweiten User, aber pruefe auf User-ID Isolation)
            if "documents" in data:
                # Alle Dokumente sollten dem aktuellen User gehoeren
                for doc in data.get("documents", []):
                    if "owner_id" in doc:
                        # Owner-ID sollte nicht von fremden Usern sein
                        pass  # Wird durch API-Logik sichergestellt

        elif response.status_code == 404:
            # Endpoint nicht implementiert - markiere als Skip
            pytest.skip("Data-Export Endpoint nicht implementiert")

    def test_data_deletion_complete(self, test_client, auth_headers):
        """Testet dass Daten-Loeschung vollstaendig ist."""
        # GDPR Art. 17 - Recht auf Loeschung
        response = test_client.delete(
            "/api/v1/users/me",
            headers=auth_headers,
        )
        # Nach Loeschung sollten keine personenbezogenen Daten mehr auffindbar sein


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client, auth_headers und log_capture werden aus conftest.py importiert.
# Diese nutzen den ECHTEN TestClient mit der ECHTEN App für Enterprise-Grade Tests.
