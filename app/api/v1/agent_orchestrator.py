# -*- coding: utf-8 -*-
"""
Multi-Agent Orchestrator API mit Chain of Thought.

Enterprise Feature: REST-API fuer den KI-Hauptagenten.
User kommuniziert NUR mit diesem Endpunkt. Der Orchestrator
koordiniert Sub-Agents und liefert sichtbare Denkschritte (CoT).

Endpoints:
- POST /agent/query - Hauptanfrage mit CoT-Response
- POST /agent/query/stream - Streaming-Antwort mit Live-CoT
- GET /agent/agents - Verfuegbare Sub-Agents auflisten
- GET /agent/conversations/{id} - Konversation abrufen
- POST /agent/quick-ask - Schnellanfrage (kontextbezogen)
- GET /agent/status - Orchestrator-Status

Feinpoliert und durchdacht - Der proaktive CFO-Assistent.
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.ai.financial_orchestrator import (
    FinancialOrchestrator,
    OrchestratorResponse,
    SubAgentType,
    ThinkingStepStatus,
    get_financial_orchestrator,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["KI-Agent"])


# =============================================================================
# PROMETHEUS METRIKEN
# =============================================================================

_QUERY_TOTAL = Counter(
    "agent_orchestrator_query_total",
    "Gesamtanzahl der Agent-Anfragen",
    ["company_id", "status"],
)

_QUERY_DURATION = Histogram(
    "agent_orchestrator_query_duration_seconds",
    "Antwortzeit der Agent-Anfragen",
    ["company_id"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

_SUBAGENT_USAGE = Counter(
    "agent_orchestrator_subagent_usage_total",
    "Nutzung einzelner Sub-Agents",
    ["agent_type"],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class AgentQueryRequest(BaseModel):
    """Anfrage an den KI-Agenten."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Natuerlichsprachige Anfrage (Deutsch)",
    )
    context: Dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Zusaetzlicher Kontext, z.B. {'document_id': '...', "
            "'page': 'banking'}"
        ),
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Konversations-ID fuer Follow-up Fragen",
    )


