# -*- coding: utf-8 -*-
"""
Document Lifecycle API Endpoints.

Enterprise Feature: Dokument-Lebenszyklus mit SLA-Überwachung.

Endpoints:
- GET  /document-lifecycle/overview           - Kanban-Übersicht (Stufen-Zaehler)
- GET  /document-lifecycle/{document_id}      - Lebenszyklus-Historie eines Dokuments
- POST /document-lifecycle/{document_id}/transition - Stufen-Übergang
- GET  /document-lifecycle/sla-violations     - Aktuelle SLA-Verletzungen
- GET  /document-lifecycle/metrics            - Stufen-Metriken (Durchschnittszeiten)
"""


from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.core.rate_limiting import limiter
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.db.models_document_lifecycle import DocumentLifecycleStage
from app.services.document_lifecycle_service import (
    DocumentLifecycleService,
    get_document_lifecycle_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/document-lifecycle",
    tags=["Document Lifecycle"],
)


# =============================================================================
# Pydantic Schemas
# =============================================================================


class StageTransitionRequest(BaseModel):
    """Anfrage für einen Stufen-Übergang."""

    to_stage: DocumentLifecycleStage = Field(
        ..., description="Ziel-Stufe"
    )
    note: Optional[str] = Field(
        None, max_length=500, description="Optionale Notiz"
    )


class LifecycleEventResponse(BaseModel):
    """Antwort für ein Lebenszyklus-Event."""

    id: str = Field(..., description="Event-ID")
    document_id: str = Field(..., description="Dokument-ID")
    from_stage: Optional[str] = Field(None, description="Ausgangs-Stufe")
    to_stage: str = Field(..., description="Ziel-Stufe")
    transitioned_at: Optional[str] = Field(
        None, description="Zeitpunkt des Übergangs"
    )
    transitioned_by_id: Optional[str] = Field(
        None, description="Benutzer-ID"
    )
    duration_seconds: Optional[int] = Field(
        None, description="Dauer in der vorherigen Stufe (Sekunden)"
    )
    sla_met: Optional[bool] = Field(
        None, description="SLA eingehalten?"
    )
    note: Optional[str] = Field(None, description="Notiz")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "document_id": "660e8400-e29b-41d4-a716-446655440001",
                "from_stage": "eingang",
                "to_stage": "ocr",
                "transitioned_at": "2026-02-15T10:30:00+00:00",
                "duration_seconds": 120,
                "sla_met": True,
            }
        }
    )


class SLAViolationResponse(BaseModel):
    """Antwort für eine SLA-Verletzung."""

    document_id: str = Field(..., description="Dokument-ID")
    document_filename: str = Field(..., description="Dateiname")
    document_type: str = Field(..., description="Dokumenttyp")
    current_stage: str = Field(..., description="Aktuelle Stufe")
    entered_stage_at: str = Field(
        ..., description="Zeitpunkt des Stufen-Eintritts"
    )
    max_duration_hours: int = Field(
        ..., description="Maximale Dauer (Stunden)"
    )
    actual_duration_hours: float = Field(
        ..., description="Tatsaechliche Dauer (Stunden)"
    )
    overdue_hours: float = Field(
        ..., description="Überschreitung (Stunden)"
    )
    escalation_to_role: Optional[str] = Field(
        None, description="Eskalations-Rolle"
    )


class StageMetricResponse(BaseModel):
    """Antwort für eine Stufen-Metrik."""

    stage: str = Field(..., description="Stufe")
    avg_duration_seconds: float = Field(
        ..., description="Durchschnittliche Dauer (Sekunden)"
    )
    min_duration_seconds: float = Field(
        ..., description="Minimale Dauer (Sekunden)"
    )
    max_duration_seconds: float = Field(
        ..., description="Maximale Dauer (Sekunden)"
    )
    total_transitions: int = Field(
        ..., description="Anzahl Übergaenge"
    )
    sla_compliance_rate: float = Field(
        ..., description="SLA-Einhaltungsrate (0-1)"
    )


# =============================================================================
# Endpoints
# IMPORTANT: Fixed paths MUST be defined before path-parameter routes
# to avoid /{document_id} shadowing /overview, /sla-violations, /metrics
# =============================================================================


@router.get(
    "/overview",
    response_model=Dict[str, int],
    summary="Kanban-Übersicht",
)
@limiter.limit("60/minute")
async def get_lifecycle_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Dict[str, int]:
    """
    Gibt die Kanban-Übersicht zurück: Anzahl Dokumente pro Stufe.

    Zeigt für jede Lebenszyklus-Stufe die Anzahl der aktuell
    in dieser Stufe befindlichen Dokumente.

    Returns:
        Dictionary mit Stufe -> Anzahl Dokumente
    """
    try:
        service = get_document_lifecycle_service(db)
        return await service.get_lifecycle_overview(company_id)
    except Exception as e:
        logger.error("lifecycle_overview_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lebenszyklus-Übersicht konnte nicht abgerufen werden",
        )


