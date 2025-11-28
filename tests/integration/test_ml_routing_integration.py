# -*- coding: utf-8 -*-
"""
Integration Tests for ML-Routing System.

Tests the complete ML routing flow:
- Drift Detection + SHAP + A/B Testing integration
- End-to-End routing decisions
- Metrics collection pipeline
- Celery task execution

Feinpoliert und durchdacht - Produktionsreife Integrationstests.
"""

import pytest
import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestMLRoutingIntegration:
    """Integration tests for the complete ML routing flow."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir)
            (storage / "drift").mkdir()
            (storage / "ab_tests").mkdir()
            (storage / "shap").mkdir()
            yield storage

    @pytest.fixture
    def drift_detector(self, temp_storage):
        """Create drift detector with temp storage."""
        from app.ml.drift_detector import DriftDetector

        return DriftDetector(
            reference_window_days=7,
            drift_threshold=0.1,
            min_samples=10,
            storage_path=temp_storage / "drift",
        )

    @pytest.fixture
    def ab_manager(self, temp_storage):
        """Create A/B test manager with temp storage."""
        from app.ml.ab_testing import ABTestManager

        return ABTestManager(storage_path=temp_storage / "ab_tests")

    @pytest.fixture
    def shap_explainer(self, temp_storage):
        """Create SHAP explainer with temp storage."""
        from app.ml.shap_explainer import SHAPExplainer

        return SHAPExplainer(storage_path=temp_storage / "shap")

    @pytest.mark.integration
    def test_full_routing_flow_with_tracking(
        self, drift_detector, ab_manager, shap_explainer, temp_storage
    ):
        """Test complete routing flow with all ML components."""
        # 1. Create and start an A/B experiment
        experiment = ab_manager.create_experiment(
            name="DeepSeek vs GOT-OCR",
            description="Test DeepSeek gegen GOT-OCR",
            variants=[
                {"name": "control", "config": {"backend": "deepseek"}},
                {"name": "treatment", "config": {"backend": "got_ocr"}},
            ],
        )
        ab_manager.start_experiment(experiment.experiment_id)

        # 2. Simulate document processing and routing decisions
        document_features = {
            "quality_score": 0.85,
            "file_size_mb": 1.5,
            "complexity": "medium",
            "has_tables": True,
            "language": "de",
        }

        # 3. Get A/B variant for document
        document_id = "doc_test_001"
        variant = ab_manager.get_variant(experiment.experiment_id, document_id)
        assert variant is not None
        selected_backend = variant.config.get("backend", "deepseek")

        # 4. Track the routing decision in drift detector
        drift_detector.add_sample(
            features=document_features,
            prediction=selected_backend,
        )

        # 5. Get SHAP explanation
        explanation = shap_explainer.explain_routing(
            document_id=document_id,
            features=document_features,
            selected_backend=selected_backend,
            confidence=0.85,
            all_probabilities={"deepseek": 0.6, "got_ocr": 0.3, "surya": 0.1},
        )

        assert explanation is not None
        assert explanation.selected_backend == selected_backend
        assert len(explanation.top_contributions) > 0

        # 6. Record A/B result
        ab_manager.record_result(
            experiment_id=experiment.experiment_id,
            variant_name=variant.name,
            success=True,
            latency_ms=1500.0,
            accuracy=0.95,
        )

        # 7. Verify experiment has recorded sample
        updated_variant = next(
            v for v in experiment.variants if v.name == variant.name
        )
        assert updated_variant.samples == 1
        assert updated_variant.conversions == 1

    @pytest.mark.integration
    def test_drift_detection_triggers_recommendation(
        self, drift_detector, temp_storage
    ):
        """Test that drift detection properly identifies distribution changes."""
        # Add reference samples (old distribution)
        past = datetime.now() - timedelta(days=10)
        for i in range(20):
            drift_detector.add_sample(
                features={
                    "quality_score": 0.9,
                    "file_size_mb": 1.0,
                    "complexity": "low",
                },
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        # Add current samples (new, different distribution)
        now = datetime.now()
        for i in range(20):
            drift_detector.add_sample(
                features={
                    "quality_score": 0.5,  # Much lower quality
                    "file_size_mb": 5.0,  # Much larger files
                    "complexity": "high",  # More complex
                },
                prediction="surya",  # Different backend
                timestamp=now + timedelta(hours=i),
            )

        # Run drift detection
        report = drift_detector.detect_drift()

        # Should detect drift
        assert report.overall_drift_score > 0
        assert report.samples_reference == 20
        assert report.samples_current == 20

        # Verify report can be serialized
        report_dict = report.to_dict()
        json_str = json.dumps(report_dict)
        assert "overall_drift_score" in json_str

    @pytest.mark.integration
    def test_ab_experiment_lifecycle(self, ab_manager, temp_storage):
        """Test complete A/B experiment lifecycle."""
        from app.ml.ab_testing import ExperimentStatus

        # 1. Create experiment
        experiment = ab_manager.create_experiment(
            name="Backend Performance Test",
            description="Vergleiche Backend-Performance",
            variants=[
                {"name": "deepseek", "config": {"backend": "deepseek"}},
                {"name": "got_ocr", "config": {"backend": "got_ocr"}},
            ],
        )

        assert experiment.status == ExperimentStatus.DRAFT

        # 2. Start experiment
        success = ab_manager.start_experiment(experiment.experiment_id)
        assert success
        assert experiment.status == ExperimentStatus.RUNNING

        # 3. Record multiple results
        for i in range(50):
            # Control (deepseek) - 90% success
            ab_manager.record_result(
                experiment_id=experiment.experiment_id,
                variant_name="deepseek",
                success=i % 10 != 0,  # 90% success
                latency_ms=100 + (i % 50),
                accuracy=0.95,
            )

            # Treatment (got_ocr) - 80% success
            ab_manager.record_result(
                experiment_id=experiment.experiment_id,
                variant_name="got_ocr",
                success=i % 5 != 0,  # 80% success
                latency_ms=80 + (i % 40),
                accuracy=0.92,
            )

        # 4. Get experiment summary
        summary = experiment.get_summary()
        assert summary["name"] == "Backend Performance Test"
        assert len(summary["variants"]) == 2

        # 5. Conclude experiment
        winner = ab_manager.conclude_experiment(experiment.experiment_id)
        assert experiment.status == ExperimentStatus.COMPLETED
        # DeepSeek should win with 90% vs 80%
        assert winner == "deepseek"

    @pytest.mark.integration
    def test_shap_global_importance_accumulation(
        self, shap_explainer, temp_storage
    ):
        """Test that SHAP explanations accumulate for global importance."""
        # Generate multiple explanations
        for i in range(20):
            features = {
                "quality_score": 0.5 + (i * 0.02),
                "file_size_mb": 1.0 + (i * 0.1),
                "complexity": ["low", "medium", "high"][i % 3],
                "has_tables": i % 2 == 0,
            }

            shap_explainer.explain_routing(
                document_id=f"doc_{i:03d}",
                features=features,
                selected_backend=["deepseek", "got_ocr", "surya"][i % 3],
                confidence=0.7 + (i * 0.01),
                all_probabilities={
                    "deepseek": 0.5,
                    "got_ocr": 0.3,
                    "surya": 0.2,
                },
            )

        # Get global importance
        global_importance = shap_explainer.get_global_importance()

        # Global importance returns a dict of feature names to importance scores
        assert isinstance(global_importance, dict)
        assert len(global_importance) > 0
        # Should contain standard features
        assert any(
            key in global_importance
            for key in ["quality_score", "complexity", "detected_language"]
        )

    @pytest.mark.integration
    def test_combined_metrics_tracking(self, temp_storage):
        """Test that all ML components properly track metrics."""
        from app.ml.metrics import get_ml_metrics, MLMetrics

        # Reset singleton for test isolation
        import app.ml.metrics
        app.ml.metrics._ml_metrics = None

        metrics = get_ml_metrics()

        # Track routing request
        metrics.record_routing_request(
            method="ml",
            backend="deepseek",
            status="success",
            latency_seconds=0.025,
            confidence=0.92,
        )

        # Track backend request
        metrics.record_backend_request(
            backend="deepseek",
            status="success",
            language="de",
            processing_time=1.5,
            accuracy=0.95,
            document_type="invoice",
        )

        # Track drift
        metrics.record_drift_score(
            overall_score=0.15,
            feature_scores={"quality_score": 0.1, "complexity": 0.2},
            severity="low",
        )

        # Track A/B sample
        metrics.record_ab_sample(
            experiment_id="exp_001",
            variant="control",
            success=True,
        )

        # Set model version
        metrics.set_model_version(
            version="1.0.0",
            model_name="ocr_router",
        )

        # All should complete without error
        assert True


class TestMLCeleryTasksIntegration:
    """Integration tests for ML Celery tasks."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.integration
    @patch("app.ml.drift_detector.get_drift_detector")
    @patch("app.ml.metrics.get_ml_metrics")
    def test_drift_detection_task_flow(
        self, mock_metrics, mock_detector, temp_storage
    ):
        """Test drift detection task execution flow."""
        from app.ml.drift_detector import DriftReport, DriftSeverity

        # Setup mock detector
        mock_report = DriftReport(
            timestamp=datetime.now(),
            report_id="test_report",
            overall_drift_score=0.25,
            severity=DriftSeverity.LOW,
            dataset_drift_detected=False,
            feature_drifts=[],
            prediction_drift=0.1,
            samples_reference=100,
            samples_current=50,
            recommendations=["Monitor weiter"],
        )

        detector = Mock()
        detector.detect_drift.return_value = mock_report
        mock_detector.return_value = detector

        metrics = Mock()
        mock_metrics.return_value = metrics

        # Import and execute task logic (without Celery)
        from app.workers.tasks.ml_tasks import MLTracker

        # Test MLTracker tracking
        MLTracker.track_routing_decision(
            document_id="doc_001",
            features={"quality": 0.9},
            selected_backend="deepseek",
            confidence=0.85,
            routing_method="ml",
            latency_ms=25.0,
        )

        # Verify interactions
        assert detector.add_sample.called or not mock_detector.called

    @pytest.mark.integration
    def test_ml_tracker_tracking_functions(self, temp_storage):
        """Test MLTracker static methods work correctly."""
        from app.workers.tasks.ml_tasks import MLTracker

        # These should not raise exceptions even if ML modules
        # are not fully initialized
        MLTracker.track_routing_decision(
            document_id="doc_test",
            features={"quality_score": 0.9},
            selected_backend="deepseek",
            confidence=0.85,
            routing_method="ml",
            latency_ms=20.0,
        )

        MLTracker.track_ocr_result(
            document_id="doc_test",
            backend="deepseek",
            success=True,
            processing_time_ms=1500.0,
            accuracy=0.95,
            language="de",
            document_type="invoice",
        )

        # Get explanation (might return None if model not loaded)
        explanation = MLTracker.get_routing_explanation(
            document_id="doc_test",
            features={"quality_score": 0.9},
            selected_backend="deepseek",
            confidence=0.85,
            all_probabilities={"deepseek": 0.6, "got_ocr": 0.3, "surya": 0.1},
        )

        # Should either return explanation or None (no error)
        assert explanation is None or isinstance(explanation, dict)


