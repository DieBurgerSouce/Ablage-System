# -*- coding: utf-8 -*-
"""
Tests fuer Profiling API Endpoints.

Testet:
- Summary Endpoint
- Endpoint-Stats Endpoint
- Slow-Requests Endpoint
- Hot-Paths Endpoint
- Memory-Snapshots Endpoint
- Konfiguration
- Reset
- Report
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.profiling_service import (
    ProfilingLevel,
    ProfilingService,
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
def mock_profiling_service():
    """Mock Profiling Service."""
    service = Mock(spec=ProfilingService)

    # Mock Summary
    service.get_summary.return_value = {
        "status": "aktiv",
        "profiling_level": "basic",
        "uptime_seconds": 3600.0,
        "uptime_formatted": "1:00:00",
        "total_endpoints_tracked": 5,
        "total_requests": 100,
        "total_errors": 5,
        "error_rate_percent": 5.0,
        "total_slow_requests": 3,
        "slow_request_threshold_ms": 1000.0,
        "avg_latency_ms": 150.0,
        "p95_latency_ms": 450.0,
        "p99_latency_ms": 800.0,
        "memory_snapshots_count": 10,
        "slow_requests_buffer_count": 3,
    }

    # Mock Endpoint Stats
    service.get_endpoint_stats.return_value = [
        {
            "endpoint": "/api/users",
            "method": "GET",
            "request_count": 50,
            "avg_time_ms": 120.0,
            "min_time_ms": 50.0,
            "max_time_ms": 500.0,
            "p50_time_ms": 100.0,
            "p95_time_ms": 400.0,
            "p99_time_ms": 480.0,
            "error_count": 2,
            "error_rate_percent": 4.0,
            "slow_request_count": 1,
            "last_request_time": datetime.now(timezone.utc).isoformat(),
        }
    ]

    # Mock Slow Requests
    service.get_slow_requests.return_value = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": "/api/users",
            "method": "GET",
            "duration_ms": 1500.0,
            "status_code": 200,
            "request_id": "req-123",
            "user_id": "user-456",
            "memory_delta_mb": 10.5,
        }
    ]

    # Mock Hot Paths
    service.get_hot_paths.return_value = [
        {
            "rank": 1,
            "endpoint": "/api/users",
            "method": "GET",
            "request_count": 50,
            "avg_time_ms": 120.0,
            "requests_per_second": 0.5,
        }
    ]

    # Mock Memory Snapshots
    service.get_memory_snapshots.return_value = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rss_mb": 500.0,
            "vms_mb": 1000.0,
            "shared_mb": 100.0,
            "gpu_used_mb": 2000.0,
            "context": "test",
        }
    ]

    # Mock Configure
    service.configure.return_value = {
        "profiling_level": "basic",
        "slow_request_threshold_ms": 1000.0,
        "max_slow_requests": 100,
        "max_memory_snapshots": 100,
        "excluded_paths": ["/health", "/metrics"],
    }

    # Mock Reset
    service.reset_stats.return_value = {
        "status": "erfolg",
        "geloeschte_endpoints": 5,
        "geloeschte_langsame_requests": 3,
        "geloeschte_snapshots": 10,
    }

    # Mock profiling_level property
    service.profiling_level = ProfilingLevel.BASIC

    return service


@pytest.fixture
def test_client(mock_superuser, mock_profiling_service):
    """Test Client mit gemockten Dependencies."""
    from app.api.v1.profiling import router
    from app.api.dependencies import get_current_superuser

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override superuser dependency
    app.dependency_overrides[get_current_superuser] = lambda: mock_superuser

    with patch("app.api.v1.profiling.get_profiling_service", return_value=mock_profiling_service):
        client = TestClient(app)
        yield client


# =============================================================================
# GET /profiling/summary TESTS
# =============================================================================


class TestGetProfilingSummary:
    """Tests fuer GET /profiling/summary Endpoint."""

    def test_get_summary_success(self, test_client, mock_profiling_service):
        """Summary erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/summary")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "aktiv"
        assert data["total_requests"] == 100
        assert data["avg_latency_ms"] == 150.0


# =============================================================================
# GET /profiling/endpoints TESTS
# =============================================================================


