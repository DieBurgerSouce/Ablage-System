"""
Collaboration API Endpoints.

Echtzeit-Kollaborationsfunktionen:
- Document Locking
- @Mentions
- Activity Feed
- Presence
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.collaboration_service import (
    ActivityAction,
    ActivityEntry,
    CollaborationService,
    DocumentLock,
    LockType,
    Mention,
    get_collaboration_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


# =========================================================================
# PYDANTIC SCHEMAS
# =========================================================================


class DocumentLockResponse(BaseModel):
    """Document Lock Response."""

    document_id: str
    locked_by: str
    locked_by_name: str
    locked_at: datetime
    lock_type: str
    expires_at: datetime


class MentionResponse(BaseModel):
    """Mention Response."""

    id: str
    document_id: str
    mentioned_user_id: str
    mentioned_by_id: str
    context: str
    read: bool
    created_at: datetime


class MentionCreate(BaseModel):
    """Mention Create Request."""

    mentioned_user_id: str = Field(..., description="ID des erwähnten Benutzers")
    context: str = Field(..., max_length=500, description="Kontext-Text")


class ActivityEntryResponse(BaseModel):
    """Activity Entry Response."""

    id: str
    document_id: Optional[str]
    user_id: str
    user_name: str
    action: str
    details: str
    created_at: datetime


class ViewerInfo(BaseModel):
    """Document Viewer Info."""

    user_id: str
    status: str
    connected_at: str


# =========================================================================
# DOCUMENT LOCKING ENDPOINTS
# =========================================================================


@router.post(
    "/documents/{document_id}/lock",
    response_model=DocumentLockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokument sperren",
    description="Sperrt ein Dokument für die Bearbeitung (30 Minuten)",
)
async def lock_document(
    document_id: uuid.UUID,
    lock_type: LockType = Query(LockType.EDIT, description="Art der Sperre"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> DocumentLockResponse:
    """Sperrt ein Dokument für einen Benutzer."""
    try:
        lock = await service.acquire_lock(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
            lock_type=lock_type,
        )

        return DocumentLockResponse(
            document_id=str(lock.document_id),
            locked_by=str(lock.locked_by),
            locked_by_name=lock.locked_by_name,
            locked_at=lock.locked_at,
            lock_type=lock.lock_type.value,
            expires_at=lock.expires_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_detail(str(e)),
        )
    except Exception as e:
        logger.error("lock_document_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Dokument konnte nicht gesperrt werden"),
        )


@router.delete(
    "/documents/{document_id}/lock",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sperre aufheben",
    description="Gibt eine Dokumentsperre frei",
    response_class=Response,
)
async def unlock_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> Response:
    """Gibt eine Dokumentsperre frei."""
    try:
        released = await service.release_lock(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
        )

        if not released:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=safe_error_detail("Keine Sperre gefunden"),
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(str(e)),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("unlock_document_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Sperre konnte nicht aufgehoben werden"),
        )


@router.get(
    "/documents/{document_id}/lock",
    response_model=Optional[DocumentLockResponse],
    summary="Lock-Status prüfen",
    description="Prüft ob ein Dokument gesperrt ist",
)
async def get_document_lock(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> Optional[DocumentLockResponse]:
    """Prüft Lock-Status eines Dokuments."""
    try:
        lock = await service.check_lock(db=db, document_id=document_id)

        if not lock:
            return None

        return DocumentLockResponse(
            document_id=str(lock.document_id),
            locked_by=str(lock.locked_by),
            locked_by_name=lock.locked_by_name,
            locked_at=lock.locked_at,
            lock_type=lock.lock_type.value,
            expires_at=lock.expires_at,
        )

    except Exception as e:
        logger.error("get_document_lock_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Lock-Status konnte nicht abgerufen werden"),
        )


@router.put(
    "/documents/{document_id}/lock/refresh",
    response_model=DocumentLockResponse,
    summary="Lock verlängern",
    description="Verlängert die Gültigkeit eines Locks um weitere 30 Minuten",
)
async def refresh_document_lock(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> DocumentLockResponse:
    """Verlängert die Gültigkeit eines Locks."""
    try:
        lock = await service.refresh_lock(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
        )

        return DocumentLockResponse(
            document_id=str(lock.document_id),
            locked_by=str(lock.locked_by),
            locked_by_name=lock.locked_by_name,
            locked_at=lock.locked_at,
            lock_type=lock.lock_type.value,
            expires_at=lock.expires_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(str(e)),
        )
    except Exception as e:
        logger.error("refresh_document_lock_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Lock konnte nicht verlängert werden"),
        )


# =========================================================================
# MENTIONS ENDPOINTS
# =========================================================================


@router.get(
    "/mentions",
    response_model=List[MentionResponse],
    summary="Mentions abrufen",
    description="Holt alle oder ungelesene @Mentions für den aktuellen Benutzer",
)
async def get_mentions(
    unread_only: bool = Query(False, description="Nur ungelesene Mentions"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> List[MentionResponse]:
    """Holt Mentions für den aktuellen Benutzer."""
    try:
        if unread_only:
            mentions = await service.get_unread_mentions(
                db=db,
                user_id=current_user.id,
                company_id=current_user.company_id,
            )
        else:
            mentions = await service.get_all_mentions(
                db=db,
                user_id=current_user.id,
                company_id=current_user.company_id,
            )

        return [
            MentionResponse(
                id=str(m.id),
                document_id=str(m.document_id),
                mentioned_user_id=str(m.mentioned_user_id),
                mentioned_by_id=str(m.mentioned_by_id),
                context=m.context,
                read=m.read,
                created_at=m.created_at,
            )
            for m in mentions
        ]

    except Exception as e:
        logger.error("get_mentions_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Mentions konnten nicht abgerufen werden"),
        )


@router.post(
    "/documents/{document_id}/mentions",
    response_model=MentionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mention erstellen",
    description="Erstellt eine @Mention für einen Benutzer",
)
async def create_mention(
    document_id: uuid.UUID,
    request: MentionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> MentionResponse:
    """Erstellt eine neue @Mention."""
    try:
        mention = await service.create_mention(
            db=db,
            document_id=document_id,
            mentioned_user_id=uuid.UUID(request.mentioned_user_id),
            mentioned_by_id=current_user.id,
            context=request.context,
            company_id=current_user.company_id,
        )

        return MentionResponse(
            id=str(mention.id),
            document_id=str(mention.document_id),
            mentioned_user_id=str(mention.mentioned_user_id),
            mentioned_by_id=str(mention.mentioned_by_id),
            context=mention.context,
            read=mention.read,
            created_at=mention.created_at,
        )

    except Exception as e:
        logger.error("create_mention_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Mention konnte nicht erstellt werden"),
        )


@router.patch(
    "/mentions/{mention_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mention als gelesen markieren",
    description="Markiert eine @Mention als gelesen",
    response_class=Response,
)
async def mark_mention_read(
    mention_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> Response:
    """Markiert eine Mention als gelesen."""
    try:
        success = await service.mark_mention_read(
            db=db,
            mention_id=mention_id,
            user_id=current_user.id,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=safe_error_detail("Mention nicht gefunden"),
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("mark_mention_read_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Mention konnte nicht aktualisiert werden"),
        )


# =========================================================================
# ACTIVITY FEED ENDPOINTS
# =========================================================================


@router.get(
    "/documents/{document_id}/activity",
    response_model=List[ActivityEntryResponse],
    summary="Dokument-Aktivitäten",
    description="Holt Activity Feed für ein Dokument",
)
async def get_document_activity(
    document_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100, description="Maximale Anzahl Einträge"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> List[ActivityEntryResponse]:
    """Holt Activity Feed für ein Dokument."""
    try:
        activities = await service.get_document_activity(
            db=db,
            document_id=document_id,
            limit=limit,
        )

        return [
            ActivityEntryResponse(
                id=str(a.id),
                document_id=str(a.document_id) if a.document_id else None,
                user_id=str(a.user_id),
                user_name=a.user_name,
                action=a.action.value,
                details=a.details,
                created_at=a.created_at,
            )
            for a in activities
        ]

    except Exception as e:
        logger.error("get_document_activity_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Aktivitäten konnten nicht abgerufen werden"),
        )


@router.get(
    "/activity/feed",
    response_model=List[ActivityEntryResponse],
    summary="Activity Feed",
    description="Holt persönlichen Activity Feed",
)
async def get_activity_feed(
    limit: int = Query(50, ge=1, le=100, description="Maximale Anzahl Einträge"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> List[ActivityEntryResponse]:
    """Holt persönlichen Activity Feed."""
    try:
        activities = await service.get_user_activity_feed(
            db=db,
            user_id=current_user.id,
            company_id=current_user.company_id,
            limit=limit,
        )

        return [
            ActivityEntryResponse(
                id=str(a.id),
                document_id=str(a.document_id) if a.document_id else None,
                user_id=str(a.user_id),
                user_name=a.user_name,
                action=a.action.value,
                details=a.details,
                created_at=a.created_at,
            )
            for a in activities
        ]

    except Exception as e:
        logger.error("get_activity_feed_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Activity Feed konnte nicht abgerufen werden"),
        )


# =========================================================================
# PRESENCE ENDPOINTS
# =========================================================================


@router.get(
    "/documents/{document_id}/presence",
    response_model=List[ViewerInfo],
    summary="Dokument-Betrachter",
    description="Holt Liste aller Benutzer die ein Dokument gerade betrachten",
)
async def get_document_presence(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: CollaborationService = Depends(get_collaboration_service),
) -> List[ViewerInfo]:
    """Holt Liste der aktuellen Dokument-Betrachter."""
    try:
        viewers = await service.get_document_viewers(document_id=document_id)

        return [
            ViewerInfo(
                user_id=v["user_id"],
                status=v["status"],
                connected_at=v["connected_at"],
            )
            for v in viewers
        ]

    except Exception as e:
        logger.error("get_document_presence_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail("Presence-Informationen konnten nicht abgerufen werden"),
        )
