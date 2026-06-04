# -*- coding: utf-8 -*-
"""
FinancialHealthService - Berechnet den Financial Health Score.

Berechnet automatisch einen Gesundheits-Score (0-100) basierend auf:
1. Vermoegens-Trend (Net Worth Wachstum)
2. Schulden-Management (Debt-to-Income Ratio)
3. Risiko-Abdeckung (Versicherungs-Adaequanz)
4. Liquiditaet (Notgroschen-Reserve)
5. Altersvorsorge (Retirement Readiness)
6. Diversifikation (Portfolio-Streuung)

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from enum import Enum

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

HEALTH_SCORE_CALCULATIONS = Counter(
    "financial_health_calculations_total",
    "Anzahl der Financial Health Berechnungen",
    ["calculation_type"]
)

HEALTH_SCORE_DURATION = Histogram(
    "financial_health_duration_seconds",
    "Dauer der Financial Health Berechnung",
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

HEALTH_SCORE_GAUGE = Gauge(
    "financial_health_score",
    "Aktueller Financial Health Score",
    ["space_id"]
)


# =============================================================================
# Konstanten und Referenzwerte
# =============================================================================

# Gewichtung der einzelnen Dimensionen (summe = 100)
DIMENSION_WEIGHTS = {
    "net_worth_trend": Decimal("20"),
    "debt_management": Decimal("20"),
    "risk_coverage": Decimal("15"),
    "liquidity": Decimal("15"),
    "retirement_readiness": Decimal("15"),
    "diversification": Decimal("15"),
}

# Empfohlene Notgroschen-Monate
RECOMMENDED_EMERGENCY_MONTHS = 6

# Empfohlene maximale Schulden-Quote (Debt-to-Income)
MAX_HEALTHY_DTI_RATIO = Decimal("0.36")  # 36%

# Empfohlene Versicherungs-Typen
ESSENTIAL_INSURANCE_TYPES = [
    "haftpflicht",
    "privathaftpflicht",
    "hausrat",
    "berufsunfähigkeit",
    "krankenversicherung",
    "kfz_haftpflicht",
]

# Altersvorsorge-Multiplikatoren (Empfohlen: Jahresgehalt * Alter / 10)
RETIREMENT_FACTOR_BY_AGE = {
    25: Decimal("0.5"),   # 0.5x Jahresgehalt mit 25
    30: Decimal("1.0"),   # 1x mit 30
    35: Decimal("2.0"),   # 2x mit 35
    40: Decimal("3.0"),   # 3x mit 40
    45: Decimal("4.0"),   # 4x mit 45
    50: Decimal("5.0"),   # 5x mit 50
    55: Decimal("6.0"),   # 6x mit 55
    60: Decimal("7.0"),   # 7x mit 60
    65: Decimal("8.0"),   # 8x mit 65
}


class HealthRating(str, Enum):
    """Bewertungs-Stufen für Financial Health."""
    EXCELLENT = "exzellent"
    GOOD = "gut"
    MODERATE = "moderat"
    NEEDS_ATTENTION = "verbesserungsbedürftig"
    CRITICAL = "kritisch"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DimensionScore:
    """Score einer einzelnen Dimension."""
    name: str
    score: Decimal  # 0-100
    weight: Decimal
    weighted_score: Decimal
    rating: HealthRating
    details: Dict[str, Any]
    recommendations: List[str]


@dataclass
class NetWorthSummary:
    """Zusammenfassung des Netto-Vermoegens."""
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal

    # Aufschluesslung Assets
    property_value: Decimal
    vehicle_value: Decimal
    investment_value: Decimal
    cash_and_savings: Decimal

    # Aufschluesslung Schulden
    mortgage_debt: Decimal
    loan_debt: Decimal
    other_debt: Decimal

    # Trend
    net_worth_change_ytd: Optional[Decimal]
    net_worth_change_pct: Optional[Decimal]


@dataclass
class FinancialHealthScore:
    """Vollständiger Financial Health Score."""
    space_id: UUID

    # Gesamt-Score (0-100)
    total_score: Decimal
    rating: HealthRating

    # Einzelne Dimensionen
    dimensions: List[DimensionScore]

    # Net Worth Zusammenfassung
    net_worth: NetWorthSummary

    # Monatliche Kennzahlen
    estimated_monthly_income: Optional[Decimal]
    estimated_monthly_expenses: Optional[Decimal]
    monthly_savings_rate: Optional[Decimal]

    # Top Empfehlungen (priorisiert)
    priority_recommendations: List[str]

    # Vergleich
    benchmark_percentile: Optional[Decimal]  # Wo steht man im Vergleich (0-100)

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Singleton Service
# =============================================================================

class FinancialHealthService:
    """
    Singleton Service für Financial Health Score Berechnung.

    Berechnet einen ganzheitlichen Gesundheits-Score basierend auf:
    - Vermoegen und Schulden
    - Einkommens- und Ausgaben-Verhältnis
    - Versicherungsschutz
    - Notfall-Reserve
    - Altersvorsorge
    - Investment-Diversifikation
    """

    _instance: Optional["FinancialHealthService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "FinancialHealthService":
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
        logger.info("financial_health_service_initialized")

    # =========================================================================
    # Net Worth Berechnung
    # =========================================================================

    async def calculate_net_worth(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> NetWorthSummary:
        """Berechnet das Netto-Vermoegen eines Spaces."""
        from app.db.models import (
            PrivatProperty, PrivatVehicle, PrivatInvestment, PrivatLoan,
            PrivatKPIHistory,
        )

        HEALTH_SCORE_CALCULATIONS.labels(calculation_type="net_worth").inc()

        # Properties (Immobilien)
        prop_result = await db.execute(
            select(func.coalesce(func.sum(PrivatProperty.current_value), 0))
            .where(
                PrivatProperty.space_id == space_id,
                or_(PrivatProperty.deleted_at == None, PrivatProperty.deleted_at.is_(None)),
            )
        )
        property_value = Decimal(str(prop_result.scalar() or 0))

        # Vehicles (Fahrzeuge)
        veh_result = await db.execute(
            select(func.coalesce(func.sum(PrivatVehicle.current_estimated_value), 0))
            .where(
                PrivatVehicle.space_id == space_id,
                PrivatVehicle.is_active == True,
            )
        )
        vehicle_value = Decimal(str(veh_result.scalar() or 0))

        # Falls keine geschätzten Werte, nehme Kaufpreis
        if vehicle_value == 0:
            veh_purchase_result = await db.execute(
                select(func.coalesce(func.sum(PrivatVehicle.purchase_price), 0))
                .where(
                    PrivatVehicle.space_id == space_id,
                    PrivatVehicle.is_active == True,
                )
            )
            vehicle_value = Decimal(str(veh_purchase_result.scalar() or 0))

        # Investments
        inv_result = await db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0))
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
            )
        )
        investment_value = Decimal(str(inv_result.scalar() or 0))

        # Tagesgeld/Sparguthaben separat (aus Investments mit Typ tagesgeld/festgeld/sparbuch)
        cash_result = await db.execute(
            select(func.coalesce(func.sum(PrivatInvestment.current_value), 0))
            .where(
                PrivatInvestment.space_id == space_id,
                PrivatInvestment.is_active == True,
                PrivatInvestment.investment_type.in_(["tagesgeld", "festgeld", "sparbuch", "girokonto"]),
            )
        )
        cash_and_savings = Decimal(str(cash_result.scalar() or 0))

        # Schulden (Kredite)
        loan_result = await db.execute(
            select(
                func.coalesce(func.sum(PrivatLoan.remaining_balance), 0).label("total"),
            )
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
            )
        )
        total_loan_debt = Decimal(str(loan_result.scalar() or 0))

        # Hypotheken separat
        mortgage_result = await db.execute(
            select(func.coalesce(func.sum(PrivatLoan.remaining_balance), 0))
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
                PrivatLoan.loan_type.in_(["hypothek", "baufinanzierung", "immobiliendarlehen"]),
            )
        )
        mortgage_debt = Decimal(str(mortgage_result.scalar() or 0))

        # Sonstige Kredite
        other_loans = total_loan_debt - mortgage_debt

        # Totals berechnen
        total_assets = property_value + vehicle_value + investment_value
        total_liabilities = total_loan_debt
        net_worth = total_assets - total_liabilities

        # Net Worth Trend aus historischen Daten berechnen
        net_worth_change_ytd: Optional[Decimal] = None
        net_worth_change_pct: Optional[Decimal] = None

        # Hole Net Worth vom Jahresanfang (oder aeltester verfügbarer Eintrag)
        year_start = datetime(datetime.now(timezone.utc).year, 1, 1, tzinfo=timezone.utc)

        # Suche aeltesten Net Worth Eintrag im aktuellen Jahr
        ytd_result = await db.execute(
            select(PrivatKPIHistory.kpi_value, PrivatKPIHistory.recorded_at)
            .where(
                PrivatKPIHistory.space_id == space_id,
                PrivatKPIHistory.kpi_name == "net_worth",
                PrivatKPIHistory.recorded_at >= year_start,
            )
            .order_by(PrivatKPIHistory.recorded_at.asc())
            .limit(1)
        )
        oldest_entry = ytd_result.first()

        if oldest_entry and oldest_entry.kpi_value is not None:
            historical_net_worth = Decimal(str(oldest_entry.kpi_value))
            net_worth_change_ytd = net_worth - historical_net_worth

            # Prozentuale Änderung berechnen (Division by Zero vermeiden)
            if historical_net_worth != 0:
                net_worth_change_pct = (
                    (net_worth_change_ytd / abs(historical_net_worth)) * 100
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                # Bei historischem Null-Vermoegen: Spezialfall
                if net_worth > 0:
                    net_worth_change_pct = Decimal("100.00")  # Positiver Aufbau
                elif net_worth < 0:
                    net_worth_change_pct = Decimal("-100.00")  # Schulden aufgebaut
                else:
                    net_worth_change_pct = Decimal("0.00")

        return NetWorthSummary(
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_worth=net_worth,
            property_value=property_value,
            vehicle_value=vehicle_value,
            investment_value=investment_value,
            cash_and_savings=cash_and_savings,
            mortgage_debt=mortgage_debt,
            loan_debt=other_loans,
            other_debt=Decimal("0"),
            net_worth_change_ytd=net_worth_change_ytd,
            net_worth_change_pct=net_worth_change_pct,
        )

    # =========================================================================
    # Dimensions-Berechnungen
    # =========================================================================

    async def _calculate_net_worth_trend_score(
        self,
        net_worth: NetWorthSummary,
    ) -> DimensionScore:
        """Berechnet den Score für Net Worth Trend."""
        score = Decimal("50")  # Basis-Score wenn kein Trend bekannt
        recommendations: List[str] = []

        # Positives Net Worth?
        if net_worth.net_worth >= 0:
            score = Decimal("60")

            # Vermoegen im Verhältnis zu Schulden
            if net_worth.total_liabilities == 0:
                score = Decimal("85")
            elif net_worth.total_assets > 0:
                asset_ratio = net_worth.total_assets / (net_worth.total_assets + net_worth.total_liabilities)
                score = (asset_ratio * 100).quantize(Decimal("0.1"))

            # Bonus für diversifizierte Assets
            asset_types = 0
            if net_worth.property_value > 0:
                asset_types += 1
            if net_worth.vehicle_value > 0:
                asset_types += 1
            if net_worth.investment_value > 0:
                asset_types += 1

            if asset_types >= 3:
                score = min(Decimal("100"), score + Decimal("10"))

        else:
            # Negatives Net Worth (mehr Schulden als Vermoegen)
            score = Decimal("30")
            recommendations.append(
                "Ihr Netto-Vermoegen ist negativ. Priorisieren Sie den Schuldenabbau "
                "und bauen Sie gleichzeitig Vermoegen auf."
            )

        # Trend-basierte Anpassung (falls verfügbar)
        if net_worth.net_worth_change_pct is not None:
            if net_worth.net_worth_change_pct > 10:
                score = min(Decimal("100"), score + Decimal("15"))
            elif net_worth.net_worth_change_pct > 5:
                score = min(Decimal("100"), score + Decimal("10"))
            elif net_worth.net_worth_change_pct < -5:
                score = max(Decimal("0"), score - Decimal("15"))
                recommendations.append(
                    "Ihr Netto-Vermoegen ist in diesem Jahr gesunken. "
                    "Überprüfen Sie Ihre Ausgaben und Spar-Strategie."
                )

        if not recommendations and score >= 70:
            recommendations.append(
                "Guter Vermoegensaufbau! Halten Sie die aktuelle Strategie bei."
            )

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="net_worth_trend",
            score=score,
            weight=DIMENSION_WEIGHTS["net_worth_trend"],
            weighted_score=(score * DIMENSION_WEIGHTS["net_worth_trend"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details={
                "net_worth": str(net_worth.net_worth),
                "total_assets": str(net_worth.total_assets),
                "total_liabilities": str(net_worth.total_liabilities),
            },
            recommendations=recommendations,
        )

    async def _calculate_debt_management_score(
        self,
        db: AsyncSession,
        space_id: UUID,
        net_worth: NetWorthSummary,
        estimated_monthly_income: Optional[Decimal],
    ) -> DimensionScore:
        """Berechnet den Score für Schulden-Management."""
        from app.db.models import PrivatLoan

        score = Decimal("100")  # Starte mit perfektem Score
        recommendations: List[str] = []
        details: Dict[str, Any] = {}

        # Keine Schulden = perfekt
        if net_worth.total_liabilities == 0:
            details["dti_ratio"] = "0%"
            details["has_debt"] = False
            return DimensionScore(
                name="debt_management",
                score=score,
                weight=DIMENSION_WEIGHTS["debt_management"],
                weighted_score=(score * DIMENSION_WEIGHTS["debt_management"] / 100).quantize(Decimal("0.1")),
                rating=HealthRating.EXCELLENT,
                details=details,
                recommendations=["Keine Schulden - hervorragend!"],
            )

        details["has_debt"] = True
        details["total_debt"] = str(net_worth.total_liabilities)

        # Debt-to-Income Ratio berechnen
        if estimated_monthly_income and estimated_monthly_income > 0:
            # Monatliche Schulden-Zahlungen holen
            loan_result = await db.execute(
                select(func.coalesce(func.sum(PrivatLoan.monthly_payment), 0))
                .where(
                    PrivatLoan.space_id == space_id,
                    PrivatLoan.is_active == True,
                )
            )
            monthly_payments = Decimal(str(loan_result.scalar() or 0))

            dti_ratio = monthly_payments / estimated_monthly_income
            details["dti_ratio"] = f"{(dti_ratio * 100).quantize(Decimal('0.1'))}%"
            details["monthly_payments"] = str(monthly_payments)

            # Score basierend auf DTI
            if dti_ratio <= Decimal("0.20"):
                score = Decimal("90")
            elif dti_ratio <= Decimal("0.30"):
                score = Decimal("75")
            elif dti_ratio <= MAX_HEALTHY_DTI_RATIO:
                score = Decimal("60")
            elif dti_ratio <= Decimal("0.50"):
                score = Decimal("40")
                recommendations.append(
                    f"Ihre Schulden-Quote liegt bei {details['dti_ratio']}. "
                    "Empfohlen sind maximal 36%. Reduzieren Sie Schulden oder erhöhen Sie das Einkommen."
                )
            else:
                score = Decimal("20")
                recommendations.append(
                    f"Kritische Schulden-Quote von {details['dti_ratio']}! "
                    "Dringende Schuldenreduktion erforderlich."
                )
        else:
            # Fallback: Verhältnis Schulden zu Vermoegen
            if net_worth.total_assets > 0:
                debt_ratio = net_worth.total_liabilities / net_worth.total_assets
                if debt_ratio <= Decimal("0.30"):
                    score = Decimal("80")
                elif debt_ratio <= Decimal("0.50"):
                    score = Decimal("60")
                elif debt_ratio <= Decimal("0.80"):
                    score = Decimal("40")
                else:
                    score = Decimal("20")
                    recommendations.append(
                        "Sehr hohe Verschuldung im Verhältnis zum Vermoegen. "
                        "Schuldenabbau sollte Priorität haben."
                    )
            else:
                score = Decimal("25")
                recommendations.append(
                    "Sie haben Schulden aber kein nennenswertes Vermoegen. "
                    "Fokussieren Sie sich auf Schuldenabbau."
                )

        # Bonus für niedrige Zinsen
        high_interest_result = await db.execute(
            select(func.count(PrivatLoan.id))
            .where(
                PrivatLoan.space_id == space_id,
                PrivatLoan.is_active == True,
                PrivatLoan.interest_rate > Decimal("8"),  # Hochzins-Kredite
            )
        )
        high_interest_count = high_interest_result.scalar() or 0

        if high_interest_count > 0:
            score = max(Decimal("0"), score - Decimal("10"))
            recommendations.append(
                f"Sie haben {high_interest_count} Kredit(e) mit hohen Zinsen (>8%). "
                "Prüfen Sie Umschuldungs-Möglichkeiten."
            )

        if not recommendations:
            recommendations.append("Gutes Schulden-Management!")

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="debt_management",
            score=score,
            weight=DIMENSION_WEIGHTS["debt_management"],
            weighted_score=(score * DIMENSION_WEIGHTS["debt_management"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details=details,
            recommendations=recommendations,
        )

    async def _calculate_risk_coverage_score(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> DimensionScore:
        """Berechnet den Score für Risiko-Abdeckung (Versicherungen)."""
        from app.db.models import PrivatInsurance

        score = Decimal("0")
        recommendations: List[str] = []
        details: Dict[str, Any] = {}

        # Alle aktiven Versicherungen holen
        ins_result = await db.execute(
            select(PrivatInsurance.insurance_type)
            .where(
                PrivatInsurance.space_id == space_id,
                PrivatInsurance.is_active == True,
            )
        )
        insurance_types = [row[0].lower() for row in ins_result.all()]
        details["insurance_count"] = len(insurance_types)
        details["insurance_types"] = list(set(insurance_types))

        # Prüfe essentielle Versicherungen
        covered_essentials: List[str] = []
        missing_essentials: List[str] = []

        for essential in ESSENTIAL_INSURANCE_TYPES:
            # Prüfe ob Typ (oder Variante) vorhanden
            found = any(
                essential in ins_type or ins_type in essential
                for ins_type in insurance_types
            )
            if found:
                covered_essentials.append(essential)
            else:
                missing_essentials.append(essential)

        details["covered_essentials"] = covered_essentials
        details["missing_essentials"] = missing_essentials

        # Score berechnen
        coverage_ratio = len(covered_essentials) / len(ESSENTIAL_INSURANCE_TYPES)
        score = (Decimal(str(coverage_ratio)) * 100).quantize(Decimal("0.1"))

        # Empfehlungen für fehlende Versicherungen
        if missing_essentials:
            for missing in missing_essentials[:3]:  # Top 3
                recommendations.append(
                    f"Empfehlung: Prüfen Sie den Abschluss einer {missing.replace('_', '-').title()}-Versicherung."
                )

        # Bonus für gute Deckung
        if score >= 80:
            score = min(Decimal("100"), score + Decimal("10"))

        if not recommendations:
            recommendations.append("Gute Risiko-Abdeckung durch Versicherungen!")

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="risk_coverage",
            score=score,
            weight=DIMENSION_WEIGHTS["risk_coverage"],
            weighted_score=(score * DIMENSION_WEIGHTS["risk_coverage"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details=details,
            recommendations=recommendations,
        )

    async def _calculate_liquidity_score(
        self,
        net_worth: NetWorthSummary,
        estimated_monthly_expenses: Optional[Decimal],
    ) -> DimensionScore:
        """Berechnet den Score für Liquiditaet (Notgroschen)."""
        score = Decimal("0")
        recommendations: List[str] = []
        details: Dict[str, Any] = {}

        cash_reserves = net_worth.cash_and_savings
        details["cash_reserves"] = str(cash_reserves)

        if estimated_monthly_expenses and estimated_monthly_expenses > 0:
            # Berechne Monate an Reserve
            months_covered = cash_reserves / estimated_monthly_expenses
            details["months_covered"] = str(months_covered.quantize(Decimal("0.1")))
            details["recommended_months"] = RECOMMENDED_EMERGENCY_MONTHS

            if months_covered >= RECOMMENDED_EMERGENCY_MONTHS:
                score = Decimal("100")
            elif months_covered >= 3:
                score = Decimal("70")
                recommendations.append(
                    f"Ihr Notgroschen deckt {details['months_covered']} Monate. "
                    f"Empfohlen sind {RECOMMENDED_EMERGENCY_MONTHS} Monate."
                )
            elif months_covered >= 1:
                score = Decimal("40")
                recommendations.append(
                    "Notgroschen-Reserve zu gering! Bauen Sie mindestens 3-6 Monatsausgaben auf."
                )
            else:
                score = Decimal("15")
                recommendations.append(
                    "KRITISCH: Kaum liquide Mittel vorhanden! "
                    "Ein Notgroschen sollte hoechste Priorität haben."
                )
        else:
            # Fallback: Absolute Betraege
            if cash_reserves >= Decimal("30000"):
                score = Decimal("90")
            elif cash_reserves >= Decimal("15000"):
                score = Decimal("70")
            elif cash_reserves >= Decimal("5000"):
                score = Decimal("50")
            elif cash_reserves >= Decimal("1000"):
                score = Decimal("30")
            else:
                score = Decimal("10")
                recommendations.append(
                    "Bauen Sie eine liquide Reserve auf. Empfohlen: 3-6 Monatsausgaben."
                )

        if not recommendations:
            recommendations.append("Gute Liquiditaetsreserve vorhanden!")

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="liquidity",
            score=score,
            weight=DIMENSION_WEIGHTS["liquidity"],
            weighted_score=(score * DIMENSION_WEIGHTS["liquidity"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details=details,
            recommendations=recommendations,
        )

    async def _calculate_retirement_readiness_score(
        self,
        net_worth: NetWorthSummary,
        estimated_annual_income: Optional[Decimal],
        age: Optional[int],
    ) -> DimensionScore:
        """Berechnet den Score für Altersvorsorge."""
        score = Decimal("50")  # Default wenn keine Daten
        recommendations: List[str] = []
        details: Dict[str, Any] = {}

        # Altersvorsorge-relevante Werte (Investments ohne kurzfristige)
        retirement_assets = net_worth.investment_value + net_worth.property_value

        details["retirement_assets"] = str(retirement_assets)

        if estimated_annual_income and age and age >= 20:
            # Ziel basierend auf Alter
            target_factor = self._get_retirement_factor(age)
            target_amount = estimated_annual_income * target_factor

            details["target_amount"] = str(target_amount.quantize(Decimal("0.01")))
            details["target_factor"] = str(target_factor)
            details["age"] = age

            if target_amount > 0:
                ratio = retirement_assets / target_amount
                score = min(Decimal("100"), (ratio * 100).quantize(Decimal("0.1")))

                if ratio < Decimal("0.5"):
                    recommendations.append(
                        f"Ihre Altersvorsorge liegt deutlich unter dem Ziel "
                        f"({(ratio * 100).quantize(Decimal('0.1'))}% vom empfohlenen Wert). "
                        "Erhöhen Sie Ihre Sparquote."
                    )
                elif ratio < Decimal("0.8"):
                    recommendations.append(
                        "Altersvorsorge leicht unter Ziel. Kleine Anpassungen empfohlen."
                    )
        else:
            # Fallback: Absolute Betraege
            if retirement_assets >= Decimal("500000"):
                score = Decimal("90")
            elif retirement_assets >= Decimal("250000"):
                score = Decimal("75")
            elif retirement_assets >= Decimal("100000"):
                score = Decimal("60")
            elif retirement_assets >= Decimal("50000"):
                score = Decimal("45")
            else:
                score = Decimal("30")
                recommendations.append(
                    "Bauen Sie frühzeitig Altersvorsorge auf. "
                    "Der Zinseszins-Effekt wirkt umso stärker, je früher Sie beginnen."
                )

        if not recommendations:
            recommendations.append("Altersvorsorge auf gutem Kurs!")

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="retirement_readiness",
            score=score,
            weight=DIMENSION_WEIGHTS["retirement_readiness"],
            weighted_score=(score * DIMENSION_WEIGHTS["retirement_readiness"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details=details,
            recommendations=recommendations,
        )

    def _get_retirement_factor(self, age: int) -> Decimal:
        """Gibt den empfohlenen Altersvorsorge-Faktor für ein Alter zurück."""
        # Finde nächsten Ankerpunkt
        ages = sorted(RETIREMENT_FACTOR_BY_AGE.keys())

        if age <= ages[0]:
            return RETIREMENT_FACTOR_BY_AGE[ages[0]]
        if age >= ages[-1]:
            return RETIREMENT_FACTOR_BY_AGE[ages[-1]]

        # Interpolieren
        for i in range(len(ages) - 1):
            if ages[i] <= age < ages[i + 1]:
                lower_age = ages[i]
                upper_age = ages[i + 1]
                lower_factor = RETIREMENT_FACTOR_BY_AGE[lower_age]
                upper_factor = RETIREMENT_FACTOR_BY_AGE[upper_age]

                ratio = Decimal(str(age - lower_age)) / Decimal(str(upper_age - lower_age))
                return lower_factor + ratio * (upper_factor - lower_factor)

        return Decimal("3")  # Fallback

    async def _calculate_diversification_score(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> DimensionScore:
        """Berechnet den Score für Diversifikation."""
        from app.services.privat.investment_intelligence_service import get_investment_intelligence_service

        intel_service = get_investment_intelligence_service()

        try:
            diversification = await intel_service.analyze_diversification(db, space_id)

            score = diversification.diversification_score
            details = {
                "herfindahl_index": str(diversification.herfindahl_index),
                "unique_types": diversification.unique_types,
                "largest_position_pct": str(diversification.largest_position_percentage),
                "rating": diversification.rating,
            }
            recommendations = diversification.recommendations[:2]  # Top 2

        except Exception as e:
            logger.warning(
                "diversification_calculation_failed",
                space_id=str(space_id),
                **safe_error_log(e),
            )
            score = Decimal("50")
            details = {"error": "Berechnung nicht möglich"}
            recommendations = ["Fuegen Sie Investments hinzu für Diversifikations-Analyse."]

        rating = self._score_to_rating(score)

        return DimensionScore(
            name="diversification",
            score=score,
            weight=DIMENSION_WEIGHTS["diversification"],
            weighted_score=(score * DIMENSION_WEIGHTS["diversification"] / 100).quantize(Decimal("0.1")),
            rating=rating,
            details=details,
            recommendations=recommendations,
        )

    # =========================================================================
    # Haupt-Berechnung
    # =========================================================================

    async def calculate_health_score(
        self,
        db: AsyncSession,
        space_id: UUID,
        estimated_monthly_income: Optional[Decimal] = None,
        estimated_monthly_expenses: Optional[Decimal] = None,
        age: Optional[int] = None,
    ) -> FinancialHealthScore:
        """Berechnet den vollständigen Financial Health Score."""
        import time

        start_time = time.time()
        HEALTH_SCORE_CALCULATIONS.labels(calculation_type="full_score").inc()

        # 1. Net Worth berechnen
        net_worth = await self.calculate_net_worth(db, space_id)

        # Jahreseinkommen schätzen falls nicht angegeben
        estimated_annual_income: Optional[Decimal] = None
        if estimated_monthly_income:
            estimated_annual_income = estimated_monthly_income * 12

        # 2. Alle Dimensionen berechnen
        dimensions: List[DimensionScore] = []

        # Net Worth Trend
        net_worth_dim = await self._calculate_net_worth_trend_score(net_worth)
        dimensions.append(net_worth_dim)

        # Debt Management
        debt_dim = await self._calculate_debt_management_score(
            db, space_id, net_worth, estimated_monthly_income
        )
        dimensions.append(debt_dim)

        # Risk Coverage
        risk_dim = await self._calculate_risk_coverage_score(db, space_id)
        dimensions.append(risk_dim)

        # Liquidity
        liquidity_dim = await self._calculate_liquidity_score(
            net_worth, estimated_monthly_expenses
        )
        dimensions.append(liquidity_dim)

        # Retirement Readiness
        retirement_dim = await self._calculate_retirement_readiness_score(
            net_worth, estimated_annual_income, age
        )
        dimensions.append(retirement_dim)

        # Diversification
        div_dim = await self._calculate_diversification_score(db, space_id)
        dimensions.append(div_dim)

        # 3. Gesamt-Score berechnen (gewichteter Durchschnitt)
        total_score = sum(d.weighted_score for d in dimensions)
        total_score = total_score.quantize(Decimal("0.1"))

        # 4. Rating bestimmen
        rating = self._score_to_rating(total_score)

        # 5. Top-Empfehlungen priorisieren
        all_recommendations: List[Tuple[Decimal, str]] = []
        for dim in dimensions:
            # Niedrigere Scores = höhere Priorität
            priority = Decimal("100") - dim.score
            for rec in dim.recommendations:
                all_recommendations.append((priority, rec))

        all_recommendations.sort(key=lambda x: x[0], reverse=True)
        priority_recommendations = [rec for _, rec in all_recommendations[:5]]

        # 6. Sparquote berechnen
        monthly_savings_rate: Optional[Decimal] = None
        if estimated_monthly_income and estimated_monthly_expenses:
            if estimated_monthly_income > 0:
                savings = estimated_monthly_income - estimated_monthly_expenses
                monthly_savings_rate = (savings / estimated_monthly_income * 100).quantize(Decimal("0.1"))

        # Prometheus Metrik setzen
        HEALTH_SCORE_GAUGE.labels(space_id=str(space_id)).set(float(total_score))

        # 7. Benchmark-Perzentil berechnen (anonymisierter Vergleich)
        benchmark_percentile = await self._calculate_benchmark_percentile(
            db, space_id, total_score
        )

        duration = time.time() - start_time
        HEALTH_SCORE_DURATION.observe(duration)

        logger.info(
            "financial_health_score_calculated",
            space_id=str(space_id),
            total_score=str(total_score),
            rating=rating.value,
            benchmark_percentile=str(benchmark_percentile) if benchmark_percentile else None,
            duration_seconds=round(duration, 3),
        )

        return FinancialHealthScore(
            space_id=space_id,
            total_score=total_score,
            rating=rating,
            dimensions=dimensions,
            net_worth=net_worth,
            estimated_monthly_income=estimated_monthly_income,
            estimated_monthly_expenses=estimated_monthly_expenses,
            monthly_savings_rate=monthly_savings_rate,
            priority_recommendations=priority_recommendations,
            benchmark_percentile=benchmark_percentile,
        )

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _score_to_rating(self, score: Decimal) -> HealthRating:
        """Wandelt einen Score in ein Rating um."""
        if score >= 85:
            return HealthRating.EXCELLENT
        elif score >= 70:
            return HealthRating.GOOD
        elif score >= 50:
            return HealthRating.MODERATE
        elif score >= 30:
            return HealthRating.NEEDS_ATTENTION
        else:
            return HealthRating.CRITICAL

    async def _calculate_benchmark_percentile(
        self,
        db: AsyncSession,
        space_id: UUID,
        current_score: Decimal,
    ) -> Optional[Decimal]:
        """
        Berechnet das Benchmark-Perzentil basierend auf anonymisierten Score-Vergleichen.

        Vergleicht den aktuellen Score mit den letzten Health Scores anderer Spaces.
        Gibt das Perzentil zurück (0-100), wobei 50 = Durchschnitt bedeutet.

        Datenschutz-Hinweis: Nur aggregierte Statistiken werden verwendet,
        keine personenbezogenen Daten werden exponiert.
        """
        from app.db.models import PrivatKPIHistory

        # Nur Scores der letzten 30 Tage für aktuellen Vergleich
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)

        try:
            # Hole den neuesten Score pro Space (exkl. eigener Space)
            # Subquery: Max(recorded_at) pro space_id
            subquery = (
                select(
                    PrivatKPIHistory.space_id,
                    func.max(PrivatKPIHistory.recorded_at).label("max_recorded"),
                )
                .where(
                    PrivatKPIHistory.kpi_name == "financial_health_score",
                    PrivatKPIHistory.recorded_at >= cutoff_date,
                    PrivatKPIHistory.space_id != space_id,  # Eigener Space ausschließen
                )
                .group_by(PrivatKPIHistory.space_id)
                .subquery()
            )

            # Join mit Historie um neueste Werte zu bekommen
            result = await db.execute(
                select(PrivatKPIHistory.kpi_value)
                .join(
                    subquery,
                    and_(
                        PrivatKPIHistory.space_id == subquery.c.space_id,
                        PrivatKPIHistory.recorded_at == subquery.c.max_recorded,
                    ),
                )
                .where(PrivatKPIHistory.kpi_name == "financial_health_score")
            )

            other_scores = [Decimal(str(row[0])) for row in result.all() if row[0] is not None]

            if len(other_scores) < 5:
                # Mindestens 5 Vergleichswerte für statistisch sinnvolles Perzentil
                logger.debug(
                    "benchmark_insufficient_data",
                    space_id=str(space_id),
                    sample_size=len(other_scores),
                )
                return None

            # Perzentil berechnen: Wie viele Scores sind kleiner als der aktuelle?
            scores_below = sum(1 for s in other_scores if s < current_score)
            total_scores = len(other_scores)

            # Perzentil-Formel: (scores_below / total) * 100
            percentile = (Decimal(str(scores_below)) / Decimal(str(total_scores)) * 100).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )

            logger.debug(
                "benchmark_percentile_calculated",
                space_id=str(space_id),
                current_score=str(current_score),
                percentile=str(percentile),
                sample_size=total_scores,
            )

            return percentile

        except Exception as e:
            logger.warning(
                "benchmark_calculation_failed",
                space_id=str(space_id),
                **safe_error_log(e),
            )
            return None

    # =========================================================================
    # Batch-Operationen für Celery
    # =========================================================================

    async def recalculate_all_health_scores(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Berechnet alle Health Scores neu (für Celery Beat)."""
        from app.db.models import PrivatSpace


        result = await db.execute(
            select(PrivatSpace.id).where(PrivatSpace.is_active == True)
        )
        space_ids = [row[0] for row in result.all()]

        processed = 0
        errors = 0

        for space_id in space_ids:
            try:
                await self.calculate_health_score(db, space_id)
                processed += 1
            except Exception as e:
                errors += 1
                logger.error(
                    "health_score_recalculation_failed",
                    space_id=str(space_id),
                    **safe_error_log(e),
                )

        logger.info(
            "all_health_scores_recalculated",
            total_spaces=len(space_ids),
            processed=processed,
            errors=errors,
        )

        return {
            "total_spaces": len(space_ids),
            "processed": processed,
            "errors": errors,
        }


# =============================================================================
# Singleton-Instanz
# =============================================================================

def get_financial_health_service() -> FinancialHealthService:
    """Gibt die Singleton-Instanz des Financial Health Service zurück."""
    return FinancialHealthService()
