# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Predictive Routing API Endpoints.

Phase 9.2: Dream Features - Predictive Document Routing

Testet:
- POST /routing/predict - Routing-Vorhersage
- POST /routing/feedback - Feedback uebermitteln
- POST /routing/train - Modell trainieren (Admin)
- GET /routing/model/info - Modell-Informationen
- GET /routing/suggestions/{document_id} - Schnelle Vorschlaege
- POST /routing/auto-route/{document_id} - Automatisches Routing
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from fastapi import HTTPException, status


# ========================= Test Fixtures =========================


@pytest.fixture
def sample_user() -> MagicMock:
    """Create mock User with company_id."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def sample_admin_user() -> MagicMock:
    """Create mock Admin User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "admin@example.com"
    user.is_active = True
    user.is_superuser = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def sample_document(sample_user: MagicMock) -> MagicMock:
    """Create mock Document."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.owner_id = sample_user.id
    doc.company_id = sample_user.company_id
    doc.deleted_at = None
    doc.filename = "rechnung_001.pdf"
    doc.document_type = "invoice"
    doc.tags = ["buchhaltung"]
    doc.extracted_data = {
        "total_amount": 1500.00,
        "invoice_number": "R-2026-001",
    }
    doc.created_at = datetime.now(timezone.utc)
    doc.business_entity_id = uuid4()
    doc.assigned_to_id = None
    doc.extracted_text = "Rechnung Nr. R-2026-001"
    doc.page_count = 2
    return doc


# ========================= Request Schema Tests =========================


class TestRoutingPredictionRequest:
    """Tests fuer RoutingPredictionRequest Schema."""

    def test_valid_request(self) -> None:
        """Test: Gueltige Request wird akzeptiert."""
        from app.api.v1.routing import RoutingPredictionRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingPredictionRequest(
            document_id=uuid4(),
            targets=[RoutingTarget.USER, RoutingTarget.PRIORITY],
        )

        assert request.document_id is not None
        assert len(request.targets) == 2

    def test_default_targets(self) -> None:
        """Test: Standard-Ziel ist USER."""
        from app.api.v1.routing import RoutingPredictionRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingPredictionRequest(
            document_id=uuid4(),
        )

        assert len(request.targets) == 1
        assert request.targets[0] == RoutingTarget.USER


class TestRoutingFeedbackRequest:
    """Tests fuer RoutingFeedbackRequest Schema."""

    def test_valid_request(self) -> None:
        """Test: Gueltige Feedback-Request."""
        from app.api.v1.routing import RoutingFeedbackRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingFeedbackRequest(
            routing_id=uuid4(),
            target=RoutingTarget.USER,
            correct_value="user_correct_123",
            was_correct=False,
        )

        assert request.routing_id is not None
        assert request.target == RoutingTarget.USER
        assert request.was_correct is False


class TestTrainingRequest:
    """Tests fuer TrainingRequest Schema."""

    def test_valid_request(self) -> None:
        """Test: Gueltige Training-Request."""
        from app.api.v1.routing import TrainingRequest
        from app.ml.routing_predictor import RoutingTarget

        request = TrainingRequest(
            target=RoutingTarget.PRIORITY,
            use_historical=True,
            days_back=60,
        )

        assert request.target == RoutingTarget.PRIORITY
        assert request.use_historical is True
        assert request.days_back == 60

    def test_default_values(self) -> None:
        """Test: Standard-Werte werden verwendet."""
        from app.api.v1.routing import TrainingRequest
        from app.ml.routing_predictor import RoutingTarget

        request = TrainingRequest()

        assert request.target == RoutingTarget.USER
        assert request.use_historical is True
        assert request.days_back == 90


# ========================= Response Schema Tests =========================


class TestRoutingPredictionResponse:
    """Tests fuer RoutingPredictionResponse Schema."""

    def test_create_response(self) -> None:
        """Test: Response kann erstellt werden."""
        from app.api.v1.routing import (
            RoutingPredictionResponse,
            UserPredictionResponse,
            PriorityPredictionResponse,
        )

        doc_id = uuid4()
        user_id = uuid4()

        response = RoutingPredictionResponse(
            document_id=doc_id,
            user_prediction=UserPredictionResponse(
                user_id=user_id,
                username="test_user",
                confidence=0.85,
                reasoning="Basierend auf Entity-Beziehung",
            ),
            priority_prediction=PriorityPredictionResponse(
                priority="high",
                confidence=0.90,
                reasoning="Hoher Betrag",
            ),
            tags_prediction=None,
            folder_prediction=None,
            overall_confidence=0.875,
            model_version="1.0.0",
            predicted_at=datetime.now(timezone.utc).isoformat(),
        )

        assert response.document_id == doc_id
        assert response.user_prediction.user_id == user_id
        assert response.overall_confidence == 0.875


class TestModelInfoResponse:
    """Tests fuer ModelInfoResponse Schema."""

    def test_create_response(self) -> None:
        """Test: Response kann erstellt werden."""
        from app.api.v1.routing import ModelInfoResponse

        response = ModelInfoResponse(
            model_version="1.0.0",
            targets_available=["user", "priority", "tags", "folder"],
            last_trained="2026-01-15T10:00:00Z",
            training_samples=5000,
            accuracy={"user": 0.85, "priority": 0.90},
            is_ml_model=True,
        )

        assert response.model_version == "1.0.0"
        assert len(response.targets_available) == 4
        assert response.is_ml_model is True


# ========================= Endpoint Tests =========================


class TestPredictRoutingEndpoint:
    """Tests fuer POST /routing/predict Endpoint."""

    @pytest.mark.asyncio
    async def test_predict_document_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierendes Dokument wirft 404."""
        from app.api.v1.routing import predict_routing, RoutingPredictionRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingPredictionRequest(
            document_id=uuid4(),
            targets=[RoutingTarget.USER],
        )

        mock_db = AsyncMock()

        # Mock execute um None zurueckzugeben
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await predict_routing(
                request=request,
                db=mock_db,
                current_user=sample_user,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_predict_with_valid_document(
        self, sample_user: MagicMock, sample_document: MagicMock
    ) -> None:
        """Test: Vorhersage fuer gueltiges Dokument."""
        from app.api.v1.routing import predict_routing, RoutingPredictionRequest
        from app.ml.routing_predictor import RoutingTarget, RoutingPrediction

        request = RoutingPredictionRequest(
            document_id=sample_document.id,
            targets=[RoutingTarget.PRIORITY],
        )

        mock_db = AsyncMock()

        # Mock document lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_document
        mock_db.execute.return_value = mock_result

        with patch("app.api.v1.routing.RoutingPredictor") as MockPredictor:
            mock_predictor = MockPredictor.return_value
            mock_predictor.model_version = "1.0.0"
            mock_predictor.predict.return_value = RoutingPrediction(
                target_type=RoutingTarget.PRIORITY,
                prediction="high",
                confidence=0.85,
                alternatives=[],
                explanation="Hoher Betrag",
                features_used=["total_amount"],
            )

            response = await predict_routing(
                request=request,
                db=mock_db,
                current_user=sample_user,
            )

        assert response.document_id == sample_document.id
        assert response.priority_prediction is not None
        assert response.priority_prediction.priority == "high"


class TestFeedbackEndpoint:
    """Tests fuer POST /routing/feedback Endpoint."""

    @pytest.mark.asyncio
    async def test_submit_feedback_success(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Feedback wird erfolgreich uebermittelt."""
        from app.api.v1.routing import submit_routing_feedback, RoutingFeedbackRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingFeedbackRequest(
            routing_id=uuid4(),
            target=RoutingTarget.USER,
            correct_value="user_correct",
            was_correct=True,
        )

        mock_db = AsyncMock()

        with patch("app.api.v1.routing.RoutingPredictor") as MockPredictor:
            mock_predictor = MockPredictor.return_value
            mock_predictor.update_from_feedback = AsyncMock()

            # Sollte ohne Fehler durchlaufen (204 No Content)
            result = await submit_routing_feedback(
                request=request,
                db=mock_db,
                current_user=sample_user,
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_submit_feedback_failure(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Feedback-Fehler wird als 500 gemeldet."""
        from app.api.v1.routing import submit_routing_feedback, RoutingFeedbackRequest
        from app.ml.routing_predictor import RoutingTarget

        request = RoutingFeedbackRequest(
            routing_id=uuid4(),
            target=RoutingTarget.USER,
            correct_value="user_correct",
            was_correct=False,
        )

        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch("app.api.v1.routing.RoutingPredictor") as MockPredictor:
                mock_predictor = MockPredictor.return_value
                mock_predictor.update_from_feedback = AsyncMock(
                    side_effect=Exception("DB Error")
                )

                await submit_routing_feedback(
                    request=request,
                    db=mock_db,
                    current_user=sample_user,
                )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestTrainModelEndpoint:
    """Tests fuer POST /routing/train Endpoint."""

    @pytest.mark.asyncio
    async def test_train_insufficient_data(
        self, sample_admin_user: MagicMock
    ) -> None:
        """Test: Training mit zu wenig Daten schlaegt fehl."""
        from app.api.v1.routing import train_routing_model, TrainingRequest
        from app.ml.routing_predictor import RoutingTarget

        request = TrainingRequest(
            target=RoutingTarget.USER,
            use_historical=True,
            days_back=90,
        )

        mock_db = AsyncMock()

        # Mock execute um wenige Dokumente zurueckzugeben
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await train_routing_model(
                request=request,
                db=mock_db,
                current_user=sample_admin_user,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "10" in str(exc_info.value.detail)


class TestModelInfoEndpoint:
    """Tests fuer GET /routing/model/info Endpoint."""

    @pytest.mark.asyncio
    async def test_get_model_info(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Modell-Informationen abrufen."""
        from app.api.v1.routing import get_model_info

        mock_db = AsyncMock()

        with patch("app.api.v1.routing.RoutingPredictor") as MockPredictor:
            mock_predictor = MockPredictor.return_value
            mock_predictor.model_version = "1.0.0"
            mock_predictor.last_trained = datetime.now(timezone.utc)
            mock_predictor.training_samples = 5000
            mock_predictor.accuracy_by_target = {"user": 0.85}
            mock_predictor.model = MagicMock()  # ML-Modell vorhanden

            response = await get_model_info(
                db=mock_db,
                current_user=sample_user,
            )

        assert response.model_version == "1.0.0"
        assert response.is_ml_model is True


class TestQuickSuggestionsEndpoint:
    """Tests fuer GET /routing/suggestions/{document_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_suggestions_document_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierendes Dokument wirft 404."""
        from app.api.v1.routing import get_quick_suggestions

        mock_db = AsyncMock()

        # Mock execute um None zurueckzugeben
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_quick_suggestions(
                document_id=uuid4(),
                db=mock_db,
                current_user=sample_user,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_suggestions_with_valid_document(
        self, sample_user: MagicMock, sample_document: MagicMock
    ) -> None:
        """Test: Vorschlaege fuer gueltiges Dokument."""
        from app.api.v1.routing import get_quick_suggestions

        mock_db = AsyncMock()

        # Mock document lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_document
        mock_db.execute.return_value = mock_result

        response = await get_quick_suggestions(
            document_id=sample_document.id,
            db=mock_db,
            current_user=sample_user,
        )

        assert "document_id" in response
        assert "suggested_users" in response
        assert "suggested_priority" in response
        assert "suggested_tags" in response


class TestAutoRouteEndpoint:
    """Tests fuer POST /routing/auto-route/{document_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_auto_route_document_not_found(
        self, sample_user: MagicMock
    ) -> None:
        """Test: Nicht existierendes Dokument wirft 404."""
        from app.api.v1.routing import auto_route_document

        mock_db = AsyncMock()

        # Mock execute um None zurueckzugeben
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await auto_route_document(
                document_id=uuid4(),
                apply_user=True,
                apply_priority=True,
                apply_tags=False,
                min_confidence=0.7,
                db=mock_db,
                current_user=sample_user,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    def test_routing_target_enum_values(self) -> None:
        """Test: RoutingTarget Enum hat richtige Werte."""
        from app.ml.routing_predictor import RoutingTarget

        assert RoutingTarget.USER.value == "user"
        assert RoutingTarget.DEPARTMENT.value == "department"
        assert RoutingTarget.PRIORITY.value == "priority"
        assert RoutingTarget.WORKFLOW.value == "workflow"
        assert RoutingTarget.TAGS.value == "tags"

    def test_priority_level_enum_values(self) -> None:
        """Test: PriorityLevel Enum hat richtige Werte."""
        from app.ml.routing_predictor import PriorityLevel

        assert PriorityLevel.LOW.value == "low"
        assert PriorityLevel.NORMAL.value == "normal"
        assert PriorityLevel.HIGH.value == "high"
        assert PriorityLevel.URGENT.value == "urgent"

    def test_training_request_days_back_validation(self) -> None:
        """Test: days_back muss zwischen 7 und 365 sein."""
        from app.api.v1.routing import TrainingRequest

        # Gueltige Werte
        valid = TrainingRequest(days_back=7)
        assert valid.days_back == 7

        valid = TrainingRequest(days_back=365)
        assert valid.days_back == 365
