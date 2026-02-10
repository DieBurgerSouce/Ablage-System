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
import threading
import uuid as uuid_module
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import httpx
import structlog
from starlette.websockets import WebSocket

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# SECURITY: Header/Key Sanitization Functions (PHASE 10.2/10.3 FIX)
# =============================================================================

def sanitize_email_header(value: str) -> str:
    """Sanitize email header values to prevent header injection attacks.

    Removes CRLF characters that could be used to inject additional headers.

    Args:
        value: Raw header value (e.g., subject, to address)

    Returns:
        Sanitized header value safe for email headers

    Security:
        - Prevents email header injection (CWE-93)
        - Removes CR, LF, and NULL characters
    """
    if not value:
        return ""
    return value.replace('\r', '').replace('\n', '').replace('\x00', '')


def validate_user_id_for_redis_key(user_id: str) -> str:
    """Validate user_id is a valid UUID before using in Redis keys.

    Prevents Redis key injection by ensuring only valid UUIDs are used.

    Args:
        user_id: User identifier to validate

    Returns:
        Validated user_id string

    Raises:
        ValueError: If user_id is not a valid UUID

    Security:
        - Prevents Redis key injection attacks
        - Ensures predictable key format
    """
    try:
        # This will raise ValueError if not a valid UUID
        uuid_module.UUID(user_id)
        return user_id
    except (ValueError, AttributeError) as e:
        logger.warning(
            "invalid_user_id_for_redis_key",
            user_id=str(user_id)[:50],  # Truncate for logging
            **safe_error_log(e)
        )
        raise ValueError(f"Invalid user_id format: must be a valid UUID")


