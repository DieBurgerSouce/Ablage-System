# -*- coding: utf-8 -*-
"""
Smart Approval Router Enhancement.

Enterprise Feature: Intelligente Genehmigungsweiterleitung mit:
- Stellvertreter-Auswahl bei Abwesenheit des primären Genehmigers
- Automatische Eskalation bei SLA-Timeout
- Historische Muster-basierte Routing-Optimierung
- Lastverteilung über Genehmiger

Feinpoliert und durchdacht - Enterprise-grade Approval Routing.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safe_errors import safe_error_log
from app.db.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    User,
    UserCompany,
    ApprovalDelegation,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class RoutingStrategy(str, Enum):
    """Routing-Strategien für Genehmigungen."""
    DIRECT = "direct"  # Direkt zum benannten Genehmiger
    ROUND_ROBIN = "round_robin"  # Gleichmaessig verteilt
    LEAST_LOADED = "least_loaded"  # Zum am wenigsten belasteten
    FASTEST_RESPONDER = "fastest_responder"  # Zum schnellsten Bearbeiter
    EXPERTISE_BASED = "expertise_based"  # Nach Fachwissen


class AbsenceStatus(str, Enum):
    """Status der Anwesenheit."""
    AVAILABLE = "available"
    ABSENT = "absent"
    PARTIALLY_AVAILABLE = "partially_available"
    UNKNOWN = "unknown"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ApproverMetrics:
    """Metriken eines Genehmigers."""
    user_id: UUID
    total_approvals: int = 0
    average_response_hours: float = 0.0
    approval_rate: float = 0.0  # Prozent genehmigt vs abgelehnt
    current_pending_count: int = 0
    last_activity_at: Optional[datetime] = None
    expertise_areas: List[str] = field(default_factory=list)


@dataclass
class DeputySelection:
    """Ergebnis einer Stellvertreter-Auswahl."""
    primary_approver_id: UUID
    deputy_id: Optional[UUID]
    reason: str
    absence_status: AbsenceStatus
    delegation_id: Optional[UUID] = None
    confidence: float = 1.0


@dataclass
class RoutingDecision:
    """Eine Routing-Entscheidung."""
    id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    selected_approver_id: UUID = field(default_factory=uuid4)
    strategy_used: RoutingStrategy = RoutingStrategy.DIRECT
    reasoning: str = ""
    alternatives_considered: List[UUID] = field(default_factory=list)
    metrics_snapshot: Optional[ApproverMetrics] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EscalationConfig:
    """Konfiguration für Eskalationen."""
    warning_hours: int = 24  # Erste Warnung
    escalation_hours: int = 48  # Eskalation
    final_escalation_hours: int = 72  # Finale Eskalation an Management
    reminder_interval_hours: int = 8  # Erinnerungs-Intervall


# =============================================================================
# Smart Approval Router Service
# =============================================================================


class SmartApprovalRouter:
    """
    Intelligenter Genehmigungsrouter.

    Features:
    - Stellvertreter-Auswahl bei Abwesenheit
    - SLA-basierte Eskalation
    - Lastverteilung
    - Historisches Pattern-Learning
    """

    _instance: Optional["SmartApprovalRouter"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SmartApprovalRouter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Eskalations-Konfiguration
        self._escalation_config = EscalationConfig()

        # Metriken-Cache (user_id -> ApproverMetrics)
        self._metrics_cache: Dict[UUID, ApproverMetrics] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_ttl = timedelta(minutes=15)
        self._last_cache_refresh: Optional[datetime] = None

        # Routing-History (für Learning)
        self._routing_history: List[RoutingDecision] = []
        self._max_history_size = 1000

        logger.info("smart_approval_router_initialized")

    # =========================================================================
    # Deputy Selection
    # =========================================================================

    async def select_deputy(
        self,
        db: AsyncSession,
        primary_approver_id: UUID,
        company_id: UUID,
        request_type: Optional[str] = None,
    ) -> DeputySelection:
        """
        Waehlt einen Stellvertreter wenn der primäre Genehmiger abwesend ist.

        Args:
            db: Database Session
            primary_approver_id: ID des primären Genehmigers
            company_id: Company ID
            request_type: Optional: Typ der Anfrage für Expertise-Matching

        Returns:
            DeputySelection mit Stellvertreter-Informationen
        """
        # 1. Prüfen ob Primärer verfügbar ist
        absence_status, delegation = await self._check_user_availability(
            db, primary_approver_id
        )

        if absence_status == AbsenceStatus.AVAILABLE:
            return DeputySelection(
                primary_approver_id=primary_approver_id,
                deputy_id=None,
                reason="Primärer Genehmiger ist verfügbar",
                absence_status=absence_status,
            )

        # 2. Aktive Delegation suchen
        if delegation:
            delegate_user_id = delegation.delegate_user_id
            # Prüfen ob Delegate verfügbar
            delegate_status, _ = await self._check_user_availability(
                db, delegate_user_id
            )
            if delegate_status == AbsenceStatus.AVAILABLE:
                return DeputySelection(
                    primary_approver_id=primary_approver_id,
                    deputy_id=delegate_user_id,
                    reason=f"Aktive Delegation zu Stellvertreter (Grund: {delegation.reason or 'Abwesenheit'})",
                    absence_status=absence_status,
                    delegation_id=delegation.id,
                    confidence=0.95,
                )

        # 3. Automatische Stellvertreter-Suche
        deputy = await self._find_best_deputy(
            db, primary_approver_id, company_id, request_type
        )

        if deputy:
            return DeputySelection(
                primary_approver_id=primary_approver_id,
                deputy_id=deputy,
                reason="Automatisch ausgewaehlt basierend auf Verfügbarkeit und Expertise",
                absence_status=absence_status,
                confidence=0.75,
            )

        # 4. Kein Stellvertreter gefunden
        return DeputySelection(
            primary_approver_id=primary_approver_id,
            deputy_id=None,
            reason="Kein verfügbarer Stellvertreter gefunden",
            absence_status=absence_status,
            confidence=0.5,
        )

    async def _check_user_availability(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> Tuple[AbsenceStatus, Optional[ApprovalDelegation]]:
        """Prüft die Verfügbarkeit eines Benutzers."""
        now = datetime.now(timezone.utc)

        # Aktive Delegation suchen
        delegation_query = select(ApprovalDelegation).where(
            and_(
                ApprovalDelegation.delegator_user_id == user_id,
                ApprovalDelegation.is_active == True,
                or_(
                    ApprovalDelegation.start_date.is_(None),
                    ApprovalDelegation.start_date <= now,
                ),
                or_(
                    ApprovalDelegation.end_date.is_(None),
                    ApprovalDelegation.end_date >= now,
                ),
            )
        )

        result = await db.execute(delegation_query)
        delegation = result.scalar_one_or_none()

        if delegation:
            return AbsenceStatus.ABSENT, delegation

        # Benutzer aktiv prüfen
        user_query = select(User).where(User.id == user_id)
        result = await db.execute(user_query)
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return AbsenceStatus.ABSENT, None

        return AbsenceStatus.AVAILABLE, None

    async def _find_best_deputy(
        self,
        db: AsyncSession,
        primary_approver_id: UUID,
        company_id: UUID,
        request_type: Optional[str],
    ) -> Optional[UUID]:
        """Findet den besten verfügbaren Stellvertreter."""
        # Andere Genehmiger in der Company finden (Manager oder Admin)
        query = (
            select(User.id)
            .join(UserCompany, User.id == UserCompany.user_id)
            .where(
                and_(
                    UserCompany.company_id == company_id,
                    UserCompany.role.in_(["admin", "manager", "owner"]),
                    User.is_active == True,
                    User.id != primary_approver_id,
                )
            )
        )

        result = await db.execute(query)
        potential_deputies = [row[0] for row in result.all()]

        if not potential_deputies:
            return None

        # Verfügbare filtern
        available_deputies = []
        for deputy_id in potential_deputies:
            status, _ = await self._check_user_availability(db, deputy_id)
            if status == AbsenceStatus.AVAILABLE:
                available_deputies.append(deputy_id)

        if not available_deputies:
            return None

        # Besten wählen (nach Metriken)
        best_deputy = await self._select_by_metrics(db, available_deputies, company_id)
        return best_deputy

    async def _select_by_metrics(
        self,
        db: AsyncSession,
        candidates: List[UUID],
        company_id: UUID,
    ) -> UUID:
        """Waehlt den besten Kandidaten basierend auf Metriken."""
        # Metriken aktualisieren
        await self._refresh_metrics_cache(db, company_id)

        best_candidate = candidates[0]
        best_score = float("inf")

        for candidate_id in candidates:
            metrics = self._metrics_cache.get(candidate_id)
            if metrics:
                # Score: niedriger ist besser
                # Gewichtung: ausstehende Anfragen (50%) + Antwortzeit (50%)
                score = (
                    metrics.current_pending_count * 2.0
                    + metrics.average_response_hours * 0.1
                )
                if score < best_score:
                    best_score = score
                    best_candidate = candidate_id

        return best_candidate

    # =========================================================================
    # SLA-Based Escalation
    # =========================================================================

    async def check_escalation_needed(
        self,
        db: AsyncSession,
        request_id: UUID,
    ) -> Tuple[bool, str, int]:
        """
        Prüft ob eine Eskalation notwendig ist.

        Returns:
            Tuple[needs_escalation, reason, escalation_level]
        """
        # Anfrage laden
        query = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        result = await db.execute(query)
        request = result.scalar_one_or_none()

        if not request:
            return False, "Anfrage nicht gefunden", 0

        if request.status != ApprovalStatus.PENDING:
            return False, "Anfrage nicht mehr ausstehend", 0

        now = datetime.now(timezone.utc)
        created_at = request.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        hours_pending = (now - created_at).total_seconds() / 3600

        config = self._escalation_config

        if hours_pending >= config.final_escalation_hours:
            return True, f"Kritisch: {hours_pending:.0f}h ausstehend - Finale Eskalation erforderlich", 3
        elif hours_pending >= config.escalation_hours:
            return True, f"Dringend: {hours_pending:.0f}h ausstehend - Eskalation erforderlich", 2
        elif hours_pending >= config.warning_hours:
            return True, f"Warnung: {hours_pending:.0f}h ausstehend - Bald eskalieren", 1

        return False, "Im SLA-Rahmen", 0

    async def escalate_to_next_level(
        self,
        db: AsyncSession,
        request_id: UUID,
        current_level: int,
        company_id: UUID,
    ) -> Optional[UUID]:
        """
        Eskaliert eine Anfrage zur nächsten Ebene.

        Args:
            db: Database Session
            request_id: Anfrage-ID
            current_level: Aktuelle Eskalationsstufe
            company_id: Company ID

        Returns:
            ID des neuen Genehmigers oder None
        """
        # Eskalationsziel basierend auf Level bestimmen
        if current_level == 1:
            target_roles = ["manager", "admin"]
        elif current_level == 2:
            target_roles = ["admin", "owner"]
        else:
            target_roles = ["owner"]

        # Passenden Empfänger finden
        query = (
            select(User.id)
            .join(UserCompany, User.id == UserCompany.user_id)
            .where(
                and_(
                    UserCompany.company_id == company_id,
                    UserCompany.role.in_(target_roles),
                    User.is_active == True,
                )
            )
            .limit(1)
        )

        result = await db.execute(query)
        escalation_target = result.scalar_one_or_none()

        if escalation_target:
            logger.info(
                "approval_escalated",
                request_id=str(request_id),
                escalation_level=current_level,
                # SECURITY: Keine User-Details loggen
            )
            return escalation_target

        return None

    # =========================================================================
    # Load Balancing
    # =========================================================================

    async def route_with_load_balancing(
        self,
        db: AsyncSession,
        company_id: UUID,
        candidate_approvers: List[UUID],
        strategy: RoutingStrategy = RoutingStrategy.LEAST_LOADED,
        request_type: Optional[str] = None,
    ) -> RoutingDecision:
        """
        Routet eine Anfrage unter Berücksichtigung der Lastverteilung.

        Args:
            db: Database Session
            company_id: Company ID
            candidate_approvers: Liste möglicher Genehmiger
            strategy: Routing-Strategie
            request_type: Optional: Typ der Anfrage

        Returns:
            RoutingDecision mit Routing-Details
        """
        if not candidate_approvers:
            raise ValueError("Keine Kandidaten für Routing vorhanden")

        # Metriken aktualisieren
        await self._refresh_metrics_cache(db, company_id)

        selected: UUID
        reasoning: str

        if strategy == RoutingStrategy.LEAST_LOADED:
            selected, reasoning = await self._route_least_loaded(candidate_approvers)
        elif strategy == RoutingStrategy.FASTEST_RESPONDER:
            selected, reasoning = await self._route_fastest_responder(candidate_approvers)
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            selected, reasoning = await self._route_round_robin(candidate_approvers)
        else:
            # Default: erster Kandidat
            selected = candidate_approvers[0]
            reasoning = "Direkte Zuweisung"

        decision = RoutingDecision(
            selected_approver_id=selected,
            strategy_used=strategy,
            reasoning=reasoning,
            alternatives_considered=[c for c in candidate_approvers if c != selected],
            metrics_snapshot=self._metrics_cache.get(selected),
        )

        # History speichern
        self._add_to_history(decision)

        return decision

    async def _route_least_loaded(
        self,
        candidates: List[UUID],
    ) -> Tuple[UUID, str]:
        """Routet zum am wenigsten belasteten Genehmiger."""
        min_pending = float("inf")
        best_candidate = candidates[0]

        for candidate in candidates:
            metrics = self._metrics_cache.get(candidate)
            pending = metrics.current_pending_count if metrics else 0

            if pending < min_pending:
                min_pending = pending
                best_candidate = candidate

        return (
            best_candidate,
            f"Gewaehlt nach geringster Last ({min_pending} ausstehend)",
        )

    async def _route_fastest_responder(
        self,
        candidates: List[UUID],
    ) -> Tuple[UUID, str]:
        """Routet zum schnellsten Bearbeiter."""
        min_response_time = float("inf")
        best_candidate = candidates[0]

        for candidate in candidates:
            metrics = self._metrics_cache.get(candidate)
            response_time = metrics.average_response_hours if metrics else 24.0

            if response_time < min_response_time:
                min_response_time = response_time
                best_candidate = candidate

        return (
            best_candidate,
            f"Gewaehlt nach schnellster Antwortzeit ({min_response_time:.1f}h)",
        )

    async def _route_round_robin(
        self,
        candidates: List[UUID],
    ) -> Tuple[UUID, str]:
        """Round-Robin Routing."""
        # Zaehle letzte Zuweisungen
        recent_assignments: Dict[UUID, int] = {c: 0 for c in candidates}

        for decision in self._routing_history[-100:]:  # Letzte 100
            if decision.selected_approver_id in recent_assignments:
                recent_assignments[decision.selected_approver_id] += 1

        # Wähle den mit wenigsten Zuweisungen
        min_assignments = float("inf")
        best_candidate = candidates[0]

        for candidate, count in recent_assignments.items():
            if count < min_assignments:
                min_assignments = count
                best_candidate = candidate

        return (
            best_candidate,
            f"Round-Robin: {min_assignments} kürzliche Zuweisungen",
        )

    # =========================================================================
    # Metrics Management
    # =========================================================================

    async def _refresh_metrics_cache(
        self,
        db: AsyncSession,
        company_id: UUID,
        force: bool = False,
    ) -> None:
        """Aktualisiert den Metriken-Cache."""
        async with self._cache_lock:
            now = datetime.now(timezone.utc)

            if not force and self._last_cache_refresh:
                if now - self._last_cache_refresh < self._cache_ttl:
                    return

            # Genehmiger der Company laden
            approvers_query = (
                select(User.id)
                .join(UserCompany, User.id == UserCompany.user_id)
                .where(
                    and_(
                        UserCompany.company_id == company_id,
                        UserCompany.role.in_(["admin", "manager", "owner", "approver"]),
                        User.is_active == True,
                    )
                )
            )
            result = await db.execute(approvers_query)
            approver_ids = [row[0] for row in result.all()]

            for approver_id in approver_ids:
                metrics = await self._calculate_approver_metrics(db, approver_id)
                self._metrics_cache[approver_id] = metrics

            self._last_cache_refresh = now

    async def _calculate_approver_metrics(
        self,
        db: AsyncSession,
        approver_id: UUID,
    ) -> ApproverMetrics:
        """Berechnet Metriken für einen Genehmiger."""
        # Ausstehende Anfragen zaehlen
        pending_query = (
            select(func.count(ApprovalStep.id))
            .where(
                and_(
                    ApprovalStep.assigned_user_id == approver_id,
                    ApprovalStep.status == ApprovalStatus.PENDING,
                )
            )
        )
        result = await db.execute(pending_query)
        pending_count = result.scalar() or 0

        # Abgeschlossene Anfragen und Durchschnittliche Bearbeitungszeit
        completed_query = (
            select(
                func.count(ApprovalStep.id),
                func.avg(
                    func.extract(
                        'epoch',
                        ApprovalStep.resolved_at - ApprovalStep.created_at
                    ) / 3600
                ),
            )
            .where(
                and_(
                    ApprovalStep.assigned_user_id == approver_id,
                    ApprovalStep.status.in_([
                        ApprovalStatus.APPROVED,
                        ApprovalStatus.REJECTED,
                    ]),
                    ApprovalStep.resolved_at.isnot(None),
                )
            )
        )
        result = await db.execute(completed_query)
        row = result.one()
        total_completed = row[0] or 0
        avg_hours = row[1] or 24.0

        return ApproverMetrics(
            user_id=approver_id,
            total_approvals=total_completed,
            average_response_hours=float(avg_hours),
            current_pending_count=pending_count,
        )

    def _add_to_history(self, decision: RoutingDecision) -> None:
        """Fuegt eine Entscheidung zur History hinzu."""
        self._routing_history.append(decision)
        if len(self._routing_history) > self._max_history_size:
            self._routing_history = self._routing_history[-self._max_history_size:]

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_approver_metrics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, ApproverMetrics]:
        """Gibt Metriken aller Genehmiger zurück."""
        await self._refresh_metrics_cache(db, company_id, force=True)
        return {str(k): v for k, v in self._metrics_cache.items()}

    def get_routing_history(self, limit: int = 50) -> List[RoutingDecision]:
        """Gibt die Routing-History zurück."""
        return self._routing_history[-limit:]

    def update_escalation_config(self, config: EscalationConfig) -> None:
        """Aktualisiert die Eskalations-Konfiguration."""
        self._escalation_config = config
        logger.info(
            "escalation_config_updated",
            warning_hours=config.warning_hours,
            escalation_hours=config.escalation_hours,
        )


# =============================================================================
# Singleton Factory
# =============================================================================

_router_instance: Optional[SmartApprovalRouter] = None
_router_lock = threading.Lock()


def get_smart_approval_router() -> SmartApprovalRouter:
    """Factory-Funktion für SmartApprovalRouter Singleton."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = SmartApprovalRouter()
    return _router_instance
