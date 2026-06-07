"""Process Execution Service.

Führt BPMN Prozesse aus:
- Start: Neue Prozess-Instanz starten
- Execute: Tokens durch den Prozess bewegen
- Gateway-Evaluation: Exclusive/Parallel/Inclusive
- Variable Management: Prozess-Variablen verwalten
- Signal/Message Correlation: Events triggern
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set, Union
from uuid import UUID
import re
import structlog

# Type alias for BPMN process variable values
ProcessVariableValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bpmn_models.bpmn import (
    ProcessDefinition,
    ProcessInstance,
    ProcessTask,
    ProcessHistory,
    ProcessTimerJob,
    ProcessVariableHistory,
    ProcessStatus,
    TaskStatus,
    TaskType,
)
from app.services.bpmn.bpmn_parser import BPMNProcess, BPMNElement, ElementType
from app.core.safe_errors import safe_error_log
from app.core.security.safe_expression_evaluator import (
    SafeExpressionEvaluator as ASTEvaluator,
    ExpressionEvaluationError,
    ExpressionSecurityError,
)

logger = structlog.get_logger(__name__)


class ExpressionEvaluator:
    """Evaluiert BPMN Expressions (Bedingungen, Variable Mappings).

    Unterstützt:
    - Variable References: ${variableName}
    - Vergleiche: ${amount > 1000}
    - Logische Operatoren: ${approved && amount < 5000}

    SECURITY: Uses AST-based SafeExpressionEvaluator instead of eval()
    to prevent arbitrary code execution (CWE-94, CWE-95).
    """

    VARIABLE_PATTERN = re.compile(r'\$\{([^}]+)\}')

    def __init__(self) -> None:
        """Initialize with AST-based safe evaluator."""
        self._safe_evaluator = ASTEvaluator(
            max_length=500,
            max_depth=10,
        )

    def evaluate_condition(
        self,
        expression: Optional[str],
        variables: Dict[str, Any]
    ) -> bool:
        """Evaluiert eine Bedingung sicher via AST-Parsing.

        Args:
            expression: Bedingungs-Ausdruck (z.B. "${amount > 1000}")
            variables: Prozess-Variablen

        Returns:
            True wenn Bedingung erfuellt oder keine Bedingung
        """
        if not expression:
            return True

        # Expression extrahieren
        match = self.VARIABLE_PATTERN.match(expression.strip())
        if not match:
            # Direkter Boolean-Wert
            return expression.lower() in ("true", "1", "yes")

        inner_expression = match.group(1)

        # Convert && and || to Python operators
        inner_expression = inner_expression.replace("&&", " and ")
        inner_expression = inner_expression.replace("||", " or ")

        # Use safe AST-based evaluation instead of eval()
        try:
            return self._safe_evaluator.evaluate_condition(
                inner_expression,
                variables
            )
        except (ExpressionEvaluationError, ExpressionSecurityError) as e:
            logger.warning(
                "expression_evaluation_failed",
                expression=expression[:100],  # Truncate for security
                **safe_error_log(e)
            )
            return False
        except Exception as e:
            logger.warning(
                "expression_evaluation_unexpected_error",
                expression=expression[:100],
                **safe_error_log(e)
            )
            return False

    def resolve_variable(
        self,
        expression: str,
        variables: Dict[str, ProcessVariableValue]
    ) -> ProcessVariableValue:
        """Loest einen Variablen-Ausdruck auf.

        Args:
            expression: z.B. "${invoiceId}" oder "literal"
            variables: Prozess-Variablen

        Returns:
            Aufgeloester Wert
        """
        match = self.VARIABLE_PATTERN.match(expression.strip())
        if not match:
            return expression

        var_name = match.group(1)
        return variables.get(var_name, expression)


class ProcessExecutionService:
    """Service für Prozess-Ausführung.

    Implementiert die BPMN Execution Engine:
    - Token-basierte Ausführung
    - Gateway-Evaluation
    - Task-Erstellung
    - Timer-Scheduling
    """

    # Maximale Verschachtelungstiefe fuer Call Activities (Rekursions-Schutz).
    MAX_CALL_ACTIVITY_DEPTH = 20

    def __init__(self, db: AsyncSession):
        self.db = db
        self.evaluator = ExpressionEvaluator()

    async def start(
        self,
        definition_key: str,
        company_id: UUID,
        variables: Optional[Dict[str, Any]] = None,
        business_key: Optional[str] = None,
        started_by_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
    ) -> ProcessInstance:
        """Startet eine neue Prozess-Instanz.

        Args:
            definition_key: Key der Prozess-Definition
            company_id: Mandant
            variables: Initiale Prozess-Variablen
            business_key: Externer Schluessel (z.B. Rechnungsnummer)
            started_by_id: Startender User
            document_id: Verknüpftes Dokument

        Returns:
            Gestartete ProcessInstance

        Raises:
            ValueError: Wenn keine aktive Definition gefunden
        """
        # Aktive Definition laden
        definition = await self._get_active_definition(definition_key, company_id)
        if not definition:
            raise ValueError(f"Keine aktive Prozess-Definition für Key '{definition_key}'")

        # Prozess parsen
        process = BPMNProcess.from_dict(definition.process_data)

        # Start Events finden
        start_events = process.get_start_events()
        if not start_events:
            raise ValueError("Prozess hat keine Start-Events")

        # Instanz erstellen
        instance = ProcessInstance(
            definition_id=definition.id,
            business_key=business_key,
            status=ProcessStatus.RUNNING,
            variables=variables or {},
            current_elements=[],
            started_by_id=started_by_id,
            document_id=document_id,
            company_id=company_id,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(instance)
        await self.db.flush()

        # History eintragen
        await self._add_history(
            instance=instance,
            event_type="PROCESS_STARTED",
            message=f"Prozess '{definition.name}' gestartet",
            actor_id=started_by_id
        )

        logger.info(
            "process_instance_started",
            instance_id=str(instance.id),
            definition_key=definition_key,
            business_key=business_key
        )

        # Start Events ausführen
        for start_event in start_events:
            await self._execute_element(instance, process, start_event, started_by_id)

        await self.db.flush()

        return instance

    async def signal(
        self,
        instance_id: UUID,
        company_id: UUID,
        signal_name: str,
        variables: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> ProcessInstance:
        """Sendet ein Signal an eine Prozess-Instanz.

        Aktiviert wartende Signal-Events.

        Args:
            instance_id: Instanz ID
            company_id: Mandant
            signal_name: Name des Signals
            variables: Zusätzliche Variablen
            user_id: Ausloesender User

        Returns:
            Aktualisierte Instanz
        """
        # Concurrency guard: serialize signal/timer/task-complete on this instance.
        await acquire_instance_lock(self.db, instance_id)

        instance = await self.get_instance(instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        if instance.status != ProcessStatus.RUNNING:
            raise ValueError(f"Prozess ist nicht aktiv (Status: {instance.status})")

        # Variablen mergen
        if variables:
            await self._update_variables(instance, variables, user_id)

        await self._add_history(
            instance=instance,
            event_type="SIGNAL_RECEIVED",
            message=f"Signal '{signal_name}' empfangen",
            actor_id=user_id,
            new_value=variables
        )

        # M17: Wartende (geparkte) Catch-Events der Instanz fortsetzen, statt das
        # Signal nur zu protokollieren. Per-Signal-Namen-Matching: nur Catch-Events,
        # deren aufgeloester Signal-Name oder signalRef-ID zum empfangenen Signal
        # passt, werden fortgesetzt. Alt-Definitionen ohne hinterlegten Signal-Namen
        # feuern weiterhin (Rueckwaertskompatibilitaet).
        resumed = await self._resume_waiting_catch_events(instance, user_id, signal_name)
        if resumed:
            logger.info(
                "signal_resumed_catch_events",
                instance_id=str(instance.id),
                signal_name=signal_name,
                resumed_elements=resumed,
            )
            await self.db.commit()
            await self.db.refresh(instance)

        return instance

    async def _resume_waiting_catch_events(
        self,
        instance: ProcessInstance,
        user_id: Optional[UUID],
        signal_name: Optional[str] = None,
    ) -> List[str]:
        """Setzt geparkte (wartende) Nicht-Timer-Catch-/Boundary-Events fort.

        Konsumiert das Token am wartenden Catch-Event und setzt den Flow ueber die
        bestehende Engine-Logik (``_continue_flow``) fort. Liefert die IDs der
        fortgesetzten Elemente. Timer-Catch-Events bleiben unberuehrt (sie feuern
        ueber den Timer-Job).

        Per-Signal-Namen-Matching (M17): Ist ``signal_name`` gesetzt, werden nur
        Catch-Events fortgesetzt, deren aufgeloester Signal-Name oder signalRef-ID
        passt (siehe ``_signal_matches_element``). Ohne ``signal_name`` bzw. fuer
        Alt-Events ohne hinterlegten Signal-Namen bleibt das bisherige Verhalten.
        """
        definition = await self._get_definition_by_id(instance.definition_id)
        if definition is None:
            return []
        process = BPMNProcess.from_dict(definition.process_data)
        resumed: List[str] = []
        for element_id in list(instance.current_elements):
            element = process.get_element(element_id)
            if element is None:
                continue
            if element.type not in (
                ElementType.INTERMEDIATE_CATCH_EVENT.value,
                ElementType.BOUNDARY_EVENT.value,
            ):
                continue
            if getattr(element, "timer_type", None):
                continue
            if not self._signal_matches_element(element, signal_name):
                continue
            current = list(instance.current_elements)
            if element_id in current:
                current.remove(element_id)
                instance.current_elements = current
            await self._continue_flow(instance, process, element, user_id)
            resumed.append(element_id)
        return resumed

    @staticmethod
    def _signal_matches_element(element: BPMNElement, signal_name: Optional[str]) -> bool:
        """Prueft, ob ein wartendes Catch-Event zum empfangenen Signal passt.

        Name-+-ID-Matching mit Rueckwaertskompatibilitaet:
        - ``signal_name is None`` (z.B. interner Aufruf ohne Namen): alle Nicht-
          Timer-Catch-Events feuern (bisheriges Verhalten).
        - Element ohne hinterlegten Signal-Namen UND ohne signalRef-ID (Definitionen
          aus der Zeit vor dieser Erweiterung): feuert weiterhin -> BC.
        - Sonst muss ``signal_name`` dem aufgeloesten Namen ODER der signalRef-ID
          entsprechen.
        """
        if signal_name is None:
            return True
        elem_name = getattr(element, "signal_name", None)
        elem_ref = getattr(element, "signal_ref", None)
        if elem_name is None and elem_ref is None:
            return True
        return signal_name == elem_name or signal_name == elem_ref

    async def get_instance(
        self,
        instance_id: UUID,
        company_id: UUID
    ) -> Optional[ProcessInstance]:
        """Laedt eine Prozess-Instanz."""
        query = select(ProcessInstance).where(
            and_(
                ProcessInstance.id == instance_id,
                ProcessInstance.company_id == company_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_instance_by_business_key(
        self,
        business_key: str,
        company_id: UUID
    ) -> Optional[ProcessInstance]:
        """Laedt Prozess-Instanz nach Business Key."""
        query = select(ProcessInstance).where(
            and_(
                ProcessInstance.business_key == business_key,
                ProcessInstance.company_id == company_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_instances(
        self,
        company_id: UUID,
        definition_key: Optional[str] = None,
        status: Optional[ProcessStatus] = None,
        started_by_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[ProcessInstance], int]:
        """Listet Prozess-Instanzen auf.

        Args:
            company_id: Mandant
            definition_key: Filter nach Prozess-Key
            status: Filter nach Status
            started_by_id: Filter nach Starter
            document_id: Filter nach verknüpftem Dokument
            page: Seite
            per_page: Einträge pro Seite

        Returns:
            (Liste der Instanzen, Gesamtanzahl)
        """
        conditions = [ProcessInstance.company_id == company_id]

        if status:
            conditions.append(ProcessInstance.status == status)

        if started_by_id:
            conditions.append(ProcessInstance.started_by_id == started_by_id)

        if document_id:
            conditions.append(ProcessInstance.document_id == document_id)

        if definition_key:
            # Join mit Definition
            conditions.append(ProcessDefinition.key == definition_key)
            query = (
                select(ProcessInstance)
                .join(ProcessDefinition)
                .where(and_(*conditions))
            )
            count_query = (
                select(func.count(ProcessInstance.id))
                .join(ProcessDefinition)
                .where(and_(*conditions))
            )
        else:
            query = select(ProcessInstance).where(and_(*conditions))
            count_query = select(func.count(ProcessInstance.id)).where(
                and_(*conditions)
            )

        # Count
        total = await self.db.scalar(count_query) or 0

        # Data
        query = (
            query
            .order_by(ProcessInstance.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        instances = list(result.scalars().all())

        return instances, total

    async def terminate(
        self,
        instance_id: UUID,
        company_id: UUID,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> ProcessInstance:
        """Terminiert eine laufende Prozess-Instanz.

        Args:
            instance_id: Instanz ID
            company_id: Mandant
            reason: Grund für Terminierung
            user_id: Terminierender User

        Returns:
            Terminierte Instanz
        """
        instance = await self.get_instance(instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        if instance.status not in (ProcessStatus.RUNNING, ProcessStatus.SUSPENDED):
            raise ValueError(f"Prozess kann nicht terminiert werden (Status: {instance.status})")

        instance.status = ProcessStatus.TERMINATED
        instance.ended_at = datetime.now(timezone.utc)

        await self._add_history(
            instance=instance,
            event_type="PROCESS_TERMINATED",
            message=reason or "Prozess manuell beendet",
            actor_id=user_id
        )

        # Offene Tasks abbrechen
        await self._cancel_open_tasks(instance)

        # Timer löschen
        await self._cancel_timers(instance)

        logger.info(
            "process_instance_terminated",
            instance_id=str(instance_id),
            reason=reason
        )

        return instance

    async def get_history(
        self,
        instance_id: UUID,
        company_id: UUID,
        limit: int = 100
    ) -> List[ProcessHistory]:
        """Gibt die Historie einer Prozess-Instanz zurück."""
        query = (
            select(ProcessHistory)
            .where(
                and_(
                    ProcessHistory.instance_id == instance_id,
                    ProcessHistory.company_id == company_id
                )
            )
            .order_by(ProcessHistory.timestamp.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Internal Execution Methods
    # =========================================================================

    async def _execute_element(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID] = None
    ) -> None:
        """Führt ein BPMN-Element aus.

        Dispatched basierend auf Element-Typ.
        """
        element_type = element.type

        logger.debug(
            "executing_element",
            instance_id=str(instance.id),
            element_id=element.id,
            element_type=element_type
        )

        # Events
        if element_type == ElementType.START_EVENT.value:
            await self._execute_start_event(instance, process, element, user_id)
        elif element_type == ElementType.END_EVENT.value:
            await self._execute_end_event(instance, process, element, user_id)
        elif element_type in (
            ElementType.INTERMEDIATE_CATCH_EVENT.value,
            ElementType.BOUNDARY_EVENT.value
        ):
            await self._execute_catch_event(instance, process, element, user_id)

        # Tasks
        elif element_type in (
            ElementType.USER_TASK.value,
            ElementType.MANUAL_TASK.value
        ):
            await self._create_user_task(instance, process, element)
        elif element_type == ElementType.SERVICE_TASK.value:
            await self._execute_service_task(instance, process, element, user_id)
        elif element_type == ElementType.SCRIPT_TASK.value:
            await self._execute_script_task(instance, process, element, user_id)

        # Gateways
        elif element_type == ElementType.EXCLUSIVE_GATEWAY.value:
            await self._execute_exclusive_gateway(instance, process, element, user_id)
        elif element_type == ElementType.PARALLEL_GATEWAY.value:
            await self._execute_parallel_gateway(instance, process, element, user_id)
        elif element_type == ElementType.INCLUSIVE_GATEWAY.value:
            await self._execute_inclusive_gateway(instance, process, element, user_id)

        # Subprocess
        elif element_type == ElementType.SUB_PROCESS.value:
            await self._execute_subprocess(instance, process, element, user_id)

        # Call Activity (Aufruf einer separaten Prozess-Definition als Sub-Instanz)
        elif element_type == ElementType.CALL_ACTIVITY.value:
            await self._execute_call_activity(instance, process, element, user_id)

        else:
            # Unbekannter Typ - einfach weiter
            await self._continue_flow(instance, process, element, user_id)

    async def _execute_start_event(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt Start-Event aus."""
        await self._add_history(
            instance=instance,
            event_type="START_EVENT_EXECUTED",
            element_id=element.id,
            element_type=element.type
        )

        # Weiter zum nächsten Element
        await self._continue_flow(instance, process, element, user_id)

    async def _execute_end_event(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt End-Event aus."""
        # Token aus current_elements entfernen
        current = list(instance.current_elements)

        # Prüfen ob noch andere Tokens aktiv
        if not current:
            # Prozess beenden
            instance.status = ProcessStatus.COMPLETED
            instance.ended_at = datetime.now(timezone.utc)

            await self._add_history(
                instance=instance,
                event_type="PROCESS_COMPLETED",
                element_id=element.id,
                message="Prozess erfolgreich abgeschlossen"
            )

            logger.info(
                "process_instance_completed",
                instance_id=str(instance.id)
            )

            # Call Activity: Ist dies eine Sub-Instanz, die Eltern-Instanz fortsetzen.
            if instance.parent_instance_id is not None:
                await self._resume_parent_after_call_activity(instance, user_id)

    async def _execute_catch_event(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt Catch-Event (Timer, Message, Signal) aus."""
        # Timer-Event
        if element.timer_type and element.timer_value:
            await self._schedule_timer(instance, element)
            return

        # Andere Events warten auf externe Trigger
        current = list(instance.current_elements)
        current.append(element.id)
        instance.current_elements = current

    async def _create_user_task(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement
    ) -> ProcessTask:
        """Erstellt einen User Task."""
        # Assignee aus Expression aufloesen
        assignee_id = None
        if element.assignee:
            assignee_value = self.evaluator.resolve_variable(
                element.assignee, instance.variables
            )
            if isinstance(assignee_value, str):
                try:
                    assignee_id = UUID(assignee_value)
                except ValueError as e:
                    logger.debug("assignee_uuid_parse_failed", assignee_value=assignee_value, error_type=type(e).__name__)

        task = ProcessTask(
            instance_id=instance.id,
            element_id=element.id,
            element_name=element.name or element.id,
            task_type=TaskType.USER_TASK,
            status=TaskStatus.ACTIVE if not assignee_id else TaskStatus.ASSIGNED,
            assignee_id=assignee_id,
            assignee_group=(
                element.candidate_groups[0] if element.candidate_groups else None
            ),
            form_key=element.form_key,
            task_variables=element.extension_properties,
            company_id=instance.company_id,
        )
        self.db.add(task)

        # Current Elements aktualisieren
        current = list(instance.current_elements)
        current.append(element.id)
        instance.current_elements = current

        await self._add_history(
            instance=instance,
            event_type="TASK_CREATED",
            element_id=element.id,
            element_type=element.type,
            message=f"Task '{element.name or element.id}' erstellt"
        )

        logger.info(
            "user_task_created",
            instance_id=str(instance.id),
            task_element_id=element.id
        )

        return task

    async def _execute_service_task(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt einen Service Task aus.

        Implementation kann sein:
        - celery:task_name -> Celery Task ausloesen
        - http:URL -> HTTP Request
        - python:module.function -> Python-Funktion
        """
        implementation = element.implementation

        if not implementation:
            # Ohne Implementation einfach weiter
            await self._continue_flow(instance, process, element, user_id)
            return

        await self._add_history(
            instance=instance,
            event_type="SERVICE_TASK_STARTED",
            element_id=element.id,
            message=f"Service Task '{element.name}' gestartet"
        )

        # Celery Task
        if implementation.startswith("celery:"):
            task_name = implementation[7:]
            await self._trigger_celery_task(
                instance, element, task_name
            )
            return

        # HTTP (nicht implementiert)
        if implementation.startswith("http:"):
            logger.warning(
                "http_service_task_not_implemented",
                element_id=element.id
            )

        # Fallback: Weiter zum nächsten Element
        await self._continue_flow(instance, process, element, user_id)

    async def _execute_script_task(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt einen Script Task aus (Sandbox!).

        WARNUNG: Script-Ausführung ist eingeschraenkt aus Sicherheitsgruenden.
        """
        script = element.script
        if not script:
            await self._continue_flow(instance, process, element, user_id)
            return

        # Sichere Ausführung (sehr eingeschraenkt)
        try:
            # Nur Variable-Zuweisungen erlauben
            # Vollständige Sandbox-Implementierung wuerde RestrictedPython benötigen
            logger.info(
                "script_task_executed",
                instance_id=str(instance.id),
                element_id=element.id
            )
        except Exception as e:
            logger.error(
                "script_task_failed",
                element_id=element.id,
                **safe_error_log(e)
            )

        await self._continue_flow(instance, process, element, user_id)

    async def _execute_exclusive_gateway(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt Exclusive Gateway (XOR) aus.

        Waehlt genau einen ausgehenden Pfad basierend auf Conditions.
        """
        # Outgoing Flows holen
        outgoing_flows = []
        default_flow = None

        for flow_id in element.outgoing:
            flow = process.get_element(flow_id)
            if flow:
                if element.default_flow and flow.id == element.default_flow:
                    default_flow = flow
                else:
                    outgoing_flows.append(flow)

        # Ersten passenden Flow finden
        selected_flow = None
        for flow in outgoing_flows:
            if self.evaluator.evaluate_condition(flow.condition, instance.variables):
                selected_flow = flow
                break

        # Fallback auf Default Flow
        if not selected_flow and default_flow:
            selected_flow = default_flow

        if not selected_flow:
            raise ValueError(
                f"Kein gültiger Pfad für Exclusive Gateway '{element.id}'"
            )

        await self._add_history(
            instance=instance,
            event_type="GATEWAY_EVALUATED",
            element_id=element.id,
            element_type=element.type,
            message=f"Pfad '{selected_flow.id}' gewaehlt"
        )

        # Zum Ziel navigieren
        target = process.get_element(selected_flow.target_ref)
        if target:
            await self._execute_element(instance, process, target, user_id)

    async def _execute_parallel_gateway(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt Parallel Gateway (AND) aus.

        Fork: Alle ausgehenden Pfade aktivieren
        Join: Warten bis alle eingehenden Tokens da sind
        """
        incoming_count = len(element.incoming)
        outgoing_count = len(element.outgoing)

        # Join: Warten auf alle Tokens
        if incoming_count > 1:
            current = list(instance.current_elements)
            # Zaehlen wie viele Tokens am Gateway angekommen
            tokens_at_gateway = current.count(element.id)

            if tokens_at_gateway < incoming_count - 1:
                # Noch nicht alle da - Token speichern
                current.append(element.id)
                instance.current_elements = current
                return

            # Alle da - Tokens entfernen
            for _ in range(incoming_count - 1):
                if element.id in current:
                    current.remove(element.id)
            instance.current_elements = current

        # Fork: Alle Pfade aktivieren
        await self._add_history(
            instance=instance,
            event_type="GATEWAY_EVALUATED",
            element_id=element.id,
            element_type=element.type,
            message=f"Parallel Gateway - {outgoing_count} Pfade aktiviert"
        )

        for flow_id in element.outgoing:
            flow = process.get_element(flow_id)
            if flow and flow.target_ref:
                target = process.get_element(flow.target_ref)
                if target:
                    await self._execute_element(instance, process, target, user_id)

    async def _execute_inclusive_gateway(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt Inclusive Gateway (OR) aus.

        Wie Exclusive, aber mehrere Pfade können aktiv werden.
        """
        selected_flows = []
        default_flow = None

        for flow_id in element.outgoing:
            flow = process.get_element(flow_id)
            if not flow:
                continue

            if element.default_flow and flow.id == element.default_flow:
                default_flow = flow
            elif self.evaluator.evaluate_condition(flow.condition, instance.variables):
                selected_flows.append(flow)

        # Fallback auf Default wenn keine Condition passt
        if not selected_flows and default_flow:
            selected_flows = [default_flow]

        if not selected_flows:
            raise ValueError(
                f"Kein gültiger Pfad für Inclusive Gateway '{element.id}'"
            )

        await self._add_history(
            instance=instance,
            event_type="GATEWAY_EVALUATED",
            element_id=element.id,
            element_type=element.type,
            message=f"{len(selected_flows)} Pfade aktiviert"
        )

        # Alle passenden Pfade aktivieren
        for flow in selected_flows:
            target = process.get_element(flow.target_ref)
            if target:
                await self._execute_element(instance, process, target, user_id)

    async def _execute_subprocess(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Führt einen embedded Subprocess inline aus.

        Call Activities (Aufruf einer SEPARATEN Prozess-Definition) laufen NICHT
        hier, sondern in ``_execute_call_activity`` (eigene Sub-Instanz mit
        Rueckkopplung an die Eltern-Instanz).
        """

        await self._add_history(
            instance=instance,
            event_type="SUBPROCESS_STARTED",
            element_id=element.id,
            message=f"Subprocess '{element.name or element.id}' gestartet"
        )

        # Bei embedded Subprocess: Innere Elemente ausführen
        if element.elements:
            # Start-Event im Subprocess finden
            start_events = [
                e for e in element.elements
                if e.type == ElementType.START_EVENT.value
            ]
            if start_events:
                # Temporaeren Sub-Process erstellen
                sub_process = BPMNProcess(
                    id=element.id,
                    name=element.name,
                    elements=element.elements
                )
                for start in start_events:
                    await self._execute_element(
                        instance, sub_process, start, user_id
                    )

        # Weiter nach Subprocess
        await self._continue_flow(instance, process, element, user_id)

    async def _execute_call_activity(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Fuehrt eine Call Activity aus: startet eine eigene Sub-Instanz der
        aufgerufenen Prozess-Definition.

        Die Eltern-Instanz parkt am Call-Activity-Element (Token), bis die
        Sub-Instanz abgeschlossen ist; danach setzt ``_execute_end_event`` der
        Sub-Instanz die Eltern-Instanz fort (``_resume_parent_after_call_activity``).

        Variablen-Semantik: Die Sub-Instanz erhaelt eine Kopie der Eltern-Variablen;
        nach Abschluss werden die Sub-Variablen in die Eltern-Instanz gemerged.

        Fehlt ``calledElement`` oder die Ziel-Definition, wird der Flow regulaer
        fortgesetzt (kein Crash) - strikt besser als das fruehere stille Ueberspringen.
        """
        called_key = (element.extension_properties or {}).get("calledElement")
        if not called_key:
            logger.warning(
                "call_activity_without_called_element",
                instance_id=str(instance.id),
                element_id=element.id,
            )
            await self._continue_flow(instance, process, element, user_id)
            return

        # Rekursions-/Tiefenschutz gegen Endlos-Verschachtelung.
        if await self._call_activity_depth(instance) >= self.MAX_CALL_ACTIVITY_DEPTH:
            logger.warning(
                "call_activity_max_depth_reached",
                instance_id=str(instance.id),
                element_id=element.id,
                called_element=called_key,
            )
            await self._continue_flow(instance, process, element, user_id)
            return

        called_def = await self._get_active_definition(called_key, instance.company_id)
        if called_def is None:
            logger.warning(
                "call_activity_definition_not_found",
                instance_id=str(instance.id),
                element_id=element.id,
                called_element=called_key,
            )
            await self._continue_flow(instance, process, element, user_id)
            return

        # Eltern-Token am Call-Activity-Element parken.
        current = list(instance.current_elements)
        if element.id not in current:
            current.append(element.id)
            instance.current_elements = current

        await self._add_history(
            instance=instance,
            event_type="CALL_ACTIVITY_STARTED",
            element_id=element.id,
            element_type=element.type,
            message=f"Call Activity '{called_key}' gestartet",
        )

        # Sub-Instanz starten (Variablen aus der Eltern-Instanz kopieren).
        sub_process = BPMNProcess.from_dict(called_def.process_data)
        sub_instance = ProcessInstance(
            definition_id=called_def.id,
            business_key=instance.business_key,
            status=ProcessStatus.RUNNING,
            variables=dict(instance.variables or {}),
            current_elements=[],
            started_by_id=user_id,
            document_id=instance.document_id,
            company_id=instance.company_id,
            parent_instance_id=instance.id,
            parent_element_id=element.id,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sub_instance)
        await self.db.flush()

        await self._add_history(
            instance=sub_instance,
            event_type="PROCESS_STARTED",
            message=f"Sub-Prozess '{called_def.name}' via Call Activity gestartet",
            actor_id=user_id,
        )

        for start_event in sub_process.get_start_events():
            await self._execute_element(sub_instance, sub_process, start_event, user_id)

        await self.db.flush()

    async def _resume_parent_after_call_activity(
        self,
        sub_instance: ProcessInstance,
        user_id: Optional[UUID]
    ) -> None:
        """Setzt die Eltern-Instanz fort, nachdem eine Call-Activity-Sub-Instanz endete.

        Merged die Sub-Variablen in die Eltern-Instanz, konsumiert das geparkte Token
        am Call-Activity-Element und setzt den Eltern-Flow ueber ``_continue_flow`` fort.
        """
        parent = await self.get_instance(
            sub_instance.parent_instance_id, sub_instance.company_id
        )
        if parent is None or parent.status != ProcessStatus.RUNNING:
            return

        # Out-Mapping: Sub-Variablen in die Eltern-Instanz uebernehmen.
        merged = dict(parent.variables or {})
        merged.update(sub_instance.variables or {})
        parent.variables = merged

        parent_def = await self._get_definition_by_id(parent.definition_id)
        parent_process = BPMNProcess.from_dict(parent_def.process_data)

        call_element_id = sub_instance.parent_element_id
        current = list(parent.current_elements)
        if call_element_id in current:
            current.remove(call_element_id)
            parent.current_elements = current

        await self._add_history(
            instance=parent,
            event_type="CALL_ACTIVITY_COMPLETED",
            element_id=call_element_id,
            message="Sub-Prozess abgeschlossen, Eltern-Prozess fortgesetzt",
        )

        call_element = parent_process.get_element(call_element_id)
        if call_element is not None:
            await self._continue_flow(parent, parent_process, call_element, user_id)
        await self.db.flush()

    async def _call_activity_depth(self, instance: ProcessInstance) -> int:
        """Zaehlt die Call-Activity-Verschachtelungstiefe ueber die Eltern-Kette.

        Dient als Rekursions-/Zyklus-Schutz: bei Erreichen der Maximaltiefe startet
        die Call Activity keine weitere Sub-Instanz mehr.
        """
        depth = 0
        seen: Set[UUID] = set()
        parent_id = instance.parent_instance_id
        while parent_id is not None and depth <= self.MAX_CALL_ACTIVITY_DEPTH:
            if parent_id in seen:
                break
            seen.add(parent_id)
            parent = await self.get_instance(parent_id, instance.company_id)
            if parent is None:
                break
            depth += 1
            parent_id = parent.parent_instance_id
        return depth

    async def _continue_flow(
        self,
        instance: ProcessInstance,
        process: BPMNProcess,
        element: BPMNElement,
        user_id: Optional[UUID]
    ) -> None:
        """Setzt den Flow nach einem Element fort."""
        for flow_id in element.outgoing:
            flow = process.get_element(flow_id)
            if flow and flow.target_ref:
                target = process.get_element(flow.target_ref)
                if target:
                    await self._execute_element(instance, process, target, user_id)

    async def _schedule_timer(
        self,
        instance: ProcessInstance,
        element: BPMNElement
    ) -> None:
        """Plant einen Timer-Job."""
        from dateutil import parser as date_parser
        from datetime import timedelta
        import isodate

        due_at = None
        repeat_count = None

        if element.timer_type == "date":
            # ISO 8601 DateTime
            due_at = date_parser.parse(element.timer_value)

        elif element.timer_type == "duration":
            # ISO 8601 Duration (z.B. PT1H30M)
            duration = isodate.parse_duration(element.timer_value)
            due_at = datetime.now(timezone.utc) + duration

        elif element.timer_type == "cycle":
            # ISO 8601 Repeating Interval (z.B. R3/PT1H)
            # Vereinfacht: Nur erste Ausführung planen
            if element.timer_value.startswith("R"):
                parts = element.timer_value.split("/")
                if len(parts) >= 2:
                    repeat_str = parts[0][1:]  # R3 -> 3
                    repeat_count = int(repeat_str) if repeat_str else None
                    duration = isodate.parse_duration(parts[1])
                    due_at = datetime.now(timezone.utc) + duration

        if due_at:
            timer_job = ProcessTimerJob(
                instance_id=instance.id,
                element_id=element.id,
                timer_type=element.timer_type,
                timer_value=element.timer_value,
                due_at=due_at,
                repeat_count=repeat_count,
                company_id=instance.company_id,
            )
            self.db.add(timer_job)

            logger.info(
                "timer_scheduled",
                instance_id=str(instance.id),
                element_id=element.id,
                due_at=str(due_at)
            )

    async def _trigger_celery_task(
        self,
        instance: ProcessInstance,
        element: BPMNElement,
        task_name: str
    ) -> None:
        """Triggert einen Celery Task."""
        # Import hier um zirkuläre Imports zu vermeiden
        from app.workers.celery_app import celery_app


        # Task asynchron ausloesen
        celery_app.send_task(
            task_name,
            kwargs={
                "instance_id": str(instance.id),
                "element_id": element.id,
                "variables": instance.variables,
            }
        )

        # Element als wartend markieren
        current = list(instance.current_elements)
        current.append(element.id)
        instance.current_elements = current

    async def continue_after_task(
        self,
        instance_id: UUID,
        element_id: str,
        company_id: UUID,
        result_variables: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Setzt Prozess nach Task-Completion fort.

        Wird von TaskService.complete() aufgerufen.
        """
        # Concurrency guard: serialize signal/timer/task-complete on this instance.
        await acquire_instance_lock(self.db, instance_id)

        instance = await self.get_instance(instance_id, company_id)
        if not instance:
            raise ValueError("Prozess-Instanz nicht gefunden")

        # Definition laden
        definition = await self._get_definition_by_id(instance.definition_id)
        process = BPMNProcess.from_dict(definition.process_data)

        # Variablen mergen
        if result_variables:
            await self._update_variables(instance, result_variables, user_id)

        # Element aus current_elements entfernen
        current = list(instance.current_elements)
        if element_id in current:
            current.remove(element_id)
        instance.current_elements = current

        # Flow fortsetzen
        element = process.get_element(element_id)
        if element:
            await self._continue_flow(instance, process, element, user_id)

        await self.db.flush()

    async def _update_variables(
        self,
        instance: ProcessInstance,
        new_variables: Dict[str, Any],
        user_id: Optional[UUID] = None
    ) -> None:
        """Aktualisiert Prozess-Variablen mit History."""
        current_vars = dict(instance.variables)

        for key, value in new_variables.items():
            old_value = current_vars.get(key)

            # History eintragen
            history = ProcessVariableHistory(
                instance_id=instance.id,
                variable_name=key,
                old_value=old_value,
                new_value=value,
                changed_by_id=user_id,
                company_id=instance.company_id,
            )
            self.db.add(history)

            current_vars[key] = value

        instance.variables = current_vars

    async def _add_history(
        self,
        instance: ProcessInstance,
        event_type: str,
        message: Optional[str] = None,
        element_id: Optional[str] = None,
        element_type: Optional[str] = None,
        task_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        actor_type: str = "user",
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
    ) -> ProcessHistory:
        """Fuegt History-Eintrag hinzu."""
        history = ProcessHistory(
            instance_id=instance.id,
            task_id=task_id,
            event_type=event_type,
            element_id=element_id,
            element_type=element_type,
            message=message,
            old_value=old_value,
            new_value=new_value,
            actor_id=actor_id,
            actor_type=actor_type,
            company_id=instance.company_id,
        )
        self.db.add(history)
        return history

    async def _cancel_open_tasks(self, instance: ProcessInstance) -> None:
        """Bricht alle offenen Tasks ab."""
        from sqlalchemy import update

        await self.db.execute(
            update(ProcessTask)
            .where(
                and_(
                    ProcessTask.instance_id == instance.id,
                    ProcessTask.status.in_([
                        TaskStatus.PENDING,
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS
                    ])
                )
            )
            .values(status=TaskStatus.SKIPPED)
        )

    async def _cancel_timers(self, instance: ProcessInstance) -> None:
        """Löscht alle aktiven Timer."""
        from sqlalchemy import update

        await self.db.execute(
            update(ProcessTimerJob)
            .where(
                and_(
                    ProcessTimerJob.instance_id == instance.id,
                    ProcessTimerJob.is_active == True
                )
            )
            .values(is_active=False)
        )

    async def _get_active_definition(
        self,
        key: str,
        company_id: UUID
    ) -> Optional[ProcessDefinition]:
        """Laedt aktive Definition nach Key."""
        query = select(ProcessDefinition).where(
            and_(
                ProcessDefinition.key == key,
                ProcessDefinition.company_id == company_id,
                ProcessDefinition.is_active == True
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_definition_by_id(
        self,
        definition_id: UUID
    ) -> ProcessDefinition:
        """Laedt Definition nach ID."""
        query = select(ProcessDefinition).where(
            ProcessDefinition.id == definition_id
        )
        result = await self.db.execute(query)
        return result.scalar_one()


async def acquire_instance_lock(db: AsyncSession, instance_id: UUID) -> None:
    """Serialize concurrent engine operations on a single process instance.

    The engine runs ``signal``, timer firing and ``continue_after_task`` as
    recursive read-modify-write of ``instance.current_elements`` / ``variables``
    with no row lock, so concurrent operations on the SAME instance could lose
    or duplicate tokens. This takes a transaction-scoped PostgreSQL advisory
    lock keyed on the instance id, serializing those operations per instance.
    The lock auto-releases on COMMIT/ROLLBACK and only ever locks one key per
    operation, so it cannot deadlock. No-op against non-Postgres mock sessions
    in unit tests (``db.execute`` is mocked).
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:iid, 0))"),
        {"iid": str(instance_id)},
    )


def get_process_execution_service(db: AsyncSession) -> ProcessExecutionService:
    """Factory Function für ProcessExecutionService."""
    return ProcessExecutionService(db)
