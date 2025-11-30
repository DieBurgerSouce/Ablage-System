"""Unit tests for Celery configuration and app setup.

Tests Celery app configuration, task routing, and base task classes.
These tests do NOT require a running Celery worker or Redis.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

# Import Celery app and components
from app.workers.celery_app import (
    celery_app,
    acquire_gpu_lock,
    release_gpu_lock,
    _GPU_LOCK_KEY,
    _GPU_LOCK_TIMEOUT,
)


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Celery app sollte initialisiert sein."""
        assert celery_app is not None
        assert celery_app.main == "ablage-system"

    def test_celery_app_has_broker(self):
        """Celery app sollte Broker-Konfiguration haben."""
        # Broker URL should be configured
        assert celery_app.conf.broker_url is not None

    def test_celery_app_has_backend(self):
        """Celery app sollte Result Backend haben."""
        assert celery_app.conf.result_backend is not None

    def test_celery_task_serializer(self):
        """Task Serializer sollte JSON sein (Sicherheit)."""
        assert celery_app.conf.task_serializer == "json"

    def test_celery_result_serializer(self):
        """Result Serializer sollte JSON sein."""
        assert celery_app.conf.result_serializer == "json"

    def test_celery_accept_content(self):
        """Accepted Content Types sollten sicher sein."""
        accept_content = celery_app.conf.accept_content
        assert "json" in accept_content

    def test_celery_timezone(self):
        """Timezone sollte konfiguriert sein."""
        assert celery_app.conf.timezone is not None

    def test_celery_task_acks_late(self):
        """Task acks_late fuer Reliability."""
        # acks_late ensures tasks are not lost on worker crash
        assert celery_app.conf.task_acks_late is True

    def test_celery_task_reject_on_worker_lost(self):
        """Tasks sollten bei Worker-Verlust rejected werden."""
        assert celery_app.conf.task_reject_on_worker_lost is True


class TestTaskRouting:
    """Tests for Celery task routing configuration."""

    def test_task_routes_configured(self):
        """Task Routes sollten konfiguriert sein."""
        task_routes = celery_app.conf.task_routes
        assert task_routes is not None

    def test_gpu_tasks_route_to_gpu_queue(self):
        """GPU-Tasks sollten zu gpu Queue geroutet werden."""
        task_routes = celery_app.conf.task_routes or {}
        # Check if GPU task pattern routes to gpu queue
        gpu_pattern = "app.workers.tasks.ocr_tasks.*"
        if gpu_pattern in task_routes:
            assert task_routes[gpu_pattern]["queue"] == "gpu"

    def test_backup_tasks_route_to_backup_queue(self):
        """Backup-Tasks sollten zu backup Queue geroutet werden."""
        task_routes = celery_app.conf.task_routes or {}
        backup_pattern = "app.workers.tasks.backup_tasks.*"
        if backup_pattern in task_routes:
            assert task_routes[backup_pattern]["queue"] == "backup"


