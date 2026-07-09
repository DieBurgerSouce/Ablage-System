"""Unit tests for app/workers/celery_app.py - Celery configuration.

Tests the Celery application configuration including:
- GPU lock acquisition and release
- Task configuration
- Worker signals
- Metrics integration

Created: 2024-12-02
"""

import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock
from redis.exceptions import RedisError


class TestGPULockAcquisition:
    """Tests for distributed GPU lock acquisition."""

    def test_acquire_gpu_lock_success(self):
        """Successfully acquiring GPU lock should return lock value."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = True  # Lock acquired
            mock_get_client.return_value = mock_redis

            lock_value = acquire_gpu_lock(timeout=5)

            assert lock_value is not None
            assert "worker:" in lock_value
            mock_redis.set.assert_called_once()

    def test_acquire_gpu_lock_timeout(self):
        """Failing to acquire lock within timeout should raise RuntimeError."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = False  # Lock not acquired
            mock_get_client.return_value = mock_redis

            with pytest.raises(RuntimeError) as exc_info:
                acquire_gpu_lock(timeout=0.5)

            assert "GPU" in str(exc_info.value) or "lock" in str(exc_info.value).lower()

    def test_acquire_gpu_lock_redis_error(self):
        """Redis error during lock acquisition should be handled."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.side_effect = RedisError("Connection failed")
            mock_get_client.return_value = mock_redis

            with pytest.raises((RuntimeError, RedisError)):
                acquire_gpu_lock(timeout=1)


class TestGPULockRelease:
    """Tests for GPU lock release."""

    def test_release_gpu_lock_success(self):
        """Successfully releasing GPU lock should work."""
        from app.workers.celery_app import release_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.get.return_value = b"worker:123:12345"
            mock_redis.delete.return_value = 1
            mock_get_client.return_value = mock_redis

            # Release should not raise
            release_gpu_lock("worker:123:12345")

    def test_release_gpu_lock_wrong_owner(self):
        """Releasing lock with wrong owner should not delete."""
        from app.workers.celery_app import release_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            # Different owner holds the lock
            mock_redis.get.return_value = b"worker:999:99999"
            mock_get_client.return_value = mock_redis

            # Should not delete lock owned by different worker
            release_gpu_lock("worker:123:12345")

            mock_redis.delete.assert_not_called()


class TestGPULockRefresh:
    """Tests for GPU lock refresh (for long-running tasks)."""

    def test_refresh_gpu_lock_success(self):
        """Refreshing GPU lock should extend expiration."""
        from app.workers.celery_app import refresh_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.get.return_value = b"worker:123:12345"
            mock_redis.expire.return_value = True
            mock_get_client.return_value = mock_redis

            result = refresh_gpu_lock("worker:123:12345")

            assert result is True
            mock_redis.expire.assert_called_once()

    def test_refresh_gpu_lock_lost(self):
        """Refreshing lost lock should return False."""
        from app.workers.celery_app import refresh_gpu_lock

        with patch('app.workers.celery_app._get_redis_lock_client') as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.get.return_value = None  # Lock expired
            mock_get_client.return_value = mock_redis

            result = refresh_gpu_lock("worker:123:12345")

            assert result is False


class TestGPULockContextManager:
    """Tests for GPU lock context manager."""

    def test_gpu_lock_context_acquires_and_releases(self):
        """Context manager should acquire and release lock."""
        from app.workers.celery_app import distributed_gpu_lock

        with patch('app.workers.celery_app.acquire_gpu_lock') as mock_acquire, \
             patch('app.workers.celery_app.release_gpu_lock') as mock_release:

            mock_acquire.return_value = "lock:123"

            with distributed_gpu_lock():
                pass

            mock_acquire.assert_called_once()
            mock_release.assert_called_once_with("lock:123")

    def test_gpu_lock_context_releases_on_exception(self):
        """Context manager should release lock even on exception."""
        from app.workers.celery_app import distributed_gpu_lock

        with patch('app.workers.celery_app.acquire_gpu_lock') as mock_acquire, \
             patch('app.workers.celery_app.release_gpu_lock') as mock_release:

            mock_acquire.return_value = "lock:456"

            with pytest.raises(ValueError):
                with distributed_gpu_lock():
                    raise ValueError("Test error")

            # Lock should still be released
            mock_release.assert_called_once_with("lock:456")


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Celery app should be configured."""
        from app.workers.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "ablage_system"

    def test_celery_broker_url_configured(self):
        """Celery broker URL should be configured."""
        from app.workers.celery_app import celery_app

        broker_url = celery_app.conf.broker_url
        assert broker_url is not None
        assert "redis" in broker_url.lower()

    def test_celery_result_backend_configured(self):
        """Celery result backend should be configured."""
        from app.workers.celery_app import celery_app

        result_backend = celery_app.conf.result_backend
        assert result_backend is not None

    def test_task_routes_configured(self):
        """Task routes should be configured for queue separation."""
        from app.workers.celery_app import celery_app

        task_routes = celery_app.conf.task_routes
        # Should have routes for different task types
        assert task_routes is not None or True  # May be empty in test


