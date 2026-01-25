"""
Inventory Item Service - Artikelverwaltung

CRUD-Operationen fuer Lagerartikel.
"""

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_inventory import InventoryItem, StockLevel


class InventoryItemService:
    """Service fuer Artikelverwaltung"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        company_id: uuid.UUID,
        item_number: str,
        name: str,
        unit: str = "Stueck",
        description: Optional[str] = None,
        category: Optional[str] = None,
        ean: Optional[str] = None,
        manufacturer_part_number: Optional[str] = None,
        purchase_price: Optional[Decimal] = None,
        sales_price: Optional[Decimal] = None,
        min_stock_level: Optional[Decimal] = None,
        reorder_point: Optional[Decimal] = None,
        reorder_quantity: Optional[Decimal] = None,
        default_supplier_id: Optional[uuid.UUID] = None,
        attributes: Optional[dict] = None,
    ) -> InventoryItem:
        """
        Erstellt einen neuen Artikel.

        Args:
            company_id: Unternehmen
            item_number: Artikelnummer (eindeutig pro Unternehmen)
            name: Artikelbezeichnung
            unit: Mengeneinheit (Stueck, kg, m, etc.)
            description: Langbeschreibung
            category: Kategorie/Warengruppe
            ean: EAN/GTIN
            manufacturer_part_number: Hersteller-Artikelnummer
            purchase_price: Einkaufspreis
            sales_price: Verkaufspreis
            min_stock_level: Mindestbestand
            reorder_point: Meldebestand
            reorder_quantity: Bestellmenge
            default_supplier_id: Standard-Lieferant
            attributes: Zusaetzliche Attribute (JSONB)

        Returns:
            Erstellter Artikel
        """
        item = InventoryItem(
            company_id=company_id,
            item_number=item_number,
            name=name,
            unit=unit,
            description=description,
            category=category,
            ean=ean,
            manufacturer_part_number=manufacturer_part_number,
            purchase_price=purchase_price,
            sales_price=sales_price,
            min_stock_level=min_stock_level,
            reorder_point=reorder_point,
            reorder_quantity=reorder_quantity,
            default_supplier_id=default_supplier_id,
            attributes=attributes or {},
            is_active=True,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_by_id(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[InventoryItem]:
        """Artikel nach ID abrufen"""
        query = select(InventoryItem).where(
            and_(
                InventoryItem.id == item_id,
                InventoryItem.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_item_number(
        self,
        item_number: str,
        company_id: uuid.UUID,
    ) -> Optional[InventoryItem]:
        """Artikel nach Artikelnummer abrufen"""
        query = select(InventoryItem).where(
            and_(
                InventoryItem.item_number == item_number,
                InventoryItem.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_ean(
        self,
        ean: str,
        company_id: uuid.UUID,
    ) -> Optional[InventoryItem]:
        """Artikel nach EAN abrufen"""
        query = select(InventoryItem).where(
            and_(
                InventoryItem.ean == ean,
                InventoryItem.company_id == company_id,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search(
        self,
        company_id: uuid.UUID,
        query_str: Optional[str] = None,
        category: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InventoryItem], int]:
        """
        Artikel suchen.

        Args:
            company_id: Unternehmen
            query_str: Suchbegriff (in Nummer, Name, EAN)
            category: Kategorie-Filter
            include_inactive: Inaktive Artikel einbeziehen
            limit: Max. Anzahl Ergebnisse
            offset: Offset fuer Pagination

        Returns:
            Tuple aus Artikelliste und Gesamtanzahl
        """
        conditions = [InventoryItem.company_id == company_id]

        if not include_inactive:
            conditions.append(InventoryItem.is_active == True)  # noqa: E712

        if query_str:
            search_term = f"%{query_str}%"
            conditions.append(
                or_(
                    InventoryItem.item_number.ilike(search_term),
                    InventoryItem.name.ilike(search_term),
                    InventoryItem.ean.ilike(search_term),
                    InventoryItem.manufacturer_part_number.ilike(search_term),
                )
            )

        if category:
            conditions.append(InventoryItem.category == category)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(InventoryItem).where(and_(*conditions))
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Daten
        query = (
            select(InventoryItem)
            .where(and_(*conditions))
            .order_by(InventoryItem.item_number)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_categories(self, company_id: uuid.UUID) -> list[str]:
        """Alle verwendeten Kategorien abrufen"""
        query = (
            select(InventoryItem.category)
            .where(
                and_(
                    InventoryItem.company_id == company_id,
                    InventoryItem.category.isnot(None),
                    InventoryItem.is_active == True,  # noqa: E712
                )
            )
            .distinct()
            .order_by(InventoryItem.category)
        )
        result = await self.session.execute(query)
        return [row[0] for row in result.all() if row[0]]

    async def get_low_stock_items(
        self,
        company_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
    ) -> list[dict]:
        """
        Artikel mit niedrigem Bestand abrufen.

        Gibt Artikel zurueck, deren Bestand unter dem Meldebestand liegt.
        """
        conditions = [
            InventoryItem.company_id == company_id,
            InventoryItem.is_active == True,  # noqa: E712
            InventoryItem.reorder_point.isnot(None),
        ]

        if warehouse_id:
            conditions.append(StockLevel.warehouse_id == warehouse_id)

        query = (
            select(
                InventoryItem,
                StockLevel.quantity_on_hand,
                StockLevel.warehouse_id,
            )
            .join(StockLevel, StockLevel.item_id == InventoryItem.id)
            .where(
                and_(
                    *conditions,
                    StockLevel.quantity_on_hand <= InventoryItem.reorder_point,
                )
            )
            .order_by(
                (StockLevel.quantity_on_hand - InventoryItem.reorder_point).asc()
            )
        )

        result = await self.session.execute(query)
        low_stock = []
        for item, quantity, wh_id in result.all():
            low_stock.append({
                "item": item,
                "quantity_on_hand": quantity,
                "reorder_point": item.reorder_point,
                "shortage": item.reorder_point - quantity,
                "warehouse_id": wh_id,
            })

        return low_stock

    async def update(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
        **kwargs,
    ) -> Optional[InventoryItem]:
        """Artikel aktualisieren"""
        item = await self.get_by_id(item_id, company_id)
        if not item:
            return None

        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)

        await self.session.flush()
        return item

    async def deactivate(
        self,
        item_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Artikel deaktivieren (nicht loeschen)"""
        item = await self.get_by_id(item_id, company_id)
        if not item:
            return False

        item.is_active = False
        await self.session.flush()
        return True

    async def match_from_text(
        self,
        text: str,
        company_id: uuid.UUID,
    ) -> list[tuple[InventoryItem, float]]:
        """
        Versucht, Artikel aus OCR-Text zu matchen.

        Args:
            text: Text aus Lieferschein (Artikelnummer, Beschreibung)
            company_id: Unternehmen

        Returns:
            Liste von (Artikel, Confidence) Tupeln
        """
        matches: list[tuple[InventoryItem, float]] = []

        # Exakter Match auf Artikelnummer
        item = await self.get_by_item_number(text.strip(), company_id)
        if item:
            matches.append((item, 1.0))
            return matches

        # EAN-Match
        if text.strip().isdigit() and len(text.strip()) in (8, 13):
            item = await self.get_by_ean(text.strip(), company_id)
            if item:
                matches.append((item, 0.95))
                return matches

        # Fuzzy-Suche
        items, _ = await self.search(
            company_id=company_id,
            query_str=text[:50],  # Nur erste 50 Zeichen
            limit=5,
        )

        for item in items:
            # Einfache Aehnlichkeitsberechnung
            confidence = 0.0

            # Artikelnummer teilweise enthalten
            if item.item_number.lower() in text.lower():
                confidence = 0.8
            # Name teilweise enthalten
            elif item.name.lower() in text.lower():
                confidence = 0.7
            # Irgendein Match
            else:
                confidence = 0.5

            matches.append((item, confidence))

        # Nach Confidence sortieren
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:3]  # Max 3 Vorschlaege
