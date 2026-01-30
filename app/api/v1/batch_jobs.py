# -*- coding: utf-8 -*-
"""
Batch Jobs API für Ablage-System OCR.

Endpoints für Batch-Job-Verwaltung:
- Status-Abfrage
- Pause/Resume
- Abbrechen
- Auflistung

Feinpoliert und durchdacht - Enterprise-grade Batch Management.
"""

from typing import Optional, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.db.models import User
from app.api.dependencies import get_current_active_user, get_db
from app.services.batch_job_service import get_batch_job_service
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/batch-jobs", tags=["batch-jobs"])


# ==================== Pydantic Models ====================

class BatchJobCreateRequest(BaseModel):
    """Request für Batch-Job-Erstellung."""
    document_ids: List[UUID] = Field(..., min_length=1, max_length=500)
    job_type: str = Field(default="ocr", pattern="^(ocr|embedding|validation)$")
    backend: str = Field(default="auto")
    language: str = Field(default="de", pattern="^(de|en)$")
    priority: int = Field(default=5, ge=1, le=10)
    options: Optional[dict] = None


class BatchJobResponse(BaseModel):
    """Response mit Batch-Job-Details."""
    id: str
    job_type: str
    status: str
    priority: int
    total_documents: int
    processed_documents: int
    failed_documents: int
    successful_documents: int
    progress: int
    current_document: Optional[str]
    message: Optional[str]
    backend: Optional[str]
    language: str
    is_paused: bool
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    estimated_completion: Optional[str]
    remaining_time_seconds: Optional[int]
    avg_time_per_document_ms: Optional[int]
    total_processing_time_ms: Optional[int]
    result_summary: Optional[dict]

    model_config = ConfigDict(from_attributes=True)


class BatchJobListResponse(BaseModel):
    """Response mit Liste von Batch-Jobs."""
    total: int
    batch_jobs: List[BatchJobResponse]


class BatchJobActionResponse(BaseModel):
    """Response nach Batch-Job-Aktion."""
    success: bool
    batch_id: str
    action: str
    message: str


# ==================== Endpoints ====================

