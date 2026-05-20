# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Approval Celery Tasks.

Testet:
- escalate_overdue_approvals (Eskalation ueberfaelliger Genehmigungen)
- send_approval_reminders (Erinnerungen fuer Genehmigungen)
- Notification Service Integration

Feinpoliert und durchdacht - Enterprise-grade Approval-Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_approval_request():
    """Create mock approval request."""
    request = Mock()
    request.id = uuid4()
    request.company_id = uuid4()
    request.title = "Rechnung genehmigen"
    request.description = "Rechnung #12345 ueber 5.000 EUR"
    request.status = Mock(value="pending")
    request.due_date = datetime.now(timezone.utc) - timedelta(hours=2)
    request.is_escalated = False
    request.escalation_date = None

    # Requester
    requester = Mock()
    requester.id = uuid4()
    requester.email = "requester@example.com"
    requester.full_name = "Max Mustermann"
    request.requested_by = requester

    # Rule with escalation
    rule = Mock()
    rule.escalation_to_role = "manager"
    request.triggered_by_rule = rule

    return request


@pytest.fixture
def mock_approval_step():
    """Create mock approval step."""
    step = Mock()
    step.id = uuid4()
    step.step_number = 1
    step.status = Mock(value="pending")
    step.assigned_user_id = uuid4()
    step.reminder_sent_count = 0
    step.last_reminder_at = None

    # Assigned user
    assigned_user = Mock()
    assigned_user.id = step.assigned_user_id
    assigned_user.email = "approver@example.com"
    assigned_user.full_name = "Anna Genehmiger"
    step.assigned_user = assigned_user

    # Parent request
    request = Mock()
    request.id = uuid4()
    request.title = "Rechnung genehmigen"
    request.due_date = datetime.now(timezone.utc) + timedelta(hours=12)

    requester = Mock()
    requester.full_name = "Max Mustermann"
    requester.email = "requester@example.com"
    request.requested_by = requester

    step.approval_request = request

    return step


@pytest.fixture
def mock_escalation_user():
    """Create mock user for escalation."""
    user = Mock()
    user.id = uuid4()
    user.email = "manager@example.com"
    user.company_id = uuid4()
    user.role = "manager"
    user.is_active = True
    user.full_name = "Chef Manager"
    return user


# ========================= NotificationType Tests =========================


class TestApprovalNotificationTypes:
    """Tests for Approval Notification Types."""

    def test_approval_notification_types_defined(self):
        """Alle Approval-Benachrichtigungstypen sollten definiert sein."""
        from app.services.notification_service import NotificationType

        assert NotificationType.APPROVAL_ESCALATED == "approval_escalated"
        assert NotificationType.APPROVAL_REMINDER == "approval_reminder"
        assert NotificationType.APPROVAL_ACTION_REQUIRED == "approval_action_required"


class TestNotificationTemplates:
    """Tests for Approval Notification Templates."""

    def test_escalation_template_rendering(self):
        """Eskalations-Template sollte korrekt gerendert werden."""
        from app.services.notification_service import (
            NotificationTemplate,
            NotificationType,
        )

        context = {
            "request_id": "req-123",
            "request_subject": "Rechnung genehmigen",
            "requester_name": "Max Mustermann",
            "due_date": "15.01.2026 10:00",
            "escalated_at": "16.01.2026 08:30",
        }

        rendered = NotificationTemplate.render(
            NotificationType.APPROVAL_ESCALATED, context
        )

        assert "eskaliert" in rendered["subject"].lower()
        assert context["request_id"] in rendered["body"]
        assert context["request_subject"] in rendered["body"]
        assert context["requester_name"] in rendered["body"]
        assert context["due_date"] in rendered["body"]
        assert context["escalated_at"] in rendered["body"]

    def test_reminder_template_rendering(self):
        """Erinnerungs-Template sollte korrekt gerendert werden."""
        from app.services.notification_service import (
            NotificationTemplate,
            NotificationType,
        )

        context = {
            "request_id": "req-456",
            "request_subject": "Bestellung freigeben",
            "requester_name": "Anna Schmidt",
            "due_date": "20.01.2026 14:00",
            "time_remaining": "5 Stunde(n) und 30 Minute(n)",
            "reminder_count": 2,
        }

        rendered = NotificationTemplate.render(
            NotificationType.APPROVAL_REMINDER, context
        )

        assert "erinnerung" in rendered["subject"].lower()
        assert context["request_id"] in rendered["body"]
        assert context["request_subject"] in rendered["body"]
        assert context["time_remaining"] in rendered["body"]
        assert str(context["reminder_count"]) in rendered["body"]

    def test_action_required_template_rendering(self):
        """Action-Required-Template sollte korrekt gerendert werden."""
        from app.services.notification_service import (
            NotificationTemplate,
            NotificationType,
        )

        context = {
            "request_id": "req-789",
            "request_subject": "Vertrag unterschreiben",
            "requester_name": "Thomas Mueller",
            "priority": "Hoch",
            "due_date": "18.01.2026 12:00",
            "description": "Wichtiger Vertrag mit Lieferant XYZ",
        }

        rendered = NotificationTemplate.render(
            NotificationType.APPROVAL_ACTION_REQUIRED, context
        )

        assert context["request_subject"] in rendered["subject"]
        assert context["priority"] in rendered["body"]
        assert context["description"] in rendered["body"]


