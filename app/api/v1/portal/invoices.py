"""
Portal Invoices API.

Rechnungsansicht fuer Kundenportal.
"""

from datetime import date
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.api.v1.portal.auth import get_current_portal_user
from app.services.portal import get_portal_invoice_service
from app.db.models_portal import PortalUser

router = APIRouter(prefix="/invoices", tags=["Portal-Rechnungen"])


# === Pydantic Models ===

class PortalInvoiceListResponse(BaseModel):
    """Rechnungsliste-Antwort."""
    items: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class PortalInvoiceItemsResponse(BaseModel):
    """Rechnungen-Items-Antwort."""
    items: List[Dict[str, Any]]


class PortalInvoiceSummaryResponse(BaseModel):
    """Rechnungs-Zusammenfassung-Antwort."""
    total_count: int
    open_count: int
    overdue_count: int
    total_outstanding: float
    total_overdue: float
    skonto_available_count: int
    skonto_savings_possible: float
    currency: str


@router.get("", response_model=PortalInvoiceListResponse)
async def list_invoices(
    status: Optional[str] = Query(None, description="Filter nach Status"),
    from_date: Optional[date] = Query(None, description="Ab Datum"),
    to_date: Optional[date] = Query(None, description="Bis Datum"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste alle Rechnungen fuer den Kunden.
    """
    if not portal_user.can_view_invoices:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer Rechnungsansicht",
        )

    service = get_portal_invoice_service(db)

    invoices, total = await service.get_invoices_for_entity(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )

    return PortalInvoiceListResponse(
        items=invoices,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=PortalInvoiceSummaryResponse)
async def get_invoice_summary(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Rechnungs-Zusammenfassung fuer Dashboard.
    """
    if not portal_user.can_view_invoices:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer Rechnungsansicht",
        )

    service = get_portal_invoice_service(db)

    summary = await service.get_invoice_summary(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    return PortalInvoiceSummaryResponse(**summary)


@router.get("/open", response_model=PortalInvoiceItemsResponse)
async def get_open_invoices(
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole offene Rechnungen.
    """
    if not portal_user.can_view_invoices:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer Rechnungsansicht",
        )

    service = get_portal_invoice_service(db)

    invoices = await service.get_open_invoices(
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    return PortalInvoiceItemsResponse(items=invoices)


@router.get("/{invoice_id}")
async def get_invoice_detail(
    invoice_id: UUID,
    portal_user: PortalUser = Depends(get_current_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hole Details einer Rechnung.
    """
    if not portal_user.can_view_invoices:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer Rechnungsansicht",
        )

    service = get_portal_invoice_service(db)

    invoice = await service.get_invoice_detail(
        invoice_id=invoice_id,
        entity_id=portal_user.entity_id,
        company_id=portal_user.company_id,
    )

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail="Rechnung nicht gefunden",
        )

    return invoice
