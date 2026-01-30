"""
Slack Integration Service.

Ermoeglicht Benachrichtigungen an Slack-Kanaele ueber:
- Incoming Webhooks (einfach, keine Bot-Installation noetig)
- Bot Token (erweitert, fuer Slash-Commands und Datei-Uploads)

Feinpoliert und durchdacht - Enterprise Slack-Integration.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from collections import deque
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel, Field

from app.core.config import settings as app_settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class SlackMessagePriority(str, Enum):
    """Prioritaet einer Slack-Nachricht."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SlackNotificationType(str, Enum):
    """Typen von Slack-Benachrichtigungen."""
    DOCUMENT_PROCESSED = "document_processed"
    DOCUMENT_ERROR = "document_error"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_COMPLETED = "approval_completed"
    WORKFLOW_COMPLETED = "workflow_completed"
    HIGH_RISK_ENTITY = "high_risk_entity"
    DUNNING_ESCALATION = "dunning_escalation"
    SKONTO_EXPIRING = "skonto_expiring"
    REPORT_GENERATED = "report_generated"
    SYSTEM_ALERT = "system_alert"
    CUSTOM = "custom"


class SlackAttachment(BaseModel):
    """Slack Message Attachment."""
    color: Optional[str] = None  # Hex oder named color
    title: Optional[str] = None
    title_link: Optional[str] = None
    text: Optional[str] = None
    fields: list[dict[str, Any]] = Field(default_factory=list)
    footer: Optional[str] = None
    ts: Optional[int] = None  # Unix timestamp


class SlackBlock(BaseModel):
    """Slack Block Kit Block."""
    type: str
    text: Optional[dict[str, Any]] = None
    elements: Optional[list[dict[str, Any]]] = None
    accessory: Optional[dict[str, Any]] = None
    block_id: Optional[str] = None


class SlackMessage(BaseModel):
    """Slack-Nachricht mit Block Kit Support."""
    channel: Optional[str] = None
    text: str  # Fallback-Text fuer Notifications
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[SlackAttachment] = Field(default_factory=list)
    thread_ts: Optional[str] = None  # Fuer Thread-Antworten
    mrkdwn: bool = True
    unfurl_links: bool = False
    unfurl_media: bool = False


class SlackServiceError(Exception):
    """Fehler bei Slack-Operationen."""
    pass


class SlackRateLimitError(SlackServiceError):
    """Rate Limit erreicht."""
    pass


