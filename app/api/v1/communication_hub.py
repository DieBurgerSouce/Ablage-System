# -*- coding: utf-8 -*-
"""
Communication Hub API - 360° Geschaeftspartner-Ansicht.

Vision 2026+ Feature #1: Kommunikations-Hub
Zentrale Ansicht ALLER Interaktionen mit einem Geschaeftspartner.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_current_company_id
from app.db.models import User
from uuid import UUID
from app.db.models_communication import (
    CommunicationType,
    CommunicationDirection,
    CommunicationSentiment,
)
from app.services.communication_hub_service import CommunicationHubService

router = APIRouter(
    prefix="/entities",
    tags=["Communication Hub"],
)


# =============================================================================
# Request/Response Schemas
# =============================================================================

class TimelineItemResponse(BaseModel):
    """Ein Eintrag in der Kommunikations-Timeline."""
    id: str
    timestamp: datetime
    type: str
    title: str
    description: Optional[str] = None
    icon: str = "MessageSquare"
    color: str = "gray"
    direction: Optional[str] = None
    sentiment: Optional[str] = None
    actor_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class InvoiceSummaryResponse(BaseModel):
    """Zusammenfassung der Rechnungen."""
    total_invoices: int = 0
    open_invoices: int = 0
    overdue_invoices: int = 0
    total_amount: float = 0.0
    open_amount: float = 0.0
    overdue_amount: float = 0.0
    average_payment_days: Optional[float] = None
    last_invoice_date: Optional[datetime] = None
    dunning_level_breakdown: Dict[int, int] = Field(default_factory=dict)


class RiskTrendResponse(BaseModel):
    """Risiko-Trend fuer einen Partner."""
    current_score: Optional[float] = None
    previous_score: Optional[float] = None
    trend_direction: str = "stable"
    trend_percentage: float = 0.0
    risk_level: str = "unknown"
    factors: Dict[str, float] = Field(default_factory=dict)


class CommunicationHubResponse(BaseModel):
    """Vollstaendige 360°-Ansicht eines Geschaeftspartners."""
    entity: Dict[str, Any]
    timeline: List[TimelineItemResponse]
    invoice_summary: InvoiceSummaryResponse
    risk_trend: RiskTrendResponse
    communication_stats: Dict[str, Any]
    recent_documents: List[Dict[str, Any]]
    open_tasks: List[Dict[str, Any]]
    phone_notes: List[Dict[str, Any]]


class PhoneNoteCreate(BaseModel):
    """Schema fuer neue Telefon-Notiz."""
    subject: str = Field(..., min_length=1, max_length=255, description="Betreff des Anrufs")
    notes: Optional[str] = Field(None, max_length=10000, description="Gespraechsnotizen")
    call_type: str = Field(
        default=CommunicationType.PHONE_CALL.value,
        description="Art der Kommunikation"
    )
    direction: str = Field(
        default=CommunicationDirection.INBOUND.value,
        description="Richtung (eingehend/ausgehend)"
    )
    contact_person: Optional[str] = Field(None, max_length=255, description="Name des Ansprechpartners")
    phone_number: Optional[str] = Field(None, max_length=50, description="Telefonnummer")
    duration_minutes: Optional[int] = Field(None, ge=0, le=480, description="Gespraechsdauer in Minuten")
    sentiment: Optional[str] = Field(None, description="Stimmung/Ergebnis")
    follow_up_required: bool = Field(default=False, description="Nachfassen erforderlich?")
    follow_up_date: Optional[datetime] = Field(None, description="Follow-up Datum")
    follow_up_notes: Optional[str] = Field(None, max_length=2000, description="Follow-up Notizen")
    call_datetime: Optional[datetime] = Field(None, description="Zeitpunkt des Anrufs")
    tags: List[str] = Field(default_factory=list, max_length=20, description="Tags")


class PhoneNoteUpdate(BaseModel):
    """Schema fuer Aktualisierung einer Telefon-Notiz."""
    subject: Optional[str] = Field(None, min_length=1, max_length=255)
    notes: Optional[str] = Field(None, max_length=10000)
    summary: Optional[str] = Field(None, max_length=500)
    call_type: Optional[str] = None
    direction: Optional[str] = None
    contact_person: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=50)
    duration_minutes: Optional[int] = Field(None, ge=0, le=480)
    sentiment: Optional[str] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = Field(None, max_length=2000)
    follow_up_completed: Optional[bool] = None
    tags: Optional[List[str]] = Field(None, max_length=20)


class PhoneNoteResponse(BaseModel):
    """Response fuer eine Telefon-Notiz."""
    id: str
    entity_id: str
    company_id: str
    call_type: str
    direction: str
    contact_person: Optional[str] = None
    phone_number: Optional[str] = None
    duration_minutes: Optional[int] = None
    subject: str
    notes: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    follow_up_required: bool = False
    follow_up_date: Optional[datetime] = None
    follow_up_notes: Optional[str] = None
    follow_up_completed: bool = False
    related_document_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    call_datetime: Optional[datetime] = None
    created_at: Optional[datetime] = None
    created_by_id: Optional[str] = None
    assigned_to_id: Optional[str] = None

    class Config:
        from_attributes = True


# =============================================================================
# Communication Hub Endpoints
# =============================================================================

@router.get(
    "/{entity_id}/communication-hub",
    response_model=CommunicationHubResponse,
    summary="360° Geschaeftspartner-Ansicht",
    description="Holt alle Kommunikationsdaten zu einem Geschaeftspartner.",
)
async def get_communication_hub(
    entity_id: uuid.UUID,
    timeline_limit: int = Query(default=50, ge=1, le=200, description="Max. Timeline-Eintraege"),
    documents_limit: int = Query(default=10, ge=1, le=50, description="Max. Dokumente"),
    sections: Optional[str] = Query(
        default=None,
        description="Komma-getrennte Liste der gewuenschten Sektionen (entity,timeline,invoices,risk,stats,documents,tasks,phone_notes)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> CommunicationHubResponse:
    """
    Holt die vollstaendige 360°-Ansicht eines Geschaeftspartners.

    Aggregiert alle verfuegbaren Daten:
    - Basisdaten des Geschaeftspartners
    - Kommunikations-Timeline (Telefonate, Emails, Dokumente, Mahnungen)
    - Rechnungs-Zusammenfassung
    - Risiko-Trend
    - Kommunikations-Statistiken
    - Aktuelle Dokumente
    - Offene Aufgaben (Follow-ups)
    - Telefon-Notizen
    """
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    include_sections = None
    if sections:
        include_sections = [s.strip() for s in sections.split(",")]

    service = CommunicationHubService(db)
    hub_data = await service.get_communication_hub(
        entity_id=entity_id,
        company_id=company_id,  # SECURITY FIX: Use validated company_id
        timeline_limit=timeline_limit,
        documents_limit=documents_limit,
        include_sections=include_sections,
    )

    # Konvertiere zu Response
    timeline_items = [
        TimelineItemResponse(
            id=str(item.id),
            timestamp=item.timestamp,
            type=item.type,
            title=item.title,
            description=item.description,
            icon=item.icon,
            color=item.color,
            direction=item.direction,
            sentiment=item.sentiment,
            actor_name=item.actor_name,
            metadata=item.metadata,
        )
        for item in hub_data.timeline
    ]

    invoice_summary = InvoiceSummaryResponse(
        total_invoices=hub_data.invoice_summary.total_invoices,
        open_invoices=hub_data.invoice_summary.open_invoices,
        overdue_invoices=hub_data.invoice_summary.overdue_invoices,
        total_amount=float(hub_data.invoice_summary.total_amount),
        open_amount=float(hub_data.invoice_summary.open_amount),
        overdue_amount=float(hub_data.invoice_summary.overdue_amount),
        average_payment_days=hub_data.invoice_summary.average_payment_days,
        last_invoice_date=hub_data.invoice_summary.last_invoice_date,
        dunning_level_breakdown=hub_data.invoice_summary.dunning_level_breakdown,
    )

    risk_trend = RiskTrendResponse(
        current_score=hub_data.risk_trend.current_score,
        previous_score=hub_data.risk_trend.previous_score,
        trend_direction=hub_data.risk_trend.trend_direction,
        trend_percentage=hub_data.risk_trend.trend_percentage,
        risk_level=hub_data.risk_trend.risk_level,
        factors=hub_data.risk_trend.factors,
    )

    return CommunicationHubResponse(
        entity=hub_data.entity,
        timeline=timeline_items,
        invoice_summary=invoice_summary,
        risk_trend=risk_trend,
        communication_stats=hub_data.communication_stats,
        recent_documents=hub_data.recent_documents,
        open_tasks=hub_data.open_tasks,
        phone_notes=hub_data.phone_notes,
    )


# =============================================================================
# Phone Note CRUD Endpoints
# =============================================================================

@router.get(
    "/{entity_id}/phone-notes",
    response_model=List[PhoneNoteResponse],
    summary="Telefon-Notizen auflisten",
    description="Listet alle Telefon-Notizen eines Geschaeftspartners auf.",
)
async def list_phone_notes(
    entity_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[PhoneNoteResponse]:
    """Listet alle Telefon-Notizen eines Geschaeftspartners auf."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    service = CommunicationHubService(db)
    notes = await service._get_phone_notes(
        entity_id=entity_id,
        company_id=company_id,  # SECURITY FIX
        limit=limit,
    )

    return [PhoneNoteResponse(**note) for note in notes]


