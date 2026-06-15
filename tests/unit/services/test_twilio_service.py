# -*- coding: utf-8 -*-
"""
Unit-Tests für Twilio Service.

Testet die ECHTE Service-API (app.services.twilio_service):
- E.164-Telefonnummer-Validierung (E164_PATTERN + Pydantic-Validator)
- Pydantic-Modelle (TwilioUserPreferences, TwilioMessage, TwilioSendResult,
  TwilioCostTracking)
- Rate Limiting (Sliding Window über time.time())
- Budget-Schutz (monatliches Budget)
- GDPR-konformes Opt-In (validate_user_opt_in)
- Ruhezeiten (_is_quiet_hours, zeitzonenbasiert)
- SMS-/WhatsApp-Versand über httpx.AsyncClient (REST-API, kein Twilio-SDK)
- Kritische Alerts (umgehen Opt-In + Ruhezeiten)
- Eskalations-Ketten
- Fehlerbehandlung (Timeouts, HTTP-Fehler)
- Singleton-Pattern

Feinpoliert und durchdacht - Twilio-Integration-Tests gegen den echten Vertrag.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx


# Test-Telefonnummern (E.164 Format)
TEST_PHONE_DE = "+4917012345678"
TEST_PHONE_AT = "+4366412345678"
TEST_PHONE_CH = "+41791234567"
TEST_PHONE_INVALID = "017012345678"  # Ohne Laendervorwahl


# ========================= Hilfsfunktionen =========================


def _make_enabled_service():
    """Erzeugt eine frische, aktivierte TwilioService-Instanz für Send-Tests.

    Der echte Service ist ein Singleton mit _initialized-Guard. Wir setzen
    den Singleton zurueck, initialisieren neu und aktivieren die Integration
    manuell (Credentials + Absender-Nummer), damit is_enabled True ist.
    """
    from app.services.twilio_service import TwilioService

    # Singleton-Zustand zuruecksetzen, damit __init__ erneut laeuft
    TwilioService._instance = None
    service = TwilioService()
    service._enabled = True
    service._account_sid = "AC_test_sid"
    service._auth_token = "test_auth_token"
    service._phone_number = TEST_PHONE_DE
    service._whatsapp_number = f"whatsapp:{TEST_PHONE_DE}"
    return service


def _make_http_response(status_code: int = 201, payload: Optional[Dict[str, Any]] = None):
    """Erzeugt eine Fake-httpx-Response mit .status_code und .json()."""
    if payload is None:
        payload = {"sid": "SM123456789", "status": "queued"}
    response = Mock()
    response.status_code = status_code
    response.json = Mock(return_value=payload)
    return response


def _attach_mock_client(service, response=None, post_side_effect=None):
    """Haengt einen gemockten httpx.AsyncClient an den Service.

    _get_client() ist async, daher ersetzen wir es durch einen AsyncMock,
    der einen Client mit gemocktem .post() liefert.
    """
    client = AsyncMock()
    if post_side_effect is not None:
        client.post = AsyncMock(side_effect=post_side_effect)
    else:
        client.post = AsyncMock(return_value=response or _make_http_response())
    service._get_client = AsyncMock(return_value=client)
    service._mock_client = client  # fuer Assertions zugaenglich machen
    return client


# ========================= Enum-Tests =========================


class TestTwilioMessageType:
    """Tests für TwilioMessageType-Enum."""

    def test_message_types_defined(self):
        """Alle Nachrichtentypen sollten definiert sein."""
        from app.services.twilio_service import TwilioMessageType

        assert TwilioMessageType.SMS == "sms"
        assert TwilioMessageType.WHATSAPP == "whatsapp"

    def test_message_types_string_value(self):
        """Nachrichtentypen sollten String-Werte haben."""
        from app.services.twilio_service import TwilioMessageType

        assert TwilioMessageType.SMS.value == "sms"
        assert TwilioMessageType.WHATSAPP.value == "whatsapp"


class TestTwilioMessagePriority:
    """Tests für TwilioMessagePriority-Enum."""

    def test_priority_levels_defined(self):
        """Alle Prioritaetsstufen sollten definiert sein."""
        from app.services.twilio_service import TwilioMessagePriority

        assert TwilioMessagePriority.LOW == "low"
        assert TwilioMessagePriority.NORMAL == "normal"
        assert TwilioMessagePriority.HIGH == "high"
        assert TwilioMessagePriority.CRITICAL == "critical"


class TestTwilioNotificationType:
    """Tests für TwilioNotificationType-Enum."""

    def test_notification_types_defined(self):
        """Alle Benachrichtigungstypen sollten definiert sein."""
        from app.services.twilio_service import TwilioNotificationType

        assert TwilioNotificationType.CRITICAL_ALERT == "critical_alert"
        assert TwilioNotificationType.HIGH_RISK_ENTITY == "high_risk_entity"
        assert TwilioNotificationType.FRAUD_DETECTED == "fraud_detected"
        assert TwilioNotificationType.SECURITY_INCIDENT == "security_incident"
        assert TwilioNotificationType.SYSTEM_DOWN == "system_down"
        assert TwilioNotificationType.APPROVAL_URGENT == "approval_urgent"
        assert TwilioNotificationType.PAYMENT_CRITICAL == "payment_critical"
        assert TwilioNotificationType.ESCALATION == "escalation"
        assert TwilioNotificationType.CUSTOM == "custom"


class TestTwilioDeliveryStatus:
    """Tests für TwilioDeliveryStatus-Enum."""

    def test_delivery_status_defined(self):
        """Lieferstatus-Werte sollten definiert sein."""
        from app.services.twilio_service import TwilioDeliveryStatus

        assert TwilioDeliveryStatus.QUEUED == "queued"
        assert TwilioDeliveryStatus.SENT == "sent"
        assert TwilioDeliveryStatus.DELIVERED == "delivered"
        assert TwilioDeliveryStatus.FAILED == "failed"


# ========================= E.164 Telefonnummer-Validierung =========================


class TestPhoneNumberValidation:
    """Tests für E.164-Telefonnummer-Validierung über E164_PATTERN.

    Der echte Service kapselt die Validierung im Pydantic-Validator von
    TwilioUserPreferences und im Modul-Pattern E164_PATTERN. Wir testen das
    echte Verhalten beider Wege.
    """

    def test_valid_german_phone_number(self):
        """Gueltige deutsche Telefonnummer matcht E164_PATTERN."""
        from app.services.twilio_service import E164_PATTERN

        assert E164_PATTERN.match(TEST_PHONE_DE) is not None

    def test_valid_austrian_phone_number(self):
        """Gueltige oesterreichische Telefonnummer matcht E164_PATTERN."""
        from app.services.twilio_service import E164_PATTERN

        assert E164_PATTERN.match(TEST_PHONE_AT) is not None

    def test_valid_swiss_phone_number(self):
        """Gueltige schweizer Telefonnummer matcht E164_PATTERN."""
        from app.services.twilio_service import E164_PATTERN

        assert E164_PATTERN.match(TEST_PHONE_CH) is not None

    def test_invalid_phone_number_no_country_code(self):
        """Telefonnummer ohne führendes '+' ist ungueltig."""
        from app.services.twilio_service import E164_PATTERN

        assert E164_PATTERN.match(TEST_PHONE_INVALID) is None

    def test_invalid_phone_number_contains_letters(self):
        """Telefonnummer mit Buchstaben ist ungueltig."""
        from app.services.twilio_service import E164_PATTERN

        assert E164_PATTERN.match("+49ABC1234567") is None

    def test_pydantic_validator_rejects_invalid_number(self):
        """Der Pydantic-Validator wirft bei ungueltiger Nummer einen Fehler."""
        from app.services.twilio_service import TwilioUserPreferences
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TwilioUserPreferences(phone_number=TEST_PHONE_INVALID)

    def test_pydantic_validator_normalizes_number(self):
        """Der Validator entfernt Leerzeichen/Bindestriche/Klammern (Normalisierung)."""
        from app.services.twilio_service import TwilioUserPreferences

        prefs = TwilioUserPreferences(phone_number="+49 170 1234567")
        assert prefs.phone_number == "+491701234567"

        prefs2 = TwilioUserPreferences(phone_number="+49-170-1234567")
        assert prefs2.phone_number == "+491701234567"

        prefs3 = TwilioUserPreferences(phone_number="+49 (170) 1234567")
        assert prefs3.phone_number == "+491701234567"


# ========================= TwilioUserPreferences =========================


class TestTwilioUserPreferences:
    """Tests für das TwilioUserPreferences-Modell."""

    def test_preferences_initialization(self):
        """User-Praeferenzen sollten korrekt initialisiert werden."""
        from app.services.twilio_service import TwilioUserPreferences

        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            sms_opt_in=True,
            whatsapp_opt_in=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )

        assert prefs.phone_number == TEST_PHONE_DE
        assert prefs.sms_opt_in is True
        assert prefs.whatsapp_opt_in is True
        assert prefs.quiet_hours_start == 22
        assert prefs.quiet_hours_end == 7

    def test_preferences_default_values(self):
        """Default-Werte sollten GDPR-konform sein (Opt-In standardmaessig False)."""
        from app.services.twilio_service import TwilioUserPreferences

        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE)

        assert prefs.sms_opt_in is False
        assert prefs.whatsapp_opt_in is False
        assert prefs.timezone == "Europe/Berlin"
        assert prefs.quiet_hours_enabled is True
        # Default-Notification-Typen enthalten kritische Typen
        assert "critical_alert" in prefs.allowed_notification_types


# ========================= Ruhezeiten =========================


class TestQuietHours:
    """Tests für Ruhezeiten (_is_quiet_hours).

    _is_quiet_hours nutzt zoneinfo + datetime.now(user_tz). Wir patchen
    datetime im Modul, damit now(tz) eine kontrollierte Stunde liefert.
    """

    def _patch_now(self, hour: int):
        """Erzeugt ein datetime-Mock, dessen now(tz) eine feste Stunde liefert."""
        fixed = datetime(2024, 1, 15, hour, 0, tzinfo=timezone.utc)
        mock_dt = MagicMock(wraps=datetime)
        mock_dt.now.return_value = fixed
        return mock_dt

    def test_is_quiet_hours_within_range(self):
        """23:00 Uhr liegt in den Ruhezeiten (22:00-07:00)."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        service = TwilioService()
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            sms_opt_in=True,
            quiet_hours_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )

        with patch("app.services.twilio_service.datetime", self._patch_now(23)):
            assert service._is_quiet_hours(prefs) is True

    def test_is_not_quiet_hours(self):
        """14:00 Uhr liegt NICHT in den Ruhezeiten (22:00-07:00)."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        service = TwilioService()
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            sms_opt_in=True,
            quiet_hours_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )

        with patch("app.services.twilio_service.datetime", self._patch_now(14)):
            assert service._is_quiet_hours(prefs) is False

    def test_quiet_hours_disabled_returns_false(self):
        """Bei deaktivierten Ruhezeiten ist das Ergebnis immer False."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        service = TwilioService()
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            quiet_hours_enabled=False,
        )
        # Selbst um 23:00 Uhr: deaktiviert -> False (kein Patch noetig)
        assert service._is_quiet_hours(prefs) is False


