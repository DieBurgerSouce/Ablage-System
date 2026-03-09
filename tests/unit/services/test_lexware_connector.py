# -*- coding: utf-8 -*-
"""
Tests fuer LexwareConnector (ERP-Integration).

Testet:
- Verbindungsmanagement (connect/disconnect)
- Token-Validierung
- Webhook-Signatur-Verifizierung (Sicherheitskritisch)
- Webhook-Event-Parsing
- Request-Handling und Retry-Logik
"""

import hashlib
import hmac
import json
import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.services.erp.lexware_connector import (
    LexwareConnector,
    LexwareConnectionConfig,
    LexwareAPIVersion,
    LexwareEndpoint,
    LexwareWebhookEvent,
)
from app.services.erp.base_connector import ERPConnectionStatus, ERPEntity


@pytest.fixture
def config() -> LexwareConnectionConfig:
    """Erstellt eine Lexware-Testkonfiguration."""
    return LexwareConnectionConfig(
        client_id="test-client-id-for-test",
        client_secret="test-client-secret-for-test",
        organization_id="test-org-12345",
        webhook_secret="test-webhook-secret-for-verification",
        environment="sandbox",
    )


@pytest.fixture
def connector(config: LexwareConnectionConfig) -> LexwareConnector:
    """Erstellt einen LexwareConnector mit Testkonfiguration."""
    return LexwareConnector(config)


class TestLexwareConnectionConfig:
    """Tests fuer LexwareConnectionConfig."""

    def test_sandbox_url_wird_gesetzt(self):
        """Sandbox-Umgebung bekommt die richtige URL."""
        cfg = LexwareConnectionConfig(environment="sandbox")
        assert "sandbox" in cfg.url

    def test_production_url_wird_gesetzt(self):
        """Produktionsumgebung bekommt die richtige URL."""
        cfg = LexwareConnectionConfig(environment="production")
        assert "api.lexware.de" in cfg.url

    def test_standard_webhook_events(self):
        """Standard-Webhook-Events sind konfiguriert."""
        cfg = LexwareConnectionConfig()
        assert "contact.created" in cfg.subscribed_events
        assert "invoice.paid" in cfg.subscribed_events


class TestLexwareConnect:
    """Tests fuer connect() und disconnect()."""

    @pytest.mark.asyncio
    async def test_connect_mit_gueltigem_token(self, connector: LexwareConnector):
        """Verbindung mit existierendem gueltigem Token."""
        connector.config.access_token = "valid-test-token"

        mock_headers = {"Content-Type": "application/json"}
        mock_client = MagicMock()
        mock_client.headers = mock_headers

        with patch.object(connector, "_is_token_valid", return_value=True):
            with patch(
                "app.services.erp.lexware_connector.httpx.AsyncClient",
                return_value=mock_client,
            ):
                with patch(
                    "app.services.erp.lexware_connector.httpx.Timeout",
                    return_value=MagicMock(),
                ):
                    result = await connector.connect()

        assert result is True
        assert connector._status == ERPConnectionStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_connect_ohne_token_authentifiziert_neu(
        self, connector: LexwareConnector
    ):
        """Ohne Token wird neue Authentifizierung durchgefuehrt."""
        mock_headers = {"Content-Type": "application/json"}
        mock_client = MagicMock()
        mock_client.headers = mock_headers

        with patch(
            "app.services.erp.lexware_connector.httpx.AsyncClient",
            return_value=mock_client,
        ):
            with patch(
                "app.services.erp.lexware_connector.httpx.Timeout",
                return_value=MagicMock(),
            ):
                with patch.object(
                    connector, "_authenticate", new_callable=AsyncMock, return_value=True
                ) as mock_auth:
                    result = await connector.connect()

        assert result is True
        mock_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_fehler_setzt_error_status(
        self, connector: LexwareConnector
    ):
        """Verbindungsfehler setzt Status auf ERROR."""
        with patch(
            "app.services.erp.lexware_connector.httpx.AsyncClient",
            side_effect=Exception("Verbindungsfehler"),
        ):
            result = await connector.connect()

        assert result is False
        assert connector._status == ERPConnectionStatus.ERROR

    @pytest.mark.asyncio
    async def test_disconnect_schliesst_client(self, connector: LexwareConnector):
        """disconnect() schliesst den HTTP-Client."""
        mock_client = AsyncMock()
        connector._client = mock_client

        await connector.disconnect()

        mock_client.aclose.assert_called_once()
        assert connector._client is None
        assert connector._status == ERPConnectionStatus.DISCONNECTED


