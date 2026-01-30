# -*- coding: utf-8 -*-
"""
UnifiedDecisionEngine - Zentrale Entscheidungskoordination.

Das "Grosshirn" des Systems:
- Sammelt ALLE anstehenden Entscheidungen/Empfehlungen
- Priorisiert nach GESAMT-IMPACT, nicht pro Modul
- Erkennt und verhindert KONFLIKTE
- Konsolidiert aehnliche Empfehlungen

TRUE Enterprise-Level: EIN Punkt der ALLES koordiniert.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Gauge, Histogram

from app.services.orchestration.cross_module_orchestrator import (
    OrchestrationAction,
    ActionType,
    ActionPriority,
    ModuleType,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

DECISIONS_PROCESSED = Counter(
    "unified_decisions_processed_total",
    "Anzahl verarbeiteter Entscheidungen",
    ["result"]  # approved, rejected, merged, deferred
)

CONFLICTS_DETECTED = Counter(
    "decision_conflicts_detected_total",
    "Anzahl erkannter Entscheidungskonflikte",
    ["conflict_type"]
)

DECISION_QUEUE_SIZE = Gauge(
    "unified_decision_queue_size",
    "Anzahl Entscheidungen in der Queue",
)

IMPACT_SCORE_HISTOGRAM = Histogram(
    "decision_impact_score",
    "Verteilung der Impact-Scores",
    buckets=[0, 10, 25, 50, 75, 100, 150, 200, 500, 1000]
)


# =============================================================================
# Enums und Typen
# =============================================================================

class ConflictType(str, Enum):
    """Typen von Entscheidungskonflikten."""
    RESOURCE_CONFLICT = "resource_conflict"           # Gleiches Geld, verschiedene Verwendungen
    TIMING_CONFLICT = "timing_conflict"               # Widersprüchliche Zeitplanungen
    GOAL_CONFLICT = "goal_conflict"                   # Widersprüchliche Ziele
    DUPLICATE = "duplicate"                           # Doppelte Empfehlungen
    SUPERSEDED = "superseded"                         # Neuere Empfehlung ersetzt aeltere


class DecisionStatus(str, Enum):
    """Status einer Entscheidung."""
    PENDING = "pending"             # Wartet auf Verarbeitung
    APPROVED = "approved"           # Zur Ausfuehrung freigegeben
    REJECTED = "rejected"           # Abgelehnt (z.B. Konflikt)
    MERGED = "merged"               # Mit anderer Entscheidung zusammengefuehrt
    DEFERRED = "deferred"           # Aufgeschoben (z.B. niedrige Prioritaet)
    EXECUTED = "executed"           # Ausgefuehrt


class ImpactDimension(str, Enum):
    """Dimensionen fuer Impact-Berechnung."""
    FINANCIAL = "financial"          # Direkte finanzielle Auswirkung
    RISK_REDUCTION = "risk_reduction"  # Risikominimierung
    COMPLIANCE = "compliance"         # Compliance/Fristen
    OPPORTUNITY = "opportunity"       # Verpasste Chancen
    CONVENIENCE = "convenience"       # Nutzerfreundlichkeit


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ImpactScore:
    """Multi-dimensionaler Impact-Score einer Entscheidung."""
    financial_impact: Decimal = Decimal("0")       # Positive = Ersparnis/Gewinn
    risk_reduction: float = 0.0                    # 0-100 Punkte
    compliance_urgency: float = 0.0                # 0-100 Punkte
    opportunity_value: Decimal = Decimal("0")      # Potenzieller Gewinn
    convenience_gain: float = 0.0                  # 0-100 Punkte

    # Gewichtungen (konfigurierbar pro User/Space)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "financial": 0.35,
        "risk": 0.25,
        "compliance": 0.20,
        "opportunity": 0.15,
        "convenience": 0.05,
    })

    @property
    def total_score(self) -> float:
        """Berechnet gewichteten Gesamt-Score."""
        # Normalisiere finanzielle Werte auf 0-100 Skala
        # (angenommen: 1000 EUR = 100 Punkte)
        financial_normalized = min(float(self.financial_impact) / 10, 100)
        opportunity_normalized = min(float(self.opportunity_value) / 10, 100)

        weighted = (
            financial_normalized * self.weights["financial"] +
            self.risk_reduction * self.weights["risk"] +
            self.compliance_urgency * self.weights["compliance"] +
            opportunity_normalized * self.weights["opportunity"] +
            self.convenience_gain * self.weights["convenience"]
        )
        return round(weighted, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "financial_impact": float(self.financial_impact),
            "risk_reduction": self.risk_reduction,
            "compliance_urgency": self.compliance_urgency,
            "opportunity_value": float(self.opportunity_value),
            "convenience_gain": self.convenience_gain,
            "total_score": self.total_score,
            "weights": self.weights,
        }


@dataclass
class UnifiedDecision:
    """Eine koordinierte Entscheidung im System."""
    id: UUID = field(default_factory=uuid4)

    # Ursprüngliche Aktion(en)
    source_actions: List[OrchestrationAction] = field(default_factory=list)

    # Kategorisierung
    primary_module: ModuleType = ModuleType.SYSTEM
    affected_modules: List[ModuleType] = field(default_factory=list)

    # Impact
    impact_score: ImpactScore = field(default_factory=ImpactScore)

    # Status
    status: DecisionStatus = DecisionStatus.PENDING

    # Begruendung
    title: str = ""
    description: str = ""
    reasoning: str = ""

    # Konflikt-Info
    conflicts_with: List[UUID] = field(default_factory=list)
    conflict_type: Optional[ConflictType] = None
    conflict_resolution: str = ""

    # Metadaten
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None

    # User-Context
    user_id: Optional[UUID] = None
    space_id: Optional[UUID] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer API/Serialisierung."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "reasoning": self.reasoning,
            "primary_module": self.primary_module.value,
            "affected_modules": [m.value for m in self.affected_modules],
            "impact_score": self.impact_score.to_dict(),
            "status": self.status.value,
            "conflicts_with": [str(c) for c in self.conflicts_with],
            "conflict_type": self.conflict_type.value if self.conflict_type else None,
            "conflict_resolution": self.conflict_resolution,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "source_actions_count": len(self.source_actions),
        }


@dataclass
class ConflictPair:
    """Ein erkannter Konflikt zwischen zwei Entscheidungen."""
    decision_a: UnifiedDecision
    decision_b: UnifiedDecision
    conflict_type: ConflictType
    reason: str
    resolution_strategy: str  # "keep_a", "keep_b", "merge", "defer_both", "user_choice"


# =============================================================================
# Conflict Detection Rules
# =============================================================================

@dataclass
class ConflictRule:
    """Regel zur Konflikterkennung."""
    name: str
    conflict_type: ConflictType
    check_fn: str  # Name der Methode
    resolution: str


CONFLICT_RULES: List[ConflictRule] = [
    ConflictRule(
        name="duplicate_recommendation",
        conflict_type=ConflictType.DUPLICATE,
        check_fn="_check_duplicate",
        resolution="merge"
    ),
    ConflictRule(
        name="opposing_financial_goals",
        conflict_type=ConflictType.GOAL_CONFLICT,
        check_fn="_check_opposing_goals",
        resolution="keep_higher_impact"
    ),
    ConflictRule(
        name="resource_competition",
        conflict_type=ConflictType.RESOURCE_CONFLICT,
        check_fn="_check_resource_conflict",
        resolution="prioritize_by_urgency"
    ),
    ConflictRule(
        name="timing_overlap",
        conflict_type=ConflictType.TIMING_CONFLICT,
        check_fn="_check_timing_conflict",
        resolution="sequence_by_priority"
    ),
]


# =============================================================================
# UnifiedDecisionEngine Service
# =============================================================================

class UnifiedDecisionEngine:
    """
    Singleton Service fuer zentrale Entscheidungskoordination.

    Funktionen:
    - Sammelt Entscheidungen aus allen Quellen
    - Berechnet Multi-dimensionale Impact-Scores
    - Erkennt und loest Konflikte
    - Priorisiert nach Gesamt-Impact
    - Verhindert widersprüchliche Empfehlungen

    Architektur:
    - OrchestrationActions -> UnifiedDecisions
    - Scoring -> Ranking -> Conflict Detection -> Resolution
    - Output: Priorisierte, konfliktfreie Entscheidungsliste
    """

    _instance: Optional["UnifiedDecisionEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "UnifiedDecisionEngine":
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

        # Decision Queue - BOUNDED um Memory Leaks zu verhindern
        self._max_queue_size = 5000
        self._decision_queue: Deque[UnifiedDecision] = deque(maxlen=self._max_queue_size)
        self._queue_lock = asyncio.Lock()

        # Processed Decisions (History) - BOUNDED
        self._max_history = 500
        self._processed_decisions: Deque[UnifiedDecision] = deque(maxlen=self._max_history)

        # Conflict Detection Cache - MIT TTL und automatischem Cleanup
        self._known_conflicts: Dict[Tuple[UUID, UUID], datetime] = {}
        self._conflict_cache_ttl = timedelta(hours=12)  # 12h TTL

        # Configuration
        self._auto_resolve_duplicates = True
        self._min_impact_threshold = 5.0  # Mindest-Score fuer Bearbeitung

        logger.info("unified_decision_engine_initialized")

    # =========================================================================
    # Decision Ingestion
    # =========================================================================

    async def ingest_action(self, action: OrchestrationAction) -> UnifiedDecision:
        """
        Nimmt eine OrchestrationAction entgegen und erstellt UnifiedDecision.

        Berechnet Impact-Score und fuegt zur Queue hinzu.
        """
        decision = self._convert_action_to_decision(action)

        # Impact Score berechnen
        decision.impact_score = await self._calculate_impact_score(action, decision)

        IMPACT_SCORE_HISTOGRAM.observe(decision.impact_score.total_score)

        async with self._queue_lock:
            self._decision_queue.append(decision)
            DECISION_QUEUE_SIZE.set(len(self._decision_queue))

        logger.debug(
            "decision_ingested",
            decision_id=str(decision.id),
            impact_score=decision.impact_score.total_score,
        )

        return decision

    async def ingest_actions(self, actions: List[OrchestrationAction]) -> List[UnifiedDecision]:
        """Nimmt mehrere Actions entgegen."""
        decisions = []
        for action in actions:
            decision = await self.ingest_action(action)
            decisions.append(decision)
        return decisions

    def _convert_action_to_decision(self, action: OrchestrationAction) -> UnifiedDecision:
        """Konvertiert OrchestrationAction zu UnifiedDecision."""
        # Modul aus Action ableiten
        primary_module = action.source_module or ModuleType.SYSTEM

        # Titel und Beschreibung aus Action-Daten
        data = action.action_data
        title = data.get("title", action.reason or "Systemempfehlung")
        description = data.get("description", action.impact_description or "")

        # User/Space IDs aus Event
        user_id = None
        space_id = None
        if action.source_event:
            user_id = action.source_event.user_id
            space_id = action.source_event.space_id

        return UnifiedDecision(
            source_actions=[action],
            primary_module=primary_module,
            affected_modules=[primary_module],
            title=title,
            description=description,
            reasoning=action.reason,
            user_id=user_id,
            space_id=space_id,
        )

    async def _calculate_impact_score(
        self,
        action: OrchestrationAction,
        decision: UnifiedDecision
    ) -> ImpactScore:
        """
        Berechnet multi-dimensionalen Impact-Score.

        Heuristiken basierend auf Action-Typ und Daten.
        """
        score = ImpactScore()
        data = action.action_data

        # Finanzielle Auswirkung
        if "potential_savings" in data:
            score.financial_impact = Decimal(str(data["potential_savings"]))
        elif "amount" in data:
            score.financial_impact = Decimal(str(data["amount"]))
        elif action.action_type == ActionType.CREATE_RECOMMENDATION:
            # Schaetze basierend auf Kategorie
            category = data.get("category", "")
            if category in ["refinanzierung", "versicherung", "cost_control"]:
                score.financial_impact = Decimal("500")  # Geschaetzter Wert

        # Risikoreduktion
        if action.action_type == ActionType.TRIGGER_WORKFLOW:
            score.risk_reduction = 50.0  # Workflows reduzieren Risiko
        if data.get("severity") == "critical":
            score.risk_reduction += 30.0
        elif data.get("severity") == "high":
            score.risk_reduction += 20.0

        # Compliance/Fristen
        if "deadline" in str(decision.description).lower():
            score.compliance_urgency = 80.0
        if "days_remaining" in data:
            days = data["days_remaining"]
            if days <= 7:
                score.compliance_urgency = 100.0
            elif days <= 14:
                score.compliance_urgency = 70.0
            elif days <= 30:
                score.compliance_urgency = 40.0

        # Opportunity Value
        if "potential_gain" in data:
            score.opportunity_value = Decimal(str(data["potential_gain"]))
        if data.get("category") == "investment":
            score.opportunity_value = Decimal("200")  # Geschaetzt

        # Convenience
        if action.action_type == ActionType.AUTO_APPROVE:
            score.convenience_gain = 80.0  # Automatisierung = Komfort

        return score

    # =========================================================================
    # Conflict Detection
    # =========================================================================

    async def detect_conflicts(self) -> List[ConflictPair]:
        """
        Erkennt Konflikte zwischen allen anstehenden Entscheidungen.

        Prueft jedes Paar auf moegliche Konflikte.
        """
        conflicts: List[ConflictPair] = []

        async with self._queue_lock:
            decisions = [d for d in self._decision_queue if d.status == DecisionStatus.PENDING]

        # Paarweise Pruefung
        for i, decision_a in enumerate(decisions):
            for decision_b in decisions[i+1:]:
                conflict = await self._check_pair_for_conflict(decision_a, decision_b)
                if conflict:
                    conflicts.append(conflict)
                    CONFLICTS_DETECTED.labels(
                        conflict_type=conflict.conflict_type.value
                    ).inc()

        return conflicts

    async def _check_pair_for_conflict(
        self,
        a: UnifiedDecision,
        b: UnifiedDecision
    ) -> Optional[ConflictPair]:
        """Prueft zwei Entscheidungen auf Konflikte."""

        # Schon bekannter Konflikt? Mit TTL-Pruefung
        key_ab = (a.id, b.id)
        key_ba = (b.id, a.id)
        now = datetime.now(timezone.utc)

        for key in [key_ab, key_ba]:
            if key in self._known_conflicts:
                if now - self._known_conflicts[key] < self._conflict_cache_ttl:
                    return None
                else:
                    # TTL abgelaufen - entfernen
                    del self._known_conflicts[key]

        # Duplikat-Pruefung
        if self._check_duplicate(a, b):
            return ConflictPair(
                decision_a=a,
                decision_b=b,
                conflict_type=ConflictType.DUPLICATE,
                reason="Entscheidungen haben identisches Ziel und Aktion",
                resolution_strategy="merge"
            )

        # Gegensaetzliche Ziele
        goal_conflict = self._check_opposing_goals(a, b)
        if goal_conflict:
            return ConflictPair(
                decision_a=a,
                decision_b=b,
                conflict_type=ConflictType.GOAL_CONFLICT,
                reason=goal_conflict,
                resolution_strategy="keep_higher_impact"
            )

        # Ressourcen-Konflikt
        resource_conflict = self._check_resource_conflict(a, b)
        if resource_conflict:
            return ConflictPair(
                decision_a=a,
                decision_b=b,
                conflict_type=ConflictType.RESOURCE_CONFLICT,
                reason=resource_conflict,
                resolution_strategy="prioritize_by_urgency"
            )

        return None

    def _check_duplicate(self, a: UnifiedDecision, b: UnifiedDecision) -> bool:
        """Prueft auf Duplikate."""
        # Gleicher Titel und gleiches Modul
        if a.title == b.title and a.primary_module == b.primary_module:
            return True

        # Gleiche Source-Entity
        if a.source_actions and b.source_actions:
            a_entity = a.source_actions[0].target_entity_id
            b_entity = b.source_actions[0].target_entity_id
            a_type = a.source_actions[0].action_type
            b_type = b.source_actions[0].action_type

            if a_entity and a_entity == b_entity and a_type == b_type:
                return True

        return False

    def _check_opposing_goals(
        self,
        a: UnifiedDecision,
        b: UnifiedDecision
    ) -> Optional[str]:
        """Prueft auf gegensaetzliche Ziele."""
        # Sparen vs. Investieren
        a_categories = self._extract_categories(a)
        b_categories = self._extract_categories(b)

        opposing_pairs = [
            ({"cost_control", "sparen"}, {"investment", "investition"}),
            ({"zahlungspause"}, {"vorzeitige_tilgung"}),
            ({"versicherung_kuendigen"}, {"versicherung_erweitern"}),
        ]

        for cat_set_1, cat_set_2 in opposing_pairs:
            if (a_categories & cat_set_1 and b_categories & cat_set_2) or \
               (a_categories & cat_set_2 and b_categories & cat_set_1):
                return f"Gegensaetzliche Ziele: {a_categories} vs {b_categories}"

        return None

    def _check_resource_conflict(
        self,
        a: UnifiedDecision,
        b: UnifiedDecision
    ) -> Optional[str]:
        """Prueft auf Ressourcen-Konflikte (gleiches Geld, verschiedene Verwendungen)."""
        # Beide erfordern signifikante finanzielle Mittel?
        a_cost = abs(float(a.impact_score.financial_impact))
        b_cost = abs(float(b.impact_score.financial_impact))

        if a_cost > 1000 and b_cost > 1000:
            # Gleiches Modul = wahrscheinlich gleiches Budget
            if a.primary_module == b.primary_module:
                return f"Ressourcen-Konflikt: Beide Entscheidungen erfordern >1000 EUR"

        return None

    def _extract_categories(self, decision: UnifiedDecision) -> Set[str]:
        """Extrahiert Kategorien aus einer Entscheidung."""
        categories = set()

        for action in decision.source_actions:
            if "category" in action.action_data:
                categories.add(action.action_data["category"].lower())

        # Keywords aus Title/Description
        text = (decision.title + " " + decision.description).lower()
        keywords = [
            "sparen", "investition", "investment", "cost_control",
            "zahlungspause", "tilgung", "kuendigen", "erweitern",
            "versicherung", "refinanzierung"
        ]
        for kw in keywords:
            if kw in text:
                categories.add(kw)

        return categories

    # =========================================================================
    # Conflict Resolution
    # =========================================================================

    async def resolve_conflicts(self, conflicts: List[ConflictPair]) -> None:
        """
        Loest erkannte Konflikte auf.

        Strategien:
        - merge: Duplikate zusammenfuehren
        - keep_higher_impact: Hoeheren Impact behalten
        - prioritize_by_urgency: Nach Dringlichkeit priorisieren
        - defer_both: Beide aufschieben und User fragen
        """
        for conflict in conflicts:
            await self._resolve_conflict(conflict)

    async def _resolve_conflict(self, conflict: ConflictPair) -> None:
        """Loest einen einzelnen Konflikt."""
        a = conflict.decision_a
        b = conflict.decision_b

        if conflict.resolution_strategy == "merge":
            await self._merge_decisions(a, b)

        elif conflict.resolution_strategy == "keep_higher_impact":
            if a.impact_score.total_score >= b.impact_score.total_score:
                b.status = DecisionStatus.REJECTED
                b.conflict_type = conflict.conflict_type
                b.conflict_resolution = f"Ersetzt durch Entscheidung {a.id} mit hoeherem Impact"
                DECISIONS_PROCESSED.labels(result="rejected").inc()
            else:
                a.status = DecisionStatus.REJECTED
                a.conflict_type = conflict.conflict_type
                a.conflict_resolution = f"Ersetzt durch Entscheidung {b.id} mit hoeherem Impact"
                DECISIONS_PROCESSED.labels(result="rejected").inc()

        elif conflict.resolution_strategy == "prioritize_by_urgency":
            # Nach Compliance-Urgency sortieren
            if a.impact_score.compliance_urgency > b.impact_score.compliance_urgency:
                b.status = DecisionStatus.DEFERRED
                b.conflict_resolution = f"Aufgeschoben zugunsten dringenderer Entscheidung {a.id}"
                DECISIONS_PROCESSED.labels(result="deferred").inc()
            else:
                a.status = DecisionStatus.DEFERRED
                a.conflict_resolution = f"Aufgeschoben zugunsten dringenderer Entscheidung {b.id}"
                DECISIONS_PROCESSED.labels(result="deferred").inc()

        # Konflikt als bekannt markieren mit Timestamp
        self._known_conflicts[(a.id, b.id)] = datetime.now(timezone.utc)

        logger.info(
            "conflict_resolved",
            conflict_type=conflict.conflict_type.value,
            resolution=conflict.resolution_strategy,
            decision_a=str(a.id),
            decision_b=str(b.id),
        )

    async def _merge_decisions(self, a: UnifiedDecision, b: UnifiedDecision) -> None:
        """Fuehrt zwei Entscheidungen zusammen."""
        # B wird zu A gemerged
        b.status = DecisionStatus.MERGED
        b.conflict_resolution = f"Zusammengefuehrt mit Entscheidung {a.id}"

        # A erhaelt kombinierten Impact
        a.source_actions.extend(b.source_actions)
        a.affected_modules = list(set(a.affected_modules + b.affected_modules))

        # Impact-Scores kombinieren (hoechsten Wert nehmen)
        a.impact_score.financial_impact = max(
            a.impact_score.financial_impact,
            b.impact_score.financial_impact
        )
        a.impact_score.risk_reduction = max(
            a.impact_score.risk_reduction,
            b.impact_score.risk_reduction
        )

        DECISIONS_PROCESSED.labels(result="merged").inc()

    # =========================================================================
    # Prioritization
    # =========================================================================

    async def get_prioritized_decisions(
        self,
        user_id: Optional[UUID] = None,
        space_id: Optional[UUID] = None,
        limit: int = 10,
        min_score: Optional[float] = None
    ) -> List[UnifiedDecision]:
        """
        Gibt priorisierte Entscheidungsliste zurueck.

        Workflow:
        1. Konflikte erkennen und loesen
        2. Nach Impact-Score sortieren
        3. Nur PENDING/APPROVED zurueckgeben
        """
        # Konflikte erkennen und loesen
        conflicts = await self.detect_conflicts()
        if conflicts:
            await self.resolve_conflicts(conflicts)

        async with self._queue_lock:
            # Filtern nach User/Space
            decisions = [
                d for d in self._decision_queue
                if d.status in [DecisionStatus.PENDING, DecisionStatus.APPROVED]
            ]

            if user_id:
                decisions = [d for d in decisions if d.user_id == user_id]
            if space_id:
                decisions = [d for d in decisions if d.space_id == space_id]

            # Mindest-Score filtern
            threshold = min_score or self._min_impact_threshold
            decisions = [d for d in decisions if d.impact_score.total_score >= threshold]

            # Nach Impact-Score sortieren (hoechster zuerst)
            decisions.sort(key=lambda d: d.impact_score.total_score, reverse=True)

            return decisions[:limit]

    async def get_pending_count(self) -> int:
        """Anzahl ausstehender Entscheidungen."""
        async with self._queue_lock:
            return len([d for d in self._decision_queue if d.status == DecisionStatus.PENDING])

    # =========================================================================
    # Decision Execution
    # =========================================================================

    async def approve_decision(self, decision_id: UUID) -> bool:
        """Genehmigt eine Entscheidung zur Ausfuehrung."""
        async with self._queue_lock:
            for decision in self._decision_queue:
                if decision.id == decision_id:
                    decision.status = DecisionStatus.APPROVED
                    decision.processed_at = datetime.now(timezone.utc)
                    DECISIONS_PROCESSED.labels(result="approved").inc()
                    logger.info("decision_approved", decision_id=str(decision_id))
                    return True
        return False

    async def reject_decision(self, decision_id: UUID, reason: str = "") -> bool:
        """Lehnt eine Entscheidung ab."""
        async with self._queue_lock:
            for decision in self._decision_queue:
                if decision.id == decision_id:
                    decision.status = DecisionStatus.REJECTED
                    decision.conflict_resolution = reason or "Manuell abgelehnt"
                    decision.processed_at = datetime.now(timezone.utc)
                    DECISIONS_PROCESSED.labels(result="rejected").inc()
                    logger.info("decision_rejected", decision_id=str(decision_id), reason=reason)
                    return True
        return False

    async def execute_approved_decisions(self) -> int:
        """
        Fuehrt alle genehmigten Entscheidungen aus.

        Gibt Anzahl ausgefuehrter Entscheidungen zurueck.
        """
        executed = 0

        async with self._queue_lock:
            approved = [
                d for d in self._decision_queue
                if d.status == DecisionStatus.APPROVED
            ]

        for decision in approved:
            success = await self._execute_decision(decision)
            if success:
                decision.status = DecisionStatus.EXECUTED
                decision.executed_at = datetime.now(timezone.utc)
                executed += 1

                # Zu History verschieben
                self._processed_decisions.append(decision)

        # Ausgefuehrte aus Queue entfernen
        async with self._queue_lock:
            self._decision_queue = [
                d for d in self._decision_queue
                if d.status != DecisionStatus.EXECUTED
            ]
            DECISION_QUEUE_SIZE.set(len(self._decision_queue))

        # History begrenzen
        if len(self._processed_decisions) > self._max_history:
            self._processed_decisions = self._processed_decisions[-self._max_history:]

        return executed

    async def _execute_decision(self, decision: UnifiedDecision) -> bool:
        """Fuehrt eine einzelne Entscheidung aus."""
        try:
            # Hole Orchestrator und fuehre Source-Actions aus
            from app.services.orchestration import get_cross_module_orchestrator


            orchestrator = get_cross_module_orchestrator()

            for action in decision.source_actions:
                await orchestrator._execute_action(action)

            logger.info(
                "decision_executed",
                decision_id=str(decision.id),
                actions_count=len(decision.source_actions),
            )
            return True

        except Exception as e:
            logger.error(
                "decision_execution_failed",
                decision_id=str(decision.id),
                **safe_error_log(e),
            )
            return False

    # =========================================================================
    # Analytics & Reporting
    # =========================================================================

    async def get_decision_summary(
        self,
        user_id: Optional[UUID] = None,
        space_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Gibt Zusammenfassung aller Entscheidungen zurueck.

        Fuer Dashboard-Anzeige.
        """
        async with self._queue_lock:
            decisions = list(self._decision_queue)

        if user_id:
            decisions = [d for d in decisions if d.user_id == user_id]
        if space_id:
            decisions = [d for d in decisions if d.space_id == space_id]

        # Status-Verteilung
        status_counts = {}
        for status in DecisionStatus:
            status_counts[status.value] = len([d for d in decisions if d.status == status])

        # Modul-Verteilung
        module_counts = {}
        for decision in decisions:
            module = decision.primary_module.value
            module_counts[module] = module_counts.get(module, 0) + 1

        # Top Impact Decisions
        pending = [d for d in decisions if d.status == DecisionStatus.PENDING]
        pending.sort(key=lambda d: d.impact_score.total_score, reverse=True)
        top_decisions = [d.to_dict() for d in pending[:5]]

        # Konflikt-Statistik
        conflict_count = len([d for d in decisions if d.conflict_type is not None])

        # Gesamt-Impact
        total_financial_impact = sum(
            float(d.impact_score.financial_impact)
            for d in pending
        )

        return {
            "total_decisions": len(decisions),
            "status_distribution": status_counts,
            "module_distribution": module_counts,
            "top_decisions": top_decisions,
            "conflict_count": conflict_count,
            "potential_financial_impact": total_financial_impact,
            "average_impact_score": (
                sum(d.impact_score.total_score for d in pending) / len(pending)
                if pending else 0
            ),
        }

    async def get_metrics(self) -> Dict[str, Any]:
        """Gibt Engine-Metriken zurueck."""
        async with self._queue_lock:
            pending = len([d for d in self._decision_queue if d.status == DecisionStatus.PENDING])
            approved = len([d for d in self._decision_queue if d.status == DecisionStatus.APPROVED])

        return {
            "queue_size": len(self._decision_queue),
            "queue_max_size": self._max_queue_size,
            "pending_count": pending,
            "approved_count": approved,
            "processed_count": len(self._processed_decisions),
            "processed_max_size": self._max_history,
            "known_conflicts": len(self._known_conflicts),
        }

    # =========================================================================
    # Maintenance
    # =========================================================================

    async def cleanup_stale_conflicts(self) -> int:
        """Entfernt veraltete Konflikt-Cache-Eintraege.

        Returns:
            Anzahl entfernter Eintraege.
        """
        cutoff = datetime.now(timezone.utc) - self._conflict_cache_ttl
        stale_keys = [
            k for k, ts in self._known_conflicts.items()
            if ts < cutoff
        ]
        for key in stale_keys:
            del self._known_conflicts[key]

        if stale_keys:
            logger.debug(
                "stale_conflicts_cleaned",
                count=len(stale_keys),
            )
        return len(stale_keys)

    async def cleanup_old_decisions(self, days_to_keep: int = 30) -> int:
        """Raeumt alte verarbeitete Entscheidungen auf.

        Note: Mit bounded deque ist manuelles Cleanup weniger kritisch,
        aber wir behalten diese Methode fuer explizites Cleanup.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

        # Da wir deque nutzen, filtern wir und erstellen neue deque
        original_count = len(self._processed_decisions)
        remaining = deque(
            (d for d in self._processed_decisions
             if d.processed_at and d.processed_at > cutoff),
            maxlen=self._max_history
        )
        self._processed_decisions = remaining

        removed = original_count - len(self._processed_decisions)

        if removed > 0:
            logger.info("old_decisions_cleaned_up", removed_count=removed)

        # Auch Conflict-Cache aufraumen
        await self.cleanup_stale_conflicts()

        return removed


# =============================================================================
# Singleton Factory
# =============================================================================

_engine_instance: Optional[UnifiedDecisionEngine] = None
_engine_lock = threading.Lock()


def get_unified_decision_engine() -> UnifiedDecisionEngine:
    """Factory-Funktion fuer UnifiedDecisionEngine Singleton."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = UnifiedDecisionEngine()
    return _engine_instance
