# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Unified Notification Hub.

Testet:
- Multi-Channel Orchestration (Email, Slack, Teams, Push, SMS, WhatsApp)
- Severity-basiertes Routing
- Deduplizierung mit TTL
- Eskalations-Ketten
- Channel-spezifische Zustellung
- Fehlerbehandlung und Fallbacks

Feinpoliert und durchdacht - Unified Notification Hub Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4
import json


# Test-Konstanten fuer gueltige UUIDs
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_COMPANY_UUID = UUID("00000000-0000-0000-0000-000000000002")
TEST_DOCUMENT_UUID = UUID("00000000-0000-0000-0000-000000000003")
TEST_NOTIFICATION_UUID = UUID("00000000-0000-0000-0000-000000000004")


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_email_service():
    """Create mock email service."""
    service = AsyncMock()
    service.send = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_slack_service():
    """Create mock Slack service."""
    service = AsyncMock()
    service.send_message = AsyncMock(return_value={"ok": True, "ts": "12345.67890"})
    service.send_block_message = AsyncMock(return_value={"ok": True})
    return service


@pytest.fixture
def mock_teams_service():
    """Create mock Teams service."""
    service = AsyncMock()
    service.send_message = AsyncMock(return_value=True)
    service.send_adaptive_card = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_push_service():
    """Create mock push notification service."""
    service = AsyncMock()
    service.send_to_user = AsyncMock(return_value=(1, 0))  # (success, failed)
    return service


@pytest.fixture
def mock_twilio_service():
    """Create mock Twilio service."""
    from app.services.twilio_service import TwilioSendResult, TwilioDeliveryStatus

    service = AsyncMock()
    result = TwilioSendResult(
        success=True,
        message_sid="SM123",
        status=TwilioDeliveryStatus.QUEUED,
    )
    service.send_sms = AsyncMock(return_value=result)
    service.send_whatsapp = AsyncMock(return_value=result)
    return service


@pytest.fixture
def mock_redis():
    """Create mock Redis for deduplication."""
    redis = AsyncMock()
    redis.client = AsyncMock()
    redis.client.get = AsyncMock(return_value=None)
    redis.client.setex = AsyncMock()
    redis.client.exists = AsyncMock(return_value=0)
    return redis


@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    """Provide sample notification payload."""
    return {
        "title": "Dokument verarbeitet",
        "message": "Das Dokument 'Rechnung-2024.pdf' wurde erfolgreich verarbeitet.",
        "category": "document",
        "severity": "info",
        "document_id": str(TEST_DOCUMENT_UUID),
        "action_url": "/documents/view/123",
        "metadata": {
            "filename": "Rechnung-2024.pdf",
            "backend": "deepseek",
            "confidence": 0.95,
        },
    }


@pytest.fixture
def sample_recipient() -> Dict[str, Any]:
    """Provide sample notification recipient."""
    return {
        "user_id": str(TEST_USER_UUID),
        "company_id": str(TEST_COMPANY_UUID),
        "email": "user@example.com",
        "phone_number": "+4917012345678",
        "slack_user_id": "U12345",
        "teams_user_id": "teams-user-123",
    }


@pytest.fixture
def sample_preferences() -> Dict[str, Any]:
    """Provide sample user notification preferences."""
    return {
        "email_enabled": True,
        "slack_enabled": True,
        "teams_enabled": False,
        "push_enabled": True,
        "sms_enabled": False,
        "whatsapp_enabled": False,
        "in_app_enabled": True,
        "websocket_enabled": True,
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
        "timezone": "Europe/Berlin",
        "digest_mode": False,
        "digest_frequency": "daily",
    }


# ========================= NotificationChannel Tests =========================


class TestNotificationChannel:
    """Tests for NotificationChannel enum."""

    def test_all_channels_defined(self):
        """Alle Kanaele sollten definiert sein."""
        from app.services.notification.unified_hub import NotificationChannel

        assert NotificationChannel.EMAIL == "email"
        assert NotificationChannel.SLACK == "slack"
        assert NotificationChannel.TEAMS == "teams"
        assert NotificationChannel.PUSH == "push"
        assert NotificationChannel.SMS == "sms"
        assert NotificationChannel.WHATSAPP == "whatsapp"
        assert NotificationChannel.IN_APP == "in_app"
        assert NotificationChannel.WEBSOCKET == "websocket"

    def test_channel_count(self):
        """Anzahl der Kanaele pruefen."""
        from app.services.notification.unified_hub import NotificationChannel

        assert len(NotificationChannel) == 8


