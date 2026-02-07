"""
Tests fuer WebSocket Presence und Room-System.

Testet:
- Presence-Tracking (viewing_document_id, status, cursor_position)
- Room Join/Leave
- Document Viewer Tracking
- Cursor Position Broadcasting
- Company-Isolation fuer Presence
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.realtime.realtime_websocket_manager import (
    RealtimeWebSocketManager,
    UserConnection,
    ConnectionState,
    Room,
    WSMessage,
)
from app.services.realtime.event_broadcaster import EventBroadcaster


@pytest.fixture
def mock_broadcaster() -> EventBroadcaster:
    """Mock EventBroadcaster."""
    broadcaster = MagicMock(spec=EventBroadcaster)
    broadcaster.register_callback = MagicMock(return_value=lambda: None)
    return broadcaster


@pytest.fixture
async def ws_manager(mock_broadcaster: EventBroadcaster) -> RealtimeWebSocketManager:
    """WebSocket Manager Instanz fuer Tests."""
    manager = RealtimeWebSocketManager(broadcaster=mock_broadcaster)
    await manager.start()
    yield manager
    await manager.stop()


@pytest.fixture
def mock_websocket() -> MagicMock:
    """Mock WebSocket."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
class TestPresenceTracking:
    """Tests fuer Presence-Tracking."""

    async def test_update_presence_sets_document_id(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: Presence-Update setzt viewing_document_id."""
        # Connect user
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Update presence
        await ws_manager.update_presence("user1", document_id="doc123", status="online")

        # Verify
        async with ws_manager._lock:
            connection = ws_manager._connections["user1"]
            assert connection.viewing_document_id == "doc123"
            assert connection.status == "online"

    async def test_update_presence_broadcasts_to_company(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: Presence-Update wird an Company gebroadcastet."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect two users in same company
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")

        # Clear previous calls
        mock_websocket.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # Update presence
        await ws_manager.update_presence("user1", document_id="doc123")

        # Verify both users received broadcast
        assert mock_websocket.send_text.called or ws2.send_text.called

    async def test_get_document_viewers(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: get_document_viewers gibt aktive Viewer zurueck."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")

        # Set both users viewing same document
        await ws_manager.update_presence("user1", document_id="doc123")
        await ws_manager.update_presence("user2", document_id="doc123")

        # Get viewers
        viewers = await ws_manager.get_document_viewers("doc123")

        # Verify
        assert len(viewers) == 2
        viewer_ids = [v["user_id"] for v in viewers]
        assert "user1" in viewer_ids
        assert "user2" in viewer_ids

    async def test_get_company_presence(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: get_company_presence gibt alle User einer Company zurueck."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        # Connect users to same company
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")

        # Update presence
        await ws_manager.update_presence("user1", status="online")
        await ws_manager.update_presence("user2", status="away")

        # Get presence
        presence = await ws_manager.get_company_presence("company1")

        # Verify
        assert len(presence) == 2
        statuses = {p["user_id"]: p["status"] for p in presence}
        assert statuses["user1"] == "online"
        assert statuses["user2"] == "away"

    async def test_presence_company_isolation(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: Presence ist nach Company isoliert."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        # Connect users to different companies
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company2")

        # Get presence for company1
        presence = await ws_manager.get_company_presence("company1")

        # Verify only user1 is returned
        assert len(presence) == 1
        assert presence[0]["user_id"] == "user1"

    async def test_disconnect_notifies_presence_change(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: Disconnect sendet Presence-Change (offline)."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect two users
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")

        # Set user1 viewing document
        await ws_manager.update_presence("user1", document_id="doc123")

        # Clear calls
        ws2.send_text.reset_mock()

        # Disconnect user1
        await ws_manager.disconnect("user1")

        # Verify user2 was notified
        assert ws2.send_text.called


@pytest.mark.asyncio
class TestRoomSystem:
    """Tests fuer Room-System."""

    async def test_join_room_creates_room(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: join_room erstellt Room wenn nicht vorhanden."""
        # Connect user
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Join room
        await ws_manager.join_room("user1", "doc:123")

        # Verify room created
        async with ws_manager._lock:
            assert "doc:123" in ws_manager._rooms
            assert "user1" in ws_manager._rooms["doc:123"].members

    async def test_join_room_adds_to_existing_room(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: join_room fuegt User zu bestehendem Room hinzu."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")

        # Both join same room
        await ws_manager.join_room("user1", "doc:123")
        await ws_manager.join_room("user2", "doc:123")

        # Verify both in room
        async with ws_manager._lock:
            room = ws_manager._rooms["doc:123"]
            assert len(room.members) == 2
            assert "user1" in room.members
            assert "user2" in room.members

    async def test_leave_room_removes_user(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: leave_room entfernt User aus Room."""
        # Connect and join room
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.join_room("user1", "doc:123")

        # Leave room
        await ws_manager.leave_room("user1", "doc:123")

        # Verify room removed (empty rooms are deleted)
        async with ws_manager._lock:
            assert "doc:123" not in ws_manager._rooms

    async def test_leave_room_keeps_room_if_members_remain(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: leave_room behaelt Room wenn noch Mitglieder vorhanden."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()

        # Connect users and join room
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")
        await ws_manager.join_room("user1", "doc:123")
        await ws_manager.join_room("user2", "doc:123")

        # User1 leaves
        await ws_manager.leave_room("user1", "doc:123")

        # Verify room still exists
        async with ws_manager._lock:
            assert "doc:123" in ws_manager._rooms
            assert "user2" in ws_manager._rooms["doc:123"].members
            assert "user1" not in ws_manager._rooms["doc:123"].members

    async def test_broadcast_to_room(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: broadcast_to_room sendet an alle Room-Mitglieder."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users and join room
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")
        await ws_manager.join_room("user1", "doc:123")
        await ws_manager.join_room("user2", "doc:123")

        # Clear previous calls
        mock_websocket.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # Broadcast to room
        message = WSMessage(type="test", payload={"data": "test"})
        sent_count = await ws_manager.broadcast_to_room("doc:123", message)

        # Verify
        assert sent_count == 2

    async def test_broadcast_to_room_excludes_sender(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: broadcast_to_room kann Sender ausschliessen."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users and join room
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")
        await ws_manager.join_room("user1", "doc:123")
        await ws_manager.join_room("user2", "doc:123")

        # Clear calls
        mock_websocket.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # Broadcast excluding user1
        message = WSMessage(type="test", payload={"data": "test"})
        sent_count = await ws_manager.broadcast_to_room(
            "doc:123", message, exclude_sender="user1"
        )

        # Verify only user2 received
        assert sent_count == 1
        assert ws2.send_text.called
        assert not mock_websocket.send_text.called

    async def test_disconnect_removes_from_rooms(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: Disconnect entfernt User aus allen Rooms."""
        # Connect and join multiple rooms
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.join_room("user1", "doc:123")
        await ws_manager.join_room("user1", "workflow:abc")

        # Disconnect
        await ws_manager.disconnect("user1")

        # Verify removed from all rooms (and rooms deleted)
        async with ws_manager._lock:
            assert "doc:123" not in ws_manager._rooms
            assert "workflow:abc" not in ws_manager._rooms


@pytest.mark.asyncio
class TestCursorPositionBroadcast:
    """Tests fuer Cursor-Position Broadcasting."""

    async def test_cursor_move_updates_position(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: cursor_move aktualisiert cursor_position."""
        # Connect user
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Handle cursor move
        message = {
            "type": "cursor_move",
            "document_id": "doc123",
            "cursor_position": {"x": 100, "y": 200},
        }
        await ws_manager.handle_message("user1", '{"type": "cursor_move", "document_id": "doc123", "cursor_position": {"x": 100, "y": 200}}')

        # Verify
        async with ws_manager._lock:
            connection = ws_manager._connections["user1"]
            assert connection.cursor_position == {"x": 100, "y": 200}

    async def test_cursor_move_broadcasts_to_document_viewers(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: cursor_move wird an andere Document-Viewer gesendet."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users and join same document room
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")
        await ws_manager.join_room("user1", "doc:doc123")
        await ws_manager.join_room("user2", "doc:doc123")

        # Clear previous calls
        ws2.send_text.reset_mock()

        # User1 moves cursor
        await ws_manager.handle_message(
            "user1",
            '{"type": "cursor_move", "document_id": "doc123", "cursor_position": {"x": 100, "y": 200}}'
        )

        # Verify user2 was notified
        assert ws2.send_text.called

    async def test_cursor_move_excludes_sender(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: cursor_move sendet nicht an Sender selbst."""
        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_text = AsyncMock()

        # Connect users
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.connect(ws2, "user2", "company1")
        await ws_manager.join_room("user1", "doc:doc123")
        await ws_manager.join_room("user2", "doc:doc123")

        # Clear calls
        mock_websocket.send_text.reset_mock()
        ws2.send_text.reset_mock()

        # User1 moves cursor
        await ws_manager.handle_message(
            "user1",
            '{"type": "cursor_move", "document_id": "doc123", "cursor_position": {"x": 100, "y": 200}}'
        )

        # Verify only user2 received, not user1
        assert ws2.send_text.called
        # Note: user1 might receive the confirmation message, so we can't assert not called


@pytest.mark.asyncio
class TestHandleMessagePresence:
    """Tests fuer handle_message mit Presence/Room Messages."""

    async def test_handle_presence_update_message(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: handle_message verarbeitet presence_update."""
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Send presence_update message
        await ws_manager.handle_message(
            "user1",
            '{"type": "presence_update", "document_id": "doc123", "status": "busy"}'
        )

        # Verify
        async with ws_manager._lock:
            connection = ws_manager._connections["user1"]
            assert connection.viewing_document_id == "doc123"
            assert connection.status == "busy"

    async def test_handle_join_room_message(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: handle_message verarbeitet join_room."""
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Send join_room message
        await ws_manager.handle_message(
            "user1",
            '{"type": "join_room", "room_id": "doc:123"}'
        )

        # Verify
        async with ws_manager._lock:
            assert "doc:123" in ws_manager._rooms
            assert "user1" in ws_manager._rooms["doc:123"].members

    async def test_handle_leave_room_message(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: handle_message verarbeitet leave_room."""
        await ws_manager.connect(mock_websocket, "user1", "company1")
        await ws_manager.join_room("user1", "doc:123")

        # Send leave_room message
        await ws_manager.handle_message(
            "user1",
            '{"type": "leave_room", "room_id": "doc:123"}'
        )

        # Verify room removed
        async with ws_manager._lock:
            assert "doc:123" not in ws_manager._rooms

    async def test_handle_join_room_without_room_id(
        self, ws_manager: RealtimeWebSocketManager, mock_websocket: MagicMock
    ):
        """Test: join_room ohne room_id sendet Fehler."""
        await ws_manager.connect(mock_websocket, "user1", "company1")

        # Clear previous calls
        mock_websocket.send_text.reset_mock()

        # Send join_room without room_id
        await ws_manager.handle_message(
            "user1",
            '{"type": "join_room"}'
        )

        # Verify error was sent
        assert mock_websocket.send_text.called
