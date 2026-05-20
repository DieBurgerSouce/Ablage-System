# -*- coding: utf-8 -*-
"""
Unit Tests for Predictive Payment Service.

Tests fuer:
- Feature Extraction
- Zahlungsverzoegerungs-Vorhersage
- Ausfallwahrscheinlichkeit
- Zahlungsbedingungen-Empfehlung
- Cash-Flow-Projektion

Phase 3: Predictive Payment AI
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.ai.predictive_payment_service import (
    PredictivePaymentService,
    PaymentFeatures,
    PaymentDelayPrediction,
    DefaultProbabilityPrediction,
    PaymentTermsSuggestion,
    CashFlowProjection,
    PredictionFeedback,
    RiskTier,
    PaymentTermSuggestion,
    get_predictive_payment_service,
)


class TestPaymentFeatures:
    """Tests fuer PaymentFeatures Datenklasse."""

    def test_default_initialization(self) -> None:
        """Test Default-Werte bei Initialisierung."""
        entity_id = uuid4()
        features = PaymentFeatures(entity_id=entity_id)

        assert features.entity_id == entity_id
        assert features.payment_history_avg_delay == 0.0
        assert features.payment_history_std_delay == 0.0
        assert features.total_invoices == 0
        assert features.paid_invoices == 0
        assert features.overdue_invoices == 0
        assert features.invoice_volume_total == 0.0
        assert features.current_outstanding == 0.0
        assert features.skonto_usage_rate == 0.0

    def test_to_dict_serialization(self) -> None:
        """Test Serialisierung zu Dictionary."""
        entity_id = uuid4()
        features = PaymentFeatures(
            entity_id=entity_id,
            payment_history_avg_delay=5.5,
            payment_history_std_delay=2.3,
            total_invoices=10,
            paid_invoices=8,
            overdue_invoices=1,
            invoice_volume_total=15000.50,
            current_outstanding=2500.00,
            skonto_usage_rate=0.75,
        )

        result = features.to_dict()

        assert result["entity_id"] == str(entity_id)
        assert result["payment_history_avg_delay"] == 5.5
        assert result["total_invoices"] == 10
        assert result["invoice_volume_total"] == 15000.50
        assert result["skonto_usage_rate"] == 0.75


class TestPredictivePaymentService:
    """Tests fuer PredictivePaymentService."""

    @pytest.fixture
    def service(self) -> PredictivePaymentService:
        """Erstelle Service-Instanz."""
        return PredictivePaymentService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstelle Mock DB-Session."""
        return AsyncMock()

    def test_singleton_instance(self) -> None:
        """Test Singleton-Pattern."""
        service1 = get_predictive_payment_service()
        service2 = get_predictive_payment_service()
        assert service1 is service2

    def test_classify_delay_risk_low(self, service: PredictivePaymentService) -> None:
        """Test Risiko-Klassifizierung: Niedrig."""
        assert service._classify_delay_risk(0) == RiskTier.LOW
        assert service._classify_delay_risk(1) == RiskTier.LOW
        assert service._classify_delay_risk(3) == RiskTier.LOW

    def test_classify_delay_risk_medium(self, service: PredictivePaymentService) -> None:
        """Test Risiko-Klassifizierung: Mittel."""
        assert service._classify_delay_risk(4) == RiskTier.MEDIUM
        assert service._classify_delay_risk(7) == RiskTier.MEDIUM
        assert service._classify_delay_risk(10) == RiskTier.MEDIUM

    def test_classify_delay_risk_high(self, service: PredictivePaymentService) -> None:
        """Test Risiko-Klassifizierung: Hoch."""
        assert service._classify_delay_risk(11) == RiskTier.HIGH
        assert service._classify_delay_risk(15) == RiskTier.HIGH
        assert service._classify_delay_risk(20) == RiskTier.HIGH

    def test_classify_delay_risk_critical(self, service: PredictivePaymentService) -> None:
        """Test Risiko-Klassifizierung: Kritisch."""
        assert service._classify_delay_risk(21) == RiskTier.CRITICAL
        assert service._classify_delay_risk(30) == RiskTier.CRITICAL
        assert service._classify_delay_risk(60) == RiskTier.CRITICAL

    def test_calculate_delay_prediction_base(self, service: PredictivePaymentService) -> None:
        """Test Delay-Berechnung mit Basis-Features."""
        entity_id = uuid4()
        features = PaymentFeatures(
            entity_id=entity_id,
            payment_history_avg_delay=5.0,
            payment_history_std_delay=2.0,
            total_invoices=10,
            paid_invoices=8,
            invoice_volume_total=25000.0,
            relationship_age_days=400,
        )

        predicted = service._calculate_delay_prediction(features)

        # Sollte nahe am historischen Durchschnitt liegen (5.0)
        # mit leichten Anpassungen durch Faktoren
        assert 3.0 <= predicted <= 8.0

    def test_calculate_delay_prediction_high_volume(self, service: PredictivePaymentService) -> None:
        """Test Delay-Berechnung bei hohem Volumen (reduziert Risiko)."""
        entity_id = uuid4()
        features = PaymentFeatures(
            entity_id=entity_id,
            payment_history_avg_delay=5.0,
            invoice_volume_total=100000.0,  # Hohes Volumen
            relationship_age_days=500,
        )

        predicted = service._calculate_delay_prediction(features)

        # Hohes Volumen sollte Delay reduzieren
        assert predicted < 5.0

    def test_calculate_prediction_confidence_low_data(
        self, service: PredictivePaymentService
    ) -> None:
        """Test Konfidenz bei wenig Daten."""
        features = PaymentFeatures(
            entity_id=uuid4(),
            paid_invoices=2,
            relationship_age_days=30,
        )

        confidence = service._calculate_prediction_confidence(features)

        # Wenig Daten = niedrige Konfidenz
        assert confidence < 0.6

    def test_calculate_prediction_confidence_high_data(
        self, service: PredictivePaymentService
    ) -> None:
        """Test Konfidenz bei viel Daten."""
        features = PaymentFeatures(
            entity_id=uuid4(),
            paid_invoices=15,
            relationship_age_days=500,
            payment_history_std_delay=2.0,  # Niedrige Varianz
            invoice_volume_last_90_days=5000.0,
        )

        confidence = service._calculate_prediction_confidence(features)

        # Viel Daten = hohe Konfidenz
        assert confidence >= 0.7

    def test_get_top_delay_factors(self, service: PredictivePaymentService) -> None:
        """Test Identifikation der Top-Faktoren."""
        features = PaymentFeatures(
            entity_id=uuid4(),
            payment_history_avg_delay=10.0,
            max_dunning_level_reached=2,
            current_overdue=5000.0,
            relationship_age_days=60,  # Kurze Beziehung
        )

        factors = service._get_top_delay_factors(features, 12.0)

        # Sollte mindestens einen Faktor zurueckgeben
        assert len(factors) >= 1
        # Faktoren sollten Tupel (name, weight) sein
        assert all(len(f) == 2 for f in factors)
        # Gewichte sollten 0-1 sein
        assert all(0 <= f[1] <= 1 for f in factors)

    def test_clear_feature_cache(self, service: PredictivePaymentService) -> None:
        """Test Cache-Loeschung."""
        entity_id = uuid4()

        # Cache simulieren
        service._feature_cache[str(entity_id)] = (
            PaymentFeatures(entity_id=entity_id),
            datetime.now(timezone.utc),
        )

        assert str(entity_id) in service._feature_cache

        # Einzelne Entity loeschen
        service.clear_feature_cache(entity_id)
        assert str(entity_id) not in service._feature_cache

        # Alle loeschen
        service._feature_cache["test"] = ("dummy", datetime.now(timezone.utc))
        service.clear_feature_cache()
        assert len(service._feature_cache) == 0


