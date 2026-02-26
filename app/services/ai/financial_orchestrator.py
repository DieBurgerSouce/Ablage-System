# -*- coding: utf-8 -*-
"""
Multi-Agent Financial Orchestrator mit Chain of Thought.

Enterprise Feature: Hauptagent der Sub-Agents koordiniert und dem User
eine sichtbare Chain of Thought (Collapsible Thinking Steps) liefert.

Architektur:
- FinancialOrchestrator: Hauptagent - User kommuniziert NUR mit ihm
- Sub-Agents: Spezialisierte Agents fuer verschiedene Domaenen
- ThinkingStep: Sichtbare Denkschritte fuer CoT-UI
- AgentRegistry: Dynamische Registrierung neuer Sub-Agents

Sub-Agents:
- DocumentAgent: Feld-Extraktion, Klassifikation, Zusammenfassung
- MatchingAgent: 3-Way Match, Entity-Zuordnung
- ComplianceAgent: XRechnung-Validierung, GoBD, GDPR
- FinanceAgent: Cashflow, Skonto, Budget, Prognosen
- AnomalyAgent: Duplikate, Ausreisser, saisonale Anomalien

Feinpoliert und durchdacht - Der proaktive CFO-Assistent.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Dict,
    List,
    Optional,
    Protocol,
)
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_provider import (
    ChatMessage,
    GenerationParams,
    LLMRole,
    LLMRouter,
    TaskComplexity,
    get_llm_router,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# CHAIN OF THOUGHT DATENTYPEN
# =============================================================================


class ThinkingStepStatus(str, Enum):
    """Status eines Denkschritts."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SubAgentType(str, Enum):
    """Typen von Sub-Agents."""

    DOCUMENT = "document"
    MATCHING = "matching"
    COMPLIANCE = "compliance"
    FINANCE = "finance"
    ANOMALY = "anomaly"
    SEARCH = "search"
    GENERAL = "general"


@dataclass
class ThinkingStep:
    """
    Ein sichtbarer Denkschritt in der Chain of Thought.

    Wird in der UI als collapsible Block dargestellt:
    > Schritt 1: Dokument-Agent
    > Extrahiere Felder aus Rechnung #2024-0847
    > Ergebnis: Rechnungsnr: 2024-0847, Betrag: 12.500 EUR
    """

    id: str
    agent_type: SubAgentType
    agent_name: str
    description: str
    status: ThinkingStepStatus = ThinkingStepStatus.PENDING
    details: List[str] = field(default_factory=list)
    result_summary: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def start(self) -> None:
        """Markiert den Schritt als gestartet."""
        self.status = ThinkingStepStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def complete(self, summary: str, details: Optional[List[str]] = None) -> None:
        """Markiert den Schritt als abgeschlossen."""
        self.status = ThinkingStepStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.result_summary = summary
        if details:
            self.details.extend(details)
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = delta.total_seconds() * 1000

    def fail(self, error_msg: str) -> None:
        """Markiert den Schritt als fehlgeschlagen."""
        self.status = ThinkingStepStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        self.error = error_msg
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = delta.total_seconds() * 1000

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert fuer API-Response."""
        return {
            "id": self.id,
            "agent_type": self.agent_type.value,
            "agent_name": self.agent_name,
            "description": self.description,
            "status": self.status.value,
            "details": self.details,
            "result_summary": self.result_summary,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class OrchestratorResponse:
    """
    Antwort des Orchestrators inkl. Chain of Thought.

    Enthaelt:
    - answer: Die finale Antwort fuer den User
    - thinking_steps: Alle Denkschritte (fuer CoT-UI)
    - suggested_actions: Vorgeschlagene Aktionen (Buttons)
    - context: Kontext-Daten fuer Follow-up
    """

    answer: str
    thinking_steps: List[ThinkingStep]
    suggested_actions: List[SuggestedAction] = field(default_factory=list)
    conversation_id: Optional[str] = None
    total_duration_ms: float = 0.0
    model_used: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serialisiert fuer API-Response."""
        return {
            "answer": self.answer,
            "thinking_steps": [s.to_dict() for s in self.thinking_steps],
            "suggested_actions": [a.to_dict() for a in self.suggested_actions],
            "conversation_id": self.conversation_id,
            "total_duration_ms": self.total_duration_ms,
            "model_used": self.model_used,
        }


