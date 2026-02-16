"""
Inventory API - Lagerverwaltung und Wareneingang

Endpoints für:
- Lager (Warehouses)
- Artikel (Inventory Items)
- Bestände (Stock Levels)
- Warenbewegungen (Movements)
- Wareneingang (Goods Receipts)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_current_company_id, get_db
from app.core.safe_errors import safe_error_detail
from app.db.models import User
from app.db.models_inventory import MovementType
from app.services.inventory import (
    WarehouseService,
    InventoryItemService,
    StockService,
    GoodsReceiptService,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ============================================================================
# Schemas
# ============================================================================

# Warehouse Schemas
class WarehouseCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "DE"
    is_default: bool = False


class WarehouseUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=20)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    is_default: Optional[bool] = None


class WarehouseResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str]
    address_line1: Optional[str]
    address_line2: Optional[str]
    postal_code: Optional[str]
    city: Optional[str]
    country: str
    is_active: bool
    is_default: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Item Schemas
class ItemCreate(BaseModel):
    item_number: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    unit: str = "Stück"
    description: Optional[str] = None
    category: Optional[str] = None
    ean: Optional[str] = Field(None, max_length=13)
    manufacturer_part_number: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    sales_price: Optional[Decimal] = None
    min_stock_level: Optional[Decimal] = None
    reorder_point: Optional[Decimal] = None
    reorder_quantity: Optional[Decimal] = None
    default_supplier_id: Optional[uuid.UUID] = None
    attributes: Optional[dict] = None


class ItemUpdate(BaseModel):
    item_number: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    unit: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    ean: Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    purchase_price: Optional[Decimal] = None
    sales_price: Optional[Decimal] = None
    min_stock_level: Optional[Decimal] = None
    reorder_point: Optional[Decimal] = None
    reorder_quantity: Optional[Decimal] = None
    default_supplier_id: Optional[uuid.UUID] = None
    attributes: Optional[dict] = None


class ItemResponse(BaseModel):
    id: uuid.UUID
    item_number: str
    name: str
    unit: str
    description: Optional[str]
    category: Optional[str]
    ean: Optional[str]
    manufacturer_part_number: Optional[str]
    purchase_price: Optional[Decimal]
    sales_price: Optional[Decimal]
    min_stock_level: Optional[Decimal]
    reorder_point: Optional[Decimal]
    reorder_quantity: Optional[Decimal]
    default_supplier_id: Optional[uuid.UUID]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int


# Stock Schemas
class StockLevelResponse(BaseModel):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    quantity_on_order: Decimal
    last_count_date: Optional[datetime]


class StockByWarehouseResponse(BaseModel):
    warehouse_id: uuid.UUID
    warehouse_name: str
    warehouse_code: str
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    quantity_on_order: Decimal


class MovementCreate(BaseModel):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: MovementType
    quantity: Decimal = Field(..., gt=0)
    target_warehouse_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None
    entity_id: Optional[uuid.UUID] = None
    unit_price: Optional[Decimal] = None
    notes: Optional[str] = None


class MovementResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    target_warehouse_id: Optional[uuid.UUID]
    movement_type: str
    status: str
    quantity: Decimal
    unit_price: Optional[Decimal]
    total_value: Optional[Decimal]
    document_id: Optional[uuid.UUID]
    reference_number: Optional[str]
    entity_id: Optional[uuid.UUID]
    notes: Optional[str]
    movement_date: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryCountRequest(BaseModel):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    counted_quantity: Decimal = Field(..., ge=0)


# Goods Receipt Schemas
class GoodsReceiptCreate(BaseModel):
    document_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_date: Optional[datetime] = None
    notes: Optional[str] = None


class GoodsReceiptLineResponse(BaseModel):
    id: uuid.UUID
    line_number: int
    item_id: Optional[uuid.UUID]
    item_number_extracted: Optional[str]
    description: Optional[str]
    quantity_expected: Optional[Decimal]
    quantity_received: Decimal
    unit: str
    is_matched: bool
    match_confidence: Optional[Decimal]

    class Config:
        from_attributes = True


class GoodsReceiptResponse(BaseModel):
    id: uuid.UUID
    delivery_note_id: uuid.UUID
    warehouse_id: uuid.UUID
    supplier_id: Optional[uuid.UUID]
    delivery_note_number: Optional[str]
    purchase_order_number: Optional[str]
    receipt_date: datetime
    is_processed: bool
    processed_at: Optional[datetime]
    notes: Optional[str]
    lines: list[GoodsReceiptLineResponse]
    created_at: datetime

    class Config:
        from_attributes = True


class LineMatchRequest(BaseModel):
    line_id: uuid.UUID
    item_id: uuid.UUID


class LineQuantityUpdate(BaseModel):
    line_id: uuid.UUID
    quantity_received: Decimal = Field(..., ge=0)


# ============================================================================
# Warehouse Endpoints
# ============================================================================

@router.post("/warehouses", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    data: WarehouseCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Erstellt ein neues Lager"""
    service = WarehouseService(session)

    # Prüfen ob Code bereits existiert
    existing = await service.get_by_code(data.code, company_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Lager mit Code '{data.code}' existiert bereits",
        )

    warehouse = await service.create(
        company_id=company_id,
        **data.model_dump(),
    )
    await session.commit()
    return warehouse


