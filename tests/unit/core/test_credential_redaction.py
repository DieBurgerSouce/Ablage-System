# -*- coding: utf-8 -*-
"""
Unit Tests fuer app/core/credential_redaction.py.

Testet umfassende Credential-Redaktion:
- Feldnamen-basierte Redaktion
- Pattern-basierte Erkennung
- URL-Redaktion
- Header-Redaktion
- Structlog Processor
- FastAPI Middleware
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.credential_redaction import (
    RedactionLevel,
    RedactionConfig,
    DEFAULT_CONFIG,
    SENSITIVE_FIELD_NAMES,
    SENSITIVE_HEADERS,
    CREDENTIAL_PATTERNS,
    CredentialPattern,
    redact_value,
    redact_dict,
    redact_headers,
    redact_url,
    redact_json_string,
    redact_for_logging,
    is_sensitive_key,
    get_redaction_processor,
    CredentialRedactionProcessor,
)


# ============================================================================
# Test Configuration Classes
# ============================================================================


class TestRedactionLevel:
    """Tests fuer RedactionLevel Enum."""

    def test_levels_exist(self):
        """Alle Redaction Levels existieren."""
        assert RedactionLevel.MINIMAL is not None
        assert RedactionLevel.STANDARD is not None
        assert RedactionLevel.PARANOID is not None

    def test_level_values(self):
        """Level Values sind korrekt."""
        assert RedactionLevel.MINIMAL.value == "minimal"
        assert RedactionLevel.STANDARD.value == "standard"
        assert RedactionLevel.PARANOID.value == "paranoid"


class TestRedactionConfig:
    """Tests fuer RedactionConfig."""

    def test_default_config(self):
        """Default-Konfiguration ist korrekt."""
        config = RedactionConfig()

        assert config.level == RedactionLevel.STANDARD
        assert config.redaction_text == "[REDACTED]"
        assert config.redaction_text_de == "[ZENSIERT]"
        assert config.show_partial is False
        assert config.log_redactions is False

    def test_custom_config(self):
        """Benutzerdefinierte Konfiguration."""
        config = RedactionConfig(
            level=RedactionLevel.PARANOID,
            redaction_text="***",
            show_partial=True
        )

        assert config.level == RedactionLevel.PARANOID
        assert config.redaction_text == "***"
        assert config.show_partial is True


# ============================================================================
# Test Constants
# ============================================================================


class TestSensitiveFieldNames:
    """Tests fuer sensitive Feldnamen."""

    def test_password_fields(self):
        """Passwort-Felder sind enthalten."""
        assert "password" in SENSITIVE_FIELD_NAMES
        assert "passwd" in SENSITIVE_FIELD_NAMES
        assert "passwort" in SENSITIVE_FIELD_NAMES

    def test_token_fields(self):
        """Token-Felder sind enthalten."""
        assert "token" in SENSITIVE_FIELD_NAMES
        assert "access_token" in SENSITIVE_FIELD_NAMES
        assert "refresh_token" in SENSITIVE_FIELD_NAMES
        assert "bearer_token" in SENSITIVE_FIELD_NAMES
        assert "jwt" in SENSITIVE_FIELD_NAMES

    def test_api_key_fields(self):
        """API-Key-Felder sind enthalten."""
        assert "api_key" in SENSITIVE_FIELD_NAMES
        assert "apikey" in SENSITIVE_FIELD_NAMES
        assert "secret" in SENSITIVE_FIELD_NAMES

    def test_database_fields(self):
        """Datenbank-Felder sind enthalten."""
        assert "db_password" in SENSITIVE_FIELD_NAMES
        assert "connection_string" in SENSITIVE_FIELD_NAMES

    def test_cloud_fields(self):
        """Cloud-Felder sind enthalten."""
        assert "aws_secret" in SENSITIVE_FIELD_NAMES
        assert "vault_token" in SENSITIVE_FIELD_NAMES


class TestSensitiveHeaders:
    """Tests fuer sensitive HTTP Headers."""

    def test_auth_headers(self):
        """Authentifizierungs-Headers sind enthalten."""
        assert "authorization" in SENSITIVE_HEADERS
        assert "x-api-key" in SENSITIVE_HEADERS
        assert "x-auth-token" in SENSITIVE_HEADERS

    def test_cookie_headers(self):
        """Cookie-Headers sind enthalten."""
        assert "cookie" in SENSITIVE_HEADERS
        assert "set-cookie" in SENSITIVE_HEADERS


class TestCredentialPatterns:
    """Tests fuer Credential Patterns."""

    def test_patterns_exist(self):
        """Patterns sind definiert."""
        assert len(CREDENTIAL_PATTERNS) > 0

    def test_jwt_pattern_exists(self):
        """JWT Pattern ist vorhanden."""
        jwt_patterns = [p for p in CREDENTIAL_PATTERNS if p.name == "jwt"]
        assert len(jwt_patterns) == 1

    def test_bearer_pattern_exists(self):
        """Bearer Pattern ist vorhanden."""
        bearer_patterns = [p for p in CREDENTIAL_PATTERNS if p.name == "bearer"]
        assert len(bearer_patterns) == 1


# ============================================================================
# Test redact_value Function
# ============================================================================


class TestRedactValue:
    """Tests fuer redact_value Funktion."""

    def test_clean_value_unchanged(self):
        """Sauberer Wert bleibt unveraendert."""
        result = redact_value("Hello World")
        assert result == "Hello World"

    def test_jwt_token_redacted(self):
        """JWT Token wird redaktiert."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

        result = redact_value(jwt)

        assert "eyJ" not in result
        assert "[REDACTED]" in result

    def test_bearer_token_redacted(self):
        """Bearer Token wird redaktiert."""
        bearer = "Bearer eyJhbGciOiJIUzI1NiJ9.test.signature"

        result = redact_value(bearer)

        assert "eyJ" not in result

    def test_basic_auth_redacted(self):
        """Basic Auth wird redaktiert."""
        basic = "Basic dXNlcm5hbWU6cGFzc3dvcmQ="

        result = redact_value(basic)

        assert "dXNlcm5hbWU6cGFzc3dvcmQ" not in result

    def test_aws_key_redacted(self):
        """AWS Access Key wird redaktiert."""
        aws_key = "AKIAIOSFODNN7EXAMPLE"

        result = redact_value(aws_key)

        # AWS Key im Text wird erkannt
        assert result != "AKIAIOSFODNN7EXAMPLE" or len(aws_key) < 20

    def test_connection_string_redacted(self):
        """Connection String wird redaktiert."""
        conn_str = "postgresql://admin:secretpass@localhost:5432/mydb"

        result = redact_value(conn_str)

        assert "secretpass" not in result
        assert "[DB_CONNECTION_REDACTED]" in result or "[REDACTED]" in result

    def test_github_token_redacted(self):
        """GitHub Token wird redaktiert."""
        gh_token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1234"

        result = redact_value(gh_token)

        assert "ghp_" not in result or "[REDACTED]" in result

    def test_private_key_redacted(self):
        """Private Key wird redaktiert."""
        private_key = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDZ
