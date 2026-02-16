# -*- coding: utf-8 -*-
"""
RetirementService - Altersvorsorge-Planung für das Privat-Modul.

Bietet umfassende Funktionen für:
1. Rentenlücken-Berechnung (gesetzlich + privat + betrieblich)
2. Entnahmestrategien (4%-Regel, dynamisch, Floor-and-Ceiling)
3. Monte-Carlo-Simulation für Portfolio-Langlebigkeit
4. Rentenoptimierungsempfehlungen
5. Integration des deutschen Rentensystems (DRV, Riester, Ruerup, bAV)

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
SECURITY: NIEMALS persoenliche Daten oder Betraege loggen!
"""

from __future__ import annotations

import threading
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from enum import Enum

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

RETIREMENT_CALCULATIONS = Counter(
    "retirement_calculations_total",
    "Anzahl der Altersvorsorge-Berechnungen",
    ["calculation_type"]
)

RETIREMENT_DURATION = Histogram(
    "retirement_duration_seconds",
    "Dauer der Altersvorsorge-Berechnung",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)


# =============================================================================
# Deutsche Rentenversicherung - Konstanten (Stand 2026)
# =============================================================================

class PensionType(str, Enum):
    """Typen von Altersvorsorge."""
    GESETZLICH = "gesetzlich"  # Deutsche Rentenversicherung
    RIESTER = "riester"  # Riester-Rente
    RUERUP = "ruerup"  # Basisrente/Ruerup
    BAV = "bav"  # Betriebliche Altersvorsorge
    PRIVATE = "private"  # Private Rentenversicherung
    DEPOT = "depot"  # Depot/ETF-Sparplan
    IMMOBILIE = "immobilie"  # Mietfreies Wohnen / Mieteinnahmen


class WithdrawalStrategy(str, Enum):
    """Entnahmestrategien."""
    FIXED_PERCENTAGE = "fixed_percentage"  # 4%-Regel
    DYNAMIC = "dynamic"  # Dynamisch nach Marktlage
    FLOOR_CEILING = "floor_ceiling"  # Min/Max-Grenzen
    GUYTON_KLINGER = "guyton_klinger"  # Guyton-Klinger Decision Rules
    VPW = "vpw"  # Variable Percentage Withdrawal


class RiskProfile(str, Enum):
    """Risikoprofil für Simulationen."""
    KONSERVATIV = "konservativ"
    AUSGEWOGEN = "ausgewogen"
    WACHSTUM = "wachstum"


# Aktueller Rentenwert (West, Stand 2026 geschätzt)
RENTENWERT_AKTUELL = Decimal("39.32")  # EUR pro Entgeltpunkt

# Regelaltersgrenze (nach Geburtsjahr)
REGELALTERSGRENZE = {
    1958: 66,
    1959: 66 + 2/12,  # 66 Jahre 2 Monate
    1960: 66 + 4/12,
    1961: 66 + 6/12,
    1962: 66 + 8/12,
    1963: 66 + 10/12,
    1964: 67,  # Ab 1964 geboren: 67 Jahre
}

# Beitragsbemessungsgrenze (BBG) West 2026 geschätzt
BBG_WEST_JAEHRLICH = Decimal("96600")
BBG_WEST_MONATLICH = Decimal("8050")

# Durchschnittsentgelt 2026 geschätzt (für Entgeltpunkte)
DURCHSCHNITTSENTGELT = Decimal("47950")

# Riester-Zulagen
RIESTER_GRUNDZULAGE = Decimal("175")
RIESTER_KINDERZULAGE_AB_2008 = Decimal("300")
RIESTER_KINDERZULAGE_VOR_2008 = Decimal("185")
RIESTER_MAX_EIGENBEITRAG = Decimal("2100")

# Ruerup-Hoechstbetrag 2026
RUERUP_HOECHSTBETRAG_SINGLE = Decimal("27566")
RUERUP_HOECHSTBETRAG_VERHEIRATET = Decimal("55132")

# bAV-Grenzen
BAV_STEUERFREIER_BEITRAG = Decimal("3864")  # 4% BBG (geschätzt)
BAV_PAUSCHALVERSTEUERUNGSGRENZE = Decimal("2040")

# Monte-Carlo Parameter
MC_DEFAULT_ITERATIONS = 1000
MC_HISTORICAL_RETURNS = {
    RiskProfile.KONSERVATIV: {"mean": Decimal("0.04"), "std": Decimal("0.06")},
    RiskProfile.AUSGEWOGEN: {"mean": Decimal("0.06"), "std": Decimal("0.12")},
    RiskProfile.WACHSTUM: {"mean": Decimal("0.08"), "std": Decimal("0.18")},
}
MC_INFLATION_MEAN = Decimal("0.02")
MC_INFLATION_STD = Decimal("0.01")


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PensionSource:
    """Eine Quelle für Renteneinkommen."""
    pension_type: PensionType
    name: str
    current_value: Decimal  # Aktueller Wert / angesammeltes Kapital
    expected_monthly_benefit: Decimal  # Erwartete monatliche Rente
    guaranteed_monthly_benefit: Optional[Decimal] = None  # Garantierte Leistung
    start_age: int = 67
    annual_contribution: Decimal = Decimal("0")
    employer_contribution: Decimal = Decimal("0")  # Bei bAV
    tax_treatment: str = "nachgelagert"  # vorgelagert/nachgelagert/steuerfrei
    notes: Optional[str] = None


@dataclass
class PensionPoint:
    """Entgeltpunkt der gesetzlichen Rentenversicherung."""
    year: int
    gross_income: Decimal
    points_earned: Decimal
    contribution_months: int = 12


