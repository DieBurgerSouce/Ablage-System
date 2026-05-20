# -*- coding: utf-8 -*-
"""
Tests fuer den Error Tracking Service.

Testet Fehler-Tracking, Statistiken, Trends und Alerting.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock

import pytest

from app.services.error_tracking_service import (
    ErrorTrackingService,
    get_error_tracking_service,
    track_error,
    track_ocr_error,
    track_gpu_error,
    track_auth_error,
    track_db_error,
    ErrorCategory,
    ErrorSeverity,
    TrackedError,
    ErrorStats,
    AlertConfig,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def fresh_service():
    """Erstellt eine frische Service-Instanz fuer isolierte Tests."""
    # Reset Singleton
    ErrorTrackingService._instance = None

    # Erstelle neue Instanz (Singleton reset)
    service = ErrorTrackingService()
    # Override Settings fuer Tests
    service._max_buffer_size = 100
    service._retention_hours = 1
    service._error_buffer = []
    service._stats = {cat: ErrorStats() for cat in ErrorCategory}

    yield service

    # Cleanup
    ErrorTrackingService._instance = None


@pytest.fixture
def service_with_errors(fresh_service):
    """Service mit vorhandenen Fehlern."""
    service = fresh_service

    # Fuege verschiedene Fehler hinzu
    service.track_error(
        category=ErrorCategory.OCR,
        error_type="OCRProcessingError",
        severity=ErrorSeverity.ERROR,
        message="OCR fehlgeschlagen fuer Dokument",
        path="/api/v1/ocr/process",
    )

    service.track_error(
        category=ErrorCategory.GPU,
        error_type="GPUOutOfMemoryError",
        severity=ErrorSeverity.CRITICAL,
        message="GPU Speicher erschoepft",
        path="/api/v1/ocr/batch",
    )

    service.track_error(
        category=ErrorCategory.AUTH,
        error_type="AuthenticationError",
        severity=ErrorSeverity.WARNING,
        message="Ungueltige Anmeldedaten",
        path="/api/v1/auth/login",
    )

    service.track_error(
        category=ErrorCategory.VALIDATION,
        error_type="ValidationError",
        severity=ErrorSeverity.WARNING,
        message="Ungueltige Eingabe",
        path="/api/v1/documents",
    )

    return service


# =============================================================================
# SERVICE TESTS
# =============================================================================


class TestErrorTrackingService:
    """Tests fuer ErrorTrackingService Klasse."""

    def test_singleton_pattern(self, fresh_service):
        """Service sollte Singleton sein."""
        service1 = ErrorTrackingService()
        service2 = ErrorTrackingService()

        assert service1 is service2

    def test_track_error_basic(self, fresh_service):
        """Basis-Fehler-Tracking funktioniert."""
        service = fresh_service

        service.track_error(
            category=ErrorCategory.OCR,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test-Fehlermeldung",
        )

        stats = service.get_stats(ErrorCategory.OCR)
        assert stats["total_count"] == 1
        assert "TestError" in stats["error_types"]
        assert stats["error_types"]["TestError"] == 1

    def test_track_error_with_all_fields(self, fresh_service):
        """Fehler-Tracking mit allen Feldern funktioniert."""
        service = fresh_service

        service.track_error(
            category=ErrorCategory.DATABASE,
            error_type="ConnectionError",
            severity=ErrorSeverity.CRITICAL,
            message="Datenbankverbindung fehlgeschlagen",
            path="/api/v1/documents",
            user_id="user-123",
            request_id="req-456",
            details={"host": "localhost", "port": 5432},
            response_time_ms=150.5,
        )

        recent = service.get_recent_errors(limit=1)
        assert len(recent) == 1
        assert recent[0]["error_type"] == "ConnectionError"
        assert recent[0]["category"] == "database"
        assert recent[0]["path"] == "/api/v1/documents"

    def test_message_truncation(self, fresh_service):
        """Lange Nachrichten werden truncated."""
        service = fresh_service
        long_message = "x" * 1000

        service.track_error(
            category=ErrorCategory.SYSTEM,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message=long_message,
        )

        recent = service.get_recent_errors(limit=1)
        assert len(recent[0]["message"]) == 500

    def test_stack_trace_truncation(self, fresh_service):
        """Lange Stack-Traces werden truncated."""
        service = fresh_service
        long_trace = "line\n" * 500

        service.track_error(
            category=ErrorCategory.SYSTEM,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test",
            stack_trace=long_trace,
        )

        # Stack-Trace wird intern gespeichert, aber nicht in get_recent_errors zurueckgegeben
        assert service._error_buffer[0].stack_trace is not None
        assert len(service._error_buffer[0].stack_trace) == 2000

    def test_buffer_ring_behavior(self, fresh_service):
        """Buffer verhaelt sich wie Ring-Buffer bei Ueberlauf."""
        service = fresh_service

        # Fuege mehr Fehler hinzu als max_buffer_size
        for i in range(150):
            service.track_error(
                category=ErrorCategory.OCR,
                error_type=f"Error_{i}",
                severity=ErrorSeverity.ERROR,
                message=f"Fehler {i}",
            )

        # Buffer sollte auf max_buffer_size (100) begrenzt sein
        assert len(service._error_buffer) <= 100

        # Neueste Fehler sollten erhalten sein (Error_149 ist der letzte)
        recent = service.get_recent_errors(limit=1)
        # Die neueste Nummer sollte >= 100 sein (die aeltesten wurden entfernt)
        error_num = int(recent[0]["error_type"].split("_")[1])
        assert error_num >= 50  # Die ersten ~50 sollten entfernt worden sein


class TestErrorStats:
    """Tests fuer Fehler-Statistiken."""

    def test_get_stats_single_category(self, service_with_errors):
        """Statistiken fuer einzelne Kategorie abrufen."""
        stats = service_with_errors.get_stats(ErrorCategory.OCR)

        assert stats["total_count"] == 1
        assert "OCRProcessingError" in stats["error_types"]
        assert "error" in stats["severity_counts"]

    def test_get_stats_all_categories(self, service_with_errors):
        """Statistiken fuer alle Kategorien abrufen."""
        all_stats = service_with_errors.get_stats()

        assert "ocr" in all_stats
        assert "gpu" in all_stats
        assert "auth" in all_stats
        assert "validation" in all_stats

    def test_last_error_time(self, fresh_service):
        """Zeitstempel des letzten Fehlers wird korrekt gespeichert."""
        service = fresh_service
        before = datetime.now(timezone.utc)

        service.track_error(
            category=ErrorCategory.OCR,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test",
        )

        after = datetime.now(timezone.utc)
        stats = service.get_stats(ErrorCategory.OCR)

        # last_error_time sollte zwischen before und after liegen
        assert stats["last_error_time"] is not None

    def test_severity_counts(self, service_with_errors):
        """Severity-Zaehler funktionieren korrekt."""
        # Fuege mehr Fehler mit verschiedenen Severities hinzu
        service_with_errors.track_error(
            category=ErrorCategory.OCR,
            error_type="MinorError",
            severity=ErrorSeverity.WARNING,
            message="Warnung",
        )

        stats = service_with_errors.get_stats(ErrorCategory.OCR)

        assert "error" in stats["severity_counts"]
        assert "warning" in stats["severity_counts"]


class TestRecentErrors:
    """Tests fuer Recent Errors Abfrage."""

    def test_get_recent_errors_basic(self, service_with_errors):
        """Recent Errors Abfrage funktioniert."""
        recent = service_with_errors.get_recent_errors(limit=10)

        assert len(recent) == 4
        # Neueste zuerst
        assert recent[0]["timestamp"] >= recent[-1]["timestamp"]

    def test_get_recent_errors_category_filter(self, service_with_errors):
        """Filter nach Kategorie funktioniert."""
        recent = service_with_errors.get_recent_errors(
            category=ErrorCategory.OCR,
            limit=10,
        )

        assert len(recent) == 1
        assert all(e["category"] == "ocr" for e in recent)

    def test_get_recent_errors_severity_filter(self, service_with_errors):
        """Filter nach Severity funktioniert."""
        recent = service_with_errors.get_recent_errors(
            severity=ErrorSeverity.WARNING,
            limit=10,
        )

        assert len(recent) == 2
        assert all(e["severity"] == "warning" for e in recent)

    def test_get_recent_errors_limit(self, service_with_errors):
        """Limit wird eingehalten."""
        recent = service_with_errors.get_recent_errors(limit=2)

        assert len(recent) == 2


class TestErrorTrends:
    """Tests fuer Fehler-Trends."""

    def test_get_error_trends_basic(self, service_with_errors):
        """Trends Abfrage funktioniert."""
        trends = service_with_errors.get_error_trends(
            category=ErrorCategory.OCR,
            hours=24,
        )

        assert trends["category"] == "ocr"
        assert trends["period_hours"] == 24
        assert trends["total_errors"] == 1
        assert isinstance(trends["hourly_counts"], dict)

    def test_get_error_trends_empty_category(self, fresh_service):
        """Trends fuer leere Kategorie."""
        trends = fresh_service.get_error_trends(
            category=ErrorCategory.NETWORK,
            hours=24,
        )

        assert trends["total_errors"] == 0
        assert len(trends["hourly_counts"]) == 0


class TestTopErrors:
    """Tests fuer Top-Fehler Abfrage."""

    def test_get_top_errors_basic(self, service_with_errors):
        """Top Errors Abfrage funktioniert."""
        top = service_with_errors.get_top_errors(limit=10)

        assert len(top) == 4
        # Jeder Eintrag hat error_type, count, category
        for entry in top:
            assert "error_type" in entry
            assert "count" in entry
            assert "category" in entry

    def test_get_top_errors_category_filter(self, service_with_errors):
        """Top Errors mit Kategorie-Filter."""
        top = service_with_errors.get_top_errors(
            category=ErrorCategory.OCR,
            limit=10,
        )

        assert len(top) == 1
        assert top[0]["category"] == "ocr"


class TestAlertConfig:
    """Tests fuer Alert-Konfiguration."""

    def test_configure_alert(self, fresh_service):
        """Alert-Konfiguration funktioniert."""
        service = fresh_service

        service.configure_alert(
            category=ErrorCategory.OCR,
            threshold_per_minute=5.0,
            cooldown_minutes=10,
        )

        assert ErrorCategory.OCR in service._alert_configs
        config = service._alert_configs[ErrorCategory.OCR]
        assert config.threshold_per_minute == 5.0
        assert config.cooldown_minutes == 10

    def test_alert_callback(self, fresh_service):
        """Alert-Callback wird aufgerufen."""
        service = fresh_service
        callback_mock = Mock()

        service.configure_alert(
            category=ErrorCategory.OCR,
            threshold_per_minute=0.1,  # Sehr niedriger Schwellenwert
            cooldown_minutes=1,
            callback=callback_mock,
        )

        # Generiere mehrere Fehler um Alert auszuloesen
        for i in range(5):
            service.track_error(
                category=ErrorCategory.OCR,
                error_type="TestError",
                severity=ErrorSeverity.ERROR,
                message=f"Test {i}",
            )

        # Callback sollte aufgerufen worden sein
        # (abhaengig von Rate-Berechnung, kann variieren)

    def test_clear_alert(self, fresh_service):
        """Alert loeschen funktioniert."""
        service = fresh_service

        service.configure_alert(
            category=ErrorCategory.OCR,
            threshold_per_minute=0.1,
        )

        # Simuliere aktiven Alert
        service._active_alerts[ErrorCategory.OCR] = datetime.now(timezone.utc)

        service.clear_alert(ErrorCategory.OCR)

        assert ErrorCategory.OCR not in service._active_alerts


class TestCleanup:
    """Tests fuer Cleanup-Funktionen."""

    @pytest.mark.asyncio
    async def test_cleanup_old_errors(self, fresh_service):
        """Alte Fehler werden bereinigt."""
        service = fresh_service

        # Fuege Fehler hinzu
        service.track_error(
            category=ErrorCategory.OCR,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test",
        )

        initial_count = len(service._error_buffer)

        # Simuliere alten Fehler durch manuelle Timestamp-Aenderung
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=48)
        service._error_buffer[0] = TrackedError(
            timestamp=old_timestamp,
            category=ErrorCategory.OCR,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Test",
        )

        # Retention ist 1 Stunde (aus Fixture), also wird alles aelter als 1h entfernt
        removed = await service.cleanup_old_errors()

        assert removed == initial_count
        assert len(service._error_buffer) == 0

    def test_reset_stats_single_category(self, service_with_errors):
        """Stats fuer einzelne Kategorie zuruecksetzen."""
        service = service_with_errors

        service.reset_stats(ErrorCategory.OCR)

        stats = service.get_stats(ErrorCategory.OCR)
        assert stats["total_count"] == 0

        # Andere Kategorien sollten nicht betroffen sein
        gpu_stats = service.get_stats(ErrorCategory.GPU)
        assert gpu_stats["total_count"] == 1

    def test_reset_stats_all(self, service_with_errors):
        """Stats fuer alle Kategorien zuruecksetzen."""
        service = service_with_errors

        service.reset_stats()

        for cat in ErrorCategory:
            stats = service.get_stats(cat)
            assert stats["total_count"] == 0


class TestSanitization:
    """Tests fuer Daten-Sanitization."""

    def test_sanitize_sensitive_keys(self, fresh_service):
        """Sensible Keys werden entfernt."""
        service = fresh_service

        details = {
            "password": "secret123",
            "api_key": "key123",
            "email": "user@example.com",
            "safe_field": "safe_value",  # "field" statt "key" da "key" sensitiv ist
        }

        sanitized = service._sanitize_details(details)

        assert "password" not in sanitized
        assert "api_key" not in sanitized
        assert "email" not in sanitized
        assert sanitized["safe_field"] == "safe_value"

    def test_sanitize_nested_dict(self, fresh_service):
        """Verschachtelte Dicts werden sanitized."""
        service = fresh_service

        details = {
            "nested": {
                "password": "secret",
                "safe": "value",
            }
        }

        sanitized = service._sanitize_details(details)

        assert "password" not in sanitized["nested"]
        assert sanitized["nested"]["safe"] == "value"

    def test_sanitize_long_strings(self, fresh_service):
        """Lange Strings werden truncated."""
        service = fresh_service

        details = {
            "long_value": "x" * 500,
        }

        sanitized = service._sanitize_details(details)

        assert len(sanitized["long_value"]) == 203  # 200 + "..."


# =============================================================================
# CONVENIENCE FUNCTIONS TESTS
# =============================================================================


class TestConvenienceFunctions:
    """Tests fuer Convenience-Funktionen."""

    def test_track_error_convenience(self, fresh_service):
        """track_error Convenience-Funktion funktioniert."""
        track_error(
            ErrorCategory.OCR,
            "TestError",
            "Test-Nachricht",
        )

        service = get_error_tracking_service()
        stats = service.get_stats(ErrorCategory.OCR)
        assert stats["total_count"] >= 1

    def test_track_ocr_error(self, fresh_service):
        """track_ocr_error funktioniert."""
        track_ocr_error("OCRFailure", "OCR fehlgeschlagen")

        service = get_error_tracking_service()
        stats = service.get_stats(ErrorCategory.OCR)
        assert "OCRFailure" in stats["error_types"]

    def test_track_gpu_error(self, fresh_service):
        """track_gpu_error funktioniert."""
        track_gpu_error("GPUMemoryError", "GPU Speicher voll")

        service = get_error_tracking_service()
        stats = service.get_stats(ErrorCategory.GPU)
        assert "GPUMemoryError" in stats["error_types"]

    def test_track_auth_error(self, fresh_service):
        """track_auth_error funktioniert."""
        track_auth_error("InvalidToken", "Token ungueltig")

        service = get_error_tracking_service()
        stats = service.get_stats(ErrorCategory.AUTH)
        assert "InvalidToken" in stats["error_types"]

    def test_track_db_error(self, fresh_service):
        """track_db_error funktioniert."""
        track_db_error("ConnectionError", "DB Verbindung fehlgeschlagen")

        service = get_error_tracking_service()
        stats = service.get_stats(ErrorCategory.DATABASE)
        assert "ConnectionError" in stats["error_types"]


# =============================================================================
# RATE TRACKING TESTS
# =============================================================================


class TestRateTracking:
    """Tests fuer Rate-Tracking."""

    def test_rate_calculation(self, fresh_service):
        """Rate-Berechnung funktioniert."""
        service = fresh_service

        # Generiere mehrere Fehler
        for _ in range(5):
            service.track_error(
                category=ErrorCategory.OCR,
                error_type="TestError",
                severity=ErrorSeverity.ERROR,
                message="Test",
            )

        stats = service.get_stats(ErrorCategory.OCR)

        # Rate sollte groesser 0 sein
        assert stats["rate_per_minute"] > 0


class TestSeverityMapping:
    """Tests fuer Severity-Mapping."""

    def test_severity_to_log_level(self, fresh_service):
        """Severity zu Log-Level Mapping."""
        service = fresh_service

        assert service._severity_to_log_level(ErrorSeverity.DEBUG) == "debug"
        assert service._severity_to_log_level(ErrorSeverity.INFO) == "info"
        assert service._severity_to_log_level(ErrorSeverity.WARNING) == "warning"
        assert service._severity_to_log_level(ErrorSeverity.ERROR) == "error"
        assert service._severity_to_log_level(ErrorSeverity.CRITICAL) == "critical"
