# -*- coding: utf-8 -*-
"""
AI Conversations API Endpoints.

Vision 2.0 - Phase 1: Conversation Persistence

Endpoints für den KI-Finanzassistenten:

Konversationen:
- GET  /ai/conversations                    - Konversationen auflisten (paginiert)
- POST /ai/conversations                    - Neue Konversation starten
- GET  /ai/conversations/session/{id}       - Konversation per Session-ID abrufen
- GET  /ai/conversations/{id}               - Konversation abrufen
- PATCH /ai/conversations/{id}              - Konversation aktualisieren
- DELETE /ai/conversations/{id}             - Konversation löschen

Nachrichten:
- GET  /ai/conversations/{id}/messages      - Nachrichten abrufen
- POST /ai/conversations/{id}/messages      - Nachricht senden

Feedback:
- POST /ai/conversations/messages/{id}/feedback  - Feedback zu Nachricht (primär)
- POST /ai/conversations/{id}/feedback           - Feedback (legacy)

Aktionen:
- GET  /ai/conversations/{id}/actions            - Aktionen abrufen
- POST /ai/conversations/{id}/actions/{id}/confirm - Aktion bestätigen
- POST /ai/conversations/{id}/actions/{id}/cancel  - Aktion abbrechen

Statistiken:
- GET /ai/conversations/stats               - Konversations-Statistiken

Feinpoliert und durchdacht - Deutsche Präzision.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, ConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func, and_, cast, Date
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.core.safe_errors import safe_error_log
from app.db.models_ai_conversation import (
    AIConversation,
    AIConversationMessage,
    AIConversationAction,
    AIConversationFeedback,
    AIMessageRole,
    AIAssistantIntent,
    AIActionStatus,
    AIFeedbackType,
)

logger = structlog.get_logger(__name__)

# Rate Limiter für AI Conversations Endpoints
limiter = Limiter(key_func=get_remote_address)

# =============================================================================
# Security: Input Validation Patterns
# =============================================================================

# Pattern für sichere Suche (keine SQL Injection)
SAFE_SEARCH_PATTERN = re.compile(r"^[a-zA-Z0-9äöüÄÖÜß\s\-_.,:;!?()]*$")
MAX_SEARCH_LENGTH = 100
MAX_TITLE_LENGTH = 255
MAX_CONTENT_LENGTH = 10000
MAX_COMMENT_LENGTH = 2000
MAX_SESSION_ID_LENGTH = 64
MAX_CONTEXT_PAGE_LENGTH = 255


def validate_search_input(search: Optional[str]) -> Optional[str]:
    """Validiere und bereinige Sucheingabe gegen SQL Injection."""
    if not search:
        return None

    # Längenbegrenzung
    if len(search) > MAX_SEARCH_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Suchbegriff zu lang (max. {MAX_SEARCH_LENGTH} Zeichen)",
        )

    # Pattern-Validierung
    if not SAFE_SEARCH_PATTERN.match(search):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Suchbegriff enthält ungültige Zeichen",
        )

    # Escape SQL Wildcards im Suchstring
    escaped = search.replace("%", r"\%").replace("_", r"\_")
    return escaped

router = APIRouter(prefix="/ai/conversations", tags=["AI Conversations"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class CreateConversationRequest(BaseModel):
    """Request zum Erstellen einer neuen Konversation."""
    context_page: Optional[str] = Field(
        None,
        max_length=MAX_CONTEXT_PAGE_LENGTH,
        description="Seite auf der gestartet wurde"
    )
    context_data: Optional[JSONDict] = Field(None, description="Zusätzlicher Kontext")
    language: str = Field("de", max_length=5, description="Sprache (de/en)")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validiere Sprachcode."""
        allowed = {"de", "en"}
        if v not in allowed:
            raise ValueError(f"Sprache muss eine von {allowed} sein")
        return v

    @field_validator("context_page")
    @classmethod
    def validate_context_page(cls, v: Optional[str]) -> Optional[str]:
        """Validiere context_page gegen Path Traversal."""
        if v and (".." in v or v.startswith("/")):
            raise ValueError("Ungültiger Seitenkontext")
        return v


class ConversationSummary(BaseModel):
    """Kurzübersicht einer Konversation."""
    id: str
    session_id: str
    title: Optional[str]
    message_count: int
    action_count: int
    is_starred: bool
    is_active: bool
    context_page: Optional[str]
    language: str = "de"
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    last_message_at: Optional[datetime]


