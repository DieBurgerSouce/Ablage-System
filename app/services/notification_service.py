# -*- coding: utf-8 -*-
"""
Notification Service for Ablage-System.

Enterprise-grade notification system for document processing events:
- Email notifications (SMTP)
- Webhook notifications (HTTP callbacks)
- WebSocket real-time updates
- In-app notification storage

Feinpoliert und durchdacht - Zuverlässige Benachrichtigungen für Benutzer.
"""

import asyncio
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class NotificationType:
    """Notification type constants."""
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    OCR_QUALITY_WARNING = "ocr_quality_warning"
    GERMAN_VALIDATION_WARNING = "german_validation_warning"
    BATCH_COMPLETED = "batch_completed"
    SYSTEM_ALERT = "system_alert"


class NotificationChannel:
    """Notification channel constants."""
    EMAIL = "email"
    WEBHOOK = "webhook"
    WEBSOCKET = "websocket"
    IN_APP = "in_app"


class NotificationPriority:
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationTemplate:
    """German notification templates."""

    TEMPLATES = {
        NotificationType.PROCESSING_STARTED: {
            "subject": "Dokumentverarbeitung gestartet",
            "body": """
Sehr geehrter Benutzer,

Die Verarbeitung Ihres Dokuments wurde gestartet.

Dokument-ID: {document_id}
Dateiname: {filename}
Backend: {backend}
Gestartet um: {started_at}

Sie werden benachrichtigt, sobald die Verarbeitung abgeschlossen ist.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.PROCESSING_COMPLETED: {
            "subject": "Dokumentverarbeitung erfolgreich abgeschlossen",
            "body": """
Sehr geehrter Benutzer,

Die Verarbeitung Ihres Dokuments wurde erfolgreich abgeschlossen.

Dokument-ID: {document_id}
Dateiname: {filename}
OCR-Backend: {backend}
Verarbeitungszeit: {processing_time}
OCR-Konfidenz: {confidence}%
Erkannter Text: {word_count} Wörter

Ergebnisse:
- Erkannte Entitäten: {entity_count}
- Deutsche Umlaute validiert: {umlauts_valid}

Sie können das Dokument jetzt im Dashboard einsehen.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.PROCESSING_FAILED: {
            "subject": "Dokumentverarbeitung fehlgeschlagen",
            "body": """
Sehr geehrter Benutzer,

Die Verarbeitung Ihres Dokuments ist leider fehlgeschlagen.

Dokument-ID: {document_id}
Dateiname: {filename}
Fehler: {error_message}
Fehlgeschlagen um: {failed_at}

Mögliche Ursachen:
- Das Dokument ist möglicherweise beschädigt
- Das Format wird nicht unterstützt
- Die Bildqualität ist zu niedrig

Bitte versuchen Sie es erneut oder kontaktieren Sie den Support.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.OCR_QUALITY_WARNING: {
            "subject": "OCR-Qualitätswarnung",
            "body": """
Sehr geehrter Benutzer,

Bei der OCR-Verarbeitung wurde eine niedrige Erkennungsqualität festgestellt.

Dokument-ID: {document_id}
Konfidenz: {confidence}%
Empfohlene Aktion: {recommendation}

Bitte überprüfen Sie das Ergebnis manuell.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.GERMAN_VALIDATION_WARNING: {
            "subject": "Deutsche Textvalidierung - Warnung",
            "body": """
Sehr geehrter Benutzer,

Bei der Validierung des deutschen Texts wurden potenzielle Probleme gefunden.

Dokument-ID: {document_id}
Validierungsscore: {validation_score}%
Probleme: {issues}

Bitte überprüfen Sie die Umlaute und Sonderzeichen manuell.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.BATCH_COMPLETED: {
            "subject": "Stapelverarbeitung abgeschlossen",
            "body": """
Sehr geehrter Benutzer,

Die Stapelverarbeitung wurde abgeschlossen.

Batch-ID: {batch_id}
Gesamte Dokumente: {total_documents}
Erfolgreich: {successful_count}
Fehlgeschlagen: {failed_count}
Gesamtzeit: {total_time}

Details zu fehlgeschlagenen Dokumenten finden Sie im Dashboard.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.SYSTEM_ALERT: {
            "subject": "Ablage-System - Systemwarnung",
            "body": """
SYSTEMWARNUNG

{alert_type}: {message}

Zeitpunkt: {timestamp}
Schweregrad: {severity}

{details}

Bitte überprüfen Sie das System.
            """.strip(),
        },
    }

    @classmethod
    def render(
        cls,
        notification_type: str,
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Render notification template with context."""
        template = cls.TEMPLATES.get(notification_type, {})

        subject = template.get("subject", "Ablage-System Benachrichtigung")
        body = template.get("body", "Keine Vorlage verfügbar")

        # Render with context
        try:
            rendered_body = body.format(**context)
            rendered_subject = subject.format(**context) if "{" in subject else subject
        except KeyError as e:
            logger.warning("missing_template_context", missing_key=str(e))
            rendered_body = body
            rendered_subject = subject

        return {
            "subject": rendered_subject,
            "body": rendered_body,
        }


class EmailNotifier:
    """Email notification sender using SMTP."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None,
        use_tls: bool = True,
    ) -> None:
        """
        Initialize email notifier.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_email: Sender email address
            use_tls: Whether to use TLS
        """
        self.smtp_host = smtp_host or getattr(settings, "SMTP_HOST", None)
        self.smtp_port = smtp_port or getattr(settings, "SMTP_PORT", 587)
        self.smtp_user = smtp_user or getattr(settings, "SMTP_USER", None)
        self.smtp_password = smtp_password or getattr(settings, "SMTP_PASSWORD", None)
        self.from_email = from_email or getattr(settings, "FROM_EMAIL", "noreply@ablage-system.de")
        self.use_tls = use_tls

    @property
    def is_configured(self) -> bool:
        """Check if email notifications are configured."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send email notification.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            logger.warning("E-Mail-Benachrichtigungen nicht konfiguriert")
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            # Add plain text
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # Add HTML if provided
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Send email in thread pool to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._send_smtp,
                to_email,
                msg,
            )

            logger.info(
                "email_sent",
                to=to_email,
                subject=subject,
            )
            return True

        except Exception as e:
            logger.error(
                "email_send_failed",
                to=to_email,
                error=str(e),
            )
            return False

    def _send_smtp(self, to_email: str, msg: MIMEMultipart) -> None:
        """Send email via SMTP (blocking operation)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg, self.from_email, [to_email])


class WebhookNotifier:
    """Webhook notification sender for external integrations."""

    DEFAULT_TIMEOUT = 30
    MAX_RETRIES = 3

    def __init__(
        self,
        default_webhook_url: Optional[str] = None,
        secret_key: Optional[str] = None,
    ) -> None:
        """
        Initialize webhook notifier.

        Args:
            default_webhook_url: Default webhook URL
            secret_key: Secret key for signing payloads
        """
        self.default_webhook_url = default_webhook_url or getattr(
            settings, "WEBHOOK_URL", None
        )
        self.secret_key = secret_key or getattr(settings, "WEBHOOK_SECRET", None)

    async def send(
        self,
        webhook_url: Optional[str],
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Send webhook notification.

        Args:
            webhook_url: Target webhook URL (or use default)
            payload: JSON payload to send
            headers: Optional custom headers

        Returns:
            True if sent successfully
        """
        url = webhook_url or self.default_webhook_url

        if not url:
            logger.warning("Keine Webhook-URL konfiguriert")
            return False

        try:
            request_headers = {
                "Content-Type": "application/json",
                "X-Ablage-System-Event": payload.get("event_type", "notification"),
                "X-Ablage-System-Timestamp": datetime.utcnow().isoformat(),
            }

            if headers:
                request_headers.update(headers)

            # Add signature if secret key configured
            if self.secret_key:
                import hashlib
                import hmac
                signature = hmac.new(
                    self.secret_key.encode(),
                    json.dumps(payload).encode(),
                    hashlib.sha256,
                ).hexdigest()
                request_headers["X-Ablage-System-Signature"] = signature

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=request_headers,
                    timeout=self.DEFAULT_TIMEOUT,
                )
                response.raise_for_status()

            logger.info(
                "webhook_sent",
                url=url,
                status_code=response.status_code,
            )
            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "webhook_http_error",
                url=url,
                status_code=e.response.status_code,
            )
            return False
        except Exception as e:
            logger.error(
                "webhook_send_failed",
                url=url,
                error=str(e),
            )
            return False


class InAppNotificationStore:
    """In-app notification storage using Redis."""

    NOTIFICATION_TTL = 7 * 24 * 60 * 60  # 7 days
    MAX_NOTIFICATIONS_PER_USER = 100

    def __init__(self) -> None:
        """Initialize in-app notification store."""
        self._redis = None

    async def _get_redis(self):
        """Get Redis client (lazy initialization)."""
        if self._redis is None:
            from app.core.redis_state import get_redis
            self._redis = await get_redis()
        return self._redis

    async def store(
        self,
        user_id: str,
        notification: Dict[str, Any],
    ) -> str:
        """
        Store notification for user.

        Args:
            user_id: User identifier
            notification: Notification data

        Returns:
            Notification ID
        """
        import uuid as uuid_module
        notification_id = str(uuid_module.uuid4())

        notification_data = {
            "id": notification_id,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "read": False,
            **notification,
        }

        try:
            redis = await self._get_redis()
            key = f"notifications:{user_id}"

            # Store notification
            await redis.client.lpush(key, json.dumps(notification_data))

            # Trim to max notifications
            await redis.client.ltrim(key, 0, self.MAX_NOTIFICATIONS_PER_USER - 1)

            # Set TTL
            await redis.client.expire(key, self.NOTIFICATION_TTL)

            logger.debug(
                "notification_stored",
                user_id=user_id,
                notification_id=notification_id,
            )

            return notification_id

        except Exception as e:
            logger.error(
                "notification_store_failed",
                user_id=user_id,
                error=str(e),
            )
            return notification_id

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get notifications for user.

        Args:
            user_id: User identifier
            unread_only: Only return unread notifications
            limit: Maximum number to return

        Returns:
            List of notifications
        """
        try:
            redis = await self._get_redis()
            key = f"notifications:{user_id}"

            # Get notifications
            raw_notifications = await redis.client.lrange(key, 0, limit - 1)

            notifications = []
            for raw in raw_notifications:
                notification = json.loads(raw)
                if unread_only and notification.get("read"):
                    continue
                notifications.append(notification)

            return notifications

        except Exception as e:
            logger.error(
                "notification_fetch_failed",
                user_id=user_id,
                error=str(e),
            )
            return []

    async def mark_read(
        self,
        user_id: str,
        notification_id: str,
    ) -> bool:
        """Mark notification as read."""
        try:
            redis = await self._get_redis()
            key = f"notifications:{user_id}"

            # Get all notifications
            raw_notifications = await redis.client.lrange(key, 0, -1)

            for i, raw in enumerate(raw_notifications):
                notification = json.loads(raw)
                if notification.get("id") == notification_id:
                    notification["read"] = True
                    notification["read_at"] = datetime.utcnow().isoformat()
                    await redis.client.lset(key, i, json.dumps(notification))
                    return True

            return False

        except Exception as e:
            logger.error(
                "notification_mark_read_failed",
                user_id=user_id,
                notification_id=notification_id,
                error=str(e),
            )
            return False

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications."""
        notifications = await self.get_notifications(user_id, unread_only=True)
        return len(notifications)


class NotificationService:
    """
    Central notification service coordinating all channels.

    Provides a unified interface for sending notifications through:
    - Email (SMTP)
    - Webhooks (HTTP POST)
    - In-app notifications (Redis)
    """

    def __init__(self) -> None:
        """Initialize notification service with all channels."""
        self.email = EmailNotifier()
        self.webhook = WebhookNotifier()
        self.in_app = InAppNotificationStore()

    async def notify(
        self,
        notification_type: str,
        context: Dict[str, Any],
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        webhook_url: Optional[str] = None,
        channels: Optional[List[str]] = None,
        priority: str = NotificationPriority.NORMAL,
    ) -> Dict[str, bool]:
        """
        Send notification through specified channels.

        Args:
            notification_type: Type of notification
            context: Template context for rendering
            user_id: User ID for in-app notifications
            email: Email address for email notifications
            webhook_url: Custom webhook URL
            channels: List of channels to use (default: all configured)
            priority: Notification priority

        Returns:
            Dictionary of channel -> success status
        """
        # Determine channels
        if channels is None:
            channels = []
            if email and self.email.is_configured:
                channels.append(NotificationChannel.EMAIL)
            if webhook_url or self.webhook.default_webhook_url:
                channels.append(NotificationChannel.WEBHOOK)
            if user_id:
                channels.append(NotificationChannel.IN_APP)

        # Render template
        rendered = NotificationTemplate.render(notification_type, context)

        # Prepare results
        results = {}

        # Send to all channels concurrently
        tasks = []

        if NotificationChannel.EMAIL in channels and email:
            tasks.append(self._send_email(email, rendered, results))

        if NotificationChannel.WEBHOOK in channels:
            tasks.append(self._send_webhook(
                webhook_url,
                notification_type,
                context,
                priority,
                results,
            ))

        if NotificationChannel.IN_APP in channels and user_id:
            tasks.append(self._store_in_app(
                user_id,
                notification_type,
                rendered,
                priority,
                results,
            ))

        # Execute all notifications concurrently
        if tasks:
            await asyncio.gather(*tasks)

        logger.info(
            "notifications_sent",
            notification_type=notification_type,
            channels=channels,
            results=results,
        )

        return results

    async def _send_email(
        self,
        email: str,
        rendered: Dict[str, str],
        results: Dict[str, bool],
    ) -> None:
        """Send email notification."""
        results[NotificationChannel.EMAIL] = await self.email.send(
            to_email=email,
            subject=rendered["subject"],
            body=rendered["body"],
        )

    async def _send_webhook(
        self,
        webhook_url: Optional[str],
        notification_type: str,
        context: Dict[str, Any],
        priority: str,
        results: Dict[str, bool],
    ) -> None:
        """Send webhook notification."""
        payload = {
            "event_type": notification_type,
            "timestamp": datetime.utcnow().isoformat(),
            "priority": priority,
            "data": context,
        }
        results[NotificationChannel.WEBHOOK] = await self.webhook.send(
            webhook_url=webhook_url,
            payload=payload,
        )

    async def _store_in_app(
        self,
        user_id: str,
        notification_type: str,
        rendered: Dict[str, str],
        priority: str,
        results: Dict[str, bool],
    ) -> None:
        """Store in-app notification."""
        notification_id = await self.in_app.store(
            user_id=user_id,
            notification={
                "type": notification_type,
                "title": rendered["subject"],
                "message": rendered["body"],
                "priority": priority,
            },
        )
        results[NotificationChannel.IN_APP] = bool(notification_id)

    async def notify_processing_completed(
        self,
        document_id: str,
        filename: str,
        backend: str,
        processing_result: Dict[str, Any],
        user_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        Send processing completed notification.

        Convenience method for common notification type.
        """
        context = {
            "document_id": document_id,
            "filename": filename,
            "backend": backend,
            "processing_time": processing_result.get("processing_time", "N/A"),
            "confidence": round(processing_result.get("confidence", 0) * 100, 1),
            "word_count": processing_result.get("word_count", 0),
            "entity_count": processing_result.get("entity_count", 0),
            "umlauts_valid": "Ja" if processing_result.get("umlauts_valid") else "Nein",
        }

        return await self.notify(
            notification_type=NotificationType.PROCESSING_COMPLETED,
            context=context,
            user_id=user_id,
            email=email,
        )

    async def notify_processing_failed(
        self,
        document_id: str,
        filename: str,
        error_message: str,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        Send processing failed notification.

        Convenience method for common notification type.
        """
        context = {
            "document_id": document_id,
            "filename": filename,
            "error_message": error_message,
            "failed_at": datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S"),
        }

        return await self.notify(
            notification_type=NotificationType.PROCESSING_FAILED,
            context=context,
            user_id=user_id,
            email=email,
            priority=NotificationPriority.HIGH,
        )

    async def notify_quality_warning(
        self,
        document_id: str,
        confidence: float,
        recommendation: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, bool]:
        """
        Send OCR quality warning notification.

        Convenience method for quality warnings.
        """
        context = {
            "document_id": document_id,
            "confidence": round(confidence * 100, 1),
            "recommendation": recommendation,
        }

        return await self.notify(
            notification_type=NotificationType.OCR_QUALITY_WARNING,
            context=context,
            user_id=user_id,
            channels=[NotificationChannel.IN_APP],  # Quality warnings only in-app
        )


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create singleton notification service."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
