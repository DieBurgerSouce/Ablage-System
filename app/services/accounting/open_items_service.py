# -*- coding: utf-8 -*-
"""
Offene Posten Service (Open Items / Accounts Receivable & Payable).

Verwaltet Debitoren und Kreditoren:
- Offene Forderungen (Ausgangsrechnungen)
- Offene Verbindlichkeiten (Eingangsrechnungen)
- Zahlungsstatus-Tracking
- Faelligkeits-Management

GoBD-konform mit vollstaendiger Protokollierung.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    InvoiceStatus,
    EntityType,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================


class OpenItemType(str, Enum):
    """Typ des offenen Postens."""
    RECEIVABLE = "receivable"  # Forderung (Debitor)
    PAYABLE = "payable"        # Verbindlichkeit (Kreditor)


class PaymentPriority(str, Enum):
    """Zahlungsprioritaet."""
    NORMAL = "normal"
    HIGH = "high"      # Skonto-Frist naht
    URGENT = "urgent"  # Ueberfaellig
    CRITICAL = "critical"  # Stark ueberfaellig (90+ Tage)


@dataclass
class OpenItem:
    """Ein offener Posten."""
    id: uuid.UUID
    document_id: uuid.UUID
    invoice_tracking_id: Optional[uuid.UUID]

    item_type: OpenItemType
    entity_id: Optional[uuid.UUID]
    entity_name: str

    invoice_number: Optional[str]
    invoice_date: Optional[date]
    due_date: Optional[date]

    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    currency: str = "EUR"

    days_overdue: int = 0
    dunning_level: int = 0
    payment_priority: PaymentPriority = PaymentPriority.NORMAL

    # Skonto
    skonto_deadline: Optional[date] = None
    skonto_amount: Optional[Decimal] = None
    skonto_percentage: Optional[float] = None

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_payment_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "invoice_tracking_id": str(self.invoice_tracking_id) if self.invoice_tracking_id else None,
            "item_type": self.item_type.value,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "entity_name": self.entity_name,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "amount": float(self.amount),
            "paid_amount": float(self.paid_amount),
            "outstanding_amount": float(self.outstanding_amount),
            "currency": self.currency,
            "days_overdue": self.days_overdue,
            "dunning_level": self.dunning_level,
            "payment_priority": self.payment_priority.value,
            "skonto_deadline": self.skonto_deadline.isoformat() if self.skonto_deadline else None,
            "skonto_amount": float(self.skonto_amount) if self.skonto_amount else None,
            "skonto_percentage": self.skonto_percentage,
        }


@dataclass
class OpenItemsReport:
    """Zusammenfassung der offenen Posten."""
    report_date: date
    generated_at: datetime

    # Forderungen
    total_receivables: Decimal = Decimal("0.00")
    total_receivables_overdue: Decimal = Decimal("0.00")
    receivables_count: int = 0
    receivables_overdue_count: int = 0

    # Verbindlichkeiten
    total_payables: Decimal = Decimal("0.00")
    total_payables_overdue: Decimal = Decimal("0.00")
    payables_count: int = 0
    payables_overdue_count: int = 0

    # Skonto-Potenzial
    skonto_potential: Decimal = Decimal("0.00")
    skonto_items_count: int = 0

    # Netto-Position
    net_position: Decimal = Decimal("0.00")

    # Details
    receivables: List[OpenItem] = field(default_factory=list)
    payables: List[OpenItem] = field(default_factory=list)


@dataclass
class EntityBalance:
    """Saldo eines Geschaeftspartners."""
    entity_id: uuid.UUID
    entity_name: str
    entity_type: str  # customer, supplier

    total_invoices: Decimal = Decimal("0.00")
    total_paid: Decimal = Decimal("0.00")
    outstanding: Decimal = Decimal("0.00")
    overdue_amount: Decimal = Decimal("0.00")

    invoice_count: int = 0
    open_items_count: int = 0
    oldest_open_days: int = 0
    average_payment_days: float = 0.0

    credit_limit: Optional[Decimal] = None
    credit_usage_percent: float = 0.0


# ============================================================================
# OPEN ITEMS SERVICE
# ============================================================================


class OpenItemsService:
    """
    Service fuer Offene-Posten-Verwaltung.

    Features:
    - Debitoren-/Kreditoren-Uebersicht
    - Faelligkeitsanalyse
    - Skonto-Optimierung
    - Zahlungspriorisierung
    - Entity-Salden

    GoBD-konform mit Audit-Trail.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    # ========================================================================
    # OFFENE POSTEN ABFRAGEN
    # ========================================================================

    async def get_open_items_report(
        self,
        company_id: uuid.UUID,
        as_of_date: Optional[date] = None,
        include_details: bool = True,
    ) -> OpenItemsReport:
        """
        Erstellt vollstaendigen Offene-Posten-Bericht.

        Args:
            company_id: Firma
            as_of_date: Stichtag (Standard: heute)
            include_details: Einzelpositionen einbeziehen

        Returns:
            OpenItemsReport
        """
        if as_of_date is None:
            as_of_date = date.today()

        report = OpenItemsReport(
            report_date=as_of_date,
            generated_at=datetime.now(timezone.utc),
        )

        # Forderungen laden
        receivables = await self._get_open_receivables(company_id, as_of_date)
        for item in receivables:
            report.total_receivables += item.outstanding_amount
            report.receivables_count += 1

            if item.days_overdue > 0:
                report.total_receivables_overdue += item.outstanding_amount
                report.receivables_overdue_count += 1

            if item.skonto_amount and item.skonto_deadline and item.skonto_deadline >= as_of_date:
                report.skonto_potential += item.skonto_amount
                report.skonto_items_count += 1

        if include_details:
            report.receivables = receivables

        # Verbindlichkeiten laden
        payables = await self._get_open_payables(company_id, as_of_date)
        for item in payables:
            report.total_payables += item.outstanding_amount
            report.payables_count += 1

            if item.days_overdue > 0:
                report.total_payables_overdue += item.outstanding_amount
                report.payables_overdue_count += 1

        if include_details:
            report.payables = payables

        # Netto-Position
        report.net_position = report.total_receivables - report.total_payables

        logger.info(
            "open_items_report_generated",
            company_id=str(company_id),
            receivables_count=report.receivables_count,
            payables_count=report.payables_count,
            net_position=float(report.net_position),
        )

        return report

    async def get_open_receivables(
        self,
        company_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
        overdue_only: bool = False,
        priority: Optional[PaymentPriority] = None,
    ) -> List[OpenItem]:
        """
        Holt offene Forderungen.

        Args:
            company_id: Firma
            entity_id: Optional - nur fuer bestimmten Debitor
            overdue_only: Nur ueberfaellige
            priority: Nach Prioritaet filtern

        Returns:
            Liste offener Posten
        """
        items = await self._get_open_receivables(company_id, date.today())

        if entity_id:
            items = [i for i in items if i.entity_id == entity_id]

        if overdue_only:
            items = [i for i in items if i.days_overdue > 0]

        if priority:
            items = [i for i in items if i.payment_priority == priority]

        return items

    async def get_open_payables(
        self,
        company_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
        due_within_days: Optional[int] = None,
    ) -> List[OpenItem]:
        """
        Holt offene Verbindlichkeiten.

        Args:
            company_id: Firma
            entity_id: Optional - nur fuer bestimmten Kreditor
            due_within_days: Nur die in X Tagen faellig werden

        Returns:
            Liste offener Posten
        """
        items = await self._get_open_payables(company_id, date.today())

        if entity_id:
            items = [i for i in items if i.entity_id == entity_id]

        if due_within_days is not None:
            cutoff = date.today() + timedelta(days=due_within_days)
            items = [
                i for i in items
                if i.due_date and i.due_date <= cutoff
            ]

        return items

    async def _get_open_receivables(
        self,
        company_id: uuid.UUID,
        as_of_date: date,
    ) -> List[OpenItem]:
        """Holt offene Forderungen aus der DB."""
        # Ausgangsrechnungen mit offenen Betraegen
        query = (
            select(InvoiceTracking, Document, BusinessEntity)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .outerjoin(BusinessEntity, Document.entity_id == BusinessEntity.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type.in_(["invoice", "ausgangsrechnung"]),
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.status.notin_([
                        InvoiceStatus.PAID.value,
                        InvoiceStatus.CANCELLED.value,
                    ]),
                )
            )
        )

        result = await self.db.execute(query)
        rows = result.all()

        items: List[OpenItem] = []

        for inv, doc, entity in rows:
            outstanding = Decimal(str(inv.amount or 0)) - Decimal(str(inv.paid_amount or 0))
            if outstanding <= 0:
                continue

            # Tage ueberfaellig berechnen
            days_overdue = 0
            if inv.due_date:
                due = inv.due_date.date() if hasattr(inv.due_date, 'date') else inv.due_date
                days_overdue = max(0, (as_of_date - due).days)

            # Prioritaet bestimmen
            priority = self._calculate_priority(days_overdue, inv.skonto_deadline, as_of_date)

            item = OpenItem(
                id=uuid.uuid4(),
                document_id=doc.id,
                invoice_tracking_id=inv.id,
                item_type=OpenItemType.RECEIVABLE,
                entity_id=entity.id if entity else None,
                entity_name=entity.name if entity else (doc.extracted_data or {}).get("customer_name", "Unbekannt"),
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date.date() if hasattr(inv.invoice_date, 'date') else inv.invoice_date,
                due_date=inv.due_date.date() if hasattr(inv.due_date, 'date') else inv.due_date,
                amount=Decimal(str(inv.amount or 0)),
                paid_amount=Decimal(str(inv.paid_amount or 0)),
                outstanding_amount=outstanding,
                currency=inv.currency or "EUR",
                days_overdue=days_overdue,
                dunning_level=inv.dunning_level or 0,
                payment_priority=priority,
                skonto_deadline=inv.skonto_deadline.date() if inv.skonto_deadline and hasattr(inv.skonto_deadline, 'date') else inv.skonto_deadline,
                skonto_amount=Decimal(str(inv.skonto_amount)) if inv.skonto_amount else None,
                skonto_percentage=inv.skonto_percentage,
            )
            items.append(item)

        # Nach Prioritaet und Faelligkeit sortieren
        items.sort(key=lambda x: (
            -self._priority_rank(x.payment_priority),
            x.due_date or date.max,
        ))

        return items

    async def _get_open_payables(
        self,
        company_id: uuid.UUID,
        as_of_date: date,
    ) -> List[OpenItem]:
        """Holt offene Verbindlichkeiten aus der DB."""
        # Eingangsrechnungen mit offenen Betraegen
        query = (
            select(InvoiceTracking, Document, BusinessEntity)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .outerjoin(BusinessEntity, Document.entity_id == BusinessEntity.id)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type.in_(["eingangsrechnung", "supplier_invoice", "purchase_invoice"]),
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.status.notin_([
                        InvoiceStatus.PAID.value,
                        InvoiceStatus.CANCELLED.value,
                    ]),
                )
            )
        )

        result = await self.db.execute(query)
        rows = result.all()

        items: List[OpenItem] = []

        for inv, doc, entity in rows:
            outstanding = Decimal(str(inv.amount or 0)) - Decimal(str(inv.paid_amount or 0))
            if outstanding <= 0:
                continue

            # Tage ueberfaellig
            days_overdue = 0
            if inv.due_date:
                due = inv.due_date.date() if hasattr(inv.due_date, 'date') else inv.due_date
                days_overdue = max(0, (as_of_date - due).days)

            priority = self._calculate_priority(days_overdue, inv.skonto_deadline, as_of_date)

            item = OpenItem(
                id=uuid.uuid4(),
                document_id=doc.id,
                invoice_tracking_id=inv.id,
                item_type=OpenItemType.PAYABLE,
                entity_id=entity.id if entity else None,
                entity_name=entity.name if entity else (doc.extracted_data or {}).get("supplier_name", "Unbekannt"),
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date.date() if hasattr(inv.invoice_date, 'date') else inv.invoice_date,
                due_date=inv.due_date.date() if hasattr(inv.due_date, 'date') else inv.due_date,
                amount=Decimal(str(inv.amount or 0)),
                paid_amount=Decimal(str(inv.paid_amount or 0)),
                outstanding_amount=outstanding,
                currency=inv.currency or "EUR",
                days_overdue=days_overdue,
                dunning_level=inv.dunning_level or 0,
                payment_priority=priority,
                skonto_deadline=inv.skonto_deadline.date() if inv.skonto_deadline and hasattr(inv.skonto_deadline, 'date') else inv.skonto_deadline,
                skonto_amount=Decimal(str(inv.skonto_amount)) if inv.skonto_amount else None,
                skonto_percentage=inv.skonto_percentage,
            )
            items.append(item)

        # Sortieren: Skonto-Fristen zuerst, dann Faelligkeit
        items.sort(key=lambda x: (
            x.skonto_deadline or date.max,
            x.due_date or date.max,
        ))

        return items

    def _calculate_priority(
        self,
        days_overdue: int,
        skonto_deadline: Optional[datetime],
        as_of_date: date,
    ) -> PaymentPriority:
        """Berechnet die Zahlungsprioritaet."""
        if days_overdue >= 90:
            return PaymentPriority.CRITICAL
        elif days_overdue > 0:
            return PaymentPriority.URGENT

        # Skonto-Frist pruefen
        if skonto_deadline:
            deadline = skonto_deadline.date() if hasattr(skonto_deadline, 'date') else skonto_deadline
            days_to_skonto = (deadline - as_of_date).days
            if 0 <= days_to_skonto <= 3:
                return PaymentPriority.HIGH

        return PaymentPriority.NORMAL

    def _priority_rank(self, priority: PaymentPriority) -> int:
        """Gibt numerischen Rang fuer Sortierung zurueck."""
        ranks = {
            PaymentPriority.CRITICAL: 4,
            PaymentPriority.URGENT: 3,
            PaymentPriority.HIGH: 2,
            PaymentPriority.NORMAL: 1,
        }
        return ranks.get(priority, 0)

    # ========================================================================
    # ENTITY BALANCES
    # ========================================================================

    async def get_debtor_balances(
        self,
        company_id: uuid.UUID,
        min_outstanding: Optional[Decimal] = None,
    ) -> List[EntityBalance]:
        """
        Holt Debitoren-Salden (Kunden).

        Args:
            company_id: Firma
            min_outstanding: Mindest-Aussenhstand

        Returns:
            Liste der Debitoren mit Salden
        """
        items = await self._get_open_receivables(company_id, date.today())
        return self._aggregate_entity_balances(items, EntityType.CUSTOMER, min_outstanding)

    async def get_creditor_balances(
        self,
        company_id: uuid.UUID,
        min_outstanding: Optional[Decimal] = None,
    ) -> List[EntityBalance]:
        """
        Holt Kreditoren-Salden (Lieferanten).

        Args:
            company_id: Firma
            min_outstanding: Mindest-Aussenhstand

        Returns:
            Liste der Kreditoren mit Salden
        """
        items = await self._get_open_payables(company_id, date.today())
        return self._aggregate_entity_balances(items, EntityType.SUPPLIER, min_outstanding)

    def _aggregate_entity_balances(
        self,
        items: List[OpenItem],
        entity_type: EntityType,
        min_outstanding: Optional[Decimal],
    ) -> List[EntityBalance]:
        """Aggregiert offene Posten zu Entity-Salden."""
        by_entity: Dict[uuid.UUID, EntityBalance] = {}

        # Fallback fuer Items ohne Entity
        unknown_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

        for item in items:
            eid = item.entity_id or unknown_id

            if eid not in by_entity:
                by_entity[eid] = EntityBalance(
                    entity_id=eid,
                    entity_name=item.entity_name,
                    entity_type=entity_type.value,
                )

            balance = by_entity[eid]
            balance.total_invoices += item.amount
            balance.total_paid += item.paid_amount
            balance.outstanding += item.outstanding_amount
            balance.invoice_count += 1
            balance.open_items_count += 1

            if item.days_overdue > 0:
                balance.overdue_amount += item.outstanding_amount
                balance.oldest_open_days = max(balance.oldest_open_days, item.days_overdue)

        balances = list(by_entity.values())

        # Filter
        if min_outstanding:
            balances = [b for b in balances if b.outstanding >= min_outstanding]

        # Nach Aussenstand sortieren
        balances.sort(key=lambda b: b.outstanding, reverse=True)

        return balances

    # ========================================================================
    # PAYMENT SUGGESTIONS
    # ========================================================================

    async def get_payment_suggestions(
        self,
        company_id: uuid.UUID,
        available_funds: Decimal,
        optimize_for: str = "skonto",  # skonto, due_date, amount
    ) -> List[Dict[str, Any]]:
        """
        Erstellt Zahlungsvorschlaege basierend auf verfuegbaren Mitteln.

        Args:
            company_id: Firma
            available_funds: Verfuegbare Mittel
            optimize_for: Optimierungsstrategie
                - skonto: Maximiere Skonto-Ersparnis
                - due_date: Nach Faelligkeit
                - amount: Kleinste zuerst

        Returns:
            Zahlungsvorschlaege
        """
        payables = await self._get_open_payables(company_id, date.today())

        if not payables:
            return []

        # Sortieren nach Strategie
        if optimize_for == "skonto":
            # Skonto-Posten zuerst, nach Deadline sortiert
            payables.sort(key=lambda x: (
                0 if x.skonto_deadline and x.skonto_deadline >= date.today() else 1,
                x.skonto_deadline or date.max,
            ))
        elif optimize_for == "due_date":
            payables.sort(key=lambda x: x.due_date or date.max)
        elif optimize_for == "amount":
            payables.sort(key=lambda x: x.outstanding_amount)

        suggestions = []
        remaining_funds = available_funds
        total_skonto = Decimal("0.00")

        for item in payables:
            if remaining_funds <= 0:
                break

            # Skonto-Betrag berechnen
            pay_with_skonto = item.outstanding_amount
            skonto_savings = Decimal("0.00")

            if item.skonto_deadline and item.skonto_deadline >= date.today() and item.skonto_amount:
                pay_with_skonto = item.outstanding_amount - item.skonto_amount
                skonto_savings = item.skonto_amount

            if remaining_funds >= pay_with_skonto:
                suggestions.append({
                    "invoice_number": item.invoice_number,
                    "entity_name": item.entity_name,
                    "original_amount": float(item.outstanding_amount),
                    "pay_amount": float(pay_with_skonto),
                    "skonto_savings": float(skonto_savings),
                    "due_date": item.due_date.isoformat() if item.due_date else None,
                    "skonto_deadline": item.skonto_deadline.isoformat() if item.skonto_deadline else None,
                    "priority": item.payment_priority.value,
                    "document_id": str(item.document_id),
                })
                remaining_funds -= pay_with_skonto
                total_skonto += skonto_savings

        logger.info(
            "payment_suggestions_generated",
            company_id=str(company_id),
            available_funds=float(available_funds),
            suggestions_count=len(suggestions),
            total_skonto_savings=float(total_skonto),
        )

        return suggestions


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_open_items_service(db: AsyncSession) -> OpenItemsService:
    """Factory-Funktion fuer Dependency Injection."""
    return OpenItemsService(db)
