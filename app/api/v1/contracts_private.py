# -*- coding: utf-8 -*-
"""
Private Contract Management API Endpoints.

P5.1: Vertragsmanagement fuer das Privat-Modul.

Endpunkte fuer:
- CRUD-Operationen fuer private Vertraege
- OCR-basierte Vertragserkennung
- Kuendigungsfrist-Tracking
- Erinnerungssystem
- Kostenuebersicht
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, status, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User, PrivatSpace
from app.db.schemas import PrivatAccessLevel
from app.db.models_privat_contracts import (
    PrivatContractCategory,
    PrivatContractStatus,
)
from app.services.privat.contract_management_service import (
    get_contract_management_service,
    PrivatContractManagementService,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["privat-contracts"])


# =============================================================================
# Schemas
# =============================================================================


class PrivatContractCreate(BaseModel):
    """Schema fuer Vertragserstellung."""
    title: str = Field(..., min_length=1, max_length=255)
    partner_name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(default="sonstige", max_length=50)
    contract_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_months: Optional[int] = Field(None, ge=1)
    cancellation_notice_days: Optional[int] = Field(None, ge=0)
    auto_renewal: bool = False
    renewal_period_months: Optional[int] = Field(None, ge=1)
    monthly_cost: Optional[Decimal] = Field(None, ge=0)
    yearly_cost: Optional[Decimal] = Field(None, ge=0)
    document_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class PrivatContractUpdate(BaseModel):
    """Schema fuer Vertragsaktualisierung."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    partner_name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=30)
    contract_number: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_months: Optional[int] = Field(None, ge=1)
    cancellation_notice_days: Optional[int] = Field(None, ge=0)
    auto_renewal: Optional[bool] = None
    renewal_period_months: Optional[int] = Field(None, ge=1)
    monthly_cost: Optional[Decimal] = Field(None, ge=0)
    yearly_cost: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class PrivatContractResponse(BaseModel):
    """Response-Schema fuer einen Vertrag."""
    id: uuid.UUID
    space_id: uuid.UUID
    title: str
    partner_name: str
    contract_number: Optional[str] = None
    category: str
    status: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    duration_months: Optional[int] = None
    cancellation_notice_days: Optional[int] = None
    next_cancellation_date: Optional[date] = None
    auto_renewal: bool = False
    renewal_period_months: Optional[int] = None
    monthly_cost: Optional[Decimal] = None
    yearly_cost: Optional[Decimal] = None
    currency: str = "EUR"
    document_id: Optional[uuid.UUID] = None
    extraction_confidence: Optional[float] = None
    notes: Optional[str] = None
    tags: List[str] = []
    days_until_cancellation: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class PrivatContractListResponse(BaseModel):
    """Response-Schema fuer Vertragsliste."""
    items: List[PrivatContractResponse]
    total: int
    page: int
    page_size: int


class ContractExtractionResponse(BaseModel):
    """Response-Schema fuer Vertragsextraktion."""
    contract: PrivatContractResponse
    extraction: dict


class ContractCostSummary(BaseModel):
    """Response-Schema fuer Kostenuebersicht."""
    monthly_total: Decimal
    yearly_total: Decimal
    by_category: dict


class ReminderResponse(BaseModel):
    """Response-Schema fuer Erinnerungen."""
    id: uuid.UUID
    contract_id: uuid.UUID
    reminder_date: date
    days_before_deadline: int
    reminder_type: str
    is_sent: bool
    sent_at: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================


def _contract_to_response(contract: object) -> PrivatContractResponse:
    """Konvertiert ein Contract-Model zu einem Response-Schema."""
    today = date.today()
    days_until = None
    if contract.next_cancellation_date:  # type: ignore[union-attr]
        days_until = (contract.next_cancellation_date - today).days  # type: ignore[union-attr]

    confidence = None
    if contract.extraction_confidence:  # type: ignore[union-attr]
        confidence = float(contract.extraction_confidence)  # type: ignore[union-attr]

    return PrivatContractResponse(
        id=contract.id,  # type: ignore[union-attr]
        space_id=contract.space_id,  # type: ignore[union-attr]
        title=contract.title,  # type: ignore[union-attr]
        partner_name=contract.partner_name,  # type: ignore[union-attr]
        contract_number=contract.contract_number,  # type: ignore[union-attr]
        category=contract.category,  # type: ignore[union-attr]
        status=contract.status,  # type: ignore[union-attr]
        description=contract.description,  # type: ignore[union-attr]
        start_date=contract.start_date,  # type: ignore[union-attr]
        end_date=contract.end_date,  # type: ignore[union-attr]
        duration_months=contract.duration_months,  # type: ignore[union-attr]
        cancellation_notice_days=contract.cancellation_notice_days,  # type: ignore[union-attr]
        next_cancellation_date=contract.next_cancellation_date,  # type: ignore[union-attr]
        auto_renewal=contract.auto_renewal,  # type: ignore[union-attr]
        renewal_period_months=contract.renewal_period_months,  # type: ignore[union-attr]
        monthly_cost=contract.monthly_cost,  # type: ignore[union-attr]
        yearly_cost=contract.yearly_cost,  # type: ignore[union-attr]
        currency=contract.currency,  # type: ignore[union-attr]
        document_id=contract.document_id,  # type: ignore[union-attr]
        extraction_confidence=confidence,
        notes=contract.notes,  # type: ignore[union-attr]
        tags=contract.tags or [],  # type: ignore[union-attr]
        days_until_cancellation=days_until,
        created_at=contract.created_at.isoformat() if contract.created_at else None,  # type: ignore[union-attr]
        updated_at=contract.updated_at.isoformat() if contract.updated_at else None,  # type: ignore[union-attr]
    )


