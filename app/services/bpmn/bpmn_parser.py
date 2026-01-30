"""BPMN 2.0 XML Parser und Generator.

Parst BPMN 2.0 XML und konvertiert es in eine JSONB-freundliche Struktur.
Unterstuetzt:
- Start/End Events
- User Tasks, Service Tasks, Script Tasks
- Exclusive, Parallel, Inclusive Gateways
- Sequence Flows mit Conditions
- Timer Events (Duration, Date, Cycle)
- Subprocesses

BPMN 2.0 Namespace: http://www.omg.org/spec/BPMN/20100524/MODEL
"""

import re
import xml.etree.ElementTree as ET
import defusedxml.ElementTree as DefusedET
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum
import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# BPMN 2.0 Namespaces
BPMN_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI_NS = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC_NS = "{http://www.omg.org/spec/DD/20100524/DC}"


class ElementType(str, Enum):
    """BPMN Element-Typen."""
    # Events
    START_EVENT = "startEvent"
    END_EVENT = "endEvent"
    INTERMEDIATE_CATCH_EVENT = "intermediateCatchEvent"
    INTERMEDIATE_THROW_EVENT = "intermediateThrowEvent"
    BOUNDARY_EVENT = "boundaryEvent"

    # Tasks
    TASK = "task"
    USER_TASK = "userTask"
    SERVICE_TASK = "serviceTask"
    SCRIPT_TASK = "scriptTask"
    SEND_TASK = "sendTask"
    RECEIVE_TASK = "receiveTask"
    MANUAL_TASK = "manualTask"
    BUSINESS_RULE_TASK = "businessRuleTask"

    # Gateways
    EXCLUSIVE_GATEWAY = "exclusiveGateway"
    PARALLEL_GATEWAY = "parallelGateway"
    INCLUSIVE_GATEWAY = "inclusiveGateway"
    EVENT_BASED_GATEWAY = "eventBasedGateway"

    # Flows
    SEQUENCE_FLOW = "sequenceFlow"

    # Subprocess
    SUB_PROCESS = "subProcess"
    CALL_ACTIVITY = "callActivity"


