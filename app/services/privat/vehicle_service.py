"""Service fuer die Verwaltung von Fahrzeugen im Privat-Modul."""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatVehicle, PrivatFuelLog
from app.db.schemas import (
    PrivatVehicleCreate,
    PrivatVehicleUpdate,
    PrivatVehicleResponse,
    PrivatVehicleWithLogs,
    PrivatVehicleListResponse,
    PrivatFuelLogCreate,
    PrivatFuelLogUpdate,
    PrivatFuelLogResponse,
    VehicleType,
    FuelType,
)

logger = structlog.get_logger(__name__)


class PrivatVehicleService:
    """Service fuer Fahrzeuge und Tankbelege."""

    # ========== Vehicle CRUD ==========

    async def create_vehicle(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatVehicleCreate,
    ) -> PrivatVehicle:
        """Erstellt ein neues Fahrzeug.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Fahrzeug-Daten

        Returns:
            Erstelltes Fahrzeug
        """
        vehicle = PrivatVehicle(
            id=uuid.uuid4(),
            space_id=space_id,
            name=data.name,
            vehicle_type=data.vehicle_type.value if isinstance(data.vehicle_type, VehicleType) else data.vehicle_type,
            make=data.make,
            model=data.model,
            year=data.year,
            license_plate=data.license_plate,
            vin=data.vin,
            fuel_type=data.fuel_type.value if isinstance(data.fuel_type, FuelType) else data.fuel_type,
            mileage=data.mileage,
            purchase_date=data.purchase_date,
            purchase_price=data.purchase_price,
            current_value=data.current_value,
            next_inspection=data.next_inspection,
            next_service=data.next_service,
            notes=data.notes,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)

        logger.info(
            "privat_vehicle_created",
            vehicle_id=str(vehicle.id),
            space_id=str(space_id),
        )

        return vehicle

    async def get_vehicle(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
    ) -> Optional[PrivatVehicle]:
        """Holt ein Fahrzeug nach ID."""
        result = await db.execute(
            select(PrivatVehicle).where(PrivatVehicle.id == vehicle_id)
        )
        return result.scalar_one_or_none()

    async def get_vehicle_with_access_check(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatVehicle]:
        """IDOR-sichere Methode: Holt Fahrzeug nur wenn User Zugriff hat.

        SECURITY: Gibt einheitlich None zurueck bei:
        - Fahrzeug existiert nicht
        - User hat keinen Zugriff

        Dies verhindert Information Disclosure ueber Existenz von Fahrzeugen.

        Args:
            db: Datenbank-Session
            vehicle_id: Fahrzeug-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Fahrzeug wenn vorhanden und Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # Join mit Space um Owner zu pruefen
        result = await db.execute(
            select(PrivatVehicle, PrivatSpace)
            .join(PrivatSpace, PrivatVehicle.space_id == PrivatSpace.id)
            .where(PrivatVehicle.id == vehicle_id)
        )
        row = result.first()

        if not row:
            return None

        vehicle, space = row

        # Owner hat immer Zugriff
        if space.owner_id == requesting_user_id:
            return vehicle

        # Pruefe explizite Berechtigung
        now = datetime.utcnow()
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now,
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            # SECURITY: Log IDOR-Versuch ohne sensible Details
            logger.warning(
                "idor_vehicle_attempt_blocked",
                vehicle_id=str(vehicle_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return vehicle

    async def list_vehicles(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatVehicleListResponse:
        """Listet alle Fahrzeuge eines Spaces."""
        conditions = [PrivatVehicle.space_id == space_id]
        if active_only:
            conditions.append(PrivatVehicle.is_active == True)

        # Count
        count_result = await db.execute(
            select(func.count(PrivatVehicle.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatVehicle)
            .where(and_(*conditions))
            .order_by(PrivatVehicle.name)
            .offset(offset)
            .limit(page_size)
        )
        vehicles = result.scalars().all()

        # Mit Tankdaten anreichern
        items = []
        for veh in vehicles:
            recent_logs = await self._get_recent_fuel_logs(db, veh.id, limit=5)
            fuel_cost = await self._get_yearly_fuel_cost(db, veh.id)
            avg_consumption = await self._calculate_average_consumption(db, veh.id)

            items.append(PrivatVehicleWithLogs(
                id=veh.id,
                space_id=veh.space_id,
                name=veh.name,
                vehicle_type=VehicleType(veh.vehicle_type),
                make=veh.make,
                model=veh.model,
                year=veh.year,
                license_plate=veh.license_plate,
                vin=veh.vin,
                fuel_type=FuelType(veh.fuel_type),
                mileage=veh.mileage,
                purchase_date=veh.purchase_date,
                purchase_price=veh.purchase_price,
                current_value=veh.current_value,
                next_inspection=veh.next_inspection,
                next_service=veh.next_service,
                notes=veh.notes,
                is_active=veh.is_active,
                created_at=veh.created_at,
                updated_at=veh.updated_at,
                recent_fuel_logs=recent_logs,
                total_fuel_cost_year=fuel_cost,
                average_consumption=avg_consumption,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatVehicleListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def _get_recent_fuel_logs(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        limit: int = 5,
    ) -> List[PrivatFuelLogResponse]:
        """Holt die letzten Tankbelege."""
        result = await db.execute(
            select(PrivatFuelLog)
            .where(PrivatFuelLog.vehicle_id == vehicle_id)
            .order_by(PrivatFuelLog.date.desc())
            .limit(limit)
        )
        logs = result.scalars().all()
        return [self._to_fuel_log_response(log) for log in logs]

    async def _get_yearly_fuel_cost(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet die Kraftstoffkosten des aktuellen Jahres."""
        current_year = date.today().year
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatFuelLog.total_price), 0))
            .where(
                PrivatFuelLog.vehicle_id == vehicle_id,
                func.extract("year", PrivatFuelLog.date) == current_year,
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def _calculate_average_consumption(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
    ) -> Optional[Decimal]:
        """Berechnet den Durchschnittsverbrauch (L/100km)."""
        # Hole die letzten Tankbelege mit Volltankung
        result = await db.execute(
            select(PrivatFuelLog)
            .where(
                PrivatFuelLog.vehicle_id == vehicle_id,
                PrivatFuelLog.is_full_tank == True,
            )
            .order_by(PrivatFuelLog.mileage.desc())
            .limit(10)
        )
        logs = list(result.scalars().all())

        if len(logs) < 2:
            return None

        # Berechne Verbrauch zwischen Volltankungen
        total_liters = Decimal("0")
        total_km = 0

        for i in range(len(logs) - 1):
            km_diff = logs[i].mileage - logs[i + 1].mileage
            if km_diff > 0:
                total_liters += logs[i].liters
                total_km += km_diff

        if total_km == 0:
            return None

        return (total_liters * 100) / total_km

    async def update_vehicle(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        data: PrivatVehicleUpdate,
    ) -> Optional[PrivatVehicle]:
        """Aktualisiert ein Fahrzeug.

        SECURITY FIX 23-5: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Fahrzeugdaten entstehen
        """
        # SECURITY FIX 23-5: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatVehicle)
            .where(PrivatVehicle.id == vehicle_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Fahrzeugdaten!
        )
        vehicle = result.scalar_one_or_none()
        if not vehicle:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "vehicle_type" and value:
                value = value.value if isinstance(value, VehicleType) else value
            elif key == "fuel_type" and value:
                value = value.value if isinstance(value, FuelType) else value
            setattr(vehicle, key, value)

        vehicle.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(vehicle)

        return vehicle

    async def delete_vehicle(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Loescht ein Fahrzeug.

        SECURITY FIX 23-6: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen
        """
        # SECURITY FIX 23-6: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatVehicle)
            .where(PrivatVehicle.id == vehicle_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        vehicle = result.scalar_one_or_none()
        if not vehicle:
            return False

        if soft_delete:
            vehicle.is_active = False
            vehicle.updated_at = datetime.utcnow()
            await db.commit()
        else:
            await db.delete(vehicle)
            await db.commit()

        return True

    # ========== Fuel Log CRUD ==========

    async def create_fuel_log(
        self,
        db: AsyncSession,
        data: PrivatFuelLogCreate,
    ) -> PrivatFuelLog:
        """Erstellt einen neuen Tankbeleg."""
        # Berechne Verbrauch wenn moeglich
        consumption = await self._calculate_consumption_for_log(
            db, data.vehicle_id, data.mileage, data.liters, data.is_full_tank
        )

        log = PrivatFuelLog(
            id=uuid.uuid4(),
            vehicle_id=data.vehicle_id,
            date=data.date,
            mileage=data.mileage,
            liters=data.liters,
            price_per_liter=data.price_per_liter,
            total_price=data.total_price,
            fuel_type=data.fuel_type.value if isinstance(data.fuel_type, FuelType) else data.fuel_type,
            station_name=data.station_name,
            is_full_tank=data.is_full_tank,
            consumption=consumption,
            notes=data.notes,
            created_at=datetime.utcnow(),
        )

        db.add(log)

        # SECURITY FIX 24-4: Row Lock fuer atomare Mileage-Aktualisierung (TOCTOU Prevention)
        # Aktualisiere Kilometerstand des Fahrzeugs mit SELECT FOR UPDATE
        vehicle_result = await db.execute(
            select(PrivatVehicle)
            .where(PrivatVehicle.id == data.vehicle_id)
            .with_for_update()  # SECURITY: Exclusive Row Lock - CWE-367 Prevention
        )
        vehicle = vehicle_result.scalar_one_or_none()
        if vehicle and data.mileage > (vehicle.mileage or 0):
            vehicle.mileage = data.mileage
            vehicle.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(log)

        logger.info(
            "privat_fuel_log_created",
            log_id=str(log.id),
            vehicle_id=str(data.vehicle_id),
        )

        return log

    async def _calculate_consumption_for_log(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        current_mileage: int,
        liters: Decimal,
        is_full_tank: bool,
    ) -> Optional[Decimal]:
        """Berechnet den Verbrauch fuer einen einzelnen Tankbeleg."""
        if not is_full_tank:
            return None

        # Hole vorherigen Volltank-Eintrag
        result = await db.execute(
            select(PrivatFuelLog)
            .where(
                PrivatFuelLog.vehicle_id == vehicle_id,
                PrivatFuelLog.is_full_tank == True,
                PrivatFuelLog.mileage < current_mileage,
            )
            .order_by(PrivatFuelLog.mileage.desc())
            .limit(1)
        )
        prev_log = result.scalar_one_or_none()

        if not prev_log:
            return None

        km_diff = current_mileage - prev_log.mileage
        if km_diff <= 0:
            return None

        return (liters * 100) / km_diff

    def _to_fuel_log_response(self, log: PrivatFuelLog) -> PrivatFuelLogResponse:
        """Konvertiert FuelLog zu Response."""
        return PrivatFuelLogResponse(
            id=log.id,
            vehicle_id=log.vehicle_id,
            date=log.date,
            mileage=log.mileage,
            liters=log.liters,
            price_per_liter=log.price_per_liter,
            total_price=log.total_price,
            fuel_type=FuelType(log.fuel_type),
            station_name=log.station_name,
            is_full_tank=log.is_full_tank,
            consumption=log.consumption,
            notes=log.notes,
            created_at=log.created_at,
        )

    async def list_fuel_logs(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        year: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[PrivatFuelLogResponse]:
        """Listet Tankbelege eines Fahrzeugs."""
        conditions = [PrivatFuelLog.vehicle_id == vehicle_id]
        if year:
            conditions.append(func.extract("year", PrivatFuelLog.date) == year)

        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatFuelLog)
            .where(and_(*conditions))
            .order_by(PrivatFuelLog.date.desc())
            .offset(offset)
            .limit(page_size)
        )

        logs = result.scalars().all()
        return [self._to_fuel_log_response(log) for log in logs]

    async def get_fuel_statistics(
        self,
        db: AsyncSession,
        vehicle_id: uuid.UUID,
        year: Optional[int] = None,
    ) -> dict:
        """Berechnet Kraftstoff-Statistiken."""
        conditions = [PrivatFuelLog.vehicle_id == vehicle_id]
        if year:
            conditions.append(func.extract("year", PrivatFuelLog.date) == year)

        result = await db.execute(
            select(
                func.count(PrivatFuelLog.id).label("count"),
                func.coalesce(func.sum(PrivatFuelLog.liters), 0).label("total_liters"),
                func.coalesce(func.sum(PrivatFuelLog.total_price), 0).label("total_cost"),
                func.coalesce(func.avg(PrivatFuelLog.price_per_liter), 0).label("avg_price"),
                func.coalesce(func.max(PrivatFuelLog.mileage), 0).label("max_mileage"),
                func.coalesce(func.min(PrivatFuelLog.mileage), 0).label("min_mileage"),
            )
            .where(and_(*conditions))
        )

        row = result.one()

        total_km = row.max_mileage - row.min_mileage if row.min_mileage > 0 else 0
        avg_consumption = (
            (Decimal(str(row.total_liters)) * 100) / total_km
            if total_km > 0
            else None
        )

        return {
            "fill_ups": row.count,
            "total_liters": Decimal(str(row.total_liters)),
            "total_cost": Decimal(str(row.total_cost)),
            "avg_price_per_liter": Decimal(str(row.avg_price)),
            "total_kilometers": total_km,
            "avg_consumption_per_100km": avg_consumption,
        }
