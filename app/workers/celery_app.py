"""Celery application configuration for async task processing."""

import os
import time
import structlog
from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import task_prerun, task_postrun, task_failure, task_retry, task_success
from contextlib import contextmanager
from typing import Any, Optional
import torch
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Redis client for distributed GPU lock
_redis_lock_client: Optional[Redis] = None
_GPU_LOCK_KEY = "ablage:gpu:lock"
_GPU_LOCK_TIMEOUT = 300  # 5 minutes max lock hold time


def _get_redis_lock_client() -> Redis:
    """Get or create Redis client for distributed locking."""
    global _redis_lock_client
    if _redis_lock_client is None:
        _redis_lock_client = Redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=False,
            socket_timeout=5.0,
            socket_connect_timeout=5.0
        )
    return _redis_lock_client


def acquire_gpu_lock(timeout: int = _GPU_LOCK_TIMEOUT) -> str:
    """Acquire distributed GPU lock using Redis.

    Args:
        timeout: Maximum time to wait for lock (seconds)

    Returns:
        Lock value (used for release verification)

    Raises:
        RuntimeError: If lock cannot be acquired within timeout
    """
    redis = _get_redis_lock_client()
    lock_value = f"worker:{os.getpid()}:{time.time()}"

    # Try to acquire lock with timeout
    for attempt in range(timeout):
        try:
            acquired = redis.set(
                _GPU_LOCK_KEY,
                lock_value,
                nx=True,  # Only set if not exists
                ex=_GPU_LOCK_TIMEOUT  # Auto-expire after timeout
            )
            if acquired:
                logger.debug("gpu_lock_acquired", lock_value=lock_value, attempt=attempt)
                return lock_value
        except RedisError as e:
            logger.warning("gpu_lock_redis_error", error=str(e), attempt=attempt)

        # Wait before retry
        time.sleep(1)

    raise RuntimeError(
        f"GPU-Lock nicht verfügbar nach {timeout} Sekunden. "
        "Ein anderer Worker verarbeitet derzeit einen GPU-Task."
    )


def release_gpu_lock(lock_value: str) -> bool:
    """Release distributed GPU lock.

    Args:
        lock_value: The value returned by acquire_gpu_lock

    Returns:
        True if lock was released, False if lock was not owned by us
    """
    try:
        redis = _get_redis_lock_client()
        current_value = redis.get(_GPU_LOCK_KEY)

        # Only release if we own the lock (compare bytes)
        if current_value == lock_value.encode():
            redis.delete(_GPU_LOCK_KEY)
            logger.debug("gpu_lock_released", lock_value=lock_value)
            return True
        else:
            logger.warning(
                "gpu_lock_not_owned",
                expected=lock_value,
                current=current_value.decode() if current_value else None
            )
            return False
    except RedisError as e:
        logger.error("gpu_lock_release_error", error=str(e), lock_value=lock_value)
        return False


@contextmanager
def distributed_gpu_lock(timeout: int = _GPU_LOCK_TIMEOUT):
    """Context manager for distributed GPU lock.

    Usage:
        with distributed_gpu_lock():
            # GPU-intensive operation
            pass
    """
    lock_value = acquire_gpu_lock(timeout)
    try:
        yield lock_value
    finally:
        release_gpu_lock(lock_value)


