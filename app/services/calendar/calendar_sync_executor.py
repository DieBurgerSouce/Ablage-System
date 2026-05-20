# -*- coding: utf-8 -*-
"""
Kalender-Sync-Executor: Orchestriert die Synchronisierung zwischen
Ablage-Deadlines und externen Kalendern.

Berechnet Diff (erstellen/aktualisieren/löschen) und wendet
Änderungen über den entsprechenden Provider-Client an.

Feinpoliert und durchdacht - Zuverlaessige Kalender-Synchronisation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_log
from app.services.calendar.calendar_types import CalendarEvent, CalendarInfo

logger = structlog.get_logger(__name__)


# =============================================================================
# Datenstrukturen
# =============================================================================


@dataclass
class SyncDiff:
    """Berechneter Diff zwischen aktuellem und letztem Sync-State."""

    to_create: List[CalendarEvent] = field(default_factory=list)
    to_update: List[CalendarEvent] = field(default_factory=list)
    to_delete: List[str] = field(default_factory=list)  # external event IDs


@dataclass
class SyncResult:
    """Ergebnis einer Synchronisierung."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = field(default_factory=list)
    synced_at: Optional[str] = None


if TYPE_CHECKING:
    from app.services.calendar.caldav_client import CaldavClient
    from app.services.calendar.google_calendar_client import GoogleCalendarClient
    from app.services.calendar.microsoft_calendar_client import MicrosoftCalendarClient

# Type alias für Provider-Clients
ProviderClient = Union[
    "GoogleCalendarClient",
    "MicrosoftCalendarClient",
    "CaldavClient",
]


# =============================================================================
# Executor
# =============================================================================


