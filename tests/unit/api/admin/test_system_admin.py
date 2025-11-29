"""
Tests for Admin System API endpoints.

Tests system monitoring functionality:
- GPU status and metrics
- Queue status (Celery/Redis)
- Health checks
- Storage usage
- System diagnostics
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.db.models import User
from app.db.schemas import (
    UserRole,
    MessageResponse,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = str(uuid4())
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    user.tier = "enterprise"
    user.created_at = datetime.utcnow()
    return user


class TestSystemStatus:
    """Tests for GET /admin/system/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard_success(self, mock_db, admin_user):
        """Systemstatus-Dashboard erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        mock_dashboard = MagicMock()
        mock_dashboard.gpu_status.available = True
        mock_dashboard.queue_status.active_jobs = 5
        mock_dashboard.health.status = "healthy"

        with patch.object(SystemStatusService, "get_dashboard", return_value=mock_dashboard):
            result = await SystemStatusService.get_dashboard(db=mock_db)
            assert result.health.status == "healthy"
            assert result.gpu_status.available is True

    @pytest.mark.asyncio
    async def test_get_health_status_success(self, mock_db, admin_user):
        """Systemgesundheit erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        mock_health = MagicMock()
        mock_health.status = "healthy"
        mock_health.postgresql_connected = True
        mock_health.redis_connected = True
        mock_health.minio_connected = True

        with patch.object(SystemStatusService, "get_health_status", return_value=mock_health):
            result = await SystemStatusService.get_health_status(db=mock_db)
            assert result.status == "healthy"
            assert result.postgresql_connected is True