# Create Celery app
celery_app = Celery(
    "ablage_system",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.ocr_tasks",
        "app.workers.tasks.embedding_tasks",
        "app.workers.tasks.backup_tasks",
        "app.workers.tasks.cleanup_tasks",
        "app.workers.tasks.gdpr_tasks",
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_extended=True,
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_send_sent_event=True,
    task_time_limit=settings.OCR_TIMEOUT_SECONDS,
    task_soft_time_limit=settings.OCR_TIMEOUT_SECONDS - 30,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # Critical for GPU tasks - one task at a time

    # Result backend
    result_expires=3600 * 24,  # 24 hours
    result_backend_always_retry=True,
    result_backend_max_retries=10,
    result_compression="gzip",

    # Worker settings
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks (memory management)
    worker_disable_rate_limits=False,
    worker_send_task_events=True,
    worker_pool="solo",  # Single process pool for GPU isolation

    # Beat schedule (for periodic tasks)
    beat_schedule={
        "cleanup-old-results": {
            "task": "app.workers.tasks.ocr_tasks.cleanup_task",
            "schedule": 3600.0,  # Every hour
            "args": (24,),  # Cleanup results older than 24 hours
        },
        "update-system-metrics": {
            "task": "app.workers.tasks.ocr_tasks.update_system_metrics",
            "schedule": 300.0,  # Every 5 minutes
        },
        "refresh-search-analytics": {
            "task": "app.workers.tasks.embedding_tasks.refresh_search_analytics",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2:00 AM
        },
        # Backup Tasks
        "backup-full-daily": {
            "task": "app.workers.tasks.backup_tasks.backup_full_task",
            "schedule": crontab(hour=2, minute=30),  # Taeglich um 02:30 Uhr
        },
        "backup-retention-weekly": {
            "task": "app.workers.tasks.backup_tasks.apply_retention_task",
            "schedule": crontab(day_of_week=0, hour=3, minute=0),  # Sonntag 03:00
        },
        "backup-remote-sync-daily": {
            "task": "app.workers.tasks.backup_tasks.sync_to_remote_task",
            "schedule": crontab(hour=4, minute=0),  # Taeglich um 04:00 Uhr
        },
        "backup-metrics-update": {
            "task": "app.workers.tasks.backup_tasks.update_backup_metrics_task",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # Cleanup Tasks (GDPR-konform)
        "cleanup-soft-deleted-daily": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_soft_deleted_documents",
            "schedule": crontab(hour=3, minute=30),  # Taeglich um 03:30 Uhr
            "kwargs": {"retention_days": 30, "dry_run": False},
        },
        "cleanup-orphaned-files-weekly": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_orphaned_files",
            "schedule": crontab(day_of_week=6, hour=4, minute=30),  # Samstag 04:30
        },
        "cleanup-expired-cache-daily": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_expired_cache",
            "schedule": crontab(hour=5, minute=0),  # Taeglich um 05:00 Uhr
        },
        "cleanup-search-analytics-monthly": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_search_analytics",
            "schedule": crontab(day_of_month=1, hour=4, minute=0),  # Monatlich am 1. um 04:00
            "kwargs": {"retention_months": 6, "dry_run": False},
        },
        # GDPR Automatisierung (Art. 17, 30, 33 DSGVO)
        "gdpr-process-deletion-requests": {
            "task": "app.workers.tasks.gdpr_tasks.process_deletion_requests",
            "schedule": crontab(hour="*/6"),  # Alle 6 Stunden
        },
        "gdpr-check-retention-compliance": {
            "task": "app.workers.tasks.gdpr_tasks.check_retention_compliance",
            "schedule": crontab(hour=1, minute=0),  # Täglich um 01:00 Uhr
            "kwargs": {"dry_run": False},
        },
        "gdpr-generate-compliance-report": {
            "task": "app.workers.tasks.gdpr_tasks.generate_compliance_report",
            "schedule": crontab(day_of_week=1, hour=6, minute=0),  # Montag 06:00
        },
    },

    # Queue routing
    task_routes={
        # OCR tasks
        "app.workers.tasks.ocr_tasks.process_document_task": {"queue": "ocr_high", "priority": 9},
        "app.workers.tasks.ocr_tasks.batch_process_task": {"queue": "ocr_normal", "priority": 5},
        "app.workers.tasks.ocr_tasks.validate_german_text_task": {"queue": "validation", "priority": 3},
        "app.workers.tasks.ocr_tasks.extract_metadata_task": {"queue": "metadata", "priority": 3},
        "app.workers.tasks.ocr_tasks.cleanup_task": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.ocr_tasks.update_system_metrics": {"queue": "metrics", "priority": 1},
        # Embedding tasks (GPU)
        "app.workers.tasks.embedding_tasks.generate_document_embedding": {"queue": "embedding_high", "priority": 8},
        "app.workers.tasks.embedding_tasks.batch_generate_embeddings": {"queue": "embedding_normal", "priority": 5},
        "app.workers.tasks.embedding_tasks.regenerate_all_embeddings": {"queue": "embedding_low", "priority": 2},
        "app.workers.tasks.embedding_tasks.check_embedding_coverage": {"queue": "maintenance", "priority": 1},
        # Search analytics tasks (CPU)
        "app.workers.tasks.embedding_tasks.refresh_search_analytics": {"queue": "maintenance", "priority": 1},
        # Backup tasks (CPU)
        "app.workers.tasks.backup_tasks.backup_full_task": {"queue": "backup", "priority": 2},
        "app.workers.tasks.backup_tasks.backup_postgres_task": {"queue": "backup", "priority": 3},
        "app.workers.tasks.backup_tasks.backup_redis_task": {"queue": "backup", "priority": 3},
        "app.workers.tasks.backup_tasks.apply_retention_task": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.backup_tasks.sync_to_remote_task": {"queue": "backup", "priority": 2},
        "app.workers.tasks.backup_tasks.update_backup_metrics_task": {"queue": "metrics", "priority": 1},
        # Cleanup tasks (GDPR)
        "app.workers.tasks.cleanup_tasks.cleanup_soft_deleted_documents": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.cleanup_tasks.cleanup_orphaned_files": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.cleanup_tasks.cleanup_expired_cache": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.cleanup_tasks.cleanup_search_analytics": {"queue": "maintenance", "priority": 1},
    },

    # Priority settings
    task_default_priority=5,
    task_inherit_parent_priority=True,
    worker_direct=True,
    task_create_missing_queues=True,

    # Dead letter queue settings
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True,
)


