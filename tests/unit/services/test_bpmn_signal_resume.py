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

from app.services.bpmn.bpmn_parser import BPMNParser, BPMNProcess, ElementType
from app.services.bpmn.process_execution_service import ProcessExecutionService


# Minimal-BPMN mit globaler <signal>-Definition (definitions-Ebene) und einem
# Signal-Catch-Event, das per signalRef darauf verweist.
_SIGNAL_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="defs" targetNamespace="http://test">
  <signal id="Signal_1" name="Freigabe erteilt"/>
  <process id="P1" isExecutable="true">
    <startEvent id="start"/>
    <intermediateCatchEvent id="catch1">
      <signalEventDefinition signalRef="Signal_1"/>
    </intermediateCatchEvent>
  </process>
</definitions>"""


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


def _signal_catch(signal_ref=None, signal_name=None) -> SimpleNamespace:
    """Erzeugt ein geparktes Signal-Catch-Event fuer die Matching-Tests."""
    return SimpleNamespace(
        type=ElementType.INTERMEDIATE_CATCH_EVENT.value,
        timer_type=None,
        id="catch1",
        outgoing=[],
        signal_ref=signal_ref,
        signal_name=signal_name,
    )


async def _run_resume(service, catch, signal_name):
    """Fuehrt _resume_waiting_catch_events mit gepatchtem Prozess aus."""
    service._get_definition_by_id = AsyncMock(
        return_value=SimpleNamespace(process_data={})
    )
    service._continue_flow = AsyncMock()
    fake_process = MagicMock()
    fake_process.get_element.return_value = catch
    instance = SimpleNamespace(
        current_elements=["catch1"], definition_id=uuid.uuid4(), id=uuid.uuid4()
    )
    with patch(
        "app.services.bpmn.process_execution_service.BPMNProcess.from_dict",
        return_value=fake_process,
    ):
        resumed = await service._resume_waiting_catch_events(
            instance, None, signal_name=signal_name
        )
    return resumed, instance


@pytest.mark.asyncio
async def test_resume_matches_by_signal_name(service):
    """M17: Catch-Event mit passendem aufgeloesten Signal-Namen feuert."""
    catch = _signal_catch(signal_ref="Signal_1", signal_name="Freigabe erteilt")
    resumed, instance = await _run_resume(service, catch, "Freigabe erteilt")
    assert resumed == ["catch1"]
    assert "catch1" not in instance.current_elements
    service._continue_flow.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_skips_non_matching_signal_name(service):
    """M17: Catch-Event mit anderem Signal-Namen bleibt geparkt (kein Fehlfeuern)."""
    catch = _signal_catch(signal_ref="Signal_1", signal_name="Freigabe erteilt")
    resumed, instance = await _run_resume(service, catch, "Ablehnung")
    assert resumed == []
    assert instance.current_elements == ["catch1"]
    service._continue_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_matches_by_signal_ref_fallback(service):
    """M17: Ohne aufgeloesten Namen matcht die signalRef-ID als Fallback."""
    catch = _signal_catch(signal_ref="Signal_1", signal_name=None)
    resumed, _ = await _run_resume(service, catch, "Signal_1")
    assert resumed == ["catch1"]
    service._continue_flow.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_backward_compat_element_without_signal(service):
    """M17/BC: Alt-Event ohne hinterlegten Signal-Namen/-Ref feuert weiterhin."""
    catch = _signal_catch(signal_ref=None, signal_name=None)
    resumed, _ = await _run_resume(service, catch, "IrgendeinSignal")
    assert resumed == ["catch1"]
    service._continue_flow.assert_awaited_once()


def test_parser_extracts_signal_ref_and_name():
    """M17: Parser liest signalRef + aufgeloesten Namen aus globaler <signal>-Definition."""
    process = BPMNParser().parse(_SIGNAL_BPMN)
    catch = process.get_element("catch1")
    assert catch is not None
    assert catch.signal_ref == "Signal_1"
    assert catch.signal_name == "Freigabe erteilt"


def test_signal_fields_survive_jsonb_roundtrip():
    """M17: signal_ref/signal_name ueberstehen to_dict()->from_dict() (JSONB-Pfad)."""
    process = BPMNParser().parse(_SIGNAL_BPMN)
    restored = BPMNProcess.from_dict(process.to_dict())
    catch = restored.get_element("catch1")
    assert catch is not None
    assert catch.signal_ref == "Signal_1"
    assert catch.signal_name == "Freigabe erteilt"
