# -*- coding: utf-8 -*-
"""Unit-Tests fuer M17: Signal setzt wartende Catch-Events fort.

Frueher protokollierte ``signal()`` ein Signal nur (Token blieb geparkt). Jetzt
werden geparkte Nicht-Timer-Catch-/Boundary-Events der Instanz fortgesetzt.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bpmn.bpmn_parser import ElementType
from app.services.bpmn.process_execution_service import ProcessExecutionService


@pytest.fixture
def service() -> ProcessExecutionService:
    return ProcessExecutionService(db=AsyncMock())


@pytest.mark.asyncio
async def test_resume_consumes_token_and_continues(service):
    """Ein geparktes Signal-Catch-Event wird konsumiert und der Flow fortgesetzt."""
    service._get_definition_by_id = AsyncMock(return_value=SimpleNamespace(process_data={}))
    service._continue_flow = AsyncMock()

    catch = SimpleNamespace(
        type=ElementType.INTERMEDIATE_CATCH_EVENT.value,
        timer_type=None,
        id="catch1",
        outgoing=[],
    )
    fake_process = MagicMock()
    fake_process.get_element.return_value = catch
    instance = SimpleNamespace(
        current_elements=["catch1"], definition_id=uuid.uuid4(), id=uuid.uuid4()
    )

    with patch(
        "app.services.bpmn.process_execution_service.BPMNProcess.from_dict",
        return_value=fake_process,
    ):
        resumed = await service._resume_waiting_catch_events(instance, None)

    assert resumed == ["catch1"]
    assert "catch1" not in instance.current_elements
    service._continue_flow.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_ignores_timer_catch_events(service):
    """Timer-Catch-Events feuern ueber den Timer-Job, nicht ueber Signale."""
    service._get_definition_by_id = AsyncMock(return_value=SimpleNamespace(process_data={}))
    service._continue_flow = AsyncMock()

    timer = SimpleNamespace(
        type=ElementType.INTERMEDIATE_CATCH_EVENT.value,
        timer_type="duration",
        id="t1",
        outgoing=[],
    )
    fake_process = MagicMock()
    fake_process.get_element.return_value = timer
    instance = SimpleNamespace(
        current_elements=["t1"], definition_id=uuid.uuid4(), id=uuid.uuid4()
    )

    with patch(
        "app.services.bpmn.process_execution_service.BPMNProcess.from_dict",
        return_value=fake_process,
    ):
        resumed = await service._resume_waiting_catch_events(instance, None)

    assert resumed == []
    assert instance.current_elements == ["t1"]
    service._continue_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_no_definition_returns_empty(service):
    """Ohne Prozess-Definition wird nichts fortgesetzt (kein Crash)."""
    service._get_definition_by_id = AsyncMock(return_value=None)
    instance = SimpleNamespace(
        current_elements=["x"], definition_id=uuid.uuid4(), id=uuid.uuid4()
    )
    resumed = await service._resume_waiting_catch_events(instance, None)
    assert resumed == []
