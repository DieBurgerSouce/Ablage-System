# -*- coding: utf-8 -*-
"""
Unit-Tests für ML Celery Tasks.

Testet:
- MLTracker (Routing, OCR-Tracking)
- run_drift_detection
- update_ml_metrics
- check_experiment_completion
- trigger_model_retrain
- generate_ml_report

Feinpoliert und durchdacht - ML-Operations-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_celery_task():
    """Create mock Celery task context."""
    task = Mock()
    task.request = Mock()
    task.request.id = str(uuid4())
    return task


@pytest.fixture
def sample_features():
    """Create sample document features."""
    return {
        "has_tables": True,
        "has_images": False,
        "language": "de",
        "word_count": 500,
        "complexity_score": 0.7,
    }


@pytest.fixture
def sample_drift_report():
    """Create sample drift report."""
    report = Mock()
    report.overall_drift_score = 0.35
    report.severity = Mock()
    report.severity.value = "low"
    report.feature_drifts = [
        Mock(feature_name="complexity_score", drift_score=0.4),
        Mock(feature_name="word_count", drift_score=0.3),
    ]
    report.recommendations = ["Monitor closely"]
    report.to_dict = Mock(return_value={
        "overall_drift_score": 0.35,
        "severity": "low",
    })
    return report


@pytest.fixture
def sample_experiment():
    """Create sample A/B experiment."""
    exp = Mock()
    exp.experiment_id = "exp-001"
    exp.name = "DeepSeek vs GOT"
    exp.end_time = datetime.now(timezone.utc) + timedelta(days=7)
    exp.significance_reached = False
    exp.get_summary = Mock(return_value={
        "id": "exp-001",
        "name": "DeepSeek vs GOT",
        "status": "active",
    })
    return exp


# ========================= MLTracker Tests =========================


class TestMLTracker:
    """Tests for MLTracker helper class."""

    def test_track_routing_decision(self, sample_features):
        """Sollte Routing-Entscheidung tracken."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_drift:
            detector = Mock()
            mock_drift.return_value = detector

            with patch('app.ml.metrics.get_ml_metrics') as mock_metrics:
                metrics = Mock()
                mock_metrics.return_value = metrics

                from app.workers.tasks.ml_tasks import ml_tracker

                ml_tracker.track_routing_decision(
                    document_id="doc-123",
                    features=sample_features,
                    selected_backend="deepseek",
                    confidence=0.95,
                    routing_method="ml",
                    latency_ms=50.0,
                )

                detector.add_sample.assert_called_once()
                metrics.record_routing_request.assert_called_once()

    def test_track_routing_handles_errors(self, sample_features):
        """Sollte Fehler beim Tracking abfangen."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_drift:
            mock_drift.side_effect = Exception("Service unavailable")

            from app.workers.tasks.ml_tasks import ml_tracker

            # Should not raise
            ml_tracker.track_routing_decision(
                document_id="doc-123",
                features=sample_features,
                selected_backend="deepseek",
                confidence=0.9,
                routing_method="ml",
                latency_ms=50.0,
            )

    def test_track_ocr_result(self):
        """Sollte OCR-Ergebnis tracken."""
        with patch('app.ml.metrics.get_ml_metrics') as mock_metrics:
            metrics = Mock()
            mock_metrics.return_value = metrics

            with patch('app.ml.ab_testing.get_ab_test_manager') as mock_ab:
                ab_manager = Mock()
                ab_manager.get_active_experiments.return_value = []
                mock_ab.return_value = ab_manager

                from app.workers.tasks.ml_tasks import ml_tracker

                ml_tracker.track_ocr_result(
                    document_id="doc-123",
                    backend="deepseek",
                    success=True,
                    processing_time_ms=1500.0,
                    accuracy=0.95,
                    language="de",
                    document_type="invoice",
                )

                metrics.record_backend_request.assert_called_once()

    def test_get_routing_explanation(self, sample_features):
        """Sollte SHAP-Erklaerung generieren."""
        with patch('app.ml.shap_explainer.get_shap_explainer') as mock_shap:
            explainer = Mock()
            explanation = Mock()
            explanation.to_dict.return_value = {
                "feature_contributions": {"complexity_score": 0.3},
            }
            explainer.explain_routing.return_value = explanation
            mock_shap.return_value = explainer

            from app.workers.tasks.ml_tasks import ml_tracker

            result = ml_tracker.get_routing_explanation(
                document_id="doc-123",
                features=sample_features,
                selected_backend="deepseek",
                confidence=0.9,
                all_probabilities={"deepseek": 0.9, "got_ocr": 0.1},
            )

            assert result is not None
            assert "feature_contributions" in result


# ========================= run_drift_detection Tests =========================


class TestRunDriftDetection:
    """Tests for drift detection task."""

    def test_drift_detection_success(self, mock_celery_task, sample_drift_report):
        """Sollte Drift erfolgreich erkennen."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_get:
            detector = Mock()
            detector.detect_drift.return_value = sample_drift_report
            mock_get.return_value = detector

            with patch('app.ml.metrics.get_ml_metrics') as mock_metrics:
                metrics = Mock()
                mock_metrics.return_value = metrics

                from app.workers.tasks.ml_tasks import run_drift_detection

                result = run_drift_detection.run()

                assert result["overall_drift_score"] == 0.35
                metrics.record_drift_score.assert_called_once()

    def test_drift_detection_records_severity(self, mock_celery_task, sample_drift_report):
        """Sollte Schweregrad aufzeichnen."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_get:
            detector = Mock()
            detector.detect_drift.return_value = sample_drift_report
            mock_get.return_value = detector

            with patch('app.ml.metrics.get_ml_metrics') as mock_metrics:
                metrics = Mock()
                mock_metrics.return_value = metrics

                from app.workers.tasks.ml_tasks import run_drift_detection

                run_drift_detection.run()

                call_args = metrics.record_drift_score.call_args
                assert call_args[1]["severity"] == "low"


# ========================= update_ml_metrics Tests =========================


class TestUpdateMLMetrics:
    """Tests for ML metrics update task."""

    def test_metrics_update_success(self, mock_celery_task):
        """Sollte Metriken erfolgreich aktualisieren."""
        with patch('app.ml.metrics.get_ml_metrics') as mock_get_metrics:
            metrics = Mock()
            mock_get_metrics.return_value = metrics

            with patch('app.ml.ab_testing.get_ab_test_manager') as mock_get_ab:
                ab_manager = Mock()
                ab_manager.get_active_experiments.return_value = []
                mock_get_ab.return_value = ab_manager

                with patch('app.ml.drift_detector.get_drift_detector') as mock_get_drift:
                    detector = Mock()
                    detector.get_current_status.return_value = {
                        "ready_for_detection": True,
                        "reference_samples": 1000,
                        "current_samples": 500,
                    }
                    mock_get_drift.return_value = detector

                    from app.workers.tasks.ml_tasks import update_ml_metrics

                    result = update_ml_metrics.run()

                    assert "timestamp" in result
                    assert result["active_experiments"] == 0
                    metrics.update_gpu_metrics.assert_called_once()

    def test_metrics_update_handles_error(self, mock_celery_task):
        """Sollte Fehler abfangen."""
        with patch('app.ml.metrics.get_ml_metrics') as mock_get:
            mock_get.side_effect = Exception("Metrics error")

            from app.workers.tasks.ml_tasks import update_ml_metrics

            result = update_ml_metrics.run()

            assert "error" in result


# ========================= check_experiment_completion Tests =========================


class TestCheckExperimentCompletion:
    """Tests for experiment completion check."""

    def test_check_finds_expired_experiments(self, mock_celery_task, sample_experiment):
        """Sollte abgelaufene Experimente finden."""
        sample_experiment.end_time = datetime.now(timezone.utc) - timedelta(days=1)

        with patch('app.ml.ab_testing.get_ab_test_manager') as mock_get:
            ab_manager = Mock()
            ab_manager.get_active_experiments.return_value = [sample_experiment]
            ab_manager.conclude_experiment.return_value = "deepseek"
            mock_get.return_value = ab_manager

            from app.workers.tasks.ml_tasks import check_experiment_completion

            result = check_experiment_completion.run()

            assert len(result["completed"]) == 1
            assert result["completed"][0]["winner"] == "deepseek"

    def test_check_finds_significant_experiments(self, mock_celery_task, sample_experiment):
        """Sollte signifikante Experimente finden."""
        sample_experiment.significance_reached = True

        with patch('app.ml.ab_testing.get_ab_test_manager') as mock_get:
            ab_manager = Mock()
            ab_manager.get_active_experiments.return_value = [sample_experiment]
            ab_manager.conclude_experiment.return_value = "got_ocr"
            mock_get.return_value = ab_manager

            from app.workers.tasks.ml_tasks import check_experiment_completion

            result = check_experiment_completion.run()

            assert len(result["completed"]) == 1
            assert "Signifikanz" in result["completed"][0]["reason"]

    def test_check_no_completed_experiments(self, mock_celery_task, sample_experiment):
        """Sollte keine Experimente abschliessen wenn nicht faellig."""
        with patch('app.ml.ab_testing.get_ab_test_manager') as mock_get:
            ab_manager = Mock()
            ab_manager.get_active_experiments.return_value = [sample_experiment]
            mock_get.return_value = ab_manager

            from app.workers.tasks.ml_tasks import check_experiment_completion

            with patch.object(check_experiment_completion, 'request', mock_celery_task.request):
                result = check_experiment_completion(mock_celery_task)

                assert len(result["completed"]) == 0


# ========================= trigger_model_retrain Tests =========================


class TestTriggerModelRetrain:
    """Tests for model retrain trigger."""

    def test_retrain_triggered_on_high_drift(self, mock_celery_task, sample_drift_report):
        """Sollte Retraining bei hohem Drift triggern."""
        sample_drift_report.overall_drift_score = 0.7
        sample_drift_report.severity.value = "high"

        with patch('app.ml.drift_detector.get_drift_detector') as mock_get:
            detector = Mock()
            detector.get_drift_history.return_value = [sample_drift_report]
            detector.reset_reference_window = Mock()
            mock_get.return_value = detector

            from app.workers.tasks.ml_tasks import trigger_model_retrain

            with patch.object(trigger_model_retrain, 'request', mock_celery_task.request):
                result = trigger_model_retrain(mock_celery_task, drift_threshold=0.5)

                assert result["should_retrain"] is True
                assert result["retrain_triggered"] is True
                detector.reset_reference_window.assert_called_once()

    def test_retrain_not_triggered_low_drift(self, mock_celery_task, sample_drift_report):
        """Sollte kein Retraining bei niedrigem Drift triggern."""
        sample_drift_report.overall_drift_score = 0.2
        sample_drift_report.severity.value = "low"

        with patch('app.ml.drift_detector.get_drift_detector') as mock_get:
            detector = Mock()
            detector.get_drift_history.return_value = [sample_drift_report]
            mock_get.return_value = detector

            from app.workers.tasks.ml_tasks import trigger_model_retrain

            with patch.object(trigger_model_retrain, 'request', mock_celery_task.request):
                result = trigger_model_retrain(mock_celery_task, drift_threshold=0.5)

                assert result["should_retrain"] is False

    def test_retrain_forced(self, mock_celery_task, sample_drift_report):
        """Sollte Retraining bei force=True triggern."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_get:
            detector = Mock()
            detector.get_drift_history.return_value = [sample_drift_report]
            detector.reset_reference_window = Mock()
            mock_get.return_value = detector

            from app.workers.tasks.ml_tasks import trigger_model_retrain

            with patch.object(trigger_model_retrain, 'request', mock_celery_task.request):
                result = trigger_model_retrain(mock_celery_task, force=True)

                assert result["should_retrain"] is True
                assert "Manuell" in result["reason"]


