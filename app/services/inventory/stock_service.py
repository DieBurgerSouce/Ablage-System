"""
Stock Service - Bestandsfuehrung

Verwaltung von Lagerbestaenden und Warenbewegungen.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_inventory import (
    StockLevel,
    InventoryMovement,
    MovementType,
    MovementStatus,
    Warehouse,
    InventoryItem,
)


class StockService:
    """Service fuer Bestandsfuehrung"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_stock_level(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[StockLevel]:
        """Bestandslevel fuer Artikel im Lager abrufen"""
        query = select(StockLevel).where(
            and_(
                StockLevel.item_id == item_id,
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_stock_level(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> StockLevel:
        """Bestandslevel abrufen oder erstellen"""
        stock = await self.get_stock_level(item_id, warehouse_id, company_id)
        if not stock:
            stock = StockLevel(
                company_id=company_id,
                item_id=item_id,
                warehouse_id=warehouse_id,
                quantity_on_hand=Decimal("0"),
                quantity_reserved=Decimal("0"),
                quantity_on_order=Decimal("0"),
            )
            self.session.add(stock)
            await self.session.flush()
        return stock

    async def get_total_stock(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Decimal:
        """Gesamtbestand eines Artikels ueber alle Lager"""
        query = select(func.sum(StockLevel.quantity_on_hand)).where(
            and_(
                StockLevel.item_id == item_id,
                StockLevel.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        total = result.scalar_one_or_none()
        return total or Decimal("0")

    async def get_item_stock_by_warehouse(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> list[dict]:
        """Bestand eines Artikels nach Lagern aufgeschluesselt"""
        query = (
            select(StockLevel, Warehouse.name, Warehouse.code)
            .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .where(
                and_(
                    StockLevel.item_id == item_id,
                    StockLevel.company_id == company_id,
                )
            )
            .order_by(Warehouse.name)
        )
        result = await self.session.execute(query)

        stocks = []
        for stock, wh_name, wh_code in result.all():
            stocks.append({
                "warehouse_id": stock.warehouse_id,
                "warehouse_name": wh_name,
                "warehouse_code": wh_code,
                "quantity_on_hand": stock.quantity_on_hand,
                "quantity_reserved": stock.quantity_reserved,
                "quantity_available": stock.quantity_available,
                "quantity_on_order": stock.quantity_on_order,
            })
        return stocks

    async def get_warehouse_inventory(
        self,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        include_zero_stock: bool = False,
    ) -> list[dict]:
        """Alle Bestaende in einem Lager"""
        conditions = [
            StockLevel.warehouse_id == warehouse_id,
            StockLevel.company_id == company_id,
        ]
        if not include_zero_stock:
            conditions.append(StockLevel.quantity_on_hand > 0)

        query = (
            select(StockLevel, InventoryItem.item_number, InventoryItem.name)
            .join(InventoryItem, InventoryItem.id == StockLevel.item_id)
            .where(and_(*conditions))
            .order_by(InventoryItem.item_number)
        )
        result = await self.session.execute(query)

        inventory = []
        for stock, item_number, item_name in result.all():
            inventory.append({
                "item_id": stock.item_id,
                "item_number": item_number,
                "item_name": item_name,
                "quantity_on_hand": stock.quantity_on_hand,
                "quantity_reserved": stock.quantity_reserved,
                "quantity_available": stock.quantity_available,
            })
        return inventory

    async def book_movement(
        self,
        company_id: uuid.UUID,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        movement_type: MovementType,
        quantity: Decimal,
        document_id: Optional[uuid.UUID] = None,
        reference_number: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        unit_price: Optional[Decimal] = None,
        notes: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
        target_warehouse_id: Optional[uuid.UUID] = None,
    ) -> InventoryMovement:
        """
        Bucht eine Warenbewegung und aktualisiert den Bestand.

        Args:
            company_id: Unternehmen
            item_id: Artikel
            warehouse_id: Quelllager
            movement_type: Art der Bewegung
            quantity: Menge (immer positiv)
            document_id: Verknuepftes Dokument
            reference_number: Referenznummer (Lieferschein, etc.)
            entity_id: Geschaeftspartner
            unit_price: Stueckpreis
            notes: Bemerkungen
            created_by: Erstellt durch User
            target_warehouse_id: Ziellager (bei Umlagerung)

        Returns:
            Erstellte Bewegung
        """
        # Bestand holen/erstellen
        stock = await self.get_or_create_stock_level(item_id, warehouse_id, company_id)

        # Bewegung erstellen
        total_value = None
        if unit_price:
            total_value = unit_price * quantity

        movement = InventoryMovement(
            company_id=company_id,
            item_id=item_id,
            warehouse_id=warehouse_id,
            target_warehouse_id=target_warehouse_id,
            movement_type=movement_type,
            status=MovementStatus.CONFIRMED,
            quantity=quantity,
            unit_price=unit_price,
            total_value=total_value,
            document_id=document_id,
            reference_number=reference_number,
            entity_id=entity_id,
            notes=notes,
            created_by=created_by,
            movement_date=datetime.utcnow(),
        )
        self.session.add(movement)

        # Bestand aktualisieren
        if movement_type in (
            MovementType.GOODS_RECEIPT,
            MovementType.RETURN_INBOUND,
            MovementType.ADJUSTMENT_PLUS,
        ):
            stock.quantity_on_hand += quantity

        elif movement_type in (
            MovementType.GOODS_ISSUE,
            MovementType.RETURN_OUTBOUND,
            MovementType.ADJUSTMENT_MINUS,
            MovementType.SCRAPPING,
        ):
            stock.quantity_on_hand -= quantity

        elif movement_type == MovementType.TRANSFER:
            # Vom Quelllager abziehen
            stock.quantity_on_hand -= quantity

            # Ins Ziellager buchen
            if target_warehouse_id:
                target_stock = await self.get_or_create_stock_level(
                    item_id, target_warehouse_id, company_id
                )
                target_stock.quantity_on_hand += quantity

        await self.session.flush()
        return movement

    async def reserve_stock(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        quantity: Decimal,
    ) -> bool:
        """
        Reserviert Bestand fuer einen Auftrag.

        Returns:
            True wenn genug verfuegbar und reserviert, False sonst
        """
        stock = await self.get_stock_level(item_id, warehouse_id, company_id)
        if not stock:
            return False

        if stock.quantity_available < quantity:
            return False

        stock.quantity_reserved += quantity
        await self.session.flush()
        return True

    async def release_reservation(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        quantity: Decimal,
    ) -> bool:
        """Gibt reservierten Bestand wieder frei"""
        stock = await self.get_stock_level(item_id, warehouse_id, company_id)
        if not stock:
            return False

        stock.quantity_reserved = max(Decimal("0"), stock.quantity_reserved - quantity)
        await self.session.flush()
        return True

    async def adjust_on_order(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        quantity: Decimal,
        increase: bool = True,
    ) -> StockLevel:
        """Bestellbestand anpassen"""
        stock = await self.get_or_create_stock_level(item_id, warehouse_id, company_id)

        if increase:
            stock.quantity_on_order += quantity
        else:
            stock.quantity_on_order = max(Decimal("0"), stock.quantity_on_order - quantity)

        await self.session.flush()
        return stock

    async def record_inventory_count(
        self,
        item_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        company_id: uuid.UUID,
        counted_quantity: Decimal,
        created_by: Optional[uuid.UUID] = None,
    ) -> tuple[StockLevel, Optional[InventoryMovement]]:
        """
        Inventurzaehlung erfassen und ggf. Korrektur buchen.

        Returns:
            Tuple aus (StockLevel, Korrektur-Bewegung oder None)
        """
        stock = await self.get_or_create_stock_level(item_id, warehouse_id, company_id)

        # Differenz berechnen
        difference = counted_quantity - stock.quantity_on_hand
        movement = None

        if difference != 0:
            # Korrektur buchen
            if difference > 0:
                movement_type = MovementType.ADJUSTMENT_PLUS
            else:
                movement_type = MovementType.ADJUSTMENT_MINUS

            movement = await self.book_movement(
                company_id=company_id,
                item_id=item_id,
                warehouse_id=warehouse_id,
                movement_type=movement_type,
                quantity=abs(difference),
                notes=f"Inventurkorrektur: Gezaehlt {counted_quantity}, System {stock.quantity_on_hand}",
                created_by=created_by,
            )

        # Inventurzaehlung dokumentieren
        stock.last_count_date = datetime.utcnow()
        stock.last_count_quantity = counted_quantity

        await self.session.flush()
        return stock, movement

    async def get_movement_history(
        self,
        company_id: uuid.UUID,
        item_id: Optional[uuid.UUID] = None,
        warehouse_id: Optional[uuid.UUID] = None,
        movement_type: Optional[MovementType] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[InventoryMovement], int]:
        """Bewegungshistorie abrufen"""
        conditions = [InventoryMovement.company_id == company_id]

        if item_id:
            conditions.append(InventoryMovement.item_id == item_id)
        if warehouse_id:
            conditions.append(InventoryMovement.warehouse_id == warehouse_id)
        if movement_type:
            conditions.append(InventoryMovement.movement_type == movement_type)
        if from_date:
            conditions.append(InventoryMovement.movement_date >= from_date)
        if to_date:
            conditions.append(InventoryMovement.movement_date <= to_date)

        # Gesamtanzahl
        count_query = (
            select(func.count())
            .select_from(InventoryMovement)
            .where(and_(*conditions))
        )
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Daten
        query = (
            select(InventoryMovement)
            .where(and_(*conditions))
            .order_by(InventoryMovement.movement_date.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        movements = list(result.scalars().all())

        return movements, total

    async def get_stock_value(
        self,
        company_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """
        Berechnet den Gesamtwert des Lagerbestands.

        Returns:
            Dict mit total_value, total_items, by_category
        """
        conditions = [
            StockLevel.company_id == company_id,
            StockLevel.quantity_on_hand > 0,
        ]
        if warehouse_id:
            conditions.append(StockLevel.warehouse_id == warehouse_id)

        query = (
            select(
                StockLevel.quantity_on_hand,
                InventoryItem.purchase_price,
                InventoryItem.category,
            )
            .join(InventoryItem, InventoryItem.id == StockLevel.item_id)
            .where(and_(*conditions))
        )
        result = await self.session.execute(query)

        total_value = Decimal("0")
        total_items = 0
        by_category: dict[str, Decimal] = {}

        for quantity, price, category in result.all():
            total_items += 1
            if price:
                value = quantity * price
                total_value += value

                cat_key = category or "Ohne Kategorie"
                by_category[cat_key] = by_category.get(cat_key, Decimal("0")) + value

        return {
            "total_value": total_value,
            "total_items": total_items,
            "by_category": by_category,
        }