class TestGetEndpointStats:
    """Tests fuer GET /profiling/endpoints Endpoint."""

    def test_get_endpoints_success(self, test_client, mock_profiling_service):
        """Endpoint-Stats erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/endpoints")
        assert response.status_code == 200

        data = response.json()
        assert "endpoints" in data
        assert len(data["endpoints"]) == 1

    def test_get_endpoints_with_filter(self, test_client, mock_profiling_service):
        """Endpoint-Stats mit Filter abrufen."""
        response = test_client.get(
            "/api/v1/profiling/endpoints",
            params={"endpoint": "/api/users", "method": "GET", "limit": 10}
        )
        assert response.status_code == 200

        mock_profiling_service.get_endpoint_stats.assert_called_once()

    def test_get_endpoints_with_sorting(self, test_client, mock_profiling_service):
        """Endpoint-Stats mit Sortierung abrufen."""
        response = test_client.get(
            "/api/v1/profiling/endpoints",
            params={"sort_by": "avg_time_ms"}
        )
        assert response.status_code == 200

    def test_get_endpoints_invalid_sort(self, test_client, mock_profiling_service):
        """Ungueltige Sortierung gibt Fehler."""
        response = test_client.get(
            "/api/v1/profiling/endpoints",
            params={"sort_by": "invalid_field"}
        )
        assert response.status_code == 422


# =============================================================================
# GET /profiling/slow-requests TESTS
# =============================================================================


class TestGetSlowRequests:
    """Tests fuer GET /profiling/slow-requests Endpoint."""

    def test_get_slow_requests_success(self, test_client, mock_profiling_service):
        """Slow Requests erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/slow-requests")
        assert response.status_code == 200

        data = response.json()
        assert "requests" in data
        assert len(data["requests"]) == 1
        assert data["requests"][0]["duration_ms"] == 1500.0

    def test_get_slow_requests_with_filter(self, test_client, mock_profiling_service):
        """Slow Requests mit Filter abrufen."""
        response = test_client.get(
            "/api/v1/profiling/slow-requests",
            params={"endpoint": "/api/users", "limit": 5}
        )
        assert response.status_code == 200


# =============================================================================
# GET /profiling/hot-paths TESTS
# =============================================================================


class TestGetHotPaths:
    """Tests fuer GET /profiling/hot-paths Endpoint."""

    def test_get_hot_paths_success(self, test_client, mock_profiling_service):
        """Hot Paths erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/hot-paths")
        assert response.status_code == 200

        data = response.json()
        assert "hot_paths" in data
        assert len(data["hot_paths"]) == 1
        assert data["hot_paths"][0]["rank"] == 1

    def test_get_hot_paths_with_limit(self, test_client, mock_profiling_service):
        """Hot Paths mit Limit abrufen."""
        response = test_client.get(
            "/api/v1/profiling/hot-paths",
            params={"limit": 5}
        )
        assert response.status_code == 200


# =============================================================================
# GET /profiling/memory TESTS
# =============================================================================


class TestGetMemorySnapshots:
    """Tests fuer GET /profiling/memory Endpoint."""

    def test_get_memory_snapshots_success(self, test_client, mock_profiling_service):
        """Memory Snapshots erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/memory")
        assert response.status_code == 200

        data = response.json()
        assert "snapshots" in data
        assert len(data["snapshots"]) == 1
        assert data["snapshots"][0]["rss_mb"] == 500.0


# =============================================================================
# POST /profiling/memory/snapshot TESTS
# =============================================================================