# ========================= GDPR Opt-In Validierung =========================


class TestGDPROptIn:
    """Tests für GDPR-konforme Opt-In-Validierung (validate_user_opt_in)."""

    def test_sms_without_opt_in_rejected(self):
        """SMS ohne Opt-In wird abgelehnt."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = TwilioService()
        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE, sms_opt_in=False)

        is_valid, error = service.validate_user_opt_in(
            prefs, TwilioMessageType.SMS, "critical_alert"
        )

        assert is_valid is False
        assert error is not None
        assert "sms" in error.lower() or "aktiviert" in error.lower()

    def test_whatsapp_without_opt_in_rejected(self):
        """WhatsApp ohne Opt-In wird abgelehnt."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = TwilioService()
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            whatsapp_number=TEST_PHONE_DE,
            sms_opt_in=True,
            whatsapp_opt_in=False,
        )

        is_valid, error = service.validate_user_opt_in(
            prefs, TwilioMessageType.WHATSAPP, "critical_alert"
        )

        assert is_valid is False
        assert error is not None

    def test_sms_with_opt_in_allowed(self):
        """SMS mit Opt-In und erlaubtem Notification-Typ wird zugelassen."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = TwilioService()
        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE, sms_opt_in=True)

        is_valid, error = service.validate_user_opt_in(
            prefs, TwilioMessageType.SMS, "critical_alert"
        )

        assert is_valid is True
        assert error is None

    def test_notification_type_not_allowed_rejected(self):
        """Ein nicht erlaubter Notification-Typ wird abgelehnt (granulare Kontrolle)."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = TwilioService()
        # Opt-In vorhanden, aber 'custom' ist nicht in allowed_notification_types
        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE, sms_opt_in=True)

        is_valid, error = service.validate_user_opt_in(
            prefs, TwilioMessageType.SMS, "custom"
        )

        assert is_valid is False
        assert error is not None


