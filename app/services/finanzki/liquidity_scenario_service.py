# -*- coding: utf-8 -*-
"""Liquidity Scenario Service.

What-If Analyse fuer Cashflow-Prognosen mit Monte-Carlo-Simulation.

Features:
- Basis-Szenario (erwartete Zahlungen)
- Benutzerdefinierte Szenarien
- Automatische Best/Worst/Expected Case
- Monte-Carlo-Simulation fuer Unsicherheit
- Vergleichs-Visualisierung
- Timeline mit Liquiditaets-Korridoren
- Handlungsempfehlungen

Created: 2026-01-28
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
import math
import statistics

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    InvoiceTracking,
    BankTransaction,
    BankAccount,
    BusinessEntity,
    AppConfig,
)
from app.services.finanzki.predictive_cashflow_service import (
    PredictiveCashFlowService,
    SeasonalityPattern,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Data Classes
# =============================================================================


class ScenarioType(str, Enum):
    """Szenario-Typen."""

    BASE = "base"  # Basis-Szenario
    BEST_CASE = "best_case"
    WORST_CASE = "worst_case"
    EXPECTED = "expected"
    CUSTOM = "custom"
    MONTE_CARLO = "monte_carlo"


class RiskLevel(str, Enum):
    """Risiko-Level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScenarioAssumption:
    """Annahme fuer ein Szenario."""

    name: str
    description: str
    parameter: str
    value: float
    unit: str = ""
    impact_type: str = "multiplicative"  # multiplicative, additive


