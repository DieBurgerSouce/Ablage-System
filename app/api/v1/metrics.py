"""
Metrics API Endpoints.

Provides Prometheus metrics scraping and custom business metrics.
All sensitive endpoints require proper authentication.
"""

from fastapi import APIRouter, Response, Depends, HTTPException, status

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.redis_state import get_redis
from app.api.dependencies import get_current_superuser, get_current_active_user
from app.db.models import User
from app.services.search_metrics import get_search_metrics
from app.services.backup_metrics_service import get_backup_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


# =============================================================================
# PROMETHEUS METRICS ENDPOINT
# =============================================================================


@router.get("", response_class=Response)
@router.get("/prometheus", response_class=Response)
async def prometheus_metrics():
    """
    Prometheus metrics scrape endpoint.

    Returns metrics in Prometheus text format for scraping.

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-system'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics'
    ```
    """
    # Generate metrics from all registered collectors
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/search", response_class=Response)
async def search_metrics_prometheus():
    """
    Prometheus metrics for search functionality.

    Returns search-specific metrics in Prometheus text format:
    - search_requests_total: Suchanfragen nach Typ und Status
    - search_duration_seconds: Suchlatenz
    - search_results_count: Ergebnismengen
    - search_zero_results_total: Suchen ohne Ergebnisse
    - search_cache_operations_total: Cache-Treffer/Miss
    - search_cache_invalidations_total: Cache-Invalidierungen
    - search_embedding_generation_seconds: Embedding-Generierung
    - search_similar_requests_total: Aehnliche-Dokumente-Anfragen
    - search_filter_usage_total: Filter-Verwendung

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-search'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics/search'
    ```
    """
    metrics = get_search_metrics()
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


@router.get("/backup", response_class=Response)
async def backup_metrics_prometheus():
    """
    Prometheus metrics for backup functionality.

    Returns backup-specific metrics in Prometheus text format:
    - ablage_backup_last_success_timestamp: Letztes erfolgreiches Backup
    - ablage_backup_last_failure_timestamp: Letztes fehlgeschlagenes Backup
    - ablage_backup_success_total: Erfolgreiche Backups
    - ablage_backup_failure_total: Fehlgeschlagene Backups
    - ablage_backup_duration_seconds: Backup-Dauer
    - ablage_backup_size_bytes: Backup-Groesse
    - ablage_backup_validation_success_total: Erfolgreiche Validierungen
    - ablage_backup_validation_failure_total: Fehlgeschlagene Validierungen
    - ablage_backup_remote_sync_success_total: Remote-Sync Erfolge
    - ablage_backup_disk_usage_bytes: Speicherplatz-Nutzung
    - ablage_backup_disk_free_bytes: Freier Speicherplatz

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-backup'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics/backup'
    ```
    """
    metrics = get_backup_metrics()
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


@router.get("/backup/summary")
async def backup_metrics_summary():
    """
    Backup metrics summary (JSON format).

    Returns backup-specific metrics for dashboards:
    - Speicherplatz-Nutzung und Verfuegbarkeit
    - Anzahl Backup-Dateien nach Typ
    - Prometheus-Status

    Useful for custom dashboards and health monitoring.
    """
    metrics = get_backup_metrics()
    return metrics.get_summary()


# =============================================================================
# CUSTOM BUSINESS METRICS
# =============================================================================


@router.get("/business")
async def business_metrics():
    """
    Custom business metrics (JSON format).

    Returns business-specific metrics for dashboards.
    """
    redis = await get_redis()

    # Get counters from Redis
    documents_processed = await redis.get_counter("ocr.documents_processed")
    documents_failed = await redis.get_counter("ocr.documents_failed")
    gpu_oom_errors = await redis.get_counter("gpu.oom_errors")

    # Get agent statuses
    agent_statuses = await redis.get_all_agents_status()

    # Calculate success rate
    total = documents_processed + documents_failed
    success_rate = (documents_processed / total * 100) if total > 0 else 0.0

    return {
        "documents": {
            "total_processed": documents_processed,
            "total_failed": documents_failed,
            "success_rate_percent": round(success_rate, 2),
        },
        "gpu": {
            "oom_errors": gpu_oom_errors,
        },
        "agents": {
            "total_count": len(agent_statuses),
            "active_count": sum(
                1 for a in agent_statuses if a.get("status") == "running"
            ),
            "idle_count": sum(
                1 for a in agent_statuses if a.get("status") == "idle"
            ),
            "failed_count": sum(
                1 for a in agent_statuses if a.get("status") == "failed"
            ),
        },
        "agents_detail": agent_statuses,
    }