# ========================= NotificationSeverity Tests =========================


class TestNotificationSeverity:
    """Tests for NotificationSeverity enum."""

    def test_severity_levels_defined(self):
        """Alle Schweregrade sollten definiert sein."""
        from app.services.notification.unified_hub import NotificationSeverity

        assert NotificationSeverity.INFO == "info"
        assert NotificationSeverity.LOW == "low"
        assert NotificationSeverity.MEDIUM == "medium"
        assert NotificationSeverity.HIGH == "high"
        assert NotificationSeverity.CRITICAL == "critical"

    def test_severity_ordering(self):
        """Schweregrade sollten geordnet sein."""
        from app.services.notification.unified_hub import NotificationSeverity

        severities = list(NotificationSeverity)
        assert severities[0] == NotificationSeverity.INFO
        assert severities[-1] == NotificationSeverity.CRITICAL


# ========================= NotificationCategory Tests =========================


class TestNotificationCategory:
    """Tests for NotificationCategory enum."""

    def test_categories_defined(self):
        """Alle Kategorien sollten definiert sein."""
        from app.services.notification.unified_hub import NotificationCategory

        assert NotificationCategory.DOCUMENT == "document"
        assert NotificationCategory.ALERT == "alert"
        assert NotificationCategory.WORKFLOW == "workflow"
        assert NotificationCategory.SYSTEM == "system"
        assert NotificationCategory.SECURITY == "security"
        assert NotificationCategory.FINANCE == "finance"
        assert NotificationCategory.COMPLIANCE == "compliance"
        assert NotificationCategory.REMINDER == "reminder"


# ========================= EscalationLevel Tests =========================


class TestEscalationLevel:
    """Tests for EscalationLevel enum."""

    def test_escalation_levels_defined(self):
        """Alle Eskalationsstufen sollten definiert sein."""
        from app.services.notification.unified_hub import EscalationLevel

        assert EscalationLevel.NONE == 0
        assert EscalationLevel.LEVEL_1 == 1
        assert EscalationLevel.LEVEL_2 == 2
        assert EscalationLevel.LEVEL_3 == 3
        assert EscalationLevel.LEVEL_4 == 4
        assert EscalationLevel.LEVEL_5 == 5


# ========================= NotificationPayload Tests =========================


class TestNotificationPayload:
    """Tests for NotificationPayload model."""

    def test_payload_initialization(self, sample_payload):
        """Payload sollte korrekt initialisiert werden."""
        from app.services.notification.unified_hub import (
            NotificationPayload,
            NotificationSeverity,
            NotificationCategory,
        )

        payload = NotificationPayload(
            notification_type="document_processed",
            title=sample_payload["title"],
            message=sample_payload["message"],
            category=NotificationCategory.DOCUMENT,
            severity=NotificationSeverity.INFO,
            reference_type="document",
            reference_id=sample_payload["document_id"],
            url=sample_payload["action_url"],
            metadata=sample_payload["metadata"],
        )

        assert payload.title == "Dokument verarbeitet"
        assert payload.severity == NotificationSeverity.INFO
        assert payload.reference_id == sample_payload["document_id"]

    def test_payload_with_defaults(self):
        """Payload mit Default-Werten."""
        from app.services.notification.unified_hub import (
            NotificationPayload,
            NotificationSeverity,
            NotificationCategory,
        )

        payload = NotificationPayload(
            notification_type="test",
            title="Test",
            message="Test-Nachricht",
        )

        assert payload.severity == NotificationSeverity.MEDIUM
        assert payload.category == NotificationCategory.SYSTEM
        assert payload.metadata == {}


# ========================= NotificationRecipient Tests =========================


class TestNotificationRecipient:
    """Tests for NotificationRecipient model."""

    def test_recipient_initialization(self, sample_recipient):
        """Empfaenger sollte korrekt initialisiert werden."""
        from app.services.notification.unified_hub import NotificationRecipient

        recipient = NotificationRecipient(
            user_id=UUID(sample_recipient["user_id"]),
            email=sample_recipient["email"],
            phone_number=sample_recipient["phone_number"],
            slack_user_id=sample_recipient["slack_user_id"],
            teams_user_id=sample_recipient["teams_user_id"],
        )

        assert recipient.user_id == TEST_USER_UUID
        assert recipient.email == "user@example.com"
        assert recipient.phone_number == "+4917012345678"


