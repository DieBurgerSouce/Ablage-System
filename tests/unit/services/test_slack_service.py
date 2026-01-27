# -*- coding: utf-8 -*-
"""
Unit Tests fuer SlackService.

Testet:
- Webhook-Benachrichtigungen
- Bot Token API
- Rate Limiting (Sliding Window)
- PII Masking (IBAN, Email, Kundennr)
- Block Kit Formatting
- Notification Types
- Error Handling und Retries
- Connection Testing

Feinpoliert und durchdacht - Slack-Integration Tests.
"""

import pytest
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import httpx
import pytest_asyncio

from app.services.slack_service import (
    SlackService,
    SlackMessage,
    SlackAttachment,
    SlackNotificationType,
    SlackMessagePriority,
    SlackServiceError,
    SlackRateLimitError,
    get_slack_service,
    send_slack_notification,
)


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_settings():
    """Mock app settings for Slack configuration."""
    settings = Mock()
    settings.SLACK_WEBHOOK_URL = Mock()
    settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = "https://hooks.slack.com/services/TEST/WEBHOOK/URL"
    settings.SLACK_BOT_TOKEN = Mock()
    settings.SLACK_BOT_TOKEN.get_secret_value.return_value = "xoxb-test-bot-token"
    settings.SLACK_DEFAULT_CHANNEL = "#allgemein"
    settings.SLACK_ENABLED = True
    settings.SLACK_NOTIFICATION_TYPES = [
        "document_processed",
        "approval_required",
        "system_alert",
        "high_risk_entity",
    ]
    settings.SLACK_RATE_LIMIT_PER_MINUTE = 30
    return settings


@pytest.fixture
def mock_settings_webhook_only():
    """Mock settings with only webhook configured."""
    settings = Mock()
    settings.SLACK_WEBHOOK_URL = Mock()
    settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = "https://hooks.slack.com/services/TEST/WEBHOOK"
    settings.SLACK_BOT_TOKEN = None
    settings.SLACK_DEFAULT_CHANNEL = "#allgemein"
    settings.SLACK_ENABLED = True
    settings.SLACK_NOTIFICATION_TYPES = ["document_processed", "system_alert"]
    settings.SLACK_RATE_LIMIT_PER_MINUTE = 30
    return settings


@pytest.fixture
def mock_settings_disabled():
    """Mock settings with Slack disabled."""
    settings = Mock()
    settings.SLACK_WEBHOOK_URL = None
    settings.SLACK_BOT_TOKEN = None
    settings.SLACK_DEFAULT_CHANNEL = "#allgemein"
    settings.SLACK_ENABLED = False
    settings.SLACK_NOTIFICATION_TYPES = []
    settings.SLACK_RATE_LIMIT_PER_MINUTE = 30
    return settings