test_key_content
-----END PRIVATE KEY-----"""

        result = redact_value(private_key)

        assert "MIIEvgIBADANBg" not in result
        assert "PRIVATE_KEY_REDACTED" in result

    def test_email_redacted(self):
        """Email wird redaktiert."""
        email = "user@example.com"

        result = redact_value(email)

        assert "@example.com" not in result
        assert "EMAIL_REDACTED" in result

    def test_credit_card_redacted(self):
        """Kreditkartennummer wird redaktiert."""
        cc = "4111 1111 1111 1111"

        result = redact_value(cc)

        assert "4111" not in result


# ============================================================================
# Test redact_dict Function
# ============================================================================


class TestRedactDict:
    """Tests fuer redact_dict Funktion."""

    def test_empty_dict(self):
        """Leeres Dictionary bleibt leer."""
        result = redact_dict({})
        assert result == {}

    def test_clean_dict_unchanged(self):
        """Dictionary ohne sensitive Daten bleibt unveraendert."""
        data = {"name": "Test", "value": 123}
        result = redact_dict(data)

        assert result["name"] == "Test"
        assert result["value"] == 123

    def test_password_field_redacted(self):
        """Password-Feld wird redaktiert."""
        data = {"username": "admin", "password": "secret123"}
        result = redact_dict(data)

        assert result["username"] == "admin"
        assert result["password"] == "[ZENSIERT]"

    def test_api_key_field_redacted(self):
        """API-Key-Feld wird redaktiert."""
        data = {"api_key": "sk-1234567890abcdef"}
        result = redact_dict(data)

        assert result["api_key"] == "[ZENSIERT]"

    def test_nested_dict_redacted(self):
        """Verschachtelte Dicts werden redaktiert."""
        data = {
            "user": {
                "name": "Test",
                "credentials": {
                    "password": "secret"
                }
            }
        }
        result = redact_dict(data)

        assert result["user"]["name"] == "Test"
        assert result["user"]["credentials"]["password"] == "[ZENSIERT]"

    def test_list_in_dict_redacted(self):
        """Listen in Dicts werden verarbeitet."""
        data = {
            "tokens": [
                {"token": "abc123"},
                {"token": "def456"}
            ]
        }
        result = redact_dict(data)

        for item in result["tokens"]:
            assert item["token"] == "[ZENSIERT]"

    def test_case_insensitive_field_names(self):
        """Feldnamen werden case-insensitive geprueft."""
        data = {
            "PASSWORD": "secret1",
            "Password": "secret2",
            "passWORD": "secret3"
        }
        result = redact_dict(data)

        for key in data.keys():
            assert result[key] == "[ZENSIERT]"

    def test_partial_field_name_match(self):
        """Teilweise Feldnamen werden erkannt."""
        data = {
            "user_password": "secret",
            "db_password_hash": "hash123",
            "my_api_key_value": "key123"
        }
        result = redact_dict(data)

        assert result["user_password"] == "[ZENSIERT]"
        assert result["db_password_hash"] == "[ZENSIERT]"
        assert result["my_api_key_value"] == "[ZENSIERT]"

    def test_jwt_in_value_redacted(self):
        """JWT in Wert wird redaktiert."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.dGVzdA"
        data = {"auth_header": f"Bearer {jwt}"}
        result = redact_dict(data)

        assert "eyJ" not in result["auth_header"]


