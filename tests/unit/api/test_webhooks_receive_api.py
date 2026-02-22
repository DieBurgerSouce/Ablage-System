# -*- coding: utf-8 -*-
"""
Unit Tests fuer Inbound Webhook Receive API.

Testet alle drei Endpunkte des Inbound-Webhook-Routers:
  POST /api/v1/webhooks/receive/{provider}/{config_id}  - Webhook empfangen
  GET  /api/v1/webhooks/receive/{provider}/events       - Events auflisten
  POST /api/v1/webhooks/receive/{provider}/events/{event_id}/retry - Retry

Alle externen Abhaengigkeiten werden vollstaendig gemockt.
Kein echter Datenbankzugriff, keine echten Celery-Tasks.
"""

import hashlib
import hmac
import json
import sys
import types
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Celery-Task-Modul vorab mocken (lazy import im API-Code).
# app.api.v1.webhooks_receive importiert process_inbound_webhook beim
# Ausfuehren des retry-Endpunkts. Da das echte Modul (psutil, torch, ...)
# nicht verfuegbar ist, wird es hier in sys.modules vorregistriert.
# ---------------------------------------------------------------------------
_mock_task_module = types.ModuleType("app.workers.tasks.webhook_inbound_tasks")
_mock_process_inbound_webhook = MagicMock()
_mock_task_module.process_inbound_webhook = _mock_process_inbound_webhook

