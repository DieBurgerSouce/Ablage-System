# -*- coding: utf-8 -*-
"""
Unit Tests fuer Outbound Webhook Event Platform API.

Testet alle 11 Outbound-Webhook-Endpoints:
- GET /webhooks/outbound/endpoints - Endpoints auflisten
- POST /webhooks/outbound/endpoints - Endpoint registrieren
- PUT /webhooks/outbound/endpoints/{id} - Endpoint aktualisieren
- DELETE /webhooks/outbound/endpoints/{id} - Endpoint deaktivieren
- POST /webhooks/outbound/endpoints/{id}/test - Test-Zustellung
- GET /webhooks/outbound/endpoints/{id}/deliveries - Zustellungshistorie
- GET /webhooks/outbound/dlq - Dead Letter Queue
- POST /webhooks/outbound/dlq/{id}/retry - DLQ-Retry
- GET /webhooks/outbound/events - Event-Journal
- POST /webhooks/outbound/events/{id}/replay - Einzelner Replay
- POST /webhooks/outbound/events/replay/bulk - Bulk-Replay

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]

# Base path for all outbound webhook endpoints
BASE = "/api/v1/webhooks/outbound"


def _mock_endpoint(
    endpoint_id=None,
    company_id=None,
    url="https://example.com/hook",
    is_active=True,
    event_types=None,
):
    """Erzeugt ein Mock-WebhookEndpoint-Objekt."""
    ep = Mock()
    ep.id = endpoint_id or uuid4()
    ep.company_id = company_id or uuid4()
    ep.url = url
    ep.description = "Test-Endpoint"
    ep.event_types = event_types or ["document.created"]
    ep.is_active = is_active
    ep.headers = None
    ep.retry_policy = {"max_retries": 3, "backoff_factor": 2, "timeout_seconds": 30}
    ep.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ep.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ep


def _mock_delivery(endpoint_id=None, company_id=None, status="delivered"):
    """Erzeugt ein Mock-WebhookDelivery-Objekt."""
    d = Mock()
    d.id = uuid4()
    d.endpoint_id = endpoint_id or uuid4()
    d.company_id = company_id or uuid4()
    d.event_type = "document.created"
    d.event_id = uuid4()
    d.status = status
    d.attempts = 1
    d.max_attempts = 3
    d.response_status_code = 200
    d.response_body = None
    d.last_attempt_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d.next_retry_at = None
    d.delivered_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return d


def _mock_event_log(company_id=None):
    """Erzeugt ein Mock-WebhookEventLog-Objekt."""
    e = Mock()
    e.id = uuid4()
    e.company_id = company_id or uuid4()
    e.event_type = "document.created"
    e.source_table = "documents"
    e.source_id = uuid4()
    e.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return e


def _patch_deps():
    """Patcht require_company, get_db und get_webhook_service fuer Outbound-API."""
    company = Mock()
    company.id = uuid4()

    mock_db = AsyncMock()
    mock_service = Mock()

    p_company = patch(
        "app.api.v1.webhooks_outbound.require_company", return_value=company
    )
    p_db = patch(
        "app.api.v1.webhooks_outbound.get_db", return_value=mock_db
    )
    p_service = patch(
        "app.api.v1.webhooks_outbound.get_webhook_service", return_value=mock_service
    )

    return p_company, p_db, p_service, company, mock_db, mock_service


# =============================================================================
# TestListEndpoints
# =============================================================================


class TestListEndpoints:
    """Tests fuer GET /webhooks/outbound/endpoints."""

    @pytest.mark.asyncio
    async def test_list_success(self, async_client):
        """Endpoints erfolgreich auflisten."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        ep = _mock_endpoint(company_id=company.id)
        mock_service.list_endpoints = AsyncMock(return_value=[ep])

        with p_company, p_db, p_service:
            response = await async_client.get(f"{BASE}/endpoints")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["has_more"] is False
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_with_inactive_filter(self, async_client):
        """Endpoints mit include_inactive auflisten."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.list_endpoints = AsyncMock(return_value=[])

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/endpoints?include_inactive=true"
            )

        assert response.status_code == 200
        mock_service.list_endpoints.assert_called_once()
        call_kwargs = mock_service.list_endpoints.call_args.kwargs
        assert call_kwargs["include_inactive"] is True

    @pytest.mark.asyncio
    async def test_list_pagination(self, async_client):
        """Pagination mit page=2, per_page=1."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        eps = [_mock_endpoint(company_id=company.id) for _ in range(3)]
        mock_service.list_endpoints = AsyncMock(return_value=eps)

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/endpoints?page=2&per_page=1"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["per_page"] == 1
        assert data["total"] == 3
        assert data["has_more"] is True
        assert len(data["items"]) == 1


# =============================================================================
# TestRegisterEndpoint
# =============================================================================


