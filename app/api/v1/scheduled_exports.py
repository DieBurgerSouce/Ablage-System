# -*- coding: utf-8 -*-
"""Scheduled Exports API - Geplante automatische Exports.

Enthaelt:
- CRUD fuer Scheduled Exports
- Manuelle Ausfuehrung
- Aktivierung/Deaktivierung
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

import structlog
from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete, func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User, ScheduledExport, BatchJob, ProcessingStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scheduled-exports", tags=["scheduled-exports"])


# ==============================================================================
# Pydantic Schemas
# ==============================================================================


class ScheduledExportCreate(BaseModel):
    """Request zum Erstellen eines Scheduled Exports."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cron_expression: str = Field(..., min_length=5, max_length=100)
    timezone: str = Field(default="Europe/Berlin")
    export_type: str = Field(..., pattern="^(documents|invoices|datev|training)$")
    export_format: str = Field(..., pattern="^(json|csv|zip|excel|pdf)$")
    filter_config: Optional[dict] = None
    include_text: bool = True
    include_metadata: bool = True
    notify_email: bool = True
    notify_on_failure_only: bool = False
    notification_email: Optional[str] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate cron expression."""
        try:
            croniter(v)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Ungueltiger Cron-Ausdruck: {e}")
        return v


class ScheduledExportUpdate(BaseModel):
    """Request zum Aktualisieren eines Scheduled Exports."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cron_expression: Optional[str] = Field(None, min_length=5, max_length=100)
    timezone: Optional[str] = None
    export_type: Optional[str] = Field(None, pattern="^(documents|invoices|datev|training)$")
    export_format: Optional[str] = Field(None, pattern="^(json|csv|zip|excel|pdf)$")
    filter_config: Optional[dict] = None
    include_text: Optional[bool] = None
    include_metadata: Optional[bool] = None
    is_active: Optional[bool] = None
    notify_email: Optional[bool] = None
    notify_on_failure_only: Optional[bool] = None
    notification_email: Optional[str] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        """Validate cron expression."""
        if v is not None:
            try:
                croniter(v)
            except (ValueError, KeyError) as e:
                raise ValueError(f"Ungueltiger Cron-Ausdruck: {e}")
        return v


class ScheduledExportResponse(BaseModel):
    """Response fuer Scheduled Export."""
    id: UUID
    name: str
    description: Optional[str] = None
    cron_expression: str
    cron_description: Optional[str] = None
    timezone: str
    export_type: str
    export_format: str
    filter_config: Optional[dict] = None
    include_text: bool
    include_metadata: bool
    is_active: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    notify_email: bool
    notify_on_failure_only: bool
    notification_email: Optional[str] = None
    total_runs: int
    successful_runs: int
    failed_runs: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class ScheduledExportListResponse(BaseModel):
    """Liste von Scheduled Exports."""
    exports: List[ScheduledExportResponse]
    total: int


class RunNowResponse(BaseModel):
    """Response nach manueller Ausfuehrung."""
    scheduled_export_id: UUID
    job_id: UUID
    status: str
    message: str


# ==============================================================================
# Helper Functions
# ==============================================================================


def get_cron_description(cron_expr: str) -> str:
    """Generiert eine deutsche Beschreibung des Cron-Ausdrucks."""
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr

    minute, hour, day_of_month, month, day_of_week = parts

    # Einfache Uebersetzungen
    if cron_expr == "0 8 * * 1":
        return "Jeden Montag um 08:00 Uhr"
    elif cron_expr == "0 8 * * *":
        return "Taeglich um 08:00 Uhr"
    elif cron_expr == "0 0 1 * *":
        return "Monatlich am 1. um Mitternacht"
    elif cron_expr == "0 6 * * 1-5":
        return "Werktags um 06:00 Uhr"

    # Generische Beschreibung
    desc_parts = []
    if minute != "*":
        desc_parts.append(f"Minute {minute}")
    if hour != "*":
        desc_parts.append(f"um {hour}:00 Uhr")
    if day_of_month != "*":
        desc_parts.append(f"am {day_of_month}. des Monats")
    if day_of_week != "*":
        days = {"0": "So", "1": "Mo", "2": "Di", "3": "Mi", "4": "Do", "5": "Fr", "6": "Sa"}
        if "-" in day_of_week:
            desc_parts.append(f"an Wochentagen {day_of_week}")
        else:
            desc_parts.append(f"am {days.get(day_of_week, day_of_week)}")

    return ", ".join(desc_parts) if desc_parts else cron_expr


