# -*- coding: utf-8 -*-
"""
Zugriffs-Analytik Dashboard API.

Admin-only Endpunkte fuer die Visualisierung von Dokumentenzugriffen,
Benutzeraktivitaeten und Anomalie-Erkennung.

Alle Endpunkte erfordern die Berechtigung "admin:audit:read".
Multi-Tenant-Isolation via company_id wird in jedem Endpunkt erzwungen.

SECURITY:
- Kein Logging von Dokument-Inhalten oder PII
- Alle Anfragen werden im Audit-Log protokolliert
- Rate-Limiting greift ueber die zentrale Middleware
"""

from __future__ import annotations

from typing import List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.rbac import require_permission
from app.db.models import User
from app.middleware.company_context import require_company
from app.services.access_analytics_service import (
    AccessAnalyticsService,
    AccessAnomaly,
    AccessOverview,
    DocumentAccessLog,
    EventTypeStat,
    HourlyStats,
    UserTimeline,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/access-analytics",
    tags=["Zugriffs-Analytik"],
)

# =============================================================================
# Prometheus Metriken
# =============================================================================

_REQUEST_COUNTER = Counter(
    "access_analytics_requests_total",
    "Gesamtanzahl der Zugriffs-Analytik API-Anfragen",
    ["endpoint", "status"],
)

