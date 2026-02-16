# -*- coding: utf-8 -*-
"""
Presence API Endpoints.

Echtzeit-Praesenz-Tracking für Dokumente:
- GET /presence/{document_id} - Wer betrachtet dieses Dokument
- POST /presence/{document_id}/join - Dokument betreten
- POST /presence/{document_id}/leave - Dokument verlassen
- POST /presence/{document_id}/heartbeat - Heartbeat (alle 30s)
- PATCH /presence/{document_id}/editing - Bearbeitungsstatus setzen

Feinpoliert und durchdacht - Collaborative Presence.
"""

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.collaboration.presence_service import (
    PresenceService,
    get_presence_service,
)
from app.services.realtime import get_realtime_ws_manager
from app.services.realtime.realtime_websocket_manager import WSMessage

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/presence", tags=["Präsenz"])


# =============================================================================
# Request/Response Models
# =============================================================================


class EditingRequest(BaseModel):
    """Request-Model für Editing-Status."""
    is_editing: bool


class PresenceEntryResponse(BaseModel):
    """Response-Model für einen Praesenz-Eintrag."""
    user_id: str
    user_name: str
    joined_at: str
    last_heartbeat: str
    is_editing: bool
    avatar_color: str


class PresenceResponse(BaseModel):
    """Response-Model für Dokument-Praesenz."""
    document_id: str
    viewers: List[PresenceEntryResponse]
    viewer_count: int
    editor_count: int


# =============================================================================
# Helper
# =============================================================================


async def _broadcast_presence_event(
    document_id: UUID,
    event_type: str,
    user_id: UUID,
    user_name: str,
    is_editing: bool = False,
) -> None:
    """Broadcast presence event to document viewers via WebSocket."""
    try:
        ws_manager = get_realtime_ws_manager()
        await ws_manager.broadcast_to_room(
            room_id=f"doc:{document_id}",
            message=WSMessage(
                type=event_type,
                payload={
                    "document_id": str(document_id),
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "is_editing": is_editing,
                },
            ),
        )
    except Exception as e:
        # Non-critical: log and continue
        logger.warning(
            "presence_broadcast_failed",
            event_type=event_type,
            document_id=str(document_id),
            **safe_error_log(e),
        )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/{document_id}",
    response_model=PresenceResponse,
    summary="Dokument-Praesenz abrufen",
    description="Gibt alle Benutzer zurück die dieses Dokument gerade betrachten.",
)
async def get_document_presence(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> PresenceResponse:
    """Ruft aktuelle Praesenz für ein Dokument ab."""
    try:
        service = get_presence_service()
        entries = await service.get_presence(document_id)

        viewers = [
            PresenceEntryResponse(
                user_id=e.user_id,
                user_name=e.user_name,
                joined_at=e.joined_at,
                last_heartbeat=e.last_heartbeat,
                is_editing=e.is_editing,
                avatar_color=e.avatar_color,
            )
            for e in entries
        ]

        return PresenceResponse(
            document_id=str(document_id),
            viewers=viewers,
            viewer_count=len(viewers),
            editor_count=sum(1 for v in viewers if v.is_editing),
        )

    except Exception as e:
        logger.error(
            "presence_get_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen der Praesenz"),
        )


@router.post(
    "/{document_id}/join",
    response_model=PresenceResponse,
    summary="Dokument betreten",
    description="Registriert den aktuellen Benutzer als Betrachter des Dokuments.",
)
async def join_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> PresenceResponse:
    """Registriert Benutzer als Dokument-Betrachter."""
    try:
        service = get_presence_service()
        user_name = current_user.full_name or current_user.email or str(current_user.id)

        entries = await service.join_document(
            document_id=document_id,
            user_id=current_user.id,
            user_name=user_name,
        )

        # Broadcast join event
        await _broadcast_presence_event(
            document_id=document_id,
            event_type="presence_joined",
            user_id=current_user.id,
            user_name=user_name,
        )

        viewers = [
            PresenceEntryResponse(
                user_id=e.user_id,
                user_name=e.user_name,
                joined_at=e.joined_at,
                last_heartbeat=e.last_heartbeat,
                is_editing=e.is_editing,
                avatar_color=e.avatar_color,
            )
            for e in entries
        ]

        logger.info(
            "presence_join_success",
            document_id=str(document_id),
            user_id=str(current_user.id),
            viewer_count=len(viewers),
        )

        return PresenceResponse(
            document_id=str(document_id),
            viewers=viewers,
            viewer_count=len(viewers),
            editor_count=sum(1 for v in viewers if v.is_editing),
        )

    except Exception as e:
        logger.error(
            "presence_join_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Betreten des Dokuments"),
        )


@router.post(
    "/{document_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dokument verlassen",
    description="Entfernt den aktuellen Benutzer als Betrachter des Dokuments.",
)
async def leave_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Entfernt Benutzer als Dokument-Betrachter."""
    try:
        service = get_presence_service()
        user_name = current_user.full_name or current_user.email or str(current_user.id)

        await service.leave_document(
            document_id=document_id,
            user_id=current_user.id,
        )

        # Broadcast leave event
        await _broadcast_presence_event(
            document_id=document_id,
            event_type="presence_left",
            user_id=current_user.id,
            user_name=user_name,
        )

    except Exception as e:
        logger.error(
            "presence_leave_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Verlassen des Dokuments"),
        )


@router.post(
    "/{document_id}/heartbeat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Heartbeat senden",
    description="Heartbeat zum Aufrechterhalten der Praesenz. Sollte alle 30 Sekunden gesendet werden.",
)
async def heartbeat(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Heartbeat für Praesenz-Aufrechterhaltung."""
    try:
        service = get_presence_service()
        await service.heartbeat(
            document_id=document_id,
            user_id=current_user.id,
        )
    except Exception as e:
        logger.error(
            "presence_heartbeat_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Heartbeat fehlgeschlagen"),
        )


@router.patch(
    "/{document_id}/editing",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Bearbeitungsstatus setzen",
    description="Setzt den Bearbeitungsstatus des aktuellen Benutzers auf dem Dokument.",
)
async def set_editing_state(
    document_id: UUID,
    request: EditingRequest,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Setzt Bearbeitungsstatus für Benutzer auf Dokument."""
    try:
        service = get_presence_service()
        user_name = current_user.full_name or current_user.email or str(current_user.id)

        await service.set_editing(
            document_id=document_id,
            user_id=current_user.id,
            is_editing=request.is_editing,
        )

        # Broadcast editing state change
        await _broadcast_presence_event(
            document_id=document_id,
            event_type="presence_editing",
            user_id=current_user.id,
            user_name=user_name,
            is_editing=request.is_editing,
        )

    except Exception as e:
        logger.error(
            "presence_set_editing_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Setzen des Bearbeitungsstatus"),
        )
