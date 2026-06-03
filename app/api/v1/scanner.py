"""Scanner API - Geraeteverwaltung und Scan-Aufträge."""

from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User
from app.services.scanner.scanner_service import (
    ScannerService, ScannerType, ScanResolution, ScanColorMode, ScanJobStatus
)

import structlog
from app.core.safe_errors import safe_error_detail
logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/scanner", tags=["Scanner"])

_scanner_service = ScannerService()

# --- Schemas ---

class ScannerRegisterRequest(BaseModel):
    id: str = Field(description="Eindeutige Scanner-ID")
    name: str = Field(description="Anzeigename")
    scanner_type: str = Field(description="wia, sane, network, webusb")
    model: Optional[str] = None
    location: Optional[str] = None
    has_adf: bool = False
    has_duplex: bool = False
    max_resolution: int = 600

class ScannerResponse(BaseModel):
    id: str
    name: str
    scanner_type: str
    model: Optional[str] = None
    location: Optional[str] = None
    has_adf: bool
    has_duplex: bool
    max_resolution: int
    is_online: bool
    last_seen: Optional[str] = None

class ScanJobRequest(BaseModel):
    scanner_id: str
    resolution: str = "300"
    color_mode: str = "color"
    use_adf: bool = False
    duplex: bool = False

class ScanJobResponse(BaseModel):
    id: str
    scanner_id: str
    status: str
    resolution: str
    color_mode: str
    use_adf: bool
    duplex: bool
    pages_scanned: int
    created_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    document_ids: List[str]

class ScanJobUpdateRequest(BaseModel):
    status: str
    pages_scanned: int = 0
    error_message: Optional[str] = None
    document_ids: Optional[List[str]] = None

# --- Endpoints ---

@router.get("/devices", response_model=List[ScannerResponse])
async def list_scanners(current_user: User = Depends(get_current_active_user)):
    """Listet alle registrierten Scanner-Geraete."""
    devices = _scanner_service.list_scanners()
    return [ScannerResponse(
        id=d.id, name=d.name, scanner_type=d.scanner_type.value,
        model=d.model, location=d.location, has_adf=d.has_adf,
        has_duplex=d.has_duplex, max_resolution=d.max_resolution,
        is_online=d.is_online,
        last_seen=d.last_seen.isoformat() if d.last_seen else None,
    ) for d in devices]

@router.post("/devices/register", response_model=ScannerResponse, status_code=201)
async def register_scanner(body: ScannerRegisterRequest, current_user: User = Depends(get_current_active_user)):
    """Registriert ein neues Scanner-Geraet."""
    from app.services.scanner.scanner_service import ScannerDevice
    device = ScannerDevice(
        id=body.id, name=body.name, scanner_type=ScannerType(body.scanner_type),
        model=body.model, location=body.location, has_adf=body.has_adf,
        has_duplex=body.has_duplex, max_resolution=body.max_resolution,
        is_online=True,
    )
    result = _scanner_service.register_scanner(device)
    return ScannerResponse(
        id=result.id, name=result.name, scanner_type=result.scanner_type.value,
        model=result.model, location=result.location, has_adf=result.has_adf,
        has_duplex=result.has_duplex, max_resolution=result.max_resolution,
        is_online=result.is_online, last_seen=None,
    )

@router.post("/devices/{scanner_id}/heartbeat")
async def scanner_heartbeat(scanner_id: str):
    """Scanner-Agent meldet sich als online."""
    if not _scanner_service.heartbeat(scanner_id):
        raise HTTPException(status_code=404, detail="Scanner nicht gefunden")
    return {"status": "ok"}

@router.delete("/devices/{scanner_id}")
async def unregister_scanner(scanner_id: str, current_user: User = Depends(get_current_active_user)):
    """Entfernt Scanner-Registrierung."""
    if not _scanner_service.unregister_scanner(scanner_id):
        raise HTTPException(status_code=404, detail="Scanner nicht gefunden")
    return {"status": "ok", "message": "Scanner wurde entfernt"}

@router.post("/jobs", response_model=ScanJobResponse, status_code=201)
async def create_scan_job(body: ScanJobRequest, current_user: User = Depends(get_current_active_user), company_id: UUID = Depends(get_user_company_id_dep)):
    """Erstellt einen neuen Scan-Auftrag."""
    try:
        job = _scanner_service.create_scan_job(
            scanner_id=body.scanner_id, company_id=company_id,
            user_id=current_user.id, resolution=ScanResolution(body.resolution),
            color_mode=ScanColorMode(body.color_mode), use_adf=body.use_adf,
            duplex=body.duplex,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Scanner"))
    return _job_to_response(job)

@router.get("/jobs", response_model=List[ScanJobResponse])
async def list_scan_jobs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Listet Scan-Aufträge."""
    jobs = _scanner_service.list_jobs(str(company_id), limit=limit)
    return [_job_to_response(j) for j in jobs]

@router.get("/jobs/{job_id}", response_model=ScanJobResponse)
async def get_scan_job(job_id: str, current_user: User = Depends(get_current_active_user)):
    """Liest einen Scan-Auftrag."""
    job = _scanner_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan-Auftrag nicht gefunden")
    return _job_to_response(job)

@router.put("/jobs/{job_id}/status", response_model=ScanJobResponse)
async def update_scan_job(job_id: str, body: ScanJobUpdateRequest):
    """Scanner-Agent aktualisiert Auftrag-Status."""
    job = _scanner_service.update_job_status(
        job_id=job_id, status=ScanJobStatus(body.status),
        pages_scanned=body.pages_scanned, error_message=body.error_message,
        document_ids=body.document_ids,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Scan-Auftrag nicht gefunden")
    return _job_to_response(job)

@router.delete("/jobs/{job_id}")
async def cancel_scan_job(job_id: str, current_user: User = Depends(get_current_active_user)):
    """Bricht Scan-Auftrag ab."""
    if not _scanner_service.cancel_job(job_id):
        raise HTTPException(status_code=400, detail="Auftrag kann nicht abgebrochen werden")
    return {"status": "ok", "message": "Scan-Auftrag abgebrochen"}

def _job_to_response(job) -> ScanJobResponse:
    return ScanJobResponse(
        id=job.id, scanner_id=job.scanner_id, status=job.status.value,
        resolution=job.resolution.value, color_mode=job.color_mode.value,
        use_adf=job.use_adf, duplex=job.duplex, pages_scanned=job.pages_scanned,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message, document_ids=job.document_ids,
    )
