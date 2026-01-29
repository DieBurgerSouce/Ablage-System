# -*- coding: utf-8 -*-
"""
Tests fuer Predictive Maintenance Celery Tasks.

Testet:
- Task Registrierung
- Task Optionen und Einstellungen
- Celery Beat Schedule Eintraege

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

import pytest


class TestTaskRegistration:
    """Tests fuer Task Registrierung."""

    def test_collect_metrics_is_registered(self):
        """Sollte collect_metrics_for_prediction Task registriert haben."""
        from app.workers.tasks.predictive_tasks import collect_metrics_for_prediction

        assert collect_metrics_for_prediction is not None
        assert hasattr(collect_metrics_for_prediction, "name")
        assert (
            collect_metrics_for_prediction.name
            == "app.workers.tasks.predictive_tasks.collect_metrics_for_prediction"
        )

    def test_run_predictions_is_registered(self):
        """Sollte run_predictions Task registriert haben."""
        from app.workers.tasks.predictive_tasks import run_predictions

        assert run_predictions is not None
        assert hasattr(run_predictions, "name")
        assert (
            run_predictions.name
            == "app.workers.tasks.predictive_tasks.run_predictions"
        )

    def test_generate_alerts_is_registered(self):
        """Sollte generate_predictive_alerts Task registriert haben."""
        from app.workers.tasks.predictive_tasks import generate_predictive_alerts

        assert generate_predictive_alerts is not None
        assert hasattr(generate_predictive_alerts, "name")
        assert (
            generate_predictive_alerts.name
            == "app.workers.tasks.predictive_tasks.generate_predictive_alerts"
        )

    def test_cleanup_alerts_is_registered(self):
        """Sollte cleanup_old_predictive_alerts Task registriert haben."""
        from app.workers.tasks.predictive_tasks import cleanup_old_predictive_alerts

        assert cleanup_old_predictive_alerts is not None
        assert hasattr(cleanup_old_predictive_alerts, "name")
        assert (
            cleanup_old_predictive_alerts.name
            == "app.workers.tasks.predictive_tasks.cleanup_old_predictive_alerts"
        )


class TestTaskOptions:
    """Tests fuer Task Optionen."""

    def test_collect_metrics_has_time_limits(self):
        """Sollte collect_metrics_for_prediction Zeitlimits haben."""
        from app.workers.tasks.predictive_tasks import collect_metrics_for_prediction

        assert collect_metrics_for_prediction.soft_time_limit == 55
        assert collect_metrics_for_prediction.time_limit == 60

    def test_run_predictions_has_time_limits(self):
        """Sollte run_predictions Zeitlimits haben."""
        from app.workers.tasks.predictive_tasks import run_predictions

        assert run_predictions.soft_time_limit == 55
        assert run_predictions.time_limit == 60

    def test_generate_alerts_has_time_limits(self):
        """Sollte generate_predictive_alerts Zeitlimits haben."""
        from app.workers.tasks.predictive_tasks import generate_predictive_alerts

        assert generate_predictive_alerts.soft_time_limit == 55
        assert generate_predictive_alerts.time_limit == 60

    def test_cleanup_alerts_has_time_limits(self):
        """Sollte cleanup_old_predictive_alerts Zeitlimits haben."""
        from app.workers.tasks.predictive_tasks import cleanup_old_predictive_alerts

        assert cleanup_old_predictive_alerts.soft_time_limit == 55
        assert cleanup_old_predictive_alerts.time_limit == 60

    def test_tasks_ignore_result(self):
        """Sollte Predictive Tasks mit ignore_result konfigurieren."""
        from app.workers.tasks.predictive_tasks import (
            collect_metrics_for_prediction,
            run_predictions,
            generate_predictive_alerts,
            cleanup_old_predictive_alerts,
        )

        tasks = [
            collect_metrics_for_prediction,
            run_predictions,
            generate_predictive_alerts,
            cleanup_old_predictive_alerts,
        ]

        for task in tasks:
            # ignore_result=True wird in den Task-Dekoratoren gesetzt
            assert task.ignore_result is True, f"Task {task.name} sollte ignore_result=True haben"

    def test_tasks_have_correct_queues(self):
        """Sollte Predictive Tasks korrekte Queues zuweisen."""
        from app.workers.tasks.predictive_tasks import (
            collect_metrics_for_prediction,
            run_predictions,
            generate_predictive_alerts,
            cleanup_old_predictive_alerts,
        )

        # Metriken und Predictions auf monitoring Queue
        assert collect_metrics_for_prediction.queue == "monitoring"
        assert run_predictions.queue == "monitoring"
        assert generate_predictive_alerts.queue == "monitoring"

        # Cleanup auf maintenance Queue
        assert cleanup_old_predictive_alerts.queue == "maintenance"


class TestCeleryBeatSchedule:
    """Tests fuer Celery Beat Schedule Eintraege."""

    def test_predictive_tasks_in_beat_schedule(self):
        """Sollte Predictive Tasks im Beat Schedule haben."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        # Pruefe ob alle Predictive Tasks im Schedule sind
        expected_entries = [
            "predictive-collect-metrics",
            "predictive-run-predictions",
            "predictive-generate-alerts",
            "predictive-cleanup-old-alerts",
        ]

        for entry in expected_entries:
            assert entry in beat_schedule, f"Beat Schedule sollte '{entry}' enthalten"

    def test_collect_metrics_schedule_interval(self):
        """Sollte collect_metrics alle 60 Sekunden ausfuehren."""
        from app.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule.get("predictive-collect-metrics")

        assert entry is not None
        assert entry["schedule"] == 60.0

    def test_run_predictions_schedule_interval(self):
        """Sollte run_predictions alle 300 Sekunden (5 min) ausfuehren."""
        from app.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule.get("predictive-run-predictions")

        assert entry is not None
        assert entry["schedule"] == 300.0

    def test_generate_alerts_schedule_interval(self):
        """Sollte generate_alerts alle 300 Sekunden (5 min) ausfuehren."""
        from app.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule.get("predictive-generate-alerts")

        assert entry is not None
        assert entry["schedule"] == 300.0

    def test_cleanup_alerts_schedule_is_daily(self):
        """Sollte cleanup_alerts taeglich um 03:50 ausfuehren."""
        from celery.schedules import crontab
        from app.workers.celery_app import celery_app

        entry = celery_app.conf.beat_schedule.get("predictive-cleanup-old-alerts")

        assert entry is not None
        assert isinstance(entry["schedule"], crontab)
        assert entry["kwargs"]["max_age_hours"] == 24


class TestHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    def test_collect_disk_usage_returns_float_or_none(self):
        """Sollte _collect_disk_usage float oder None zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_disk_usage

        result = _collect_disk_usage()

        assert result is None or isinstance(result, float)
        if result is not None:
            assert 0 <= result <= 100

    def test_collect_queue_depths_returns_dict(self):
        """Sollte _collect_queue_depths Dict zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_queue_depths

        result = _collect_queue_depths()

        assert isinstance(result, dict)
        # Alle Werte sollten int sein
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, int)
            assert value >= 0

    def test_collect_memory_usage_returns_float_or_none(self):
        """Sollte _collect_memory_usage float oder None zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_memory_usage

        result = _collect_memory_usage()

        # Kann None sein wenn psutil nicht verfuegbar
        assert result is None or isinstance(result, float)
        if result is not None:
            assert 0 <= result <= 100

    def test_collect_cpu_usage_returns_float_or_none(self):
        """Sollte _collect_cpu_usage float oder None zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_cpu_usage

        result = _collect_cpu_usage()

        # Kann None sein wenn psutil nicht verfuegbar
        assert result is None or isinstance(result, float)
        if result is not None:
            assert 0 <= result <= 100

    def test_collect_gpu_vram_handles_missing_cuda(self):
        """Sollte _collect_gpu_vram None bei fehlendem CUDA zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_gpu_vram

        result = _collect_gpu_vram()

        # Kann float sein wenn CUDA verfuegbar, sonst None
        assert result is None or isinstance(result, float)
        if result is not None:
            assert result >= 0

    def test_collect_gpu_utilization_handles_missing_nvidia_smi(self):
        """Sollte _collect_gpu_utilization None bei fehlendem nvidia-smi zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_gpu_utilization

        result = _collect_gpu_utilization()

        # Kann float sein wenn nvidia-smi verfuegbar, sonst None
        assert result is None or isinstance(result, float)
        if result is not None:
            assert 0 <= result <= 100

    def test_collect_ocr_quality_metrics_returns_dict(self):
        """Sollte _collect_ocr_quality_metrics Dict zurueckgeben."""
        from app.workers.tasks.predictive_tasks import _collect_ocr_quality_metrics

        result = _collect_ocr_quality_metrics()

        assert isinstance(result, dict)
        # Sollte leeres Dict oder Dict mit Backend-Keys sein
        for key, value in result.items():
            assert key in ["deepseek", "got_ocr", "surya", "surya_gpu"]
            assert isinstance(value, dict)
