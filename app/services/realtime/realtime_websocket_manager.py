"""
Realtime WebSocket Manager.

Verwaltet WebSocket-Verbindungen für Echtzeit-Updates.
Unterscheidet sich vom Chat-WebSocket durch:
- User-basierte Subscriptions (nicht Session-basiert)
- Company-Isolation
- Event-Type Filtering
- Reconnection mit Event-History
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from app.core.safe_errors import safe_error_log
from app.services.realtime.event_broadcaster import (

    EventBroadcaster,
    RealtimeEvent,
    RealtimeEventType,
    get_event_broadcaster,
)

logger = structlog.get_logger(__name__)


class ConnectionState(str, Enum):
    """WebSocket Connection States."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


@dataclass
class UserConnection:
    """Informationen über eine User-WebSocket-Verbindung."""

    websocket: WebSocket
    user_id: str
    company_id: Optional[str]
    connected_at: datetime
    last_ping: datetime
    subscribed_events: Set[RealtimeEventType] = field(default_factory=set)
    state: ConnectionState = ConnectionState.CONNECTED
    viewing_document_id: Optional[str] = None
    cursor_position: Optional[Dict[str, int]] = None
    status: str = "online"

    @property
    def is_active(self) -> bool:
        """Prüft ob Verbindung aktiv ist."""
        return self.state == ConnectionState.CONNECTED