class GPUTask(Task):
    """Base task class for GPU-intensive operations.

    Ensures only one GPU task executes at a time to prevent VRAM overflow.
    Uses Redis-based distributed lock to coordinate across multiple workers.
    Automatically manages GPU memory and provides error recovery.
    """

    autoretry_for = (torch.cuda.OutOfMemoryError, RuntimeError)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True

    # Instance variable to store lock value for release
    _current_lock_value: Optional[str] = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task with GPU memory management."""
        with gpu_memory_guard():
            return super().__call__(*args, **kwargs)

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Acquire GPU resources before task execution using distributed lock."""
        logger.info("gpu_task_starting", task_id=task_id, task_name=self.name)
        # Acquire distributed GPU lock (works across all workers)
        try:
            self._current_lock_value = acquire_gpu_lock()
            logger.debug("gpu_lock_acquired_for_task", task_id=task_id, lock_value=self._current_lock_value)
        except RuntimeError as e:
            logger.error("gpu_lock_acquisition_failed", task_id=task_id, error=str(e))
            raise

    def after_return(
        self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Optional[Any]
    ) -> None:
        """Release GPU resources after task completion."""
        try:
            # Clear GPU cache to prevent memory leaks
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info("gpu_task_completed", task_id=task_id, task_name=self.name, status=status, has_error=einfo is not None)
        finally:
            # Always release distributed GPU lock
            if self._current_lock_value:
                released = release_gpu_lock(self._current_lock_value)
                if released:
                    logger.debug("gpu_lock_released_for_task", task_id=task_id)
                self._current_lock_value = None

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any
    ) -> None:
        """Handle task retry."""
        logger.warning("gpu_task_retrying", task_id=task_id, task_name=self.name, exception=str(exc), retry_count=self.request.retries)
        # Clear GPU memory before retry
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        # Release lock before retry (will be re-acquired on next attempt)
        if self._current_lock_value:
            release_gpu_lock(self._current_lock_value)
            self._current_lock_value = None


class CPUTask(Task):
    """Base task class for CPU-only operations."""

    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 300  # Max 5 minutes
    retry_jitter = True


@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6):
    """Context manager to ensure GPU memory stays below threshold (85% of 16GB).

    Args:
        threshold_gb: Maximum GPU memory in GB (default: 13.6 = 85% of 16GB)
    """
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        yield
    finally:
        if torch.cuda.is_available():
            current_memory = torch.cuda.memory_allocated() / 1024**3
            if current_memory > threshold_gb:
                logger.warning("gpu_memory_high", current_gb=round(current_memory, 2), threshold_gb=threshold_gb)
                torch.cuda.empty_cache()


# Signal handlers for monitoring and callbacks
@task_prerun.connect
def task_prerun_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    task: Optional[Task] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    **extra: Any
) -> None:
    """Log task start and update database status."""
    task_name = task.name if task else None
    logger.info("task_starting", task_id=task_id, task_name=task_name)


@task_postrun.connect
def task_postrun_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    task: Optional[Task] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    retval: Optional[Any] = None,
    state: Optional[str] = None,
    **extra: Any
) -> None:
    """Log task completion and cleanup GPU memory."""
    task_name = task.name if task else None
    logger.info("task_completed", task_id=task_id, task_name=task_name, state=state)

    # Clear GPU memory for GPU tasks
    if task and hasattr(task, "__class__") and issubclass(task.__class__, GPUTask):
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


@task_failure.connect
def task_failure_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    exception: Optional[Exception] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    traceback: Optional[Any] = None,
    einfo: Optional[Any] = None,
    **extra: Any
) -> None:
    """Log task failure and cleanup resources."""
    task_name = sender.name if sender else None
    logger.error("task_failed", task_id=task_id, task_name=task_name, exception=str(exception), exc_info=True)

    # Clear GPU memory on failure
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Note: Distributed GPU lock is released in GPUTask.after_return
    # Redis lock auto-expires after _GPU_LOCK_TIMEOUT seconds as fallback


@task_retry.connect
def task_retry_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    reason: Optional[str] = None,
    einfo: Optional[Any] = None,
    **extra: Any
) -> None:
    """Log task retry attempts."""
    task_name = sender.name if sender else None
    logger.warning("task_retrying", task_id=task_id, task_name=task_name, reason=str(reason))


@task_success.connect
def task_success_handler(
    sender: Optional[Task] = None,
    result: Optional[Any] = None,
    **extra: Any
) -> None:
    """Log successful task completion."""
    task_name = sender.name if sender else None
    logger.info("task_success", task_name=task_name)