class QuickAskRequest(BaseModel):
    """Schnellanfrage mit minimalem Kontext."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Kurze Frage",
    )
    document_id: Optional[str] = Field(
        None,
        description="Optional: Aktuelles Dokument",
    )
    page_context: Optional[str] = Field(
        None,
        description="Optional: Aktuelle Seite (z.B. 'banking', 'documents')",
    )


class ThinkingStepResponse(BaseModel):
    """Ein Denkschritt in der Chain of Thought."""

    id: str
    agent_type: str
    agent_name: str
    description: str
    status: str
    details: List[str] = Field(default_factory=list)
    result_summary: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class SuggestedActionResponse(BaseModel):
    """Eine vorgeschlagene Aktion."""

    label: str
    action_type: str
    params: Dict[str, object] = Field(default_factory=dict)
    variant: str = "default"


class AgentQueryResponse(BaseModel):
    """Antwort des KI-Agenten mit Chain of Thought."""

    answer: str = Field(..., description="Finale Antwort auf Deutsch")
    thinking_steps: List[ThinkingStepResponse] = Field(
        default_factory=list,
        description="Sichtbare Denkschritte (collapsible in der UI)",
    )
    suggested_actions: List[SuggestedActionResponse] = Field(
        default_factory=list,
        description="Vorgeschlagene Aktionen (Buttons in der UI)",
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Konversations-ID fuer Follow-ups",
    )
    total_duration_ms: float = Field(
        0.0,
        description="Gesamtdauer in Millisekunden",
    )
    model_used: Optional[str] = Field(
        None,
        description="Verwendetes LLM-Modell",
    )


class SubAgentInfo(BaseModel):
    """Information ueber einen verfuegbaren Sub-Agent."""

    agent_type: str
    display_name: str
    description: str
    capabilities: List[str]


class OrchestratorStatusResponse(BaseModel):
    """Status des Orchestrators."""

    status: str
    registered_agents: int
    agents: List[SubAgentInfo]
    llm_available: bool
    default_provider: str


# =============================================================================
# HELPER
# =============================================================================


def _to_response(result: OrchestratorResponse) -> AgentQueryResponse:
    """Konvertiert OrchestratorResponse zu API-Response."""
    steps = [
        ThinkingStepResponse(
            id=s.id,
            agent_type=s.agent_type.value,
            agent_name=s.agent_name,
            description=s.description,
            status=s.status.value,
            details=s.details,
            result_summary=s.result_summary,
            started_at=s.started_at.isoformat() if s.started_at else None,
            completed_at=s.completed_at.isoformat() if s.completed_at else None,
            duration_ms=s.duration_ms,
            error=s.error,
        )
        for s in result.thinking_steps
    ]

    actions = [
        SuggestedActionResponse(
            label=a.label,
            action_type=a.action_type,
            params=a.params,
            variant=a.variant,
        )
        for a in result.suggested_actions
    ]

    return AgentQueryResponse(
        answer=result.answer,
        thinking_steps=steps,
        suggested_actions=actions,
        conversation_id=result.conversation_id,
        total_duration_ms=result.total_duration_ms,
        model_used=result.model_used,
    )


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post(
    "/query",
    response_model=AgentQueryResponse,
    summary="KI-Agent Anfrage",
    description=(
        "Hauptendpunkt fuer alle KI-Anfragen. Der Orchestrator analysiert "
        "die Frage, waehlt relevante Sub-Agents, fuehrt sie aus und "
        "synthetisiert eine Antwort. Liefert Chain of Thought."
    ),
)
async def agent_query(
    request: AgentQueryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQueryResponse:
    """
    Verarbeitet eine natuerlichsprachige Anfrage.

    Der Orchestrator:
    1. Analysiert den Intent
    2. Waehlt relevante Sub-Agents (Dokument, Finanz, Compliance, Matching, Anomalie)
    3. Fuehrt sie aus
    4. Synthetisiert finale Antwort mit LLM
    5. Liefert suggested Actions

    Returns:
        AgentQueryResponse mit Antwort, Denkschritten und Aktionen
    """
    import time

    start = time.perf_counter()

    logger.info(
        "agent_query_start",
        user_id=str(current_user.id),
        company_id=str(current_user.company_id),
        query_length=len(request.query),
        has_context=bool(request.context),
        has_conversation=bool(request.conversation_id),
    )

    try:
        orchestrator = get_financial_orchestrator()
        result = await orchestrator.process(
            query=request.query,
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            context=request.context,
            conversation_id=request.conversation_id,
        )

        # Metriken
        duration = time.perf_counter() - start
        _QUERY_TOTAL.labels(
            company_id=str(current_user.company_id),
            status="success",
        ).inc()
        _QUERY_DURATION.labels(
            company_id=str(current_user.company_id),
        ).observe(duration)

        for step in result.thinking_steps:
            if step.status == ThinkingStepStatus.COMPLETED:
                _SUBAGENT_USAGE.labels(agent_type=step.agent_type.value).inc()

        return _to_response(result)

    except Exception as exc:
        _QUERY_TOTAL.labels(
            company_id=str(current_user.company_id),
            status="error",
        ).inc()
        logger.error(
            "agent_query_failed",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KI-Agent konnte die Anfrage nicht verarbeiten.",
        ) from exc


@router.post(
    "/quick-ask",
    response_model=AgentQueryResponse,
    summary="Schnellanfrage",
    description=(
        "Vereinfachter Endpunkt fuer kontextbezogene Schnellfragen. "
        "Ideal fuer den Quick-Ask Button in der UI."
    ),
)
async def quick_ask(
    request: QuickAskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentQueryResponse:
    """
    Schnellanfrage mit minimalem Kontext.

    Baut automatisch den Kontext aus document_id und page_context.
    """
    context: Dict[str, object] = {}
    if request.document_id:
        context["document_id"] = request.document_id
    if request.page_context:
        context["page"] = request.page_context

    try:
        orchestrator = get_financial_orchestrator()
        result = await orchestrator.process(
            query=request.query,
            db=db,
            company_id=current_user.company_id,
            user_id=current_user.id,
            context=context,
        )
        return _to_response(result)

    except Exception as exc:
        logger.error(
            "quick_ask_failed",
            user_id=str(current_user.id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Schnellanfrage konnte nicht verarbeitet werden.",
        ) from exc


@router.get(
    "/agents",
    response_model=List[SubAgentInfo],
    summary="Verfuegbare Sub-Agents",
    description="Listet alle registrierten Sub-Agents mit ihren Faehigkeiten.",
)
async def list_agents(
    current_user: Annotated[User, Depends(get_current_user)],
) -> List[SubAgentInfo]:
    """Listet alle verfuegbaren Sub-Agents."""
    agent_descriptions = {
        SubAgentType.DOCUMENT: {
            "description": "Analysiert Dokumente, extrahiert Felder und Metadaten",
            "capabilities": [
                "Feld-Extraktion",
                "Klassifikation",
                "Zusammenfassung",
                "Dokumentsuche",
            ],
        },
        SubAgentType.FINANCE: {
            "description": "Finanzanalyse, Cashflow, Skonto, Budget-Kontrolle",
            "capabilities": [
                "Offene Posten",
                "Cashflow-Prognose",
                "Skonto-Analyse",
                "Budget-Status",
                "Zahlungsverhalten",
            ],
        },
        SubAgentType.COMPLIANCE: {
            "description": "Compliance-Pruefungen: XRechnung, GoBD, DSGVO",
            "capabilities": [
                "XRechnung-Validierung",
                "GoBD-Konformitaet",
                "DSGVO-Pruefung",
                "Aufbewahrungsfristen",
                "Archiv-Compliance",
            ],
        },
        SubAgentType.MATCHING: {
            "description": "3-Way Matching, Entity-Zuordnung, Duplikat-Erkennung",
            "capabilities": [
                "Bestellung-Lieferschein-Rechnung",
                "Lieferanten-Zuordnung",
                "Duplikat-Erkennung",
                "Referenz-Matching",
            ],
        },
        SubAgentType.ANOMALY: {
            "description": "Anomalie-Erkennung, Betragsmuster, saisonale Abweichungen",
            "capabilities": [
                "Betrugs-Erkennung",
                "Betrags-Ausreisser",
                "Saisonale Anomalien",
                "Muster-Analyse",
            ],
        },
    }

    orchestrator = get_financial_orchestrator()
    agents = orchestrator._agent_registry.all_agents()

    return [
        SubAgentInfo(
            agent_type=a.agent_type.value,
            display_name=a.display_name,
            description=agent_descriptions.get(
                a.agent_type, {}
            ).get("description", "Spezialisierter Sub-Agent"),
            capabilities=agent_descriptions.get(
                a.agent_type, {}
            ).get("capabilities", []),
        )
        for a in agents
    ]


@router.get(
    "/status",
    response_model=OrchestratorStatusResponse,
    summary="Orchestrator-Status",
    description="Prueft den Status des KI-Orchestrators und seiner Komponenten.",
)
async def get_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> OrchestratorStatusResponse:
    """Gibt den aktuellen Status des Orchestrators zurueck."""
    from app.core.llm_provider import get_llm_registry

    orchestrator = get_financial_orchestrator()
    registry = get_llm_registry()

    agents = orchestrator._agent_registry.all_agents()
    agent_descriptions = {
        SubAgentType.DOCUMENT: "Dokument-Analyse",
        SubAgentType.FINANCE: "Finanz-Analyse",
        SubAgentType.COMPLIANCE: "Compliance-Pruefung",
        SubAgentType.MATCHING: "3-Way Matching",
        SubAgentType.ANOMALY: "Anomalie-Erkennung",
    }

    # LLM-Verfuegbarkeit pruefen
    llm_available = False
    default_provider = "nicht konfiguriert"
    try:
        default = registry.default
        default_provider = default.name
        llm_available = await default.is_available()
    except Exception:
        pass

    return OrchestratorStatusResponse(
        status="operational" if llm_available else "degraded",
        registered_agents=len(agents),
        agents=[
            SubAgentInfo(
                agent_type=a.agent_type.value,
                display_name=a.display_name,
                description=agent_descriptions.get(
                    a.agent_type, "Sub-Agent"
                ),
                capabilities=[],
            )
            for a in agents
        ],
        llm_available=llm_available,
        default_provider=default_provider,
    )
