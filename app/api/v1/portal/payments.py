"""
Portal Payments API.

Zahlungsbestaetigungen fuer Kundenportal.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.api.v1.portal.auth import get_current_portal_user
from app.services.portal import get_portal_payment_service
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/payments", tags=["Portal-Zahlungen"])


class PaymentConfirmationRequest(BaseModel):
    """Zahlungsbestaetigungs-Anfrage."""
    invoice_tracking_id: UUID
    payment_date: datetime
    payment_amount: str
    payment_reference: Optional[str] = None
    payment_method: Optional[str] = None
    attachment_ids: Optional[List[str]] = None
    notes: Optional[str] = None


@router.post("/confirm")
async def submit_payment_confirmation(
    data: PaymentConfirmationRequest,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reiche eine Zahlungsbestaetigung ein.
    """
    if not portal_user.can_confirm_payments:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer Zahlungsbestaetigungen",
        )

    service = get_portal_payment_service(db)

    try:
        confirmation = await service.submit_payment_confirmation(
            portal_user=portal_user,
            invoice_tracking_id=data.invoice_tracking_id,
            payment_date=data.payment_date,
            payment_amount=data.payment_amount,
            payment_reference=data.payment_reference,
            payment_method=data.payment_method,
            attachment_ids=data.attachment_ids,
            notes=data.notes,
        )

        return {
            "success": True,
            "confirmation_id": str(confirmation.id),
            "message": "Zahlungsbestaetigung erfolgreich eingereicht",
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get("/confirmations")
async def list_payment_confirmations(
    status: Optional[str] = Query(None),
    invoice_tracking_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste alle Zahlungsbestaetigungen.
    """
    service = get_portal_payment_service(db)

    confirmations, total = await service.get_payment_confirmations(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        status=status,
        invoice_tracking_id=invoice_tracking_id,
        limit=limit,
        offset=offset,
    )

    return {
        "items": confirmations,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/confirmations/{confirmation_id}")
async def get_payment_confirmation_detail(
    confirmation_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Details einer Zahlungsbestaetigung.
    """
    service = get_portal_payment_service(db)

    detail = await service.get_payment_confirmation_detail(
        confirmation_id=confirmation_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not detail:
        raise HTTPException(
            status_code=404,
            detail="Zahlungsbestaetigung nicht gefunden",
        )

    return detail


@router.delete("/confirmations/{confirmation_id}")
async def cancel_payment_confirmation(
    confirmation_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Storniere eine ausstehende Zahlungsbestaetigung.
    """
    service = get_portal_payment_service(db)

    success = await service.cancel_payment_confirmation(
        confirmation_id=confirmation_id,
        portal_user=portal_user,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Stornierung nicht moeglich (nicht gefunden oder bereits bearbeitet)",
        )

    return {
        "success": True,
        "message": "Zahlungsbestaetigung storniert",
    }
