"""Tests fuer EventBroadcaster.emit_notification()."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.services.realtime.event_broadcaster import (
    EventBroadcaster,
    RealtimeEventType,
)


@pytest.mark.asyncio
async def test_emit_notification_creates_event():
    """Test that emit_notification broadcasts NOTIFICATION_RECEIVED event."""
    broadcaster = EventBroadcaster()

    received_events = []

    async def capture_callback(event):
        received_events.append(event)

    broadcaster.register_callback(capture_callback)

    await broadcaster.emit_notification(
        user_id="user-123",
        title="Test-Benachrichtigung",
        message="Dies ist ein Test",
        priority="high",
        notification_type="processing_completed",
    )

    assert len(received_events) == 1
    event = received_events[0]
    assert event.event_type == RealtimeEventType.NOTIFICATION_RECEIVED
    assert event.payload["title"] == "Test-Benachrichtigung"
    assert event.payload["message"] == "Dies ist ein Test"
    assert event.payload["priority"] == "high"
    assert event.payload["notification_type"] == "processing_completed"
    assert event.target_users == {"user-123"}


@pytest.mark.asyncio
async def test_emit_notification_default_priority():
    """Test that emit_notification uses normal priority by default."""
    broadcaster = EventBroadcaster()

    received_events = []

    async def capture_callback(event):
        received_events.append(event)

    broadcaster.register_callback(capture_callback)

    await broadcaster.emit_notification(
        user_id="user-456",
        title="Info",
        message="Nachricht",
    )

    assert len(received_events) == 1
    assert received_events[0].priority == "normal"


@pytest.mark.asyncio
async def test_notification_received_in_enum():
    """Test that NOTIFICATION_RECEIVED exists in RealtimeEventType."""
    assert hasattr(RealtimeEventType, 'NOTIFICATION_RECEIVED')
    assert RealtimeEventType.NOTIFICATION_RECEIVED.value == "notification.received"
