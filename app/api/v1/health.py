# -*- coding: utf-8 -*-
"""
Health Check API Endpoints.

Detaillierte Gesundheitsprüfungen für alle Systemkomponenten.
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
from typing import Dict, List, Optional, Union

from app.core.types import JSONDict
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
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Health check cache configuration
HEALTH_CHECK_CACHE_TTL = 5  # 5 seconds TTL
HEALTH_CHECK_CACHE_MAXSIZE = 10  # Max cached entries

# Type alias for cacheable health check results (forward reference)
# Actual types defined below: BasicHealthResponse, DetailedHealthResponse, DependencyHealthResponse
CachedHealthResult = Union["BasicHealthResponse", "DetailedHealthResponse", "DependencyHealthResponse", Dict[str, object]]

# Thread-safe cache for health check results
if CACHETOOLS_AVAILABLE:
    _health_cache: TTLCache = TTLCache(
        maxsize=HEALTH_CHECK_CACHE_MAXSIZE,
        ttl=HEALTH_CHECK_CACHE_TTL
    )
    _health_cache_lock = threading.Lock()
else:
    _health_cache: Dict[str, CachedHealthResult] = {}
    _health_cache_lock = threading.Lock()


def _get_cached_result(cache_key: str) -> Optional[CachedHealthResult]:
    """Get cached health check result if available."""
    if not CACHETOOLS_AVAILABLE:
        return None

    with _health_cache_lock:
        return _health_cache.get(cache_key)


def _set_cached_result(cache_key: str, result: CachedHealthResult) -> None:
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
    details: Optional[JSONDict] = Field(None, description="Weitere Details")


class BasicHealthResponse(BaseModel):
    """Einfache Gesundheitsprüfung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default_factory=lambda: settings.APP_VERSION, description="API-Version")


class DetailedHealthResponse(BaseModel):
    """Detaillierte Gesundheitsprüfung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default_factory=lambda: settings.APP_VERSION, description="API-Version")
    komponenten: Dict[str, KomponentenStatus] = Field(
        ..., description="Status je Komponente"
    )
    zusammenfassung: str = Field(..., description="Kurze Zusammenfassung")


class DependencyHealthResponse(BaseModel):
    """Gesundheitsprüfung der Abhängigkeiten."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    datenbank: KomponentenStatus = Field(..., description="PostgreSQL-Status")
    cache: KomponentenStatus = Field(..., description="Redis-Status")
    speicher: KomponentenStatus = Field(..., description="MinIO-Status")
    vault: KomponentenStatus = Field(..., description="Vault-Status")


# =============================================================================
# Helper Functions
# =============================================================================


async def _check_database(db: AsyncSession) -> KomponentenStatus:
    """Prüfe Datenbank-Verbindung."""
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
        logger.error("health_check_database_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False,
            nachricht=f"Datenbank nicht erreichbar: {safe_error_detail(e, 'DB-Verbindung')}",
            latenz_ms=None,
        )


