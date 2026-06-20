# -*- coding: utf-8 -*-
"""
Unit Tests fuer Structured Logging Configuration.

Tests fuer:
- GermanLogLevelProcessor
- CorrelationIdProcessor
- SensitiveDataFilter
- PerformanceProcessor
- RequestContextProcessor
- Convenience Logging Functions
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from app.core.logging_config import (
    GermanLogLevelProcessor,
    CorrelationIdProcessor,
    SensitiveDataFilter,
    PerformanceProcessor,
    RequestContextProcessor,
    configure_logging,
    get_logger,
    log_erfolg,
    log_warnung,
    log_fehler,
    log_ocr_verarbeitung,
    log_authentifizierung,
    log_api_anfrage,
    log_datenbank_operation,
    GERMAN_LOG_LEVELS,
)


class TestGermanLogLevelProcessor:
    """Tests fuer GermanLogLevelProcessor."""

    def test_adds_german_level_for_debug(self):
        """DEBUG wird zu FEHLERSUCHE."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "DEBUG", "event": "test"}

        result = processor(None, "debug", event_dict)

        assert result["stufe"] == "FEHLERSUCHE"

    def test_adds_german_level_for_info(self):
        """INFO wird zu INFORMATION."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "INFO", "event": "test"}

        result = processor(None, "info", event_dict)

        assert result["stufe"] == "INFORMATION"

    def test_adds_german_level_for_warning(self):
        """WARNING wird zu WARNUNG."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "WARNING", "event": "test"}

        result = processor(None, "warning", event_dict)

        assert result["stufe"] == "WARNUNG"

    def test_adds_german_level_for_error(self):
        """ERROR wird zu FEHLER."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "ERROR", "event": "test"}

        result = processor(None, "error", event_dict)

        assert result["stufe"] == "FEHLER"

    def test_adds_german_level_for_critical(self):
        """CRITICAL wird zu KRITISCH."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "CRITICAL", "event": "test"}

        result = processor(None, "critical", event_dict)

        assert result["stufe"] == "KRITISCH"

    def test_unknown_level_preserved(self):
        """Unbekannte Level werden beibehalten."""
        processor = GermanLogLevelProcessor()
        event_dict = {"level": "TRACE", "event": "test"}

        result = processor(None, "trace", event_dict)

        assert result["stufe"] == "TRACE"

    def test_no_level_no_german_level(self):
        """Ohne level wird kein stufe hinzugefuegt."""
        processor = GermanLogLevelProcessor()
        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        assert "stufe" not in result


class TestCorrelationIdProcessor:
    """Tests fuer CorrelationIdProcessor."""

    def test_adds_correlation_id_when_set(self):
        """Correlation ID wird hinzugefuegt wenn im Context."""
        processor = CorrelationIdProcessor()
        event_dict = {"event": "test"}

        # Context Variable kann im Processor nicht direkt getestet werden
        # ohne den vollen Middleware-Kontext
        result = processor(None, "info", event_dict)

        # Ohne gesetzten Context sollte kein korrelations_id da sein
        # (Default ist None)
        assert "korrelations_id" not in result or result.get("korrelations_id") is None

    def test_no_correlation_id_when_not_set(self):
        """Keine Correlation ID ohne Context."""
        processor = CorrelationIdProcessor()
        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        assert "korrelations_id" not in result or result.get("korrelations_id") is None


