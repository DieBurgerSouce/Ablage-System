# -*- coding: utf-8 -*-
"""Partial Payment Service.

Verwaltet Teilzahlungen für Rechnungen:
- Erfassung von Teilzahlungen
- Berechnung ausstehender Betraege
- Automatische Status-Updates (partial -> paid)
- Integration mit Dunning/Mahnwesen
- Bank-Reconciliation Support
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


@dataclass
class PaymentTransactionCreate:
    """Daten für neue Teilzahlung."""
    amount: Decimal
    transaction_date: Optional[datetime] = None
    payment_reference: Optional[str] = None
    payment_method: str = "bank_transfer"
    bank_transaction_id: Optional[UUID] = None
    skonto_deducted: Optional[Decimal] = None
    notes: Optional[str] = None


@dataclass
class PaymentTransactionResponse:
    """Response für Teilzahlung."""
    id: UUID
    invoice_tracking_id: UUID
    amount: Decimal
    transaction_date: datetime
    payment_reference: Optional[str]
    payment_method: str
    skonto_deducted: Optional[Decimal]
    reconciliation_status: str
    created_at: datetime


@dataclass
class InvoicePaymentSummary:
    """Zusammenfassung der Zahlungen für eine Rechnung."""
    invoice_tracking_id: UUID
    invoice_number: Optional[str]
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    skonto_total: Decimal
    payment_count: int
    payments: List[PaymentTransactionResponse]
    is_fully_paid: bool
    overpaid_amount: Decimal  # Falls mehr gezahlt als geschuldet


class PartialPaymentService:
    """Service für Teilzahlungs-Management.

    Features:
    - Mehrere Zahlungen pro Rechnung
    - Automatische Berechnung des ausstehenden Betrags
    - Status-Update wenn vollständig bezahlt
    - Skonto-Integration
    - Bank-Reconciliation Support
    """

    # Toleranz für "vollständig bezahlt" (Rundungsdifferenzen)
    PAYMENT_TOLERANCE = Decimal("0.05")  # 5 Cent

    async def record_payment(
        self,
        db: AsyncSession,
        invoice_tracking_id: UUID,
        payment_data: PaymentTransactionCreate,
        user_id: UUID,
        company_id: UUID,
    ) -> Tuple[PaymentTransactionResponse, str]:
        """Erfasse eine Teilzahlung.

        Args:
            db: Datenbank-Session
            invoice_tracking_id: ID des Invoice-Trackings
            payment_data: Zahlungsdaten
            user_id: Benutzer-ID
            company_id: Firmen-ID

        Returns:
            Tuple: (PaymentTransactionResponse, Statusmeldung)
        """
        from app.db.models import InvoiceTracking, PaymentTransaction

        # Invoice laden - SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.id == invoice_tracking_id,
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            logger.warning(
                "record_payment_failed",
                invoice_id=str(invoice_tracking_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            raise ValueError("Rechnung nicht gefunden")

        if invoice.status == "cancelled":
            raise ValueError("Rechnung wurde storniert - keine Zahlung möglich")

        # Validierung: Betrag positiv
        if payment_data.amount <= Decimal("0"):
            raise ValueError("Zahlungsbetrag muss positiv sein")

        # Berechne aktuellen Stand - SECURITY: company_id durchreichen
        current_paid = await self._get_total_paid(db, invoice_tracking_id, company_id)
        total_amount = Decimal(str(invoice.amount))
        outstanding = total_amount - current_paid

        # Warnung bei Überzahlung
        message = ""
        if payment_data.amount > outstanding + self.PAYMENT_TOLERANCE:
            overpaid = payment_data.amount - outstanding
            message = f"Hinweis: Überzahlung von {overpaid}EUR"
            logger.warning(
                "Überzahlung erfasst",
                invoice_id=str(invoice_tracking_id),
                amount=str(payment_data.amount),
                outstanding=str(outstanding),
            )

        # Transaktion erstellen
        transaction = PaymentTransaction(
            id=uuid4(),
            invoice_tracking_id=invoice_tracking_id,
            transaction_date=payment_data.transaction_date or utc_now(),
            amount=float(payment_data.amount),
            payment_reference=payment_data.payment_reference,
            payment_method=payment_data.payment_method,
            bank_transaction_id=payment_data.bank_transaction_id,
            skonto_deducted=float(payment_data.skonto_deducted) if payment_data.skonto_deducted else None,
            reconciliation_status="matched" if payment_data.bank_transaction_id else "pending",
            reconciled_at=utc_now() if payment_data.bank_transaction_id else None,
            notes=payment_data.notes,
            created_at=utc_now(),
            created_by_id=user_id,
            company_id=company_id,
        )

        db.add(transaction)

        # Invoice aktualisieren
        new_paid = current_paid + payment_data.amount
        skonto_total = payment_data.skonto_deducted or Decimal("0")

        invoice.paid_amount = float(new_paid)
        invoice.outstanding_amount = float(max(Decimal("0"), total_amount - new_paid))
        invoice.is_partial_payment = True
        invoice.updated_at = utc_now()

        # Status aktualisieren
        if new_paid >= total_amount - self.PAYMENT_TOLERANCE:
            invoice.status = "paid"
            invoice.paid_at = utc_now()
            if not message:
                message = "Rechnung vollständig bezahlt"
        else:
            invoice.status = "partial"
            remaining = total_amount - new_paid
            message = message or f"Teilzahlung erfasst - noch {remaining}EUR ausstehend"

        await db.flush()

        logger.info(
            "Teilzahlung erfasst",
            invoice_id=str(invoice_tracking_id),
            payment_amount=str(payment_data.amount),
            total_paid=str(new_paid),
            status=invoice.status,
        )

        return PaymentTransactionResponse(
            id=transaction.id,
            invoice_tracking_id=invoice_tracking_id,
            amount=Decimal(str(transaction.amount)),
            transaction_date=transaction.transaction_date,
            payment_reference=transaction.payment_reference,
            payment_method=transaction.payment_method,
            skonto_deducted=Decimal(str(transaction.skonto_deducted)) if transaction.skonto_deducted else None,
            reconciliation_status=transaction.reconciliation_status,
            created_at=transaction.created_at,
        ), message

    async def get_payment_summary(
        self,
        db: AsyncSession,
        invoice_tracking_id: UUID,
        company_id: UUID,
    ) -> InvoicePaymentSummary:
        """Hole Zahlungsübersicht für eine Rechnung.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Args:
            db: Datenbank-Session
            invoice_tracking_id: ID des Invoice-Trackings
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)

        Returns:
            InvoicePaymentSummary

        Raises:
            ValueError: Wenn Rechnung nicht gefunden oder company_id nicht stimmt
        """
        from app.db.models import InvoiceTracking, PaymentTransaction

        # Invoice laden - SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.id == invoice_tracking_id,
                InvoiceTracking.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise ValueError("Rechnung nicht gefunden")

        # Alle Zahlungen laden - SECURITY: company_id Filter für Defense-in-Depth
        payments_stmt = (
            select(PaymentTransaction)
            .where(
                and_(
                    PaymentTransaction.invoice_tracking_id == invoice_tracking_id,
                    PaymentTransaction.company_id == company_id,
                )
            )
            .order_by(PaymentTransaction.transaction_date.asc())
        )
        payments_result = await db.execute(payments_stmt)
        payments = payments_result.scalars().all()

        # Berechnung
        total_amount = Decimal(str(invoice.amount))
        paid_amount = sum(Decimal(str(p.amount)) for p in payments)
        skonto_total = sum(
            Decimal(str(p.skonto_deducted)) for p in payments
            if p.skonto_deducted
        )
        outstanding = max(Decimal("0"), total_amount - paid_amount)
        overpaid = max(Decimal("0"), paid_amount - total_amount)

        payment_responses = [
            PaymentTransactionResponse(
                id=p.id,
                invoice_tracking_id=p.invoice_tracking_id,
                amount=Decimal(str(p.amount)),
                transaction_date=p.transaction_date,
                payment_reference=p.payment_reference,
                payment_method=p.payment_method,
                skonto_deducted=Decimal(str(p.skonto_deducted)) if p.skonto_deducted else None,
                reconciliation_status=p.reconciliation_status,
                created_at=p.created_at,
            )
            for p in payments
        ]

        return InvoicePaymentSummary(
            invoice_tracking_id=invoice_tracking_id,
            invoice_number=invoice.invoice_number,
            total_amount=total_amount,
            paid_amount=paid_amount,
            outstanding_amount=outstanding,
            skonto_total=skonto_total,
            payment_count=len(payments),
            payments=payment_responses,
            is_fully_paid=outstanding <= self.PAYMENT_TOLERANCE,
            overpaid_amount=overpaid,
        )

    async def delete_payment(
        self,
        db: AsyncSession,
        payment_transaction_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> Tuple[bool, str]:
        """Lösche eine Teilzahlung.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Nur möglich wenn:
        - Zahlung noch nicht reconciled
        - Benutzer berechtigt
        - company_id stimmt

        Args:
            db: Datenbank-Session
            payment_transaction_id: ID der Transaktion
            user_id: Benutzer-ID
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)

        Returns:
            Tuple: (Erfolg, Meldung)
        """
        from app.db.models import InvoiceTracking, PaymentTransaction

        # Transaktion laden - SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(PaymentTransaction).where(
            and_(
                PaymentTransaction.id == payment_transaction_id,
                PaymentTransaction.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.warning(
                "delete_payment_failed",
                payment_id=str(payment_transaction_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False, "Transaktion nicht gefunden"

        if transaction.reconciliation_status == "matched":
            return False, "Bereits abgestimmte Zahlung kann nicht gelöscht werden"

        invoice_tracking_id = transaction.invoice_tracking_id
        deleted_amount = Decimal(str(transaction.amount))

        # Transaktion löschen
        await db.delete(transaction)

        # Invoice aktualisieren - SECURITY: company_id Filter für Defense-in-Depth
        invoice_stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.id == invoice_tracking_id,
                InvoiceTracking.company_id == company_id,
            )
        )
        invoice_result = await db.execute(invoice_stmt)
        invoice = invoice_result.scalar_one_or_none()

        if invoice:
            # Neuen Stand berechnen - SECURITY: company_id durchreichen
            new_paid = await self._get_total_paid(db, invoice_tracking_id, company_id)
            total_amount = Decimal(str(invoice.amount))

            invoice.paid_amount = float(new_paid)
            invoice.outstanding_amount = float(total_amount - new_paid)
            invoice.updated_at = utc_now()

            # Status anpassen
            if new_paid <= self.PAYMENT_TOLERANCE:
                invoice.status = "open" if not invoice.due_date or invoice.due_date > utc_now() else "overdue"
                invoice.is_partial_payment = False
            elif new_paid < total_amount - self.PAYMENT_TOLERANCE:
                invoice.status = "partial"
                invoice.is_partial_payment = True
            else:
                invoice.status = "paid"

        await db.flush()

        logger.info(
            "Teilzahlung gelöscht",
            payment_id=str(payment_transaction_id),
            invoice_id=str(invoice_tracking_id),
            deleted_amount=str(deleted_amount),
        )

        return True, f"Zahlung über {deleted_amount}EUR gelöscht"

    async def get_partially_paid_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 50,
    ) -> List[InvoicePaymentSummary]:
        """Hole alle Rechnungen mit Teilzahlungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            limit: Maximale Anzahl

        Returns:
            Liste von InvoicePaymentSummary
        """
        from app.db.models import InvoiceTracking

        stmt = (
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.is_partial_payment == True,
                    InvoiceTracking.status.in_(["partial", "paid"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            .order_by(InvoiceTracking.updated_at.desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        invoices = result.scalars().all()

        summaries = []
        for invoice in invoices:
            # SECURITY: company_id durchreichen für Defense-in-Depth
            summary = await self.get_payment_summary(db, invoice.id, company_id)
            summaries.append(summary)

        return summaries

    async def reconcile_with_bank_transaction(
        self,
        db: AsyncSession,
        payment_transaction_id: UUID,
        bank_transaction_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> bool:
        """Verknüpfe Teilzahlung mit Bank-Transaktion.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Args:
            db: Datenbank-Session
            payment_transaction_id: ID der Teilzahlung
            bank_transaction_id: ID der Bank-Transaktion
            user_id: Benutzer-ID
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)

        Returns:
            True bei Erfolg
        """
        from app.db.models import PaymentTransaction

        # SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(PaymentTransaction).where(
            and_(
                PaymentTransaction.id == payment_transaction_id,
                PaymentTransaction.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()

        if not transaction:
            logger.warning(
                "reconcile_payment_failed",
                payment_id=str(payment_transaction_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False

        transaction.bank_transaction_id = bank_transaction_id
        transaction.reconciliation_status = "matched"
        transaction.reconciled_at = utc_now()
        transaction.reconciled_by_id = user_id

        await db.flush()

        logger.info(
            "Teilzahlung mit Bank-Transaktion verknüpft",
            payment_id=str(payment_transaction_id),
            bank_transaction_id=str(bank_transaction_id),
        )

        return True

    async def _get_total_paid(
        self,
        db: AsyncSession,
        invoice_tracking_id: UUID,
        company_id: UUID,
    ) -> Decimal:
        """Berechne Summe aller Zahlungen für eine Rechnung.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Args:
            db: Datenbank-Session
            invoice_tracking_id: ID des Invoice-Trackings
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)

        Returns:
            Summe der Zahlungen
        """
        from app.db.models import PaymentTransaction

        # SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
            and_(
                PaymentTransaction.invoice_tracking_id == invoice_tracking_id,
                PaymentTransaction.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        total = result.scalar() or 0

        return Decimal(str(total))
