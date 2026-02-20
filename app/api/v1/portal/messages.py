"""
Portal Messages API.

Kommunikation zwischen Kunden und Unternehmen.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.api.v1.portal.auth import get_current_portal_user
from app.services.portal import get_portal_communication_service
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/messages", tags=["Portal-Nachrichten"])


class MessageSendRequest(BaseModel):
    """Nachricht senden."""
    content: str = Field(..., min_length=1, max_length=10000)
    subject: Optional[str] = Field(None, max_length=255)
    complaint_id: Optional[UUID] = None
    attachments: Optional[List[str]] = None


@router.post("")
async def send_message(
    data: MessageSendRequest,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sende eine Nachricht an das Unternehmen.
    """
    service = get_portal_communication_service(db)

    message = await service.send_message(
        portal_user=portal_user,
        content=data.content,
        subject=data.subject,
        complaint_id=data.complaint_id,
        attachments=data.attachments,
    )

    return {
        "success": True,
        "message_id": str(message.id),
        "message": "Nachricht erfolgreich gesendet",
    }


@router.get("")
async def list_messages(
    complaint_id: Optional[UUID] = Query(None),
    direction: Optional[str] = Query(None, description="inbound oder outbound"),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=100, description="Eintraege pro Seite"),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste alle Nachrichten.
    """
    service = get_portal_communication_service(db)

    messages, total = await service.get_messages(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        complaint_id=complaint_id,
        direction=direction,
        unread_only=unread_only,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return {
        "items": messages,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/conversation")
async def get_conversation(
    complaint_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Konversation in chronologischer Reihenfolge.
    """
    service = get_portal_communication_service(db)

    messages = await service.get_conversation(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        complaint_id=complaint_id,
        limit=limit,
    )

    return {"messages": messages}


@router.get("/summary")
async def get_message_summary(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Nachrichten-Zusammenfassung.
    """
    service = get_portal_communication_service(db)

    return await service.get_communication_summary(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )


@router.get("/unread-count")
async def get_unread_count(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Anzahl ungelesener Nachrichten.
    """
    service = get_portal_communication_service(db)

    count = await service.get_unread_count(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    return {"unread_count": count}


@router.post("/{message_id}/read")
async def mark_message_as_read(
    message_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Markiere eine Nachricht als gelesen.
    """
    service = get_portal_communication_service(db)

    success = await service.mark_as_read(
        message_id=message_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Nachricht nicht gefunden",
        )

    return {"success": True}


@router.post("/mark-all-read")
async def mark_all_messages_as_read(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Markiere alle Nachrichten als gelesen.
    """
    service = get_portal_communication_service(db)

    count = await service.mark_all_as_read(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    return {
        "success": True,
        "marked_count": count,
    }
