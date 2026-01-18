# -*- coding: utf-8 -*-
"""Calendar & Deadline Service.

Zentralisierte Fristenverwaltung fuer das Ablage-System:
- Zahlungsfristen (Eingang + Ausgang)
- Skonto-Fristen
- Steuertermine
- Vertragsfristen

Features:
- Kalender-Ansicht mit allen Fristen
- Benachrichtigungen vor Ablauf
- Priorisierung nach Dringlichkeit
- Integration mit bestehenden Services
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


class DeadlineCategory(str, Enum):
    """Kategorien fuer Fristen."""
    SKONTO = "skonto"
    PAYMENT_INCOMING = "payment_incoming"  # Zahlungseingang
    PAYMENT_OUTGOING = "payment_outgoing"  # Zahlungsausgang
    TAX = "tax"                            # Steuertermine
    CONTRACT = "contract"                   # Vertragsfristen
    DUNNING = "dunning"                    # Mahnfristen
    DOCUMENT = "document"                   # Dokumentenfristen
    CUSTOM = "custom"                       # Benutzerdefiniert


class DeadlineUrgency(str, Enum):
    """Dringlichkeitsstufen."""
    CRITICAL = "critical"    # Heute oder ueberfaellig
    WARNING = "warning"      # Innerhalb 3 Tagen
    UPCOMING = "upcoming"    # Innerhalb 7 Tagen
    SCHEDULED = "scheduled"  # Mehr als 7 Tage


class DeadlineStatus(str, Enum):
    """Status einer Frist."""
    PENDING = "pending"      # Ausstehend
    COMPLETED = "completed"  # Erledigt
    EXPIRED = "expired"      # Abgelaufen (nicht erledigt)
    CANCELLED = "cancelled"  # Storniert


@dataclass
class DeadlineItem:
    """Einzelne Frist."""
    id: str
    category: DeadlineCategory
    title: str
    description: str
    deadline: datetime
    urgency: DeadlineUrgency
    status: DeadlineStatus
    days_until: int

    # Optionale Referenzen
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    contract_id: Optional[UUID] = None

    # Betrag (falls relevant)
    amount: Optional[Decimal] = None
    currency: str = "EUR"

    # Zusaetzliche Metadaten
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CalendarDay:
    """Ein Tag im Kalender mit Fristen."""
    date: date
    deadlines: List[DeadlineItem] = field(default_factory=list)
    total_amount_incoming: Decimal = Decimal("0.00")
    total_amount_outgoing: Decimal = Decimal("0.00")

    @property
    def has_critical(self) -> bool:
        return any(d.urgency == DeadlineUrgency.CRITICAL for d in self.deadlines)

    @property
    def deadline_count(self) -> int:
        return len(self.deadlines)


@dataclass
class CalendarWeek:
    """Eine Woche im Kalender."""
    week_number: int
    year: int
    start_date: date
    end_date: date
    days: List[CalendarDay] = field(default_factory=list)

    @property
    def total_deadlines(self) -> int:
        return sum(day.deadline_count for day in self.days)


@dataclass
class CalendarMonth:
    """Ein Monat im Kalender."""
    month: int
    year: int
    weeks: List[CalendarWeek] = field(default_factory=list)
    summary: Dict[DeadlineCategory, int] = field(default_factory=dict)


@dataclass
class DeadlineSummary:
    """Zusammenfassung aller Fristen."""
    total_count: int
    critical_count: int
    warning_count: int
    upcoming_count: int
    scheduled_count: int
    overdue_count: int

    by_category: Dict[DeadlineCategory, int] = field(default_factory=dict)
    total_amount_at_risk: Decimal = Decimal("0.00")
    next_deadline: Optional[DeadlineItem] = None


class CalendarService:
    """Service fuer Kalender und Fristenverwaltung."""

    # Standard-Steuertermine (jaehrlich wiederkehrend)
    STANDARD_TAX_DEADLINES = [
        # USt-Voranmeldung
        {"day": 10, "name": "USt-Voranmeldung", "monthly": True},
        # Lohnsteuer
        {"day": 10, "name": "Lohnsteuer-Anmeldung", "monthly": True},
        # Einkommensteuer-Vorauszahlung
        {"day": 10, "months": [3, 6, 9, 12], "name": "ESt-Vorauszahlung", "quarterly": True},
        # Koerperschaftsteuer-Vorauszahlung
        {"day": 10, "months": [3, 6, 9, 12], "name": "KSt-Vorauszahlung", "quarterly": True},
        # Gewerbesteuer-Vorauszahlung
        {"day": 15, "months": [2, 5, 8, 11], "name": "GewSt-Vorauszahlung", "quarterly": True},
        # Jahresabschluss (31.12. Geschaeftsjahr)
        {"day": 31, "month": 7, "name": "Jahresabschluss Einreichung", "annual": True},
    ]

    async def get_all_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        categories: Optional[List[DeadlineCategory]] = None,
        include_completed: bool = False,
        limit: int = 100,
    ) -> List[DeadlineItem]:
        """Hole alle Fristen fuer einen Zeitraum.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            start_date: Startdatum (default: heute)
            end_date: Enddatum (default: heute + 90 Tage)
            categories: Filter nach Kategorien
            include_completed: Erledigte Fristen einschliessen
            limit: Maximale Anzahl

        Returns:
            Liste von DeadlineItem sortiert nach Dringlichkeit
        """
        now = utc_now()
        today = now.date()

        if start_date is None:
            start_date = today - timedelta(days=7)  # Auch kuerzlich ueberfaellige
        if end_date is None:
            end_date = today + timedelta(days=90)

        all_deadlines: List[DeadlineItem] = []

        # 1. Skonto-Fristen
        skonto_deadlines = await self._get_skonto_deadlines(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(skonto_deadlines)

        # 2. Zahlungsfristen (Ausgang - wir muessen zahlen)
        payment_outgoing = await self._get_payment_deadlines_outgoing(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(payment_outgoing)

        # 3. Zahlungsfristen (Eingang - Kunden muessen zahlen)
        payment_incoming = await self._get_payment_deadlines_incoming(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(payment_incoming)

        # 4. Steuertermine (aus Konfiguration + Dokumente)
        tax_deadlines = await self._get_tax_deadlines(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(tax_deadlines)

        # 5. Vertragsfristen
        contract_deadlines = await self._get_contract_deadlines(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(contract_deadlines)

        # 6. Mahnfristen
        dunning_deadlines = await self._get_dunning_deadlines(
            db, company_id, start_date, end_date
        )
        all_deadlines.extend(dunning_deadlines)

        # Filter nach Kategorien
        if categories:
            all_deadlines = [d for d in all_deadlines if d.category in categories]

        # Filter completed
        if not include_completed:
            all_deadlines = [d for d in all_deadlines if d.status != DeadlineStatus.COMPLETED]

        # Sortieren nach Dringlichkeit (ueberfaellig zuerst, dann nach Datum)
        all_deadlines.sort(key=lambda x: (x.days_until >= 0, x.days_until))

        # Limit
        return all_deadlines[:limit]

    async def get_calendar_month(
        self,
        db: AsyncSession,
        company_id: UUID,
        year: int,
        month: int,
    ) -> CalendarMonth:
        """Hole Kalender-Ansicht fuer einen Monat.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            year: Jahr
            month: Monat (1-12)

        Returns:
            CalendarMonth mit Wochen und Tagen
        """
        from calendar import monthcalendar, monthrange

        # Monat-Grenzen
        first_day = date(year, month, 1)
        _, last_day_num = monthrange(year, month)
        last_day = date(year, month, last_day_num)

        # Alle Fristen fuer den Monat holen
        deadlines = await self.get_all_deadlines(
            db, company_id,
            start_date=first_day,
            end_date=last_day,
            limit=500
        )

        # Fristen nach Datum gruppieren
        deadlines_by_date: Dict[date, List[DeadlineItem]] = {}
        for deadline in deadlines:
            deadline_date = deadline.deadline.date() if isinstance(deadline.deadline, datetime) else deadline.deadline
            if deadline_date not in deadlines_by_date:
                deadlines_by_date[deadline_date] = []
            deadlines_by_date[deadline_date].append(deadline)

        # Wochen erstellen
        weeks: List[CalendarWeek] = []
        calendar_weeks = monthcalendar(year, month)

        for week_idx, week_days in enumerate(calendar_weeks):
            week_start = None
            week_end = None
            days: List[CalendarDay] = []

            for day_num in week_days:
                if day_num == 0:
                    continue

                current_date = date(year, month, day_num)
                if week_start is None:
                    week_start = current_date
                week_end = current_date

                day_deadlines = deadlines_by_date.get(current_date, [])

                # Betraege berechnen
                incoming = sum(
                    d.amount or Decimal("0.00")
                    for d in day_deadlines
                    if d.category == DeadlineCategory.PAYMENT_INCOMING
                )
                outgoing = sum(
                    d.amount or Decimal("0.00")
                    for d in day_deadlines
                    if d.category in [DeadlineCategory.PAYMENT_OUTGOING, DeadlineCategory.SKONTO, DeadlineCategory.TAX]
                )

                days.append(CalendarDay(
                    date=current_date,
                    deadlines=day_deadlines,
                    total_amount_incoming=incoming,
                    total_amount_outgoing=outgoing,
                ))

            if week_start and week_end:
                week_number = week_start.isocalendar()[1]
                weeks.append(CalendarWeek(
                    week_number=week_number,
                    year=year,
                    start_date=week_start,
                    end_date=week_end,
                    days=days,
                ))

        # Zusammenfassung nach Kategorie
        summary: Dict[DeadlineCategory, int] = {}
        for deadline in deadlines:
            summary[deadline.category] = summary.get(deadline.category, 0) + 1

        return CalendarMonth(
            month=month,
            year=year,
            weeks=weeks,
            summary=summary,
        )

    async def get_deadline_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> DeadlineSummary:
        """Hole Zusammenfassung aller aktuellen Fristen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            DeadlineSummary mit Statistiken
        """
        today = date.today()

        # Alle Fristen holen
        deadlines = await self.get_all_deadlines(
            db, company_id,
            start_date=today - timedelta(days=30),  # Auch ueberfaellige
            end_date=today + timedelta(days=90),
            limit=1000
        )

        # Zaehlen
        critical = 0
        warning = 0
        upcoming = 0
        scheduled = 0
        overdue = 0
        by_category: Dict[DeadlineCategory, int] = {}
        amount_at_risk = Decimal("0.00")

        for deadline in deadlines:
            # Nach Kategorie
            by_category[deadline.category] = by_category.get(deadline.category, 0) + 1

            # Nach Dringlichkeit
            if deadline.urgency == DeadlineUrgency.CRITICAL:
                critical += 1
            elif deadline.urgency == DeadlineUrgency.WARNING:
                warning += 1
            elif deadline.urgency == DeadlineUrgency.UPCOMING:
                upcoming += 1
            else:
                scheduled += 1

            # Ueberfaellig
            if deadline.days_until < 0:
                overdue += 1
                if deadline.amount:
                    amount_at_risk += deadline.amount

        # Naechste Frist
        pending_deadlines = [d for d in deadlines if d.status == DeadlineStatus.PENDING and d.days_until >= 0]
        next_deadline = pending_deadlines[0] if pending_deadlines else None

        return DeadlineSummary(
            total_count=len(deadlines),
            critical_count=critical,
            warning_count=warning,
            upcoming_count=upcoming,
            scheduled_count=scheduled,
            overdue_count=overdue,
            by_category=by_category,
            total_amount_at_risk=amount_at_risk,
            next_deadline=next_deadline,
        )

    async def get_upcoming_alerts(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 7,
    ) -> List[DeadlineItem]:
        """Hole dringende Fristen fuer Benachrichtigungen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            days_ahead: Tage im Voraus

        Returns:
            Liste kritischer und warnender Fristen
        """
        today = date.today()

        deadlines = await self.get_all_deadlines(
            db, company_id,
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=days_ahead),
            limit=100
        )

        # Nur kritische und warnende
        alerts = [
            d for d in deadlines
            if d.urgency in [DeadlineUrgency.CRITICAL, DeadlineUrgency.WARNING]
            and d.status == DeadlineStatus.PENDING
        ]

        return alerts

    # =========================================================================
    # Private Methoden fuer verschiedene Fristentypen
    # =========================================================================

    async def _get_skonto_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Skonto-Fristen aus InvoiceTracking."""
        from app.db.models import InvoiceTracking, Document, BusinessEntity

        now = utc_now()
        today = now.date()

        stmt = (
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_used == False,
                    InvoiceTracking.status.in_(["open", "sent"]),
                    InvoiceTracking.deleted_at.is_(None),
                    func.date(InvoiceTracking.skonto_deadline) >= start_date,
                    func.date(InvoiceTracking.skonto_deadline) <= end_date,
                )
            )
            .order_by(InvoiceTracking.skonto_deadline.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        deadlines: List[DeadlineItem] = []
        for invoice, document in rows:
            deadline_date = invoice.skonto_deadline
            days_remaining = (deadline_date.date() - today).days if deadline_date else 0

            # Dringlichkeit berechnen
            if days_remaining < 0:
                urgency = DeadlineUrgency.CRITICAL
                status = DeadlineStatus.EXPIRED
            elif days_remaining <= 1:
                urgency = DeadlineUrgency.CRITICAL
                status = DeadlineStatus.PENDING
            elif days_remaining <= 3:
                urgency = DeadlineUrgency.WARNING
                status = DeadlineStatus.PENDING
            elif days_remaining <= 7:
                urgency = DeadlineUrgency.UPCOMING
                status = DeadlineStatus.PENDING
            else:
                urgency = DeadlineUrgency.SCHEDULED
                status = DeadlineStatus.PENDING

            skonto_amount = Decimal(str(invoice.skonto_amount or 0))

            deadlines.append(DeadlineItem(
                id=f"skonto-{invoice.id}",
                category=DeadlineCategory.SKONTO,
                title=f"Skonto-Frist: {invoice.invoice_number or document.original_filename}",
                description=f"{invoice.skonto_percentage}% Skonto = {skonto_amount}EUR Ersparnis",
                deadline=deadline_date,
                urgency=urgency,
                status=status,
                days_until=days_remaining,
                document_id=document.id,
                invoice_id=invoice.id,
                amount=skonto_amount,
                currency=invoice.currency or "EUR",
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "skonto_percentage": invoice.skonto_percentage,
                    "original_amount": invoice.amount,
                },
            ))

        return deadlines

    async def _get_payment_deadlines_outgoing(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Zahlungsfristen fuer ausgehende Zahlungen (wir muessen zahlen)."""
        from app.db.models import InvoiceTracking, Document

        now = utc_now()
        today = now.date()

        # Lieferantenrechnungen / Eingangsrechnungen
        stmt = (
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.status.in_(["open", "sent"]),
                    InvoiceTracking.deleted_at.is_(None),
                    Document.document_type.in_(["supplier_invoice", "purchase_invoice"]),
                    func.date(InvoiceTracking.due_date) >= start_date,
                    func.date(InvoiceTracking.due_date) <= end_date,
                )
            )
            .order_by(InvoiceTracking.due_date.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        deadlines: List[DeadlineItem] = []
        for invoice, document in rows:
            deadline_date = invoice.due_date
            days_remaining = (deadline_date.date() - today).days if deadline_date else 0

            urgency = self._calculate_urgency(days_remaining)
            status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

            amount = Decimal(str(invoice.outstanding_amount or invoice.amount or 0))

            deadlines.append(DeadlineItem(
                id=f"payment-out-{invoice.id}",
                category=DeadlineCategory.PAYMENT_OUTGOING,
                title=f"Zahlung faellig: {invoice.invoice_number or document.original_filename}",
                description=f"Lieferantenrechnung - {amount}EUR ausstehend",
                deadline=deadline_date,
                urgency=urgency,
                status=status,
                days_until=days_remaining,
                document_id=document.id,
                invoice_id=invoice.id,
                amount=amount,
                currency=invoice.currency or "EUR",
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "document_type": document.document_type,
                },
            ))

        return deadlines

    async def _get_payment_deadlines_incoming(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Zahlungsfristen fuer eingehende Zahlungen (Kunden muessen zahlen)."""
        from app.db.models import InvoiceTracking, Document

        now = utc_now()
        today = now.date()

        # Kundenrechnungen / Ausgangsrechnungen
        stmt = (
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                    Document.document_type.in_(["invoice", "customer_invoice"]),
                    func.date(InvoiceTracking.due_date) >= start_date,
                    func.date(InvoiceTracking.due_date) <= end_date,
                )
            )
            .order_by(InvoiceTracking.due_date.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        deadlines: List[DeadlineItem] = []
        for invoice, document in rows:
            deadline_date = invoice.due_date
            days_remaining = (deadline_date.date() - today).days if deadline_date else 0

            urgency = self._calculate_urgency(days_remaining)
            status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

            amount = Decimal(str(invoice.outstanding_amount or invoice.amount or 0))

            deadlines.append(DeadlineItem(
                id=f"payment-in-{invoice.id}",
                category=DeadlineCategory.PAYMENT_INCOMING,
                title=f"Zahlungseingang erwartet: {invoice.invoice_number or document.original_filename}",
                description=f"Kundenrechnung - {amount}EUR ausstehend",
                deadline=deadline_date,
                urgency=urgency,
                status=status,
                days_until=days_remaining,
                document_id=document.id,
                invoice_id=invoice.id,
                amount=amount,
                currency=invoice.currency or "EUR",
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "dunning_level": invoice.dunning_level,
                },
            ))

        return deadlines

    async def _get_tax_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Steuertermine."""
        from app.db.models import Document

        now = utc_now()
        today = now.date()

        deadlines: List[DeadlineItem] = []

        # 1. Dokumente mit Einspruchsfristen (Steuerbescheide)
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type.in_(["tax_notice", "steuerbescheid"]),
                    Document.extracted_data.isnot(None),
                )
            )
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Einspruchsfrist
            einspruchsfrist_str = extracted.get("einspruchsfrist")
            if einspruchsfrist_str:
                try:
                    deadline_date = datetime.fromisoformat(einspruchsfrist_str.replace("Z", "+00:00"))
                    deadline_dt = deadline_date.date() if isinstance(deadline_date, datetime) else deadline_date

                    if start_date <= deadline_dt <= end_date:
                        days_remaining = (deadline_dt - today).days
                        urgency = self._calculate_urgency(days_remaining)
                        status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

                        amount = Decimal(str(extracted.get("nachzahlung", 0)))

                        deadlines.append(DeadlineItem(
                            id=f"tax-appeal-{doc.id}",
                            category=DeadlineCategory.TAX,
                            title=f"Einspruchsfrist: {doc.original_filename}",
                            description=f"Einspruchsfrist endet - Aktenzeichen: {extracted.get('aktenzeichen', 'N/A')}",
                            deadline=deadline_date,
                            urgency=urgency,
                            status=status,
                            days_until=days_remaining,
                            document_id=doc.id,
                            amount=amount if amount > 0 else None,
                            metadata={
                                "aktenzeichen": extracted.get("aktenzeichen"),
                                "steuerart": extracted.get("steuerart"),
                            },
                        ))
                except (ValueError, TypeError):
                    pass

            # Zahlungsfrist
            zahlungsfrist_str = extracted.get("zahlungsfrist")
            if zahlungsfrist_str:
                try:
                    deadline_date = datetime.fromisoformat(zahlungsfrist_str.replace("Z", "+00:00"))
                    deadline_dt = deadline_date.date() if isinstance(deadline_date, datetime) else deadline_date

                    if start_date <= deadline_dt <= end_date:
                        days_remaining = (deadline_dt - today).days
                        urgency = self._calculate_urgency(days_remaining)
                        status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

                        amount = Decimal(str(extracted.get("nachzahlung", 0)))

                        deadlines.append(DeadlineItem(
                            id=f"tax-payment-{doc.id}",
                            category=DeadlineCategory.TAX,
                            title=f"Steuerzahlung faellig: {doc.original_filename}",
                            description=f"Steuerzahlung {extracted.get('steuerart', '')} - {amount}EUR",
                            deadline=deadline_date,
                            urgency=urgency,
                            status=status,
                            days_until=days_remaining,
                            document_id=doc.id,
                            amount=amount if amount > 0 else None,
                            metadata={
                                "aktenzeichen": extracted.get("aktenzeichen"),
                                "steuerart": extracted.get("steuerart"),
                            },
                        ))
                except (ValueError, TypeError):
                    pass

        # 2. Standard-Steuertermine (wiederkehrend)
        for tax_deadline in self.STANDARD_TAX_DEADLINES:
            # Iteriere durch alle Monate im Zeitraum
            current = start_date.replace(day=1)
            while current <= end_date:
                # Pruefen ob dieser Monat relevant ist
                is_relevant = False
                if tax_deadline.get("monthly"):
                    is_relevant = True
                elif tax_deadline.get("quarterly") and current.month in tax_deadline.get("months", []):
                    is_relevant = True
                elif tax_deadline.get("annual") and current.month == tax_deadline.get("month", 1):
                    is_relevant = True

                if is_relevant:
                    try:
                        deadline_day = tax_deadline["day"]
                        from calendar import monthrange
                        _, last_day = monthrange(current.year, current.month)
                        deadline_day = min(deadline_day, last_day)
                        deadline_date = datetime(current.year, current.month, deadline_day, tzinfo=timezone.utc)
                        deadline_dt = deadline_date.date()

                        if start_date <= deadline_dt <= end_date:
                            days_remaining = (deadline_dt - today).days
                            urgency = self._calculate_urgency(days_remaining)
                            status = DeadlineStatus.COMPLETED if days_remaining < -14 else (
                                DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING
                            )

                            deadlines.append(DeadlineItem(
                                id=f"tax-recurring-{tax_deadline['name']}-{current.year}-{current.month}",
                                category=DeadlineCategory.TAX,
                                title=tax_deadline["name"],
                                description=f"Wiederkehrender Steuertermin - {current.strftime('%B %Y')}",
                                deadline=deadline_date,
                                urgency=urgency,
                                status=status,
                                days_until=days_remaining,
                                metadata={
                                    "recurring": True,
                                    "type": "monthly" if tax_deadline.get("monthly") else
                                           "quarterly" if tax_deadline.get("quarterly") else "annual",
                                },
                            ))
                    except (ValueError, TypeError):
                        pass

                # Naechster Monat
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)

        return deadlines

    async def _get_contract_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Vertragsfristen (Kuendigung, Verlaengerung)."""
        from app.db.models import Document

        now = utc_now()
        today = now.date()

        deadlines: List[DeadlineItem] = []

        # Dokumente mit Vertragsfristen
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type.in_(["contract", "vertrag", "subscription", "abo"]),
                    Document.extracted_data.isnot(None),
                )
            )
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Kuendigungsfrist
            kuendigungsfrist_str = extracted.get("kuendigungsfrist") or extracted.get("cancellation_deadline")
            if kuendigungsfrist_str:
                try:
                    deadline_date = datetime.fromisoformat(kuendigungsfrist_str.replace("Z", "+00:00"))
                    deadline_dt = deadline_date.date() if isinstance(deadline_date, datetime) else deadline_date

                    if start_date <= deadline_dt <= end_date:
                        days_remaining = (deadline_dt - today).days
                        urgency = self._calculate_urgency(days_remaining)
                        status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

                        deadlines.append(DeadlineItem(
                            id=f"contract-cancel-{doc.id}",
                            category=DeadlineCategory.CONTRACT,
                            title=f"Kuendigungsfrist: {doc.original_filename}",
                            description=f"Vertrag kuendbar bis {deadline_dt.strftime('%d.%m.%Y')}",
                            deadline=deadline_date,
                            urgency=urgency,
                            status=status,
                            days_until=days_remaining,
                            document_id=doc.id,
                            metadata={
                                "contract_type": extracted.get("vertrag_typ"),
                                "partner": extracted.get("vertragspartner"),
                            },
                        ))
                except (ValueError, TypeError):
                    pass

            # Vertragsende/Verlaengerung
            vertragsende_str = extracted.get("vertragsende") or extracted.get("contract_end")
            if vertragsende_str:
                try:
                    deadline_date = datetime.fromisoformat(vertragsende_str.replace("Z", "+00:00"))
                    deadline_dt = deadline_date.date() if isinstance(deadline_date, datetime) else deadline_date

                    if start_date <= deadline_dt <= end_date:
                        days_remaining = (deadline_dt - today).days
                        urgency = self._calculate_urgency(days_remaining)
                        status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

                        deadlines.append(DeadlineItem(
                            id=f"contract-end-{doc.id}",
                            category=DeadlineCategory.CONTRACT,
                            title=f"Vertragsende: {doc.original_filename}",
                            description=f"Vertrag endet am {deadline_dt.strftime('%d.%m.%Y')}",
                            deadline=deadline_date,
                            urgency=urgency,
                            status=status,
                            days_until=days_remaining,
                            document_id=doc.id,
                            metadata={
                                "contract_type": extracted.get("vertrag_typ"),
                                "partner": extracted.get("vertragspartner"),
                                "auto_renewal": extracted.get("auto_verlaengerung", False),
                            },
                        ))
                except (ValueError, TypeError):
                    pass

        return deadlines

    async def _get_dunning_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[DeadlineItem]:
        """Hole Mahnfristen."""
        from app.db.models import InvoiceTracking, Document

        now = utc_now()
        today = now.date()

        # Rechnungen mit Mahnstatus
        stmt = (
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status.in_(["overdue", "dunning"]),
                    InvoiceTracking.dunning_level >= 1,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            .order_by(InvoiceTracking.last_dunning_at.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        deadlines: List[DeadlineItem] = []

        # Standard-Mahnintervalle
        DUNNING_INTERVALS = {
            1: 14,  # 14 Tage nach 1. Mahnung
            2: 10,  # 10 Tage nach 2. Mahnung
            3: 7,   # 7 Tage nach 3. Mahnung
        }

        for invoice, document in rows:
            if invoice.last_dunning_at and invoice.dunning_level < 4:
                next_level = invoice.dunning_level + 1
                interval = DUNNING_INTERVALS.get(invoice.dunning_level, 7)

                next_dunning_date = invoice.last_dunning_at + timedelta(days=interval)
                deadline_dt = next_dunning_date.date() if isinstance(next_dunning_date, datetime) else next_dunning_date

                if start_date <= deadline_dt <= end_date:
                    days_remaining = (deadline_dt - today).days
                    urgency = self._calculate_urgency(days_remaining)
                    status = DeadlineStatus.EXPIRED if days_remaining < 0 else DeadlineStatus.PENDING

                    amount = Decimal(str(invoice.outstanding_amount or invoice.amount or 0))

                    deadlines.append(DeadlineItem(
                        id=f"dunning-{invoice.id}-{next_level}",
                        category=DeadlineCategory.DUNNING,
                        title=f"Mahnung #{next_level}: {invoice.invoice_number or document.original_filename}",
                        description=f"Naechste Mahnstufe faellig - {amount}EUR ausstehend",
                        deadline=next_dunning_date,
                        urgency=urgency,
                        status=status,
                        days_until=days_remaining,
                        document_id=document.id,
                        invoice_id=invoice.id,
                        amount=amount,
                        metadata={
                            "current_dunning_level": invoice.dunning_level,
                            "next_dunning_level": next_level,
                            "last_dunning_at": invoice.last_dunning_at.isoformat() if invoice.last_dunning_at else None,
                        },
                    ))

        return deadlines

    def _calculate_urgency(self, days_remaining: int) -> DeadlineUrgency:
        """Berechne Dringlichkeit basierend auf verbleibenden Tagen."""
        if days_remaining < 0 or days_remaining <= 1:
            return DeadlineUrgency.CRITICAL
        elif days_remaining <= 3:
            return DeadlineUrgency.WARNING
        elif days_remaining <= 7:
            return DeadlineUrgency.UPCOMING
        else:
            return DeadlineUrgency.SCHEDULED


# Singleton
calendar_service = CalendarService()


def get_calendar_service() -> CalendarService:
    """Factory-Funktion fuer CalendarService."""
    return calendar_service
