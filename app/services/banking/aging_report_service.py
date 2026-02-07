# -*- coding: utf-8 -*-
"""Aging Report Service.

Erstellt Alterungsberichte fuer:
- Forderungen (Accounts Receivable)
- Verbindlichkeiten (Accounts Payable)

Altersklassen:
- Aktuell (nicht faellig)
- 1-30 Tage ueberfaellig
- 31-60 Tage ueberfaellig
- 61-90 Tage ueberfaellig
- 90+ Tage ueberfaellig
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Dict, List, Tuple, Union
from uuid import UUID

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]
import structlog

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document

logger = structlog.get_logger(__name__)


class AgingBucket(str, Enum):
    """Altersklassen."""
    CURRENT = "current"      # Nicht faellig
    DAYS_1_30 = "1-30"       # 1-30 Tage ueberfaellig
    DAYS_31_60 = "31-60"     # 31-60 Tage ueberfaellig
    DAYS_61_90 = "61-90"     # 61-90 Tage ueberfaellig
    DAYS_90_PLUS = "90+"     # Mehr als 90 Tage


class ReportType(str, Enum):
    """Berichtstyp."""
    RECEIVABLES = "receivables"  # Forderungen
    PAYABLES = "payables"        # Verbindlichkeiten


@dataclass
class AgingLineItem:
    """Einzelne Position im Aging Report."""
    document_id: UUID
    invoice_number: Optional[str]
    counterparty: Optional[str]  # Debitor oder Kreditor
    invoice_date: Optional[date]
    due_date: Optional[date]
    amount: Decimal
    bucket: AgingBucket
    days_overdue: int
    document_type: str


@dataclass
class AgingBucketSummary:
    """Zusammenfassung einer Altersklasse."""
    bucket: AgingBucket
    count: int = 0
    amount: Decimal = Decimal("0.00")
    percentage: float = 0.0


@dataclass
class AgingReport:
    """Vollstaendiger Aging Report."""
    report_type: ReportType
    generated_at: datetime
    as_of_date: date

    # Zusammenfassungen
    total_count: int = 0
    total_amount: Decimal = Decimal("0.00")
    total_overdue: Decimal = Decimal("0.00")

    # Buckets
    buckets: List[AgingBucketSummary] = field(default_factory=list)

    # Details
    line_items: List[AgingLineItem] = field(default_factory=list)

    # Kennzahlen
    average_days_overdue: float = 0.0
    weighted_average_age: float = 0.0
    dso: float = 0.0  # Days Sales Outstanding


class AgingReportService:
    """Service fuer Aging Reports."""

    # Bucket-Grenzen (Tage ueberfaellig)
    BUCKET_RANGES = {
        AgingBucket.CURRENT: (None, 0),
        AgingBucket.DAYS_1_30: (1, 30),
        AgingBucket.DAYS_31_60: (31, 60),
        AgingBucket.DAYS_61_90: (61, 90),
        AgingBucket.DAYS_90_PLUS: (91, None),
    }

    async def get_receivables_aging(
        self,
        db: AsyncSession,
        user_id: UUID,
        as_of_date: Optional[date] = None,
        include_details: bool = True,
        counterparty: Optional[str] = None,
    ) -> AgingReport:
        """Erstelle Forderungs-Aging-Report.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            as_of_date: Stichtag (Standard: heute)
            include_details: Einzelpositionen einbeziehen?
            counterparty: Optional - nur fuer bestimmten Debitor

        Returns:
            AgingReport
        """
        return await self._generate_report(
            db=db,
            user_id=user_id,
            report_type=ReportType.RECEIVABLES,
            document_types=["invoice"],
            as_of_date=as_of_date or date.today(),
            include_details=include_details,
            counterparty=counterparty,
        )

    async def get_payables_aging(
        self,
        db: AsyncSession,
        user_id: UUID,
        as_of_date: Optional[date] = None,
        include_details: bool = True,
        counterparty: Optional[str] = None,
    ) -> AgingReport:
        """Erstelle Verbindlichkeiten-Aging-Report.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            as_of_date: Stichtag (Standard: heute)
            include_details: Einzelpositionen einbeziehen?
            counterparty: Optional - nur fuer bestimmten Kreditor

        Returns:
            AgingReport
        """
        return await self._generate_report(
            db=db,
            user_id=user_id,
            report_type=ReportType.PAYABLES,
            document_types=["supplier_invoice", "purchase_order"],
            as_of_date=as_of_date or date.today(),
            include_details=include_details,
            counterparty=counterparty,
        )

    async def get_aging_summary(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> JSONDict:
        """Hole kombinierte Aging-Zusammenfassung.

        Returns:
            Dictionary mit Forderungen und Verbindlichkeiten
        """
        receivables = await self.get_receivables_aging(
            db, user_id, include_details=False
        )
        payables = await self.get_payables_aging(
            db, user_id, include_details=False
        )

        return {
            "generated_at": utc_now().isoformat(),
            "receivables": self._report_to_dict(receivables),
            "payables": self._report_to_dict(payables),
            "net_position": {
                "total": float(receivables.total_amount - payables.total_amount),
                "overdue": float(receivables.total_overdue - payables.total_overdue),
            },
        }

    async def get_top_debtors(
        self,
        db: AsyncSession,
        user_id: UUID,
        limit: int = 10,
    ) -> List[JSONDict]:
        """Hole Top-Schuldner (hoechste Forderungen).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            limit: Max. Anzahl

        Returns:
            Liste der groessten Schuldner
        """
        report = await self.get_receivables_aging(
            db, user_id, include_details=True
        )

        # Nach Counterparty gruppieren
        by_counterparty: Dict[str, JSONDict] = {}

        for item in report.line_items:
            name = item.counterparty or "Unbekannt"
            if name not in by_counterparty:
                by_counterparty[name] = {
                    "name": name,
                    "total_amount": Decimal("0.00"),
                    "overdue_amount": Decimal("0.00"),
                    "invoice_count": 0,
                    "oldest_invoice_days": 0,
                }

            entry = by_counterparty[name]
            entry["total_amount"] += item.amount
            entry["invoice_count"] += 1

            if item.days_overdue > 0:
                entry["overdue_amount"] += item.amount

            if item.days_overdue > entry["oldest_invoice_days"]:
                entry["oldest_invoice_days"] = item.days_overdue

        # Sortieren und limitieren
        sorted_debtors = sorted(
            by_counterparty.values(),
            key=lambda x: x["total_amount"],
            reverse=True
        )[:limit]

        # Zu JSON-serialisierbarem Format konvertieren
        return [
            {
                "name": d["name"],
                "total_amount": float(d["total_amount"]),
                "overdue_amount": float(d["overdue_amount"]),
                "invoice_count": d["invoice_count"],
                "oldest_invoice_days": d["oldest_invoice_days"],
            }
            for d in sorted_debtors
        ]

    async def get_top_creditors(
        self,
        db: AsyncSession,
        user_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Hole Top-Glaeubiger (hoechste Verbindlichkeiten).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            limit: Max. Anzahl

        Returns:
            Liste der groessten Glaeubiger
        """
        report = await self.get_payables_aging(
            db, user_id, include_details=True
        )

        # Nach Counterparty gruppieren
        by_counterparty: Dict[str, JSONDict] = {}

        for item in report.line_items:
            name = item.counterparty or "Unbekannt"
            if name not in by_counterparty:
                by_counterparty[name] = {
                    "name": name,
                    "total_amount": Decimal("0.00"),
                    "overdue_amount": Decimal("0.00"),
                    "invoice_count": 0,
                    "oldest_invoice_days": 0,
                }

            entry = by_counterparty[name]
            entry["total_amount"] += item.amount
            entry["invoice_count"] += 1

            if item.days_overdue > 0:
                entry["overdue_amount"] += item.amount

            if item.days_overdue > entry["oldest_invoice_days"]:
                entry["oldest_invoice_days"] = item.days_overdue

        # Sortieren und limitieren
        sorted_creditors = sorted(
            by_counterparty.values(),
            key=lambda x: x["total_amount"],
            reverse=True
        )[:limit]

        return [
            {
                "name": c["name"],
                "total_amount": float(c["total_amount"]),
                "overdue_amount": float(c["overdue_amount"]),
                "invoice_count": c["invoice_count"],
                "oldest_invoice_days": c["oldest_invoice_days"],
            }
            for c in sorted_creditors
        ]

    async def calculate_dso(
        self,
        db: AsyncSession,
        user_id: UUID,
        period_days: int = 90,
    ) -> Dict[str, Any]:
        """Berechne Days Sales Outstanding (DSO).

        DSO = (Forderungen / Umsatz) * Periode

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            period_days: Betrachtungszeitraum

        Returns:
            Dictionary mit DSO-Kennzahlen
        """
        today = date.today()
        period_start = today - timedelta(days=period_days)

        # Aktuelle Forderungen
        receivables = await self.get_receivables_aging(
            db, user_id, include_details=False
        )

        # Umsatz im Zeitraum (aus bezahlten Rechnungen)
        # Vereinfachte Implementierung - in Produktion aus Buchhaltung
        revenue_query = select(Document).where(
            and_(
                Document.owner_id == user_id,
                Document.document_type == "invoice",
                Document.deleted_at.is_(None),
                Document.created_at >= period_start,
            )
        )

        result = await db.execute(revenue_query)
        documents = result.scalars().all()

        total_revenue = Decimal("0.00")
        for doc in documents:
            extracted = doc.extracted_data or {}
            if extracted.get("payment_status") == "paid":
                amount = extracted.get("total_amount") or extracted.get("amount")
                if amount:
                    try:
                        total_revenue += Decimal(str(amount))
                    except (ValueError, TypeError, InvalidOperation) as e:
                        logger.debug("dso_calculation_invalid_amount", error_type=type(e).__name__, amount_value=str(amount))

        # DSO berechnen
        if total_revenue > 0:
            dso = (receivables.total_amount / total_revenue) * period_days
        else:
            dso = Decimal("0")

        return {
            "dso": float(dso),
            "period_days": period_days,
            "receivables": float(receivables.total_amount),
            "revenue": float(total_revenue),
            "interpretation": self._interpret_dso(float(dso)),
        }

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _generate_report(
        self,
        db: AsyncSession,
        user_id: UUID,
        report_type: ReportType,
        document_types: List[str],
        as_of_date: date,
        include_details: bool,
        counterparty: Optional[str],
    ) -> AgingReport:
        """Generiere Aging Report."""
        report = AgingReport(
            report_type=report_type,
            generated_at=utc_now(),
            as_of_date=as_of_date,
        )

        # Buckets initialisieren
        for bucket in AgingBucket:
            report.buckets.append(AgingBucketSummary(bucket=bucket))

        # Dokumente laden
        query = select(Document).where(
            and_(
                Document.owner_id == user_id,
                Document.document_type.in_(document_types),
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        total_weighted_days = Decimal("0.00")

        for doc in documents:
            extracted = doc.extracted_data or {}

            # Bezahlte ueberspringen
            if extracted.get("payment_status") == "paid":
                continue

            # Betrag
            amount = extracted.get("total_amount") or extracted.get("amount")
            if not amount:
                continue

            try:
                amount = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation) as e:
                logger.debug("aging_report_invalid_amount", error_type=type(e).__name__, amount_value=str(amount))
                continue

            # Counterparty
            cp = extracted.get("creditor_name") or extracted.get("supplier_name")
            if counterparty and cp != counterparty:
                continue

            # Faelligkeitsdatum
            due_date_str = extracted.get("due_date")
            if due_date_str:
                try:
                    if isinstance(due_date_str, str):
                        due_date = datetime.fromisoformat(due_date_str).date()
                    else:
                        due_date = due_date_str
                except (ValueError, TypeError) as e:
                    logger.debug("aging_report_invalid_due_date", error_type=type(e).__name__, due_date_value=str(due_date_str))
                    due_date = None
            else:
                due_date = None

            # Rechnungsdatum
            invoice_date_str = extracted.get("invoice_date") or extracted.get("date")
            if invoice_date_str:
                try:
                    if isinstance(invoice_date_str, str):
                        invoice_date = datetime.fromisoformat(invoice_date_str).date()
                    else:
                        invoice_date = invoice_date_str
                except (ValueError, TypeError) as e:
                    logger.debug("aging_report_invalid_invoice_date", error_type=type(e).__name__, invoice_date_value=str(invoice_date_str))
                    invoice_date = None
            else:
                invoice_date = None

            # Tage ueberfaellig
            if due_date:
                days_overdue = (as_of_date - due_date).days
            else:
                days_overdue = 0

            # Bucket bestimmen
            bucket = self._get_bucket(days_overdue)

            # Line Item erstellen
            line_item = AgingLineItem(
                document_id=doc.id,
                invoice_number=extracted.get("invoice_number"),
                counterparty=cp,
                invoice_date=invoice_date,
                due_date=due_date,
                amount=amount,
                bucket=bucket,
                days_overdue=days_overdue,
                document_type=doc.document_type,
            )

            if include_details:
                report.line_items.append(line_item)

            # Bucket-Summe aktualisieren
            for bucket_summary in report.buckets:
                if bucket_summary.bucket == bucket:
                    bucket_summary.count += 1
                    bucket_summary.amount += amount
                    break

            # Totals
            report.total_count += 1
            report.total_amount += amount
            if days_overdue > 0:
                report.total_overdue += amount

            # Fuer gewichteten Durchschnitt
            if days_overdue > 0:
                total_weighted_days += amount * Decimal(str(days_overdue))

        # Prozentsaetze berechnen
        if report.total_amount > 0:
            for bucket_summary in report.buckets:
                bucket_summary.percentage = float(
                    bucket_summary.amount / report.total_amount * 100
                )

            # Gewichteter Durchschnitt
            overdue_items = [i for i in report.line_items if i.days_overdue > 0]
            if overdue_items:
                report.average_days_overdue = sum(
                    i.days_overdue for i in overdue_items
                ) / len(overdue_items)

            report.weighted_average_age = float(
                total_weighted_days / report.total_amount
            )

        logger.info(
            "aging_report_generated",
            report_type=report_type.value,
            user_id=str(user_id),
            total_count=report.total_count,
            total_amount=float(report.total_amount),
        )

        return report

    def _get_bucket(self, days_overdue: int) -> AgingBucket:
        """Bestimme Bucket fuer Tage ueberfaellig."""
        if days_overdue <= 0:
            return AgingBucket.CURRENT
        elif days_overdue <= 30:
            return AgingBucket.DAYS_1_30
        elif days_overdue <= 60:
            return AgingBucket.DAYS_31_60
        elif days_overdue <= 90:
            return AgingBucket.DAYS_61_90
        else:
            return AgingBucket.DAYS_90_PLUS

    def _report_to_dict(self, report: AgingReport) -> Dict[str, Any]:
        """Konvertiere Report zu Dictionary."""
        return {
            "as_of_date": report.as_of_date.isoformat(),
            "total_count": report.total_count,
            "total_amount": float(report.total_amount),
            "total_overdue": float(report.total_overdue),
            "average_days_overdue": report.average_days_overdue,
            "buckets": [
                {
                    "bucket": b.bucket.value,
                    "count": b.count,
                    "amount": float(b.amount),
                    "percentage": round(b.percentage, 1),
                }
                for b in report.buckets
            ],
        }

    def _interpret_dso(self, dso: float) -> str:
        """Interpretiere DSO-Wert."""
        if dso < 30:
            return "Ausgezeichnet: Schnelle Zahlungseingaenge"
        elif dso < 45:
            return "Gut: Zahlungseingaenge im normalen Bereich"
        elif dso < 60:
            return "Akzeptabel: Raum fuer Verbesserung"
        elif dso < 90:
            return "Verbesserungsbedarf: Zahlungseingaenge zu langsam"
        else:
            return "Kritisch: Erhebliche Verzoegerungen bei Zahlungseingaengen"


# Singleton
aging_report_service = AgingReportService()
