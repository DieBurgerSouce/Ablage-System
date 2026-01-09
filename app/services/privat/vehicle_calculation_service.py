# -*- coding: utf-8 -*-
"""
VehicleCalculationService - Berechnete Fahrzeug-KPIs.

Berechnet automatisch:
- Total Cost of Ownership (TCO)
- Wertverlust/Abschreibung
- Durchschnittsverbrauch
- Naechster Service

Enterprise Feature - feinpoliert und durchdacht.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

VEHICLE_CALCULATIONS = Counter(
    "vehicle_calculation_requests_total",
    "Anzahl der Fahrzeug-KPI Berechnungen",
    ["calculation_type"]
)

VEHICLE_CALCULATION_DURATION = Histogram(
    "vehicle_calculation_duration_seconds",
    "Dauer der Fahrzeug-KPI Berechnung in Sekunden",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DepreciationResult:
    """Ergebnis der Abschreibungsberechnung."""
    vehicle_id: UUID
    purchase_price: Decimal
    current_estimated_value: Decimal
    total_depreciation: Decimal  # Gesamter Wertverlust
    depreciation_rate: Decimal  # Prozent
    monthly_depreciation: Decimal  # Monatliche Abschreibung
    annual_depreciation: Decimal  # Jaehrliche Abschreibung
    age_months: int
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TCOResult:
    """Ergebnis der TCO-Berechnung."""
    vehicle_id: UUID
    tco_total: Decimal  # Gesamtkosten bisher
    tco_per_km: Optional[Decimal]  # Kosten pro km
    tco_per_month: Decimal  # Monatliche Kosten
    components: Dict[str, Decimal]  # Aufschuesselung
    # components: {"fuel": 5000, "insurance": 1200, "tax": 400, "maintenance": 800, "depreciation": 3000}
    total_km: Optional[int]
    holding_period_months: int
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FuelConsumptionResult:
    """Ergebnis der Verbrauchsanalyse."""
    vehicle_id: UUID
    average_consumption: Optional[Decimal]  # l/100km oder kWh/100km
    total_fuel_cost: Decimal
    total_liters: Decimal
    total_km_tracked: int
    cost_per_km: Optional[Decimal]
    fuel_entries_count: int
    trend: str  # "increasing", "decreasing", "stable"
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ServicePredictionResult:
    """Ergebnis der Service-Vorhersage."""
    vehicle_id: UUID
    next_service_date: Optional[date]
    next_service_km: Optional[int]
    days_until_service: Optional[int]
    km_until_service: Optional[int]
    average_daily_km: Optional[Decimal]
    service_type: str  # "scheduled", "mileage", "tuev", "inspection"
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class VehicleKPIs:
    """Alle berechneten KPIs fuer ein Fahrzeug."""
    vehicle_id: UUID
    depreciation: Optional[DepreciationResult] = None
    tco: Optional[TCOResult] = None
    fuel_consumption: Optional[FuelConsumptionResult] = None
    service_prediction: Optional[ServicePredictionResult] = None
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Abschreibungstabellen
# =============================================================================

# Typische Wertverlust-Kurve nach Jahren (kumulativ)
DEPRECIATION_CURVE = {
    0: Decimal("0"),      # Neuwagen
    1: Decimal("25"),     # Nach 1 Jahr: 25% Wertverlust
    2: Decimal("35"),     # Nach 2 Jahren: 35% kumulativ
    3: Decimal("45"),     # Nach 3 Jahren: 45% kumulativ
    4: Decimal("52"),     # Nach 4 Jahren: 52% kumulativ
    5: Decimal("58"),     # Nach 5 Jahren: 58% kumulativ
    6: Decimal("63"),     # Nach 6 Jahren: 63% kumulativ
    7: Decimal("68"),     # Nach 7 Jahren
    8: Decimal("72"),     # Nach 8 Jahren
    9: Decimal("75"),     # Nach 9 Jahren
    10: Decimal("78"),    # Nach 10 Jahren
}

# Service-Intervalle nach Fahrzeugtyp
SERVICE_INTERVALS = {
    "default": {"km": 15000, "months": 12},
    "diesel": {"km": 20000, "months": 24},
    "electric": {"km": 30000, "months": 24},
    "hybrid": {"km": 15000, "months": 12},
}


# =============================================================================
# Service
# =============================================================================

class VehicleCalculationService:
    """
    Service fuer berechnete Fahrzeug-KPIs.

    Berechnet:
    - Wertverlust/Abschreibung
    - Total Cost of Ownership (TCO)
    - Durchschnittsverbrauch aus Tankdaten
    - Naechster Service-Termin
    """

    def __init__(self) -> None:
        """Initialisiert den Service."""
        pass

    # =========================================================================
    # Wertverlust-Berechnung
    # =========================================================================

    async def calculate_depreciation(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[DepreciationResult]:
        """
        Berechnet den Wertverlust eines Fahrzeugs.

        Nutzt eine typische Abschreibungskurve basierend auf Fahrzeugalter.

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID

        Returns:
            DepreciationResult oder None wenn Berechnung nicht moeglich
        """
        from app.db.models import PrivatVehicle

        VEHICLE_CALCULATIONS.labels(calculation_type="depreciation").inc()

        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            logger.warning(
                "vehicle_not_found_for_depreciation",
                vehicle_id=str(vehicle_id)
            )
            return None

        # Kaufpreis pruefen
        if not vehicle.purchase_price or vehicle.purchase_price <= 0:
            logger.debug(
                "no_purchase_price_for_depreciation",
                vehicle_id=str(vehicle_id)
            )
            return None

        # Kaufdatum pruefen
        if not vehicle.purchase_date:
            logger.debug(
                "no_purchase_date_for_depreciation",
                vehicle_id=str(vehicle_id)
            )
            return None

        # Fahrzeugalter berechnen
        today = date.today()
        age_days = (today - vehicle.purchase_date).days
        age_months = age_days // 30
        age_years = age_days / Decimal("365.25")

        # Wertverlust aus Kurve interpolieren
        year_floor = min(int(age_years), 10)
        year_ceil = min(year_floor + 1, 10)

        depreciation_floor = DEPRECIATION_CURVE.get(year_floor, Decimal("78"))
        depreciation_ceil = DEPRECIATION_CURVE.get(year_ceil, Decimal("78"))

        # Lineare Interpolation
        fraction = age_years - Decimal(year_floor)
        depreciation_rate = depreciation_floor + (depreciation_ceil - depreciation_floor) * fraction
        depreciation_rate = min(depreciation_rate, Decimal("85"))  # Max 85% Wertverlust

        # Werte berechnen
        total_depreciation = vehicle.purchase_price * (depreciation_rate / 100)
        current_value = vehicle.purchase_price - total_depreciation

        # Monatliche/jaehrliche Abschreibung
        if age_months > 0:
            monthly_depreciation = total_depreciation / age_months
            annual_depreciation = monthly_depreciation * 12
        else:
            monthly_depreciation = Decimal("0")
            annual_depreciation = Decimal("0")

        logger.info(
            "vehicle_depreciation_calculated",
            vehicle_id=str(vehicle_id),
            purchase_price=float(vehicle.purchase_price),
            current_value=float(current_value),
            depreciation_rate=float(depreciation_rate),
            age_months=age_months,
        )

        return DepreciationResult(
            vehicle_id=vehicle_id,
            purchase_price=vehicle.purchase_price,
            current_estimated_value=round(current_value, 2),
            total_depreciation=round(total_depreciation, 2),
            depreciation_rate=round(depreciation_rate, 2),
            monthly_depreciation=round(monthly_depreciation, 2),
            annual_depreciation=round(annual_depreciation, 2),
            age_months=age_months,
        )

    # =========================================================================
    # TCO-Berechnung
    # =========================================================================

    async def calculate_tco(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[TCOResult]:
        """
        Berechnet die Total Cost of Ownership (TCO).

        Summiert:
        - Kraftstoffkosten
        - Versicherung (annualisiert)
        - Steuern (geschaetzt)
        - Wartung/Reparaturen
        - Wertverlust

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID

        Returns:
            TCOResult oder None wenn Berechnung nicht moeglich
        """
        from app.db.models import PrivatVehicle, PrivatFuelLog

        VEHICLE_CALCULATIONS.labels(calculation_type="tco").inc()

        result = await db.execute(
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return None

        if not vehicle.purchase_date:
            return None

        # Haltedauer berechnen
        today = date.today()
        holding_days = (today - vehicle.purchase_date).days
        holding_months = max(1, holding_days // 30)

        components: Dict[str, Decimal] = {}

        # 1. Kraftstoffkosten (aus Tankprotokollen)
        fuel_cost = Decimal("0")
        total_km = 0
        if vehicle.fuel_logs:
            for log in vehicle.fuel_logs:
                if log.total_cost:
                    fuel_cost += log.total_cost
            # Gesamtkilometer aus aktuellem Stand minus Kaufstand schaetzen
            if vehicle.current_mileage:
                # Geschaetzt: Mileage bei Kauf war deutlich niedriger
                total_km = vehicle.current_mileage

        components["fuel"] = fuel_cost

        # 2. Versicherung (jaehrlich auf Haltedauer umrechnen)
        insurance_cost = Decimal("0")
        if vehicle.insurance_premium:
            years_held = Decimal(holding_months) / 12
            insurance_cost = vehicle.insurance_premium * years_held
        components["insurance"] = round(insurance_cost, 2)

        # 3. Kfz-Steuer (geschaetzt 200 EUR/Jahr fuer Durchschnittsfahrzeug)
        estimated_tax_per_year = Decimal("200")
        years_held = Decimal(holding_months) / 12
        tax_cost = estimated_tax_per_year * years_held
        components["tax"] = round(tax_cost, 2)

        # 4. Wartung/Reparaturen (geschaetzt 500 EUR/Jahr)
        estimated_maintenance_per_year = Decimal("500")
        maintenance_cost = estimated_maintenance_per_year * years_held
        components["maintenance"] = round(maintenance_cost, 2)

        # 5. Wertverlust
        depreciation = await self.calculate_depreciation(db, vehicle_id)
        if depreciation:
            components["depreciation"] = depreciation.total_depreciation
        else:
            components["depreciation"] = Decimal("0")

        # TCO berechnen
        tco_total = sum(components.values())
        tco_per_month = tco_total / holding_months if holding_months > 0 else Decimal("0")

        # Kosten pro km
        tco_per_km = None
        if total_km and total_km > 0:
            tco_per_km = tco_total / total_km

        logger.info(
            "vehicle_tco_calculated",
            vehicle_id=str(vehicle_id),
            tco_total=float(tco_total),
            tco_per_km=float(tco_per_km) if tco_per_km else None,
            holding_months=holding_months,
        )

        return TCOResult(
            vehicle_id=vehicle_id,
            tco_total=round(tco_total, 2),
            tco_per_km=round(tco_per_km, 3) if tco_per_km else None,
            tco_per_month=round(tco_per_month, 2),
            components=components,
            total_km=total_km if total_km > 0 else None,
            holding_period_months=holding_months,
        )

    # =========================================================================
    # Verbrauchsanalyse
    # =========================================================================

    async def analyze_fuel_consumption(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[FuelConsumptionResult]:
        """
        Analysiert den Kraftstoffverbrauch basierend auf Tankdaten.

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID

        Returns:
            FuelConsumptionResult oder None
        """
        from app.db.models import PrivatVehicle, PrivatFuelLog

        VEHICLE_CALCULATIONS.labels(calculation_type="fuel_consumption").inc()

        result = await db.execute(
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle or not vehicle.fuel_logs:
            return None

        # Sortiere nach Datum
        fuel_logs = sorted(vehicle.fuel_logs, key=lambda x: x.date)

        if len(fuel_logs) < 2:
            return None

        # Gesamtwerte berechnen
        total_cost = Decimal("0")
        total_liters = Decimal("0")
        total_km = 0

        for log in fuel_logs:
            if log.total_cost:
                total_cost += log.total_cost
            if log.amount:
                total_liters += log.amount
            if log.mileage:
                total_km = max(total_km, log.mileage)

        # Kilometer-Differenz zwischen erstem und letztem Eintrag
        first_km = fuel_logs[0].mileage or 0
        last_km = fuel_logs[-1].mileage or 0
        km_tracked = last_km - first_km

        # Durchschnittsverbrauch
        average_consumption = None
        cost_per_km = None
        if km_tracked > 0:
            average_consumption = (total_liters / km_tracked) * 100  # l/100km
            cost_per_km = total_cost / km_tracked

        # Trend erkennen (erste Haelfte vs zweite Haelfte)
        trend = "stable"
        if len(fuel_logs) >= 4:
            mid = len(fuel_logs) // 2
            first_half_consumption = []
            second_half_consumption = []

            for i, log in enumerate(fuel_logs[:-1]):
                next_log = fuel_logs[i + 1]
                if log.mileage and next_log.mileage and log.amount:
                    km_diff = next_log.mileage - log.mileage
                    if km_diff > 0:
                        consumption = (log.amount / km_diff) * 100
                        if i < mid:
                            first_half_consumption.append(consumption)
                        else:
                            second_half_consumption.append(consumption)

            if first_half_consumption and second_half_consumption:
                avg_first = sum(first_half_consumption) / len(first_half_consumption)
                avg_second = sum(second_half_consumption) / len(second_half_consumption)

                if avg_second > avg_first * Decimal("1.05"):
                    trend = "increasing"
                elif avg_second < avg_first * Decimal("0.95"):
                    trend = "decreasing"

        logger.info(
            "vehicle_fuel_consumption_analyzed",
            vehicle_id=str(vehicle_id),
            average_consumption=float(average_consumption) if average_consumption else None,
            entries_count=len(fuel_logs),
            trend=trend,
        )

        return FuelConsumptionResult(
            vehicle_id=vehicle_id,
            average_consumption=round(average_consumption, 2) if average_consumption else None,
            total_fuel_cost=total_cost,
            total_liters=total_liters,
            total_km_tracked=km_tracked,
            cost_per_km=round(cost_per_km, 3) if cost_per_km else None,
            fuel_entries_count=len(fuel_logs),
            trend=trend,
        )

    # =========================================================================
    # Service-Vorhersage
    # =========================================================================

    async def predict_next_service(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
    ) -> Optional[ServicePredictionResult]:
        """
        Sagt den naechsten Servicetermin voraus.

        Beruecksichtigt:
        - Letzte Inspektion/Service
        - Durchschnittliche km-Leistung
        - TUeV-Termin
        - Service-Intervalle nach Fahrzeugtyp

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID

        Returns:
            ServicePredictionResult oder None
        """
        from app.db.models import PrivatVehicle, PrivatFuelLog

        VEHICLE_CALCULATIONS.labels(calculation_type="service_prediction").inc()

        result = await db.execute(
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return None

        today = date.today()

        # 1. TUeV-Termin pruefen (hoechste Prioritaet)
        if vehicle.tuev_due:
            days_until_tuev = (vehicle.tuev_due - today).days
            if days_until_tuev <= 90:  # Innerhalb 3 Monate
                return ServicePredictionResult(
                    vehicle_id=vehicle_id,
                    next_service_date=vehicle.tuev_due,
                    next_service_km=None,
                    days_until_service=days_until_tuev,
                    km_until_service=None,
                    average_daily_km=None,
                    service_type="tuev",
                )

        # 2. Inspektion pruefen
        if vehicle.inspection_due:
            days_until_inspection = (vehicle.inspection_due - today).days
            if days_until_inspection <= 60:  # Innerhalb 2 Monate
                return ServicePredictionResult(
                    vehicle_id=vehicle_id,
                    next_service_date=vehicle.inspection_due,
                    next_service_km=None,
                    days_until_service=days_until_inspection,
                    km_until_service=None,
                    average_daily_km=None,
                    service_type="inspection",
                )

        # 3. Service-Intervall basierend auf km berechnen
        fuel_type = vehicle.fuel_type or "default"
        interval = SERVICE_INTERVALS.get(fuel_type, SERVICE_INTERVALS["default"])

        # Durchschnittliche km-Leistung aus Tankdaten
        average_daily_km = None
        if vehicle.fuel_logs and len(vehicle.fuel_logs) >= 2:
            sorted_logs = sorted(vehicle.fuel_logs, key=lambda x: x.date)
            first_log = sorted_logs[0]
            last_log = sorted_logs[-1]

            if first_log.mileage and last_log.mileage and first_log.date and last_log.date:
                km_diff = last_log.mileage - first_log.mileage
                days_diff = (last_log.date - first_log.date).days

                if days_diff > 0:
                    average_daily_km = Decimal(km_diff) / days_diff

        # Naechsten Service schaetzen
        next_service_date = None
        next_service_km = None
        days_until_service = None
        km_until_service = None

        if vehicle.current_mileage:
            # Naechster Service bei km-Stand
            current_interval = vehicle.current_mileage // interval["km"]
            next_service_km = (current_interval + 1) * interval["km"]
            km_until_service = next_service_km - vehicle.current_mileage

            # Datum schaetzen basierend auf Fahrleistung
            if average_daily_km and average_daily_km > 0:
                days_until = int(km_until_service / average_daily_km)
                next_service_date = today + timedelta(days=days_until)
                days_until_service = days_until
            else:
                # Fallback: 12 Monate
                next_service_date = today + timedelta(days=interval["months"] * 30)
                days_until_service = interval["months"] * 30

        logger.info(
            "vehicle_service_predicted",
            vehicle_id=str(vehicle_id),
            next_service_date=str(next_service_date) if next_service_date else None,
            next_service_km=next_service_km,
            service_type="scheduled",
        )

        return ServicePredictionResult(
            vehicle_id=vehicle_id,
            next_service_date=next_service_date,
            next_service_km=next_service_km,
            days_until_service=days_until_service,
            km_until_service=km_until_service,
            average_daily_km=average_daily_km,
            service_type="scheduled",
        )

    # =========================================================================
    # Alle KPIs berechnen
    # =========================================================================

    async def calculate_all_kpis(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        persist: bool = True,
    ) -> VehicleKPIs:
        """
        Berechnet alle KPIs fuer ein Fahrzeug.

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID
            persist: Ob die Werte in der Datenbank gespeichert werden sollen

        Returns:
            VehicleKPIs mit allen berechneten Werten
        """
        depreciation = await self.calculate_depreciation(db, vehicle_id)
        tco = await self.calculate_tco(db, vehicle_id)
        fuel_consumption = await self.analyze_fuel_consumption(db, vehicle_id)
        service_prediction = await self.predict_next_service(db, vehicle_id)

        kpis = VehicleKPIs(
            vehicle_id=vehicle_id,
            depreciation=depreciation,
            tco=tco,
            fuel_consumption=fuel_consumption,
            service_prediction=service_prediction,
        )

        if persist:
            await self._persist_vehicle_kpis(db, vehicle_id, kpis)

        return kpis

    async def _persist_vehicle_kpis(
        self,
        db: AsyncSession,
        vehicle_id: UUID,
        kpis: VehicleKPIs,
    ) -> None:
        """
        Speichert berechnete KPIs in der Datenbank.

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID
            kpis: Berechnete KPIs
        """
        from app.db.models import PrivatVehicle

        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            return

        # Update depreciation fields
        if kpis.depreciation:
            vehicle.current_estimated_value = kpis.depreciation.current_estimated_value
            vehicle.depreciation_monthly = kpis.depreciation.monthly_depreciation

        # Update TCO fields
        if kpis.tco:
            vehicle.tco_total = kpis.tco.tco_total
            vehicle.tco_per_km = kpis.tco.tco_per_km

        # Update fuel consumption
        if kpis.fuel_consumption:
            vehicle.average_fuel_consumption = kpis.fuel_consumption.average_consumption

        # Update service prediction
        if kpis.service_prediction:
            vehicle.next_service_date = kpis.service_prediction.next_service_date
            vehicle.next_service_km = kpis.service_prediction.next_service_km

        # Update calculation timestamp
        vehicle.last_kpi_calculation = datetime.now(timezone.utc)

        await db.flush()

        logger.info(
            "vehicle_kpis_persisted",
            vehicle_id=str(vehicle_id),
            current_estimated_value=float(vehicle.current_estimated_value) if vehicle.current_estimated_value else None,
            tco_total=float(vehicle.tco_total) if vehicle.tco_total else None,
        )

    # =========================================================================
    # Batch-Berechnung
    # =========================================================================

    async def recalculate_all_vehicles(
        self,
        db: AsyncSession,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Berechnet KPIs fuer alle Fahrzeuge (oder alle in einem Space).

        Args:
            db: Datenbank-Session
            space_id: Optional: Nur Fahrzeuge in diesem Space

        Returns:
            Statistik-Dictionary
        """
        from app.db.models import PrivatVehicle

        VEHICLE_CALCULATIONS.labels(calculation_type="batch_all").inc()

        query = select(PrivatVehicle).where(PrivatVehicle.is_active == True)
        if space_id:
            query = query.where(PrivatVehicle.space_id == space_id)

        result = await db.execute(query)
        vehicles = result.scalars().all()

        stats = {
            "total": len(vehicles),
            "calculated": 0,
            "skipped": 0,
            "errors": [],
        }

        for vehicle in vehicles:
            try:
                await self.calculate_all_kpis(db, vehicle.id)
                stats["calculated"] += 1

            except Exception as e:
                stats["skipped"] += 1
                stats["errors"].append(f"{vehicle.id}: {str(e)}")
                logger.warning(
                    "vehicle_kpi_calculation_failed",
                    vehicle_id=str(vehicle.id),
                    error=str(e),
                )

        logger.info(
            "batch_vehicle_kpi_calculation_completed",
            total=stats["total"],
            calculated=stats["calculated"],
            skipped=stats["skipped"],
        )

        return stats


# =============================================================================
# Singleton
# =============================================================================

_vehicle_calculation_service: Optional[VehicleCalculationService] = None
_service_lock = threading.Lock()


def get_vehicle_calculation_service() -> VehicleCalculationService:
    """Factory fuer VehicleCalculationService Singleton (Thread-safe)."""
    global _vehicle_calculation_service
    if _vehicle_calculation_service is None:
        with _service_lock:
            if _vehicle_calculation_service is None:
                _vehicle_calculation_service = VehicleCalculationService()
    return _vehicle_calculation_service
