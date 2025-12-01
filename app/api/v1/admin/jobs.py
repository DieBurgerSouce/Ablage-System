"""
Job Administration API Endpoints.

Provides job management for admins:
- List jobs with filtering and pagination
- Cancel running/pending jobs
- Retry failed jobs
- Clear job queue
"""

from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User, ProcessingStatus
from app.db.schemas import (
    JobAdminView,
    JobListFilters,
    JobListResponse,
    JobActionResponse,
    QueueClearResponse,
    JobSortField,
    SortOrder,
)
from app.services.admin.job_admin_service import JobAdminService


router = APIRouter(prefix="/jobs", tags=["Admin - Auftragsverwaltung"])


# ==================== List Jobs ====================

@router.get(
    "",
    response_model=JobListResponse,
    summary="Auftraege auflisten",
    description="Listet alle Verarbeitungsauftraege mit Filter- und Paginierungsoptionen auf"
)
async def list_jobs(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    status_filter: Optional[ProcessingStatus] = Query(None, alias="status", description="Nach Status filtern"),
    backend: Optional[str] = Query(None, description="Nach Backend filtern"),
    user_id: Optional[UUID] = Query(None, description="Nach Benutzer filtern"),
    priority: Optional[int] = Query(None, ge=1, le=10, description="Nach Prioritaet filtern"),
    has_error: Optional[bool] = Query(None, description="Nur Auftraege mit/ohne Fehler"),
    created_from: Optional[datetime] = Query(None, description="Erstellt ab (ISO-Format)"),
    created_to: Optional[datetime] = Query(None, description="Erstellt bis (ISO-Format)"),
    sort_by: JobSortField = Query(JobSortField.CREATED_AT, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """
    Listet alle Verarbeitungsauftraege im System auf.

    Nur fuer Administratoren zugaenglich.

    **Filter:**
    - **status**: pending, queued, processing, completed, failed, cancelled
    - **backend**: deepseek, got_ocr, surya, surya_gpu
    - **user_id**: UUID des Dokumenteigentuemers
    - **priority**: 1-10 (1 = hoechste Prioritaet)
    - **has_error**: true = nur fehlgeschlagene Auftraege
    - **created_from/to**: Zeitraumfilter

    **Sortierung:**
    - Standardmaessig nach Erstellungsdatum absteigend
    - Sortierbare Felder: created_at, started_at, completed_at, priority
    """
    filters = JobListFilters(
        status=status_filter,
        backend=backend,
        user_id=user_id,
        priority=priority,
        has_error=has_error,
        created_from=created_from,
        created_to=created_to,
    )

    return await JobAdminService.list_jobs(
        db=db,
        page=page,
        per_page=per_page,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ==================== Get Single Job ====================

@router.get(
    "/{job_id}",
    response_model=JobAdminView,
    summary="Auftrag abrufen",
    description="Ruft detaillierte Informationen zu einem Auftrag ab"
)
async def get_job(
    job_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> JobAdminView:
    """
    Ruft detaillierte Informationen zu einem bestimmten Auftrag ab.

    Nur fuer Administratoren zugaenglich.
    """
    job = await JobAdminService.get_job(db, job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftrag nicht gefunden",
        )

    return job


# ==================== Cancel Job ====================

@router.post(
    "/{job_id}/cancel",
    response_model=JobActionResponse,
    summary="Auftrag abbrechen",
    description="Bricht einen wartenden oder laufenden Auftrag ab"
)
async def cancel_job(
    job_id: UUID,
    request: Request,
    reason: Optional[str] = Query(None, description="Grund fuer Abbruch"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Bricht einen wartenden oder laufenden Auftrag ab.

    Der Auftrag wird als 'cancelled' markiert und nicht weiter verarbeitet.

    **Hinweis:** Bereits abgeschlossene Auftraege koennen nicht abgebrochen werden.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.cancel_job(
        db=db,
        job_id=job_id,
        admin=admin,
        reason=reason,
        ip_address=ip_address,
    )


# ==================== Retry Job ====================

@router.post(
    "/{job_id}/retry",
    response_model=JobActionResponse,
    summary="Auftrag wiederholen",
    description="Erstellt einen neuen Auftrag basierend auf einem fehlgeschlagenen Auftrag"
)
async def retry_job(
    job_id: UUID,
    request: Request,
    priority: Optional[int] = Query(None, ge=1, le=10, description="Neue Prioritaet"),
    backend: Optional[str] = Query(None, description="Anderes Backend verwenden"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Erstellt einen neuen Auftrag basierend auf einem fehlgeschlagenen Auftrag.

    Der urspruengliche Auftrag bleibt unveraendert. Es wird ein neuer
    Auftrag mit denselben Parametern erstellt.

    **Optionen:**
    - **priority**: Neue Prioritaet setzen (1-10)
    - **backend**: Anderes OCR-Backend verwenden

    **Hinweis:** Nur fehlgeschlagene Auftraege koennen wiederholt werden.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.retry_job(
        db=db,
        job_id=job_id,
        admin=admin,
        priority=priority,
        backend=backend,
        ip_address=ip_address,
    )


# ==================== Clear Queue ====================

@router.post(
    "/queue/clear",
    response_model=QueueClearResponse,
    summary="Warteschlange leeren",
    description="Loescht alle wartenden Auftraege aus der Warteschlange"
)
async def clear_queue(
    request: Request,
    status_filter: ProcessingStatus = Query(
        ProcessingStatus.PENDING,
        alias="status",
        description="Status der zu loeschenden Auftraege"
    ),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> QueueClearResponse:
    """
    Loescht alle Auftraege mit dem angegebenen Status aus der Warteschlange.

    **WARNUNG:** Diese Aktion kann nicht rueckgaengig gemacht werden!

    Standardmaessig werden nur wartende (pending) Auftraege geloescht.
    Es koennen auch Auftraege im Status 'queued' geloescht werden.

    Laufende oder abgeschlossene Auftraege koennen nicht geloescht werden.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.clear_queue(
        db=db,
        admin=admin,
        status=status_filter,
        ip_address=ip_address,
    )


# ==================== Bulk Cancel ====================

@router.post(
    "/bulk/cancel",
    response_model=dict,
    summary="Mehrere Auftraege abbrechen",
    description="Bricht mehrere Auftraege gleichzeitig ab"
)
async def bulk_cancel_jobs(
    job_ids: list[UUID],
    request: Request,
    reason: Optional[str] = Query(None, description="Grund fuer Abbruch"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Bricht mehrere Auftraege gleichzeitig ab.

    Gibt eine Zusammenfassung zurueck, welche Auftraege erfolgreich
    abgebrochen wurden und welche nicht.
    """
    ip_address = request.client.host if request.client else None

    results = {
        "success": [],
        "failed": [],
        "total": len(job_ids),
    }

    for job_id in job_ids:
        response = await JobAdminService.cancel_job(
            db=db,
            job_id=job_id,
            admin=admin,
            reason=reason,
            ip_address=ip_address,
        )

        if response.success:
            results["success"].append(str(job_id))
        else:
            results["failed"].append({
                "job_id": str(job_id),
                "reason": response.message,
            })

    results["success_count"] = len(results["success"])
    results["failed_count"] = len(results["failed"])

    return results


# ==================== Job Statistics ====================

@router.get(
    "/stats/summary",
    summary="Auftragsstatistiken",
    description="Ruft zusammenfassende Statistiken zu Auftraegen ab"
)
async def get_job_stats(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft zusammenfassende Statistiken zu Auftraegen ab.

    Zeigt:
    - Anzahl Auftraege nach Status
    - Durchschnittliche Verarbeitungszeit
    - Durchschnittliche Wartezeit
    - Auftraege nach Backend
    """
    # Get basic job list with stats
    response = await JobAdminService.list_jobs(db, page=1, per_page=1)

    return {
        "status_summary": response.status_summary,
        "total_jobs": response.total,
    }
