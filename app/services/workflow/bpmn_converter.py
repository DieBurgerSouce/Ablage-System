# -*- coding: utf-8 -*-
"""BPMN 2.0 Import/Export Converter für Ablage-System Workflows.

Bidirektionale Konvertierung zwischen internem Workflow-Format und BPMN 2.0 XML.
Kompatibel mit:
- Camunda Modeler
- Activiti
- jBPM
- Flowable

BPMN 2.0 Namespace: http://www.omg.org/spec/BPMN/20100524/MODEL
"""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import defusedxml.ElementTree as DefusedET
import structlog

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# BPMN 2.0 Namespaces
# =============================================================================

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"
ABLAGE_NS = "http://ablage-system.de/bpmn"

# Namespace prefixes for ElementTree
NS_MAP = {
    "bpmn": BPMN_NS,
    "bpmndi": BPMNDI_NS,
    "dc": DC_NS,
    "di": DI_NS,
    "camunda": CAMUNDA_NS,
    "ablage": ABLAGE_NS,
}

# Register namespaces for XML generation
for prefix, uri in NS_MAP.items():
    ET.register_namespace(prefix, uri)


# =============================================================================
# Type Enums and Mappings
# =============================================================================

class TaskType(str, Enum):
    """Interne Task-Typen."""
    APPROVAL = "approval"
    AUTOMATED = "automated"
    SCRIPT = "script"
    MANUAL = "manual"
    NOTIFICATION = "notification"
    CONDITION = "condition"
    ACTION = "action"
    DELAY = "delay"


class GatewayType(str, Enum):
    """Gateway-Typen."""
    EXCLUSIVE = "exclusive"
    PARALLEL = "parallel"
    INCLUSIVE = "inclusive"
    EVENT_BASED = "event_based"


class EventType(str, Enum):
    """Event-Typen."""
    START = "start"
    END = "end"
    INTERMEDIATE_CATCH = "intermediate_catch"
    INTERMEDIATE_THROW = "intermediate_throw"
    BOUNDARY = "boundary"
    TIMER = "timer"
    MESSAGE = "message"
    SIGNAL = "signal"
    ERROR = "error"


# BPMN Element zu internem Typ Mapping
BPMN_TASK_MAPPING: Dict[str, TaskType] = {
    "userTask": TaskType.APPROVAL,
    "serviceTask": TaskType.AUTOMATED,
    "scriptTask": TaskType.SCRIPT,
    "manualTask": TaskType.MANUAL,
    "sendTask": TaskType.NOTIFICATION,
    "task": TaskType.MANUAL,
    "businessRuleTask": TaskType.AUTOMATED,
    "receiveTask": TaskType.MANUAL,
}

BPMN_GATEWAY_MAPPING: Dict[str, GatewayType] = {
    "exclusiveGateway": GatewayType.EXCLUSIVE,
    "parallelGateway": GatewayType.PARALLEL,
    "inclusiveGateway": GatewayType.INCLUSIVE,
    "eventBasedGateway": GatewayType.EVENT_BASED,
}

# Interner Typ zu BPMN Mapping (Reverse)
INTERNAL_TO_BPMN_TASK: Dict[TaskType, str] = {
    TaskType.APPROVAL: "userTask",
    TaskType.AUTOMATED: "serviceTask",
    TaskType.SCRIPT: "scriptTask",
    TaskType.MANUAL: "manualTask",
    TaskType.NOTIFICATION: "sendTask",
    TaskType.CONDITION: "exclusiveGateway",
    TaskType.ACTION: "serviceTask",
    TaskType.DELAY: "intermediateCatchEvent",
}

INTERNAL_TO_BPMN_GATEWAY: Dict[GatewayType, str] = {
    GatewayType.EXCLUSIVE: "exclusiveGateway",
    GatewayType.PARALLEL: "parallelGateway",
    GatewayType.INCLUSIVE: "inclusiveGateway",
    GatewayType.EVENT_BASED: "eventBasedGateway",
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TaskDefinition:
    """Definition eines Tasks im Workflow."""
    id: str
    name: Optional[str] = None
    task_type: TaskType = TaskType.MANUAL
    description: Optional[str] = None

    # Assignment
    assignee: Optional[str] = None
    candidate_groups: List[str] = field(default_factory=list)
    candidate_users: List[str] = field(default_factory=list)

    # Configuration
    form_key: Optional[str] = None
    due_date_expression: Optional[str] = None
    priority: int = 50

    # Service Task specific
    implementation: Optional[str] = None
    topic: Optional[str] = None

    # Script Task specific
    script_format: Optional[str] = None
    script: Optional[str] = None

    # Position (for diagram)
    position_x: float = 0.0
    position_y: float = 0.0
    width: float = 100.0
    height: float = 80.0

    # Extension properties
    extension_properties: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type.value if isinstance(self.task_type, TaskType) else self.task_type,
            "description": self.description,
            "assignee": self.assignee,
            "candidate_groups": self.candidate_groups,
            "candidate_users": self.candidate_users,
            "form_key": self.form_key,
            "due_date_expression": self.due_date_expression,
            "priority": self.priority,
            "implementation": self.implementation,
            "topic": self.topic,
            "script_format": self.script_format,
            "script": self.script,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "extension_properties": self.extension_properties,
        }


@dataclass
class GatewayDefinition:
    """Definition eines Gateways."""
    id: str
    name: Optional[str] = None
    gateway_type: GatewayType = GatewayType.EXCLUSIVE
    default_flow: Optional[str] = None

    # Position
    position_x: float = 0.0
    position_y: float = 0.0
    width: float = 50.0
    height: float = 50.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "gateway_type": self.gateway_type.value if isinstance(self.gateway_type, GatewayType) else self.gateway_type,
            "default_flow": self.default_flow,
            "position_x": self.position_x,
            "position_y": self.position_y,
        }


