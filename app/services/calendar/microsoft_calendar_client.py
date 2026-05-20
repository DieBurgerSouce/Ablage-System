# -*- coding: utf-8 -*-
"""
Microsoft Graph Calendar API Client.

Verwendet httpx.AsyncClient für Microsoft 365 Kalender-Integration.
Mappt zwischen dem einheitlichen CalendarEvent-Format und dem
Microsoft Graph API Event-Format.

Feinpoliert und durchdacht - Microsoft 365 Calendar Integration.
"""

from datetime import datetime, timezone
from typing import List, Optional

import httpx
import structlog

from app.core.safe_errors import safe_error_log
from app.services.calendar.calendar_types import CalendarEvent, CalendarInfo

logger = structlog.get_logger(__name__)

BASE_URL = "https://graph.microsoft.com/v1.0"


class MicrosoftCalendarClient:
    """
    Asynchroner Client für die Microsoft Graph Calendar API.

    Microsoft verwendet andere Feld-Namen als Google:
    - subject statt summary
    - start/end als Objekt mit dateTime und timeZone
    - bodyPreview / body.content statt description

    Usage:
        async with MicrosoftCalendarClient(access_token="...") as client:
            calendars = await client.list_calendars()
            event_id = await client.create_event("primary", event)
    """

    def __init__(self, access_token: str) -> None:
        """
        Initialisiert den Microsoft Calendar Client.

        Args:
            access_token: OAuth2 Access Token für Microsoft Graph API
        """
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        """Schließt den HTTP-Client."""
        await self._client.aclose()

    async def __aenter__(self) -> "MicrosoftCalendarClient":
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
        """
        try:
            response = await self._client.get("/me/calendars")

            if response.status_code == 429:
                logger.warning("ms_calendar_rate_limited", endpoint="calendars")
                return []

            response.raise_for_status()
            data = response.json()

            calendars: List[CalendarInfo] = []
            for item in data.get("value", []):
                calendars.append(CalendarInfo(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("name", ""),
                    primary=item.get("isDefaultCalendar", False),
                    color=item.get("hexColor"),
                ))
            return calendars

        except httpx.HTTPStatusError as e:
            logger.error(
                "ms_calendar_list_failed",
                status=e.response.status_code,
                **safe_error_log(e),
            )
            raise
        except Exception as e:
            logger.error("ms_calendar_list_error", **safe_error_log(e))
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
        Erstellt ein neues Ereignis im Microsoft Kalender.

        Args:
            calendar_id: Kalender-ID (verwende Kalender-ID aus list_calendars)
            event: CalendarEvent mit Ereignisdaten

        Returns:
            Microsoft Event-ID des erstellten Ereignisses
        """
        body = self._event_to_ms_json(event)

        try:
            response = await self._client.post(
                f"/me/calendars/{calendar_id}/events",
                json=body,
            )

            if response.status_code == 429:
                logger.warning("ms_calendar_rate_limited", endpoint="createEvent")
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            result = response.json()
            external_id = result.get("id", "")

            logger.info(
                "ms_event_created",
                calendar_id=calendar_id,
                event_uid=event.uid,
                external_id=external_id,
            )
            return external_id

        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            logger.error(
                "ms_event_create_error",
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
            event_id: Microsoft Event-ID
            event: Aktualisierte CalendarEvent-Daten

        Returns:
            True wenn erfolgreich
        """
        body = self._event_to_ms_json(event)

        try:
            response = await self._client.patch(
                f"/me/calendars/{calendar_id}/events/{event_id}",
                json=body,
            )

            if response.status_code == 429:
                logger.warning("ms_calendar_rate_limited", endpoint="updateEvent")
                return False

            response.raise_for_status()

            logger.info(
                "ms_event_updated",
                calendar_id=calendar_id,
                event_id=event_id,
            )
            return True

        except Exception as e:
            logger.error(
                "ms_event_update_error",
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
            event_id: Microsoft Event-ID

        Returns:
            True wenn erfolgreich
        """
        try:
            response = await self._client.delete(
                f"/me/calendars/{calendar_id}/events/{event_id}",
            )

            if response.status_code == 429:
                logger.warning("ms_calendar_rate_limited", endpoint="deleteEvent")
                return False

            if response.status_code in (200, 204):
                logger.info(
                    "ms_event_deleted",
                    calendar_id=calendar_id,
                    event_id=event_id,
                )
                return True

            # 404 = bereits gelöscht
            if response.status_code == 404:
                logger.info(
                    "ms_event_already_deleted",
                    calendar_id=calendar_id,
                    event_id=event_id,
                )
                return True

            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(
                "ms_event_delete_error",
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
            "startDateTime": time_min.isoformat(),
            "endDateTime": time_max.isoformat(),
            "$top": "250",
            "$orderby": "start/dateTime",
        }

        try:
            response = await self._client.get(
                f"/me/calendars/{calendar_id}/calendarView",
                params=params,
            )

            if response.status_code == 429:
                logger.warning("ms_calendar_rate_limited", endpoint="listEvents")
                return []

            response.raise_for_status()
            data = response.json()

            events: List[CalendarEvent] = []
            for item in data.get("value", []):
                parsed = self._ms_json_to_event(item)
                if parsed:
                    events.append(parsed)

            return events

        except Exception as e:
            logger.error(
                "ms_events_list_error",
                calendar_id=calendar_id,
                **safe_error_log(e),
            )
            return []

    # =========================================================================
    # Private: JSON Mapping
    # =========================================================================

    @staticmethod
    def _event_to_ms_json(event: CalendarEvent) -> dict:
        """Konvertiert CalendarEvent in Microsoft Graph JSON-Format."""
        body: dict = {
            "subject": event.title,
            "body": {
                "contentType": "text",
                "content": event.description,
            },
        }

        if event.location:
            body["location"] = {
                "displayName": event.location,
            }

        if event.all_day:
            body["isAllDay"] = True
            body["start"] = {
                "dateTime": event.start.strftime("%Y-%m-%dT00:00:00"),
                "timeZone": "Europe/Berlin",
            }
            body["end"] = {
                "dateTime": event.end.strftime("%Y-%m-%dT00:00:00"),
                "timeZone": "Europe/Berlin",
            }
        else:
            body["start"] = {
                "dateTime": event.start.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": "Europe/Berlin",
            }
            body["end"] = {
                "dateTime": event.end.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": "Europe/Berlin",
            }

        # Ablage-UID in singleValueExtendedProperties speichern
        body["singleValueExtendedProperties"] = [
            {
                "id": "String {66f5a359-4659-4830-9070-00047ec6ac6e} Name ablage_uid",
                "value": event.uid,
            }
        ]

        return body

    @staticmethod
    def _ms_json_to_event(item: dict) -> Optional[CalendarEvent]:
        """Konvertiert Microsoft Graph JSON in CalendarEvent."""
        try:
            event_id = item.get("id", "")
            subject = item.get("subject", "")
            body_data = item.get("body", {})
            description = body_data.get("content", "") if isinstance(body_data, dict) else ""

            location_data = item.get("location", {})
            location = location_data.get("displayName") if isinstance(location_data, dict) else None

            all_day = item.get("isAllDay", False)

            # Start/End parsen
            start_data = item.get("start", {})
            end_data = item.get("end", {})

            start_str = start_data.get("dateTime", "") if isinstance(start_data, dict) else ""
            end_str = end_data.get("dateTime", "") if isinstance(end_data, dict) else ""

            # Microsoft gibt dateTime ohne Timezone-Offset zurück
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

            # Ablage-UID aus singleValueExtendedProperties lesen
            uid = f"ms-{event_id}"
            ext_props = item.get("singleValueExtendedProperties", [])
            for prop in ext_props:
                if isinstance(prop, dict) and "ablage_uid" in prop.get("id", ""):
                    uid = prop.get("value", uid)
                    break

            return CalendarEvent(
                uid=uid,
                title=subject,
                description=description,
                start=start,
                end=end,
                location=location,
                all_day=all_day,
                external_id=event_id,
            )

        except (ValueError, KeyError) as e:
            logger.warning(
                "ms_event_parse_failed",
                event_id=item.get("id", "unknown"),
                **safe_error_log(e),
            )
            return None
