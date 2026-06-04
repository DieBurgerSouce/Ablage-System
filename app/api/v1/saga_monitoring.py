"""Saga Monitoring API Endpoints.

Überwachung von Saga-Ausführungen (Rechnungsverarbeitung, Zahlungen).
Stellt Saga-Status, Step-Details und Statistiken bereit.

7 Endpoints:
- GET /sagas/ - Liste aller Saga-Ausführungen
- GET /sagas/statistics - Saga-Statistiken (Erfolgsrate, DLQ, etc.)
- GET /sagas/{saga_id} - Saga-Details mit Steps
- GET /sagas/{saga_id}/logs - Transaktionslogs einer Saga
- GET /sagas/{saga_id}/diagram - State-Diagramm einer Saga
- POST /sagas/{saga_id}/retry - Saga manuell wiederholen
- DELETE /sagas/{saga_id}/dlq - Saga aus DLQ entfernen
"""


from typing import List, Optional
from uuid import UUID

import structlog
from app.core.safe_errors import safe_error_detail
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.api.v1.workflows import get_user_company_id
from app.core.types import JSONDict
from app.db.models import User
from app.db.models_workflow_versioning import Saga, SagaStep, SagaTransactionLog
from app.services.workflow.saga_service import SagaService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sagas", tags=["saga-monitoring"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class SagaStepResponse(BaseModel):
    """Schema für einen Saga-Schritt."""

    id: str
    step_order: int
    name: str
    description: Optional[str] = None
    action_type: str
    status: str
    has_compensation: bool = False
    compensation_type: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    result_data: Optional[JSONDict] = None

    model_config = ConfigDict(from_attributes=True)


