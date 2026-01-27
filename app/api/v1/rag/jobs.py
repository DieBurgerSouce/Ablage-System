"""RAG Batch Jobs API Endpoints.

Verwaltung von RAG Batch-Operationen:
- Job-Status abfragen
- Jobs starten
- Jobs abbrechen
- Job-History
"""

import structlog
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.models import User, RAGBatchJob, RAGBatchJobStatus, RAGBatchJobType
from app.api.dependencies import get_current_user, get_db, require_admin

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["rag-jobs"])


# =============================================================================
# Pydantic Schemas (lokal, da spezifisch fuer Jobs)
# =============================================================================

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class JobStatusResponse(BaseModel):
    """Status eines Batch-Jobs."""
    id: UUID
    job_type: str
    status: str
    progress_percent: int
    items_total: Optional[int] = None
    items_processed: Optional[int] = None
    items_failed: Optional[int] = None
    error_message: Optional[str] = None
    result: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobCreateRequest(BaseModel):
    """Request fuer neuen Batch-Job."""
    job_type: str = Field(..., description="Job-Typ: chunk_all, sync_cards, generate_report")
    parameters: Optional[dict] = Field(default=None, description="Job-spezifische Parameter")


class JobListResponse(BaseModel):
    """Liste von Batch-Jobs."""
    jobs: List[JobStatusResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=JobListResponse,
    summary="Batch-Jobs auflisten",
    description="Listet alle RAG Batch-Jobs auf."
)
async def list_jobs(
    job_type: Optional[str] = Query(None, description="Nach Job-Typ filtern"),
    status_filter: Optional[str] = Query(None, alias="status", description="Nach Status filtern"),
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobListResponse:
    """
    Listet RAG Batch-Jobs auf.

    Filterbar nach:
    - **job_type**: chunk_all, sync_cards, generate_report, etc.
    - **status**: pending, running, completed, failed, cancelled
    """
    query = select(RAGBatchJob)

    # Filter anwenden
    if job_type:
        try:
            jt = RAGBatchJobType(job_type)
            query = query.where(RAGBatchJob.job_type == jt)
        except ValueError as e:
            logger.debug("invalid_job_type_filter_skipped", job_type=job_type, error_type=type(e).__name__)

    if status_filter:
        try:
            st = RAGBatchJobStatus(status_filter)
            query = query.where(RAGBatchJob.status == st)
        except ValueError as e:
            logger.debug("invalid_status_filter_skipped", status=status_filter, error_type=type(e).__name__)

    # Sortierung
    query = query.order_by(desc(RAGBatchJob.created_at))

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Total count
    from sqlalchemy import func
    count_query = select(func.count(RAGBatchJob.id))
    if job_type:
        try:
            jt = RAGBatchJobType(job_type)
            count_query = count_query.where(RAGBatchJob.job_type == jt)
        except ValueError as e:
            logger.debug("invalid_job_type_count_filter_skipped", job_type=job_type, error_type=type(e).__name__)
    if status_filter:
        try:
            st = RAGBatchJobStatus(status_filter)
            count_query = count_query.where(RAGBatchJob.status == st)
        except ValueError as e:
            logger.debug("invalid_status_count_filter_skipped", status=status_filter, error_type=type(e).__name__)

    total = await db.scalar(count_query) or 0

    return JobListResponse(
        jobs=[
            JobStatusResponse(
                id=j.id,
                job_type=j.job_type.value,
                status=j.status.value,
                progress_percent=j.progress_percent,
                items_total=j.items_total,
                items_processed=j.items_processed,
                items_failed=j.items_failed,
                error_message=j.error_message,
                result=j.result,
                started_at=j.started_at,
                completed_at=j.completed_at,
                created_at=j.created_at
            )
            for j in jobs
        ],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Job-Status abrufen",
    description="Gibt den Status eines Batch-Jobs zurueck."
)
async def get_job_status(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobStatusResponse:
    """
    Ruft den Status eines spezifischen Batch-Jobs ab.

    Enthaelt:
    - Fortschritt in Prozent
    - Anzahl verarbeiteter/fehlgeschlagener Items
    - Fehlermeldung bei Problemen
    - Ergebnis bei Abschluss
    """
    result = await db.execute(
        select(RAGBatchJob).where(RAGBatchJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job nicht gefunden"
        )

    return JobStatusResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        progress_percent=job.progress_percent,
        items_total=job.items_total,
        items_processed=job.items_processed,
        items_failed=job.items_failed,
        error_message=job.error_message,
        result=job.result,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at
    )


@router.post(
    "",
    response_model=JobStatusResponse,
    summary="Neuen Batch-Job starten",
    description="Startet einen neuen RAG Batch-Job.",
    dependencies=[Depends(require_admin)]
)
async def create_job(
    request: JobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobStatusResponse:
    """
    Startet einen neuen Batch-Job.

    Verfuegbare Job-Typen:
    - **chunk_all**: Alle Dokumente chunken
    - **sync_cards**: Customer Cards synchronisieren
    - **generate_report**: Report generieren
    - **rebuild_embeddings**: Embeddings neu generieren

    Parameter sind Job-spezifisch.
    """
    # Job-Typ validieren
    try:
        job_type = RAGBatchJobType(request.job_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Job-Typ: {request.job_type}. "
                   f"Erlaubt: {[t.value for t in RAGBatchJobType]}"
        )

    # Pruefen ob gleicher Job bereits laeuft
    running_check = await db.execute(
        select(RAGBatchJob).where(
            RAGBatchJob.job_type == job_type,
            RAGBatchJob.status.in_([RAGBatchJobStatus.PENDING, RAGBatchJobStatus.RUNNING])
        )
    )
    if running_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ein Job vom Typ '{request.job_type}' laeuft bereits"
        )

    # Job erstellen
    job = RAGBatchJob(
        job_type=job_type,
        status=RAGBatchJobStatus.PENDING,
        progress_percent=0,
        parameters=request.parameters
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    logger.info(
        "batch_job_created",
        job_id=str(job.id),
        job_type=request.job_type,
        user_id=str(current_user.id)
    )

    # Celery Task starten
    from app.workers.tasks.rag_tasks import run_rag_batch_job
    run_rag_batch_job.delay(str(job.id))

    return JobStatusResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        progress_percent=job.progress_percent,
        items_total=job.items_total,
        items_processed=job.items_processed,
        items_failed=job.items_failed,
        error_message=job.error_message,
        result=job.result,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at
    )


@router.post(
    "/{job_id}/cancel",
    response_model=JobStatusResponse,
    summary="Job abbrechen",
    description="Bricht einen laufenden Batch-Job ab.",
    dependencies=[Depends(require_admin)]
)
async def cancel_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> JobStatusResponse:
    """
    Bricht einen Batch-Job ab.

    Nur Jobs mit Status 'pending' oder 'running' koennen abgebrochen werden.
    """
    result = await db.execute(
        select(RAGBatchJob).where(RAGBatchJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job nicht gefunden"
        )

    if job.status not in [RAGBatchJobStatus.PENDING, RAGBatchJobStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job kann nicht abgebrochen werden (Status: {job.status.value})"
        )

    # Job abbrechen
    job.status = RAGBatchJobStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    job.error_message = f"Abgebrochen von Benutzer {current_user.email}"

    await db.commit()

    logger.info(
        "batch_job_cancelled",
        job_id=str(job_id),
        user_id=str(current_user.id)
    )

    return JobStatusResponse(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        progress_percent=job.progress_percent,
        items_total=job.items_total,
        items_processed=job.items_processed,
        items_failed=job.items_failed,
        error_message=job.error_message,
        result=job.result,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at
    )


@router.delete(
    "/{job_id}",
    summary="Job loeschen",
    description="Loescht einen abgeschlossenen Batch-Job.",
    dependencies=[Depends(require_admin)]
)
async def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Loescht einen Batch-Job aus der Historie.

    Nur abgeschlossene, fehlgeschlagene oder abgebrochene Jobs koennen geloescht werden.
    """
    result = await db.execute(
        select(RAGBatchJob).where(RAGBatchJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job nicht gefunden"
        )

    if job.status in [RAGBatchJobStatus.PENDING, RAGBatchJobStatus.RUNNING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Laufende Jobs koennen nicht geloescht werden. Erst abbrechen."
        )

    await db.delete(job)
    await db.commit()

    logger.info(
        "batch_job_deleted",
        job_id=str(job_id),
        user_id=str(current_user.id)
    )

    return {
        "success": True,
        "job_id": str(job_id),
        "message": "Job geloescht"
    }


@router.get(
    "/stats/overview",
    summary="Job-Statistiken abrufen",
    description="Gibt eine Uebersicht ueber Batch-Job-Statistiken."
)
async def get_job_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Statistiken ueber Batch-Jobs.

    - Anzahl nach Status
    - Durchschnittliche Verarbeitungszeit
    - Fehlerrate
    """
    from sqlalchemy import func

    # Jobs nach Status
    status_counts = {}
    for st in RAGBatchJobStatus:
        count = await db.scalar(
            select(func.count(RAGBatchJob.id)).where(RAGBatchJob.status == st)
        ) or 0
        status_counts[st.value] = count

    # Durchschnittliche Verarbeitungszeit (nur abgeschlossene)
    from sqlalchemy import extract

    completed_jobs = await db.execute(
        select(RAGBatchJob).where(
            RAGBatchJob.status == RAGBatchJobStatus.COMPLETED,
            RAGBatchJob.started_at.isnot(None),
            RAGBatchJob.completed_at.isnot(None)
        ).limit(100)
    )
    completed = completed_jobs.scalars().all()

    avg_duration_seconds = 0
    if completed:
        durations = [
            (j.completed_at - j.started_at).total_seconds()
            for j in completed
            if j.started_at and j.completed_at
        ]
        if durations:
            avg_duration_seconds = sum(durations) / len(durations)

    # Fehlerrate
    total_jobs = sum(status_counts.values())
    failed_jobs = status_counts.get("failed", 0)
    error_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0

    # Letzte Jobs
    recent_result = await db.execute(
        select(RAGBatchJob)
        .order_by(desc(RAGBatchJob.created_at))
        .limit(5)
    )
    recent_jobs = recent_result.scalars().all()

    return {
        "status_counts": status_counts,
        "total_jobs": total_jobs,
        "avg_duration_seconds": round(avg_duration_seconds, 2),
        "error_rate_percent": round(error_rate, 2),
        "recent_jobs": [
            {
                "id": str(j.id),
                "job_type": j.job_type.value,
                "status": j.status.value,
                "progress_percent": j.progress_percent,
                "created_at": j.created_at.isoformat()
            }
            for j in recent_jobs
        ]
    }
