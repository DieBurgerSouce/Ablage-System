# -*- coding: utf-8 -*-
"""
Belegprüfung und Vollständigkeitskontrolle.

Prüft die Vollständigkeit von Buchhaltungsbelegen:
- Buchungen ohne Beleg
- Fehlende Monate in Rechnungssequenzen
- Lücken in Rechnungsnummern
- Plausibilitaetsprüfung (ungewoehnliche Betraege, Datumsinkonsistenzen)

Rechtliche Grundlage:
- GoBD (Grundsätze zur ordnungsmaessigen Führung von Buechern)
- § 146 AO (Ordnungsvorschriften für die Buchführung)
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    BankTransaction,
    BusinessEntity,
    Document,
    InvoiceTracking,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class UnmatchedBooking:
    """Bankbuchung ohne zugeordneten Beleg."""

    transaction_id: uuid.UUID
    booking_date: date
    amount: Decimal
    description: str
    counterparty: Optional[str]
    suggested_action: str  # German


@dataclass
class InvoiceGap:
    """Lücke in einer Rechnungsnummern-Sequenz."""

    vendor_name: str
    vendor_entity_id: Optional[uuid.UUID]
    last_number: str
    expected_next: str
    found_next: str
    gap_count: int


@dataclass
class MissingMonthlyInvoice:
    """Fehlende monatliche Rechnung."""

    vendor_name: str
    vendor_entity_id: Optional[uuid.UUID]
    expected_month: date
    expected_amount: Optional[Decimal]
    category: Optional[str]
    last_invoice_date: Optional[date]


@dataclass
class PlausibilityIssue:
    """Plausibilitaetsproblem bei einem Beleg."""

    document_id: uuid.UUID
    issue_type: str  # "unusual_amount", "duplicate_suspected", "round_number"
    description: str  # German
    severity: str  # "info", "warning", "error"
    amount: Optional[Decimal]
    average_amount: Optional[Decimal]
    deviation_percent: Optional[float]


@dataclass
class DateIssue:
    """Datumsinkonsistenz bei einem Beleg."""

    document_id: uuid.UUID
    issue_type: str  # "future_date", "wrong_period", "large_gap"
    description: str  # German
    document_date: date
    booking_date: Optional[date]
    gap_days: Optional[int]


@dataclass
class CompletenessReport:
    """Vollständiger Belegcheck-Report."""

    company_id: uuid.UUID
    period_start: date
    period_end: date
    overall_score: float  # 0-100
    generated_at: datetime
    summary: Dict[str, int]
    unmatched_bookings: List[UnmatchedBooking]
    invoice_gaps: List[InvoiceGap]
    missing_monthly: List[MissingMonthlyInvoice]
    plausibility_issues: List[PlausibilityIssue]
    date_issues: List[DateIssue]
    recommendations: List[str]  # German recommendations


# =============================================================================
# Service
# =============================================================================


class DocumentCompletenessService:
    """Belegprüfung und Vollständigkeitskontrolle.

    Prüft:
    - Buchungen ohne Beleg
    - Fehlende Monate in Rechnungssequenzen
    - Lücken in Rechnungsnummern
    - Plausibilitaetsprüfung (ungewoehnliche Betraege, Datumsinkonsistenzen)
    """

    # Schwellenwerte
    UNUSUAL_AMOUNT_DEVIATION = 3.0  # Standardabweichungen
    ROUND_NUMBER_THRESHOLD = Decimal("1000")
    MAX_BOOKING_GAP_DAYS = 30
    MIN_MONTHLY_OCCURRENCES = 3  # Min. Monate um als "monatlich" zu gelten

    async def check_bookings_without_receipts(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[UnmatchedBooking]:
        """Findet Bankbuchungen ohne zugeordneten Beleg.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            period_start: Beginn des Prüfzeitraums
            period_end: Ende des Prüfzeitraums

        Returns:
            Liste von Buchungen ohne Beleg
        """
        # BankTransaction hat kein company_id direkt.
        # Filtere über BankAccount -> user_id -> User -> company_id
        # oder verwende die matched_document_id == NULL Logik
        from app.db.models import BankAccount

        stmt = (
            select(BankTransaction)
            .join(
                BankAccount,
                BankTransaction.bank_account_id == BankAccount.id,
            )
            .join(
                Document,
                Document.owner_id == BankAccount.user_id,
            )
            .where(
                and_(
                    Document.company_id == company_id,
                    BankTransaction.matched_document_id.is_(None),
                    BankTransaction.reconciliation_status == "unmatched",
                    BankTransaction.booking_date >= datetime(
                        period_start.year, period_start.month, period_start.day,
                        tzinfo=timezone.utc,
                    ),
                    BankTransaction.booking_date <= datetime(
                        period_end.year, period_end.month, period_end.day,
                        23, 59, 59, tzinfo=timezone.utc,
                    ),
                )
            )
            .distinct(BankTransaction.id)
            .limit(500)
        )

        result = await db.execute(stmt)
        transactions = result.scalars().all()

        unmatched: List[UnmatchedBooking] = []
        for tx in transactions:
            unmatched.append(
                UnmatchedBooking(
                    transaction_id=tx.id,
                    booking_date=tx.booking_date.date()
                    if isinstance(tx.booking_date, datetime)
                    else tx.booking_date,
                    amount=Decimal(str(tx.amount)),
                    description=tx.reference_text or tx.booking_text or "",
                    counterparty=tx.counterparty_name,
                    suggested_action=self._suggest_action_for_unmatched(tx),
                )
            )

        logger.info(
            "bookings_without_receipts_checked",
            company_id=str(company_id),
            unmatched_count=len(unmatched),
        )

        return unmatched

    async def check_invoice_number_gaps(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        vendor_entity_id: Optional[uuid.UUID] = None,
        year: Optional[int] = None,
    ) -> List[InvoiceGap]:
        """Prüft Lücken in Rechnungsnummern-Sequenzen pro Lieferant.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            vendor_entity_id: Optional - nur für einen Lieferanten
            year: Optional - nur für ein Jahr

        Returns:
            Liste von Rechnungsnummern-Lücken
        """
        conditions = [
            InvoiceTracking.company_id == company_id,
            InvoiceTracking.invoice_number.isnot(None),
            InvoiceTracking.deleted_at.is_(None),
        ]

        if vendor_entity_id is not None:
            # Filter über Document -> business_entity_id
            conditions.append(Document.business_entity_id == vendor_entity_id)

        if year is not None:
            conditions.append(
                extract("year", InvoiceTracking.invoice_date) == year
            )

        stmt = (
            select(
                InvoiceTracking.invoice_number,
                InvoiceTracking.invoice_date,
                Document.business_entity_id,
                BusinessEntity.name.label("vendor_name"),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .outerjoin(
                BusinessEntity,
                Document.business_entity_id == BusinessEntity.id,
            )
            .where(and_(*conditions))
            .order_by(
                Document.business_entity_id,
                InvoiceTracking.invoice_number,
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        # Gruppiere nach Vendor
        vendor_invoices: Dict[
            Optional[uuid.UUID], List[Tuple[str, str]]
        ] = defaultdict(list)
        vendor_names: Dict[Optional[uuid.UUID], str] = {}

        for row in rows:
            vid = row.business_entity_id
            vendor_invoices[vid].append(
                (row.invoice_number, row.vendor_name or "Unbekannter Lieferant")
            )
            if row.vendor_name:
                vendor_names[vid] = row.vendor_name

        gaps: List[InvoiceGap] = []

        for vid, invoice_list in vendor_invoices.items():
            vendor_name = vendor_names.get(vid, "Unbekannter Lieferant")
            numbers = [inv[0] for inv in invoice_list]
            detected_gaps = self._detect_number_gaps(numbers)

            for gap in detected_gaps:
                gaps.append(
                    InvoiceGap(
                        vendor_name=vendor_name,
                        vendor_entity_id=vid,
                        last_number=gap["last"],
                        expected_next=gap["expected"],
                        found_next=gap["found"],
                        gap_count=gap["gap_count"],
                    )
                )

        logger.info(
            "invoice_number_gaps_checked",
            company_id=str(company_id),
            gap_count=len(gaps),
        )

        return gaps

    async def check_missing_monthly_invoices(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        year: int,
    ) -> List[MissingMonthlyInvoice]:
        """Findet fehlende monatliche Rechnungen (z.B. Miete, Strom, Telekom).

        Erkennt wiederkehrende Rechnungsmuster und meldet fehlende Monate.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            year: Prüf-Jahr

        Returns:
            Liste fehlender monatlicher Rechnungen
        """
        # Lade alle Rechnungen des Jahres gruppiert nach Vendor
        stmt = (
            select(
                Document.business_entity_id,
                BusinessEntity.name.label("vendor_name"),
                extract("month", InvoiceTracking.invoice_date).label("month"),
                func.avg(InvoiceTracking.amount).label("avg_amount"),
                func.count().label("invoice_count"),
                func.max(InvoiceTracking.invoice_date).label("last_date"),
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .outerjoin(
                BusinessEntity,
                Document.business_entity_id == BusinessEntity.id,
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.invoice_date.isnot(None),
                    extract("year", InvoiceTracking.invoice_date) == year,
                    Document.business_entity_id.isnot(None),
                )
            )
            .group_by(
                Document.business_entity_id,
                BusinessEntity.name,
                extract("month", InvoiceTracking.invoice_date),
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        # Gruppiere nach Vendor
        vendor_months: Dict[
            uuid.UUID, Dict[str, List[int]]
        ] = defaultdict(lambda: {"months": [], "amounts": [], "names": []})

        for row in rows:
            if row.business_entity_id is None:
                continue
            vid = row.business_entity_id
            month_val = int(row.month)
            vendor_months[vid]["months"].append(month_val)
            vendor_months[vid]["amounts"].append(float(row.avg_amount or 0))
            if row.vendor_name:
                vendor_months[vid]["names"].append(row.vendor_name)

        missing: List[MissingMonthlyInvoice] = []

        # Aktueller Monat als Obergrenze
        current_date = utc_now().date()
        max_month = 12 if year < current_date.year else current_date.month

        for vid, data in vendor_months.items():
            months_present = set(data["months"])
            # Nur prüfen wenn Lieferant in genug Monaten vorkommt
            if len(months_present) < self.MIN_MONTHLY_OCCURRENCES:
                continue

            vendor_name = data["names"][0] if data["names"] else "Unbekannt"
            avg_amount = (
                Decimal(str(round(sum(data["amounts"]) / len(data["amounts"]), 2)))
                if data["amounts"]
                else None
            )

            # Finde fehlende Monate
            expected_months = set(range(1, max_month + 1))
            missing_months = expected_months - months_present

            for m in sorted(missing_months):
                last_invoice = None
                # Finde den letzten Monat vor dem fehlenden
                earlier_months = [
                    mo for mo in sorted(months_present) if mo < m
                ]
                if earlier_months:
                    last_month_num = earlier_months[-1]
                    last_invoice = date(year, last_month_num, 1)

                missing.append(
                    MissingMonthlyInvoice(
                        vendor_name=vendor_name,
                        vendor_entity_id=vid,
                        expected_month=date(year, m, 1),
                        expected_amount=avg_amount,
                        category=None,
                        last_invoice_date=last_invoice,
                    )
                )

        logger.info(
            "missing_monthly_invoices_checked",
            company_id=str(company_id),
            year=year,
            missing_count=len(missing),
        )

        return missing

    async def check_amount_plausibility(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[PlausibilityIssue]:
        """Prüft Plausibilitaet von Betraegen.

        Erkennt:
        - Betraege deutlich über Durchschnitt pro Lieferant
        - Runde Betraege (Schätzungen)
        - Doppelte Betraege am gleichen Tag vom gleichen Lieferanten

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            period_start: Beginn des Prüfzeitraums
            period_end: Ende des Prüfzeitraums

        Returns:
            Liste von Plausibilitaetsproblemen
        """
        issues: List[PlausibilityIssue] = []

        # 1. Lade Rechnungen im Zeitraum
        stmt = (
            select(
                InvoiceTracking.id,
                InvoiceTracking.document_id,
                InvoiceTracking.amount,
                InvoiceTracking.invoice_date,
                Document.business_entity_id,
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.invoice_date.isnot(None),
                    InvoiceTracking.invoice_date >= datetime(
                        period_start.year, period_start.month, period_start.day,
                        tzinfo=timezone.utc,
                    ),
                    InvoiceTracking.invoice_date <= datetime(
                        period_end.year, period_end.month, period_end.day,
                        23, 59, 59, tzinfo=timezone.utc,
                    ),
                )
            )
        )

        result = await db.execute(stmt)
        invoices = result.all()

        # 2. Berechne Durchschnitt und Standardabweichung pro Vendor
        vendor_amounts: Dict[
            Optional[uuid.UUID], List[float]
        ] = defaultdict(list)
        for inv in invoices:
            vendor_amounts[inv.business_entity_id].append(float(inv.amount or 0))

        vendor_stats: Dict[Optional[uuid.UUID], Tuple[float, float]] = {}
        for vid, amounts in vendor_amounts.items():
            if len(amounts) < 2:
                continue
            avg = sum(amounts) / len(amounts)
            variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
            stddev = variance ** 0.5
            vendor_stats[vid] = (avg, stddev)

        # 3. Prüfe jede Rechnung
        # Gruppiere nach (vendor, date, amount) für Duplikat-Erkennung
        seen_combos: Dict[
            Tuple[Optional[uuid.UUID], str, float], List[uuid.UUID]
        ] = defaultdict(list)

        for inv in invoices:
            amount_val = float(inv.amount or 0)
            doc_id = inv.document_id

            # Runde Betraege prüfen
            if amount_val > 0:
                dec_amount = Decimal(str(amount_val))
                if (
                    dec_amount >= self.ROUND_NUMBER_THRESHOLD
                    and dec_amount == dec_amount.quantize(Decimal("1000"))
                ):
                    issues.append(
                        PlausibilityIssue(
                            document_id=doc_id,
                            issue_type="round_number",
                            description=(
                                f"Runder Betrag ({amount_val:.2f} EUR) - "
                                f"möglicherweise Schätzung"
                            ),
                            severity="info",
                            amount=dec_amount,
                            average_amount=None,
                            deviation_percent=None,
                        )
                    )

            # Ungewoehnlicher Betrag prüfen
            vid = inv.business_entity_id
            if vid in vendor_stats:
                avg, stddev = vendor_stats[vid]
                if stddev > 0 and amount_val > 0:
                    deviation = abs(amount_val - avg) / stddev
                    if deviation > self.UNUSUAL_AMOUNT_DEVIATION:
                        dev_pct = ((amount_val - avg) / avg * 100) if avg > 0 else 0
                        issues.append(
                            PlausibilityIssue(
                                document_id=doc_id,
                                issue_type="unusual_amount",
                                description=(
                                    f"Ungewoehnlicher Betrag ({amount_val:.2f} EUR) - "
                                    f"{abs(dev_pct):.0f}% über Durchschnitt "
                                    f"({avg:.2f} EUR)"
                                ),
                                severity="warning",
                                amount=Decimal(str(amount_val)),
                                average_amount=Decimal(str(round(avg, 2))),
                                deviation_percent=round(dev_pct, 1),
                            )
                        )

            # Duplikat-Erkennung (gleicher Vendor + Datum + Betrag)
            inv_date_str = ""
            if inv.invoice_date:
                inv_date_obj = (
                    inv.invoice_date.date()
                    if isinstance(inv.invoice_date, datetime)
                    else inv.invoice_date
                )
                inv_date_str = inv_date_obj.isoformat()

            combo_key = (vid, inv_date_str, amount_val)
            seen_combos[combo_key].append(doc_id)

        # Duplikate melden
        for combo_key, doc_ids in seen_combos.items():
            if len(doc_ids) > 1:
                for doc_id in doc_ids:
                    issues.append(
                        PlausibilityIssue(
                            document_id=doc_id,
                            issue_type="duplicate_suspected",
                            description=(
                                f"Mögliches Duplikat: {len(doc_ids)} Rechnungen "
                                f"mit gleichem Betrag ({combo_key[2]:.2f} EUR) "
                                f"am gleichen Tag"
                            ),
                            severity="warning",
                            amount=Decimal(str(combo_key[2])),
                            average_amount=None,
                            deviation_percent=None,
                        )
                    )

        logger.info(
            "amount_plausibility_checked",
            company_id=str(company_id),
            issue_count=len(issues),
        )

        return issues

    async def check_date_consistency(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[DateIssue]:
        """Prüft Datumskonsistenz.

        Erkennt:
        - Rechnungsdatum in der Zukunft
        - Grosser Abstand zwischen Rechnungsdatum und Buchungsdatum
        - Dokumente im falschen Zeitraum

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            period_start: Beginn des Prüfzeitraums
            period_end: Ende des Prüfzeitraums

        Returns:
            Liste von Datumsproblemen
        """
        issues: List[DateIssue] = []
        today = utc_now().date()

        # Lade Rechnungen mit optionalen Bank-Transaktionen
        stmt = (
            select(
                InvoiceTracking.document_id,
                InvoiceTracking.invoice_date,
                BankTransaction.booking_date.label("tx_booking_date"),
            )
            .outerjoin(
                BankTransaction,
                and_(
                    BankTransaction.matched_document_id
                    == InvoiceTracking.document_id,
                ),
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                    InvoiceTracking.invoice_date.isnot(None),
                    InvoiceTracking.invoice_date >= datetime(
                        period_start.year, period_start.month, period_start.day,
                        tzinfo=timezone.utc,
                    ),
                    InvoiceTracking.invoice_date <= datetime(
                        period_end.year, period_end.month, period_end.day,
                        23, 59, 59, tzinfo=timezone.utc,
                    ),
                )
            )
        )

        result = await db.execute(stmt)
        rows = result.all()

        for row in rows:
            doc_id = row.document_id
            inv_date = (
                row.invoice_date.date()
                if isinstance(row.invoice_date, datetime)
                else row.invoice_date
            )

            # Zukunftsdatum prüfen
            if inv_date > today:
                issues.append(
                    DateIssue(
                        document_id=doc_id,
                        issue_type="future_date",
                        description=(
                            f"Rechnungsdatum ({inv_date.isoformat()}) liegt "
                            f"in der Zukunft"
                        ),
                        document_date=inv_date,
                        booking_date=None,
                        gap_days=None,
                    )
                )

            # Buchungsdatum-Abweichung prüfen
            if row.tx_booking_date is not None:
                booking_dt = (
                    row.tx_booking_date.date()
                    if isinstance(row.tx_booking_date, datetime)
                    else row.tx_booking_date
                )
                gap = abs((booking_dt - inv_date).days)
                if gap > self.MAX_BOOKING_GAP_DAYS:
                    issues.append(
                        DateIssue(
                            document_id=doc_id,
                            issue_type="large_gap",
                            description=(
                                f"Grosser Abstand ({gap} Tage) zwischen "
                                f"Rechnungsdatum ({inv_date.isoformat()}) "
                                f"und Buchungsdatum ({booking_dt.isoformat()})"
                            ),
                            document_date=inv_date,
                            booking_date=booking_dt,
                            gap_days=gap,
                        )
                    )

            # Falscher Zeitraum prüfen (Rechnung ausserhalb des
            # Buchungsjahres)
            if inv_date < period_start or inv_date > period_end:
                issues.append(
                    DateIssue(
                        document_id=doc_id,
                        issue_type="wrong_period",
                        description=(
                            f"Rechnungsdatum ({inv_date.isoformat()}) "
                            f"ausserhalb des Prüfzeitraums "
                            f"({period_start.isoformat()} bis "
                            f"{period_end.isoformat()})"
                        ),
                        document_date=inv_date,
                        booking_date=None,
                        gap_days=None,
                    )
                )

        logger.info(
            "date_consistency_checked",
            company_id=str(company_id),
            issue_count=len(issues),
        )

        return issues

    async def generate_completeness_report(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        year: int,
        quarter: Optional[int] = None,
        month: Optional[int] = None,
    ) -> CompletenessReport:
        """Generiert vollständigen Belegcheck-Report.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            year: Berichtsjahr
            quarter: Optional - Quartal (1-4)
            month: Optional - Monat (1-12)

        Returns:
            Vollständiger Belegcheck-Report mit Score und Ergebnissen
        """
        period_start, period_end = self._calculate_period(year, quarter, month)

        # Führe alle Checks aus
        unmatched = await self.check_bookings_without_receipts(
            db, company_id, period_start, period_end
        )
        invoice_gaps = await self.check_invoice_number_gaps(
            db, company_id, year=year
        )
        missing_monthly = await self.check_missing_monthly_invoices(
            db, company_id, year
        )
        plausibility = await self.check_amount_plausibility(
            db, company_id, period_start, period_end
        )
        date_issues = await self.check_date_consistency(
            db, company_id, period_start, period_end
        )

        # Berechne Score
        score = self._calculate_score(
            unmatched, invoice_gaps, missing_monthly, plausibility, date_issues
        )

        # Generiere Empfehlungen
        recommendations = self._generate_recommendations(
            unmatched, invoice_gaps, missing_monthly, plausibility, date_issues
        )

        summary: Dict[str, int] = {
            "unmatched_bookings": len(unmatched),
            "invoice_gaps": len(invoice_gaps),
            "missing_monthly": len(missing_monthly),
            "plausibility_issues": len(plausibility),
            "date_issues": len(date_issues),
        }

        report = CompletenessReport(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            overall_score=score,
            generated_at=utc_now(),
            summary=summary,
            unmatched_bookings=unmatched,
            invoice_gaps=invoice_gaps,
            missing_monthly=missing_monthly,
            plausibility_issues=plausibility,
            date_issues=date_issues,
            recommendations=recommendations,
        )

        logger.info(
            "completeness_report_generated",
            company_id=str(company_id),
            year=year,
            score=score,
            findings=sum(summary.values()),
        )

        return report

    async def get_completeness_score(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> float:
        """Berechnet Vollständigkeits-Score (0-100).

        Schnelle Variante ohne vollständigen Report.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID (Multi-Tenant)
            period_start: Beginn des Prüfzeitraums
            period_end: Ende des Prüfzeitraums

        Returns:
            Score von 0 bis 100
        """
        # Zaehle unmatched Buchungen
        from app.db.models import BankAccount

        unmatched_stmt = (
            select(func.count())
            .select_from(BankTransaction)
            .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .join(Document, Document.owner_id == BankAccount.user_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    BankTransaction.matched_document_id.is_(None),
                    BankTransaction.reconciliation_status == "unmatched",
                    BankTransaction.booking_date >= datetime(
                        period_start.year, period_start.month, period_start.day,
                        tzinfo=timezone.utc,
                    ),
                    BankTransaction.booking_date <= datetime(
                        period_end.year, period_end.month, period_end.day,
                        23, 59, 59, tzinfo=timezone.utc,
                    ),
                )
            )
        )
        unmatched_result = await db.execute(unmatched_stmt)
        unmatched_count = unmatched_result.scalar() or 0

        # Zaehle Gesamt-Buchungen im Zeitraum
        total_stmt = (
            select(func.count())
            .select_from(BankTransaction)
            .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .join(Document, Document.owner_id == BankAccount.user_id)
            .where(
                and_(
                    Document.company_id == company_id,
                    BankTransaction.booking_date >= datetime(
                        period_start.year, period_start.month, period_start.day,
                        tzinfo=timezone.utc,
                    ),
                    BankTransaction.booking_date <= datetime(
                        period_end.year, period_end.month, period_end.day,
                        23, 59, 59, tzinfo=timezone.utc,
                    ),
                )
            )
        )
        total_result = await db.execute(total_stmt)
        total_count = total_result.scalar() or 0

        if total_count == 0:
            return 100.0

        match_rate = (total_count - unmatched_count) / total_count
        score = round(match_rate * 100, 1)

        logger.info(
            "completeness_score_calculated",
            company_id=str(company_id),
            score=score,
            matched=total_count - unmatched_count,
            total=total_count,
        )

        return score

    # =========================================================================
    # Helper-Methoden
    # =========================================================================

    def _suggest_action_for_unmatched(
        self, tx: BankTransaction
    ) -> str:
        """Schlaegt eine Aktion für eine unzugeordnete Buchung vor."""
        amount = float(tx.amount or 0)
        if amount < 0:
            return "Beleg für Ausgabe suchen und zuordnen"
        if amount > 0:
            return "Zahlungseingang prüfen und Rechnung zuordnen"
        return "Buchung mit Betrag 0 prüfen"

    def _detect_number_gaps(
        self, numbers: List[str]
    ) -> List[Dict[str, str]]:
        """Erkennt Lücken in Nummernsequenzen.

        Versucht numerische Suffixe zu extrahieren und Lücken zu finden.
        """
        gaps: List[Dict[str, str]] = []

        # Extrahiere numerische Suffixe
        parsed: List[Tuple[str, int, str]] = []
        for num in numbers:
            # Versuche die letzte Ziffernfolge zu extrahieren
            match = re.search(r"(\d+)\s*$", num)
            if match:
                numeric_part = int(match.group(1))
                prefix = num[: match.start()]
                parsed.append((prefix, numeric_part, num))

        if len(parsed) < 2:
            return gaps

        # Gruppiere nach Prefix
        prefix_groups: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
        for prefix, num_val, original in parsed:
            prefix_groups[prefix].append((num_val, original))

        for prefix, nums_and_originals in prefix_groups.items():
            sorted_nums = sorted(nums_and_originals, key=lambda x: x[0])

            for i in range(len(sorted_nums) - 1):
                current_num, current_orig = sorted_nums[i]
                next_num, next_orig = sorted_nums[i + 1]
                expected_next = current_num + 1

                if next_num > expected_next:
                    gap_count = next_num - expected_next
                    gaps.append(
                        {
                            "last": current_orig,
                            "expected": f"{prefix}{expected_next}",
                            "found": next_orig,
                            "gap_count": gap_count,
                        }
                    )

        return gaps

    def _calculate_period(
        self, year: int, quarter: Optional[int], month: Optional[int]
    ) -> Tuple[date, date]:
        """Berechnet Start- und End-Datum für den Prüfzeitraum."""
        if month is not None:
            start = date(year, month, 1)
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1)
                # Tag vor dem nächsten Monat
                from datetime import timedelta

                end = end - timedelta(days=1)
            return start, end

        if quarter is not None:
            quarter_starts = {1: 1, 2: 4, 3: 7, 4: 10}
            quarter_ends = {1: 3, 2: 6, 3: 9, 4: 12}
            start_month = quarter_starts[quarter]
            end_month = quarter_ends[quarter]
            start = date(year, start_month, 1)
            if end_month == 12:
                end = date(year, 12, 31)
            else:
                from datetime import timedelta

                end = date(year, end_month + 1, 1) - timedelta(days=1)
            return start, end

        return date(year, 1, 1), date(year, 12, 31)

    def _calculate_score(
        self,
        unmatched: List[UnmatchedBooking],
        gaps: List[InvoiceGap],
        missing: List[MissingMonthlyInvoice],
        plausibility: List[PlausibilityIssue],
        date_issues: List[DateIssue],
    ) -> float:
        """Berechnet den Vollständigkeits-Score.

        Gewichtung:
        - Unmatched Buchungen: -3 Punkte pro Stück (max -30)
        - Rechnungsnummern-Lücken: -5 Punkte pro Stück (max -20)
        - Fehlende Monatsrechnungen: -2 Punkte pro Stück (max -15)
        - Plausibilitaetsprobleme (warning/error): -2 Punkte pro Stück (max -15)
        - Datumsprobleme: -2 Punkte pro Stück (max -20)
        """
        score = 100.0

        score -= min(30, len(unmatched) * 3)
        score -= min(20, len(gaps) * 5)
        score -= min(15, len(missing) * 2)

        warning_issues = [
            i for i in plausibility if i.severity in ("warning", "error")
        ]
        score -= min(15, len(warning_issues) * 2)

        score -= min(20, len(date_issues) * 2)

        return max(0.0, round(score, 1))

    def _generate_recommendations(
        self,
        unmatched: List[UnmatchedBooking],
        gaps: List[InvoiceGap],
        missing: List[MissingMonthlyInvoice],
        plausibility: List[PlausibilityIssue],
        date_issues: List[DateIssue],
    ) -> List[str]:
        """Generiert deutsche Handlungsempfehlungen."""
        recommendations: List[str] = []

        if unmatched:
            recommendations.append(
                f"{len(unmatched)} Bankbuchungen haben keinen zugeordneten Beleg. "
                f"Bitte prüfen Sie diese Buchungen und ordnen Sie die "
                f"entsprechenden Belege zu."
            )

        if gaps:
            recommendations.append(
                f"{len(gaps)} Lücken in Rechnungsnummern-Sequenzen gefunden. "
                f"Bitte klaren Sie mit den Lieferanten, ob fehlende "
                f"Rechnungen existieren."
            )

        if missing:
            vendors = set(m.vendor_name for m in missing)
            recommendations.append(
                f"Für {len(vendors)} Lieferanten fehlen monatliche Rechnungen. "
                f"Prüfen Sie, ob wiederkehrende Rechnungen eingegangen sind."
            )

        duplicates = [
            i for i in plausibility if i.issue_type == "duplicate_suspected"
        ]
        if duplicates:
            recommendations.append(
                f"{len(duplicates)} mögliche Duplikat-Rechnungen erkannt. "
                f"Bitte prüfen Sie, ob doppelte Zahlungen vorliegen."
            )

        unusual = [
            i for i in plausibility if i.issue_type == "unusual_amount"
        ]
        if unusual:
            recommendations.append(
                f"{len(unusual)} Rechnungen mit ungewoehnlich hohen Betraegen. "
                f"Bitte prüfen Sie die Plausibilitaet dieser Betraege."
            )

        future_dates = [
            i for i in date_issues if i.issue_type == "future_date"
        ]
        if future_dates:
            recommendations.append(
                f"{len(future_dates)} Rechnungen mit Datum in der Zukunft. "
                f"Bitte korrigieren Sie die Rechnungsdaten."
            )

        large_gaps = [
            i for i in date_issues if i.issue_type == "large_gap"
        ]
        if large_gaps:
            recommendations.append(
                f"{len(large_gaps)} Rechnungen mit grossem Abstand zwischen "
                f"Rechnungs- und Buchungsdatum. Prüfen Sie die zeitnahe "
                f"Erfassung."
            )

        if not recommendations:
            recommendations.append(
                "Keine Auffälligkeiten gefunden. "
                "Die Belegvollständigkeit ist gut."
            )

        return recommendations


# Singleton-Instanz
document_completeness_service = DocumentCompletenessService()
