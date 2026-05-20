# -*- coding: utf-8 -*-
"""
CDC Admin-API - Change Data Capture Verwaltung.

Admin-Endpoints fuer Ueberwachung und Steuerung der CDC-Infrastruktur.
Nur fuer System-Administratoren zugaenglich.
"""

import structlog
from datetime import datetime
from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_superuser, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import User
from app.services.cdc.cdc_service import CDCService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/cdc", tags=["cdc-admin"])


# =============================================================================
# Pydantic Response Models
# =============================================================================


class CDCConsumerResponse(BaseModel):
    """Response-Modell fuer einen CDC-Consumer."""

    id: UUID
    consumer_name: str
    last_sequence_number: int
    last_processed_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    config: Dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CDCEventResponse(BaseModel):
    """Response-Modell fuer ein CDC-Event."""

    id: UUID
    source_table: str
    source_id: UUID
    operation: str
    old_data: Optional[Dict[str, object]] = None
    new_data: Optional[Dict[str, object]] = None
    changed_columns: List[str] = Field(default_factory=list)
    sequence_number: int
    processed: bool
    processed_at: Optional[datetime] = None
    consumer_id: Optional[str] = None
    company_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    transaction_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CDCEventListResponse(BaseModel):
    """Paginierte Liste von CDC-Events."""

    events: List[CDCEventResponse]
    total: int
    limit: int
    offset: int


class CDCCleanupResponse(BaseModel):
    """Response fuer CDC-Bereinigung."""

    deleted_count: int
    cutoff_days: int
    message: str


class CDCConsumerActionResponse(BaseModel):
    """Response fuer Consumer-Aktionen (Pause/Fortsetzen)."""

    consumer_name: str
    status: str
    message: str


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/consumers",
    response_model=List[CDCConsumerResponse],
    summary="CDC-Consumer auflisten",
    description="Listet alle registrierten CDC-Consumer mit Status und Offset auf.",
)
async def list_consumers(
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> List[CDCConsumerResponse]:
    """Listet alle registrierten CDC-Consumer auf."""
    try:
        service = CDCService(db)
        consumers = await service.get_all_consumers()

        logger.info(
            "cdc_consumer_aufgelistet",
            admin_user_id=str(current_user.id),
            consumer_count=len(consumers),
        )

        return [
            CDCConsumerResponse(
                id=c.id,
                consumer_name=c.consumer_name,
                last_sequence_number=c.last_sequence_number or 0,
                last_processed_at=c.last_processed_at,
                status=c.status,
                error_message=c.error_message,
                config=c.config or {},
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in consumers
        ]
    except Exception as e:
        logger.error("cdc_consumer_liste_fehler", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der CDC-Consumer",
        )


@router.get(
    "/events",
    response_model=CDCEventListResponse,
    summary="CDC-Events auflisten",
    description=(
        "Listet CDC-Events auf mit optionaler Filterung nach Tabelle, "
        "Verarbeitungsstatus und Pagination."
    ),
)
async def list_events(
    source_table: Optional[str] = Query(
        None,
        description="Filter nach Quell-Tabelle",
    ),
    processed: Optional[bool] = Query(
        None,
        description="Filter nach Verarbeitungsstatus",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximale Anzahl"),
    offset: int = Query(0, ge=0, description="Offset fuer Pagination"),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CDCEventListResponse:
    """Listet CDC-Events mit Filterung und Pagination auf."""
    try:
        from sqlalchemy import select, func, and_
        from app.db.models_cdc import ChangeDataCaptureLog

        # Query aufbauen
        base_filter = []
        if source_table is not None:
            base_filter.append(
                ChangeDataCaptureLog.source_table == source_table
            )
        if processed is not None:
            base_filter.append(
                ChangeDataCaptureLog.processed == processed
            )

        # Gesamtanzahl ermitteln
        count_stmt = select(func.count(ChangeDataCaptureLog.id))
        if base_filter:
            count_stmt = count_stmt.where(and_(*base_filter))
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Events abrufen
        events_stmt = (
            select(ChangeDataCaptureLog)
            .order_by(ChangeDataCaptureLog.sequence_number.desc())
            .limit(limit)
            .offset(offset)
        )
        if base_filter:
            events_stmt = events_stmt.where(and_(*base_filter))

        events_result = await db.execute(events_stmt)
        events = list(events_result.scalars().all())

        logger.info(
            "cdc_events_aufgelistet",
            admin_user_id=str(current_user.id),
            total=total,
            returned=len(events),
            source_table=source_table,
        )

        return CDCEventListResponse(
            events=[
                CDCEventResponse(
                    id=e.id,
                    source_table=e.source_table,
                    source_id=e.source_id,
                    operation=e.operation,
                    old_data=e.old_data,
                    new_data=e.new_data,
                    changed_columns=e.changed_columns or [],
                    sequence_number=e.sequence_number,
                    processed=e.processed,
                    processed_at=e.processed_at,
                    consumer_id=e.consumer_id,
                    company_id=e.company_id,
                    user_id=e.user_id,
                    transaction_id=e.transaction_id,
                    created_at=e.created_at,
                )
                for e in events
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error("cdc_events_liste_fehler", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der CDC-Events",
        )


@router.post(
    "/consumers/{name}/pause",
    response_model=CDCConsumerActionResponse,
    summary="CDC-Consumer pausieren",
    description="Pausiert einen aktiven CDC-Consumer.",
)
async def pause_consumer(
    name: str,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CDCConsumerActionResponse:
    """Pausiert einen CDC-Consumer."""
    try:
        service = CDCService(db)
        success = await service.pause_consumer(name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consumer '{name}' nicht gefunden",
            )

        await db.commit()

        logger.info(
            "cdc_consumer_pausiert_admin",
            admin_user_id=str(current_user.id),
            consumer_name=name,
        )

        return CDCConsumerActionResponse(
            consumer_name=name,
            status="paused",
            message=f"Consumer '{name}' wurde pausiert",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("cdc_consumer_pause_fehler", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Pausieren des Consumers",
        )


@router.post(
    "/consumers/{name}/resume",
    response_model=CDCConsumerActionResponse,
    summary="CDC-Consumer fortsetzen",
    description="Setzt einen pausierten CDC-Consumer fort.",
)
async def resume_consumer(
    name: str,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CDCConsumerActionResponse:
    """Setzt einen pausierten CDC-Consumer fort."""
    try:
        service = CDCService(db)
        success = await service.resume_consumer(name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consumer '{name}' nicht gefunden",
            )

        await db.commit()

        logger.info(
            "cdc_consumer_fortgesetzt_admin",
            admin_user_id=str(current_user.id),
            consumer_name=name,
        )

        return CDCConsumerActionResponse(
            consumer_name=name,
            status="active",
            message=f"Consumer '{name}' wurde fortgesetzt",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("cdc_consumer_resume_fehler", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Fortsetzen des Consumers",
        )


@router.delete(
    "/events/cleanup",
    response_model=CDCCleanupResponse,
    summary="Alte CDC-Events bereinigen",
    description=(
        "Loescht verarbeitete CDC-Events, die aelter als die angegebene "
        "Anzahl Tage sind. Standard: 90 Tage."
    ),
)
async def cleanup_events(
    days: int = Query(
        90,
        ge=1,
        le=365,
        description="Mindestalter in Tagen fuer Loeschung",
    ),
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> CDCCleanupResponse:
    """Bereinigt alte verarbeitete CDC-Events."""
    try:
        service = CDCService(db)
        deleted_count = await service.cleanup_old_events(days=days)
        await db.commit()

        logger.info(
            "cdc_bereinigung_admin",
            admin_user_id=str(current_user.id),
            deleted_count=deleted_count,
            cutoff_days=days,
        )

        return CDCCleanupResponse(
            deleted_count=deleted_count,
            cutoff_days=days,
            message=(
                f"{deleted_count} verarbeitete Events "
                f"aelter als {days} Tage geloescht"
            ),
        )
    except Exception as e:
        logger.error("cdc_bereinigung_fehler", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der CDC-Bereinigung",
        )
