# -*- coding: utf-8 -*-
"""Integrations-Sync Dashboard API.

REST-Endpunkte für das Integrations-Sync Dashboard:
- Alle Integrationen auflisten
- Dashboard-Statistiken abrufen
- Sync-Verlauf pro Integration
- Manuellen Sync auslösen
- Konfiguration aktualisieren
- Health-Status aller Integrationen

Feinpoliert und durchdacht - Enterprise-grade Integrations-API.
"""

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    get_user_company_id_dep,
)
from app.db.models import User
from app.db.models_integration_sync import INTEGRATION_TYPES
from app.services.integration_sync_service import (
    get_integration_sync_service,
)
from app.core.safe_errors import safe_error_log

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations-Sync"])


# =============================================================================
# Pydantic-Schemata
# =============================================================================


class IntegrationConfigResponse(BaseModel):
    """Antwort-Schema für eine einzelne Integrations-Konfiguration."""

    id: UUID
    company_id: UUID
    integration_type: str
    display_name: str
    config: Dict
    is_active: bool
    last_sync_at: Optional[str]
    last_sync_status: Optional[str]
    last_error_message: Optional[str]
    sync_interval_minutes: int
    next_sync_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class IntegrationListResponse(BaseModel):
    """Antwort-Schema für die Integrations-Liste."""

    integrations: List[Dict]
    total: int


class DashboardStatsResponse(BaseModel):
    """Antwort-Schema für Dashboard-Gesamtstatistiken."""

    total_integrations: int
    active_integrations: int
    integrations_in_error: int
    integrations_partial: int
    healthy_integrations: int
    latest_sync_at: Optional[str]
    error_rate_24h: float
    total_runs_24h: int
    error_runs_24h: int
    avg_sync_duration_seconds: Optional[float]


class SyncLogResponse(BaseModel):
    """Antwort-Schema für einen einzelnen Sync-Log-Eintrag."""

    id: UUID
    integration_config_id: UUID
    company_id: UUID
    sync_type: str
    status: str
    items_processed: int
    items_failed: int
    items_total: int
    error_details: Dict
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]

    model_config = {"from_attributes": True}


class SyncHistoryResponse(BaseModel):
    """Antwort-Schema für den Sync-Verlauf."""

    logs: List[Dict]
    total: int
    integration_type: Optional[str]


class TriggerSyncResponse(BaseModel):
    """Antwort-Schema nach Auslösen eines manuellen Syncs."""

    sync_log_id: str
    task_id: Optional[str]
    integration_type: str
    status: str
    message: str


class UpdateConfigRequest(BaseModel):
    """Request-Schema für Konfigurations-Updates."""

    is_active: Optional[bool] = Field(
        None, description="Integration aktivieren oder deaktivieren"
    )
    sync_interval_minutes: Optional[int] = Field(
        None, ge=1, le=10080, description="Sync-Intervall in Minuten (1 Min bis 7 Tage)"
    )
    display_name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Anzeigename im Dashboard"
    )
    config: Optional[Dict] = Field(
        None, description="Integrationsspezifische Konfigurationsdaten"
    )


class HealthStatusEntry(BaseModel):
    """Health-Status-Eintrag für eine einzelne Integration."""

    integration_type: str
    display_name: str
    is_active: bool
    health_level: str
    last_sync_at: Optional[str]
    last_sync_status: Optional[str]
    minutes_since_last_sync: Optional[float]
    sync_interval_minutes: int
    total_runs_24h: int
    error_runs_24h: int
    error_rate_24h: float
    avg_duration_seconds: Optional[float]


class HealthStatusResponse(BaseModel):
    """Antwort-Schema für den Integrations-Health-Check."""

    integrations: List[Dict]
    overall_health: str


# =============================================================================
# API-Endpunkte
# =============================================================================


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> IntegrationListResponse:
    """Alle Integrationen des aktuellen Mandanten auflisten.

    Gibt den aktuellen Status und die Konfiguration aller Integrationen zurück,
    einschließlich letztem Sync-Zeitpunkt und nächstem geplantem Sync.
    """
    service = get_integration_sync_service(session)

    try:
        integrations = await service.get_integrations(company_id=company_id)
    except Exception as exc:
        logger.error(
            "integrations_list_failed",
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Integrations-Liste konnte nicht geladen werden.",
        )

    return IntegrationListResponse(
        integrations=integrations,
        total=len(integrations),
    )


