# -*- coding: utf-8 -*-
"""
Tests fuer Error API Endpoints.

Testet Error-Statistiken, Trends und Alert-Management via API.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.services.error_tracking_service import (
    ErrorCategory,
    ErrorSeverity,
    ErrorTrackingService,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_superuser():
    """Mock Superuser fuer Admin-Endpoints."""
    user = Mock()
    user.id = "admin-123"
    user.email = "admin@example.com"
    user.is_superuser = True
    return user


@pytest.fixture
def mock_error_service():
    """Mock Error Tracking Service."""
    service = Mock(spec=ErrorTrackingService)

    # Mock Stats
    service.get_stats.return_value = {
        "ocr": {
            "total_count": 10,
            "last_hour_count": 5,
            "last_24h_count": 10,
            "rate_per_minute": 0.5,
            "last_error_time": datetime.now(timezone.utc).isoformat(),
            "error_types": {"OCRProcessingError": 8, "OCRTimeoutError": 2},
            "severity_counts": {"error": 7, "warning": 3},
            "alert_active": False,
        },
        "gpu": {
            "total_count": 3,
            "last_hour_count": 1,
            "last_24h_count": 3,
            "rate_per_minute": 0.1,
            "last_error_time": datetime.now(timezone.utc).isoformat(),
            "error_types": {"GPUOutOfMemoryError": 3},
            "severity_counts": {"critical": 3},
            "alert_active": True,
        },
    }

    # Mock Recent Errors
    service.get_recent_errors.return_value = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": "ocr",
            "error_type": "OCRProcessingError",
            "severity": "error",
            "message": "OCR fehlgeschlagen",
            "path": "/api/v1/ocr/process",
            "request_id": "req-123",
        }
    ]

    # Mock Trends
    service.get_error_trends.return_value = {
        "category": "ocr",
        "period_hours": 24,
        "total_errors": 10,
        "hourly_counts": {"2025-01-01 10:00": 5, "2025-01-01 11:00": 5},
        "average_per_hour": 0.42,
    }

    # Mock Top Errors
    service.get_top_errors.return_value = [
        {"error_type": "OCRProcessingError", "count": 8, "category": "ocr"},
        {"error_type": "GPUOutOfMemoryError", "count": 3, "category": "gpu"},
    ]

    return service


@pytest.fixture
def test_client(mock_superuser, mock_error_service):
    """Test Client mit gemockten Dependencies - ohne Auth."""
    from fastapi import FastAPI
    from app.api.v1.errors import router
    from app.api.dependencies import get_current_superuser

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override superuser dependency globally
    app.dependency_overrides[get_current_superuser] = lambda: mock_superuser

    with patch("app.api.v1.errors.get_error_tracking_service", return_value=mock_error_service):
        client = TestClient(app)
        yield client


# =============================================================================
# GET /errors/stats TESTS
# =============================================================================


class TestGetAllErrorStats:
    """Tests fuer GET /errors/stats Endpoint."""

    def test_get_all_stats_success(self, test_client, mock_error_service):
        """Alle Statistiken erfolgreich abrufen."""
        response = test_client.get("/api/v1/errors/stats")
        assert response.status_code == 200

        data = response.json()
        assert "zeitstempel" in data
        assert "kategorien" in data
        assert "zusammenfassung" in data


# =============================================================================
# GET /errors/stats/{category} TESTS
# =============================================================================


class TestGetCategoryStats:
    """Tests fuer GET /errors/stats/{category} Endpoint."""

    def test_get_category_stats_ocr(self, test_client, mock_error_service):
        """Statistiken fuer OCR-Kategorie abrufen."""
        # Mock fuer einzelne Kategorie
        mock_error_service.get_stats.return_value = {
            "total_count": 10,
            "last_hour_count": 5,
            "last_24h_count": 10,
            "rate_per_minute": 0.5,
            "last_error_time": None,
            "error_types": {},
            "severity_counts": {},
            "alert_active": False,
        }

        response = test_client.get("/api/v1/errors/stats/ocr")
        assert response.status_code == 200

    def test_get_category_stats_invalid_category(self, test_client, mock_error_service):
        """Ungueltige Kategorie gibt Fehler."""
        response = test_client.get("/api/v1/errors/stats/invalid_category")
        # Sollte 422 (Validation Error) sein
        assert response.status_code == 422


# =============================================================================
# GET /errors/recent TESTS
# =============================================================================


class TestGetRecentErrors:
    """Tests fuer GET /errors/recent Endpoint."""

    def test_get_recent_errors_default(self, test_client, mock_error_service):
        """Recent Errors mit Standardwerten abrufen."""
        response = test_client.get("/api/v1/errors/recent")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_get_recent_errors_with_filters(self, test_client, mock_error_service):
        """Recent Errors mit Filtern abrufen."""
        response = test_client.get(
            "/api/v1/errors/recent",
            params={"category": "ocr", "severity": "error", "limit": 10},
        )
        assert response.status_code == 200

    def test_get_recent_errors_limit_validation(self, test_client, mock_error_service):
        """Limit-Validierung funktioniert."""
        # Limit zu gross
        response = test_client.get(
            "/api/v1/errors/recent",
            params={"limit": 1000},
        )
        # Sollte 422 sein (Limit max 500)
        assert response.status_code == 422


# =============================================================================
# GET /errors/trends/{category} TESTS
# =============================================================================


class TestGetErrorTrends:
    """Tests fuer GET /errors/trends/{category} Endpoint."""

    def test_get_trends_basic(self, test_client, mock_error_service):
        """Trends fuer Kategorie abrufen."""
        response = test_client.get("/api/v1/errors/trends/ocr")
        assert response.status_code == 200

        data = response.json()
        assert data["category"] == "ocr"

    def test_get_trends_with_hours(self, test_client, mock_error_service):
        """Trends mit Zeitraum abrufen."""
        response = test_client.get(
            "/api/v1/errors/trends/ocr",
            params={"hours": 48},
        )
        assert response.status_code == 200

    def test_get_trends_hours_validation(self, test_client, mock_error_service):
        """Hours-Validierung funktioniert."""
        # Hours zu gross (max 168)
        response = test_client.get(
            "/api/v1/errors/trends/ocr",
            params={"hours": 500},
        )
        assert response.status_code == 422


# =============================================================================
# GET /errors/top TESTS
# =============================================================================


class TestGetTopErrors:
    """Tests fuer GET /errors/top Endpoint."""

    def test_get_top_errors_default(self, test_client, mock_error_service):
        """Top Errors mit Standardwerten abrufen."""
        response = test_client.get("/api/v1/errors/top")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_get_top_errors_with_category(self, test_client, mock_error_service):
        """Top Errors mit Kategorie-Filter abrufen."""
        response = test_client.get(
            "/api/v1/errors/top",
            params={"category": "ocr", "limit": 5},
        )
        assert response.status_code == 200


# =============================================================================
# POST /errors/alerts/{category} TESTS
# =============================================================================


class TestConfigureAlert:
    """Tests fuer POST /errors/alerts/{category} Endpoint."""

    def test_configure_alert_success(self, test_client, mock_error_service):
        """Alert konfigurieren erfolgreich."""
        response = test_client.post(
            "/api/v1/errors/alerts/ocr",
            json={"threshold_per_minute": 5.0, "cooldown_minutes": 10},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "erfolg"

    def test_configure_alert_validation(self, test_client, mock_error_service):
        """Alert-Konfiguration Validierung."""
        # Ungueltige Werte
        response = test_client.post(
            "/api/v1/errors/alerts/ocr",
            json={"threshold_per_minute": 0, "cooldown_minutes": 100},
        )
        assert response.status_code == 422


# =============================================================================
# DELETE /errors/alerts/{category} TESTS
# =============================================================================


class TestClearAlert:
    """Tests fuer DELETE /errors/alerts/{category} Endpoint."""

    def test_clear_alert_success(self, test_client, mock_error_service):
        """Alert loeschen erfolgreich."""
        response = test_client.delete("/api/v1/errors/alerts/ocr")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "erfolg"


# =============================================================================
# POST /errors/reset TESTS
# =============================================================================


class TestResetStats:
    """Tests fuer POST /errors/reset Endpoint."""

    def test_reset_stats_all(self, test_client, mock_error_service):
        """Alle Stats zuruecksetzen."""
        response = test_client.post("/api/v1/errors/reset")
        assert response.status_code == 200

    def test_reset_stats_category(self, test_client, mock_error_service):
        """Stats fuer Kategorie zuruecksetzen."""
        response = test_client.post(
            "/api/v1/errors/reset",
            params={"category": "ocr"},
        )
        assert response.status_code == 200


# =============================================================================
# POST /errors/cleanup TESTS
# =============================================================================


class TestCleanupErrors:
    """Tests fuer POST /errors/cleanup Endpoint."""

    def test_cleanup_errors(self, test_client, mock_error_service):
        """Alte Fehler bereinigen."""
        import asyncio
        mock_future = asyncio.Future()
        mock_future.set_result(5)
        mock_error_service.cleanup_old_errors = MagicMock(return_value=mock_future)

        response = test_client.post("/api/v1/errors/cleanup")
        assert response.status_code == 200


# =============================================================================
# GET /errors/prometheus TESTS
# =============================================================================


class TestPrometheusMetrics:
    """Tests fuer GET /errors/prometheus Endpoint."""

    def test_prometheus_metrics(self, test_client, mock_error_service):
        """Prometheus Metriken abrufen."""
        mock_error_service.get_stats.return_value = {
            "ocr": {
                "total_count": 10,
                "rate_per_minute": 0.5,
                "alert_active": False,
            },
            "gpu": {
                "total_count": 3,
                "rate_per_minute": 0.1,
                "alert_active": True,
            },
        }

        response = test_client.get("/api/v1/errors/prometheus")
        # Kein Auth erforderlich fuer Prometheus
        assert response.status_code == 200

        data = response.json()
        assert "ablage_errors_total" in data
        assert "kategorien" in data


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestErrorTrackingIntegration:
    """Integration Tests fuer Error Tracking."""

    def test_error_flow_complete(self):
        """Kompletter Error-Flow funktioniert."""
        # Reset Singleton
        ErrorTrackingService._instance = None

        service = ErrorTrackingService()
        service._max_buffer_size = 100

        # Track error
        service.track_error(
            category=ErrorCategory.OCR,
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
            message="Integration Test",
        )

        # Get stats
        stats = service.get_stats(ErrorCategory.OCR)
        assert stats["total_count"] == 1

        # Get recent
        recent = service.get_recent_errors(limit=1)
        assert len(recent) == 1

        # Get trends
        trends = service.get_error_trends(ErrorCategory.OCR, hours=1)
        assert trends["total_errors"] == 1

        # Reset
        service.reset_stats()
        stats = service.get_stats(ErrorCategory.OCR)
        assert stats["total_count"] == 0

        # Cleanup Singleton
        ErrorTrackingService._instance = None