@router.post(
    "/{entity_id}/phone-notes",
    response_model=PhoneNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Telefon-Notiz erstellen",
    description="Erstellt eine neue Telefon-Notiz fuer einen Geschaeftspartner.",
)
async def create_phone_note(
    entity_id: uuid.UUID,
    data: PhoneNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> PhoneNoteResponse:
    """Erstellt eine neue Telefon-Notiz."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    # Validiere call_type
    valid_call_types = [ct.value for ct in CommunicationType]
    if data.call_type not in valid_call_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger call_type. Erlaubt: {valid_call_types}"
        )

    # Validiere direction
    valid_directions = [d.value for d in CommunicationDirection]
    if data.direction not in valid_directions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige direction. Erlaubt: {valid_directions}"
        )

    # Validiere sentiment falls vorhanden
    if data.sentiment:
        valid_sentiments = [s.value for s in CommunicationSentiment]
        if data.sentiment not in valid_sentiments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger sentiment. Erlaubt: {valid_sentiments}"
            )

    service = CommunicationHubService(db)
    note = await service.create_phone_note(
        entity_id=entity_id,
        company_id=company_id,  # SECURITY FIX
        user_id=current_user.id,
        subject=data.subject,
        notes=data.notes,
        call_type=data.call_type,
        direction=data.direction,
        contact_person=data.contact_person,
        phone_number=data.phone_number,
        duration_minutes=data.duration_minutes,
        sentiment=data.sentiment,
        follow_up_required=data.follow_up_required,
        follow_up_date=data.follow_up_date,
        follow_up_notes=data.follow_up_notes,
        call_datetime=data.call_datetime,
    )

    return PhoneNoteResponse(**note.to_dict())


@router.get(
    "/{entity_id}/phone-notes/{note_id}",
    response_model=PhoneNoteResponse,
    summary="Einzelne Telefon-Notiz abrufen",
    description="Holt eine spezifische Telefon-Notiz.",
)
async def get_phone_note(
    entity_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> PhoneNoteResponse:
    """Holt eine spezifische Telefon-Notiz."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    from sqlalchemy import select
    from app.db.models_communication import PhoneNote

    result = await db.execute(
        select(PhoneNote).where(
            PhoneNote.id == note_id,
            PhoneNote.entity_id == entity_id,
            PhoneNote.company_id == company_id,  # SECURITY FIX
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telefon-Notiz nicht gefunden"
        )

    return PhoneNoteResponse(**note.to_dict())


@router.patch(
    "/{entity_id}/phone-notes/{note_id}",
    response_model=PhoneNoteResponse,
    summary="Telefon-Notiz aktualisieren",
    description="Aktualisiert eine bestehende Telefon-Notiz.",
)
async def update_phone_note(
    entity_id: uuid.UUID,
    note_id: uuid.UUID,
    data: PhoneNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> PhoneNoteResponse:
    """Aktualisiert eine bestehende Telefon-Notiz."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    # Validierungen
    if data.call_type:
        valid_call_types = [ct.value for ct in CommunicationType]
        if data.call_type not in valid_call_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger call_type. Erlaubt: {valid_call_types}"
            )

    if data.direction:
        valid_directions = [d.value for d in CommunicationDirection]
        if data.direction not in valid_directions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltige direction. Erlaubt: {valid_directions}"
            )

    if data.sentiment:
        valid_sentiments = [s.value for s in CommunicationSentiment]
        if data.sentiment not in valid_sentiments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungueltiger sentiment. Erlaubt: {valid_sentiments}"
            )

    service = CommunicationHubService(db)
    note = await service.update_phone_note(
        note_id=note_id,
        company_id=company_id,  # SECURITY FIX
        **data.model_dump(exclude_unset=True),
    )

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telefon-Notiz nicht gefunden"
        )

    return PhoneNoteResponse(**note.to_dict())


@router.delete(
    "/{entity_id}/phone-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Telefon-Notiz loeschen",
    description="Loescht eine Telefon-Notiz.",
)
async def delete_phone_note(
    entity_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
):
    """Loescht eine Telefon-Notiz."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    service = CommunicationHubService(db)
    deleted = await service.delete_phone_note(
        note_id=note_id,
        company_id=company_id,  # SECURITY FIX
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telefon-Notiz nicht gefunden"
        )


@router.post(
    "/{entity_id}/phone-notes/{note_id}/complete-follow-up",
    response_model=PhoneNoteResponse,
    summary="Follow-up abschliessen",
    description="Markiert ein Follow-up als abgeschlossen.",
)
async def complete_follow_up(
    entity_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> PhoneNoteResponse:
    """Markiert ein Follow-up als abgeschlossen."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    service = CommunicationHubService(db)
    note = await service.update_phone_note(
        note_id=note_id,
        company_id=company_id,  # SECURITY FIX
        follow_up_completed=True,
    )

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Telefon-Notiz nicht gefunden"
        )

    return PhoneNoteResponse(**note.to_dict())


# =============================================================================
# Quick Actions
# =============================================================================

@router.get(
    "/{entity_id}/communication-hub/quick-stats",
    summary="Schnelle Kommunikations-Statistiken",
    description="Holt nur die wichtigsten Statistiken fuer schnelle Anzeige.",
)
async def get_quick_stats(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> Dict[str, Any]:
    """Holt schnelle Statistiken fuer Badge-Anzeigen etc."""
    # SECURITY FIX: Multi-Tenant Check
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    service = CommunicationHubService(db)

    # Nur Stats und Tasks laden
    hub_data = await service.get_communication_hub(
        entity_id=entity_id,
        company_id=company_id,  # SECURITY FIX
        include_sections=["stats", "tasks", "invoices"],
    )

    return {
        "total_phone_calls": hub_data.communication_stats.get("total_phone_calls", 0),
        "open_follow_ups": hub_data.communication_stats.get("open_follow_ups", 0),
        "total_documents": hub_data.communication_stats.get("total_documents", 0),
        "open_invoices": hub_data.invoice_summary.open_invoices,
        "overdue_invoices": hub_data.invoice_summary.overdue_invoices,
        "overdue_tasks": len([t for t in hub_data.open_tasks if t.get("is_overdue")]),
    }


@router.get(
    "/{entity_id}/communication-hub/timeline",
    response_model=List[TimelineItemResponse],
    summary="Nur Timeline abrufen",
    description="Holt nur die Timeline ohne andere Sektionen.",
)
async def get_timeline_only(
    entity_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    type_filter: Optional[str] = Query(
        default=None,
        description="Komma-getrennte Liste der Typen (phone_call,email,document,invoice,dunning,comment)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> List[TimelineItemResponse]:
    """Holt nur die Timeline."""
    # SECURITY FIX (P0): Multi-Tenant Check - CWE-639
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma ausgewaehlt. Bitte waehlen Sie eine Firma aus.",
        )

    service = CommunicationHubService(db)

    hub_data = await service.get_communication_hub(
        entity_id=entity_id,
        company_id=company_id,  # SECURITY FIX: Use validated company_id
        timeline_limit=limit,
        include_sections=["timeline"],
    )

    # Optional: Nach Typ filtern
    timeline = hub_data.timeline
    if type_filter:
        allowed_types = [t.strip() for t in type_filter.split(",")]
        timeline = [item for item in timeline if item.type in allowed_types]

    return [
        TimelineItemResponse(
            id=str(item.id),
            timestamp=item.timestamp,
            type=item.type,
            title=item.title,
            description=item.description,
            icon=item.icon,
            color=item.color,
            direction=item.direction,
            sentiment=item.sentiment,
            actor_name=item.actor_name,
            metadata=item.metadata,
        )
        for item in timeline
    ]