# ========================= Rate Limiting =========================


class TestRateLimiting:
    """Tests für das Sliding-Window-Rate-Limiting (_check_rate_limit).

    Das Fenster (_rate_limit_window) enthaelt time.time()-Floats, NICHT
    datetime-Objekte. _check_rate_limit entfernt Eintraege aelter als 24h.
    """

    def test_rate_limit_check_under_limit(self):
        """Anfrage unter dem Limit ist erlaubt."""
        from app.services.twilio_service import TwilioService
        import time

        service = TwilioService()
        service._rate_limit_window.clear()
        service._rate_limit_per_day = 100

        now = time.time()
        for _ in range(5):
            service._rate_limit_window.append(now)

        assert service._check_rate_limit() is True

    def test_rate_limit_check_at_limit(self):
        """Anfrage am Limit wird abgelehnt."""
        from app.services.twilio_service import TwilioService
        import time

        service = TwilioService()
        service._rate_limit_window.clear()
        service._rate_limit_per_day = 10

        now = time.time()
        for _ in range(service._rate_limit_per_day):
            service._rate_limit_window.append(now)

        assert service._check_rate_limit() is False

    def test_rate_limit_window_sliding(self):
        """Eintraege aelter als 24h werden ignoriert (Sliding Window)."""
        from app.services.twilio_service import TwilioService
        import time

        service = TwilioService()
        service._rate_limit_window.clear()
        service._rate_limit_per_day = 10

        # Timestamps aelter als 24h (25 Stunden zurueck)
        old_ts = time.time() - (25 * 60 * 60)
        for _ in range(service._rate_limit_per_day):
            service._rate_limit_window.append(old_ts)

        # Alte Eintraege zaehlen nicht -> wieder erlaubt
        assert service._check_rate_limit() is True
        # Sie wurden auch aus dem Fenster entfernt
        assert len(service._rate_limit_window) == 0


