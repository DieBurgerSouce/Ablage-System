# -*- coding: utf-8 -*-
"""
Tests für WebhookDispatcher Service.

Testet Event-Dispatching, Payload-Erstellung und Delivery-Logik.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx

from app.services.webhook_dispatcher import (
    WebhookDispatcher,
    WebhookCircuitBreaker,
    WebhookEventType,
    DeliveryStatus,
    CircuitState,
    get_webhook_dispatcher,
    get_webhook_circuit_breaker,
)


class TestWebhookCircuitBreaker:
    """Tests für WebhookCircuitBreaker."""

    def setup_method(self):
        """Reset circuit breaker vor jedem Test."""
        self.circuit_breaker = WebhookCircuitBreaker()

    def test_initial_state_closed(self):
        """Circuit sollte initial CLOSED sein."""
        state = self.circuit_breaker.get_state("https://example.com/webhook")
        assert state == CircuitState.CLOSED

    def test_is_allowed_when_closed(self):
        """Requests sollten bei CLOSED erlaubt sein."""
        assert self.circuit_breaker.is_allowed("https://example.com/webhook")

    def test_opens_after_threshold_failures(self):
        """Circuit sollte nach FAILURE_THRESHOLD Fehlern öffnen."""
        url = "https://example.com/webhook"

        for _ in range(WebhookCircuitBreaker.FAILURE_THRESHOLD):
            self.circuit_breaker.record_failure(url)

        assert self.circuit_breaker.get_state(url) == CircuitState.OPEN
        assert not self.circuit_breaker.is_allowed(url)

    def test_success_resets_failure_count(self):
        """Erfolg sollte Failure-Count zurücksetzen."""
        url = "https://example.com/webhook"

        # Ein paar Fehler, aber unter Threshold
        for _ in range(3):
            self.circuit_breaker.record_failure(url)

        # Erfolg
        self.circuit_breaker.record_success(url)

        # Noch mehr Fehler sollten nicht zum Öffnen führen
        for _ in range(3):
            self.circuit_breaker.record_failure(url)

        assert self.circuit_breaker.get_state(url) == CircuitState.CLOSED

    def test_half_open_closes_after_successes(self):
        """Circuit sollte nach SUCCESS_THRESHOLD in HALF_OPEN schließen."""
        url = "https://example.com/webhook"

        # Öffne Circuit
        for _ in range(WebhookCircuitBreaker.FAILURE_THRESHOLD):
            self.circuit_breaker.record_failure(url)

        # Simuliere HALF_OPEN State
        self.circuit_breaker._states[url] = CircuitState.HALF_OPEN
        self.circuit_breaker._success_counts[url] = 0

        # Erfolgreich antworten
        for _ in range(WebhookCircuitBreaker.SUCCESS_THRESHOLD):
            self.circuit_breaker.record_success(url)

        assert self.circuit_breaker.get_state(url) == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        """Circuit sollte bei Fehler in HALF_OPEN sofort wieder öffnen."""
        url = "https://example.com/webhook"

        # Simuliere HALF_OPEN State
        self.circuit_breaker._states[url] = CircuitState.HALF_OPEN

        # Fehler
        self.circuit_breaker.record_failure(url)

        assert self.circuit_breaker.get_state(url) == CircuitState.OPEN

    def test_half_open_limited_calls(self):
        """HALF_OPEN sollte nur begrenzte Test-Calls erlauben."""
        url = "https://example.com/webhook"

        # Simuliere HALF_OPEN State
        self.circuit_breaker._states[url] = CircuitState.HALF_OPEN
        self.circuit_breaker._half_open_calls[url] = 0

        # Sollte MAX_CALLS erlauben
        allowed_count = 0
        for _ in range(WebhookCircuitBreaker.HALF_OPEN_MAX_CALLS + 5):
            if self.circuit_breaker.is_allowed(url):
                allowed_count += 1

        assert allowed_count == WebhookCircuitBreaker.HALF_OPEN_MAX_CALLS

    def test_reset_single_url(self):
        """Reset sollte nur einen URL-Eintrag entfernen."""
        url1 = "https://example1.com/webhook"
        url2 = "https://example2.com/webhook"

        # Beide URLs mit Fehlern
        for _ in range(3):
            self.circuit_breaker.record_failure(url1)
            self.circuit_breaker.record_failure(url2)

        # Reset nur url1
        self.circuit_breaker.reset(url1)

        assert self.circuit_breaker._failure_counts.get(url1, 0) == 0
        assert self.circuit_breaker._failure_counts.get(url2, 0) == 3

    def test_get_stats(self):
        """Stats sollten korrekte Werte zurückgeben."""
        url = "https://example.com/webhook"

        # Öffne Circuit
        for _ in range(WebhookCircuitBreaker.FAILURE_THRESHOLD):
            self.circuit_breaker.record_failure(url)

        stats = self.circuit_breaker.get_stats()

        assert stats["total_tracked"] == 1
        assert stats["by_state"][CircuitState.OPEN.value] == 1
        assert len(stats["open_circuits"]) == 1
        assert stats["open_circuits"][0]["failures"] == WebhookCircuitBreaker.FAILURE_THRESHOLD


class TestWebhookDispatcher:
    """Tests für WebhookDispatcher."""

    @pytest.fixture
    def dispatcher(self):
        """Erstellt WebhookDispatcher-Instanz."""
        return WebhookDispatcher()

    @pytest.fixture
    def mock_db(self):
        """Mock AsyncSession."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_subscription(self):
        """Mock WebhookSubscription."""
        sub = MagicMock()
        sub.id = uuid4()
        sub.user_id = uuid4()
        sub.url = "https://example.com/webhook"
        sub.secret = "test_secret_key_123"
        sub.is_active = True
        sub.event_types = ["document.processed"]
        sub.headers = {}
        sub.max_retries = 3
        sub.retry_delay_seconds = 60
        return sub

    def test_create_event_payload(self, dispatcher):
        """_create_event_payload sollte korrektes Payload erstellen."""
        payload = dispatcher._create_event_payload(
            event_type="document.processed",
            data={"document_id": "doc123", "filename": "test.pdf"},
            metadata={"source": "api"}
        )

        assert payload["event_type"] == "document.processed"
        assert payload["api_version"] == "v1"
        assert payload["data"]["document_id"] == "doc123"
        assert payload["metadata"]["source"] == "api"
        assert payload["event_id"].startswith("evt_")
        assert "created_at" in payload

    def test_create_event_payload_no_metadata(self, dispatcher):
        """_create_event_payload sollte ohne Metadata funktionieren."""
        payload = dispatcher._create_event_payload(
            event_type="ocr.started",
            data={"document_id": "doc456"}
        )

        assert payload["metadata"] == {}

    @pytest.mark.asyncio
    async def test_dispatch_event_no_subscriptions(self, dispatcher, mock_db):
        """dispatch_event sollte 0 zurückgeben wenn keine Subscriptions."""
        # Mock: keine Subscriptions gefunden
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        result = await dispatcher.dispatch_event(
            db=mock_db,
            user_id=uuid4(),
            event_type="document.processed",
            payload={"test": "data"}
        )

        assert result == 0

    @pytest.mark.asyncio
    async def test_dispatch_event_with_matching_subscription(
        self, dispatcher, mock_db, mock_subscription
    ):
        """dispatch_event sollte passende Subscriptions finden und dispatchen."""
        # Mock: eine Subscription gefunden
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_subscription])))
        ))

        # Mock HTTP Client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch.object(dispatcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            # Reset circuit breaker für diesen Test
            circuit_breaker = get_webhook_circuit_breaker()
            circuit_breaker.reset(mock_subscription.url)

            result = await dispatcher.dispatch_event(
                db=mock_db,
                user_id=mock_subscription.user_id,
                event_type="document.processed",
                payload={"document_id": "doc123"}
            )

            assert result == 1

    @pytest.mark.asyncio
    async def test_deliver_webhook_success(
        self, dispatcher, mock_db, mock_subscription
    ):
        """_deliver_webhook sollte bei 2xx True zurückgeben."""
        # Reset circuit breaker
        circuit_breaker = get_webhook_circuit_breaker()
        circuit_breaker.reset(mock_subscription.url)

        # Mock HTTP Response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch.object(dispatcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            payload = {
                "event_id": "evt_test123",
                "event_type": "document.processed",
                "data": {"test": "data"}
            }

            result = await dispatcher._deliver_webhook(
                db=mock_db,
                subscription=mock_subscription,
                payload=payload
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_deliver_webhook_circuit_open(
        self, dispatcher, mock_db, mock_subscription
    ):
        """_deliver_webhook sollte False zurückgeben wenn Circuit offen."""
        # Öffne Circuit
        circuit_breaker = get_webhook_circuit_breaker()
        for _ in range(WebhookCircuitBreaker.FAILURE_THRESHOLD):
            circuit_breaker.record_failure(mock_subscription.url)

        payload = {
            "event_id": "evt_test123",
            "event_type": "document.processed",
            "data": {"test": "data"}
        }

        result = await dispatcher._deliver_webhook(
            db=mock_db,
            subscription=mock_subscription,
            payload=payload
        )

        assert result is False

        # Cleanup
        circuit_breaker.reset(mock_subscription.url)

    @pytest.mark.asyncio
    async def test_deliver_webhook_client_error(
        self, dispatcher, mock_db, mock_subscription
    ):
        """_deliver_webhook sollte bei 4xx nicht retrien und False zurückgeben."""
        # Reset circuit breaker
        circuit_breaker = get_webhook_circuit_breaker()
        circuit_breaker.reset(mock_subscription.url)

        # Mock HTTP Response 400
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch.object(dispatcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            payload = {
                "event_id": "evt_test123",
                "event_type": "document.processed",
                "data": {"test": "data"}
            }

            result = await dispatcher._deliver_webhook(
                db=mock_db,
                subscription=mock_subscription,
                payload=payload
            )

            assert result is False
            # Sollte nur einmal aufgerufen werden (kein Retry bei 4xx)
            assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_deliver_webhook_timeout_retry(
        self, dispatcher, mock_db, mock_subscription
    ):
        """_deliver_webhook sollte bei Timeout retrien."""
        # Reset circuit breaker
        circuit_breaker = get_webhook_circuit_breaker()
        circuit_breaker.reset(mock_subscription.url)

        # Reduziere Retries für schnelleren Test
        mock_subscription.max_retries = 1
        mock_subscription.retry_delay_seconds = 0.01  # 10ms

        with patch.object(dispatcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_get_client.return_value = mock_client

            payload = {
                "event_id": "evt_test123",
                "event_type": "document.processed",
                "data": {"test": "data"}
            }

            result = await dispatcher._deliver_webhook(
                db=mock_db,
                subscription=mock_subscription,
                payload=payload
            )

            assert result is False
            # Sollte 2 mal aufgerufen werden (initial + 1 retry)
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_get_matching_subscriptions_wildcard(
        self, dispatcher, mock_db
    ):
        """_get_matching_subscriptions sollte Wildcards unterstützen."""
        user_id = uuid4()

        # Mock Subscriptions mit Wildcard
        sub1 = MagicMock()
        sub1.event_types = ["document.*"]  # Wildcard
        sub1.is_active = True

        sub2 = MagicMock()
        sub2.event_types = ["ocr.completed"]  # Spezifisch
        sub2.is_active = True

        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sub1, sub2])))
        ))

        # Test mit document.processed
        matching = await dispatcher._get_matching_subscriptions(
            db=mock_db,
            user_id=user_id,
            event_type="document.processed"
        )

        # sub1 sollte matchen (Wildcard), sub2 nicht
        assert sub1 in matching
        assert sub2 not in matching

    @pytest.mark.asyncio
    async def test_get_matching_subscriptions_empty_types(
        self, dispatcher, mock_db
    ):
        """_get_matching_subscriptions sollte leere event_types als 'alle' behandeln."""
        user_id = uuid4()

        # Mock Subscription ohne Event-Filter
        sub = MagicMock()
        sub.event_types = []  # Leer = alle Events
        sub.is_active = True

        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[sub])))
        ))

        matching = await dispatcher._get_matching_subscriptions(
            db=mock_db,
            user_id=user_id,
            event_type="any.event.type"
        )

        assert sub in matching


