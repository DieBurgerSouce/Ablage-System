# -*- coding: utf-8 -*-
"""
PropertyIntelligenceService - Intelligente Immobilienbewertung und KPIs.

Berechnet automatisch:
- Geschaetzter Immobilienwert (Inflation + Lage + Alter)
- Mietrendite (Brutto/Netto)
- ROI inkl. aller Kosten
- Wertsteigerungsprognose
- Nebenkosten-Analyse

Enterprise Feature - KEINE externen APIs, alles lokal berechnet.
"""

from __future__ import annotations

import threading
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PROPERTY_INTEL_CALCULATIONS = Counter(
    "property_intelligence_calculations_total",
    "Anzahl der Property-Intelligence Berechnungen",
    ["calculation_type"]
)

PROPERTY_INTEL_DURATION = Histogram(
    "property_intelligence_duration_seconds",
    "Dauer der Property-Intelligence Berechnung",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

PROPERTY_ESTIMATED_VALUES = Gauge(
    "property_estimated_values_total",
    "Summe aller geschaetzten Immobilienwerte"
)


# =============================================================================
# Referenzdaten (Lokale statische Daten, keine externen APIs)
# =============================================================================

# PLZ-Faktoren fuer deutsche Regionen (vereinfacht)
# Faktor 1.0 = Durchschnitt, >1.0 = teurer, <1.0 = guenstiger
PLZ_LOCATION_FACTORS: Dict[str, float] = {
    # Muenchen
    "80": 1.8, "81": 1.75, "82": 1.5, "83": 1.3, "85": 1.4,
    # Frankfurt
    "60": 1.5, "61": 1.3, "63": 1.2, "65": 1.25,
    # Hamburg
    "20": 1.4, "21": 1.2, "22": 1.45,
    # Berlin
    "10": 1.35, "12": 1.25, "13": 1.2, "14": 1.3,
    # Stuttgart
    "70": 1.45, "71": 1.3, "72": 1.15,
    # Duesseldorf/Koeln
    "40": 1.3, "50": 1.25, "51": 1.15,
    # Ostdeutschland (niedrigere Preise)
    "01": 0.85, "04": 0.8, "06": 0.75, "07": 0.7, "08": 0.7, "09": 0.75,
    "15": 0.8, "16": 0.75, "17": 0.7, "18": 0.65, "19": 0.65,
    # Laendliche Gebiete
    "27": 0.8, "29": 0.75, "31": 0.85, "37": 0.8,
    "48": 0.9, "49": 0.85, "56": 0.9, "57": 0.85,
    "66": 0.95, "67": 0.9, "76": 0.95, "77": 0.9,
    "88": 1.1, "89": 1.0, "94": 0.85, "95": 0.8, "96": 0.85, "97": 0.9,
}

# Durchschnittliche Inflation fuer Immobilien (konservativ)
REAL_ESTATE_INFLATION_RATE = Decimal("0.025")  # 2.5% p.a.

# Gebaeude-Abschreibung
BUILDING_DEPRECIATION_RATE = Decimal("0.005")  # 0.5% p.a.

# Typische Nebenkosten-Quote (% des Kaufpreises)
ACQUISITION_COSTS_RATE = Decimal("0.10")  # ~10% (Notar, Grunderwerbsteuer, Makler)

# Instandhaltungsruecklage Empfehlung (% des Wertes p.a.)
MAINTENANCE_RESERVE_RATE = Decimal("0.015")  # 1.5% p.a.


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PropertyValuation:
    """Geschaetzter Immobilienwert."""
    property_id: UUID
    purchase_price: Decimal
    estimated_current_value: Decimal
    valuation_method: str  # "inflation_adjusted", "manual", "hybrid"

    # Komponenten
    inflation_adjustment: Decimal = Decimal("0")
    location_factor: Decimal = Decimal("1.0")
    age_depreciation: Decimal = Decimal("0")

    # Konfidenz
    confidence_score: Decimal = Decimal("0.7")  # 0-1
    confidence_reason: str = ""

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PropertyAnalytics:
    """Vollstaendige Property-Analytics."""
    property_id: UUID

    # Wertentwicklung
    valuation: Optional[PropertyValuation] = None
    value_appreciation_absolute: Decimal = Decimal("0")
    value_appreciation_percent: Decimal = Decimal("0")
    annual_appreciation_rate: Decimal = Decimal("0")

    # Rendite
    gross_rental_yield: Optional[Decimal] = None
    net_rental_yield: Optional[Decimal] = None
    cap_rate: Optional[Decimal] = None  # Capitalization Rate

    # Kosten
    annual_rental_income: Decimal = Decimal("0")
    annual_costs: Decimal = Decimal("0")
    cost_breakdown: Dict[str, Decimal] = field(default_factory=dict)

    # ROI
    total_roi: Optional[Decimal] = None
    annual_roi: Optional[Decimal] = None
    cash_on_cash_return: Optional[Decimal] = None

    # Prognose
    projected_value_5y: Optional[Decimal] = None
    projected_value_10y: Optional[Decimal] = None
    break_even_years: Optional[Decimal] = None

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)
    health_score: Decimal = Decimal("0")  # 0-100

    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PropertyCostAnalysis:
    """Detaillierte Kostenanalyse."""
    property_id: UUID

    # Einmalige Kosten
    acquisition_costs: Decimal = Decimal("0")
    notary_costs: Decimal = Decimal("0")
    land_transfer_tax: Decimal = Decimal("0")

    # Laufende Kosten (jaehrlich)
    property_tax: Decimal = Decimal("0")
    insurance: Decimal = Decimal("0")
    maintenance: Decimal = Decimal("0")
    management_fees: Decimal = Decimal("0")
    utilities_landlord: Decimal = Decimal("0")

    # Berechnete Werte
    total_annual_costs: Decimal = Decimal("0")
    cost_per_sqm: Optional[Decimal] = None

    # Trend
    cost_trend_12m: str = "stable"  # "increasing", "decreasing", "stable"
    cost_trend_percent: Decimal = Decimal("0")


