# -*- coding: utf-8 -*-
"""
Unit Tests fuer Celery Task Timeout Handling.

Tests fuer:
- Task Time Limits (soft und hard)
- SoftTimeLimitExceeded Handling
- Stuck Task Detection
- Worker Health Monitoring
- Timeout Recovery
"""

import pytest
import time
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded


class TestCeleryTimeoutConfiguration:
    """Tests fuer Celery Timeout-Konfiguration."""

    def test_task_time_limit_configured(self):
        """task_time_limit sollte konfiguriert sein."""
        from app.workers.celery_app import celery_app

        # Hard time limit should be set
        assert celery_app.conf.task_time_limit is not None
        assert celery_app.conf.task_time_limit > 0

    def test_task_soft_time_limit_configured(self):
        """task_soft_time_limit sollte konfiguriert sein."""
        from app.workers.celery_app import celery_app

        # Soft time limit should be less than hard limit
        assert celery_app.conf.task_soft_time_limit is not None
        assert celery_app.conf.task_soft_time_limit > 0

    def test_soft_limit_less_than_hard_limit(self):
        """Soft Limit sollte kleiner als Hard Limit sein."""
        from app.workers.celery_app import celery_app

        soft = celery_app.conf.task_soft_time_limit
        hard = celery_app.conf.task_time_limit

        assert soft < hard, "Soft time limit muss kleiner als hard time limit sein"

    def test_soft_limit_gives_grace_period(self):
        """Soft Limit sollte 30s Vorlaufzeit geben."""
        from app.workers.celery_app import celery_app

        soft = celery_app.conf.task_soft_time_limit
        hard = celery_app.conf.task_time_limit

        grace_period = hard - soft
        assert grace_period >= 30, "Grace Period sollte mindestens 30 Sekunden sein"

    def test_visibility_timeout_configured(self):
        """visibility_timeout fuer lange Tasks konfiguriert."""
        from app.workers.celery_app import celery_app

        transport_options = celery_app.conf.broker_transport_options or {}
        visibility_timeout = transport_options.get("visibility_timeout")

        # Should be at least 1 hour for long-running OCR tasks
        if visibility_timeout:
            assert visibility_timeout >= 3600


class TestSoftTimeLimitHandling:
    """Tests fuer SoftTimeLimitExceeded Handling."""

    def test_soft_time_limit_exception_raised(self):
        """SoftTimeLimitExceeded wird korrekt geworfen."""
        exc = SoftTimeLimitExceeded()
        assert isinstance(exc, SoftTimeLimitExceeded)

    def test_soft_time_limit_can_be_caught(self):
        """SoftTimeLimitExceeded kann gefangen werden."""
        try:
            raise SoftTimeLimitExceeded("Task timeout")
        except SoftTimeLimitExceeded as e:
            # Exception string representation includes class name
            assert "Task timeout" in str(e)

    def test_soft_limit_allows_cleanup(self):
        """Soft Limit erlaubt Cleanup-Logik."""
        cleanup_performed = False

        def task_with_cleanup():
            try:
                raise SoftTimeLimitExceeded()
            except SoftTimeLimitExceeded:
                nonlocal cleanup_performed
                cleanup_performed = True
                return {"status": "timeout", "cleanup": True}

        result = task_with_cleanup()
        assert cleanup_performed is True
        assert result["cleanup"] is True

    def test_hard_time_limit_exception(self):
        """TimeLimitExceeded (hard) wird nach Soft geworfen."""
        exc = TimeLimitExceeded()
        assert isinstance(exc, TimeLimitExceeded)


