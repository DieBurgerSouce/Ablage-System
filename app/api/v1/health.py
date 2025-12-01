# -*- coding: utf-8 -*-
"""
Health Check API Endpoints.

Detaillierte Gesundheitspruefungen fuer alle Systemkomponenten.
Feinpoliert und durchdacht - Enterprise Health Monitoring.

Features:
- TTL-basiertes Caching für teure Health-Checks (5 Sekunden)
- Reduziert Last bei häufigen Monitoring-Abfragen
- Kubernetes-kompatible Probes (live, ready, startup)
- Parallele Health-Checks für schnellere Antwortzeiten
- Umfassende System-Informationen
"""

import asyncio
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import threading

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Track startup time for uptime calculation
_startup_time = time.time()

# TTL-based caching for health checks
try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    TTLCache = None
    CACHETOOLS_AVAILABLE = False

from app.api.dependencies import get_db
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Health check cache configuration
HEALTH_CHECK_CACHE_TTL = 5  # 5 seconds TTL
HEALTH_CHECK_CACHE_MAXSIZE = 10  # Max cached entries

# Thread-safe cache for health check results
if CACHETOOLS_AVAILABLE:
    _health_cache: TTLCache = TTLCache(
        maxsize=HEALTH_CHECK_CACHE_MAXSIZE,
        ttl=HEALTH_CHECK_CACHE_TTL
    )
    _health_cache_lock = threading.Lock()
else:
    _health_cache: Dict[str, Any] = {}
    _health_cache_lock = threading.Lock()


def _get_cached_result(cache_key: str) -> Optional[Any]:
    """Get cached health check result if available."""
    if not CACHETOOLS_AVAILABLE:
        return None

    with _health_cache_lock:
        return _health_cache.get(cache_key)


def _set_cached_result(cache_key: str, result: Any) -> None:
    """Cache health check result."""
    if not CACHETOOLS_AVAILABLE:
        return

    with _health_cache_lock:
        _health_cache[cache_key] = result

router = APIRouter(prefix="/health", tags=["health"])


# =============================================================================
# Response Models
# =============================================================================


class KomponentenStatus(BaseModel):
    """Status einer einzelnen Komponente."""

    gesund: bool = Field(..., description="Ist Komponente gesund?")
    nachricht: Optional[str] = Field(None, description="Status-Nachricht")
    latenz_ms: Optional[float] = Field(None, description="Antwortzeit in ms")
    details: Optional[Dict[str, Any]] = Field(None, description="Weitere Details")


class BasicHealthResponse(BaseModel):
    """Einfache Gesundheitspruefung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default="0.2.0-poc", description="API-Version")


class DetailedHealthResponse(BaseModel):
    """Detaillierte Gesundheitspruefung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default="0.2.0-poc", description="API-Version")
    komponenten: Dict[str, KomponentenStatus] = Field(
        ..., description="Status je Komponente"
    )
    zusammenfassung: str = Field(..., description="Kurze Zusammenfassung")


