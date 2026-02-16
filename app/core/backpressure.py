# -*- coding: utf-8 -*-
"""
Backpressure Handling für OCR API.

Verhindert Queue-Overflow durch:
- Queue-Längen-Monitoring
- Anfrage-Ablehnung bei hoher Last
- Graceful Degradation zu schnelleren Backends
- Response Headers mit Queue-Status

Konfiguration via Umgebungsvariablen:
- BACKPRESSURE_ENABLED: Aktivierung (default: True)
- BACKPRESSURE_QUEUE_THRESHOLD_WARNING: Warnung ab X Tasks (default: 50)
- BACKPRESSURE_QUEUE_THRESHOLD_CRITICAL: Ablehnung ab X Tasks (default: 100)
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import structlog
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)


class BackpressureConfig:
    """Konfiguration für Backpressure-Handling."""

    # Aktivierung
    ENABLED = os.environ.get("BACKPRESSURE_ENABLED", "true").lower() == "true"

    # Queue-Thresholds
    QUEUE_THRESHOLD_WARNING = int(os.environ.get("BACKPRESSURE_QUEUE_THRESHOLD_WARNING", "50"))
    QUEUE_THRESHOLD_CRITICAL = int(os.environ.get("BACKPRESSURE_QUEUE_THRESHOLD_CRITICAL", "100"))
    QUEUE_THRESHOLD_REJECT = int(os.environ.get("BACKPRESSURE_QUEUE_THRESHOLD_REJECT", "200"))

    # Welche Queues werden geprüft
    MONITORED_QUEUES = ["ocr_high", "ocr_normal"]

    # Cache TTL für Queue-Status (Sekunden)
    STATUS_CACHE_TTL_SECONDS = 5

    # Retry-After Header Wert (Sekunden)
    RETRY_AFTER_SECONDS = 30


class BackpressureStatus:
    """Status-Informationen für Backpressure."""

    NORMAL = "normal"           # Alles OK, Anfragen akzeptiert
    WARNING = "warning"         # Hohe Last, Anfragen akzeptiert mit Warnung
    CRITICAL = "critical"       # Sehr hohe Last, nur dringende Anfragen
    OVERLOADED = "overloaded"   # Queue voll, Anfragen abgelehnt


# Cache für Queue-Status
_queue_status_cache: Optional[Dict[str, Any]] = None
_queue_status_timestamp: Optional[datetime] = None


def get_queue_lengths() -> Dict[str, int]:
    """
    Hole aktuelle Queue-Längen aus Redis.

    Returns:
        Dict mit Queue-Namen und Längen
    """
    try:
        from redis import Redis
        from celery import current_app


        redis_url = current_app.conf.broker_url
        redis_client = Redis.from_url(redis_url)

        queue_lengths = {}
        for queue_name in BackpressureConfig.MONITORED_QUEUES:
            try:
                length = redis_client.llen(queue_name)
                queue_lengths[queue_name] = length
            except Exception:
                queue_lengths[queue_name] = 0

        return queue_lengths

    except Exception as e:
        logger.warning("queue_length_check_failed", **safe_error_log(e))
        return {}


def get_backpressure_status(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Ermittle aktuellen Backpressure-Status.

    Verwendet einen Cache um Redis-Aufrufe zu minimieren.

    Args:
        force_refresh: Cache ignorieren und neu laden

    Returns:
        Dict mit Status-Informationen
    """
    global _queue_status_cache, _queue_status_timestamp

    # Cache prüfen
    if not force_refresh and _queue_status_cache and _queue_status_timestamp:
        age = (datetime.now(timezone.utc) - _queue_status_timestamp).total_seconds()
        if age < BackpressureConfig.STATUS_CACHE_TTL_SECONDS:
            return _queue_status_cache

    # Queue-Längen holen
    queue_lengths = get_queue_lengths()
    total_length = sum(queue_lengths.values())

    # Status bestimmen
    if total_length >= BackpressureConfig.QUEUE_THRESHOLD_REJECT:
        status = BackpressureStatus.OVERLOADED
    elif total_length >= BackpressureConfig.QUEUE_THRESHOLD_CRITICAL:
        status = BackpressureStatus.CRITICAL
    elif total_length >= BackpressureConfig.QUEUE_THRESHOLD_WARNING:
        status = BackpressureStatus.WARNING
    else:
        status = BackpressureStatus.NORMAL

    result = {
        "status": status,
        "total_queue_length": total_length,
        "queues": queue_lengths,
        "thresholds": {
            "warning": BackpressureConfig.QUEUE_THRESHOLD_WARNING,
            "critical": BackpressureConfig.QUEUE_THRESHOLD_CRITICAL,
            "reject": BackpressureConfig.QUEUE_THRESHOLD_REJECT,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Cache aktualisieren
    _queue_status_cache = result
    _queue_status_timestamp = datetime.now(timezone.utc)

    return result


def check_backpressure(
    priority: str = "normal",
    allow_degraded: bool = True
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Prüfe ob eine neue Anfrage akzeptiert werden kann.

    Args:
        priority: Anfrage-Prioritaet ("high", "normal", "low")
        allow_degraded: Ob bei hoher Last auf CPU-Backend gewechselt werden darf

    Returns:
        Tuple von:
        - accepted: Bool ob Anfrage akzeptiert wird
        - suggested_backend: Empfohlenes Backend bei Degradation
        - status: Status-Dictionary für Headers
    """
    if not BackpressureConfig.ENABLED:
        return True, None, {"status": BackpressureStatus.NORMAL}

    status = get_backpressure_status()
    backpressure_status = status["status"]

    # Normale Last - alles OK
    if backpressure_status == BackpressureStatus.NORMAL:
        return True, None, status

    # Warnung - akzeptieren mit Hinweis
    if backpressure_status == BackpressureStatus.WARNING:
        logger.info(
            "backpressure_warning",
            queue_length=status["total_queue_length"]
        )
        return True, None, status

    # Kritisch - nur High-Priority oder Degradation
    if backpressure_status == BackpressureStatus.CRITICAL:
        if priority == "high":
            logger.warning(
                "backpressure_critical_high_priority_accepted",
                queue_length=status["total_queue_length"]
            )
            return True, None, status

        if allow_degraded:
            # Empfehle CPU-Backend
            logger.warning(
                "backpressure_critical_degraded_mode",
                queue_length=status["total_queue_length"],
                suggested_backend="surya"
            )
            return True, "surya", status

        # Ablehnen
        return False, None, status

    # Überlastet - ablehnen (ausser high priority)
    if backpressure_status == BackpressureStatus.OVERLOADED:
        if priority == "high":
            logger.error(
                "backpressure_overloaded_high_priority",
                queue_length=status["total_queue_length"]
            )
            # Auch high priority nur mit Degradation
            return True, "surya", status

        logger.error(
            "backpressure_overloaded_rejected",
            queue_length=status["total_queue_length"]
        )
        return False, None, status

    return True, None, status


async def backpressure_dependency(request: Request) -> Dict[str, Any]:
    """
    FastAPI Dependency für Backpressure-Checking.

    Verwendung:
        @app.post("/ocr/process")
        async def process_document(
            backpressure: Dict = Depends(backpressure_dependency)
        ):
            ...

    Raises:
        HTTPException 503: Wenn System überlastet
    """
    if not BackpressureConfig.ENABLED:
        return {"status": BackpressureStatus.NORMAL, "accepted": True}

    # Prioritaet aus Header oder Query
    priority = request.headers.get("X-Priority", "normal").lower()
    if priority not in ["high", "normal", "low"]:
        priority = "normal"

    accepted, suggested_backend, status = check_backpressure(
        priority=priority,
        allow_degraded=True
    )

    if not accepted:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service vorübergehend überlastet",
                "message": f"Verarbeitungs-Queue hat {status['total_queue_length']} ausstehende Tasks. "
                           f"Bitte versuchen Sie es in {BackpressureConfig.RETRY_AFTER_SECONDS} Sekunden erneut.",
                "status": status["status"],
                "retry_after_seconds": BackpressureConfig.RETRY_AFTER_SECONDS,
            },
            headers={
                "Retry-After": str(BackpressureConfig.RETRY_AFTER_SECONDS),
                "X-Queue-Length": str(status["total_queue_length"]),
                "X-Backpressure-Status": status["status"],
            }
        )

    result = {
        "status": status["status"],
        "accepted": True,
        "suggested_backend": suggested_backend,
        "queue_length": status["total_queue_length"],
    }

    return result


def add_backpressure_headers(response: JSONResponse, status: Dict[str, Any]) -> JSONResponse:
    """
    Fuege Backpressure-Headers zur Response hinzu.

    Args:
        response: FastAPI JSONResponse
        status: Backpressure-Status Dictionary

    Returns:
        Response mit Headers
    """
    response.headers["X-Queue-Length"] = str(status.get("total_queue_length", 0))
    response.headers["X-Backpressure-Status"] = status.get("status", BackpressureStatus.NORMAL)

    if status.get("status") in [BackpressureStatus.WARNING, BackpressureStatus.CRITICAL]:
        response.headers["X-Backpressure-Warning"] = "true"

    return response


def get_backpressure_info() -> Dict[str, Any]:
    """
    Hole vollständige Backpressure-Information für Monitoring.

    Returns:
        Dict mit allen Backpressure-Metriken
    """
    status = get_backpressure_status(force_refresh=True)

    return {
        "enabled": BackpressureConfig.ENABLED,
        "current_status": status["status"],
        "queue_lengths": status["queues"],
        "total_queue_length": status["total_queue_length"],
        "thresholds": status["thresholds"],
        "config": {
            "monitored_queues": BackpressureConfig.MONITORED_QUEUES,
            "cache_ttl_seconds": BackpressureConfig.STATUS_CACHE_TTL_SECONDS,
            "retry_after_seconds": BackpressureConfig.RETRY_AFTER_SECONDS,
        },
        "recommendation": _get_recommendation(status["status"]),
        "timestamp": status["timestamp"],
    }


def _get_recommendation(status: str) -> str:
    """Generiere Empfehlung basierend auf Status."""
    if status == BackpressureStatus.NORMAL:
        return "System laeuft normal. Keine Aktion erforderlich."
    elif status == BackpressureStatus.WARNING:
        return "Erhöhte Last. Erwaeuge zusätzliche Worker zu starten."
    elif status == BackpressureStatus.CRITICAL:
        return "Kritische Last. Neue Anfragen werden auf CPU-Backend umgeleitet."
    elif status == BackpressureStatus.OVERLOADED:
        return "System überlastet. Neue Anfragen werden abgelehnt. Sofortiges Eingreifen erforderlich!"
    return "Unbekannter Status"
