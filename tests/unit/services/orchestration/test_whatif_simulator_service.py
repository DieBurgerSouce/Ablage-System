# -*- coding: utf-8 -*-
"""
Unit Tests fuer WhatIfSimulatorService.

Testet:
- Singleton-Verhalten
- Szenario-Simulation
- KPI-Projektionen
- Zeitleisten-Generierung
- Szenario-Vergleich
- Template-Berechnungen

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.whatif_simulator_service import (
    WhatIfSimulatorService,
    ScenarioType,
    TimeHorizon,
    ImpactSeverity,
    ScenarioInput,
    KPIProjection,
    TimelinePoint,
    ScenarioResult,
    ComparisonResult,
    ScenarioTemplates,
    get_whatif_simulator,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    WhatIfSimulatorService._instance = None
    yield
    WhatIfSimulatorService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return WhatIfSimulatorService()


@pytest.fixture
def sample_kpis():
    """Standard-KPIs fuer Tests."""
    return {
        "health_score": 70.0,
        "dti_ratio": 35.0,
        "savings_rate": 12.0,
        "emergency_fund_months": 4.5,
        "monthly_income": 5000.0,
        "monthly_expenses": 3500.0,
        "total_debt": 150000.0,
    }


@pytest.fixture
def sample_scenario_input():
    """Erstellt eine Beispiel-Szenario-Eingabe."""
    return ScenarioInput(
        scenario_type=ScenarioType.EXTRA_SAVINGS,
        amount=Decimal("300"),
        duration_months=12,
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = WhatIfSimulatorService()
        instance2 = WhatIfSimulatorService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_whatif_simulator()
        instance2 = get_whatif_simulator()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_service):
        """Initialisierung erfolgt nur einmal."""
        instance = WhatIfSimulatorService()
        original_cache = instance._simulation_cache

        instance2 = WhatIfSimulatorService()

        assert instance2._simulation_cache is original_cache


# =============================================================================
# Enums Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_scenario_type_values(self):
        """ScenarioType hat erwartete Werte."""
        assert ScenarioType.EXTRA_SAVINGS.value == "extra_savings"
        assert ScenarioType.EXTRA_PAYMENT.value == "extra_payment"
        assert ScenarioType.INCOME_CHANGE.value == "income_change"
        assert ScenarioType.INTEREST_RATE_CHANGE.value == "interest_rate_change"
        assert ScenarioType.LOAN_REFINANCE.value == "loan_refinance"
        assert ScenarioType.CUSTOM.value == "custom"

    def test_time_horizon_values(self):
        """TimeHorizon hat erwartete Werte."""
        assert TimeHorizon.IMMEDIATE.value == "immediate"
        assert TimeHorizon.THREE_MONTHS.value == "3_months"
        assert TimeHorizon.SIX_MONTHS.value == "6_months"
        assert TimeHorizon.ONE_YEAR.value == "1_year"
        assert TimeHorizon.TWO_YEARS.value == "2_years"

    def test_impact_severity_values(self):
        """ImpactSeverity hat erwartete Werte."""
        assert ImpactSeverity.VERY_POSITIVE.value == "very_positive"
        assert ImpactSeverity.POSITIVE.value == "positive"
        assert ImpactSeverity.NEUTRAL.value == "neutral"
        assert ImpactSeverity.NEGATIVE.value == "negative"
        assert ImpactSeverity.VERY_NEGATIVE.value == "very_negative"


# =============================================================================
# ScenarioInput Tests
# =============================================================================

class TestScenarioInput:
    """Tests fuer ScenarioInput Dataclass."""

    def test_defaults(self):
        """ScenarioInput hat sinnvolle Defaults."""
        scenario = ScenarioInput(scenario_type=ScenarioType.EXTRA_SAVINGS)

        assert scenario.amount == Decimal("0")
        assert scenario.percentage == 0.0
        assert scenario.target_entity_id is None
        assert scenario.duration_months == 12
        assert scenario.additional_params == {}

    def test_with_all_params(self):
        """ScenarioInput mit allen Parametern."""
        entity_id = uuid4()
        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_PAYMENT,
            amount=Decimal("5000"),
            percentage=10.0,
            target_entity_id=entity_id,
            target_entity_type="loan",
            duration_months=24,
            additional_params={"loan_data": {"balance": 100000}},
        )

        assert scenario.scenario_type == ScenarioType.EXTRA_PAYMENT
        assert scenario.amount == Decimal("5000")
        assert scenario.target_entity_id == entity_id
        assert scenario.duration_months == 24


# =============================================================================
# KPIProjection Tests
# =============================================================================

class TestKPIProjection:
    """Tests fuer KPIProjection Dataclass."""

    def test_to_dict(self):
        """to_dict gibt korrektes Dictionary zurueck."""
        projection = KPIProjection(
            kpi_name="Sparquote",
            current_value=12.0,
            projected_value=18.0,
            change_absolute=6.0,
            change_percentage=50.0,
            impact_severity=ImpactSeverity.VERY_POSITIVE,
            threshold_warning=None,
        )

        result = projection.to_dict()

        assert result["kpi_name"] == "Sparquote"
        assert result["current_value"] == 12.0
        assert result["projected_value"] == 18.0
        assert result["change_absolute"] == 6.0
        assert result["change_percentage"] == 50.0
        assert result["impact_severity"] == "very_positive"
        assert result["threshold_warning"] is None

    def test_with_warning(self):
        """KPIProjection mit Schwellenwert-Warnung."""
        projection = KPIProjection(
            kpi_name="DTI Ratio",
            current_value=35.0,
            projected_value=45.0,
            change_absolute=10.0,
            change_percentage=28.6,
            impact_severity=ImpactSeverity.VERY_NEGATIVE,
            threshold_warning="Kritisch: DTI ueber 40%",
        )

        result = projection.to_dict()

        assert result["threshold_warning"] == "Kritisch: DTI ueber 40%"


# =============================================================================
# TimelinePoint Tests
# =============================================================================

class TestTimelinePoint:
    """Tests fuer TimelinePoint Dataclass."""

    def test_to_dict(self):
        """to_dict gibt korrektes Dictionary zurueck."""
        now = datetime.now(timezone.utc)
        point = TimelinePoint(
            month=6,
            date=now,
            health_score=75.0,
            key_kpis={"dti_ratio": 30.0, "savings_rate": 15.0},
            events=["Ziel erreicht"],
        )

        result = point.to_dict()

        assert result["month"] == 6
        assert result["health_score"] == 75.0
        assert "dti_ratio" in result["key_kpis"]
        assert "Ziel erreicht" in result["events"]

    def test_default_events(self):
        """TimelinePoint hat leere Events als Default."""
        point = TimelinePoint(
            month=0,
            date=datetime.now(timezone.utc),
            health_score=70.0,
            key_kpis={},
        )

        assert point.events == []


# =============================================================================
# ScenarioResult Tests
# =============================================================================

class TestScenarioResult:
    """Tests fuer ScenarioResult Dataclass."""

    def test_defaults(self):
        """ScenarioResult hat sinnvolle Defaults."""
        result = ScenarioResult(
            scenario_id=uuid4(),
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            scenario_description="Test",
            current_health_score=70.0,
            current_kpis={},
            projected_health_score=75.0,
            projected_kpis=[],
            health_score_change=5.0,
            health_score_change_percentage=7.14,
            overall_impact_severity=ImpactSeverity.POSITIVE,
            timeline=[],
            total_cost=Decimal("0"),
            total_benefit=Decimal("1000"),
            net_benefit=Decimal("1000"),
        )

        assert result.risks == []
        assert result.warnings == []
        assert result.opportunities == []
        assert result.confidence_percentage == 85.0
        assert result.calculated_at is not None  # Feld heisst calculated_at, nicht created_at

    def test_to_dict(self):
        """to_dict gibt korrektes Dictionary zurueck."""
        scenario_id = uuid4()
        result = ScenarioResult(
            scenario_id=scenario_id,
            scenario_type=ScenarioType.EXTRA_PAYMENT,
            scenario_description="5000 EUR Sondertilgung",
            current_health_score=70.0,
            current_kpis={"dti_ratio": 35.0},
            projected_health_score=78.0,
            projected_kpis=[],
            health_score_change=8.0,
            health_score_change_percentage=11.4,
            overall_impact_severity=ImpactSeverity.POSITIVE,
            timeline=[],
            total_cost=Decimal("5000"),
            total_benefit=Decimal("8000"),
            net_benefit=Decimal("3000"),
            payback_months=24,
            risks=["Liquiditaet reduziert"],
            opportunities=["DTI sinkt"],
        )

        d = result.to_dict()

        assert d["scenario_id"] == str(scenario_id)
        assert d["scenario_type"] == "extra_payment"
        assert d["health_score_change"] == 8.0
        assert d["net_benefit"] == 3000.0
        assert d["payback_months"] == 24
        assert "Liquiditaet reduziert" in d["risks"]


# =============================================================================
# ComparisonResult Tests
# =============================================================================

class TestComparisonResult:
    """Tests fuer ComparisonResult Dataclass."""

    def test_to_dict(self):
        """to_dict gibt korrektes Dictionary zurueck."""
        comparison_id = uuid4()
        scenario_id = uuid4()

        mock_scenario = ScenarioResult(
            scenario_id=scenario_id,
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            scenario_description="Test",
            current_health_score=70.0,
            current_kpis={},
            projected_health_score=75.0,
            projected_kpis=[],
            health_score_change=5.0,
            health_score_change_percentage=7.14,
            overall_impact_severity=ImpactSeverity.POSITIVE,
            timeline=[],
            total_cost=Decimal("0"),
            total_benefit=Decimal("1000"),
            net_benefit=Decimal("1000"),
        )

        comparison = ComparisonResult(
            comparison_id=comparison_id,
            scenarios=[mock_scenario],
            best_scenario_id=scenario_id,
            best_scenario_reason="Hoechster Net-Benefit",
            ranking=[{"rank": 1, "scenario_id": str(scenario_id)}],
            recommendation="Test Empfehlung",
        )

        result = comparison.to_dict()

        assert result["comparison_id"] == str(comparison_id)
        assert len(result["scenarios"]) == 1
        assert result["best_scenario_id"] == str(scenario_id)
        assert result["recommendation"] == "Test Empfehlung"


# =============================================================================
# ScenarioTemplates Tests
# =============================================================================

class TestScenarioTemplates:
    """Tests fuer ScenarioTemplates Berechnungen."""

    def test_extra_savings_impact_basic(self, sample_kpis):
        """Extra Savings Impact wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_extra_savings_impact(
            sample_kpis,
            monthly_amount=Decimal("300"),
            duration_months=12,
        )

        assert "new_kpis" in result
        assert "changes" in result
        assert "total_benefit" in result
        assert "opportunities" in result

        # Sparquote sollte steigen
        assert result["new_kpis"]["savings_rate"] > sample_kpis["savings_rate"]
        # Notgroschen sollte steigen
        assert result["new_kpis"]["emergency_fund_months"] > sample_kpis["emergency_fund_months"]
        # Health Score sollte steigen
        assert result["new_kpis"]["health_score"] > sample_kpis["health_score"]

    def test_extra_savings_with_zero_income(self):
        """Extra Savings bei Null-Einkommen."""
        kpis = {"monthly_income": 0, "savings_rate": 10.0, "emergency_fund_months": 3.0}

        result = ScenarioTemplates.calculate_extra_savings_impact(
            kpis,
            monthly_amount=Decimal("300"),
            duration_months=12,
        )

        # Sparquote bleibt unveraendert bei 0 Einkommen
        assert result["new_kpis"]["savings_rate"] == 10.0

    def test_extra_payment_impact(self, sample_kpis):
        """Extra Payment Impact wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_extra_payment_impact(
            sample_kpis,
            payment_amount=Decimal("5000"),
            target_loan_data={"balance": 100000, "interest_rate": 4.0, "remaining_years": 15},
        )

        # DTI sollte sinken
        assert result["new_kpis"]["dti_ratio"] < sample_kpis["dti_ratio"]
        # Schulden sollten sinken
        assert result["new_kpis"]["total_debt"] < sample_kpis["total_debt"]
        # Total Benefit (Zinsersparnis) sollte positiv sein
        assert result["total_benefit"] > 0
        # Cost ist die Zahlung
        assert result["total_cost"] == Decimal("5000")

    def test_extra_payment_large_amount_shows_risk(self, sample_kpis):
        """Grosse Sondertilgung zeigt Liquiditaetsrisiko."""
        result = ScenarioTemplates.calculate_extra_payment_impact(
            sample_kpis,
            payment_amount=Decimal("20000"),  # > 3x Monatseinkommen
        )

        assert len(result["risks"]) > 0
        assert "Liquiditaet" in result["risks"][0]

    def test_interest_rate_increase(self, sample_kpis):
        """Zinserhoehung wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_interest_rate_change_impact(
            sample_kpis,
            rate_change_percentage=2.0,  # +2%
        )

        # DTI sollte steigen
        assert result["new_kpis"]["dti_ratio"] > sample_kpis["dti_ratio"]
        # Health Score sollte sinken
        assert result["new_kpis"]["health_score"] < sample_kpis["health_score"]
        # Es sollten Risiken gelistet sein
        assert len(result["risks"]) > 0
        # Kosten steigen
        assert result["total_cost"] > 0

    def test_interest_rate_decrease(self, sample_kpis):
        """Zinssenkung wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_interest_rate_change_impact(
            sample_kpis,
            rate_change_percentage=-1.0,  # -1%
        )

        # DTI sollte sinken
        assert result["new_kpis"]["dti_ratio"] < sample_kpis["dti_ratio"]
        # Health Score sollte steigen
        assert result["new_kpis"]["health_score"] > sample_kpis["health_score"]
        # Es sollten Chancen gelistet sein
        assert len(result["opportunities"]) > 0
        # Benefit positiv
        assert result["total_benefit"] > 0

    def test_income_increase(self, sample_kpis):
        """Einkommenserhöhung wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_income_change_impact(
            sample_kpis,
            change_amount=Decimal("500"),
            is_increase=True,
        )

        # Einkommen sollte steigen
        assert result["new_kpis"]["monthly_income"] > sample_kpis["monthly_income"]
        # DTI sollte sinken
        assert result["new_kpis"]["dti_ratio"] < sample_kpis["dti_ratio"]
        # Health Score sollte steigen
        assert result["new_kpis"]["health_score"] > sample_kpis["health_score"]
        # Chancen vorhanden
        assert len(result["opportunities"]) > 0

    def test_income_decrease(self, sample_kpis):
        """Einkommensreduzierung wird korrekt berechnet."""
        result = ScenarioTemplates.calculate_income_change_impact(
            sample_kpis,
            change_amount=Decimal("1000"),
            is_increase=False,
        )

        # Einkommen sollte sinken
        assert result["new_kpis"]["monthly_income"] < sample_kpis["monthly_income"]
        # DTI sollte steigen
        assert result["new_kpis"]["dti_ratio"] > sample_kpis["dti_ratio"]
        # Health Score sollte sinken
        assert result["new_kpis"]["health_score"] < sample_kpis["health_score"]
        # Risiken vorhanden
        assert len(result["risks"]) > 0


