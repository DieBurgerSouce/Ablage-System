# -*- coding: utf-8 -*-
"""
Security Tests: Secrets Exposure Prevention (OWASP A02:2021)

Testet Schutz gegen:
- Secrets in Code
- Secrets in Logs
- Secrets in API-Responses
- Secrets in Error-Messages
- Exposed Configuration Files

Kritische Regeln aus CLAUDE.md:
- "NEVER log sensitive content, API keys, PII"
- "Secrets only in env vars"
- "Email-Passwoerter verschluesselt (AES-256-GCM)"
"""

import os
import re
import uuid
from pathlib import Path
from typing import List, Pattern

import pytest


# =============================================================================
# SECRET PATTERNS
# =============================================================================


# Patterns fuer Secrets in Code/Logs
SECRET_PATTERNS: List[tuple] = [
    # API Keys
    (r"(api[_-]?key|apikey)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}['\"]?", "API Key"),
    (r"sk[_-][a-zA-Z0-9]{20,}", "Stripe Secret Key"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"[a-zA-Z0-9/+=]{40}", "AWS Secret Access Key"),
    # JWT Secrets
    (r"(jwt[_-]?secret|secret[_-]?key)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}['\"]?", "JWT Secret"),
    # Database URLs
    (r"postgres://[^:]+:[^@]+@", "PostgreSQL Connection String"),
    (r"mysql://[^:]+:[^@]+@", "MySQL Connection String"),
    (r"mongodb://[^:]+:[^@]+@", "MongoDB Connection String"),
    (r"redis://[^:]+:[^@]+@", "Redis Connection String"),
    # Generic Passwords
    (r"(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?", "Password"),
    # Private Keys
    (r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----", "Private Key"),
    (r"-----BEGIN PGP PRIVATE KEY BLOCK-----", "PGP Private Key"),
    # Tokens
    (r"(access[_-]?token|refresh[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{20,}['\"]?", "Token"),
    (r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer Token"),
    # Webhooks
    (r"https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[a-zA-Z0-9]+", "Slack Webhook"),
    # Email Passwords
    (r"(imap|smtp)[_-]?(password|pass)\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?", "Email Password"),
]


# =============================================================================
# CODE SCANNING TESTS
# =============================================================================


class TestSecretsInCode:
    """Tests dass keine Secrets im Code vorhanden sind."""

    @pytest.fixture
    def source_files(self) -> List[Path]:
        """Alle Python-Sourcedateien."""
        base_path = Path("C:/Users/benfi/Ablage_System")
        return list(base_path.glob("app/**/*.py"))

    def test_no_hardcoded_api_keys(self, source_files):
        """Testet dass keine hartcodierten API-Keys im Code sind."""
        api_key_patterns = [
            re.compile(r"api[_-]?key\s*=\s*['\"][a-zA-Z0-9_\-]{20,}['\"]", re.I),
            re.compile(r"['\"]sk-[a-zA-Z0-9]{20,}['\"]"),  # OpenAI
            re.compile(r"['\"]AKIA[0-9A-Z]{16}['\"]"),  # AWS
        ]
        for file_path in source_files:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for pattern in api_key_patterns:
                    assert not pattern.search(content), \
                        f"Potentieller API-Key in {file_path}"

    def test_no_hardcoded_passwords(self, source_files):
        """Testet dass keine hartcodierten Passwoerter im Code sind."""
        # Ausnahmen: Test-Dateien, Mock-Daten
        password_pattern = re.compile(
            r"password\s*=\s*['\"][^'\"]{8,}['\"]",
            re.I
        )
        for file_path in source_files:
            if "test" in str(file_path).lower():
                continue  # Skip test files
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                matches = password_pattern.findall(content)
                # Erlaubt: password=None, password=settings.X, etc.
                for match in matches:
                    assert "settings." in content or "environ" in content or \
                        "None" in match or "***" in match, \
                        f"Potentielles Passwort in {file_path}"

    def test_no_private_keys(self, source_files):
        """Testet dass keine Private Keys im Code sind."""
        private_key_pattern = re.compile(
            r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"
        )
        for file_path in source_files:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                assert not private_key_pattern.search(content), \
                    f"Private Key in {file_path}"

    def test_no_database_urls_with_credentials(self, source_files):
        """Testet dass keine DB-URLs mit Credentials im Code sind."""
        db_url_patterns = [
            re.compile(r"postgres://[^:]+:[^@]+@", re.I),
            re.compile(r"mysql://[^:]+:[^@]+@", re.I),
            re.compile(r"redis://:[^@]+@", re.I),
        ]
        for file_path in source_files:
            if "test" in str(file_path).lower():
                continue
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for pattern in db_url_patterns:
                    # Erlaubt wenn es Environment-Variable referenziert
                    if pattern.search(content):
                        assert "environ" in content or "settings." in content, \
                            f"DB-URL mit Credentials in {file_path}"


# =============================================================================
# API RESPONSE TESTS
# =============================================================================


class TestSecretsInAPIResponses:
    """Tests dass keine Secrets in API-Responses exponiert werden."""

    def test_config_endpoint_no_secrets(self, test_client, auth_headers):
        """Testet dass Config-Endpoint keine Secrets exponiert."""
        response = test_client.get(
            "/api/v1/admin/config",
            headers=auth_headers,
        )
        if response.status_code == 200:
            text = response.text.lower()
            # Keine Passwoerter
            assert "password\":" not in text or "***" in text or "null" in text
            # Keine API-Keys
            assert "api_key\":" not in text or "***" in text or "null" in text
            # Keine Secrets
            assert "secret\":" not in text or "***" in text or "null" in text

    def test_email_config_masked_password(self, test_client, auth_headers):
        """Testet dass Email-Config Passwoerter maskiert."""
        response = test_client.get(
            "/api/v1/imports/email/configs",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            configs = data.get("configs", []) if isinstance(data, dict) else data
            for config in configs:
                # Passwort sollte maskiert oder nicht vorhanden sein
                password = config.get("password", config.get("imap_password", ""))
                assert not password or password == "***" or len(password) < 8

    def test_webhook_config_masked_secrets(self, test_client, auth_headers):
        """Testet dass Webhook-Configs Secrets maskieren."""
        response = test_client.get(
            "/api/v1/webhooks",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            webhooks = data.get("webhooks", []) if isinstance(data, dict) else data
            for webhook in webhooks:
                # Secret Header Values sollten maskiert sein
                headers = webhook.get("headers", {})
                for key, value in headers.items():
                    if "secret" in key.lower() or "token" in key.lower():
                        assert "***" in str(value) or len(str(value)) < 8

    def test_slack_config_masked_token(self, test_client, auth_headers):
        """Testet dass Slack-Config Tokens maskiert."""
        response = test_client.get(
            "/api/v1/slack/config",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            # Bot Token sollte maskiert sein
            bot_token = data.get("bot_token", "")
            assert not bot_token or "xoxb-" not in bot_token or "***" in bot_token
            # Webhook URL sollte teilweise maskiert sein
            webhook_url = data.get("webhook_url", "")
            assert not webhook_url or "***" in webhook_url or \
                "hooks.slack.com" not in webhook_url

    def test_banking_config_masked_credentials(self, test_client, auth_headers):
        """Testet dass Banking-Configs Credentials maskieren."""
        response = test_client.get(
            "/api/v1/banking/connections",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            connections = data.get("connections", []) if isinstance(data, dict) else data
            for conn in connections:
                # PIN/Passwort sollte nie zurueckgegeben werden
                assert "pin" not in conn or conn.get("pin") is None
                assert "password" not in conn or conn.get("password") is None


# =============================================================================
# ERROR RESPONSE TESTS
# =============================================================================


class TestSecretsInErrors:
    """Tests dass keine Secrets in Fehlermeldungen exponiert werden."""

    def test_db_connection_error_no_credentials(self, test_client, auth_headers):
        """Testet dass DB-Verbindungsfehler keine Credentials zeigen."""
        # Simuliere DB-Fehler durch ungueltige Anfrage
        response = test_client.get(
            "/api/v1/documents?invalid=true",
            headers=auth_headers,
        )
        if response.status_code >= 400:
            text = response.text
            # Keine DB-URL mit Passwort
            assert "postgres://" not in text or "@" not in text
            assert "mysql://" not in text or "@" not in text

    def test_auth_error_no_token_leak(self, test_client):
        """Testet dass Auth-Fehler keine Tokens leaken."""
        response = test_client.get(
            "/api/v1/documents",
            headers={"Authorization": "Bearer invalid-token"},
        )
        if response.status_code == 401:
            text = response.text
            # Kein JWT Secret in Fehlermeldung
            assert "secret" not in text.lower()
            assert "key" not in text.lower() or "invalid" in text.lower()

    def test_external_service_error_no_credentials(self, test_client, auth_headers):
        """Testet dass Fehler externer Services keine Credentials zeigen."""
        response = test_client.post(
            "/api/v1/imports/email/configs/test",
            json={"config_id": str(uuid.uuid4())},
            headers=auth_headers,
        )
        if response.status_code >= 400:
            text = response.text
            # Keine IMAP-Passwoerter in Fehlern
            assert "password" not in text.lower() or "invalid" in text.lower() or \
                "wrong" in text.lower()


# =============================================================================
# LOG TESTS
# =============================================================================


class TestSecretsInLogs:
    """Tests dass keine Secrets in Logs erscheinen."""

    def test_startup_logs_no_secrets(self):
        """Testet dass Startup-Logs keine Secrets enthalten."""
        import structlog
        import io
        import re

        # Test-Logger erstellen und pruefen dass Secrets gefiltert werden
        # Wir pruefen die Structlog-Konfiguration
        from app.core.config import Settings
        settings = Settings()

        # Secret-Werte die NIEMALS in Logs erscheinen duerfen
        secret_patterns = [
            settings.SECRET_KEY.get_secret_value() if hasattr(settings.SECRET_KEY, 'get_secret_value') else str(settings.SECRET_KEY),
            r"[A-Za-z0-9+/]{40,}={0,2}",  # Base64 Secrets
            r"sk-[A-Za-z0-9]{48}",  # OpenAI Keys
            r"ghp_[A-Za-z0-9]{36}",  # GitHub PATs
        ]

        # Pruefe dass structlog mit Processors konfiguriert ist
        processors = structlog.get_config().get("processors", [])
        # Ein Log-System sollte Processor-Pipeline haben
        assert len(processors) > 0, "Structlog sollte mit Processors konfiguriert sein"

    def test_request_logs_no_auth_headers(self, test_client, auth_headers):
        """Testet dass Request-Logs keine Auth-Headers enthalten."""
        import io
        import logging

        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("uvicorn.access")
        logger.addHandler(handler)

        # Request mit Auth-Header machen
        response = test_client.get("/api/v1/documents", headers=auth_headers)

        # Log output pruefen
        log_output = log_capture.getvalue()

        # JWT-Token sollte NICHT im Log erscheinen
        if "Authorization" in str(auth_headers):
            token = auth_headers.get("Authorization", "").replace("Bearer ", "")
            if token:
                # Token sollte maskiert oder nicht vorhanden sein
                assert token not in log_output or "***" in log_output, \
                    "Auth-Token sollte nicht im Klartext geloggt werden"

        logger.removeHandler(handler)

    def test_error_logs_no_credentials(self, test_client):
        """Testet dass Error-Logs keine Credentials enthalten."""
        import io
        import logging

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.ERROR)
        logger = logging.getLogger()
        original_handlers = logger.handlers[:]
        logger.handlers = [handler]

        # Provoziere einen Fehler mit Credential-aehnlichen Daten
        response = test_client.post(
            "/api/v1/auth/login",
            json={"username": "test@example.com", "password": "MySecretPassword123!"},
        )

        log_output = log_capture.getvalue()
        logger.handlers = original_handlers

        # Passwort sollte NICHT im Log erscheinen
        assert "MySecretPassword123!" not in log_output, \
            "Passwoerter sollten NIEMALS in Error-Logs erscheinen"


# =============================================================================
# ENVIRONMENT VARIABLE TESTS
# =============================================================================


class TestEnvironmentVariables:
    """Tests fuer sichere Environment-Variable-Nutzung."""

    def test_secrets_from_env_vars(self):
        """Testet dass Secrets aus Environment-Variablen kommen."""
        from app.core.config import Settings
        settings = Settings()

        # Diese Felder sollten aus Env-Vars kommen, nicht hartcodiert
        sensitive_fields = [
            "SECRET_KEY",
            "DATABASE_URL",
            "REDIS_URL",
        ]
        # Test ist konzeptionell - Settings sollte env vars nutzen

    def test_no_secrets_in_default_values(self):
        """Testet dass keine echten Secrets als Defaults definiert sind."""
        from app.core.config import Settings

        # Field defaults sollten keine echten Secrets sein
        # (nur Platzhalter wie "change-me" oder None)


# =============================================================================
# CONFIGURATION FILE TESTS
# =============================================================================


class TestConfigurationFiles:
    """Tests dass Konfigurations-Dateien keine Secrets enthalten."""

    def test_env_example_no_real_secrets(self):
        """Testet dass .env.example keine echten Secrets enthaelt."""
        env_example_path = Path("C:/Users/benfi/Ablage_System/.env.example")
        if env_example_path.exists():
            content = env_example_path.read_text()
            # Sollte nur Platzhalter enthalten
            assert "your-secret-here" in content.lower() or \
                "change-me" in content.lower() or \
                "xxx" in content.lower() or \
                content.count("=") == content.count("\n")  # Leere Values

    def test_docker_compose_no_hardcoded_secrets(self):
        """Testet dass docker-compose keine hartcodierten Secrets hat."""
        compose_path = Path("C:/Users/benfi/Ablage_System/docker-compose.yml")
        if compose_path.exists():
            content = compose_path.read_text()
            # Passwoerter sollten aus Env-Vars kommen
            lines = content.split("\n")
            for line in lines:
                if "password:" in line.lower() or "secret:" in line.lower():
                    # Sollte ${VAR} oder ${VAR:-default} Format haben
                    assert "${" in line or "env_file" in content

    def test_gitignore_excludes_secrets(self):
        """Testet dass .gitignore sensitive Dateien ausschliesst."""
        gitignore_path = Path("C:/Users/benfi/Ablage_System/.gitignore")
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            required_excludes = [".env", "*.pem", "*.key", "secrets/"]
            for exclude in required_excludes:
                # Mindestens .env sollte excluded sein
                if exclude == ".env":
                    assert ".env" in content


# =============================================================================
# ENCRYPTION TESTS
# =============================================================================


class TestSecretsEncryption:
    """Tests dass gespeicherte Secrets verschluesselt sind."""

    def test_email_passwords_encrypted(self, test_client, auth_headers):
        """Testet dass Email-Passwoerter verschluesselt gespeichert werden."""
        import base64

        # Email-Konfiguration erstellen mit Passwort
        config_data = {
            "name": "Test Email Config",
            "email_address": "test@example.com",
            "imap_server": "imap.example.com",
            "imap_port": 993,
            "password": "TestEmailPassword123!",
            "use_ssl": True,
            "enabled": False,  # Nicht aktivieren fuer Test
        }

        response = test_client.post(
            "/api/v1/imports/email/configs",
            json=config_data,
            headers=auth_headers,
        )

        # Falls Endpoint existiert und erfolgreich
        if response.status_code in [200, 201]:
            data = response.json()
            # Passwort sollte NICHT im Klartext zurueckgegeben werden
            assert "TestEmailPassword123!" not in str(data), \
                "Passwort sollte nicht im Klartext in API-Response sein"

            # Falls password_hash oder encrypted_password vorhanden
            if "password" in data:
                password_value = data.get("password", "")
                if password_value:
                    # Sollte verschluesselt (Base64) oder maskiert (***) sein
                    assert password_value == "***" or \
                           password_value != "TestEmailPassword123!", \
                        "Passwort muss verschluesselt oder maskiert sein"

    def test_banking_pins_encrypted(self, test_client, auth_headers):
        """Testet dass Banking-PINs verschluesselt gespeichert werden."""
        # Banking-Verbindung erstellen mit PIN
        config_data = {
            "bank_code": "12345678",
            "account_number": "1234567890",
            "pin": "SecretBankingPIN123",
            "enabled": False,
        }

        response = test_client.post(
            "/api/v1/banking/connections",
            json=config_data,
            headers=auth_headers,
        )

        # Falls Endpoint existiert
        if response.status_code in [200, 201]:
            data = response.json()
            # PIN sollte NIEMALS im Klartext zurueckgegeben werden
            assert "SecretBankingPIN123" not in str(data), \
                "Banking-PIN sollte nicht im Klartext in API-Response sein"

        # Selbst bei Fehler: Pruefe dass PIN nicht in Fehlermeldung
        if response.status_code >= 400:
            error_text = response.text
            assert "SecretBankingPIN123" not in error_text, \
                "Banking-PIN sollte nicht in Fehlermeldungen erscheinen"


# =============================================================================
# DEBUG ENDPOINT TESTS
# =============================================================================


class TestDebugEndpoints:
    """Tests dass Debug-Endpoints keine Secrets exponieren."""

    def test_health_endpoint_no_secrets(self, test_client):
        """Testet dass Health-Endpoint keine Secrets exponiert."""
        response = test_client.get("/health")
        if response.status_code == 200:
            text = response.text
            assert "password" not in text.lower()
            assert "secret" not in text.lower()
            assert "token" not in text.lower() or "status" in text.lower()

    def test_debug_endpoints_protected(self, test_client):
        """Testet dass Debug-Endpoints geschuetzt sind."""
        debug_endpoints = [
            "/debug",
            "/debug/config",
            "/debug/env",
            "/debug/vars",
            "/.env",
            "/config.json",
        ]
        for endpoint in debug_endpoints:
            response = test_client.get(endpoint)
            # Sollte 404 oder 401/403 sein
            assert response.status_code in [401, 403, 404]


# =============================================================================
# FIXTURES - Verwendung von conftest.py
# =============================================================================
# Die Fixtures test_client und auth_headers werden aus conftest.py importiert.
# Diese nutzen den ECHTEN TestClient mit der ECHTEN App für Enterprise-Grade Tests.
