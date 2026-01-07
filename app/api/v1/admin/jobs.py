"""
Job Administration API Endpoints.

Provides job management for admins:
- List jobs with filtering and pagination
- Cancel running/pending jobs
- Retry failed jobs
- Clear job queue

Enterprise Features:
- Request timeouts for long-running operations
- Max batch size limits for bulk operations
- Structured error responses
"""

import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser, check_destructive_admin_rate_limit
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
from app.core.audit_logger import SecurityAuditLogger, SecurityEventType


# ==================== Constants ====================

# Maximum timeout for bulk operations (seconds)
BULK_OPERATION_TIMEOUT = 60

# Maximum number of jobs per bulk operation
MAX_BULK_JOBS = 100


router = APIRouter(prefix="/jobs", tags=["Admin - Auftragsverwaltung"])


# ==================== List Jobs ====================

@router.get(
    "",
    response_model=JobListResponse,
    summary="Auftraege auflisten",
    description="Listet alle Verarbeitungsauftraege mit Filter- und Paginierungsoptionen auf"
)
async def list_jobs(
    request: Request,
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
    sort_order_raw: str = Query("desc", alias="sort_order", description="Sortierrichtung (asc/desc)"),
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

    **Audit Logging:**
    - Alle Auflistungen werden fuer GDPR Art. 30 protokolliert
    """
    # Case-insensitive sort_order parsing (accepts both "DESC" and "desc")
    sort_order = SortOrder.DESC if sort_order_raw.lower() == "desc" else SortOrder.ASC

    filters = JobListFilters(
        status=status_filter,
        backend=backend,
        user_id=user_id,
        priority=priority,
        has_error=has_error,
        created_from=created_from,
        created_to=created_to,
    )

    result = await JobAdminService.list_jobs(
        db=db,
        page=page,
        per_page=per_page,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # GDPR Art. 30: Audit Log fuer Admin-Zugriff auf Job-Liste
    # Fix 6: Filter-Parameter maskieren - user_id nicht vollstaendig loggen
    ip_address = request.client.host if request.client else None
    audit = SecurityAuditLogger(db)
    await audit.log_event(
        event_type=SecurityEventType.ADMIN_JOBS_LISTED,
        user_id=str(admin.id),
        ip_address=ip_address,
        resource_type="job_queue",
        details={
            "page": page,
            "per_page": per_page,
            "total_jobs": result.total,
            "filters_applied": {
                "status": status_filter.value if status_filter else None,
                "backend": backend,
                # user_id maskiert: nur ob Filter gesetzt wurde, nicht der Wert
                "user_id_filtered": user_id is not None,
                "priority": priority,
                "has_error": has_error,
            },
            "sort_by": sort_by.value,
            "sort_order": sort_order.value,
        },
        severity="info",
    )

    return result


# ==================== Get Single Job ====================

@router.get(
    "/{job_id}",
    response_model=JobAdminView,
    summary="Auftrag abrufen",
    description="Ruft detaillierte Informationen zu einem Auftrag ab"
)
async def get_job(
    job_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> JobAdminView:
    """
    Ruft detaillierte Informationen zu einem bestimmten Auftrag ab.

    Nur fuer Administratoren zugaenglich.

    **Audit Logging:**
    - Alle Einzelabrufe werden fuer GDPR Art. 30 protokolliert
    """
    job = await JobAdminService.get_job(db, job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftrag nicht gefunden",
        )

    # GDPR Art. 30: Audit Log fuer Admin-Zugriff auf einzelnen Job
    ip_address = request.client.host if request.client else None
    audit = SecurityAuditLogger(db)
    await audit.log_event(
        event_type=SecurityEventType.ADMIN_JOB_ACCESSED,
        user_id=str(admin.id),
        ip_address=ip_address,
        resource_type="processing_job",
        resource_id=str(job_id),
        details={
            "job_status": job.status,
            "job_backend": job.backend,
            "document_id": str(job.document_id) if job.document_id else None,
            "owner_email": job.owner_email,
        },
        severity="info",
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
    reason: Optional[str] = Query(None, description="Grund für Abbruch"),
    admin: User = Depends(check_destructive_admin_rate_limit),
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
    admin: User = Depends(check_destructive_admin_rate_limit),
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

# Longer timeout for clear_queue as it may affect many jobs
CLEAR_QUEUE_TIMEOUT = 120  # 2 minutes

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
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> QueueClearResponse:
    """
    Loescht alle Auftraege mit dem angegebenen Status aus der Warteschlange.

    **WARNUNG:** Diese Aktion kann nicht rueckgaengig gemacht werden!

    **Limits:**
    - Timeout: 120 Sekunden
    - Rate Limit: 10/Minute, 50/Stunde (destruktive Operation)

    Standardmaessig werden nur wartende (pending) Auftraege geloescht.
    Es koennen auch Auftraege im Status 'queued' geloescht werden.

    Laufende oder abgeschlossene Auftraege koennen nicht geloescht werden.
    """
    ip_address = request.client.host if request.client else None

    try:
        async with asyncio.timeout(CLEAR_QUEUE_TIMEOUT):
            return await JobAdminService.clear_queue(
                db=db,
                admin=admin,
                status=status_filter,
                ip_address=ip_address,
            )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Operation nach {CLEAR_QUEUE_TIMEOUT} Sekunden abgebrochen. "
                   "Bitte versuchen Sie es erneut oder wenden Sie sich an den Support."
        )


# ==================== Bulk Cancel ====================

@router.post(
    "/bulk/cancel",
    response_model=dict,
    summary="Mehrere Auftraege abbrechen",
    description="Bricht mehrere Auftraege gleichzeitig ab (max. 100 Jobs)"
)
async def bulk_cancel_jobs(
    job_ids: list[UUID],
    request: Request,
    reason: Optional[str] = Query(None, description="Grund für Abbruch"),
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Bricht mehrere Auftraege gleichzeitig ab.

    **Limits:**
    - Maximal 100 Jobs pro Anfrage
    - Timeout: 60 Sekunden
    - Rate Limit: 10/Minute, 50/Stunde (destruktive Operation)

    Gibt eine Zusammenfassung zurueck, welche Auftraege erfolgreich
    abgebrochen wurden und welche nicht.
    """
    # Enforce max batch size
    if len(job_ids) > MAX_BULK_JOBS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximal {MAX_BULK_JOBS} Auftraege pro Anfrage erlaubt. "
                   f"Erhalten: {len(job_ids)}"
        )

    ip_address = request.client.host if request.client else None

    results = {
        "success": [],
        "failed": [],
        "total": len(job_ids),
    }

    try:
        async with asyncio.timeout(BULK_OPERATION_TIMEOUT):
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
    except asyncio.TimeoutError:
        # Operation timed out - return partial results
        results["timeout"] = True
        results["timeout_message"] = (
            f"Operation nach {BULK_OPERATION_TIMEOUT} Sekunden abgebrochen. "
            f"Teilweise verarbeitet: {len(results['success'])} erfolgreich, "
            f"{len(results['failed'])} fehlgeschlagen."
        )

    results["success_count"] = len(results["success"])
    results["failed_count"] = len(results["failed"])

    # GDPR Art. 30: Audit Log fuer Bulk-Cancel-Operation
    audit = SecurityAuditLogger(db)
    await audit.log_event(
        event_type=SecurityEventType.ADMIN_JOBS_BULK_ACTION,
        user_id=str(admin.id),
        ip_address=ip_address,
        resource_type="job_queue",
        details={
            "action": "bulk_cancel",
            "total_requested": len(job_ids),
            "success_count": results["success_count"],
            "failed_count": results["failed_count"],
            "reason": reason,
            "timed_out": results.get("timeout", False),
        },
        severity="warning",  # Destruktive Operation
    )

    return results