@pytest.fixture
async def mock_httpx_client():
    """Mock httpx AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def slack_service(mock_settings):
    """Create SlackService instance with mocked settings."""
    # Reset singleton
    SlackService._instance = None

    with patch("app.services.slack_service.app_settings", mock_settings):
        service = SlackService()
        # Prevent re-initialization
        service._initialized = False
        service.__init__()
        yield service

    # Cleanup
    SlackService._instance = None


@pytest.fixture
def sample_slack_message() -> SlackMessage:
    """Provide sample Slack message."""
    return SlackMessage(
        channel="#test",
        text="Test-Nachricht",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Dies ist eine Test-Nachricht",
                },
            }
        ],
    )


@pytest.fixture
def sample_notification_context() -> Dict[str, Any]:
    """Provide sample notification context."""
    return {
        "document_id": str(uuid4()),
        "confidence": 0.95,
        "backend": "deepseek",
        "processing_time": 1.5,
    }


# ========================= Initialization Tests =========================


class TestSlackServiceInitialization:
    """Tests für SlackService Initialisierung."""

    def test_initialization_with_webhook_and_bot(self, mock_settings):
        """Service sollte mit Webhook und Bot-Token initialisiert werden."""
        # Reset singleton
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings):
            service = SlackService()

            assert service._webhook_url == "https://hooks.slack.com/services/TEST/WEBHOOK/URL"
            assert service._bot_token == "xoxb-test-bot-token"
            assert service._default_channel == "#allgemein"
            assert service._enabled is True
            assert service._rate_limit_per_minute == 30

        SlackService._instance = None

    def test_initialization_webhook_only(self, mock_settings_webhook_only):
        """Service sollte nur mit Webhook funktionieren."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings_webhook_only):
            service = SlackService()

            assert service._webhook_url is not None
            assert service._bot_token is None
            assert service.is_enabled is True

        SlackService._instance = None

    def test_initialization_disabled(self, mock_settings_disabled):
        """Service sollte deaktiviert sein wenn keine Credentials."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings_disabled):
            service = SlackService()

            assert service.is_enabled is False

        SlackService._instance = None

    def test_singleton_pattern(self, mock_settings):
        """Service sollte Singleton-Pattern verwenden."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings):
            service1 = SlackService()
            service2 = SlackService()

            assert service1 is service2

        SlackService._instance = None

    def test_invalid_webhook_url_detection(self):
        """Service sollte ungueltige Webhook-URLs erkennen."""
        settings = Mock()
        settings.SLACK_WEBHOOK_URL = Mock()
        settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = "invalid-url"
        settings.SLACK_BOT_TOKEN = None
        settings.SLACK_DEFAULT_CHANNEL = "#test"
        settings.SLACK_ENABLED = True
        settings.SLACK_NOTIFICATION_TYPES = []
        settings.SLACK_RATE_LIMIT_PER_MINUTE = 30

        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", settings):
            service = SlackService()
            # URL wird als ungueltig erkannt und auf None gesetzt
            assert service._webhook_url is None

        SlackService._instance = None

    def test_non_slack_webhook_warning(self):
        """Service sollte bei nicht-slack.com URLs warnen."""
        settings = Mock()
        settings.SLACK_WEBHOOK_URL = Mock()
        settings.SLACK_WEBHOOK_URL.get_secret_value.return_value = "https://evil.com/webhook"
        settings.SLACK_BOT_TOKEN = None
        settings.SLACK_DEFAULT_CHANNEL = "#test"
        settings.SLACK_ENABLED = True
        settings.SLACK_NOTIFICATION_TYPES = []
        settings.SLACK_RATE_LIMIT_PER_MINUTE = 30

        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", settings):
            service = SlackService()
            # URL wird gesetzt aber gewarnt
            assert service._webhook_url == "https://evil.com/webhook"

        SlackService._instance = None

    def test_invalid_bot_token_format_warning(self):
        """Service sollte bei falschem Bot-Token-Format warnen."""
        settings = Mock()
        settings.SLACK_WEBHOOK_URL = None
        settings.SLACK_BOT_TOKEN = Mock()
        settings.SLACK_BOT_TOKEN.get_secret_value.return_value = "invalid-token-format"
        settings.SLACK_DEFAULT_CHANNEL = "#test"
        settings.SLACK_ENABLED = True
        settings.SLACK_NOTIFICATION_TYPES = []
        settings.SLACK_RATE_LIMIT_PER_MINUTE = 30

        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", settings):
            service = SlackService()
            # Token wird gesetzt aber gewarnt (sollte mit xoxb- beginnen)
            assert service._bot_token == "invalid-token-format"

        SlackService._instance = None


# ========================= Webhook Sending Tests =========================


