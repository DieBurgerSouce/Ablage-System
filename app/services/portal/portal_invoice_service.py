"""
Portal-Rechnungsservice.

Read-Only Zugriff auf Rechnungen fuer Kunden.
"""

from datetime import datetime, timezone, date
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import Document, DocumentType, InvoiceTracking, Entity
from app.db.models_portal import PortalUser

logger = structlog.get_logger(__name__)


class PortalInvoiceService:
    """
    Service fuer Rechnungsansicht im Kundenportal.

    Nur lesender Zugriff - keine Modifikationen.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_invoices_for_entity(
        self,
        entity_id: UUID,
        company_id: UUID,
        status: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        Hole alle Rechnungen fuer einen Entity (Kunden/Lieferanten).

        Returns:
            Tuple aus Liste von Rechnungsdaten und Gesamtanzahl.
        """
        # Basis-Query
        query = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
            .options(selectinload(InvoiceTracking.document))
        )

        # Filter
        if status:
            query = query.where(InvoiceTracking.status == status)
        if from_date:
            query = query.where(InvoiceTracking.invoice_date >= from_date)
        if to_date:
            query = query.where(InvoiceTracking.invoice_date <= to_date)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sortierung und Paginierung
        query = query.order_by(InvoiceTracking.invoice_date.desc())
        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        invoices = result.scalars().all()

        # Konvertiere zu Portal-Ansicht (nur relevante Felder)
        invoice_list = []
        for inv in invoices:
            invoice_list.append({
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "gross_amount": float(inv.gross_amount) if inv.gross_amount else None,
                "net_amount": float(inv.net_amount) if inv.net_amount else None,
                "currency": inv.currency or "EUR",
                "status": inv.status,
                "dunning_level": inv.dunning_level or 0,
                "paid_amount": float(inv.paid_amount) if inv.paid_amount else 0.0,
                "outstanding_amount": float(inv.outstanding_amount) if inv.outstanding_amount else float(inv.gross_amount or 0),
                "is_overdue": inv.due_date and inv.due_date < date.today() and inv.status != "paid",
                "skonto_applicable": bool(
                    inv.skonto_deadline and
                    inv.skonto_deadline >= date.today() and
                    inv.status != "paid"
                ),
                "skonto_deadline": inv.skonto_deadline.isoformat() if inv.skonto_deadline else None,
                "skonto_percentage": float(inv.skonto_percentage) if inv.skonto_percentage else None,
                "skonto_amount": float(inv.skonto_amount) if inv.skonto_amount else None,
                "has_document": inv.document_id is not None,
                "document_id": str(inv.document_id) if inv.document_id else None,
            })

        return invoice_list, total

    async def get_invoice_detail(
        self,
        invoice_id: UUID,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[dict]:
        """
        Hole Details einer einzelnen Rechnung.
        """
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.id == invoice_id,
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
            .options(selectinload(InvoiceTracking.document))
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            return None

        # Zahlungshistorie
        payments = invoice.partial_payments or []

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "gross_amount": float(invoice.gross_amount) if invoice.gross_amount else None,
            "net_amount": float(invoice.net_amount) if invoice.net_amount else None,
            "vat_amount": float(invoice.vat_amount) if invoice.vat_amount else None,
            "currency": invoice.currency or "EUR",
            "status": invoice.status,
            "dunning_level": invoice.dunning_level or 0,
            "paid_amount": float(invoice.paid_amount) if invoice.paid_amount else 0.0,
            "outstanding_amount": float(invoice.outstanding_amount) if invoice.outstanding_amount else float(invoice.gross_amount or 0),
            "is_overdue": invoice.due_date and invoice.due_date < date.today() and invoice.status != "paid",
            # Skonto-Informationen
            "skonto_applicable": bool(
                invoice.skonto_deadline and
                invoice.skonto_deadline >= date.today() and
                invoice.status != "paid"
            ),
            "skonto_deadline": invoice.skonto_deadline.isoformat() if invoice.skonto_deadline else None,
            "skonto_percentage": float(invoice.skonto_percentage) if invoice.skonto_percentage else None,
            "skonto_amount": float(invoice.skonto_amount) if invoice.skonto_amount else None,
            # Zahlungshistorie
            "payments": payments,
            # Dokument
            "has_document": invoice.document_id is not None,
            "document_id": str(invoice.document_id) if invoice.document_id else None,
            # Zeiten
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "last_updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        }

    async def get_invoice_summary(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> dict:
        """
        Hole Zusammenfassung aller Rechnungen fuer Dashboard.
        """
        # Alle Rechnungen fuer Entity
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        invoices = result.scalars().all()

        total_count = len(invoices)
        open_count = 0
        overdue_count = 0
        total_outstanding = Decimal("0")
        total_overdue = Decimal("0")
        skonto_available = 0
        skonto_savings_possible = Decimal("0")

        today = date.today()

        for inv in invoices:
            if inv.status not in ("paid", "cancelled"):
                open_count += 1
                outstanding = inv.outstanding_amount or inv.gross_amount or Decimal("0")
                total_outstanding += outstanding

                if inv.due_date and inv.due_date < today:
                    overdue_count += 1
                    total_overdue += outstanding

                # Skonto
                if inv.skonto_deadline and inv.skonto_deadline >= today and inv.skonto_amount:
                    skonto_available += 1
                    skonto_savings_possible += inv.skonto_amount

        return {
            "total_invoices": total_count,
            "open_invoices": open_count,
            "overdue_invoices": overdue_count,
            "total_outstanding": float(total_outstanding),
            "total_overdue": float(total_overdue),
            "skonto_available_count": skonto_available,
            "skonto_savings_possible": float(skonto_savings_possible),
            "currency": "EUR",
        }

    async def get_open_invoices(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> List[dict]:
        """
        Hole nur offene Rechnungen.
        """
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.notin_(["paid", "cancelled"]),
                )
            )
            .order_by(InvoiceTracking.due_date.asc())
        )
        invoices = result.scalars().all()

        return [
            {
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "outstanding_amount": float(inv.outstanding_amount or inv.gross_amount or 0),
                "currency": inv.currency or "EUR",
                "is_overdue": inv.due_date and inv.due_date < date.today(),
                "days_until_due": (inv.due_date - date.today()).days if inv.due_date else None,
            }
            for inv in invoices
        ]


def get_portal_invoice_service(db: AsyncSession) -> PortalInvoiceService:
    """Factory-Funktion fuer PortalInvoiceService."""
    return PortalInvoiceService(db)
