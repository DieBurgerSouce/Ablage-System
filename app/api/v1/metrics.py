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
from app.services.gpu_metrics_service import get_gpu_metrics_service

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
# GPU METRICS
# =============================================================================


@router.get("/gpu", response_class=Response)
async def gpu_metrics_prometheus():
    """
    Prometheus metrics for GPU functionality.

    Returns GPU-specific metrics in Prometheus text format:
    - ablage_gpu_memory_used_bytes: VRAM-Nutzung
    - ablage_gpu_memory_total_bytes: VRAM gesamt
    - ablage_gpu_memory_percent: VRAM-Nutzung in Prozent
    - ablage_gpu_available: GPU-Verfuegbarkeit
    - ablage_ocr_requests_total: OCR-Anfragen nach Backend/Status
    - ablage_ocr_processing_duration_seconds: OCR-Verarbeitungszeit
    - ablage_ocr_batch_size: Batch-Groessen
    - ablage_ocr_errors_total: OCR-Fehler nach Typ
    - ablage_gpu_oom_errors_total: OOM-Fehler
    - ablage_gpu_oom_recoveries_total: Erfolgreiche OOM-Recoveries
    - ablage_model_load_duration_seconds: Model-Ladezeiten
    - ablage_ocr_cache_operations_total: Cache-Hits/Misses

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-gpu'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics/gpu'
    ```
    """
    metrics = get_gpu_metrics_service()
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


@router.get("/gpu/summary")
async def gpu_metrics_summary():
    """
    GPU metrics summary (JSON format).

    Returns GPU-specific metrics for dashboards:
    - GPU-Speicher-Status
    - Verfuegbarkeit
    - Letzte Aktualisierung

    Nuetzlich fuer:
    - GPU-Monitoring Dashboards
    - Kapazitaetsplanung
    - Performance-Analyse
    """
    metrics = get_gpu_metrics_service()
    return metrics.get_summary()