async def _check_redis() -> KomponentenStatus:
    """Prüfe Redis-Verbindung.

    Testet Verbindung zum Redis-Server via PING-Befehl.

    Returns:
        KomponentenStatus mit Latenz bei Erfolg

    Note:
        Erfordert redis.asyncio (optionale Abhängigkeit).
        Bei fehlendem Modul wird gesund=False zurückgegeben.
    """
    import time

    try:
        import redis.asyncio as redis

        start = time.perf_counter()
        # Kanonische URL nutzen (wie RedisStateManager): settings.REDIS_URL traegt die
        # In-Container-Adresse inkl. Passwort (z.B. redis://:***@redis:6379). Der frueher
        # aus REDIS_HOST:REDIS_PORT gebaute String zeigte auf die Host-Mapping
        # (localhost:6380) -> im Container nicht erreichbar -> faelschlich redis:false
        # -> /health/startup 503, obwohl die App via REDIS_URL laeuft.
        client = redis.from_url(
            # W2-04 / Redis-Probe: volle URL inkl. AUTH (Passwort) statt Host/Port;
            # Fallback auf Host/Port nur falls REDIS_URL leer ist (robuster als reines REDIS_URL)
            settings.REDIS_URL or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
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
        logger.error("health_check_redis_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"Redis nicht erreichbar: {safe_error_detail(e, 'Redis')}"
        )


def _check_gpu() -> KomponentenStatus:
    """Prüfe GPU-Verfügbarkeit."""
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            memory_total = torch.cuda.get_device_properties(0).total_memory
            memory_allocated = torch.cuda.memory_allocated(0)
            memory_percent = (memory_allocated / memory_total) * 100

            return KomponentenStatus(
                gesund=memory_percent < 85,
                nachricht=f"GPU verfügbar: {device_name}",
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
                nachricht="Keine GPU verfügbar - CPU-Modus aktiv",
                details={"cuda_verfügbar": False},
            )
    except ImportError:
        return KomponentenStatus(
            gesund=True,
            nachricht="PyTorch nicht installiert - CPU-Modus",
            details={"pytorch_installiert": False},
        )
    except Exception as e:
        logger.error("health_check_gpu_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"GPU-Prüfung fehlgeschlagen: {safe_error_detail(e, 'GPU')}"
        )


def _check_disk_space() -> KomponentenStatus:
    """Prüfe verfügbaren Speicherplatz."""
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
        logger.error("health_check_disk_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"Speicherplatz-Prüfung fehlgeschlagen: {safe_error_detail(e, 'Storage')}"
        )


def _check_ocr_models() -> KomponentenStatus:
    """Prüfe OCR-Modell-Verfügbarkeit."""
    try:
        from app.services.model_preloader import get_model_preloader

        preloader = get_model_preloader()
        status_info = preloader.get_status()

        if not status_info.get("enabled"):
            return KomponentenStatus(
                gesund=True,
                nachricht="Model-Preloading deaktiviert",
                details={"enabled": False},
            )

        models = status_info.get("models", {})
        summary = status_info.get("summary", {})
        loaded = summary.get("loaded", 0)
        total = summary.get("total", 0)
        failed = summary.get("failed", 0)

        model_details = {
            name: info.get("status", "unknown")
            for name, info in models.items()
        }

        if not status_info.get("preload_completed"):
            return KomponentenStatus(
                gesund=True,
                nachricht="Modelle werden noch geladen...",
                details={
                    "preload_completed": False,
                    "models": model_details,
                },
            )

        if failed > 0 and loaded == 0:
            return KomponentenStatus(
                gesund=False,
                nachricht=f"Kein OCR-Modell verfügbar ({failed} fehlgeschlagen)",
                details={"models": model_details, "summary": summary},
            )

        return KomponentenStatus(
            gesund=loaded > 0,
            nachricht=f"{loaded}/{total} OCR-Modelle geladen",
            details={"models": model_details, "summary": summary},
        )

    except ImportError:
        return KomponentenStatus(
            gesund=True,
            nachricht="Model-Preloader nicht verfügbar",
            details={"available": False},
        )
    except Exception as e:
        logger.error("health_check_ocr_models_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False,
            nachricht=f"OCR-Modell-Prüfung fehlgeschlagen: {safe_error_detail(e, 'OCR')}",
        )


async def _check_minio() -> KomponentenStatus:
    """Prüfe MinIO-Verbindung."""
    import time

    try:
        from minio import Minio

        start = time.perf_counter()
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        # List buckets als Health Check
        buckets = client.list_buckets()
        latenz = (time.perf_counter() - start) * 1000

        return KomponentenStatus(
            gesund=True,
            nachricht=f"MinIO erreichbar - {len(buckets)} Buckets",
            latenz_ms=round(latenz, 2),
            details={
                "endpoint": settings.MINIO_ENDPOINT,
                "buckets": len(buckets),
            },
        )
    except ImportError:
        return KomponentenStatus(
            gesund=False, nachricht="MinIO-Client nicht installiert"
        )
    except Exception as e:
        logger.error("health_check_minio_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"MinIO nicht erreichbar: {safe_error_detail(e, 'MinIO')}"
        )


def _check_vault() -> KomponentenStatus:
    """
    Prüfe Vault-Verbindung und -Konfiguration.

    Vault-Status:
    - "gesund": Vault aktiviert und verbunden, ODER Vault deaktiviert (nicht erforderlich)
    - "beeintraechtigt": Vault aktiviert aber nicht verbunden
    - "kritisch": Production UND Vault deaktiviert
    """
    try:
        from app.core.config.vault_client import VaultClient

        vault_client = VaultClient.get_instance()

        # Vault nicht aktiviert
        if not settings.VAULT_ENABLED:
            # In Production: KRITISCH
            if not settings.DEBUG:
                return KomponentenStatus(
                    gesund=False,
                    nachricht="Vault in Production deaktiviert - KRITISCH",
                    details={
                        "enabled": False,
                        "environment": "production",
                        "severity": "critical",
                    },
                )
            # In Development: OK
            return KomponentenStatus(
                gesund=True,
                nachricht="Vault deaktiviert (Development-Modus)",
                details={"enabled": False, "environment": "development"},
            )

        # Vault aktiviert - prüfe Verbindung
        if not vault_client.is_configured():
            return KomponentenStatus(
                gesund=False,
                nachricht="Vault aktiviert aber nicht konfiguriert",
                details={
                    "enabled": True,
                    "configured": False,
                },
            )

        if vault_client.is_healthy():
            return KomponentenStatus(
                gesund=True,
                nachricht="Vault verbunden und authentifiziert",
                details={
                    "enabled": True,
                    "connected": True,
                    "authenticated": True,
                    "address": vault_client.vault_addr,
                },
            )
        else:
            return KomponentenStatus(
                gesund=False,
                nachricht="Vault nicht verbunden",
                details={
                    "enabled": True,
                    "connected": False,
                },
            )

    except ImportError:
        # hvac nicht installiert
        if settings.VAULT_ENABLED:
            return KomponentenStatus(
                gesund=False,
                nachricht="Vault aktiviert aber hvac nicht installiert",
            )
        return KomponentenStatus(
            gesund=True,
            nachricht="Vault nicht verfügbar (hvac nicht installiert)",
            details={"enabled": False, "available": False},
        )
    except Exception as e:
        logger.error("health_check_vault_failed", **safe_error_log(e))
        return KomponentenStatus(
            gesund=False, nachricht=f"Vault-Prüfung fehlgeschlagen: {safe_error_detail(e, 'Vault')}"
        )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/",
    response_model=BasicHealthResponse,
    summary="Einfache Gesundheitsprüfung",
    description="Schnelle Prüfung ob API erreichbar ist.",
)
async def basic_health() -> BasicHealthResponse:
    """Einfache Gesundheitsprüfung - nur API-Erreichbarkeit."""
    return BasicHealthResponse(
        status="gesund",
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version=settings.APP_VERSION,
    )