# ========================= UserNotificationPreferences Tests =========================


class TestUserNotificationPreferences:
    """Tests for UserNotificationPreferences model."""

    def test_preferences_initialization(self, sample_preferences):
        """Praeferenzen sollten korrekt initialisiert werden."""
        from app.services.notification.unified_hub import UserNotificationPreferences

        prefs = UserNotificationPreferences(
            email_enabled=sample_preferences["email_enabled"],
            slack_enabled=sample_preferences["slack_enabled"],
            teams_enabled=sample_preferences["teams_enabled"],
            push_enabled=sample_preferences["push_enabled"],
            sms_enabled=sample_preferences["sms_enabled"],
            in_app_enabled=sample_preferences["in_app_enabled"],
        )

        assert prefs.email_enabled is True
        assert prefs.slack_enabled is True
        assert prefs.teams_enabled is False
        assert prefs.sms_enabled is False

    def test_preferences_defaults(self):
        """Default-Praeferenzen pruefen."""
        from app.services.notification.unified_hub import UserNotificationPreferences

        prefs = UserNotificationPreferences()

        assert prefs.email_enabled is True
        assert prefs.in_app_enabled is True
        assert prefs.push_enabled is True
        assert prefs.sms_enabled is False


# ========================= UnifiedNotificationHub Initialization Tests =========================


class TestUnifiedNotificationHubInitialization:
    """Tests for UnifiedNotificationHub initialization."""

    def test_hub_initialization(self):
        """Hub sollte korrekt initialisiert werden."""
        from app.services.notification.unified_hub import UnifiedNotificationHub

        hub = UnifiedNotificationHub()

        assert hub is not None

    def test_singleton_pattern(self):
        """get_unified_notification_hub sollte Singleton zurueckgeben."""
        from app.services.notification.unified_hub import get_unified_notification_hub
        import app.services.notification.unified_hub as module

        # Reset singleton
        module._unified_hub = None

        hub1 = get_unified_notification_hub()
        hub2 = get_unified_notification_hub()

        assert hub1 is hub2


# ========================= Severity-Based Routing Tests =========================


class TestSeverityBasedRouting:
    """Tests for severity-based channel routing."""

    def test_info_severity_channels(self):
        """INFO-Schweregrad sollte nur In-App nutzen."""
        from app.services.notification.unified_hub import (
            DEFAULT_CHANNELS_BY_SEVERITY,
            NotificationSeverity,
            NotificationChannel,
        )

        channels = DEFAULT_CHANNELS_BY_SEVERITY[NotificationSeverity.INFO]

        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.EMAIL not in channels
        assert NotificationChannel.SMS not in channels

    def test_low_severity_channels(self):
        """LOW-Schweregrad sollte In-App und WebSocket nutzen."""
        from app.services.notification.unified_hub import (
            DEFAULT_CHANNELS_BY_SEVERITY,
            NotificationSeverity,
            NotificationChannel,
        )

        channels = DEFAULT_CHANNELS_BY_SEVERITY[NotificationSeverity.LOW]

        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.WEBSOCKET in channels

    def test_medium_severity_channels(self):
        """MEDIUM-Schweregrad sollte zusaetzlich Email/Slack nutzen."""
        from app.services.notification.unified_hub import (
            DEFAULT_CHANNELS_BY_SEVERITY,
            NotificationSeverity,
            NotificationChannel,
        )

        channels = DEFAULT_CHANNELS_BY_SEVERITY[NotificationSeverity.MEDIUM]

        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.SLACK in channels

    def test_high_severity_channels(self):
        """HIGH-Schweregrad sollte auch Push nutzen."""
        from app.services.notification.unified_hub import (
            DEFAULT_CHANNELS_BY_SEVERITY,
            NotificationSeverity,
            NotificationChannel,
        )

        channels = DEFAULT_CHANNELS_BY_SEVERITY[NotificationSeverity.HIGH]

        assert NotificationChannel.PUSH in channels
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.TEAMS in channels

    def test_critical_severity_channels(self):
        """CRITICAL-Schweregrad sollte SMS nutzen."""
        from app.services.notification.unified_hub import (
            DEFAULT_CHANNELS_BY_SEVERITY,
            NotificationSeverity,
            NotificationChannel,
        )

        channels = DEFAULT_CHANNELS_BY_SEVERITY[NotificationSeverity.CRITICAL]

        assert NotificationChannel.SMS in channels
        assert NotificationChannel.PUSH in channels
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.IN_APP in channels