class ConversationDetail(BaseModel):
    """Vollständige Konversation mit Nachrichten."""
    id: str
    session_id: str
    title: Optional[str]
    message_count: int
    action_count: int
    is_starred: bool
    is_active: bool
    context_page: Optional[str]
    context_data: Optional[JSONDict]
    preferences: Optional[JSONDict]
    language: str = "de"
    total_tokens: Optional[int]
    messages: List[JSONDict]
    actions: List[JSONDict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    last_message_at: Optional[datetime]


class SendMessageRequest(BaseModel):
    """Request zum Senden einer Nachricht."""
    content: str = Field(..., min_length=1, max_length=10000, description="Nachrichteninhalt")
    intent: Optional[str] = Field(None, description="Erkannte Absicht (optional)")


class MessageResponse(BaseModel):
    """Antwort mit Assistenten-Nachricht."""
    id: str
    role: str
    content: str
    intent: Optional[str]
    confidence: Optional[float]
    search_results_count: Optional[int]
    actions_proposed: Optional[int]
    processing_time_ms: Optional[int]
    referenced_documents: Optional[List[str]]
    created_at: Optional[datetime]


class FeedbackRequest(BaseModel):
    """Request für Feedback zu einer Nachricht."""
    message_id: str = Field(..., description="ID der Nachricht")
    feedback_type: str = Field(..., description="helpful, not_helpful, incorrect, confusing, other")
    rating: Optional[int] = Field(None, ge=1, le=5, description="1-5 Sterne")
    comment: Optional[str] = Field(None, max_length=2000, description="Kommentar")
    correction: Optional[str] = Field(None, max_length=10000, description="Korrigierte Antwort")
    expected_intent: Optional[str] = Field(None, description="Erwartete Absicht")


class ActionConfirmRequest(BaseModel):
    """Request zum Bestätigen einer Aktion."""
    parameters: Optional[JSONDict] = Field(None, description="Angepasste Parameter")


class UpdateConversationRequest(BaseModel):
    """Request zum Aktualisieren einer Konversation."""
    title: Optional[str] = Field(None, max_length=MAX_TITLE_LENGTH)
    is_starred: Optional[bool] = None
    is_active: Optional[bool] = None
    preferences: Optional[JSONDict] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        """Validiere Titel gegen gefährliche Zeichen."""
        if v and not SAFE_SEARCH_PATTERN.match(v):
            raise ValueError("Titel enthält ungültige Zeichen")
        return v


class ConversationListResponse(BaseModel):
    """Paginierte Liste von Konversationen."""
    conversations: List[ConversationSummary]
    total: int
    page: int
    page_size: int


class ConversationStatsResponse(BaseModel):
    """Statistiken über Konversationen."""
    total_conversations: int
    active_conversations: int
    total_messages: int
    total_actions: int
    total_feedbacks: int
    actions_by_status: Dict[str, int]
    conversations_by_day: List[JSONDict]
    top_intents: List[JSONDict]
    average_messages_per_conversation: float
    average_actions_per_conversation: float


class ConversationMessagesResponse(BaseModel):
    """Response für Nachrichten einer Konversation."""
    messages: List[MessageResponse]
    total: int


class ActionResponse(BaseModel):
    """Response für eine einzelne Aktion."""
    id: str
    action_type: str
    description: str
    status: str
    parameters: JSONDict
    result: Optional[JSONDict]
    error_message: Optional[str]
    affected_count: Optional[int]
    success_count: Optional[int]
    failure_count: Optional[int]
    requires_confirmation: bool
    confirmed_at: Optional[datetime]
    proposed_at: Optional[datetime]
    executed_at: Optional[datetime]


class ConversationActionsResponse(BaseModel):
    """Response für Aktionen einer Konversation."""
    actions: List[ActionResponse]
    total: int


class FeedbackResponse(BaseModel):
    """Response für Feedback."""
    id: str
    feedback_type: str
    rating: Optional[int]
    comment: Optional[str]
    correction: Optional[str]
    expected_intent: Optional[str]
    created_at: Optional[datetime]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=ConversationListResponse)