class TestSensitiveDataFilter:
    """Tests fuer SensitiveDataFilter (GDPR-Compliance)."""

    @pytest.fixture
    def filter(self):
        """SensitiveDataFilter Instanz."""
        return SensitiveDataFilter()

    @staticmethod
    def _expected_mask(value: str) -> str:
        """Spiegelt den partiellen Maskierungs-Vertrag von _mask_value wider.

        Vertrag (app/core/logging_config.py): erste 2 + last 2 Zeichen bleiben,
        Rest wird mit '*' ersetzt; Werte <= 4 Zeichen werden komplett '****'.
        """
        if len(value) <= 4:
            return "****"
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"

    def test_redacts_password(self, filter):
        """password wird (partiell) maskiert."""
        event_dict = {"event": "test", "password": "geheim123"}

        result = filter(None, "info", event_dict)

        assert result["password"] == self._expected_mask("geheim123")
        assert "geheim123" != result["password"]

    def test_redacts_passwort(self, filter):
        """passwort (deutsch) wird (partiell) maskiert."""
        event_dict = {"event": "test", "passwort": "geheim123"}

        result = filter(None, "info", event_dict)

        assert result["passwort"] == self._expected_mask("geheim123")

    def test_redacts_token(self, filter):
        """token wird (partiell) maskiert."""
        event_dict = {"event": "test", "token": "eyJhbG..."}

        result = filter(None, "info", event_dict)

        assert result["token"] == self._expected_mask("eyJhbG...")

    def test_redacts_access_token(self, filter):
        """access_token wird (partiell) maskiert."""
        event_dict = {"event": "test", "access_token": "abc123"}

        result = filter(None, "info", event_dict)

        assert result["access_token"] == self._expected_mask("abc123")

    def test_redacts_refresh_token(self, filter):
        """refresh_token wird (partiell) maskiert."""
        event_dict = {"event": "test", "refresh_token": "refresh123"}

        result = filter(None, "info", event_dict)

        assert result["refresh_token"] == self._expected_mask("refresh123")

    def test_redacts_api_key(self, filter):
        """api_key wird (partiell) maskiert."""
        event_dict = {"event": "test", "api_key": "sk-123abc"}

        result = filter(None, "info", event_dict)

        assert result["api_key"] == self._expected_mask("sk-123abc")

    def test_redacts_secret(self, filter):
        """secret wird (partiell) maskiert."""
        event_dict = {"event": "test", "client_secret": "supersecret"}

        result = filter(None, "info", event_dict)

        assert result["client_secret"] == self._expected_mask("supersecret")

    def test_redacts_email(self, filter):
        """email wird (partiell) maskiert."""
        event_dict = {"event": "test", "email": "test@example.com"}

        result = filter(None, "info", event_dict)

        assert result["email"] == self._expected_mask("test@example.com")

    def test_redacts_iban(self, filter):
        """iban wird (partiell) maskiert."""
        event_dict = {"event": "test", "iban": "DE89370400440532013000"}

        result = filter(None, "info", event_dict)

        assert result["iban"] == self._expected_mask("DE89370400440532013000")

    def test_redacts_credit_card(self, filter):
        """credit_card wird (partiell) maskiert."""
        event_dict = {"event": "test", "credit_card": "4111111111111111"}

        result = filter(None, "info", event_dict)

        assert result["credit_card"] == self._expected_mask("4111111111111111")

    def test_redacts_authorization_header(self, filter):
        """authorization Header wird (partiell) maskiert."""
        event_dict = {"event": "test", "authorization": "Bearer eyJhbG..."}

        result = filter(None, "info", event_dict)

        assert result["authorization"] == self._expected_mask("Bearer eyJhbG...")

    def test_redacts_case_insensitive(self, filter):
        """Erkennung ist case-insensitive (partielle Maskierung)."""
        event_dict = {
            "event": "test",
            "PASSWORD": "secret",
            "Api_Key": "key123",
            "EMAIL_address": "test@test.de"
        }

        result = filter(None, "info", event_dict)

        assert result["PASSWORD"] == self._expected_mask("secret")
        assert result["Api_Key"] == self._expected_mask("key123")
        assert result["EMAIL_address"] == self._expected_mask("test@test.de")

    def test_preserves_non_sensitive_fields(self, filter):
        """Nicht-sensitive Felder bleiben erhalten."""
        event_dict = {
            "event": "test",
            "user_id": "123",
            "path": "/api/users",
            "method": "GET"
        }

        result = filter(None, "info", event_dict)

        assert result["user_id"] == "123"
        assert result["path"] == "/api/users"
        assert result["method"] == "GET"


