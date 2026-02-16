"""
WebSocket Endpoint für Chat Collaboration.

Real-time Kommunikation für:
- Nachrichten-Synchronisation
- Typing-Indikatoren
- Presence-Tracking
- AI-Streaming
"""

import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from jose import JWTError, jwt

from app.db.session import get_async_session_context
from app.db.models import User, ChatSessionAccessLevel
from app.services.websocket_manager import (
    get_websocket_manager,
    ChatWebSocketManager,
    WSMessageType,
)
from app.services.chat_sharing_service import get_chat_sharing_service
from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["chat-websocket"])


async def authenticate_websocket(token: str) -> tuple[User | None, str | None]:
    """
    Authentifiziert einen WebSocket-User via JWT Token.

    Args:
        token: JWT Access Token

    Returns:
        Tuple von (User, error_message)
    """
    try:
        # Explizite Expiration-Prüfung für Enterprise Security
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True, "require_exp": True}
        )
        user_id = payload.get("sub")
        if not user_id:
            return None, "Ungültiger Token"

        async with get_async_session_context() as db:
            user = await db.get(User, UUID(user_id))
            if not user:
                return None, "Benutzer nicht gefunden"
            if not user.is_active:
                return None, "Benutzer deaktiviert"

            return user, None

    except JWTError as e:
        logger.warning("websocket_auth_failed", **safe_error_log(e))
        return None, "Token ungültig oder abgelaufen"
    except Exception as e:
        logger.error("websocket_auth_error", **safe_error_log(e))
        return None, "Authentifizierungsfehler"


async def check_session_access(
    user_id: UUID,
    session_id: str,
) -> tuple[bool, str | None]:
    """
    Prüft ob ein User Zugriff auf eine Chat Session hat.

    Args:
        user_id: User ID
        session_id: Chat Session ID

    Returns:
        Tuple von (has_access, access_level)
    """
    async with get_async_session_context() as db:
        sharing_service = get_chat_sharing_service(db)
        access_level = await sharing_service.get_access_level(
            UUID(session_id),
            user_id
        )
        if access_level:
            return True, access_level

    return False, None


@router.websocket("/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="JWT Access Token"),
):
    """
    WebSocket Endpoint für Chat Real-time Collaboration.

    **Verbindung herstellen:**
    ```
    ws://localhost:8000/api/v1/rag/ws/chat/{session_id}?token=<jwt_token>
    ```

    **Client -> Server Messages:**
    - `{"type": "typing_start"}` - User tippt
    - `{"type": "typing_stop"}` - User tippt nicht mehr
    - `{"type": "ping"}` - Keep-alive

    **Server -> Client Messages:**
    - `{"type": "new_message", ...}` - Neue Nachricht
    - `{"type": "typing_start", "user_id": ..., "username": ...}`
    - `{"type": "typing_stop", "user_id": ..., "username": ...}`
    - `{"type": "presence", "users": [...]}` - Online Users
    - `{"type": "user_joined", ...}` - User beigetreten
    - `{"type": "user_left", ...}` - User verlassen
    - `{"type": "ai_chunk", "chunk": ...}` - AI Streaming Chunk
    - `{"type": "ai_done", "message_id": ..., "full_content": ...}`
    - `{"type": "error", "message": ...}` - Fehler
    """
    ws_manager = get_websocket_manager()

    # 1. Authentifizierung
    user, auth_error = await authenticate_websocket(token)
    if not user:
        await websocket.accept()
        await websocket.send_json({
            "type": WSMessageType.ERROR.value,
            "message": auth_error or "Authentifizierung fehlgeschlagen",
        })
        await websocket.close(code=4001)
        return

    # 2. Zugriffsprüfung
    has_access, access_level = await check_session_access(user.id, session_id)
    if not has_access:
        await websocket.accept()
        await websocket.send_json({
            "type": WSMessageType.ERROR.value,
            "message": "Kein Zugriff auf diese Session",
        })
        await websocket.close(code=4003)
        return

    # 3. Verbindung herstellen
    await ws_manager.connect(
        websocket=websocket,
        session_id=session_id,
        user_id=str(user.id),
        username=user.username,
    )

    logger.info(
        "chat_websocket_connected",
        session_id=session_id,
        user_id=str(user.id),
        username=user.username,
        access_level=access_level,
    )

    try:
        # 4. Message Loop
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "typing_start":
                    await ws_manager.set_typing(
                        session_id=session_id,
                        user_id=str(user.id),
                        is_typing=True,
                    )

                elif msg_type == "typing_stop":
                    await ws_manager.set_typing(
                        session_id=session_id,
                        user_id=str(user.id),
                        is_typing=False,
                    )

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "get_presence":
                    await ws_manager.send_presence_update(session_id)

                else:
                    logger.debug(
                        "unknown_ws_message_type",
                        session_id=session_id,
                        user_id=str(user.id),
                        msg_type=msg_type,
                    )

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": WSMessageType.ERROR.value,
                    "message": "Ungültiges JSON Format",
                })

    except WebSocketDisconnect:
        logger.info(
            "chat_websocket_disconnected",
            session_id=session_id,
            user_id=str(user.id),
        )
    except Exception as e:
        logger.error(
            "chat_websocket_error",
            session_id=session_id,
            user_id=str(user.id),
            **safe_error_log(e),
        )
    finally:
        await ws_manager.disconnect(
            session_id=session_id,
            user_id=str(user.id),
        )
