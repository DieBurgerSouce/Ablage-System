# -*- coding: utf-8 -*-
"""
Unit Tests fuer ChatWebSocketManager.

Testet WebSocket-Verbindungsverwaltung:
- Connect/Disconnect
- Broadcast-Funktionalitaet
- Typing-Indikatoren
- Presence-Updates
- AI-Streaming
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.websocket_manager import (
    ChatWebSocketManager,
    ConnectionInfo,
    WSMessageType,
    get_websocket_manager,
)


class TestWSMessageType:
    """Tests fuer WebSocket Nachrichten-Typen."""

    def test_all_message_types_defined(self) -> None:
        """Alle erwarteten Nachrichten-Typen sind definiert."""
        # Note: Enum-Namen unterscheiden sich von Werten
        # z.B. PRESENCE_UPDATE hat Wert "presence"
        expected_types = [
            "NEW_MESSAGE",
            "MESSAGE_UPDATED",
            "TYPING_START",
            "TYPING_STOP",
            "PRESENCE_UPDATE",  # Enum-Name ist PRESENCE_UPDATE, nicht PRESENCE
            "USER_JOINED",
            "USER_LEFT",
            "AI_STREAMING",
            "AI_CHUNK",
            "AI_DONE",
            "ERROR",
        ]

        for msg_type in expected_types:
            assert hasattr(WSMessageType, msg_type), f"Missing: {msg_type}"

    def test_message_types_are_strings(self) -> None:
        """Nachrichten-Typen sind Strings."""
        assert WSMessageType.NEW_MESSAGE.value == "new_message"
        assert WSMessageType.TYPING_START.value == "typing_start"
        assert isinstance(WSMessageType.AI_CHUNK.value, str)


class TestConnectionInfo:
    """Tests fuer ConnectionInfo."""

    def test_connection_info_creation(self) -> None:
        """ConnectionInfo kann erstellt werden."""
        mock_ws = AsyncMock()
        conn = ConnectionInfo(
            websocket=mock_ws,
            user_id="user-123",
            username="TestUser",
            session_id="session-456",
        )

        assert conn.websocket is mock_ws
        assert conn.user_id == "user-123"
        assert conn.username == "TestUser"
        assert conn.session_id == "session-456"
        assert conn.is_typing is False
        assert conn.connected_at is not None
        assert conn.last_activity is not None


class TestChatWebSocketManager:
    """Tests fuer ChatWebSocketManager."""

    @pytest.fixture
    def manager(self) -> ChatWebSocketManager:
        """Erstellt einen frischen WebSocket Manager."""
        return ChatWebSocketManager()

    @pytest.fixture
    def mock_websocket(self) -> AsyncMock:
        """Erstellt einen Mock-WebSocket."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        return ws

    # =========================================================================
    # CONNECT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_connect_new_user(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Neuer User kann sich verbinden."""
        result = await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        assert result is True
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_creates_session(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Verbindung erstellt Session wenn noetig."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="new-session",
            user_id="user-1",
            username="TestUser",
        )

        assert "new-session" in manager._connections
        assert "user-1" in manager._connections["new-session"]

    @pytest.mark.asyncio
    async def test_connect_replaces_existing_connection(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Alte Verbindung wird geschlossen bei Neuverbindung."""
        old_ws = AsyncMock()
        old_ws.accept = AsyncMock()
        old_ws.close = AsyncMock()

        new_ws = AsyncMock()
        new_ws.accept = AsyncMock()

        # Erste Verbindung
        await manager.connect(
            websocket=old_ws,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        # Zweite Verbindung desselben Users
        await manager.connect(
            websocket=new_ws,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        old_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_tracks_user_sessions(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """User-Sessions werden getrackt."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        assert "user-1" in manager._user_sessions
        assert "session-1" in manager._user_sessions["user-1"]

    @pytest.mark.asyncio
    async def test_connect_user_in_multiple_sessions(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """User kann in mehreren Sessions sein."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await manager.connect(
            websocket=ws1,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )
        await manager.connect(
            websocket=ws2,
            session_id="session-2",
            user_id="user-1",
            username="TestUser",
        )

        assert "session-1" in manager._user_sessions["user-1"]
        assert "session-2" in manager._user_sessions["user-1"]

    # =========================================================================
    # DISCONNECT TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_disconnect_user(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """User kann sich trennen."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        await manager.disconnect(
            session_id="session-1",
            user_id="user-1",
        )

        assert "user-1" not in manager._connections.get("session-1", {})

    @pytest.mark.asyncio
    async def test_disconnect_removes_empty_session(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Leere Session wird entfernt."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        await manager.disconnect(
            session_id="session-1",
            user_id="user-1",
        )

        assert "session-1" not in manager._connections

    @pytest.mark.asyncio
    async def test_disconnect_updates_user_sessions(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """User-Sessions werden aktualisiert."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="TestUser",
        )

        await manager.disconnect(
            session_id="session-1",
            user_id="user-1",
        )

        assert "user-1" not in manager._user_sessions

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_user(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Disconnect eines nicht existierenden Users verursacht keinen Fehler."""
        # Sollte keinen Fehler werfen
        await manager.disconnect(
            session_id="nonexistent-session",
            user_id="nonexistent-user",
        )

    # =========================================================================
    # BROADCAST TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_broadcast_to_session(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Nachricht wird an alle in Session gesendet."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(
            websocket=ws1,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )
        await manager.connect(
            websocket=ws2,
            session_id="session-1",
            user_id="user-2",
            username="User2",
        )

        message = {"type": "test", "content": "Hello"}
        await manager.broadcast_to_session(
            session_id="session-1",
            message=message,
        )

        ws1.send_json.assert_called()
        ws2.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_broadcast_exclude_user(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """User kann von Broadcast ausgeschlossen werden."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(
            websocket=ws1,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )
        await manager.connect(
            websocket=ws2,
            session_id="session-1",
            user_id="user-2",
            username="User2",
        )

        # Reset mock call counts after connect (which sends presence updates)
        ws1.send_json.reset_mock()
        ws2.send_json.reset_mock()

        message = {"type": "test", "content": "Hello"}
        await manager.broadcast_to_session(
            session_id="session-1",
            message=message,
            exclude_user="user-1",
        )

        # ws1 sollte nur die Testmessage NICHT erhalten haben
        ws1_calls = ws1.send_json.call_args_list
        ws2_calls = ws2.send_json.call_args_list

        # ws1 sollte keine Testmessage haben
        for call in ws1_calls:
            assert call[0][0].get("type") != "test"

        # ws2 sollte die Testmessage erhalten haben
        assert any(call[0][0].get("type") == "test" for call in ws2_calls)

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_session(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Broadcast zu nicht existierender Session verursacht keinen Fehler."""
        await manager.broadcast_to_session(
            session_id="nonexistent",
            message={"type": "test"},
        )

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_error(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Fehler beim Senden werden behandelt."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        await manager.connect(
            websocket=ws,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        # Sollte keinen Fehler werfen
        await manager.broadcast_to_session(
            session_id="session-1",
            message={"type": "test"},
        )

    # =========================================================================
    # SEND TO USER TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_send_to_user(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Nachricht an spezifischen User senden."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        message = {"type": "private", "content": "Hello"}
        result = await manager.send_to_user(
            session_id="session-1",
            user_id="user-1",
            message=message,
        )

        assert result is True
        mock_websocket.send_json.assert_called_with(message)

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_user(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Senden an nicht existierenden User gibt False zurueck."""
        result = await manager.send_to_user(
            session_id="session-1",
            user_id="nonexistent",
            message={"type": "test"},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_user_handles_error(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Fehler beim Senden an User wird behandelt."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock(side_effect=Exception("Error"))

        await manager.connect(
            websocket=ws,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        result = await manager.send_to_user(
            session_id="session-1",
            user_id="user-1",
            message={"type": "test"},
        )

        assert result is False

    # =========================================================================
    # TYPING INDICATOR TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_set_typing_true(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Typing-Status auf True setzen."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        await manager.set_typing(
            session_id="session-1",
            user_id="user-1",
            is_typing=True,
        )

        conn = manager._connections["session-1"]["user-1"]
        assert conn.is_typing is True

    @pytest.mark.asyncio
    async def test_set_typing_false(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Typing-Status auf False setzen."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        await manager.set_typing(
            session_id="session-1",
            user_id="user-1",
            is_typing=True,
        )
        await manager.set_typing(
            session_id="session-1",
            user_id="user-1",
            is_typing=False,
        )

        conn = manager._connections["session-1"]["user-1"]
        assert conn.is_typing is False

    @pytest.mark.asyncio
    async def test_set_typing_updates_last_activity(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Typing-Aenderung aktualisiert last_activity."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        conn = manager._connections["session-1"]["user-1"]
        old_activity = conn.last_activity

        # Kurze Pause um Zeitunterschied sicherzustellen
        await asyncio.sleep(0.01)

        await manager.set_typing(
            session_id="session-1",
            user_id="user-1",
            is_typing=True,
        )

        assert conn.last_activity >= old_activity

    # =========================================================================
    # AI STREAMING TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_broadcast_ai_chunk(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """AI-Chunk wird gebroadcastet."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        await manager.broadcast_ai_chunk(
            session_id="session-1",
            chunk="Hello ",
            message_id="msg-1",
        )

        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == WSMessageType.AI_CHUNK.value
        assert call_args["chunk"] == "Hello "

    @pytest.mark.asyncio
    async def test_broadcast_ai_done(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """AI-Done wird gebroadcastet."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        await manager.broadcast_ai_done(
            session_id="session-1",
            message_id="msg-1",
            full_content="Hello World",
        )

        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == WSMessageType.AI_DONE.value
        assert call_args["full_content"] == "Hello World"

    # =========================================================================
    # MESSAGE BROADCAST TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_broadcast_new_message(
        self,
        manager: ChatWebSocketManager,
        mock_websocket: AsyncMock,
    ) -> None:
        """Neue Chat-Nachricht wird gebroadcastet."""
        await manager.connect(
            websocket=mock_websocket,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )

        await manager.broadcast_new_message(
            session_id="session-1",
            message_id="msg-1",
            user_id="user-2",
            username="User2",
            content="Hello!",
            role="user",
            created_at="2024-01-15T10:00:00Z",
        )

        mock_websocket.send_json.assert_called()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == WSMessageType.NEW_MESSAGE.value
        assert call_args["message"]["content"] == "Hello!"

    # =========================================================================
    # PRESENCE TESTS
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_online_users(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Online-User abrufen."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await manager.connect(
            websocket=ws1,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )
        await manager.connect(
            websocket=ws2,
            session_id="session-1",
            user_id="user-2",
            username="User2",
        )

        users = manager.get_online_users("session-1")

        assert len(users) == 2
        user_ids = [u["user_id"] for u in users]
        assert "user-1" in user_ids
        assert "user-2" in user_ids

    def test_get_online_users_empty_session(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Leere Session gibt leere Liste zurueck."""
        users = manager.get_online_users("nonexistent")
        assert users == []

    @pytest.mark.asyncio
    async def test_get_connection_count(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Verbindungsanzahl abrufen."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await manager.connect(
            websocket=ws1,
            session_id="session-1",
            user_id="user-1",
            username="User1",
        )
        await manager.connect(
            websocket=ws2,
            session_id="session-1",
            user_id="user-2",
            username="User2",
        )

        count = manager.get_connection_count("session-1")
        assert count == 2

    def test_get_connection_count_empty(
        self,
        manager: ChatWebSocketManager,
    ) -> None:
        """Leere Session hat 0 Verbindungen."""
        count = manager.get_connection_count("nonexistent")
        assert count == 0


class TestGetWebSocketManagerSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self) -> None:
        """Singleton gibt immer dieselbe Instanz zurueck."""
        manager1 = get_websocket_manager()
        manager2 = get_websocket_manager()

        assert manager1 is manager2
