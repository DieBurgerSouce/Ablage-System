# -*- coding: utf-8 -*-
"""Tests fuer Workflow Execution Events im Event Broadcaster.

Testet neue Event-Typen und Convenience-Methoden.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from typing import List, Dict
from datetime import datetime, timezone

from app.services.realtime.event_broadcaster import (
    EventBroadcaster,
    RealtimeEventType,
    RealtimeEvent,
)

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.services, pytest.mark.asyncio]


@pytest.fixture
def mock_event_bus() -> MagicMock:
    """Mock Event Bus."""
    bus = MagicMock()
    bus.subscribe_pattern = MagicMock()
    return bus


@pytest.fixture
def event_broadcaster(mock_event_bus: MagicMock) -> EventBroadcaster:
    """Event Broadcaster mit Mock-Bus."""
    return EventBroadcaster(event_bus=mock_event_bus)


class TestWorkflowEventTypes:
    """Tests fuer Workflow Event Types."""

    def test_workflow_event_types_exist(self) -> None:
        """Alle 5 neuen Event-Typen existieren in enum."""
        workflow_event_types = [
            RealtimeEventType.WORKFLOW_STEP_STARTED,
            RealtimeEventType.WORKFLOW_STEP_COMPLETED,
            RealtimeEventType.WORKFLOW_STEP_FAILED,
            RealtimeEventType.WORKFLOW_INSTANCE_COMPLETED,
            RealtimeEventType.WORKFLOW_SLA_WARNING,
        ]

        for event_type in workflow_event_types:
            assert isinstance(event_type, RealtimeEventType), f"{event_type} sollte im Enum sein"
            assert event_type.value.startswith("workflow."), f"{event_type} sollte mit workflow. beginnen"


class TestEmitWorkflowStepStarted:
    """Tests fuer emit_workflow_step_started."""

    async def test_emit_workflow_step_started(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Broadcasts correct event type and payload."""
        # Mock callbacks list
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        instance_id = "inst-123"
        step_id = "step-456"
        step_name = "Validierung"
        step_type = "action"
        user_id = "user-789"
        company_id = "comp-abc"

        await event_broadcaster.emit_workflow_step_started(
            instance_id=instance_id,
            step_id=step_id,
            step_name=step_name,
            step_type=step_type,
            user_id=user_id,
            company_id=company_id,
        )

        # Callback sollte aufgerufen worden sein
        assert callback.called, "Callback sollte aufgerufen werden"

        # Event pruefen
        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_STEP_STARTED
        assert event.payload["instance_id"] == instance_id
        assert event.payload["step_id"] == step_id
        assert event.payload["step_name"] == step_name
        assert event.payload["step_type"] == step_type
        assert event.target_company_id == company_id
        assert event.priority == "normal"