class TestWebhookSending:
    """Tests für Webhook-Nachrichten."""

    @pytest.mark.asyncio
    async def test_send_webhook_message_success(self, slack_service, sample_slack_message):
        """Webhook-Nachricht sollte erfolgreich gesendet werden."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        slack_service._client = mock_client

        result = await slack_service.send_webhook_message(sample_slack_message)

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == slack_service._webhook_url
        assert "text" in call_args[1]["json"]

    @pytest.mark.asyncio
    async def test_send_webhook_message_no_webhook_configured(self, slack_service, sample_slack_message):
        """Sollte False zurückgeben wenn kein Webhook konfiguriert."""
        slack_service._webhook_url = None

        result = await slack_service.send_webhook_message(sample_slack_message)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_message_rate_limit_reached(self, slack_service, sample_slack_message):
        """Sollte SlackRateLimitError werfen bei Rate Limit."""
        # Rate Limit Window voll machen
        now = time.time()
        for _ in range(slack_service._rate_limit_per_minute):
            slack_service._rate_limit_window.append(now)

        with pytest.raises(SlackRateLimitError) as exc_info:
            await slack_service.send_webhook_message(sample_slack_message)

        assert "Rate Limit erreicht" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_webhook_message_retry_on_429(self, slack_service, sample_slack_message):
        """Sollte bei 429 (Rate Limit) retry mit Retry-After."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        mock_response.text = "rate_limited"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        with pytest.raises(SlackRateLimitError):
            await slack_service.send_webhook_message(sample_slack_message, retry_count=2)

        # Sollte 2x versucht haben
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_webhook_message_retry_on_timeout(self, slack_service, sample_slack_message):
        """Sollte bei Timeout retry mit exponential backoff."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        slack_service._client = mock_client

        result = await slack_service.send_webhook_message(sample_slack_message, retry_count=3)

        assert result is False
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_send_webhook_message_with_attachments(self, slack_service):
        """Sollte Attachments korrekt senden."""
        message = SlackMessage(
            text="Test mit Attachment",
            attachments=[
                SlackAttachment(
                    color="#36A64F",
                    title="Test Attachment",
                    text="Attachment-Text",
                )
            ],
        )

        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.send_webhook_message(message)

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["color"] == "#36A64F"

    @pytest.mark.asyncio
    async def test_send_webhook_message_records_rate_limit(self, slack_service, sample_slack_message):
        """Sollte gesendete Nachrichten für Rate Limiting aufzeichnen."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        initial_count = len(slack_service._rate_limit_window)

        await slack_service.send_webhook_message(sample_slack_message)

        assert len(slack_service._rate_limit_window) == initial_count + 1


# ========================= Bot Token API Tests =========================


