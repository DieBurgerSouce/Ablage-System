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
from app.core.german_messages import HTTPErrors
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
    description="Ruft eine Übersicht aller Systemstatus-Informationen ab"
)
async def get_dashboard(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> SystemDashboard:
    """
    Ruft eine vollständige Übersicht des Systemstatus ab.

    Enthält:
    - GPU-Status und Speichernutzung
    - Warteschlangenstatus
    - Gesundheitsstatus aller Dienste
    - Verarbeitungsstatistiken

    Nur für Administratoren zugänglich.
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
    - GPU-Verfügbarkeit und Modell
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

    Nützlich wenn der VRAM-Verbrauch zu hoch ist oder
    Speicherprobleme auftreten.

    **Hinweis:** Kann laufende GPU-Operationen beeinträchtigen.
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
    description="Prüft den Gesundheitsstatus aller Systemkomponenten"
)
async def get_health_status(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> SystemHealthStatus:
    """
    Prüft den Gesundheitsstatus aller Systemkomponenten.

    Prüft:
    - PostgreSQL-Datenbankverbindung
    - Redis-Cache und Warteschlange
    - MinIO-Objektspeicher
    - Celery-Worker-Status
    - GPU-Verfügbarkeit

    Gibt den Gesamtstatus und Details für jede Komponente zurück.
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
    days: int = Query(7, ge=1, le=90, description="Anzahl Tage für Statistiken"),
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

    Zeigt für jedes Backend:
    - Ob es verfügbar ist
    - Letzte Aktivität
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


# ==================== Service Restart ====================

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

    Unterstützte Dienste:
    - **celery**: Celery Worker neu starten

    **Hinweis:** Ein Neustart kann laufende Aufträge unterbrechen.
    """
    if service not in ["celery"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=HTTPErrors.SERVICE_NOT_SUPPORTED.format(service=service),
        )

    # M6: Ehrlicher Neustart statt Fake-Erfolg (Interface-Kontrakt M6).
    # G4 stellt den Worker-Control-Hook bereit:
    #   app/services/admin/worker_control_service.request_worker_restart(reason)
    #       -> WorkerRestartResult{performed: bool, mechanism: str, detail: str}
    # Solange der Hook NICHT verdrahtet ist (Service existiert noch nicht), antworten
    # wir ehrlich mit HTTP 501 statt einen erfolgreichen Neustart vorzutäuschen.
    import importlib

    restart_unsupported = HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Automatischer Neustart in dieser Umgebung nicht unterstützt",
    )

    try:
        # TODO(G4): worker_control_service bereitstellen (siehe Interface-Kontrakt M6)
        worker_control = importlib.import_module(
            "app.services.admin.worker_control_service"
        )
    except ModuleNotFoundError:
        raise restart_unsupported from None

    request_restart = getattr(worker_control, "request_worker_restart", None)
    if request_restart is None:
        raise restart_unsupported

    result = await request_restart(reason=f"Admin-Neustart angefordert: {service}")
    if not bool(getattr(result, "performed", False)):
        raise restart_unsupported

    return MessageResponse(
        message=f"Neustart von '{service}' wurde ausgeführt",
        detail=str(getattr(result, "detail", "Der Dienst wurde neu gestartet.")),
    )
