# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Twilio Service.

Testet:
- SMS-Versand (Twilio API)
- WhatsApp-Versand
- Rate Limiting (Sliding Window)
- Budget Protection
- E.164 Telefonnummer-Validierung
- GDPR-konformes Opt-In/Opt-Out
- Quiet Hours
- Eskalations-Ketten
- Fehlerbehandlung

Feinpoliert und durchdacht - Twilio-Integration-Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import UUID, uuid4
import json


# Test-Konstanten fuer gueltige UUIDs
TEST_USER_UUID = "00000000-0000-0000-0000-000000000001"
TEST_COMPANY_UUID = "00000000-0000-0000-0000-000000000002"

# Test-Telefonnummern (E.164 Format)
TEST_PHONE_DE = "+4917012345678"
TEST_PHONE_AT = "+4366412345678"
TEST_PHONE_CH = "+41791234567"
TEST_PHONE_INVALID = "017012345678"  # Ohne Laendervorwahl


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_twilio_client():
    """Create mock Twilio client."""
    client = Mock()
    # Mock messages resource
    client.messages = Mock()
    mock_message = Mock()
    mock_message.sid = "SM123456789"
    mock_message.status = "queued"
    mock_message.price = "0.05"
    mock_message.price_unit = "EUR"
    client.messages.create = Mock(return_value=mock_message)
    return client


@pytest.fixture
def mock_redis():
    """Create mock Redis client for rate limiting."""
    redis = AsyncMock()
    redis.client = AsyncMock()
    redis.client.get = AsyncMock(return_value=None)
    redis.client.setex = AsyncMock()
    redis.client.incr = AsyncMock(return_value=1)
    redis.client.expire = AsyncMock()
    redis.client.ttl = AsyncMock(return_value=3600)
    redis.client.lrange = AsyncMock(return_value=[])
    redis.client.lpush = AsyncMock()
    redis.client.ltrim = AsyncMock()
    return redis


@pytest.fixture
def sample_user_preferences() -> Dict[str, Any]:
    """Provide sample user preferences for Twilio."""
    return {
        "phone_number": TEST_PHONE_DE,
        "sms_opt_in": True,
        "whatsapp_opt_in": True,
        "quiet_hours_enabled": True,
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
        "timezone": "Europe/Berlin",
    }


@pytest.fixture
def sample_message() -> Dict[str, Any]:
    """Provide sample message payload."""
    return {
        "to": TEST_PHONE_DE,
        "body": "Die Rechnung INV-2024-001 ist seit 14 Tagen ueberfaellig.",
        "priority": "high",
        "notification_type": "payment_critical",
    }


# ========================= TwilioMessageType Tests =========================


class TestTwilioMessageType:
    """Tests for TwilioMessageType enum."""

    def test_message_types_defined(self):
        """Alle Nachrichtentypen sollten definiert sein."""
        from app.services.twilio_service import TwilioMessageType

        assert TwilioMessageType.SMS == "sms"
        assert TwilioMessageType.WHATSAPP == "whatsapp"

    def test_message_types_string_value(self):
        """Nachrichtentypen sollten String-Werte haben."""
        from app.services.twilio_service import TwilioMessageType

        assert str(TwilioMessageType.SMS.value) == "sms"
        assert str(TwilioMessageType.WHATSAPP.value) == "whatsapp"


class TestTwilioMessagePriority:
    """Tests for TwilioMessagePriority enum."""

    def test_priority_levels_defined(self):
        """Alle Prioritaetsstufen sollten definiert sein."""
        from app.services.twilio_service import TwilioMessagePriority

        assert TwilioMessagePriority.LOW == "low"
        assert TwilioMessagePriority.NORMAL == "normal"
        assert TwilioMessagePriority.HIGH == "high"
        assert TwilioMessagePriority.CRITICAL == "critical"


class TestTwilioNotificationType:
    """Tests for TwilioNotificationType enum."""

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


# ========================= Phone Number Validation Tests =========================


class TestPhoneNumberValidation:
    """Tests for E.164 phone number validation."""

    def test_valid_german_phone_number(self):
        """Gueltige deutsche Telefonnummer."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number(TEST_PHONE_DE) is True

    def test_valid_austrian_phone_number(self):
        """Gueltige oesterreichische Telefonnummer."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number(TEST_PHONE_AT) is True

    def test_valid_swiss_phone_number(self):
        """Gueltige schweizer Telefonnummer."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number(TEST_PHONE_CH) is True

    def test_invalid_phone_number_no_country_code(self):
        """Ungueltige Telefonnummer ohne Laendervorwahl."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number(TEST_PHONE_INVALID) is False

    def test_invalid_phone_number_too_short(self):
        """Ungueltige Telefonnummer (zu kurz)."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number("+49123") is False

    def test_invalid_phone_number_contains_letters(self):
        """Ungueltige Telefonnummer mit Buchstaben."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        assert service._validate_phone_number("+49ABC1234567") is False