_REQUEST_DURATION = Histogram(
    "access_analytics_request_duration_seconds",
    "Antwortzeit der Zugriffs-Analytik API-Endpunkte in Sekunden",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# =============================================================================
# GET /access-analytics/overview
# =============================================================================


@router.get(
    "/overview",
    response_model=AccessOverview,
    summary="Zugriffs-Uebersicht",
    description=(
        "Gibt eine Uebersicht der wichtigsten Zugriffs-Kennzahlen zurueck: "
        "Top-10 meistbesuchte Dokumente, aktivste Benutzer und "
        "fehlgeschlagene Anmeldeversuche pro Tag. Nur fuer Administratoren."
    ),
)
async def get_overview(
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Betrachtungszeitraum in Tagen (1-90, Standard: 7)",
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> AccessOverview:
    """Uebersicht der Zugriffs-Analytik fuer den aktuellen Mandanten.

    Gibt zurueck:
    - Top-10 meistbesuchte Dokumente
    - Top-10 aktivste Benutzer
    - Fehlgeschlagene Logins pro Tag

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_overview",
        admin_id=str(admin.id),
        company_id=str(company_id),
        days=days,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.get_overview(db=db, company_id=company_id, days=days)

        _REQUEST_COUNTER.labels(endpoint="overview", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="overview").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="overview", status="error").inc()
        logger.error(
            "access_analytics_overview_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analytik-Uebersicht konnte nicht geladen werden.",
        ) from exc


# =============================================================================
# GET /access-analytics/by-user/{user_id}
# =============================================================================


@router.get(
    "/by-user/{user_id}",
    response_model=UserTimeline,
    summary="Benutzer-Aktivitaetstimeline",
    description=(
        "Gibt die chronologische Timeline aller Aktionen eines bestimmten Benutzers "
        "zurueck. Paginiert, neueste Eintraege zuerst. Nur fuer Administratoren."
    ),
)
async def get_user_timeline(
    user_id: UUID,
    offset: int = Query(default=0, ge=0, description="Paginierungs-Offset"),
    limit: int = Query(
        default=50, ge=1, le=200, description="Eintraege pro Seite (max 200)"
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> UserTimeline:
    """Timeline aller Aktionen eines bestimmten Benutzers.

    Listet alle Audit-Log-Eintraege dieses Benutzers auf,
    gefiltert nach dem aktuellen Mandanten.

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_user_timeline",
        admin_id=str(admin.id),
        company_id=str(company_id),
        target_user_id=str(user_id),
        offset=offset,
        limit=limit,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.get_user_timeline(
            db=db,
            company_id=company_id,
            user_id=user_id,
            offset=offset,
            limit=limit,
        )

        _REQUEST_COUNTER.labels(endpoint="by_user", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="by_user").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="by_user", status="error").inc()
        logger.error(
            "access_analytics_user_timeline_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            target_user_id=str(user_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Benutzer-Timeline konnte nicht geladen werden.",
        ) from exc


# =============================================================================
# GET /access-analytics/by-document/{document_id}
# =============================================================================


@router.get(
    "/by-document/{document_id}",
    response_model=DocumentAccessLog,
    summary="Dokumentenzugriffs-Protokoll",
    description=(
        "Zeigt wer ein bestimmtes Dokument wann angesehen oder bearbeitet hat. "
        "Paginiert, neueste Eintraege zuerst. Nur fuer Administratoren."
    ),
)
async def get_document_access_log(
    document_id: UUID,
    offset: int = Query(default=0, ge=0, description="Paginierungs-Offset"),
    limit: int = Query(
        default=50, ge=1, le=200, description="Eintraege pro Seite (max 200)"
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> DocumentAccessLog:
    """Wer hat dieses Dokument wann angesehen oder bearbeitet.

    Gibt alle Audit-Log-Eintraege zurueck, die sich auf das angegebene
    Dokument beziehen, gefiltert nach dem aktuellen Mandanten.

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_document_log",
        admin_id=str(admin.id),
        company_id=str(company_id),
        document_id=str(document_id),
        offset=offset,
        limit=limit,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.get_document_access_log(
            db=db,
            company_id=company_id,
            document_id=document_id,
            offset=offset,
            limit=limit,
        )

        _REQUEST_COUNTER.labels(endpoint="by_document", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="by_document").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="by_document", status="error").inc()
        logger.error(
            "access_analytics_document_log_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            document_id=str(document_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dokument-Zugriffsprotokoll konnte nicht geladen werden.",
        ) from exc


# =============================================================================
# GET /access-analytics/anomalies
# =============================================================================


@router.get(
    "/anomalies",
    response_model=List[AccessAnomaly],
    summary="Anomalie-Erkennung",
    description=(
        "Erkennt ungewoehnliche Zugriffsmuster anhand von konfigurierten Schwellenwerten. "
        "Prueft auf: Massen-Downloads, Brute-Force-Angriffe, Off-Hours-Zugriffe, "
        "Massen-Dokumentenscans und ungewoehnliche Exporte. Nur fuer Administratoren."
    ),
)
async def get_anomalies(
    hours: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Betrachtungszeitraum in Stunden (1-168, Standard: 24)",
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[AccessAnomaly]:
    """Erkennt ungewoehnliche Zugriffsmuster fuer den aktuellen Mandanten.

    Erkannte Anomalie-Typen:
    - mass_download: >50 Downloads/Stunde pro Benutzer
    - brute_force: >10 fehlgeschlagene Logins/Stunde pro IP
    - off_hours_access: Erhebliche Aktivitaet zwischen 23:00-05:00 Uhr
    - mass_document_scan: >100 eindeutige Dokumente in 30 Minuten
    - unusual_export: Grosse Exporte ausserhalb der Geschaeftszeiten

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_anomaly_detection",
        admin_id=str(admin.id),
        company_id=str(company_id),
        hours=hours,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.detect_anomalies(
            db=db, company_id=company_id, hours=hours
        )

        _REQUEST_COUNTER.labels(endpoint="anomalies", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="anomalies").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="anomalies", status="error").inc()
        logger.error(
            "access_analytics_anomaly_detection_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Anomalie-Erkennung konnte nicht ausgefuehrt werden.",
        ) from exc


# =============================================================================
# GET /access-analytics/stats/hourly
# =============================================================================


@router.get(
    "/stats/hourly",
    response_model=List[HourlyStats],
    summary="Stuendliche Zugriffsverteilung",
    description=(
        "Gibt die stuendliche Zugriffsverteilung fuer alle 24 Stunden des Tages zurueck. "
        "Geeignet fuer Heatmap-Visualisierungen. Nur fuer Administratoren."
    ),
)
async def get_hourly_stats(
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Betrachtungszeitraum in Tagen (1-90, Standard: 7)",
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[HourlyStats]:
    """Stuendliche Zugriffsverteilung fuer Heatmap-Visualisierung.

    Gibt fuer jede Stunde (0-23) die Gesamtanzahl der Zugriffe zurueck.
    Stunden ohne Zugriffe werden mit count=0 zurueckgegeben.

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_hourly_stats",
        admin_id=str(admin.id),
        company_id=str(company_id),
        days=days,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.get_hourly_distribution(
            db=db, company_id=company_id, days=days
        )

        _REQUEST_COUNTER.labels(endpoint="stats_hourly", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="stats_hourly").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="stats_hourly", status="error").inc()
        logger.error(
            "access_analytics_hourly_stats_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stuendliche Zugriffsstatistik konnte nicht geladen werden.",
        ) from exc


# =============================================================================
# GET /access-analytics/stats/event-types
# =============================================================================


@router.get(
    "/stats/event-types",
    response_model=List[EventTypeStat],
    summary="Event-Typ Verteilung",
    description=(
        "Gibt die Verteilung aller Event-Typen im Betrachtungszeitraum zurueck "
        "(z.B. document_view, document_upload, login, etc.). "
        "Absteigend nach Haeufigkeit sortiert. Nur fuer Administratoren."
    ),
)
async def get_event_type_stats(
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Betrachtungszeitraum in Tagen (1-90, Standard: 7)",
    ),
    admin: User = Depends(require_permission("admin:audit:read")),
    company: object = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[EventTypeStat]:
    """Verteilung der Event-Typen im Betrachtungszeitraum.

    Gibt fuer jeden Event-Typ die absolute Anzahl und den prozentualen
    Anteil am Gesamtvolumen zurueck. Begrenzt auf die Top-50 Event-Typen.

    Erfordert Berechtigung: admin:audit:read
    """
    import time

    start = time.perf_counter()
    company_id: UUID = company.id  # type: ignore[union-attr]

    logger.info(
        "access_analytics_event_type_stats",
        admin_id=str(admin.id),
        company_id=str(company_id),
        days=days,
    )

    try:
        service = AccessAnalyticsService()
        result = await service.get_event_type_stats(
            db=db, company_id=company_id, days=days
        )

        _REQUEST_COUNTER.labels(endpoint="stats_event_types", status="success").inc()
        _REQUEST_DURATION.labels(endpoint="stats_event_types").observe(
            time.perf_counter() - start
        )
        return result

    except Exception as exc:
        _REQUEST_COUNTER.labels(endpoint="stats_event_types", status="error").inc()
        logger.error(
            "access_analytics_event_type_stats_failed",
            admin_id=str(admin.id),
            company_id=str(company_id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event-Typ-Statistik konnte nicht geladen werden.",
        ) from exc
