# -*- coding: utf-8 -*-
"""API Endpoints für den Conversational Assistant.

Enterprise Feature: Intelligenter Chat-Assistent mit Ollama Integration.

Endpoints:
- POST /chat - Chat-Nachricht senden
- GET /history - Chat-Verlauf abrufen
- POST /feedback - Feedback zu Antwort geben
- GET /health - Service-Status prüfen
- GET /sessions - Aktive Sessions auflisten
- DELETE /sessions/{session_id} - Session löschen

Feinpoliert und durchdacht - Deutsche Präzision.
"""

from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.db.models import User
from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIFeedbackType,
)
from app.services.ai.conversational_assistant import (
    get_conversational_assistant_service,
    ConversationalAssistantService,
    ChatContext,
    ChatResponse as ServiceChatResponse,
    AssistantIntent,
)

router = APIRouter(prefix="/assistant", tags=["Conversational Assistant"])


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ContextData(BaseModel):
    """Kontext-Daten für Chat-Nachricht."""

    document_id: Optional[UUID] = Field(
        default=None,
        description="Aktuell ausgewaehltes Dokument"
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Aktuelle Seite im Dokument"
    )
    selected_text: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Vom Benutzer markierter Text"
    )
    current_view: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Aktuelle Ansicht/Seite im Frontend"
    )
    additional_data: Optional[JSONDict] = Field(
        default=None,
        description="Zusätzliche Kontext-Daten"
    )


class ChatRequest(BaseModel):
    """Anfrage für Chat-Nachricht."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Chat-Nachricht des Benutzers"
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Session-ID für Konversations-Kontext (wird generiert wenn leer)"
    )
    context: Optional[ContextData] = Field(
        default=None,
        description="Optionaler Kontext (Dokument, Seite, etc.)"
    )

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validiert und bereinigt die Nachricht."""
        v = v.strip()
        if not v:
            raise ValueError("Nachricht darf nicht leer sein")
        return v


class DocumentReferenceResponse(BaseModel):
    """Dokument-Referenz in der Antwort."""

    id: UUID
    filename: str
    document_type: Optional[str] = None
    similarity: float = Field(ge=0.0, le=1.0)
    snippet: Optional[str] = None


class SuggestedActionResponse(BaseModel):
    """Vorgeschlagene Aktion in der Antwort."""

    action_type: str
    description: str
    parameters: JSONDict = Field(default_factory=dict)
    requires_confirmation: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    """Antwort des Assistenten."""

    response: str = Field(description="Antwort-Text des Assistenten")
    intent: str = Field(description="Erkannter Intent (nlq, document_search, action_request, general)")
    sources: List[DocumentReferenceResponse] = Field(
        default_factory=list,
        description="Referenzierte Dokumente"
    )
    actions: List[SuggestedActionResponse] = Field(
        default_factory=list,
        description="Vorgeschlagene Aktionen"
    )
    session_id: str = Field(description="Session-ID für Folgeanfragen")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Konfidenz der Antwort"
    )
    processing_time_ms: int = Field(
        ge=0,
        description="Verarbeitungszeit in Millisekunden"
    )
    model_used: Optional[str] = Field(
        default=None,
        description="Verwendetes LLM-Modell"
    )
    tokens_used: Optional[int] = Field(
        default=None,
        description="Anzahl verwendeter Tokens"
    )
    follow_up_suggestions: List[str] = Field(
        default_factory=list,
        description="Vorschläge für Folgefragen"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Fehlermeldung (nur bei Fehlern)"
    )


class MessageResponse(BaseModel):
    """Einzelne Nachricht im Chat-Verlauf."""

    id: UUID
    role: str
    content: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    search_results_count: Optional[int] = None
    actions_proposed: Optional[int] = None
    processing_time_ms: Optional[int] = None
    model_used: Optional[str] = None
    referenced_documents: Optional[List[str]] = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    """Chat-Verlauf einer Session."""

    session_id: str
    messages: List[MessageResponse]
    total_count: int


class FeedbackRequest(BaseModel):
    """Anfrage für Feedback zu einer Antwort."""

    message_id: UUID = Field(description="ID der Assistenten-Nachricht")
    feedback_type: str = Field(
        description="Feedback-Typ: helpful, not_helpful, incorrect, confusing, other"
    )
    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Sternebewertung 1-5"
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optionaler Kommentar"
    )
    correction: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Korrigierte Antwort (bei 'incorrect')"
    )

    @field_validator('feedback_type')
    @classmethod
    def validate_feedback_type(cls, v: str) -> str:
        """Validiert den Feedback-Typ."""
        valid_types = ["helpful", "not_helpful", "incorrect", "confusing", "other"]
        v = v.lower()
        if v not in valid_types:
            raise ValueError(f"Ungültiger Feedback-Typ. Erlaubt: {', '.join(valid_types)}")
        return v


