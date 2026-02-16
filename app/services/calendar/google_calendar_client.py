# -*- coding: utf-8 -*-
"""
Google Calendar API v3 Client.

Verwendet httpx.AsyncClient für asynchrone API-Aufrufe.
Implementiert Erstellung, Aktualisierung und Löschung von
Kalender-Ereignissen über die Google Calendar REST API.

Feinpoliert und durchdacht - Google Calendar Integration.
"""

from datetime import datetime, timezone
from typing import List, Optional

import httpx
import structlog

from app.core.safe_errors import safe_error_log
from app.services.calendar.calendar_types import CalendarEvent, CalendarInfo

logger = structlog.get_logger(__name__)

BASE_URL = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarClient:
    """
    Asynchroner Client für die Google Calendar API v3.

    Verwendet Context-Manager-Pattern für sicheres Ressourcen-Management.

    Usage:
        async with GoogleCalendarClient(access_token="...") as client:
            calendars = await client.list_calendars()
            event_id = await client.create_event("primary", event)
    """

    def __init__(self, access_token: str) -> None:
        """
        Initialisiert den Google Calendar Client.

        Args:
            access_token: OAuth2 Access Token für Google Calendar API
        """
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Schließt den HTTP-Client."""
        await self._client.aclose()

    async def __aenter__(self) -> "GoogleCalendarClient":
        """Context-Manager Entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Context-Manager Exit - schließt HTTP-Client."""
        await self.close()

    # =========================================================================
    # Kalender-Liste
    # =========================================================================

    async def list_calendars(self) -> List[CalendarInfo]:
        """
        Listet alle verfügbaren Kalender des Benutzers auf.

        Returns:
            Liste von CalendarInfo-Objekten

        Raises:
            httpx.HTTPStatusError: Bei API-Fehler
        """
        try:
            response = await self._client.get("/users/me/calendarList")

            if response.status_code == 429:
                logger.warning("google_calendar_rate_limited", endpoint="calendarList")
                return []

            response.raise_for_status()
            data = response.json()

            calendars: List[CalendarInfo] = []
            for item in data.get("items", []):
                calendars.append(CalendarInfo(
                    id=item.get("id", ""),
                    name=item.get("summary", ""),
                    description=item.get("description", ""),
                    primary=item.get("primary", False),
                    color=item.get("backgroundColor"),
                ))
            return calendars

        except httpx.HTTPStatusError as e:
            logger.error(
                "google_calendar_list_failed",
                status=e.response.status_code,
                **safe_error_log(e),
            )
            raise
        except Exception as e:
            logger.error("google_calendar_list_error", **safe_error_log(e))
            raise

    # =========================================================================
    # Event CRUD
    # =========================================================================

    async def create_event(
        self,
        calendar_id: str,
        event: CalendarEvent,
    ) -> str:
        """
        Erstellt ein neues Ereignis im Google Calendar.

        Args:
            calendar_id: Kalender-ID (z.B. "primary")
            event: CalendarEvent mit Ereignisdaten

        Returns:
            Google Event-ID des erstellten Ereignisses

        Raises:
            httpx.HTTPStatusError: Bei API-Fehler
        """
        body = self._event_to_google_json(event)

        try:
            response = await self._client.post(
                f"/calendars/{calendar_id}/events",
                json=body,
            )

            if response.status_code == 429:
                logger.warning("google_calendar_rate_limited", endpoint="createEvent")
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            result = response.json()
            external_id = result.get("id", "")

            logger.info(
                "google_event_created",
                calendar_id=calendar_id,
                event_uid=event.uid,
                external_id=external_id,
            )
            return external_id

        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            logger.error(
                "google_event_create_error",
                calendar_id=calendar_id,
                **safe_error_log(e),
            )
            raise

    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        event: CalendarEvent,
    ) -> bool:
        """
        Aktualisiert ein bestehendes Ereignis.

        Args:
            calendar_id: Kalender-ID
            event_id: Google Event-ID
            event: Aktualisierte CalendarEvent-Daten

        Returns:
            True wenn erfolgreich
        """
        body = self._event_to_google_json(event)

        try:
            response = await self._client.put(
                f"/calendars/{calendar_id}/events/{event_id}",
                json=body,
            )

            if response.status_code == 429:
                logger.warning("google_calendar_rate_limited", endpoint="updateEvent")
                return False

            response.raise_for_status()

            logger.info(
                "google_event_updated",
                calendar_id=calendar_id,
                event_id=event_id,
            )
            return True

        except Exception as e:
            logger.error(
                "google_event_update_error",
                calendar_id=calendar_id,
                event_id=event_id,
                **safe_error_log(e),
            )
            return False

    async def delete_event(
        self,
        calendar_id: str,
        event_id: str,
    ) -> bool:
        """
        Löscht ein Ereignis aus dem Kalender.

        Args:
            calendar_id: Kalender-ID
            event_id: Google Event-ID

        Returns:
            True wenn erfolgreich
        """
        try:
            response = await self._client.delete(
                f"/calendars/{calendar_id}/events/{event_id}",
            )

            if response.status_code == 429:
                logger.warning("google_calendar_rate_limited", endpoint="deleteEvent")
                return False

            if response.status_code in (200, 204):
                logger.info(
                    "google_event_deleted",
                    calendar_id=calendar_id,
                    event_id=event_id,
                )
                return True

            # 404 = bereits gelöscht, auch als Erfolg werten
            if response.status_code == 404:
                logger.info(
                    "google_event_already_deleted",
                    calendar_id=calendar_id,
                    event_id=event_id,
                )
                return True

            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(
                "google_event_delete_error",
                calendar_id=calendar_id,
                event_id=event_id,
                **safe_error_log(e),
            )
            return False

    async def list_events(
        self,
        calendar_id: str,
        time_min: datetime,
        time_max: datetime,
    ) -> List[CalendarEvent]:
        """
        Listet Ereignisse in einem Zeitraum auf.

        Args:
            calendar_id: Kalender-ID
            time_min: Beginn des Zeitraums (timezone-aware)
            time_max: Ende des Zeitraums (timezone-aware)

        Returns:
            Liste von CalendarEvent-Objekten
        """
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }

        try:
            response = await self._client.get(
                f"/calendars/{calendar_id}/events",
                params=params,
            )

            if response.status_code == 429:
                logger.warning("google_calendar_rate_limited", endpoint="listEvents")
                return []

            response.raise_for_status()
            data = response.json()

            events: List[CalendarEvent] = []
            for item in data.get("items", []):
                parsed = self._google_json_to_event(item)
                if parsed:
                    events.append(parsed)

            return events

        except Exception as e:
            logger.error(
                "google_events_list_error",
                calendar_id=calendar_id,
                **safe_error_log(e),
            )
            return []

    # =========================================================================
    # Private: JSON Mapping
    # =========================================================================

    @staticmethod
    def _event_to_google_json(event: CalendarEvent) -> dict:
        """Konvertiert CalendarEvent in Google Calendar JSON-Format."""
        body: dict = {
            "summary": event.title,
            "description": event.description,
        }

        if event.location:
            body["location"] = event.location

        if event.all_day:
            body["start"] = {"date": event.start.strftime("%Y-%m-%d")}
            body["end"] = {"date": event.end.strftime("%Y-%m-%d")}
        else:
            body["start"] = {
                "dateTime": event.start.isoformat(),
                "timeZone": "Europe/Berlin",
            }
            body["end"] = {
                "dateTime": event.end.isoformat(),
                "timeZone": "Europe/Berlin",
            }

        # Ablage-UID als extended property speichern
        body["extendedProperties"] = {
            "private": {
                "ablage_uid": event.uid,
            },
        }

        return body

    @staticmethod
    def _google_json_to_event(item: dict) -> Optional[CalendarEvent]:
        """Konvertiert Google Calendar JSON in CalendarEvent."""
        try:
            event_id = item.get("id", "")
            summary = item.get("summary", "")
            description = item.get("description", "")
            location = item.get("location")

            # Start/End parsen
            start_data = item.get("start", {})
            end_data = item.get("end", {})

            all_day = "date" in start_data and "dateTime" not in start_data

            if all_day:
                start_str = start_data.get("date", "")
                end_str = end_data.get("date", "")
                start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                start_str = start_data.get("dateTime", "")
                end_str = end_data.get("dateTime", "")
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

            # Ablage-UID aus extended properties lesen
            ext_props = item.get("extendedProperties", {})
            private_props = ext_props.get("private", {})
            uid = private_props.get("ablage_uid", f"google-{event_id}")

            return CalendarEvent(
                uid=uid,
                title=summary,
                description=description,
                start=start,
                end=end,
                location=location,
                all_day=all_day,
                external_id=event_id,
            )

        except (ValueError, KeyError) as e:
            logger.warning(
                "google_event_parse_failed",
                event_id=item.get("id", "unknown"),
                **safe_error_log(e),
            )
            return None
