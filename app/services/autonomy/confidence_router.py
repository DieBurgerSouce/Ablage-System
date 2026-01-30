# -*- coding: utf-8 -*-
"""
Confidence-based Action Router.

Enterprise Feature: Intelligentes Routing basierend auf Confidence-Scores.

Routing-Regeln:
- < 80%: Manual Review erforderlich
- 80-95%: Vorschlag mit Bestätigung
- 95%+: Auto-Execute (wenn Level >= SMART_HYBRID)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypedDict
from uuid import UUID

from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.autonomy.action_queue import (
    ActionApprovalQueue,
    ActionPriority,
    get_action_queue,
)
from app.services.autonomy.autonomy_level import (
    ActionCategory,
    AutonomyDecision,
    AutonomyLevel,
    can_auto_execute,
)


# Prometheus Metrics
ROUTING_DECISIONS = Counter(
    "confidence_routing_decisions_total",
    "Gesamtzahl der Routing-Entscheidungen",
    ["route", "category"],
)
CONFIDENCE_DISTRIBUTION = Histogram(
    "confidence_score_distribution",
    "Verteilung der Confidence-Scores",
    ["category"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98, 1.0],
)
EXECUTION_OUTCOMES = Counter(
    "action_execution_outcomes_total",
    "Ergebnisse ausgeführter Aktionen",
    ["route", "outcome"],  # outcome: success, failure, partial
)


class RoutingResult(str, Enum):
    """Ergebnis des Confidence-Routings."""

    MANUAL_REVIEW = "manual_review"      # < 80%
    SUGGEST_CONFIRM = "suggest_confirm"  # 80-95%
    AUTO_EXECUTE = "auto_execute"        # 95%+
    FORCE_MANUAL = "force_manual"        # Kritische Kategorie


class RoutingDecision(TypedDict):
    """Vollständige Routing-Entscheidung."""

    route: str
    confidence: float
    threshold_used: float
    action_category: str
    autonomy_level: int
    reason: str
    can_auto_execute: bool
    requires_confirmation: bool
    suggested_reviewers: list[str]
    estimated_risk: str
    queue_action_id: str | None


@dataclass
class ActionContext:
    """Kontext für eine auszuführende Aktion."""

    action_type: str
    category: ActionCategory
    description: str
    parameters: dict
    confidence: float
    company_id: UUID
    user_id: UUID | None = None
    priority: ActionPriority = ActionPriority.NORMAL
    metadata: dict | None = None


class ConfidenceRouter:
    """
    Router für Confidence-basierte Aktionsausführung.

    Entscheidet basierend auf:
    - Confidence-Score der KI
    - Autonomie-Level des Tenants
    - Kategorie der Aktion
    - Historische Performance
    """

    # Schwellenwerte
    LOW_CONFIDENCE_THRESHOLD = 0.80
    HIGH_CONFIDENCE_THRESHOLD = 0.95

    _instance: "ConfidenceRouter | None" = None

    def __new__(cls) -> "ConfidenceRouter":
        """Singleton Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def route(
        self,
        db: AsyncSession,
        context: ActionContext,
        autonomy_level: AutonomyLevel,
        timeout_minutes: int | None = None,
        auto_approve_on_timeout: bool = False,
    ) -> RoutingDecision:
        """
        Routet eine Aktion basierend auf Confidence und Autonomie-Level.

        Args:
            db: Datenbank-Session
            context: Aktionskontext
            autonomy_level: Aktuelles Autonomie-Level
            timeout_minutes: Optional - Timeout für Genehmigung
            auto_approve_on_timeout: Bei Timeout auto-genehmigen

        Returns:
            RoutingDecision mit Route und Details
        """
        # Metrics: Confidence-Verteilung
        CONFIDENCE_DISTRIBUTION.labels(
            category=context.category.name,
        ).observe(context.confidence)

        # Prüfe Autonomie-Entscheidung
        autonomy_decision = can_auto_execute(
            autonomy_level,
            context.category,
            context.confidence,
        )

        # Bestimme Route
        route = self._determine_route(
            context.confidence,
            context.category,
            autonomy_level,
            autonomy_decision,
        )

        # Metrics: Routing-Entscheidungen
        ROUTING_DECISIONS.labels(
            route=route.value,
            category=context.category.name,
        ).inc()

        # Erstelle Queue-Eintrag wenn nicht auto-execute
        queue_action_id = None
        if route != RoutingResult.AUTO_EXECUTE:
            queue = get_action_queue()
            queued_action = await queue.enqueue(
                db=db,
                company_id=context.company_id,
                action_type=context.action_type,
                category=context.category,
                description=context.description,
                parameters=context.parameters,
                confidence=context.confidence,
                autonomy_level=autonomy_level,
                priority=context.priority,
                user_id=context.user_id,
                timeout_minutes=timeout_minutes,
                auto_approve_on_timeout=auto_approve_on_timeout,
                metadata=context.metadata,
            )
            queue_action_id = queued_action["id"]

        return RoutingDecision(
            route=route.value,
            confidence=context.confidence,
            threshold_used=autonomy_decision["required_confidence"],
            action_category=context.category.name,
            autonomy_level=autonomy_level,
            reason=self._get_routing_reason(route, context, autonomy_decision),
            can_auto_execute=route == RoutingResult.AUTO_EXECUTE,
            requires_confirmation=route in (
                RoutingResult.SUGGEST_CONFIRM,
                RoutingResult.MANUAL_REVIEW,
                RoutingResult.FORCE_MANUAL,
            ),
            suggested_reviewers=autonomy_decision["suggested_reviewers"],
            estimated_risk=context.category.risk_level,
            queue_action_id=queue_action_id,
        )

    def _determine_route(
        self,
        confidence: float,
        category: ActionCategory,
        autonomy_level: AutonomyLevel,
        autonomy_decision: AutonomyDecision,
    ) -> RoutingResult:
        """Bestimmt die Route basierend auf allen Faktoren."""
        # Kritische Kategorien immer manuell
        if category.requires_explicit_approval:
            return RoutingResult.FORCE_MANUAL

        # Conservative Level immer manuell
        if autonomy_level == AutonomyLevel.CONSERVATIVE:
            return RoutingResult.MANUAL_REVIEW

        # Auto-Execute möglich?
        if autonomy_decision["can_auto_execute"]:
            return RoutingResult.AUTO_EXECUTE

        # Sonst nach Confidence-Bereichen
        if confidence < self.LOW_CONFIDENCE_THRESHOLD:
            return RoutingResult.MANUAL_REVIEW
        elif confidence < self.HIGH_CONFIDENCE_THRESHOLD:
            return RoutingResult.SUGGEST_CONFIRM
        else:
            # Hohe Confidence aber Autonomie-Level zu niedrig
            return RoutingResult.SUGGEST_CONFIRM

    def _get_routing_reason(
        self,
        route: RoutingResult,
        context: ActionContext,
        autonomy_decision: AutonomyDecision,
    ) -> str:
        """Generiert eine lesbare Begründung für die Route."""
        reasons = {
            RoutingResult.MANUAL_REVIEW: (
                f"Manuelle Überprüfung erforderlich: "
                f"Confidence {context.confidence:.1%} unter Schwellenwert "
                f"{self.LOW_CONFIDENCE_THRESHOLD:.0%}"
            ),
            RoutingResult.SUGGEST_CONFIRM: (
                f"Vorschlag mit Bestätigung: "
                f"Confidence {context.confidence:.1%} zwischen "
                f"{self.LOW_CONFIDENCE_THRESHOLD:.0%} und {self.HIGH_CONFIDENCE_THRESHOLD:.0%}"
            ),
            RoutingResult.AUTO_EXECUTE: (
                f"Automatische Ausführung: "
                f"Confidence {context.confidence:.1%} über Schwellenwert "
                f"{autonomy_decision['required_confidence']:.0%}"
            ),
            RoutingResult.FORCE_MANUAL: (
                f"Erzwungene manuelle Überprüfung: "
                f"Kategorie '{context.category.name}' erfordert immer Genehmigung"
            ),
        }
        return reasons.get(route, "Unbekannte Route")

    async def execute_auto_action(
        self,
        db: AsyncSession,
        context: ActionContext,
        executor: "ActionExecutor",
    ) -> dict:
        """
        Führt eine auto-genehmigte Aktion aus.

        Args:
            db: Datenbank-Session
            context: Aktionskontext
            executor: ActionExecutor-Implementierung

        Returns:
            Ausführungsergebnis
        """
        try:
            result = await executor.execute(db, context)

            EXECUTION_OUTCOMES.labels(
                route=RoutingResult.AUTO_EXECUTE.value,
                outcome="success" if result.get("success") else "failure",
            ).inc()

            return result
        except Exception as e:
            EXECUTION_OUTCOMES.labels(
                route=RoutingResult.AUTO_EXECUTE.value,
                outcome="failure",
            ).inc()
            raise

    async def get_routing_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
        days: int = 30,
    ) -> dict:
        """
        Holt Routing-Statistiken aus der Datenbank.

        Args:
            db: Datenbank-Session
            company_id: Tenant-ID
            days: Anzahl Tage zurück

        Returns:
            Statistiken über Routing-Entscheidungen
        """
        from datetime import datetime, timedelta
        from sqlalchemy import select, func, and_
        from app.db.models_autonomy import AutonomyDecisionLog, RoutingDecision

        queue = get_action_queue()
        queue_stats = await queue.get_stats(db, company_id)

        # Zeitraum für historische Daten
        since = datetime.utcnow() - timedelta(days=days)

        # Routing-Verteilung aus Decision Log
        routing_query = select(
            AutonomyDecisionLog.routing_decision,
            func.count(AutonomyDecisionLog.id)
        ).where(
            and_(
                AutonomyDecisionLog.company_id == company_id,
                AutonomyDecisionLog.created_at >= since,
            )
        ).group_by(AutonomyDecisionLog.routing_decision)

        routing_result = await db.execute(routing_query)
        routing_counts = {r: c for r, c in routing_result.fetchall()}
        total_routing = sum(routing_counts.values()) or 1  # Vermeidet Division durch 0

        # Confidence-Verteilung
        confidence_query = select(
            func.avg(AutonomyDecisionLog.confidence_score),
            func.count(AutonomyDecisionLog.id).filter(
                AutonomyDecisionLog.confidence_score < 0.80
            ),
            func.count(AutonomyDecisionLog.id).filter(
                and_(
                    AutonomyDecisionLog.confidence_score >= 0.80,
                    AutonomyDecisionLog.confidence_score < 0.95,
                )
            ),
            func.count(AutonomyDecisionLog.id).filter(
                AutonomyDecisionLog.confidence_score >= 0.95
            ),
        ).where(
            and_(
                AutonomyDecisionLog.company_id == company_id,
                AutonomyDecisionLog.created_at >= since,
            )
        )
        conf_result = await db.execute(confidence_query)
        conf_row = conf_result.fetchone()

        # Execution-Statistiken
        exec_query = select(
            AutonomyDecisionLog.outcome,
            func.count(AutonomyDecisionLog.id)
        ).where(
            and_(
                AutonomyDecisionLog.company_id == company_id,
                AutonomyDecisionLog.created_at >= since,
                AutonomyDecisionLog.was_auto_executed.is_(True),
            )
        ).group_by(AutonomyDecisionLog.outcome)

        exec_result = await db.execute(exec_query)
        exec_counts = {o or "unknown": c for o, c in exec_result.fetchall()}
        total_executed = sum(exec_counts.values()) or 1

        return {
            "queue_stats": queue_stats,
            "routing_distribution": {
                "auto_execute_rate": routing_counts.get(
                    RoutingDecision.AUTO_EXECUTE.value, 0
                ) / total_routing,
                "suggest_confirm_rate": routing_counts.get(
                    RoutingDecision.SUGGEST_AND_CONFIRM.value, 0
                ) / total_routing,
                "manual_review_rate": routing_counts.get(
                    RoutingDecision.MANUAL_REVIEW.value, 0
                ) / total_routing,
            },
            "confidence_stats": {
                "avg_confidence": float(conf_row[0] or 0.0) if conf_row else 0.0,
                "below_80_percent": conf_row[1] if conf_row else 0,
                "between_80_95_percent": conf_row[2] if conf_row else 0,
                "above_95_percent": conf_row[3] if conf_row else 0,
            },
            "execution_stats": {
                "success_rate": exec_counts.get("executed", 0) / total_executed,
                "failure_rate": exec_counts.get("failed", 0) / total_executed,
                "total_executed": sum(exec_counts.values()),
            },
        }


