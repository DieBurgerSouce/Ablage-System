# -*- coding: utf-8 -*-
"""
Deadline Insights Service.

Enterprise Feature: Proaktive Warnungen zu Fristen und Deadlines.

Dieses Modul überwacht verschiedene Deadline-Typen und generiert
rechtzeitig Warnungen:

- Skonto-Fristen: "Skonto-Frist für Rechnung XY laeuft in 2 Tagen ab!"
- Vertrags-Kündigungen: "Kündigungsfrist für Vertrag Z endet am 15.02."
- Zahlungsfristen: "3 Rechnungen sind überfällig!"
- Aufbewahrungsfristen: "12 Dokumente erreichen Aufbewahrungsfrist."

Integration mit: SkontoService, ContractService, InvoiceTracking, RetentionService
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.proactive_insights_service import (
    ExtractedEntity,
    EntityType,
    InsightPriority,
    InsightType,
    ProactiveInsight,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class DeadlineType(str, Enum):
    """Typ der Deadline."""
    SKONTO = "skonto"
    CONTRACT_CANCELLATION = "contract_cancellation"
    PAYMENT_DUE = "payment_due"
    RETENTION_EXPIRY = "retention_expiry"


class UrgencyLevel(str, Enum):
    """Dringlichkeitsstufe der Deadline."""
    CRITICAL = "critical"       # Heute oder morgen
    URGENT = "urgent"           # Nächste 3 Tage
    SOON = "soon"               # Nächste 7 Tage
    UPCOMING = "upcoming"       # Nächste 14 Tage
    FUTURE = "future"           # Mehr als 14 Tage


@dataclass
class DeadlineAlert:
    """Ein Deadline-Alert mit Details."""
    deadline_type: DeadlineType
    entity_id: UUID
    entity_name: str
    deadline_date: datetime
    urgency: UrgencyLevel
    potential_value: Optional[Decimal] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def days_until(self) -> int:
        """Tage bis zur Deadline."""
        now = datetime.now(timezone.utc)
        delta = self.deadline_date - now
        return delta.days

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {
            UrgencyLevel.CRITICAL: InsightPriority.CRITICAL,
            UrgencyLevel.URGENT: InsightPriority.HIGH,
            UrgencyLevel.SOON: InsightPriority.MEDIUM,
            UrgencyLevel.UPCOMING: InsightPriority.MEDIUM,
            UrgencyLevel.FUTURE: InsightPriority.LOW,
        }

        type_map = {
            DeadlineType.SKONTO: InsightType.REMINDER,
            DeadlineType.CONTRACT_CANCELLATION: InsightType.WARNING,
            DeadlineType.PAYMENT_DUE: InsightType.WARNING,
            DeadlineType.RETENTION_EXPIRY: InsightType.INFORMATION,
        }

        return ProactiveInsight(
            insight_type=type_map.get(self.deadline_type, InsightType.REMINDER),
            priority=priority_map.get(self.urgency, InsightPriority.MEDIUM),
            title=self._generate_title(),
            message=self._generate_message(),
            detail=self._generate_detail(),
            potential_value=self.potential_value,
            action_url=self.action_url,
            action_label=self.action_label,
            expires_at=self.deadline_date,
            source_rule=f"deadline_{self.deadline_type.value}",
            related_entities=[
                ExtractedEntity(
                    entity_type=self._get_entity_type(),
                    entity_id=self.entity_id,
                    entity_name=self.entity_name,
                    confidence=1.0,
                )
            ],
        )

    def _generate_title(self) -> str:
        """Generiert Titel basierend auf Deadline-Typ."""
        days = self.days_until

        if self.deadline_type == DeadlineType.SKONTO:
            if days <= 0:
                return f"Skonto-Frist abgelaufen: {self.entity_name}"
            elif days == 1:
                return f"Skonto-Frist laeuft morgen ab!"
            else:
                return f"Skonto-Frist in {days} Tagen"

        elif self.deadline_type == DeadlineType.CONTRACT_CANCELLATION:
            if days <= 0:
                return f"Kündigungsfrist verpasst: {self.entity_name}"
            elif days == 1:
                return f"Kündigungsfrist endet morgen!"
            else:
                return f"Kündigungsfrist in {days} Tagen"

        elif self.deadline_type == DeadlineType.PAYMENT_DUE:
            if days <= 0:
                return f"Zahlung überfällig: {self.entity_name}"
            elif days == 1:
                return f"Zahlung morgen fällig!"
            else:
                return f"Zahlung in {days} Tagen fällig"

        elif self.deadline_type == DeadlineType.RETENTION_EXPIRY:
            if days <= 0:
                return f"Aufbewahrungsfrist erreicht: {self.entity_name}"
            else:
                return f"Aufbewahrungsfrist endet in {days} Tagen"

        return f"Deadline in {days} Tagen"

    def _generate_message(self) -> str:
        """Generiert Nachricht basierend auf Deadline-Typ."""
        if self.deadline_type == DeadlineType.SKONTO:
            percentage = self.metadata.get("skonto_percentage", 0)
            return f"Bei Zahlung bis {self.deadline_date.strftime('%d.%m.%Y')} sparen Sie {percentage:.1f}% Skonto."

        elif self.deadline_type == DeadlineType.CONTRACT_CANCELLATION:
            return f"Vertrag '{self.entity_name}' muss bis {self.deadline_date.strftime('%d.%m.%Y')} gekündigt werden."

        elif self.deadline_type == DeadlineType.PAYMENT_DUE:
            return f"Rechnung '{self.entity_name}' ist bis {self.deadline_date.strftime('%d.%m.%Y')} fällig."

        elif self.deadline_type == DeadlineType.RETENTION_EXPIRY:
            return f"Dokument '{self.entity_name}' kann nach dem {self.deadline_date.strftime('%d.%m.%Y')} gelöscht werden."

        return f"Deadline am {self.deadline_date.strftime('%d.%m.%Y')}."

    def _generate_detail(self) -> str:
        """Generiert Detail-Text basierend auf Deadline-Typ."""
        if self.deadline_type == DeadlineType.SKONTO:
            amount = self.metadata.get("invoice_amount", 0)
            skonto = self.metadata.get("skonto_amount", 0)
            return f"Rechnungsbetrag: {amount:,.2f} EUR, Skonto-Ersparnis: {skonto:,.2f} EUR"

        elif self.deadline_type == DeadlineType.CONTRACT_CANCELLATION:
            notice_period = self.metadata.get("notice_period_months", 0)
            auto_extend = self.metadata.get("auto_extend_months", 0)
            return f"Kündigungsfrist: {notice_period} Monat(e), Auto-Verlängerung: {auto_extend} Monat(e)"

        elif self.deadline_type == DeadlineType.PAYMENT_DUE:
            dunning_level = self.metadata.get("dunning_level", 0)
            return f"Mahnstufe: {dunning_level}" if dunning_level > 0 else "Noch keine Mahnung"

        elif self.deadline_type == DeadlineType.RETENTION_EXPIRY:
            doc_type = self.metadata.get("document_type", "Dokument")
            retention_years = self.metadata.get("retention_years", 10)
            return f"Dokumenttyp: {doc_type}, Aufbewahrungspflicht: {retention_years} Jahre"

        return ""

    def _get_entity_type(self) -> EntityType:
        """Bestimmt Entity-Typ basierend auf Deadline-Typ."""
        entity_map = {
            DeadlineType.SKONTO: EntityType.DOCUMENT,
            DeadlineType.CONTRACT_CANCELLATION: EntityType.DOCUMENT,
            DeadlineType.PAYMENT_DUE: EntityType.DOCUMENT,
            DeadlineType.RETENTION_EXPIRY: EntityType.DOCUMENT,
        }
        return entity_map.get(self.deadline_type, EntityType.GENERAL)


def _calculate_urgency(deadline_date: datetime) -> UrgencyLevel:
    """Berechnet Dringlichkeit basierend auf Deadline-Datum."""
    now = datetime.now(timezone.utc)
    days = (deadline_date - now).days

    if days <= 1:
        return UrgencyLevel.CRITICAL
    elif days <= 3:
        return UrgencyLevel.URGENT
    elif days <= 7:
        return UrgencyLevel.SOON
    elif days <= 14:
        return UrgencyLevel.UPCOMING
    else:
        return UrgencyLevel.FUTURE


@dataclass
class DeadlineCheckResult:
    """Ergebnis einer Deadline-Prüfung."""
    deadline_type: DeadlineType
    deadline_date: datetime
    title: str
    message: str
    detail: str = ""
    days_remaining: int = 0
    priority: str = "medium"
    potential_value: Optional[Decimal] = None
    action_url: Optional[str] = None
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {"critical": InsightPriority.CRITICAL, "high": InsightPriority.HIGH,
                        "medium": InsightPriority.MEDIUM, "low": InsightPriority.LOW}
        return ProactiveInsight(
            insight_type=InsightType.WARNING if self.priority in ("critical", "high") else InsightType.SUGGESTION,
            priority=priority_map.get(self.priority, InsightPriority.MEDIUM),
            title=self.title,
            message=self.message,
            detail=self.detail,
            potential_value=self.potential_value,
            action_url=self.action_url,
        )


class DeadlineInsightsService:
    """
    Service für proaktive Deadline-Warnungen.

    Überwacht verschiedene Fristen im System und generiert
    rechtzeitig Warnungen, damit keine wichtigen Deadlines
    verpasst werden.
    """

    def __init__(self) -> None:
        self._initialized = False
        logger.info("deadline_insights_service_initialized")

    async def check_all_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 14,
    ) -> List[ProactiveInsight]:
        """
        Prüft alle Deadline-Typen und generiert Insights.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            days_ahead: Wie viele Tage in die Zukunft prüfen

        Returns:
            Liste von ProactiveInsights für alle relevanten Deadlines
        """
        logger.info(
            "checking_all_deadlines",
            company_id=str(company_id),
            days_ahead=days_ahead,
        )

        all_insights: List[ProactiveInsight] = []

        # Parallel alle Deadline-Checks ausführen
        results = await asyncio.gather(
            self.check_skonto_deadlines(db, company_id, days_ahead),
            self.check_contract_deadlines(db, company_id, days_ahead),
            self.check_payment_deadlines(db, company_id, days_ahead),
            self.check_retention_deadlines(db, company_id, days_ahead),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "deadline_check_failed",
                    error=str(result),
                )
            elif isinstance(result, list):
                all_insights.extend(result)

        # Nach Priorität sortieren
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        all_insights.sort(key=lambda i: priority_order.get(i.priority, 4))

        logger.info(
            "all_deadlines_checked",
            total_insights=len(all_insights),
        )

        return all_insights

    async def check_skonto_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 14,
    ) -> List[ProactiveInsight]:
        """
        Prüft ablaufende Skonto-Fristen.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            days_ahead: Wie viele Tage in die Zukunft prüfen

        Returns:
            Liste von ProactiveInsights für Skonto-Deadlines
        """
        from app.db.models import InvoiceTracking

        try:
            now = datetime.now(timezone.utc)
            deadline_limit = now + timedelta(days=days_ahead)

            # Rechnungen mit ablaufendem Skonto finden
            query = select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline <= deadline_limit,
                    InvoiceTracking.skonto_deadline >= now,
                    InvoiceTracking.skonto_used.is_(False),
                    InvoiceTracking.status != "paid",
                )
            ).order_by(InvoiceTracking.skonto_deadline.asc())

            result = await db.execute(query)
            invoices: Sequence[InvoiceTracking] = result.scalars().all()

            alerts: List[DeadlineAlert] = []
            for invoice in invoices:
                if invoice.skonto_deadline is None:
                    continue

                skonto_amount = (
                    float(invoice.total_amount or 0) *
                    float(invoice.skonto_percentage or 0) / 100
                )

                alert = DeadlineAlert(
                    deadline_type=DeadlineType.SKONTO,
                    entity_id=invoice.id,
                    entity_name=f"Rechnung {invoice.invoice_number}",
                    deadline_date=invoice.skonto_deadline,
                    urgency=_calculate_urgency(invoice.skonto_deadline),
                    potential_value=Decimal(str(skonto_amount)),
                    action_url=f"/invoices/{invoice.id}",
                    action_label="Rechnung öffnen",
                    metadata={
                        "skonto_percentage": float(invoice.skonto_percentage or 0),
                        "skonto_amount": skonto_amount,
                        "invoice_amount": float(invoice.total_amount or 0),
                        "invoice_number": invoice.invoice_number,
                        "supplier_name": invoice.supplier_name,
                    },
                )
                alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "skonto_deadlines_checked",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "skonto_deadline_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def check_contract_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 30,
    ) -> List[ProactiveInsight]:
        """
        Prüft ablaufende Vertrags-Kündigungsfristen.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            days_ahead: Wie viele Tage in die Zukunft prüfen

        Returns:
            Liste von ProactiveInsights für Vertrags-Deadlines
        """
        from app.db.models import Contract

        try:
            now = datetime.now(timezone.utc)
            deadline_limit = now + timedelta(days=days_ahead)

            # Verträge mit ablaufender Kündigungsfrist finden
            query = select(Contract).where(
                and_(
                    Contract.company_id == company_id,
                    Contract.cancellation_deadline.isnot(None),
                    Contract.cancellation_deadline <= deadline_limit,
                    Contract.cancellation_deadline >= now,
                    Contract.is_cancelled.is_(False),
                    Contract.auto_renewal.is_(True),
                )
            ).order_by(Contract.cancellation_deadline.asc())

            result = await db.execute(query)
            contracts: Sequence[Contract] = result.scalars().all()

            alerts: List[DeadlineAlert] = []
            for contract in contracts:
                if contract.cancellation_deadline is None:
                    continue

                # Jährliche Kosten als potentieller Wert
                annual_cost = Decimal("0")
                if contract.monthly_cost:
                    annual_cost = Decimal(str(contract.monthly_cost)) * 12

                alert = DeadlineAlert(
                    deadline_type=DeadlineType.CONTRACT_CANCELLATION,
                    entity_id=contract.id,
                    entity_name=contract.name,
                    deadline_date=contract.cancellation_deadline,
                    urgency=_calculate_urgency(contract.cancellation_deadline),
                    potential_value=annual_cost if annual_cost > 0 else None,
                    action_url=f"/contracts/{contract.id}",
                    action_label="Vertrag prüfen",
                    metadata={
                        "notice_period_months": contract.notice_period_months or 0,
                        "auto_extend_months": contract.auto_extend_months or 12,
                        "monthly_cost": float(contract.monthly_cost or 0),
                        "contract_type": contract.contract_type,
                        "provider": contract.provider_name,
                    },
                )
                alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "contract_deadlines_checked",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "contract_deadline_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def check_payment_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 14,
    ) -> List[ProactiveInsight]:
        """
        Prüft fällige und überfällige Zahlungen.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            days_ahead: Wie viele Tage in die Zukunft prüfen

        Returns:
            Liste von ProactiveInsights für Zahlungs-Deadlines
        """
        from app.db.models import InvoiceTracking

        try:
            now = datetime.now(timezone.utc)
            deadline_limit = now + timedelta(days=days_ahead)

            # Offene Rechnungen mit Fälligkeitsdatum finden
            query = select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.due_date <= deadline_limit,
                    InvoiceTracking.status.in_(["open", "overdue", "dunning"]),
                )
            ).order_by(InvoiceTracking.due_date.asc())

            result = await db.execute(query)
            invoices: Sequence[InvoiceTracking] = result.scalars().all()

            alerts: List[DeadlineAlert] = []
            for invoice in invoices:
                if invoice.due_date is None:
                    continue

                outstanding = Decimal(str(invoice.outstanding_amount or invoice.total_amount or 0))

                alert = DeadlineAlert(
                    deadline_type=DeadlineType.PAYMENT_DUE,
                    entity_id=invoice.id,
                    entity_name=f"Rechnung {invoice.invoice_number}",
                    deadline_date=invoice.due_date,
                    urgency=_calculate_urgency(invoice.due_date),
                    potential_value=outstanding,
                    action_url=f"/invoices/{invoice.id}",
                    action_label="Rechnung bezahlen",
                    metadata={
                        "dunning_level": invoice.dunning_level or 0,
                        "total_amount": float(invoice.total_amount or 0),
                        "outstanding_amount": float(outstanding),
                        "invoice_number": invoice.invoice_number,
                        "supplier_name": invoice.supplier_name,
                    },
                )
                alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "payment_deadlines_checked",
                company_id=str(company_id),
                alerts_count=len(alerts),
            )

            return insights

        except Exception as e:
            logger.warning(
                "payment_deadline_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def check_retention_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 90,
    ) -> List[ProactiveInsight]:
        """
        Prüft Dokumente, deren Aufbewahrungsfrist endet.

        Args:
            db: Datenbank-Session
            company_id: ID der Company
            days_ahead: Wie viele Tage in die Zukunft prüfen

        Returns:
            Liste von ProactiveInsights für Aufbewahrungs-Deadlines
        """
        from app.db.models import Document


        try:
            now = datetime.now(timezone.utc)
            deadline_limit = now + timedelta(days=days_ahead)

            # Dokumente mit ablaufender Aufbewahrungsfrist finden
            query = select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.retention_until.isnot(None),
                    Document.retention_until <= deadline_limit,
                    Document.retention_until >= now,
                    Document.is_deleted.is_(False),
                )
            ).order_by(Document.retention_until.asc())

            result = await db.execute(query)
            documents: Sequence[Document] = result.scalars().all()

            # Gruppieren nach Monat für bessere Übersicht
            alerts: List[DeadlineAlert] = []

            # Bei vielen Dokumenten: Zusammenfassende Insights erstellen
            if len(documents) > 10:
                # Gruppiere nach Monat
                monthly_counts: Dict[str, List[Document]] = {}
                for doc in documents:
                    if doc.retention_until:
                        month_key = doc.retention_until.strftime("%Y-%m")
                        if month_key not in monthly_counts:
                            monthly_counts[month_key] = []
                        monthly_counts[month_key].append(doc)

                for month_key, docs in monthly_counts.items():
                    first_deadline = min(d.retention_until for d in docs if d.retention_until)

                    alert = DeadlineAlert(
                        deadline_type=DeadlineType.RETENTION_EXPIRY,
                        entity_id=docs[0].id,  # Referenz auf erstes Dokument
                        entity_name=f"{len(docs)} Dokumente",
                        deadline_date=first_deadline,
                        urgency=_calculate_urgency(first_deadline),
                        action_url="/admin/retention",
                        action_label="Aufbewahrung prüfen",
                        metadata={
                            "document_count": len(docs),
                            "month": month_key,
                            "document_types": list({d.document_type for d in docs if d.document_type}),
                        },
                    )
                    alerts.append(alert)
            else:
                # Einzelne Insights für wenige Dokumente
                for doc in documents:
                    if doc.retention_until is None:
                        continue

                    alert = DeadlineAlert(
                        deadline_type=DeadlineType.RETENTION_EXPIRY,
                        entity_id=doc.id,
                        entity_name=doc.title or f"Dokument {doc.id}",
                        deadline_date=doc.retention_until,
                        urgency=_calculate_urgency(doc.retention_until),
                        action_url=f"/documents/{doc.id}",
                        action_label="Dokument prüfen",
                        metadata={
                            "document_type": doc.document_type,
                            "retention_years": 10,  # Standard GoBD
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        },
                    )
                    alerts.append(alert)

            insights = [alert.to_insight() for alert in alerts]

            logger.info(
                "retention_deadlines_checked",
                company_id=str(company_id),
                alerts_count=len(alerts),
                documents_expiring=len(documents),
            )

            return insights

        except Exception as e:
            logger.warning(
                "retention_deadline_check_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def get_deadline_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung aller Deadlines.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Zusammenfassung mit Counts pro Typ und Dringlichkeit
        """
        insights = await self.check_all_deadlines(db, company_id, days_ahead=30)

        summary: Dict[str, Any] = {
            "total_count": len(insights),
            "by_type": {},
            "by_urgency": {},
            "total_potential_value": Decimal("0"),
        }

        for insight in insights:
            # Nach Typ zaehlen
            rule_type = insight.source_rule or "unknown"
            if rule_type not in summary["by_type"]:
                summary["by_type"][rule_type] = 0
            summary["by_type"][rule_type] += 1

            # Nach Priorität zaehlen
            priority = insight.priority.value
            if priority not in summary["by_urgency"]:
                summary["by_urgency"][priority] = 0
            summary["by_urgency"][priority] += 1

            # Wert summieren
            if insight.potential_value:
                summary["total_potential_value"] += insight.potential_value

        return summary


# Singleton-Instanz
_deadline_insights_instance: Optional[DeadlineInsightsService] = None


def get_deadline_insights_service() -> DeadlineInsightsService:
    """Gibt die Singleton-Instanz des Deadline Insights Service zurück."""
    global _deadline_insights_instance
    if _deadline_insights_instance is None:
        _deadline_insights_instance = DeadlineInsightsService()
    return _deadline_insights_instance
