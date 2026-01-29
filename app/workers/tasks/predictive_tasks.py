# -*- coding: utf-8 -*-
"""
Predictive Maintenance Celery Tasks.

Sammelt Metriken und fuehrt Vorhersagen fuer proaktive Systemueberwachung aus:
- Metriken-Sammlung (GPU, Queue, Disk)
- System Health Predictions
- OCR Quality Forecasting
- Proaktive Alert-Generierung

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

import structlog

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Type aliases for mypy strict mode
MetricValue = Union[int, float, str, bool, None]
MetricDict = Dict[str, MetricValue]
StatsDict = Dict[str, Union[int, float, Dict[str, int]]]


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.predictive_tasks.collect_metrics_for_prediction",
    queue="monitoring",
    priority=2,
    ignore_result=True,
    soft_time_limit=55,
    time_limit=60,
)
def collect_metrics_for_prediction() -> MetricDict:
    """
    Sammelt System-Metriken fuer Vorhersage-Modelle.

    Wird jede Minute via Celery Beat ausgefuehrt.
    Zeichnet GPU VRAM, Queue-Tiefen, Disk-Nutzung und Worker-Status auf.

    Returns:
        Dict mit gesammelten Metriken
    """
    from app.services.predictive.system_health_predictor import (
        MetricType,
        get_health_predictor,
    )
    from app.services.predictive.ocr_quality_forecaster import (
        OCRBackend,
        get_quality_forecaster,
    )

    predictor = get_health_predictor()
    forecaster = get_quality_forecaster()

    collected: MetricDict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
    }

    try:
        # GPU VRAM Metrik
        gpu_vram_gb = _collect_gpu_vram()
        if gpu_vram_gb is not None:
            predictor.record_metric(MetricType.GPU_VRAM, gpu_vram_gb)
            collected["gpu_vram_gb"] = gpu_vram_gb

        # GPU Utilization
        gpu_util = _collect_gpu_utilization()
        if gpu_util is not None:
            predictor.record_metric(MetricType.GPU_UTILIZATION, gpu_util)
            collected["gpu_utilization"] = gpu_util

        # Queue Depths
        queue_depths = _collect_queue_depths()
        for queue_name, depth in queue_depths.items():
            predictor.record_queue_metric(queue_name, depth)
        collected["queue_depths"] = len(queue_depths)

        # Disk Usage
        disk_usage = _collect_disk_usage()
        if disk_usage is not None:
            predictor.record_metric(MetricType.DISK_USAGE, disk_usage)
            collected["disk_usage_percent"] = disk_usage

        # Memory Usage
        memory_usage = _collect_memory_usage()
        if memory_usage is not None:
            predictor.record_metric(MetricType.MEMORY_USAGE, memory_usage)
            collected["memory_usage_percent"] = memory_usage

        # CPU Usage
        cpu_usage = _collect_cpu_usage()
        if cpu_usage is not None:
            predictor.record_metric(MetricType.CPU_USAGE, cpu_usage)
            collected["cpu_usage_percent"] = cpu_usage

        # OCR Quality Metriken (aus Redis-Cache falls verfuegbar)
        ocr_metrics = _collect_ocr_quality_metrics()
        for backend_name, metrics in ocr_metrics.items():
            try:
                backend = OCRBackend(backend_name)
                forecaster.record_quality(
                    backend=backend,
                    cer=metrics.get("cer"),
                    wer=metrics.get("wer"),
                    confidence=metrics.get("confidence"),
                    umlaut_accuracy=metrics.get("umlaut_accuracy"),
                    document_count=metrics.get("document_count", 1),
                )
            except ValueError:
                # Unbekannter Backend-Name, ignorieren
                pass

        logger.debug(
            "predictive_metrics_collected",
            gpu_vram=collected.get("gpu_vram_gb"),
            queues=collected.get("queue_depths"),
            disk=collected.get("disk_usage_percent"),
        )

    except Exception as e:
        logger.error("predictive_metrics_collection_failed", **safe_error_log(e))
        collected["success"] = False
        collected["error"] = str(e)

    return collected


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.predictive_tasks.run_predictions",
    queue="monitoring",
    priority=2,
    ignore_result=True,
    soft_time_limit=55,
    time_limit=60,
)
def run_predictions() -> MetricDict:
    """
    Fuehrt alle System-Vorhersagen aus.

    Wird alle 5 Minuten via Celery Beat ausgefuehrt.
    Analysiert Trends und erstellt Vorhersagen fuer:
    - GPU VRAM Overflow
    - Queue Overflow
    - Disk Space Exhaustion
    - OCR Quality Degradation

    Returns:
        Dict mit Vorhersage-Ergebnissen
    """
    import asyncio
    from app.services.predictive.system_health_predictor import get_health_predictor
    from app.services.predictive.ocr_quality_forecaster import get_quality_forecaster

    predictor = get_health_predictor()
    forecaster = get_quality_forecaster()

    result: MetricDict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "predictions_count": 0,
        "warnings_count": 0,
        "critical_count": 0,
    }

    try:
        # System Health Predictions - verwende asyncio.run() statt new_event_loop()
        # um Memory Leaks und File Descriptor Exhaustion zu vermeiden
        async def _run_all_predictions() -> Tuple[List, List]:
            """Async helper fuer alle Predictions."""
            health_preds = await predictor.get_all_predictions()
            quality_alerts = await forecaster.get_all_degradation_alerts()
            return health_preds, quality_alerts

        health_predictions, degradation_alerts = asyncio.run(_run_all_predictions())

        result["predictions_count"] = len(health_predictions)

        # Zaehle Warnungen
        for pred in health_predictions:
            if pred.severity.value == "warning":
                result["warnings_count"] = int(result.get("warnings_count", 0)) + 1
            elif pred.severity.value == "critical":
                result["critical_count"] = int(result.get("critical_count", 0)) + 1

        # OCR Quality Degradation Alerts
        result["ocr_degradation_alerts"] = len(degradation_alerts)

        for alert in degradation_alerts:
            if alert.severity == "warning":
                result["warnings_count"] = int(result.get("warnings_count", 0)) + 1
            elif alert.severity == "critical":
                result["critical_count"] = int(result.get("critical_count", 0)) + 1

        logger.info(
            "predictions_completed",
            total=result.get("predictions_count"),
            warnings=result.get("warnings_count"),
            critical=result.get("critical_count"),
            ocr_alerts=result.get("ocr_degradation_alerts"),
        )

    except Exception as e:
        logger.error("predictions_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = str(e)

    return result


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.predictive_tasks.generate_predictive_alerts",
    queue="monitoring",
    priority=1,
    ignore_result=True,
    soft_time_limit=55,
    time_limit=60,
)
def generate_predictive_alerts() -> MetricDict:
    """
    Generiert proaktive Alerts basierend auf Vorhersagen.

    Wird alle 5 Minuten via Celery Beat ausgefuehrt.
    Kombiniert System Health und OCR Quality Predictions zu Alerts.

    Returns:
        Dict mit Alert-Statistiken
    """
    import asyncio
    from app.services.predictive.predictive_alerts_service import (
        get_predictive_alerts_service,
    )

    service = get_predictive_alerts_service()

    result: MetricDict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "alerts_generated": 0,
        "critical_alerts": 0,
    }

    try:
        # Generiere Alerts - verwende asyncio.run() statt new_event_loop()
        # um Memory Leaks und File Descriptor Exhaustion zu vermeiden
        new_alerts = asyncio.run(service.generate_all_alerts())
        result["alerts_generated"] = len(new_alerts)

        # Zaehle kritische Alerts
        critical_count = sum(
            1 for a in new_alerts if a.severity.value == "critical"
        )
        result["critical_alerts"] = critical_count

        # Log kritische Alerts einzeln (ohne PII)
        for alert in new_alerts:
            if alert.severity.value == "critical":
                logger.warning(
                    "critical_predictive_alert_generated",
                    alert_type=alert.alert_type.value,
                    eta_minutes=alert.eta_minutes,
                )

        # Hole Gesamtstatistik
        stats = service.get_alert_stats()
        result["total_active_alerts"] = stats.get("total_active", 0)

        logger.info(
            "predictive_alerts_generated",
            new_alerts=result.get("alerts_generated"),
            critical=result.get("critical_alerts"),
            total_active=result.get("total_active_alerts"),
        )

    except Exception as e:
        logger.error("predictive_alert_generation_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = str(e)

    return result


@celery_app.task(
    base=CPUTask,
    name="app.workers.tasks.predictive_tasks.cleanup_old_predictive_alerts",
    queue="maintenance",
    priority=3,
    ignore_result=True,
    soft_time_limit=55,
    time_limit=60,
)
def cleanup_old_predictive_alerts(max_age_hours: int = 24) -> MetricDict:
    """
    Entfernt alte proaktive Alerts.

    Wird taeglich via Celery Beat ausgefuehrt.

    Args:
        max_age_hours: Maximales Alter in Stunden (default: 24)

    Returns:
        Dict mit Cleanup-Ergebnis
    """
    from app.services.predictive.predictive_alerts_service import (
        get_predictive_alerts_service,
    )

    service = get_predictive_alerts_service()

    result: MetricDict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "removed_count": 0,
    }

    try:
        removed = service.clear_old_alerts(max_age_hours)
        result["removed_count"] = removed

        logger.info(
            "predictive_alerts_cleanup_completed",
            removed=removed,
            max_age_hours=max_age_hours,
        )

    except Exception as e:
        logger.error("predictive_alerts_cleanup_failed", **safe_error_log(e))
        result["success"] = False
        result["error"] = str(e)

    return result


# =============================================================================
# Helper Functions fuer Metrik-Sammlung
# =============================================================================


def _collect_gpu_vram() -> Optional[float]:
    """Sammelt GPU VRAM Nutzung in GB."""
    try:
        import torch
        if torch.cuda.is_available():
            # Speicher in Bytes, konvertiere zu GB
            allocated = torch.cuda.memory_allocated(0)
            return round(allocated / (1024 ** 3), 2)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("gpu_vram_collection_failed", error=str(e))
    return None


def _collect_gpu_utilization() -> Optional[float]:
    """Sammelt GPU Auslastung in Prozent."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("gpu_utilization_collection_failed", error=str(e))
    return None