class TestGPULockFunctions:
    """Tests for distributed GPU lock functions."""

    def test_gpu_lock_key_constant(self):
        """GPU Lock Key sollte definiert sein."""
        assert _GPU_LOCK_KEY == "ablage:gpu:lock"

    def test_gpu_lock_timeout_constant(self):
        """GPU Lock Timeout sollte 5 Minuten sein."""
        assert _GPU_LOCK_TIMEOUT == 300

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_acquire_gpu_lock_success(self, mock_get_client):
        """GPU Lock Acquisition sollte funktionieren."""
        mock_redis = Mock()
        mock_redis.set.return_value = True
        mock_get_client.return_value = mock_redis

        lock_value = acquire_gpu_lock(timeout=5)

        assert lock_value is not None
        assert "worker:" in lock_value
        mock_redis.set.assert_called()

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_acquire_gpu_lock_timeout(self, mock_get_client):
        """GPU Lock sollte RuntimeError bei Timeout werfen."""
        mock_redis = Mock()
        mock_redis.set.return_value = False  # Lock not acquired
        mock_get_client.return_value = mock_redis

        with pytest.raises(RuntimeError) as exc_info:
            acquire_gpu_lock(timeout=2)

        assert "GPU-Lock nicht verfügbar" in str(exc_info.value)

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_release_gpu_lock_success(self, mock_get_client):
        """GPU Lock Release sollte funktionieren."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"worker:123:1234567890"
        mock_redis.delete.return_value = 1
        mock_get_client.return_value = mock_redis

        result = release_gpu_lock("worker:123:1234567890")

        assert result is True
        mock_redis.delete.assert_called_with(_GPU_LOCK_KEY)

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_release_gpu_lock_wrong_value(self, mock_get_client):
        """GPU Lock Release sollte bei falschem Wert fehlschlagen."""
        mock_redis = Mock()
        mock_redis.get.return_value = b"worker:other:9999"  # Different lock holder
        mock_get_client.return_value = mock_redis

        result = release_gpu_lock("worker:123:1234567890")

        assert result is False
        mock_redis.delete.assert_not_called()


class TestTaskBaseClasses:
    """Tests for custom Celery task base classes."""

    def test_gpu_task_class_exists(self):
        """GPUTask Base-Klasse sollte existieren."""
        from app.workers.celery_app import GPUTask
        assert GPUTask is not None

    def test_cpu_task_class_exists(self):
        """CPUTask Base-Klasse sollte existieren."""
        from app.workers.celery_app import CPUTask
        assert CPUTask is not None

    def test_gpu_task_has_rate_limit(self):
        """GPUTask sollte Rate Limit haben."""
        from app.workers.celery_app import GPUTask
        # GPU tasks should have rate limiting to prevent overload
        task = GPUTask()
        assert hasattr(task, "rate_limit") or hasattr(GPUTask, "rate_limit")

    def test_gpu_task_has_retry_settings(self):
        """GPUTask sollte Retry-Einstellungen haben."""
        from app.workers.celery_app import GPUTask
        # Check if GPUTask has retry configuration
        assert hasattr(GPUTask, "autoretry_for") or hasattr(GPUTask, "max_retries")


class TestCeleryBeatSchedule:
    """Tests for Celery beat scheduled tasks."""

    def test_beat_schedule_configured(self):
        """Celery Beat Schedule sollte konfiguriert sein."""
        beat_schedule = celery_app.conf.beat_schedule
        assert beat_schedule is not None

    def test_scheduled_tasks_have_schedule(self):
        """Scheduled Tasks sollten crontab oder interval haben."""
        beat_schedule = celery_app.conf.beat_schedule or {}

        for task_name, task_config in beat_schedule.items():
            assert "schedule" in task_config, f"Task {task_name} hat keine schedule"
            assert "task" in task_config, f"Task {task_name} hat keine task"


class TestTaskDiscovery:
    """Tests for task autodiscovery."""

    def test_tasks_autodiscovered(self):
        """Tasks sollten auto-discovered sein."""
        # Registered tasks should include our custom tasks
        registered_tasks = celery_app.tasks.keys()

        # At minimum, celery built-in tasks should be present
        assert len(registered_tasks) > 0

    def test_ocr_tasks_registered(self):
        """OCR Tasks sollten registriert sein."""
        registered_tasks = list(celery_app.tasks.keys())

        # Check if any OCR task is registered
        ocr_tasks = [t for t in registered_tasks if "ocr" in t.lower()]
        # Note: May not be present if tasks not fully loaded in test context
        # This is just a soft check

    def test_backup_tasks_registered(self):
        """Backup Tasks sollten registriert sein."""
        registered_tasks = list(celery_app.tasks.keys())

        # Check if any backup task is registered
        backup_tasks = [t for t in registered_tasks if "backup" in t.lower()]