@router.get(
    "/detailed",
    response_model=DetailedHealthResponse,
    summary="Detaillierte Gesundheitsprüfung",
    description="Prüft alle Systemkomponenten: Datenbank, Redis, GPU, Speicher. Ergebnisse werden 5 Sekunden gecacht.",
)
async def detailed_health(
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthResponse:
    """
    Detaillierte Gesundheitsprüfung aller Komponenten.

    Prüft:
    - PostgreSQL-Datenbank
    - Redis-Cache
    - GPU-Verfügbarkeit und -Speicher
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

    # Prüfe alle Komponenten
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    gpu_status = _check_gpu()
    disk_status = _check_disk_space()
    ocr_status = _check_ocr_models()
    vault_status = _check_vault()

    komponenten = {
        "datenbank": db_status,
        "cache": redis_status,
        "gpu": gpu_status,
        "speicherplatz": disk_status,
        "ocr_modelle": ocr_status,
        "vault": vault_status,
    }

    # Bestimme Gesamtstatus
    # Datenbank und Vault (in Production) sind kritisch
    kritische_komponenten = ["datenbank"]
    if not settings.DEBUG:  # Production
        kritische_komponenten.append("vault")

    kritisch = [k for k, v in komponenten.items() if not v.gesund and k in kritische_komponenten]
    beeintraechtigt = [k for k, v in komponenten.items() if not v.gesund and k not in kritische_komponenten]

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
        version=settings.APP_VERSION,
        komponenten=komponenten,
        zusammenfassung=zusammenfassung,
    )

    # Cache the result
    _set_cached_result(cache_key, result)

    return result


@router.get(
    "/dependencies",
    response_model=DependencyHealthResponse,
    summary="Abhängigkeiten prüfen",
    description="Prüft externe Abhängigkeiten: Datenbank, Redis, MinIO, Vault.",
)
async def check_dependencies(
    db: AsyncSession = Depends(get_db),
) -> DependencyHealthResponse:
    """
    Prüft nur externe Abhängigkeiten (Datenbank, Cache, Speicher, Vault).

    Nuetzlich für Kubernetes Readiness Probes.
    """
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    minio_status = await _check_minio()
    vault_status = _check_vault()

    # Vault ist in Production kritisch, sonst nur beeintraechtigt
    critical_deps = [db_status.gesund]
    if not settings.DEBUG:  # Production
        critical_deps.append(vault_status.gesund)

    degraded_deps = [redis_status.gesund, minio_status.gesund]
    if settings.DEBUG:  # In Development, Vault ist optional
        degraded_deps.append(vault_status.gesund)

    if all(critical_deps) and all(degraded_deps):
        status = "gesund"
    elif all(critical_deps):
        status = "beeintraechtigt"
    else:
        status = "kritisch"

    return DependencyHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        datenbank=db_status,
        cache=redis_status,
        speicher=minio_status,
        vault=vault_status,
    )


@router.get(
    "/models",
    summary="OCR-Modell-Status",
    description="Zeigt Verfügbarkeit und Ladezustand aller OCR-Modelle.",
)
async def model_health() -> JSONDict:
    """OCR-Modell-Verfügbarkeit prüfen."""
    ocr_status = _check_ocr_models()
    return {
        "status": "gesund" if ocr_status.gesund else "beeintraechtigt",
        "zeitstempel": datetime.now(timezone.utc).isoformat(),
        "ocr_modelle": {
            "gesund": ocr_status.gesund,
            "nachricht": ocr_status.nachricht,
            "details": ocr_status.details,
        },
    }


@router.get(
    "/live",
    summary="Liveness Probe",
    description="Kubernetes Liveness Probe - prüft nur ob API laeuft.",
)
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes Liveness Probe."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Kubernetes Readiness Probe - prüft Datenbank-Verbindung.",
)
async def readiness_probe(
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """Kubernetes Readiness Probe."""
    db_status = await _check_database(db)

    if not db_status.gesund:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datenbank nicht verfügbar",
        )

    return {"status": "ready", "datenbank": db_status.gesund}


@router.get(
    "/startup",
    summary="Startup Probe",
    description="Kubernetes Startup Probe - prüft ob Anwendung vollständig gestartet ist.",
)
async def startup_probe(
    db: AsyncSession = Depends(get_db),
) -> JSONDict:
    """
    Kubernetes Startup Probe.

    Prüft ob alle kritischen Komponenten beim Start bereit sind:
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
        errors.append("Datenbank nicht verfügbar")

    # Check Redis
    redis_status = await _check_redis()
    startup_checks["redis"] = redis_status.gesund
    if not redis_status.gesund:
        errors.append("Redis nicht verfügbar")

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
    """Prüfe Celery Worker Status."""
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
            logger.warning("celery_broker_check_failed", **safe_error_log(e))
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
            except Exception as e:
                logger.debug(
                    "queue_length_fetch_failed",
                    queue=queue_name,
                    error_type=type(e).__name__,
                )

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
            logger.warning("celery_inspect_failed", **safe_error_log(e))
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
            except Exception as e:
                logger.debug(
                    "gpu_memory_fetch_failed",
                    worker=worker_name,
                    error_type=type(e).__name__,
                )

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
        logger.warning("celery_not_available", **safe_error_log(e))
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
        logger.error("celery_worker_health_failed", **safe_error_log(e))
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
            empfehlungen=[f"Worker-Prüfung fehlgeschlagen: {safe_error_detail(e, 'Vorgang')}"],
        )