@dataclass
class EventDefinition:
    """Definition eines Events."""
    id: str
    name: Optional[str] = None
    event_type: EventType = EventType.START

    # Timer specific
    timer_type: Optional[str] = None  # date, duration, cycle
    timer_value: Optional[str] = None

    # Message specific
    message_ref: Optional[str] = None

    # Signal specific
    signal_ref: Optional[str] = None

    # Error specific
    error_ref: Optional[str] = None

    # Boundary specific
    attached_to_ref: Optional[str] = None
    cancel_activity: bool = True

    # Position
    position_x: float = 0.0
    position_y: float = 0.0
    width: float = 36.0
    height: float = 36.0

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "timer_type": self.timer_type,
            "timer_value": self.timer_value,
            "message_ref": self.message_ref,
            "signal_ref": self.signal_ref,
            "error_ref": self.error_ref,
            "attached_to_ref": self.attached_to_ref,
            "cancel_activity": self.cancel_activity,
            "position_x": self.position_x,
            "position_y": self.position_y,
        }


@dataclass
class FlowDefinition:
    """Definition eines Sequence Flows."""
    id: str
    name: Optional[str] = None
    source_ref: str = ""
    target_ref: str = ""
    condition: Optional[str] = None
    is_default: bool = False

    # Waypoints for diagram
    waypoints: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "condition": self.condition,
            "is_default": self.is_default,
            "waypoints": self.waypoints,
        }


@dataclass
class ProcessDefinition:
    """Definition eines einzelnen Prozesses."""
    id: str
    name: Optional[str] = None
    is_executable: bool = True

    tasks: List[TaskDefinition] = field(default_factory=list)
    gateways: List[GatewayDefinition] = field(default_factory=list)
    events: List[EventDefinition] = field(default_factory=list)
    flows: List[FlowDefinition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "is_executable": self.is_executable,
            "tasks": [t.to_dict() for t in self.tasks],
            "gateways": [g.to_dict() for g in self.gateways],
            "events": [e.to_dict() for e in self.events],
            "flows": [f.to_dict() for f in self.flows],
        }


@dataclass
class WorkflowDefinition:
    """Vollständige Workflow-Definition."""
    id: str
    name: str
    description: Optional[str] = None
    version: int = 1

    # Trigger configuration
    trigger_type: str = "manual"
    trigger_config: Dict[str, Any] = field(default_factory=dict)

    # Processes
    processes: List[ProcessDefinition] = field(default_factory=list)

    # Variables
    variables: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "processes": [p.to_dict() for p in self.processes],
            "variables": self.variables,
        }


# =============================================================================
# Validation
# =============================================================================