class TestRegisterEndpoint:
    """Tests fuer POST /webhooks/outbound/endpoints."""

    @pytest.mark.asyncio
    async def test_create_success(self, async_client):
        """Endpoint erfolgreich registrieren mit Secret in Response."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        ep = _mock_endpoint(company_id=company.id)
        mock_service.register_endpoint = AsyncMock(return_value=ep)

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/endpoints",
                json={
                    "url": "https://example.com/hook",
                    "event_types": ["document.created"],
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "secret" in data
        assert data["secret"].startswith("whsec_")

    @pytest.mark.asyncio
    async def test_create_secret_format(self, async_client):
        """Secret hat korrektes whsec_-Format und ist lang genug."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        ep = _mock_endpoint(company_id=company.id)
        mock_service.register_endpoint = AsyncMock(return_value=ep)

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/endpoints",
                json={"url": "https://example.com/hook"},
            )

        secret = response.json()["secret"]
        assert secret.startswith("whsec_")
        assert len(secret) > 40

    @pytest.mark.asyncio
    async def test_create_validates_blocked_headers(self, async_client):
        """Blockierte Header (authorization) fuehren zu 422."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/endpoints",
                json={
                    "url": "https://example.com/hook",
                    "headers": {"Authorization": "Bearer xyz"},
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_validates_empty_event_type(self, async_client):
        """Leerer Event-Typ fuehrt zu 422."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/endpoints",
                json={
                    "url": "https://example.com/hook",
                    "event_types": [""],
                },
            )

        assert response.status_code == 422


# =============================================================================
# TestUpdateEndpoint
# =============================================================================


