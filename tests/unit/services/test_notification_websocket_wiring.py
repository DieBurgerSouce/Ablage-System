"""Tests that NotificationService._send_websocket calls EventBroadcaster.emit_notification."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.notification_service import (
    NotificationChannel,
    NotificationService,
)


@pytest.mark.asyncio
async def test_send_websocket_calls_event_broadcaster():
    """Test that _send_websocket delegates to EventBroadcaster.emit_notification."""
    service = NotificationService()

    mock_broadcaster = MagicMock()
    mock_broadcaster.emit_notification = AsyncMock()

    rendered = {
        "subject": "Test-Betreff",
        "body": "Test-Inhalt",
    }
    results = {}

    with patch(
        "app.services.realtime.event_broadcaster.get_event_broadcaster",
        return_value=mock_broadcaster,
    ):
        await service._send_websocket(
            user_id="user-abc",
            notification_type="processing_completed",
            rendered=rendered,
            priority="high",
            results=results,
        )

    assert results[NotificationChannel.WEBSOCKET] is True
    mock_broadcaster.emit_notification.assert_called_once_with(
        user_id="user-abc",
        title="Test-Betreff",
        message="Test-Inhalt",
        priority="high",
        notification_type="processing_completed",
    )


@pytest.mark.asyncio
async def test_send_websocket_handles_broadcaster_error():
    """Test that _send_websocket catches exceptions and sets result to False."""
    service = NotificationService()

    mock_broadcaster = MagicMock()
    mock_broadcaster.emit_notification = AsyncMock(
        side_effect=RuntimeError("Verbindung fehlgeschlagen")
    )

    rendered = {
        "subject": "Test",
        "body": "Test",
    }
    results = {}

    with patch(
        "app.services.realtime.event_broadcaster.get_event_broadcaster",
        return_value=mock_broadcaster,
    ):
        await service._send_websocket(
            user_id="user-xyz",
            notification_type="system_alert",
            rendered=rendered,
            priority="normal",
            results=results,
        )

    assert results[NotificationChannel.WEBSOCKET] is False


@pytest.mark.asyncio
async def test_notify_always_adds_websocket_channel_for_user():
    """Test that notify() adds WEBSOCKET channel when user_id is present."""
    service = NotificationService()

    # Mock all channel senders to prevent actual execution
    service._send_email = AsyncMock()
    service._send_webhook = AsyncMock()
    service._store_in_app = AsyncMock()
    service._send_websocket = AsyncMock()

    await service.notify(
        notification_type="processing_completed",
        context={"document_id": "doc-1"},
        user_id="user-123",
    )

    # _send_websocket should have been called (WEBSOCKET channel added)
    service._send_websocket.assert_called_once()
    call_args = service._send_websocket.call_args
    assert call_args[0][0] == "user-123"
