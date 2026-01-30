# -*- coding: utf-8 -*-
"""
Monitoring Tasks fuer Worker Health Checks.

Periodische Tasks zur Ueberwachung der Worker-Gesundheit:
- Health Status Checks
- Stuck Task Detection
- GPU Memory Monitoring
- Queue Backpressure Detection
"""

from datetime import datetime, timezone
from typing import Any, Dict

import structlog

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.monitoring_tasks.worker_health_check_task",
    queue="metrics",
    priority=1,
    ignore_result=True,
    soft_time_limit=25,  # 25 Sekunden Soft-Limit
    time_limit=30,  # Max 30 Sekunden
)
def worker_health_check_task() -> Dict[str, Any]:
    """
    Periodischer Health Check fuer alle Celery Worker.

    Wird jede Minute via Celery Beat ausgefuehrt.

    Returns:
        Dict mit Health-Status
    """
    from app.workers.celery_app import get_worker_health_status

    try:
        health = get_worker_health_status()

        # Log Warnungen
        for warning in health.get("warnings", []):
            logger.warning("worker_health_warning", message=warning)

        # Log Zusammenfassung
        logger.info(
            "worker_health_check_complete",
            total_workers=health.get("total_workers", 0),
            healthy_workers=health.get("healthy_workers", 0),
            unhealthy_workers=health.get("unhealthy_workers", 0),
            stale_tasks=len(health.get("stale_tasks", [])),
        )

        # Metriken aktualisieren (fuer Prometheus)
        _update_health_metrics(health)

        return {
            "success": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": health.get("total_workers", 0),
                "healthy": health.get("healthy_workers", 0),
                "stale_tasks": len(health.get("stale_tasks", [])),
            }
        }

    except Exception as e:
        logger.error("worker_health_check_task_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": safe_error_detail(e, "Vorgang"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.monitoring_tasks.cleanup_stuck_tasks",
    queue="maintenance",
    priority=1,
    ignore_result=True,
    soft_time_limit=55,  # 55 Sekunden Soft-Limit
    time_limit=60,
)
def cleanup_stuck_tasks() -> Dict[str, Any]:
    """
    Pruefe und bereinige stuck Tasks.

    Wird alle 5 Minuten ausgefuehrt. Bei kritischen stuck Tasks
    (>30 Minuten) wird automatisch revoked.

    Returns:
        Dict mit Cleanup-Ergebnis
    """
    from app.workers.celery_app import get_worker_health_status, restart_stuck_tasks

    try:
        health = get_worker_health_status()
        stale_tasks = health.get("stale_tasks", [])

        if not stale_tasks:
            return {
                "success": True,
                "action": "none",
                "message": "Keine stuck Tasks gefunden",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Kritische Tasks (>30 Minuten)
        critical_tasks = [
            t for t in stale_tasks
            if t.get("elapsed_seconds", 0) > 1800  # 30 Minuten
        ]

        result = {
            "success": True,
            "stale_tasks_found": len(stale_tasks),
            "critical_tasks": len(critical_tasks),
            "actions": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Log Warnungen fuer alle stuck Tasks
        for task in stale_tasks:
            logger.warning(
                "stuck_task_detected",
                task_id=task.get("task_id"),
                task_name=task.get("task_name"),
                worker=task.get("worker"),
                elapsed_seconds=task.get("elapsed_seconds"),
            )

        # Auto-Revoke nur bei kritischen Tasks und nur wenn konfiguriert
        auto_revoke_enabled = False  # Konservativ: Manuell aktivieren
        if critical_tasks and auto_revoke_enabled:
            logger.warning(
                "auto_revoking_critical_tasks",
                count=len(critical_tasks)
            )
            revoke_result = restart_stuck_tasks(force=True)
            result["actions"].append({
                "action": "revoke",
                "revoked": revoke_result.get("revoked", []),
                "errors": revoke_result.get("errors", []),
            })

        return result

    except Exception as e:
        logger.error("cleanup_stuck_tasks_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": safe_error_detail(e, "Vorgang"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.monitoring_tasks.check_queue_backpressure",
    queue="metrics",
    priority=1,
    ignore_result=True,
    soft_time_limit=25,  # 25 Sekunden Soft-Limit
    time_limit=30,
)
def check_queue_backpressure() -> Dict[str, Any]:
    """
    Pruefe Queue-Laengen fuer Backpressure-Detection.

    Returns:
        Dict mit Queue-Status und Backpressure-Indikatoren
    """
    from celery import current_app
    from redis import Redis

    try:
        # Redis-Verbindung fuer Queue-Laengen
        redis_url = current_app.conf.broker_url
        redis_client = Redis.from_url(redis_url)

        # Definierte Queues
        queues = [
            "ocr_high", "ocr_normal",
            "embedding_high", "embedding_normal", "embedding_low",
            "validation", "metadata",
            "backup", "maintenance", "metrics"
        ]

        queue_lengths = {}
        total_length = 0

        for queue_name in queues:
            try:
                length = redis_client.llen(queue_name)
                queue_lengths[queue_name] = length
                total_length += length
            except Exception as e:
                logger.debug(
                    "queue_length_check_failed",
                    queue_name=queue_name,
                    error_type=type(e).__name__,
                )
                queue_lengths[queue_name] = -1  # Error indicator

        # Backpressure-Thresholds
        THRESHOLD_HIGH = 100
        THRESHOLD_CRITICAL = 200

        backpressure_status = "normal"
        warnings = []

        if total_length > THRESHOLD_CRITICAL:
            backpressure_status = "critical"
            warnings.append(f"KRITISCH: {total_length} Tasks in Queues")
        elif total_length > THRESHOLD_HIGH:
            backpressure_status = "high"
            warnings.append(f"WARNUNG: {total_length} Tasks in Queues")

        # Einzelne Queue Warnungen
        for queue, length in queue_lengths.items():
            if length > 50:
                warnings.append(f"Queue {queue}: {length} Tasks")

        result = {
            "success": True,
            "queues": queue_lengths,
            "total": total_length,
            "backpressure_status": backpressure_status,
            "warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Log bei hoher Backpressure
        if backpressure_status != "normal":
            logger.warning(
                "queue_backpressure_detected",
                status=backpressure_status,
                total=total_length,
                queues=queue_lengths
            )

        return result

    except Exception as e:
        logger.error("backpressure_check_failed", **safe_error_log(e))
        return {
            "success": False,
            "error": safe_error_detail(e, "Vorgang"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def _update_health_metrics(health: Dict[str, Any]) -> None:
    """
    Aktualisiere Prometheus-Metriken basierend auf Health-Status.

    Args:
        health: Health-Status Dictionary
    """
    try:
        from app.workers.prometheus_metrics import (
            WORKER_HEALTH_GAUGE,
            STALE_TASKS_GAUGE,
        )

        # Worker-Anzahl
        WORKER_HEALTH_GAUGE.labels(status="healthy").set(
            health.get("healthy_workers", 0)
        )
        WORKER_HEALTH_GAUGE.labels(status="unhealthy").set(
            health.get("unhealthy_workers", 0)
        )

        # Stale Tasks
        STALE_TASKS_GAUGE.set(len(health.get("stale_tasks", [])))

    except ImportError:
        # Prometheus Metriken nicht verfuegbar
        pass
    except Exception as e:
        logger.debug("health_metrics_update_failed", **safe_error_log(e))