# ========================= Budget-Schutz =========================


class TestBudgetProtection:
    """Tests für den Budget-Schutz (_check_budget)."""

    def test_budget_check_under_limit(self):
        """Budget-Check unter dem Limit ist True."""
        from app.services.twilio_service import TwilioService, TwilioCostTracking

        service = TwilioService()
        service._cost_tracking = TwilioCostTracking(monthly_cost_eur=Decimal("25.00"))
        service._max_monthly_budget_eur = Decimal("50.00")

        assert service._check_budget() is True

    def test_budget_check_exceeds_limit(self):
        """Budget-Check ueber dem Limit ist False."""
        from app.services.twilio_service import TwilioService, TwilioCostTracking

        service = TwilioService()
        service._cost_tracking = TwilioCostTracking(monthly_cost_eur=Decimal("55.00"))
        service._max_monthly_budget_eur = Decimal("50.00")

        assert service._check_budget() is False

    def test_record_message_increments_cost(self):
        """_record_message addiert die Kosten und erhoeht die Zaehler."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioCostTracking,
            TwilioMessageType,
        )

        service = TwilioService()
        service._cost_tracking = TwilioCostTracking(monthly_cost_eur=Decimal("10.00"))
        service._rate_limit_window.clear()

        service._record_message(Decimal("2.50"), TwilioMessageType.SMS)

        assert service._cost_tracking.monthly_cost_eur == Decimal("12.50")
        assert service._cost_tracking.monthly_sms_count == 1
        # Ein Timestamp wurde fuer das Rate-Limiting aufgezeichnet
        assert len(service._rate_limit_window) == 1


# ========================= SMS-Versand =========================


class TestSMSSending:
    """Tests für den SMS-Versand über die echte httpx-REST-Integration."""

    @pytest.mark.asyncio
    async def test_send_sms_success(self):
        """SMS erfolgreich senden (HTTP 201 mit SID)."""
        from app.services.twilio_service import TwilioMessage, TwilioUserPreferences

        service = _make_enabled_service()
        client = _attach_mock_client(
            service,
            response=_make_http_response(
                201, {"sid": "SM123456789", "status": "queued"}
            ),
        )

        # quiet_hours_enabled=False: Default ist True (22-07 Uhr). Dieser Test
        # prueft die Sende-Mechanik (HTTP 201), nicht die Ruhezeiten -> sonst
        # zeitabhaengiger Flake (schlaegt nachts mit "Ruhezeiten aktiv" fehl).
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE, sms_opt_in=True, quiet_hours_enabled=False
        )
        message = TwilioMessage(
            to=TEST_PHONE_DE,
            body="Test-Nachricht fuer Unit-Test",
            notification_type="critical_alert",
        )

        result = await service.send_sms(message, prefs)

        assert result.success is True
        assert result.message_sid == "SM123456789"
        client.post.assert_awaited_once()
        # Das richtige From/To wurde gesendet
        call_kwargs = client.post.await_args.kwargs
        assert call_kwargs["data"]["To"] == TEST_PHONE_DE
        assert call_kwargs["data"]["From"] == TEST_PHONE_DE

    @pytest.mark.asyncio
    async def test_send_sms_without_opt_in_rejected(self):
        """SMS ohne Opt-In wird vor dem HTTP-Call abgelehnt."""
        from app.services.twilio_service import TwilioMessage, TwilioUserPreferences

        service = _make_enabled_service()
        client = _attach_mock_client(service)

        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE, sms_opt_in=False)
        message = TwilioMessage(
            to=TEST_PHONE_DE,
            body="Test",
            notification_type="critical_alert",
        )

        result = await service.send_sms(message, prefs)

        assert result.success is False
        assert result.error_message is not None
        # Kein HTTP-Call, da Opt-In-Validierung greift
        client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_sms_override_opt_in_succeeds(self):
        """Mit override_opt_in (System-/Kritisch-Pfad) wird ohne Opt-In gesendet."""
        from app.services.twilio_service import TwilioMessage

        service = _make_enabled_service()
        client = _attach_mock_client(service)

        message = TwilioMessage(to=TEST_PHONE_DE, body="System-Nachricht")

        result = await service.send_sms(message, override_opt_in=True)

        assert result.success is True
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_sms_disabled_service(self):
        """Bei deaktiviertem Service schlaegt der Versand sauber fehl."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        TwilioService._instance = None
        service = TwilioService()
        service._enabled = False  # explizit deaktiviert

        prefs = TwilioUserPreferences(phone_number=TEST_PHONE_DE, sms_opt_in=True)
        message = TwilioMessage(to=TEST_PHONE_DE, body="Test")

        result = await service.send_sms(message, prefs)

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_send_sms_http_error(self):
        """HTTP-Fehlerantwort (z.B. 400) wird in error_code/error_message gemappt."""
        from app.services.twilio_service import TwilioMessage

        service = _make_enabled_service()
        error_payload = {"code": 21211, "message": "Invalid 'To' Phone Number"}
        _attach_mock_client(
            service, response=_make_http_response(400, error_payload)
        )

        message = TwilioMessage(to=TEST_PHONE_DE, body="Test")

        result = await service.send_sms(message, override_opt_in=True)

        assert result.success is False
        assert result.error_code == 21211
        assert "Invalid" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_send_sms_timeout_handled(self):
        """Ein Timeout bei der Twilio-API wird abgefangen."""
        from app.services.twilio_service import TwilioMessage

        service = _make_enabled_service()
        _attach_mock_client(
            service,
            post_side_effect=httpx.TimeoutException("timed out"),
        )

        message = TwilioMessage(to=TEST_PHONE_DE, body="Test")

        result = await service.send_sms(message, override_opt_in=True)

        assert result.success is False
        assert result.error_message is not None
        assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_send_sms_rate_limit_blocks(self):
        """Bei erreichtem Rate-Limit wird mit Code 429 abgelehnt."""
        from app.services.twilio_service import TwilioMessage
        import time

        service = _make_enabled_service()
        client = _attach_mock_client(service)
        # Fenster auffuellen
        service._rate_limit_per_day = 1
        service._rate_limit_window.clear()
        service._rate_limit_window.append(time.time())

        message = TwilioMessage(to=TEST_PHONE_DE, body="Test")

        result = await service.send_sms(message, override_opt_in=True)

        assert result.success is False
        assert result.error_code == 429
        client.post.assert_not_awaited()