class TestTriggerMemorySnapshot:
    """Tests fuer POST /profiling/memory/snapshot Endpoint."""

    def test_trigger_snapshot_success(self, test_client, mock_profiling_service):
        """Memory Snapshot ausloesen erfolgreich."""
        mock_snapshot = MagicMock()
        mock_snapshot.to_dict.return_value = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rss_mb": 500.0,
            "vms_mb": 1000.0,
            "shared_mb": 100.0,
            "heap_mb": None,
            "gpu_used_mb": 2000.0,
            "context": "manual",
        }
        mock_profiling_service.take_memory_snapshot.return_value = mock_snapshot

        response = test_client.post(
            "/api/v1/profiling/memory/snapshot",
            params={"context": "manual"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["rss_mb"] == 500.0


# =============================================================================
# GET/POST /profiling/config TESTS
# =============================================================================


class TestProfilingConfig:
    """Tests fuer Profiling Config Endpoints."""

    def test_get_config_success(self, test_client, mock_profiling_service):
        """Config erfolgreich abrufen."""
        response = test_client.get("/api/v1/profiling/config")
        assert response.status_code == 200

        data = response.json()
        assert data["profiling_level"] == "basic"
        assert data["slow_request_threshold_ms"] == 1000.0

    def test_update_config_level(self, test_client, mock_profiling_service):
        """Config Level aktualisieren."""
        response = test_client.post(
            "/api/v1/profiling/config",
            json={"level": "detailed"}
        )
        assert response.status_code == 200

    def test_update_config_threshold(self, test_client, mock_profiling_service):
        """Config Threshold aktualisieren."""
        response = test_client.post(
            "/api/v1/profiling/config",
            json={"slow_threshold_ms": 2000.0}
        )
        assert response.status_code == 200

    def test_update_config_invalid_threshold(self, test_client, mock_profiling_service):
        """Ungueltiger Threshold gibt Fehler."""
        response = test_client.post(
            "/api/v1/profiling/config",
            json={"slow_threshold_ms": 0}  # Must be > 0
        )
        assert response.status_code == 422


# =============================================================================
# POST /profiling/reset TESTS
# =============================================================================


class TestResetProfilingStats:
    """Tests fuer POST /profiling/reset Endpoint."""

    def test_reset_success(self, test_client, mock_profiling_service):
        """Stats zuruecksetzen erfolgreich."""
        response = test_client.post("/api/v1/profiling/reset")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "erfolg"
        assert data["geloeschte_endpoints"] == 5


# =============================================================================
# GET /profiling/prometheus TESTS
# =============================================================================


class TestPrometheusMetrics:
    """Tests fuer GET /profiling/prometheus Endpoint."""

    def test_prometheus_metrics(self, test_client):
        """Prometheus Metriken abrufen."""
        response = test_client.get("/api/v1/profiling/prometheus")
        # Prometheus endpoint hat keine Auth
        assert response.status_code == 200


# =============================================================================
# GET /profiling/report TESTS
# =============================================================================


class TestProfilingReport:
    """Tests fuer GET /profiling/report Endpoint."""

    def test_get_report_success(self, test_client, mock_profiling_service):
        """Report erfolgreich generieren."""
        response = test_client.get("/api/v1/profiling/report")
        assert response.status_code == 200

        data = response.json()
        assert "zusammenfassung" in data
        assert "hot_paths" in data
        assert "langsamste_endpoints" in data
        assert "langsame_requests" in data
        assert "memory" in data
        assert "empfehlungen" in data


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================


class TestAuthentication:
    """Tests fuer Authentifizierung."""

    def test_endpoints_require_auth(self, mock_profiling_service):
        """Admin-Endpoints erfordern Authentifizierung."""
        from app.api.v1.profiling import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        # Kein dependency override - sollte 401/403 geben
        with patch("app.api.v1.profiling.get_profiling_service", return_value=mock_profiling_service):
            client = TestClient(app, raise_server_exceptions=False)

            # Diese Endpoints sollten ohne Auth fehlschlagen
            endpoints = [
                "/api/v1/profiling/summary",
                "/api/v1/profiling/endpoints",
                "/api/v1/profiling/slow-requests",
                "/api/v1/profiling/hot-paths",
                "/api/v1/profiling/memory",
                "/api/v1/profiling/config",
                "/api/v1/profiling/report",
            ]

            for endpoint in endpoints:
                response = client.get(endpoint)
                # Ohne Auth sollte 401 oder 403 kommen (je nach Implementation)
                assert response.status_code in [401, 403, 422], f"Endpoint {endpoint} should require auth"


# =============================================================================
# RECOMMENDATIONS TESTS
# =============================================================================


class TestRecommendations:
    """Tests fuer Performance-Empfehlungen."""

    def test_high_error_rate_recommendation(self, test_client, mock_profiling_service):
        """Hohe Fehlerrate sollte Warnung generieren."""
        mock_profiling_service.get_summary.return_value = {
            "status": "aktiv",
            "profiling_level": "basic",
            "uptime_seconds": 3600.0,
            "uptime_formatted": "1:00:00",
            "total_endpoints_tracked": 5,
            "total_requests": 100,
            "total_errors": 10,
            "error_rate_percent": 10.0,  # >5% sollte Warnung geben
            "total_slow_requests": 0,
            "slow_request_threshold_ms": 1000.0,
            "avg_latency_ms": 150.0,
            "p95_latency_ms": 450.0,
            "p99_latency_ms": 800.0,
            "memory_snapshots_count": 0,
            "slow_requests_buffer_count": 0,
        }

        response = test_client.get("/api/v1/profiling/report")
        assert response.status_code == 200

        data = response.json()
        recommendations = data["empfehlungen"]

        # Sollte Warnung fuer Fehlerrate enthalten
        error_warnings = [r for r in recommendations if r["bereich"] == "Fehlerrate"]
        assert len(error_warnings) >= 1