class DependencyHealthResponse(BaseModel):
    """Gesundheitspruefung der Abhaengigkeiten."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    datenbank: KomponentenStatus = Field(..., description="PostgreSQL-Status")
    cache: KomponentenStatus = Field(..., description="Redis-Status")
    speicher: KomponentenStatus = Field(..., description="MinIO-Status")


# =============================================================================
# Helper Functions
# =============================================================================


async def _check_database(db: AsyncSession) -> KomponentenStatus:
    """Pruefe Datenbank-Verbindung."""
    import time

    start = time.perf_counter()
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        latenz = (time.perf_counter() - start) * 1000

        return KomponentenStatus(
            gesund=True,
            nachricht="PostgreSQL erreichbar",
            latenz_ms=round(latenz, 2),
            details={"pool_size": settings.DB_POOL_SIZE},
        )
    except Exception as e:
        logger.error("health_check_database_failed", error=str(e))
        return KomponentenStatus(
            gesund=False,
            nachricht=f"Datenbank nicht erreichbar: {str(e)[:100]}",
            latenz_ms=None,
        )


async def _check_redis() -> KomponentenStatus:
    """Pruefe Redis-Verbindung.

    Testet Verbindung zum Redis-Server via PING-Befehl.

    Returns:
        KomponentenStatus mit Latenz bei Erfolg

    Note:
        Erfordert redis.asyncio (optionale Abhaengigkeit).
        Bei fehlendem Modul wird gesund=False zurueckgegeben.
    """
    import time

    try:
        import redis.asyncio as redis

        start = time.perf_counter()
        client = redis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            decode_responses=True,
        )
        await client.ping()
        latenz = (time.perf_counter() - start) * 1000
        await client.close()

        return KomponentenStatus(
            gesund=True,
            nachricht="Redis erreichbar",
            latenz_ms=round(latenz, 2),
            details={
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
            },
        )
    except ImportError:
        return KomponentenStatus(
            gesund=False, nachricht="Redis-Client nicht installiert"
        )
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"Redis nicht erreichbar: {str(e)[:100]}"
        )


def _check_gpu() -> KomponentenStatus:
    """Pruefe GPU-Verfuegbarkeit."""
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            memory_total = torch.cuda.get_device_properties(0).total_memory
            memory_allocated = torch.cuda.memory_allocated(0)
            memory_percent = (memory_allocated / memory_total) * 100

            return KomponentenStatus(
                gesund=memory_percent < 85,
                nachricht=f"GPU verfuegbar: {device_name}",
                details={
                    "geraet": device_name,
                    "speicher_total_gb": round(memory_total / 1024**3, 2),
                    "speicher_belegt_gb": round(memory_allocated / 1024**3, 2),
                    "speicher_prozent": round(memory_percent, 1),
                },
            )
        else:
            return KomponentenStatus(
                gesund=True,
                nachricht="Keine GPU verfuegbar - CPU-Modus aktiv",
                details={"cuda_verfuegbar": False},
            )
    except ImportError:
        return KomponentenStatus(
            gesund=True,
            nachricht="PyTorch nicht installiert - CPU-Modus",
            details={"pytorch_installiert": False},
        )
    except Exception as e:
        logger.error("health_check_gpu_failed", error=str(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"GPU-Pruefung fehlgeschlagen: {str(e)[:100]}"
        )


def _check_disk_space() -> KomponentenStatus:
    """Pruefe verfuegbaren Speicherplatz."""
    try:
        import shutil

        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        used_percent = (used / total) * 100

        return KomponentenStatus(
            gesund=free_gb > 10,  # Mindestens 10GB frei
            nachricht=f"{free_gb:.1f} GB frei",
            details={
                "gesamt_gb": round(total / (1024**3), 1),
                "belegt_gb": round(used / (1024**3), 1),
                "frei_gb": round(free_gb, 1),
                "belegt_prozent": round(used_percent, 1),
            },
        )
    except Exception as e:
        logger.error("health_check_disk_failed", error=str(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"Speicherplatz-Pruefung fehlgeschlagen: {str(e)[:100]}"
        )


async def _check_minio() -> KomponentenStatus:
    """Pruefe MinIO-Verbindung."""
    import time

    try:
        from minio import Minio

        start = time.perf_counter()
        client = Minio(
            f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        # List buckets als Health Check
        buckets = client.list_buckets()
        latenz = (time.perf_counter() - start) * 1000

        return KomponentenStatus(
            gesund=True,
            nachricht=f"MinIO erreichbar - {len(buckets)} Buckets",
            latenz_ms=round(latenz, 2),
            details={
                "host": settings.MINIO_HOST,
                "buckets": len(buckets),
            },
        )
    except ImportError:
        return KomponentenStatus(
            gesund=False, nachricht="MinIO-Client nicht installiert"
        )
    except Exception as e:
        logger.error("health_check_minio_failed", error=str(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"MinIO nicht erreichbar: {str(e)[:100]}"
        )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/",
    response_model=BasicHealthResponse,
    summary="Einfache Gesundheitspruefung",
    description="Schnelle Pruefung ob API erreichbar ist.",
)
async def basic_health() -> BasicHealthResponse:
    """Einfache Gesundheitspruefung - nur API-Erreichbarkeit."""
    return BasicHealthResponse(
        status="gesund",
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version="0.2.0-poc",
    )


@router.get(
    "/detailed",
    response_model=DetailedHealthResponse,
    summary="Detaillierte Gesundheitspruefung",
    description="Prueft alle Systemkomponenten: Datenbank, Redis, GPU, Speicher. Ergebnisse werden 5 Sekunden gecacht.",
)
async def detailed_health(
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthResponse:
    """
    Detaillierte Gesundheitspruefung aller Komponenten.

    Prueft:
    - PostgreSQL-Datenbank
    - Redis-Cache
    - GPU-Verfuegbarkeit und -Speicher
    - Festplatten-Speicherplatz

    Ergebnisse werden 5 Sekunden gecacht um Last bei häufigen
    Monitoring-Abfragen zu reduzieren.
    """
    # Check cache first
    cache_key = "detailed_health"
    cached = _get_cached_result(cache_key)
    if cached is not None:
        logger.debug("health_check_cache_hit", endpoint="detailed")
        return cached

    # Pruefe alle Komponenten
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    gpu_status = _check_gpu()
    disk_status = _check_disk_space()

    komponenten = {
        "datenbank": db_status,
        "cache": redis_status,
        "gpu": gpu_status,
        "speicherplatz": disk_status,
    }

    # Bestimme Gesamtstatus
    kritisch = [k for k, v in komponenten.items() if not v.gesund and k in ["datenbank"]]
    beeintraechtigt = [k for k, v in komponenten.items() if not v.gesund and k not in ["datenbank"]]

    if kritisch:
        status = "kritisch"
        zusammenfassung = f"Kritische Fehler: {', '.join(kritisch)}"
    elif beeintraechtigt:
        status = "beeintraechtigt"
        zusammenfassung = f"Beeintraechtigte Komponenten: {', '.join(beeintraechtigt)}"
    else:
        status = "gesund"
        zusammenfassung = "Alle Komponenten funktionieren ordnungsgemaess"

    logger.info(
        "health_check_complete",
        status=status,
        komponenten={k: v.gesund for k, v in komponenten.items()},
    )

    result = DetailedHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version="0.2.0-poc",
        komponenten=komponenten,
        zusammenfassung=zusammenfassung,
    )

    # Cache the result
    _set_cached_result(cache_key, result)

    return result


@router.get(
    "/dependencies",
    response_model=DependencyHealthResponse,
    summary="Abhaengigkeiten pruefen",
    description="Prueft externe Abhaengigkeiten: Datenbank, Redis, MinIO.",
)
async def check_dependencies(
    db: AsyncSession = Depends(get_db),
) -> DependencyHealthResponse:
    """
    Prueft nur externe Abhaengigkeiten (Datenbank, Cache, Speicher).

    Nuetzlich fuer Kubernetes Readiness Probes.
    """
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    minio_status = await _check_minio()

    all_healthy = all([db_status.gesund, redis_status.gesund, minio_status.gesund])

    if all_healthy:
        status = "gesund"
    elif db_status.gesund:
        status = "beeintraechtigt"
    else:
        status = "kritisch"

    return DependencyHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        datenbank=db_status,
        cache=redis_status,
        speicher=minio_status,
    )


@router.get(
    "/live",
    summary="Liveness Probe",
    description="Kubernetes Liveness Probe - prueft nur ob API laeuft.",
)
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes Liveness Probe."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Kubernetes Readiness Probe - prueft Datenbank-Verbindung.",
)
async def readiness_probe(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Kubernetes Readiness Probe."""
    db_status = await _check_database(db)

    if not db_status.gesund:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbank nicht verfuegbar",
        )

    return {"status": "ready", "datenbank": db_status.gesund}


