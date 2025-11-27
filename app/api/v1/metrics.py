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
