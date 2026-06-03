"""
Kommentar-Thread API Endpoints.

Erweiterte Kommentar-Funktionen für Google-Docs-Style Collaboration:
- Thread-Management (Erstellen, Aufloesen, Wieder öffnen)
- PDF-Anker (Positionierung von Kommentaren auf PDF-Seiten)
- Änderungsvorschläge (Vorschläge für Feldwerte mit Annahme/Ablehnung)

Feinpoliert und durchdacht - Enterprise Collaboration.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User, Document, DocumentComment
from app.db.models_comments import (
    CommentAnchor,
    CommentThread,
    CommentSuggestion,
    CommentAnchorType,
    SuggestionStatus,
    ThreadStatus,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/comment-threads", tags=["Kommentar-Threads"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class ThreadCreateRequest(BaseModel):
    """Schema für das Erstellen eines Threads."""
    document_id: UUID = Field(..., description="Dokument-ID")
    root_comment_id: UUID = Field(..., description="Root-Kommentar-ID")
    subject: Optional[str] = Field(None, max_length=255, description="Thread-Betreff")


class ThreadResponse(BaseModel):
    """Schema für die Thread-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    company_id: UUID
    subject: Optional[str]
    root_comment_id: UUID
    status: str
    reply_count: int
    resolved_at: Optional[datetime]
    resolved_by_id: Optional[UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class AnchorCreateRequest(BaseModel):
    """Schema für das Erstellen eines PDF-Ankers."""
    comment_id: UUID = Field(..., description="Kommentar-ID")
    page_number: int = Field(..., ge=1, description="PDF-Seitennummer (1-basiert)")
    x: float = Field(..., ge=0.0, le=1.0, description="X-Position (normalisiert 0-1)")
    y: float = Field(..., ge=0.0, le=1.0, description="Y-Position (normalisiert 0-1)")
    width: Optional[float] = Field(None, ge=0.0, le=1.0, description="Breite (normalisiert)")
    height: Optional[float] = Field(None, ge=0.0, le=1.0, description="Höhe (normalisiert)")
    anchor_type: str = Field(default="pin", description="Anker-Typ (pin/highlight/rectangle/freeform/field)")
    highlighted_text: Optional[str] = Field(None, description="Markierter Text")
    color: str = Field(default="#FBBF24", max_length=7, description="Farbe (Hex-Format)")


class AnchorResponse(BaseModel):
    """Schema für die Anker-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    comment_id: UUID
    page_number: int
    x: float
    y: float
    width: Optional[float]
    height: Optional[float]
    anchor_type: str
    highlighted_text: Optional[str]
    color: str


class SuggestionCreateRequest(BaseModel):
    """Schema für das Erstellen eines Änderungsvorschlags."""
    comment_id: UUID = Field(..., description="Kommentar-ID")
    document_id: UUID = Field(..., description="Dokument-ID")
    field_name: Optional[str] = Field(None, max_length=100, description="Betroffenes Extraktionsfeld")
    original_value: Optional[str] = Field(None, description="Aktueller Wert")
    suggested_value: str = Field(..., description="Vorgeschlagener neuer Wert")
    reason: Optional[str] = Field(None, description="Begruendung für die Änderung")


class SuggestionDecisionRequest(BaseModel):
    """Schema für die Entscheidung über einen Vorschlag."""
    decision_comment: Optional[str] = Field(None, description="Kommentar zur Entscheidung")


class SuggestionResponse(BaseModel):
    """Schema für die Vorschlags-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    comment_id: UUID
    document_id: UUID
    field_name: Optional[str]
    original_value: Optional[str]
    suggested_value: str
    reason: Optional[str]
    status: str
    decided_at: Optional[datetime]
    decided_by_id: Optional[UUID]
    decision_comment: Optional[str]
    created_at: Optional[datetime]
    created_by_id: Optional[UUID]


# ============================================================================
# Thread Endpoints
# ============================================================================


@router.post(
    "/",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Thread erstellen",
    description="Erstellt einen neuen Kommentar-Thread aus einem bestehenden Root-Kommentar",
)
async def create_thread(
    data: ThreadCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ThreadResponse:
    """Erstellt einen neuen Kommentar-Thread."""
    # Dokument prüfen
    result = await db.execute(
        select(Document).where(Document.id == data.document_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    if document.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Dokument",
        )

    # Root-Kommentar prüfen
    result = await db.execute(
        select(DocumentComment).where(
            and_(
                DocumentComment.id == data.root_comment_id,
                DocumentComment.document_id == data.document_id,
            )
        )
    )
    root_comment = result.scalar_one_or_none()
    if not root_comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Root-Kommentar nicht gefunden",
        )

    thread = CommentThread(
        document_id=data.document_id,
        company_id=company_id,
        root_comment_id=data.root_comment_id,
        subject=data.subject,
        status=ThreadStatus.OFFEN.value,
        created_by_id=current_user.id,
    )
    db.add(thread)
    await db.flush()
    await db.refresh(thread)

    logger.info("comment_thread_created", thread_id=str(thread.id), document_id=str(data.document_id))
    return ThreadResponse.model_validate(thread)


@router.get(
    "/document/{document_id}",
    response_model=List[ThreadResponse],
    summary="Alle Threads eines Dokuments",
    description="Ruft alle Kommentar-Threads eines Dokuments ab",
)
async def get_document_threads(
    document_id: UUID,
    status_filter: Optional[str] = Query(None, description="Status-Filter (offen/geloest/geschlossen)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[ThreadResponse]:
    """Ruft alle Threads eines Dokuments ab."""
    conditions = [
        CommentThread.document_id == document_id,
        CommentThread.company_id == company_id,
    ]
    if status_filter:
        conditions.append(CommentThread.status == status_filter)

    result = await db.execute(
        select(CommentThread)
        .where(and_(*conditions))
        .order_by(CommentThread.created_at.desc())
    )
    threads = result.scalars().all()
    return [ThreadResponse.model_validate(t) for t in threads]


@router.put(
    "/{thread_id}/resolve",
    response_model=ThreadResponse,
    summary="Thread als geloest markieren",
)
async def resolve_thread(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ThreadResponse:
    """Markiert einen Thread als geloest."""
    result = await db.execute(
        select(CommentThread).where(
            and_(CommentThread.id == thread_id, CommentThread.company_id == company_id)
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread nicht gefunden")

    thread.status = ThreadStatus.GELOEST.value
    thread.resolved_at = datetime.now(timezone.utc)
    thread.resolved_by_id = current_user.id
    await db.flush()
    await db.refresh(thread)

    logger.info("comment_thread_resolved", thread_id=str(thread_id))
    return ThreadResponse.model_validate(thread)


@router.put(
    "/{thread_id}/reopen",
    response_model=ThreadResponse,
    summary="Thread wieder öffnen",
)
async def reopen_thread(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ThreadResponse:
    """Öffnet einen Thread wieder."""
    result = await db.execute(
        select(CommentThread).where(
            and_(CommentThread.id == thread_id, CommentThread.company_id == company_id)
        )
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread nicht gefunden")

    thread.status = ThreadStatus.OFFEN.value
    thread.resolved_at = None
    thread.resolved_by_id = None
    await db.flush()
    await db.refresh(thread)

    logger.info("comment_thread_reopened", thread_id=str(thread_id))
    return ThreadResponse.model_validate(thread)


# ============================================================================
# Anchor Endpoints
# ============================================================================


@router.post(
    "/anchors",
    response_model=AnchorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="PDF-Anker setzen",
    description="Setzt einen PDF-Anker für einen Kommentar",
)
async def create_anchor(
    data: AnchorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AnchorResponse:
    """Setzt einen PDF-Anker für einen Kommentar."""
    # Prüfen ob Kommentar existiert
    result = await db.execute(
        select(DocumentComment).where(DocumentComment.id == data.comment_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Kommentar nicht gefunden")

    # Prüfen ob bereits ein Anker existiert
    result = await db.execute(
        select(CommentAnchor).where(CommentAnchor.comment_id == data.comment_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kommentar hat bereits einen Anker",
        )

    anchor = CommentAnchor(
        comment_id=data.comment_id,
        page_number=data.page_number,
        x=data.x,
        y=data.y,
        width=data.width,
        height=data.height,
        anchor_type=data.anchor_type,
        highlighted_text=data.highlighted_text,
        color=data.color,
    )
    db.add(anchor)
    await db.flush()
    await db.refresh(anchor)

    return AnchorResponse.model_validate(anchor)


@router.get(
    "/anchors/comment/{comment_id}",
    response_model=AnchorResponse,
    summary="Anker eines Kommentars abrufen",
)
async def get_anchor(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AnchorResponse:
    """Ruft den Anker eines Kommentars ab."""
    result = await db.execute(
        select(CommentAnchor).where(CommentAnchor.comment_id == comment_id)
    )
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Kein Anker gefunden")

    return AnchorResponse.model_validate(anchor)


# ============================================================================
# Suggestion Endpoints
# ============================================================================


@router.post(
    "/suggestions",
    response_model=SuggestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Änderungsvorschlag erstellen",
    description="Erstellt einen Änderungsvorschlag für ein Dokumentfeld",
)
async def create_suggestion(
    data: SuggestionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SuggestionResponse:
    """Erstellt einen Änderungsvorschlag."""
    # Dokument prüfen
    result = await db.execute(
        select(Document).where(
            and_(Document.id == data.document_id, Document.company_id == company_id)
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden oder keine Berechtigung")

    suggestion = CommentSuggestion(
        comment_id=data.comment_id,
        document_id=data.document_id,
        field_name=data.field_name,
        original_value=data.original_value,
        suggested_value=data.suggested_value,
        reason=data.reason,
        status=SuggestionStatus.OFFEN.value,
        created_by_id=current_user.id,
    )
    db.add(suggestion)
    await db.flush()
    await db.refresh(suggestion)

    logger.info("comment_suggestion_created", suggestion_id=str(suggestion.id))
    return SuggestionResponse.model_validate(suggestion)


@router.get(
    "/suggestions/document/{document_id}",
    response_model=List[SuggestionResponse],
    summary="Alle Vorschläge eines Dokuments",
)
async def get_document_suggestions(
    document_id: UUID,
    status_filter: Optional[str] = Query(None, description="Status-Filter (offen/angenommen/abgelehnt)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[SuggestionResponse]:
    """Ruft alle Vorschläge eines Dokuments ab."""
    conditions = [CommentSuggestion.document_id == document_id]
    if status_filter:
        conditions.append(CommentSuggestion.status == status_filter)

    result = await db.execute(
        select(CommentSuggestion)
        .where(and_(*conditions))
        .order_by(CommentSuggestion.created_at.desc())
    )
    suggestions = result.scalars().all()
    return [SuggestionResponse.model_validate(s) for s in suggestions]


@router.put(
    "/suggestions/{suggestion_id}/accept",
    response_model=SuggestionResponse,
    summary="Vorschlag annehmen",
)
async def accept_suggestion(
    suggestion_id: UUID,
    data: Optional[SuggestionDecisionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SuggestionResponse:
    """Nimmt einen Vorschlag an."""
    result = await db.execute(
        select(CommentSuggestion).where(CommentSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Vorschlag nicht gefunden")

    if suggestion.status != SuggestionStatus.OFFEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorschlag wurde bereits bearbeitet",
        )

    suggestion.status = SuggestionStatus.ANGENOMMEN.value
    suggestion.decided_at = datetime.now(timezone.utc)
    suggestion.decided_by_id = current_user.id
    if data and data.decision_comment:
        suggestion.decision_comment = data.decision_comment

    await db.flush()
    await db.refresh(suggestion)

    logger.info("comment_suggestion_accepted", suggestion_id=str(suggestion_id))
    return SuggestionResponse.model_validate(suggestion)


@router.put(
    "/suggestions/{suggestion_id}/reject",
    response_model=SuggestionResponse,
    summary="Vorschlag ablehnen",
)
async def reject_suggestion(
    suggestion_id: UUID,
    data: Optional[SuggestionDecisionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SuggestionResponse:
    """Lehnt einen Vorschlag ab."""
    result = await db.execute(
        select(CommentSuggestion).where(CommentSuggestion.id == suggestion_id)
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Vorschlag nicht gefunden")

    if suggestion.status != SuggestionStatus.OFFEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorschlag wurde bereits bearbeitet",
        )

    suggestion.status = SuggestionStatus.ABGELEHNT.value
    suggestion.decided_at = datetime.now(timezone.utc)
    suggestion.decided_by_id = current_user.id
    if data and data.decision_comment:
        suggestion.decision_comment = data.decision_comment

    await db.flush()
    await db.refresh(suggestion)

    logger.info("comment_suggestion_rejected", suggestion_id=str(suggestion_id))
    return SuggestionResponse.model_validate(suggestion)