class TestWebhookEventTypes:
    """Tests für WebhookEventType Enum."""

    def test_document_events(self):
        """Document Events sollten korrekt definiert sein."""
        assert WebhookEventType.DOCUMENT_CREATED.value == "document.created"
        assert WebhookEventType.DOCUMENT_PROCESSED.value == "document.processed"
        assert WebhookEventType.DOCUMENT_FAILED.value == "document.failed"

    def test_ocr_events(self):
        """OCR Events sollten korrekt definiert sein."""
        assert WebhookEventType.OCR_STARTED.value == "ocr.started"
        assert WebhookEventType.OCR_COMPLETED.value == "ocr.completed"
        assert WebhookEventType.OCR_FAILED.value == "ocr.failed"

    def test_batch_events(self):
        """Batch Events sollten korrekt definiert sein."""
        assert WebhookEventType.BATCH_STARTED.value == "batch.started"
        assert WebhookEventType.BATCH_COMPLETED.value == "batch.completed"


class TestDeliveryStatus:
    """Tests für DeliveryStatus Enum."""

    def test_all_statuses_defined(self):
        """Alle Delivery-Status sollten definiert sein."""
        assert DeliveryStatus.PENDING.value == "pending"
        assert DeliveryStatus.SUCCESS.value == "success"
        assert DeliveryStatus.FAILED.value == "failed"
        assert DeliveryStatus.RETRYING.value == "retrying"
        assert DeliveryStatus.CIRCUIT_OPEN.value == "circuit_open"


class TestSingletons:
    """Tests für Singleton-Funktionen."""

    def test_get_webhook_dispatcher_singleton(self):
        """get_webhook_dispatcher sollte immer dieselbe Instanz zurückgeben."""
        d1 = get_webhook_dispatcher()
        d2 = get_webhook_dispatcher()
        assert d1 is d2

    def test_get_webhook_circuit_breaker_singleton(self):
        """get_webhook_circuit_breaker sollte immer dieselbe Instanz zurückgeben."""
        cb1 = get_webhook_circuit_breaker()
        cb2 = get_webhook_circuit_breaker()
        assert cb1 is cb2
