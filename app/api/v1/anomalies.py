# -*- coding: utf-8 -*-
"""
API Endpoints fuer Anomalie-Erkennung.

Anomalie-Management:
- Anomalien auflisten (paginiert, filterbar)
- Dashboard-Statistiken
- Manuellen Scan ausloesen
- Status aktualisieren (aufloesen/Fehlalarm)
- Anomalie-Details abrufen

Phase 2.3 der Feature-Roadmap (Februar 2026).
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.middleware.company_context import require_company
from app.db.models import User, Company
from app.db.models_anomaly import Anomaly, AnomalyStatus
from app.services.anomaly.anomaly_detection_service import (
    get_anomaly_detection_service,
)
from app.core.safe_errors import safe_error_log

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/anomalies", tags=["Anomalie-Erkennung"])


# ============================================================================
# Schemas
# ============================================================================


class AnomalyResponse(BaseModel):
    """Antwort-Schema fuer eine einzelne Anomalie."""

    id: str
    rule_id: Optional[str] = None
    anomaly_type: str
    severity: str
    title: str
    description: Optional[str] = None
    source_table: str
    source_id: str
    related_ids: List[str] = Field(default_factory=list)
    score: float
    details: Dict[str, object] = Field(default_factory=dict)
    status: str
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    company_id: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AnomalyListResponse(BaseModel):
    """Paginierte Liste von Anomalien."""

    items: List[AnomalyResponse]
    total: int
    page: int
    page_size: int


class AnomalyStatsResponse(BaseModel):
    """Dashboard-Statistiken fuer Anomalien."""

    total: int = 0
    open: int = 0
    investigating: int = 0
    resolved: int = 0
    false_positive: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)


class AnomalyUpdateRequest(BaseModel):
    """Request zum Aktualisieren des Anomalie-Status."""

    status: str = Field(
        ...,
        description=(
            "Neuer Status: 'investigating', 'resolved' oder "
            "'false_positive'"
        ),
    )
    resolution_note: Optional[str] = Field(
        default=None,
        description="Optionale Begruendung",
        max_length=2000,
    )


class ScanResultResponse(BaseModel):
    """Ergebnis eines manuellen Anomalie-Scans."""

    success: bool
    message: str
    anomalies_found: int
    task_id: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=AnomalyListResponse,
    summary="Anomalien auflisten",
    description=(
        "Gibt eine paginierte und filterbare Liste aller Anomalien "
        "fuer den aktuellen Mandanten zurueck."
    ),
)
async def list_anomalies(
    page: int = Query(default=1, ge=1, description="Seitennummer"),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Eintraege pro Seite"
    ),
    anomaly_type: Optional[str] = Query(
        default=None,
        description=(
            "Filter nach Anomalie-Typ "
            "(duplicate_invoice, amount_outlier, etc.)"
        ),
    ),
    severity: Optional[str] = Query(
        default=None,
        description="Filter nach Schweregrad (info, warning, critical)",
    ),
    anomaly_status: Optional[str] = Query(
        default=None,
        alias="status",
        description=(
            "Filter nach Status "
            "(open, investigating, resolved, false_positive)"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AnomalyListResponse:
    """Hole alle Anomalien (paginiert und filterbar)."""
    conditions = [Anomaly.company_id == company.id]

    if anomaly_type:
        conditions.append(Anomaly.anomaly_type == anomaly_type)
    if severity:
        conditions.append(Anomaly.severity == severity)
    if anomaly_status:
        conditions.append(Anomaly.status == anomaly_status)

    # Gesamtanzahl
    count_stmt = (
        select(func.count(Anomaly.id)).where(and_(*conditions))
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Paginierte Ergebnisse
    offset = (page - 1) * page_size
    data_stmt = (
        select(Anomaly)
        .where(and_(*conditions))
        .order_by(Anomaly.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    data_result = await db.execute(data_stmt)
    anomalies = data_result.scalars().all()

    items = [
        AnomalyResponse(
            id=str(a.id),
            rule_id=str(a.rule_id) if a.rule_id else None,
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            title=a.title,
            description=a.description,
            source_table=a.source_table,
            source_id=str(a.source_id),
            related_ids=a.related_ids or [],
            score=a.score or 0.0,
            details=a.details or {},
            status=a.status,
            resolved_at=a.resolved_at,
            resolution_note=a.resolution_note,
            company_id=str(a.company_id),
            created_at=a.created_at,
        )
        for a in anomalies
    ]

    return AnomalyListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/stats",
    response_model=AnomalyStatsResponse,
    summary="Anomalie-Statistiken",
    description="Dashboard-Statistiken fuer die Anomalie-Erkennung.",
)
async def get_anomaly_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AnomalyStatsResponse:
    """Hole Anomalie-Statistiken fuer das Dashboard."""
    service = get_anomaly_detection_service(db)
    stats = await service.get_anomaly_stats(company.id)

    return AnomalyStatsResponse(
        total=stats.get("total", 0),
        open=stats.get("open", 0),
        investigating=stats.get("investigating", 0),
        resolved=stats.get("resolved", 0),
        false_positive=stats.get("false_positive", 0),
        by_type=stats.get("by_type", {}),
        by_severity=stats.get("by_severity", {}),
    )


@router.post(
    "/scan",
    response_model=ScanResultResponse,
    summary="Manuellen Scan ausloesen",
    description=(
        "Loest eine manuelle Anomalie-Pruefung fuer den aktuellen "
        "Mandanten aus."
    ),
)
async def trigger_anomaly_scan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ScanResultResponse:
    """Starte einen manuellen Anomalie-Scan."""
    try:
        service = get_anomaly_detection_service(db)
        anomalies = await service.run_all_checks(company.id)
        await db.commit()

        return ScanResultResponse(
            success=True,
            message=(
                f"Scan abgeschlossen. {len(anomalies)} "
                f"Anomalie(n) erkannt."
            ),
            anomalies_found=len(anomalies),
        )
    except Exception as exc:
        logger.error(
            "manual_anomaly_scan_failed",
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Anomalie-Scan fehlgeschlagen. Bitte versuchen Sie es spaeter erneut.",
        )


@router.patch(
    "/{anomaly_id}",
    response_model=AnomalyResponse,
    summary="Anomalie-Status aktualisieren",
    description=(
        "Aktualisiert den Status einer Anomalie "
        "(aufloesen, als Fehlalarm markieren, untersuchen)."
    ),
)
async def update_anomaly_status(
    anomaly_id: UUID,
    request: AnomalyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AnomalyResponse:
    """Aktualisiere den Status einer Anomalie."""
    # Validierung: Status muss gueltig sein
    valid_statuses = {"investigating", "resolved", "false_positive"}
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ungueltiger Status '{request.status}'. "
                f"Erlaubt: {', '.join(sorted(valid_statuses))}"
            ),
        )

    service = get_anomaly_detection_service(db)

    try:
        anomaly = await service.resolve_anomaly(
            anomaly_id=anomaly_id,
            user_id=current_user.id,
            status=request.status,
            note=request.resolution_note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Mandanten-Check
    if anomaly.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomalie nicht gefunden.",
        )

    await db.commit()

    return AnomalyResponse(
        id=str(anomaly.id),
        rule_id=str(anomaly.rule_id) if anomaly.rule_id else None,
        anomaly_type=anomaly.anomaly_type,
        severity=anomaly.severity,
        title=anomaly.title,
        description=anomaly.description,
        source_table=anomaly.source_table,
        source_id=str(anomaly.source_id),
        related_ids=anomaly.related_ids or [],
        score=anomaly.score or 0.0,
        details=anomaly.details or {},
        status=anomaly.status,
        resolved_at=anomaly.resolved_at,
        resolution_note=anomaly.resolution_note,
        company_id=str(anomaly.company_id),
        created_at=anomaly.created_at,
    )


@router.get(
    "/{anomaly_id}",
    response_model=AnomalyResponse,
    summary="Anomalie-Details",
    description=(
        "Gibt die Details einer einzelnen Anomalie zurueck, "
        "inkl. verknuepfter Entitaeten."
    ),
)
async def get_anomaly_detail(
    anomaly_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AnomalyResponse:
    """Hole Details einer einzelnen Anomalie."""
    stmt = (
        select(Anomaly)
        .where(
            and_(
                Anomaly.id == anomaly_id,
                Anomaly.company_id == company.id,
            )
        )
    )
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomalie nicht gefunden.",
        )

    return AnomalyResponse(
        id=str(anomaly.id),
        rule_id=str(anomaly.rule_id) if anomaly.rule_id else None,
        anomaly_type=anomaly.anomaly_type,
        severity=anomaly.severity,
        title=anomaly.title,
        description=anomaly.description,
        source_table=anomaly.source_table,
        source_id=str(anomaly.source_id),
        related_ids=anomaly.related_ids or [],
        score=anomaly.score or 0.0,
        details=anomaly.details or {},
        status=anomaly.status,
        resolved_at=anomaly.resolved_at,
        resolution_note=anomaly.resolution_note,
        company_id=str(anomaly.company_id),
        created_at=anomaly.created_at,
    )
