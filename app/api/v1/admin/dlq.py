"""
Dead Letter Queue (DLQ) Administration API Endpoints.

Provides DLQ management for admins:
- List failed tasks in DLQ
- Get DLQ statistics
- Retry individual DLQ tasks
- Purge DLQ
"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User


router = APIRouter(prefix="/dlq", tags=["Admin - Dead Letter Queue"])


# ==================== Response Models ====================

class DLQTask(BaseModel):
    """Eine Task in der Dead Letter Queue."""
    id: str = Field(..., description="Task-ID")
    name: str = Field(..., description="Task-Name")
    args: Optional[List] = Field(None, description="Task-Argumente")
    kwargs: Optional[dict] = Field(None, description="Task-Keyword-Argumente")
    exception_type: str = Field("Unknown", description="Fehlertyp")
    exception_message: str = Field("", description="Fehlermeldung")
    traceback: Optional[str] = Field(None, description="Stack-Trace")
    failed_at: Optional[datetime] = Field(None, description="Zeitpunkt des Fehlers")
    retries: int = Field(0, description="Anzahl bisheriger Versuche")
    original_queue: str = Field("celery", description="Urspruengliche Queue")
    is_poison_pill: bool = Field(False, description="Wiederholte Fehler (>3x)")


class DLQStatsResponse(BaseModel):
    """DLQ-Statistiken."""
    total_tasks: int = Field(0, description="Gesamtzahl Tasks in DLQ")
    poison_pills: int = Field(0, description="Anzahl Poison Pills (>3 Fehler)")
    oldest_task_age_hours: Optional[float] = Field(None, description="Alter der aeltesten Task (Stunden)")
    tasks_by_exception: dict = Field(default_factory=dict, description="Tasks nach Fehlertyp")
    tasks_by_name: dict = Field(default_factory=dict, description="Tasks nach Task-Name")
    status: str = Field("healthy", description="DLQ-Status: healthy | warning | critical")
    status_message: str = Field("", description="Status-Nachricht")


class DLQTaskListResponse(BaseModel):
    """Liste der DLQ-Tasks."""
    tasks: List[DLQTask]
    total: int
    page: int
    per_page: int
    total_pages: int


class DLQActionResponse(BaseModel):
    """Antwort auf DLQ-Aktionen."""
    success: bool
    message: str
    task_id: Optional[str] = None
    details: Optional[dict] = None


# ==================== Endpoints ====================

@router.get(
    "/stats",
    response_model=DLQStatsResponse,
    summary="DLQ-Statistiken",
    description="Ruft Statistiken der Dead Letter Queue ab"
)
async def get_dlq_stats(
    admin: User = Depends(get_current_superuser),
) -> DLQStatsResponse:
    """
    Ruft Statistiken der Dead Letter Queue ab.

    Zeigt:
    - Gesamtzahl fehlgeschlagener Tasks
    - Poison Pills (Tasks die >3x fehlgeschlagen sind)
    - Alter der aeltesten Task
    - Gruppierung nach Fehlertyp
    - DLQ-Gesundheitsstatus
    """
    try:
        from app.workers.celery_app import celery_app
        import redis
        import json

        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Get all DLQ messages
        dlq_messages = r.lrange("dlq", 0, -1)
        total_tasks = len(dlq_messages)

        if total_tasks == 0:
            return DLQStatsResponse(
                total_tasks=0,
                poison_pills=0,
                oldest_task_age_hours=None,
                tasks_by_exception={},
                tasks_by_name={},
                status="healthy",
                status_message="DLQ ist leer - keine fehlgeschlagenen Tasks",
            )

        # Parse messages and collect stats
        tasks_by_exception = {}
        tasks_by_name = {}
        poison_pills = 0
        oldest_timestamp = None

        for msg in dlq_messages:
            try:
                task_data = json.loads(msg)
                headers = task_data.get("headers", {})
                properties = task_data.get("properties", {})

                task_name = headers.get("task", "unknown")
                exception_type = headers.get("exception_type", "Unknown")
                retries = headers.get("retries", 0)
                timestamp = properties.get("timestamp")

                # Count by exception type
                tasks_by_exception[exception_type] = tasks_by_exception.get(exception_type, 0) + 1

                # Count by task name
                tasks_by_name[task_name] = tasks_by_name.get(task_name, 0) + 1

                # Check for poison pills
                if retries >= 3:
                    poison_pills += 1

                # Track oldest
                if timestamp:
                    task_time = datetime.fromtimestamp(timestamp)
                    if oldest_timestamp is None or task_time < oldest_timestamp:
                        oldest_timestamp = task_time

            except Exception:
                continue

        # Calculate age
        oldest_age_hours = None
        if oldest_timestamp:
            age_delta = datetime.utcnow() - oldest_timestamp
            oldest_age_hours = round(age_delta.total_seconds() / 3600, 1)

        # Determine status
        if total_tasks > 500:
            dlq_status = "critical"
            status_message = f"KRITISCH: {total_tasks} Tasks in DLQ - sofortige Aufmerksamkeit erforderlich"
        elif total_tasks > 100:
            dlq_status = "warning"
            status_message = f"WARNUNG: {total_tasks} Tasks in DLQ - Ueberpruefen empfohlen"
        elif poison_pills > 0:
            dlq_status = "warning"
            status_message = f"{poison_pills} Poison Pills erkannt - moeglicherweise systematische Fehler"
        else:
            dlq_status = "healthy"
            status_message = f"{total_tasks} Tasks in DLQ - im normalen Bereich"

        return DLQStatsResponse(
            total_tasks=total_tasks,
            poison_pills=poison_pills,
            oldest_task_age_hours=oldest_age_hours,
            tasks_by_exception=tasks_by_exception,
            tasks_by_name=tasks_by_name,
            status=dlq_status,
            status_message=status_message,
        )

    except Exception as e:
        return DLQStatsResponse(
            total_tasks=0,
            poison_pills=0,
            status="error",
            status_message=f"Fehler beim Abrufen der DLQ-Statistiken: {str(e)}",
        )


@router.get(
    "/tasks",
    response_model=DLQTaskListResponse,
    summary="DLQ-Tasks auflisten",
    description="Listet alle Tasks in der Dead Letter Queue auf"
)
async def list_dlq_tasks(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    exception_filter: Optional[str] = Query(None, description="Nach Fehlertyp filtern"),
    task_filter: Optional[str] = Query(None, description="Nach Task-Name filtern"),
    admin: User = Depends(get_current_superuser),
) -> DLQTaskListResponse:
    """
    Listet alle Tasks in der Dead Letter Queue auf.

    Mit Pagination und optionaler Filterung nach Fehlertyp oder Task-Name.
    """
    try:
        from app.workers.celery_app import celery_app
        import redis
        import json
        import math

        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Get all DLQ messages
        all_messages = r.lrange("dlq", 0, -1)

        # Parse and filter
        tasks = []
        for msg in all_messages:
            try:
                task_data = json.loads(msg)
                headers = task_data.get("headers", {})
                body = task_data.get("body", {})
                properties = task_data.get("properties", {})

                task_name = headers.get("task", "unknown")
                exception_type = headers.get("exception_type", "Unknown")

                # Apply filters
                if exception_filter and exception_filter.lower() not in exception_type.lower():
                    continue
                if task_filter and task_filter.lower() not in task_name.lower():
                    continue

                # Parse body for args/kwargs
                args = []
                kwargs = {}
                if isinstance(body, (list, tuple)) and len(body) >= 2:
                    args = body[0] if body[0] else []
                    kwargs = body[1] if body[1] else {}

                # Get timestamp
                failed_at = None
                if properties.get("timestamp"):
                    failed_at = datetime.fromtimestamp(properties["timestamp"])

                tasks.append(DLQTask(
                    id=headers.get("id", "unknown"),
                    name=task_name,
                    args=args[:5] if args else None,  # Limit for display
                    kwargs={k: str(v)[:100] for k, v in (kwargs or {}).items()} if kwargs else None,
                    exception_type=exception_type,
                    exception_message=headers.get("exception_message", "")[:500],
                    traceback=headers.get("traceback", "")[:2000] if headers.get("traceback") else None,
                    failed_at=failed_at,
                    retries=headers.get("retries", 0),
                    original_queue=headers.get("original_queue", properties.get("delivery_info", {}).get("routing_key", "celery")),
                    is_poison_pill=headers.get("retries", 0) >= 3,
                ))

            except Exception:
                continue

        # Sort by failed_at (newest first)
        tasks.sort(key=lambda t: t.failed_at or datetime.min, reverse=True)

        # Paginate
        total = len(tasks)
        total_pages = math.ceil(total / per_page) if total > 0 else 1
        offset = (page - 1) * per_page
        paginated_tasks = tasks[offset:offset + per_page]

        return DLQTaskListResponse(
            tasks=paginated_tasks,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.exception("dlq_list_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Auflisten der DLQ-Tasks. Bitte erneut versuchen.",
        )


@router.post(
    "/{task_id}/retry",
    response_model=DLQActionResponse,
    summary="DLQ-Task wiederholen",
    description="Wiederholt eine fehlgeschlagene Task aus der DLQ"
)
async def retry_dlq_task(
    task_id: str,
    request: Request,
    admin: User = Depends(get_current_superuser),
) -> DLQActionResponse:
    """
    Wiederholt eine fehlgeschlagene Task aus der Dead Letter Queue.

    Die Task wird aus der DLQ entfernt und zurueck in die urspruengliche
    Queue eingereiht.
    """
    try:
        from app.workers.celery_app import celery_app
        import redis
        import json

        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Find and remove the task from DLQ
        all_messages = r.lrange("dlq", 0, -1)
        task_found = None
        task_index = -1

        for i, msg in enumerate(all_messages):
            try:
                task_data = json.loads(msg)
                headers = task_data.get("headers", {})
                if headers.get("id") == task_id:
                    task_found = task_data
                    task_index = i
                    break
            except Exception:
                continue

        if not task_found:
            return DLQActionResponse(
                success=False,
                message="Task nicht in DLQ gefunden",
                task_id=task_id,
            )

        # Get original task info
        headers = task_found.get("headers", {})
        task_name = headers.get("task")
        body = task_found.get("body", [[], {}])

        if not task_name:
            return DLQActionResponse(
                success=False,
                message="Task-Name nicht ermittelbar",
                task_id=task_id,
            )

        # Parse body
        args = body[0] if isinstance(body, (list, tuple)) and body else []
        kwargs = body[1] if isinstance(body, (list, tuple)) and len(body) > 1 else {}

        # Re-queue the task
        try:
            task = celery_app.send_task(
                task_name,
                args=args,
                kwargs=kwargs,
                retry=False,  # Don't auto-retry if it fails again
            )

            # Remove from DLQ
            r.lrem("dlq", 1, all_messages[task_index])

            return DLQActionResponse(
                success=True,
                message=f"Task wurde erneut in Queue eingereiht",
                task_id=task_id,
                details={
                    "new_task_id": task.id,
                    "task_name": task_name,
                },
            )

        except Exception as e:
            return DLQActionResponse(
                success=False,
                message=f"Fehler beim Wiederholen der Task: {str(e)}",
                task_id=task_id,
            )

    except Exception as e:
        return DLQActionResponse(
            success=False,
            message=f"Fehler: {str(e)}",
            task_id=task_id,
        )


@router.post(
    "/purge",
    response_model=DLQActionResponse,
    summary="DLQ leeren",
    description="Loescht alle Tasks aus der Dead Letter Queue (GEFAEHRLICH)"
)
async def purge_dlq(
    request: Request,
    confirm: bool = Query(False, description="Bestaetigung erforderlich"),
    admin: User = Depends(get_current_superuser),
) -> DLQActionResponse:
    """
    Loescht ALLE Tasks aus der Dead Letter Queue.

    **WARNUNG:** Diese Aktion kann NICHT rueckgaengig gemacht werden!
    Alle fehlgeschlagenen Tasks werden unwiderruflich geloescht.

    Erfordert explizite Bestaetigung via ?confirm=true
    """
    if not confirm:
        return DLQActionResponse(
            success=False,
            message="Bestaetigung erforderlich: Bitte ?confirm=true hinzufuegen",
            details={
                "warning": "Diese Aktion loescht ALLE Tasks aus der DLQ unwiderruflich!"
            },
        )

    try:
        from app.workers.celery_app import celery_app
        from app.db.models import AdminAction
        import redis

        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Count before delete
        count = r.llen("dlq") or 0

        if count == 0:
            return DLQActionResponse(
                success=True,
                message="DLQ ist bereits leer",
                details={"deleted_count": 0},
            )

        # Delete all
        r.delete("dlq")

        # Log admin action (we need a db session for this)
        # Note: In a real implementation, we'd use dependency injection for this
        import structlog
        logger = structlog.get_logger(__name__)
        logger.warning(
            "dlq_purged",
            admin_id=str(admin.id),
            deleted_count=count,
            ip_address=request.client.host if request.client else None,
        )

        return DLQActionResponse(
            success=True,
            message=f"DLQ wurde geleert: {count} Tasks geloescht",
            details={
                "deleted_count": count,
                "admin_id": str(admin.id),
            },
        )

    except Exception as e:
        return DLQActionResponse(
            success=False,
            message=f"Fehler beim Leeren der DLQ: {str(e)}",
        )


@router.post(
    "/bulk/retry",
    response_model=DLQActionResponse,
    summary="Mehrere DLQ-Tasks wiederholen",
    description="Wiederholt mehrere fehlgeschlagene Tasks aus der DLQ"
)
async def bulk_retry_dlq_tasks(
    task_ids: List[str],
    request: Request,
    admin: User = Depends(get_current_superuser),
) -> DLQActionResponse:
    """
    Wiederholt mehrere fehlgeschlagene Tasks aus der Dead Letter Queue.

    Gibt eine Zusammenfassung zurueck, welche Tasks erfolgreich
    wiederholt wurden und welche nicht.
    """
    if not task_ids:
        return DLQActionResponse(
            success=False,
            message="Keine Task-IDs angegeben",
        )

    success_count = 0
    failed_count = 0
    failed_ids = []

    for task_id in task_ids:
        result = await retry_dlq_task(task_id, request, admin)
        if result.success:
            success_count += 1
        else:
            failed_count += 1
            failed_ids.append(task_id)

    return DLQActionResponse(
        success=failed_count == 0,
        message=f"{success_count} von {len(task_ids)} Tasks erfolgreich wiederholt",
        details={
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_ids": failed_ids[:10],  # Limit to first 10
        },
    )
