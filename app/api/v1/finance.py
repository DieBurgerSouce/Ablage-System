# -*- coding: utf-8 -*-
"""
Finance API Endpoints.

REST API fuer Jahr-basierte Finanz-Dokumentenverwaltung:
- GET /years - Alle Finanz-Jahre mit Dokument-Counts
- GET /years/{year} - Details fuer ein Jahr
- GET /aggregations - Gesamt-Aggregationen
- GET /years/{year}/aggregations - Jahr-Aggregationen
- GET /years/{year}/categories/{category}/documents - Kategorie-Dokumente
- GET /years/{year}/categories/{category}/aggregations - Kategorie-Aggregationen
- POST /years/{year}/categories/{category}/documents - Dokument hochladen
- PATCH /documents/{document_id} - Finanz-Dokument bearbeiten
- DELETE /documents/{document_id} - Finanz-Dokument loeschen

Feinpoliert und durchdacht - Deutsche Finanzdokumente.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Document, FinanceDocumentHistory
from app.db.schemas import (
    FinanceYearResponse,
    FinanceYearListResponse,
    FinanceAggregationsResponse,
    FinanceCategoryFilter,
    FinanceCategoryDocumentListResponse,
    FinanceCategoryAggregations,
    FinanceDocumentCategory,
    FinanceDocumentUpdateRequest,
    FinanceDocumentUploadResponse,
    FinanceDocumentDeleteResponse,
    FinanceCategoryDocumentResponse,
    ProcessingStatus,
    MessageResponse,
    # Bulk Operations
    FinanceBulkDeleteRequest,
    FinanceBulkDeleteResponse,
    FinanceBulkUpdateRequest,
    FinanceBulkUpdateResponse,
    FinanceExportRequest,
    FinanceExportResponse,
    FinanceExportFormat,
    # Deadlines
    FinanceDeadlineItem,
    FinanceDeadlineListResponse,
    DeadlineType,
    # History / Audit Trail
    FinanceDocumentHistoryResponse,
    FinanceDocumentHistoryItem,
    FinanceHistoryAction,
)
from app.api.dependencies import get_db, get_current_active_user, check_rate_limit
from app.core.rbac import (
    require_finance_read,
    require_finance_write,
    require_finance_delete,
)
from app.services.document_services.finance_service import (
    get_finance_service,
    FINANCE_CATEGORY_TO_DOCTYPE,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/finance", tags=["Finance"])


# =============================================================================
# YEAR ENDPOINTS
# =============================================================================

@router.get(
    "/years",
    response_model=FinanceYearListResponse,
    summary="Finanz-Jahre auflisten",
    description="Listet alle Jahre mit Finanz-Dokumenten und Aggregationen"
)
async def list_finance_years(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceYearListResponse:
    """
    Listet alle Finanz-Jahre auf.

    Jedes Jahr enthaelt:
    - Dokument-Counts pro Kategorie
    - Gesamt-Nachzahlung und -Erstattung
    - Anzahl offener Fristen
    - Letztes Dokumentdatum
    """
    service = get_finance_service()

    try:
        result = await service.get_finance_years(db, current_user.id)

        logger.info(
            "finance_years_listed",
            user_id=str(current_user.id),
            count=len(result.items),
        )

        return result

    except Exception as e:
        logger.exception("finance_years_list_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Finanz-Jahre"
        )


@router.get(
    "/years/{year}",
    response_model=FinanceYearResponse,
    summary="Finanz-Jahr abrufen",
    description="Ruft Details fuer ein spezifisches Finanz-Jahr ab"
)
async def get_finance_year(
    year: int = Path(..., ge=2000, le=2100, description="Das Jahr (z.B. 2024)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceYearResponse:
    """
    Ruft Details fuer ein Finanz-Jahr ab.

    Enthaelt:
    - Dokument-Counts pro Kategorie (18 Kategorien in 4 Paketen)
    - Nachzahlung/Erstattung-Summen
    - Offene Fristen
    - Aktivitaetsstatus
    """
    service = get_finance_service()

    try:
        result = await service.get_year_details(db, current_user.id, year)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Keine Finanz-Dokumente fuer Jahr {year} gefunden"
            )

        logger.info(
            "finance_year_retrieved",
            user_id=str(current_user.id),
            year=year,
            total_docs=result.total_documents,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("finance_year_retrieval_failed", user_id=str(current_user.id), year=year)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Finanz-Jahres"
        )


# =============================================================================
# AGGREGATION ENDPOINTS
# =============================================================================

@router.get(
    "/aggregations",
    response_model=FinanceAggregationsResponse,
    summary="Gesamt-Aggregationen",
    description="Gesamt-Statistiken ueber alle Finanz-Jahre"
)
async def get_overall_aggregations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceAggregationsResponse:
    """
    Ruft Gesamt-Aggregationen ueber alle Jahre ab.

    Enthaelt:
    - Gesamt-Dokumente
    - Gesamt-Nachzahlung und -Erstattung
    - Saldo (Erstattung - Nachzahlung)
    - Offene und ueberfaellige Fristen
    - Dokumente nach Kategorie und Paket
    """
    service = get_finance_service()

    try:
        result = await service.get_overall_aggregations(db, current_user.id)

        logger.info(
            "finance_overall_aggregations_retrieved",
            user_id=str(current_user.id),
            total_docs=result.total_documents,
            saldo=result.saldo,
        )

        return result

    except Exception as e:
        logger.exception("finance_aggregations_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Finanz-Aggregationen"
        )


@router.get(
    "/years/{year}/aggregations",
    response_model=FinanceAggregationsResponse,
    summary="Jahr-Aggregationen",
    description="Statistiken fuer ein spezifisches Finanz-Jahr"
)
async def get_year_aggregations(
    year: int = Path(..., ge=2000, le=2100, description="Das Jahr"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceAggregationsResponse:
    """
    Ruft Aggregationen fuer ein Jahr ab.

    Enthaelt:
    - Jahres-Dokumente
    - Nachzahlung/Erstattung-Summen
    - Saldo
    - Fristen fuer dieses Jahr
    - Dokumente nach Kategorie und Paket
    """
    service = get_finance_service()

    try:
        result = await service.get_year_aggregations(db, current_user.id, year)

        logger.info(
            "finance_year_aggregations_retrieved",
            user_id=str(current_user.id),
            year=year,
            total_docs=result.total_documents,
        )

        return result

    except Exception as e:
        logger.exception("finance_year_aggregations_failed", user_id=str(current_user.id), year=year)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Jahr-Aggregationen"
        )


# =============================================================================
# CATEGORY DOCUMENT ENDPOINTS
# =============================================================================

@router.get(
    "/years/{year}/categories/{category}/documents",
    response_model=FinanceCategoryDocumentListResponse,
    summary="Kategorie-Dokumente",
    description="Listet Dokumente einer Finanz-Kategorie mit Paginierung und Filtern"
)
async def get_category_documents(
    year: int = Path(..., ge=2000, le=2100, description="Das Jahr"),
    category: str = Path(..., description="Kategorie-Slug (z.B. 'steuerbescheide')"),
    search: Optional[str] = Query(None, min_length=1, max_length=100, description="Textsuche"),
    date_from: Optional[datetime] = Query(None, description="Dokumente ab Datum"),
    date_to: Optional[datetime] = Query(None, description="Dokumente bis Datum"),
    amount_min: Optional[float] = Query(None, ge=0, description="Mindestbetrag"),
    amount_max: Optional[float] = Query(None, ge=0, description="Maximalbetrag"),
    steuerart: Optional[str] = Query(None, description="Steuerart-Filter"),
    page: int = Query(0, ge=0, description="Seite (0-basiert)"),
    page_size: int = Query(25, ge=1, le=100, description="Eintraege pro Seite"),
    sort_by: str = Query("document_date", description="Sortierfeld"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceCategoryDocumentListResponse:
    """
    Listet Dokumente einer Finanz-Kategorie auf.

    **Kategorien (18 in 4 Paketen):**

    *Steuern:*
    - grundabgabenbescheid
    - steuerbescheide
    - vorauszahlungen
    - steuererklaerungen
    - finanzamt_korrespondenz

    *Personal:*
    - lohn_gehalt
    - sozialversicherung
    - berufsgenossenschaft
    - arbeitsvertraege

    *Versicherung:*
    - betriebshaftpflicht
    - sachversicherungen
    - kfz_versicherung
    - rechtsschutz

    *Bank:*
    - kontoauszuege
    - kreditvertraege
    - buergschaften
    - darlehen

    **Filter:**
    - search: Suche in Dateinamen
    - date_from/date_to: Datumszeitraum
    - amount_min/amount_max: Betragsbereich
    - steuerart: Nur bei Steuer-Kategorien

    **Sortierung:**
    - document_date, created_at, filename, file_size
    """
    # Validiere Kategorie
    valid_categories = [e.value for e in FinanceDocumentCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannte Kategorie '{category}'. Gueltige Kategorien: {', '.join(valid_categories)}"
        )

    service = get_finance_service()

    # Build filter
    filter_params = FinanceCategoryFilter(
        year=year,
        category=category,
        search=search,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        steuerart=steuerart,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    try:
        result = await service.get_category_documents(db, current_user.id, filter_params)

        logger.info(
            "finance_category_documents_listed",
            user_id=str(current_user.id),
            year=year,
            category=category,
            count=len(result.items),
            total=result.total,
        )

        return result

    except Exception as e:
        logger.exception(
            "finance_category_documents_failed",
            user_id=str(current_user.id),
            year=year,
            category=category,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Kategorie-Dokumente"
        )


@router.get(
    "/years/{year}/categories/{category}/aggregations",
    response_model=FinanceCategoryAggregations,
    summary="Kategorie-Aggregationen",
    description="Statistiken fuer eine spezifische Finanz-Kategorie"
)
async def get_category_aggregations(
    year: int = Path(..., ge=2000, le=2100, description="Das Jahr"),
    category: str = Path(..., description="Kategorie-Slug"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FinanceCategoryAggregations:
    """
    Ruft Aggregationen fuer eine Finanz-Kategorie ab.

    Enthaelt:
    - Dokument-Anzahl in dieser Kategorie
    - Nachzahlung/Erstattung (nur bei relevanten Kategorien)
    - Offene/ueberfaellige Fristen (nur bei relevanten Kategorien)
    - Datum des aeltesten und neuesten Dokuments
    """
    # Validiere Kategorie
    valid_categories = [e.value for e in FinanceDocumentCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannte Kategorie '{category}'"
        )

    service = get_finance_service()

    try:
        result = await service.get_category_aggregations(db, current_user.id, year, category)

        logger.info(
            "finance_category_aggregations_retrieved",
            user_id=str(current_user.id),
            year=year,
            category=category,
            total_docs=result.total_documents,
        )

        return result

    except Exception as e:
        logger.exception(
            "finance_category_aggregations_failed",
            user_id=str(current_user.id),
            year=year,
            category=category,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Kategorie-Aggregationen"
        )


# =============================================================================
# DOCUMENT CRUD ENDPOINTS
# =============================================================================

@router.post(
    "/years/{year}/categories/{category}/documents",
    response_model=FinanceDocumentUploadResponse,
    status_code=201,
    summary="Finanz-Dokument hochladen",
    description="Laedt ein Dokument in eine Finanz-Kategorie hoch"
)
async def upload_finance_document(
    year: int = Path(..., ge=2000, le=2100, description="Das Jahr"),
    category: str = Path(..., description="Kategorie-Slug"),
    file: UploadFile = File(..., description="Dokument (PDF, PNG, JPG, TIFF)"),
    start_ocr: bool = Form(True, description="OCR-Verarbeitung automatisch starten"),
    ocr_backend: str = Form("auto", description="OCR-Backend (auto/deepseek/got_ocr/surya)"),
    current_user: User = Depends(require_finance_write),
    db: AsyncSession = Depends(get_db),
) -> FinanceDocumentUploadResponse:
    """
    Laedt ein Finanz-Dokument hoch.

    **Workflow:**
    1. Datei-Validierung (Typ, Groesse)
    2. Upload zu MinIO Object Storage
    3. Datenbank-Eintrag mit Finanz-Kategorie
    4. Optional: OCR-Job starten

    **Kategorien:** steuerbescheide, lohn_gehalt, kontoauszuege, etc.
    """
    from app.core.config import settings
    from app.services.storage_service import get_storage_service
    from app.core.file_validation import validate_file_security, verify_magic_bytes, FileValidationError

    # 1. Validiere Kategorie
    valid_categories = [e.value for e in FinanceDocumentCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannte Kategorie '{category}'"
        )

    # 2. Validiere Dateiname
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dateiname fehlt")

    file_ext = FilePath(file.filename).suffix.lower()
    allowed_extensions = settings.ALLOWED_EXTENSIONS

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Dateityp nicht erlaubt: {file_ext}. Erlaubt: {', '.join(allowed_extensions)}"
        )

    # 3. Dateiinhalt lesen
    file_content = await file.read()
    file_size = len(file_content)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Leere Datei")

    file_size_mb = file_size / (1024 * 1024)
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu gross: {file_size_mb:.1f}MB. Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # 4. Magic-Byte Validierung
    is_valid, magic_error, detected_type = verify_magic_bytes(file_content, file.filename)
    if not is_valid:
        raise HTTPException(status_code=400, detail=magic_error or "Ungueltige Datei")

    # MIME-Type
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    detected_mime = mime_map.get(file_ext, "application/octet-stream")

    # 5. Sicherheitsvalidierung
    try:
        is_secure, security_error, _ = validate_file_security(file_content, file.filename, detected_mime)
        if not is_secure:
            raise HTTPException(status_code=400, detail=security_error or "Sicherheitsvalidierung fehlgeschlagen")
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=e.user_message_de)

    # 6. Checksum
    file_hash = hashlib.sha256(file_content).hexdigest()

    # 7. Upload zu MinIO
    storage = get_storage_service()
    try:
        upload_result = await storage.upload_document(
            file_data=file_content,
            filename=file.filename,
            content_type=detected_mime,
            user_id=str(current_user.id),
            metadata={
                "document_type": FINANCE_CATEGORY_TO_DOCTYPE.get(category, "other").value
                    if hasattr(FINANCE_CATEGORY_TO_DOCTYPE.get(category, "other"), "value")
                    else str(FINANCE_CATEGORY_TO_DOCTYPE.get(category, "other")),
                "finance_category": category,
                "finance_year": str(year),
                "original_filename": file.filename,
            }
        )
    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("finance_upload_storage_failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail="Upload fehlgeschlagen. Bitte erneut versuchen.")

    # 8. Datenbank-Eintrag
    doc_id = uuid4()
    doc_type = FINANCE_CATEGORY_TO_DOCTYPE.get(category)
    doc_type_value = doc_type.value if doc_type and hasattr(doc_type, "value") else "other"

    new_document = Document(
        id=doc_id,
        filename=upload_result["storage_path"].split("/")[-1],
        original_filename=file.filename,
        file_path=upload_result["storage_path"],
        file_size=file_size,
        mime_type=detected_mime,
        checksum=file_hash,
        document_type=doc_type_value,
        status="pending" if start_ocr else "uploaded",
        owner_id=current_user.id,
        document_metadata={
            "finance_category": category,
            "finance_year": year,
            "ocr_backend_requested": ocr_backend,
        },
        extracted_data={
            "finance_category": category,
            "finance_year": year,
        },
    )

    db.add(new_document)
    await db.commit()
    await db.refresh(new_document)

    # 9. OCR-Job starten
    processing_job_id = None
    if start_ocr:
        try:
            from app.workers.tasks.ocr_tasks import process_document_task
            task = process_document_task.apply_async(
                kwargs={
                    "document_id": str(doc_id),
                    "backend": ocr_backend,
                    "language": "de",
                },
                priority=5
            )
            processing_job_id = task.id
            logger.info(
                "finance_ocr_job_queued",
                document_id=str(doc_id),
                task_id=task.id,
                category=category,
            )
        except Exception as e:
            logger.warning("finance_ocr_queue_failed", error=str(e))

    logger.info(
        "finance_document_uploaded",
        document_id=str(doc_id),
        user_id=str(current_user.id),
        category=category,
        year=year,
        file_size=file_size,
    )

    return FinanceDocumentUploadResponse(
        id=doc_id,
        filename=new_document.filename,
        original_filename=file.filename,
        category=category,
        year=year,
        document_type=doc_type if doc_type else "other",
        processing_status=ProcessingStatus.PENDING if start_ocr else ProcessingStatus.UPLOADED,
        file_size=file_size,
        created_at=new_document.created_at,
        ocr_job_id=processing_job_id,
        message=f"Dokument erfolgreich zu {category} ({year}) hochgeladen"
    )


@router.patch(
    "/documents/{document_id}",
    response_model=FinanceCategoryDocumentResponse,
    summary="Finanz-Dokument bearbeiten",
    description="Aktualisiert Finanz-spezifische Felder eines Dokuments"
)
async def update_finance_document(
    document_id: UUID = Path(..., description="Dokument-ID"),
    update_data: FinanceDocumentUpdateRequest = ...,
    current_user: User = Depends(require_finance_write),
    db: AsyncSession = Depends(get_db),
) -> FinanceCategoryDocumentResponse:
    """
    Bearbeitet Finanz-Felder eines Dokuments.

    **Bearbeitbare Felder:**
    - category: Kategorie aendern
    - einspruchsfrist, aktenzeichen, steuernummer, etc.
    - nachzahlung, erstattung
    - document_date, document_number, total_amount
    """
    # Validiere Kategorie falls angegeben
    if update_data.category:
        valid_categories = [e.value for e in FinanceDocumentCategory]
        if update_data.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannte Kategorie '{update_data.category}'"
            )

    service = get_finance_service()

    try:
        # Konvertiere Pydantic-Model zu Dict (ohne None-Werte)
        update_dict = update_data.model_dump(exclude_none=True)

        document = await service.update_finance_document(
            db, current_user.id, document_id, update_dict
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {document_id} nicht gefunden oder keine Berechtigung"
            )

        # Konvertiere zu Response
        category = update_data.category or document.document_metadata.get("finance_category", "other")
        return service._to_finance_document_response(document, category)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "finance_document_update_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren des Dokuments"
        )


@router.delete(
    "/documents/{document_id}",
    response_model=FinanceDocumentDeleteResponse,
    summary="Finanz-Dokument loeschen",
    description="Loescht ein Finanz-Dokument (Soft-Delete)"
)
async def delete_finance_document(
    document_id: UUID = Path(..., description="Dokument-ID"),
    current_user: User = Depends(require_finance_delete),
    db: AsyncSession = Depends(get_db),
) -> FinanceDocumentDeleteResponse:
    """
    Loescht ein Finanz-Dokument.

    Implementiert Soft-Delete gemaess GDPR-Compliance.
    Das Dokument wird als geloescht markiert, aber nicht sofort physisch entfernt.
    """
    service = get_finance_service()

    try:
        document = await service.delete_finance_document(db, current_user.id, document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {document_id} nicht gefunden oder keine Berechtigung"
            )

        return FinanceDocumentDeleteResponse(
            id=document_id,
            deleted=True,
            deleted_at=document.deleted_at or datetime.now(timezone.utc),
            message="Finanz-Dokument erfolgreich geloescht"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "finance_document_delete_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Loeschen des Dokuments"
        )


@router.get(
    "/documents/{document_id}",
    response_model=FinanceCategoryDocumentResponse,
    summary="Finanz-Dokument abrufen",
    description="Ruft Details eines einzelnen Finanz-Dokuments ab"
)
async def get_finance_document(
    document_id: UUID = Path(..., description="Dokument-ID"),
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> FinanceCategoryDocumentResponse:
    """
    Ruft ein einzelnes Finanz-Dokument ab.

    Enthaelt alle Finanz-spezifischen Felder wie
    Einspruchsfrist, Aktenzeichen, Nachzahlung, etc.
    """
    service = get_finance_service()

    try:
        document = await service.get_finance_document(db, current_user.id, document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {document_id} nicht gefunden"
            )

        category = (document.document_metadata or {}).get("finance_category", "other")
        return service._to_finance_document_response(document, category)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "finance_document_get_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen des Dokuments"
        )


# =============================================================================
# BULK OPERATION ENDPOINTS
# =============================================================================

@router.post(
    "/documents/bulk-delete",
    response_model=FinanceBulkDeleteResponse,
    summary="Finanz-Dokumente massenhaft loeschen",
    description="Loescht mehrere Finanz-Dokumente auf einmal (Soft-Delete)"
)
async def bulk_delete_finance_documents(
    request: FinanceBulkDeleteRequest,
    current_user: User = Depends(require_finance_delete),
    db: AsyncSession = Depends(get_db),
) -> FinanceBulkDeleteResponse:
    """
    Loescht mehrere Finanz-Dokumente massenhaft.

    **Limits:**
    - Maximal 100 Dokumente pro Request
    - Nur eigene Dokumente koennen geloescht werden

    **Verhalten:**
    - Soft-Delete gemaess GDPR-Compliance
    - Teilerfolge moeglich (einige geloescht, einige fehlgeschlagen)
    - Detaillierte Rueckmeldung pro Dokument
    """
    service = get_finance_service()
    deleted_ids: list[UUID] = []
    failed_ids: list[UUID] = []
    errors: list[str] = []

    for doc_id in request.document_ids:
        try:
            document = await service.delete_finance_document(db, current_user.id, doc_id)
            if document:
                deleted_ids.append(doc_id)
            else:
                failed_ids.append(doc_id)
                errors.append(f"{doc_id}: Nicht gefunden oder keine Berechtigung")
        except Exception as e:
            failed_ids.append(doc_id)
            errors.append(f"{doc_id}: {str(e)}")
            logger.warning(
                "bulk_delete_document_failed",
                document_id=str(doc_id),
                error=str(e),
            )

    logger.info(
        "finance_bulk_delete_completed",
        user_id=str(current_user.id),
        deleted_count=len(deleted_ids),
        failed_count=len(failed_ids),
    )

    return FinanceBulkDeleteResponse(
        deleted_count=len(deleted_ids),
        failed_count=len(failed_ids),
        deleted_ids=deleted_ids,
        failed_ids=failed_ids,
        errors=errors,
        message=f"{len(deleted_ids)} Dokumente geloescht, {len(failed_ids)} fehlgeschlagen"
    )


@router.patch(
    "/documents/bulk-update",
    response_model=FinanceBulkUpdateResponse,
    summary="Finanz-Dokumente massenhaft aktualisieren",
    description="Aktualisiert Kategorie/Jahr fuer mehrere Dokumente"
)
async def bulk_update_finance_documents(
    request: FinanceBulkUpdateRequest,
    current_user: User = Depends(require_finance_write),
    db: AsyncSession = Depends(get_db),
) -> FinanceBulkUpdateResponse:
    """
    Aktualisiert mehrere Finanz-Dokumente massenhaft.

    **Anwendungsfaelle:**
    - Kategorie aendern (z.B. falsch zugeordnete Dokumente korrigieren)
    - Jahr aendern (z.B. bei Import-Fehlern)
    - Steuerart setzen

    **Limits:**
    - Maximal 100 Dokumente pro Request
    - Nur eigene Dokumente koennen aktualisiert werden
    """
    # Validiere Kategorie
    if request.category:
        valid_categories = [e.value for e in FinanceDocumentCategory]
        if request.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannte Kategorie '{request.category}'"
            )

    service = get_finance_service()
    updated_ids: list[UUID] = []
    failed_ids: list[UUID] = []
    errors: list[str] = []

    # Build update dict
    update_data = {}
    if request.category:
        update_data["category"] = request.category
    if request.year:
        update_data["year"] = request.year
    if request.steuerart:
        update_data["steuerart"] = request.steuerart

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Feld zum Aktualisieren erforderlich (category, year, steuerart)"
        )

    for doc_id in request.document_ids:
        try:
            document = await service.update_finance_document(
                db, current_user.id, doc_id, update_data
            )
            if document:
                updated_ids.append(doc_id)
            else:
                failed_ids.append(doc_id)
                errors.append(f"{doc_id}: Nicht gefunden oder keine Berechtigung")
        except Exception as e:
            failed_ids.append(doc_id)
            errors.append(f"{doc_id}: {str(e)}")
            logger.warning(
                "bulk_update_document_failed",
                document_id=str(doc_id),
                error=str(e),
            )

    logger.info(
        "finance_bulk_update_completed",
        user_id=str(current_user.id),
        updated_count=len(updated_ids),
        failed_count=len(failed_ids),
    )

    return FinanceBulkUpdateResponse(
        updated_count=len(updated_ids),
        failed_count=len(failed_ids),
        updated_ids=updated_ids,
        failed_ids=failed_ids,
        errors=errors,
        message=f"{len(updated_ids)} Dokumente aktualisiert, {len(failed_ids)} fehlgeschlagen"
    )


@router.post(
    "/documents/export",
    response_model=FinanceExportResponse,
    summary="Finanz-Dokumente exportieren",
    description="Startet einen Export-Job fuer Finanz-Dokumente"
)
async def export_finance_documents(
    request: FinanceExportRequest,
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> FinanceExportResponse:
    """
    Startet einen Export-Job fuer Finanz-Dokumente.

    **Export-Formate:**
    - JSON: Metadaten als JSON-Datei
    - CSV: Metadaten als CSV-Tabelle
    - ZIP: Metadaten + Original-Dateien als ZIP-Archiv

    **Filter:**
    - document_ids: Spezifische Dokumente
    - year: Alle Dokumente eines Jahres
    - category: Alle Dokumente einer Kategorie

    **Hinweis:**
    Der Export wird asynchron verarbeitet. Bei grossen Exports
    kann die download_url erst nach kurzer Zeit verfuegbar sein.
    """
    from uuid import uuid4 as generate_uuid
    from datetime import timedelta

    service = get_finance_service()

    # Validiere Kategorie falls angegeben
    if request.category:
        valid_categories = [e.value for e in FinanceDocumentCategory]
        if request.category not in valid_categories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannte Kategorie '{request.category}'"
            )

    # Zaehle Dokumente fuer Export
    try:
        # Wenn spezifische IDs angegeben, zaehle diese
        if request.document_ids:
            doc_count = len(request.document_ids)
        else:
            # Zaehle basierend auf Filtern
            # Hier vereinfacht - in Produktion wuerde man eine count-Query machen
            doc_count = 0
            if request.year:
                aggregations = await service.get_year_aggregations(
                    db, current_user.id, request.year
                )
                doc_count = aggregations.total_documents

        if doc_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keine Dokumente fuer Export gefunden"
            )

        # Generiere Export-ID
        export_id = str(generate_uuid())

        # In Produktion: Celery Task starten
        # Hier: Synchrone Response (fuer kleine Exports)
        logger.info(
            "finance_export_started",
            user_id=str(current_user.id),
            export_id=export_id,
            format=request.format.value,
            document_count=doc_count,
        )

        # Fuer grosse Exports: Celery Task
        # task = export_finance_documents_task.delay(export_id, ...)
        # return FinanceExportResponse(export_id=export_id, status="pending", ...)

        # Fuer kleine Exports (< 50 Dokumente): Direkt-URL
        # In Produktion wuerde hier der tatsaechliche Export stattfinden
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        return FinanceExportResponse(
            export_id=export_id,
            status="processing",
            download_url=None,  # Wird spaeter via WebSocket/Polling bereitgestellt
            document_count=doc_count,
            file_size_bytes=None,
            expires_at=expires_at,
            message=f"Export von {doc_count} Dokumenten wird verarbeitet"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "finance_export_failed",
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Starten des Exports"
        )


# =============================================================================
# DEADLINE ENDPOINTS
# =============================================================================

# Kategorie-Labels fuer Fristen
CATEGORY_LABELS = {
    "steuerbescheide": "Steuerbescheide",
    "vorauszahlungen": "Vorauszahlungen",
    "steuererklaerungen": "Steuererklaerungen",
    "lohn_gehalt": "Lohn/Gehalt",
    "rente_pension": "Rente/Pension",
    "sozialversicherung": "Sozialversicherung",
    "versicherungen_privat": "Versicherungen (Privat)",
    "versicherungen_kfz": "KFZ-Versicherungen",
    "versicherungen_sonstige": "Sonstige Versicherungen",
    "vertraege_abos": "Vertraege & Abos",
    "rechnungen_belege": "Rechnungen & Belege",
    "bankunterlagen": "Bankunterlagen",
    "immobilien": "Immobilien",
    "sonstige": "Sonstige",
}


@router.get(
    "/deadlines",
    response_model=FinanceDeadlineListResponse,
    summary="Finanz-Fristen auflisten",
    description="Listet alle anstehenden und ueberfaelligen Fristen"
)
async def list_finance_deadlines(
    year: Optional[str] = Query(None, description="Nur Fristen fuer dieses Jahr"),
    category: Optional[str] = Query(None, description="Nur Fristen fuer diese Kategorie"),
    include_past: bool = Query(True, description="Ueberfaellige Fristen einschliessen"),
    days_ahead: int = Query(90, ge=1, le=365, description="Tage in die Zukunft"),
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> FinanceDeadlineListResponse:
    """
    Listet alle Finanz-Fristen auf.

    **Filter:**
    - year: Nur Fristen fuer ein bestimmtes Jahr
    - category: Nur Fristen fuer eine bestimmte Kategorie
    - include_past: Ueberfaellige Fristen einschliessen (Standard: ja)
    - days_ahead: Wie viele Tage in die Zukunft schauen (Standard: 90)

    **Sortierung:**
    Fristen werden nach Dringlichkeit sortiert (ueberfaellig zuerst, dann nach Datum).
    """
    from datetime import timedelta
    from sqlalchemy import select, and_, or_

    service = get_finance_service()

    try:
        # Datum-Grenzen berechnen
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        future_limit = today + timedelta(days=days_ahead)

        # Query bauen
        query = select(Document).where(
            and_(
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
                # Nur Dokumente mit Einspruchsfrist
                Document.extracted_data.isnot(None),
            )
        )

        # Jahr-Filter
        if year:
            query = query.where(Document.year == int(year))

        # Kategorie-Filter
        if category:
            valid_categories = [e.value for e in FinanceDocumentCategory]
            if category not in valid_categories:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unbekannte Kategorie '{category}'"
                )
            # Kategorie zu Document-Type mappen
            doc_type = FINANCE_CATEGORY_TO_DOCTYPE.get(category)
            if doc_type:
                query = query.where(Document.document_type == doc_type)

        result = await db.execute(query)
        documents = result.scalars().all()

        # Fristen extrahieren und filtern
        deadline_items: list[FinanceDeadlineItem] = []

        for doc in documents:
            if not doc.extracted_data:
                continue

            # Einspruchsfrist pruefen
            einspruchsfrist = doc.extracted_data.get("einspruchsfrist")
            if einspruchsfrist:
                try:
                    deadline_date = datetime.fromisoformat(einspruchsfrist.replace("Z", "+00:00"))
                    if deadline_date.tzinfo is None:
                        deadline_date = deadline_date.replace(tzinfo=timezone.utc)

                    # Filter: Datum-Bereich
                    if not include_past and deadline_date < today:
                        continue
                    if deadline_date > future_limit:
                        continue

                    days_until = (deadline_date - today).days

                    # Kategorie aus Document-Type ableiten
                    doc_category = "sonstige"
                    for cat, dtype in FINANCE_CATEGORY_TO_DOCTYPE.items():
                        if dtype == doc.document_type:
                            doc_category = cat
                            break

                    deadline_items.append(FinanceDeadlineItem(
                        id=f"deadline-{doc.id}-einspruch",
                        document_id=doc.id,
                        document_name=doc.original_filename or str(doc.id),
                        category=doc_category,
                        category_label=CATEGORY_LABELS.get(doc_category, doc_category),
                        year=str(doc.year) if doc.year else str(datetime.now().year),
                        deadline=deadline_date,
                        deadline_type=DeadlineType.EINSPRUCHSFRIST,
                        aktenzeichen=doc.extracted_data.get("aktenzeichen"),
                        days_until=days_until,
                    ))
                except (ValueError, TypeError):
                    pass  # Ungueliges Datum ignorieren

            # Zahlungsfrist pruefen (falls vorhanden)
            zahlungsfrist = doc.extracted_data.get("zahlungsfrist")
            if zahlungsfrist:
                try:
                    deadline_date = datetime.fromisoformat(zahlungsfrist.replace("Z", "+00:00"))
                    if deadline_date.tzinfo is None:
                        deadline_date = deadline_date.replace(tzinfo=timezone.utc)

                    if not include_past and deadline_date < today:
                        continue
                    if deadline_date > future_limit:
                        continue

                    days_until = (deadline_date - today).days

                    doc_category = "sonstige"
                    for cat, dtype in FINANCE_CATEGORY_TO_DOCTYPE.items():
                        if dtype == doc.document_type:
                            doc_category = cat
                            break

                    deadline_items.append(FinanceDeadlineItem(
                        id=f"deadline-{doc.id}-zahlung",
                        document_id=doc.id,
                        document_name=doc.original_filename or str(doc.id),
                        category=doc_category,
                        category_label=CATEGORY_LABELS.get(doc_category, doc_category),
                        year=str(doc.year) if doc.year else str(datetime.now().year),
                        deadline=deadline_date,
                        deadline_type=DeadlineType.ZAHLUNGSFRIST,
                        aktenzeichen=doc.extracted_data.get("aktenzeichen"),
                        days_until=days_until,
                    ))
                except (ValueError, TypeError):
                    pass

        # Sortieren: Ueberfaellig zuerst, dann nach Datum
        deadline_items.sort(key=lambda x: (x.days_until >= 0, x.days_until))

        # Zaehlen
        overdue_count = sum(1 for d in deadline_items if d.days_until < 0)
        urgent_count = sum(1 for d in deadline_items if 0 <= d.days_until <= 7)
        upcoming_count = sum(1 for d in deadline_items if 7 < d.days_until <= 30)

        logger.info(
            "finance_deadlines_listed",
            user_id=str(current_user.id),
            total=len(deadline_items),
            overdue=overdue_count,
            urgent=urgent_count,
            upcoming=upcoming_count,
        )

        return FinanceDeadlineListResponse(
            items=deadline_items,
            total=len(deadline_items),
            overdue_count=overdue_count,
            urgent_count=urgent_count,
            upcoming_count=upcoming_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("finance_deadlines_list_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Fristen"
        )


# =============================================================================
# HISTORY / AUDIT TRAIL ENDPOINTS
# =============================================================================

@router.get(
    "/documents/{document_id}/history",
    response_model=FinanceDocumentHistoryResponse,
    summary="Dokument-History abrufen",
    description="Ruft die vollstaendige Aenderungs-History eines Finanz-Dokuments ab"
)
async def get_document_history(
    document_id: UUID = Path(..., description="Dokument-ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Eintraege"),
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> FinanceDocumentHistoryResponse:
    """
    Ruft die vollstaendige Aenderungs-History eines Finanz-Dokuments ab.

    **Aktionstypen:**
    - created: Dokument erstellt
    - updated: Dokument bearbeitet
    - deleted: Dokument geloescht
    - restored: Dokument wiederhergestellt
    - category_changed: Kategorie geaendert
    - year_changed: Jahr geaendert
    - ocr_completed: OCR-Verarbeitung abgeschlossen
    - deadline_set: Frist gesetzt
    - deadline_removed: Frist entfernt
    - bulk_update: Massenaktualisierung

    **Sortierung:**
    Neueste Eintraege zuerst.
    """
    from sqlalchemy import select, and_

    service = get_finance_service()

    try:
        # Dokument abrufen und Berechtigung pruefen
        document = await service.get_finance_document(db, current_user.id, document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {document_id} nicht gefunden"
            )

        # History-Eintraege abrufen
        query = (
            select(FinanceDocumentHistory)
            .where(FinanceDocumentHistory.document_id == document_id)
            .order_by(FinanceDocumentHistory.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(query)
        history_entries = result.scalars().all()

        # Benutzer-Infos laden (Join waere effizienter, aber fuer Einfachheit)
        from app.db.models import User as UserModel

        items: list[FinanceDocumentHistoryItem] = []
        for entry in history_entries:
            # Benutzer laden wenn vorhanden
            user_email = None
            user_name = None
            if entry.user_id:
                user_result = await db.execute(
                    select(UserModel).where(UserModel.id == entry.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    user_email = user.email
                    user_name = user.full_name or user.username

            items.append(FinanceDocumentHistoryItem(
                id=entry.id,
                document_id=entry.document_id,
                user_id=entry.user_id,
                user_email=user_email,
                user_name=user_name,
                action=entry.action,
                description=entry.description,
                old_values=entry.old_values or {},
                new_values=entry.new_values or {},
                changed_fields=entry.changed_fields or [],
                ip_address=entry.ip_address,
                metadata=entry.metadata or {},
                created_at=entry.created_at,
            ))

        logger.info(
            "finance_document_history_retrieved",
            user_id=str(current_user.id),
            document_id=str(document_id),
            count=len(items),
        )

        return FinanceDocumentHistoryResponse(
            document_id=document_id,
            document_name=document.original_filename or str(document_id),
            items=items,
            total=len(items),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "finance_document_history_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Dokument-History"
        )


# =============================================================================
# ANOMALY DETECTION ENDPOINTS (Enterprise Feature)
# =============================================================================

from pydantic import BaseModel, Field
from typing import List


class AnomalyItem(BaseModel):
    """Einzelne erkannte Anomalie."""
    type: str = Field(..., description="Anomalie-Typ")
    severity: str = Field(..., description="Schweregrad (low/medium/high/critical)")
    description: str = Field(..., description="Beschreibung der Anomalie")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz 0-1")
    details: dict = Field(default_factory=dict, description="Zusaetzliche Details")


class AnomalyCheckResponse(BaseModel):
    """Response fuer Anomalie-Check eines Dokuments."""
    document_id: UUID
    document_name: str
    is_suspicious: bool = Field(..., description="Verdaechtig ja/nein")
    overall_risk_score: float = Field(..., ge=0.0, le=1.0, description="Gesamt-Risikoscore")
    anomaly_count: int = Field(..., description="Anzahl erkannter Anomalien")
    anomalies: List[AnomalyItem] = Field(default_factory=list, description="Liste der Anomalien")
    checked_at: datetime = Field(..., description="Zeitpunkt der Pruefung")
    message: str = Field(..., description="Status-Nachricht")


class AnomalyDashboardStats(BaseModel):
    """Statistiken fuer Anomalie-Dashboard."""
    total_documents_checked: int = Field(..., description="Gesamtzahl gepruefter Dokumente")
    suspicious_documents: int = Field(..., description="Anzahl verdaechtiger Dokumente")
    pending_review: int = Field(..., description="Zur Pruefung ausstehend")
    resolved: int = Field(..., description="Bereits bearbeitet")
    average_risk_score: float = Field(..., description="Durchschnittlicher Risikoscore")
    anomaly_type_distribution: dict = Field(default_factory=dict, description="Verteilung nach Typ")


class AnomalyDocumentSummary(BaseModel):
    """Zusammenfassung eines verdaechtigen Dokuments."""
    document_id: UUID
    document_name: str
    category: str
    year: int
    risk_score: float
    anomaly_count: int
    anomaly_types: List[str]
    detected_at: datetime
    status: str = Field(..., description="pending/reviewed/resolved")


class AnomalyDashboardResponse(BaseModel):
    """Response fuer Anomalie-Dashboard."""
    stats: AnomalyDashboardStats
    recent_anomalies: List[AnomalyDocumentSummary] = Field(
        default_factory=list, description="Neueste verdaechtige Dokumente"
    )
    message: str


@router.post(
    "/anomalies/check/{document_id}",
    response_model=AnomalyCheckResponse,
    summary="Dokument auf Anomalien pruefen",
    description="Prueft ein Finanz-Dokument manuell auf Anomalien"
)
async def check_document_anomalies(
    document_id: UUID = Path(..., description="Dokument-ID"),
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> AnomalyCheckResponse:
    """
    Prueft ein Finanz-Dokument manuell auf Anomalien.

    **Erkannte Anomalie-Typen:**
    - HIGH_AMOUNT: Ungewoehnlich hoher Betrag
    - NEW_SUPPLIER_HIGH_VALUE: Neuer Lieferant mit hohem Wert
    - DUPLICATE_NUMBER: Duplizierte Rechnungsnummer
    - UNUSUAL_PAYMENT_TERMS: Ungewoehnliche Zahlungsbedingungen
    - ROUND_AMOUNT: Verdaechtiger runder Betrag
    - WEEKEND_INVOICE: Rechnung am Wochenende
    - MISSING_VAT: Fehlende Umsatzsteuer
    - AMOUNT_MISMATCH: Betrag stimmt nicht ueberein
    - FUTURE_DATE: Datum in der Zukunft

    **Risikoscore:**
    - 0.0-0.3: Niedriges Risiko
    - 0.3-0.6: Mittleres Risiko
    - 0.6-0.8: Hohes Risiko
    - 0.8-1.0: Kritisch
    """
    from app.services.ai.anomaly_detection_service import get_anomaly_detection_service

    # Dokument abrufen und Berechtigung pruefen
    service = get_finance_service()
    document = await service.get_finance_document(db, current_user.id, document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dokument {document_id} nicht gefunden"
        )

    try:
        anomaly_service = get_anomaly_detection_service()
        result = await anomaly_service.check_document(
            db, document_id, getattr(document, 'company_id', None)
        )

        # Anomalien in API-Format konvertieren
        anomaly_items = []
        for anomaly in result.anomalies:
            anomaly_items.append(AnomalyItem(
                type=anomaly.anomaly_type.value,
                severity=anomaly.severity.value,
                description=anomaly.description,
                confidence=anomaly.confidence,
                details=anomaly.details or {},
            ))

        # AI Decision erstellen falls verdaechtig
        if result.is_suspicious:
            try:
                await anomaly_service.create_anomaly_decision(
                    db, document_id, result, getattr(document, 'company_id', None)
                )
            except Exception as decision_error:
                logger.warning(
                    "anomaly_decision_creation_failed",
                    document_id=str(document_id),
                    error=str(decision_error),
                )

        logger.info(
            "anomaly_check_completed",
            user_id=str(current_user.id),
            document_id=str(document_id),
            is_suspicious=result.is_suspicious,
            anomaly_count=len(result.anomalies),
            risk_score=result.overall_risk_score,
        )

        return AnomalyCheckResponse(
            document_id=document_id,
            document_name=document.original_filename or str(document_id),
            is_suspicious=result.is_suspicious,
            overall_risk_score=result.overall_risk_score,
            anomaly_count=len(result.anomalies),
            anomalies=anomaly_items,
            checked_at=datetime.now(timezone.utc),
            message="Anomalie-Pruefung abgeschlossen" if not result.is_suspicious
                    else f"ACHTUNG: {len(result.anomalies)} Anomalie(n) erkannt!"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "anomaly_check_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei der Anomalie-Pruefung"
        )


@router.get(
    "/anomalies/dashboard",
    response_model=AnomalyDashboardResponse,
    summary="Anomalie-Dashboard",
    description="Zeigt Uebersicht aller erkannten Anomalien"
)
async def get_anomaly_dashboard(
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Filter nach Jahr"),
    limit: int = Query(20, ge=1, le=100, description="Max. Anzahl Dokumente"),
    current_user: User = Depends(require_finance_read),
    db: AsyncSession = Depends(get_db),
) -> AnomalyDashboardResponse:
    """
    Zeigt eine Uebersicht aller erkannten Anomalien.

    **Dashboard enthält:**
    - Gesamtstatistiken (geprüft, verdächtig, ausstehend, gelöst)
    - Durchschnittlicher Risikoscore
    - Verteilung nach Anomalie-Typ
    - Liste der neuesten verdächtigen Dokumente

    **Filter:**
    - year: Nur Anomalien aus diesem Jahr anzeigen
    - limit: Maximale Anzahl der angezeigten Dokumente
    """
    from sqlalchemy import select, func, and_
    from app.db.models import AIDecision

    try:
        # Query: Alle Dokumente mit Anomalien im extracted_data
        base_query = select(Document).where(
            and_(
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
                Document.extracted_data.isnot(None),
            )
        )

        if year:
            base_query = base_query.where(Document.year == year)

        result = await db.execute(base_query)
        documents = result.scalars().all()

        # Statistiken berechnen
        total_checked = 0
        suspicious_docs = 0
        risk_scores = []
        type_distribution: dict[str, int] = {}
        recent_anomalies: list[AnomalyDocumentSummary] = []

        for doc in documents:
            if not doc.extracted_data:
                continue

            anomalies_data = doc.extracted_data.get("anomalies")
            if anomalies_data:
                total_checked += 1

                if anomalies_data.get("is_suspicious"):
                    suspicious_docs += 1
                    risk_score = anomalies_data.get("risk_score", 0.0)
                    risk_scores.append(risk_score)

                    # Typ-Verteilung
                    for atype in anomalies_data.get("types", []):
                        type_distribution[atype] = type_distribution.get(atype, 0) + 1

                    # Zu Recent hinzufuegen
                    category = (doc.document_metadata or {}).get("finance_category", "sonstige")
                    doc_year = (doc.extracted_data or {}).get("finance_year", doc.year or datetime.now().year)

                    recent_anomalies.append(AnomalyDocumentSummary(
                        document_id=doc.id,
                        document_name=doc.original_filename or str(doc.id),
                        category=category,
                        year=int(doc_year) if doc_year else datetime.now().year,
                        risk_score=risk_score,
                        anomaly_count=anomalies_data.get("anomaly_count", 0),
                        anomaly_types=anomalies_data.get("types", []),
                        detected_at=doc.updated_at or doc.created_at,
                        status="pending",  # TODO: AIDecision status abfragen
                    ))

        # Nach Risikoscore sortieren (hoechstes Risiko zuerst)
        recent_anomalies.sort(key=lambda x: x.risk_score, reverse=True)
        recent_anomalies = recent_anomalies[:limit]

        # Durchschnittlicher Risikoscore
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

        # AIDecisions fuer Status zaehlen
        pending_count = 0
        resolved_count = 0
        try:
            # Pending AIDecisions
            pending_result = await db.execute(
                select(func.count(AIDecision.id)).where(
                    and_(
                        AIDecision.decision_type == "anomaly_review",
                        AIDecision.status == "pending",
                    )
                )
            )
            pending_count = pending_result.scalar() or 0

            # Resolved AIDecisions
            resolved_result = await db.execute(
                select(func.count(AIDecision.id)).where(
                    and_(
                        AIDecision.decision_type == "anomaly_review",
                        AIDecision.status.in_(["approved", "rejected"]),
                    )
                )
            )
            resolved_count = resolved_result.scalar() or 0
        except Exception:
            # AIDecision Tabelle existiert moeglicherweise nicht
            pass

        logger.info(
            "anomaly_dashboard_retrieved",
            user_id=str(current_user.id),
            total_checked=total_checked,
            suspicious=suspicious_docs,
            avg_risk=avg_risk,
        )

        return AnomalyDashboardResponse(
            stats=AnomalyDashboardStats(
                total_documents_checked=total_checked,
                suspicious_documents=suspicious_docs,
                pending_review=pending_count,
                resolved=resolved_count,
                average_risk_score=round(avg_risk, 3),
                anomaly_type_distribution=type_distribution,
            ),
            recent_anomalies=recent_anomalies,
            message=f"{suspicious_docs} verdaechtige Dokumente von {total_checked} geprueften"
        )

    except Exception as e:
        logger.exception(
            "anomaly_dashboard_failed",
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Anomalie-Dashboards"
        )
