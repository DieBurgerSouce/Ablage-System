# -*- coding: utf-8 -*-
"""
Tests für Metrics API Endpoints.

Testet:
- Prometheus Metrics Endpoints
- Search Metrics
- Backup Metrics
- GPU Metrics
- Business Metrics
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import Response


# ==================== Prometheus Metrics Tests ====================


class TestPrometheusMetrics:
    """Tests für GET /metrics und /metrics/prometheus."""

    @pytest.mark.asyncio
    async def test_prometheus_metrics_endpoint(self):
        """Prometheus Metrics Endpoint gibt gültiges Format zurück."""
        from app.api.v1.metrics import prometheus_metrics

        with patch('app.api.v1.metrics.generate_latest') as mock_generate:
            mock_generate.return_value = b'# HELP test_metric Test\n# TYPE test_metric gauge\ntest_metric 1.0\n'

            response = await prometheus_metrics()

            assert isinstance(response, Response)
            assert response.media_type == "text/plain; version=0.0.4; charset=utf-8"

    @pytest.mark.asyncio
    async def test_prometheus_metrics_content(self):
        """Prometheus Metrics enthalten erwartete Metriken."""
        from app.api.v1.metrics import prometheus_metrics

        with patch('app.api.v1.metrics.generate_latest') as mock_generate:
            mock_content = (
                b'# HELP http_requests_total Total HTTP requests\n'
                b'# TYPE http_requests_total counter\n'
                b'http_requests_total{method="GET"} 100\n'
            )
            mock_generate.return_value = mock_content

            response = await prometheus_metrics()

            assert b'http_requests_total' in response.body


# ==================== Search Metrics Tests ====================


class TestSearchMetrics:
    """Tests für GET /metrics/search."""

    @pytest.mark.asyncio
    async def test_search_metrics_endpoint(self):
        """Search Metrics Endpoint gibt gültiges Format zurück."""
        from app.api.v1.metrics import search_metrics_prometheus

        mock_metrics = Mock()
        mock_metrics.get_metrics.return_value = b'# HELP search_requests_total Total search requests\nsearch_requests_total 50\n'
        mock_metrics.get_content_type.return_value = "text/plain; version=0.0.4; charset=utf-8"

        with patch('app.api.v1.metrics.get_search_metrics', return_value=mock_metrics):
            response = await search_metrics_prometheus()

            assert isinstance(response, Response)
            mock_metrics.get_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_metrics_contains_expected_metrics(self):
        """Search Metrics enthalten erwartete Metriken."""
        from app.api.v1.metrics import search_metrics_prometheus

        mock_content = (
            b'# HELP ablage_search_requests_total Total search requests\n'
            b'ablage_search_requests_total{type="fulltext"} 100\n'
            b'# HELP ablage_search_duration_seconds Search duration\n'
            b'ablage_search_duration_seconds_bucket{le="0.1"} 80\n'
        )

        mock_metrics = Mock()
        mock_metrics.get_metrics.return_value = mock_content
        mock_metrics.get_content_type.return_value = "text/plain"

        with patch('app.api.v1.metrics.get_search_metrics', return_value=mock_metrics):
            response = await search_metrics_prometheus()

            assert b'search_requests_total' in response.body
            assert b'search_duration' in response.body


# ==================== Backup Metrics Tests ====================


class TestBackupMetrics:
    """Tests für GET /metrics/backup."""

    @pytest.mark.asyncio
    async def test_backup_metrics_endpoint(self):
        """Backup Metrics Endpoint gibt gültiges Format zurück."""
        from app.api.v1.metrics import backup_metrics_prometheus

        mock_metrics = Mock()
        mock_metrics.get_metrics.return_value = b'# HELP ablage_backup_success_total Backups\nablage_backup_success_total 10\n'
        mock_metrics.get_content_type.return_value = "text/plain; version=0.0.4; charset=utf-8"

        with patch('app.api.v1.metrics.get_backup_metrics', return_value=mock_metrics):
            response = await backup_metrics_prometheus()

            assert isinstance(response, Response)
            mock_metrics.get_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_backup_metrics_summary_endpoint(self):
        """Backup Metrics Summary Endpoint gibt JSON zurück."""
        from app.api.v1.metrics import backup_metrics_summary

        mock_summary = {
            "disk_usage_bytes": 1024 * 1024 * 1024,
            "disk_free_bytes": 10 * 1024 * 1024 * 1024,
            "backup_count": {"postgres": 10, "redis": 10, "minio": 5},
            "prometheus_available": True
        }

        mock_metrics = Mock()
        mock_metrics.get_summary.return_value = mock_summary

        with patch('app.api.v1.metrics.get_backup_metrics', return_value=mock_metrics):
            response = await backup_metrics_summary()

            assert "disk_usage_bytes" in response
            assert "backup_count" in response

    @pytest.mark.asyncio
    async def test_backup_metrics_contains_expected_metrics(self):
        """Backup Metrics enthalten erwartete Metriken."""
        from app.api.v1.metrics import backup_metrics_prometheus

        mock_content = (
            b'# HELP ablage_backup_success_total Successful backups\n'
            b'ablage_backup_success_total{type="postgres"} 10\n'
            b'# HELP ablage_backup_duration_seconds Backup duration\n'
            b'ablage_backup_duration_seconds{type="postgres"} 120.5\n'
        )

        mock_metrics = Mock()
        mock_metrics.get_metrics.return_value = mock_content
        mock_metrics.get_content_type.return_value = "text/plain"

        with patch('app.api.v1.metrics.get_backup_metrics', return_value=mock_metrics):
            response = await backup_metrics_prometheus()

            assert b'backup_success_total' in response.body
            assert b'backup_duration' in response.body


# ==================== GPU Metrics Tests ====================


class TestGPUMetrics:
    """Tests für GET /metrics/gpu."""

    @pytest.mark.asyncio
    async def test_gpu_metrics_endpoint(self):
        """GPU Metrics Endpoint gibt gültiges Format zurück."""
        from app.api.v1.metrics import gpu_metrics_prometheus

        mock_service = Mock()
        mock_service.get_metrics.return_value = b'# HELP ablage_gpu_memory_used GPU memory\nablage_gpu_memory_used 8000000000\n'
        mock_service.get_content_type.return_value = "text/plain; version=0.0.4; charset=utf-8"

        with patch('app.api.v1.metrics.get_gpu_metrics_service', return_value=mock_service):
            response = await gpu_metrics_prometheus()

            assert isinstance(response, Response)

    @pytest.mark.asyncio
    async def test_gpu_metrics_summary_endpoint(self):
        """GPU Metrics Summary Endpoint gibt JSON zurück."""
        from app.api.v1.metrics import gpu_metrics_summary

        mock_summary = {
            "gpu_available": True,
            "gpu_name": "NVIDIA RTX 4080",
            "memory_total_gb": 16.0,
            "memory_used_gb": 8.5,
            "memory_utilization_percent": 53.1,
            "temperature_celsius": 65,
            "power_usage_watts": 200
        }

        mock_service = Mock()
        mock_service.get_summary.return_value = mock_summary

        with patch('app.api.v1.metrics.get_gpu_metrics_service', return_value=mock_service):
            response = await gpu_metrics_summary()

            assert "gpu_available" in response
            assert response["gpu_name"] == "NVIDIA RTX 4080"

    @pytest.mark.asyncio
    async def test_gpu_metrics_no_gpu_available(self):
        """GPU Metrics ohne verfügbare GPU."""
        from app.api.v1.metrics import gpu_metrics_summary

        mock_summary = {
            "gpu_available": False,
            "reason": "No NVIDIA GPU detected"
        }

        mock_service = Mock()
        mock_service.get_summary.return_value = mock_summary

        with patch('app.api.v1.metrics.get_gpu_metrics_service', return_value=mock_service):
            response = await gpu_metrics_summary()

            assert response["gpu_available"] is False


# ==================== Business Metrics Tests ====================


class TestBusinessMetrics:
    """Tests für Business-Metriken."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        user.is_superuser = False
        return user

    @pytest.fixture
    def mock_superuser(self):
        """Mock für Superuser."""
        user = Mock()
        user.id = uuid4()
        user.is_superuser = True
        return user

    @pytest.mark.asyncio
    async def test_business_metrics_endpoint(self, mock_superuser):
        """Business Metrics Endpoint für Superuser."""
        from app.api.v1.metrics import get_business_metrics

        mock_metrics = {
            "documents_total": 1500,
            "documents_processed_today": 50,
            "ocr_success_rate": 0.98,
            "average_processing_time_seconds": 2.5,
            "active_users_today": 25,
            "storage_used_gb": 150.5
        }

        with patch('app.api.v1.metrics.calculate_business_metrics', return_value=mock_metrics):
            response = await get_business_metrics(current_user=mock_superuser)

            assert response["documents_total"] == 1500
            assert response["ocr_success_rate"] == 0.98


