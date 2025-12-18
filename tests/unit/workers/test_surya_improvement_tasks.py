# -*- coding: utf-8 -*-
"""
Tests fuer Surya Improvement Celery Tasks.

Testet:
- Beat Schedule Konfiguration
- Task Registrierung
- Task Optionen und Einstellungen

HINWEIS: Die Surya-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung).
"""

import pytest


class TestSuryaBeatSchedule:
    """Tests fuer Surya Improvement Celery Beat Schedule Konfiguration."""

    def test_beat_schedule_is_defined(self):
        """Sollte Beat Schedule definiert haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE is not None
        assert isinstance(CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE, dict)

    def test_beat_schedule_contains_daily_benchmark(self):
        """Sollte daily benchmark Task im Schedule haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert "surya-daily-benchmark" in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        config = CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE["surya-daily-benchmark"]
        assert "task" in config
        assert "schedule" in config
        assert config["task"] == "app.workers.tasks.surya_improvement_tasks.run_surya_benchmark"

    def test_beat_schedule_contains_retraining_check(self):
        """Sollte retraining check Task im Schedule haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert "surya-check-retraining-daily" in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        config = CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE["surya-check-retraining-daily"]
        assert config["task"] == "app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions"

    def test_beat_schedule_contains_corrections_processing(self):
        """Sollte corrections processing Task im Schedule haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert "surya-process-corrections-hourly" in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        config = CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE["surya-process-corrections-hourly"]
        assert config["task"] == "app.workers.tasks.surya_improvement_tasks.process_surya_corrections"

    def test_beat_schedule_contains_metrics_update(self):
        """Sollte metrics update Task im Schedule haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert "surya-update-metrics" in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        config = CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE["surya-update-metrics"]
        assert config["task"] == "app.workers.tasks.surya_improvement_tasks.update_surya_metrics"
        assert config["schedule"] == 900.0  # 15 Minuten

    def test_beat_schedule_contains_monthly_report(self):
        """Sollte monthly report Task im Schedule haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        assert "surya-monthly-report" in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        config = CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE["surya-monthly-report"]
        assert config["task"] == "app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report"

    def test_beat_schedule_has_valid_configs(self):
        """Sollte gueltige Konfigurationen haben."""
        from app.workers.tasks.surya_improvement_tasks import CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE

        for task_name, config in CELERY_BEAT_SURYA_IMPROVEMENT_SCHEDULE.items():
            assert "task" in config, f"Task {task_name} hat keine task-Definition"
            assert "schedule" in config, f"Task {task_name} hat keine schedule-Definition"

            # Validate queue option
            options = config.get("options", {})
            assert "queue" in options, f"Task {task_name} hat keine queue in options"


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_run_surya_benchmark_is_registered(self):
        """Sollte run_surya_benchmark Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import run_surya_benchmark

        assert run_surya_benchmark is not None
        assert hasattr(run_surya_benchmark, 'name')
        assert run_surya_benchmark.name == "app.workers.tasks.surya_improvement_tasks.run_surya_benchmark"

    def test_check_retraining_conditions_is_registered(self):
        """Sollte check_surya_retraining_conditions Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import check_surya_retraining_conditions

        assert check_surya_retraining_conditions is not None
        assert hasattr(check_surya_retraining_conditions, 'name')
        assert check_surya_retraining_conditions.name == "app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions"

    def test_export_dataset_is_registered(self):
        """Sollte export_surya_training_dataset Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import export_surya_training_dataset

        assert export_surya_training_dataset is not None
        assert hasattr(export_surya_training_dataset, 'name')
        assert export_surya_training_dataset.name == "app.workers.tasks.surya_improvement_tasks.export_surya_training_dataset"

    def test_finetuning_is_registered(self):
        """Sollte run_surya_german_finetuning Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import run_surya_german_finetuning

        assert run_surya_german_finetuning is not None
        assert hasattr(run_surya_german_finetuning, 'name')
        assert run_surya_german_finetuning.name == "app.workers.tasks.surya_improvement_tasks.run_surya_german_finetuning"

    def test_evaluate_model_is_registered(self):
        """Sollte evaluate_surya_model Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import evaluate_surya_model

        assert evaluate_surya_model is not None
        assert hasattr(evaluate_surya_model, 'name')
        assert evaluate_surya_model.name == "app.workers.tasks.surya_improvement_tasks.evaluate_surya_model"

    def test_deploy_model_is_registered(self):
        """Sollte deploy_surya_model Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import deploy_surya_model

        assert deploy_surya_model is not None
        assert hasattr(deploy_surya_model, 'name')
        assert deploy_surya_model.name == "app.workers.tasks.surya_improvement_tasks.deploy_surya_model"

    def test_evaluate_ab_test_is_registered(self):
        """Sollte evaluate_surya_ab_test Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import evaluate_surya_ab_test

        assert evaluate_surya_ab_test is not None
        assert hasattr(evaluate_surya_ab_test, 'name')
        assert evaluate_surya_ab_test.name == "app.workers.tasks.surya_improvement_tasks.evaluate_surya_ab_test"

    def test_rollback_is_registered(self):
        """Sollte rollback_surya_model Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import rollback_surya_model

        assert rollback_surya_model is not None
        assert hasattr(rollback_surya_model, 'name')
        assert rollback_surya_model.name == "app.workers.tasks.surya_improvement_tasks.rollback_surya_model"

    def test_process_corrections_is_registered(self):
        """Sollte process_surya_corrections Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import process_surya_corrections

        assert process_surya_corrections is not None
        assert hasattr(process_surya_corrections, 'name')
        assert process_surya_corrections.name == "app.workers.tasks.surya_improvement_tasks.process_surya_corrections"

    def test_update_metrics_is_registered(self):
        """Sollte update_surya_metrics Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import update_surya_metrics

        assert update_surya_metrics is not None
        assert hasattr(update_surya_metrics, 'name')
        assert update_surya_metrics.name == "app.workers.tasks.surya_improvement_tasks.update_surya_metrics"

    def test_generate_report_is_registered(self):
        """Sollte generate_surya_improvement_report Task registriert haben."""
        from app.workers.tasks.surya_improvement_tasks import generate_surya_improvement_report

        assert generate_surya_improvement_report is not None
        assert hasattr(generate_surya_improvement_report, 'name')
        assert generate_surya_improvement_report.name == "app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report"


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_benchmark_has_long_time_limits(self):
        """Sollte run_surya_benchmark lange Zeitlimits haben (GPU-intensiv)."""
        from app.workers.tasks.surya_improvement_tasks import run_surya_benchmark

        assert run_surya_benchmark.soft_time_limit == 3600  # 1 Stunde
        assert run_surya_benchmark.time_limit == 4200

    def test_finetuning_has_very_long_time_limits(self):
        """Sollte run_surya_german_finetuning sehr lange Zeitlimits haben."""
        from app.workers.tasks.surya_improvement_tasks import run_surya_german_finetuning

        assert run_surya_german_finetuning.soft_time_limit == 86400  # 24 Stunden
        assert run_surya_german_finetuning.time_limit == 90000

    def test_metrics_update_has_short_time_limits(self):
        """Sollte update_surya_metrics kurze Zeitlimits haben."""
        from app.workers.tasks.surya_improvement_tasks import update_surya_metrics

        assert update_surya_metrics.soft_time_limit == 120  # 2 Minuten
        assert update_surya_metrics.time_limit == 180