class NotificationType:
    """Notification type constants."""
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    OCR_QUALITY_WARNING = "ocr_quality_warning"
    GERMAN_VALIDATION_WARNING = "german_validation_warning"
    BATCH_COMPLETED = "batch_completed"
    SYSTEM_ALERT = "system_alert"
    PASSWORD_RESET_CONFIRMATION = "password_reset_confirmation"
    # Export-spezifische Typen
    EXPORT_COMPLETED = "export_completed"
    EXPORT_FAILED = "export_failed"
    SCHEDULED_EXPORT_COMPLETED = "scheduled_export_completed"
    SCHEDULED_EXPORT_FAILED = "scheduled_export_failed"
    # Approval-spezifische Typen
    APPROVAL_ESCALATED = "approval_escalated"
    APPROVAL_REMINDER = "approval_reminder"
    APPROVAL_ACTION_REQUIRED = "approval_action_required"
    # Banking-spezifische Typen
    SKONTO_EXPIRING = "skonto_expiring"
    ERP_CONFLICT_PENDING = "erp_conflict_pending"
    DUNNING_NOTIFICATION = "dunning_notification"


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
        NotificationType.PASSWORD_RESET_CONFIRMATION: {
            "subject": "Passwort erfolgreich geändert - Ablage-System",
            "body": """
Guten Tag {full_name},

Ihr Passwort für das Ablage-System wurde erfolgreich geändert.

Zeitpunkt: {timestamp}
IP-Adresse: {ip_address}
Gerät: {user_agent}

Falls Sie diese Änderung NICHT vorgenommen haben, ergreifen Sie bitte sofort folgende Maßnahmen:
1. Kontaktieren Sie umgehend den Administrator
2. Versuchen Sie, Ihr Passwort erneut zurückzusetzen
3. Überprüfen Sie Ihre anderen Konten auf verdächtige Aktivitäten

Mit freundlichen Grüßen,
Ablage-System Team

---
Diese E-Mail wurde automatisch generiert. Bitte antworten Sie nicht darauf.
            """.strip(),
        },
        NotificationType.EXPORT_COMPLETED: {
            "subject": "Export erfolgreich abgeschlossen",
            "body": """
Sehr geehrter Benutzer,

Ihr Export wurde erfolgreich abgeschlossen.

Export-Details:
- Dokumente exportiert: {documents_exported}
- Format: {export_format}
- Gesamtgröße: {total_size}
- Verarbeitungszeit: {processing_time}

Sie können die exportierten Daten jetzt herunterladen.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.EXPORT_FAILED: {
            "subject": "Export fehlgeschlagen",
            "body": """
Sehr geehrter Benutzer,

Ihr Export ist leider fehlgeschlagen.

Fehlerdetails:
- Fehler: {error_message}
- Verarbeitete Dokumente: {processed_count}/{total_count}
- Zeitpunkt: {failed_at}

Bitte versuchen Sie es erneut oder kontaktieren Sie den Support.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.SCHEDULED_EXPORT_COMPLETED: {
            "subject": "Geplanter Export '{export_name}' abgeschlossen",
            "body": """
Sehr geehrter Benutzer,

Ihr geplanter Export wurde erfolgreich ausgeführt.

Export-Name: {export_name}
Ausführungszeitpunkt: {executed_at}

Ergebnis:
- Dokumente exportiert: {documents_exported}
- Format: {export_format}
- Status: Erfolgreich

Der nächste geplante Export ist für {next_run} vorgesehen.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.SCHEDULED_EXPORT_FAILED: {
            "subject": "Geplanter Export '{export_name}' fehlgeschlagen",
            "body": """
Sehr geehrter Benutzer,

Ihr geplanter Export ist leider fehlgeschlagen.

Export-Name: {export_name}
Ausführungszeitpunkt: {executed_at}

Fehlerdetails:
- Fehler: {error_message}
- Verarbeitete Dokumente: {processed_count}/{total_count}

Der nächste Versuch ist für {next_run} geplant.
Bei wiederholten Fehlern überprüfen Sie bitte die Export-Konfiguration.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.APPROVAL_ESCALATED: {
            "subject": "Genehmigungsanfrage eskaliert - Sofortige Aufmerksamkeit erforderlich",
            "body": """
Sehr geehrter Benutzer,

Eine Genehmigungsanfrage wurde eskaliert und erfordert Ihre sofortige Aufmerksamkeit.

Anfrage-Details:
- Anfrage-ID: {request_id}
- Betreff: {request_subject}
- Ursprünglicher Antragsteller: {requester_name}
- Fälligkeitsdatum: {due_date}
- Eskaliert am: {escalated_at}

Grund der Eskalation:
Die ursprüngliche Fälligkeitsfrist wurde überschritten ohne dass eine Entscheidung getroffen wurde.

Bitte bearbeiten Sie diese Anfrage umgehend im Dashboard.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.APPROVAL_REMINDER: {
            "subject": "Erinnerung: Ausstehende Genehmigung wartet auf Ihre Entscheidung",
            "body": """
Sehr geehrter Benutzer,

Sie haben eine ausstehende Genehmigungsanfrage, die bald fällig ist.

Anfrage-Details:
- Anfrage-ID: {request_id}
- Betreff: {request_subject}
- Antragsteller: {requester_name}
- Fälligkeitsdatum: {due_date}
- Verbleibende Zeit: {time_remaining}

Erinnerungszähler: {reminder_count}

Bitte treffen Sie eine Entscheidung, um eine Eskalation zu vermeiden.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.APPROVAL_ACTION_REQUIRED: {
            "subject": "Neue Genehmigungsanfrage: {request_subject}",
            "body": """
Sehr geehrter Benutzer,

Sie haben eine neue Genehmigungsanfrage erhalten, die Ihre Aufmerksamkeit erfordert.

Anfrage-Details:
- Anfrage-ID: {request_id}
- Betreff: {request_subject}
- Antragsteller: {requester_name}
- Priorität: {priority}
- Fälligkeitsdatum: {due_date}

Beschreibung:
{description}

Bitte prüfen und genehmigen oder ablehnen Sie diese Anfrage im Dashboard.

Mit freundlichen Grüßen,
Ablage-System
            """.strip(),
        },
        NotificationType.SKONTO_EXPIRING: {
            "subject": "Skonto-Frist laeuft ab - Handlungsbedarf",
            "body": """
Sehr geehrter Benutzer,

Folgende Rechnungen haben bald ablaufende Skonto-Fristen:

{opportunities_list}

Gesamtersparnis bei rechtzeitiger Zahlung: {total_savings} EUR

Bitte pruefen Sie die Zahlungsmoeglichkeiten.

Mit freundlichen Gruessen,
Ablage-System
            """.strip(),
        },
        NotificationType.ERP_CONFLICT_PENDING: {
            "subject": "ERP-Synchronisationskonflikte erfordern Aufmerksamkeit",
            "body": """
Sehr geehrter Administrator,

Es wurden Konflikte bei der ERP-Synchronisation festgestellt, die Ihre Aufmerksamkeit erfordern.

Konflikt-Zusammenfassung:
- Anzahl offener Konflikte: {total_conflicts}
- Betroffene Verbindungen: {connection_count}

Details nach Verbindung:
{conflicts_by_connection_list}

Bitte loesen Sie diese Konflikte im Admin-Bereich unter ERP-Sync > Konflikte.

Mit freundlichen Gruessen,
Ablage-System
            """.strip(),
        },
        NotificationType.DUNNING_NOTIFICATION: {
            "subject": "Mahnung Stufe {dunning_level} - {customer_name}",
            "body": """
Sehr geehrter Benutzer,

Eine neue Mahnaufgabe wurde erstellt.

Details:
- Kunde: {customer_name}
- Rechnungsnummer: {invoice_number}
- Betrag: {amount} EUR
- Faellig seit: {days_overdue} Tagen
- Mahnstufe: {dunning_level}
- Empfohlene Aktion: {recommended_action}

Bitte bearbeiten Sie diese Aufgabe zeitnah.

Mit freundlichen Gruessen,
Ablage-System
            """.strip(),
        },
    }

    @classmethod
    def render(
        cls,
        notification_type: str,
        context: Dict[str, object],
    ) -> Dict[str, str]:
        """Render notification template with context."""
        template = cls.TEMPLATES.get(notification_type, {})

        subject = template.get("subject", "Ablage-System Benachrichtigung")
        body = template.get("body", "Keine Vorlage verfügbar")

        # Render with context
        try:
            rendered_body = body.format(**context)
            # SECURITY FIX Phase 11.1: Sanitize rendered subject to prevent header injection
            rendered_subject = sanitize_email_header(
                subject.format(**context) if "{" in subject else subject
            )
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
            # SECURITY: Sanitize headers to prevent header injection (Phase 10.2)
            msg["Subject"] = sanitize_email_header(subject)
            msg["From"] = self.from_email  # from_email is controlled by config
            msg["To"] = sanitize_email_header(to_email)

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
                **safe_error_log(e),
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
        payload: Dict[str, object],
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

        # M.1 CRITICAL: SSRF-Schutz - URL validieren BEVOR HTTP-Request gemacht wird
        from app.core.security import validate_url_for_ssrf_async
        is_valid, ssrf_error = await validate_url_for_ssrf_async(url)
        if not is_valid:
            logger.warning(
                "notification_webhook_ssrf_blocked",
                url=url[:50],
                error=ssrf_error
            )
            return False

        try:
            request_headers = {
                "Content-Type": "application/json",
                "X-Ablage-System-Event": payload.get("event_type", "notification"),
                "X-Ablage-System-Timestamp": datetime.now(timezone.utc).isoformat(),
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
                **safe_error_log(e),
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
        notification: Dict[str, object],
    ) -> str:
        """
        Store notification for user.

        Args:
            user_id: User identifier
            notification: Notification data

        Returns:
            Notification ID
        """
        notification_id = str(uuid_module.uuid4())

        notification_data = {
            "id": notification_id,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
            **notification,
        }

        try:
            redis = await self._get_redis()
            # SECURITY: Validate user_id to prevent Redis key injection (Phase 10.3)
            validated_user_id = validate_user_id_for_redis_key(user_id)
            key = f"notifications:{validated_user_id}"

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
                **safe_error_log(e),
            )
            return notification_id

    async def get_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, object]]:
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
            # SECURITY: Validate user_id to prevent Redis key injection (Phase 10.3)
            validated_user_id = validate_user_id_for_redis_key(user_id)
            key = f"notifications:{validated_user_id}"

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
                **safe_error_log(e),
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
            # SECURITY: Validate user_id to prevent Redis key injection (Phase 10.3)
            validated_user_id = validate_user_id_for_redis_key(user_id)
            key = f"notifications:{validated_user_id}"

            # Get all notifications
            raw_notifications = await redis.client.lrange(key, 0, -1)

            for i, raw in enumerate(raw_notifications):
                notification = json.loads(raw)
                if notification.get("id") == notification_id:
                    notification["read"] = True
                    notification["read_at"] = datetime.now(timezone.utc).isoformat()
                    await redis.client.lset(key, i, json.dumps(notification))
                    return True

            return False

        except Exception as e:
            logger.error(
                "notification_mark_read_failed",
                user_id=user_id,
                notification_id=notification_id,
                **safe_error_log(e),
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
    - WebSocket real-time updates
    """

    def __init__(self) -> None:
        """Initialize notification service with all channels."""
        self.email = EmailNotifier()
        self.webhook = WebhookNotifier()
        self.in_app = InAppNotificationStore()
        # WebSocket manager wird lazy initialisiert um zirkulaere Imports zu vermeiden
        self._ws_manager: Optional["NotificationWebSocketManager"] = None

    @property
    def websocket(self) -> "NotificationWebSocketManager":
        """Lazy initialization of WebSocket manager."""
        if self._ws_manager is None:
            self._ws_manager = get_notification_ws_manager()
        return self._ws_manager

    async def notify(
        self,
        notification_type: str,
        context: Dict[str, object],
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
                channels.append(NotificationChannel.WEBSOCKET)

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

        if NotificationChannel.WEBSOCKET in channels and user_id:
            tasks.append(self._send_websocket(
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
        context: Dict[str, object],
        priority: str,
        results: Dict[str, bool],
    ) -> None:
        """Send webhook notification."""
        payload = {
            "event_type": notification_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def _send_websocket(
        self,
        user_id: str,
        notification_type: str,
        rendered: Dict[str, str],
        priority: str,
        results: Dict[str, bool],
    ) -> None:
        """Send WebSocket notification via EventBroadcaster."""
        try:
            # Emit via EventBroadcaster for realtime system
            from app.services.realtime.event_broadcaster import get_event_broadcaster
            broadcaster = get_event_broadcaster()
            await broadcaster.emit_notification(
                user_id=user_id,
                title=rendered["subject"],
                message=rendered["body"],
                priority=priority,
                notification_type=notification_type,
            )
            results[NotificationChannel.WEBSOCKET] = True

            logger.debug(
                "websocket_notification_sent",
                user_id=user_id,
                notification_type=notification_type,
            )
        except Exception as e:
            logger.warning(
                "websocket_notification_failed",
                user_id=user_id,
                **safe_error_log(e),
            )
            results[NotificationChannel.WEBSOCKET] = False

    async def notify_processing_completed(
        self,
        document_id: str,
        filename: str,
        backend: str,
        processing_result: Dict[str, object],
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
            "failed_at": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S"),
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

    async def send_admin_alert(
        self,
        subject: str,
        message: str,
        priority: str = NotificationPriority.HIGH,
    ) -> bool:
        """
        Send alert to admin/DPO.

        Used for critical system alerts, security incidents, and GDPR breach notifications.

        Args:
            subject: Alert subject
            message: Alert message
            priority: Alert priority (default: HIGH)

        Returns:
            True if sent successfully
        """
        admin_email = getattr(settings, "SMTP_FROM_EMAIL", None) or getattr(settings, "ADMIN_EMAIL", None)

        if not admin_email:
            logger.warning("admin_alert_no_recipient", message="Keine Admin-E-Mail konfiguriert")
            # Log to console as fallback
            logger.critical("admin_alert", subject=subject, message=message, priority=priority)
            return False

        if not self.email.is_configured:
            logger.warning("admin_alert_email_not_configured")
            logger.critical("admin_alert", subject=subject, message=message, priority=priority)
            return False

        return await self.email.send(
            to_email=admin_email,
            subject=f"[{priority.upper()}] {subject}",
            body=message,
        )

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send email directly.

        Convenience method for direct email sending (e.g., GDPR notifications).

        Args:
            to_email: Recipient email
            subject: Email subject
            body: Email body
            html_body: Optional HTML body

        Returns:
            True if sent successfully
        """
        return await self.email.send(
            to_email=to_email,
            subject=subject,
            body=body,
            html_body=html_body,
        )


# =============================================================================
# WebSocket Notification Manager
# =============================================================================


class NotificationWebSocketManager:
    """
    WebSocket Manager fuer Real-time Benachrichtigungen an Benutzer.

    Features:
    - Pro-User WebSocket-Verbindungen (kann mehrere Tabs haben)
    - Broadcast an alle Verbindungen eines Users
    - Automatische Verbindungsverwaltung
    - Thread-safe fuer async Operationen
    """

    def __init__(self) -> None:
        """Initialize notification WebSocket manager."""
        # user_id -> List[WebSocket]  (User kann mehrere Tabs/Geraete haben)
        self._connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
    ) -> bool:
        """
        Verbindet einen User fuer Benachrichtigungen.

        Args:
            websocket: WebSocket-Verbindung
            user_id: User ID

        Returns:
            True wenn erfolgreich verbunden
        """
        try:
            await websocket.accept()
        except Exception as e:
            logger.warning(
                "notification_ws_accept_failed",
                user_id=user_id,
                **safe_error_log(e)
            )
            return False

        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(websocket)

        logger.info(
            "notification_ws_connected",
            user_id=user_id,
            connection_count=len(self._connections.get(user_id, [])),
        )
        return True

    async def disconnect(
        self,
        websocket: WebSocket,
        user_id: str,
    ) -> None:
        """
        Trennt eine WebSocket-Verbindung.

        Args:
            websocket: WebSocket-Verbindung
            user_id: User ID
        """
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(websocket)
                except ValueError as e:
                    logger.debug(
                        "websocket_remove_failed",
                        error_type=type(e).__name__,
                    )

                # Leere Liste entfernen
                if not self._connections[user_id]:
                    del self._connections[user_id]

        logger.info(
            "notification_ws_disconnected",
            user_id=user_id,
            remaining_connections=len(self._connections.get(user_id, [])),
        )

    async def send_to_user(
        self,
        user_id: str,
        message: Dict[str, object],
    ) -> int:
        """
        Sendet eine Nachricht an alle Verbindungen eines Users.

        Args:
            user_id: Ziel-User ID
            message: Nachricht als Dict

        Returns:
            Anzahl erfolgreicher Sendungen
        """
        async with self._lock:
            if user_id not in self._connections:
                return 0

            # Kopie der Liste fuer thread-safe Iteration
            connections = list(self._connections[user_id])

        sent_count = 0
        dead_connections = []

        for ws in connections:
            try:
                await ws.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "notification_ws_send_failed",
                    user_id=user_id,
                    **safe_error_log(e),
                )
                dead_connections.append(ws)

        # Tote Verbindungen entfernen
        if dead_connections:
            async with self._lock:
                if user_id in self._connections:
                    for dead_ws in dead_connections:
                        try:
                            self._connections[user_id].remove(dead_ws)
                        except ValueError as e:
                            logger.debug(
                                "dead_websocket_remove_failed",
                                error_type=type(e).__name__,
                            )

        return sent_count

    async def broadcast_to_all(
        self,
        message: Dict[str, object],
    ) -> int:
        """
        Sendet eine Nachricht an alle verbundenen User.

        Args:
            message: Nachricht als Dict

        Returns:
            Anzahl erfolgreicher Sendungen
        """
        async with self._lock:
            all_user_ids = list(self._connections.keys())

        total_sent = 0
        for user_id in all_user_ids:
            sent = await self.send_to_user(user_id, message)
            total_sent += sent

        return total_sent

    def get_connected_users(self) -> List[str]:
        """Gibt Liste aller verbundenen User-IDs zurueck."""
        return list(self._connections.keys())

    def get_connection_count(self, user_id: str) -> int:
        """Gibt Anzahl der Verbindungen eines Users zurueck."""
        return len(self._connections.get(user_id, []))

    def is_user_connected(self, user_id: str) -> bool:
        """Prueft ob User verbunden ist."""
        return user_id in self._connections and len(self._connections[user_id]) > 0


# Singleton instances mit Thread-Safety (Double-Check Locking)
_notification_service: Optional[NotificationService] = None
_notification_service_lock = threading.Lock()
_notification_ws_manager: Optional[NotificationWebSocketManager] = None
_notification_ws_manager_lock = threading.Lock()


def get_notification_service() -> NotificationService:
    """Get or create singleton notification service (Thread-Safe)."""
    global _notification_service
    if _notification_service is None:
        with _notification_service_lock:
            # Double-Check Locking: Erneut pruefen nach Lock-Erwerb
            if _notification_service is None:
                _notification_service = NotificationService()
    return _notification_service


def get_notification_ws_manager() -> NotificationWebSocketManager:
    """Get or create singleton notification WebSocket manager (Thread-Safe)."""
    global _notification_ws_manager
    if _notification_ws_manager is None:
        with _notification_ws_manager_lock:
            # Double-Check Locking: Erneut pruefen nach Lock-Erwerb
            if _notification_ws_manager is None:
                _notification_ws_manager = NotificationWebSocketManager()
    return _notification_ws_manager
