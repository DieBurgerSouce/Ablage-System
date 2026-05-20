# -*- coding: utf-8 -*-
"""Tests fuer den BPMN 2.0 Import/Export Converter.

Tests fuer:
- BPMNParser: Parsen von BPMN 2.0 XML
- BPMNExporter: Export zu BPMN 2.0 XML
- BPMNValidator: Validierung von BPMN XML
- BPMNConverter: Bidirektionale Konvertierung
"""

import pytest
from uuid import uuid4

from app.services.workflow.bpmn_converter import (
    BPMNConverter,
    BPMNParser,
    BPMNExporter,
    BPMNValidator,
    WorkflowDefinition,
    ProcessDefinition,
    TaskDefinition,
    GatewayDefinition,
    EventDefinition,
    FlowDefinition,
    ValidationResult,
    TaskType,
    GatewayType,
    EventType,
    get_bpmn_converter,
    get_bpmn_parser,
    get_bpmn_exporter,
    get_bpmn_validator,
)


# =============================================================================
# Test Data: Valide BPMN XML
# =============================================================================

VALID_SIMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             id="Definitions_1"
             targetNamespace="http://example.com/bpmn">
    <process id="Process_1" name="Einfacher Prozess" isExecutable="true">
        <startEvent id="StartEvent_1" name="Start"/>
        <userTask id="Task_1" name="Aufgabe bearbeiten"
                  camunda:assignee="admin"
                  camunda:candidateGroups="managers,reviewers"/>
        <endEvent id="EndEvent_1" name="Ende"/>
        <sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1"/>
        <sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="EndEvent_1"/>
    </process>
</definitions>"""

VALID_COMPLEX_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             id="Definitions_2"
             targetNamespace="http://example.com/bpmn">
    <process id="InvoiceApproval" name="Rechnungsfreigabe" isExecutable="true">
        <startEvent id="Start" name="Rechnung eingegangen"/>

        <userTask id="Review" name="Rechnung pruefen"
                  camunda:assignee="${reviewer}"
                  camunda:formKey="forms/invoice-review"/>

        <exclusiveGateway id="Gateway_Decision" name="Freigabe?" default="Flow_Reject"/>

        <serviceTask id="AutoApprove" name="Automatisch freigeben"
                     implementation="celery:approve_invoice"/>

        <userTask id="ManualApprove" name="Manuelle Freigabe"
                  camunda:candidateGroups="finance-managers"/>

        <parallelGateway id="Gateway_Parallel" name="Parallel"/>

        <scriptTask id="ScriptTask" name="Skript ausfuehren"
                    scriptFormat="javascript">
            <script>console.log('Invoice approved');</script>
        </scriptTask>

        <endEvent id="End_Approved" name="Freigegeben"/>
        <endEvent id="End_Rejected" name="Abgelehnt"/>

        <sequenceFlow id="Flow_Start" sourceRef="Start" targetRef="Review"/>
        <sequenceFlow id="Flow_ToGateway" sourceRef="Review" targetRef="Gateway_Decision"/>
        <sequenceFlow id="Flow_Approve" sourceRef="Gateway_Decision" targetRef="AutoApprove">
            <conditionExpression xsi:type="tFormalExpression"
                                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                ${amount &lt; 1000}
            </conditionExpression>
        </sequenceFlow>
        <sequenceFlow id="Flow_ManualApprove" sourceRef="Gateway_Decision" targetRef="ManualApprove">
            <conditionExpression xsi:type="tFormalExpression"
                                 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                ${amount >= 1000}
            </conditionExpression>
        </sequenceFlow>
        <sequenceFlow id="Flow_Reject" sourceRef="Gateway_Decision" targetRef="End_Rejected"/>
        <sequenceFlow id="Flow_AutoToEnd" sourceRef="AutoApprove" targetRef="End_Approved"/>
        <sequenceFlow id="Flow_ManualToEnd" sourceRef="ManualApprove" targetRef="End_Approved"/>
    </process>
</definitions>"""

