"""Calendar Sync Service - iCalendar Export, CalDAV Synchronisation und Provider-Sync."""

import structlog
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Tuple
from uuid import UUID
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

class CalendarProvider(str, Enum):
    ICAL_FILE = "ical_file"       # .ics file export
    CALDAV = "caldav"             # CalDAV server sync
    GOOGLE = "google_calendar"    # Google Calendar API
    OUTLOOK = "outlook"           # Microsoft Graph API

@dataclass
class CalendarEvent:
    """Kalender-Ereignis für Export."""
    uid: str
    summary: str
    description: str
    dtstart: datetime
    dtend: datetime
    categories: List[str]
    priority: int  # 1=high, 5=normal, 9=low
    url: Optional[str] = None
    location: Optional[str] = None
    alarm_minutes_before: int = 60

@dataclass
class SyncConfig:
    """Konfiguration für Kalender-Synchronisation."""
    provider: CalendarProvider
    calendar_url: Optional[str] = None  # CalDAV URL
    username: Optional[str] = None
    # password stored encrypted in DB, not here
    sync_categories: Optional[List[str]] = None  # Which deadline categories to sync
    sync_interval_minutes: int = 60
    auto_sync_enabled: bool = False

@dataclass
class SyncResult:
    """Ergebnis einer Synchronisation."""
    events_exported: int
    events_updated: int
    events_deleted: int
    errors: List[str]
    last_sync: datetime