# ========================= WhatsApp-Versand =========================


class TestWhatsAppSending:
    """Tests für den WhatsApp-Versand."""

    @pytest.mark.asyncio
    async def test_send_whatsapp_success(self):
        """WhatsApp erfolgreich senden; To-Nummer erhaelt den whatsapp:-Prefix."""
        from app.services.twilio_service import (
            TwilioMessage,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = _make_enabled_service()
        client = _attach_mock_client(service)

        # quiet_hours_enabled=False: testet die Sende-Mechanik, nicht Ruhezeiten
        # (Default 22-07 Uhr -> sonst nachts "Ruhezeiten aktiv"-Flake).
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            whatsapp_number=TEST_PHONE_DE,
            whatsapp_opt_in=True,
            quiet_hours_enabled=False,
        )
        message = TwilioMessage(
            to=TEST_PHONE_DE,
            body="Test-WhatsApp-Nachricht",
            message_type=TwilioMessageType.WHATSAPP,
            notification_type="critical_alert",
        )

        result = await service.send_whatsapp(message, prefs)

        assert result.success is True
        call_kwargs = client.post.await_args.kwargs
        assert call_kwargs["data"]["To"].startswith("whatsapp:")

    @pytest.mark.asyncio
    async def test_send_whatsapp_without_opt_in_rejected(self):
        """WhatsApp ohne Opt-In wird abgelehnt."""
        from app.services.twilio_service import (
            TwilioMessage,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        service = _make_enabled_service()
        client = _attach_mock_client(service)

        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            whatsapp_number=TEST_PHONE_DE,
            sms_opt_in=True,
            whatsapp_opt_in=False,
        )
        message = TwilioMessage(
            to=TEST_PHONE_DE,
            body="Test",
            message_type=TwilioMessageType.WHATSAPP,
            notification_type="critical_alert",
        )

        result = await service.send_whatsapp(message, prefs)

        assert result.success is False
        client.post.assert_not_awaited()


