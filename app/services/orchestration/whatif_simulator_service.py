# -*- coding: utf-8 -*-
"""
What-If Simulator Service.

Enterprise Feature: Szenario-Simulation für finanzielle Entscheidungen.

"Was passiert wenn ich 500 EUR/Monat mehr spare?"
"Was passiert wenn der Zins um 2% steigt?"
"Was passiert wenn ich den Kredit jetzt tilge?"

Dieses Modul berechnet die Auswirkungen hypothetischer Änderungen auf:
- Financial Health Score
- Einzelne KPIs (DTI, Sparquote, Notgroschen, etc.)
- Langzeit-Prognosen (3, 6, 12, 24 Monate)
- Vergleich mit aktuellem Zustand

TRUE Enterprise-Level: Der User sieht die Zukunft BEVOR er handelt.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================

class ScenarioType(str, Enum):
    """Typ des Szenarios."""
    EXTRA_SAVINGS = "extra_savings"                 # Zusätzliche Sparrate
    EXTRA_PAYMENT = "extra_payment"                 # Zusätzliche Kredittilgung
    INCOME_CHANGE = "income_change"                 # Einkommensänderung
    EXPENSE_CHANGE = "expense_change"               # Ausgabenänderung
    INTEREST_RATE_CHANGE = "interest_rate_change"   # Zinssatzänderung
    ASSET_SALE = "asset_sale"                       # Vermoegensverkauf
    ASSET_PURCHASE = "asset_purchase"               # Vermoegenskauf
    LOAN_REFINANCE = "loan_refinance"               # Kredit-Refinanzierung
    INSURANCE_CHANGE = "insurance_change"           # Versicherungsänderung
    EMERGENCY_EXPENSE = "emergency_expense"         # Notfall-Ausgabe
    RENTAL_INCOME = "rental_income"                 # Mieteinnahmen
    TENANT_CHANGE = "tenant_change"                 # Mieterwechsel
    CUSTOM = "custom"                               # Benutzerdefiniert


class TimeHorizon(str, Enum):
    """Zeithorizont der Simulation."""
    IMMEDIATE = "immediate"     # Sofort
    THREE_MONTHS = "3_months"   # 3 Monate
    SIX_MONTHS = "6_months"     # 6 Monate
    ONE_YEAR = "1_year"         # 1 Jahr
    TWO_YEARS = "2_years"       # 2 Jahre
    FIVE_YEARS = "5_years"      # 5 Jahre


class ImpactSeverity(str, Enum):
    """Schweregrad des Impacts."""
    VERY_POSITIVE = "very_positive"   # Sehr positiv (> +20%)
    POSITIVE = "positive"             # Positiv (+5% bis +20%)
    NEUTRAL = "neutral"               # Neutral (-5% bis +5%)
    NEGATIVE = "negative"             # Negativ (-20% bis -5%)
    VERY_NEGATIVE = "very_negative"   # Sehr negativ (< -20%)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ScenarioInput:
    """Eingabeparameter für ein Szenario."""
    scenario_type: ScenarioType
    amount: Decimal = Decimal("0")              # Betrag in EUR
    percentage: float = 0.0                     # Prozentuale Änderung
    target_entity_id: Optional[UUID] = None     # Ziel-Entity (z.B. Kredit-ID)
    target_entity_type: Optional[str] = None    # Typ der Entity
    duration_months: int = 12                   # Dauer in Monaten
    start_date: Optional[datetime] = None       # Startdatum
    additional_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KPIProjection:
    """Projektion eines einzelnen KPI."""
    kpi_name: str
    current_value: float
    projected_value: float
    change_absolute: float
    change_percentage: float
    impact_severity: ImpactSeverity
    threshold_warning: Optional[str] = None     # Warnung bei Schwellenwert-Verletzung

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "kpi_name": self.kpi_name,
            "current_value": self.current_value,
            "projected_value": self.projected_value,
            "change_absolute": self.change_absolute,
            "change_percentage": self.change_percentage,
            "impact_severity": self.impact_severity.value,
            "threshold_warning": self.threshold_warning,
        }


@dataclass
class TimelinePoint:
    """Ein Punkt auf der Zeitleiste."""
    month: int
    date: datetime
    health_score: float
    key_kpis: Dict[str, float]
    events: List[str] = field(default_factory=list)  # Besondere Ereignisse

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "month": self.month,
            "date": self.date.isoformat(),
            "health_score": self.health_score,
            "key_kpis": self.key_kpis,
            "events": self.events,
        }


@dataclass
class ScenarioResult:
    """Ergebnis einer Szenario-Simulation."""
    scenario_id: UUID
    scenario_type: ScenarioType
    scenario_description: str

    # Aktueller Zustand
    current_health_score: float
    current_kpis: Dict[str, float]

    # Projizierter Zustand
    projected_health_score: float
    projected_kpis: List[KPIProjection]

    # Änderungen
    health_score_change: float
    health_score_change_percentage: float
    overall_impact_severity: ImpactSeverity

    # Zeitleiste
    timeline: List[TimelinePoint]

    # Finanzielle Auswirkungen
    total_cost: Decimal                         # Gesamtkosten der Aktion
    total_benefit: Decimal                      # Gesamtnutzen
    net_benefit: Decimal                        # Netto-Nutzen
    payback_months: Optional[int] = None        # Monate bis Amortisation

    # Risiken und Warnungen
    risks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)

    # Meta
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence_percentage: float = 85.0
    data_basis: str = "Aktuelle Daten"

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "scenario_id": str(self.scenario_id),
            "scenario_type": self.scenario_type.value,
            "scenario_description": self.scenario_description,
            "current_health_score": self.current_health_score,
            "current_kpis": self.current_kpis,
            "projected_health_score": self.projected_health_score,
            "projected_kpis": [kpi.to_dict() for kpi in self.projected_kpis],
            "health_score_change": self.health_score_change,
            "health_score_change_percentage": self.health_score_change_percentage,
            "overall_impact_severity": self.overall_impact_severity.value,
            "timeline": [tp.to_dict() for tp in self.timeline],
            "total_cost": float(self.total_cost),
            "total_benefit": float(self.total_benefit),
            "net_benefit": float(self.net_benefit),
            "payback_months": self.payback_months,
            "risks": self.risks,
            "warnings": self.warnings,
            "opportunities": self.opportunities,
            "calculated_at": self.calculated_at.isoformat(),
            "confidence_percentage": self.confidence_percentage,
            "data_basis": self.data_basis,
        }


@dataclass
class ComparisonResult:
    """Vergleich mehrerer Szenarien."""
    comparison_id: UUID
    scenarios: List[ScenarioResult]
    best_scenario_id: UUID
    best_scenario_reason: str
    ranking: List[Dict[str, Any]]  # Sortierte Liste nach Net-Benefit
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "comparison_id": str(self.comparison_id),
            "scenarios": [s.to_dict() for s in self.scenarios],
            "best_scenario_id": str(self.best_scenario_id),
            "best_scenario_reason": self.best_scenario_reason,
            "ranking": self.ranking,
            "recommendation": self.recommendation,
        }


# =============================================================================
# Simulator Templates (Szenario-spezifische Berechnungen)
# =============================================================================

class ScenarioTemplates:
    """Vorlagen für verschiedene Szenario-Typen."""

    @staticmethod
    def calculate_extra_savings_impact(
        current_kpis: Dict[str, float],
        monthly_amount: Decimal,
        duration_months: int
    ) -> Dict[str, Any]:
        """Berechnet Impact von zusätzlicher Sparrate."""
        current_savings_rate = current_kpis.get("savings_rate", 10.0)
        current_emergency_months = current_kpis.get("emergency_fund_months", 3.0)
        current_health = current_kpis.get("health_score", 70.0)
        monthly_income = current_kpis.get("monthly_income", 5000.0)

        # Neue Sparquote
        if monthly_income > 0:
            additional_savings_rate = (float(monthly_amount) / monthly_income) * 100
            new_savings_rate = min(current_savings_rate + additional_savings_rate, 50.0)
        else:
            new_savings_rate = current_savings_rate

        # Neuer Notgroschen (nach duration_months)
        total_extra_savings = float(monthly_amount) * duration_months
        monthly_expenses = current_kpis.get("monthly_expenses", 3000.0)
        if monthly_expenses > 0:
            additional_months = total_extra_savings / monthly_expenses
            new_emergency_months = current_emergency_months + additional_months
        else:
            new_emergency_months = current_emergency_months

        # Health Score Verbesserung
        savings_rate_improvement = (new_savings_rate - current_savings_rate) * 0.5
        emergency_fund_improvement = min((new_emergency_months - current_emergency_months) * 2, 15)
        health_improvement = savings_rate_improvement + emergency_fund_improvement
        new_health_score = min(current_health + health_improvement, 100.0)

        return {
            "new_kpis": {
                "savings_rate": new_savings_rate,
                "emergency_fund_months": new_emergency_months,
                "health_score": new_health_score,
            },
            "changes": {
                "savings_rate": new_savings_rate - current_savings_rate,
                "emergency_fund_months": new_emergency_months - current_emergency_months,
                "health_score": new_health_score - current_health,
            },
            "total_benefit": Decimal(str(total_extra_savings)),
            "total_cost": Decimal("0"),
            "risks": [],
            "opportunities": [
                f"Notgroschen waechst auf {new_emergency_months:.1f} Monate",
                f"Sparquote steigt auf {new_savings_rate:.1f}%",
            ],
        }

    @staticmethod
    def calculate_extra_payment_impact(
        current_kpis: Dict[str, float],
        payment_amount: Decimal,
        target_loan_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Berechnet Impact einer Sondertilgung."""
        current_dti = current_kpis.get("dti_ratio", 35.0)
        current_health = current_kpis.get("health_score", 70.0)
        total_debt = current_kpis.get("total_debt", 100000.0)
        monthly_income = current_kpis.get("monthly_income", 5000.0)

        # Neue Schulden
        new_total_debt = max(total_debt - float(payment_amount), 0)

        # Neues DTI
        if target_loan_data and target_loan_data.get("monthly_payment"):
            # Geschätzte Reduktion der monatlichen Rate
            loan_balance = target_loan_data.get("balance", total_debt)
            if loan_balance > 0:
                reduction_ratio = float(payment_amount) / loan_balance
                monthly_payment_reduction = target_loan_data["monthly_payment"] * reduction_ratio
                annual_income = monthly_income * 12
                if annual_income > 0:
                    dti_reduction = (monthly_payment_reduction * 12 / annual_income) * 100
                    new_dti = max(current_dti - dti_reduction, 0)
                else:
                    new_dti = current_dti
            else:
                new_dti = current_dti
        else:
            # Grobe Schätzung
            if total_debt > 0:
                reduction_ratio = float(payment_amount) / total_debt
                new_dti = current_dti * (1 - reduction_ratio * 0.8)  # Nicht linear
            else:
                new_dti = current_dti

        # Zinsersparnis schätzen (4% p.a. als Default)
        interest_rate = 0.04
        if target_loan_data and target_loan_data.get("interest_rate"):
            interest_rate = target_loan_data["interest_rate"] / 100

        # Ersparnis über Restlaufzeit (vereinfacht: 10 Jahre)
        remaining_years = target_loan_data.get("remaining_years", 10) if target_loan_data else 10
        interest_savings = float(payment_amount) * interest_rate * remaining_years

        # Health Score Verbesserung
        dti_improvement = (current_dti - new_dti) * 0.8  # DTI-Verbesserung stark gewichtet
        health_improvement = min(dti_improvement, 20)
        new_health_score = min(current_health + health_improvement, 100.0)

        return {
            "new_kpis": {
                "dti_ratio": new_dti,
                "total_debt": new_total_debt,
                "health_score": new_health_score,
            },
            "changes": {
                "dti_ratio": new_dti - current_dti,
                "total_debt": new_total_debt - total_debt,
                "health_score": new_health_score - current_health,
            },
            "total_benefit": Decimal(str(interest_savings)),
            "total_cost": payment_amount,
            "payback_months": None,  # Sofortige Auswirkung
            "risks": [
                "Liquiditaet kurzfristig reduziert",
            ] if float(payment_amount) > monthly_income * 3 else [],
            "opportunities": [
                f"DTI sinkt auf {new_dti:.1f}%",
                f"Zinsersparnis: ca. {interest_savings:,.0f} EUR über Restlaufzeit",
            ],
        }

    @staticmethod
    def calculate_interest_rate_change_impact(
        current_kpis: Dict[str, float],
        rate_change_percentage: float
    ) -> Dict[str, Any]:
        """Berechnet Impact einer Zinssatzänderung."""
        current_health = current_kpis.get("health_score", 70.0)
        total_debt = current_kpis.get("total_debt", 100000.0)
        current_dti = current_kpis.get("dti_ratio", 35.0)
        monthly_income = current_kpis.get("monthly_income", 5000.0)

        # Vereinfachte Berechnung: Wie ändert sich die monatliche Belastung?
        # Annahme: 15 Jahre Restlaufzeit, Annuitaetendarlehen
        current_rate = 0.04  # Annahme 4%
        new_rate = current_rate + (rate_change_percentage / 100)

        # Monatliche Rate Änderung (vereinfacht)
        # Bei 2% Zinserhöhung steigt Rate um ca. 10-15% je nach Tilgung
        rate_increase_factor = 1 + (rate_change_percentage / 100) * 3  # Approximation

        if rate_change_percentage > 0:
            # Zinsen steigen - negativ
            monthly_increase = (total_debt / 180) * (rate_increase_factor - 1)  # 180 = 15 Jahre
            annual_increase = monthly_increase * 12

            # DTI steigt
            if monthly_income > 0:
                dti_increase = (monthly_increase * 12 / (monthly_income * 12)) * 100
                new_dti = current_dti + dti_increase
            else:
                new_dti = current_dti

            health_change = -min(dti_increase * 0.5, 15)
            new_health = max(current_health + health_change, 20)

            return {
                "new_kpis": {
                    "dti_ratio": new_dti,
                    "health_score": new_health,
                },
                "changes": {
                    "dti_ratio": new_dti - current_dti,
                    "health_score": new_health - current_health,
                },
                "total_benefit": Decimal("0"),
                "total_cost": Decimal(str(annual_increase * 10)),  # 10 Jahre Mehrkosten
                "risks": [
                    f"DTI steigt auf {new_dti:.1f}%",
                    f"Jährliche Mehrbelastung: ca. {annual_increase:,.0f} EUR",
                ],
                "opportunities": [],
                "warnings": [
                    "Bei weiteren Zinserhöhungen könnte die Belastung kritisch werden",
                ],
            }
        else:
            # Zinsen sinken - positiv
            monthly_savings = abs((total_debt / 180) * (1 - rate_increase_factor))
            annual_savings = monthly_savings * 12

            if monthly_income > 0:
                dti_decrease = (monthly_savings * 12 / (monthly_income * 12)) * 100
                new_dti = max(current_dti - dti_decrease, 0)
            else:
                new_dti = current_dti

            health_change = min(dti_decrease * 0.5, 10)
            new_health = min(current_health + health_change, 100)

            return {
                "new_kpis": {
                    "dti_ratio": new_dti,
                    "health_score": new_health,
                },
                "changes": {
                    "dti_ratio": new_dti - current_dti,
                    "health_score": new_health - current_health,
                },
                "total_benefit": Decimal(str(annual_savings * 10)),
                "total_cost": Decimal("0"),
                "risks": [],
                "opportunities": [
                    f"DTI sinkt auf {new_dti:.1f}%",
                    f"Jährliche Ersparnis: ca. {annual_savings:,.0f} EUR",
                    "Refinanzierung prüfen!",
                ],
            }

    @staticmethod
    def calculate_income_change_impact(
        current_kpis: Dict[str, float],
        change_amount: Decimal,
        is_increase: bool
    ) -> Dict[str, Any]:
        """Berechnet Impact einer Einkommensänderung."""
        current_health = current_kpis.get("health_score", 70.0)
        monthly_income = current_kpis.get("monthly_income", 5000.0)
        current_dti = current_kpis.get("dti_ratio", 35.0)
        current_savings_rate = current_kpis.get("savings_rate", 10.0)
        monthly_expenses = current_kpis.get("monthly_expenses", 3000.0)

        if is_increase:
            new_income = monthly_income + float(change_amount)
        else:
            new_income = max(monthly_income - float(change_amount), 0)

        # DTI ändert sich
        if new_income > 0:
            current_debt_payment = (current_dti / 100) * monthly_income
            new_dti = (current_debt_payment / new_income) * 100
        else:
            new_dti = 100.0 if current_dti > 0 else 0.0

        # Sparquote bei Einkommensänderung
        if new_income > monthly_expenses:
            new_savings_potential = new_income - monthly_expenses
            new_savings_rate = (new_savings_potential / new_income) * 100
        else:
            new_savings_rate = 0.0

        # Health Score
        if is_increase:
            dti_improvement = max(current_dti - new_dti, 0)
            savings_improvement = max(new_savings_rate - current_savings_rate, 0) * 0.3
            health_change = min(dti_improvement * 0.5 + savings_improvement, 20)
        else:
            dti_worsening = max(new_dti - current_dti, 0)
            savings_worsening = max(current_savings_rate - new_savings_rate, 0) * 0.3
            health_change = -min(dti_worsening * 0.5 + savings_worsening, 25)

        new_health = max(min(current_health + health_change, 100), 20)

        annual_change = float(change_amount) * 12

        return {
            "new_kpis": {
                "monthly_income": new_income,
                "dti_ratio": new_dti,
                "savings_rate": new_savings_rate,
                "health_score": new_health,
            },
            "changes": {
                "monthly_income": new_income - monthly_income,
                "dti_ratio": new_dti - current_dti,
                "savings_rate": new_savings_rate - current_savings_rate,
                "health_score": new_health - current_health,
            },
            "total_benefit": Decimal(str(annual_change)) if is_increase else Decimal("0"),
            "total_cost": Decimal(str(abs(annual_change))) if not is_increase else Decimal("0"),
            "risks": [] if is_increase else [
                f"DTI steigt auf {new_dti:.1f}%",
                f"Sparquote faellt auf {new_savings_rate:.1f}%",
            ],
            "opportunities": [
                f"DTI sinkt auf {new_dti:.1f}%",
                f"Sparquote steigt auf {new_savings_rate:.1f}%",
            ] if is_increase else [],
        }