@router.get(
    "/workers",
    response_model=WorkerHealthResponse,
    summary="Celery Worker Status",
    description="Prüft alle Celery Worker, Queues und Task-Statistiken.",
)
async def worker_health() -> WorkerHealthResponse:
    """
    Detaillierte Gesundheitsprüfung der Celery Worker.

    Prüft:
    - Broker-Verbindung (Redis)
    - Aktive Worker und deren Status
    - Queue-Längen
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
    status: Optional[JSONDict] = Field(None, description="Backend-Status")


class OCRHealthResponse(BaseModel):
    """OCR Gesundheitsprüfung."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    gesamt_gesund: bool = Field(..., description="Mindestens ein Backend gesund")
    backends: Dict[str, OCRBackendHealth] = Field(..., description="Backend-Status")
    gesunde_backends: int = Field(..., description="Anzahl gesunder Backends")
    ungesunde_backends: int = Field(..., description="Anzahl ungesunder Backends")
    fallback_verfuegbar: bool = Field(..., description="CPU-Fallback verfügbar")
    empfohlenes_backend: Optional[str] = Field(None, description="Empfohlenes Backend")


@router.get(
    "/ocr",
    response_model=OCRHealthResponse,
    summary="OCR Backend Gesundheitsprüfung",
    description="Prüft alle OCR-Backends auf Verfügbarkeit und VRAM.",
)
async def ocr_health() -> OCRHealthResponse:
    """
    Detaillierte Gesundheitsprüfung aller OCR-Backends.

    Prüft:
    - DeepSeek-Janus-Pro (GPU)
    - GOT-OCR 2.0 (GPU)
    - Surya GPU (GPU)
    - Surya CPU (Fallback)

    Gibt Empfehlung für optimales Backend zurück.
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
        logger.error("ocr_health_check_failed", **safe_error_log(e))
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
    summary="Einzelnes OCR Backend prüfen",
    description="Prüft ein spezifisches OCR-Backend.",
)
async def ocr_backend_health(backend_name: str) -> OCRBackendHealth:
    """
    Gesundheitsprüfung für ein spezifisches OCR-Backend.

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
        logger.error("ocr_backend_health_check_failed", backend=backend_name, **safe_error_log(e))
        return OCRBackendHealth(
            gesund=False,
            grund=f"Prüfung fehlgeschlagen: {safe_error_detail(e, 'Vorgang')}",
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
    retry_after_seconds: float = Field(..., description="Sekunden bis Retry möglich")
    times_opened: int = Field(..., description="Wie oft geöffnet")


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
    description="Prüft alle OCR Backend Circuit Breakers.",
)
async def circuit_breaker_health() -> CircuitBreakerHealthResponse:
    """
    Gesundheitsprüfung aller Circuit Breakers.

    Zeigt Status, Fehlerraten und Recovery-Zeiten für alle Backends.
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
        logger.error("circuit_breaker_health_failed", **safe_error_log(e))
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
    fallback_chain_status: Optional[JSONDict] = Field(
        None, description="Fallback Chain Metriken"
    )
    circuit_breaker_status: Optional[JSONDict] = Field(
        None, description="Circuit Breaker Status"
    )
    memory_guard_status: Optional[JSONDict] = Field(
        None, description="GPU Memory Guard Status"
    )
    german_correction_stats: Optional[JSONDict] = Field(
        None, description="German Correction Statistiken"
    )


@router.get(
    "/pipeline",
    response_model=PipelineHealthResponse,
    summary="OCR Pipeline Status",
    description="Vollständiger Status der OCR Pipeline mit allen Komponenten.",
)
async def pipeline_health() -> PipelineHealthResponse:
    """
    Vollständige Gesundheitsprüfung der OCR Pipeline.

    Prüft:
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
        logger.error("pipeline_health_failed", **safe_error_log(e))
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
    availability_target: float = Field(..., description="Verfügbarkeits-Ziel")
    availability_current: float = Field(..., description="Aktuelle Verfügbarkeit")
    availability_met: bool = Field(..., description="Verfügbarkeits-SLO erfuellt")
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
    description="Service Level Objectives und Indicators Übersicht.",
)
async def slo_health() -> SLOHealthResponse:
    """
    Prüft alle Service Level Objectives.

    SLOs:
    - Verfügbarkeit: 99.9%
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
        logger.error("slo_health_failed", **safe_error_log(e))
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


class GPUStatusResponse(BaseModel):
    """GPU Verfügbarkeitsstatus für Frontend."""

    available: bool = Field(..., description="GPU verfügbar für OCR")
    name: Optional[str] = Field(None, description="GPU-Gerätename")
    memory_total_gb: Optional[float] = Field(None, description="Gesamt VRAM in GB")
    memory_used_gb: Optional[float] = Field(None, description="Belegter VRAM in GB")
    memory_free_gb: Optional[float] = Field(None, description="Freier VRAM in GB")
    utilization_percent: Optional[float] = Field(None, description="VRAM Nutzung in Prozent")


@router.get(
    "/gpu",
    response_model=GPUStatusResponse,
    summary="GPU Verfügbarkeitsstatus",
    description="Prüft ob GPU für OCR-Verarbeitung verfügbar ist.",
)
async def gpu_status() -> GPUStatusResponse:
    """
    GPU-Verfügbarkeitsstatus für Upload-Dialog.

    Gibt zurück:
    - available: true wenn CUDA-GPU vorhanden und nutzbar
    - name: GPU-Gerätename (z.B. 'NVIDIA RTX 4080')
    - memory_*: VRAM-Statistiken
    """
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            memory_total = torch.cuda.get_device_properties(0).total_memory
            memory_allocated = torch.cuda.memory_allocated(0)
            memory_free = memory_total - memory_allocated
            memory_percent = (memory_allocated / memory_total) * 100

            return GPUStatusResponse(
                available=True,
                name=device_name,
                memory_total_gb=round(memory_total / 1024**3, 2),
                memory_used_gb=round(memory_allocated / 1024**3, 2),
                memory_free_gb=round(memory_free / 1024**3, 2),
                utilization_percent=round(memory_percent, 1),
            )
        else:
            return GPUStatusResponse(
                available=False,
                name=None,
                memory_total_gb=None,
                memory_used_gb=None,
                memory_free_gb=None,
                utilization_percent=None,
            )
    except ImportError:
        # PyTorch nicht installiert
        return GPUStatusResponse(
            available=False,
            name=None,
            memory_total_gb=None,
            memory_used_gb=None,
            memory_free_gb=None,
            utilization_percent=None,
        )
    except Exception as e:
        logger.error("gpu_status_check_failed", **safe_error_log(e))
        return GPUStatusResponse(
            available=False,
            name=None,
            memory_total_gb=None,
            memory_used_gb=None,
            memory_free_gb=None,
            utilization_percent=None,
        )


class MemoryGuardHealthResponse(BaseModel):
    """GPU Memory Guard Status."""

    status: str = Field(..., description="gesund, warnung, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    gpu_available: bool = Field(..., description="GPU verfügbar")
    total_memory_gb: float = Field(..., description="Gesamt VRAM in GB")
    used_memory_gb: float = Field(..., description="Belegter VRAM in GB")
    available_memory_gb: float = Field(..., description="Verfügbarer VRAM in GB")
    usage_percent: float = Field(..., description="VRAM Nutzung in Prozent")
    limit_gb: float = Field(..., description="Konfiguriertes Limit in GB")
    is_critical: bool = Field(..., description="Kritischer Zustand")
    cleanup_recommended: bool = Field(..., description="Cleanup empfohlen")


@router.get(
    "/gpu-memory",
    response_model=MemoryGuardHealthResponse,
    summary="GPU Memory Guard Status",
    description="Prüft GPU-Speicher und Memory Guard Zustand.",
)
async def gpu_memory_health() -> MemoryGuardHealthResponse:
    """
    Detaillierter GPU-Speicher Status.

    Zeigt:
    - Aktueller VRAM-Verbrauch
    - Verfügbarer Speicher
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
        logger.error("gpu_memory_health_failed", **safe_error_log(e))
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
    """Vollständiger System-Gesundheitsbericht."""

    status: str = Field(..., description="gesund, beeintraechtigt, kritisch")
    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    version: str = Field(default_factory=lambda: settings.APP_VERSION, description="API-Version")
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
    summary="Vollständige Systemgesundheit",
    description="Umfassende Prüfung aller Systemkomponenten inkl. OCR Pipeline, SLOs und Circuit Breaker.",
)
async def complete_health(
    db: AsyncSession = Depends(get_db),
) -> CompleteHealthResponse:
    """
    Vollständiger Gesundheitsbericht des gesamten Systems.

    Prüft:
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
        probleme.append(f"OCR: {ocr_response.ungesunde_backends} Backends nicht verfügbar")

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
            probleme.append(f"SLO Verfügbarkeit nicht erfuellt: {slo_response.availability_current:.2%}")
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
        empfehlungen.append("Datenbank-Verbindung prüfen")
    if not redis_status.gesund:
        empfehlungen.append("Redis-Server prüfen")
    if cb_response.offene_circuits > 0:
        empfehlungen.append("Circuit Breaker Recovery abwarten oder manuell zurücksetzen")
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
        version=settings.APP_VERSION,
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


# =============================================================================
# System Information Endpoints
# =============================================================================


class SystemInfoResponse(BaseModel):
    """System-Informationen."""

    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    uptime_seconds: float = Field(..., description="Laufzeit in Sekunden")
    uptime_human: str = Field(..., description="Laufzeit lesbar")
    python_version: str = Field(..., description="Python Version")
    platform_name: str = Field(..., description="Betriebssystem")
    platform_version: str = Field(..., description="OS Version")
    architecture: str = Field(..., description="CPU Architektur")
    hostname: str = Field(..., description="Hostname")
    cpu_count: int = Field(..., description="CPU Kerne")
    api_version: str = Field(default_factory=lambda: settings.APP_VERSION, description="API Version")
    debug_mode: bool = Field(..., description="Debug Modus aktiv")
    environment: str = Field(..., description="Environment (dev/staging/prod)")


def _format_uptime(seconds: float) -> str:
    """Formatiere Uptime in lesbares Format."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