# ==================== Job Statistics ====================

@router.get(
    "/stats/summary",
    summary="Auftragsstatistiken",
    description="Ruft zusammenfassende Statistiken zu Auftraegen ab"
)
async def get_job_stats(
    request: Request,
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

    **Audit Logging:**
    - Alle Statistik-Abfragen werden fuer GDPR Art. 30 protokolliert
    """
    result = await JobAdminService.get_job_stats(db)

    # GDPR Art. 30: Audit Log fuer Statistik-Abfragen (Fix 1)
    ip_address = request.client.host if request.client else None
    audit = SecurityAuditLogger(db)
    await audit.log_event(
        event_type=SecurityEventType.ADMIN_JOB_ACCESSED,  # Job stats viewing
        user_id=str(admin.id),
        ip_address=ip_address,
        resource_type="job_statistics",
        details={
            "action": "job_stats_viewed",
            "total_jobs": result.get("total_jobs", 0),
            "active_jobs": result.get("active_jobs", 0),
        },
        severity="info",
    )

    return result


# ==================== Bulk Retry ====================

@router.post(
    "/bulk/retry",
    response_model=dict,
    summary="Mehrere Auftraege wiederholen",
    description="Wiederholt mehrere fehlgeschlagene Auftraege gleichzeitig (max. 100 Jobs)"
)
async def bulk_retry_jobs(
    job_ids: list[UUID],
    request: Request,
    priority: Optional[int] = Query(None, ge=1, le=10, description="Neue Prioritaet fuer alle"),
    backend: Optional[str] = Query(None, description="Anderes Backend verwenden"),
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Wiederholt mehrere fehlgeschlagene Auftraege gleichzeitig.

    **Limits:**
    - Maximal 100 Jobs pro Anfrage
    - Timeout: 60 Sekunden
    - Rate Limit: 10/Minute, 50/Stunde (destruktive Operation)

    Gibt eine Zusammenfassung zurueck, welche Auftraege erfolgreich
    wiederholt wurden und welche nicht.
    """
    # Enforce max batch size
    if len(job_ids) > MAX_BULK_JOBS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximal {MAX_BULK_JOBS} Auftraege pro Anfrage erlaubt. "
                   f"Erhalten: {len(job_ids)}"
        )

    ip_address = request.client.host if request.client else None

    results = {
        "success": [],
        "failed": [],
        "total": len(job_ids),
    }

    try:
        async with asyncio.timeout(BULK_OPERATION_TIMEOUT):
            for job_id in job_ids:
                response = await JobAdminService.retry_job(
                    db=db,
                    job_id=job_id,
                    admin=admin,
                    priority=priority,
                    backend=backend,
                    ip_address=ip_address,
                )

                if response.success:
                    results["success"].append({
                        "original_job_id": str(job_id),
                        "new_job_id": str(response.job_id),
                    })
                else:
                    results["failed"].append({
                        "job_id": str(job_id),
                        "reason": response.message,
                    })
    except asyncio.TimeoutError:
        # Operation timed out - return partial results
        results["timeout"] = True
        results["timeout_message"] = (
            f"Operation nach {BULK_OPERATION_TIMEOUT} Sekunden abgebrochen. "
            f"Teilweise verarbeitet: {len(results['success'])} erfolgreich, "
            f"{len(results['failed'])} fehlgeschlagen."
        )

    results["success_count"] = len(results["success"])
    results["failed_count"] = len(results["failed"])

    # GDPR Art. 30: Audit Log fuer Bulk-Retry-Operation
    audit = SecurityAuditLogger(db)
    await audit.log_event(
        event_type=SecurityEventType.ADMIN_JOBS_BULK_ACTION,
        user_id=str(admin.id),
        ip_address=ip_address,
        resource_type="job_queue",
        details={
            "action": "bulk_retry",
            "total_requested": len(job_ids),
            "success_count": results["success_count"],
            "failed_count": results["failed_count"],
            "priority_override": priority,
            "backend_override": backend,
            "timed_out": results.get("timeout", False),
        },
        severity="warning",  # Destruktive Operation
    )

    return results


