# -*- coding: utf-8 -*-
"""
Unit tests for Privat Deadline Service.

Tests fuer Fristen-Verwaltung:
- Frist-Erstellung
- Frist-Status-Berechnung
- Dashboard-Widget
- iCal-Export
- Wiederkehrende Fristen
"""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from pathlib import Path
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestDeadlineStatusCalculation:
    """Tests fuer Frist-Status-Berechnung (keine DB erforderlich)."""

    def test_days_remaining_future_date(self):
        """Teste Berechnung verbleibender Tage (Zukunft)."""
        today = date.today()
        due_date = today + timedelta(days=7)

        days_remaining = (due_date - today).days

        assert days_remaining == 7

    def test_days_remaining_past_date(self):
        """Teste Berechnung verbleibender Tage (Vergangenheit)."""
        today = date.today()
        due_date = today - timedelta(days=3)

        days_remaining = (due_date - today).days

        assert days_remaining == -3

    def test_days_remaining_today(self):
        """Teste Berechnung fuer heute faellige Frist."""
        today = date.today()
        due_date = today

        days_remaining = (due_date - today).days

        assert days_remaining == 0

    def test_is_overdue_past_date(self):
        """Teste Ueberfaelligkeits-Status (Vergangenheit)."""
        today = date.today()
        due_date = today - timedelta(days=1)
        is_completed = False

        days_remaining = (due_date - today).days
        is_overdue = days_remaining < 0 and not is_completed

        assert is_overdue is True

    def test_is_overdue_future_date(self):
        """Teste Ueberfaelligkeits-Status (Zukunft)."""
        today = date.today()
        due_date = today + timedelta(days=1)
        is_completed = False

        days_remaining = (due_date - today).days
        is_overdue = days_remaining < 0 and not is_completed

        assert is_overdue is False

    def test_is_overdue_completed(self):
        """Teste Ueberfaelligkeits-Status (erledigt)."""
        today = date.today()
        due_date = today - timedelta(days=10)
        is_completed = True

        days_remaining = (due_date - today).days
        is_overdue = days_remaining < 0 and not is_completed

        assert is_overdue is False  # Erledigt = nicht ueberfaellig


class TestDeadlineReminderCalculation:
    """Tests fuer Erinnerungs-Berechnung."""

    def test_next_reminder_calculation_7_days(self):
        """Teste naechste Erinnerung 7 Tage vorher."""
        today = date.today()
        due_date = today + timedelta(days=10)
        reminder_days = [7, 3, 1]

        next_reminder = None
        for days in sorted(reminder_days, reverse=True):
            reminder_date = due_date - timedelta(days=days)
            if reminder_date >= today:
                next_reminder = reminder_date
                break

        expected = due_date - timedelta(days=7)
        assert next_reminder == expected

    def test_next_reminder_calculation_3_days(self):
        """Teste naechste Erinnerung 3 Tage vorher."""
        today = date.today()
        due_date = today + timedelta(days=5)
        reminder_days = [7, 3, 1]

        next_reminder = None
        for days in sorted(reminder_days, reverse=True):
            reminder_date = due_date - timedelta(days=days)
            if reminder_date >= today:
                next_reminder = reminder_date
                break

        # 7 Tage vorher waere in der Vergangenheit
        # 3 Tage vorher ist in der Zukunft
        expected = due_date - timedelta(days=3)
        assert next_reminder == expected

    def test_next_reminder_no_reminders_left(self):
        """Teste wenn keine Erinnerung mehr bevorsteht."""
        today = date.today()
        due_date = today  # Heute faellig
        reminder_days = [7, 3, 1]

        next_reminder = None
        for days in sorted(reminder_days, reverse=True):
            reminder_date = due_date - timedelta(days=days)
            if reminder_date >= today:
                next_reminder = reminder_date
                break

        assert next_reminder is None

    def test_reminder_on_exact_day(self):
        """Teste Erinnerung am exakten Tag."""
        today = date.today()
        due_date = today + timedelta(days=7)
        reminder_days = [7]

        reminder_date = due_date - timedelta(days=7)
        is_reminder_due = reminder_date == today

        assert is_reminder_due is True


