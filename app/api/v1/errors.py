# -*- coding: utf-8 -*-
"""
Error Tracking API Endpoints.

Stellt Fehler-Statistiken und -Analytics bereit.
Nur für Admins und Monitoring-Systeme zugaenglich.

Feinpoliert und durchdacht - Enterprise Error Analytics.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.types import JSONDict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.error_tracking_service import (
    ErrorCategory,
    ErrorSeverity,
    get_error_tracking_service,
)

router = APIRouter(prefix="/errors", tags=["errors"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class ErrorStatsResponse(BaseModel):
    """Fehler-Statistiken Response."""
    total_count: int = Field(..., description="Gesamtzahl Fehler")
    last_hour_count: int = Field(..., description="Fehler letzte Stunde")
    last_24h_count: int = Field(..., description="Fehler letzte 24 Stunden")
    rate_per_minute: float = Field(..., description="Fehler pro Minute")
    last_error_time: Optional[str] = Field(None, description="Letzter Fehler")
    error_types: Dict[str, int] = Field(default_factory=dict, description="Fehler nach Typ")
    severity_counts: Dict[str, int] = Field(default_factory=dict, description="Fehler nach Schweregrad")
    alert_active: bool = Field(False, description="Alert aktiv")


class AllErrorStatsResponse(BaseModel):
    """Alle Fehler-Statistiken Response."""
    zeitstempel: str = Field(..., description="Zeitstempel der Abfrage")
    kategorien: Dict[str, ErrorStatsResponse] = Field(..., description="Statistiken pro Kategorie")
    zusammenfassung: JSONDict = Field(..., description="Zusammenfassung")


class RecentErrorResponse(BaseModel):
    """Einzelner Fehler Response."""
    timestamp: str = Field(..., description="Zeitstempel")
    category: str = Field(..., description="Kategorie")
    error_type: str = Field(..., description="Fehler-Typ")
    severity: str = Field(..., description="Schweregrad")
    message: str = Field(..., description="Nachricht")
    path: Optional[str] = Field(None, description="Request-Pfad")
    request_id: Optional[str] = Field(None, description="Request-ID")


class ErrorTrendsResponse(BaseModel):
    """Fehler-Trends Response."""
    category: str = Field(..., description="Kategorie")
    period_hours: int = Field(..., description="Zeitraum in Stunden")
    total_errors: int = Field(..., description="Gesamtzahl Fehler")
    hourly_counts: Dict[str, int] = Field(..., description="Fehler pro Stunde")
    average_per_hour: float = Field(..., description="Durchschnitt pro Stunde")


class TopErrorResponse(BaseModel):
    """Häufigster Fehler Response."""
    error_type: str = Field(..., description="Fehler-Typ")
    count: int = Field(..., description="Anzahl")
    category: str = Field(..., description="Kategorie")


class AlertConfigRequest(BaseModel):
    """Alert-Konfiguration Request."""
    threshold_per_minute: float = Field(10.0, ge=0.1, description="Schwellenwert pro Minute")
    cooldown_minutes: int = Field(5, ge=1, le=60, description="Cooldown in Minuten")


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "/stats",
    response_model=AllErrorStatsResponse,
    summary="Alle Fehler-Statistiken abrufen",
)
async def get_all_error_stats(
    current_user: User = Depends(get_current_superuser),
) -> AllErrorStatsResponse:
    """
    Hole alle Fehler-Statistiken über alle Kategorien.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Returns:
        Statistiken für alle Fehler-Kategorien mit Zusammenfassung.
    """
    service = get_error_tracking_service()
    stats = service.get_stats()

    # Berechne Zusammenfassung
    total_all = sum(s.get("total_count", 0) for s in stats.values())
    hour_all = sum(s.get("last_hour_count", 0) for s in stats.values())
    active_alerts = sum(1 for s in stats.values() if s.get("alert_active", False))

    return AllErrorStatsResponse(
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        kategorien={k: ErrorStatsResponse(**v) for k, v in stats.items()},
        zusammenfassung={
            "gesamt_fehler": total_all,
            "fehler_letzte_stunde": hour_all,
            "aktive_alerts": active_alerts,
            "kategorien_count": len(stats),
        },
    )


@router.get(
    "/stats/{category}",
    response_model=ErrorStatsResponse,
    summary="Fehler-Statistiken für Kategorie",
)
async def get_category_error_stats(
    category: ErrorCategory,
    current_user: User = Depends(get_current_superuser),
) -> ErrorStatsResponse:
    """
    Hole Fehler-Statistiken für eine spezifische Kategorie.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Fehler-Kategorie (ocr, gpu, database, auth, etc.)

    Returns:
        Statistiken für die angegebene Kategorie.
    """
    service = get_error_tracking_service()
    stats = service.get_stats(category)

    return ErrorStatsResponse(**stats)


@router.get(
    "/recent",
    response_model=List[RecentErrorResponse],
    summary="Letzte Fehler abrufen",
)
async def get_recent_errors(
    category: Optional[ErrorCategory] = Query(None, description="Filter nach Kategorie"),
    severity: Optional[ErrorSeverity] = Query(None, description="Filter nach Schweregrad"),
    limit: int = Query(50, ge=1, le=500, description="Maximale Anzahl"),
    current_user: User = Depends(get_current_superuser),
) -> List[RecentErrorResponse]:
    """
    Hole die letzten aufgetretenen Fehler.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Optional Filter nach Kategorie
        severity: Optional Filter nach Schweregrad
        limit: Maximale Anzahl (1-500)

    Returns:
        Liste der letzten Fehler, sortiert nach Zeit (neueste zuerst).
    """
    service = get_error_tracking_service()
    errors = service.get_recent_errors(
        category=category,
        severity=severity,
        limit=limit,
    )

    return [RecentErrorResponse(**e) for e in errors]


@router.get(
    "/trends/{category}",
    response_model=ErrorTrendsResponse,
    summary="Fehler-Trends abrufen",
)
async def get_error_trends(
    category: ErrorCategory,
    hours: int = Query(24, ge=1, le=168, description="Zeitraum in Stunden (max 7 Tage)"),
    current_user: User = Depends(get_current_superuser),
) -> ErrorTrendsResponse:
    """
    Hole Fehler-Trends über Zeit für eine Kategorie.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Fehler-Kategorie
        hours: Zeitraum in Stunden (1-168)

    Returns:
        Stuendliche Fehler-Counts und Durchschnittswerte.
    """
    service = get_error_tracking_service()
    trends = service.get_error_trends(category, hours)

    return ErrorTrendsResponse(**trends)


@router.get(
    "/top",
    response_model=List[TopErrorResponse],
    summary="Häufigste Fehler abrufen",
)
async def get_top_errors(
    category: Optional[ErrorCategory] = Query(None, description="Filter nach Kategorie"),
    limit: int = Query(10, ge=1, le=50, description="Anzahl"),
    current_user: User = Depends(get_current_superuser),
) -> List[TopErrorResponse]:
    """
    Hole die häufigsten Fehler-Typen.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Optional Filter nach Kategorie
        limit: Anzahl (1-50)

    Returns:
        Liste der häufigsten Fehler-Typen, sortiert nach Anzahl.
    """
    service = get_error_tracking_service()
    top_errors = service.get_top_errors(category, limit)

    return [TopErrorResponse(**e) for e in top_errors]


@router.post(
    "/alerts/{category}",
    summary="Alert konfigurieren",
    status_code=status.HTTP_200_OK,
)
async def configure_alert(
    category: ErrorCategory,
    config: AlertConfigRequest,
    current_user: User = Depends(get_current_superuser),
) -> JSONDict:
    """
    Konfiguriere Alert-Schwellenwert für eine Kategorie.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Fehler-Kategorie
        config: Alert-Konfiguration

    Returns:
        Bestätigungsmeldung.
    """
    service = get_error_tracking_service()
    service.configure_alert(
        category=category,
        threshold_per_minute=config.threshold_per_minute,
        cooldown_minutes=config.cooldown_minutes,
    )

    return {
        "status": "erfolg",
        "nachricht": f"Alert für {category.value} konfiguriert",
        "schwellenwert": config.threshold_per_minute,
        "cooldown_minuten": config.cooldown_minutes,
    }


@router.delete(
    "/alerts/{category}",
    summary="Alert löschen",
    status_code=status.HTTP_200_OK,
)
async def clear_alert(
    category: ErrorCategory,
    current_user: User = Depends(get_current_superuser),
) -> JSONDict:
    """
    Lösche aktiven Alert für eine Kategorie.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Args:
        category: Fehler-Kategorie

    Returns:
        Bestätigungsmeldung.
    """
    service = get_error_tracking_service()
    service.clear_alert(category)

    return {
        "status": "erfolg",
        "nachricht": f"Alert für {category.value} gelöscht",
    }


@router.post(
    "/reset",
    summary="Fehler-Statistiken zurücksetzen",
    status_code=status.HTTP_200_OK,
)
async def reset_error_stats(
    category: Optional[ErrorCategory] = Query(None, description="Kategorie (leer = alle)"),
    current_user: User = Depends(get_current_superuser),
) -> JSONDict:
    """
    Setze Fehler-Statistiken zurück.

    **ERFORDERT ADMIN-BERECHTIGUNG**

    **ACHTUNG**: Diese Aktion löscht alle Fehler-Daten im Buffer!

    Args:
        category: Optional spezifische Kategorie, sonst alle

    Returns:
        Bestätigungsmeldung.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    logger.warning(
        "error_stats_reset",
        admin_user_id=str(current_user.id),
        category=category.value if category else "all",
    )

    service = get_error_tracking_service()
    service.reset_stats(category)

    return {
        "status": "erfolg",
        "nachricht": f"Fehler-Statistiken zurückgesetzt für: {category.value if category else 'alle Kategorien'}",
        "durchgeführt_von": str(current_user.id),
    }


