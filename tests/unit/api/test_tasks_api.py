# -*- coding: utf-8 -*-
"""
Unit-Tests für Tasks API Endpoints.

Testet:
- Task Status Endpoints (REST)
- Task Cancellation
- User Task Listing
- Task Result Retrieval
- WebSocket Connection Manager
- WebSocket Progress Updates

Feinpoliert und durchdacht - Task-Management API Tests.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Set
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_task_service():
    """Create mock task service."""
    service = Mock()
    service.get_task_status = Mock(return_value={
        "state": "STARTED",
        "ready": False,
        "successful": False,
        "progress": 50,
        "message": "Verarbeitung laeuft",
    })
    service.cancel_task = Mock(return_value={
        "cancelled": True,
        "message": "Task wurde abgebrochen",
    })
    service.get_user_tasks = AsyncMock(return_value=[
        {"task_id": "task-1", "state": "SUCCESS"},
        {"task_id": "task-2", "state": "PENDING"},
    ])
    service.get_task_result = Mock(return_value={"text": "Extrahierter Text"})
    return service


@pytest.fixture
def mock_current_user():
    """Create mock authenticated user."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ========================= Task Status Tests =========================


class TestGetTaskStatus:
    """Tests for GET /tasks/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_task_status_success(self, mock_task_service, mock_current_user):
        """Sollte Task-Status zurueckgeben."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_status

            result = await get_task_status("task-123", mock_current_user)

            assert result["state"] == "STARTED"
            assert result["progress"] == 50
            mock_task_service.get_task_status.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_get_task_status_error(self, mock_task_service, mock_current_user):
        """Sollte HTTPException bei Fehler werfen."""
        mock_task_service.get_task_status.side_effect = Exception("Service error")

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_status

            with pytest.raises(HTTPException) as exc_info:
                await get_task_status("task-123", mock_current_user)

            assert exc_info.value.status_code == 500


# ========================= Task Cancellation Tests =========================


class TestCancelTask:
    """Tests for DELETE /tasks/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, mock_task_service, mock_current_user):
        """Sollte Task erfolgreich abbrechen."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import cancel_task

            result = await cancel_task("task-123", mock_current_user)

            assert isinstance(result, JSONResponse)
            assert result.status_code == 200
            mock_task_service.cancel_task.assert_called_once_with("task-123")

    @pytest.mark.asyncio
    async def test_cancel_task_failed(self, mock_task_service, mock_current_user):
        """Sollte 400 zurueckgeben wenn Abbruch fehlschlaegt."""
        mock_task_service.cancel_task.return_value = {
            "cancelled": False,
            "message": "Task bereits abgeschlossen",
        }

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import cancel_task

            result = await cancel_task("task-123", mock_current_user)

            assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_cancel_task_error(self, mock_task_service, mock_current_user):
        """Sollte HTTPException bei Fehler werfen."""
        mock_task_service.cancel_task.side_effect = Exception("Service error")

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import cancel_task

            with pytest.raises(HTTPException) as exc_info:
                await cancel_task("task-123", mock_current_user)

            assert exc_info.value.status_code == 500


# ========================= User Tasks List Tests =========================


