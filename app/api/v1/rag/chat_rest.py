"""REST Chat API Endpoints.

Non-WebSocket chat interface fuer:
- Session-Management
- Synchrone Chat-Nachrichten mit Multi-Tool Calling
- History-Abfragen
- Action Confirm/Reject

Feinpoliert und durchdacht - Intelligente Dokumentenanalyse.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_current_user, get_db
from app.services.rag import get_chat_service
from app.services.rag.action_dispatcher import get_action_dispatcher
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["rag-chat"])


def _get_user_level(user: User) -> str:
    """Bestimmt User-Level fuer Tool-Zugriff.

    Args:
        user: User-Objekt

    Returns:
        viewer, editor, oder admin
    """
    if user.is_superuser:
        return "admin"
    if hasattr(user, "role"):
        if user.role in ("admin", "manager"):
            return "admin"
        if user.role in ("editor", "operator"):
            return "editor"
    return "viewer"


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


class ChatToolActionResponse(BaseModel):
    """Tool action result in chat response."""

    action_id: str
    tool_name: str
    parameters: JSONDict = {}
    action_type: str
    status: str
    message: str = ""
    data: Optional[JSONDict] = None
    requires_confirmation: bool = False
    execution_time_ms: int = 0


class ChatMessageResponse(BaseModel):
    """Chat message response."""

    message_id: str
    session_id: str
    content: str
    sources: List[ChatMessageSource]
    tool_actions: List[ChatToolActionResponse] = []
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
    messages: List[JSONDict]
    context_documents: List[JSONDict]
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
    Parses tool-calls from LLM response and dispatches actions.
    """
    chat_service = get_chat_service()

    # Bestimme User-Level fuer Tool-Zugriff
    user_level = _get_user_level(current_user)

    try:
        # Use existing session or create new one
        message = await chat_service.chat(
            query=request.content,
            user_id=current_user.id,
            db=db,
            session_id=request.session_id,
            stream=False,
            user=current_user,
            user_level=user_level,
        )

        # Get session for response
        session = chat_service.get_or_create_session(
            session_id=request.session_id,
            user_id=current_user.id,
            user_level=user_level,
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
            tool_actions=[
                ChatToolActionResponse(**action)
                for action in message.tool_actions
            ],
            timestamp=message.timestamp,
        )

    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Berechtigung"),
        )
    except Exception as e:
        logger.error(
            "chat_message_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Chat-Verarbeitung"),
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
    Processes tool-calls after streaming completes and emits action events.
    """
    chat_service = get_chat_service()
    user_level = _get_user_level(current_user)

    async def generate():
        """Generate streaming response."""
        try:
            session = chat_service.get_or_create_session(
                session_id=request.session_id,
                user_id=current_user.id,
                user_level=user_level,
            )

            # Retrieve context
            context_docs = await chat_service.retrieve_context(
                query=request.content,
                user_id=current_user.id,
                db=db,
            )

            # Send context info
            import json as _json
            yield f"data: {_json.dumps({'type': 'context', 'count': len(context_docs)})}\n\n"

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

            # Parse und dispatch Tool-Calls
            tool_actions: List[JSONDict] = []
            parsed_calls = chat_service.tool_registry.parse_tool_calls(full_response)

            if parsed_calls:
                yield f"data: {_json.dumps({'type': 'processing', 'message': 'Aktionen werden ausgefuehrt...'})}\n\n"

                tool_actions = await chat_service.dispatch_tool_calls(
                    tool_calls=parsed_calls,
                    user=current_user,
                    db=db,
                )

                # Emit each tool action as SSE event
                for action in tool_actions:
                    yield f"data: {_json.dumps({'type': 'tool_action', **action})}\n\n"

            # Save to session
            from app.services.rag.chat_service import ChatMessage

            user_msg = ChatMessage(role="user", content=request.content)
            session.add_message(user_msg)

            sources = [
                {"document_id": doc["document_id"], "filename": doc["filename"], "similarity": doc["similarity"]}
                for doc in context_docs
            ]
            assistant_msg = ChatMessage(
                role="assistant",
                content=full_response,
                sources=sources,
                tool_actions=tool_actions,
            )
            session.add_message(assistant_msg)

            # Send completion
            yield f"data: {_json.dumps({'type': 'complete', 'session_id': session.id, 'message_id': assistant_msg.id, 'tool_action_count': len(tool_actions)})}\n\n"

        except Exception as e:
            logger.error("chat_stream_error", **safe_error_log(e))
            yield f'data: {{"type": "error", "message": "{safe_error_detail(e, "Chat-Stream")}"}}\n\n'

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
        "tools_available": len(
            chat_service.tool_registry.get_tools_for_user(_get_user_level(current_user))
        ),
    }


# ==================== Action API ====================


@router.post(
    "/actions/{action_id}/confirm",
    summary="Aktion bestaetigen",
    description="Bestaetigt eine ausstehende Chat-Aktion.",
)
async def confirm_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a pending chat action."""
    dispatcher = get_action_dispatcher()

    try:
        result = await dispatcher.confirm_action(
            action_id=UUID(action_id),
            user=current_user,
            db=db,
        )
        return {
            "success": result.status.value != "failed",
            "status": result.status.value,
            "message": result.message or "",
            "result": result.data if hasattr(result, "data") else None,
        }
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Action-ID",
        )
    except Exception as e:
        logger.error(
            "action_confirm_error",
            action_id=action_id,
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Aktionsbestaetigung"),
        )


@router.post(
    "/actions/{action_id}/reject",
    summary="Aktion ablehnen",
    description="Lehnt eine ausstehende Chat-Aktion ab.",
)
async def reject_action(
    action_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending chat action."""
    dispatcher = get_action_dispatcher()

    try:
        result = await dispatcher.reject_action(
            action_id=UUID(action_id),
            user=current_user,
            db=db,
        )
        return {
            "success": True,
            "status": result.status.value,
            "message": result.message or "Aktion abgelehnt",
        }
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Action-ID",
        )
    except Exception as e:
        logger.error(
            "action_reject_error",
            action_id=action_id,
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Aktionsablehnung"),
        )
