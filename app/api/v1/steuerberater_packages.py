# -*- coding: utf-8 -*-
"""
Steuerberater Package API Endpoints.

Vision 2026 Q4: DATEV Export mit Steuerberater-Freigabe-Workflow.

Endpoints:
- GET    /steuerberater/packages           - Pakete auflisten
- POST   /steuerberater/packages           - Neues Paket erstellen
- GET    /steuerberater/packages/{id}      - Paket-Details
- DELETE /steuerberater/packages/{id}      - Paket löschen
- POST   /steuerberater/packages/{id}/submit        - Zur Prüfung einreichen
- POST   /steuerberater/packages/{id}/approve       - Genehmigen
- POST   /steuerberater/packages/{id}/reject        - Ablehnen
- POST   /steuerberater/packages/{id}/export        - Als ZIP exportieren
- GET    /steuerberater/packages/{id}/documents     - Dokumente im Paket
- POST   /steuerberater/packages/{id}/documents     - Dokument hinzufügen
- DELETE /steuerberater/packages/{id}/documents/{doc_id} - Dokument entfernen
- GET    /steuerberater/packages/{id}/validation    - Validierung prüfen
"""


from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_current_admin_user, get_user_company_id_dep
from app.core.rate_limiting import limiter
from app.core.security import build_content_disposition
from app.db.models import User
from app.services.datev.steuerberater_package_service import (
    get_steuerberater_package_service,
    PackageStatus,
    SteuerberaterPackage,
    PackageDocument,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/steuerberater", tags=["Steuerberater Packages"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class PackageDocumentResponse(BaseModel):
    """Ein Dokument im Steuerberater-Paket."""
    document_id: str = Field(..., description="Dokument-ID")
    document_type: str = Field(..., description="Dokumenttyp")
    belegdatum: Optional[str] = Field(None, description="Belegdatum")
    belegnummer: Optional[str] = Field(None, description="Belegnummer")
    betrag: Optional[float] = Field(None, description="Betrag")
    lieferant_kunde: Optional[str] = Field(None, description="Lieferant/Kunde")
    buchungstext: Optional[str] = Field(None, description="Buchungstext")
    konto_soll: Optional[str] = Field(None, description="Soll-Konto")
    konto_haben: Optional[str] = Field(None, description="Haben-Konto")
    kostenstelle: Optional[str] = Field(None, description="Kostenstelle")
    has_belegbild: bool = Field(default=False, description="Belegbild vorhanden")
    validation_errors: List[str] = Field(default=[], description="Validierungsfehler")


class PackageResponse(BaseModel):
    """Ein Steuerberater-Paket."""
    id: str = Field(..., description="Paket-ID")
    name: str = Field(..., description="Name")
    description: Optional[str] = Field(None, description="Beschreibung")
    status: str = Field(..., description="Status")
    period_from: str = Field(..., description="Periode von")
    period_to: str = Field(..., description="Periode bis")
    document_count: int = Field(default=0, description="Anzahl Dokumente")
    total_amount: float = Field(default=0.0, description="Gesamtbetrag")
    created_by_name: Optional[str] = Field(None, description="Erstellt von")
    created_at: str = Field(..., description="Erstellt am")
    submitted_at: Optional[str] = Field(None, description="Eingereicht am")
    approved_at: Optional[str] = Field(None, description="Genehmigt am")
    approved_by_name: Optional[str] = Field(None, description="Genehmigt von")
    exported_at: Optional[str] = Field(None, description="Exportiert am")
    is_valid: bool = Field(default=True, description="Valide für Export")
    validation_error_count: int = Field(default=0, description="Anzahl Validierungsfehler")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "pkg-2026-01-001",
            "name": "Januar 2026",
            "description": "Monatsabschluss Januar",
            "status": "draft",
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
            "document_count": 42,
            "total_amount": 15234.50,
            "created_by_name": "Max Mustermann",
            "created_at": "2026-01-28T10:00:00Z",
            "is_valid": True,
            "validation_error_count": 0,
        }
    })


class PackageListResponse(BaseModel):
    """Liste von Paketen."""
    packages: List[PackageResponse] = Field(..., description="Pakete")
    total_count: int = Field(..., description="Gesamtanzahl")
    by_status: Dict[str, int] = Field(default_factory=dict, description="Nach Status")


class PackageCreateRequest(BaseModel):
    """Request zum Erstellen eines Pakets."""
    name: str = Field(..., min_length=1, max_length=100, description="Name")
    description: Optional[str] = Field(None, max_length=500, description="Beschreibung")
    period_from: date = Field(..., description="Periode von")
    period_to: date = Field(..., description="Periode bis")
    auto_populate: bool = Field(
        default=True, description="Automatisch mit Dokumenten füllen"
    )