@router.get(
    "/system",
    response_model=SystemInfoResponse,
    summary="System-Informationen",
    description="Zeigt Systeminformationen wie Uptime, Versionen und Konfiguration.",
)
async def system_info() -> SystemInfoResponse:
    """
    System-Informationen Endpoint.

    Zeigt:
    - Uptime seit Start
    - Python und Betriebssystem Version
    - Hardware-Informationen
    - Konfiguration
    """
    import os

    uptime = time.time() - _startup_time
    env = getattr(settings, 'ENVIRONMENT', None) or "development"

    return SystemInfoResponse(
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(uptime, 2),
        uptime_human=_format_uptime(uptime),
        python_version=sys.version.split()[0],
        platform_name=platform.system(),
        platform_version=platform.release(),
        architecture=platform.machine(),
        hostname=platform.node(),
        cpu_count=os.cpu_count() or 1,
        api_version=settings.APP_VERSION,
        debug_mode=settings.DEBUG,
        environment=env,
    )


# =============================================================================
# Cache Statistics Endpoints
# =============================================================================


class CacheStatsResponse(BaseModel):
    """Cache-Statistiken."""

    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    redis_verfuegbar: bool = Field(..., description="Redis erreichbar")
    health_cache: JSONDict = Field(..., description="Health Check Cache Stats")
    ocr_cache: Optional[JSONDict] = Field(None, description="OCR Cache Stats")
    session_cache: Optional[JSONDict] = Field(None, description="Session Cache Stats")
    redis_info: Optional[JSONDict] = Field(None, description="Redis Server Info")


