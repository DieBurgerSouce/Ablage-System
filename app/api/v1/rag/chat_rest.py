"""REST Chat API Endpoints.

Non-WebSocket chat interface fuer:
- Session-Management
- Synchrone Chat-Nachrichten
- History-Abfragen

Feinpoliert und durchdacht - Intelligente Dokumentenanalyse.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_current_user, get_db
from app.services.rag import get_chat_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["rag-chat"])


# ==================== Schemas ====================


class ChatMessageRequest(BaseModel):
    """Chat message request."""

    content: str = Field(..., min_length=1, max_length=10000, description="Nachricht")
    session_id: Optional[str] = Field(None, description="Session ID (optional, wird erstellt wenn leer)")


class ChatMessageSource(BaseModel):
    """Source document reference."""

    document_id: str
    filename: str
    similarity: float


class ChatMessageResponse(BaseModel):
    """Chat message response."""

    message_id: str
    session_id: str
    content: str
    sources: List[ChatMessageSource]
    timestamp: datetime


class SessionInfo(BaseModel):
    """Session information."""

    id: str
    user_id: Optional[str]
    message_count: int
    created_at: datetime
    updated_at: datetime


class SessionHistoryResponse(BaseModel):
    """Session history response."""

    session_id: str
    messages: List[Dict[str, Any]]
    context_documents: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """List of sessions."""

    sessions: List[SessionInfo]
    total: int


# ==================== Endpoints ====================


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    summary="Chat-Nachricht senden",
    description="Sendet eine Nachricht und erhaelt eine kontextbasierte Antwort.",
)
async def send_chat_message(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """Send a chat message and receive a response.

    Uses RAG to find relevant documents and generate a contextual answer.
    """
    chat_service = get_chat_service()

    try:
        # Use existing session or create new one
        message = await chat_service.chat(
            query=request.content,
            user_id=current_user.id,
            db=db,
            session_id=request.session_id,
            stream=False,
        )

        # Get session for response
        session = chat_service.get_or_create_session(
            session_id=request.session_id,
            user_id=current_user.id,
        )

        return ChatMessageResponse(
            message_id=message.id,
            session_id=session.id,
            content=message.content,
            sources=[
                ChatMessageSource(
                    document_id=s["document_id"],
                    filename=s["filename"],
                    similarity=s["similarity"],
                )
                for s in message.sources
            ],
            timestamp=message.timestamp,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "chat_message_error",
            user_id=str(current_user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat-Verarbeitung fehlgeschlagen: {str(e)}",
        )


@router.post(
    "/message/stream",
    summary="Chat-Nachricht mit Streaming",
    description="Sendet eine Nachricht und streamt die Antwort.",
)
async def send_chat_message_stream(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a chat message and stream the response.

    Returns Server-Sent Events (SSE) with streaming tokens.
    """
    chat_service = get_chat_service()

    async def generate():
        """Generate streaming response."""
        try:
            session = chat_service.get_or_create_session(
                session_id=request.session_id,
                user_id=current_user.id,
            )

            # Retrieve context
            context_docs = await chat_service.retrieve_context(
                query=request.content,
                user_id=current_user.id,
                db=db,
            )

            # Send context info
            yield f"data: {{'type': 'context', 'count': {len(context_docs)}}}\n\n"

            # Stream response
            full_response = ""
            async for token in chat_service.generate_response(
                query=request.content,
                session=session,
                context_documents=context_docs,
                stream=True,
            ):
                full_response += token
                # Escape for SSE
                escaped = token.replace("\n", "\\n").replace('"', '\\"')
                yield f'data: {{"type": "token", "content": "{escaped}"}}\n\n'

            # Save to session
            from app.services.rag.chat_service import ChatMessage

            user_msg = ChatMessage(role="user", content=request.content)
            session.add_message(user_msg)

            sources = [
                {"document_id": doc["document_id"], "filename": doc["filename"], "similarity": doc["similarity"]}
                for doc in context_docs
            ]
            assistant_msg = ChatMessage(role="assistant", content=full_response, sources=sources)
            session.add_message(assistant_msg)

            # Send completion
            yield f'data: {{"type": "complete", "session_id": "{session.id}", "message_id": "{assistant_msg.id}"}}\n\n'

        except Exception as e:
            logger.error("chat_stream_error", error=str(e))
            yield f'data: {{"type": "error", "message": "{str(e)}"}}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="Chat-Sessions auflisten",
    description="Gibt alle aktiven Chat-Sessions des Benutzers zurueck.",
)
async def list_sessions(
    current_user: User = Depends(get_current_user),
) -> SessionListResponse:
    """List all chat sessions for the current user."""
    chat_service = get_chat_service()

    sessions = []
    for session_id, session in chat_service.sessions.items():
        if session.user_id == current_user.id:
            sessions.append(
                SessionInfo(
                    id=session.id,
                    user_id=str(session.user_id) if session.user_id else None,
                    message_count=len(session.messages),
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )

    # Sort by updated_at descending
    sessions.sort(key=lambda s: s.updated_at, reverse=True)

    return SessionListResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.post(
    "/sessions",
    response_model=SessionInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Neue Chat-Session erstellen",
    description="Erstellt eine neue Chat-Session.",
)
async def create_session(
    current_user: User = Depends(get_current_user),
) -> SessionInfo:
    """Create a new chat session."""
    chat_service = get_chat_service()

    session = chat_service.get_or_create_session(user_id=current_user.id)

    logger.info(
        "chat_session_created_via_api",
        session_id=session.id,
        user_id=str(current_user.id),
    )

    return SessionInfo(
        id=session.id,
        user_id=str(session.user_id) if session.user_id else None,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionHistoryResponse,
    summary="Session-Verlauf abrufen",
    description="Gibt den Chat-Verlauf einer Session zurueck.",
)
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> SessionHistoryResponse:
    """Get chat history for a session."""
    chat_service = get_chat_service()

    history = chat_service.get_session_history(session_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden",
        )

    # Verify ownership
    if history.get("user_id") and history["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Session",
        )

    return SessionHistoryResponse(
        session_id=history["id"],
        messages=history["messages"],
        context_documents=history.get("context_documents", []),
        created_at=datetime.fromisoformat(history["created_at"]),
        updated_at=datetime.fromisoformat(history["updated_at"]),
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Session loeschen",
    description="Loescht eine Chat-Session.",
)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a chat session."""
    chat_service = get_chat_service()

    # Check if session exists and belongs to user
    history = chat_service.get_session_history(session_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden",
        )

    if history.get("user_id") and history["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Session",
        )

    chat_service.delete_session(session_id)

    logger.info(
        "chat_session_deleted",
        session_id=session_id,
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/clear",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Session-Verlauf loeschen",
    description="Loescht den Chat-Verlauf einer Session (behaelt System-Prompt).",
)
async def clear_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Clear chat history for a session."""
    chat_service = get_chat_service()

    # Check ownership
    history = chat_service.get_session_history(session_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden",
        )

    if history.get("user_id") and history["user_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer diese Session",
        )

    chat_service.clear_session_history(session_id)

    logger.info(
        "chat_session_history_cleared",
        session_id=session_id,
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/status",
    summary="Chat-Service Status",
    description="Gibt den Status des Chat-Service zurueck.",
)
async def get_chat_service_status(
    current_user: User = Depends(get_current_user),
):
    """Get chat service status."""
    chat_service = get_chat_service()

    return {
        "llm_enabled": chat_service.llm_enabled,
        "llm_model": chat_service.llm_model if chat_service.llm_enabled else None,
        "ollama_url": chat_service.ollama_url if chat_service.llm_enabled else None,
        "active_sessions": len(chat_service.sessions),
        "user_session_count": sum(
            1 for s in chat_service.sessions.values() if s.user_id == current_user.id
        ),
    }