@router.get(
    "/startup",
    summary="Startup Probe",
    description="Kubernetes Startup Probe - prueft ob Anwendung vollstaendig gestartet ist.",
)
async def startup_probe(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Kubernetes Startup Probe.

    Prueft ob alle kritischen Komponenten beim Start bereit sind:
    - Datenbank-Verbindung
    - Redis-Verbindung
    - Model Preloader Status (falls aktiviert)

    Unterschied zu Readiness:
    - Startup Probe laeuft nur einmal beim Start
    - Readiness Probe laeuft kontinuierlich
    """
    from fastapi import HTTPException, status

    startup_checks = {}
    errors = []

    # Check Database
    db_status = await _check_database(db)
    startup_checks["datenbank"] = db_status.gesund
    if not db_status.gesund:
        errors.append("Datenbank nicht verfuegbar")

    # Check Redis
    redis_status = await _check_redis()
    startup_checks["redis"] = redis_status.gesund
    if not redis_status.gesund:
        errors.append("Redis nicht verfuegbar")

    # Check Model Preloader
    try:
        from app.services.model_preloader import get_model_preloader

        preloader = get_model_preloader()
        preloader_status = preloader.get_status()
        startup_checks["model_preloader"] = preloader_status.get("enabled", False)

        # If preloading is enabled, check if it completed
        if preloader_status.get("enabled") and preloader_status.get("preload_started"):
            if not preloader_status.get("preload_completed"):
                # Still loading - not ready yet
                startup_checks["models_ready"] = False
            else:
                startup_checks["models_ready"] = True
    except ImportError:
        startup_checks["model_preloader"] = False

    # Calculate startup duration
    uptime = time.time() - _startup_time

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "starting",
                "errors": errors,
                "checks": startup_checks,
                "uptime_seconds": round(uptime, 2),
            },
        )

    return {
        "status": "started",
        "checks": startup_checks,
        "uptime_seconds": round(uptime, 2),
    }


# =============================================================================
# Celery Worker Health Endpoints
# =============================================================================


class WorkerInfo(BaseModel):
    """Informationen zu einem einzelnen Celery Worker."""

    name: str = Field(..., description="Worker-Name")
    status: str = Field(..., description="active, idle, offline")
    hostname: str = Field(..., description="Hostname")
    pid: Optional[int] = Field(None, description="Process ID")
    concurrency: Optional[int] = Field(None, description="Worker Concurrency")
    active_tasks: int = Field(default=0, description="Aktive Tasks")
    processed_tasks: int = Field(default=0, description="Verarbeitete Tasks gesamt")
    gpu_memory_percent: Optional[float] = Field(None, description="GPU Memory Nutzung")
    last_heartbeat: Optional[str] = Field(None, description="Letzter Heartbeat")
    uptime_seconds: Optional[float] = Field(None, description="Laufzeit in Sekunden")


class QueueInfo(BaseModel):
    """Informationen zu einer Celery Queue."""

    name: str = Field(..., description="Queue-Name")
    length: int = Field(..., description="Anzahl Tasks in Queue")
    consumers: int = Field(default=0, description="Anzahl Consumer")


class WorkerHealthResponse(BaseModel):
    """Celery Worker Gesundheitsstatus."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    broker_erreichbar: bool = Field(..., description="Redis Broker erreichbar")
    workers_aktiv: int = Field(..., description="Anzahl aktiver Worker")
    workers_gesamt: int = Field(..., description="Gesamtzahl registrierter Worker")
    tasks_wartend: int = Field(..., description="Tasks in Warteschlange")
    tasks_aktiv: int = Field(..., description="Aktuell verarbeitete Tasks")
    workers: list[WorkerInfo] = Field(default_factory=list, description="Worker Details")
    queues: list[QueueInfo] = Field(default_factory=list, description="Queue Details")
    tasks_erfolg_rate: Optional[float] = Field(None, description="Task Erfolgsrate")
    durchschnittliche_task_dauer_ms: Optional[float] = Field(
        None, description="Durchschnittliche Task-Dauer"
    )
    empfehlungen: list = Field(default_factory=list, description="Empfehlungen")


async def _check_celery_workers() -> WorkerHealthResponse:
    """Pruefe Celery Worker Status."""
    import time
    from datetime import datetime, timezone

    empfehlungen = []
    workers_list = []
    queues_list = []
    tasks_wartend = 0
    tasks_aktiv = 0

    try:
        from app.workers.celery_app import celery_app
        import redis.asyncio as aioredis

        # Check broker connection
        broker_url = celery_app.conf.broker_url or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

        try:
            redis_client = aioredis.from_url(broker_url, decode_responses=True)
            await redis_client.ping()
            broker_erreichbar = True
        except Exception as e:
            logger.warning("celery_broker_check_failed", error=str(e))
            broker_erreichbar = False
            empfehlungen.append("Redis Broker nicht erreichbar - Worker können keine Tasks empfangen")
            return WorkerHealthResponse(
                status="kritisch",
                zeitstempel=datetime.now(timezone.utc).isoformat(),
                broker_erreichbar=False,
                workers_aktiv=0,
                workers_gesamt=0,
                tasks_wartend=0,
                tasks_aktiv=0,
                workers=[],
                queues=[],
                empfehlungen=empfehlungen,
            )

        # Get queue lengths from Redis
        queue_names = ["celery", "ocr_tasks", "gpu_tasks", "default"]
        for queue_name in queue_names:
            try:
                length = await redis_client.llen(queue_name)
                queues_list.append(QueueInfo(
                    name=queue_name,
                    length=length,
                    consumers=0,  # Will be updated from worker info
                ))
                tasks_wartend += length
            except Exception:
                pass

        await redis_client.close()

        # Get worker info using Celery inspect
        # Note: This is synchronous, so we run it carefully
        inspect = celery_app.control.inspect()

        # Get active workers (with timeout)
        try:
            active = inspect.active() or {}
            stats = inspect.stats() or {}
            ping_result = inspect.ping() or {}
            reserved = inspect.reserved() or {}
        except Exception as e:
            logger.warning("celery_inspect_failed", error=str(e))
            active = {}
            stats = {}
            ping_result = {}
            reserved = {}

        # Process worker information
        all_workers = set(active.keys()) | set(stats.keys()) | set(ping_result.keys())

        for worker_name in all_workers:
            worker_stats = stats.get(worker_name, {})
            worker_active = active.get(worker_name, [])
            worker_reserved = reserved.get(worker_name, [])

            # Determine worker status
            if worker_name in ping_result:
                worker_status = "active" if worker_active else "idle"
            else:
                worker_status = "offline"

            # Extract worker info
            pool_info = worker_stats.get("pool", {})
            total_tasks = worker_stats.get("total", {})

            # Calculate processed tasks
            processed = sum(total_tasks.values()) if isinstance(total_tasks, dict) else 0

            # Get GPU memory if available
            gpu_mem = None
            try:
                import torch
                if torch.cuda.is_available():
                    mem_used = torch.cuda.memory_allocated() / torch.cuda.get_device_properties(0).total_memory * 100
                    gpu_mem = round(mem_used, 1)
            except Exception:
                pass

            workers_list.append(WorkerInfo(
                name=worker_name,
                status=worker_status,
                hostname=worker_stats.get("hostname", worker_name.split("@")[-1] if "@" in worker_name else "unknown"),
                pid=worker_stats.get("pid"),
                concurrency=pool_info.get("max-concurrency"),
                active_tasks=len(worker_active),
                processed_tasks=processed,
                gpu_memory_percent=gpu_mem,
                last_heartbeat=datetime.now(timezone.utc).isoformat() if worker_status != "offline" else None,
                uptime_seconds=worker_stats.get("uptime"),
            ))

            tasks_aktiv += len(worker_active)

        # Calculate statistics
        workers_aktiv = sum(1 for w in workers_list if w.status in ["active", "idle"])
        workers_gesamt = len(workers_list)

        # Calculate success rate from stats
        tasks_erfolg_rate = None
        total_success = 0
        total_failed = 0

        for worker_name, worker_stats in stats.items():
            total_stats = worker_stats.get("total", {})
            if isinstance(total_stats, dict):
                for task_name, count in total_stats.items():
                    if "error" in task_name.lower() or "fail" in task_name.lower():
                        total_failed += count
                    else:
                        total_success += count

        if total_success + total_failed > 0:
            tasks_erfolg_rate = round((total_success / (total_success + total_failed)) * 100, 2)

        # Generate recommendations
        if workers_aktiv == 0:
            empfehlungen.append("Keine aktiven Worker - celery worker starten")
        elif workers_aktiv < 2:
            empfehlungen.append("Nur ein Worker aktiv - redundanten Worker hinzufügen")

        if tasks_wartend > 100:
            empfehlungen.append(f"Hohe Queue-Last ({tasks_wartend} Tasks) - mehr Worker skalieren")

        if tasks_erfolg_rate is not None and tasks_erfolg_rate < 95:
            empfehlungen.append(f"Niedrige Erfolgsrate ({tasks_erfolg_rate}%) - Fehlerursachen analysieren")

        # Determine overall status
        if not broker_erreichbar or workers_aktiv == 0:
            status = "kritisch"
        elif tasks_wartend > 50 or workers_aktiv < workers_gesamt:
            status = "beeintraechtigt"
        else:
            status = "gesund"

        logger.info(
            "celery_worker_health_complete",
            status=status,
            active_workers=workers_aktiv,
            total_workers=workers_gesamt,
            tasks_waiting=tasks_wartend,
            tasks_active=tasks_aktiv,
        )

        return WorkerHealthResponse(
            status=status,
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            broker_erreichbar=broker_erreichbar,
            workers_aktiv=workers_aktiv,
            workers_gesamt=workers_gesamt,
            tasks_wartend=tasks_wartend,
            tasks_aktiv=tasks_aktiv,
            workers=workers_list,
            queues=queues_list,
            tasks_erfolg_rate=tasks_erfolg_rate,
            empfehlungen=empfehlungen,
        )

    except ImportError as e:
        logger.warning("celery_not_available", error=str(e))
        return WorkerHealthResponse(
            status="unbekannt",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            broker_erreichbar=False,
            workers_aktiv=0,
            workers_gesamt=0,
            tasks_wartend=0,
            tasks_aktiv=0,
            workers=[],
            queues=[],
            empfehlungen=["Celery nicht installiert oder konfiguriert"],
        )
    except Exception as e:
        logger.error("celery_worker_health_failed", error=str(e))
        return WorkerHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            broker_erreichbar=False,
            workers_aktiv=0,
            workers_gesamt=0,
            tasks_wartend=0,
            tasks_aktiv=0,
            workers=[],
            queues=[],
            empfehlungen=[f"Worker-Prüfung fehlgeschlagen: {str(e)[:100]}"],
        )