class TestEmitWorkflowStepCompleted:
    """Tests fuer emit_workflow_step_completed."""

    async def test_emit_workflow_step_completed(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Includes duration and next_steps."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        instance_id = "inst-123"
        step_id = "step-456"
        step_name = "Validierung"
        duration_ms = 1500
        next_steps = ["step-789", "step-012"]

        await event_broadcaster.emit_workflow_step_completed(
            instance_id=instance_id,
            step_id=step_id,
            step_name=step_name,
            duration_ms=duration_ms,
            next_steps=next_steps,
        )

        assert callback.called, "Callback sollte aufgerufen werden"

        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_STEP_COMPLETED
        assert event.payload["instance_id"] == instance_id
        assert event.payload["step_id"] == step_id
        assert event.payload["duration_ms"] == duration_ms
        assert event.payload["next_steps"] == next_steps
        assert event.priority == "normal"


class TestEmitWorkflowStepFailed:
    """Tests fuer emit_workflow_step_failed."""

    async def test_emit_workflow_step_failed(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Includes error_message, high priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        instance_id = "inst-123"
        step_id = "step-456"
        step_name = "Validierung"
        error_message = "Validation fehlgeschlagen: Ungueltige Daten"

        await event_broadcaster.emit_workflow_step_failed(
            instance_id=instance_id,
            step_id=step_id,
            step_name=step_name,
            error_message=error_message,
        )

        assert callback.called, "Callback sollte aufgerufen werden"

        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_STEP_FAILED
        assert event.payload["instance_id"] == instance_id
        assert event.payload["step_id"] == step_id
        assert event.payload["error_message"] == error_message
        assert event.priority == "high", "Failed step sollte high priority haben"


class TestEmitWorkflowInstanceCompleted:
    """Tests fuer emit_workflow_instance_completed."""

    async def test_emit_workflow_instance_completed(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Includes summary stats."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        instance_id = "inst-123"
        workflow_id = "wf-456"
        workflow_name = "Rechnungsverarbeitung"
        status = "completed"
        total_duration_ms = 15000
        steps_completed = 10
        steps_failed = 0

        await event_broadcaster.emit_workflow_instance_completed(
            instance_id=instance_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=status,
            total_duration_ms=total_duration_ms,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
        )

        assert callback.called, "Callback sollte aufgerufen werden"

        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_INSTANCE_COMPLETED
        assert event.payload["instance_id"] == instance_id
        assert event.payload["workflow_id"] == workflow_id
        assert event.payload["workflow_name"] == workflow_name
        assert event.payload["status"] == status
        assert event.payload["total_duration_ms"] == total_duration_ms
        assert event.payload["steps_completed"] == steps_completed
        assert event.payload["steps_failed"] == steps_failed
        assert event.priority == "normal", "Successful completion sollte normal priority haben"

    async def test_emit_workflow_instance_completed_failed_status(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Failed instance completion hat high priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        await event_broadcaster.emit_workflow_instance_completed(
            instance_id="inst-123",
            workflow_id="wf-456",
            workflow_name="Test Workflow",
            status="failed",
            total_duration_ms=5000,
            steps_completed=3,
            steps_failed=1,
        )

        assert callback.called
        event: RealtimeEvent = callback.call_args[0][0]
        assert event.priority == "high", "Failed status sollte high priority haben"


class TestEmitWorkflowSLAWarning:
    """Tests fuer emit_workflow_sla_warning."""

    async def test_emit_workflow_sla_warning(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Critical priority for SLA warnings."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        instance_id = "inst-123"
        step_id = "step-456"
        step_name = "Approval"
        sla_deadline = "2026-02-10T15:00:00Z"
        elapsed_seconds = 7200

        await event_broadcaster.emit_workflow_sla_warning(
            instance_id=instance_id,
            step_id=step_id,
            step_name=step_name,
            sla_deadline=sla_deadline,
            elapsed_seconds=elapsed_seconds,
        )

        assert callback.called, "Callback sollte aufgerufen werden"

        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_SLA_WARNING
        assert event.payload["instance_id"] == instance_id
        assert event.payload["step_id"] == step_id
        assert event.payload["step_name"] == step_name
        assert event.payload["sla_deadline"] == sla_deadline
        assert event.payload["elapsed_seconds"] == elapsed_seconds
        assert event.priority == "high", "SLA warning sollte high priority haben"


class TestEventBroadcasterCallbacks:
    """Tests fuer Callback-Mechanismus."""

    async def test_multiple_callbacks_receive_event(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Mehrere Callbacks erhalten dasselbe Event."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        callback3 = AsyncMock()

        event_broadcaster._callbacks.extend([callback1, callback2, callback3])

        await event_broadcaster.emit_workflow_step_started(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            step_type="action",
        )

        assert callback1.called, "Callback 1 sollte aufgerufen werden"
        assert callback2.called, "Callback 2 sollte aufgerufen werden"
        assert callback3.called, "Callback 3 sollte aufgerufen werden"

    async def test_callback_exception_does_not_break_broadcast(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Exception in einem Callback bricht Broadcast nicht ab."""
        callback1 = AsyncMock(side_effect=Exception("Test error"))
        callback2 = AsyncMock()

        event_broadcaster._callbacks.extend([callback1, callback2])

        # Sollte nicht crashen
        await event_broadcaster.emit_workflow_step_started(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            step_type="action",
        )

        # Callback 2 sollte trotzdem aufgerufen werden
        assert callback2.called, "Callback 2 sollte trotz Exception in Callback 1 aufgerufen werden"


class TestEventHistory:
    """Tests fuer Event-History."""

    async def test_events_are_stored_in_history(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Events werden in History gespeichert."""
        await event_broadcaster.emit_workflow_step_started(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            step_type="action",
        )

        # History sollte Event enthalten
        history = event_broadcaster.get_recent_events()
        assert len(history) > 0, "History sollte mindestens ein Event enthalten"

        last_event = history[-1]
        assert last_event.event_type == RealtimeEventType.WORKFLOW_STEP_STARTED


class TestRealtimeEventDataclass:
    """Tests fuer RealtimeEvent Dataclass."""

    def test_realtime_event_to_dict(self) -> None:
        """RealtimeEvent kann zu Dict konvertiert werden."""
        event = RealtimeEvent(
            event_type=RealtimeEventType.WORKFLOW_STEP_STARTED,
            payload={"test": "data"},
            event_id="evt-123",
            timestamp=datetime.now(timezone.utc),
            priority="normal",
        )

        event_dict = event.to_dict()

        assert "event_type" in event_dict
        assert "payload" in event_dict
        assert "event_id" in event_dict
        assert "timestamp" in event_dict
        assert "priority" in event_dict

        assert event_dict["event_type"] == "workflow.step_started"
        assert event_dict["payload"] == {"test": "data"}
        assert event_dict["priority"] == "normal"


class TestWorkflowEventHandler:
    """Tests fuer _handle_workflow_event."""

    async def test_handle_workflow_event_maps_correctly(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Workflow events werden korrekt gemappt."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        # Mock Event Bus Event
        from app.services.events.event_bus import Event, EventType
        from uuid import uuid4

        # Create mock event
        mock_event = Mock()
        mock_event.event_type = Mock()
        mock_event.event_type.value = "workflow.step_started"
        mock_event.payload = {
            "instance_id": "inst-123",
            "step_id": "step-456",
            "step_name": "Test",
            "step_type": "action",
        }
        mock_event.event_id = uuid4()
        mock_event.user_id = None
        # Call handler directly
        await event_broadcaster._handle_workflow_event(mock_event)

        # Callback sollte aufgerufen worden sein
        assert callback.called, "Callback sollte aufgerufen werden"

        call_args = callback.call_args
        event: RealtimeEvent = call_args[0][0]

        assert event.event_type == RealtimeEventType.WORKFLOW_STEP_STARTED


class TestPriorityLevels:
    """Tests fuer Priority-Logik."""

    async def test_normal_priority_for_started(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Step started hat normal priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        await event_broadcaster.emit_workflow_step_started(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            step_type="action",
        )

        event: RealtimeEvent = callback.call_args[0][0]
        assert event.priority == "normal"

    async def test_normal_priority_for_completed(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Step completed hat normal priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        await event_broadcaster.emit_workflow_step_completed(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            duration_ms=1000,
            next_steps=[],
        )

        event: RealtimeEvent = callback.call_args[0][0]
        assert event.priority == "normal"

    async def test_high_priority_for_failed(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """Step failed hat high priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        await event_broadcaster.emit_workflow_step_failed(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            error_message="Error",
        )

        event: RealtimeEvent = callback.call_args[0][0]
        assert event.priority == "high"

    async def test_high_priority_for_sla_warning(
        self, event_broadcaster: EventBroadcaster
    ) -> None:
        """SLA warning hat high priority."""
        callback = AsyncMock()
        event_broadcaster._callbacks.append(callback)

        await event_broadcaster.emit_workflow_sla_warning(
            instance_id="inst-123",
            step_id="step-456",
            step_name="Test",
            sla_deadline="2026-02-10T15:00:00Z",
            elapsed_seconds=7200,
        )

        event: RealtimeEvent = callback.call_args[0][0]
        assert event.priority == "high"