# ========================= generate_ml_report Tests =========================


class TestGenerateMLReport:
    """Tests for ML report generation."""

    def test_report_generation_success(self, mock_celery_task, sample_experiment):
        """Sollte Report erfolgreich generieren."""
        with patch('app.ml.drift_detector.get_drift_detector') as mock_drift:
            detector = Mock()
            detector.get_current_status.return_value = {"ready_for_detection": True}
            detector.get_drift_history.return_value = []
            mock_drift.return_value = detector

            with patch('app.ml.ab_testing.get_ab_test_manager') as mock_ab:
                ab_manager = Mock()
                ab_manager.get_active_experiments.return_value = [sample_experiment]
                ab_manager.list_experiments.return_value = []
                mock_ab.return_value = ab_manager

                with patch('app.ml.shap_explainer.get_shap_explainer') as mock_shap:
                    explainer = Mock()
                    explainer.get_global_importance.return_value = {"complexity_score": 0.5}
                    mock_shap.return_value = explainer

                    from app.workers.tasks.ml_tasks import generate_ml_report

                    with patch.object(generate_ml_report, 'request', mock_celery_task.request):
                        result = generate_ml_report(mock_celery_task)

                        assert "generated_at" in result
                        assert "drift" in result
                        assert "experiments" in result
                        assert "feature_importance" in result

    def test_report_includes_recommendations(self, mock_celery_task, sample_drift_report, sample_experiment):
        """Sollte Empfehlungen enthalten."""
        sample_drift_report.severity.value = "high"

        with patch('app.ml.drift_detector.get_drift_detector') as mock_drift:
            detector = Mock()
            detector.get_current_status.return_value = {"ready_for_detection": True}
            detector.get_drift_history.return_value = [sample_drift_report]
            mock_drift.return_value = detector

            with patch('app.ml.ab_testing.get_ab_test_manager') as mock_ab:
                ab_manager = Mock()
                ab_manager.get_active_experiments.return_value = []
                ab_manager.list_experiments.return_value = []
                mock_ab.return_value = ab_manager

                with patch('app.ml.shap_explainer.get_shap_explainer') as mock_shap:
                    explainer = Mock()
                    explainer.get_global_importance.return_value = {}
                    mock_shap.return_value = explainer

                    from app.workers.tasks.ml_tasks import generate_ml_report

                    with patch.object(generate_ml_report, 'request', mock_celery_task.request):
                        result = generate_ml_report(mock_celery_task)

                        assert len(result["recommendations"]) > 0
                        assert "Retraining" in result["recommendations"][0]


