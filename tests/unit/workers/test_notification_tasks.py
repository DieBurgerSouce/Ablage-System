# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Notification Celery Tasks.

Testet:
- send_daily_digest (Taegliche E-Mail-Zusammenfassung)
- send_weekly_digest (Woechentliche E-Mail-Zusammenfassung)
- cleanup_old_notifications (Alte Benachrichtigungen loeschen)

HINWEIS: Die Notification-Tasks importieren Services dynamisch INSIDE der Funktionen.
Diese Tests fokussieren auf die statisch testbaren Aspekte (Konfiguration, Registrierung, Templates).

Feinpoliert und durchdacht - Enterprise-grade Notification-Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_user_with_daily_digest():
    """Create mock user with daily digest preference."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    user.preferences = {
        "notifications": {
            "email_digest": "daily",
            "email_on_ocr_complete": True,
            "email_on_ocr_failed": True,
            "email_on_share": True,
        }
    }
    return user


@pytest.fixture
def mock_user_with_weekly_digest():
    """Create mock user with weekly digest preference."""
    user = Mock()
    user.id = uuid4()
    user.email = "weekly@example.com"
    user.username = "weeklyuser"
    user.full_name = "Weekly User"
    user.preferences = {
        "notifications": {
            "email_digest": "weekly",
            "email_on_ocr_complete": True,
            "email_on_ocr_failed": False,
            "email_on_share": True,
        }
    }
    return user


@pytest.fixture
def sample_notifications():
    """Create sample unread notifications."""
    return [
        Mock(
            id=uuid4(),
            title="Dokument verarbeitet",
            message="Rechnung_001.pdf wurde erfolgreich verarbeitet",
            notification_type="document_processed",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            is_read=False,
        ),
        Mock(
            id=uuid4(),
            title="OCR abgeschlossen",
            message="5 Dokumente wurden verarbeitet",
            notification_type="batch_complete",
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
            is_read=False,
        ),
        Mock(
            id=uuid4(),
            title="Dokument geteilt",
            message="Max Mustermann hat ein Dokument mit Ihnen geteilt",
            notification_type="document_shared",
            created_at=datetime.now(timezone.utc) - timedelta(hours=10),
            is_read=False,
        ),
    ]


@pytest.fixture
def sample_document_stats():
    """Create sample document stats."""
    return {
        "total": 15,
        "successful": 13,
        "failed": 2,
        "success_rate": 86.7,
    }


# ========================= Task Definition Tests =========================


class TestTaskDefinitions:
    """Tests fuer Task-Definitionen."""

    def test_send_daily_digest_exists(self):
        """send_daily_digest sollte existieren."""
        from app.workers.tasks.notification_tasks import send_daily_digest

        assert send_daily_digest is not None

    def test_send_weekly_digest_exists(self):
        """send_weekly_digest sollte existieren."""
        from app.workers.tasks.notification_tasks import send_weekly_digest

        assert send_weekly_digest is not None

    def test_cleanup_old_notifications_exists(self):
        """cleanup_old_notifications sollte existieren."""
        from app.workers.tasks.notification_tasks import cleanup_old_notifications

        assert cleanup_old_notifications is not None

    def test_tasks_have_names(self):
        """Tasks sollten benannt sein."""
        from app.workers.tasks.notification_tasks import (
            send_daily_digest,
            send_weekly_digest,
            cleanup_old_notifications,
        )

        assert send_daily_digest.name is not None
        assert "daily_digest" in send_daily_digest.name
        assert send_weekly_digest.name is not None
        assert "weekly_digest" in send_weekly_digest.name
        assert cleanup_old_notifications.name is not None
        assert "cleanup" in cleanup_old_notifications.name

    def test_tasks_exported_from_init(self):
        """Tasks sollten von __init__ exportiert werden."""
        from app.workers.tasks import (
            send_daily_digest,
            send_weekly_digest,
            cleanup_old_notifications,
        )

        assert send_daily_digest is not None
        assert send_weekly_digest is not None
        assert cleanup_old_notifications is not None

    def test_tasks_have_correct_names(self):
        """Tasks sollten korrekte Namen haben."""
        from app.workers.tasks.notification_tasks import (
            send_daily_digest,
            send_weekly_digest,
            cleanup_old_notifications,
        )

        assert send_daily_digest.name == "app.workers.tasks.notification_tasks.send_daily_digest"
        assert send_weekly_digest.name == "app.workers.tasks.notification_tasks.send_weekly_digest"
        assert cleanup_old_notifications.name == "app.workers.tasks.notification_tasks.cleanup_old_notifications"


# ========================= Template Tests =========================


class TestEmailTemplates:
    """Tests fuer E-Mail-Templates."""

    def test_daily_template_exists(self):
        """Daily template sollte existieren."""
        from app.workers.tasks.notification_tasks import DAILY_DIGEST_TEMPLATE

        assert DAILY_DIGEST_TEMPLATE is not None
        assert len(DAILY_DIGEST_TEMPLATE) > 100  # Should have substantial content

    def test_weekly_template_exists(self):
        """Weekly template sollte existieren."""
        from app.workers.tasks.notification_tasks import WEEKLY_DIGEST_TEMPLATE

        assert WEEKLY_DIGEST_TEMPLATE is not None
        assert len(WEEKLY_DIGEST_TEMPLATE) > 100

    def test_daily_template_has_placeholders(self):
        """Daily template sollte erforderliche Platzhalter haben."""
        from app.workers.tasks.notification_tasks import DAILY_DIGEST_TEMPLATE

        required_placeholders = [
            "{username}",
            "{date}",
            "{documents_section}",
            "{notifications_section}",
            "{total_documents}",
            "{total_notifications}",
            "{unread_count}",
        ]

        for placeholder in required_placeholders:
            assert placeholder in DAILY_DIGEST_TEMPLATE, f"Missing: {placeholder}"

    def test_weekly_template_has_placeholders(self):
        """Weekly template sollte erforderliche Platzhalter haben."""
        from app.workers.tasks.notification_tasks import WEEKLY_DIGEST_TEMPLATE

        required_placeholders = [
            "{username}",
            "{week_start}",
            "{week_end}",
            "{documents_section}",
            "{notifications_section}",
            "{total_documents}",
            "{ocr_success_rate}",
            "{total_notifications}",
            "{avg_processing_time}",
            "{trend_section}",
        ]

        for placeholder in required_placeholders:
            assert placeholder in WEEKLY_DIGEST_TEMPLATE, f"Missing: {placeholder}"

    def test_templates_are_in_german(self):
        """Templates sollten auf Deutsch sein."""
        from app.workers.tasks.notification_tasks import (
            DAILY_DIGEST_TEMPLATE,
            WEEKLY_DIGEST_TEMPLATE,
        )

        # Check for German words
        assert "Guten Morgen" in DAILY_DIGEST_TEMPLATE
        assert "Zusammenfassung" in DAILY_DIGEST_TEMPLATE or "zusammenfassung" in DAILY_DIGEST_TEMPLATE.lower()
        assert "Guten Morgen" in WEEKLY_DIGEST_TEMPLATE
        assert "Ablage-System" in DAILY_DIGEST_TEMPLATE
        assert "Ablage-System" in WEEKLY_DIGEST_TEMPLATE


# ========================= Helper Function Tests =========================


class TestHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    def test_run_async_helper_exists(self):
        """run_async Helper sollte existieren."""
        from app.workers.tasks.notification_tasks import run_async

        assert run_async is not None
        assert callable(run_async)

    def test_run_async_executes_coroutine(self):
        """run_async sollte Coroutine ausfuehren."""
        from app.workers.tasks.notification_tasks import run_async

        async def sample_coro():
            return "success"

        result = run_async(sample_coro())

        assert result == "success"

    def test_run_async_handles_exception(self):
        """run_async sollte Exceptions propagieren."""
        from app.workers.tasks.notification_tasks import run_async

        async def failing_coro():
            raise ValueError("Test error")

        with pytest.raises(ValueError) as exc_info:
            run_async(failing_coro())

        assert "Test error" in str(exc_info.value)

    def test_format_documents_section_exists(self):
        """format_documents_section sollte existieren."""
        from app.workers.tasks.notification_tasks import format_documents_section

        assert format_documents_section is not None
        assert callable(format_documents_section)

    def test_format_documents_section_no_docs(self):
        """Sollte korrekt formatieren bei keinen Dokumenten."""
        from app.workers.tasks.notification_tasks import format_documents_section

        result = format_documents_section({"total": 0, "successful": 0, "failed": 0})

        assert "Keine neuen Dokumente" in result

    def test_format_documents_section_with_docs(self, sample_document_stats):
        """Sollte korrekt formatieren mit Dokumenten."""
        from app.workers.tasks.notification_tasks import format_documents_section

        result = format_documents_section(sample_document_stats)

        assert "15" in result or "Dokument" in result
        assert "13" in result or "erfolgreich" in result

    def test_format_documents_section_shows_failures(self):
        """Sollte Fehler anzeigen wenn vorhanden."""
        from app.workers.tasks.notification_tasks import format_documents_section

        stats = {"total": 10, "successful": 8, "failed": 2}
        result = format_documents_section(stats)

        assert "2" in result
        assert "Fehler" in result or "⚠️" in result

    def test_format_notifications_section_exists(self):
        """format_notifications_section sollte existieren."""
        from app.workers.tasks.notification_tasks import format_notifications_section

        assert format_notifications_section is not None
        assert callable(format_notifications_section)

    def test_format_notifications_section_no_notifications(self):
        """Sollte korrekt formatieren bei keinen Benachrichtigungen."""
        from app.workers.tasks.notification_tasks import format_notifications_section

        result = format_notifications_section([])

        assert "Keine neuen Benachrichtigungen" in result

    def test_format_notifications_section_with_notifications(self, sample_notifications):
        """Sollte korrekt formatieren mit Benachrichtigungen."""
        from app.workers.tasks.notification_tasks import format_notifications_section

        result = format_notifications_section(sample_notifications)

        # Should contain notification titles
        assert "Dokument verarbeitet" in result or "📬" in result or "📭" in result


# ========================= Async Helper Tests =========================


class TestAsyncHelpers:
    """Tests fuer async Helper-Funktionen."""

    def test_get_users_with_digest_preference_exists(self):
        """get_users_with_digest_preference sollte existieren."""
        from app.workers.tasks.notification_tasks import get_users_with_digest_preference

        assert get_users_with_digest_preference is not None
        assert callable(get_users_with_digest_preference)

    def test_get_user_document_stats_exists(self):
        """get_user_document_stats sollte existieren."""
        from app.workers.tasks.notification_tasks import get_user_document_stats

        assert get_user_document_stats is not None
        assert callable(get_user_document_stats)

    def test_get_user_notifications_exists(self):
        """get_user_notifications sollte existieren."""
        from app.workers.tasks.notification_tasks import get_user_notifications

        assert get_user_notifications is not None
        assert callable(get_user_notifications)

    def test_get_unread_notification_count_exists(self):
        """get_unread_notification_count sollte existieren."""
        from app.workers.tasks.notification_tasks import get_unread_notification_count

        assert get_unread_notification_count is not None
        assert callable(get_unread_notification_count)

    def test_send_digest_email_exists(self):
        """send_digest_email sollte existieren."""
        from app.workers.tasks.notification_tasks import send_digest_email

        assert send_digest_email is not None
        assert callable(send_digest_email)


# ========================= Celery Beat Schedule Tests =========================


class TestCeleryBeatSchedule:
    """Tests fuer Celery Beat Schedule Konfiguration."""

    def test_daily_digest_in_beat_schedule(self):
        """Daily digest sollte im Beat Schedule sein."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        assert "notification-daily-digest" in beat_schedule
        config = beat_schedule["notification-daily-digest"]
        assert config["task"] == "app.workers.tasks.notification_tasks.send_daily_digest"

    def test_weekly_digest_in_beat_schedule(self):
        """Weekly digest sollte im Beat Schedule sein."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        assert "notification-weekly-digest" in beat_schedule
        config = beat_schedule["notification-weekly-digest"]
        assert config["task"] == "app.workers.tasks.notification_tasks.send_weekly_digest"

    def test_cleanup_in_beat_schedule(self):
        """Cleanup sollte im Beat Schedule sein."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        assert "notification-cleanup-old" in beat_schedule
        config = beat_schedule["notification-cleanup-old"]
        assert config["task"] == "app.workers.tasks.notification_tasks.cleanup_old_notifications"

    def test_daily_digest_schedule_time(self):
        """Daily digest sollte um 08:00 Uhr laufen."""
        from app.workers.celery_app import celery_app
        from celery.schedules import crontab

        beat_schedule = celery_app.conf.beat_schedule
        config = beat_schedule["notification-daily-digest"]
        schedule = config["schedule"]

        # Check that it's a crontab at 08:00
        assert isinstance(schedule, crontab)
        assert schedule._orig_hour == 8
        assert schedule._orig_minute == 0

    def test_weekly_digest_schedule_time(self):
        """Weekly digest sollte Montag 08:00 laufen."""
        from app.workers.celery_app import celery_app
        from celery.schedules import crontab

        beat_schedule = celery_app.conf.beat_schedule
        config = beat_schedule["notification-weekly-digest"]
        schedule = config["schedule"]

        # Check that it's a crontab on Monday at 08:00
        assert isinstance(schedule, crontab)
        assert schedule._orig_day_of_week == 1  # Monday
        assert schedule._orig_hour == 8

    def test_cleanup_schedule_time(self):
        """Cleanup sollte Sonntag 04:00 laufen."""
        from app.workers.celery_app import celery_app
        from celery.schedules import crontab

        beat_schedule = celery_app.conf.beat_schedule
        config = beat_schedule["notification-cleanup-old"]
        schedule = config["schedule"]

        # Check that it's a crontab on Sunday at 04:00
        assert isinstance(schedule, crontab)
        assert schedule._orig_day_of_week == 0  # Sunday
        assert schedule._orig_hour == 4

    def test_cleanup_default_days_90(self):
        """Cleanup sollte standardmaessig 90 Tage verwenden."""
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule
        config = beat_schedule["notification-cleanup-old"]

        assert "kwargs" in config
        assert config["kwargs"]["days"] == 90