@dataclass
class Room:
    """WebSocket Room für dokumentbezogene Kommunikation."""

    room_id: str
    room_type: str
    members: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WSMessage:
    """WebSocket Message Structure."""

    type: str
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Konvertiert zu JSON String."""
        return json.dumps(self.to_dict())


class RealtimeWebSocketManager:
    """
    Manager für Realtime WebSocket Verbindungen.

    Features:
    - User-basierte Verbindungsverwaltung
    - Company-Isolation (Multi-Tenant)
    - Event-Type Subscriptions
    - Heartbeat/Ping-Pong
    - Reconnection mit Event-History
    - Graceful Disconnect
    """

    PING_INTERVAL_SECONDS = 30
    PING_TIMEOUT_SECONDS = 10

    def __init__(self, broadcaster: Optional[EventBroadcaster] = None) -> None:
        """
        Initialisiert den WebSocket Manager.

        Args:
            broadcaster: Optional Event Broadcaster. Falls None, wird Singleton verwendet.
        """
        self._broadcaster = broadcaster or get_event_broadcaster()
        # user_id -> UserConnection
        self._connections: Dict[str, UserConnection] = {}
        # company_id -> Set[user_id]
        self._company_users: Dict[str, Set[str]] = {}
        # room_id -> Room
        self._rooms: Dict[str, Room] = {}
        self._lock = asyncio.Lock()
        self._ping_task: Optional[asyncio.Task] = None
        self._started = False

        # Register callback with broadcaster
        self._unsubscribe: Optional[Callable[[], None]] = None

    async def start(self) -> None:
        """Startet den WebSocket Manager."""
        if self._started:
            return

        # Register callback to receive events from broadcaster
        self._unsubscribe = self._broadcaster.register_callback(
            self._on_broadcast_event
        )

        # Start ping task
        self._ping_task = asyncio.create_task(self._ping_loop())
        self._started = True
        logger.info("Realtime WebSocket Manager gestartet")

    async def stop(self) -> None:
        """Stoppt den WebSocket Manager."""
        if not self._started:
            return

        # Unsubscribe from broadcaster
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        # Stop ping task
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None

        # Close all connections
        async with self._lock:
            for conn in self._connections.values():
                try:
                    await conn.websocket.close(code=1001, reason="Server shutdown")
                except Exception as e:
                    logger.debug("websocket_close_on_shutdown_failed", error_type=type(e).__name__)
            self._connections.clear()
            self._company_users.clear()

        self._started = False
        logger.info("Realtime WebSocket Manager gestoppt")

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        company_id: Optional[str] = None,
    ) -> bool:
        """
        Verbindet einen User.

        Args:
            websocket: WebSocket-Verbindung
            user_id: User ID
            company_id: Optional Company ID für Isolation

        Returns:
            True wenn erfolgreich verbunden
        """
        try:
            await websocket.accept()
        except Exception as e:
            logger.error("websocket_accept_failed", user_id=user_id, **safe_error_log(e))
            return False

        async with self._lock:
            # Alte Verbindung schließen falls vorhanden
            if user_id in self._connections:
                old_conn = self._connections[user_id]
                try:
                    await old_conn.websocket.close(
                        code=1000,
                        reason="Neue Verbindung aufgebaut"
                    )
                except Exception as e:
                    logger.debug("old_websocket_close_failed", error_type=type(e).__name__)

            # Neue Verbindung speichern
            now = datetime.now(timezone.utc)
            connection = UserConnection(
                websocket=websocket,
                user_id=user_id,
                company_id=company_id,
                connected_at=now,
                last_ping=now,
                subscribed_events=set(RealtimeEventType),  # Subscribe to all by default
            )
            self._connections[user_id] = connection

            # Company-User Mapping aktualisieren
            if company_id:
                if company_id not in self._company_users:
                    self._company_users[company_id] = set()
                self._company_users[company_id].add(user_id)

        logger.info(
            "websocket_connected",
            user_id=user_id,
            company_id=company_id,
        )

        # Send welcome message
        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="connected",
                payload={
                    "user_id": user_id,
                    "company_id": company_id,
                    "server_time": now.isoformat(),
                },
            ),
        )

        return True

    async def disconnect(self, user_id: str) -> None:
        """
        Trennt einen User.

        Args:
            user_id: User ID
        """
        company_id = None
        viewing_document_id = None

        async with self._lock:
            if user_id not in self._connections:
                return

            connection = self._connections[user_id]
            company_id = connection.company_id
            viewing_document_id = connection.viewing_document_id

            # Company-User Mapping aktualisieren
            if company_id and company_id in self._company_users:
                self._company_users[company_id].discard(user_id)
                if not self._company_users[company_id]:
                    del self._company_users[company_id]

            # Remove from all rooms
            rooms_to_clean = []
            for room_id, room in self._rooms.items():
                if user_id in room.members:
                    room.members.discard(user_id)
                    # Mark empty rooms for deletion
                    if not room.members:
                        rooms_to_clean.append(room_id)

            # Clean up empty rooms
            for room_id in rooms_to_clean:
                del self._rooms[room_id]

            # Verbindung entfernen
            del self._connections[user_id]

        # Notify company about presence change
        if company_id:
            await self.broadcast_to_company(
                company_id=company_id,
                message=WSMessage(
                    type="presence_changed",
                    payload={
                        "user_id": user_id,
                        "status": "offline",
                        "viewing_document_id": None,
                    },
                ),
            )

        # Notify document viewers if user was viewing a document
        if viewing_document_id:
            await self.broadcast_to_room(
                room_id=f"doc:{viewing_document_id}",
                message=WSMessage(
                    type="document_viewer_left",
                    payload={
                        "user_id": user_id,
                        "document_id": viewing_document_id,
                    },
                ),
            )

        logger.info("websocket_disconnected", user_id=user_id)

    async def handle_message(self, user_id: str, data: str) -> None:
        """
        Verarbeitet eine eingehende Nachricht.

        Args:
            user_id: User ID
            data: JSON-String der Nachricht
        """
        try:
            message = json.loads(data)
            msg_type = message.get("type", "")

            if msg_type == "ping":
                await self._handle_ping(user_id)
            elif msg_type == "subscribe":
                await self._handle_subscribe(user_id, message.get("event_types", []))
            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(user_id, message.get("event_types", []))
            elif msg_type == "get_history":
                await self._handle_get_history(user_id, message.get("since"))
            elif msg_type == "presence_update":
                await self._handle_presence_update(user_id, message)
            elif msg_type == "cursor_move":
                await self._handle_cursor_move(user_id, message)
            elif msg_type == "join_room":
                await self._handle_join_room(user_id, message.get("room_id"))
            elif msg_type == "leave_room":
                await self._handle_leave_room(user_id, message.get("room_id"))
            else:
                logger.warning(
                    "unknown_message_type",
                    user_id=user_id,
                    msg_type=msg_type,
                )

        except json.JSONDecodeError as e:
            logger.warning(
                "invalid_json_message",
                user_id=user_id,
                **safe_error_log(e),
            )
        except Exception as e:
            logger.error(
                "message_handling_failed",
                user_id=user_id,
                **safe_error_log(e),
            )

    async def _handle_ping(self, user_id: str) -> None:
        """Verarbeitet Ping-Nachricht."""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].last_ping = datetime.now(timezone.utc)

        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="pong",
                payload={"server_time": datetime.now(timezone.utc).isoformat()},
            ),
        )

    async def _handle_subscribe(self, user_id: str, event_types: List[str]) -> None:
        """Verarbeitet Subscribe-Nachricht."""
        async with self._lock:
            if user_id not in self._connections:
                return

            connection = self._connections[user_id]
            for event_type_str in event_types:
                try:
                    event_type = RealtimeEventType(event_type_str)
                    connection.subscribed_events.add(event_type)
                except ValueError:
                    logger.warning(
                        "invalid_event_type",
                        user_id=user_id,
                        event_type=event_type_str,
                    )

        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="subscribed",
                payload={"event_types": event_types},
            ),
        )

    async def _handle_unsubscribe(self, user_id: str, event_types: List[str]) -> None:
        """Verarbeitet Unsubscribe-Nachricht."""
        async with self._lock:
            if user_id not in self._connections:
                return

            connection = self._connections[user_id]
            for event_type_str in event_types:
                try:
                    event_type = RealtimeEventType(event_type_str)
                    connection.subscribed_events.discard(event_type)
                except ValueError as e:
                    logger.debug("invalid_event_type_on_unsubscribe", error_type=type(e).__name__)

        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="unsubscribed",
                payload={"event_types": event_types},
            ),
        )

    async def _handle_get_history(self, user_id: str, since: Optional[str]) -> None:
        """Verarbeitet Get-History-Nachricht für Reconnection."""
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError as e:
                logger.debug(
                    "since_timestamp_parse_failed",
                    error_type=type(e).__name__,
                )

        # Get company_id for filtering
        company_id = None
        async with self._lock:
            if user_id in self._connections:
                company_id = self._connections[user_id].company_id

        # Get recent events from broadcaster
        events = self._broadcaster.get_recent_events(
            since=since_dt,
            company_id=company_id,
            limit=50,
        )

        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="history",
                payload={
                    "events": [e.to_dict() for e in events],
                    "count": len(events),
                },
            ),
        )

    async def _on_broadcast_event(self, event: RealtimeEvent) -> None:
        """
        Callback vom Event Broadcaster.

        Verteilt Events an relevante User basierend auf:
        - Event-Type Subscription
        - Company-Isolation
        - User-Targeting
        """
        async with self._lock:
            connections_snapshot = list(self._connections.items())

        for user_id, connection in connections_snapshot:
            # Check if user is subscribed to this event type
            if event.event_type not in connection.subscribed_events:
                continue

            # Check company isolation
            if event.target_company_id:
                if connection.company_id and connection.company_id != event.target_company_id:
                    continue

            # Check user targeting
            if event.target_users and user_id not in event.target_users:
                continue

            # Send event
            await self._send_to_user(
                user_id=user_id,
                message=WSMessage(
                    type="event",
                    payload=event.to_dict(),
                ),
            )

    async def _send_to_user(self, user_id: str, message: WSMessage) -> bool:
        """
        Sendet eine Nachricht an einen User.

        Args:
            user_id: User ID
            message: Zu sendende Nachricht

        Returns:
            True wenn erfolgreich gesendet
        """
        async with self._lock:
            if user_id not in self._connections:
                return False
            connection = self._connections[user_id]

        try:
            await connection.websocket.send_text(message.to_json())
            return True
        except Exception as e:
            logger.warning(
                "websocket_send_failed",
                user_id=user_id,
                **safe_error_log(e),
            )
            # Mark for cleanup
            async with self._lock:
                if user_id in self._connections:
                    self._connections[user_id].state = ConnectionState.DISCONNECTED
            return False

    async def broadcast_to_company(
        self,
        company_id: str,
        message: WSMessage,
    ) -> int:
        """
        Sendet eine Nachricht an alle User einer Company.

        Args:
            company_id: Company ID
            message: Zu sendende Nachricht

        Returns:
            Anzahl der erfolgreichen Sendungen
        """
        async with self._lock:
            user_ids = self._company_users.get(company_id, set()).copy()

        sent_count = 0
        for user_id in user_ids:
            if await self._send_to_user(user_id, message):
                sent_count += 1

        return sent_count

    async def broadcast_to_all(self, message: WSMessage) -> int:
        """
        Sendet eine Nachricht an alle verbundenen User.

        Args:
            message: Zu sendende Nachricht

        Returns:
            Anzahl der erfolgreichen Sendungen
        """
        async with self._lock:
            user_ids = list(self._connections.keys())

        sent_count = 0
        for user_id in user_ids:
            if await self._send_to_user(user_id, message):
                sent_count += 1

        return sent_count

    async def update_presence(
        self,
        user_id: str,
        document_id: Optional[str] = None,
        status: str = "online",
    ) -> None:
        """
        Aktualisiert die Presence-Informationen eines Users.

        Args:
            user_id: User ID
            document_id: Optional Dokument-ID das der User betrachtet
            status: Status (online/away/busy)
        """
        old_document_id = None
        company_id = None

        async with self._lock:
            if user_id not in self._connections:
                return

            connection = self._connections[user_id]
            old_document_id = connection.viewing_document_id
            company_id = connection.company_id

            connection.viewing_document_id = document_id
            connection.status = status

        # Broadcast presence change to company
        if company_id:
            await self.broadcast_to_company(
                company_id=company_id,
                message=WSMessage(
                    type="presence_changed",
                    payload={
                        "user_id": user_id,
                        "status": status,
                        "viewing_document_id": document_id,
                    },
                ),
            )

        # Notify old document viewers
        if old_document_id and old_document_id != document_id:
            await self.broadcast_to_room(
                room_id=f"doc:{old_document_id}",
                message=WSMessage(
                    type="document_viewer_left",
                    payload={
                        "user_id": user_id,
                        "document_id": old_document_id,
                    },
                ),
            )

        # Notify new document viewers
        if document_id:
            await self.broadcast_to_room(
                room_id=f"doc:{document_id}",
                message=WSMessage(
                    type="document_viewer_joined",
                    payload={
                        "user_id": user_id,
                        "document_id": document_id,
                        "status": status,
                    },
                ),
                exclude_sender=user_id,
            )

    async def get_document_viewers(self, document_id: str) -> List[Dict[str, str]]:
        """
        Gibt alle User zurück die ein Dokument gerade betrachten.

        Args:
            document_id: Dokument ID

        Returns:
            Liste von User-Informationen
        """
        viewers: List[Dict[str, str]] = []

        async with self._lock:
            for user_id, connection in self._connections.items():
                if connection.viewing_document_id == document_id and connection.is_active:
                    viewers.append({
                        "user_id": user_id,
                        "status": connection.status,
                        "connected_at": connection.connected_at.isoformat(),
                    })

        return viewers

    async def get_company_presence(self, company_id: str) -> List[Dict[str, str]]:
        """
        Gibt Presence-Informationen aller User einer Company zurück.

        Args:
            company_id: Company ID

        Returns:
            Liste von User-Presence-Informationen
        """
        presence: List[Dict[str, str]] = []

        async with self._lock:
            user_ids = self._company_users.get(company_id, set())
            for user_id in user_ids:
                if user_id in self._connections:
                    connection = self._connections[user_id]
                    presence.append({
                        "user_id": user_id,
                        "status": connection.status,
                        "viewing_document_id": connection.viewing_document_id or "",
                        "connected_at": connection.connected_at.isoformat(),
                        "last_ping": connection.last_ping.isoformat(),
                    })

        return presence

    async def join_room(self, user_id: str, room_id: str) -> None:
        """
        User tritt einem Room bei.

        Args:
            user_id: User ID
            room_id: Room ID (z.B. "doc:12345", "workflow:abc")
        """
        async with self._lock:
            if user_id not in self._connections:
                return

            # Create room if it doesn't exist
            if room_id not in self._rooms:
                room_type = room_id.split(":")[0] if ":" in room_id else "default"
                self._rooms[room_id] = Room(
                    room_id=room_id,
                    room_type=room_type,
                    members=set(),
                )

            # Add user to room
            self._rooms[room_id].members.add(user_id)

        logger.info("user_joined_room", user_id=user_id, room_id=room_id)

        # Notify other room members
        await self.broadcast_to_room(
            room_id=room_id,
            message=WSMessage(
                type="room_user_joined",
                payload={
                    "user_id": user_id,
                    "room_id": room_id,
                },
            ),
            exclude_sender=user_id,
        )

        # Send confirmation to user
        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="room_joined",
                payload={
                    "room_id": room_id,
                    "member_count": len(self._rooms[room_id].members),
                },
            ),
        )

    async def leave_room(self, user_id: str, room_id: str) -> None:
        """
        User verlaesst einen Room.

        Args:
            user_id: User ID
            room_id: Room ID
        """
        async with self._lock:
            if room_id not in self._rooms:
                return

            room = self._rooms[room_id]
            room.members.discard(user_id)

            # Remove empty rooms
            if not room.members:
                del self._rooms[room_id]

        logger.info("user_left_room", user_id=user_id, room_id=room_id)

        # Notify other room members
        await self.broadcast_to_room(
            room_id=room_id,
            message=WSMessage(
                type="room_user_left",
                payload={
                    "user_id": user_id,
                    "room_id": room_id,
                },
            ),
        )

        # Send confirmation to user
        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="room_left",
                payload={"room_id": room_id},
            ),
        )

    async def broadcast_to_room(
        self,
        room_id: str,
        message: WSMessage,
        exclude_sender: Optional[str] = None,
    ) -> int:
        """
        Sendet eine Nachricht an alle Mitglieder eines Rooms.

        Args:
            room_id: Room ID
            message: Zu sendende Nachricht
            exclude_sender: Optional User ID der ausgeschlossen werden soll

        Returns:
            Anzahl der erfolgreichen Sendungen
        """
        async with self._lock:
            if room_id not in self._rooms:
                return 0
            member_ids = self._rooms[room_id].members.copy()

        if exclude_sender:
            member_ids.discard(exclude_sender)

        sent_count = 0
        for user_id in member_ids:
            if await self._send_to_user(user_id, message):
                sent_count += 1

        return sent_count

    async def _handle_presence_update(self, user_id: str, message: Dict[str, Any]) -> None:
        """Verarbeitet Presence-Update-Nachricht."""
        document_id = message.get("document_id")
        status = message.get("status", "online")

        await self.update_presence(
            user_id=user_id,
            document_id=document_id,
            status=status,
        )

        await self._send_to_user(
            user_id=user_id,
            message=WSMessage(
                type="presence_updated",
                payload={
                    "document_id": document_id,
                    "status": status,
                },
            ),
        )

    async def _handle_cursor_move(self, user_id: str, message: Dict[str, Any]) -> None:
        """Verarbeitet Cursor-Move-Nachricht."""
        document_id = message.get("document_id")
        cursor_position = message.get("cursor_position")

        if not document_id or not cursor_position:
            return

        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].cursor_position = cursor_position

        # Broadcast to other viewers of same document
        await self.broadcast_to_room(
            room_id=f"doc:{document_id}",
            message=WSMessage(
                type="cursor_moved",
                payload={
                    "user_id": user_id,
                    "document_id": document_id,
                    "cursor_position": cursor_position,
                },
            ),
            exclude_sender=user_id,
        )

    async def _handle_join_room(self, user_id: str, room_id: Optional[str]) -> None:
        """Verarbeitet Join-Room-Nachricht."""
        if not room_id:
            await self._send_to_user(
                user_id=user_id,
                message=WSMessage(
                    type="error",
                    payload={"message": "Room ID fehlt"},
                ),
            )
            return

        await self.join_room(user_id, room_id)

    async def _handle_leave_room(self, user_id: str, room_id: Optional[str]) -> None:
        """Verarbeitet Leave-Room-Nachricht."""
        if not room_id:
            await self._send_to_user(
                user_id=user_id,
                message=WSMessage(
                    type="error",
                    payload={"message": "Room ID fehlt"},
                ),
            )
            return

        await self.leave_room(user_id, room_id)

    async def _ping_loop(self) -> None:
        """Periodischer Ping an alle Verbindungen."""
        while True:
            try:
                await asyncio.sleep(self.PING_INTERVAL_SECONDS)

                now = datetime.now(timezone.utc)
                disconnected_users: List[str] = []

                async with self._lock:
                    for user_id, connection in self._connections.items():
                        # Check for stale connections
                        time_since_ping = (now - connection.last_ping).total_seconds()
                        if time_since_ping > self.PING_INTERVAL_SECONDS + self.PING_TIMEOUT_SECONDS:
                            disconnected_users.append(user_id)
                            continue

                        # Send ping
                        try:
                            await connection.websocket.send_text(
                                WSMessage(
                                    type="ping",
                                    payload={"server_time": now.isoformat()},
                                ).to_json()
                            )
                        except Exception as e:
                            logger.debug("ping_send_failed", error_type=type(e).__name__)
                            disconnected_users.append(user_id)

                # Cleanup disconnected users
                for user_id in disconnected_users:
                    await self.disconnect(user_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ping_loop_error", **safe_error_log(e))

    def get_stats(self) -> Dict[str, Any]:
        """Gibt Statistiken über Verbindungen zurück."""
        return {
            "total_connections": len(self._connections),
            "companies": len(self._company_users),
            "users_per_company": {
                company_id: len(users)
                for company_id, users in self._company_users.items()
            },
        }


# Singleton Instance
_ws_manager_instance: Optional[RealtimeWebSocketManager] = None


def get_realtime_ws_manager() -> RealtimeWebSocketManager:
    """Factory-Funktion für RealtimeWebSocketManager Singleton."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = RealtimeWebSocketManager()
    return _ws_manager_instance


async def reset_realtime_ws_manager() -> None:
    """Setzt den WebSocket Manager zurück (für Tests)."""
    global _ws_manager_instance
    if _ws_manager_instance:
        await _ws_manager_instance.stop()
        _ws_manager_instance = None