async def _get_space_or_404(
    db: AsyncSession,
    space_id: uuid.UUID,
    user: User,
    required_level: PrivatAccessLevel = PrivatAccessLevel.READ,
) -> PrivatSpace:
    """Prueft Space-Zugriff und gibt Space zurueck."""
    from app.services.privat import PrivatSpaceService

    space_service = PrivatSpaceService()
    space = await space_service.get_with_access_check(
        db, space_id, user.id,
        required_level.value if hasattr(required_level, "value") else required_level,
    )
    if space is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space nicht gefunden",
        )
    return space


# =============================================================================
# Contract CRUD Endpoints
# =============================================================================


@router.post(
    "/privat/spaces/{space_id}/contracts",
    response_model=PrivatContractResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vertrag erstellen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def create_contract(
    request: Request,
    space_id: uuid.UUID,
    data: PrivatContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatContractResponse:
    """Erstellt einen neuen privaten Vertrag."""
    await _get_space_or_404(db, space_id, current_user, PrivatAccessLevel.WRITE)

    service = get_contract_management_service()
    contract = await service.create_contract(
        db=db,
        space_id=space_id,
        title=data.title,
        partner_name=data.partner_name,
        category=data.category,
        contract_number=data.contract_number,
        description=data.description,
        start_date=data.start_date,
        end_date=data.end_date,
        duration_months=data.duration_months,
        cancellation_notice_days=data.cancellation_notice_days,
        auto_renewal=data.auto_renewal,
        renewal_period_months=data.renewal_period_months,
        monthly_cost=data.monthly_cost,
        yearly_cost=data.yearly_cost,
        document_id=data.document_id,
        notes=data.notes,
        tags=data.tags,
    )

    # Erinnerungen planen
    if contract.next_cancellation_date:
        await service.schedule_reminders(db, contract.id)

    return _contract_to_response(contract)


@router.get(
    "/privat/spaces/{space_id}/contracts",
    response_model=PrivatContractListResponse,
    summary="Vertraege auflisten",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def list_contracts(
    request: Request,
    space_id: uuid.UUID,
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter nach Status"),
    expiring_within_days: Optional[int] = Query(None, ge=1, le=365, description="Ablaufende Vertraege innerhalb X Tagen"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatContractListResponse:
    """Listet alle Vertraege eines Spaces mit Filteroptionen."""
    await _get_space_or_404(db, space_id, current_user)

    service = get_contract_management_service()
    contracts, total = await service.list_contracts(
        db=db,
        space_id=space_id,
        category=category,
        status_filter=status_filter,
        expiring_within_days=expiring_within_days,
        page=page,
        page_size=page_size,
    )

    return PrivatContractListResponse(
        items=[_contract_to_response(c) for c in contracts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/privat/contracts/{contract_id}",
    response_model=PrivatContractResponse,
    summary="Vertragsdetails abrufen",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_contract(
    request: Request,
    contract_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatContractResponse:
    """Holt Vertragsdetails mit Kuendigungsfrist-Informationen."""
    service = get_contract_management_service()
    contract = await service.get_by_id(db, contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # SECURITY: Pruefe Space-Zugriff
    await _get_space_or_404(db, contract.space_id, current_user)

    return _contract_to_response(contract)


@router.put(
    "/privat/contracts/{contract_id}",
    response_model=PrivatContractResponse,
    summary="Vertrag aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def update_contract(
    request: Request,
    contract_id: uuid.UUID,
    data: PrivatContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PrivatContractResponse:
    """Aktualisiert einen Vertrag. Kuendigungsfrist wird automatisch neu berechnet."""
    service = get_contract_management_service()
    existing = await service.get_by_id(db, contract_id)

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # SECURITY: Pruefe Space-Zugriff (WRITE)
    await _get_space_or_404(db, existing.space_id, current_user, PrivatAccessLevel.WRITE)

    updates = data.model_dump(exclude_unset=True)
    contract = await service.update_contract(
        db=db,
        contract_id=contract_id,
        space_id=existing.space_id,
        **updates,
    )

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # Erinnerungen aktualisieren
    if contract.next_cancellation_date:
        await service.schedule_reminders(db, contract.id)

    return _contract_to_response(contract)


@router.delete(
    "/privat/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Vertrag loeschen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def delete_contract(
    request: Request,
    contract_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Loescht einen Vertrag (Soft-Delete)."""
    service = get_contract_management_service()
    existing = await service.get_by_id(db, contract_id)

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # SECURITY: Pruefe Space-Zugriff (WRITE)
    await _get_space_or_404(db, existing.space_id, current_user, PrivatAccessLevel.WRITE)

    success = await service.delete_contract(db, contract_id, existing.space_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )


# =============================================================================
# Expiring Contracts
# =============================================================================


@router.get(
    "/privat/spaces/{space_id}/contracts/expiring",
    response_model=List[PrivatContractResponse],
    summary="Ablaufende Vertraege",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_expiring_contracts(
    request: Request,
    space_id: uuid.UUID,
    days: int = Query(90, ge=1, le=365, description="Tage voraus"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PrivatContractResponse]:
    """Holt Vertraege mit bevorstehender Kuendigungsfrist."""
    await _get_space_or_404(db, space_id, current_user)

    service = get_contract_management_service()
    contracts = await service.get_expiring_contracts(db, space_id, days)

    return [_contract_to_response(c) for c in contracts]


# =============================================================================
# OCR Extraction
# =============================================================================


@router.post(
    "/privat/spaces/{space_id}/contracts/extract/{document_id}",
    response_model=ContractExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vertrag aus OCR-Dokument extrahieren",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def extract_contract_from_document(
    request: Request,
    space_id: uuid.UUID,
    document_id: uuid.UUID,
    title: Optional[str] = Query(None, description="Optionaler Titel"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ContractExtractionResponse:
    """Extrahiert Vertragsinformationen aus einem OCR-Dokument.

    Analysiert den extrahierten Text und erstellt automatisch
    einen Vertrag mit erkannten Feldern:
    - Vertragspartner
    - Vertragsbeginn / Laufzeit
    - Kuendigungsfrist
    - Kosten (monatlich/jaehrlich)
    - Vertragskategorie
    """
    await _get_space_or_404(db, space_id, current_user, PrivatAccessLevel.WRITE)

    # Dokument laden
    from app.db.models import Document

    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )
    if not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen extrahierten Text. Bitte zuerst OCR durchfuehren.",
        )

    service = get_contract_management_service()
    contract, info = await service.create_from_extraction(
        db=db,
        space_id=space_id,
        document_id=document_id,
        ocr_text=doc.extracted_text,
        title=title,
    )

    # Erinnerungen planen
    if contract.next_cancellation_date:
        await service.schedule_reminders(db, contract.id)

    return ContractExtractionResponse(
        contract=_contract_to_response(contract),
        extraction={
            "confidence": info.confidence,
            "category_detected": info.category,
            "fields_found": list(info.raw_fields.keys()),
            "raw_fields": info.raw_fields,
        },
    )


# =============================================================================
# Reminders
# =============================================================================


@router.post(
    "/privat/contracts/{contract_id}/remind",
    response_model=List[ReminderResponse],
    summary="Erinnerungen setzen/aktualisieren",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def set_reminders(
    request: Request,
    contract_id: uuid.UUID,
    reminder_days: Optional[List[int]] = Query(
        None,
        description="Tage vor Kuendigungsfrist (z.B. 30,14,7)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[ReminderResponse]:
    """Setzt oder aktualisiert Erinnerungen fuer einen Vertrag.

    Standard-Erinnerungen: 30, 14 und 7 Tage vor Kuendigungsfrist.
    """
    service = get_contract_management_service()
    contract = await service.get_by_id(db, contract_id)

    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vertrag nicht gefunden",
        )

    # SECURITY: Pruefe Space-Zugriff
    await _get_space_or_404(db, contract.space_id, current_user, PrivatAccessLevel.WRITE)

    if not contract.next_cancellation_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kein Kuendigungsdatum vorhanden. Bitte zuerst Vertragslaufzeit und Kuendigungsfrist eintragen.",
        )

    reminders = await service.schedule_reminders(db, contract_id, reminder_days)

    return [
        ReminderResponse(
            id=r.id,
            contract_id=r.contract_id,
            reminder_date=r.reminder_date,
            days_before_deadline=r.days_before_deadline,
            reminder_type=r.reminder_type,
            is_sent=r.is_sent,
            sent_at=r.sent_at.isoformat() if r.sent_at else None,
        )
        for r in reminders
    ]


# =============================================================================
# Cost Summary
# =============================================================================


@router.get(
    "/privat/spaces/{space_id}/contracts/costs",
    response_model=ContractCostSummary,
    summary="Vertragskostenuebersicht",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_contract_costs(
    request: Request,
    space_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ContractCostSummary:
    """Berechnet die Gesamtkosten aller aktiven Vertraege.

    Liefert:
    - Monatliche Gesamtkosten
    - Jaehrliche Gesamtkosten
    - Aufschluesselung nach Kategorie
    """
    await _get_space_or_404(db, space_id, current_user)

    service = get_contract_management_service()
    summary = await service.get_contract_cost_summary(db, space_id)

    return ContractCostSummary(
        monthly_total=summary["monthly_total"],
        yearly_total=summary["yearly_total"],
        by_category={
            k: float(v) for k, v in summary["by_category"].items()
        },
    )
