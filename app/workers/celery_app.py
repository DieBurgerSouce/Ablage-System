"""
Celery Application Configuration
Distributed task queue for async OCR processing
Priority: P0 - CRITICAL
Created: 2024-11-22
"""
from celery import Celery
from kombu import Queue, Exchange
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS
# ============================================================================

def _safe_int_env(key: str, default: int) -> int:
    """Safely get integer from environment variable."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid integer for {key}='{value}', using default {default}")
        return default


# ============================================================================
# CONFIGURATION
# ============================================================================

class CeleryConfig:
    """Celery configuration from environment"""

    # Broker & Backend
    BROKER_URL = os.getenv(
        "CELERY_BROKER_URL",
        "redis://localhost:6379/1"
    )
    RESULT_BACKEND = os.getenv(
        "CELERY_RESULT_BACKEND",
        "redis://localhost:6379/2"
    )

    # Task settings
    TASK_SERIALIZER = "json"
    RESULT_SERIALIZER = "json"
    ACCEPT_CONTENT = ["json"]
    TIMEZONE = "Europe/Berlin"
    ENABLE_UTC = True

    # Task execution
    TASK_TRACK_STARTED = True
    TASK_TIME_LIMIT = _safe_int_env("CELERY_TASK_TIME_LIMIT", 600)  # 10 minutes
    TASK_SOFT_TIME_LIMIT = _safe_int_env("CELERY_TASK_SOFT_TIME_LIMIT", 540)  # 9 minutes
    TASK_ACKS_LATE = True
    WORKER_PREFETCH_MULTIPLIER = 1  # Important for GPU workers

    # Result backend
    RESULT_EXPIRES = 3600  # 1 hour
    RESULT_PERSISTENT = True

    # Worker settings
    WORKER_LOG_FORMAT = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
    WORKER_TASK_LOG_FORMAT = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"

    # Queues
    TASK_DEFAULT_QUEUE = "default"
    TASK_DEFAULT_EXCHANGE = "tasks"
    TASK_DEFAULT_ROUTING_KEY = "default"

    TASK_QUEUES = (
        Queue("default", Exchange("tasks"), routing_key="default"),
        Queue("ocr_gpu", Exchange("tasks"), routing_key="ocr.gpu"),
        Queue("ocr_cpu", Exchange("tasks"), routing_key="ocr.cpu"),
        Queue("priority", Exchange("tasks"), routing_key="priority"),
    )

    TASK_ROUTES = {
        "app.workers.tasks.ocr_tasks.process_document_gpu": {
            "queue": "ocr_gpu",
            "routing_key": "ocr.gpu",
        },
        "app.workers.tasks.ocr_tasks.process_document_cpu": {
            "queue": "ocr_cpu",
            "routing_key": "ocr.cpu",
        },
        "app.workers.tasks.ocr_tasks.batch_process_documents": {
            "queue": "ocr_gpu",
            "routing_key": "ocr.gpu",
        },
        "app.workers.tasks.ocr_tasks.process_document_workflow": {
            "queue": "ocr_gpu",
            "routing_key": "ocr.gpu",
        },
    }

    # Retry policy
    TASK_AUTORETRY_FOR = (Exception,)
    TASK_RETRY_KWARGS = {
        "max_retries": 3,
        "countdown": 60  # Retry after 60 seconds
    }


# ============================================================================
# CELERY APPLICATION
# ============================================================================

# Initialize Celery app
celery_app = Celery("ablage_ocr")

# Load configuration
celery_app.config_from_object(CeleryConfig)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers.tasks"])

logger.info(
    "celery_initialized",
    broker=CeleryConfig.BROKER_URL.split("@")[-1],  # Hide credentials
    backend=CeleryConfig.RESULT_BACKEND.split("@")[-1]
)


# ============================================================================
# CELERY SIGNALS
# ============================================================================

from celery.signals import task_prerun, task_postrun, task_failure


@task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **extra):
    """Log when task starts"""
    logger.info(
        f"task_started: {task.name}",
        task_id=task_id,
        args=args,
        kwargs=kwargs
    )


@task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, **extra):
    """Log when task completes"""
    logger.info(
        f"task_completed: {task.name}",
        task_id=task_id,
        result=str(retval)[:100]  # Limit result logging
    )


@task_failure.connect
def task_failure_handler(task_id, exception, args, kwargs, traceback, einfo, **extra):
    """Log task failures"""
    logger.error(
        f"task_failed",
        task_id=task_id,
        exception=str(exception),
        traceback=str(traceback)[:500]
    )


# ============================================================================
# HEALTH CHECK TASK
# ============================================================================

@celery_app.task(name="health_check")
def health_check_task():
    """Simple health check task"""
    return {"status": "healthy", "message": "Celery worker is running"}
