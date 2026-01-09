# -*- coding: utf-8 -*-
"""
CrossModuleOrchestrator - Intelligente Event-Orchestrierung zwischen Modulen.

Das Herzstück des TRUE Enterprise-Level Systems:
- Reagiert automatisch auf Events aus ALLEN Modulen
- Triggert Workflows, Benachrichtigungen, Empfehlungen
- Koordiniert Entscheidungen um Konflikte zu vermeiden
- Analysiert kaskadierende Auswirkungen

PROAKTIV statt REAKTIV - Das System HANDELT, nicht nur MELDET.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Callable, Coroutine, Set, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.events.event_bus import (
    EventBus,
    Event,
    EventType,
    get_event_bus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

ORCHESTRATED_EVENTS = Counter(
    "orchestrated_events_total",
    "Anzahl orchestrierter Events",
    ["event_type", "action_type"]
)

PENDING_ACTIONS = Gauge(
    "pending_orchestration_actions",
    "Anzahl ausstehender Orchestrierungs-Aktionen",
    ["action_type"]
)

ORCHESTRATION_LATENCY = Histogram(
    "orchestration_latency_seconds",
    "Latenz der Event-Orchestrierung",
    ["event_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

CASCADING_IMPACTS = Counter(
    "cascading_impacts_detected_total",
    "Anzahl erkannter kaskadierender Auswirkungen",
    ["source_module", "target_module"]
)


# =============================================================================
# Enums und Typen
# =============================================================================

class ActionType(str, Enum):
    """Typen von Orchestrierungs-Aktionen."""
    TRIGGER_WORKFLOW = "trigger_workflow"
    CREATE_RECOMMENDATION = "create_recommendation"
    SEND_NOTIFICATION = "send_notification"
    AUTO_APPROVE = "auto_approve"
    CREATE_TASK = "create_task"
    UPDATE_KPI = "update_kpi"
    GENERATE_ALERT = "generate_alert"
    SCHEDULE_REVIEW = "schedule_review"


class ActionPriority(str, Enum):
    """Prioritaet von Aktionen."""
    CRITICAL = "kritisch"      # Sofort ausfuehren
    HIGH = "hoch"              # Innerhalb von Minuten
    NORMAL = "normal"          # Normale Queue
    LOW = "niedrig"            # Batch-Verarbeitung


class ModuleType(str, Enum):
    """Module im System."""
    DOCUMENT = "document"
    PROPERTY = "property"
    VEHICLE = "vehicle"
    INSURANCE = "insurance"
    LOAN = "loan"
    INVESTMENT = "investment"
    FINANCE = "finance"
    DEADLINE = "deadline"
    SYSTEM = "system"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OrchestrationAction:
    """Eine auszufuehrende Orchestrierungs-Aktion."""
    id: UUID = field(default_factory=uuid4)
    action_type: ActionType = ActionType.SEND_NOTIFICATION
    priority: ActionPriority = ActionPriority.NORMAL

    # Quelle
    source_event: Optional[Event] = None
    source_module: Optional[ModuleType] = None

    # Ziel
    target_module: Optional[ModuleType] = None
    target_entity_id: Optional[UUID] = None
    target_entity_type: Optional[str] = None

    # Aktion
    action_data: Dict[str, Any] = field(default_factory=dict)

    # Status
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    status: str = "pending"  # pending, executing, completed, failed
    error: Optional[str] = None

    # Erklaerung (fuer Explainability)
    reason: str = ""
    impact_description: str = ""
    confidence: float = 1.0


@dataclass
class CascadingImpact:
    """Eine kaskadierende Auswirkung."""
    source_module: ModuleType
    source_entity_id: UUID
    source_change: str

    target_module: ModuleType
    target_entity_ids: List[UUID]
    impact_type: str
    impact_description: str
    estimated_magnitude: str  # "gering", "mittel", "hoch", "kritisch"

    # Abgeleitete Aktionen
    suggested_actions: List[OrchestrationAction] = field(default_factory=list)


@dataclass
class OrchestrationDecision:
    """Eine Orchestrierungs-Entscheidung mit Erklaerung."""
    decision_id: UUID = field(default_factory=uuid4)

    # Event das die Entscheidung ausgeloest hat
    trigger_event: Event = None

    # Getroffene Entscheidung
    actions: List[OrchestrationAction] = field(default_factory=list)

    # Erklaerung
    reasoning: str = ""
    factors: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0

    # Alternative Optionen
    alternatives_considered: List[str] = field(default_factory=list)
    why_not_alternatives: str = ""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Event Handler Typen
# =============================================================================

EventHandler = Callable[[Event], Coroutine[Any, Any, List[OrchestrationAction]]]


# =============================================================================
# CrossModuleOrchestrator Service
# =============================================================================

class CrossModuleOrchestrator:
    """
    Singleton Service fuer Cross-Module Event-Orchestrierung.

    Das Gehirn des Systems - verbindet alle Module intelligent:
    - Anomalie erkannt → Auto-Workflow starten
    - Cash-Flow kritisch → Zahlungspause vorschlagen
    - Reconciliation Match 95%+ → Auto-Buchung
    - Insurance Gap → Versicherungsvergleich triggern
    - Early Warning → Proaktive Empfehlung erstellen

    KEINE externen APIs - alles lokal entschieden.
    """

    _instance: Optional["CrossModuleOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CrossModuleOrchestrator":
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

        # Event Bus Referenz
        self._event_bus: Optional[EventBus] = None

        # Pending Actions Queue - BOUNDED mit maxlen um Memory Leaks zu verhindern
        self._max_pending_actions = 10000
        self._pending_actions: Deque[OrchestrationAction] = deque(maxlen=self._max_pending_actions)
        self._action_lock = asyncio.Lock()

        # Entscheidungs-History (fuer Explainability) - BOUNDED
        self._decision_history: Deque[OrchestrationDecision] = deque(maxlen=1000)

        # Aktive Konflikte verhindern - MIT TTL fuer automatisches Cleanup
        # Value ist jetzt Tuple[Set[str], datetime] - Actions + Timestamp
        self._active_entity_actions: Dict[str, Tuple[Set[str], datetime]] = {}
        self._entity_action_ttl = timedelta(hours=24)  # 24h TTL

        # Handler-Registry
        self._handlers: Dict[EventType, EventHandler] = {}
        self._register_default_handlers()

        logger.info("cross_module_orchestrator_initialized")

    # =========================================================================
    # Initialisierung
    # =========================================================================

    async def start(self) -> None:
        """Startet den Orchestrator und verbindet mit EventBus."""
        self._event_bus = get_event_bus()

        # Alle Event-Typen abonnieren die wir orchestrieren wollen
        await self._subscribe_to_events()

        logger.info("cross_module_orchestrator_started")

    async def stop(self) -> None:
        """Stoppt den Orchestrator."""
        logger.info("cross_module_orchestrator_stopped")

    def _register_default_handlers(self) -> None:
        """Registriert die Standard-Event-Handler."""
        # Document Events
        self._handlers[EventType.DOCUMENT_ANOMALY_DETECTED] = self._handle_document_anomaly

        # Finance Events
        self._handlers[EventType.FINANCE_ANOMALY_DETECTED] = self._handle_finance_anomaly
        self._handlers[EventType.FINANCE_BUDGET_EXCEEDED] = self._handle_budget_exceeded

        # Insurance Events
        self._handlers[EventType.INSURANCE_GAP_DETECTED] = self._handle_insurance_gap
        self._handlers[EventType.INSURANCE_DEADLINE_APPROACHING] = self._handle_insurance_deadline

        # Loan Events
        self._handlers[EventType.LOAN_PAYMENT_DUE] = self._handle_loan_payment_due

        # Investment Events
        self._handlers[EventType.INVESTMENT_REBALANCING_NEEDED] = self._handle_rebalancing_needed
        self._handlers[EventType.INVESTMENT_TARGET_REACHED] = self._handle_investment_target

        # Deadline Events
        self._handlers[EventType.DEADLINE_APPROACHING] = self._handle_deadline_approaching
        self._handlers[EventType.DEADLINE_OVERDUE] = self._handle_deadline_overdue

        # Property Events
        self._handlers[EventType.PROPERTY_KPIS_CALCULATED] = self._handle_property_kpi_update

        # Vehicle Events
        self._handlers[EventType.VEHICLE_SERVICE_DUE] = self._handle_vehicle_service_due

    async def _subscribe_to_events(self) -> None:
        """Abonniert alle relevanten Events."""
        # Pattern-basierte Subscription fuer alle Module
        self._event_bus.subscribe_pattern("document.*", self._on_event)
        self._event_bus.subscribe_pattern("finance.*", self._on_event)
        self._event_bus.subscribe_pattern("insurance.*", self._on_event)
        self._event_bus.subscribe_pattern("loan.*", self._on_event)
        self._event_bus.subscribe_pattern("investment.*", self._on_event)
        self._event_bus.subscribe_pattern("property.*", self._on_event)
        self._event_bus.subscribe_pattern("vehicle.*", self._on_event)
        self._event_bus.subscribe_pattern("deadline.*", self._on_event)

        logger.debug("orchestrator_subscribed_to_events")

    # =========================================================================
    # Event Processing
    # =========================================================================

    async def _on_event(self, event: Event) -> None:
        """Zentraler Event-Handler - routet zu spezifischen Handlern."""
        start_time = datetime.now(timezone.utc)

        try:
            # Handler fuer diesen Event-Typ suchen
            handler = self._handlers.get(event.event_type)

            if handler:
                # Spezifischen Handler ausfuehren
                actions = await handler(event)

                if actions:
                    # Entscheidung dokumentieren
                    decision = OrchestrationDecision(
                        trigger_event=event,
                        actions=actions,
                        reasoning=self._generate_reasoning(event, actions),
                        confidence=self._calculate_confidence(event, actions),
                    )
                    await self._record_decision(decision)

                    # Aktionen zur Queue hinzufuegen
                    for action in actions:
                        await self._queue_action(action)

                    # Kritische Aktionen sofort ausfuehren
                    critical_actions = [a for a in actions if a.priority == ActionPriority.CRITICAL]
                    if critical_actions:
                        await self._execute_critical_actions(critical_actions)

                ORCHESTRATED_EVENTS.labels(
                    event_type=event.event_type.value,
                    action_type=actions[0].action_type.value if actions else "none"
                ).inc()

            # Latenz messen
            latency = (datetime.now(timezone.utc) - start_time).total_seconds()
            ORCHESTRATION_LATENCY.labels(
                event_type=event.event_type.value
            ).observe(latency)

        except Exception as e:
            logger.error(
                "orchestration_event_handler_error",
                event_type=event.event_type.value,
                error=str(e),
                exc_info=True
            )

    # =========================================================================
    # Event Handler Implementierungen
    # =========================================================================

    async def _handle_document_anomaly(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt erkannte Dokument-Anomalien.

        PROAKTIV: Startet automatisch Approval-Workflow bei kritischen Anomalien.
        """
        actions: List[OrchestrationAction] = []
        payload = event.payload

        anomaly_type = payload.get("anomaly_type", "unknown")
        severity = payload.get("severity", "low")
        document_id = payload.get("document_id")
        confidence = payload.get("confidence", 0.5)

        # Pruefe ob bereits eine Aktion fuer dieses Dokument laeuft
        if self._is_action_active(f"document_{document_id}", "workflow"):
            logger.debug("document_anomaly_action_already_active", document_id=document_id)
            return actions

        if severity in ["critical", "high"] and confidence > 0.8:
            # Automatisch Approval-Workflow starten
            workflow_action = OrchestrationAction(
                action_type=ActionType.TRIGGER_WORKFLOW,
                priority=ActionPriority.CRITICAL if severity == "critical" else ActionPriority.HIGH,
                source_event=event,
                source_module=ModuleType.DOCUMENT,
                target_entity_id=UUID(document_id) if document_id else None,
                target_entity_type="document",
                action_data={
                    "workflow_type": "document_approval",
                    "anomaly_type": anomaly_type,
                    "severity": severity,
                    "requires_review": True,
                },
                reason=f"Kritische Anomalie '{anomaly_type}' mit {confidence*100:.0f}% Konfidenz erkannt",
                impact_description="Dokument wird zur manuellen Pruefung markiert",
                confidence=confidence,
            )
            actions.append(workflow_action)

            # Benachrichtigung an zustaendige Person
            notification_action = OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.HIGH,
                source_event=event,
                target_entity_id=event.user_id,
                action_data={
                    "notification_type": "anomaly_detected",
                    "title": f"Anomalie erkannt: {anomaly_type}",
                    "message": f"Im Dokument wurde eine {severity} Anomalie erkannt. Bitte pruefen.",
                    "priority": "high",
                    "action_url": f"/documents/{document_id}",
                },
                reason="Benutzer muss ueber kritische Anomalie informiert werden",
            )
            actions.append(notification_action)

            # Als aktiv markieren
            await self._mark_action_active(f"document_{document_id}", "workflow")

        elif severity == "medium":
            # Nur Empfehlung erstellen
            rec_action = OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.NORMAL,
                source_event=event,
                target_entity_id=UUID(document_id) if document_id else None,
                action_data={
                    "category": "document_review",
                    "priority": "medium",
                    "title": f"Dokument-Anomalie: {anomaly_type}",
                    "description": "Das System hat eine potenzielle Anomalie erkannt. Eine manuelle Pruefung wird empfohlen.",
                    "suggested_actions": ["Dokument pruefen", "Kategorisierung verifizieren"],
                },
                reason=f"Mittlere Anomalie '{anomaly_type}' erkannt - Empfehlung zur Pruefung",
            )
            actions.append(rec_action)

        return actions

    async def _handle_finance_anomaly(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt Finanz-Anomalien (ungewoehnliche Transaktionen)."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        anomaly_type = payload.get("anomaly_type", "unusual_amount")
        amount = Decimal(str(payload.get("amount", 0)))
        expected_amount = Decimal(str(payload.get("expected_amount", 0)))
        deviation_pct = payload.get("deviation_percent", 0)

        if deviation_pct > 50:  # Mehr als 50% Abweichung
            # Kritische Anomalie - sofortige Benachrichtigung
            actions.append(OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.CRITICAL,
                source_event=event,
                source_module=ModuleType.FINANCE,
                action_data={
                    "notification_type": "finance_anomaly_critical",
                    "title": f"Finanz-Alarm: {anomaly_type}",
                    "message": f"Ungewoehnliche Transaktion: {amount:.2f} EUR (erwartet: {expected_amount:.2f} EUR, Abweichung: {deviation_pct:.0f}%)",
                    "priority": "critical",
                },
                reason=f"Transaktion weicht um {deviation_pct:.0f}% vom Erwartungswert ab",
                impact_description="Potenzielle Fehltransaktion oder Betrug",
            ))

            # Task zur Pruefung erstellen
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_TASK,
                priority=ActionPriority.HIGH,
                source_event=event,
                action_data={
                    "task_type": "review_transaction",
                    "title": "Ungewoehnliche Transaktion pruefen",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                },
                reason="Transaktion erfordert menschliche Pruefung",
            ))

        elif deviation_pct > 20:  # 20-50% Abweichung
            # Empfehlung zur Pruefung
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.NORMAL,
                source_event=event,
                source_module=ModuleType.FINANCE,
                action_data={
                    "category": "finance_review",
                    "priority": "medium",
                    "title": f"Transaktion pruefen: {anomaly_type}",
                    "description": f"Transaktion weicht um {deviation_pct:.0f}% vom Erwartungswert ab.",
                },
                reason=f"Moderate Abweichung von {deviation_pct:.0f}% erkannt",
            ))

        return actions

    async def _handle_budget_exceeded(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt Budgetueberschreitungen."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        category = payload.get("category", "Allgemein")
        budget = Decimal(str(payload.get("budget", 0)))
        spent = Decimal(str(payload.get("spent", 0)))
        overage_pct = ((spent - budget) / budget * 100) if budget > 0 else 0

        # Kaskadierende Auswirkung: Budget-Ueberschreitung beeinflusst Financial Health
        cascading_impact = CascadingImpact(
            source_module=ModuleType.FINANCE,
            source_entity_id=event.correlation_id or uuid4(),
            source_change=f"Budget '{category}' ueberschritten",
            target_module=ModuleType.FINANCE,
            target_entity_ids=[],
            impact_type="financial_health_degradation",
            impact_description=f"Financial Health Score wird negativ beeinflusst (ca. -{min(overage_pct/2, 10):.1f} Punkte)",
            estimated_magnitude="mittel" if overage_pct < 30 else "hoch",
        )

        CASCADING_IMPACTS.labels(
            source_module="finance",
            target_module="finance"
        ).inc()

        # Benachrichtigung
        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=ActionPriority.HIGH if overage_pct > 30 else ActionPriority.NORMAL,
            source_event=event,
            source_module=ModuleType.FINANCE,
            action_data={
                "notification_type": "budget_exceeded",
                "title": f"Budget ueberschritten: {category}",
                "message": f"Das Budget fuer '{category}' wurde um {overage_pct:.1f}% ueberschritten ({spent:.2f} EUR von {budget:.2f} EUR).",
                "priority": "high" if overage_pct > 30 else "normal",
            },
            reason=f"Budget um {overage_pct:.1f}% ueberschritten",
            impact_description=cascading_impact.impact_description,
        ))

        # Bei starker Ueberschreitung: Zahlungspause vorschlagen
        if overage_pct > 50:
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.HIGH,
                source_event=event,
                action_data={
                    "category": "cost_control",
                    "priority": "hoch",
                    "title": "Zahlungspause empfohlen",
                    "description": f"Die Kategorie '{category}' hat das Budget massiv ueberschritten. Pruefe ob Zahlungen aufgeschoben werden koennen.",
                    "suggested_actions": [
                        "Nicht dringende Zahlungen aufschieben",
                        "Budget fuer naechsten Monat anpassen",
                        "Ausgaben in dieser Kategorie einschraenken",
                    ],
                    "potential_savings": float(spent - budget),
                },
                reason="Massive Budgetueberschreitung erfordert Kostenkontrolle",
            ))

        return actions

    async def _handle_insurance_gap(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt erkannte Versicherungsluecken."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        gap_type = payload.get("gap_type", "unknown")
        severity = payload.get("severity", "medium")
        affected_asset = payload.get("affected_asset", "")
        recommended_coverage = payload.get("recommended_coverage", "")

        if severity == "critical":
            # Sofortige Warnung - Risiko unversichert
            actions.append(OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.CRITICAL,
                source_event=event,
                source_module=ModuleType.INSURANCE,
                action_data={
                    "notification_type": "insurance_gap_critical",
                    "title": f"KRITISCH: Versicherungsluecke bei {affected_asset}",
                    "message": f"Dein {affected_asset} ist nicht ausreichend versichert. Empfohlene Deckung: {recommended_coverage}",
                    "priority": "critical",
                },
                reason=f"Kritische Deckungsluecke: {gap_type}",
                impact_description="Hohes finanzielles Risiko bei Schadensfall",
            ))

        # Empfehlung zum Versicherungsvergleich
        actions.append(OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            priority=ActionPriority.HIGH if severity == "critical" else ActionPriority.NORMAL,
            source_event=event,
            source_module=ModuleType.INSURANCE,
            action_data={
                "category": "versicherung",
                "priority": severity,
                "title": f"Versicherungsluecke schliessen: {gap_type}",
                "description": f"Fuer {affected_asset} wurde eine Deckungsluecke erkannt. Empfehlung: {recommended_coverage}",
                "suggested_actions": [
                    "Aktuelle Police pruefen",
                    "Vergleichsangebote einholen",
                    "Deckungssumme erhoehen",
                ],
            },
            reason=f"Versicherungsluecke '{gap_type}' erkannt",
        ))

        return actions

    async def _handle_insurance_deadline(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt nahende Versicherungsfristen (Kuendigung, Wechsel)."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        deadline_type = payload.get("deadline_type", "unknown")
        deadline_date = payload.get("deadline_date")
        policy_name = payload.get("policy_name", "")
        days_remaining = payload.get("days_remaining", 30)

        priority = ActionPriority.CRITICAL if days_remaining <= 7 else (
            ActionPriority.HIGH if days_remaining <= 14 else ActionPriority.NORMAL
        )

        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=priority,
            source_event=event,
            source_module=ModuleType.INSURANCE,
            action_data={
                "notification_type": "insurance_deadline",
                "title": f"Versicherungsfrist: {policy_name}",
                "message": f"In {days_remaining} Tagen: {deadline_type} fuer '{policy_name}'",
                "priority": priority.value,
            },
            reason=f"Versicherungsfrist in {days_remaining} Tagen",
        ))

        if deadline_type in ["kuendigung", "wechsel"]:
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=priority,
                source_event=event,
                action_data={
                    "category": "versicherung",
                    "priority": priority.value,
                    "title": f"Versicherungswechsel pruefen: {policy_name}",
                    "description": f"Die Kuendigungsfrist fuer '{policy_name}' endet in {days_remaining} Tagen. Jetzt ist der ideale Zeitpunkt fuer einen Tarifvergleich.",
                    "suggested_actions": [
                        "Aktuelle Konditionen pruefen",
                        "Vergleichsangebote einholen",
                        "Bei Wechsel: Rechtzeitig kuendigen",
                    ],
                    "deadline": deadline_date,
                },
                reason=f"Optimaler Zeitpunkt fuer Versicherungswechsel-Pruefung",
            ))

        return actions

    async def _handle_loan_payment_due(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt faellige Kreditraten."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        loan_name = payload.get("loan_name", "")
        amount = Decimal(str(payload.get("amount", 0)))
        due_date = payload.get("due_date")
        days_until = payload.get("days_until", 0)

        # Warnung bei knapper Zeit
        if days_until <= 3:
            actions.append(OrchestrationAction(
                action_type=ActionType.SEND_NOTIFICATION,
                priority=ActionPriority.CRITICAL if days_until <= 1 else ActionPriority.HIGH,
                source_event=event,
                source_module=ModuleType.LOAN,
                action_data={
                    "notification_type": "loan_payment_due",
                    "title": f"Kreditrate faellig: {loan_name}",
                    "message": f"In {days_until} Tag(en) ist die Rate von {amount:.2f} EUR faellig.",
                    "priority": "critical" if days_until <= 1 else "high",
                },
                reason=f"Kreditrate in {days_until} Tag(en) faellig",
            ))

        # Kaskadierende Auswirkung auf Cash-Flow
        if amount > Decimal("500"):  # Relevante Rate
            CASCADING_IMPACTS.labels(
                source_module="loan",
                target_module="finance"
            ).inc()

        return actions

    async def _handle_rebalancing_needed(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt notwendiges Portfolio-Rebalancing."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        current_allocation = payload.get("current_allocation", {})
        target_allocation = payload.get("target_allocation", {})
        deviation = payload.get("max_deviation_percent", 0)

        if deviation > 10:
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.HIGH if deviation > 20 else ActionPriority.NORMAL,
                source_event=event,
                source_module=ModuleType.INVESTMENT,
                action_data={
                    "category": "rebalancing",
                    "priority": "hoch" if deviation > 20 else "mittel",
                    "title": f"Portfolio-Rebalancing empfohlen",
                    "description": f"Die aktuelle Allokation weicht um bis zu {deviation:.1f}% von der Ziel-Allokation ab.",
                    "current_allocation": current_allocation,
                    "target_allocation": target_allocation,
                    "suggested_actions": [
                        "Uebergewichtete Positionen reduzieren",
                        "Untergewichtete Positionen aufstocken",
                        "Rebalancing-Zeitpunkt planen",
                    ],
                },
                reason=f"Portfolio-Allokation weicht um {deviation:.1f}% ab",
            ))

        return actions

    async def _handle_investment_target(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt erreichte Investment-Ziele."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        investment_name = payload.get("investment_name", "")
        target_value = payload.get("target_value", 0)
        current_value = payload.get("current_value", 0)

        # Positive Nachricht!
        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=ActionPriority.NORMAL,
            source_event=event,
            source_module=ModuleType.INVESTMENT,
            action_data={
                "notification_type": "investment_target_reached",
                "title": f"Ziel erreicht: {investment_name}",
                "message": f"Dein Investmentziel von {target_value:.2f} EUR wurde erreicht! Aktueller Wert: {current_value:.2f} EUR",
                "priority": "normal",
                "celebration": True,  # Frontend kann Konfetti anzeigen :)
            },
            reason="Investment-Ziel erfolgreich erreicht",
        ))

        # Empfehlung fuer naechste Schritte
        actions.append(OrchestrationAction(
            action_type=ActionType.CREATE_RECOMMENDATION,
            priority=ActionPriority.LOW,
            source_event=event,
            action_data={
                "category": "optimierung",
                "priority": "niedrig",
                "title": f"Naechstes Ziel setzen: {investment_name}",
                "description": "Herzlichen Glueckwunsch zum erreichten Ziel! Setze dir ein neues ambitioniertes Ziel.",
                "suggested_actions": [
                    "Neues Ziel definieren",
                    "Sparrate ueberpruefen",
                    "Strategie anpassen",
                ],
            },
            reason="Ziel erreicht - Zeit fuer neues Ziel",
        ))

        return actions

    async def _handle_deadline_approaching(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt nahende Fristen."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        deadline_name = payload.get("name", "")
        deadline_date = payload.get("deadline_date")
        days_remaining = payload.get("days_remaining", 30)
        importance = payload.get("importance", "normal")

        priority = ActionPriority.CRITICAL if days_remaining <= 3 else (
            ActionPriority.HIGH if days_remaining <= 7 else ActionPriority.NORMAL
        )

        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=priority,
            source_event=event,
            source_module=ModuleType.DEADLINE,
            action_data={
                "notification_type": "deadline_approaching",
                "title": f"Frist: {deadline_name}",
                "message": f"Noch {days_remaining} Tag(e) bis zur Frist: {deadline_name}",
                "priority": priority.value,
            },
            reason=f"Frist '{deadline_name}' in {days_remaining} Tagen",
        ))

        return actions

    async def _handle_deadline_overdue(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt ueberfaellige Fristen."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        deadline_name = payload.get("name", "")
        days_overdue = payload.get("days_overdue", 0)

        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=ActionPriority.CRITICAL,
            source_event=event,
            source_module=ModuleType.DEADLINE,
            action_data={
                "notification_type": "deadline_overdue",
                "title": f"UEBERFAELLIG: {deadline_name}",
                "message": f"Die Frist '{deadline_name}' ist seit {days_overdue} Tag(en) ueberfaellig!",
                "priority": "critical",
            },
            reason=f"Frist seit {days_overdue} Tagen ueberfaellig",
        ))

        # Task zur Behandlung erstellen
        actions.append(OrchestrationAction(
            action_type=ActionType.CREATE_TASK,
            priority=ActionPriority.CRITICAL,
            source_event=event,
            action_data={
                "task_type": "handle_overdue_deadline",
                "title": f"Ueberfaellige Frist behandeln: {deadline_name}",
                "urgency": "critical",
            },
            reason="Ueberfaellige Frist erfordert sofortige Aufmerksamkeit",
        ))

        return actions

    async def _handle_property_kpi_update(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt KPI-Updates fuer Immobilien - prueft auf Anomalien."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        property_id = payload.get("property_id")
        rental_yield = payload.get("rental_yield")
        vacancy_risk = payload.get("vacancy_risk")

        # Pruefe auf problematische KPIs
        if vacancy_risk and vacancy_risk > 0.3:  # 30% Leerstandsrisiko
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.HIGH,
                source_event=event,
                source_module=ModuleType.PROPERTY,
                target_entity_id=UUID(property_id) if property_id else None,
                action_data={
                    "category": "risiko",
                    "priority": "hoch",
                    "title": "Erhoehtes Leerstandsrisiko",
                    "description": f"Fuer diese Immobilie besteht ein erhoehtes Leerstandsrisiko ({vacancy_risk*100:.0f}%). Praventive Massnahmen empfohlen.",
                    "suggested_actions": [
                        "Mietpreis ueberpruefen",
                        "Zustand der Immobilie pruefen",
                        "Marketingmassnahmen vorbereiten",
                    ],
                },
                reason=f"Leerstandsrisiko bei {vacancy_risk*100:.0f}%",
            ))

        if rental_yield and rental_yield < 0.03:  # Unter 3% Rendite
            actions.append(OrchestrationAction(
                action_type=ActionType.CREATE_RECOMMENDATION,
                priority=ActionPriority.NORMAL,
                source_event=event,
                source_module=ModuleType.PROPERTY,
                target_entity_id=UUID(property_id) if property_id else None,
                action_data={
                    "category": "optimierung",
                    "priority": "mittel",
                    "title": "Niedrige Mietrendite",
                    "description": f"Die aktuelle Mietrendite ({rental_yield*100:.1f}%) liegt unter dem Zielwert. Optimierungspotenzial vorhanden.",
                    "suggested_actions": [
                        "Mietanpassung pruefen",
                        "Nebenkosten optimieren",
                        "Wertsteigerungsmassnahmen",
                    ],
                },
                reason=f"Mietrendite unter 3%: {rental_yield*100:.1f}%",
            ))

        return actions

    async def _handle_vehicle_service_due(self, event: Event) -> List[OrchestrationAction]:
        """Behandelt faellige Fahrzeug-Wartungen."""
        actions: List[OrchestrationAction] = []
        payload = event.payload

        vehicle_name = payload.get("vehicle_name", "")
        service_type = payload.get("service_type", "Wartung")
        due_date = payload.get("due_date")
        days_until = payload.get("days_until", 30)

        priority = ActionPriority.CRITICAL if days_until <= 0 else (
            ActionPriority.HIGH if days_until <= 7 else ActionPriority.NORMAL
        )

        actions.append(OrchestrationAction(
            action_type=ActionType.SEND_NOTIFICATION,
            priority=priority,
            source_event=event,
            source_module=ModuleType.VEHICLE,
            action_data={
                "notification_type": "vehicle_service_due",
                "title": f"Fahrzeug-{service_type}: {vehicle_name}",
                "message": f"{service_type} fuer '{vehicle_name}' {'ueberfaellig!' if days_until <= 0 else f'in {days_until} Tagen faellig.'}",
                "priority": priority.value,
            },
            reason=f"Fahrzeugwartung {'ueberfaellig' if days_until <= 0 else 'faellig'}",
        ))

        return actions

    # =========================================================================
    # Action Management
    # =========================================================================

    async def _queue_action(self, action: OrchestrationAction) -> None:
        """Fuegt eine Aktion zur Queue hinzu."""
        async with self._action_lock:
            self._pending_actions.append(action)
            PENDING_ACTIONS.labels(action_type=action.action_type.value).inc()

        logger.debug(
            "orchestration_action_queued",
            action_id=str(action.id),
            action_type=action.action_type.value,
            priority=action.priority.value,
        )

    async def _execute_critical_actions(self, actions: List[OrchestrationAction]) -> None:
        """Fuehrt kritische Aktionen sofort aus."""
        for action in actions:
            try:
                await self._execute_action(action)
            except Exception as e:
                logger.error(
                    "critical_action_execution_failed",
                    action_id=str(action.id),
                    error=str(e),
                )

    async def _execute_action(self, action: OrchestrationAction) -> bool:
        """Fuehrt eine einzelne Aktion aus."""
        action.status = "executing"

        try:
            if action.action_type == ActionType.SEND_NOTIFICATION:
                await self._execute_notification(action)
            elif action.action_type == ActionType.CREATE_RECOMMENDATION:
                await self._execute_create_recommendation(action)
            elif action.action_type == ActionType.TRIGGER_WORKFLOW:
                await self._execute_trigger_workflow(action)
            elif action.action_type == ActionType.CREATE_TASK:
                await self._execute_create_task(action)
            else:
                logger.warning(
                    "unknown_action_type",
                    action_type=action.action_type.value,
                )
                return False

            action.status = "completed"
            action.executed_at = datetime.now(timezone.utc)

            PENDING_ACTIONS.labels(action_type=action.action_type.value).dec()

            logger.info(
                "orchestration_action_executed",
                action_id=str(action.id),
                action_type=action.action_type.value,
            )
            return True

        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            logger.error(
                "action_execution_failed",
                action_id=str(action.id),
                error=str(e),
            )
            return False

    async def _execute_notification(self, action: OrchestrationAction) -> None:
        """Sendet eine Benachrichtigung."""
        from app.services.notification_service import get_notification_service

        notification_service = get_notification_service()
        data = action.action_data

        user_id = str(action.target_entity_id) if action.target_entity_id else None

        await notification_service.notify(
            notification_type=data.get("notification_type", "system_alert"),
            context=data,
            user_id=user_id,
            priority=data.get("priority", "normal"),
        )

    async def _execute_create_recommendation(self, action: OrchestrationAction) -> None:
        """Erstellt eine Empfehlung und persistiert sie in AIDecision.

        Nutzt das AIDecision-Model fuer vollstaendigen Audit-Trail.
        """
        from app.db.session import get_async_session_context
        from app.db.models import AIDecision

        data = action.action_data
        user_id = data.get("user_id") or action.target_entity_id
        document_id = data.get("document_id")

        logger.info(
            "recommendation_created_by_orchestrator",
            category=data.get("category"),
            priority=data.get("priority"),
            title=data.get("title"),
            reason=action.reason,
        )

        # Confidence aus Priority ableiten
        priority_confidence_map = {
            "critical": 0.95,
            "high": 0.85,
            "medium": 0.75,
            "low": 0.65,
        }
        confidence = priority_confidence_map.get(
            data.get("priority", "medium"),
            0.75
        )

        # Confidence Level basierend auf Confidence
        if confidence >= 0.9:
            confidence_level = "auto"
        elif confidence >= 0.7:
            confidence_level = "suggest"
        else:
            confidence_level = "manual"

        try:
            async with get_async_session_context() as session:
                ai_decision = AIDecision(
                    company_id=data.get("company_id"),
                    document_id=document_id,
                    decision_type="recommendation",
                    decision_value={
                        "category": data.get("category"),
                        "title": data.get("title"),
                        "description": data.get("description"),
                        "priority": data.get("priority"),
                        "action_url": data.get("action_url"),
                        "potential_value": (
                            float(data.get("potential_value", 0))
                            if data.get("potential_value")
                            else None
                        ),
                        "orchestrator_action_id": str(action.id),
                        "source_module": (
                            action.source_module.value
                            if action.source_module
                            else None
                        ),
                    },
                    confidence=confidence,
                    confidence_level=confidence_level,
                    explanation={
                        "reason": action.reason,
                        "source": "cross_module_orchestrator",
                        "trigger_event": data.get("trigger_event"),
                    },
                    auto_applied=False,
                    requires_review=True,
                    is_final=False,
                )
                session.add(ai_decision)
                await session.commit()

                logger.info(
                    "recommendation_persisted",
                    decision_id=str(ai_decision.id),
                    category=data.get("category"),
                    title=data.get("title"),
                    confidence=confidence,
                )
        except Exception as e:
            logger.error(
                "recommendation_persistence_failed",
                error=str(e),
                category=data.get("category"),
                title=data.get("title"),
            )

    async def _execute_trigger_workflow(self, action: OrchestrationAction) -> None:
        """Triggert einen Workflow.

        Integriert mit WorkflowTriggerService fuer echte Workflow-Ausfuehrung.
        """
        from app.db.session import get_async_session_context
        from app.services.workflow.workflow_trigger_service import WorkflowTriggerService
        from app.services.workflow.workflow_execution_service import WorkflowExecutionService

        data = action.action_data
        workflow_id = data.get("workflow_id")
        user_id = data.get("user_id") or action.target_entity_id

        logger.info(
            "workflow_triggered_by_orchestrator",
            workflow_type=data.get("workflow_type"),
            workflow_id=str(workflow_id) if workflow_id else None,
            target_entity_id=str(action.target_entity_id) if action.target_entity_id else None,
            reason=action.reason,
        )

        if not workflow_id:
            logger.warning(
                "workflow_trigger_missing_workflow_id",
                action_id=str(action.id),
                reason="workflow_id fehlt in action_data",
            )
            return

        if not user_id:
            logger.warning(
                "workflow_trigger_missing_user_id",
                action_id=str(action.id),
                reason="user_id fehlt in action_data und target_entity_id",
            )
            return

        try:
            async with get_async_session_context() as session:
                # ExecutionService erstellen
                execution_service = WorkflowExecutionService(db=session)

                # TriggerService mit ExecutionService erstellen
                trigger_service = WorkflowTriggerService(
                    db=session,
                    execution_service=execution_service,
                )

                # Workflow manuell triggern
                execution_id = await trigger_service.trigger_workflow_manually(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    document_id=data.get("document_id"),
                    variables={
                        "orchestrator_action_id": str(action.id),
                        "orchestrator_reason": action.reason,
                        "source_module": action.source_module.value if action.source_module else None,
                        **(data.get("variables") or {}),
                    },
                )

                if execution_id:
                    logger.info(
                        "workflow_execution_started",
                        workflow_id=str(workflow_id),
                        execution_id=str(execution_id),
                        orchestrator_action_id=str(action.id),
                    )
                else:
                    logger.warning(
                        "workflow_trigger_returned_none",
                        workflow_id=str(workflow_id),
                        reason="trigger_workflow_manually gab None zurueck",
                    )

        except Exception as e:
            logger.error(
                "workflow_trigger_failed",
                workflow_id=str(workflow_id) if workflow_id else None,
                action_id=str(action.id),
                error=str(e),
            )

    async def _execute_create_task(self, action: OrchestrationAction) -> None:
        """Erstellt einen Task und persistiert ihn in der Datenbank.

        Nutzt das PrivatTask-Model um Orchestrator-generierte Aufgaben
        zu speichern und dem Benutzer im Dashboard anzuzeigen.
        """
        from app.db.session import get_async_session_context
        from app.db.models import PrivatTask

        data = action.action_data

        # Mapping Priority String -> Task Priority
        priority_map = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
        priority = priority_map.get(data.get("priority", "medium"), "medium")

        # Due Date berechnen (falls nicht angegeben, 7 Tage default)
        due_date = data.get("due_date")
        if due_date is None:
            due_date = datetime.now(timezone.utc) + timedelta(days=7)
        elif isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date.replace("Z", "+00:00"))

        try:
            async with get_async_session_context() as session:
                privat_task = PrivatTask(
                    space_id=data.get("space_id"),
                    user_id=data.get("user_id"),
                    task_type=data.get("task_type", "action"),
                    title=data.get("title", "Orchestrator Task"),
                    description=data.get("description"),
                    category=data.get("category", "general"),
                    priority=priority,
                    due_date=due_date,
                    source_action_id=action.id,
                    source_reason=action.reason,
                    source_module=data.get("source_module"),
                    status="pending",
                    related_entity_type=data.get("entity_type"),
                    related_entity_id=data.get("entity_id"),
                    extra_data={
                        "action_type": action.action_type.value,
                        "original_data": data,
                        "created_by": "cross_module_orchestrator",
                    },
                )
                session.add(privat_task)
                await session.commit()
                await session.refresh(privat_task)

                logger.info(
                    "task_created_by_orchestrator",
                    task_id=str(privat_task.id),
                    task_type=privat_task.task_type,
                    title=privat_task.title,
                    priority=privat_task.priority,
                    due_date=due_date.isoformat() if due_date else None,
                    reason=action.reason,
                )

        except Exception as e:
            logger.error(
                "task_creation_failed",
                action_id=str(action.id),
                error=str(e),
            )

    # =========================================================================
    # Conflict Prevention - mit TTL-basiertem Cleanup
    # =========================================================================

    def _is_action_active(self, entity_key: str, action_type: str) -> bool:
        """Prueft ob bereits eine Aktion fuer diese Entity laeuft.

        SYNC Methode - keine async Operationen noetig.
        """
        entry = self._active_entity_actions.get(entity_key)
        if entry is None:
            return False
        actions, timestamp = entry
        # Check TTL
        if datetime.now(timezone.utc) - timestamp > self._entity_action_ttl:
            del self._active_entity_actions[entity_key]
            return False
        return action_type in actions

    async def _mark_action_active(self, entity_key: str, action_type: str) -> None:
        """Markiert eine Aktion als aktiv fuer diese Entity."""
        now = datetime.now(timezone.utc)
        if entity_key not in self._active_entity_actions:
            self._active_entity_actions[entity_key] = (set(), now)
        actions, _ = self._active_entity_actions[entity_key]
        actions.add(action_type)
        # Timestamp aktualisieren
        self._active_entity_actions[entity_key] = (actions, now)

    async def _mark_action_complete(self, entity_key: str, action_type: str) -> None:
        """Markiert eine Aktion als abgeschlossen."""
        if entity_key in self._active_entity_actions:
            actions, timestamp = self._active_entity_actions[entity_key]
            actions.discard(action_type)
            if not actions:
                # Keine Aktionen mehr - Entry entfernen
                del self._active_entity_actions[entity_key]
            else:
                self._active_entity_actions[entity_key] = (actions, timestamp)

    async def _cleanup_stale_entity_actions(self) -> int:
        """Entfernt veraltete Entity-Action Eintraege.

        Returns:
            Anzahl entfernter Eintraege.
        """
        cutoff = datetime.now(timezone.utc) - self._entity_action_ttl
        stale_keys = [
            k for k, (_, ts) in self._active_entity_actions.items()
            if ts < cutoff
        ]
        for key in stale_keys:
            del self._active_entity_actions[key]

        if stale_keys:
            logger.debug(
                "stale_entity_actions_cleaned",
                count=len(stale_keys),
            )
        return len(stale_keys)

    # =========================================================================
    # Decision Recording (fuer Explainability)
    # =========================================================================

    async def _record_decision(self, decision: OrchestrationDecision) -> None:
        """Zeichnet eine Entscheidung auf.

        Die History ist eine bounded deque - altes wird automatisch entfernt.
        """
        self._decision_history.append(decision)
        # Kein manuelles Slicing noetig - deque hat maxlen

        logger.debug(
            "orchestration_decision_recorded",
            decision_id=str(decision.decision_id),
            actions_count=len(decision.actions),
        )

    def _generate_reasoning(self, event: Event, actions: List[OrchestrationAction]) -> str:
        """Generiert eine Begruendung fuer die Entscheidung."""
        if not actions:
            return "Keine Aktion erforderlich."

        reasons = [a.reason for a in actions if a.reason]
        return " -> ".join(reasons) if reasons else "Standardverhalten"

    def _calculate_confidence(self, event: Event, actions: List[OrchestrationAction]) -> float:
        """Berechnet die Konfidenz der Entscheidung."""
        if not actions:
            return 1.0

        # Durchschnitt der Action-Confidences
        confidences = [a.confidence for a in actions]
        return sum(confidences) / len(confidences)

    # =========================================================================
    # Public API
    # =========================================================================

    def get_pending_actions(self) -> List[OrchestrationAction]:
        """Gibt ausstehende Aktionen zurueck."""
        return list(self._pending_actions)

    def get_decision_history(self, limit: int = 100) -> List[OrchestrationDecision]:
        """Gibt die Entscheidungs-History zurueck."""
        # deque unterstuetzt kein Slicing, daher zu list konvertieren
        return list(self._decision_history)[-limit:]

    async def get_metrics(self) -> Dict[str, Any]:
        """Gibt Orchestrierungs-Metriken zurueck."""
        return {
            "pending_actions_count": len(self._pending_actions),
            "pending_actions_max": self._max_pending_actions,
            "decision_history_count": len(self._decision_history),
            "active_entity_actions": {
                k: {"actions": list(actions), "since": ts.isoformat()}
                for k, (actions, ts) in self._active_entity_actions.items()
            },
        }

    async def process_pending_actions(self, max_actions: int = 50) -> int:
        """Verarbeitet ausstehende Aktionen (fuer Celery-Task).

        Returns:
            Anzahl verarbeiteter Aktionen
        """
        processed = 0

        async with self._action_lock:
            # Cleanup stale entity actions zuerst
            await self._cleanup_stale_entity_actions()

            # Sortiere nach Prioritaet (kopiere zu Liste fuer Sortierung)
            sorted_actions = sorted(
                list(self._pending_actions),
                key=lambda a: list(ActionPriority).index(a.priority)
            )

            for action in sorted_actions[:max_actions]:
                if action.status == "pending":
                    success = await self._execute_action(action)
                    if success:
                        processed += 1

            # Abgeschlossene entfernen - neue deque erstellen
            remaining = deque(
                (a for a in self._pending_actions
                 if a.status not in ["completed", "failed"]),
                maxlen=self._max_pending_actions
            )
            self._pending_actions = remaining

        return processed


# =============================================================================
# Singleton Factory
# =============================================================================

_orchestrator_instance: Optional[CrossModuleOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_cross_module_orchestrator() -> CrossModuleOrchestrator:
    """Factory-Funktion fuer CrossModuleOrchestrator Singleton."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        with _orchestrator_lock:
            if _orchestrator_instance is None:
                _orchestrator_instance = CrossModuleOrchestrator()
    return _orchestrator_instance


async def start_orchestrator() -> CrossModuleOrchestrator:
    """Startet den Orchestrator (fuer Application Startup)."""
    orchestrator = get_cross_module_orchestrator()
    await orchestrator.start()
    return orchestrator


async def stop_orchestrator() -> None:
    """Stoppt den Orchestrator (fuer Application Shutdown)."""
    orchestrator = get_cross_module_orchestrator()
    await orchestrator.stop()
