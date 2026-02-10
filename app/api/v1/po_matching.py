# -*- coding: utf-8 -*-
"""
PO-Matching API Endpoints.

REST API fuer 3-Way Purchase Order Matching:
- Bestellung <-> Lieferschein <-> Rechnung
- Automatisches Matching und Abweichungserkennung
- Freigabe-Workflow
- Statistiken

Phase 2.2 der Feature-Roadmap (Februar 2026).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_po_matching import (
    MatchStatus,
    DiscrepancyCategory,
    DiscrepancySeverity,
)
from app.api.dependencies import get_db, get_current_active_user
from app.services.finance.po_matching_service import (
    get_po_matching_service,
    MatchCreateRequest,
    MatchFilter,
    AddDocumentRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/po-matching", tags=["PO-Matching"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class MatchCreateSchema(BaseModel):
    """Schema fuer Match-Erstellung."""
    purchase_order_id: Optional[UUID] = Field(None, description="Bestellungs-Dokument-ID")
    delivery_note_id: Optional[UUID] = Field(None, description="Lieferschein-Dokument-ID")
    invoice_id: Optional[UUID] = Field(None, description="Rechnungs-Dokument-ID")
    document_chain_id: Optional[str] = Field(None, max_length=100, description="Dokumentenketten-ID (z.B. CHAIN-2026-00001)")
    vendor_entity_id: Optional[UUID] = Field(None, description="Lieferanten-Entity-ID")
    vendor_name: Optional[str] = Field(None, max_length=255, description="Lieferantenname")
    order_number: Optional[str] = Field(None, max_length=100, description="Bestellnummer")
    order_date: Optional[datetime] = Field(None, description="Bestelldatum")
    po_amount: Optional[float] = Field(None, ge=0, description="Bestellbetrag")
    dn_amount: Optional[float] = Field(None, ge=0, description="Lieferscheinbetrag")
    invoice_amount: Optional[float] = Field(None, ge=0, description="Rechnungsbetrag")
    amount_tolerance_percent: float = Field(default=2.0, ge=0, le=100, description="Betrags-Toleranz in %")
    quantity_tolerance_percent: float = Field(default=1.0, ge=0, le=100, description="Mengen-Toleranz in %")


class AddDocumentSchema(BaseModel):
    """Schema zum Hinzufuegen eines Dokuments."""
    document_id: UUID = Field(..., description="Dokument-ID")
    document_type: str = Field(
        ...,
        description="Dokumenttyp: purchase_order, delivery_note, invoice"
    )
    amount: Optional[float] = Field(None, ge=0, description="Betrag des Dokuments")


class ApproveMatchSchema(BaseModel):
    """Schema fuer Match-Freigabe."""
    notes: Optional[str] = Field(None, max_length=2000, description="Freigabe-Notizen")


class DiscrepancyResponse(BaseModel):
    """Response-Schema fuer Abweichung."""
    id: UUID
    match_id: UUID
    category: DiscrepancyCategory
    description: str
    field_name: str
    expected_value: Optional[str]
    actual_value: Optional[str]
    expected_amount: Optional[float]
    actual_amount: Optional[float]
    deviation_percent: Optional[float]
    severity: DiscrepancySeverity
    resolved: bool
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MatchResponse(BaseModel):
    """Response-Schema fuer PO-Match."""
    id: UUID
    company_id: UUID
    purchase_order_id: Optional[UUID]
    delivery_note_id: Optional[UUID]
    invoice_id: Optional[UUID]
    document_chain_id: Optional[str]
    vendor_entity_id: Optional[UUID]
    vendor_name: Optional[str]
    order_number: Optional[str]
    order_date: Optional[datetime]
    po_amount: Optional[float]
    dn_amount: Optional[float]
    invoice_amount: Optional[float]
    match_status: MatchStatus
    match_score: float
    auto_matched: bool
    amount_tolerance_percent: float
    quantity_tolerance_percent: float
    approved_by_id: Optional[UUID]
    approved_at: Optional[datetime]
    approval_notes: Optional[str]
    document_count: int
    is_complete: bool
    created_at: datetime
    updated_at: datetime
    matched_at: Optional[datetime]

    class Config:
        from_attributes = True


class MatchDetailResponse(MatchResponse):
    """Response-Schema fuer Match mit Abweichungen."""
    discrepancies: List[DiscrepancyResponse] = Field(default_factory=list)


class MatchListResponse(BaseModel):
    """Paginierte Match-Liste."""
    items: List[MatchResponse]
    total: int
    page: int
    page_size: int


class MatchStatisticsResponse(BaseModel):
    """Statistik-Response."""
    total_matches: int
    pending_matches: int
    partial_matches: int
    full_matches: int
    discrepancy_matches: int
    approved_matches: int
    rejected_matches: int
    auto_matched_count: int
    avg_match_score: float
    total_discrepancies: int
    unresolved_discrepancies: int
    avg_amount_deviation_percent: float
    period_start: date
    period_end: date


class UnmatchedDocumentResponse(BaseModel):
    """Response fuer ungematchtes Dokument."""
    id: UUID
    filename: Optional[str]
    document_type: Optional[str]
    chain_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AutoMatchResponse(BaseModel):
    """Response fuer Auto-Matching."""
    matches_updated: int
    matches: List[MatchResponse]


class MessageResponse(BaseModel):
    """Einfache Nachricht-Response."""
    message: str


# ============================================================================
# Helper Functions
# ============================================================================


def _match_to_response(match: "PurchaseOrderMatch") -> MatchResponse:
    """Konvertiert PurchaseOrderMatch zu MatchResponse."""
    return MatchResponse(
        id=match.id,
        company_id=match.company_id,
        purchase_order_id=match.purchase_order_id,
        delivery_note_id=match.delivery_note_id,
        invoice_id=match.invoice_id,
        document_chain_id=match.document_chain_id,
        vendor_entity_id=match.vendor_entity_id,
        vendor_name=match.vendor_name,
        order_number=match.order_number,
        order_date=match.order_date,
        po_amount=float(match.po_amount) if match.po_amount is not None else None,
        dn_amount=float(match.dn_amount) if match.dn_amount is not None else None,
        invoice_amount=float(match.invoice_amount) if match.invoice_amount is not None else None,
        match_status=match.match_status,
        match_score=match.match_score or 0.0,
        auto_matched=match.auto_matched or False,
        amount_tolerance_percent=match.amount_tolerance_percent or 2.0,
        quantity_tolerance_percent=match.quantity_tolerance_percent or 1.0,
        approved_by_id=match.approved_by_id,
        approved_at=match.approved_at,
        approval_notes=match.approval_notes,
        document_count=match.document_count,
        is_complete=match.is_complete,
        created_at=match.created_at,
        updated_at=match.updated_at,
        matched_at=match.matched_at,
    )


def _match_to_detail_response(match: "PurchaseOrderMatch") -> MatchDetailResponse:
    """Konvertiert PurchaseOrderMatch zu MatchDetailResponse mit Abweichungen."""
    discrepancies = []
    for d in (match.discrepancies or []):
        discrepancies.append(DiscrepancyResponse(
            id=d.id,
            match_id=d.match_id,
            category=d.category,
            description=d.description,
            field_name=d.field_name,
            expected_value=d.expected_value,
            actual_value=d.actual_value,
            expected_amount=float(d.expected_amount) if d.expected_amount is not None else None,
            actual_amount=float(d.actual_amount) if d.actual_amount is not None else None,
            deviation_percent=d.deviation_percent,
            severity=d.severity,
            resolved=d.resolved or False,
            resolved_at=d.resolved_at,
            resolution_notes=d.resolution_notes,
            created_at=d.created_at,
        ))

    base = _match_to_response(match)
    return MatchDetailResponse(
        **base.model_dump(),
        discrepancies=discrepancies,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=MatchListResponse,
    summary="Matches auflisten",
    description="Listet alle PO-Matches mit Filtern und Paginierung"
)
async def list_matches(
    status: Optional[MatchStatus] = Query(None, description="Status-Filter"),
    vendor_entity_id: Optional[UUID] = Query(None, description="Lieferanten-Filter"),
    date_from: Optional[date] = Query(None, description="Ab Datum"),
    date_to: Optional[date] = Query(None, description="Bis Datum"),
    order_number: Optional[str] = Query(None, description="Bestellnummer-Suche"),
    page: int = Query(0, ge=0, description="Seite (0-basiert)"),
    page_size: int = Query(25, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchListResponse:
    """Listet alle PO-Matches."""
    service = get_po_matching_service()

    matches, total = await service.list_matches(
        db,
        MatchFilter(
            company_id=current_user.company_id,
            status=status,
            vendor_entity_id=vendor_entity_id,
            date_from=date_from,
            date_to=date_to,
            order_number=order_number,
        ),
        page=page,
        page_size=page_size,
    )

    items = [_match_to_response(m) for m in matches]
    return MatchListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/unmatched",
    response_model=List[UnmatchedDocumentResponse],
    summary="Ungematchte Dokumente",
    description="Findet Dokumente ohne PO-Match"
)
async def get_unmatched_documents(
    document_type: Optional[str] = Query(
        None,
        description="Dokumenttyp: purchase_order, delivery_note, invoice"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[UnmatchedDocumentResponse]:
    """Listet ungematchte Dokumente."""
    service = get_po_matching_service()

    documents = await service.get_unmatched_documents(
        db,
        company_id=current_user.company_id,
        document_type=document_type,
    )

    return [
        UnmatchedDocumentResponse(
            id=doc.id,
            filename=getattr(doc, "filename", None),
            document_type=getattr(doc, "document_type", None),
            chain_id=getattr(doc, "chain_id", None),
            created_at=doc.created_at,
        )
        for doc in documents
    ]


@router.get(
    "/statistics",
    response_model=MatchStatisticsResponse,
    summary="Matching-Statistiken",
    description="Berechnet Matching-Statistiken fuer einen Zeitraum"
)
async def get_matching_statistics(
    period_start: date = Query(..., description="Zeitraum-Start"),
    period_end: date = Query(..., description="Zeitraum-Ende"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchStatisticsResponse:
    """Gibt Matching-Statistiken zurueck."""
    service = get_po_matching_service()

    try:
        stats = await service.get_matching_statistics(
            db,
            company_id=current_user.company_id,
            period_start=period_start,
            period_end=period_end,
        )

        return MatchStatisticsResponse(
            total_matches=stats.total_matches,
            pending_matches=stats.pending_matches,
            partial_matches=stats.partial_matches,
            full_matches=stats.full_matches,
            discrepancy_matches=stats.discrepancy_matches,
            approved_matches=stats.approved_matches,
            rejected_matches=stats.rejected_matches,
            auto_matched_count=stats.auto_matched_count,
            avg_match_score=stats.avg_match_score,
            total_discrepancies=stats.total_discrepancies,
            unresolved_discrepancies=stats.unresolved_discrepancies,
            avg_amount_deviation_percent=stats.avg_amount_deviation_percent,
            period_start=stats.period_start,
            period_end=stats.period_end,
        )

    except Exception as e:
        logger.exception("matching_statistics_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Berechnen der Statistiken")


@router.get(
    "/{match_id}",
    response_model=MatchDetailResponse,
    summary="Match-Detail abrufen",
    description="Ruft einen Match mit allen Abweichungen ab"
)
async def get_match_detail(
    match_id: UUID = Path(..., description="Match-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchDetailResponse:
    """Ruft einen Match mit Abweichungen ab."""
    service = get_po_matching_service()

    match = await service.get_match_detail(db, match_id)

    if not match:
        raise HTTPException(status_code=404, detail="Match nicht gefunden")

    if match.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Match")

    return _match_to_detail_response(match)


@router.post(
    "",
    response_model=MatchResponse,
    status_code=201,
    summary="Match erstellen",
    description="Erstellt einen neuen 3-Way Match"
)
async def create_match(
    data: MatchCreateSchema,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Erstellt einen neuen Match."""
    service = get_po_matching_service()

    try:
        match = await service.create_match(
            db,
            MatchCreateRequest(
                company_id=current_user.company_id,
                purchase_order_id=data.purchase_order_id,
                delivery_note_id=data.delivery_note_id,
                invoice_id=data.invoice_id,
                document_chain_id=data.document_chain_id,
                vendor_entity_id=data.vendor_entity_id,
                vendor_name=data.vendor_name,
                order_number=data.order_number,
                order_date=data.order_date,
                po_amount=Decimal(str(data.po_amount)) if data.po_amount is not None else None,
                dn_amount=Decimal(str(data.dn_amount)) if data.dn_amount is not None else None,
                invoice_amount=Decimal(str(data.invoice_amount)) if data.invoice_amount is not None else None,
                amount_tolerance_percent=data.amount_tolerance_percent,
                quantity_tolerance_percent=data.quantity_tolerance_percent,
            )
        )

        return _match_to_response(match)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Match-Erstellung"))
    except Exception as e:
        logger.exception("match_create_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Erstellen des Matches")