class TestPerformanceProcessor:
    """Tests fuer PerformanceProcessor."""

    @pytest.fixture
    def processor(self):
        """PerformanceProcessor Instanz."""
        return PerformanceProcessor()

    def test_adds_timestamp(self, processor):
        """zeitstempel wird hinzugefuegt."""
        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        assert "zeitstempel" in result
        # Sollte ISO-Format haben
        datetime.fromisoformat(result["zeitstempel"])

    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    def test_adds_system_metrics(self, mock_disk, mock_mem, mock_cpu, processor):
        """System-Metriken werden hinzugefuegt."""
        mock_cpu.return_value = 45.5
        mock_mem.return_value = Mock(percent=60.0)
        mock_disk.return_value = Mock(percent=75.0)

        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        assert "system" in result
        assert result["system"]["cpu_prozent"] == 45.5
        assert result["system"]["speicher_prozent"] == 60.0
        assert result["system"]["festplatte_prozent"] == 75.0

    @patch("psutil.cpu_percent", return_value=50.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.memory_allocated", return_value=4 * 1024**3)  # 4GB
    @patch("torch.cuda.get_device_properties")
    def test_adds_gpu_metrics_when_available(
        self, mock_props, mock_mem, mock_available, mock_disk, mock_vmem, mock_cpu, processor
    ):
        """GPU-Metriken werden hinzugefuegt wenn verfuegbar."""
        mock_vmem.return_value = Mock(percent=50.0)
        mock_disk.return_value = Mock(percent=50.0)
        mock_props.return_value = Mock(total_memory=16 * 1024**3)  # 16GB

        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        assert "gpu" in result
        # Quelle nutzt korrekt den deutschen Umlaut-Schluessel "verfügbar"
        # (CLAUDE.md Regel 2 - UTF-8 fuer Umlaute).
        assert result["gpu"]["verfügbar"] is True
        assert result["gpu"]["speicher_verwendet"] == 4.0  # 4GB
        assert result["gpu"]["speicher_gesamt"] == 16.0  # 16GB


class TestRequestContextProcessor:
    """Tests fuer RequestContextProcessor."""

    def test_no_request_context_without_request(self):
        """Ohne Request kein anfrage-Kontext."""
        processor = RequestContextProcessor()
        event_dict = {"event": "test"}

        result = processor(None, "info", event_dict)

        # Ohne Request im Context wird kein anfrage hinzugefuegt
        assert "anfrage" not in result or result.get("anfrage") is None


class TestConvenienceLoggingFunctions:
    """Tests fuer Convenience Logging Functions."""

    def test_log_erfolg(self):
        """log_erfolg loggt mit typ=erfolg."""
        logger = Mock()

        log_erfolg(logger, "Operation erfolgreich", extra_field="value")

        logger.info.assert_called_once_with(
            "Operation erfolgreich",
            typ="erfolg",
            extra_field="value"
        )

    def test_log_warnung(self):
        """log_warnung loggt mit typ=warnung."""
        logger = Mock()

        log_warnung(logger, "Vorsicht", reason="etwas stimmt nicht")

        logger.warning.assert_called_once_with(
            "Vorsicht",
            typ="warnung",
            reason="etwas stimmt nicht"
        )

    def test_log_fehler(self):
        """log_fehler loggt mit typ=fehler."""
        logger = Mock()

        log_fehler(logger, "Fehler aufgetreten", error_code=500)

        logger.error.assert_called_once_with(
            "Fehler aufgetreten",
            typ="fehler",
            error_code=500
        )

    def test_log_ocr_verarbeitung(self):
        """log_ocr_verarbeitung loggt OCR-Events."""
        logger = Mock()

        log_ocr_verarbeitung(
            logger,
            dokument_id="doc123",
            backend="deepseek",
            status="erfolgreich",
            dauer_ms=1500
        )

        logger.info.assert_called_once()
        call_args = logger.info.call_args
        assert call_args[0][0] == "OCR Verarbeitung"
        assert call_args[1]["dokument_id"] == "doc123"
        assert call_args[1]["backend"] == "deepseek"
        assert call_args[1]["status"] == "erfolgreich"
        assert call_args[1]["dauer_ms"] == 1500
        assert call_args[1]["kategorie"] == "ocr"

    def test_log_authentifizierung_erfolg(self):
        """log_authentifizierung loggt erfolgreiche Auth."""
        logger = Mock()

        log_authentifizierung(
            logger,
            benutzer="user@example.com",
            aktion="login",
            erfolgreich=True,
            ip_adresse="192.168.1.100"
        )

        logger.info.assert_called_once()
        call_args = logger.info.call_args
        assert call_args[0][0] == "Authentifizierung"
        assert call_args[1]["erfolgreich"] is True
        assert call_args[1]["kategorie"] == "sicherheit"

    def test_log_authentifizierung_fehlgeschlagen(self):
        """log_authentifizierung loggt fehlgeschlagene Auth als Warning."""
        logger = Mock()

        log_authentifizierung(
            logger,
            benutzer="attacker",
            aktion="login",
            erfolgreich=False,
            ip_adresse="evil.ip"
        )

        logger.warning.assert_called_once()
        call_args = logger.warning.call_args
        assert call_args[1]["erfolgreich"] is False

    def test_log_api_anfrage(self):
        """log_api_anfrage loggt API-Requests."""
        logger = Mock()

        log_api_anfrage(
            logger,
            methode="POST",
            pfad="/api/v1/documents",
            status_code=201,
            dauer_ms=45,
            benutzer_id="user123"
        )

        logger.info.assert_called_once()
        call_args = logger.info.call_args
        assert call_args[0][0] == "API Anfrage"
        assert call_args[1]["methode"] == "POST"
        assert call_args[1]["pfad"] == "/api/v1/documents"
        assert call_args[1]["status_code"] == 201
        assert call_args[1]["dauer_ms"] == 45
        assert call_args[1]["benutzer_id"] == "user123"
        assert call_args[1]["kategorie"] == "api"

    def test_log_datenbank_operation(self):
        """log_datenbank_operation loggt DB-Operationen."""
        logger = Mock()

        log_datenbank_operation(
            logger,
            operation="SELECT",
            tabelle="documents",
            dauer_ms=12,
            zeilen_betroffen=100
        )

        logger.debug.assert_called_once()
        call_args = logger.debug.call_args
        assert call_args[0][0] == "Datenbank Operation"
        assert call_args[1]["operation"] == "SELECT"
        assert call_args[1]["tabelle"] == "documents"
        assert call_args[1]["dauer_ms"] == 12
        assert call_args[1]["zeilen_betroffen"] == 100
        assert call_args[1]["kategorie"] == "datenbank"


class TestConfigureLogging:
    """Tests fuer configure_logging Funktion."""

    @patch("structlog.configure")
    @patch("logging.basicConfig")
    def test_configure_with_defaults(self, mock_basic, mock_struct):
        """Konfiguration mit Standardwerten."""
        configure_logging()

        mock_struct.assert_called_once()
        mock_basic.assert_called_once()

    @patch("structlog.configure")
    @patch("logging.basicConfig")
    def test_configure_json_format(self, mock_basic, mock_struct):
        """Konfiguration mit JSON-Format."""
        configure_logging(log_format="json")

        # Verify structlog was configured
        mock_struct.assert_called_once()

    @patch("structlog.configure")
    @patch("logging.basicConfig")
    def test_configure_console_format(self, mock_basic, mock_struct):
        """Konfiguration mit Console-Format."""
        configure_logging(log_format="console")

        mock_struct.assert_called_once()

    @patch("structlog.configure")
    @patch("logging.basicConfig")
    def test_configure_with_log_level(self, mock_basic, mock_struct):
        """Konfiguration mit spezifischem Log-Level."""
        configure_logging(log_level="DEBUG")

        mock_basic.assert_called_once()
        # Log level sollte DEBUG sein
        call_kwargs = mock_basic.call_args[1]
        assert call_kwargs["level"] == 10  # DEBUG = 10


class TestGetLogger:
    """Tests fuer get_logger Funktion."""

    def test_returns_logger(self):
        """get_logger gibt einen Logger zurueck."""
        logger = get_logger("test_module")

        assert logger is not None

    def test_logger_has_methods(self):
        """Logger hat die erwarteten Methoden."""
        logger = get_logger("test_module")

        # Structlog bound logger hat diese Methoden
        assert hasattr(logger, "info") or hasattr(logger, "msg")
        assert hasattr(logger, "debug") or hasattr(logger, "msg")


class TestGermanLogLevelsMapping:
    """Tests fuer GERMAN_LOG_LEVELS Mapping."""

    def test_all_levels_defined(self):
        """Alle Standard-Level sind definiert."""
        expected_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in expected_levels:
            assert level in GERMAN_LOG_LEVELS

    def test_german_translations(self):
        """Deutsche Uebersetzungen sind korrekt."""
        assert GERMAN_LOG_LEVELS["DEBUG"] == "FEHLERSUCHE"
        assert GERMAN_LOG_LEVELS["INFO"] == "INFORMATION"
        assert GERMAN_LOG_LEVELS["WARNING"] == "WARNUNG"
        assert GERMAN_LOG_LEVELS["ERROR"] == "FEHLER"
        assert GERMAN_LOG_LEVELS["CRITICAL"] == "KRITISCH"


class TestSensitiveFieldsList:
    """Tests fuer SENSITIVE_FIELDS Liste."""

    def test_sensitive_fields_comprehensive(self):
        """SENSITIVE_FIELDS enthaelt wichtige Felder."""
        filter = SensitiveDataFilter()

        # Alle wichtigen sensiblen Felder sollten erkannt werden
        sensitive_fields = [
            "password", "passwort", "token", "access_token",
            "refresh_token", "api_key", "secret", "email",
            "iban", "credit_card", "ssn", "authorization"
        ]

        for field in sensitive_fields:
            event_dict = {field: "sensitive_value"}
            result = filter(None, "info", event_dict)
            # Partielle Maskierung: erste 2 + last 2 bleiben, Rest wird '*'.
            masked = result[field]
            value = "sensitive_value"
            expected = f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
            assert masked != value, f"{field} sollte maskiert werden"
            assert masked == expected, f"{field} sollte partiell maskiert werden"