class PackageCreateResponse(BaseModel):
    """Response nach Paket-Erstellung."""
    success: bool = Field(..., description="Erfolgreich erstellt")
    package_id: str = Field(..., description="Paket-ID")
    document_count: int = Field(default=0, description="Automatisch hinzugefügte Dokumente")
    message: str = Field(..., description="Nachricht")


class DocumentAddRequest(BaseModel):
    """Request zum Hinzufügen eines Dokuments."""
    document_id: UUID = Field(..., description="Dokument-ID")
    buchungstext: Optional[str] = Field(None, max_length=60, description="Buchungstext")
    konto_soll: Optional[str] = Field(None, max_length=10, description="Soll-Konto")
    konto_haben: Optional[str] = Field(None, max_length=10, description="Haben-Konto")
    kostenstelle: Optional[str] = Field(None, max_length=10, description="Kostenstelle")


class SubmitReviewRequest(BaseModel):
    """Request zum Einreichen zur Prüfung."""
    message: Optional[str] = Field(None, max_length=500, description="Nachricht an Prüfer")


class ApproveRejectRequest(BaseModel):
    """Request zum Genehmigen/Ablehnen."""
    comment: Optional[str] = Field(None, max_length=500, description="Kommentar")


class ValidationResultResponse(BaseModel):
    """Validierungsergebnis eines Pakets."""
    is_valid: bool = Field(..., description="Paket valide")
    total_documents: int = Field(..., description="Gesamtanzahl Dokumente")
    valid_documents: int = Field(..., description="Valide Dokumente")
    invalid_documents: int = Field(..., description="Invalide Dokumente")
    errors: List[JSONDict] = Field(default=[], description="Fehler")
    warnings: List[JSONDict] = Field(default=[], description="Warnungen")


# =============================================================================
# Helper Functions
# =============================================================================

def _package_to_response(pkg: SteuerberaterPackage) -> PackageResponse:
    """Konvertiert Package zu Response-Schema."""
    return PackageResponse(
        id=str(pkg.id),
        name=pkg.name,
        description=pkg.description,
        status=pkg.status.value,
        period_from=pkg.period_from.isoformat(),
        period_to=pkg.period_to.isoformat(),
        document_count=pkg.document_count,
        total_amount=float(pkg.total_amount),
        created_by_name=pkg.created_by_name,
        created_at=pkg.created_at.isoformat(),
        submitted_at=pkg.submitted_at.isoformat() if pkg.submitted_at else None,
        approved_at=pkg.approved_at.isoformat() if pkg.approved_at else None,
        approved_by_name=pkg.approved_by_name,
        exported_at=pkg.exported_at.isoformat() if pkg.exported_at else None,
        is_valid=pkg.is_valid,
        validation_error_count=pkg.validation_error_count,
    )


def _document_to_response(doc: PackageDocument) -> PackageDocumentResponse:
    """Konvertiert PackageDocument zu Response-Schema."""
    return PackageDocumentResponse(
        document_id=str(doc.document_id),
        document_type=doc.document_type,
        belegdatum=doc.belegdatum.isoformat() if doc.belegdatum else None,
        belegnummer=doc.belegnummer,
        betrag=float(doc.betrag) if doc.betrag else None,
        lieferant_kunde=doc.lieferant_kunde,
        buchungstext=doc.buchungstext,
        konto_soll=doc.konto_soll,
        konto_haben=doc.konto_haben,
        kostenstelle=doc.kostenstelle,
        has_belegbild=doc.has_belegbild,
        validation_errors=doc.validation_errors,
    )


# =============================================================================
# Package CRUD Endpoints
# =============================================================================

@router.get(
    "/packages",
    response_model=PackageListResponse,
    summary="Pakete auflisten",
    description="Listet alle Steuerberater-Pakete auf.",
)
@limiter.limit("30/minute")
async def list_packages(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
    status_filter: Optional[str] = Query(None, description="Filter nach Status"),
    page: int = Query(1, ge=1, description="Seite"),
    page_size: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
) -> PackageListResponse:
    """
    Listet alle Steuerberater-Pakete auf.

    Unterstützt Filterung nach Status:
    - draft: Entwurf
    - pending_review: Zur Prüfung eingereicht
    - approved: Genehmigt
    - exported: Exportiert
    """
    service = get_steuerberater_package_service()

    status_enum = None
    if status_filter:
        try:
            status_enum = PackageStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {status_filter}",
            )

    # F-31 minimal: Service-Signatur ist list_packages(company_id, status) ohne
    # db-/page-kwargs und liefert eine Liste (kein (packages, total)-Tupel).
    all_packages = await service.list_packages(
        company_id=company_id,
        status=status_enum,
    )
    total = len(all_packages)

    # Pagination im Router (Service paginiert nicht).
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    packages = all_packages[start:end]

    # Zähle nach Status (ueber alle, nicht nur die aktuelle Seite)
    by_status: Dict[str, int] = {}
    for pkg in all_packages:
        key = pkg.status.value
        by_status[key] = by_status.get(key, 0) + 1

    return PackageListResponse(
        packages=[_package_to_response(p) for p in packages],
        total_count=total,
        by_status=by_status,
    )


