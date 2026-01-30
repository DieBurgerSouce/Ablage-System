# -*- coding: utf-8 -*-
"""Shipment Tracking API - Paketdienst-Integration.

Endpoints fuer:
- Sendungsverfolgung (DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post)
- CRUD fuer Sendungen
- Statistiken und Analysen
- Carrier-Erkennung

Multi-Tenant: Alle Endpoints filtern nach company_id!
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail
from app.api.dependencies import (
    get_current_active_user,
    get_db,
)
from app.middleware.company_context import get_current_company_id
from app.db.models import User, ShipmentCarrier, ShipmentDirection, ShipmentStatusEnum
from app.services.shipping import (
    CarrierService,
    Carrier,
    ShipmentStatus,
)
from app.services.shipping.carrier_service import ShipmentDirection as ServiceDirection

router = APIRouter(prefix="/shipments", tags=["Sendungen"])

# Service Instance
_carrier_service: Optional[CarrierService] = None


def get_carrier_service() -> CarrierService:
    """Gibt Singleton CarrierService zurueck."""
    global _carrier_service
    if _carrier_service is None:
        _carrier_service = CarrierService()
    return _carrier_service


# ==================== Schemas ====================


class ShipmentCreate(BaseModel):
    """Schema zum Erstellen einer Sendung."""
    tracking_number: str = Field(..., min_length=8, max_length=50, description="Sendungsnummer")
    direction: str = Field(default="inbound", description="Richtung: inbound, outbound, return")
    carrier: Optional[str] = Field(None, description="Carrier (optional, wird automatisch erkannt)")
    entity_id: Optional[UUID] = Field(None, description="Verknuepfter Kunde/Lieferant")
    document_id: Optional[UUID] = Field(None, description="Verknuepftes Dokument")
    reference: Optional[str] = Field(None, max_length=100, description="Referenz (Bestellnummer)")
    notes: Optional[str] = Field(None, description="Notizen")
    shipping_cost: Optional[Decimal] = Field(None, ge=0, description="Versandkosten")

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        valid = ["inbound", "outbound", "return"]
        if v.lower() not in valid:
            raise ValueError(f"Richtung muss eine von {valid} sein")
        return v.lower()

    @field_validator("carrier")
    @classmethod
    def validate_carrier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = [c.value for c in ShipmentCarrier]
        if v.lower() not in valid:
            raise ValueError(f"Carrier muss einer von {valid} sein")
        return v.lower()


class ShipmentUpdate(BaseModel):
    """Schema zum Aktualisieren einer Sendung."""
    reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    shipping_cost: Optional[Decimal] = Field(None, ge=0)
    entity_id: Optional[UUID] = None
    document_id: Optional[UUID] = None


class ShipmentEventResponse(BaseModel):
    """Response fuer ein Tracking-Event."""
    id: UUID
    timestamp: datetime
    status: str
    description: Optional[str]
    location: Optional[str]
    postal_code: Optional[str]
    country_code: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ShipmentResponse(BaseModel):
    """Response fuer eine Sendung."""
    id: UUID
    tracking_number: str
    carrier: str
    direction: str
    status: str
    status_description: Optional[str]
    tracking_url: Optional[str]
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    last_tracking_update: Optional[datetime]
    origin: Optional[str]
    destination: Optional[str]
    weight_kg: Optional[float]
    service_type: Optional[str]
    reference: Optional[str]
    notes: Optional[str]
    shipping_cost: Optional[Decimal]
    currency: str
    entity_id: Optional[UUID]
    document_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    events: List[ShipmentEventResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ShipmentListResponse(BaseModel):
    """Response fuer Sendungsliste."""
    items: List[ShipmentResponse]
    total: int
    page: int
    per_page: int
    pages: int


class TrackingResponse(BaseModel):
    """Response fuer Tracking-Abfrage."""
    tracking_number: str
    carrier: str
    current_status: str
    status_description: str
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    origin: Optional[str]
    destination: Optional[str]
    weight_kg: Optional[float]
    service_type: Optional[str]
    events: List[Dict[str, Any]]
    tracking_url: Optional[str]
    last_updated: datetime


class CarrierDetectionResponse(BaseModel):
    """Response fuer Carrier-Erkennung."""
    tracking_number: str
    detected_carrier: str
    tracking_url: Optional[str]
    confidence: str  # "high", "medium", "low"


class ShipmentSummaryResponse(BaseModel):
    """Response fuer Sendungs-Zusammenfassung."""
    total: int
    by_carrier: Dict[str, int]
    by_status: Dict[str, int]
    pending_delivery: int
    delivered_today: int
    exceptions: int


class CarrierStatisticsResponse(BaseModel):
    """Response fuer Carrier-Statistiken."""
    carrier: str
    total_shipments: int
    delivered: int
    avg_delivery_days: float
    on_time_rate: float
    exception_rate: float


# ==================== Endpoints ====================


@router.post("", response_model=ShipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_shipment(
    data: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentResponse:
    """Erstellt eine neue Sendung.

    Der Carrier wird automatisch anhand der Tracking-Nummer erkannt,
    wenn nicht explizit angegeben.
    """
    service = get_carrier_service()

    # Carrier ermitteln
    carrier = None
    if data.carrier:
        carrier = Carrier(data.carrier)
    else:
        carrier = service.detect_carrier(data.tracking_number)

    # Direction mapping
    direction_map = {
        "inbound": ServiceDirection.INBOUND,
        "outbound": ServiceDirection.OUTBOUND,
        "return": ServiceDirection.RETURN,
    }

    try:
        shipment = await service.create_shipment(
            db=db,
            company_id=company_id,
            tracking_number=data.tracking_number,
            direction=direction_map[data.direction],
            carrier=carrier,
            entity_id=data.entity_id,
            document_id=data.document_id,
            reference=data.reference,
            notes=data.notes,
        )

        # Update shipping cost if provided
        if data.shipping_cost is not None:
            shipment.shipping_cost = data.shipping_cost
            await db.commit()
            await db.refresh(shipment)

        return ShipmentResponse.model_validate(shipment)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Vorgang")
        )


@router.get("", response_model=ShipmentListResponse)
async def list_shipments(
    direction: Optional[str] = Query(None, description="Filter nach Richtung"),
    status: Optional[str] = Query(None, description="Filter nach Status"),
    carrier: Optional[str] = Query(None, description="Filter nach Carrier"),
    entity_id: Optional[UUID] = Query(None, description="Filter nach Entity"),
    page: int = Query(1, ge=1, description="Seite"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentListResponse:
    """Listet alle Sendungen mit optionalen Filtern."""
    service = get_carrier_service()

    # Filter mapping
    direction_filter = None
    if direction:
        try:
            direction_filter = ServiceDirection(direction)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungueltige Richtung: {direction}")

    status_filter = None
    if status:
        try:
            status_filter = ShipmentStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungueltiger Status: {status}")

    carrier_filter = None
    if carrier:
        try:
            carrier_filter = Carrier(carrier)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungueltiger Carrier: {carrier}")

    shipments, total = await service.list_shipments(
        db=db,
        company_id=company_id,
        direction=direction_filter,
        status=status_filter,
        carrier=carrier_filter,
        entity_id=entity_id,
        page=page,
        per_page=per_page,
    )

    return ShipmentListResponse(
        items=[ShipmentResponse.model_validate(s) for s in shipments],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get("/summary", response_model=ShipmentSummaryResponse)
async def get_shipment_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentSummaryResponse:
    """Gibt eine Zusammenfassung aller Sendungen zurueck."""
    service = get_carrier_service()
    summary = await service.get_shipment_summary(db, company_id)
    return ShipmentSummaryResponse(**summary)


@router.get("/statistics", response_model=List[CarrierStatisticsResponse])
async def get_carrier_statistics(
    days: int = Query(90, ge=7, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> List[CarrierStatisticsResponse]:
    """Gibt Statistiken pro Carrier zurueck."""
    service = get_carrier_service()
    stats = await service.get_carrier_statistics(db, company_id, days)
    return [CarrierStatisticsResponse(**s) for s in stats]


@router.get("/detect-carrier", response_model=CarrierDetectionResponse)
async def detect_carrier(
    tracking_number: str = Query(..., min_length=8, description="Sendungsnummer"),
    current_user: User = Depends(get_current_active_user),
) -> CarrierDetectionResponse:
    """Erkennt den Carrier anhand der Tracking-Nummer."""
    service = get_carrier_service()

    carrier = service.detect_carrier(tracking_number)
    tracking_url = service.get_tracking_url(tracking_number, carrier)

    confidence = "high" if carrier != Carrier.UNKNOWN else "low"

    return CarrierDetectionResponse(
        tracking_number=tracking_number,
        detected_carrier=carrier.value,
        tracking_url=tracking_url,
        confidence=confidence,
    )


@router.get("/track", response_model=TrackingResponse)
async def track_shipment(
    tracking_number: str = Query(..., min_length=8, description="Sendungsnummer"),
    carrier: Optional[str] = Query(None, description="Carrier (optional)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> TrackingResponse:
    """Fragt Tracking-Informationen fuer eine Sendungsnummer ab.

    Funktioniert auch fuer Sendungen, die noch nicht im System erfasst sind.
    """
    service = get_carrier_service()

    carrier_enum = None
    if carrier:
        try:
            carrier_enum = Carrier(carrier)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungueltiger Carrier: {carrier}")

    try:
        result = await service.track_shipment(
            db=db,
            tracking_number=tracking_number,
            carrier=carrier_enum,
            company_id=company_id,
            save_to_db=False,  # Nur abfragen, nicht speichern
        )

        return TrackingResponse(
            tracking_number=result["tracking_number"],
            carrier=result["carrier"],
            current_status=result["current_status"].value,
            status_description=result["status_description"],
            estimated_delivery=result["estimated_delivery"],
            actual_delivery=result["actual_delivery"],
            origin=result["origin"],
            destination=result["destination"],
            weight_kg=result["weight_kg"],
            service_type=result["service_type"],
            events=[{
                "timestamp": e["timestamp"].isoformat() if e["timestamp"] else None,
                "status": e["status"].value,
                "description": e["description"],
                "location": e["location"],
                "postal_code": e["postal_code"],
                "country_code": e["country_code"],
            } for e in result["events"]],
            tracking_url=service.get_tracking_url(tracking_number),
            last_updated=result["last_updated"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_detail(e, "Vorgang")
        )


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentResponse:
    """Holt eine einzelne Sendung."""
    service = get_carrier_service()

    shipment = await service.get_shipment(db, company_id, shipment_id)
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sendung nicht gefunden"
        )

    return ShipmentResponse.model_validate(shipment)


@router.patch("/{shipment_id}", response_model=ShipmentResponse)
async def update_shipment(
    shipment_id: UUID,
    data: ShipmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentResponse:
    """Aktualisiert eine Sendung."""
    service = get_carrier_service()

    shipment = await service.get_shipment(db, company_id, shipment_id)
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sendung nicht gefunden"
        )

    # Update fields
    if data.reference is not None:
        shipment.reference = data.reference
    if data.notes is not None:
        shipment.notes = data.notes
    if data.shipping_cost is not None:
        shipment.shipping_cost = data.shipping_cost
    if data.entity_id is not None:
        shipment.entity_id = data.entity_id
    if data.document_id is not None:
        shipment.document_id = data.document_id

    await db.commit()
    await db.refresh(shipment)

    return ShipmentResponse.model_validate(shipment)


@router.post("/{shipment_id}/refresh", response_model=ShipmentResponse)
async def refresh_shipment_tracking(
    shipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> ShipmentResponse:
    """Aktualisiert die Tracking-Daten einer Sendung."""
    service = get_carrier_service()

    shipment = await service.get_shipment(db, company_id, shipment_id)
    if not shipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sendung nicht gefunden"
        )

    try:
        await service.track_shipment(
            db=db,
            tracking_number=shipment.tracking_number,
            carrier=Carrier(shipment.carrier),
            company_id=company_id,
            save_to_db=True,
        )

        # Refresh shipment
        await db.refresh(shipment)
        return ShipmentResponse.model_validate(shipment)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_detail(e, "Vorgang")
        )


@router.delete("/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipment(
    shipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> None:
    """Loescht eine Sendung (Soft Delete)."""
    service = get_carrier_service()

    deleted = await service.delete_shipment(db, company_id, shipment_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sendung nicht gefunden"
        )


@router.post("/refresh-all")
async def refresh_all_shipments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
) -> Dict[str, int]:
    """Aktualisiert alle aktiven Sendungen.

    Nur nicht-zugestellte und nicht-zurueckgeschickte Sendungen werden aktualisiert.
    """
    service = get_carrier_service()

    updated, failed = await service.refresh_all_active_shipments(db, company_id)

    return {
        "updated": updated,
        "failed": failed,
    }


# ==================== Carrier-spezifische Infos ====================


@router.get("/carriers/list")
async def list_carriers(
    current_user: User = Depends(get_current_active_user),
) -> List[Dict[str, str]]:
    """Listet alle unterstuetzten Carrier auf."""
    carriers = [
        {
            "id": "dhl",
            "name": "DHL",
            "description": "DHL Paket Deutschland - Marktfuehrer",
            "tracking_url_pattern": "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={tracking_number}",
        },
        {
            "id": "dpd",
            "name": "DPD",
            "description": "DPD Deutschland - B2B stark",
            "tracking_url_pattern": "https://tracking.dpd.de/status/de_DE/parcel/{tracking_number}",
        },
        {
            "id": "hermes",
            "name": "Hermes",
            "description": "Hermes Deutschland - B2C stark",
            "tracking_url_pattern": "https://www.myhermes.de/empfangen/sendungsverfolgung/?sendung={tracking_number}",
        },
        {
            "id": "ups",
            "name": "UPS",
            "description": "UPS - International stark",
            "tracking_url_pattern": "https://www.ups.com/track?tracknum={tracking_number}&loc=de_DE",
        },
        {
            "id": "gls",
            "name": "GLS",
            "description": "GLS Germany - B2B stark",
            "tracking_url_pattern": "https://gls-group.com/DE/de/paketverfolgung?match={tracking_number}",
        },
        {
            "id": "fedex",
            "name": "FedEx",
            "description": "FedEx - Express/International",
            "tracking_url_pattern": "https://www.fedex.com/fedextrack/?trknbr={tracking_number}",
        },
        {
            "id": "deutsche_post",
            "name": "Deutsche Post",
            "description": "Deutsche Post - Briefe und Einschreiben",
            "tracking_url_pattern": "https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode={tracking_number}",
        },
    ]

    return carriers