@limiter.limit("60/minute")
async def list_conversations(
    request: Request,
    is_starred: Optional[bool] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = Query(None, max_length=MAX_SEARCH_LENGTH),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    page_size: int = Query(50, ge=1, le=100, description="Einträge pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    """
    Liste Konversationen des aktuellen Benutzers.

    Unterstützt Filterung nach starred/active Status und Suche im Titel.
    Gibt paginierte Ergebnisse zurück.
    """
    try:
        # Validiere und bereinige Sucheingabe
        validated_search = validate_search_input(search)

        # Basis-Query
        base_conditions = [AIConversation.user_id == current_user.id]

        # Filter: is_active (Standard: nur aktive)
        if is_active is not None:
            base_conditions.append(AIConversation.is_active == is_active)
        else:
            # Default: nur aktive Konversationen
            base_conditions.append(AIConversation.is_active == True)

        # Filter: is_starred
        if is_starred is not None:
            base_conditions.append(AIConversation.is_starred == is_starred)

        # Filter: Suche im Titel (mit escaped Wildcards)
        if validated_search:
            base_conditions.append(
                AIConversation.title.ilike(f"%{validated_search}%", escape="\\")
            )

        # Count Query für Pagination
        count_query = select(func.count(AIConversation.id)).where(and_(*base_conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Daten-Query mit Pagination
        offset = (page - 1) * page_size
        query = select(AIConversation).where(and_(*base_conditions))
        query = query.order_by(AIConversation.last_message_at.desc().nullslast())
        query = query.offset(offset).limit(page_size)

        result = await db.execute(query)
        conversations = result.scalars().all()

        return ConversationListResponse(
            conversations=[
                ConversationSummary(**conv.to_summary_dict())
                for conv in conversations
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_conversations_list_db_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Konversationen",
        )


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_conversation(
    body: CreateConversationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    """Erstelle eine neue Konversation."""
    try:
        session_id = f"conv_{uuid.uuid4().hex[:16]}"

        conversation = AIConversation(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=current_user.id,
            company_id=current_user.company_id,
            context_page=body.context_page,
            context_data=body.context_data,
            language=body.language,
            is_active=True,
            is_starred=False,
            message_count=0,
            action_count=0,
        )

        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

        logger.info(
            "ai_conversation_created",
            user_id=str(current_user.id),
            conversation_id=str(conversation.id),
            session_id=session_id,
        )

        # Return ConversationDetail (Frontend erwartet diesen Typ)
        return ConversationDetail(
            id=str(conversation.id),
            session_id=conversation.session_id,
            title=conversation.title,
            message_count=conversation.message_count,
            action_count=conversation.action_count,
            is_starred=conversation.is_starred,
            is_active=conversation.is_active,
            context_page=conversation.context_page,
            context_data=conversation.context_data,
            preferences=conversation.preferences,
            language=conversation.language or "de",
            total_tokens=conversation.total_tokens,
            messages=[],
            actions=[],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_conversation_create_db_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Erstellen der Konversation",
        )


@router.get("/session/{session_id}", response_model=ConversationDetail)
@limiter.limit("60/minute")
async def get_conversation_by_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    """
    Hole Konversation anhand der Session-ID.

    Dies ermöglicht das Wiederherstellen einer Konversation über die Session-ID
    anstelle der internen UUID.
    """
    try:
        # Validiere Session-ID Länge
        if len(session_id) > MAX_SESSION_ID_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session-ID zu lang (max. {MAX_SESSION_ID_LENGTH} Zeichen)",
            )

        query = select(AIConversation).where(
            and_(
                AIConversation.session_id == session_id,
                AIConversation.user_id == current_user.id,
            )
        ).options(
            selectinload(AIConversation.messages),
            selectinload(AIConversation.actions),
        )

        result = await db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation mit dieser Session-ID nicht gefunden",
            )

        return ConversationDetail(
            id=str(conversation.id),
            session_id=conversation.session_id,
            title=conversation.title,
            message_count=conversation.message_count,
            action_count=conversation.action_count,
            is_starred=conversation.is_starred,
            is_active=conversation.is_active,
            context_page=conversation.context_page,
            context_data=conversation.context_data,
            preferences=conversation.preferences,
            language=conversation.language or "de",
            total_tokens=conversation.total_tokens,
            messages=[msg.to_dict() for msg in conversation.messages],
            actions=[action.to_dict() for action in conversation.actions],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_conversation_get_by_session_db_error",
            user_id=str(current_user.id),
            session_id=session_id[:20] + "..." if len(session_id) > 20 else session_id,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Konversation",
        )


@router.get("/{conversation_id}", response_model=ConversationDetail)
@limiter.limit("60/minute")
async def get_conversation(
    conversation_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    """Hole Konversation mit allen Nachrichten."""
    try:
        query = select(AIConversation).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        ).options(
            selectinload(AIConversation.messages),
            selectinload(AIConversation.actions),
        )

        result = await db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        return ConversationDetail(
            id=str(conversation.id),
            session_id=conversation.session_id,
            title=conversation.title,
            message_count=conversation.message_count,
            action_count=conversation.action_count,
            is_starred=conversation.is_starred,
            is_active=conversation.is_active,
            context_page=conversation.context_page,
            context_data=conversation.context_data,
            preferences=conversation.preferences,
            language=conversation.language or "de",
            total_tokens=conversation.total_tokens,
            messages=[msg.to_dict() for msg in conversation.messages],
            actions=[action.to_dict() for action in conversation.actions],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_conversation_get_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Konversation",
        )


@router.patch("/{conversation_id}", response_model=ConversationDetail)
@limiter.limit("30/minute")
async def update_conversation(
    conversation_id: UUID,
    body: UpdateConversationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    """Aktualisiere Konversation (Titel, Starred, etc.)."""
    try:
        query = select(AIConversation).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        ).options(
            selectinload(AIConversation.messages),
            selectinload(AIConversation.actions),
        )

        result = await db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        if body.title is not None:
            conversation.title = body.title
        if body.is_starred is not None:
            conversation.is_starred = body.is_starred
        if body.is_active is not None:
            conversation.is_active = body.is_active
        if body.preferences is not None:
            conversation.preferences = body.preferences

        await db.commit()
        await db.refresh(conversation)

        logger.info(
            "ai_conversation_updated",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
        )

        # Return ConversationDetail (Frontend erwartet diesen Typ)
        return ConversationDetail(
            id=str(conversation.id),
            session_id=conversation.session_id,
            title=conversation.title,
            message_count=conversation.message_count,
            action_count=conversation.action_count,
            is_starred=conversation.is_starred,
            is_active=conversation.is_active,
            context_page=conversation.context_page,
            context_data=conversation.context_data,
            preferences=conversation.preferences,
            language=conversation.language or "de",
            total_tokens=conversation.total_tokens,
            messages=[msg.to_dict() for msg in conversation.messages],
            actions=[action.to_dict() for action in conversation.actions],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_conversation_update_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Aktualisieren der Konversation",
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_conversation(
    conversation_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Lösche Konversation (Soft-Delete durch is_active=False)."""
    try:
        query = select(AIConversation).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )

        result = await db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        conversation.is_active = False
        await db.commit()

        logger.info(
            "ai_conversation_deleted",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_conversation_delete_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Löschen der Konversation",
        )


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
@limiter.limit("60/minute")
async def get_messages(
    conversation_id: UUID,
    request: Request,
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationMessagesResponse:
    """Hole Nachrichten einer Konversation."""
    try:
        # Prüfe Zugriff
        conv_query = select(AIConversation.id).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )
        conv_result = await db.execute(conv_query)
        if not conv_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        # Count total messages
        count_query = select(func.count(AIConversationMessage.id)).where(
            AIConversationMessage.conversation_id == conversation_id
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch messages
        query = select(AIConversationMessage).where(
            AIConversationMessage.conversation_id == conversation_id
        ).order_by(
            AIConversationMessage.created_at.asc()
        ).offset((page - 1) * per_page).limit(per_page)

        result = await db.execute(query)
        messages = result.scalars().all()

        return ConversationMessagesResponse(
            messages=[
                MessageResponse(
                    id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    intent=msg.intent,
                    confidence=msg.confidence,
                    search_results_count=msg.search_results_count,
                    actions_proposed=msg.actions_proposed,
                    processing_time_ms=msg.processing_time_ms,
                    referenced_documents=msg.referenced_documents,
                    created_at=msg.created_at,
                )
                for msg in messages
            ],
            total=total,
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_messages_get_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Nachrichten",
        )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
@limiter.limit("30/minute")
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Sende eine Nachricht an den KI-Assistenten.

    Die Antwort wird asynchron generiert und in der Datenbank gespeichert.
    """
    try:
        # Prüfe Zugriff und hole Konversation
        conv_query = select(AIConversation).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
                AIConversation.is_active == True,
            )
        )
        conv_result = await db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden oder inaktiv",
            )

        # Speichere User-Nachricht
        user_message = AIConversationMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=AIMessageRole.USER.value,
            content=body.content,
            intent=body.intent,
        )
        db.add(user_message)

        # Aktualisiere Konversation
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(timezone.utc)

        # Generiere automatischen Titel wenn noch keiner vorhanden
        if not conversation.title and conversation.message_count == 1:
            # Ersten 50 Zeichen der ersten Nachricht als Titel
            conversation.title = body.content[:50] + ("..." if len(body.content) > 50 else "")

        await db.commit()
        await db.refresh(user_message)

        # KI-Verarbeitung über FinanceAssistantService triggern (async Celery Task)
        # Die eigentliche Verarbeitung erfolgt asynchron, um die Response nicht zu blockieren
        from app.workers.tasks.ai_conversation_tasks import process_ai_message

        # Celery Task für asynchrone KI-Verarbeitung triggern
        try:
            process_ai_message.delay(
                conversation_id=str(conversation_id),
                message_id=str(user_message.id),
                user_id=str(current_user.id),
                company_id=str(conversation.company_id) if conversation.company_id else None,
                content=body.content,
            )
        except Exception as task_error:
            logger.warning(
                "ai_message_celery_task_failed",
                user_id=str(current_user.id),
                conversation_id=str(conversation_id),
                error_type=type(task_error).__name__,
            )
            # Fehler beim Task-Dispatch nicht fatal - Nachricht wurde trotzdem gespeichert

        logger.info(
            "ai_message_sent",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            message_id=str(user_message.id),
        )

        return MessageResponse(
            id=str(user_message.id),
            role=user_message.role,
            content=user_message.content,
            intent=user_message.intent,
            confidence=user_message.confidence,
            search_results_count=None,
            actions_proposed=None,
            processing_time_ms=None,
            referenced_documents=None,
            created_at=user_message.created_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_message_send_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Senden der Nachricht",
        )


class MessageFeedbackRequest(BaseModel):
    """Request für Message-Level Feedback (alternativer Pfad)."""
    feedback_type: str = Field(..., alias="feedbackType", description="helpful, not_helpful, incorrect, confusing, other")
    rating: Optional[int] = Field(None, ge=1, le=5, description="1-5 Sterne")
    comment: Optional[str] = Field(None, max_length=2000, description="Kommentar")
    correction: Optional[str] = Field(None, max_length=10000, description="Korrigierte Antwort")
    expected_intent: Optional[str] = Field(None, alias="expectedIntent", description="Erwartete Absicht")

    model_config = ConfigDict(populate_by_name=True)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def submit_message_feedback(
    message_id: UUID,
    body: MessageFeedbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """
    Gib Feedback zu einer spezifischen Nachricht (Message-Level-API).

    Dies ist der primäre Feedback-Endpoint, der direkt auf Message-Ebene arbeitet.
    Das Frontend nutzt diesen Pfad: /ai/conversations/messages/{messageId}/feedback
    """
    try:
        # Finde die Nachricht und prüfe Zugriff über die Konversation
        msg_query = select(AIConversationMessage).join(
            AIConversation
        ).where(
            and_(
                AIConversationMessage.id == message_id,
                AIConversation.user_id == current_user.id,
            )
        )
        msg_result = await db.execute(msg_query)
        message = msg_result.scalar_one_or_none()

        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nachricht nicht gefunden oder kein Zugriff",
            )

        # Validiere Feedback-Typ
        try:
            feedback_type = AIFeedbackType(body.feedback_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Feedback-Typ: {body.feedback_type}",
            )

        feedback = AIConversationFeedback(
            id=uuid.uuid4(),
            message_id=message_id,
            user_id=current_user.id,
            feedback_type=feedback_type.value,
            rating=body.rating,
            comment=body.comment,
            correction=body.correction,
            expected_intent=body.expected_intent,
        )

        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)

        logger.info(
            "ai_message_feedback_submitted",
            user_id=str(current_user.id),
            message_id=str(message_id),
            feedback_type=body.feedback_type,
        )

        return FeedbackResponse(
            id=str(feedback.id),
            feedback_type=feedback.feedback_type,
            rating=feedback.rating,
            comment=feedback.comment,
            correction=feedback.correction,
            expected_intent=feedback.expected_intent,
            created_at=feedback.created_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_feedback_submit_db_error",
            user_id=str(current_user.id),
            message_id=str(message_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Speichern des Feedbacks",
        )


@router.post("/{conversation_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def submit_feedback(
    conversation_id: UUID,
    body: FeedbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    """
    Gib Feedback zu einer Assistenten-Nachricht (Conversation-Level-API).

    Alternativer Endpoint der conversation_id im Pfad hat.
    DEPRECATED: Bitte /messages/{message_id}/feedback verwenden.
    """
    try:
        # Prüfe Zugriff
        conv_query = select(AIConversation.id).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )
        conv_result = await db.execute(conv_query)
        if not conv_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        # Validiere Feedback-Typ
        try:
            feedback_type = AIFeedbackType(body.feedback_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Feedback-Typ: {body.feedback_type}",
            )

        # Validiere message_id Format
        try:
            message_uuid = UUID(body.message_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültige Nachrichten-ID",
            )

        # Prüfe ob Nachricht existiert
        msg_query = select(AIConversationMessage.id).where(
            and_(
                AIConversationMessage.id == message_uuid,
                AIConversationMessage.conversation_id == conversation_id,
            )
        )
        msg_result = await db.execute(msg_query)
        if not msg_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nachricht nicht gefunden",
            )

        feedback = AIConversationFeedback(
            id=uuid.uuid4(),
            message_id=message_uuid,
            user_id=current_user.id,
            feedback_type=feedback_type.value,
            rating=body.rating,
            comment=body.comment,
            correction=body.correction,
            expected_intent=body.expected_intent,
        )

        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)

        logger.info(
            "ai_feedback_submitted",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            message_id=body.message_id,
            feedback_type=body.feedback_type,
        )

        return FeedbackResponse(
            id=str(feedback.id),
            feedback_type=feedback.feedback_type,
            rating=feedback.rating,
            comment=feedback.comment,
            correction=feedback.correction,
            expected_intent=feedback.expected_intent,
            created_at=feedback.created_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_feedback_submit_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Speichern des Feedbacks",
        )


@router.get("/{conversation_id}/actions", response_model=ConversationActionsResponse)
@limiter.limit("60/minute")
async def get_actions(
    conversation_id: UUID,
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationActionsResponse:
    """Hole Aktionen einer Konversation."""
    try:
        # Prüfe Zugriff
        conv_query = select(AIConversation.id).where(
            and_(
                AIConversation.id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )
        conv_result = await db.execute(conv_query)
        if not conv_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Konversation nicht gefunden",
            )

        # Base conditions
        conditions = [AIConversationAction.conversation_id == conversation_id]

        if status_filter:
            try:
                action_status = AIActionStatus(status_filter)
                conditions.append(AIConversationAction.status == action_status.value)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungültiger Status-Filter: {status_filter}",
                )

        # Count total
        count_query = select(func.count(AIConversationAction.id)).where(and_(*conditions))
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch actions
        query = select(AIConversationAction).where(and_(*conditions))
        query = query.order_by(AIConversationAction.proposed_at.desc())

        result = await db.execute(query)
        actions = result.scalars().all()

        return ConversationActionsResponse(
            actions=[
                ActionResponse(
                    id=str(action.id),
                    action_type=action.action_type,
                    description=action.description,
                    status=action.status,
                    parameters=action.parameters or {},
                    result=action.result,
                    error_message=action.error_message,
                    affected_count=action.affected_count,
                    success_count=action.success_count,
                    failure_count=action.failure_count,
                    requires_confirmation=action.requires_confirmation,
                    confirmed_at=action.confirmed_at,
                    proposed_at=action.proposed_at,
                    executed_at=action.executed_at,
                )
                for action in actions
            ],
            total=total,
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_actions_get_db_error",
            user_id=str(current_user.id),
            conversation_id=str(conversation_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Aktionen",
        )


@router.post("/{conversation_id}/actions/{action_id}/confirm", response_model=ActionResponse)
@limiter.limit("20/minute")
async def confirm_action(
    conversation_id: UUID,
    action_id: UUID,
    body: ActionConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActionResponse:
    """Bestätigt eine vorgeschlagene Aktion."""
    try:
        # Prüfe Zugriff und hole Aktion
        action_query = select(AIConversationAction).join(
            AIConversation
        ).where(
            and_(
                AIConversationAction.id == action_id,
                AIConversationAction.conversation_id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )

        result = await db.execute(action_query)
        action = result.scalar_one_or_none()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aktion nicht gefunden",
            )

        if action.status != AIActionStatus.PROPOSED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aktion kann nicht bestätigt werden (Status: {action.status})",
            )

        # Aktualisiere Parameter wenn angegeben
        if body.parameters:
            action.parameters = {**(action.parameters or {}), **body.parameters}

        action.status = AIActionStatus.CONFIRMED.value
        action.confirmed_by_id = current_user.id
        action.confirmed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(action)

        logger.info(
            "ai_action_confirmed",
            user_id=str(current_user.id),
            action_id=str(action_id),
            action_type=action.action_type,
        )

        # Aktion asynchron ausführen via Celery Task
        from app.workers.tasks.ai_conversation_tasks import execute_ai_action

        try:
            execute_ai_action.delay(
                action_id=str(action_id),
                conversation_id=str(conversation_id),
                user_id=str(current_user.id),
                company_id=str(action.company_id) if hasattr(action, 'company_id') and action.company_id else None,
            )
        except Exception as task_error:
            logger.warning(
                "ai_action_celery_task_failed",
                user_id=str(current_user.id),
                action_id=str(action_id),
                error_type=type(task_error).__name__,
            )
            # Fehler beim Task-Dispatch nicht fatal - Aktion wurde trotzdem bestätigt

        return ActionResponse(
            id=str(action.id),
            action_type=action.action_type,
            description=action.description,
            status=action.status,
            parameters=action.parameters or {},
            result=action.result,
            error_message=action.error_message,
            affected_count=action.affected_count,
            success_count=action.success_count,
            failure_count=action.failure_count,
            requires_confirmation=action.requires_confirmation,
            confirmed_at=action.confirmed_at,
            proposed_at=action.proposed_at,
            executed_at=action.executed_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_action_confirm_db_error",
            user_id=str(current_user.id),
            action_id=str(action_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Bestätigen der Aktion",
        )


@router.post("/{conversation_id}/actions/{action_id}/cancel", response_model=ActionResponse)
@limiter.limit("20/minute")
async def cancel_action(
    conversation_id: UUID,
    action_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActionResponse:
    """Bricht eine vorgeschlagene Aktion ab."""
    try:
        # Prüfe Zugriff und hole Aktion
        action_query = select(AIConversationAction).join(
            AIConversation
        ).where(
            and_(
                AIConversationAction.id == action_id,
                AIConversationAction.conversation_id == conversation_id,
                AIConversation.user_id == current_user.id,
            )
        )

        result = await db.execute(action_query)
        action = result.scalar_one_or_none()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aktion nicht gefunden",
            )

        if action.status not in [AIActionStatus.PROPOSED.value, AIActionStatus.CONFIRMED.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aktion kann nicht abgebrochen werden (Status: {action.status})",
            )

        action.status = AIActionStatus.CANCELLED.value

        await db.commit()
        await db.refresh(action)

        logger.info(
            "ai_action_cancelled",
            user_id=str(current_user.id),
            action_id=str(action_id),
            action_type=action.action_type,
        )

        return ActionResponse(
            id=str(action.id),
            action_type=action.action_type,
            description=action.description,
            status=action.status,
            parameters=action.parameters or {},
            result=action.result,
            error_message=action.error_message,
            affected_count=action.affected_count,
            success_count=action.success_count,
            failure_count=action.failure_count,
            requires_confirmation=action.requires_confirmation,
            confirmed_at=action.confirmed_at,
            proposed_at=action.proposed_at,
            executed_at=action.executed_at,
        )

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(
            "ai_action_cancel_db_error",
            user_id=str(current_user.id),
            action_id=str(action_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Abbrechen der Aktion",
        )


@router.get("/stats", response_model=ConversationStatsResponse)
@limiter.limit("30/minute")
async def get_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationStatsResponse:
    """
    Hole umfassende Statistiken über Konversationen des Benutzers.

    Dies ist der primäre Stats-Endpoint (Frontend erwartet /stats).
    """
    try:
        # Anzahl Konversationen (gesamt und aktiv)
        total_conv_query = select(func.count(AIConversation.id)).where(
            AIConversation.user_id == current_user.id
        )
        total_conv_result = await db.execute(total_conv_query)
        total_conversations = total_conv_result.scalar() or 0

        active_conv_query = select(func.count(AIConversation.id)).where(
            and_(
                AIConversation.user_id == current_user.id,
                AIConversation.is_active == True,
            )
        )
        active_conv_result = await db.execute(active_conv_query)
        active_conversations = active_conv_result.scalar() or 0

        # Anzahl Nachrichten
        msg_count_query = select(func.count(AIConversationMessage.id)).join(
            AIConversation
        ).where(
            AIConversation.user_id == current_user.id
        )
        msg_count_result = await db.execute(msg_count_query)
        total_messages = msg_count_result.scalar() or 0

        # Anzahl Aktionen + Status-Breakdown
        action_count_query = select(func.count(AIConversationAction.id)).join(
            AIConversation
        ).where(
            AIConversation.user_id == current_user.id
        )
        action_count_result = await db.execute(action_count_query)
        total_actions = action_count_result.scalar() or 0

        # Aktionen nach Status
        actions_by_status_query = select(
            AIConversationAction.status,
            func.count(AIConversationAction.id)
        ).join(
            AIConversation
        ).where(
            AIConversation.user_id == current_user.id
        ).group_by(AIConversationAction.status)
        actions_by_status_result = await db.execute(actions_by_status_query)
        actions_by_status = {
            row[0]: row[1] for row in actions_by_status_result.all()
        }

        # Anzahl Feedbacks
        feedback_count_query = select(func.count(AIConversationFeedback.id)).where(
            AIConversationFeedback.user_id == current_user.id
        )
        feedback_count_result = await db.execute(feedback_count_query)
        total_feedbacks = feedback_count_result.scalar() or 0

        # Konversationen pro Tag (letzte 30 Tage)
        conversations_by_day_query = select(
            cast(AIConversation.created_at, Date).label("date"),
            func.count(AIConversation.id).label("count")
        ).where(
            and_(
                AIConversation.user_id == current_user.id,
                AIConversation.created_at >= func.now() - func.cast("30 days", func.literal_column("interval")),
            )
        ).group_by(
            cast(AIConversation.created_at, Date)
        ).order_by(
            cast(AIConversation.created_at, Date).desc()
        )
        conversations_by_day_result = await db.execute(conversations_by_day_query)
        conversations_by_day = [
            {"date": str(row.date), "count": row.count}
            for row in conversations_by_day_result.all()
        ]

        # Top Intents (häufigste erkannte Absichten)
        top_intents_query = select(
            AIConversationMessage.intent,
            func.count(AIConversationMessage.id).label("count")
        ).join(
            AIConversation
        ).where(
            and_(
                AIConversation.user_id == current_user.id,
                AIConversationMessage.intent.isnot(None),
            )
        ).group_by(
            AIConversationMessage.intent
        ).order_by(
            func.count(AIConversationMessage.id).desc()
        ).limit(10)
        top_intents_result = await db.execute(top_intents_query)
        top_intents = [
            {"intent": row.intent, "count": row.count}
            for row in top_intents_result.all()
        ]

        # Durchschnittswerte berechnen
        avg_messages = total_messages / total_conversations if total_conversations > 0 else 0.0
        avg_actions = total_actions / total_conversations if total_conversations > 0 else 0.0

        return ConversationStatsResponse(
            total_conversations=total_conversations,
            active_conversations=active_conversations,
            total_messages=total_messages,
            total_actions=total_actions,
            total_feedbacks=total_feedbacks,
            actions_by_status=actions_by_status,
            conversations_by_day=conversations_by_day,
            top_intents=top_intents,
            average_messages_per_conversation=round(avg_messages, 2),
            average_actions_per_conversation=round(avg_actions, 2),
        )

    except SQLAlchemyError as e:
        logger.error(
            "ai_stats_get_db_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Statistiken",
        )


@router.get("/stats/summary")
@limiter.limit("30/minute")
async def get_conversation_stats_legacy(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Hole Statistiken über Konversationen des Benutzers (Legacy-Endpoint).

    DEPRECATED: Bitte /stats verwenden. Dieser Endpoint bleibt für
    Rückwärtskompatibilität erhalten.
    """
    try:
        # Anzahl Konversationen
        conv_count_query = select(func.count(AIConversation.id)).where(
            and_(
                AIConversation.user_id == current_user.id,
                AIConversation.is_active == True,
            )
        )
        conv_count_result = await db.execute(conv_count_query)
        total_conversations = conv_count_result.scalar() or 0

        # Anzahl Nachrichten
        msg_count_query = select(func.count(AIConversationMessage.id)).join(
            AIConversation
        ).where(
            AIConversation.user_id == current_user.id
        )
        msg_count_result = await db.execute(msg_count_query)
        total_messages = msg_count_result.scalar() or 0

        # Anzahl Aktionen
        action_count_query = select(func.count(AIConversationAction.id)).join(
            AIConversation
        ).where(
            AIConversation.user_id == current_user.id
        )
        action_count_result = await db.execute(action_count_query)
        total_actions = action_count_result.scalar() or 0

        # Anzahl Feedbacks
        feedback_count_query = select(func.count(AIConversationFeedback.id)).where(
            AIConversationFeedback.user_id == current_user.id
        )
        feedback_count_result = await db.execute(feedback_count_query)
        total_feedbacks = feedback_count_result.scalar() or 0

        return {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "total_actions": total_actions,
            "total_feedbacks": total_feedbacks,
        }

    except SQLAlchemyError as e:
        logger.error(
            "ai_stats_legacy_get_db_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Datenbankfehler beim Laden der Statistiken",
        )
