"""
Portal-Zahlungsservice.

Kunden koennen Zahlungsbestaetigungen einreichen.
"""

from datetime import datetime, timezone, date
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from app.db.models import InvoiceTracking
from app.db.models_portal import (
    PortalPaymentConfirmation, PortalUser
)

logger = structlog.get_logger(__name__)


class PortalPaymentService:
    """
    Service fuer Zahlungsbestaetigungen im Kundenportal.

    Kunden koennen mitteilen, dass sie bezahlt haben.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_payment_confirmation(
        self,
        portal_user: PortalUser,
        invoice_tracking_id: UUID,
        payment_date: datetime,
        payment_amount: str,
        payment_reference: Optional[str] = None,
        payment_method: Optional[str] = None,
        attachment_ids: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> PortalPaymentConfirmation:
        """
        Reiche eine Zahlungsbestaetigung ein.
        """
        # Validiere dass Rechnung existiert und zum Entity gehoert
        result = await self.db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.id == invoice_tracking_id,
                    InvoiceTracking.entity_id == portal_user.entity_id,
                    InvoiceTracking.company_id == portal_user.company_id,
                )
            )
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise ValueError("Rechnung nicht gefunden oder kein Zugriff")

        if invoice.status == "paid":
            raise ValueError("Rechnung ist bereits als bezahlt markiert")

        # Erstelle Zahlungsbestaetigung
        confirmation = PortalPaymentConfirmation(
            company_id=portal_user.company_id,
            entity_id=portal_user.entity_id,
            portal_user_id=portal_user.id,
            invoice_tracking_id=invoice_tracking_id,
            payment_date=payment_date,
            payment_amount=payment_amount,
            payment_reference=payment_reference,
            payment_method=payment_method,
            attachment_ids=attachment_ids or [],
            notes=notes,
            status="pending",
        )

        self.db.add(confirmation)
        await self.db.commit()
        await self.db.refresh(confirmation)

        logger.info(
            "portal_payment_confirmation_submitted",
            confirmation_id=str(confirmation.id),
            invoice_id=str(invoice_tracking_id),
            entity_id=str(portal_user.entity_id),
        )

        return confirmation

    async def get_payment_confirmations(
        self,
        entity_id: UUID,
        company_id: UUID,
        status: Optional[str] = None,
        invoice_tracking_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole alle Zahlungsbestaetigungen fuer einen Entity.
        """
        query = select(PortalPaymentConfirmation).where(
            and_(
                PortalPaymentConfirmation.entity_id == entity_id,
                PortalPaymentConfirmation.company_id == company_id,
            )
        )

        if status:
            query = query.where(PortalPaymentConfirmation.status == status)
        if invoice_tracking_id:
            query = query.where(PortalPaymentConfirmation.invoice_tracking_id == invoice_tracking_id)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(PortalPaymentConfirmation.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        confirmations = result.scalars().all()

        confirmation_list = []
        for conf in confirmations:
            confirmation_list.append({
                "id": str(conf.id),
                "invoice_tracking_id": str(conf.invoice_tracking_id),
                "payment_date": conf.payment_date.isoformat() if conf.payment_date else None,
                "payment_amount": conf.payment_amount,
                "payment_reference": conf.payment_reference,
                "payment_method": conf.payment_method,
                "status": conf.status,
                "verified_at": conf.verified_at.isoformat() if conf.verified_at else None,
                "rejection_reason": conf.rejection_reason,
                "created_at": conf.created_at.isoformat() if conf.created_at else None,
            })

        return confirmation_list, total

    async def get_payment_confirmation_detail(
        self,
        confirmation_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """
        Hole Details einer Zahlungsbestaetigung.
        """
        result = await self.db.execute(
            select(PortalPaymentConfirmation).where(
                and_(
                    PortalPaymentConfirmation.id == confirmation_id,
                    PortalPaymentConfirmation.entity_id == entity_id,
                    PortalPaymentConfirmation.company_id == company_id,
                )
            )
        )
        conf = result.scalar_one_or_none()

        if not conf:
            return None

        # Lade Rechnungsdetails
        invoice_result = await self.db.execute(
            select(InvoiceTracking).where(
                InvoiceTracking.id == conf.invoice_tracking_id
            )
        )
        invoice = invoice_result.scalar_one_or_none()

        return {
            "id": str(conf.id),
            "invoice_tracking_id": str(conf.invoice_tracking_id),
            "invoice_number": invoice.invoice_number if invoice else None,
            "invoice_gross_amount": float(invoice.gross_amount) if invoice and invoice.gross_amount else None,
            "payment_date": conf.payment_date.isoformat() if conf.payment_date else None,
            "payment_amount": conf.payment_amount,
            "payment_reference": conf.payment_reference,
            "payment_method": conf.payment_method,
            "attachment_ids": conf.attachment_ids,
            "status": conf.status,
            "verified_at": conf.verified_at.isoformat() if conf.verified_at else None,
            "rejection_reason": conf.rejection_reason,
            "notes": conf.notes,
            "created_at": conf.created_at.isoformat() if conf.created_at else None,
        }

    async def cancel_payment_confirmation(
        self,
        confirmation_id: UUID,
        portal_user: PortalUser,
    ) -> bool:
        """
        Storniere eine ausstehende Zahlungsbestaetigung.

        Nur moeglich wenn Status noch "pending".
        """
        result = await self.db.execute(
            select(PortalPaymentConfirmation).where(
                and_(
                    PortalPaymentConfirmation.id == confirmation_id,
                    PortalPaymentConfirmation.entity_id == portal_user.entity_id,
                    PortalPaymentConfirmation.company_id == portal_user.company_id,
                    PortalPaymentConfirmation.status == "pending",
                )
            )
        )
        confirmation = result.scalar_one_or_none()

        if not confirmation:
            return False

        # Storniere (markiere als abgelehnt mit Grund)
        confirmation.status = "cancelled"
        confirmation.rejection_reason = "Vom Kunden storniert"

        await self.db.commit()

        logger.info(
            "portal_payment_confirmation_cancelled",
            confirmation_id=str(confirmation_id),
        )

        return True


def get_portal_payment_service(db: AsyncSession) -> PortalPaymentService:
    """Factory-Funktion fuer PortalPaymentService."""
    return PortalPaymentService(db)
