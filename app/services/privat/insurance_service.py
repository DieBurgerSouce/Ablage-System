"""Service fuer die Verwaltung von Versicherungen im Privat-Modul."""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import PrivatInsurance
from app.db.schemas import (
    PrivatInsuranceCreate,
    PrivatInsuranceUpdate,
    PrivatInsuranceResponse,
    PrivatInsuranceWithDeadlines,
    PrivatInsuranceListResponse,
    InsuranceType,
)

logger = structlog.get_logger(__name__)


class PrivatInsuranceService:
    """Service fuer Versicherungsverwaltung."""

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatInsuranceCreate,
    ) -> PrivatInsurance:
        """Erstellt eine neue Versicherung.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Versicherungs-Daten

        Returns:
            Erstellte Versicherung
        """
        insurance = PrivatInsurance(
            id=uuid.uuid4(),
            space_id=space_id,
            name=data.name,
            insurance_type=data.insurance_type.value if isinstance(data.insurance_type, InsuranceType) else data.insurance_type,
            provider=data.provider,
            policy_number=data.policy_number,
            premium=data.premium,
            premium_interval=data.premium_interval,
            coverage_amount=data.coverage_amount,
            deductible=data.deductible,
            start_date=data.start_date,
            end_date=data.end_date,
            cancellation_period=data.cancellation_period,
            auto_renewal=data.auto_renewal,
            notes=data.notes,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(insurance)
        await db.commit()
        await db.refresh(insurance)

        logger.info(
            "privat_insurance_created",
            insurance_id=str(insurance.id),
            space_id=str(space_id),
            insurance_type=insurance.insurance_type,
        )

        return insurance

    async def get_by_id(
        self,
        db: AsyncSession,
        insurance_id: uuid.UUID,
    ) -> Optional[PrivatInsurance]:
        """Holt eine Versicherung nach ID.

        WARNUNG: Diese Methode fuehrt KEINEN Access-Check durch!
        Fuer API-Aufrufe IMMER get_by_id_with_access_check() verwenden!
        """
        result = await db.execute(
            select(PrivatInsurance).where(PrivatInsurance.id == insurance_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        insurance_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatInsurance]:
        """Holt eine Versicherung nach ID MIT Access-Check.

        SECURITY: Diese Methode ist IDOR-sicher:
        - Access-Check erfolgt VOR Rueckgabe der Versicherung
        - Gibt None zurueck wenn nicht existiert ODER kein Zugriff
        - Keine Information Disclosure ueber Existenz fremder Ressourcen

        Args:
            db: Datenbank-Session
            insurance_id: Versicherungs-ID
            requesting_user_id: User-ID fuer Zugriffskontrolle (REQUIRED)

        Returns:
            Versicherung wenn existiert UND Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # SECURITY: Hole Versicherung MIT Space in EINER Query
        result = await db.execute(
            select(PrivatInsurance, PrivatSpace)
            .join(PrivatSpace, PrivatInsurance.space_id == PrivatSpace.id)
            .where(PrivatInsurance.id == insurance_id)
        )
        row = result.first()

        if not row:
            return None  # Einheitliche Antwort: nicht gefunden

        insurance, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == requesting_user_id:
            return insurance

        # Pruefe explizite Berechtigung - SECURITY: mit expires_at Validierung!
        from datetime import timezone
        now = datetime.now(timezone.utc)
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                # SECURITY: expires_at check - abgelaufene Zugriffe ignorieren
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            logger.warning(
                "idor_insurance_attempt_blocked",
                insurance_id=str(insurance_id),
                user_id=str(requesting_user_id),
                space_id=str(space.id)
            )
            return None  # SECURITY: Einheitliche Antwort

        return insurance

    async def list_insurances(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        insurance_type: Optional[InsuranceType] = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatInsuranceListResponse:
        """Listet alle Versicherungen eines Spaces."""
        conditions = [PrivatInsurance.space_id == space_id]

        if active_only:
            conditions.append(PrivatInsurance.is_active == True)

        if insurance_type:
            conditions.append(
                PrivatInsurance.insurance_type == insurance_type.value
            )

        # Count
        count_result = await db.execute(
            select(func.count(PrivatInsurance.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatInsurance)
            .where(and_(*conditions))
            .order_by(PrivatInsurance.name)
            .offset(offset)
            .limit(page_size)
        )
        insurances = result.scalars().all()

        # Mit Frist-Informationen anreichern
        items = []
        for ins in insurances:
            upcoming_payment = self._calculate_next_payment(ins)
            days_until = None
            if upcoming_payment:
                days_until = (upcoming_payment - date.today()).days

            annual_cost = self._calculate_annual_cost(ins)

            items.append(PrivatInsuranceWithDeadlines(
                id=ins.id,
                space_id=ins.space_id,
                name=ins.name,
                insurance_type=InsuranceType(ins.insurance_type),
                provider=ins.provider,
                policy_number=ins.policy_number,
                premium=ins.premium,
                premium_interval=ins.premium_interval,
                coverage_amount=ins.coverage_amount,
                deductible=ins.deductible,
                start_date=ins.start_date,
                end_date=ins.end_date,
                cancellation_period=ins.cancellation_period,
                auto_renewal=ins.auto_renewal,
                notes=ins.notes,
                is_active=ins.is_active,
                created_at=ins.created_at,
                updated_at=ins.updated_at,
                upcoming_payment=upcoming_payment,
                days_until_payment=days_until,
                annual_cost=annual_cost,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatInsuranceListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def _calculate_next_payment(
        self,
        insurance: PrivatInsurance,
    ) -> Optional[date]:
        """Berechnet das naechste Zahlungsdatum."""
        if not insurance.start_date:
            return None

        today = date.today()
        start = insurance.start_date

        # Intervall in Monaten
        interval_months = {
            "monthly": 1,
            "quarterly": 3,
            "semi_annual": 6,
            "annual": 12,
        }.get(insurance.premium_interval, 12)

        # Berechne naechstes Zahlungsdatum
        current = start
        while current <= today:
            # Naechstes Datum
            month = current.month + interval_months
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1

            # Handle Tage die im neuen Monat nicht existieren
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day = min(current.day, max_day)

            current = date(year, month, day)

        return current

    def _calculate_annual_cost(
        self,
        insurance: PrivatInsurance,
    ) -> Decimal:
        """Berechnet die jaehrlichen Kosten."""
        if not insurance.premium:
            return Decimal("0.00")

        multiplier = {
            "monthly": 12,
            "quarterly": 4,
            "semi_annual": 2,
            "annual": 1,
        }.get(insurance.premium_interval, 1)

        return insurance.premium * multiplier

    async def update(
        self,
        db: AsyncSession,
        insurance_id: uuid.UUID,
        data: PrivatInsuranceUpdate,
    ) -> Optional[PrivatInsurance]:
        """Aktualisiert eine Versicherung.

        SECURITY FIX 21-5: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Versicherungsdaten entstehen
        """
        # SECURITY FIX 21-5: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatInsurance)
            .where(PrivatInsurance.id == insurance_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Versicherungsdaten!
        )
        insurance = result.scalar_one_or_none()
        if not insurance:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "insurance_type" and value:
                value = value.value if isinstance(value, InsuranceType) else value
            setattr(insurance, key, value)

        insurance.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(insurance)

        logger.info(
            "privat_insurance_updated",
            insurance_id=str(insurance_id),
        )

        return insurance

    async def delete(
        self,
        db: AsyncSession,
        insurance_id: uuid.UUID,
        soft_delete: bool = True,
    ) -> bool:
        """Loescht eine Versicherung.

        SECURITY FIX 22-13: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen
        """
        # SECURITY FIX 22-13: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatInsurance)
            .where(PrivatInsurance.id == insurance_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        insurance = result.scalar_one_or_none()
        if not insurance:
            return False

        if soft_delete:
            insurance.is_active = False
            insurance.updated_at = datetime.utcnow()
            await db.commit()
        else:
            await db.delete(insurance)
            await db.commit()

        logger.info(
            "privat_insurance_deleted",
            insurance_id=str(insurance_id),
            soft_delete=soft_delete,
        )

        return True

    async def get_expiring_insurances(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        days_ahead: int = 30,
    ) -> List[PrivatInsuranceWithDeadlines]:
        """Holt Versicherungen die bald ablaufen oder erneuert werden muessen."""
        target_date = date.today()
        from datetime import timedelta
        end_date = target_date + timedelta(days=days_ahead)

        result = await db.execute(
            select(PrivatInsurance)
            .where(
                PrivatInsurance.space_id == space_id,
                PrivatInsurance.is_active == True,
                PrivatInsurance.end_date.isnot(None),
                PrivatInsurance.end_date <= end_date,
                PrivatInsurance.end_date >= target_date,
            )
            .order_by(PrivatInsurance.end_date)
        )

        insurances = result.scalars().all()
        return [
            PrivatInsuranceWithDeadlines(
                id=ins.id,
                space_id=ins.space_id,
                name=ins.name,
                insurance_type=InsuranceType(ins.insurance_type),
                provider=ins.provider,
                policy_number=ins.policy_number,
                premium=ins.premium,
                premium_interval=ins.premium_interval,
                coverage_amount=ins.coverage_amount,
                deductible=ins.deductible,
                start_date=ins.start_date,
                end_date=ins.end_date,
                cancellation_period=ins.cancellation_period,
                auto_renewal=ins.auto_renewal,
                notes=ins.notes,
                is_active=ins.is_active,
                created_at=ins.created_at,
                updated_at=ins.updated_at,
                upcoming_payment=self._calculate_next_payment(ins),
                days_until_payment=(ins.end_date - target_date).days if ins.end_date else None,
                annual_cost=self._calculate_annual_cost(ins),
            )
            for ins in insurances
        ]

    async def get_total_annual_cost(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet die gesamten jaehrlichen Versicherungskosten."""
        result = await db.execute(
            select(PrivatInsurance)
            .where(
                PrivatInsurance.space_id == space_id,
                PrivatInsurance.is_active == True,
            )
        )

        insurances = result.scalars().all()
        total = Decimal("0.00")
        for ins in insurances:
            total += self._calculate_annual_cost(ins)

        return total