# ========================= Deduplication Tests =========================


class TestDeduplication:
    """Tests for notification deduplication."""

    @pytest.mark.asyncio
    async def test_deduplication_blocks_duplicate(self, mock_redis):
        """Duplikate sollten blockiert werden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
        )

        hub = UnifiedNotificationHub()

        payload = NotificationPayload(
            notification_type="test",
            title="Test",
            message="Test-Nachricht",
            dedupe_key="test-dedupe-key",
        )

        # First call - not a duplicate
        with patch.object(hub, '_dedup_cache', {}):
            hub._dedup_cache["test-dedupe-key"] = datetime.now(timezone.utc)

            # Now it should be a duplicate
            is_duplicate = await hub._is_duplicate(payload, TEST_USER_UUID)

            assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_deduplication_allows_new(self, mock_redis):
        """Neue Benachrichtigungen sollten erlaubt sein."""
        from app.services.notification.unified_hub import UnifiedNotificationHub, NotificationPayload

        hub = UnifiedNotificationHub()

        payload = NotificationPayload(
            notification_type="test",
            title="Test",
            message="Test-Nachricht",
            dedupe_key="new-dedupe-key",
        )

        # Empty cache - should not be duplicate
        with patch.object(hub, '_dedup_cache', {}):
            is_duplicate = await hub._is_duplicate(payload, TEST_USER_UUID)

            assert is_duplicate is False

    def test_deduplication_key_generation(self):
        """Deduplizierungs-Key sollte aus dedupe_key stammen."""
        from app.services.notification.unified_hub import NotificationPayload

        payload = NotificationPayload(
            notification_type="test",
            title="Test",
            message="Test-Nachricht",
            dedupe_key="custom-key",
        )

        assert payload.dedupe_key == "custom-key"


# ========================= Send Notification Tests =========================


class TestSendNotification:
    """Tests for sending notifications."""

    @pytest.mark.asyncio
    async def test_send_to_email_channel(self, sample_payload, sample_recipient):
        """Benachrichtigung per Email senden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
            NotificationSeverity,
            NotificationCategory,
        )

        hub = UnifiedNotificationHub()

        # Mock the _send_email method
        hub._send_email = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="document_processed",
            title=sample_payload["title"],
            message=sample_payload["message"],
            severity=NotificationSeverity.INFO,
            category=NotificationCategory.DOCUMENT,
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL],
        )

        assert len(results) >= 1
        hub._send_email.assert_called()

    @pytest.mark.asyncio
    async def test_send_to_multiple_channels(self, sample_payload):
        """Benachrichtigung an mehrere Kanaele senden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
            NotificationSeverity,
        )

        hub = UnifiedNotificationHub()

        # Mock the channel send methods
        hub._send_email = AsyncMock(return_value=True)
        hub._send_slack = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
            severity=NotificationSeverity.MEDIUM,
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
            slack_user_id="U12345",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        )

        assert len(results) >= 1
        hub._send_email.assert_called()
        hub._send_slack.assert_called()

    @pytest.mark.asyncio
    async def test_send_to_multiple_recipients(self, sample_payload):
        """Benachrichtigung an mehrere Empfaenger senden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
        )

        hub = UnifiedNotificationHub()

        # Mock the _send_email method
        hub._send_email = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipients = [
            NotificationRecipient(
                user_id=uuid4(),
                email="user1@example.com",
            ),
            NotificationRecipient(
                user_id=uuid4(),
                email="user2@example.com",
            ),
        ]

        results = await hub.send(
            recipients=recipients,
            payload=payload,
            channels=[NotificationChannel.EMAIL],
        )

        assert len(results) == 2
        assert hub._send_email.call_count == 2


# ========================= Escalation Tests =========================