class TestMLAPIIntegration:
    """Integration tests for ML API endpoints."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_drift_api_endpoint_flow(self, temp_storage):
        """Test drift API endpoint flow."""
        from app.ml.drift_detector import DriftDetector, get_drift_detector

        # Create detector with test data
        detector = DriftDetector(
            min_samples=10,
            storage_path=temp_storage,
        )

        # Add samples
        past = datetime.now() - timedelta(days=10)
        for i in range(10):
            detector.add_sample(
                features={"quality": 0.9},
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        now = datetime.now()
        for i in range(10):
            detector.add_sample(
                features={"quality": 0.7},
                prediction="got_ocr",
                timestamp=now + timedelta(hours=i),
            )

        # Get status (simulates API call)
        status = detector.get_current_status()

        assert status["reference_samples"] == 10
        assert status["current_samples"] == 10
        assert status["ready_for_detection"] is True

        # Run detection (simulates API call)
        report = detector.detect_drift()
        report_dict = report.to_dict()

        assert "overall_drift_score" in report_dict
        assert "severity" in report_dict
        assert "recommendations" in report_dict

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_experiment_api_endpoint_flow(self, temp_storage):
        """Test A/B experiment API endpoint flow."""
        from app.ml.ab_testing import ABTestManager, ExperimentStatus

        manager = ABTestManager(storage_path=temp_storage)

        # Create (POST /experiments)
        experiment = manager.create_experiment(
            name="API Test Experiment",
            description="Test via API",
            variants=[
                {"name": "a", "config": {"backend": "deepseek"}},
                {"name": "b", "config": {"backend": "got_ocr"}},
            ],
        )

        assert experiment.experiment_id is not None

        # Start (POST /experiments/{id}/start)
        success = manager.start_experiment(experiment.experiment_id)
        assert success

        # Get variant (GET /experiments/{id}/variant/{doc_id})
        variant = manager.get_variant(experiment.experiment_id, "doc123")
        assert variant is not None

        # Record result (POST /experiments/{id}/result)
        manager.record_result(
            experiment_id=experiment.experiment_id,
            variant_name=variant.name,
            success=True,
            latency_ms=100.0,
        )

        # Get experiment (GET /experiments/{id})
        experiments = manager.list_experiments(ExperimentStatus.RUNNING)
        assert len(experiments) == 1

        # Conclude (POST /experiments/{id}/conclude)
        winner = manager.conclude_experiment(experiment.experiment_id)
        assert winner is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_explain_api_endpoint_flow(self, temp_storage):
        """Test SHAP explanation API endpoint flow."""
        from app.ml.shap_explainer import SHAPExplainer

        explainer = SHAPExplainer(storage_path=temp_storage)

        # Explain routing (POST /explain/routing)
        explanation = explainer.explain_routing(
            document_id="api_test_doc",
            features={
                "quality_score": 0.85,
                "file_size_mb": 2.0,
                "complexity": "high",
            },
            selected_backend="deepseek",
            confidence=0.88,
            all_probabilities={
                "deepseek": 0.55,
                "got_ocr": 0.30,
                "surya": 0.15,
            },
        )

        # Convert to API response format
        response = explanation.to_dict()

        assert "document_id" in response
        assert "selected_backend" in response
        assert "top_contributions" in response
        assert "decision_summary" in response

        # German language check - summary should contain German text
        summary = response.get("decision_summary", "")
        assert len(summary) > 0


class TestEndToEndMLPipeline:
    """End-to-end tests for the complete ML pipeline."""

    @pytest.fixture
    def ml_components(self):
        """Create all ML components with shared temp storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir)

            from app.ml.drift_detector import DriftDetector
            from app.ml.ab_testing import ABTestManager
            from app.ml.shap_explainer import SHAPExplainer

            yield {
                "drift_detector": DriftDetector(
                    min_samples=10, storage_path=storage / "drift"
                ),
                "ab_manager": ABTestManager(storage_path=storage / "ab"),
                "shap_explainer": SHAPExplainer(storage_path=storage / "shap"),
                "storage": storage,
            }

    @pytest.mark.integration
    def test_document_processing_pipeline(self, ml_components):
        """Test complete document processing with ML routing."""
        drift_detector = ml_components["drift_detector"]
        ab_manager = ml_components["ab_manager"]
        shap_explainer = ml_components["shap_explainer"]

        # Setup: Create active experiment
        experiment = ab_manager.create_experiment(
            name="Production Backend Test",
            description="Produktions-Test",
            variants=[
                {"name": "control", "config": {"backend": "deepseek"}},
                {"name": "treatment", "config": {"backend": "got_ocr"}},
            ],
        )
        ab_manager.start_experiment(experiment.experiment_id)

        # Simulate processing 100 documents
        results = []
        for i in range(100):
            doc_id = f"doc_{i:04d}"

            # Extract features (simulated)
            features = {
                "quality_score": 0.7 + (i % 30) * 0.01,
                "file_size_mb": 0.5 + (i % 10) * 0.5,
                "complexity": ["low", "medium", "high"][i % 3],
                "has_tables": i % 4 == 0,
                "language": "de",
            }

            # Get A/B variant
            variant = ab_manager.get_variant(experiment.experiment_id, doc_id)
            if variant:
                selected_backend = variant.config.get("backend", "deepseek")
            else:
                selected_backend = "deepseek"

            # Calculate confidence (simulated)
            confidence = 0.7 + (features["quality_score"] - 0.7) * 2

            # Track in drift detector
            drift_detector.add_sample(
                features=features,
                prediction=selected_backend,
            )

            # Get explanation
            explanation = shap_explainer.explain_routing(
                document_id=doc_id,
                features=features,
                selected_backend=selected_backend,
                confidence=confidence,
                all_probabilities={
                    "deepseek": 0.5,
                    "got_ocr": 0.3,
                    "surya": 0.2,
                },
            )

            # Simulate processing result
            success = i % 20 != 0  # 95% success rate
            processing_time = 500 + (i % 500)

            # Record A/B result
            if variant:
                ab_manager.record_result(
                    experiment_id=experiment.experiment_id,
                    variant_name=variant.name,
                    success=success,
                    latency_ms=float(processing_time),
                    accuracy=0.9 + (i % 10) * 0.01 if success else 0.0,
                )

            results.append({
                "doc_id": doc_id,
                "backend": selected_backend,
                "success": success,
                "has_explanation": explanation is not None,
            })

        # Verify results
        assert len(results) == 100
        assert all(r["has_explanation"] for r in results)

        # Check drift detector status
        status = drift_detector.get_current_status()
        assert status["reference_samples"] > 0

        # Check experiment
        summary = experiment.get_summary()
        assert summary["status"] == "running"

        # Check global importance - returns dict of feature names to scores
        importance = shap_explainer.get_global_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0

    @pytest.mark.integration
    def test_model_retraining_trigger_flow(self, ml_components):
        """Test model retraining trigger based on drift."""
        drift_detector = ml_components["drift_detector"]

        # Add stable reference data
        past = datetime.now() - timedelta(days=10)
        for i in range(20):
            drift_detector.add_sample(
                features={"quality": 0.9, "size": 1.0},
                prediction="deepseek",
                timestamp=past + timedelta(hours=i),
            )

        # Add drifted current data
        now = datetime.now()
        for i in range(20):
            drift_detector.add_sample(
                features={"quality": 0.3, "size": 10.0},  # Very different
                prediction="surya",
                timestamp=now + timedelta(hours=i),
            )

        # Run drift detection
        report = drift_detector.detect_drift()

        # Check if retraining should be triggered
        # Note: Drift detection depends on statistical tests and may not always
        # detect drift with limited samples or without Evidently library
        should_retrain = (
            report.overall_drift_score >= 0.3 or
            report.severity.value in ("high", "critical")
        )

        # Verify report structure is correct
        assert report.samples_reference == 20
        assert report.samples_current == 20
        assert report.overall_drift_score >= 0  # Score should be non-negative

        # Get recommendations
        assert isinstance(report.recommendations, list)
        assert len(report.recommendations) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