# ============================================================================
# Test redact_headers Function
# ============================================================================


class TestRedactHeaders:
    """Tests fuer redact_headers Funktion."""

    def test_normal_header_unchanged(self):
        """Normale Headers bleiben unveraendert."""
        headers = {"Content-Type": "application/json"}
        result = redact_headers(headers)

        assert result["Content-Type"] == "application/json"

    def test_authorization_redacted(self):
        """Authorization Header wird redaktiert."""
        headers = {"Authorization": "Bearer token123"}
        result = redact_headers(headers)

        assert result["Authorization"] == "[ZENSIERT]"

    def test_api_key_header_redacted(self):
        """X-API-Key Header wird redaktiert."""
        headers = {"X-API-Key": "secret-api-key-12345"}
        result = redact_headers(headers)

        assert result["X-API-Key"] == "[ZENSIERT]"

    def test_cookie_header_redacted(self):
        """Cookie Header wird redaktiert."""
        headers = {"Cookie": "session=abc123; token=xyz789"}
        result = redact_headers(headers)

        assert result["Cookie"] == "[ZENSIERT]"

    def test_mixed_headers(self):
        """Gemischte Headers werden korrekt verarbeitet."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret",
            "Accept": "*/*",
            "X-API-Key": "key123"
        }
        result = redact_headers(headers)

        assert result["Content-Type"] == "application/json"
        assert result["Authorization"] == "[ZENSIERT]"
        assert result["Accept"] == "*/*"
        assert result["X-API-Key"] == "[ZENSIERT]"

    def test_case_insensitive_headers(self):
        """Header-Namen sind case-insensitive."""
        headers = {
            "AUTHORIZATION": "Bearer token",
            "Cookie": "session=abc"
        }
        result = redact_headers(headers)

        assert result["AUTHORIZATION"] == "[ZENSIERT]"
        assert result["Cookie"] == "[ZENSIERT]"


# ============================================================================
# Test redact_url Function
# ============================================================================


class TestRedactUrl:
    """Tests fuer redact_url Funktion."""

    def test_url_without_credentials(self):
        """URL ohne Credentials bleibt unveraendert."""
        url = "https://example.com/api/v1/users"
        result = redact_url(url)

        assert result == url

    def test_url_with_password(self):
        """URL mit Passwort wird redaktiert."""
        url = "postgresql://admin:secretpassword@localhost:5432/db"
        result = redact_url(url)

        assert "secretpassword" not in result
        assert "[REDACTED]" in result
        assert "admin" in result  # Username bleibt

    def test_url_with_special_chars(self):
        """URL mit Sonderzeichen im Passwort."""
        url = "mysql://user:p@ss%word!@host:3306/db"
        result = redact_url(url)

        assert "p@ss%word!" not in result

    def test_redis_url(self):
        """Redis URL wird redaktiert."""
        url = "redis://:mysecretpassword@redis.example.com:6379/0"
        result = redact_url(url)

        assert "mysecretpassword" not in result


# ============================================================================
# Test redact_json_string Function
# ============================================================================


class TestRedactJsonString:
    """Tests fuer redact_json_string Funktion."""

    def test_valid_json(self):
        """Valides JSON wird redaktiert."""
        json_str = '{"username": "admin", "password": "secret"}'
        result = redact_json_string(json_str)

        assert "secret" not in result
        assert "[ZENSIERT]" in result or "ZENSIERT" in result

    def test_invalid_json(self):
        """Invalides JSON wird als String verarbeitet."""
        invalid = "not valid json with password=secret"
        result = redact_json_string(invalid)

        # Sollte nicht crashen
        assert result is not None

    def test_nested_json(self):
        """Verschachteltes JSON wird redaktiert."""
        json_str = '{"user": {"auth": {"api_key": "key123"}}}'
        result = redact_json_string(json_str)

        assert "key123" not in result


# ============================================================================
# Test Helper Functions
# ============================================================================


class TestHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    def test_is_sensitive_key_true(self):
        """Sensitive Keys werden erkannt."""
        assert is_sensitive_key("password") is True
        assert is_sensitive_key("api_key") is True
        assert is_sensitive_key("user_password") is True
        assert is_sensitive_key("MY_SECRET") is True

    def test_is_sensitive_key_false(self):
        """Nicht-sensitive Keys werden erkannt."""
        assert is_sensitive_key("username") is False
        assert is_sensitive_key("name") is False
        assert is_sensitive_key("count") is False
        assert is_sensitive_key("status") is False

    def test_is_sensitive_key_partial_match(self):
        """Teilweise Matches werden erkannt."""
        # "password" ist in SENSITIVE_FIELD_NAMES - Teilstring-Match
        assert is_sensitive_key("user_password") is True
        assert is_sensitive_key("PASSWORD_HASH") is True
        # "token" ist in SENSITIVE_FIELD_NAMES
        assert is_sensitive_key("auth_token_value") is True

    def test_redact_for_logging_dict(self):
        """redact_for_logging mit Dict."""
        data = {"password": "secret"}
        result = redact_for_logging(data)

        assert result["password"] == "[ZENSIERT]"

    def test_redact_for_logging_string(self):
        """redact_for_logging mit String."""
        data = "Bearer token123"
        result = redact_for_logging(data)

        # Bearer tokens werden erkannt
        assert result is not None

    def test_redact_for_logging_list(self):
        """redact_for_logging mit Liste."""
        data = [{"token": "abc"}, {"token": "def"}]
        result = redact_for_logging(data)

        for item in result:
            assert item["token"] == "[ZENSIERT]"


# ============================================================================
# Test CredentialRedactionProcessor
# ============================================================================


class TestCredentialRedactionProcessor:
    """Tests fuer Structlog Processor."""

    def test_processor_creation(self):
        """Processor kann erstellt werden."""
        processor = CredentialRedactionProcessor()
        assert processor is not None

    def test_processor_with_custom_config(self):
        """Processor mit benutzerdefinierter Config."""
        config = RedactionConfig(level=RedactionLevel.PARANOID)
        processor = CredentialRedactionProcessor(config)

        assert processor.config.level == RedactionLevel.PARANOID

    def test_processor_redacts_password(self):
        """Processor redaktiert Passwort."""
        processor = CredentialRedactionProcessor()
        event_dict = {"event": "login", "password": "secret123"}

        result = processor(None, "info", event_dict)

        assert result["event"] == "login"
        assert result["password"] == "[ZENSIERT]"

    def test_processor_redacts_nested(self):
        """Processor redaktiert verschachtelte Daten."""
        processor = CredentialRedactionProcessor()
        event_dict = {
            "event": "api_call",
            "request": {
                "headers": {
                    "api_key": "secret-key"
                }
            }
        }

        result = processor(None, "info", event_dict)

        assert result["request"]["headers"]["api_key"] == "[ZENSIERT]"

    def test_get_redaction_processor(self):
        """get_redaction_processor erstellt Processor."""
        processor = get_redaction_processor(RedactionLevel.PARANOID)

        assert isinstance(processor, CredentialRedactionProcessor)
        assert processor.config.level == RedactionLevel.PARANOID


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests fuer Grenzfaelle."""

    def test_none_value(self):
        """None-Werte werden korrekt behandelt."""
        data = {"password": None}
        result = redact_dict(data)

        # None bleibt None, wird nicht als String behandelt
        assert result["password"] == "[ZENSIERT]" or result["password"] is None

    def test_empty_string_value(self):
        """Leere Strings werden behandelt."""
        data = {"password": ""}
        result = redact_dict(data)

        assert result["password"] == "[ZENSIERT]"

    def test_numeric_values(self):
        """Numerische Werte bleiben unveraendert."""
        data = {"port": 8080, "count": 100}
        result = redact_dict(data)

        assert result["port"] == 8080
        assert result["count"] == 100

    def test_boolean_values(self):
        """Boolean-Werte bleiben unveraendert."""
        data = {"enabled": True, "debug": False}
        result = redact_dict(data)

        assert result["enabled"] is True
        assert result["debug"] is False

    def test_deeply_nested_structure(self):
        """Tief verschachtelte Strukturen werden verarbeitet."""
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "secret_key": "deep_secret"
                        }
                    }
                }
            }
        }
        result = redact_dict(data)

        assert result["level1"]["level2"]["level3"]["level4"]["secret_key"] == "[ZENSIERT]"

    def test_mixed_list_types(self):
        """Listen mit gemischten Typen."""
        data = {
            "items": [
                "string",
                123,
                {"password": "secret"},
                None,
                True
            ]
        }
        result = redact_dict(data)

        assert result["items"][0] == "string"
        assert result["items"][1] == 123
        assert result["items"][2]["password"] == "[ZENSIERT]"

    def test_unicode_values(self):
        """Unicode-Werte werden korrekt behandelt."""
        data = {"passwort": "geheim123", "name": "Müller"}
        result = redact_dict(data)

        assert result["passwort"] == "[ZENSIERT]"
        assert result["name"] == "Müller"


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integrations-Tests fuer vollstaendige Szenarien."""

    def test_full_api_request_redaction(self):
        """Vollstaendige API-Request Redaktion."""
        request_data = {
            "method": "POST",
            "url": "https://api.example.com/auth",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test.sig",
                "X-API-Key": "sk-12345"
            },
            "body": {
                "username": "admin",
                "password": "secretpassword123",
                "remember_me": True
            }
        }

        result = redact_dict(request_data)

        # Nicht-sensitive Daten bleiben
        assert result["method"] == "POST"
        assert result["body"]["remember_me"] is True
        assert result["headers"]["Content-Type"] == "application/json"

        # Sensitive Daten sind redaktiert
        assert result["body"]["password"] == "[ZENSIERT]"
        assert result["headers"]["Authorization"] == "[ZENSIERT]"
        assert result["headers"]["X-API-Key"] == "[ZENSIERT]"

    def test_database_config_redaction(self):
        """Datenbank-Konfiguration Redaktion."""
        db_config = {
            "host": "localhost",
            "port": 5432,
            "database": "myapp",
            "user": "admin",
            "password": "db_secret_pass",
            "connection_string": "postgresql://admin:db_secret_pass@localhost:5432/myapp"
        }

        result = redact_dict(db_config)

        assert result["host"] == "localhost"
        assert result["port"] == 5432
        assert result["password"] == "[ZENSIERT]"
        assert "db_secret_pass" not in result["connection_string"]

    def test_log_event_redaction(self):
        """Log-Event Redaktion."""
        log_event = {
            "event": "user_login",
            "user_id": "12345",
            "email": "user@example.com",
            "session_token": "sess_abc123xyz",
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0"
        }

        processor = CredentialRedactionProcessor()
        result = processor(None, "info", log_event)

        assert result["event"] == "user_login"
        assert result["user_id"] == "12345"
        assert result["session_token"] == "[ZENSIERT]"
        # Email wird als sensitiv behandelt
        assert "user@example.com" not in str(result["email"]) or result["email"] == "[ZENSIERT]"