@router.post(
    "/auto-detect",
    response_model=AutoMatchResponse,
    summary="Auto-Matching ausfuehren",
    description="Fuehrt automatisches Matching nach Bestellnummer und Lieferant aus"
)
async def auto_detect_matches(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AutoMatchResponse:
    """Fuehrt Auto-Matching aus."""
    service = get_po_matching_service()

    try:
        updated_matches = await service.auto_match_by_reference(
            db,
            company_id=current_user.company_id,
        )

        return AutoMatchResponse(
            matches_updated=len(updated_matches),
            matches=[_match_to_response(m) for m in updated_matches],
        )

    except Exception as e:
        logger.exception("auto_match_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Auto-Matching")


@router.post(
    "/{match_id}/add-document",
    response_model=MatchResponse,
    summary="Dokument hinzufuegen",
    description="Fuegt ein Dokument zu einem bestehenden Match hinzu"
)
async def add_document_to_match(
    data: AddDocumentSchema,
    match_id: UUID = Path(..., description="Match-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Fuegt ein Dokument zu einem Match hinzu."""
    service = get_po_matching_service()

    try:
        match = await service.add_document_to_match(
            db,
            match_id,
            AddDocumentRequest(
                document_id=data.document_id,
                document_type=data.document_type,
                amount=Decimal(str(data.amount)) if data.amount is not None else None,
            ),
        )

        return _match_to_response(match)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Dokument-Verknuepfung"))
    except Exception as e:
        logger.exception("add_document_to_match_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler beim Hinzufuegen des Dokuments")


@router.post(
    "/{match_id}/evaluate",
    response_model=MatchDetailResponse,
    summary="Match bewerten",
    description="Bewertet einen Match und erkennt Abweichungen"
)
async def evaluate_match(
    match_id: UUID = Path(..., description="Match-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchDetailResponse:
    """Bewertet einen Match."""
    service = get_po_matching_service()

    try:
        match = await service.evaluate_match(db, match_id)
        return _match_to_detail_response(match)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Match-Bewertung"))
    except Exception as e:
        logger.exception("evaluate_match_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Match-Bewertung")


@router.post(
    "/{match_id}/approve",
    response_model=MatchResponse,
    summary="Match freigeben",
    description="Gibt einen Match frei (auch bei Abweichungen)"
)
async def approve_match(
    data: ApproveMatchSchema,
    match_id: UUID = Path(..., description="Match-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Gibt einen Match frei."""
    service = get_po_matching_service()

    try:
        match = await service.approve_match(
            db,
            match_id,
            user_id=current_user.id,
            notes=data.notes,
        )

        return _match_to_response(match)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Match-Freigabe"))
    except Exception as e:
        logger.exception("approve_match_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Fehler bei der Match-Freigabe")