class CalendarSyncService:
    """Kalender-Synchronisationsdienst."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_ical(self, company_id: UUID, user_id: UUID,
                            categories: Optional[List[str]] = None,
                            days_ahead: int = 90) -> str:
        """
        Generiert iCalendar (.ics) Datei mit allen Fristen.

        Uses VCALENDAR with VEVENT components per RFC 5545.
        Includes VALARM for reminders.
        """
        # Import calendar_service to get deadlines
        from app.services.calendar_service import get_calendar_service
        cal_service = get_calendar_service()

        deadlines = await cal_service.get_deadlines(
            db=self.db, user_id=user_id, company_id=company_id,
            days_ahead=days_ahead
        )

        # Filter by categories if specified
        if categories:
            deadlines = [d for d in deadlines if d.category.value in categories]

        events = []
        for deadline in deadlines:
            event = CalendarEvent(
                uid=f"ablage-{deadline.id}@ablage-system.local",
                summary=deadline.title,
                description=deadline.description,
                dtstart=deadline.deadline,
                dtend=deadline.deadline + timedelta(hours=1),
                categories=[deadline.category.value],
                priority=self._urgency_to_priority(deadline.urgency.value),
                alarm_minutes_before=self._get_alarm_minutes(deadline.urgency.value),
            )
            events.append(event)

        return self._render_ical(events)

    def _render_ical(self, events: List[CalendarEvent]) -> str:
        """Rendert iCalendar-Datei nach RFC 5545."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Ablage-System//Fristen//DE",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Ablage-System Fristen",
            "X-WR-TIMEZONE:Europe/Berlin",
        ]

        for event in events:
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{event.uid}",
                f"DTSTART:{event.dtstart.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{event.dtend.strftime('%Y%m%dT%H%M%SZ')}",
                f"SUMMARY:{self._ical_escape(event.summary)}",
                f"DESCRIPTION:{self._ical_escape(event.description)}",
                f"CATEGORIES:{','.join(event.categories)}",
                f"PRIORITY:{event.priority}",
            ])
            if event.url:
                lines.append(f"URL:{event.url}")
            if event.alarm_minutes_before > 0:
                lines.extend([
                    "BEGIN:VALARM",
                    "TRIGGER:-PT{}M".format(event.alarm_minutes_before),
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:Frist: {self._ical_escape(event.summary)}",
                    "END:VALARM",
                ])
            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

    @staticmethod
    def _ical_escape(text: str) -> str:
        """Escaped Sonderzeichen für iCalendar."""
        return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    @staticmethod
    def _urgency_to_priority(urgency: str) -> int:
        mapping = {"critical": 1, "warning": 3, "upcoming": 5, "scheduled": 7}
        return mapping.get(urgency, 5)

    @staticmethod
    def _get_alarm_minutes(urgency: str) -> int:
        mapping = {"critical": 30, "warning": 60, "upcoming": 120, "scheduled": 1440}
        return mapping.get(urgency, 60)

    async def get_sync_config(self, company_id: UUID) -> Optional[SyncConfig]:
        """Laedt Sync-Konfiguration aus DB (company_settings JSONB)."""
        from app.db.models import CompanySettings
        stmt = select(CompanySettings).limit(1)
        result = await self.db.execute(stmt)
        settings_row = result.scalar_one_or_none()
        if not settings_row or not settings_row.calendar_sync:
            return None
        data = settings_row.calendar_sync
        return SyncConfig(
            provider=CalendarProvider(data.get("provider", "ical_file")),
            calendar_url=data.get("calendar_url"),
            username=data.get("username"),
            sync_categories=data.get("sync_categories"),
            sync_interval_minutes=data.get("sync_interval_minutes", 60),
            auto_sync_enabled=data.get("auto_sync_enabled", False),
        )

    async def save_sync_config(self, company_id: UUID, config: SyncConfig) -> None:
        """Speichert Sync-Konfiguration."""
        from app.db.models import CompanySettings
        stmt = select(CompanySettings).limit(1)
        result = await self.db.execute(stmt)
        settings_row = result.scalar_one_or_none()
        if settings_row:
            settings_row.calendar_sync = {
                "provider": config.provider.value,
                "calendar_url": config.calendar_url,
                "username": config.username,
                "sync_categories": config.sync_categories,
                "sync_interval_minutes": config.sync_interval_minutes,
                "auto_sync_enabled": config.auto_sync_enabled,
            }
            await self.db.commit()
        logger.info("calendar_sync_config_saved", company_id=str(company_id))

    # =========================================================================
    # Provider-Sync Methoden
    # =========================================================================

    async def sync_to_provider(
        self, db: AsyncSession, company_id: UUID
    ) -> "SyncExecutorResult":
        """Delegiert Synchronisierung an CalendarSyncExecutor.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            SyncResult vom Executor
        """
        from app.services.calendar.calendar_sync_executor import (
            CalendarSyncExecutor,
            SyncResult as ExecutorSyncResult,
        )

        config = await self.get_sync_config(company_id)
        if not config:
            return ExecutorSyncResult(
                errors=["Keine Kalender-Konfiguration vorhanden."]
            )

        if config.provider == CalendarProvider.ICAL_FILE:
            return ExecutorSyncResult(
                errors=["iCal-Export benötigt keine Synchronisierung."]
            )

        executor = CalendarSyncExecutor()
        cal_id = config.calendar_url or "primary"

        return await executor.sync(
            db=db,
            company_id=company_id,
            provider=config.provider.value,
            calendar_id=cal_id,
            categories=config.sync_categories,
            days_ahead=90,
        )

    async def get_sync_status(
        self, db: AsyncSession, company_id: UUID
    ) -> Dict[str, object]:
        """Liest den Sync-Status aus CompanySettings.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Dict mit Sync-Status-Informationen
        """
        from app.db.models import CompanySettings

        config = await self.get_sync_config(company_id)

        # Sync-State laden für Event-Zähler
        stmt = select(CompanySettings).where(CompanySettings.id == company_id)
        result = await db.execute(stmt)
        settings_row = result.scalar_one_or_none()

        sync_state = {}
        if settings_row:
            state = getattr(settings_row, "calendar_sync_state", None)
            if isinstance(state, dict):
                sync_state = state

        return {
            "last_synced_at": None,  # Wird aus Sync-State abgeleitet
            "events_synced": len(sync_state),
            "provider": config.provider.value if config else None,
            "auto_sync_enabled": config.auto_sync_enabled if config else False,
        }

    async def test_provider_connection(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        calendar_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Testet die Verbindung zu einem Kalender-Provider.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name
            calendar_url: CalDAV-URL (nur für CalDAV)
            username: Benutzername (nur für CalDAV)
            password: Passwort (nur für CalDAV)

        Returns:
            Tuple aus (Erfolg, Statusmeldung auf Deutsch)
        """
        try:
            if provider == "caldav":
                if not calendar_url or not username or not password:
                    return False, "CalDAV benötigt URL, Benutzername und Passwort."

                from app.services.calendar.caldav_client import CaldavClient

                client = CaldavClient(
                    url=calendar_url,
                    username=username,
                    password=password,
                )
                return await client.test_connection()

            elif provider in ("google_calendar", "google"):
                from app.services.calendar.oauth_service import get_calendar_oauth_service
                from app.core.config import settings as app_settings

                oauth = get_calendar_oauth_service()
                token = await oauth.get_valid_token(
                    db=db,
                    company_id=company_id,
                    provider="google",
                    client_id=getattr(app_settings, "GOOGLE_CALENDAR_CLIENT_ID", ""),
                    client_secret=getattr(app_settings, "GOOGLE_CALENDAR_CLIENT_SECRET", ""),
                )

                if not token:
                    return False, "Keine gültige Google-OAuth-Verbindung. Bitte zuerst autorisieren."

                from app.services.calendar.google_calendar_client import GoogleCalendarClient

                async with GoogleCalendarClient(access_token=token) as client:
                    calendars = await client.list_calendars()
                    return True, f"Verbindung erfolgreich. {len(calendars)} Kalender gefunden."

            elif provider in ("outlook", "microsoft"):
                from app.services.calendar.oauth_service import get_calendar_oauth_service
                from app.core.config import settings as app_settings

                oauth = get_calendar_oauth_service()
                token = await oauth.get_valid_token(
                    db=db,
                    company_id=company_id,
                    provider="outlook",
                    client_id=getattr(app_settings, "OUTLOOK_CALENDAR_CLIENT_ID", ""),
                    client_secret=getattr(app_settings, "OUTLOOK_CALENDAR_CLIENT_SECRET", ""),
                )

                if not token:
                    return False, "Keine gültige Outlook-OAuth-Verbindung. Bitte zuerst autorisieren."

                from app.services.calendar.microsoft_calendar_client import MicrosoftCalendarClient

                async with MicrosoftCalendarClient(access_token=token) as client:
                    calendars = await client.list_calendars()
                    return True, f"Verbindung erfolgreich. {len(calendars)} Kalender gefunden."

            else:
                return False, f"Unbekannter Provider: {provider}"

        except Exception as e:
            logger.error(
                "calendar_test_connection_failed",
                provider=provider,
                **safe_error_log(e),
            )
            return False, "Verbindungstest fehlgeschlagen. Bitte Konfiguration prüfen."