class SlackService:
    """
    Slack-Integration Service.

    Features:
    - Webhook-basierte Benachrichtigungen
    - Block Kit fuer reichhaltige Nachrichten
    - Rate Limiting mit Sliding Window
    - Retry-Logik fuer temporaere Fehler
    - Thread-Support fuer Konversationen
    - Attachment-Support fuer Dateien

    Verwendung:
        slack = SlackService()
        await slack.send_notification(
            notification_type=SlackNotificationType.DOCUMENT_PROCESSED,
            title="Dokument verarbeitet",
            message="Rechnung #12345 wurde erfolgreich verarbeitet",
            context={"document_id": "...", "confidence": 0.95}
        )
    """

    _instance: Optional["SlackService"] = None
    _lock = asyncio.Lock()

    # Rate Limiting
    _rate_limit_window: deque  # Timestamps der letzten Nachrichten
    _rate_limit_per_minute: int

    def __new__(cls) -> "SlackService":
        """Singleton-Pattern fuer Thread-Safety."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisierung (einmalig)."""
        if self._initialized:
            return

        self._webhook_url: Optional[str] = (
            app_settings.SLACK_WEBHOOK_URL.get_secret_value()
            if app_settings.SLACK_WEBHOOK_URL else None
        )
        self._bot_token: Optional[str] = (
            app_settings.SLACK_BOT_TOKEN.get_secret_value()
            if app_settings.SLACK_BOT_TOKEN else None
        )
        self._default_channel = app_settings.SLACK_DEFAULT_CHANNEL
        self._enabled = app_settings.SLACK_ENABLED
        self._notification_types = set(app_settings.SLACK_NOTIFICATION_TYPES)
        self._rate_limit_per_minute = app_settings.SLACK_RATE_LIMIT_PER_MINUTE

        # Rate Limiting
        self._rate_limit_window = deque(maxlen=self._rate_limit_per_minute * 2)

        # HTTP Client
        self._client: Optional[httpx.AsyncClient] = None

        # Konfiguration validieren
        self._validate_config()

        self._initialized = True
        logger.info(
            "slack_service_initialized",
            enabled=self._enabled,
            has_webhook=bool(self._webhook_url),
            has_bot_token=bool(self._bot_token),
            default_channel=self._default_channel,
        )

    def _validate_config(self) -> None:
        """Validiert die Slack-Konfiguration."""
        if not self._enabled:
            return

        if not self._webhook_url and not self._bot_token:
            logger.warning(
                "slack_no_credentials",
                message="Slack aktiviert aber weder Webhook noch Bot-Token konfiguriert"
            )
            self._enabled = False
            return

        # Webhook-URL validieren
        if self._webhook_url:
            parsed = urlparse(self._webhook_url)
            if not parsed.scheme or not parsed.netloc:
                logger.error("slack_invalid_webhook_url")
                self._webhook_url = None
            elif not parsed.netloc.endswith("slack.com"):
                logger.warning(
                    "slack_non_slack_webhook",
                    message="Webhook-URL zeigt nicht auf slack.com"
                )

        # Bot-Token validieren
        if self._bot_token:
            if not self._bot_token.startswith("xoxb-"):
                logger.warning(
                    "slack_invalid_bot_token_format",
                    message="Bot-Token sollte mit 'xoxb-' beginnen"
                )

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-Initialisierung des HTTP-Clients."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=False,  # Sicherheit: Keine Redirects
            )
        return self._client

    def _check_rate_limit(self) -> bool:
        """
        Prueft ob Rate Limit erreicht ist.

        Sliding Window Algorithmus:
        - Entfernt Timestamps aelter als 60 Sekunden
        - Prueft ob Limit erreicht
        """
        now = time.time()
        window_start = now - 60

        # Alte Timestamps entfernen
        while self._rate_limit_window and self._rate_limit_window[0] < window_start:
            self._rate_limit_window.popleft()

        return len(self._rate_limit_window) < self._rate_limit_per_minute

    def _record_message(self) -> None:
        """Zeichnet eine gesendete Nachricht fuer Rate Limiting auf."""
        self._rate_limit_window.append(time.time())

    @property
    def is_enabled(self) -> bool:
        """Gibt zurueck ob Slack-Integration aktiv ist."""
        return self._enabled and (bool(self._webhook_url) or bool(self._bot_token))

    def should_send_notification(self, notification_type: str) -> bool:
        """Prueft ob ein Notification-Typ an Slack gesendet werden soll."""
        if not self.is_enabled:
            return False
        return notification_type in self._notification_types

    async def send_webhook_message(
        self,
        message: SlackMessage,
        retry_count: int = 3,
    ) -> bool:
        """
        Sendet eine Nachricht via Webhook.

        Args:
            message: Die zu sendende Nachricht
            retry_count: Anzahl Retry-Versuche bei temporaeren Fehlern

        Returns:
            True wenn erfolgreich, False sonst

        Raises:
            SlackRateLimitError: Wenn Rate Limit erreicht
            SlackServiceError: Bei anderen Fehlern
        """
        if not self._webhook_url:
            logger.warning("slack_no_webhook_configured")
            return False

        if not self._check_rate_limit():
            logger.warning("slack_rate_limit_reached")
            raise SlackRateLimitError("Slack Rate Limit erreicht")

        client = await self._get_client()

        # Payload vorbereiten
        payload: dict[str, Any] = {
            "text": message.text,
        }

        if message.blocks:
            payload["blocks"] = message.blocks

        if message.attachments:
            payload["attachments"] = [
                att.model_dump(exclude_none=True)
                for att in message.attachments
            ]

        # Senden mit Retry
        for attempt in range(retry_count):
            try:
                response = await client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    self._record_message()
                    logger.debug(
                        "slack_webhook_sent",
                        text_preview=message.text[:50] if message.text else None,
                    )
                    return True

                if response.status_code == 429:
                    # Rate Limited von Slack
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "slack_rate_limited_by_api",
                        retry_after=retry_after,
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise SlackRateLimitError(f"Slack API Rate Limit, retry nach {retry_after}s")

                logger.error(
                    "slack_webhook_error",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else None,
                )

            except httpx.TimeoutException:
                logger.warning(
                    "slack_webhook_timeout",
                    attempt=attempt + 1,
                    max_attempts=retry_count,
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

            except httpx.RequestError as e:
                logger.error(
                    "slack_webhook_request_error",
                    **safe_error_log(e),
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        return False

    async def send_bot_message(
        self,
        message: SlackMessage,
        channel: Optional[str] = None,
        retry_count: int = 3,
    ) -> Optional[str]:
        """
        Sendet eine Nachricht via Bot API.

        Args:
            message: Die zu sendende Nachricht
            channel: Ziel-Kanal (ueberschreibt message.channel)
            retry_count: Anzahl Retry-Versuche

        Returns:
            Message-ID wenn erfolgreich, None sonst
        """
        if not self._bot_token:
            logger.warning("slack_no_bot_token_configured")
            return None

        if not self._check_rate_limit():
            logger.warning("slack_rate_limit_reached")
            raise SlackRateLimitError("Slack Rate Limit erreicht")

        target_channel = channel or message.channel or self._default_channel

        client = await self._get_client()

        # Payload vorbereiten
        payload: dict[str, Any] = {
            "channel": target_channel,
            "text": message.text,
            "mrkdwn": message.mrkdwn,
            "unfurl_links": message.unfurl_links,
            "unfurl_media": message.unfurl_media,
        }

        if message.blocks:
            payload["blocks"] = message.blocks

        if message.attachments:
            payload["attachments"] = [
                att.model_dump(exclude_none=True)
                for att in message.attachments
            ]

        if message.thread_ts:
            payload["thread_ts"] = message.thread_ts

        # Senden mit Retry
        for attempt in range(retry_count):
            try:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._bot_token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                )

                data = response.json()

                if data.get("ok"):
                    self._record_message()
                    message_ts = data.get("ts")
                    logger.debug(
                        "slack_bot_message_sent",
                        channel=target_channel,
                        message_ts=message_ts,
                    )
                    return message_ts

                error = data.get("error", "unknown")
                logger.error(
                    "slack_bot_message_error",
                    error=error,
                    channel=target_channel,
                )

                # Nicht-retry-faehige Fehler
                if error in ("channel_not_found", "not_in_channel", "invalid_auth"):
                    return None

            except httpx.TimeoutException:
                logger.warning(
                    "slack_bot_timeout",
                    attempt=attempt + 1,
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

            except httpx.RequestError as e:
                logger.error(
                    "slack_bot_request_error",
                    **safe_error_log(e),
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue

        return None

    async def send_notification(
        self,
        notification_type: SlackNotificationType | str,
        title: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        priority: SlackMessagePriority = SlackMessagePriority.NORMAL,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> bool:
        """
        Sendet eine formatierte Benachrichtigung an Slack.

        Args:
            notification_type: Typ der Benachrichtigung
            title: Titel der Nachricht
            message: Haupttext
            context: Zusaetzliche Kontext-Daten
            priority: Prioritaet der Nachricht
            channel: Ziel-Kanal (optional)
            thread_ts: Thread-ID fuer Antworten (optional)

        Returns:
            True wenn erfolgreich
        """
        if not self.is_enabled:
            logger.debug("slack_not_enabled")
            return False

        # Typ als String
        type_str = notification_type.value if isinstance(notification_type, SlackNotificationType) else notification_type

        # Pruefen ob Typ aktiviert
        if not self.should_send_notification(type_str):
            logger.debug(
                "slack_notification_type_disabled",
                notification_type=type_str,
            )
            return False

        # Farbe basierend auf Prioritaet und Typ
        color = self._get_notification_color(type_str, priority)

        # Icon basierend auf Typ
        icon = self._get_notification_icon(type_str)

        # Blocks erstellen
        blocks = self._build_notification_blocks(
            title=title,
            message=message,
            notification_type=type_str,
            context=context,
            icon=icon,
        )

        # Attachment fuer Farbe
        attachment = SlackAttachment(
            color=color,
            footer=f"Ablage-System | {type_str}",
            ts=int(datetime.now(timezone.utc).timestamp()),
        )

        slack_message = SlackMessage(
            channel=channel or self._default_channel,
            text=f"{icon} {title}: {message}",  # Fallback
            blocks=blocks,
            attachments=[attachment],
            thread_ts=thread_ts,
        )

        # Bevorzugt Bot-API, Fallback auf Webhook
        if self._bot_token:
            result = await self.send_bot_message(slack_message, channel)
            return result is not None
        elif self._webhook_url:
            return await self.send_webhook_message(slack_message)

        return False

    def _get_notification_color(
        self,
        notification_type: str,
        priority: SlackMessagePriority,
    ) -> str:
        """Bestimmt die Farbe basierend auf Typ und Prioritaet."""
        # Prioritaet ueberschreibt
        if priority == SlackMessagePriority.URGENT:
            return "#FF0000"  # Rot
        if priority == SlackMessagePriority.HIGH:
            return "#FF8C00"  # Orange

        # Typ-basierte Farben
        type_colors = {
            "document_processed": "#36A64F",  # Gruen
            "document_error": "#FF0000",  # Rot
            "approval_required": "#FFA500",  # Orange
            "approval_completed": "#36A64F",  # Gruen
            "workflow_completed": "#36A64F",  # Gruen
            "high_risk_entity": "#FF0000",  # Rot
            "dunning_escalation": "#FF8C00",  # Orange
            "skonto_expiring": "#FFA500",  # Orange - Ablaufende Skonto-Fristen
            "report_generated": "#0066CC",  # Blau
            "system_alert": "#FF8C00",  # Orange
        }

        return type_colors.get(notification_type, "#808080")  # Grau default

    def _get_notification_icon(self, notification_type: str) -> str:
        """Bestimmt das Icon basierend auf Typ."""
        type_icons = {
            "document_processed": ":white_check_mark:",
            "document_error": ":x:",
            "approval_required": ":hourglass_flowing_sand:",
            "approval_completed": ":heavy_check_mark:",
            "workflow_completed": ":checkered_flag:",
            "high_risk_entity": ":warning:",
            "dunning_escalation": ":warning:",
            "skonto_expiring": ":moneybag:",
            "report_generated": ":bar_chart:",
            "system_alert": ":rotating_light:",
            "custom": ":bell:",
        }

        return type_icons.get(notification_type, ":bell:")

    def _build_notification_blocks(
        self,
        title: str,
        message: str,
        notification_type: str,
        context: Optional[dict[str, Any]],
        icon: str,
    ) -> list[dict[str, Any]]:
        """Erstellt Block Kit Blocks fuer die Nachricht."""
        blocks: list[dict[str, Any]] = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{icon} {title}",
                "emoji": True,
            },
        })

        # Haupttext
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message,
            },
        })

        # Kontext-Felder
        if context:
            fields = []
            for key, value in context.items():
                # Sensible Daten maskieren (NEVER log PII)
                if key.lower() in ("iban", "vat_id", "customer_number", "kundennr"):
                    continue

                # Wert formatieren
                if isinstance(value, bool):
                    display_value = "Ja" if value else "Nein"
                elif isinstance(value, float):
                    display_value = f"{value:.2f}"
                elif isinstance(value, datetime):
                    display_value = value.strftime("%d.%m.%Y %H:%M")
                else:
                    display_value = str(value)

                # Key formatieren (snake_case -> Title Case)
                display_key = key.replace("_", " ").title()

                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{display_key}:*\n{display_value}",
                })

            if fields:
                # Max 10 Felder pro Section
                for i in range(0, len(fields), 10):
                    blocks.append({
                        "type": "section",
                        "fields": fields[i:i+10],
                    })

        # Divider vor Footer
        blocks.append({"type": "divider"})

        # Timestamp und Typ
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":clock1: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} | Typ: `{notification_type}`",
                },
            ],
        })

        return blocks

    async def test_connection(self) -> dict[str, Any]:
        """
        Testet die Slack-Verbindung.

        Returns:
            Status-Dictionary mit Verbindungsinformationen
        """
        result = {
            "enabled": self._enabled,
            "webhook_configured": bool(self._webhook_url),
            "bot_token_configured": bool(self._bot_token),
            "default_channel": self._default_channel,
            "webhook_test": None,
            "bot_test": None,
        }

        if not self._enabled:
            return result

        # Webhook testen
        if self._webhook_url:
            try:
                test_msg = SlackMessage(
                    text=":test_tube: Ablage-System Verbindungstest",
                    blocks=[{
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":white_check_mark: Slack-Webhook Verbindung erfolgreich!",
                        },
                    }],
                )
                success = await self.send_webhook_message(test_msg, retry_count=1)
                result["webhook_test"] = "success" if success else "failed"
            except Exception as e:
                result["webhook_test"] = f"error: {safe_error_detail(e, 'Slack')}"

        # Bot testen
        if self._bot_token:
            try:
                client = await self._get_client()
                response = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {self._bot_token}"},
                )
                data = response.json()
                if data.get("ok"):
                    result["bot_test"] = {
                        "status": "success",
                        "team": data.get("team"),
                        "user": data.get("user"),
                    }
                else:
                    result["bot_test"] = {"status": "failed", "error": data.get("error")}
            except Exception as e:
                result["bot_test"] = {"status": "error", **safe_error_log(e)}

        return result

    async def close(self) -> None:
        """Schliesst den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton-Instanz
_slack_service: Optional[SlackService] = None


def get_slack_service() -> SlackService:
    """Factory-Funktion fuer Slack-Service Dependency Injection."""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service


async def send_slack_notification(
    notification_type: str,
    title: str,
    message: str,
    context: Optional[dict[str, Any]] = None,
    priority: str = "normal",
    channel: Optional[str] = None,
) -> bool:
    """
    Convenience-Funktion fuer einfaches Senden von Slack-Benachrichtigungen.

    Kann aus jedem Teil der Anwendung aufgerufen werden.

    Args:
        notification_type: Typ (document_processed, approval_required, etc.)
        title: Titel der Nachricht
        message: Haupttext
        context: Zusaetzliche Kontext-Daten
        priority: low, normal, high, urgent
        channel: Ziel-Kanal (optional)

    Returns:
        True wenn erfolgreich
    """
    service = get_slack_service()

    try:
        priority_enum = SlackMessagePriority(priority)
    except ValueError:
        priority_enum = SlackMessagePriority.NORMAL

    return await service.send_notification(
        notification_type=notification_type,
        title=title,
        message=message,
        context=context,
        priority=priority_enum,
        channel=channel,
    )