# =============================================================================
# Service Tests - Simulation
# =============================================================================

class TestSimulation:
    """Tests fuer Szenario-Simulation."""

    @pytest.mark.asyncio
    async def test_simulate_extra_savings(self, service, sample_kpis, sample_scenario_input):
        """Extra Savings Szenario wird simuliert."""
        result = await service.simulate_scenario(
            sample_scenario_input,
            sample_kpis,
        )

        assert result is not None
        assert result.scenario_type == ScenarioType.EXTRA_SAVINGS
        assert result.current_health_score == 70.0
        assert result.projected_health_score >= result.current_health_score
        assert len(result.projected_kpis) > 0
        assert len(result.timeline) > 0

    @pytest.mark.asyncio
    async def test_simulate_extra_payment(self, service, sample_kpis):
        """Extra Payment Szenario wird simuliert."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_PAYMENT,
            amount=Decimal("5000"),
            duration_months=12,
        )

        result = await service.simulate_scenario(scenario, sample_kpis)

        assert result.scenario_type == ScenarioType.EXTRA_PAYMENT
        assert result.total_cost == Decimal("5000")

    @pytest.mark.asyncio
    async def test_simulate_interest_rate_change(self, service, sample_kpis):
        """Zinssatz-Szenario wird simuliert."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.INTEREST_RATE_CHANGE,
            percentage=2.0,
            duration_months=12,
        )

        result = await service.simulate_scenario(scenario, sample_kpis)

        assert result.scenario_type == ScenarioType.INTEREST_RATE_CHANGE
        # 2% Zinserhoehung verursacht nur geringe Health-Score-Aenderung (< 5%)
        # Bei -0.7% Aenderung ist NEUTRAL korrekt (Schwelle: -5% bis +5%)
        assert result.overall_impact_severity in [
            ImpactSeverity.NEUTRAL,
            ImpactSeverity.NEGATIVE,
            ImpactSeverity.VERY_NEGATIVE,
        ]

    @pytest.mark.asyncio
    async def test_simulate_income_change(self, service, sample_kpis):
        """Einkommens-Szenario wird simuliert."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.INCOME_CHANGE,
            amount=Decimal("500"),
            duration_months=12,
        )

        result = await service.simulate_scenario(scenario, sample_kpis)

        assert result.scenario_type == ScenarioType.INCOME_CHANGE

    @pytest.mark.asyncio
    async def test_simulation_caches_result(self, service, sample_kpis, sample_scenario_input):
        """Simulation wird gecached."""
        user_id = uuid4()

        result = await service.simulate_scenario(
            sample_scenario_input,
            sample_kpis,
            user_id=user_id,
        )

        cache_key = f"{user_id}:{result.scenario_id}"
        assert cache_key in service._simulation_cache


# =============================================================================
# Service Tests - Comparison
# =============================================================================

class TestComparison:
    """Tests fuer Szenario-Vergleich."""

    @pytest.mark.asyncio
    async def test_compare_two_scenarios(self, service, sample_kpis):
        """Zwei Szenarien werden verglichen."""
        scenarios = [
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_SAVINGS,
                amount=Decimal("300"),
                duration_months=12,
            ),
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_PAYMENT,
                amount=Decimal("5000"),
                duration_months=12,
            ),
        ]

        result = await service.compare_scenarios(scenarios, sample_kpis)

        assert result is not None
        assert len(result.scenarios) == 2
        assert len(result.ranking) == 2
        assert result.ranking[0]["rank"] == 1
        assert result.ranking[1]["rank"] == 2
        assert result.best_scenario_id is not None
        assert result.recommendation != ""

    @pytest.mark.asyncio
    async def test_compare_ranks_by_net_benefit(self, service, sample_kpis):
        """Ranking erfolgt nach Net-Benefit."""
        scenarios = [
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_SAVINGS,
                amount=Decimal("100"),  # Kleiner Betrag
                duration_months=12,
            ),
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_SAVINGS,
                amount=Decimal("500"),  # Groesserer Betrag
                duration_months=12,
            ),
        ]

        result = await service.compare_scenarios(scenarios, sample_kpis)

        # Hoeherer Betrag sollte besser ranken
        first_rank = result.ranking[0]
        second_rank = result.ranking[1]
        assert first_rank["net_benefit"] >= second_rank["net_benefit"]


# =============================================================================
# Service Tests - Combined Scenarios
# =============================================================================

class TestCombinedScenarios:
    """Tests fuer kombinierte Szenarien."""

    @pytest.mark.asyncio
    async def test_simulate_combined(self, service, sample_kpis):
        """Kombinierte Szenarien werden simuliert."""
        scenarios = [
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_SAVINGS,
                amount=Decimal("200"),
                duration_months=12,
            ),
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_PAYMENT,
                amount=Decimal("3000"),
                duration_months=12,
            ),
        ]

        result = await service.simulate_combined_scenarios(scenarios, sample_kpis)

        assert result is not None
        assert result.scenario_type == ScenarioType.CUSTOM
        assert "Kombiniert:" in result.scenario_description
        assert result.confidence_percentage == 75.0  # Reduziert fuer kombiniert

    @pytest.mark.asyncio
    async def test_combined_aggregates_costs_and_benefits(self, service, sample_kpis):
        """Kombinierte Szenarien aggregieren Kosten und Nutzen."""
        scenarios = [
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_SAVINGS,
                amount=Decimal("300"),
                duration_months=12,
            ),
            ScenarioInput(
                scenario_type=ScenarioType.EXTRA_PAYMENT,
                amount=Decimal("5000"),
                duration_months=12,
            ),
        ]

        result = await service.simulate_combined_scenarios(scenarios, sample_kpis)

        # Cost sollte mindestens die Sondertilgung enthalten
        assert result.total_cost >= Decimal("5000")


# =============================================================================
# Service Tests - Quick Scenarios
# =============================================================================

class TestQuickScenarios:
    """Tests fuer Quick-Szenarios."""

    @pytest.mark.asyncio
    async def test_get_quick_scenarios_for_high_dti(self, service):
        """Quick Scenarios bei hohem DTI."""
        kpis = {
            "dti_ratio": 40.0,  # Hoch
            "emergency_fund_months": 6.0,
            "savings_rate": 15.0,
            "monthly_income": 5000.0,
            "monthly_expenses": 3000.0,
        }

        scenarios = await service.get_quick_scenarios(kpis)

        # Sollte "reduce_dti" Szenario enthalten
        ids = [s["id"] for s in scenarios]
        assert "reduce_dti" in ids

    @pytest.mark.asyncio
    async def test_get_quick_scenarios_for_low_emergency_fund(self, service):
        """Quick Scenarios bei niedrigem Notgroschen."""
        kpis = {
            "dti_ratio": 25.0,
            "emergency_fund_months": 2.0,  # Niedrig
            "savings_rate": 15.0,
            "monthly_income": 5000.0,
            "monthly_expenses": 3000.0,
        }

        scenarios = await service.get_quick_scenarios(kpis)

        ids = [s["id"] for s in scenarios]
        assert "build_emergency_fund" in ids

    @pytest.mark.asyncio
    async def test_get_quick_scenarios_for_low_savings_rate(self, service):
        """Quick Scenarios bei niedriger Sparquote."""
        kpis = {
            "dti_ratio": 25.0,
            "emergency_fund_months": 6.0,
            "savings_rate": 8.0,  # Niedrig
            "monthly_income": 5000.0,
            "monthly_expenses": 3000.0,
        }

        scenarios = await service.get_quick_scenarios(kpis)

        ids = [s["id"] for s in scenarios]
        assert "increase_savings" in ids

    @pytest.mark.asyncio
    async def test_get_quick_scenarios_always_includes_stress_tests(self, service, sample_kpis):
        """Quick Scenarios enthalten immer Stresstests."""
        scenarios = await service.get_quick_scenarios(sample_kpis)

        ids = [s["id"] for s in scenarios]
        assert "interest_increase" in ids
        assert "income_loss" in ids


# =============================================================================
# Impact Severity Tests
# =============================================================================

class TestImpactSeverity:
    """Tests fuer Impact-Severity-Bestimmung."""

    def test_very_positive(self, service):
        """Sehr positive Aenderung (> +20%)."""
        severity = service._determine_impact_severity(25.0)
        assert severity == ImpactSeverity.VERY_POSITIVE

    def test_positive(self, service):
        """Positive Aenderung (+5% bis +20%)."""
        severity = service._determine_impact_severity(10.0)
        assert severity == ImpactSeverity.POSITIVE

    def test_neutral(self, service):
        """Neutrale Aenderung (-5% bis +5%)."""
        severity = service._determine_impact_severity(0.0)
        assert severity == ImpactSeverity.NEUTRAL

        severity = service._determine_impact_severity(4.0)
        assert severity == ImpactSeverity.NEUTRAL

        severity = service._determine_impact_severity(-4.0)
        assert severity == ImpactSeverity.NEUTRAL

    def test_negative(self, service):
        """Negative Aenderung (-20% bis -5%)."""
        severity = service._determine_impact_severity(-10.0)
        assert severity == ImpactSeverity.NEGATIVE

    def test_very_negative(self, service):
        """Sehr negative Aenderung (< -20%)."""
        severity = service._determine_impact_severity(-25.0)
        assert severity == ImpactSeverity.VERY_NEGATIVE


# =============================================================================
# KPI-spezifische Impact Severity Tests
# =============================================================================

class TestKPIImpactSeverity:
    """Tests fuer KPI-spezifische Impact-Severity."""

    def test_dti_decrease_is_positive(self, service):
        """DTI-Senkung ist positiv."""
        # DTI sinkt um 10% -> invers = positiv
        severity = service._determine_kpi_impact_severity("dti_ratio", -10.0)
        assert severity == ImpactSeverity.POSITIVE

    def test_dti_increase_is_negative(self, service):
        """DTI-Erhöhung ist negativ."""
        severity = service._determine_kpi_impact_severity("dti_ratio", 10.0)
        assert severity == ImpactSeverity.NEGATIVE

    def test_debt_decrease_is_positive(self, service):
        """Schulden-Senkung ist positiv."""
        severity = service._determine_kpi_impact_severity("total_debt", -15.0)
        assert severity == ImpactSeverity.POSITIVE

    def test_savings_rate_increase_is_positive(self, service):
        """Sparquoten-Erhöhung ist positiv."""
        severity = service._determine_kpi_impact_severity("savings_rate", 15.0)
        assert severity == ImpactSeverity.POSITIVE


# =============================================================================
# Payback Calculation Tests
# =============================================================================

class TestPaybackCalculation:
    """Tests fuer Payback-Berechnung."""

    def test_payback_with_positive_benefit(self, service):
        """Payback wird berechnet wenn Benefit > Cost."""
        payback = service._calculate_payback(
            total_cost=Decimal("1200"),  # Exakt teilbar
            total_benefit=Decimal("2400"),  # 2400/12 = 200/Monat
            duration_months=12,
        )

        # Payback: 1200 / 200 = 6 Monate exakt
        assert payback is not None
        assert payback == 6

    def test_payback_none_when_no_cost(self, service):
        """Payback ist None ohne Kosten."""
        payback = service._calculate_payback(
            total_cost=Decimal("0"),
            total_benefit=Decimal("1000"),
            duration_months=12,
        )

        assert payback is None

    def test_payback_none_when_no_benefit(self, service):
        """Payback ist None ohne Benefit."""
        payback = service._calculate_payback(
            total_cost=Decimal("1000"),
            total_benefit=Decimal("0"),
            duration_months=12,
        )

        assert payback is None

    def test_payback_none_when_benefit_less_than_cost(self, service):
        """Payback ist None wenn Benefit < Cost."""
        payback = service._calculate_payback(
            total_cost=Decimal("1000"),
            total_benefit=Decimal("500"),
            duration_months=12,
        )

        assert payback is None

    def test_payback_capped_at_120_months(self, service):
        """Payback ist maximal 120 Monate."""
        payback = service._calculate_payback(
            total_cost=Decimal("10000"),
            total_benefit=Decimal("10001"),  # Minimal mehr
            duration_months=12,
        )

        assert payback is not None
        assert payback <= 120


# =============================================================================
# Confidence Calculation Tests
# =============================================================================

class TestConfidenceCalculation:
    """Tests fuer Konfidenz-Berechnung."""

    def test_confidence_with_complete_data(self, service, sample_kpis):
        """Volle Konfidenz bei vollstaendigen Daten."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            duration_months=6,
        )

        confidence = service._calculate_confidence(scenario, sample_kpis)

        assert confidence >= 80.0

    def test_confidence_reduced_for_long_horizon(self, service, sample_kpis):
        """Konfidenz sinkt bei langem Zeithorizont."""
        short_term = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            duration_months=6,
        )
        long_term = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            duration_months=36,
        )

        short_confidence = service._calculate_confidence(short_term, sample_kpis)
        long_confidence = service._calculate_confidence(long_term, sample_kpis)

        assert short_confidence > long_confidence

    def test_confidence_reduced_for_incomplete_data(self, service):
        """Konfidenz sinkt bei unvollstaendigen Daten."""
        complete_kpis = {
            "health_score": 70.0,
            "dti_ratio": 35.0,
            "savings_rate": 10.0,
            "monthly_income": 5000.0,
        }
        incomplete_kpis = {
            "health_score": 70.0,
        }

        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            duration_months=12,
        )

        complete_confidence = service._calculate_confidence(scenario, complete_kpis)
        incomplete_confidence = service._calculate_confidence(scenario, incomplete_kpis)

        assert complete_confidence > incomplete_confidence