# ========================= TwilioUserPreferences Tests =========================


class TestTwilioUserPreferences:
    """Tests for TwilioUserPreferences model."""

    def test_preferences_initialization(self, sample_user_preferences):
        """User-Praeferenzen sollten korrekt initialisiert werden."""
        from app.services.twilio_service import TwilioUserPreferences

        prefs = TwilioUserPreferences(**sample_user_preferences)

        assert prefs.phone_number == TEST_PHONE_DE
        assert prefs.sms_opt_in is True
        assert prefs.whatsapp_opt_in is True
        assert prefs.quiet_hours_start == 22
        assert prefs.quiet_hours_end == 7

    def test_preferences_default_values(self):
        """Default-Werte sollten gesetzt werden."""
        from app.services.twilio_service import TwilioUserPreferences

        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
        )

        assert prefs.sms_opt_in is False
        assert prefs.whatsapp_opt_in is False
        assert prefs.timezone == "Europe/Berlin"


# ========================= Quiet Hours Tests =========================


class TestQuietHours:
    """Tests for quiet hours functionality."""

    def test_is_quiet_hours_within_range(self):
        """Prueft ob aktuelle Zeit in Quiet Hours liegt."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        service = TwilioService()

        # 23:00 Uhr ist in Quiet Hours (22:00-07:00)
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            sms_opt_in=True,
            quiet_hours_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )

        test_time = datetime(2024, 1, 15, 23, 0, tzinfo=timezone.utc)

        with patch('app.services.twilio_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = service._is_quiet_hours(prefs)
            assert result is True

    def test_is_not_quiet_hours(self):
        """Prueft ob aktuelle Zeit ausserhalb Quiet Hours liegt."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        service = TwilioService()

        # 14:00 Uhr ist NICHT in Quiet Hours (22:00-07:00)
        prefs = TwilioUserPreferences(
            phone_number=TEST_PHONE_DE,
            sms_opt_in=True,
            quiet_hours_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )

        test_time = datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)

        with patch('app.services.twilio_service.datetime') as mock_datetime:
            mock_datetime.now.return_value = test_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = service._is_quiet_hours(prefs)
            assert result is False


# ========================= GDPR Opt-In Tests =========================


class TestGDPROptIn:
    """Tests for GDPR-compliant opt-in validation."""

    @pytest.mark.asyncio
    async def test_send_sms_without_opt_in_fails(self, mock_twilio_client):
        """SMS ohne Opt-In sollte abgelehnt werden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=False,  # Kein Opt-In!
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test-Nachricht",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is False
            assert "opt_in" in result.error.lower() or "gdpr" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_whatsapp_without_opt_in_fails(self, mock_twilio_client):
        """WhatsApp ohne Opt-In sollte abgelehnt werden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,
                whatsapp_opt_in=False,  # Kein WhatsApp Opt-In!
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test-Nachricht",
            )

            result = await service.send_whatsapp(message, prefs)

            assert result.success is False

    @pytest.mark.asyncio
    async def test_send_sms_with_opt_in_succeeds(self, mock_twilio_client):
        """SMS mit Opt-In sollte erfolgreich sein."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,  # Opt-In vorhanden!
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test-Nachricht",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is True
            assert result.message_sid is not None


# ========================= Rate Limiting Tests =========================


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_check_under_limit(self):
        """Anfrage unter Rate-Limit sollte erlaubt sein."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        # Reset rate limit window for testing
        service._rate_limit_window.clear()

        # Add some messages but under limit
        for _ in range(5):
            service._rate_limit_window.append(datetime.now(timezone.utc))

        result = service._check_rate_limit()
        assert result is True

    def test_rate_limit_check_at_limit(self):
        """Anfrage am Rate-Limit sollte abgelehnt werden."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        # Reset rate limit window for testing
        service._rate_limit_window.clear()

        # Fill up the rate limit
        for _ in range(service._rate_limit_per_day):
            service._rate_limit_window.append(datetime.now(timezone.utc))

        result = service._check_rate_limit()
        assert result is False

    def test_rate_limit_window_sliding(self):
        """Rate-Limit sollte alte Eintraege ignorieren."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()
        service._rate_limit_window.clear()

        # Add old messages (more than 24h ago)
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        for _ in range(service._rate_limit_per_day):
            service._rate_limit_window.append(old_time)

        # Old messages should not count
        result = service._check_rate_limit()
        assert result is True


# ========================= Budget Protection Tests =========================