@dataclass
class RentenlueckeResult:
    """Ergebnis der Rentenlücken-Analyse."""
    space_id: UUID
    current_age: int
    retirement_age: int
    years_until_retirement: int

    # Ziel-Einkommen
    target_monthly_income: Decimal
    target_replacement_ratio: Decimal  # z.B. 80% des letzten Nettos

    # Prognostizierte Renten
    expected_statutory_pension: Decimal  # DRV
    expected_riester: Decimal
    expected_ruerup: Decimal
    expected_bav: Decimal
    expected_private: Decimal
    expected_investment_income: Decimal  # Aus Depot

    total_expected_pension: Decimal
    pension_gap: Decimal
    pension_gap_yearly: Decimal

    # Kapitallücke
    capital_needed_for_gap: Decimal
    current_savings: Decimal
    additional_savings_needed: Decimal
    monthly_savings_required: Decimal

    # Entgeltpunkte (DRV)
    current_pension_points: Decimal
    projected_pension_points: Decimal

    recommendations: List[str]
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WithdrawalPlan:
    """Entnahmeplan für den Ruhestand."""
    strategy: WithdrawalStrategy
    initial_portfolio: Decimal
    annual_withdrawal_rate: Decimal
    initial_annual_withdrawal: Decimal
    inflation_adjusted: bool

    # Jahres-Projektion
    yearly_projections: List[Dict[str, Any]]

    # Risikometriken
    success_probability: Decimal  # Aus Monte-Carlo
    median_end_portfolio: Decimal
    worst_case_end_portfolio: Decimal
    best_case_end_portfolio: Decimal

    # Empfehlungen
    safe_withdrawal_rate: Decimal
    recommendations: List[str]


@dataclass
class MonteCarloResult:
    """Ergebnis der Monte-Carlo-Simulation."""
    iterations: int
    time_horizon_years: int
    initial_portfolio: Decimal
    annual_withdrawal: Decimal

    # Statistiken
    success_rate: Decimal  # % Simulationen mit positivem End-Portfolio
    median_end_portfolio: Decimal
    percentile_5: Decimal  # 5%-Quantil (Worst Case)
    percentile_95: Decimal  # 95%-Quantil (Best Case)
    mean_end_portfolio: Decimal
    std_dev: Decimal

    # Detaillierte Verteilung
    portfolio_paths: List[List[Decimal]]  # Für Visualisierung

    recommendations: List[str]


@dataclass
class RiesterOptimization:
    """Riester-Optimierungsempfehlung."""
    eligible: bool
    optimal_eigenbeitrag: Decimal
    total_zulagen: Decimal
    grundzulage: Decimal
    kinderzulagen: Decimal
    tax_benefit: Decimal
    net_cost: Decimal  # Eigenbeitrag - Steuerersparnis
    effective_return_boost: Decimal  # Zulagen/Eigenbeitrag
    recommendations: List[str]


@dataclass
class BAVAnalysis:
    """Analyse der betrieblichen Altersvorsorge."""
    current_contribution: Decimal
    employer_match: Decimal
    employer_match_percent: Decimal
    total_contribution: Decimal

    # Steuer-/SV-Ersparnis
    tax_savings: Decimal
    social_security_savings: Decimal
    total_immediate_benefit: Decimal

    # Projektion
    projected_capital_at_retirement: Decimal
    projected_monthly_pension: Decimal

    # Optimierung
    optimal_contribution: Decimal
    max_tax_free_contribution: Decimal
    additional_employer_match_available: bool
    recommendations: List[str]


@dataclass
class RetirementSummary:
    """Vollständige Altersvorsorge-Zusammenfassung."""
    space_id: UUID
    current_age: int
    target_retirement_age: int

    # Rentenlücke
    pension_gap_analysis: RentenlueckeResult

    # Entnahmeplanung
    withdrawal_plan: Optional[WithdrawalPlan]

    # Monte-Carlo
    monte_carlo_result: Optional[MonteCarloResult]

    # Optimierungen
    riester_analysis: Optional[RiesterOptimization]
    bav_analysis: Optional[BAVAnalysis]

    # Gesamtbewertung
    retirement_readiness_score: Decimal  # 0-100
    overall_rating: str  # "gut", "ausreichend", "kritisch"
    priority_actions: List[str]

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Singleton Service
# =============================================================================