@router.get(
    "/cache",
    response_model=CacheStatsResponse,
    summary="Cache-Statistiken",
    description="Zeigt Cache-Statistiken für Health Checks, OCR und Sessions.",
)
async def cache_stats() -> CacheStatsResponse:
    """
    Cache-Statistiken Endpoint.

    Zeigt:
    - Health Check Cache Nutzung
    - OCR Cache Statistiken
    - Redis Server Informationen
    """
    # Health check cache stats
    health_cache_stats: JSONDict = {
        "cachetools_available": CACHETOOLS_AVAILABLE,
        "maxsize": HEALTH_CHECK_CACHE_MAXSIZE,
        "ttl_seconds": HEALTH_CHECK_CACHE_TTL,
    }

    if CACHETOOLS_AVAILABLE:
        with _health_cache_lock:
            health_cache_stats["current_size"] = len(_health_cache)
            health_cache_stats["cached_keys"] = list(_health_cache.keys())

    # OCR Cache stats
    ocr_cache_stats = None
    try:
        from app.services.ocr_cache_service import get_ocr_cache_service

        cache_service = get_ocr_cache_service()
        ocr_cache_stats = await cache_service.get_stats()
    except ImportError:
        pass
    except Exception as e:
        logger.warning("cache_stats_ocr_failed", **safe_error_log(e))
        ocr_cache_stats = {"error": safe_error_detail(e, "Vorgang")[:100]}

    # Redis info
    redis_verfuegbar = False
    redis_info = None

    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            decode_responses=True,
        )

        # Basic Redis info
        info = await client.info(section="memory")
        redis_verfuegbar = True

        redis_info = {
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
            "maxmemory_human": info.get("maxmemory_human", "unlimited"),
            "connected_clients": (await client.info(section="clients")).get("connected_clients", 0),
        }

        # Get key count by pattern
        try:
            db_info = await client.info(section="keyspace")
            if "db0" in db_info:
                redis_info["total_keys"] = db_info["db0"].get("keys", 0)
        except Exception as e:
            logger.debug(
                "redis_keyspace_info_failed",
                error_type=type(e).__name__,
            )

        await client.close()

    except ImportError:
        redis_info = {"error": "Redis Client nicht installiert"}
    except Exception as e:
        logger.warning("cache_stats_redis_failed", **safe_error_log(e))
        redis_info = {"error": safe_error_detail(e, "Vorgang")[:100]}

    # Session cache stats
    session_cache_stats = None
    try:
        from app.core.session_store import get_session_stats

        session_cache_stats = get_session_stats()
    except ImportError:
        pass  # Module not installed
    except Exception as e:
        logger.debug(
            "session_cache_stats_failed",
            error_type=type(e).__name__,
        )

    return CacheStatsResponse(
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        redis_verfuegbar=redis_verfuegbar,
        health_cache=health_cache_stats,
        ocr_cache=ocr_cache_stats,
        session_cache=session_cache_stats,
        redis_info=redis_info,
    )


# =============================================================================
# Model Preloader Status Endpoint
# =============================================================================


class ModelPreloaderResponse(BaseModel):
    """Model Preloader Status."""

    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    enabled: bool = Field(..., description="Preloading aktiviert")
    preload_started: bool = Field(..., description="Preloading gestartet")
    preload_completed: bool = Field(..., description="Preloading abgeschlossen")
    models: Dict[str, str] = Field(..., description="Model Status (model -> status)")
    summary: Dict[str, int] = Field(..., description="Zusammenfassung")
    load_times: Optional[Dict[str, float]] = Field(None, description="Ladezeiten in Sekunden")
    errors: Optional[Dict[str, str]] = Field(None, description="Fehler pro Model")


