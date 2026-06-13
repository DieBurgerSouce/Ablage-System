"""
Metrics API Endpoints.

Provides Prometheus metrics scraping and custom business metrics.
All sensitive endpoints require proper authentication.
"""

from typing import Optional

from app.core.types import JSONDict
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from fastapi import APIRouter, Response, Depends, HTTPException, status, Header

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
from app.services.datev.metrics import get_datev_metrics_service
from app.core.safe_errors import safe_error_log
from app.core.safe_errors import safe_error_detail

router = APIRouter(prefix="/metrics", tags=["metrics"])


# SECURITY FIX 27-10: PII Masking für Admin-Logs (GDPR-konform)
def _mask_admin_email_for_log(email: Optional[str]) -> str:
    """Maskiert Admin-Email-Adresse für Log-Ausgabe."""
    if not email or "@" not in email:
        return "[no-email]"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"


# =============================================================================
# PROMETHEUS METRICS ENDPOINT
# =============================================================================


def verify_metrics_token(authorization: str | None = None) -> bool:
    """
    Verifiziert den Metrics-Scrape-Token für interne Endpunkte.

    Args:
        authorization: Authorization Header (Bearer token)

    Returns:
        True wenn Token gültig oder kein Token konfiguriert

    Raises:
        HTTPException 401/403 wenn Token ungültig
    """
    from app.core.config import settings

    # Wenn kein Token konfiguriert, erlaube Zugriff (für Development)
    if not settings.METRICS_SCRAPE_TOKEN:
        return True

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extrahiere Token aus "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if parts[1] != settings.METRICS_SCRAPE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid metrics token",
        )

    return True


@router.get("/internal", response_class=Response)
async def internal_prometheus_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Internal Prometheus metrics endpoint for automated scraping.

    This endpoint is designed for Prometheus/Grafana scraping without
    requiring full user authentication. Instead, it uses a simple
    Bearer token configured via METRICS_SCRAPE_TOKEN environment variable.

    **Authentication:**
    - If METRICS_SCRAPE_TOKEN is set: Requires Bearer token in Authorization header
    - If METRICS_SCRAPE_TOKEN is not set: Allows unauthenticated access (dev mode)

    **Usage in prometheus.yml:**
    ```yaml
    scrape_configs:
      - job_name: 'ablage-backend'
        static_configs:
          - targets: ['backend:8000']
        metrics_path: '/api/v1/metrics/internal'
        bearer_token: '<your-metrics-token>'
    ```

    Returns:
        Prometheus metrics in text format
    """
    verify_metrics_token(authorization)

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/internal/backup", response_class=Response)
async def internal_backup_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Internal Prometheus metrics endpoint for backup scraping.

    Uses the same token-based auth as /internal endpoint.
    Designed for Prometheus scraping without user authentication.

    **Authentication:**
    - If METRICS_SCRAPE_TOKEN is set: Requires Bearer token
    - If METRICS_SCRAPE_TOKEN is not set: Allows unauthenticated access (dev mode)
    """
    verify_metrics_token(authorization)

    metrics = get_backup_metrics()

    # 2026-05-06: Bei jedem Prometheus-Scrape Disk-Usage neu berechnen.
    # Vorher: Gauge wurde nur via Celery-Beat-Task alle 15min im Worker-Prozess
    # aktualisiert -> Multi-Process-Bug, Backend-Prozess sah immer 0.
    # Jetzt: Backend-Prozess aktualisiert seine eigene Gauge-Instanz beim Scrape.
    # Performance: shutil.disk_usage ist O(1) syscall, ~0.1ms.
    try:
        metrics.update_disk_usage()
    except Exception as e:  # noqa: BLE001
        # Niemals Scrape failen lassen wegen Disk-Update-Error
        import structlog
        structlog.get_logger(__name__).warning(
            "backup_disk_usage_update_failed_at_scrape",
            error=str(e)[:200],
        )

    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