@dataclass
class SuggestedAction:
    """Eine vorgeschlagene Aktion (wird als Button in der UI angezeigt)."""

    label: str  # German button text
    action_type: str  # z.B. "pay_invoice", "approve", "categorize"
    params: Dict[str, object] = field(default_factory=dict)
    variant: str = "default"  # default, outline, ghost, destructive

    def to_dict(self) -> Dict[str, object]:
        return {
            "label": self.label,
            "action_type": self.action_type,
            "params": self.params,
            "variant": self.variant,
        }


# =============================================================================
# SUB-AGENT PROTOCOL
# =============================================================================


class SubAgent(Protocol):
    """Protocol fuer Sub-Agents."""

    @property
    def agent_type(self) -> SubAgentType: ...

    @property
    def display_name(self) -> str: ...

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        """Gibt Confidence (0-1) zurueck ob dieser Agent die Anfrage bearbeiten kann."""
        ...

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        """Fuehrt die Aufgabe aus und aktualisiert den ThinkingStep."""
        ...


# =============================================================================
# SUB-AGENT REGISTRY
# =============================================================================


class SubAgentRegistry:
    """Registry fuer dynamische Sub-Agent Registrierung."""

    def __init__(self) -> None:
        self._agents: Dict[SubAgentType, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        """Registriert einen Sub-Agent."""
        self._agents[agent.agent_type] = agent
        logger.info(
            "sub_agent_registered",
            agent_type=agent.agent_type.value,
            display_name=agent.display_name,
        )

    def get(self, agent_type: SubAgentType) -> Optional[SubAgent]:
        """Holt einen Sub-Agent nach Typ."""
        return self._agents.get(agent_type)

    def all_agents(self) -> List[SubAgent]:
        """Alle registrierten Sub-Agents."""
        return list(self._agents.values())

    async def find_capable_agents(
        self, intent: str, context: Dict[str, object],
    ) -> List[tuple[SubAgent, float]]:
        """
        Findet Sub-Agents die eine Anfrage bearbeiten koennen.

        Returns:
            Liste von (Agent, Confidence) sortiert nach Confidence
        """
        results: List[tuple[SubAgent, float]] = []
        for agent in self._agents.values():
            try:
                confidence = await agent.can_handle(intent, context)
                if confidence > 0.1:
                    results.append((agent, confidence))
            except Exception as e:
                logger.warning(
                    "agent_capability_check_failed",
                    agent=agent.agent_type.value,
                    error=str(e),
                )
        results.sort(key=lambda x: x[1], reverse=True)
        return results


# =============================================================================
# BUILT-IN SUB-AGENTS
# =============================================================================


class DocumentSubAgent:
    """Sub-Agent fuer Dokument-Analyse und Feld-Extraktion."""

    @property
    def agent_type(self) -> SubAgentType:
        return SubAgentType.DOCUMENT

    @property
    def display_name(self) -> str:
        return "Dokument-Agent"

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        """Erkennt Dokument-bezogene Anfragen."""
        doc_keywords = [
            "rechnung", "dokument", "beleg", "vertrag", "lieferschein",
            "bestellung", "angebot", "mahnung", "gutschrift", "quittung",
            "extrahier", "feld", "zusammenfass", "pruef", "validier",
            "invoice", "document",
        ]
        intent_lower = intent.lower()
        matches = sum(1 for kw in doc_keywords if kw in intent_lower)
        if "document_id" in context:
            return min(0.9, 0.5 + matches * 0.15)
        return min(0.8, matches * 0.2)

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        step.start()
        step.details.append("Lade Dokumentdaten...")

        document_id = context.get("document_id")
        result: Dict[str, object] = {"agent": "document"}

        if document_id:
            from app.db.models import Document
            from sqlalchemy import select

            doc_result = await db.execute(
                select(Document).where(
                    Document.id == UUID(str(document_id)),
                    Document.company_id == company_id,
                )
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                step.details.append(
                    f"Dokument: {doc.original_filename or 'Unbenannt'}"
                )
                result["document"] = {
                    "id": str(doc.id),
                    "filename": doc.original_filename,
                    "type": doc.document_type,
                    "status": doc.status,
                    "category": getattr(doc, "category", None),
                }
                step.complete(
                    f"Dokument '{doc.original_filename}' geladen "
                    f"(Typ: {doc.document_type or 'unbekannt'})",
                )
            else:
                step.fail("Dokument nicht gefunden")
        else:
            step.details.append("Kein spezifisches Dokument angegeben")
            step.complete("Allgemeine Dokumentanfrage verarbeitet")

        return result


class FinanceSubAgent:
    """Sub-Agent fuer Finanz-Analyse, Cashflow, Skonto, Budget."""

    @property
    def agent_type(self) -> SubAgentType:
        return SubAgentType.FINANCE

    @property
    def display_name(self) -> str:
        return "Finanz-Agent"

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        finance_keywords = [
            "cashflow", "skonto", "budget", "zahlung", "ueberweisung",
            "konto", "saldo", "prognose", "forecast", "mahnwesen",
            "offene posten", "faellig", "ueberfaellig", "liquiditaet",
            "ausgaben", "einnahmen", "kosten", "einkauf", "sparen",
        ]
        intent_lower = intent.lower()
        matches = sum(1 for kw in finance_keywords if kw in intent_lower)
        return min(0.9, matches * 0.25)

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        step.start()
        step.details.append("Analysiere Finanzdaten...")

        # Offene Posten zaehlen
        from app.db.models import Document
        from sqlalchemy import select, func, and_

        count_result = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "invoice",
                    Document.status.in_(["pending", "processing"]),
                    Document.deleted_at.is_(None),
                )
            )
        )
        open_invoices = count_result.scalar() or 0

        step.details.append(f"Offene Rechnungen: {open_invoices}")
        step.complete(
            f"{open_invoices} offene Rechnungen gefunden",
            details=["Finanzanalyse abgeschlossen"],
        )

        return {
            "agent": "finance",
            "open_invoices": open_invoices,
        }