# =============================================================================
# Data Basis Tests
# =============================================================================

class TestDataBasis:
    """Tests fuer Datenbasis-Bestimmung."""

    def test_full_data(self, service):
        """Vollstaendige Finanzdaten bei 10+ KPIs."""
        kpis = {f"kpi_{i}": i for i in range(12)}

        basis = service._determine_data_basis(kpis)

        assert basis == "Vollstaendige Finanzdaten"

    def test_basic_data(self, service):
        """Basis-Finanzdaten bei 5-9 KPIs."""
        kpis = {f"kpi_{i}": i for i in range(7)}

        basis = service._determine_data_basis(kpis)

        assert basis == "Basis-Finanzdaten"

    def test_limited_data(self, service):
        """Begrenzte Datenbasis bei <5 KPIs."""
        kpis = {"kpi_1": 1, "kpi_2": 2}

        basis = service._determine_data_basis(kpis)

        assert basis == "Begrenzte Datenbasis"


# =============================================================================
# Scenario Description Tests
# =============================================================================

class TestScenarioDescription:
    """Tests fuer Szenario-Beschreibung."""

    def test_extra_savings_description(self, service):
        """Extra Savings Beschreibung."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_SAVINGS,
            amount=Decimal("300"),
        )

        desc = service._generate_scenario_description(scenario)

        assert "300" in desc
        assert "sparen" in desc.lower()

    def test_extra_payment_description(self, service):
        """Extra Payment Beschreibung."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.EXTRA_PAYMENT,
            amount=Decimal("5000"),
        )

        desc = service._generate_scenario_description(scenario)

        assert "5,000" in desc or "5000" in desc
        assert "Sondertilgung" in desc

    def test_interest_rate_increase_description(self, service):
        """Zinssatz-Steigerung Beschreibung."""
        scenario = ScenarioInput(
            scenario_type=ScenarioType.INTEREST_RATE_CHANGE,
            percentage=2.0,
        )

        desc = service._generate_scenario_description(scenario)

        assert "Zinssatz" in desc
        assert "steigt" in desc