for _mod in ("app.workers", "app.workers.tasks", "app.workers.tasks.webhook_inbound_tasks"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
sys.modules["app.workers.tasks.webhook_inbound_tasks"] = _mock_task_module

# Testmarkierungen fuer das gesamte Modul
pytestmark = [pytest.mark.unit, pytest.mark.api]

# Basis-Pfad aller getesteten Endpunkte
BASE = "/api/v1/webhooks/receive"

# Gueltiger DHL-Provider-Wert gemaess InboundWebhookProvider-Enum
PROVIDER = "dhl"


# =============================================================================
# Hilfsfunktionen
# =============================================================================


def _make_timestamp() -> str:
    """Erzeugt einen aktuellen Unix-Timestamp als String."""
    return str(int(datetime.now(timezone.utc).timestamp()))


def _make_signature(payload: bytes, timestamp: str, secret: str) -> str:
    """Erzeugt eine gueltige HMAC-SHA256 Signatur im Webhook-Format."""
    message = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _valid_payload(
    event_id: str = "evt-test-001",
    event_type: str = "shipment.delivered",
    action: str = "status_change",
    data: Optional[dict] = None,
) -> dict:
    """Erzeugt einen gueltigen Webhook-Payload als Dictionary."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "action": action,
        "data": data or {"tracking_number": "TRACK-42"},
    }


def _mock_event_db_row(
    provider: str = "dhl",
    status: str = "pending",
    event_id_str: Optional[str] = None,
) -> Mock:
    """Erzeugt eine Mock-InboundWebhookEvent-DB-Zeile."""
    row = Mock()
    row.id = uuid4()
    row.provider = provider
    row.event_id = event_id_str or f"evt-{uuid4().hex[:8]}"
    row.event_type = "shipment.delivered"
    row.action = "status_change"
    row.status = status
    row.external_ref = "TRACK-42"
    row.internal_event_type = None
    row.received_at = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
    row.processed_at = None
    row.attempts = 0
    row.error_message = None
    row.payload_preview = {"tracking_number": "TRACK-42"}
    return row


def _patch_get_db(mock_db: AsyncMock):
    """Patcht die get_db-Dependency fuer den Webhook-Router."""
    return patch("app.api.v1.webhooks_receive.get_db", return_value=mock_db)


# =============================================================================
# TestReceiveWebhookEndpoint
# =============================================================================


class TestReceiveWebhookEndpoint:
    """Tests fuer POST /{provider}/{config_id} - Webhook empfangen."""

    @pytest.mark.asyncio
    async def test_unbekannter_provider_liefert_400(self, async_client) -> None:
        """Ein nicht registrierter Provider muss HTTP 400 zurueckgeben.

        Das Provider-Enum akzeptiert nur datev, dhl, dpd, ups, gls.
        """
        config_id = uuid4()
        # 'fedex' ist nicht im InboundWebhookProvider-Enum
        response = await async_client.post(
            f"{BASE}/fedex/{config_id}",
            content=b'{"event_id":"e1","event_type":"t","action":"create","data":{}}',
            headers={"Content-Type": "application/json"},
        )
        # FastAPI gibt 422 fuer ungueltige Enum-Werte im Path zurück
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_datev_provider_wird_erkannt(self, async_client) -> None:
        """DATEV als Provider muss erkannt und an den Service weitergeleitet werden."""
        config_id = uuid4()
        payload_dict = _valid_payload(action="create")
        payload_bytes = json.dumps(payload_dict).encode()
        timestamp = _make_timestamp()
        secret = "datev-secret"
        sig = _make_signature(payload_bytes, timestamp, secret)

        mock_response = Mock()
        mock_response.success = True
        mock_response.event_id = payload_dict["event_id"]
        mock_response.message = "Webhook empfangen"
        mock_response.task_id = "task-datev-1"

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(return_value=mock_response)

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/datev/{config_id}",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-DATEV-Webhook-Signature": sig,
                        "X-DATEV-Webhook-Timestamp": timestamp,
                        "X-DATEV-Webhook-Id": "webhook-id-001",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["event_id"] == payload_dict["event_id"]

    @pytest.mark.asyncio
    async def test_dhl_provider_extrahiert_korrekte_signatur_header(self, async_client) -> None:
        """DHL-spezifische Header muessen korrekt an den Service weitergeleitet werden."""
        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload()).encode()
        timestamp = _make_timestamp()
        sig = "test-dhl-signature"

        mock_response = Mock()
        mock_response.success = True
        mock_response.event_id = "evt-test-001"
        mock_response.message = "OK"
        mock_response.task_id = "celery-1"

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(return_value=mock_response)

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/{config_id}",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-DHL-Signature": sig,
                        "X-DHL-Timestamp": timestamp,
                        "X-DHL-Webhook-Id": "wh-dhl-999",
                    },
                )

        assert response.status_code == 200
        # Pruefe dass process_webhook mit den richtigen Headerwerten aufgerufen wurde
        call_kwargs = instance.process_webhook.call_args.kwargs
        assert call_kwargs["signature"] == sig
        assert call_kwargs["timestamp"] == timestamp
        assert call_kwargs["webhook_id"] == "wh-dhl-999"

    @pytest.mark.asyncio
    async def test_service_raise_401_wird_weitergeleitet(self, async_client) -> None:
        """HTTPException 401 vom Service muss unveraendert als 401 zurueckkommen."""
        from fastapi import HTTPException

        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload()).encode()

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(
                side_effect=HTTPException(status_code=401, detail="Ungueltige Signatur")
            )

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/{config_id}",
                    content=payload_bytes,
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_service_raise_404_wird_weitergeleitet(self, async_client) -> None:
        """HTTPException 404 vom Service muss unveraendert als 404 zurueckkommen."""
        from fastapi import HTTPException

        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload()).encode()

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(
                side_effect=HTTPException(status_code=404, detail="Konfiguration nicht gefunden")
            )

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/{config_id}",
                    content=payload_bytes,
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_service_raise_413_wird_weitergeleitet(self, async_client) -> None:
        """HTTPException 413 vom Service muss unveraendert als 413 zurueckkommen."""
        from fastapi import HTTPException

        config_id = uuid4()
        # Zu grossen Payload simulieren ueber Service-Exception
        payload_bytes = json.dumps(_valid_payload()).encode()

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(
                side_effect=HTTPException(status_code=413, detail="Payload zu gross")
            )

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/{config_id}",
                    content=payload_bytes,
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_response_schema_enthält_pflichtfelder(self, async_client) -> None:
        """Die Antwort muss success, event_id und message enthalten."""
        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload(event_id="evt-schema-check")).encode()

        mock_response = Mock()
        mock_response.success = True
        mock_response.event_id = "evt-schema-check"
        mock_response.message = "Verarbeitet"
        mock_response.task_id = None

        with patch(
            "app.api.v1.webhooks_receive.InboundWebhookService"
        ) as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(return_value=mock_response)

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/{config_id}",
                    content=payload_bytes,
                    headers={"Content-Type": "application/json"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "event_id" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_gueltige_uuid_fuer_config_id_erforderlich(self, async_client) -> None:
        """Eine nicht-UUID als config_id muss von FastAPI abgelehnt werden (422)."""
        response = await async_client.post(
            f"{BASE}/{PROVIDER}/kein-gueltiger-uuid",
            content=b'{}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


# =============================================================================
# TestListInboundEvents
# =============================================================================


class TestListInboundEvents:
    """Tests fuer GET /{provider}/events - Events auflisten."""

    @pytest.mark.asyncio
    async def test_events_auflisten_gibt_liste_zurueck(self, async_client) -> None:
        """Event-Liste muss events-Array und total enthalten."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="success")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [event_row]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(f"{BASE}/{PROVIDER}/events")

        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert data["total"] == 1
        assert len(data["events"]) == 1

    @pytest.mark.asyncio
    async def test_leere_event_liste(self, async_client) -> None:
        """Keine Events muessen eine leere Liste mit total=0 ergeben."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(f"{BASE}/{PROVIDER}/events")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["events"] == []

    @pytest.mark.asyncio
    async def test_status_filter_wird_angewendet(self, async_client) -> None:
        """Der status-Query-Parameter muss an die DB-Query weitergegeben werden."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(
                f"{BASE}/{PROVIDER}/events?status=failed"
            )

        assert response.status_code == 200
        # DB.execute muss aufgerufen worden sein (Filter wird intern angewendet)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_limit_parameter_wird_akzeptiert(self, async_client) -> None:
        """Gueltiger limit-Parameter muss ohne Fehler akzeptiert werden."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(
                f"{BASE}/{PROVIDER}/events?limit=10"
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_limit_untergrenze_verletzung_liefert_422(self, async_client) -> None:
        """limit=0 (unter Minimum 1) muss 422 ergeben."""
        mock_db = AsyncMock()
        with _patch_get_db(mock_db):
            response = await async_client.get(
                f"{BASE}/{PROVIDER}/events?limit=0"
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_obergrenze_verletzung_liefert_422(self, async_client) -> None:
        """limit=501 (ueber Maximum 500) muss 422 ergeben."""
        mock_db = AsyncMock()
        with _patch_get_db(mock_db):
            response = await async_client.get(
                f"{BASE}/{PROVIDER}/events?limit=501"
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_event_summary_felder_vorhanden(self, async_client) -> None:
        """Jedes Event-Objekt muss die erwarteten Felder enthalten."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="success")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [event_row]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(f"{BASE}/{PROVIDER}/events")

        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 1
        event = events[0]
        # Pflichtfelder gemaess InboundWebhookEventSummary
        for field in ("id", "provider", "event_id", "event_type", "action", "status"):
            assert field in event, f"Pflichtfeld '{field}' fehlt im Event-Summary"

    @pytest.mark.asyncio
    async def test_mehrere_events_korrekte_anzahl(self, async_client) -> None:
        """Mehrere DB-Zeilen muessen korrekt zaehlt werden."""
        rows = [_mock_event_db_row(provider=PROVIDER) for _ in range(5)]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rows

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.get(f"{BASE}/{PROVIDER}/events")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["events"]) == 5

    @pytest.mark.asyncio
    async def test_ungueltige_provider_liefert_422(self, async_client) -> None:
        """Ein ungueltigier Provider-Wert muss 422 ausloesen."""
        mock_db = AsyncMock()
        with _patch_get_db(mock_db):
            response = await async_client.get(f"{BASE}/unbekannt/events")
        assert response.status_code == 422