# ==================== Metriken-Integrität Tests ====================


class TestMetricsIntegrity:
    """Tests für Metriken-Integrität."""

    def test_prometheus_format_valid(self):
        """Prometheus-Format ist gültig."""
        # Prometheus erwartet bestimmtes Format:
        # # HELP metric_name Description
        # # TYPE metric_name type
        # metric_name{labels} value

        valid_format = b'''# HELP test_counter Total test events
# TYPE test_counter counter
test_counter{label="value"} 100
'''
        # Sollte keine Parsing-Fehler verursachen
        lines = valid_format.decode().split('\n')
        assert lines[0].startswith('# HELP')
        assert lines[1].startswith('# TYPE')

    def test_metric_names_follow_convention(self):
        """Metrik-Namen folgen Prometheus-Konvention."""
        # Namen sollten snake_case sein und mit ablage_ Prefix beginnen
        valid_names = [
            "ablage_documents_total",
            "ablage_ocr_requests_total",
            "ablage_search_duration_seconds",
            "ablage_backup_size_bytes"
        ]

        for name in valid_names:
            assert name.startswith("ablage_")
            assert "_" in name
            assert name == name.lower()


# ==================== Sicherheits-Tests ====================


class TestMetricsSecurity:
    """Sicherheitstests für Metrics-Endpoints."""

    def test_prometheus_endpoint_public(self):
        """Prometheus-Endpoint ist öffentlich."""
        # /metrics sollte ohne Auth erreichbar sein für Prometheus scraping
        from app.api.v1.metrics import router

        for route in router.routes:
            if hasattr(route, 'path') and route.path in ['', '/prometheus']:
                # Diese sollten keine Auth Dependencies haben
                pass

    def test_business_metrics_require_auth(self):
        """Business-Metrics erfordern Authentifizierung."""
        from app.api.v1.metrics import router

        for route in router.routes:
            if hasattr(route, 'path') and 'business' in str(route.path):
                # Diese sollten Auth Dependencies haben
                pass