class TestBotTokenAPI:
    """Tests für Bot Token API."""

    @pytest.mark.asyncio
    async def test_send_bot_message_success(self, slack_service, sample_slack_message):
        """Bot-Nachricht sollte erfolgreich gesendet werden."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
            "channel": "C1234567890",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        message_ts = await slack_service.send_bot_message(sample_slack_message)

        assert message_ts == "1234567890.123456"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://slack.com/api/chat.postMessage"
        assert "Authorization" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_send_bot_message_no_token_configured(self, slack_service, sample_slack_message):
        """Sollte None zurückgeben wenn kein Bot-Token."""
        slack_service._bot_token = None

        result = await slack_service.send_bot_message(sample_slack_message)

        assert result is None

    @pytest.mark.asyncio
    async def test_send_bot_message_channel_not_found(self, slack_service, sample_slack_message):
        """Sollte bei channel_not_found Error sofort abbrechen."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.send_bot_message(sample_slack_message, retry_count=3)

        assert result is None
        # Sollte nur 1x versuchen (nicht-retry-fähiger Fehler)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_bot_message_with_thread_ts(self, slack_service):
        """Sollte Thread-Antworten unterstützen."""
        message = SlackMessage(
            text="Thread-Antwort",
            thread_ts="1234567890.123456",
        )

        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "ts": "1234567890.123457",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        await slack_service.send_bot_message(message)

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["thread_ts"] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_send_bot_message_with_custom_channel(self, slack_service, sample_slack_message):
        """Sollte Custom-Channel-Override unterstützen."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "ts": "123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        await slack_service.send_bot_message(sample_slack_message, channel="#custom")

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["channel"] == "#custom"

    @pytest.mark.asyncio
    async def test_send_bot_message_rate_limit_check(self, slack_service, sample_slack_message):
        """Sollte Rate Limit auch bei Bot-API pruefen."""
        # Rate Limit voll machen
        now = time.time()
        for _ in range(slack_service._rate_limit_per_minute):
            slack_service._rate_limit_window.append(now)

        with pytest.raises(SlackRateLimitError):
            await slack_service.send_bot_message(sample_slack_message)


# ========================= Rate Limiting Tests =========================


class TestRateLimiting:
    """Tests für Rate Limiting (Sliding Window)."""

    def test_check_rate_limit_within_limit(self, slack_service):
        """Sollte True zurückgeben wenn unter Limit."""
        # Window leer
        assert slack_service._check_rate_limit() is True

    def test_check_rate_limit_at_limit(self, slack_service):
        """Sollte False zurückgeben wenn Limit erreicht."""
        now = time.time()
        # Window voll machen
        for _ in range(slack_service._rate_limit_per_minute):
            slack_service._rate_limit_window.append(now)

        assert slack_service._check_rate_limit() is False

    def test_check_rate_limit_sliding_window_cleanup(self, slack_service):
        """Sollte alte Timestamps aus Window entfernen."""
        # Alte Timestamps hinzufügen (älter als 60s)
        old_time = time.time() - 65
        for _ in range(10):
            slack_service._rate_limit_window.append(old_time)

        # Check sollte alte Einträge entfernen
        assert slack_service._check_rate_limit() is True
        assert len(slack_service._rate_limit_window) == 0

    def test_record_message_adds_timestamp(self, slack_service):
        """Sollte Timestamp beim Senden aufzeichnen."""
        initial_count = len(slack_service._rate_limit_window)

        slack_service._record_message()

        assert len(slack_service._rate_limit_window) == initial_count + 1

    def test_rate_limit_window_maxlen(self, slack_service):
        """Sollte maxlen für deque respektieren."""
        # Window über maxlen füllen
        expected_maxlen = slack_service._rate_limit_per_minute * 2
        for _ in range(expected_maxlen + 10):
            slack_service._rate_limit_window.append(time.time())

        # Sollte auf maxlen begrenzt sein
        assert len(slack_service._rate_limit_window) == expected_maxlen


# ========================= PII Masking Tests =========================


class TestPIIMasking:
    """Tests für PII-Maskierung in Context-Feldern."""

    @pytest.mark.asyncio
    async def test_context_filters_iban(self, slack_service):
        """Sollte IBAN aus Context-Feldern filtern."""
        context = {
            "iban": "DE89370400440532013000",
            "amount": 1234.56,
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
            icon=":white_check_mark:",
        )

        # IBAN sollte nicht in Blocks erscheinen
        blocks_str = str(blocks)
        assert "DE89370400440532013000" not in blocks_str
        assert "iban" not in blocks_str.lower()

    @pytest.mark.asyncio
    async def test_context_filters_vat_id(self, slack_service):
        """Sollte VAT-ID aus Context filtern."""
        context = {
            "vat_id": "DE123456789",
            "company": "Test GmbH",
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test-Nachricht",
            notification_type="high_risk_entity",
            context=context,
            icon=":warning:",
        )

        blocks_str = str(blocks)
        assert "DE123456789" not in blocks_str
        assert "vat_id" not in blocks_str.lower()

    @pytest.mark.asyncio
    async def test_context_filters_customer_number(self, slack_service):
        """Sollte Kundennummer aus Context filtern."""
        context = {
            "customer_number": "KD-12345",
            "kundennr": "67890",
            "amount": 999.99,
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test-Nachricht",
            notification_type="approval_required",
            context=context,
            icon=":hourglass:",
        )

        blocks_str = str(blocks)
        assert "KD-12345" not in blocks_str
        assert "67890" not in blocks_str
        assert "customer_number" not in blocks_str.lower()
        assert "kundennr" not in blocks_str.lower()

    @pytest.mark.asyncio
    async def test_context_allows_safe_fields(self, slack_service):
        """Sollte sichere Felder in Context anzeigen."""
        context = {
            "document_id": "doc-123",
            "confidence": 0.95,
            "backend": "deepseek",
            "processing_time": 1.5,
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
            icon=":white_check_mark:",
        )

        # Sichere Felder sollten erscheinen
        blocks_str = str(blocks)
        assert "doc-123" in blocks_str
        assert "0.95" in blocks_str
        assert "deepseek" in blocks_str


# ========================= Block Kit Formatting Tests =========================


class TestBlockKitFormatting:
    """Tests für Block Kit Nachrichtenformatierung."""

    def test_build_notification_blocks_header(self, slack_service):
        """Sollte Header-Block mit Icon und Titel erstellen."""
        blocks = slack_service._build_notification_blocks(
            title="Dokument verarbeitet",
            message="Rechnung #12345",
            notification_type="document_processed",
            context=None,
            icon=":white_check_mark:",
        )

        assert len(blocks) > 0
        header_block = blocks[0]
        assert header_block["type"] == "header"
        assert ":white_check_mark:" in header_block["text"]["text"]
        assert "Dokument verarbeitet" in header_block["text"]["text"]

    def test_build_notification_blocks_section(self, slack_service):
        """Sollte Section-Block mit Nachricht erstellen."""
        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Dies ist die Hauptnachricht",
            notification_type="system_alert",
            context=None,
            icon=":bell:",
        )

        # Section-Block suchen
        section_block = next(
            (b for b in blocks if b["type"] == "section" and "text" in b),
            None
        )
        assert section_block is not None
        assert section_block["text"]["text"] == "Dies ist die Hauptnachricht"

    def test_build_notification_blocks_context_fields(self, slack_service):
        """Sollte Context-Felder als Section mit Fields erstellen."""
        context = {
            "confidence": 0.95,
            "processing_time": 1.5,
            "word_count": 250,
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test-Nachricht",
            notification_type="document_processed",
            context=context,
            icon=":white_check_mark:",
        )

        # Section mit Fields suchen
        fields_block = next(
            (b for b in blocks if b["type"] == "section" and "fields" in b),
            None
        )
        assert fields_block is not None
        assert len(fields_block["fields"]) == 3

    def test_build_notification_blocks_footer_context(self, slack_service):
        """Sollte Footer mit Timestamp und Typ erstellen."""
        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test",
            notification_type="approval_required",
            context=None,
            icon=":hourglass:",
        )

        # Context-Block (Footer) suchen
        footer_block = next(
            (b for b in blocks if b["type"] == "context"),
            None
        )
        assert footer_block is not None
        assert "approval_required" in footer_block["elements"][0]["text"]

    def test_build_notification_blocks_divider(self, slack_service):
        """Sollte Divider vor Footer einfügen."""
        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test",
            notification_type="system_alert",
            context=None,
            icon=":bell:",
        )

        # Divider suchen
        divider_block = next(
            (b for b in blocks if b["type"] == "divider"),
            None
        )
        assert divider_block is not None

    def test_build_notification_blocks_value_formatting(self, slack_service):
        """Sollte Werte korrekt formatieren (bool, float, datetime)."""
        context = {
            "is_valid": True,
            "confidence": 0.953678,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
        }

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test",
            notification_type="document_processed",
            context=context,
            icon=":white_check_mark:",
        )

        blocks_str = str(blocks)
        # Bool als Ja/Nein
        assert "Ja" in blocks_str
        # Float mit 2 Dezimalstellen
        assert "0.95" in blocks_str
        # Datetime formatiert
        assert "15.01.2024" in blocks_str

    def test_build_notification_blocks_max_10_fields_per_section(self, slack_service):
        """Sollte max 10 Felder pro Section haben."""
        # 25 Felder
        context = {f"field_{i}": i for i in range(25)}

        blocks = slack_service._build_notification_blocks(
            title="Test",
            message="Test",
            notification_type="document_processed",
            context=context,
            icon=":white_check_mark:",
        )

        # Sections mit Fields zählen
        field_sections = [b for b in blocks if b["type"] == "section" and "fields" in b]
        assert len(field_sections) == 3  # 10 + 10 + 5


# ========================= Notification Types Tests =========================


class TestNotificationTypes:
    """Tests für verschiedene Notification-Typen."""

    @pytest.mark.asyncio
    async def test_send_notification_document_processed(self, slack_service):
        """Sollte document_processed Benachrichtigung senden."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "ts": "123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.send_notification(
            notification_type=SlackNotificationType.DOCUMENT_PROCESSED,
            title="Dokument verarbeitet",
            message="Rechnung #12345 wurde erfolgreich verarbeitet",
            context={"confidence": 0.95},
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_approval_required(self, slack_service):
        """Sollte approval_required Benachrichtigung senden."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        # Bevorzugt Webhook wenn kein Bot-Token
        slack_service._bot_token = None

        result = await slack_service.send_notification(
            notification_type=SlackNotificationType.APPROVAL_REQUIRED,
            title="Genehmigung erforderlich",
            message="Rechnung #12345 benötigt Genehmigung",
            priority=SlackMessagePriority.HIGH,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_notification_disabled_type(self, slack_service):
        """Sollte nicht senden wenn Notification-Typ deaktiviert."""
        # Typ nicht in aktivierten Typen
        result = await slack_service.send_notification(
            notification_type="workflow_completed",  # nicht in SLACK_NOTIFICATION_TYPES
            title="Workflow abgeschlossen",
            message="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_notification_custom_channel(self, slack_service):
        """Sollte Custom-Channel unterstützen."""
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "ts": "123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        await slack_service.send_notification(
            notification_type=SlackNotificationType.SYSTEM_ALERT,
            title="System-Alert",
            message="Test",
            channel="#alerts",
        )

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["channel"] == "#alerts"

    @pytest.mark.asyncio
    async def test_should_send_notification_checks_enabled_and_type(self, slack_service):
        """Sollte nur aktivierte Notification-Typen senden."""
        # Aktivierter Typ
        assert slack_service.should_send_notification("document_processed") is True

        # Nicht aktivierter Typ
        assert slack_service.should_send_notification("workflow_completed") is False

        # Service deaktiviert
        slack_service._enabled = False
        assert slack_service.should_send_notification("document_processed") is False


# ========================= Color and Icon Tests =========================


class TestColorAndIconSelection:
    """Tests für Farb- und Icon-Auswahl."""

    def test_get_notification_color_urgent_priority(self, slack_service):
        """Sollte Rot für URGENT Priorität verwenden."""
        color = slack_service._get_notification_color(
            "document_processed",
            SlackMessagePriority.URGENT
        )
        assert color == "#FF0000"

    def test_get_notification_color_high_priority(self, slack_service):
        """Sollte Orange für HIGH Priorität verwenden."""
        color = slack_service._get_notification_color(
            "document_processed",
            SlackMessagePriority.HIGH
        )
        assert color == "#FF8C00"

    def test_get_notification_color_document_processed(self, slack_service):
        """Sollte Gruen für document_processed verwenden."""
        color = slack_service._get_notification_color(
            "document_processed",
            SlackMessagePriority.NORMAL
        )
        assert color == "#36A64F"

    def test_get_notification_color_document_error(self, slack_service):
        """Sollte Rot für document_error verwenden."""
        color = slack_service._get_notification_color(
            "document_error",
            SlackMessagePriority.NORMAL
        )
        assert color == "#FF0000"

    def test_get_notification_color_skonto_expiring(self, slack_service):
        """Sollte Orange für skonto_expiring verwenden."""
        color = slack_service._get_notification_color(
            "skonto_expiring",
            SlackMessagePriority.NORMAL
        )
        assert color == "#FFA500"

    def test_get_notification_color_default(self, slack_service):
        """Sollte Grau für unbekannte Typen verwenden."""
        color = slack_service._get_notification_color(
            "unknown_type",
            SlackMessagePriority.NORMAL
        )
        assert color == "#808080"

    def test_get_notification_icon_document_processed(self, slack_service):
        """Sollte Checkmark-Icon für document_processed verwenden."""
        icon = slack_service._get_notification_icon("document_processed")
        assert icon == ":white_check_mark:"

    def test_get_notification_icon_high_risk_entity(self, slack_service):
        """Sollte Warning-Icon für high_risk_entity verwenden."""
        icon = slack_service._get_notification_icon("high_risk_entity")
        assert icon == ":warning:"

    def test_get_notification_icon_skonto_expiring(self, slack_service):
        """Sollte Moneybag-Icon für skonto_expiring verwenden."""
        icon = slack_service._get_notification_icon("skonto_expiring")
        assert icon == ":moneybag:"

    def test_get_notification_icon_default(self, slack_service):
        """Sollte Bell-Icon für unbekannte Typen verwenden."""
        icon = slack_service._get_notification_icon("unknown_type")
        assert icon == ":bell:"


# ========================= Error Handling Tests =========================


class TestErrorHandling:
    """Tests für Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_send_webhook_message_handles_request_error(self, slack_service, sample_slack_message):
        """Sollte RequestError gracefully handeln."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
        slack_service._client = mock_client

        result = await slack_service.send_webhook_message(sample_slack_message, retry_count=2)

        assert result is False
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_bot_message_handles_timeout(self, slack_service, sample_slack_message):
        """Sollte Timeout gracefully handeln."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        slack_service._client = mock_client

        result = await slack_service.send_bot_message(sample_slack_message, retry_count=2)

        assert result is None
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_send_notification_service_disabled(self, slack_service):
        """Sollte False zurückgeben wenn Service deaktiviert."""
        slack_service._enabled = False

        result = await slack_service.send_notification(
            notification_type=SlackNotificationType.SYSTEM_ALERT,
            title="Test",
            message="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_close_client_cleanup(self, slack_service):
        """Sollte HTTP-Client beim Close schließen."""
        mock_client = AsyncMock()
        slack_service._client = mock_client

        await slack_service.close()

        mock_client.aclose.assert_called_once()
        assert slack_service._client is None


# ========================= Connection Testing Tests =========================


class TestConnectionTesting:
    """Tests für Connection Testing."""

    @pytest.mark.asyncio
    async def test_test_connection_webhook_success(self, slack_service):
        """Sollte Webhook-Verbindung erfolgreich testen."""
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.test_connection()

        assert result["enabled"] is True
        assert result["webhook_configured"] is True
        assert result["webhook_test"] == "success"

    @pytest.mark.asyncio
    async def test_test_connection_bot_success(self, slack_service):
        """Sollte Bot-Verbindung erfolgreich testen."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "team": "Test Team",
            "user": "test_bot",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.test_connection()

        assert result["bot_test"]["status"] == "success"
        assert result["bot_test"]["team"] == "Test Team"

    @pytest.mark.asyncio
    async def test_test_connection_disabled(self, mock_settings_disabled):
        """Sollte bei deaktiviertem Service nur Basis-Info zurückgeben."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings_disabled):
            service = SlackService()
            result = await service.test_connection()

            assert result["enabled"] is False
            assert result["webhook_test"] is None
            assert result["bot_test"] is None

        SlackService._instance = None

    @pytest.mark.asyncio
    async def test_test_connection_webhook_failed(self, slack_service):
        """Sollte Webhook-Fehler korrekt reporten."""
        mock_response = Mock()
        mock_response.status_code = 400

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        slack_service._client = mock_client

        result = await slack_service.test_connection()

        assert result["webhook_test"] == "failed"


# ========================= Factory Function Tests =========================


class TestFactoryFunctions:
    """Tests für Factory-Funktionen."""

    def test_get_slack_service_singleton(self, mock_settings):
        """get_slack_service sollte Singleton zurückgeben."""
        # Reset global
        import app.services.slack_service as slack_module
        slack_module._slack_service = None
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings):
            service1 = get_slack_service()
            service2 = get_slack_service()

            assert service1 is service2

        SlackService._instance = None
        slack_module._slack_service = None

    @pytest.mark.asyncio
    async def test_send_slack_notification_convenience(self, mock_settings):
        """send_slack_notification sollte als Convenience-Funktion arbeiten."""
        SlackService._instance = None

        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "ts": "123"}

        with patch("app.services.slack_service.app_settings", mock_settings):
            service = SlackService()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await send_slack_notification(
                notification_type="document_processed",
                title="Test",
                message="Test-Nachricht",
                priority="high",
            )

            assert result is True

        SlackService._instance = None

    @pytest.mark.asyncio
    async def test_send_slack_notification_invalid_priority_defaults_to_normal(self, mock_settings):
        """Sollte bei ungültiger Priorität auf NORMAL defaulten."""
        SlackService._instance = None

        mock_response = Mock()
        mock_response.json.return_value = {"ok": True, "ts": "123"}

        with patch("app.services.slack_service.app_settings", mock_settings):
            service = SlackService()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            # Ungültige Priorität
            result = await send_slack_notification(
                notification_type="document_processed",
                title="Test",
                message="Test",
                priority="invalid_priority",
            )

            assert result is True

        SlackService._instance = None


