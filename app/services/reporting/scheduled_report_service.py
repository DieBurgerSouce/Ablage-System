# -*- coding: utf-8 -*-
"""
Scheduled Report Service.

Verwaltet geplante Ausführungen von Ad-Hoc Reports.
Unterstützt tägliche, woechentliche und monatliche Zeitplaene.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Union

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_adhoc_reporting import (
    ScheduledReport,
    ScheduleFrequency,
    ExportFormat,
)

logger = structlog.get_logger(__name__)


class ScheduledReportService:
    """Service für geplante Report-Ausführungen."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_schedule(
        self,
        db: AsyncSession,
        report_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        frequency: str,
        recipients: List[str],
        export_format: str = "excel",
        time_of_day: str = "08:00",
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
    ) -> ScheduledReport:
        """Erstellt einen neuen Zeitplan für einen Report.

        Args:
            report_id: ID des Ad-Hoc Reports
            company_id: Mandanten-ID
            user_id: Ersteller-ID
            frequency: daily|weekly|monthly
            recipients: Liste der E-Mail-Empfänger
            export_format: pdf|excel|csv
            time_of_day: Uhrzeit im Format "HH:MM"
            day_of_week: 0=Montag bis 6=Sonntag (nur für weekly)
            day_of_month: 1-28 (nur für monthly)

        Returns:
            Erstellter ScheduledReport
        """
        # Validate frequency
        valid_frequencies = {f.value for f in ScheduleFrequency}
        if frequency not in valid_frequencies:
            raise ValueError(f"Ungültige Frequenz: {frequency}. Erlaubt: {valid_frequencies}")

        # Validate export format
        valid_formats = {f.value for f in ExportFormat}
        if export_format not in valid_formats:
            raise ValueError(f"Ungültiges Format: {export_format}. Erlaubt: {valid_formats}")

        # Validate time_of_day format
        if not self._validate_time_format(time_of_day):
            raise ValueError(f"Ungültiges Zeitformat: {time_of_day}. Erwartet: HH:MM")

        # Validate day_of_week for weekly
        if frequency == ScheduleFrequency.WEEKLY.value:
            if day_of_week is None:
                day_of_week = 0  # Default: Montag
            elif day_of_week < 0 or day_of_week > 6:
                raise ValueError("day_of_week muss zwischen 0 (Montag) und 6 (Sonntag) liegen")

        # Validate day_of_month for monthly
        if frequency == ScheduleFrequency.MONTHLY.value:
            if day_of_month is None:
                day_of_month = 1  # Default: 1. des Monats
            elif day_of_month < 1 or day_of_month > 28:
                raise ValueError("day_of_month muss zwischen 1 und 28 liegen")

        # Validate recipients
        if not recipients:
            raise ValueError("Mindestens ein Empfänger ist erforderlich")

        # Calculate next execution time
        next_send_at = self.calculate_next_send_at(
            frequency=frequency,
            time_of_day=time_of_day,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
        )

        schedule = ScheduledReport(
            report_id=report_id,
            company_id=company_id,
            frequency=frequency,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            time_of_day=time_of_day,
            export_format=export_format,
            recipients=recipients,
            is_active=True,
            next_send_at=next_send_at,
            created_by_user_id=user_id,
        )
        db.add(schedule)
        await db.commit()
        await db.refresh(schedule)

        logger.info(
            "scheduled_report_created",
            schedule_id=str(schedule.id),
            report_id=str(report_id),
            frequency=frequency,
            next_send_at=next_send_at.isoformat(),
        )
        return schedule

    async def update_schedule(
        self,
        db: AsyncSession,
        schedule_id: uuid.UUID,
        company_id: uuid.UUID,
        **updates: object,
    ) -> Optional[ScheduledReport]:
        """Aktualisiert einen Zeitplan."""
        result = await db.execute(
            select(ScheduledReport).where(
                and_(
                    ScheduledReport.id == schedule_id,
                    ScheduledReport.company_id == company_id,
                )
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return None

        allowed_fields = {
            "frequency", "day_of_week", "day_of_month", "time_of_day",
            "export_format", "recipients", "is_active",
        }

        for key, value in updates.items():
            if key in allowed_fields:
                setattr(schedule, key, value)

        # Recalculate next_send_at if schedule parameters changed
        recalc_keys = {"frequency", "day_of_week", "day_of_month", "time_of_day"}
        if recalc_keys.intersection(updates.keys()):
            schedule.next_send_at = self.calculate_next_send_at(
                frequency=schedule.frequency,
                time_of_day=schedule.time_of_day,
                day_of_week=schedule.day_of_week,
                day_of_month=schedule.day_of_month,
            )

        await db.commit()
        await db.refresh(schedule)

        logger.info("scheduled_report_updated", schedule_id=str(schedule_id))
        return schedule

    async def delete_schedule(
        self,
        db: AsyncSession,
        schedule_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> bool:
        """Löscht einen Zeitplan."""
        result = await db.execute(
            select(ScheduledReport).where(
                and_(
                    ScheduledReport.id == schedule_id,
                    ScheduledReport.company_id == company_id,
                )
            )
        )
        schedule = result.scalar_one_or_none()
        if not schedule:
            return False

        await db.delete(schedule)
        await db.commit()

        logger.info("scheduled_report_deleted", schedule_id=str(schedule_id))
        return True

    async def get_schedule(
        self,
        db: AsyncSession,
        schedule_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Optional[ScheduledReport]:
        """Laedt einen Zeitplan."""
        result = await db.execute(
            select(ScheduledReport).where(
                and_(
                    ScheduledReport.id == schedule_id,
                    ScheduledReport.company_id == company_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_schedules(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        report_id: Optional[uuid.UUID] = None,
        limit: int = 100,
    ) -> List[ScheduledReport]:
        """Listet Zeitplaene für ein Unternehmen auf."""
        stmt = select(ScheduledReport).where(
            ScheduledReport.company_id == company_id,
        )
        if report_id:
            stmt = stmt.where(ScheduledReport.report_id == report_id)

        stmt = stmt.order_by(ScheduledReport.next_send_at).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # SCHEDULING ENGINE
    # ------------------------------------------------------------------

    async def get_due_schedules(self, db: AsyncSession) -> List[ScheduledReport]:
        """Findet alle fälligen Zeitplaene.

        Returns:
            Liste der ScheduledReports, deren next_send_at <= jetzt ist.
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ScheduledReport).where(
                and_(
                    ScheduledReport.is_active == True,  # noqa: E712
                    ScheduledReport.next_send_at <= now,
                )
            ).order_by(ScheduledReport.next_send_at)
            .limit(50)
        )
        return list(result.scalars().all())

    async def mark_as_sent(
        self,
        db: AsyncSession,
        schedule: ScheduledReport,
    ) -> None:
        """Markiert einen Zeitplan als gesendet und berechnet den nächsten Zeitpunkt."""
        now = datetime.now(timezone.utc)
        schedule.last_sent_at = now
        schedule.next_send_at = self.calculate_next_send_at(
            frequency=schedule.frequency,
            time_of_day=schedule.time_of_day,
            day_of_week=schedule.day_of_week,
            day_of_month=schedule.day_of_month,
        )
        await db.commit()

    def calculate_next_send_at(
        self,
        frequency: str,
        time_of_day: str = "08:00",
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
    ) -> datetime:
        """Berechnet den nächsten Ausführungszeitpunkt.

        Args:
            frequency: daily|weekly|monthly
            time_of_day: "HH:MM"
            day_of_week: 0-6 (nur für weekly)
            day_of_month: 1-28 (nur für monthly)

        Returns:
            datetime (UTC) des nächsten Ausführungszeitpunkts
        """
        now = datetime.now(timezone.utc)
        hour, minute = self._parse_time(time_of_day)

        if frequency == ScheduleFrequency.DAILY.value:
            # Next day at the specified time
            next_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_dt <= now:
                next_dt += timedelta(days=1)
            return next_dt

        elif frequency == ScheduleFrequency.WEEKLY.value:
            target_weekday = day_of_week if day_of_week is not None else 0
            next_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Calculate days until target weekday
            days_ahead = target_weekday - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0 and next_dt <= now:
                days_ahead = 7

            next_dt += timedelta(days=days_ahead)
            return next_dt

        elif frequency == ScheduleFrequency.MONTHLY.value:
            target_day = day_of_month if day_of_month is not None else 1

            # Try current month
            try:
                next_dt = now.replace(
                    day=target_day, hour=hour, minute=minute,
                    second=0, microsecond=0,
                )
                if next_dt <= now:
                    # Move to next month
                    if now.month == 12:
                        next_dt = next_dt.replace(year=now.year + 1, month=1)
                    else:
                        next_dt = next_dt.replace(month=now.month + 1)
                return next_dt
            except ValueError:
                # Day doesn't exist in month (e.g., Feb 30) -> next month
                if now.month == 12:
                    next_dt = now.replace(
                        year=now.year + 1, month=1, day=target_day,
                        hour=hour, minute=minute, second=0, microsecond=0,
                    )
                else:
                    next_dt = now.replace(
                        month=now.month + 1, day=target_day,
                        hour=hour, minute=minute, second=0, microsecond=0,
                    )
                return next_dt

        else:
            # Fallback: next day
            return now + timedelta(days=1)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_time_format(time_str: str) -> bool:
        """Validates HH:MM format."""
        if len(time_str) != 5 or time_str[2] != ":":
            return False
        try:
            hour = int(time_str[:2])
            minute = int(time_str[3:])
            return 0 <= hour <= 23 and 0 <= minute <= 59
        except ValueError:
            return False

    @staticmethod
    def _parse_time(time_str: str) -> tuple:
        """Parses HH:MM string into (hour, minute) tuple."""
        try:
            parts = time_str.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return 8, 0  # Default: 08:00