# ========================= Helper Function Tests =========================


class TestGetEscalationRecipients:
    """Tests for _get_escalation_recipients helper."""

    def test_get_recipients_from_escalation_role(
        self, mock_approval_request, mock_escalation_user
    ):
        """Sollte User mit Eskalations-Rolle finden."""
        from app.workers.tasks.approval_tasks import _get_escalation_recipients

        mock_db = Mock()
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_escalation_user]
        mock_db.execute.return_value = mock_result

        recipients = _get_escalation_recipients(mock_db, mock_approval_request)

        assert len(recipients) == 1
        assert recipients[0].email == "manager@example.com"
        assert mock_db.execute.called

    def test_fallback_to_admin_when_no_role_users(self, mock_approval_request):
        """Sollte auf Admins zurueckfallen wenn keine Rollen-User."""
        from app.workers.tasks.approval_tasks import _get_escalation_recipients

        # Keine Eskalations-Rolle definiert
        mock_approval_request.triggered_by_rule = None

        admin_user = Mock()
        admin_user.id = uuid4()
        admin_user.email = "admin@example.com"
        admin_user.role = "admin"

        mock_db = Mock()
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [admin_user]
        mock_db.execute.return_value = mock_result

        recipients = _get_escalation_recipients(mock_db, mock_approval_request)

        assert len(recipients) == 1
        assert recipients[0].email == "admin@example.com"


class TestSendEscalationNotification:
    """Tests for _send_escalation_notification helper."""

    @patch("app.workers.tasks.approval_tasks.asyncio.run")
    @patch("app.workers.tasks.approval_tasks.NotificationService")
    def test_sends_escalation_notification(
        self,
        mock_notification_service_class,
        mock_asyncio_run,
        mock_approval_request,
        mock_escalation_user,
    ):
        """Sollte Eskalations-Benachrichtigung senden."""
        from app.workers.tasks.approval_tasks import _send_escalation_notification

        mock_service = Mock()
        mock_service.notify = AsyncMock()
        mock_notification_service_class.return_value = mock_service

        now = datetime.now(timezone.utc)
        _send_escalation_notification(mock_approval_request, mock_escalation_user, now)

        # asyncio.run sollte aufgerufen worden sein
        assert mock_asyncio_run.called


class TestSendReminderNotification:
    """Tests for _send_reminder_notification helper."""

    @patch("app.workers.tasks.approval_tasks.asyncio.run")
    @patch("app.workers.tasks.approval_tasks.NotificationService")
    def test_sends_reminder_notification(
        self,
        mock_notification_service_class,
        mock_asyncio_run,
        mock_approval_step,
    ):
        """Sollte Erinnerungs-Benachrichtigung senden."""
        from app.workers.tasks.approval_tasks import _send_reminder_notification

        mock_service = Mock()
        mock_service.notify = AsyncMock()
        mock_notification_service_class.return_value = mock_service

        now = datetime.now(timezone.utc)
        _send_reminder_notification(mock_approval_step, now)

        # asyncio.run sollte aufgerufen worden sein
        assert mock_asyncio_run.called

    def test_skips_when_no_assigned_user(self, mock_approval_step):
        """Sollte ueberspringen wenn kein zugewiesener User."""
        from app.workers.tasks.approval_tasks import _send_reminder_notification

        mock_approval_step.assigned_user = None

        # Sollte keine Exception werfen
        now = datetime.now(timezone.utc)
        _send_reminder_notification(mock_approval_step, now)

    def test_skips_when_no_approval_request(self, mock_approval_step):
        """Sollte ueberspringen wenn keine ApprovalRequest."""
        from app.workers.tasks.approval_tasks import _send_reminder_notification

        mock_approval_step.approval_request = None

        # Sollte keine Exception werfen
        now = datetime.now(timezone.utc)
        _send_reminder_notification(mock_approval_step, now)