@router.post(
    "/cleanup",
    summary="Alte Fehler bereinigen",
    status_code=status.HTTP_200_OK,
)
async def cleanup_old_errors(
    current_user: User = Depends(get_current_superuser),
) -> JSONDict:
    """
    Bereinige alte Fehler aus dem Buffer (aelter als Retention-Zeit).

    **ERFORDERT ADMIN-BERECHTIGUNG**

    Returns:
        Anzahl der bereinigten Fehler.
    """
    service = get_error_tracking_service()
    removed_count = await service.cleanup_old_errors()

    return {
        "status": "erfolg",
        "nachricht": f"{removed_count} alte Fehler bereinigt",
        "bereinigt": removed_count,
    }


@router.get(
    "/prometheus",
    summary="Prometheus Metriken (Error-spezifisch)",
)
async def prometheus_error_metrics(
    current_user: User = Depends(get_current_superuser),  # X.2 SECURITY FIX: Admin required
) -> JSONDict:
    """
    Prometheus-kompatible Metriken für Error Tracking.

    **REQUIRES ADMIN AUTHENTICATION**

    Dieser Endpoint liefert eine Zusammenfassung der Error-Metriken.
    Für vollständige Prometheus-Scraping, nutze /api/v1/metrics.

    Args:
        current_user: Authenticated admin user (required)

    Returns:
        Error-Metriken Zusammenfassung.
    """
    service = get_error_tracking_service()
    stats = service.get_stats()

    # Berechne Metriken
    total_errors = sum(s.get("total_count", 0) for s in stats.values())
    total_rate = sum(s.get("rate_per_minute", 0) for s in stats.values())
    active_alerts = sum(1 for s in stats.values() if s.get("alert_active", False))

    return {
        "ablage_errors_total": total_errors,
        "ablage_error_rate_total": round(total_rate, 2),
        "ablage_active_alerts": active_alerts,
        "kategorien": {
            k: {
                "total": v.get("total_count", 0),
                "rate": v.get("rate_per_minute", 0),
                "alert": v.get("alert_active", False),
            }
            for k, v in stats.items()
        },
    }
