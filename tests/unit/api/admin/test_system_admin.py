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

from app.db.models import User, UserRole
from app.db.schemas import (
    SystemStatusResponse,
    GPUStatusResponse,
    QueueStatusResponse,
    StorageStatusResponse,
    HealthCheckResponse,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return User(
        id=str(uuid4()),
        email="admin@test.de",
        username="admin",
        hashed_password="hashed",
        is_active=True,
        is_superuser=True,
        role=UserRole.ADMIN,
        created_at=datetime.utcnow(),
    )


class TestSystemStatus:
    """Tests for GET /admin/system/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_system_status_success(self, mock_db, admin_user):
        """Systemstatus erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_status = {
            "cpu_percent": 45.2,
            "memory_percent": 62.8,
            "disk_percent": 35.0,
            "uptime_seconds": 86400,
            "timestamp": datetime.utcnow().isoformat(),
        }

        with patch.object(service, "get_system_status", return_value=mock_status):
            result = await service.get_system_status()
            assert result["cpu_percent"] == 45.2
            assert result["memory_percent"] == 62.8

    @pytest.mark.asyncio
    async def test_get_system_status_high_load(self, mock_db, admin_user):
        """Systemstatus bei hoher Last."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_status = {
            "cpu_percent": 95.5,
            "memory_percent": 88.0,
            "disk_percent": 75.0,
            "warning": True,
            "warnings": ["Hohe CPU-Auslastung", "Hohe Speicherauslastung"],
        }

        with patch.object(service, "get_system_status", return_value=mock_status):
            result = await service.get_system_status()
            assert result["warning"] is True
            assert len(result["warnings"]) == 2


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
    """Tests for GET /admin/system/storage endpoint."""

    @pytest.mark.asyncio
    async def test_get_storage_status_success(self, mock_db, admin_user):
        """Speicherstatus erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_storage = {
            "minio_connected": True,
            "buckets": {
                "documents": {
                    "objects": 1500,
                    "size_gb": 25.5,
                },
                "processed": {
                    "objects": 1200,
                    "size_gb": 18.2,
                },
            },
            "total_size_gb": 43.7,
            "quota_gb": 500.0,
            "usage_percent": 8.74,
        }

        with patch.object(service, "get_storage_status", return_value=mock_storage):
            result = await service.get_storage_status()
            assert result["minio_connected"] is True
            assert result["total_size_gb"] == 43.7


class TestHealthCheck:
    """Tests for GET /admin/system/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, mock_db, admin_user):
        """Alle Komponenten gesund."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_health = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "redis": {"status": "healthy", "latency_ms": 2},
                "minio": {"status": "healthy", "latency_ms": 10},
                "celery": {"status": "healthy", "workers": 2},
                "gpu": {"status": "healthy", "memory_percent": 45},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        with patch.object(service, "check_health", return_value=mock_health):
            result = await service.check_health()
            assert result["status"] == "healthy"
            assert all(
                c["status"] == "healthy" for c in result["components"].values()
            )

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, mock_db, admin_user):
        """Einige Komponenten beeinträchtigt."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_health = {
            "status": "degraded",
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "redis": {"status": "degraded", "latency_ms": 150},
                "minio": {"status": "healthy", "latency_ms": 10},
                "celery": {"status": "healthy", "workers": 1},
                "gpu": {"status": "warning", "memory_percent": 88},
            },
            "warnings": ["Redis-Latenz hoch", "GPU-Speicher nahe Limit"],
        }

        with patch.object(service, "check_health", return_value=mock_health):
            result = await service.check_health()
            assert result["status"] == "degraded"
            assert len(result["warnings"]) == 2

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_db, admin_user):
        """Kritische Komponenten nicht erreichbar."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_health = {
            "status": "unhealthy",
            "components": {
                "database": {"status": "unhealthy", "error": "Verbindung abgelehnt"},
                "redis": {"status": "healthy", "latency_ms": 2},
                "minio": {"status": "healthy", "latency_ms": 10},
                "celery": {"status": "unhealthy", "error": "Keine Worker verfügbar"},
                "gpu": {"status": "healthy", "memory_percent": 45},
            },
            "errors": ["Datenbankverbindung fehlgeschlagen", "Celery-Worker offline"],
        }

        with patch.object(service, "check_health", return_value=mock_health):
            result = await service.check_health()
            assert result["status"] == "unhealthy"
            assert len(result["errors"]) == 2


class TestDiagnostics:
    """Tests for GET /admin/system/diagnostics endpoint."""

    @pytest.mark.asyncio
    async def test_get_diagnostics_success(self, mock_db, admin_user):
        """Systemdiagnose erfolgreich abrufen."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        mock_diagnostics = {
            "python_version": "3.11.5",
            "torch_version": "2.1.0",
            "cuda_version": "12.1",
            "environment": "production",
            "config": {
                "max_workers": 4,
                "gpu_memory_limit_percent": 85,
                "ocr_default_backend": "deepseek",
            },
        }

        with patch.object(service, "get_diagnostics", return_value=mock_diagnostics):
            result = await service.get_diagnostics()
            assert result["python_version"] == "3.11.5"
            assert result["cuda_version"] == "12.1"


class TestCacheManagement:
    """Tests for cache management endpoints."""

    @pytest.mark.asyncio
    async def test_clear_cache_success(self, mock_db, admin_user):
        """Cache erfolgreich leeren."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        with patch.object(
            service,
            "clear_cache",
            return_value={"cleared_keys": 150, "freed_memory_mb": 256},
        ):
            result = await service.clear_cache(pattern="*")
            assert result["cleared_keys"] == 150

    @pytest.mark.asyncio
    async def test_clear_cache_pattern(self, mock_db, admin_user):
        """Cache mit Muster leeren."""
        from app.services.admin import SystemStatusService

        service = SystemStatusService()

        with patch.object(
            service,
            "clear_cache",
            return_value={"cleared_keys": 25, "freed_memory_mb": 50},
        ):
            result = await service.clear_cache(pattern="ocr:*")
            assert result["cleared_keys"] == 25
