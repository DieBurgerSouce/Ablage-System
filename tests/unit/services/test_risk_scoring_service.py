# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Risk Scoring Service v2.0.

Testet:
- Risk Factor Berechnung (Payment Delay, Default Rate, etc.)
- Score-Berechnung (0-100 Skala)
- Gewichtete Aggregation
- Edge Cases (keine Daten, Grenzwerte)
- Entity Risk Update
- V2: Industry Risk Scoring
- V2: Payment Trend Analysis (Linear Regression)
- V2: External Data Provider Stubs
- V2: Recommendations Generation

Feinpoliert und durchdacht - Risk Scoring Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from app.services.risk_scoring_service import (
    RiskScoringService,
    RiskFactors,
    RiskFactor,
    RiskScoreDetailedResponse,
    RiskLevel,
    TrendDirection,
    RISK_WEIGHTS_V1,
    RISK_WEIGHTS_V2,
    INDUSTRY_RISK_SCORES,
    ExternalDataProvider,
    NorthDataProvider,
    SchufaB2BProvider,
    CreditreformProvider,
    ExternalData,
    get_risk_scoring_service,
    reset_risk_scoring_service,
)


# ========================= Test Fixtures =========================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_risk_scoring_service()
    yield
    reset_risk_scoring_service()


@pytest.fixture
def risk_service_v1() -> RiskScoringService:
    """Create RiskScoringService instance with V1 weights."""
    return RiskScoringService(use_v2_weights=False)


@pytest.fixture
def risk_service_v2() -> RiskScoringService:
    """Create RiskScoringService instance with V2 weights."""
    return RiskScoringService(use_v2_weights=True)


@pytest.fixture
def sample_entity_id() -> UUID:
    """Provide sample entity UUID."""
    return uuid4()


@pytest.fixture
def empty_factors() -> RiskFactors:
    """Provide empty RiskFactors instance."""
    return RiskFactors()


@pytest.fixture
def high_risk_factors() -> RiskFactors:
    """Provide high-risk RiskFactors instance."""
    factors = RiskFactors()
    factors.payment_delay_days = 45.0  # Stark ueberfaellig
    factors.default_rate = 0.25  # 25% Ausfallrate
    factors.invoice_volume = 1000.0  # Niedriges Volumen
    factors.document_frequency = 0.5  # Selten
    factors.relationship_months = 3.0  # Kurze Beziehung
    factors.total_invoices = 20
    factors.paid_invoices = 10
    factors.overdue_invoices = 5
    factors.open_invoices = 5
    # V2 fields
    factors.industry_code = "startup"
    factors.industry_risk_score = 85.0
    factors.payment_trend = TrendDirection.WORSENING
    factors.trend_slope = 2.5
    factors.trend_adjustment = 10
    return factors


@pytest.fixture
def low_risk_factors() -> RiskFactors:
    """Provide low-risk RiskFactors instance."""
    factors = RiskFactors()
    factors.payment_delay_days = 0.0  # Keine Verzoegerung
    factors.default_rate = 0.0  # Keine Ausfaelle
    factors.invoice_volume = 150000.0  # Hohes Volumen
    factors.document_frequency = 15.0  # Regelmaessig
    factors.relationship_months = 36.0  # Lange Beziehung
    factors.total_invoices = 100
    factors.paid_invoices = 100
    factors.overdue_invoices = 0
    factors.open_invoices = 0
    # V2 fields
    factors.industry_code = "government"
    factors.industry_risk_score = 5.0
    factors.payment_trend = TrendDirection.IMPROVING
    factors.trend_slope = -1.5
    factors.trend_adjustment = -10
    return factors


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = Mock()
    return session


# ========================= RiskFactors Tests =========================