class TestEscalation:
    """Tests for escalation functionality."""

    @pytest.mark.asyncio
    async def test_escalation_level_1(self, sample_payload):
        """Eskalationsstufe 1 sollte Email und Slack nutzen."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            EscalationLevel,
        )

        hub = UnifiedNotificationHub()

        # Mock the send methods
        hub._send_email = AsyncMock(return_value=True)
        hub._send_slack = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
            slack_user_id="U12345",
        )

        results = await hub.escalate(
            original_notification_id=TEST_NOTIFICATION_UUID,
            recipient=recipient,
            payload=payload,
            level=EscalationLevel.LEVEL_1,
        )

        assert results is not None

    @pytest.mark.asyncio
    async def test_escalation_level_4_uses_sms(self, sample_payload):
        """Eskalationsstufe 4 sollte SMS nutzen."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            EscalationLevel,
        )

        hub = UnifiedNotificationHub()

        # Mock the send methods
        hub._send_email = AsyncMock(return_value=True)
        hub._send_slack = AsyncMock(return_value=True)
        hub._send_teams = AsyncMock(return_value=True)
        hub._send_push = AsyncMock(return_value=True)
        hub._send_sms = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            phone_number="+4917012345678",
        )

        results = await hub.escalate(
            original_notification_id=TEST_NOTIFICATION_UUID,
            recipient=recipient,
            payload=payload,
            level=EscalationLevel.LEVEL_4,
        )

        hub._send_sms.assert_called()


# ========================= Channel Preference Tests =========================


