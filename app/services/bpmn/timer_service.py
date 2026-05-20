"""Timer Service für BPMN Timer Events.

Verwaltet Timer-Jobs für:
- Timer Start Events
- Timer Intermediate Catch Events
- Timer Boundary Events
- Cycle Timers (wiederkehrend)

Wird von Celery Beat regelmäßig aufgerufen.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID
import structlog

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.bpmn_models.bpmn import (
    ProcessTimerJob,
    ProcessInstance,
    ProcessStatus,
)

logger = structlog.get_logger(__name__)


class TimerService:
    """Service für Timer-Event Verarbeitung.

    Hauptaufgaben:
    - Fällige Timer finden und ausführen
    - Wiederholende Timer (Cycles) neu planen
    - Abgelaufene/stornierte Timer bereinigen
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_due_timers(
        self,
        company_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[ProcessTimerJob]:
        """Gibt alle fälligen Timer zurück.

        Args:
            company_id: Optional Filter nach Mandant
            limit: Maximale Anzahl

        Returns:
            Liste fälliger Timer-Jobs
        """
        now = datetime.now(timezone.utc)

        conditions = [
            ProcessTimerJob.is_active == True,
            ProcessTimerJob.due_at <= now,
        ]

        if company_id:
            conditions.append(ProcessTimerJob.company_id == company_id)

        query = (
            select(ProcessTimerJob)
            .where(and_(*conditions))
            .order_by(ProcessTimerJob.due_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def execute_timer(
        self,
        timer_id: UUID,
        company_id: UUID
    ) -> bool:
        """Führt einen Timer aus.

        Args:
            timer_id: Timer-Job ID
            company_id: Mandant

        Returns:
            True wenn erfolgreich ausgeführt
        """
        # Timer laden
        timer = await self._get_timer(timer_id, company_id)
        if not timer:
            logger.warning("timer_not_found", timer_id=str(timer_id))
            return False

        if not timer.is_active:
            logger.info("timer_already_inactive", timer_id=str(timer_id))
            return False

        # Instanz prüfen
        instance = await self._get_instance(timer.instance_id, company_id)
        if not instance or instance.status != ProcessStatus.RUNNING:
            # Instanz nicht mehr aktiv - Timer deaktivieren
            timer.is_active = False
            await self.db.flush()
            logger.info(
                "timer_deactivated_instance_not_running",
                timer_id=str(timer_id),
                instance_id=str(timer.instance_id)
            )
            return False

        logger.info(
            "executing_timer",
            timer_id=str(timer_id),
            element_id=timer.element_id,
            instance_id=str(timer.instance_id)
        )

        try:
            # Prozess fortsetzen
            from app.services.bpmn.process_execution_service import (
                get_process_execution_service
            )
            from app.services.bpmn.bpmn_parser import BPMNProcess


            execution_service = get_process_execution_service(self.db)

            # Definition laden
            definition = await execution_service._get_definition_by_id(
                instance.definition_id
            )
            process = BPMNProcess.from_dict(definition.process_data)

            # Element finden
            element = process.get_element(timer.element_id)
            if not element:
                logger.error(
                    "timer_element_not_found",
                    timer_id=str(timer_id),
                    element_id=timer.element_id
                )
                timer.is_active = False
                return False

            # Element aus current_elements entfernen falls vorhanden
            current = list(instance.current_elements)
            if timer.element_id in current:
                current.remove(timer.element_id)
            instance.current_elements = current

            # Flow fortsetzen
            await execution_service._continue_flow(
                instance=instance,
                process=process,
                element=element,
                user_id=None
            )

            # History eintragen
            await execution_service._add_history(
                instance=instance,
                event_type="TIMER_FIRED",
                element_id=timer.element_id,
                message=f"Timer ausgeführt ({timer.timer_type}: {timer.timer_value})",
                actor_type="timer"
            )

            # Timer aktualisieren
            timer.last_executed_at = datetime.now(timezone.utc)

            # Bei Cycle: Nächste Ausführung planen
            if timer.timer_type == "cycle" and timer.repeat_count:
                if timer.repeat_count > 1:
                    timer.repeat_count -= 1
                    timer.due_at = self._calculate_next_cycle(timer)
                    logger.info(
                        "cycle_timer_rescheduled",
                        timer_id=str(timer_id),
                        next_due=str(timer.due_at),
                        remaining=timer.repeat_count
                    )
                else:
                    timer.is_active = False
            else:
                timer.is_active = False

            await self.db.flush()

            logger.info(
                "timer_executed_successfully",
                timer_id=str(timer_id)
            )
            return True

        except Exception as e:
            logger.error(
                "timer_execution_failed",
                timer_id=str(timer_id),
                **safe_error_log(e)
            )
            # Bei Fehler: Timer nicht deaktivieren für Retry
            return False

    async def execute_due_timers(
        self,
        company_id: Optional[UUID] = None,
        batch_size: int = 50
    ) -> int:
        """Führt alle fälligen Timer aus.

        Args:
            company_id: Optional Filter nach Mandant
            batch_size: Anzahl pro Batch

        Returns:
            Anzahl ausgeführter Timer
        """
        timers = await self.get_due_timers(company_id, batch_size)
        executed = 0

        for timer in timers:
            try:
                success = await self.execute_timer(timer.id, timer.company_id)
                if success:
                    executed += 1
            except Exception as e:
                logger.error(
                    "timer_batch_execution_error",
                    timer_id=str(timer.id),
                    **safe_error_log(e)
                )

        return executed

    async def cancel_timer(
        self,
        timer_id: UUID,
        company_id: UUID
    ) -> bool:
        """Storniert einen Timer.

        Args:
            timer_id: Timer ID
            company_id: Mandant

        Returns:
            True wenn erfolgreich storniert
        """
        timer = await self._get_timer(timer_id, company_id)
        if not timer:
            return False

        timer.is_active = False
        await self.db.flush()

        logger.info("timer_cancelled", timer_id=str(timer_id))
        return True

    async def cancel_instance_timers(
        self,
        instance_id: UUID,
        company_id: UUID
    ) -> int:
        """Storniert alle Timer einer Instanz.

        Args:
            instance_id: Instanz ID
            company_id: Mandant

        Returns:
            Anzahl stornierter Timer
        """
        result = await self.db.execute(
            update(ProcessTimerJob)
            .where(
                and_(
                    ProcessTimerJob.instance_id == instance_id,
                    ProcessTimerJob.company_id == company_id,
                    ProcessTimerJob.is_active == True
                )
            )
            .values(is_active=False)
        )
        count = result.rowcount
        await self.db.flush()

        logger.info(
            "instance_timers_cancelled",
            instance_id=str(instance_id),
            count=count
        )
        return count

    async def cleanup_old_timers(
        self,
        days_old: int = 30,
        company_id: Optional[UUID] = None
    ) -> int:
        """Entfernt alte, inaktive Timer.

        Args:
            days_old: Alter in Tagen
            company_id: Optional Filter

        Returns:
            Anzahl gelöschter Timer
        """
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)

        conditions = [
            ProcessTimerJob.is_active == False,
            ProcessTimerJob.last_executed_at < cutoff
        ]

        if company_id:
            conditions.append(ProcessTimerJob.company_id == company_id)

        result = await self.db.execute(
            delete(ProcessTimerJob).where(and_(*conditions))
        )
        count = result.rowcount
        await self.db.flush()

        logger.info(
            "old_timers_cleaned",
            count=count,
            days_old=days_old
        )
        return count

    async def get_timer_statistics(
        self,
        company_id: UUID
    ) -> dict:
        """Gibt Timer-Statistiken zurück."""
        from sqlalchemy import func

        # Aktive Timer
        active_count = await self.db.scalar(
            select(func.count(ProcessTimerJob.id)).where(
                and_(
                    ProcessTimerJob.company_id == company_id,
                    ProcessTimerJob.is_active == True
                )
            )
        ) or 0

        # Fällige Timer
        now = datetime.now(timezone.utc)
        due_count = await self.db.scalar(
            select(func.count(ProcessTimerJob.id)).where(
                and_(
                    ProcessTimerJob.company_id == company_id,
                    ProcessTimerJob.is_active == True,
                    ProcessTimerJob.due_at <= now
                )
            )
        ) or 0

        # Nach Typ
        type_query = (
            select(
                ProcessTimerJob.timer_type,
                func.count(ProcessTimerJob.id).label("count")
            )
            .where(
                and_(
                    ProcessTimerJob.company_id == company_id,
                    ProcessTimerJob.is_active == True
                )
            )
            .group_by(ProcessTimerJob.timer_type)
        )
        type_result = await self.db.execute(type_query)
        by_type = {row.timer_type: row.count for row in type_result}

        return {
            "active": active_count,
            "due": due_count,
            "by_type": by_type,
        }

    def _calculate_next_cycle(self, timer: ProcessTimerJob) -> datetime:
        """Berechnet nächsten Ausführungszeitpunkt für Cycle Timer."""
        import isodate

        # Cycle-Format: R3/PT1H oder R/PT1H (unendlich)
        parts = timer.timer_value.split("/")
        if len(parts) >= 2:
            duration_str = parts[1]
            duration = isodate.parse_duration(duration_str)
            return datetime.now(timezone.utc) + duration

        # Fallback: 1 Stunde
        return datetime.now(timezone.utc) + timedelta(hours=1)

    async def _get_timer(
        self,
        timer_id: UUID,
        company_id: UUID
    ) -> Optional[ProcessTimerJob]:
        """Laedt einen Timer."""
        query = select(ProcessTimerJob).where(
            and_(
                ProcessTimerJob.id == timer_id,
                ProcessTimerJob.company_id == company_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_instance(
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


def get_timer_service(db: AsyncSession) -> TimerService:
    """Factory Function für TimerService."""
    return TimerService(db)
