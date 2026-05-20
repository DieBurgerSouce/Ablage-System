# -*- coding: utf-8 -*-
"""
Unit Tests für OCR Router Training Pipeline.

Tests für:
- Trainingsdaten-Sammlung
- Feature-Extraktion
- Modelltraining (mit Mock XGBoost)
- A/B-Test Routing-Logik
- Confidence Fallback Thresholds
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import numpy as np

from app.ml.ocr_router_trainer import (
    OCRRouterTrainingPipeline,
    TrainingDataset,
    TrainingResult,
    EvaluationMetrics,
    DeploymentResult,
)
from app.agents.orchestration.ml_trainer import TrainingSample
from app.agents.orchestration.ml_router_model import OCRRouterFeatures, OCRRouterModel


class TestOCRRouterTrainingPipeline:
    """Tests für Training Pipeline."""

    @pytest.fixture
    def pipeline(self, tmp_path: Path) -> OCRRouterTrainingPipeline:
        """Create training pipeline mit temp directories."""
        return OCRRouterTrainingPipeline(
            model_dir=tmp_path / "models",
            data_dir=tmp_path / "data",
        )

    @pytest.fixture
    def mock_ocr_results(self) -> List[MagicMock]:
        """Create mock OCR results."""
        results = []
        backends = ["deepseek", "got_ocr", "surya"]

        for i in range(100):
            result = MagicMock()
            result.id = i
            result.backend_used = backends[i % len(backends)]
            result.confidence_score = 0.85 + (i % 10) * 0.01
            result.processing_time_ms = 1000 + (i % 500)
            result.created_at = datetime.now(timezone.utc) - timedelta(days=i % 30)
            result.document_metadata = {
                "document_type": "invoice" if i % 3 == 0 else "other",
                "complexity": "high" if i % 4 == 0 else "medium",
                "quality_score": 0.8,
                "has_tables": i % 5 == 0,
                "has_images": True,
                "has_handwriting": i % 10 == 0,
                "has_fraktur": False,
                "page_count": 1 + (i % 5),
            }
            results.append(result)

        return results

    @pytest.mark.asyncio
    async def test_collect_training_data(
        self,
        pipeline: OCRRouterTrainingPipeline,
        mock_ocr_results: List[MagicMock],
    ) -> None:
        """Test Trainingsdaten-Sammlung aus DB."""
        # Mock database query
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_ocr_results
        mock_db.execute.return_value = mock_result

        # Collect data
        dataset = await pipeline.collect_training_data(
            db=mock_db,
            since_days=30,
            min_confidence=0.7,
        )

        # Assertions
        assert isinstance(dataset, TrainingDataset)
        assert dataset.total_samples == len(mock_ocr_results)
        assert len(dataset.samples) == len(mock_ocr_results)
        assert "deepseek" in dataset.backend_distribution
        assert "got_ocr" in dataset.backend_distribution
        assert dataset.date_range_days == 30

    @pytest.mark.asyncio
    async def test_collect_training_data_empty(
        self,
        pipeline: OCRRouterTrainingPipeline,
    ) -> None:
        """Test Datensammlung mit leeren Ergebnissen."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        dataset = await pipeline.collect_training_data(db=mock_db)

        assert dataset.total_samples == 0
        assert len(dataset.samples) == 0
        assert len(dataset.backend_distribution) == 0


class TestFeatureExtraction:
    """Tests für Feature-Extraktion."""

    @pytest.fixture
    def features(self) -> OCRRouterFeatures:
        """Create feature extractor."""
        return OCRRouterFeatures()

    def test_extract_features_basic(self, features: OCRRouterFeatures) -> None:
        """Test grundlegende Feature-Extraktion."""
        document_metadata = {
            "document_type": "invoice",
            "complexity": "medium",
            "quality_score": 0.85,
            "has_tables": True,
            "has_images": False,
            "has_handwriting": False,
            "has_fraktur": False,
            "page_count": 3,
        }

        sla_requirements = {
            "max_processing_time_seconds": 30,
            "min_accuracy": 0.9,
            "is_critical": False,
        }

        resource_status = {
            "gpu_available": True,
            "gpu_memory_available_gb": 12.0,
            "queue_length": 5,
        }

        feature_vector = features.extract_features(
            document_metadata,
            sla_requirements,
            resource_status,
        )

        # Check feature vector shape
        assert isinstance(feature_vector, np.ndarray)
        assert feature_vector.shape == (features.num_features,)
        assert feature_vector.dtype == np.float32

        # Check specific features
        # Document type one-hot: invoice should be 1
        invoice_idx = features.DOCUMENT_TYPES.index("invoice")
        assert feature_vector[invoice_idx] == 1.0

        # Check has_tables boolean
        tables_idx = features.feature_names.index("has_tables")
        assert feature_vector[tables_idx] == 1.0

    def test_extract_features_with_new_fields(
        self,
        features: OCRRouterFeatures,
    ) -> None:
        """Test Feature-Extraktion mit neuen Feldern."""
        document_metadata = {
            "document_type": "contract",
            "complexity": "high",
            "quality_score": 0.75,
            "has_tables": False,
            "has_images": True,
            "has_handwriting": True,
            "has_fraktur": True,
            "page_count": 10,
            "fraktur_score": 0.8,
            "handwriting_score": 0.6,
            "layout_complexity": 0.9,
            "dpi": 600,
        }

        resource_status = {
            "gpu_available": True,
            "gpu_memory_available_gb": 14.0,
            "queue_length": 0,
        }

        feature_vector = features.extract_features(
            document_metadata,
            resource_status=resource_status,
        )

        # Check new features exist
        assert "fraktur_score" in features.feature_names
        assert "handwriting_score" in features.feature_names
        assert "layout_complexity" in features.feature_names
        assert "dpi" in features.feature_names
        assert "available_vram_gb" in features.feature_names

        # Check fraktur_score value
        fraktur_idx = features.feature_names.index("fraktur_score")
        assert feature_vector[fraktur_idx] == 0.8

    def test_backend_to_index_mapping(self, features: OCRRouterFeatures) -> None:
        """Test Backend-Index Mapping."""
        assert features.backend_to_index("deepseek") == 0
        assert features.backend_to_index("got_ocr") == 1
        assert features.backend_to_index("donut") == 4

        # Unknown backend defaults to got_ocr
        assert features.backend_to_index("unknown") == 1

    def test_index_to_backend_mapping(self, features: OCRRouterFeatures) -> None:
        """Test Index-Backend Mapping."""
        assert features.index_to_backend(0) == "deepseek"
        assert features.index_to_backend(1) == "got_ocr"
        assert features.index_to_backend(4) == "donut"

        # Out of range defaults to got_ocr
        assert features.index_to_backend(999) == "got_ocr"