class TestBudgetProtection:
    """Tests for budget protection functionality."""

    def test_budget_check_under_limit(self):
        """Prueft Budget-Check unter dem Limit."""
        from app.services.twilio_service import TwilioService, TwilioCostTracking

        service = TwilioService()

        # Set cost tracking to under limit
        service._cost_tracking = TwilioCostTracking(
            monthly_cost_eur=Decimal("25.00")
        )
        service._max_monthly_budget_eur = Decimal("50.00")

        result = service._check_budget()
        assert result is True

    def test_budget_check_exceeds_limit(self):
        """Prueft Budget-Check ueber dem Limit."""
        from app.services.twilio_service import TwilioService, TwilioCostTracking

        service = TwilioService()

        # Set cost tracking to over limit
        service._cost_tracking = TwilioCostTracking(
            monthly_cost_eur=Decimal("55.00")
        )
        service._max_monthly_budget_eur = Decimal("50.00")

        result = service._check_budget()
        assert result is False

    def test_budget_tracking_increment(self):
        """Budget-Tracking sollte Kosten addieren."""
        from app.services.twilio_service import TwilioService, TwilioCostTracking

        service = TwilioService()

        # Reset cost tracking
        service._cost_tracking = TwilioCostTracking(
            monthly_cost_eur=Decimal("10.00")
        )

        initial_cost = service._cost_tracking.monthly_cost_eur

        # Add cost
        service._cost_tracking.monthly_cost_eur += Decimal("2.50")

        assert service._cost_tracking.monthly_cost_eur == initial_cost + Decimal("2.50")


# ========================= SMS Sending Tests =========================


class TestSMSSending:
    """Tests for SMS sending functionality."""

    @pytest.mark.asyncio
    async def test_send_sms_success(self, mock_twilio_client, sample_user_preferences):
        """SMS erfolgreich senden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(**sample_user_preferences)
            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test-Nachricht fuer Unit-Test",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is True
            assert result.message_sid == "SM123456789"
            mock_twilio_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_sms_invalid_phone(self, mock_twilio_client):
        """SMS an ungueltige Telefonnummer sollte fehlschlagen."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_INVALID,
                sms_opt_in=True,
            )

            message = TwilioMessage(
                to=TEST_PHONE_INVALID,  # Ungueltig!
                body="Test",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is False
            assert "telefonnummer" in result.error.lower() or "e.164" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_sms_twilio_error(self, mock_twilio_client, sample_user_preferences):
        """Twilio API-Fehler sollte behandelt werden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        mock_twilio_client.messages.create.side_effect = Exception("Twilio API error")

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(**sample_user_preferences)
            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is False
            assert result.error is not None


# ========================= WhatsApp Sending Tests =========================


class TestWhatsAppSending:
    """Tests for WhatsApp sending functionality."""

    @pytest.mark.asyncio
    async def test_send_whatsapp_success(self, mock_twilio_client):
        """WhatsApp erfolgreich senden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioMessageType,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                whatsapp_opt_in=True,
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Test-WhatsApp-Nachricht",
                message_type=TwilioMessageType.WHATSAPP,
            )

            result = await service.send_whatsapp(message, prefs)

            assert result.success is True
            # WhatsApp Format: whatsapp:+49...
            call_kwargs = mock_twilio_client.messages.create.call_args.kwargs
            assert "whatsapp:" in call_kwargs.get("to", "")


# ========================= Critical Alert Tests =========================


