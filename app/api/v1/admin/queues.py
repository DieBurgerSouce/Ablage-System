"""
Queue and Worker Administration API Endpoints.

Provides queue and worker monitoring for admins:
- List all queues with their status
- Get queue statistics
- List workers with health status
- Monitor GPU usage
"""

from typing import Optional, List
from datetime import datetime
from app.core.datetime_utils import utc_now

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import structlog

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/queues", tags=["Admin - Warteschlangen"])


# ==================== Response Models ====================

class QueueStatus(BaseModel):
    """Status einer einzelnen Queue."""
    name: str = Field(..., description="Queue-Name")
    length: int = Field(0, description="Anzahl wartender Tasks")
    processing: int = Field(0, description="Anzahl laufender Tasks")
    priority: int = Field(5, description="Queue-Prioritaet (1-10)")
    description: str = Field("", description="Queue-Beschreibung")


class QueueListResponse(BaseModel):
    """Liste aller Queues."""
    queues: List[QueueStatus]
    total_pending: int = Field(0, description="Gesamtzahl wartender Tasks")
    total_processing: int = Field(0, description="Gesamtzahl laufender Tasks")


class WorkerStatus(BaseModel):
    """Status eines Workers."""
    id: str = Field(..., description="Worker-ID")
    hostname: str = Field(..., description="Hostname")
    status: str = Field(..., description="online | offline | busy")
    active_tasks: int = Field(0, description="Anzahl aktiver Tasks")
    current_task: Optional[str] = Field(None, description="Aktueller Task-Name")
    current_task_id: Optional[str] = Field(None, description="Aktuelle Task-ID")
    last_heartbeat: Optional[datetime] = Field(None, description="Letzter Heartbeat")
    tasks_processed: int = Field(0, description="Verarbeitete Tasks seit Start")
    pool_size: int = Field(1, description="Worker Pool Groesse")
    prefetch_count: int = Field(1, description="Prefetch Count")


class GPUStatus(BaseModel):
    """GPU-Status."""
    available: bool = Field(False, description="GPU verfuegbar")
    name: Optional[str] = Field(None, description="GPU-Name")
    memory_used_mb: int = Field(0, description="Verwendeter Speicher (MB)")
    memory_total_mb: int = Field(0, description="Gesamtspeicher (MB)")
    memory_percent: float = Field(0.0, description="Speicherauslastung (%)")
    utilization_percent: float = Field(0.0, description="GPU-Auslastung (%)")
    temperature_celsius: Optional[int] = Field(None, description="Temperatur (Celsius)")
    lock_held: bool = Field(False, description="GPU-Lock gehalten")
    lock_holder: Optional[str] = Field(None, description="Lock-Inhaber (Task-ID)")


class WorkerListResponse(BaseModel):
    """Liste aller Worker."""
    workers: List[WorkerStatus]
    total_workers: int = Field(0, description="Gesamtzahl Worker")
    online_workers: int = Field(0, description="Online Worker")
    busy_workers: int = Field(0, description="Busy Worker")
    gpu: GPUStatus = Field(default_factory=GPUStatus, description="GPU-Status")