@router.post("", response_model=BatchJobResponse, status_code=201)
async def create_batch_job(
    request: BatchJobCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt einen neuen Batch-Job und startet die Verarbeitung.

    Der Batch-Job wird in die Warteschlange eingereiht und
    kann über die Status-API verfolgt werden.

    Maximal 500 Dokumente pro Batch.
    """
    service = get_batch_job_service()

    batch_job = await service.create_batch_job(
        db=db,
        user_id=current_user.id,
        document_ids=request.document_ids,
        job_type=request.job_type,
        backend=request.backend,
        language=request.language,
        priority=request.priority,
        options=request.options
    )

    # Starte Celery-Task basierend auf Job-Typ
    celery_task_id = None
    try:
        if request.job_type == "ocr":
            from app.workers.tasks.ocr_tasks import batch_process_task
            result = batch_process_task.apply_async(
                kwargs={
                    "document_ids": [str(doc_id) for doc_id in request.document_ids],
                    "backend": request.backend,
                    "language": request.language,
                    "batch_job_id": str(batch_job.id),
                    "user_id": str(current_user.id)
                },
                priority=request.priority
            )
            celery_task_id = result.id
        elif request.job_type == "embedding":
            from app.workers.tasks.embedding_tasks import batch_generate_embeddings

            result = batch_generate_embeddings.apply_async(
                kwargs={
                    "document_ids": [str(doc_id) for doc_id in request.document_ids],
                    "batch_job_id": str(batch_job.id)
                },
                priority=request.priority
            )
            celery_task_id = result.id

        # Starte BatchJob mit Celery-Task-ID
        await service.start_batch_job(db, batch_job.id, celery_task_id)

    except Exception as e:
        logger.error(
            "batch_job_celery_start_failed",
            batch_id=str(batch_job.id)[:8],
            **safe_error_log(e)
        )
        # Job bleibt im Status QUEUED, kann manuell gestartet werden

    # Hole detaillierte Informationen
    job_details = await service.get_batch_job(db, batch_job.id, current_user.id)

    logger.info(
        "batch_job_created_api",
        batch_id=str(batch_job.id)[:8],
        user_id=str(current_user.id)[:8],
        total_documents=len(request.document_ids),
        celery_task_id=celery_task_id
    )

    return job_details


@router.get("", response_model=BatchJobListResponse)
async def list_batch_jobs(
    status: Optional[str] = Query(None, description="Nach Status filtern"),
    job_type: Optional[str] = Query(None, description="Nach Job-Typ filtern"),
    limit: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    offset: int = Query(0, ge=0, description="Offset fuer Pagination"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Listet alle Batch-Jobs des aktuellen Benutzers auf.

    Filterbar nach Status und Job-Typ.
    """
    service = get_batch_job_service()

    result = await service.list_batch_jobs(
        db=db,
        user_id=current_user.id,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset
    )

    return result


@router.get("/active", response_model=List[BatchJobResponse])
async def get_active_batch_jobs(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle aktiven (laufenden oder wartenden) Batch-Jobs zurueck.

    Nuetzlich fuer Dashboard-Anzeigen.
    """
    service = get_batch_job_service()
    return await service.get_active_batch_jobs(db, current_user.id)


@router.get("/{batch_id}", response_model=BatchJobResponse)
async def get_batch_job(
    batch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt detaillierte Informationen zu einem Batch-Job zurueck.

    Inklusive Fortschritt, Zeitschaetzung und Ergebnis-Zusammenfassung.
    """
    service = get_batch_job_service()

    job_details = await service.get_batch_job(db, batch_id, current_user.id)

    if not job_details:
        raise HTTPException(
            status_code=404,
            detail="Batch-Job nicht gefunden oder keine Berechtigung"
        )

    return job_details


@router.post("/{batch_id}/pause", response_model=BatchJobActionResponse)
async def pause_batch_job(
    batch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Pausiert einen laufenden Batch-Job.

    Nur Jobs im Status 'processing' koennen pausiert werden.
    Die Verarbeitung wird nach dem aktuellen Dokument angehalten.
    """
    service = get_batch_job_service()

    try:
        batch_job = await service.pause_batch_job(db, batch_id, current_user.id)
        if not batch_job:
            raise HTTPException(
                status_code=404,
                detail="Batch-Job nicht gefunden"
            )

        logger.info(
            "batch_job_paused_api",
            batch_id=str(batch_id)[:8],
            user_id=str(current_user.id)[:8]
        )

        return {
            "success": True,
            "batch_id": str(batch_id),
            "action": "pause",
            "message": f"Batch-Job pausiert nach {batch_job.processed_documents} Dokumenten"
        }

    except PermissionError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_pause_permission_denied", **safe_error_log(e))
        raise HTTPException(status_code=403, detail="Keine Berechtigung fuer diese Aktion")
    except ValueError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_pause_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=400, detail="Ungueltige Anfrage fuer Batch-Pause")


@router.post("/{batch_id}/resume", response_model=BatchJobActionResponse)
async def resume_batch_job(
    batch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Setzt einen pausierten Batch-Job fort.

    Die Verarbeitung wird ab dem letzten Dokument fortgesetzt.
    """
    service = get_batch_job_service()

    try:
        batch_job = await service.resume_batch_job(db, batch_id, current_user.id)
        if not batch_job:
            raise HTTPException(
                status_code=404,
                detail="Batch-Job nicht gefunden"
            )

        logger.info(
            "batch_job_resumed_api",
            batch_id=str(batch_id)[:8],
            user_id=str(current_user.id)[:8]
        )

        return {
            "success": True,
            "batch_id": str(batch_id),
            "action": "resume",
            "message": f"Batch-Job fortgesetzt ab Dokument {batch_job.resume_from_index + 1}"
        }

    except PermissionError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_resume_permission_denied", **safe_error_log(e))
        raise HTTPException(status_code=403, detail="Keine Berechtigung fuer diese Aktion")
    except ValueError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_resume_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=400, detail="Ungueltige Anfrage fuer Batch-Fortsetzung")


@router.post("/{batch_id}/cancel", response_model=BatchJobActionResponse)
async def cancel_batch_job(
    batch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Bricht einen Batch-Job ab.

    Bereits verarbeitete Dokumente bleiben erhalten.
    """
    service = get_batch_job_service()

    try:
        batch_job = await service.cancel_batch_job(db, batch_id, current_user.id)
        if not batch_job:
            raise HTTPException(
                status_code=404,
                detail="Batch-Job nicht gefunden"
            )

        logger.info(
            "batch_job_cancelled_api",
            batch_id=str(batch_id)[:8],
            user_id=str(current_user.id)[:8]
        )

        return {
            "success": True,
            "batch_id": str(batch_id),
            "action": "cancel",
            "message": f"Batch-Job abgebrochen nach {batch_job.processed_documents} Dokumenten"
        }

    except PermissionError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_cancel_permission_denied", **safe_error_log(e))
        raise HTTPException(status_code=403, detail="Keine Berechtigung fuer diese Aktion")
    except ValueError as e:
        # SECURITY FIX 28-17: Generische Fehlermeldung
        logger.warning("batch_cancel_validation_error", **safe_error_log(e))
        raise HTTPException(status_code=400, detail="Ungueltige Anfrage fuer Batch-Abbruch")


@router.get("/{batch_id}/progress")
async def get_batch_job_progress(
    batch_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt kompakten Fortschrittsstatus fuer Echtzeit-Updates zurueck.

    Optimiert fuer haeufiges Polling vom Frontend.
    """
    service = get_batch_job_service()

    job_details = await service.get_batch_job(db, batch_id, current_user.id)

    if not job_details:
        raise HTTPException(
            status_code=404,
            detail="Batch-Job nicht gefunden oder keine Berechtigung"
        )

    return {
        "batch_id": job_details["id"],
        "status": job_details["status"],
        "progress": job_details["progress"],
        "processed": job_details["processed_documents"],
        "total": job_details["total_documents"],
        "failed": job_details["failed_documents"],
        "is_paused": job_details["is_paused"],
        "message": job_details["message"],
        "remaining_time_seconds": job_details["remaining_time_seconds"]
    }