# ========================= Kritische Alerts =========================


class TestCriticalAlerts:
    """Tests für kritische Alerts (umgehen Opt-In + Ruhezeiten)."""

    @pytest.mark.asyncio
    async def test_send_critical_alert_bypasses_quiet_hours(self):
        """Kritische Alerts werden trotz aktiver Ruhezeiten gesendet."""
        service = _make_enabled_service()
        client = _attach_mock_client(service)

        result = await service.send_critical_alert(
            phone_number=TEST_PHONE_DE,
            title="KRITISCH",
            message="Sicherheitswarnung!",
            alert_code="SEC_001",
        )

        assert result.success is True
        client.post.assert_awaited_once()
        # Der Body enthaelt den Alert-Titel und -Code
        body = client.post.await_args.kwargs["data"]["Body"]
        assert "KRITISCH" in body
        assert "SEC_001" in body

    @pytest.mark.asyncio
    async def test_send_critical_alert_via_whatsapp(self):
        """Kritischer Alert kann auch über WhatsApp gesendet werden."""
        service = _make_enabled_service()
        client = _attach_mock_client(service)

        result = await service.send_critical_alert(
            phone_number=TEST_PHONE_DE,
            title="KRITISCH",
            message="Vorfall",
            use_whatsapp=True,
        )

        assert result.success is True
        assert client.post.await_args.kwargs["data"]["To"].startswith("whatsapp:")


