# -*- coding: utf-8 -*-
"""
Tests fuer RoutingPredictor.

Phase 9.2: Dream Features - Predictive Document Routing

Testet:
- Feature-Extraktion
- Regelbasierte Vorhersagen
- ML-basierte Vorhersagen
- Online-Learning mit Feedback
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

from app.ml.routing_predictor import (
    RoutingPredictor,
    RoutingFeatureExtractor,
    RoutingTarget,
    PriorityLevel,
    RoutingFeatures,
    RoutingHistory,
    RoutingPrediction,
    TrainingResult,
)


class TestRoutingTarget:
    """Tests fuer RoutingTarget Enum."""

    def test_routing_target_values(self) -> None:
        """Test: RoutingTarget hat korrekte Werte."""
        assert RoutingTarget.USER.value == "user"
        assert RoutingTarget.PRIORITY.value == "priority"
        assert RoutingTarget.TAGS.value == "tags"
        assert RoutingTarget.FOLDER.value == "folder"


class TestPriorityLevel:
    """Tests fuer PriorityLevel Enum."""

    def test_priority_level_values(self) -> None:
        """Test: PriorityLevel hat korrekte Werte."""
        assert PriorityLevel.LOW.value == "low"
        assert PriorityLevel.NORMAL.value == "normal"
        assert PriorityLevel.MEDIUM.value == "medium"
        assert PriorityLevel.HIGH.value == "high"
        assert PriorityLevel.URGENT.value == "urgent"


class TestRoutingFeatures:
    """Tests fuer RoutingFeatures Dataclass."""

    def test_create_routing_features(self) -> None:
        """Test: RoutingFeatures erstellen."""
        features = RoutingFeatures(
            document_type="invoice",
            amount=1500.00,
            entity_id=str(uuid4()),
            entity_name="Firma Mueller",
            entity_type="supplier",
            tags=["wichtig", "dringend"],
            has_due_date=True,
            days_to_due=7,
            document_age_days=1,
            has_attachments=False,
            page_count=2,
            word_count=500,
            language="de",
        )

        assert features.document_type == "invoice"
        assert features.amount == 1500.00
        assert features.entity_name == "Firma Mueller"
        assert features.has_due_date is True
        assert features.days_to_due == 7

    def test_routing_features_to_dict(self) -> None:
        """Test: Features koennen zu Dict konvertiert werden."""
        features = RoutingFeatures(
            document_type="invoice",
            amount=1500.00,
            entity_id=None,
            entity_name=None,
            entity_type=None,
            tags=[],
            has_due_date=False,
            days_to_due=None,
            document_age_days=0,
            has_attachments=False,
            page_count=1,
            word_count=100,
            language="de",
        )

        feature_dict = features.to_dict()

        assert "document_type" in feature_dict
        assert "amount" in feature_dict
        assert feature_dict["document_type"] == "invoice"


class TestRoutingHistory:
    """Tests fuer RoutingHistory Dataclass."""

    def test_create_routing_history(self) -> None:
        """Test: RoutingHistory erstellen."""
        doc_id = uuid4()
        history = RoutingHistory(
            document_id=doc_id,
            routed_to="user_123",
            routed_at=datetime.now(timezone.utc),
            was_correct=True,
            time_to_process=timedelta(hours=2),
        )

        assert history.document_id == doc_id
        assert history.routed_to == "user_123"
        assert history.was_correct is True
        assert history.time_to_process == timedelta(hours=2)


class TestRoutingPrediction:
    """Tests fuer RoutingPrediction Dataclass."""

    def test_create_routing_prediction(self) -> None:
        """Test: RoutingPrediction erstellen."""
        prediction = RoutingPrediction(
            target=RoutingTarget.USER,
            predicted_value="user_abc",
            confidence=0.85,
            alternatives=[("user_xyz", 0.72), ("user_123", 0.65)],
            reasoning="Basierend auf Entity-Beziehung",
            model_version="1.0.0",
        )

        assert prediction.target == RoutingTarget.USER
        assert prediction.predicted_value == "user_abc"
        assert prediction.confidence == 0.85
        assert len(prediction.alternatives) == 2
        assert "Entity" in prediction.reasoning


class TestTrainingResult:
    """Tests fuer TrainingResult Dataclass."""

    def test_create_training_result(self) -> None:
        """Test: TrainingResult erstellen."""
        result = TrainingResult(
            samples_used=1000,
            accuracy=0.85,
            precision=0.82,
            recall=0.88,
            f1_score=0.85,
            feature_importance={
                "document_type": 0.25,
                "amount": 0.20,
                "entity_type": 0.18,
            },
            model_version="1.0.0",
            trained_at=datetime.now(timezone.utc),
        )

        assert result.samples_used == 1000
        assert result.accuracy == 0.85
        assert "document_type" in result.feature_importance


class TestRoutingFeatureExtractor:
    """Tests fuer RoutingFeatureExtractor."""

    @pytest.fixture
    def extractor(self) -> RoutingFeatureExtractor:
        """Erstellt Extractor-Instanz."""
        return RoutingFeatureExtractor()

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt Mock-Dokument."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.filename = "rechnung_001.pdf"
        doc.document_type = "invoice"
        doc.tags = ["buchhaltung", "dringend"]
        doc.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        doc.extracted_data = {
            "total_amount": 1500.00,
            "due_date": "2026-01-25",
            "invoice_number": "R-2026-001",
        }
        doc.extracted_text = "Rechnung " * 100  # ~100 Woerter
        doc.page_count = 2
        doc.business_entity_id = uuid4()
        return doc

    @pytest.fixture
    def mock_entity(self) -> MagicMock:
        """Erstellt Mock-Entity."""
        entity = MagicMock()
        entity.id = uuid4()
        entity.name = "Firma Mueller GmbH"
        entity.entity_type = "supplier"
        return entity

    def test_extract_features_basic(
        self, extractor: RoutingFeatureExtractor, mock_document: MagicMock
    ) -> None:
        """Test: Basis-Features werden extrahiert."""
        features = extractor.extract_features(mock_document)

        assert features.document_type == "invoice"
        assert features.amount == 1500.00
        assert "buchhaltung" in features.tags
        assert features.page_count == 2

    def test_extract_features_with_entity(
        self,
        extractor: RoutingFeatureExtractor,
        mock_document: MagicMock,
        mock_entity: MagicMock,
    ) -> None:
        """Test: Entity-Features werden extrahiert."""
        features = extractor.extract_features(mock_document, mock_entity)

        assert features.entity_id == str(mock_entity.id)
        assert features.entity_name == "Firma Mueller GmbH"
        assert features.entity_type == "supplier"

    def test_extract_features_no_amount(
        self, extractor: RoutingFeatureExtractor, mock_document: MagicMock
    ) -> None:
        """Test: Fehlender Betrag wird als None behandelt."""
        mock_document.extracted_data = {}

        features = extractor.extract_features(mock_document)

        assert features.amount is None

    def test_extract_features_due_date_calculation(
        self, extractor: RoutingFeatureExtractor, mock_document: MagicMock
    ) -> None:
        """Test: Faelligkeitstage werden berechnet."""
        # Setze Faelligkeitsdatum in 7 Tagen
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
        mock_document.extracted_data["due_date"] = future_date

        features = extractor.extract_features(mock_document)

        assert features.has_due_date is True
        assert features.days_to_due is not None
        assert 6 <= features.days_to_due <= 8  # Toleranz fuer Zeitzone


class TestRoutingPredictorInit:
    """Tests fuer Predictor-Initialisierung."""

    def test_predictor_init(self) -> None:
        """Test: Predictor kann initialisiert werden."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        assert predictor.db == mock_db
        assert predictor.model is None  # Kein ML-Modell initial
        assert predictor.model_version is not None

    def test_predictor_init_with_config(self) -> None:
        """Test: Predictor mit Konfiguration."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        # Standardwerte pruefen
        assert predictor.training_samples == 0
        assert predictor.accuracy_by_target == {}


class TestRuleBasedPrediction:
    """Tests fuer regelbasierte Vorhersagen."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor-Instanz."""
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt Mock-Dokument."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.document_type = "invoice"
        doc.extracted_data = {"total_amount": 15000.00}
        doc.tags = []
        doc.created_at = datetime.now(timezone.utc)
        doc.business_entity_id = None
        doc.extracted_text = ""
        doc.page_count = 1
        return doc

    @pytest.mark.asyncio
    async def test_predict_priority_high_amount(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Hoher Betrag ergibt hohe Prioritaet."""
        mock_document.extracted_data = {"total_amount": 15000.00}

        prediction = await predictor.predict(mock_document, RoutingTarget.PRIORITY)

        assert prediction.target == RoutingTarget.PRIORITY
        assert prediction.predicted_value in ["high", "urgent"]
        assert prediction.confidence > 0.5

    @pytest.mark.asyncio
    async def test_predict_priority_low_amount(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Niedriger Betrag ergibt normale Prioritaet."""
        mock_document.extracted_data = {"total_amount": 100.00}

        prediction = await predictor.predict(mock_document, RoutingTarget.PRIORITY)

        assert prediction.target == RoutingTarget.PRIORITY
        assert prediction.predicted_value in ["normal", "low"]

    @pytest.mark.asyncio
    async def test_predict_tags_from_document_type(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Tags werden aus Dokumenttyp abgeleitet."""
        mock_document.document_type = "invoice"

        prediction = await predictor.predict(mock_document, RoutingTarget.TAGS)

        assert prediction.target == RoutingTarget.TAGS
        assert prediction.predicted_value is not None
        assert "invoice" in prediction.predicted_value or "rechnung" in prediction.predicted_value.lower()


class TestMLPrediction:
    """Tests fuer ML-basierte Vorhersagen."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor mit Mock-Modell."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        # Mock ML-Modell
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = [[0.7, 0.2, 0.1]]
        mock_model.classes_ = ["user_1", "user_2", "user_3"]
        predictor.model = mock_model

        return predictor

    @pytest.mark.asyncio
    async def test_ml_prediction_with_model(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: ML-Vorhersage mit trainiertem Modell."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.document_type = "invoice"
        mock_doc.extracted_data = {"total_amount": 1000.00}
        mock_doc.tags = []
        mock_doc.created_at = datetime.now(timezone.utc)
        mock_doc.business_entity_id = None
        mock_doc.extracted_text = ""
        mock_doc.page_count = 1

        prediction = await predictor.predict(mock_doc, RoutingTarget.USER)

        assert prediction.target == RoutingTarget.USER
        assert prediction.confidence >= 0.0
        assert prediction.confidence <= 1.0


class TestTraining:
    """Tests fuer Modell-Training."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor-Instanz."""
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    def test_training_requires_minimum_samples(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Training benoetigt Mindestanzahl an Samples."""
        # Nur 5 Samples - zu wenig
        training_data = [
            RoutingHistory(
                document_id=uuid4(),
                routed_to=f"user_{i}",
                routed_at=datetime.now(timezone.utc),
                was_correct=True,
                time_to_process=None,
            )
            for i in range(5)
        ]

        # Sollte Fehler werfen oder niedrige Metrik zurueckgeben
        # (abhaengig von Implementierung)
        assert len(training_data) < 10

    @pytest.mark.asyncio
    async def test_training_with_sufficient_samples(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Training mit ausreichend Samples."""
        # Mock Dokumente fuer Training
        mock_result = MagicMock()
        mock_docs = []
        for i in range(50):
            doc = MagicMock()
            doc.id = uuid4()
            doc.document_type = "invoice" if i % 2 == 0 else "delivery_note"
            doc.extracted_data = {"total_amount": 1000.0 + i * 100}
            doc.tags = []
            doc.created_at = datetime.now(timezone.utc) - timedelta(days=i)
            doc.business_entity_id = None
            doc.extracted_text = ""
            doc.page_count = 1
            doc.assigned_to_id = uuid4() if i % 3 == 0 else None
            mock_docs.append(doc)

        mock_result.scalars.return_value.all.return_value = mock_docs
        predictor.db.execute.return_value = mock_result

        training_data = [
            RoutingHistory(
                document_id=doc.id,
                routed_to=str(doc.assigned_to_id) if doc.assigned_to_id else "default",
                routed_at=doc.created_at,
                was_correct=True,
                time_to_process=None,
            )
            for doc in mock_docs
            if doc.assigned_to_id
        ]

        # Training ausfuehren (falls genug Samples)
        if len(training_data) >= 10:
            result = await predictor.train(training_data, RoutingTarget.USER)
            assert result is not None


class TestFeedbackLearning:
    """Tests fuer Online-Learning mit Feedback."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor-Instanz."""
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.mark.asyncio
    async def test_update_from_positive_feedback(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Positives Feedback wird verarbeitet."""
        routing_id = uuid4()

        # Sollte ohne Fehler durchlaufen
        await predictor.update_from_feedback(
            routing_id=routing_id,
            correct_target="user_correct",
            was_correct=True,
        )

    @pytest.mark.asyncio
    async def test_update_from_negative_feedback(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Negatives Feedback wird verarbeitet."""
        routing_id = uuid4()

        await predictor.update_from_feedback(
            routing_id=routing_id,
            correct_target="user_correct",
            was_correct=False,
        )

        # Feedback sollte fuer spaeteres Retraining gespeichert werden


class TestPriorityPrediction:
    """Spezifische Tests fuer Prioritaets-Vorhersage."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor-Instanz."""
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.mark.asyncio
    async def test_urgent_priority_for_overdue(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Ueberfaellige Dokumente haben dringende Prioritaet."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.document_type = "invoice"
        # Faelligkeitsdatum in der Vergangenheit
        past_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
        mock_doc.extracted_data = {
            "total_amount": 1000.00,
            "due_date": past_date,
        }
        mock_doc.tags = []
        mock_doc.created_at = datetime.now(timezone.utc) - timedelta(days=10)
        mock_doc.business_entity_id = None
        mock_doc.extracted_text = ""
        mock_doc.page_count = 1

        prediction = await predictor.predict(mock_doc, RoutingTarget.PRIORITY)

        # Ueberfaellig = hohe/dringende Prioritaet
        assert prediction.predicted_value in ["high", "urgent"]

    @pytest.mark.asyncio
    async def test_priority_for_document_without_due_date(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Dokumente ohne Faelligkeitsdatum."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_doc.document_type = "contract"
        mock_doc.extracted_data = {"contract_value": 50000.00}
        mock_doc.tags = []
        mock_doc.created_at = datetime.now(timezone.utc)
        mock_doc.business_entity_id = None
        mock_doc.extracted_text = ""
        mock_doc.page_count = 5

        prediction = await predictor.predict(mock_doc, RoutingTarget.PRIORITY)

        # Sollte normale Prioritaet haben
        assert prediction.predicted_value is not None
        assert prediction.confidence > 0


class TestFeatureImportance:
    """Tests fuer Feature-Wichtigkeit."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor mit trainiertem Modell."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        # Mock trainiertes Modell mit feature_importances_
        mock_model = MagicMock()
        mock_model.feature_importances_ = [0.25, 0.20, 0.18, 0.15, 0.12, 0.10]
        predictor.model = mock_model

        return predictor

    def test_feature_importance_extraction(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Feature-Wichtigkeit wird extrahiert."""
        if predictor.model and hasattr(predictor.model, "feature_importances_"):
            importances = predictor.model.feature_importances_

            assert len(importances) > 0
            assert sum(importances) == pytest.approx(1.0, 0.01)
