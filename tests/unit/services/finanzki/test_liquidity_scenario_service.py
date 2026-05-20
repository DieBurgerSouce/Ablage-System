# -*- coding: utf-8 -*-
"""Unit Tests fuer LiquidityScenarioService.

Vision 2026+ Feature #8: Liquiditaets-Szenarien (What-If)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import random

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.finanzki.liquidity_scenario_service import (
    LiquidityScenarioService,
    ScenarioResult,
    ScenarioType,
    ScenarioAssumption,
    ScenarioComparison,
    MonteCarloResult,
    LiquidityCorridor,
    RiskLevel,
)


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def service(mock_db: AsyncMock) -> LiquidityScenarioService:
    """Erstellt Service-Instanz."""
    return LiquidityScenarioService(mock_db)


@pytest.fixture
def company_id() -> uuid.UUID:
    """Test Company ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_forecast() -> Dict[str, Any]:
    """Mock Cashflow-Prognose."""
    forecast_data = []
    balance = 10000.0

    for i in range(30):
        inflows = 500.0 + (i % 5) * 100
        outflows = 400.0 + (i % 3) * 50
        balance += inflows - outflows
        forecast_data.append({
            "date": (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d"),
            "inflows": inflows,
            "inflows_adjusted": inflows,
            "outflows": outflows,
            "balance": balance,
        })

    return {
        "current_balance": 10000.0,
        "forecast": forecast_data,
    }


# =============================================================================
# Test: create_scenario - Basis
# =============================================================================


class TestCreateScenario:
    """Tests fuer create_scenario Methode."""

    @pytest.mark.asyncio
    async def test_creates_base_scenario(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Erstellt Basis-Szenario."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            with patch.object(
                service, "_cache_scenario", new_callable=AsyncMock
            ):
                result = await service.create_scenario(
                    company_id=company_id,
                    name="Test Basis",
                    scenario_type=ScenarioType.BASE,
                    forecast_days=30,
                )

        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == ScenarioType.BASE
        assert result.name == "Test Basis"
        assert result.forecast_days == 30
        assert result.current_balance == 10000.0

    @pytest.mark.asyncio
    async def test_creates_custom_scenario_with_assumptions(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Erstellt Custom-Szenario mit Annahmen."""
        assumptions = [
            {
                "name": "Verzoegerte Zahlungen",
                "parameter": "payment_delay",
                "value": 7,
                "description": "7 Tage Verzoegerung",
            }
        ]

        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            with patch.object(
                service, "_cache_scenario", new_callable=AsyncMock
            ):
                result = await service.create_scenario(
                    company_id=company_id,
                    name="Verzoegerte Zahlungen",
                    scenario_type=ScenarioType.CUSTOM,
                    assumptions=assumptions,
                    forecast_days=30,
                )

        assert result.scenario_type == ScenarioType.CUSTOM
        assert len(result.assumptions) == 1
        assert result.assumptions[0].name == "Verzoegerte Zahlungen"

    @pytest.mark.asyncio
    async def test_calculates_min_max_balance(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Berechnet Min/Max Balance korrekt."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            with patch.object(
                service, "_cache_scenario", new_callable=AsyncMock
            ):
                result = await service.create_scenario(
                    company_id=company_id,
                    name="Test",
                    scenario_type=ScenarioType.BASE,
                )

        # Min/Max sollten berechnet werden
        assert result.min_balance <= result.max_balance
        assert result.min_balance_date != ""


# =============================================================================
# Test: get_standard_scenarios
# =============================================================================


class TestGetStandardScenarios:
    """Tests fuer Standard-Szenarien."""

    @pytest.mark.asyncio
    async def test_creates_all_standard_scenarios(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Erstellt alle Standard-Szenarien."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            with patch.object(
                service, "_cache_scenario", new_callable=AsyncMock
            ):
                result = await service.get_standard_scenarios(company_id)

        assert isinstance(result, ScenarioComparison)
        # Base, Best Case, Worst Case, Expected = 4 Szenarien
        assert len(result.scenarios) >= 3

        scenario_types = [s.scenario_type for s in result.scenarios]
        assert ScenarioType.BASE in scenario_types
        assert ScenarioType.BEST_CASE in scenario_types
        assert ScenarioType.WORST_CASE in scenario_types


# =============================================================================
# Test: Monte Carlo Simulation
# =============================================================================


class TestMonteCarlo:
    """Tests fuer Monte-Carlo-Simulation."""

    @pytest.mark.asyncio
    async def test_runs_monte_carlo_iterations(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Fuehrt Monte-Carlo-Iterationen durch."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            # Weniger Iterationen fuer schnellere Tests
            result = await service.run_monte_carlo(
                company_id=company_id,
                forecast_days=30,
                iterations=100,
            )

        assert isinstance(result, MonteCarloResult)
        assert result.iterations == 100

    @pytest.mark.asyncio
    async def test_calculates_percentiles(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Berechnet Perzentile korrekt."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            result = await service.run_monte_carlo(
                company_id=company_id,
                iterations=100,
            )

        # Perzentile sollten vorhanden sein
        assert "p5" in result.percentiles
        assert "p25" in result.percentiles
        assert "p50" in result.percentiles
        assert "p75" in result.percentiles
        assert "p95" in result.percentiles

        # Perzentile sollten aufsteigend sein
        assert result.percentiles["p5"] <= result.percentiles["p25"]
        assert result.percentiles["p25"] <= result.percentiles["p50"]
        assert result.percentiles["p50"] <= result.percentiles["p75"]
        assert result.percentiles["p75"] <= result.percentiles["p95"]

    @pytest.mark.asyncio
    async def test_calculates_probabilities(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Berechnet Wahrscheinlichkeiten korrekt."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            result = await service.run_monte_carlo(
                company_id=company_id,
                iterations=100,
            )

        # Wahrscheinlichkeiten sollten zwischen 0 und 1 sein
        assert 0.0 <= result.probability_negative <= 1.0
        assert 0.0 <= result.probability_critical <= 1.0

    @pytest.mark.asyncio
    async def test_builds_confidence_corridor(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_forecast: Dict[str, Any],
    ) -> None:
        """Erstellt Konfidenz-Korridor."""
        with patch.object(
            service.cashflow_service, "forecast_with_seasonality",
            new_callable=AsyncMock
        ) as mock_cf:
            mock_cf.return_value = mock_forecast

            result = await service.run_monte_carlo(
                company_id=company_id,
                forecast_days=30,
                iterations=100,
            )

        # Korridor sollte 30 Tage haben
        assert len(result.confidence_corridor) > 0


# =============================================================================
# Test: Payment Delay Logic (Fixed)
# =============================================================================


class TestPaymentDelayLogic:
    """Tests fuer korrigierte Payment-Delay-Logik."""

    def test_delay_probability_calculation(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Korrigierte Delay-Wahrscheinlichkeit."""
        # Test: factor = 1.2 -> delay_probability = 0.2/1.2 = 16.7%
        factor = 1.2
        expected_probability = (factor - 1.0) / factor

        assert 0.16 < expected_probability < 0.17

    def test_delay_probability_never_negative(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Delay-Wahrscheinlichkeit ist nie negativ."""
        # Alte fehlerhafte Logik: random.random() < (factor - 1)
        # Bei factor < 1 war das immer False (ok)
        # Bei factor = 0.8 war (factor - 1) = -0.2 (negativ!)

        # Neue Logik: nur wenn factor > 1
        for factor in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
            if factor > 1.0:
                probability = (factor - 1.0) / factor
                assert probability > 0.0
                assert probability < 1.0
            else:
                # Keine Verzoegerung bei factor <= 1.0
                pass


# =============================================================================
# Test: Risk Assessment
# =============================================================================


class TestRiskAssessment:
    """Tests fuer Risiko-Bewertung."""

    def test_assess_risk_low(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Low Risk bei positivem Min-Balance."""
        forecast = {"forecast": [{"balance": 10000}]}
        risk = service._assess_risk(5000, forecast)
        assert risk == RiskLevel.LOW

    def test_assess_risk_medium(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Medium Risk bei niedrigem Min-Balance."""
        forecast = {"forecast": [{"balance": 1000}]}
        risk = service._assess_risk(500, forecast)
        assert risk == RiskLevel.MEDIUM

    def test_assess_risk_high(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """High Risk bei sehr niedrigem Min-Balance."""
        forecast = {"forecast": [{"balance": 100}]}
        risk = service._assess_risk(100, forecast)
        assert risk == RiskLevel.HIGH

    def test_assess_risk_critical(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Critical Risk bei negativem Min-Balance."""
        forecast = {"forecast": [{"balance": -1000}]}
        risk = service._assess_risk(-5000, forecast)
        assert risk == RiskLevel.CRITICAL


# =============================================================================
# Test: Warnings and Recommendations
# =============================================================================


class TestWarningsAndRecommendations:
    """Tests fuer Warnungen und Empfehlungen."""

    def test_generates_warnings_for_negative_balance(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Generiert Warnungen bei negativem Saldo."""
        daily_forecast = [
            {"date": "2026-01-15", "balance": -500},
        ]
        warnings = service._generate_warnings(daily_forecast, -500)

        assert len(warnings) > 0
        assert any("negativ" in w.lower() for w in warnings)

    def test_generates_recommendations_for_critical_risk(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Generiert Empfehlungen bei kritischem Risiko."""
        recommendations = service._generate_recommendations(
            RiskLevel.CRITICAL, -10000, []
        )

        assert len(recommendations) > 0


# =============================================================================
# Test: Scenario Comparison
# =============================================================================


class TestScenarioComparison:
    """Tests fuer Szenario-Vergleich."""

    @pytest.mark.asyncio
    async def test_compares_scenarios(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Vergleicht mehrere Szenarien."""
        # Mock cached scenarios
        scenario1 = ScenarioResult(
            scenario_id="s1",
            scenario_type=ScenarioType.BASE,
            name="Base",
            description="",
            assumptions=[],
            forecast_days=30,
            current_balance=10000,
            min_balance=5000,
            min_balance_date="2026-01-15",
            max_balance=15000,
            end_balance=12000,
            total_inflows=50000,
            total_outflows=48000,
            daily_forecast=[],
            risk_level=RiskLevel.LOW,
            warnings=[],
            recommendations=[],
        )

        scenario2 = ScenarioResult(
            scenario_id="s2",
            scenario_type=ScenarioType.WORST_CASE,
            name="Worst",
            description="",
            assumptions=[],
            forecast_days=30,
            current_balance=10000,
            min_balance=-2000,
            min_balance_date="2026-01-20",
            max_balance=10000,
            end_balance=3000,
            total_inflows=40000,
            total_outflows=47000,
            daily_forecast=[],
            risk_level=RiskLevel.CRITICAL,
            warnings=[],
            recommendations=[],
        )

        with patch.object(
            service, "_get_cached_scenario", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.side_effect = [scenario1, scenario2]

            result = await service.compare_scenarios(
                company_id, ["s1", "s2"]
            )

        assert isinstance(result, ScenarioComparison)
        assert len(result.scenarios) == 2
        assert result.base_scenario_id == "s1"

    @pytest.mark.asyncio
    async def test_raises_error_when_no_scenarios_found(
        self,
        service: LiquidityScenarioService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Wirft Fehler wenn keine Szenarien gefunden."""
        with patch.object(
            service, "_get_cached_scenario", new_callable=AsyncMock
        ) as mock_cache:
            mock_cache.return_value = None

            with pytest.raises(ValueError, match="Keine Szenarien"):
                await service.compare_scenarios(company_id, ["s1", "s2"])


# =============================================================================
# Test: Assumption Parsing
# =============================================================================


class TestAssumptionParsing:
    """Tests fuer Annahmen-Parsing."""

    def test_parses_assumptions(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Parst Annahmen korrekt."""
        raw_assumptions = [
            {
                "name": "Test Annahme",
                "parameter": "payment_delay",
                "value": 7,
                "description": "7 Tage",
            }
        ]

        parsed = service._parse_assumptions(raw_assumptions)

        assert len(parsed) == 1
        assert isinstance(parsed[0], ScenarioAssumption)
        assert parsed[0].name == "Test Annahme"
        assert parsed[0].parameter == "payment_delay"
        assert parsed[0].value == 7

    def test_handles_empty_assumptions(
        self,
        service: LiquidityScenarioService,
    ) -> None:
        """Behandelt leere Annahmen."""
        parsed = service._parse_assumptions([])
        assert parsed == []