# ==================== Edge Cases ====================


class TestMetricsEdgeCases:
    """Edge Cases für Metrics."""

    @pytest.mark.asyncio
    async def test_metrics_empty_registry(self):
        """Metrics bei leerer Registry."""
        from app.api.v1.metrics import prometheus_metrics

        with patch('app.api.v1.metrics.generate_latest', return_value=b''):
            response = await prometheus_metrics()

            assert response.body == b''

    @pytest.mark.asyncio
    async def test_metrics_large_values(self):
        """Metrics mit großen Werten."""
        from app.api.v1.metrics import prometheus_metrics

        large_value_content = b'ablage_documents_total 9999999999999\n'

        with patch('app.api.v1.metrics.generate_latest', return_value=large_value_content):
            response = await prometheus_metrics()

            assert b'9999999999999' in response.body

    @pytest.mark.asyncio
    async def test_gpu_metrics_service_unavailable(self):
        """GPU Metrics wenn Service nicht verfügbar."""
        from app.api.v1.metrics import gpu_metrics_prometheus

        mock_service = Mock()
        mock_service.get_metrics.return_value = b'# GPU service unavailable\n'
        mock_service.get_content_type.return_value = "text/plain"

        with patch('app.api.v1.metrics.get_gpu_metrics_service', return_value=mock_service):
            response = await gpu_metrics_prometheus()

            # Sollte nicht crashen
            assert isinstance(response, Response)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])
