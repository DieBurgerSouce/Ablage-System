"""Smart Inbox Aggregator - Sammelt Items aus verschiedenen Quellen.

Aggregiert Aufgaben aus:
- Validation Queue (ZeroTouchResult)
- Alerts (Warnungen)
- Deadlines (Fristen)
- OCR Results (niedrige Confidence)
- Approval Requests (Genehmigungen)
- Document Tasks (Aufgaben)
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.db.models import (
    ZeroTouchResult,
    InvoiceTracking,
    Document,
    ApprovalRequest,
    DocumentTask,
    SmartInboxItemSource,
)
from app.db.models_alert import Alert, AlertSeverity, AlertStatus
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class InboxItemData:
    """Daten fuer ein Smart Inbox Item."""
    source_type: str
    source_id: UUID
    title: str
    description: Optional[str]
    category: str
    raw_priority: float  # 0-100
    deadline: Optional[datetime]
    document_id: Optional[UUID]
    entity_id: Optional[UUID]
    context_data: Dict[str, Any]
    recommended_actions: List[str]


class InboxAggregator:
    """Aggregiert Smart Inbox Items aus verschiedenen Quellen."""

    def __init__(self) -> None:
        """Initialisiert den Aggregator."""
        self.logger = logger.bind(service="inbox_aggregator")

    async def aggregate_for_user(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """
        Aggregiert alle Inbox Items fuer einen Benutzer.

        Args:
            user_id: Benutzer-ID
            company_id: Company-ID fuer Multi-Tenant Isolation
            db: Async DB Session

        Returns:
            Liste von InboxItemData
        """
        self.logger.info(
            "aggregating_inbox_items",
            user_id=str(user_id),
            company_id=str(company_id),
        )

        items: List[InboxItemData] = []

        # Alle Quellen aggregieren
        sources = [
            SmartInboxItemSource.VALIDATION_QUEUE,
            SmartInboxItemSource.ALERT,
            SmartInboxItemSource.DEADLINE,
            SmartInboxItemSource.OCR_RESULT,
            SmartInboxItemSource.APPROVAL,
            SmartInboxItemSource.TASK,
        ]

        for source_type in sources:
            try:
                source_items = await self.aggregate_single_source(
                    source_type=source_type.value,
                    user_id=user_id,
                    company_id=company_id,
                    db=db,
                )
                items.extend(source_items)
            except Exception as e:
                self.logger.error(
                    "source_aggregation_failed",
                    source_type=source_type.value,
                    **safe_error_log(e),
                )
                # Weiter mit nächster Quelle

        self.logger.info(
            "aggregation_complete",
            total_items=len(items),
        )

        return items

    async def aggregate_single_source(
        self,
        source_type: str,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """
        Aggregiert Items von einer einzelnen Quelle.

        Args:
            source_type: Typ der Quelle
            user_id: Benutzer-ID
            company_id: Company-ID
            db: Async DB Session

        Returns:
            Liste von InboxItemData
        """
        self.logger.debug(
            "aggregating_source",
            source_type=source_type,
        )

        if source_type == SmartInboxItemSource.VALIDATION_QUEUE.value:
            return await self._aggregate_validation_queue(user_id, company_id, db)
        elif source_type == SmartInboxItemSource.ALERT.value:
            return await self._aggregate_alerts(user_id, company_id, db)
        elif source_type == SmartInboxItemSource.DEADLINE.value:
            return await self._aggregate_deadlines(user_id, company_id, db)
        elif source_type == SmartInboxItemSource.OCR_RESULT.value:
            return await self._aggregate_ocr_results(user_id, company_id, db)
        elif source_type == SmartInboxItemSource.APPROVAL.value:
            return await self._aggregate_approvals(user_id, company_id, db)
        elif source_type == SmartInboxItemSource.TASK.value:
            return await self._aggregate_tasks(user_id, company_id, db)
        else:
            self.logger.warning("unknown_source_type", source_type=source_type)
            return []

    async def _aggregate_validation_queue(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert Items aus der Validation Queue."""
        items: List[InboxItemData] = []

        # Zero-Touch Results mit niedrigem Confidence Score
        stmt = (
            select(ZeroTouchResult)
            .options(selectinload(ZeroTouchResult.document))
            .where(
                and_(
                    ZeroTouchResult.company_id == company_id,
                    ZeroTouchResult.requires_review == True,  # noqa: E712
                    ZeroTouchResult.reviewed_at.is_(None),
                )
            )
            .order_by(ZeroTouchResult.created_at.desc())
            .limit(50)
        )

        result = await db.execute(stmt)
        zero_touch_results = result.scalars().all()

        for ztr in zero_touch_results:
            # Priorität basierend auf Confidence
            confidence = ztr.overall_confidence or 0.0
            raw_priority = 70.0 if confidence < 0.6 else 55.0

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.VALIDATION_QUEUE.value,
                    source_id=ztr.id,
                    title=f"Dokument überprüfen: {ztr.document.filename if ztr.document else 'Unbekannt'}",
                    description=f"OCR-Ergebnis mit {confidence:.0%} Confidence benötigt Überprüfung",
                    category="validation",
                    raw_priority=raw_priority,
                    deadline=None,
                    document_id=ztr.document_id,
                    entity_id=None,
                    context_data={
                        "confidence": confidence,
                        "classification": ztr.classification_type or "unknown",
                    },
                    recommended_actions=["review", "approve", "reject"],
                )
            )

        return items

    async def _aggregate_alerts(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert ungelöste Alerts."""
        items: List[InboxItemData] = []

        # Alerts mit Status NEW oder ACKNOWLEDGED
        stmt = (
            select(Alert)
            .where(
                and_(
                    Alert.company_id == company_id,
                    Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]),
                )
            )
            .order_by(Alert.created_at.desc())
            .limit(50)
        )

        result = await db.execute(stmt)
        alerts = result.scalars().all()

        for alert in alerts:
            # Priorität basierend auf Severity
            priority_map = {
                AlertSeverity.CRITICAL.value: 95.0,
                AlertSeverity.HIGH.value: 80.0,
                AlertSeverity.MEDIUM.value: 60.0,
                AlertSeverity.LOW.value: 40.0,
                AlertSeverity.INFO.value: 30.0,
            }
            raw_priority = priority_map.get(alert.severity, 50.0)

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.ALERT.value,
                    source_id=alert.id,
                    title=alert.title,
                    description=alert.message,
                    category=alert.category,
                    raw_priority=raw_priority,
                    deadline=None,
                    document_id=alert.document_id,
                    entity_id=alert.entity_id,
                    context_data={
                        "alert_code": alert.alert_code,
                        "severity": alert.severity,
                        "status": alert.status,
                    },
                    recommended_actions=["acknowledge", "escalate", "dismiss"],
                )
            )

        return items

    async def _aggregate_deadlines(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert Fristen (Rechnungen mit Due Date)."""
        items: List[InboxItemData] = []

        now = datetime.now(timezone.utc)
        next_week = now + timedelta(days=7)

        # Offene Rechnungen mit Fälligkeit in den nächsten 7 Tagen
        stmt = (
            select(InvoiceTracking)
            .options(selectinload(InvoiceTracking.document))
            .where(
                and_(
                    InvoiceTracking.document.has(Document.company_id == company_id),
                    InvoiceTracking.status == "open",
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.due_date <= next_week,
                )
            )
            .order_by(InvoiceTracking.due_date.asc())
            .limit(50)
        )

        result = await db.execute(stmt)
        invoices = result.scalars().all()

        for invoice in invoices:
            if not invoice.due_date:
                continue

            # Priorität basierend auf Zeitnähe
            days_until_due = (invoice.due_date - now).days
            if days_until_due <= 0:
                raw_priority = 90.0  # Überfällig
                deadline_text = "überfällig"
            elif days_until_due == 1:
                raw_priority = 85.0  # Morgen
                deadline_text = "morgen fällig"
            elif days_until_due <= 3:
                raw_priority = 70.0  # In 2-3 Tagen
                deadline_text = f"in {days_until_due} Tagen fällig"
            else:
                raw_priority = 50.0  # Diese Woche
                deadline_text = f"in {days_until_due} Tagen fällig"

            # Skonto-Deadline erhöht Priorität
            if invoice.skonto_deadline and invoice.skonto_deadline > now:
                skonto_days = (invoice.skonto_deadline - now).days
                if skonto_days <= 2:
                    raw_priority += 10.0
                    deadline_text += f" (Skonto in {skonto_days} Tagen)"

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.DEADLINE.value,
                    source_id=invoice.id,
                    title=f"Rechnung {invoice.invoice_number or 'ohne Nr.'} {deadline_text}",
                    description=f"Betrag: {invoice.amount:.2f} {invoice.currency}",
                    category="deadline",
                    raw_priority=raw_priority,
                    deadline=invoice.due_date,
                    document_id=invoice.document_id,
                    entity_id=None,
                    context_data={
                        "invoice_number": invoice.invoice_number,
                        "amount": invoice.amount,
                        "currency": invoice.currency,
                        "days_until_due": days_until_due,
                        "skonto_available": invoice.skonto_deadline is not None,
                    },
                    recommended_actions=["pay", "use_skonto", "set_reminder"],
                )
            )

        return items

    async def _aggregate_ocr_results(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert OCR-Ergebnisse mit niedrigem Confidence."""
        items: List[InboxItemData] = []

        # Documents mit OCR-Ergebnissen unter 70% Confidence
        # Diese wurden noch nicht in ZeroTouchResult erfasst
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.ocr_confidence < 0.7,
                    Document.ocr_confidence > 0.0,
                    Document.processing_status == "completed",
                    # Nur Dokumente ohne ZeroTouchResult
                    ~Document.zero_touch_results.any(),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(30)
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            confidence = doc.ocr_confidence or 0.0
            raw_priority = 55.0

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.OCR_RESULT.value,
                    source_id=doc.id,
                    title=f"OCR-Ergebnis überprüfen: {doc.filename}",
                    description=f"Niedrige Confidence ({confidence:.0%}) bei OCR-Verarbeitung",
                    category="ocr_review",
                    raw_priority=raw_priority,
                    deadline=None,
                    document_id=doc.id,
                    entity_id=None,
                    context_data={
                        "confidence": confidence,
                        "ocr_backend": doc.ocr_backend or "unknown",
                    },
                    recommended_actions=["review", "reprocess"],
                )
            )

        return items

    async def _aggregate_approvals(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert offene Genehmigungsanfragen."""
        items: List[InboxItemData] = []

        # Pending Approvals für den Benutzer
        stmt = (
            select(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == "pending",
                    or_(
                        ApprovalRequest.requested_from_id == user_id,
                        # TODO: Auch Approvals für Gruppen/Rollen
                    ),
                )
            )
            .order_by(ApprovalRequest.created_at.desc())
            .limit(50)
        )

        result = await db.execute(stmt)
        approvals = result.scalars().all()

        for approval in approvals:
            raw_priority = 75.0

            # Erhöhte Priorität bei Eskalation
            if approval.escalated:
                raw_priority = 85.0

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.APPROVAL.value,
                    source_id=approval.id,
                    title=f"Genehmigung erforderlich: {approval.entity_type}",
                    description=approval.reason or "Keine Beschreibung",
                    category="approval",
                    raw_priority=raw_priority,
                    deadline=approval.deadline,
                    document_id=None,
                    entity_id=approval.entity_id,
                    context_data={
                        "entity_type": approval.entity_type,
                        "entity_id": str(approval.entity_id),
                        "requested_by": str(approval.requested_by_id),
                        "escalated": approval.escalated,
                    },
                    recommended_actions=["approve", "reject", "delegate"],
                )
            )

        return items

    async def _aggregate_tasks(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[InboxItemData]:
        """Aggregiert offene Dokumenten-Aufgaben."""
        items: List[InboxItemData] = []

        # Tasks für den Benutzer
        stmt = (
            select(DocumentTask)
            .options(selectinload(DocumentTask.document))
            .where(
                and_(
                    DocumentTask.company_id == company_id,
                    DocumentTask.assigned_to_id == user_id,
                    DocumentTask.status.in_(["pending", "in_progress"]),
                )
            )
            .order_by(DocumentTask.created_at.desc())
            .limit(50)
        )

        result = await db.execute(stmt)
        tasks = result.scalars().all()

        for task in tasks:
            raw_priority = 50.0

            # Erhöhte Priorität bei Deadline
            if task.deadline:
                now = datetime.now(timezone.utc)
                days_until_due = (task.deadline - now).days
                if days_until_due <= 0:
                    raw_priority = 80.0
                elif days_until_due <= 2:
                    raw_priority = 65.0

            items.append(
                InboxItemData(
                    source_type=SmartInboxItemSource.TASK.value,
                    source_id=task.id,
                    title=task.title,
                    description=task.description,
                    category="task",
                    raw_priority=raw_priority,
                    deadline=task.deadline,
                    document_id=task.document_id,
                    entity_id=None,
                    context_data={
                        "task_type": task.task_type,
                        "status": task.status,
                        "assigned_by": str(task.assigned_by_id) if task.assigned_by_id else None,
                    },
                    recommended_actions=["complete", "delegate", "update"],
                )
            )

        return items
