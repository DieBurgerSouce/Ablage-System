# -*- coding: utf-8 -*-
"""
Report Scheduler Service.

Verwaltet geplante Report-Ausfuehrungen und E-Mail-Versand.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReportExecution, ReportTemplate, User

logger = structlog.get_logger(__name__)


# Versuche croniter zu importieren
try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    logger.warning("croniter not available - schedule validation disabled")


class ReportSchedulerService:
    """Service fuer geplante Report-Ausfuehrungen."""

    _instance: Optional["ReportSchedulerService"] = None

    def __new__(cls) -> "ReportSchedulerService":
        """Singleton-Pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def validate_cron_expression(self, cron_expression: str) -> bool:
        """Validiert einen Cron-Ausdruck."""
        if not CRONITER_AVAILABLE:
            logger.warning("croniter not available - skipping validation")
            return True

        try:
            croniter(cron_expression)
            return True
        except (KeyError, ValueError):
            return False

    def get_next_run_time(
        self,
        cron_expression: str,
        timezone_str: str = "Europe/Berlin",
    ) -> Optional[datetime]:
        """Berechnet die naechste Ausfuehrungszeit."""
        if not CRONITER_AVAILABLE:
            return None

        try:
            import pytz
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            cron = croniter(cron_expression, now)
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"Error calculating next run time: {e}")
            return None

    async def enable_schedule(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
        cron_expression: str,
        timezone_str: str = "Europe/Berlin",
        recipients: Optional[List[str]] = None,
        format: str = "excel",
    ) -> Optional[ReportTemplate]:
        """Aktiviert einen Zeitplan fuer einen Report."""
        # Validiere Cron-Ausdruck
        if not self.validate_cron_expression(cron_expression):
            logger.warning(
                "invalid_cron_expression",
                template_id=str(template_id),
                cron_expression=cron_expression,
            )
            return None

        # Template laden
        result = await db.execute(
            select(ReportTemplate)
            .where(ReportTemplate.id == template_id)
            .where(ReportTemplate.user_id == user_id)
        )
        template = result.scalar_one_or_none()

        if not template:
            return None

        # Zeitplan konfigurieren
        template.is_scheduled = True
        template.schedule_config = {
            "cron_expression": cron_expression,
            "timezone": timezone_str,
            "recipients": recipients or [],
            "format": format,
            "enabled": True,
            "last_run": None,
            "next_run": self.get_next_run_time(cron_expression, timezone_str).isoformat()
            if self.get_next_run_time(cron_expression, timezone_str)
            else None,
        }

        await db.commit()
        await db.refresh(template)

        logger.info(
            "report_schedule_enabled",
            template_id=str(template_id),
            cron_expression=cron_expression,
            recipients=recipients,
        )

        return template

    async def disable_schedule(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Deaktiviert einen Zeitplan."""
        result = await db.execute(
            update(ReportTemplate)
            .where(ReportTemplate.id == template_id)
            .where(ReportTemplate.user_id == user_id)
            .values(
                is_scheduled=False,
                schedule_config=None,
            )
        )
        await db.commit()

        if result.rowcount > 0:
            logger.info("report_schedule_disabled", template_id=str(template_id))
            return True

        return False

    async def get_due_reports(
        self,
        db: AsyncSession,
        limit: int = 100,
    ) -> List[ReportTemplate]:
        """Holt alle faelligen Reports."""
        now = datetime.now(timezone.utc)

        # Reports die scheduled sind und deren next_run in der Vergangenheit liegt
        query = (
            select(ReportTemplate)
            .where(ReportTemplate.is_scheduled == True)
            .limit(limit)
        )

        result = await db.execute(query)
        templates = list(result.scalars().all())

        # Filtere nach next_run
        due_reports = []
        for template in templates:
            if template.schedule_config:
                next_run_str = template.schedule_config.get("next_run")
                if next_run_str:
                    try:
                        next_run = datetime.fromisoformat(next_run_str.replace("Z", "+00:00"))
                        if next_run <= now:
                            due_reports.append(template)
                    except ValueError as e:
                        logger.debug("next_run_parse_failed", error_type=type(e).__name__)

        return due_reports

    async def create_execution(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        executed_by_id: Optional[uuid.UUID],
        format: str,
        trigger_type: str = "manual",
        filter_snapshot: Optional[Dict[str, Any]] = None,
    ) -> ReportExecution:
        """Erstellt einen neuen Execution-Eintrag."""
        execution = ReportExecution(
            id=uuid.uuid4(),
            template_id=template_id,
            executed_by_id=executed_by_id,
            status="pending",
            format=format,
            trigger_type=trigger_type,
            filter_snapshot=filter_snapshot,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        logger.info(
            "report_execution_created",
            execution_id=str(execution.id),
            template_id=str(template_id),
            trigger_type=trigger_type,
        )

        return execution

    async def update_execution_status(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
        status: str,
        row_count: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        file_path: Optional[str] = None,
        download_url: Optional[str] = None,
        download_expires_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[ReportExecution]:
        """Aktualisiert den Status einer Execution."""
        result = await db.execute(
            select(ReportExecution).where(ReportExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            return None

        now = datetime.now(timezone.utc)

        execution.status = status

        if status == "running" and not execution.started_at:
            execution.started_at = now
        elif status in ["completed", "failed"]:
            execution.completed_at = now
            if execution.started_at:
                execution.duration_ms = int((now - execution.started_at).total_seconds() * 1000)

        if row_count is not None:
            execution.row_count = row_count
        if file_size_bytes is not None:
            execution.file_size_bytes = file_size_bytes
        if file_path is not None:
            execution.file_path = file_path
        if download_url is not None:
            execution.download_url = download_url
        if download_expires_at is not None:
            execution.download_expires_at = download_expires_at
        if error_message is not None:
            execution.error_message = error_message
        if error_details is not None:
            execution.error_details = error_details

        await db.commit()
        await db.refresh(execution)

        logger.info(
            "report_execution_updated",
            execution_id=str(execution_id),
            status=status,
            row_count=row_count,
        )

        return execution

    async def update_schedule_after_run(
        self,
        db: AsyncSession,
        template: ReportTemplate,
    ) -> None:
        """Aktualisiert den Zeitplan nach einer Ausfuehrung."""
        if not template.schedule_config:
            return

        now = datetime.now(timezone.utc)
        cron_expression = template.schedule_config.get("cron_expression")
        timezone_str = template.schedule_config.get("timezone", "Europe/Berlin")

        if cron_expression:
            next_run = self.get_next_run_time(cron_expression, timezone_str)

            template.schedule_config = {
                **template.schedule_config,
                "last_run": now.isoformat(),
                "next_run": next_run.isoformat() if next_run else None,
            }
            template.last_executed_at = now

            await db.commit()

    async def list_executions(
        self,
        db: AsyncSession,
        template_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReportExecution]:
        """Listet Executions."""
        query = select(ReportExecution)

        if template_id:
            query = query.where(ReportExecution.template_id == template_id)
        if user_id:
            query = query.where(ReportExecution.executed_by_id == user_id)
        if status:
            query = query.where(ReportExecution.status == status)

        query = query.order_by(ReportExecution.created_at.desc())
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_execution(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
    ) -> Optional[ReportExecution]:
        """Holt eine Execution."""
        result = await db.execute(
            select(ReportExecution).where(ReportExecution.id == execution_id)
        )
        return result.scalar_one_or_none()

    async def cleanup_old_executions(
        self,
        db: AsyncSession,
        days: int = 90,
    ) -> int:
        """Loescht alte Executions."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        from sqlalchemy import delete

        result = await db.execute(
            delete(ReportExecution)
            .where(ReportExecution.created_at < cutoff)
            .where(ReportExecution.status.in_(["completed", "failed"]))
        )
        await db.commit()

        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(
                "old_executions_cleaned_up",
                deleted_count=deleted_count,
                cutoff_days=days,
            )

        return deleted_count

    def get_schedule_presets(self) -> List[Dict[str, Any]]:
        """Gibt vordefinierte Zeitplan-Optionen zurueck."""
        return [
            {"id": "daily_morning", "name": "Taeglich 08:00", "cron": "0 8 * * *"},
            {"id": "daily_evening", "name": "Taeglich 18:00", "cron": "0 18 * * *"},
            {"id": "weekly_monday", "name": "Woechentlich Montag 08:00", "cron": "0 8 * * 1"},
            {"id": "weekly_friday", "name": "Woechentlich Freitag 16:00", "cron": "0 16 * * 5"},
            {"id": "monthly_first", "name": "Monatlich 1. Tag 08:00", "cron": "0 8 1 * *"},
            {"id": "monthly_last_workday", "name": "Letzter Werktag 18:00", "cron": "0 18 L * *"},
            {"id": "quarterly", "name": "Quartalsweise 1. Tag", "cron": "0 8 1 1,4,7,10 *"},
        ]