class TestPaymentDelayPrediction:
    """Tests fuer PaymentDelayPrediction Datenklasse."""

    def test_prediction_creation(self) -> None:
        """Test Erstellung einer Vorhersage."""
        entity_id = uuid4()
        prediction = PaymentDelayPrediction(
            entity_id=entity_id,
            predicted_delay_days=7.5,
            confidence=0.85,
            risk_tier=RiskTier.MEDIUM,
            delay_range_min=4.0,
            delay_range_max=12.0,
            top_factors=[("historical_payment_behavior", 0.8)],
        )

        assert prediction.entity_id == entity_id
        assert prediction.predicted_delay_days == 7.5
        assert prediction.confidence == 0.85
        assert prediction.risk_tier == RiskTier.MEDIUM
        assert len(prediction.top_factors) == 1


class TestDefaultProbabilityPrediction:
    """Tests fuer DefaultProbabilityPrediction."""

    def test_prediction_creation(self) -> None:
        """Test Erstellung einer Ausfallvorhersage."""
        entity_id = uuid4()
        prediction = DefaultProbabilityPrediction(
            entity_id=entity_id,
            default_probability=0.15,
            confidence=0.75,
            risk_tier=RiskTier.MEDIUM,
            contributing_factors={"overdue_rate": 0.1, "dunning_level": 1},
        )

        assert prediction.entity_id == entity_id
        assert prediction.default_probability == 0.15
        assert "overdue_rate" in prediction.contributing_factors


