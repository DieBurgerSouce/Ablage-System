# -*- coding: utf-8 -*-
"""
Tests fuer RoutingPredictor.

Phase 9.2: Dream Features - Predictive Document Routing

Testet gegen den ECHTEN Vertrag von app.ml.routing_predictor:
- Feature-Extraktion (RoutingFeatureExtractor)
- Regelbasierte Vorhersagen (Prioritaet, Tags, User)
- Training (Mindest-Samples, Regel-Lernen aus Historie)
- Online-Learning mit Feedback
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
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
        """Test: RoutingTarget hat die echten Werte."""
        assert RoutingTarget.USER.value == "user"
        assert RoutingTarget.DEPARTMENT.value == "department"
        assert RoutingTarget.PRIORITY.value == "priority"
        assert RoutingTarget.WORKFLOW.value == "workflow"
        assert RoutingTarget.TAGS.value == "tags"


class TestPriorityLevel:
    """Tests fuer PriorityLevel Enum."""

    def test_priority_level_values(self) -> None:
        """Test: PriorityLevel hat die echten Werte (URGENT/HIGH/NORMAL/LOW)."""
        assert PriorityLevel.URGENT.value == "urgent"
        assert PriorityLevel.HIGH.value == "high"
        assert PriorityLevel.NORMAL.value == "normal"
        assert PriorityLevel.LOW.value == "low"


class TestRoutingFeatures:
    """Tests fuer RoutingFeatures Dataclass."""

    def test_create_routing_features(self) -> None:
        """Test: RoutingFeatures mit echten Feldern erstellen."""
        features = RoutingFeatures(
            document_type="invoice",
            file_size=2048,
            page_count=2,
            has_ocr_text=True,
            entity_id=str(uuid4()),
            entity_name="Firma Mueller",
            entity_type="supplier",
            total_amount=1500.00,
            amount_category="large",
        )

        assert features.document_type == "invoice"
        assert features.total_amount == 1500.00
        assert features.entity_name == "Firma Mueller"
        assert features.amount_category == "large"
        assert features.has_ocr_text is True

    def test_routing_features_to_vector(self) -> None:
        """Test: Features koennen in einen numerischen Vektor konvertiert werden."""
        features = RoutingFeatures(
            document_type="invoice",
            file_size=1_000_000,
            page_count=1,
            has_ocr_text=False,
            amount_category="medium",
        )

        vector = features.to_vector()

        # Vektor muss rein numerisch sein und stabile Laenge haben
        assert isinstance(vector, list)
        assert len(vector) > 0
        assert all(isinstance(v, float) for v in vector)
        # invoice ist das erste One-Hot-Feld -> 1.0
        assert vector[0] == 1.0
        # has_ocr_text=False muss als 0.0 kodiert sein
        assert 0.0 in vector


class TestRoutingHistory:
    """Tests fuer RoutingHistory Dataclass."""

    def test_create_routing_history(self) -> None:
        """Test: RoutingHistory mit echten Feldern erstellen."""
        doc_id = uuid4()
        user_id = uuid4()
        features = RoutingFeatures(
            document_type="invoice",
            file_size=1024,
            page_count=1,
            has_ocr_text=True,
            entity_id=str(uuid4()),
        )
        history = RoutingHistory(
            document_id=doc_id,
            features=features,
            assigned_user_id=user_id,
            assigned_department="Buchhaltung",
            priority=PriorityLevel.HIGH,
            tags=["wichtig"],
        )

        assert history.document_id == doc_id
        assert history.assigned_user_id == user_id
        assert history.priority == PriorityLevel.HIGH
        assert history.was_correct is True


class TestRoutingPrediction:
    """Tests fuer RoutingPrediction Dataclass."""

    def test_create_routing_prediction(self) -> None:
        """Test: RoutingPrediction mit echten Feldern erstellen."""
        prediction = RoutingPrediction(
            target_type=RoutingTarget.USER,
            prediction="user_abc",
            confidence=0.85,
            alternatives=[("user_xyz", 0.72), ("user_123", 0.65)],
            explanation="Basierend auf Entity-Beziehung",
            features_used=["entity_history"],
        )

        assert prediction.target_type == RoutingTarget.USER
        assert prediction.prediction == "user_abc"
        assert prediction.confidence == 0.85
        assert len(prediction.alternatives) == 2
        assert "Entity" in prediction.explanation


class TestTrainingResult:
    """Tests fuer TrainingResult Dataclass."""

    def test_create_training_result(self) -> None:
        """Test: TrainingResult mit echten Feldern erstellen."""
        result = TrainingResult(
            target_type=RoutingTarget.USER,
            samples_used=1000,
            accuracy=0.85,
            model_version="routing-v1-20260101",
            trained_at=datetime.now(timezone.utc),
            feature_importance={
                "document_type": 0.25,
                "entity_history": 0.20,
            },
        )

        assert result.samples_used == 1000
        assert result.accuracy == 0.85
        assert result.target_type == RoutingTarget.USER
        assert "document_type" in result.feature_importance


class TestRoutingFeatureExtractor:
    """Tests fuer RoutingFeatureExtractor."""

    @pytest.fixture
    def extractor(self) -> RoutingFeatureExtractor:
        """Erstellt Extractor-Instanz."""
        return RoutingFeatureExtractor()

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt Mock-Dokument (echte Document-Attribute)."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.filename = "rechnung_001.pdf"
        doc.document_type = "invoice"
        doc.file_size = 4096
        doc.page_count = 2
        doc.detected_language = "de"
        doc.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        # Service liest total_gross aus extracted_data
        doc.extracted_data = {
            "total_gross": 1500.00,
            "invoice_number": "R-2026-001",
        }
        doc.extracted_text = "Rechnung " * 100
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
        assert features.total_amount == 1500.00
        # 1500 EUR liegt in der Kategorie 'large' (1000 <= x < 10000)
        assert features.amount_category == "large"
        assert features.page_count == 2
        assert features.has_ocr_text is True

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

        assert features.total_amount is None
        assert features.amount_category == "unknown"

    def test_extract_features_keyword_detection(
        self, extractor: RoutingFeatureExtractor, mock_document: MagicMock
    ) -> None:
        """Test: Keywords aus dem Text werden erkannt."""
        mock_document.extracted_text = "Dies ist eine dringende Mahnung mit Frist."

        features = extractor.extract_features(mock_document)

        assert features.has_keywords.get("dringend") is True
        assert features.has_keywords.get("mahnung") is True
        assert features.has_keywords.get("vertrag") is False


class TestRoutingPredictorInit:
    """Tests fuer Predictor-Initialisierung."""

    def test_predictor_init(self) -> None:
        """Test: Predictor kann initialisiert werden."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        assert predictor.db == mock_db
        # Kein ML-Modell initial geladen
        assert predictor._user_model is None
        assert isinstance(predictor.feature_extractor, RoutingFeatureExtractor)

    def test_predictor_init_default_stats(self) -> None:
        """Test: Predictor startet mit leeren Statistiken/Regeln."""
        mock_db = AsyncMock()
        predictor = RoutingPredictor(mock_db)

        assert predictor._predictions_count == 0
        assert predictor._correct_predictions == 0
        assert predictor._user_rules == {}