@router.get(
    "/sla-violations",
    response_model=List[SLAViolationResponse],
    summary="SLA-Verletzungen",
)
@limiter.limit("30/minute")
async def get_sla_violations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[SLAViolationResponse]:
    """
    Listet alle aktuellen SLA-Verletzungen auf.

    Zeigt Dokumente, deren Verweildauer in einer Stufe die
    konfigurierte maximale Dauer überschreitet.

    Returns:
        Liste von SLA-Verletzungen
    """
    try:
        service = get_document_lifecycle_service(db)
        violations = await service.check_sla_violations(
            company_id=company_id,
        )

        return [
            SLAViolationResponse(
                document_id=str(v.document_id),
                document_filename=v.document_filename,
                document_type=v.document_type,
                current_stage=v.current_stage,
                entered_stage_at=v.entered_stage_at.isoformat(),
                max_duration_hours=v.max_duration_hours,
                actual_duration_hours=v.actual_duration_hours,
                overdue_hours=v.overdue_hours,
                escalation_to_role=v.escalation_to_role,
            )
            for v in violations
        ]
    except Exception as e:
        logger.error("sla_violations_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SLA-Verletzungen konnten nicht abgerufen werden",
        )


@router.get(
    "/metrics",
    response_model=List[StageMetricResponse],
    summary="Stufen-Metriken",
)
@limiter.limit("30/minute")
async def get_stage_metrics(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[StageMetricResponse]:
    """
    Berechnet Metriken pro Lebenszyklus-Stufe.

    Zeigt Durchschnittszeiten, minimale/maximale Dauern und
    SLA-Einhaltungsraten pro Stufe.

    Returns:
        Liste von Stufen-Metriken
    """
    try:
        service = get_document_lifecycle_service(db)
        metrics = await service.get_stage_metrics(
            company_id=company_id,
            days=days,
        )

        return [
            StageMetricResponse(
                stage=m.stage,
                avg_duration_seconds=m.avg_duration_seconds,
                min_duration_seconds=m.min_duration_seconds,
                max_duration_seconds=m.max_duration_seconds,
                total_transitions=m.total_transitions,
                sla_compliance_rate=m.sla_compliance_rate,
            )
            for m in metrics
        ]
    except Exception as e:
        logger.error("stage_metrics_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stufen-Metriken konnten nicht berechnet werden",
        )


# Path-parameter routes AFTER fixed routes
@router.get(
    "/{document_id}",
    response_model=List[LifecycleEventResponse],
    summary="Lebenszyklus-Historie",
)
@limiter.limit("60/minute")
async def get_document_lifecycle_history(
    request: Request,
    document_id: UUID = Path(..., description="Dokument-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[LifecycleEventResponse]:
    """
    Gibt die vollständige Lebenszyklus-Historie eines Dokuments zurück.

    Zeigt alle Stufen-Übergaenge chronologisch sortiert mit
    Dauer- und SLA-Informationen.

    Returns:
        Liste von Lebenszyklus-Events
    """
    try:
        service = get_document_lifecycle_service(db)
        events = await service.get_document_history(
            document_id=document_id,
            company_id=company_id,
        )

        return [
            LifecycleEventResponse(
                id=str(event.id),
                document_id=str(event.document_id),
                from_stage=event.from_stage,
                to_stage=event.to_stage,
                transitioned_at=(
                    event.transitioned_at.isoformat()
                    if event.transitioned_at
                    else None
                ),
                transitioned_by_id=(
                    str(event.transitioned_by_id)
                    if event.transitioned_by_id
                    else None
                ),
                duration_seconds=event.duration_seconds,
                sla_met=event.sla_met,
                note=event.note,
            )
            for event in events
        ]
    except Exception as e:
        logger.error(
            "lifecycle_history_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lebenszyklus-Historie konnte nicht abgerufen werden",
        )


@router.post(
    "/{document_id}/transition",
    response_model=LifecycleEventResponse,
    summary="Stufen-Übergang",
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def transition_document_stage(
    request: Request,
    body: StageTransitionRequest,
    document_id: UUID = Path(..., description="Dokument-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> LifecycleEventResponse:
    """
    Führt einen Stufen-Übergang für ein Dokument durch.

    Validiert den Übergang, berechnet die Dauer in der
    vorherigen Stufe und prüft die SLA-Einhaltung.

    Returns:
        Das erstellte Lebenszyklus-Event
    """
    try:
        service = get_document_lifecycle_service(db)
        event = await service.transition_stage(
            document_id=document_id,
            company_id=company_id,
            to_stage=body.to_stage,
            user_id=current_user.id,
            note=body.note,
        )
        await db.commit()

        return LifecycleEventResponse(
            id=str(event.id),
            document_id=str(event.document_id),
            from_stage=event.from_stage,
            to_stage=event.to_stage,
            transitioned_at=(
                event.transitioned_at.isoformat()
                if event.transitioned_at
                else None
            ),
            transitioned_by_id=(
                str(event.transitioned_by_id)
                if event.transitioned_by_id
                else None
            ),
            duration_seconds=event.duration_seconds,
            sla_met=event.sla_met,
            note=event.note,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Lebenszyklus"),
        )
    except Exception as e:
        logger.error(
            "lifecycle_transition_failed",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stufen-Übergang konnte nicht durchgeführt werden",
        )
