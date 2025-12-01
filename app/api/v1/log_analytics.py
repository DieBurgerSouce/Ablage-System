# -*- coding: utf-8 -*-
"""
Log Analytics API Endpoints.

Bietet Admin-Endpoints fuer:
- Log-Metriken und Statistiken
- Trend-Analyse
- Health-Reports
- Dashboard-Daten

Alle Endpoints erfordern Superuser-Authentifizierung.
"""

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.log_analytics_service import (
    LogLevel,
    get_log_analytics_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/log-analytics", tags=["log-analytics"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class LogMetricsResponse(BaseModel):
    """Response fuer Log-Metriken."""

    total_entries: int
    by_level: Dict[str, int]
    by_source: Dict[str, int]
    error_rate_percent: float
    warning_rate_percent: float
    entries_per_minute: float


class TrendResponse(BaseModel):
    """Response fuer Trend-Analyse."""

    metric_name: str
    direction: str
    current_value: float
    previous_value: float
    change_percent: float
    is_anomaly: bool
    anomaly_reason: Optional[str] = None


class AlertResponse(BaseModel):
    """Response fuer Alert."""

    severity: str
    type: str
    message: str


class HealthReportResponse(BaseModel):
    """Response fuer Health Report."""

    timestamp: str
    period_minutes: int
    metrics: LogMetricsResponse
    trends: List[TrendResponse]
    alerts: List[Dict[str, Any]]
    recommendations: List[str]


class TopErrorResponse(BaseModel):
    """Response fuer Top Error."""

    message: str
    source: str
    level: str
    count: int
    last_occurrence: str


class SourceStatsResponse(BaseModel):
    """Response fuer Source-Statistiken."""

    source: str
    total: int
    error_count: int
    warning_count: int
    error_rate_percent: float


class DashboardDataResponse(BaseModel):
    """Response fuer Dashboard-Daten."""

    timestamp: str
    period_minutes: int
    summary: Dict[str, Any]
    by_level: Dict[str, int]
    trends: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    recommendations: List[str]
    top_errors: List[Dict[str, Any]]
    volume_timeline: List[Dict[str, Any]]
    source_stats: List[Dict[str, Any]]


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/metrics", response_model=LogMetricsResponse)
async def get_log_metrics(
    current_user: User = Depends(get_current_superuser),
    last_minutes: int = Query(60, ge=1, le=1440, description="Zeitfenster in Minuten"),
) -> LogMetricsResponse:
    """
    Gibt aktuelle Log-Metriken zurueck.

    Aggregiert Logs nach Level und Quelle fuer den angegebenen Zeitraum.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    metrics = service.get_metrics(last_minutes)

    return LogMetricsResponse(
        total_entries=metrics.total_entries,
        by_level=metrics.by_level,
        by_source=metrics.by_source,
        error_rate_percent=metrics.error_rate_percent,
        warning_rate_percent=metrics.warning_rate_percent,
        entries_per_minute=metrics.entries_per_minute,
    )


@router.get("/trends", response_model=List[TrendResponse])
async def get_log_trends(
    current_user: User = Depends(get_current_superuser),
) -> List[TrendResponse]:
    """
    Analysiert Trends in den Log-Metriken.

    Vergleicht aktuelle Periode mit vorheriger und erkennt Anomalien.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    trends = service.analyze_trends()

    return [
        TrendResponse(
            metric_name=t.metric_name,
            direction=t.direction.value,
            current_value=t.current_value,
            previous_value=t.previous_value,
            change_percent=t.change_percent,
            is_anomaly=t.is_anomaly,
            anomaly_reason=t.anomaly_reason,
        )
        for t in trends
    ]


@router.get("/health", response_model=HealthReportResponse)
async def get_log_health(
    current_user: User = Depends(get_current_superuser),
) -> HealthReportResponse:
    """
    Gibt vollstaendigen Log-Health-Report zurueck.

    Inkludiert Metriken, Trends, Alerts und Empfehlungen.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    report = service.get_health_report()

    return HealthReportResponse(
        timestamp=report.timestamp.isoformat(),
        period_minutes=report.period_minutes,
        metrics=LogMetricsResponse(
            total_entries=report.metrics.total_entries,
            by_level=report.metrics.by_level,
            by_source=report.metrics.by_source,
            error_rate_percent=report.metrics.error_rate_percent,
            warning_rate_percent=report.metrics.warning_rate_percent,
            entries_per_minute=report.metrics.entries_per_minute,
        ),
        trends=[
            TrendResponse(
                metric_name=t.metric_name,
                direction=t.direction.value,
                current_value=t.current_value,
                previous_value=t.previous_value,
                change_percent=t.change_percent,
                is_anomaly=t.is_anomaly,
                anomaly_reason=t.anomaly_reason,
            )
            for t in report.trends
        ],
        alerts=report.alerts,
        recommendations=report.recommendations,
    )


@router.get("/top-errors", response_model=List[TopErrorResponse])
async def get_top_errors(
    current_user: User = Depends(get_current_superuser),
    limit: int = Query(10, ge=1, le=50, description="Anzahl der Top-Errors"),
) -> List[TopErrorResponse]:
    """
    Gibt die haeufigsten Errors zurueck.

    Gruppiert nach Nachricht und zeigt Anzahl der Vorkommen.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    errors = service.get_top_errors(limit)

    return [
        TopErrorResponse(
            message=e["message"],
            source=e["source"],
            level=e["level"],
            count=e["count"],
            last_occurrence=e["last_occurrence"],
        )
        for e in errors
    ]


@router.get("/sources", response_model=List[SourceStatsResponse])
async def get_source_statistics(
    current_user: User = Depends(get_current_superuser),
) -> List[SourceStatsResponse]:
    """
    Gibt Statistiken nach Log-Quelle zurueck.

    Zeigt welche Services/Module die meisten Logs und Errors produzieren.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    stats = service.get_source_statistics()

    return [
        SourceStatsResponse(
            source=s["source"],
            total=s["total"],
            error_count=s["error_count"],
            warning_count=s["warning_count"],
            error_rate_percent=s["error_rate_percent"],
        )
        for s in stats
    ]


@router.get("/timeline")
async def get_volume_timeline(
    current_user: User = Depends(get_current_superuser),
    interval_minutes: int = Query(5, ge=1, le=60, description="Intervall in Minuten"),
    periods: int = Query(12, ge=2, le=48, description="Anzahl der Perioden"),
):
    """
    Gibt Log-Volumen ueber Zeit zurueck.

    Ideal fuer Zeitreihen-Charts in Dashboards.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    timeline = service.get_log_volume_by_time(interval_minutes, periods)

    return {
        "interval_minutes": interval_minutes,
        "periods": periods,
        "data": timeline,
    }


@router.get("/dashboard", response_model=DashboardDataResponse)
async def get_dashboard_data(
    current_user: User = Depends(get_current_superuser),
) -> DashboardDataResponse:
    """
    Gibt alle Dashboard-relevanten Daten in einem Request zurueck.

    Optimiert fuer Monitoring-Dashboards - alle Daten in einem Call.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    data = service.get_dashboard_data()

    logger.info(
        "log_analytics_dashboard_accessed",
        user_id=str(current_user.id),
    )

    return DashboardDataResponse(
        timestamp=data["timestamp"],
        period_minutes=data["period_minutes"],
        summary=data["summary"],
        by_level=data["by_level"],
        trends=data["trends"],
        alerts=data["alerts"],
        recommendations=data["recommendations"],
        top_errors=data["top_errors"],
        volume_timeline=data["volume_timeline"],
        source_stats=data["source_stats"],
    )


@router.post("/record")
async def record_log_entry(
    current_user: User = Depends(get_current_superuser),
    level: str = Query(..., description="Log-Level (debug, info, warning, error, critical)"),
    source: str = Query(..., description="Log-Quelle"),
    message: str = Query(..., description="Log-Nachricht"),
):
    """
    Zeichnet manuell einen Log-Eintrag auf.

    Nuetzlich fuer Tests und manuelle Log-Injektion.

    **Erfordert Superuser-Authentifizierung.**
    """
    # Validate level
    try:
        log_level = LogLevel(level.lower())
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Ungueltiger Log-Level. Erlaubt: {[l.value for l in LogLevel]}"
        )

    service = get_log_analytics_service()
    service.record_log(
        level=log_level,
        source=source,
        message=message,
        metadata={"recorded_by": str(current_user.id), "manual": True},
    )

    return {
        "success": True,
        "message": "Log-Eintrag aufgezeichnet",
        "level": level,
        "source": source,
    }


@router.post("/snapshot")
async def store_metrics_snapshot(
    current_user: User = Depends(get_current_superuser),
):
    """
    Speichert aktuellen Metriken-Snapshot fuer Trend-Analyse.

    Wird normalerweise automatisch aufgerufen, kann aber auch manuell getriggert werden.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    service.store_metrics_snapshot()

    return {
        "success": True,
        "message": "Metriken-Snapshot gespeichert",
    }


@router.get("/alerts")
async def get_active_alerts(
    current_user: User = Depends(get_current_superuser),
):
    """
    Gibt nur aktive Alerts zurueck.

    Fuer Alerting-Systeme und Benachrichtigungen.

    **Erfordert Superuser-Authentifizierung.**
    """
    service = get_log_analytics_service()
    report = service.get_health_report()

    return {
        "total_alerts": len(report.alerts),
        "critical_count": sum(1 for a in report.alerts if a.get("severity") == "critical"),
        "warning_count": sum(1 for a in report.alerts if a.get("severity") == "warning"),
        "alerts": report.alerts,
        "has_anomalies": any(a.get("type") == "anomaly" for a in report.alerts),
    }