class TestUpdateEndpoint:
    """Tests fuer PUT /webhooks/outbound/endpoints/{id}."""

    @pytest.mark.asyncio
    async def test_update_success(self, async_client):
        """Endpoint URL und Beschreibung aktualisieren."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        ep = _mock_endpoint(company_id=company.id, url="https://new.example.com/hook")
        mock_service.update_endpoint = AsyncMock(return_value=ep)
        endpoint_id = uuid4()

        with p_company, p_db, p_service:
            response = await async_client.put(
                f"{BASE}/endpoints/{endpoint_id}",
                json={
                    "url": "https://new.example.com/hook",
                    "description": "Neue Beschreibung",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == "https://new.example.com/hook"
        # Secret darf NICHT in der Update-Response sein
        assert "secret" not in data

    @pytest.mark.asyncio
    async def test_update_not_found(self, async_client):
        """ValueError vom Service fuehrt zu 404."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.update_endpoint = AsyncMock(
            side_effect=ValueError("Endpoint nicht gefunden")
        )

        with p_company, p_db, p_service:
            response = await async_client.put(
                f"{BASE}/endpoints/{uuid4()}",
                json={"url": "https://example.com/hook"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_is_active_toggle(self, async_client):
        """Endpoint deaktivieren via is_active=false."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        ep = _mock_endpoint(company_id=company.id, is_active=False)
        mock_service.update_endpoint = AsyncMock(return_value=ep)

        with p_company, p_db, p_service:
            response = await async_client.put(
                f"{BASE}/endpoints/{uuid4()}",
                json={"is_active": False},
            )

        assert response.status_code == 200
        assert response.json()["is_active"] is False


# =============================================================================
# TestDeleteEndpoint
# =============================================================================


class TestDeleteEndpoint:
    """Tests fuer DELETE /webhooks/outbound/endpoints/{id}."""

    @pytest.mark.asyncio
    async def test_delete_success(self, async_client):
        """Endpoint erfolgreich deaktivieren (Soft-Delete)."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.delete_endpoint = AsyncMock(return_value=None)

        with p_company, p_db, p_service:
            response = await async_client.delete(
                f"{BASE}/endpoints/{uuid4()}"
            )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_not_found(self, async_client):
        """Nicht existierender Endpoint fuehrt zu 404."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.delete_endpoint = AsyncMock(
            side_effect=ValueError("Endpoint nicht gefunden")
        )

        with p_company, p_db, p_service:
            response = await async_client.delete(
                f"{BASE}/endpoints/{uuid4()}"
            )

        assert response.status_code == 404


# =============================================================================
# TestTestEndpoint
# =============================================================================


class TestTestEndpoint:
    """Tests fuer POST /webhooks/outbound/endpoints/{id}/test."""

    @pytest.mark.asyncio
    async def test_test_success(self, async_client):
        """Test-Zustellung erfolgreich dispatchen."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        endpoint_id = uuid4()
        ep = _mock_endpoint(endpoint_id=endpoint_id, company_id=company.id)
        mock_service.list_endpoints = AsyncMock(return_value=[ep])

        mock_delivery = Mock()
        mock_delivery.id = uuid4()

        mock_db.add = Mock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.commit = AsyncMock()

        with p_company, p_db, p_service, patch(
            "app.api.v1.webhooks_outbound.WebhookDelivery", return_value=mock_delivery
        ), patch(
            "app.api.v1.webhooks_outbound.deliver_webhook"
        ) as mock_task:
            mock_task.delay = Mock()
            response = await async_client.post(
                f"{BASE}/endpoints/{endpoint_id}/test",
                json={"event_type": "webhook.test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dispatched"

    @pytest.mark.asyncio
    async def test_endpoint_not_found(self, async_client):
        """Test fuer nicht existierenden Endpoint gibt 404."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.list_endpoints = AsyncMock(return_value=[])

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/endpoints/{uuid4()}/test",
                json={"event_type": "webhook.test"},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_custom_payload(self, async_client):
        """Test-Zustellung mit eigenem Payload."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        endpoint_id = uuid4()
        ep = _mock_endpoint(endpoint_id=endpoint_id, company_id=company.id)
        mock_service.list_endpoints = AsyncMock(return_value=[ep])

        mock_delivery = Mock()
        mock_delivery.id = uuid4()

        mock_db.add = Mock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.commit = AsyncMock()

        with p_company, p_db, p_service, patch(
            "app.api.v1.webhooks_outbound.WebhookDelivery", return_value=mock_delivery
        ), patch(
            "app.api.v1.webhooks_outbound.deliver_webhook"
        ) as mock_task:
            mock_task.delay = Mock()
            response = await async_client.post(
                f"{BASE}/endpoints/{endpoint_id}/test",
                json={
                    "event_type": "webhook.test",
                    "payload": {"custom": "data", "test": True},
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "dispatched"


# =============================================================================
# TestDeliveryHistory
# =============================================================================


class TestDeliveryHistory:
    """Tests fuer GET /webhooks/outbound/endpoints/{id}/deliveries."""

    @pytest.mark.asyncio
    async def test_history_success(self, async_client):
        """Zustellungshistorie erfolgreich abrufen."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        d = _mock_delivery(company_id=company.id)
        mock_service.get_delivery_history = AsyncMock(return_value=[d])

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/endpoints/{uuid4()}/deliveries"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_history_not_found(self, async_client):
        """ValueError vom Service fuehrt zu 404."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.get_delivery_history = AsyncMock(
            side_effect=ValueError("Endpoint nicht gefunden")
        )

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/endpoints/{uuid4()}/deliveries"
            )

        assert response.status_code == 404


# =============================================================================
# TestDLQ
# =============================================================================


class TestDLQ:
    """Tests fuer GET /webhooks/outbound/dlq."""

    @pytest.mark.asyncio
    async def test_dlq_list_success(self, async_client):
        """DLQ-Eintraege erfolgreich auflisten."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        d = _mock_delivery(company_id=company.id, status="failed")
        mock_service.get_dlq_items = AsyncMock(return_value=[d])

        with p_company, p_db, p_service:
            response = await async_client.get(f"{BASE}/dlq")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_dlq_list_pagination(self, async_client):
        """DLQ-Pagination mit page und per_page."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.get_dlq_items = AsyncMock(return_value=[])

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/dlq?page=2&per_page=5"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["per_page"] == 5


# =============================================================================
# TestRetryDLQ
# =============================================================================


class TestRetryDLQ:
    """Tests fuer POST /webhooks/outbound/dlq/{id}/retry."""

    @pytest.mark.asyncio
    async def test_retry_success(self, async_client):
        """DLQ-Eintrag erfolgreich wiederholen."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        d = _mock_delivery(company_id=company.id, status="pending")
        mock_service.retry_delivery = AsyncMock(return_value=d)

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/dlq/{uuid4()}/retry"
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "status" in data

    @pytest.mark.asyncio
    async def test_retry_invalid(self, async_client):
        """Ungueltiger Retry fuehrt zu 400."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.retry_delivery = AsyncMock(
            side_effect=ValueError("Zustellung kann nicht wiederholt werden")
        )

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/dlq/{uuid4()}/retry"
            )

        assert response.status_code == 400


# =============================================================================
# TestEventLog
# =============================================================================


class TestEventLog:
    """Tests fuer GET /webhooks/outbound/events."""

    @pytest.mark.asyncio
    async def test_events_list(self, async_client):
        """Event-Journal erfolgreich abrufen."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        e = _mock_event_log(company_id=company.id)
        mock_service.get_event_log = AsyncMock(return_value=[e])

        with p_company, p_db, p_service:
            response = await async_client.get(f"{BASE}/events")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_events_filter_type(self, async_client):
        """Event-Journal nach Event-Typ filtern."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.get_event_log = AsyncMock(return_value=[])

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/events?event_type=document.created"
            )

        assert response.status_code == 200
        call_kwargs = mock_service.get_event_log.call_args.kwargs
        assert call_kwargs["event_type"] == "document.created"

    @pytest.mark.asyncio
    async def test_events_filter_date(self, async_client):
        """Event-Journal nach Datum filtern."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.get_event_log = AsyncMock(return_value=[])

        with p_company, p_db, p_service:
            response = await async_client.get(
                f"{BASE}/events"
                "?from_date=2026-01-01T00:00:00Z"
                "&to_date=2026-01-31T23:59:59Z"
            )

        assert response.status_code == 200
        call_kwargs = mock_service.get_event_log.call_args.kwargs
        assert call_kwargs["from_date"] is not None
        assert call_kwargs["to_date"] is not None


# =============================================================================
# TestReplaySingleEvent
# =============================================================================


class TestReplaySingleEvent:
    """Tests fuer POST /webhooks/outbound/events/{id}/replay."""

    @pytest.mark.asyncio
    async def test_replay_success(self, async_client):
        """Einzelnen Event erfolgreich replayan."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.replay_event = AsyncMock(return_value=3)

        event_id = uuid4()
        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/events/{event_id}/replay"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["dispatched"] == 3
        assert str(event_id) in data["event_id"]

    @pytest.mark.asyncio
    async def test_replay_not_found(self, async_client):
        """Nicht existierender Event fuehrt zu 404."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.replay_event = AsyncMock(
            side_effect=ValueError("Event nicht gefunden")
        )

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/events/{uuid4()}/replay"
            )

        assert response.status_code == 404


# =============================================================================
# TestBulkReplay
# =============================================================================


class TestBulkReplay:
    """Tests fuer POST /webhooks/outbound/events/replay/bulk."""

    @pytest.mark.asyncio
    async def test_bulk_success(self, async_client):
        """Bulk-Replay erfolgreich starten."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.replay_events = AsyncMock(return_value=15)

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/events/replay/bulk",
                json={
                    "event_type": "document.created",
                    "from_date": "2026-01-01T00:00:00Z",
                    "to_date": "2026-01-31T23:59:59Z",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_dispatched"] == 15
        assert data["event_type"] == "document.created"

    @pytest.mark.asyncio
    async def test_bulk_invalid_dates(self, async_client):
        """to_date vor from_date fuehrt zu 422."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/events/replay/bulk",
                json={
                    "event_type": "document.created",
                    "from_date": "2026-02-01T00:00:00Z",
                    "to_date": "2026-01-01T00:00:00Z",
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_service_error(self, async_client):
        """Service-Fehler fuehrt zu 500."""
        p_company, p_db, p_service, company, mock_db, mock_service = _patch_deps()
        mock_service.replay_events = AsyncMock(
            side_effect=RuntimeError("DB-Verbindung fehlgeschlagen")
        )

        with p_company, p_db, p_service:
            response = await async_client.post(
                f"{BASE}/events/replay/bulk",
                json={
                    "event_type": "document.created",
                    "from_date": "2026-01-01T00:00:00Z",
                    "to_date": "2026-01-31T23:59:59Z",
                },
            )

        assert response.status_code == 500


# =============================================================================
# Pydantic Schema Validation Tests
# =============================================================================


class TestSchemaValidation:
    """Tests fuer Pydantic-Schema-Validierung."""

    def _import_schemas(self):
        """Importiert Outbound-Schemas; ueberspringt bei Import-Fehler."""
        try:
            from app.api.v1.webhooks_outbound import (
                BulkReplayRequest,
                RetryPolicySchema,
                WebhookEndpointCreateRequest,
            )
            return RetryPolicySchema, BulkReplayRequest, WebhookEndpointCreateRequest
        except Exception:
            pytest.skip("Outbound-Schemas nicht importierbar (SQLAlchemy-Konflikt)")

    def test_retry_policy_max_retries_limit(self):
        """max_retries > 10 fuehrt zu Validierungsfehler."""
        from pydantic import ValidationError

        RetryPolicySchema, _, _ = self._import_schemas()
        with pytest.raises(ValidationError):
            RetryPolicySchema(max_retries=11)

    def test_bulk_replay_date_validation(self):
        """BulkReplayRequest: to_date vor from_date -> Fehler."""
        from pydantic import ValidationError

        _, BulkReplayRequest, _ = self._import_schemas()
        with pytest.raises(ValidationError):
            BulkReplayRequest(
                event_type="document.created",
                from_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
                to_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_create_request_header_blocklist(self):
        """WebhookEndpointCreateRequest: blockierte Header -> Fehler."""
        from pydantic import ValidationError

        _, _, WebhookEndpointCreateRequest = self._import_schemas()
        with pytest.raises(ValidationError):
            WebhookEndpointCreateRequest(
                url="https://example.com/hook",
                headers={"Content-Type": "application/json"},
            )