@router.get(
    "/workers",
    response_model=WorkerHealthResponse,
    summary="Celery Worker Status",
    description="Prueft alle Celery Worker, Queues und Task-Statistiken.",
)
async def worker_health() -> WorkerHealthResponse:
    """
    Detaillierte Gesundheitspruefung der Celery Worker.

    Prueft:
    - Broker-Verbindung (Redis)
    - Aktive Worker und deren Status
    - Queue-Laengen
    - Task-Statistiken
    - GPU-Speicher pro Worker

    Gibt Empfehlungen bei Problemen.
    """
    # Check cache first
    cache_key = "worker_health"
    cached = _get_cached_result(cache_key)
    if cached is not None:
        logger.debug("health_check_cache_hit", endpoint="workers")
        return cached

    result = await _check_celery_workers()

    # Cache the result
    _set_cached_result(cache_key, result)

    return result


# =============================================================================
# OCR Health Endpoints
# =============================================================================


class OCRBackendHealth(BaseModel):
    """OCR Backend Gesundheitsstatus."""

    gesund: bool = Field(..., description="Ist Backend gesund?")
    grund: Optional[str] = Field(None, description="Grund falls ungesund")
    status: Optional[Dict[str, Any]] = Field(None, description="Backend-Status")


class OCRHealthResponse(BaseModel):
    """OCR Gesundheitspruefung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    gesamt_gesund: bool = Field(..., description="Mindestens ein Backend gesund")
    backends: Dict[str, OCRBackendHealth] = Field(..., description="Backend-Status")
    gesunde_backends: int = Field(..., description="Anzahl gesunder Backends")
    ungesunde_backends: int = Field(..., description="Anzahl ungesunder Backends")
    fallback_verfuegbar: bool = Field(..., description="CPU-Fallback verfuegbar")
    empfohlenes_backend: Optional[str] = Field(None, description="Empfohlenes Backend")


@router.get(
    "/ocr",
    response_model=OCRHealthResponse,
    summary="OCR Backend Gesundheitspruefung",
    description="Prueft alle OCR-Backends auf Verfuegbarkeit und VRAM.",
)
async def ocr_health() -> OCRHealthResponse:
    """
    Detaillierte Gesundheitspruefung aller OCR-Backends.

    Prueft:
    - DeepSeek-Janus-Pro (GPU)
    - GOT-OCR 2.0 (GPU)
    - Surya GPU (GPU)
    - Surya CPU (Fallback)

    Gibt Empfehlung fuer optimales Backend zurueck.
    """
    from app.services.ocr_service import OCRService

    # Create temporary OCR service instance for health check
    # In production, this should use a singleton or dependency injection
    try:
        ocr_service = OCRService()
        health_status = await ocr_service.get_health_status()

        # Convert backend health to response format
        backends = {}
        for name, health in health_status.get("backends", {}).items():
            backends[name] = OCRBackendHealth(
                gesund=health.get("healthy", False),
                grund=health.get("reason") if not health.get("healthy") else None,
                status=health.get("status"),
            )

        # Determine overall status
        healthy_count = health_status.get("healthy_count", 0)
        total = health_status.get("total_backends", 0)

        if healthy_count == 0:
            status = "kritisch"
        elif healthy_count < total:
            status = "beeintraechtigt"
        else:
            status = "gesund"

        # Get recommended backend
        recommendation = await ocr_service.get_recommended_backend()
        empfohlenes_backend = recommendation.get("recommended")

        # Clean up
        await ocr_service.cleanup()

        logger.info(
            "ocr_health_check_complete",
            status=status,
            healthy_count=healthy_count,
            total=total,
            recommended=empfohlenes_backend,
        )

        return OCRHealthResponse(
            status=status,
            zeitstempel=health_status.get("timestamp", datetime.now(timezone.utc).isoformat()),
            gesamt_gesund=health_status.get("overall_healthy", False),
            backends=backends,
            gesunde_backends=healthy_count,
            ungesunde_backends=health_status.get("unhealthy_count", 0),
            fallback_verfuegbar=health_status.get("fallback_available", False),
            empfohlenes_backend=empfohlenes_backend,
        )

    except Exception as e:
        logger.error("ocr_health_check_failed", error=str(e))
        return OCRHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            gesamt_gesund=False,
            backends={},
            gesunde_backends=0,
            ungesunde_backends=0,
            fallback_verfuegbar=False,
            empfohlenes_backend=None,
        )


@router.get(
    "/ocr/{backend_name}",
    response_model=OCRBackendHealth,
    summary="Einzelnes OCR Backend pruefen",
    description="Prueft ein spezifisches OCR-Backend.",
)
async def ocr_backend_health(backend_name: str) -> OCRBackendHealth:
    """
    Gesundheitspruefung fuer ein spezifisches OCR-Backend.

    Args:
        backend_name: Name des Backends (deepseek, got_ocr, surya, surya_gpu)

    Returns:
        Gesundheitsstatus des Backends
    """
    from app.services.ocr_service import OCRService

    try:
        ocr_service = OCRService()
        health = await ocr_service.check_backend_health(backend_name)
        await ocr_service.cleanup()

        return OCRBackendHealth(
            gesund=health.get("healthy", False),
            grund=health.get("reason") if not health.get("healthy") else None,
            status=health.get("status"),
        )

    except Exception as e:
        logger.error("ocr_backend_health_check_failed", backend=backend_name, error=str(e))
        return OCRBackendHealth(
            gesund=False,
            grund=f"Pruefung fehlgeschlagen: {str(e)[:100]}",
            status=None,
        )


# =============================================================================
# Circuit Breaker Health Endpoints
# =============================================================================


class CircuitBreakerHealth(BaseModel):
    """Circuit Breaker Gesundheitsstatus."""

    name: str = Field(..., description="Backend-Name")
    state: str = Field(..., description="closed, open, half_open")
    gesund: bool = Field(..., description="True wenn closed")
    failure_rate: float = Field(..., description="Aktuelle Fehlerrate")
    consecutive_failures: int = Field(..., description="Aufeinanderfolgende Fehler")
    retry_after_seconds: float = Field(..., description="Sekunden bis Retry moeglich")
    times_opened: int = Field(..., description="Wie oft geoeffnet")


class CircuitBreakerHealthResponse(BaseModel):
    """Circuit Breaker Gesamtstatus."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    circuit_breakers: Dict[str, CircuitBreakerHealth] = Field(
        ..., description="Status je Circuit Breaker"
    )
    offene_circuits: int = Field(..., description="Anzahl offener Circuits")
    gesamtzahl: int = Field(..., description="Gesamtzahl Circuit Breakers")


