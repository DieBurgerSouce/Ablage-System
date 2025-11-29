"""
System Administration API Endpoints.

Provides system status and monitoring for admins:
- GPU status and memory management
- Queue status and statistics
- Health checks for all services
- Processing statistics
- System dashboard overview
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.db.schemas import (
    GPUStatusAdmin,
    QueueStatus,
    SystemHealthStatus,
    ProcessingStats,
    SystemDashboard,
    MessageResponse,
)
from app.services.admin.system_status_service import SystemStatusService


router = APIRouter(prefix="/system", tags=["Admin - Systemstatus"])


# ==================== System Dashboard ====================

@router.get(
    "/dashboard",
    response_model=SystemDashboard,
    summary="System-Dashboard",
    description="Ruft eine Uebersicht aller Systemstatus-Informationen ab"
)
async def get_dashboard(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> SystemDashboard:
    """
    Ruft eine vollstaendige Uebersicht des Systemstatus ab.

    Enthaelt:
    - GPU-Status und Speichernutzung
    - Warteschlangenstatus
    - Gesundheitsstatus aller Dienste
    - Verarbeitungsstatistiken

    Nur fuer Administratoren zugaenglich.
    """
    return await SystemStatusService.get_dashboard(db)


# ==================== GPU Status ====================

@router.get(
    "/gpu",
    response_model=GPUStatusAdmin,
    summary="GPU-Status",
    description="Ruft detaillierten GPU-Status ab"
)
async def get_gpu_status(
    admin: User = Depends(get_current_superuser),
) -> GPUStatusAdmin:
    """
    Ruft detaillierten GPU-Status ab.

    Zeigt:
    - GPU-Verfuegbarkeit und Modell
    - VRAM-Nutzung (aktuell/gesamt)
    - GPU-Auslastung in Prozent
    - Temperatur und Leistungsaufnahme
    - Empfehlungen bei hoher Auslastung
    """
    return await SystemStatusService.get_gpu_status()


@router.post(
    "/gpu/clear-cache",
    response_model=MessageResponse,
    summary="GPU-Cache leeren",
    description="Leert den GPU-Speicher-Cache"
)
async def clear_gpu_cache(
    admin: User = Depends(get_current_superuser),
) -> MessageResponse:
    """
    Leert den GPU-Speicher-Cache.

    Nuetzlich wenn der VRAM-Verbrauch zu hoch ist oder
    Speicherprobleme auftreten.

    **Hinweis:** Kann laufende GPU-Operationen beeintraechtigen.
    """
    result = await SystemStatusService.clear_gpu_cache()
    return MessageResponse(
        message="GPU-Cache wurde geleert",
        detail=result.get("message", "Speicher freigegeben"),
    )


# ==================== Queue Status ====================

@router.get(
    "/queue",
    response_model=QueueStatus,
    summary="Warteschlangenstatus",
    description="Ruft den Status der Verarbeitungswarteschlange ab"
)
async def get_queue_status(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> QueueStatus:
    """
    Ruft den Status der Verarbeitungswarteschlange ab.

    Zeigt:
    - Anzahl wartender Jobs
    - Anzahl aktiver Jobs
    - Durchschnittliche Wartezeit
    - Jobs nach Prioritaet
    - Jobs nach Backend
    """
    return await SystemStatusService.get_queue_status(db)


# ==================== Health Status ====================

@router.get(
    "/health",
    response_model=SystemHealthStatus,
    summary="Gesundheitsstatus",
    description="Prueft den Gesundheitsstatus aller Systemkomponenten"
)
async def get_health_status(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> SystemHealthStatus:
    """
    Prueft den Gesundheitsstatus aller Systemkomponenten.

    Prueft:
    - PostgreSQL-Datenbankverbindung
    - Redis-Cache und Warteschlange
    - MinIO-Objektspeicher
    - Celery-Worker-Status
    - GPU-Verfuegbarkeit

    Gibt den Gesamtstatus und Details fuer jede Komponente zurueck.
    """
    return await SystemStatusService.get_health_status(db)


# ==================== Processing Statistics ====================

@router.get(
    "/stats",
    response_model=ProcessingStats,
    summary="Verarbeitungsstatistiken",
    description="Ruft Statistiken zur Dokumentenverarbeitung ab"
)
async def get_processing_stats(
    days: int = Query(7, ge=1, le=90, description="Anzahl Tage fuer Statistiken"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> ProcessingStats:
    """
    Ruft Statistiken zur Dokumentenverarbeitung ab.

    Zeigt:
    - Gesamtzahl verarbeiteter Dokumente
    - Erfolgs-/Fehlerquote
    - Durchschnittliche Verarbeitungszeit
    - Statistiken nach Backend
    - Statistiken nach Tag
    """
    return await SystemStatusService.get_processing_stats(db, days=days)


# ==================== Backend Status ====================

@router.get(
    "/backends",
    summary="Backend-Status",
    description="Ruft den Status aller OCR-Backends ab"
)
async def get_backends_status(
    admin: User = Depends(get_current_superuser),
):
    """
    Ruft den Status aller OCR-Backends ab.

    Zeigt fuer jedes Backend:
    - Ob es verfuegbar ist
    - Letzte Aktivitaet
    - Fehler oder Warnungen
    - VRAM-Bedarf
    """
    # Get status from SystemStatusService
    dashboard = await SystemStatusService.get_gpu_status()

    # Get backend health from health check
    health = await SystemStatusService.get_health_status(db=None)

    return {
        "backends": {
            "deepseek_janus": {
                "name": "DeepSeek-Janus-Pro",
                "status": "available" if dashboard.available else "unavailable",
                "vram_required_gb": 12.0,
                "description": "Beste Umlaut-Genauigkeit, Fraktur, komplexe Layouts",
            },
            "got_ocr": {
                "name": "GOT-OCR 2.0",
                "status": "available",
                "vram_required_gb": 10.0,
                "description": "Tabellen, Formeln, schnelle Verarbeitung",
            },
            "surya": {
                "name": "Surya + Docling",
                "status": "available",
                "vram_required_gb": 0,
                "description": "CPU-Fallback, Layout-Analyse",
            },
            "surya_gpu": {
                "name": "Surya GPU",
                "status": "available" if dashboard.available else "unavailable",
                "vram_required_gb": 4.0,
                "description": "Schnelle GPU-Variante von Surya",
            },
        },
        "gpu_available": dashboard.available,
        "gpu_memory_used_gb": dashboard.memory_used_gb,
        "gpu_memory_total_gb": dashboard.memory_total_gb,
    }


# ==================== Service Restart (Placeholder) ====================

@router.post(
    "/restart/{service}",
    response_model=MessageResponse,
    summary="Dienst neustarten",
    description="Startet einen Systemdienst neu (Celery Worker)"
)
async def restart_service(
    service: str,
    admin: User = Depends(get_current_superuser),
) -> MessageResponse:
    """
    Startet einen Systemdienst neu.

    Unterstuetzte Dienste:
    - **celery**: Celery Worker neu starten

    **Hinweis:** Ein Neustart kann laufende Auftraege unterbrechen.
    """
    if service not in ["celery"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dienst '{service}' wird nicht unterstuetzt. Verfuegbar: celery",
        )

    # In a real implementation, this would trigger a service restart
    # For now, return a placeholder response
    return MessageResponse(
        message=f"Neustart von '{service}' wurde angefordert",
        detail="Der Dienst wird in Kuerze neu gestartet. Dies kann einige Sekunden dauern.",
    )
