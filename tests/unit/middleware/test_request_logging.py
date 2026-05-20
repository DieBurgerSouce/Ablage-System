# -*- coding: utf-8 -*-
"""
Unit Tests fuer Request Logging Middleware.

Testet:
- PII-Filterung (Dict und Text)
- Redaction/Masking/Truncation
- Request-Info-Sammlung
- Response-Info-Sammlung
- Pfad-Ausschluss
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.request_logging import (
    PIIFilterConfig,
    redact_value,
    mask_value,
    truncate_value,
    filter_pii_from_dict,
    filter_pii_from_text,
    truncate_body,
    RequestLoggingMiddleware,
    get_request_logging_stats,
)


class TestPIIFilterConfig:
    """Tests fuer PIIFilterConfig."""

    def test_redacted_fields_defined(self):
        """Redacted-Felder sind definiert."""
        assert "password" in PIIFilterConfig.REDACTED_FIELDS
        assert "token" in PIIFilterConfig.REDACTED_FIELDS
        assert "api_key" in PIIFilterConfig.REDACTED_FIELDS

    def test_masked_fields_defined(self):
        """Masked-Felder sind definiert."""
        assert "email" in PIIFilterConfig.MASKED_FIELDS
        assert "iban" in PIIFilterConfig.MASKED_FIELDS
        assert "phone" in PIIFilterConfig.MASKED_FIELDS

    def test_truncated_fields_defined(self):
        """Truncated-Felder sind definiert."""
        assert "name" in PIIFilterConfig.TRUNCATED_FIELDS
        assert "username" in PIIFilterConfig.TRUNCATED_FIELDS
        assert "address" in PIIFilterConfig.TRUNCATED_FIELDS

    def test_sensitive_patterns_defined(self):
        """Sensitive-Patterns sind definiert."""
        assert len(PIIFilterConfig.SENSITIVE_PATTERNS) > 0

    def test_excluded_paths_defined(self):
        """Excluded-Paths sind definiert."""
        assert "/health" in PIIFilterConfig.EXCLUDED_PATHS
        assert "/metrics" in PIIFilterConfig.EXCLUDED_PATHS


class TestRedactValue:
    """Tests fuer redact_value()."""

    def test_redacts_string(self):
        """Strings werden redacted."""
        assert redact_value("secret123") == "[REDACTED]"

    def test_redacts_any_value(self):
        """Beliebige Werte werden redacted."""
        assert redact_value(12345) == "[REDACTED]"
        assert redact_value(None) == "[REDACTED]"


class TestMaskValue:
    """Tests fuer mask_value()."""

    def test_masks_long_string(self):
        """Lange Strings zeigen letzte 4 Zeichen."""
        assert mask_value("test@example.com") == "***.com"

    def test_masks_short_string(self):
        """Kurze Strings werden komplett maskiert."""
        assert mask_value("abc") == "[MASKED]"

    def test_masks_non_string(self):
        """Non-Strings werden konvertiert und maskiert."""
        result = mask_value(12345678)
        assert result.endswith("5678")


class TestTruncateValue:
    """Tests fuer truncate_value()."""

    def test_truncates_long_string(self):
        """Lange Strings zeigen erste 3 Zeichen."""
        assert truncate_value("Johannes") == "Joh***"

    def test_truncates_short_string(self):
        """Kurze Strings bleiben mit ***."""
        assert truncate_value("Jo") == "Jo***"

    def test_truncates_non_string(self):
        """Non-Strings werden konvertiert und gekuerzt."""
        result = truncate_value(123456)
        assert result.startswith("123")


class TestFilterPIIFromDict:
    """Tests fuer filter_pii_from_dict()."""

    def test_redacts_password(self):
        """Passwoerter werden redacted."""
        data = {"user_id": "test123", "password": "secret123"}
        result = filter_pii_from_dict(data)
        assert result["password"] == "[REDACTED]"
        assert result["user_id"] == "test123"  # user_id wird nicht gefiltert

    def test_masks_email(self):
        """Emails werden maskiert."""
        data = {"email": "test@example.com"}
        result = filter_pii_from_dict(data)
        assert "***" in result["email"]

    def test_truncates_name(self):
        """Namen werden gekuerzt."""
        data = {"firstname": "Johannes"}
        result = filter_pii_from_dict(data)
        assert result["firstname"].startswith("Joh")
        assert "***" in result["firstname"]

    def test_handles_nested_dict(self):
        """Verschachtelte Dicts werden gefiltert."""
        data = {
            "user": {
                "password": "secret",
                "email": "test@example.com"
            }
        }
        result = filter_pii_from_dict(data)
        assert result["user"]["password"] == "[REDACTED]"
        assert "***" in result["user"]["email"]

    def test_handles_list(self):
        """Listen werden gefiltert."""
        data = {
            "users": [
                {"password": "secret1"},
                {"password": "secret2"}
            ]
        }
        result = filter_pii_from_dict(data)
        assert result["users"][0]["password"] == "[REDACTED]"
        assert result["users"][1]["password"] == "[REDACTED]"

    def test_limits_list_items(self):
        """Listen werden auf 10 Items begrenzt."""
        data = {"items": [{"id": i} for i in range(20)]}
        result = filter_pii_from_dict(data)
        # 10 Items + "... und X weitere"
        assert len(result["items"]) == 11
        assert "weitere" in result["items"][-1]

    def test_max_depth_protection(self):
        """Max-Depth wird eingehalten."""
        # Sehr tiefe Verschachtelung
        deep_data = {"level1": {"level2": {"level3": {"level4": {"level5": {"level6": {}}}}}}}
        result = filter_pii_from_dict(deep_data, depth=4)
        assert "_truncated" in result["level1"]["level2"]

    def test_partial_field_match(self):
        """Partielle Feldnamen werden erkannt."""
        data = {"user_password_hash": "secret", "my_email_address": "test@example.com"}
        result = filter_pii_from_dict(data)
        assert result["user_password_hash"] == "[REDACTED]"
        assert "***" in result["my_email_address"]


class TestFilterPIIFromText:
    """Tests fuer filter_pii_from_text()."""

    def test_filters_email(self):
        """Emails werden gefiltert."""
        text = "Kontakt: test@example.com"
        result = filter_pii_from_text(text)
        assert "test@example.com" not in result
        assert "[EMAIL-REDACTED]" in result

    def test_filters_german_iban(self):
        """Deutsche IBANs werden gefiltert."""
        text = "IBAN: DE89370400440532013000"
        result = filter_pii_from_text(text)
        assert "DE89370400440532013000" not in result

    def test_filters_phone(self):
        """Telefonnummern werden gefiltert."""
        text = "Tel: +49 171 12345678"
        result = filter_pii_from_text(text)
        assert "12345678" not in result

    def test_filters_credit_card(self):
        """Kreditkartennummern werden gefiltert."""
        text = "Card: 4111-1111-1111-1111"
        result = filter_pii_from_text(text)
        assert "4111" not in result

    def test_filters_jwt(self):
        """JWT-Tokens werden gefiltert."""
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = filter_pii_from_text(text)
        assert "eyJ" not in result
        assert "[JWT-REDACTED]" in result

    def test_preserves_normal_text(self):
        """Normaler Text bleibt erhalten."""
        text = "Dies ist ein normaler deutscher Text."
        result = filter_pii_from_text(text)
        assert result == text


class TestTruncateBody:
    """Tests fuer truncate_body()."""

    def test_short_body_unchanged(self):
        """Kurze Bodies bleiben unveraendert."""
        body = "Short body"
        result = truncate_body(body, max_length=100)
        assert result == body

    def test_long_body_truncated(self):
        """Lange Bodies werden gekuerzt."""
        body = "a" * 3000
        result = truncate_body(body, max_length=100)
        assert len(result) < len(body)
        assert "truncated" in result

    def test_includes_total_length(self):
        """Truncated-Nachricht enthaelt Gesamtlaenge."""
        body = "a" * 3000
        result = truncate_body(body, max_length=100)
        assert "3000 bytes" in result


class TestRequestLoggingMiddleware:
    """Tests fuer RequestLoggingMiddleware."""

    def test_initialization(self):
        """Middleware initialisiert korrekt."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(
            app,
            log_request_body=True,
            log_response_body=False,
            log_headers=True
        )
        assert middleware.log_request_body is True
        assert middleware.log_response_body is False
        assert middleware.log_headers is True

    def test_default_excluded_paths(self):
        """Standard-Excluded-Paths werden geladen."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)
        assert "/health" in middleware.excluded_paths
        assert "/metrics" in middleware.excluded_paths

    def test_custom_excluded_paths(self):
        """Custom-Excluded-Paths werden akzeptiert."""
        app = MagicMock()
        custom_paths = {"/custom", "/internal"}
        middleware = RequestLoggingMiddleware(app, excluded_paths=custom_paths)
        assert "/custom" in middleware.excluded_paths
        assert "/internal" in middleware.excluded_paths


class TestRequestLoggingMiddlewareDispatch:
    """Tests fuer RequestLoggingMiddleware.dispatch()."""

    @pytest.mark.asyncio
    async def test_skips_excluded_path(self):
        """Excluded-Paths werden uebersprungen."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"

        mock_response = MagicMock(spec=Response)
        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)

        assert result == mock_response
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    @patch('app.middleware.request_logging.logger')
    async def test_logs_request(self, mock_logger):
        """Requests werden geloggt."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app, log_request_body=False)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/documents"
        mock_request.method = "GET"
        mock_request.query_params = {}
        mock_request.headers = {"user-agent": "test-agent"}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.state = MagicMock()
        mock_request.state.request_id = None

        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json", "content-length": "100"}

        mock_call_next = AsyncMock(return_value=mock_response)

        await middleware.dispatch(mock_request, mock_call_next)

        # Sollte mindestens einmal geloggt haben
        assert mock_logger.info.called


class TestRequestLoggingMiddlewareClientIP:
    """Tests fuer Client-IP-Ermittlung."""

    def test_gets_direct_client_ip(self):
        """Direkte Client-IP wird ermittelt."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"

        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_gets_forwarded_for_ip(self):
        """X-Forwarded-For IP wird ermittelt."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        mock_request.client = None

        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"

    def test_gets_real_ip(self):
        """X-Real-IP wird ermittelt."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.headers = {"x-real-ip": "172.16.0.1"}
        mock_request.client = None

        ip = middleware._get_client_ip(mock_request)
        assert ip == "172.16.0.1"

    def test_returns_unknown_when_no_ip(self):
        """Gibt 'unknown' zurueck wenn keine IP."""
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client = None

        ip = middleware._get_client_ip(mock_request)
        assert ip == "unknown"


class TestGetRequestLoggingStats:
    """Tests fuer get_request_logging_stats()."""

    def test_returns_stats(self):
        """Gibt Statistiken zurueck."""
        stats = get_request_logging_stats()

        assert "pii_redacted_fields" in stats
        assert "pii_masked_fields" in stats
        assert "pii_truncated_fields" in stats
        assert "sensitive_patterns" in stats
        assert "max_body_log_length" in stats
        assert "excluded_paths" in stats

    def test_stats_have_correct_types(self):
        """Statistiken haben korrekte Typen."""
        stats = get_request_logging_stats()

        assert isinstance(stats["pii_redacted_fields"], int)
        assert isinstance(stats["pii_masked_fields"], int)
        assert isinstance(stats["excluded_paths"], list)
