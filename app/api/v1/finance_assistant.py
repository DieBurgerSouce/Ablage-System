# -*- coding: utf-8 -*-
"""API Endpoints fuer den intelligenten Finanz-Assistenten.

Vision 2.0 - Phase 1 (Januar 2026)

Endpoints:
- Chat mit KI-Assistent
- Aktionen ausfuehren
- Proaktive Insights abrufen
- Buchungsvorschlaege
"""

from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.ai.finance_assistant_service import (
    FinanceAssistantService,
    AssistantContext,
    AssistantIntent,
    ActionProposal,
    get_finance_assistant_service,
)
from app.services.ai.action_executor_service import (
    ActionExecutorService,
    ActionContext,
    get_action_executor_service,
)
from app.services.ai.insight_generator_service import (
    InsightGeneratorService,
    InsightContext,
    get_insight_generator_service,
)

router = APIRouter(prefix="/finance-assistant", tags=["Finance Assistant"])


# ===== Pydantic Schemas =====


class ChatRequest(BaseModel):
    """Anfrage fuer Chat mit dem Assistenten."""

    message: str = Field(..., min_length=1, max_length=5000)
    current_page: Optional[str] = None
    selected_documents: List[UUID] = Field(default_factory=list)
    session_id: Optional[str] = None


class ActionData(BaseModel):
    """Daten einer vorgeschlagenen Aktion."""

    action_type: str
    description: str
    parameters: dict[str, Any]
    confidence: float
    requires_confirmation: bool
    affected_count: int


class BookingSuggestionData(BaseModel):
    """Buchungsvorschlag."""

    debit_account: str
    debit_account_name: str
    credit_account: str
    credit_account_name: str
    amount: float
    description: str
    tax_code: Optional[str] = None
    confidence: float
    reasoning: str


class InsightData(BaseModel):
    """Ein Insight."""

    title: str
    content: str
    category: str
    severity: str
    related_documents: List[UUID] = Field(default_factory=list)
    data: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Antwort des Assistenten."""

    message: str
    intent: str
    success: bool
    confidence: float
    actions: List[ActionData] = Field(default_factory=list)
    booking_suggestions: List[BookingSuggestionData] = Field(default_factory=list)
    insights: List[InsightData] = Field(default_factory=list)
    search_results: Optional[List[dict[str, Any]]] = None
    result_count: int = 0
    processing_time_ms: int = 0
    follow_up_suggestions: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class ExecuteActionRequest(BaseModel):
    """Anfrage zur Aktionsausfuehrung."""

    action_type: str = Field(..., pattern="^[a-z_]+$")
    parameters: dict[str, Any]


class ExecuteActionResponse(BaseModel):
    """Antwort der Aktionsausfuehrung."""

    action_id: UUID
    status: str
    success: bool
    message: str
    affected_count: int = 0
    rollback_possible: bool = False
    execution_time_ms: int = 0
    error_details: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(BaseModel):
    """Anfrage zum Rollback."""

    action_id: UUID


class InsightResponse(BaseModel):
    """Ein generiertes Insight."""

    id: UUID
    category: str
    severity: str
    title: str
    summary: str
    details: str
    recommendations: List[str] = Field(default_factory=list)
    affected_entities: List[UUID] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    action_url: Optional[str] = None


class InsightsListResponse(BaseModel):
    """Liste von Insights."""

    insights: List[InsightResponse]
    count: int
    generated_at: str


# ===== Endpoints =====


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Chat mit dem intelligenten Finanz-Assistenten.

    Unterstuetzte Intents:
    - search: Dokumente/Daten suchen
    - execute_action: Aktionen ausfuehren
    - explain: Erklaerungen generieren
    - suggest_booking: Buchungsvorschlaege
    - analyze: Analysen durchfuehren
    - predict: Vorhersagen treffen
    - help: Hilfe anzeigen
    - chat: Allgemeiner Chat
    """
    service = await get_finance_assistant_service(db)

    context = AssistantContext(
        user_id=current_user.id,
        company_id=current_user.company_id,
        user_role=current_user.role or "viewer",
        current_page=request.current_page,
        selected_documents=request.selected_documents,
        session_id=request.session_id or "",
    )

    response = await service.process_message(
        message=request.message,
        context=context,
    )

    return ChatResponse(
        message=response.message,
        intent=response.intent.value,
        success=response.success,
        confidence=response.confidence,
        actions=[
            ActionData(
                action_type=a.action_type.value,
                description=a.description,
                parameters=a.parameters,
                confidence=a.confidence,
                requires_confirmation=a.requires_confirmation,
                affected_count=a.affected_count,
            )
            for a in response.actions
        ],
        booking_suggestions=[
            BookingSuggestionData(
                debit_account=b.debit_account,
                debit_account_name=b.debit_account_name,
                credit_account=b.credit_account,
                credit_account_name=b.credit_account_name,
                amount=float(b.amount),
                description=b.description,
                tax_code=b.tax_code,
                confidence=b.confidence,
                reasoning=b.reasoning,
            )
            for b in response.booking_suggestions
        ],
        insights=[
            InsightData(
                title=i.title,
                content=i.content,
                category=i.category,
                severity=i.severity,
                related_documents=i.related_documents,
                data=i.data,
            )
            for i in response.insights
        ],
        search_results=response.search_results,
        result_count=response.result_count,
        processing_time_ms=response.processing_time_ms,
        follow_up_suggestions=response.follow_up_suggestions,
        error_message=response.error_message,
    )


