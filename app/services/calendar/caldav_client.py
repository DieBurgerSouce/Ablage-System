# -*- coding: utf-8 -*-
"""
CalDAV-Protokoll Client für On-Premises Kalender (Nextcloud, ownCloud).

Verwendet die caldav Python Library für CalDAV-Server-Kommunikation.
Bei fehlender Library wird auf manuell generierte iCalendar-Strings
und httpx-basierte WebDAV-Aufrufe zurückgegriffen.

Feinpoliert und durchdacht - On-Premises Kalender-Integration.
"""

from datetime import datetime
from typing import List, Optional, Tuple

import httpx
import structlog

from app.core.safe_errors import safe_error_log
from app.services.calendar.calendar_types import CalendarEvent, CalendarInfo

logger = structlog.get_logger(__name__)


def _render_vevent(event: CalendarEvent) -> str:
    """
    Generiert einen VCALENDAR/VEVENT-String nach RFC 5545.

    Args:
        event: CalendarEvent mit Ereignisdaten

    Returns:
        Vollständiger VCALENDAR-String
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Ablage-System//CalDAV//DE",
        "BEGIN:VEVENT",
        f"UID:{event.uid}",
        f"SUMMARY:{_ical_escape(event.title)}",
        f"DESCRIPTION:{_ical_escape(event.description)}",
    ]

    if event.all_day:
        lines.append(f"DTSTART;VALUE=DATE:{event.start.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{event.end.strftime('%Y%m%d')}")
    else:
        lines.append(f"DTSTART:{event.start.strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(f"DTEND:{event.end.strftime('%Y%m%dT%H%M%SZ')}")

    if event.location:
        lines.append(f"LOCATION:{_ical_escape(event.location)}")

    lines.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])
    return "\r\n".join(lines)


def _ical_escape(text: str) -> str:
    """Escaped Sonderzeichen für iCalendar nach RFC 5545."""
    return (
        text
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


class CaldavClient:
    """
    CalDAV-Client für On-Premises Kalender-Server.

    Unterstützt Nextcloud, ownCloud, Radicale und andere
    CalDAV-kompatible Server.

    Versucht zuerst die caldav Python Library zu verwenden.
    Falls nicht installiert, werden httpx-basierte WebDAV-Aufrufe
    mit manuell generierten iCalendar-Strings verwendet.

    Usage:
        client = CaldavClient(
            url="https://nextcloud.example.com/remote.php/dav",
            username="benutzer",
            password="passwort",
        )
        success, message = await client.test_connection()
        if success:
            calendars = await client.list_calendars()
    """

    def __init__(self, url: str, username: str, password: str) -> None:
        """
        Initialisiert den CalDAV Client.

        Args:
            url: CalDAV-Server URL (z.B. https://nextcloud.example.com/remote.php/dav)
            username: Benutzername für Basic Auth
            password: Passwort für Basic Auth
        """
        self._url = url.rstrip("/")
        self._username = username
        self._password = password
        self._caldav_available = False

        # Prüfen ob caldav Library verfügbar ist
        try:
            import caldav as _caldav_mod  # noqa: F401
            self._caldav_available = True
        except ImportError:
            logger.info("caldav_library_not_available_using_httpx_fallback")

    # =========================================================================
    # Verbindungstest
    # =========================================================================

    async def test_connection(self) -> Tuple[bool, str]:
        """
        Testet die Verbindung zum CalDAV-Server.

        Returns:
            Tuple aus (Erfolg, Statusmeldung auf Deutsch)
        """
        if self._caldav_available:
            return await self._test_connection_caldav()
        return await self._test_connection_httpx()

    async def _test_connection_caldav(self) -> Tuple[bool, str]:
        """Verbindungstest via caldav Library."""
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            principal = client.principal()
            calendars = principal.calendars()
            return True, f"Verbindung erfolgreich. {len(calendars)} Kalender gefunden."
        except Exception as e:
            logger.error("caldav_connection_test_failed", **safe_error_log(e))
            return False, "Verbindung fehlgeschlagen. Bitte URL und Zugangsdaten prüfen."

    async def _test_connection_httpx(self) -> Tuple[bool, str]:
        """Verbindungstest via httpx PROPFIND."""
        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
            ) as client:
                response = await client.request(
                    "PROPFIND",
                    self._url,
                    headers={
                        "Depth": "0",
                        "Content-Type": "application/xml; charset=utf-8",
                    },
                    content=(
                        '<?xml version="1.0" encoding="utf-8"?>'
                        '<d:propfind xmlns:d="DAV:">'
                        "<d:prop><d:resourcetype/></d:prop>"
                        "</d:propfind>"
                    ),
                )
                if response.status_code in (200, 207):
                    return True, "Verbindung erfolgreich."
                if response.status_code == 401:
                    return False, "Authentifizierung fehlgeschlagen. Zugangsdaten prüfen."
                return False, f"Server-Antwort: HTTP {response.status_code}"

        except Exception as e:
            logger.error("caldav_httpx_connection_failed", **safe_error_log(e))
            return False, "Verbindung fehlgeschlagen. Server nicht erreichbar."

    # =========================================================================
    # Kalender-Liste
    # =========================================================================

    async def list_calendars(self) -> List[CalendarInfo]:
        """
        Listet alle verfügbaren Kalender auf dem Server auf.

        Returns:
            Liste von CalendarInfo-Objekten
        """
        if self._caldav_available:
            return await self._list_calendars_caldav()
        return await self._list_calendars_httpx()

    async def _list_calendars_caldav(self) -> List[CalendarInfo]:
        """Kalender-Liste via caldav Library."""
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            principal = client.principal()
            cal_list = principal.calendars()

            calendars: List[CalendarInfo] = []
            for idx, cal in enumerate(cal_list):
                calendars.append(CalendarInfo(
                    id=str(cal.url),
                    name=getattr(cal, "name", f"Kalender {idx + 1}"),
                    description="",
                    primary=idx == 0,
                ))
            return calendars

        except Exception as e:
            logger.error("caldav_list_calendars_failed", **safe_error_log(e))
            return []

    async def _list_calendars_httpx(self) -> List[CalendarInfo]:
        """Kalender-Liste via httpx PROPFIND."""
        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
            ) as client:
                response = await client.request(
                    "PROPFIND",
                    self._url,
                    headers={
                        "Depth": "1",
                        "Content-Type": "application/xml; charset=utf-8",
                    },
                    content=(
                        '<?xml version="1.0" encoding="utf-8"?>'
                        '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                        "<d:prop><d:displayname/><d:resourcetype/></d:prop>"
                        "</d:propfind>"
                    ),
                )
                if response.status_code not in (200, 207):
                    return []

                # Einfaches XML-Parsing für Kalender-Einträge
                return self._parse_propfind_calendars(response.text)

        except Exception as e:
            logger.error("caldav_httpx_list_failed", **safe_error_log(e))
            return []

    @staticmethod
    def _parse_propfind_calendars(xml_text: str) -> List[CalendarInfo]:
        """Parst PROPFIND-Antwort für Kalender-Einträge (einfaches Parsing)."""
        import xml.etree.ElementTree as ET

        calendars: List[CalendarInfo] = []
        try:
            root = ET.fromstring(xml_text)
            ns = {
                "d": "DAV:",
                "c": "urn:ietf:params:xml:ns:caldav",
            }

            for response_elem in root.findall(".//d:response", ns):
                href = response_elem.findtext("d:href", "", ns)
                propstat = response_elem.find("d:propstat", ns)
                if propstat is None:
                    continue

                prop = propstat.find("d:prop", ns)
                if prop is None:
                    continue

                # Prüfen ob es ein Kalender ist (resourcetype hat calendar)
                resourcetype = prop.find("d:resourcetype", ns)
                if resourcetype is None:
                    continue

                is_calendar = resourcetype.find("c:calendar", ns) is not None
                if not is_calendar:
                    continue

                name = prop.findtext("d:displayname", "", ns) or href.rstrip("/").split("/")[-1]

                calendars.append(CalendarInfo(
                    id=href,
                    name=name,
                    description="",
                    primary=len(calendars) == 0,
                ))

        except ET.ParseError as e:
            logger.warning("caldav_xml_parse_error", **safe_error_log(e))

        return calendars

    # =========================================================================
    # Event CRUD
    # =========================================================================

    async def create_event(
        self,
        calendar_id: str,
        event: CalendarEvent,
    ) -> str:
        """
        Erstellt ein neues Ereignis im CalDAV-Kalender.

        Args:
            calendar_id: Kalender-URL / Pfad
            event: CalendarEvent mit Ereignisdaten

        Returns:
            Event-UID (identisch mit event.uid)
        """
        vcalendar = _render_vevent(event)

        if self._caldav_available:
            return await self._create_event_caldav(calendar_id, event, vcalendar)
        return await self._create_event_httpx(calendar_id, event, vcalendar)

    async def _create_event_caldav(
        self, calendar_id: str, event: CalendarEvent, vcalendar: str
    ) -> str:
        """Event erstellen via caldav Library."""
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            calendar = caldav.Calendar(client=client, url=calendar_id)
            calendar.save_event(vcalendar)

            logger.info("caldav_event_created", event_uid=event.uid)
            return event.uid

        except Exception as e:
            logger.error(
                "caldav_event_create_failed",
                event_uid=event.uid,
                **safe_error_log(e),
            )
            raise

    async def _create_event_httpx(
        self, calendar_id: str, event: CalendarEvent, vcalendar: str
    ) -> str:
        """Event erstellen via httpx PUT."""
        event_url = f"{calendar_id.rstrip('/')}/{event.uid}.ics"

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
            ) as client:
                response = await client.put(
                    event_url,
                    headers={"Content-Type": "text/calendar; charset=utf-8"},
                    content=vcalendar,
                )
                response.raise_for_status()

                logger.info("caldav_event_created_httpx", event_uid=event.uid)
                return event.uid

        except Exception as e:
            logger.error(
                "caldav_httpx_event_create_failed",
                event_uid=event.uid,
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

        Bei CalDAV wird ein Update durch erneutes PUT der .ics-Datei
        mit derselben UID durchgeführt.

        Args:
            calendar_id: Kalender-URL / Pfad
            event_id: Event-UID
            event: Aktualisierte CalendarEvent-Daten

        Returns:
            True wenn erfolgreich
        """
        vcalendar = _render_vevent(event)

        if self._caldav_available:
            return await self._update_event_caldav(calendar_id, event_id, vcalendar)
        return await self._update_event_httpx(calendar_id, event_id, vcalendar)

    async def _update_event_caldav(
        self, calendar_id: str, event_id: str, vcalendar: str
    ) -> bool:
        """Event aktualisieren via caldav Library."""
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            calendar = caldav.Calendar(client=client, url=calendar_id)
            calendar.save_event(vcalendar)

            logger.info("caldav_event_updated", event_id=event_id)
            return True

        except Exception as e:
            logger.error(
                "caldav_event_update_failed",
                event_id=event_id,
                **safe_error_log(e),
            )
            return False

    async def _update_event_httpx(
        self, calendar_id: str, event_id: str, vcalendar: str
    ) -> bool:
        """Event aktualisieren via httpx PUT."""
        event_url = f"{calendar_id.rstrip('/')}/{event_id}.ics"

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
            ) as client:
                response = await client.put(
                    event_url,
                    headers={"Content-Type": "text/calendar; charset=utf-8"},
                    content=vcalendar,
                )
                response.raise_for_status()

                logger.info("caldav_event_updated_httpx", event_id=event_id)
                return True

        except Exception as e:
            logger.error(
                "caldav_httpx_event_update_failed",
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
        Löscht ein Ereignis aus dem CalDAV-Kalender.

        Args:
            calendar_id: Kalender-URL / Pfad
            event_id: Event-UID

        Returns:
            True wenn erfolgreich
        """
        if self._caldav_available:
            return await self._delete_event_caldav(calendar_id, event_id)
        return await self._delete_event_httpx(calendar_id, event_id)

    async def _delete_event_caldav(self, calendar_id: str, event_id: str) -> bool:
        """Event löschen via caldav Library."""
        try:
            import caldav
            client = caldav.DAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
            )
            calendar = caldav.Calendar(client=client, url=calendar_id)

            # Event suchen und löschen
            try:
                event_url = f"{calendar_id.rstrip('/')}/{event_id}.ics"
                event_obj = caldav.Event(client=client, url=event_url, parent=calendar)
                event_obj.delete()
            except Exception:
                # Fallback: Alle Events durchsuchen
                events = calendar.events()
                for evt in events:
                    if hasattr(evt, "vobject_instance"):
                        vevent = evt.vobject_instance.vevent
                        if hasattr(vevent, "uid") and str(vevent.uid.value) == event_id:
                            evt.delete()
                            break

            logger.info("caldav_event_deleted", event_id=event_id)
            return True

        except Exception as e:
            logger.error(
                "caldav_event_delete_failed",
                event_id=event_id,
                **safe_error_log(e),
            )
            return False

    async def _delete_event_httpx(self, calendar_id: str, event_id: str) -> bool:
        """Event löschen via httpx DELETE."""
        event_url = f"{calendar_id.rstrip('/')}/{event_id}.ics"

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                timeout=15.0,
            ) as client:
                response = await client.delete(event_url)

                if response.status_code in (200, 204, 404):
                    logger.info("caldav_event_deleted_httpx", event_id=event_id)
                    return True

                response.raise_for_status()
                return True

        except Exception as e:
            logger.error(
                "caldav_httpx_event_delete_failed",
                event_id=event_id,
                **safe_error_log(e),
            )
            return False
