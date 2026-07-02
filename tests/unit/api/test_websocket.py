# -*- coding: utf-8 -*-
"""
Unit Tests fuer WebSocket API Endpoints.

Testet:
- WS  /ws/realtime (WebSocket-Verbindung mit Token-Auth)
- GET /ws/stats (WebSocket-Statistiken)
- GET /ws/event-types (Verfuegbare Event-Typen)
- GET /ws/presence/{document_id} (Dokument-Presence)
- GET /ws/presence/company/{company_id} (Company-Presence)
- GET /ws/rooms (User-Rooms)
"""

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_ws_manager():
    """Mock RealtimeWSManager."""
    manager = MagicMock()
    manager.connect = AsyncMock(return_value=True)
    manager.disconnect = AsyncMock()
    manager.handle_message = AsyncMock()
    manager.get_stats.return_value = {
        "active_connections": 5,
        "total_rooms": 3,
        "messages_sent": 1234,
    }
    manager.get_document_viewers = AsyncMock(return_value=[
        {"user_id": str(uuid4()), "connected_at": "2026-01-01T00:00:00Z"}
    ])
    manager.get_company_presence = AsyncMock(return_value=[
        {"user_id": str(uuid4()), "status": "online"}
    ])
    manager._lock = AsyncMock()
    manager._rooms = {}
    return manager


@pytest.fixture
def valid_user_payload():
    """Gueltiges User-Payload aus Token."""
    return {
        "id": str(uuid4()),
        "email": "ws-user@ablage.local",
        "company_id": str(uuid4()),
    }


@pytest.fixture
def fake_request():
    """Minimaler Request-Stub fuer den G03-Cookie-Fallback.

    Die Presence-/Rooms-Endpunkte lesen seit dem Cookie-Auth-Umbau (Commit
    13d6aeff7) `request.cookies.get("access_token")`. Der Stub liefert ein
    leeres Cookie-Dict, damit der Fallback greift, ohne einen echten Token
    zu setzen. Nur `.cookies.get()` wird vom Endpoint benoetigt.
    """
    return SimpleNamespace(cookies={})


# =============================================================================
# Token Validation Tests
# =============================================================================


