# -*- coding: utf-8 -*-
"""Workflow Service fuer CRUD-Operationen.

Verwaltet Workflows, Steps und Templates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Workflow, WorkflowStep, WorkflowExecution

if TYPE_CHECKING:
    from app.db.models import User

logger = structlog.get_logger(__name__)


class WorkflowService:
    """Service fuer Workflow-CRUD-Operationen.

    Verwaltet:
    - Workflow-Definitionen
    - Workflow-Steps
    - Workflow-Templates
    - Workflow-Validierung
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den WorkflowService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # Workflow CRUD
    # =========================================================================

    async def create_workflow(
        self,
        user_id: UUID,
        name: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        nodes: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        company_id: Optional[UUID] = None,
        variables: Optional[Dict[str, Any]] = None,
        max_concurrent_executions: int = 10,
        timeout_seconds: int = 3600,
        retry_config: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """Erstellt einen neuen Workflow.

        Args:
            user_id: ID des erstellenden Users
            name: Name des Workflows
            trigger_type: Trigger-Typ (document_event, schedule, etc.)
            trigger_config: Trigger-Konfiguration
            nodes: ReactFlow-Knoten
            edges: ReactFlow-Kanten
            description: Beschreibung
            company_id: Optionale Firmen-ID
            variables: Workflow-Variablen
            max_concurrent_executions: Max parallele Ausfuehrungen
            timeout_seconds: Timeout in Sekunden
            retry_config: Retry-Konfiguration

        Returns:
            Erstellter Workflow
        """
        workflow = Workflow(
            id=uuid4(),
            user_id=user_id,
            company_id=company_id,
            name=name,
            description=description,
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            nodes=nodes or [],
            edges=edges or [],
            variables=variables or {},
            is_active=False,  # Standardmaessig inaktiv
            is_template=False,
            max_concurrent_executions=max_concurrent_executions,
            timeout_seconds=timeout_seconds,
            retry_config=retry_config or {"max_retries": 3, "retry_delay": 60},
            execution_count=0,
        )

        self.db.add(workflow)
        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(
            "workflow_created",
            workflow_id=str(workflow.id),
            name=name,
            trigger_type=trigger_type,
            user_id=str(user_id),
        )

        return workflow

    async def get_workflow(
        self,
        workflow_id: UUID,
        user_id: Optional[UUID] = None,
        include_steps: bool = True,
    ) -> Optional[Workflow]:
        """Holt einen Workflow nach ID.

        Args:
            workflow_id: Workflow-ID
            user_id: Optionale User-ID fuer Berechtigungspruefung
            include_steps: Steps mit laden

        Returns:
            Workflow oder None
        """
        query = select(Workflow).where(Workflow.id == workflow_id)

        if include_steps:
            query = query.options(selectinload(Workflow.steps))

        if user_id:
            query = query.where(
                or_(
                    Workflow.user_id == user_id,
                    Workflow.is_template == True,  # noqa: E712
                )
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_workflows(
        self,
        user_id: UUID,
        company_id: Optional[UUID] = None,
        trigger_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_template: Optional[bool] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[Workflow], int]:
        """Listet Workflows mit Filtern.

        Args:
            user_id: User-ID
            company_id: Optionale Firmen-ID
            trigger_type: Filter nach Trigger-Typ
            is_active: Filter nach Aktiv-Status
            is_template: Filter nach Template-Status
            search: Suchbegriff fuer Name/Beschreibung
            offset: Pagination Offset
            limit: Pagination Limit

        Returns:
            Tuple aus Workflow-Liste und Gesamtanzahl
        """
        # Base Query
        conditions = [
            or_(
                Workflow.user_id == user_id,
                Workflow.is_template == True,  # noqa: E712
            )
        ]

        if company_id:
            conditions.append(
                or_(Workflow.company_id == company_id, Workflow.company_id.is_(None))
            )

        if trigger_type:
            conditions.append(Workflow.trigger_type == trigger_type)

        if is_active is not None:
            conditions.append(Workflow.is_active == is_active)

        if is_template is not None:
            conditions.append(Workflow.is_template == is_template)

        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Workflow.name.ilike(search_pattern),
                    Workflow.description.ilike(search_pattern),
                )
            )

        # Count Query
        count_query = select(func.count(Workflow.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data Query
        query = (
            select(Workflow)
            .where(and_(*conditions))
            .order_by(Workflow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        workflows = list(result.scalars().all())

        return workflows, total

    async def update_workflow(
        self,
        workflow_id: UUID,
        user_id: UUID,
        **updates: Any,
    ) -> Optional[Workflow]:
        """Aktualisiert einen Workflow.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID fuer Berechtigungspruefung
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierter Workflow oder None
        """
        workflow = await self.get_workflow(workflow_id, user_id, include_steps=False)
        if not workflow:
            return None

        # Nur eigene Workflows bearbeiten (keine Templates)
        if workflow.user_id != user_id:
            logger.warning(
                "workflow_update_denied",
                workflow_id=str(workflow_id),
                user_id=str(user_id),
            )
            return None

        # Erlaubte Felder
        allowed_fields = {
            "name",
            "description",
            "trigger_type",
            "trigger_config",
            "nodes",
            "edges",
            "variables",
            "is_active",
            "max_concurrent_executions",
            "timeout_seconds",
            "retry_config",
        }

        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                setattr(workflow, key, value)

        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(
            "workflow_updated",
            workflow_id=str(workflow_id),
            updated_fields=list(updates.keys()),
        )

        return workflow

    async def delete_workflow(
        self,
        workflow_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Loescht einen Workflow.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID fuer Berechtigungspruefung

        Returns:
            True wenn erfolgreich geloescht
        """
        workflow = await self.get_workflow(workflow_id, user_id, include_steps=False)
        if not workflow or workflow.user_id != user_id:
            return False

        # Loescht auch Steps durch CASCADE
        await self.db.delete(workflow)
        await self.db.commit()

        logger.info(
            "workflow_deleted",
            workflow_id=str(workflow_id),
            user_id=str(user_id),
        )

        return True

    async def duplicate_workflow(
        self,
        workflow_id: UUID,
        user_id: UUID,
        new_name: Optional[str] = None,
    ) -> Optional[Workflow]:
        """Dupliziert einen Workflow.

        Args:
            workflow_id: Original Workflow-ID
            user_id: User-ID des neuen Besitzers
            new_name: Optionaler neuer Name

        Returns:
            Duplizierter Workflow oder None
        """
        original = await self.get_workflow(workflow_id, user_id, include_steps=True)
        if not original:
            return None

        # Neuen Workflow erstellen
        duplicate = await self.create_workflow(
            user_id=user_id,
            name=new_name or f"{original.name} (Kopie)",
            trigger_type=original.trigger_type,
            trigger_config=original.trigger_config.copy() if original.trigger_config else {},
            nodes=original.nodes.copy() if original.nodes else [],
            edges=original.edges.copy() if original.edges else [],
            description=original.description,
            company_id=original.company_id,
            variables=original.variables.copy() if original.variables else {},
            max_concurrent_executions=original.max_concurrent_executions,
            timeout_seconds=original.timeout_seconds,
            retry_config=original.retry_config.copy() if original.retry_config else {},
        )

        # Steps duplizieren
        if original.steps:
            for step in original.steps:
                await self.create_step(
                    workflow_id=duplicate.id,
                    step_order=step.step_order,
                    step_type=step.step_type,
                    step_name=step.step_name,
                    config=step.config.copy() if step.config else {},
                    retry_on_failure=step.retry_on_failure,
                    max_retries=step.max_retries,
                    position_x=step.position_x,
                    position_y=step.position_y,
                )

        logger.info(
            "workflow_duplicated",
            original_id=str(workflow_id),
            duplicate_id=str(duplicate.id),
            user_id=str(user_id),
        )

        return duplicate

    async def toggle_workflow(
        self,
        workflow_id: UUID,
        user_id: UUID,
    ) -> Optional[Workflow]:
        """Aktiviert/Deaktiviert einen Workflow.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID

        Returns:
            Aktualisierter Workflow oder None
        """
        workflow = await self.get_workflow(workflow_id, user_id, include_steps=False)
        if not workflow or workflow.user_id != user_id:
            return None

        workflow.is_active = not workflow.is_active
        workflow.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(workflow)

        logger.info(
            "workflow_toggled",
            workflow_id=str(workflow_id),
            is_active=workflow.is_active,
        )

        return workflow

    # =========================================================================
    # Workflow Steps
    # =========================================================================

    async def create_step(
        self,
        workflow_id: UUID,
        step_order: int,
        step_type: str,
        step_name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        retry_on_failure: bool = True,
        max_retries: int = 3,
        position_x: float = 0.0,
        position_y: float = 0.0,
    ) -> WorkflowStep:
        """Erstellt einen Workflow-Step.

        Args:
            workflow_id: Workflow-ID
            step_order: Reihenfolge
            step_type: Step-Typ (condition, action, branch, delay, parallel)
            step_name: Optionaler Name
            config: Step-Konfiguration
            retry_on_failure: Bei Fehler wiederholen
            max_retries: Max Wiederholungen
            position_x: X-Position in ReactFlow
            position_y: Y-Position in ReactFlow

        Returns:
            Erstellter Step
        """
        step = WorkflowStep(
            id=uuid4(),
            workflow_id=workflow_id,
            step_order=step_order,
            step_type=step_type,
            step_name=step_name,
            config=config or {},
            retry_on_failure=retry_on_failure,
            max_retries=max_retries,
            position_x=position_x,
            position_y=position_y,
        )

        self.db.add(step)
        await self.db.commit()
        await self.db.refresh(step)

        logger.debug(
            "workflow_step_created",
            step_id=str(step.id),
            workflow_id=str(workflow_id),
            step_type=step_type,
        )

        return step

    async def get_steps(
        self,
        workflow_id: UUID,
    ) -> List[WorkflowStep]:
        """Holt alle Steps eines Workflows.

        Args:
            workflow_id: Workflow-ID

        Returns:
            Liste der Steps
        """
        query = (
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == workflow_id)
            .order_by(WorkflowStep.step_order)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_step(
        self,
        step_id: UUID,
        **updates: Any,
    ) -> Optional[WorkflowStep]:
        """Aktualisiert einen Step.

        Args:
            step_id: Step-ID
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierter Step oder None
        """
        query = select(WorkflowStep).where(WorkflowStep.id == step_id)
        result = await self.db.execute(query)
        step = result.scalar_one_or_none()

        if not step:
            return None

        allowed_fields = {
            "step_order",
            "step_type",
            "step_name",
            "config",
            "retry_on_failure",
            "max_retries",
            "position_x",
            "position_y",
        }

        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                setattr(step, key, value)

        step.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(step)

        return step

    async def delete_step(
        self,
        step_id: UUID,
    ) -> bool:
        """Loescht einen Step.

        Args:
            step_id: Step-ID

        Returns:
            True wenn erfolgreich
        """
        stmt = delete(WorkflowStep).where(WorkflowStep.id == step_id)
        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount > 0

    async def reorder_steps(
        self,
        workflow_id: UUID,
        step_orders: List[Dict[str, Any]],
    ) -> bool:
        """Ordnet Steps neu an.

        Args:
            workflow_id: Workflow-ID
            step_orders: Liste mit {step_id, step_order}

        Returns:
            True wenn erfolgreich
        """
        for item in step_orders:
            step_id = item.get("step_id")
            new_order = item.get("step_order")

            if step_id and new_order is not None:
                stmt = (
                    update(WorkflowStep)
                    .where(
                        and_(
                            WorkflowStep.id == UUID(str(step_id)),
                            WorkflowStep.workflow_id == workflow_id,
                        )
                    )
                    .values(step_order=new_order)
                )
                await self.db.execute(stmt)

        await self.db.commit()

        logger.info(
            "workflow_steps_reordered",
            workflow_id=str(workflow_id),
            count=len(step_orders),
        )

        return True

    async def batch_update_steps(
        self,
        workflow_id: UUID,
        steps_data: List[Dict[str, Any]],
    ) -> List[WorkflowStep]:
        """Aktualisiert mehrere Steps (ReactFlow Bulk-Update).

        Args:
            workflow_id: Workflow-ID
            steps_data: Liste mit Step-Daten

        Returns:
            Aktualisierte Steps
        """
        updated_steps = []

        for step_data in steps_data:
            step_id = step_data.pop("id", None)

            if step_id:
                # Update existierenden Step
                step = await self.update_step(UUID(str(step_id)), **step_data)
                if step:
                    updated_steps.append(step)
            else:
                # Neuen Step erstellen
                step = await self.create_step(
                    workflow_id=workflow_id,
                    step_order=step_data.get("step_order", 0),
                    step_type=step_data.get("step_type", "action"),
                    step_name=step_data.get("step_name"),
                    config=step_data.get("config", {}),
                    position_x=step_data.get("position_x", 0.0),
                    position_y=step_data.get("position_y", 0.0),
                )
                updated_steps.append(step)

        return updated_steps

    # =========================================================================
    # Workflow Templates
    # =========================================================================

    async def list_templates(
        self,
        category: Optional[str] = None,
    ) -> List[Workflow]:
        """Listet verfuegbare Workflow-Templates.

        Args:
            category: Optionale Kategorie

        Returns:
            Liste der Templates
        """
        conditions = [Workflow.is_template == True]  # noqa: E712

        if category:
            conditions.append(
                Workflow.trigger_config["category"].astext == category
            )

        query = (
            select(Workflow)
            .where(and_(*conditions))
            .order_by(Workflow.name)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def instantiate_template(
        self,
        template_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> Optional[Workflow]:
        """Erstellt Workflow aus Template.

        Args:
            template_id: Template-ID
            user_id: User-ID
            name: Optionaler Name
            company_id: Optionale Firmen-ID

        Returns:
            Erstellter Workflow oder None
        """
        template = await self.get_workflow(template_id, include_steps=True)
        if not template or not template.is_template:
            return None

        # Workflow erstellen
        workflow = await self.create_workflow(
            user_id=user_id,
            name=name or template.name,
            trigger_type=template.trigger_type,
            trigger_config=template.trigger_config.copy() if template.trigger_config else {},
            nodes=template.nodes.copy() if template.nodes else [],
            edges=template.edges.copy() if template.edges else [],
            description=template.description,
            company_id=company_id,
            variables=template.variables.copy() if template.variables else {},
            max_concurrent_executions=template.max_concurrent_executions,
            timeout_seconds=template.timeout_seconds,
            retry_config=template.retry_config.copy() if template.retry_config else {},
        )

        # Steps kopieren
        if template.steps:
            for step in template.steps:
                await self.create_step(
                    workflow_id=workflow.id,
                    step_order=step.step_order,
                    step_type=step.step_type,
                    step_name=step.step_name,
                    config=step.config.copy() if step.config else {},
                    retry_on_failure=step.retry_on_failure,
                    max_retries=step.max_retries,
                    position_x=step.position_x,
                    position_y=step.position_y,
                )

        logger.info(
            "workflow_template_instantiated",
            template_id=str(template_id),
            workflow_id=str(workflow.id),
            user_id=str(user_id),
        )

        return workflow

    # =========================================================================
    # Workflow Validation
    # =========================================================================

    async def validate_workflow(
        self,
        workflow_id: UUID,
    ) -> Dict[str, Any]:
        """Validiert einen Workflow.

        Args:
            workflow_id: Workflow-ID

        Returns:
            Validierungsergebnis mit errors und warnings
        """
        workflow = await self.get_workflow(workflow_id, include_steps=True)
        if not workflow:
            return {"valid": False, "errors": ["Workflow nicht gefunden"], "warnings": []}

        errors = []
        warnings = []

        # Trigger validieren
        if not workflow.trigger_type:
            errors.append("Kein Trigger-Typ definiert")

        if workflow.trigger_type == "schedule":
            cron = workflow.trigger_config.get("cron")
            if not cron:
                errors.append("Schedule-Trigger benoetigt Cron-Ausdruck")

        if workflow.trigger_type == "document_event":
            events = workflow.trigger_config.get("events", [])
            if not events:
                errors.append("Document-Event-Trigger benoetigt mindestens ein Event")

        # Steps validieren
        if not workflow.steps:
            warnings.append("Workflow hat keine Steps")
        else:
            for step in workflow.steps:
                step_errors = self._validate_step(step)
                errors.extend(step_errors)

        # Graph validieren (ReactFlow)
        if workflow.nodes and workflow.edges:
            graph_errors = self._validate_graph(workflow.nodes, workflow.edges)
            errors.extend(graph_errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _validate_step(self, step: WorkflowStep) -> List[str]:
        """Validiert einen einzelnen Step.

        Args:
            step: WorkflowStep

        Returns:
            Liste von Fehlern
        """
        errors = []

        if step.step_type == "action":
            action_type = step.config.get("action_type")
            if not action_type:
                errors.append(f"Step '{step.step_name}': Kein Action-Typ definiert")

        elif step.step_type == "condition":
            conditions = step.config.get("conditions")
            if not conditions:
                errors.append(f"Step '{step.step_name}': Keine Bedingungen definiert")

        elif step.step_type == "delay":
            delay_seconds = step.config.get("delay_seconds")
            if not delay_seconds or delay_seconds <= 0:
                errors.append(f"Step '{step.step_name}': Ungueltige Verzoegerung")

        return errors

    def _validate_graph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> List[str]:
        """Validiert ReactFlow-Graph.

        Args:
            nodes: ReactFlow-Knoten
            edges: ReactFlow-Kanten

        Returns:
            Liste von Fehlern
        """
        errors = []

        # Node-IDs sammeln
        node_ids = {node.get("id") for node in nodes}

        # Start-Knoten pruefen
        has_start = any(node.get("type") == "trigger" for node in nodes)
        if not has_start:
            errors.append("Graph benoetigt einen Trigger-Knoten")

        # Kanten pruefen
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")

            if source not in node_ids:
                errors.append(f"Kante referenziert unbekannten Quell-Knoten: {source}")
            if target not in node_ids:
                errors.append(f"Kante referenziert unbekannten Ziel-Knoten: {target}")

        # Zyklen erkennen (einfache Pruefung)
        # TODO: Vollstaendige Zyklenerkennung implementieren

        return errors

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_workflow_stats(
        self,
        workflow_id: UUID,
    ) -> Dict[str, Any]:
        """Holt Statistiken fuer einen Workflow.

        Args:
            workflow_id: Workflow-ID

        Returns:
            Statistik-Dictionary
        """
        workflow = await self.get_workflow(workflow_id, include_steps=False)
        if not workflow:
            return {}

        # Execution-Statistiken
        exec_query = select(
            func.count(WorkflowExecution.id).label("total"),
            func.sum(
                func.cast(WorkflowExecution.status == "completed", Integer)
            ).label("completed"),
            func.sum(
                func.cast(WorkflowExecution.status == "failed", Integer)
            ).label("failed"),
            func.avg(
                func.extract("epoch", WorkflowExecution.completed_at)
                - func.extract("epoch", WorkflowExecution.started_at)
            ).label("avg_duration"),
        ).where(WorkflowExecution.workflow_id == workflow_id)

        from sqlalchemy import Integer

        result = await self.db.execute(exec_query)
        row = result.one()

        return {
            "workflow_id": str(workflow_id),
            "name": workflow.name,
            "is_active": workflow.is_active,
            "execution_count": workflow.execution_count,
            "last_executed_at": workflow.last_executed_at.isoformat() if workflow.last_executed_at else None,
            "statistics": {
                "total_executions": row.total or 0,
                "completed": row.completed or 0,
                "failed": row.failed or 0,
                "success_rate": (
                    (row.completed / row.total * 100) if row.total else 0
                ),
                "avg_duration_seconds": float(row.avg_duration) if row.avg_duration else 0,
            },
        }