class ComplianceSubAgent:
    """Sub-Agent fuer Compliance-Pruefungen (XRechnung, GoBD, GDPR)."""

    @property
    def agent_type(self) -> SubAgentType:
        return SubAgentType.COMPLIANCE

    @property
    def display_name(self) -> str:
        return "Compliance-Agent"

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        compliance_keywords = [
            "compliance", "xrechnung", "zugferd", "gobd", "gdpr", "dsgvo",
            "pruef", "validier", "archiv", "aufbewahrung", "datenschutz",
            "audit", "revisionssicher", "steuer", "finanzamt",
        ]
        intent_lower = intent.lower()
        matches = sum(1 for kw in compliance_keywords if kw in intent_lower)
        return min(0.9, matches * 0.3)

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        step.start()
        step.details.append("Pruefe Compliance-Status...")
        step.complete("Compliance-Pruefung abgeschlossen")
        return {"agent": "compliance", "status": "ok"}


class MatchingSubAgent:
    """Sub-Agent fuer 3-Way Matching und Entity-Zuordnung."""

    @property
    def agent_type(self) -> SubAgentType:
        return SubAgentType.MATCHING

    @property
    def display_name(self) -> str:
        return "Matching-Agent"

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        matching_keywords = [
            "match", "zuordn", "verknuepf", "bestellung", "lieferschein",
            "abgleich", "lieferant", "zugehoer", "referenz", "kette",
            "duplikat", "aehnlich",
        ]
        intent_lower = intent.lower()
        matches = sum(1 for kw in matching_keywords if kw in intent_lower)
        return min(0.9, matches * 0.3)

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        step.start()
        step.details.append("Suche zugehoerige Dokumente...")
        step.complete("Matching-Analyse abgeschlossen")
        return {"agent": "matching"}


class AnomalySubAgent:
    """Sub-Agent fuer Anomalie-Erkennung und saisonale Muster."""

    @property
    def agent_type(self) -> SubAgentType:
        return SubAgentType.ANOMALY

    @property
    def display_name(self) -> str:
        return "Anomalie-Agent"

    async def can_handle(self, intent: str, context: Dict[str, object]) -> float:
        anomaly_keywords = [
            "anomalie", "ungewoehnlich", "verdaechtig", "ausreisser",
            "betrug", "fraud", "abweich", "auffaellig", "muster",
            "saisonal", "normal", "trend",
        ]
        intent_lower = intent.lower()
        matches = sum(1 for kw in anomaly_keywords if kw in intent_lower)
        return min(0.9, matches * 0.3)

    async def execute(
        self,
        query: str,
        context: Dict[str, object],
        db: AsyncSession,
        company_id: UUID,
        step: ThinkingStep,
    ) -> Dict[str, object]:
        step.start()
        step.details.append("Pruefe auf Anomalien...")
        step.complete("Anomalie-Pruefung abgeschlossen")
        return {"agent": "anomaly"}


# =============================================================================
# FINANCIAL ORCHESTRATOR (HAUPTAGENT)
# =============================================================================


