# -*- coding: utf-8 -*-
"""
Tests fuer Training Celery Tasks.

Testet:
- Beat Schedule Konfiguration
- Task Registrierung
- Task Optionen und Einstellungen

HINWEIS: Die Training-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4


class TestCeleryBeatSchedule:
    """Tests fuer Celery Beat Schedule Konfiguration."""

    def test_beat_schedule_is_defined(self):
        """Sollte Beat Schedule definiert haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        assert CELERY_BEAT_TRAINING_SCHEDULE is not None
        assert isinstance(CELERY_BEAT_TRAINING_SCHEDULE, dict)

    def test_beat_schedule_contains_daily_stats(self):
        """Sollte daily stats Task im Schedule haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        assert "training-daily-stats" in CELERY_BEAT_TRAINING_SCHEDULE

        config = CELERY_BEAT_TRAINING_SCHEDULE["training-daily-stats"]
        assert "task" in config
        assert "schedule" in config
        assert config["task"] == "app.workers.tasks.training_tasks.generate_daily_stats"

    def test_beat_schedule_contains_feedback_queue(self):
        """Sollte feedback queue Task im Schedule haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        assert "training-feedback-queue-hourly" in CELERY_BEAT_TRAINING_SCHEDULE

        config = CELERY_BEAT_TRAINING_SCHEDULE["training-feedback-queue-hourly"]
        assert config["task"] == "app.workers.tasks.training_tasks.process_feedback_queue"

    def test_beat_schedule_contains_learned_weights(self):
        """Sollte learned weights Task im Schedule haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        assert "training-learned-weights-daily" in CELERY_BEAT_TRAINING_SCHEDULE

        config = CELERY_BEAT_TRAINING_SCHEDULE["training-learned-weights-daily"]
        assert config["task"] == "app.workers.tasks.training_tasks.update_learned_weights"

    def test_beat_schedule_contains_weekly_benchmarks(self):
        """Sollte weekly benchmarks Task im Schedule haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        assert "training-weekly-benchmarks" in CELERY_BEAT_TRAINING_SCHEDULE

        config = CELERY_BEAT_TRAINING_SCHEDULE["training-weekly-benchmarks"]
        assert config["task"] == "app.workers.tasks.training_tasks.run_scheduled_benchmarks"

    def test_beat_schedule_has_valid_schedules(self):
        """Sollte gueltige Schedule-Werte haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        for task_name, config in CELERY_BEAT_TRAINING_SCHEDULE.items():
            assert "task" in config, f"Task {task_name} hat keine task-Definition"
            assert "schedule" in config, f"Task {task_name} hat keine schedule-Definition"
            assert "options" in config, f"Task {task_name} hat keine options-Definition"

            # Schedule muss ein Wert sein (int, float, oder dict fuer crontab)
            schedule = config["schedule"]
            assert isinstance(schedule, (int, float, dict)), \
                f"Task {task_name} hat ungueltigen Schedule-Typ: {type(schedule)}"

    def test_beat_schedule_tasks_have_queue(self):
        """Sollte Queue-Option fuer alle Tasks haben."""
        from app.workers.tasks.training_tasks import CELERY_BEAT_TRAINING_SCHEDULE

        for task_name, config in CELERY_BEAT_TRAINING_SCHEDULE.items():
            options = config.get("options", {})
            assert "queue" in options, f"Task {task_name} hat keine queue in options"


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_run_benchmark_batch_is_registered(self):
        """Sollte run_benchmark_batch Task registriert haben."""
        from app.workers.tasks.training_tasks import run_benchmark_batch

        assert run_benchmark_batch is not None
        assert hasattr(run_benchmark_batch, 'name')
        assert run_benchmark_batch.name == "app.workers.tasks.training_tasks.run_benchmark_batch"

    def test_run_scheduled_benchmarks_is_registered(self):
        """Sollte run_scheduled_benchmarks Task registriert haben."""
        from app.workers.tasks.training_tasks import run_scheduled_benchmarks

        assert run_scheduled_benchmarks is not None
        assert hasattr(run_scheduled_benchmarks, 'name')
        assert run_scheduled_benchmarks.name == "app.workers.tasks.training_tasks.run_scheduled_benchmarks"

    def test_generate_daily_stats_is_registered(self):
        """Sollte generate_daily_stats Task registriert haben."""
        from app.workers.tasks.training_tasks import generate_daily_stats

        assert generate_daily_stats is not None
        assert hasattr(generate_daily_stats, 'name')
        assert generate_daily_stats.name == "app.workers.tasks.training_tasks.generate_daily_stats"

    def test_process_feedback_queue_is_registered(self):
        """Sollte process_feedback_queue Task registriert haben."""
        from app.workers.tasks.training_tasks import process_feedback_queue

        assert process_feedback_queue is not None
        assert hasattr(process_feedback_queue, 'name')
        assert process_feedback_queue.name == "app.workers.tasks.training_tasks.process_feedback_queue"

    def test_update_learned_weights_is_registered(self):
        """Sollte update_learned_weights Task registriert haben."""
        from app.workers.tasks.training_tasks import update_learned_weights

        assert update_learned_weights is not None
        assert hasattr(update_learned_weights, 'name')
        assert update_learned_weights.name == "app.workers.tasks.training_tasks.update_learned_weights"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_benchmark_batch_is_gpu_task(self):
        """Sollte run_benchmark_batch als GPU Task konfiguriert sein."""
        from app.workers.tasks.training_tasks import run_benchmark_batch
        from app.workers.celery_app import GPUTask

        # Check if task uses GPUTask base class
        assert isinstance(run_benchmark_batch, GPUTask), \
            "run_benchmark_batch sollte GPUTask als Base verwenden"

    def test_benchmark_batch_has_retry_config(self):
        """Sollte run_benchmark_batch retry Konfiguration haben."""
        from app.workers.tasks.training_tasks import run_benchmark_batch

        # Check retry configuration
        assert hasattr(run_benchmark_batch, 'autoretry_for')
        assert hasattr(run_benchmark_batch, 'retry_kwargs')

    def test_daily_stats_has_time_limits(self):
        """Sollte generate_daily_stats Zeitlimits haben."""
        from app.workers.tasks.training_tasks import generate_daily_stats

        assert hasattr(generate_daily_stats, 'soft_time_limit')
        assert hasattr(generate_daily_stats, 'time_limit')
        assert generate_daily_stats.soft_time_limit < generate_daily_stats.time_limit

    def test_scheduled_benchmarks_has_long_time_limits(self):
        """Sollte run_scheduled_benchmarks lange Zeitlimits haben."""
        from app.workers.tasks.training_tasks import run_scheduled_benchmarks

        # Should have at least 1 hour time limit for benchmarks
        assert run_scheduled_benchmarks.soft_time_limit >= 3600
        assert run_scheduled_benchmarks.time_limit >= 3600


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.training_tasks import (
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
            process_feedback_queue,
            update_learned_weights,
        )

        tasks = [
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
            process_feedback_queue,
            update_learned_weights,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.training_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"

    def test_all_tasks_use_base_class(self):
        """Sollte alle Tasks mit GPUTask oder CPUTask Base konfigurieren."""
        from app.workers.tasks.training_tasks import (
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
            process_feedback_queue,
            update_learned_weights,
        )
        from app.workers.celery_app import GPUTask, CPUTask

        # GPU-intensive tasks
        gpu_tasks = [
            run_benchmark_batch,
            run_scheduled_benchmarks,
        ]
        for task in gpu_tasks:
            assert isinstance(task, GPUTask), f"Task {task.name} sollte GPUTask verwenden"

        # CPU-only tasks
        cpu_tasks = [
            generate_daily_stats,
            process_feedback_queue,
            update_learned_weights,
        ]
        for task in cpu_tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskAcksLateConfig:
    """Tests fuer acks_late Konfiguration (Reliability)."""

    def test_critical_tasks_have_acks_late(self):
        """Sollte kritische Tasks mit acks_late konfigurieren."""
        from app.workers.tasks.training_tasks import (
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
        )

        # Kritische Tasks sollten acks_late=True haben fuer Reliability
        critical_tasks = [
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
        ]

        for task in critical_tasks:
            assert getattr(task, 'acks_late', False) is True, \
                f"Kritischer Task {task.name} hat nicht acks_late=True"

    def test_critical_tasks_reject_on_worker_lost(self):
        """Sollte kritische Tasks mit reject_on_worker_lost konfigurieren."""
        from app.workers.tasks.training_tasks import (
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
        )

        critical_tasks = [
            run_benchmark_batch,
            run_scheduled_benchmarks,
            generate_daily_stats,
        ]

        for task in critical_tasks:
            assert getattr(task, 'reject_on_worker_lost', False) is True, \
                f"Kritischer Task {task.name} hat nicht reject_on_worker_lost=True"