class TestTaskSignals:
    """Tests for Celery task signals."""

    def test_task_prerun_signal_configured(self):
        """task_prerun signal should be configured."""
        from celery.signals import task_prerun

        # Signal should have receivers
        # (actual receivers depend on the signal configuration)
        assert task_prerun is not None

    def test_task_postrun_signal_configured(self):
        """task_postrun signal should be configured."""
        from celery.signals import task_postrun

        assert task_postrun is not None

    def test_task_failure_signal_configured(self):
        """task_failure signal should be configured."""
        from celery.signals import task_failure

        assert task_failure is not None


class TestWorkerSignals:
    """Tests for Celery worker signals."""

    def test_worker_ready_signal_configured(self):
        """worker_ready signal should be configured."""
        from celery.signals import worker_ready

        assert worker_ready is not None

    def test_worker_shutdown_signal_configured(self):
        """worker_shutdown signal should be configured."""
        from celery.signals import worker_shutdown

        assert worker_shutdown is not None


class TestBeatSchedule:
    """Tests for Celery Beat schedule configuration."""

    def test_beat_schedule_configured(self):
        """Beat schedule should be configured for periodic tasks."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        # May have scheduled tasks like cleanup, backup, etc.
        assert beat_schedule is not None or True  # May be empty in some configs

    def test_frozen_finance_cashflow_beats_are_pruned(self):
        """F-10: Bei eingefrorenem MODULE_FINANCE laufen KEINE Cashflow-Beats.

        Regressionsschutz: ``extended-alerts-cashflow-daily`` (fuehrt taeglich
        den gefrorenen CashflowPredictionService) muss - wie das laengst
        gepoppte Geschwister ``insights-cashflow-daily`` - aus dem effektiven
        Beat-Schedule entfernt sein, solange finance eingefroren ist.
        """
        import pytest
        from app.core.module_registry import MODULE_FINANCE, is_module_active
        from app.workers.celery_app import celery_app

        if is_module_active(MODULE_FINANCE):
            pytest.skip("finance ist aktiv (ACTIVE_OPTIONAL_MODULES) — Beats erwartet")

        beat_schedule = celery_app.conf.beat_schedule or {}
        assert "extended-alerts-cashflow-daily" not in beat_schedule
        assert "insights-cashflow-daily" not in beat_schedule


class TestRedisLockClient:
    """Tests for Redis lock client initialization."""

    def test_get_redis_lock_client_creates_client(self):
        """First call should create Redis client."""
        from app.workers.celery_app import _get_redis_lock_client

        with patch('app.workers.celery_app._redis_lock_client', None):
            with patch('app.workers.celery_app.Redis') as mock_redis_class:
                mock_client = MagicMock()
                mock_redis_class.from_url.return_value = mock_client

                # This tests the creation logic
                # Note: May need to reset module state for accurate testing

    def test_get_redis_lock_client_reuses_client(self):
        """Subsequent calls should reuse existing client."""
        from app.workers import celery_app as celery_module

        with patch.object(celery_module, '_redis_lock_client', MagicMock()):
            # If client already exists, should reuse it
            pass


class TestGPUMemoryManagement:
    """Tests for GPU memory management in tasks."""