class TestRiskFactors:
    """Tests for RiskFactors data class."""

    def test_default_values(self):
        """Default-Werte sollten 0 sein."""
        factors = RiskFactors()

        assert factors.payment_delay_days == 0.0
        assert factors.default_rate == 0.0
        assert factors.invoice_volume == 0.0
        assert factors.document_frequency == 0.0
        assert factors.relationship_months == 0.0
        assert factors.total_invoices == 0
        assert factors.paid_invoices == 0
        assert factors.overdue_invoices == 0
        assert factors.open_invoices == 0
        # V2 defaults
        assert factors.industry_code == "unknown"
        assert factors.industry_risk_score == 50.0
        assert factors.payment_trend == TrendDirection.STABLE
        assert factors.trend_slope == 0.0
        assert factors.trend_adjustment == 0
        assert factors.external_data is None
        assert factors.economic_indicator_score == 50.0

    def test_to_dict(self, high_risk_factors: RiskFactors):
        """to_dict() sollte korrekte Struktur liefern."""
        result = high_risk_factors.to_dict()

        # V1 fields
        assert "payment_delay_days" in result
        assert "default_rate" in result
        assert "invoice_volume" in result
        assert "document_frequency" in result
        assert "relationship_months" in result
        assert "total_invoices" in result
        assert "paid_invoices" in result
        assert "overdue_invoices" in result
        assert "open_invoices" in result
        # V2 fields
        assert "industry_code" in result
        assert "industry_risk_score" in result
        assert "payment_trend" in result
        assert "trend_slope" in result
        assert "trend_adjustment" in result
        assert "economic_indicator_score" in result

    def test_to_dict_rounded_values(self):
        """to_dict() sollte Werte korrekt runden."""
        factors = RiskFactors()
        factors.payment_delay_days = 12.3456
        factors.default_rate = 0.156789
        factors.invoice_volume = 12345.6789
        factors.document_frequency = 5.789
        factors.relationship_months = 8.888
        factors.industry_risk_score = 42.567
        factors.trend_slope = 1.2345
        factors.economic_indicator_score = 55.555

        result = factors.to_dict()

        assert result["payment_delay_days"] == 12.3  # 1 Dezimalstelle
        assert result["default_rate"] == 15.7  # Als Prozent, 1 Dezimalstelle
        assert result["invoice_volume"] == 12345.68  # 2 Dezimalstellen
        assert result["document_frequency"] == 5.79  # 2 Dezimalstellen
        assert result["relationship_months"] == 8.9  # 1 Dezimalstelle
        assert result["industry_risk_score"] == 42.6  # 1 Dezimalstelle
        assert result["trend_slope"] == 1.23  # 2 Dezimalstellen
        assert result["economic_indicator_score"] == 55.6  # 1 Dezimalstelle

    def test_to_dict_with_external_data(self):
        """to_dict() sollte externe Daten korrekt einbinden."""
        factors = RiskFactors()
        factors.external_data = ExternalData(
            provider="north_data",
            credit_score=35,
            credit_rating="A",
        )

        result = factors.to_dict()

        assert result["external_data_provider"] == "north_data"
        assert result["external_credit_score"] == 35


# ========================= Score Calculation Tests =========================


class TestPaymentDelayScoring:
    """Tests for payment delay scoring."""

    def test_no_delay_returns_zero(self, risk_service_v2: RiskScoringService):
        """Keine Verzoegerung sollte Score 0 ergeben."""
        assert risk_service_v2._score_payment_delay(0.0) == 0.0
        assert risk_service_v2._score_payment_delay(-5.0) == 0.0

    def test_max_delay_returns_hundred(self, risk_service_v2: RiskScoringService):
        """30+ Tage sollte Score 100 ergeben."""
        assert risk_service_v2._score_payment_delay(30.0) == 100.0
        assert risk_service_v2._score_payment_delay(60.0) == 100.0
        assert risk_service_v2._score_payment_delay(90.0) == 100.0

    def test_linear_scaling(self, risk_service_v2: RiskScoringService):
        """Score sollte linear skalieren zwischen 0 und 30 Tagen."""
        assert risk_service_v2._score_payment_delay(15.0) == 50.0
        assert abs(risk_service_v2._score_payment_delay(10.0) - 33.33) < 0.1
        assert abs(risk_service_v2._score_payment_delay(20.0) - 66.67) < 0.1


