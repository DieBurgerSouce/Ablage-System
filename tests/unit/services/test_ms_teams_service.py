# -*- coding: utf-8 -*-
"""
Unit Tests fuer TeamsService.

Testet:
- Webhook-Benachrichtigungen
- Rate Limiting (Sliding Window)
- PII Masking (IBAN, Email, Kundennr)
- Adaptive Card Formatting
- Message Card Formatting
- Notification Types
- Error Handling und Retries
- Connection Testing

Feinpoliert und durchdacht - Microsoft Teams-Integration Tests.
"""

import pytest
import time
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.services.ms_teams_service import (
    TeamsService,
    TeamsMessage,
    TeamsSection,
    TeamsAction,
    TeamsNotificationType,
    TeamsMessagePriority,
    TeamsServiceError,
    TeamsRateLimitError,
    get_teams_service,
    send_teams_notification,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_settings():
    """Mock app settings for Teams configuration."""
    settings = Mock()
    settings.TEAMS_WEBHOOK_URL = Mock()
    settings.TEAMS_WEBHOOK_URL.get_secret_value.return_value = "https://outlook.office.com/webhook/TEST/IncomingWebhook/GUID"
    settings.TEAMS_DEFAULT_CHANNEL = "Allgemein"
    settings.TEAMS_ENABLED = True
    settings.TEAMS_NOTIFICATION_TYPES = [
        "document_processed",
        "document_error",
        "approval_required",
        "system_alert",
        "high_risk_entity",
        "payment_reminder",
    ]
    settings.TEAMS_RATE_LIMIT_PER_MINUTE = 30
    return settings


@pytest.fixture
def mock_settings_disabled():
    """Mock settings with Teams disabled."""
    settings = Mock()
    settings.TEAMS_WEBHOOK_URL = None
    settings.TEAMS_DEFAULT_CHANNEL = None
    settings.TEAMS_ENABLED = False
    settings.TEAMS_NOTIFICATION_TYPES = []
    settings.TEAMS_RATE_LIMIT_PER_MINUTE = 30
    return settings


@pytest.fixture
async def mock_httpx_client():
    """Mock httpx AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def teams_service(mock_settings):
    """Create TeamsService instance with mocked settings."""
    # Reset singleton
    TeamsService._instance = None

    with patch("app.services.ms_teams_service.app_settings", mock_settings):
        service = TeamsService()
        # Prevent re-initialization
        service._initialized = False
        service.__init__()
        yield service

    # Cleanup
    TeamsService._instance = None


@pytest.fixture
def sample_teams_message() -> TeamsMessage:
    """Provide sample Teams message."""
    return TeamsMessage(
        title="Test-Nachricht",
        summary="Dies ist eine Test-Nachricht",
        sections=[
            TeamsSection(
                title="Details",
                text="Nachricht-Text",
                facts=[{"name": "Feld1", "value": "Wert1"}],
            )
        ],
        theme_color="0076D7",
    )


@pytest.fixture
def sample_notification_context() -> Dict[str, Any]:
    """Provide sample notification context."""
    return {
        "document_id": "doc-123",
        "confidence": 0.95,
        "backend": "deepseek",
        "processing_time": 1.5,
    }


# ========================= Initialization Tests =========================


class TestTeamsServiceInitialization:
    """Tests fuer TeamsService Initialisierung."""

    def test_initialization_with_webhook(self, mock_settings):
        """Service sollte mit Webhook initialisiert werden."""
        # Reset singleton
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service = TeamsService()

            assert service._webhook_url == "https://outlook.office.com/webhook/TEST/IncomingWebhook/GUID"
            assert service._default_channel == "Allgemein"
            assert service._enabled is True
            assert service._rate_limit_per_minute == 30

        TeamsService._instance = None

    def test_initialization_disabled(self, mock_settings_disabled):
        """Service sollte deaktiviert sein wenn keine Credentials."""
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings_disabled):
            service = TeamsService()

            assert service.is_enabled is False

        TeamsService._instance = None

    def test_singleton_pattern(self, mock_settings):
        """Service sollte Singleton-Pattern verwenden."""
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service1 = TeamsService()
            service2 = TeamsService()

            assert service1 is service2

        TeamsService._instance = None

    def test_invalid_webhook_url_detection(self):
        """Service sollte ungueltige Webhook-URLs erkennen."""
        settings = Mock()
        settings.TEAMS_WEBHOOK_URL = Mock()
        settings.TEAMS_WEBHOOK_URL.get_secret_value.return_value = "invalid-url"
        settings.TEAMS_DEFAULT_CHANNEL = None
        settings.TEAMS_ENABLED = True
        settings.TEAMS_NOTIFICATION_TYPES = []
        settings.TEAMS_RATE_LIMIT_PER_MINUTE = 30

        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", settings):
            service = TeamsService()
            # URL wird als ungueltig erkannt und auf None gesetzt
            assert service._webhook_url is None

        TeamsService._instance = None

    def test_non_microsoft_webhook_warning(self):
        """Service sollte bei nicht-microsoft URLs warnen aber akzeptieren."""
        settings = Mock()
        settings.TEAMS_WEBHOOK_URL = Mock()
        settings.TEAMS_WEBHOOK_URL.get_secret_value.return_value = "https://evil.com/webhook"
        settings.TEAMS_DEFAULT_CHANNEL = None
        settings.TEAMS_ENABLED = True
        settings.TEAMS_NOTIFICATION_TYPES = []
        settings.TEAMS_RATE_LIMIT_PER_MINUTE = 30

        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", settings):
            service = TeamsService()
            # URL wird gesetzt aber gewarnt
            assert service._webhook_url == "https://evil.com/webhook"

        TeamsService._instance = None


# ========================= Webhook Sending Tests =========================


class TestWebhookSending:
    """Tests fuer Webhook-Nachrichten."""

    @pytest.mark.asyncio
    async def test_send_webhook_message_success(self, teams_service):
        """Webhook-Nachricht sollte erfolgreich gesendet werden."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "1"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        teams_service._client = mock_client

        payload = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="system_alert",
            context=None,
        )

        result = await teams_service.send_webhook_message(payload)

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == teams_service._webhook_url

    @pytest.mark.asyncio
    async def test_send_webhook_message_no_webhook_configured(self, teams_service):
        """Sollte False zurueckgeben wenn kein Webhook konfiguriert."""
        teams_service._webhook_url = None

        result = await teams_service.send_webhook_message({"test": "payload"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_message_rate_limit_reached(self, teams_service):
        """Sollte TeamsRateLimitError werfen bei Rate Limit."""
        # Rate Limit Window voll machen
        now = time.time()
        for _ in range(teams_service._rate_limit_per_minute):
            teams_service._rate_limit_window.append(now)

        with pytest.raises(TeamsRateLimitError) as exc_info:
            await teams_service.send_webhook_message({"test": "payload"})

        assert "Rate Limit erreicht" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_webhook_message_retry_on_429(self, teams_service):
        """Sollte bei 429 (Rate Limit) retry mit Retry-After."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        mock_response.text = "rate_limited"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        with pytest.raises(TeamsRateLimitError):
            await teams_service.send_webhook_message({"test": "payload"}, retry_count=2)

        # Sollte 2x versucht haben
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_webhook_message_retry_on_timeout(self, teams_service):
        """Sollte bei Timeout retry mit exponential backoff."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        teams_service._client = mock_client

        result = await teams_service.send_webhook_message({"test": "payload"}, retry_count=3)

        assert result is False
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_webhook_message_records_rate_limit(self, teams_service):
        """Sollte gesendete Nachrichten fuer Rate Limiting aufzeichnen."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        initial_count = len(teams_service._rate_limit_window)

        await teams_service.send_webhook_message({"test": "payload"})

        assert len(teams_service._rate_limit_window) == initial_count + 1


# ========================= Rate Limiting Tests =========================


class TestRateLimiting:
    """Tests fuer Rate Limiting (Sliding Window)."""

    def test_check_rate_limit_within_limit(self, teams_service):
        """Sollte True zurueckgeben wenn unter Limit."""
        # Window leer
        assert teams_service._check_rate_limit() is True

    def test_check_rate_limit_at_limit(self, teams_service):
        """Sollte False zurueckgeben wenn Limit erreicht."""
        now = time.time()
        # Window voll machen
        for _ in range(teams_service._rate_limit_per_minute):
            teams_service._rate_limit_window.append(now)

        assert teams_service._check_rate_limit() is False

    def test_check_rate_limit_sliding_window_cleanup(self, teams_service):
        """Sollte alte Timestamps aus Window entfernen."""
        # Alte Timestamps hinzufuegen (aelter als 60s)
        old_time = time.time() - 65
        for _ in range(10):
            teams_service._rate_limit_window.append(old_time)

        # Check sollte alte Eintraege entfernen
        assert teams_service._check_rate_limit() is True
        assert len(teams_service._rate_limit_window) == 0

    def test_record_message_adds_timestamp(self, teams_service):
        """Sollte Timestamp beim Senden aufzeichnen."""
        initial_count = len(teams_service._rate_limit_window)

        teams_service._record_message()

        assert len(teams_service._rate_limit_window) == initial_count + 1

    def test_rate_limit_window_maxlen(self, teams_service):
        """Sollte maxlen fuer deque respektieren."""
        # Window ueber maxlen fuellen
        expected_maxlen = teams_service._rate_limit_per_minute * 2
        for _ in range(expected_maxlen + 10):
            teams_service._rate_limit_window.append(time.time())

        # Sollte auf maxlen begrenzt sein
        assert len(teams_service._rate_limit_window) == expected_maxlen


# ========================= PII Masking Tests =========================


class TestPIIMasking:
    """Tests fuer PII-Maskierung in Context-Feldern."""

    def test_context_filters_iban(self, teams_service):
        """Sollte IBAN aus Context-Feldern filtern."""
        context = {
            "iban": "DE89370400440532013000",
            "amount": 1234.56,
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
        )

        # IBAN sollte nicht in Card erscheinen
        card_str = str(card)
        assert "DE89370400440532013000" not in card_str
        assert "iban" not in card_str.lower()

    def test_context_filters_vat_id(self, teams_service):
        """Sollte VAT-ID aus Context filtern."""
        context = {
            "vat_id": "DE123456789",
            "company": "Test GmbH",
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="high_risk_entity",
            context=context,
        )

        card_str = str(card)
        assert "DE123456789" not in card_str
        assert "vat_id" not in card_str.lower()

    def test_context_filters_customer_number(self, teams_service):
        """Sollte Kundennummer aus Context filtern."""
        context = {
            "customer_number": "KD-12345",
            "kundennr": "67890",
            "amount": 999.99,
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="approval_required",
            context=context,
        )

        card_str = str(card)
        assert "KD-12345" not in card_str
        assert "67890" not in card_str
        assert "customer_number" not in card_str.lower()
        assert "kundennr" not in card_str.lower()

    def test_context_allows_safe_fields(self, teams_service):
        """Sollte sichere Felder in Context anzeigen."""
        context = {
            "document_id": "doc-123",
            "confidence": 0.95,
            "backend": "deepseek",
            "processing_time": 1.5,
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
        )

        # Sichere Felder sollten erscheinen
        card_str = str(card)
        assert "doc-123" in card_str
        assert "0.95" in card_str
        assert "deepseek" in card_str


# ========================= Adaptive Card Formatting Tests =========================


class TestAdaptiveCardFormatting:
    """Tests fuer Adaptive Card Nachrichtenformatierung."""

    def test_build_adaptive_card_structure(self, teams_service):
        """Sollte korrekte Adaptive Card Struktur erstellen."""
        card = teams_service._build_adaptive_card(
            title="Dokument verarbeitet",
            message="Rechnung #12345",
            notification_type="document_processed",
            context=None,
        )

        assert card["type"] == "message"
        assert "attachments" in card
        assert len(card["attachments"]) == 1
        assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"

    def test_build_adaptive_card_body_elements(self, teams_service):
        """Sollte Body-Elemente korrekt erstellen."""
        card = teams_service._build_adaptive_card(
            title="Test",
            message="Dies ist die Hauptnachricht",
            notification_type="system_alert",
            context=None,
        )

        body = card["attachments"][0]["content"]["body"]
        assert len(body) >= 2  # Mindestens Titel und Nachricht

        # Titel-Block
        title_block = body[0]
        assert title_block["type"] == "TextBlock"
        assert title_block["size"] == "Large"
        assert title_block["weight"] == "Bolder"
        assert "Test" in title_block["text"]

        # Nachricht-Block
        message_block = body[1]
        assert message_block["type"] == "TextBlock"
        assert message_block["text"] == "Dies ist die Hauptnachricht"

    def test_build_adaptive_card_with_context_factset(self, teams_service):
        """Sollte Context-Felder als FactSet erstellen."""
        context = {
            "confidence": 0.95,
            "processing_time": 1.5,
            "word_count": 250,
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
        )

        body = card["attachments"][0]["content"]["body"]

        # FactSet suchen
        factset = next(
            (b for b in body if b["type"] == "FactSet"),
            None
        )
        assert factset is not None
        assert len(factset["facts"]) == 3

    def test_build_adaptive_card_with_actions(self, teams_service):
        """Sollte Aktions-Buttons korrekt hinzufuegen."""
        actions = [
            TeamsAction(type="Action.OpenUrl", title="Dokument oeffnen", url="https://example.com/doc/123"),
            TeamsAction(type="Action.OpenUrl", title="Ablehnen", url="https://example.com/reject"),
        ]

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test",
            notification_type="approval_required",
            context=None,
            actions=actions,
        )

        content = card["attachments"][0]["content"]
        assert "actions" in content
        assert len(content["actions"]) == 2
        assert content["actions"][0]["type"] == "Action.OpenUrl"
        assert content["actions"][0]["title"] == "Dokument oeffnen"

    def test_build_adaptive_card_value_formatting(self, teams_service):
        """Sollte Werte korrekt formatieren (bool, float, datetime)."""
        context = {
            "is_valid": True,
            "confidence": 0.953678,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
        }

        card = teams_service._build_adaptive_card(
            title="Test",
            message="Test",
            notification_type="document_processed",
            context=context,
        )

        card_str = str(card)
        # Bool als Ja/Nein
        assert "Ja" in card_str
        # Float mit 2 Dezimalstellen
        assert "0.95" in card_str
        # Datetime formatiert
        assert "15.01.2024" in card_str


# ========================= Message Card Formatting Tests =========================


class TestMessageCardFormatting:
    """Tests fuer Legacy Message Card Formatierung."""

    def test_build_message_card_structure(self, teams_service):
        """Sollte korrekte Message Card Struktur erstellen."""
        card = teams_service._build_message_card(
            title="Test",
            message="Test-Nachricht",
            notification_type="system_alert",
            context=None,
            theme_color="FF0000",
        )

        assert card["@type"] == "MessageCard"
        assert card["@context"] == "http://schema.org/extensions"
        assert card["themeColor"] == "FF0000"
        assert "summary" in card
        assert "sections" in card

    def test_build_message_card_with_facts(self, teams_service):
        """Sollte Context-Felder als Facts erstellen."""
        context = {
            "confidence": 0.95,
            "backend": "deepseek",
        }

        card = teams_service._build_message_card(
            title="Test",
            message="Test",
            notification_type="document_processed",
            context=context,
        )

        sections = card["sections"]
        assert len(sections) > 0
        assert "facts" in sections[0]
        assert len(sections[0]["facts"]) == 2

    def test_build_message_card_with_actions(self, teams_service):
        """Sollte Potential Actions korrekt hinzufuegen."""
        actions = [
            TeamsAction(type="Action.OpenUrl", title="Oeffnen", url="https://example.com"),
        ]

        card = teams_service._build_message_card(
            title="Test",
            message="Test",
            notification_type="system_alert",
            context=None,
            actions=actions,
        )

        assert "potentialAction" in card
        assert len(card["potentialAction"]) == 1
        assert card["potentialAction"][0]["@type"] == "OpenUri"


# ========================= Notification Types Tests =========================


class TestNotificationTypes:
    """Tests fuer verschiedene Notification-Typen."""

    @pytest.mark.asyncio
    async def test_send_notification_document_processed(self, teams_service):
        """Sollte document_processed Benachrichtigung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_notification(
            notification_type=TeamsNotificationType.DOCUMENT_PROCESSED,
            title="Dokument verarbeitet",
            message="Rechnung #12345 wurde erfolgreich verarbeitet",
            context={"confidence": 0.95},
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_approval_required(self, teams_service):
        """Sollte approval_required Benachrichtigung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_notification(
            notification_type=TeamsNotificationType.APPROVAL_REQUIRED,
            title="Genehmigung erforderlich",
            message="Rechnung #12345 benoetigt Genehmigung",
            priority=TeamsMessagePriority.HIGH,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_disabled_type(self, teams_service):
        """Sollte nicht senden wenn Notification-Typ deaktiviert."""
        # Typ nicht in aktivierten Typen
        teams_service._notification_types = {"document_processed"}

        result = await teams_service.send_notification(
            notification_type="workflow_completed",  # nicht aktiviert
            title="Workflow abgeschlossen",
            message="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_should_send_notification_checks_enabled_and_type(self, teams_service):
        """Sollte nur aktivierte Notification-Typen senden."""
        # Aktivierter Typ
        assert teams_service.should_send_notification("document_processed") is True

        # Nicht aktivierter Typ
        teams_service._notification_types = {"document_processed"}
        assert teams_service.should_send_notification("workflow_completed") is False

        # Service deaktiviert
        teams_service._enabled = False
        assert teams_service.should_send_notification("document_processed") is False

    @pytest.mark.asyncio
    async def test_send_notification_message_card_mode(self, teams_service):
        """Sollte Message Card Mode unterstuetzen."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_notification(
            notification_type=TeamsNotificationType.SYSTEM_ALERT,
            title="Test",
            message="Test-Nachricht",
            use_adaptive_card=False,  # Legacy Mode
        )

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["@type"] == "MessageCard"


# ========================= Color and Icon Tests =========================


class TestColorAndIconSelection:
    """Tests fuer Farb- und Icon-Auswahl."""

    def test_get_notification_color_urgent_priority(self, teams_service):
        """Sollte Rot fuer URGENT Prioritaet verwenden."""
        color = teams_service._get_notification_color(
            "document_processed",
            TeamsMessagePriority.URGENT
        )
        assert color == "FF0000"

    def test_get_notification_color_high_priority(self, teams_service):
        """Sollte Orange fuer HIGH Prioritaet verwenden."""
        color = teams_service._get_notification_color(
            "document_processed",
            TeamsMessagePriority.HIGH
        )
        assert color == "FF8C00"

    def test_get_notification_color_document_processed(self, teams_service):
        """Sollte Gruen fuer document_processed verwenden."""
        color = teams_service._get_notification_color(
            "document_processed",
            TeamsMessagePriority.NORMAL
        )
        assert color == "36A64F"

    def test_get_notification_color_document_error(self, teams_service):
        """Sollte Rot fuer document_error verwenden."""
        color = teams_service._get_notification_color(
            "document_error",
            TeamsMessagePriority.NORMAL
        )
        assert color == "FF0000"

    def test_get_notification_color_payment_reminder(self, teams_service):
        """Sollte Blau fuer payment_reminder verwenden."""
        color = teams_service._get_notification_color(
            "payment_reminder",
            TeamsMessagePriority.NORMAL
        )
        assert color == "0076D7"

    def test_get_notification_color_default(self, teams_service):
        """Sollte Microsoft Blau fuer unbekannte Typen verwenden."""
        color = teams_service._get_notification_color(
            "unknown_type",
            TeamsMessagePriority.NORMAL
        )
        assert color == "0076D7"

    def test_get_notification_icon_document_processed(self, teams_service):
        """Sollte Checkmark-Icon fuer document_processed verwenden."""
        icon = teams_service._get_notification_icon("document_processed")
        assert icon == "\u2705"

    def test_get_notification_icon_high_risk_entity(self, teams_service):
        """Sollte Warning-Icon fuer high_risk_entity verwenden."""
        icon = teams_service._get_notification_icon("high_risk_entity")
        assert icon == "\u26A0\uFE0F"

    def test_get_notification_icon_payment_reminder(self, teams_service):
        """Sollte Credit Card-Icon fuer payment_reminder verwenden."""
        icon = teams_service._get_notification_icon("payment_reminder")
        assert icon == "\U0001F4B3"

    def test_get_notification_icon_default(self, teams_service):
        """Sollte Bell-Icon fuer unbekannte Typen verwenden."""
        icon = teams_service._get_notification_icon("unknown_type")
        assert icon == "\U0001F514"


# ========================= Specialized Notification Tests =========================


class TestSpecializedNotifications:
    """Tests fuer spezialisierte Benachrichtigungsmethoden."""

    @pytest.mark.asyncio
    async def test_send_document_notification_success(self, teams_service):
        """Sollte Dokument-Erfolgsbenachrichtigung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_document_notification(
            document_id="doc-123",
            document_name="Rechnung_2024.pdf",
            success=True,
            confidence=0.95,
            document_url="https://example.com/doc/123",
        )

        assert result is True
        call_args = mock_client.post.call_args
        payload_str = str(call_args[1]["json"])
        assert "Rechnung_2024.pdf" in payload_str
        assert "95.0%" in payload_str

    @pytest.mark.asyncio
    async def test_send_document_notification_error(self, teams_service):
        """Sollte Dokument-Fehlerbenachrichtigung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_document_notification(
            document_id="doc-123",
            document_name="Korrupt.pdf",
            success=False,
            error_message="Datei konnte nicht gelesen werden",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_approval_notification(self, teams_service):
        """Sollte Genehmigungsanfrage senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_approval_notification(
            title="Rechnungsfreigabe",
            description="Rechnung #12345 benoetigt Ihre Genehmigung",
            requester="Max Mustermann",
            approve_url="https://example.com/approve",
            reject_url="https://example.com/reject",
        )

        assert result is True
        call_args = mock_client.post.call_args
        payload_str = str(call_args[1]["json"])
        assert "Genehmigen" in payload_str
        assert "Ablehnen" in payload_str

    @pytest.mark.asyncio
    async def test_send_alert(self, teams_service):
        """Sollte System-Alert senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_alert(
            title="GPU Speicher kritisch",
            message="VRAM-Auslastung bei 95%",
            severity="critical",
            alert_url="https://example.com/alerts/123",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_payment_reminder(self, teams_service):
        """Sollte Zahlungserinnerung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.send_payment_reminder(
            invoice_number="RE-2024-001",
            amount=1234.56,
            due_date=datetime(2024, 1, 15),
            days_overdue=10,
            customer_name="Test GmbH",
            invoice_url="https://example.com/invoice/123",
        )

        assert result is True
        call_args = mock_client.post.call_args
        payload_str = str(call_args[1]["json"])
        assert "RE-2024-001" in payload_str
        assert "1234.56" in payload_str


# ========================= Error Handling Tests =========================


class TestErrorHandling:
    """Tests fuer Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_send_webhook_message_handles_request_error(self, teams_service):
        """Sollte RequestError gracefully handeln."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
        teams_service._client = mock_client

        result = await teams_service.send_webhook_message({"test": "payload"}, retry_count=2)

        assert result is False
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_notification_service_disabled(self, teams_service):
        """Sollte False zurueckgeben wenn Service deaktiviert."""
        teams_service._enabled = False

        result = await teams_service.send_notification(
            notification_type=TeamsNotificationType.SYSTEM_ALERT,
            title="Test",
            message="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_close_client_cleanup(self, teams_service):
        """Sollte HTTP-Client beim Close schliessen."""
        mock_client = AsyncMock()
        teams_service._client = mock_client

        await teams_service.close()

        mock_client.aclose.assert_called_once()
        assert teams_service._client is None


# ========================= Connection Testing Tests =========================


class TestConnectionTesting:
    """Tests fuer Connection Testing."""

    @pytest.mark.asyncio
    async def test_test_connection_webhook_success(self, teams_service):
        """Sollte Webhook-Verbindung erfolgreich testen."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.test_connection()

        assert result["enabled"] is True
        assert result["webhook_configured"] is True
        assert result["webhook_test"] == "success"

    @pytest.mark.asyncio
    async def test_test_connection_webhook_failed(self, teams_service):
        """Sollte Webhook-Fehler korrekt reporten."""
        mock_response = Mock()
        mock_response.status_code = 400

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        teams_service._client = mock_client

        result = await teams_service.test_connection()

        assert result["webhook_test"] == "failed"

    @pytest.mark.asyncio
    async def test_test_connection_disabled(self, mock_settings_disabled):
        """Sollte bei deaktiviertem Service nur Basis-Info zurueckgeben."""
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings_disabled):
            service = TeamsService()
            result = await service.test_connection()

            assert result["enabled"] is False
            assert result["webhook_test"] is None

        TeamsService._instance = None


# ========================= Factory Function Tests =========================


class TestFactoryFunctions:
    """Tests fuer Factory-Funktionen."""

    def test_get_teams_service_singleton(self, mock_settings):
        """get_teams_service sollte Singleton zurueckgeben."""
        # Reset global
        import app.services.ms_teams_service as teams_module
        teams_module._teams_service = None
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service1 = get_teams_service()
            service2 = get_teams_service()

            assert service1 is service2

        TeamsService._instance = None
        teams_module._teams_service = None

    @pytest.mark.asyncio
    async def test_send_teams_notification_convenience(self, mock_settings):
        """send_teams_notification sollte als Convenience-Funktion arbeiten."""
        TeamsService._instance = None

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service = TeamsService()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await send_teams_notification(
                notification_type="document_processed",
                title="Test",
                message="Test-Nachricht",
                priority="high",
            )

            assert result is True

        TeamsService._instance = None

    @pytest.mark.asyncio
    async def test_send_teams_notification_invalid_priority_defaults_to_normal(self, mock_settings):
        """Sollte bei ungueltiger Prioritaet auf NORMAL defaulten."""
        TeamsService._instance = None

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service = TeamsService()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            # Ungueltige Prioritaet
            result = await send_teams_notification(
                notification_type="document_processed",
                title="Test",
                message="Test",
                priority="invalid_priority",
            )

            assert result is True

        TeamsService._instance = None

    @pytest.mark.asyncio
    async def test_send_teams_notification_with_actions(self, mock_settings):
        """Sollte Actions aus Dict konvertieren."""
        TeamsService._instance = None

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service = TeamsService()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await send_teams_notification(
                notification_type="document_processed",
                title="Test",
                message="Test",
                actions=[
                    {"type": "Action.OpenUrl", "title": "Oeffnen", "url": "https://example.com"},
                ],
            )

            assert result is True

        TeamsService._instance = None


# ========================= Integration Tests =========================


class TestTeamsServiceIntegration:
    """Integration-Tests fuer komplette Workflows."""

    @pytest.mark.asyncio
    async def test_full_notification_workflow(self, mock_settings):
        """Vollstaendiger Workflow: Notification mit Adaptive Card."""
        TeamsService._instance = None

        with patch("app.services.ms_teams_service.app_settings", mock_settings):
            service = TeamsService()

            mock_response = Mock()
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await service.send_notification(
                notification_type=TeamsNotificationType.HIGH_RISK_ENTITY,
                title="Risiko-Warnung",
                message="Entity zeigt erhoehtes Risiko",
                context={
                    "risk_score": 85,
                    "payment_delay": 45,
                    "iban": "DE89370400440532013000",  # Sollte gefiltert werden
                },
                priority=TeamsMessagePriority.URGENT,
                actions=[
                    TeamsAction(type="Action.OpenUrl", title="Details", url="https://example.com"),
                ],
            )

            assert result is True
            mock_client.post.assert_called_once()

            # Prüfe dass IBAN nicht gesendet wurde
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            payload_str = str(payload)
            assert "DE89370400440532013000" not in payload_str

        TeamsService._instance = None