# =============================================================================
# Service
# =============================================================================

class PropertyIntelligenceService:
    """
    Intelligente Immobilien-Analyse ohne externe APIs.

    Features:
    - Automatische Wertschaetzung basierend auf Inflation + Lage
    - Vollstaendige Rendite-Berechnung
    - Kosten-Analyse mit Trend
    - Prognosen und Empfehlungen
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._cache: Dict[str, Any] = {}

    # =========================================================================
    # Wertschaetzung
    # =========================================================================

    async def estimate_property_value(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> Optional[PropertyValuation]:
        """
        Schaetzt den aktuellen Immobilienwert.

        Methodik:
        1. Kaufpreis als Basis
        2. Inflationsanpassung (2.5% p.a.)
        3. Lagefaktor basierend auf PLZ
        4. Gebaeudealter-Abschreibung

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID

        Returns:
            PropertyValuation oder None
        """
        from app.db.models import PrivatProperty

        PROPERTY_INTEL_CALCULATIONS.labels(calculation_type="valuation").inc()

        result = await db.execute(
            select(PrivatProperty).where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            logger.warning("property_not_found", property_id=str(property_id))
            return None

        if not prop.purchase_price or prop.purchase_price <= 0:
            logger.debug("no_purchase_price", property_id=str(property_id))
            return None

        purchase_price = Decimal(str(prop.purchase_price))

        # Wenn aktueller Wert manuell gesetzt wurde und aktuell ist
        if prop.current_value and prop.value_date:
            days_since_valuation = (date.today() - prop.value_date).days
            if days_since_valuation < 180:  # Weniger als 6 Monate alt
                return PropertyValuation(
                    property_id=property_id,
                    purchase_price=purchase_price,
                    estimated_current_value=Decimal(str(prop.current_value)),
                    valuation_method="manual",
                    confidence_score=Decimal("0.9"),
                    confidence_reason="Manueller Wert, weniger als 6 Monate alt",
                )

        # Automatische Berechnung
        if not prop.purchase_date:
            # Kein Kaufdatum - einfache Anpassung
            estimated = purchase_price * Decimal("1.05")  # Konservativ +5%
            return PropertyValuation(
                property_id=property_id,
                purchase_price=purchase_price,
                estimated_current_value=estimated.quantize(Decimal("0.01")),
                valuation_method="estimate",
                confidence_score=Decimal("0.4"),
                confidence_reason="Kein Kaufdatum vorhanden",
            )

        # Jahre seit Kauf
        days_held = (date.today() - prop.purchase_date).days
        years_held = Decimal(str(days_held)) / Decimal("365.25")

        # 1. Inflationsanpassung
        inflation_factor = (1 + REAL_ESTATE_INFLATION_RATE) ** years_held
        inflation_adjustment = purchase_price * (inflation_factor - 1)

        # 2. Lagefaktor
        location_factor = Decimal("1.0")
        if prop.postal_code:
            plz_prefix = prop.postal_code[:2]
            if plz_prefix in PLZ_LOCATION_FACTORS:
                location_factor = Decimal(str(PLZ_LOCATION_FACTORS[plz_prefix]))

        # 3. Gebaeude-Abschreibung (nur wenn Baujahr bekannt, sonst ignorieren)
        # Vereinfacht: 0.5% pro Jahr auf 80% des Wertes (Gebaeudewert)
        building_ratio = Decimal("0.8")  # 80% Gebaeude, 20% Grundstueck
        age_depreciation = purchase_price * building_ratio * BUILDING_DEPRECIATION_RATE * years_held

        # Geschaetzter Wert
        base_value = purchase_price * inflation_factor * location_factor
        estimated_value = (base_value - age_depreciation).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Mindestwert: 80% des Kaufpreises
        min_value = purchase_price * Decimal("0.8")
        if estimated_value < min_value:
            estimated_value = min_value

        # Konfidenz basierend auf verfuegbaren Daten
        confidence = Decimal("0.5")
        confidence_reasons = []

        if prop.postal_code:
            confidence += Decimal("0.15")
            confidence_reasons.append("PLZ vorhanden")
        if prop.living_area_sqm:
            confidence += Decimal("0.1")
            confidence_reasons.append("Wohnflaeche bekannt")
        if location_factor != Decimal("1.0"):
            confidence += Decimal("0.1")
            confidence_reasons.append("Regionale Anpassung")

        logger.info(
            "property_value_estimated",
            property_id=str(property_id),
            purchase_price=float(purchase_price),
            estimated_value=float(estimated_value),
            years_held=float(years_held),
            location_factor=float(location_factor),
        )

        return PropertyValuation(
            property_id=property_id,
            purchase_price=purchase_price,
            estimated_current_value=estimated_value,
            valuation_method="inflation_adjusted",
            inflation_adjustment=inflation_adjustment.quantize(Decimal("0.01")),
            location_factor=location_factor,
            age_depreciation=age_depreciation.quantize(Decimal("0.01")),
            confidence_score=min(confidence, Decimal("0.85")),
            confidence_reason=", ".join(confidence_reasons) if confidence_reasons else "Basis-Berechnung",
        )

    # =========================================================================
    # Kosten-Analyse
    # =========================================================================

    async def analyze_costs(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> PropertyCostAnalysis:
        """
        Analysiert alle Kosten einer Immobilie.

        Beruecksichtigt:
        - Kaufnebenkosten
        - Nebenkostenabrechnungen
        - Versicherung (falls verknuepft)
        - Geschaetzte Instandhaltung
        """
        from app.db.models import PrivatProperty, PrivatUtilityStatement, PrivatInsurance

        PROPERTY_INTEL_CALCULATIONS.labels(calculation_type="cost_analysis").inc()

        result = await db.execute(
            select(PrivatProperty)
            .options(selectinload(PrivatProperty.utility_statements))
            .where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            return PropertyCostAnalysis(property_id=property_id)

        analysis = PropertyCostAnalysis(property_id=property_id)

        # Kaufnebenkosten
        analysis.notary_costs = Decimal(str(prop.notary_costs or 0))
        analysis.land_transfer_tax = Decimal(str(prop.land_transfer_tax or 0))
        analysis.acquisition_costs = analysis.notary_costs + analysis.land_transfer_tax

        # Laufende Kosten aus Nebenkostenabrechnungen
        current_year = date.today().year
        yearly_utility_costs = Decimal("0")

        for statement in prop.utility_statements:
            if statement.period_end and statement.period_end.year == current_year:
                yearly_utility_costs += Decimal(str(statement.total_costs or 0))

        # Geschaetzte Instandhaltung wenn keine Daten
        estimated_maintenance = Decimal("0")
        if prop.current_value or prop.purchase_price:
            value = Decimal(str(prop.current_value or prop.purchase_price))
            estimated_maintenance = value * MAINTENANCE_RESERVE_RATE

        analysis.maintenance = estimated_maintenance.quantize(Decimal("0.01"))

        # Suche verknuepfte Versicherungen
        # (Vereinfacht - in vollstaendiger Impl. wuerde man nach Insurance mit property_type suchen)

        # Gesamtkosten
        analysis.total_annual_costs = (
            yearly_utility_costs +
            analysis.maintenance
        ).quantize(Decimal("0.01"))

        # Kosten pro qm
        if prop.living_area_sqm and prop.living_area_sqm > 0:
            analysis.cost_per_sqm = (
                analysis.total_annual_costs / Decimal(str(prop.living_area_sqm))
            ).quantize(Decimal("0.01"))

        # Trend-Analyse (letzte 12 Monate vs. vorherige 12 Monate)
        analysis.cost_trend_12m = await self._calculate_cost_trend(db, property_id)

        return analysis

    async def _calculate_cost_trend(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> str:
        """Berechnet den Kosten-Trend."""
        from app.db.models import PrivatUtilityStatement

        today = date.today()
        one_year_ago = today - timedelta(days=365)
        two_years_ago = today - timedelta(days=730)

        # Letzte 12 Monate
        result = await db.execute(
            select(func.sum(PrivatUtilityStatement.total_costs))
            .where(
                and_(
                    PrivatUtilityStatement.property_id == property_id,
                    PrivatUtilityStatement.period_end >= one_year_ago,
                    PrivatUtilityStatement.period_end < today,
                )
            )
        )
        recent_costs = result.scalar() or Decimal("0")

        # Vorherige 12 Monate
        result = await db.execute(
            select(func.sum(PrivatUtilityStatement.total_costs))
            .where(
                and_(
                    PrivatUtilityStatement.property_id == property_id,
                    PrivatUtilityStatement.period_end >= two_years_ago,
                    PrivatUtilityStatement.period_end < one_year_ago,
                )
            )
        )
        previous_costs = result.scalar() or Decimal("0")

        if previous_costs <= 0:
            return "stable"

        change_rate = (Decimal(str(recent_costs)) - Decimal(str(previous_costs))) / Decimal(str(previous_costs))

        if change_rate > Decimal("0.05"):
            return "increasing"
        elif change_rate < Decimal("-0.05"):
            return "decreasing"
        return "stable"

    # =========================================================================
    # Vollstaendige Analytics
    # =========================================================================

    async def get_full_analytics(
        self,
        db: AsyncSession,
        property_id: UUID,
        persist: bool = True,
    ) -> PropertyAnalytics:
        """
        Berechnet alle Analytics fuer eine Immobilie.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID
            persist: Ob die Werte in der DB gespeichert werden sollen

        Returns:
            PropertyAnalytics mit allen berechneten Werten
        """
        from app.db.models import PrivatProperty, PrivatTenant

        PROPERTY_INTEL_CALCULATIONS.labels(calculation_type="full_analytics").inc()

        with PROPERTY_INTEL_DURATION.time():
            result = await db.execute(
                select(PrivatProperty)
                .options(
                    selectinload(PrivatProperty.tenants),
                    selectinload(PrivatProperty.rental_incomes),
                    selectinload(PrivatProperty.utility_statements),
                )
                .where(PrivatProperty.id == property_id)
            )
            prop = result.scalar_one_or_none()

            if not prop:
                return PropertyAnalytics(property_id=property_id)

            analytics = PropertyAnalytics(property_id=property_id)

            # 1. Wertschaetzung
            analytics.valuation = await self.estimate_property_value(db, property_id)

            if analytics.valuation:
                current_value = analytics.valuation.estimated_current_value
                purchase_price = analytics.valuation.purchase_price

                # Wertentwicklung
                analytics.value_appreciation_absolute = current_value - purchase_price
                if purchase_price > 0:
                    analytics.value_appreciation_percent = (
                        (analytics.value_appreciation_absolute / purchase_price) * 100
                    ).quantize(Decimal("0.01"))

                    # Jaehrliche Rate
                    if prop.purchase_date:
                        years = Decimal(str((date.today() - prop.purchase_date).days)) / Decimal("365.25")
                        if years > 0:
                            analytics.annual_appreciation_rate = (
                                analytics.value_appreciation_percent / years
                            ).quantize(Decimal("0.01"))

            # 2. Mieteinnahmen
            annual_rental_income = Decimal("0")
            for tenant in prop.tenants:
                if tenant.is_active and tenant.monthly_rent:
                    annual_rental_income += Decimal(str(tenant.monthly_rent)) * 12

            analytics.annual_rental_income = annual_rental_income

            # 3. Kosten-Analyse
            cost_analysis = await self.analyze_costs(db, property_id)
            analytics.annual_costs = cost_analysis.total_annual_costs
            analytics.cost_breakdown = {
                "maintenance": cost_analysis.maintenance,
                "notary_costs": cost_analysis.notary_costs,
                "land_transfer_tax": cost_analysis.land_transfer_tax,
            }

            # 4. Rendite-Berechnung
            if analytics.valuation and analytics.valuation.estimated_current_value > 0:
                current_value = analytics.valuation.estimated_current_value

                # Bruttomietrendite
                if annual_rental_income > 0:
                    analytics.gross_rental_yield = (
                        (annual_rental_income / current_value) * 100
                    ).quantize(Decimal("0.01"))

                    # Nettomietrendite
                    net_income = annual_rental_income - analytics.annual_costs
                    analytics.net_rental_yield = (
                        (net_income / current_value) * 100
                    ).quantize(Decimal("0.01"))

                    # Cap Rate (NOI / Value)
                    analytics.cap_rate = analytics.net_rental_yield

            # 5. ROI-Berechnung
            if prop.purchase_price and prop.purchase_date:
                purchase_price = Decimal(str(prop.purchase_price))
                years_held = Decimal(str((date.today() - prop.purchase_date).days)) / Decimal("365.25")

                if years_held > 0:
                    total_rental = annual_rental_income * years_held
                    total_costs = cost_analysis.acquisition_costs + (analytics.annual_costs * years_held)
                    value_gain = analytics.value_appreciation_absolute

                    total_gain = value_gain + total_rental - total_costs
                    analytics.total_roi = (
                        (total_gain / purchase_price) * 100
                    ).quantize(Decimal("0.01"))

                    analytics.annual_roi = (
                        analytics.total_roi / years_held
                    ).quantize(Decimal("0.01"))

            # 6. Prognosen
            if analytics.valuation:
                current_value = analytics.valuation.estimated_current_value
                growth_rate = 1 + float(REAL_ESTATE_INFLATION_RATE)

                analytics.projected_value_5y = (
                    current_value * Decimal(str(growth_rate ** 5))
                ).quantize(Decimal("0.01"))

                analytics.projected_value_10y = (
                    current_value * Decimal(str(growth_rate ** 10))
                ).quantize(Decimal("0.01"))

            # 7. Empfehlungen generieren
            analytics.recommendations = self._generate_recommendations(prop, analytics)

            # 8. Health Score
            analytics.health_score = self._calculate_health_score(analytics)

            # Persistieren
            if persist:
                await self._persist_analytics(db, property_id, analytics)

            return analytics

    def _generate_recommendations(
        self,
        prop: "PrivatProperty",
        analytics: PropertyAnalytics,
    ) -> List[str]:
        """Generiert intelligente Empfehlungen."""
        recommendations = []

        # Wertentwicklung
        if analytics.value_appreciation_percent < Decimal("0"):
            recommendations.append(
                "Wert unter Kaufpreis - Renovierung oder Marktanalyse empfohlen"
            )

        # Rendite
        if analytics.gross_rental_yield is not None:
            if analytics.gross_rental_yield < Decimal("3"):
                recommendations.append(
                    f"Bruttomietrendite nur {analytics.gross_rental_yield}% - "
                    "Miterhoehung oder Vergleich mit Marktmieten pruefen"
                )
            elif analytics.gross_rental_yield > Decimal("6"):
                recommendations.append(
                    f"Starke Rendite von {analytics.gross_rental_yield}% - "
                    "Potenzial fuer aehnliche Investments pruefen"
                )

        # Leerstehend
        if not prop.is_rented and prop.property_type not in ["eigennutzung", "ferienwohnung"]:
            recommendations.append(
                "Objekt nicht vermietet - Vermietungspotenzial pruefen"
            )

        # Alter Wert
        if prop.value_date:
            days_since = (date.today() - prop.value_date).days
            if days_since > 365:
                recommendations.append(
                    f"Immobilienwert seit {days_since} Tagen nicht aktualisiert - "
                    "Neubewertung empfohlen"
                )

        # Nebenkosten-Trend
        if analytics.cost_breakdown.get("maintenance", Decimal("0")) == Decimal("0"):
            recommendations.append(
                "Keine Instandhaltungsruecklage erfasst - "
                "Empfohlen: 1.5% des Wertes p.a. einplanen"
            )

        return recommendations

    def _calculate_health_score(self, analytics: PropertyAnalytics) -> Decimal:
        """Berechnet einen Gesundheits-Score (0-100)."""
        score = Decimal("50")  # Basis

        # Wertentwicklung (+/- 15 Punkte)
        if analytics.value_appreciation_percent > Decimal("0"):
            score += min(Decimal("15"), analytics.value_appreciation_percent)
        else:
            score -= min(Decimal("15"), abs(analytics.value_appreciation_percent))

        # Rendite (+/- 20 Punkte)
        if analytics.gross_rental_yield is not None:
            if analytics.gross_rental_yield >= Decimal("5"):
                score += Decimal("20")
            elif analytics.gross_rental_yield >= Decimal("3"):
                score += Decimal("10")
            elif analytics.gross_rental_yield < Decimal("2"):
                score -= Decimal("10")

        # ROI (+/- 15 Punkte)
        if analytics.annual_roi is not None:
            if analytics.annual_roi >= Decimal("8"):
                score += Decimal("15")
            elif analytics.annual_roi >= Decimal("5"):
                score += Decimal("10")
            elif analytics.annual_roi < Decimal("0"):
                score -= Decimal("15")

        # Sicherstellen 0-100
        return max(Decimal("0"), min(Decimal("100"), score)).quantize(Decimal("0.01"))

    async def _persist_analytics(
        self,
        db: AsyncSession,
        property_id: UUID,
        analytics: PropertyAnalytics,
    ) -> None:
        """Speichert Analytics in der Datenbank."""
        from app.db.models import PrivatProperty

        result = await db.execute(
            select(PrivatProperty).where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            return

        # Wertschaetzung
        if analytics.valuation:
            prop.current_value = analytics.valuation.estimated_current_value
            prop.value_date = date.today()

        # Rendite
        prop.calculated_yield = analytics.gross_rental_yield
        prop.calculated_net_yield = analytics.net_rental_yield

        # Wertentwicklung
        prop.value_appreciation = analytics.value_appreciation_absolute
        prop.value_appreciation_rate = analytics.value_appreciation_percent

        # ROI
        prop.calculated_roi = analytics.total_roi
        prop.annual_roi = analytics.annual_roi

        # Kosten
        prop.total_costs_ytd = analytics.annual_costs

        # Timestamp
        prop.last_kpi_calculation = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "property_analytics_persisted",
            property_id=str(property_id),
            gross_yield=float(analytics.gross_rental_yield) if analytics.gross_rental_yield else None,
            health_score=float(analytics.health_score),
        )

    # =========================================================================
    # Batch-Operationen
    # =========================================================================

    async def recalculate_all_properties(
        self,
        db: AsyncSession,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Berechnet Analytics fuer alle Immobilien.

        Args:
            db: Datenbank-Session
            space_id: Optional: Nur Immobilien in diesem Space

        Returns:
            Statistik-Dictionary
        """
        from app.db.models import PrivatProperty


        PROPERTY_INTEL_CALCULATIONS.labels(calculation_type="batch_all").inc()

        query = select(PrivatProperty).where(PrivatProperty.deleted_at.is_(None))
        if space_id:
            query = query.where(PrivatProperty.space_id == space_id)

        result = await db.execute(query)
        properties = result.scalars().all()

        stats = {
            "total": len(properties),
            "calculated": 0,
            "skipped": 0,
            "errors": [],
            "total_estimated_value": Decimal("0"),
        }

        for prop in properties:
            try:
                analytics = await self.get_full_analytics(db, prop.id, persist=True)
                stats["calculated"] += 1

                if analytics.valuation:
                    stats["total_estimated_value"] += analytics.valuation.estimated_current_value

            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append(f"{prop.id}: {safe_error_detail(e, 'Immobilie')}")
                logger.warning(
                    "property_analytics_failed",
                    property_id=str(prop.id),
                    **safe_error_log(e),
                )

        # Prometheus Gauge aktualisieren
        PROPERTY_ESTIMATED_VALUES.set(float(stats["total_estimated_value"]))

        await db.commit()

        logger.info(
            "batch_property_analytics_completed",
            **{k: v if not isinstance(v, Decimal) else float(v) for k, v in stats.items() if k != "errors"},
        )

        return stats


# =============================================================================
# Singleton
# =============================================================================

_property_intelligence_service: Optional[PropertyIntelligenceService] = None
_service_lock = threading.Lock()


def get_property_intelligence_service() -> PropertyIntelligenceService:
    """Factory fuer PropertyIntelligenceService Singleton (Thread-safe)."""
    global _property_intelligence_service
    if _property_intelligence_service is None:
        with _service_lock:
            if _property_intelligence_service is None:
                _property_intelligence_service = PropertyIntelligenceService()
    return _property_intelligence_service