class FeedbackResponse(BaseModel):
    """Antwort auf Feedback-Submission."""

    success: bool
    message: str


class HealthResponse(BaseModel):
    """Service-Health-Status."""

    available: bool
    ollama_connected: bool
    models: List[str] = Field(default_factory=list)
    message: str


class SessionSummary(BaseModel):
    """Zusammenfassung einer Chat-Session."""

    id: UUID
    session_id: str
    title: Optional[str] = None
    message_count: int
    action_count: int
    is_starred: bool
    is_active: bool
    created_at: str
    last_message_at: Optional[str] = None


class SessionsListResponse(BaseModel):
    """Liste der Chat-Sessions."""

    sessions: List[SessionSummary]
    total_count: int


# =============================================================================
# DEPENDENCIES
# =============================================================================


async def get_service() -> ConversationalAssistantService:
    """Dependency für ConversationalAssistantService."""
    return get_conversational_assistant_service()


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service-Verfügbarkeit prüfen",
    description="Prüft ob der Conversational Assistant und Ollama verfügbar sind.",
)
async def check_health(
    service: ConversationalAssistantService = Depends(get_service),
) -> HealthResponse:
    """Prüft den Service-Status."""
    available = await service.is_available()

    if available:
        models = await service._ollama.list_models()
        return HealthResponse(
            available=True,
            ollama_connected=True,
            models=models,
            message="Der Assistent ist bereit.",
        )
    else:
        return HealthResponse(
            available=False,
            ollama_connected=False,
            models=[],
            message="Ollama ist nicht verfügbar. Bitte stellen Sie sicher, dass Ollama laeuft.",
        )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat-Nachricht senden",
    description="""
Sendet eine Nachricht an den Assistenten und erhaelt eine Antwort.

Der Assistent kann:
- Fragen zu Dokumenten beantworten (RAG-basiert)
- Daten abfragen (Natural Language Query)
- Aktionen vorschlagen (Genehmigung, Export, etc.)
- Allgemeine Fragen beantworten

**Session-Management:**
- Ohne session_id wird eine neue Session erstellt
- Mit session_id wird die bestehende Konversation fortgesetzt
""",
    responses={
        200: {"description": "Erfolgreiche Antwort"},
        503: {"description": "Ollama nicht verfügbar"},
    },
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    db: AsyncSession = Depends(get_db),
    service: ConversationalAssistantService = Depends(get_service),
) -> ChatResponse:
    """Verarbeitet eine Chat-Nachricht."""
    # Service-Verfügbarkeit prüfen
    if not await service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Der Assistent ist derzeit nicht verfügbar. Ollama laeuft nicht.",
        )

    # Kontext erstellen
    context = None
    if request.context:
        context = ChatContext(
            document_id=request.context.document_id,
            page_number=request.context.page_number,
            selected_text=request.context.selected_text,
            current_view=request.context.current_view,
            additional_data=request.context.additional_data or {},
        )

    # Nachricht verarbeiten
    response = await service.process_message(
        db=db,
        message=request.message,
        user=current_user,
        company_id=company_id,
        session_id=request.session_id,
        context=context,
    )

    # Response konvertieren
    return ChatResponse(
        response=response.response,
        intent=response.intent.value,
        sources=[
            DocumentReferenceResponse(
                id=s.id,
                filename=s.filename,
                document_type=s.document_type,
                similarity=s.similarity,
                snippet=s.snippet,
            )
            for s in response.sources
        ],
        actions=[
            SuggestedActionResponse(
                action_type=a.action_type,
                description=a.description,
                parameters=a.parameters,
                requires_confirmation=a.requires_confirmation,
                confidence=a.confidence,
            )
            for a in response.actions
        ],
        session_id=response.session_id,
        confidence=response.confidence,
        processing_time_ms=response.processing_time_ms,
        model_used=response.model_used,
        tokens_used=response.tokens_used,
        follow_up_suggestions=response.follow_up_suggestions,
        error_message=response.error_message,
    )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Chat-Verlauf abrufen",
    description="Ruft den Chat-Verlauf für eine bestimmte Session ab.",
)
async def get_chat_history(
    session_id: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ConversationalAssistantService = Depends(get_service),
) -> ChatHistoryResponse:
    """Ruft den Chat-Verlauf ab."""
    messages = await service.get_chat_history(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
        limit=limit,
    )

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                id=msg["id"],
                role=msg["role"],
                content=msg["content"],
                intent=msg.get("intent"),
                confidence=msg.get("confidence"),
                search_results_count=msg.get("search_results_count"),
                actions_proposed=msg.get("actions_proposed"),
                processing_time_ms=msg.get("processing_time_ms"),
                model_used=msg.get("model_used"),
                referenced_documents=msg.get("referenced_documents"),
                created_at=msg["created_at"],
            )
            for msg in messages
        ],
        total_count=len(messages),
    )


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Feedback zu Antwort geben",
    description="""
Ermöglicht es dem Benutzer, Feedback zu einer Assistenten-Antwort zu geben.

**Feedback-Typen:**
- `helpful` - Antwort war hilfreich
- `not_helpful` - Antwort war nicht hilfreich
- `incorrect` - Antwort war falsch (mit optionaler Korrektur)
- `confusing` - Antwort war verwirrend
- `other` - Sonstiges Feedback

Das Feedback wird für die kontinuierliche Verbesserung des Assistenten genutzt.
""",
)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ConversationalAssistantService = Depends(get_service),
) -> FeedbackResponse:
    """Speichert Feedback zu einer Antwort."""
    success = await service.submit_feedback(
        db=db,
        message_id=request.message_id,
        user_id=current_user.id,
        feedback_type=request.feedback_type,
        rating=request.rating,
        comment=request.comment,
        correction=request.correction,
    )

    if success:
        return FeedbackResponse(
            success=True,
            message="Vielen Dank für Ihr Feedback!",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback konnte nicht gespeichert werden.",
        )


