# -*- coding: utf-8 -*-
"""
Action Approval Queue.

Enterprise Feature: Warteschlange für KI-vorgeschlagene Aktionen.

Features:
- Queue für ausstehende Genehmigungen (DB-persistent!)
- Bulk-Approval für mehrere Aktionen
- Timeout-basierte Auto-Genehmigung (konfigurierbar)
- Prioritäts-basierte Sortierung

ENTERPRISE-GRADE: Verwendet PendingAction DB-Modell für Persistenz.
"""

from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import TypedDict
from uuid import UUID, uuid4

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.autonomy.autonomy_level import (
    ActionCategory,
    AutonomyDecision,
    AutonomyLevel,
    can_auto_execute,
)


# Prometheus Metrics
ACTIONS_QUEUED = Counter(
    "autonomy_actions_queued_total",
    "Gesamtzahl der in die Queue eingefügten Aktionen",
    ["category", "company_id"],
)
ACTIONS_APPROVED = Counter(
    "autonomy_actions_approved_total",
    "Gesamtzahl der genehmigten Aktionen",
    ["category", "approval_type"],  # approval_type: auto, manual, timeout
)
ACTIONS_REJECTED = Counter(
    "autonomy_actions_rejected_total",
    "Gesamtzahl der abgelehnten Aktionen",
    ["category", "reason"],
)
QUEUE_SIZE = Gauge(
    "autonomy_queue_size",
    "Aktuelle Größe der Approval-Queue",
    ["company_id", "priority"],
)
APPROVAL_TIME = Histogram(
    "autonomy_approval_time_seconds",
    "Zeit bis zur Genehmigung/Ablehnung",
    ["category", "approval_type"],
    buckets=[1, 5, 15, 60, 300, 900, 3600, 86400],
)


class ActionStatus(str, Enum):
    """Status einer Aktion in der Queue."""

    PENDING = "pending"           # Wartet auf Genehmigung
    APPROVED = "approved"         # Manuell genehmigt
    AUTO_APPROVED = "auto_approved"  # Automatisch genehmigt
    TIMEOUT_APPROVED = "timeout_approved"  # Nach Timeout genehmigt
    REJECTED = "rejected"         # Abgelehnt
    CANCELLED = "cancelled"       # Abgebrochen
    EXECUTED = "executed"         # Ausgeführt
    FAILED = "failed"             # Ausführung fehlgeschlagen


class ActionPriority(IntEnum):
    """Priorität einer Aktion."""

    CRITICAL = 1   # Sofort bearbeiten
    HIGH = 2       # Innerhalb von Minuten
    NORMAL = 3     # Normale Bearbeitung
    LOW = 4        # Kann warten
    BACKGROUND = 5  # Hintergrund


class QueuedActionData(TypedDict):
    """Daten einer Aktion in der Queue."""

    id: str
    action_type: str
    category: str
    description: str
    parameters: dict
    confidence: float
    priority: int
    status: str
    company_id: str
    user_id: str | None
    created_at: str
    timeout_at: str | None
    auto_approve_on_timeout: bool
    autonomy_decision: dict
    execution_result: dict | None
    approved_by: str | None
    rejected_reason: str | None
    metadata: dict


class QueueStats(TypedDict):
    """Statistiken der Action Queue."""

    total_pending: int
    by_priority: dict[str, int]
    by_category: dict[str, int]
    avg_wait_time_seconds: float
    oldest_pending_age_seconds: float
    auto_approved_today: int
    manual_approved_today: int
    rejected_today: int


