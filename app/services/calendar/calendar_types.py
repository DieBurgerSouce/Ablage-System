# -*- coding: utf-8 -*-
"""
Gemeinsame Typen für Kalender-Provider-Clients.

Definiert CalendarEvent und CalendarInfo als zentrale Datenstrukturen,
die von allen Provider-Clients (Google, Microsoft, CalDAV) verwendet werden.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CalendarEvent:
    """Einheitliche Kalender-Ereignis-Darstellung.

    Wird von allen Provider-Clients verwendet und auf das
    jeweilige Provider-Format gemappt.
    """

    uid: str
    """Ablage-interne UID für Tracking."""

    title: str
    """Titel / Betreff des Ereignisses."""

    description: str
    """Beschreibung / Notizen."""

    start: datetime
    """Startzeitpunkt (timezone-aware)."""

    end: datetime
    """Endzeitpunkt (timezone-aware)."""

    location: Optional[str] = None
    """Optionaler Veranstaltungsort."""

    all_day: bool = False
    """Ganztaegiges Ereignis."""

    external_id: Optional[str] = None
    """Provider-spezifische Event-ID nach Erstellung."""


@dataclass
class CalendarInfo:
    """Kalender-Metadaten von einem Provider."""

    id: str
    """Provider-spezifische Kalender-ID."""

    name: str
    """Anzeigename des Kalenders."""

    description: str
    """Beschreibung des Kalenders."""

    primary: bool
    """Ob dies der primäre Kalender des Benutzers ist."""

    color: Optional[str] = None
    """Optionale Farbkennung (Hex-Wert)."""