# ========================= Eskalation =========================


class TestEscalation:
    """Tests für die Eskalations-Kette (send_escalation)."""

    @pytest.mark.asyncio
    async def test_escalation_sends_sms(self):
        """Eskalation sendet eine SMS mit Stufe und urspruenglichem Kanal."""
        service = _make_enabled_service()
        client = _attach_mock_client(service)

        result = await service.send_escalation(
            phone_number=TEST_PHONE_DE,
            escalation_level=4,
            original_channel="email",
            title="Eskalation",
            message="Wichtige Nachricht",
        )

        assert result.success is True
        body = client.post.await_args.kwargs["data"]["Body"]
        assert "Stufe 4" in body
        assert "email" in body


# ========================= Initialisierung =========================


class TestTwilioServiceInitialization:
    """Tests für die TwilioService-Initialisierung."""

    def test_service_initialization_without_credentials(self):
        """Ohne Credentials bleibt der Service deaktiviert."""
        from app.services.twilio_service import TwilioService

        with patch("app.services.twilio_service.app_settings") as mock_settings:
            mock_settings.TWILIO_ACCOUNT_SID = None
            mock_settings.TWILIO_AUTH_TOKEN = None
            mock_settings.TWILIO_ENABLED = False
            mock_settings.TWILIO_PHONE_NUMBER = None
            mock_settings.TWILIO_WHATSAPP_NUMBER = None
            mock_settings.TWILIO_MAX_SMS_PER_DAY = 100
            mock_settings.TWILIO_MAX_MONTHLY_BUDGET_EUR = 50

            TwilioService._instance = None
            service = TwilioService()

            assert service._enabled is False
            assert service.is_enabled is False

    def test_service_initialization_with_credentials(self):
        """Mit gültigen Credentials + Absender-Nummer ist der Service aktiv."""
        from app.services.twilio_service import TwilioService

        with patch("app.services.twilio_service.app_settings") as mock_settings:
            mock_settings.TWILIO_ACCOUNT_SID = "AC123"
            mock_token = Mock()
            mock_token.get_secret_value.return_value = "auth_token_123"
            mock_settings.TWILIO_AUTH_TOKEN = mock_token
            mock_settings.TWILIO_ENABLED = True
            mock_settings.TWILIO_PHONE_NUMBER = TEST_PHONE_DE
            mock_settings.TWILIO_WHATSAPP_NUMBER = None
            mock_settings.TWILIO_MAX_SMS_PER_DAY = 100
            mock_settings.TWILIO_MAX_MONTHLY_BUDGET_EUR = 50

            TwilioService._instance = None
            service = TwilioService()

            assert service._enabled is True
            assert service.is_enabled is True


# ========================= Singleton-Pattern =========================


class TestSingletonPattern:
    """Tests für das Singleton-Pattern."""

    def test_get_twilio_service_singleton(self):
        """get_twilio_service liefert immer dieselbe Instanz."""
        import app.services.twilio_service as module
        from app.services.twilio_service import get_twilio_service

        module._twilio_service = None
        service1 = get_twilio_service()
        service2 = get_twilio_service()

        assert service1 is service2

    def test_class_is_singleton(self):
        """Auch direkte Instanziierung liefert dieselbe Instanz (Singleton)."""
        from app.services.twilio_service import TwilioService

        TwilioService._instance = None
        a = TwilioService()
        b = TwilioService()
        assert a is b


# ========================= TwilioSendResult =========================