class ActionApprovalQueue:
    """
    Warteschlange für KI-vorgeschlagene Aktionen.

    Verwaltet ausstehende Genehmigungen mit:
    - DB-Persistenz via PendingAction Modell
    - Prioritäts-basierter Sortierung
    - Timeout-basierter Auto-Genehmigung
    - Bulk-Approval-Funktionalität
    """

    _instance: "ActionApprovalQueue | None" = None

    def __new__(cls) -> "ActionApprovalQueue":
        """Singleton Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _priority_to_db(self, priority: ActionPriority) -> int:
        """Konvertiert ActionPriority zu DB-Priorität (0-100)."""
        # IntEnum 1-5 -> DB 100-0 (höhere Zahl = höhere Prio)
        return 100 - (priority * 20)

    def _db_to_priority(self, db_priority: int) -> int:
        """Konvertiert DB-Priorität zu ActionPriority-Wert."""
        # DB 100-0 -> IntEnum 1-5
        return max(1, min(5, (100 - db_priority) // 20 + 1))

    async def enqueue(
        self,
        db: AsyncSession,
        company_id: UUID,
        action_type: str,
        category: ActionCategory,
        description: str,
        parameters: dict,
        confidence: float,
        autonomy_level: AutonomyLevel,
        priority: ActionPriority = ActionPriority.NORMAL,
        user_id: UUID | None = None,
        timeout_minutes: int | None = None,
        auto_approve_on_timeout: bool = False,
        metadata: dict | None = None,
    ) -> QueuedActionData:
        """
        Fügt eine Aktion zur Genehmigungsqueue hinzu.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            action_type: Aktionstyp (z.B. "create_payment_run")
            category: Aktionskategorie
            description: Lesbare Beschreibung
            parameters: Aktionsparameter
            confidence: KI-Confidence (0.0 - 1.0)
            autonomy_level: Aktuelles Autonomie-Level
            priority: Priorität
            user_id: Optional - auslösender Benutzer
            timeout_minutes: Optional - Minuten bis Timeout
            auto_approve_on_timeout: Bei Timeout automatisch genehmigen
            metadata: Zusätzliche Metadaten

        Returns:
            QueuedActionData der eingefügten Aktion
        """
        # Import hier um Circular Imports zu vermeiden
        from app.db.models_autonomy import PendingAction, PendingActionStatus, RoutingDecision

        # Prüfe ob Auto-Ausführung möglich
        decision = can_auto_execute(autonomy_level, category, confidence)

        # Bestimme Routing-Entscheidung für DB
        if decision["can_auto_execute"]:
            routing = RoutingDecision.AUTO_EXECUTE
            status = PendingActionStatus.AUTO_APPROVED
        elif confidence >= 0.80:
            routing = RoutingDecision.SUGGEST_AND_CONFIRM
            status = PendingActionStatus.PENDING
        else:
            routing = RoutingDecision.MANUAL_REVIEW
            status = PendingActionStatus.PENDING

        # Berechne Timeout
        timeout_hours = timeout_minutes / 60 if timeout_minutes else 24
        expires_at = datetime.utcnow() + timedelta(hours=timeout_hours)

        # Erstelle DB-Eintrag
        action_id = uuid4()
        pending_action = PendingAction(
            id=action_id,
            company_id=company_id,
            action_type=action_type,
            action_category=category.name.lower(),
            description=description,
            detailed_description=metadata.get("detailed_description") if metadata else None,
            status=status.value,
            confidence=confidence,
            routing_decision=routing.value,
            reason=decision.get("reason"),
            parameters=parameters,
            affected_entities=metadata.get("affected_entities") if metadata else None,
            estimated_impact=metadata.get("estimated_impact") if metadata else None,
            source_type=metadata.get("source_type") if metadata else "api",
            source_id=metadata.get("source_id") if metadata else None,
            priority=self._priority_to_db(priority),
            expires_at=expires_at,
        )

        db.add(pending_action)
        await db.commit()
        await db.refresh(pending_action)

        # Erstelle Response-Objekt
        action_data = QueuedActionData(
            id=str(action_id),
            action_type=action_type,
            category=category.name,
            description=description,
            parameters=parameters,
            confidence=confidence,
            priority=priority,
            status=status.value,
            company_id=str(company_id),
            user_id=str(user_id) if user_id else None,
            created_at=pending_action.created_at.isoformat(),
            timeout_at=expires_at.isoformat(),
            auto_approve_on_timeout=auto_approve_on_timeout,
            autonomy_decision=decision,
            execution_result=None,
            approved_by=None,
            rejected_reason=None,
            metadata=metadata or {},
        )

        # Metrics
        company_key = str(company_id)
        ACTIONS_QUEUED.labels(
            category=category.name,
            company_id=company_key,
        ).inc()

        if decision["can_auto_execute"]:
            ACTIONS_APPROVED.labels(
                category=category.name,
                approval_type="auto",
            ).inc()

        return action_data

    async def get_pending(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 50,
        priority_filter: ActionPriority | None = None,
        category_filter: ActionCategory | None = None,
    ) -> list[QueuedActionData]:
        """
        Holt ausstehende Aktionen aus der Queue.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            limit: Maximale Anzahl
            priority_filter: Optional - nur bestimmte Priorität
            category_filter: Optional - nur bestimmte Kategorie

        Returns:
            Liste der ausstehenden Aktionen
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        # Query aufbauen
        query = select(PendingAction).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        )

        if priority_filter:
            db_priority = self._priority_to_db(priority_filter)
            query = query.where(PendingAction.priority == db_priority)

        if category_filter:
            query = query.where(
                PendingAction.action_category == category_filter.name.lower()
            )

        query = query.order_by(
            PendingAction.priority.desc(),  # Höhere Priorität zuerst
            PendingAction.created_at.asc(),  # Ältere zuerst bei gleicher Prio
        ).limit(limit)

        result = await db.execute(query)
        actions = result.scalars().all()

        return [
            QueuedActionData(
                id=str(action.id),
                action_type=action.action_type,
                category=action.action_category.upper(),
                description=action.description,
                parameters=action.parameters or {},
                confidence=action.confidence,
                priority=self._db_to_priority(action.priority),
                status=action.status,
                company_id=str(action.company_id),
                user_id=None,
                created_at=action.created_at.isoformat(),
                timeout_at=action.expires_at.isoformat() if action.expires_at else None,
                auto_approve_on_timeout=False,
                autonomy_decision={
                    "routing": action.routing_decision,
                    "reason": action.reason,
                },
                execution_result=action.execution_result,
                approved_by=str(action.approved_by_id) if action.approved_by_id else None,
                rejected_reason=action.rejection_reason,
                metadata={},
            )
            for action in actions
        ]

    async def approve(
        self,
        db: AsyncSession,
        company_id: UUID,
        action_id: str,
        approved_by: UUID,
        comment: str | None = None,
    ) -> QueuedActionData | None:
        """
        Genehmigt eine Aktion manuell.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            action_id: Aktions-ID
            approved_by: Genehmigender Benutzer
            comment: Optionaler Kommentar

        Returns:
            Aktualisierte Aktion oder None
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        # Aktion holen
        query = select(PendingAction).where(
            and_(
                PendingAction.id == UUID(action_id),
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        )
        result = await db.execute(query)
        action = result.scalar_one_or_none()

        if not action:
            return None

        # Update
        now = datetime.utcnow()
        action.status = PendingActionStatus.APPROVED.value
        action.approved_by_id = approved_by
        action.approved_at = now
        if comment:
            action.parameters = {**(action.parameters or {}), "approval_comment": comment}

        await db.commit()
        await db.refresh(action)

        # Metrics
        created = action.created_at
        duration = (now - created).total_seconds()
        APPROVAL_TIME.labels(
            category=action.action_category,
            approval_type="manual",
        ).observe(duration)
        ACTIONS_APPROVED.labels(
            category=action.action_category,
            approval_type="manual",
        ).inc()

        return QueuedActionData(
            id=str(action.id),
            action_type=action.action_type,
            category=action.action_category.upper(),
            description=action.description,
            parameters=action.parameters or {},
            confidence=action.confidence,
            priority=self._db_to_priority(action.priority),
            status=action.status,
            company_id=str(action.company_id),
            user_id=None,
            created_at=action.created_at.isoformat(),
            timeout_at=action.expires_at.isoformat() if action.expires_at else None,
            auto_approve_on_timeout=False,
            autonomy_decision={"routing": action.routing_decision},
            execution_result=action.execution_result,
            approved_by=str(action.approved_by_id),
            rejected_reason=None,
            metadata={},
        )

    async def reject(
        self,
        db: AsyncSession,
        company_id: UUID,
        action_id: str,
        rejected_by: UUID,
        reason: str,
    ) -> QueuedActionData | None:
        """
        Lehnt eine Aktion ab.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            action_id: Aktions-ID
            rejected_by: Ablehnender Benutzer
            reason: Ablehnungsgrund

        Returns:
            Aktualisierte Aktion oder None
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        # Aktion holen
        query = select(PendingAction).where(
            and_(
                PendingAction.id == UUID(action_id),
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        )
        result = await db.execute(query)
        action = result.scalar_one_or_none()

        if not action:
            return None

        # Update
        action.status = PendingActionStatus.REJECTED.value
        action.rejection_reason = reason
        action.parameters = {**(action.parameters or {}), "rejected_by": str(rejected_by)}

        await db.commit()
        await db.refresh(action)

        # Metrics
        ACTIONS_REJECTED.labels(
            category=action.action_category,
            reason="manual",
        ).inc()

        return QueuedActionData(
            id=str(action.id),
            action_type=action.action_type,
            category=action.action_category.upper(),
            description=action.description,
            parameters=action.parameters or {},
            confidence=action.confidence,
            priority=self._db_to_priority(action.priority),
            status=action.status,
            company_id=str(action.company_id),
            user_id=None,
            created_at=action.created_at.isoformat(),
            timeout_at=action.expires_at.isoformat() if action.expires_at else None,
            auto_approve_on_timeout=False,
            autonomy_decision={"routing": action.routing_decision},
            execution_result=None,
            approved_by=None,
            rejected_reason=action.rejection_reason,
            metadata={},
        )

    async def bulk_approve(
        self,
        db: AsyncSession,
        company_id: UUID,
        action_ids: list[str],
        approved_by: UUID,
    ) -> dict[str, bool]:
        """
        Genehmigt mehrere Aktionen auf einmal.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            action_ids: Liste der Aktions-IDs
            approved_by: Genehmigender Benutzer

        Returns:
            Dict mit action_id -> success
        """
        results: dict[str, bool] = {}

        for action_id in action_ids:
            action = await self.approve(db, company_id, action_id, approved_by)
            results[action_id] = action is not None

        return results

    async def process_timeouts(self, db: AsyncSession) -> int:
        """
        Verarbeitet abgelaufene Timeouts.

        Wird periodisch aufgerufen um Aktionen mit
        abgelaufenem Timeout zu bearbeiten.

        Args:
            db: Datenbank-Session

        Returns:
            Anzahl der verarbeiteten Aktionen
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        now = datetime.utcnow()

        # Finde abgelaufene Aktionen
        query = select(PendingAction).where(
            and_(
                PendingAction.status == PendingActionStatus.PENDING.value,
                PendingAction.expires_at <= now,
            )
        )
        result = await db.execute(query)
        expired_actions = result.scalars().all()

        processed = 0
        for action in expired_actions:
            # Markiere als expired
            action.status = PendingActionStatus.EXPIRED.value
            ACTIONS_REJECTED.labels(
                category=action.action_category,
                reason="timeout",
            ).inc()
            processed += 1

        if processed > 0:
            await db.commit()

        return processed

    async def get_stats(self, db: AsyncSession, company_id: UUID) -> QueueStats:
        """
        Holt Statistiken der Queue.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID

        Returns:
            QueueStats mit Zusammenfassung
        """
        from app.db.models_autonomy import PendingAction, PendingActionStatus

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Zähle pending nach Priorität
        priority_query = select(
            PendingAction.priority,
            func.count(PendingAction.id)
        ).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        ).group_by(PendingAction.priority)
        priority_result = await db.execute(priority_query)
        by_priority = {str(p): c for p, c in priority_result.fetchall()}

        # Zähle pending nach Kategorie
        category_query = select(
            PendingAction.action_category,
            func.count(PendingAction.id)
        ).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        ).group_by(PendingAction.action_category)
        category_result = await db.execute(category_query)
        by_category = {c.upper(): cnt for c, cnt in category_result.fetchall()}

        # Statistiken für heute
        today_query = select(
            PendingAction.status,
            func.count(PendingAction.id)
        ).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.created_at >= today_start,
            )
        ).group_by(PendingAction.status)
        today_result = await db.execute(today_query)
        today_stats = {s: c for s, c in today_result.fetchall()}

        # Durchschnittliche Wartezeit für pending
        avg_wait_query = select(
            func.avg(func.extract('epoch', now - PendingAction.created_at))
        ).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        )
        avg_result = await db.execute(avg_wait_query)
        avg_wait = avg_result.scalar() or 0.0

        # Älteste pending Aktion
        oldest_query = select(
            func.min(PendingAction.created_at)
        ).where(
            and_(
                PendingAction.company_id == company_id,
                PendingAction.status == PendingActionStatus.PENDING.value,
            )
        )
        oldest_result = await db.execute(oldest_query)
        oldest = oldest_result.scalar()
        oldest_age = (now - oldest).total_seconds() if oldest else 0.0

        total_pending = sum(by_priority.values())

        return QueueStats(
            total_pending=total_pending,
            by_priority=by_priority,
            by_category=by_category,
            avg_wait_time_seconds=float(avg_wait),
            oldest_pending_age_seconds=oldest_age,
            auto_approved_today=today_stats.get(PendingActionStatus.AUTO_APPROVED.value, 0),
            manual_approved_today=today_stats.get(PendingActionStatus.APPROVED.value, 0),
            rejected_today=today_stats.get(PendingActionStatus.REJECTED.value, 0),
        )


# Singleton Instance
_action_queue: ActionApprovalQueue | None = None


def get_action_queue() -> ActionApprovalQueue:
    """Gibt die Singleton-Instanz der ActionApprovalQueue zurück."""
    global _action_queue
    if _action_queue is None:
        _action_queue = ActionApprovalQueue()
    return _action_queue
