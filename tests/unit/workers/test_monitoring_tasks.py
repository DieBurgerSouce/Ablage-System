# -*- coding: utf-8 -*-
"""
Tests fuer Monitoring Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen

HINWEIS: Die Monitoring-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_worker_health_check_is_registered(self):
        """Sollte worker_health_check_task Task registriert haben."""
        from app.workers.tasks.monitoring_tasks import worker_health_check_task

        assert worker_health_check_task is not None
        assert hasattr(worker_health_check_task, 'name')
        assert worker_health_check_task.name == "app.workers.tasks.monitoring_tasks.worker_health_check_task"

    def test_cleanup_stuck_tasks_is_registered(self):
        """Sollte cleanup_stuck_tasks Task registriert haben."""
        from app.workers.tasks.monitoring_tasks import cleanup_stuck_tasks

        assert cleanup_stuck_tasks is not None
        assert hasattr(cleanup_stuck_tasks, 'name')
        assert cleanup_stuck_tasks.name == "app.workers.tasks.monitoring_tasks.cleanup_stuck_tasks"

    def test_check_queue_backpressure_is_registered(self):
        """Sollte check_queue_backpressure Task registriert haben."""
        from app.workers.tasks.monitoring_tasks import check_queue_backpressure

        assert check_queue_backpressure is not None
        assert hasattr(check_queue_backpressure, 'name')
        assert check_queue_backpressure.name == "app.workers.tasks.monitoring_tasks.check_queue_backpressure"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_health_check_has_short_time_limits(self):
        """Sollte worker_health_check_task kurze Zeitlimits haben."""
        from app.workers.tasks.monitoring_tasks import worker_health_check_task

        assert worker_health_check_task.soft_time_limit == 25
        assert worker_health_check_task.time_limit == 30

    def test_cleanup_stuck_has_time_limits(self):
        """Sollte cleanup_stuck_tasks Zeitlimits haben."""
        from app.workers.tasks.monitoring_tasks import cleanup_stuck_tasks

        assert cleanup_stuck_tasks.soft_time_limit == 55
        assert cleanup_stuck_tasks.time_limit == 60

    def test_backpressure_has_short_time_limits(self):
        """Sollte check_queue_backpressure kurze Zeitlimits haben."""
        from app.workers.tasks.monitoring_tasks import check_queue_backpressure

        assert check_queue_backpressure.soft_time_limit == 25
        assert check_queue_backpressure.time_limit == 30

    def test_tasks_ignore_result(self):
        """Sollte Monitoring Tasks mit ignore_result konfigurieren."""
        from app.workers.tasks.monitoring_tasks import (
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        )

        tasks = [
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        ]

        for task in tasks:
            assert getattr(task, 'ignore_result', False) is True, \
                f"Task {task.name} sollte ignore_result=True haben"

    def test_tasks_have_priority(self):
        """Sollte Monitoring Tasks mit hoher Prioritaet konfigurieren."""
        from app.workers.tasks.monitoring_tasks import (
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        )

        tasks = [
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        ]

        for task in tasks:
            # Priority 1 is high priority
            assert getattr(task, 'priority', None) == 1, \
                f"Task {task.name} sollte priority=1 haben"


class TestTaskBaseClass:
    """Tests fuer Task Base Class Konfiguration."""

    def test_all_tasks_use_cpu_base(self):
        """Sollte alle Monitoring Tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.monitoring_tasks import (
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        )
        from app.workers.celery_app import CPUTask

        tasks = [
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        ]

        for task in tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskQueueConfig:
    """Tests fuer Task Queue Konfiguration."""

    def test_health_check_uses_metrics_queue(self):
        """Sollte worker_health_check_task metrics Queue verwenden."""
        from app.workers.tasks.monitoring_tasks import worker_health_check_task

        assert getattr(worker_health_check_task, 'queue', None) == "metrics"

    def test_cleanup_uses_maintenance_queue(self):
        """Sollte cleanup_stuck_tasks maintenance Queue verwenden."""
        from app.workers.tasks.monitoring_tasks import cleanup_stuck_tasks

        assert getattr(cleanup_stuck_tasks, 'queue', None) == "maintenance"

    def test_backpressure_uses_metrics_queue(self):
        """Sollte check_queue_backpressure metrics Queue verwenden."""
        from app.workers.tasks.monitoring_tasks import check_queue_backpressure

        assert getattr(check_queue_backpressure, 'queue', None) == "metrics"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.monitoring_tasks import (
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        )

        tasks = [
            worker_health_check_task,
            cleanup_stuck_tasks,
            check_queue_backpressure,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.monitoring_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"
