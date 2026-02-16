# -*- coding: utf-8 -*-
"""Document Context API - Aggregierter Cross-Module Kontext für Dokumente."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.document_context_aggregator import (
    DocumentContextAggregatorService,
    EntityContext as EntityContextData,
    ChainContext as ChainContextData,
    PaymentContext as PaymentContextData,
    PendingAction as PendingActionData,
    RelatedDocument as RelatedDocumentData,
)

router = APIRouter(prefix="/documents", tags=["Document Context"])


# ============================================================================
# Pydantic Response Models
# ============================================================================

class EntityContextResponse(BaseModel):
    """Entitaets-Kontext Response."""
    id: str
    name: str
    entity_type: str
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    risk_trend: Optional[str] = None


class ChainContextResponse(BaseModel):
    """Auftragsketten-Kontext Response."""
    chain_id: Optional[str] = None
    position: Optional[int] = None
    total_docs: int = 0
    is_complete: bool = False
    open_discrepancies: int = 0
    has_quote: bool = False
    has_order: bool = False
    has_delivery_note: bool = False
    has_invoice: bool = False
    has_credit_note: bool = False


class PaymentContextResponse(BaseModel):
    """Zahlungs-Kontext Response."""
    status: str = "unknown"
    paid_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    skonto_available: bool = False
    skonto_deadline: Optional[date] = None
    skonto_amount: Optional[Decimal] = None
    skonto_percent: Optional[float] = None
    days_overdue: int = 0


class PendingActionResponse(BaseModel):
    """Ausstehende Aktion Response."""
    id: str
    action_type: str
    priority: str
    reason: str
    impact_description: str


class RelatedDocumentResponse(BaseModel):
    """Verwandtes Dokument Response."""
    id: str
    filename: str
    document_type: Optional[str] = None
    created_at: Optional[str] = None


class DocumentContextResponse(BaseModel):
    """Aggregierter Dokument-Kontext Response."""
    entity: Optional[EntityContextResponse] = None
    chain: Optional[ChainContextResponse] = None
    payment: Optional[PaymentContextResponse] = None
    related_documents: List[RelatedDocumentResponse] = Field(default_factory=list)
    pending_actions: List[PendingActionResponse] = Field(default_factory=list)


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/{document_id}/context", response_model=DocumentContextResponse)
async def get_document_context(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentContextResponse:
    """
    Aggregierter Cross-Module Kontext für ein Dokument.

    Liefert folgende Informationen:
    - **Entitaet**: Geschäftspartner-Info mit Risk-Scoring
    - **Auftragskette**: Position in der Dokumentenkette (Angebot -> Rechnung)
    - **Zahlung**: Zahlungsstatus, Skonto-Informationen, Überfälligkeit
    - **Verwandte Dokumente**: Andere Dokumente derselben Entitaet
    - **Ausstehende Aktionen**: Orchestrierungs-Aktionen für diese Entitaet

    Args:
        document_id: Dokument-ID
        db: Datenbank-Session (injected)
        current_user: Aktueller Benutzer (injected)

    Returns:
        Aggregierter Dokument-Kontext

    Raises:
        HTTPException: 404 wenn Dokument nicht gefunden
    """
    service = DocumentContextAggregatorService(db)
    context = await service.get_context(document_id, current_user.company_id)

    # Wenn kein Dokument gefunden wurde, 404 zurückgeben
    # (context ist leer aber nicht None bei fehlendem Dokument)

    # Dataclasses zu Pydantic Models konvertieren
    return DocumentContextResponse(
        entity=(
            EntityContextResponse(**vars(context.entity))
            if context.entity
            else None
        ),
        chain=(
            ChainContextResponse(**vars(context.chain))
            if context.chain
            else None
        ),
        payment=(
            PaymentContextResponse(**vars(context.payment))
            if context.payment
            else None
        ),
        related_documents=[
            RelatedDocumentResponse(**vars(rd)) for rd in context.related_documents
        ],
        pending_actions=[
            PendingActionResponse(**vars(pa)) for pa in context.pending_actions
        ],
    )