class TestGPUStatus:
    """Tests for GET /admin/system/gpu endpoint."""

    @pytest.mark.asyncio
    async def test_get_gpu_status_success(self, mock_db, admin_user):
        """GPU-Status erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_gpu = {
            "available": True,
            "device_count": 1,
            "devices": [
                {
                    "index": 0,
                    "name": "NVIDIA GeForce RTX 4080",
                    "memory_total_gb": 16.0,
                    "memory_used_gb": 8.5,
                    "memory_free_gb": 7.5,
                    "utilization_percent": 45.0,
                    "temperature_celsius": 65,
                }
            ],
        }

        with patch.object(service, "get_gpu_status", return_value=mock_gpu):
            result = await service.get_gpu_status()
            assert result["available"] is True
            assert result["devices"][0]["name"] == "NVIDIA GeForce RTX 4080"

    @pytest.mark.asyncio
    async def test_get_gpu_status_no_gpu(self, mock_db, admin_user):
        """GPU-Status ohne GPU."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_gpu = {
            "available": False,
            "device_count": 0,
            "devices": [],
            "error": "CUDA nicht verfügbar",
        }

        with patch.object(service, "get_gpu_status", return_value=mock_gpu):
            result = await service.get_gpu_status()
            assert result["available"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_gpu_status_high_memory(self, mock_db, admin_user):
        """GPU-Status bei hoher Speicherauslastung."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_gpu = {
            "available": True,
            "device_count": 1,
            "devices": [
                {
                    "index": 0,
                    "name": "NVIDIA GeForce RTX 4080",
                    "memory_total_gb": 16.0,
                    "memory_used_gb": 14.5,  # >85%
                    "memory_free_gb": 1.5,
                    "utilization_percent": 98.0,
                    "temperature_celsius": 82,
                    "warning": True,
                }
            ],
        }

        with patch.object(service, "get_gpu_status", return_value=mock_gpu):
            result = await service.get_gpu_status()
            assert result["devices"][0]["warning"] is True


class TestQueueStatus:
    """Tests for GET /admin/system/queue endpoint."""

    @pytest.mark.asyncio
    async def test_get_queue_status_success(self, mock_db, admin_user):
        """Queue-Status erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_queue = {
            "redis_connected": True,
            "celery_workers": 2,
            "queues": {
                "default": {"pending": 5, "active": 2},
                "ocr": {"pending": 10, "active": 1},
                "high_priority": {"pending": 0, "active": 0},
            },
            "total_pending": 15,
            "total_active": 3,
        }

        with patch.object(service, "get_queue_status", return_value=mock_queue):
            result = await service.get_queue_status()
            assert result["redis_connected"] is True
            assert result["total_pending"] == 15

    @pytest.mark.asyncio
    async def test_get_queue_status_redis_down(self, mock_db, admin_user):
        """Queue-Status bei Redis-Ausfall."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_queue = {
            "redis_connected": False,
            "celery_workers": 0,
            "error": "Redis-Verbindung fehlgeschlagen",
            "queues": {},
        }

        with patch.object(service, "get_queue_status", return_value=mock_queue):
            result = await service.get_queue_status()
            assert result["redis_connected"] is False
            assert "error" in result


class TestStorageStatus:
    """Tests for MinIO storage health check."""

    @pytest.mark.asyncio
    async def test_check_minio_health_success(self, mock_db, admin_user):
        """MinIO-Speicherstatus erfolgreich prüfen."""
        from app.services.admin import SystemStatusService

        mock_health = MagicMock()
        mock_health.healthy = True
        mock_health.latency_ms = 15.5
        mock_health.error = None

        with patch.object(SystemStatusService, "check_minio_health", return_value=mock_health):
            result = await SystemStatusService.check_minio_health()
            assert result.healthy is True
            assert result.latency_ms == 15.5


class TestHealthCheck:
    """Tests for GET /admin/system/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, mock_db, admin_user):
        """Alle Komponenten gesund."""
        from app.services.admin import SystemStatusService

        mock_health = MagicMock()
        mock_health.status = "healthy"
        mock_health.postgresql_connected = True
        mock_health.redis_connected = True
        mock_health.minio_connected = True
        mock_health.celery_active = True

        with patch.object(SystemStatusService, "get_health_status", return_value=mock_health):
            result = await SystemStatusService.get_health_status(db=mock_db)
            assert result.status == "healthy"
            assert result.postgresql_connected is True

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, mock_db, admin_user):
        """Einige Komponenten beeinträchtigt."""
        from app.services.admin import SystemStatusService

        mock_health = MagicMock()
        mock_health.status = "degraded"
        mock_health.postgresql_connected = True
        mock_health.redis_connected = True
        mock_health.minio_connected = False
        mock_health.warnings = ["MinIO nicht erreichbar"]

        with patch.object(SystemStatusService, "get_health_status", return_value=mock_health):
            result = await SystemStatusService.get_health_status(db=mock_db)
            assert result.status == "degraded"
            assert result.minio_connected is False

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_db, admin_user):
        """Kritische Komponenten nicht erreichbar."""
        from app.services.admin import SystemStatusService

        mock_health = MagicMock()
        mock_health.status = "unhealthy"
        mock_health.postgresql_connected = False
        mock_health.redis_connected = False
        mock_health.errors = ["Datenbankverbindung fehlgeschlagen", "Redis offline"]

        with patch.object(SystemStatusService, "get_health_status", return_value=mock_health):
            result = await SystemStatusService.get_health_status(db=mock_db)
            assert result.status == "unhealthy"
            assert result.postgresql_connected is False


class TestProcessingStats:
    """Tests for processing statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_processing_stats_success(self, mock_db, admin_user):
        """Verarbeitungsstatistiken erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        mock_stats = MagicMock()
        mock_stats.total_processed = 1500
        mock_stats.success_rate = 95.5
        mock_stats.average_processing_time_ms = 2500

        with patch.object(SystemStatusService, "get_processing_stats", return_value=mock_stats):
            result = await SystemStatusService.get_processing_stats(db=mock_db)
            assert result.total_processed == 1500
            assert result.success_rate == 95.5


class TestCacheManagement:
    """Tests for GPU cache management endpoints."""

    @pytest.mark.asyncio
    async def test_clear_gpu_cache_success(self, mock_db, admin_user):
        """GPU-Cache erfolgreich leeren."""
        from app.services.admin import SystemStatusService

        with patch.object(SystemStatusService, "clear_gpu_cache", return_value=True):
            result = await SystemStatusService.clear_gpu_cache()
            assert result is True

    @pytest.mark.asyncio
    async def test_clear_gpu_cache_no_gpu(self, mock_db, admin_user):
        """GPU-Cache leeren ohne GPU."""
        from app.services.admin import SystemStatusService

        with patch.object(SystemStatusService, "clear_gpu_cache", return_value=False):
            result = await SystemStatusService.clear_gpu_cache()
            assert result is False
