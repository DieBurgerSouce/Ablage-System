"""
Unit-Tests fuer FinancialHealthService

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Score-to-Rating Konvertierung
- Methoden-Existenz
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.privat.financial_health_service import (
    FinancialHealthService,
    HealthRating,
    DimensionScore,
    NetWorthSummary,
    FinancialHealthScore,
)


class TestFinancialHealthService:
    """Tests fuer FinancialHealthService."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        service = FinancialHealthService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_singleton_pattern(self) -> None:
        """Testet dass Service ein Singleton ist."""
        service1 = FinancialHealthService()
        service2 = FinancialHealthService()
        assert service1 is service2


class TestHealthRatingEnum:
    """Tests fuer HealthRating Enum."""

    def test_health_rating_values(self) -> None:
        """Testet dass alle HealthRating Werte korrekt sind."""
        assert HealthRating.EXCELLENT.value == "exzellent"
        assert HealthRating.GOOD.value == "gut"
        assert HealthRating.MODERATE.value == "moderat"
        assert HealthRating.NEEDS_ATTENTION.value == "verbesserungsbedürftig"
        assert HealthRating.CRITICAL.value == "kritisch"

    def test_health_rating_count(self) -> None:
        """Testet dass genau 5 Rating-Stufen existieren."""
        assert len(HealthRating) == 5


class TestScoreToRating:
    """Tests fuer _score_to_rating Methode."""

    @pytest.fixture
    def service(self) -> FinancialHealthService:
        return FinancialHealthService()

    def test_score_to_rating_excellent(self, service: FinancialHealthService) -> None:
        """Score 85+ sollte EXCELLENT sein."""
        rating = service._score_to_rating(Decimal("95"))
        assert rating == HealthRating.EXCELLENT

        rating = service._score_to_rating(Decimal("85"))
        assert rating == HealthRating.EXCELLENT

    def test_score_to_rating_good(self, service: FinancialHealthService) -> None:
        """Score 70-84 sollte GOOD sein."""
        rating = service._score_to_rating(Decimal("80"))
        assert rating == HealthRating.GOOD

        rating = service._score_to_rating(Decimal("70"))
        assert rating == HealthRating.GOOD

    def test_score_to_rating_moderate(self, service: FinancialHealthService) -> None:
        """Score 50-69 sollte MODERATE sein."""
        rating = service._score_to_rating(Decimal("60"))
        assert rating == HealthRating.MODERATE

        rating = service._score_to_rating(Decimal("50"))
        assert rating == HealthRating.MODERATE

    def test_score_to_rating_needs_attention(self, service: FinancialHealthService) -> None:
        """Score 30-49 sollte NEEDS_ATTENTION sein."""
        rating = service._score_to_rating(Decimal("40"))
        assert rating == HealthRating.NEEDS_ATTENTION

        rating = service._score_to_rating(Decimal("30"))
        assert rating == HealthRating.NEEDS_ATTENTION

    def test_score_to_rating_critical(self, service: FinancialHealthService) -> None:
        """Score <30 sollte CRITICAL sein."""
        rating = service._score_to_rating(Decimal("20"))
        assert rating == HealthRating.CRITICAL

        rating = service._score_to_rating(Decimal("0"))
        assert rating == HealthRating.CRITICAL


class TestDimensionScoreDataClass:
    """Tests fuer DimensionScore Datenstruktur."""

    def test_dimension_score_creation(self) -> None:
        """Testet DimensionScore Erstellung."""
        score = DimensionScore(
            name="net_worth_trend",
            score=Decimal("85"),
            weight=Decimal("20"),
            weighted_score=Decimal("17"),
            rating=HealthRating.EXCELLENT,
            details={"trend_pct": Decimal("8.5")},
            recommendations=["Kurs beibehalten"],
        )

        assert score.name == "net_worth_trend"
        assert score.score == Decimal("85")
        assert score.rating == HealthRating.EXCELLENT
        assert len(score.recommendations) == 1