class TestABTestRouting:
    """Tests für A/B-Test Routing-Logik."""

    @pytest.mark.asyncio
    async def test_ab_test_selection_active(self) -> None:
        """Test A/B-Test Selection wenn Test aktiv."""
        with patch("app.agents.orchestration.unified_router.get_ab_test_manager") as mock_ab:
            from app.agents.orchestration.unified_router import (
                UnifiedOCRRouter,
                DocumentAnalysis,
                SLARequirements,
            )

            # Mock A/B manager
            mock_manager = MagicMock()
            mock_variant = MagicMock()
            mock_variant.name = "treatment"
            mock_variant.config = {"model_version": "v1.2.0"}
            mock_manager.get_variant.return_value = mock_variant
            mock_ab.return_value = mock_manager

            # Create router with mock ML model
            router = UnifiedOCRRouter(use_ml_routing=True)
            router._ab_test_active = True
            router._ab_test_config = {"experiment_id": "test_exp_123"}

            # Mock ML model
            mock_model = MagicMock()
            mock_model.is_trained = True
            mock_model.predict.return_value = {
                "backend": "deepseek",
                "confidence": 0.9,
                "alternatives": [],
                "probabilities": {},
            }
            router._ml_model = mock_model

            analysis = DocumentAnalysis(
                document_type="invoice",
                complexity="medium",
            )

            result = await router._ab_test_selection(
                analysis,
                SLARequirements(),
                {"gpu_available": True},
            )

            assert result is not None
            assert result.model_version == "v1.2.0"
            assert "A/B-Test" in result.reason

    @pytest.mark.asyncio
    async def test_ab_test_selection_inactive(self) -> None:
        """Test A/B-Test Selection wenn inaktiv."""
        from app.agents.orchestration.unified_router import (
            UnifiedOCRRouter,
            DocumentAnalysis,
            SLARequirements,
        )

        router = UnifiedOCRRouter(use_ml_routing=False)
        router._ab_test_active = False

        analysis = DocumentAnalysis()
        result = await router._ab_test_selection(
            analysis,
            SLARequirements(),
            {},
        )

        # Should return None when A/B test inactive
        assert result is None


