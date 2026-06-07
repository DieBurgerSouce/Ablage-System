# -*- coding: utf-8 -*-
"""Unit-Tests fuer M17 (3b): BPMN Call Activity als eigene Sub-Instanz.

Eine Call Activity startet eine separate Sub-Instanz der aufgerufenen Definition;
die Eltern-Instanz parkt am Call-Activity-Element und wird nach Abschluss der
Sub-Instanz fortgesetzt (Rueckkopplung im End-Event).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.bpmn_models.bpmn import ProcessStatus
from app.services.bpmn.bpmn_parser import BPMNElement, BPMNParser, ElementType
from app.services.bpmn.process_execution_service import ProcessExecutionService


_CALL_ACTIVITY_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="defs" targetNamespace="http://test">
  <process id="Parent" isExecutable="true">
    <startEvent id="start"/>
    <callActivity id="ca1" name="Sub aufrufen" calledElement="SubProc"/>
    <endEvent id="end"/>
  </process>
</definitions>"""


@pytest.fixture
def service() -> ProcessExecutionService:
    return ProcessExecutionService(db=AsyncMock())


def _call_element() -> BPMNElement:
    return BPMNElement(
        id="ca1",
        type=ElementType.CALL_ACTIVITY.value,
        extension_properties={"calledElement": "SubProc"},
        outgoing=[],
    )


def test_parser_reads_called_element():
    """Parser legt calledElement in extension_properties ab."""
    process = BPMNParser().parse(_CALL_ACTIVITY_BPMN)
    ca = process.get_element("ca1")
    assert ca is not None
    assert ca.type == ElementType.CALL_ACTIVITY.value
    assert ca.extension_properties.get("calledElement") == "SubProc"


@pytest.mark.asyncio
async def test_call_activity_without_called_element_continues(service):
    """Ohne calledElement wird der Flow fortgesetzt (kein Sub-Prozess, kein Crash)."""
    service._continue_flow = AsyncMock()
    service._get_active_definition = AsyncMock()
    element = BPMNElement(id="ca1", type=ElementType.CALL_ACTIVITY.value, extension_properties={})
    instance = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), current_elements=[])

    await service._execute_call_activity(instance, MagicMock(), element, None)

    service._continue_flow.assert_awaited_once()
    service._get_active_definition.assert_not_called()
    service.db.add.assert_not_called()


@pytest.mark.asyncio
async def test_call_activity_definition_not_found_continues(service):
    """Fehlt die Ziel-Definition, wird der Flow fortgesetzt (kein Sub-Prozess)."""
    service._continue_flow = AsyncMock()
    service._add_history = AsyncMock()
    service._call_activity_depth = AsyncMock(return_value=0)
    service._get_active_definition = AsyncMock(return_value=None)
    element = _call_element()
    instance = SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), current_elements=[])

    await service._execute_call_activity(instance, MagicMock(), element, None)

    service._continue_flow.assert_awaited_once()
    service.db.add.assert_not_called()


@pytest.mark.asyncio
async def test_call_activity_starts_subinstance_and_parks_parent(service):
    """Happy Path: Sub-Instanz mit Eltern-Verknuepfung wird angelegt, Parent parkt."""
    service._add_history = AsyncMock()
    service._call_activity_depth = AsyncMock(return_value=0)
    called_def = SimpleNamespace(
        id=uuid.uuid4(), name="Sub",
        process_data={"id": "SubProc", "elements": []},  # keine Start-Events -> keine Rekursion
    )
    service._get_active_definition = AsyncMock(return_value=called_def)
    service.db.add = MagicMock()
    service.db.flush = AsyncMock()

    element = _call_element()
    instance = SimpleNamespace(
        id=uuid.uuid4(), company_id=uuid.uuid4(), business_key="BK-1",
        variables={"betrag": 100}, current_elements=[], document_id=None,
    )

    await service._execute_call_activity(instance, MagicMock(), element, None)

    # Parent-Token geparkt
    assert "ca1" in instance.current_elements
    # Sub-Instanz mit Verknuepfung angelegt
    service.db.add.assert_called_once()
    sub = service.db.add.call_args.args[0]
    assert sub.definition_id == called_def.id
    assert sub.parent_instance_id == instance.id
    assert sub.parent_element_id == "ca1"
    assert sub.company_id == instance.company_id
    assert sub.variables == {"betrag": 100}
    assert sub.variables is not instance.variables  # Kopie, keine Referenz