@router.get("/internal/ab-testing", response_class=Response)
async def internal_ab_testing_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Internal Prometheus metrics endpoint for A/B testing scraping.

    Converts A/B testing metrics to Prometheus text format.
    Uses token-based auth for Prometheus scraping.

    **Authentication:**
    - If METRICS_SCRAPE_TOKEN is set: Requires Bearer token
    - If METRICS_SCRAPE_TOKEN is not set: Allows unauthenticated access (dev mode)
    """
    verify_metrics_token(authorization)

    lines = []
    try:
        from app.services.rag.ab_testing_router import get_ab_testing_router

        ab_router = get_ab_testing_router()
        ab_status = ab_router.get_status()

        # Export config as gauge
        enabled_val = 1 if ab_status.get("enabled") else 0
        lines.append(f"# HELP ablage_ab_testing_enabled Whether A/B testing is enabled")
        lines.append(f"# TYPE ablage_ab_testing_enabled gauge")
        lines.append(f"ablage_ab_testing_enabled {enabled_val}")

        traffic_split = ab_status.get("traffic_split", 0)
        lines.append(f"# HELP ablage_ab_testing_traffic_split_percent Traffic split percentage for treatment")
        lines.append(f"# TYPE ablage_ab_testing_traffic_split_percent gauge")
        lines.append(f"ablage_ab_testing_traffic_split_percent {traffic_split}")

        # Export per-variant metrics
        ab_metrics = ab_status.get("metrics", {})
        for variant_name, variant_data in ab_metrics.items():
            if not isinstance(variant_data, dict):
                continue
            labels = f'variant="{variant_name}"'

            total_req = variant_data.get("total_requests", 0)
            lines.append(f"# HELP ablage_ab_testing_requests_total Total requests per variant")
            lines.append(f"# TYPE ablage_ab_testing_requests_total counter")
            lines.append(f'ablage_ab_testing_requests_total{{{labels}}} {total_req}')

            avg_latency = variant_data.get("avg_latency_ms", 0)
            lines.append(f"# HELP ablage_ab_testing_avg_latency_ms Average latency per variant")
            lines.append(f"# TYPE ablage_ab_testing_avg_latency_ms gauge")
            lines.append(f'ablage_ab_testing_avg_latency_ms{{{labels}}} {avg_latency}')

            errors = variant_data.get("errors", 0)
            lines.append(f"# HELP ablage_ab_testing_errors_total Total errors per variant")
            lines.append(f"# TYPE ablage_ab_testing_errors_total counter")
            lines.append(f'ablage_ab_testing_errors_total{{{labels}}} {errors}')

    except ImportError:
        lines.append("# A/B Testing module not available")
    except RuntimeError:
        lines.append("# A/B Testing router not initialized")
    except Exception:
        lines.append("# A/B Testing metrics temporarily unavailable")

    content = "\n".join(lines) + "\n"
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("", response_class=Response)
@router.get("/prometheus", response_class=Response)
async def prometheus_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics scrape endpoint.

    **REQUIRES ADMIN AUTHENTICATION**

    Returns metrics in Prometheus text format for scraping.

    Note: For automated Prometheus scraping, use /internal endpoint with
    METRICS_SCRAPE_TOKEN or network-level security (internal network only).

    Args:
        current_user: Authenticated admin user (required)
    """
    # Generate metrics from all registered collectors
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/search", response_class=Response)
async def search_metrics_prometheus(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics for search functionality.

    **REQUIRES ADMIN AUTHENTICATION**

    Returns search-specific metrics in Prometheus text format:
    - search_requests_total: Suchanfragen nach Typ und Status
    - search_duration_seconds: Suchlatenz
    - search_results_count: Ergebnismengen
    - search_zero_results_total: Suchen ohne Ergebnisse
    - search_cache_operations_total: Cache-Treffer/Miss
    - search_cache_invalidations_total: Cache-Invalidierungen
    - search_embedding_generation_seconds: Embedding-Generierung
    - search_similar_requests_total: Ähnliche-Dokumente-Anfragen
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
async def backup_metrics_prometheus(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics for backup functionality.

    **REQUIRES ADMIN AUTHENTICATION**

    Returns backup-specific metrics in Prometheus text format:
    - ablage_backup_last_success_timestamp: Letztes erfolgreiches Backup
    - ablage_backup_last_failure_timestamp: Letztes fehlgeschlagenes Backup
    - ablage_backup_success_total: Erfolgreiche Backups
    - ablage_backup_failure_total: Fehlgeschlagene Backups
    - ablage_backup_duration_seconds: Backup-Dauer
    - ablage_backup_size_bytes: Backup-Größe
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
async def backup_metrics_summary(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Backup metrics summary (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

    Returns backup-specific metrics for dashboards:
    - Speicherplatz-Nutzung und Verfügbarkeit
    - Anzahl Backup-Dateien nach Typ
    - Prometheus-Status

    Useful for custom dashboards and health monitoring.
    """
    metrics = get_backup_metrics()
    return metrics.get_summary()


# =============================================================================
# DATEV METRICS
# =============================================================================


@router.get("/datev", response_class=Response)
async def datev_metrics_prometheus(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics for DATEV functionality.

    **REQUIRES ADMIN AUTHENTICATION**

    Returns DATEV-specific metrics in Prometheus text format:
    - datev_exports_total: Anzahl Exports nach Status/Kontenrahmen
    - datev_export_duration_seconds: Export-Dauer als Histogram
    - datev_export_documents_total: Exportierte Dokumente
    - datev_config_count: Anzahl aktiver Konfigurationen
    - datev_vendor_mappings_count: Anzahl Vendor-Mappings
    - datev_export_errors_total: Export-Fehler nach Typ
    - datev_rate_limit_hits_total: Rate-Limit-Treffer

    Example Prometheus config:
    ```yaml
    scrape_configs:
      - job_name: 'ablage-datev'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/metrics/datev'
    ```
    """
    metrics = get_datev_metrics_service()
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type(),
    )


@router.get("/datev/summary")
async def datev_metrics_summary(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    DATEV metrics summary (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

    Returns DATEV-specific metrics for dashboards:
    - Verfügbare Metriken-Typen
    - Prometheus-Endpoint

    Nuetzlich für:
    - DATEV-Monitoring Dashboards
    - Export-Tracking
    - Performance-Analyse
    """
    metrics = get_datev_metrics_service()
    return metrics.get_summary()


# =============================================================================
# GPU METRICS
# =============================================================================


@router.get("/gpu", response_class=Response)
async def gpu_metrics_prometheus(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics for GPU functionality.

    **REQUIRES ADMIN AUTHENTICATION**

    Returns GPU-specific metrics in Prometheus text format:
    - ablage_gpu_memory_used_bytes: VRAM-Nutzung
    - ablage_gpu_memory_total_bytes: VRAM gesamt
    - ablage_gpu_memory_percent: VRAM-Nutzung in Prozent
    - ablage_gpu_available: GPU-Verfügbarkeit
    - ablage_ocr_requests_total: OCR-Anfragen nach Backend/Status
    - ablage_ocr_processing_duration_seconds: OCR-Verarbeitungszeit
    - ablage_ocr_batch_size: Batch-Größen
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
async def gpu_metrics_summary(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    GPU metrics summary (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

    Returns GPU-specific metrics for dashboards:
    - GPU-Speicher-Status
    - Verfügbarkeit
    - Letzte Aktualisierung

    Nuetzlich für:
    - GPU-Monitoring Dashboards
    - Kapazitaetsplanung
    - Performance-Analyse
    """
    metrics = get_gpu_metrics_service()
    return metrics.get_summary()


@router.get("/gpu/detailed")
async def gpu_metrics_detailed(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Detaillierte GPU-Metriken (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

    Returns comprehensive GPU metrics:
    - Hardware-Informationen
    - Speicher-Status
    - OCR-Statistiken
    - Cache-Performance
    - Model-Status

    **Hinweis**: Dieser Endpoint sammelt Metriken aus mehreren Quellen
    und kann bei hoher Last etwas länger dauern.
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
        logger.warning("gpu_metrics_cache_stats_failed", **safe_error_log(e))
        cache_stats = {"error": safe_error_detail(e, "Vorgang")}

    # Get GPU manager stats
    try:
        from app.gpu_manager import get_gpu_manager
        gpu_manager = get_gpu_manager()
        manager_stats = gpu_manager.get_detailed_status()
    except Exception as e:
        logger.warning("gpu_metrics_manager_stats_failed", **safe_error_log(e))
        manager_stats = {"error": safe_error_detail(e, "Vorgang")}

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
async def business_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Custom business metrics (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

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
async def business_metrics_prometheus(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Prometheus metrics for OCR and document processing.

    **REQUIRES ADMIN AUTHENTICATION**

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
    - ablage_document_size_bytes: Dokumentengröße
    - ablage_document_page_count: Seitenanzahl
    - ablage_document_status_transitions_total: Status-Übergaenge

    **Backpressure Metrics:**
    - ablage_backpressure_status: Aktueller Status
    - ablage_backpressure_queue_length_total: Queue-Länge
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
async def business_metrics_summary(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Business metrics summary (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

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
        "hinweis": "Nutze /metrics/business/prometheus für Prometheus-Format"
    }


@router.get("/health")
async def metrics_health(
    current_user: User = Depends(get_current_active_user),  # W.2 SECURITY FIX: Auth required
):
    """
    Health check for metrics system.

    **REQUIRES AUTHENTICATION**

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
async def ocr_cache_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    OCR Cache Statistics (JSON format).

    **REQUIRES ADMIN AUTHENTICATION**

    Returns cache-specific metrics:
    - **enabled**: Ob Caching aktiviert ist
    - **redis_available**: Redis-Verbindungsstatus
    - **hits**: Cache-Treffer
    - **misses**: Cache-Fehlschlaege
    - **total_requests**: Gesamtzahl der Anfragen
    - **hit_rate_percent**: Trefferquote in Prozent
    - **default_ttl_seconds**: Standard-Cache-Lebenszeit

    Nuetzlich für:
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
    OCR Cache Statistiken zurücksetzen.

    **REQUIRES ADMIN AUTHENTICATION**

    Setzt nur die Statistik-Zaehler zurück (hits/misses),
    nicht die gecacheten Ergebnisse selbst.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    from app.services.ocr_cache_service import get_ocr_cache_service

    # SECURITY FIX 27-10: PII Masking - Admin-Email nicht vollständig loggen!
    logger.warning(
        "ocr_cache_stats_reset_initiated",
        admin_user_id=str(current_user.id)[:8] + "...",
        admin_email=_mask_admin_email_for_log(current_user.email)
    )

    service = get_ocr_cache_service()
    success = await service.clear_stats()

    return {
        "status": "erfolg" if success else "fehlgeschlagen",
        "nachricht": "OCR-Cache-Statistiken wurden zurückgesetzt" if success else "Zurücksetzen fehlgeschlagen",
        "durchgeführt_von": str(current_user.id)
    }


@router.get("/cache-hit-rate")
async def get_cache_hit_rate_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Aggregierte Cache Hit-Rate Metriken.

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt Cache-Effizienz über alle Cache-Schichten:

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
        logger.warning("ocr_cache_stats_error", **safe_error_log(e))
        result["ocr_cache"]["error"] = safe_error_detail(e, "Vorgang")

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
        logger.warning("prometheus_metrics_error", **safe_error_log(e))
        result["prometheus_metrics"]["error"] = safe_error_detail(e, "Vorgang")

    # Generate recommendations
    recommendations = []

    # Check OCR cache hit rate
    ocr_overall = result.get("ocr_cache", {}).get("overall", {})
    if ocr_overall.get("combined_hit_rate_percent", 100) < 30:
        recommendations.append({
            "type": "ocr_cache",
            "severity": "warning",
            "message": "OCR Cache Hit-Rate unter 30% - prüfe Cache-TTL und Backend-Auswahl",
        })

    # Check API cache hit rate
    if result.get("api_cache", {}).get("hit_rate_percent", 100) < 50:
        recommendations.append({
            "type": "api_cache",
            "severity": "info",
            "message": "API Cache Hit-Rate unter 50% - prüfe Cache-Konfiguration",
        })

    result["recommendations"] = recommendations

    return result


@router.get("/database")
async def get_database_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Database Performance Metriken.

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt Datenbank-Performance-Statistiken:

    **Query Performance:**
    - Durchschnittliche Query-Dauer
    - Slow Query Zaehler
    - Queries pro Operation

    **Connection Pool:**
    - Pool-Größe
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
        logger.warning("db_pool_stats_error", **safe_error_log(e))
        result["connection_pool"]["error"] = safe_error_detail(e, "Vorgang")

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
        logger.warning("db_prometheus_metrics_error", **safe_error_log(e))
        result["query_stats"]["error"] = safe_error_detail(e, "Vorgang")

    # Generate recommendations
    recommendations = []

    # Check pool utilization
    pool_util = result.get("connection_pool", {}).get("utilization_percent", 0)
    if pool_util > 80:
        recommendations.append({
            "type": "connection_pool",
            "severity": "warning",
            "message": f"Connection Pool Auslastung bei {pool_util}% - erhöhe Pool-Größe",
        })

    # Check slow queries
    slow_total = result.get("slow_queries", {}).get("total", 0)
    if slow_total > 100:
        recommendations.append({
            "type": "slow_queries",
            "severity": "warning",
            "message": f"{slow_total} langsame Queries (>100ms) - prüfe Indizes und Queries",
        })

    # Check error rate
    error_rate = result.get("query_stats", {}).get("error_rate_percent", 0)
    if error_rate > 1:
        recommendations.append({
            "type": "query_errors",
            "severity": "critical",
            "message": f"Datenbank-Fehlerrate bei {error_rate}% - prüfe Verbindung und Logs",
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
async def get_slo_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Service Level Objectives (SLO) Status.

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt den aktuellen Status der definierten SLOs:

    **Verfügbarkeit:**
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

    Nuetzlich für:
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
            "name": "Verfügbarkeit",
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
            logger.warning("slo_gpu_metrics_unavailable", **safe_error_log(e))
            sli_values["gpu_vram_usage"] = None

        # Latenz-Perzentile (aus Redis Histogramm wenn verfügbar)
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

        # OCR-Verarbeitungszeiten (aus Redis wenn verfügbar)
        try:
            ocr_under_5s = await redis.get("metrics:ocr:under_5s_rate")
            ocr_under_30s = await redis.get("metrics:ocr:under_30s_rate")
            sli_values["ocr_processing_5s"] = float(ocr_under_5s) if ocr_under_5s else None
            sli_values["ocr_processing_30s"] = float(ocr_under_30s) if ocr_under_30s else None
        except Exception:
            sli_values["ocr_processing_5s"] = None
            sli_values["ocr_processing_30s"] = None

        # Umlaut-Genauigkeit (aus Redis wenn verfügbar)
        try:
            umlaut_acc = await redis.get("metrics:ocr:umlaut_accuracy_avg")
            sli_values["umlaut_accuracy"] = float(umlaut_acc) if umlaut_acc else None
        except Exception:
            sli_values["umlaut_accuracy"] = None

    except Exception as e:
        logger.error("slo_metrics_collection_error", **safe_error_log(e))

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
    slo_key: Optional[str] = None,
    current_user: User = Depends(get_current_superuser)  # EE.3 SECURITY FIX: Admin only
):
    """
    SLO-Verlauf über Zeit.

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt historische SLO-Daten für Trend-Analyse und Reporting.

    **Parameter:**
    - days: Anzahl der Tage (1-30)
    - slo_key: Spezifisches SLO (optional, sonst alle)

    **Rückgabe:**
    - Tägliche SLO-Werte
    - Trend-Richtung
    - Durchschnittswerte

    Nuetzlich für:
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
                detail=f"Unbekanntes SLO: {slo_key}. Verfügbar: {tracked_slos}"
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
async def get_ocr_quality_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    OCR-Qualitaetsmetriken (aggregiert).

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt aggregierte Qualitaetsmetriken über alle OCR-Verarbeitungen:

    **Character Error Rate (CER):**
    - Durchschnitt, Min, Max, Verteilung

    **Word Error Rate (WER):**
    - Durchschnitt, Min, Max, Verteilung

    **Umlaut-Genauigkeit:**
    - Durchschnitt pro Backend
    - Häufigste Fehler

    **Backend-Vergleich:**
    - Qualitaet nach OCR-Backend
    - Verarbeitungszeiten nach Backend

    Nuetzlich für:
    - Backend-Auswahl-Optimierung
    - Qualitaetsüberwachung
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
        logger.error("ocr_quality_metrics_error", **safe_error_log(e))
        quality_metrics["error"] = safe_error_detail(e, "Vorgang")

    return quality_metrics


# =============================================================================
# WEBHOOK / CIRCUIT BREAKER METRIKEN
# =============================================================================


@router.get("/webhooks")
async def get_webhook_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
):
    """
    Webhook und Circuit Breaker Metriken.

    **REQUIRES ADMIN AUTHENTICATION**

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
        logger.warning("circuit_breaker_stats_error", **safe_error_log(e))
        result["circuit_breaker"]["error"] = safe_error_detail(e, "Vorgang")

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
        logger.warning("webhook_prometheus_metrics_error", **safe_error_log(e))
        result["delivery_stats"]["error"] = safe_error_detail(e, "Vorgang")

    # Generate recommendations
    recommendations = []

    # Check for open circuits
    open_count = result.get("circuit_breaker", {}).get("by_state", {}).get("open", 0)
    half_open_count = result.get("circuit_breaker", {}).get("by_state", {}).get("half_open", 0)

    if open_count > 0:
        recommendations.append({
            "type": "circuit_breaker",
            "severity": "warning",
            "message": f"{open_count} Circuit Breaker offen - prüfe Webhook-Endpunkte",
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
            "message": f"Webhook-Erfolgsrate nur {success_rate}% - prüfe Endpunkt-Verfügbarkeit",
        })

    result["recommendations"] = recommendations

    return result


@router.post("/webhooks/circuit-breaker/reset")
async def reset_circuit_breaker(
    url: str | None = None,
    current_user: User = Depends(get_current_superuser)
):
    """
    Circuit Breaker zurücksetzen.

    **REQUIRES ADMIN AUTHENTICATION**

    Setzt Circuit Breaker zurück:
    - Mit URL-Parameter: Nur den Circuit Breaker für diese URL zurücksetzen
    - Ohne URL-Parameter: Alle Circuit Breaker zurücksetzen

    Args:
        url: Optional - Spezifische URL zum Zurücksetzen
        current_user: Authentifizierter Admin-User

    Returns:
        Erfolgs-Status mit Anzahl zurückgesetzter Circuits
    """
    import structlog
    logger = structlog.get_logger(__name__)

    from app.services.webhook_dispatcher import get_webhook_circuit_breaker

    circuit_breaker = get_webhook_circuit_breaker()

    # SECURITY FIX 27-10: PII Masking - Admin-Email nicht vollständig loggen!
    logger.warning(
        "circuit_breaker_reset_initiated",
        admin_user_id=str(current_user.id)[:8] + "...",
        admin_email=_mask_admin_email_for_log(current_user.email),
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
        "nachricht": f"Circuit Breaker zurückgesetzt",
        "circuits_reset": reset_count,
        "target": url[:50] if url else "alle",
        "durchgeführt_von": str(current_user.id),
    }


# =============================================================================
# GRAFANA DASHBOARD LINKS
# =============================================================================


@router.get("/dashboards")
async def get_dashboard_links(
    current_user: User = Depends(get_current_active_user),  # W.2 SECURITY FIX: Auth required
):
    """
    Grafana Dashboard Links.

    **REQUIRES AUTHENTICATION**

    Gibt URLs zu allen verfügbaren Grafana-Dashboards zurück.

    **Verfügbare Dashboards:**
    - **System Overview**: Allgemeine Systemmetriken, Container-Health
    - **OCR Pipeline**: OCR-Verarbeitungsmetriken, Backend-Vergleich
    - **GPU Profiling**: VRAM-Nutzung, Batch-Größen, OOM-Events
    - **ML Routing**: Backend-Auswahl, Gewichtungen, A/B Testing
    - **Backup Monitoring**: Backup-Status, Speicherplatz, Sync-Status

    Returns:
        Dictionary mit Dashboard-URLs und Verfügbarkeitsstatus
    """
    from app.core.config import settings

    if not settings.GRAFANA_ENABLED:
        return {
            "enabled": False,
            "message": "Grafana-Integration ist deaktiviert",
            "dashboards": {}
        }

    base_url = settings.GRAFANA_URL.rstrip("/")

    dashboards = {
        "system_overview": {
            "name": "System Overview",
            "url": f"{base_url}/d/ablage-system-overview",
            "description": "Allgemeine Systemmetriken, Container-Health, Resource-Nutzung",
            "icon": "Activity"
        },
        "ocr_pipeline": {
            "name": "OCR Pipeline",
            "url": f"{base_url}/d/ablage-ocr-pipeline",
            "description": "OCR-Verarbeitungsmetriken, CER/WER, Backend-Vergleich",
            "icon": "FileText"
        },
        "gpu_profiling": {
            "name": "GPU Profiling",
            "url": f"{base_url}/d/ablage-gpu-profiling",
            "description": "VRAM-Nutzung, Batch-Größen, OOM-Events, Model-Loading",
            "icon": "Cpu"
        },
        "ml_routing": {
            "name": "ML Routing",
            "url": f"{base_url}/d/ablage-ml-routing",
            "description": "Backend-Auswahl, Gelernte Gewichtungen, A/B Testing",
            "icon": "GitBranch"
        },
        "backup_monitoring": {
            "name": "Backup Monitoring",
            "url": f"{base_url}/d/ablage-backup-monitoring",
            "description": "Backup-Status, Speicherplatz, Remote-Sync",
            "icon": "Database"
        }
    }

    return {
        "enabled": True,
        "grafana_base": base_url,
        "dashboards": dashboards
    }


# =============================================================================
# A/B TESTING METRIKEN (pgvector vs Qdrant)
# =============================================================================


@router.get("/ab-testing")
async def get_ab_testing_metrics(
    current_user: User = Depends(get_current_superuser),  # W.2 SECURITY FIX: Admin required
) -> JSONDict:
    """
    A/B Testing Status für Vector Search (pgvector vs Qdrant).

    **REQUIRES ADMIN AUTHENTICATION**

    Zeigt aktuellen Status und Metriken des A/B Tests:

    **Konfiguration:**
    - enabled: Ob A/B Testing aktiv ist
    - traffic_split: Prozentsatz für Treatment (Qdrant)
    - control_backend: Kontroll-Backend (pgvector)
    - treatment_backend: Treatment-Backend (qdrant)

    **Metriken pro Variante:**
    - total_requests: Gesamtanzahl Anfragen
    - avg_latency_ms: Durchschnittliche Latenz
    - avg_results: Durchschnittliche Ergebnisanzahl
    - avg_score: Durchschnittlicher Relevanz-Score
    - errors: Fehleranzahl
    - error_rate: Fehlerrate

    **Qdrant Status:**
    - points_count: Anzahl Vektoren in Qdrant
    - collection_status: Collection-Status

    Nuetzlich für:
    - Performance-Vergleich pgvector vs Qdrant
    - Entscheidung für Migration
    - Monitoring der Rollout-Phase
    """
    from app.services.rag.ab_testing_router import get_ab_testing_router
    from app.core.config import settings

    logger = structlog.get_logger(__name__)

    result = {
        "zeitstempel": datetime.now(timezone.utc).isoformat(),
        "konfiguration": {},
        "metriken": {},
        "qdrant_status": {},
        "empfehlungen": [],
    }

    # Get A/B Testing Router Status
    try:
        router = get_ab_testing_router()
        status = router.get_status()

        result["konfiguration"] = {
            "aktiviert": status["enabled"],
            "traffic_split_prozent": status["traffic_split"],
            "kontrolle": status["control"],
            "behandlung": status["treatment"],
        }

        result["metriken"] = status["metrics"]

    except ImportError as ie:
        logger.error("ab_testing_router_import_error", error=str(ie))
        result["konfiguration"]["fehler"] = "A/B Testing Modul nicht verfügbar"
    except RuntimeError as re:
        logger.warning("ab_testing_router_runtime_error", error=str(re))
        result["konfiguration"]["fehler"] = f"Router-Initialisierung fehlgeschlagen: {re}"
    except Exception as e:
        logger.error("ab_testing_router_error", **safe_error_log(e))
        result["konfiguration"]["fehler"] = "Unerwarteter Fehler beim Abrufen des A/B Testing Status"

    # Get Qdrant Status
    try:
        # URL-Validierung
        qdrant_host = settings.QDRANT_HOST
        qdrant_port = settings.QDRANT_HTTP_PORT

        if not qdrant_host:
            raise ValueError("QDRANT_HOST nicht konfiguriert")
        if not isinstance(qdrant_port, int) or not (0 < qdrant_port <= 65535):
            raise ValueError(f"Ungültiger QDRANT_HTTP_PORT: {qdrant_port}")

        # TLS-Unterstützung prüfen (falls konfiguriert)
        protocol = "https" if getattr(settings, 'QDRANT_USE_TLS', False) else "http"
        qdrant_url = f"{protocol}://{qdrant_host}:{qdrant_port}"
        collection_name = settings.QDRANT_COLLECTION_CHUNKS

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Collection Info
            resp = await client.get(f"{qdrant_url}/collections/{collection_name}")
            if resp.status_code == 200:
                try:
                    info = resp.json()
                except ValueError as json_err:
                    raise ValueError(f"Ungültige JSON-Antwort von Qdrant: {json_err}")

                collection_info = info.get("result", {})
                result["qdrant_status"] = {
                    "verfügbar": True,
                    "collection": collection_name,
                    "punkte_anzahl": collection_info.get("points_count", 0),
                    "vektoren_anzahl": collection_info.get("vectors_count", 0),
                    "status": collection_info.get("status", "unbekannt"),
                    "konfiguration": {
                        "vektor_größe": collection_info.get("config", {}).get("params", {}).get("vectors", {}).get("size"),
                        "distanz": collection_info.get("config", {}).get("params", {}).get("vectors", {}).get("distance"),
                    },
                    "tls_aktiviert": protocol == "https"
                }
            elif resp.status_code == 404:
                result["qdrant_status"] = {
                    "verfügbar": True,
                    "fehler": f"Collection '{collection_name}' existiert nicht. Führe Migration aus."
                }
            else:
                result["qdrant_status"] = {
                    "verfügbar": False,
                    "fehler": f"Qdrant-Fehler: HTTP {resp.status_code}"
                }

    except httpx.TimeoutException:
        logger.warning("qdrant_timeout", timeout_seconds=5.0)
        result["qdrant_status"] = {
            "verfügbar": False,
            "fehler": "Qdrant nicht erreichbar (Timeout nach 5 Sekunden)"
        }
    except httpx.ConnectError:
        logger.warning("qdrant_connection_error", host=settings.QDRANT_HOST)
        result["qdrant_status"] = {
            "verfügbar": False,
            "fehler": f"Verbindung zu Qdrant fehlgeschlagen ({settings.QDRANT_HOST}:{settings.QDRANT_HTTP_PORT})"
        }
    except ValueError as ve:
        logger.warning("qdrant_config_error", error=str(ve))
        result["qdrant_status"] = {
            "verfügbar": False,
            "fehler": str(ve)
        }
    except Exception as e:
        logger.error("qdrant_status_error", **safe_error_log(e), error_type=type(e).__name__)
        result["qdrant_status"] = {
            "verfügbar": False,
            "fehler": "Unerwarteter Fehler beim Qdrant-Statusabruf"
        }

    # Empfehlungen generieren
    empfehlungen = []

    # Prüfen ob A/B Testing aktiviert aber noch keine Anfragen
    control_requests = result.get("metriken", {}).get("control", {}).get("total_requests", 0)
    treatment_requests = result.get("metriken", {}).get("treatment", {}).get("total_requests", 0)

    if result.get("konfiguration", {}).get("aktiviert") and control_requests == 0 and treatment_requests == 0:
        empfehlungen.append({
            "typ": "info",
            "nachricht": "A/B Testing aktiviert, aber noch keine Anfragen. Führe RAG-Suchen durch um Daten zu sammeln."
        })

    # Latenz-Vergleich
    if control_requests > 10 and treatment_requests > 10:
        control_latency = result.get("metriken", {}).get("control", {}).get("avg_latency_ms", 0)
        treatment_latency = result.get("metriken", {}).get("treatment", {}).get("avg_latency_ms", 0)

        if treatment_latency > 0 and control_latency > 0:
            if treatment_latency < control_latency * 0.8:
                empfehlungen.append({
                    "typ": "erfolg",
                    "nachricht": f"Qdrant ist {((control_latency - treatment_latency) / control_latency * 100):.1f}% schneller als pgvector. Erwäge Traffic-Split zu erhöhen."
                })
            elif treatment_latency > control_latency * 1.2:
                empfehlungen.append({
                    "typ": "warnung",
                    "nachricht": f"Qdrant ist {((treatment_latency - control_latency) / control_latency * 100):.1f}% langsamer als pgvector. Prüfe Qdrant-Konfiguration."
                })

    # Fehlerraten prüfen
    control_error_rate = result.get("metriken", {}).get("control", {}).get("error_rate", 0)
    treatment_error_rate = result.get("metriken", {}).get("treatment", {}).get("error_rate", 0)

    if treatment_error_rate > 0.05:
        empfehlungen.append({
            "typ": "warnung",
            "nachricht": f"Qdrant Fehlerrate bei {treatment_error_rate * 100:.1f}%. Prüfe Logs und Verbindung."
        })

    # Qdrant Sync-Status prüfen
    qdrant_points = result.get("qdrant_status", {}).get("punkte_anzahl", 0)
    if qdrant_points == 0 and result.get("konfiguration", {}).get("aktiviert"):
        empfehlungen.append({
            "typ": "kritisch",
            "nachricht": "Qdrant Collection ist leer! Führe Migration aus: migrate_embeddings_to_qdrant"
        })

    result["empfehlungen"] = empfehlungen

    return result


@router.post("/ab-testing/traffic-split")
async def update_ab_testing_traffic_split(
    new_split: int,
    current_user: User = Depends(get_current_superuser)
) -> JSONDict:
    """
    A/B Testing Traffic-Split ändern.

    **REQUIRES ADMIN AUTHENTICATION**

    Ändert den Prozentsatz des Traffics, der an Qdrant (Treatment) geht.

    **Parameter:**
    - new_split: Neuer Prozentsatz (0-100)
      - 0 = Alles pgvector
      - 10 = 10% Qdrant, 90% pgvector
      - 50 = 50/50 Split
      - 100 = Alles Qdrant

    **Empfohlene Rollout-Strategie:**
    1. Start: 10% (validieren)
    2. Phase 2: 25% (mehr Daten sammeln)
    3. Phase 3: 50% (echte A/B Vergleichbarkeit)
    4. Phase 4: 90% (fast vollständig)
    5. Final: 100% (Migration abgeschlossen)

    Returns:
        Bestätigung mit altem und neuem Split-Wert
    """
    logger = structlog.get_logger(__name__)

    if new_split < 0 or new_split > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Traffic-Split muss zwischen 0 und 100 liegen"
        )

    from app.services.rag.ab_testing_router import get_ab_testing_router

    router = get_ab_testing_router()
    old_split = router._traffic_split

    logger.warning(
        "ab_testing_traffic_split_change",
        admin_user_id=str(current_user.id),
        admin_email=current_user.email,
        old_split=old_split,
        new_split=new_split
    )

    router.update_traffic_split(new_split)

    return {
        "status": "erfolg",
        "nachricht": f"Traffic-Split von {old_split}% auf {new_split}% geändert",
        "alter_split": old_split,
        "neuer_split": new_split,
        "durchgeführt_von": str(current_user.id)
    }


@router.post("/ab-testing/reset-metrics")
async def reset_ab_testing_metrics(
    current_user: User = Depends(get_current_superuser)
) -> JSONDict:
    """
    A/B Testing Metriken zurücksetzen.

    **REQUIRES ADMIN AUTHENTICATION**

    Setzt alle gesammelten A/B Testing Metriken auf 0 zurück.
    Nuetzlich nach Konfigurationsänderungen oder für neue Testphasen.

    Returns:
        Bestätigung des Resets
    """
    from app.services.rag.ab_testing_router import get_ab_testing_router


    logger = structlog.get_logger(__name__)

    logger.warning(
        "ab_testing_metrics_reset",
        admin_user_id=str(current_user.id),
        admin_email=current_user.email
    )

    router = get_ab_testing_router()
    router.reset_metrics()

    return {
        "status": "erfolg",
        "nachricht": "A/B Testing Metriken wurden zurückgesetzt",
        "durchgeführt_von": str(current_user.id)
    }