@router.get(
    "/models",
    response_model=ModelPreloaderResponse,
    summary="Model Preloader Status",
    description="Zeigt Status aller vorgeladenen OCR-Modelle.",
)
async def model_preloader_status() -> ModelPreloaderResponse:
    """
    Model Preloader Status Endpoint.

    Zeigt:
    - Welche Modelle vorgeladen werden
    - Status jedes Modells (pending, loading, loaded, failed, skipped)
    - Ladezeiten
    - Fehler falls aufgetreten
    """
    try:
        from app.services.model_preloader import get_model_preloader

        preloader = get_model_preloader()
        status_data = preloader.get_status()

        return ModelPreloaderResponse(
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            enabled=status_data.get("enabled", False),
            preload_started=status_data.get("preload_started", False),
            preload_completed=status_data.get("preload_completed", False),
            models=status_data.get("models", {}),
            summary=status_data.get("summary", {"total": 0, "loaded": 0, "failed": 0, "skipped": 0}),
            load_times=status_data.get("load_times"),
            errors=status_data.get("errors"),
        )

    except ImportError:
        return ModelPreloaderResponse(
            zeitstempel=datetime.now(timezone.utc).isoformat(),
            enabled=False,
            preload_started=False,
            preload_completed=False,
            models={},
            summary={"total": 0, "loaded": 0, "failed": 0, "skipped": 0},
            load_times=None,
            errors={"_": "Model Preloader nicht verfügbar"},
        )


# =============================================================================
# Parallel Health Check Helper
# =============================================================================


async def _run_parallel_health_checks(
    db: AsyncSession,
) -> Dict[str, KomponentenStatus]:
    """
    Führe alle Basis-Health-Checks parallel aus.

    Verbessert die Response-Zeit erheblich bei mehreren Checks.
    """
    # Define all check coroutines
    async def check_db() -> tuple[str, KomponentenStatus]:
        return "datenbank", await _check_database(db)

    async def check_redis_wrap() -> tuple[str, KomponentenStatus]:
        return "cache", await _check_redis()

    async def check_minio_wrap() -> tuple[str, KomponentenStatus]:
        return "objektspeicher", await _check_minio()

    def check_gpu_sync() -> tuple[str, KomponentenStatus]:
        return "gpu", _check_gpu()

    def check_disk_sync() -> tuple[str, KomponentenStatus]:
        return "speicherplatz", _check_disk_space()

    # Run async checks in parallel
    async_results = await asyncio.gather(
        check_db(),
        check_redis_wrap(),
        check_minio_wrap(),
        return_exceptions=True,
    )

    # Run sync checks (GPU, disk)
    sync_results = [check_gpu_sync(), check_disk_sync()]

    # Combine results
    komponenten: Dict[str, KomponentenStatus] = {}

    for result in list(async_results) + sync_results:
        if isinstance(result, Exception):
            logger.error("parallel_health_check_error", error=str(result))
            continue
        if isinstance(result, tuple) and len(result) == 2:
            name, status = result
            komponenten[name] = status

    return komponenten


@router.get(
    "/detailed/fast",
    response_model=DetailedHealthResponse,
    summary="Schnelle detaillierte Gesundheitsprüfung",
    description="Führt alle Health-Checks parallel aus für schnellere Antwortzeit.",
)
async def detailed_health_fast(
    db: AsyncSession = Depends(get_db),
) -> DetailedHealthResponse:
    """
    Detaillierte Gesundheitsprüfung mit paralleler Ausführung.

    Gleiche Prüfungen wie /detailed, aber alle Checks laufen parallel
    für bessere Performance bei hoher Last.
    """
    # Check cache first
    cache_key = "detailed_health_fast"
    cached = _get_cached_result(cache_key)
    if cached is not None:
        logger.debug("health_check_cache_hit", endpoint="detailed_fast")
        return cached

    # Run all checks in parallel
    komponenten = await _run_parallel_health_checks(db)

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
        "health_check_fast_complete",
        status=status,
        komponenten={k: v.gesund for k, v in komponenten.items()},
    )

    result = DetailedHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version=settings.APP_VERSION,
        komponenten=komponenten,
        zusammenfassung=zusammenfassung,
    )

    # Cache the result
    _set_cached_result(cache_key, result)

    return result


# =============================================================================
# Degradation Status Endpoint
# =============================================================================


class DegradationStatusResponse(BaseModel):
    """Degradation Status - zeigt ob System im eingeschraenkten Modus laeuft."""

    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    degraded: bool = Field(..., description="System laeuft eingeschraenkt")
    degradation_reasons: List[str] = Field(..., description="Gruende für Einschränkung")
    available_features: Dict[str, bool] = Field(..., description="Verfügbare Features")
    unavailable_features: List[str] = Field(..., description="Nicht verfügbare Features")
    recovery_actions: List[str] = Field(..., description="Empfohlene Recovery-Aktionen")


# =============================================================================
# FAANG-AUDIT FIX: Permission Cache Health Endpoint
# =============================================================================


class PermissionCacheHealthResponse(BaseModel):
    """Permission Cache Gesundheitsstatus - FAANG-AUDIT FIX."""

    zeitstempel: str = Field(..., description="ISO-Zeitstempel")
    status: str = Field(..., description="gesund, warnung, kritisch")
    redis_available: bool = Field(..., description="Redis für Permission-Cache erreichbar")
    fallback_active: bool = Field(..., description="In-Memory Fallback aktiv (Warnung bei Multi-Worker!)")
    cache_type: str = Field(..., description="Aktueller Cache-Typ (redis oder in-memory)")
    warning_message: Optional[str] = Field(None, description="Warnung falls Fallback aktiv")
    multi_worker_safe: bool = Field(..., description="Sicher für Multi-Worker-Deployment")


