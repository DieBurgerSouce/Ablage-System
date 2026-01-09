"""Service fuer die Verwaltung von Fristen im Privat-Modul."""

import uuid
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from typing import Optional, List
from io import BytesIO

from sqlalchemy import select, func, and_, or_
from datetime import timezone as tz
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    PrivatDeadline,
    PrivatDeadlineNotification,
    PrivatInsurance,
    PrivatLoan,
    PrivatVehicle,
)
from app.db.schemas import (
    PrivatDeadlineCreate,
    PrivatDeadlineUpdate,
    PrivatDeadlineResponse,
    PrivatDeadlineWithStatus,
    PrivatDeadlineListResponse,
    PrivatDeadlineWidget,
    PrivatDeadlineType,
)

logger = structlog.get_logger(__name__)


class PrivatDeadlineService:
    """Service fuer Fristen und Erinnerungen."""

    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        data: PrivatDeadlineCreate,
    ) -> PrivatDeadline:
        """Erstellt eine neue Frist.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            data: Frist-Daten

        Returns:
            Erstellte Frist
        """
        deadline = PrivatDeadline(
            id=uuid.uuid4(),
            space_id=space_id,
            title=data.title,
            description=data.description,
            deadline_type=data.deadline_type.value if isinstance(data.deadline_type, PrivatDeadlineType) else data.deadline_type,
            due_date=data.due_date,
            reminder_days=data.reminder_days,
            is_recurring=data.is_recurring,
            recurrence_interval=data.recurrence_interval,
            priority=data.priority,
            related_entity_type=data.related_entity_type,
            related_entity_id=data.related_entity_id,
            is_completed=False,
            completed_at=None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(deadline)
        await db.commit()
        await db.refresh(deadline)

        logger.info(
            "privat_deadline_created",
            deadline_id=str(deadline.id),
            space_id=str(space_id),
            due_date=str(data.due_date),
        )

        return deadline

    async def get_by_id(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
    ) -> Optional[PrivatDeadline]:
        """Holt eine Frist nach ID.

        WARNUNG: Diese Methode fuehrt KEINEN Access-Check durch!
        Fuer API-Aufrufe IMMER get_by_id_with_access_check() verwenden!
        """
        result = await db.execute(
            select(PrivatDeadline).where(PrivatDeadline.id == deadline_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_access_check(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
    ) -> Optional[PrivatDeadline]:
        """Holt eine Frist nach ID MIT Access-Check.

        SECURITY: Diese Methode ist IDOR-sicher:
        - Access-Check erfolgt VOR Rueckgabe der Frist
        - Gibt None zurueck wenn nicht existiert ODER kein Zugriff
        - Keine Information Disclosure ueber Existenz fremder Ressourcen
        """
        from app.db.models import PrivatSpace, PrivatSpaceAccess

        # SECURITY: Hole Frist MIT Space in EINER Query
        result = await db.execute(
            select(PrivatDeadline, PrivatSpace)
            .join(PrivatSpace, PrivatDeadline.space_id == PrivatSpace.id)
            .where(PrivatDeadline.id == deadline_id)
        )
        row = result.first()

        if not row:
            return None

        deadline, space = row

        # Owner hat immer vollen Zugriff
        if space.owner_id == requesting_user_id:
            return deadline

        # Pruefe explizite Berechtigung - SECURITY: mit expires_at Validierung!
        now = datetime.now(tz.utc)
        access_result = await db.execute(
            select(PrivatSpaceAccess)
            .where(
                PrivatSpaceAccess.space_id == space.id,
                PrivatSpaceAccess.user_id == requesting_user_id,
                # SECURITY: expires_at check - abgelaufene Zugriffe ignorieren
                or_(
                    PrivatSpaceAccess.expires_at == None,
                    PrivatSpaceAccess.expires_at > now
                ),
            )
        )
        access = access_result.scalar_one_or_none()

        if not access:
            logger.warning(
                "idor_deadline_attempt_blocked",
                deadline_id=str(deadline_id),
                user_id=str(requesting_user_id),
                space_id=str(space.id)
            )
            return None

        return deadline

    async def list_deadlines(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        include_completed: bool = False,
        deadline_type: Optional[PrivatDeadlineType] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PrivatDeadlineListResponse:
        """Listet alle Fristen eines Spaces."""
        conditions = [PrivatDeadline.space_id == space_id]

        if not include_completed:
            conditions.append(PrivatDeadline.is_completed == False)

        if deadline_type:
            conditions.append(
                PrivatDeadline.deadline_type == deadline_type.value
            )

        # Count
        count_result = await db.execute(
            select(func.count(PrivatDeadline.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatDeadline)
            .where(and_(*conditions))
            .order_by(PrivatDeadline.due_date)
            .offset(offset)
            .limit(page_size)
        )
        deadlines = result.scalars().all()

        # Mit Status anreichern
        items = [await self._to_deadline_with_status(db, d) for d in deadlines]

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return PrivatDeadlineListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def _to_deadline_with_status(
        self,
        db: AsyncSession,
        deadline: PrivatDeadline,
    ) -> PrivatDeadlineWithStatus:
        """Konvertiert Deadline zu Response mit Status."""
        today = date.today()

        days_remaining = (deadline.due_date - today).days
        is_overdue = days_remaining < 0 and not deadline.is_completed

        # Naechste Erinnerung berechnen
        next_reminder = None
        if deadline.reminder_days and not deadline.is_completed:
            for days in sorted(deadline.reminder_days, reverse=True):
                reminder_date = deadline.due_date - timedelta(days=days)
                if reminder_date >= today:
                    next_reminder = reminder_date
                    break

        # Verknuepften Entity-Namen holen
        related_name = None
        if deadline.related_entity_type and deadline.related_entity_id:
            related_name = await self._get_related_entity_name(
                db, deadline.related_entity_type, deadline.related_entity_id
            )

        return PrivatDeadlineWithStatus(
            id=deadline.id,
            space_id=deadline.space_id,
            title=deadline.title,
            description=deadline.description,
            deadline_type=PrivatDeadlineType(deadline.deadline_type),
            due_date=deadline.due_date,
            reminder_days=deadline.reminder_days or [],
            is_recurring=deadline.is_recurring,
            recurrence_interval=deadline.recurrence_interval,
            priority=deadline.priority,
            related_entity_type=deadline.related_entity_type,
            related_entity_id=deadline.related_entity_id,
            is_completed=deadline.is_completed,
            completed_at=deadline.completed_at,
            created_at=deadline.created_at,
            updated_at=deadline.updated_at,
            days_remaining=days_remaining,
            is_overdue=is_overdue,
            next_reminder=next_reminder,
            related_entity_name=related_name,
        )

    async def _get_related_entity_name(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Optional[str]:
        """Holt den Namen der verknuepften Entity."""
        if entity_type == "insurance":
            result = await db.execute(
                select(PrivatInsurance.name)
                .where(PrivatInsurance.id == entity_id)
            )
            row = result.one_or_none()
            return row[0] if row else None

        elif entity_type == "loan":
            result = await db.execute(
                select(PrivatLoan.name)
                .where(PrivatLoan.id == entity_id)
            )
            row = result.one_or_none()
            return row[0] if row else None

        elif entity_type == "vehicle":
            result = await db.execute(
                select(PrivatVehicle.name)
                .where(PrivatVehicle.id == entity_id)
            )
            row = result.one_or_none()
            return row[0] if row else None

        return None

    async def get_dashboard_widget(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> PrivatDeadlineWidget:
        """Holt Fristen fuer das Dashboard-Widget."""
        today = date.today()
        week_end = today + timedelta(days=7)
        month_end = today + timedelta(days=30)

        # Alle offenen Fristen laden
        result = await db.execute(
            select(PrivatDeadline)
            .where(
                PrivatDeadline.space_id == space_id,
                PrivatDeadline.is_completed == False,
            )
            .order_by(PrivatDeadline.due_date)
        )
        deadlines = result.scalars().all()

        today_list = []
        this_week = []
        this_month = []
        overdue = []

        for d in deadlines:
            status = await self._to_deadline_with_status(db, d)

            if d.due_date < today:
                overdue.append(status)
            elif d.due_date == today:
                today_list.append(status)
            elif d.due_date <= week_end:
                this_week.append(status)
            elif d.due_date <= month_end:
                this_month.append(status)

        return PrivatDeadlineWidget(
            today=today_list,
            this_week=this_week,
            this_month=this_month,
            overdue=overdue,
        )

    async def update(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
        data: PrivatDeadlineUpdate,
    ) -> Optional[PrivatDeadline]:
        """Aktualisiert eine Frist.

        SECURITY FIX 23-7: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelen Updates zu verhindern. Ohne Row Lock koennte:
        - Lost Updates bei gleichzeitigen Aenderungen auftreten
        - Inkonsistente Frist-Daten entstehen
        """
        # SECURITY FIX 23-7: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatDeadline)
            .where(PrivatDeadline.id == deadline_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Frist-Daten!
        )
        deadline = result.scalar_one_or_none()
        if not deadline:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "deadline_type" and value:
                value = value.value if isinstance(value, PrivatDeadlineType) else value
            setattr(deadline, key, value)

        deadline.updated_at = utc_now()

        await db.commit()
        await db.refresh(deadline)

        return deadline

    async def complete(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
    ) -> Optional[PrivatDeadline]:
        """Markiert eine Frist als erledigt.

        SECURITY FIX 23-8: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Complete zu verhindern. Besonders KRITISCH bei recurring deadlines!
        Ohne Row Lock koennte:
        - Double-Complete auftreten
        - Doppelte Folge-Fristen erstellt werden
        """
        # SECURITY FIX 23-8: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatDeadline)
            .where(PrivatDeadline.id == deadline_id)
            .with_for_update()  # ROW LOCK - KRITISCH fuer recurring deadlines!
        )
        deadline = result.scalar_one_or_none()
        if not deadline:
            return None

        deadline.is_completed = True
        deadline.completed_at = utc_now()
        deadline.updated_at = utc_now()

        # Bei wiederkehrender Frist: Neue erstellen
        if deadline.is_recurring and deadline.recurrence_interval:
            await self._create_next_occurrence(db, deadline)

        await db.commit()
        await db.refresh(deadline)

        logger.info(
            "privat_deadline_completed",
            deadline_id=str(deadline_id),
        )

        return deadline

    async def _create_next_occurrence(
        self,
        db: AsyncSession,
        deadline: PrivatDeadline,
    ) -> PrivatDeadline:
        """Erstellt die naechste Wiederholung einer Frist."""
        interval_days = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
            "quarterly": 90,
            "semi_annual": 180,
            "annual": 365,
        }.get(deadline.recurrence_interval, 30)

        next_due = deadline.due_date + timedelta(days=interval_days)

        new_deadline = PrivatDeadline(
            id=uuid.uuid4(),
            space_id=deadline.space_id,
            title=deadline.title,
            description=deadline.description,
            deadline_type=deadline.deadline_type,
            due_date=next_due,
            reminder_days=deadline.reminder_days,
            is_recurring=True,
            recurrence_interval=deadline.recurrence_interval,
            priority=deadline.priority,
            related_entity_type=deadline.related_entity_type,
            related_entity_id=deadline.related_entity_id,
            is_completed=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(new_deadline)
        return new_deadline

    async def delete(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
    ) -> bool:
        """Loescht eine Frist.

        SECURITY FIX 23-9: Row Lock mit with_for_update() um TOCTOU Race Conditions
        bei parallelem Delete zu verhindern. Ohne Row Lock koennte:
        - Double-Delete auftreten
        - Inkonsistente Zustaende entstehen
        """
        # SECURITY FIX 23-9: Row Lock verhindert parallele Modifikationen
        result = await db.execute(
            select(PrivatDeadline)
            .where(PrivatDeadline.id == deadline_id)
            .with_for_update()  # ROW LOCK - kritisch fuer Datenintegritaet!
        )
        deadline = result.scalar_one_or_none()
        if not deadline:
            return False

        await db.delete(deadline)
        await db.commit()

        return True

    async def get_due_reminders(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> List[PrivatDeadline]:
        """Holt Fristen fuer die heute Erinnerungen faellig sind."""
        today = date.today()

        result = await db.execute(
            select(PrivatDeadline)
            .where(
                PrivatDeadline.space_id == space_id,
                PrivatDeadline.is_completed == False,
            )
        )

        deadlines = result.scalars().all()
        due_reminders = []

        for d in deadlines:
            if d.reminder_days:
                for days in d.reminder_days:
                    reminder_date = d.due_date - timedelta(days=days)
                    if reminder_date == today:
                        due_reminders.append(d)
                        break

        return due_reminders

    async def record_notification(
        self,
        db: AsyncSession,
        deadline_id: uuid.UUID,
        notification_type: str,
        sent_to: str,
    ) -> PrivatDeadlineNotification:
        """Erfasst eine gesendete Benachrichtigung."""
        notification = PrivatDeadlineNotification(
            id=uuid.uuid4(),
            deadline_id=deadline_id,
            notification_type=notification_type,
            sent_at=utc_now(),
            sent_to=sent_to,
        )

        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        return notification

    def generate_ical(
        self,
        deadlines: List[PrivatDeadline],
        calendar_name: str = "Privat-Fristen",
    ) -> bytes:
        """Generiert eine iCal-Datei fuer Fristen.

        Args:
            deadlines: Liste von Fristen
            calendar_name: Name des Kalenders

        Returns:
            iCal-Datei als Bytes
        """
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Ablage-System//Privat-Modul//DE",
            f"X-WR-CALNAME:{calendar_name}",
            "METHOD:PUBLISH",
        ]

        for d in deadlines:
            uid = str(d.id).replace("-", "")
            dtstart = d.due_date.strftime("%Y%m%d")
            dtstamp = utc_now().strftime("%Y%m%dT%H%M%SZ")

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}@ablage-system.privat",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"SUMMARY:{d.title}",
            ])

            if d.description:
                # Escape Zeilenumbrueche
                desc = d.description.replace("\n", "\\n")
                lines.append(f"DESCRIPTION:{desc}")

            # Erinnerungen als VALARM
            if d.reminder_days:
                for days in d.reminder_days:
                    lines.extend([
                        "BEGIN:VALARM",
                        "ACTION:DISPLAY",
                        f"DESCRIPTION:Erinnerung: {d.title}",
                        f"TRIGGER:-P{days}D",
                        "END:VALARM",
                    ])

            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")

        return "\r\n".join(lines).encode("utf-8")

    async def export_calendar(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        include_completed: bool = False,
    ) -> bytes:
        """Exportiert alle Fristen als iCal.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            include_completed: Erledigte einschliessen?

        Returns:
            iCal-Datei als Bytes
        """
        conditions = [PrivatDeadline.space_id == space_id]
        if not include_completed:
            conditions.append(PrivatDeadline.is_completed == False)

        result = await db.execute(
            select(PrivatDeadline)
            .where(and_(*conditions))
            .order_by(PrivatDeadline.due_date)
        )

        deadlines = list(result.scalars().all())
        return self.generate_ical(deadlines)