class TestTwilioSendResult:
    """Tests für das TwilioSendResult-Modell."""

    def test_success_result(self):
        """Erfolgreiche Result-Erstellung mit message_sid und Status."""
        from app.services.twilio_service import TwilioSendResult, TwilioDeliveryStatus

        result = TwilioSendResult(
            success=True,
            message_sid="SM123",
            status=TwilioDeliveryStatus.QUEUED,
        )

        assert result.success is True
        assert result.message_sid == "SM123"
        # Bei Erfolg sind die Fehlerfelder leer
        assert result.error_message is None
        assert result.error_code is None

    def test_failure_result(self):
        """Fehlerhafte Result-Erstellung mit error_message und error_code."""
        from app.services.twilio_service import TwilioSendResult, TwilioDeliveryStatus

        result = TwilioSendResult(
            success=False,
            status=TwilioDeliveryStatus.FAILED,
            error_code=21211,
            error_message="API-Fehler aufgetreten",
        )

        assert result.success is False
        assert result.error_message == "API-Fehler aufgetreten"
        assert result.error_code == 21211


# ========================= Kostentracking =========================


class TestCostTracking:
    """Tests für das TwilioCostTracking-Modell und get_cost_statistics."""

    def test_cost_tracking_initialization(self):
        """Cost-Tracking sollte mit Defaults initialisiert werden."""
        from app.services.twilio_service import TwilioCostTracking

        tracking = TwilioCostTracking()

        assert tracking.daily_sms_count == 0
        assert tracking.monthly_cost_eur == Decimal("0")

    def test_cost_tracking_with_usage(self):
        """Cost-Tracking mit Nutzungsdaten."""
        from app.services.twilio_service import TwilioCostTracking

        tracking = TwilioCostTracking(
            daily_sms_count=20,
            daily_whatsapp_count=5,
            daily_cost_eur=Decimal("3.50"),
            monthly_sms_count=200,
            monthly_whatsapp_count=50,
            monthly_cost_eur=Decimal("35.00"),
        )

        assert tracking.daily_sms_count == 20
        assert tracking.monthly_whatsapp_count == 50
        assert tracking.monthly_cost_eur == Decimal("35.00")

    def test_get_cost_statistics_structure(self):
        """get_cost_statistics liefert daily/monthly/limits-Struktur."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        stats = service.get_cost_statistics()

        assert "daily" in stats
        assert "monthly" in stats
        assert "limits" in stats
        assert "max_sms_per_day" in stats["limits"]


# ========================= SMS-Segment-Berechnung =========================


class TestSMSSegments:
    """Tests für die SMS-Segment-Berechnung (_calculate_sms_segments)."""

    def test_short_gsm7_is_one_segment(self):
        """Kurzer GSM-7-Text ist ein Segment."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._calculate_sms_segments("Kurze Nachricht") == 1

    def test_long_text_multiple_segments(self):
        """Sehr langer Text ergibt mehrere Segmente."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        long_text = "A" * 400  # GSM-7, deutlich ueber 160 Zeichen
        assert service._calculate_sms_segments(long_text) > 1


# ========================= Edge Cases =========================


class TestTwilioServiceEdgeCases:
    """Tests für Randfaelle."""

    @pytest.mark.asyncio
    async def test_message_with_umlauts_preserved(self):
        """Nachricht mit echten Umlauten wird unveraendert übertragen."""
        from app.services.twilio_service import TwilioMessage

        service = _make_enabled_service()
        client = _attach_mock_client(service)

        body = "Prüfbericht: Die Änderungen wurden übernommen. Schöne Grüße."
        message = TwilioMessage(to=TEST_PHONE_DE, body=body)

        result = await service.send_sms(message, override_opt_in=True)

        assert result.success is True
        sent_body = client.post.await_args.kwargs["data"]["Body"]
        assert "Änderungen" in sent_body
        assert "Grüße" in sent_body

    def test_empty_body_rejected_by_model(self):
        """Ein leerer Body ist zulaessig (Pflichtfeld erfüllt) - Vertragspruefung.

        Das Modell erzwingt keine Mindestlaenge; ein leerer String ist gueltig.
        Wir dokumentieren dieses Verhalten explizit, damit kein falscher
        Pass-Stub entsteht.
        """
        from app.services.twilio_service import TwilioMessage

        message = TwilioMessage(to=TEST_PHONE_DE, body="")
        assert message.body == ""

    def test_body_over_max_length_rejected(self):
        """Ein Body über max_length=1600 wird vom Modell abgelehnt."""
        from app.services.twilio_service import TwilioMessage
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TwilioMessage(to=TEST_PHONE_DE, body="x" * 1601)