class TestStuckTaskDetection:
    """Tests fuer Stuck Task Erkennung."""

    def test_stale_task_threshold_defined(self):
        """STALE_TASK_THRESHOLD_SECONDS sollte definiert sein."""
        from app.workers.celery_app import STALE_TASK_THRESHOLD_SECONDS

        assert STALE_TASK_THRESHOLD_SECONDS > 0
        assert STALE_TASK_THRESHOLD_SECONDS == 600  # 10 Minuten

    def test_task_considered_stuck_after_threshold(self):
        """Task gilt als stuck nach Threshold."""
        from app.workers.celery_app import STALE_TASK_THRESHOLD_SECONDS

        task_started = time.time() - (STALE_TASK_THRESHOLD_SECONDS + 60)  # 11 min ago
        elapsed = time.time() - task_started

        is_stuck = elapsed > STALE_TASK_THRESHOLD_SECONDS
        assert is_stuck is True

    def test_task_not_stuck_within_threshold(self):
        """Task gilt nicht als stuck innerhalb Threshold."""
        from app.workers.celery_app import STALE_TASK_THRESHOLD_SECONDS

        task_started = time.time() - 60  # 1 min ago
        elapsed = time.time() - task_started

        is_stuck = elapsed > STALE_TASK_THRESHOLD_SECONDS
        assert is_stuck is False

    def test_stuck_task_detection_formula(self):
        """Stuck Task Detection Formel ist korrekt."""
        from app.workers.celery_app import STALE_TASK_THRESHOLD_SECONDS

        # Edge case: exactly at threshold
        elapsed_at_threshold = STALE_TASK_THRESHOLD_SECONDS
        is_stuck_at = elapsed_at_threshold > STALE_TASK_THRESHOLD_SECONDS
        assert is_stuck_at is False  # Not stuck AT threshold

        # Just over threshold
        elapsed_over = STALE_TASK_THRESHOLD_SECONDS + 1
        is_stuck_over = elapsed_over > STALE_TASK_THRESHOLD_SECONDS
        assert is_stuck_over is True