def _collect_queue_depths() -> Dict[str, int]:
    """Sammelt Queue-Tiefen fuer alle bekannten Queues."""
    from app.workers.celery_app import celery_app

    depths: Dict[str, int] = {}
    known_queues = [
        "ocr", "high_priority", "default", "maintenance",
        "metadata", "embeddings", "gpu", "monitoring",
    ]

    try:
        with celery_app.pool.acquire(block=True) as conn:
            for queue_name in known_queues:
                try:
                    # Redis LLEN fuer Queue-Tiefe
                    depth = conn.default_channel.client.llen(queue_name)
                    depths[queue_name] = depth
                except Exception:
                    depths[queue_name] = 0
    except Exception as e:
        logger.debug("queue_depth_collection_failed", error=str(e))

    return depths


def _collect_disk_usage() -> Optional[float]:
    """Sammelt Festplatten-Nutzung in Prozent."""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        return round((used / total) * 100, 1)
    except Exception as e:
        logger.debug("disk_usage_collection_failed", error=str(e))
    return None


def _collect_memory_usage() -> Optional[float]:
    """Sammelt Arbeitsspeicher-Nutzung in Prozent."""
    try:
        import psutil
        memory = psutil.virtual_memory()
        return round(memory.percent, 1)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("memory_usage_collection_failed", error=str(e))
    return None