@router.post(
    "/packages",
    response_model=PackageCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Paket erstellen",
    description="Erstellt ein neues Steuerberater-Paket.",
)
@limiter.limit("10/minute")
async def create_package(
    request: Request,
    data: PackageCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageCreateResponse:
    """
    Erstellt ein neues Steuerberater-Paket.

    Bei `auto_populate=true` werden automatisch alle
    buchungsrelevanten Dokumente der Periode hinzugefügt.
    """
    if data.period_from > data.period_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Periode von muss vor Periode bis liegen.",
        )

    service = get_steuerberater_package_service()

    package, doc_count = await service.create_package(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        user_name=current_user.full_name or current_user.email,
        name=data.name,
        description=data.description,
        period_from=data.period_from,
        period_to=data.period_to,
        auto_populate=data.auto_populate,
    )

    await db.commit()

    logger.info(
        "steuerberater_package_created",
        package_id=str(package.id),
        user_id=str(current_user.id),
        document_count=doc_count,
    )

    return PackageCreateResponse(
        success=True,
        package_id=str(package.id),
        document_count=doc_count,
        message=f"Paket '{data.name}' erstellt mit {doc_count} Dokumenten.",
    )


@router.get(
    "/packages/{package_id}",
    response_model=PackageResponse,
    summary="Paket-Details",
    description="Ruft Details eines Pakets ab.",
)
@limiter.limit("30/minute")
async def get_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageResponse:
    """Ruft Details eines Steuerberater-Pakets ab."""
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    return _package_to_response(package)


@router.delete(
    "/packages/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Paket löschen",
    description="Löscht ein Paket (nur Entwürfe).",
)
@limiter.limit("10/minute")
async def delete_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Response:
    """
    Löscht ein Steuerberater-Paket.

    **Nur Entwürfe können gelöscht werden.**
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    if package.status != PackageStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur Entwürfe können gelöscht werden.",
        )

    await service.delete_package(db, package_id)
    await db.commit()

    logger.info(
        "steuerberater_package_deleted",
        package_id=str(package_id),
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Workflow Endpoints
# =============================================================================

@router.post(
    "/packages/{package_id}/submit",
    response_model=PackageResponse,
    summary="Zur Prüfung einreichen",
    description="Reicht ein Paket zur Prüfung durch den Steuerberater ein.",
)
@limiter.limit("10/minute")
async def submit_for_review(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    data: SubmitReviewRequest = SubmitReviewRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageResponse:
    """
    Reicht ein Paket zur Prüfung ein.

    Das Paket wird validiert und bei Erfolg in den Status
    'pending_review' versetzt.
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    success, error = await service.submit_for_review(
        db=db,
        package_id=package_id,
        submitter_name=current_user.full_name or current_user.email,
        message=data.message,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Einreichung fehlgeschlagen.",
        )

    await db.commit()

    # Aktualisiertes Paket abrufen
    package = await service.get_package(db, package_id, company_id)
    return _package_to_response(package)


