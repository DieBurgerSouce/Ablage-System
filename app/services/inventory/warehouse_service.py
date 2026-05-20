"""
Warehouse Service - Lagerverwaltung

CRUD-Operationen für Lager (Warehouses).
"""

import uuid
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_inventory import Warehouse


class WarehouseService:
    """Service für Lagerverwaltung"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        company_id: uuid.UUID,
        code: str,
        name: str,
        description: Optional[str] = None,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        country: str = "DE",
        is_default: bool = False,
    ) -> Warehouse:
        """
        Erstellt ein neues Lager.

        Args:
            company_id: Unternehmen
            code: Kurzcode (z.B. "HAUPT", "LAGER1")
            name: Anzeigename
            description: Optionale Beschreibung
            address_line1: Adresszeile 1
            address_line2: Adresszeile 2
            postal_code: PLZ
            city: Ort
            country: Land (ISO 2-Letter)
            is_default: Als Standardlager setzen

        Returns:
            Erstelltes Warehouse
        """
        # Wenn als Default gesetzt, andere Default-Flags entfernen
        if is_default:
            await self._clear_default_flag(company_id)

        warehouse = Warehouse(
            company_id=company_id,
            code=code.upper(),
            name=name,
            description=description,
            address_line1=address_line1,
            address_line2=address_line2,
            postal_code=postal_code,
            city=city,
            country=country,
            is_default=is_default,
            is_active=True,
        )
        self.session.add(warehouse)
        await self.session.flush()
        return warehouse

    async def get_by_id(
        self,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[Warehouse]:
        """Lager nach ID abrufen"""
        query = select(Warehouse).where(
            and_(
                Warehouse.id == warehouse_id,
                Warehouse.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
        company_id: uuid.UUID,
    ) -> Optional[Warehouse]:
        """Lager nach Code abrufen"""
        query = select(Warehouse).where(
            and_(
                Warehouse.code == code.upper(),
                Warehouse.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        company_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> list[Warehouse]:
        """Alle Lager eines Unternehmens auflisten"""
        conditions = [Warehouse.company_id == company_id]
        if not include_inactive:
            conditions.append(Warehouse.is_active == True)  # noqa: E712

        query = select(Warehouse).where(and_(*conditions)).order_by(Warehouse.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_default(self, company_id: uuid.UUID) -> Optional[Warehouse]:
        """Standardlager abrufen"""
        query = select(Warehouse).where(
            and_(
                Warehouse.company_id == company_id,
                Warehouse.is_default == True,  # noqa: E712
                Warehouse.is_active == True,  # noqa: E712
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update(
        self,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        **kwargs,
    ) -> Optional[Warehouse]:
        """Lager aktualisieren"""
        warehouse = await self.get_by_id(warehouse_id, company_id)
        if not warehouse:
            return None

        # Wenn als Default gesetzt, andere Default-Flags entfernen
        if kwargs.get("is_default", False):
            await self._clear_default_flag(company_id, exclude_id=warehouse_id)

        # Code immer uppercase
        if "code" in kwargs:
            kwargs["code"] = kwargs["code"].upper()

        for key, value in kwargs.items():
            if hasattr(warehouse, key):
                setattr(warehouse, key, value)

        await self.session.flush()
        return warehouse

    async def deactivate(
        self,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Lager deaktivieren (nicht löschen)"""
        warehouse = await self.get_by_id(warehouse_id, company_id)
        if not warehouse:
            return False

        warehouse.is_active = False
        warehouse.is_default = False
        await self.session.flush()
        return True

    async def _clear_default_flag(
        self,
        company_id: uuid.UUID,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Default-Flag bei allen anderen Lagern entfernen"""
        conditions = [
            Warehouse.company_id == company_id,
            Warehouse.is_default == True,  # noqa: E712
        ]
        if exclude_id:
            conditions.append(Warehouse.id != exclude_id)

        query = select(Warehouse).where(and_(*conditions))
        result = await self.session.execute(query)
        for warehouse in result.scalars():
            warehouse.is_default = False