class SagaSummaryResponse(BaseModel):
    """Schema für Saga-Zusammenfassung in Listen."""

    id: str
    name: str
    description: Optional[str] = None
    status: str
    total_steps: int
    current_step_index: int = 0
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    in_dead_letter_queue: bool = False
    retry_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SagaDetailResponse(BaseModel):
    """Schema für Saga-Detailansicht mit Steps."""

    id: str
    name: str
    description: Optional[str] = None
    status: str
    total_steps: int
    current_step_index: int = 0
    context_data: Optional[JSONDict] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    in_dead_letter_queue: bool = False
    dead_letter_reason: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    steps: List[SagaStepResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SagaListResponse(BaseModel):
    """Schema für paginierte Saga-Liste."""

    items: List[SagaSummaryResponse]
    total: int
    page: int
    per_page: int


class SagaLogEntryResponse(BaseModel):
    """Schema für einen Transaktionslog-Eintrag."""

    id: str
    saga_id: str
    step_id: Optional[str] = None
    event_type: str
    previous_state: Optional[str] = None
    new_state: str
    event_data: Optional[JSONDict] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SagaLogsResponse(BaseModel):
    """Schema für paginierte Transaktionslogs."""

    items: List[SagaLogEntryResponse]
    total: int
    page: int
    per_page: int


class SagaStatisticsResponse(BaseModel):
    """Schema für Saga-Statistiken."""

    total: int
    by_status: JSONDict
    dead_letter_queue: int
    success_rate: float
    completed: int
    failed: int
    compensated: int
    partially_compensated: int


class SagaRetryResponse(BaseModel):
    """Schema für Saga-Retry Ergebnis."""

    saga_id: str
    status: str
    retry_count: int
    message: str


class SagaDiagramResponse(BaseModel):
    """Schema für Saga State-Diagramm."""

    saga_id: str
    name: str
    status: str
    nodes: List[JSONDict]
    edges: List[JSONDict]
    progress_percent: Optional[float] = None


# =============================================================================
# Helper
# =============================================================================


def _saga_to_summary(saga: Saga) -> SagaSummaryResponse:
    """Konvertiert ein Saga-ORM-Objekt in ein Summary-Schema."""
    return SagaSummaryResponse(
        id=str(saga.id),
        name=saga.name,
        description=saga.description,
        status=saga.status,
        total_steps=saga.total_steps,
        current_step_index=saga.current_step_index or 0,
        created_at=saga.created_at.isoformat() if saga.created_at else None,
        started_at=saga.started_at.isoformat() if saga.started_at else None,
        completed_at=saga.completed_at.isoformat() if saga.completed_at else None,
        in_dead_letter_queue=saga.in_dead_letter_queue,
        retry_count=saga.retry_count,
    )


def _step_to_response(step: SagaStep) -> SagaStepResponse:
    """Konvertiert ein SagaStep-ORM-Objekt in ein Response-Schema."""
    return SagaStepResponse(
        id=str(step.id),
        step_order=step.step_order,
        name=step.name,
        description=step.description,
        action_type=step.action_type,
        status=step.status,
        has_compensation=step.has_compensation,
        compensation_type=step.compensation_type,
        executed_at=step.executed_at.isoformat() if step.executed_at else None,
        completed_at=step.completed_at.isoformat() if step.completed_at else None,
        error_message=step.error_message,
        retry_count=step.retry_count,
        result_data=step.result_data,
    )


def _log_to_response(log: SagaTransactionLog) -> SagaLogEntryResponse:
    """Konvertiert ein SagaTransactionLog-ORM-Objekt in ein Response-Schema."""
    return SagaLogEntryResponse(
        id=str(log.id),
        saga_id=str(log.saga_id),
        step_id=str(log.step_id) if log.step_id else None,
        event_type=log.event_type,
        previous_state=log.previous_state,
        new_state=log.new_state,
        event_data=log.event_data,
        error_message=log.error_message,
        created_at=log.created_at.isoformat() if log.created_at else None,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/",
    response_model=SagaListResponse,
    summary="Saga-Ausführungen auflisten",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def list_sagas(
    request: Request,
    saga_status: Optional[str] = Query(
        None,
        alias="status",
        description="Filter nach Status (pending, running, completed, "
        "failed, compensated, partially_compensated)",
    ),
    in_dlq: Optional[bool] = Query(
        None,
        description="Nur Sagas aus der Dead Letter Queue",
    ),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaListResponse:
    """Listet alle Saga-Ausführungen des Mandanten auf.

    Unterstützt Filterung nach Status und Dead Letter Queue.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "list_sagas_requested",
        company_id=str(company_id),
        status_filter=saga_status,
        in_dlq=in_dlq,
        page=page,
        per_page=per_page,
    )

    try:
        sagas, total = await saga_service.list_sagas(
            company_id=company_id,
            status=saga_status,
            in_dead_letter_queue=in_dlq,
            offset=(page - 1) * per_page,
            limit=per_page,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Saga"),
        )

    return SagaListResponse(
        items=[_saga_to_summary(s) for s in sagas],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/statistics",
    response_model=SagaStatisticsResponse,
    summary="Saga-Statistiken abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_saga_statistics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaStatisticsResponse:
    """Gibt aggregierte Saga-Statistiken zurueck.

    Enthaelt Erfolgsrate, DLQ-Groesse und Status-Verteilung.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "get_saga_statistics_requested",
        company_id=str(company_id),
    )

    stats = await saga_service.get_saga_statistics(company_id=company_id)
    return SagaStatisticsResponse(**stats)


@router.get(
    "/{saga_id}",
    response_model=SagaDetailResponse,
    summary="Saga-Details mit Steps abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_saga_detail(
    request: Request,
    saga_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaDetailResponse:
    """Gibt detaillierte Informationen zu einer Saga inkl. aller Steps zurück."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "get_saga_detail_requested",
        company_id=str(company_id),
        saga_id=str(saga_id),
    )

    try:
        saga = await saga_service.get_saga(
            saga_id=saga_id,
            company_id=company_id,
            include_steps=True,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Saga"),
        )

    if not saga:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saga nicht gefunden",
        )

    steps = sorted(saga.steps, key=lambda s: s.step_order)

    return SagaDetailResponse(
        id=str(saga.id),
        name=saga.name,
        description=saga.description,
        status=saga.status,
        total_steps=saga.total_steps,
        current_step_index=saga.current_step_index or 0,
        context_data=saga.context_data,
        created_at=saga.created_at.isoformat() if saga.created_at else None,
        started_at=saga.started_at.isoformat() if saga.started_at else None,
        completed_at=saga.completed_at.isoformat() if saga.completed_at else None,
        in_dead_letter_queue=saga.in_dead_letter_queue,
        dead_letter_reason=saga.dead_letter_reason,
        retry_count=saga.retry_count,
        max_retries=saga.max_retries,
        steps=[_step_to_response(s) for s in steps],
    )


@router.get(
    "/{saga_id}/logs",
    response_model=SagaLogsResponse,
    summary="Saga-Transaktionslogs abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_saga_logs(
    request: Request,
    saga_id: UUID,
    step_id: Optional[UUID] = Query(None, description="Filter nach Step-ID"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=200, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaLogsResponse:
    """Gibt die Transaktionslogs einer Saga zurück.

    Zeigt alle State-Transitions, Events und Fehler chronologisch.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "get_saga_logs_requested",
        company_id=str(company_id),
        saga_id=str(saga_id),
        step_id=str(step_id) if step_id else None,
        page=page,
        per_page=per_page,
    )

    # Prüfen ob Saga existiert
    saga = await saga_service.get_saga(
        saga_id=saga_id,
        company_id=company_id,
        include_steps=False,
    )
    if not saga:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saga nicht gefunden",
        )

    try:
        logs, total = await saga_service.get_transaction_logs(
            saga_id=saga_id,
            company_id=company_id,
            step_id=step_id,
            offset=(page - 1) * per_page,
            limit=per_page,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Saga"),
        )

    return SagaLogsResponse(
        items=[_log_to_response(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{saga_id}/diagram",
    response_model=SagaDiagramResponse,
    summary="Saga State-Diagramm abrufen",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_saga_diagram(
    request: Request,
    saga_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaDiagramResponse:
    """Gibt ein State-Diagramm fuer eine Saga zurueck.

    Zeigt Nodes (Steps) und Edges (Transitionen) fuer Visualisierung.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)
    diagram = await saga_service.get_saga_state_diagram(
        saga_id=saga_id,
        company_id=company_id,
    )

    if not diagram:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saga nicht gefunden",
        )

    return SagaDiagramResponse(**diagram)


@router.post(
    "/{saga_id}/retry",
    response_model=SagaRetryResponse,
    summary="Saga manuell wiederholen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def retry_saga(
    request: Request,
    saga_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaRetryResponse:
    """Wiederholt eine fehlgeschlagene Saga manuell.

    Nur moeglich fuer Sagas im Status FAILED oder PARTIALLY_COMPENSATED.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "saga_manual_retry_requested",
        company_id=str(company_id),
        saga_id=str(saga_id),
        user_id=str(current_user.id),
    )

    saga = await saga_service.retry_saga(
        saga_id=saga_id,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not saga:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Saga kann nicht wiederholt werden (nicht gefunden, falscher Status oder max. Versuche erreicht)",
        )

    return SagaRetryResponse(
        saga_id=str(saga.id),
        status=saga.status,
        retry_count=saga.retry_count,
        message="Saga wird erneut ausgefuehrt",
    )


@router.delete(
    "/{saga_id}/dlq",
    response_model=SagaRetryResponse,
    summary="Saga aus Dead Letter Queue entfernen",
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def remove_saga_from_dlq(
    request: Request,
    saga_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SagaRetryResponse:
    """Entfernt eine Saga aus der Dead Letter Queue.

    Die Saga bleibt im aktuellen Status, wird aber nicht mehr
    automatisch fuer Retry vorgemerkt.
    """
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Benutzer muss einer Firma zugeordnet sein",
        )

    saga_service = SagaService(db)

    logger.info(
        "saga_remove_from_dlq_requested",
        company_id=str(company_id),
        saga_id=str(saga_id),
        user_id=str(current_user.id),
    )

    saga = await saga_service.remove_from_dead_letter_queue(
        saga_id=saga_id,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not saga:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saga nicht gefunden oder nicht in der Dead Letter Queue",
        )

    return SagaRetryResponse(
        saga_id=str(saga.id),
        status=saga.status,
        retry_count=saga.retry_count,
        message="Saga aus Dead Letter Queue entfernt",
    )