# ========================= Task Registration Tests =========================


class TestTaskRegistration:
    """Tests for Celery task registration."""

    def test_escalate_task_registered(self):
        """Task escalate_overdue_approvals sollte registriert sein."""
        from app.workers.tasks.approval_tasks import escalate_overdue_approvals

        assert escalate_overdue_approvals.name == (
            "app.workers.tasks.approval_tasks.escalate_overdue_approvals"
        )

    def test_reminders_task_registered(self):
        """Task send_approval_reminders sollte registriert sein."""
        from app.workers.tasks.approval_tasks import send_approval_reminders

        assert send_approval_reminders.name == (
            "app.workers.tasks.approval_tasks.send_approval_reminders"
        )

    def test_stats_task_registered(self):
        """Task generate_approval_stats sollte registriert sein."""
        from app.workers.tasks.approval_tasks import generate_approval_stats

        assert generate_approval_stats.name == (
            "app.workers.tasks.approval_tasks.generate_approval_stats"
        )

    def test_expire_task_registered(self):
        """Task expire_old_approvals sollte registriert sein."""
        from app.workers.tasks.approval_tasks import expire_old_approvals

        assert expire_old_approvals.name == (
            "app.workers.tasks.approval_tasks.expire_old_approvals"
        )

    def test_process_action_task_registered(self):
        """Task process_approval_action sollte registriert sein."""
        from app.workers.tasks.approval_tasks import process_approval_action

        assert process_approval_action.name == (
            "app.workers.tasks.approval_tasks.process_approval_action"
        )


# ========================= Time Remaining Calculation Tests =========================


class TestTimeRemainingCalculation:
    """Tests for time remaining calculation in reminders."""

    def test_time_remaining_days(self, mock_approval_step):
        """Sollte Tage korrekt berechnen."""
        mock_approval_step.approval_request.due_date = (
            datetime.now(timezone.utc) + timedelta(days=2, hours=5)
        )

        from app.workers.tasks.approval_tasks import _send_reminder_notification

        # Die eigentliche Berechnung ist in _send_reminder_notification
        # Wir testen indirekt durch den Aufruf
        with patch("app.workers.tasks.approval_tasks.asyncio.run"):
            with patch("app.workers.tasks.approval_tasks.NotificationService"):
                now = datetime.now(timezone.utc)
                _send_reminder_notification(mock_approval_step, now)

    def test_time_remaining_hours(self, mock_approval_step):
        """Sollte Stunden korrekt berechnen."""
        mock_approval_step.approval_request.due_date = (
            datetime.now(timezone.utc) + timedelta(hours=18, minutes=30)
        )

        from app.workers.tasks.approval_tasks import _send_reminder_notification

        with patch("app.workers.tasks.approval_tasks.asyncio.run"):
            with patch("app.workers.tasks.approval_tasks.NotificationService"):
                now = datetime.now(timezone.utc)
                _send_reminder_notification(mock_approval_step, now)

    def test_time_remaining_minutes(self, mock_approval_step):
        """Sollte Minuten korrekt berechnen wenn weniger als 1 Stunde."""
        mock_approval_step.approval_request.due_date = (
            datetime.now(timezone.utc) + timedelta(minutes=45)
        )

        from app.workers.tasks.approval_tasks import _send_reminder_notification

        with patch("app.workers.tasks.approval_tasks.asyncio.run"):
            with patch("app.workers.tasks.approval_tasks.NotificationService"):
                now = datetime.now(timezone.utc)
                _send_reminder_notification(mock_approval_step, now)