VALID_TIMER_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="Definitions_Timer"
             targetNamespace="http://example.com/bpmn">
    <process id="TimerProcess" name="Timer Prozess" isExecutable="true">
        <startEvent id="Start" name="Start">
            <timerEventDefinition>
                <timeCycle>R5/PT1H</timeCycle>
            </timerEventDefinition>
        </startEvent>
        <intermediateCatchEvent id="Timer_Wait" name="Warten">
            <timerEventDefinition>
                <timeDuration>PT30M</timeDuration>
            </timerEventDefinition>
        </intermediateCatchEvent>
        <endEvent id="End" name="Ende"/>
        <sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Timer_Wait"/>
        <sequenceFlow id="Flow_2" sourceRef="Timer_Wait" targetRef="End"/>
    </process>
</definitions>"""

# =============================================================================
# Test Data: Ungueltige BPMN XML
# =============================================================================

INVALID_XML = "This is not XML at all!"

INVALID_NO_PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="Definitions_NoProcess"
             targetNamespace="http://example.com/bpmn">
</definitions>"""

INVALID_NO_START_EVENT = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="Definitions_NoStart"
             targetNamespace="http://example.com/bpmn">
    <process id="Process_NoStart" name="Ohne Start" isExecutable="true">
        <userTask id="Task_1" name="Aufgabe"/>
        <endEvent id="End_1" name="Ende"/>
        <sequenceFlow id="Flow_1" sourceRef="Task_1" targetRef="End_1"/>
    </process>