class CalendarSyncExecutor:
    """Führt die Kalender-Synchronisierung durch.

    Orchestriert den kompletten Sync-Zyklus:
    1. Aktuelle Deadlines aus CalendarService laden
    2. Letzten Sync-State aus CompanySettings laden
    3. Diff berechnen (create/update/delete)
    4. Diff über Provider-Client anwenden
    5. Neuen Sync-State speichern
    """

    async def sync(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
        calendar_id: str,
        categories: Optional[List[str]] = None,
        days_ahead: int = 30,
    ) -> SyncResult:
        """
        Hauptmethode: Holt Deadlines, berechnet Diff, wendet Änderungen an.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name (google_calendar, outlook, caldav)
            calendar_id: Ziel-Kalender-ID
            categories: Zu synchronisierende Frist-Kategorien (None = alle)
            days_ahead: Zeitraum in Tagen für Deadlines

        Returns:
            SyncResult mit Zählerstaenden und ggf. Fehlern
        """
        result = SyncResult()

        try:
            # 1. Aktuelle Deadlines laden und zu CalendarEvents konvertieren
            current_events = await self._load_current_events(
                db, company_id, categories, days_ahead
            )

            # 2. Letzten Sync-State laden
            sync_state = await self._load_sync_state(db, company_id)

            # 3. Diff berechnen
            diff = self._compute_diff(current_events, sync_state)

            logger.info(
                "calendar_sync_diff_computed",
                company_id=str(company_id),
                provider=provider,
                to_create=len(diff.to_create),
                to_update=len(diff.to_update),
                to_delete=len(diff.to_delete),
            )

            # 4. Provider-Client erstellen
            client = await self._get_provider_client(db, company_id, provider)
            if client is None:
                result.errors.append(
                    "Provider-Client konnte nicht erstellt werden. "
                    "Bitte Zugangsdaten prüfen."
                )
                return result

            # 5. Diff anwenden
            result = await self._apply_diff(
                diff, client, calendar_id, sync_state
            )

            # 6. Neuen Sync-State speichern
            await self._save_sync_state(db, company_id, sync_state)

            result.synced_at = utc_now().isoformat()

            logger.info(
                "calendar_sync_completed",
                company_id=str(company_id),
                provider=provider,
                created=result.created,
                updated=result.updated,
                deleted=result.deleted,
                errors=len(result.errors),
            )

        except Exception as e:
            logger.error(
                "calendar_sync_failed",
                company_id=str(company_id),
                provider=provider,
                **safe_error_log(e),
            )
            result.errors.append(f"Synchronisierung fehlgeschlagen: {type(e).__name__}")

        return result

    # =========================================================================
    # Deadlines laden und konvertieren
    # =========================================================================

    async def _load_current_events(
        self,
        db: AsyncSession,
        company_id: UUID,
        categories: Optional[List[str]],
        days_ahead: int,
    ) -> List[CalendarEvent]:
        """Laedt aktuelle Deadlines und konvertiert sie zu CalendarEvents."""
        from app.services.calendar_service import get_calendar_service

        cal_service = get_calendar_service()
        deadlines = await cal_service.get_all_deadlines(
            db=db,
            company_id=company_id,
            days_ahead=days_ahead,
            limit=500,
        )

        # Nach Kategorien filtern
        if categories:
            deadlines = [
                d for d in deadlines
                if d.category.value in categories
            ]

        # Zu CalendarEvents konvertieren
        events: List[CalendarEvent] = []
        for deadline in deadlines:
            uid = f"ablage-{deadline.id}@ablage-system.local"
            event = CalendarEvent(
                uid=uid,
                title=deadline.title,
                description=deadline.description,
                start=deadline.deadline,
                end=deadline.deadline + timedelta(hours=1),
            )
            events.append(event)

        return events

    # =========================================================================
    # Diff-Berechnung
    # =========================================================================

    def _compute_diff(
        self,
        current_events: List[CalendarEvent],
        sync_state: Dict[str, str],
    ) -> SyncDiff:
        """
        Berechnet was erstellt/aktualisiert/gelöscht werden muss.

        Args:
            current_events: Aktuelle Deadlines als CalendarEvents
            sync_state: Mapping {ablage_uid: external_event_id}

        Returns:
            SyncDiff mit create/update/delete Listen

        Logik:
        - Neues Event (uid nicht in sync_state) -> create
        - Existierendes Event (uid in sync_state) -> update
        - Entferntes Event (uid in sync_state aber nicht in current) -> delete
        """
        diff = SyncDiff()
        current_uids = set()

        for event in current_events:
            current_uids.add(event.uid)

            if event.uid in sync_state:
                # Event existiert bereits -> update
                diff.to_update.append(event)
            else:
                # Neues Event -> create
                diff.to_create.append(event)

        # Events die im Sync-State sind aber nicht mehr in current -> delete
        for uid, external_id in sync_state.items():
            if uid not in current_uids:
                diff.to_delete.append(external_id)

        return diff

    # =========================================================================
    # Diff anwenden
    # =========================================================================

    async def _apply_diff(
        self,
        diff: SyncDiff,
        client: ProviderClient,
        calendar_id: str,
        sync_state: Dict[str, str],
    ) -> SyncResult:
        """Wendet Diff über den Provider-Client an.

        Args:
            diff: Berechneter Diff
            client: Provider-Client (Google/Outlook/CalDAV)
            calendar_id: Ziel-Kalender-ID
            sync_state: Wird in-place aktualisiert mit neuen Mappings

        Returns:
            SyncResult mit Zählerstaenden
        """
        result = SyncResult()

        # Erstellen
        for event in diff.to_create:
            try:
                external_id = await client.create_event(calendar_id, event)
                sync_state[event.uid] = external_id
                result.created += 1
            except Exception as e:
                logger.warning(
                    "calendar_sync_create_failed",
                    event_uid=event.uid,
                    **safe_error_log(e),
                )
                result.errors.append(
                    f"Erstellen fehlgeschlagen: {event.title}"
                )

        # Aktualisieren
        for event in diff.to_update:
            external_id = sync_state.get(event.uid, "")
            if not external_id:
                continue
            try:
                await client.update_event(calendar_id, external_id, event)
                result.updated += 1
            except Exception as e:
                logger.warning(
                    "calendar_sync_update_failed",
                    event_uid=event.uid,
                    external_id=external_id,
                    **safe_error_log(e),
                )
                result.errors.append(
                    f"Aktualisierung fehlgeschlagen: {event.title}"
                )

        # Löschen
        for external_id in diff.to_delete:
            try:
                await client.delete_event(calendar_id, external_id)
                result.deleted += 1
                # Aus sync_state entfernen
                keys_to_remove = [
                    k for k, v in sync_state.items()
                    if v == external_id
                ]
                for key in keys_to_remove:
                    del sync_state[key]
            except Exception as e:
                logger.warning(
                    "calendar_sync_delete_failed",
                    external_id=external_id,
                    **safe_error_log(e),
                )
                result.errors.append(
                    f"Löschen fehlgeschlagen: Event {external_id}"
                )

        return result

    # =========================================================================
    # Provider-Client erstellen
    # =========================================================================

    async def _get_provider_client(
        self,
        db: AsyncSession,
        company_id: UUID,
        provider: str,
    ) -> Optional[ProviderClient]:
        """Erstellt den passenden Provider-Client.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            provider: Provider-Name

        Returns:
            Provider-Client oder None bei Fehler
        """
        if provider in ("google_calendar", "google"):
            return await self._create_google_client(db, company_id)
        elif provider in ("outlook", "microsoft"):
            return await self._create_outlook_client(db, company_id)
        elif provider == "caldav":
            return await self._create_caldav_client(db, company_id)
        else:
            logger.error(
                "calendar_sync_unknown_provider",
                provider=provider,
                company_id=str(company_id),
            )
            return None

    async def _create_google_client(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Optional["GoogleCalendarClient"]:
        """Erstellt Google Calendar Client mit gültigem Token."""
        from app.services.calendar.oauth_service import get_calendar_oauth_service
        from app.services.calendar.google_calendar_client import GoogleCalendarClient
        from app.core.config import settings

        oauth = get_calendar_oauth_service()
        token = await oauth.get_valid_token(
            db=db,
            company_id=company_id,
            provider="google",
            client_id=getattr(settings, "GOOGLE_CALENDAR_CLIENT_ID", ""),
            client_secret=getattr(settings, "GOOGLE_CALENDAR_CLIENT_SECRET", ""),
        )

        if not token:
            logger.warning(
                "calendar_sync_no_google_token",
                company_id=str(company_id),
            )
            return None

        return GoogleCalendarClient(access_token=token)

    async def _create_outlook_client(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Optional["MicrosoftCalendarClient"]:
        """Erstellt Microsoft Calendar Client mit gültigem Token."""
        from app.services.calendar.oauth_service import get_calendar_oauth_service
        from app.services.calendar.microsoft_calendar_client import MicrosoftCalendarClient
        from app.core.config import settings

        oauth = get_calendar_oauth_service()
        token = await oauth.get_valid_token(
            db=db,
            company_id=company_id,
            provider="outlook",
            client_id=getattr(settings, "OUTLOOK_CALENDAR_CLIENT_ID", ""),
            client_secret=getattr(settings, "OUTLOOK_CALENDAR_CLIENT_SECRET", ""),
        )

        if not token:
            logger.warning(
                "calendar_sync_no_outlook_token",
                company_id=str(company_id),
            )
            return None

        return MicrosoftCalendarClient(access_token=token)

    async def _create_caldav_client(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Optional["CaldavClient"]:
        """Erstellt CalDAV Client mit Konfiguration aus DB."""
        from app.services.calendar.caldav_client import CaldavClient
        from app.services.calendar.calendar_sync_service import CalendarSyncService

        sync_service = CalendarSyncService(db)
        config = await sync_service.get_sync_config(company_id)

        if not config or not config.calendar_url or not config.username:
            logger.warning(
                "calendar_sync_no_caldav_config",
                company_id=str(company_id),
            )
            return None

        # Passwort aus verschlüsseltem Speicher laden
        from app.core.encryption import decrypt_data
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).where(
            CompanySettings.id == company_id
        )
        result = await db.execute(stmt)
        settings_row = result.scalar_one_or_none()

        password = ""
        if settings_row:
            cal_sync_data = getattr(settings_row, "calendar_sync", None)
            if isinstance(cal_sync_data, dict):
                encrypted_pw = cal_sync_data.get("encrypted_password", "")
                if encrypted_pw:
                    try:
                        password = decrypt_data(
                            encrypted_pw,
                            associated_data=f"caldav_password:{company_id}",
                        )
                    except Exception as e:
                        logger.error(
                            "calendar_sync_caldav_password_decrypt_failed",
                            **safe_error_log(e),
                        )
                        return None

        return CaldavClient(
            url=config.calendar_url,
            username=config.username,
            password=password,
        )

    # =========================================================================
    # Sync-State Verwaltung
    # =========================================================================

    async def _load_sync_state(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, str]:
        """Laedt den Sync-State aus CompanySettings.calendar_sync_state.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID

        Returns:
            Mapping {ablage_uid: external_event_id}
        """
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).where(
            CompanySettings.id == company_id
        )
        result = await db.execute(stmt)
        settings_row = result.scalar_one_or_none()

        if not settings_row:
            return {}

        state = getattr(settings_row, "calendar_sync_state", None)
        if isinstance(state, dict):
            return dict(state)
        return {}

    async def _save_sync_state(
        self,
        db: AsyncSession,
        company_id: UUID,
        state: Dict[str, str],
    ) -> None:
        """Speichert den aktualisierten Sync-State in CompanySettings.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            state: Aktualisiertes Mapping {ablage_uid: external_event_id}
        """
        from app.db.models import CompanySettings

        stmt = select(CompanySettings).where(
            CompanySettings.id == company_id
        )
        result = await db.execute(stmt)
        settings_row = result.scalar_one_or_none()

        if settings_row:
            settings_row.calendar_sync_state = state
            await db.commit()

            logger.debug(
                "calendar_sync_state_saved",
                company_id=str(company_id),
                entries=len(state),
            )
