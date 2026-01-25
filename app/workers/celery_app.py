"""Celery application configuration for async task processing."""

import os
import time
import random
from datetime import datetime, timezone
import structlog
from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import (
    task_prerun, task_postrun, task_failure, task_retry, task_success,
    worker_ready, worker_shutdown, celeryd_init
)
from contextlib import contextmanager
from typing import Any, Dict, Optional
import torch
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.workers.celery_metrics import (
    record_task_started, record_task_succeeded, record_task_failed,
    record_task_retried, record_gpu_oom, init_worker_metrics,
    shutdown_worker_metrics, start_metrics_server, stop_metrics_server,
    set_gpu_lock_status, update_gpu_metrics
)

logger = structlog.get_logger(__name__)

# Redis client for distributed GPU lock
_redis_lock_client: Optional[Redis] = None
_GPU_LOCK_KEY = "ablage:gpu:lock"
# GPU Lock Timeouts (aus config.py)
_GPU_LOCK_TIMEOUT = settings.GPU_LOCK_TIMEOUT
_GPU_LOCK_ACQUIRE_TIMEOUT = settings.GPU_LOCK_ACQUIRE_TIMEOUT
_GPU_LOCK_RETRY_INTERVAL = settings.GPU_LOCK_RETRY_INTERVAL


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


def acquire_gpu_lock(timeout: int = _GPU_LOCK_ACQUIRE_TIMEOUT) -> str:
    """Acquire distributed GPU lock using Redis.

    Uses short retry intervals (100ms) to minimize blocking.
    Lock auto-expires after 60 seconds (use refresh_gpu_lock for long tasks).

    Args:
        timeout: Maximum time to wait for lock (seconds), default 30s

    Returns:
        Lock value (used for release verification and refresh)

    Raises:
        RuntimeError: If lock cannot be acquired within timeout
    """
    redis = _get_redis_lock_client()
    lock_value = f"worker:{os.getpid()}:{time.time()}"

    # Calculate max attempts based on retry interval
    max_attempts = int(timeout / _GPU_LOCK_RETRY_INTERVAL)
    start_time = time.time()

    for attempt in range(max_attempts):
        try:
            acquired = redis.set(
                _GPU_LOCK_KEY,
                lock_value,
                nx=True,  # Only set if not exists
                ex=_GPU_LOCK_TIMEOUT  # Auto-expire after 60s
            )
            if acquired:
                elapsed = time.time() - start_time
                logger.debug(
                    "gpu_lock_acquired",
                    lock_value=lock_value,
                    attempts=attempt + 1,
                    elapsed_ms=int(elapsed * 1000)
                )
                return lock_value
        except RedisError as e:
            # Fix 10: Exponential Backoff mit Jitter bei Redis-Fehlern
            base_delay = _GPU_LOCK_RETRY_INTERVAL * (2 ** min(attempt, 5))  # Max 2^5 = 32x
            jitter = random.uniform(0, base_delay * 0.5)  # 0-50% Jitter
            retry_delay = min(base_delay + jitter, 5.0)  # Max 5 Sekunden
            logger.warning(
                "gpu_lock_redis_error",
                error=str(e),
                attempt=attempt,
                retry_delay_ms=int(retry_delay * 1000)
            )
            time.sleep(retry_delay)
            continue

        # Short non-blocking sleep (100ms) fuer normale Lock-Checks
        time.sleep(_GPU_LOCK_RETRY_INTERVAL)

    elapsed = time.time() - start_time
    raise RuntimeError(
        f"GPU-Lock nicht verfügbar nach {elapsed:.1f} Sekunden ({max_attempts} Versuche). "
        "Ein anderer Worker verarbeitet derzeit einen GPU-Task."
    )


def refresh_gpu_lock(lock_value: str, extend_seconds: int = _GPU_LOCK_TIMEOUT) -> bool:
    """Refresh/extend GPU lock TTL for long-running tasks.

    Should be called periodically (every 30s) for tasks > 60 seconds.

    Args:
        lock_value: The value returned by acquire_gpu_lock
        extend_seconds: New TTL in seconds (default 60s)

    Returns:
        True if lock was refreshed, False if lock expired or not owned
    """
    try:
        redis = _get_redis_lock_client()
        current_value = redis.get(_GPU_LOCK_KEY)

        # Only refresh if we still own the lock
        if current_value == lock_value.encode():
            redis.expire(_GPU_LOCK_KEY, extend_seconds)
            logger.debug("gpu_lock_refreshed", lock_value=lock_value, new_ttl=extend_seconds)
            return True
        else:
            logger.warning(
                "gpu_lock_refresh_failed_not_owned",
                expected=lock_value,
                current=current_value.decode() if current_value else None
            )
            return False
    except RedisError as e:
        logger.error("gpu_lock_refresh_error", error=str(e), lock_value=lock_value)
        return False


def release_gpu_lock(lock_value: str) -> bool:
    """Release distributed GPU lock.

    Uses Redis WATCH/MULTI/EXEC for atomic check-and-delete.

    Args:
        lock_value: The value returned by acquire_gpu_lock

    Returns:
        True if lock was released, False if lock was not owned by us
    """
    try:
        redis = _get_redis_lock_client()

        # Use pipeline with WATCH for atomic check-and-delete
        with redis.pipeline() as pipe:
            try:
                # Watch the key for changes
                pipe.watch(_GPU_LOCK_KEY)
                current_value = pipe.get(_GPU_LOCK_KEY)

                # Only delete if we own the lock
                if current_value == lock_value.encode():
                    pipe.multi()
                    pipe.delete(_GPU_LOCK_KEY)
                    pipe.execute()
                    logger.debug("gpu_lock_released", lock_value=lock_value)
                    return True
                else:
                    pipe.unwatch()
                    logger.warning(
                        "gpu_lock_not_owned",
                        expected=lock_value,
                        current=current_value.decode() if current_value else None
                    )
                    return False
            except Exception:
                pipe.unwatch()
                raise

    except RedisError as e:
        logger.error("gpu_lock_release_error", error=str(e), lock_value=lock_value)
        # Force delete on error to prevent deadlock
        try:
            redis = _get_redis_lock_client()
            redis.delete(_GPU_LOCK_KEY)
            logger.warning("gpu_lock_force_released", lock_value=lock_value)
        except RedisError:
            pass
        return False


def check_gpu_lock_health() -> dict:
    """Check GPU lock status for monitoring/debugging.

    Returns:
        Dict with lock status, owner, and TTL
    """
    try:
        redis = _get_redis_lock_client()
        current_value = redis.get(_GPU_LOCK_KEY)
        ttl = redis.ttl(_GPU_LOCK_KEY)

        if current_value:
            return {
                "locked": True,
                "owner": current_value.decode(),
                "ttl_seconds": ttl if ttl > 0 else 0,
                "status": "healthy" if ttl > 10 else "expiring_soon"
            }
        else:
            return {
                "locked": False,
                "owner": None,
                "ttl_seconds": 0,
                "status": "available"
            }
    except RedisError as e:
        return {
            "locked": None,
            "owner": None,
            "ttl_seconds": None,
            "status": f"error: {str(e)}"
        }


