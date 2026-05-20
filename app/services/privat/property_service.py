"""Service für die Verwaltung von Immobilien im Privat-Modul."""

import uuid
from datetime import datetime, date
from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    PrivatProperty,
    PrivatTenant,
    PrivatRentalIncome,
    PrivatUtilityStatement,
)
from app.db.schemas import (
    PrivatPropertyCreate,
    PrivatPropertyUpdate,
    PrivatPropertyResponse,
    PrivatPropertyWithTenants,
    PrivatPropertyListResponse,
    PrivatTenantCreate,
    PrivatTenantUpdate,
    PrivatTenantResponse,
    PrivatRentalIncomeCreate,
    PrivatRentalIncomeResponse,
    PrivatUtilityStatementCreate,
    PrivatUtilityStatementResponse,
)

logger = structlog.get_logger(__name__)


class PrivatPropertyService:
    """Service für Immobilien, Mieter und zugehoerige Daten."""

    # ========== Property CRUD ==========

    async def create_property(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatPropertyCreate,
    ) -> PrivatProperty:
        """Erstellt eine neue Immobilie.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Immobilien-Daten

        Returns:
            Erstellte Immobilie
        """
        property_obj = PrivatProperty(
            id=uuid.uuid4(),
            space_id=space_id,
            name=data.name,
            address=data.address,
            city=data.city,
            postal_code=data.postal_code,
            country=data.country,
            property_type=data.property_type,
            size_sqm=data.size_sqm,
            rooms=data.rooms,
            purchase_date=data.purchase_date,
            purchase_price=data.purchase_price,
            current_value=data.current_value,
            notes=data.notes,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(property_obj)
        await db.commit()
        await db.refresh(property_obj)

        logger.info(
            "privat_property_created",
            property_id=str(property_obj.id),
            space_id=str(space_id),
        )

        return property_obj

    async def get_property(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> Optional[PrivatProperty]:
        """Holt eine Immobilie nach ID."""
        result = await db.execute(
            select(PrivatProperty).where(PrivatProperty.id == property_id)
        )
        return result.scalar_one_or_none()

    async def get_property_with_access_check(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatProperty]:
        """IDOR-sichere Methode: Holt Immobilie nur wenn User Zugriff hat.

        SECURITY: Gibt einheitlich None zurück bei:
        - Immobilie existiert nicht
        - User hat keinen Zugriff

        Dies verhindert Information Disclosure über Existenz von Immobilien.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Immobilie wenn vorhanden und Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # Join mit Space um Owner zu prüfen
        result = await db.execute(
            select(PrivatProperty, PrivatSpace)
            .join(PrivatSpace, PrivatProperty.space_id == PrivatSpace.id)
            .where(PrivatProperty.id == property_id)
        )
        row = result.first()

        if not row:
            return None

        property_obj, space = row

        # Owner hat immer Zugriff
        if space.owner_id == requesting_user_id:
            return property_obj

        # Prüfe explizite Berechtigung
        now = utc_now()
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
                "idor_property_attempt_blocked",
                property_id=str(property_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return property_obj

    async def list_properties(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> PrivatPropertyListResponse:
        """Listet alle Immobilien eines Spaces."""
        # Count
        count_result = await db.execute(
            select(func.count(PrivatProperty.id))
            .where(PrivatProperty.space_id == space_id)
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatProperty)
            .where(PrivatProperty.space_id == space_id)
            .order_by(PrivatProperty.name)
            .offset(offset)
            .limit(page_size)
        )
        properties = result.scalars().all()

        # Mit Mieter-Daten anreichern
        items = []
        for prop in properties:
            tenants = await self.list_tenants(db, prop.id)
            rental_income = await self._get_total_rental_income(db, prop.id)
            pending = await self._get_pending_payments(db, prop.id)

            items.append(PrivatPropertyWithTenants(
                id=prop.id,
                space_id=prop.space_id,
                name=prop.name,
                address=prop.address,
                city=prop.city,
                postal_code=prop.postal_code,
                country=prop.country,
                property_type=prop.property_type,
                size_sqm=prop.size_sqm,
                rooms=prop.rooms,
                purchase_date=prop.purchase_date,
                purchase_price=prop.purchase_price,
                current_value=prop.current_value,
                notes=prop.notes,
                created_at=prop.created_at,
                updated_at=prop.updated_at,
                tenants=tenants,
                total_rental_income=rental_income,
                pending_payments=pending,
            ))

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatPropertyListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def _get_total_rental_income(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> Decimal:
        """Berechnet die Gesamtmieteinnahmen des aktuellen Jahres."""
        current_year = date.today().year
        result = await db.execute(
            select(func.coalesce(func.sum(PrivatRentalIncome.amount), 0))
            .join(PrivatTenant)
            .where(
                PrivatTenant.property_id == property_id,
                func.extract("year", PrivatRentalIncome.payment_date) == current_year,
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def _get_pending_payments(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> int:
        """Zaehlt ausstehende Zahlungen."""
        # Vereinfacht: Zaehle Utility Statements die nicht bezahlt sind
        result = await db.execute(
            select(func.count(PrivatUtilityStatement.id))
            .where(
                PrivatUtilityStatement.property_id == property_id,
                PrivatUtilityStatement.is_paid == False,
            )
        )
        return result.scalar() or 0

    async def get_pending_payments_count(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> int:
        """Öffentliche Methode: Zählt ausstehende Zahlungen für eine Immobilie.

        Args:
            db: Datenbank-Session
            property_id: Immobilien-ID

        Returns:
            Anzahl ausstehender Zahlungen (unbezahlte Nebenkostenabrechnungen)
        """
        return await self._get_pending_payments(db, property_id)

    async def update_property(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
        data: PrivatPropertyUpdate,
    ) -> Optional[PrivatProperty]:
        """Aktualisiert eine Immobilie.

        SECURITY FIX 22-14: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock könnte:
        - Lost Updates bei gleichzeitigen Änderungen auftreten
        - Inkonsistente Immobiliendaten entstehen
        """
        # SECURITY FIX 22-14: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatProperty)
            .where(PrivatProperty.id == property_id)
            .with_for_update()  # ROW LOCK - kritisch für Immobiliendaten!
        )
        property_obj = result.scalar_one_or_none()
        if not property_obj:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(property_obj, key, value)

        property_obj.updated_at = utc_now()

        await db.commit()
        await db.refresh(property_obj)

        return property_obj

    async def delete_property(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> bool:
        """Löscht eine Immobilie.

        SECURITY FIX 22-14b: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern.
        """
        # SECURITY FIX 22-14b: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatProperty)
            .where(PrivatProperty.id == property_id)
            .with_for_update()  # ROW LOCK - kritisch für Datenintegrität!
        )
        property_obj = result.scalar_one_or_none()
        if not property_obj:
            return False

        await db.delete(property_obj)
        await db.commit()
        return True

    # ========== Tenant CRUD ==========

    async def create_tenant(
        self,
        db: AsyncSession,
        data: PrivatTenantCreate,
    ) -> PrivatTenant:
        """Erstellt einen neuen Mieter."""
        tenant = PrivatTenant(
            id=uuid.uuid4(),
            property_id=data.property_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            unit_number=data.unit_number,
            lease_start=data.lease_start,
            lease_end=data.lease_end,
            monthly_rent=data.monthly_rent,
            deposit=data.deposit,
            notes=data.notes,
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        logger.info(
            "privat_tenant_created",
            tenant_id=str(tenant.id),
            property_id=str(data.property_id),
        )

        return tenant

    async def get_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Optional[PrivatTenant]:
        """Holt einen Mieter nach ID."""
        result = await db.execute(
            select(PrivatTenant).where(PrivatTenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_tenant_with_access_check(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatTenant]:
        """IDOR-sichere Methode: Holt Mieter nur wenn User Zugriff auf Property hat.

        SECURITY: Gibt einheitlich None zurück bei:
        - Mieter existiert nicht
        - User hat keinen Zugriff auf zugehoerige Immobilie

        Args:
            db: Datenbank-Session
            tenant_id: Mieter-ID
            requesting_user_id: ID des anfragenden Users

        Returns:
            Mieter wenn vorhanden und Zugriff erlaubt, sonst None
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # Join Tenant -> Property -> Space um Owner zu prüfen
        result = await db.execute(
            select(PrivatTenant, PrivatProperty, PrivatSpace)
            .join(PrivatProperty, PrivatTenant.property_id == PrivatProperty.id)
            .join(PrivatSpace, PrivatProperty.space_id == PrivatSpace.id)
            .where(PrivatTenant.id == tenant_id)
        )
        row = result.first()

        if not row:
            return None

        tenant, property_obj, space = row

        # Owner hat immer Zugriff
        if space.owner_id == requesting_user_id:
            return tenant

        # Prüfe explizite Berechtigung
        now = utc_now()
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
                "idor_tenant_attempt_blocked",
                tenant_id=str(tenant_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        return tenant

    async def list_tenants(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> List[PrivatTenantResponse]:
        """Listet alle Mieter einer Immobilie.

        SECURITY FIX 22-6: Pagination um DoS durch unbegrenzte Listen zu verhindern.
        """
        conditions = [PrivatTenant.property_id == property_id]
        if active_only:
            conditions.append(PrivatTenant.is_active == True)

        # SECURITY FIX 22-6: Pagination anwenden
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatTenant)
            .where(and_(*conditions))
            .order_by(PrivatTenant.last_name, PrivatTenant.first_name)
            .offset(offset)
            .limit(page_size)
        )

        tenants = result.scalars().all()
        return [
            PrivatTenantResponse(
                id=t.id,
                property_id=t.property_id,
                first_name=t.first_name,
                last_name=t.last_name,
                email=t.email,
                phone=t.phone,
                unit_number=t.unit_number,
                lease_start=t.lease_start,
                lease_end=t.lease_end,
                monthly_rent=t.monthly_rent,
                deposit=t.deposit,
                notes=t.notes,
                is_active=t.is_active,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tenants
        ]

    async def update_tenant(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        data: PrivatTenantUpdate,
    ) -> Optional[PrivatTenant]:
        """Aktualisiert einen Mieter.

        SECURITY FIX 23-10: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock könnte:
        - Lost Updates bei gleichzeitigen Änderungen auftreten
        - Inkonsistente Mieterdaten entstehen
        """
        # SECURITY FIX 23-10: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatTenant)
            .where(PrivatTenant.id == tenant_id)
            .with_for_update()  # ROW LOCK - kritisch für Mieterdaten!
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tenant, key, value)

        tenant.updated_at = utc_now()

        await db.commit()
        await db.refresh(tenant)

        return tenant

    # ========== Rental Income ==========

    async def record_rental_income_with_access_check(
        self,
        db: AsyncSession,
        data: PrivatRentalIncomeCreate,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatRentalIncome]:
        """SECURITY FIX 20-4: IDOR-sichere Mieteinnahmen-Erfassung.

        Validiert dass der anfragende User Zugriff auf den Tenant hat,
        bevor eine Mieteinnahme erstellt wird.

        Args:
            db: Datenbank-Session
            data: Mieteinnahmen-Daten
            requesting_user_id: ID des anfragenden Users

        Returns:
            Erstellte Mieteinnahme oder None wenn kein Zugriff
        """
        # SECURITY FIX 20-4: Prüfe Tenant-Ownership bevor Einnahme erstellt wird
        tenant = await self.get_tenant_with_access_check(
            db, data.tenant_id, requesting_user_id
        )
        if not tenant:
            logger.warning(
                "idor_rental_income_creation_blocked",
                tenant_id=str(data.tenant_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        income = PrivatRentalIncome(
            id=uuid.uuid4(),
            tenant_id=data.tenant_id,
            amount=data.amount,
            payment_date=data.payment_date,
            period_start=data.period_start,
            period_end=data.period_end,
            payment_method=data.payment_method,
            notes=data.notes,
            created_at=utc_now(),
        )

        db.add(income)
        await db.commit()
        await db.refresh(income)

        logger.info(
            "privat_rental_income_recorded",
            income_id=str(income.id),
            tenant_id=str(data.tenant_id),
            requesting_user_id=str(requesting_user_id),
        )

        return income

    async def record_rental_income(
        self,
        db: AsyncSession,
        data: PrivatRentalIncomeCreate,
    ) -> PrivatRentalIncome:
        """Erfasst eine Mieteinnahme.

        DEPRECATED: Nutze record_rental_income_with_access_check() für IDOR-sichere Operationen.
        """
        income = PrivatRentalIncome(
            id=uuid.uuid4(),
            tenant_id=data.tenant_id,
            amount=data.amount,
            payment_date=data.payment_date,
            period_start=data.period_start,
            period_end=data.period_end,
            payment_method=data.payment_method,
            notes=data.notes,
            created_at=utc_now(),
        )

        db.add(income)
        await db.commit()
        await db.refresh(income)

        return income

    async def list_rental_incomes(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        year: Optional[int] = None,
    ) -> List[PrivatRentalIncomeResponse]:
        """Listet Mieteinnahmen eines Mieters."""
        conditions = [PrivatRentalIncome.tenant_id == tenant_id]
        if year:
            conditions.append(
                func.extract("year", PrivatRentalIncome.payment_date) == year
            )

        result = await db.execute(
            select(PrivatRentalIncome)
            .where(and_(*conditions))
            .order_by(PrivatRentalIncome.payment_date.desc())
        )

        incomes = result.scalars().all()
        return [
            PrivatRentalIncomeResponse(
                id=i.id,
                tenant_id=i.tenant_id,
                amount=i.amount,
                payment_date=i.payment_date,
                period_start=i.period_start,
                period_end=i.period_end,
                payment_method=i.payment_method,
                notes=i.notes,
                created_at=i.created_at,
            )
            for i in incomes
        ]

    # ========== Utility Statements ==========

    async def create_utility_statement_with_access_check(
        self,
        db: AsyncSession,
        data: PrivatUtilityStatementCreate,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatUtilityStatement]:
        """SECURITY FIX 20-9: IDOR-sichere Nebenkostenabrechnung-Erstellung.

        Validiert dass der anfragende User Zugriff auf Property und Tenant hat,
        bevor eine Nebenkostenabrechnung erstellt wird.

        Args:
            db: Datenbank-Session
            data: Nebenkostenabrechnung-Daten
            requesting_user_id: ID des anfragenden Users

        Returns:
            Erstellte Nebenkostenabrechnung oder None wenn kein Zugriff
        """
        # SECURITY FIX 20-9: Prüfe Property-Ownership
        property_obj = await self.get_property_with_access_check(
            db, data.property_id, requesting_user_id
        )
        if not property_obj:
            logger.warning(
                "idor_utility_statement_property_blocked",
                property_id=str(data.property_id),
                requesting_user_id=str(requesting_user_id),
            )
            return None

        # SECURITY FIX 20-9: Prüfe Tenant-Ownership wenn angegeben
        if data.tenant_id:
            tenant = await self.get_tenant_with_access_check(
                db, data.tenant_id, requesting_user_id
            )
            if not tenant:
                logger.warning(
                    "idor_utility_statement_tenant_blocked",
                    tenant_id=str(data.tenant_id),
                    requesting_user_id=str(requesting_user_id),
                )
                return None

            # Zusätzlich prüfen: Tenant muss zur Property gehoeren
            if tenant.property_id != data.property_id:
                logger.warning(
                    "idor_utility_statement_tenant_mismatch",
                    tenant_id=str(data.tenant_id),
                    tenant_property_id=str(tenant.property_id),
                    data_property_id=str(data.property_id),
                    requesting_user_id=str(requesting_user_id),
                )
                return None

        statement = PrivatUtilityStatement(
            id=uuid.uuid4(),
            property_id=data.property_id,
            tenant_id=data.tenant_id,
            year=data.year,
            total_amount=data.total_amount,
            prepayments=data.prepayments,
            balance=data.balance,
            due_date=data.due_date,
            is_paid=data.is_paid,
            notes=data.notes,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(statement)
        await db.commit()
        await db.refresh(statement)

        logger.info(
            "privat_utility_statement_created",
            statement_id=str(statement.id),
            property_id=str(data.property_id),
            tenant_id=str(data.tenant_id) if data.tenant_id else None,
            requesting_user_id=str(requesting_user_id),
        )

        return statement

    async def create_utility_statement(
        self,
        db: AsyncSession,
        data: PrivatUtilityStatementCreate,
    ) -> PrivatUtilityStatement:
        """Erstellt eine Nebenkostenabrechnung.

        DEPRECATED: Nutze create_utility_statement_with_access_check() für IDOR-sichere Operationen.
        """
        statement = PrivatUtilityStatement(
            id=uuid.uuid4(),
            property_id=data.property_id,
            tenant_id=data.tenant_id,
            year=data.year,
            total_amount=data.total_amount,
            prepayments=data.prepayments,
            balance=data.balance,
            due_date=data.due_date,
            is_paid=data.is_paid,
            notes=data.notes,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(statement)
        await db.commit()
        await db.refresh(statement)

        return statement

    async def list_utility_statements(
        self,
        db: AsyncSession,
        property_id: uuid.UUID,
    ) -> List[PrivatUtilityStatementResponse]:
        """Listet Nebenkostenabrechnungen einer Immobilie."""
        result = await db.execute(
            select(PrivatUtilityStatement)
            .where(PrivatUtilityStatement.property_id == property_id)
            .order_by(PrivatUtilityStatement.year.desc())
        )

        statements = result.scalars().all()
        return [
            PrivatUtilityStatementResponse(
                id=s.id,
                property_id=s.property_id,
                tenant_id=s.tenant_id,
                year=s.year,
                total_amount=s.total_amount,
                prepayments=s.prepayments,
                balance=s.balance,
                due_date=s.due_date,
                is_paid=s.is_paid,
                notes=s.notes,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in statements
        ]