@pytest.mark.asyncio
async def test_resume_parent_merges_vars_and_continues(service):
    """Nach Sub-Abschluss: Variablen gemerged, Token konsumiert, Eltern-Flow fortgesetzt."""
    service._add_history = AsyncMock()
    service._continue_flow = AsyncMock()
    service.db.flush = AsyncMock()

    parent_id = uuid.uuid4()
    cid = uuid.uuid4()
    parent = SimpleNamespace(
        id=parent_id, company_id=cid, status=ProcessStatus.RUNNING,
        variables={"a": 1}, definition_id=uuid.uuid4(), current_elements=["ca1"],
    )
    service.get_instance = AsyncMock(return_value=parent)
    service._get_definition_by_id = AsyncMock(
        return_value=SimpleNamespace(process_data={"id": "Parent", "elements": []})
    )
    call_element = SimpleNamespace(id="ca1", outgoing=[])
    fake_parent_process = MagicMock()
    fake_parent_process.get_element.return_value = call_element

    sub_instance = SimpleNamespace(
        parent_instance_id=parent_id, parent_element_id="ca1",
        company_id=cid, variables={"b": 2},
    )

    with patch(
        "app.services.bpmn.process_execution_service.BPMNProcess.from_dict",
        return_value=fake_parent_process,
    ):
        await service._resume_parent_after_call_activity(sub_instance, None)

    assert parent.variables == {"a": 1, "b": 2}      # out-Mapping gemerged
    assert "ca1" not in parent.current_elements       # Token konsumiert
    service._continue_flow.assert_awaited_once_with(parent, fake_parent_process, call_element, None)


@pytest.mark.asyncio
async def test_resume_parent_skips_when_parent_not_running(service):
    """Ist die Eltern-Instanz nicht mehr aktiv, passiert nichts (kein Crash)."""
    service._continue_flow = AsyncMock()
    parent = SimpleNamespace(status=ProcessStatus.COMPLETED)
    service.get_instance = AsyncMock(return_value=parent)
    sub_instance = SimpleNamespace(
        parent_instance_id=uuid.uuid4(), parent_element_id="ca1",
        company_id=uuid.uuid4(), variables={},
    )

    await service._resume_parent_after_call_activity(sub_instance, None)

    service._continue_flow.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_activity_depth_counts_parent_chain(service):
    """_call_activity_depth zaehlt die Eltern-Kette korrekt."""
    cid = uuid.uuid4()
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    inst1 = SimpleNamespace(parent_instance_id=None, company_id=cid)
    inst2 = SimpleNamespace(parent_instance_id=id1, company_id=cid)
    inst3 = SimpleNamespace(parent_instance_id=id2, company_id=cid)
    mapping = {id1: inst1, id2: inst2}
    service.get_instance = AsyncMock(side_effect=lambda pid, c: mapping.get(pid))

    assert await service._call_activity_depth(inst3) == 2
    assert await service._call_activity_depth(inst1) == 0


@pytest.mark.asyncio
async def test_end_event_resumes_parent_when_subinstance(service):
    """End-Event einer Sub-Instanz triggert die Eltern-Rueckkopplung."""
    service._add_history = AsyncMock()
    service._resume_parent_after_call_activity = AsyncMock()
    element = BPMNElement(id="end", type=ElementType.END_EVENT.value)
    sub = SimpleNamespace(
        id=uuid.uuid4(), company_id=uuid.uuid4(), current_elements=[],
        parent_instance_id=uuid.uuid4(), status=ProcessStatus.RUNNING,
    )

    await service._execute_end_event(sub, MagicMock(), element, None)

    assert sub.status == ProcessStatus.COMPLETED
    service._resume_parent_after_call_activity.assert_awaited_once_with(sub, None)


@pytest.mark.asyncio
async def test_end_event_no_parent_no_resume(service):
    """Root-Instanz (ohne Eltern) loest keine Rueckkopplung aus."""
    service._add_history = AsyncMock()
    service._resume_parent_after_call_activity = AsyncMock()
    element = BPMNElement(id="end", type=ElementType.END_EVENT.value)
    root = SimpleNamespace(
        id=uuid.uuid4(), company_id=uuid.uuid4(), current_elements=[],
        parent_instance_id=None, status=ProcessStatus.RUNNING,
    )

    await service._execute_end_event(root, MagicMock(), element, None)

    assert root.status == ProcessStatus.COMPLETED
    service._resume_parent_after_call_activity.assert_not_awaited()