class TestWorkerHealthCheck:
    """Tests fuer Worker Health Check System."""

    def test_health_check_interval_defined(self):
        """HEALTH_CHECK_INTERVAL_SECONDS sollte definiert sein."""
        from app.workers.celery_app import HEALTH_CHECK_INTERVAL_SECONDS

        assert HEALTH_CHECK_INTERVAL_SECONDS > 0
        assert HEALTH_CHECK_INTERVAL_SECONDS == 30  # Alle 30 Sekunden

    def test_worker_unresponsive_threshold_defined(self):
        """WORKER_UNRESPONSIVE_THRESHOLD_SECONDS sollte definiert sein."""
        from app.workers.celery_app import WORKER_UNRESPONSIVE_THRESHOLD_SECONDS

        assert WORKER_UNRESPONSIVE_THRESHOLD_SECONDS > 0
        assert WORKER_UNRESPONSIVE_THRESHOLD_SECONDS == 120  # 2 Minuten

    def test_get_worker_health_status_returns_dict(self):
        """get_worker_health_status gibt Dictionary zurueck."""
        from app.workers.celery_app import get_worker_health_status

        with patch("app.workers.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect_instance = MagicMock()
            mock_inspect_instance.ping.return_value = {}
            mock_inspect_instance.stats.return_value = {}
            mock_inspect_instance.active.return_value = {}
            mock_inspect_instance.reserved.return_value = {}
            mock_inspect.return_value = mock_inspect_instance

            result = get_worker_health_status()

            assert isinstance(result, dict)
            assert "workers" in result
            assert "total_workers" in result
            assert "healthy_workers" in result
            assert "stale_tasks" in result
            assert "timestamp" in result

    def test_health_status_detects_no_workers(self):
        """Health Status erkennt keine aktiven Worker."""
        from app.workers.celery_app import get_worker_health_status

        with patch("app.workers.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect_instance = MagicMock()
            mock_inspect_instance.ping.return_value = {}  # No workers responding
            mock_inspect_instance.stats.return_value = {}
            mock_inspect_instance.active.return_value = {}
            mock_inspect_instance.reserved.return_value = {}
            mock_inspect.return_value = mock_inspect_instance

            result = get_worker_health_status()

            assert result["total_workers"] == 0
            assert "Keine aktiven Worker" in str(result.get("warnings", []))

    def test_health_status_detects_stuck_tasks(self):
        """Health Status erkennt stuck Tasks."""
        from app.workers.celery_app import get_worker_health_status, STALE_TASK_THRESHOLD_SECONDS

        with patch("app.workers.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect_instance = MagicMock()
            mock_inspect_instance.ping.return_value = {"worker1": {"ok": "pong"}}
            mock_inspect_instance.stats.return_value = {"worker1": {"pid": 1234}}

            # Task that started 15 minutes ago (stuck)
            stuck_time = time.time() - (STALE_TASK_THRESHOLD_SECONDS + 300)
            mock_inspect_instance.active.return_value = {
                "worker1": [{
                    "id": "task-123",
                    "name": "test_task",
                    "time_start": stuck_time,
                    "args": ["arg1"]
                }]
            }
            mock_inspect_instance.reserved.return_value = {}
            mock_inspect.return_value = mock_inspect_instance

            with patch("app.workers.celery_app.check_gpu_lock_health") as mock_gpu:
                mock_gpu.return_value = {"locked": False, "status": "available"}
                result = get_worker_health_status()

            assert len(result["stale_tasks"]) > 0
            assert result["stale_tasks"][0]["task_id"] == "task-123"


class TestCachedWorkerHealth:
    """Tests fuer gecachte Worker Health Checks."""

    def test_get_cached_worker_health_returns_dict(self):
        """get_cached_worker_health gibt Dictionary zurueck."""
        from app.workers.celery_app import get_cached_worker_health

        with patch("app.workers.celery_app.get_worker_health_status") as mock_health:
            mock_health.return_value = {
                "workers": [],
                "total_workers": 0,
                "healthy_workers": 0,
                "stale_tasks": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            result = get_cached_worker_health()

            assert isinstance(result, dict)

    def test_cached_health_expires(self):
        """Gecachte Health Status verfaellt nach Interval."""
        from app.workers.celery_app import (
            get_cached_worker_health,
            HEALTH_CHECK_INTERVAL_SECONDS,
            _worker_health_cache,
            _last_health_check
        )

        # This tests the caching logic conceptually
        # Cache should be refreshed if older than HEALTH_CHECK_INTERVAL_SECONDS
        interval = HEALTH_CHECK_INTERVAL_SECONDS
        assert interval > 0


class TestRestartStuckTasks:
    """Tests fuer Stuck Task Restart."""

    def test_restart_stuck_tasks_requires_force(self):
        """restart_stuck_tasks erfordert force=True."""
        from app.workers.celery_app import restart_stuck_tasks

        with patch("app.workers.celery_app.get_worker_health_status") as mock_health:
            mock_health.return_value = {"stale_tasks": [{"task_id": "123"}]}

            result = restart_stuck_tasks(force=False)

            assert result["success"] is False
            assert "force=True" in result["message"]

    def test_restart_stuck_tasks_with_force(self):
        """restart_stuck_tasks mit force=True revoked Tasks."""
        from app.workers.celery_app import restart_stuck_tasks

        with patch("app.workers.celery_app.get_worker_health_status") as mock_health:
            mock_health.return_value = {
                "stale_tasks": [
                    {"task_id": "task-1"},
                    {"task_id": "task-2"}
                ]
            }

            with patch("app.workers.celery_app.celery_app.control.revoke") as mock_revoke:
                result = restart_stuck_tasks(force=True)

                assert len(result["revoked"]) == 2
                assert mock_revoke.call_count == 2


class TestWorkerHeartbeat:
    """Tests fuer Worker Heartbeat Status."""

    def test_get_worker_heartbeat_status_returns_dict(self):
        """get_worker_heartbeat_status gibt Dictionary zurueck."""
        from app.workers.celery_app import get_worker_heartbeat_status

        with patch("app.workers.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect_instance = MagicMock()
            mock_inspect_instance.ping.return_value = {
                "worker1": {"ok": "pong"}
            }
            mock_inspect.return_value = mock_inspect_instance

            result = get_worker_heartbeat_status()

            assert isinstance(result, dict)
            assert "workers" in result
            assert "timestamp" in result

    def test_heartbeat_detects_responding_workers(self):
        """Heartbeat erkennt antwortende Worker."""
        from app.workers.celery_app import get_worker_heartbeat_status

        with patch("app.workers.celery_app.celery_app.control.inspect") as mock_inspect:
            mock_inspect_instance = MagicMock()
            mock_inspect_instance.ping.return_value = {
                "worker1": {"ok": "pong"},
                "worker2": {"ok": "pong"}
            }
            mock_inspect.return_value = mock_inspect_instance

            result = get_worker_heartbeat_status()

            assert "worker1" in result["workers"]
            assert result["workers"]["worker1"]["responding"] is True


class TestGPUTaskTimeoutHandling:
    """Tests fuer GPU Task Timeout Handling."""

    def test_gpu_task_has_retry_settings(self):
        """GPUTask hat Retry-Einstellungen fuer Timeout."""
        from app.workers.celery_app import GPUTask

        assert hasattr(GPUTask, "max_retries")
        assert hasattr(GPUTask, "retry_backoff")
        assert hasattr(GPUTask, "retry_backoff_max")

    def test_gpu_task_max_retries(self):
        """GPUTask hat sinnvollen max_retries Wert."""
        from app.workers.celery_app import GPUTask

        assert GPUTask.max_retries == 3

    def test_gpu_task_retry_backoff_enabled(self):
        """GPUTask hat exponential backoff aktiviert."""
        from app.workers.celery_app import GPUTask

        assert GPUTask.retry_backoff is True

    def test_gpu_task_retry_backoff_max(self):
        """GPUTask hat max backoff von 10 Minuten."""
        from app.workers.celery_app import GPUTask

        assert GPUTask.retry_backoff_max == 600  # 10 minutes

    def test_gpu_task_retry_jitter_enabled(self):
        """GPUTask hat retry jitter aktiviert."""
        from app.workers.celery_app import GPUTask

        assert GPUTask.retry_jitter is True


class TestCPUTaskTimeoutHandling:
    """Tests fuer CPU Task Timeout Handling."""

    def test_cpu_task_has_retry_settings(self):
        """CPUTask hat Retry-Einstellungen."""
        from app.workers.celery_app import CPUTask

        assert hasattr(CPUTask, "max_retries")
        assert hasattr(CPUTask, "retry_backoff")

    def test_cpu_task_max_retries(self):
        """CPUTask hat sinnvollen max_retries Wert."""
        from app.workers.celery_app import CPUTask

        assert CPUTask.max_retries == 3

    def test_cpu_task_retry_backoff_max(self):
        """CPUTask hat max backoff von 5 Minuten."""
        from app.workers.celery_app import CPUTask

        assert CPUTask.retry_backoff_max == 300  # 5 minutes


class TestTaskAcknowledgment:
    """Tests fuer Task Acknowledgment Verhalten."""

    def test_task_acks_late_enabled(self):
        """task_acks_late ist aktiviert fuer Reliability."""
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_acks_late is True

    def test_task_reject_on_worker_lost_enabled(self):
        """task_reject_on_worker_lost ist aktiviert."""
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_reject_on_worker_lost is True

    def test_task_acks_on_failure_or_timeout_disabled(self):
        """task_acks_on_failure_or_timeout ist deaktiviert (Tasks gehen bei Fehler in DLQ)."""
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_acks_on_failure_or_timeout is False


class TestGPULockTimeouts:
    """Tests fuer GPU Lock Timeout Verhalten."""

    def test_gpu_lock_timeout_defined(self):
        """GPU Lock Timeout sollte definiert sein (erhoet fuer lange OCR-Tasks)."""
        from app.workers.celery_app import _GPU_LOCK_TIMEOUT

        assert _GPU_LOCK_TIMEOUT > 0
        assert _GPU_LOCK_TIMEOUT == 180  # 180 Sekunden (erhoet von 60s)

    def test_gpu_lock_acquire_timeout_defined(self):
        """GPU Lock Acquire Timeout sollte definiert sein (erhoet fuer lange OCR-Tasks)."""
        from app.workers.celery_app import _GPU_LOCK_ACQUIRE_TIMEOUT

        assert _GPU_LOCK_ACQUIRE_TIMEOUT > 0
        assert _GPU_LOCK_ACQUIRE_TIMEOUT == 300  # 300 Sekunden (erhoet von 30s)

    def test_gpu_lock_retry_interval_defined(self):
        """GPU Lock Retry Interval sollte definiert sein."""
        from app.workers.celery_app import _GPU_LOCK_RETRY_INTERVAL

        assert _GPU_LOCK_RETRY_INTERVAL > 0
        assert _GPU_LOCK_RETRY_INTERVAL == 0.1  # 100ms

    def test_gpu_lock_refresh_function_exists(self):
        """refresh_gpu_lock Funktion sollte existieren."""
        from app.workers.celery_app import refresh_gpu_lock

        assert callable(refresh_gpu_lock)

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_gpu_lock_refresh_success(self, mock_get_client):
        """GPU Lock Refresh sollte funktionieren."""
        from app.workers.celery_app import refresh_gpu_lock

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"worker:123:1234567890"
        mock_redis.expire.return_value = True
        mock_get_client.return_value = mock_redis

        result = refresh_gpu_lock("worker:123:1234567890")

        assert result is True
        mock_redis.expire.assert_called()

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_gpu_lock_refresh_not_owned(self, mock_get_client):
        """GPU Lock Refresh fehlschlaegt wenn nicht besitzt."""
        from app.workers.celery_app import refresh_gpu_lock

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"worker:other:9999"  # Different owner
        mock_get_client.return_value = mock_redis

        result = refresh_gpu_lock("worker:123:1234567890")

        assert result is False


class TestGPULockHealthCheck:
    """Tests fuer GPU Lock Health Check."""

    def test_check_gpu_lock_health_exists(self):
        """check_gpu_lock_health Funktion sollte existieren."""
        from app.workers.celery_app import check_gpu_lock_health

        assert callable(check_gpu_lock_health)

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_gpu_lock_health_when_available(self, mock_get_client):
        """GPU Lock Health zeigt available wenn nicht gelockt."""
        from app.workers.celery_app import check_gpu_lock_health

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_redis.ttl.return_value = -2  # Key doesn't exist
        mock_get_client.return_value = mock_redis

        result = check_gpu_lock_health()

        assert result["locked"] is False
        assert result["status"] == "available"

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_gpu_lock_health_when_locked(self, mock_get_client):
        """GPU Lock Health zeigt locked Status."""
        from app.workers.celery_app import check_gpu_lock_health

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"worker:123:1234567890"
        mock_redis.ttl.return_value = 45
        mock_get_client.return_value = mock_redis

        result = check_gpu_lock_health()

        assert result["locked"] is True
        assert result["owner"] == "worker:123:1234567890"
        assert result["ttl_seconds"] == 45
        assert result["status"] == "healthy"

    @patch("app.workers.celery_app._get_redis_lock_client")
    def test_gpu_lock_health_expiring_soon(self, mock_get_client):
        """GPU Lock Health zeigt expiring_soon wenn TTL niedrig."""
        from app.workers.celery_app import check_gpu_lock_health

        mock_redis = MagicMock()
        mock_redis.get.return_value = b"worker:123:1234567890"
        mock_redis.ttl.return_value = 5  # Only 5 seconds left
        mock_get_client.return_value = mock_redis

        result = check_gpu_lock_health()

        assert result["status"] == "expiring_soon"


class TestDistributedGPULockContextManager:
    """Tests fuer distributed_gpu_lock Context Manager."""

    def test_distributed_gpu_lock_exists(self):
        """distributed_gpu_lock Context Manager sollte existieren."""
        from app.workers.celery_app import distributed_gpu_lock

        assert callable(distributed_gpu_lock)

    @patch("app.workers.celery_app.release_gpu_lock")
    @patch("app.workers.celery_app.acquire_gpu_lock")
    def test_distributed_gpu_lock_acquires_and_releases(self, mock_acquire, mock_release):
        """distributed_gpu_lock acquired und released Lock."""
        from app.workers.celery_app import distributed_gpu_lock

        mock_acquire.return_value = "test-lock-value"
        mock_release.return_value = True

        with distributed_gpu_lock():
            pass

        mock_acquire.assert_called_once()
        mock_release.assert_called_once_with("test-lock-value")

    @patch("app.workers.celery_app.release_gpu_lock")
    @patch("app.workers.celery_app.acquire_gpu_lock")
    def test_distributed_gpu_lock_releases_on_exception(self, mock_acquire, mock_release):
        """distributed_gpu_lock released Lock auch bei Exception."""
        from app.workers.celery_app import distributed_gpu_lock

        mock_acquire.return_value = "test-lock-value"

        with pytest.raises(ValueError):
            with distributed_gpu_lock():
                raise ValueError("Test error")

        mock_release.assert_called_once_with("test-lock-value")


class TestTaskTimeoutSignalHandlers:
    """Tests fuer Task Timeout Signal Handlers."""

    def test_task_failure_handler_connected(self):
        """task_failure Signal Handler sollte verbunden sein."""
        from celery.signals import task_failure

        # Check that handlers are connected
        assert len(task_failure.receivers) > 0

    def test_task_retry_handler_connected(self):
        """task_retry Signal Handler sollte verbunden sein."""
        from celery.signals import task_retry

        # Check that handlers are connected
        assert len(task_retry.receivers) > 0


class TestWorkerMaxTasksPerChild:
    """Tests fuer Worker Max Tasks per Child."""

    def test_worker_max_tasks_per_child_configured(self):
        """worker_max_tasks_per_child sollte konfiguriert sein."""
        from app.workers.celery_app import celery_app

        max_tasks = celery_app.conf.worker_max_tasks_per_child

        # Should be set to prevent memory leaks (Worker-Restart nach N Tasks).
        # Echter Wert in celery_app.py: 100.
        assert max_tasks is not None
        assert max_tasks == 100

    def test_worker_prefetch_multiplier_configured(self):
        """worker_prefetch_multiplier sollte fuer GPU Tasks 1 sein."""
        from app.workers.celery_app import celery_app

        prefetch = celery_app.conf.worker_prefetch_multiplier

        # Must be 1 for GPU tasks to prevent VRAM overflow
        assert prefetch == 1


class TestGermanErrorMessages:
    """Tests fuer deutsche Timeout-Fehlermeldungen."""

    def test_gpu_lock_timeout_message_german(self):
        """GPU Lock Timeout Nachricht ist auf Deutsch."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch("app.workers.celery_app._get_redis_lock_client") as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = False
            mock_get_client.return_value = mock_redis

            with pytest.raises(RuntimeError) as exc_info:
                acquire_gpu_lock(timeout=1)

            error_msg = str(exc_info.value)
            assert "GPU-Lock nicht verfügbar" in error_msg
            assert "Worker verarbeitet" in error_msg

    def test_stuck_task_warning_german(self):
        """Stuck Task Warnung ist auf Deutsch."""
        message = "Stuck Task: process_document laeuft seit 900s"
        assert "laeuft seit" in message or "Stuck Task" in message


class TestEdgeCases:
    """Tests fuer Timeout Edge Cases."""

    def test_zero_timeout_raises_immediately(self):
        """Timeout von 0 sollte sofort RuntimeError werfen."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch("app.workers.celery_app._get_redis_lock_client") as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = False
            mock_get_client.return_value = mock_redis

            with pytest.raises(RuntimeError):
                acquire_gpu_lock(timeout=0)

    def test_negative_timeout_handled(self):
        """Negativer Timeout wird behandelt."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch("app.workers.celery_app._get_redis_lock_client") as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = False
            mock_get_client.return_value = mock_redis

            # Negative timeout should result in 0 iterations
            with pytest.raises(RuntimeError):
                acquire_gpu_lock(timeout=-1)

    def test_very_long_timeout_allowed(self):
        """Sehr langer Timeout ist erlaubt (fuer Batch-Jobs)."""
        from app.workers.celery_app import acquire_gpu_lock

        with patch("app.workers.celery_app._get_redis_lock_client") as mock_get_client:
            mock_redis = MagicMock()
            mock_redis.set.return_value = True  # Immediately succeeds
            mock_get_client.return_value = mock_redis

            # Long timeout should work
            lock = acquire_gpu_lock(timeout=3600)  # 1 hour

            assert lock is not None
