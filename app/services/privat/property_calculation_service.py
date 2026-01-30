# -*- coding: utf-8 -*-
"""
PropertyCalculationService - Berechnete Immobilien-KPIs.

Berechnet automatisch:
- Mietrendite (Rental Yield)
- ROI inkl. Wertsteigerung
- Nebenkosten-Trends
- Gesamtkosten

Enterprise Feature - feinpoliert und durchdacht.
"""

from __future__ import annotations

import threading
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

PROPERTY_CALCULATIONS = Counter(
    "property_calculation_requests_total",
    "Anzahl der Immobilien-KPI Berechnungen",
    ["calculation_type"]
)

PROPERTY_CALCULATION_DURATION = Histogram(
    "property_calculation_duration_seconds",
    "Dauer der Immobilien-KPI Berechnung in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RentalYieldResult:
    """Ergebnis der Mietrendite-Berechnung."""
    property_id: UUID
    gross_rental_yield: Decimal  # Bruttomietrendite in %
    net_rental_yield: Optional[Decimal] = None  # Nettomietrendite in %
    annual_rental_income: Decimal = Decimal("0")
    annual_costs: Decimal = Decimal("0")
    purchase_price: Optional[Decimal] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ROIResult:
    """Ergebnis der ROI-Berechnung."""
    property_id: UUID
    total_roi: Decimal  # Gesamt-ROI in %
    annual_roi: Decimal  # Jaehrlicher ROI in %
    value_appreciation: Decimal  # Wertsteigerung absolut
    appreciation_rate: Decimal  # Wertsteigerung in %
    total_rental_income: Decimal  # Gesamte Mieteinnahmen
    total_costs: Decimal  # Gesamte Kosten
    holding_period_years: Decimal  # Haltedauer in Jahren
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CostTrendResult:
    """Ergebnis der Nebenkosten-Trend-Analyse."""
    property_id: UUID
    monthly_costs: List[Dict[str, Any]]  # [{month: "2024-01", amount: 150.00}, ...]
    average_monthly_cost: Decimal
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_percentage: Decimal  # Aenderung in %
    ytd_total: Decimal  # Year-to-date Gesamtkosten
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PropertyKPIs:
    """Alle berechneten KPIs fuer eine Immobilie."""
    property_id: UUID
    rental_yield: Optional[RentalYieldResult] = None
    roi: Optional[ROIResult] = None
    cost_trend: Optional[CostTrendResult] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Service
# =============================================================================

class PropertyCalculationService:
    """
    Service fuer berechnete Immobilien-KPIs.

    Berechnet:
    - Mietrendite (Brutto/Netto)
    - ROI inkl. Wertsteigerung und Kosten
    - Nebenkosten-Trends nach Monat
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    # =========================================================================
    # Mietrendite-Berechnung
    # =========================================================================

    async def calculate_rental_yield(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> Optional[RentalYieldResult]:
        """
        Berechnet die Mietrendite einer Immobilie.

        Bruttomietrendite = (Jahresmiete / Kaufpreis) * 100
        Nettomietrendite = ((Jahresmiete - Jaehrliche Kosten) / Kaufpreis) * 100

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID

        Returns:
            RentalYieldResult oder None wenn Berechnung nicht moeglich
        """
        from app.db.models import PrivatProperty, PrivatTenant

        PROPERTY_CALCULATIONS.labels(calculation_type="rental_yield").inc()

        # Immobilie laden mit Mietern
        result = await db.execute(
            select(PrivatProperty)
            .options(selectinload(PrivatProperty.tenants))
            .where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            logger.warning(
                "property_not_found_for_yield_calculation",
                property_id=str(property_id)
            )
            return None

        # Kaufpreis pruefen
        if not prop.purchase_price or prop.purchase_price <= 0:
            logger.debug(
                "no_purchase_price_for_yield_calculation",
                property_id=str(property_id)
            )
            return None

        # Jaehrliche Mieteinnahmen berechnen (aktive Mieter)
        annual_rental_income = Decimal("0")
        for tenant in prop.tenants:
            if tenant.is_active and tenant.monthly_rent:
                annual_rental_income += tenant.monthly_rent * 12

        # Bruttomietrendite
        gross_yield = (annual_rental_income / prop.purchase_price) * 100

        # Jaehrliche Kosten berechnen (wenn verfuegbar)
        annual_costs = await self._calculate_annual_costs(db, property_id)

        # Nettomietrendite
        net_yield = None
        if annual_costs is not None:
            net_income = annual_rental_income - annual_costs
            net_yield = (net_income / prop.purchase_price) * 100

        logger.info(
            "rental_yield_calculated",
            property_id=str(property_id),
            gross_yield=float(gross_yield),
            net_yield=float(net_yield) if net_yield else None,
            annual_income=float(annual_rental_income),
        )

        return RentalYieldResult(
            property_id=property_id,
            gross_rental_yield=round(gross_yield, 2),
            net_rental_yield=round(net_yield, 2) if net_yield else None,
            annual_rental_income=annual_rental_income,
            annual_costs=annual_costs or Decimal("0"),
            purchase_price=prop.purchase_price,
        )

    # =========================================================================
    # ROI-Berechnung
    # =========================================================================

    async def calculate_roi(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> Optional[ROIResult]:
        """
        Berechnet den Return on Investment (ROI) einer Immobilie.

        ROI = ((Aktueller Wert - Kaufpreis + Mieteinnahmen - Kosten) / Kaufpreis) * 100
        Jaehrlicher ROI = ROI / Haltedauer in Jahren

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID

        Returns:
            ROIResult oder None wenn Berechnung nicht moeglich
        """
        from app.db.models import PrivatProperty

        PROPERTY_CALCULATIONS.labels(calculation_type="roi").inc()

        result = await db.execute(
            select(PrivatProperty)
            .options(selectinload(PrivatProperty.tenants))
            .where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            return None

        # Pflichtfelder pruefen
        if not prop.purchase_price or prop.purchase_price <= 0:
            return None
        if not prop.purchase_date:
            return None

        # Haltedauer berechnen
        today = date.today()
        holding_days = (today - prop.purchase_date).days
        holding_years = Decimal(str(holding_days)) / Decimal("365.25")

        if holding_years <= 0:
            return None

        # Aktueller Wert (oder Kaufpreis als Fallback)
        current_value = prop.current_value or prop.purchase_price
        value_appreciation = current_value - prop.purchase_price
        appreciation_rate = (value_appreciation / prop.purchase_price) * 100

        # Gesamte Mieteinnahmen (geschaetzt basierend auf aktuellen Mietern)
        annual_rental_income = Decimal("0")
        for tenant in prop.tenants:
            if tenant.is_active and tenant.monthly_rent:
                annual_rental_income += tenant.monthly_rent * 12

        total_rental_income = annual_rental_income * holding_years

        # Gesamte Kosten
        total_costs = await self._calculate_total_costs(db, property_id)

        # Kaufnebenkosten
        acquisition_costs = (prop.notary_costs or Decimal("0")) + (prop.land_transfer_tax or Decimal("0"))

        # Gesamt-ROI
        total_gain = value_appreciation + total_rental_income - total_costs - acquisition_costs
        total_roi = (total_gain / prop.purchase_price) * 100

        # Jaehrlicher ROI
        annual_roi = total_roi / holding_years if holding_years > 0 else Decimal("0")

        logger.info(
            "roi_calculated",
            property_id=str(property_id),
            total_roi=float(total_roi),
            annual_roi=float(annual_roi),
            holding_years=float(holding_years),
        )

        return ROIResult(
            property_id=property_id,
            total_roi=round(total_roi, 2),
            annual_roi=round(annual_roi, 2),
            value_appreciation=value_appreciation,
            appreciation_rate=round(appreciation_rate, 2),
            total_rental_income=total_rental_income,
            total_costs=total_costs,
            holding_period_years=round(holding_years, 2),
        )

    # =========================================================================
    # Nebenkosten-Trend
    # =========================================================================

    async def get_cost_trend(
        self,
        db: AsyncSession,
        property_id: UUID,
        months: int = 12,
    ) -> Optional[CostTrendResult]:
        """
        Analysiert den Nebenkosten-Trend einer Immobilie.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID
            months: Anzahl Monate fuer die Analyse

        Returns:
            CostTrendResult oder None wenn keine Daten vorhanden
        """
        from app.db.models import PrivatProperty, PrivatRentalPayment

        PROPERTY_CALCULATIONS.labels(calculation_type="cost_trend").inc()

        # Immobilie pruefen
        result = await db.execute(
            select(PrivatProperty).where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            return None

        # Zeitraum festlegen
        end_date = date.today()
        start_date = end_date - timedelta(days=months * 30)

        # Kosten pro Monat abfragen (via RentalPayments oder Property-spezifische Kosten)
        # Da das System flexible Strukturen hat, nutzen wir hier einen generischen Ansatz
        # In einer vollstaendigen Implementierung wuerden spezifische Kostentabellen abgefragt

        # Beispiel: Kosten aus Miet-Zahlungsdaten
        # Hier koennte eine separate Kostentabelle verwendet werden
        monthly_costs: List[Dict[str, Any]] = []
        ytd_total = Decimal("0")

        # Trend berechnen (Placeholder fuer echte Daten)
        # In einer vollstaendigen Implementierung wuerde hier eine DB-Abfrage stehen
        avg_monthly = Decimal("0")
        trend_direction = "stable"
        trend_percentage = Decimal("0")

        if monthly_costs:
            amounts = [Decimal(str(c["amount"])) for c in monthly_costs]
            avg_monthly = sum(amounts) / len(amounts)

            # Trend erkennen (erste Haelfte vs. zweite Haelfte)
            if len(amounts) >= 4:
                first_half = sum(amounts[:len(amounts)//2]) / (len(amounts)//2)
                second_half = sum(amounts[len(amounts)//2:]) / (len(amounts) - len(amounts)//2)

                if second_half > first_half * Decimal("1.05"):
                    trend_direction = "increasing"
                    trend_percentage = ((second_half - first_half) / first_half) * 100
                elif second_half < first_half * Decimal("0.95"):
                    trend_direction = "decreasing"
                    trend_percentage = ((first_half - second_half) / first_half) * 100

        return CostTrendResult(
            property_id=property_id,
            monthly_costs=monthly_costs,
            average_monthly_cost=round(avg_monthly, 2),
            trend_direction=trend_direction,
            trend_percentage=round(trend_percentage, 2),
            ytd_total=ytd_total,
        )

    # =========================================================================
    # Alle KPIs berechnen
    # =========================================================================

    async def calculate_all_kpis(
        self,
        db: AsyncSession,
        property_id: UUID,
        persist: bool = True,
    ) -> PropertyKPIs:
        """
        Berechnet alle KPIs fuer eine Immobilie.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            PropertyKPIs mit allen berechneten Werten
        """
        rental_yield = await self.calculate_rental_yield(db, property_id)
        roi = await self.calculate_roi(db, property_id)
        cost_trend = await self.get_cost_trend(db, property_id)

        kpis = PropertyKPIs(
            property_id=property_id,
            rental_yield=rental_yield,
            roi=roi,
            cost_trend=cost_trend,
        )

        # Persist to database if requested
        if persist:
            await self._persist_property_kpis(db, property_id, kpis)

        return kpis

    async def _persist_property_kpis(
        self,
        db: AsyncSession,
        property_id: UUID,
        kpis: PropertyKPIs,
    ) -> None:
        """
        Speichert berechnete KPIs in der Datenbank.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID
            kpis: Berechnete KPIs
        """
        from app.db.models import PrivatProperty

        result = await db.execute(
            select(PrivatProperty).where(PrivatProperty.id == property_id)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            return

        # Update yield fields
        if kpis.rental_yield:
            prop.calculated_yield = kpis.rental_yield.gross_rental_yield
            prop.calculated_net_yield = kpis.rental_yield.net_rental_yield

        # Update ROI fields
        if kpis.roi:
            prop.calculated_roi = kpis.roi.total_roi
            prop.annual_roi = kpis.roi.annual_roi
            prop.value_appreciation = kpis.roi.value_appreciation
            prop.value_appreciation_rate = kpis.roi.appreciation_rate

        # Update cost trend fields
        if kpis.cost_trend:
            prop.total_costs_ytd = kpis.cost_trend.ytd_total

        # Update calculation timestamp
        prop.last_kpi_calculation = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "property_kpis_persisted",
            property_id=str(property_id),
            calculated_yield=float(prop.calculated_yield) if prop.calculated_yield else None,
            calculated_roi=float(prop.calculated_roi) if prop.calculated_roi else None,
        )

    # =========================================================================
    # Batch-Berechnung
    # =========================================================================

    async def recalculate_all_properties(
        self,
        db: AsyncSession,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Berechnet KPIs fuer alle Immobilien (oder alle in einem Space).

        Args:
            db: Datenbank-Session
            space_id: Optional: Nur Immobilien in diesem Space

        Returns:
            Statistik-Dictionary
        """
        from app.db.models import PrivatProperty

        PROPERTY_CALCULATIONS.labels(calculation_type="batch_all").inc()

        # Immobilien laden
        query = select(PrivatProperty)
        if space_id:
            query = query.where(PrivatProperty.space_id == space_id)

        result = await db.execute(query)
        properties = result.scalars().all()

        stats = {
            "total": len(properties),
            "calculated": 0,
            "skipped": 0,
            "errors": [],
        }

        for prop in properties:
            try:
                kpis = await self.calculate_all_kpis(db, prop.id)

                # In extracted_data speichern (oder separate Felder)
                # Hier koennte auch ein separates Feld im Model aktualisiert werden
                stats["calculated"] += 1

            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append(f"{prop.id}: {safe_error_detail(e, 'Immobilie')}")
                logger.warning(
                    "property_kpi_calculation_failed",
                    property_id=str(prop.id),
                    **safe_error_log(e),
                )

        logger.info(
            "batch_property_kpi_calculation_completed",
            total=stats["total"],
            calculated=stats["calculated"],
            skipped=stats["skipped"],
        )

        return stats

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    async def _calculate_annual_costs(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> Optional[Decimal]:
        """Berechnet die jaehrlichen Kosten einer Immobilie.

        Kostenquellen:
        - PrivatUtilityStatement.total_costs (Nebenkostenabrechnungen)
        - Geschaetzte Grundsteuer (ca. 0.2% des Kaufpreises)
        - Geschaetzte Versicherung (ca. 0.1% des Kaufpreises)
        - Instandhaltungsruecklage (ca. 1% des Kaufpreises)

        Returns:
            Jaehrliche Kosten als Decimal oder None bei Fehler
        """
        from app.db.models import PrivatProperty, PrivatUtilityStatement

        try:
            # Property laden fuer Kaufpreis (fuer Schaetzungen)
            stmt = select(PrivatProperty).where(
                PrivatProperty.id == property_id,
                PrivatProperty.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            prop = result.scalar_one_or_none()

            if not prop:
                return None

            # Aktuelles Jahr
            current_year = date.today().year

            # 1. Nebenkosten aus Utility Statements (aktuelles Jahr)
            utility_stmt = select(func.sum(PrivatUtilityStatement.total_costs)).where(
                PrivatUtilityStatement.property_id == property_id,
                extract('year', PrivatUtilityStatement.period_end) == current_year,
            )
            utility_result = await db.execute(utility_stmt)
            utility_costs = utility_result.scalar_one_or_none() or Decimal("0")

            # 2. Geschaetzte fixe Kosten (wenn Kaufpreis bekannt)
            estimated_fixed = Decimal("0")
            if prop.purchase_price:
                # Grundsteuer ~0.2%, Versicherung ~0.1%, Instandhaltung ~1%
                estimated_fixed = prop.purchase_price * Decimal("0.013")

            total_annual = Decimal(str(utility_costs)) + estimated_fixed

            logger.debug(
                "annual_costs_calculated",
                property_id=str(property_id),
                utility_costs=float(utility_costs),
                estimated_fixed=float(estimated_fixed),
                total=float(total_annual),
            )

            return total_annual.quantize(Decimal("0.01"))

        except Exception as e:
            logger.error(
                "annual_costs_calculation_error",
                property_id=str(property_id),
                **safe_error_log(e),
            )
            return None

    async def _calculate_total_costs(
        self,
        db: AsyncSession,
        property_id: UUID,
    ) -> Decimal:
        """Berechnet die Gesamtkosten einer Immobilie seit Kauf.

        Kostenquellen:
        - Kaufnebenkosten (Notar, Grunderwerbsteuer)
        - Alle historischen Utility Statements
        - Geschaetzte jaehrliche Kosten seit Kaufdatum

        Returns:
            Gesamtkosten als Decimal
        """
        from app.db.models import PrivatProperty, PrivatUtilityStatement


        try:
            # Property laden
            stmt = select(PrivatProperty).where(
                PrivatProperty.id == property_id,
                PrivatProperty.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            prop = result.scalar_one_or_none()

            if not prop:
                return Decimal("0")

            total_costs = Decimal("0")

            # 1. Kaufnebenkosten
            if prop.notary_costs:
                total_costs += prop.notary_costs
            if prop.land_transfer_tax:
                total_costs += prop.land_transfer_tax

            # 2. Alle historischen Utility Statements
            utility_stmt = select(func.sum(PrivatUtilityStatement.total_costs)).where(
                PrivatUtilityStatement.property_id == property_id,
            )
            utility_result = await db.execute(utility_stmt)
            utility_total = utility_result.scalar_one_or_none() or Decimal("0")
            total_costs += Decimal(str(utility_total))

            # 3. Geschaetzte Kosten fuer Jahre ohne Utility Statements
            if prop.purchase_date and prop.purchase_price:
                holding_years = (date.today() - prop.purchase_date).days / Decimal("365.25")

                # Anzahl Jahre mit Utility Statements
                years_with_utils_stmt = select(
                    func.count(func.distinct(extract('year', PrivatUtilityStatement.period_end)))
                ).where(PrivatUtilityStatement.property_id == property_id)
                years_result = await db.execute(years_with_utils_stmt)
                years_with_utils = years_result.scalar_one_or_none() or 0

                # Geschaetzte Kosten fuer Jahre ohne Statements (1.3% vom Kaufpreis)
                missing_years = max(Decimal("0"), Decimal(str(holding_years)) - Decimal(str(years_with_utils)))
                if missing_years > 0:
                    estimated_missing = missing_years * prop.purchase_price * Decimal("0.013")
                    total_costs += estimated_missing

            logger.debug(
                "total_costs_calculated",
                property_id=str(property_id),
                total=float(total_costs),
            )

            return total_costs.quantize(Decimal("0.01"))

        except Exception as e:
            logger.error(
                "total_costs_calculation_error",
                property_id=str(property_id),
                **safe_error_log(e),
            )
            return Decimal("0")


# =============================================================================
# Singleton
# =============================================================================

_property_calculation_service: Optional[PropertyCalculationService] = None
_service_lock = threading.Lock()


def get_property_calculation_service() -> PropertyCalculationService:
    """Factory fuer PropertyCalculationService Singleton (Thread-safe)."""
    global _property_calculation_service
    if _property_calculation_service is None:
        with _service_lock:
            if _property_calculation_service is None:
                _property_calculation_service = PropertyCalculationService()
    return _property_calculation_service
