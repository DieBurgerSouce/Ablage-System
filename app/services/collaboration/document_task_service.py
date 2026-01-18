# -*- coding: utf-8 -*-
"""
Document Task Service for Ablage-System.

Enterprise-grade Aufgabenverwaltung fuer Dokumente:
- CRUD-Operationen fuer DocumentTask
- Zuweisung mit Benachrichtigung
- Status-Uebergaenge
- Deadline-Ueberwachung
- Eskalations-Integration

Feinpoliert und durchdacht - Aufgaben-Management auf Enterprise-Niveau.
"""

import structlog
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.db.models import (
    Document,
    DocumentTask,
    TaskPriority,
    TaskStatus,
    User,
    UserNotification,
    NotificationType as DBNotificationType,
)

logger = structlog.get_logger(__name__)


class TaskType:
    """Aufgabentyp-Konstanten."""
    REVIEW = "review"
    APPROVE = "approve"
    PROCESS = "process"
    CLASSIFY = "classify"
    VERIFY = "verify"
    OTHER = "other"


class DocumentTaskService:
    """Service fuer Dokument-Aufgaben-Verwaltung."""

    def __init__(self, db: AsyncSession):
        """Initialisiert den DocumentTaskService.

        Args:
            db: AsyncSession fuer Datenbankoperationen
        """
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_task(
        self,
        document_id: UUID,
        company_id: UUID,
        created_by_id: UUID,
        title: str,
        description: Optional[str] = None,
        task_type: str = TaskType.REVIEW,
        assigned_to_id: Optional[UUID] = None,
        priority: str = TaskPriority.NORMAL.value,
        due_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        notify_assignee: bool = True,
    ) -> DocumentTask:
        """Erstellt eine neue Aufgabe fuer ein Dokument.

        Args:
            document_id: ID des zugehoerigen Dokuments
            company_id: ID der Firma
            created_by_id: ID des erstellenden Benutzers
            title: Aufgabentitel
            description: Optionale Beschreibung
            task_type: Art der Aufgabe (review, approve, etc.)
            assigned_to_id: ID des zugewiesenen Benutzers
            priority: Prioritaet (low, normal, high, urgent)
            due_date: Faelligkeitsdatum
            metadata: Zusaetzliche Metadaten
            notify_assignee: Bei True wird der Zugewiesene benachrichtigt

        Returns:
            Erstellte DocumentTask

        Raises:
            ValueError: Bei ungueltigem Dokument oder Benutzer
        """
        # Validiere Dokument existiert
        doc_result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise ValueError("Dokument nicht gefunden oder gehoert nicht zur Firma")

        # Validiere assigned_to falls angegeben
        if assigned_to_id:
            user_result = await self.db.execute(
                select(User).where(User.id == assigned_to_id)
            )
            assigned_user = user_result.scalar_one_or_none()
            if not assigned_user:
                raise ValueError("Zugewiesener Benutzer nicht gefunden")

        # Erstelle Task
        task = DocumentTask(
            document_id=document_id,
            company_id=company_id,
            title=title,
            description=description,
            task_type=task_type,
            created_by_id=created_by_id,
            assigned_to_id=assigned_to_id,
            status=TaskStatus.OPEN.value,
            priority=priority,
            due_date=due_date,
            task_metadata=metadata or {},
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_created",
            task_id=str(task.id),
            document_id=str(document_id),
            task_type=task_type,
            assigned_to_id=str(assigned_to_id) if assigned_to_id else None,
        )

        # Benachrichtigung an Zugewiesenen
        if assigned_to_id and notify_assignee:
            await self._send_assignment_notification(task, assigned_to_id, created_by_id)

        return task

    async def get_task(
        self,
        task_id: UUID,
        company_id: Optional[UUID] = None,
    ) -> Optional[DocumentTask]:
        """Holt eine Aufgabe anhand ihrer ID.

        Args:
            task_id: ID der Aufgabe
            company_id: Optional - Firmenzugehoerigkeit pruefen

        Returns:
            DocumentTask oder None
        """
        query = (
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.document),
                selectinload(DocumentTask.created_by),
                selectinload(DocumentTask.assigned_to),
            )
            .where(DocumentTask.id == task_id)
        )

        if company_id:
            query = query.where(DocumentTask.company_id == company_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_task(
        self,
        task_id: UUID,
        company_id: UUID,
        updated_by_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        due_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DocumentTask]:
        """Aktualisiert eine Aufgabe.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            updated_by_id: ID des aktualisierenden Benutzers
            title: Neuer Titel
            description: Neue Beschreibung
            priority: Neue Prioritaet
            due_date: Neues Faelligkeitsdatum
            metadata: Neue Metadaten

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        # Nur offene oder in Bearbeitung befindliche Aufgaben aktualisierbar
        if task.status not in [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]:
            raise ValueError(f"Aufgabe mit Status '{task.status}' kann nicht aktualisiert werden")

        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        if due_date is not None:
            task.due_date = due_date
        if metadata is not None:
            task.task_metadata = {**task.task_metadata, **metadata}

        task.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_updated",
            task_id=str(task_id),
            updated_by=str(updated_by_id),
        )

        return task

    async def delete_task(
        self,
        task_id: UUID,
        company_id: UUID,
        deleted_by_id: UUID,
    ) -> bool:
        """Loescht eine Aufgabe.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            deleted_by_id: ID des loeschenden Benutzers

        Returns:
            True bei Erfolg, False wenn nicht gefunden
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return False

        await self.db.delete(task)
        await self.db.commit()

        logger.info(
            "task_deleted",
            task_id=str(task_id),
            deleted_by=str(deleted_by_id),
        )

        return True

    # =========================================================================
    # Status Transitions
    # =========================================================================

    async def start_task(
        self,
        task_id: UUID,
        company_id: UUID,
        user_id: UUID,
    ) -> Optional[DocumentTask]:
        """Startet die Bearbeitung einer Aufgabe.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            user_id: ID des Benutzers, der beginnt

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status != TaskStatus.OPEN.value:
            raise ValueError(f"Nur offene Aufgaben koennen gestartet werden (aktuell: {task.status})")

        task.status = TaskStatus.IN_PROGRESS.value
        task.updated_at = utc_now()

        # Falls nicht zugewiesen, automatisch zuweisen
        if not task.assigned_to_id:
            task.assigned_to_id = user_id

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_started",
            task_id=str(task_id),
            user_id=str(user_id),
        )

        return task

    async def complete_task(
        self,
        task_id: UUID,
        company_id: UUID,
        completed_by_id: UUID,
        completion_notes: Optional[str] = None,
    ) -> Optional[DocumentTask]:
        """Schliesst eine Aufgabe ab.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            completed_by_id: ID des abschliessenden Benutzers
            completion_notes: Optionale Abschlussnotizen

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status not in [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value]:
            raise ValueError(f"Aufgabe mit Status '{task.status}' kann nicht abgeschlossen werden")

        now = utc_now()
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = now
        task.completed_by_id = completed_by_id
        task.completion_notes = completion_notes
        task.updated_at = now

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_completed",
            task_id=str(task_id),
            completed_by=str(completed_by_id),
        )

        # Benachrichtigung an Ersteller
        if task.created_by_id and task.created_by_id != completed_by_id:
            await self._send_completion_notification(task, completed_by_id)

        return task

    async def cancel_task(
        self,
        task_id: UUID,
        company_id: UUID,
        cancelled_by_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[DocumentTask]:
        """Bricht eine Aufgabe ab.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            cancelled_by_id: ID des abbrechenden Benutzers
            reason: Optionaler Grund fuer Abbruch

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status == TaskStatus.COMPLETED.value:
            raise ValueError("Abgeschlossene Aufgaben koennen nicht abgebrochen werden")

        task.status = TaskStatus.CANCELLED.value
        task.updated_at = utc_now()
        if reason:
            task.task_metadata = {**task.task_metadata, "cancellation_reason": reason}

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_cancelled",
            task_id=str(task_id),
            cancelled_by=str(cancelled_by_id),
        )

        return task

    async def block_task(
        self,
        task_id: UUID,
        company_id: UUID,
        blocked_by_id: UUID,
        reason: str,
    ) -> Optional[DocumentTask]:
        """Markiert eine Aufgabe als blockiert.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            blocked_by_id: ID des blockierenden Benutzers
            reason: Grund fuer Blockierung (Pflichtfeld)

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]:
            raise ValueError(f"Aufgabe mit Status '{task.status}' kann nicht blockiert werden")

        task.status = TaskStatus.BLOCKED.value
        task.updated_at = utc_now()
        task.task_metadata = {**task.task_metadata, "block_reason": reason}

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_blocked",
            task_id=str(task_id),
            blocked_by=str(blocked_by_id),
        )

        return task

    async def unblock_task(
        self,
        task_id: UUID,
        company_id: UUID,
        unblocked_by_id: UUID,
    ) -> Optional[DocumentTask]:
        """Hebt die Blockierung einer Aufgabe auf.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            unblocked_by_id: ID des entblockierenden Benutzers

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status != TaskStatus.BLOCKED.value:
            raise ValueError("Nur blockierte Aufgaben koennen entblockt werden")

        task.status = TaskStatus.IN_PROGRESS.value
        task.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_unblocked",
            task_id=str(task_id),
            unblocked_by=str(unblocked_by_id),
        )

        return task

    # =========================================================================
    # Assignment Operations
    # =========================================================================

    async def assign_task(
        self,
        task_id: UUID,
        company_id: UUID,
        assigned_to_id: UUID,
        assigned_by_id: UUID,
        notify_assignee: bool = True,
    ) -> Optional[DocumentTask]:
        """Weist eine Aufgabe einem Benutzer zu.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            assigned_to_id: ID des neuen Zugewiesenen
            assigned_by_id: ID des Zuweisenden
            notify_assignee: Bei True wird der Zugewiesene benachrichtigt

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        if task.status in [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]:
            raise ValueError(f"Aufgabe mit Status '{task.status}' kann nicht zugewiesen werden")

        # Validiere neuen Zugewiesenen
        user_result = await self.db.execute(
            select(User).where(User.id == assigned_to_id)
        )
        assigned_user = user_result.scalar_one_or_none()
        if not assigned_user:
            raise ValueError("Benutzer nicht gefunden")

        old_assignee_id = task.assigned_to_id
        task.assigned_to_id = assigned_to_id
        task.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_assigned",
            task_id=str(task_id),
            assigned_to=str(assigned_to_id),
            assigned_by=str(assigned_by_id),
            previous_assignee=str(old_assignee_id) if old_assignee_id else None,
        )

        if notify_assignee:
            await self._send_assignment_notification(task, assigned_to_id, assigned_by_id)

        return task

    async def unassign_task(
        self,
        task_id: UUID,
        company_id: UUID,
        unassigned_by_id: UUID,
    ) -> Optional[DocumentTask]:
        """Entfernt die Zuweisung einer Aufgabe.

        Args:
            task_id: ID der Aufgabe
            company_id: ID der Firma
            unassigned_by_id: ID des Entfernenden

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task = await self.get_task(task_id, company_id)
        if not task:
            return None

        old_assignee_id = task.assigned_to_id
        task.assigned_to_id = None
        task.updated_at = utc_now()

        # Status zurueck auf OPEN wenn IN_PROGRESS
        if task.status == TaskStatus.IN_PROGRESS.value:
            task.status = TaskStatus.OPEN.value

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_unassigned",
            task_id=str(task_id),
            unassigned_by=str(unassigned_by_id),
            previous_assignee=str(old_assignee_id) if old_assignee_id else None,
        )

        return task

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def list_tasks(
        self,
        company_id: UUID,
        document_id: Optional[UUID] = None,
        assigned_to_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        overdue_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DocumentTask], int]:
        """Listet Aufgaben mit Filtern.

        Args:
            company_id: ID der Firma
            document_id: Filter nach Dokument
            assigned_to_id: Filter nach Zugewiesenem
            created_by_id: Filter nach Ersteller
            status: Filter nach Status
            priority: Filter nach Prioritaet
            task_type: Filter nach Aufgabentyp
            overdue_only: Nur ueberfaellige Aufgaben
            limit: Max. Anzahl Ergebnisse
            offset: Pagination Offset

        Returns:
            Tuple aus (Liste von Tasks, Gesamtanzahl)
        """
        base_filter = DocumentTask.company_id == company_id

        filters = [base_filter]

        if document_id:
            filters.append(DocumentTask.document_id == document_id)
        if assigned_to_id:
            filters.append(DocumentTask.assigned_to_id == assigned_to_id)
        if created_by_id:
            filters.append(DocumentTask.created_by_id == created_by_id)
        if status:
            filters.append(DocumentTask.status == status)
        if priority:
            filters.append(DocumentTask.priority == priority)
        if task_type:
            filters.append(DocumentTask.task_type == task_type)
        if overdue_only:
            now = utc_now()
            filters.append(DocumentTask.due_date < now)
            filters.append(
                DocumentTask.status.in_([TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value])
            )

        # Count Query
        count_query = select(func.count(DocumentTask.id)).where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Data Query
        query = (
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.document),
                selectinload(DocumentTask.created_by),
                selectinload(DocumentTask.assigned_to),
            )
            .where(and_(*filters))
            .order_by(
                DocumentTask.due_date.asc().nullslast(),
                DocumentTask.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        return list(tasks), total

    async def get_my_tasks(
        self,
        user_id: UUID,
        company_id: UUID,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[DocumentTask], int]:
        """Holt alle Aufgaben fuer einen Benutzer.

        Args:
            user_id: ID des Benutzers
            company_id: ID der Firma
            status: Optionaler Statusfilter
            limit: Max. Anzahl Ergebnisse
            offset: Pagination Offset

        Returns:
            Tuple aus (Liste von Tasks, Gesamtanzahl)
        """
        return await self.list_tasks(
            company_id=company_id,
            assigned_to_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_document_tasks(
        self,
        document_id: UUID,
        company_id: UUID,
        include_completed: bool = False,
    ) -> List[DocumentTask]:
        """Holt alle Aufgaben fuer ein Dokument.

        Args:
            document_id: ID des Dokuments
            company_id: ID der Firma
            include_completed: Auch abgeschlossene Aufgaben einbeziehen

        Returns:
            Liste von DocumentTasks
        """
        filters = [
            DocumentTask.document_id == document_id,
            DocumentTask.company_id == company_id,
        ]

        if not include_completed:
            filters.append(
                DocumentTask.status.notin_([
                    TaskStatus.COMPLETED.value,
                    TaskStatus.CANCELLED.value,
                ])
            )

        query = (
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.created_by),
                selectinload(DocumentTask.assigned_to),
            )
            .where(and_(*filters))
            .order_by(DocumentTask.created_at.desc())
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_overdue_tasks(
        self,
        company_id: UUID,
        limit: int = 100,
    ) -> List[DocumentTask]:
        """Holt alle ueberfaelligen Aufgaben.

        Args:
            company_id: ID der Firma
            limit: Max. Anzahl Ergebnisse

        Returns:
            Liste von ueberfaelligen DocumentTasks
        """
        now = utc_now()

        query = (
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.document),
                selectinload(DocumentTask.created_by),
                selectinload(DocumentTask.assigned_to),
            )
            .where(
                and_(
                    DocumentTask.company_id == company_id,
                    DocumentTask.due_date < now,
                    DocumentTask.status.in_([
                        TaskStatus.OPEN.value,
                        TaskStatus.IN_PROGRESS.value,
                    ]),
                )
            )
            .order_by(DocumentTask.due_date.asc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_tasks_due_soon(
        self,
        company_id: UUID,
        hours: int = 24,
        limit: int = 100,
    ) -> List[DocumentTask]:
        """Holt Aufgaben, die bald faellig sind.

        Args:
            company_id: ID der Firma
            hours: Stunden bis Faelligkeit
            limit: Max. Anzahl Ergebnisse

        Returns:
            Liste von bald faelligen DocumentTasks
        """
        now = utc_now()
        soon = now + timedelta(hours=hours)

        query = (
            select(DocumentTask)
            .options(
                selectinload(DocumentTask.document),
                selectinload(DocumentTask.created_by),
                selectinload(DocumentTask.assigned_to),
            )
            .where(
                and_(
                    DocumentTask.company_id == company_id,
                    DocumentTask.due_date >= now,
                    DocumentTask.due_date <= soon,
                    DocumentTask.status.in_([
                        TaskStatus.OPEN.value,
                        TaskStatus.IN_PROGRESS.value,
                    ]),
                    DocumentTask.reminder_sent == False,
                )
            )
            .order_by(DocumentTask.due_date.asc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_task_statistics(
        self,
        company_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Berechnet Aufgaben-Statistiken.

        Args:
            company_id: ID der Firma
            user_id: Optional - nur fuer diesen Benutzer

        Returns:
            Dict mit Statistiken
        """
        base_filter = DocumentTask.company_id == company_id
        if user_id:
            base_filter = and_(base_filter, DocumentTask.assigned_to_id == user_id)

        now = utc_now()

        # Gesamtanzahl
        total_result = await self.db.execute(
            select(func.count(DocumentTask.id)).where(base_filter)
        )
        total = total_result.scalar() or 0

        # Nach Status
        status_counts = {}
        for status in TaskStatus:
            status_result = await self.db.execute(
                select(func.count(DocumentTask.id)).where(
                    and_(base_filter, DocumentTask.status == status.value)
                )
            )
            status_counts[status.value] = status_result.scalar() or 0

        # Ueberfaellig
        overdue_result = await self.db.execute(
            select(func.count(DocumentTask.id)).where(
                and_(
                    base_filter,
                    DocumentTask.due_date < now,
                    DocumentTask.status.in_([
                        TaskStatus.OPEN.value,
                        TaskStatus.IN_PROGRESS.value,
                    ]),
                )
            )
        )
        overdue_count = overdue_result.scalar() or 0

        # Nach Prioritaet
        priority_counts = {}
        for priority in TaskPriority:
            priority_result = await self.db.execute(
                select(func.count(DocumentTask.id)).where(
                    and_(base_filter, DocumentTask.priority == priority.value)
                )
            )
            priority_counts[priority.value] = priority_result.scalar() or 0

        return {
            "totalTasks": total,
            "openTasks": status_counts.get(TaskStatus.OPEN.value, 0),
            "inProgressTasks": status_counts.get(TaskStatus.IN_PROGRESS.value, 0),
            "completedTasks": status_counts.get(TaskStatus.COMPLETED.value, 0),
            "cancelledTasks": status_counts.get(TaskStatus.CANCELLED.value, 0),
            "blockedTasks": status_counts.get(TaskStatus.BLOCKED.value, 0),
            "overdueTasks": overdue_count,
            "byPriority": priority_counts,
        }

    # =========================================================================
    # Notifications (Internal)
    # =========================================================================

    async def _send_assignment_notification(
        self,
        task: DocumentTask,
        assigned_to_id: UUID,
        assigned_by_id: UUID,
    ) -> None:
        """Sendet eine Zuweisungs-Benachrichtigung.

        Args:
            task: Die zugewiesene Aufgabe
            assigned_to_id: ID des Zugewiesenen
            assigned_by_id: ID des Zuweisenden
        """
        # Hole Zuweisenden Namen
        assignee_result = await self.db.execute(
            select(User).where(User.id == assigned_by_id)
        )
        assigner = assignee_result.scalar_one_or_none()
        assigner_name = assigner.full_name or assigner.username if assigner else "System"

        notification = UserNotification(
            user_id=assigned_to_id,
            notification_type=DBNotificationType.TASK_ASSIGNED.value,
            title="Neue Aufgabe zugewiesen",
            message=f"{assigner_name} hat Ihnen eine Aufgabe zugewiesen: {task.title}",
            from_user_id=assigned_by_id,
            document_id=task.document_id,
            action_url=f"/documents/{task.document_id}?tab=tasks",
            is_read=False,
        )

        self.db.add(notification)
        await self.db.commit()

        logger.info(
            "task_assignment_notification_sent",
            task_id=str(task.id),
            assigned_to=str(assigned_to_id),
        )

    async def _send_completion_notification(
        self,
        task: DocumentTask,
        completed_by_id: UUID,
    ) -> None:
        """Sendet eine Abschluss-Benachrichtigung an den Ersteller.

        Args:
            task: Die abgeschlossene Aufgabe
            completed_by_id: ID des Abschliessenden
        """
        # Hole Abschliessenden Namen
        completer_result = await self.db.execute(
            select(User).where(User.id == completed_by_id)
        )
        completer = completer_result.scalar_one_or_none()
        completer_name = completer.full_name or completer.username if completer else "System"

        notification = UserNotification(
            user_id=task.created_by_id,
            notification_type=DBNotificationType.TASK_COMPLETED.value,
            title="Aufgabe abgeschlossen",
            message=f"{completer_name} hat die Aufgabe abgeschlossen: {task.title}",
            from_user_id=completed_by_id,
            document_id=task.document_id,
            action_url=f"/documents/{task.document_id}?tab=tasks",
            is_read=False,
        )

        self.db.add(notification)
        await self.db.commit()

        logger.info(
            "task_completion_notification_sent",
            task_id=str(task.id),
            notified_user=str(task.created_by_id),
        )

    # =========================================================================
    # Reminder/Escalation Support
    # =========================================================================

    async def mark_reminder_sent(
        self,
        task_id: UUID,
    ) -> None:
        """Markiert eine Aufgabe als erinnert.

        Args:
            task_id: ID der Aufgabe
        """
        await self.db.execute(
            update(DocumentTask)
            .where(DocumentTask.id == task_id)
            .values(reminder_sent=True)
        )
        await self.db.commit()

    async def escalate_task(
        self,
        task_id: UUID,
        escalated_to_id: UUID,
        reason: Optional[str] = None,
    ) -> Optional[DocumentTask]:
        """Eskaliert eine Aufgabe.

        Args:
            task_id: ID der Aufgabe
            escalated_to_id: ID des Eskalationsziels
            reason: Grund der Eskalation

        Returns:
            Aktualisierte DocumentTask oder None
        """
        task_result = await self.db.execute(
            select(DocumentTask).where(DocumentTask.id == task_id)
        )
        task = task_result.scalar_one_or_none()

        if not task:
            return None

        now = utc_now()
        task.escalated = True
        task.escalated_at = now
        task.escalated_to_id = escalated_to_id
        task.updated_at = now

        if reason:
            task.task_metadata = {**task.task_metadata, "escalation_reason": reason}

        await self.db.commit()
        await self.db.refresh(task)

        logger.info(
            "task_escalated",
            task_id=str(task_id),
            escalated_to=str(escalated_to_id),
        )

        # Benachrichtigung an Eskalationsziel
        await self._send_escalation_notification(task, escalated_to_id)

        return task

    async def _send_escalation_notification(
        self,
        task: DocumentTask,
        escalated_to_id: UUID,
    ) -> None:
        """Sendet eine Eskalations-Benachrichtigung.

        Args:
            task: Die eskalierte Aufgabe
            escalated_to_id: ID des Eskalationsziels
        """
        notification = UserNotification(
            user_id=escalated_to_id,
            notification_type=DBNotificationType.TASK_ESCALATED.value,
            title="Aufgabe eskaliert",
            message=f"Eine Aufgabe wurde an Sie eskaliert: {task.title}",
            from_user_id=task.created_by_id,
            document_id=task.document_id,
            action_url=f"/documents/{task.document_id}?tab=tasks",
            is_read=False,
        )

        self.db.add(notification)
        await self.db.commit()


# =============================================================================
# Factory Function
# =============================================================================


def get_document_task_service(db: AsyncSession) -> DocumentTaskService:
    """Factory-Funktion fuer DocumentTaskService.

    Args:
        db: AsyncSession fuer Datenbankoperationen

    Returns:
        DocumentTaskService Instanz
    """
    return DocumentTaskService(db)