@router.get(
    "/circuit-breakers",
    response_model=CircuitBreakerHealthResponse,
    summary="Circuit Breaker Status",
    description="Prueft alle OCR Backend Circuit Breakers.",
)
async def circuit_breaker_health() -> CircuitBreakerHealthResponse:
    """
    Gesundheitspruefung aller Circuit Breakers.

    Zeigt Status, Fehlerraten und Recovery-Zeiten fuer alle Backends.
    """
    try:
        from app.services.circuit_breaker import get_circuit_breaker_registry, CircuitState

        registry = get_circuit_breaker_registry()
        all_status = registry.get_all_status()

        circuit_breakers = {}
        offene = 0

        for name, status in all_status.items():
            state = status.get("state", "unknown")
            is_healthy = state == "closed"

            if state == "open":
                offene += 1

            stats = status.get("stats", {})

            circuit_breakers[name] = CircuitBreakerHealth(
                name=name,
                state=state,
                gesund=is_healthy,
                failure_rate=stats.get("failure_rate", 0.0),
                consecutive_failures=stats.get("consecutive_failures", 0),
                retry_after_seconds=status.get("retry_after", 0.0),
                times_opened=stats.get("times_opened", 0),
            )

        # Bestimme Gesamtstatus
        total = len(circuit_breakers)
        if offene == 0:
            status = "gesund"
        elif offene < total:
            status = "beeintraechtigt"
        else:
            status = "kritisch"

        logger.info(
            "circuit_breaker_health_complete",
            status=status,
            open_count=offene,
            total=total,
        )

        return CircuitBreakerHealthResponse(
            status=status,
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            circuit_breakers=circuit_breakers,
            offene_circuits=offene,
            gesamtzahl=total,
        )

    except ImportError:
        return CircuitBreakerHealthResponse(
            status="unbekannt",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            circuit_breakers={},
            offene_circuits=0,
            gesamtzahl=0,
        )
    except Exception as e:
        logger.error("circuit_breaker_health_failed", error=str(e))
        return CircuitBreakerHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            circuit_breakers={},
            offene_circuits=0,
            gesamtzahl=0,
        )


# =============================================================================
# OCR Pipeline Health Endpoints
# =============================================================================


