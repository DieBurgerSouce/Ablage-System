# -*- coding: utf-8 -*-
"""
Unit-Tests für Backup Celery Tasks.

Testet:
- backup_full_task (Vollbackup)
- backup_postgres_task (PostgreSQL)
- backup_redis_task (Redis)
- apply_retention_task (Retention Policy)
- sync_to_remote_task (Remote-Sync)
- update_backup_metrics_task (Metriken)

Feinpoliert und durchdacht - Enterprise-grade Backup-Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_backup_service():
    """Create mock backup service."""
    service = Mock()
    service.config = Mock()
    service.config.remote_enabled = True
    service.config.remote_target = "s3://backup-bucket"
    service.metrics = Mock()
    return service


@pytest.fixture
def sample_backup_result():
    """Create sample backup result."""
    result = Mock()
    result.success = True
    result.backup_type = "postgres"
    result.path = "/backups/postgres_20241201.sql.gz"
    result.size_bytes = 1024 * 1024 * 50  # 50MB
    result.error = None
    return result


@pytest.fixture
def sample_failed_result():
    """Create sample failed backup result."""
    result = Mock()
    result.success = False
    result.backup_type = "redis"
    result.path = None
    result.size_bytes = 0
    result.error = "Redis connection failed"
    return result


@pytest.fixture
def mock_celery_task():
    """Create mock Celery task context."""
    task = Mock()
    task.request = Mock()
    task.request.id = str(uuid4())
    task.retry = Mock(side_effect=Exception("Retry triggered"))
    return task


# ========================= backup_full_task Tests =========================


class TestBackupFullTask:
    """Tests for full backup task."""

    def test_backup_full_success(self, mock_backup_service, sample_backup_result, mock_celery_task):
        """Vollbackup sollte alle Komponenten sichern."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            # Mock async backup_full
            async def mock_backup():
                return [sample_backup_result, sample_backup_result]

            mock_backup_service.backup_full = Mock(return_value=mock_backup())

            from app.workers.tasks.backup_tasks import backup_full_task

            with patch.object(backup_full_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = [sample_backup_result, sample_backup_result]

                    result = backup_full_task(mock_celery_task)

                    assert result["erfolg"] is True
                    assert result["erfolgreich"] == 2
                    assert result["fehlgeschlagen"] == 0

    def test_backup_full_partial_failure(self, mock_backup_service, sample_backup_result, sample_failed_result, mock_celery_task):
        """Teilweiser Fehler sollte reported werden."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import backup_full_task

            with patch.object(backup_full_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = [sample_backup_result, sample_failed_result]

                    result = backup_full_task(mock_celery_task)

                    assert result["erfolg"] is False
                    assert result["erfolgreich"] == 1
                    assert result["fehlgeschlagen"] == 1

    def test_backup_full_retry_on_error(self, mock_backup_service, mock_celery_task):
        """Fehler sollte Retry auslösen."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import backup_full_task

            with patch.object(backup_full_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.side_effect = Exception("Connection error")

                    with pytest.raises(Exception):
                        backup_full_task(mock_celery_task)


# ========================= backup_postgres_task Tests =========================


class TestBackupPostgresTask:
    """Tests for PostgreSQL backup task."""

    def test_backup_postgres_success(self, mock_backup_service, sample_backup_result, mock_celery_task):
        """PostgreSQL-Backup sollte erfolgreich sein."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import backup_postgres_task

            with patch.object(backup_postgres_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = sample_backup_result

                    result = backup_postgres_task(mock_celery_task)

                    assert result["erfolg"] is True
                    assert result["typ"] == "postgres"
                    assert result["groesse_mb"] == 50.0

    def test_backup_postgres_calculates_size(self, mock_backup_service, mock_celery_task):
        """Groesse sollte korrekt berechnet werden."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            backup_result = Mock()
            backup_result.success = True
            backup_result.backup_type = "postgres"
            backup_result.path = "/backups/test.sql.gz"
            backup_result.size_bytes = 1024 * 1024 * 100  # 100MB
            backup_result.error = None

            from app.workers.tasks.backup_tasks import backup_postgres_task

            with patch.object(backup_postgres_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = backup_result

                    result = backup_postgres_task(mock_celery_task)

                    assert result["groesse_mb"] == 100.0


# ========================= backup_redis_task Tests =========================


class TestBackupRedisTask:
    """Tests for Redis backup task."""

    def test_backup_redis_success(self, mock_backup_service, mock_celery_task):
        """Redis-Backup sollte erfolgreich sein."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            backup_result = Mock()
            backup_result.success = True
            backup_result.backup_type = "redis"
            backup_result.path = "/backups/redis_dump.rdb"
            backup_result.size_bytes = 1024 * 1024 * 10
            backup_result.error = None

            from app.workers.tasks.backup_tasks import backup_redis_task

            with patch.object(backup_redis_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = backup_result

                    result = backup_redis_task(mock_celery_task)

                    assert result["erfolg"] is True
                    assert result["typ"] == "redis"


# ========================= apply_retention_task Tests =========================


class TestApplyRetentionTask:
    """Tests for retention policy task."""

    def test_retention_deletes_old_backups(self, mock_backup_service, mock_celery_task):
        """Retention sollte alte Backups loeschen."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import apply_retention_task

            with patch.object(apply_retention_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = {
                        "postgres": 5,
                        "redis": 3,
                        "minio": 2,
                    }

                    result = apply_retention_task(mock_celery_task)

                    assert result["erfolg"] is True
                    assert result["geloescht_gesamt"] == 10

    def test_retention_no_old_backups(self, mock_backup_service, mock_celery_task):
        """Ohne alte Backups sollte nichts geloescht werden."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import apply_retention_task

            with patch.object(apply_retention_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = {}

                    result = apply_retention_task(mock_celery_task)

                    assert result["geloescht_gesamt"] == 0


# ========================= sync_to_remote_task Tests =========================


class TestSyncToRemoteTask:
    """Tests for remote sync task."""

    def test_sync_success(self, mock_backup_service, mock_celery_task):
        """Sync sollte erfolgreich sein."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_backup_service.config.remote_enabled = True
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import sync_to_remote_task

            with patch.object(sync_to_remote_task, 'request', mock_celery_task.request):
                with patch('app.workers.tasks.backup_tasks.run_async') as mock_run:
                    mock_run.return_value = True

                    result = sync_to_remote_task(mock_celery_task)

                    assert result["erfolg"] is True
                    assert result["synchronisiert"] is True

    def test_sync_disabled(self, mock_backup_service, mock_celery_task):
        """Deaktivierter Sync sollte uebersprungen werden."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_backup_service.config.remote_enabled = False
            mock_get.return_value = mock_backup_service

            from app.workers.tasks.backup_tasks import sync_to_remote_task

            with patch.object(sync_to_remote_task, 'request', mock_celery_task.request):
                result = sync_to_remote_task(mock_celery_task)

                assert result["erfolg"] is True
                assert result["synchronisiert"] is False
                assert "deaktiviert" in result["nachricht"]


# ========================= update_backup_metrics_task Tests =========================


class TestUpdateBackupMetricsTask:
    """Tests for backup metrics task."""

    def test_metrics_update_success(self, mock_backup_service, mock_celery_task):
        """Metriken-Update sollte erfolgreich sein."""
        with patch('app.workers.tasks.backup_tasks.get_backup_service') as mock_get:
            mock_get.return_value = mock_backup_service

            disk_usage = Mock()
            disk_usage.total_bytes = 1024 * 1024 * 1024 * 500  # 500GB
            disk_usage.free_bytes = 1024 * 1024 * 1024 * 200  # 200GB
            disk_usage.usage_percent = 60.0

            mock_backup_service.metrics.update_disk_usage.return_value = disk_usage
            mock_backup_service.metrics.update_backup_file_counts.return_value = {
                "postgres": 10,
                "redis": 10,
            }

            from app.workers.tasks.backup_tasks import update_backup_metrics_task

            with patch.object(update_backup_metrics_task, 'request', mock_celery_task.request):
                result = update_backup_metrics_task(mock_celery_task)

                assert result["erfolg"] is True
                assert result["speicherplatz"]["total_gb"] == 500.0
                assert result["speicherplatz"]["verwendung_prozent"] == 60.0


# ========================= run_async Helper Tests =========================


class TestRunAsyncHelper:
    """Tests for run_async helper function."""

    def test_run_async_executes_coroutine(self):
        """run_async sollte Coroutine ausfuehren."""
        from app.workers.tasks.backup_tasks import run_async

        async def sample_coro():
            return "success"

        result = run_async(sample_coro())

        assert result == "success"

    def test_run_async_handles_exception(self):
        """run_async sollte Exceptions propagieren."""
        from app.workers.tasks.backup_tasks import run_async

        async def failing_coro():
            raise ValueError("Test error")

        with pytest.raises(ValueError) as exc_info:
            run_async(failing_coro())

        assert "Test error" in str(exc_info.value)
