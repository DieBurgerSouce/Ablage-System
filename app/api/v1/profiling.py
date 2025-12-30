# -*- coding: utf-8 -*-
"""
Performance Profiling API Endpoints.

Bietet Admin-Endpoints fuer:
- Endpoint-Performance-Statistiken
- Langsame Requests
- Hot Paths
- Memory-Snapshots
- Profiling-Konfiguration

Alle Endpoints erfordern Admin-Authentifizierung.
"""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.profiling_service import (
    ProfilingLevel,
    get_profiling_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/profiling", tags=["profiling"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class ProfilingConfigRequest(BaseModel):
    """Request zum Konfigurieren des Profilings."""

    level: Optional[ProfilingLevel] = Field(
        None,
        description="Profiling-Level: off, basic, detailed, full",
    )
    slow_threshold_ms: Optional[float] = Field(
        None,
        gt=0,
        le=60000,
        description="Schwellwert fuer langsame Requests in ms (1-60000)",
    )


class ProfilingConfigResponse(BaseModel):
    """Response mit Profiling-Konfiguration."""

    profiling_level: str
    slow_request_threshold_ms: float
    max_slow_requests: int
    max_memory_snapshots: int
    excluded_paths: list


class ProfilingSummaryResponse(BaseModel):
    """Response mit Profiling-Zusammenfassung."""

    status: str
    profiling_level: str
    uptime_seconds: float
    uptime_formatted: str
    total_endpoints_tracked: int
    total_requests: int
    total_errors: int
    error_rate_percent: float
    total_slow_requests: int
    slow_request_threshold_ms: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    memory_snapshots_count: int
    slow_requests_buffer_count: int


class ResetResponse(BaseModel):
    """Response fuer Reset-Operationen."""

    status: str
    geloeschte_endpoints: int
    geloeschte_langsame_requests: int
    geloeschte_snapshots: int


class MemorySnapshotTriggerResponse(BaseModel):
    """Response nach Memory-Snapshot."""

    timestamp: str
    rss_mb: float
    vms_mb: float
    shared_mb: float
    heap_mb: Optional[float]
    gpu_used_mb: Optional[float]
    context: Optional[str]


# =============================================================================
# GET /profiling/summary
# =============================================================================


@router.get("/summary", response_model=ProfilingSummaryResponse)
async def get_profiling_summary(
    current_user: User = Depends(get_current_superuser),
) -> ProfilingSummaryResponse:
    """
    Profiling-Zusammenfassung abrufen.

    Gibt aggregierte Metriken ueber alle getracten Endpoints zurueck:
    - Gesamtzahl Requests und Fehler
    - Latenz-Statistiken (avg, p95, p99)
    - Anzahl langsamer Requests
    - Uptime des Profiling-Service

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    summary = service.get_summary()

    logger.info(
        "profiling_summary_retrieved",
        user_id=str(current_user.id),
        endpoints_tracked=summary["total_endpoints_tracked"],
    )

    return ProfilingSummaryResponse(**summary)


# =============================================================================
# GET /profiling/endpoints
# =============================================================================


@router.get("/endpoints")
async def get_endpoint_stats(
    current_user: User = Depends(get_current_superuser),
    endpoint: Optional[str] = Query(None, description="Filter nach Endpoint-Pfad"),
    method: Optional[str] = Query(None, description="Filter nach HTTP-Methode"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Ergebnisse"),
    sort_by: str = Query(
        "request_count",
        description="Sortierfeld",
        pattern="^(request_count|avg_time_ms|max_time_ms|error_count|slow_request_count)$",
    ),
):
    """
    Endpoint-Statistiken abrufen.

    Gibt detaillierte Performance-Metriken pro Endpoint zurueck:
    - Request-Count, Fehler, langsame Requests
    - Timing-Statistiken (min, max, avg, p50, p95, p99)
    - Error-Rate

    **Erfordert Admin-Authentifizierung.**

    **Sortieroptionen:**
    - `request_count`: Nach Anzahl Requests (Standard)
    - `avg_time_ms`: Nach durchschnittlicher Dauer
    - `max_time_ms`: Nach maximaler Dauer
    - `error_count`: Nach Anzahl Fehler
    - `slow_request_count`: Nach Anzahl langsamer Requests
    """
    service = get_profiling_service()
    stats = service.get_endpoint_stats(
        endpoint=endpoint,
        method=method,
        limit=limit,
        sort_by=sort_by,
    )

    logger.info(
        "endpoint_stats_retrieved",
        user_id=str(current_user.id),
        count=len(stats),
        filter_endpoint=endpoint,
        filter_method=method,
    )

    return {
        "zeitstempel": service.get_summary()["uptime_formatted"],
        "total_count": len(stats),
        "filter": {
            "endpoint": endpoint,
            "method": method,
            "sort_by": sort_by,
            "limit": limit,
        },
        "endpoints": stats,
    }


# =============================================================================
# GET /profiling/slow-requests
# =============================================================================


@router.get("/slow-requests")
async def get_slow_requests(
    current_user: User = Depends(get_current_superuser),
    endpoint: Optional[str] = Query(None, description="Filter nach Endpoint-Pfad"),
    limit: int = Query(20, ge=1, le=100, description="Maximale Anzahl Ergebnisse"),
):
    """
    Langsame Requests abrufen.

    Gibt aufgezeichnete langsame Requests zurueck (sortiert nach Dauer):
    - Timestamp, Endpoint, Methode
    - Dauer, Status-Code
    - Request-ID, User-ID
    - Memory-Nutzung (wenn aktiviert)

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    requests = service.get_slow_requests(endpoint=endpoint, limit=limit)
    config = service.configure()

    logger.info(
        "slow_requests_retrieved",
        user_id=str(current_user.id),
        count=len(requests),
    )

    return {
        "schwellwert_ms": config["slow_request_threshold_ms"],
        "total_count": len(requests),
        "filter": {
            "endpoint": endpoint,
            "limit": limit,
        },
        "requests": requests,
    }


# =============================================================================
# GET /profiling/hot-paths
# =============================================================================


@router.get("/hot-paths")
async def get_hot_paths(
    current_user: User = Depends(get_current_superuser),
    limit: int = Query(10, ge=1, le=50, description="Maximale Anzahl Ergebnisse"),
):
    """
    Hot Paths (meistgenutzte Endpoints) abrufen.

    Gibt die am haeufigsten aufgerufenen Endpoints zurueck:
    - Rang, Endpoint, Methode
    - Request-Count
    - Durchschnittliche Latenz
    - Requests pro Sekunde

    **Erfordert Admin-Authentifizierung.**

    Nuetzlich fuer:
    - Performance-Optimierung
    - Kapazitaetsplanung
    - Caching-Entscheidungen
    """
    service = get_profiling_service()
    hot_paths = service.get_hot_paths(limit=limit)

    logger.info(
        "hot_paths_retrieved",
        user_id=str(current_user.id),
        count=len(hot_paths),
    )

    return {
        "total_count": len(hot_paths),
        "hot_paths": hot_paths,
    }


# =============================================================================
# GET /profiling/memory
# =============================================================================


@router.get("/memory")
async def get_memory_snapshots(
    current_user: User = Depends(get_current_superuser),
    limit: int = Query(20, ge=1, le=100, description="Maximale Anzahl Ergebnisse"),
):
    """
    Memory-Snapshots abrufen.

    Gibt aufgezeichnete Memory-Snapshots zurueck (neueste zuerst):
    - Timestamp, Kontext
    - RSS, VMS, Shared Memory (in MB)
    - GPU-Speicher (wenn verfuegbar)

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    snapshots = service.get_memory_snapshots(limit=limit)

    logger.info(
        "memory_snapshots_retrieved",
        user_id=str(current_user.id),
        count=len(snapshots),
    )

    return {
        "total_count": len(snapshots),
        "snapshots": snapshots,
    }


# =============================================================================
# POST /profiling/memory/snapshot
# =============================================================================


@router.post("/memory/snapshot", response_model=MemorySnapshotTriggerResponse)
async def trigger_memory_snapshot(
    current_user: User = Depends(get_current_superuser),
    context: Optional[str] = Query(None, max_length=100, description="Optionaler Kontext-String"),
) -> MemorySnapshotTriggerResponse:
    """
    Memory-Snapshot manuell ausloesen.

    Erstellt einen neuen Memory-Snapshot und gibt ihn zurueck.
    Nuetzlich fuer:
    - Debugging von Memory-Leaks
    - Vergleich vor/nach Operationen
    - Baseline-Messungen

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    snapshot = service.take_memory_snapshot(context=context)

    logger.info(
        "memory_snapshot_triggered",
        user_id=str(current_user.id),
        context=context,
        rss_mb=round(snapshot.rss_mb, 2),
    )

    return MemorySnapshotTriggerResponse(**snapshot.to_dict())


# =============================================================================
# GET /profiling/config
# =============================================================================


@router.get("/config", response_model=ProfilingConfigResponse)
async def get_profiling_config(
    current_user: User = Depends(get_current_superuser),
) -> ProfilingConfigResponse:
    """
    Aktuelle Profiling-Konfiguration abrufen.

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    config = service.configure()

    logger.info(
        "profiling_config_retrieved",
        user_id=str(current_user.id),
    )

    return ProfilingConfigResponse(**config)


# =============================================================================
# POST /profiling/config
# =============================================================================


@router.post("/config", response_model=ProfilingConfigResponse)
async def update_profiling_config(
    config: ProfilingConfigRequest,
    current_user: User = Depends(get_current_superuser),
) -> ProfilingConfigResponse:
    """
    Profiling-Konfiguration aktualisieren.

    Aendert Profiling-Einstellungen:
    - **level**: off, basic, detailed, full
    - **slow_threshold_ms**: Schwellwert fuer langsame Requests (1-60000ms)

    **Erfordert Admin-Authentifizierung.**

    **Level-Beschreibungen:**
    - `off`: Profiling deaktiviert
    - `basic`: Nur Timing-Metriken
    - `detailed`: Timings + Memory-Tracking
    - `full`: Alles inklusive Stack-Traces
    """
    service = get_profiling_service()

    new_config = service.configure(
        level=config.level,
        slow_threshold_ms=config.slow_threshold_ms,
    )

    logger.warning(
        "profiling_config_updated",
        user_id=str(current_user.id),
        user_email=current_user.email,
        new_level=config.level.value if config.level else None,
        new_threshold_ms=config.slow_threshold_ms,
    )

    return ProfilingConfigResponse(**new_config)


# =============================================================================
# POST /profiling/reset
# =============================================================================


@router.post("/reset", response_model=ResetResponse)
async def reset_profiling_stats(
    current_user: User = Depends(get_current_superuser),
) -> ResetResponse:
    """
    Alle Profiling-Statistiken zuruecksetzen.

    Loescht:
    - Alle Endpoint-Statistiken
    - Alle aufgezeichneten langsamen Requests
    - Alle Memory-Snapshots

    **ACHTUNG: Diese Aktion kann nicht rueckgaengig gemacht werden!**

    **Erfordert Admin-Authentifizierung.**
    """
    service = get_profiling_service()
    result = service.reset_stats()

    logger.warning(
        "profiling_stats_reset_by_user",
        user_id=str(current_user.id),
        user_email=current_user.email,
        endpoints_cleared=result["geloeschte_endpoints"],
        slow_requests_cleared=result["geloeschte_langsame_requests"],
    )

    return ResetResponse(**result)


# =============================================================================
# GET /profiling/prometheus
# =============================================================================


@router.get("/prometheus", response_class=Response)
async def get_profiling_prometheus_metrics(
    current_user: User = Depends(get_current_superuser),  # V.7 SECURITY FIX: Superuser-Auth required
):
    """
    Prometheus-Metriken fuer Profiling.

    Gibt Profiling-spezifische Metriken im Prometheus-Format zurueck:
    - `ablage_profiling_requests_total`: Anzahl profilierter Requests
    - `ablage_profiling_latency_seconds`: Request-Latenz-Histogram
    - `ablage_profiling_slow_requests_total`: Anzahl langsamer Requests
    - `ablage_profiling_memory_usage_bytes`: Memory-Nutzung

    **V.7 SECURITY FIX: Erfordert Admin-Authentifizierung.**

    Fuer Prometheus-Scraping ohne Auth verwenden Sie stattdessen
    einen internen Endpoint mit IP-Whitelist oder Service-Mesh.

    Example Prometheus config (mit Basic Auth):
    ```yaml
    scrape_configs:
      - job_name: 'ablage-profiling'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/api/v1/profiling/prometheus'
        basic_auth:
          username: 'admin'
          password: 'secret'
    ```
    """
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    logger.debug(
        "prometheus_metrics_retrieved",
        user_id=str(current_user.id),
    )

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# =============================================================================
# GET /profiling/report
# =============================================================================


@router.get("/report")
async def get_profiling_report(
    current_user: User = Depends(get_current_superuser),
):
    """
    Umfassenden Profiling-Report generieren.

    Kombiniert alle Profiling-Daten in einem Report:
    - Zusammenfassung
    - Top 10 Hot Paths
    - Top 10 langsamste Endpoints
    - Letzte 10 langsame Requests
    - Letzter Memory-Snapshot

    **Erfordert Admin-Authentifizierung.**

    Nuetzlich fuer:
    - Performance-Reviews
    - Debugging-Sessions
    - Kapazitaetsplanung
    """
    service = get_profiling_service()

    summary = service.get_summary()
    hot_paths = service.get_hot_paths(limit=10)
    slowest = service.get_endpoint_stats(limit=10, sort_by="avg_time_ms")
    slow_requests = service.get_slow_requests(limit=10)
    memory = service.get_memory_snapshots(limit=1)

    logger.info(
        "profiling_report_generated",
        user_id=str(current_user.id),
    )

    return {
        "report_generiert_am": summary["uptime_formatted"],
        "zusammenfassung": summary,
        "hot_paths": {
            "beschreibung": "Meistgenutzte Endpoints",
            "endpoints": hot_paths,
        },
        "langsamste_endpoints": {
            "beschreibung": "Endpoints mit hoechster durchschnittlicher Latenz",
            "endpoints": slowest,
        },
        "langsame_requests": {
            "beschreibung": f"Requests ueber {summary['slow_request_threshold_ms']}ms",
            "requests": slow_requests,
        },
        "memory": {
            "beschreibung": "Letzter Memory-Snapshot",
            "snapshot": memory[0] if memory else None,
        },
        "empfehlungen": _generate_recommendations(summary, slowest, hot_paths),
    }


def _generate_recommendations(
    summary: dict,
    slowest: list,
    hot_paths: list,
) -> list:
    """Generiert Performance-Empfehlungen basierend auf Daten."""
    recommendations = []

    # Error Rate
    if summary["error_rate_percent"] > 5:
        recommendations.append({
            "typ": "warnung",
            "bereich": "Fehlerrate",
            "nachricht": f"Fehlerrate bei {summary['error_rate_percent']}% - sollte unter 5% sein",
            "prioritaet": "hoch",
        })

    # P99 Latenz
    if summary["p99_latency_ms"] > 2000:
        recommendations.append({
            "typ": "warnung",
            "bereich": "Latenz",
            "nachricht": f"P99-Latenz bei {summary['p99_latency_ms']}ms - sollte unter 2000ms sein",
            "prioritaet": "mittel",
        })

    # Slow Requests
    if summary["total_slow_requests"] > 0:
        slow_ratio = summary["total_slow_requests"] / max(summary["total_requests"], 1) * 100
        if slow_ratio > 1:
            recommendations.append({
                "typ": "warnung",
                "bereich": "Langsame Requests",
                "nachricht": f"{slow_ratio:.1f}% der Requests sind langsam - Ursachen pruefen",
                "prioritaet": "mittel",
            })

    # Hot Path mit hoher Latenz
    for hp in hot_paths[:3]:
        if hp["avg_time_ms"] > 500:
            recommendations.append({
                "typ": "optimierung",
                "bereich": "Hot Path",
                "nachricht": f"Haeufig genutzter Endpoint {hp['endpoint']} hat hohe Latenz ({hp['avg_time_ms']}ms) - Caching/Optimierung pruefen",
                "prioritaet": "hoch",
            })

    if not recommendations:
        recommendations.append({
            "typ": "info",
            "bereich": "Allgemein",
            "nachricht": "Keine kritischen Performance-Probleme erkannt",
            "prioritaet": "niedrig",
        })

    return recommendations
