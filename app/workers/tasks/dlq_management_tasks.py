"""Dead Letter Queue (DLQ) Management Tasks.

Dieses Modul enthält Tasks und Utilities zum Management der Dead Letter Queue:
- Inspektion fehlgeschlagener Tasks
- Retry von Tasks aus der DLQ
- Poison-Pill-Detection (wiederholt fehlende Tasks)
- Alerting bei kritischen DLQ-Zuständen

WICHTIG: Die DLQ sammelt alle Tasks, die nach max_retries fehlgeschlagen sind.
Diese Tasks gehen NICHT verloren und können manuell untersucht werden.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict

import structlog
from celery import current_app
from pydantic import BaseModel, ConfigDict, ValidationError as PydanticValidationError
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.workers.celery_app import celery_app, CPUTask


# =============================================================================
# Pydantic Validierungsmodelle fuer DLQ-Tasks
# =============================================================================

class DLQTaskHeadersSchema(BaseModel):
    """Validierungsschema fuer Celery Task Headers."""
    id: Optional[str] = None
    task: Optional[str] = None

    model_config = ConfigDict(extra="allow")  # Erlaube zusaetzliche Felder


class DLQTaskPropertiesSchema(BaseModel):
    """Validierungsschema fuer Celery Task Properties."""
    timestamp: Optional[float] = None

    model_config = ConfigDict(extra="allow")


class DLQTaskSchema(BaseModel):
    """Validierungsschema fuer DLQ Task JSON.

    Validiert die Struktur von Celery-Tasks in der Dead Letter Queue.
    """
    headers: DLQTaskHeadersSchema = DLQTaskHeadersSchema()
    properties: DLQTaskPropertiesSchema = DLQTaskPropertiesSchema()
    body: Optional[str] = None

    model_config = ConfigDict(extra="allow")


def validate_dlq_task(data: Dict[str, Any]) -> DLQTaskSchema:
    """Validiere DLQ Task JSON.

    Args:
        data: Deserialisierte JSON-Daten

    Returns:
        Validiertes DLQTaskSchema

    Raises:
        pydantic.ValidationError: Bei Validierungsfehlern
    """
    return DLQTaskSchema.model_validate(data)

logger = structlog.get_logger(__name__)

# =============================================================================
# DLQ Konfiguration
# =============================================================================

DLQ_QUEUE_NAME = "dlq"
DLQ_REDIS_KEY = f"celery:{DLQ_QUEUE_NAME}"
POISON_PILL_THRESHOLD = 3  # Nach 3 Failures gilt Task als Poison Pill
DLQ_ALERT_THRESHOLD = 100  # Alert wenn >100 Tasks in DLQ
DLQ_CRITICAL_THRESHOLD = 500  # Kritisch wenn >500 Tasks in DLQ

# Tracking für Poison Pills (im Memory - bei Worker-Restart zurückgesetzt)
_failure_counts: Dict[str, int] = defaultdict(int)


def _get_redis_client() -> Redis:
    """Hole Redis-Client für DLQ-Operationen."""
    return Redis.from_url(
        settings.CELERY_BROKER_URL,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0
    )


# =============================================================================
# DLQ Inspektion
# =============================================================================

def get_dlq_stats() -> Dict[str, Any]:
    """Hole Statistiken über die Dead Letter Queue.

    Returns:
        Dict mit DLQ-Statistiken:
        - count: Anzahl Tasks in DLQ
        - status: healthy|warning|critical
        - oldest_task: Ältester Task (falls vorhanden)
        - task_types: Aufschlüsselung nach Task-Typ
        - poison_pills: Liste von Poison-Pill Task-IDs
    """
    try:
        redis = _get_redis_client()

        # DLQ-Länge ermitteln
        count = redis.llen(DLQ_REDIS_KEY)

        # Status bestimmen
        if count >= DLQ_CRITICAL_THRESHOLD:
            status = "critical"
        elif count >= DLQ_ALERT_THRESHOLD:
            status = "warning"
        else:
            status = "healthy"

        result = {
            "count": count,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thresholds": {
                "alert": DLQ_ALERT_THRESHOLD,
                "critical": DLQ_CRITICAL_THRESHOLD,
            },
            "poison_pills": [],
            "task_types": {},
        }

        # Nur bei wenigen Tasks Details laden (Performance)
        if count > 0 and count <= 1000:
            # Sample Tasks für Analyse
            sample_size = min(count, 100)
            tasks = redis.lrange(DLQ_REDIS_KEY, 0, sample_size - 1)

            task_types: Dict[str, int] = defaultdict(int)
            oldest_timestamp = None

            for task_data in tasks:
                try:
                    raw_task = json.loads(task_data)
                    # Pydantic-Validierung fuer sichere Deserialisierung
                    validated_task = validate_dlq_task(raw_task)
                    task_name = validated_task.headers.task or "unknown"
                    task_types[task_name] += 1

                    # Aeltesten Task finden
                    task_ts = validated_task.properties.timestamp
                    if task_ts:
                        if oldest_timestamp is None or task_ts < oldest_timestamp:
                            oldest_timestamp = task_ts
                except (json.JSONDecodeError, PydanticValidationError):
                    task_types["parse_error"] += 1

            result["task_types"] = dict(task_types)
            if oldest_timestamp:
                result["oldest_task_timestamp"] = oldest_timestamp

        # Poison Pills aus Memory-Tracking
        result["poison_pills"] = [
            task_id for task_id, count in _failure_counts.items()
            if count >= POISON_PILL_THRESHOLD
        ]

        return result

    except RedisError as e:
        logger.error("dlq_stats_redis_error", error=str(e))
        return {
            "count": -1,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_dlq_tasks(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Hole Tasks aus der Dead Letter Queue.

    Args:
        limit: Maximale Anzahl Tasks
        offset: Start-Offset

    Returns:
        Liste von Task-Dicts mit Details
    """
    try:
        redis = _get_redis_client()
        raw_tasks = redis.lrange(DLQ_REDIS_KEY, offset, offset + limit - 1)

        tasks = []
        for raw_task in raw_tasks:
            try:
                task_data = json.loads(raw_task)
                # Pydantic-Validierung fuer sichere Deserialisierung
                validated_task = validate_dlq_task(task_data)
                task_info = {
                    "task_id": validated_task.headers.id,
                    "task_name": validated_task.headers.task,
                    "args": task_data.get("body", {}).get("args", [])[:3],  # Truncate
                    "kwargs_keys": list(task_data.get("body", {}).get("kwargs", {}).keys()),
                    "timestamp": validated_task.properties.timestamp,
                    "retries": task_data.get("headers", {}).get("retries", 0),
                    "origin": task_data.get("headers", {}).get("origin"),
                    "raw_size_bytes": len(raw_task),
                }
                tasks.append(task_info)
            except (json.JSONDecodeError, PydanticValidationError) as e:
                tasks.append({
                    "error": f"Parse-Fehler: {e}",
                    "raw_preview": raw_task[:200] if raw_task else None,
                })

        return tasks

    except RedisError as e:
        logger.error("dlq_get_tasks_error", error=str(e))
        return [{"error": str(e)}]