# ========================= Integration Tests =========================


class TestSlackServiceIntegration:
    """Integration-Tests für komplette Workflows."""

    @pytest.mark.asyncio
    async def test_full_notification_workflow_with_bot(self, mock_settings):
        """Vollständiger Workflow: Notification mit Bot-API."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings):
            service = SlackService()

            mock_response = Mock()
            mock_response.json.return_value = {
                "ok": True,
                "ts": "1234567890.123456",
                "channel": "C1234567890",
            }

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await service.send_notification(
                notification_type=SlackNotificationType.HIGH_RISK_ENTITY,
                title="Risiko-Warnung",
                message="Entity zeigt erhöhtes Risiko",
                context={
                    "risk_score": 85,
                    "payment_delay": 45,
                    "iban": "DE89370400440532013000",  # Sollte gefiltert werden
                },
                priority=SlackMessagePriority.URGENT,
                channel="#risk-alerts",
            )

            assert result is True
            mock_client.post.assert_called_once()

            # Prüfe dass IBAN nicht gesendet wurde
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            payload_str = str(payload)
            assert "DE89370400440532013000" not in payload_str

        SlackService._instance = None

    @pytest.mark.asyncio
    async def test_full_notification_workflow_with_webhook_fallback(self, mock_settings_webhook_only):
        """Vollständiger Workflow: Fallback auf Webhook wenn kein Bot-Token."""
        SlackService._instance = None

        with patch("app.services.slack_service.app_settings", mock_settings_webhook_only):
            service = SlackService()

            mock_response = Mock()
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await service.send_notification(
                notification_type=SlackNotificationType.DOCUMENT_PROCESSED,
                title="Dokument verarbeitet",
                message="Erfolgreich verarbeitet",
                context={"confidence": 0.95},
            )

            assert result is True
            # Sollte Webhook verwendet haben
            call_args = mock_client.post.call_args
            assert "hooks.slack.com" in call_args[0][0]

        SlackService._instance = None