@router.get("/gpu/detailed")
async def gpu_metrics_detailed():
    """
    Detaillierte GPU-Metriken (JSON format).

    Returns comprehensive GPU metrics:
    - Hardware-Informationen
    - Speicher-Status
    - OCR-Statistiken
    - Cache-Performance
    - Model-Status

    **Hinweis**: Dieser Endpoint sammelt Metriken aus mehreren Quellen
    und kann bei hoher Last etwas laenger dauern.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    gpu_service = get_gpu_metrics_service()
    gpu_summary = gpu_service.get_summary()

    # Get OCR cache stats
    try:
        from app.services.ocr_cache_service import get_ocr_cache_service
        cache_service = get_ocr_cache_service()
        cache_stats = await cache_service.get_stats()
    except Exception as e:
        logger.warning("gpu_metrics_cache_stats_failed", error=str(e))
        cache_stats = {"error": str(e)}

    # Get GPU manager stats
    try:
        from app.gpu_manager import get_gpu_manager
        gpu_manager = get_gpu_manager()
        manager_stats = gpu_manager.get_detailed_status()
    except Exception as e:
        logger.warning("gpu_metrics_manager_stats_failed", error=str(e))
        manager_stats = {"error": str(e)}

    return {
        "gpu_hardware": gpu_summary.get("gpu", {}),
        "memory_management": manager_stats,
        "ocr_cache": cache_stats,
        "last_update": gpu_summary.get("last_update"),
    }


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


@router.get("/business/prometheus", response_class=Response)
async def business_metrics_prometheus():
    """
    Prometheus metrics for OCR and document processing.

    Returns business-specific metrics in Prometheus text format:

    **OCR Metrics:**
    - ablage_ocr_processing_total: OCR-Verarbeitungen nach Backend/Status
    - ablage_ocr_processing_duration_seconds: Verarbeitungsdauer
    - ablage_ocr_characters_extracted: Extrahierte Zeichen
    - ablage_ocr_confidence_score: Konfidenz-Scores
    - ablage_ocr_backend_selection_total: Backend-Auswahl
    - ablage_ocr_pages_processed_total: Verarbeitete Seiten

    **Fraktur/German Metrics:**
    - ablage_ocr_fraktur_detected_total: Fraktur-Erkennungen
    - ablage_ocr_umlaut_accuracy: Umlaut-Genauigkeit
    - ablage_ocr_postprocessing_corrections_total: Postprocessing-Korrekturen

    **Document Metrics:**
    - ablage_documents_uploaded_total: Hochgeladene Dokumente
    - ablage_document_size_bytes: Dokumentengroesse
    - ablage_document_page_count: Seitenanzahl
    - ablage_document_status_transitions_total: Status-Uebergaenge

    **Backpressure Metrics:**
    - ablage_backpressure_status: Aktueller Status
    - ablage_backpressure_queue_length_total: Queue-Laenge
    - ablage_backpressure_rejected_total: Abgelehnte Anfragen
    - ablage_backpressure_degraded_total: Degradierte Anfragen

    **Model Loading Metrics:**
    - ablage_model_loading_duration_seconds: Model-Ladedauer
    - ablage_model_loading_status: Model-Status
    - ablage_models_preloaded_total: Vorgeladene Modelle

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-business'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics/business/prometheus'
    ```
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/business/summary")
async def business_metrics_summary():
    """
    Business metrics summary (JSON format).

    Returns a structured summary of all business metrics categories.
    """
    from app.core.business_metrics import get_metrics_summary

    redis = await get_redis()

    # Get counters from Redis
    documents_processed = await redis.get_counter("ocr.documents_processed")
    documents_failed = await redis.get_counter("ocr.documents_failed")
    gpu_oom_errors = await redis.get_counter("gpu.oom_errors")

    # Calculate success rate
    total = documents_processed + documents_failed
    success_rate = (documents_processed / total * 100) if total > 0 else 0.0

    return {
        "overview": {
            "total_documents_processed": documents_processed,
            "total_documents_failed": documents_failed,
            "success_rate_percent": round(success_rate, 2),
            "gpu_oom_errors": gpu_oom_errors,
        },
        "metrics_categories": get_metrics_summary(),
        "hinweis": "Nutze /metrics/business/prometheus fuer Prometheus-Format"
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


@router.get("/cache-hit-rate")
async def get_cache_hit_rate_metrics():
    """
    Aggregierte Cache Hit-Rate Metriken.

    Zeigt Cache-Effizienz ueber alle Cache-Schichten:

    **OCR Cache:**
    - L1 (Memory) und L2 (Redis) Hit-Raten
    - Per-Backend Statistiken

    **API Cache:**
    - Endpoint-spezifische Hit-Raten
    - Latenz-Metriken

    **Prometheus Metriken:**
    - ablage_ocr_cache_operations_total
    - ablage_api_cache_operations_total

    Returns:
        Aggregierte Cache-Statistiken
    """
    import structlog
    from datetime import datetime, timezone

    logger = structlog.get_logger(__name__)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ocr_cache": {},
        "api_cache": {},
        "prometheus_metrics": {},
        "recommendations": [],
    }

    # OCR Cache Statistics
    try:
        from app.services.ocr_cache_service import get_ocr_cache_service
        ocr_cache = get_ocr_cache_service()
        ocr_stats = await ocr_cache.get_stats()
        result["ocr_cache"] = {
            "enabled": ocr_stats.get("enabled", False),
            "l1_cache": ocr_stats.get("l1_cache", {}),
            "l2_cache": ocr_stats.get("l2_cache", {}),
            "per_backend": ocr_stats.get("per_backend", {}),
            "overall": ocr_stats.get("overall", {}),
        }
    except Exception as e:
        logger.warning("ocr_cache_stats_error", error=str(e))
        result["ocr_cache"]["error"] = str(e)

    # Try to get Prometheus metrics
    try:
        from prometheus_client import REGISTRY

        # API Cache metrics
        api_cache_hits = 0
        api_cache_misses = 0
        for metric in REGISTRY.collect():
            if metric.name == "ablage_api_cache_operations_total":
                for sample in metric.samples:
                    if sample.labels.get("operation") == "hit":
                        api_cache_hits += sample.value
                    elif sample.labels.get("operation") == "miss":
                        api_cache_misses += sample.value

        total_api = api_cache_hits + api_cache_misses
        api_hit_rate = (api_cache_hits / total_api * 100) if total_api > 0 else 0

        result["api_cache"] = {
            "hits": int(api_cache_hits),
            "misses": int(api_cache_misses),
            "total_requests": int(total_api),
            "hit_rate_percent": round(api_hit_rate, 2),
        }

        # OCR Cache Prometheus metrics
        ocr_l1_hits = 0
        ocr_l2_hits = 0
        ocr_misses = 0
        for metric in REGISTRY.collect():
            if metric.name == "ablage_ocr_cache_operations_total":
                for sample in metric.samples:
                    op = sample.labels.get("operation")
                    level = sample.labels.get("level")
                    if op == "hit":
                        if level == "l1":
                            ocr_l1_hits += sample.value
                        else:
                            ocr_l2_hits += sample.value
                    elif op == "miss":
                        ocr_misses += sample.value

        total_ocr = ocr_l1_hits + ocr_l2_hits + ocr_misses
        ocr_combined_rate = ((ocr_l1_hits + ocr_l2_hits) / total_ocr * 100) if total_ocr > 0 else 0

        result["prometheus_metrics"] = {
            "ocr_cache": {
                "l1_hits": int(ocr_l1_hits),
                "l2_hits": int(ocr_l2_hits),
                "misses": int(ocr_misses),
                "total": int(total_ocr),
                "combined_hit_rate_percent": round(ocr_combined_rate, 2),
            },
            "api_cache": {
                "hits": int(api_cache_hits),
                "misses": int(api_cache_misses),
                "total": int(total_api),
                "hit_rate_percent": round(api_hit_rate, 2),
            },
        }
    except Exception as e:
        logger.warning("prometheus_metrics_error", error=str(e))
        result["prometheus_metrics"]["error"] = str(e)

    # Generate recommendations
    recommendations = []

    # Check OCR cache hit rate
    ocr_overall = result.get("ocr_cache", {}).get("overall", {})
    if ocr_overall.get("combined_hit_rate_percent", 100) < 30:
        recommendations.append({
            "type": "ocr_cache",
            "severity": "warning",
            "message": "OCR Cache Hit-Rate unter 30% - pruefe Cache-TTL und Backend-Auswahl",
        })

    # Check API cache hit rate
    if result.get("api_cache", {}).get("hit_rate_percent", 100) < 50:
        recommendations.append({
            "type": "api_cache",
            "severity": "info",
            "message": "API Cache Hit-Rate unter 50% - pruefe Cache-Konfiguration",
        })

    result["recommendations"] = recommendations

    return result


@router.get("/database")
async def get_database_metrics():
    """
    Database Performance Metriken.

    Zeigt Datenbank-Performance-Statistiken:

    **Query Performance:**
    - Durchschnittliche Query-Dauer
    - Slow Query Zaehler
    - Queries pro Operation

    **Connection Pool:**
    - Pool-Groesse
    - Aktive Connections
    - Overflow-Connections

    **Prometheus Metriken:**
    - ablage_db_query_duration_seconds
    - ablage_db_query_total
    - ablage_db_slow_queries_total

    Returns:
        Database Performance Statistiken
    """
    import structlog
    from datetime import datetime, timezone

    logger = structlog.get_logger(__name__)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "connection_pool": {},
        "query_stats": {},
        "slow_queries": {},
        "recommendations": [],
    }

    # Get connection pool stats
    try:
        from app.api.dependencies import engine
        pool = engine.pool

        if pool:
            result["connection_pool"] = {
                "size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "checked_in": pool.checkedin(),
            }

            # Calculate pool utilization
            total_connections = pool.size() + pool.overflow()
            if total_connections > 0:
                utilization = pool.checkedout() / total_connections * 100
                result["connection_pool"]["utilization_percent"] = round(utilization, 2)
    except Exception as e:
        logger.warning("db_pool_stats_error", error=str(e))
        result["connection_pool"]["error"] = str(e)

    # Get Prometheus metrics for query stats
    try:
        from prometheus_client import REGISTRY

        query_counts = {"select": 0, "insert": 0, "update": 0, "delete": 0, "other": 0}
        error_counts = {"select": 0, "insert": 0, "update": 0, "delete": 0, "other": 0}
        slow_query_counts = {}

        for metric in REGISTRY.collect():
            if metric.name == "ablage_db_query_total":
                for sample in metric.samples:
                    op = sample.labels.get("operation", "other")
                    status = sample.labels.get("status", "success")
                    if status == "success":
                        query_counts[op] = query_counts.get(op, 0) + int(sample.value)
                    else:
                        error_counts[op] = error_counts.get(op, 0) + int(sample.value)

            elif metric.name == "ablage_db_slow_queries_total":
                for sample in metric.samples:
                    table = sample.labels.get("table", "unknown")
                    slow_query_counts[table] = int(sample.value)

        total_queries = sum(query_counts.values())
        total_errors = sum(error_counts.values())

        result["query_stats"] = {
            "total_queries": total_queries,
            "total_errors": total_errors,
            "error_rate_percent": round(total_errors / (total_queries + total_errors) * 100, 2) if (total_queries + total_errors) > 0 else 0,
            "by_operation": query_counts,
            "errors_by_operation": error_counts,
        }

        result["slow_queries"] = {
            "total": sum(slow_query_counts.values()),
            "by_table": slow_query_counts,
            "threshold_ms": 100,
        }

    except Exception as e:
        logger.warning("db_prometheus_metrics_error", error=str(e))
        result["query_stats"]["error"] = str(e)

    # Generate recommendations
    recommendations = []

    # Check pool utilization
    pool_util = result.get("connection_pool", {}).get("utilization_percent", 0)
    if pool_util > 80:
        recommendations.append({
            "type": "connection_pool",
            "severity": "warning",
            "message": f"Connection Pool Auslastung bei {pool_util}% - erhoehe Pool-Groesse",
        })

    # Check slow queries
    slow_total = result.get("slow_queries", {}).get("total", 0)
    if slow_total > 100:
        recommendations.append({
            "type": "slow_queries",
            "severity": "warning",
            "message": f"{slow_total} langsame Queries (>100ms) - pruefe Indizes und Queries",
        })

    # Check error rate
    error_rate = result.get("query_stats", {}).get("error_rate_percent", 0)
    if error_rate > 1:
        recommendations.append({
            "type": "query_errors",
            "severity": "critical",
            "message": f"Datenbank-Fehlerrate bei {error_rate}% - pruefe Verbindung und Logs",
        })

    result["recommendations"] = recommendations

    return result


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


# =============================================================================
# SLO/SLI METRICS
# =============================================================================


@router.get("/slo")
async def get_slo_metrics():
    """
    Service Level Objectives (SLO) Status.

    Zeigt den aktuellen Status der definierten SLOs:

    **Verfuegbarkeit:**
    - Ziel: 99.5% Uptime
    - Messung: Erfolgreiche Requests / Gesamt-Requests

    **OCR-Verarbeitung:**
    - Ziel: 95% der Dokumente in <5s verarbeitet
    - Ziel: 99% der Dokumente in <30s verarbeitet
    - Ziel: <5% Fehlerrate

    **Umlaut-Genauigkeit:**
    - Ziel: 100% korrekte Umlaut-Erkennung (ä, ö, ü, ß)

    **Response-Zeiten:**
    - API p50: <100ms
    - API p95: <500ms
    - API p99: <2000ms

    **GPU:**
    - VRAM-Nutzung: <85%
    - OOM-Rate: <1%

    Nuetzlich fuer:
    - Compliance-Reporting
    - Performance-Dashboards
    - Alerting-Schwellwerte
    """
    import structlog
    from datetime import datetime, timedelta

    logger = structlog.get_logger(__name__)

    redis = await get_redis()

    # SLO-Definitionen
    slo_definitions = {
        "availability": {
            "name": "Verfuegbarkeit",
            "target": 0.995,
            "unit": "Prozent",
            "description": "99.5% Uptime"
        },
        "ocr_processing_5s": {
            "name": "OCR Verarbeitung <5s",
            "target": 0.95,
            "unit": "Prozent",
            "description": "95% der Dokumente in unter 5 Sekunden"
        },
        "ocr_processing_30s": {
            "name": "OCR Verarbeitung <30s",
            "target": 0.99,
            "unit": "Prozent",
            "description": "99% der Dokumente in unter 30 Sekunden"
        },
        "ocr_error_rate": {
            "name": "OCR Fehlerrate",
            "target": 0.05,
            "unit": "Prozent (max)",
            "description": "Maximal 5% Fehlerrate",
            "is_upper_bound": True
        },
        "umlaut_accuracy": {
            "name": "Umlaut-Genauigkeit",
            "target": 1.0,
            "unit": "Prozent",
            "description": "100% korrekte Umlaut-Erkennung"
        },
        "api_latency_p50": {
            "name": "API Latenz p50",
            "target": 100,
            "unit": "ms (max)",
            "description": "50. Perzentil unter 100ms",
            "is_upper_bound": True
        },
        "api_latency_p95": {
            "name": "API Latenz p95",
            "target": 500,
            "unit": "ms (max)",
            "description": "95. Perzentil unter 500ms",
            "is_upper_bound": True
        },
        "api_latency_p99": {
            "name": "API Latenz p99",
            "target": 2000,
            "unit": "ms (max)",
            "description": "99. Perzentil unter 2000ms",
            "is_upper_bound": True
        },
        "gpu_vram_usage": {
            "name": "GPU VRAM Nutzung",
            "target": 0.85,
            "unit": "Prozent (max)",
            "description": "VRAM unter 85%",
            "is_upper_bound": True
        },
        "gpu_oom_rate": {
            "name": "GPU OOM Rate",
            "target": 0.01,
            "unit": "Prozent (max)",
            "description": "Maximal 1% OOM-Fehler",
            "is_upper_bound": True
        }
    }

    # Aktuelle Werte sammeln
    sli_values = {}

    try:
        # OCR-Metriken
        documents_processed = await redis.get_counter("ocr.documents_processed")
        documents_failed = await redis.get_counter("ocr.documents_failed")
        gpu_oom_errors = await redis.get_counter("gpu.oom_errors")

        total_docs = documents_processed + documents_failed
        if total_docs > 0:
            sli_values["availability"] = documents_processed / total_docs
            sli_values["ocr_error_rate"] = documents_failed / total_docs
            sli_values["gpu_oom_rate"] = gpu_oom_errors / total_docs if gpu_oom_errors else 0
        else:
            sli_values["availability"] = 1.0
            sli_values["ocr_error_rate"] = 0.0
            sli_values["gpu_oom_rate"] = 0.0

        # GPU VRAM
        try:
            gpu_service = get_gpu_metrics_service()
            gpu_summary = gpu_service.get_summary()
            if "memory_percent" in gpu_summary.get("gpu", {}):
                sli_values["gpu_vram_usage"] = gpu_summary["gpu"]["memory_percent"] / 100.0
            else:
                sli_values["gpu_vram_usage"] = 0.0
        except Exception as e:
            logger.warning("slo_gpu_metrics_unavailable", error=str(e))
            sli_values["gpu_vram_usage"] = None

        # Latenz-Perzentile (aus Redis Histogramm wenn verfuegbar)
        try:
            p50 = await redis.get("metrics:api_latency:p50")
            p95 = await redis.get("metrics:api_latency:p95")
            p99 = await redis.get("metrics:api_latency:p99")
            sli_values["api_latency_p50"] = float(p50) if p50 else None
            sli_values["api_latency_p95"] = float(p95) if p95 else None
            sli_values["api_latency_p99"] = float(p99) if p99 else None
        except Exception:
            sli_values["api_latency_p50"] = None
            sli_values["api_latency_p95"] = None
            sli_values["api_latency_p99"] = None

        # OCR-Verarbeitungszeiten (aus Redis wenn verfuegbar)
        try:
            ocr_under_5s = await redis.get("metrics:ocr:under_5s_rate")
            ocr_under_30s = await redis.get("metrics:ocr:under_30s_rate")
            sli_values["ocr_processing_5s"] = float(ocr_under_5s) if ocr_under_5s else None
            sli_values["ocr_processing_30s"] = float(ocr_under_30s) if ocr_under_30s else None
        except Exception:
            sli_values["ocr_processing_5s"] = None
            sli_values["ocr_processing_30s"] = None

        # Umlaut-Genauigkeit (aus Redis wenn verfuegbar)
        try:
            umlaut_acc = await redis.get("metrics:ocr:umlaut_accuracy_avg")
            sli_values["umlaut_accuracy"] = float(umlaut_acc) if umlaut_acc else None
        except Exception:
            sli_values["umlaut_accuracy"] = None

    except Exception as e:
        logger.error("slo_metrics_collection_error", error=str(e))

    # SLO-Status berechnen
    slo_status = {}
    overall_compliant = True

    for slo_key, slo_def in slo_definitions.items():
        current_value = sli_values.get(slo_key)
        target = slo_def["target"]
        is_upper_bound = slo_def.get("is_upper_bound", False)

        if current_value is not None:
            if is_upper_bound:
                compliant = current_value <= target
                margin = target - current_value
            else:
                compliant = current_value >= target
                margin = current_value - target

            status = "erfuellt" if compliant else "verletzt"
        else:
            compliant = None
            margin = None
            status = "keine_daten"

        if compliant is False:
            overall_compliant = False

        slo_status[slo_key] = {
            "name": slo_def["name"],
            "description": slo_def["description"],
            "target": target,
            "current_value": round(current_value, 4) if current_value is not None else None,
            "status": status,
            "compliant": compliant,
            "margin": round(margin, 4) if margin is not None else None,
            "unit": slo_def["unit"]
        }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_status": "erfuellt" if overall_compliant else "verletzt",
        "slos": slo_status,
        "summary": {
            "total_slos": len(slo_definitions),
            "compliant": sum(1 for s in slo_status.values() if s["compliant"] is True),
            "violated": sum(1 for s in slo_status.values() if s["compliant"] is False),
            "no_data": sum(1 for s in slo_status.values() if s["compliant"] is None)
        }
    }


@router.get("/slo/history")
async def get_slo_history(
    days: int = 7,
    slo_key: str = None,
    current_user: User = Depends(get_current_active_user)
):
    """
    SLO-Verlauf ueber Zeit.

    Zeigt historische SLO-Daten fuer Trend-Analyse und Reporting.

    **Parameter:**
    - days: Anzahl der Tage (1-30)
    - slo_key: Spezifisches SLO (optional, sonst alle)

    **Rueckgabe:**
    - Taegliche SLO-Werte
    - Trend-Richtung
    - Durchschnittswerte

    Nuetzlich fuer:
    - SLO-Reports
    - Trend-Erkennung
    - Kapazitaetsplanung
    """
    from datetime import datetime, timedelta

    if days < 1 or days > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="days muss zwischen 1 und 30 liegen"
        )

    redis = await get_redis()
    history = {}

    # SLO-Keys die wir verfolgen
    tracked_slos = ["availability", "ocr_error_rate", "gpu_vram_usage"]
    if slo_key:
        if slo_key not in tracked_slos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekanntes SLO: {slo_key}. Verfuegbar: {tracked_slos}"
            )
        tracked_slos = [slo_key]

    for slo in tracked_slos:
        daily_values = []
        for day_offset in range(days):
            date = (datetime.now(timezone.utc) - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            key = f"slo:history:{slo}:{date}"

            try:
                value = await redis.get(key)
                if value:
                    daily_values.append({
                        "date": date,
                        "value": float(value)
                    })
                else:
                    daily_values.append({
                        "date": date,
                        "value": None
                    })
            except Exception:
                daily_values.append({
                    "date": date,
                    "value": None
                })

        # Trend berechnen
        valid_values = [v["value"] for v in daily_values if v["value"] is not None]
        if len(valid_values) >= 2:
            # Einfacher Trend: Vergleich erster/letzter Wert
            trend = "steigend" if valid_values[0] > valid_values[-1] else "fallend" if valid_values[0] < valid_values[-1] else "stabil"
            avg = sum(valid_values) / len(valid_values)
        else:
            trend = "unbekannt"
            avg = valid_values[0] if valid_values else None

        history[slo] = {
            "daily_values": daily_values,
            "trend": trend,
            "average": round(avg, 4) if avg is not None else None,
            "data_points": len(valid_values)
        }

    return {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history": history
    }


@router.get("/ocr-quality")
async def get_ocr_quality_metrics():
    """
    OCR-Qualitaetsmetriken (aggregiert).

    Zeigt aggregierte Qualitaetsmetriken ueber alle OCR-Verarbeitungen:

    **Character Error Rate (CER):**
    - Durchschnitt, Min, Max, Verteilung

    **Word Error Rate (WER):**
    - Durchschnitt, Min, Max, Verteilung

    **Umlaut-Genauigkeit:**
    - Durchschnitt pro Backend
    - Haeufigste Fehler

    **Backend-Vergleich:**
    - Qualitaet nach OCR-Backend
    - Verarbeitungszeiten nach Backend

    Nuetzlich fuer:
    - Backend-Auswahl-Optimierung
    - Qualitaetsueberwachung
    - Benchmarking
    """
    import structlog
    logger = structlog.get_logger(__name__)

    redis = await get_redis()

    quality_metrics = {
        "timestamp": None,
        "cer": {},
        "wer": {},
        "umlaut_accuracy": {},
        "by_backend": {},
        "sample_count": 0
    }

    try:
        from datetime import datetime, timezone
        quality_metrics["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Aggregierte CER-Metriken
        cer_avg = await redis.get("metrics:ocr:cer:avg")
        cer_p50 = await redis.get("metrics:ocr:cer:p50")
        cer_p95 = await redis.get("metrics:ocr:cer:p95")

        quality_metrics["cer"] = {
            "average": float(cer_avg) if cer_avg else None,
            "p50": float(cer_p50) if cer_p50 else None,
            "p95": float(cer_p95) if cer_p95 else None,
            "target": 0.05,  # 5% max CER
            "unit": "Fehlerrate (0-1)"
        }

        # Aggregierte WER-Metriken
        wer_avg = await redis.get("metrics:ocr:wer:avg")
        wer_p50 = await redis.get("metrics:ocr:wer:p50")
        wer_p95 = await redis.get("metrics:ocr:wer:p95")

        quality_metrics["wer"] = {
            "average": float(wer_avg) if wer_avg else None,
            "p50": float(wer_p50) if wer_p50 else None,
            "p95": float(wer_p95) if wer_p95 else None,
            "target": 0.10,  # 10% max WER
            "unit": "Fehlerrate (0-1)"
        }

        # Umlaut-Genauigkeit
        umlaut_avg = await redis.get("metrics:ocr:umlaut_accuracy:avg")

        quality_metrics["umlaut_accuracy"] = {
            "average": float(umlaut_avg) if umlaut_avg else None,
            "target": 1.0,  # 100%
            "unit": "Genauigkeit (0-1)"
        }

        # Backend-spezifische Metriken
        backends = ["deepseek", "got_ocr", "surya"]
        for backend in backends:
            backend_cer = await redis.get(f"metrics:ocr:cer:{backend}:avg")
            backend_wer = await redis.get(f"metrics:ocr:wer:{backend}:avg")
            backend_umlaut = await redis.get(f"metrics:ocr:umlaut:{backend}:avg")
            backend_time = await redis.get(f"metrics:ocr:time:{backend}:avg")
            backend_count = await redis.get_counter(f"ocr.processed.{backend}")

            quality_metrics["by_backend"][backend] = {
                "cer_avg": float(backend_cer) if backend_cer else None,
                "wer_avg": float(backend_wer) if backend_wer else None,
                "umlaut_accuracy": float(backend_umlaut) if backend_umlaut else None,
                "avg_processing_time_ms": float(backend_time) if backend_time else None,
                "documents_processed": backend_count
            }

        # Gesamtzahl der Samples
        sample_count = await redis.get_counter("ocr.quality_samples")
        quality_metrics["sample_count"] = sample_count

    except Exception as e:
        logger.error("ocr_quality_metrics_error", error=str(e))
        quality_metrics["error"] = str(e)

    return quality_metrics


# =============================================================================
# WEBHOOK / CIRCUIT BREAKER METRIKEN
# =============================================================================


@router.get("/webhooks")
async def get_webhook_metrics():
    """
    Webhook und Circuit Breaker Metriken.

    Zeigt Webhook-Zustellungs- und Circuit Breaker-Statistiken:

    **Circuit Breaker:**
    - Anzahl offener Circuits
    - Zustand pro URL (closed/open/half_open)
    - Fehler-Zaehler
    - Letzte Fehler-Zeitpunkte

    **Webhook-Zustellungen:**
    - Erfolgreiche Zustellungen
    - Fehlgeschlagene Zustellungen
    - Durch Circuit Breaker blockierte Zustellungen
    - Durchschnittliche Zustellungsdauer

    **Prometheus Metriken:**
    - ablage_webhook_deliveries_total
    - ablage_webhook_delivery_duration_seconds
    - ablage_webhook_circuit_breakers_open
    - ablage_webhook_circuit_breaker_transitions_total

    Returns:
        Webhook und Circuit Breaker Statistiken
    """
    import structlog
    from datetime import datetime, timezone

    logger = structlog.get_logger(__name__)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "circuit_breaker": {},
        "delivery_stats": {},
        "recommendations": [],
    }

    # Get circuit breaker stats
    try:
        from app.services.webhook_dispatcher import get_webhook_circuit_breaker

        circuit_breaker = get_webhook_circuit_breaker()
        cb_stats = circuit_breaker.get_stats()

        result["circuit_breaker"] = {
            "total_tracked_urls": cb_stats["total_tracked"],
            "by_state": cb_stats["by_state"],
            "open_circuits": cb_stats["open_circuits"],
            "configuration": {
                "failure_threshold": circuit_breaker.FAILURE_THRESHOLD,
                "success_threshold": circuit_breaker.SUCCESS_THRESHOLD,
                "open_timeout_seconds": circuit_breaker.OPEN_TIMEOUT_SECONDS,
                "half_open_max_calls": circuit_breaker.HALF_OPEN_MAX_CALLS,
            }
        }
    except Exception as e:
        logger.warning("circuit_breaker_stats_error", error=str(e))
        result["circuit_breaker"]["error"] = str(e)

    # Get delivery stats from Prometheus
    try:
        from prometheus_client import REGISTRY

        success_count = 0
        failed_count = 0
        circuit_open_count = 0

        for metric in REGISTRY.collect():
            if metric.name == "ablage_webhook_deliveries_total":
                for sample in metric.samples:
                    if sample.name.endswith("_total"):
                        status = sample.labels.get("status", "")
                        if status == "success":
                            success_count += sample.value
                        elif status == "failed":
                            failed_count += sample.value
                        elif status == "circuit_open":
                            circuit_open_count += sample.value

        total = success_count + failed_count + circuit_open_count
        success_rate = (success_count / total * 100) if total > 0 else 0

        result["delivery_stats"] = {
            "total_deliveries": int(total),
            "successful": int(success_count),
            "failed": int(failed_count),
            "blocked_by_circuit": int(circuit_open_count),
            "success_rate_percent": round(success_rate, 2),
        }
    except Exception as e:
        logger.warning("webhook_prometheus_metrics_error", error=str(e))
        result["delivery_stats"]["error"] = str(e)

    # Generate recommendations
    recommendations = []

    # Check for open circuits
    open_count = result.get("circuit_breaker", {}).get("by_state", {}).get("open", 0)
    half_open_count = result.get("circuit_breaker", {}).get("by_state", {}).get("half_open", 0)

    if open_count > 0:
        recommendations.append({
            "type": "circuit_breaker",
            "severity": "warning",
            "message": f"{open_count} Circuit Breaker offen - pruefe Webhook-Endpunkte",
        })

    if half_open_count > 0:
        recommendations.append({
            "type": "circuit_breaker",
            "severity": "info",
            "message": f"{half_open_count} Circuit Breaker im Test-Modus (half-open)",
        })

    # Check success rate
    success_rate = result.get("delivery_stats", {}).get("success_rate_percent", 100)
    if success_rate < 90:
        recommendations.append({
            "type": "delivery",
            "severity": "warning",
            "message": f"Webhook-Erfolgsrate nur {success_rate}% - pruefe Endpunkt-Verfuegbarkeit",
        })

    result["recommendations"] = recommendations

    return result


@router.post("/webhooks/circuit-breaker/reset")
async def reset_circuit_breaker(
    url: str | None = None,
    current_user: User = Depends(get_current_superuser)
):
    """
    Circuit Breaker zuruecksetzen.

    **REQUIRES ADMIN AUTHENTICATION**

    Setzt Circuit Breaker zurueck:
    - Mit URL-Parameter: Nur den Circuit Breaker fuer diese URL zuruecksetzen
    - Ohne URL-Parameter: Alle Circuit Breaker zuruecksetzen

    Args:
        url: Optional - Spezifische URL zum Zuruecksetzen
        current_user: Authentifizierter Admin-User

    Returns:
        Erfolgs-Status mit Anzahl zurueckgesetzter Circuits
    """
    import structlog
    logger = structlog.get_logger(__name__)

    from app.services.webhook_dispatcher import get_webhook_circuit_breaker

    circuit_breaker = get_webhook_circuit_breaker()

    # Log admin action
    logger.warning(
        "circuit_breaker_reset_initiated",
        admin_user_id=str(current_user.id),
        admin_email=current_user.email,
        target_url=url[:50] if url else "all"
    )

    # Get count before reset
    stats_before = circuit_breaker.get_stats()
    count_before = stats_before["total_tracked"]

    # Reset
    circuit_breaker.reset(url)

    # Get count after reset
    stats_after = circuit_breaker.get_stats()
    count_after = stats_after["total_tracked"]

    reset_count = count_before - count_after if url else count_before

    logger.info(
        "circuit_breaker_reset_completed",
        admin_user_id=str(current_user.id),
        circuits_reset=reset_count
    )

    return {
        "status": "erfolg",
        "nachricht": f"Circuit Breaker zurueckgesetzt",
        "circuits_reset": reset_count,
        "target": url[:50] if url else "alle",
        "durchgefuehrt_von": str(current_user.id),
    }
