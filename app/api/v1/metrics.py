"""
Metrics API Endpoints.

Provides Prometheus metrics scraping and custom business metrics.
"""

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.redis_state import get_redis

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
async def reset_metrics():
    """
    Reset all metrics counters (development/testing only).

    WARNING: This will reset all business metrics!

    TODO: Add authentication/authorization before production deployment!
          This endpoint should require admin role or be disabled in production.

    SECURITY RISK: Currently NO AUTHENTICATION - anyone can reset metrics!
    """
    # TODO: Replace with proper auth check
    # if not await verify_admin_role(current_user):
    #     raise HTTPException(403, "Admin role required")

    import os
    if os.getenv("ENVIRONMENT", "development") == "production":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="Metrics reset disabled in production. Enable authentication first."
        )

    redis = await get_redis()

    # Reset counters
    await redis.reset_counter("ocr.documents_processed")
    await redis.reset_counter("ocr.documents_failed")
    await redis.reset_counter("gpu.oom_errors")

    return {
        "status": "success",
        "message": "All metrics counters reset to 0",
    }