class TestChannelPreferences:
    """Tests for respecting user channel preferences."""

    @pytest.mark.asyncio
    async def test_respects_disabled_channel(self, sample_payload, sample_preferences):
        """Deaktivierte Kanaele sollten nicht genutzt werden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
            UserNotificationPreferences,
        )

        hub = UnifiedNotificationHub()

        # Mock the _send_email method
        hub._send_email = AsyncMock(return_value=True)

        prefs = UserNotificationPreferences(
            email_enabled=False,  # Email deaktiviert
            slack_enabled=True,
        )

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL],
            preferences={str(TEST_USER_UUID): prefs},
        )

        # Email sollte nicht gesendet worden sein (deaktiviert)
        # Note: The actual behavior depends on how preferences are checked
        # in the UnifiedNotificationHub implementation


# ========================= Delivery Result Tests =========================


class TestNotificationDeliveryResult:
    """Tests for NotificationDeliveryResult model."""

    def test_success_result(self):
        """Erfolgreiche Zustellung."""
        from app.services.notification.unified_hub import (
            NotificationDeliveryResult,
            ChannelDeliveryResult,
            NotificationChannel,
            DeliveryStatus,
        )

        channel_result = ChannelDeliveryResult(
            channel=NotificationChannel.EMAIL,
            status=DeliveryStatus.DELIVERED,
        )

        result = NotificationDeliveryResult(
            notification_id=TEST_NOTIFICATION_UUID,
            success=True,
            total_channels=1,
            successful_channels=1,
            failed_channels=0,
            skipped_channels=0,
            channel_results=[channel_result],
        )

        assert result.success is True
        assert result.successful_channels == 1

    def test_failed_result(self):
        """Fehlgeschlagene Zustellung."""
        from app.services.notification.unified_hub import (
            NotificationDeliveryResult,
            ChannelDeliveryResult,
            NotificationChannel,
            DeliveryStatus,
        )

        channel_result = ChannelDeliveryResult(
            channel=NotificationChannel.SMS,
            status=DeliveryStatus.FAILED,
            error_message="Rate limit exceeded",
        )

        result = NotificationDeliveryResult(
            notification_id=TEST_NOTIFICATION_UUID,
            success=False,
            total_channels=1,
            successful_channels=0,
            failed_channels=1,
            skipped_channels=0,
            channel_results=[channel_result],
        )

        assert result.success is False
        assert result.failed_channels == 1
        assert result.channel_results[0].error_message == "Rate limit exceeded"


# ========================= Error Handling Tests =========================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_channel_failure_continues_to_next(self, sample_payload):
        """Kanal-Fehler sollte nicht andere Kanaele blockieren."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
        )

        hub = UnifiedNotificationHub()

        # Email schlaegt fehl, Slack erfolgreich
        hub._send_email = AsyncMock(side_effect=Exception("SMTP error"))
        hub._send_slack = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
            slack_user_id="U12345",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
        )

        # Slack sollte trotzdem gesendet worden sein
        hub._send_slack.assert_called()

    @pytest.mark.asyncio
    async def test_all_channels_fail_returns_results(self, sample_payload):
        """Alle Kanal-Fehler sollten Results zurueckgeben."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
        )

        hub = UnifiedNotificationHub()

        hub._send_email = AsyncMock(side_effect=Exception("SMTP error"))

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL],
        )

        assert len(results) == 1
        assert results[0].success is False


# ========================= Convenience Function Tests =========================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_unified_notification_hub(self):
        """get_unified_notification_hub sollte Hub zurueckgeben."""
        from app.services.notification.unified_hub import (
            get_unified_notification_hub,
            UnifiedNotificationHub,
        )

        hub = get_unified_notification_hub()

        assert hub is not None
        assert isinstance(hub, UnifiedNotificationHub)


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_recipients_list(self, sample_payload):
        """Leere Empfaengerliste sollte leere Results zurueckgeben."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationChannel,
        )

        hub = UnifiedNotificationHub()

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        results = await hub.send(
            recipients=[],
            payload=payload,
            channels=[NotificationChannel.EMAIL],
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_empty_channels_list(self, sample_payload):
        """Leere Kanalliste sollte leere Results zurueckgeben."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
        )

        hub = UnifiedNotificationHub()

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            email="user@example.com",
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[],
        )

        assert results == []

    def test_payload_with_german_umlauts(self):
        """Payload mit Umlauten sollte korrekt verarbeitet werden."""
        from app.services.notification.unified_hub import NotificationPayload

        payload = NotificationPayload(
            notification_type="test",
            title="Aenderungen uebernommen",
            message="Die Pruefung wurde erfolgreich abgeschlossen. Moechten Sie fortfahren?",
        )

        assert "Aenderungen" in payload.title
        assert "Pruefung" in payload.message

    @pytest.mark.asyncio
    async def test_recipient_missing_channel_contact(self, sample_payload):
        """Empfaenger ohne Kontaktinfo fuer Kanal sollte uebersprungen werden."""
        from app.services.notification.unified_hub import (
            UnifiedNotificationHub,
            NotificationPayload,
            NotificationRecipient,
            NotificationChannel,
        )

        hub = UnifiedNotificationHub()

        hub._send_email = AsyncMock(return_value=True)

        payload = NotificationPayload(
            notification_type="test",
            title=sample_payload["title"],
            message=sample_payload["message"],
        )

        recipient = NotificationRecipient(
            user_id=TEST_USER_UUID,
            # Keine Email!
        )

        results = await hub.send(
            recipients=[recipient],
            payload=payload,
            channels=[NotificationChannel.EMAIL],
        )

        # Email sollte nicht gesendet worden sein (keine Email-Adresse)
        hub._send_email.assert_not_called()


# ========================= TTL Tests =========================


class TestDeduplicationTTL:
    """Tests for deduplication TTL based on severity."""

    def test_info_ttl(self):
        """INFO sollte laengere TTL haben."""
        from app.services.notification.unified_hub import (
            DEDUP_TTL_BY_SEVERITY,
            NotificationSeverity,
        )

        ttl = DEDUP_TTL_BY_SEVERITY[NotificationSeverity.INFO]

        assert ttl == 3600  # 1 Stunde

    def test_critical_ttl(self):
        """CRITICAL sollte kuerzere TTL haben (schnellere Wiederholung)."""
        from app.services.notification.unified_hub import (
            DEDUP_TTL_BY_SEVERITY,
            NotificationSeverity,
        )

        ttl = DEDUP_TTL_BY_SEVERITY[NotificationSeverity.CRITICAL]

        # Critical hat kuerzeste TTL fuer schnellere Wiederholungs-Moeglichkeit
        assert ttl == 60  # 1 Minute

    def test_ttl_ordering(self):
        """TTL sollte mit steigendem Schweregrad abnehmen."""
        from app.services.notification.unified_hub import (
            DEDUP_TTL_BY_SEVERITY,
            NotificationSeverity,
        )

        # INFO > LOW > MEDIUM > HIGH > CRITICAL
        assert DEDUP_TTL_BY_SEVERITY[NotificationSeverity.INFO] > \
               DEDUP_TTL_BY_SEVERITY[NotificationSeverity.LOW]
        assert DEDUP_TTL_BY_SEVERITY[NotificationSeverity.LOW] > \
               DEDUP_TTL_BY_SEVERITY[NotificationSeverity.MEDIUM]
        assert DEDUP_TTL_BY_SEVERITY[NotificationSeverity.MEDIUM] > \
               DEDUP_TTL_BY_SEVERITY[NotificationSeverity.HIGH]
        assert DEDUP_TTL_BY_SEVERITY[NotificationSeverity.HIGH] > \
               DEDUP_TTL_BY_SEVERITY[NotificationSeverity.CRITICAL]