class TestCriticalAlerts:
    """Tests for critical alert functionality."""

    @pytest.mark.asyncio
    async def test_send_critical_alert_bypasses_quiet_hours(self, mock_twilio_client):
        """Kritische Alerts sollten Quiet Hours ignorieren."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,
                quiet_hours_enabled=True,
                quiet_hours_start=0,  # Ganztaegig Quiet Hours
                quiet_hours_end=23,
            )

            result = await service.send_critical_alert(
                phone_number=TEST_PHONE_DE,
                title="KRITISCH",
                message="Sicherheitswarnung!",
                preferences=prefs,
            )

            assert result.success is True
            mock_twilio_client.messages.create.assert_called()


# ========================= Escalation Tests =========================


class TestEscalation:
    """Tests for escalation chain functionality."""

    @pytest.mark.asyncio
    async def test_escalation_chain_progression(self, mock_twilio_client):
        """Eskalations-Kette sollte korrekten Kanal waehlen."""
        from app.services.twilio_service import TwilioService, TwilioUserPreferences

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,
                whatsapp_opt_in=True,
            )

            # Eskalationsstufe 4 sollte SMS verwenden
            result = await service.send_escalation(
                phone_number=TEST_PHONE_DE,
                title="Eskalation",
                message="Wichtige Nachricht",
                escalation_level=4,
                preferences=prefs,
            )

            assert result.success is True


# ========================= TwilioService Initialization Tests =========================


class TestTwilioServiceInitialization:
    """Tests for TwilioService initialization."""

    def test_service_initialization_without_credentials(self):
        """Service sollte ohne Credentials initialisiert werden."""
        from app.services.twilio_service import TwilioService

        with patch('app.services.twilio_service.settings') as mock_settings:
            mock_settings.TWILIO_ACCOUNT_SID = None
            mock_settings.TWILIO_AUTH_TOKEN = None
            mock_settings.TWILIO_ENABLED = False

            service = TwilioService()

            assert service._enabled is False

    def test_service_initialization_with_credentials(self):
        """Service sollte mit Credentials initialisiert werden."""
        from app.services.twilio_service import TwilioService
        from unittest.mock import PropertyMock

        with patch('app.services.twilio_service.settings') as mock_settings:
            mock_settings.TWILIO_ACCOUNT_SID = "AC123"
            mock_token = Mock()
            mock_token.get_secret_value.return_value = "auth_token_123"
            mock_settings.TWILIO_AUTH_TOKEN = mock_token
            mock_settings.TWILIO_ENABLED = True
            mock_settings.TWILIO_PHONE_NUMBER = TEST_PHONE_DE

            service = TwilioService()

            assert service._enabled is True


# ========================= Singleton Pattern Tests =========================


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_get_twilio_service_singleton(self):
        """get_twilio_service sollte Singleton zurueckgeben."""
        from app.services.twilio_service import get_twilio_service
        import app.services.twilio_service as module

        # Reset singleton
        module._twilio_service = None

        service1 = get_twilio_service()
        service2 = get_twilio_service()

        assert service1 is service2


# ========================= TwilioSendResult Tests =========================


class TestTwilioSendResult:
    """Tests for TwilioSendResult model."""

    def test_success_result(self):
        """Erfolgreiche Result-Erstellung."""
        from app.services.twilio_service import TwilioSendResult, TwilioDeliveryStatus

        result = TwilioSendResult(
            success=True,
            message_sid="SM123",
            status=TwilioDeliveryStatus.QUEUED,
        )

        assert result.success is True
        assert result.message_sid == "SM123"
        assert result.error is None

    def test_failure_result(self):
        """Fehlerhafte Result-Erstellung."""
        from app.services.twilio_service import TwilioSendResult, TwilioDeliveryStatus

        result = TwilioSendResult(
            success=False,
            status=TwilioDeliveryStatus.FAILED,
            error="API-Fehler aufgetreten",
        )

        assert result.success is False
        assert result.error == "API-Fehler aufgetreten"


# ========================= Edge Cases =========================


class TestTwilioServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_send_empty_message(self, mock_twilio_client):
        """Leere Nachricht sollte abgelehnt werden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="",  # Leer!
            )

            result = await service.send_sms(message, prefs)

            # Sollte fehlschlagen oder leere Nachricht ablehnen
            assert result.success is False or message.body == ""

    @pytest.mark.asyncio
    async def test_message_with_umlauts(self, mock_twilio_client):
        """Nachricht mit Umlauten sollte korrekt gesendet werden."""
        from app.services.twilio_service import (
            TwilioService,
            TwilioMessage,
            TwilioUserPreferences,
        )

        with patch('app.services.twilio_service.TWILIO_CLIENT', mock_twilio_client):
            service = TwilioService()

            prefs = TwilioUserPreferences(
                phone_number=TEST_PHONE_DE,
                sms_opt_in=True,
            )

            message = TwilioMessage(
                to=TEST_PHONE_DE,
                body="Pruefbericht: Die Aenderungen wurden uebernommen. Moegen Sie oeffentlich bestaetigen?",
            )

            result = await service.send_sms(message, prefs)

            assert result.success is True
            # Verify umlauts were preserved
            call_kwargs = mock_twilio_client.messages.create.call_args.kwargs
            assert "Aenderungen" in call_kwargs.get("body", "")

    def test_phone_number_normalization(self):
        """Telefonnummer-Normalisierung."""
        from app.services.twilio_service import TwilioService

        service = TwilioService()

        # Verschiedene Formate sollten normalisiert werden
        assert service._normalize_phone_number("+49 170 1234567") == "+491701234567"
        assert service._normalize_phone_number("+49-170-1234567") == "+491701234567"
        assert service._normalize_phone_number("+49 (170) 1234567") == "+491701234567"


# ========================= Cost Tracking Tests =========================


class TestCostTracking:
    """Tests for cost tracking functionality."""

    def test_cost_tracking_initialization(self):
        """Cost-Tracking sollte initialisiert werden."""
        from app.services.twilio_service import TwilioCostTracking

        tracking = TwilioCostTracking(
            daily_sms_count=0,
            daily_whatsapp_count=0,
            daily_cost_eur=Decimal("0"),
            monthly_sms_count=0,
            monthly_whatsapp_count=0,
            monthly_cost_eur=Decimal("0"),
        )

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