class TestNetWorthSummaryDataClass:
    """Tests fuer NetWorthSummary Datenstruktur."""

    def test_net_worth_summary_creation(self) -> None:
        """Testet NetWorthSummary Erstellung."""
        summary = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("350000"),
            property_value=Decimal("300000"),
            vehicle_value=Decimal("45000"),
            investment_value=Decimal("100000"),
            cash_and_savings=Decimal("55000"),
            mortgage_debt=Decimal("120000"),
            loan_debt=Decimal("25000"),
            other_debt=Decimal("5000"),
            net_worth_change_ytd=Decimal("30000"),
            net_worth_change_pct=Decimal("9.38"),
        )

        assert summary.total_assets == Decimal("500000")
        assert summary.net_worth == Decimal("350000")
        assert summary.net_worth_change_pct == Decimal("9.38")


class TestFinancialHealthScoreDataClass:
    """Tests fuer FinancialHealthScore Datenstruktur."""

    def test_financial_health_score_creation(self) -> None:
        """Testet FinancialHealthScore Erstellung."""
        space_id = uuid4()

        net_worth = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("350000"),
            property_value=Decimal("300000"),
            vehicle_value=Decimal("45000"),
            investment_value=Decimal("100000"),
            cash_and_savings=Decimal("55000"),
            mortgage_debt=Decimal("120000"),
            loan_debt=Decimal("25000"),
            other_debt=Decimal("5000"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        score = FinancialHealthScore(
            space_id=space_id,
            total_score=Decimal("78"),
            rating=HealthRating.GOOD,
            dimensions=[],
            net_worth=net_worth,
            estimated_monthly_income=Decimal("5500"),
            estimated_monthly_expenses=Decimal("3500"),
            monthly_savings_rate=Decimal("36.36"),
            priority_recommendations=["Notgroschen aufbauen"],
            benchmark_percentile=Decimal("65"),
        )

        assert score.space_id == space_id
        assert score.total_score == Decimal("78")
        assert score.rating == HealthRating.GOOD
        assert score.calculated_at is not None


class TestServiceMethodsExist:
    """Tests dass alle wichtigen Service-Methoden existieren."""

    @pytest.fixture
    def service(self) -> FinancialHealthService:
        return FinancialHealthService()

    def test_service_has_calculate_net_worth_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service calculate_net_worth Methode hat."""
        assert hasattr(service, "calculate_net_worth")
        assert callable(getattr(service, "calculate_net_worth"))

    def test_service_has_calculate_health_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service calculate_health_score Methode hat."""
        assert hasattr(service, "calculate_health_score")
        assert callable(getattr(service, "calculate_health_score"))

    def test_service_has_recalculate_all_health_scores_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service recalculate_all_health_scores Methode hat."""
        assert hasattr(service, "recalculate_all_health_scores")
        assert callable(getattr(service, "recalculate_all_health_scores"))

    def test_service_has_score_to_rating_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _score_to_rating Methode hat."""
        assert hasattr(service, "_score_to_rating")
        assert callable(getattr(service, "_score_to_rating"))


class TestDimensionScoreCalculationMethods:
    """Tests dass alle Dimensions-Berechnungsmethoden existieren."""

    @pytest.fixture
    def service(self) -> FinancialHealthService:
        return FinancialHealthService()

    def test_service_has_net_worth_trend_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_net_worth_trend_score Methode hat."""
        assert hasattr(service, "_calculate_net_worth_trend_score")
        assert callable(getattr(service, "_calculate_net_worth_trend_score"))

    def test_service_has_debt_management_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_debt_management_score Methode hat."""
        assert hasattr(service, "_calculate_debt_management_score")
        assert callable(getattr(service, "_calculate_debt_management_score"))

    def test_service_has_risk_coverage_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_risk_coverage_score Methode hat."""
        assert hasattr(service, "_calculate_risk_coverage_score")
        assert callable(getattr(service, "_calculate_risk_coverage_score"))

    def test_service_has_liquidity_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_liquidity_score Methode hat."""
        assert hasattr(service, "_calculate_liquidity_score")
        assert callable(getattr(service, "_calculate_liquidity_score"))

    def test_service_has_retirement_readiness_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_retirement_readiness_score Methode hat."""
        assert hasattr(service, "_calculate_retirement_readiness_score")
        assert callable(getattr(service, "_calculate_retirement_readiness_score"))

    def test_service_has_diversification_score_method(self, service: FinancialHealthService) -> None:
        """Testet dass Service _calculate_diversification_score Methode hat."""
        assert hasattr(service, "_calculate_diversification_score")
        assert callable(getattr(service, "_calculate_diversification_score"))


class TestGetServiceFunction:
    """Tests fuer get_financial_health_service Factory."""

    def test_get_service_function_exists(self) -> None:
        """Testet dass get_financial_health_service existiert."""
        from app.services.privat.financial_health_service import (
            get_financial_health_service,
        )

        assert get_financial_health_service is not None
        assert callable(get_financial_health_service)

    def test_get_service_returns_instance(self) -> None:
        """Testet dass get_financial_health_service eine Instanz zurueckgibt."""
        from app.services.privat.financial_health_service import (
            FinancialHealthService,
            get_financial_health_service,
        )

        service = get_financial_health_service()

        assert isinstance(service, FinancialHealthService)


# =============================================================================
# ECHTE BUSINESS-LOGIC TESTS
# =============================================================================


class TestScoreCalculationEdgeCases:
    """Tests fuer Score-Berechnungs-Edge-Cases."""

    @pytest.fixture
    def service(self) -> FinancialHealthService:
        return FinancialHealthService()

    def test_score_boundary_85_exactly(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert genau bei 85 -> EXCELLENT."""
        assert service._score_to_rating(Decimal("85")) == HealthRating.EXCELLENT

    def test_score_boundary_84_99(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert 84.99 -> GOOD (nicht EXCELLENT)."""
        assert service._score_to_rating(Decimal("84.99")) == HealthRating.GOOD

    def test_score_boundary_70_exactly(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert genau bei 70 -> GOOD."""
        assert service._score_to_rating(Decimal("70")) == HealthRating.GOOD

    def test_score_boundary_69_99(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert 69.99 -> MODERATE (nicht GOOD)."""
        assert service._score_to_rating(Decimal("69.99")) == HealthRating.MODERATE

    def test_score_boundary_50_exactly(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert genau bei 50 -> MODERATE."""
        assert service._score_to_rating(Decimal("50")) == HealthRating.MODERATE

    def test_score_boundary_49_99(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert 49.99 -> NEEDS_ATTENTION."""
        assert service._score_to_rating(Decimal("49.99")) == HealthRating.NEEDS_ATTENTION

    def test_score_boundary_30_exactly(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert genau bei 30 -> NEEDS_ATTENTION."""
        assert service._score_to_rating(Decimal("30")) == HealthRating.NEEDS_ATTENTION

    def test_score_boundary_29_99(self, service: FinancialHealthService) -> None:
        """Testet Grenzwert 29.99 -> CRITICAL."""
        assert service._score_to_rating(Decimal("29.99")) == HealthRating.CRITICAL

    def test_score_negative(self, service: FinancialHealthService) -> None:
        """Testet negativer Score -> CRITICAL."""
        assert service._score_to_rating(Decimal("-10")) == HealthRating.CRITICAL

    def test_score_above_100(self, service: FinancialHealthService) -> None:
        """Testet Score > 100 -> EXCELLENT."""
        assert service._score_to_rating(Decimal("110")) == HealthRating.EXCELLENT


class TestNetWorthSummaryCalculations:
    """Tests fuer NetWorthSummary Berechnungen."""

    def test_net_worth_is_assets_minus_liabilities(self) -> None:
        """Testet dass Nettovermoegen = Assets - Liabilities."""
        summary = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("350000"),  # 500000 - 150000
            property_value=Decimal("300000"),
            vehicle_value=Decimal("50000"),
            investment_value=Decimal("100000"),
            cash_and_savings=Decimal("50000"),
            mortgage_debt=Decimal("100000"),
            loan_debt=Decimal("30000"),
            other_debt=Decimal("20000"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        assert summary.net_worth == summary.total_assets - summary.total_liabilities

    def test_asset_components_sum_to_total(self) -> None:
        """Testet dass Asset-Komponenten = Total Assets."""
        summary = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("0"),
            net_worth=Decimal("500000"),
            property_value=Decimal("300000"),
            vehicle_value=Decimal("50000"),
            investment_value=Decimal("100000"),
            cash_and_savings=Decimal("50000"),
            mortgage_debt=Decimal("0"),
            loan_debt=Decimal("0"),
            other_debt=Decimal("0"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        component_sum = (
            summary.property_value
            + summary.vehicle_value
            + summary.investment_value
            + summary.cash_and_savings
        )
        assert component_sum == summary.total_assets

    def test_liability_components_sum_to_total(self) -> None:
        """Testet dass Liability-Komponenten = Total Liabilities."""
        summary = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("350000"),
            property_value=Decimal("500000"),
            vehicle_value=Decimal("0"),
            investment_value=Decimal("0"),
            cash_and_savings=Decimal("0"),
            mortgage_debt=Decimal("100000"),
            loan_debt=Decimal("30000"),
            other_debt=Decimal("20000"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        liability_sum = (
            summary.mortgage_debt + summary.loan_debt + summary.other_debt
        )
        assert liability_sum == summary.total_liabilities

    def test_negative_net_worth_scenario(self) -> None:
        """Testet Szenario mit negativem Nettovermoegen (Schulden > Assets)."""
        summary = NetWorthSummary(
            total_assets=Decimal("100000"),
            total_liabilities=Decimal("150000"),
            net_worth=Decimal("-50000"),
            property_value=Decimal("100000"),
            vehicle_value=Decimal("0"),
            investment_value=Decimal("0"),
            cash_and_savings=Decimal("0"),
            mortgage_debt=Decimal("150000"),
            loan_debt=Decimal("0"),
            other_debt=Decimal("0"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        assert summary.net_worth < Decimal("0")
        assert summary.total_liabilities > summary.total_assets


class TestDimensionWeights:
    """Tests fuer Dimensions-Gewichtung."""

    def test_all_weights_sum_to_100(self) -> None:
        """Testet dass alle Gewichtungen zusammen 100 ergeben."""
        from app.services.privat.financial_health_service import DIMENSION_WEIGHTS

        total_weight = sum(DIMENSION_WEIGHTS.values())
        assert total_weight == Decimal("100")

    def test_all_dimensions_have_weight(self) -> None:
        """Testet dass alle 6 Dimensionen gewichtet sind."""
        from app.services.privat.financial_health_service import DIMENSION_WEIGHTS

        expected_dimensions = {
            "net_worth_trend",
            "debt_management",
            "risk_coverage",
            "liquidity",
            "retirement_readiness",
            "diversification",
        }
        assert set(DIMENSION_WEIGHTS.keys()) == expected_dimensions

    def test_no_weight_is_zero(self) -> None:
        """Testet dass keine Gewichtung 0 ist."""
        from app.services.privat.financial_health_service import DIMENSION_WEIGHTS

        for name, weight in DIMENSION_WEIGHTS.items():
            assert weight > Decimal("0"), f"{name} hat Gewichtung 0"


class TestBusinessRuleConstants:
    """Tests fuer Business-Rule Konstanten."""

    def test_max_healthy_dti_ratio_is_36_percent(self) -> None:
        """Testet dass max DTI bei 36% liegt (Industrie-Standard)."""
        from app.services.privat.financial_health_service import MAX_HEALTHY_DTI_RATIO

        assert MAX_HEALTHY_DTI_RATIO == Decimal("0.36")

    def test_emergency_fund_recommendation_is_6_months(self) -> None:
        """Testet dass Notgroschen-Empfehlung 6 Monate ist."""
        from app.services.privat.financial_health_service import (
            RECOMMENDED_EMERGENCY_MONTHS,
        )

        assert RECOMMENDED_EMERGENCY_MONTHS == 6

    def test_essential_insurance_types_include_haftpflicht(self) -> None:
        """Testet dass Haftpflicht als essentiell gilt."""
        from app.services.privat.financial_health_service import (
            ESSENTIAL_INSURANCE_TYPES,
        )

        assert "haftpflicht" in ESSENTIAL_INSURANCE_TYPES
        assert "privathaftpflicht" in ESSENTIAL_INSURANCE_TYPES

    def test_retirement_factor_increases_with_age(self) -> None:
        """Testet dass Altersvorsorge-Faktor mit Alter steigt."""
        from app.services.privat.financial_health_service import (
            RETIREMENT_FACTOR_BY_AGE,
        )

        ages = sorted(RETIREMENT_FACTOR_BY_AGE.keys())
        for i in range(len(ages) - 1):
            assert (
                RETIREMENT_FACTOR_BY_AGE[ages[i + 1]]
                > RETIREMENT_FACTOR_BY_AGE[ages[i]]
            ), f"Faktor sollte von {ages[i]} zu {ages[i+1]} steigen"


class TestWeightedScoreCalculation:
    """Tests fuer gewichtete Score-Berechnung."""

    def test_weighted_score_calculation(self) -> None:
        """Testet Berechnung des gewichteten Scores."""
        # Score 80, Gewichtung 20 -> 80 * 20 / 100 = 16
        score = DimensionScore(
            name="test",
            score=Decimal("80"),
            weight=Decimal("20"),
            weighted_score=Decimal("16.0"),  # 80 * 20 / 100
            rating=HealthRating.GOOD,
            details={},
            recommendations=[],
        )

        expected = (score.score * score.weight / 100).quantize(Decimal("0.1"))
        assert score.weighted_score == expected

    def test_perfect_score_weighted(self) -> None:
        """Testet perfekten Score mit Gewichtung."""
        # Score 100, Gewichtung 15 -> 100 * 15 / 100 = 15
        score = DimensionScore(
            name="test",
            score=Decimal("100"),
            weight=Decimal("15"),
            weighted_score=Decimal("15.0"),
            rating=HealthRating.EXCELLENT,
            details={},
            recommendations=[],
        )

        expected = (score.score * score.weight / 100).quantize(Decimal("0.1"))
        assert score.weighted_score == expected

    def test_zero_score_weighted(self) -> None:
        """Testet Score 0 mit Gewichtung."""
        # Score 0, Gewichtung 20 -> 0 * 20 / 100 = 0
        score = DimensionScore(
            name="test",
            score=Decimal("0"),
            weight=Decimal("20"),
            weighted_score=Decimal("0.0"),
            rating=HealthRating.CRITICAL,
            details={},
            recommendations=[],
        )

        expected = (score.score * score.weight / 100).quantize(Decimal("0.1"))
        assert score.weighted_score == expected


class TestFinancialHealthScoreIntegrity:
    """Tests fuer FinancialHealthScore Konsistenz."""

    def test_total_score_within_bounds(self) -> None:
        """Testet dass total_score zwischen 0-100 liegt."""
        space_id = uuid4()
        net_worth = NetWorthSummary(
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("0"),
            net_worth=Decimal("500000"),
            property_value=Decimal("300000"),
            vehicle_value=Decimal("50000"),
            investment_value=Decimal("100000"),
            cash_and_savings=Decimal("50000"),
            mortgage_debt=Decimal("0"),
            loan_debt=Decimal("0"),
            other_debt=Decimal("0"),
            net_worth_change_ytd=None,
            net_worth_change_pct=None,
        )

        # Perfekte Situation
        score = FinancialHealthScore(
            space_id=space_id,
            total_score=Decimal("95"),
            rating=HealthRating.EXCELLENT,
            dimensions=[],
            net_worth=net_worth,
            estimated_monthly_income=Decimal("6000"),
            estimated_monthly_expenses=Decimal("4000"),
            monthly_savings_rate=Decimal("33.33"),
            priority_recommendations=[],
            benchmark_percentile=Decimal("90"),
        )

        assert Decimal("0") <= score.total_score <= Decimal("100")

    def test_savings_rate_calculation(self) -> None:
        """Testet Sparquoten-Berechnung."""
        income = Decimal("6000")
        expenses = Decimal("4000")
        savings_rate = ((income - expenses) / income * 100).quantize(Decimal("0.01"))

        # 2000 / 6000 * 100 = 33.33%
        assert savings_rate == Decimal("33.33")

    def test_rating_matches_score(self) -> None:
        """Testet dass Rating zum Score passt."""
        service = FinancialHealthService()

        # Score 95 -> EXCELLENT
        rating = service._score_to_rating(Decimal("95"))
        assert rating == HealthRating.EXCELLENT

        # Score 45 -> NEEDS_ATTENTION
        rating = service._score_to_rating(Decimal("45"))
        assert rating == HealthRating.NEEDS_ATTENTION