class QueueStatsResponse(BaseModel):
    """Detaillierte Queue-Statistiken."""
    name: str
    length: int
    processing: int
    completed_last_hour: int
    failed_last_hour: int
    avg_processing_time_ms: int
    throughput_per_minute: float


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=QueueListResponse,
    summary="Warteschlangen auflisten",
    description="Listet alle Celery-Warteschlangen mit ihrem Status auf"
)
async def list_queues(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> QueueListResponse:
    """
    Listet alle Celery-Warteschlangen mit ihrem aktuellen Status auf.

    Zeigt:
    - Queue-Name und Prioritaet
    - Anzahl wartender Tasks
    - Anzahl laufender Tasks
    """
    try:
        from app.workers.celery_app import celery_app
        import redis

        # Get queue info from Redis
        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Known queues with their priorities and descriptions
        queue_configs = {
            "ocr_high": {"priority": 9, "description": "Hochprioritaets-OCR (GPU)"},
            "ocr_normal": {"priority": 5, "description": "Standard-OCR (GPU)"},
            "embedding_high": {"priority": 8, "description": "Hochprioritaets-Embeddings"},
            "embedding_normal": {"priority": 5, "description": "Standard-Embeddings"},
            "embedding_low": {"priority": 2, "description": "Niedrigprioritaets-Embeddings"},
            "validation": {"priority": 3, "description": "Text-Validierung (CPU)"},
            "metadata": {"priority": 3, "description": "Metadaten-Extraktion"},
            "backup": {"priority": 2, "description": "Backup-Operationen"},
            "maintenance": {"priority": 1, "description": "Wartungsaufgaben"},
            "metrics": {"priority": 1, "description": "Metriken-Sammlung"},
            "dlq": {"priority": 0, "description": "Dead Letter Queue"},
            "celery": {"priority": 5, "description": "Standard Celery Queue"},
        }

        queues = []
        total_pending = 0
        total_processing = 0

        for queue_name, config in queue_configs.items():
            try:
                # Get queue length from Redis
                length = r.llen(queue_name) or 0
                total_pending += length

                queues.append(QueueStatus(
                    name=queue_name,
                    length=length,
                    processing=0,  # Will be updated from worker inspection
                    priority=config["priority"],
                    description=config["description"],
                ))
            except Exception:
                queues.append(QueueStatus(
                    name=queue_name,
                    length=0,
                    processing=0,
                    priority=config["priority"],
                    description=config["description"],
                ))

        # Get active task counts from workers
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active() or {}

            for worker_name, tasks in active.items():
                for task in tasks:
                    queue_name = task.get("delivery_info", {}).get("routing_key", "celery")
                    for queue in queues:
                        if queue.name == queue_name:
                            queue.processing += 1
                            total_processing += 1
                            break
        except Exception as e:
            logger.debug(
                "celery_reserved_tasks_fetch_failed",
                error_type=type(e).__name__,
            )

        # Sort by priority (highest first)
        queues.sort(key=lambda q: q.priority, reverse=True)

        return QueueListResponse(
            queues=queues,
            total_pending=total_pending,
            total_processing=total_processing,
        )

    except Exception as e:
        # Return empty list on error
        return QueueListResponse(
            queues=[],
            total_pending=0,
            total_processing=0,
        )


@router.get(
    "/{queue_name}/stats",
    response_model=QueueStatsResponse,
    summary="Queue-Statistiken",
    description="Ruft detaillierte Statistiken fuer eine Queue ab"
)
async def get_queue_stats(
    queue_name: str,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> QueueStatsResponse:
    """
    Ruft detaillierte Statistiken fuer eine bestimmte Queue ab.

    Zeigt:
    - Aktuelle Laenge
    - Durchsatz pro Minute
    - Durchschnittliche Verarbeitungszeit
    - Erfolge/Fehler in der letzten Stunde
    """
    try:
        from app.workers.celery_app import celery_app
        import redis
        from datetime import timedelta
        from sqlalchemy import select, func, and_
        from app.db.models import ProcessingJob, ProcessingStatus

        redis_url = celery_app.conf.broker_url
        r = redis.from_url(redis_url)

        # Get queue length
        length = r.llen(queue_name) or 0

        # Get processing count from active tasks
        processing = 0
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active() or {}
            for worker_name, tasks in active.items():
                for task in tasks:
                    task_queue = task.get("delivery_info", {}).get("routing_key", "celery")
                    if task_queue == queue_name:
                        processing += 1
        except Exception as e:
            logger.debug(
                "celery_active_tasks_fetch_failed",
                queue=queue_name,
                error_type=type(e).__name__,
            )

        # Get stats from database for jobs that went through this queue
        # Note: This is approximate as we don't track queue per job currently
        now = utc_now()
        last_hour = now - timedelta(hours=1)

        # Completed in last hour
        completed_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= last_hour
                )
            )
        )
        completed_last_hour = completed_result.scalar() or 0

        # Failed in last hour
        failed_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.FAILED,
                    ProcessingJob.completed_at >= last_hour
                )
            )
        )
        failed_last_hour = failed_result.scalar() or 0

        # Average processing time
        avg_time_result = await db.execute(
            select(func.avg(
                func.extract('epoch', ProcessingJob.completed_at) -
                func.extract('epoch', ProcessingJob.started_at)
            )).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= last_hour,
                    ProcessingJob.started_at.isnot(None)
                )
            )
        )
        avg_time_seconds = avg_time_result.scalar() or 0

        # Throughput per minute
        throughput_per_minute = completed_last_hour / 60.0 if completed_last_hour > 0 else 0.0

        return QueueStatsResponse(
            name=queue_name,
            length=length,
            processing=processing,
            completed_last_hour=completed_last_hour,
            failed_last_hour=failed_last_hour,
            avg_processing_time_ms=int(avg_time_seconds * 1000) if avg_time_seconds else 0,
            throughput_per_minute=round(throughput_per_minute, 2),
        )

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.exception("queue_stats_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Queue-Statistiken. Bitte erneut versuchen.",
        )


# ==================== Worker Endpoints ====================

