"""
WebSocket Manager fuer Real-time Chat Collaboration.

Verwaltet WebSocket-Verbindungen fuer:
- Echtzeit-Nachrichten-Synchronisation
- Typing-Indikatoren
- Presence-Tracking (wer ist online)
- AI-Streaming-Broadcast
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any, List
from uuid import UUID
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
import structlog

logger = structlog.get_logger(__name__)


class WSMessageType(str, Enum):
    """WebSocket Nachrichten-Typen."""
    # Chat Messages
    NEW_MESSAGE = "new_message"
    MESSAGE_UPDATED = "message_updated"

    # Typing Indicators
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"

    # Presence
    PRESENCE_UPDATE = "presence"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"

    # AI Streaming
    AI_STREAMING = "ai_streaming"
    AI_CHUNK = "ai_chunk"
    AI_DONE = "ai_done"

    # Errors
    ERROR = "error"


class ConnectionInfo:
    """Informationen ueber eine WebSocket-Verbindung."""

    def __init__(
        self,
        websocket: WebSocket,
        user_id: str,
        username: str,
        session_id: str,
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.username = username
        self.session_id = session_id
        self.connected_at = datetime.now(timezone.utc)
        self.is_typing = False
        self.last_activity = datetime.now(timezone.utc)


class ChatWebSocketManager:
    """
    Manager fuer WebSocket-Verbindungen in Chat Sessions.

    Features:
    - Multi-User pro Session
    - Broadcast an alle Session-Teilnehmer
    - Typing-Indikatoren mit Debouncing
    - Presence-Tracking
    - AI-Streaming-Weiterleitung
    """

    def __init__(self):
        # session_id -> {user_id -> ConnectionInfo}
        self._connections: Dict[str, Dict[str, ConnectionInfo]] = {}
        # user_id -> Set[session_id]  (User kann in mehreren Sessions sein)
        self._user_sessions: Dict[str, Set[str]] = {}
        # Lock fuer thread-safe Zugriff
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        user_id: str,
        username: str,
    ) -> bool:
        """
        Verbindet einen User mit einer Chat Session.

        Args:
            websocket: WebSocket-Verbindung
            session_id: Chat Session ID
            user_id: User ID
            username: Username fuer Anzeige

        Returns:
            True wenn erfolgreich verbunden
        """
        await websocket.accept()

        async with self._lock:
            # Session-Dict erstellen falls nicht vorhanden
            if session_id not in self._connections:
                self._connections[session_id] = {}

            # Alte Verbindung schliessen falls vorhanden
            if user_id in self._connections[session_id]:
                old_conn = self._connections[session_id][user_id]
                try:
                    await old_conn.websocket.close()
                except Exception as e:
                    logger.debug("close_old_websocket_connection", error_type=type(e).__name__)

            # Neue Verbindung speichern
            conn_info = ConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                username=username,
                session_id=session_id,
            )
            self._connections[session_id][user_id] = conn_info

            # User-Sessions tracken
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = set()
            self._user_sessions[user_id].add(session_id)

        logger.info(
            "websocket_connected",
            session_id=session_id,
            user_id=user_id,
            username=username,
        )

        # User-joined Event an andere senden
        await self.broadcast_to_session(
            session_id=session_id,
            message={
                "type": WSMessageType.USER_JOINED.value,
                "user_id": user_id,
                "username": username,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude_user=user_id,
        )

        # Presence Update an alle senden
        await self.send_presence_update(session_id)

        return True

    async def disconnect(
        self,
        session_id: str,
        user_id: str,
    ) -> None:
        """
        Trennt einen User von einer Chat Session.

        Args:
            session_id: Chat Session ID
            user_id: User ID
        """
        username = None

        async with self._lock:
            if session_id in self._connections:
                if user_id in self._connections[session_id]:
                    conn_info = self._connections[session_id][user_id]
                    username = conn_info.username
                    del self._connections[session_id][user_id]

                    # Leere Session entfernen
                    if not self._connections[session_id]:
                        del self._connections[session_id]

            # User-Sessions aktualisieren
            if user_id in self._user_sessions:
                self._user_sessions[user_id].discard(session_id)
                if not self._user_sessions[user_id]:
                    del self._user_sessions[user_id]

        logger.info(
            "websocket_disconnected",
            session_id=session_id,
            user_id=user_id,
        )

        # User-left Event an andere senden
        if username:
            await self.broadcast_to_session(
                session_id=session_id,
                message={
                    "type": WSMessageType.USER_LEFT.value,
                    "user_id": user_id,
                    "username": username,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Presence Update an alle senden
            await self.send_presence_update(session_id)

    async def broadcast_to_session(
        self,
        session_id: str,
        message: Dict[str, Any],
        exclude_user: Optional[str] = None,
    ) -> None:
        """
        Sendet eine Nachricht an alle User in einer Session.

        Args:
            session_id: Chat Session ID
            message: Nachricht als Dict
            exclude_user: Optional User ID zum Ausschliessen
        """
        async with self._lock:
            if session_id not in self._connections:
                return

            connections = list(self._connections[session_id].items())

        # Ausserhalb des Locks senden
        for user_id, conn_info in connections:
            if exclude_user and user_id == exclude_user:
                continue

            try:
                await conn_info.websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    session_id=session_id,
                    user_id=user_id,
                    error=str(e),
                )

    async def send_to_user(
        self,
        session_id: str,
        user_id: str,
        message: Dict[str, Any],
    ) -> bool:
        """
        Sendet eine Nachricht an einen spezifischen User.

        Args:
            session_id: Chat Session ID
            user_id: Ziel-User ID
            message: Nachricht als Dict

        Returns:
            True wenn erfolgreich gesendet
        """
        async with self._lock:
            if session_id not in self._connections:
                return False
            if user_id not in self._connections[session_id]:
                return False

            conn_info = self._connections[session_id][user_id]

        try:
            await conn_info.websocket.send_json(message)
            return True
        except Exception as e:
            logger.warning(
                "websocket_send_to_user_failed",
                session_id=session_id,
                user_id=user_id,
                error=str(e),
            )
            return False

    async def send_presence_update(self, session_id: str) -> None:
        """
        Sendet ein Presence-Update an alle User in einer Session.

        Args:
            session_id: Chat Session ID
        """
        async with self._lock:
            if session_id not in self._connections:
                return

            online_users = [
                {
                    "user_id": conn.user_id,
                    "username": conn.username,
                    "is_typing": conn.is_typing,
                    "connected_at": conn.connected_at.isoformat(),
                }
                for conn in self._connections[session_id].values()
            ]

        await self.broadcast_to_session(
            session_id=session_id,
            message={
                "type": WSMessageType.PRESENCE_UPDATE.value,
                "users": online_users,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def set_typing(
        self,
        session_id: str,
        user_id: str,
        is_typing: bool,
    ) -> None:
        """
        Setzt den Typing-Status eines Users.

        Args:
            session_id: Chat Session ID
            user_id: User ID
            is_typing: True wenn User tippt
        """
        username = None

        async with self._lock:
            if session_id in self._connections:
                if user_id in self._connections[session_id]:
                    conn = self._connections[session_id][user_id]
                    conn.is_typing = is_typing
                    conn.last_activity = datetime.now(timezone.utc)
                    username = conn.username

        if username:
            msg_type = WSMessageType.TYPING_START if is_typing else WSMessageType.TYPING_STOP
            await self.broadcast_to_session(
                session_id=session_id,
                message={
                    "type": msg_type.value,
                    "user_id": user_id,
                    "username": username,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude_user=user_id,
            )

    async def broadcast_new_message(
        self,
        session_id: str,
        message_id: str,
        user_id: str,
        username: str,
        content: str,
        role: str,
        created_at: str,
    ) -> None:
        """
        Broadcastet eine neue Chat-Nachricht.

        Args:
            session_id: Chat Session ID
            message_id: Nachricht ID
            user_id: Sender User ID
            username: Sender Username
            content: Nachrichteninhalt
            role: Rolle (user/assistant)
            created_at: Erstellungszeitpunkt
        """
        await self.broadcast_to_session(
            session_id=session_id,
            message={
                "type": WSMessageType.NEW_MESSAGE.value,
                "message": {
                    "id": message_id,
                    "user_id": user_id,
                    "username": username,
                    "content": content,
                    "role": role,
                    "created_at": created_at,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude_user=user_id if role == "user" else None,
        )

    async def broadcast_ai_chunk(
        self,
        session_id: str,
        chunk: str,
        message_id: Optional[str] = None,
    ) -> None:
        """
        Broadcastet einen AI-Streaming-Chunk.

        Args:
            session_id: Chat Session ID
            chunk: Text-Chunk
            message_id: Optional Message ID
        """
        await self.broadcast_to_session(
            session_id=session_id,
            message={
                "type": WSMessageType.AI_CHUNK.value,
                "chunk": chunk,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def broadcast_ai_done(
        self,
        session_id: str,
        message_id: str,
        full_content: str,
    ) -> None:
        """
        Broadcastet das Ende der AI-Antwort.

        Args:
            session_id: Chat Session ID
            message_id: Message ID
            full_content: Vollstaendiger Inhalt
        """
        await self.broadcast_to_session(
            session_id=session_id,
            message={
                "type": WSMessageType.AI_DONE.value,
                "message_id": message_id,
                "full_content": full_content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def get_online_users(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Gibt alle online User einer Session zurueck.

        Args:
            session_id: Chat Session ID

        Returns:
            Liste von User-Infos
        """
        if session_id not in self._connections:
            return []

        return [
            {
                "user_id": conn.user_id,
                "username": conn.username,
                "is_typing": conn.is_typing,
            }
            for conn in self._connections[session_id].values()
        ]

    def get_connection_count(self, session_id: str) -> int:
        """Gibt Anzahl der Verbindungen in einer Session zurueck."""
        if session_id not in self._connections:
            return 0
        return len(self._connections[session_id])


# Singleton-Instanz
_ws_manager: Optional[ChatWebSocketManager] = None


def get_websocket_manager() -> ChatWebSocketManager:
    """Gibt die globale WebSocket-Manager-Instanz zurueck."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = ChatWebSocketManager()
    return _ws_manager