@contextmanager
def distributed_gpu_lock(timeout: int = _GPU_LOCK_ACQUIRE_TIMEOUT):
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
        "app.workers.tasks.ml_tasks",
        "app.workers.tasks.dlq_management_tasks",  # Dead Letter Queue Management
        "app.workers.tasks.document_intelligence_tasks",  # Document Intelligence (Grouping, Entities)
        "app.workers.tasks.training_tasks",  # OCR Training & Benchmarking
        "app.workers.tasks.extraction_tasks",  # Structured Data Extraction
        "app.workers.tasks.rag_tasks",  # RAG Document Processing
        "app.workers.tasks.monitoring_tasks",  # Worker Health Monitoring
        "app.workers.tasks.surya_improvement_tasks",  # Surya OCR Continuous Improvement
        "app.workers.tasks.export_tasks",  # Export Tasks (Batch, Scheduled)
        "app.workers.tasks.privat_tasks",  # Privat-Modul Intelligence Tasks (KPIs, Deadlines, Financial Health)
        "app.workers.tasks.orchestration_tasks",  # Cross-Module Orchestration (Phase 2 - Intelligent Event Routing)
        "app.workers.tasks.entity_linking_tasks",  # Entity Linking (Lexware Integration - Document-Entity Matching)
        "app.workers.tasks.workflow_tasks",  # Document Workflow Triggers (on_document_created)
        "app.workers.tasks.notification_tasks",  # Notification Tasks (Daily Digest, Cleanup)
        "app.workers.tasks.approval_tasks",  # Approval Workflow Tasks (Escalation, Reminders, Stats)
        "app.workers.tasks.collaboration_tasks",  # Collaboration Tasks (Digest, Task Reminders, Escalation)
        "app.workers.tasks.mlops_tasks",  # MLOps Pipeline (Model Registry, Retraining, Rollback)
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

    # ==========================================================================
    # PRIORITY QUEUE CONFIGURATION
    # ==========================================================================
    # Redis supports priority queues with broker_transport_options
    # Priority range: 0 (highest) to 9 (lowest)
    # Workers should be started with: celery -A app.workers.celery_app worker -Q ocr_high,ocr_normal,embedding_high,embedding_normal,validation,metadata,backup,maintenance,metrics

    broker_transport_options={
        "priority_steps": list(range(10)),  # 0-9 priority levels
        "sep": ":",
        "queue_order_strategy": "priority",  # Process high priority first
        "visibility_timeout": 43200,  # 12 hours (for long-running OCR tasks)
    },

    # ==========================================================================
    # DEAD LETTER QUEUE (DLQ) KONFIGURATION
    # ==========================================================================
    # Fehlgeschlagene Tasks werden NICHT gelöscht, sondern in die DLQ verschoben.
    # Von dort können sie inspiziert, repariert und erneut ausgeführt werden.
    #
    # DLQ Exchange und Queue müssen vorab in Redis/RabbitMQ existieren.
    # Bei Redis wird automatisch eine Liste "dlq" erstellt.

    # Task queues with explicit priority configuration and DLQ support
    task_queues={
        # =================================================================
        # DEAD LETTER QUEUE - Sammelt alle fehlgeschlagenen Tasks
        # =================================================================
        "dlq": {
            "exchange": "dlq",
            "routing_key": "dlq",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-message-ttl": 604800000,  # 7 Tage TTL (ms)
            },
        },

        # =================================================================
        # GPU Tasks (High Priority) - Mit DLQ Routing
        # =================================================================
        "ocr_high": {
            "exchange": "ocr_high",
            "routing_key": "ocr.high",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "ocr_normal": {
            "exchange": "ocr_normal",
            "routing_key": "ocr.normal",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "embedding_high": {
            "exchange": "embedding_high",
            "routing_key": "embedding.high",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "embedding_normal": {
            "exchange": "embedding_normal",
            "routing_key": "embedding.normal",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "embedding_low": {
            "exchange": "embedding_low",
            "routing_key": "embedding.low",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },

        # =================================================================
        # CPU Tasks (Medium Priority) - Mit DLQ Routing
        # =================================================================
        "validation": {
            "exchange": "validation",
            "routing_key": "validation",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "metadata": {
            "exchange": "metadata",
            "routing_key": "metadata",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "backup": {
            "exchange": "backup",
            "routing_key": "backup",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },

        # =================================================================
        # Background Tasks (Low Priority) - Mit DLQ Routing
        # =================================================================
        "maintenance": {
            "exchange": "maintenance",
            "routing_key": "maintenance",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        # =================================================================
        # Privat-Modul Queue (Enterprise Intelligence)
        # =================================================================
        "privat": {
            "exchange": "privat",
            "routing_key": "privat",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        "metrics": {
            "exchange": "metrics",
            "routing_key": "metrics",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        # =================================================================
        # Cross-Module Orchestration Queue (Phase 2 - Enterprise Intelligence)
        # =================================================================
        "orchestration": {
            "exchange": "orchestration",
            "routing_key": "orchestration",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        # =================================================================
        # Approval Workflow Queue (Enterprise Approval Management)
        # =================================================================
        "approval": {
            "exchange": "approval",
            "routing_key": "approval",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        # =================================================================
        # Workflow Execution Queue (Document Workflow Processing)
        # =================================================================
        "workflow": {
            "exchange": "workflow",
            "routing_key": "workflow",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
        # =================================================================
        # Shipment Tracking Queue (Paketdienst-Integration)
        # DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post
        # =================================================================
        "tracking": {
            "exchange": "tracking",
            "routing_key": "tracking",
            "queue_arguments": {
                "x-max-priority": 10,
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": "dlq",
            },
        },
    },

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
            "schedule": crontab(hour=2, minute=5),  # Daily at 2:05 AM (staggered from 02:00)
        },
        # Backup Tasks
        "backup-full-daily": {
            "task": "app.workers.tasks.backup_tasks.backup_full_task",
            "schedule": crontab(hour=2, minute=30),  # Taeglich um 02:30 Uhr
        },
        "backup-retention-weekly": {
            "task": "app.workers.tasks.backup_tasks.apply_retention_task",
            "schedule": crontab(day_of_week=0, hour=3, minute=25),  # Sonntag 03:25 (staggered)
        },
        "backup-remote-sync-daily": {
            "task": "app.workers.tasks.backup_tasks.sync_to_remote_task",
            "schedule": crontab(hour=4, minute=0),  # Taeglich um 04:00 Uhr
        },
        "backup-metrics-update": {
            "task": "app.workers.tasks.backup_tasks.update_backup_metrics_task",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # Audit Archive Tasks (Phase 1.4 - GoBD WORM Storage)
        "audit-archive-monthly": {
            "task": "app.workers.tasks.backup_tasks.archive_audit_logs_monthly_task",
            "schedule": crontab(day_of_month=1, hour=1, minute=0),  # 1. des Monats um 01:00
        },
        "audit-archive-verify-weekly": {
            "task": "app.workers.tasks.backup_tasks.verify_audit_archives_task",
            "schedule": crontab(day_of_week=6, hour=4, minute=0),  # Samstag 04:00
        },
        # Backup Restore Test (Phase 2.3 - Woechentliche Validierung)
        "backup-restore-test-weekly": {
            "task": "app.workers.tasks.backup_tasks.backup_restore_test_task",
            "schedule": crontab(day_of_week=0, hour=2, minute=0),  # Sonntag 02:00
            "kwargs": {"validation_level": "standard", "cleanup_on_success": True},
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
        # Worker Health Monitoring
        "worker-health-check": {
            "task": "app.workers.tasks.monitoring_tasks.worker_health_check_task",
            "schedule": 60.0,  # Jede Minute
        },
        "worker-stuck-task-cleanup": {
            "task": "app.workers.tasks.monitoring_tasks.cleanup_stuck_tasks",
            "schedule": 300.0,  # Alle 5 Minuten
        },
        "queue-backpressure-check": {
            "task": "app.workers.tasks.monitoring_tasks.check_queue_backpressure",
            "schedule": 60.0,  # Jede Minute
        },
        # Session & Token Cleanup (Security)
        "cleanup-expired-sessions-daily": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_expired_sessions",
            "schedule": crontab(hour=2, minute=15),  # Taeglich um 02:15 Uhr
        },
        "cleanup-expired-verification-tokens-daily": {
            "task": "app.workers.tasks.cleanup_tasks.cleanup_expired_verification_tokens",
            "schedule": crontab(hour=2, minute=30),  # Taeglich um 02:30 Uhr
        },
        # ML/Drift Detection Tasks
        "ml-drift-detection": {
            "task": "app.workers.tasks.ml_tasks.run_drift_detection",
            "schedule": 3600.0,  # Stündlich
        },
        "ml-drift-response": {
            "task": "app.workers.tasks.ml_tasks.check_drift_and_respond",
            "schedule": 7200.0,  # Alle 2 Stunden - automatische A/B-Tests bei Drift
        },
        "ml-metrics-update": {
            "task": "app.workers.tasks.ml_tasks.update_ml_metrics",
            "schedule": 60.0,  # Jede Minute (reduziert von 30s für weniger Load)
        },
        "ml-experiment-check": {
            "task": "app.workers.tasks.ml_tasks.check_experiment_completion",
            "schedule": 300.0,  # Alle 5 Minuten
        },
        "ml-apply-winners": {
            "task": "app.workers.tasks.ml_tasks.apply_ab_test_winners",
            "schedule": 1800.0,  # Alle 30 Minuten
        },
        "ml-monthly-report": {
            "task": "app.workers.tasks.ml_tasks.generate_monthly_drift_report",
            "schedule": crontab(day_of_month=1, hour=5, minute=0),  # Monatlich am 1. um 05:00
        },
        # =================================================================
        # Dead Letter Queue (DLQ) Monitoring
        # =================================================================
        "dlq-health-check": {
            "task": "app.workers.tasks.dlq_management_tasks.check_dlq_health",
            "schedule": 300.0,  # Alle 5 Minuten
        },
        "dlq-cleanup-old-tasks": {
            "task": "app.workers.tasks.dlq_management_tasks.cleanup_old_dlq_tasks",
            "schedule": crontab(hour=6, minute=0),  # Täglich um 06:00 Uhr
            "kwargs": {"max_age_days": 7},
        },
        # =================================================================
        # Risk Scoring Tasks (Entity Payment Behavior Analysis)
        # =================================================================
        "risk-scoring-daily-batch": {
            "task": "risk_scoring.calculate_all",
            "schedule": crontab(hour=2, minute=0),  # Taeglich um 02:00 Uhr (Basis-Task)
            "kwargs": {"limit": 1000, "recalculate_all": False},
        },
        "risk-scoring-check-high-risk": {
            "task": "risk_scoring.check_high_risk_entities",
            "schedule": crontab(hour=2, minute=30),  # Taeglich um 02:30 Uhr (nach Batch)
            "kwargs": {"threshold": 75.0},
        },
        "risk-scoring-weekly-statistics": {
            "task": "risk_scoring.generate_statistics",
            "schedule": crontab(day_of_week=1, hour=6, minute=30),  # Montag 06:30 Uhr
        },
        # =================================================================
        # Document Intelligence Tasks (Grouping & Entity Extraction)
        # =================================================================
        "document-intelligence-pipeline": {
            "task": "app.workers.tasks.document_intelligence_tasks.run_document_intelligence_pipeline",
            "schedule": crontab(hour=3, minute=0),  # Taeglich um 03:00 Uhr (Basis-Task)
        },
        "document-intelligence-metrics": {
            "task": "app.workers.tasks.document_intelligence_tasks.update_intelligence_metrics",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # =================================================================
        # OCR Training Tasks (Benchmarking & Self-Learning)
        # =================================================================
        "training-daily-stats": {
            "task": "app.workers.tasks.training_tasks.generate_daily_stats",
            "schedule": crontab(hour=1, minute=0),  # Taeglich um 01:00 Uhr
        },
        "training-feedback-queue": {
            "task": "app.workers.tasks.training_tasks.process_feedback_queue",
            "schedule": 3600.0,  # Stuendlich
        },
        "training-learned-weights": {
            "task": "app.workers.tasks.training_tasks.update_learned_weights",
            "schedule": crontab(hour=2, minute=10),  # Taeglich um 02:10 Uhr (staggered from 02:00)
        },
        "training-weekly-benchmarks": {
            "task": "app.workers.tasks.training_tasks.run_scheduled_benchmarks",
            "schedule": crontab(day_of_week=0, hour=3, minute=5),  # Sonntag 03:05 Uhr (staggered)
        },
        "training-weekly-report": {
            "task": "app.workers.tasks.training_tasks.generate_training_report",
            "schedule": crontab(day_of_week=1, hour=7, minute=0),  # Montag 07:00 Uhr
        },
        # =================================================================
        # OCR Self-Learning Tasks (Persistent DB-based)
        # =================================================================
        "ocr-learning-backend-performance": {
            "task": "app.workers.tasks.ocr_tasks.calculate_ocr_backend_performance",
            "schedule": crontab(hour=2, minute=45),  # Taeglich um 02:45 Uhr (nach Training)
            "kwargs": {"period_days": 30},
        },
        "ocr-learning-process-feedbacks": {
            "task": "app.workers.tasks.ocr_tasks.process_pending_ocr_feedbacks",
            "schedule": crontab(hour="*/4"),  # Alle 4 Stunden
            "kwargs": {"batch_size": 100},
        },
        # =================================================================
        # Export Tasks (Scheduled Exports)
        # =================================================================
        "export-check-scheduled": {
            "task": "export.check_scheduled_exports",
            "schedule": 300.0,  # Alle 5 Minuten
        },
        # =================================================================
        # RAG Intelligence Layer Tasks
        # =================================================================
        "rag-customer-card-sync": {
            "task": "app.workers.tasks.rag_tasks.sync_customer_cards_scheduled",
            "schedule": crontab(hour=3, minute=30),  # Taeglich um 03:30 Uhr
        },
        "rag-chunk-new-documents": {
            "task": "app.workers.tasks.rag_tasks.scheduled_chunk_new_documents",
            "schedule": crontab(hour="*/4"),  # Alle 4 Stunden
        },
        # =================================================================
        # Embedding Coverage Verification
        # =================================================================
        "embedding-coverage-check": {
            "task": "app.workers.tasks.embedding_tasks.check_embedding_coverage",
            "schedule": crontab(hour=6, minute=0),  # Taeglich um 06:00 Uhr
        },
        # =================================================================
        # Qdrant Sync & A/B Testing Tasks
        # =================================================================
        "qdrant-sync-pending-daily": {
            "task": "app.workers.tasks.embedding_tasks.sync_pending_to_qdrant",
            "schedule": crontab(hour=3, minute=10),  # Taeglich um 03:10 Uhr (staggered from 03:00)
            "kwargs": {"limit": 500},
        },
        "vector-ab-test-analysis-daily": {
            "task": "app.workers.tasks.embedding_tasks.analyze_ab_test_metrics",
            "schedule": crontab(hour=7, minute=0),  # Taeglich um 07:00 Uhr
            "kwargs": {"days": 7},
        },
        # =================================================================
        # Surya OCR Continuous Improvement (Self-Learning Loop)
        # =================================================================
        # Taeglich: Pruefe ob Retraining-Bedingungen erfuellt sind
        "surya-check-retraining-daily": {
            "task": "app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions",
            "schedule": crontab(hour=2, minute=20),  # Taeglich um 02:20 Uhr (staggered from 02:00)
        },
        # Woechentlich: Benchmark gegen Ground Truth Fixtures
        "surya-weekly-benchmark": {
            "task": "app.workers.tasks.surya_improvement_tasks.run_surya_benchmark",
            "schedule": crontab(day_of_week=0, hour=3, minute=15),  # Sonntag 03:15 Uhr (staggered)
        },
        # Taeglich: Verarbeite Surya-Korrekturen zu Training Samples
        "surya-process-corrections": {
            "task": "app.workers.tasks.surya_improvement_tasks.process_surya_corrections",
            "schedule": crontab(hour=4, minute=0),  # Taeglich um 04:00 Uhr
        },
        # Alle 6 Stunden: Pruefe aktive A/B Tests auf Completion
        "surya-evaluate-ab-tests": {
            "task": "app.workers.tasks.surya_improvement_tasks.evaluate_surya_ab_test",
            "schedule": crontab(hour="*/6"),  # Alle 6 Stunden
        },
        # Alle 15 Minuten: Aktualisiere Surya-Metriken fuer Monitoring
        "surya-update-metrics": {
            "task": "app.workers.tasks.surya_improvement_tasks.update_surya_metrics",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # Monatlich: Generiere Surya Improvement Report
        "surya-monthly-report": {
            "task": "app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report",
            "schedule": crontab(day_of_month=1, hour=6, minute=0),  # Monatlich am 1. um 06:00 Uhr
        },
        # =================================================================
        # Notification Tasks (E-Mail Digests)
        # =================================================================
        "notification-daily-digest": {
            "task": "app.workers.tasks.notification_tasks.send_daily_digest",
            "schedule": crontab(hour=8, minute=0),  # Taeglich um 08:00 Uhr
        },
        "notification-weekly-digest": {
            "task": "app.workers.tasks.notification_tasks.send_weekly_digest",
            "schedule": crontab(day_of_week=1, hour=8, minute=0),  # Montag 08:00 Uhr
        },
        "notification-cleanup-old": {
            "task": "app.workers.tasks.notification_tasks.cleanup_old_notifications",
            "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sonntag 04:00 Uhr
            "kwargs": {"days": 90},
        },
        # Dunning Email Retry - Stuendlich fehlgeschlagene Mahnungen wiederholen
        "notification-retry-failed-dunning-emails": {
            "task": "app.workers.tasks.notification_tasks.retry_failed_dunning_emails",
            "schedule": 3600.0,  # Stuendlich (jede Stunde)
        },
        # =================================================================
        # GoBD Retention Tasks (Aufbewahrungsfristen-Management)
        # =================================================================
        "retention-check-expiring-daily": {
            "task": "retention.check_expiring_archives",
            "schedule": crontab(hour=8, minute=15),  # Taeglich um 08:15 Uhr (nach Digest)
            "kwargs": {"days_ahead": 90},
        },
        "retention-verify-integrity-weekly": {
            "task": "retention.verify_archive_integrity",
            "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sonntag 04:00 Uhr
            "kwargs": {"batch_size": 500},
        },
        "retention-process-expired-daily": {
            "task": "retention.process_expired_archives",
            "schedule": crontab(hour=2, minute=45),  # Taeglich um 02:45 Uhr
        },
        # =================================================================
        # Privat-Modul Intelligence Tasks (KPIs, Deadlines, Financial Health)
        # =================================================================
        # Deadline Reminders - Taeglich um 08:00 Uhr
        "privat-deadline-reminders": {
            "task": "app.workers.tasks.privat_tasks.send_deadline_reminders",
            "schedule": crontab(hour=8, minute=0),  # Taeglich um 08:00 Uhr
        },
        # Property KPIs - Taeglich um 02:25 Uhr (staggered from 02:00)
        "privat-property-kpis": {
            "task": "app.workers.tasks.privat_tasks.calculate_property_kpis",
            "schedule": crontab(hour=2, minute=25),  # Taeglich um 02:25 Uhr (staggered from 02:00)
        },
        # Vehicle TCO - Taeglich um 02:15 Uhr
        "privat-vehicle-tco": {
            "task": "app.workers.tasks.privat_tasks.calculate_vehicle_tco",
            "schedule": crontab(hour=2, minute=15),  # Taeglich um 02:15 Uhr
        },
        # Insurance Coverage Check - Woechentlich Sonntag 04:00
        "privat-insurance-coverage": {
            "task": "app.workers.tasks.privat_tasks.analyze_insurance_coverage",
            "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sonntag 04:00 Uhr
        },
        # Loan Amortization - Taeglich um 02:30 Uhr
        "privat-loan-amortization": {
            "task": "app.workers.tasks.privat_tasks.generate_loan_amortization",
            "schedule": crontab(hour=2, minute=30),  # Taeglich um 02:30 Uhr
        },
        # Financial Health Score - Woechentlich Sonntag 05:00
        "privat-financial-health": {
            "task": "app.workers.tasks.privat_tasks.calculate_financial_health",
            "schedule": crontab(day_of_week=0, hour=5, minute=0),  # Sonntag 05:00 Uhr
        },
        # Recommendations - Woechentlich Montag 06:00
        "privat-recommendations": {
            "task": "app.workers.tasks.privat_tasks.generate_all_recommendations",
            "schedule": crontab(day_of_week=1, hour=6, minute=0),  # Montag 06:00 Uhr
        },
        # Daily Intelligence Recalculation - Taeglich um 03:20 Uhr (staggered from 03:00)
        "privat-intelligence-daily": {
            "task": "app.workers.tasks.privat_tasks.daily_intelligence_recalculation",
            "schedule": crontab(hour=3, minute=20),  # Taeglich um 03:20 Uhr (staggered from 03:00)
        },
        # Privat Metrics Update - Alle 15 Minuten
        "privat-metrics-update": {
            "task": "app.workers.tasks.privat_tasks.update_privat_metrics",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # -----------------------------------------------------------------
        # Portfolio & Financial Goals Tasks
        # -----------------------------------------------------------------
        # Monthly Portfolio Snapshot - Am 1. jeden Monats um 06:00 Uhr
        "privat-portfolio-snapshot-monthly": {
            "task": "app.workers.tasks.privat_tasks.create_monthly_portfolio_snapshot",
            "schedule": crontab(day_of_month=1, hour=6, minute=0),
        },
        # Daily Financial Goals Recalculation - Taeglich um 04:30 Uhr
        "privat-recalculate-goals-daily": {
            "task": "app.workers.tasks.privat_tasks.recalculate_financial_goals",
            "schedule": crontab(hour=4, minute=30),
        },
        # Check Goals At Risk - Taeglich um 09:00 Uhr
        "privat-check-goals-at-risk-daily": {
            "task": "app.workers.tasks.privat_tasks.check_goals_at_risk",
            "schedule": crontab(hour=9, minute=0),
        },
        # -----------------------------------------------------------------
        # Predictive Intelligence Tasks (Phase 1 - PROAKTIV)
        # -----------------------------------------------------------------
        # KPI History Recording - Taeglich um 23:55 Uhr (Ende des Tages)
        "privat-record-kpi-history-daily": {
            "task": "app.workers.tasks.privat_tasks.record_kpi_history",
            "schedule": crontab(hour=23, minute=55),
        },
        # Early Warning Generation - Taeglich um 03:30 Uhr (nach record_kpi_history)
        "privat-generate-predictive-alerts-daily": {
            "task": "app.workers.tasks.privat_tasks.generate_predictive_alerts",
            "schedule": crontab(hour=3, minute=30),
        },
        # Cleanup alte Projektionen - Woechentlich Sonntag 02:00 Uhr
        "privat-cleanup-projections-weekly": {
            "task": "app.workers.tasks.privat_tasks.cleanup_old_projections",
            "schedule": crontab(day_of_week=0, hour=2, minute=0),
            "kwargs": {"days_to_keep": 90},
        },
        # -----------------------------------------------------------------
        # Cross-Module Orchestration Tasks (Phase 2 - INTELLIGENT ROUTING)
        # -----------------------------------------------------------------
        # Process Pending Actions - Alle 2 Minuten
        "orchestration-process-pending-actions": {
            "task": "app.workers.tasks.orchestration_tasks.process_pending_orchestration_actions",
            "schedule": 120.0,  # Alle 2 Minuten
            "kwargs": {"max_actions": 50},
        },
        # Check Threshold Events - Alle 15 Minuten
        "orchestration-check-threshold-events": {
            "task": "app.workers.tasks.orchestration_tasks.check_and_emit_threshold_events",
            "schedule": 900.0,  # Alle 15 Minuten
        },
        # Cleanup alte Decisions - Woechentlich Sonntag 03:00 Uhr
        "orchestration-cleanup-decisions-weekly": {
            "task": "app.workers.tasks.orchestration_tasks.cleanup_old_decisions",
            "schedule": crontab(day_of_week=0, hour=3, minute=0),
            "kwargs": {"days_to_keep": 30},
        },
        # =================================================================
        # Approval System Tasks
        # =================================================================
        # Eskalation ueberfaelliger Genehmigungen - Alle 30 Minuten
        "approval-escalate-overdue": {
            "task": "app.workers.tasks.approval_tasks.escalate_overdue_approvals",
            "schedule": 1800.0,  # Alle 30 Minuten
        },
        # Erinnerungen fuer bald faellige Genehmigungen - Taeglich 08:00 und 14:00
        "approval-reminders-morning": {
            "task": "app.workers.tasks.approval_tasks.send_approval_reminders",
            "schedule": crontab(hour=8, minute=0),
            "kwargs": {"hours_before_due": 24},
        },
        "approval-reminders-afternoon": {
            "task": "app.workers.tasks.approval_tasks.send_approval_reminders",
            "schedule": crontab(hour=14, minute=0),
            "kwargs": {"hours_before_due": 8},
        },
        # Approval-Statistiken generieren - Taeglich um 01:00 Uhr
        "approval-generate-stats": {
            "task": "app.workers.tasks.approval_tasks.generate_approval_stats",
            "schedule": crontab(hour=1, minute=0),
        },
        # Alte Genehmigungen ablaufen lassen - Woechentlich Sonntag 04:00 Uhr
        "approval-expire-old": {
            "task": "app.workers.tasks.approval_tasks.expire_old_approvals",
            "schedule": crontab(day_of_week=0, hour=4, minute=0),
            "kwargs": {"days_to_expire": 30},
        },
        # =================================================================
        # Workflow Automation Tasks
        # =================================================================
        "workflow-check-scheduled": {
            "task": "workflow.check_scheduled",
            "schedule": 60.0,  # Jede Minute
        },
        "workflow-cleanup-old-executions": {
            "task": "workflow.cleanup_old_executions",
            "schedule": crontab(hour=3, minute=0),  # Taeglich um 03:00 Uhr
            "kwargs": {"retention_days": 90},
        },
        "workflow-weekly-report": {
            "task": "workflow.generate_report",
            "schedule": crontab(day_of_week=1, hour=7, minute=30),  # Montag 07:30 Uhr
        },
        # =================================================================
        # Entity Linking Tasks (Lexware Integration)
        # =================================================================
        # Taeglich: Statistiken generieren
        "entity-linking-daily-stats": {
            "task": "entity_linking.generate_statistics",
            "schedule": crontab(hour=1, minute=0),  # Taeglich um 01:00 Uhr
        },
        # Woechentlich: Low-Confidence Dokumente erneut verarbeiten
        "entity-linking-reprocess-low-confidence": {
            "task": "entity_linking.reprocess_low_confidence",
            "schedule": crontab(day_of_week=0, hour=4, minute=0),  # Sonntag 04:00 Uhr
            "kwargs": {"min_confidence": 0.75, "max_confidence": 0.85, "limit": 500},
        },
        # =================================================================
        # Shipment Tracking Tasks (Paketdienst-Integration)
        # DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post
        # =================================================================
        # Stuendlich: Aktive Sendungen aktualisieren
        "shipment-refresh-active-hourly": {
            "task": "shipment_tracking.refresh_active",
            "schedule": crontab(minute=15),  # Stuendlich um :15
        },
        # Taeglich: Verspaetete Sendungen pruefen (>5 Tage Transit)
        "shipment-check-delayed-daily": {
            "task": "shipment_tracking.check_delayed",
            "schedule": crontab(hour=9, minute=0),  # Taeglich um 09:00 Uhr
        },
        # =================================================================
        # Email/Folder Import Tasks (Auto-Import Vollautomatisierung)
        # =================================================================
        # Email-Sync alle 15 Minuten
        "import-sync-all-email-configs": {
            "task": "import.sync_all_email_configs",
            "schedule": 900.0,  # 15 Minuten
        },
        # Folder-Polling alle 5 Minuten
        "import-poll-all-folder-configs": {
            "task": "import.poll_all_folder_configs",
            "schedule": 300.0,  # 5 Minuten
        },
        # Retry fehlgeschlagene Imports alle 30 Minuten
        "import-retry-failed-imports": {
            "task": "import.retry_failed_imports",
            "schedule": 1800.0,  # 30 Minuten
        },
        # Cleanup alte Logs taeglich um 03:00
        "import-cleanup-old-logs": {
            "task": "import.cleanup_old_logs",
            "schedule": crontab(hour=3, minute=0),
        },
        # Reset taegliche Stats um 00:00
        "import-reset-daily-folder-stats": {
            "task": "import.reset_daily_stats",
            "schedule": crontab(hour=0, minute=0),
        },
        # Health-Check alle 30 Minuten
        "import-check-connection-health": {
            "task": "import.check_connection_health",
            "schedule": 1800.0,  # 30 Minuten
        },
        # =================================================================
        # Contract Management Tasks (Vertragsmanagement)
        # Automatische Erinnerungen, Status-Updates, Verlaengerungen
        # =================================================================
        # Taeglich: Kuendigungsfrist-Erinnerungen um 08:00 Uhr
        "contract-deadline-reminders-daily": {
            "task": "contracts.send_deadline_reminders",
            "schedule": crontab(hour=8, minute=0),  # Taeglich um 08:00 Uhr
            "kwargs": {"days_ahead": 90},
        },
        # Taeglich: Ablaufende Vertraege pruefen um 08:30 Uhr
        "contract-check-expiring-daily": {
            "task": "contracts.check_expiring",
            "schedule": crontab(hour=8, minute=30),  # Taeglich um 08:30 Uhr
        },
        # Taeglich: Automatische Verlaengerung um 09:00 Uhr
        "contract-auto-renew-daily": {
            "task": "contracts.auto_renew",
            "schedule": crontab(hour=9, minute=0),  # Taeglich um 09:00 Uhr
        },
        # Woechentlich: Vertragsreport generieren (Montag 07:00 Uhr)
        "contract-weekly-report": {
            "task": "contracts.generate_weekly_report",
            "schedule": crontab(day_of_week=1, hour=7, minute=0),  # Montag 07:00 Uhr
        },
        # Taeglich: Abgelaufene Renewal Options pruefen um 00:30 Uhr
        "contract-renewal-option-expiry-daily": {
            "task": "contracts.check_renewal_option_expiry",
            "schedule": crontab(hour=0, minute=30),  # Taeglich um 00:30 Uhr
        },
        # Taeglich: Ueberfaellige Meilensteine pruefen um 09:30 Uhr
        "contract-check-overdue-milestones-daily": {
            "task": "contracts.check_overdue_milestones",
            "schedule": crontab(hour=9, minute=30),  # Taeglich um 09:30 Uhr
        },
        # =================================================================
        # Collaboration Tasks (Team-Aufgaben, Digest-Emails)
        # =================================================================
        # Stuendliche Digests um jede volle Stunde
        "collaboration-hourly-digests": {
            "task": "app.workers.tasks.collaboration_tasks.process_hourly_digests",
            "schedule": 3600.0,  # Stuendlich
        },
        # Taegliche Digests um 08:05 Uhr (staggered from other 08:00 tasks)
        "collaboration-daily-digests": {
            "task": "app.workers.tasks.collaboration_tasks.process_daily_digests",
            "schedule": crontab(hour=8, minute=5),  # Taeglich um 08:05 Uhr
        },
        # Woechentliche Digests am Montag um 08:10 Uhr
        "collaboration-weekly-digests": {
            "task": "app.workers.tasks.collaboration_tasks.process_weekly_digests",
            "schedule": crontab(day_of_week=1, hour=8, minute=10),  # Montag 08:10 Uhr
        },
        # Ueberfaellige Aufgaben-Erinnerungen stuendlich
        "collaboration-overdue-task-check": {
            "task": "app.workers.tasks.collaboration_tasks.check_overdue_tasks",
            "schedule": 3600.0,  # Stuendlich
        },
        # "Bald faellig" Erinnerungen alle 4 Stunden
        "collaboration-due-soon-reminders": {
            "task": "app.workers.tasks.collaboration_tasks.send_task_due_soon_reminders",
            "schedule": 14400.0,  # Alle 4 Stunden
            "kwargs": {"hours_before": 24},
        },
        # Eskalation stark ueberfaelliger Aufgaben alle 4 Stunden
        "collaboration-escalate-tasks": {
            "task": "app.workers.tasks.collaboration_tasks.escalate_overdue_tasks",
            "schedule": 14400.0,  # Alle 4 Stunden
            "kwargs": {"escalation_threshold_hours": 48},
        },
        # Cleanup alter Digest-Queue-Eintraege woechentlich
        "collaboration-cleanup-digests": {
            "task": "app.workers.tasks.collaboration_tasks.cleanup_old_digest_entries",
            "schedule": crontab(day_of_week=0, hour=5, minute=0),  # Sonntag 05:00 Uhr
            "kwargs": {"days_old": 7},
        },
        # =================================================================
        # BANKING & MAHNWESEN Tasks (BGB §286 Compliance)
        # Automatische Zahlungserinnerungen, Mahnlauf, Cash-Flow
        # =================================================================
        # Taeglich: Automatisches Mahnwesen um 09:00 Uhr
        "banking-process-dunning-daily": {
            "task": "app.workers.tasks.banking_tasks.process_automatic_dunning",
            "schedule": crontab(hour=9, minute=0),  # Taeglich um 09:00 Uhr
        },
        # Taeglich: Mahnlauf (Daily Dunning Run) um 09:00 Uhr
        "banking-daily-mahnlauf": {
            "task": "app.workers.tasks.banking_tasks.daily_mahnlauf",
            "schedule": crontab(hour=9, minute=0),  # Taeglich um 09:00 Uhr
        },
        # Taeglich: Snoozed Tasks reaktivieren um 08:30 Uhr
        "banking-reactivate-snoozed-tasks": {
            "task": "app.workers.tasks.banking_tasks.reactivate_snoozed_tasks",
            "schedule": crontab(hour=8, minute=30),  # Taeglich um 08:30 Uhr
        },
        # Taeglich: Abgelaufene Mahnstopp pruefen um 08:45 Uhr
        "banking-check-expired-mahnstopp": {
            "task": "app.workers.tasks.banking_tasks.check_expired_mahnstopp",
            "schedule": crontab(hour=8, minute=45),  # Taeglich um 08:45 Uhr
        },
        # Taeglich: Pre-Due-Date Reminders um 07:00 Uhr (3 Tage vor Faelligkeit)
        "banking-pre-due-reminders-morning": {
            "task": "app.workers.tasks.banking_tasks.send_pre_due_reminders",
            "schedule": crontab(hour=7, minute=0),  # Taeglich um 07:00 Uhr
        },
        # Taeglich: Skonto-Alerts um 07:30 Uhr (7 Tage voraus)
        "banking-skonto-alerts-morning": {
            "task": "app.workers.tasks.banking_tasks.send_skonto_alerts",
            "schedule": crontab(hour=7, minute=30),  # Taeglich um 07:30 Uhr
            "kwargs": {"days_ahead": 7},
        },
        # Taeglich: Skonto-Alerts um 08:00 Uhr (3 Tage voraus - dringend)
        "banking-skonto-alerts-urgent-3d": {
            "task": "app.workers.tasks.banking_tasks.send_skonto_alerts",
            "schedule": crontab(hour=8, minute=0),  # Taeglich um 08:00 Uhr
            "kwargs": {"days_ahead": 3},
        },
        # Taeglich: Skonto-Alerts um 08:30 Uhr (1 Tag voraus - kritisch)
        "banking-skonto-alerts-critical-1d": {
            "task": "app.workers.tasks.banking_tasks.send_skonto_alerts",
            "schedule": crontab(hour=8, minute=30),  # Taeglich um 08:30 Uhr
            "kwargs": {"days_ahead": 1},
        },
        # Taeglich: Dunning Daily Report um 18:00 Uhr (Tagesabschluss)
        "banking-dunning-daily-report": {
            "task": "app.workers.tasks.banking_tasks.generate_dunning_daily_report",
            "schedule": crontab(hour=18, minute=0),  # Taeglich um 18:00 Uhr
        },
        # Alle 4 Stunden: Cash-Flow Forecasts aktualisieren
        "banking-update-cash-flow-4h": {
            "task": "app.workers.tasks.banking_tasks.update_cash_flow_forecasts",
            "schedule": 14400.0,  # Alle 4 Stunden
        },
        # Stuendlich: TAN-Challenges aufraumen
        "banking-tan-cleanup-hourly": {
            "task": "app.workers.tasks.banking_tasks.cleanup_tan_challenges",
            "schedule": 3600.0,  # Stuendlich
        },

        # =============================================================
        # GoBD Compliance Tasks (Revisionssichere Archivierung)
        # =============================================================
        # Woechentlich: Audit-Chain Integritaet verifizieren (Sonntag 04:30)
        "gobd-audit-chain-weekly": {
            "task": "gobd.verify_audit_chain",
            "schedule": crontab(day_of_week=0, hour=4, minute=30),
        },
        # Taeglich: Batch-Integritaetspruefung der Archive (03:45)
        "gobd-batch-integrity-daily": {
            "task": "gobd.batch_integrity_check",
            "schedule": crontab(hour=3, minute=45),
            "kwargs": {"batch_size": 100},
        },
        # Taeglich: Aufbewahrungsfristen-Warnungen pruefen (09:15)
        "gobd-retention-warnings-daily": {
            "task": "gobd.check_retention_warnings",
            "schedule": crontab(hour=9, minute=15),
        },
        # =================================================================
        # MLOps Pipeline Tasks (Model Lifecycle Management)
        # =================================================================
        # Taeglich: Pruefe ob Retraining-Threshold erreicht (03:00)
        "mlops-check-retraining-threshold": {
            "task": "mlops.check_retraining_threshold",
            "schedule": crontab(hour=3, minute=0),
        },
        # Woechentlich: Alte Modell-Versionen archivieren (Sonntag 05:30)
        "mlops-cleanup-old-versions": {
            "task": "mlops.cleanup_old_versions",
            "schedule": crontab(day_of_week=0, hour=5, minute=30),
            "kwargs": {"archive_older_than_days": 90},
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
        # Qdrant Sync & A/B Testing tasks (GPU for embedding, CPU for analysis)
        "app.workers.tasks.embedding_tasks.sync_document_to_qdrant": {"queue": "embedding_normal", "priority": 6},
        "app.workers.tasks.embedding_tasks.migrate_embeddings_to_qdrant": {"queue": "embedding_low", "priority": 3},
        "app.workers.tasks.embedding_tasks.generate_jina_embedding": {"queue": "embedding_high", "priority": 7},
        "app.workers.tasks.embedding_tasks.analyze_ab_test_metrics": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.embedding_tasks.sync_pending_to_qdrant": {"queue": "maintenance", "priority": 2},
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
        "app.workers.tasks.cleanup_tasks.cleanup_expired_sessions": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.cleanup_tasks.cleanup_expired_verification_tokens": {"queue": "maintenance", "priority": 2},
        # GDPR tasks (Art. 17, Art. 33)
        "app.workers.tasks.gdpr_tasks.process_deletion_requests": {"queue": "maintenance", "priority": 3},
        "app.workers.tasks.gdpr_tasks.check_retention_compliance": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.gdpr_tasks.send_breach_notification": {"queue": "maintenance", "priority": 9},  # Hohe Prioritaet - GDPR Art. 33
        "app.workers.tasks.gdpr_tasks.generate_compliance_report": {"queue": "maintenance", "priority": 1},
        # Notification tasks
        "app.workers.tasks.notification_tasks.send_daily_digest": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.notification_tasks.send_weekly_digest": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.notification_tasks.cleanup_old_notifications": {"queue": "maintenance", "priority": 1},
        # Dunning Email tasks (Task 1.4: Email-Retry-Logik)
        "app.workers.tasks.notification_tasks.send_dunning_email_with_retry": {"queue": "notification", "priority": 5},
        "app.workers.tasks.notification_tasks.retry_failed_dunning_emails": {"queue": "maintenance", "priority": 3},
        # Banking & Dunning tasks (BGB §286 Compliance)
        "app.workers.tasks.banking_tasks.process_automatic_dunning": {"queue": "default", "priority": 5},
        "app.workers.tasks.banking_tasks.daily_mahnlauf": {"queue": "default", "priority": 5},
        "app.workers.tasks.banking_tasks.reactivate_snoozed_tasks": {"queue": "default", "priority": 3},
        "app.workers.tasks.banking_tasks.check_expired_mahnstopp": {"queue": "default", "priority": 3},
        "app.workers.tasks.banking_tasks.send_pre_due_reminders": {"queue": "notification", "priority": 5},
        "app.workers.tasks.banking_tasks.send_skonto_alerts": {"queue": "notification", "priority": 5},
        "app.workers.tasks.banking_tasks.generate_dunning_daily_report": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.banking_tasks.update_cash_flow_forecasts": {"queue": "default", "priority": 3},
        "app.workers.tasks.banking_tasks.cleanup_tan_challenges": {"queue": "maintenance", "priority": 1},
        # Monitoring tasks
        "app.workers.tasks.monitoring_tasks.worker_health_check_task": {"queue": "metrics", "priority": 1},
        "app.workers.tasks.monitoring_tasks.cleanup_stuck_tasks": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.monitoring_tasks.check_queue_backpressure": {"queue": "metrics", "priority": 1},
        # Extraction tasks
        "extraction.quick_classify_document": {"queue": "ocr_high", "priority": 10},  # Hoechste Prioritaet fuer schnelle Klassifizierung
        "extraction.reprocess_all_structured_extraction": {"queue": "ocr_normal", "priority": 4},
        "extraction.reprocess_single_document": {"queue": "ocr_high", "priority": 6},
        "extraction.reprocess_quick_classification": {"queue": "ocr_normal", "priority": 5},  # Quick-Classification Re-Processing
        "extraction.generate_extraction_stats": {"queue": "metrics", "priority": 1},
        # ML/Drift Detection tasks (CPU)
        "app.workers.tasks.ml_tasks.run_drift_detection": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.ml_tasks.check_drift_and_respond": {"queue": "metrics", "priority": 3},
        "app.workers.tasks.ml_tasks.update_ml_metrics": {"queue": "metrics", "priority": 1},
        "app.workers.tasks.ml_tasks.check_experiment_completion": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.ml_tasks.apply_ab_test_winners": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.ml_tasks.generate_ml_report": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.ml_tasks.generate_monthly_drift_report": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.ml_tasks.trigger_model_retrain": {"queue": "maintenance", "priority": 2},
        # MLOps Pipeline tasks (Model Lifecycle Management)
        "mlops.check_retraining_threshold": {"queue": "maintenance", "priority": 2},
        "mlops.run_retraining": {"queue": "gpu", "priority": 4},
        "mlops.evaluate_model": {"queue": "metadata", "priority": 3},
        "mlops.rollback_if_degraded": {"queue": "maintenance", "priority": 8},  # Hohe Prioritaet fuer Rollback
        "mlops.cleanup_old_versions": {"queue": "maintenance", "priority": 1},
        "mlops.get_stats": {"queue": "metadata", "priority": 1},
        # DLQ Management tasks (CPU)
        "app.workers.tasks.dlq_management_tasks.check_dlq_health": {"queue": "metrics", "priority": 1},
        "app.workers.tasks.dlq_management_tasks.cleanup_old_dlq_tasks": {"queue": "maintenance", "priority": 1},
        # Document Intelligence tasks (CPU)
        "app.workers.tasks.document_intelligence_tasks.detect_document_groups": {"queue": "metadata", "priority": 4},
        "app.workers.tasks.document_intelligence_tasks.batch_detect_groups_by_folder": {"queue": "metadata", "priority": 3},
        "app.workers.tasks.document_intelligence_tasks.extract_entities_from_document": {"queue": "metadata", "priority": 5},
        "app.workers.tasks.document_intelligence_tasks.batch_extract_entities": {"queue": "metadata", "priority": 3},
        "app.workers.tasks.document_intelligence_tasks.run_document_intelligence_pipeline": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.document_intelligence_tasks.update_intelligence_metrics": {"queue": "metrics", "priority": 1},
        # Training tasks (GPU for benchmarks, CPU for stats)
        "app.workers.tasks.training_tasks.run_benchmark_batch": {"queue": "ocr_normal", "priority": 4},
        "app.workers.tasks.training_tasks.run_scheduled_benchmarks": {"queue": "ocr_normal", "priority": 3},
        # Bulk Processing Jobs
        "app.workers.tasks.training_tasks.run_bulk_processing_job": {"queue": "ocr_high", "priority": 6},
        "app.workers.tasks.training_tasks.run_bulk_processing_job_cpu": {"queue": "ocr_normal", "priority": 5},
        "app.workers.tasks.training_tasks.generate_daily_stats": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.training_tasks.process_feedback_queue": {"queue": "maintenance", "priority": 3},
        "app.workers.tasks.training_tasks.update_learned_weights": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.training_tasks.populate_training_batch": {"queue": "maintenance", "priority": 3},
        "app.workers.tasks.training_tasks.generate_training_report": {"queue": "maintenance", "priority": 1},
        # =================================================================
        # Surya Continuous Improvement Tasks
        # =================================================================
        # CPU tasks for monitoring and checks
        "app.workers.tasks.surya_improvement_tasks.check_surya_retraining_conditions": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.surya_improvement_tasks.update_surya_metrics": {"queue": "metrics", "priority": 1},
        "app.workers.tasks.surya_improvement_tasks.evaluate_surya_ab_test": {"queue": "metrics", "priority": 2},
        "app.workers.tasks.surya_improvement_tasks.generate_surya_improvement_report": {"queue": "maintenance", "priority": 1},
        # CPU tasks for data processing
        "app.workers.tasks.surya_improvement_tasks.export_surya_training_dataset": {"queue": "maintenance", "priority": 3},
        "app.workers.tasks.surya_improvement_tasks.process_surya_corrections": {"queue": "maintenance", "priority": 3},
        # GPU tasks for training and benchmarking
        "app.workers.tasks.surya_improvement_tasks.run_surya_benchmark": {"queue": "ocr_normal", "priority": 4},
        "app.workers.tasks.surya_improvement_tasks.run_surya_german_finetuning": {"queue": "ocr_high", "priority": 5},
        "app.workers.tasks.surya_improvement_tasks.evaluate_surya_model": {"queue": "ocr_normal", "priority": 4},
        "app.workers.tasks.surya_improvement_tasks.deploy_surya_model": {"queue": "metrics", "priority": 4},
        "app.workers.tasks.surya_improvement_tasks.rollback_surya_model": {"queue": "metrics", "priority": 8},  # Hohe Prioritaet fuer Rollback
        # =================================================================
        # Privat-Modul Intelligence Tasks (CPU-Tasks, niedrige Prioritaet)
        # =================================================================
        "app.workers.tasks.privat_tasks.send_deadline_reminders": {"queue": "maintenance", "priority": 3},
        "app.workers.tasks.privat_tasks.calculate_property_kpis": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.calculate_vehicle_kpis": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.check_insurance_coverage": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.recalculate_loan_kpis": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.calculate_financial_health_scores": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.generate_all_recommendations": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.daily_intelligence_recalculation": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.update_privat_metrics": {"queue": "metrics", "priority": 1},
        # Predictive Intelligence Tasks (PROAKTIV - Phase 1)
        "app.workers.tasks.privat_tasks.record_kpi_history": {"queue": "maintenance", "priority": 2},
        "app.workers.tasks.privat_tasks.generate_predictive_alerts": {"queue": "maintenance", "priority": 3},  # Hoehere Prioritaet - Early Warnings
        "app.workers.tasks.privat_tasks.cleanup_old_projections": {"queue": "maintenance", "priority": 1},
        "app.workers.tasks.privat_tasks.get_predictive_insights_summary": {"queue": "maintenance", "priority": 4},  # On-demand - hohe Prioritaet
        # =================================================================
        # Cross-Module Orchestration Tasks (Phase 2 - INTELLIGENT ROUTING)
        # =================================================================
        "app.workers.tasks.orchestration_tasks.process_pending_orchestration_actions": {"queue": "orchestration", "priority": 5},  # Hoch - verarbeitet proaktiv
        "app.workers.tasks.orchestration_tasks.emit_system_event": {"queue": "orchestration", "priority": 6},  # Sehr hoch - Events muessen schnell raus
        "app.workers.tasks.orchestration_tasks.check_and_emit_threshold_events": {"queue": "orchestration", "priority": 4},  # Mittel - periodische Pruefung
        "app.workers.tasks.orchestration_tasks.get_orchestration_metrics": {"queue": "metrics", "priority": 1},  # Niedrig - Monitoring
        "app.workers.tasks.orchestration_tasks.cleanup_old_decisions": {"queue": "maintenance", "priority": 1},  # Niedrig - Maintenance
        # =================================================================
        # Workflow Automation Tasks
        # =================================================================
        "workflow.execute_async": {"queue": "ocr_normal", "priority": 6},
        "workflow.execute_step": {"queue": "ocr_normal", "priority": 6},
        "workflow.check_scheduled": {"queue": "maintenance", "priority": 2},
        "workflow.cleanup_old_executions": {"queue": "maintenance", "priority": 1},
        "workflow.process_delayed_step": {"queue": "ocr_normal", "priority": 5},
        "workflow.generate_report": {"queue": "maintenance", "priority": 1},
        "workflow.on_document_created": {"queue": "metadata", "priority": 7},
        "workflow.on_document_processed": {"queue": "metadata", "priority": 7},
        "workflow.on_document_failed": {"queue": "metadata", "priority": 7},
        # =================================================================
        # Entity Linking Tasks (Lexware Integration)
        # =================================================================
        # Batch-Verknuepfung aller Dokumente (nach Lexware-Import)
        "entity_linking.link_all_documents": {"queue": "metadata", "priority": 5},
        # Einzeldokument-Verknuepfung (bei OCR-Completion)
        "entity_linking.link_single_document": {"queue": "metadata", "priority": 6},
        # Post-Import Orchestrierung
        "entity_linking.post_lexware_import": {"queue": "metadata", "priority": 7},
        # Statistik-Generierung
        "entity_linking.generate_statistics": {"queue": "maintenance", "priority": 2},
        # Low-Confidence Re-Processing
        "entity_linking.reprocess_low_confidence": {"queue": "metadata", "priority": 3},
        # Event-Handler (OCR Completion)
        "entity_linking.on_ocr_completed": {"queue": "metadata", "priority": 6},
        # Event-Handler (Entity Imported)
        "entity_linking.on_entity_imported": {"queue": "metadata", "priority": 5},
        # =================================================================
        # Shipment Tracking Tasks (Paketdienst-Integration)
        # =================================================================
        # Stuendliches Refresh aller aktiven Sendungen
        "shipment_tracking.refresh_active": {"queue": "tracking", "priority": 4},
        # On-Demand Refresh einer einzelnen Sendung
        "shipment_tracking.refresh_single": {"queue": "tracking", "priority": 6},
        # Taeglich: Verspaetete Sendungen pruefen
        "shipment_tracking.check_delayed": {"queue": "maintenance", "priority": 3},
        # Woechentlich: Statistiken generieren
        "shipment_tracking.generate_statistics": {"queue": "maintenance", "priority": 2},
        # =================================================================
        # Email/Folder Import Tasks (Auto-Import)
        # =================================================================
        # Email-Sync und Folder-Polling
        "import.sync_all_email_configs": {"queue": "default", "priority": 4},
        "import.poll_all_folder_configs": {"queue": "default", "priority": 4},
        "import.sync_single_email_config": {"queue": "default", "priority": 5},
        "import.poll_single_folder_config": {"queue": "default", "priority": 5},
        # Retry und Cleanup
        "import.retry_failed_imports": {"queue": "maintenance", "priority": 3},
        "import.cleanup_old_logs": {"queue": "maintenance", "priority": 1},
        "import.reset_daily_stats": {"queue": "maintenance", "priority": 1},
        # Health-Check
        "import.check_connection_health": {"queue": "maintenance", "priority": 2},
        # Einzeldokument-Import
        "import.process_email_attachment": {"queue": "default", "priority": 6},
        "import.process_folder_file": {"queue": "default", "priority": 6},
        # =================================================================
        # Collaboration Tasks (Digest, Tasks, Escalation)
        # =================================================================
        # Digest-Verarbeitung (Emails)
        "app.workers.tasks.collaboration_tasks.process_hourly_digests": {"queue": "notification", "priority": 4},
        "app.workers.tasks.collaboration_tasks.process_daily_digests": {"queue": "notification", "priority": 4},
        "app.workers.tasks.collaboration_tasks.process_weekly_digests": {"queue": "notification", "priority": 4},
        # Task-Erinnerungen
        "app.workers.tasks.collaboration_tasks.check_overdue_tasks": {"queue": "maintenance", "priority": 5},
        "app.workers.tasks.collaboration_tasks.escalate_overdue_tasks": {"queue": "maintenance", "priority": 6},  # Hoehere Prioritaet - Eskalation
        "app.workers.tasks.collaboration_tasks.send_task_due_soon_reminders": {"queue": "maintenance", "priority": 4},
        # Cleanup
        "app.workers.tasks.collaboration_tasks.cleanup_old_digest_entries": {"queue": "maintenance", "priority": 1},
        # =================================================================
        # GoBD Compliance Tasks (Revisionssichere Archivierung)
        # =================================================================
        # Audit-Chain Verifikation (CPU, niedrige Prioritaet)
        "gobd.verify_audit_chain": {"queue": "maintenance", "priority": 2},
        # Batch-Integritaetspruefung (CPU, mittlere Prioritaet)
        "gobd.batch_integrity_check": {"queue": "maintenance", "priority": 3},
        # Retention-Warnungen (CPU, normale Prioritaet)
        "gobd.check_retention_warnings": {"queue": "maintenance", "priority": 4},
        # Chain-Statistiken (CPU, niedrige Prioritaet)
        "gobd.generate_chain_statistics": {"queue": "maintenance", "priority": 2},
        # =================================================================
        # Contract Management Tasks (Vertragsmanagement)
        # =================================================================
        # Taeglich: Kuendigungsfrist-Erinnerungen
        "contracts.send_deadline_reminders": {"queue": "maintenance", "priority": 4},
        # Taeglich: Ablaufende Vertraege pruefen
        "contracts.check_expiring": {"queue": "maintenance", "priority": 4},
        # Taeglich: Automatische Verlaengerung
        "contracts.auto_renew": {"queue": "maintenance", "priority": 5},
        # Woechentlich: Vertragsreport generieren
        "contracts.generate_weekly_report": {"queue": "maintenance", "priority": 2},
        # Taeglich: Renewal Options pruefen
        "contracts.check_renewal_option_expiry": {"queue": "maintenance", "priority": 3},
        # Taeglich: Ueberfaellige Meilensteine pruefen
        "contracts.check_overdue_milestones": {"queue": "maintenance", "priority": 4},
    },

    # Priority settings
    task_default_priority=5,
    task_inherit_parent_priority=True,
    worker_direct=True,
    task_create_missing_queues=True,

    # ==========================================================================
    # DEAD LETTER QUEUE SETTINGS
    # ==========================================================================
    # WICHTIG: Tasks werden bei Fehler NICHT gelöscht, sondern in DLQ verschoben
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,  # GEÄNDERT: False = Tasks werden bei Fehler rejected und gehen in DLQ
    task_default_queue="ocr_normal",  # Default Queue mit DLQ-Support
)


class GPUTask(Task):
    """Base task class for GPU-intensive operations.

    Ensures only one GPU task executes at a time to prevent VRAM overflow.
    Uses Redis-based distributed lock to coordinate across multiple workers.
    Automatically manages GPU memory and provides error recovery.

    For long-running tasks (>30s), call self.refresh_lock() periodically
    to prevent lock expiration.
    """

    autoretry_for = (torch.cuda.OutOfMemoryError, RuntimeError)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True

    # Instance variable to store lock value for release
    _current_lock_value: Optional[str] = None
    # Track last refresh time to avoid excessive Redis calls
    _last_lock_refresh: float = 0.0
    # Minimum interval between refreshes (30 seconds)
    _LOCK_REFRESH_INTERVAL: float = 30.0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute task with GPU memory management."""
        with gpu_memory_guard():
            return super().__call__(*args, **kwargs)

    def refresh_lock(self) -> bool:
        """Refresh GPU lock TTL for long-running tasks.

        Call this periodically (every 30s) for tasks that run longer than 60s.
        The lock auto-expires after 60s, so failing to refresh will cause
        the task to lose exclusivity.

        Returns:
            True if lock was refreshed, False if refresh failed or skipped
        """
        if not self._current_lock_value:
            logger.warning("refresh_lock_no_lock_held", task_name=self.name)
            return False

        # Rate limit refreshes to avoid Redis spam
        current_time = time.time()
        if current_time - self._last_lock_refresh < self._LOCK_REFRESH_INTERVAL:
            return True  # Skip, too soon since last refresh

        refreshed = refresh_gpu_lock(self._current_lock_value)
        if refreshed:
            self._last_lock_refresh = current_time
            logger.debug(
                "gpu_lock_refreshed_by_task",
                task_name=self.name,
                lock_value=self._current_lock_value
            )
        return refreshed

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Acquire GPU resources before task execution using distributed lock."""
        logger.info("gpu_task_starting", task_id=task_id, task_name=self.name)

        # Skip GPU lock if no GPU available (CPU-only worker)
        if not torch.cuda.is_available():
            logger.info("gpu_lock_skipped_no_gpu", task_id=task_id, task_name=self.name)
            self._current_lock_value = None
            return
        # Acquire distributed GPU lock (works across all workers)
        try:
            self._current_lock_value = acquire_gpu_lock()
            self._last_lock_refresh = time.time()  # Initialize refresh timestamp
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
    task_name = task.name if task else "unknown"
    queue = getattr(task.request, 'delivery_info', {}).get('routing_key', 'default') if task else "default"

    logger.info("task_starting", task_id=task_id, task_name=task_name)

    # Prometheus Metriken
    record_task_started(task_id or "unknown", task_name, queue)


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
    task_name = task.name if task else "unknown"
    queue = getattr(task.request, 'delivery_info', {}).get('routing_key', 'default') if task else "default"

    logger.info("task_completed", task_id=task_id, task_name=task_name, state=state)

    # Prometheus Metriken (nur bei SUCCESS, FAILURE wird separat behandelt)
    if state == "SUCCESS":
        record_task_succeeded(task_id or "unknown", task_name, queue)

    # Clear GPU memory for GPU tasks
    if task and hasattr(task, "__class__") and issubclass(task.__class__, GPUTask):
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            update_gpu_metrics()


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
    task_name = sender.name if sender else "unknown"
    exception_type = type(exception).__name__ if exception else "unknown"

    logger.error("task_failed", task_id=task_id, task_name=task_name, exception=str(exception), exc_info=True)

    # Prometheus Metriken
    record_task_failed(
        task_id or "unknown",
        task_name,
        "default",
        exception_type
    )

    # Clear GPU memory on failure
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        update_gpu_metrics()

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
    task_name = sender.name if sender else "unknown"
    logger.warning("task_retrying", task_id=task_id, task_name=task_name, reason=str(reason))

    # Prometheus Metriken
    record_task_retried(task_id or "unknown", task_name)


@task_success.connect
def task_success_handler(
    sender: Optional[Task] = None,
    result: Optional[Any] = None,
    **extra: Any
) -> None:
    """Log successful task completion."""
    task_name = sender.name if sender else None
    logger.info("task_success", task_name=task_name)


# =============================================================================
# Model Preloading - Worker Startup Optimization
# =============================================================================

# Global flag to track if models are preloaded
_models_preloaded = False


@worker_ready.connect
def preload_ocr_models(sender: Any = None, **kwargs: Any) -> None:
    """
    Preload OCR models when worker starts to eliminate cold start latency.

    Cold start problem:
    - First inference takes 60-90 seconds (CUDA kernel compilation)
    - Subsequent inferences are fast (~2-5 seconds)

    Solution:
    - Load models at worker startup
    - Run warm-up inference with dummy data
    - Models stay in GPU memory for fast subsequent processing

    Note: Only runs on GPU workers (worker_pool="solo")
    """
    global _models_preloaded

    if _models_preloaded:
        logger.debug("models_already_preloaded")
        return

    # Starte Prometheus Metrics Server auf Port 8001
    start_metrics_server(port=8001)

    # Initialisiere Worker Metriken
    hostname = sender.hostname if sender else os.environ.get("HOSTNAME", "unknown")
    init_worker_metrics(hostname=hostname, pool_size=1, prefetch=1)

    logger.info("worker_ready_preloading_models")

    if not torch.cuda.is_available():
        logger.warning("gpu_not_available_skipping_preload")
        _models_preloaded = True
        return

    try:
        # Import OCR backends lazily to avoid circular imports
        from app.core.config import settings

        # Get default backend from settings
        default_backend = getattr(settings, 'DEFAULT_OCR_BACKEND', 'deepseek')

        logger.info(
            "preloading_ocr_model",
            backend=default_backend,
            cuda_device=torch.cuda.get_device_name(0)
        )

        # Preload based on backend
        if default_backend == "deepseek":
            _preload_deepseek()
        elif default_backend == "got_ocr":
            _preload_got_ocr()
        elif default_backend == "surya_gpu":
            _preload_surya_gpu()
        else:
            logger.info("preload_skipped_cpu_backend", backend=default_backend)

        _models_preloaded = True
        logger.info("models_preloaded_successfully", backend=default_backend)

    except Exception as e:
        logger.error("model_preload_failed", error=str(e), exc_info=True)
        # Don't fail worker startup - just log and continue
        _models_preloaded = True


def _preload_deepseek() -> None:
    """Preload DeepSeek-Janus-Pro model."""
    try:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        logger.info("preloading_deepseek_model")
        agent = DeepSeekAgent()

        # Access model to trigger loading
        if hasattr(agent, 'model') and agent.model is not None:
            # Run warm-up inference
            logger.info("running_deepseek_warmup")
            dummy_input = torch.randn(1, 3, 224, 224).cuda()
            with torch.no_grad():
                # Simple forward pass to compile CUDA kernels
                if hasattr(agent.model, 'encode_image'):
                    _ = agent.model.encode_image(dummy_input)
                elif hasattr(agent.model, 'forward'):
                    _ = agent.model(dummy_input)

            logger.info("deepseek_warmup_complete")
        else:
            logger.warning("deepseek_model_not_loaded")

    except ImportError as e:
        logger.warning("deepseek_import_failed", error=str(e))
    except Exception as e:
        logger.error("deepseek_preload_error", error=str(e))


def _preload_got_ocr() -> None:
    """Preload GOT-OCR 2.0 model."""
    try:
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent

        logger.info("preloading_got_ocr_model")
        agent = GOTOCRAgent()

        if hasattr(agent, 'model') and agent.model is not None:
            logger.info("running_got_ocr_warmup")
            dummy_input = torch.randn(1, 3, 384, 384).cuda()
            with torch.no_grad():
                if hasattr(agent.model, 'forward'):
                    _ = agent.model(dummy_input)

            logger.info("got_ocr_warmup_complete")
        else:
            logger.warning("got_ocr_model_not_loaded")

    except ImportError as e:
        logger.warning("got_ocr_import_failed", error=str(e))
    except Exception as e:
        logger.error("got_ocr_preload_error", error=str(e))


def _preload_surya_gpu() -> None:
    """Preload Surya GPU model."""
    try:
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        logger.info("preloading_surya_gpu_model")
        agent = SuryaGPUAgent()

        if hasattr(agent, 'model') and agent.model is not None:
            logger.info("running_surya_gpu_warmup")
            # Surya typically uses different input shape
            dummy_input = torch.randn(1, 3, 256, 256).cuda()
            with torch.no_grad():
                if hasattr(agent.model, 'forward'):
                    _ = agent.model(dummy_input)

            logger.info("surya_gpu_warmup_complete")
        else:
            logger.warning("surya_gpu_model_not_loaded")

    except ImportError as e:
        logger.warning("surya_gpu_import_failed", error=str(e))
    except Exception as e:
        logger.error("surya_gpu_preload_error", error=str(e))


# =============================================================================
# Worker Shutdown - GPU Cleanup
# =============================================================================

@worker_shutdown.connect
def cleanup_gpu_on_worker_shutdown(sender: Any = None, **kwargs: Any) -> None:
    """
    Clean up GPU resources when worker shuts down.

    Prevents:
    - GPU memory leaks
    - Zombie CUDA processes
    - Resource contention with other workers
    """
    logger.info("worker_shutdown_cleaning_gpu")

    # Stoppe Prometheus Metrics Server
    stop_metrics_server()
    shutdown_worker_metrics()

    if torch.cuda.is_available():
        try:
            # Clear CUDA cache
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

            # Log final memory state
            allocated = torch.cuda.memory_allocated() / (1024**3)
            reserved = torch.cuda.memory_reserved() / (1024**3)

            logger.info(
                "gpu_cleanup_complete",
                allocated_gb=round(allocated, 2),
                reserved_gb=round(reserved, 2)
            )

        except Exception as e:
            logger.error("gpu_cleanup_failed", error=str(e))

    # Force garbage collection
    import gc
    gc.collect()

    logger.info("worker_shutdown_complete")


# =============================================================================
# Worker Health Check System (P1 - Tote Worker erkennen)
# =============================================================================

# Health Check Konfiguration
HEALTH_CHECK_INTERVAL_SECONDS = 30  # Alle 30 Sekunden
STALE_TASK_THRESHOLD_SECONDS = 600  # Tasks aelter als 10 Min gelten als stuck
WORKER_UNRESPONSIVE_THRESHOLD_SECONDS = 120  # Worker gilt als tot nach 2 Min ohne Heartbeat

# Globaler Health-Status Cache
_worker_health_cache: Dict[str, Any] = {}
_last_health_check: Optional[datetime] = None


def get_worker_health_status() -> Dict[str, Any]:
    """
    Ermittle den Gesundheitsstatus aller Celery Worker.

    Returns:
        Dict mit:
        - workers: Liste der Worker mit Status
        - total_workers: Anzahl aktiver Worker
        - healthy_workers: Anzahl gesunder Worker
        - stale_tasks: Liste von stuck Tasks
        - warnings: Warnungen
        - timestamp: Zeitstempel der Pruefung
    """
    from celery import current_app
    from datetime import timezone
    import time

    result = {
        "workers": [],
        "total_workers": 0,
        "healthy_workers": 0,
        "unhealthy_workers": 0,
        "stale_tasks": [],
        "warnings": [],
        "errors": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        inspect = current_app.control.inspect()

        # 1. Pruefe aktive Worker via Ping
        ping_results = inspect.ping() or {}
        active_workers = list(ping_results.keys())
        result["total_workers"] = len(active_workers)

        # 2. Hole Worker-Stats
        stats = inspect.stats() or {}

        # 3. Hole aktive Tasks
        active_tasks = inspect.active() or {}

        # 4. Hole reservierte (queued) Tasks
        reserved_tasks = inspect.reserved() or {}

        # 5. Pruefe jeden Worker
        for worker_name in active_workers:
            worker_stats = stats.get(worker_name, {})
            worker_active = active_tasks.get(worker_name, [])
            worker_reserved = reserved_tasks.get(worker_name, [])

            worker_info = {
                "name": worker_name,
                "status": "healthy",
                "active_tasks": len(worker_active),
                "reserved_tasks": len(worker_reserved),
                "pid": worker_stats.get("pid"),
                "pool": worker_stats.get("pool", {}).get("implementation", "unknown"),
                "prefetch": worker_stats.get("prefetch_count", 0),
                "total_processed": worker_stats.get("total", {}).get("app.workers.tasks.ocr_tasks.process_document_task", 0),
                "warnings": [],
            }

            # GPU-Status pruefen wenn verfuegbar
            if torch.cuda.is_available():
                try:
                    worker_info["gpu"] = {
                        "available": True,
                        "device": torch.cuda.get_device_name(0),
                        "allocated_gb": round(torch.cuda.memory_allocated() / (1024**3), 2),
                        "reserved_gb": round(torch.cuda.memory_reserved() / (1024**3), 2),
                    }
                except Exception as e:
                    worker_info["gpu"] = {"available": False, "error": str(e)}
                    worker_info["warnings"].append("GPU-Status nicht verfuegbar")

            # Pruefe auf stuck Tasks
            for task in worker_active:
                if isinstance(task, dict):
                    task_started = task.get("time_start")
                    if task_started:
                        elapsed = time.time() - task_started
                        if elapsed > STALE_TASK_THRESHOLD_SECONDS:
                            task_info = {
                                "task_id": task.get("id"),
                                "task_name": task.get("name"),
                                "worker": worker_name,
                                "elapsed_seconds": round(elapsed, 0),
                                "args": str(task.get("args", []))[:100],  # Truncate
                            }
                            result["stale_tasks"].append(task_info)
                            worker_info["warnings"].append(
                                f"Stuck Task: {task.get('name')} laeuft seit {int(elapsed)}s"
                            )
                            worker_info["status"] = "degraded"

            # Worker ist gesund wenn keine Warnungen
            if worker_info["status"] == "healthy":
                result["healthy_workers"] += 1
            else:
                result["unhealthy_workers"] += 1

            result["workers"].append(worker_info)

        # 6. Warnungen generieren
        if result["total_workers"] == 0:
            result["warnings"].append("KRITISCH: Keine aktiven Worker gefunden!")

        if result["stale_tasks"]:
            result["warnings"].append(
                f"WARNUNG: {len(result['stale_tasks'])} stuck Tasks gefunden"
            )

        if result["unhealthy_workers"] > 0:
            result["warnings"].append(
                f"WARNUNG: {result['unhealthy_workers']} Worker mit Problemen"
            )

        # GPU Lock Status
        lock_status = check_gpu_lock_health()
        result["gpu_lock"] = lock_status

    except Exception as e:
        logger.error("worker_health_check_failed", error=str(e))
        result["errors"].append(f"Health Check fehlgeschlagen: {e}")

    # Cache aktualisieren
    global _worker_health_cache, _last_health_check
    _worker_health_cache = result
    _last_health_check = datetime.now(timezone.utc)

    return result


def get_cached_worker_health() -> Dict[str, Any]:
    """
    Hole gecachten Worker-Health-Status.

    Falls der Cache aelter als HEALTH_CHECK_INTERVAL_SECONDS ist,
    wird ein neuer Health Check durchgefuehrt.

    Returns:
        Dict mit Worker-Health-Informationen
    """
    global _worker_health_cache, _last_health_check

    if _last_health_check is None:
        return get_worker_health_status()

    age_seconds = (datetime.now(timezone.utc) - _last_health_check).total_seconds()

    if age_seconds > HEALTH_CHECK_INTERVAL_SECONDS:
        return get_worker_health_status()

    return _worker_health_cache


def restart_stuck_tasks(force: bool = False) -> Dict[str, Any]:
    """
    Beende und starte stuck Tasks neu.

    VORSICHT: Kann zu Datenverlust fuehren wenn Tasks
    wichtige Arbeit machen. Nur mit force=True ausfuehren.

    Args:
        force: Erzwinge Neustart auch bei laufenden Tasks

    Returns:
        Dict mit Ergebnis der Operation
    """
    if not force:
        return {
            "success": False,
            "message": "force=True erforderlich fuer Restart",
            "stuck_tasks": len(get_worker_health_status().get("stale_tasks", []))
        }

    from celery import current_app

    result = {
        "revoked": [],
        "errors": [],
    }

    health = get_worker_health_status()
    stale_tasks = health.get("stale_tasks", [])

    for task in stale_tasks:
        task_id = task.get("task_id")
        if task_id:
            try:
                current_app.control.revoke(task_id, terminate=True, signal="SIGKILL")
                result["revoked"].append(task_id)
                logger.warning("stuck_task_revoked", task_id=task_id)
            except Exception as e:
                result["errors"].append({"task_id": task_id, "error": str(e)})
                logger.error("stuck_task_revoke_failed", task_id=task_id, error=str(e))

    return result


def get_worker_heartbeat_status() -> Dict[str, Any]:
    """
    Pruefe Worker-Heartbeats via Celery Events.

    Returns:
        Dict mit Heartbeat-Status pro Worker
    """
    from celery import current_app

    result = {
        "workers": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Ping alle Worker
        inspect = current_app.control.inspect()
        ping_results = inspect.ping(timeout=5.0) or {}

        for worker, response in ping_results.items():
            result["workers"][worker] = {
                "responding": response.get("ok") == "pong",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    except Exception as e:
        logger.error("heartbeat_check_failed", error=str(e))
        result["error"] = str(e)

    return result


# =============================================================================
# Enhanced OOM Recovery Signal Handler
# =============================================================================

@task_failure.connect
def enhanced_oom_recovery_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    exception: Optional[Exception] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    traceback: Optional[Any] = None,
    einfo: Optional[Any] = None,
    **extra: Any
) -> None:
    """
    Enhanced OOM recovery handler with GPU memory cleanup.

    Actions on OOM:
    1. Log detailed GPU memory state
    2. Clear CUDA cache
    3. Reset peak memory stats
    4. Trigger garbage collection
    5. Record metrics for monitoring
    """
    task_name = sender.name if sender else "unknown"

    # Check if this is an OOM error
    is_oom = (
        isinstance(exception, torch.cuda.OutOfMemoryError) if torch.cuda.is_available()
        else False
    ) or (
        exception and "out of memory" in str(exception).lower()
    )

    if is_oom:
        logger.error(
            "oom_recovery_triggered",
            task_id=task_id,
            task_name=task_name,
            error=str(exception)
        )

        if torch.cuda.is_available():
            try:
                # Log memory state before cleanup
                before_allocated = torch.cuda.memory_allocated() / (1024**3)
                before_reserved = torch.cuda.memory_reserved() / (1024**3)

                # Aggressive cleanup
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                torch.cuda.reset_peak_memory_stats()

                # Force garbage collection
                import gc
                gc.collect()

                # Log memory state after cleanup
                after_allocated = torch.cuda.memory_allocated() / (1024**3)
                after_reserved = torch.cuda.memory_reserved() / (1024**3)

                freed_gb = before_allocated - after_allocated

                logger.info(
                    "oom_recovery_complete",
                    task_id=task_id,
                    freed_gb=round(freed_gb, 2),
                    before_allocated_gb=round(before_allocated, 2),
                    after_allocated_gb=round(after_allocated, 2)
                )

                # Update OOM metrics (for Prometheus)
                record_gpu_oom(task_name)
                update_gpu_metrics()
                _record_oom_event(task_name, freed_gb)

            except Exception as cleanup_error:
                logger.error(
                    "oom_recovery_cleanup_failed",
                    task_id=task_id,
                    error=str(cleanup_error)
                )


def _record_oom_event(task_name: str, freed_gb: float) -> None:
    """Record OOM event for metrics/monitoring."""
    try:
        # Try to update Prometheus metrics if available
        from app.gpu_manager import get_batch_processor
        processor = get_batch_processor()
        # Stats are tracked internally in AdaptiveBatchProcessor
        logger.debug(
            "oom_event_recorded",
            task_name=task_name,
            freed_gb=freed_gb,
            processor_stats=processor.get_stats()
        )
    except Exception:
        # Metrics not available - just log
        pass
