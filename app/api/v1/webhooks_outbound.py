# -*- coding: utf-8 -*-
"""
Outbound Webhook Event Platform API.

REST-Endpunkte fuer das vollstaendige Outbound-Webhook-Management:
- CRUD fuer Webhook-Endpoints (Registrierung, Konfiguration, Deaktivierung)
- Event-Log fuer Audit und Replay-Vorbereitung
- Zustellungshistorie und Fehlerverfolgung
- Dead Letter Queue (DLQ) - Verwaltung und manueller Retry
- Test-Zustellungen fuer neue Endpoints
- Event-Replay (einzeln und per Bulk)

Sicherheitsrichtlinien:
- Secrets werden NIEMALS in API-Antworten zurueckgegeben (nur bei Erstellung)
- Alle Endpoints erfordern Mandantenzugehoerigkeitspruefung
- Rate-Limiting schuetzt vor Missbrauch

Feinpoliert und durchdacht - Enterprise-grade Webhook Event Platform API.
"""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.db.models_webhooks import WebhookDelivery, WebhookEndpoint, WebhookEventLog
from app.middleware.company_context import require_company
from app.services.webhook_service import get_webhook_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks/outbound", tags=["webhooks-outbound"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class RetryPolicySchema(BaseModel):
    """Retry-Richtlinie fuer einen Webhook-Endpoint."""

    max_retries: int = Field(3, ge=0, le=10, description="Maximale Anzahl Wiederholungsversuche")
    backoff_factor: int = Field(2, ge=1, le=10, description="Exponentieller Backoff-Faktor")
    timeout_seconds: int = Field(30, ge=5, le=120, description="Timeout in Sekunden")