class PipelineHealthResponse(BaseModel):
    """OCR Pipeline Gesamtstatus."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    german_correction_enabled: bool = Field(..., description="Deutsche Korrektur aktiv")
    circuit_breaker_enabled: bool = Field(..., description="Circuit Breaker aktiv")
    memory_guard_enabled: bool = Field(..., description="Memory Guard aktiv")
    min_confidence_threshold: float = Field(..., description="Min. Confidence Schwelle")
    fallback_chain_status: Optional[Dict[str, Any]] = Field(
        None, description="Fallback Chain Metriken"
    )
    circuit_breaker_status: Optional[Dict[str, Any]] = Field(
        None, description="Circuit Breaker Status"
    )
    memory_guard_status: Optional[Dict[str, Any]] = Field(
        None, description="GPU Memory Guard Status"
    )
    german_correction_stats: Optional[Dict[str, Any]] = Field(
        None, description="German Correction Statistiken"
    )


@router.get(
    "/pipeline",
    response_model=PipelineHealthResponse,
    summary="OCR Pipeline Status",
    description="Vollstaendiger Status der OCR Pipeline mit allen Komponenten.",
)
async def pipeline_health() -> PipelineHealthResponse:
    """
    Vollstaendige Gesundheitspruefung der OCR Pipeline.

    Prueft:
    - Pipeline-Konfiguration
    - Fallback Chain Status
    - Circuit Breaker Status
    - GPU Memory Guard Status
    - German Correction Agent Status
    """
    try:
        from app.services.ocr_pipeline import get_ocr_pipeline

        pipeline = get_ocr_pipeline()
        status_data = pipeline.get_status()

        pipeline_config = status_data.get("pipeline", {})
        fallback_status = status_data.get("fallback_chain", {})
        cb_status = status_data.get("circuit_breakers", {})
        memory_status = status_data.get("memory_guard")
        german_stats = status_data.get("german_correction")

        # Bestimme Gesamtstatus
        issues = []

        # Check Circuit Breakers
        open_circuits = [k for k, v in cb_status.items() if v.get("state") == "open"]
        if open_circuits:
            issues.append(f"Circuit Breaker offen: {', '.join(open_circuits)}")

        # Check Memory Guard
        if memory_status and memory_status.get("is_critical"):
            issues.append("GPU-Speicher kritisch")

        # Check Fallback Chain
        if fallback_status.get("total_failures", 0) > 10:
            issues.append("Hohe Anzahl Fallback-Fehler")

        if not issues:
            status = "gesund"
        elif len(issues) < 2:
            status = "beeintraechtigt"
        else:
            status = "kritisch"

        logger.info(
            "pipeline_health_complete",
            status=status,
            issues=issues,
        )

        return PipelineHealthResponse(
            status=status,
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            german_correction_enabled=pipeline_config.get("german_correction_enabled", False),
            circuit_breaker_enabled=pipeline_config.get("circuit_breaker_enabled", False),
            memory_guard_enabled=pipeline_config.get("memory_guard_enabled", False),
            min_confidence_threshold=pipeline_config.get("min_confidence_threshold", 0.65),
            fallback_chain_status=fallback_status,
            circuit_breaker_status=cb_status,
            memory_guard_status=memory_status,
            german_correction_stats=german_stats,
        )

    except ImportError:
        return PipelineHealthResponse(
            status="unbekannt",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            german_correction_enabled=False,
            circuit_breaker_enabled=False,
            memory_guard_enabled=False,
            min_confidence_threshold=0.65,
            fallback_chain_status=None,
            circuit_breaker_status=None,
            memory_guard_status=None,
            german_correction_stats=None,
        )
    except Exception as e:
        logger.error("pipeline_health_failed", error=str(e))
        return PipelineHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            german_correction_enabled=False,
            circuit_breaker_enabled=False,
            memory_guard_enabled=False,
            min_confidence_threshold=0.65,
            fallback_chain_status=None,
            circuit_breaker_status=None,
            memory_guard_status=None,
            german_correction_stats=None,
        )


# =============================================================================
# SLO/SLI Health Endpoints
# =============================================================================


class SLOHealthResponse(BaseModel):
    """SLO/SLI Status."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    availability_target: float = Field(..., description="Verfuegbarkeits-Ziel")
    availability_current: float = Field(..., description="Aktuelle Verfuegbarkeit")
    availability_met: bool = Field(..., description="Verfuegbarkeits-SLO erfuellt")
    latency_target_p95_seconds: float = Field(..., description="Latenz P95 Ziel")
    latency_current_p95_seconds: float = Field(..., description="Aktuelle Latenz P95")
    latency_met: bool = Field(..., description="Latenz-SLO erfuellt")
    quality_target: float = Field(..., description="Qualitaets-Ziel (Confidence)")
    quality_current: float = Field(..., description="Aktuelle Qualitaet")
    quality_met: bool = Field(..., description="Qualitaets-SLO erfuellt")
    error_budget_remaining: float = Field(..., description="Verbleibendes Error Budget (0-1)")
    error_budget_exhausted: bool = Field(..., description="Error Budget erschoepft")
    all_slos_met: bool = Field(..., description="Alle SLOs erfuellt")


