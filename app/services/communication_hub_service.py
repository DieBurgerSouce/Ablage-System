# -*- coding: utf-8 -*-
"""
Communication Hub Service - 360° Geschäftspartner-Ansicht.

Vision 2026+ Feature #1: Kommunikations-Hub
Aggregiert alle Interaktionen mit einem Geschäftspartner:
- Emails (aus Email-Import)
- Mahnungen & Zahlungshistorie
- Telefon-Notizen
- Chat/Kommentare an Dokumenten
- Dokument-Timeline
- Offene Rechnungen & Zahlungsverhalten
- Risiko-Score & Trend
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BusinessEntity,
    Document,
    Comment,
    InvoiceTracking,
    AuditLog,
    DocumentActivity,
    User,
)
from app.db.models_communication import (

    PhoneNote,
    CommunicationSummary,
    CommunicationType,
    CommunicationDirection,
    CommunicationSentiment,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

COMM_HUB_REQUESTS = Counter(
    "communication_hub_requests_total",
    "Anzahl der Communication Hub Anfragen",
    ["section"]
)

COMM_HUB_DURATION = Histogram(
    "communication_hub_duration_seconds",
    "Dauer der Communication Hub Abfragen",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class CommunicationTimelineItem:
    """Ein einzelner Eintrag in der Kommunikations-Timeline."""
    id: uuid.UUID
    timestamp: datetime
    type: str  # phone_call, email, document, invoice, comment, dunning
    title: str
    description: Optional[str] = None
    icon: str = "MessageSquare"
    color: str = "gray"
    direction: Optional[str] = None  # inbound, outbound
    sentiment: Optional[str] = None
    actor_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InvoiceSummary:
    """Zusammenfassung der Rechnungen mit einem Partner."""
    total_invoices: int = 0
    open_invoices: int = 0
    overdue_invoices: int = 0
    total_amount: Decimal = Decimal("0.00")
    open_amount: Decimal = Decimal("0.00")
    overdue_amount: Decimal = Decimal("0.00")
    average_payment_days: Optional[float] = None
    last_invoice_date: Optional[datetime] = None
    dunning_level_breakdown: Dict[int, int] = field(default_factory=dict)


@dataclass
class RiskTrend:
    """Risiko-Trend für einen Partner."""
    current_score: Optional[float] = None
    previous_score: Optional[float] = None
    trend_direction: str = "stable"  # improving, stable, declining
    trend_percentage: float = 0.0
    risk_level: str = "unknown"  # low, medium, high, critical
    factors: Dict[str, float] = field(default_factory=dict)


@dataclass
class CommunicationHubData:
    """Vollständige 360°-Ansicht eines Geschäftspartners."""
    entity: Dict[str, Any]
    timeline: List[CommunicationTimelineItem]
    invoice_summary: InvoiceSummary
    risk_trend: RiskTrend
    communication_stats: Dict[str, Any]
    recent_documents: List[Dict[str, Any]]
    open_tasks: List[Dict[str, Any]]
    phone_notes: List[Dict[str, Any]]


class CommunicationHubService:
    """
    Service für die 360° Geschäftspartner-Ansicht.

    Aggregiert alle relevanten Daten für eine zentrale Übersicht.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert den Service."""
        self.db = db

    async def get_communication_hub(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        timeline_limit: int = 50,
        documents_limit: int = 10,
        include_sections: Optional[List[str]] = None,
    ) -> CommunicationHubData:
        """
        Holt die vollständige 360°-Ansicht eines Geschäftspartners.

        Args:
            entity_id: ID des Geschäftspartners
            company_id: Company-ID (Multi-Tenant)
            timeline_limit: Max. Anzahl Timeline-Einträge
            documents_limit: Max. Anzahl Dokumente
            include_sections: Welche Sektionen geladen werden sollen

        Returns:
            CommunicationHubData mit allen aggregierten Daten
        """
        import time
        start_time = time.perf_counter()

        # Default: alle Sektionen
        if include_sections is None:
            include_sections = [
                "entity", "timeline", "invoices", "risk",
                "stats", "documents", "tasks", "phone_notes"
            ]

        # Error-Tracking für partielle Fehler
        errors: List[str] = []

        # Lade Entity - Kritisch, ohne Entity kein Hub
        entity_data = {}
        if "entity" in include_sections:
            try:
                entity_data = await self._load_entity(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="entity").inc()
            except Exception as e:
                logger.error(
                    "communication_hub_entity_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("entity")
                # Entity-Fehler ist kritisch - leere Response
                if not entity_data:
                    entity_data = {"error": "Entity konnte nicht geladen werden"}

        # Lade Timeline
        timeline = []
        if "timeline" in include_sections:
            try:
                timeline = await self._build_timeline(
                    entity_id, company_id, limit=timeline_limit
                )
                COMM_HUB_REQUESTS.labels(section="timeline").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_timeline_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("timeline")

        # Lade Rechnungs-Zusammenfassung
        invoice_summary = InvoiceSummary()
        if "invoices" in include_sections:
            try:
                invoice_summary = await self._get_invoice_summary(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="invoices").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_invoices_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("invoices")

        # Lade Risiko-Trend
        risk_trend = RiskTrend()
        if "risk" in include_sections:
            try:
                risk_trend = await self._get_risk_trend(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="risk").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_risk_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("risk")

        # Lade Kommunikations-Statistiken
        comm_stats = {}
        if "stats" in include_sections:
            try:
                comm_stats = await self._get_communication_stats(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="stats").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_stats_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("stats")

        # Lade aktuelle Dokumente
        recent_documents = []
        if "documents" in include_sections:
            try:
                recent_documents = await self._get_recent_documents(
                    entity_id, company_id, limit=documents_limit
                )
                COMM_HUB_REQUESTS.labels(section="documents").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_documents_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("documents")

        # Lade offene Aufgaben
        open_tasks = []
        if "tasks" in include_sections:
            try:
                open_tasks = await self._get_open_tasks(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="tasks").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_tasks_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("tasks")

        # Lade Telefon-Notizen
        phone_notes = []
        if "phone_notes" in include_sections:
            try:
                phone_notes = await self._get_phone_notes(entity_id, company_id)
                COMM_HUB_REQUESTS.labels(section="phone_notes").inc()
            except Exception as e:
                logger.warning(
                    "communication_hub_phone_notes_error",
                    entity_id=str(entity_id),
                    **safe_error_log(e),
                )
                errors.append("phone_notes")

        duration = time.perf_counter() - start_time
        COMM_HUB_DURATION.observe(duration)

        # Log mit Fehler-Info wenn partielle Fehler aufgetreten
        if errors:
            logger.warning(
                "communication_hub_loaded_partial",
                entity_id=str(entity_id),
                sections=include_sections,
                failed_sections=errors,
                duration_ms=round(duration * 1000, 2),
            )
        else:
            logger.info(
                "communication_hub_loaded",
                entity_id=str(entity_id),
                sections=include_sections,
                duration_ms=round(duration * 1000, 2),
            )

        return CommunicationHubData(
            entity=entity_data,
            timeline=timeline,
            invoice_summary=invoice_summary,
            risk_trend=risk_trend,
            communication_stats=comm_stats,
            recent_documents=recent_documents,
            open_tasks=open_tasks,
            phone_notes=phone_notes,
        )

    async def _load_entity(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Laedt die Entity-Basisdaten.

        SECURITY: Multi-Tenant Isolation via Document.company_id Check.
        BusinessEntity hat kein eigenes company_id, daher prüfen wir
        ob mindestens ein Dokument dieser Entity zur Company gehoert.
        """
        # Erst prüfen ob Entity existiert und mindestens ein Dokument
        # dieser Company mit dieser Entity verknüpft ist
        access_check = await self.db.execute(
            select(func.count(Document.id))
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        has_access = (access_check.scalar() or 0) > 0

        if not has_access:
            logger.warning(
                "entity_access_denied",
                entity_id=str(entity_id),
                company_id=str(company_id),
            )
            return {}

        # Jetzt Entity laden
        result = await self.db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id == entity_id,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            return {}

        return {
            "id": str(entity.id),
            "name": entity.name,
            "display_name": entity.display_name or entity.name,
            "short_name": entity.short_name,
            "entity_type": entity.entity_type,
            "vat_id": entity.vat_id,
            "iban": entity.iban,
            "email": entity.email,
            "phone": entity.phone,
            "full_address": entity.full_address,
            "is_active": entity.is_active,
            "verified": entity.verified,
            "risk_score": entity.risk_score,
            "payment_behavior_score": entity.payment_behavior_score,
            "document_count": entity.document_count,
            "total_invoice_amount": entity.total_invoice_amount,
            "first_document_date": entity.first_document_date.isoformat() if entity.first_document_date else None,
            "last_document_date": entity.last_document_date.isoformat() if entity.last_document_date else None,
            "lexware_ids": entity.lexware_ids or {},
            "notes": entity.notes,
        }

    async def _build_timeline(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        limit: int = 50,
    ) -> List[CommunicationTimelineItem]:
        """Baut die kombinierte Kommunikations-Timeline."""
        timeline: List[CommunicationTimelineItem] = []

        # 1. Telefon-Notizen
        phone_result = await self.db.execute(
            select(PhoneNote)
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
            )
            .order_by(PhoneNote.call_datetime.desc())
            .limit(limit)
        )
        for note in phone_result.scalars().all():
            timeline.append(CommunicationTimelineItem(
                id=note.id,
                timestamp=note.call_datetime,
                type="phone_call",
                title=note.subject,
                description=note.summary or note.notes[:200] if note.notes else None,
                icon="Phone",
                color="blue",
                direction=note.direction,
                sentiment=note.sentiment,
                actor_name=note.contact_person,
                metadata={
                    "duration_minutes": note.duration_minutes,
                    "follow_up_required": note.follow_up_required,
                },
            ))

        # 2. Dokumente (mit Aktivitäten)
        doc_result = await self.db.execute(
            select(Document)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        for doc in doc_result.scalars().all():
            timeline.append(CommunicationTimelineItem(
                id=doc.id,
                timestamp=doc.created_at,
                type="document",
                title=f"Dokument: {doc.original_filename or doc.filename}",
                description=f"Typ: {doc.document_type or 'Unbekannt'}",
                icon="FileText",
                color="gray",
                direction="inbound" if doc.document_type in ["invoice_incoming", "delivery_note", "order"] else "outbound",
                metadata={
                    "document_type": doc.document_type,
                    "ocr_status": doc.status,
                    "ocr_confidence": doc.ocr_confidence,
                },
            ))

        # 3. Rechnungen und Mahnungen
        invoice_result = await self.db.execute(
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
            )
            .order_by(InvoiceTracking.invoice_date.desc())
            .limit(limit)
        )
        for invoice in invoice_result.scalars().all():
            # Rechnungs-Eintrag
            color = "green"
            if invoice.status == "overdue":
                color = "red"
            elif invoice.status == "dunning":
                color = "orange"
            elif invoice.status == "paid":
                color = "emerald"

            timeline.append(CommunicationTimelineItem(
                id=invoice.id,
                timestamp=invoice.invoice_date,
                type="invoice",
                title=f"Rechnung: {invoice.invoice_number or 'Unbekannt'}",
                description=f"Betrag: {invoice.amount or 0:.2f} EUR, Status: {invoice.status}",
                icon="Receipt",
                color=color,
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": float(invoice.amount) if invoice.amount else 0,
                    "status": invoice.status,
                    "dunning_level": invoice.dunning_level,
                },
            ))

            # Mahnungs-Eintrag falls vorhanden
            if invoice.dunning_level and invoice.dunning_level > 0:
                timeline.append(CommunicationTimelineItem(
                    id=uuid.uuid4(),  # Synthetische ID
                    timestamp=invoice.dunning_date or invoice.due_date,
                    type="dunning",
                    title=f"Mahnung Stufe {invoice.dunning_level}",
                    description=f"Rechnung {invoice.invoice_number}, {invoice.amount or 0:.2f} EUR",
                    icon="AlertTriangle",
                    color="red",
                    direction="outbound",
                    metadata={
                        "invoice_id": str(invoice.id),
                        "dunning_level": invoice.dunning_level,
                    },
                ))

        # 4. Kommentare an Dokumenten
        comment_result = await self.db.execute(
            select(Comment)
            .join(Document, Comment.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
            )
            .order_by(Comment.created_at.desc())
            .limit(limit)
        )
        for comment in comment_result.scalars().all():
            timeline.append(CommunicationTimelineItem(
                id=comment.id,
                timestamp=comment.created_at,
                type="comment",
                title="Kommentar",
                description=comment.content[:200] if comment.content else None,
                icon="MessageSquare",
                color="purple",
                metadata={
                    "document_id": str(comment.document_id),
                },
            ))

        # Sortiere nach Timestamp absteigend
        timeline.sort(key=lambda x: x.timestamp, reverse=True)

        # Limitiere
        return timeline[:limit]

    async def _get_invoice_summary(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> InvoiceSummary:
        """Berechnet die Rechnungs-Zusammenfassung."""
        summary = InvoiceSummary()
        now = datetime.now(timezone.utc)

        # Lade alle Rechnungen des Partners
        result = await self.db.execute(
            select(InvoiceTracking)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
            )
        )
        invoices = result.scalars().all()

        if not invoices:
            return summary

        summary.total_invoices = len(invoices)
        total_amount = Decimal("0.00")
        open_amount = Decimal("0.00")
        overdue_amount = Decimal("0.00")
        payment_days_sum = 0
        payment_days_count = 0
        dunning_breakdown: Dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

        for invoice in invoices:
            amount = Decimal(str(invoice.amount)) if invoice.amount else Decimal("0.00")
            total_amount += amount

            # Status-basierte Aggregation
            if invoice.status in ["open", "sent", "partial"]:
                summary.open_invoices += 1
                open_amount += amount

                if invoice.due_date and now.date() > invoice.due_date:
                    summary.overdue_invoices += 1
                    overdue_amount += amount

            elif invoice.status == "overdue" or invoice.status == "dunning":
                summary.open_invoices += 1
                summary.overdue_invoices += 1
                open_amount += amount
                overdue_amount += amount

            # Mahnstufen
            level = invoice.dunning_level or 0
            if level in dunning_breakdown:
                dunning_breakdown[level] += 1

            # Zahlungstage berechnen (nur für bezahlte)
            if invoice.status == "paid" and invoice.invoice_date and invoice.paid_at:
                days = (invoice.paid_at.date() - invoice.invoice_date).days
                if 0 <= days <= 365:  # Sinnvolle Werte
                    payment_days_sum += days
                    payment_days_count += 1

            # Letztes Rechnungsdatum
            if invoice.invoice_date:
                if summary.last_invoice_date is None or invoice.invoice_date > summary.last_invoice_date.date():
                    summary.last_invoice_date = datetime.combine(
                        invoice.invoice_date,
                        datetime.min.time()
                    ).replace(tzinfo=timezone.utc)

        summary.total_amount = total_amount
        summary.open_amount = open_amount
        summary.overdue_amount = overdue_amount
        summary.dunning_level_breakdown = dunning_breakdown

        if payment_days_count > 0:
            summary.average_payment_days = round(payment_days_sum / payment_days_count, 1)

        return summary

    async def _get_risk_trend(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> RiskTrend:
        """Berechnet den Risiko-Trend.

        HINWEIS: Zugriffsprüfung erfolgt bereits in _load_entity().
        Diese Methode wird nur für bereits validierte Entities aufgerufen.
        """
        result = await self.db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id == entity_id,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            return RiskTrend()

        trend = RiskTrend()
        trend.current_score = entity.risk_score

        # Risk Level bestimmen
        if entity.risk_score is None:
            trend.risk_level = "unknown"
        elif entity.risk_score < 25:
            trend.risk_level = "low"
        elif entity.risk_score < 50:
            trend.risk_level = "medium"
        elif entity.risk_score < 75:
            trend.risk_level = "high"
        else:
            trend.risk_level = "critical"

        # Risk Factors
        if entity.risk_factors:
            trend.factors = entity.risk_factors

        # Historische Trend-Berechnung basierend auf InvoiceTracking-Daten
        # Vergleiche Zahlungsverhalten der letzten 90 Tage mit den 90 Tagen davor
        now = datetime.now(timezone.utc)
        period_end = now
        period_start = now - timedelta(days=90)
        prev_period_end = period_start
        prev_period_start = prev_period_end - timedelta(days=90)

        # Aktuelle Periode: Durchschnittliche Zahlungsverzögerung
        current_payment_stats = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', InvoiceTracking.paid_at) -
                    func.extract('epoch', func.cast(InvoiceTracking.due_date, Document.created_at.type))
                ) / 86400  # Sekunden zu Tagen
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                InvoiceTracking.status == "paid",
                InvoiceTracking.paid_at >= period_start,
                InvoiceTracking.paid_at < period_end,
            )
        )
        current_avg_delay = current_payment_stats.scalar() or 0

        # Vorherige Periode
        prev_payment_stats = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', InvoiceTracking.paid_at) -
                    func.extract('epoch', func.cast(InvoiceTracking.due_date, Document.created_at.type))
                ) / 86400
            )
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                InvoiceTracking.status == "paid",
                InvoiceTracking.paid_at >= prev_period_start,
                InvoiceTracking.paid_at < prev_period_end,
            )
        )
        prev_avg_delay = prev_payment_stats.scalar() or 0

        # Trend berechnen (negative Verzögerung = besser)
        if prev_avg_delay != 0:
            # Wenn aktuelle Verzögerung geringer ist, verbessert sich der Trend
            change = current_avg_delay - prev_avg_delay
            trend.trend_percentage = round(abs(change / prev_avg_delay) * 100, 1) if prev_avg_delay else 0

            if change < -1:  # Mindestens 1 Tag Verbesserung
                trend.trend_direction = "improving"
            elif change > 1:  # Mindestens 1 Tag Verschlechterung
                trend.trend_direction = "declining"
            else:
                trend.trend_direction = "stable"

            # Schätze vorherigen Score basierend auf Verzögerungsänderung
            if entity.risk_score is not None:
                # Rückrechnung: Wenn sich Verzögerung geändert hat, war Score anders
                score_impact = change * 2  # ~2 Punkte pro Tag Verzögerungsänderung
                trend.previous_score = max(0, min(100, entity.risk_score - score_impact))

        return trend

    async def _get_communication_stats(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Berechnet Kommunikations-Statistiken."""
        # Telefon-Notizen zaehlen
        phone_result = await self.db.execute(
            select(func.count(PhoneNote.id))
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
            )
        )
        phone_count = phone_result.scalar() or 0

        # Offene Follow-ups
        follow_up_result = await self.db.execute(
            select(func.count(PhoneNote.id))
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
                PhoneNote.follow_up_required == True,
                PhoneNote.follow_up_completed == False,
            )
        )
        open_follow_ups = follow_up_result.scalar() or 0

        # Dokumente zaehlen
        doc_result = await self.db.execute(
            select(func.count(Document.id))
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        doc_count = doc_result.scalar() or 0

        # Kommentare zaehlen
        comment_result = await self.db.execute(
            select(func.count(Comment.id))
            .join(Document, Comment.document_id == Document.id)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
            )
        )
        comment_count = comment_result.scalar() or 0

        # Sentiment-Verteilung (Telefon-Notizen)
        sentiment_result = await self.db.execute(
            select(PhoneNote.sentiment, func.count(PhoneNote.id))
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
                PhoneNote.sentiment.isnot(None),
            )
            .group_by(PhoneNote.sentiment)
        )
        sentiment_dist = {row[0]: row[1] for row in sentiment_result.all()}

        # Zeitbasierte Statistiken für die letzten 30 Tage
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Telefonate pro Woche (4 Wochen)
        weekly_calls = {}
        for week_offset in range(4):
            week_start = now - timedelta(days=7 * (week_offset + 1))
            week_end = now - timedelta(days=7 * week_offset)
            week_count_result = await self.db.execute(
                select(func.count(PhoneNote.id))
                .where(
                    PhoneNote.entity_id == entity_id,
                    PhoneNote.company_id == company_id,
                    PhoneNote.call_datetime >= week_start,
                    PhoneNote.call_datetime < week_end,
                )
            )
            weekly_calls[f"week_{week_offset + 1}"] = week_count_result.scalar() or 0

        # Dokumente pro Woche (4 Wochen)
        weekly_docs = {}
        for week_offset in range(4):
            week_start = now - timedelta(days=7 * (week_offset + 1))
            week_end = now - timedelta(days=7 * week_offset)
            week_doc_result = await self.db.execute(
                select(func.count(Document.id))
                .where(
                    Document.business_entity_id == entity_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.created_at >= week_start,
                    Document.created_at < week_end,
                )
            )
            weekly_docs[f"week_{week_offset + 1}"] = week_doc_result.scalar() or 0

        # Aktivitätstrend (Vergleich letzte 15 Tage vs. vorherige 15 Tage)
        first_half_start = thirty_days_ago
        first_half_end = now - timedelta(days=15)
        second_half_start = first_half_end
        second_half_end = now

        first_half_calls = await self.db.execute(
            select(func.count(PhoneNote.id))
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
                PhoneNote.call_datetime >= first_half_start,
                PhoneNote.call_datetime < first_half_end,
            )
        )
        second_half_calls = await self.db.execute(
            select(func.count(PhoneNote.id))
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
                PhoneNote.call_datetime >= second_half_start,
                PhoneNote.call_datetime < second_half_end,
            )
        )
        first_count = first_half_calls.scalar() or 0
        second_count = second_half_calls.scalar() or 0

        activity_trend = "stable"
        if second_count > first_count + 2:
            activity_trend = "increasing"
        elif second_count < first_count - 2:
            activity_trend = "decreasing"

        return {
            "total_phone_calls": phone_count,
            "open_follow_ups": open_follow_ups,
            "total_documents": doc_count,
            "total_comments": comment_count,
            "sentiment_distribution": sentiment_dist,
            "last_30_days": {
                "phone_calls_by_week": weekly_calls,
                "documents_by_week": weekly_docs,
                "activity_trend": activity_trend,
                "total_phone_calls": sum(weekly_calls.values()),
                "total_documents": sum(weekly_docs.values()),
            },
        }

    async def _get_recent_documents(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Laedt die aktuellsten Dokumente."""
        result = await self.db.execute(
            select(Document)
            .where(
                Document.business_entity_id == entity_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        documents = []
        for doc in result.scalars().all():
            documents.append({
                "id": str(doc.id),
                "filename": doc.original_filename or doc.filename,
                "document_type": doc.document_type,
                "status": doc.status,
                "ocr_confidence": doc.ocr_confidence,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            })

        return documents

    async def _get_open_tasks(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        """Laedt offene Aufgaben (Follow-ups)."""
        result = await self.db.execute(
            select(PhoneNote)
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
                PhoneNote.follow_up_required == True,
                PhoneNote.follow_up_completed == False,
            )
            .order_by(PhoneNote.follow_up_date.asc())
        )

        tasks = []
        now = datetime.now(timezone.utc)

        for note in result.scalars().all():
            is_overdue = False
            if note.follow_up_date and note.follow_up_date < now:
                is_overdue = True

            tasks.append({
                "id": str(note.id),
                "type": "follow_up",
                "subject": note.subject,
                "notes": note.follow_up_notes,
                "due_date": note.follow_up_date.isoformat() if note.follow_up_date else None,
                "is_overdue": is_overdue,
                "contact_person": note.contact_person,
            })

        return tasks

    async def _get_phone_notes(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Laedt Telefon-Notizen."""
        result = await self.db.execute(
            select(PhoneNote)
            .where(
                PhoneNote.entity_id == entity_id,
                PhoneNote.company_id == company_id,
            )
            .order_by(PhoneNote.call_datetime.desc())
            .limit(limit)
        )

        return [note.to_dict() for note in result.scalars().all()]

    # =========================================================================
    # Phone Note CRUD
    # =========================================================================

    async def create_phone_note(
        self,
        entity_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        subject: str,
        notes: Optional[str] = None,
        call_type: str = CommunicationType.PHONE_CALL.value,
        direction: str = CommunicationDirection.INBOUND.value,
        contact_person: Optional[str] = None,
        phone_number: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        sentiment: Optional[str] = None,
        follow_up_required: bool = False,
        follow_up_date: Optional[datetime] = None,
        follow_up_notes: Optional[str] = None,
        call_datetime: Optional[datetime] = None,
    ) -> PhoneNote:
        """Erstellt eine neue Telefon-Notiz."""
        note = PhoneNote(
            entity_id=entity_id,
            company_id=company_id,
            created_by_id=user_id,
            subject=subject,
            notes=notes,
            call_type=call_type,
            direction=direction,
            contact_person=contact_person,
            phone_number=phone_number,
            duration_minutes=duration_minutes,
            sentiment=sentiment,
            follow_up_required=follow_up_required,
            follow_up_date=follow_up_date,
            follow_up_notes=follow_up_notes,
            call_datetime=call_datetime or datetime.now(timezone.utc),
        )

        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)

        logger.info(
            "phone_note_created",
            note_id=str(note.id),
            entity_id=str(entity_id),
            call_type=call_type,
        )

        return note

    async def update_phone_note(
        self,
        note_id: uuid.UUID,
        company_id: uuid.UUID,
        **kwargs,
    ) -> Optional[PhoneNote]:
        """Aktualisiert eine Telefon-Notiz."""
        result = await self.db.execute(
            select(PhoneNote).where(
                PhoneNote.id == note_id,
                PhoneNote.company_id == company_id,
            )
        )
        note = result.scalar_one_or_none()

        if not note:
            return None

        # Aktualisiere Felder
        allowed_fields = {
            "subject", "notes", "summary", "call_type", "direction",
            "contact_person", "phone_number", "duration_minutes",
            "sentiment", "follow_up_required", "follow_up_date",
            "follow_up_notes", "follow_up_completed", "tags",
        }

        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                setattr(note, key, value)

        # Follow-up Completion Timestamp
        if kwargs.get("follow_up_completed") and not note.follow_up_completed_at:
            note.follow_up_completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(note)

        return note

    async def delete_phone_note(
        self,
        note_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Löscht eine Telefon-Notiz."""
        result = await self.db.execute(
            select(PhoneNote).where(
                PhoneNote.id == note_id,
                PhoneNote.company_id == company_id,
            )
        )
        note = result.scalar_one_or_none()

        if not note:
            return False

        await self.db.delete(note)
        await self.db.commit()

        logger.info(
            "phone_note_deleted",
            note_id=str(note_id),
        )

        return True