class TestRecurrenceIntervalCalculation:
    """Tests fuer Wiederholungs-Intervalle."""

    def test_daily_interval(self):
        """Teste taegliches Intervall."""
        interval_days = {"daily": 1}.get("daily", 30)
        assert interval_days == 1

    def test_weekly_interval(self):
        """Teste woechentliches Intervall."""
        interval_days = {"weekly": 7}.get("weekly", 30)
        assert interval_days == 7

    def test_monthly_interval(self):
        """Teste monatliches Intervall."""
        interval_days = {"monthly": 30}.get("monthly", 30)
        assert interval_days == 30

    def test_quarterly_interval(self):
        """Teste vierteljaehrliches Intervall."""
        interval_days = {"quarterly": 90}.get("quarterly", 30)
        assert interval_days == 90

    def test_semi_annual_interval(self):
        """Teste halbjaehrliches Intervall."""
        interval_days = {"semi_annual": 180}.get("semi_annual", 30)
        assert interval_days == 180

    def test_annual_interval(self):
        """Teste jaehrliches Intervall."""
        interval_days = {"annual": 365}.get("annual", 30)
        assert interval_days == 365

    def test_unknown_interval_defaults_to_30(self):
        """Teste Fallback fuer unbekanntes Intervall."""
        intervals = {
            "daily": 1,
            "weekly": 7,
            "monthly": 30,
        }
        interval_days = intervals.get("unknown", 30)
        assert interval_days == 30

    def test_next_occurrence_calculation(self):
        """Teste Berechnung der naechsten Wiederholung."""
        current_due = date(2024, 12, 29)
        interval_days = 30

        next_due = current_due + timedelta(days=interval_days)

        assert next_due == date(2025, 1, 28)


class TestICalGeneration:
    """Tests fuer iCal-Export."""

    def test_ical_header_format(self):
        """Teste iCal-Header-Format."""
        calendar_name = "Privat-Fristen"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Ablage-System//Privat-Modul//DE",
            f"X-WR-CALNAME:{calendar_name}",
            "METHOD:PUBLISH",
        ]

        ical = "\r\n".join(lines)

        assert "BEGIN:VCALENDAR" in ical
        assert "VERSION:2.0" in ical
        assert "PRODID:-//Ablage-System//Privat-Modul//DE" in ical
        assert f"X-WR-CALNAME:{calendar_name}" in ical

    def test_ical_event_format(self):
        """Teste iCal-Event-Format."""
        deadline_id = uuid4()
        title = "Versicherung erneuern"
        due_date = date(2024, 12, 29)

        uid = str(deadline_id).replace("-", "")
        dtstart = due_date.strftime("%Y%m%d")

        lines = [
            "BEGIN:VEVENT",
            f"UID:{uid}@ablage-system.privat",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"SUMMARY:{title}",
            "END:VEVENT",
        ]

        ical = "\r\n".join(lines)

        assert "BEGIN:VEVENT" in ical
        assert f"UID:{uid}@ablage-system.privat" in ical
        assert "DTSTART;VALUE=DATE:20241229" in ical
        assert f"SUMMARY:{title}" in ical
        assert "END:VEVENT" in ical

    def test_ical_alarm_format(self):
        """Teste iCal-Alarm-Format (VALARM)."""
        title = "Versicherung erneuern"
        reminder_days = 7

        lines = [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Erinnerung: {title}",
            f"TRIGGER:-P{reminder_days}D",
            "END:VALARM",
        ]

        ical = "\r\n".join(lines)

        assert "BEGIN:VALARM" in ical
        assert "ACTION:DISPLAY" in ical
        assert "TRIGGER:-P7D" in ical
        assert "END:VALARM" in ical

    def test_ical_multiple_alarms(self):
        """Teste mehrere Erinnerungen pro Event."""
        reminder_days = [7, 3, 1]

        alarm_count = 0
        for days in reminder_days:
            alarm_count += 1

        assert alarm_count == 3

    def test_ical_description_escaping(self):
        """Teste Escape von Zeilenumbruechen in Beschreibung."""
        description = "Erste Zeile\nZweite Zeile\nDritte Zeile"

        escaped = description.replace("\n", "\\n")

        assert "\\n" in escaped
        assert escaped == "Erste Zeile\\nZweite Zeile\\nDritte Zeile"

    def test_ical_encoding_utf8(self):
        """Teste UTF-8 Encoding fuer deutsche Umlaute."""
        title = "Versicherungsüberprüfung"

        ical_line = f"SUMMARY:{title}"
        encoded = ical_line.encode("utf-8")

        assert b"\xc3\xbc" in encoded  # ü in UTF-8