class TestTaskBaseClass:
    """Tests fuer Task Base Class Konfiguration."""

    def test_gpu_tasks_use_gpu_base(self):
        """Sollte GPU-intensive Tasks mit GPUTask Base konfigurieren."""
        from app.workers.tasks.surya_improvement_tasks import (
            run_surya_benchmark,
            run_surya_german_finetuning,
            evaluate_surya_model,
        )
        from app.workers.celery_app import GPUTask

        gpu_tasks = [
            run_surya_benchmark,
            run_surya_german_finetuning,
            evaluate_surya_model,
        ]

        for task in gpu_tasks:
            assert isinstance(task, GPUTask), f"Task {task.name} sollte GPUTask verwenden"

    def test_cpu_tasks_use_cpu_base(self):
        """Sollte CPU-only Tasks mit CPUTask Base konfigurieren."""
        from app.workers.tasks.surya_improvement_tasks import (
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            deploy_surya_model,
            evaluate_surya_ab_test,
            rollback_surya_model,
            process_surya_corrections,
            update_surya_metrics,
            generate_surya_improvement_report,
        )
        from app.workers.celery_app import CPUTask

        cpu_tasks = [
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            deploy_surya_model,
            evaluate_surya_ab_test,
            rollback_surya_model,
            process_surya_corrections,
            update_surya_metrics,
            generate_surya_improvement_report,
        ]

        for task in cpu_tasks:
            assert isinstance(task, CPUTask), f"Task {task.name} sollte CPUTask verwenden"


class TestTaskAcksLateConfig:
    """Tests fuer acks_late Konfiguration (Reliability)."""

    def test_critical_tasks_have_acks_late(self):
        """Sollte kritische Tasks mit acks_late konfigurieren."""
        from app.workers.tasks.surya_improvement_tasks import (
            run_surya_benchmark,
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            run_surya_german_finetuning,
            evaluate_surya_model,
            deploy_surya_model,
        )

        critical_tasks = [
            run_surya_benchmark,
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            run_surya_german_finetuning,
            evaluate_surya_model,
            deploy_surya_model,
        ]

        for task in critical_tasks:
            assert getattr(task, 'acks_late', False) is True, \
                f"Kritischer Task {task.name} hat nicht acks_late=True"


class TestTaskNaming:
    """Tests fuer Task Namenskonventionen."""

    def test_task_names_follow_convention(self):
        """Sollte Task-Namen nach Konvention benennen."""
        from app.workers.tasks.surya_improvement_tasks import (
            run_surya_benchmark,
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            run_surya_german_finetuning,
            evaluate_surya_model,
            deploy_surya_model,
            evaluate_surya_ab_test,
            rollback_surya_model,
            process_surya_corrections,
            update_surya_metrics,
            generate_surya_improvement_report,
        )

        tasks = [
            run_surya_benchmark,
            check_surya_retraining_conditions,
            export_surya_training_dataset,
            run_surya_german_finetuning,
            evaluate_surya_model,
            deploy_surya_model,
            evaluate_surya_ab_test,
            rollback_surya_model,
            process_surya_corrections,
            update_surya_metrics,
            generate_surya_improvement_report,
        ]

        for task in tasks:
            assert task.name.startswith("app.workers.tasks.surya_improvement_tasks."), \
                f"Task {task.name} folgt nicht der Namenskonvention"