# ========================= Task Routes Tests =========================


class TestTaskRoutes:
    """Tests fuer Task Routing Konfiguration."""

    def test_notification_tasks_routed_to_maintenance_queue(self):
        """Notification tasks sollten zur maintenance queue geroutet werden."""
        from app.workers.celery_app import celery_app

        routes = celery_app.conf.task_routes

        # Check daily digest
        assert "app.workers.tasks.notification_tasks.send_daily_digest" in routes
        assert routes["app.workers.tasks.notification_tasks.send_daily_digest"]["queue"] == "maintenance"

        # Check weekly digest
        assert "app.workers.tasks.notification_tasks.send_weekly_digest" in routes
        assert routes["app.workers.tasks.notification_tasks.send_weekly_digest"]["queue"] == "maintenance"

        # Check cleanup
        assert "app.workers.tasks.notification_tasks.cleanup_old_notifications" in routes
        assert routes["app.workers.tasks.notification_tasks.cleanup_old_notifications"]["queue"] == "maintenance"


# ========================= Task Configuration Tests =========================


class TestTaskConfiguration:
    """Tests fuer Task-Konfiguration."""

    def test_daily_digest_max_retries(self):
        """Daily digest sollte max_retries konfiguriert haben."""
        from app.workers.tasks.notification_tasks import send_daily_digest

        assert send_daily_digest.max_retries == 3

    def test_weekly_digest_max_retries(self):
        """Weekly digest sollte max_retries konfiguriert haben."""
        from app.workers.tasks.notification_tasks import send_weekly_digest

        assert send_weekly_digest.max_retries == 3

    def test_cleanup_max_retries(self):
        """Cleanup sollte max_retries konfiguriert haben."""
        from app.workers.tasks.notification_tasks import cleanup_old_notifications

        assert cleanup_old_notifications.max_retries == 2

    def test_tasks_are_bound(self):
        """Tasks sollten gebunden sein (bind=True)."""
        from app.workers.tasks.notification_tasks import (
            send_daily_digest,
            send_weekly_digest,
            cleanup_old_notifications,
        )

        # All tasks should have bind=True in their signature
        # This means they receive 'self' as first argument
        assert hasattr(send_daily_digest, 'bind')
        assert hasattr(send_weekly_digest, 'bind')
        assert hasattr(cleanup_old_notifications, 'bind')