class TestPaymentTermsSuggestion:
    """Tests fuer PaymentTermsSuggestion."""

    def test_suggestion_creation(self) -> None:
        """Test Erstellung einer Zahlungsbedingungen-Empfehlung."""
        entity_id = uuid4()
        expected_date = datetime.now(timezone.utc) + timedelta(days=30)

        suggestion = PaymentTermsSuggestion(
            entity_id=entity_id,
            invoice_amount=5000.0,
            suggested_term=PaymentTermSuggestion.NET_30,
            suggested_days=30,
            suggested_skonto_percentage=2.0,
            suggested_skonto_days=10,
            expected_payment_date=expected_date,
            reasoning="Standard-Konditionen",
            confidence=0.8,
        )

        assert suggestion.entity_id == entity_id
        assert suggestion.suggested_term == PaymentTermSuggestion.NET_30
        assert suggestion.suggested_skonto_percentage == 2.0


class TestCashFlowProjection:
    """Tests fuer CashFlowProjection."""

    def test_projection_creation(self) -> None:
        """Test Erstellung einer Cash-Flow-Projektion."""
        projection = CashFlowProjection(
            projection_date=datetime.now(timezone.utc),
            days_ahead=5,
            expected_inflow=10000.0,
            expected_inflow_min=8000.0,
            expected_inflow_max=12000.0,
            expected_outflow=5000.0,
            net_flow=5000.0,
            cumulative_balance=15000.0,
        )

        assert projection.expected_inflow == 10000.0
        assert projection.net_flow == 5000.0
        assert projection.cumulative_balance == 15000.0


class TestPredictionFeedback:
    """Tests fuer PredictionFeedback."""

    def test_feedback_creation(self) -> None:
        """Test Erstellung eines Feedback-Objekts."""
        entity_id = uuid4()
        feedback = PredictionFeedback(
            prediction_id="pred-123",
            entity_id=entity_id,
            prediction_type="delay",
            predicted_value=5.0,
            actual_value=7.0,
        )

        assert feedback.entity_id == entity_id
        assert feedback.prediction_type == "delay"
        assert feedback.predicted_value == 5.0
        assert feedback.actual_value == 7.0
        # was_accurate sollte False sein da |5-7| > 3
        assert feedback.was_accurate == False


class TestRiskTierEnum:
    """Tests fuer RiskTier Enum."""

    def test_risk_tier_values(self) -> None:
        """Test Enum-Werte."""
        assert RiskTier.LOW.value == "low"
        assert RiskTier.MEDIUM.value == "medium"
        assert RiskTier.HIGH.value == "high"
        assert RiskTier.CRITICAL.value == "critical"


class TestPaymentTermSuggestionEnum:
    """Tests fuer PaymentTermSuggestion Enum."""

    def test_payment_term_values(self) -> None:
        """Test Enum-Werte."""
        assert PaymentTermSuggestion.PREPAYMENT.value == "prepayment"
        assert PaymentTermSuggestion.NET_30.value == "net_30"
        assert PaymentTermSuggestion.NET_60.value == "net_60"
        assert PaymentTermSuggestion.INSTALLMENT.value == "installment"