class TestRuleBasedPrediction:
    """Tests fuer regelbasierte Vorhersagen."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        """Erstellt Predictor-Instanz."""
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        """Erstellt Mock-Dokument ohne Entity (keine DB-Abfrage)."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.document_type = "invoice"
        doc.file_size = 2048
        doc.page_count = 1
        doc.detected_language = "de"
        doc.extracted_data = {"total_gross": 15000.00}
        doc.created_at = datetime.now(timezone.utc)
        doc.business_entity_id = None
        doc.extracted_text = ""
        return doc

    @pytest.mark.asyncio
    async def test_predict_priority_high_amount(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Hoher Betrag (>=10000 = xlarge) ergibt hohe Prioritaet."""
        mock_document.extracted_data = {"total_gross": 15000.00}

        prediction = await predictor.predict(mock_document, RoutingTarget.PRIORITY)

        assert prediction.target_type == RoutingTarget.PRIORITY
        assert prediction.prediction == PriorityLevel.HIGH
        assert prediction.confidence > 0.5

    @pytest.mark.asyncio
    async def test_predict_priority_low_amount(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Niedriger Betrag ergibt normale Prioritaet."""
        mock_document.extracted_data = {"total_gross": 100.00}

        prediction = await predictor.predict(mock_document, RoutingTarget.PRIORITY)

        assert prediction.target_type == RoutingTarget.PRIORITY
        assert prediction.prediction == PriorityLevel.NORMAL

    @pytest.mark.asyncio
    async def test_predict_priority_keyword_urgent(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Keyword 'dringend' fuehrt zu URGENT (hoechste Prioritaet)."""
        mock_document.extracted_data = {"total_gross": 50.00}
        mock_document.extracted_text = "Bitte dringend bearbeiten!"

        prediction = await predictor.predict(mock_document, RoutingTarget.PRIORITY)

        assert prediction.prediction == PriorityLevel.URGENT
        assert prediction.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_predict_tags_from_document_type(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Tags werden aus Dokumenttyp abgeleitet."""
        mock_document.document_type = "invoice"

        prediction = await predictor.predict(mock_document, RoutingTarget.TAGS)

        assert prediction.target_type == RoutingTarget.TAGS
        assert isinstance(prediction.prediction, list)
        assert "invoice" in prediction.prediction


class TestUserPrediction:
    """Tests fuer User-Vorhersage (Regeln + Fallback)."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.fixture
    def mock_document(self) -> MagicMock:
        doc = MagicMock()
        doc.id = uuid4()
        doc.document_type = "invoice"
        doc.file_size = 2048
        doc.page_count = 1
        doc.detected_language = "de"
        doc.extracted_data = {"total_gross": 1000.00}
        doc.created_at = datetime.now(timezone.utc)
        doc.business_entity_id = None
        doc.extracted_text = ""
        return doc

    @pytest.mark.asyncio
    async def test_predict_user_fallback_when_no_data(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Ohne Regeln/Modell liefert User-Vorhersage 'unknown' mit Confidence 0."""
        prediction = await predictor.predict(mock_document, RoutingTarget.USER)

        assert prediction.target_type == RoutingTarget.USER
        assert prediction.prediction == "unknown"
        assert prediction.confidence == 0.0

    @pytest.mark.asyncio
    async def test_predict_user_from_entity_rule(
        self, predictor: RoutingPredictor, mock_document: MagicMock
    ) -> None:
        """Test: Gelernte Entity->User-Regel wird angewendet."""
        entity_id = uuid4()
        user_id = uuid4()
        mock_document.business_entity_id = entity_id

        # Entity wird ueber DB nachgeladen
        entity = MagicMock()
        entity.id = entity_id
        entity.name = "Stamm-Lieferant"
        entity.entity_type = "supplier"
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=entity)
        predictor.db.execute.return_value = result

        # Regel injizieren (entity_id -> user_id)
        predictor._user_rules[str(entity_id)] = str(user_id)

        prediction = await predictor.predict(mock_document, RoutingTarget.USER)

        assert prediction.target_type == RoutingTarget.USER
        assert prediction.prediction == user_id
        assert prediction.confidence >= 0.85


class TestTraining:
    """Tests fuer Modell-Training."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    def _make_history(self, n: int) -> List[RoutingHistory]:
        items: List[RoutingHistory] = []
        for i in range(n):
            features = RoutingFeatures(
                document_type="invoice",
                file_size=1024,
                page_count=1,
                has_ocr_text=True,
                entity_id=str(uuid4()),
            )
            items.append(
                RoutingHistory(
                    document_id=uuid4(),
                    features=features,
                    assigned_user_id=uuid4(),
                    assigned_department=None,
                    priority=PriorityLevel.NORMAL,
                    tags=[],
                )
            )
        return items

    @pytest.mark.asyncio
    async def test_training_insufficient_samples_returns_rules_only(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Unter MIN_TRAINING_SAMPLES wird 'rules-only' zurueckgegeben."""
        history = self._make_history(5)
        assert len(history) < predictor.MIN_TRAINING_SAMPLES

        result = await predictor.train(history, RoutingTarget.USER)

        assert result.model_version == "rules-only"
        assert result.accuracy == 0.0
        assert result.samples_used == 5

    @pytest.mark.asyncio
    async def test_training_with_sufficient_samples(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Mit genug Samples wird ein Modell-Version-String erzeugt."""
        history = self._make_history(predictor.MIN_TRAINING_SAMPLES)

        result = await predictor.train(history, RoutingTarget.USER)

        assert result.samples_used == predictor.MIN_TRAINING_SAMPLES
        assert result.model_version.startswith(predictor.MODEL_VERSION_PREFIX)
        assert result.accuracy > 0.0

    @pytest.mark.asyncio
    async def test_training_learns_entity_user_rule(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Wiederholte Entity->User-Zuweisungen werden als Regel gelernt."""
        entity_id = str(uuid4())
        user_id = uuid4()
        history: List[RoutingHistory] = []
        # 50 Samples, alle mit derselben Entity->User-Zuordnung
        for _ in range(predictor.MIN_TRAINING_SAMPLES):
            features = RoutingFeatures(
                document_type="invoice",
                file_size=1024,
                page_count=1,
                has_ocr_text=True,
                entity_id=entity_id,
            )
            history.append(
                RoutingHistory(
                    document_id=uuid4(),
                    features=features,
                    assigned_user_id=user_id,
                    assigned_department=None,
                    priority=PriorityLevel.NORMAL,
                    tags=[],
                )
            )

        await predictor.train(history, RoutingTarget.USER)

        # Mind. 3 gleiche Zuweisungen -> Regel gelernt
        assert predictor._user_rules.get(entity_id) == str(user_id)


class TestFeedbackLearning:
    """Tests fuer Online-Learning mit Feedback."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    @pytest.mark.asyncio
    async def test_update_from_positive_feedback(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Positives Feedback erhoeht Korrekt-Zaehler."""
        routing_id = uuid4()

        await predictor.update_from_feedback(
            routing_id=routing_id,
            correct_target="user_correct",
            was_correct=True,
        )

        assert predictor._predictions_count == 1
        assert predictor._correct_predictions == 1

    @pytest.mark.asyncio
    async def test_update_from_negative_feedback(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Negatives Feedback zaehlt Vorhersage, aber nicht als korrekt."""
        routing_id = uuid4()

        await predictor.update_from_feedback(
            routing_id=routing_id,
            correct_target="user_correct",
            was_correct=False,
        )

        assert predictor._predictions_count == 1
        assert predictor._correct_predictions == 0


class TestStatistics:
    """Tests fuer Statistik-Ausgabe."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    def test_statistics_initial(self, predictor: RoutingPredictor) -> None:
        """Test: Statistiken sind initial leer/null."""
        stats = predictor.get_statistics()

        assert stats["predictions_count"] == 0
        assert stats["accuracy"] == 0.0
        assert stats["has_ml_model"] is False

    @pytest.mark.asyncio
    async def test_statistics_after_feedback(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Accuracy wird aus Feedback berechnet."""
        await predictor.update_from_feedback(uuid4(), "u", was_correct=True)
        await predictor.update_from_feedback(uuid4(), "u", was_correct=False)

        stats = predictor.get_statistics()

        assert stats["predictions_count"] == 2
        assert stats["correct_predictions"] == 1
        assert stats["accuracy"] == 0.5


class TestPriorityPrediction:
    """Spezifische Tests fuer Prioritaets-Vorhersage."""

    @pytest.fixture
    def predictor(self) -> RoutingPredictor:
        mock_db = AsyncMock()
        return RoutingPredictor(mock_db)

    def _make_doc(self) -> MagicMock:
        doc = MagicMock()
        doc.id = uuid4()
        doc.document_type = "invoice"
        doc.file_size = 2048
        doc.page_count = 1
        doc.detected_language = "de"
        doc.created_at = datetime.now(timezone.utc)
        doc.business_entity_id = None
        doc.extracted_text = ""
        doc.extracted_data = {}
        return doc

    @pytest.mark.asyncio
    async def test_high_priority_for_mahnung(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Mahnung im Text ergibt hohe Prioritaet."""
        doc = self._make_doc()
        doc.extracted_text = "Zahlungserinnerung: Bitte begleichen Sie die Mahnung."

        prediction = await predictor.predict(doc, RoutingTarget.PRIORITY)

        assert prediction.prediction == PriorityLevel.HIGH

    @pytest.mark.asyncio
    async def test_priority_for_document_without_keywords(
        self, predictor: RoutingPredictor
    ) -> None:
        """Test: Dokument ohne besondere Merkmale erhaelt normale Prioritaet."""
        doc = self._make_doc()
        doc.document_type = "contract"
        doc.extracted_data = {}

        prediction = await predictor.predict(doc, RoutingTarget.PRIORITY)

        assert prediction.prediction == PriorityLevel.NORMAL
        assert prediction.confidence > 0