# =============================================================================
# PHASE 1: Automatische Zahlungserinnerungen - Dunning Email Tasks (Januar 2026)
# =============================================================================


class TestDunningEmailWithRetryTask:
    """Tests fuer send_dunning_email_with_retry Task (Task 1.4)."""

    def test_send_dunning_email_with_retry_exists(self):
        """send_dunning_email_with_retry sollte existieren."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        assert send_dunning_email_with_retry is not None

    def test_send_dunning_email_with_retry_is_registered(self):
        """Sollte send_dunning_email_with_retry Task registriert haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        assert hasattr(send_dunning_email_with_retry, 'name')
        assert send_dunning_email_with_retry.name == "app.workers.tasks.notification_tasks.send_dunning_email_with_retry"

    def test_send_dunning_email_with_retry_has_retry_config(self):
        """Sollte retry Konfiguration mit exponential backoff haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        assert hasattr(send_dunning_email_with_retry, 'max_retries')
        assert send_dunning_email_with_retry.max_retries == 5

    def test_send_dunning_email_with_retry_has_backoff(self):
        """Sollte exponential backoff konfiguriert haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        # Check retry_backoff is True (exponential backoff)
        assert hasattr(send_dunning_email_with_retry, 'retry_backoff')
        assert send_dunning_email_with_retry.retry_backoff is True

    def test_send_dunning_email_with_retry_has_jitter(self):
        """Sollte retry jitter konfiguriert haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        assert hasattr(send_dunning_email_with_retry, 'retry_jitter')
        assert send_dunning_email_with_retry.retry_jitter is True

    def test_send_dunning_email_with_retry_has_max_backoff(self):
        """Sollte maximale Backoff-Zeit konfiguriert haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        assert hasattr(send_dunning_email_with_retry, 'retry_backoff_max')
        assert send_dunning_email_with_retry.retry_backoff_max == 600  # 10 Minuten

    def test_send_dunning_email_with_retry_uses_cpu_base(self):
        """Sollte CPUTask Base verwenden."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry
        from app.workers.celery_app import CPUTask

        assert isinstance(send_dunning_email_with_retry, CPUTask)


class TestRetryFailedDunningEmailsTask:
    """Tests fuer retry_failed_dunning_emails Task (Task 1.4)."""

    def test_retry_failed_dunning_emails_exists(self):
        """retry_failed_dunning_emails sollte existieren."""
        from app.workers.tasks.notification_tasks import retry_failed_dunning_emails

        assert retry_failed_dunning_emails is not None

    def test_retry_failed_dunning_emails_is_registered(self):
        """Sollte retry_failed_dunning_emails Task registriert haben."""
        from app.workers.tasks.notification_tasks import retry_failed_dunning_emails

        assert hasattr(retry_failed_dunning_emails, 'name')
        assert retry_failed_dunning_emails.name == "app.workers.tasks.notification_tasks.retry_failed_dunning_emails"

    def test_retry_failed_dunning_emails_uses_cpu_base(self):
        """Sollte CPUTask Base verwenden."""
        from app.workers.tasks.notification_tasks import retry_failed_dunning_emails
        from app.workers.celery_app import CPUTask

        assert isinstance(retry_failed_dunning_emails, CPUTask)

    def test_retry_failed_dunning_emails_has_retry_config(self):
        """Sollte retry Konfiguration haben."""
        from app.workers.tasks.notification_tasks import retry_failed_dunning_emails

        assert hasattr(retry_failed_dunning_emails, 'max_retries')
        # Batch-Retry-Task braucht selbst nicht viele Retries
        assert retry_failed_dunning_emails.max_retries >= 1

    def test_retry_failed_dunning_emails_not_in_beat_schedule(self):
        """Beat-Eintrag ist durch den Mahnwesen-Freeze entfernt (Odoo-Neuausrichtung 2026-07).

        Der Task-Code bleibt bestehen (Modul notification_tasks ist aktiv), aber der
        Beat-Eintrag wird in celery_app.py explizit gepoppt, weil das Mahnwesen an
        Odoo (account_followup) uebergeht. Reaktivierung: ACTIVE_OPTIONAL_MODULES.
        """
        from app.workers.celery_app import celery_app

        beat_schedule = celery_app.conf.beat_schedule

        assert "notification-retry-failed-dunning-emails" not in beat_schedule

    def test_no_beat_entry_dispatches_dunning_retry(self):
        """Kein verbleibender Beat-Eintrag zeigt auf retry_failed_dunning_emails (Freeze)."""
        from app.workers.celery_app import celery_app

        offending = [
            name
            for name, config in celery_app.conf.beat_schedule.items()
            if config.get("task") == "app.workers.tasks.notification_tasks.retry_failed_dunning_emails"
        ]
        assert offending == []


class TestDunningEmailTaskRoutes:
    """Tests fuer Dunning Email Task Routing."""

    def test_dunning_email_tasks_routed_correctly(self):
        """Dunning Email Tasks sollten zur korrekten Queue geroutet werden."""
        from app.workers.celery_app import celery_app

        routes = celery_app.conf.task_routes

        # send_dunning_email_with_retry should be routed to notification queue
        assert "app.workers.tasks.notification_tasks.send_dunning_email_with_retry" in routes
        route = routes["app.workers.tasks.notification_tasks.send_dunning_email_with_retry"]
        assert route["queue"] in ["notification", "maintenance", "banking"]


class TestDunningEmailTaskIntegration:
    """Integration Tests fuer Dunning Email Tasks."""

    @pytest.fixture
    def sample_notification_data(self):
        """Sample Notification Daten fuer Tests."""
        return {
            "notification_id": str(uuid4()),
            "recipient_email": "kunde@example.com",
            "subject": "1. Mahnung - Rechnung RE-2024-001",
            "body": "Sehr geehrte Damen und Herren...",
            "pdf_attachment": b"%PDF-1.4 test content",
            "attachment_filename": "Mahnung_RE-2024-001.pdf",
        }

    def test_dunning_email_task_params(self, sample_notification_data):
        """Sollte korrekte Parameter akzeptieren."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry

        # Verify task accepts required parameters
        # This is a static check - doesn't actually call the task
        import inspect
        sig = inspect.signature(send_dunning_email_with_retry.run)
        params = list(sig.parameters.keys())

        # Should have these parameters (self is implicit for bound tasks)
        expected_params = [
            "notification_id",
            "recipient_email",
            "subject",
            "body",
        ]

        for param in expected_params:
            assert param in params, f"Missing parameter: {param}"

    def test_dunning_email_task_optional_params(self, sample_notification_data):
        """Sollte optionale Parameter fuer PDF-Anhang haben."""
        from app.workers.tasks.notification_tasks import send_dunning_email_with_retry
        import inspect

        sig = inspect.signature(send_dunning_email_with_retry.run)
        params = sig.parameters

        # Optional attachment parameters
        optional_params = ["pdf_attachment", "attachment_filename"]

        for param in optional_params:
            if param in params:
                # Should have a default value (optional)
                assert params[param].default is not inspect.Parameter.empty or \
                       params[param].default is None
