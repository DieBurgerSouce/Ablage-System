# -*- coding: utf-8 -*-
"""
Unit-Tests für Notification Service.

Testet:
- Email-Benachrichtigungen (SMTP)
- Webhook-Benachrichtigungen
- In-App-Benachrichtigungen (Redis)
- Notification Templates
- Kanal-Koordination
- Fehlerbehandlung

Feinpoliert und durchdacht - Benachrichtigungs-Tests.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json


# Test-Konstanten fuer gueltige UUIDs (Service erfordert UUID-Validierung)
TEST_USER_UUID = "00000000-0000-0000-0000-000000000001"


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_smtp():
    """Create mock SMTP server."""
    smtp = Mock()
    smtp.__enter__ = Mock(return_value=smtp)
    smtp.__exit__ = Mock(return_value=False)
    smtp.starttls = Mock()
    smtp.login = Mock()
    smtp.send_message = Mock()
    return smtp


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.client = AsyncMock()
    redis.client.lpush = AsyncMock()
    redis.client.ltrim = AsyncMock()
    redis.client.expire = AsyncMock()
    redis.client.lrange = AsyncMock(return_value=[])
    redis.client.lset = AsyncMock()
    return redis


@pytest.fixture
def sample_context() -> Dict[str, Any]:
    """Provide sample notification context."""
    return {
        "document_id": "doc-123",
        "filename": "test_document.pdf",
        "backend": "deepseek",
        "processing_time": "1.5s",
        "confidence": 95.5,
        "word_count": 250,
        "entity_count": 5,
        "umlauts_valid": "Ja",
    }


@pytest.fixture
def sample_error_context() -> Dict[str, Any]:
    """Provide sample error context."""
    return {
        "document_id": "doc-123",
        "filename": "test_document.pdf",
        "error_message": "OCR-Verarbeitung fehlgeschlagen",
        "failed_at": "29.11.2024 10:30:00",
    }


# ========================= NotificationType Tests =========================


class TestNotificationType:
    """Tests for NotificationType constants."""

    def test_notification_types_defined(self):
        """Alle Benachrichtigungstypen sollten definiert sein."""
        from app.services.notification_service import NotificationType

        assert NotificationType.PROCESSING_STARTED == "processing_started"
        assert NotificationType.PROCESSING_COMPLETED == "processing_completed"
        assert NotificationType.PROCESSING_FAILED == "processing_failed"
        assert NotificationType.OCR_QUALITY_WARNING == "ocr_quality_warning"
        assert NotificationType.GERMAN_VALIDATION_WARNING == "german_validation_warning"
        assert NotificationType.BATCH_COMPLETED == "batch_completed"
        assert NotificationType.SYSTEM_ALERT == "system_alert"

    def test_approval_notification_types_defined(self):
        """Approval-Benachrichtigungstypen sollten definiert sein."""
        from app.services.notification_service import NotificationType

        assert NotificationType.APPROVAL_ESCALATED == "approval_escalated"
        assert NotificationType.APPROVAL_REMINDER == "approval_reminder"
        assert NotificationType.APPROVAL_ACTION_REQUIRED == "approval_action_required"


class TestNotificationChannel:
    """Tests for NotificationChannel constants."""

    def test_notification_channels_defined(self):
        """Alle Kanäle sollten definiert sein."""
        from app.services.notification_service import NotificationChannel

        assert NotificationChannel.EMAIL == "email"
        assert NotificationChannel.WEBHOOK == "webhook"
        assert NotificationChannel.WEBSOCKET == "websocket"
        assert NotificationChannel.IN_APP == "in_app"


# ========================= NotificationTemplate Tests =========================


class TestNotificationTemplate:
    """Tests for NotificationTemplate class."""

    def test_render_processing_completed(self, sample_context):
        """Template für abgeschlossene Verarbeitung rendern."""
        from app.services.notification_service import NotificationTemplate, NotificationType

        result = NotificationTemplate.render(
            NotificationType.PROCESSING_COMPLETED,
            sample_context
        )

        assert "subject" in result
        assert "body" in result
        assert "erfolgreich abgeschlossen" in result["subject"]
        assert sample_context["document_id"] in result["body"]
        assert sample_context["filename"] in result["body"]

    def test_render_processing_failed(self, sample_error_context):
        """Template für fehlgeschlagene Verarbeitung rendern."""
        from app.services.notification_service import NotificationTemplate, NotificationType

        result = NotificationTemplate.render(
            NotificationType.PROCESSING_FAILED,
            sample_error_context
        )

        assert "fehlgeschlagen" in result["subject"]
        assert sample_error_context["error_message"] in result["body"]

    def test_render_missing_template_key(self):
        """Fehlende Template-Schlüssel sollten behandelt werden."""
        from app.services.notification_service import NotificationTemplate, NotificationType

        # Context with missing keys
        incomplete_context = {"document_id": "doc-123"}

        result = NotificationTemplate.render(
            NotificationType.PROCESSING_COMPLETED,
            incomplete_context
        )

        # Should not raise, should return original template
        assert "subject" in result
        assert "body" in result

    def test_render_unknown_notification_type(self):
        """Unbekannter Benachrichtigungstyp sollte Fallback verwenden."""
        from app.services.notification_service import NotificationTemplate

        result = NotificationTemplate.render(
            "unknown_type",
            {}
        )

        assert "Ablage-System Benachrichtigung" in result["subject"]

    def test_template_contains_german_text(self, sample_context):
        """Templates sollten auf Deutsch sein."""
        from app.services.notification_service import NotificationTemplate, NotificationType

        result = NotificationTemplate.render(
            NotificationType.PROCESSING_COMPLETED,
            sample_context
        )

        # Check for German phrases
        assert "Sehr geehrter Benutzer" in result["body"]
        assert "Mit freundlichen Grüßen" in result["body"]


# ========================= EmailNotifier Tests =========================


class TestEmailNotifier:
    """Tests for EmailNotifier class."""

    def test_email_notifier_initialization(self):
        """EmailNotifier sollte korrekt initialisiert werden."""
        from app.services.notification_service import EmailNotifier

        notifier = EmailNotifier(
            smtp_host="smtp.test.local",
            smtp_port=587,
            smtp_user="test@test.local",
            smtp_password="password",
            from_email="noreply@test.local"
        )

        assert notifier.smtp_host == "smtp.test.local"
        assert notifier.smtp_port == 587
        assert notifier.is_configured is True

    def test_email_notifier_not_configured(self):
        """EmailNotifier ohne Konfiguration."""
        from app.services.notification_service import EmailNotifier

        notifier = EmailNotifier(
            smtp_host=None,
            smtp_user=None,
            smtp_password=None
        )

        assert notifier.is_configured is False

    @pytest.mark.asyncio
    async def test_send_email_success(self, mock_smtp):
        """E-Mail erfolgreich senden."""
        from app.services.notification_service import EmailNotifier

        with patch('smtplib.SMTP', return_value=mock_smtp):
            notifier = EmailNotifier(
                smtp_host="smtp.test.local",
                smtp_port=587,
                smtp_user="test@test.local",
                smtp_password="password"
            )

            result = await notifier.send(
                to_email="user@test.local",
                subject="Test Betreff",
                body="Test Nachricht"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_email_not_configured(self):
        """E-Mail-Versand ohne Konfiguration sollte False zurückgeben."""
        from app.services.notification_service import EmailNotifier

        notifier = EmailNotifier(smtp_host=None, smtp_user=None, smtp_password=None)

        result = await notifier.send(
            to_email="user@test.local",
            subject="Test",
            body="Test"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_email_with_html_body(self, mock_smtp):
        """E-Mail mit HTML-Inhalt senden."""
        from app.services.notification_service import EmailNotifier

        with patch('smtplib.SMTP', return_value=mock_smtp):
            notifier = EmailNotifier(
                smtp_host="smtp.test.local",
                smtp_port=587,
                smtp_user="test@test.local",
                smtp_password="password"
            )

            result = await notifier.send(
                to_email="user@test.local",
                subject="Test",
                body="Plain text",
                html_body="<html><body>HTML content</body></html>"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_email_failure(self, mock_smtp):
        """E-Mail-Versandfehler sollte False zurückgeben."""
        from app.services.notification_service import EmailNotifier

        mock_smtp.send_message.side_effect = Exception("SMTP error")

        with patch('smtplib.SMTP', return_value=mock_smtp):
            notifier = EmailNotifier(
                smtp_host="smtp.test.local",
                smtp_port=587,
                smtp_user="test@test.local",
                smtp_password="password"
            )

            result = await notifier.send(
                to_email="user@test.local",
                subject="Test",
                body="Test"
            )

            assert result is False


# ========================= WebhookNotifier Tests =========================


class TestWebhookNotifier:
    """Tests for WebhookNotifier class."""

    def test_webhook_notifier_initialization(self):
        """WebhookNotifier sollte korrekt initialisiert werden."""
        from app.services.notification_service import WebhookNotifier

        notifier = WebhookNotifier(
            default_webhook_url="https://webhook.test.local/notify",
            secret_key="test-secret"
        )

        assert notifier.default_webhook_url == "https://webhook.test.local/notify"
        assert notifier.secret_key == "test-secret"

    @pytest.mark.asyncio
    async def test_send_webhook_success(self):
        """Webhook erfolgreich senden."""
        from app.services.notification_service import WebhookNotifier

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch('httpx.AsyncClient') as MockClient, \
             patch('app.core.security.validate_url_for_ssrf_async',
                   new_callable=AsyncMock, return_value=(True, None)):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            notifier = WebhookNotifier()

            result = await notifier.send(
                webhook_url="https://webhook.test.local/notify",
                payload={"event": "test"}
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_send_webhook_no_url(self):
        """Webhook ohne URL sollte False zurückgeben."""
        from app.services.notification_service import WebhookNotifier

        notifier = WebhookNotifier()

        result = await notifier.send(
            webhook_url=None,
            payload={"event": "test"}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_with_signature(self):
        """Webhook mit Signatur senden."""
        from app.services.notification_service import WebhookNotifier

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        with patch('httpx.AsyncClient') as MockClient, \
             patch('app.core.security.validate_url_for_ssrf_async',
                   new_callable=AsyncMock, return_value=(True, None)):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            notifier = WebhookNotifier(secret_key="test-secret")

            result = await notifier.send(
                webhook_url="https://webhook.test.local/notify",
                payload={"event": "test"}
            )

            assert result is True
            # Verify signature header was added
            call_kwargs = mock_client.post.call_args.kwargs
            assert "X-Ablage-System-Signature" in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_send_webhook_http_error(self):
        """Webhook HTTP-Fehler sollte False zurückgeben."""
        from app.services.notification_service import WebhookNotifier
        import httpx

        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 500
            mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Internal Server Error",
                request=Mock(),
                response=mock_response
            ))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_client

            notifier = WebhookNotifier()

            result = await notifier.send(
                webhook_url="https://webhook.test.local/notify",
                payload={"event": "test"}
            )

            assert result is False


# ========================= InAppNotificationStore Tests =========================


class TestInAppNotificationStore:
    """Tests for InAppNotificationStore class."""

    @pytest.mark.asyncio
    async def test_store_notification(self, mock_redis):
        """Benachrichtigung speichern."""
        from app.services.notification_service import InAppNotificationStore

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            notification_id = await store.store(
                user_id=TEST_USER_UUID,
                notification={
                    "type": "processing_completed",
                    "title": "Verarbeitung abgeschlossen",
                    "message": "Ihr Dokument wurde verarbeitet"
                }
            )

            assert notification_id is not None
            mock_redis.client.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_notifications(self, mock_redis):
        """Benachrichtigungen abrufen."""
        from app.services.notification_service import InAppNotificationStore

        stored_notification = json.dumps({
            "id": "notif-123",
            "user_id": TEST_USER_UUID,
            "type": "test",
            "read": False
        })
        mock_redis.client.lrange.return_value = [stored_notification]

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            notifications = await store.get_notifications(TEST_USER_UUID)

            assert len(notifications) == 1
            assert notifications[0]["id"] == "notif-123"

    @pytest.mark.asyncio
    async def test_get_notifications_unread_only(self, mock_redis):
        """Nur ungelesene Benachrichtigungen abrufen."""
        from app.services.notification_service import InAppNotificationStore

        notifications = [
            json.dumps({"id": "1", "read": False}),
            json.dumps({"id": "2", "read": True}),
            json.dumps({"id": "3", "read": False}),
        ]
        mock_redis.client.lrange.return_value = notifications

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            result = await store.get_notifications(TEST_USER_UUID, unread_only=True)

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_mark_read(self, mock_redis):
        """Benachrichtigung als gelesen markieren."""
        from app.services.notification_service import InAppNotificationStore

        stored_notification = json.dumps({
            "id": "notif-123",
            "read": False
        })
        mock_redis.client.lrange.return_value = [stored_notification]

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            result = await store.mark_read(TEST_USER_UUID, "notif-123")

            assert result is True
            mock_redis.client.lset.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self, mock_redis):
        """Nicht existierende Benachrichtigung markieren."""
        from app.services.notification_service import InAppNotificationStore

        mock_redis.client.lrange.return_value = []

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            result = await store.mark_read(TEST_USER_UUID, "nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_unread_count(self, mock_redis):
        """Anzahl ungelesener Benachrichtigungen."""
        from app.services.notification_service import InAppNotificationStore

        notifications = [
            json.dumps({"id": "1", "read": False}),
            json.dumps({"id": "2", "read": False}),
            json.dumps({"id": "3", "read": True}),
        ]
        mock_redis.client.lrange.return_value = notifications

        store = InAppNotificationStore()

        with patch.object(store, '_get_redis', return_value=mock_redis):
            count = await store.get_unread_count(TEST_USER_UUID)

            assert count == 2


# ========================= NotificationService Tests =========================


class TestNotificationService:
    """Tests for NotificationService class."""

    def test_notification_service_initialization(self):
        """NotificationService sollte korrekt initialisiert werden."""
        from app.services.notification_service import NotificationService

        service = NotificationService()

        assert service.email is not None
        assert service.webhook is not None
        assert service.in_app is not None

    @pytest.mark.asyncio
    async def test_notify_all_channels(self, sample_context, mock_redis):
        """Benachrichtigung an alle Kanäle senden."""
        from app.services.notification_service import (
            NotificationService, NotificationType, NotificationChannel
        )

        service = NotificationService()

        # Mock all channels
        service.email.send = AsyncMock(return_value=True)
        service.webhook.send = AsyncMock(return_value=True)

        with patch.object(service.in_app, '_get_redis', return_value=mock_redis):
            result = await service.notify(
                notification_type=NotificationType.PROCESSING_COMPLETED,
                context=sample_context,
                user_id=TEST_USER_UUID,
                email="user@test.local",
                webhook_url="https://webhook.test.local",
                channels=[
                    NotificationChannel.EMAIL,
                    NotificationChannel.WEBHOOK,
                    NotificationChannel.IN_APP
                ]
            )

            assert NotificationChannel.EMAIL in result
            assert NotificationChannel.WEBHOOK in result
            assert NotificationChannel.IN_APP in result

    @pytest.mark.asyncio
    async def test_notify_email_only(self, sample_context):
        """Nur E-Mail-Benachrichtigung senden."""
        from app.services.notification_service import (
            NotificationService, NotificationType, NotificationChannel
        )

        service = NotificationService()
        service.email.send = AsyncMock(return_value=True)

        result = await service.notify(
            notification_type=NotificationType.PROCESSING_COMPLETED,
            context=sample_context,
            email="user@test.local",
            channels=[NotificationChannel.EMAIL]
        )

        assert result[NotificationChannel.EMAIL] is True
        assert NotificationChannel.WEBHOOK not in result

    @pytest.mark.asyncio
    async def test_notify_processing_completed(self, mock_redis):
        """Convenience-Methode für abgeschlossene Verarbeitung."""
        from app.services.notification_service import NotificationService

        service = NotificationService()
        service.email.send = AsyncMock(return_value=True)

        with patch.object(service.in_app, '_get_redis', return_value=mock_redis):
            result = await service.notify_processing_completed(
                document_id="doc-123",
                filename="test.pdf",
                backend="deepseek",
                processing_result={
                    "processing_time": "1.5s",
                    "confidence": 0.95,
                    "word_count": 250,
                    "entity_count": 5,
                    "umlauts_valid": True
                },
                user_id=TEST_USER_UUID,
                email="user@test.local"
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_notify_processing_failed(self, mock_redis):
        """Convenience-Methode für fehlgeschlagene Verarbeitung."""
        from app.services.notification_service import NotificationService

        service = NotificationService()
        service.email.send = AsyncMock(return_value=True)

        with patch.object(service.in_app, '_get_redis', return_value=mock_redis):
            result = await service.notify_processing_failed(
                document_id="doc-123",
                filename="test.pdf",
                error_message="OCR-Fehler aufgetreten",
                user_id=TEST_USER_UUID
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_notify_quality_warning(self, mock_redis):
        """Convenience-Methode für Qualitätswarnung."""
        from app.services.notification_service import NotificationService, NotificationChannel

        service = NotificationService()

        with patch.object(service.in_app, '_get_redis', return_value=mock_redis):
            result = await service.notify_quality_warning(
                document_id="doc-123",
                confidence=0.65,
                recommendation="Manuelle Überprüfung empfohlen",
                user_id=TEST_USER_UUID
            )

            # Quality warnings should only go to in-app
            assert NotificationChannel.IN_APP in result
            assert NotificationChannel.EMAIL not in result

    @pytest.mark.asyncio
    async def test_notify_auto_detect_channels(self, sample_context, mock_redis):
        """Kanäle sollten automatisch erkannt werden."""
        from app.services.notification_service import (
            NotificationService, NotificationType, NotificationChannel
        )

        service = NotificationService()
        # Configure email
        service.email._smtp_host = "smtp.test.local"
        service.email._smtp_user = "test"
        service.email._smtp_password = "pass"
        service.email.send = AsyncMock(return_value=True)

        with patch.object(service.in_app, '_get_redis', return_value=mock_redis):
            result = await service.notify(
                notification_type=NotificationType.PROCESSING_COMPLETED,
                context=sample_context,
                user_id=TEST_USER_UUID,
                email="user@test.local"
            )

            # Should have in_app since user_id provided
            assert NotificationChannel.IN_APP in result


# ========================= Factory Tests =========================


class TestNotificationServiceFactory:
    """Tests for factory function."""

    def test_get_notification_service_singleton(self):
        """get_notification_service sollte Singleton zurückgeben."""
        from app.services.notification_service import get_notification_service
        import app.services.notification_service as module

        # Reset singleton
        module._notification_service = None

        service1 = get_notification_service()
        service2 = get_notification_service()

        assert service1 is service2


# ========================= Priority Tests =========================


class TestNotificationPriority:
    """Tests for NotificationPriority."""

    def test_priority_levels(self):
        """Prioritätsstufen sollten definiert sein."""
        from app.services.notification_service import NotificationPriority

        assert NotificationPriority.LOW == "low"
        assert NotificationPriority.NORMAL == "normal"
        assert NotificationPriority.HIGH == "high"
        assert NotificationPriority.CRITICAL == "critical"

    @pytest.mark.asyncio
    async def test_notify_with_priority(self, sample_context, mock_redis):
        """Benachrichtigung mit Priorität senden."""
        from app.services.notification_service import (
            NotificationService, NotificationType, NotificationPriority,
            NotificationChannel
        )

        service = NotificationService()
        service.webhook.send = AsyncMock(return_value=True)

        result = await service.notify(
            notification_type=NotificationType.PROCESSING_FAILED,
            context=sample_context,
            webhook_url="https://webhook.test.local",
            channels=[NotificationChannel.WEBHOOK],
            priority=NotificationPriority.CRITICAL
        )

        assert result[NotificationChannel.WEBHOOK] is True
        # Verify priority was passed in payload
        call_kwargs = service.webhook.send.call_args.kwargs
        assert call_kwargs["payload"]["priority"] == NotificationPriority.CRITICAL


# ========================= Edge Cases =========================


class TestNotificationServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_notify_no_channels(self, sample_context):
        """Benachrichtigung ohne Kanäle."""
        from app.services.notification_service import NotificationService, NotificationType

        service = NotificationService()

        result = await service.notify(
            notification_type=NotificationType.PROCESSING_COMPLETED,
            context=sample_context,
            channels=[]
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_notify_redis_failure(self, sample_context):
        """In-App-Benachrichtigung bei Redis-Fehler."""
        from app.services.notification_service import (
            NotificationService, NotificationType, NotificationChannel
        )

        service = NotificationService()

        # Mock Redis failure
        async def failing_get_redis():
            raise Exception("Redis connection failed")

        with patch.object(service.in_app, '_get_redis', side_effect=failing_get_redis):
            result = await service.notify(
                notification_type=NotificationType.PROCESSING_COMPLETED,
                context=sample_context,
                user_id=TEST_USER_UUID,
                channels=[NotificationChannel.IN_APP]
            )

            # Should still return result (with failed status)
            assert NotificationChannel.IN_APP in result

    @pytest.mark.asyncio
    async def test_template_with_umlauts(self):
        """Template mit Umlauten rendern."""
        from app.services.notification_service import NotificationTemplate, NotificationType

        context = {
            "document_id": "doc-123",
            "filename": "Prüfbericht_Änderungen.pdf",
            "backend": "deepseek",
            "processing_time": "2.5s",
            "confidence": 98.0,
            "word_count": 500,
            "entity_count": 10,
            "umlauts_valid": "Ja",
        }

        result = NotificationTemplate.render(
            NotificationType.PROCESSING_COMPLETED,
            context
        )

        assert "Prüfbericht" in result["body"]
        assert "Änderungen" in result["body"]