# ========================= Celery Beat Schedule Tests =========================


class TestCeleryBeatSchedule:
    """Tests for Celery Beat schedule configuration."""

    def test_schedule_contains_required_tasks(self):
        """Sollte alle erforderlichen Tasks enthalten."""
        from app.workers.tasks.ml_tasks import CELERY_BEAT_ML_SCHEDULE

        assert "ml-drift-detection-hourly" in CELERY_BEAT_ML_SCHEDULE
        assert "ml-metrics-update" in CELERY_BEAT_ML_SCHEDULE
        assert "ml-experiment-check" in CELERY_BEAT_ML_SCHEDULE
        assert "ml-report-daily" in CELERY_BEAT_ML_SCHEDULE

    def test_schedule_intervals_reasonable(self):
        """Sollte vernuenftige Intervalle haben."""
        from app.workers.tasks.ml_tasks import CELERY_BEAT_ML_SCHEDULE

        # Drift detection hourly
        assert CELERY_BEAT_ML_SCHEDULE["ml-drift-detection-hourly"]["schedule"] == 3600.0

        # Metrics update frequently
        assert CELERY_BEAT_ML_SCHEDULE["ml-metrics-update"]["schedule"] <= 60.0

        # Experiment check every 5 minutes
        assert CELERY_BEAT_ML_SCHEDULE["ml-experiment-check"]["schedule"] == 300.0

        # Report daily
        assert CELERY_BEAT_ML_SCHEDULE["ml-report-daily"]["schedule"] == 86400.0