class TestListUserTasks:
    """Tests for GET /tasks/ endpoint."""

    @pytest.mark.asyncio
    async def test_list_user_tasks_success(self, mock_task_service, mock_current_user, mock_db_session):
        """Sollte Benutzer-Tasks auflisten."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import list_user_tasks

            result = await list_user_tasks(
                limit=10,
                current_user=mock_current_user,
                session=mock_db_session
            )

            assert str(result["user_id"]) == str(mock_current_user.id)
            assert result["total"] == 2
            assert len(result["tasks"]) == 2
            mock_task_service.get_user_tasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_user_tasks_empty(self, mock_task_service, mock_current_user, mock_db_session):
        """Sollte leere Liste zurueckgeben."""
        mock_task_service.get_user_tasks.return_value = []

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import list_user_tasks

            result = await list_user_tasks(
                limit=10,
                current_user=mock_current_user,
                session=mock_db_session
            )

            assert result["total"] == 0
            assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_list_user_tasks_error(self, mock_task_service, mock_current_user, mock_db_session):
        """Sollte HTTPException bei Fehler werfen."""
        mock_task_service.get_user_tasks.side_effect = Exception("DB error")

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import list_user_tasks

            with pytest.raises(HTTPException) as exc_info:
                await list_user_tasks(
                    limit=10,
                    current_user=mock_current_user,
                    session=mock_db_session
                )

            assert exc_info.value.status_code == 500


# ========================= Task Result Tests =========================


class TestGetTaskResult:
    """Tests for GET /tasks/{task_id}/result endpoint."""

    @pytest.mark.asyncio
    async def test_get_task_result_success(self, mock_task_service, mock_current_user):
        """Sollte Task-Ergebnis zurueckgeben."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_result

            result = await get_task_result(
                task_id="task-123",
                timeout=None,
                current_user=mock_current_user
            )

            assert result["task_id"] == "task-123"
            assert "result" in result
            mock_task_service.get_task_result.assert_called_once_with("task-123", timeout=None)

    @pytest.mark.asyncio
    async def test_get_task_result_with_timeout(self, mock_task_service, mock_current_user):
        """Sollte Timeout-Parameter verwenden."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_result

            await get_task_result(
                task_id="task-123",
                timeout=30.0,
                current_user=mock_current_user
            )

            mock_task_service.get_task_result.assert_called_once_with("task-123", timeout=30.0)

    @pytest.mark.asyncio
    async def test_get_task_result_timeout_error(self, mock_task_service, mock_current_user):
        """Sollte 408 bei Timeout werfen."""
        mock_task_service.get_task_result.side_effect = TimeoutError()

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_result

            with pytest.raises(HTTPException) as exc_info:
                await get_task_result(
                    task_id="task-123",
                    timeout=5.0,
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 408

    @pytest.mark.asyncio
    async def test_get_task_result_value_error(self, mock_task_service, mock_current_user):
        """Sollte 400 bei ValueError werfen."""
        mock_task_service.get_task_result.side_effect = ValueError("Invalid task state")

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            from app.api.v1.tasks import get_task_result

            with pytest.raises(HTTPException) as exc_info:
                await get_task_result(
                    task_id="task-123",
                    timeout=None,
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 400


# ========================= WebSocket Connection Manager Tests =========================


class TestConnectionManager:
    """Tests for WebSocket ConnectionManager class."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_websocket):
        """Sollte WebSocket-Verbindung akzeptieren."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        result = await manager.connect("task-123", mock_websocket)

        assert result is True
        mock_websocket.accept.assert_called_once()
        assert "task-123" in manager.active_connections
        assert mock_websocket in manager.active_connections["task-123"]

    @pytest.mark.asyncio
    async def test_connect_error(self, mock_websocket):
        """Sollte False bei Verbindungsfehler zurueckgeben."""
        mock_websocket.accept.side_effect = Exception("Connection error")

        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        result = await manager.connect("task-123", mock_websocket)

        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_websocket):
        """Sollte WebSocket-Verbindung entfernen."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)
        await manager.disconnect("task-123", mock_websocket)

        assert "task-123" not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_one_of_multiple(self, mock_websocket):
        """Sollte nur eine Verbindung entfernen bei mehreren."""
        mock_websocket2 = AsyncMock(spec=WebSocket)
        mock_websocket2.accept = AsyncMock()

        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)
        await manager.connect("task-123", mock_websocket2)

        await manager.disconnect("task-123", mock_websocket)

        assert "task-123" in manager.active_connections
        assert mock_websocket2 in manager.active_connections["task-123"]
        assert mock_websocket not in manager.active_connections["task-123"]

    @pytest.mark.asyncio
    async def test_broadcast(self, mock_websocket):
        """Sollte Nachricht an alle Clients senden."""
        mock_websocket2 = AsyncMock(spec=WebSocket)
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()

        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)
        await manager.connect("task-123", mock_websocket2)

        await manager.broadcast("task-123", {"status": "update"})

        mock_websocket.send_json.assert_called_once_with({"status": "update"})
        mock_websocket2.send_json.assert_called_once_with({"status": "update"})

    @pytest.mark.asyncio
    async def test_broadcast_cleans_disconnected(self, mock_websocket):
        """Sollte getrennte Clients entfernen."""
        mock_websocket.send_json.side_effect = Exception("Disconnected")

        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)

        await manager.broadcast("task-123", {"status": "update"})

        # Disconnected client should be removed
        assert manager.get_connection_count("task-123") == 0

    @pytest.mark.asyncio
    async def test_send_update(self, mock_websocket):
        """Sollte Update an spezifischen Client senden."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)

        result = await manager.send_update("task-123", mock_websocket, {"progress": 75})

        assert result is True
        mock_websocket.send_json.assert_called_with({"progress": 75})

    @pytest.mark.asyncio
    async def test_send_update_error(self, mock_websocket):
        """Sollte False bei Sendefehler zurueckgeben."""
        mock_websocket.send_json.side_effect = Exception("Send error")

        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        await manager.connect("task-123", mock_websocket)

        result = await manager.send_update("task-123", mock_websocket, {"progress": 75})

        assert result is False

    def test_get_connection_count_specific_task(self, mock_websocket):
        """Sollte Verbindungsanzahl fuer Task zurueckgeben."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        manager.active_connections["task-123"] = {mock_websocket}

        count = manager.get_connection_count("task-123")

        assert count == 1

    def test_get_connection_count_all(self, mock_websocket):
        """Sollte Gesamtanzahl aller Verbindungen zurueckgeben."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()
        manager.active_connections["task-1"] = {mock_websocket}
        manager.active_connections["task-2"] = {Mock(), Mock()}

        count = manager.get_connection_count()

        assert count == 3

    def test_get_connection_count_unknown_task(self):
        """Sollte 0 fuer unbekannten Task zurueckgeben."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()

        count = manager.get_connection_count("unknown-task")

        assert count == 0