class TestDefaultRateScoring:
    """Tests for default rate scoring."""

    def test_no_defaults_returns_zero(self, risk_service_v2: RiskScoringService):
        """Keine Ausfaelle sollte Score 0 ergeben."""
        assert risk_service_v2._score_default_rate(0.0) == 0.0
        assert risk_service_v2._score_default_rate(-0.05) == 0.0

    def test_high_default_rate_returns_hundred(self, risk_service_v2: RiskScoringService):
        """20%+ Ausfallrate sollte Score 100 ergeben."""
        assert risk_service_v2._score_default_rate(0.20) == 100.0
        assert risk_service_v2._score_default_rate(0.50) == 100.0
        assert risk_service_v2._score_default_rate(1.0) == 100.0

    def test_linear_scaling(self, risk_service_v2: RiskScoringService):
        """Score sollte linear skalieren zwischen 0% und 20%."""
        assert risk_service_v2._score_default_rate(0.10) == pytest.approx(50.0)
        assert risk_service_v2._score_default_rate(0.05) == pytest.approx(25.0)
        assert risk_service_v2._score_default_rate(0.15) == pytest.approx(75.0)


class TestInvoiceVolumeScoring:
    """Tests for invoice volume scoring."""

    def test_no_volume_returns_high_score(self, risk_service_v2: RiskScoringService):
        """Kein Volumen sollte hohen Score (80) ergeben."""
        assert risk_service_v2._score_invoice_volume(0.0) == 80.0
        assert risk_service_v2._score_invoice_volume(-1000.0) == 80.0

    def test_high_volume_returns_zero(self, risk_service_v2: RiskScoringService):
        """100k+ EUR sollte Score 0 ergeben."""
        assert risk_service_v2._score_invoice_volume(100000.0) == 0.0
        assert risk_service_v2._score_invoice_volume(500000.0) == 0.0

    def test_linear_scaling(self, risk_service_v2: RiskScoringService):
        """Score sollte linear abnehmen mit steigendem Volumen."""
        assert risk_service_v2._score_invoice_volume(50000.0) == 40.0
        assert risk_service_v2._score_invoice_volume(25000.0) == 60.0


class TestDocumentFrequencyScoring:
    """Tests for document frequency scoring."""

    def test_no_frequency_returns_high_score(self, risk_service_v2: RiskScoringService):
        """Keine Dokumente sollte Score 60 ergeben."""
        assert risk_service_v2._score_document_frequency(0.0) == 60.0
        assert risk_service_v2._score_document_frequency(-1.0) == 60.0

    def test_high_frequency_returns_zero(self, risk_service_v2: RiskScoringService):
        """10+ Dokumente/Monat sollte Score 0 ergeben."""
        assert risk_service_v2._score_document_frequency(10.0) == 0.0
        assert risk_service_v2._score_document_frequency(20.0) == 0.0

    def test_linear_scaling(self, risk_service_v2: RiskScoringService):
        """Score sollte linear abnehmen mit steigender Frequenz."""
        assert risk_service_v2._score_document_frequency(5.0) == 30.0
        assert risk_service_v2._score_document_frequency(2.5) == 45.0


class TestRelationshipAgeScoring:
    """Tests for relationship age scoring."""

    def test_new_relationship_returns_high_score(self, risk_service_v2: RiskScoringService):
        """Neue Beziehung sollte Score 70 ergeben."""
        assert risk_service_v2._score_relationship_age(0.0) == 70.0
        assert risk_service_v2._score_relationship_age(-1.0) == 70.0

    def test_long_relationship_returns_zero(self, risk_service_v2: RiskScoringService):
        """24+ Monate sollte Score 0 ergeben."""
        assert risk_service_v2._score_relationship_age(24.0) == 0.0
        assert risk_service_v2._score_relationship_age(48.0) == 0.0

    def test_linear_scaling(self, risk_service_v2: RiskScoringService):
        """Score sollte linear abnehmen mit zunehmender Beziehungsdauer."""
        assert risk_service_v2._score_relationship_age(12.0) == 35.0
        assert risk_service_v2._score_relationship_age(6.0) == 52.5


# ========================= V2: Payment Trend Scoring Tests =========================