@dataclass
class BPMNElement:
    """Parsed BPMN Element."""
    id: str
    type: str
    name: Optional[str] = None

    # Flow-Referenzen
    incoming: List[str] = field(default_factory=list)
    outgoing: List[str] = field(default_factory=list)

    # Sequence Flow spezifisch
    source_ref: Optional[str] = None
    target_ref: Optional[str] = None
    condition: Optional[str] = None
    is_default: bool = False

    # Task spezifisch
    assignee: Optional[str] = None
    candidate_groups: List[str] = field(default_factory=list)
    candidate_users: List[str] = field(default_factory=list)
    form_key: Optional[str] = None
    due_date_expression: Optional[str] = None
    priority_expression: Optional[str] = None

    # Service Task spezifisch
    implementation: Optional[str] = None  # z.B. "celery:task_name"
    topic: Optional[str] = None  # Fuer External Tasks

    # Script Task spezifisch
    script_format: Optional[str] = None
    script: Optional[str] = None

    # Timer spezifisch
    timer_type: Optional[str] = None  # date, duration, cycle
    timer_value: Optional[str] = None

    # Boundary Event spezifisch
    attached_to_ref: Optional[str] = None
    cancel_activity: bool = True

    # Gateway spezifisch
    default_flow: Optional[str] = None

    # Subprocess spezifisch
    elements: List["BPMNElement"] = field(default_factory=list)

    # Extension Properties (Custom)
    extension_properties: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSONB."""
        result = asdict(self)
        # Entferne None-Werte und leere Listen
        return {k: v for k, v in result.items()
                if v is not None and v != [] and v != {}}


@dataclass
class BPMNProcess:
    """Parsed BPMN Process."""
    id: str
    name: Optional[str] = None
    is_executable: bool = True
    elements: List[BPMNElement] = field(default_factory=list)

    # Maps fuer schnellen Zugriff
    _elements_by_id: Dict[str, BPMNElement] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self):
        """Build element index."""
        self._build_index()

    def _build_index(self):
        """Index der Elemente nach ID aufbauen."""
        self._elements_by_id = {e.id: e for e in self.elements}

    def get_element(self, element_id: str) -> Optional[BPMNElement]:
        """Element nach ID abrufen."""
        return self._elements_by_id.get(element_id)

    def get_start_events(self) -> List[BPMNElement]:
        """Alle Start-Events zurueckgeben."""
        return [e for e in self.elements
                if e.type == ElementType.START_EVENT.value]

    def get_outgoing_elements(self, element_id: str) -> List[BPMNElement]:
        """Nachfolger-Elemente fuer ein Element."""
        element = self.get_element(element_id)
        if not element:
            return []

        result = []
        for flow_id in element.outgoing:
            flow = self.get_element(flow_id)
            if flow and flow.target_ref:
                target = self.get_element(flow.target_ref)
                if target:
                    result.append(target)
        return result

    def get_incoming_flows(self, element_id: str) -> List[BPMNElement]:
        """Eingehende Sequence Flows fuer ein Element."""
        element = self.get_element(element_id)
        if not element:
            return []

        return [self.get_element(flow_id) for flow_id in element.incoming
                if self.get_element(flow_id)]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer JSONB-Speicherung."""
        return {
            "id": self.id,
            "name": self.name,
            "is_executable": self.is_executable,
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BPMNProcess":
        """Erstellt BPMNProcess aus Dictionary."""
        elements = [
            BPMNElement(**elem_data)
            for elem_data in data.get("elements", [])
        ]
        process = cls(
            id=data["id"],
            name=data.get("name"),
            is_executable=data.get("is_executable", True),
            elements=elements,
        )
        process._build_index()
        return process


class BPMNParser:
    """BPMN 2.0 XML Parser.

    Parst BPMN XML und erstellt eine BPMNProcess-Struktur.
    """

    TASK_TYPES = {
        f"{BPMN_NS}task": ElementType.TASK,
        f"{BPMN_NS}userTask": ElementType.USER_TASK,
        f"{BPMN_NS}serviceTask": ElementType.SERVICE_TASK,
        f"{BPMN_NS}scriptTask": ElementType.SCRIPT_TASK,
        f"{BPMN_NS}sendTask": ElementType.SEND_TASK,
        f"{BPMN_NS}receiveTask": ElementType.RECEIVE_TASK,
        f"{BPMN_NS}manualTask": ElementType.MANUAL_TASK,
        f"{BPMN_NS}businessRuleTask": ElementType.BUSINESS_RULE_TASK,
    }

    GATEWAY_TYPES = {
        f"{BPMN_NS}exclusiveGateway": ElementType.EXCLUSIVE_GATEWAY,
        f"{BPMN_NS}parallelGateway": ElementType.PARALLEL_GATEWAY,
        f"{BPMN_NS}inclusiveGateway": ElementType.INCLUSIVE_GATEWAY,
        f"{BPMN_NS}eventBasedGateway": ElementType.EVENT_BASED_GATEWAY,
    }

    EVENT_TYPES = {
        f"{BPMN_NS}startEvent": ElementType.START_EVENT,
        f"{BPMN_NS}endEvent": ElementType.END_EVENT,
        f"{BPMN_NS}intermediateCatchEvent": ElementType.INTERMEDIATE_CATCH_EVENT,
        f"{BPMN_NS}intermediateThrowEvent": ElementType.INTERMEDIATE_THROW_EVENT,
        f"{BPMN_NS}boundaryEvent": ElementType.BOUNDARY_EVENT,
    }

    def parse(self, bpmn_xml: str) -> BPMNProcess:
        """Parst BPMN 2.0 XML und gibt BPMNProcess zurueck.

        Args:
            bpmn_xml: BPMN 2.0 XML String

        Returns:
            BPMNProcess mit allen geparsten Elementen

        Raises:
            ValueError: Bei ungueltigem XML oder fehlendem Process
        """
        try:
            # SECURITY: Use defusedxml to prevent XXE attacks (CWE-611)
            root = DefusedET.fromstring(bpmn_xml)
        except ET.ParseError as e:
            logger.error("bpmn_parse_error", **safe_error_log(e))
            raise ValueError(f"Ungueltiges BPMN XML: {e}") from e

        # Process Element finden
        process_elem = root.find(f"{BPMN_NS}process")
        if process_elem is None:
            raise ValueError("Kein Process-Element im BPMN gefunden")

        process_id = process_elem.get("id")
        if not process_id:
            raise ValueError("Process-Element hat keine ID")

        process = BPMNProcess(
            id=process_id,
            name=process_elem.get("name"),
            is_executable=process_elem.get("isExecutable", "true").lower() == "true",
        )

        # Alle Elemente parsen
        elements = self._parse_process_elements(process_elem)
        process.elements = elements
        process._build_index()

        logger.info(
            "bpmn_parsed",
            process_id=process_id,
            element_count=len(elements)
        )

        return process

    def _parse_process_elements(
        self,
        process_elem: ET.Element
    ) -> List[BPMNElement]:
        """Parst alle Elemente innerhalb eines Process."""
        elements = []

        for child in process_elem:
            tag = child.tag

            # Events
            if tag in self.EVENT_TYPES:
                elements.append(self._parse_event(child, self.EVENT_TYPES[tag]))

            # Tasks
            elif tag in self.TASK_TYPES:
                elements.append(self._parse_task(child, self.TASK_TYPES[tag]))

            # Gateways
            elif tag in self.GATEWAY_TYPES:
                elements.append(self._parse_gateway(child, self.GATEWAY_TYPES[tag]))

            # Sequence Flow
            elif tag == f"{BPMN_NS}sequenceFlow":
                elements.append(self._parse_sequence_flow(child))

            # Subprocess
            elif tag == f"{BPMN_NS}subProcess":
                elements.append(self._parse_subprocess(child))

            # Call Activity
            elif tag == f"{BPMN_NS}callActivity":
                elements.append(self._parse_call_activity(child))

        return elements

    def _parse_base_element(
        self,
        elem: ET.Element,
        element_type: ElementType
    ) -> BPMNElement:
        """Parst gemeinsame Attribute aller Elemente."""
        element = BPMNElement(
            id=elem.get("id", ""),
            type=element_type.value,
            name=elem.get("name"),
        )

        # Incoming/Outgoing Flows
        for incoming in elem.findall(f"{BPMN_NS}incoming"):
            if incoming.text:
                element.incoming.append(incoming.text)

        for outgoing in elem.findall(f"{BPMN_NS}outgoing"):
            if outgoing.text:
                element.outgoing.append(outgoing.text)

        # Extension Properties
        ext_elems = elem.find(f"{BPMN_NS}extensionElements")
        if ext_elems is not None:
            element.extension_properties = self._parse_extension_properties(ext_elems)

        return element

    def _parse_extension_properties(
        self,
        ext_elem: ET.Element
    ) -> Dict[str, str]:
        """Parst Extension Properties (Camunda-kompatibel)."""
        properties = {}

        # Camunda-Style properties
        for prop in ext_elem.findall(".//{http://camunda.org/schema/1.0/bpmn}property"):
            name = prop.get("name")
            value = prop.get("value")
            if name and value:
                properties[name] = value

        return properties

    def _parse_event(
        self,
        elem: ET.Element,
        element_type: ElementType
    ) -> BPMNElement:
        """Parst ein Event-Element."""
        element = self._parse_base_element(elem, element_type)

        # Timer Event Definition
        timer_def = elem.find(f"{BPMN_NS}timerEventDefinition")
        if timer_def is not None:
            # Time Date
            time_date = timer_def.find(f"{BPMN_NS}timeDate")
            if time_date is not None and time_date.text:
                element.timer_type = "date"
                element.timer_value = time_date.text

            # Time Duration
            time_duration = timer_def.find(f"{BPMN_NS}timeDuration")
            if time_duration is not None and time_duration.text:
                element.timer_type = "duration"
                element.timer_value = time_duration.text

            # Time Cycle
            time_cycle = timer_def.find(f"{BPMN_NS}timeCycle")
            if time_cycle is not None and time_cycle.text:
                element.timer_type = "cycle"
                element.timer_value = time_cycle.text

        # Boundary Event spezifisch
        if element_type == ElementType.BOUNDARY_EVENT:
            element.attached_to_ref = elem.get("attachedToRef")
            element.cancel_activity = elem.get("cancelActivity", "true").lower() == "true"

        return element

    def _parse_task(
        self,
        elem: ET.Element,
        element_type: ElementType
    ) -> BPMNElement:
        """Parst ein Task-Element."""
        element = self._parse_base_element(elem, element_type)

        # User Task spezifisch (Camunda-Attribute)
        if element_type == ElementType.USER_TASK:
            # Camunda namespace fuer Assignee etc.
            camunda_ns = "{http://camunda.org/schema/1.0/bpmn}"

            element.assignee = elem.get(f"{camunda_ns}assignee")
            element.form_key = elem.get(f"{camunda_ns}formKey")
            element.due_date_expression = elem.get(f"{camunda_ns}dueDate")
            element.priority_expression = elem.get(f"{camunda_ns}priority")

            # Candidate Groups/Users
            candidate_groups = elem.get(f"{camunda_ns}candidateGroups")
            if candidate_groups:
                element.candidate_groups = [
                    g.strip() for g in candidate_groups.split(",")
                ]

            candidate_users = elem.get(f"{camunda_ns}candidateUsers")
            if candidate_users:
                element.candidate_users = [
                    u.strip() for u in candidate_users.split(",")
                ]

        # Service Task spezifisch
        elif element_type == ElementType.SERVICE_TASK:
            camunda_ns = "{http://camunda.org/schema/1.0/bpmn}"
            element.implementation = elem.get("implementation")
            element.topic = elem.get(f"{camunda_ns}topic")

            # Alternativ: Class/Expression
            if not element.implementation:
                element.implementation = elem.get(f"{camunda_ns}class")
            if not element.implementation:
                element.implementation = elem.get(f"{camunda_ns}expression")

        # Script Task spezifisch
        elif element_type == ElementType.SCRIPT_TASK:
            element.script_format = elem.get("scriptFormat")
            script_elem = elem.find(f"{BPMN_NS}script")
            if script_elem is not None and script_elem.text:
                element.script = script_elem.text

        return element

    def _parse_gateway(
        self,
        elem: ET.Element,
        element_type: ElementType
    ) -> BPMNElement:
        """Parst ein Gateway-Element."""
        element = self._parse_base_element(elem, element_type)

        # Default Flow
        element.default_flow = elem.get("default")

        return element

    def _parse_sequence_flow(self, elem: ET.Element) -> BPMNElement:
        """Parst einen Sequence Flow."""
        element = BPMNElement(
            id=elem.get("id", ""),
            type=ElementType.SEQUENCE_FLOW.value,
            name=elem.get("name"),
            source_ref=elem.get("sourceRef"),
            target_ref=elem.get("targetRef"),
        )

        # Condition Expression
        condition_elem = elem.find(f"{BPMN_NS}conditionExpression")
        if condition_elem is not None and condition_elem.text:
            element.condition = condition_elem.text

        return element

    def _parse_subprocess(self, elem: ET.Element) -> BPMNElement:
        """Parst einen Subprocess (embedded)."""
        element = self._parse_base_element(elem, ElementType.SUB_PROCESS)

        # Rekursiv innere Elemente parsen
        inner_elements = self._parse_process_elements(elem)
        element.elements = inner_elements

        return element

    def _parse_call_activity(self, elem: ET.Element) -> BPMNElement:
        """Parst eine Call Activity (externer Subprocess)."""
        element = self._parse_base_element(elem, ElementType.CALL_ACTIVITY)

        # Called Element
        element.extension_properties["calledElement"] = elem.get("calledElement", "")

        return element

    def generate(self, process: BPMNProcess) -> str:
        """Generiert BPMN 2.0 XML aus BPMNProcess.

        Args:
            process: BPMNProcess-Instanz

        Returns:
            BPMN 2.0 XML String
        """
        # Root Element
        definitions = ET.Element("definitions")
        definitions.set("xmlns", "http://www.omg.org/spec/BPMN/20100524/MODEL")
        definitions.set("xmlns:bpmndi", "http://www.omg.org/spec/BPMN/20100524/DI")
        definitions.set("xmlns:dc", "http://www.omg.org/spec/DD/20100524/DC")
        definitions.set("xmlns:camunda", "http://camunda.org/schema/1.0/bpmn")
        definitions.set("id", f"Definitions_{process.id}")
        definitions.set("targetNamespace", "http://ablage-system.de/bpmn")

        # Process Element
        process_elem = ET.SubElement(definitions, "process")
        process_elem.set("id", process.id)
        if process.name:
            process_elem.set("name", process.name)
        process_elem.set("isExecutable", str(process.is_executable).lower())

        # Elemente generieren
        for element in process.elements:
            self._generate_element(process_elem, element)

        # XML generieren
        ET.indent(definitions)
        xml_string = ET.tostring(definitions, encoding="unicode", xml_declaration=True)

        return xml_string

    def _generate_element(
        self,
        parent: ET.Element,
        element: BPMNElement
    ) -> ET.Element:
        """Generiert XML fuer ein einzelnes Element."""
        elem = ET.SubElement(parent, element.type)
        elem.set("id", element.id)

        if element.name:
            elem.set("name", element.name)

        # Incoming/Outgoing
        for incoming_id in element.incoming:
            incoming_elem = ET.SubElement(elem, "incoming")
            incoming_elem.text = incoming_id

        for outgoing_id in element.outgoing:
            outgoing_elem = ET.SubElement(elem, "outgoing")
            outgoing_elem.text = outgoing_id

        # Sequence Flow spezifisch
        if element.type == ElementType.SEQUENCE_FLOW.value:
            if element.source_ref:
                elem.set("sourceRef", element.source_ref)
            if element.target_ref:
                elem.set("targetRef", element.target_ref)
            if element.condition:
                cond_elem = ET.SubElement(elem, "conditionExpression")
                cond_elem.set("{http://www.w3.org/2001/XMLSchema-instance}type",
                              "tFormalExpression")
                cond_elem.text = element.condition

        # Gateway Default Flow
        if element.default_flow:
            elem.set("default", element.default_flow)

        # Timer Event Definition
        if element.timer_type and element.timer_value:
            timer_def = ET.SubElement(elem, "timerEventDefinition")
            if element.timer_type == "date":
                time_elem = ET.SubElement(timer_def, "timeDate")
            elif element.timer_type == "duration":
                time_elem = ET.SubElement(timer_def, "timeDuration")
            else:  # cycle
                time_elem = ET.SubElement(timer_def, "timeCycle")
            time_elem.text = element.timer_value

        # User Task spezifisch
        if element.type == ElementType.USER_TASK.value:
            if element.assignee:
                elem.set("{http://camunda.org/schema/1.0/bpmn}assignee",
                         element.assignee)
            if element.form_key:
                elem.set("{http://camunda.org/schema/1.0/bpmn}formKey",
                         element.form_key)
            if element.candidate_groups:
                elem.set("{http://camunda.org/schema/1.0/bpmn}candidateGroups",
                         ",".join(element.candidate_groups))

        return elem