# ========================= WebSocket Status Tests =========================


class TestGetWebSocketStatus:
    """Tests for GET /tasks/ws/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_websocket_status(self):
        """Sollte WebSocket-Status zurueckgeben."""
        from app.api.v1.tasks import get_websocket_status, manager

        # Setup some connections
        manager.active_connections = {
            "task-1": {Mock()},
            "task-2": {Mock(), Mock()},
        }

        result = await get_websocket_status()

        assert result["total_connections"] == 3
        assert "task-1" in result["active_tasks"]
        assert "task-2" in result["active_tasks"]


# ========================= WebSocket Endpoint Tests =========================


class TestTaskProgressWebSocket:
    """Tests for WebSocket /tasks/ws/{task_id} endpoint."""

    @pytest.mark.asyncio
    async def test_websocket_initial_status_sent(self, mock_websocket, mock_task_service):
        """Sollte Initial-Status senden."""
        mock_task_service.get_task_status.return_value = {
            "state": "PENDING",
            "ready": False,
            "successful": False,
        }

        # Need to break the while loop
        call_count = [0]

        def get_status_side_effect(task_id):
            call_count[0] += 1
            if call_count[0] > 1:
                return {
                    "state": "SUCCESS",
                    "ready": True,
                    "successful": True,
                    "result": {"text": "Done"},
                }
            return {
                "state": "PENDING",
                "ready": False,
                "successful": False,
            }

        mock_task_service.get_task_status.side_effect = get_status_side_effect

        with patch('app.api.v1.tasks.task_service', mock_task_service):
            with patch('app.api.v1.tasks.manager') as mock_manager:
                mock_manager.connect = AsyncMock(return_value=True)
                mock_manager.send_update = AsyncMock(return_value=True)
                mock_manager.disconnect = AsyncMock()

                from app.api.v1.tasks import task_progress_websocket

                with patch('asyncio.sleep', new_callable=AsyncMock):
                    await task_progress_websocket(mock_websocket, "task-123")

                # Initial status should be sent
                assert mock_manager.send_update.call_count >= 2

    @pytest.mark.asyncio
    async def test_websocket_disconnect_handling(self, mock_websocket, mock_task_service):
        """Sollte Disconnect behandeln."""
        with patch('app.api.v1.tasks.task_service', mock_task_service):
            with patch('app.api.v1.tasks.manager') as mock_manager:
                mock_manager.connect = AsyncMock(return_value=True)
                mock_manager.send_update = AsyncMock(side_effect=WebSocketDisconnect())
                mock_manager.disconnect = AsyncMock()

                from app.api.v1.tasks import task_progress_websocket

                # Should not raise, just handle disconnect
                await task_progress_websocket(mock_websocket, "task-123")

                mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_connection_failed(self, mock_websocket, mock_task_service):
        """Sollte bei fehlgeschlagener Verbindung beenden."""
        with patch('app.api.v1.tasks.manager') as mock_manager:
            mock_manager.connect = AsyncMock(return_value=False)

            from app.api.v1.tasks import task_progress_websocket

            # Should return early without error
            await task_progress_websocket(mock_websocket, "task-123")

            mock_manager.disconnect.assert_not_called()


# ========================= Thread Safety Tests =========================


class TestConnectionManagerThreadSafety:
    """Tests for ConnectionManager thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_connects(self):
        """Sollte gleichzeitige Verbindungen sicher handhaben."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()

        async def connect_client(task_id: str, client_id: int):
            ws = AsyncMock(spec=WebSocket)
            ws.accept = AsyncMock()
            await manager.connect(task_id, ws)
            return ws

        # Concurrent connections to same task
        tasks = [connect_client("task-123", i) for i in range(10)]
        websockets = await asyncio.gather(*tasks)

        assert manager.get_connection_count("task-123") == 10

    @pytest.mark.asyncio
    async def test_concurrent_disconnects(self):
        """Sollte gleichzeitige Disconnects sicher handhaben."""
        from app.api.v1.tasks import ConnectionManager

        manager = ConnectionManager()

        # Setup connections
        websockets = []
        for i in range(10):
            ws = AsyncMock(spec=WebSocket)
            ws.accept = AsyncMock()
            await manager.connect("task-123", ws)
            websockets.append(ws)

        # Concurrent disconnections
        await asyncio.gather(*[
            manager.disconnect("task-123", ws)
            for ws in websockets
        ])

        assert manager.get_connection_count("task-123") == 0
