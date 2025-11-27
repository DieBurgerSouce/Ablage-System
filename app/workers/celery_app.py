"""Celery application configuration for async task processing."""

import logging
from celery import Celery, Task
from celery.signals import task_prerun, task_postrun, task_failure, task_retry, task_success
from contextlib import contextmanager
from typing import Any, Optional
import torch
import threading

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# GPU lock for single GPU task execution
_gpu_lock = threading.Lock()


# Create Celery app
celery_app = Celery(
    "ablage_system",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.ocr_tasks"]
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
    },

    # Queue routing
    task_routes={
        "app.workers.tasks.ocr_tasks.process_document_task": {"queue": "ocr_high", "priority": 9},
        "app.workers.tasks.ocr_tasks.batch_process_task": {"queue": "ocr_normal", "priority": 5},
        "app.workers.tasks.ocr_tasks.validate_german_text_task": {"queue": "validation", "priority": 3},
        "app.workers.tasks.ocr_tasks.extract_metadata_task": {"queue": "metadata", "priority": 3},
        "app.workers.tasks.ocr_tasks.cleanup_task": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.ocr_tasks.update_system_metrics": {"queue": "metrics", "priority": 1},
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
    Automatically manages GPU memory and provides error recovery.
    """

    autoretry_for = (torch.cuda.OutOfMemoryError, RuntimeError)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task with GPU memory management."""
        with gpu_memory_guard():
            return super().__call__(*args, **kwargs)

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Acquire GPU resources before task execution."""
        logger.info(
            f"gpu_task_starting - task_id={task_id} task_name={self.name} args={args} kwargs={kwargs}"
        )
        # Acquire GPU lock
        _gpu_lock.acquire()

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

            logger.info(
                f"gpu_task_completed - task_id={task_id} task_name={self.name} status={status} has_error={einfo is not None}"
            )
        finally:
            # Always release GPU lock
            if _gpu_lock.locked():
                _gpu_lock.release()

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any
    ) -> None:
        """Handle task retry."""
        logger.warning(
            f"gpu_task_retrying - task_id={task_id} task_name={self.name} exception={str(exc)} retry_count={self.request.retries}"
        )
        # Clear GPU memory before retry
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


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
                logger.warning(
                    f"gpu_memory_high - current_gb={current_memory} threshold_gb={threshold_gb}"
                )
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
    logger.info(
        f"task_starting - task_id={task_id} task_name={task_name} args={args} kwargs={kwargs}"
    )


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
    logger.info(
        f"task_completed - task_id={task_id} task_name={task_name} state={state}"
    )

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
    logger.error(
        f"task_failed - task_id={task_id} task_name={task_name} exception={str(exception)}",
        exc_info=True
    )

    # Clear GPU memory on failure
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Release GPU lock if held
    if _gpu_lock.locked():
        _gpu_lock.release()


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
    logger.warning(
        f"task_retrying - task_id={task_id} task_name={task_name} reason={str(reason)}"
    )


@task_success.connect
def task_success_handler(
    sender: Optional[Task] = None,
    result: Optional[Any] = None,
    **extra: Any
) -> None:
    """Log successful task completion."""
    task_name = sender.name if sender else None
    logger.info(f"task_success - task_name={task_name}")