@router.post("/execute", response_model=ExecuteActionResponse)
async def execute_action(
    request: ExecuteActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecuteActionResponse:
    """Fuehrt eine vom Assistenten vorgeschlagene Aktion aus.

    Erfordert mindestens Editor-Rolle fuer die meisten Aktionen.
    Admin-Rolle fuer Zahlungslaeufe und Loeschungen.
    """
    service = await get_action_executor_service(db)

    context = ActionContext(
        user_id=current_user.id,
        company_id=current_user.company_id,
        user_role=current_user.role or "viewer",
        session_id="",
    )

    result = await service.execute_action(
        action_type=request.action_type,
        parameters=request.parameters,
        context=context,
    )

    return ExecuteActionResponse(
        action_id=result.action_id,
        status=result.status.value,
        success=result.success,
        message=result.message,
        affected_count=result.affected_count,
        rollback_possible=result.rollback_possible,
        execution_time_ms=result.execution_time_ms,
        error_details=result.error_details,
        metadata=result.metadata,
    )


@router.post("/rollback", response_model=ExecuteActionResponse)
async def rollback_action(
    request: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecuteActionResponse:
    """Macht eine ausgefuehrte Aktion rueckgaengig.

    Nur moeglich fuer Aktionen mit rollback_possible=True.
    """
    service = await get_action_executor_service(db)

    context = ActionContext(
        user_id=current_user.id,
        company_id=current_user.company_id,
        user_role=current_user.role or "viewer",
        session_id="",
    )

    result = await service.rollback_action(
        action_id=request.action_id,
        context=context,
    )

    return ExecuteActionResponse(
        action_id=result.action_id,
        status=result.status.value,
        success=result.success,
        message=result.message,
        affected_count=result.affected_count,
        rollback_possible=False,
        execution_time_ms=result.execution_time_ms,
        error_details=result.error_details,
        metadata=result.metadata,
    )


@router.get("/insights", response_model=InsightsListResponse)
async def get_insights(
    include_predictions: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InsightsListResponse:
    """Ruft proaktive Insights ab.

    Generiert Insights basierend auf:
    - Ueberfaellige Posten
    - Cash-Flow-Analyse
    - Skonto-Chancen
    - Anomalien
    - Trends
    - Risiken
    """
    from app.core.datetime_utils import utc_now

    service = await get_insight_generator_service(db)

    context = InsightContext(
        company_id=current_user.company_id,
        user_id=current_user.id,
        include_predictions=include_predictions,
    )

    insights = await service.generate_all_insights(context)

    return InsightsListResponse(
        insights=[
            InsightResponse(
                id=i.id,
                category=i.category.value,
                severity=i.severity.value,
                title=i.title,
                summary=i.summary,
                details=i.details,
                recommendations=i.recommendations,
                affected_entities=i.affected_entities,
                metrics=i.metrics,
                action_url=i.action_url,
            )
            for i in insights
        ],
        count=len(insights),
        generated_at=utc_now().isoformat(),
    )


@router.get("/help")
async def get_assistant_help(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Gibt Hilfe-Informationen zum Assistenten zurueck."""
    return {
        "version": "2.0",
        "capabilities": [
            {
                "name": "Suchen",
                "description": "Dokumente und Daten mit natuerlicher Sprache suchen",
                "examples": [
                    "Zeige alle Rechnungen von Mueller GmbH",
                    "Welche Rechnungen sind ueberfaellig?",
                    "Finde Dokumente mit Stichwort 'Wartung'",
                ],
            },
            {
                "name": "Aktionen",
                "description": "Geschaeftsprozesse ausfuehren",
                "examples": [
                    "Erstelle Zahlungslauf fuer faellige Rechnungen unter 5000 EUR",
                    "Starte Mahnlauf",
                    "Exportiere Daten als DATEV",
                ],
            },
            {
                "name": "Analysen",
                "description": "Geschaeftsdaten analysieren",
                "examples": [
                    "Analysiere den Cash Flow",
                    "Warum ist der Umsatz gesunken?",
                    "Zeige Anomalien",
                ],
            },
            {
                "name": "Buchungsvorschlaege",
                "description": "Kontierung nach SKR03/04",
                "examples": [
                    "Wie buche ich einen Wareneingang ueber 500 EUR?",
                    "Buchungsvorschlag fuer Werbekosten",
                ],
            },
            {
                "name": "Vorhersagen",
                "description": "Prognosen und Trends",
                "examples": [
                    "Wie entwickelt sich die Liquiditaet?",
                    "Prognose fuer naechsten Monat",
                ],
            },
        ],
        "supported_languages": ["de"],
        "requires_ollama": True,
    }