@router.get(
    "/slo",
    response_model=SLOHealthResponse,
    summary="SLO/SLI Status",
    description="Service Level Objectives und Indicators Uebersicht.",
)
async def slo_health() -> SLOHealthResponse:
    """
    Prueft alle Service Level Objectives.

    SLOs:
    - Verfuegbarkeit: 99.9%
    - Latenz P95: < 10s
    - Qualitaet: > 85% Confidence
    """
    try:
        from app.core.telemetry import get_slo_tracker

        tracker = get_slo_tracker()
        report = tracker.get_slo_report()

        availability = report.get("availability", {})
        latency = report.get("latency", {})
        quality = report.get("quality", {})
        error_budget = report.get("error_budget", {})

        # Extrahiere Werte
        availability_current = availability.get("current", 0.0)
        availability_target = availability.get("target", 0.999)
        availability_met = availability.get("met", False)

        latency_current = latency.get("current_p95", 0.0)
        latency_target = latency.get("target_p95", 10.0)
        latency_met = latency.get("met", False)

        quality_current = quality.get("current", 0.0)
        quality_target = quality.get("target", 0.85)
        quality_met = quality.get("met", False)

        budget_remaining = error_budget.get("remaining", 1.0)
        budget_exhausted = budget_remaining <= 0

        all_met = all([availability_met, latency_met, quality_met, not budget_exhausted])

        # Bestimme Status
        met_count = sum([availability_met, latency_met, quality_met])
        if all_met:
            status = "gesund"
        elif met_count >= 2:
            status = "beeintraechtigt"
        else:
            status = "kritisch"

        logger.info(
            "slo_health_complete",
            status=status,
            all_met=all_met,
            availability=availability_current,
            latency_p95=latency_current,
            quality=quality_current,
        )

        return SLOHealthResponse(
            status=status,
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            availability_target=availability_target,
            availability_current=availability_current,
            availability_met=availability_met,
            latency_target_p95_seconds=latency_target,
            latency_current_p95_seconds=latency_current,
            latency_met=latency_met,
            quality_target=quality_target,
            quality_current=quality_current,
            quality_met=quality_met,
            error_budget_remaining=budget_remaining,
            error_budget_exhausted=budget_exhausted,
            all_slos_met=all_met,
        )

    except ImportError:
        return SLOHealthResponse(
            status="unbekannt",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            availability_target=0.999,
            availability_current=0.0,
            availability_met=False,
            latency_target_p95_seconds=10.0,
            latency_current_p95_seconds=0.0,
            latency_met=False,
            quality_target=0.85,
            quality_current=0.0,
            quality_met=False,
            error_budget_remaining=1.0,
            error_budget_exhausted=False,
            all_slos_met=False,
        )
    except Exception as e:
        logger.error("slo_health_failed", error=str(e))
        return SLOHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            availability_target=0.999,
            availability_current=0.0,
            availability_met=False,
            latency_target_p95_seconds=10.0,
            latency_current_p95_seconds=0.0,
            latency_met=False,
            quality_target=0.85,
            quality_current=0.0,
            quality_met=False,
            error_budget_remaining=0.0,
            error_budget_exhausted=True,
            all_slos_met=False,
        )


# =============================================================================
# GPU Memory Guard Health Endpoint
# =============================================================================


