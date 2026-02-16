# -*- coding: utf-8 -*-
"""
InvestmentIntelligenceService - Intelligente Portfolio-Analyse und Performance-Tracking.

Berechnet automatisch:
- Performance-Metriken (Absolut, %, CAGR)
- Portfolio-Diversifikation (Herfindahl-Index)
- Risiko-Profil basierend auf Investment-Typen
- Allokations-Analyse
- Rebalancing-Empfehlungen

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

INVESTMENT_INTEL_CALCULATIONS = Counter(
    "investment_intelligence_calculations_total",
    "Anzahl der Investment-Intelligence Berechnungen",
    ["calculation_type"]
)

INVESTMENT_INTEL_DURATION = Histogram(
    "investment_intelligence_duration_seconds",
    "Dauer der Investment-Intelligence Berechnung",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

PORTFOLIO_TOTAL_VALUE = Gauge(
    "portfolio_total_value_euros",
    "Gesamtwert aller Portfolios",
    ["space_id"]
)


# =============================================================================
# Referenzdaten - Investment-Kategorien und Risiko-Profile
# =============================================================================

# Investment-Typ zu Risiko-Score Mapping (0 = kein Risiko, 100 = maximales Risiko)
INVESTMENT_TYPE_RISK_SCORES: Dict[str, int] = {
    # Sehr niedriges Risiko
    "tagesgeld": 5,
    "festgeld": 8,
    "sparbuch": 3,
    "bausparvertrag": 10,

    # Niedriges Risiko
    "staatsanleihe": 15,
    "anleihe": 20,
    "renten_fonds": 25,
    "geldmarktfonds": 12,

    # Mittleres Risiko
    "etf": 45,
    "indexfonds": 45,
    "mischfonds": 40,
    "immobilienfonds": 35,

    # Hohes Risiko
    "aktie": 70,
    "aktienfonds": 60,
    "einzelaktie": 75,
    "aktien": 70,

    # Sehr hohes Risiko
    "krypto": 95,
    "kryptowährung": 95,
    "bitcoin": 95,
    "rohstoffe": 80,
    "optionen": 90,
    "derivate": 92,

    # Spezial
    "lebensversicherung": 15,
    "rentenversicherung": 12,
    "beteiligung": 85,
    "crowdfunding": 80,
    "p2p_kredit": 75,

    # Default
    "sonstige": 50,
}

# Ideale Allokation nach Risikoprofil (vereinfacht)
IDEAL_ALLOCATIONS: Dict[str, Dict[str, Decimal]] = {
    "konservativ": {
        "sicher": Decimal("0.70"),    # Tagesgeld, Festgeld, Anleihen
        "moderat": Decimal("0.25"),   # ETF, Mischfonds
        "riskant": Decimal("0.05"),   # Aktien, Krypto
    },
    "ausgewogen": {
        "sicher": Decimal("0.40"),
        "moderat": Decimal("0.40"),
        "riskant": Decimal("0.20"),
    },
    "wachstum": {
        "sicher": Decimal("0.20"),
        "moderat": Decimal("0.40"),
        "riskant": Decimal("0.40"),
    },
    "aggressiv": {
        "sicher": Decimal("0.10"),
        "moderat": Decimal("0.30"),
        "riskant": Decimal("0.60"),
    },
}

# Risiko-Kategorie-Mapping
RISK_CATEGORIES: Dict[str, List[str]] = {
    "sicher": ["tagesgeld", "festgeld", "sparbuch", "bausparvertrag", "staatsanleihe",
               "anleihe", "renten_fonds", "geldmarktfonds", "lebensversicherung",
               "rentenversicherung"],
    "moderat": ["etf", "indexfonds", "mischfonds", "immobilienfonds"],
    "riskant": ["aktie", "aktienfonds", "einzelaktie", "aktien", "krypto",
                "kryptowährung", "bitcoin", "rohstoffe", "optionen", "derivate",
                "beteiligung", "crowdfunding", "p2p_kredit"],
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class InvestmentPerformance:
    """Performance-Kennzahlen eines Investments."""
    investment_id: UUID
    investment_name: str

    # Werte
    purchase_value: Decimal
    current_value: Decimal

    # Performance
    absolute_gain: Decimal
    percentage_gain: Decimal

    # Zeitraum
    purchase_date: Optional[date]
    holding_days: int
    holding_years: Decimal

    # Annualisierte Rendite (CAGR)
    cagr: Optional[Decimal]

    # Risiko-Einordnung
    risk_score: int
    risk_category: str

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PortfolioAllocation:
    """Portfolio-Allokation nach Kategorien."""
    # Verteilung nach Investment-Typ
    by_type: Dict[str, Decimal]
    by_type_percentages: Dict[str, Decimal]

    # Verteilung nach Risiko-Kategorie
    by_risk_category: Dict[str, Decimal]
    by_risk_category_percentages: Dict[str, Decimal]

    # Totals
    total_value: Decimal
    investment_count: int


@dataclass
class DiversificationAnalysis:
    """Diversifikations-Analyse des Portfolios."""
    # Herfindahl-Hirschman Index (0-10000, niedriger = besser diversifiziert)
    herfindahl_index: Decimal

    # Normalisierter Diversifikations-Score (0-100, höher = besser)
    diversification_score: Decimal

    # Anzahl verschiedener Investment-Typen
    unique_types: int

    # Konzentration
    largest_position_percentage: Decimal
    largest_position_name: str
    top_3_concentration: Decimal

    # Bewertung
    rating: str  # "sehr_gut", "gut", "moderat", "schlecht", "kritisch"

    # Empfehlungen
    recommendations: List[str]


@dataclass
class RiskProfile:
    """Risiko-Profil des Portfolios."""
    # Gewichteter durchschnittlicher Risiko-Score (0-100)
    weighted_risk_score: Decimal

    # Risiko-Kategorie
    risk_category: str  # "konservativ", "ausgewogen", "wachstum", "aggressiv"

    # Risiko-Verteilung
    safe_percentage: Decimal
    moderate_percentage: Decimal
    risky_percentage: Decimal

    # Vergleich mit Idealprofil
    deviation_from_ideal: Dict[str, Decimal]

    # Bewertung
    volatility_estimate: str  # "niedrig", "moderat", "hoch", "sehr_hoch"


@dataclass
class RebalancingRecommendation:
    """Rebalancing-Empfehlung."""
    category: str
    current_percentage: Decimal
    target_percentage: Decimal
    difference: Decimal
    action: str  # "kaufen", "verkaufen", "halten"
    amount_to_adjust: Decimal
    affected_types: List[str]


@dataclass
class PortfolioAnalytics:
    """Vollständige Portfolio-Analyse."""
    space_id: UUID

    # Performance
    total_invested: Decimal
    total_value: Decimal
    total_gain: Decimal
    total_gain_percentage: Decimal
    portfolio_cagr: Optional[Decimal]

    # Allokation
    allocation: PortfolioAllocation

    # Diversifikation
    diversification: DiversificationAnalysis

    # Risiko
    risk_profile: RiskProfile

    # Einzelne Investments
    investments: List[InvestmentPerformance]

    # Rebalancing
    rebalancing_needed: bool
    rebalancing_recommendations: List[RebalancingRecommendation]

    # Health Score (0-100)
    portfolio_health_score: Decimal

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Singleton Service
# =============================================================================

class InvestmentIntelligenceService:
    """
    Singleton Service für Investment-Intelligence.

    Berechnet:
    - Investment-Performance (Absolut, %, CAGR)
    - Portfolio-Diversifikation (Herfindahl-Index)
    - Risiko-Profil
    - Rebalancing-Empfehlungen
    """

    _instance: Optional["InvestmentIntelligenceService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "InvestmentIntelligenceService":
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
        logger.info("investment_intelligence_service_initialized")

    # =========================================================================
    # Investment-Performance
    # =========================================================================

    async def calculate_investment_performance(
        self,
        db: AsyncSession,
        investment_id: UUID,
    ) -> Optional[InvestmentPerformance]:
        """Berechnet Performance-Kennzahlen für ein einzelnes Investment."""
        from app.db.models import PrivatInvestment

        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="performance").inc()

        result = await db.execute(
            select(PrivatInvestment).where(PrivatInvestment.id == investment_id)
        )
        investment = result.scalar_one_or_none()

        if not investment:
            logger.warning(
                "investment_not_found_for_performance",
                investment_id=str(investment_id)
            )
            return None

        return self._calculate_single_performance(investment)

    def _calculate_single_performance(
        self,
        investment: "PrivatInvestment",  # type: ignore
    ) -> InvestmentPerformance:
        """Interne Berechnung der Performance eines Investments."""
        purchase_value = investment.purchase_value or Decimal("0")
        current_value = investment.current_value or Decimal("0")

        # Absoluter Gewinn/Verlust
        absolute_gain = current_value - purchase_value

        # Prozentualer Gewinn/Verlust
        percentage_gain = Decimal("0")
        if purchase_value > 0:
            percentage_gain = ((current_value - purchase_value) / purchase_value * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        # Haltedauer
        purchase_date = investment.purchase_date
        holding_days = 0
        holding_years = Decimal("0")
        cagr = None

        if purchase_date:
            holding_days = (date.today() - purchase_date).days
            holding_years = Decimal(str(holding_days)) / Decimal("365.25")

            # CAGR berechnen (Compound Annual Growth Rate)
            if holding_years >= Decimal("0.1") and purchase_value > 0:  # Mindestens ~36 Tage
                try:
                    # CAGR = (Endwert / Startwert)^(1/Jahre) - 1
                    ratio = float(current_value / purchase_value)
                    years = float(holding_years)
                    if ratio > 0:
                        cagr_float = (ratio ** (1 / years)) - 1
                        cagr = (Decimal(str(cagr_float)) * 100).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                except (ValueError, ZeroDivisionError, OverflowError) as e:
                    logger.debug("cagr_calculation_failed", error_type=type(e).__name__)
                    cagr = None

        # Risiko-Einordnung
        inv_type = (investment.investment_type or "sonstige").lower().replace(" ", "_")
        risk_score = INVESTMENT_TYPE_RISK_SCORES.get(inv_type, 50)
        risk_category = self._get_risk_category(inv_type)

        return InvestmentPerformance(
            investment_id=investment.id,
            investment_name=investment.name,
            purchase_value=purchase_value,
            current_value=current_value,
            absolute_gain=absolute_gain,
            percentage_gain=percentage_gain,
            purchase_date=purchase_date,
            holding_days=holding_days,
            holding_years=holding_years.quantize(Decimal("0.01")),
            cagr=cagr,
            risk_score=risk_score,
            risk_category=risk_category,
        )

    def _get_risk_category(self, investment_type: str) -> str:
        """Bestimmt die Risiko-Kategorie eines Investment-Typs."""
        inv_type = investment_type.lower().replace(" ", "_")

        for category, types in RISK_CATEGORIES.items():
            if inv_type in types:
                return category

        # Fallback basierend auf Risiko-Score
        score = INVESTMENT_TYPE_RISK_SCORES.get(inv_type, 50)
        if score <= 25:
            return "sicher"
        elif score <= 50:
            return "moderat"
        else:
            return "riskant"

    # =========================================================================
    # Portfolio-Allokation
    # =========================================================================

    async def calculate_allocation(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> PortfolioAllocation:
        """Berechnet die Portfolio-Allokation."""
        from app.db.models import PrivatInvestment

        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="allocation").inc()

        result = await db.execute(
            select(PrivatInvestment).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.is_active == True,
                )
            )
        )
        investments = result.scalars().all()

        # Nach Typ aggregieren
        by_type: Dict[str, Decimal] = {}
        by_risk_category: Dict[str, Decimal] = {"sicher": Decimal("0"), "moderat": Decimal("0"), "riskant": Decimal("0")}
        total_value = Decimal("0")

        for inv in investments:
            value = inv.current_value or Decimal("0")
            total_value += value

            # Nach Investment-Typ
            inv_type = (inv.investment_type or "sonstige").lower()
            by_type[inv_type] = by_type.get(inv_type, Decimal("0")) + value

            # Nach Risiko-Kategorie
            risk_cat = self._get_risk_category(inv_type)
            by_risk_category[risk_cat] += value

        # Prozentuale Verteilung berechnen
        by_type_percentages: Dict[str, Decimal] = {}
        by_risk_category_percentages: Dict[str, Decimal] = {}

        if total_value > 0:
            for t, v in by_type.items():
                by_type_percentages[t] = (v / total_value * 100).quantize(Decimal("0.1"))

            for c, v in by_risk_category.items():
                by_risk_category_percentages[c] = (v / total_value * 100).quantize(Decimal("0.1"))

        return PortfolioAllocation(
            by_type=by_type,
            by_type_percentages=by_type_percentages,
            by_risk_category=by_risk_category,
            by_risk_category_percentages=by_risk_category_percentages,
            total_value=total_value,
            investment_count=len(investments),
        )

    # =========================================================================
    # Diversifikations-Analyse
    # =========================================================================

    async def analyze_diversification(
        self,
        db: AsyncSession,
        space_id: UUID,
    ) -> DiversificationAnalysis:
        """Analysiert die Diversifikation des Portfolios."""
        from app.db.models import PrivatInvestment

        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="diversification").inc()

        result = await db.execute(
            select(PrivatInvestment).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.is_active == True,
                )
            )
        )
        investments = list(result.scalars().all())

        if not investments:
            return DiversificationAnalysis(
                herfindahl_index=Decimal("10000"),
                diversification_score=Decimal("0"),
                unique_types=0,
                largest_position_percentage=Decimal("0"),
                largest_position_name="",
                top_3_concentration=Decimal("0"),
                rating="kritisch",
                recommendations=["Keine Investments vorhanden. Beginnen Sie mit dem Aufbau eines diversifizierten Portfolios."],
            )

        # Gesamtwert berechnen
        total_value = sum(inv.current_value or Decimal("0") for inv in investments)

        if total_value <= 0:
            return DiversificationAnalysis(
                herfindahl_index=Decimal("10000"),
                diversification_score=Decimal("0"),
                unique_types=len(set(inv.investment_type for inv in investments)),
                largest_position_percentage=Decimal("0"),
                largest_position_name="",
                top_3_concentration=Decimal("0"),
                rating="kritisch",
                recommendations=["Portfolio-Gesamtwert ist null. Aktualisieren Sie die aktuellen Werte."],
            )

        # Gewichtungen berechnen
        weights: List[Tuple[str, Decimal, Decimal]] = []
        for inv in investments:
            value = inv.current_value or Decimal("0")
            weight = value / total_value
            weights.append((inv.name, value, weight))

        # Nach Gewichtung sortieren (absteigend)
        weights.sort(key=lambda x: x[2], reverse=True)

        # Herfindahl-Hirschman Index berechnen
        # HHI = Summe(Gewichtung_i^2) * 10000
        hhi = sum(w[2] ** 2 for w in weights) * Decimal("10000")
        hhi = hhi.quantize(Decimal("1"))

        # Normalisierter Diversifikations-Score
        # Score = 100 * (1 - (HHI - 100) / 9900) mit Minimum HHI = 100 (perfekte Diversifikation)
        # Vereinfacht: Score = 100 - (HHI / 100)
        div_score = max(Decimal("0"), Decimal("100") - (hhi / Decimal("100")))
        div_score = div_score.quantize(Decimal("0.1"))

        # Konzentrations-Metriken
        largest_position = weights[0] if weights else ("", Decimal("0"), Decimal("0"))
        largest_pct = (largest_position[2] * 100).quantize(Decimal("0.1"))

        top_3_pct = Decimal("0")
        for i in range(min(3, len(weights))):
            top_3_pct += weights[i][2]
        top_3_pct = (top_3_pct * 100).quantize(Decimal("0.1"))

        # Unique Investment-Typen
        unique_types = len(set(inv.investment_type for inv in investments))

        # Rating bestimmen
        rating = self._rate_diversification(hhi, unique_types, largest_pct)

        # Empfehlungen generieren
        recommendations = self._generate_diversification_recommendations(
            hhi, unique_types, largest_pct, top_3_pct, weights
        )

        return DiversificationAnalysis(
            herfindahl_index=hhi,
            diversification_score=div_score,
            unique_types=unique_types,
            largest_position_percentage=largest_pct,
            largest_position_name=largest_position[0],
            top_3_concentration=top_3_pct,
            rating=rating,
            recommendations=recommendations,
        )

    def _rate_diversification(
        self,
        hhi: Decimal,
        unique_types: int,
        largest_pct: Decimal,
    ) -> str:
        """Bewertet die Diversifikation."""
        # HHI < 1500: Nicht konzentriert
        # HHI 1500-2500: Moderat konzentriert
        # HHI > 2500: Stark konzentriert

        if hhi < 1000 and unique_types >= 5 and largest_pct <= 25:
            return "sehr_gut"
        elif hhi < 1500 and unique_types >= 4 and largest_pct <= 35:
            return "gut"
        elif hhi < 2500 and unique_types >= 3:
            return "moderat"
        elif hhi < 4000:
            return "schlecht"
        else:
            return "kritisch"

    def _generate_diversification_recommendations(
        self,
        hhi: Decimal,
        unique_types: int,
        largest_pct: Decimal,
        top_3_pct: Decimal,
        weights: List[Tuple[str, Decimal, Decimal]],
    ) -> List[str]:
        """Generiert Empfehlungen zur Diversifikation."""
        recommendations: List[str] = []

        if unique_types < 3:
            recommendations.append(
                f"Erhöhen Sie die Anzahl verschiedener Investment-Typen (aktuell: {unique_types}). "
                "Empfohlen sind mindestens 5 verschiedene Kategorien."
            )

        if largest_pct > 40:
            recommendations.append(
                f"Die größte Position macht {largest_pct}% des Portfolios aus. "
                "Empfohlen: Maximal 20-25% pro Position."
            )

        if top_3_pct > 70:
            recommendations.append(
                f"Die Top-3 Positionen machen {top_3_pct}% aus. "
                "Erweitern Sie das Portfolio um weitere Investments."
            )

        if hhi > 2500:
            recommendations.append(
                "Hohe Konzentration (HHI > 2500). Verteilen Sie das Kapital auf mehr Positionen."
            )

        if not recommendations:
            recommendations.append(
                "Gute Diversifikation! Behalten Sie die aktuelle Struktur bei und "
                "überprüfen Sie regelmäßig die Balance."
            )

        return recommendations

    # =========================================================================
    # Risiko-Profil
    # =========================================================================

    async def analyze_risk_profile(
        self,
        db: AsyncSession,
        space_id: UUID,
        target_profile: str = "ausgewogen",
    ) -> RiskProfile:
        """Analysiert das Risiko-Profil des Portfolios."""
        from app.db.models import PrivatInvestment

        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="risk_profile").inc()

        result = await db.execute(
            select(PrivatInvestment).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.is_active == True,
                )
            )
        )
        investments = result.scalars().all()

        if not investments:
            return RiskProfile(
                weighted_risk_score=Decimal("0"),
                risk_category="unbestimmt",
                safe_percentage=Decimal("0"),
                moderate_percentage=Decimal("0"),
                risky_percentage=Decimal("0"),
                deviation_from_ideal={},
                volatility_estimate="unbekannt",
            )

        # Gewichteten Risiko-Score berechnen
        total_value = Decimal("0")
        weighted_risk_sum = Decimal("0")

        safe_value = Decimal("0")
        moderate_value = Decimal("0")
        risky_value = Decimal("0")

        for inv in investments:
            value = inv.current_value or Decimal("0")
            total_value += value

            inv_type = (inv.investment_type or "sonstige").lower().replace(" ", "_")
            risk_score = INVESTMENT_TYPE_RISK_SCORES.get(inv_type, 50)
            weighted_risk_sum += value * Decimal(str(risk_score))

            # Nach Risiko-Kategorie
            risk_cat = self._get_risk_category(inv_type)
            if risk_cat == "sicher":
                safe_value += value
            elif risk_cat == "moderat":
                moderate_value += value
            else:
                risky_value += value

        # Gewichteter Durchschnitt
        weighted_risk_score = Decimal("50")
        if total_value > 0:
            weighted_risk_score = (weighted_risk_sum / total_value).quantize(Decimal("0.1"))

        # Prozentuale Verteilung
        safe_pct = (safe_value / total_value * 100).quantize(Decimal("0.1")) if total_value > 0 else Decimal("0")
        moderate_pct = (moderate_value / total_value * 100).quantize(Decimal("0.1")) if total_value > 0 else Decimal("0")
        risky_pct = (risky_value / total_value * 100).quantize(Decimal("0.1")) if total_value > 0 else Decimal("0")

        # Risiko-Kategorie bestimmen
        risk_category = self._determine_portfolio_risk_category(weighted_risk_score)

        # Abweichung vom Ideal berechnen
        ideal = IDEAL_ALLOCATIONS.get(target_profile, IDEAL_ALLOCATIONS["ausgewogen"])
        deviation: Dict[str, Decimal] = {
            "sicher": safe_pct / 100 - ideal["sicher"],
            "moderat": moderate_pct / 100 - ideal["moderat"],
            "riskant": risky_pct / 100 - ideal["riskant"],
        }

        # Volatilitäts-Schätzung
        volatility = self._estimate_volatility(weighted_risk_score)

        return RiskProfile(
            weighted_risk_score=weighted_risk_score,
            risk_category=risk_category,
            safe_percentage=safe_pct,
            moderate_percentage=moderate_pct,
            risky_percentage=risky_pct,
            deviation_from_ideal={k: (v * 100).quantize(Decimal("0.1")) for k, v in deviation.items()},
            volatility_estimate=volatility,
        )

    def _determine_portfolio_risk_category(self, weighted_score: Decimal) -> str:
        """Bestimmt die Portfolio-Risikokategorie basierend auf gewichtetem Score."""
        if weighted_score < 25:
            return "konservativ"
        elif weighted_score < 45:
            return "ausgewogen"
        elif weighted_score < 65:
            return "wachstum"
        else:
            return "aggressiv"

    def _estimate_volatility(self, risk_score: Decimal) -> str:
        """Schätzt die erwartete Volatilität."""
        if risk_score < 20:
            return "niedrig"
        elif risk_score < 45:
            return "moderat"
        elif risk_score < 70:
            return "hoch"
        else:
            return "sehr_hoch"

    # =========================================================================
    # Rebalancing-Empfehlungen
    # =========================================================================

    async def generate_rebalancing_recommendations(
        self,
        db: AsyncSession,
        space_id: UUID,
        target_profile: str = "ausgewogen",
        threshold_pct: Decimal = Decimal("10"),
    ) -> List[RebalancingRecommendation]:
        """Generiert Rebalancing-Empfehlungen."""
        from app.db.models import PrivatInvestment

        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="rebalancing").inc()

        allocation = await self.calculate_allocation(db, space_id)

        if allocation.total_value <= 0:
            return []

        ideal = IDEAL_ALLOCATIONS.get(target_profile, IDEAL_ALLOCATIONS["ausgewogen"])
        recommendations: List[RebalancingRecommendation] = []

        # Für jede Risiko-Kategorie prüfen
        for category in ["sicher", "moderat", "riskant"]:
            current_pct = allocation.by_risk_category_percentages.get(category, Decimal("0"))
            target_pct = ideal[category] * 100
            difference = current_pct - target_pct

            # Nur empfehlen wenn Abweichung über Schwellenwert
            if abs(difference) >= threshold_pct:
                action = "verkaufen" if difference > 0 else "kaufen"
                amount = abs(difference) / 100 * allocation.total_value

                # Betroffene Investment-Typen finden
                affected = [t for t in RISK_CATEGORIES.get(category, [])
                           if t in allocation.by_type]

                recommendations.append(RebalancingRecommendation(
                    category=category,
                    current_percentage=current_pct,
                    target_percentage=target_pct,
                    difference=difference.quantize(Decimal("0.1")),
                    action=action,
                    amount_to_adjust=amount.quantize(Decimal("0.01")),
                    affected_types=affected,
                ))

        return recommendations

    # =========================================================================
    # Vollständige Portfolio-Analyse
    # =========================================================================

    async def get_full_portfolio_analytics(
        self,
        db: AsyncSession,
        space_id: UUID,
        target_risk_profile: str = "ausgewogen",
    ) -> PortfolioAnalytics:
        """Führt eine vollständige Portfolio-Analyse durch."""
        import time
        from app.db.models import PrivatInvestment

        start_time = time.time()
        INVESTMENT_INTEL_CALCULATIONS.labels(calculation_type="full_analytics").inc()

        # Alle aktiven Investments laden
        result = await db.execute(
            select(PrivatInvestment).where(
                and_(
                    PrivatInvestment.space_id == space_id,
                    PrivatInvestment.is_active == True,
                )
            )
        )
        investments = list(result.scalars().all())

        # Einzelne Performance-Berechnungen
        investment_performances: List[InvestmentPerformance] = []
        total_invested = Decimal("0")
        total_value = Decimal("0")
        earliest_date: Optional[date] = None

        for inv in investments:
            perf = self._calculate_single_performance(inv)
            investment_performances.append(perf)

            total_invested += perf.purchase_value
            total_value += perf.current_value

            if perf.purchase_date:
                if earliest_date is None or perf.purchase_date < earliest_date:
                    earliest_date = perf.purchase_date

        # Gesamt-Performance
        total_gain = total_value - total_invested
        total_gain_pct = Decimal("0")
        if total_invested > 0:
            total_gain_pct = ((total_value - total_invested) / total_invested * 100).quantize(Decimal("0.01"))

        # Portfolio-CAGR
        portfolio_cagr: Optional[Decimal] = None
        if earliest_date and total_invested > 0:
            days = (date.today() - earliest_date).days
            years = Decimal(str(days)) / Decimal("365.25")
            if years >= Decimal("0.1"):
                try:
                    ratio = float(total_value / total_invested)
                    if ratio > 0:
                        cagr_float = (ratio ** (1 / float(years))) - 1
                        portfolio_cagr = (Decimal(str(cagr_float)) * 100).quantize(Decimal("0.01"))
                except (ValueError, ZeroDivisionError, OverflowError) as e:
                    logger.debug("portfolio_cagr_calculation_failed", error_type=type(e).__name__)

        # Allokation, Diversifikation, Risiko parallel berechnen
        allocation = await self.calculate_allocation(db, space_id)
        diversification = await self.analyze_diversification(db, space_id)
        risk_profile = await self.analyze_risk_profile(db, space_id, target_risk_profile)
        rebalancing_recs = await self.generate_rebalancing_recommendations(
            db, space_id, target_risk_profile
        )

        # Rebalancing noetig?
        rebalancing_needed = len(rebalancing_recs) > 0

        # Health Score berechnen
        health_score = self._calculate_portfolio_health_score(
            diversification, risk_profile, total_gain_pct, len(investments)
        )

        # Prometheus Metrik
        PORTFOLIO_TOTAL_VALUE.labels(space_id=str(space_id)).set(float(total_value))

        duration = time.time() - start_time
        INVESTMENT_INTEL_DURATION.observe(duration)

        logger.info(
            "portfolio_analytics_completed",
            space_id=str(space_id),
            total_investments=len(investments),
            total_value=str(total_value),
            health_score=str(health_score),
            duration_seconds=round(duration, 3),
        )

        return PortfolioAnalytics(
            space_id=space_id,
            total_invested=total_invested,
            total_value=total_value,
            total_gain=total_gain,
            total_gain_percentage=total_gain_pct,
            portfolio_cagr=portfolio_cagr,
            allocation=allocation,
            diversification=diversification,
            risk_profile=risk_profile,
            investments=investment_performances,
            rebalancing_needed=rebalancing_needed,
            rebalancing_recommendations=rebalancing_recs,
            portfolio_health_score=health_score,
        )

    def _calculate_portfolio_health_score(
        self,
        diversification: DiversificationAnalysis,
        risk_profile: RiskProfile,
        gain_pct: Decimal,
        investment_count: int,
    ) -> Decimal:
        """Berechnet einen Gesundheits-Score für das Portfolio (0-100)."""
        score = Decimal("0")

        # Diversifikation (max 40 Punkte)
        div_score = diversification.diversification_score
        score += min(Decimal("40"), div_score * Decimal("0.4"))

        # Anzahl Investments (max 15 Punkte)
        if investment_count >= 10:
            score += Decimal("15")
        elif investment_count >= 5:
            score += Decimal("10")
        elif investment_count >= 3:
            score += Decimal("5")

        # Positive Performance (max 25 Punkte)
        if gain_pct >= 20:
            score += Decimal("25")
        elif gain_pct >= 10:
            score += Decimal("20")
        elif gain_pct >= 5:
            score += Decimal("15")
        elif gain_pct >= 0:
            score += Decimal("10")
        elif gain_pct >= -10:
            score += Decimal("5")

        # Ausgewogenes Risiko (max 20 Punkte)
        if risk_profile.risk_category == "ausgewogen":
            score += Decimal("20")
        elif risk_profile.risk_category in ["konservativ", "wachstum"]:
            score += Decimal("15")
        else:
            score += Decimal("10")

        return min(Decimal("100"), score).quantize(Decimal("0.1"))

    # =========================================================================
    # Batch-Operationen für Celery
    # =========================================================================

    async def recalculate_all_portfolios(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Berechnet alle Portfolio-Analysen neu (für Celery Beat)."""
        from app.db.models import PrivatSpace


        result = await db.execute(
            select(PrivatSpace.id).where(PrivatSpace.is_active == True)
        )
        space_ids = [row[0] for row in result.all()]

        processed = 0
        errors = 0

        for space_id in space_ids:
            try:
                await self.get_full_portfolio_analytics(db, space_id)
                processed += 1
            except Exception as e:
                errors += 1
                logger.error(
                    "portfolio_recalculation_failed",
                    space_id=str(space_id),
                    **safe_error_log(e),
                )

        logger.info(
            "all_portfolios_recalculated",
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

def get_investment_intelligence_service() -> InvestmentIntelligenceService:
    """Gibt die Singleton-Instanz des Investment Intelligence Service zurück."""
    return InvestmentIntelligenceService()
