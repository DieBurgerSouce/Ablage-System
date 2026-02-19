"""
Portal Complaints API.

Reklamationen für Kundenportal.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.safe_errors import safe_error_detail
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.api.v1.portal.auth import get_current_portal_user
from app.services.portal import get_portal_complaint_service, PortalComplaintService
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/complaints", tags=["Portal-Reklamationen"])


class ComplaintCreateRequest(BaseModel):
    """Reklamations-Erstellungs-Anfrage."""
    complaint_type: str
    subject: str = Field(..., max_length=255)
    description: str
    document_id: Optional[UUID] = None
    invoice_tracking_id: Optional[UUID] = None
    priority: str = "normal"
    metadata: Optional[dict] = None


class ComplaintAddInfoRequest(BaseModel):
    """Zusätzliche Information hinzufuegen."""
    additional_info: str
    attachment_ids: Optional[List[str]] = None


@router.get("/types")
async def get_complaint_types():
    """
    Hole verfügbare Reklamationstypen.
    """
    return {
        "types": PortalComplaintService.get_complaint_types(),
    }


@router.post("")
async def create_complaint(
    data: ComplaintCreateRequest,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Erstelle eine neue Reklamation.
    """
    if not portal_user.can_submit_complaints:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für Reklamationen",
        )

    service = get_portal_complaint_service(db)

    try:
        complaint = await service.submit_complaint(
            portal_user=portal_user,
            complaint_type=data.complaint_type,
            subject=data.subject,
            description=data.description,
            document_id=data.document_id,
            invoice_tracking_id=data.invoice_tracking_id,
            priority=data.priority,
            metadata=data.metadata,
        )

        return {
            "success": True,
            "complaint_id": str(complaint.id),
            "reference_number": complaint.reference_number,
            "message": "Reklamation erfolgreich eingereicht",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=safe_error_detail(e, "Reklamation"),
        )


@router.get("")
async def list_complaints(
    status: Optional[str] = Query(None),
    complaint_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste alle Reklamationen.
    """
    service = get_portal_complaint_service(db)

    complaints, total = await service.get_complaints(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        status=status,
        complaint_type=complaint_type,
        limit=limit,
        offset=offset,
    )

    return {
        "items": complaints,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary")
async def get_complaint_summary(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Reklamations-Zusammenfassung.
    """
    service = get_portal_complaint_service(db)

    return await service.get_complaint_summary(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )


@router.get("/{complaint_id}")
async def get_complaint_detail(
    complaint_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Details einer Reklamation.
    """
    service = get_portal_complaint_service(db)

    detail = await service.get_complaint_detail(
        complaint_id=complaint_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not detail:
        raise HTTPException(
            status_code=404,
            detail="Reklamation nicht gefunden",
        )

    return detail


@router.post("/{complaint_id}/info")
async def add_complaint_info(
    complaint_id: UUID,
    data: ComplaintAddInfoRequest,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fuege zusätzliche Informationen zu einer Reklamation hinzu.
    """
    if not portal_user.can_submit_complaints:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für Reklamationen",
        )

    service = get_portal_complaint_service(db)

    success = await service.add_information(
        complaint_id=complaint_id,
        portal_user=portal_user,
        additional_info=data.additional_info,
        attachment_ids=data.attachment_ids,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Information konnte nicht hinzugefuegt werden (Reklamation nicht gefunden oder bereits abgeschlossen)",
        )

    return {
        "success": True,
        "message": "Information hinzugefuegt",
    }