def _collect_cpu_usage() -> Optional[float]:
    """Sammelt CPU-Nutzung in Prozent."""
    try:
        import psutil
        return round(psutil.cpu_percent(interval=0.1), 1)
    except ImportError:
        pass
    except Exception as e:
        logger.debug("cpu_usage_collection_failed", error=str(e))
    return None


def _collect_ocr_quality_metrics() -> Dict[str, Dict[str, Optional[float]]]:
    """
    Sammelt OCR-Qualitaetsmetriken aus Redis-Cache.

    Returns:
        Dict mit Backend -> Metriken Mapping
    """
    from redis import Redis
    from app.core.config import settings

    metrics: Dict[str, Dict[str, Optional[float]]] = {}

    try:
        redis_client = Redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=True,
            socket_timeout=2.0,
        )

        # Suche nach OCR-Qualitaets-Cache-Keys
        for backend in ["deepseek", "got_ocr", "surya", "surya_gpu"]:
            key = f"ocr_quality:{backend}:current"
            data = redis_client.hgetall(key)

            if data:
                metrics[backend] = {
                    "cer": float(data["cer"]) if data.get("cer") else None,
                    "wer": float(data["wer"]) if data.get("wer") else None,
                    "confidence": float(data["confidence"]) if data.get("confidence") else None,
                    "umlaut_accuracy": float(data["umlaut_accuracy"]) if data.get("umlaut_accuracy") else None,
                    "document_count": int(data.get("document_count", 1)),
                }

    except Exception as e:
        logger.debug("ocr_quality_metrics_collection_failed", error=str(e))

    return metrics