class TestTokenValidierung:
    """Tests fuer _is_token_valid()."""

    def test_kein_ablaufdatum_ist_ungueltig(self, connector: LexwareConnector):
        """Token ohne Ablaufdatum ist ungueltig."""
        connector.config.token_expires_at = None
        assert connector._is_token_valid() is False

    def test_abgelaufener_token_ist_ungueltig(self, connector: LexwareConnector):
        """Abgelaufener Token ist ungueltig."""
        connector.config.token_expires_at = datetime.now() - timedelta(hours=1)

        with patch("app.services.erp.lexware_connector.utc_now") as mock_utc:
            mock_utc.return_value = datetime.now()
            assert connector._is_token_valid() is False

    def test_gueltiger_token_mit_puffer(self, connector: LexwareConnector):
        """Token ist gueltig wenn mehr als 5 Minuten Restlaufzeit."""
        now = datetime.now()
        connector.config.token_expires_at = now + timedelta(hours=1)

        with patch("app.services.erp.lexware_connector.utc_now") as mock_utc:
            mock_utc.return_value = now
            assert connector._is_token_valid() is True


class TestWebhookSignaturVerifizierung:
    """Tests fuer verify_webhook_signature() - Sicherheitskritisch."""

    def test_gueltige_signatur_wird_akzeptiert(self, connector: LexwareConnector):
        """Korrekte HMAC-SHA256 Signatur wird akzeptiert."""
        payload = b'{"event": "invoice.paid", "id": "test-123"}'
        expected_sig = hmac.new(
            b"test-webhook-secret-for-verification",
            payload,
            hashlib.sha256,
        ).hexdigest()

        result = connector.verify_webhook_signature(
            payload, f"sha256={expected_sig}"
        )

        assert result is True

    def test_ungueltige_signatur_wird_abgelehnt(self, connector: LexwareConnector):
        """Falsche Signatur wird abgelehnt."""
        payload = b'{"event": "invoice.paid"}'

        result = connector.verify_webhook_signature(payload, "sha256=invalid-signature")

        assert result is False

    def test_manipulierter_payload_wird_abgelehnt(self, connector: LexwareConnector):
        """Manipulierter Payload wird erkannt und abgelehnt."""
        original_payload = b'{"amount": 100.00}'
        manipulated_payload = b'{"amount": 999999.99}'

        # Signatur fuer Original
        sig = hmac.new(
            b"test-webhook-secret-for-verification",
            original_payload,
            hashlib.sha256,
        ).hexdigest()

        result = connector.verify_webhook_signature(
            manipulated_payload, f"sha256={sig}"
        )

        assert result is False

    def test_kein_webhook_secret_konfiguriert(self):
        """Ohne konfiguriertes Secret schlaegt Verifizierung fehl."""
        config = LexwareConnectionConfig(webhook_secret="")
        conn = LexwareConnector(config)

        result = conn.verify_webhook_signature(b"payload", "sha256=abc")

        assert result is False

    def test_leerer_payload(self, connector: LexwareConnector):
        """Leerer Payload generiert gueltige Signatur."""
        payload = b""
        sig = hmac.new(
            b"test-webhook-secret-for-verification",
            payload,
            hashlib.sha256,
        ).hexdigest()

        result = connector.verify_webhook_signature(payload, f"sha256={sig}")

        assert result is True


class TestWebhookEventParsing:
    """Tests fuer LexwareWebhookEvent.from_payload()."""

    def test_parst_gueltigen_payload(self):
        """Gueltiger Webhook-Payload wird korrekt geparst."""
        payload = {
            "id": "evt-test-123",
            "event": "invoice.paid",
            "resource_type": "invoice",
            "resource_id": "inv-456",
            "organization_id": "org-789",
            "timestamp": "2026-01-15T10:00:00+00:00",
            "data": {"amount": 100.0},
        }

        event = LexwareWebhookEvent.from_payload(payload)

        assert event.id == "evt-test-123"
        assert event.event_type == "invoice.paid"
        assert event.resource_id == "inv-456"
        assert event.data["amount"] == 100.0

    def test_parst_unvollstaendigen_payload(self):
        """Unvollstaendiger Payload wird mit Defaults geparst."""
        event = LexwareWebhookEvent.from_payload({})

        assert event.id == ""
        assert event.event_type == ""
        assert event.data == {}

    def test_parst_ungueltigen_timestamp(self):
        """Ungueltiger Timestamp wird mit aktuellem Zeitpunkt ersetzt."""
        payload = {
            "id": "test",
            "event": "test.event",
            "resource_type": "test",
            "resource_id": "123",
            "organization_id": "org",
            "timestamp": "not-a-date",
        }

        event = LexwareWebhookEvent.from_payload(payload)

        assert event.timestamp is not None


class TestBaseUrl:
    """Tests fuer die base_url Property."""

    def test_base_url_enthalt_api_version(self, connector: LexwareConnector):
        """Base-URL enthaelt die konfigurierte API-Version."""
        assert "/v1" in connector.base_url

    def test_v2_api_version(self):
        """V2 API-Version wird korrekt in URL eingebaut."""
        config = LexwareConnectionConfig(api_version=LexwareAPIVersion.V2)
        conn = LexwareConnector(config)

        assert "/v2" in conn.base_url