# =============================================================================
# DLQ Retry Operations
# =============================================================================

def retry_dlq_task(task_index: int = 0) -> Dict[str, Any]:
    """Retry einen einzelnen Task aus der DLQ.

    Der Task wird aus der DLQ entfernt und erneut in die Original-Queue gestellt.

    Args:
        task_index: Index des Tasks in der DLQ (0 = ältester)

    Returns:
        Dict mit Ergebnis der Operation
    """
    try:
        redis = _get_redis_client()

        # Task aus DLQ holen (ohne zu entfernen)
        raw_task = redis.lindex(DLQ_REDIS_KEY, task_index)
        if not raw_task:
            return {"success": False, "error": "Kein Task an diesem Index gefunden"}

        task_data = json.loads(raw_task)
        task_id = task_data.get("headers", {}).get("id")
        task_name = task_data.get("headers", {}).get("task")

        # Poison Pill Check
        if _failure_counts.get(task_id, 0) >= POISON_PILL_THRESHOLD:
            return {
                "success": False,
                "error": f"Task {task_id} ist ein Poison Pill ({_failure_counts[task_id]} Failures). Manuelles Eingreifen erforderlich.",
                "task_id": task_id,
                "task_name": task_name,
            }

        # Task aus DLQ entfernen
        # LREM entfernt das erste Vorkommen des exakten Wertes
        removed = redis.lrem(DLQ_REDIS_KEY, 1, raw_task)

        if removed == 0:
            return {"success": False, "error": "Task konnte nicht aus DLQ entfernt werden"}

        # Task erneut ausführen
        args = task_data.get("body", {}).get("args", [])
        kwargs = task_data.get("body", {}).get("kwargs", {})

        # Retry-Counter erhöhen für Poison-Pill-Detection
        _failure_counts[task_id] = _failure_counts.get(task_id, 0) + 1

        # Task erneut senden
        current_app.send_task(
            task_name,
            args=args,
            kwargs=kwargs,
            task_id=f"{task_id}_retry_{int(time.time())}",
        )

        logger.info(
            "dlq_task_retried",
            task_id=task_id,
            task_name=task_name,
            retry_count=_failure_counts[task_id]
        )

        return {
            "success": True,
            "task_id": task_id,
            "task_name": task_name,
            "retry_count": _failure_counts[task_id],
        }

    except (json.JSONDecodeError, RedisError) as e:
        logger.error("dlq_retry_error", error=str(e))
        return {"success": False, "error": str(e)}