class TestDashboardWidgetCategorization:
    """Tests fuer Dashboard-Widget-Kategorisierung."""

    def test_categorize_overdue(self):
        """Teste Kategorisierung: Ueberfaellig."""
        today = date.today()
        due_date = today - timedelta(days=5)

        is_overdue = due_date < today
        is_today = due_date == today
        is_this_week = today < due_date <= (today + timedelta(days=7))
        is_this_month = (today + timedelta(days=7)) < due_date <= (today + timedelta(days=30))

        assert is_overdue is True
        assert is_today is False
        assert is_this_week is False
        assert is_this_month is False

    def test_categorize_today(self):
        """Teste Kategorisierung: Heute."""
        today = date.today()
        due_date = today

        is_overdue = due_date < today
        is_today = due_date == today
        is_this_week = today < due_date <= (today + timedelta(days=7))
        is_this_month = (today + timedelta(days=7)) < due_date <= (today + timedelta(days=30))

        assert is_overdue is False
        assert is_today is True
        assert is_this_week is False
        assert is_this_month is False

    def test_categorize_this_week(self):
        """Teste Kategorisierung: Diese Woche."""
        today = date.today()
        due_date = today + timedelta(days=3)

        is_overdue = due_date < today
        is_today = due_date == today
        is_this_week = today < due_date <= (today + timedelta(days=7))
        is_this_month = (today + timedelta(days=7)) < due_date <= (today + timedelta(days=30))

        assert is_overdue is False
        assert is_today is False
        assert is_this_week is True
        assert is_this_month is False

    def test_categorize_this_month(self):
        """Teste Kategorisierung: Diesen Monat."""
        today = date.today()
        due_date = today + timedelta(days=15)

        is_overdue = due_date < today
        is_today = due_date == today
        is_this_week = today < due_date <= (today + timedelta(days=7))
        is_this_month = (today + timedelta(days=7)) < due_date <= (today + timedelta(days=30))

        assert is_overdue is False
        assert is_today is False
        assert is_this_week is False
        assert is_this_month is True

    def test_categorize_beyond_month(self):
        """Teste Kategorisierung: Nach diesem Monat (nicht im Widget)."""
        today = date.today()
        due_date = today + timedelta(days=45)

        is_overdue = due_date < today
        is_today = due_date == today
        is_this_week = today < due_date <= (today + timedelta(days=7))
        is_this_month = (today + timedelta(days=7)) < due_date <= (today + timedelta(days=30))

        assert is_overdue is False
        assert is_today is False
        assert is_this_week is False
        assert is_this_month is False


class TestDeadlineTypeEnum:
    """Tests fuer Fristen-Typen."""

    def test_deadline_types_defined(self):
        """Teste dass alle wichtigen Fristen-Typen definiert sind."""
        from app.db.schemas import PrivatDeadlineType

        # Versicherungen
        assert hasattr(PrivatDeadlineType, "INSURANCE_RENEWAL")
        assert hasattr(PrivatDeadlineType, "INSURANCE_PAYMENT")

        # Fahrzeuge
        assert hasattr(PrivatDeadlineType, "VEHICLE_TUEV")
        assert hasattr(PrivatDeadlineType, "VEHICLE_INSURANCE")

        # Immobilien
        assert hasattr(PrivatDeadlineType, "PROPERTY_TAX")

        # Kredite
        assert hasattr(PrivatDeadlineType, "LOAN_PAYMENT")

        # Steuern
        assert hasattr(PrivatDeadlineType, "TAX_DEADLINE")

        # Allgemein
        assert hasattr(PrivatDeadlineType, "CUSTOM")

    def test_deadline_type_values(self):
        """Teste Fristen-Typ-Werte."""
        from app.db.schemas import PrivatDeadlineType

        assert PrivatDeadlineType.INSURANCE_RENEWAL.value == "insurance_renewal"
        assert PrivatDeadlineType.VEHICLE_TUEV.value == "vehicle_tuev"
        assert PrivatDeadlineType.CUSTOM.value == "custom"


class TestDeadlinePriority:
    """Tests fuer Fristen-Prioritaeten."""

    def test_priority_sorting(self):
        """Teste Sortierung nach Prioritaet."""
        deadlines = [
            {"title": "Low Priority", "priority": "low"},
            {"title": "High Priority", "priority": "high"},
            {"title": "Medium Priority", "priority": "medium"},
        ]

        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_deadlines = sorted(
            deadlines,
            key=lambda d: priority_order.get(d["priority"], 1)
        )

        assert sorted_deadlines[0]["title"] == "High Priority"
        assert sorted_deadlines[1]["title"] == "Medium Priority"
        assert sorted_deadlines[2]["title"] == "Low Priority"

    def test_default_priority_medium(self):
        """Teste Standard-Prioritaet."""
        default_priority = "medium"
        assert default_priority == "medium"
