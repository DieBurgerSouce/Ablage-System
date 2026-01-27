# -*- coding: utf-8 -*-
"""
PredictiveActionService - Proaktive Handlungsvorschlaege.

Analysiert Geschaeftsdaten und generiert intelligente Vorschlaege:
1. Mahnung faellig → Vorschlag: "Mahnung senden"
2. Skonto-Frist naht → Vorschlag: "Skonto nutzen, spart X EUR"
3. Vertrag endet → Vorschlag: "Kuendigen oder verlaengern?"
4. Budget-Ueberschreitung → Vorschlag: "Budget anpassen"
5. Wiederkehrende Rechnung → Vorschlag: "Dauerauftrag einrichten"

Features:
- Multi-Channel Benachrichtigung (In-App, Email, Slack)
- Akzeptanz-Tracking fuer ML-Verbesserung
- Konfidenz-basierte Priorisierung
- Benutzer-Praeferenzen respektieren

Phase 2.2 der Feature-Roadmap (Januar 2026)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
import asyncio

import structlog
from sqlalchemy import select, and_, or_, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now

if TYPE_CHECKING:
    from app.services.notification_service import NotificationService
    from app.services.slack_service import SlackService

logger = structlog.get_logger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class ActionType(str, Enum):
    """Typen von vorgeschlagenen Aktionen."""

    # Mahnwesen
    SEND_DUNNING = "send_dunning"
    CALL_CUSTOMER = "call_customer"

    # Zahlungen
    USE_SKONTO = "use_skonto"
    PAY_INVOICE = "pay_invoice"
    SCHEDULE_PAYMENT = "schedule_payment"

    # Vertraege
    RENEW_CONTRACT = "renew_contract"
    CANCEL_CONTRACT = "cancel_contract"
    REVIEW_CONTRACT = "review_contract"

    # Budget
    ADJUST_BUDGET = "adjust_budget"
    REVIEW_SPENDING = "review_spending"

    # Dokumente
    ARCHIVE_DOCUMENT = "archive_document"
    COMPLETE_METADATA = "complete_metadata"

    # Prozesse
    SETUP_RECURRING = "setup_recurring"
    AUTOMATE_WORKFLOW = "automate_workflow"


class ActionPriority(str, Enum):
    """Prioritaet einer Aktion."""

    CRITICAL = "critical"  # Sofortige Aufmerksamkeit erforderlich
    HIGH = "high"  # Innerhalb 24h bearbeiten
    MEDIUM = "medium"  # Innerhalb einer Woche
    LOW = "low"  # Informativ, keine Eile


class ActionStatus(str, Enum):
    """Status einer vorgeschlagenen Aktion."""

    PENDING = "pending"  # Noch nicht angezeigt/bearbeitet
    SHOWN = "shown"  # Dem Benutzer angezeigt
    ACCEPTED = "accepted"  # Vom Benutzer akzeptiert
    REJECTED = "rejected"  # Vom Benutzer abgelehnt
    SNOOZED = "snoozed"  # Auf spaeter verschoben
    EXPIRED = "expired"  # Nicht mehr relevant
    EXECUTED = "executed"  # Automatisch ausgefuehrt


class TriggerType(str, Enum):
    """Ausloeser fuer Aktionsvorschlaege."""

    DUNNING_DUE = "dunning_due"
    SKONTO_EXPIRING = "skonto_expiring"
    CONTRACT_ENDING = "contract_ending"
    BUDGET_WARNING = "budget_warning"
    PAYMENT_DUE = "payment_due"
    RECURRING_PATTERN = "recurring_pattern"
    DOCUMENT_INCOMPLETE = "document_incomplete"
    ANOMALY_DETECTED = "anomaly_detected"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class PredictiveAction:
    """Ein vorgeschlagener Handlungsvorschlag."""

    id: uuid.UUID
    action_type: ActionType
    trigger_type: TriggerType
    priority: ActionPriority

    # Inhalt
    title: str
    description: str
    benefit_text: str  # z.B. "Spart 45,00 EUR"

    # Kontext
    target_id: uuid.UUID  # Invoice-ID, Document-ID, etc.
    target_type: str  # "invoice", "document", "contract", etc.
    company_id: uuid.UUID
    user_id: Optional[uuid.UUID]  # Optional: Spezifischer User

    # Konfidenz und Timing
    confidence: float  # 0.0 - 1.0
    deadline: Optional[datetime]  # Wann wird Aktion irrelevant?
    suggested_action_time: Optional[datetime]  # Optimaler Zeitpunkt

    # Zusaetzliche Daten
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Status
    status: ActionStatus = ActionStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    shown_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_feedback: Optional[str] = None


@dataclass
class ActionFeedback:
    """Feedback zu einer ausgefuehrten Aktion."""

    action_id: uuid.UUID
    user_id: uuid.UUID
    accepted: bool
    feedback_type: str  # "helpful", "not_helpful", "wrong_timing", etc.
    feedback_text: Optional[str]
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ActionStatistics:
    """Statistiken zu Aktionsvorschlaegen."""

    period_start: datetime
    period_end: datetime

    # Gesamtzahlen
    total_suggested: int
    total_shown: int
    total_accepted: int
    total_rejected: int
    total_snoozed: int
    total_expired: int

    # Raten
    acceptance_rate: float
    effectiveness_rate: float  # Akzeptiert und positives Feedback

    # Nach Typ
    by_action_type: Dict[str, Dict[str, int]]
    by_trigger_type: Dict[str, Dict[str, int]]

    # Geschaetzter Nutzen
    estimated_savings: Decimal
    realized_savings: Decimal


@dataclass
class UserPreferences:
    """Benutzer-Praeferenzen fuer Aktionsvorschlaege."""

    user_id: uuid.UUID

    # Aktivierte Trigger
    enabled_triggers: List[TriggerType] = field(default_factory=list)

    # Benachrichtigungs-Kanaele
    notification_channels: List[str] = field(default_factory=lambda: ["in_app"])

    # Timing
    quiet_hours_start: Optional[int] = None  # 22 = 22:00
    quiet_hours_end: Optional[int] = None  # 8 = 08:00

    # Schwellwerte
    min_confidence: float = 0.7
    min_savings_threshold: Decimal = Decimal("5.00")

    # Snooze-Dauer (Standard)
    default_snooze_hours: int = 24


# ============================================================================
# Service
# ============================================================================


class PredictiveActionService:
    """Service fuer proaktive Handlungsvorschlaege.

    Analysiert kontinuierlich Geschaeftsdaten und generiert
    kontextbezogene Vorschlaege zur Optimierung von Prozessen.

    Features:
    - Multi-Trigger-System (Mahnungen, Skonto, Vertraege, etc.)
    - Konfidenz-basierte Priorisierung
    - Benutzer-Praeferenzen
    - Lern-Feedback-Loop
    """

    def __init__(
        self,
        notification_service: Optional[NotificationService] = None,
        slack_service: Optional[SlackService] = None,
    ) -> None:
        """Initialisiere PredictiveActionService.

        Args:
            notification_service: Optional NotificationService fuer Benachrichtigungen
            slack_service: Optional SlackService fuer Slack-Integration
        """
        self._notification_service = notification_service
        self._slack_service = slack_service

    @property
    def notification_service(self) -> NotificationService:
        """Lazy-Load NotificationService."""
        if self._notification_service is None:
            from app.services.notification_service import get_notification_service
            self._notification_service = get_notification_service()
        return self._notification_service

    @property
    def slack_service(self) -> Optional[SlackService]:
        """Lazy-Load SlackService."""
        if self._slack_service is None:
            try:
                from app.services.slack_service import get_slack_service
                self._slack_service = get_slack_service()
            except ImportError:
                self._slack_service = None
        return self._slack_service

    # ========================================================================
    # Core Methods
    # ========================================================================

    async def generate_actions_for_company(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[PredictiveAction]:
        """Generiere alle relevanten Aktionsvorschlaege fuer eine Firma.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Optional Benutzer-ID fuer personalisierte Vorschlaege

        Returns:
            Liste von PredictiveActions sortiert nach Prioritaet
        """
        actions: List[PredictiveAction] = []

        # 1. Mahnungs-Vorschlaege
        dunning_actions = await self._generate_dunning_actions(db, company_id)
        actions.extend(dunning_actions)

        # 2. Skonto-Vorschlaege
        skonto_actions = await self._generate_skonto_actions(db, company_id)
        actions.extend(skonto_actions)

        # 3. Vertrags-Vorschlaege
        contract_actions = await self._generate_contract_actions(db, company_id)
        actions.extend(contract_actions)

        # 4. Budget-Vorschlaege
        budget_actions = await self._generate_budget_actions(db, company_id)
        actions.extend(budget_actions)

        # 5. Zahlungs-Vorschlaege
        payment_actions = await self._generate_payment_actions(db, company_id)
        actions.extend(payment_actions)

        # Sortiere nach Prioritaet und Konfidenz
        priority_order = {
            ActionPriority.CRITICAL: 0,
            ActionPriority.HIGH: 1,
            ActionPriority.MEDIUM: 2,
            ActionPriority.LOW: 3,
        }

        actions.sort(key=lambda a: (priority_order[a.priority], -a.confidence))

        logger.info(
            "predictive_actions_generated",
            company_id=str(company_id),
            total_actions=len(actions),
            by_type={t.value: sum(1 for a in actions if a.action_type == t) for t in ActionType},
        )

        return actions

    async def get_pending_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        action_types: Optional[List[ActionType]] = None,
        min_priority: Optional[ActionPriority] = None,
    ) -> List[PredictiveAction]:
        """Hole ausstehende Aktionsvorschlaege.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            user_id: Optional Benutzer-ID
            limit: Maximale Anzahl
            action_types: Filter nach Aktionstypen
            min_priority: Minimale Prioritaet

        Returns:
            Liste von PredictiveActions
        """
        # Generiere frische Vorschlaege
        all_actions = await self.generate_actions_for_company(db, company_id, user_id)

        # Filter anwenden
        filtered = all_actions

        if action_types:
            filtered = [a for a in filtered if a.action_type in action_types]

        if min_priority:
            priority_order = {
                ActionPriority.CRITICAL: 0,
                ActionPriority.HIGH: 1,
                ActionPriority.MEDIUM: 2,
                ActionPriority.LOW: 3,
            }
            min_order = priority_order[min_priority]
            filtered = [a for a in filtered if priority_order[a.priority] <= min_order]

        return filtered[:limit]

    async def accept_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
        execute_action: bool = False,
    ) -> Tuple[bool, str]:
        """Akzeptiere einen Aktionsvorschlag.

        Args:
            db: Datenbank-Session
            action: Der Aktionsvorschlag
            user_id: Benutzer-ID
            execute_action: Soll die Aktion direkt ausgefuehrt werden?

        Returns:
            Tuple: (success, message)
        """
        action.status = ActionStatus.ACCEPTED
        action.resolved_at = utc_now()

        if execute_action:
            success, message = await self._execute_action(db, action, user_id)
            if success:
                action.status = ActionStatus.EXECUTED
            return success, message

        # Feedback speichern fuer ML-Training
        await self._record_feedback(
            db=db,
            action_id=action.id,
            user_id=user_id,
            accepted=True,
            feedback_type="accepted",
        )

        logger.info(
            "predictive_action_accepted",
            action_id=str(action.id),
            action_type=action.action_type.value,
            user_id=str(user_id),
        )

        return True, "Aktion akzeptiert"

    async def reject_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> bool:
        """Lehne einen Aktionsvorschlag ab.

        Args:
            db: Datenbank-Session
            action: Der Aktionsvorschlag
            user_id: Benutzer-ID
            reason: Optional Ablehnungsgrund

        Returns:
            True bei Erfolg
        """
        action.status = ActionStatus.REJECTED
        action.resolved_at = utc_now()
        action.resolution_feedback = reason

        # Feedback speichern fuer ML-Training
        await self._record_feedback(
            db=db,
            action_id=action.id,
            user_id=user_id,
            accepted=False,
            feedback_type="rejected",
            feedback_text=reason,
        )

        logger.info(
            "predictive_action_rejected",
            action_id=str(action.id),
            action_type=action.action_type.value,
            user_id=str(user_id),
            reason=reason,
        )

        return True

    async def snooze_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
        snooze_hours: int = 24,
    ) -> datetime:
        """Verschiebe einen Aktionsvorschlag.

        Args:
            db: Datenbank-Session
            action: Der Aktionsvorschlag
            user_id: Benutzer-ID
            snooze_hours: Stunden bis zur erneuten Anzeige

        Returns:
            Zeitpunkt der naechsten Anzeige
        """
        action.status = ActionStatus.SNOOZED
        snooze_until = utc_now() + timedelta(hours=snooze_hours)
        action.metadata["snoozed_until"] = snooze_until.isoformat()

        logger.info(
            "predictive_action_snoozed",
            action_id=str(action.id),
            user_id=str(user_id),
            snooze_until=snooze_until.isoformat(),
        )

        return snooze_until

    # ========================================================================
    # Trigger-spezifische Generatoren
    # ========================================================================

    async def _generate_dunning_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PredictiveAction]:
        """Generiere Mahnungs-Vorschlaege."""
        from app.db.models import InvoiceTracking

        actions: List[PredictiveAction] = []
        now = utc_now()

        # Finde ueberfaellige Rechnungen
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status == "overdue",
                InvoiceTracking.deleted_at.is_(None),
            )
        ).order_by(InvoiceTracking.due_date.asc())

        result = await db.execute(stmt)
        overdue_invoices = result.scalars().all()

        for invoice in overdue_invoices:
            if not invoice.due_date:
                continue

            days_overdue = (now.date() - invoice.due_date).days
            current_level = invoice.dunning_level or 0

            # Bestimme Prioritaet basierend auf Ueberfaelligkeit
            if days_overdue > 60 or current_level >= 3:
                priority = ActionPriority.CRITICAL
            elif days_overdue > 30 or current_level >= 2:
                priority = ActionPriority.HIGH
            elif days_overdue > 14:
                priority = ActionPriority.MEDIUM
            else:
                priority = ActionPriority.LOW

            # Bestimme Aktion basierend auf Mahnstufe
            if current_level >= 3:
                action_type = ActionType.CALL_CUSTOMER
                title = "Telefonische Nachverfolgung empfohlen"
                description = f"Rechnung {invoice.invoice_number} ist {days_overdue} Tage ueberfaellig (Mahnstufe {current_level}). Telefonischer Kontakt empfohlen."
                benefit = "Hoeherer Zahlungseingang"
            else:
                action_type = ActionType.SEND_DUNNING
                next_level = current_level + 1
                title = f"Mahnung Stufe {next_level} senden"
                description = f"Rechnung {invoice.invoice_number} ist {days_overdue} Tage ueberfaellig. Naechste Mahnstufe empfohlen."
                benefit = "Beschleunigter Zahlungseingang"

            # Konfidenz basierend auf Daten
            confidence = min(0.95, 0.70 + (days_overdue / 100))

            actions.append(PredictiveAction(
                id=uuid.uuid4(),
                action_type=action_type,
                trigger_type=TriggerType.DUNNING_DUE,
                priority=priority,
                title=title,
                description=description,
                benefit_text=benefit,
                target_id=invoice.id,
                target_type="invoice",
                company_id=company_id,
                user_id=None,
                confidence=confidence,
                deadline=None,
                suggested_action_time=utc_now(),
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": float(invoice.amount) if invoice.amount else 0,
                    "days_overdue": days_overdue,
                    "current_dunning_level": current_level,
                },
            ))

        return actions

    async def _generate_skonto_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PredictiveAction]:
        """Generiere Skonto-Vorschlaege."""
        from app.db.models import InvoiceTracking

        actions: List[PredictiveAction] = []
        now = utc_now()

        # Finde Rechnungen mit anstehenden Skonto-Fristen
        # Nur incoming Rechnungen (die wir bezahlen muessen)
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.skonto_deadline.isnot(None),
                InvoiceTracking.skonto_deadline > now,
                InvoiceTracking.skonto_used == False,
                InvoiceTracking.status.in_(["open", "sent"]),
                InvoiceTracking.deleted_at.is_(None),
            )
        ).order_by(InvoiceTracking.skonto_deadline.asc())

        result = await db.execute(stmt)
        invoices = result.scalars().all()

        for invoice in invoices:
            if not invoice.skonto_deadline or not invoice.skonto_percentage:
                continue

            days_remaining = (invoice.skonto_deadline - now).days

            # Berechne Ersparnis
            skonto_amount = Decimal(str(invoice.amount)) * Decimal(str(invoice.skonto_percentage)) / Decimal("100")
            skonto_amount = skonto_amount.quantize(Decimal("0.01"))

            # Prioritaet basierend auf verbleibender Zeit
            if days_remaining <= 1:
                priority = ActionPriority.CRITICAL
            elif days_remaining <= 3:
                priority = ActionPriority.HIGH
            elif days_remaining <= 7:
                priority = ActionPriority.MEDIUM
            else:
                priority = ActionPriority.LOW

            # Konfidenz: Hoher Skonto = Hohe Konfidenz
            confidence = min(0.95, 0.80 + (float(invoice.skonto_percentage) / 20))

            actions.append(PredictiveAction(
                id=uuid.uuid4(),
                action_type=ActionType.USE_SKONTO,
                trigger_type=TriggerType.SKONTO_EXPIRING,
                priority=priority,
                title=f"Skonto nutzen - {invoice.skonto_percentage}% sparen",
                description=f"Rechnung {invoice.invoice_number}: Bei Zahlung bis {invoice.skonto_deadline.strftime('%d.%m.%Y')} sparen Sie {skonto_amount} EUR.",
                benefit_text=f"Spart {skonto_amount} EUR",
                target_id=invoice.id,
                target_type="invoice",
                company_id=company_id,
                user_id=None,
                confidence=confidence,
                deadline=invoice.skonto_deadline,
                suggested_action_time=utc_now(),
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": float(invoice.amount) if invoice.amount else 0,
                    "skonto_percentage": invoice.skonto_percentage,
                    "skonto_amount": float(skonto_amount),
                    "days_remaining": days_remaining,
                    "skonto_deadline": invoice.skonto_deadline.isoformat(),
                },
            ))

        return actions

    async def _generate_contract_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PredictiveAction]:
        """Generiere Vertrags-Vorschlaege.

        Hinweis: Erfordert Contract-Tracking Modell (nicht in allen Installationen).
        """
        actions: List[PredictiveAction] = []

        # Versuche Contract-Model zu laden
        try:
            from app.db.models import ContractTracking
        except ImportError:
            # Contract-Tracking nicht verfuegbar
            return actions

        now = utc_now()

        # Finde Vertraege die in 30 Tagen auslaufen
        warning_date = now + timedelta(days=30)

        stmt = select(ContractTracking).where(
            and_(
                ContractTracking.company_id == company_id,
                ContractTracking.end_date.isnot(None),
                ContractTracking.end_date <= warning_date,
                ContractTracking.end_date > now,
                ContractTracking.status == "active",
            )
        ).order_by(ContractTracking.end_date.asc())

        try:
            result = await db.execute(stmt)
            contracts = result.scalars().all()
        except Exception:
            # Tabelle existiert nicht
            return actions

        for contract in contracts:
            days_remaining = (contract.end_date - now).days

            # Prioritaet basierend auf verbleibender Zeit
            if days_remaining <= 7:
                priority = ActionPriority.CRITICAL
            elif days_remaining <= 14:
                priority = ActionPriority.HIGH
            else:
                priority = ActionPriority.MEDIUM

            # Entscheide ob Verlaengerung oder Kuendigung
            if getattr(contract, 'auto_renewal', False):
                action_type = ActionType.REVIEW_CONTRACT
                title = "Vertrag vor Auto-Verlaengerung pruefen"
                description = f"Vertrag '{contract.name}' verlaengert sich automatisch am {contract.end_date.strftime('%d.%m.%Y')}. Jetzt pruefen."
            else:
                action_type = ActionType.RENEW_CONTRACT
                title = "Vertragsverlaengerung pruefen"
                description = f"Vertrag '{contract.name}' endet am {contract.end_date.strftime('%d.%m.%Y')}. Entscheidung erforderlich."

            actions.append(PredictiveAction(
                id=uuid.uuid4(),
                action_type=action_type,
                trigger_type=TriggerType.CONTRACT_ENDING,
                priority=priority,
                title=title,
                description=description,
                benefit_text="Rechtzeitige Entscheidung",
                target_id=contract.id,
                target_type="contract",
                company_id=company_id,
                user_id=None,
                confidence=0.95,  # Vertragsdaten sind zuverlaessig
                deadline=contract.end_date,
                suggested_action_time=utc_now(),
                metadata={
                    "contract_name": contract.name,
                    "end_date": contract.end_date.isoformat(),
                    "days_remaining": days_remaining,
                    "auto_renewal": getattr(contract, 'auto_renewal', False),
                },
            ))

        return actions

    async def _generate_budget_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PredictiveAction]:
        """Generiere Budget-Vorschlaege."""
        actions: List[PredictiveAction] = []

        # Versuche Budget-Model zu laden
        try:
            from app.db.models_budget import Budget, BudgetLine
        except ImportError:
            return actions

        # Finde aktive Budgets mit Ueberschreitungsrisiko
        stmt = select(Budget).where(
            and_(
                Budget.company_id == company_id,
                Budget.status == "active",
            )
        )

        try:
            result = await db.execute(stmt)
            budgets = result.scalars().all()
        except Exception:
            return actions

        for budget in budgets:
            utilization = 0.0
            if budget.total_planned and budget.total_planned > 0:
                utilization = (budget.total_actual / budget.total_planned) * 100

            if utilization >= 90:
                priority = ActionPriority.HIGH if utilization >= 100 else ActionPriority.MEDIUM

                if utilization >= 100:
                    title = "Budget ueberschritten"
                    description = f"Budget '{budget.name}' ist zu {utilization:.1f}% ausgeschoepft. Anpassung empfohlen."
                else:
                    title = "Budget-Warnung"
                    description = f"Budget '{budget.name}' ist zu {utilization:.1f}% ausgeschoepft. Ueberpruefung empfohlen."

                actions.append(PredictiveAction(
                    id=uuid.uuid4(),
                    action_type=ActionType.ADJUST_BUDGET if utilization >= 100 else ActionType.REVIEW_SPENDING,
                    trigger_type=TriggerType.BUDGET_WARNING,
                    priority=priority,
                    title=title,
                    description=description,
                    benefit_text="Kostenueberblick behalten",
                    target_id=budget.id,
                    target_type="budget",
                    company_id=company_id,
                    user_id=None,
                    confidence=0.90,
                    deadline=budget.end_date,
                    suggested_action_time=utc_now(),
                    metadata={
                        "budget_name": budget.name,
                        "total_planned": float(budget.total_planned),
                        "total_actual": float(budget.total_actual),
                        "utilization_percent": utilization,
                    },
                ))

        return actions

    async def _generate_payment_actions(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PredictiveAction]:
        """Generiere Zahlungs-Vorschlaege."""
        from app.db.models import InvoiceTracking

        actions: List[PredictiveAction] = []
        now = utc_now()

        # Finde bald faellige Rechnungen (incoming)
        warning_date = now + timedelta(days=7)

        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.due_date.isnot(None),
                InvoiceTracking.due_date <= warning_date,
                InvoiceTracking.due_date >= now.date(),
                InvoiceTracking.status == "open",
                InvoiceTracking.deleted_at.is_(None),
            )
        ).order_by(InvoiceTracking.due_date.asc())

        result = await db.execute(stmt)
        invoices = result.scalars().all()

        for invoice in invoices:
            if not invoice.due_date:
                continue

            days_remaining = (invoice.due_date - now.date()).days

            # Prioritaet basierend auf Faelligkeit
            if days_remaining <= 1:
                priority = ActionPriority.HIGH
            elif days_remaining <= 3:
                priority = ActionPriority.MEDIUM
            else:
                priority = ActionPriority.LOW

            actions.append(PredictiveAction(
                id=uuid.uuid4(),
                action_type=ActionType.PAY_INVOICE,
                trigger_type=TriggerType.PAYMENT_DUE,
                priority=priority,
                title="Zahlung vorbereiten",
                description=f"Rechnung {invoice.invoice_number} ist in {days_remaining} Tag(en) faellig.",
                benefit_text="Zahlungsverzug vermeiden",
                target_id=invoice.id,
                target_type="invoice",
                company_id=company_id,
                user_id=None,
                confidence=0.95,
                deadline=datetime.combine(invoice.due_date, datetime.min.time()),
                suggested_action_time=utc_now(),
                metadata={
                    "invoice_number": invoice.invoice_number,
                    "amount": float(invoice.amount) if invoice.amount else 0,
                    "due_date": invoice.due_date.isoformat(),
                    "days_remaining": days_remaining,
                },
            ))

        return actions

    # ========================================================================
    # Action Execution
    # ========================================================================

    async def _execute_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
    ) -> Tuple[bool, str]:
        """Fuehre eine Aktion aus.

        Args:
            db: Datenbank-Session
            action: Die auszufuehrende Aktion
            user_id: Benutzer-ID

        Returns:
            Tuple: (success, message)
        """
        if action.action_type == ActionType.SEND_DUNNING:
            return await self._execute_dunning_action(db, action, user_id)

        elif action.action_type == ActionType.USE_SKONTO:
            return await self._execute_skonto_action(db, action, user_id)

        # Andere Aktionen sind nicht automatisch ausfuehrbar
        return False, "Aktion erfordert manuelle Bearbeitung"

    async def _execute_dunning_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
    ) -> Tuple[bool, str]:
        """Fuehre Mahnungs-Aktion aus."""
        from app.db.models import InvoiceTracking

        stmt = select(InvoiceTracking).where(
            InvoiceTracking.id == action.target_id
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            return False, "Rechnung nicht gefunden"

        # Erhoehe Mahnstufe
        old_level = invoice.dunning_level or 0
        new_level = min(old_level + 1, 4)

        invoice.dunning_level = new_level
        invoice.last_dunning_date = utc_now().date()
        invoice.updated_at = utc_now()

        await db.flush()

        logger.info(
            "dunning_executed_via_predictive_action",
            invoice_id=str(invoice.id),
            old_level=old_level,
            new_level=new_level,
            user_id=str(user_id),
        )

        return True, f"Mahnstufe auf {new_level} erhoeht"

    async def _execute_skonto_action(
        self,
        db: AsyncSession,
        action: PredictiveAction,
        user_id: uuid.UUID,
    ) -> Tuple[bool, str]:
        """Markiere Skonto als angewendet (Zahlungsplanung)."""
        # Dies ist eher ein Hinweis - Zahlung muss manuell erfolgen
        return False, "Skonto-Zahlung muss manuell durchgefuehrt werden"

    # ========================================================================
    # Feedback and Learning
    # ========================================================================

    async def _record_feedback(
        self,
        db: AsyncSession,
        action_id: uuid.UUID,
        user_id: uuid.UUID,
        accepted: bool,
        feedback_type: str,
        feedback_text: Optional[str] = None,
    ) -> None:
        """Speichere Feedback fuer ML-Training.

        Hinweis: In Produktion wuerde dies in einer separaten Tabelle
        gespeichert und fuer Model-Training verwendet.
        """
        # Feedback wird in strukturierten Logs gespeichert fuer ML-Training
        # FUTURE: Wenn ActionFeedback-Tabelle erstellt, hier persistieren:
        #   await db.execute(insert(ActionFeedback).values(
        #       action_id=action_id, user_id=user_id, accepted=accepted,
        #       feedback_type=feedback_type, feedback_text=feedback_text
        #   ))
        logger.info(
            "predictive_action_feedback",
            action_id=str(action_id),
            user_id=str(user_id),
            accepted=accepted,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            # Strukturierte Daten fuer spaeteren Log-Export zu ML-Pipeline
            ml_training_data={
                "action_id": str(action_id),
                "accepted": accepted,
                "feedback_type": feedback_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def get_action_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> ActionStatistics:
        """Hole Statistiken zu Aktionsvorschlaegen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            start_date: Startdatum
            end_date: Enddatum

        Returns:
            ActionStatistics
        """
        # Placeholder - in Produktion aus Datenbank laden
        return ActionStatistics(
            period_start=start_date,
            period_end=end_date,
            total_suggested=0,
            total_shown=0,
            total_accepted=0,
            total_rejected=0,
            total_snoozed=0,
            total_expired=0,
            acceptance_rate=0.0,
            effectiveness_rate=0.0,
            by_action_type={},
            by_trigger_type={},
            estimated_savings=Decimal("0.00"),
            realized_savings=Decimal("0.00"),
        )

    # ========================================================================
    # Notifications
    # ========================================================================

    async def send_action_notifications(
        self,
        db: AsyncSession,
        actions: List[PredictiveAction],
        user_preferences: Optional[UserPreferences] = None,
    ) -> Dict[str, int]:
        """Sende Benachrichtigungen fuer Aktionsvorschlaege.

        Args:
            db: Datenbank-Session
            actions: Liste von Aktionen
            user_preferences: Optional Benutzer-Praeferenzen

        Returns:
            Dict mit Anzahl gesendeter Benachrichtigungen pro Kanal
        """
        channels = user_preferences.notification_channels if user_preferences else ["in_app"]
        sent_counts = {channel: 0 for channel in channels}

        # Nur kritische und hohe Prioritaet benachrichtigen
        important_actions = [
            a for a in actions
            if a.priority in [ActionPriority.CRITICAL, ActionPriority.HIGH]
        ]

        if not important_actions:
            return sent_counts

        # In-App Benachrichtigungen
        if "in_app" in channels:
            for action in important_actions:
                if action.user_id:
                    try:
                        await self.notification_service.notify(
                            notification_type="predictive_action",
                            context={
                                "action_id": str(action.id),
                                "title": action.title,
                                "description": action.description,
                                "priority": action.priority.value,
                                "benefit": action.benefit_text,
                            },
                            user_id=str(action.user_id),
                            priority="high" if action.priority == ActionPriority.CRITICAL else "normal",
                        )
                        sent_counts["in_app"] += 1
                    except Exception as e:
                        logger.warning(
                            "predictive_action_notification_failed",
                            action_id=str(action.id),
                            channel="in_app",
                            error=str(e),
                        )

        # Slack Benachrichtigungen
        if "slack" in channels and self.slack_service:
            for action in important_actions:
                if action.priority == ActionPriority.CRITICAL:
                    try:
                        await self.slack_service.send_message(
                            message=f"*{action.title}*\n{action.description}\n_{action.benefit_text}_",
                            channel=None,  # Default channel
                        )
                        sent_counts["slack"] += 1
                    except Exception as e:
                        logger.warning(
                            "predictive_action_notification_failed",
                            action_id=str(action.id),
                            channel="slack",
                            error=str(e),
                        )

        return sent_counts


# ============================================================================
# Factory Function
# ============================================================================


_predictive_action_service: Optional[PredictiveActionService] = None


def get_predictive_action_service() -> PredictiveActionService:
    """Factory-Funktion fuer PredictiveActionService Singleton.

    Returns:
        PredictiveActionService Instanz
    """
    global _predictive_action_service
    if _predictive_action_service is None:
        _predictive_action_service = PredictiveActionService()
    return _predictive_action_service