@router.get(
    "/sessions",
    response_model=SessionsListResponse,
    summary="Chat-Sessions auflisten",
    description="Listet alle Chat-Sessions des aktuellen Benutzers auf.",
)
async def list_sessions(
    page: int = Query(default=1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Eintraege pro Seite"),
    active_only: bool = Query(default=True, description="Nur aktive Sessions"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    db: AsyncSession = Depends(get_db),
) -> SessionsListResponse:
    """Listet Chat-Sessions auf."""
    # Query aufbauen
    stmt = (
        select(AIConversation)
        .where(
            and_(
                AIConversation.user_id == current_user.id,
                AIConversation.company_id == company_id,
            )
        )
    )

    if active_only:
        stmt = stmt.where(AIConversation.is_active == True)

    # Count
    from sqlalchemy import func as sql_func
    count_stmt = select(sql_func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # Daten holen
    stmt = (
        stmt
        .order_by(desc(AIConversation.last_message_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return SessionsListResponse(
        sessions=[
            SessionSummary(
                id=s.id,
                session_id=s.session_id,
                title=s.title,
                message_count=s.message_count,
                action_count=s.action_count,
                is_starred=s.is_starred,
                is_active=s.is_active,
                created_at=s.created_at.isoformat() if s.created_at else "",
                last_message_at=s.last_message_at.isoformat() if s.last_message_at else None,
            )
            for s in sessions
        ],
        total_count=total_count,
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Chat-Session archivieren",
    description="Markiert eine Chat-Session als archiviert (soft delete).",
    responses={
        200: {"description": "Session archiviert"},
        404: {"description": "Session nicht gefunden"},
    },
)
async def archive_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Archiviert eine Chat-Session."""
    stmt = select(AIConversation).where(
        and_(
            AIConversation.session_id == session_id,
            AIConversation.user_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden.",
        )

    conversation.is_active = False
    await db.commit()

    return {"message": "Session wurde archiviert."}


@router.patch(
    "/sessions/{session_id}/star",
    summary="Session markieren/entmarkieren",
    description="Markiert oder entmarkiert eine Chat-Session als Favorit.",
)
async def toggle_star(
    session_id: str,
    starred: bool = Query(..., description="True zum Markieren, False zum Entmarkieren"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Markiert/entmarkiert eine Session."""
    stmt = select(AIConversation).where(
        and_(
            AIConversation.session_id == session_id,
            AIConversation.user_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden.",
        )

    conversation.is_starred = starred
    await db.commit()

    return {
        "session_id": session_id,
        "is_starred": starred,
        "message": "Markiert" if starred else "Markierung entfernt",
    }


@router.patch(
    "/sessions/{session_id}/title",
    summary="Session-Titel ändern",
    description="Ändert den Titel einer Chat-Session.",
)
async def update_title(
    session_id: str,
    title: str = Query(..., min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Ändert den Session-Titel."""
    stmt = select(AIConversation).where(
        and_(
            AIConversation.session_id == session_id,
            AIConversation.user_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden.",
        )

    conversation.title = title
    await db.commit()

    return {
        "session_id": session_id,
        "title": title,
        "message": "Titel aktualisiert",
    }