# ==================== Change Priority ====================

@router.patch(
    "/{job_id}/priority",
    response_model=JobActionResponse,
    summary="Prioritaet aendern",
    description="Aendert die Prioritaet eines wartenden Auftrags"
)
async def change_job_priority(
    job_id: UUID,
    priority: int = Query(..., ge=1, le=10, description="Neue Prioritaet (1-10, 1=hoechste)"),
    request: Request = None,
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Aendert die Prioritaet eines wartenden oder in Warteschlange befindlichen Auftrags.

    **Hinweis:** Nur Auftraege im Status 'pending' oder 'queued' koennen priorisiert werden.
    """
    ip_address = request.client.host if request and request.client else None

    return await JobAdminService.change_priority(
        db=db,
        job_id=job_id,
        priority=priority,
        admin=admin,
        ip_address=ip_address,
    )


# ==================== Force Kill ====================

@router.post(
    "/{job_id}/force-kill",
    response_model=JobActionResponse,
    summary="Auftrag erzwungen beenden",
    description="Beendet einen feststeckenden Auftrag erzwungen (SIGKILL)"
)
async def force_kill_job(
    job_id: UUID,
    request: Request,
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Beendet einen feststeckenden Auftrag erzwungen.

    **WARNUNG:** Diese Aktion sendet ein SIGKILL an den Celery Worker Task.
    Dies sollte nur verwendet werden, wenn ein Auftrag nicht auf normale
    Abbruch-Anfragen reagiert.

    Die GPU-Sperre wird ebenfalls freigegeben, falls vorhanden.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.force_kill_job(
        db=db,
        job_id=job_id,
        admin=admin,
        ip_address=ip_address,
    )


# ==================== Pause Job ====================

@router.post(
    "/{job_id}/pause",
    response_model=JobActionResponse,
    summary="Auftrag pausieren",
    description="Pausiert einen laufenden Auftrag"
)
async def pause_job(
    job_id: UUID,
    request: Request,
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Pausiert einen laufenden oder wartenden Auftrag.

    Der Auftrag kann spaeter mit /resume fortgesetzt werden.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.pause_job(
        db=db,
        job_id=job_id,
        admin=admin,
        ip_address=ip_address,
    )


# ==================== Resume Job ====================

@router.post(
    "/{job_id}/resume",
    response_model=JobActionResponse,
    summary="Auftrag fortsetzen",
    description="Setzt einen pausierten Auftrag fort"
)
async def resume_job(
    job_id: UUID,
    request: Request,
    admin: User = Depends(check_destructive_admin_rate_limit),
    db: AsyncSession = Depends(get_db),
) -> JobActionResponse:
    """
    Setzt einen pausierten Auftrag fort.

    Der Auftrag wird wieder in die Warteschlange eingereiht.
    """
    ip_address = request.client.host if request.client else None

    return await JobAdminService.resume_job(
        db=db,
        job_id=job_id,
        admin=admin,
        ip_address=ip_address,
    )