@router.get("/dashboard", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> DashboardStatsResponse:
    """Aggregierte Dashboard-Statistiken für alle Integrationen.

    Gibt eine Übersicht über aktive/fehlerhafte Integrationen,
    Fehlerquoten der letzten 24 Stunden und Sync-Kennzahlen zurück.
    """
    service = get_integration_sync_service(session)

    try:
        stats = await service.get_dashboard_stats(company_id=company_id)
    except Exception as exc:
        logger.error(
            "integrations_dashboard_stats_failed",
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard-Statistiken konnten nicht geladen werden.",
        )

    return DashboardStatsResponse(**stats)


@router.get("/health", response_model=HealthStatusResponse)
async def get_health_status(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> HealthStatusResponse:
    """Health-Status aller Integrationen des aktuellen Mandanten.

    Berechnet pro Integration eine Gesundheitsbewertung (healthy/warning/error/inactive)
    basierend auf letztem Sync-Status, Fehlerquoten und Überfälligkeit.
    """
    service = get_integration_sync_service(session)

    try:
        health_list = await service.get_health_status(company_id=company_id)
    except Exception as exc:
        logger.error(
            "integrations_health_check_failed",
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health-Status konnte nicht ermittelt werden.",
        )

    # Gesamt-Gesundheit aus Einzelwerten ableiten
    overall_health = _compute_overall_health(health_list)

    return HealthStatusResponse(
        integrations=health_list,
        overall_health=overall_health,
    )


@router.get("/{integration_type}/history", response_model=SyncHistoryResponse)
async def get_sync_history(
    integration_type: str,
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl zurückgegebener Einträge"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> SyncHistoryResponse:
    """Sync-Verlauf für eine bestimmte Integration.

    Gibt die letzten Sync-Läufe mit Statistiken und Fehlerdetails zurück,
    neueste Einträge zuerst.

    Args:
        integration_type: Integrations-Typ (datev, lexware, banking, slack, email)
        limit: Maximale Anzahl zurückgegebener Einträge
    """
    if integration_type not in INTEGRATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ungültiger Integrations-Typ: '{integration_type}'. "
                f"Erlaubt: {', '.join(INTEGRATION_TYPES)}"
            ),
        )

    service = get_integration_sync_service(session)

    try:
        logs = await service.get_sync_history(
            company_id=company_id,
            integration_type=integration_type,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "integrations_history_failed",
            integration_type=integration_type,
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sync-Verlauf konnte nicht geladen werden.",
        )

    return SyncHistoryResponse(
        logs=logs,
        total=len(logs),
        integration_type=integration_type,
    )


@router.post(
    "/{integration_type}/sync",
    response_model=TriggerSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_manual_sync(
    integration_type: str,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> TriggerSyncResponse:
    """Manuellen Sync für eine bestimmte Integration auslösen.

    Sendet einen Celery-Hintergrund-Task und erstellt einen Sync-Log-Eintrag
    mit Status 'started'. Die Integration muss aktiv sein.

    Args:
        integration_type: Integrations-Typ (datev, lexware, banking, slack, email)
    """
    if integration_type not in INTEGRATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ungültiger Integrations-Typ: '{integration_type}'. "
                f"Erlaubt: {', '.join(INTEGRATION_TYPES)}"
            ),
        )

    service = get_integration_sync_service(session)

    try:
        result = await service.trigger_sync(
            company_id=company_id,
            integration_type=integration_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "integrations_manual_sync_failed",
            integration_type=integration_type,
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Manueller Sync konnte nicht gestartet werden.",
        )

    return TriggerSyncResponse(**result)


@router.patch("/{integration_type}", response_model=Dict)
async def update_integration_config(
    integration_type: str,
    request: UpdateConfigRequest,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    session: AsyncSession = Depends(get_db),
) -> Dict:
    """Konfiguration einer Integration aktualisieren.

    Erlaubt das Aktivieren/Deaktivieren einer Integration,
    das Ändern des Sync-Intervalls, des Anzeigenamens und
    der integrationsspezifischen Konfigurationsdaten.

    Args:
        integration_type: Integrations-Typ (datev, lexware, banking, slack, email)
    """
    if integration_type not in INTEGRATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ungültiger Integrations-Typ: '{integration_type}'. "
                f"Erlaubt: {', '.join(INTEGRATION_TYPES)}"
            ),
        )

    # Prüfen ob mindestens ein Feld gesetzt wurde
    if all(
        v is None
        for v in (
            request.is_active,
            request.sync_interval_minutes,
            request.display_name,
            request.config,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Mindestens ein Feld muss angegeben werden: "
                "is_active, sync_interval_minutes, display_name, config."
            ),
        )

    service = get_integration_sync_service(session)

    try:
        updated = await service.update_config(
            company_id=company_id,
            integration_type=integration_type,
            is_active=request.is_active,
            sync_interval_minutes=request.sync_interval_minutes,
            display_name=request.display_name,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(
            "integrations_config_update_failed",
            integration_type=integration_type,
            company_id=str(company_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Konfiguration konnte nicht aktualisiert werden.",
        )

    return updated


# =============================================================================
# Interne Hilfsfunktionen
# =============================================================================


def _compute_overall_health(health_list: List[Dict]) -> str:
    """Leitet den Gesamt-Health-Level aus den Einzel-Levels ab.

    Regeln:
    - Mindestens ein 'error' -> Gesamt ist 'error'
    - Mindestens ein 'warning' -> Gesamt ist 'warning'
    - Alle 'inactive' -> Gesamt ist 'inactive'
    - Sonst 'healthy'

    Args:
        health_list: Liste der Health-Status-Einträge

    Returns:
        Gesamt-Health-Level: 'healthy' | 'warning' | 'error' | 'inactive'
    """
    if not health_list:
        return "healthy"

    levels = {entry.get("health_level", "inactive") for entry in health_list}

    if "error" in levels:
        return "error"
    if "warning" in levels:
        return "warning"
    if levels == {"inactive"}:
        return "inactive"
    return "healthy"