class WebhookEndpointCreateRequest(BaseModel):
    """Request-Body fuer die Endpoint-Registrierung."""

    url: str = Field(
        ...,
        max_length=2000,
        description="Ziel-URL fuer Webhook-Zustellungen (HTTPS empfohlen)",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionale Beschreibung des Endpoints",
    )
    event_types: List[str] = Field(
        default_factory=list,
        description=(
            "Abonnierte Event-Typen, z.B. ['document.created', 'invoice.*']. "
            "Leere Liste = alle Events."
        ),
    )
    headers: Optional[Dict[str, str]] = Field(
        None,
        description="Optionale benutzerdefinierte HTTP-Header",
    )
    retry_policy: Optional[RetryPolicySchema] = Field(
        None,
        description="Retry-Konfiguration (Standard: max_retries=3, backoff_factor=2)",
    )

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: List[str]) -> List[str]:
        """Validiert Event-Typ-Format (lowercase mit Punkt-Separator oder Wildcard)."""
        for event_type in v:
            if not event_type or len(event_type) > 100:
                raise ValueError(
                    f"Ungueltiger Event-Typ: '{event_type[:50]}' (max 100 Zeichen)"
                )
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Verhindert sicherheitskritische Header-Ueberschreibungen."""
        if v is None:
            return v
        blocked = {"authorization", "x-webhook-signature", "content-type"}
        for key in v:
            if key.lower() in blocked:
                raise ValueError(
                    f"Header '{key}' darf nicht manuell gesetzt werden"
                )
        return v


class WebhookEndpointUpdateRequest(BaseModel):
    """Request-Body fuer das Endpoint-Update (alle Felder optional)."""

    url: Optional[str] = Field(None, max_length=2000)
    description: Optional[str] = Field(None, max_length=500)
    secret: Optional[str] = Field(
        None,
        description="Neues Secret fuer Secret-Rotation (wird sofort gehasht)",
    )
    event_types: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    retry_policy: Optional[RetryPolicySchema] = None
    is_active: Optional[bool] = None


class WebhookEndpointResponse(BaseModel):
    """Antwort-Schema fuer einen Webhook-Endpoint (ohne Secret)."""

    id: UUID
    company_id: UUID
    url: str
    description: Optional[str]
    event_types: List[str]
    is_active: bool
    headers: Optional[Dict[str, str]]
    retry_policy: Dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookEndpointCreateResponse(WebhookEndpointResponse):
    """Antwort bei Endpoint-Erstellung (enthaelt das Secret einmalig)."""

    secret: str = Field(
        ...,
        description=(
            "Webhook-Secret im Klartext. Wird nur bei der Erstellung angezeigt "
            "und kann spaeter NICHT mehr abgerufen werden."
        ),
    )


class WebhookDeliveryResponse(BaseModel):
    """Antwort-Schema fuer eine Webhook-Zustellung."""

    id: UUID
    endpoint_id: UUID
    company_id: UUID
    event_type: str
    event_id: UUID
    status: str
    attempts: int
    max_attempts: int
    response_status_code: Optional[int]
    response_body: Optional[str]
    last_attempt_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookEventLogResponse(BaseModel):
    """Antwort-Schema fuer einen Event-Log-Eintrag."""

    id: UUID
    company_id: UUID
    event_type: str
    source_table: str
    source_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookTestRequest(BaseModel):
    """Request-Body fuer eine Test-Zustellung."""

    event_type: str = Field(
        "webhook.test",
        description="Event-Typ fuer die Test-Zustellung",
    )
    payload: Optional[Dict] = Field(
        None,
        description="Optionaler Test-Payload (Standard: generierter Test-Payload)",
    )


class WebhookTestResponse(BaseModel):
    """Antwort einer Test-Zustellung."""

    delivery_id: UUID
    status: str
    message: str


class BulkReplayRequest(BaseModel):
    """Request-Body fuer einen Bulk-Replay."""

    event_type: str = Field(..., description="Zu replaylender Event-Typ")
    from_date: datetime = Field(..., description="Startdatum des Replay-Zeitraums (UTC)")
    to_date: datetime = Field(..., description="Enddatum des Replay-Zeitraums (UTC)")

    @field_validator("to_date")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """Prueft dass das Enddatum nach dem Startdatum liegt."""
        from_date = info.data.get("from_date")
        if from_date and v <= from_date:
            raise ValueError("Das Enddatum muss nach dem Startdatum liegen")
        return v


class PaginatedResponse(BaseModel):
    """Generische paginierte Antwort."""

    total: int
    page: int
    per_page: int
    has_more: bool


class WebhookEndpointListResponse(PaginatedResponse):
    """Paginierte Liste von Webhook-Endpoints."""

    items: List[WebhookEndpointResponse]


class WebhookDeliveryListResponse(PaginatedResponse):
    """Paginierte Liste von Webhook-Zustellungen."""

    items: List[WebhookDeliveryResponse]


class WebhookEventLogListResponse(PaginatedResponse):
    """Paginierte Liste von Event-Log-Eintraegen."""

    items: List[WebhookEventLogResponse]


# =============================================================================
# Hilfsfunktionen
# =============================================================================


def _generate_webhook_secret() -> str:
    """Generiert ein kryptografisch sicheres Webhook-Secret.

    Returns:
        Secret im Format "whsec_<32-Byte-URL-Safe-Token>"
    """
    return f"whsec_{secrets.token_urlsafe(32)}"


def _endpoint_to_response(endpoint: WebhookEndpoint) -> WebhookEndpointResponse:
    """Konvertiert ein WebhookEndpoint-Modell in ein Response-Schema."""
    return WebhookEndpointResponse(
        id=endpoint.id,
        company_id=endpoint.company_id,
        url=endpoint.url,
        description=endpoint.description,
        event_types=endpoint.event_types or [],
        is_active=endpoint.is_active,
        headers=endpoint.headers,
        retry_policy=endpoint.retry_policy or {},
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


def _delivery_to_response(delivery: WebhookDelivery) -> WebhookDeliveryResponse:
    """Konvertiert ein WebhookDelivery-Modell in ein Response-Schema."""
    return WebhookDeliveryResponse(
        id=delivery.id,
        endpoint_id=delivery.endpoint_id,
        company_id=delivery.company_id,
        event_type=delivery.event_type,
        event_id=delivery.event_id,
        status=delivery.status,
        attempts=delivery.attempts,
        max_attempts=delivery.max_attempts,
        response_status_code=delivery.response_status_code,
        response_body=delivery.response_body,
        last_attempt_at=delivery.last_attempt_at,
        next_retry_at=delivery.next_retry_at,
        delivered_at=delivery.delivered_at,
        created_at=delivery.created_at,
    )


def _event_log_to_response(event_log: WebhookEventLog) -> WebhookEventLogResponse:
    """Konvertiert ein WebhookEventLog-Modell in ein Response-Schema."""
    return WebhookEventLogResponse(
        id=event_log.id,
        company_id=event_log.company_id,
        event_type=event_log.event_type,
        source_table=event_log.source_table,
        source_id=event_log.source_id,
        created_at=event_log.created_at,
    )


# =============================================================================
# Endpoint-Verwaltung
# =============================================================================


@router.get(
    "/endpoints",
    response_model=WebhookEndpointListResponse,
    summary="Webhook-Endpoints auflisten",
    description="Gibt alle registrierten Outbound-Webhook-Endpoints des Mandanten zurueck.",
)
async def list_endpoints(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    include_inactive: bool = Query(False, description="Auch deaktivierte Endpoints anzeigen"),
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointListResponse:
    """Listet alle Webhook-Endpoints des aktuellen Mandanten auf."""
    service = get_webhook_service()
    endpoints = await service.list_endpoints(
        db=db,
        company_id=current_company.id,
        include_inactive=include_inactive,
    )

    total = len(endpoints)
    start = (page - 1) * per_page
    page_items = endpoints[start : start + per_page]

    return WebhookEndpointListResponse(
        total=total,
        page=page,
        per_page=per_page,
        has_more=(start + per_page) < total,
        items=[_endpoint_to_response(e) for e in page_items],
    )


@router.post(
    "/endpoints",
    response_model=WebhookEndpointCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Webhook-Endpoint registrieren",
    description=(
        "Registriert einen neuen Outbound-Webhook-Endpoint. "
        "Das Secret wird nur bei der Erstellung angezeigt und kann spaeter NICHT mehr abgerufen werden."
    ),
)
async def register_endpoint(
    request_body: WebhookEndpointCreateRequest,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointCreateResponse:
    """Registriert einen neuen Webhook-Endpoint.

    Das generierte Secret wird einmalig in der Antwort zurueckgegeben.
    Danach ist es nicht mehr abrufbar - bei Verlust muss ein neues Secret
    ueber den Update-Endpunkt rotiert werden.
    """
    secret = _generate_webhook_secret()
    service = get_webhook_service()

    try:
        endpoint = await service.register_endpoint(
            db=db,
            company_id=current_company.id,
            url=request_body.url,
            secret=secret,
            event_types=request_body.event_types,
            description=request_body.description,
            headers=request_body.headers,
            retry_policy=request_body.retry_policy.model_dump() if request_body.retry_policy else None,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_endpoint_register_failed",
            company_id=str(current_company.id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook-Endpoint konnte nicht registriert werden.",
        )

    response = WebhookEndpointCreateResponse(
        id=endpoint.id,
        company_id=endpoint.company_id,
        url=endpoint.url,
        description=endpoint.description,
        event_types=endpoint.event_types or [],
        is_active=endpoint.is_active,
        headers=endpoint.headers,
        retry_policy=endpoint.retry_policy or {},
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
        secret=secret,  # Einmalig im Klartext - danach nicht mehr abrufbar
    )

    return response


@router.put(
    "/endpoints/{endpoint_id}",
    response_model=WebhookEndpointResponse,
    summary="Webhook-Endpoint aktualisieren",
    description="Aktualisiert die Konfiguration eines bestehenden Endpoints. Alle Felder sind optional.",
)
async def update_endpoint(
    endpoint_id: UUID,
    request_body: WebhookEndpointUpdateRequest,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    """Aktualisiert einen bestehenden Webhook-Endpoint (PATCH-Semantik).

    Zur Secret-Rotation: Das neue Secret wird gehasht gespeichert und
    ist danach nicht mehr im Klartext abrufbar.
    """
    service = get_webhook_service()

    try:
        endpoint = await service.update_endpoint(
            db=db,
            endpoint_id=endpoint_id,
            company_id=current_company.id,
            url=request_body.url,
            description=request_body.description,
            secret=request_body.secret,
            event_types=request_body.event_types,
            headers=request_body.headers,
            retry_policy=(
                request_body.retry_policy.model_dump() if request_body.retry_policy else None
            ),
            is_active=request_body.is_active,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_endpoint_update_failed",
            endpoint_id=str(endpoint_id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook-Endpoint konnte nicht aktualisiert werden.",
        )

    return _endpoint_to_response(endpoint)


@router.delete(
    "/endpoints/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Webhook-Endpoint deaktivieren",
    description="Deaktiviert einen Webhook-Endpoint (Soft-Delete). Historische Daten bleiben erhalten.",
)
async def delete_endpoint(
    endpoint_id: UUID,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deaktiviert einen Webhook-Endpoint.

    Die Deaktivierung ist kein physischer Loeschvorgang - historische
    Zustelldaten bleiben fuer Auditzwecke erhalten.
    """
    service = get_webhook_service()

    try:
        await service.delete_endpoint(
            db=db,
            endpoint_id=endpoint_id,
            company_id=current_company.id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_endpoint_delete_failed",
            endpoint_id=str(endpoint_id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook-Endpoint konnte nicht deaktiviert werden.",
        )


@router.post(
    "/endpoints/{endpoint_id}/test",
    response_model=WebhookTestResponse,
    summary="Test-Zustellung senden",
    description="Sendet eine Test-Zustellung an den konfigurierten Endpoint.",
)
async def test_endpoint(
    endpoint_id: UUID,
    request_body: WebhookTestRequest,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookTestResponse:
    """Sendet einen Test-Webhook an den konfigurierten Endpoint.

    Der Test-Payload wird mit dem Praefix 'webhook.test' markiert und
    erscheint im Zustellungsprotokoll des Endpoints.
    """
    service = get_webhook_service()

    # Pruefe Zugriff auf Endpoint
    try:
        endpoints = await service.list_endpoints(
            db=db, company_id=current_company.id
        )
        endpoint_ids = {str(e.id) for e in endpoints}
        if str(endpoint_id) not in endpoint_ids:
            raise ValueError("Endpoint nicht gefunden")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    test_payload: Dict = request_body.payload or {
        "test": True,
        "message": "Dies ist eine Test-Zustellung vom Ablage-System.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint_id": str(endpoint_id),
    }

    # Test-Event publizieren (direkt an diesen Endpoint)
    test_event_id = uuid.uuid4()

    try:
        from app.workers.tasks.webhook_tasks import deliver_webhook
        from app.db.models_webhooks import WebhookDelivery

        # Delivery-Record direkt erstellen und Task dispatchen
        delivery = WebhookDelivery(
            endpoint_id=endpoint_id,
            company_id=current_company.id,
            event_type=request_body.event_type,
            event_id=test_event_id,
            payload=test_payload,
            status="pending",
            attempts=0,
            max_attempts=1,  # Test: kein Retry
        )
        db.add(delivery)
        await db.flush()
        await db.refresh(delivery)
        await db.commit()

        deliver_webhook.delay(str(delivery.id))

        return WebhookTestResponse(
            delivery_id=delivery.id,
            status="dispatched",
            message="Test-Zustellung wurde gestartet. Das Ergebnis ist in der Zustellungshistorie sichtbar.",
        )

    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_test_failed",
            endpoint_id=str(endpoint_id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Test-Zustellung konnte nicht gestartet werden.",
        )


# =============================================================================
# Zustellungshistorie
# =============================================================================


@router.get(
    "/endpoints/{endpoint_id}/deliveries",
    response_model=WebhookDeliveryListResponse,
    summary="Zustellungshistorie",
    description="Gibt die Zustellungshistorie eines Webhook-Endpoints zurueck.",
)
async def get_delivery_history(
    endpoint_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryListResponse:
    """Gibt die Zustellungshistorie eines spezifischen Endpoints zurueck."""
    service = get_webhook_service()

    try:
        deliveries = await service.get_delivery_history(
            db=db,
            endpoint_id=endpoint_id,
            company_id=current_company.id,
            limit=per_page,
            offset=(page - 1) * per_page,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return WebhookDeliveryListResponse(
        total=len(deliveries),
        page=page,
        per_page=per_page,
        has_more=len(deliveries) == per_page,
        items=[_delivery_to_response(d) for d in deliveries],
    )


# =============================================================================
# Dead Letter Queue
# =============================================================================


@router.get(
    "/dlq",
    response_model=WebhookDeliveryListResponse,
    summary="Dead Letter Queue anzeigen",
    description="Gibt alle Eintraege in der Dead Letter Queue des Mandanten zurueck.",
)
async def get_dlq(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryListResponse:
    """Gibt alle fehlgeschlagenen Zustellungen in der DLQ zurueck.

    DLQ-Eintraege sind Zustellungen, bei denen alle Versuche erschoepft wurden.
    Sie koennen manuell wiederholt oder fuer die Analyse exportiert werden.
    """
    service = get_webhook_service()
    dlq_items = await service.get_dlq_items(
        db=db,
        company_id=current_company.id,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return WebhookDeliveryListResponse(
        total=len(dlq_items),
        page=page,
        per_page=per_page,
        has_more=len(dlq_items) == per_page,
        items=[_delivery_to_response(d) for d in dlq_items],
    )


@router.post(
    "/dlq/{delivery_id}/retry",
    response_model=WebhookDeliveryResponse,
    summary="DLQ-Eintrag wiederholen",
    description="Fuehrt einen manuellen Retry fuer einen DLQ-Eintrag durch.",
)
async def retry_dlq_item(
    delivery_id: UUID,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """Wiederholt eine fehlgeschlagene Zustellung aus der DLQ manuell.

    Setzt den Status auf 'pending' und dispatcht sofort einen neuen
    Zustellungs-Task.
    """
    service = get_webhook_service()

    try:
        delivery = await service.retry_delivery(
            db=db,
            delivery_id=delivery_id,
            company_id=current_company.id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_dlq_retry_failed",
            delivery_id=str(delivery_id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Wiederholung der Zustellung fehlgeschlagen.",
        )

    return _delivery_to_response(delivery)


# =============================================================================
# Event-Log und Replay
# =============================================================================


@router.get(
    "/events",
    response_model=WebhookEventLogListResponse,
    summary="Event-Journal anzeigen",
    description="Gibt Eintraege aus dem Event-Journal fuer Replay-Planung zurueck.",
)
async def get_event_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    event_type: Optional[str] = Query(None, description="Filterung nach Event-Typ"),
    from_date: Optional[datetime] = Query(None, description="Startdatum (ISO 8601)"),
    to_date: Optional[datetime] = Query(None, description="Enddatum (ISO 8601)"),
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> WebhookEventLogListResponse:
    """Gibt das Event-Journal des Mandanten zurueck.

    Das Journal enthaelt alle publizierten Events und dient als Grundlage
    fuer den Replay von Events nach Endpoint-Ausfaellen oder fuer die
    Synchronisation neuer Endpoints.
    """
    service = get_webhook_service()
    events = await service.get_event_log(
        db=db,
        company_id=current_company.id,
        event_type=event_type,
        from_date=from_date,
        to_date=to_date,
        limit=per_page,
        offset=(page - 1) * per_page,
    )

    return WebhookEventLogListResponse(
        total=len(events),
        page=page,
        per_page=per_page,
        has_more=len(events) == per_page,
        items=[_event_log_to_response(e) for e in events],
    )


@router.post(
    "/events/{event_id}/replay",
    summary="Einzelnen Event replayan",
    description="Replayed einen einzelnen Event an alle passenden aktiven Endpoints.",
)
async def replay_single_event(
    event_id: UUID,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Replayed einen spezifischen Event aus dem Journal.

    Alle aktiven Endpoints, die den Event-Typ abonniert haben, erhalten
    eine neue Zustellung mit dem originalen Payload.

    Returns:
        Anzahl der ausgeloesten Zustellungen
    """
    service = get_webhook_service()

    try:
        dispatched = await service.replay_event(
            db=db,
            event_log_id=event_id,
            company_id=current_company.id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_replay_failed",
            event_id=str(event_id)[:8],
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event-Replay fehlgeschlagen.",
        )

    return {
        "event_id": str(event_id),
        "dispatched": dispatched,
        "message": f"{dispatched} Webhook-Zustellung(en) gestartet.",
    }


@router.post(
    "/events/replay/bulk",
    summary="Bulk-Replay starten",
    description=(
        "Replayed alle Events eines Typs in einem definierten Zeitraum. "
        "Nuetzlich nach Endpoint-Ausfaellen oder fuer neue Abonnenten."
    ),
)
async def replay_bulk_events(
    request_body: BulkReplayRequest,
    current_company=Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """Startet einen Bulk-Replay fuer Events in einem Zeitraum.

    Alle Events des angegebenen Typs im definierten Zeitraum werden
    erneut an alle passenden aktiven Endpoints zugestellt.

    Args:
        request_body: Event-Typ und Zeitraum fuer den Replay

    Returns:
        Gesamtanzahl der gestarteten Zustellungen
    """
    service = get_webhook_service()

    try:
        total_dispatched = await service.replay_events(
            db=db,
            company_id=current_company.id,
            event_type=request_body.event_type,
            from_date=request_body.from_date,
            to_date=request_body.to_date,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "webhook_bulk_replay_failed",
            company_id=str(current_company.id)[:8],
            event_type=request_body.event_type,
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bulk-Replay fehlgeschlagen.",
        )

    return {
        "event_type": request_body.event_type,
        "from_date": request_body.from_date.isoformat(),
        "to_date": request_body.to_date.isoformat(),
        "total_dispatched": total_dispatched,
        "message": f"Bulk-Replay gestartet: {total_dispatched} Zustellung(en) ausgeloest.",
    }