@router.get(
    "/permission-cache",
    response_model=PermissionCacheHealthResponse,
    summary="Permission Cache Status (FAANG-AUDIT)",
    description="Prüft ob Permission-Cache Redis verwendet oder im unsicheren In-Memory Fallback laeuft.",
)
async def permission_cache_health(
    db: AsyncSession = Depends(get_db),
) -> PermissionCacheHealthResponse:
    """
    FAANG-AUDIT FIX: Prüft den Permission-Cache Status.

    Bei Multi-Worker-Deployments MUSS Redis verfügbar sein, sonst
    können Permission-Updates zwischen Workern inkonsistent sein.

    Returns:
        - status: gesund (Redis aktiv) oder warnung (Fallback aktiv)
        - redis_available: Ob Redis erreichbar ist
        - fallback_active: Ob In-Memory Fallback verwendet wird
        - multi_worker_safe: Ob Setup für Multi-Worker sicher ist
    """
    from app.services.permission_service import PermissionService

    # Create a temporary service instance to check status
    service = PermissionService(db)

    # Try to get redis client to check if it's available
    redis_client = await service._get_redis_client()
    redis_available = redis_client is not None
    fallback_active = service._redis_fallback_mode

    if redis_available and not fallback_active:
        status = "gesund"
        cache_type = "redis"
        warning_message = None
        multi_worker_safe = True
    else:
        status = "warnung"
        cache_type = "in-memory"
        warning_message = (
            "WARNUNG: Permission-Cache laeuft im In-Memory Fallback-Modus. "
            "Bei Multi-Worker-Deployment können Permission-Updates "
            "zwischen Workern bis zu 30 Sekunden inkonsistent sein! "
            "Dies ist ein Sicherheitsrisiko."
        )
        multi_worker_safe = False

    logger.info(
        "permission_cache_health_check",
        status=status,
        redis_available=redis_available,
        fallback_active=fallback_active,
        multi_worker_safe=multi_worker_safe,
    )

    return PermissionCacheHealthResponse(
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        status=status,
        redis_available=redis_available,
        fallback_active=fallback_active,
        cache_type=cache_type,
        warning_message=warning_message,
        multi_worker_safe=multi_worker_safe,
    )


@router.get(
    "/degradation",
    response_model=DegradationStatusResponse,
    summary="Degradation Status",
    description="Zeigt ob und warum das System im eingeschraenkten Modus laeuft.",
)
async def degradation_status(
    db: AsyncSession = Depends(get_db),
) -> DegradationStatusResponse:
    """
    Prüft ob das System im Degradation Mode laeuft.

    Nuetzlich für:
    - Feature-Flags basierend auf Systemzustand
    - Automatische Fallback-Aktivierung
    - User-Benachrichtigungen
    """
    degradation_reasons: List[str] = []
    unavailable_features: List[str] = []
    recovery_actions: List[str] = []

    available_features = {
        "ocr_gpu": True,
        "ocr_cpu": True,
        "document_upload": True,
        "document_search": True,
        "user_auth": True,
        "batch_processing": True,
        "real_time_processing": True,
    }

    # Check GPU
    gpu_status = _check_gpu()
    if not gpu_status.gesund:
        available_features["ocr_gpu"] = False
        unavailable_features.append("GPU-basierte OCR")
        degradation_reasons.append("GPU nicht verfügbar oder Speicher kritisch")
        recovery_actions.append("GPU-Speicher freigeben oder System neustarten")

    # Check Database
    db_status = await _check_database(db)
    if not db_status.gesund:
        available_features["document_upload"] = False
        available_features["document_search"] = False
        available_features["user_auth"] = False
        unavailable_features.extend(["Dokumenten-Upload", "Suche", "Authentifizierung"])
        degradation_reasons.append("Datenbank nicht erreichbar")
        recovery_actions.append("Datenbank-Verbindung prüfen")

    # Check Redis
    redis_status = await _check_redis()
    if not redis_status.gesund:
        available_features["batch_processing"] = False
        available_features["real_time_processing"] = False
        unavailable_features.extend(["Batch-Verarbeitung", "Echtzeit-Verarbeitung"])
        degradation_reasons.append("Redis/Task-Queue nicht erreichbar")
        recovery_actions.append("Redis-Server prüfen und ggf. neustarten")

    # Check Circuit Breakers
    try:
        from app.services.circuit_breaker import get_circuit_breaker_registry


        registry = get_circuit_breaker_registry()
        all_status = registry.get_all_status()
        open_circuits = [k for k, v in all_status.items() if v.get("state") == "open"]

        if open_circuits:
            degradation_reasons.append(f"Circuit Breaker offen: {', '.join(open_circuits)}")
            recovery_actions.append("Warten auf Circuit Breaker Recovery (automatisch)")
    except ImportError:
        pass

    # Check Disk Space
    disk_status = _check_disk_space()
    if not disk_status.gesund:
        available_features["document_upload"] = False
        unavailable_features.append("Dokumenten-Upload (Speicherplatz)")
        degradation_reasons.append("Speicherplatz kritisch")
        recovery_actions.append("Speicherplatz freigeben")

    degraded = len(degradation_reasons) > 0

    return DegradationStatusResponse(
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        degraded=degraded,
        degradation_reasons=degradation_reasons,
        available_features=available_features,
        unavailable_features=unavailable_features,
        recovery_actions=recovery_actions,
    )