class ActionExecutor:
    """
    Basis-Klasse für Aktions-Executoren.

    Implementierungen für spezifische Aktionstypen sollten
    diese Klasse erweitern.
    """

    async def execute(
        self,
        db: AsyncSession,
        context: ActionContext,
    ) -> dict:
        """
        Führt eine Aktion aus.

        Args:
            db: Datenbank-Session
            context: Aktionskontext

        Returns:
            Ausführungsergebnis mit "success" Key
        """
        raise NotImplementedError("Subklassen müssen execute() implementieren")

    async def validate(
        self,
        db: AsyncSession,
        context: ActionContext,
    ) -> tuple[bool, str | None]:
        """
        Validiert eine Aktion vor der Ausführung.

        Args:
            db: Datenbank-Session
            context: Aktionskontext

        Returns:
            Tuple (is_valid, error_message)
        """
        return True, None

    async def rollback(
        self,
        db: AsyncSession,
        context: ActionContext,
        execution_result: dict,
    ) -> bool:
        """
        Macht eine Aktion rückgängig (wenn möglich).

        Args:
            db: Datenbank-Session
            context: Aktionskontext
            execution_result: Ergebnis der ursprünglichen Ausführung

        Returns:
            True wenn Rollback erfolgreich
        """
        return False  # Default: Kein Rollback möglich


# Singleton Instance
_confidence_router: ConfidenceRouter | None = None


def get_confidence_router() -> ConfidenceRouter:
    """Gibt die Singleton-Instanz des ConfidenceRouter zurück."""
    global _confidence_router
    if _confidence_router is None:
        _confidence_router = ConfidenceRouter()
    return _confidence_router
