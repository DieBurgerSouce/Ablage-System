# -*- coding: utf-8 -*-
"""
Unit-Tests für ML API Endpoints.

Testet:
- Drift Detection Endpoints
- SHAP Explainability Endpoints
- A/B Testing Endpoints
- ML Metrics Endpoints

Feinpoliert und durchdacht - ML-Observability API Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from enum import Enum

from fastapi import HTTPException, Request


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_current_user():
    """Create mock authenticated user."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_superuser = False
    return user


@pytest.fixture
def mock_admin_user():
    """Create mock admin user."""
    user = Mock()
    user.id = uuid4()
    user.email = "admin@example.com"
    user.is_superuser = True
    return user


@pytest.fixture
def mock_request():
    """Create mock HTTP request."""
    request = Mock(spec=Request)
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_drift_detector():
    """Create mock drift detector."""
    detector = Mock()
    detector.get_current_status = Mock(return_value={
        "reference_samples": 1000,
        "current_samples": 500,
        "min_samples_required": 100,
        "ready_for_detection": True,
        "last_report": None,
        "drift_threshold": 0.05,
    })
    return detector


@pytest.fixture
def mock_drift_report():
    """Create mock drift report."""
    class MockSeverity(Enum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    report = Mock()
    report.report_id = str(uuid4())
    report.timestamp = datetime.now(timezone.utc)
    report.overall_drift_score = 0.15
    report.severity = MockSeverity.MEDIUM
    report.dataset_drift_detected = True
    report.feature_drifts = []
    report.prediction_drift = 0.1
    report.samples_reference = 1000
    report.samples_current = 500
    report.recommendations = ["Modell-Retraining empfohlen"]
    return report


@pytest.fixture
def mock_shap_explainer():
    """Create mock SHAP explainer."""
    explainer = Mock()
    return explainer


@pytest.fixture
def mock_ab_test_manager():
    """Create mock A/B test manager."""
    manager = Mock()
    return manager


# ========================= Drift Detection Tests =========================


class TestGetDriftStatus:
    """Tests for GET /ml/drift/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_drift_status_success(self, mock_request, mock_current_user, mock_drift_detector):
        """Sollte Drift-Status zurueckgeben."""
        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            from app.api.v1.ml import get_drift_status

            result = await get_drift_status(mock_request, mock_current_user)

            assert result.reference_samples == 1000
            assert result.current_samples == 500
            assert result.ready_for_detection is True
            mock_drift_detector.get_current_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_drift_status_error(self, mock_request, mock_current_user):
        """Sollte HTTPException bei Fehler werfen."""
        with patch('app.api.v1.ml.get_drift_detector') as mock_get:
            mock_get.side_effect = Exception("Detector error")

            from app.api.v1.ml import get_drift_status

            with pytest.raises(HTTPException) as exc_info:
                await get_drift_status(mock_request, mock_current_user)

            assert exc_info.value.status_code == 500


class TestRunDriftDetection:
    """Tests for POST /ml/drift/detect endpoint."""

    @pytest.mark.asyncio
    async def test_run_drift_detection_success(self, mock_request, mock_current_user, mock_drift_detector, mock_drift_report):
        """Sollte Drift-Detection durchfuehren."""
        mock_drift_detector.detect_drift = Mock(return_value=mock_drift_report)

        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            from app.api.v1.ml import run_drift_detection

            result = await run_drift_detection(mock_request, mock_current_user)

            assert result.overall_drift_score == 0.15
            assert result.severity == "medium"
            assert result.dataset_drift_detected is True
            mock_drift_detector.detect_drift.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_drift_detection_error(self, mock_request, mock_current_user):
        """Sollte HTTPException bei Fehler werfen."""
        with patch('app.api.v1.ml.get_drift_detector') as mock_get:
            mock_get.side_effect = Exception("Detection failed")

            from app.api.v1.ml import run_drift_detection

            with pytest.raises(HTTPException) as exc_info:
                await run_drift_detection(mock_request, mock_current_user)

            assert exc_info.value.status_code == 500


class TestGetDriftHistory:
    """Tests for GET /ml/drift/history endpoint."""

    @pytest.mark.asyncio
    async def test_get_drift_history_success(self, mock_request, mock_current_user, mock_drift_detector, mock_drift_report):
        """Sollte Drift-Historie zurueckgeben."""
        mock_drift_detector.get_drift_history = Mock(return_value=[mock_drift_report])

        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            from app.api.v1.ml import get_drift_history

            result = await get_drift_history(mock_request, limit=10, current_user=mock_current_user)

            assert len(result) == 1
            mock_drift_detector.get_drift_history.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_get_drift_history_empty(self, mock_request, mock_current_user, mock_drift_detector):
        """Sollte leere Liste zurueckgeben."""
        mock_drift_detector.get_drift_history = Mock(return_value=[])

        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            from app.api.v1.ml import get_drift_history

            result = await get_drift_history(mock_request, limit=10, current_user=mock_current_user)

            assert result == []


class TestResetDriftReference:
    """Tests for POST /ml/drift/reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_drift_reference_success(self, mock_request, mock_admin_user, mock_drift_detector):
        """Sollte Drift-Reference zuruecksetzen (Admin)."""
        mock_drift_detector.reset_reference_window = Mock()

        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            from app.api.v1.ml import reset_drift_reference

            result = await reset_drift_reference(mock_request, mock_admin_user)

            assert "erfolgreich" in result["message"]
            mock_drift_detector.reset_reference_window.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_drift_reference_error(self, mock_request, mock_admin_user):
        """Sollte HTTPException bei Fehler werfen."""
        with patch('app.api.v1.ml.get_drift_detector') as mock_get:
            mock_get.side_effect = Exception("Reset failed")

            from app.api.v1.ml import reset_drift_reference

            with pytest.raises(HTTPException) as exc_info:
                await reset_drift_reference(mock_request, mock_admin_user)

            assert exc_info.value.status_code == 500


# ========================= SHAP Explainability Tests =========================


class TestExplainRoutingDecision:
    """Tests for POST /ml/explain/routing endpoint."""

    @pytest.mark.asyncio
    async def test_explain_routing_success(self, mock_request, mock_current_user, mock_shap_explainer):
        """Sollte Routing-Erklaerung erstellen."""
        mock_explanation = Mock()
        mock_explanation.document_id = "doc-123"
        mock_explanation.selected_backend = "deepseek"
        mock_explanation.confidence = 0.95
        mock_explanation.top_contributions = []
        mock_explanation.alternative_backends = [("got_ocr", 0.8)]
        mock_explanation.decision_summary = "Komplexes Layout erkannt"
        mock_explanation.counterfactual = None

        mock_shap_explainer.explain_routing = Mock(return_value=mock_explanation)

        with patch('app.api.v1.ml.get_shap_explainer', return_value=mock_shap_explainer):
            from app.api.v1.ml import explain_routing_decision, ExplainRoutingRequest

            request = ExplainRoutingRequest(
                document_id="doc-123",
                features={"page_count": 5.0, "has_tables": 1.0},
                selected_backend="deepseek",
                confidence=0.95,
                all_probabilities={"deepseek": 0.95, "got_ocr": 0.8},
            )

            result = await explain_routing_decision(mock_request, request, mock_current_user)

            assert result.document_id == "doc-123"
            assert result.selected_backend == "deepseek"
            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_explain_routing_error(self, mock_request, mock_current_user):
        """Sollte HTTPException bei Fehler werfen."""
        with patch('app.api.v1.ml.get_shap_explainer') as mock_get:
            mock_get.side_effect = Exception("Explainer error")

            from app.api.v1.ml import explain_routing_decision, ExplainRoutingRequest

            request = ExplainRoutingRequest(
                document_id="doc-123",
                features={"page_count": 5.0},
                selected_backend="deepseek",
                confidence=0.95,
                all_probabilities={"deepseek": 0.95},
            )

            with pytest.raises(HTTPException) as exc_info:
                await explain_routing_decision(mock_request, request, mock_current_user)

            assert exc_info.value.status_code == 500


class TestGetRoutingExplanation:
    """Tests for GET /ml/explain/{document_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_routing_explanation_success(self, mock_request, mock_current_user, mock_shap_explainer):
        """Sollte gespeicherte Erklaerung zurueckgeben."""
        mock_explanation = Mock()
        mock_explanation.document_id = "doc-123"
        mock_explanation.selected_backend = "deepseek"
        mock_explanation.confidence = 0.95
        mock_explanation.top_contributions = []
        mock_explanation.alternative_backends = []
        mock_explanation.decision_summary = "Test"
        mock_explanation.counterfactual = None

        mock_shap_explainer.get_explanation = Mock(return_value=mock_explanation)

        with patch('app.api.v1.ml.get_shap_explainer', return_value=mock_shap_explainer):
            from app.api.v1.ml import get_routing_explanation

            result = await get_routing_explanation(mock_request, "doc-123", mock_current_user)

            assert result.document_id == "doc-123"

    @pytest.mark.asyncio
    async def test_get_routing_explanation_not_found(self, mock_request, mock_current_user, mock_shap_explainer):
        """Sollte 404 bei nicht gefundener Erklaerung werfen."""
        mock_shap_explainer.get_explanation = Mock(return_value=None)

        with patch('app.api.v1.ml.get_shap_explainer', return_value=mock_shap_explainer):
            from app.api.v1.ml import get_routing_explanation

            with pytest.raises(HTTPException) as exc_info:
                await get_routing_explanation(mock_request, "unknown-doc", mock_current_user)

            assert exc_info.value.status_code == 404


class TestGetGlobalFeatureImportance:
    """Tests for GET /ml/explain/importance endpoint."""

    @pytest.mark.asyncio
    async def test_get_global_feature_importance_success(self, mock_request, mock_current_user, mock_shap_explainer):
        """Sollte Feature-Importance zurueckgeben."""
        mock_shap_explainer.get_global_importance = Mock(return_value={
            "page_count": 0.35,
            "has_tables": 0.25,
            "language": 0.20,
        })

        with patch('app.api.v1.ml.get_shap_explainer', return_value=mock_shap_explainer):
            from app.api.v1.ml import get_global_feature_importance

            result = await get_global_feature_importance(mock_request, mock_current_user)

            assert "page_count" in result.features
            assert result.features["page_count"] == 0.35


# ========================= A/B Testing Tests =========================


class TestCreateExperiment:
    """Tests for POST /ml/experiments endpoint."""

    @pytest.mark.asyncio
    async def test_create_experiment_success(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte Experiment erstellen."""
        mock_experiment = Mock()
        mock_experiment.get_summary = Mock(return_value={
            "experiment_id": "exp-123",
            "name": "Test Experiment",
            "status": "draft",
            "variants": [],
            "total_samples": 0,
            "winner": None,
            "significance_reached": False,
        })

        mock_ab_test_manager.create_experiment = Mock(return_value=mock_experiment)

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import create_experiment, CreateExperimentRequest, VariantConfig

            request = CreateExperimentRequest(
                name="Test Experiment",
                description="Test",
                variants=[
                    VariantConfig(name="control", backend="deepseek", weight=1.0),
                    VariantConfig(name="treatment", backend="got_ocr", weight=1.0),
                ],
                allocation_method="sticky",
                min_samples=100,
            )

            result = await create_experiment(mock_request, request, mock_current_user)

            assert result.experiment_id == "exp-123"
            assert result.name == "Test Experiment"

    @pytest.mark.asyncio
    async def test_create_experiment_invalid_allocation(self, mock_request, mock_current_user):
        """Sollte ValueError bei ungueltiger Allokationsmethode werfen."""
        from app.api.v1.ml import CreateExperimentRequest, VariantConfig

        with pytest.raises(ValueError) as exc_info:
            CreateExperimentRequest(
                name="Test",
                variants=[
                    VariantConfig(name="a", backend="deepseek"),
                    VariantConfig(name="b", backend="got_ocr"),
                ],
                allocation_method="invalid_method",
            )

        assert "Allokationsmethode" in str(exc_info.value)


class TestStartExperiment:
    """Tests for POST /ml/experiments/{experiment_id}/start endpoint."""

    @pytest.mark.asyncio
    async def test_start_experiment_success(self, mock_request, mock_admin_user, mock_ab_test_manager):
        """Sollte Experiment starten (Admin)."""
        mock_ab_test_manager.start_experiment = Mock(return_value=True)

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import start_experiment

            result = await start_experiment(mock_request, "exp-123", mock_admin_user)

            assert "gestartet" in result["message"]
            mock_ab_test_manager.start_experiment.assert_called_once_with("exp-123")

    @pytest.mark.asyncio
    async def test_start_experiment_failed(self, mock_request, mock_admin_user, mock_ab_test_manager):
        """Sollte 400 wenn Start fehlschlaegt."""
        mock_ab_test_manager.start_experiment = Mock(return_value=False)

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import start_experiment

            with pytest.raises(HTTPException) as exc_info:
                await start_experiment(mock_request, "exp-123", mock_admin_user)

            assert exc_info.value.status_code == 400


class TestGetExperiment:
    """Tests for GET /ml/experiments/{experiment_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_experiment_success(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte Experiment-Details zurueckgeben."""
        mock_experiment = Mock()
        mock_experiment.get_summary = Mock(return_value={
            "experiment_id": "exp-123",
            "name": "Test",
            "status": "running",
            "variants": [],
            "total_samples": 100,
            "winner": None,
            "significance_reached": False,
        })

        mock_ab_test_manager.get_experiment = Mock(return_value=mock_experiment)

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import get_experiment

            result = await get_experiment(mock_request, "exp-123", mock_current_user)

            assert result.experiment_id == "exp-123"
            assert result.status == "running"

    @pytest.mark.asyncio
    async def test_get_experiment_not_found(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte 404 bei unbekanntem Experiment werfen."""
        mock_ab_test_manager.get_experiment = Mock(return_value=None)

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import get_experiment

            with pytest.raises(HTTPException) as exc_info:
                await get_experiment(mock_request, "unknown", mock_current_user)

            assert exc_info.value.status_code == 404


class TestListExperiments:
    """Tests for GET /ml/experiments endpoint."""

    @pytest.mark.asyncio
    async def test_list_experiments_success(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte alle Experimente auflisten."""
        mock_experiment = Mock()
        mock_experiment.get_summary = Mock(return_value={
            "experiment_id": "exp-1",
            "name": "Test 1",
            "status": "running",
            "variants": [],
            "total_samples": 50,
            "winner": None,
            "significance_reached": False,
        })

        mock_ab_test_manager.list_experiments = Mock(return_value=[mock_experiment])

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import list_experiments

            result = await list_experiments(mock_request, status=None, current_user=mock_current_user)

            assert len(result) == 1
            assert result[0].experiment_id == "exp-1"

    @pytest.mark.asyncio
    async def test_list_experiments_with_status_filter(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte nach Status filtern."""
        mock_ab_test_manager.list_experiments = Mock(return_value=[])

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            with patch('app.api.v1.ml.ExperimentStatus') as mock_status:
                mock_status.return_value = "running"

                from app.api.v1.ml import list_experiments

                await list_experiments(mock_request, status="running", current_user=mock_current_user)

                mock_ab_test_manager.list_experiments.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_experiments_invalid_status(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte 400 bei ungueltigem Status werfen."""
        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            with patch('app.api.v1.ml.ExperimentStatus') as mock_status:
                mock_status.side_effect = ValueError("Invalid status")

                from app.api.v1.ml import list_experiments

                with pytest.raises(HTTPException) as exc_info:
                    await list_experiments(mock_request, status="invalid", current_user=mock_current_user)

                assert exc_info.value.status_code == 400


class TestRecordExperimentResult:
    """Tests for POST /ml/experiments/{experiment_id}/record endpoint."""

    @pytest.mark.asyncio
    async def test_record_result_success(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte Ergebnis erfassen."""
        mock_ab_test_manager.record_result = Mock()

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import record_experiment_result, RecordResultRequest

            request = RecordResultRequest(
                variant_name="control",
                success=True,
                latency_ms=150.0,
                accuracy=0.95,
            )

            result = await record_experiment_result(mock_request, "exp-123", request, mock_current_user)

            assert "erfasst" in result["message"]
            mock_ab_test_manager.record_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_result_invalid_variant(self, mock_request, mock_current_user, mock_ab_test_manager):
        """Sollte ValueError bei ungueltiger Variante werfen."""
        mock_ab_test_manager.record_result = Mock(side_effect=ValueError("Unknown variant"))

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import record_experiment_result, RecordResultRequest

            request = RecordResultRequest(
                variant_name="unknown",
                success=True,
                latency_ms=150.0,
            )

            with pytest.raises(HTTPException) as exc_info:
                await record_experiment_result(mock_request, "exp-123", request, mock_current_user)

            assert exc_info.value.status_code == 400


class TestConcludeExperiment:
    """Tests for POST /ml/experiments/{experiment_id}/conclude endpoint."""

    @pytest.mark.asyncio
    async def test_conclude_experiment_success(self, mock_request, mock_admin_user, mock_ab_test_manager):
        """Sollte Experiment abschliessen (Admin)."""
        mock_ab_test_manager.conclude_experiment = Mock(return_value="control")

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import conclude_experiment

            result = await conclude_experiment(mock_request, "exp-123", mock_admin_user)

            assert "abgeschlossen" in result["message"]
            assert result["winner"] == "control"

    @pytest.mark.asyncio
    async def test_conclude_experiment_no_significance(self, mock_request, mock_admin_user, mock_ab_test_manager):
        """Sollte ValueError bei fehlender Signifikanz werfen."""
        mock_ab_test_manager.conclude_experiment = Mock(side_effect=ValueError("Not enough samples"))

        with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
            from app.api.v1.ml import conclude_experiment

            with pytest.raises(HTTPException) as exc_info:
                await conclude_experiment(mock_request, "exp-123", mock_admin_user)

            assert exc_info.value.status_code == 400


# ========================= Metrics Tests =========================


class TestGetPrometheusMetrics:
    """Tests for GET /ml/metrics endpoint."""

    @pytest.mark.asyncio
    async def test_get_prometheus_metrics_success(self, mock_request, mock_current_user):
        """Sollte Prometheus-Metriken zurueckgeben."""
        mock_metrics = Mock()
        mock_metrics.update_gpu_metrics = Mock()
        mock_metrics.get_metrics = Mock(return_value="# HELP metric\nmetric 1.0")
        mock_metrics.get_content_type = Mock(return_value="text/plain")

        with patch('app.api.v1.ml.get_ml_metrics', return_value=mock_metrics):
            from app.api.v1.ml import get_prometheus_metrics

            result = await get_prometheus_metrics(mock_request, mock_current_user)

            assert result.media_type == "text/plain"
            mock_metrics.update_gpu_metrics.assert_called_once()


class TestGetMetricsSummary:
    """Tests for GET /ml/metrics/summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_metrics_summary_success(self, mock_request, mock_current_user, mock_drift_detector, mock_ab_test_manager):
        """Sollte Metriken-Zusammenfassung zurueckgeben."""
        mock_drift_detector.get_current_status = Mock(return_value={
            "ready_for_detection": True,
            "last_report": None,
            "current_samples": 500,
        })

        mock_ab_test_manager.get_active_experiments = Mock(return_value=[])

        with patch('app.api.v1.ml.get_drift_detector', return_value=mock_drift_detector):
            with patch('app.api.v1.ml.get_ab_test_manager', return_value=mock_ab_test_manager):
                from app.api.v1.ml import get_metrics_summary

                result = await get_metrics_summary(mock_request, mock_current_user)

                assert "routing" in result.dict()
                assert "backends" in result.dict()
                assert "drift" in result.dict()
                assert "experiments" in result.dict()


# ========================= Request Validation Tests =========================


class TestExplainRoutingRequestValidation:
    """Tests for ExplainRoutingRequest validation."""

    def test_valid_request(self):
        """Sollte gueltige Requests akzeptieren."""
        from app.api.v1.ml import ExplainRoutingRequest

        request = ExplainRoutingRequest(
            document_id="doc-123",
            features={"feature1": 1.0, "feature2": 2.0},
            selected_backend="deepseek",
            confidence=0.95,
            all_probabilities={"deepseek": 0.95, "got_ocr": 0.05},
        )

        assert request.document_id == "doc-123"
        assert request.confidence == 0.95

    def test_invalid_probability_range(self):
        """Sollte ValueError bei ungueltiger Wahrscheinlichkeit werfen."""
        from app.api.v1.ml import ExplainRoutingRequest

        with pytest.raises(ValueError) as exc_info:
            ExplainRoutingRequest(
                document_id="doc-123",
                features={"feature1": 1.0},
                selected_backend="deepseek",
                confidence=0.95,
                all_probabilities={"deepseek": 1.5},  # Invalid: > 1.0
            )

        assert "zwischen 0 und 1" in str(exc_info.value)

    def test_invalid_confidence_range(self):
        """Sollte ValueError bei ungueltiger Konfidenz werfen."""
        from app.api.v1.ml import ExplainRoutingRequest

        with pytest.raises(ValueError):
            ExplainRoutingRequest(
                document_id="doc-123",
                features={"feature1": 1.0},
                selected_backend="deepseek",
                confidence=1.5,  # Invalid: > 1.0
                all_probabilities={"deepseek": 0.95},
            )


class TestCreateExperimentRequestValidation:
    """Tests for CreateExperimentRequest validation."""

    def test_valid_request(self):
        """Sollte gueltige Requests akzeptieren."""
        from app.api.v1.ml import CreateExperimentRequest, VariantConfig

        request = CreateExperimentRequest(
            name="Test Experiment",
            description="A test",
            variants=[
                VariantConfig(name="control", backend="deepseek"),
                VariantConfig(name="treatment", backend="got_ocr"),
            ],
            allocation_method="weighted",
            min_samples=100,
            duration_days=30,
        )

        assert request.name == "Test Experiment"
        assert len(request.variants) == 2

    def test_too_few_variants(self):
        """Sollte ValueError bei zu wenig Varianten werfen."""
        from app.api.v1.ml import CreateExperimentRequest, VariantConfig

        with pytest.raises(ValueError):
            CreateExperimentRequest(
                name="Test",
                variants=[
                    VariantConfig(name="only_one", backend="deepseek"),
                ],  # Need at least 2
            )

    def test_invalid_min_samples(self):
        """Sollte ValueError bei ungueltigen min_samples werfen."""
        from app.api.v1.ml import CreateExperimentRequest, VariantConfig

        with pytest.raises(ValueError):
            CreateExperimentRequest(
                name="Test",
                variants=[
                    VariantConfig(name="a", backend="deepseek"),
                    VariantConfig(name="b", backend="got_ocr"),
                ],
                min_samples=5,  # Min is 10
            )


class TestRecordResultRequestValidation:
    """Tests for RecordResultRequest validation."""

    def test_valid_request(self):
        """Sollte gueltige Requests akzeptieren."""
        from app.api.v1.ml import RecordResultRequest

        request = RecordResultRequest(
            variant_name="control",
            success=True,
            latency_ms=150.0,
            accuracy=0.95,
        )

        assert request.variant_name == "control"
        assert request.success is True

    def test_optional_accuracy(self):
        """Sollte optionale accuracy akzeptieren."""
        from app.api.v1.ml import RecordResultRequest

        request = RecordResultRequest(
            variant_name="control",
            success=True,
            latency_ms=150.0,
            # accuracy not provided
        )

        assert request.accuracy is None

    def test_invalid_latency(self):
        """Sollte ValueError bei negativer Latenz werfen."""
        from app.api.v1.ml import RecordResultRequest

        with pytest.raises(ValueError):
            RecordResultRequest(
                variant_name="control",
                success=True,
                latency_ms=-10.0,  # Invalid: negative
            )
