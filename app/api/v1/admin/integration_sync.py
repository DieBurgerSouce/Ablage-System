"""Integration Sync Admin API.

Admin-Endpunkte für DATEV Write-back und Lexware Bidirektional-Export.
"""

from datetime import date, datetime, time
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.api.dependencies import get_db, get_current_active_user, get_user_company_id_dep
from app.db.models import User

import structlog
logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/integration-sync", tags=["Integration Sync"])

# --- DATEV Writeback Schemas ---

class DATEVWritebackEntryRequest(BaseModel):
    """Eine Buchung für den DATEV-Writeback.

    Schemathesis-Fix (W1-004 #3): Leere Pflichtfelder ("" / betrag=false)
    liefen bis ``datetime.fromisoformat("")`` durch -> 500. Jetzt 422 via
    Pydantic-Constraints; belegdatum wird als ISO-Datum validiert.
    """
    document_id: str = Field(..., min_length=1, max_length=64)
    soll_konto: str = Field(..., min_length=1, max_length=9, pattern=r"^\d+$")
    haben_konto: str = Field(..., min_length=1, max_length=9, pattern=r"^\d+$")
    betrag: float = Field(..., gt=0)
    belegdatum: date  # ISO date (von Pydantic validiert)
    buchungstext: str = Field(..., min_length=1, max_length=200)
    belegnummer: Optional[str] = None
    steuerschluessel: Optional[str] = None
    kostenstelle: Optional[str] = None

class DATEVWritebackBatchRequest(BaseModel):
    kontenrahmen: str = "SKR03"
    berater_nummer: Optional[str] = None
    mandanten_nummer: Optional[str] = None
    entries: List[DATEVWritebackEntryRequest]

class DATEVBatchResponse(BaseModel):
    id: str
    status: str
    entry_count: int
    kontenrahmen: str
    created_at: str

# --- Lexware Export Schemas ---

class LexwareExportResponse(BaseModel):
    id: str
    export_type: str
    status: str
    record_count: int
    created_at: str

# --- DATEV Writeback Endpoints ---

@router.post("/datev/writeback", response_model=DATEVBatchResponse, status_code=201)
async def create_datev_writeback(
    body: DATEVWritebackBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Erstellt einen DATEV Writeback-Batch mit Buchungen."""
    from app.services.datev.datev_writeback_service import DATEVWritebackService, WritebackEntry

    service = DATEVWritebackService(db)
    batch = await service.create_batch(company_id, current_user.id, body.kontenrahmen)

    if body.berater_nummer:
        batch.berater_nummer = body.berater_nummer
    if body.mandanten_nummer:
        batch.mandanten_nummer = body.mandanten_nummer

    for e in body.entries:
        entry = WritebackEntry(
            document_id=e.document_id,
            soll_konto=e.soll_konto,
            haben_konto=e.haben_konto,
            betrag=Decimal(str(e.betrag)),
            belegdatum=datetime.combine(e.belegdatum, time.min),
            buchungstext=e.buchungstext,
            belegnummer=e.belegnummer,
            steuerschluessel=e.steuerschluessel,
            kostenstelle=e.kostenstelle,
        )
        await service.add_entry(batch.id, entry)

    await service.generate_csv(batch.id)
    return DATEVBatchResponse(
        id=batch.id, status=batch.status.value, entry_count=len(batch.entries),
        kontenrahmen=batch.kontenrahmen, created_at=batch.created_at.isoformat(),
    )

@router.get("/datev/writeback/{batch_id}/download")
async def download_datev_writeback(batch_id: str, db: AsyncSession = Depends(get_db),
                                    current_user: User = Depends(get_current_active_user)):
    """Laedt DATEV Writeback CSV herunter."""
    from app.services.datev.datev_writeback_service import DATEVWritebackService
    service = DATEVWritebackService(db)
    csv_content = await service.export_batch(batch_id)
    return Response(
        content=csv_content, media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=DATEV_Writeback_{batch_id}.csv"},
    )

@router.post("/datev/writeback/{batch_id}/confirm-import")
async def confirm_datev_import(batch_id: str, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_active_user)):
    """Bestätigt DATEV-Import eines Batches."""
    from app.services.datev.datev_writeback_service import DATEVWritebackService
    service = DATEVWritebackService(db)
    batch = await service.mark_imported(batch_id)
    return {"status": "ok", "message": "DATEV-Import bestätigt", "batch_id": batch.id}

@router.get("/datev/writeback", response_model=List[DATEVBatchResponse])
async def list_datev_writeback(limit: int = Query(20, ge=1, le=100),
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_active_user),
                                company_id: UUID = Depends(get_user_company_id_dep)):
    """Listet DATEV Writeback-Batches."""
    from app.services.datev.datev_writeback_service import DATEVWritebackService
    service = DATEVWritebackService(db)
    batches = await service.list_batches(str(company_id), limit)
    return [DATEVBatchResponse(
        id=b.id, status=b.status.value, entry_count=len(b.entries),
        kontenrahmen=b.kontenrahmen, created_at=b.created_at.isoformat(),
    ) for b in batches]

# --- Lexware Export Endpoints ---

@router.post("/lexware/export/{export_type}", response_model=LexwareExportResponse, status_code=201)
async def create_lexware_export(
    export_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
):
    """Erstellt Lexware-Export (customers, suppliers, payments)."""
    from app.services.lexware.lexware_export_service import LexwareExportService
    service = LexwareExportService(db)

    if export_type == "customers":
        job = await service.export_customers(company_id)
    elif export_type == "suppliers":
        job = await service.export_suppliers(company_id)
    elif export_type == "payments":
        job = await service.export_payment_status(company_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unbekannter Export-Typ: {export_type}")

    return LexwareExportResponse(
        id=job.id, export_type=job.export_type.value, status=job.status.value,
        record_count=job.record_count, created_at=job.created_at.isoformat(),
    )

@router.get("/lexware/export/{job_id}/download")
async def download_lexware_export(job_id: str, current_user: User = Depends(get_current_active_user)):
    """Laedt Lexware Export CSV herunter."""
    from app.services.lexware.lexware_export_service import LexwareExportService
    service = LexwareExportService(None)  # No DB needed for download
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export nicht gefunden")
    return Response(
        content=job.csv_content or "", media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=Lexware_{job.export_type.value}_{job.id}.csv"},
    )

@router.get("/lexware/exports", response_model=List[LexwareExportResponse])
async def list_lexware_exports(limit: int = Query(20, ge=1, le=100),
                                current_user: User = Depends(get_current_active_user),
                                company_id: UUID = Depends(get_user_company_id_dep)):
    """Listet Lexware-Exports."""
    from app.services.lexware.lexware_export_service import LexwareExportService
    service = LexwareExportService(None)
    jobs = service.list_jobs(str(company_id), limit)
    return [LexwareExportResponse(
        id=j.id, export_type=j.export_type.value, status=j.status.value,
        record_count=j.record_count, created_at=j.created_at.isoformat(),
    ) for j in jobs]
