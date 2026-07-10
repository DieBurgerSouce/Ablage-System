# -*- coding: utf-8 -*-
"""
Monitoring Tasks für Worker Health Checks.

Periodische Tasks zur Überwachung der Worker-Gesundheit:
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
from app.core.safe_errors import safe_error_detail

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
    Periodischer Health Check für alle Celery Worker.

    Wird jede Minute via Celery Beat ausgeführt.

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

        # Metriken aktualisieren (für Prometheus)
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
    Prüfe und bereinige stuck Tasks.

    Wird alle 5 Minuten ausgeführt. Bei kritischen stuck Tasks
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

        # Log Warnungen für alle stuck Tasks
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
    Prüfe Queue-Längen für Backpressure-Detection.

    Returns:
        Dict mit Queue-Status und Backpressure-Indikatoren
    """
    from celery import current_app
    from redis import Redis

    try:
        # Redis-Verbindung für Queue-Längen
        redis_url = current_app.conf.broker_url
        redis_client = Redis.from_url(redis_url)

        # F-13: VOLLSTÄNDIGE Liste aller konsumierten/gerouteten Queues (Union der
        # -Q-Flags von worker + worker-cpu, plus datev). Vorher fehlten u. a.
        # monitoring/erp/notification(s)/default — genau die orphan-Queue
        # `monitoring` (F-12, 207 gestaute Msgs) blieb damit unsichtbar. Nur mit
        # der vollen Liste kann die Backlog-Alert-Familie einen Stau erkennen.
        queues = [
            "ocr_high", "ocr_normal",
            "embedding_high", "embedding_normal", "embedding_low",
            "validation", "metadata", "maintenance", "metrics",
            "backup", "dlq",
            "workflow", "approval", "orchestration", "tracking", "privat",
            "notification", "notifications", "erp", "default", "monitoring",
            "datev",
        ]

        # F-13: Die Prometheus-Gauge ablage_celery_queue_length wurde bislang NIE
        # befüllt (update_queue_metrics war ungenutzt) -> CeleryQueueBacklog(-Critical)
        # konnten nie feuern. Diese bereits beat-geschedulte Task setzt sie jetzt mit.
        from app.workers.celery_metrics import celery_queue_length

        queue_lengths = {}
        total_length = 0

        for queue_name in queues:
            try:
                length = redis_client.llen(queue_name)
                queue_lengths[queue_name] = length
                total_length += length
                try:
                    celery_queue_length.labels(queue_name=queue_name).set(length)
                except Exception:  # Metrik-Export darf die Task nie brechen
                    pass
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
        # Prometheus Metriken nicht verfügbar
        pass
    except Exception as e:
        logger.debug("health_metrics_update_failed", **safe_error_log(e))