@router.get(
    "/workers",
    response_model=WorkerListResponse,
    summary="Worker auflisten",
    description="Listet alle Celery-Worker mit ihrem Status auf"
)
async def list_workers(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> WorkerListResponse:
    """
    Listet alle Celery-Worker mit ihrem aktuellen Status auf.

    Zeigt:
    - Worker-ID und Hostname
    - Status (online/offline/busy)
    - Aktive Tasks
    - Verarbeitete Tasks seit Start
    - GPU-Status
    """
    try:
        from app.workers.celery_app import celery_app

        workers = []
        online_count = 0
        busy_count = 0

        # Inspect workers
        inspect = celery_app.control.inspect()

        # Get ping responses (online workers)
        ping_response = inspect.ping() or {}

        # Get active tasks
        active_tasks = inspect.active() or {}

        # Get stats
        stats = inspect.stats() or {}

        for worker_name in set(list(ping_response.keys()) + list(stats.keys())):
            is_online = worker_name in ping_response
            worker_active = active_tasks.get(worker_name, [])
            worker_stats = stats.get(worker_name, {})

            current_task = None
            current_task_id = None
            if worker_active:
                current_task = worker_active[0].get("name", "Unknown")
                current_task_id = worker_active[0].get("id")

            worker_status = "offline"
            if is_online:
                worker_status = "busy" if worker_active else "online"
                online_count += 1
                if worker_active:
                    busy_count += 1

            # Parse hostname from worker name (format: celery@hostname)
            hostname = worker_name.split("@")[1] if "@" in worker_name else worker_name

            workers.append(WorkerStatus(
                id=worker_name,
                hostname=hostname,
                status=worker_status,
                active_tasks=len(worker_active),
                current_task=current_task,
                current_task_id=current_task_id,
                last_heartbeat=utc_now() if is_online else None,
                tasks_processed=worker_stats.get("total", {}).get("completed", 0) if worker_stats else 0,
                pool_size=worker_stats.get("pool", {}).get("max-concurrency", 1) if worker_stats else 1,
                prefetch_count=worker_stats.get("prefetch_count", 1) if worker_stats else 1,
            ))

        # Get GPU status
        gpu_status = await _get_gpu_status()

        return WorkerListResponse(
            workers=workers,
            total_workers=len(workers),
            online_workers=online_count,
            busy_workers=busy_count,
            gpu=gpu_status,
        )

    except Exception as e:
        # Return empty list on error
        return WorkerListResponse(
            workers=[],
            total_workers=0,
            online_workers=0,
            busy_workers=0,
            gpu=GPUStatus(),
        )


@router.get(
    "/workers/health",
    summary="Worker-Gesundheit",
    description="Ruft detaillierte Gesundheitsinformationen aller Worker ab"
)
async def get_workers_health(
    admin: User = Depends(get_current_superuser),
) -> dict:
    """
    Ruft detaillierte Gesundheitsinformationen aller Worker ab.

    Zeigt:
    - Worker-Status und Heartbeat
    - Stuck Tasks (>10 Minuten)
    - GPU-Lock-Status
    - Warnungen und Fehler
    """
    try:
        from app.workers.celery_app import get_worker_health_status
        return get_worker_health_status()
    except Exception as e:
        return {**safe_error_log(e), "workers": [],
            "total_workers": 0,
            "healthy_workers": 0,
            "unhealthy_workers": 0,
            "stale_tasks": [],
            "warnings": [],
            "errors": [safe_error_detail(e, "Vorgang")],
        }


# ==================== Helper Functions ====================

async def _get_gpu_status() -> GPUStatus:
    """Get current GPU status."""
    try:
        import torch

        if not torch.cuda.is_available():
            return GPUStatus(available=False)

        # Get GPU info
        device = torch.cuda.current_device()
        name = torch.cuda.get_device_name(device)

        memory_allocated = torch.cuda.memory_allocated(device) / 1024 / 1024
        memory_reserved = torch.cuda.memory_reserved(device) / 1024 / 1024
        memory_total = torch.cuda.get_device_properties(device).total_memory / 1024 / 1024
        memory_percent = (memory_allocated / memory_total) * 100 if memory_total > 0 else 0

        # Check GPU lock status
        lock_held = False
        lock_holder = None
        try:
            from app.workers.celery_app import check_gpu_lock_health

            lock_status = check_gpu_lock_health()
            lock_held = lock_status.get("locked", False)
            lock_holder = lock_status.get("owner")
        except Exception as e:
            logger.debug(
                "gpu_lock_health_check_failed",
                error_type=type(e).__name__,
            )

        return GPUStatus(
            available=True,
            name=name,
            memory_used_mb=int(memory_allocated),
            memory_total_mb=int(memory_total),
            memory_percent=round(memory_percent, 1),
            utilization_percent=0.0,  # Would need pynvml for this
            temperature_celsius=None,  # Would need pynvml for this
            lock_held=lock_held,
            lock_holder=lock_holder,
        )

    except Exception:
        return GPUStatus(available=False)