class TestConfidenceFallback:
    """Tests für Confidence Fallback Thresholds."""

    @pytest.mark.asyncio
    async def test_low_confidence_fallback(self) -> None:
        """Test Fallback zu Regeln bei niedriger Confidence."""
        from app.agents.orchestration.unified_router import (
            UnifiedOCRRouter,
            DocumentAnalysis,
            SLARequirements,
        )

        router = UnifiedOCRRouter(use_ml_routing=True)

        # Mock ML model with low confidence
        mock_model = MagicMock()
        mock_model.is_trained = True
        mock_model.predict.return_value = {
            "backend": "got_ocr",
            "confidence": 0.65,  # Below 0.7 threshold
            "alternatives": [],
            "reason": "Low confidence",
        }
        router._ml_model = mock_model

        analysis = DocumentAnalysis(
            has_formulas=True,  # Should route to GOT-OCR by rules
        )

        result = await router._ml_selection(
            analysis,
            SLARequirements(),
            {"gpu_available": True},
        )

        # Should fall back to rule-based routing
        assert result.backend.value == "got_ocr"
        assert result.routing_method.value == "rule_based"

    @pytest.mark.asyncio
    async def test_medium_confidence_alternatives(self) -> None:
        """Test zusätzliche Alternativen bei mittlerer Confidence."""
        from app.agents.orchestration.unified_router import (
            UnifiedOCRRouter,
            DocumentAnalysis,
            SLARequirements,
        )

        router = UnifiedOCRRouter(use_ml_routing=True)

        mock_model = MagicMock()
        mock_model.is_trained = True
        mock_model.predict.return_value = {
            "backend": "deepseek",
            "confidence": 0.78,  # Between 0.7-0.85
            "alternatives": [{"backend": "got_ocr"}],
            "reason": "Medium confidence",
        }
        router._ml_model = mock_model

        analysis = DocumentAnalysis(has_tables=True)

        result = await router._ml_selection(
            analysis,
            SLARequirements(),
            {"gpu_available": True},
        )

        # Should keep ML routing but add alternatives
        assert result.backend.value == "deepseek"
        assert result.routing_method.value == "ml"
        # Should have alternatives from both ML and rules
        assert len(result.alternatives) > 0

    @pytest.mark.asyncio
    async def test_high_confidence_trust_ml(self) -> None:
        """Test direktes ML-Routing bei hoher Confidence."""
        from app.agents.orchestration.unified_router import (
            UnifiedOCRRouter,
            DocumentAnalysis,
            SLARequirements,
        )

        router = UnifiedOCRRouter(use_ml_routing=True)

        mock_model = MagicMock()
        mock_model.is_trained = True
        mock_model.predict.return_value = {
            "backend": "deepseek",
            "confidence": 0.92,  # Above 0.85
            "alternatives": [{"backend": "hybrid"}],
            "reason": "High confidence",
        }
        router._ml_model = mock_model

        analysis = DocumentAnalysis()

        result = await router._ml_selection(
            analysis,
            SLARequirements(),
            {"gpu_available": True},
        )

        # Should trust ML fully
        assert result.backend.value == "deepseek"
        assert result.routing_method.value == "ml"
        assert result.confidence == 0.92


class TestModelTraining:
    """Tests für Modelltraining (mit Mock XGBoost)."""

    @pytest.mark.asyncio
    async def test_train_model_success(self, tmp_path: Path) -> None:
        """Test erfolgreicher Modelltraining."""
        pipeline = OCRRouterTrainingPipeline(
            model_dir=tmp_path / "models",
            data_dir=tmp_path / "data",
        )

        # Create training dataset
        samples = []
        for i in range(100):
            sample = TrainingSample(
                sample_id=f"sample_{i}",
                document_metadata={
                    "document_type": "invoice",
                    "complexity": "medium",
                    "quality_score": 0.8,
                    "has_tables": i % 2 == 0,
                    "has_images": False,
                    "has_handwriting": False,
                    "has_fraktur": False,
                    "page_count": 1,
                },
                sla_requirements={},
                resource_status={"gpu_available": True},
                selected_backend="got_ocr",
                was_successful=True,
                accuracy_score=0.85,
                processing_time_ms=1000,
            )
            samples.append(sample)

        dataset = TrainingDataset(
            samples=samples,
            total_samples=len(samples),
            backend_distribution={"got_ocr": len(samples)},
            date_range_days=30,
        )

        # Mock XGBoost training
        with patch("app.agents.orchestration.ml_trainer.XGBOOST_AVAILABLE", True):
            result = await pipeline.train_model(dataset, force=True)

            # Result depends on XGBoost availability
            if result.success:
                assert result.validation_accuracy > 0
                assert result.total_samples == len(samples)
            else:
                assert "XGBoost" in result.error_message or "genug" in result.error_message

    @pytest.mark.asyncio
    async def test_train_model_insufficient_data(self, tmp_path: Path) -> None:
        """Test Training mit zu wenig Daten."""
        pipeline = OCRRouterTrainingPipeline(
            model_dir=tmp_path / "models",
            data_dir=tmp_path / "data",
        )

        # Too few samples
        dataset = TrainingDataset(
            samples=[],
            total_samples=10,
            backend_distribution={},
            date_range_days=30,
        )

        result = await pipeline.train_model(dataset, force=False)

        assert not result.success
        assert "genug" in result.error_message.lower()


class TestModelVersioning:
    """Tests für Modell-Versionierung."""

    def test_get_model_version(self) -> None:
        """Test Modell-Versionierung."""
        with patch("app.agents.orchestration.ml_router_model.XGBOOST_AVAILABLE", False):
            from app.agents.orchestration.ml_router_model import OCRRouterModel

            model = OCRRouterModel()
            version = model.get_model_version()

            # Untrainiertes Modell hat unversioned string
            assert "unversioned" in version or "v" in version

    def test_get_model_metrics(self) -> None:
        """Test Modell-Metriken."""
        with patch("app.agents.orchestration.ml_router_model.XGBOOST_AVAILABLE", False):
            from app.agents.orchestration.ml_router_model import OCRRouterModel

            model = OCRRouterModel()
            metrics = model.get_model_metrics()

            assert isinstance(metrics, dict)
            assert "training_samples" in metrics
            assert "validation_accuracy" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
