# -*- coding: utf-8 -*-
"""MahnTask Service - Aufgabenverwaltung fuer Mahnungswesen.

Verwaltet Tasks fuer das Mahnungswesen:
- Erstellen von Mahn-Aufgaben
- Snooze-Funktion (max 3x)
- Bulk-Operationen
- Zuweisung an Benutzer

Mahnstopp-Integration:
- Bei Reklamation wird Mahnung pausiert
- Automatische Task-Erstellung bei Mahnstopp-Ende
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from enum import Enum
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID, uuid4
import structlog

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    MahnTask,
    DunningRecord,
    PhoneCallLog,
    User,
)

logger = structlog.get_logger(__name__)


class MahnTaskType(str, Enum):
    """Mahn-Aufgabentyp."""
    REMINDER = "reminder"           # Zahlungserinnerung senden
    ESCALATE = "escalate"           # Zur naechsten Stufe eskalieren
    PHONE_CALL = "phone_call"       # Telefonkontakt herstellen
    REVIEW = "review"               # Fall pruefen
    COLLECTION = "collection"       # An Inkasso uebergeben


class MahnTaskStatus(str, Enum):
    """Mahn-Aufgabenstatus."""
    PENDING = "pending"             # Ausstehend
    IN_PROGRESS = "in_progress"     # In Bearbeitung
    COMPLETED = "completed"         # Erledigt
    SNOOZED = "snoozed"             # Zurueckgestellt
    CANCELLED = "cancelled"         # Abgebrochen


class PhoneCallOutcome(str, Enum):
    """Ergebnis eines Telefonats."""
    REACHED = "reached"                     # Erreicht
    NOT_REACHED = "not_reached"             # Nicht erreicht
    VOICEMAIL = "voicemail"                 # Mailbox
    CALLBACK_REQUESTED = "callback_requested"  # Rueckruf erbeten
    PAYMENT_PROMISED = "payment_promised"   # Zahlung zugesagt
    DISPUTE_RAISED = "dispute_raised"       # Reklamation erhoben


@dataclass
class MahnTaskFilter:
    """Filter fuer Mahn-Aufgaben."""
    status: Optional[MahnTaskStatus] = None
    task_type: Optional[MahnTaskType] = None
    assigned_user_id: Optional[UUID] = None
    due_date_from: Optional[date] = None
    due_date_to: Optional[date] = None
    priority: Optional[int] = None
    include_snoozed: bool = False


class MahnTaskService:
    """Service fuer Mahn-Aufgaben."""

    MAX_SNOOZE_COUNT = 3  # Maximale Anzahl Zurueckstellungen

    async def list_tasks(
        self,
        db: AsyncSession,
        user_id: UUID,
        filters: Optional[MahnTaskFilter] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Liste Mahn-Aufgaben auf.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID (fuer Zugriffspruefung)
            filters: Optionale Filter
            limit: Max. Ergebnisse
            offset: Offset fuer Pagination

        Returns:
            Tuple (Liste der Tasks, Gesamtanzahl)
        """
        # Basis-Query mit Joins
        query = (
            select(MahnTask)
            .join(DunningRecord, MahnTask.dunning_record_id == DunningRecord.id)
            .where(DunningRecord.user_id == user_id)
        )

        # Filter anwenden
        if filters:
            if filters.status:
                query = query.where(MahnTask.status == filters.status.value)
            if filters.task_type:
                query = query.where(MahnTask.task_type == filters.task_type.value)
            if filters.assigned_user_id:
                query = query.where(MahnTask.assigned_user_id == filters.assigned_user_id)
            if filters.due_date_from:
                query = query.where(MahnTask.due_date >= filters.due_date_from)
            if filters.due_date_to:
                query = query.where(MahnTask.due_date <= filters.due_date_to)
            if filters.priority:
                query = query.where(MahnTask.priority == filters.priority)
            if not filters.include_snoozed:
                query = query.where(
                    or_(
                        MahnTask.status != MahnTaskStatus.SNOOZED.value,
                        MahnTask.snoozed_until <= date.today()
                    )
                )

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Sortierung und Pagination
        query = query.order_by(
            MahnTask.priority.asc(),
            MahnTask.due_date.asc(),
            MahnTask.created_at.asc()
        )
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        tasks = result.scalars().all()

        return [self._task_to_dict(t) for t in tasks], total

    async def get_pending_tasks_summary(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Hole Zusammenfassung offener Aufgaben.

        Returns:
            Dictionary mit Aufgaben-Statistiken
        """
        today = date.today()

        # Basis-Query fuer User
        base_query = (
            select(MahnTask)
            .join(DunningRecord, MahnTask.dunning_record_id == DunningRecord.id)
            .where(DunningRecord.user_id == user_id)
            .where(MahnTask.status.in_([
                MahnTaskStatus.PENDING.value,
                MahnTaskStatus.IN_PROGRESS.value
            ]))
        )

        # Heute faellig
        due_today_query = base_query.where(MahnTask.due_date == today)
        due_today_result = await db.execute(select(func.count()).select_from(due_today_query.subquery()))
        due_today = due_today_result.scalar() or 0

        # Ueberfaellig
        overdue_query = base_query.where(MahnTask.due_date < today)
        overdue_result = await db.execute(select(func.count()).select_from(overdue_query.subquery()))
        overdue = overdue_result.scalar() or 0

        # Nach Typ gruppiert
        type_query = (
            select(MahnTask.task_type, func.count())
            .join(DunningRecord, MahnTask.dunning_record_id == DunningRecord.id)
            .where(DunningRecord.user_id == user_id)
            .where(MahnTask.status.in_([
                MahnTaskStatus.PENDING.value,
                MahnTaskStatus.IN_PROGRESS.value
            ]))
            .group_by(MahnTask.task_type)
        )
        type_result = await db.execute(type_query)
        by_type = {row[0]: row[1] for row in type_result}

        # Zurueckgestellte
        snoozed_query = (
            select(func.count())
            .select_from(MahnTask)
            .join(DunningRecord, MahnTask.dunning_record_id == DunningRecord.id)
            .where(DunningRecord.user_id == user_id)
            .where(MahnTask.status == MahnTaskStatus.SNOOZED.value)
        )
        snoozed_result = await db.execute(snoozed_query)
        snoozed = snoozed_result.scalar() or 0

        return {
            "due_today": due_today,
            "overdue": overdue,
            "snoozed": snoozed,
            "by_type": by_type,
            "total_pending": due_today + overdue,
        }

    async def create_task(
        self,
        db: AsyncSession,
        dunning_record_id: UUID,
        task_type: MahnTaskType,
        due_date: date,
        assigned_user_id: Optional[UUID] = None,
        priority: int = 3,
    ) -> Dict[str, Any]:
        """Erstelle neue Mahn-Aufgabe.

        Args:
            db: Datenbank-Session
            dunning_record_id: Mahnvorgang-ID
            task_type: Aufgabentyp
            due_date: Faelligkeitsdatum
            assigned_user_id: Optionaler Bearbeiter
            priority: Prioritaet (1=hoechste, 5=niedrigste)

        Returns:
            Erstellte Aufgabe als Dictionary
        """
        task = MahnTask(
            id=uuid4(),
            dunning_record_id=dunning_record_id,
            task_type=task_type.value,
            assigned_user_id=assigned_user_id,
            due_date=due_date,
            status=MahnTaskStatus.PENDING.value,
            priority=priority,
            snooze_count=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        logger.info(
            "mahn_task_created",
            task_id=str(task.id),
            dunning_record_id=str(dunning_record_id),
            task_type=task_type.value,
            due_date=due_date.isoformat(),
        )

        return self._task_to_dict(task)

    async def assign_task(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_id: UUID,
        assigned_user_id: UUID,
    ) -> Dict[str, Any]:
        """Weise Aufgabe einem Benutzer zu.

        Args:
            db: Datenbank-Session
            user_id: Aktueller Benutzer (fuer Zugriffspruefung)
            task_id: Aufgaben-ID
            assigned_user_id: Ziel-Benutzer

        Returns:
            Aktualisierte Aufgabe
        """
        task = await self._get_task_for_user(db, user_id, task_id)
        if not task:
            raise ValueError("Aufgabe nicht gefunden")

        task.assigned_user_id = assigned_user_id
        task.status = MahnTaskStatus.IN_PROGRESS.value
        task.updated_at = utc_now()

        await db.commit()
        await db.refresh(task)

        logger.info(
            "mahn_task_assigned",
            task_id=str(task_id),
            assigned_user_id=str(assigned_user_id),
        )

        return self._task_to_dict(task)

    async def snooze_task(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_id: UUID,
        snooze_until: date,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stelle Aufgabe zurueck (max 3x).

        Args:
            db: Datenbank-Session
            user_id: Aktueller Benutzer
            task_id: Aufgaben-ID
            snooze_until: Wiedervorlage-Datum
            reason: Optionaler Grund

        Returns:
            Aktualisierte Aufgabe

        Raises:
            ValueError: Wenn max. Zurueckstellungen erreicht
        """
        task = await self._get_task_for_user(db, user_id, task_id)
        if not task:
            raise ValueError("Aufgabe nicht gefunden")

        if task.snooze_count >= self.MAX_SNOOZE_COUNT:
            raise ValueError(
                f"Maximale Anzahl Zurueckstellungen ({self.MAX_SNOOZE_COUNT}) erreicht"
            )

        if snooze_until <= date.today():
            raise ValueError("Wiedervorlage-Datum muss in der Zukunft liegen")

        task.status = MahnTaskStatus.SNOOZED.value
        task.snoozed_until = snooze_until
        task.snooze_count += 1
        task.snooze_reason = reason
        task.updated_at = utc_now()

        await db.commit()
        await db.refresh(task)

        logger.info(
            "mahn_task_snoozed",
            task_id=str(task_id),
            snooze_until=snooze_until.isoformat(),
            snooze_count=task.snooze_count,
        )

        return self._task_to_dict(task)

    async def complete_task(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_id: UUID,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Schliesse Aufgabe ab.

        Args:
            db: Datenbank-Session
            user_id: Aktueller Benutzer
            task_id: Aufgaben-ID
            notes: Optionale Notizen

        Returns:
            Aktualisierte Aufgabe
        """
        task = await self._get_task_for_user(db, user_id, task_id)
        if not task:
            raise ValueError("Aufgabe nicht gefunden")

        task.status = MahnTaskStatus.COMPLETED.value
        task.completed_at = utc_now()
        task.completed_by_id = user_id
        task.completion_notes = notes
        task.updated_at = utc_now()

        await db.commit()
        await db.refresh(task)

        logger.info(
            "mahn_task_completed",
            task_id=str(task_id),
            completed_by=str(user_id),
        )

        return self._task_to_dict(task)

    async def cancel_task(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_id: UUID,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Breche Aufgabe ab.

        Args:
            db: Datenbank-Session
            user_id: Aktueller Benutzer
            task_id: Aufgaben-ID
            reason: Optionaler Grund

        Returns:
            Aktualisierte Aufgabe
        """
        task = await self._get_task_for_user(db, user_id, task_id)
        if not task:
            raise ValueError("Aufgabe nicht gefunden")

        task.status = MahnTaskStatus.CANCELLED.value
        task.completion_notes = reason
        task.updated_at = utc_now()

        await db.commit()
        await db.refresh(task)

        logger.info(
            "mahn_task_cancelled",
            task_id=str(task_id),
            reason=reason,
        )

        return self._task_to_dict(task)

    async def bulk_complete(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_ids: List[UUID],
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Schliesse mehrere Aufgaben ab.

        Args:
            db: Datenbank-Session
            user_id: Aktueller Benutzer
            task_ids: Liste von Aufgaben-IDs
            notes: Optionale Notizen

        Returns:
            Ergebnis mit Erfolgs- und Fehlerliste
        """
        successful = []
        failed = []

        for task_id in task_ids:
            try:
                await self.complete_task(db, user_id, task_id, notes)
                successful.append(str(task_id))
            except Exception as e:
                failed.append({"id": str(task_id), **safe_error_log(e)})

        logger.info(
            "mahn_tasks_bulk_completed",
            successful_count=len(successful),
            failed_count=len(failed),
        )

        return {
            "successful": successful,
            "failed": failed,
            "total_processed": len(task_ids),
        }

    async def log_phone_call(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_record_id: UUID,
        contact_name: str,
        outcome: PhoneCallOutcome,
        phone_number: Optional[str] = None,
        notes: Optional[str] = None,
        follow_up_required: bool = False,
        follow_up_date: Optional[date] = None,
        follow_up_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Protokolliere Telefonkontakt.

        Args:
            db: Datenbank-Session
            user_id: Anrufer-ID
            dunning_record_id: Mahnvorgang-ID
            contact_name: Kontaktperson
            outcome: Ergebnis des Gespraechs
            phone_number: Angerufene Nummer
            notes: Gespraechsnotizen
            follow_up_required: Nachfassen erforderlich?
            follow_up_date: Datum fuer Nachfassen
            follow_up_notes: Notizen fuer Nachfassen

        Returns:
            Erstelltes Protokoll
        """
        call_log = PhoneCallLog(
            id=uuid4(),
            dunning_record_id=dunning_record_id,
            called_at=utc_now(),
            called_by_id=user_id,
            contact_name=contact_name,
            phone_number=phone_number,
            outcome=outcome.value,
            notes=notes,
            follow_up_required=follow_up_required,
            follow_up_date=follow_up_date,
            follow_up_notes=follow_up_notes,
        )

        db.add(call_log)

        # Bei Reklamation: Mahnstopp setzen
        if outcome == PhoneCallOutcome.DISPUTE_RAISED:
            dunning = await db.get(DunningRecord, dunning_record_id)
            if dunning:
                dunning.mahnstopp = True
                dunning.mahnstopp_reason = f"Reklamation erhoben ({contact_name})"
                dunning.updated_at = utc_now()

        # Bei Zahlungszusage: Follow-up Task erstellen
        if outcome == PhoneCallOutcome.PAYMENT_PROMISED and follow_up_date:
            await self.create_task(
                db=db,
                dunning_record_id=dunning_record_id,
                task_type=MahnTaskType.REVIEW,
                due_date=follow_up_date,
                assigned_user_id=user_id,
                priority=2,
            )

        await db.commit()
        await db.refresh(call_log)

        logger.info(
            "phone_call_logged",
            call_id=str(call_log.id),
            dunning_record_id=str(dunning_record_id),
            outcome=outcome.value,
        )

        return self._call_log_to_dict(call_log)

    async def get_phone_call_history(
        self,
        db: AsyncSession,
        user_id: UUID,
        dunning_record_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Hole Telefon-Historie fuer Mahnvorgang (paginiert).

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID (fuer Zugriffspruefung)
            dunning_record_id: Mahnvorgang-ID
            limit: Maximale Anzahl Eintraege
            offset: Offset fuer Pagination

        Returns:
            Tuple aus (Liste von Telefonprotokollen, Gesamtanzahl)
        """
        # Zugriffspruefung
        dunning_query = select(DunningRecord).where(
            and_(
                DunningRecord.id == dunning_record_id,
                DunningRecord.user_id == user_id,
            )
        )
        dunning_result = await db.execute(dunning_query)
        if not dunning_result.scalar_one_or_none():
            raise ValueError("Mahnvorgang nicht gefunden")

        # Count-Query fuer Gesamtanzahl
        count_query = (
            select(func.count())
            .select_from(PhoneCallLog)
            .where(PhoneCallLog.dunning_record_id == dunning_record_id)
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginierte Telefon-Historie laden (mit Eager Loading)
        query = (
            select(PhoneCallLog)
            .options(selectinload(PhoneCallLog.called_by))
            .where(PhoneCallLog.dunning_record_id == dunning_record_id)
            .order_by(PhoneCallLog.called_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query)
        calls = result.scalars().all()

        return [self._call_log_to_dict(c) for c in calls], total

    async def reactivate_snoozed_tasks(
        self,
        db: AsyncSession,
    ) -> int:
        """Reaktiviere abgelaufene Snooze-Aufgaben.

        Wird vom Celery Beat Task taeglich aufgerufen.

        Returns:
            Anzahl reaktivierter Aufgaben
        """
        today = date.today()

        query = (
            update(MahnTask)
            .where(
                and_(
                    MahnTask.status == MahnTaskStatus.SNOOZED.value,
                    MahnTask.snoozed_until <= today,
                )
            )
            .values(
                status=MahnTaskStatus.PENDING.value,
                snoozed_until=None,
                updated_at=utc_now(),
            )
        )

        result = await db.execute(query)
        await db.commit()

        count = result.rowcount
        if count > 0:
            logger.info(
                "snoozed_tasks_reactivated",
                count=count,
            )

        return count

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_task_for_user(
        self,
        db: AsyncSession,
        user_id: UUID,
        task_id: UUID,
    ) -> Optional[MahnTask]:
        """Hole Aufgabe mit Zugriffspruefung."""
        query = (
            select(MahnTask)
            .join(DunningRecord, MahnTask.dunning_record_id == DunningRecord.id)
            .where(
                and_(
                    MahnTask.id == task_id,
                    DunningRecord.user_id == user_id,
                )
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _task_to_dict(self, task: MahnTask) -> Dict[str, Any]:
        """Konvertiere Task zu Dictionary."""
        return {
            "id": str(task.id),
            "dunning_record_id": str(task.dunning_record_id),
            "task_type": task.task_type,
            "assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "status": task.status,
            "snoozed_until": task.snoozed_until.isoformat() if task.snoozed_until else None,
            "snooze_count": task.snooze_count,
            "snooze_reason": task.snooze_reason,
            "priority": task.priority,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "completed_by_id": str(task.completed_by_id) if task.completed_by_id else None,
            "completion_notes": task.completion_notes,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    def _call_log_to_dict(self, call: PhoneCallLog) -> Dict[str, Any]:
        """Konvertiere PhoneCallLog zu Dictionary."""
        return {
            "id": str(call.id),
            "dunning_record_id": str(call.dunning_record_id),
            "called_at": call.called_at.isoformat() if call.called_at else None,
            "called_by_id": str(call.called_by_id) if call.called_by_id else None,
            "called_by_name": call.called_by.name if call.called_by else None,
            "contact_name": call.contact_name,
            "phone_number": call.phone_number,
            "outcome": call.outcome,
            "notes": call.notes,
            "follow_up_required": call.follow_up_required,
            "follow_up_date": call.follow_up_date.isoformat() if call.follow_up_date else None,
            "follow_up_notes": call.follow_up_notes,
        }


# Singleton
mahn_task_service = MahnTaskService()
