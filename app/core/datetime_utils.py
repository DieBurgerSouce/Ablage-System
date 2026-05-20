# -*- coding: utf-8 -*-
"""Datetime Utilities - Zentrale Funktionen für Zeitstempel.

Diese Utilities ersetzen datetime.utcnow() das seit Python 3.12
deprecated ist. Die korrekte Alternative ist datetime.now(timezone.utc).

Verwendung:
    from app.core.datetime_utils import utc_now

    now = utc_now()  # timezone-aware UTC datetime
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Gibt aktuellen UTC-Zeitstempel zurück.

    Ersetzt das deprecated datetime.utcnow() mit
    datetime.now(timezone.utc) für timezone-aware datetimes.

    Returns:
        datetime: Aktueller UTC-Zeitstempel (timezone-aware)

    Example:
        >>> from app.core.datetime_utils import utc_now
        >>> now = utc_now()
        >>> now.tzinfo is not None
        True
    """
    return datetime.now(timezone.utc)


def utc_today() -> datetime:
    """Gibt Mitternacht des heutigen Tages in UTC zurück.

    Returns:
        datetime: Heutiges Datum um 00:00:00 UTC (timezone-aware)
    """
    now = utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def utc_timestamp() -> float:
    """Gibt aktuellen UTC-Zeitstempel als Unix-Timestamp zurück.

    Returns:
        float: Sekunden seit Unix Epoch
    """
    return utc_now().timestamp()


def utc_isoformat() -> str:
    """Gibt aktuellen UTC-Zeitstempel im ISO-Format zurück.

    Returns:
        str: ISO 8601 formatierter Zeitstempel (z.B. "2024-01-15T10:30:00+00:00")
    """
    return utc_now().isoformat()


def parse_iso_datetime(iso_string: str) -> Optional[datetime]:
    """Parst einen ISO 8601 Zeitstempel.

    Args:
        iso_string: ISO 8601 formatierter Zeitstempel

    Returns:
        datetime: Geparstes Datetime-Objekt oder None bei Fehler
    """
    try:
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def ensure_utc(dt: datetime) -> datetime:
    """Stellt sicher dass ein datetime timezone-aware (UTC) ist.

    Falls das datetime naive ist (kein tzinfo), wird UTC angenommen.

    Args:
        dt: datetime Objekt (naive oder aware)

    Returns:
        datetime: Timezone-aware UTC datetime
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