@router.post(
    "/packages/{package_id}/approve",
    response_model=PackageResponse,
    summary="Paket genehmigen",
    description="Genehmigt ein Paket (nur für Steuerberater/Admin).",
)
@limiter.limit("10/minute")
async def approve_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    data: ApproveRejectRequest = ApproveRejectRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageResponse:
    """
    Genehmigt ein Steuerberater-Paket.

    **Nur für Administratoren/Steuerberater.**
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    success, error = await service.approve_package(
        db=db,
        package_id=package_id,
        approver_id=current_user.id,
        approver_name=current_user.full_name or current_user.email,
        comment=data.comment,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Genehmigung fehlgeschlagen.",
        )

    await db.commit()

    # Aktualisiertes Paket abrufen
    package = await service.get_package(db, package_id, company_id)
    return _package_to_response(package)


@router.post(
    "/packages/{package_id}/reject",
    response_model=PackageResponse,
    summary="Paket ablehnen",
    description="Lehnt ein Paket ab (nur für Steuerberater/Admin).",
)
@limiter.limit("10/minute")
async def reject_package(
    request: Request,
    data: ApproveRejectRequest,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageResponse:
    """
    Lehnt ein Steuerberater-Paket ab.

    **Nur für Administratoren/Steuerberater.**
    Das Paket wird zurück in den Entwurf-Status versetzt.
    """
    if not data.comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ablehnungsgrund erforderlich.",
        )

    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    success, error = await service.reject_package(
        db=db,
        package_id=package_id,
        rejector_name=current_user.full_name or current_user.email,
        reason=data.comment,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Ablehnung fehlgeschlagen.",
        )

    await db.commit()

    # Aktualisiertes Paket abrufen
    package = await service.get_package(db, package_id, company_id)
    return _package_to_response(package)


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post(
    "/packages/{package_id}/export",
    summary="Als ZIP exportieren",
    description="Exportiert ein genehmigtes Paket als DATEV-kompatibles ZIP.",
)
@limiter.limit("5/minute")
async def export_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> StreamingResponse:
    """
    Exportiert ein Steuerberater-Paket als ZIP.

    Das ZIP enthält:
    - Buchungsstapel.csv (DATEV-Format)
    - Belegbilder/ (PDF-Ordner)
    - Index.xml (Verzeichnis)
    - Prüfsummen.txt (MD5)

    **Nur genehmigte Pakete können exportiert werden.**
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    if package.status != PackageStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur genehmigte Pakete können exportiert werden.",
        )

    # Export generieren
    zip_bytes, filename = await service.export_package(
        db=db,
        package_id=package_id,
    )

    await db.commit()

    logger.info(
        "steuerberater_package_exported",
        package_id=str(package_id),
        user_id=str(current_user.id),
        filename=filename,
    )

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": build_content_disposition(filename, "attachment"),
            "X-Package-ID": str(package_id),
        },
    )


# =============================================================================
# Document Management Endpoints
# =============================================================================

@router.get(
    "/packages/{package_id}/documents",
    response_model=List[PackageDocumentResponse],
    summary="Dokumente im Paket",
    description="Listet alle Dokumente in einem Paket auf.",
)
@limiter.limit("30/minute")
async def list_package_documents(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[PackageDocumentResponse]:
    """Listet alle Dokumente in einem Steuerberater-Paket auf."""
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    documents = await service.get_package_documents(db, package_id)
    return [_document_to_response(d) for d in documents]


@router.post(
    "/packages/{package_id}/documents",
    response_model=PackageDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dokument hinzufügen",
    description="Fügt ein Dokument zum Paket hinzu.",
)
@limiter.limit("30/minute")
async def add_document_to_package(
    request: Request,
    data: DocumentAddRequest,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> PackageDocumentResponse:
    """
    Fügt ein Dokument zum Steuerberater-Paket hinzu.

    **Nur Entwürfe können bearbeitet werden.**
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    if package.status != PackageStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur Entwürfe können bearbeitet werden.",
        )

    document, error = await service.add_document(
        db=db,
        package_id=package_id,
        document_id=data.document_id,
        buchungstext=data.buchungstext,
        konto_soll=data.konto_soll,
        konto_haben=data.konto_haben,
        kostenstelle=data.kostenstelle,
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Dokument konnte nicht hinzugefügt werden.",
        )

    await db.commit()
    return _document_to_response(document)


@router.delete(
    "/packages/{package_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dokument entfernen",
    description="Entfernt ein Dokument aus dem Paket.",
)
@limiter.limit("30/minute")
async def remove_document_from_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    document_id: UUID = Path(..., description="Dokument-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Response:
    """
    Entfernt ein Dokument aus dem Steuerberater-Paket.

    **Nur Entwürfe können bearbeitet werden.**
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    if package.status != PackageStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur Entwürfe können bearbeitet werden.",
        )

    success = await service.remove_document(db, package_id, document_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht im Paket gefunden.",
        )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Validation Endpoints
# =============================================================================

@router.get(
    "/packages/{package_id}/validation",
    response_model=ValidationResultResponse,
    summary="Validierung prüfen",
    description="Prüft die DATEV-Validierung eines Pakets.",
)
@limiter.limit("30/minute")
async def validate_package(
    request: Request,
    package_id: UUID = Path(..., description="Paket-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ValidationResultResponse:
    """
    Führt eine DATEV-Validierung des Pakets durch.

    Prüft:
    - Pflichtfelder
    - Kontonummern-Format
    - Belegdaten
    - DATEV-Regeln
    """
    service = get_steuerberater_package_service()
    package = await service.get_package(db, package_id, company_id)

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paket nicht gefunden.",
        )

    result = await service.validate_package(db, package_id)

    return ValidationResultResponse(
        is_valid=result.is_valid,
        total_documents=result.total_documents,
        valid_documents=result.valid_documents,
        invalid_documents=result.invalid_documents,
        errors=result.errors,
        warnings=result.warnings,
    )
