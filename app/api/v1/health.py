# -*- coding: utf-8 -*-
"""
Health Check API Endpoints.

Detaillierte Gesundheitspruefungen fuer alle Systemkomponenten.
Feinpoliert und durchdacht - Enterprise Health Monitoring.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.config import settings

logger = structlog.get_logger(__name__)

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
    """Pruefe Redis-Verbindung."""
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
    description="Prueft alle Systemkomponenten: Datenbank, Redis, GPU, Speicher.",
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
    """
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

    return DetailedHealthResponse(
        status=status,
        zeitstempel=datetime.now(timezone.utc).isoformat(),
        version="0.2.0-poc",
        komponenten=komponenten,
        zusammenfassung=zusammenfassung,
    )


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
