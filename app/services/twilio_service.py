# -*- coding: utf-8 -*-
"""
Twilio SMS/WhatsApp Integration Service fuer Ablage-System.

Enterprise-grade Benachrichtigungen ueber:
- SMS fuer kritische Alerts (High/Critical Severity)
- WhatsApp Business fuer reichhaltige Nachrichten
- Rate Limiting und Budget-Schutz
- GDPR-konformes Opt-in pro Benutzer
- Eskalationsketten: Email -> Slack -> Teams -> SMS

Feinpoliert und durchdacht - Kritische Benachrichtigungen zuverlaessig zugestellt.
"""

import asyncio
import re
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings as app_settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Phone number validation pattern (E.164 format)
E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")

# Twilio API endpoints
TWILIO_SMS_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
TWILIO_LOOKUP_API = "https://lookups.twilio.com/v2/PhoneNumbers/{phone_number}"

# Cost estimates per message (EUR, approximate)
SMS_COST_EUR = Decimal("0.075")  # ~0.075 EUR per SMS segment
WHATSAPP_COST_EUR = Decimal("0.05")  # ~0.05 EUR per WhatsApp message


class TwilioMessageType(str, Enum):
    """Typ der Twilio-Nachricht."""
    SMS = "sms"
    WHATSAPP = "whatsapp"


