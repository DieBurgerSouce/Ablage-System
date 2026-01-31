"""Process Task Service.

Verwaltet BPMN User Tasks:
- Claim/Unclaim: Task uebernehmen/freigeben
- Complete: Task abschliessen
- Delegate: Task delegieren
- List: Meine Tasks, Gruppen-Tasks
- Escalation: Eskalation bei Ueberfaelligkeit
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog

from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.bpmn_models.bpmn import (
    ProcessTask,
    ProcessInstance,
    ProcessDefinition,
    ProcessHistory,
    TaskStatus,
    TaskType,
    ProcessStatus,
)

logger = structlog.get_logger(__name__)


class ProcessTaskService:
    """Service fuer User Task Management.

    Ermoeglicht Benutzern das Bearbeiten von Workflow-Aufgaben:
    - Tasks abrufen (eigene, Gruppen, alle)
    - Tasks uebernehmen und abschliessen
    - Tasks delegieren
    - Prioritaet und Faelligkeit verwalten
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_task(
        self,
        task_id: UUID,
        company_id: UUID
    ) -> Optional[ProcessTask]:
        """Laedt einen einzelnen Task."""
        query = (
            select(ProcessTask)
            .where(
                and_(
                    ProcessTask.id == task_id,
                    ProcessTask.company_id == company_id
                )
            )
            .options(joinedload(ProcessTask.instance))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_tasks(
        self,
        user_id: UUID,
        company_id: UUID,
        status: Optional[TaskStatus] = None,
        include_group_tasks: bool = True,
        user_groups: Optional[List[str]] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[ProcessTask], int]:
        """Gibt Tasks fuer einen Benutzer zurueck.

        Beinhaltet:
        - Direkt zugewiesene Tasks
        - Optional: Tasks fuer Benutzer-Gruppen

        Args:
            user_id: Benutzer ID
            company_id: Mandant
            status: Filter nach Status
            include_group_tasks: Gruppen-Tasks einbeziehen
            user_groups: Gruppen des Benutzers
            page: Seite
            per_page: Eintraege pro Seite

        Returns:
            (Liste der Tasks, Gesamtanzahl)
        """
        conditions = [
            ProcessTask.company_id == company_id,
        ]

        # Nur aktive/zugewiesene Tasks standardmaessig
        if status:
            conditions.append(ProcessTask.status == status)
        else:
            conditions.append(
                ProcessTask.status.in_([
                    TaskStatus.ACTIVE,
                    TaskStatus.ASSIGNED,
                    TaskStatus.IN_PROGRESS
                ])
            )

        # User-spezifische Filter
        user_conditions = [ProcessTask.assignee_id == user_id]

        if include_group_tasks and user_groups:
            user_conditions.append(
                and_(
                    ProcessTask.assignee_id.is_(None),
                    ProcessTask.assignee_group.in_(user_groups)
                )
            )

        conditions.append(or_(*user_conditions))

        # Count
        count_query = select(func.count(ProcessTask.id)).where(and_(*conditions))
        total = await self.db.scalar(count_query) or 0

        # Data
        query = (
            select(ProcessTask)
            .where(and_(*conditions))
            .options(joinedload(ProcessTask.instance))
            .order_by(
                ProcessTask.priority.desc(),
                ProcessTask.due_date.asc().nullslast(),
                ProcessTask.created_at.asc()
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        tasks = list(result.unique().scalars().all())

        return tasks, total

    async def get_group_tasks(
        self,
        group_name: str,
        company_id: UUID,
        status: Optional[TaskStatus] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[ProcessTask], int]:
        """Gibt unzugewiesene Tasks fuer eine Gruppe zurueck."""
        conditions = [
            ProcessTask.company_id == company_id,
            ProcessTask.assignee_group == group_name,
            ProcessTask.assignee_id.is_(None),
        ]

        if status:
            conditions.append(ProcessTask.status == status)
        else:
            conditions.append(ProcessTask.status == TaskStatus.ACTIVE)

        count_query = select(func.count(ProcessTask.id)).where(and_(*conditions))
        total = await self.db.scalar(count_query) or 0

        query = (
            select(ProcessTask)
            .where(and_(*conditions))
            .options(joinedload(ProcessTask.instance))
            .order_by(
                ProcessTask.priority.desc(),
                ProcessTask.due_date.asc().nullslast()
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        tasks = list(result.unique().scalars().all())

        return tasks, total

    async def claim(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID
    ) -> ProcessTask:
        """Uebernimmt einen Task.

        Der Task muss ACTIVE und nicht bereits zugewiesen sein.

        Args:
            task_id: Task ID
            user_id: Uebernehmender User
            company_id: Mandant

        Returns:
            Uebernommener Task

        Raises:
            ValueError: Wenn Task nicht verfuegbar
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        if task.status not in (TaskStatus.ACTIVE, TaskStatus.PENDING):
            raise ValueError(f"Task kann nicht uebernommen werden (Status: {task.status})")

        if task.assignee_id and task.assignee_id != user_id:
            raise ValueError("Task ist bereits einem anderen Benutzer zugewiesen")

        task.assignee_id = user_id
        task.status = TaskStatus.ASSIGNED
        task.claimed_at = datetime.now(timezone.utc)

        await self._add_task_history(
            task=task,
            event_type="TASK_CLAIMED",
            message=f"Task uebernommen",
            actor_id=user_id
        )

        logger.info(
            "task_claimed",
            task_id=str(task_id),
            user_id=str(user_id)
        )

        return task

    async def unclaim(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID
    ) -> ProcessTask:
        """Gibt einen Task wieder frei.

        Args:
            task_id: Task ID
            user_id: Freigender User (muss Assignee sein)
            company_id: Mandant

        Returns:
            Freigegebener Task
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        if task.assignee_id != user_id:
            raise ValueError("Nur der zugewiesene Benutzer kann den Task freigeben")

        if task.status not in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
            raise ValueError(f"Task kann nicht freigegeben werden (Status: {task.status})")

        task.assignee_id = None
        task.status = TaskStatus.ACTIVE
        task.claimed_at = None

        await self._add_task_history(
            task=task,
            event_type="TASK_UNCLAIMED",
            message="Task freigegeben",
            actor_id=user_id
        )

        logger.info(
            "task_unclaimed",
            task_id=str(task_id)
        )

        return task

    async def start_working(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID
    ) -> ProcessTask:
        """Markiert Task als "In Bearbeitung"."""
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        if task.assignee_id != user_id:
            raise ValueError("Nur der zugewiesene Benutzer kann den Task bearbeiten")

        if task.status != TaskStatus.ASSIGNED:
            raise ValueError(f"Task ist nicht bereit zur Bearbeitung (Status: {task.status})")

        task.status = TaskStatus.IN_PROGRESS

        await self._add_task_history(
            task=task,
            event_type="TASK_STARTED",
            message="Bearbeitung gestartet",
            actor_id=user_id
        )

        return task

    async def complete(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID,
        variables: Optional[Dict[str, Any]] = None
    ) -> ProcessTask:
        """Schliesst einen Task ab.

        Args:
            task_id: Task ID
            user_id: Abschliessender User
            company_id: Mandant
            variables: Output-Variablen fuer den Prozess

        Returns:
            Abgeschlossener Task
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        # Claim automatisch wenn noch nicht zugewiesen
        if not task.assignee_id:
            task.assignee_id = user_id
            task.claimed_at = datetime.now(timezone.utc)
        elif task.assignee_id != user_id:
            raise ValueError("Nur der zugewiesene Benutzer kann den Task abschliessen")

        if task.status not in (
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.ACTIVE
        ):
            raise ValueError(f"Task kann nicht abgeschlossen werden (Status: {task.status})")

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)

        # Variablen in Task speichern
        if variables:
            current_vars = dict(task.task_variables)
            current_vars["_output"] = variables
            task.task_variables = current_vars

        await self._add_task_history(
            task=task,
            event_type="TASK_COMPLETED",
            message="Task abgeschlossen",
            actor_id=user_id,
            new_value=variables
        )

        logger.info(
            "task_completed",
            task_id=str(task_id),
            user_id=str(user_id)
        )

        # Benachrichtigungen senden (async, nicht blockierend)
        await self._send_task_completion_notifications(
            task=task,
            completed_by_id=user_id,
            company_id=company_id,
        )

        # Prozess fortsetzen
        from app.services.bpmn.process_execution_service import get_process_execution_service
        execution_service = get_process_execution_service(self.db)
        await execution_service.continue_after_task(
            instance_id=task.instance_id,
            element_id=task.element_id,
            company_id=company_id,
            result_variables=variables,
            user_id=user_id
        )

        return task

    async def delegate(
        self,
        task_id: UUID,
        from_user_id: UUID,
        to_user_id: UUID,
        company_id: UUID,
        comment: Optional[str] = None
    ) -> ProcessTask:
        """Delegiert einen Task an einen anderen Benutzer.

        Args:
            task_id: Task ID
            from_user_id: Delegierender User
            to_user_id: Empfaenger
            company_id: Mandant
            comment: Optionaler Kommentar

        Returns:
            Delegierter Task
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        if task.assignee_id and task.assignee_id != from_user_id:
            raise ValueError("Nur der zugewiesene Benutzer kann delegieren")

        if task.status not in (
            TaskStatus.ACTIVE,
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS
        ):
            raise ValueError(f"Task kann nicht delegiert werden (Status: {task.status})")

        # Delegation speichern
        task.delegated_from_id = task.assignee_id
        task.assignee_id = to_user_id
        task.status = TaskStatus.ASSIGNED
        task.claimed_at = datetime.now(timezone.utc)

        await self._add_task_history(
            task=task,
            event_type="TASK_DELEGATED",
            message=comment or "Task delegiert",
            actor_id=from_user_id
        )

        logger.info(
            "task_delegated",
            task_id=str(task_id),
            from_user=str(from_user_id),
            to_user=str(to_user_id)
        )

        return task

    async def set_due_date(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID,
        due_date: datetime
    ) -> ProcessTask:
        """Setzt das Faelligkeitsdatum."""
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        old_due = task.due_date
        task.due_date = due_date

        await self._add_task_history(
            task=task,
            event_type="TASK_DUE_DATE_CHANGED",
            message=f"Faelligkeit geaendert",
            actor_id=user_id,
            old_value={"due_date": str(old_due) if old_due else None},
            new_value={"due_date": str(due_date)}
        )

        return task

    async def set_priority(
        self,
        task_id: UUID,
        user_id: UUID,
        company_id: UUID,
        priority: int
    ) -> ProcessTask:
        """Setzt die Prioritaet (0-100)."""
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        if not 0 <= priority <= 100:
            raise ValueError("Prioritaet muss zwischen 0 und 100 liegen")

        old_priority = task.priority
        task.priority = priority

        await self._add_task_history(
            task=task,
            event_type="TASK_PRIORITY_CHANGED",
            message=f"Prioritaet geaendert: {old_priority} -> {priority}",
            actor_id=user_id
        )

        return task

    async def escalate(
        self,
        task_id: UUID,
        company_id: UUID,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> ProcessTask:
        """Eskaliert einen Task.

        Erhoeht Eskalationsstufe und markiert Zeitpunkt.

        Args:
            task_id: Task ID
            company_id: Mandant
            reason: Eskalationsgrund
            user_id: Eskalierender User (oder System)

        Returns:
            Eskalierter Task
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            raise ValueError("Task nicht gefunden")

        task.escalation_level += 1
        task.escalated_at = datetime.now(timezone.utc)
        task.status = TaskStatus.ESCALATED

        await self._add_task_history(
            task=task,
            event_type="TASK_ESCALATED",
            message=reason or f"Eskaliert auf Stufe {task.escalation_level}",
            actor_id=user_id,
            actor_type="user" if user_id else "system"
        )

        logger.warning(
            "task_escalated",
            task_id=str(task_id),
            level=task.escalation_level,
            reason=reason
        )

        return task

    async def get_overdue_tasks(
        self,
        company_id: UUID,
        limit: int = 100
    ) -> List[ProcessTask]:
        """Gibt alle ueberfaelligen Tasks zurueck."""
        now = datetime.now(timezone.utc)

        query = (
            select(ProcessTask)
            .where(
                and_(
                    ProcessTask.company_id == company_id,
                    ProcessTask.due_date < now,
                    ProcessTask.status.in_([
                        TaskStatus.ACTIVE,
                        TaskStatus.ASSIGNED,
                        TaskStatus.IN_PROGRESS
                    ])
                )
            )
            .options(joinedload(ProcessTask.instance))
            .order_by(ProcessTask.due_date.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.unique().scalars().all())

    async def get_task_statistics(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Gibt Task-Statistiken zurueck."""
        conditions = [ProcessTask.company_id == company_id]

        if user_id:
            conditions.append(ProcessTask.assignee_id == user_id)

        # Gesamt
        total = await self.db.scalar(
            select(func.count(ProcessTask.id)).where(and_(*conditions))
        ) or 0

        # Nach Status
        status_query = (
            select(
                ProcessTask.status,
                func.count(ProcessTask.id).label("count")
            )
            .where(and_(*conditions))
            .group_by(ProcessTask.status)
        )
        status_result = await self.db.execute(status_query)
        by_status = {row.status: row.count for row in status_result}

        # Ueberfaellig
        now = datetime.now(timezone.utc)
        overdue_conditions = conditions + [
            ProcessTask.due_date < now,
            ProcessTask.status.in_([
                TaskStatus.ACTIVE,
                TaskStatus.ASSIGNED,
                TaskStatus.IN_PROGRESS
            ])
        ]
        overdue = await self.db.scalar(
            select(func.count(ProcessTask.id)).where(and_(*overdue_conditions))
        ) or 0

        # Durchschnittliche Bearbeitungszeit (nur abgeschlossene)
        avg_duration_query = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        ProcessTask.completed_at - ProcessTask.claimed_at
                    )
                )
            )
            .where(
                and_(
                    *conditions,
                    ProcessTask.status == TaskStatus.COMPLETED,
                    ProcessTask.claimed_at.isnot(None),
                    ProcessTask.completed_at.isnot(None)
                )
            )
        )
        avg_duration_seconds = await self.db.scalar(avg_duration_query)

        return {
            "total": total,
            "by_status": by_status,
            "overdue": overdue,
            "average_duration_minutes": (
                round(avg_duration_seconds / 60, 1) if avg_duration_seconds else None
            ),
        }

    async def _add_task_history(
        self,
        task: ProcessTask,
        event_type: str,
        message: Optional[str] = None,
        actor_id: Optional[UUID] = None,
        actor_type: str = "user",
        old_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
    ) -> ProcessHistory:
        """Fuegt History-Eintrag fuer Task hinzu."""
        history = ProcessHistory(
            instance_id=task.instance_id,
            task_id=task.id,
            event_type=event_type,
            element_id=task.element_id,
            element_type="userTask",
            message=message,
            old_value=old_value,
            new_value=new_value,
            actor_id=actor_id,
            actor_type=actor_type,
            company_id=task.company_id,
        )
        self.db.add(history)
        return history

    async def _send_task_completion_notifications(
        self,
        task: ProcessTask,
        completed_by_id: UUID,
        company_id: UUID,
    ) -> None:
        """Sendet Benachrichtigungen bei Task-Abschluss.

        Benachrichtigt:
        - Den urspruenglich zugewiesenen Benutzer (wenn delegiert)
        - Slack-Kanal fuer wichtige Tasks (approval, review)

        Args:
            task: Der abgeschlossene Task
            completed_by_id: ID des abschliessenden Benutzers
            company_id: Firmen-ID
        """
        try:
            # Tasks die Slack-Benachrichtigung erhalten
            SLACK_WORTHY_TASK_TYPES = {
                "approval", "review", "sign", "escalation",
                "genehmigung", "pruefung", "unterschrift",
            }

            task_name = task.name or task.element_id
            task_name_lower = task_name.lower()

            # In-App Benachrichtigung fuer delegierte Tasks
            if task.delegated_from_id and task.delegated_from_id != completed_by_id:
                try:
                    from app.services.notification_service import (
                        get_notification_service,
                        NotificationType,
                        NotificationPriority,
                    )
                    notification_service = get_notification_service()
                    await notification_service.send_in_app_notification(
                        user_id=str(task.delegated_from_id),
                        title=f"Delegierter Task abgeschlossen: {task_name}",
                        message=f"Der von Ihnen delegierte Task wurde abgeschlossen.",
                        priority=NotificationPriority.NORMAL,
                        notification_type=NotificationType.SYSTEM_ALERT,
                        metadata={
                            "task_id": str(task.id),
                            "instance_id": str(task.instance_id),
                            "completed_by_id": str(completed_by_id),
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "task_notification_in_app_failed",
                        task_id=str(task.id),
                        error_type=type(e).__name__,
                    )

            # Slack-Benachrichtigung fuer wichtige Tasks
            is_slack_worthy = any(
                t in task_name_lower for t in SLACK_WORTHY_TASK_TYPES
            )

            if is_slack_worthy:
                try:
                    from app.services.slack_service import (
                        SlackService,
                        SlackNotificationType,
                    )
                    slack = SlackService()
                    await slack.send_notification(
                        notification_type=SlackNotificationType.WORKFLOW_COMPLETED,
                        title=f"Workflow-Task abgeschlossen: {task_name}",
                        message=f"Der Task wurde erfolgreich abgeschlossen.",
                        context={
                            "task_id": str(task.id),
                            "instance_id": str(task.instance_id),
                            "company_id": str(company_id),
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "task_notification_slack_failed",
                        task_id=str(task.id),
                        error_type=type(e).__name__,
                    )

        except Exception as e:
            # Benachrichtigungsfehler sollten Task-Abschluss nicht blockieren
            logger.warning(
                "task_completion_notification_failed",
                task_id=str(task.id),
                error_type=type(e).__name__,
            )


def get_task_service(db: AsyncSession) -> ProcessTaskService:
    """Factory Function fuer ProcessTaskService."""
    return ProcessTaskService(db)