@dataclass
class ScenarioResult:
    """Ergebnis eines einzelnen Szenarios."""

    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    assumptions: List[ScenarioAssumption]
    forecast_days: int
    current_balance: float
    min_balance: float
    min_balance_date: str
    max_balance: float
    end_balance: float
    total_inflows: float
    total_outflows: float
    daily_forecast: List[Dict[str, Any]]
    risk_level: RiskLevel
    warnings: List[str]
    recommendations: List[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MonteCarloResult:
    """Ergebnis der Monte-Carlo-Simulation."""

    iterations: int
    confidence_level: float
    percentiles: Dict[str, float]  # p5, p25, p50, p75, p95
    mean_min_balance: float
    std_dev_min_balance: float
    probability_negative: float  # Wahrscheinlichkeit negativer Bilanz
    probability_critical: float  # Wahrscheinlichkeit kritischer Liquiditaet
    confidence_corridor: List[Dict[str, Any]]  # Daily P5-P95 corridor


@dataclass
class LiquidityCorridor:
    """Liquiditaets-Korridor fuer einen Tag."""

    date: str
    p5: float  # 5. Perzentil (Worst Case)
    p25: float
    p50: float  # Median
    p75: float
    p95: float  # 95. Perzentil (Best Case)
    expected: float  # Erwartungswert


@dataclass
class ScenarioComparison:
    """Vergleich mehrerer Szenarien."""

    scenarios: List[ScenarioResult]
    base_scenario_id: str
    comparison_metrics: Dict[str, Dict[str, float]]
    monte_carlo: Optional[MonteCarloResult] = None
    corridor: List[LiquidityCorridor] = field(default_factory=list)


# =============================================================================
# Cache Key
# =============================================================================

SCENARIO_CACHE_KEY = "liquidity_scenarios"


# =============================================================================
# Liquidity Scenario Service
# =============================================================================


class LiquidityScenarioService:
    """Service fuer Liquiditaets-Szenario-Analyse.

    Ermoeglicht What-If Analysen und Monte-Carlo-Simulationen
    fuer Cashflow-Prognosen.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db
        self.cashflow_service = PredictiveCashFlowService(db)

    # =========================================================================
    # Public API
    # =========================================================================

    async def create_scenario(
        self,
        company_id: UUID,
        name: str,
        scenario_type: ScenarioType = ScenarioType.CUSTOM,
        assumptions: Optional[List[Dict[str, Any]]] = None,
        forecast_days: int = 30,
        description: Optional[str] = None,
    ) -> ScenarioResult:
        """Erstellt ein neues Szenario.

        Args:
            company_id: Firmen-ID
            name: Szenario-Name
            scenario_type: Typ des Szenarios
            assumptions: Liste von Annahmen
            forecast_days: Prognosezeitraum
            description: Optionale Beschreibung

        Returns:
            ScenarioResult mit Prognose
        """
        logger.info(
            "scenario_creation_started",
            company_id=str(company_id),
            scenario_type=scenario_type.value,
            name=name,
        )

        # Basis-Prognose holen
        base_forecast = await self.cashflow_service.forecast_with_seasonality(
            company_id, forecast_days
        )

        # Annahmen parsen
        parsed_assumptions = self._parse_assumptions(assumptions or [])

        # Prognose modifizieren basierend auf Annahmen
        modified_forecast = self._apply_assumptions(
            base_forecast, parsed_assumptions, scenario_type
        )

        # Statistiken berechnen
        daily_forecast = modified_forecast.get("forecast", [])
        min_balance = min(f["balance"] for f in daily_forecast) if daily_forecast else 0
        max_balance = max(f["balance"] for f in daily_forecast) if daily_forecast else 0
        end_balance = daily_forecast[-1]["balance"] if daily_forecast else 0

        min_balance_date = ""
        for f in daily_forecast:
            if f["balance"] == min_balance:
                min_balance_date = f["date"]
                break

        # Risiko bewerten
        risk_level = self._assess_risk(min_balance, modified_forecast)

        # Warnungen und Empfehlungen
        warnings = self._generate_warnings(daily_forecast, min_balance)
        recommendations = self._generate_recommendations(
            risk_level, min_balance, parsed_assumptions
        )

        scenario_id = str(uuid4())

        result = ScenarioResult(
            scenario_id=scenario_id,
            scenario_type=scenario_type,
            name=name,
            description=description or f"{scenario_type.value} Szenario",
            assumptions=parsed_assumptions,
            forecast_days=forecast_days,
            current_balance=base_forecast.get("current_balance", 0),
            min_balance=min_balance,
            min_balance_date=min_balance_date,
            max_balance=max_balance,
            end_balance=end_balance,
            total_inflows=sum(f.get("inflows", 0) for f in daily_forecast),
            total_outflows=sum(f.get("outflows", 0) for f in daily_forecast),
            daily_forecast=daily_forecast,
            risk_level=risk_level,
            warnings=warnings,
            recommendations=recommendations,
        )

        # Szenario cachen
        await self._cache_scenario(company_id, result)

        logger.info(
            "scenario_created",
            scenario_id=scenario_id,
            risk_level=risk_level.value,
            min_balance=min_balance,
        )

        return result

    async def get_standard_scenarios(
        self,
        company_id: UUID,
        forecast_days: int = 30,
    ) -> ScenarioComparison:
        """Erstellt Standard-Szenarien (Best/Worst/Expected).

        Args:
            company_id: Firmen-ID
            forecast_days: Prognosezeitraum

        Returns:
            ScenarioComparison mit allen Standard-Szenarien
        """
        scenarios: List[ScenarioResult] = []

        # Base Scenario
        base = await self.create_scenario(
            company_id=company_id,
            name="Basis-Szenario",
            scenario_type=ScenarioType.BASE,
            forecast_days=forecast_days,
            description="Prognose basierend auf aktuellen Daten",
        )
        scenarios.append(base)

        # Best Case
        best_case = await self.create_scenario(
            company_id=company_id,
            name="Best Case",
            scenario_type=ScenarioType.BEST_CASE,
            assumptions=[
                {
                    "name": "Schnellere Zahlungen",
                    "parameter": "payment_speed",
                    "value": 1.2,
                    "description": "20% schnellere Zahlungseingaenge",
                },
                {
                    "name": "Weniger Ausfaelle",
                    "parameter": "default_rate",
                    "value": 0.5,
                    "description": "50% weniger Zahlungsausfaelle",
                },
            ],
            forecast_days=forecast_days,
            description="Optimistisches Szenario",
        )
        scenarios.append(best_case)

        # Worst Case
        worst_case = await self.create_scenario(
            company_id=company_id,
            name="Worst Case",
            scenario_type=ScenarioType.WORST_CASE,
            assumptions=[
                {
                    "name": "Verzoegerte Zahlungen",
                    "parameter": "payment_delay",
                    "value": 14,
                    "unit": "Tage",
                    "description": "14 Tage Zahlungsverzoegerung",
                },
                {
                    "name": "Hoehere Ausfallrate",
                    "parameter": "default_rate",
                    "value": 2.0,
                    "description": "Doppelte Ausfallrate",
                },
                {
                    "name": "Unerwartete Kosten",
                    "parameter": "extra_costs",
                    "value": 10000,
                    "unit": "EUR",
                    "description": "10.000 EUR unerwartete Kosten",
                },
            ],
            forecast_days=forecast_days,
            description="Pessimistisches Szenario",
        )
        scenarios.append(worst_case)

        # Expected Case (gewichteter Durchschnitt)
        expected = await self.create_scenario(
            company_id=company_id,
            name="Expected Case",
            scenario_type=ScenarioType.EXPECTED,
            assumptions=[
                {
                    "name": "Normale Verzoegerung",
                    "parameter": "payment_delay",
                    "value": 5,
                    "unit": "Tage",
                    "description": "5 Tage durchschnittliche Verzoegerung",
                },
                {
                    "name": "Normale Ausfaelle",
                    "parameter": "default_rate",
                    "value": 1.0,
                    "description": "Normale Ausfallrate",
                },
            ],
            forecast_days=forecast_days,
            description="Wahrscheinlichstes Szenario",
        )
        scenarios.append(expected)

        # Vergleich erstellen
        comparison = self._create_comparison(scenarios, base.scenario_id)

        return comparison

    async def run_monte_carlo(
        self,
        company_id: UUID,
        forecast_days: int = 30,
        iterations: int = 1000,
        confidence_level: float = 0.95,
    ) -> MonteCarloResult:
        """Fuehrt Monte-Carlo-Simulation durch.

        Args:
            company_id: Firmen-ID
            forecast_days: Prognosezeitraum
            iterations: Anzahl Simulationen
            confidence_level: Konfidenzniveau (z.B. 0.95)

        Returns:
            MonteCarloResult mit Perzentilen und Wahrscheinlichkeiten
        """
        logger.info(
            "monte_carlo_started",
            company_id=str(company_id),
            iterations=iterations,
            forecast_days=forecast_days,
        )

        # Basis-Prognose
        base_forecast = await self.cashflow_service.forecast_with_seasonality(
            company_id, forecast_days
        )

        # Simulationen durchfuehren
        min_balances: List[float] = []
        daily_results: Dict[int, List[float]] = {
            day: [] for day in range(forecast_days + 1)
        }

        for _ in range(iterations):
            # Zufaellige Parameter (mit min-Guards gegen negative Werte)
            # Normalverteilung kann theoretisch negative Werte erzeugen bei >6σ
            payment_delay_factor = max(0.01, random.gauss(1.0, 0.15))
            inflow_factor = max(0.01, random.gauss(1.0, 0.1))
            outflow_factor = max(0.01, random.gauss(1.0, 0.05))
            default_rate = max(0, min(0.95, random.gauss(0.02, 0.01)))  # 2% +/- 1%, capped

            # Prognose modifizieren
            running_balance = base_forecast["current_balance"]
            simulation_min = float('inf')

            for day_idx, day_data in enumerate(base_forecast["forecast"]):
                # Eingaenge anpassen
                inflows = day_data.get("inflows_adjusted", day_data["inflows"])
                adjusted_inflows = inflows * inflow_factor * (1 - default_rate)

                # Ausgaenge anpassen
                outflows = day_data["outflows"]
                adjusted_outflows = outflows * outflow_factor

                # Zahlungsverzoegerung (Eingaenge verschieben)
                # payment_delay_factor > 1.0 = mehr Verzoegerungen erwartet
                # Korrigierte Logik: Wahrscheinlichkeit = (factor - 1.0) / factor
                # bei factor=1.2 -> 0.2/1.2 = 16.7% Chance auf Verzoegerung
                if payment_delay_factor > 1.0:
                    delay_probability = (payment_delay_factor - 1.0) / payment_delay_factor
                    if random.random() < delay_probability:
                        adjusted_inflows *= 0.5  # 50% verzoegert

                # Balance berechnen
                running_balance += adjusted_inflows - adjusted_outflows
                daily_results[day_idx].append(running_balance)

                if running_balance < simulation_min:
                    simulation_min = running_balance

            min_balances.append(simulation_min)

        # Statistiken berechnen
        min_balances.sort()

        p5_idx = int(iterations * 0.05)
        p25_idx = int(iterations * 0.25)
        p50_idx = int(iterations * 0.50)
        p75_idx = int(iterations * 0.75)
        p95_idx = int(iterations * 0.95)

        percentiles = {
            "p5": min_balances[p5_idx],
            "p25": min_balances[p25_idx],
            "p50": min_balances[p50_idx],
            "p75": min_balances[p75_idx],
            "p95": min_balances[p95_idx],
        }

        mean_min = statistics.mean(min_balances)
        std_dev = statistics.stdev(min_balances) if len(min_balances) > 1 else 0

        # Wahrscheinlichkeiten
        prob_negative = sum(1 for b in min_balances if b < 0) / iterations
        prob_critical = sum(1 for b in min_balances if b < -10000) / iterations

        # Konfidenz-Korridor
        confidence_corridor = self._build_confidence_corridor(
            daily_results, base_forecast["forecast"]
        )

        result = MonteCarloResult(
            iterations=iterations,
            confidence_level=confidence_level,
            percentiles=percentiles,
            mean_min_balance=round(mean_min, 2),
            std_dev_min_balance=round(std_dev, 2),
            probability_negative=round(prob_negative, 4),
            probability_critical=round(prob_critical, 4),
            confidence_corridor=confidence_corridor,
        )

        logger.info(
            "monte_carlo_completed",
            company_id=str(company_id),
            mean_min_balance=mean_min,
            prob_negative=prob_negative,
        )

        return result

    async def compare_scenarios(
        self,
        company_id: UUID,
        scenario_ids: List[str],
    ) -> ScenarioComparison:
        """Vergleicht mehrere Szenarien.

        Args:
            company_id: Firmen-ID
            scenario_ids: Liste der Szenario-IDs

        Returns:
            ScenarioComparison mit Metriken
        """
        scenarios: List[ScenarioResult] = []

        for scenario_id in scenario_ids:
            scenario = await self._get_cached_scenario(company_id, scenario_id)
            if scenario:
                scenarios.append(scenario)

        if not scenarios:
            raise ValueError("Keine Szenarien gefunden")

        base_id = scenarios[0].scenario_id
        comparison = self._create_comparison(scenarios, base_id)

        return comparison

    async def get_scenario(
        self,
        company_id: UUID,
        scenario_id: str,
    ) -> Optional[ScenarioResult]:
        """Holt ein Szenario aus dem Cache.

        Args:
            company_id: Firmen-ID
            scenario_id: Szenario-ID

        Returns:
            ScenarioResult oder None
        """
        return await self._get_cached_scenario(company_id, scenario_id)

    async def list_scenarios(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Listet alle gecachten Szenarien.

        Args:
            company_id: Firmen-ID

        Returns:
            Liste der Szenario-Metadaten
        """
        cache = await self._get_scenario_cache(company_id)
        return [
            {
                "scenario_id": s["scenario_id"],
                "name": s["name"],
                "scenario_type": s["scenario_type"],
                "risk_level": s["risk_level"],
                "min_balance": s["min_balance"],
                "created_at": s["created_at"],
            }
            for s in cache.values()
        ]

    async def delete_scenario(
        self,
        company_id: UUID,
        scenario_id: str,
    ) -> bool:
        """Loescht ein Szenario.

        Args:
            company_id: Firmen-ID
            scenario_id: Szenario-ID

        Returns:
            True wenn erfolgreich
        """
        query = select(AppConfig).where(
            AppConfig.key == f"{SCENARIO_CACHE_KEY}_{company_id}"
        )
        result = await self.db.execute(query)
        config = result.scalar_one_or_none()

        if config and config.value and scenario_id in config.value:
            del config.value[scenario_id]
            await self.db.commit()
            return True

        return False

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _parse_assumptions(
        self,
        assumptions: List[Dict[str, Any]],
    ) -> List[ScenarioAssumption]:
        """Parst Annahmen-Dictionaries zu ScenarioAssumption-Objekten."""
        parsed = []
        for a in assumptions:
            parsed.append(
                ScenarioAssumption(
                    name=a.get("name", "Unbekannt"),
                    description=a.get("description", ""),
                    parameter=a.get("parameter", ""),
                    value=float(a.get("value", 1.0)),
                    unit=a.get("unit", ""),
                    impact_type=a.get("impact_type", "multiplicative"),
                )
            )
        return parsed

    def _apply_assumptions(
        self,
        base_forecast: Dict[str, Any],
        assumptions: List[ScenarioAssumption],
        scenario_type: ScenarioType,
    ) -> Dict[str, Any]:
        """Wendet Annahmen auf Basis-Prognose an."""
        modified = dict(base_forecast)
        forecast = [dict(f) for f in base_forecast.get("forecast", [])]

        # Standard-Modifikationen fuer Szenario-Typen
        inflow_multiplier = 1.0
        outflow_multiplier = 1.0
        delay_days = 0
        extra_costs = 0.0

        if scenario_type == ScenarioType.BEST_CASE:
            inflow_multiplier = 1.1
            outflow_multiplier = 0.95
        elif scenario_type == ScenarioType.WORST_CASE:
            inflow_multiplier = 0.8
            outflow_multiplier = 1.1
            delay_days = 7

        # Annahmen anwenden
        for assumption in assumptions:
            if assumption.parameter == "payment_speed":
                inflow_multiplier *= assumption.value
            elif assumption.parameter == "payment_delay":
                delay_days = int(assumption.value)
            elif assumption.parameter == "default_rate":
                # default_rate als Faktor (z.B. 1.5 = 50% mehr Ausfaelle)
                # Basis-Ausfallrate angenommen: 5%
                # Neue Ausfallrate: 5% * assumption.value
                # Auswirkung auf Einnahmen: 1 - neue_rate
                base_default_rate = 0.05  # 5% Basis-Ausfallrate
                adjusted_rate = base_default_rate * assumption.value
                # Sicherstellen, dass nicht mehr als 100% ausfallen
                adjusted_rate = min(0.95, adjusted_rate)
                inflow_multiplier *= (1.0 - adjusted_rate)
            elif assumption.parameter == "extra_costs":
                extra_costs = assumption.value
            elif assumption.parameter == "inflow_change":
                if assumption.impact_type == "multiplicative":
                    inflow_multiplier *= assumption.value
                else:
                    inflow_multiplier += assumption.value
            elif assumption.parameter == "outflow_change":
                if assumption.impact_type == "multiplicative":
                    outflow_multiplier *= assumption.value
                else:
                    outflow_multiplier += assumption.value

        # Prognose modifizieren
        running_balance = base_forecast.get("current_balance", 0)

        for i, day in enumerate(forecast):
            # Eingaenge anpassen
            original_inflows = day.get("inflows_adjusted", day.get("inflows", 0))
            day["inflows"] = round(original_inflows * inflow_multiplier, 2)

            # Zahlungsverzoegerung: Eingaenge um delay_days verschieben
            if delay_days > 0 and i < len(forecast) - delay_days:
                # Ein Teil der Eingaenge wird verzoegert
                delayed = day["inflows"] * 0.3
                day["inflows"] -= delayed
                forecast[i + delay_days]["inflows"] = forecast[i + delay_days].get("inflows", 0) + delayed

            # Ausgaenge anpassen
            original_outflows = day.get("outflows", 0)
            day["outflows"] = round(original_outflows * outflow_multiplier, 2)

            # Extra-Kosten am ersten Tag
            if i == 0 and extra_costs > 0:
                day["outflows"] += extra_costs

            # Net Flow und Balance
            day["net_flow"] = round(day["inflows"] - day["outflows"], 2)
            running_balance += day["net_flow"]
            day["balance"] = round(running_balance, 2)

        modified["forecast"] = forecast
        return modified

    def _assess_risk(
        self,
        min_balance: float,
        forecast: Dict[str, Any],
    ) -> RiskLevel:
        """Bewertet das Risiko-Level."""
        if min_balance < -50000:
            return RiskLevel.CRITICAL
        elif min_balance < -10000:
            return RiskLevel.HIGH
        elif min_balance < 0:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_warnings(
        self,
        daily_forecast: List[Dict[str, Any]],
        min_balance: float,
    ) -> List[str]:
        """Generiert Warnungen."""
        warnings = []

        if min_balance < 0:
            warnings.append(f"Negativer Saldo erwartet: {min_balance:,.2f} EUR")

        # Tage mit negativem Saldo zaehlen
        negative_days = sum(1 for f in daily_forecast if f.get("balance", 0) < 0)
        if negative_days > 0:
            warnings.append(f"{negative_days} Tag(e) mit negativem Saldo")

        # Grosse Schwankungen
        if daily_forecast:
            balances = [f.get("balance", 0) for f in daily_forecast]
            max_swing = max(balances) - min(balances)
            if max_swing > 100000:
                warnings.append(f"Hohe Schwankung: {max_swing:,.0f} EUR")

        return warnings

    def _generate_recommendations(
        self,
        risk_level: RiskLevel,
        min_balance: float,
        assumptions: List[ScenarioAssumption],
    ) -> List[str]:
        """Generiert Handlungsempfehlungen."""
        recommendations = []

        if risk_level == RiskLevel.CRITICAL:
            recommendations.append("SOFORT: Kontokorrent-Kredit einrichten")
            recommendations.append("Zahlungen priorisieren und nicht-kritische verschieben")
            recommendations.append("Zahlungsziele mit Lieferanten neu verhandeln")
        elif risk_level == RiskLevel.HIGH:
            recommendations.append("Liquiditaetsreserve aufbauen")
            recommendations.append("Forderungsmanagement intensivieren")
            recommendations.append("Skonto-Nutzung bei Einkauf pruefen")
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("Cashflow-Monitoring verstaerken")
            recommendations.append("Zahlungsziele einhalten")
        else:
            recommendations.append("Ueberschuessige Liquiditaet anlegen")
            recommendations.append("Investitionsmoeglichkeiten pruefen")

        return recommendations

    def _create_comparison(
        self,
        scenarios: List[ScenarioResult],
        base_id: str,
    ) -> ScenarioComparison:
        """Erstellt Szenario-Vergleich."""
        base_scenario = next(
            (s for s in scenarios if s.scenario_id == base_id),
            scenarios[0] if scenarios else None
        )

        comparison_metrics: Dict[str, Dict[str, float]] = {}

        for scenario in scenarios:
            if not base_scenario:
                continue

            metrics = {
                "min_balance": scenario.min_balance,
                "min_balance_diff": scenario.min_balance - base_scenario.min_balance,
                "end_balance": scenario.end_balance,
                "end_balance_diff": scenario.end_balance - base_scenario.end_balance,
                "total_inflows": scenario.total_inflows,
                "total_outflows": scenario.total_outflows,
                "net_flow": scenario.total_inflows - scenario.total_outflows,
            }
            comparison_metrics[scenario.scenario_id] = metrics

        # Korridor aus allen Szenarien
        corridor = self._build_corridor_from_scenarios(scenarios)

        return ScenarioComparison(
            scenarios=scenarios,
            base_scenario_id=base_id,
            comparison_metrics=comparison_metrics,
            corridor=corridor,
        )

    def _build_corridor_from_scenarios(
        self,
        scenarios: List[ScenarioResult],
    ) -> List[LiquidityCorridor]:
        """Erstellt Liquiditaets-Korridor aus Szenarien."""
        if not scenarios:
            return []

        # Alle Tage sammeln
        days: Dict[str, List[float]] = {}

        for scenario in scenarios:
            for day_data in scenario.daily_forecast:
                date = day_data.get("date", "")
                if date not in days:
                    days[date] = []
                days[date].append(day_data.get("balance", 0))

        # Korridor berechnen
        corridor = []
        for date in sorted(days.keys()):
            balances = sorted(days[date])
            n = len(balances)

            corridor.append(
                LiquidityCorridor(
                    date=date,
                    p5=balances[0],
                    p25=balances[n // 4] if n >= 4 else balances[0],
                    p50=balances[n // 2] if n >= 2 else balances[0],
                    p75=balances[3 * n // 4] if n >= 4 else balances[-1],
                    p95=balances[-1],
                    expected=statistics.mean(balances),
                )
            )

        return corridor

    def _build_confidence_corridor(
        self,
        daily_results: Dict[int, List[float]],
        base_forecast: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Erstellt Konfidenz-Korridor aus Monte-Carlo-Ergebnissen."""
        corridor = []

        for day_idx, balances in sorted(daily_results.items()):
            if not balances:
                continue

            sorted_balances = sorted(balances)
            n = len(sorted_balances)

            date = base_forecast[day_idx]["date"] if day_idx < len(base_forecast) else ""

            corridor.append({
                "date": date,
                "p5": round(sorted_balances[int(n * 0.05)], 2),
                "p25": round(sorted_balances[int(n * 0.25)], 2),
                "p50": round(sorted_balances[int(n * 0.50)], 2),
                "p75": round(sorted_balances[int(n * 0.75)], 2),
                "p95": round(sorted_balances[int(n * 0.95)], 2),
                "mean": round(statistics.mean(sorted_balances), 2),
            })

        return corridor

    # =========================================================================
    # Caching
    # =========================================================================

    async def _cache_scenario(
        self,
        company_id: UUID,
        scenario: ScenarioResult,
    ) -> None:
        """Cached ein Szenario."""
        cache_key = f"{SCENARIO_CACHE_KEY}_{company_id}"

        query = select(AppConfig).where(AppConfig.key == cache_key)
        result = await self.db.execute(query)
        config = result.scalar_one_or_none()

        cache = config.value if config else {}
        cache[scenario.scenario_id] = {
            "scenario_id": scenario.scenario_id,
            "scenario_type": scenario.scenario_type.value,
            "name": scenario.name,
            "description": scenario.description,
            "assumptions": [
                {
                    "name": a.name,
                    "parameter": a.parameter,
                    "value": a.value,
                    "unit": a.unit,
                }
                for a in scenario.assumptions
            ],
            "forecast_days": scenario.forecast_days,
            "current_balance": scenario.current_balance,
            "min_balance": scenario.min_balance,
            "min_balance_date": scenario.min_balance_date,
            "max_balance": scenario.max_balance,
            "end_balance": scenario.end_balance,
            "total_inflows": scenario.total_inflows,
            "total_outflows": scenario.total_outflows,
            "risk_level": scenario.risk_level.value,
            "warnings": scenario.warnings,
            "recommendations": scenario.recommendations,
            "created_at": scenario.created_at.isoformat(),
            "daily_forecast": scenario.daily_forecast,
        }

        if config:
            config.value = cache
        else:
            config = AppConfig(key=cache_key, value=cache)
            self.db.add(config)

        await self.db.commit()

    async def _get_cached_scenario(
        self,
        company_id: UUID,
        scenario_id: str,
    ) -> Optional[ScenarioResult]:
        """Holt ein Szenario aus dem Cache."""
        cache = await self._get_scenario_cache(company_id)

        if scenario_id not in cache:
            return None

        data = cache[scenario_id]

        return ScenarioResult(
            scenario_id=data["scenario_id"],
            scenario_type=ScenarioType(data["scenario_type"]),
            name=data["name"],
            description=data.get("description", ""),
            assumptions=[
                ScenarioAssumption(
                    name=a.get("name", ""),
                    description="",
                    parameter=a.get("parameter", ""),
                    value=a.get("value", 1.0),
                    unit=a.get("unit", ""),
                )
                for a in data.get("assumptions", [])
            ],
            forecast_days=data.get("forecast_days", 30),
            current_balance=data.get("current_balance", 0),
            min_balance=data.get("min_balance", 0),
            min_balance_date=data.get("min_balance_date", ""),
            max_balance=data.get("max_balance", 0),
            end_balance=data.get("end_balance", 0),
            total_inflows=data.get("total_inflows", 0),
            total_outflows=data.get("total_outflows", 0),
            daily_forecast=data.get("daily_forecast", []),
            risk_level=RiskLevel(data.get("risk_level", "low")),
            warnings=data.get("warnings", []),
            recommendations=data.get("recommendations", []),
            created_at=datetime.fromisoformat(data.get("created_at", "2026-01-01T00:00:00+00:00")),
        )

    async def _get_scenario_cache(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Holt den Szenario-Cache."""
        cache_key = f"{SCENARIO_CACHE_KEY}_{company_id}"

        query = select(AppConfig).where(AppConfig.key == cache_key)
        result = await self.db.execute(query)
        config = result.scalar_one_or_none()

        return config.value if config and config.value else {}


def get_liquidity_scenario_service(db: AsyncSession) -> LiquidityScenarioService:
    """Factory-Funktion fuer LiquidityScenarioService."""
    return LiquidityScenarioService(db)