class TestGetUserFromToken:
    """Tests fuer JWT Token-Validierung im WebSocket-Kontext."""

    @pytest.mark.asyncio
    async def test_valid_token(self):
        """Gueltiges Token gibt User-Dict zurueck."""
        with patch("app.api.v1.websocket.jwt") as mock_jwt, \
             patch("app.api.v1.websocket.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            mock_settings.JWT_ALGORITHM = "HS256"
            mock_jwt.decode.return_value = {
                "sub": "user-123",
                "email": "test@ablage.local",
                "company_id": "comp-456",
            }
            mock_jwt.ExpiredSignatureError = Exception
            mock_jwt.InvalidTokenError = Exception

            from app.api.v1.websocket import get_user_from_token

            result = await get_user_from_token("valid-token")

            assert result is not None
            assert result["id"] == "user-123"
            assert result["email"] == "test@ablage.local"
            assert result["company_id"] == "comp-456"

    @pytest.mark.asyncio
    async def test_expired_token(self):
        """Abgelaufenes Token gibt None zurueck."""
        import jwt as real_jwt

        with patch("app.api.v1.websocket.jwt") as mock_jwt, \
             patch("app.api.v1.websocket.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            mock_settings.JWT_ALGORITHM = "HS256"
            mock_jwt.ExpiredSignatureError = real_jwt.ExpiredSignatureError
            mock_jwt.InvalidTokenError = real_jwt.InvalidTokenError
            mock_jwt.decode.side_effect = real_jwt.ExpiredSignatureError("Token expired")

            from app.api.v1.websocket import get_user_from_token

            result = await get_user_from_token("expired-token")
            assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Ungueltiges Token gibt None zurueck."""
        import jwt as real_jwt

        with patch("app.api.v1.websocket.jwt") as mock_jwt, \
             patch("app.api.v1.websocket.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            mock_settings.JWT_ALGORITHM = "HS256"
            mock_jwt.ExpiredSignatureError = real_jwt.ExpiredSignatureError
            mock_jwt.InvalidTokenError = real_jwt.InvalidTokenError
            mock_jwt.decode.side_effect = real_jwt.InvalidTokenError("Invalid token")

            from app.api.v1.websocket import get_user_from_token

            result = await get_user_from_token("invalid-token")
            assert result is None


# =============================================================================
# WebSocket Stats Tests
# =============================================================================


class TestWebSocketStats:
    """Tests fuer GET /ws/stats."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, mock_ws_manager):
        """Statistiken werden korrekt zurueckgegeben."""
        with patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ):
            from app.api.v1.websocket import get_websocket_stats

            result = await get_websocket_stats()

            assert result["active_connections"] == 5
            assert result["total_rooms"] == 3
            assert result["messages_sent"] == 1234


# =============================================================================
# Event Types Tests
# =============================================================================


class TestEventTypes:
    """Tests fuer GET /ws/event-types."""

    @pytest.mark.asyncio
    async def test_get_event_types_success(self):
        """Verfuegbare Event-Typen werden zurueckgegeben."""
        from app.api.v1.websocket import get_event_types

        result = await get_event_types()

        assert "event_types" in result
        assert "categories" in result
        assert isinstance(result["event_types"], list)
        assert len(result["event_types"]) > 0

        # Jeder Event-Typ hat type, category, name
        for event_type in result["event_types"]:
            assert "type" in event_type
            assert "category" in event_type
            assert "name" in event_type

    @pytest.mark.asyncio
    async def test_event_types_contain_document_events(self):
        """Document-Events sind enthalten."""
        from app.api.v1.websocket import get_event_types

        result = await get_event_types()

        assert "document" in result["categories"]

    @pytest.mark.asyncio
    async def test_event_types_categories_are_strings(self):
        """Kategorien sind Strings."""
        from app.api.v1.websocket import get_event_types

        result = await get_event_types()

        for cat in result["categories"]:
            assert isinstance(cat, str)


# =============================================================================
# Presence Tests
# =============================================================================


class TestDocumentPresence:
    """Tests fuer GET /ws/presence/{document_id}."""

    @pytest.mark.asyncio
    async def test_get_document_presence_success(self, mock_ws_manager, valid_user_payload, fake_request):
        """Dokument-Presence wird zurueckgegeben."""
        with patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ), patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ):
            from app.api.v1.websocket import get_document_presence

            result = await get_document_presence(
                request=fake_request,
                document_id="doc-123",
                token="valid-token",
            )

            assert result["document_id"] == "doc-123"
            assert result["viewer_count"] == 1
            assert len(result["viewers"]) == 1

    @pytest.mark.asyncio
    async def test_get_document_presence_no_token(self, fake_request):
        """401 ohne Token."""
        from fastapi import HTTPException
        from app.api.v1.websocket import get_document_presence

        with pytest.raises(HTTPException) as exc_info:
            await get_document_presence(
                request=fake_request,
                document_id="doc-123",
                token=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_document_presence_invalid_token(self, fake_request):
        """401 mit ungueltigem Token."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from app.api.v1.websocket import get_document_presence

            with pytest.raises(HTTPException) as exc_info:
                await get_document_presence(
                    request=fake_request,
                    document_id="doc-123",
                    token="invalid-token",
                )
            assert exc_info.value.status_code == 401


class TestCompanyPresence:
    """Tests fuer GET /ws/presence/company/{company_id}."""

    @pytest.mark.asyncio
    async def test_get_company_presence_success(self, mock_ws_manager, valid_user_payload, fake_request):
        """Company-Presence wird zurueckgegeben."""
        company_id = valid_user_payload["company_id"]

        with patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ), patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ):
            from app.api.v1.websocket import get_company_presence_endpoint

            result = await get_company_presence_endpoint(
                request=fake_request,
                company_id=company_id,
                token="valid-token",
            )

            assert result["company_id"] == company_id
            assert result["online_count"] == 1

    @pytest.mark.asyncio
    async def test_get_company_presence_wrong_company(self, valid_user_payload, fake_request):
        """403 wenn User nicht zur Company gehoert."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ):
            from app.api.v1.websocket import get_company_presence_endpoint

            with pytest.raises(HTTPException) as exc_info:
                await get_company_presence_endpoint(
                    request=fake_request,
                    company_id="other-company-id",
                    token="valid-token",
                )
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_company_presence_no_token(self, fake_request):
        """401 ohne Token."""
        from fastapi import HTTPException
        from app.api.v1.websocket import get_company_presence_endpoint

        with pytest.raises(HTTPException) as exc_info:
            await get_company_presence_endpoint(
                request=fake_request,
                company_id="comp-123",
                token=None,
            )
        assert exc_info.value.status_code == 401


# =============================================================================
# Rooms Tests
# =============================================================================


class TestUserRooms:
    """Tests fuer GET /ws/rooms."""

    @pytest.mark.asyncio
    async def test_get_rooms_success(self, mock_ws_manager, valid_user_payload, fake_request):
        """User-Rooms werden zurueckgegeben."""
        with patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ), patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ):
            from app.api.v1.websocket import get_user_rooms

            result = await get_user_rooms(request=fake_request, token="valid-token")

            assert result["user_id"] == valid_user_payload["id"]
            assert result["room_count"] == 0
            assert result["rooms"] == []

    @pytest.mark.asyncio
    async def test_get_rooms_no_token(self, fake_request):
        """401 ohne Token."""
        from fastapi import HTTPException
        from app.api.v1.websocket import get_user_rooms

        with pytest.raises(HTTPException) as exc_info:
            await get_user_rooms(request=fake_request, token=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_rooms_invalid_token(self, fake_request):
        """401 mit ungueltigem Token."""
        from fastapi import HTTPException

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from app.api.v1.websocket import get_user_rooms

            with pytest.raises(HTTPException) as exc_info:
                await get_user_rooms(request=fake_request, token="invalid-token")
            assert exc_info.value.status_code == 401


# =============================================================================
# WebSocket Endpoint Tests
# =============================================================================


class TestWebSocketRealtimeEndpoint:
    """Tests fuer WS /ws/realtime."""

    @pytest.mark.asyncio
    async def test_websocket_no_token_closes(self):
        """WebSocket wird ohne Token geschlossen (code 4001)."""
        mock_ws = AsyncMock()
        # G03: websocket_realtime_endpoint faellt auf
        # `websocket.cookies.get("access_token")` zurueck. Ein blanker AsyncMock
        # liefert dort ein truthy Mock-Objekt -> der 4001-Pfad wuerde
        # uebersprungen. Ein echtes leeres Dict liefert None und haelt den Test
        # ehrlich. Die anderen WS-Tests uebergeben truthy Tokens, sodass der
        # `or`-Fallback dort gar nicht ausgewertet wird (kein Fix noetig).
        mock_ws.cookies = {}

        with patch(
            "app.api.v1.websocket.get_realtime_ws_manager"
        ):
            from app.api.v1.websocket import websocket_realtime_endpoint

            await websocket_realtime_endpoint(
                websocket=mock_ws,
                token=None,
            )

            mock_ws.close.assert_awaited_once_with(
                code=4001, reason="Token erforderlich"
            )

    @pytest.mark.asyncio
    async def test_websocket_invalid_token_closes(self):
        """WebSocket wird mit ungueltigem Token geschlossen (code 4002)."""
        mock_ws = AsyncMock()

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.api.v1.websocket.get_realtime_ws_manager"
        ):
            from app.api.v1.websocket import websocket_realtime_endpoint

            await websocket_realtime_endpoint(
                websocket=mock_ws,
                token="invalid",
            )

            mock_ws.close.assert_awaited_once_with(
                code=4002, reason="Ung\u00fcltiges Token"
            )

    @pytest.mark.asyncio
    async def test_websocket_connection_failed_closes(self, mock_ws_manager, valid_user_payload):
        """WebSocket wird geschlossen wenn connect fehlschlaegt (code 4003)."""
        mock_ws = AsyncMock()
        mock_ws_manager.connect = AsyncMock(return_value=False)

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ), patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ):
            from app.api.v1.websocket import websocket_realtime_endpoint

            await websocket_realtime_endpoint(
                websocket=mock_ws,
                token="valid-token",
            )

            mock_ws.close.assert_awaited_once_with(
                code=4003, reason="Verbindung fehlgeschlagen"
            )

    @pytest.mark.asyncio
    async def test_websocket_disconnect_cleanup(self, mock_ws_manager, valid_user_payload):
        """Disconnect raeumt Verbindung auf."""
        from fastapi import WebSocketDisconnect

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        mock_ws_manager.connect = AsyncMock(return_value=True)

        with patch(
            "app.api.v1.websocket.get_user_from_token",
            new_callable=AsyncMock,
            return_value=valid_user_payload,
        ), patch(
            "app.api.v1.websocket.get_realtime_ws_manager",
            return_value=mock_ws_manager,
        ):
            from app.api.v1.websocket import websocket_realtime_endpoint

            await websocket_realtime_endpoint(
                websocket=mock_ws,
                token="valid-token",
            )

            mock_ws_manager.disconnect.assert_awaited_once_with(
                valid_user_payload["id"]
            )