# =============================================================================
# TestRetryInboundEvent
# =============================================================================


class TestRetryInboundEvent:
    """Tests fuer POST /{provider}/events/{event_id}/retry - Event erneut verarbeiten."""

    @pytest.mark.asyncio
    async def test_event_nicht_gefunden_liefert_404(self, async_client) -> None:
        """Event-ID nicht in DB muss HTTP 404 ergeben."""
        event_uuid = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.post(
                f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_bereits_erfolgreiches_event_liefert_400(self, async_client) -> None:
        """Event mit Status SUCCESS darf nicht erneut eingereiht werden (HTTP 400)."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="success")
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            response = await async_client.post(
                f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_fehlgeschlagenes_event_wird_eingereiht(self, async_client) -> None:
        """Event mit Status FAILED muss erfolgreich erneut eingereiht werden."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="failed")
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_task = Mock()
        mock_task.id = "retry-task-id-999"

        with _patch_get_db(mock_db):
            with patch(
                "app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook"
            ) as celery_mock:
                celery_mock.delay.return_value = mock_task
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "retry-task-id-999"
        assert "retry" in data["message"].lower() or "eingereiht" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_pending_event_kann_retried_werden(self, async_client) -> None:
        """Event mit Status PENDING muss eingereiht werden koennen (kein 400)."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="pending")
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_task = Mock()
        mock_task.id = "task-pending-retry"

        with _patch_get_db(mock_db):
            with patch(
                "app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook"
            ) as celery_mock:
                celery_mock.delay.return_value = mock_task
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
                )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_response_enthaelt_event_id(self, async_client) -> None:
        """Retry-Response muss die event_id der DB-Zeile enthalten."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="failed")
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            with patch(
                "app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook"
            ) as celery_mock:
                celery_mock.delay.return_value = Mock(id="task-x")
                response = await async_client.post(
                    f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
                )

        assert response.status_code == 200
        data = response.json()
        # event_id im Response muss der UUID der angeforderten Ressource entsprechen
        assert data["event_id"] == str(event_uuid)

    @pytest.mark.asyncio
    async def test_celery_delay_wird_mit_korrekten_parametern_aufgerufen(
        self, async_client
    ) -> None:
        """process_inbound_webhook.delay muss mit den Event-Feldern aufgerufen werden."""
        event_row = _mock_event_db_row(provider=PROVIDER, status="failed")
        event_row.internal_event_type = "SHIPMENT_DELIVERED"
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            with patch(
                "app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook"
            ) as celery_mock:
                celery_mock.delay.return_value = Mock(id="task-y")
                await async_client.post(
                    f"{BASE}/{PROVIDER}/events/{event_uuid}/retry"
                )

        celery_mock.delay.assert_called_once()
        call_kwargs = celery_mock.delay.call_args.kwargs
        assert call_kwargs["event_db_id"] == str(event_uuid)
        assert call_kwargs["provider"] == PROVIDER
        assert call_kwargs["internal_event_type"] == "SHIPMENT_DELIVERED"

    @pytest.mark.asyncio
    async def test_ungueltige_event_uuid_liefert_422(self, async_client) -> None:
        """Eine ungueltige UUID als event_id muss 422 ergeben."""
        mock_db = AsyncMock()
        with _patch_get_db(mock_db):
            response = await async_client.post(
                f"{BASE}/{PROVIDER}/events/kein-uuid/retry"
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_datev_retry_prueft_provider_und_event_id(self, async_client) -> None:
        """Beim DATEV-Retry muss sowohl provider als auch event_id aus der DB abgeglichen werden."""
        event_row = _mock_event_db_row(provider="datev", status="failed")
        event_uuid = event_row.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = event_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with _patch_get_db(mock_db):
            with patch(
                "app.workers.tasks.webhook_inbound_tasks.process_inbound_webhook"
            ) as celery_mock:
                celery_mock.delay.return_value = Mock(id="datev-retry-task")
                response = await async_client.post(
                    f"{BASE}/datev/events/{event_uuid}/retry"
                )

        assert response.status_code == 200


# =============================================================================
# Tests fuer Provider-Header-Extraktion
# =============================================================================


class TestProviderHeaderExtraktion:
    """Tests fuer die provider-spezifische Header-Extraktion im receive_webhook-Endpoint."""

    @pytest.mark.asyncio
    async def test_dpd_provider_header_werden_korrekt_extrahiert(
        self, async_client
    ) -> None:
        """DPD-spezifische Header (X-DPD-Signature etc.) muessen korrekt weitergegeben werden."""
        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload(action="create")).encode()
        timestamp = _make_timestamp()

        mock_response = Mock()
        mock_response.success = True
        mock_response.event_id = "evt-dpd"
        mock_response.message = "DPD OK"
        mock_response.task_id = "t1"

        with patch("app.api.v1.webhooks_receive.InboundWebhookService") as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(return_value=mock_response)

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                await async_client.post(
                    f"{BASE}/dpd/{config_id}",
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-DPD-Signature": "dpd-sig",
                        "X-DPD-Timestamp": timestamp,
                        "X-DPD-Webhook-Id": "dpd-wh-id",
                    },
                )

        call_kwargs = instance.process_webhook.call_args.kwargs
        assert call_kwargs["provider"] == "dpd"
        assert call_kwargs["signature"] == "dpd-sig"
        assert call_kwargs["timestamp"] == timestamp
        assert call_kwargs["webhook_id"] == "dpd-wh-id"

    @pytest.mark.asyncio
    async def test_fehlende_header_werden_als_none_weitergegeben(
        self, async_client
    ) -> None:
        """Fehlende optionale Header muessen als None an den Service weitergegeben werden."""
        config_id = uuid4()
        payload_bytes = json.dumps(_valid_payload(action="update")).encode()

        mock_response = Mock()
        mock_response.success = True
        mock_response.event_id = "evt-missing-header"
        mock_response.message = "OK"
        mock_response.task_id = None

        with patch("app.api.v1.webhooks_receive.InboundWebhookService") as MockService:
            instance = MockService.return_value
            instance.process_webhook = AsyncMock(return_value=mock_response)

            mock_db = AsyncMock()
            with _patch_get_db(mock_db):
                # Keine Signatur-Header werden gesendet
                await async_client.post(
                    f"{BASE}/ups/{config_id}",
                    content=payload_bytes,
                    headers={"Content-Type": "application/json"},
                )

        call_kwargs = instance.process_webhook.call_args.kwargs
        assert call_kwargs["signature"] is None
        assert call_kwargs["timestamp"] is None
        assert call_kwargs["webhook_id"] is None