@router.get("/warehouses", response_model=list[WarehouseResponse])
async def list_warehouses(
    include_inactive: bool = False,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Listet alle Lager auf"""
    service = WarehouseService(session)
    return await service.list_all(company_id, include_inactive)


@router.get("/warehouses/default", response_model=Optional[WarehouseResponse])
async def get_default_warehouse(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt das Standardlager zurück"""
    service = WarehouseService(session)
    return await service.get_default(company_id)


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt ein einzelnes Lager zurück"""
    service = WarehouseService(session)
    warehouse = await service.get_by_id(warehouse_id, company_id)
    if not warehouse:
        raise HTTPException(status_code=404, detail="Lager nicht gefunden")
    return warehouse


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    data: WarehouseUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Aktualisiert ein Lager"""
    service = WarehouseService(session)
    warehouse = await service.update(
        warehouse_id,
        company_id,
        **data.model_dump(exclude_unset=True),
    )
    if not warehouse:
        raise HTTPException(status_code=404, detail="Lager nicht gefunden")
    await session.commit()
    return warehouse


@router.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_warehouse(
    warehouse_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Deaktiviert ein Lager"""
    service = WarehouseService(session)
    success = await service.deactivate(warehouse_id, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lager nicht gefunden")
    await session.commit()


# ============================================================================
# Item Endpoints
# ============================================================================

@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Erstellt einen neuen Artikel"""
    service = InventoryItemService(session)

    # Prüfen ob Artikelnummer bereits existiert
    existing = await service.get_by_item_number(data.item_number, company_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Artikel mit Nummer '{data.item_number}' existiert bereits",
        )

    item = await service.create(company_id=company_id, **data.model_dump())
    await session.commit()
    return item


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    q: Optional[str] = Query(None, description="Suchbegriff"),
    category: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Listet Artikel mit optionaler Suche"""
    service = InventoryItemService(session)
    items, total = await service.search(
        company_id=company_id,
        query_str=q,
        category=category,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return ItemListResponse(items=items, total=total)


@router.get("/items/categories", response_model=list[str])
async def list_categories(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Listet alle verwendeten Kategorien"""
    service = InventoryItemService(session)
    return await service.get_categories(company_id)


@router.get("/items/low-stock")
async def get_low_stock_items(
    warehouse_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt Artikel unter Meldebestand zurück"""
    service = InventoryItemService(session)
    return await service.get_low_stock_items(company_id, warehouse_id)


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt einen einzelnen Artikel zurück"""
    service = InventoryItemService(session)
    item = await service.get_by_id(item_id, company_id)
    if not item:
        raise HTTPException(status_code=404, detail="Artikel nicht gefunden")
    return item


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: ItemUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Aktualisiert einen Artikel"""
    service = InventoryItemService(session)
    item = await service.update(item_id, company_id, **data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Artikel nicht gefunden")
    await session.commit()
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Deaktiviert einen Artikel"""
    service = InventoryItemService(session)
    success = await service.deactivate(item_id, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Artikel nicht gefunden")
    await session.commit()


# ============================================================================
# Stock Endpoints
# ============================================================================

@router.get("/stock/{item_id}", response_model=list[StockByWarehouseResponse])
async def get_item_stock(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt Bestände eines Artikels nach Lagern zurück"""
    service = StockService(session)
    return await service.get_item_stock_by_warehouse(item_id, company_id)


@router.get("/stock/warehouse/{warehouse_id}")
async def get_warehouse_inventory(
    warehouse_id: uuid.UUID,
    include_zero: bool = False,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt alle Bestände in einem Lager zurück"""
    service = StockService(session)
    return await service.get_warehouse_inventory(warehouse_id, company_id, include_zero)


@router.get("/stock/value")
async def get_stock_value(
    warehouse_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Berechnet den Gesamtwert des Lagerbestands"""
    service = StockService(session)
    return await service.get_stock_value(company_id, warehouse_id)


@router.post("/movements", response_model=MovementResponse, status_code=status.HTTP_201_CREATED)
async def create_movement(
    data: MovementCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Erstellt eine Warenbewegung"""
    service = StockService(session)
    movement = await service.book_movement(
        company_id=company_id,
        item_id=data.item_id,
        warehouse_id=data.warehouse_id,
        movement_type=data.movement_type,
        quantity=data.quantity,
        target_warehouse_id=data.target_warehouse_id,
        reference_number=data.reference_number,
        entity_id=data.entity_id,
        unit_price=data.unit_price,
        notes=data.notes,
        created_by=current_user.id,
    )
    await session.commit()
    return movement


@router.get("/movements")
async def list_movements(
    item_id: Optional[uuid.UUID] = None,
    warehouse_id: Optional[uuid.UUID] = None,
    movement_type: Optional[MovementType] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Listet Warenbewegungen"""
    service = StockService(session)
    movements, total = await service.get_movement_history(
        company_id=company_id,
        item_id=item_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return {"movements": movements, "total": total}


@router.post("/inventory-count")
async def record_inventory_count(
    data: InventoryCountRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Erfasst eine Inventurzaehlung"""
    service = StockService(session)
    stock, movement = await service.record_inventory_count(
        item_id=data.item_id,
        warehouse_id=data.warehouse_id,
        company_id=company_id,
        counted_quantity=data.counted_quantity,
        created_by=current_user.id,
    )
    await session.commit()

    return {
        "stock_level": {
            "quantity_on_hand": stock.quantity_on_hand,
            "last_count_date": stock.last_count_date,
            "last_count_quantity": stock.last_count_quantity,
        },
        "adjustment_created": movement is not None,
        "adjustment_id": movement.id if movement else None,
    }


# ============================================================================
# Goods Receipt Endpoints
# ============================================================================

@router.post("/goods-receipts", response_model=GoodsReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_goods_receipt(
    data: GoodsReceiptCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Erstellt Wareneingang aus Lieferschein"""
    service = GoodsReceiptService(session)
    try:
        receipt = await service.create_from_delivery_note(
            document_id=data.document_id,
            company_id=company_id,
            warehouse_id=data.warehouse_id,
            receipt_date=data.receipt_date,
            notes=data.notes,
            created_by=current_user.id,
        )
        await session.commit()
        return receipt
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Inventar"))


@router.get("/goods-receipts", response_model=list[GoodsReceiptResponse])
async def list_goods_receipts(
    warehouse_id: Optional[uuid.UUID] = None,
    pending_only: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Listet Wareneingaenge"""
    service = GoodsReceiptService(session)
    if pending_only:
        return await service.list_pending(company_id, warehouse_id, limit, offset)

    # Wenn alle gewünscht, separate Methode oder Anpassung nötig
    return await service.list_pending(company_id, warehouse_id, limit, offset)


@router.get("/goods-receipts/unprocessed-delivery-notes")
async def get_unprocessed_delivery_notes(
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt Lieferscheine ohne Wareneingang zurück"""
    service = GoodsReceiptService(session)
    documents = await service.get_unprocessed_delivery_notes(company_id, limit)

    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "document_type": doc.document_type.value if doc.document_type else None,
            "entity_id": doc.entity_id,
            "created_at": doc.created_at,
            "extracted_data": doc.extracted_data,
        }
        for doc in documents
    ]


@router.get("/goods-receipts/statistics")
async def get_goods_receipt_statistics(
    warehouse_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt Statistiken zu Wareneingaengen zurück"""
    service = GoodsReceiptService(session)
    return await service.get_statistics(company_id, warehouse_id)


@router.get("/goods-receipts/{receipt_id}", response_model=GoodsReceiptResponse)
async def get_goods_receipt(
    receipt_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Gibt einen einzelnen Wareneingang zurück"""
    service = GoodsReceiptService(session)
    receipt = await service.get_by_id(receipt_id, company_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Wareneingang nicht gefunden")
    return receipt


@router.post("/goods-receipts/{receipt_id}/auto-match")
async def auto_match_goods_receipt(
    receipt_id: uuid.UUID,
    min_confidence: float = Query(0.8, ge=0.5, le=1.0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Führt Auto-Matching für Wareneingangszeilen durch"""
    service = GoodsReceiptService(session)
    try:
        result = await service.auto_match_lines(receipt_id, company_id, min_confidence)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Inventar"))


@router.post("/goods-receipts/{receipt_id}/match-line")
async def match_goods_receipt_line(
    receipt_id: uuid.UUID,
    data: LineMatchRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Ordnet eine Zeile manuell einem Artikel zu"""
    service = GoodsReceiptService(session)
    try:
        line = await service.match_line_to_item(data.line_id, data.item_id, company_id)
        await session.commit()
        return GoodsReceiptLineResponse.model_validate(line)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Inventar"))


@router.patch("/goods-receipts/{receipt_id}/line-quantity")
async def update_goods_receipt_line_quantity(
    receipt_id: uuid.UUID,
    data: LineQuantityUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Aktualisiert die empfangene Menge einer Zeile"""
    service = GoodsReceiptService(session)
    try:
        line = await service.update_line_quantity(data.line_id, company_id, data.quantity_received)
        await session.commit()
        return GoodsReceiptLineResponse.model_validate(line)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Inventar"))


@router.post("/goods-receipts/{receipt_id}/process")
async def process_goods_receipt(
    receipt_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_current_company_id),
):
    """Verarbeitet Wareneingang und bucht Bestände"""
    service = GoodsReceiptService(session)
    try:
        result = await service.process_receipt(receipt_id, company_id, current_user.id)
        await session.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Inventar"))
