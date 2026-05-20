# -*- coding: utf-8 -*-
"""
Tests fuer DLQ Management Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Helper Funktionen (ohne Redis-Verbindung)

HINWEIS: Die DLQ-Tasks importieren Redis-Clients dynamisch.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_check_dlq_health_is_registered(self):
        """Sollte check_dlq_health Task registriert haben."""
        from app.workers.tasks.dlq_management_tasks import check_dlq_health

        assert check_dlq_health is not None
        assert hasattr(check_dlq_health, 'name')
        assert check_dlq_health.name == "app.workers.tasks.dlq_management_tasks.check_dlq_health"

    def test_cleanup_old_dlq_tasks_is_registered(self):
        """Sollte cleanup_old_dlq_tasks Task registriert haben."""
        from app.workers.tasks.dlq_management_tasks import cleanup_old_dlq_tasks

        assert cleanup_old_dlq_tasks is not None
        assert hasattr(cleanup_old_dlq_tasks, 'name')
        assert cleanup_old_dlq_tasks.name == "app.workers.tasks.dlq_management_tasks.cleanup_old_dlq_tasks"


class TestTaskBaseClass:
    """Tests fuer Task Base Class Konfiguration."""

    def test_all_tasks_use_cpu_base(self):
        """Sollte alle DLQ Tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.dlq_management_tasks import (
            check_dlq_health,
            cleanup_old_dlq_tasks,
        )
        from app.workers.celery_app import CPUTask

        tasks = [
            check_dlq_health,
            cleanup_old_dlq_tasks,
        ]

        for task in tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.dlq_management_tasks import (
            check_dlq_health,
            cleanup_old_dlq_tasks,
        )

        tasks = [
            check_dlq_health,
            cleanup_old_dlq_tasks,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.dlq_management_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"


class TestDLQConfiguration:
    """Tests fuer DLQ Konfiguration."""

    def test_dlq_queue_name_is_defined(self):
        """Sollte DLQ Queue Name definiert haben."""
        from app.workers.tasks.dlq_management_tasks import DLQ_QUEUE_NAME

        assert DLQ_QUEUE_NAME == "dlq"

    def test_dlq_redis_key_is_defined(self):
        """Sollte DLQ Redis Key definiert haben."""
        from app.workers.tasks.dlq_management_tasks import DLQ_REDIS_KEY

        assert DLQ_REDIS_KEY == "celery:dlq"

    def test_poison_pill_threshold_is_defined(self):
        """Sollte Poison Pill Threshold definiert haben."""
        from app.workers.tasks.dlq_management_tasks import POISON_PILL_THRESHOLD

        assert POISON_PILL_THRESHOLD == 3

    def test_alert_threshold_is_defined(self):
        """Sollte Alert Threshold definiert haben."""
        from app.workers.tasks.dlq_management_tasks import DLQ_ALERT_THRESHOLD

        assert DLQ_ALERT_THRESHOLD == 100

    def test_critical_threshold_is_defined(self):
        """Sollte Critical Threshold definiert haben."""
        from app.workers.tasks.dlq_management_tasks import DLQ_CRITICAL_THRESHOLD

        assert DLQ_CRITICAL_THRESHOLD == 500

    def test_thresholds_are_in_order(self):
        """Sollte Thresholds in richtiger Reihenfolge haben."""
        from app.workers.tasks.dlq_management_tasks import (
            DLQ_ALERT_THRESHOLD,
            DLQ_CRITICAL_THRESHOLD,
        )

        assert DLQ_ALERT_THRESHOLD < DLQ_CRITICAL_THRESHOLD


class TestRecordTaskFailure:
    """Tests fuer record_task_failure Hilfsfunktion."""

    def test_record_failure_increments_count(self):
        """Sollte Failure-Count inkrementieren."""
        from app.workers.tasks.dlq_management_tasks import record_task_failure, _failure_counts

        test_task_id = "test-task-123"

        # Reset count
        _failure_counts[test_task_id] = 0

        record_task_failure(test_task_id, "test_task")

        assert _failure_counts[test_task_id] == 1

    def test_record_failure_accumulates(self):
        """Sollte Failure-Count akkumulieren."""
        from app.workers.tasks.dlq_management_tasks import record_task_failure, _failure_counts

        test_task_id = "test-task-456"

        # Reset count
        _failure_counts[test_task_id] = 0

        record_task_failure(test_task_id, "test_task")
        record_task_failure(test_task_id, "test_task")
        record_task_failure(test_task_id, "test_task")

        assert _failure_counts[test_task_id] == 3


class TestGetDLQStatsFunction:
    """Tests fuer get_dlq_stats Hilfsfunktion."""

    def test_get_dlq_stats_returns_dict(self):
        """Sollte get_dlq_stats ein Dictionary zurueckgeben."""
        from app.workers.tasks.dlq_management_tasks import get_dlq_stats

        with patch('app.workers.tasks.dlq_management_tasks._get_redis_client') as mock_redis:
            mock_client = MagicMock()
            mock_client.llen.return_value = 0
            mock_redis.return_value = mock_client

            result = get_dlq_stats()

            assert isinstance(result, dict)
            assert "count" in result
            assert "status" in result
            assert "timestamp" in result

    def test_get_dlq_stats_healthy_status(self):
        """Sollte healthy Status bei wenigen Tasks zurueckgeben."""
        from app.workers.tasks.dlq_management_tasks import get_dlq_stats

        with patch('app.workers.tasks.dlq_management_tasks._get_redis_client') as mock_redis:
            mock_client = MagicMock()
            mock_client.llen.return_value = 10
            mock_client.lrange.return_value = []
            mock_redis.return_value = mock_client

            result = get_dlq_stats()

            assert result["status"] == "healthy"
            assert result["count"] == 10

    def test_get_dlq_stats_warning_status(self):
        """Sollte warning Status bei vielen Tasks zurueckgeben."""
        from app.workers.tasks.dlq_management_tasks import get_dlq_stats, DLQ_ALERT_THRESHOLD

        with patch('app.workers.tasks.dlq_management_tasks._get_redis_client') as mock_redis:
            mock_client = MagicMock()
            mock_client.llen.return_value = DLQ_ALERT_THRESHOLD + 1
            mock_client.lrange.return_value = []
            mock_redis.return_value = mock_client

            result = get_dlq_stats()

            assert result["status"] == "warning"

    def test_get_dlq_stats_critical_status(self):
        """Sollte critical Status bei sehr vielen Tasks zurueckgeben."""
        from app.workers.tasks.dlq_management_tasks import get_dlq_stats, DLQ_CRITICAL_THRESHOLD

        with patch('app.workers.tasks.dlq_management_tasks._get_redis_client') as mock_redis:
            mock_client = MagicMock()
            mock_client.llen.return_value = DLQ_CRITICAL_THRESHOLD + 1
            mock_client.lrange.return_value = []
            mock_redis.return_value = mock_client

            result = get_dlq_stats()

            assert result["status"] == "critical"


class TestPurgeDLQ:
    """Tests fuer purge_dlq Hilfsfunktion."""

    def test_purge_dlq_requires_confirm(self):
        """Sollte purge_dlq ohne confirm=True ablehnen."""
        from app.workers.tasks.dlq_management_tasks import purge_dlq

        result = purge_dlq(confirm=False)

        assert result["success"] is False
        assert "confirm=True" in result["error"]

    def test_purge_dlq_with_confirm(self):
        """Sollte purge_dlq mit confirm=True ausfuehren."""
        from app.workers.tasks.dlq_management_tasks import purge_dlq

        with patch('app.workers.tasks.dlq_management_tasks._get_redis_client') as mock_redis:
            mock_client = MagicMock()
            mock_client.llen.return_value = 5
            mock_redis.return_value = mock_client

            result = purge_dlq(confirm=True)

            assert result["success"] is True
            assert result["deleted_count"] == 5
            mock_client.delete.assert_called_once()