@router.get("/health")
async def metrics_health():
    """
    Health check for metrics system.

    Returns status of metrics collection components.
    """
    redis = await get_redis()

    # Check Redis connection
    redis_healthy = await redis.ping()

    return {
        "status": "healthy" if redis_healthy else "unhealthy",
        "components": {
            "redis": "healthy" if redis_healthy else "unhealthy",
            "prometheus": "healthy",  # Always healthy if endpoint responds
        },
    }


# =============================================================================
# OCR CACHE METRICS
# =============================================================================


@router.get("/ocr-cache")
async def ocr_cache_metrics():
    """
    OCR Cache Statistics (JSON format).

    Returns cache-specific metrics:
    - **enabled**: Ob Caching aktiviert ist
    - **redis_available**: Redis-Verbindungsstatus
    - **hits**: Cache-Treffer
    - **misses**: Cache-Fehlschlaege
    - **total_requests**: Gesamtzahl der Anfragen
    - **hit_rate_percent**: Trefferquote in Prozent
    - **default_ttl_seconds**: Standard-Cache-Lebenszeit

    Nuetzlich fuer:
    - Performance-Monitoring
    - Cache-Effizienz-Analyse
    - Ressourcen-Optimierung
    """
    from app.services.ocr_cache_service import get_ocr_cache_service

    service = get_ocr_cache_service()
    return await service.get_stats()


@router.delete("/ocr-cache/stats")
async def clear_ocr_cache_stats(
    current_user: User = Depends(get_current_superuser)
):
    """
    OCR Cache Statistiken zuruecksetzen.

    **REQUIRES ADMIN AUTHENTICATION**

    Setzt nur die Statistik-Zaehler zurueck (hits/misses),
    nicht die gecacheten Ergebnisse selbst.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    from app.services.ocr_cache_service import get_ocr_cache_service

    logger.warning(
        "ocr_cache_stats_reset_initiated",
        admin_user_id=str(current_user.id),
        admin_email=current_user.email
    )

    service = get_ocr_cache_service()
    success = await service.clear_stats()

    return {
        "status": "erfolg" if success else "fehlgeschlagen",
        "nachricht": "OCR-Cache-Statistiken wurden zurueckgesetzt" if success else "Zuruecksetzen fehlgeschlagen",
        "durchgefuehrt_von": str(current_user.id)
    }


@router.post("/reset")
async def reset_metrics(
    current_user: User = Depends(get_current_superuser)
):
    """
    Reset all metrics counters.

    **REQUIRES ADMIN AUTHENTICATION**

    This endpoint resets all business metrics counters to zero.
    Only superusers/administrators can perform this action.

    Args:
        current_user: Current authenticated superuser (injected via dependency)

    Returns:
        Success status with reset confirmation

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 403: If not a superuser
    """
    import structlog
    logger = structlog.get_logger(__name__)

    # Log the admin action for audit trail
    logger.warning(
        "metrics_reset_initiated",
        admin_user_id=str(current_user.id),
        admin_email=current_user.email,
        action="reset_all_metrics"
    )

    redis = await get_redis()

    # Reset counters
    await redis.reset_counter("ocr.documents_processed")
    await redis.reset_counter("ocr.documents_failed")
    await redis.reset_counter("gpu.oom_errors")

    logger.info(
        "metrics_reset_completed",
        admin_user_id=str(current_user.id)
    )

    return {
        "status": "erfolg",  # German: success
        "nachricht": "Alle Metriken-Zähler wurden auf 0 zurückgesetzt",  # All metrics counters reset to 0
        "durchgeführt_von": str(current_user.id),  # Performed by
    }