class TwilioMessagePriority(str, Enum):
    """Prioritaet einer Twilio-Nachricht."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TwilioNotificationType(str, Enum):
    """Typen von Twilio-Benachrichtigungen."""
    CRITICAL_ALERT = "critical_alert"
    HIGH_RISK_ENTITY = "high_risk_entity"
    FRAUD_DETECTED = "fraud_detected"
    SECURITY_INCIDENT = "security_incident"
    SYSTEM_DOWN = "system_down"
    APPROVAL_URGENT = "approval_urgent"
    PAYMENT_CRITICAL = "payment_critical"
    ESCALATION = "escalation"
    CUSTOM = "custom"


class TwilioDeliveryStatus(str, Enum):
    """Lieferstatus einer Twilio-Nachricht."""
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    FAILED = "failed"


# =============================================================================
# Pydantic Models
# =============================================================================

class TwilioUserPreferences(BaseModel):
    """Benutzer-Praeferenzen fuer Twilio-Benachrichtigungen (GDPR-konform)."""

    # Opt-in Status (GDPR: explizite Zustimmung erforderlich)
    sms_opt_in: bool = Field(
        default=False,
        description="Benutzer hat SMS-Benachrichtigungen explizit aktiviert"
    )
    whatsapp_opt_in: bool = Field(
        default=False,
        description="Benutzer hat WhatsApp-Benachrichtigungen explizit aktiviert"
    )

    # Telefonnummern (E.164 Format: +49...)
    phone_number: Optional[str] = Field(
        default=None,
        description="Primaere Telefonnummer fuer SMS (E.164 Format)"
    )
    whatsapp_number: Optional[str] = Field(
        default=None,
        description="WhatsApp-Nummer (E.164 Format, kann gleich phone_number sein)"
    )

    # Benachrichtigungstypen die erlaubt sind
    allowed_notification_types: list[str] = Field(
        default_factory=lambda: [
            TwilioNotificationType.CRITICAL_ALERT.value,
            TwilioNotificationType.FRAUD_DETECTED.value,
            TwilioNotificationType.SECURITY_INCIDENT.value,
        ],
        description="Erlaubte Notification-Typen (GDPR: granulare Kontrolle)"
    )

    # Ruhezeiten (keine Nachrichten waehrend dieser Zeit)
    quiet_hours_enabled: bool = Field(
        default=True,
        description="Ruhezeiten aktivieren"
    )
    quiet_hours_start: int = Field(
        default=22,
        ge=0,
        le=23,
        description="Beginn der Ruhezeit (Stunde, 0-23)"
    )
    quiet_hours_end: int = Field(
        default=7,
        ge=0,
        le=23,
        description="Ende der Ruhezeit (Stunde, 0-23)"
    )

    # Zeitzone fuer Ruhezeiten
    timezone: str = Field(
        default="Europe/Berlin",
        description="Zeitzone des Benutzers"
    )

    # Opt-in Zeitpunkte (GDPR: Nachweis der Zustimmung)
    sms_opt_in_at: Optional[datetime] = Field(
        default=None,
        description="Zeitpunkt der SMS Opt-in Zustimmung"
    )
    whatsapp_opt_in_at: Optional[datetime] = Field(
        default=None,
        description="Zeitpunkt der WhatsApp Opt-in Zustimmung"
    )

    @field_validator("phone_number", "whatsapp_number", mode="before")
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        """Validiert Telefonnummer im E.164 Format."""
        if v is None or v == "":
            return None
        # Bereinigen: Leerzeichen und Bindestriche entfernen
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not E164_PATTERN.match(cleaned):
            raise ValueError(
                f"Telefonnummer muss im E.164 Format sein (z.B. +4915123456789), "
                f"erhalten: {v}"
            )
        return cleaned


class TwilioMessage(BaseModel):
    """Twilio-Nachricht mit Metadaten."""

    to: str = Field(..., description="Empfaenger-Telefonnummer (E.164)")
    body: str = Field(..., max_length=1600, description="Nachrichtentext")
    message_type: TwilioMessageType = Field(
        default=TwilioMessageType.SMS,
        description="SMS oder WhatsApp"
    )
    notification_type: Optional[str] = Field(
        default=None,
        description="Notification-Typ fuer Tracking"
    )
    priority: TwilioMessagePriority = Field(
        default=TwilioMessagePriority.HIGH,
        description="Prioritaet der Nachricht"
    )
    company_id: Optional[UUID] = Field(
        default=None,
        description="Mandanten-ID fuer Tracking"
    )
    user_id: Optional[UUID] = Field(
        default=None,
        description="Benutzer-ID fuer Tracking"
    )
    reference_id: Optional[str] = Field(
        default=None,
        description="Referenz-ID (z.B. Alert-ID)"
    )


class TwilioSendResult(BaseModel):
    """Ergebnis eines Twilio-Sendevorgangs."""

    success: bool = Field(..., description="Erfolgreich gesendet")
    message_sid: Optional[str] = Field(
        default=None,
        description="Twilio Message SID"
    )
    status: Optional[TwilioDeliveryStatus] = Field(
        default=None,
        description="Lieferstatus"
    )
    error_code: Optional[int] = Field(
        default=None,
        description="Twilio-Fehlercode"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Fehlermeldung"
    )
    cost_eur: Optional[Decimal] = Field(
        default=None,
        description="Geschaetzte Kosten in EUR"
    )
    segments: int = Field(
        default=1,
        description="Anzahl SMS-Segmente"
    )


class TwilioCostTracking(BaseModel):
    """Kostentracking fuer Twilio-Nutzung."""

    daily_sms_count: int = Field(default=0)
    daily_whatsapp_count: int = Field(default=0)
    daily_cost_eur: Decimal = Field(default=Decimal("0"))
    monthly_sms_count: int = Field(default=0)
    monthly_whatsapp_count: int = Field(default=0)
    monthly_cost_eur: Decimal = Field(default=Decimal("0"))
    last_reset_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Service Errors
# =============================================================================

class TwilioServiceError(Exception):
    """Basis-Fehler fuer Twilio-Operationen."""
    pass


class TwilioRateLimitError(TwilioServiceError):
    """Rate Limit erreicht."""
    pass


class TwilioBudgetExceededError(TwilioServiceError):
    """Budget-Limit ueberschritten."""
    pass


class TwilioOptInRequiredError(TwilioServiceError):
    """Benutzer hat kein Opt-in fuer diesen Kanal."""
    pass


class TwilioQuietHoursError(TwilioServiceError):
    """Nachricht waehrend Ruhezeiten nicht erlaubt."""
    pass


class TwilioConfigurationError(TwilioServiceError):
    """Twilio nicht korrekt konfiguriert."""
    pass


# =============================================================================
# Twilio Service
# =============================================================================

class TwilioService:
    """
    Twilio SMS/WhatsApp Integration Service.

    Features:
    - SMS fuer kritische Alerts (nur High/Critical Severity)
    - WhatsApp Business fuer reichhaltige Nachrichten
    - Rate Limiting mit Sliding Window (Budget-Schutz)
    - GDPR-konformes Opt-in pro Benutzer
    - Ruhezeiten-Respektierung
    - Eskalationsketten-Integration
    - Kostentracking pro Nachricht

    Verwendung:
        twilio = TwilioService()
        result = await twilio.send_critical_alert(
            phone_number="+4915123456789",
            title="Kritischer Alert",
            message="Sicherheitsvorfall erkannt",
            company_id=company_id,
        )
    """

    _instance: Optional["TwilioService"] = None
    _lock = asyncio.Lock()

    # Rate Limiting
    _rate_limit_window: deque  # Timestamps der letzten Nachrichten
    _rate_limit_per_day: int  # Max SMS pro Tag

    def __new__(cls) -> "TwilioService":
        """Singleton-Pattern fuer Thread-Safety."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisierung (einmalig)."""
        if self._initialized:
            return

        # Twilio-Credentials aus Konfiguration
        self._account_sid: Optional[str] = getattr(
            app_settings, "TWILIO_ACCOUNT_SID", None
        )
        self._auth_token: Optional[str] = None
        if hasattr(app_settings, "TWILIO_AUTH_TOKEN") and app_settings.TWILIO_AUTH_TOKEN:
            self._auth_token = app_settings.TWILIO_AUTH_TOKEN.get_secret_value()

        self._phone_number: Optional[str] = getattr(
            app_settings, "TWILIO_PHONE_NUMBER", None
        )
        self._whatsapp_number: Optional[str] = getattr(
            app_settings, "TWILIO_WHATSAPP_NUMBER", None
        )

        # Feature-Flags
        self._enabled: bool = getattr(app_settings, "TWILIO_ENABLED", False)
        self._max_sms_per_day: int = getattr(
            app_settings, "TWILIO_MAX_SMS_PER_DAY", 100
        )
        self._max_monthly_budget_eur: Decimal = Decimal(
            str(getattr(app_settings, "TWILIO_MAX_MONTHLY_BUDGET_EUR", "50"))
        )

        # Rate Limiting
        self._rate_limit_window = deque(maxlen=self._max_sms_per_day * 2)
        self._rate_limit_per_day = self._max_sms_per_day

        # Kostentracking
        self._cost_tracking = TwilioCostTracking()

        # HTTP Client
        self._client: Optional[httpx.AsyncClient] = None

        # Konfiguration validieren
        self._validate_config()

        self._initialized = True
        logger.info(
            "twilio_service_initialized",
            enabled=self._enabled,
            has_account_sid=bool(self._account_sid),
            has_phone_number=bool(self._phone_number),
            has_whatsapp_number=bool(self._whatsapp_number),
            max_sms_per_day=self._max_sms_per_day,
        )

    def _validate_config(self) -> None:
        """Validiert die Twilio-Konfiguration."""
        if not self._enabled:
            return

        if not self._account_sid or not self._auth_token:
            logger.warning(
                "twilio_no_credentials",
                message="Twilio aktiviert aber Credentials nicht konfiguriert"
            )
            self._enabled = False
            return

        if not self._phone_number:
            logger.warning(
                "twilio_no_phone_number",
                message="Twilio aktiviert aber keine Absender-Telefonnummer konfiguriert"
            )
            self._enabled = False
            return

        # Telefonnummer validieren
        if not E164_PATTERN.match(self._phone_number):
            logger.error(
                "twilio_invalid_phone_number",
                phone_number=self._phone_number[:6] + "***"
            )
            self._phone_number = None

        # WhatsApp-Nummer validieren (optional)
        if self._whatsapp_number:
            # WhatsApp-Nummer muss mit "whatsapp:" prefix sein
            if not self._whatsapp_number.startswith("whatsapp:"):
                self._whatsapp_number = f"whatsapp:{self._whatsapp_number}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-Initialisierung des HTTP-Clients."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                auth=(self._account_sid, self._auth_token),
                follow_redirects=False,
            )
        return self._client

    def _check_rate_limit(self) -> bool:
        """
        Prueft ob taegliches Rate Limit erreicht ist.

        Sliding Window Algorithmus:
        - Entfernt Timestamps aelter als 24 Stunden
        - Prueft ob Limit erreicht
        """
        now = time.time()
        window_start = now - (24 * 60 * 60)  # 24 Stunden

        # Alte Timestamps entfernen
        while self._rate_limit_window and self._rate_limit_window[0] < window_start:
            self._rate_limit_window.popleft()

        return len(self._rate_limit_window) < self._rate_limit_per_day

    def _record_message(self, cost: Decimal, message_type: TwilioMessageType) -> None:
        """Zeichnet eine gesendete Nachricht fuer Rate Limiting und Kosten auf."""
        self._rate_limit_window.append(time.time())

        # Reset taeglich
        now = datetime.now(timezone.utc)
        if now.date() > self._cost_tracking.last_reset_date.date():
            self._cost_tracking.daily_sms_count = 0
            self._cost_tracking.daily_whatsapp_count = 0
            self._cost_tracking.daily_cost_eur = Decimal("0")
            self._cost_tracking.last_reset_date = now

        # Reset monatlich
        if now.month != self._cost_tracking.last_reset_date.month:
            self._cost_tracking.monthly_sms_count = 0
            self._cost_tracking.monthly_whatsapp_count = 0
            self._cost_tracking.monthly_cost_eur = Decimal("0")

        # Tracking aktualisieren
        if message_type == TwilioMessageType.SMS:
            self._cost_tracking.daily_sms_count += 1
            self._cost_tracking.monthly_sms_count += 1
        else:
            self._cost_tracking.daily_whatsapp_count += 1
            self._cost_tracking.monthly_whatsapp_count += 1

        self._cost_tracking.daily_cost_eur += cost
        self._cost_tracking.monthly_cost_eur += cost

    def _check_budget(self) -> bool:
        """Prueft ob monatliches Budget ueberschritten wuerde."""
        return self._cost_tracking.monthly_cost_eur < self._max_monthly_budget_eur

    def _calculate_sms_segments(self, text: str) -> int:
        """
        Berechnet die Anzahl der SMS-Segmente.

        GSM-7: 160 Zeichen pro Segment (153 wenn mehrere Segmente)
        UCS-2: 70 Zeichen pro Segment (67 wenn mehrere Segmente)
        """
        # Pruefen ob Text nur GSM-7 Zeichen enthaelt
        gsm7_chars = (
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        is_gsm7 = all(c in gsm7_chars for c in text)

        if is_gsm7:
            if len(text) <= 160:
                return 1
            return (len(text) + 152) // 153
        else:
            if len(text) <= 70:
                return 1
            return (len(text) + 66) // 67

    def _is_quiet_hours(
        self,
        preferences: TwilioUserPreferences,
    ) -> bool:
        """Prueft ob aktuelle Zeit in Ruhezeiten faellt."""
        if not preferences.quiet_hours_enabled:
            return False

        try:
            # Aktuelle Stunde in User-Zeitzone
            import zoneinfo
            user_tz = zoneinfo.ZoneInfo(preferences.timezone)
            user_now = datetime.now(user_tz)
            current_hour = user_now.hour

            start = preferences.quiet_hours_start
            end = preferences.quiet_hours_end

            # Ruhezeiten koennen Mitternacht ueberspannen
            if start <= end:
                # z.B. 22:00 - 07:00 -> nicht ueber Mitternacht
                return start <= current_hour < end
            else:
                # z.B. 22:00 - 07:00 -> ueber Mitternacht
                return current_hour >= start or current_hour < end

        except Exception as e:
            logger.warning(
                "twilio_quiet_hours_check_failed",
                **safe_error_log(e),
            )
            return False

    @property
    def is_enabled(self) -> bool:
        """Gibt zurueck ob Twilio-Integration aktiv ist."""
        return self._enabled and bool(self._account_sid) and bool(self._auth_token)

    def validate_user_opt_in(
        self,
        preferences: TwilioUserPreferences,
        message_type: TwilioMessageType,
        notification_type: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Validiert Benutzer-Opt-in fuer den Nachrichtentyp.

        Args:
            preferences: Benutzer-Praeferenzen
            message_type: SMS oder WhatsApp
            notification_type: Typ der Benachrichtigung

        Returns:
            Tuple (ist_erlaubt, fehlermeldung)
        """
        # Opt-in pruefen
        if message_type == TwilioMessageType.SMS:
            if not preferences.sms_opt_in:
                return False, "SMS-Benachrichtigungen nicht aktiviert"
            if not preferences.phone_number:
                return False, "Keine Telefonnummer hinterlegt"
        else:
            if not preferences.whatsapp_opt_in:
                return False, "WhatsApp-Benachrichtigungen nicht aktiviert"
            if not preferences.whatsapp_number:
                return False, "Keine WhatsApp-Nummer hinterlegt"

        # Notification-Typ pruefen
        if notification_type not in preferences.allowed_notification_types:
            return False, f"Benachrichtigungstyp '{notification_type}' nicht erlaubt"

        return True, None

    async def send_sms(
        self,
        message: TwilioMessage,
        preferences: Optional[TwilioUserPreferences] = None,
        override_quiet_hours: bool = False,
        override_opt_in: bool = False,
    ) -> TwilioSendResult:
        """
        Sendet eine SMS-Nachricht.

        Args:
            message: Die zu sendende Nachricht
            preferences: Benutzer-Praeferenzen (optional fuer System-Nachrichten)
            override_quiet_hours: Ruhezeiten ignorieren (nur fuer kritische Alerts)
            override_opt_in: Opt-in ignorieren (nur fuer System-Nachrichten)

        Returns:
            Ergebnis des Sendevorgangs
        """
        if not self.is_enabled:
            logger.warning("twilio_not_enabled")
            return TwilioSendResult(
                success=False,
                error_message="Twilio nicht aktiviert"
            )

        # Validierungen
        if preferences and not override_opt_in:
            is_valid, error = self.validate_user_opt_in(
                preferences,
                TwilioMessageType.SMS,
                message.notification_type or "custom",
            )
            if not is_valid:
                return TwilioSendResult(
                    success=False,
                    error_message=error
                )

        if preferences and not override_quiet_hours:
            if self._is_quiet_hours(preferences):
                # Bei kritischen Alerts trotzdem senden
                if message.priority != TwilioMessagePriority.CRITICAL:
                    return TwilioSendResult(
                        success=False,
                        error_message="Ruhezeiten aktiv"
                    )

        # Rate Limit pruefen
        if not self._check_rate_limit():
            logger.warning("twilio_rate_limit_reached")
            return TwilioSendResult(
                success=False,
                error_code=429,
                error_message="Taegliches SMS-Limit erreicht"
            )

        # Budget pruefen
        if not self._check_budget():
            logger.warning("twilio_budget_exceeded")
            return TwilioSendResult(
                success=False,
                error_message="Monatliches Budget ueberschritten"
            )

        # SMS-Segmente berechnen
        segments = self._calculate_sms_segments(message.body)
        estimated_cost = SMS_COST_EUR * segments

        # SMS senden
        client = await self._get_client()

        try:
            response = await client.post(
                TWILIO_SMS_API.format(account_sid=self._account_sid),
                data={
                    "To": message.to,
                    "From": self._phone_number,
                    "Body": message.body,
                },
            )

            if response.status_code in (200, 201):
                data = response.json()
                self._record_message(estimated_cost, TwilioMessageType.SMS)

                logger.info(
                    "twilio_sms_sent",
                    message_sid=data.get("sid"),
                    to=message.to[:6] + "***",
                    segments=segments,
                    notification_type=message.notification_type,
                )

                return TwilioSendResult(
                    success=True,
                    message_sid=data.get("sid"),
                    status=TwilioDeliveryStatus(data.get("status", "queued")),
                    cost_eur=estimated_cost,
                    segments=segments,
                )

            # Fehler
            data = response.json()
            error_code = data.get("code")
            error_message = data.get("message", "Unbekannter Fehler")

            logger.error(
                "twilio_sms_error",
                status_code=response.status_code,
                error_code=error_code,
                error_message=error_message[:100],
            )

            return TwilioSendResult(
                success=False,
                error_code=error_code,
                error_message=error_message,
            )

        except httpx.TimeoutException:
            logger.error("twilio_sms_timeout")
            return TwilioSendResult(
                success=False,
                error_message="Timeout bei Twilio-API"
            )

        except httpx.RequestError as e:
            logger.error(
                "twilio_sms_request_error",
                **safe_error_log(e),
            )
            return TwilioSendResult(
                success=False,
                error_message=safe_error_detail(e, "Twilio-SMS")
            )

    async def send_whatsapp(
        self,
        message: TwilioMessage,
        preferences: Optional[TwilioUserPreferences] = None,
        override_quiet_hours: bool = False,
        override_opt_in: bool = False,
    ) -> TwilioSendResult:
        """
        Sendet eine WhatsApp-Nachricht.

        Args:
            message: Die zu sendende Nachricht
            preferences: Benutzer-Praeferenzen
            override_quiet_hours: Ruhezeiten ignorieren
            override_opt_in: Opt-in ignorieren

        Returns:
            Ergebnis des Sendevorgangs
        """
        if not self.is_enabled:
            logger.warning("twilio_not_enabled")
            return TwilioSendResult(
                success=False,
                error_message="Twilio nicht aktiviert"
            )

        if not self._whatsapp_number:
            return TwilioSendResult(
                success=False,
                error_message="WhatsApp nicht konfiguriert"
            )

        # Validierungen
        if preferences and not override_opt_in:
            is_valid, error = self.validate_user_opt_in(
                preferences,
                TwilioMessageType.WHATSAPP,
                message.notification_type or "custom",
            )
            if not is_valid:
                return TwilioSendResult(
                    success=False,
                    error_message=error
                )

        if preferences and not override_quiet_hours:
            if self._is_quiet_hours(preferences):
                if message.priority != TwilioMessagePriority.CRITICAL:
                    return TwilioSendResult(
                        success=False,
                        error_message="Ruhezeiten aktiv"
                    )

        # Rate Limit pruefen
        if not self._check_rate_limit():
            return TwilioSendResult(
                success=False,
                error_code=429,
                error_message="Taegliches Nachrichtenlimit erreicht"
            )

        # Budget pruefen
        if not self._check_budget():
            return TwilioSendResult(
                success=False,
                error_message="Monatliches Budget ueberschritten"
            )

        # WhatsApp-Nummer formatieren
        to_number = message.to
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        # WhatsApp senden
        client = await self._get_client()

        try:
            response = await client.post(
                TWILIO_SMS_API.format(account_sid=self._account_sid),
                data={
                    "To": to_number,
                    "From": self._whatsapp_number,
                    "Body": message.body,
                },
            )

            if response.status_code in (200, 201):
                data = response.json()
                self._record_message(WHATSAPP_COST_EUR, TwilioMessageType.WHATSAPP)

                logger.info(
                    "twilio_whatsapp_sent",
                    message_sid=data.get("sid"),
                    to=message.to[:6] + "***",
                    notification_type=message.notification_type,
                )

                return TwilioSendResult(
                    success=True,
                    message_sid=data.get("sid"),
                    status=TwilioDeliveryStatus(data.get("status", "queued")),
                    cost_eur=WHATSAPP_COST_EUR,
                    segments=1,
                )

            # Fehler
            data = response.json()
            error_code = data.get("code")
            error_message = data.get("message", "Unbekannter Fehler")

            logger.error(
                "twilio_whatsapp_error",
                status_code=response.status_code,
                error_code=error_code,
            )

            return TwilioSendResult(
                success=False,
                error_code=error_code,
                error_message=error_message,
            )

        except httpx.TimeoutException:
            logger.error("twilio_whatsapp_timeout")
            return TwilioSendResult(
                success=False,
                error_message="Timeout bei Twilio-API"
            )

        except httpx.RequestError as e:
            logger.error(
                "twilio_whatsapp_request_error",
                **safe_error_log(e),
            )
            return TwilioSendResult(
                success=False,
                error_message=safe_error_detail(e, "Twilio-WhatsApp")
            )

    async def send_critical_alert(
        self,
        phone_number: str,
        title: str,
        message: str,
        alert_code: Optional[str] = None,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        reference_id: Optional[str] = None,
        use_whatsapp: bool = False,
    ) -> TwilioSendResult:
        """
        Sendet einen kritischen Alert (SMS oder WhatsApp).

        Diese Methode umgeht Ruhezeiten und ist fuer dringende Alerts gedacht.

        Args:
            phone_number: Empfaenger-Telefonnummer (E.164)
            title: Alert-Titel
            message: Alert-Nachricht
            alert_code: Alert-Code (z.B. FRAUD_001)
            company_id: Mandanten-ID
            user_id: Benutzer-ID
            reference_id: Referenz-ID
            use_whatsapp: WhatsApp statt SMS verwenden

        Returns:
            Ergebnis des Sendevorgangs
        """
        # Nachricht formatieren
        body = f"KRITISCHER ALERT - {title}\n\n{message}"
        if alert_code:
            body += f"\n\nCode: {alert_code}"
        body += f"\n\n- Ablage-System"

        twilio_message = TwilioMessage(
            to=phone_number,
            body=body,
            message_type=TwilioMessageType.WHATSAPP if use_whatsapp else TwilioMessageType.SMS,
            notification_type=TwilioNotificationType.CRITICAL_ALERT.value,
            priority=TwilioMessagePriority.CRITICAL,
            company_id=company_id,
            user_id=user_id,
            reference_id=reference_id,
        )

        if use_whatsapp:
            return await self.send_whatsapp(
                twilio_message,
                override_quiet_hours=True,
                override_opt_in=True,
            )
        else:
            return await self.send_sms(
                twilio_message,
                override_quiet_hours=True,
                override_opt_in=True,
            )

    async def send_escalation(
        self,
        phone_number: str,
        escalation_level: int,
        original_channel: str,
        title: str,
        message: str,
        company_id: Optional[UUID] = None,
    ) -> TwilioSendResult:
        """
        Sendet eine Eskalations-SMS.

        Wird aufgerufen wenn vorherige Kanaele (Email, Slack, Teams) nicht reagiert haben.

        Args:
            phone_number: Empfaenger-Telefonnummer
            escalation_level: Eskalationsstufe (1-5)
            original_channel: Urspruenglicher Kanal
            title: Alert-Titel
            message: Alert-Nachricht
            company_id: Mandanten-ID

        Returns:
            Ergebnis des Sendevorgangs
        """
        body = (
            f"ESKALATION Stufe {escalation_level}\n\n"
            f"{title}\n\n"
            f"{message}\n\n"
            f"Urspruenglich via: {original_channel}\n"
            f"Keine Reaktion erhalten.\n\n"
            f"- Ablage-System"
        )

        twilio_message = TwilioMessage(
            to=phone_number,
            body=body,
            message_type=TwilioMessageType.SMS,
            notification_type=TwilioNotificationType.ESCALATION.value,
            priority=TwilioMessagePriority.CRITICAL,
            company_id=company_id,
        )

        return await self.send_sms(
            twilio_message,
            override_quiet_hours=True,
            override_opt_in=True,
        )

    def get_cost_statistics(self) -> dict[str, Any]:
        """
        Gibt aktuelle Kostenstatistiken zurueck.

        Returns:
            Dictionary mit Kostenstatistiken
        """
        return {
            "daily": {
                "sms_count": self._cost_tracking.daily_sms_count,
                "whatsapp_count": self._cost_tracking.daily_whatsapp_count,
                "cost_eur": float(self._cost_tracking.daily_cost_eur),
            },
            "monthly": {
                "sms_count": self._cost_tracking.monthly_sms_count,
                "whatsapp_count": self._cost_tracking.monthly_whatsapp_count,
                "cost_eur": float(self._cost_tracking.monthly_cost_eur),
            },
            "limits": {
                "max_sms_per_day": self._max_sms_per_day,
                "max_monthly_budget_eur": float(self._max_monthly_budget_eur),
                "remaining_daily_sms": max(
                    0,
                    self._max_sms_per_day - self._cost_tracking.daily_sms_count
                ),
                "remaining_monthly_budget_eur": float(
                    self._max_monthly_budget_eur - self._cost_tracking.monthly_cost_eur
                ),
            },
        }

    async def test_connection(self) -> dict[str, Any]:
        """
        Testet die Twilio-Verbindung.

        Returns:
            Status-Dictionary mit Verbindungsinformationen
        """
        result = {
            "enabled": self._enabled,
            "account_sid_configured": bool(self._account_sid),
            "phone_number_configured": bool(self._phone_number),
            "whatsapp_configured": bool(self._whatsapp_number),
            "api_test": None,
        }

        if not self._enabled:
            return result

        try:
            client = await self._get_client()

            # Account-Informationen abrufen
            response = await client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}.json"
            )

            if response.status_code == 200:
                data = response.json()
                result["api_test"] = {
                    "status": "success",
                    "account_name": data.get("friendly_name"),
                    "account_status": data.get("status"),
                }
            else:
                result["api_test"] = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            result["api_test"] = {
                "status": "error",
                **safe_error_log(e),
            }

        return result

    async def close(self) -> None:
        """Schliesst den HTTP-Client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# Singleton-Instanz
# =============================================================================

_twilio_service: Optional[TwilioService] = None


def get_twilio_service() -> TwilioService:
    """Factory-Funktion fuer Twilio-Service Dependency Injection."""
    global _twilio_service
    if _twilio_service is None:
        _twilio_service = TwilioService()
    return _twilio_service


async def send_critical_sms(
    phone_number: str,
    title: str,
    message: str,
    alert_code: Optional[str] = None,
    company_id: Optional[UUID] = None,
) -> TwilioSendResult:
    """
    Convenience-Funktion fuer kritische SMS.

    Kann aus jedem Teil der Anwendung aufgerufen werden.

    Args:
        phone_number: Empfaenger-Telefonnummer (E.164)
        title: Alert-Titel
        message: Alert-Nachricht
        alert_code: Alert-Code
        company_id: Mandanten-ID

    Returns:
        Ergebnis des Sendevorgangs
    """
    service = get_twilio_service()
    return await service.send_critical_alert(
        phone_number=phone_number,
        title=title,
        message=message,
        alert_code=alert_code,
        company_id=company_id,
    )
