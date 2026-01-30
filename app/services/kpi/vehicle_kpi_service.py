"""Vehicle KPI Service fuer Fahrzeug-Berechnungen.

Berechnet alle Fahrzeug-bezogenen KPIs:
- TCO (Total Cost of Ownership)
- Abschreibung
- Verbrauchskosten
- Restwert

Enterprise Features:
- Multi-Tenant Security via space_id
- Echte DB-Integration mit SQLAlchemy
- KPI-Persistenz in DB
- Structured Logging
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PrivatVehicle, PrivatFuelLog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class VehicleKPIResult:
    """Ergebnis der Vehicle-KPI-Berechnung."""

    # Wert-KPIs
    current_estimated_value: Decimal
    depreciation_monthly: Decimal
    depreciation_total: Decimal

    # TCO-KPIs
    tco_total: Decimal
    tco_per_km: Decimal
    tco_per_month: Decimal

    # Verbrauchs-KPIs
    average_fuel_consumption: Decimal
    fuel_cost_per_km: Decimal

    # Service-KPIs
    next_service_date: Optional[date]
    days_until_service: int


class VehicleKPIService:
    """Service fuer Fahrzeug-KPI-Berechnungen.

    Berechnet automatisch alle relevanten KPIs fuer Fahrzeuge
    basierend auf Kaufpreis, Alter, Kilometerstand und Betriebskosten.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def calculate_all_kpis(
        self,
        vehicle_id: UUID,
        space_id: UUID,
        persist: bool = True
    ) -> VehicleKPIResult:
        """Berechnet alle KPIs fuer ein Fahrzeug.

        Args:
            vehicle_id: UUID des Fahrzeugs
            space_id: UUID des Space (Multi-Tenant Security!)
            persist: Ob KPIs in DB persistiert werden sollen

        Returns:
            VehicleKPIResult mit allen berechneten KPIs

        Raises:
            ValueError: Wenn Fahrzeug nicht gefunden oder Zugriff verweigert
        """
        logger.info(
            "vehicle_kpi_calculation_started",
            vehicle_id=str(vehicle_id),
            space_id=str(space_id),
        )

        vehicle = await self._get_vehicle(vehicle_id, space_id)
        fuel_logs = await self._get_fuel_logs(vehicle_id, space_id)

        current_value = self._calc_current_value(vehicle)
        tco_total = self._calc_tco_total(vehicle)

        result = VehicleKPIResult(
            current_estimated_value=current_value,
            depreciation_monthly=self._calc_monthly_depreciation(vehicle),
            depreciation_total=self._calc_total_depreciation(vehicle),
            tco_total=tco_total,
            tco_per_km=self._calc_tco_per_km(vehicle, tco_total),
            tco_per_month=self._calc_tco_per_month(vehicle, tco_total),
            average_fuel_consumption=self._calc_avg_consumption(fuel_logs),
            fuel_cost_per_km=self._calc_fuel_cost_per_km(fuel_logs),
            next_service_date=self._calc_next_service(vehicle),
            days_until_service=self._calc_days_until_service(vehicle),
        )

        if persist:
            await self._persist_kpis(vehicle, result)

        logger.info(
            "vehicle_kpi_calculation_completed",
            vehicle_id=str(vehicle_id),
            tco_total=str(result.tco_total),
            current_value=str(result.current_estimated_value),
        )

        return result

    async def _persist_kpis(
        self,
        vehicle: PrivatVehicle,
        result: VehicleKPIResult
    ) -> None:
        """Persistiert berechnete KPIs in der Datenbank."""
        vehicle.current_estimated_value = result.current_estimated_value
        vehicle.depreciation_monthly = result.depreciation_monthly
        vehicle.tco_total = result.tco_total
        vehicle.tco_per_km = result.tco_per_km
        vehicle.average_fuel_consumption = result.average_fuel_consumption
        vehicle.next_service_date = result.next_service_date
        vehicle.last_kpi_calculation = datetime.now(timezone.utc)

        await self.db.commit()

        logger.debug(
            "vehicle_kpis_persisted",
            vehicle_id=str(vehicle.id),
        )

    def _calc_current_value(self, vehicle: PrivatVehicle) -> Decimal:
        """Berechnet den geschaetzten aktuellen Restwert.

        Verwendet eine degressive Abschreibung:
        - Jahr 1: 15% Wertverlust
        - Ab Jahr 2: 10% pro Jahr
        - Maximum: 80% Gesamtabschreibung
        """
        age_months = self._calc_age_months(vehicle.purchase_date)

        if age_months <= 12:
            depreciation_rate = Decimal("0.15")
        else:
            years = age_months / 12
            depreciation_rate = Decimal("0.15") + (Decimal(str(years)) - 1) * Decimal("0.10")

        # Maximum 80% Abschreibung
        depreciation_rate = min(depreciation_rate, Decimal("0.80"))

        result = vehicle.purchase_price * (1 - depreciation_rate)
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_monthly_depreciation(self, vehicle: PrivatVehicle) -> Decimal:
        """Berechnet die monatliche Abschreibung."""
        total_depreciation = self._calc_total_depreciation(vehicle)
        age_months = max(self._calc_age_months(vehicle.purchase_date), 1)

        result = total_depreciation / Decimal(str(age_months))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_total_depreciation(self, vehicle: PrivatVehicle) -> Decimal:
        """Berechnet die gesamte bisherige Abschreibung."""
        current_value = self._calc_current_value(vehicle)
        return vehicle.purchase_price - current_value

    def _calc_tco_total(self, vehicle: PrivatVehicle) -> Decimal:
        """Berechnet die Total Cost of Ownership.

        TCO = Kaufpreis + Betriebskosten - Restwert

        Note: Das DB-Model hat insurance_premium (jaehrlich) aber keine
        separaten Felder fuer Steuer/Wartung/Kraftstoff.
        Wir verwenden die Versicherungspraemie als einzige bekannte Betriebskosten.
        """
        if not vehicle.purchase_price or not vehicle.purchase_date:
            return Decimal("0")

        # Jaehrliche Betriebskosten aus bekannten Feldern
        # insurance_premium ist die Versicherungspraemie
        insurance_annual = Decimal(str(vehicle.insurance_premium or 0))

        # Leasingrate als laufende Kosten (falls geleast)
        if vehicle.is_leased and vehicle.monthly_rate:
            leasing_annual = Decimal(str(vehicle.monthly_rate)) * 12
        else:
            leasing_annual = Decimal("0")

        operating_costs_annual = insurance_annual + leasing_annual

        # Gesamte Betriebskosten ueber Besitzdauer
        age_years = self._calc_age_months(vehicle.purchase_date) / 12
        total_operating = operating_costs_annual * Decimal(str(max(age_years, 1)))

        # Restwert
        residual = self._calc_current_value(vehicle)

        # TCO = Kaufpreis + Betriebskosten - Restwert
        purchase_price = Decimal(str(vehicle.purchase_price))
        result = purchase_price + total_operating - residual
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_tco_per_km(self, vehicle: PrivatVehicle, tco_total: Decimal) -> Decimal:
        """Berechnet TCO pro Kilometer."""
        current_km = vehicle.current_mileage or 0
        # PrivatVehicle hat kein initial_mileage - benutze 0 als Basis
        driven_km = current_km

        if driven_km <= 0:
            return Decimal("0")

        result = tco_total / Decimal(str(driven_km))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_tco_per_month(self, vehicle: PrivatVehicle, tco_total: Decimal) -> Decimal:
        """Berechnet TCO pro Monat."""
        if not vehicle.purchase_date:
            return Decimal("0")

        age_months = max(self._calc_age_months(vehicle.purchase_date), 1)

        result = tco_total / Decimal(str(age_months))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_avg_consumption(self, fuel_logs: list[PrivatFuelLog]) -> Decimal:
        """Berechnet den Durchschnittsverbrauch.

        Args:
            fuel_logs: Liste von Tankprotokollen

        Returns:
            Durchschnittsverbrauch in l/100km
        """
        if not fuel_logs or len(fuel_logs) < 2:
            return Decimal("0")

        total_liters = sum(log.liters for log in fuel_logs[1:])  # Erste Tankung ignorieren
        total_km = fuel_logs[-1].mileage - fuel_logs[0].mileage

        if total_km <= 0:
            return Decimal("0")

        result = (total_liters / Decimal(str(total_km))) * 100
        return result.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    def _calc_fuel_cost_per_km(self, fuel_logs: list[PrivatFuelLog]) -> Decimal:
        """Berechnet die Kraftstoffkosten pro km."""
        if not fuel_logs or len(fuel_logs) < 2:
            return Decimal("0")

        total_cost = sum(log.total_cost for log in fuel_logs[1:])
        total_km = fuel_logs[-1].mileage - fuel_logs[0].mileage

        if total_km <= 0:
            return Decimal("0")

        result = total_cost / Decimal(str(total_km))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_next_service(self, vehicle: PrivatVehicle) -> Optional[date]:
        """Berechnet das naechste Service-Datum."""
        last_service = getattr(vehicle, 'last_service_date', None)
        service_interval_months = getattr(vehicle, 'service_interval_months', 12)

        if not last_service:
            # Falls kein Service, 1 Jahr nach Kauf
            return vehicle.purchase_date + timedelta(days=365)

        return last_service + timedelta(days=service_interval_months * 30)

    def _calc_days_until_service(self, vehicle: PrivatVehicle) -> int:
        """Berechnet Tage bis zum naechsten Service."""
        next_service = self._calc_next_service(vehicle)
        if not next_service:
            return 365

        delta = next_service - date.today()
        return max(delta.days, 0)

    def _calc_age_months(self, purchase_date: date) -> int:
        """Berechnet das Alter in Monaten."""
        today = date.today()
        delta = today - purchase_date
        return max(int(delta.days / 30), 1)

    async def _get_vehicle(self, vehicle_id: UUID, space_id: UUID) -> PrivatVehicle:
        """Laedt Vehicle aus der Datenbank mit Multi-Tenant Security.

        Args:
            vehicle_id: UUID des Fahrzeugs
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            PrivatVehicle Objekt

        Raises:
            ValueError: Wenn Fahrzeug nicht gefunden oder Zugriff verweigert
        """
        stmt = (
            select(PrivatVehicle)
            .options(selectinload(PrivatVehicle.fuel_logs))
            .where(
                PrivatVehicle.id == vehicle_id,
                PrivatVehicle.space_id == space_id,  # Multi-Tenant Security!
                PrivatVehicle.deleted_at.is_(None),
            )
        )

        result = await self.db.execute(stmt)
        vehicle = result.scalar_one_or_none()

        if not vehicle:
            logger.warning(
                "vehicle_not_found_or_access_denied",
                vehicle_id=str(vehicle_id),
                space_id=str(space_id),
            )
            raise ValueError(
                f"Fahrzeug {vehicle_id} nicht gefunden oder Zugriff verweigert"
            )

        return vehicle

    async def _get_fuel_logs(
        self,
        vehicle_id: UUID,
        space_id: UUID
    ) -> list[PrivatFuelLog]:
        """Laedt Tankprotokolle mit Multi-Tenant Security.

        Args:
            vehicle_id: UUID des Fahrzeugs
            space_id: UUID des Space (Multi-Tenant Security!)

        Returns:
            Liste von PrivatFuelLog Objekten sortiert nach Datum
        """
        # Join ueber Vehicle um Multi-Tenant zu pruefen
        stmt = (
            select(PrivatFuelLog)
            .join(PrivatVehicle, PrivatFuelLog.vehicle_id == PrivatVehicle.id)
            .where(
                PrivatFuelLog.vehicle_id == vehicle_id,
                PrivatVehicle.space_id == space_id,  # Multi-Tenant Security!
            )
            .order_by(PrivatFuelLog.date.asc(), PrivatFuelLog.mileage.asc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def calculate_all_vehicles_for_space(
        self,
        space_id: UUID,
        persist: bool = True
    ) -> dict[UUID, VehicleKPIResult]:
        """Berechnet KPIs fuer alle Fahrzeuge eines Space.

        Batch-Methode fuer Celery Tasks.

        Args:
            space_id: UUID des Space
            persist: Ob KPIs persistiert werden sollen

        Returns:
            Dict von vehicle_id -> VehicleKPIResult
        """
        logger.info(
            "batch_vehicle_kpi_calculation_started",
            space_id=str(space_id),
        )

        # Alle aktiven Fahrzeuge des Space laden
        stmt = (
            select(PrivatVehicle)
            .where(
                PrivatVehicle.space_id == space_id,
                PrivatVehicle.deleted_at.is_(None),
                PrivatVehicle.is_active.is_(True),
            )
        )

        result = await self.db.execute(stmt)
        vehicles = result.scalars().all()

        results: dict[UUID, VehicleKPIResult] = {}
        success_count = 0
        error_count = 0

        for vehicle in vehicles:
            try:
                kpi_result = await self.calculate_all_kpis(
                    vehicle_id=vehicle.id,
                    space_id=space_id,
                    persist=persist,
                )
                results[vehicle.id] = kpi_result
                success_count += 1
            except Exception as e:
                logger.error(
                    "vehicle_kpi_calculation_failed",
                    vehicle_id=str(vehicle.id),
                    **safe_error_log(e),
                )
                error_count += 1

        logger.info(
            "batch_vehicle_kpi_calculation_completed",
            space_id=str(space_id),
            total=len(vehicles),
            success=success_count,
            errors=error_count,
        )

        return results