def retry_all_dlq_tasks(max_tasks: int = 100) -> Dict[str, Any]:
    """Retry alle Tasks aus der DLQ (bis zu max_tasks).

    VORSICHT: Bei vielen Tasks kann dies das System überlasten!

    Args:
        max_tasks: Maximale Anzahl Tasks zum Retry

    Returns:
        Dict mit Zusammenfassung
    """
    results = {
        "total_attempted": 0,
        "successful": 0,
        "failed": 0,
        "poison_pills_skipped": 0,
        "errors": [],
    }

    for i in range(max_tasks):
        result = retry_dlq_task(0)  # Immer Index 0 (ältester Task)

        results["total_attempted"] += 1

        if result.get("success"):
            results["successful"] += 1
        elif "Poison Pill" in result.get("error", ""):
            results["poison_pills_skipped"] += 1
        else:
            results["failed"] += 1
            if len(results["errors"]) < 10:  # Max 10 Fehler speichern
                results["errors"].append(result.get("error"))

        # Abbruch wenn DLQ leer
        if "Kein Task" in result.get("error", ""):
            break

    logger.info("dlq_retry_all_complete", **results)
    return results


def purge_dlq(confirm: bool = False) -> Dict[str, Any]:
    """Lösche alle Tasks aus der DLQ.

    VORSICHT: Gelöschte Tasks sind unwiederbringlich verloren!

    Args:
        confirm: Muss True sein für Ausführung

    Returns:
        Dict mit Ergebnis
    """
    if not confirm:
        return {
            "success": False,
            "error": "confirm=True erforderlich zum Löschen der DLQ",
        }

    try:
        redis = _get_redis_client()
        count = redis.llen(DLQ_REDIS_KEY)
        redis.delete(DLQ_REDIS_KEY)

        logger.warning("dlq_purged", deleted_count=count)

        return {
            "success": True,
            "deleted_count": count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except RedisError as e:
        logger.error("dlq_purge_error", error=str(e))
        return {"success": False, "error": str(e)}


def remove_poison_pill(task_id: str) -> Dict[str, Any]:
    """Entferne einen Poison Pill aus der DLQ ohne Retry.

    Für Tasks, die dauerhaft fehlerhaft sind und manuell behandelt wurden.

    Args:
        task_id: Task-ID des Poison Pills

    Returns:
        Dict mit Ergebnis
    """
    try:
        redis = _get_redis_client()
        all_tasks = redis.lrange(DLQ_REDIS_KEY, 0, -1)

        removed = 0
        for raw_task in all_tasks:
            try:
                task_data = json.loads(raw_task)
                if task_data.get("headers", {}).get("id") == task_id:
                    redis.lrem(DLQ_REDIS_KEY, 1, raw_task)
                    removed += 1
            except json.JSONDecodeError:
                continue

        # Aus Tracking entfernen
        if task_id in _failure_counts:
            del _failure_counts[task_id]

        logger.info("poison_pill_removed", task_id=task_id, removed_count=removed)

        return {
            "success": removed > 0,
            "task_id": task_id,
            "removed_count": removed,
        }

    except RedisError as e:
        logger.error("poison_pill_remove_error", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}


# =============================================================================
# Celery Tasks für DLQ Monitoring
# =============================================================================

@celery_app.task(base=CPUTask, name="app.workers.tasks.dlq_management_tasks.check_dlq_health")
def check_dlq_health() -> Dict[str, Any]:
    """Periodischer Health Check der DLQ.

    Wird von Celery Beat ausgeführt und löst Alerts bei Problemen aus.
    """
    stats = get_dlq_stats()

    # Logging basierend auf Status
    if stats["status"] == "critical":
        logger.critical(
            "dlq_critical",
            count=stats["count"],
            threshold=DLQ_CRITICAL_THRESHOLD,
            poison_pills=len(stats.get("poison_pills", []))
        )
        # Incident-Reporting für kritische DLQ-Zustände
        from app.services.incident_response_service import (
            report_system_incident, IncidentType, IncidentSeverity
        )
        report_system_incident(
            IncidentType.DLQ_CRITICAL,
            IncidentSeverity.CRITICAL,
            f"Dead Letter Queue kritisch: {stats['count']} fehlgeschlagene Tasks",
            details={
                "count": stats["count"],
                "threshold": DLQ_CRITICAL_THRESHOLD,
                "poison_pills": len(stats.get("poison_pills", [])),
                "oldest_task_age": stats.get("oldest_task_age"),
                "failure_patterns": stats.get("failure_patterns", {})
            }
        )

    elif stats["status"] == "warning":
        logger.warning(
            "dlq_warning",
            count=stats["count"],
            threshold=DLQ_ALERT_THRESHOLD
        )

    else:
        logger.debug("dlq_healthy", count=stats["count"])

    return stats


@celery_app.task(base=CPUTask, name="app.workers.tasks.dlq_management_tasks.cleanup_old_dlq_tasks")
def cleanup_old_dlq_tasks(max_age_days: int = 7) -> Dict[str, Any]:
    """Entferne alte Tasks aus der DLQ.

    Tasks älter als max_age_days werden gelöscht.

    Args:
        max_age_days: Maximales Alter in Tagen

    Returns:
        Dict mit Anzahl entfernter Tasks
    """
    try:
        redis = _get_redis_client()
        all_tasks = redis.lrange(DLQ_REDIS_KEY, 0, -1)

        cutoff_timestamp = time.time() - (max_age_days * 24 * 60 * 60)
        removed = 0

        for raw_task in all_tasks:
            try:
                task_data = json.loads(raw_task)
                task_ts = task_data.get("properties", {}).get("timestamp", 0)

                if task_ts < cutoff_timestamp:
                    redis.lrem(DLQ_REDIS_KEY, 1, raw_task)
                    removed += 1

            except (json.JSONDecodeError, TypeError):
                continue

        logger.info("dlq_old_tasks_cleaned", removed=removed, max_age_days=max_age_days)

        return {
            "success": True,
            "removed_count": removed,
            "max_age_days": max_age_days,
        }

    except RedisError as e:
        logger.error("dlq_cleanup_error", error=str(e))
        return {"success": False, "error": str(e)}


# =============================================================================
# Task Failure Hook für Poison-Pill-Detection
# =============================================================================

def record_task_failure(task_id: str, task_name: str) -> None:
    """Registriere Task-Failure für Poison-Pill-Detection.

    Wird vom task_failure Signal aufgerufen.
    """
    _failure_counts[task_id] = _failure_counts.get(task_id, 0) + 1

    if _failure_counts[task_id] >= POISON_PILL_THRESHOLD:
        logger.warning(
            "poison_pill_detected",
            task_id=task_id,
            task_name=task_name,
            failure_count=_failure_counts[task_id]
        )