</definitions>"""


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestFactoryFunctions:
    """Tests fuer Factory Functions."""

    def test_get_bpmn_converter(self):
        """Testet Factory Function fuer BPMNConverter."""
        converter = get_bpmn_converter()
        assert isinstance(converter, BPMNConverter)

    def test_get_bpmn_parser(self):
        """Testet Factory Function fuer BPMNParser."""
        parser = get_bpmn_parser()
        assert isinstance(parser, BPMNParser)

    def test_get_bpmn_exporter(self):
        """Testet Factory Function fuer BPMNExporter."""
        exporter = get_bpmn_exporter()
        assert isinstance(exporter, BPMNExporter)

    def test_get_bpmn_validator(self):
        """Testet Factory Function fuer BPMNValidator."""
        validator = get_bpmn_validator()
        assert isinstance(validator, BPMNValidator)


# =============================================================================
# BPMNParser Tests
# =============================================================================

class TestBPMNParser:
    """Tests fuer BPMNParser."""

    @pytest.fixture
    def parser(self) -> BPMNParser:
        """Parser-Instanz."""
        return BPMNParser()

    def test_parse_simple_bpmn(self, parser: BPMNParser):
        """Testet Parsen eines einfachen BPMN."""
        workflow = parser.parse(VALID_SIMPLE_BPMN)

        assert isinstance(workflow, WorkflowDefinition)
        assert workflow.id == "Definitions_1"
        assert len(workflow.processes) == 1

        process = workflow.processes[0]
        assert process.id == "Process_1"
        assert process.name == "Einfacher Prozess"
        assert process.is_executable is True

        # Events pruefen
        assert len(process.events) == 2
        start_events = [e for e in process.events if e.event_type == EventType.START]
        end_events = [e for e in process.events if e.event_type == EventType.END]
        assert len(start_events) == 1
        assert len(end_events) == 1

        # Tasks pruefen
        assert len(process.tasks) == 1
        task = process.tasks[0]
        assert task.id == "Task_1"
        assert task.name == "Aufgabe bearbeiten"
        assert task.task_type == TaskType.APPROVAL
        assert task.assignee == "admin"
        assert "managers" in task.candidate_groups
        assert "reviewers" in task.candidate_groups

        # Flows pruefen
        assert len(process.flows) == 2

    def test_parse_complex_bpmn(self, parser: BPMNParser):
        """Testet Parsen eines komplexen BPMN mit Gateways."""
        workflow = parser.parse(VALID_COMPLEX_BPMN)

        assert isinstance(workflow, WorkflowDefinition)
        process = workflow.processes[0]

        # Gateways pruefen
        assert len(process.gateways) >= 2
        exclusive_gateways = [g for g in process.gateways if g.gateway_type == GatewayType.EXCLUSIVE]
        parallel_gateways = [g for g in process.gateways if g.gateway_type == GatewayType.PARALLEL]
        assert len(exclusive_gateways) >= 1
        assert len(parallel_gateways) >= 1

        # Tasks pruefen
        user_tasks = [t for t in process.tasks if t.task_type == TaskType.APPROVAL]
        service_tasks = [t for t in process.tasks if t.task_type == TaskType.AUTOMATED]
        script_tasks = [t for t in process.tasks if t.task_type == TaskType.SCRIPT]
        assert len(user_tasks) >= 2
        assert len(service_tasks) >= 1
        assert len(script_tasks) >= 1

        # Script Task spezifisch
        script_task = script_tasks[0]
        assert script_task.script_format == "javascript"
        assert "console.log" in script_task.script

        # Service Task spezifisch
        service_task = service_tasks[0]
        assert service_task.implementation == "celery:approve_invoice"

    def test_parse_timer_bpmn(self, parser: BPMNParser):
        """Testet Parsen von Timer Events."""
        workflow = parser.parse(VALID_TIMER_BPMN)

        process = workflow.processes[0]

        # Timer Events pruefen
        timer_events = [e for e in process.events if e.timer_type is not None]
        assert len(timer_events) >= 1

        # Cycle Timer (Start Event)
        cycle_timer = next((e for e in timer_events if e.timer_type == "cycle"), None)
        if cycle_timer:
            assert cycle_timer.timer_value == "R5/PT1H"

        # Duration Timer
        duration_timer = next((e for e in timer_events if e.timer_type == "duration"), None)
        if duration_timer:
            assert duration_timer.timer_value == "PT30M"

    def test_parse_invalid_xml_raises_error(self, parser: BPMNParser):
        """Testet dass ungueltiges XML einen Fehler wirft."""
        with pytest.raises(ValueError) as exc_info:
            parser.parse(INVALID_XML)
        assert "Ungueltiges BPMN-Format" in str(exc_info.value)

    def test_parse_no_process_raises_error(self, parser: BPMNParser):
        """Testet dass fehlender Process einen Fehler wirft."""
        with pytest.raises(ValueError) as exc_info:
            parser.parse(INVALID_NO_PROCESS)
        assert "Kein Process-Element" in str(exc_info.value)


# =============================================================================
# BPMNValidator Tests
# =============================================================================

class TestBPMNValidator:
    """Tests fuer BPMNValidator."""

    @pytest.fixture
    def validator(self) -> BPMNValidator:
        """Validator-Instanz."""
        return BPMNValidator()

    def test_validate_valid_bpmn(self, validator: BPMNValidator):
        """Testet Validierung eines validen BPMN."""
        result = validator.validate(VALID_SIMPLE_BPMN)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_invalid_xml(self, validator: BPMNValidator):
        """Testet Validierung von ungueltigem XML."""
        result = validator.validate(INVALID_XML)

        assert result.valid is False
        assert len(result.errors) >= 1
        assert any("PARSE_ERROR" in e.code or "SCHEMA_PARSE_ERROR" in e.code for e in result.errors)

    def test_validate_no_process(self, validator: BPMNValidator):
        """Testet Validierung ohne Process-Element."""
        result = validator.validate(INVALID_NO_PROCESS)

        assert result.valid is False
        assert any("NO_PROCESS" in e.code for e in result.errors)

    def test_validate_no_start_event(self, validator: BPMNValidator):
        """Testet Validierung ohne Start-Event."""
        result = validator.validate(INVALID_NO_START_EVENT)

        assert result.valid is False
        assert any("NO_START_EVENT" in e.code for e in result.errors)

    def test_validation_result_to_dict(self, validator: BPMNValidator):
        """Testet Konvertierung von ValidationResult zu Dictionary."""
        result = validator.validate(INVALID_XML)
        result_dict = result.to_dict()

        assert "valid" in result_dict
        assert "errors" in result_dict
        assert "warnings" in result_dict
        assert isinstance(result_dict["errors"], list)


# =============================================================================
# BPMNExporter Tests
# =============================================================================

class TestBPMNExporter:
    """Tests fuer BPMNExporter."""

    @pytest.fixture
    def exporter(self) -> BPMNExporter:
        """Exporter-Instanz."""
        return BPMNExporter()

    @pytest.fixture
    def simple_workflow(self) -> WorkflowDefinition:
        """Einfache Workflow-Definition."""
        process = ProcessDefinition(
            id="TestProcess",
            name="Test Prozess",
            is_executable=True,
        )

        # Start Event
        process.events.append(EventDefinition(
            id="Start_1",
            name="Start",
            event_type=EventType.START,
            position_x=100,
            position_y=200,
        ))

        # User Task
        process.tasks.append(TaskDefinition(
            id="Task_1",
            name="Aufgabe bearbeiten",
            task_type=TaskType.APPROVAL,
            assignee="admin",
            candidate_groups=["managers"],
            form_key="forms/task-form",
            position_x=250,
            position_y=200,
        ))

        # End Event
        process.events.append(EventDefinition(
            id="End_1",
            name="Ende",
            event_type=EventType.END,
            position_x=400,
            position_y=200,
        ))

        # Flows
        process.flows.append(FlowDefinition(
            id="Flow_1",
            source_ref="Start_1",
            target_ref="Task_1",
        ))
        process.flows.append(FlowDefinition(
            id="Flow_2",
            source_ref="Task_1",
            target_ref="End_1",
        ))

        return WorkflowDefinition(
            id="TestWorkflow",
            name="Test Workflow",
            description="Ein Test-Workflow",
            processes=[process],
        )

    def test_export_simple_workflow(self, exporter: BPMNExporter, simple_workflow: WorkflowDefinition):
        """Testet Export eines einfachen Workflows."""
        xml = exporter.export(simple_workflow)

        assert xml is not None
        assert "<?xml version" in xml
        assert "definitions" in xml
        assert "process" in xml
        assert "TestProcess" in xml
        assert "startEvent" in xml
        assert "userTask" in xml
        assert "endEvent" in xml
        assert "sequenceFlow" in xml

    def test_export_includes_camunda_attributes(self, exporter: BPMNExporter, simple_workflow: WorkflowDefinition):
        """Testet dass Camunda-Attribute exportiert werden."""
        xml = exporter.export(simple_workflow)

        assert "assignee" in xml
        assert "admin" in xml
        assert "candidateGroups" in xml
        assert "managers" in xml
        assert "formKey" in xml

    def test_export_includes_diagram(self, exporter: BPMNExporter, simple_workflow: WorkflowDefinition):
        """Testet dass BPMN Diagram exportiert wird."""
        xml = exporter.export(simple_workflow)

        assert "BPMNDiagram" in xml
        assert "BPMNPlane" in xml
        assert "BPMNShape" in xml
        assert "BPMNEdge" in xml

    def test_export_with_gateway(self, exporter: BPMNExporter):
        """Testet Export mit Gateway."""
        process = ProcessDefinition(
            id="GatewayProcess",
            name="Gateway Prozess",
        )

        process.events.append(EventDefinition(
            id="Start",
            event_type=EventType.START,
        ))

        process.gateways.append(GatewayDefinition(
            id="Gateway_1",
            name="Entscheidung",
            gateway_type=GatewayType.EXCLUSIVE,
            default_flow="Flow_Default",
        ))

        process.events.append(EventDefinition(
            id="End",
            event_type=EventType.END,
        ))

        workflow = WorkflowDefinition(
            id="GatewayWorkflow",
            name="Gateway Workflow",
            processes=[process],
        )

        xml = exporter.export(workflow)

        assert "exclusiveGateway" in xml
        assert "Gateway_1" in xml
        assert "default" in xml

    def test_export_with_timer(self, exporter: BPMNExporter):
        """Testet Export mit Timer Event."""
        process = ProcessDefinition(
            id="TimerProcess",
            name="Timer Prozess",
        )

        process.events.append(EventDefinition(
            id="TimerEvent",
            name="Warten",
            event_type=EventType.INTERMEDIATE_CATCH,
            timer_type="duration",
            timer_value="PT1H",
        ))

        workflow = WorkflowDefinition(
            id="TimerWorkflow",
            name="Timer Workflow",
            processes=[process],
        )

        xml = exporter.export(workflow)

        assert "timerEventDefinition" in xml
        assert "timeDuration" in xml
        assert "PT1H" in xml

    def test_export_with_condition(self, exporter: BPMNExporter):
        """Testet Export mit Condition Expression."""
        process = ProcessDefinition(
            id="ConditionProcess",
            name="Condition Prozess",
        )

        process.flows.append(FlowDefinition(
            id="ConditionalFlow",
            source_ref="Source",
            target_ref="Target",
            condition="${amount > 1000}",
        ))

        workflow = WorkflowDefinition(
            id="ConditionWorkflow",
            name="Condition Workflow",
            processes=[process],
        )

        xml = exporter.export(workflow)

        assert "conditionExpression" in xml
        assert "amount" in xml


# =============================================================================
# BPMNConverter Tests
# =============================================================================

class TestBPMNConverter:
    """Tests fuer den Haupt-Converter."""

    @pytest.fixture
    def converter(self) -> BPMNConverter:
        """Converter-Instanz."""
        return BPMNConverter()

    def test_roundtrip_simple(self, converter: BPMNConverter):
        """Testet Import und Re-Export."""
        # Import
        workflow = converter.import_bpmn(VALID_SIMPLE_BPMN)

        # Export
        exported_xml = converter.export_bpmn(workflow)

        # Re-Import
        reimported = converter.import_bpmn(exported_xml)

        # Vergleich
        assert reimported.id == workflow.id
        assert len(reimported.processes) == len(workflow.processes)
        assert len(reimported.processes[0].tasks) == len(workflow.processes[0].tasks)
        assert len(reimported.processes[0].events) == len(workflow.processes[0].events)

    def test_convert_from_internal_format(self, converter: BPMNConverter):
        """Testet Konvertierung von internem ReactFlow-Format."""
        nodes = [
            {
                "id": "node_start",
                "type": "trigger",
                "position": {"x": 100, "y": 200},
                "data": {"label": "Start"},
            },
            {
                "id": "node_task",
                "type": "userTask",
                "position": {"x": 250, "y": 200},
                "data": {
                    "label": "Aufgabe",
                    "assignee": "admin",
                    "candidateGroups": ["managers"],
                },
            },
            {
                "id": "node_end",
                "type": "end",
                "position": {"x": 400, "y": 200},
                "data": {"label": "Ende"},
            },
        ]

        edges = [
            {
                "id": "edge_1",
                "source": "node_start",
                "target": "node_task",
            },
            {
                "id": "edge_2",
                "source": "node_task",
                "target": "node_end",
            },
        ]

        xml = converter.convert_from_internal(
            nodes=nodes,
            edges=edges,
            workflow_id="test_workflow",
            workflow_name="Test Workflow",
            trigger_type="manual",
        )

        assert xml is not None
        assert "<?xml version" in xml
        assert "test_workflow" in xml or "Process_test_workflow" in xml
        assert "startEvent" in xml
        assert "userTask" in xml
        assert "endEvent" in xml
        assert "sequenceFlow" in xml

    def test_convert_to_internal_format(self, converter: BPMNConverter):
        """Testet Konvertierung zu internem ReactFlow-Format."""
        nodes, edges = converter.convert_to_internal(VALID_SIMPLE_BPMN)

        assert len(nodes) >= 3  # Start, Task, End
        assert len(edges) >= 2

        # Node-Struktur pruefen
        for node in nodes:
            assert "id" in node
            assert "type" in node
            assert "position" in node
            assert "data" in node
            assert "x" in node["position"]
            assert "y" in node["position"]
            assert "label" in node["data"]

        # Edge-Struktur pruefen
        for edge in edges:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge

    def test_convert_with_gateway(self, converter: BPMNConverter):
        """Testet Konvertierung mit Gateway."""
        nodes, edges = converter.convert_to_internal(VALID_COMPLEX_BPMN)

        # Gateway-Nodes finden
        gateway_nodes = [n for n in nodes if n["type"] in ["condition", "parallel", "inclusive"]]
        assert len(gateway_nodes) >= 1

    def test_convert_with_condition(self, converter: BPMNConverter):
        """Testet Konvertierung mit Bedingungen."""
        nodes, edges = converter.convert_to_internal(VALID_COMPLEX_BPMN)

        # Edges mit Conditions finden
        conditional_edges = [e for e in edges if e.get("data", {}).get("condition")]
        assert len(conditional_edges) >= 1


# =============================================================================
# Data Class Tests
# =============================================================================

class TestDataClasses:
    """Tests fuer Datenklassen."""

    def test_task_definition_to_dict(self):
        """Testet TaskDefinition.to_dict()."""
        task = TaskDefinition(
            id="task_1",
            name="Test Task",
            task_type=TaskType.APPROVAL,
            assignee="admin",
            candidate_groups=["managers"],
            form_key="forms/test",
        )

        result = task.to_dict()

        assert result["id"] == "task_1"
        assert result["name"] == "Test Task"
        assert result["task_type"] == "approval"
        assert result["assignee"] == "admin"
        assert result["candidate_groups"] == ["managers"]
        assert result["form_key"] == "forms/test"

    def test_gateway_definition_to_dict(self):
        """Testet GatewayDefinition.to_dict()."""
        gateway = GatewayDefinition(
            id="gateway_1",
            name="Test Gateway",
            gateway_type=GatewayType.EXCLUSIVE,
            default_flow="flow_default",
        )

        result = gateway.to_dict()

        assert result["id"] == "gateway_1"
        assert result["name"] == "Test Gateway"
        assert result["gateway_type"] == "exclusive"
        assert result["default_flow"] == "flow_default"

    def test_event_definition_to_dict(self):
        """Testet EventDefinition.to_dict()."""
        event = EventDefinition(
            id="event_1",
            name="Test Event",
            event_type=EventType.START,
            timer_type="duration",
            timer_value="PT1H",
        )

        result = event.to_dict()

        assert result["id"] == "event_1"
        assert result["name"] == "Test Event"
        assert result["event_type"] == "start"
        assert result["timer_type"] == "duration"
        assert result["timer_value"] == "PT1H"

    def test_flow_definition_to_dict(self):
        """Testet FlowDefinition.to_dict()."""
        flow = FlowDefinition(
            id="flow_1",
            name="Test Flow",
            source_ref="source",
            target_ref="target",
            condition="${x > 10}",
        )

        result = flow.to_dict()

        assert result["id"] == "flow_1"
        assert result["name"] == "Test Flow"
        assert result["source_ref"] == "source"
        assert result["target_ref"] == "target"
        assert result["condition"] == "${x > 10}"

    def test_process_definition_to_dict(self):
        """Testet ProcessDefinition.to_dict()."""
        process = ProcessDefinition(
            id="process_1",
            name="Test Process",
            is_executable=True,
        )
        process.tasks.append(TaskDefinition(id="task_1", name="Task"))
        process.events.append(EventDefinition(id="event_1", event_type=EventType.START))

        result = process.to_dict()

        assert result["id"] == "process_1"
        assert result["name"] == "Test Process"
        assert result["is_executable"] is True
        assert len(result["tasks"]) == 1
        assert len(result["events"]) == 1

    def test_workflow_definition_to_dict(self):
        """Testet WorkflowDefinition.to_dict()."""
        workflow = WorkflowDefinition(
            id="workflow_1",
            name="Test Workflow",
            description="Description",
            version=1,
            trigger_type="schedule",
            trigger_config={"cron": "0 0 * * *"},
            variables={"key": "value"},
        )

        result = workflow.to_dict()

        assert result["id"] == "workflow_1"
        assert result["name"] == "Test Workflow"
        assert result["description"] == "Description"
        assert result["version"] == 1
        assert result["trigger_type"] == "schedule"
        assert result["trigger_config"]["cron"] == "0 0 * * *"
        assert result["variables"]["key"] == "value"


# =============================================================================
# Validation Result Tests
# =============================================================================

class TestValidationResult:
    """Tests fuer ValidationResult."""

    def test_add_error(self):
        """Testet Hinzufuegen von Fehlern."""
        result = ValidationResult(valid=True)

        result.add_error("TEST_ERROR", "Test error message", "element_1")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == "TEST_ERROR"
        assert result.errors[0].message == "Test error message"
        assert result.errors[0].element_id == "element_1"

    def test_add_warning(self):
        """Testet Hinzufuegen von Warnungen."""
        result = ValidationResult(valid=True)

        result.add_warning("TEST_WARNING", "Test warning message", "element_2")

        assert result.valid is True  # Warnungen aendern valid nicht
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "TEST_WARNING"
        assert result.warnings[0].message == "Test warning message"
        assert result.warnings[0].element_id == "element_2"

    def test_to_dict(self):
        """Testet Konvertierung zu Dictionary."""
        result = ValidationResult(valid=False)
        result.add_error("ERROR_1", "Error 1")
        result.add_warning("WARNING_1", "Warning 1")

        result_dict = result.to_dict()

        assert result_dict["valid"] is False
        assert len(result_dict["errors"]) == 1
        assert len(result_dict["warnings"]) == 1
        assert result_dict["errors"][0]["code"] == "ERROR_1"
        assert result_dict["warnings"][0]["code"] == "WARNING_1"


# =============================================================================
# German Error Messages Tests
# =============================================================================

class TestGermanErrorMessages:
    """Tests fuer deutsche Fehlermeldungen."""

    @pytest.fixture
    def validator(self) -> BPMNValidator:
        """Validator-Instanz."""
        return BPMNValidator()

    @pytest.fixture
    def parser(self) -> BPMNParser:
        """Parser-Instanz."""
        return BPMNParser()

    def test_invalid_xml_error_message(self, parser: BPMNParser):
        """Testet deutsche Fehlermeldung bei ungueltigem XML."""
        with pytest.raises(ValueError) as exc_info:
            parser.parse(INVALID_XML)
        assert "Ungueltiges BPMN-Format" in str(exc_info.value)

    def test_no_process_error_message(self, parser: BPMNParser):
        """Testet deutsche Fehlermeldung bei fehlendem Process."""
        with pytest.raises(ValueError) as exc_info:
            parser.parse(INVALID_NO_PROCESS)
        assert "Kein Process-Element" in str(exc_info.value)

    def test_validation_no_start_event_message(self, validator: BPMNValidator):
        """Testet deutsche Fehlermeldung bei fehlendem Start-Event."""
        result = validator.validate(INVALID_NO_START_EVENT)
        error_messages = [e.message for e in result.errors]
        assert any("Fehlender Start-Event" in msg or "Start" in msg for msg in error_messages)