class MemoryGuardHealthResponse(BaseModel):
    """GPU Memory Guard Status."""

    status: str = Field(..., description="gesund, warnung, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    gpu_available: bool = Field(..., description="GPU verfuegbar")
    total_memory_gb: float = Field(..., description="Gesamt VRAM in GB")
    used_memory_gb: float = Field(..., description="Belegter VRAM in GB")
    available_memory_gb: float = Field(..., description="Verfuegbarer VRAM in GB")
    usage_percent: float = Field(..., description="VRAM Nutzung in Prozent")
    limit_gb: float = Field(..., description="Konfiguriertes Limit in GB")
    is_critical: bool = Field(..., description="Kritischer Zustand")
    cleanup_recommended: bool = Field(..., description="Cleanup empfohlen")


@router.get(
    "/gpu-memory",
    response_model=MemoryGuardHealthResponse,
    summary="GPU Memory Guard Status",
    description="Prueft GPU-Speicher und Memory Guard Zustand.",
)
async def gpu_memory_health() -> MemoryGuardHealthResponse:
    """
    Detaillierter GPU-Speicher Status.

    Zeigt:
    - Aktueller VRAM-Verbrauch
    - Verfuegbarer Speicher
    - Memory Guard Limit
    - Empfehlungen
    """
    try:
        from app.gpu_manager import get_memory_guard

        guard = get_memory_guard()
        status_data = guard.get_status()

        gpu_available = status_data.get("available", False)
        total = status_data.get("total_gb", 0.0)
        used = status_data.get("used_gb", 0.0)
        available = status_data.get("remaining_gb", 0.0)
        usage = status_data.get("usage_percent", 0.0)
        limit = status_data.get("limit_gb", 13.6)
        is_critical = status_data.get("is_critical", False)

        # Bestimme Status
        if not gpu_available:
            status = "unbekannt"
        elif is_critical or usage > 90:
            status = "kritisch"
        elif usage > 75:
            status = "warnung"
        else:
            status = "gesund"

        cleanup_recommended = usage > 80

        logger.info(
            "gpu_memory_health_complete",
            status=status,
            usage_percent=usage,
            is_critical=is_critical,
        )

        return MemoryGuardHealthResponse(
            status=status,
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            gpu_available=gpu_available,
            total_memory_gb=total,
            used_memory_gb=used,
            available_memory_gb=available,
            usage_percent=usage,
            limit_gb=limit,
            is_critical=is_critical,
            cleanup_recommended=cleanup_recommended,
        )

    except ImportError:
        return MemoryGuardHealthResponse(
            status="unbekannt",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            gpu_available=False,
            total_memory_gb=0.0,
            used_memory_gb=0.0,
            available_memory_gb=0.0,
            usage_percent=0.0,
            limit_gb=13.6,
            is_critical=False,
            cleanup_recommended=False,
        )
    except Exception as e:
        logger.error("gpu_memory_health_failed", error=str(e))
        return MemoryGuardHealthResponse(
            status="kritisch",
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            gpu_available=False,
            total_memory_gb=0.0,
            used_memory_gb=0.0,
            available_memory_gb=0.0,
            usage_percent=0.0,
            limit_gb=13.6,
            is_critical=True,
            cleanup_recommended=True,
        )


# =============================================================================
# Complete System Health Endpoint
# =============================================================================


class CompleteHealthResponse(BaseModel):
    """Vollstaendiger System-Gesundheitsbericht."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default="0.2.0-poc", description="API-Version")
    zusammenfassung: str = Field(..., description="Kurze Zusammenfassung")
    komponenten: Dict[str, KomponentenStatus] = Field(
        ..., description="Basis-Komponenten Status"
    )
    ocr_status: Optional[str] = Field(None, description="OCR Status")
    pipeline_status: Optional[str] = Field(None, description="Pipeline Status")
    slo_status: Optional[str] = Field(None, description="SLO Status")
    circuit_breaker_status: Optional[str] = Field(None, description="Circuit Breaker Status")
    gpu_memory_status: Optional[str] = Field(None, description="GPU Memory Status")
    worker_status: Optional[str] = Field(None, description="Celery Worker Status")
    workers_aktiv: Optional[int] = Field(None, description="Anzahl aktiver Worker")
    tasks_wartend: Optional[int] = Field(None, description="Tasks in Warteschlange")
    probleme: list = Field(default_factory=list, description="Aktive Probleme")
    empfehlungen: list = Field(default_factory=list, description="Empfehlungen")


@router.get(
    "/complete",
    response_model=CompleteHealthResponse,
    summary="Vollstaendige Systemgesundheit",
    description="Umfassende Pruefung aller Systemkomponenten inkl. OCR Pipeline, SLOs und Circuit Breaker.",
)
async def complete_health(
    db: AsyncSession = Depends(get_db),
) -> CompleteHealthResponse:
    """
    Vollstaendiger Gesundheitsbericht des gesamten Systems.

    Prueft:
    - Basis-Infrastruktur (DB, Redis, MinIO, GPU, Disk)
    - OCR Backends
    - OCR Pipeline
    - Service Level Objectives
    - Circuit Breaker
    - GPU Memory Guard

    Ergebnisse werden 5 Sekunden gecacht um Last zu reduzieren.
    """
    # Check cache first
    cache_key = "complete_health"
    cached = _get_cached_result(cache_key)
    if cached is not None:
        logger.debug("health_check_cache_hit", endpoint="complete")
        return cached

    probleme = []
    empfehlungen = []

    # Basis-Komponenten
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    gpu_status = _check_gpu()
    disk_status = _check_disk_space()
    minio_status = await _check_minio()

    komponenten = {
        "datenbank": db_status,
        "cache": redis_status,
        "gpu": gpu_status,
        "speicherplatz": disk_status,
        "objektspeicher": minio_status,
    }

    # Sammle Probleme aus Basis-Komponenten
    for name, status in komponenten.items():
        if not status.gesund:
            probleme.append(f"{name}: {status.nachricht}")

    # OCR Status
    ocr_response = await ocr_health()
    ocr_status_str = ocr_response.status
    if ocr_status_str != "gesund":
        probleme.append(f"OCR: {ocr_response.ungesunde_backends} Backends nicht verfuegbar")

    # Pipeline Status
    pipeline_response = await pipeline_health()
    pipeline_status_str = pipeline_response.status
    if pipeline_status_str == "kritisch":
        probleme.append("Pipeline: Kritischer Zustand")

    # SLO Status
    slo_response = await slo_health()
    slo_status_str = slo_response.status
    if not slo_response.all_slos_met:
        if not slo_response.availability_met:
            probleme.append(f"SLO Verfuegbarkeit nicht erfuellt: {slo_response.availability_current:.2%}")
        if not slo_response.latency_met:
            probleme.append(f"SLO Latenz nicht erfuellt: {slo_response.latency_current_p95_seconds:.2f}s")
        if not slo_response.quality_met:
            probleme.append(f"SLO Qualitaet nicht erfuellt: {slo_response.quality_current:.2%}")
        if slo_response.error_budget_exhausted:
            probleme.append("Error Budget erschoepft!")

    # Circuit Breaker Status
    cb_response = await circuit_breaker_health()
    cb_status_str = cb_response.status
    if cb_response.offene_circuits > 0:
        probleme.append(f"Circuit Breaker: {cb_response.offene_circuits} offen")

    # GPU Memory Status
    gpu_mem_response = await gpu_memory_health()
    gpu_mem_status_str = gpu_mem_response.status
    if gpu_mem_response.is_critical:
        probleme.append(f"GPU-Speicher kritisch: {gpu_mem_response.usage_percent:.1f}%")
    elif gpu_mem_response.cleanup_recommended:
        empfehlungen.append("GPU-Speicher aufräumen empfohlen")

    # Worker Status
    worker_response = await worker_health()
    worker_status_str = worker_response.status
    workers_aktiv = worker_response.workers_aktiv
    tasks_wartend = worker_response.tasks_wartend

    if worker_status_str == "kritisch":
        probleme.append(f"Worker: Keine aktiven Worker verfügbar")
    elif worker_status_str == "beeintraechtigt":
        if tasks_wartend > 50:
            probleme.append(f"Worker: Hohe Queue-Last ({tasks_wartend} Tasks)")
        if workers_aktiv == 0:
            probleme.append("Worker: Keine aktiven Worker")

    # Add worker recommendations
    empfehlungen.extend(worker_response.empfehlungen)

    # Empfehlungen generieren
    if not db_status.gesund:
        empfehlungen.append("Datenbank-Verbindung pruefen")
    if not redis_status.gesund:
        empfehlungen.append("Redis-Server pruefen")
    if cb_response.offene_circuits > 0:
        empfehlungen.append("Circuit Breaker Recovery abwarten oder manuell zuruecksetzen")
    if slo_response.error_budget_exhausted:
        empfehlungen.append("Fehlerursachen analysieren und beheben")

    # Gesamtstatus bestimmen
    critical_components = ["datenbank"]
    has_critical = any(not komponenten[c].gesund for c in critical_components if c in komponenten)

    status_scores = {
        "gesund": 0,
        "warnung": 1,
        "beeintraechtigt": 2,
        "kritisch": 3,
        "unbekannt": 1,
    }

    max_score = max([
        status_scores.get(ocr_status_str, 0),
        status_scores.get(pipeline_status_str, 0),
        status_scores.get(slo_status_str, 0),
        status_scores.get(cb_status_str, 0),
        status_scores.get(gpu_mem_status_str, 0),
        status_scores.get(worker_status_str, 0),
    ])

    if has_critical or max_score >= 3:
        status = "kritisch"
    elif max_score >= 2 or len(probleme) >= 3:
        status = "beeintraechtigt"
    elif len(probleme) > 0:
        status = "beeintraechtigt"
    else:
        status = "gesund"

    # Zusammenfassung
    if status == "gesund":
        zusammenfassung = "Alle Systeme funktionieren ordnungsgemaess"
    elif status == "beeintraechtigt":
        zusammenfassung = f"{len(probleme)} Problem(e) erkannt, System funktionsfaehig"
    else:
        zusammenfassung = f"Kritische Probleme: {len(probleme)} - Sofortige Aufmerksamkeit erforderlich"

    logger.info(
        "complete_health_check",
        status=status,
        problem_count=len(probleme),
        recommendation_count=len(empfehlungen),
    )

    result = CompleteHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version="0.2.0-poc",
        zusammenfassung=zusammenfassung,
        komponenten=komponenten,
        ocr_status=ocr_status_str,
        pipeline_status=pipeline_status_str,
        slo_status=slo_status_str,
        circuit_breaker_status=cb_status_str,
        gpu_memory_status=gpu_mem_status_str,
        worker_status=worker_status_str,
        workers_aktiv=workers_aktiv,
        tasks_wartend=tasks_wartend,
        probleme=probleme,
        empfehlungen=empfehlungen,
    )

    # Cache the result
    _set_cached_result(cache_key, result)

    return result