class RetirementService:
    """
    Singleton Service für Altersvorsorge-Planung.

    Berechnet Rentenlücken, führt Monte-Carlo-Simulationen durch
    und optimiert die Altersvorsorge-Strategie.

    SECURITY: NIEMALS persoenliche Daten oder Betraege loggen!
    """

    _instance: Optional["RetirementService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "RetirementService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info("retirement_service_initialized")

    # =========================================================================
    # Entgeltpunkte-Berechnung (DRV)
    # =========================================================================

    def calculate_pension_points(
        self,
        gross_annual_income: Decimal,
        year: int = 2026,
    ) -> Decimal:
        """
        Berechnet Entgeltpunkte für ein Jahr.

        Formel: Bruttoeinkommen / Durchschnittsentgelt
        Max: Einkommen bis BBG.
        """
        # Begrenzung auf Beitragsbemessungsgrenze
        relevant_income = min(gross_annual_income, BBG_WEST_JAEHRLICH)

        # Entgeltpunkte berechnen
        points = (relevant_income / DURCHSCHNITTSENTGELT).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )

        return points

    def calculate_statutory_pension(
        self,
        total_pension_points: Decimal,
        zugangsfaktor: Decimal = Decimal("1.0"),
        rentenartfaktor: Decimal = Decimal("1.0"),  # Altersrente = 1.0
    ) -> Decimal:
        """
        Berechnet die monatliche gesetzliche Rente.

        Rentenformel: EP x ZF x RAF x aRW
        - EP: Entgeltpunkte
        - ZF: Zugangsfaktor (1.0 = Regelalter, <1 = Frührente)
        - RAF: Rentenartfaktor (Altersrente = 1.0)
        - aRW: Aktueller Rentenwert
        """
        monthly_pension = (
            total_pension_points *
            zugangsfaktor *
            rentenartfaktor *
            RENTENWERT_AKTUELL
        ).quantize(Decimal("0.01"), ROUND_HALF_UP)

        return monthly_pension

    def calculate_early_retirement_factor(
        self,
        months_early: int,
    ) -> Decimal:
        """Berechnet den Abschlag bei Frühverrentung."""
        # 0.3% Abschlag pro Monat, max. 14.4% (48 Monate)
        max_months = 48
        effective_months = min(months_early, max_months)
        deduction = Decimal(str(effective_months)) * Decimal("0.003")
        return Decimal("1.0") - deduction

    def project_pension_points(
        self,
        current_age: int,
        retirement_age: int,
        current_points: Decimal,
        annual_income: Decimal,
    ) -> Decimal:
        """Projiziert Entgeltpunkte bis zur Rente."""
        years_remaining = max(0, retirement_age - current_age)

        future_points = Decimal("0")
        for _ in range(years_remaining):
            future_points += self.calculate_pension_points(annual_income)

        return current_points + future_points

    # =========================================================================
    # Rentenlücken-Analyse
    # =========================================================================

    async def analyze_pension_gap(
        self,
        db: AsyncSession,
        space_id: UUID,
        birth_date: date,
        current_gross_annual_income: Decimal,
        target_replacement_ratio: Decimal = Decimal("0.80"),
        current_pension_points: Decimal = Decimal("0"),
        pension_sources: Optional[List[PensionSource]] = None,
        retirement_age: Optional[int] = None,
    ) -> RentenlueckeResult:
        """
        Analysiert die Rentenlücke und gibt Handlungsempfehlungen.

        Args:
            space_id: Space-ID
            birth_date: Geburtsdatum
            current_gross_annual_income: Aktuelles Bruttojahreseinkommen
            target_replacement_ratio: Ziel-Ersatzquote (Standard: 80%)
            current_pension_points: Bereits erworbene Entgeltpunkte
            pension_sources: Vorhandene Rentenquellen
            retirement_age: Geplantes Rentenalter (Standard: Regelalter)

        SECURITY: Keine Betraege oder persoenliche Daten loggen!
        """
        import time
        start_time = time.time()

        RETIREMENT_CALCULATIONS.labels(calculation_type="pension_gap").inc()

        if pension_sources is None:
            pension_sources = []

        # Alter berechnen
        today = date.today()
        current_age = (today - birth_date).days // 365

        # Regelaltersgrenze bestimmen
        birth_year = birth_date.year
        if retirement_age is None:
            retirement_age = REGELALTERSGRENZE.get(birth_year, 67)
            # Auf ganze Jahre runden
            retirement_age = int(retirement_age)

        years_until_retirement = max(0, retirement_age - current_age)

        # Nettoeinkommen schätzen (vereinfacht: 60% des Brutto)
        current_net_monthly = (current_gross_annual_income * Decimal("0.6") / 12).quantize(
            Decimal("0.01")
        )

        target_monthly_income = (current_net_monthly * target_replacement_ratio).quantize(
            Decimal("0.01")
        )

        # Gesetzliche Rente projizieren
        projected_points = self.project_pension_points(
            current_age, retirement_age, current_pension_points, current_gross_annual_income
        )
        expected_statutory = self.calculate_statutory_pension(projected_points)

        # Andere Rentenquellen summieren
        expected_riester = sum(
            p.expected_monthly_benefit for p in pension_sources
            if p.pension_type == PensionType.RIESTER
        )
        expected_ruerup = sum(
            p.expected_monthly_benefit for p in pension_sources
            if p.pension_type == PensionType.RUERUP
        )
        expected_bav = sum(
            p.expected_monthly_benefit for p in pension_sources
            if p.pension_type == PensionType.BAV
        )
        expected_private = sum(
            p.expected_monthly_benefit for p in pension_sources
            if p.pension_type == PensionType.PRIVATE
        )

        # Investment-Einkommen (4% Regel auf Depot)
        depot_value = sum(
            p.current_value for p in pension_sources
            if p.pension_type == PensionType.DEPOT
        )
        # Projektion: 6% jährliche Rendite bis Rente
        if years_until_retirement > 0 and depot_value > 0:
            projected_depot = depot_value * (Decimal("1.06") ** years_until_retirement)
        else:
            projected_depot = depot_value
        expected_investment = (projected_depot * Decimal("0.04") / 12).quantize(Decimal("0.01"))

        # Gesamt und Lücke
        total_expected = (
            expected_statutory +
            expected_riester +
            expected_ruerup +
            expected_bav +
            expected_private +
            expected_investment
        )

        pension_gap = max(Decimal("0"), target_monthly_income - total_expected)
        pension_gap_yearly = pension_gap * 12

        # Kapitallücke berechnen (25x Regel für 4% Entnahme)
        capital_needed = pension_gap * 12 * 25

        # Aktuelle Ersparnisse
        current_savings = sum(p.current_value for p in pension_sources)

        additional_needed = max(Decimal("0"), capital_needed - projected_depot)

        # Monatliche Sparrate berechnen
        if years_until_retirement > 0:
            # Vereinfacht: Annuitaetenformel mit 6% Rendite
            r = Decimal("0.06") / 12  # Monatliche Rendite
            n = years_until_retirement * 12  # Monate

            if r > 0:
                # FV = PMT * ((1+r)^n - 1) / r
                # PMT = FV * r / ((1+r)^n - 1)
                factor = ((1 + r) ** n - 1) / r
                monthly_savings_required = (additional_needed / factor).quantize(Decimal("0.01"))
            else:
                monthly_savings_required = additional_needed / n
        else:
            monthly_savings_required = Decimal("0")

        # Empfehlungen generieren
        recommendations = self._generate_pension_recommendations(
            pension_gap, current_age, years_until_retirement,
            expected_statutory, pension_sources
        )

        duration = time.time() - start_time
        RETIREMENT_DURATION.observe(duration)

        logger.info(
            "pension_gap_analysis_completed",
            space_id=str(space_id),
            current_age=current_age,
            retirement_age=retirement_age,
            duration_seconds=round(duration, 3),
        )

        return RentenlueckeResult(
            space_id=space_id,
            current_age=current_age,
            retirement_age=retirement_age,
            years_until_retirement=years_until_retirement,
            target_monthly_income=target_monthly_income,
            target_replacement_ratio=target_replacement_ratio,
            expected_statutory_pension=expected_statutory,
            expected_riester=expected_riester,
            expected_ruerup=expected_ruerup,
            expected_bav=expected_bav,
            expected_private=expected_private,
            expected_investment_income=expected_investment,
            total_expected_pension=total_expected,
            pension_gap=pension_gap,
            pension_gap_yearly=pension_gap_yearly,
            capital_needed_for_gap=capital_needed,
            current_savings=current_savings,
            additional_savings_needed=additional_needed,
            monthly_savings_required=monthly_savings_required,
            current_pension_points=current_pension_points,
            projected_pension_points=projected_points,
            recommendations=recommendations,
        )

    def _generate_pension_recommendations(
        self,
        gap: Decimal,
        age: int,
        years_remaining: int,
        statutory_pension: Decimal,
        sources: List[PensionSource],
    ) -> List[str]:
        """Generiert Empfehlungen zur Rentenoptimierung."""
        recommendations: List[str] = []

        if gap <= 0:
            recommendations.append(
                "Glückwunsch! Ihre prognostizierte Rente deckt Ihren Zielbedarf."
            )
            return recommendations

        # Riester-Empfehlung
        has_riester = any(s.pension_type == PensionType.RIESTER for s in sources)
        if not has_riester and age < 55:
            recommendations.append(
                "Riester-Rente prüfen: Staatliche Zulagen und Steuervorteile "
                "können die Rendite deutlich erhöhen."
            )

        # bAV-Empfehlung
        has_bav = any(s.pension_type == PensionType.BAV for s in sources)
        if not has_bav:
            recommendations.append(
                "Betriebliche Altersvorsorge: Steuer- und SV-Ersparnis sowie "
                "oft Arbeitgeber-Zuschuss nutzen."
            )

        # ETF-Sparplan
        has_depot = any(s.pension_type == PensionType.DEPOT for s in sources)
        if not has_depot and years_remaining > 10:
            recommendations.append(
                "ETF-Sparplan empfohlen: Bei langem Anlagehorizont bieten "
                "breit gestreute ETFs attraktive Renditechancen."
            )

        # Zusätzliche Entgeltpunkte
        if statutory_pension < Decimal("1500"):
            recommendations.append(
                "Gesetzliche Rente steigern: Freiwillige Beitraege oder "
                "Ausgleichszahlungen für Abschlaege prüfen."
            )

        # Immobilie
        recommendations.append(
            "Mietfreies Wohnen: Eigentum kann im Alter die Ausgaben "
            "um 500-1.000 EUR monatlich reduzieren."
        )

        # Sparrate erhöhen
        if years_remaining > 5:
            recommendations.append(
                f"Sparquote erhöhen: Jeder zusätzliche Euro bringt durch "
                f"den Zinseszins-Effekt über {years_remaining} Jahre erheblichen Mehrwert."
            )

        return recommendations[:5]

    # =========================================================================
    # Entnahmestrategien
    # =========================================================================

    def create_withdrawal_plan(
        self,
        initial_portfolio: Decimal,
        annual_withdrawal_rate: Decimal = Decimal("0.04"),
        time_horizon_years: int = 30,
        strategy: WithdrawalStrategy = WithdrawalStrategy.FIXED_PERCENTAGE,
        inflation_adjusted: bool = True,
        risk_profile: RiskProfile = RiskProfile.AUSGEWOGEN,
        floor_rate: Optional[Decimal] = None,
        ceiling_rate: Optional[Decimal] = None,
    ) -> WithdrawalPlan:
        """
        Erstellt einen Entnahmeplan für den Ruhestand.

        Args:
            initial_portfolio: Startvermoegen
            annual_withdrawal_rate: Jährliche Entnahmerate (z.B. 0.04 = 4%)
            time_horizon_years: Planungshorizont in Jahren
            strategy: Entnahmestrategie
            inflation_adjusted: Inflation berücksichtigen
            risk_profile: Risikoprofil
            floor_rate: Minimale Entnahmerate (für Floor-Ceiling)
            ceiling_rate: Maximale Entnahmerate (für Floor-Ceiling)
        """
        RETIREMENT_CALCULATIONS.labels(calculation_type="withdrawal_plan").inc()

        initial_withdrawal = (initial_portfolio * annual_withdrawal_rate).quantize(
            Decimal("0.01")
        )

        # Jahres-Projektion berechnen
        projections = self._project_withdrawals(
            initial_portfolio,
            initial_withdrawal,
            time_horizon_years,
            strategy,
            inflation_adjusted,
            risk_profile,
            floor_rate,
            ceiling_rate,
        )

        # Monte-Carlo für Erfolgswahrscheinlichkeit
        mc_result = self.run_monte_carlo(
            initial_portfolio,
            initial_withdrawal,
            time_horizon_years,
            risk_profile,
        )

        # Sichere Entnahmerate berechnen
        safe_rate = self._calculate_safe_withdrawal_rate(
            initial_portfolio,
            time_horizon_years,
            risk_profile,
        )

        # Empfehlungen
        recommendations = []

        if mc_result.success_rate < Decimal("90"):
            recommendations.append(
                f"Achtung: Erfolgswahrscheinlichkeit nur {mc_result.success_rate}%. "
                f"Reduzieren Sie die Entnahmerate auf {safe_rate * 100:.1f}%."
            )

        if strategy == WithdrawalStrategy.FIXED_PERCENTAGE:
            recommendations.append(
                "Tipp: Dynamische Strategien können bei Markteinbruechen "
                "das Portfolio-Überleben verbessern."
            )

        if time_horizon_years > 35:
            recommendations.append(
                "Langer Planungshorizont: Berücksichtigen Sie Langlebigkeitsrisiko. "
                "Konservativere Entnahme empfohlen."
            )

        return WithdrawalPlan(
            strategy=strategy,
            initial_portfolio=initial_portfolio,
            annual_withdrawal_rate=annual_withdrawal_rate,
            initial_annual_withdrawal=initial_withdrawal,
            inflation_adjusted=inflation_adjusted,
            yearly_projections=projections,
            success_probability=mc_result.success_rate,
            median_end_portfolio=mc_result.median_end_portfolio,
            worst_case_end_portfolio=mc_result.percentile_5,
            best_case_end_portfolio=mc_result.percentile_95,
            safe_withdrawal_rate=safe_rate,
            recommendations=recommendations,
        )

    def _project_withdrawals(
        self,
        portfolio: Decimal,
        initial_withdrawal: Decimal,
        years: int,
        strategy: WithdrawalStrategy,
        inflation_adjusted: bool,
        risk_profile: RiskProfile,
        floor_rate: Optional[Decimal],
        ceiling_rate: Optional[Decimal],
    ) -> List[Dict[str, Any]]:
        """Projiziert Entnahmen Jahr für Jahr (deterministische Berechnung)."""
        projections = []
        current_portfolio = portfolio
        current_withdrawal = initial_withdrawal

        returns = MC_HISTORICAL_RETURNS[risk_profile]
        expected_return = returns["mean"]
        inflation = MC_INFLATION_MEAN

        for year in range(1, years + 1):
            if current_portfolio <= 0:
                break

            # Entnahme am Jahresanfang
            if strategy == WithdrawalStrategy.FIXED_PERCENTAGE:
                withdrawal = current_withdrawal
            elif strategy == WithdrawalStrategy.DYNAMIC:
                # Dynamisch: Basierend auf aktuellem Portfolio
                withdrawal = (current_portfolio * Decimal("0.04")).quantize(Decimal("0.01"))
            elif strategy == WithdrawalStrategy.FLOOR_CEILING:
                base_rate = Decimal("0.04")
                actual_rate = max(
                    floor_rate or Decimal("0.03"),
                    min(ceiling_rate or Decimal("0.05"), base_rate)
                )
                withdrawal = (current_portfolio * actual_rate).quantize(Decimal("0.01"))
            else:
                withdrawal = current_withdrawal

            # Portfolio nach Entnahme
            portfolio_after_withdrawal = current_portfolio - withdrawal

            # Rendite (deterministisch: erwarteter Wert)
            portfolio_end = (portfolio_after_withdrawal * (1 + expected_return)).quantize(
                Decimal("0.01")
            )

            projections.append({
                "year": year,
                "portfolio_start": str(current_portfolio),
                "withdrawal": str(withdrawal),
                "portfolio_after_withdrawal": str(portfolio_after_withdrawal),
                "expected_return": str(expected_return * 100) + "%",
                "portfolio_end": str(portfolio_end),
            })

            current_portfolio = portfolio_end

            # Inflation-Anpassung für nächstes Jahr
            if inflation_adjusted:
                current_withdrawal = (current_withdrawal * (1 + inflation)).quantize(
                    Decimal("0.01")
                )

        return projections

    def _calculate_safe_withdrawal_rate(
        self,
        portfolio: Decimal,
        years: int,
        risk_profile: RiskProfile,
    ) -> Decimal:
        """Berechnet die sichere Entnahmerate für 95% Erfolg."""
        # Binaeere Suche nach Rate mit 95% Erfolg
        low = Decimal("0.02")
        high = Decimal("0.08")

        for _ in range(10):  # Max 10 Iterationen
            mid = (low + high) / 2
            withdrawal = portfolio * mid

            mc_result = self.run_monte_carlo(
                portfolio, withdrawal, years, risk_profile, iterations=200
            )

            if mc_result.success_rate >= Decimal("95"):
                low = mid
            else:
                high = mid

        return low.quantize(Decimal("0.001"))

    # =========================================================================
    # Monte-Carlo-Simulation
    # =========================================================================

    def run_monte_carlo(
        self,
        initial_portfolio: Decimal,
        annual_withdrawal: Decimal,
        time_horizon_years: int,
        risk_profile: RiskProfile = RiskProfile.AUSGEWOGEN,
        iterations: int = MC_DEFAULT_ITERATIONS,
        inflation_adjusted: bool = True,
    ) -> MonteCarloResult:
        """
        Führt Monte-Carlo-Simulation für Portfolio-Langlebigkeit durch.

        Simuliert verschiedene Marktszenarien basierend auf historischen
        Renditeverteilungen.
        """
        RETIREMENT_CALCULATIONS.labels(calculation_type="monte_carlo").inc()

        returns_params = MC_HISTORICAL_RETURNS[risk_profile]
        mean_return = float(returns_params["mean"])
        std_return = float(returns_params["std"])
        mean_inflation = float(MC_INFLATION_MEAN)
        std_inflation = float(MC_INFLATION_STD)

        end_portfolios: List[Decimal] = []
        success_count = 0
        sample_paths: List[List[Decimal]] = []

        for i in range(iterations):
            portfolio = float(initial_portfolio)
            withdrawal = float(annual_withdrawal)

            path = [Decimal(str(portfolio))]

            for year in range(time_horizon_years):
                if portfolio <= 0:
                    path.append(Decimal("0"))
                    continue

                # Entnahme
                portfolio -= withdrawal

                if portfolio <= 0:
                    path.append(Decimal("0"))
                    continue

                # Zufällige Rendite (normalverteilt)
                annual_return = random.gauss(mean_return, std_return)
                portfolio *= (1 + annual_return)

                path.append(Decimal(str(max(0, portfolio))).quantize(Decimal("0.01")))

                # Inflation-Anpassung der Entnahme
                if inflation_adjusted:
                    inflation = random.gauss(mean_inflation, std_inflation)
                    withdrawal *= (1 + max(0, inflation))

            end_value = Decimal(str(max(0, portfolio))).quantize(Decimal("0.01"))
            end_portfolios.append(end_value)

            if portfolio > 0:
                success_count += 1

            # Sample-Pfade für Visualisierung (max 50)
            if i < 50:
                sample_paths.append(path)

        # Statistiken berechnen
        end_portfolios_sorted = sorted(end_portfolios)
        n = len(end_portfolios_sorted)

        success_rate = Decimal(str(success_count / iterations * 100)).quantize(Decimal("0.1"))
        median_idx = n // 2
        p5_idx = max(0, int(n * 0.05))
        p95_idx = min(n - 1, int(n * 0.95))

        median_end = end_portfolios_sorted[median_idx]
        percentile_5 = end_portfolios_sorted[p5_idx]
        percentile_95 = end_portfolios_sorted[p95_idx]

        mean_end = sum(end_portfolios) / len(end_portfolios)

        # Standardabweichung
        variance = sum((x - mean_end) ** 2 for x in end_portfolios) / len(end_portfolios)
        std_dev = Decimal(str(variance ** Decimal("0.5"))).quantize(Decimal("0.01"))

        # Empfehlungen
        recommendations = []

        if success_rate < Decimal("80"):
            recommendations.append(
                "KRITISCH: Hohe Wahrscheinlichkeit, dass das Portfolio "
                "vor Lebensende aufgebraucht ist."
            )
        elif success_rate < Decimal("90"):
            recommendations.append(
                "WARNUNG: Moderate Erfolgswahrscheinlichkeit. "
                "Entnahmerate reduzieren oder Risikoprofil anpassen."
            )

        if percentile_5 <= 0:
            recommendations.append(
                "Im schlechtesten Szenario (5%-Quantil) ist das Portfolio aufgebraucht."
            )

        return MonteCarloResult(
            iterations=iterations,
            time_horizon_years=time_horizon_years,
            initial_portfolio=initial_portfolio,
            annual_withdrawal=annual_withdrawal,
            success_rate=success_rate,
            median_end_portfolio=median_end,
            percentile_5=percentile_5,
            percentile_95=percentile_95,
            mean_end_portfolio=mean_end.quantize(Decimal("0.01")),
            std_dev=std_dev,
            portfolio_paths=sample_paths,
            recommendations=recommendations,
        )

    # =========================================================================
    # Riester-Optimierung
    # =========================================================================

    def optimize_riester(
        self,
        gross_annual_income: Decimal,
        marginal_tax_rate: Decimal,
        children_born_after_2007: int = 0,
        children_born_before_2008: int = 0,
        current_riester_contribution: Decimal = Decimal("0"),
    ) -> RiesterOptimization:
        """Optimiert die Riester-Beitraege für maximale Foerderung."""
        RETIREMENT_CALCULATIONS.labels(calculation_type="riester_optimization").inc()

        # Mindestbeitrag für volle Zulage: 4% des Vorjahres-Brutto, min. 60 EUR
        min_eigenbeitrag_fuer_volle_zulage = max(
            Decimal("60"),
            (gross_annual_income * Decimal("0.04")).quantize(Decimal("0.01"))
        )

        # Zulagen berechnen
        grundzulage = RIESTER_GRUNDZULAGE
        kinderzulage = (
            children_born_after_2007 * RIESTER_KINDERZULAGE_AB_2008 +
            children_born_before_2008 * RIESTER_KINDERZULAGE_VOR_2008
        )
        total_zulagen = grundzulage + kinderzulage

        # Optimaler Eigenbeitrag = Min-Beitrag abzueglich Zulagen
        optimal_eigenbeitrag = max(
            Decimal("60"),
            min_eigenbeitrag_fuer_volle_zulage - total_zulagen
        )

        # Begrenzung auf Hoechstbetrag
        optimal_eigenbeitrag = min(optimal_eigenbeitrag, RIESTER_MAX_EIGENBEITRAG - total_zulagen)

        # Sonderausgabenabzug prüfen
        gesamt_altersvorsorgeaufwendungen = optimal_eigenbeitrag + total_zulagen

        # Steuerersparnis (vereinfacht)
        tax_benefit = (gesamt_altersvorsorgeaufwendungen * marginal_tax_rate).quantize(
            Decimal("0.01")
        )

        # Effektive Nettokosten
        net_cost = optimal_eigenbeitrag - tax_benefit

        # Zulagen-Rendite
        effective_boost = Decimal("0")
        if optimal_eigenbeitrag > 0:
            effective_boost = ((total_zulagen / optimal_eigenbeitrag) * 100).quantize(
                Decimal("0.1")
            )

        recommendations = []

        if current_riester_contribution < optimal_eigenbeitrag:
            recommendations.append(
                f"Optimierung: Erhöhen Sie Ihren Riester-Beitrag auf "
                f"{optimal_eigenbeitrag:.2f} EUR/Jahr für volle Zulagen."
            )

        if kinderzulage > 0:
            recommendations.append(
                f"Kinderzulagen: Sie erhalten {kinderzulage:.2f} EUR/Jahr extra."
            )

        if tax_benefit > total_zulagen:
            recommendations.append(
                "Steuerersparnis übersteigt Zulagen - Sonderausgabenabzug vorteilhafter."
            )

        return RiesterOptimization(
            eligible=True,
            optimal_eigenbeitrag=optimal_eigenbeitrag,
            total_zulagen=total_zulagen,
            grundzulage=grundzulage,
            kinderzulagen=kinderzulage,
            tax_benefit=tax_benefit,
            net_cost=net_cost,
            effective_return_boost=effective_boost,
            recommendations=recommendations,
        )

    # =========================================================================
    # bAV-Analyse
    # =========================================================================

    def analyze_bav(
        self,
        current_contribution: Decimal,
        employer_match_percent: Decimal,
        employer_match_cap: Optional[Decimal] = None,
        marginal_tax_rate: Decimal = Decimal("0.35"),
        social_security_rate: Decimal = Decimal("0.20"),
        years_until_retirement: int = 20,
    ) -> BAVAnalysis:
        """Analysiert und optimiert die betriebliche Altersvorsorge."""
        RETIREMENT_CALCULATIONS.labels(calculation_type="bav_analysis").inc()

        # Arbeitgeber-Match berechnen
        employer_match = (current_contribution * employer_match_percent / 100).quantize(
            Decimal("0.01")
        )
        if employer_match_cap:
            employer_match = min(employer_match, employer_match_cap)

        total_contribution = current_contribution + employer_match

        # Steuer- und SV-Ersparnis (auf Arbeitnehmer-Beitrag)
        tax_savings = (current_contribution * marginal_tax_rate).quantize(Decimal("0.01"))

        # SV-Ersparnis nur bis zur Beitragsbemessungsgrenze
        sv_relevant = min(current_contribution, BAV_STEUERFREIER_BEITRAG)
        social_security_savings = (sv_relevant * social_security_rate).quantize(Decimal("0.01"))

        total_immediate_benefit = tax_savings + social_security_savings

        # Projektion mit 4% Rendite
        projected_capital = total_contribution * 12
        for _ in range(years_until_retirement):
            projected_capital = projected_capital * Decimal("1.04") + total_contribution * 12

        # Monatliche Rente (vereinfacht: 4% Entnahmerate)
        projected_monthly_pension = (projected_capital * Decimal("0.04") / 12).quantize(
            Decimal("0.01")
        )

        # Optimaler Beitrag = Steuerfreier Beitrag voll ausschoepfen
        optimal_contribution = BAV_STEUERFREIER_BEITRAG
        additional_match_available = employer_match < (employer_match_cap or Decimal("999999"))

        recommendations = []

        if current_contribution < BAV_STEUERFREIER_BEITRAG:
            recommendations.append(
                f"Empfehlung: Erhöhen Sie auf {BAV_STEUERFREIER_BEITRAG:.2f} EUR/Jahr "
                "für maximale Steuerersparnis."
            )

        if additional_match_available:
            recommendations.append(
                "Arbeitgeber-Match nicht ausgeschoepft - Beitrag erhöhen lohnt sich!"
            )

        if employer_match_percent == 0:
            recommendations.append(
                "Kein Arbeitgeber-Zuschuss? Fragen Sie nach - oft gibt es 15% oder mehr."
            )

        return BAVAnalysis(
            current_contribution=current_contribution,
            employer_match=employer_match,
            employer_match_percent=employer_match_percent,
            total_contribution=total_contribution,
            tax_savings=tax_savings,
            social_security_savings=social_security_savings,
            total_immediate_benefit=total_immediate_benefit,
            projected_capital_at_retirement=projected_capital,
            projected_monthly_pension=projected_monthly_pension,
            optimal_contribution=optimal_contribution,
            max_tax_free_contribution=BAV_STEUERFREIER_BEITRAG,
            additional_employer_match_available=additional_match_available,
            recommendations=recommendations,
        )

    # =========================================================================
    # Vollständige Analyse
    # =========================================================================

    async def generate_retirement_summary(
        self,
        db: AsyncSession,
        space_id: UUID,
        birth_date: date,
        current_gross_annual_income: Decimal,
        pension_sources: Optional[List[PensionSource]] = None,
        risk_profile: RiskProfile = RiskProfile.AUSGEWOGEN,
        target_retirement_age: Optional[int] = None,
        children_born_after_2007: int = 0,
        children_born_before_2008: int = 0,
    ) -> RetirementSummary:
        """
        Generiert eine vollständige Altersvorsorge-Zusammenfassung.

        SECURITY: Keine persoenlichen Daten oder Betraege loggen!
        """
        import time
        start_time = time.time()

        RETIREMENT_CALCULATIONS.labels(calculation_type="full_summary").inc()

        if pension_sources is None:
            pension_sources = []

        current_age = (date.today() - birth_date).days // 365

        # 1. Rentenlücke analysieren
        gap_analysis = await self.analyze_pension_gap(
            db, space_id, birth_date,
            current_gross_annual_income,
            pension_sources=pension_sources,
            retirement_age=target_retirement_age,
        )

        # 2. Entnahmeplanung (falls Depot vorhanden)
        depot_value = sum(
            p.current_value for p in pension_sources
            if p.pension_type == PensionType.DEPOT
        )

        withdrawal_plan = None
        mc_result = None

        if depot_value > 0 and gap_analysis.years_until_retirement <= 5:
            withdrawal_plan = self.create_withdrawal_plan(
                depot_value,
                annual_withdrawal_rate=Decimal("0.04"),
                time_horizon_years=30,
                risk_profile=risk_profile,
            )
            mc_result = self.run_monte_carlo(
                depot_value,
                depot_value * Decimal("0.04"),
                30,
                risk_profile,
            )

        # 3. Riester-Analyse
        marginal_rate = Decimal("0.35")  # Geschätzt
        riester_analysis = self.optimize_riester(
            current_gross_annual_income,
            marginal_rate,
            children_born_after_2007,
            children_born_before_2008,
        )

        # 4. bAV-Analyse
        current_bav = next(
            (p for p in pension_sources if p.pension_type == PensionType.BAV),
            None
        )
        bav_contribution = current_bav.annual_contribution if current_bav else Decimal("0")
        bav_match = Decimal("15")  # Standard-Zuschuss geschätzt

        bav_analysis = self.analyze_bav(
            bav_contribution,
            bav_match,
            years_until_retirement=gap_analysis.years_until_retirement,
        )

        # 5. Retirement Readiness Score berechnen
        readiness_score = self._calculate_readiness_score(
            gap_analysis, withdrawal_plan, riester_analysis, bav_analysis
        )

        # 6. Rating bestimmen
        if readiness_score >= 80:
            rating = "gut"
        elif readiness_score >= 60:
            rating = "ausreichend"
        else:
            rating = "kritisch"

        # 7. Prioritätsaktionen
        priority_actions = self._generate_priority_actions(
            gap_analysis, readiness_score, pension_sources
        )

        duration = time.time() - start_time
        RETIREMENT_DURATION.observe(duration)

        logger.info(
            "retirement_summary_generated",
            space_id=str(space_id),
            current_age=current_age,
            readiness_score=str(readiness_score),
            rating=rating,
            duration_seconds=round(duration, 3),
        )

        return RetirementSummary(
            space_id=space_id,
            current_age=current_age,
            target_retirement_age=gap_analysis.retirement_age,
            pension_gap_analysis=gap_analysis,
            withdrawal_plan=withdrawal_plan,
            monte_carlo_result=mc_result,
            riester_analysis=riester_analysis,
            bav_analysis=bav_analysis,
            retirement_readiness_score=readiness_score,
            overall_rating=rating,
            priority_actions=priority_actions,
        )

    def _calculate_readiness_score(
        self,
        gap_analysis: RentenlueckeResult,
        withdrawal_plan: Optional[WithdrawalPlan],
        riester: RiesterOptimization,
        bav: BAVAnalysis,
    ) -> Decimal:
        """Berechnet den Retirement Readiness Score (0-100)."""
        score = Decimal("50")  # Basis

        # Rentenlücke (max 40 Punkte)
        if gap_analysis.pension_gap <= 0:
            score += Decimal("40")
        elif gap_analysis.target_monthly_income > 0:
            coverage = gap_analysis.total_expected_pension / gap_analysis.target_monthly_income
            score += min(Decimal("40"), coverage * 40)

        # Entnahmeplan Erfolg (max 20 Punkte)
        if withdrawal_plan:
            success_factor = withdrawal_plan.success_probability / 100
            score += success_factor * 20

        # Riester genutzt (max 10 Punkte)
        if riester.optimal_eigenbeitrag > 0 and riester.effective_return_boost > 0:
            score += Decimal("10")

        # bAV optimiert (max 10 Punkte)
        if bav.current_contribution >= bav.optimal_contribution:
            score += Decimal("10")
        elif bav.current_contribution > 0:
            score += Decimal("5")

        # Diversifikation (implizit durch multiple Quellen)

        return min(Decimal("100"), max(Decimal("0"), score)).quantize(Decimal("0.1"))

    def _generate_priority_actions(
        self,
        gap_analysis: RentenlueckeResult,
        score: Decimal,
        sources: List[PensionSource],
    ) -> List[str]:
        """Generiert priorisierte Handlungsempfehlungen."""
        actions = []

        if score < 50:
            actions.append(
                "DRINGEND: Altersvorsorge stark ausbaufähig. "
                "Erhöhen Sie Ihre Sparquote sofort."
            )

        if gap_analysis.pension_gap > Decimal("500"):
            actions.append(
                f"Rentenlücke von {gap_analysis.pension_gap:.0f} EUR/Monat schließen: "
                "Zusätzliche Vorsorge aufbauen."
            )

        if gap_analysis.monthly_savings_required > Decimal("500"):
            actions.append(
                f"Sparrate um {gap_analysis.monthly_savings_required:.0f} EUR/Monat erhöhen "
                "oder Renteneintritt verschieben."
            )

        has_riester = any(s.pension_type == PensionType.RIESTER for s in sources)
        if not has_riester:
            actions.append("Riester-Vertrag abschließen für staatliche Zulagen.")

        has_bav = any(s.pension_type == PensionType.BAV for s in sources)
        if not has_bav:
            actions.append("Betriebliche Altersvorsorge beim Arbeitgeber anfragen.")

        if gap_analysis.years_until_retirement > 20:
            has_etf = any(s.pension_type == PensionType.DEPOT for s in sources)
            if not has_etf:
                actions.append("ETF-Sparplan starten für langfristigen Vermoegensaufbau.")

        return actions[:5]


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_retirement_service() -> RetirementService:
    """Gibt die Singleton-Instanz des Retirement Service zurück."""
    return RetirementService()