@dataclass
class ValidationError:
    """Validierungsfehler."""
    code: str
    message: str
    element_id: Optional[str] = None
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """Ergebnis der Validierung."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def add_error(self, code: str, message: str, element_id: Optional[str] = None) -> None:
        """Fuegt einen Fehler hinzu."""
        self.errors.append(ValidationError(code, message, element_id, "error"))
        self.valid = False

    def add_warning(self, code: str, message: str, element_id: Optional[str] = None) -> None:
        """Fuegt eine Warnung hinzu."""
        self.warnings.append(ValidationError(code, message, element_id, "warning"))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "valid": self.valid,
            "errors": [{"code": e.code, "message": e.message, "element_id": e.element_id} for e in self.errors],
            "warnings": [{"code": w.code, "message": w.message, "element_id": w.element_id} for w in self.warnings],
        }


class BPMNValidator:
    """Validiert BPMN 2.0 XML Struktur und Semantik."""

    def validate(self, xml_content: str) -> ValidationResult:
        """Validiert BPMN XML und gibt Validierungsergebnis zurück.

        Args:
            xml_content: BPMN 2.0 XML String

        Returns:
            ValidationResult mit Fehlern und Warnungen
        """
        result = ValidationResult(valid=True)

        # Schema-Validierung
        schema_errors = self._validate_schema(xml_content, result)
        if schema_errors:
            return result

        # XML parsen für semantische Validierung
        try:
            root = DefusedET.fromstring(xml_content)
        except ET.ParseError as e:
            result.add_error("PARSE_ERROR", f"Ungültiges XML: {e}")
            return result

        # Semantische Validierung
        self._validate_semantics(root, result)

        return result

    def _validate_schema(self, xml_content: str, result: ValidationResult) -> bool:
        """Validiert gegen BPMN 2.0 Schema (vereinfacht).

        Returns:
            True wenn kritische Fehler gefunden
        """
        try:
            root = DefusedET.fromstring(xml_content)
        except ET.ParseError as e:
            result.add_error("SCHEMA_PARSE_ERROR", f"Ungültiges BPMN-Format: {e}")
            return True

        # Prüfen ob Root-Element "definitions" ist
        root_tag = root.tag.replace(f"{{{BPMN_NS}}}", "").replace("{http://www.omg.org/spec/BPMN/20100524/MODEL}", "")
        if root_tag != "definitions" and not root_tag.endswith("definitions"):
            result.add_error(
                "INVALID_ROOT",
                "Root-Element muss 'definitions' sein"
            )
            return True

        # Prüfen ob mindestens ein Process vorhanden
        ns = {"bpmn": BPMN_NS}
        processes = root.findall(".//bpmn:process", ns) or root.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}process")
        if not processes:
            # Auch ohne Namespace versuchen
            processes = root.findall(".//process")

        if not processes:
            result.add_error(
                "NO_PROCESS",
                "Kein Process-Element im BPMN gefunden"
            )
            return True

        return False

    def _validate_semantics(self, root: ET.Element, result: ValidationResult) -> None:
        """Validiert semantische Regeln.

        Args:
            root: Parsed XML Root
            result: ValidationResult zum Befuellen
        """
        ns = {"bpmn": BPMN_NS}

        # Alle Processes durchgehen
        processes = root.findall(".//bpmn:process", ns) or root.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}process") or root.findall(".//process")

        for process in processes:
            process_id = process.get("id", "unknown")

            # Start-Event prüfen
            start_events = (
                process.findall(".//bpmn:startEvent", ns) or
                process.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}startEvent") or
                process.findall(".//startEvent")
            )
            if not start_events:
                result.add_error(
                    "NO_START_EVENT",
                    "Fehlender Start-Event im Prozess",
                    process_id
                )

            # End-Event prüfen
            end_events = (
                process.findall(".//bpmn:endEvent", ns) or
                process.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}endEvent") or
                process.findall(".//endEvent")
            )
            if not end_events:
                result.add_warning(
                    "NO_END_EVENT",
                    "Kein End-Event im Prozess definiert",
                    process_id
                )

            # Erreichbarkeit prüfen
            self._validate_reachability(process, result)

    def _validate_reachability(self, process: ET.Element, result: ValidationResult) -> None:
        """Prüft ob alle Elemente erreichbar sind.

        Args:
            process: Process XML Element
            result: ValidationResult
        """
        ns = {"bpmn": BPMN_NS}

        # Alle Element-IDs sammeln
        all_element_ids: set = set()
        for child in process:
            elem_id = child.get("id")
            if elem_id:
                all_element_ids.add(elem_id)

        # Alle Sequence Flows sammeln
        flows = (
            process.findall(".//bpmn:sequenceFlow", ns) or
            process.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}sequenceFlow") or
            process.findall(".//sequenceFlow")
        )

        # Targets sammeln
        connected_targets: set = set()
        for flow in flows:
            source = flow.get("sourceRef")
            target = flow.get("targetRef")
            if target:
                connected_targets.add(target)

        # Start Events sammeln
        start_events = (
            process.findall(".//bpmn:startEvent", ns) or
            process.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}startEvent") or
            process.findall(".//startEvent")
        )
        start_ids = {se.get("id") for se in start_events if se.get("id")}

        # Elemente ohne eingehende Verbindungen (ausser Start-Events)
        unreachable = all_element_ids - connected_targets - start_ids

        # Sequence Flows selbst sind keine "erreichbaren" Elemente im klassischen Sinne
        flow_ids = {f.get("id") for f in flows if f.get("id")}
        unreachable -= flow_ids

        if unreachable:
            for elem_id in unreachable:
                result.add_warning(
                    "UNREACHABLE_ELEMENT",
                    f"Unerreichbare Aufgaben erkannt: {elem_id}",
                    elem_id
                )


# =============================================================================
# BPMN Parser
# =============================================================================

class BPMNParser:
    """Parst BPMN 2.0 XML zu internem Workflow-Format."""

    def parse(self, xml_content: str) -> WorkflowDefinition:
        """Parst BPMN XML und gibt WorkflowDefinition zurück.

        Args:
            xml_content: BPMN 2.0 XML String

        Returns:
            WorkflowDefinition

        Raises:
            ValueError: Bei ungültigem XML
        """
        try:
            # SECURITY: Use defusedxml to prevent XXE attacks (CWE-611)
            root = DefusedET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.error("bpmn_parse_error", **safe_error_log(e))
            raise ValueError(f"Ungültiges BPMN-Format: {e}") from e

        # Definitions-Attribute extrahieren
        definitions_id = root.get("id", f"definitions_{uuid.uuid4().hex[:8]}")
        definitions_name = root.get("name", "Importierter Workflow")

        # Processes parsen
        processes = self._parse_all_processes(root)

        if not processes:
            raise ValueError("Kein Process-Element im BPMN gefunden")

        # WorkflowDefinition erstellen
        workflow = WorkflowDefinition(
            id=definitions_id,
            name=definitions_name,
            description=root.get("{" + ABLAGE_NS + "}description"),
            version=1,
            trigger_type=self._detect_trigger_type(processes[0]) if processes else "manual",
            processes=processes,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(
            "bpmn_parsed",
            workflow_id=workflow.id,
            process_count=len(processes),
            total_tasks=sum(len(p.tasks) for p in processes),
        )

        return workflow

    def _parse_all_processes(self, root: ET.Element) -> List[ProcessDefinition]:
        """Parst alle Prozesse aus dem Root-Element."""
        processes = []
        ns = {"bpmn": BPMN_NS}

        # Mit verschiedenen Namespace-Varianten versuchen
        process_elements = (
            root.findall(".//bpmn:process", ns) or
            root.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}process") or
            root.findall(".//process")
        )

        for process_elem in process_elements:
            processes.append(self._parse_process(process_elem))

        return processes

    def _parse_process(self, process_elem: ET.Element) -> ProcessDefinition:
        """Parst einen einzelnen Process.

        Args:
            process_elem: Process XML Element

        Returns:
            ProcessDefinition
        """
        process = ProcessDefinition(
            id=process_elem.get("id", f"process_{uuid.uuid4().hex[:8]}"),
            name=process_elem.get("name"),
            is_executable=process_elem.get("isExecutable", "true").lower() == "true",
        )

        # Tasks parsen
        process.tasks = self._parse_tasks(process_elem)

        # Gateways parsen
        process.gateways = self._parse_gateways(process_elem)

        # Events parsen
        process.events = self._parse_events(process_elem)

        # Sequence Flows parsen
        process.flows = self._parse_sequence_flows(process_elem)

        return process

    def _parse_tasks(self, process_elem: ET.Element) -> List[TaskDefinition]:
        """Parst Task-Elemente (userTask, serviceTask, scriptTask)."""
        tasks = []

        task_types = [
            ("userTask", TaskType.APPROVAL),
            ("serviceTask", TaskType.AUTOMATED),
            ("scriptTask", TaskType.SCRIPT),
            ("manualTask", TaskType.MANUAL),
            ("sendTask", TaskType.NOTIFICATION),
            ("task", TaskType.MANUAL),
            ("businessRuleTask", TaskType.AUTOMATED),
            ("receiveTask", TaskType.MANUAL),
        ]

        for bpmn_type, internal_type in task_types:
            elements = self._find_elements(process_elem, bpmn_type)
            for elem in elements:
                task = self._parse_single_task(elem, internal_type)
                tasks.append(task)

        return tasks

    def _parse_single_task(self, elem: ET.Element, task_type: TaskType) -> TaskDefinition:
        """Parst ein einzelnes Task-Element."""
        camunda_prefix = f"{{{CAMUNDA_NS}}}"

        task = TaskDefinition(
            id=elem.get("id", f"task_{uuid.uuid4().hex[:8]}"),
            name=elem.get("name"),
            task_type=task_type,
        )

        # User Task spezifisch (Camunda-Attribute)
        if task_type == TaskType.APPROVAL:
            task.assignee = elem.get(f"{camunda_prefix}assignee")
            task.form_key = elem.get(f"{camunda_prefix}formKey")
            task.due_date_expression = elem.get(f"{camunda_prefix}dueDate")

            priority_str = elem.get(f"{camunda_prefix}priority")
            if priority_str:
                try:
                    task.priority = int(priority_str)
                except ValueError:
                    pass

            # Candidate Groups
            candidate_groups = elem.get(f"{camunda_prefix}candidateGroups")
            if candidate_groups:
                task.candidate_groups = [g.strip() for g in candidate_groups.split(",")]

            # Candidate Users
            candidate_users = elem.get(f"{camunda_prefix}candidateUsers")
            if candidate_users:
                task.candidate_users = [u.strip() for u in candidate_users.split(",")]

        # Service Task spezifisch
        elif task_type == TaskType.AUTOMATED:
            task.implementation = elem.get("implementation")
            task.topic = elem.get(f"{camunda_prefix}topic")

            if not task.implementation:
                task.implementation = elem.get(f"{camunda_prefix}class")
            if not task.implementation:
                task.implementation = elem.get(f"{camunda_prefix}expression")

        # Script Task spezifisch
        elif task_type == TaskType.SCRIPT:
            task.script_format = elem.get("scriptFormat")
            script_elem = self._find_element(elem, "script")
            if script_elem is not None and script_elem.text:
                task.script = script_elem.text

        # Extension Properties parsen
        task.extension_properties = self._parse_extension_properties(elem)

        return task

    def _parse_gateways(self, process_elem: ET.Element) -> List[GatewayDefinition]:
        """Parst Gateway-Elemente (exclusive, parallel, inclusive)."""
        gateways = []

        gateway_types = [
            ("exclusiveGateway", GatewayType.EXCLUSIVE),
            ("parallelGateway", GatewayType.PARALLEL),
            ("inclusiveGateway", GatewayType.INCLUSIVE),
            ("eventBasedGateway", GatewayType.EVENT_BASED),
        ]

        for bpmn_type, internal_type in gateway_types:
            elements = self._find_elements(process_elem, bpmn_type)
            for elem in elements:
                gateway = GatewayDefinition(
                    id=elem.get("id", f"gateway_{uuid.uuid4().hex[:8]}"),
                    name=elem.get("name"),
                    gateway_type=internal_type,
                    default_flow=elem.get("default"),
                )
                gateways.append(gateway)

        return gateways

    def _parse_events(self, process_elem: ET.Element) -> List[EventDefinition]:
        """Parst Event-Elemente (start, end, intermediate)."""
        events = []

        event_types = [
            ("startEvent", EventType.START),
            ("endEvent", EventType.END),
            ("intermediateCatchEvent", EventType.INTERMEDIATE_CATCH),
            ("intermediateThrowEvent", EventType.INTERMEDIATE_THROW),
            ("boundaryEvent", EventType.BOUNDARY),
        ]

        for bpmn_type, internal_type in event_types:
            elements = self._find_elements(process_elem, bpmn_type)
            for elem in elements:
                event = self._parse_single_event(elem, internal_type)
                events.append(event)

        return events

    def _parse_single_event(self, elem: ET.Element, event_type: EventType) -> EventDefinition:
        """Parst ein einzelnes Event-Element."""
        event = EventDefinition(
            id=elem.get("id", f"event_{uuid.uuid4().hex[:8]}"),
            name=elem.get("name"),
            event_type=event_type,
        )

        # Timer Event Definition
        timer_def = self._find_element(elem, "timerEventDefinition")
        if timer_def is not None:
            time_date = self._find_element(timer_def, "timeDate")
            time_duration = self._find_element(timer_def, "timeDuration")
            time_cycle = self._find_element(timer_def, "timeCycle")

            if time_date is not None and time_date.text:
                event.timer_type = "date"
                event.timer_value = time_date.text
            elif time_duration is not None and time_duration.text:
                event.timer_type = "duration"
                event.timer_value = time_duration.text
            elif time_cycle is not None and time_cycle.text:
                event.timer_type = "cycle"
                event.timer_value = time_cycle.text

        # Message Event Definition
        message_def = self._find_element(elem, "messageEventDefinition")
        if message_def is not None:
            event.message_ref = message_def.get("messageRef")

        # Signal Event Definition
        signal_def = self._find_element(elem, "signalEventDefinition")
        if signal_def is not None:
            event.signal_ref = signal_def.get("signalRef")

        # Error Event Definition
        error_def = self._find_element(elem, "errorEventDefinition")
        if error_def is not None:
            event.error_ref = error_def.get("errorRef")

        # Boundary Event specific
        if event_type == EventType.BOUNDARY:
            event.attached_to_ref = elem.get("attachedToRef")
            event.cancel_activity = elem.get("cancelActivity", "true").lower() == "true"

        return event

    def _parse_sequence_flows(self, process_elem: ET.Element) -> List[FlowDefinition]:
        """Parst Sequence Flow Verbindungen."""
        flows = []

        flow_elements = self._find_elements(process_elem, "sequenceFlow")
        for elem in flow_elements:
            flow = FlowDefinition(
                id=elem.get("id", f"flow_{uuid.uuid4().hex[:8]}"),
                name=elem.get("name"),
                source_ref=elem.get("sourceRef", ""),
                target_ref=elem.get("targetRef", ""),
            )

            # Condition Expression
            condition_elem = self._find_element(elem, "conditionExpression")
            if condition_elem is not None and condition_elem.text:
                flow.condition = condition_elem.text

            flows.append(flow)

        return flows

    def _parse_extension_properties(self, elem: ET.Element) -> Dict[str, str]:
        """Parst Extension Properties (Camunda-kompatibel)."""
        properties = {}

        ext_elem = self._find_element(elem, "extensionElements")
        if ext_elem is not None:
            # Camunda properties
            for prop in ext_elem.findall(f".//{{{CAMUNDA_NS}}}property"):
                name = prop.get("name")
                value = prop.get("value")
                if name and value:
                    properties[name] = value

        return properties

    def _find_elements(self, parent: ET.Element, tag_name: str) -> List[ET.Element]:
        """Findet Elemente mit verschiedenen Namespace-Varianten."""
        # Mit BPMN Namespace
        elements = parent.findall(f".//{{{BPMN_NS}}}{tag_name}")
        if elements:
            return elements

        # Mit anderem Namespace-Format
        elements = parent.findall(f".//{{http://www.omg.org/spec/BPMN/20100524/MODEL}}{tag_name}")
        if elements:
            return elements

        # Ohne Namespace (direktes Child)
        elements = parent.findall(f".//{tag_name}")
        if elements:
            return elements

        # Direkte Children ohne Namespace
        elements = [child for child in parent if child.tag.endswith(tag_name)]
        return elements

    def _find_element(self, parent: ET.Element, tag_name: str) -> Optional[ET.Element]:
        """Findet ein einzelnes Element."""
        elements = self._find_elements(parent, tag_name)
        return elements[0] if elements else None

    def _detect_trigger_type(self, process: ProcessDefinition) -> str:
        """Erkennt den Trigger-Typ basierend auf Start-Events."""
        for event in process.events:
            if event.event_type == EventType.START:
                if event.timer_type:
                    return "schedule"
                if event.message_ref:
                    return "webhook"
                if event.signal_ref:
                    return "document_event"
        return "manual"


# =============================================================================
# BPMN Exporter
# =============================================================================

class BPMNExporter:
    """Exportiert internes Workflow-Format zu BPMN 2.0 XML."""

    def export(self, workflow: WorkflowDefinition) -> str:
        """Exportiert Workflow zu BPMN 2.0 XML String.

        Args:
            workflow: WorkflowDefinition

        Returns:
            BPMN 2.0 XML String
        """
        # Root: definitions
        definitions = ET.Element(f"{{{BPMN_NS}}}definitions")
        definitions.set("xmlns:bpmn", BPMN_NS)
        definitions.set("xmlns:bpmndi", BPMNDI_NS)
        definitions.set("xmlns:dc", DC_NS)
        definitions.set("xmlns:di", DI_NS)
        definitions.set("xmlns:camunda", CAMUNDA_NS)
        definitions.set("id", f"Definitions_{workflow.id}")
        definitions.set("targetNamespace", ABLAGE_NS)
        definitions.set("exporter", "Ablage-System BPMN Converter")
        definitions.set("exporterVersion", "1.0")

        # Processes erstellen
        for process in workflow.processes:
            process_elem = self._create_process(process)
            definitions.append(process_elem)

        # BPMN Diagram erstellen
        if workflow.processes:
            diagram = self._create_diagram(workflow)
            definitions.append(diagram)

        # XML generieren
        ET.indent(definitions)
        xml_string = ET.tostring(definitions, encoding="unicode")

        # XML Declaration hinzufuegen
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'

        logger.info(
            "bpmn_exported",
            workflow_id=workflow.id,
            process_count=len(workflow.processes),
        )

        return xml_declaration + xml_string

    def _create_process(self, process: ProcessDefinition) -> ET.Element:
        """Erstellt BPMN Process Element."""
        process_elem = ET.Element(f"{{{BPMN_NS}}}process")
        process_elem.set("id", process.id)
        if process.name:
            process_elem.set("name", process.name)
        process_elem.set("isExecutable", str(process.is_executable).lower())

        # Events hinzufuegen
        for event in process.events:
            event_elem = self._create_event(event)
            process_elem.append(event_elem)

        # Tasks hinzufuegen
        for task in process.tasks:
            task_elem = self._create_task(task)
            process_elem.append(task_elem)

        # Gateways hinzufuegen
        for gateway in process.gateways:
            gateway_elem = self._create_gateway(gateway)
            process_elem.append(gateway_elem)

        # Sequence Flows hinzufuegen
        for flow in process.flows:
            flow_elem = self._create_sequence_flow(flow)
            process_elem.append(flow_elem)

        return process_elem

    def _create_event(self, event: EventDefinition) -> ET.Element:
        """Erstellt BPMN Event Element."""
        # Event-Typ zu BPMN-Tag
        event_type_map = {
            EventType.START: "startEvent",
            EventType.END: "endEvent",
            EventType.INTERMEDIATE_CATCH: "intermediateCatchEvent",
            EventType.INTERMEDIATE_THROW: "intermediateThrowEvent",
            EventType.BOUNDARY: "boundaryEvent",
            EventType.TIMER: "intermediateCatchEvent",
            EventType.MESSAGE: "intermediateCatchEvent",
            EventType.SIGNAL: "intermediateCatchEvent",
            EventType.ERROR: "boundaryEvent",
        }

        event_type = event.event_type
        if isinstance(event_type, str):
            event_type = EventType(event_type)

        tag_name = event_type_map.get(event_type, "startEvent")
        event_elem = ET.Element(f"{{{BPMN_NS}}}{tag_name}")
        event_elem.set("id", event.id)

        if event.name:
            event_elem.set("name", event.name)

        # Boundary Event specific
        if event_type == EventType.BOUNDARY and event.attached_to_ref:
            event_elem.set("attachedToRef", event.attached_to_ref)
            event_elem.set("cancelActivity", str(event.cancel_activity).lower())

        # Timer Event Definition
        if event.timer_type and event.timer_value:
            timer_def = ET.SubElement(event_elem, f"{{{BPMN_NS}}}timerEventDefinition")
            if event.timer_type == "date":
                time_elem = ET.SubElement(timer_def, f"{{{BPMN_NS}}}timeDate")
            elif event.timer_type == "duration":
                time_elem = ET.SubElement(timer_def, f"{{{BPMN_NS}}}timeDuration")
            else:  # cycle
                time_elem = ET.SubElement(timer_def, f"{{{BPMN_NS}}}timeCycle")
            time_elem.text = event.timer_value

        # Message Event Definition
        if event.message_ref:
            message_def = ET.SubElement(event_elem, f"{{{BPMN_NS}}}messageEventDefinition")
            message_def.set("messageRef", event.message_ref)

        # Signal Event Definition
        if event.signal_ref:
            signal_def = ET.SubElement(event_elem, f"{{{BPMN_NS}}}signalEventDefinition")
            signal_def.set("signalRef", event.signal_ref)

        # Error Event Definition
        if event.error_ref:
            error_def = ET.SubElement(event_elem, f"{{{BPMN_NS}}}errorEventDefinition")
            error_def.set("errorRef", event.error_ref)

        return event_elem

    def _create_task(self, task: TaskDefinition) -> ET.Element:
        """Erstellt BPMN Task Element."""
        task_type = task.task_type
        if isinstance(task_type, str):
            task_type = TaskType(task_type)

        tag_name = INTERNAL_TO_BPMN_TASK.get(task_type, "userTask")
        task_elem = ET.Element(f"{{{BPMN_NS}}}{tag_name}")
        task_elem.set("id", task.id)

        if task.name:
            task_elem.set("name", task.name)

        # User Task specific (Camunda attributes)
        if task_type == TaskType.APPROVAL:
            if task.assignee:
                task_elem.set(f"{{{CAMUNDA_NS}}}assignee", task.assignee)
            if task.form_key:
                task_elem.set(f"{{{CAMUNDA_NS}}}formKey", task.form_key)
            if task.due_date_expression:
                task_elem.set(f"{{{CAMUNDA_NS}}}dueDate", task.due_date_expression)
            if task.priority != 50:
                task_elem.set(f"{{{CAMUNDA_NS}}}priority", str(task.priority))
            if task.candidate_groups:
                task_elem.set(f"{{{CAMUNDA_NS}}}candidateGroups", ",".join(task.candidate_groups))
            if task.candidate_users:
                task_elem.set(f"{{{CAMUNDA_NS}}}candidateUsers", ",".join(task.candidate_users))

        # Service Task specific
        elif task_type == TaskType.AUTOMATED:
            if task.implementation:
                task_elem.set("implementation", task.implementation)
            if task.topic:
                task_elem.set(f"{{{CAMUNDA_NS}}}topic", task.topic)

        # Script Task specific
        elif task_type == TaskType.SCRIPT:
            if task.script_format:
                task_elem.set("scriptFormat", task.script_format)
            if task.script:
                script_elem = ET.SubElement(task_elem, f"{{{BPMN_NS}}}script")
                script_elem.text = task.script

        # Extension Properties
        if task.extension_properties:
            ext_elements = ET.SubElement(task_elem, f"{{{BPMN_NS}}}extensionElements")
            properties = ET.SubElement(ext_elements, f"{{{CAMUNDA_NS}}}properties")
            for name, value in task.extension_properties.items():
                prop = ET.SubElement(properties, f"{{{CAMUNDA_NS}}}property")
                prop.set("name", name)
                prop.set("value", value)

        return task_elem

    def _create_gateway(self, gateway: GatewayDefinition) -> ET.Element:
        """Erstellt BPMN Gateway Element."""
        gateway_type = gateway.gateway_type
        if isinstance(gateway_type, str):
            gateway_type = GatewayType(gateway_type)

        tag_name = INTERNAL_TO_BPMN_GATEWAY.get(gateway_type, "exclusiveGateway")
        gateway_elem = ET.Element(f"{{{BPMN_NS}}}{tag_name}")
        gateway_elem.set("id", gateway.id)

        if gateway.name:
            gateway_elem.set("name", gateway.name)

        if gateway.default_flow:
            gateway_elem.set("default", gateway.default_flow)

        return gateway_elem

    def _create_sequence_flow(self, flow: FlowDefinition) -> ET.Element:
        """Erstellt BPMN Sequence Flow Element."""
        flow_elem = ET.Element(f"{{{BPMN_NS}}}sequenceFlow")
        flow_elem.set("id", flow.id)
        flow_elem.set("sourceRef", flow.source_ref)
        flow_elem.set("targetRef", flow.target_ref)

        if flow.name:
            flow_elem.set("name", flow.name)

        if flow.condition:
            cond_elem = ET.SubElement(flow_elem, f"{{{BPMN_NS}}}conditionExpression")
            cond_elem.set("{http://www.w3.org/2001/XMLSchema-instance}type", "tFormalExpression")
            cond_elem.text = flow.condition

        return flow_elem

    def _create_diagram(self, workflow: WorkflowDefinition) -> ET.Element:
        """Erstellt BPMN Diagram (Visual Layout) Element."""
        diagram = ET.Element(f"{{{BPMNDI_NS}}}BPMNDiagram")
        diagram.set("id", f"BPMNDiagram_{workflow.id}")

        for process in workflow.processes:
            plane = ET.SubElement(diagram, f"{{{BPMNDI_NS}}}BPMNPlane")
            plane.set("id", f"BPMNPlane_{process.id}")
            plane.set("bpmnElement", process.id)

            # Shapes für Events
            for event in process.events:
                shape = self._create_shape(
                    event.id,
                    event.position_x,
                    event.position_y,
                    event.width,
                    event.height
                )
                plane.append(shape)

            # Shapes für Tasks
            for task in process.tasks:
                shape = self._create_shape(
                    task.id,
                    task.position_x,
                    task.position_y,
                    task.width,
                    task.height
                )
                plane.append(shape)

            # Shapes für Gateways
            for gateway in process.gateways:
                shape = self._create_shape(
                    gateway.id,
                    gateway.position_x,
                    gateway.position_y,
                    gateway.width,
                    gateway.height
                )
                plane.append(shape)

            # Edges für Flows
            for flow in process.flows:
                edge = self._create_edge(flow)
                plane.append(edge)

        return diagram

    def _create_shape(
        self,
        element_id: str,
        x: float,
        y: float,
        width: float,
        height: float
    ) -> ET.Element:
        """Erstellt BPMN Shape Element."""
        shape = ET.Element(f"{{{BPMNDI_NS}}}BPMNShape")
        shape.set("id", f"{element_id}_di")
        shape.set("bpmnElement", element_id)

        bounds = ET.SubElement(shape, f"{{{DC_NS}}}Bounds")
        bounds.set("x", str(x))
        bounds.set("y", str(y))
        bounds.set("width", str(width))
        bounds.set("height", str(height))

        return shape

    def _create_edge(self, flow: FlowDefinition) -> ET.Element:
        """Erstellt BPMN Edge Element."""
        edge = ET.Element(f"{{{BPMNDI_NS}}}BPMNEdge")
        edge.set("id", f"{flow.id}_di")
        edge.set("bpmnElement", flow.id)

        # Waypoints
        if flow.waypoints:
            for x, y in flow.waypoints:
                waypoint = ET.SubElement(edge, f"{{{DI_NS}}}waypoint")
                waypoint.set("x", str(x))
                waypoint.set("y", str(y))
        else:
            # Default waypoints wenn keine vorhanden
            waypoint1 = ET.SubElement(edge, f"{{{DI_NS}}}waypoint")
            waypoint1.set("x", "0")
            waypoint1.set("y", "0")
            waypoint2 = ET.SubElement(edge, f"{{{DI_NS}}}waypoint")
            waypoint2.set("x", "100")
            waypoint2.set("y", "0")

        return edge


# =============================================================================
# Main Converter
# =============================================================================

class BPMNConverter:
    """Hauptklasse für BPMN 2.0 Import/Export.

    Handles bidirektionale Konvertierung zwischen internem
    Workflow-Format und BPMN 2.0 XML.

    Kompatibel mit:
    - Camunda Modeler
    - Activiti
    - jBPM
    - Flowable

    Usage:
        converter = BPMNConverter()

        # Import
        workflow = converter.import_bpmn(xml_content)

        # Export
        xml_content = converter.export_bpmn(workflow)

        # Validate
        result = converter.validate(xml_content)
    """

    def __init__(self) -> None:
        """Initialisiert den BPMNConverter."""
        self.parser = BPMNParser()
        self.exporter = BPMNExporter()
        self.validator = BPMNValidator()

    def import_bpmn(self, xml_content: str) -> WorkflowDefinition:
        """Importiert BPMN 2.0 XML und gibt WorkflowDefinition zurück.

        Args:
            xml_content: BPMN 2.0 XML String

        Returns:
            WorkflowDefinition

        Raises:
            ValueError: Bei ungültigem BPMN-Format
        """
        return self.parser.parse(xml_content)

    def export_bpmn(self, workflow: WorkflowDefinition) -> str:
        """Exportiert WorkflowDefinition zu BPMN 2.0 XML.

        Args:
            workflow: WorkflowDefinition

        Returns:
            BPMN 2.0 XML String
        """
        return self.exporter.export(workflow)

    def validate(self, xml_content: str) -> ValidationResult:
        """Validiert BPMN 2.0 XML.

        Args:
            xml_content: BPMN 2.0 XML String

        Returns:
            ValidationResult mit Fehlern und Warnungen
        """
        return self.validator.validate(xml_content)

    def convert_from_internal(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        workflow_id: str,
        workflow_name: str,
        trigger_type: str = "manual",
        trigger_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Konvertiert internes ReactFlow-Format zu BPMN 2.0 XML.

        Args:
            nodes: ReactFlow Nodes
            edges: ReactFlow Edges
            workflow_id: Workflow ID
            workflow_name: Workflow Name
            trigger_type: Trigger-Typ
            trigger_config: Trigger-Konfiguration

        Returns:
            BPMN 2.0 XML String
        """
        # Workflow-Definition aus internem Format erstellen
        workflow = self._convert_internal_to_workflow(
            nodes=nodes,
            edges=edges,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
        )

        return self.exporter.export(workflow)

    def convert_to_internal(
        self,
        xml_content: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Konvertiert BPMN 2.0 XML zu internem ReactFlow-Format.

        Args:
            xml_content: BPMN 2.0 XML String

        Returns:
            Tuple (nodes, edges) im ReactFlow-Format
        """
        workflow = self.parser.parse(xml_content)
        return self._convert_workflow_to_internal(workflow)

    def _convert_internal_to_workflow(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        workflow_id: str,
        workflow_name: str,
        trigger_type: str,
        trigger_config: Optional[Dict[str, Any]],
    ) -> WorkflowDefinition:
        """Konvertiert internes Format zu WorkflowDefinition."""
        process = ProcessDefinition(
            id=f"Process_{workflow_id}",
            name=workflow_name,
            is_executable=True,
        )

        # Node-Type Mapping
        node_type_map = {
            "trigger": "startEvent",
            "startEvent": "startEvent",
            "endEvent": "endEvent",
            "end": "endEvent",
            "condition": "exclusiveGateway",
            "branch": "exclusiveGateway",
            "parallel": "parallelGateway",
            "action": "serviceTask",
            "task": "userTask",
            "userTask": "userTask",
            "serviceTask": "serviceTask",
            "scriptTask": "scriptTask",
            "delay": "intermediateCatchEvent",
            "timer": "intermediateCatchEvent",
        }

        # Nodes zu BPMN-Elementen konvertieren
        for node in nodes:
            node_id = node.get("id", f"node_{uuid.uuid4().hex[:8]}")
            node_type = node.get("type", "task")
            node_data = node.get("data", {})
            position = node.get("position", {"x": 0, "y": 0})

            bpmn_type = node_type_map.get(node_type, "userTask")

            # Events
            if bpmn_type in ["startEvent", "endEvent", "intermediateCatchEvent"]:
                event = EventDefinition(
                    id=node_id,
                    name=node_data.get("label"),
                    position_x=position.get("x", 0),
                    position_y=position.get("y", 0),
                )

                if bpmn_type == "startEvent":
                    event.event_type = EventType.START
                elif bpmn_type == "endEvent":
                    event.event_type = EventType.END
                else:
                    event.event_type = EventType.INTERMEDIATE_CATCH
                    # Timer-Daten
                    if node_data.get("timerType"):
                        event.timer_type = node_data["timerType"]
                        event.timer_value = node_data.get("timerValue")

                process.events.append(event)

            # Gateways
            elif bpmn_type in ["exclusiveGateway", "parallelGateway", "inclusiveGateway"]:
                gateway = GatewayDefinition(
                    id=node_id,
                    name=node_data.get("label"),
                    position_x=position.get("x", 0),
                    position_y=position.get("y", 0),
                )

                if bpmn_type == "parallelGateway":
                    gateway.gateway_type = GatewayType.PARALLEL
                elif bpmn_type == "inclusiveGateway":
                    gateway.gateway_type = GatewayType.INCLUSIVE
                else:
                    gateway.gateway_type = GatewayType.EXCLUSIVE

                process.gateways.append(gateway)

            # Tasks
            else:
                task = TaskDefinition(
                    id=node_id,
                    name=node_data.get("label"),
                    position_x=position.get("x", 0),
                    position_y=position.get("y", 0),
                )

                if bpmn_type == "serviceTask":
                    task.task_type = TaskType.AUTOMATED
                    task.implementation = node_data.get("implementation")
                elif bpmn_type == "scriptTask":
                    task.task_type = TaskType.SCRIPT
                    task.script = node_data.get("script")
                    task.script_format = node_data.get("scriptFormat", "javascript")
                else:
                    task.task_type = TaskType.APPROVAL
                    task.assignee = node_data.get("assignee")
                    task.candidate_groups = node_data.get("candidateGroups", [])
                    task.form_key = node_data.get("formKey")

                process.tasks.append(task)

        # Edges zu Sequence Flows
        for edge in edges:
            edge_id = edge.get("id", f"flow_{uuid.uuid4().hex[:8]}")

            flow = FlowDefinition(
                id=edge_id,
                name=edge.get("label"),
                source_ref=edge.get("source", ""),
                target_ref=edge.get("target", ""),
            )

            # Condition
            edge_data = edge.get("data", {})
            if edge_data.get("condition"):
                flow.condition = edge_data["condition"]

            process.flows.append(flow)

        return WorkflowDefinition(
            id=workflow_id,
            name=workflow_name,
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            processes=[process],
        )

    def _convert_workflow_to_internal(
        self,
        workflow: WorkflowDefinition
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Konvertiert WorkflowDefinition zu internem Format."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        # ReactFlow Node-Type Mapping (Reverse)
        task_type_to_node = {
            TaskType.APPROVAL: "userTask",
            TaskType.AUTOMATED: "serviceTask",
            TaskType.SCRIPT: "scriptTask",
            TaskType.MANUAL: "manualTask",
            TaskType.NOTIFICATION: "sendTask",
            TaskType.CONDITION: "condition",
            TaskType.ACTION: "action",
            TaskType.DELAY: "delay",
        }

        event_type_to_node = {
            EventType.START: "trigger",
            EventType.END: "end",
            EventType.INTERMEDIATE_CATCH: "timer",
            EventType.INTERMEDIATE_THROW: "timer",
            EventType.BOUNDARY: "boundaryEvent",
            EventType.TIMER: "timer",
            EventType.MESSAGE: "message",
            EventType.SIGNAL: "signal",
            EventType.ERROR: "error",
        }

        gateway_type_to_node = {
            GatewayType.EXCLUSIVE: "condition",
            GatewayType.PARALLEL: "parallel",
            GatewayType.INCLUSIVE: "inclusive",
            GatewayType.EVENT_BASED: "eventBased",
        }

        for process in workflow.processes:
            # Events zu Nodes
            for event in process.events:
                event_type = event.event_type
                if isinstance(event_type, str):
                    event_type = EventType(event_type)

                node_type = event_type_to_node.get(event_type, "event")

                node = {
                    "id": event.id,
                    "type": node_type,
                    "position": {
                        "x": event.position_x,
                        "y": event.position_y,
                    },
                    "data": {
                        "label": event.name or event.id,
                    },
                }

                # Timer-Daten
                if event.timer_type:
                    node["data"]["timerType"] = event.timer_type
                    node["data"]["timerValue"] = event.timer_value

                nodes.append(node)

            # Tasks zu Nodes
            for task in process.tasks:
                task_type = task.task_type
                if isinstance(task_type, str):
                    task_type = TaskType(task_type)

                node_type = task_type_to_node.get(task_type, "task")

                node = {
                    "id": task.id,
                    "type": node_type,
                    "position": {
                        "x": task.position_x,
                        "y": task.position_y,
                    },
                    "data": {
                        "label": task.name or task.id,
                    },
                }

                # Task-spezifische Daten
                if task.assignee:
                    node["data"]["assignee"] = task.assignee
                if task.candidate_groups:
                    node["data"]["candidateGroups"] = task.candidate_groups
                if task.form_key:
                    node["data"]["formKey"] = task.form_key
                if task.implementation:
                    node["data"]["implementation"] = task.implementation
                if task.script:
                    node["data"]["script"] = task.script
                    node["data"]["scriptFormat"] = task.script_format

                nodes.append(node)

            # Gateways zu Nodes
            for gateway in process.gateways:
                gateway_type = gateway.gateway_type
                if isinstance(gateway_type, str):
                    gateway_type = GatewayType(gateway_type)

                node_type = gateway_type_to_node.get(gateway_type, "condition")

                node = {
                    "id": gateway.id,
                    "type": node_type,
                    "position": {
                        "x": gateway.position_x,
                        "y": gateway.position_y,
                    },
                    "data": {
                        "label": gateway.name or gateway.id,
                    },
                }

                if gateway.default_flow:
                    node["data"]["defaultFlow"] = gateway.default_flow

                nodes.append(node)

            # Flows zu Edges
            for flow in process.flows:
                edge = {
                    "id": flow.id,
                    "source": flow.source_ref,
                    "target": flow.target_ref,
                }

                if flow.name:
                    edge["label"] = flow.name

                if flow.condition:
                    edge["data"] = {"condition": flow.condition}

                edges.append(edge)

        return nodes, edges


# =============================================================================
# Factory Functions
# =============================================================================

def get_bpmn_converter() -> BPMNConverter:
    """Factory Function für BPMNConverter."""
    return BPMNConverter()


def get_bpmn_parser() -> BPMNParser:
    """Factory Function für BPMNParser."""
    return BPMNParser()


def get_bpmn_exporter() -> BPMNExporter:
    """Factory Function für BPMNExporter."""
    return BPMNExporter()


def get_bpmn_validator() -> BPMNValidator:
    """Factory Function für BPMNValidator."""
    return BPMNValidator()