def calculate_next_run(cron_expression: str, tz_name: str = "Europe/Berlin") -> datetime:
    """Berechnet den naechsten Ausfuehrungszeitpunkt."""
    try:
        import pytz
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        cron = croniter(cron_expression, now)
        next_run = cron.get_next(datetime)
        return next_run.astimezone(timezone.utc)
    except Exception:
        # Fallback: UTC
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        return cron.get_next(datetime)


# ==============================================================================
# API Endpoints
# ==============================================================================


@router.post("/", response_model=ScheduledExportResponse, status_code=201)
async def create_scheduled_export(
    request: ScheduledExportCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Neuen Scheduled Export erstellen.

    Args:
        request: Export-Konfiguration

    Returns:
        ScheduledExportResponse
    """
    # Berechne naechsten Ausfuehrungszeitpunkt
    next_run = calculate_next_run(request.cron_expression, request.timezone)

    scheduled_export = ScheduledExport(
        id=uuid4(),
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        cron_expression=request.cron_expression,
        timezone=request.timezone,
        export_type=request.export_type,
        export_format=request.export_format,
        filter_config=request.filter_config,
        include_text=request.include_text,
        include_metadata=request.include_metadata,
        is_active=True,
        next_run_at=next_run,
        notify_email=request.notify_email,
        notify_on_failure_only=request.notify_on_failure_only,
        notification_email=request.notification_email,
    )

    db.add(scheduled_export)
    await db.commit()
    await db.refresh(scheduled_export)

    logger.info(
        "scheduled_export_created",
        export_id=str(scheduled_export.id),
        user_id=str(current_user.id),
        cron=request.cron_expression,
        next_run=str(next_run),
    )

    return ScheduledExportResponse(
        id=scheduled_export.id,
        name=scheduled_export.name,
        description=scheduled_export.description,
        cron_expression=scheduled_export.cron_expression,
        cron_description=get_cron_description(scheduled_export.cron_expression),
        timezone=scheduled_export.timezone,
        export_type=scheduled_export.export_type,
        export_format=scheduled_export.export_format,
        filter_config=scheduled_export.filter_config,
        include_text=scheduled_export.include_text,
        include_metadata=scheduled_export.include_metadata,
        is_active=scheduled_export.is_active,
        next_run_at=scheduled_export.next_run_at,
        notify_email=scheduled_export.notify_email,
        notify_on_failure_only=scheduled_export.notify_on_failure_only,
        notification_email=scheduled_export.notification_email,
        total_runs=0,
        successful_runs=0,
        failed_runs=0,
        created_at=scheduled_export.created_at,
    )


@router.get("/", response_model=ScheduledExportListResponse)
async def list_scheduled_exports(
    is_active: Optional[bool] = Query(None, description="Filter nach aktiv/inaktiv"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste aller Scheduled Exports des Benutzers.

    Args:
        is_active: Optional Filter nach aktiv/inaktiv
        limit: Maximale Anzahl
        offset: Offset fuer Pagination

    Returns:
        ScheduledExportListResponse
    """
    query = select(ScheduledExport).where(ScheduledExport.user_id == current_user.id)

    if is_active is not None:
        query = query.where(ScheduledExport.is_active == is_active)

    query = query.order_by(ScheduledExport.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    exports = result.scalars().all()

    # Count total
    count_query = select(sql_func.count()).select_from(ScheduledExport).where(
        ScheduledExport.user_id == current_user.id
    )
    if is_active is not None:
        count_query = count_query.where(ScheduledExport.is_active == is_active)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    export_responses = [
        ScheduledExportResponse(
            id=exp.id,
            name=exp.name,
            description=exp.description,
            cron_expression=exp.cron_expression,
            cron_description=get_cron_description(exp.cron_expression),
            timezone=exp.timezone,
            export_type=exp.export_type,
            export_format=exp.export_format,
            filter_config=exp.filter_config,
            include_text=exp.include_text,
            include_metadata=exp.include_metadata,
            is_active=exp.is_active,
            last_run_at=exp.last_run_at,
            next_run_at=exp.next_run_at,
            last_run_status=exp.last_run_status,
            notify_email=exp.notify_email,
            notify_on_failure_only=exp.notify_on_failure_only,
            notification_email=exp.notification_email,
            total_runs=exp.total_runs or 0,
            successful_runs=exp.successful_runs or 0,
            failed_runs=exp.failed_runs or 0,
            created_at=exp.created_at,
            updated_at=exp.updated_at,
        )
        for exp in exports
    ]

    return ScheduledExportListResponse(exports=export_responses, total=total)


@router.get("/{export_id}", response_model=ScheduledExportResponse)
async def get_scheduled_export(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Scheduled Export nach ID abrufen.

    Args:
        export_id: ScheduledExport UUID

    Returns:
        ScheduledExportResponse
    """
    result = await db.execute(
        select(ScheduledExport).where(
            ScheduledExport.id == export_id,
            ScheduledExport.user_id == current_user.id,
        )
    )
    exp = result.scalar_one_or_none()

    if not exp:
        raise HTTPException(
            status_code=404,
            detail="Scheduled Export nicht gefunden oder keine Berechtigung",
        )

    return ScheduledExportResponse(
        id=exp.id,
        name=exp.name,
        description=exp.description,
        cron_expression=exp.cron_expression,
        cron_description=get_cron_description(exp.cron_expression),
        timezone=exp.timezone,
        export_type=exp.export_type,
        export_format=exp.export_format,
        filter_config=exp.filter_config,
        include_text=exp.include_text,
        include_metadata=exp.include_metadata,
        is_active=exp.is_active,
        last_run_at=exp.last_run_at,
        next_run_at=exp.next_run_at,
        last_run_status=exp.last_run_status,
        notify_email=exp.notify_email,
        notify_on_failure_only=exp.notify_on_failure_only,
        notification_email=exp.notification_email,
        total_runs=exp.total_runs or 0,
        successful_runs=exp.successful_runs or 0,
        failed_runs=exp.failed_runs or 0,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )


@router.put("/{export_id}", response_model=ScheduledExportResponse)
async def update_scheduled_export(
    export_id: UUID,
    request: ScheduledExportUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Scheduled Export aktualisieren.

    Args:
        export_id: ScheduledExport UUID
        request: Update-Daten

    Returns:
        ScheduledExportResponse
    """
    result = await db.execute(
        select(ScheduledExport).where(
            ScheduledExport.id == export_id,
            ScheduledExport.user_id == current_user.id,
        )
    )
    exp = result.scalar_one_or_none()

    if not exp:
        raise HTTPException(
            status_code=404,
            detail="Scheduled Export nicht gefunden oder keine Berechtigung",
        )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(exp, field, value)

    # Recalculate next run if cron changed
    if request.cron_expression or request.timezone:
        exp.next_run_at = calculate_next_run(
            exp.cron_expression,
            exp.timezone,
        )

    exp.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(exp)

    logger.info(
        "scheduled_export_updated",
        export_id=str(export_id),
        user_id=str(current_user.id),
    )

    return ScheduledExportResponse(
        id=exp.id,
        name=exp.name,
        description=exp.description,
        cron_expression=exp.cron_expression,
        cron_description=get_cron_description(exp.cron_expression),
        timezone=exp.timezone,
        export_type=exp.export_type,
        export_format=exp.export_format,
        filter_config=exp.filter_config,
        include_text=exp.include_text,
        include_metadata=exp.include_metadata,
        is_active=exp.is_active,
        last_run_at=exp.last_run_at,
        next_run_at=exp.next_run_at,
        last_run_status=exp.last_run_status,
        notify_email=exp.notify_email,
        notify_on_failure_only=exp.notify_on_failure_only,
        notification_email=exp.notification_email,
        total_runs=exp.total_runs or 0,
        successful_runs=exp.successful_runs or 0,
        failed_runs=exp.failed_runs or 0,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )


@router.delete("/{export_id}", status_code=204)
async def delete_scheduled_export(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Scheduled Export loeschen.

    Args:
        export_id: ScheduledExport UUID
    """
    result = await db.execute(
        select(ScheduledExport).where(
            ScheduledExport.id == export_id,
            ScheduledExport.user_id == current_user.id,
        )
    )
    exp = result.scalar_one_or_none()

    if not exp:
        raise HTTPException(
            status_code=404,
            detail="Scheduled Export nicht gefunden oder keine Berechtigung",
        )

    await db.execute(
        delete(ScheduledExport).where(ScheduledExport.id == export_id)
    )
    await db.commit()

    logger.info(
        "scheduled_export_deleted",
        export_id=str(export_id),
        user_id=str(current_user.id),
    )


@router.post("/{export_id}/run-now", response_model=RunNowResponse)
async def run_scheduled_export_now(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Scheduled Export jetzt manuell ausfuehren.

    Args:
        export_id: ScheduledExport UUID

    Returns:
        RunNowResponse mit Job-ID
    """
    result = await db.execute(
        select(ScheduledExport).where(
            ScheduledExport.id == export_id,
            ScheduledExport.user_id == current_user.id,
        )
    )
    exp = result.scalar_one_or_none()

    if not exp:
        raise HTTPException(
            status_code=404,
            detail="Scheduled Export nicht gefunden oder keine Berechtigung",
        )

    # Start export job
    from app.workers.tasks.export_tasks import run_scheduled_export_task

    job_id = uuid4()

    # Create BatchJob
    batch_job = BatchJob(
        id=job_id,
        user_id=current_user.id,
        job_type="export",
        status=ProcessingStatus.QUEUED,
        priority=5,
        message=f"Manueller Export: {exp.name}",
        options={
            "scheduled_export_id": str(exp.id),
            "format": exp.export_format,
            "export_type": exp.export_type,
            "include_text": exp.include_text,
            "include_metadata": exp.include_metadata,
            "filter_config": exp.filter_config,
        },
    )

    db.add(batch_job)
    await db.commit()

    # Trigger Celery task
    run_scheduled_export_task.delay(
        scheduled_export_id=str(exp.id),
        job_id=str(job_id),
        user_id=str(current_user.id),
        manual=True,
    )

    logger.info(
        "scheduled_export_manual_run",
        export_id=str(export_id),
        job_id=str(job_id),
        user_id=str(current_user.id),
    )

    return RunNowResponse(
        scheduled_export_id=export_id,
        job_id=job_id,
        status="queued",
        message=f"Export '{exp.name}' wurde gestartet",
    )


@router.post("/{export_id}/toggle", response_model=ScheduledExportResponse)
async def toggle_scheduled_export(
    export_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Scheduled Export aktivieren/deaktivieren.

    Args:
        export_id: ScheduledExport UUID

    Returns:
        ScheduledExportResponse
    """
    result = await db.execute(
        select(ScheduledExport).where(
            ScheduledExport.id == export_id,
            ScheduledExport.user_id == current_user.id,
        )
    )
    exp = result.scalar_one_or_none()

    if not exp:
        raise HTTPException(
            status_code=404,
            detail="Scheduled Export nicht gefunden oder keine Berechtigung",
        )

    exp.is_active = not exp.is_active

    if exp.is_active:
        # Recalculate next run
        exp.next_run_at = calculate_next_run(exp.cron_expression, exp.timezone)

    exp.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(exp)

    status_text = "aktiviert" if exp.is_active else "deaktiviert"
    logger.info(
        f"scheduled_export_{status_text}",
        export_id=str(export_id),
        user_id=str(current_user.id),
    )

    return ScheduledExportResponse(
        id=exp.id,
        name=exp.name,
        description=exp.description,
        cron_expression=exp.cron_expression,
        cron_description=get_cron_description(exp.cron_expression),
        timezone=exp.timezone,
        export_type=exp.export_type,
        export_format=exp.export_format,
        filter_config=exp.filter_config,
        include_text=exp.include_text,
        include_metadata=exp.include_metadata,
        is_active=exp.is_active,
        last_run_at=exp.last_run_at,
        next_run_at=exp.next_run_at,
        last_run_status=exp.last_run_status,
        notify_email=exp.notify_email,
        notify_on_failure_only=exp.notify_on_failure_only,
        notification_email=exp.notification_email,
        total_runs=exp.total_runs or 0,
        successful_runs=exp.successful_runs or 0,
        failed_runs=exp.failed_runs or 0,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )
