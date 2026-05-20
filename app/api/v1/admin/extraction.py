# -*- coding: utf-8 -*-
"""
Admin API für Strukturierte Extraktion.

Endpoints für:
- Batch-Reprocessing aller Dokumente
- Task-Status abfragen
- Extraktions-Statistiken

Nur für Administratoren.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_superuser, get_db
from app.db import models
from app.workers.tasks.extraction_tasks import (
    reprocess_all_documents_structured_extraction,
    reprocess_single_document,
    generate_extraction_stats,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/extraction", tags=["Admin - Extraktion"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================


class BatchReprocessRequest(BaseModel):
    """Request für Batch-Reprocessing."""

    batch_size: int = Field(100, ge=10, le=500, description="Dokumente pro Batch")
    document_type_filter: Optional[str] = Field(
        None, description="Nur bestimmte Dokumenttypen (invoice, order, contract)"
    )
    skip_already_processed: bool = Field(
        True, description="Bereits verarbeitete überspringen"
    )


class TaskResponse(BaseModel):
    """Antwort mit Task-ID."""

    task_id: str
    status: str
    message: str
    started_at: datetime


class TaskStatusResponse(BaseModel):
    """Task-Status Antwort."""

    task_id: str
    status: str
    progress: Optional[JSONDict] = None
    result: Optional[JSONDict] = None
    error: Optional[str] = None


class ExtractionStatsResponse(BaseModel):
    """Extraktions-Statistiken."""

    total_documents: int
    with_extraction: int
    extraction_rate: float
    by_type: Dict[str, int]
    avg_confidence: float
    needs_review_count: int
    with_line_items: int
    invoice_stats: JSONDict
    generated_at: datetime


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post(
    "/reprocess-all",
    response_model=TaskResponse,
    status_code=202,
    summary="Batch-Reprocessing starten",
    description="Startet Batch-Reprocessing aller Dokumente für strukturierte Extraktion. "
                "Langlaeufer Task, der im Hintergrund ausgeführt wird."
)
async def trigger_batch_reprocessing(
    request: BatchReprocessRequest,
    current_user: models.User = Depends(get_current_superuser),
) -> TaskResponse:
    """
    Startet Batch-Reprocessing aller Dokumente für strukturierte Extraktion.

    **Nur für Administratoren.**

    Dies ist ein langlaeufer Task, der im Hintergrund ausgeführt wird.
    Nutze GET /admin/extraction/reprocess-status/{task_id} um den Status abzufragen.

    **Parameter:**
    - batch_size: Dokumente pro Batch (10-500, default 100)
    - document_type_filter: Nur bestimmte Typen (optional)
    - skip_already_processed: Bereits verarbeitete überspringen (default True)
    """
    logger.info(
        "batch_reprocessing_triggered",
        user_id=str(current_user.id),
        user_email=current_user.email,
        batch_size=request.batch_size,
        document_type_filter=request.document_type_filter,
        skip_already_processed=request.skip_already_processed,
    )

    # Task starten
    task = reprocess_all_documents_structured_extraction.delay(
        batch_size=request.batch_size,
        document_type_filter=request.document_type_filter,
        skip_already_processed=request.skip_already_processed,
    )

    return TaskResponse(
        task_id=task.id,
        status="QUEUED",
        message=(
            f"Batch-Reprocessing gestartet. "
            f"Batch-Größe: {request.batch_size}, "
            f"Skip bereits verarbeitet: {request.skip_already_processed}"
        ),
        started_at=datetime.now(timezone.utc),
    )


@router.get(
    "/reprocess-status/{task_id}",
    response_model=TaskStatusResponse,
    summary="Reprocessing-Status abrufen",
    description="Ruft den Status eines Batch-Reprocessing Tasks ab"
)
async def get_reprocessing_status(
    task_id: str,
    current_user: models.User = Depends(get_current_superuser),
) -> TaskStatusResponse:
    """
    Status eines Batch-Reprocessing Tasks abfragen.

    **Status-Werte:**
    - PENDING: Task wartet auf Ausführung
    - PROGRESS: Task wird ausgeführt (mit Fortschritt in progress)
    - SUCCESS: Task erfolgreich abgeschlossen
    - FAILURE: Task fehlgeschlagen
    """
    result = AsyncResult(task_id)

    response = TaskStatusResponse(
        task_id=task_id,
        status=result.status,
    )

    if result.status == "PROGRESS":
        response.progress = result.info
    elif result.status == "SUCCESS":
        response.result = result.result
    elif result.status == "FAILURE":
        response.error = str(result.result) if result.result else "Unbekannter Fehler"

    return response


@router.post(
    "/reprocess-document/{document_id}",
    response_model=TaskResponse,
    summary="Einzeldokument reprocessen",
    description="Startet Reprocessing eines einzelnen Dokuments für strukturierte Extraktion"
)
async def trigger_single_document_reprocessing(
    document_id: UUID,
    current_user: models.User = Depends(get_current_superuser),
) -> TaskResponse:
    """
    Einzelnes Dokument für strukturierte Extraktion reprocessen.

    **Nur für Administratoren.**
    """
    logger.info(
        "single_document_reprocessing_triggered",
        user_id=str(current_user.id),
        document_id=str(document_id),
    )

    task = reprocess_single_document.delay(str(document_id))

    return TaskResponse(
        task_id=task.id,
        status="QUEUED",
        message=f"Reprocessing für Dokument {document_id} gestartet",
        started_at=datetime.now(timezone.utc),
    )


@router.get(
    "/stats",
    response_model=ExtractionStatsResponse,
    summary="Extraktions-Statistiken",
    description="Ruft aktuelle Statistiken zur strukturierten Extraktion ab"
)
async def get_extraction_statistics(
    refresh: bool = Query(False, description="Cache ignorieren und neu berechnen"),
    current_user: models.User = Depends(get_current_superuser),
) -> ExtractionStatsResponse:
    """
    Aktuelle Statistiken zur strukturierten Extraktion abrufen.

    **Nur für Administratoren.**

    **Enthält:**
    - Gesamtzahl Dokumente
    - Anzahl mit Extraktion
    - Aufschluesselung nach Dokumenttyp
    - Durchschnittliche Konfidenz
    - Anzahl mit Review-Bedarf
    """
    if refresh:
        # Task synchron ausführen (für Admin OK)
        task = generate_extraction_stats.delay()
        result = task.get(timeout=60)
    else:
        # Direkt ausführen (schneller für Dashboard)
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from app.workers.tasks.extraction_tasks import _async_generate_stats

            result = loop.run_until_complete(_async_generate_stats())
        finally:
            loop.close()

    return ExtractionStatsResponse(
        total_documents=result["total_documents"],
        with_extraction=result["with_extraction"],
        extraction_rate=result["extraction_rate"],
        by_type=result["by_type"],
        avg_confidence=result["avg_confidence"],
        needs_review_count=result["needs_review_count"],
        with_line_items=result["with_line_items"],
        invoice_stats=result["invoice_stats"],
        generated_at=datetime.fromisoformat(result["generated_at"]),
    )


@router.post(
    "/cancel-reprocess/{task_id}",
    summary="Reprocessing abbrechen",
    description="Bricht einen laufenden Batch-Reprocessing Task ab"
)
async def cancel_reprocessing_task(
    task_id: str,
    current_user: models.User = Depends(get_current_superuser),
) -> JSONDict:
    """
    Laufenden Batch-Reprocessing Task abbrechen.

    **Nur für Administratoren.**

    Hinweis: Der Task wird erst beim nächsten Batch-Check abgebrochen.
    """
    from app.workers.celery_app import celery_app

    celery_app.control.revoke(task_id, terminate=True)

    logger.warning(
        "batch_reprocessing_cancelled",
        task_id=task_id,
        cancelled_by=str(current_user.id),
    )

    return {
        "success": True,
        "message": f"Task {task_id} zum Abbruch markiert",
        "task_id": task_id,
    }
