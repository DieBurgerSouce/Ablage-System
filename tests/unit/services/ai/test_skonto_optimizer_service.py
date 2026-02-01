# -*- coding: utf-8 -*-
"""
Unit Tests for Skonto Optimizer Service.

Tests fuer:
- Skonto-Nutzungswahrscheinlichkeit
- Optimale Skonto-Konditionen
- Cash-Flow-Impact-Analyse

Phase 3: Predictive Payment AI
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.ai.skonto_optimizer_service import (
    SkontoOptimizerService,
    SkontoUsagePrediction,
    OptimalSkontoTerms,
    SkontoImpactAnalysis,
    STANDARD_SKONTO_TIERS,
    CAPITAL_COST_RATE,
    get_skonto_optimizer_service,
)
from app.services.ai.predictive_payment_service import (
    PaymentFeatures,
    RiskTier,
)


class TestSkontoOptimizerService:
    """Tests fuer SkontoOptimizerService."""

    @pytest.fixture
    def service(self) -> SkontoOptimizerService:
        """Erstelle Service-Instanz."""
        return SkontoOptimizerService()

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Erstelle Mock DB-Session."""
        return AsyncMock()

    def test_singleton_instance(self) -> None:
        """Test Singleton-Pattern."""
        service1 = get_skonto_optimizer_service()
        service2 = get_skonto_optimizer_service()
        assert service1 is service2

    def test_calculate_confidence_low_data(self, service: SkontoOptimizerService) -> None:
        """Test Konfidenz bei wenig Daten."""
        features = PaymentFeatures(
            entity_id=uuid4(),
            paid_invoices=1,
            relationship_age_days=10,
        )

        confidence = service._calculate_confidence(features)

        # Wenig Daten = niedrige Konfidenz
        assert confidence < 0.7

    def test_calculate_confidence_high_data(self, service: SkontoOptimizerService) -> None:
        """Test Konfidenz bei viel Daten."""
        features = PaymentFeatures(
            entity_id=uuid4(),
            paid_invoices=20,
            relationship_age_days=800,
            payment_history_std_delay=2.0,
        )

        confidence = service._calculate_confidence(features)

        # Viel Daten = hohe Konfidenz
        assert confidence >= 0.8


class TestSkontoUsagePrediction:
    """Tests fuer SkontoUsagePrediction Datenklasse."""

    def test_prediction_creation(self) -> None:
        """Test Erstellung einer Vorhersage."""
        entity_id = uuid4()
        prediction = SkontoUsagePrediction(
            entity_id=entity_id,
            usage_probability=0.65,
            confidence=0.75,
            historical_usage_rate=0.70,
            total_skonto_eligible=10,
            total_skonto_used=7,
            contributing_factors={"historical_usage_rate": 0.70},
        )

        assert prediction.entity_id == entity_id
        assert prediction.usage_probability == 0.65
        assert prediction.confidence == 0.75
        assert prediction.historical_usage_rate == 0.70
        assert "historical_usage_rate" in prediction.contributing_factors


class TestOptimalSkontoTerms:
    """Tests fuer OptimalSkontoTerms Datenklasse."""

    def test_terms_creation(self) -> None:
        """Test Erstellung einer Empfehlung."""
        entity_id = uuid4()
        terms = OptimalSkontoTerms(
            entity_id=entity_id,
            invoice_amount=5000.0,
            recommended_percentage=2.0,
            recommended_days=10,
            net_payment_days=30,
            expected_usage_probability=0.65,
            expected_savings_if_used=100.0,
            expected_cash_advance_days=20.0,
            expected_net_benefit=15.0,
            reasoning="Standard-Empfehlung",
            confidence=0.8,
        )

        assert terms.entity_id == entity_id
        assert terms.recommended_percentage == 2.0
        assert terms.recommended_days == 10
        assert terms.expected_savings_if_used == 100.0


class TestSkontoImpactAnalysis:
    """Tests fuer SkontoImpactAnalysis Datenklasse."""

    def test_analysis_creation(self) -> None:
        """Test Erstellung einer Analyse."""
        analysis = SkontoImpactAnalysis(
            days_analyzed=30,
            total_invoices_analyzed=15,
            total_skonto_eligible_amount=50000.0,
            expected_skonto_usage_amount=30000.0,
            expected_total_discount=600.0,
            expected_working_capital_improvement=50.0,
        )

        assert analysis.days_analyzed == 30
        assert analysis.total_invoices_analyzed == 15
        assert analysis.total_skonto_eligible_amount == 50000.0
        assert analysis.expected_skonto_usage_amount == 30000.0


class TestStandardSkontoTiers:
    """Tests fuer Standard-Skonto-Staffeln."""

    def test_tiers_defined(self) -> None:
        """Test dass Staffeln definiert sind."""
        assert len(STANDARD_SKONTO_TIERS) >= 3

    def test_tier_structure(self) -> None:
        """Test Struktur der Staffeln."""
        for tier in STANDARD_SKONTO_TIERS:
            assert "percentage" in tier
            assert "days" in tier
            assert "name" in tier
            assert tier["percentage"] > 0
            assert tier["days"] > 0

    def test_tiers_sorted_by_percentage(self) -> None:
        """Test dass Staffeln nach Prozent sortiert sind (absteigend)."""
        percentages = [tier["percentage"] for tier in STANDARD_SKONTO_TIERS]
        assert percentages == sorted(percentages, reverse=True)


class TestCapitalCostRate:
    """Tests fuer Kapitalkosten-Rate."""

    def test_rate_reasonable(self) -> None:
        """Test dass Rate im vernuenftigen Bereich."""
        assert 0.01 <= CAPITAL_COST_RATE <= 0.15
        assert CAPITAL_COST_RATE == 0.05  # 5% p.a.