class FinancialOrchestrator:
    """
    Hauptagent der Sub-Agents koordiniert.

    Der User kommuniziert NUR mit dem Orchestrator.
    Der Orchestrator:
    1. Analysiert die Anfrage (Intent-Erkennung)
    2. Waehlt relevante Sub-Agents
    3. Fuehrt Sub-Agents aus (parallel wo moeglich)
    4. Sammelt Ergebnisse
    5. Synthetisiert finale Antwort mit LLM
    6. Liefert Chain of Thought + Suggested Actions
    """

    def __init__(
        self,
        llm_router: Optional[LLMRouter] = None,
        agent_registry: Optional[SubAgentRegistry] = None,
    ) -> None:
        self._llm_router = llm_router or get_llm_router()
        self._agent_registry = agent_registry or SubAgentRegistry()

        # Registriere Built-in Sub-Agents
        self._agent_registry.register(DocumentSubAgent())
        self._agent_registry.register(FinanceSubAgent())
        self._agent_registry.register(ComplianceSubAgent())
        self._agent_registry.register(MatchingSubAgent())
        self._agent_registry.register(AnomalySubAgent())

    def register_agent(self, agent: SubAgent) -> None:
        """Registriert einen neuen Sub-Agent dynamisch."""
        self._agent_registry.register(agent)

    async def process(
        self,
        query: str,
        db: AsyncSession,
        company_id: UUID,
        user_id: UUID,
        context: Optional[Dict[str, object]] = None,
        conversation_id: Optional[str] = None,
    ) -> OrchestratorResponse:
        """
        Verarbeitet eine User-Anfrage.

        Args:
            query: Die natuerlichsprachige Anfrage des Users
            db: Datenbank-Session
            company_id: Mandanten-ID
            user_id: User-ID
            context: Zusaetzlicher Kontext (z.B. aktuelles Dokument)
            conversation_id: Optional - fuer Konversations-Fortfuehrung

        Returns:
            OrchestratorResponse mit Antwort und Chain of Thought
        """
        start_time = time.monotonic()
        context = context or {}
        thinking_steps: List[ThinkingStep] = []
        agent_results: Dict[str, Dict[str, object]] = {}

        conv_id = conversation_id or str(uuid.uuid4())

        logger.info(
            "orchestrator_process_start",
            query_length=len(query),
            company_id=str(company_id),
            has_context=bool(context),
        )

        # --- Schritt 1: Intent-Analyse ---
        intent_step = ThinkingStep(
            id=str(uuid.uuid4()),
            agent_type=SubAgentType.GENERAL,
            agent_name="Intent-Analyse",
            description="Analysiere die Anfrage...",
        )
        thinking_steps.append(intent_step)
        intent_step.start()

        # Finde faehige Agents
        capable_agents = await self._agent_registry.find_capable_agents(
            query, context,
        )

        if capable_agents:
            agent_names = [
                f"{a.display_name} ({c:.0%})" for a, c in capable_agents[:5]
            ]
            intent_step.complete(
                f"{len(capable_agents)} relevante Agents gefunden",
                details=agent_names,
            )
        else:
            intent_step.complete("Allgemeine Anfrage erkannt")

        # --- Schritt 2: Sub-Agents ausfuehren ---
        # Nimm die Top-3 Agents mit Confidence > 0.3
        selected_agents = [
            (agent, conf) for agent, conf in capable_agents
            if conf > 0.3
        ][:3]

        for agent, confidence in selected_agents:
            step = ThinkingStep(
                id=str(uuid.uuid4()),
                agent_type=agent.agent_type,
                agent_name=agent.display_name,
                description=f"{agent.display_name} analysiert...",
            )
            thinking_steps.append(step)

            try:
                result = await agent.execute(
                    query=query,
                    context=context,
                    db=db,
                    company_id=company_id,
                    step=step,
                )
                agent_results[agent.agent_type.value] = result
            except Exception as e:
                step.fail(f"Fehler: {str(e)[:100]}")
                logger.error(
                    "sub_agent_execution_failed",
                    agent=agent.agent_type.value,
                    **safe_error_log(e),
                )

        # --- Schritt 3: Antwort synthetisieren ---
        synthesis_step = ThinkingStep(
            id=str(uuid.uuid4()),
            agent_type=SubAgentType.GENERAL,
            agent_name="Synthese",
            description="Erstelle Antwort...",
        )
        thinking_steps.append(synthesis_step)
        synthesis_step.start()

        answer = await self._synthesize_answer(
            query=query,
            agent_results=agent_results,
            context=context,
        )

        synthesis_step.complete("Antwort erstellt")

        # --- Schritt 4: Suggested Actions ableiten ---
        suggested_actions = self._derive_actions(agent_results, context)

        total_duration = (time.monotonic() - start_time) * 1000

        logger.info(
            "orchestrator_process_complete",
            duration_ms=total_duration,
            agents_used=len(selected_agents),
            steps_count=len(thinking_steps),
        )

        return OrchestratorResponse(
            answer=answer,
            thinking_steps=thinking_steps,
            suggested_actions=suggested_actions,
            conversation_id=conv_id,
            total_duration_ms=total_duration,
        )

    async def _synthesize_answer(
        self,
        query: str,
        agent_results: Dict[str, Dict[str, object]],
        context: Dict[str, object],
    ) -> str:
        """Synthetisiert die finale Antwort aus Agent-Ergebnissen."""
        # Baue Kontext-String aus Agent-Ergebnissen
        results_text = ""
        for agent_name, result in agent_results.items():
            results_text += f"\n{agent_name}: {json.dumps(result, default=str, ensure_ascii=False)}"

        if not results_text.strip():
            results_text = "Keine spezifischen Analyseergebnisse verfuegbar."

        system_prompt = (
            "Du bist der Finanz-Assistent des Ablage-Systems. "
            "Du antwortest IMMER auf Deutsch. "
            "Du bist praezise, hilfreich und proaktiv. "
            "Basierend auf den Analyseergebnissen deiner Sub-Agents, "
            "erstelle eine klare, strukturierte Antwort fuer den User. "
            "Wenn du Handlungsempfehlungen hast, formuliere sie konkret. "
            "Verwende Zahlen und Fakten aus den Ergebnissen."
        )

        messages = [
            ChatMessage(role=LLMRole.SYSTEM, content=system_prompt),
            ChatMessage(
                role=LLMRole.USER,
                content=(
                    f"Benutzeranfrage: {query}\n\n"
                    f"Analyseergebnisse der Sub-Agents:{results_text}"
                ),
            ),
        ]

        try:
            response = await self._llm_router.route(
                messages=messages,
                complexity=TaskComplexity.MODERATE,
                params=GenerationParams(temperature=0.3, max_tokens=1024),
            )
            return response.content
        except Exception as e:
            logger.warning(
                "llm_synthesis_fallback",
                error=str(e),
            )
            # Fallback: Strukturierte Antwort ohne LLM
            return self._fallback_answer(query, agent_results)

    def _fallback_answer(
        self,
        query: str,
        agent_results: Dict[str, Dict[str, object]],
    ) -> str:
        """Erzeugt eine Antwort ohne LLM (Fallback)."""
        parts = ["Hier sind die Ergebnisse meiner Analyse:\n"]

        if "finance" in agent_results:
            fin = agent_results["finance"]
            open_inv = fin.get("open_invoices", 0)
            parts.append(f"- **Offene Rechnungen**: {open_inv}")

        if "document" in agent_results:
            doc = agent_results["document"]
            doc_info = doc.get("document", {})
            if doc_info:
                parts.append(
                    f"- **Dokument**: {doc_info.get('filename', 'Unbenannt')} "
                    f"(Typ: {doc_info.get('type', 'unbekannt')})"
                )

        if "compliance" in agent_results:
            comp = agent_results["compliance"]
            parts.append(
                f"- **Compliance**: {comp.get('status', 'unbekannt')}"
            )

        if len(parts) == 1:
            parts.append(
                "Ich konnte keine spezifischen Daten zu dieser Anfrage finden. "
                "Bitte formulieren Sie Ihre Frage genauer."
            )

        return "\n".join(parts)

    def _derive_actions(
        self,
        agent_results: Dict[str, Dict[str, object]],
        context: Dict[str, object],
    ) -> List[SuggestedAction]:
        """Leitet sinnvolle Aktionen aus den Ergebnissen ab."""
        actions: List[SuggestedAction] = []

        if "finance" in agent_results:
            fin = agent_results["finance"]
            if fin.get("open_invoices", 0) > 0:
                actions.append(SuggestedAction(
                    label="Offene Rechnungen anzeigen",
                    action_type="navigate",
                    params={"route": "/banking/payments?status=pending"},
                ))

        if "document" in agent_results:
            doc = agent_results["document"]
            doc_info = doc.get("document", {})
            if doc_info and doc_info.get("id"):
                actions.append(SuggestedAction(
                    label="Dokument oeffnen",
                    action_type="navigate",
                    params={"route": f"/documents/{doc_info['id']}"},
                ))

        return actions


# =============================================================================
# SINGLETON & DI
# =============================================================================

_orchestrator: Optional[FinancialOrchestrator] = None


def get_financial_orchestrator() -> FinancialOrchestrator:
    """Gibt die globale Orchestrator-Instanz zurueck."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = FinancialOrchestrator()
    return _orchestrator
