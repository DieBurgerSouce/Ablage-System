"""
Microsoft Teams Integration Service.

Ermoeglicht Benachrichtigungen an Microsoft Teams-Kanaele ueber:
- Incoming Webhooks (einfach, keine App-Installation noetig)
- Adaptive Cards (reichhaltige Formatierung)

Feinpoliert und durchdacht - Enterprise Microsoft Teams-Integration.
"""

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel, Field

from app.core.config import settings as app_settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


class TeamsMessagePriority(str, Enum):
    """Prioritaet einer Teams-Nachricht."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TeamsNotificationType(str, Enum):
    """Typen von Teams-Benachrichtigungen."""
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
    PAYMENT_REMINDER = "payment_reminder"
    ERROR_NOTIFICATION = "error_notification"
    CUSTOM = "custom"


class TeamsAction(BaseModel):
    """Teams Adaptive Card Action."""
    type: str = Field(default="Action.OpenUrl", description="Action-Typ")
    title: str = Field(..., description="Button-Text")
    url: Optional[str] = Field(default=None, description="URL fuer OpenUrl Actions")
    data: Optional[dict[str, Any]] = Field(default=None, description="Daten fuer Submit Actions")


class TeamsSection(BaseModel):
    """Teams Nachricht Section (fuer Message Cards)."""
    title: Optional[str] = Field(default=None, description="Section-Titel")
    text: Optional[str] = Field(default=None, description="Section-Text")
    facts: list[dict[str, str]] = Field(default_factory=list, description="Fakten-Liste")
    image: Optional[str] = Field(default=None, description="Bild-URL")


class TeamsMessage(BaseModel):
    """Microsoft Teams Nachricht mit Adaptive Card Support."""
    title: str = Field(..., description="Nachricht-Titel")
    summary: str = Field(..., description="Zusammenfassung (Fallback-Text)")
    sections: list[TeamsSection] = Field(default_factory=list, description="Nachricht-Sections")
    actions: Optional[list[TeamsAction]] = Field(default=None, description="Aktions-Buttons")
    theme_color: str = Field(default="0076D7", description="Farbthema (Hex ohne #)")


class TeamsServiceError(Exception):
    """Fehler bei Teams-Operationen."""
    pass


class TeamsRateLimitError(TeamsServiceError):
    """Rate Limit erreicht."""
    pass


class TeamsWebhookError(TeamsServiceError):
    """Webhook-Konfigurationsfehler."""
    pass


class TeamsService:
    """
    Microsoft Teams-Integration Service.

    Features:
    - Webhook-basierte Benachrichtigungen
    - Adaptive Cards fuer reichhaltige Nachrichten
    - Rate Limiting mit Sliding Window (30/min)
    - Retry-Logik mit exponentiellem Backoff
    - Attachment-Support fuer Bilder

    Verwendung:
        teams = TeamsService()
        await teams.send_notification(
            notification_type=TeamsNotificationType.DOCUMENT_PROCESSED,
            title="Dokument verarbeitet",
            message="Rechnung #12345 wurde erfolgreich verarbeitet",
            context={"document_id": "...", "confidence": 0.95}
        )
    """

    _instance: Optional["TeamsService"] = None
    _lock = asyncio.Lock()

    # Rate Limiting
    _rate_limit_window: deque  # Timestamps der letzten Nachrichten
    _rate_limit_per_minute: int

    def __new__(cls) -> "TeamsService":
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
            app_settings.TEAMS_WEBHOOK_URL.get_secret_value()
            if app_settings.TEAMS_WEBHOOK_URL else None
        )
        self._default_channel = app_settings.TEAMS_DEFAULT_CHANNEL
        self._enabled = app_settings.TEAMS_ENABLED
        self._notification_types = set(app_settings.TEAMS_NOTIFICATION_TYPES)
        self._rate_limit_per_minute = app_settings.TEAMS_RATE_LIMIT_PER_MINUTE

        # Rate Limiting
        self._rate_limit_window = deque(maxlen=self._rate_limit_per_minute * 2)

        # HTTP Client
        self._client: Optional[httpx.AsyncClient] = None

        # Konfiguration validieren
        self._validate_config()

        self._initialized = True
        logger.info(
            "teams_service_initialized",
            enabled=self._enabled,
            has_webhook=bool(self._webhook_url),
            default_channel=self._default_channel,
        )

    def _validate_config(self) -> None:
        """Validiert die Teams-Konfiguration."""
        if not self._enabled:
            return

        if not self._webhook_url:
            logger.warning(
                "teams_no_credentials",
                message="Teams aktiviert aber kein Webhook konfiguriert"
            )
            self._enabled = False
            return

        # Webhook-URL validieren
        if self._webhook_url:
            parsed = urlparse(self._webhook_url)
            if not parsed.scheme or not parsed.netloc:
                logger.error("teams_invalid_webhook_url")
                self._webhook_url = None
            elif "webhook.office.com" not in parsed.netloc and "logic.azure.com" not in parsed.netloc:
                logger.warning(
                    "teams_non_microsoft_webhook",
                    message="Webhook-URL zeigt nicht auf Microsoft (webhook.office.com oder logic.azure.com)"
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
        """Gibt zurueck ob Teams-Integration aktiv ist."""
        return self._enabled and bool(self._webhook_url)

    def should_send_notification(self, notification_type: str) -> bool:
        """Prueft ob ein Notification-Typ an Teams gesendet werden soll."""
        if not self.is_enabled:
            return False
        return notification_type in self._notification_types

    def _build_adaptive_card(
        self,
        title: str,
        message: str,
        notification_type: str,
        context: Optional[dict[str, Any]],
        actions: Optional[list[TeamsAction]] = None,
        theme_color: str = "0076D7",
    ) -> dict[str, Any]:
        """
        Erstellt eine Adaptive Card fuer Teams.

        Args:
            title: Titel der Nachricht
            message: Haupttext
            notification_type: Typ der Benachrichtigung
            context: Zusaetzliche Kontext-Daten
            actions: Optionale Aktions-Buttons
            theme_color: Farbthema (Hex ohne #)

        Returns:
            Adaptive Card Payload
        """
        # Icon basierend auf Typ
        icon = self._get_notification_icon(notification_type)

        # Body-Elemente
        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": f"{icon} {title}",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": message,
                "wrap": True,
                "spacing": "Medium",
            },
        ]

        # Kontext-Fakten hinzufuegen
        if context:
            facts = []
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

                facts.append({
                    "title": display_key,
                    "value": display_value,
                })

            if facts:
                body.append({
                    "type": "FactSet",
                    "facts": facts,
                    "spacing": "Medium",
                })

        # Timestamp und Typ
        body.append({
            "type": "TextBlock",
            "text": f"Ablage-System | {notification_type} | {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}",
            "wrap": True,
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium",
        })

        # Adaptive Card Container
        card: dict[str, Any] = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body,
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }

        # Aktions-Buttons hinzufuegen
        if actions:
            card_actions = []
            for action in actions:
                if action.type == "Action.OpenUrl" and action.url:
                    card_actions.append({
                        "type": "Action.OpenUrl",
                        "title": action.title,
                        "url": action.url,
                    })
                elif action.type == "Action.Submit" and action.data:
                    card_actions.append({
                        "type": "Action.Submit",
                        "title": action.title,
                        "data": action.data,
                    })

            if card_actions:
                card["attachments"][0]["content"]["actions"] = card_actions

        return card

    def _build_message_card(
        self,
        title: str,
        message: str,
        notification_type: str,
        context: Optional[dict[str, Any]],
        actions: Optional[list[TeamsAction]] = None,
        theme_color: str = "0076D7",
    ) -> dict[str, Any]:
        """
        Erstellt eine Legacy Message Card (O365 Connector Card) fuer Teams.

        Fallback fuer aeltere Webhooks die keine Adaptive Cards unterstuetzen.

        Args:
            title: Titel der Nachricht
            message: Haupttext
            notification_type: Typ der Benachrichtigung
            context: Zusaetzliche Kontext-Daten
            actions: Optionale Aktions-Buttons
            theme_color: Farbthema (Hex ohne #)

        Returns:
            Message Card Payload
        """
        icon = self._get_notification_icon(notification_type)

        # Sections erstellen
        sections: list[dict[str, Any]] = [
            {
                "activityTitle": f"{icon} {title}",
                "text": message,
            }
        ]

        # Kontext-Fakten hinzufuegen
        if context:
            facts = []
            for key, value in context.items():
                # Sensible Daten maskieren
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

                display_key = key.replace("_", " ").title()

                facts.append({
                    "name": display_key,
                    "value": display_value,
                })

            if facts:
                sections[0]["facts"] = facts

        # Message Card
        card: dict[str, Any] = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": f"{title}: {message[:100]}...",
            "sections": sections,
        }

        # Potential Actions hinzufuegen
        if actions:
            potential_actions = []
            for action in actions:
                if action.type == "Action.OpenUrl" and action.url:
                    potential_actions.append({
                        "@type": "OpenUri",
                        "name": action.title,
                        "targets": [
                            {"os": "default", "uri": action.url}
                        ],
                    })

            if potential_actions:
                card["potentialAction"] = potential_actions

        return card

    def _get_notification_color(
        self,
        notification_type: str,
        priority: TeamsMessagePriority,
    ) -> str:
        """Bestimmt die Farbe basierend auf Typ und Prioritaet."""
        # Prioritaet ueberschreibt
        if priority == TeamsMessagePriority.URGENT:
            return "FF0000"  # Rot
        if priority == TeamsMessagePriority.HIGH:
            return "FF8C00"  # Orange

        # Typ-basierte Farben
        type_colors = {
            "document_processed": "36A64F",  # Gruen
            "document_error": "FF0000",  # Rot
            "approval_required": "FFA500",  # Orange
            "approval_completed": "36A64F",  # Gruen
            "workflow_completed": "36A64F",  # Gruen
            "high_risk_entity": "FF0000",  # Rot
            "dunning_escalation": "FF8C00",  # Orange
            "skonto_expiring": "FFA500",  # Orange
            "payment_reminder": "0076D7",  # Blau
            "report_generated": "0066CC",  # Blau
            "system_alert": "FF8C00",  # Orange
            "error_notification": "FF0000",  # Rot
        }

        return type_colors.get(notification_type, "0076D7")  # Microsoft Blau default

    def _get_notification_icon(self, notification_type: str) -> str:
        """Bestimmt das Icon (Emoji) basierend auf Typ."""
        type_icons = {
            "document_processed": "\u2705",  # Check mark
            "document_error": "\u274C",  # X mark
            "approval_required": "\u23F3",  # Hourglass
            "approval_completed": "\u2714\uFE0F",  # Heavy check
            "workflow_completed": "\U0001F3C1",  # Checkered flag
            "high_risk_entity": "\u26A0\uFE0F",  # Warning
            "dunning_escalation": "\u26A0\uFE0F",  # Warning
            "skonto_expiring": "\U0001F4B0",  # Money bag
            "payment_reminder": "\U0001F4B3",  # Credit card
            "report_generated": "\U0001F4CA",  # Bar chart
            "system_alert": "\U0001F6A8",  # Rotating light
            "error_notification": "\U0001F6AB",  # No entry
            "custom": "\U0001F514",  # Bell
        }

        return type_icons.get(notification_type, "\U0001F514")  # Bell default

    async def send_webhook_message(
        self,
        payload: dict[str, Any],
        retry_count: int = 3,
    ) -> bool:
        """
        Sendet eine Nachricht via Webhook.

        Args:
            payload: Die zu sendende Nachricht als JSON
            retry_count: Anzahl Retry-Versuche bei temporaeren Fehlern

        Returns:
            True wenn erfolgreich, False sonst

        Raises:
            TeamsRateLimitError: Wenn Rate Limit erreicht
            TeamsServiceError: Bei anderen Fehlern
        """
        if not self._webhook_url:
            logger.warning("teams_no_webhook_configured")
            return False

        if not self._check_rate_limit():
            logger.warning("teams_rate_limit_reached")
            raise TeamsRateLimitError("Teams Rate Limit erreicht")

        client = await self._get_client()

        # Senden mit Retry und exponentiellem Backoff
        for attempt in range(retry_count):
            try:
                response = await client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                # Teams Webhook gibt 200 bei Erfolg zurueck
                if response.status_code == 200:
                    self._record_message()
                    logger.debug(
                        "teams_webhook_sent",
                        status_code=response.status_code,
                    )
                    return True

                # Rate Limited
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "teams_rate_limited_by_api",
                        retry_after=retry_after,
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise TeamsRateLimitError(f"Teams API Rate Limit, retry nach {retry_after}s")

                logger.error(
                    "teams_webhook_error",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else None,
                )

            except httpx.TimeoutException:
                logger.warning(
                    "teams_webhook_timeout",
                    attempt=attempt + 1,
                    max_attempts=retry_count,
                )
                if attempt < retry_count - 1:
                    # Exponentieller Backoff: 1s, 2s, 4s
                    await asyncio.sleep(2 ** attempt)
                    continue

            except httpx.RequestError as e:
                logger.error(
                    "teams_webhook_request_error",
                    **safe_error_log(e),
                )
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue

        return False

    async def send_notification(
        self,
        notification_type: TeamsNotificationType | str,
        title: str,
        message: str,
        context: Optional[dict[str, Any]] = None,
        priority: TeamsMessagePriority = TeamsMessagePriority.NORMAL,
        actions: Optional[list[TeamsAction]] = None,
        use_adaptive_card: bool = True,
    ) -> bool:
        """
        Sendet eine formatierte Benachrichtigung an Teams.

        Args:
            notification_type: Typ der Benachrichtigung
            title: Titel der Nachricht
            message: Haupttext
            context: Zusaetzliche Kontext-Daten
            priority: Prioritaet der Nachricht
            actions: Optionale Aktions-Buttons
            use_adaptive_card: True fuer Adaptive Cards, False fuer Message Cards

        Returns:
            True wenn erfolgreich
        """
        if not self.is_enabled:
            logger.debug("teams_not_enabled")
            return False

        # Typ als String
        type_str = notification_type.value if isinstance(notification_type, TeamsNotificationType) else notification_type

        # Pruefen ob Typ aktiviert
        if not self.should_send_notification(type_str):
            logger.debug(
                "teams_notification_type_disabled",
                notification_type=type_str,
            )
            return False

        # Farbe basierend auf Prioritaet und Typ
        color = self._get_notification_color(type_str, priority)

        # Payload erstellen (Adaptive Card oder Message Card)
        if use_adaptive_card:
            payload = self._build_adaptive_card(
                title=title,
                message=message,
                notification_type=type_str,
                context=context,
                actions=actions,
                theme_color=color,
            )
        else:
            payload = self._build_message_card(
                title=title,
                message=message,
                notification_type=type_str,
                context=context,
                actions=actions,
                theme_color=color,
            )

        return await self.send_webhook_message(payload)

    async def send_document_notification(
        self,
        document_id: str,
        document_name: str,
        success: bool,
        confidence: Optional[float] = None,
        error_message: Optional[str] = None,
        document_url: Optional[str] = None,
    ) -> bool:
        """
        Sendet eine Dokument-Verarbeitungsbenachrichtigung.

        Args:
            document_id: Dokument-ID
            document_name: Dokumentname
            success: True wenn erfolgreich verarbeitet
            confidence: OCR-Konfidenz (0-1)
            error_message: Fehlermeldung bei Misserfolg
            document_url: URL zum Dokument

        Returns:
            True wenn erfolgreich
        """
        if success:
            notification_type = TeamsNotificationType.DOCUMENT_PROCESSED
            title = "Dokument verarbeitet"
            message = f"Das Dokument **{document_name}** wurde erfolgreich verarbeitet."
            context = {"dokument": document_name}
            if confidence:
                context["konfidenz"] = f"{confidence * 100:.1f}%"
        else:
            notification_type = TeamsNotificationType.DOCUMENT_ERROR
            title = "Dokumentfehler"
            message = f"Bei der Verarbeitung von **{document_name}** ist ein Fehler aufgetreten."
            context = {"dokument": document_name}
            if error_message:
                context["fehler"] = error_message[:100]

        # Aktion: Dokument oeffnen
        actions = None
        if document_url:
            actions = [
                TeamsAction(
                    type="Action.OpenUrl",
                    title="Dokument oeffnen",
                    url=document_url,
                )
            ]

        return await self.send_notification(
            notification_type=notification_type,
            title=title,
            message=message,
            context=context,
            priority=TeamsMessagePriority.HIGH if not success else TeamsMessagePriority.NORMAL,
            actions=actions,
        )

    async def send_approval_notification(
        self,
        title: str,
        description: str,
        requester: str,
        document_url: Optional[str] = None,
        approve_url: Optional[str] = None,
        reject_url: Optional[str] = None,
    ) -> bool:
        """
        Sendet eine Genehmigungsanfrage.

        Args:
            title: Titel der Anfrage
            description: Beschreibung
            requester: Anfordernde Person
            document_url: URL zum Dokument
            approve_url: URL zum Genehmigen
            reject_url: URL zum Ablehnen

        Returns:
            True wenn erfolgreich
        """
        context = {
            "angefordert_von": requester,
            "zeitpunkt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M"),
        }

        actions = []
        if approve_url:
            actions.append(TeamsAction(
                type="Action.OpenUrl",
                title="Genehmigen",
                url=approve_url,
            ))
        if reject_url:
            actions.append(TeamsAction(
                type="Action.OpenUrl",
                title="Ablehnen",
                url=reject_url,
            ))
        if document_url:
            actions.append(TeamsAction(
                type="Action.OpenUrl",
                title="Dokument ansehen",
                url=document_url,
            ))

        return await self.send_notification(
            notification_type=TeamsNotificationType.APPROVAL_REQUIRED,
            title=title,
            message=description,
            context=context,
            priority=TeamsMessagePriority.HIGH,
            actions=actions if actions else None,
        )

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "medium",
        alert_url: Optional[str] = None,
    ) -> bool:
        """
        Sendet einen System-Alert.

        Args:
            title: Alert-Titel
            message: Alert-Nachricht
            severity: Schweregrad (low, medium, high, critical)
            alert_url: URL fuer weitere Details

        Returns:
            True wenn erfolgreich
        """
        # Prioritaet basierend auf Schweregrad
        priority_map = {
            "low": TeamsMessagePriority.LOW,
            "medium": TeamsMessagePriority.NORMAL,
            "high": TeamsMessagePriority.HIGH,
            "critical": TeamsMessagePriority.URGENT,
        }
        priority = priority_map.get(severity, TeamsMessagePriority.NORMAL)

        context = {
            "schweregrad": severity.upper(),
            "zeitpunkt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M"),
        }

        actions = None
        if alert_url:
            actions = [
                TeamsAction(
                    type="Action.OpenUrl",
                    title="Details anzeigen",
                    url=alert_url,
                )
            ]

        return await self.send_notification(
            notification_type=TeamsNotificationType.SYSTEM_ALERT,
            title=title,
            message=message,
            context=context,
            priority=priority,
            actions=actions,
        )

    async def send_payment_reminder(
        self,
        invoice_number: str,
        amount: float,
        due_date: datetime,
        days_overdue: int,
        customer_name: str,
        invoice_url: Optional[str] = None,
    ) -> bool:
        """
        Sendet eine Zahlungserinnerung.

        Args:
            invoice_number: Rechnungsnummer
            amount: Rechnungsbetrag
            due_date: Faelligkeitsdatum
            days_overdue: Tage ueberfaellig
            customer_name: Kundenname
            invoice_url: URL zur Rechnung

        Returns:
            True wenn erfolgreich
        """
        title = f"Zahlungserinnerung: Rechnung {invoice_number}"
        message = f"Die Rechnung **{invoice_number}** ist seit **{days_overdue} Tagen** ueberfaellig."

        context = {
            "rechnungsnummer": invoice_number,
            "betrag": f"{amount:.2f} EUR",
            "faellig_am": due_date.strftime("%d.%m.%Y"),
            "tage_ueberfaellig": days_overdue,
            "kunde": customer_name,
        }

        actions = None
        if invoice_url:
            actions = [
                TeamsAction(
                    type="Action.OpenUrl",
                    title="Rechnung oeffnen",
                    url=invoice_url,
                )
            ]

        # Prioritaet basierend auf Ueberfaelligkeit
        if days_overdue > 30:
            priority = TeamsMessagePriority.URGENT
        elif days_overdue > 14:
            priority = TeamsMessagePriority.HIGH
        else:
            priority = TeamsMessagePriority.NORMAL

        return await self.send_notification(
            notification_type=TeamsNotificationType.PAYMENT_REMINDER,
            title=title,
            message=message,
            context=context,
            priority=priority,
            actions=actions,
        )

    async def test_connection(self) -> dict[str, Any]:
        """
        Testet die Teams-Verbindung.

        Returns:
            Status-Dictionary mit Verbindungsinformationen
        """
        result = {
            "enabled": self._enabled,
            "webhook_configured": bool(self._webhook_url),
            "default_channel": self._default_channel,
            "webhook_test": None,
        }

        if not self._enabled:
            return result

        # Webhook testen
        if self._webhook_url:
            try:
                payload = self._build_adaptive_card(
                    title="Verbindungstest",
                    message="Ablage-System Teams-Integration Verbindungstest erfolgreich!",
                    notification_type="system_alert",
                    context={"zeitpunkt": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")},
                    theme_color="36A64F",  # Gruen
                )
                success = await self.send_webhook_message(payload, retry_count=1)
                result["webhook_test"] = "success" if success else "failed"
            except Exception as e:
                result["webhook_test"] = f"error: {safe_error_detail(e, 'Teams')}"

        return result

    async def close(self) -> None:
        """Schliesst den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton-Instanz
_teams_service: Optional[TeamsService] = None


def get_teams_service() -> TeamsService:
    """Factory-Funktion fuer Teams-Service Dependency Injection."""
    global _teams_service
    if _teams_service is None:
        _teams_service = TeamsService()
    return _teams_service


async def send_teams_notification(
    notification_type: str,
    title: str,
    message: str,
    context: Optional[dict[str, Any]] = None,
    priority: str = "normal",
    actions: Optional[list[dict[str, Any]]] = None,
) -> bool:
    """
    Convenience-Funktion fuer einfaches Senden von Teams-Benachrichtigungen.

    Kann aus jedem Teil der Anwendung aufgerufen werden.

    Args:
        notification_type: Typ (document_processed, approval_required, etc.)
        title: Titel der Nachricht
        message: Haupttext
        context: Zusaetzliche Kontext-Daten
        priority: low, normal, high, urgent
        actions: Optionale Aktions-Buttons

    Returns:
        True wenn erfolgreich
    """
    service = get_teams_service()

    try:
        priority_enum = TeamsMessagePriority(priority)
    except ValueError:
        priority_enum = TeamsMessagePriority.NORMAL

    # Actions konvertieren
    teams_actions = None
    if actions:
        teams_actions = [
            TeamsAction(**action) for action in actions
        ]

    return await service.send_notification(
        notification_type=notification_type,
        title=title,
        message=message,
        context=context,
        priority=priority_enum,
        actions=teams_actions,
    )