# =============================================================================
# Timeline Generation Tests
# =============================================================================

class TestTimelineGeneration:
    """Tests fuer Zeitleisten-Generierung."""

    @pytest.mark.asyncio
    async def test_timeline_has_start_and_end(self, service, sample_kpis):
        """Zeitleiste hat Start- und Endpunkt."""
        impact_data = {
            "new_kpis": {"health_score": 80.0},
            "changes": {"health_score": 10.0},
        }

        timeline = await service._generate_timeline(
            sample_kpis,
            impact_data,
            duration_months=12,
        )

        assert len(timeline) > 0
        assert timeline[0].month == 0
        assert "Start" in timeline[0].events[0]

    @pytest.mark.asyncio
    async def test_timeline_interpolates_health_score(self, service, sample_kpis):
        """Zeitleiste interpoliert Health Score."""
        impact_data = {
            "new_kpis": {"health_score": 90.0},
            "changes": {"health_score": 20.0},
        }

        timeline = await service._generate_timeline(
            sample_kpis,
            impact_data,
            duration_months=12,
        )

        # Erster Punkt: 70.0, Letzter Punkt: ~90.0
        assert timeline[0].health_score == 70.0
        assert timeline[-1].health_score > timeline[0].health_score

    @pytest.mark.asyncio
    async def test_timeline_steps_every_3_months(self, service, sample_kpis):
        """Zeitleiste hat Punkte alle 3 Monate."""
        impact_data = {
            "new_kpis": {"health_score": 80.0},
            "changes": {},
        }

        timeline = await service._generate_timeline(
            sample_kpis,
            impact_data,
            duration_months=12,
        )

        months = [p.month for p in timeline]
        # Sollte 0, 3, 6, 9, 12 haben
        assert 0 in months
        assert 3 in months
        assert 6 in months