class TestPaymentTrendScoring:
    """Tests for V2 payment trend scoring."""

    def test_improving_trend_returns_low_score(self, risk_service_v2: RiskScoringService):
        """Verbessernder Trend sollte niedrigen Score ergeben."""
        # Stark verbessernd (slope = -2.0)
        score = risk_service_v2._score_payment_trend(-2.0, TrendDirection.IMPROVING)
        assert score < 30  # Niedriger Score

    def test_worsening_trend_returns_high_score(self, risk_service_v2: RiskScoringService):
        """Verschlechternder Trend sollte hohen Score ergeben."""
        # Stark verschlechternd (slope = 3.0)
        score = risk_service_v2._score_payment_trend(3.0, TrendDirection.WORSENING)
        assert score > 60  # Hoher Score

    def test_stable_trend_returns_medium_score(self, risk_service_v2: RiskScoringService):
        """Stabiler Trend sollte mittleren Score ergeben."""
        score = risk_service_v2._score_payment_trend(0.0, TrendDirection.STABLE)
        assert 30 <= score <= 60  # Mittlerer Score


# ========================= V2: Linear Regression Tests =========================


class TestLinearRegression:
    """Tests for V2 linear regression implementation."""

    def test_positive_slope(self, risk_service_v2: RiskScoringService):
        """Positive Steigung sollte erkannt werden."""
        # Daten: Y steigt mit X
        data_points = [(0.0, 0.0), (1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]
        slope, intercept = risk_service_v2._linear_regression(data_points)

        assert slope == pytest.approx(2.0, rel=0.01)
        assert intercept == pytest.approx(0.0, rel=0.01)

    def test_negative_slope(self, risk_service_v2: RiskScoringService):
        """Negative Steigung sollte erkannt werden."""
        # Daten: Y faellt mit X
        data_points = [(0.0, 6.0), (1.0, 4.0), (2.0, 2.0), (3.0, 0.0)]
        slope, intercept = risk_service_v2._linear_regression(data_points)

        assert slope == pytest.approx(-2.0, rel=0.01)
        assert intercept == pytest.approx(6.0, rel=0.01)

    def test_flat_line(self, risk_service_v2: RiskScoringService):
        """Flache Linie sollte Steigung 0 haben."""
        data_points = [(0.0, 5.0), (1.0, 5.0), (2.0, 5.0), (3.0, 5.0)]
        slope, intercept = risk_service_v2._linear_regression(data_points)

        assert slope == pytest.approx(0.0, abs=0.01)
        assert intercept == pytest.approx(5.0, rel=0.01)

    def test_empty_data(self, risk_service_v2: RiskScoringService):
        """Leere Daten sollten (0, 0) liefern."""
        slope, intercept = risk_service_v2._linear_regression([])

        assert slope == 0.0
        assert intercept == 0.0


# ========================= RISK_WEIGHTS Tests =========================


class TestRiskWeightsV1:
    """Tests for V1 risk weight configuration."""

    def test_weights_sum_to_one(self):
        """V1 Gewichte sollten sich zu 1.0 summieren."""
        total = sum(RISK_WEIGHTS_V1.values())
        assert abs(total - 1.0) < 0.001

    def test_required_weights_present(self):
        """Alle V1 Gewichte sollten vorhanden sein."""
        required_keys = [
            "payment_delay",
            "default_rate",
            "invoice_volume",
            "document_frequency",
            "relationship_age",
        ]
        for key in required_keys:
            assert key in RISK_WEIGHTS_V1

    def test_payment_factors_have_higher_weight(self):
        """Zahlungsfaktoren sollten hoehere Gewichtung haben."""
        payment_weight = RISK_WEIGHTS_V1["payment_delay"] + RISK_WEIGHTS_V1["default_rate"]
        other_weight = (
            RISK_WEIGHTS_V1["invoice_volume"]
            + RISK_WEIGHTS_V1["document_frequency"]
            + RISK_WEIGHTS_V1["relationship_age"]
        )

        assert payment_weight > other_weight


class TestRiskWeightsV2:
    """Tests for V2 risk weight configuration."""

    def test_weights_sum_to_one(self):
        """V2 Gewichte sollten sich zu 1.0 summieren."""
        total = sum(RISK_WEIGHTS_V2.values())
        assert abs(total - 1.0) < 0.001

    def test_v2_new_weights_present(self):
        """V2-spezifische Gewichte sollten vorhanden sein."""
        v2_keys = ["industry_risk", "payment_trend", "economic_indicators"]
        for key in v2_keys:
            assert key in RISK_WEIGHTS_V2

    def test_payment_trend_has_significant_weight(self):
        """Payment Trend sollte signifikante Gewichtung haben."""
        assert RISK_WEIGHTS_V2["payment_trend"] >= 0.15


# ========================= V2: Industry Risk Tests =========================


class TestIndustryRiskScores:
    """Tests for industry risk scoring."""

    def test_low_risk_industries(self):
        """Low-Risk Branchen sollten Score < 25 haben."""
        low_risk = ["healthcare", "utilities", "government", "public_sector"]
        for industry in low_risk:
            assert INDUSTRY_RISK_SCORES[industry] < 25

    def test_high_risk_industries(self):
        """High-Risk Branchen sollten Score > 50 haben."""
        high_risk = ["construction", "hospitality", "tourism"]
        for industry in high_risk:
            assert INDUSTRY_RISK_SCORES[industry] > 50

    def test_very_high_risk_industries(self):
        """Very High-Risk Branchen sollten Score > 70 haben."""
        very_high = ["startup", "crypto"]
        for industry in very_high:
            assert INDUSTRY_RISK_SCORES[industry] > 70

    def test_unknown_industry_default(self):
        """Unknown sollte mittleren Score (50) haben."""
        assert INDUSTRY_RISK_SCORES["unknown"] == 50


# ========================= V2: External Data Provider Tests =========================


class TestExternalDataProviders:
    """Tests for external data provider stubs."""

    @pytest.mark.asyncio
    async def test_north_data_provider_returns_none(self):
        """NorthData Provider sollte None zurueckgeben (Stub)."""
        provider = NorthDataProvider()
        result = await provider.get_company_data(uuid4(), "DE123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_north_data_provider_not_available(self):
        """NorthData Provider sollte nicht verfuegbar sein."""
        provider = NorthDataProvider()
        is_available = await provider.is_available()

        assert is_available is False

    @pytest.mark.asyncio
    async def test_schufa_b2b_provider_returns_none(self):
        """SchufaB2B Provider sollte None zurueckgeben (Stub)."""
        provider = SchufaB2BProvider()
        result = await provider.get_company_data(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_creditreform_provider_returns_none(self):
        """Creditreform Provider sollte None zurueckgeben (Stub)."""
        provider = CreditreformProvider()
        result = await provider.get_company_data(uuid4())

        assert result is None

    def test_provider_names(self):
        """Provider-Namen sollten korrekt sein."""
        assert NorthDataProvider().provider_name == "north_data"
        assert SchufaB2BProvider().provider_name == "schufa_b2b"
        assert CreditreformProvider().provider_name == "creditreform"


# ========================= V2: Risk Level Tests =========================


class TestRiskLevelClassification:
    """Tests for risk level classification."""

    def test_low_risk_level(self, risk_service_v2: RiskScoringService):
        """Score < 25 sollte LOW Level ergeben."""
        assert risk_service_v2._get_risk_level(0) == RiskLevel.LOW
        assert risk_service_v2._get_risk_level(24.9) == RiskLevel.LOW

    def test_medium_risk_level(self, risk_service_v2: RiskScoringService):
        """25 <= Score < 50 sollte MEDIUM Level ergeben."""
        assert risk_service_v2._get_risk_level(25) == RiskLevel.MEDIUM
        assert risk_service_v2._get_risk_level(49.9) == RiskLevel.MEDIUM

    def test_high_risk_level(self, risk_service_v2: RiskScoringService):
        """50 <= Score < 75 sollte HIGH Level ergeben."""
        assert risk_service_v2._get_risk_level(50) == RiskLevel.HIGH
        assert risk_service_v2._get_risk_level(74.9) == RiskLevel.HIGH

    def test_critical_risk_level(self, risk_service_v2: RiskScoringService):
        """Score >= 75 sollte CRITICAL Level ergeben."""
        assert risk_service_v2._get_risk_level(75) == RiskLevel.CRITICAL
        assert risk_service_v2._get_risk_level(100) == RiskLevel.CRITICAL


# ========================= V2: Recommendations Tests =========================


class TestRecommendationsGeneration:
    """Tests for German recommendation generation."""

    def test_high_payment_delay_recommendation(
        self, risk_service_v2: RiskScoringService
    ):
        """Hohe Zahlungsverzoegerung sollte Empfehlung generieren."""
        factors = RiskFactors()
        factors.payment_delay_days = 20.0

        recommendations = risk_service_v2._generate_recommendations(
            factors, RiskLevel.MEDIUM
        )

        assert any("Zahlungsbedingungen" in r for r in recommendations)

    def test_high_default_rate_recommendation(
        self, risk_service_v2: RiskScoringService
    ):
        """Hohe Ausfallrate sollte Empfehlung generieren."""
        factors = RiskFactors()
        factors.default_rate = 0.15

        recommendations = risk_service_v2._generate_recommendations(
            factors, RiskLevel.HIGH
        )

        assert any("Kreditlimit" in r for r in recommendations)

    def test_worsening_trend_recommendation(
        self, risk_service_v2: RiskScoringService
    ):
        """Verschlechternder Trend sollte Empfehlung generieren."""
        factors = RiskFactors()
        factors.payment_trend = TrendDirection.WORSENING

        recommendations = risk_service_v2._generate_recommendations(
            factors, RiskLevel.MEDIUM
        )

        assert any("Liquiditaetsprobleme" in r for r in recommendations)

    def test_critical_risk_adds_warning(
        self, risk_service_v2: RiskScoringService
    ):
        """Kritisches Risiko sollte Warnung hinzufuegen."""
        factors = RiskFactors()

        recommendations = risk_service_v2._generate_recommendations(
            factors, RiskLevel.CRITICAL
        )

        assert recommendations[0].startswith("ACHTUNG")

    def test_no_issues_returns_default_recommendation(
        self, risk_service_v2: RiskScoringService
    ):
        """Keine Probleme sollte Default-Empfehlung liefern."""
        factors = RiskFactors()
        factors.payment_delay_days = 0.0
        factors.default_rate = 0.0
        factors.payment_trend = TrendDirection.STABLE
        factors.industry_risk_score = 30.0
        factors.relationship_months = 24.0

        recommendations = risk_service_v2._generate_recommendations(
            factors, RiskLevel.LOW
        )

        assert any("Keine besonderen Massnahmen" in r for r in recommendations)


# ========================= V2: Trend Description Tests =========================


class TestTrendDescriptions:
    """Tests for German trend descriptions."""

    def test_improving_trend_description(self, risk_service_v2: RiskScoringService):
        """Verbessernder Trend sollte deutsche Beschreibung haben."""
        desc = risk_service_v2._get_trend_description(TrendDirection.IMPROVING, -1.5)

        assert "verbessert sich" in desc
        assert "1.5" in desc

    def test_worsening_trend_description(self, risk_service_v2: RiskScoringService):
        """Verschlechternder Trend sollte deutsche Beschreibung haben."""
        desc = risk_service_v2._get_trend_description(TrendDirection.WORSENING, 2.0)

        assert "verschlechtert sich" in desc
        assert "2.0" in desc

    def test_stable_trend_description(self, risk_service_v2: RiskScoringService):
        """Stabiler Trend sollte deutsche Beschreibung haben."""
        desc = risk_service_v2._get_trend_description(TrendDirection.STABLE, 0.0)

        assert "stabil" in desc


# ========================= Integration Tests =========================


class TestRiskScoreCalculation:
    """Integration tests for full risk score calculation."""

    def test_high_risk_entity_v1(self, risk_service_v1: RiskScoringService):
        """Hohes Risiko sollte hohen Score ergeben (V1)."""
        delay_score = risk_service_v1._score_payment_delay(45.0)  # 100
        default_score = risk_service_v1._score_default_rate(0.25)  # 100
        volume_score = risk_service_v1._score_invoice_volume(1000.0)  # ~79.2
        freq_score = risk_service_v1._score_document_frequency(0.5)  # ~57
        age_score = risk_service_v1._score_relationship_age(3.0)  # ~61.25

        weighted_score = (
            delay_score * RISK_WEIGHTS_V1["payment_delay"]
            + default_score * RISK_WEIGHTS_V1["default_rate"]
            + volume_score * RISK_WEIGHTS_V1["invoice_volume"]
            + freq_score * RISK_WEIGHTS_V1["document_frequency"]
            + age_score * RISK_WEIGHTS_V1["relationship_age"]
        )

        assert weighted_score > 75.0  # Hohes Risiko

    def test_low_risk_entity_v1(self, risk_service_v1: RiskScoringService):
        """Niedriges Risiko sollte niedrigen Score ergeben (V1)."""
        delay_score = risk_service_v1._score_payment_delay(0.0)  # 0
        default_score = risk_service_v1._score_default_rate(0.0)  # 0
        volume_score = risk_service_v1._score_invoice_volume(150000.0)  # 0
        freq_score = risk_service_v1._score_document_frequency(15.0)  # 0
        age_score = risk_service_v1._score_relationship_age(36.0)  # 0

        weighted_score = (
            delay_score * RISK_WEIGHTS_V1["payment_delay"]
            + default_score * RISK_WEIGHTS_V1["default_rate"]
            + volume_score * RISK_WEIGHTS_V1["invoice_volume"]
            + freq_score * RISK_WEIGHTS_V1["document_frequency"]
            + age_score * RISK_WEIGHTS_V1["relationship_age"]
        )

        assert weighted_score < 25.0  # Niedriges Risiko

    def test_payment_behavior_score_inverse(self, risk_service_v2: RiskScoringService):
        """Payment Behavior Score sollte inverse Beziehung zu Risk Score haben."""
        # Guter Zahler
        delay_score_good = risk_service_v2._score_payment_delay(0.0)  # 0
        default_score_good = risk_service_v2._score_default_rate(0.0)  # 0
        payment_behavior_good = 100 - (delay_score_good * 0.6 + default_score_good * 0.4)

        # Schlechter Zahler
        delay_score_bad = risk_service_v2._score_payment_delay(30.0)  # 100
        default_score_bad = risk_service_v2._score_default_rate(0.20)  # 100
        payment_behavior_bad = 100 - (delay_score_bad * 0.6 + default_score_bad * 0.4)

        assert payment_behavior_good == 100.0
        assert payment_behavior_bad == 0.0


# ========================= Singleton Tests =========================


class TestServiceSingleton:
    """Tests for singleton service instance."""

    def test_get_risk_scoring_service_returns_instance(self):
        """get_risk_scoring_service sollte Service-Instanz liefern."""
        service = get_risk_scoring_service()
        assert isinstance(service, RiskScoringService)

    def test_singleton_returns_same_instance(self):
        """Wiederholte Aufrufe sollten dieselbe Instanz liefern."""
        service1 = get_risk_scoring_service()
        service2 = get_risk_scoring_service()
        assert service1 is service2

    def test_reset_singleton(self):
        """reset_risk_scoring_service sollte Singleton zuruecksetzen."""
        service1 = get_risk_scoring_service()
        reset_risk_scoring_service()
        service2 = get_risk_scoring_service()

        # Neue Instanz nach Reset
        assert service1 is not service2

    def test_default_uses_v2(self):
        """Default sollte V2 verwenden."""
        service = get_risk_scoring_service()
        assert service.version == "2.0"


# ========================= Version Tests =========================


class TestServiceVersioning:
    """Tests for service version handling."""

    def test_v1_version_string(self, risk_service_v1: RiskScoringService):
        """V1 Service sollte Version 1.0 haben."""
        assert risk_service_v1.version == "1.0"

    def test_v2_version_string(self, risk_service_v2: RiskScoringService):
        """V2 Service sollte Version 2.0 haben."""
        assert risk_service_v2.version == "2.0"

    def test_v1_uses_v1_weights(self, risk_service_v1: RiskScoringService):
        """V1 Service sollte V1 Gewichte verwenden."""
        assert risk_service_v1._weights == RISK_WEIGHTS_V1

    def test_v2_uses_v2_weights(self, risk_service_v2: RiskScoringService):
        """V2 Service sollte V2 Gewichte verwenden."""
        assert risk_service_v2._weights == RISK_WEIGHTS_V2


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests for edge cases and boundary values."""

    def test_score_clamping_upper_bound(self, risk_service_v2: RiskScoringService):
        """Score sollte bei 100 gedeckelt sein."""
        delay_score = risk_service_v2._score_payment_delay(1000.0)
        assert delay_score == 100.0

    def test_score_clamping_lower_bound(self, risk_service_v2: RiskScoringService):
        """Score sollte bei 0 nicht negativ werden."""
        delay_score = risk_service_v2._score_payment_delay(-100.0)
        assert delay_score == 0.0

    def test_factors_with_zero_invoices(self, empty_factors: RiskFactors):
        """Faktoren mit null Rechnungen sollten keine Division by Zero verursachen."""
        result = empty_factors.to_dict()

        assert result["total_invoices"] == 0
        assert result["default_rate"] == 0.0

    def test_boundary_value_30_days(self, risk_service_v2: RiskScoringService):
        """Grenzwert 30 Tage sollte exakt 100 ergeben."""
        assert risk_service_v2._score_payment_delay(29.99) < 100.0
        assert risk_service_v2._score_payment_delay(30.0) == 100.0
        assert risk_service_v2._score_payment_delay(30.01) == 100.0

    def test_boundary_value_20_percent_default(self, risk_service_v2: RiskScoringService):
        """Grenzwert 20% Ausfallrate sollte exakt 100 ergeben."""
        assert risk_service_v2._score_default_rate(0.199) < 100.0
        assert risk_service_v2._score_default_rate(0.20) == 100.0
        assert risk_service_v2._score_default_rate(0.201) == 100.0


# ========================= RiskScoreDetailedResponse Tests =========================


class TestRiskScoreDetailedResponse:
    """Tests for the detailed response model."""

    def test_to_dict_serialization(self):
        """to_dict sollte JSON-serialisierbares Dict liefern."""
        entity_id = uuid4()
        response = RiskScoreDetailedResponse(
            entity_id=entity_id,
            overall_score=65,
            risk_level=RiskLevel.HIGH,
            factors={
                "payment_delay": RiskFactor(
                    name="payment_delay",
                    value=15.0,
                    score=50.0,
                    weight=0.20,
                    weighted_score=10.0,
                    description="Durchschnittliche Zahlungsverzoegerung: 15.0 Tage",
                )
            },
            trend=TrendDirection.WORSENING,
            trend_score_adjustment=5,
            last_calculated=datetime.now(timezone.utc),
            recommendations=["Empfehlung 1", "Empfehlung 2"],
            payment_behavior_score=70.0,
            version="2.0",
        )

        result = response.to_dict()

        assert result["entity_id"] == str(entity_id)
        assert result["overall_score"] == 65
        assert result["risk_level"] == "HIGH"
        assert result["trend"] == "WORSENING"
        assert result["version"] == "2.0"
        assert len(result["recommendations"]) == 2
        assert "payment_delay" in result["factors"]


# ========================= Async Tests (Mocked) =========================


@pytest.mark.asyncio
class TestAsyncMethods:
    """Tests for async service methods with mocked database."""

    async def test_calculate_risk_score_entity_not_found(
        self,
        risk_service_v2: RiskScoringService,
        mock_db_session: AsyncMock,
        sample_entity_id: UUID,
    ):
        """Bei nicht gefundener Entity sollte leere Faktoren zurueckgegeben werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await risk_service_v2._collect_factors(mock_db_session, sample_entity_id)

        assert isinstance(result, RiskFactors)
        assert result.payment_delay_days == 0.0
        assert result.total_invoices == 0

    async def test_update_entity_risk_score_entity_not_found(
        self,
        risk_service_v2: RiskScoringService,
        mock_db_session: AsyncMock,
        sample_entity_id: UUID,
    ):
        """Update bei nicht gefundener Entity sollte None zurueckgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        result = await risk_service_v2.update_entity_risk_score(
            mock_db_session, sample_entity_id
        )

        assert result is None

    async def test_update_all_risk_scores_with_limit(
        self,
        risk_service_v2: RiskScoringService,
        mock_db_session: AsyncMock,
    ):
        """Batch-Update sollte Limit respektieren."""
        entity_ids = [uuid4(), uuid4(), uuid4()]
        mock_fetch_result = Mock()
        mock_fetch_result.fetchall.return_value = [(eid,) for eid in entity_ids]

        mock_db_session.execute.return_value = mock_fetch_result

        with patch.object(
            risk_service_v2,
            "update_entity_risk_score",
            new_callable=AsyncMock,
        ) as mock_update:
            mock_update.return_value = Mock()

            updated_count = await risk_service_v2.update_all_risk_scores(
                mock_db_session, limit=10
            )

            assert mock_update.call_count == 3
            assert updated_count == 3