# =============================================================================
# What-If Simulator Service
# =============================================================================

class WhatIfSimulatorService:
    """
    Service für What-If Szenario-Simulationen.

    Ermöglicht dem User, hypothetische Szenarien durchzuspielen und
    deren Auswirkungen auf die finanzielle Gesundheit zu sehen.

    Singleton-Pattern für globalen Zugriff.
    """

    _instance: Optional["WhatIfSimulatorService"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "WhatIfSimulatorService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._simulation_cache: Dict[str, ScenarioResult] = {}
        self._cache_lock = asyncio.Lock()
        self._templates = ScenarioTemplates()
        self._initialized = True

        logger.info("what_if_simulator_initialized")

    async def simulate_scenario(
        self,
        scenario_input: ScenarioInput,
        current_kpis: Dict[str, float],
        user_id: Optional[UUID] = None,
    ) -> ScenarioResult:
        """
        Simuliert ein einzelnes Szenario.

        Args:
            scenario_input: Eingabeparameter des Szenarios
            current_kpis: Aktuelle KPI-Werte
            user_id: Optional User-ID für Caching

        Returns:
            ScenarioResult mit allen Projektionen und Analysen
        """
        scenario_id = uuid4()

        logger.info(
            "simulating_scenario",
            scenario_id=str(scenario_id),
            scenario_type=scenario_input.scenario_type.value,
            amount=float(scenario_input.amount),
        )

        # Szenario-spezifische Berechnung
        impact_data = await self._calculate_impact(scenario_input, current_kpis)

        # KPI-Projektionen erstellen
        projected_kpis = self._create_kpi_projections(
            current_kpis,
            impact_data.get("new_kpis", {}),
            impact_data.get("changes", {}),
        )

        # Zeitleiste generieren
        timeline = await self._generate_timeline(
            current_kpis,
            impact_data,
            scenario_input.duration_months,
        )

        # Health Score Änderung
        current_health = current_kpis.get("health_score", 70.0)
        new_health = impact_data.get("new_kpis", {}).get("health_score", current_health)
        health_change = new_health - current_health
        health_change_pct = (health_change / current_health * 100) if current_health > 0 else 0

        # Impact Severity bestimmen
        overall_severity = self._determine_impact_severity(health_change_pct)

        # Beschreibung generieren
        description = self._generate_scenario_description(scenario_input)

        # Payback-Periode berechnen (falls zutreffend)
        payback_months = self._calculate_payback(
            impact_data.get("total_cost", Decimal("0")),
            impact_data.get("total_benefit", Decimal("0")),
            scenario_input.duration_months,
        )

        result = ScenarioResult(
            scenario_id=scenario_id,
            scenario_type=scenario_input.scenario_type,
            scenario_description=description,
            current_health_score=current_health,
            current_kpis=current_kpis,
            projected_health_score=new_health,
            projected_kpis=projected_kpis,
            health_score_change=health_change,
            health_score_change_percentage=health_change_pct,
            overall_impact_severity=overall_severity,
            timeline=timeline,
            total_cost=impact_data.get("total_cost", Decimal("0")),
            total_benefit=impact_data.get("total_benefit", Decimal("0")),
            net_benefit=impact_data.get("total_benefit", Decimal("0")) - impact_data.get("total_cost", Decimal("0")),
            payback_months=payback_months,
            risks=impact_data.get("risks", []),
            warnings=impact_data.get("warnings", []),
            opportunities=impact_data.get("opportunities", []),
            confidence_percentage=self._calculate_confidence(scenario_input, current_kpis),
            data_basis=self._determine_data_basis(current_kpis),
        )

        # Cache speichern
        async with self._cache_lock:
            cache_key = f"{user_id}:{scenario_id}" if user_id else str(scenario_id)
            self._simulation_cache[cache_key] = result

        logger.info(
            "scenario_simulated",
            scenario_id=str(scenario_id),
            health_change=health_change,
            net_benefit=float(result.net_benefit),
        )

        return result

    async def compare_scenarios(
        self,
        scenarios: List[ScenarioInput],
        current_kpis: Dict[str, float],
        user_id: Optional[UUID] = None,
    ) -> ComparisonResult:
        """
        Vergleicht mehrere Szenarien miteinander.

        Args:
            scenarios: Liste von Szenario-Eingaben
            current_kpis: Aktuelle KPI-Werte
            user_id: Optional User-ID

        Returns:
            ComparisonResult mit Ranking und Empfehlung
        """
        comparison_id = uuid4()

        logger.info(
            "comparing_scenarios",
            comparison_id=str(comparison_id),
            scenario_count=len(scenarios),
        )

        # Alle Szenarien simulieren
        results: List[ScenarioResult] = []
        for scenario in scenarios:
            result = await self.simulate_scenario(scenario, current_kpis, user_id)
            results.append(result)

        # Ranking nach Net-Benefit
        ranked = sorted(results, key=lambda r: float(r.net_benefit), reverse=True)

        ranking = [
            {
                "rank": i + 1,
                "scenario_id": str(r.scenario_id),
                "scenario_type": r.scenario_type.value,
                "description": r.scenario_description,
                "health_score_change": r.health_score_change,
                "net_benefit": float(r.net_benefit),
                "impact_severity": r.overall_impact_severity.value,
            }
            for i, r in enumerate(ranked)
        ]

        # Bestes Szenario
        best = ranked[0]
        best_reason = self._generate_best_scenario_reason(best, ranked)

        # Empfehlung
        recommendation = self._generate_comparison_recommendation(ranked)

        return ComparisonResult(
            comparison_id=comparison_id,
            scenarios=results,
            best_scenario_id=best.scenario_id,
            best_scenario_reason=best_reason,
            ranking=ranking,
            recommendation=recommendation,
        )

    async def simulate_combined_scenarios(
        self,
        scenarios: List[ScenarioInput],
        current_kpis: Dict[str, float],
        user_id: Optional[UUID] = None,
    ) -> ScenarioResult:
        """
        Simuliert mehrere Szenarien KOMBINIERT (nicht vergleichend).

        Z.B.: "Was passiert wenn ich 300 EUR mehr spare UND den Kredit schneller tilge?"
        """
        combined_id = uuid4()

        # Iterativ die Szenarien anwenden
        running_kpis = current_kpis.copy()
        total_cost = Decimal("0")
        total_benefit = Decimal("0")
        all_risks: List[str] = []
        all_opportunities: List[str] = []
        all_warnings: List[str] = []

        for scenario in scenarios:
            impact_data = await self._calculate_impact(scenario, running_kpis)

            # KPIs aktualisieren
            new_kpis = impact_data.get("new_kpis", {})
            for key, value in new_kpis.items():
                running_kpis[key] = value

            total_cost += impact_data.get("total_cost", Decimal("0"))
            total_benefit += impact_data.get("total_benefit", Decimal("0"))
            all_risks.extend(impact_data.get("risks", []))
            all_opportunities.extend(impact_data.get("opportunities", []))
            all_warnings.extend(impact_data.get("warnings", []))

        # Finale Projektionen
        current_health = current_kpis.get("health_score", 70.0)
        final_health = running_kpis.get("health_score", current_health)
        health_change = final_health - current_health

        projected_kpis = self._create_kpi_projections(
            current_kpis,
            running_kpis,
            {k: running_kpis.get(k, 0) - current_kpis.get(k, 0) for k in running_kpis},
        )

        # Beschreibung für kombiniertes Szenario
        descriptions = [self._generate_scenario_description(s) for s in scenarios]
        combined_description = " + ".join(descriptions)

        max_duration = max(s.duration_months for s in scenarios)
        timeline = await self._generate_timeline(
            current_kpis,
            {"new_kpis": running_kpis, "changes": {k: running_kpis.get(k, 0) - current_kpis.get(k, 0) for k in running_kpis}},
            max_duration,
        )

        return ScenarioResult(
            scenario_id=combined_id,
            scenario_type=ScenarioType.CUSTOM,
            scenario_description=f"Kombiniert: {combined_description}",
            current_health_score=current_health,
            current_kpis=current_kpis,
            projected_health_score=final_health,
            projected_kpis=projected_kpis,
            health_score_change=health_change,
            health_score_change_percentage=(health_change / current_health * 100) if current_health > 0 else 0,
            overall_impact_severity=self._determine_impact_severity(health_change),
            timeline=timeline,
            total_cost=total_cost,
            total_benefit=total_benefit,
            net_benefit=total_benefit - total_cost,
            risks=list(set(all_risks)),  # Deduplizieren
            warnings=list(set(all_warnings)),
            opportunities=list(set(all_opportunities)),
            confidence_percentage=75.0,  # Kombinierte Szenarien haben weniger Konfidenz
            data_basis="Kombinierte Szenario-Analyse",
        )

    async def get_quick_scenarios(
        self,
        current_kpis: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        Gibt vordefinierte Quick-Szenarien zurück basierend auf aktuellen KPIs.

        Intelligent: Schlaegt relevante Szenarien basierend auf der aktuellen Situation vor.
        """
        scenarios = []

        # Basierend auf DTI
        dti = current_kpis.get("dti_ratio", 35.0)
        if dti > 30:
            scenarios.append({
                "id": "reduce_dti",
                "title": "Schulden reduzieren",
                "description": f"DTI ist {dti:.1f}% - Sondertilgung simulieren",
                "scenario_type": ScenarioType.EXTRA_PAYMENT.value,
                "suggested_amount": 5000,
                "expected_impact": "DTI -3-5%, Health Score +5-10",
            })

        # Basierend auf Notgroschen
        emergency_months = current_kpis.get("emergency_fund_months", 3.0)
        if emergency_months < 6:
            scenarios.append({
                "id": "build_emergency_fund",
                "title": "Notgroschen aufbauen",
                "description": f"Nur {emergency_months:.1f} Monate Reserve - mehr sparen",
                "scenario_type": ScenarioType.EXTRA_SAVINGS.value,
                "suggested_amount": 300,
                "expected_impact": f"Notgroschen +{12 * 300 / current_kpis.get('monthly_expenses', 3000):.1f} Monate",
            })

        # Basierend auf Sparquote
        savings_rate = current_kpis.get("savings_rate", 10.0)
        if savings_rate < 15:
            scenarios.append({
                "id": "increase_savings",
                "title": "Sparquote erhöhen",
                "description": f"Sparquote nur {savings_rate:.1f}% - Ziel 15-20%",
                "scenario_type": ScenarioType.EXTRA_SAVINGS.value,
                "suggested_amount": 200,
                "expected_impact": "Sparquote +3-5%, Health Score +3-5",
            })

        # Zins-Szenario (immer relevant)
        scenarios.append({
            "id": "interest_increase",
            "title": "Zinsanstieg +2%",
            "description": "Was passiert bei steigenden Zinsen?",
            "scenario_type": ScenarioType.INTEREST_RATE_CHANGE.value,
            "suggested_percentage": 2.0,
            "expected_impact": "Stresstest für Finanzierung",
        })

        # Einkommensausfall
        scenarios.append({
            "id": "income_loss",
            "title": "Einkommensausfall 20%",
            "description": "Resilienz bei Einkommensrückgang testen",
            "scenario_type": ScenarioType.INCOME_CHANGE.value,
            "suggested_percentage": -20.0,
            "expected_impact": "Stresstest für Haushaltsbudget",
        })

        return scenarios

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    async def _calculate_impact(
        self,
        scenario: ScenarioInput,
        current_kpis: Dict[str, float],
    ) -> Dict[str, Any]:
        """Berechnet den Impact basierend auf Szenario-Typ."""
        if scenario.scenario_type == ScenarioType.EXTRA_SAVINGS:
            return self._templates.calculate_extra_savings_impact(
                current_kpis,
                scenario.amount,
                scenario.duration_months,
            )

        elif scenario.scenario_type == ScenarioType.EXTRA_PAYMENT:
            return self._templates.calculate_extra_payment_impact(
                current_kpis,
                scenario.amount,
                scenario.additional_params.get("loan_data"),
            )

        elif scenario.scenario_type == ScenarioType.INTEREST_RATE_CHANGE:
            return self._templates.calculate_interest_rate_change_impact(
                current_kpis,
                scenario.percentage,
            )

        elif scenario.scenario_type == ScenarioType.INCOME_CHANGE:
            is_increase = scenario.amount > 0 or scenario.percentage > 0
            if scenario.amount != Decimal("0"):
                change_amount = abs(scenario.amount)
            else:
                monthly_income = current_kpis.get("monthly_income", 5000.0)
                change_amount = Decimal(str(abs(scenario.percentage) / 100 * monthly_income))

            return self._templates.calculate_income_change_impact(
                current_kpis,
                change_amount,
                is_increase,
            )

        # Fallback für andere Typen
        return {
            "new_kpis": current_kpis.copy(),
            "changes": {},
            "total_benefit": Decimal("0"),
            "total_cost": Decimal("0"),
            "risks": [],
            "opportunities": [],
        }

    def _create_kpi_projections(
        self,
        current: Dict[str, float],
        new: Dict[str, float],
        changes: Dict[str, float],
    ) -> List[KPIProjection]:
        """Erstellt KPI-Projektionen."""
        projections = []

        kpi_labels = {
            "health_score": "Financial Health Score",
            "dti_ratio": "Debt-to-Income Ratio",
            "savings_rate": "Sparquote",
            "emergency_fund_months": "Notgroschen (Monate)",
            "total_debt": "Gesamtschulden",
            "monthly_income": "Monatseinkommen",
        }

        for kpi_name in new.keys():
            if kpi_name not in current:
                continue

            current_val = current.get(kpi_name, 0)
            new_val = new.get(kpi_name, current_val)
            change_abs = changes.get(kpi_name, new_val - current_val)

            if current_val != 0:
                change_pct = (change_abs / current_val) * 100
            else:
                change_pct = 100 if change_abs > 0 else (-100 if change_abs < 0 else 0)

            severity = self._determine_kpi_impact_severity(kpi_name, change_pct)

            # Schwellenwert-Warnung
            warning = None
            if kpi_name == "dti_ratio" and new_val > 40:
                warning = "Kritisch: DTI über 40%"
            elif kpi_name == "emergency_fund_months" and new_val < 3:
                warning = "Warnung: Weniger als 3 Monate Reserve"
            elif kpi_name == "savings_rate" and new_val < 5:
                warning = "Warnung: Sparquote unter 5%"

            projections.append(KPIProjection(
                kpi_name=kpi_labels.get(kpi_name, kpi_name),
                current_value=current_val,
                projected_value=new_val,
                change_absolute=change_abs,
                change_percentage=change_pct,
                impact_severity=severity,
                threshold_warning=warning,
            ))

        return projections

    async def _generate_timeline(
        self,
        current_kpis: Dict[str, float],
        impact_data: Dict[str, Any],
        duration_months: int,
    ) -> List[TimelinePoint]:
        """Generiert eine Zeitleiste der Entwicklung."""
        timeline = []
        now = datetime.now(timezone.utc)

        current_health = current_kpis.get("health_score", 70.0)
        target_health = impact_data.get("new_kpis", {}).get("health_score", current_health)
        health_change = target_health - current_health

        # Lineare Interpolation (vereinfacht)
        for month in range(0, min(duration_months + 1, 25), 3):  # Alle 3 Monate, max 24
            progress = month / duration_months if duration_months > 0 else 1
            interpolated_health = current_health + (health_change * progress)

            # Key KPIs interpolieren
            key_kpis = {}
            for kpi_name in ["dti_ratio", "savings_rate", "emergency_fund_months"]:
                if kpi_name in current_kpis:
                    current_val = current_kpis[kpi_name]
                    target_val = impact_data.get("new_kpis", {}).get(kpi_name, current_val)
                    key_kpis[kpi_name] = current_val + ((target_val - current_val) * progress)

            events = []
            if month == 0:
                events.append("Start des Szenarios")
            elif month == duration_months:
                events.append("Ziel erreicht")

            timeline.append(TimelinePoint(
                month=month,
                date=now + timedelta(days=30 * month),
                health_score=interpolated_health,
                key_kpis=key_kpis,
                events=events,
            ))

        return timeline

    def _determine_impact_severity(self, change_percentage: float) -> ImpactSeverity:
        """Bestimmt die Schwere des Impacts."""
        if change_percentage > 20:
            return ImpactSeverity.VERY_POSITIVE
        elif change_percentage > 5:
            return ImpactSeverity.POSITIVE
        elif change_percentage >= -5:
            return ImpactSeverity.NEUTRAL
        elif change_percentage >= -20:
            return ImpactSeverity.NEGATIVE
        else:
            return ImpactSeverity.VERY_NEGATIVE

    def _determine_kpi_impact_severity(
        self,
        kpi_name: str,
        change_percentage: float,
    ) -> ImpactSeverity:
        """Bestimmt Impact-Severity für spezifische KPIs."""
        # Bei DTI ist eine SENKUNG positiv
        if kpi_name == "dti_ratio":
            return self._determine_impact_severity(-change_percentage)

        # Bei Schulden ist eine SENKUNG positiv
        if kpi_name == "total_debt":
            return self._determine_impact_severity(-change_percentage)

        # Standard: Erhöhung ist positiv
        return self._determine_impact_severity(change_percentage)

    def _generate_scenario_description(self, scenario: ScenarioInput) -> str:
        """Generiert eine menschenlesbare Beschreibung."""
        descriptions = {
            ScenarioType.EXTRA_SAVINGS: f"{scenario.amount:,.0f} EUR/Monat zusätzlich sparen",
            ScenarioType.EXTRA_PAYMENT: f"{scenario.amount:,.0f} EUR Sondertilgung",
            ScenarioType.INCOME_CHANGE: f"Einkommen {'erhöht' if scenario.amount > 0 or scenario.percentage > 0 else 'reduziert'} um {abs(scenario.percentage):.1f}%" if scenario.percentage else f"Einkommen ändert sich um {scenario.amount:,.0f} EUR",
            ScenarioType.INTEREST_RATE_CHANGE: f"Zinssatz {'steigt' if scenario.percentage > 0 else 'sinkt'} um {abs(scenario.percentage):.2f}%",
            ScenarioType.ASSET_SALE: f"Vermoegensverkauf: {scenario.amount:,.0f} EUR",
            ScenarioType.LOAN_REFINANCE: "Kredit-Refinanzierung",
        }

        return descriptions.get(
            scenario.scenario_type,
            f"{scenario.scenario_type.value}: {scenario.amount:,.0f} EUR"
        )

    def _calculate_payback(
        self,
        total_cost: Decimal,
        total_benefit: Decimal,
        duration_months: int,
    ) -> Optional[int]:
        """Berechnet Payback-Periode in Monaten."""
        if total_cost <= 0:
            return None

        if total_benefit <= 0:
            return None

        if total_benefit <= total_cost:
            return None

        monthly_benefit = total_benefit / Decimal(str(duration_months))
        if monthly_benefit > 0:
            payback_months = int(total_cost / monthly_benefit)
            return min(payback_months, 120)  # Max 10 Jahre

        return None

    def _calculate_confidence(
        self,
        scenario: ScenarioInput,
        current_kpis: Dict[str, float],
    ) -> float:
        """Berechnet Konfidenz-Prozentsatz."""
        base_confidence = 85.0

        # Weniger Konfidenz bei längeren Zeithorizonten
        if scenario.duration_months > 24:
            base_confidence -= 10
        elif scenario.duration_months > 12:
            base_confidence -= 5

        # Mehr Konfidenz bei vollständigen Daten
        required_kpis = ["health_score", "dti_ratio", "savings_rate", "monthly_income"]
        available = sum(1 for k in required_kpis if k in current_kpis)
        data_completeness_factor = available / len(required_kpis)
        base_confidence *= data_completeness_factor

        return min(max(base_confidence, 50.0), 95.0)

    def _determine_data_basis(self, current_kpis: Dict[str, float]) -> str:
        """Bestimmt die Datenbasis-Beschreibung."""
        kpi_count = len(current_kpis)
        if kpi_count >= 10:
            return "Vollständige Finanzdaten"
        elif kpi_count >= 5:
            return "Basis-Finanzdaten"
        else:
            return "Begrenzte Datenbasis"

    def _generate_best_scenario_reason(
        self,
        best: ScenarioResult,
        all_ranked: List[ScenarioResult],
    ) -> str:
        """Generiert Begruendung für bestes Szenario."""
        if len(all_ranked) == 1:
            return "Einziges analysiertes Szenario"

        second_best = all_ranked[1] if len(all_ranked) > 1 else None

        reasons = []
        reasons.append(f"Hoechster Netto-Nutzen: {float(best.net_benefit):,.0f} EUR")

        if best.health_score_change > 0:
            reasons.append(f"Health Score +{best.health_score_change:.1f} Punkte")

        if second_best:
            advantage = float(best.net_benefit - second_best.net_benefit)
            if advantage > 0:
                reasons.append(f"{advantage:,.0f} EUR besser als nächste Alternative")

        return "; ".join(reasons)

    def _generate_comparison_recommendation(
        self,
        ranked: List[ScenarioResult],
    ) -> str:
        """Generiert Vergleichs-Empfehlung."""
        if not ranked:
            return "Keine Szenarien zum Vergleichen"

        best = ranked[0]

        if best.overall_impact_severity in [ImpactSeverity.VERY_POSITIVE, ImpactSeverity.POSITIVE]:
            return f"Empfehlung: '{best.scenario_description}' mit {float(best.net_benefit):,.0f} EUR Netto-Nutzen und Health Score Verbesserung von {best.health_score_change:.1f} Punkten."
        elif best.overall_impact_severity == ImpactSeverity.NEUTRAL:
            return f"Alle Szenarien haben ähnliche Auswirkungen. '{best.scenario_description}' hat leichten Vorteil."
        else:
            return f"Achtung: Alle Szenarien haben negative Auswirkungen. Wenn noetig, wähle '{best.scenario_description}' als geringstes Uebel."


# =============================================================================
# Singleton Accessor
# =============================================================================

_simulator_instance: Optional[WhatIfSimulatorService] = None
_simulator_lock = threading.Lock()


def get_whatif_simulator() -> WhatIfSimulatorService:
    """Gibt die Singleton-Instanz des What-If Simulators zurück."""
    global _simulator_instance
    with _simulator_lock:
        if _simulator_instance is None:
            _simulator_instance = WhatIfSimulatorService()
        return _simulator_instance
