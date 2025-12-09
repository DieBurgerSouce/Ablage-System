"""RAG Chat API Endpoints.

Chat-System mit RAG-Kontext:
- Session Management
- Kontext-aware Antworten
- Streaming Support
- Chat Historie
"""

import structlog
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    User,
    RAGChatSession,
    RAGChatMessage,
    RAGChatRole,
)
from app.api.dependencies import get_current_user, get_db
from app.api.schemas.rag import (
    RAGChatRequest,
    RAGChatResponse,
    RAGChatSessionCreate,
    RAGChatSessionResponse,
    RAGChatSessionWithMessages,
    RAGChatMessageResponse,
    RAGContextType,
    RAGChunkSearchResult,
)
from app.services.rag.llm_service import (
    get_llm_service,
    LLMService,
    LLMMessage,
    LLMContextType,
)
from app.services.rag.search_service import get_rag_search_service, RAGSearchService
from app.services.rag.prompt_templates import (
    build_rag_context,
    build_chat_prompt,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["rag-chat"])


def get_llm_service_dep() -> LLMService:
    """Dependency fuer LLMService."""
    return get_llm_service()


def get_search_service_dep() -> RAGSearchService:
    """Dependency fuer RAGSearchService."""
    return get_rag_search_service()


@router.post(
    "",
    response_model=RAGChatResponse,
    summary="Chat-Nachricht senden",
    description="Sendet eine Nachricht und erhaelt eine RAG-gestuetzte Antwort."
)
async def send_chat_message(
    request: RAGChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_service: LLMService = Depends(get_llm_service_dep),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> RAGChatResponse:
    """
    Sendet eine Chat-Nachricht und erhaelt eine Antwort.

    **Ablauf:**
    1. Relevante Chunks suchen (RAG)
    2. Kontext aus Chunks aufbauen
    3. LLM-Antwort generieren
    4. Nachricht und Antwort speichern

    **Kontext-Typen:**
    - `general`: Allgemeine Dokumenten-Fragen
    - `customer`: Kunden-bezogene Anfragen
    - `document`: Fragen zu spezifischem Dokument
    - `report`: Report-Generierung
    """
    start_time = datetime.now(timezone.utc)

    logger.info(
        "chat_message_request",
        user_id=str(current_user.id),
        session_id=str(request.session_id) if request.session_id else "new",
        context_type=request.context_type.value,
        realtime=request.realtime,
        message_length=len(request.message)
    )

    try:
        # 1. Session holen oder erstellen
        session = await _get_or_create_session(
            db=db,
            user_id=current_user.id,
            session_id=request.session_id,
            context_type=request.context_type,
            context_id=request.context_id
        )

        # 2. Chat-Historie laden
        history = await _get_chat_history(db, session.id)

        # 3. Relevante Chunks suchen
        document_ids = None
        if request.context_type == RAGContextType.DOCUMENT and request.context_id:
            try:
                document_ids = [UUID(request.context_id)]
            except ValueError:
                pass

        chunks = await search_service.search_for_context(
            db=db,
            query=request.message,
            context_chunks=settings.RAG_CHAT_CONTEXT_CHUNKS,
            document_ids=document_ids
        )

        # 4. RAG-Kontext aufbauen
        context = build_rag_context(chunks)

        # 5. Prompt erstellen
        messages = build_chat_prompt(
            question=request.message,
            context=context,
            history=history,
            realtime=request.realtime
        )

        # LLM Messages konvertieren
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        # 6. LLM-Antwort generieren
        llm_context = LLMContextType.REALTIME if request.realtime else LLMContextType.GENERAL
        if request.context_type == RAGContextType.CUSTOMER:
            llm_context = LLMContextType.CUSTOMER

        response = await llm_service.generate(
            messages=llm_messages,
            context_type=llm_context,
            enable_thinking=not request.realtime  # Kein Thinking im Realtime-Modus
        )

        # 7. Nachrichten speichern
        # User-Nachricht
        user_message = RAGChatMessage(
            session_id=session.id,
            role=RAGChatRole.USER,
            content=request.message
        )
        db.add(user_message)

        # Assistant-Nachricht
        assistant_message = RAGChatMessage(
            session_id=session.id,
            role=RAGChatRole.ASSISTANT,
            content=response.content,
            thinking_content=response.thinking_content,
            model_used=response.model,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            generation_time_ms=response.generation_time_ms,
            source_chunks=[UUID(c["chunk_id"]) for c in chunks] if chunks else None
        )
        db.add(assistant_message)

        # Session aktualisieren
        session.message_count += 2
        session.last_message_at = datetime.now(timezone.utc)

        await db.commit()

        # 8. Response erstellen
        total_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        sources = [
            RAGChunkSearchResult(
                chunk_id=UUID(c["chunk_id"]),
                document_id=UUID(c["document_id"]),
                chunk_text=c["text"][:500],  # Gekuerzt
                chunk_index=0,
                page_number=c.get("page_number"),
                section_type=c.get("section_type"),
                similarity=c.get("similarity", 0),
                rerank_score=c.get("rerank_score")
            )
            for c in chunks
        ]

        return RAGChatResponse(
            session_id=session.id,
            message=response.content,
            thinking_content=response.thinking_content,
            sources=sources,
            model_used=response.model,
            generation_time_ms=total_time
        )

    except Exception as e:
        logger.exception(
            "chat_message_failed",
            user_id=str(current_user.id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat fehlgeschlagen: {str(e)}"
        )


@router.post(
    "/sessions",
    response_model=RAGChatSessionResponse,
    summary="Neue Chat-Session erstellen",
    description="Erstellt eine neue Chat-Session."
)
async def create_chat_session(
    request: RAGChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RAGChatSessionResponse:
    """
    Erstellt eine neue Chat-Session.

    Sessions organisieren zusammengehoerige Chat-Nachrichten.
    """
    session = RAGChatSession(
        user_id=current_user.id,
        session_token=str(uuid4()),
        title=request.title,
        context_type=request.context_type.value if request.context_type else None,
        context_id=request.context_id,
        status="active"
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "chat_session_created",
        user_id=str(current_user.id),
        session_id=str(session.id)
    )

    return RAGChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        session_token=session.session_token,
        title=session.title,
        context_type=session.context_type,
        context_id=session.context_id,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at
    )


@router.get(
    "/sessions",
    response_model=List[RAGChatSessionResponse],
    summary="Chat-Sessions auflisten",
    description="Listet alle Chat-Sessions des Benutzers auf."
)
async def list_chat_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[RAGChatSessionResponse]:
    """
    Listet Chat-Sessions des aktuellen Benutzers.

    Sortiert nach letzter Aktivitaet.
    """
    result = await db.execute(
        select(RAGChatSession)
        .where(RAGChatSession.user_id == current_user.id)
        .order_by(RAGChatSession.last_message_at.desc().nullsfirst())
        .offset(offset)
        .limit(limit)
    )
    sessions = result.scalars().all()

    return [
        RAGChatSessionResponse(
            id=s.id,
            user_id=s.user_id,
            session_token=s.session_token,
            title=s.title,
            context_type=s.context_type,
            context_id=s.context_id,
            status=s.status,
            message_count=s.message_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message_at=s.last_message_at
        )
        for s in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=RAGChatSessionWithMessages,
    summary="Chat-Session mit Verlauf abrufen",
    description="Gibt eine Session mit allen Nachrichten zurueck."
)
async def get_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RAGChatSessionWithMessages:
    """
    Ruft eine Chat-Session mit vollstaendigem Verlauf ab.
    """
    # Session laden
    result = await db.execute(
        select(RAGChatSession).where(
            RAGChatSession.id == session_id,
            RAGChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden"
        )

    # Nachrichten laden
    messages_result = await db.execute(
        select(RAGChatMessage)
        .where(RAGChatMessage.session_id == session_id)
        .order_by(RAGChatMessage.created_at)
    )
    messages = messages_result.scalars().all()

    return RAGChatSessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        session_token=session.session_token,
        title=session.title,
        context_type=session.context_type,
        context_id=session.context_id,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        messages=[
            RAGChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                thinking_content=m.thinking_content,
                confidence_score=m.confidence_score,
                model_used=m.model_used,
                tokens_input=m.tokens_input,
                tokens_output=m.tokens_output,
                generation_time_ms=m.generation_time_ms,
                created_at=m.created_at
            )
            for m in messages
        ]
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Chat-Session loeschen",
    description="Loescht eine Chat-Session und alle Nachrichten."
)
async def delete_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Loescht eine Chat-Session.

    Alle zugehoerigen Nachrichten werden ebenfalls geloescht.
    """
    # Session pruefen
    result = await db.execute(
        select(RAGChatSession).where(
            RAGChatSession.id == session_id,
            RAGChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden"
        )

    # Nachrichten loeschen
    await db.execute(
        RAGChatMessage.__table__.delete().where(
            RAGChatMessage.session_id == session_id
        )
    )

    # Session loeschen
    await db.delete(session)
    await db.commit()

    logger.info(
        "chat_session_deleted",
        user_id=str(current_user.id),
        session_id=str(session_id)
    )

    return {
        "success": True,
        "session_id": str(session_id),
        "message": "Session geloescht"
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def _get_or_create_session(
    db: AsyncSession,
    user_id: UUID,
    session_id: Optional[UUID],
    context_type: RAGContextType,
    context_id: Optional[str]
) -> RAGChatSession:
    """Holt oder erstellt eine Chat-Session."""
    if session_id:
        result = await db.execute(
            select(RAGChatSession).where(
                RAGChatSession.id == session_id,
                RAGChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    # Neue Session erstellen
    session = RAGChatSession(
        user_id=user_id,
        session_token=str(uuid4()),
        context_type=context_type.value,
        context_id=context_id,
        status="active"
    )
    db.add(session)
    await db.flush()

    return session


async def _get_chat_history(
    db: AsyncSession,
    session_id: UUID,
    max_messages: int = None
) -> List[dict]:
    """Laedt Chat-Historie fuer Kontext."""
    max_messages = max_messages or settings.RAG_CHAT_MAX_HISTORY

    result = await db.execute(
        select(RAGChatMessage)
        .where(RAGChatMessage.session_id == session_id)
        .order_by(RAGChatMessage.created_at.desc())
        .limit(max_messages)
    )
    messages = result.scalars().all()

    # Umkehren fuer chronologische Reihenfolge
    return [
        {"role": m.role.value, "content": m.content}
        for m in reversed(messages)
    ]
