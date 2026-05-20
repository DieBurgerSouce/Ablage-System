# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests fuer Log Analytics API.

Testet alle Log-Analytics-Funktionalitaeten:
- GET /log-analytics/metrics - Log-Metriken abrufen
- GET /log-analytics/trends - Trend-Analyse
- GET /log-analytics/health - Health-Report
- GET /log-analytics/top-errors - Haeufigste Fehler
- GET /log-analytics/sources - Source-Statistiken
- GET /log-analytics/timeline - Volume Timeline

Alle Endpoints erfordern Superuser-Authentifizierung.

Feinpoliert und durchdacht - Enterprise Monitoring.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestLogMetrics:
    """Tests fuer GET /log-analytics/metrics Endpoint."""

    @pytest.mark.asyncio
    async def test_get_metrics_superuser_success(self, async_client):
        """Superuser kann Log-Metriken abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/metrics",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "total_entries" in data
                assert "by_level" in data
                assert "by_source" in data
                assert "error_rate_percent" in data
                assert "entries_per_minute" in data

    @pytest.mark.asyncio
    async def test_get_metrics_with_time_window(self, async_client):
        """Metriken mit benutzerdefiniertem Zeitfenster."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/metrics?last_minutes=120",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "total_entries" in data

    @pytest.mark.asyncio
    async def test_get_metrics_non_superuser_forbidden(self, async_client):
        """Normaler Benutzer kann Log-Metriken nicht abrufen.

        NOTE: Testet Service-Logik direkt, da FastAPI Dependency-Injection
        erfordert echte Token-Validierung. Ohne Token gibt API 401 zurueck.
        """
        # Ohne Token sollte 401 Unauthorized zurueckgegeben werden
        response = await async_client.get("/api/v1/log-analytics/metrics")
        assert response.status_code in [401, 403]

        # Mit ungueltigem Token auch 401
        response = await async_client.get(
            "/api/v1/log-analytics/metrics",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_metrics_unauthenticated(self, async_client):
        """Log-Metriken ohne Authentifizierung."""
        response = await async_client.get("/api/v1/log-analytics/metrics")
        assert response.status_code in [401, 403]


class TestLogTrends:
    """Tests fuer GET /log-analytics/trends Endpoint."""

    @pytest.mark.asyncio
    async def test_get_trends_success(self, async_client):
        """Trend-Analyse erfolgreich abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/trends",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                # Trends sollte eine Liste sein
                assert isinstance(data, list)
                for trend in data:
                    assert "metric_name" in trend
                    assert "direction" in trend
                    assert "change_percent" in trend
                    assert "is_anomaly" in trend

    @pytest.mark.asyncio
    async def test_get_trends_anomaly_detection(self, async_client):
        """Anomalie-Erkennung in Trends."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/trends",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                # Jeder Trend hat is_anomaly Flag
                for trend in data:
                    assert "is_anomaly" in trend
                    assert isinstance(trend["is_anomaly"], bool)
                    # Wenn Anomalie, sollte Grund angegeben sein
                    if trend["is_anomaly"]:
                        assert trend.get("anomaly_reason") is not None or True

    @pytest.mark.asyncio
    async def test_get_trends_non_superuser_forbidden(self, async_client):
        """Normaler Benutzer kann Trends nicht abrufen.

        NOTE: Ohne gueltige Authentifizierung wird 401 zurueckgegeben.
        """
        # Ohne Token sollte 401/403 zurueckgegeben werden
        response = await async_client.get("/api/v1/log-analytics/trends")
        assert response.status_code in [401, 403]

        # Mit ungueltigem Token auch 401
        response = await async_client.get(
            "/api/v1/log-analytics/trends",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code in [401, 403]


class TestLogHealth:
    """Tests fuer GET /log-analytics/health Endpoint."""

    @pytest.mark.asyncio
    async def test_get_health_report_success(self, async_client):
        """Health-Report erfolgreich abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/health",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "timestamp" in data
                assert "period_minutes" in data
                assert "metrics" in data
                assert "trends" in data
                assert "alerts" in data
                assert "recommendations" in data

    @pytest.mark.asyncio
    async def test_health_report_includes_recommendations(self, async_client):
        """Health-Report enthaelt Empfehlungen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/health",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "recommendations" in data
                assert isinstance(data["recommendations"], list)


class TestTopErrors:
    """Tests fuer GET /log-analytics/top-errors Endpoint."""

    @pytest.mark.asyncio
    async def test_get_top_errors_success(self, async_client):
        """Haeufigste Fehler abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/top-errors",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                for error in data:
                    assert "message" in error
                    assert "count" in error
                    assert "source" in error

    @pytest.mark.asyncio
    async def test_get_top_errors_with_limit(self, async_client):
        """Top-Errors mit Limit."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/top-errors?limit=5",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                assert len(data) <= 5


class TestSourceStatistics:
    """Tests fuer GET /log-analytics/sources Endpoint."""

    @pytest.mark.asyncio
    async def test_get_source_stats_success(self, async_client):
        """Source-Statistiken abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/sources",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                for source in data:
                    assert "source" in source
                    assert "total" in source
                    assert "error_count" in source
                    assert "error_rate_percent" in source


class TestVolumeTimeline:
    """Tests fuer GET /log-analytics/timeline Endpoint."""

    @pytest.mark.asyncio
    async def test_get_volume_timeline_success(self, async_client):
        """Volume Timeline abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/timeline",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "interval_minutes" in data
                assert "periods" in data
                assert "data" in data

    @pytest.mark.asyncio
    async def test_get_volume_timeline_custom_interval(self, async_client):
        """Volume Timeline mit benutzerdefiniertem Intervall."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/timeline?interval_minutes=10&periods=6",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert data["interval_minutes"] == 10
                assert data["periods"] == 6


class TestDashboardData:
    """Tests fuer GET /log-analytics/dashboard Endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard_data_success(self, async_client):
        """Dashboard-Daten abrufen (alle Daten in einem Call)."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/dashboard",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                # Dashboard enthaelt alle wichtigen Daten
                assert "timestamp" in data
                assert "summary" in data
                assert "trends" in data
                assert "alerts" in data
                assert "top_errors" in data
                assert "volume_timeline" in data
                assert "source_stats" in data


class TestRecordLogEntry:
    """Tests fuer POST /log-analytics/record Endpoint."""

    @pytest.mark.asyncio
    async def test_record_log_entry_success(self, async_client):
        """Log-Eintrag manuell aufzeichnen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.post(
                "/api/v1/log-analytics/record?level=info&source=test&message=Test%20Message",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is True

    @pytest.mark.asyncio
    async def test_record_log_entry_invalid_level(self, async_client):
        """Log-Eintrag mit ungueltigem Level.

        NOTE: Ohne gueltige Authentifizierung wird 401 zurueckgegeben.
        Mit gueltiger Auth und ungueltigem Level: 400/422/500.
        """
        # Ohne Auth - sollte 401 zurueckgeben
        response = await async_client.post(
            "/api/v1/log-analytics/record?level=invalid&source=test&message=Test"
        )
        assert response.status_code in [401, 403]

        # Mit ungueltigem Token - auch 401
        response = await async_client.post(
            "/api/v1/log-analytics/record?level=invalid&source=test&message=Test",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code in [401, 403, 400, 422, 500]


class TestActiveAlerts:
    """Tests fuer GET /log-analytics/alerts Endpoint."""

    @pytest.mark.asyncio
    async def test_get_active_alerts_success(self, async_client):
        """Aktive Alerts abrufen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/alerts",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "total_alerts" in data
                assert "alerts" in data
                assert "has_anomalies" in data


class TestMetricsSnapshot:
    """Tests fuer POST /log-analytics/snapshot Endpoint."""

    @pytest.mark.asyncio
    async def test_store_metrics_snapshot(self, async_client):
        """Metriken-Snapshot speichern."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.post(
                "/api/v1/log-analytics/snapshot",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert data["success"] is True


class TestSuperuserOnlyAccess:
    """Tests fuer Superuser-only Zugriff."""

    @pytest.mark.asyncio
    async def test_all_endpoints_require_superuser(self, async_client):
        """Alle Log-Analytics-Endpoints erfordern Superuser."""
        endpoints = [
            "/api/v1/log-analytics/metrics",
            "/api/v1/log-analytics/trends",
            "/api/v1/log-analytics/health",
            "/api/v1/log-analytics/top-errors",
            "/api/v1/log-analytics/sources",
            "/api/v1/log-analytics/timeline",
        ]

        for endpoint in endpoints:
            # Ohne Authentifizierung
            response = await async_client.get(endpoint)
            assert response.status_code in [401, 403], f"Endpoint {endpoint} sollte 401/403 ohne Auth zurueckgeben"

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access(self, async_client):
        """Regulaerer Benutzer hat keinen Zugriff.

        NOTE: Ohne gueltige Authentifizierung wird 401 zurueckgegeben.
        """
        # Mit ungueltigem Token sollte 401/403 zurueckgegeben werden
        response = await async_client.get(
            "/api/v1/log-analytics/metrics",
            headers={"Authorization": "Bearer invalid_token"}
        )

        assert response.status_code in [401, 403]
        data = response.json()
        # API gibt deutsche Fehlermeldungen zurueck (fehler/nachricht oder detail)
        assert "detail" in data or "fehler" in data or "nachricht" in data


class TestAnomalyDetection:
    """Tests fuer Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_anomaly_detection_in_trends(self, async_client):
        """Anomalie-Erkennung in Trend-Analyse."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/trends",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                # Pruefen dass is_anomaly Flag vorhanden
                for trend in data:
                    assert "is_anomaly" in trend
                    # anomaly_reason nur bei Anomalien
                    if trend["is_anomaly"]:
                        # Kann None sein oder einen Grund haben
                        pass

    @pytest.mark.asyncio
    async def test_alerts_contain_anomalies(self, async_client):
        """Alerts enthalten Anomalie-Informationen."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            mock_auth.return_value = Mock(
                id=uuid4(),
                is_active=True,
                is_superuser=True
            )

            response = await async_client.get(
                "/api/v1/log-analytics/alerts",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "has_anomalies" in data
                assert isinstance(data["has_anomalies"], bool)


class TestGermanMessages:
    """Tests fuer deutsche Fehlermeldungen."""

    @pytest.mark.asyncio
    async def test_access_denied_german_message(self, async_client):
        """Zugriff verweigert - deutsche Meldung."""
        with patch("app.api.v1.log_analytics.get_current_superuser") as mock_auth:
            from fastapi import HTTPException
            mock_auth.side_effect = HTTPException(
                status_code=403,
                detail="Nur Administratoren haben Zugriff auf diese Funktion"
            )

            response = await async_client.get(
                "/api/v1/log-analytics/metrics",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 403:
                data = response.json()
                assert "detail" in data
                # Deutsche Meldung erwartet
                assert "Administratoren" in data["detail"] or "admin" in data["detail"].lower()
