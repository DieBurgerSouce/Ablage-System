"""Documents API endpoints with search and batch operations.

Provides REST API endpoints for:
- Document CRUD operations
- Full-text and semantic search
- Similar documents discovery
- Batch operations (delete, tag, export)
"""

from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from uuid import UUID
from enum import Enum
import io
import asyncio
import os
import re
from urllib.parse import quote

import structlog


# =============================================================================
# SECURITY: Content-Disposition Header Sanitization (PHASE 10.1 FIX)
# =============================================================================
# Prevents CRLF injection / HTTP Response Splitting attacks
# Reference: CWE-113, OWASP HTTP Response Splitting

def sanitize_filename_for_header(filename: str) -> str:
    """Sanitize filename for use in Content-Disposition header.

    Removes CRLF characters to prevent HTTP Response Splitting attacks
    and encodes the filename using RFC 5987 for Unicode support.

    Args:
        filename: Original filename (may contain Unicode, CRLF)

    Returns:
        Safe filename header value with proper encoding

    Security:
        - Strips CR (\\r), LF (\\n), and NULL (\\x00) characters
        - Uses RFC 5987 encoding for non-ASCII characters
        - Provides fallback ASCII filename for legacy clients
    """
    # SECURITY: Remove CRLF and NULL characters completely
    safe_name = filename.replace('\r', '').replace('\n', '').replace('\x00', '')

    # Remove any other control characters (ASCII 0-31 except tab)
    safe_name = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', safe_name)

    # Limit filename length to prevent buffer overflow attacks
    if len(safe_name) > 255:
        # Keep extension
        parts = safe_name.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) < 20:
            safe_name = parts[0][:255 - len(parts[1]) - 1] + '.' + parts[1]
        else:
            safe_name = safe_name[:255]

    return safe_name


def build_content_disposition(filename: str, disposition: str = "attachment") -> str:
    """Build a safe Content-Disposition header value.

    Uses RFC 5987 encoding for proper Unicode support while
    maintaining backwards compatibility with ASCII-only clients.

    Args:
        filename: Original filename
        disposition: 'attachment' (download) or 'inline' (display)

    Returns:
        Safe Content-Disposition header value
    """
    safe_name = sanitize_filename_for_header(filename)

    # Create ASCII fallback (replace non-ASCII with underscore)
    ascii_name = safe_name.encode('ascii', 'replace').decode('ascii').replace('?', '_')

    # RFC 5987 encoding for the full Unicode filename
    encoded_name = quote(safe_name, safe='')

    # Return header with both fallback and encoded filename
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, Form, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.db.models import User, Company
from app.middleware.company_context import require_company, get_current_company
from app.db.schemas import (
    # Search
    SearchType, SearchFilters, SearchResponse, SimilarDocumentItem,
    SortField, SortOrder, DocumentType, ProcessingStatus, OCRBackend,
    # Documents
    DocumentDetailResponse, DocumentListResponseExtended, DocumentUpdateRequest,
    DocumentSummary, DocumentPartialUpdateRequest, DocumentCreateResponse,
    # Batch
    BatchDeleteRequest, BatchTagRequest, BatchExportRequest,
    BatchOperationResult, BatchExportResult, TagOperation, ExportFormat,
    BulkUpdateRequest, BulkUpdateResult,
    BatchFetchRequest, BatchFetchResponse,  # P1.4: Bulk fetch endpoint
    # Soft-Delete (GDPR Phase 2.3)
    SoftDeleteRequest, SoftDeleteResponse, RestoreDocumentResponse,
    DeletedDocumentsListResponse,
    # Common
    MessageResponse
)
from app.api.dependencies import (
    get_current_active_user, get_db, check_rate_limit, check_batch_rate_limit
)
from app.services.search_service import get_search_service
from app.services.document_service import get_document_service
from app.services.archive_service import archive_service
from app.core.exceptions import ImmutabilityViolationError
from app.services.document_services.ablage_service import CATEGORY_TO_DOCTYPE
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ==================== Document Upload Endpoint ====================

@router.post("/", response_model=DocumentCreateResponse, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Dokument (PDF, PNG, JPG, TIFF)"),
    document_type: DocumentType = Form(DocumentType.OTHER, description="Dokumenttyp"),
    language: str = Form("de", description="Sprache (de/en)"),
    tags: Optional[str] = Form(None, description="Tags (kommasepariert)"),
    start_ocr: bool = Form(True, description="OCR-Verarbeitung automatisch starten"),
    ocr_backend: str = Form("auto", description="OCR-Backend (auto/deepseek/got_ocr/surya)"),
    priority: int = Form(5, ge=1, le=10, description="Verarbeitungsprioritaet"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
):
    """Dokument hochladen und persistent speichern.

    Laedt ein Dokument in den Object Storage (MinIO) hoch und erstellt
    einen Datenbankeintrag. Optional wird die OCR-Verarbeitung gestartet.

    **Unterstuetzte Formate:** PDF, PNG, JPG, JPEG, TIFF, BMP

    **Workflow:**
    1. Datei-Validierung (Typ, Groesse, Magic-Bytes)
    2. Upload zu MinIO Object Storage
    3. Datenbank-Eintrag erstellen
    4. Optional: OCR-Job in Queue einreihen

    **Beispiel:**
    ```
    curl -X POST /api/v1/documents/ \\
      -H "Authorization: Bearer <token>" \\
      -F "file=@dokument.pdf" \\
      -F "document_type=invoice" \\
      -F "start_ocr=true"
    ```
    """
    import hashlib
    from pathlib import Path
    from uuid import uuid4
    from app.core.config import settings
    from app.services.storage_service import get_storage_service
    from app.db.models import Document
    from app.core.file_validation import validate_file_security, FileValidationError

    # 1. Dateiname und Erweiterung validieren
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Dateiname fehlt"
        )

    file_ext = Path(file.filename).suffix.lower()
    allowed_extensions = settings.ALLOWED_EXTENSIONS

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Dateityp nicht erlaubt: {file_ext}. Erlaubt: {', '.join(allowed_extensions)}"
        )

    # 2. Sprache validieren
    if language not in ["de", "en"]:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Sprache: {language}. Erlaubt: de, en"
        )

    # 3. Dateiinhalt lesen und Groesse pruefen
    file_content = await file.read()
    file_size = len(file_content)
    file_size_mb = file_size / (1024 * 1024)

    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Leere Datei"
        )

    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu gross: {file_size_mb:.1f}MB. Maximum: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # 4. Magic-Byte Validierung (Content-Type)
    from app.core.file_validation import verify_magic_bytes
    is_valid, magic_error, detected_type = verify_magic_bytes(file_content, file.filename)

    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=magic_error or "Ungültige Datei - Magic Bytes stimmen nicht überein"
        )

    # MIME-Type aus Dateiendung ableiten
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
        ".gif": "image/gif",
    }
    detected_mime = mime_map.get(file_ext, "application/octet-stream")

    # 5. Erweiterte Sicherheitsvalidierung (PDF-Bombs, Image-Bombs)
    try:
        is_secure, security_error, _ = validate_file_security(
            file_content, file.filename, detected_mime
        )
        if not is_secure:
            raise HTTPException(
                status_code=400,
                detail=security_error or "Sicherheitsvalidierung fehlgeschlagen"
            )
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=e.user_message_de)

    # 6. Malware-Scan (ClamAV + YARA + Heuristics)
    # SECURITY: Scannt Datei vor Upload auf Viren/Malware
    from app.core.malware_scanner import (
        scan_file_async,
        MalwareDetectedError,
        ScannerUnavailableError
    )
    from app.core.config import settings as app_settings

    # Malware-Scan nur wenn aktiviert (default: true)
    malware_scan_enabled = getattr(app_settings, 'MALWARE_SCAN_ENABLED', True)

    if malware_scan_enabled:
        try:
            scan_result = await scan_file_async(
                content=file_content,
                filename=file.filename,
                raise_on_threat=False  # Wir behandeln das Ergebnis manuell
            )

            if not scan_result.is_clean:
                # Malware erkannt - Datei blockieren
                threat_names = ", ".join(scan_result.threat_names[:3])
                if len(scan_result.threats) > 3:
                    threat_names += f" (+{len(scan_result.threats) - 3} weitere)"

                logger.warning(
                    "malware_detected_upload_blocked",
                    filename=file.filename[:50],  # Truncate for logging
                    file_hash=scan_result.file_hash_sha256[:16],
                    threat_count=len(scan_result.threats),
                    highest_level=scan_result.highest_threat_level.value,
                    engines_used=[e.value for e in scan_result.engines_used]
                )

                raise HTTPException(
                    status_code=400,
                    detail=f"Sicherheitswarnung: Schadhafter Inhalt erkannt ({threat_names}). "
                           f"Die Datei wurde blockiert. Bedrohungsstufe: {scan_result.highest_threat_level.value}"
                )

            # Scan erfolgreich - logge Metriken
            logger.info(
                "malware_scan_passed",
                filename=file.filename[:50],
                scan_duration_ms=scan_result.scan_duration_ms,
                engines_used=[e.value for e in scan_result.engines_used]
            )

        except ScannerUnavailableError as e:
            # Scanner nicht verfuegbar - je nach Konfiguration fortfahren oder blockieren
            # In Production sollte fail_on_unavailable=True sein
            fail_on_scan_unavailable = getattr(app_settings, 'MALWARE_SCAN_FAIL_CLOSED', True)

            if fail_on_scan_unavailable:
                logger.error(
                    "malware_scanner_unavailable_upload_blocked",
                    scanner=e.engine,
                    filename=file.filename[:50]
                )
                raise HTTPException(
                    status_code=503,
                    detail="Malware-Scanner nicht verfuegbar. Upload temporaer blockiert."
                )
            else:
                logger.warning(
                    "malware_scanner_unavailable_upload_allowed",
                    scanner=e.engine,
                    filename=file.filename[:50]
                )

        except Exception as scan_error:
            # Unerwarteter Fehler beim Scannen
            logger.error(
                "malware_scan_error",
                error_type=type(scan_error).__name__,
                filename=file.filename[:50]
            )

            fail_on_scan_error = getattr(app_settings, 'MALWARE_SCAN_FAIL_CLOSED', True)
            if fail_on_scan_error:
                raise HTTPException(
                    status_code=503,
                    detail="Sicherheitspruefung fehlgeschlagen. Bitte versuchen Sie es spaeter erneut."
                )

    # 7. Checksum berechnen
    file_hash = hashlib.sha256(file_content).hexdigest()

    # 8. In MinIO hochladen
    storage = get_storage_service()

    try:
        upload_result = await storage.upload_document(
            file_data=file_content,
            filename=file.filename,
            content_type=detected_mime,
            user_id=str(current_user.id),
            metadata={
                "document_type": document_type.value if hasattr(document_type, 'value') else str(document_type),
                "language": language,
                "original_filename": file.filename,
            }
        )
    except Exception as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        # SECURITY FIX: Sanitize error - log only error type, not full details that may contain PII
        error_type = type(e).__name__
        logger.error(
            "storage_upload_failed",
            error_type=error_type,
            filename_length=len(file.filename) if file.filename else 0,
            has_content_type=bool(detected_mime)
        )
        raise HTTPException(
            status_code=500,
            detail="Upload fehlgeschlagen. Bitte versuchen Sie es erneut."
        )

    # 9. Datenbank-Eintrag erstellen
    doc_id = uuid4()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    new_document = Document(
        id=doc_id,
        filename=upload_result["storage_path"].split("/")[-1],
        original_filename=file.filename,
        file_path=upload_result["storage_path"],
        file_size=file_size,
        mime_type=detected_mime,
        checksum=file_hash,
        document_type=document_type.value if hasattr(document_type, 'value') else str(document_type),
        status="pending" if start_ocr else "uploaded",
        owner_id=current_user.id,
        company_id=company.id,  # Multi-Company Support: Dokument zur aktuellen Firma zuordnen
        document_metadata={
            "language": language,
            "tags": tag_list,
            "ocr_backend_requested": ocr_backend,
            "priority": priority,
        }
    )

    db.add(new_document)
    await db.commit()
    await db.refresh(new_document)

    # 10. Optional: OCR-Job starten
    processing_job_id = None
    if start_ocr:
        try:
            from app.workers.tasks.ocr_tasks import process_document_task
            task = process_document_task.apply_async(
                kwargs={
                    "document_id": str(doc_id),
                    "backend": ocr_backend,
                    "language": language,
                },
                priority=priority
            )
            processing_job_id = task.id
            logger.info(
                "ocr_job_queued",
                document_id=str(doc_id),
                task_id=task.id,
                backend=ocr_backend
            )

            # Quick Classification wird jetzt vom OCR-Task nach Completion getriggert.
            # Grund: Surya auf CPU dauert 3+ Minuten, daher nutzt Quick Classification
            # den vorhandenen OCR-Text statt eigenes OCR durchzufuehren.
            # Siehe: ocr_tasks.py -> quick_classification_task_queued_after_ocr

        except Exception as e:
            logger.warning(
                "ocr_job_queue_failed",
                document_id=str(doc_id),
                **safe_error_log(e)
            )
            # Dokument bleibt gespeichert, OCR kann spaeter gestartet werden

    logger.info(
        "document_uploaded_api",
        document_id=str(doc_id),
        user_id=str(current_user.id),
        filename=file.filename,
        size_mb=round(file_size_mb, 2),
        start_ocr=start_ocr
    )

    # 11. Workflow-Trigger: Document Created Event
    try:
        from app.workers.tasks.workflow_tasks import on_document_created
        on_document_created.delay(
            document_id=str(doc_id),
            user_id=str(current_user.id)
        )
    except Exception as e:
        # Workflow-Trigger sollte Upload nicht blockieren
        logger.warning(
            "workflow_trigger_failed",
            document_id=str(doc_id),
            **safe_error_log(e)
        )

    return DocumentCreateResponse(
        id=doc_id,
        filename=new_document.filename,
        original_filename=file.filename,
        file_size=file_size,
        mime_type=detected_mime,
        status=ProcessingStatus(new_document.status),
        storage_path=upload_result["storage_path"],
        created_at=new_document.created_at,
        processing_job_id=processing_job_id,
        message="Dokument erfolgreich hochgeladen" + (" - OCR-Verarbeitung gestartet" if start_ocr else "")
    )


# ==================== Upload Complete (OCR-Review Workflow) ====================

from app.db.schemas import UploadCompleteRequest, UploadCompleteResponse
from app.services.temp_file_storage import get_temp_file_storage


@router.post("/upload-complete", response_model=UploadCompleteResponse, status_code=201)
async def upload_complete(
    request: UploadCompleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
):
    """Dokument nach OCR-Review endgueltig speichern.

    Dieser Endpoint wird aufgerufen, nachdem der User im OCR-Review-Modal
    die extrahierten Daten geprueft und bestaetigt hat. Er:

    1. Holt die Datei aus dem temporaeren Redis-Speicher
    2. Speichert sie permanent in MinIO mit dem finalen Dateinamen
    3. Erstellt den Document-Eintrag in der Datenbank
    4. Verknuepft das Dokument mit der Business Entity (falls angegeben)
    5. Loescht die temporaere Datei

    **Workflow:**
    ```
    /ocr/process → OCR + Quick Classification → temp_file_id
                         ↓
    OCR-Review-Modal (User prueft/korrigiert)
                         ↓
    /documents/upload-complete → Dokument permanent gespeichert
    ```

    **Beispiel:**
    ```json
    {
      "temp_file_id": "abc123-...",
      "final_filename": "Mueller_RG-2024-001.pdf",
      "document_type": "invoice",
      "document_number": "RG-2024-001",
      "folder_id": "folie",
      "category": "rechnungen",
      "entity_type": "supplier",
      "business_entity_id": "uuid-...",
      "tags": ["Rechnung", "Mueller"]
    }
    ```
    """
    import hashlib
    from uuid import uuid4
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, BusinessEntity

    # 1. Temporaere Datei aus Redis holen
    temp_storage = get_temp_file_storage()
    temp_file = await temp_storage.get(request.temp_file_id)

    if not temp_file:
        raise HTTPException(
            status_code=404,
            detail="Temporaere Datei nicht gefunden oder abgelaufen. "
                   "Bitte laden Sie das Dokument erneut hoch."
        )

    # Sicherheits-Check: User muss der sein, der die Datei hochgeladen hat
    if temp_file.user_id != str(current_user.id):
        logger.warning(
            "upload_complete_user_mismatch",
            temp_file_user_id=temp_file.user_id[:8],
            request_user_id=str(current_user.id)[:8]
        )
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer diese Datei"
        )

    # 2. Checksum berechnen
    file_hash = hashlib.sha256(temp_file.content).hexdigest()

    # 3. Storage-Pfad bestimmen (Entity-basiert)
    # Format: entities/{entity_id}/{folder_id}/{category}/{filename}
    if request.business_entity_id:
        storage_base = f"entities/{request.business_entity_id}/{request.folder_id}/{request.category}"
    else:
        # Fallback: User-basierter Pfad
        storage_base = f"users/{current_user.id}/{request.folder_id}/{request.category}"

    # Defense-in-depth: normalize filename even after schema validation (CWE-22)
    safe_filename = os.path.basename(request.final_filename)
    storage_path = f"{storage_base}/{safe_filename}"

    # 4. In MinIO hochladen
    storage = get_storage_service()

    try:
        upload_result = await storage.upload_document(
            file_data=temp_file.content,
            filename=safe_filename,
            content_type=temp_file.mime_type,
            user_id=str(current_user.id),
            metadata={
                "document_type": request.document_type,
                "original_filename": temp_file.original_filename,
                "category": request.category,
                "folder_id": request.folder_id,
                "entity_type": request.entity_type,
                "entity_id": str(request.business_entity_id) if request.business_entity_id else None,
            }
        )
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            "upload_complete_storage_failed",
            error_type=error_type,
            filename=request.final_filename[:50]
        )
        raise HTTPException(
            status_code=500,
            detail="Speichern fehlgeschlagen. Bitte versuchen Sie es erneut."
        )

    # 5. Business Entity laden (fuer Namen und Verknuepfung)
    entity_name = None
    if request.business_entity_id:
        from sqlalchemy import select
        entity = await db.scalar(
            select(BusinessEntity).where(BusinessEntity.id == request.business_entity_id)
        )
        if entity:
            entity_name = entity.display_name or entity.name

    # 6. Document-Eintrag erstellen
    doc_id = uuid4()

    # Metadaten zusammenstellen
    document_metadata = {
        "category": request.category,
        "folder_id": request.folder_id,
        "entity_type": request.entity_type,
        "tags": request.tags,
        "document_number": request.document_number,
        "document_date": request.document_date.isoformat() if request.document_date else None,
        "total_amount": float(request.total_amount) if request.total_amount else None,
        "currency": request.currency,
        "due_date": request.due_date.isoformat() if request.due_date else None,
    }

    # 6.1 Korrekten document_type basierend auf Kategorie bestimmen
    # Kategorie (z.B. "rechnungen") → DocumentType (z.B. "invoice")
    # Verhindert Mismatch zwischen Kategorie-Filter und document_type
    category_doctype = CATEGORY_TO_DOCTYPE.get(request.category.lower())
    final_document_type = category_doctype.value if category_doctype else request.document_type

    new_document = Document(
        id=doc_id,
        filename=request.final_filename,
        original_filename=temp_file.original_filename,
        file_path=upload_result["storage_path"],
        file_size=temp_file.file_size,
        mime_type=temp_file.mime_type,
        checksum=file_hash,
        document_type=final_document_type,
        status="completed",  # Bereits OCR-verarbeitet
        owner_id=current_user.id,
        company_id=company.id,
        business_entity_id=request.business_entity_id,
        document_metadata=document_metadata,
    )

    # OCR-Text speichern falls vorhanden
    if request.ocr_text:
        new_document.ocr_text = request.ocr_text
    if request.ocr_confidence is not None:
        new_document.ocr_confidence = request.ocr_confidence

    db.add(new_document)

    try:
        await db.commit()
        await db.refresh(new_document)
    except Exception as e:
        await db.rollback()
        logger.error(
            "upload_complete_db_failed",
            error_type=type(e).__name__,
            document_id=str(doc_id)
        )
        raise HTTPException(
            status_code=500,
            detail="Datenbank-Fehler. Bitte versuchen Sie es erneut."
        )

    # 7. Temporaere Datei loeschen
    try:
        await temp_storage.delete(request.temp_file_id)
    except Exception as e:
        # Nicht kritisch - TTL raeaumt spaeter auf
        logger.warning(
            "upload_complete_temp_delete_failed",
            temp_file_id=request.temp_file_id[:8],
            error_type=type(e).__name__
        )

    # 8. Logging
    logger.info(
        "document_upload_complete",
        document_id=str(doc_id),
        user_id=str(current_user.id),
        filename=request.final_filename[:50],
        category=request.category,
        folder_id=request.folder_id,
        entity_linked=bool(request.business_entity_id),
        file_size_mb=round(temp_file.file_size / (1024 * 1024), 2)
    )

    # 9. Workflow-Trigger: Document Created Event
    try:
        from app.workers.tasks.workflow_tasks import on_document_created
        on_document_created.delay(
            document_id=str(doc_id),
            user_id=str(current_user.id)
        )
    except Exception as e:
        # Workflow-Trigger sollte Upload nicht blockieren
        logger.warning(
            "workflow_trigger_failed",
            document_id=str(doc_id),
            **safe_error_log(e)
        )

    return UploadCompleteResponse(
        success=True,
        document_id=doc_id,
        filename=request.final_filename,
        storage_path=upload_result["storage_path"],
        file_size=temp_file.file_size,
        entity_linked=bool(request.business_entity_id),
        entity_name=entity_name,
        message=f"Dokument '{request.final_filename}' erfolgreich in '{request.category}' abgelegt"
    )


# ==================== Document CRUD Endpoints ====================

@router.get("/", response_model=DocumentListResponseExtended)
async def list_documents(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    document_type: Optional[DocumentType] = Query(None, description="Dokumenttyp filtern"),
    status: Optional[ProcessingStatus] = Query(None, description="Status filtern"),
    date_from: Optional[datetime] = Query(None, description="Erstellt nach"),
    date_to: Optional[datetime] = Query(None, description="Erstellt vor"),
    confidence_min: Optional[float] = Query(None, ge=0, le=100, description="Min. OCR-Konfidenz"),
    has_embedding: Optional[bool] = Query(None, description="Mit Embedding"),
    language: Optional[str] = Query(None, pattern="^(de|en)$", description="Sprache"),
    sort_by: SortField = Query(SortField.CREATED_AT, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierreihenfolge"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente auflisten mit Filterung und Pagination.

    Gibt eine paginierte Liste der eigenen Dokumente zurueck,
    optional gefiltert nach verschiedenen Kriterien.
    """
    filters = SearchFilters(
        document_type=document_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        confidence_min=confidence_min,
        has_embedding=has_embedding,
        language=language
    )

    service = get_document_service()
    return await service.list_documents(
        db=db,
        user_id=current_user.id,
        filters=filters,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order
    )


@router.get("/search/", response_model=SearchResponse)
async def search_documents(
    request: Request,
    q: str = Query(..., min_length=2, max_length=1000, description="Suchbegriff (mindestens 2 Zeichen)"),
    search_type: SearchType = Query(SearchType.HYBRID, description="Art der Suche"),
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    document_type: Optional[DocumentType] = Query(None, description="Dokumenttyp filtern"),
    status: Optional[ProcessingStatus] = Query(None, description="Status filtern"),
    date_from: Optional[datetime] = Query(None, description="Erstellt nach"),
    date_to: Optional[datetime] = Query(None, description="Erstellt vor"),
    confidence_min: Optional[float] = Query(None, ge=0, le=100, description="Min. OCR-Konfidenz"),
    has_embedding: Optional[bool] = Query(None, description="Mit Embedding"),
    tags: Optional[List[str]] = Query(None, description="Tags filtern"),
    sort_by: SortField = Query(SortField.RELEVANCE, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierreihenfolge"),
    highlight: bool = Query(True, description="Textausschnitte hervorheben"),
    similarity_threshold: float = Query(0.5, ge=0, le=1, description="Min. Aehnlichkeit fuer semantische Suche"),
    use_synonyms: bool = Query(False, description="Suche mit Synonymen erweitern (z.B. Rechnung -> Invoice, Faktura)"),
    session_id: Optional[str] = Query(None, description="Session-ID fuer Analytics"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente durchsuchen.

    Unterstuetzt drei Suchmodi:
    - **fts**: PostgreSQL Volltextsuche mit deutschen Wortstaemmen
    - **semantic**: Semantische Suche mit Embeddings (multilingual-e5-large)
    - **hybrid**: Kombination beider Methoden (empfohlen)

    Die Hybrid-Suche kombiniert Volltext- und semantische Ergebnisse
    mittels Reciprocal Rank Fusion fuer optimale Relevanz.

    Mit **use_synonyms=true** werden deutsche Geschaeftsbegriffe automatisch
    um Synonyme erweitert (z.B. "Rechnung" findet auch "Invoice", "Faktura").
    """
    import time
    start_time = time.time()

    logger.info(
        "search_request",
        query=q[:50],
        search_type=search_type.value,
        user_id=str(current_user.id)
    )

    filters = SearchFilters(
        document_type=document_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        confidence_min=confidence_min,
        has_embedding=has_embedding,
        tags=tags
    )

    service = get_search_service()

    # Search mit Timeout (30s) um Slow-Query DoS zu verhindern
    SEARCH_TIMEOUT_SECONDS = 30.0
    try:
        result = await asyncio.wait_for(
            service.search(
                db=db,
                query=q,
                user_id=current_user.id,
                search_type=search_type,
                filters=filters,
                page=page,
                per_page=per_page,
                sort_by=sort_by,
                sort_order=sort_order,
                highlight=highlight,
                similarity_threshold=similarity_threshold,
                use_synonyms=use_synonyms
            ),
            timeout=SEARCH_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.warning(
            "search_timeout",
            query=q[:50],
            search_type=search_type.value,
            timeout_seconds=SEARCH_TIMEOUT_SECONDS
        )
        raise HTTPException(
            status_code=504,
            detail="Suche hat zu lange gedauert. Bitte versuchen Sie eine praezisere Anfrage."
        )

    # Log analytics asynchronously (non-blocking)
    try:
        from app.services.search_analytics_service import get_search_analytics_service
        analytics_service = get_search_analytics_service()

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Get request metadata
        user_agent = request.headers.get("user-agent")
        # Get client IP (respect X-Forwarded-For for proxied requests)
        forwarded_for = request.headers.get("x-forwarded-for")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.client.host if request.client else None

        analytics_id = await analytics_service.log_search(
            db=db,
            query=q,
            search_type=search_type,
            total_results=result.total,
            execution_time_ms=execution_time_ms,
            user_id=current_user.id,
            filters=filters,
            page=page,
            per_page=per_page,
            session_id=session_id,
            user_agent=user_agent,
            ip_address=client_ip,
        )

        # Add analytics_id to response for click tracking
        result.analytics_id = analytics_id

        # Save to user's search history (Redis)
        from app.api.v1.search import save_search_to_history
        await save_search_to_history(
            user_id=str(current_user.id),
            query=q,
            results_count=result.total,
            filters=filters.model_dump() if filters else None
        )
    except Exception as e:
        # Don't fail the search if analytics logging fails
        logger.warning(
            "analytics_logging_failed",
            **safe_error_log(e),
            exc_info=True  # Include full traceback for debugging
        )

    return result


# ==================== Ablage (Category) Endpoints ====================
# WICHTIG: Diese statischen Routen MUESSEN VOR /{document_id} definiert werden,
# damit FastAPI sie korrekt matcht (sonst wird "/category" als document_id interpretiert)

@router.get("/category", response_model=None)
async def get_category_documents(
    business_entity_id: UUID = Query(..., description="Kunden- oder Lieferanten-ID"),
    folder_id: str = Query(..., description="Ordner-ID (z.B. '2024')"),
    category: str = Query(..., description="Kategorie (rechnungen, angebote, etc.)"),
    entity_type: str = Query("customer", pattern="^(customer|supplier)$", description="Kunde oder Lieferant"),
    search: Optional[str] = Query(None, max_length=200, description="Textsuche"),
    date_from: Optional[str] = Query(None, description="Datum ab (ISO)"),
    date_to: Optional[str] = Query(None, description="Datum bis (ISO)"),
    amount_min: Optional[float] = Query(None, ge=0, description="Mindestbetrag"),
    amount_max: Optional[float] = Query(None, ge=0, description="Höchstbetrag"),
    processing_status: Optional[List[str]] = Query(None, description="Verarbeitungsstatus"),
    payment_status: Optional[List[str]] = Query(None, description="Zahlungsstatus"),
    tags: Optional[List[str]] = Query(None, description="Tags"),
    page: int = Query(0, ge=0, description="Seitennummer (0-basiert)"),
    page_size: int = Query(25, ge=1, le=100, description="Eintraege pro Seite"),
    sort_by: str = Query("document_date", description="Sortierfeld"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sortierrichtung"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente fuer eine Kategorie-Ansicht abrufen.

    Ermoeglicht gefilterte, paginierte Dokumentenliste fuer die Ablage-Ansicht.
    Unterstuetzt Filterung nach Datum, Betrag, Status, Tags und Volltextsuche.

    **Beispiel:**
    ```
    GET /api/v1/documents/category?business_entity_id=<uuid>&folder_id=2024&category=rechnungen
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import (
        CategoryDocumentFilter,
        CategoryDocumentListResponse,
        EntityType,
        ProcessingStatus as SchemaProcessingStatus,
        DocumentPaymentStatus,
    )

    ablage_service = get_ablage_service()

    # Filter aufbauen
    try:
        # Datumsfelder parsen
        parsed_date_from = None
        parsed_date_to = None
        if date_from:
            parsed_date_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        if date_to:
            parsed_date_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))

        # Status-Enums parsen
        parsed_processing_status = None
        if processing_status:
            parsed_processing_status = [
                SchemaProcessingStatus(s) for s in processing_status
            ]

        parsed_payment_status = None
        if payment_status:
            parsed_payment_status = [
                DocumentPaymentStatus(s) for s in payment_status
            ]

        filter_params = CategoryDocumentFilter(
            business_entity_id=business_entity_id,
            folder_id=folder_id,
            category=category,
            entity_type=EntityType(entity_type),
            search=search,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            amount_min=amount_min,
            amount_max=amount_max,
            processing_status=parsed_processing_status,
            payment_status=parsed_payment_status,
            tags=tags,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(
            status_code=400,
            detail="Ungueltiger Filterwert. Bitte Eingaben pruefen."
        )

    try:
        result = await ablage_service.get_category_documents(
            db=db,
            user_id=current_user.id,
            filter_params=filter_params,
        )

        logger.debug(
            "category_documents_retrieved",
            user_id=str(current_user.id),
            category=category,
            total=result.total
        )

        return result

    except Exception as e:
        logger.error(
            "category_documents_error",
            user_id=str(current_user.id),
            category=category,
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Abrufen der Dokumente"
        )


@router.get("/category/aggregations", response_model=None)
async def get_category_aggregations(
    business_entity_id: UUID = Query(..., description="Kunden- oder Lieferanten-ID"),
    folder_id: str = Query(..., description="Ordner-ID"),
    category: str = Query(..., description="Kategorie"),
    entity_type: str = Query("customer", pattern="^(customer|supplier)$"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Aggregierte Statistiken fuer eine Kategorie abrufen.

    Liefert Summen, Anzahlen und Status-Verteilungen fuer Dashboard-Karten.

    **Beispiel:**
    ```
    GET /api/v1/documents/category/aggregations?business_entity_id=<uuid>&folder_id=2024&category=rechnungen
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import EntityType

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.get_category_aggregations(
            db=db,
            user_id=current_user.id,
            business_entity_id=business_entity_id,
            folder_id=folder_id,
            category=category,
            entity_type=EntityType(entity_type),
        )

        logger.debug(
            "category_aggregations_retrieved",
            user_id=str(current_user.id),
            category=category,
            total_documents=result.total_documents
        )

        return result

    except Exception as e:
        logger.error(
            "category_aggregations_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Berechnen der Aggregationen"
        )


# ==================== Document Detail Endpoints ====================

@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Einzelnes Dokument mit allen Details abrufen.

    Gibt alle Metadaten, OCR-Ergebnisse und Tags fuer
    das angeforderte Dokument zurueck.
    """
    service = get_document_service()
    document = await service.get_document(db, document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    # DEBUG: Log quick classification fields
    logger.info(
        "document_get_response_qc_debug",
        document_id=str(document_id),
        quick_classification_status=document.quick_classification_status,
        quick_classification_result=document.quick_classification_result
    )

    return document


# ==================== Document Download Endpoints ====================

@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Original-Dokument herunterladen.

    Lädt das originale Dokument aus dem Object Storage herunter.
    Unterstützt alle gespeicherten Dateiformate (PDF, PNG, JPG, TIFF).

    **Response:**
    - Content-Type: Originaltyp der Datei
    - Content-Disposition: attachment; filename="original_filename"

    **Beispiel:**
    ```
    curl -X GET /api/v1/documents/{id}/download \\
      -H "Authorization: Bearer <token>" \\
      -o dokument.pdf
    ```
    """
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, DocumentAccess
    from sqlalchemy import select, or_, and_

    # Prüfe Zugriff (Owner oder via DocumentAccess)
    access_query = select(Document).where(
        and_(
            Document.id == document_id,
            or_(
                Document.owner_id == current_user.id,
                Document.id.in_(
                    select(DocumentAccess.document_id).where(
                        and_(
                            DocumentAccess.user_id == current_user.id,
                            or_(
                                DocumentAccess.expires_at.is_(None),
                                DocumentAccess.expires_at > datetime.now(timezone.utc)
                            )
                        )
                    )
                )
            )
        )
    )
    result = await db.execute(access_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    if document.is_deleted:
        raise HTTPException(
            status_code=410,
            detail="Dokument wurde gelöscht"
        )

    # Datei aus Storage laden
    storage = get_storage_service()
    try:
        file_content = await storage.download_file(document.file_path)
    except Exception as e:
        logger.error(
            "document_download_storage_error",
            document_id=str(document_id),
            file_path=document.file_path,
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Laden der Datei aus dem Storage"
        )

    # Original-Dateiname verwenden
    filename = document.original_filename or document.filename

    logger.info(
        "document_downloaded",
        document_id=str(document_id),
        user_id=str(current_user.id),
        filename=filename
    )

    return Response(
        content=file_content,
        media_type=document.mime_type or "application/octet-stream",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
            "Content-Length": str(len(file_content))
        }
    )


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Browser-kompatible Vorschau des Dokuments.

    Konvertiert Bilder (TIFF, BMP, etc.) in PNG für Browser-Anzeige.
    PDFs werden direkt zurückgegeben.

    **Response:**
    - Content-Type: image/png (für konvertierte Bilder) oder application/pdf
    - Inline-Anzeige (kein Download)
    """
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, DocumentAccess
    from sqlalchemy import select, or_, and_
    from PIL import Image
    import io

    # Prüfe Zugriff (Owner oder via DocumentAccess)
    access_query = select(Document).where(
        and_(
            Document.id == document_id,
            or_(
                Document.owner_id == current_user.id,
                Document.id.in_(
                    select(DocumentAccess.document_id).where(
                        and_(
                            DocumentAccess.user_id == current_user.id,
                            or_(
                                DocumentAccess.access_level == "view",
                                DocumentAccess.access_level == "comment",
                                DocumentAccess.access_level == "edit",
                                DocumentAccess.access_level == "manage"
                            )
                        )
                    )
                )
            )
        )
    )

    result = await db.execute(access_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Zugriffsberechtigung"
        )

    # Datei aus Storage laden
    storage = get_storage_service()
    try:
        file_content = await storage.download_document(document.file_path)
    except Exception as e:
        logger.error(
            "document_preview_storage_error",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Laden der Datei"
        )

    mime_type = document.mime_type or "application/octet-stream"

    # Browser-native Formate direkt zurückgeben
    browser_native = ["image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"]
    if mime_type in browser_native:
        return Response(
            content=file_content,
            media_type=mime_type,
            headers={"Content-Disposition": "inline"}
        )

    # TIFF, BMP und andere Bilder zu PNG konvertieren
    if mime_type.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(file_content))
            # Konvertiere zu RGB falls nötig (für CMYK, etc.)
            if img.mode in ("CMYK", "P", "LA", "RGBA"):
                img = img.convert("RGB")

            output = io.BytesIO()
            img.save(output, format="PNG", optimize=True)
            output.seek(0)

            logger.info(
                "document_preview_converted",
                document_id=str(document_id),
                original_type=mime_type,
                converted_to="image/png"
            )

            return Response(
                content=output.getvalue(),
                media_type="image/png",
                headers={"Content-Disposition": "inline"}
            )
        except Exception as e:
            logger.error(
                "document_preview_conversion_error",
                document_id=str(document_id),
                **safe_error_log(e)
            )
            raise HTTPException(
                status_code=500,
                detail="Fehler bei der Bildkonvertierung"
            )

    # Fallback: Original zurückgeben
    return Response(
        content=file_content,
        media_type=mime_type,
        headers={"Content-Disposition": "inline"}
    )


@router.get("/{document_id}/thumbnail")
async def get_document_thumbnail(
    document_id: UUID,
    width: int = 120,
    height: int = 160,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Generiert ein Thumbnail für das Dokument.

    Erstellt ein kleines Vorschaubild für schnelle Anzeige in Listen/Chats.
    Thumbnails werden gecached für Performance.

    **Query Parameters:**
    - width: Breite in Pixel (default: 120)
    - height: Höhe in Pixel (default: 160)

    **Response:**
    - Content-Type: image/jpeg
    - Inline-Anzeige
    """
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, DocumentAccess
    from sqlalchemy import select, or_, and_
    from PIL import Image
    import io

    # Limit dimensions for security
    width = min(max(width, 50), 400)
    height = min(max(height, 50), 600)

    # Prüfe Zugriff (Owner oder via DocumentAccess)
    access_query = select(Document).where(
        and_(
            Document.id == document_id,
            or_(
                Document.owner_id == current_user.id,
                Document.id.in_(
                    select(DocumentAccess.document_id).where(
                        and_(
                            DocumentAccess.user_id == current_user.id,
                            or_(
                                DocumentAccess.access_level == "view",
                                DocumentAccess.access_level == "comment",
                                DocumentAccess.access_level == "edit",
                                DocumentAccess.access_level == "manage"
                            )
                        )
                    )
                )
            )
        )
    )

    result = await db.execute(access_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Zugriffsberechtigung"
        )

    storage = get_storage_service()
    mime_type = document.mime_type or "application/octet-stream"

    try:
        # Check for cached thumbnail first
        cache_key = f"thumbnails/{document_id}_{width}x{height}.jpg"
        try:
            cached = await storage.download_document(cache_key)
            if cached:
                return Response(
                    content=cached,
                    media_type="image/jpeg",
                    headers={
                        "Content-Disposition": "inline",
                        "Cache-Control": "public, max-age=86400"  # 24h cache
                    }
                )
        except Exception as e:
            logger.debug(
                "thumbnail_cache_miss",
                document_id=str(document_id)[:8],
                error_type=type(e).__name__,
            )

        # Load original file
        file_content = await storage.download_document(document.file_path)

        # Generate thumbnail based on file type
        if mime_type == "application/pdf":
            # PDF: render first page
            import fitz  # PyMuPDF
            pdf = fitz.open(stream=file_content, filetype="pdf")
            if len(pdf) > 0:
                page = pdf[0]
                # Scale to fit thumbnail size
                zoom = min(width / page.rect.width, height / page.rect.height)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            else:
                raise HTTPException(status_code=500, detail="PDF hat keine Seiten")
            pdf.close()

        elif mime_type.startswith("image/"):
            # Image: resize directly
            img = Image.open(io.BytesIO(file_content))
            if img.mode in ("CMYK", "P", "LA", "RGBA"):
                img = img.convert("RGB")

        else:
            # Unsupported format
            raise HTTPException(
                status_code=400,
                detail="Thumbnail-Generierung für diesen Dateityp nicht unterstützt"
            )

        # Resize to thumbnail maintaining aspect ratio
        img.thumbnail((width, height), Image.Resampling.LANCZOS)

        # Convert to JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85, optimize=True)
        thumbnail_bytes = output.getvalue()

        # Cache thumbnail (fire and forget)
        try:
            await storage.upload_document(
                cache_key,
                thumbnail_bytes,
                content_type="image/jpeg"
            )
        except Exception as cache_err:
            logger.warning("thumbnail_cache_failed", error=str(cache_err))

        logger.info(
            "thumbnail_generated",
            document_id=str(document_id),
            size=f"{width}x{height}"
        )

        return Response(
            content=thumbnail_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "public, max-age=86400"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "thumbnail_generation_error",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Thumbnail-Generierung"
        )


@router.get("/{document_id}/stream")
async def stream_document_download(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument als Stream herunterladen (für große Dateien).

    Speichereffizientes Streaming für Dokumente > 10 MB.
    Verwendet chunked transfer encoding für minimalen Speicherverbrauch.

    **Response:**
    - Streaming-Response mit chunked transfer encoding
    - Content-Type basierend auf Dokumenttyp

    **Vorteile gegenüber regulärem Download:**
    - Konstanter Speicherverbrauch (~1 MB)
    - Schnellerer erster Byte (Time to First Byte)
    - Keine Request-Timeouts bei großen Dateien

    **Beispiel:**
    ```
    curl -X GET /api/v1/documents/{id}/stream \\
      -H "Authorization: Bearer <token>" \\
      -o grosses_dokument.pdf
    ```
    """
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, DocumentAccess
    from sqlalchemy import select, or_, and_

    # Prüfe Zugriff (Owner oder via DocumentAccess)
    access_query = select(Document).where(
        and_(
            Document.id == document_id,
            or_(
                Document.owner_id == current_user.id,
                Document.id.in_(
                    select(DocumentAccess.document_id).where(
                        and_(
                            DocumentAccess.user_id == current_user.id,
                            or_(
                                DocumentAccess.expires_at.is_(None),
                                DocumentAccess.expires_at > datetime.now(timezone.utc)
                            )
                        )
                    )
                )
            )
        )
    )

    result = await db.execute(access_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder kein Zugriff"
        )

    # Dateigröße und Metadaten holen
    storage = get_storage_service()
    try:
        doc_info = await storage.get_document_info(document.file_path)
    except Exception as e:
        logger.error(
            "document_stream_info_error",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Abrufen der Dokumentinformationen"
        )

    filename = document.original_filename or document.filename
    content_type = document.mime_type or "application/octet-stream"

    async def generate_chunks():
        """Async Generator für Streaming-Chunks."""
        async for chunk in storage.stream_document(document.file_path):
            yield chunk

    logger.info(
        "document_streaming_started",
        document_id=str(document_id),
        user_id=str(current_user.id),
        filename=filename,
        size_bytes=doc_info.get("size", 0)
    )

    return StreamingResponse(
        generate_chunks(),
        media_type=content_type,
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
            "Content-Length": str(doc_info.get("size", 0)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        }
    )


@router.get("/{document_id}/download/pdf")
async def download_document_as_pdf(
    document_id: UUID,
    include_ocr_text: bool = Query(False, description="OCR-Text als Textlayer einbetten"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument als PDF exportieren.

    Konvertiert das Dokument zu PDF (falls es noch kein PDF ist)
    und gibt es zum Download zurück.

    **Parameter:**
    - include_ocr_text: Wenn True, wird der extrahierte OCR-Text
      als durchsuchbarer Textlayer eingebettet (PDF/A).

    **Beispiel:**
    ```
    curl -X GET /api/v1/documents/{id}/download/pdf?include_ocr_text=true \\
      -H "Authorization: Bearer <token>" \\
      -o dokument_searchable.pdf
    ```
    """
    from app.services.storage_service import get_storage_service
    from app.db.models import Document, DocumentAccess
    from sqlalchemy import select, or_, and_

    # Prüfe Zugriff
    access_query = select(Document).where(
        and_(
            Document.id == document_id,
            or_(
                Document.owner_id == current_user.id,
                Document.id.in_(
                    select(DocumentAccess.document_id).where(
                        and_(
                            DocumentAccess.user_id == current_user.id,
                            or_(
                                DocumentAccess.expires_at.is_(None),
                                DocumentAccess.expires_at > datetime.now(timezone.utc)
                            )
                        )
                    )
                )
            )
        )
    )
    result = await db.execute(access_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    if document.is_deleted:
        raise HTTPException(
            status_code=410,
            detail="Dokument wurde gelöscht"
        )

    # Wenn bereits PDF und kein OCR-Text gewünscht, direkt zurückgeben
    if document.mime_type == "application/pdf" and not include_ocr_text:
        storage = get_storage_service()
        file_content = await storage.download_file(document.file_path)
        filename = document.original_filename or document.filename
        if not filename.lower().endswith('.pdf'):
            filename = f"{filename}.pdf"

        return Response(
            content=file_content,
            media_type="application/pdf",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "Content-Length": str(len(file_content))
            }
        )

    # Bild zu PDF konvertieren oder OCR-Text einbetten
    try:
        from PIL import Image
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as reportlab_canvas

        storage = get_storage_service()
        file_content = await storage.download_file(document.file_path)

        # Bild laden
        if document.mime_type and document.mime_type.startswith("image/"):
            img = Image.open(BytesIO(file_content))

            # PDF erstellen
            pdf_buffer = BytesIO()
            # Bildgröße anpassen (max A4)
            img_width, img_height = img.size
            page_width, page_height = A4

            # Skalieren um auf Seite zu passen
            scale = min(page_width / img_width, page_height / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)

            # PDF mit reportlab erstellen
            c = reportlab_canvas.Canvas(pdf_buffer, pagesize=(new_width, new_height))

            # Bild temporär speichern
            img_temp = BytesIO()
            img.save(img_temp, format='PNG')
            img_temp.seek(0)

            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(img_temp), 0, 0, width=new_width, height=new_height)

            # OCR-Text als Textlayer hinzufügen (unsichtbar)
            if include_ocr_text and document.extracted_text:
                c.setFillColorRGB(1, 1, 1, alpha=0)  # Transparent
                c.setFont("Helvetica", 1)  # Sehr klein
                # Text am unteren Rand (unsichtbar aber durchsuchbar)
                text_obj = c.beginText(0, 0)
                text_obj.textLine(document.extracted_text[:5000])  # Max 5000 Zeichen
                c.drawText(text_obj)

            c.save()
            pdf_content = pdf_buffer.getvalue()

        elif document.mime_type == "application/pdf" and include_ocr_text:
            # PDF mit OCR-Text versehen (vereinfachte Implementierung)
            # Für vollständige Implementierung: PyPDF2 oder pikepdf verwenden
            pdf_content = file_content
            logger.info(
                "pdf_ocr_text_embedding_skipped",
                document_id=str(document_id),
                reason="Vollständige PDF/A-Konvertierung erfordert zusätzliche Bibliotheken"
            )
        else:
            pdf_content = file_content

        filename = document.original_filename or document.filename
        if not filename.lower().endswith('.pdf'):
            filename = f"{filename.rsplit('.', 1)[0]}.pdf"

        logger.info(
            "document_exported_as_pdf",
            document_id=str(document_id),
            user_id=str(current_user.id),
            include_ocr_text=include_ocr_text
        )

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "Content-Length": str(len(pdf_content))
            }
        )

    except ImportError as e:
        logger.warning(
            "pdf_export_missing_dependency",
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=501,
            detail="PDF-Export nicht verfügbar. Erforderliche Bibliotheken fehlen."
        )
    except Exception as e:
        logger.error(
            "pdf_export_error",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der PDF-Konvertierung"
        )


@router.put("/{document_id}", response_model=DocumentDetailResponse)
async def update_document(
    document_id: UUID,
    update: DocumentUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumentmetadaten aktualisieren.

    Erlaubt das Aendern von:
    - Dokumenttyp
    - Sprache
    - Tags
    - Benutzerdefinierte Metadaten

    HINWEIS: Archivierte Dokumente (GoBD) koennen nicht geaendert werden.
    """
    # GoBD: Unveraenderbarkeit pruefen
    try:
        await archive_service.validate_modification_allowed(db, document_id)
    except ImmutabilityViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.user_message_de
        )

    service = get_document_service()
    document = await service.update_document(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        document_type=update.document_type,
        language=update.language,
        tags=update.tags,
        metadata=update.metadata
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    logger.info(
        "document_updated_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return document


@router.patch("/{document_id}", response_model=DocumentDetailResponse)
async def partial_update_document(
    document_id: UUID,
    updates: DocumentPartialUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Partielle Dokumentaktualisierung (PATCH).

    Phase 2.1: Ermoeglicht das Aendern einzelner Felder:
    - **document_type**: Dokumenttyp aendern
    - **language**: Sprache aendern
    - **tags**: Alle Tags ersetzen
    - **add_tags**: Tags hinzufuegen (additiv)
    - **remove_tags**: Bestimmte Tags entfernen
    - **metadata**: Metadaten aktualisieren/erweitern

    Nur angegebene Felder werden aktualisiert.
    Tag-Operationen sind gegenseitig exklusiv.

    HINWEIS: Archivierte Dokumente (GoBD) koennen nicht geaendert werden.
    """
    # GoBD: Unveraenderbarkeit pruefen
    try:
        await archive_service.validate_modification_allowed(db, document_id)
    except ImmutabilityViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.user_message_de
        )

    service = get_document_service()

    # Build update dict from non-None fields
    update_data: Dict[str, Any] = {}

    if updates.document_type is not None:
        update_data["document_type"] = updates.document_type
    if updates.language is not None:
        update_data["language"] = updates.language
    if updates.metadata is not None:
        update_data["metadata"] = updates.metadata

    # Handle tag operations
    tag_operation = None
    tag_values = None
    if updates.tags is not None:
        tag_operation = "set"
        tag_values = updates.tags
    elif updates.add_tags is not None:
        tag_operation = "add"
        tag_values = updates.add_tags
    elif updates.remove_tags is not None:
        tag_operation = "remove"
        tag_values = updates.remove_tags

    document = await service.partial_update_document(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        updates=update_data,
        tag_operation=tag_operation,
        tag_values=tag_values
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    logger.info(
        "document_partial_updated_api",
        document_id=str(document_id),
        user_id=str(current_user.id),
        updated_fields=list(update_data.keys()) + ([f"tags_{tag_operation}"] if tag_operation else [])
    )

    return document


# =============================================================================
# EXTRACTED DATA UPDATE ENDPOINT (Phase 11: InlineMetadataEditor Backend)
# =============================================================================

# Whitelist fuer erlaubte extracted_data Pfade
# SECURITY: Verhindert SQL/NoSQL Injection und unbeabsichtigte Datenmanipulation
ALLOWED_EXTRACTED_DATA_PATHS: set[str] = {
    # Invoice Daten
    "invoice.invoice_number",
    "invoice.invoice_date",
    "invoice.due_date",
    "invoice.total_gross",
    "invoice.total_net",
    "invoice.vat_amount",
    "invoice.vat_rate",
    "invoice.currency",
    "invoice.payment_reference",
    "invoice.invoice_direction",
    "invoice.needs_review",
    # Vendor (Lieferant)
    "invoice.vendor.name",
    "invoice.vendor.street",
    "invoice.vendor.city",
    "invoice.vendor.postal_code",
    "invoice.vendor.country",
    "invoice.vendor.vat_id",
    # Customer (Kunde)
    "invoice.customer.name",
    "invoice.customer.street",
    "invoice.customer.city",
    "invoice.customer.postal_code",
    "invoice.customer.country",
    # Klassifikation
    "classification.document_type",
    "classification.confidence",
    # Extrahierte Daten
    "ibans",
    "vat_ids",
    "companies",
}


def _set_nested_value(obj: Dict[str, Any], path: str, value: Any) -> None:
    """Setzt einen verschachtelten Wert in einem Dict.

    Args:
        obj: Das zu modifizierende Dictionary
        path: Punkt-separierter Pfad (z.B. 'invoice.vendor.name')
        value: Der zu setzende Wert

    Security:
        - Pfad wird NICHT validiert - muss vorher gegen Whitelist geprueft werden!
    """
    parts = path.split('.')
    current = obj

    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        elif not isinstance(current[part], dict):
            # Wenn der aktuelle Wert kein Dict ist, ersetzen
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


class ExtractedDataUpdateRequest(BaseModel):
    """Request-Schema fuer extracted_data Updates.

    SECURITY:
    - Alle Pfade werden gegen ALLOWED_EXTRACTED_DATA_PATHS validiert
    - Werte werden typgeprueft (keine Code-Injection)
    """
    updates: Dict[str, Any] = Field(
        ...,
        description="JSONB-Pfade mit neuen Werten",
        json_schema_extra={
            "example": {
                "invoice.invoice_number": "RG-2024-001",
                "invoice.total_gross": 1234.56,
                "invoice.vendor.name": "Lieferant GmbH"
            }
        }
    )

    class Config:
        extra = "forbid"  # Keine zusaetzlichen Felder erlaubt


@router.patch(
    "/{document_id}/extracted-data",
    response_model=Dict[str, Any],
    summary="Extrahierte Daten aktualisieren",
    responses={
        200: {"description": "Aktualisierte extracted_data"},
        400: {"description": "Ungueltige Feldpfade oder Werte"},
        403: {"description": "Archiviertes Dokument (GoBD)"},
        404: {"description": "Dokument nicht gefunden"},
    }
)
async def update_extracted_data(
    document_id: UUID,
    request: ExtractedDataUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Aktualisiert einzelne Felder in extracted_data (JSONB).

    Ermoeglicht die Korrektur von OCR-Ergebnissen durch den Benutzer.
    Nur vordefinierte Feldpfade sind erlaubt (Whitelist-Validierung).

    **Erlaubte Pfade:**
    - `invoice.*`: Rechnungsdaten (invoice_number, total_gross, etc.)
    - `invoice.vendor.*`: Lieferanten-Informationen
    - `invoice.customer.*`: Kunden-Informationen
    - `classification.*`: Dokumenttyp und Confidence
    - `ibans`, `vat_ids`, `companies`: Arrays

    **Security:**
    - Multi-Tenant RLS: owner_id == current_user.id
    - Whitelist-Validierung aller Feldpfade
    - GoBD: Archivierte Dokumente sind unveraenderbar

    **Beispiel:**
    ```json
    {
      "updates": {
        "invoice.invoice_number": "RG-2024-001",
        "invoice.total_gross": 1234.56,
        "invoice.vendor.name": "Neue Firma GmbH"
      }
    }
    ```

    Returns:
        Das aktualisierte extracted_data Objekt
    """
    from sqlalchemy import select, and_
    from app.db.models import Document

    # 1. GoBD: Unveraenderbarkeit pruefen
    try:
        await archive_service.validate_modification_allowed(db, document_id)
    except ImmutabilityViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.user_message_de
        )

    # 2. Dokument laden mit Ownership-Check (Multi-Tenant RLS)
    result = await db.execute(
        select(Document).where(
            and_(
                Document.id == document_id,
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
            )
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    if not document.extracted_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine extrahierten Daten vorhanden"
        )

    # 3. Validiere alle Pfade gegen Whitelist (SECURITY!)
    invalid_paths: List[str] = []
    for path in request.updates.keys():
        if path not in ALLOWED_EXTRACTED_DATA_PATHS:
            invalid_paths.append(path)

    if invalid_paths:
        logger.warning(
            "extracted_data_invalid_paths",
            document_id=str(document_id),
            user_id=str(current_user.id),
            invalid_paths=invalid_paths,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige Feldpfade: {', '.join(invalid_paths)}"
        )

    # 4. Update mit Typ-Sicherheit
    updated_data = dict(document.extracted_data)  # Kopie erstellen
    for path, value in request.updates.items():
        _set_nested_value(updated_data, path, value)

    # 5. Speichern
    document.extracted_data = updated_data
    document.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(document)

    logger.info(
        "extracted_data_updated",
        document_id=str(document_id),
        user_id=str(current_user.id),
        fields_updated=len(request.updates),
        # SECURITY: Keine Feldwerte loggen!
    )

    return document.extracted_data


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument loeschen.

    Loescht das Dokument vollstaendig aus der Datenbank
    und dem Objektspeicher (MinIO).

    HINWEIS: Archivierte Dokumente (GoBD) koennen nicht geloescht werden
    bis die Aufbewahrungsfrist abgelaufen ist.
    """
    # GoBD: Unveraenderbarkeit pruefen (archivierte Dokumente duerfen nicht geloescht werden)
    try:
        await archive_service.validate_modification_allowed(db, document_id)
    except ImmutabilityViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=e.user_message_de
        )

    service = get_document_service()
    success = await service.delete_document(db, document_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    logger.info(
        "document_deleted_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return Response(status_code=204)


# ==================== Document Report ====================

@router.get("/{document_id}/report")
async def get_document_report(
    document_id: UUID,
    include_text: bool = Query(True, description="Extrahierten Text einschliessen"),
    include_history: bool = Query(True, description="Verarbeitungshistorie einschliessen"),
    include_entities: bool = Query(True, description="Erkannte Entitaeten einschliessen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Detaillierten PDF-Bericht fuer ein Dokument generieren.

    Erstellt einen umfassenden PDF-Bericht mit:
    - Dokumentinformationen (Dateiname, Typ, Status, Groesse)
    - OCR-Ergebnisse (Backend, Konfidenz, Wortanzahl)
    - Erkannte Entitaeten (Datumsangaben, Geldbetraege, IBAN, USt-IdNr.)
    - Deutsche Textvalidierung (Umlaute, Sprache)
    - Extrahierter Text (optional, max. 5000 Zeichen)
    - Verarbeitungshistorie (optional)

    Der Bericht wird im A4-Format generiert und ist
    fuer Archivierung und Nachvollziehbarkeit geeignet.
    """
    from app.services.document_report_service import get_document_report_service

    try:
        service = get_document_report_service()
        pdf_bytes = await service.generate_document_report(
            db=db,
            document_id=document_id,
            user_id=current_user.id,
            include_text=include_text,
            include_history=include_history,
            include_entities=include_entities
        )
    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")

    # Filename fuer Download
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dokument_bericht_{str(document_id)[:8]}_{timestamp}.pdf"

    logger.info(
        "document_report_generated_api",
        document_id=str(document_id),
        user_id=str(current_user.id),
        size_bytes=len(pdf_bytes)
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
            "Content-Length": str(len(pdf_bytes))
        }
    )


# ==================== Similar Documents ====================

@router.get("/{document_id}/similar", response_model=List[SimilarDocumentItem])
async def get_similar_documents(
    document_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Maximale Anzahl Ergebnisse"),
    similarity_threshold: float = Query(0.6, ge=0, le=1, description="Min. Aehnlichkeit"),
    exclude_same_type: bool = Query(False, description="Gleichen Dokumenttyp ausschliessen"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Aehnliche Dokumente basierend auf Inhalt finden.

    Verwendet semantische Embeddings um inhaltlich aehnliche
    Dokumente zu identifizieren. Nuetzlich fuer:
    - Duplikaterkennung
    - Thematisch verwandte Dokumente
    - Dokumentengruppierung
    """
    # Pruefen ob Dokument existiert und Zugriff erlaubt
    doc_service = get_document_service()
    document = await doc_service.get_document(db, document_id, current_user.id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    if not document.has_embedding:
        raise HTTPException(
            status_code=400,
            detail="Dokument hat kein Embedding. Bitte OCR-Verarbeitung durchfuehren."
        )

    search_service = get_search_service()
    return await search_service.find_similar_documents(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        limit=limit,
        similarity_threshold=similarity_threshold,
        exclude_same_type=exclude_same_type
    )


# ==================== Batch Operations ====================

FORCE_CONFIRM_THRESHOLD = 50  # Ab dieser Anzahl ist X-Force-Confirm erforderlich


@router.post("/batch/fetch", response_model=BatchFetchResponse)
async def batch_fetch_documents(
    request: BatchFetchRequest,
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente in einem API-Call abrufen.

    Optimiert fuer Frontend-Dashboard-Ansichten und Dokumentenlisten.
    Reduziert Netzwerk-Overhead durch gebündelte Anfragen.

    **Limits:**
    - Maximal 50 Dokumente pro Anfrage
    - include_text=true erhoeht Response-Groesse signifikant

    **Beispiel:**
    ```
    POST /api/v1/documents/batch/fetch
    {
        "document_ids": ["uuid1", "uuid2", "uuid3"],
        "include_text": false,
        "include_ocr_metadata": true
    }
    ```

    **Response:**
    - `found`: Anzahl gefundener Dokumente
    - `not_found`: Anzahl nicht gefundener IDs
    - `not_found_ids`: Liste der nicht gefundenen IDs
    """
    from app.db.models import Document
    from sqlalchemy import select

    doc_count = len(request.document_ids)

    logger.info(
        "batch_fetch_request",
        count=doc_count,
        user_id=str(current_user.id),
        include_text=request.include_text
    )

    # Query documents owned by user
    query = select(Document).where(
        Document.id.in_(request.document_ids),
        Document.owner_id == current_user.id,
        Document.deleted_at.is_(None)  # Nur nicht-geloeschte Dokumente
    )

    result = await db.execute(query)
    documents = result.scalars().all()

    # Build response
    found_ids = {doc.id for doc in documents}
    not_found_ids = [doc_id for doc_id in request.document_ids if doc_id not in found_ids]

    # Convert to response models
    document_responses = []
    for doc in documents:
        doc_response = DocumentDetailResponse(
            id=doc.id,
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            document_type=doc.document_type,
            status=doc.status,
            owner_id=doc.owner_id,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            processed_date=doc.processed_date,
            tags=doc.tags or [],
            # OCR metadata (optional)
            confidence_score=doc.confidence_score if request.include_ocr_metadata else None,
            ocr_backend_used=doc.ocr_backend_used if request.include_ocr_metadata else None,
            word_count=doc.word_count if request.include_ocr_metadata else None,
            page_count=doc.page_count if request.include_ocr_metadata else None,
            language=doc.language if request.include_ocr_metadata else None,
            # Text (optional - can be large)
            extracted_text=doc.extracted_text if request.include_text else None,
        )
        document_responses.append(doc_response)

    logger.info(
        "batch_fetch_completed",
        requested=doc_count,
        found=len(documents),
        not_found=len(not_found_ids),
        user_id=str(current_user.id)
    )

    return BatchFetchResponse(
        success=True,
        total_requested=doc_count,
        found=len(documents),
        not_found=len(not_found_ids),
        documents=document_responses,
        not_found_ids=not_found_ids
    )


@router.post("/batch/delete", response_model=BatchOperationResult)
async def batch_delete_documents(
    request_obj: Request,
    request: BatchDeleteRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente gleichzeitig loeschen.

    **Safeguards:**
    - `confirm: true` erforderlich
    - `dry_run: true` fuer Simulation ohne Loeschung
    - Header `X-Force-Confirm: DELETE-{anzahl}` erforderlich bei >50 Dokumenten

    **Beispiel fuer 75 Dokumente:**
    ```
    POST /documents/batch/delete
    X-Force-Confirm: DELETE-75
    {"document_ids": [...], "confirm": true}
    ```

    Maximal 100 Dokumente pro Anfrage.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400,
            detail="Loeschung muss mit confirm=true bestaetigt werden"
        )

    # Explizite Batch-Groessen-Validierung (Defense in Depth)
    MAX_BATCH_SIZE = 100
    doc_count = len(request.document_ids)
    if doc_count > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximal {MAX_BATCH_SIZE} Dokumente pro Anfrage. Erhalten: {doc_count}"
        )
    if doc_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Mindestens ein Dokument muss angegeben werden"
        )

    # Zusaetzliche Sicherheit bei grossen Batches
    if doc_count > FORCE_CONFIRM_THRESHOLD and not request.dry_run:
        force_confirm = request_obj.headers.get("X-Force-Confirm")
        expected_confirm = f"DELETE-{doc_count}"

        if not force_confirm:
            raise HTTPException(
                status_code=400,
                detail=f"Bei mehr als {FORCE_CONFIRM_THRESHOLD} Dokumenten ist der Header "
                       f"'X-Force-Confirm: {expected_confirm}' erforderlich. "
                       f"Nutzen Sie dry_run=true um die Operation zu simulieren."
            )

        if force_confirm != expected_confirm:
            raise HTTPException(
                status_code=400,
                detail=f"X-Force-Confirm Header ungueltig. Erwartet: '{expected_confirm}', "
                       f"erhalten: '{force_confirm}'"
            )

    logger.info(
        "batch_delete_request",
        count=doc_count,
        user_id=str(current_user.id),
        dry_run=request.dry_run,
        force_confirmed=doc_count > FORCE_CONFIRM_THRESHOLD
    )

    service = get_document_service()
    return await service.batch_delete(
        db=db,
        document_ids=request.document_ids,
        user_id=current_user.id,
        dry_run=request.dry_run
    )


@router.post("/batch/tag", response_model=BatchOperationResult)
async def batch_tag_documents(
    request: BatchTagRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Tags fuer mehrere Dokumente verwalten.

    Operationen:
    - **add**: Tags hinzufuegen (Standard)
    - **remove**: Tags entfernen
    - **set**: Alle Tags ersetzen

    Maximal 100 Dokumente pro Anfrage.
    """
    logger.info(
        "batch_tag_request",
        count=len(request.document_ids),
        operation=request.operation.value,
        tags=request.tags,
        user_id=str(current_user.id)
    )

    service = get_document_service()
    return await service.batch_tag(
        db=db,
        document_ids=request.document_ids,
        tags=request.tags,
        user_id=current_user.id,
        operation=request.operation
    )


@router.post("/batch/update", response_model=BulkUpdateResult)
async def batch_update_documents(
    request: BulkUpdateRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente gleichzeitig aktualisieren.

    Phase 2.2: Bulk-Update basierend auf Filterkriterien.

    Filter-Optionen:
    - **document_ids**: Liste spezifischer IDs (max. 100)
    - **document_type**: Nach Dokumenttyp filtern
    - **status**: Nach Verarbeitungsstatus filtern
    - **date_from/date_to**: Nach Erstellungsdatum filtern
    - **tags**: Nach Tags filtern

    Update-Optionen:
    - **document_type**: Dokumenttyp aendern
    - **language**: Sprache aendern
    - **tags/add_tags/remove_tags**: Tag-Operationen

    Mit **dry_run: true** kann die Operation simuliert werden.
    """
    logger.info(
        "batch_update_request",
        filter=request.filter.model_dump(exclude_none=True),
        updates=request.updates.model_dump(exclude_none=True),
        dry_run=request.dry_run,
        user_id=str(current_user.id)
    )

    service = get_document_service()
    result = await service.bulk_update(
        db=db,
        user_id=current_user.id,
        filter_criteria=request.filter,
        updates=request.updates,
        dry_run=request.dry_run
    )

    return result


@router.post("/batch/export")
async def batch_export_documents(
    request: BatchExportRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente exportieren.

    Exportformate:
    - **json**: JSON-Array mit Dokumentdaten
    - **csv**: CSV-Tabelle (Text gekuerzt auf 1000 Zeichen)
    - **zip**: ZIP-Archiv mit einzelnen JSON-Dateien

    Maximal 100 Dokumente pro Anfrage.
    """
    logger.info(
        "batch_export_request",
        count=len(request.document_ids),
        format=request.format.value,
        user_id=str(current_user.id)
    )

    service = get_document_service()
    export_data, content_type, result = await service.batch_export(
        db=db,
        document_ids=request.document_ids,
        user_id=current_user.id,
        format=request.format,
        include_text=request.include_text,
        include_metadata=request.include_metadata
    )

    # Filename basierend auf Format
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    extension_map = {
        ExportFormat.JSON: "json",
        ExportFormat.CSV: "csv",
        ExportFormat.ZIP: "zip",
        ExportFormat.PDF: "pdf"
    }
    extension = extension_map.get(request.format, "json")
    filename = f"dokumente_export_{timestamp}.{extension}"

    return StreamingResponse(
        io.BytesIO(export_data),
        media_type=content_type,
        headers={
            # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
            "Content-Disposition": build_content_disposition(filename, "attachment"),
            "X-Export-Count": str(result.processed),
            "X-Export-Failed": str(result.failed)
        }
    )


# ==================== Soft-Delete (GDPR Phase 2.3) ====================

@router.post("/{document_id}/soft-delete", response_model=SoftDeleteResponse)
async def soft_delete_document(
    document_id: UUID,
    request: SoftDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument soft-loeschen (GDPR-konform).

    Phase 2.3: Markiert ein Dokument als geloescht, ohne es sofort
    permanent zu entfernen. Das Dokument kann innerhalb von 30 Tagen
    wiederhergestellt werden.

    Nach 30 Tagen wird das Dokument automatisch permanent geloescht.
    """
    service = get_document_service()
    result = await service.soft_delete_document(
        db=db,
        document_id=document_id,
        user_id=current_user.id,
        reason=request.reason
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder bereits geloescht"
        )

    logger.info(
        "document_soft_deleted_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return result


@router.post("/{document_id}/restore", response_model=RestoreDocumentResponse)
async def restore_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft-geloeschtes Dokument wiederherstellen.

    Phase 2.3: Stellt ein geloeschtes Dokument wieder her,
    sofern die 30-Tage-Frist noch nicht abgelaufen ist.
    """
    service = get_document_service()

    try:
        result = await service.restore_document(
            db=db,
            document_id=document_id,
            user_id=current_user.id
        )
    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="Wiederherstellung fehlgeschlagen. Bitte Eingaben pruefen.")

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden oder nicht geloescht"
        )

    logger.info(
        "document_restored_api",
        document_id=str(document_id),
        user_id=str(current_user.id)
    )

    return result


@router.get("/deleted/list", response_model=DeletedDocumentsListResponse)
async def list_deleted_documents(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Alle soft-geloeschten Dokumente auflisten.

    Phase 2.3: Zeigt alle geloeschten Dokumente des Benutzers mit
    der verbleibenden Zeit bis zur permanenten Loeschung.
    """
    service = get_document_service()
    return await service.list_deleted_documents(db=db, user_id=current_user.id)


# ==================== Document Classification Confirmation ====================


class ClassificationConfirmRequest(BaseModel):
    """Request zum Bestaetigen/Aendern der Dokumentklassifizierung."""
    invoice_direction: Literal["incoming", "outgoing"]
    user_overridden: bool = False


@router.post("/{document_id}/confirm-classification")
async def confirm_document_classification(
    document_id: UUID,
    request: ClassificationConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Bestaetigt oder aendert die Dokumentklassifizierung (Eingangs-/Ausgangsrechnung).

    Setzt den entsprechenden Tag am Dokument und aktualisiert optional
    die extrahierten Daten wenn der Benutzer die automatische Erkennung
    ueberschrieben hat.

    **Workflow:**
    1. Dokument laden und Berechtigung pruefen
    2. Alten Richtungs-Tag entfernen (falls vorhanden)
    3. Neuen Tag (Eingangsrechnung/Ausgangsrechnung) hinzufuegen
    4. Bei Ueberschreibung: extracted_data aktualisieren
    """
    from app.db.models import Tag, Document
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Dokument direkt laden (nicht über Service, da wir das SQLAlchemy-Modell brauchen)
    query = (
        select(Document)
        .options(selectinload(Document.tags))
        .where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None)
        )
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden"
        )

    # Tag-Name basierend auf Direction
    tag_name = "Eingangsrechnung" if request.invoice_direction == "incoming" else "Ausgangsrechnung"
    opposite_tag_name = "Ausgangsrechnung" if request.invoice_direction == "incoming" else "Eingangsrechnung"

    # Alten Richtungs-Tag entfernen falls vorhanden
    doc.tags = [t for t in doc.tags if t.name not in [tag_name, opposite_tag_name]]

    # Neuen Tag holen oder erstellen
    query = select(Tag).where(Tag.name == tag_name)
    result = await db.execute(query)
    tag = result.scalar_one_or_none()

    if not tag:
        # Tag erstellen falls nicht vorhanden
        tag = Tag(name=tag_name, description=f"Automatisch erkannte {tag_name}")
        db.add(tag)
        await db.flush()

    # Tag zum Dokument hinzufuegen
    doc.tags.append(tag)

    # Extracted Data aktualisieren falls user_overridden
    if request.user_overridden and doc.extracted_data:
        extracted = dict(doc.extracted_data) if doc.extracted_data else {}
        if "invoice" in extracted:
            extracted["invoice"]["invoice_direction"] = request.invoice_direction
            extracted["invoice"]["invoice_direction_user_confirmed"] = True
            doc.extracted_data = extracted

    await db.commit()

    logger.info(
        "document_classification_confirmed",
        document_id=str(document_id),
        user_id=str(current_user.id),
        direction=request.invoice_direction,
        tag_applied=tag_name,
        user_overridden=request.user_overridden
    )

    return {
        "status": "success",
        "document_id": str(document_id),
        "applied_tag": tag_name,
        "invoice_direction": request.invoice_direction
    }


# ==================== Rename Suggestion Confirmation ====================


class RenameConfirmRequest(BaseModel):
    """Request fuer Dokumenten-Umbenennung."""
    suggested_filename: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Vorgeschlagener Dateiname (ohne Extension)"
    )


@router.post("/{document_id}/confirm-rename")
async def confirm_document_rename(
    document_id: UUID,
    request: RenameConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Bestaetigt die Umbenennung eines Dokuments basierend auf dem Vorschlag.

    Wird aufgerufen wenn der User den Umbenennungs-Vorschlag aus der
    Quick Classification akzeptiert.

    **Workflow:**
    1. Dokument laden und Berechtigung pruefen
    2. Dateinamen sanitisieren und Extension beibehalten
    3. Datenbank aktualisieren (filename, quick_classification_result)

    **Hinweis:** Die original_filename bleibt fuer Audit-Zwecke erhalten.
    """
    from app.db.models import Document
    from sqlalchemy import select
    from pathlib import Path
    import re

    # Dokument laden
    query = select(Document).where(
        Document.id == document_id,
        Document.owner_id == current_user.id,
        Document.deleted_at.is_(None)
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden"
        )

    old_filename = doc.filename

    # Extension vom alten Dateinamen beibehalten
    ext = Path(old_filename).suffix

    # Dateinamen sanitisieren (gefaehrliche Zeichen entfernen)
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', request.suggested_filename)
    sanitized_name = sanitized_name[:200]  # Maximale Laenge

    # Neuen Dateinamen zusammenbauen
    new_filename = f"{sanitized_name}{ext}"

    # Dateinamen aktualisieren
    doc.filename = new_filename

    # Source fuer Metriken extrahieren (vor dem Update)
    rename_source = "unknown"
    if doc.quick_classification_result:
        qc_result = dict(doc.quick_classification_result)
        if qc_result.get("rename_suggestion"):
            rename_source = qc_result["rename_suggestion"].get("source", "unknown")
            # Als "applied" markieren
            qc_result["rename_suggestion"]["applied"] = True
            qc_result["rename_suggestion"]["applied_filename"] = new_filename
            doc.quick_classification_result = qc_result

    # Datenbank-Commit mit Error Handling
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(
            "document_rename_failed",
            document_id=str(document_id),
            user_id=str(current_user.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Umbenennung fehlgeschlagen"
        )

    # Audit Logging (GDPR-konform)
    from app.core.audit_logger import AuditLogger, AuditEventType
    try:
        await AuditLogger.log_async(
            db=db,
            user_id=current_user.id,
            action=AuditEventType.DOCUMENT_RENAMED,
            resource_type="document",
            resource_id=str(document_id),
            details={
                "old_filename": old_filename,
                "new_filename": new_filename,
                "source": rename_source
            }
        )
    except Exception as audit_error:
        # Audit-Fehler loggen aber nicht die Operation abbrechen
        logger.warning(
            "audit_log_failed",
            document_id=str(document_id),
            error=str(audit_error)
        )

    # Prometheus Metrics
    from app.core.business_metrics import document_renames_total
    document_renames_total.labels(source=rename_source).inc()

    logger.info(
        "document_renamed",
        document_id=str(document_id),
        user_id=str(current_user.id),
        old_filename=old_filename,
        new_filename=new_filename,
        source=rename_source
    )

    return {
        "success": True,
        "document_id": str(document_id),
        "old_filename": old_filename,
        "new_filename": new_filename,
        "message": "Dokument erfolgreich umbenannt"
    }


# ==================== Cleanup and Maintenance ====================

@router.post("/{document_id}/cleanup")
async def cleanup_document_resources(
    document_id: UUID,
    clear_cache: bool = Query(True, description="Cache fuer dieses Dokument loeschen"),
    clear_temp_files: bool = Query(True, description="Temporaere Dateien loeschen"),
    clear_gpu_memory: bool = Query(False, description="GPU-Speicher freigeben (VRAM)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Ressourcen fuer ein Dokument bereinigen.

    Nuetzlich nach der Verarbeitung um:
    - Temporaere Dateien zu loeschen
    - Caches zu invalidieren
    - GPU-Speicher freizugeben

    **Hinweis**: GPU-Speicher-Freigabe ist eine globale Operation und
    kann andere laufende Verarbeitungen beeinflussen.
    """
    from app.services.storage_service import get_storage_service
    from app.services.ocr_cache_service import get_ocr_cache_service

    # Dokument existiert und gehoert dem Benutzer?
    service = get_document_service()
    doc = await service.get_document(db=db, document_id=document_id, user_id=current_user.id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    cleanup_results = {
        "document_id": str(document_id),
        "cache_cleared": False,
        "temp_files_cleared": False,
        "gpu_memory_cleared": False,
        "errors": []
    }

    # 1. Cache loeschen
    if clear_cache:
        try:
            cache_service = get_ocr_cache_service()
            await cache_service.invalidate_document_cache(str(document_id))

            search_service = get_search_service()
            await search_service.invalidate_document_cache(
                document_id, current_user.id, reason="manual_cleanup"
            )
            cleanup_results["cache_cleared"] = True
        except Exception as e:
            cleanup_results["errors"].append("Cache-Bereinigung fehlgeschlagen")
            logger.warning("cleanup_cache_failed", document_id=str(document_id), **safe_error_log(e))

    # 2. Temporaere Dateien loeschen
    if clear_temp_files:
        try:
            import shutil
            from pathlib import Path

            temp_dir = Path("data/temp") / str(document_id)
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                cleanup_results["temp_files_cleared"] = True
            else:
                cleanup_results["temp_files_cleared"] = True  # Keine temp files = bereits bereinigt
        except Exception as e:
            cleanup_results["errors"].append("Temp-Bereinigung fehlgeschlagen")
            logger.warning("cleanup_temp_failed", document_id=str(document_id), **safe_error_log(e))

    # 3. GPU-Speicher freigeben (optional, globale Auswirkung)
    if clear_gpu_memory:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

                # Aktuelle Speichernutzung nach Bereinigung
                memory_allocated = torch.cuda.memory_allocated() / (1024 ** 3)
                memory_reserved = torch.cuda.memory_reserved() / (1024 ** 3)

                cleanup_results["gpu_memory_cleared"] = True
                cleanup_results["gpu_memory_after"] = {
                    "allocated_gb": round(memory_allocated, 2),
                    "reserved_gb": round(memory_reserved, 2)
                }
            else:
                cleanup_results["gpu_memory_cleared"] = False
                cleanup_results["errors"].append("GPU nicht verfuegbar")
        except Exception as e:
            cleanup_results["errors"].append("GPU-Bereinigung fehlgeschlagen")
            logger.warning("cleanup_gpu_failed", document_id=str(document_id), **safe_error_log(e))

    cleanup_results["success"] = len(cleanup_results["errors"]) == 0

    logger.info(
        "document_cleanup_completed",
        document_id=str(document_id),
        user_id=str(current_user.id),
        results=cleanup_results
    )

    return cleanup_results


@router.post("/{document_id}/validate-german")
async def validate_german_text(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Validiert den extrahierten Text eines Dokuments auf deutsche Sprachmerkmale.

    Prueft auf:
    - Umlaute (ae, oe, ue, ss)
    - Deutsche Datumsformate (TT.MM.JJJJ)
    - Waehrungsformate (1.234,56 EUR)
    - IBANs (DE...)
    - USt-IDs (DE...)
    - Geschaeftsbegriffe (Rechnung, Vertrag, etc.)

    Nuetzlich zur:
    - OCR-Qualitaetspruefung
    - Spracherkennung
    - Dokumentklassifizierung
    """
    from app.german_validator import GermanValidator

    # Dokument laden
    service = get_document_service()
    doc = await service.get_document(db=db, document_id=document_id, user_id=current_user.id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden"
        )

    # Extrahierten Text pruefen
    text = doc.extracted_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen extrahierten Text. Bitte zuerst OCR durchfuehren."
        )

    # German Validator initialisieren
    validator = GermanValidator()

    # Validierungen durchfuehren
    validation_result = {
        "document_id": str(document_id),
        "text_length": len(text),
        "word_count": len(text.split()),
        "validations": {}
    }

    # 1. Umlaute
    has_umlauts = validator.validate_umlauts(text)
    validation_result["validations"]["umlauts"] = {
        "present": has_umlauts,
        "description": "Deutsche Umlaute (ae, oe, ue, ss) erkannt"
    }

    # 2. Datumsformate
    dates = validator.validate_date_format(text)
    validation_result["validations"]["dates"] = {
        "found": len(dates),
        "examples": dates[:5],  # Maximal 5 Beispiele
        "description": "Deutsche Datumsformate (TT.MM.JJJJ)"
    }

    # 3. Waehrungsformate
    amounts = validator.validate_currency_format(text)
    validation_result["validations"]["currency"] = {
        "found": len(amounts),
        "examples": amounts[:5],
        "description": "Deutsche Waehrungsformate (1.234,56 EUR)"
    }

    # 4. Geschaeftsbegriffe
    business_terms = validator.extract_business_terms(text)
    validation_result["validations"]["business_terms"] = {
        "found": len(business_terms),
        "terms": business_terms[:10],
        "description": "Deutsche Geschaeftsbegriffe (Rechnung, Vertrag, etc.)"
    }

    # 5. IBANs und USt-IDs
    ibans = []
    vat_ids = []
    words = text.split()
    for word in words:
        word_clean = word.strip(".,;:()[]")
        if word_clean.startswith("DE") and len(word_clean) == 22:
            if validator.validate_iban(word_clean):
                ibans.append(word_clean)
        elif word_clean.startswith("DE") and len(word_clean) == 11:
            if validator.validate_vat_id(word_clean):
                vat_ids.append(word_clean)

    validation_result["validations"]["iban"] = {
        "found": len(ibans),
        "examples": ibans[:3],
        "description": "Deutsche IBANs"
    }

    validation_result["validations"]["vat_id"] = {
        "found": len(vat_ids),
        "examples": vat_ids[:3],
        "description": "Deutsche USt-IDs"
    }

    # Gesamtbewertung
    is_german = (
        has_umlauts or
        len(dates) > 0 or
        len(amounts) > 0 or
        len(business_terms) >= 2 or
        len(ibans) > 0 or
        len(vat_ids) > 0
    )

    confidence = 0.0
    if has_umlauts:
        confidence += 0.3
    if len(dates) > 0:
        confidence += 0.2
    if len(amounts) > 0:
        confidence += 0.15
    if len(business_terms) >= 2:
        confidence += 0.2
    if len(ibans) > 0 or len(vat_ids) > 0:
        confidence += 0.15

    validation_result["is_german"] = is_german
    validation_result["confidence"] = min(confidence, 1.0)
    validation_result["quality_rating"] = (
        "hoch" if confidence >= 0.7 else
        "mittel" if confidence >= 0.4 else
        "niedrig"
    )

    logger.info(
        "german_validation_completed",
        document_id=str(document_id),
        is_german=is_german,
        confidence=confidence
    )

    return validation_result


# ==================== Statistics and Info ====================


async def _fetch_document_stats_uncached(
    db: AsyncSession,
    user_id: str
) -> dict:
    """
    Interne Funktion fuer Dokumentstatistiken (ohne Cache).

    Wird von get_document_stats aufgerufen mit optionalem Caching.
    """
    import asyncio
    from sqlalchemy import select, func
    from app.db.models import Document

    # Basis-Query fuer Benutzer
    base_filter = Document.owner_id == user_id

    # OPTIMIERUNG: Kombinierte Query mit allen Aggregationen
    combined_query = select(
        func.count(Document.id).label("total"),
        func.avg(Document.ocr_confidence).filter(
            Document.ocr_confidence.isnot(None)
        ).label("avg_confidence"),
        func.count(Document.id).filter(
            Document.embedding.isnot(None)
        ).label("with_embeddings"),
    ).where(base_filter)

    # Status-Gruppierung
    status_query = select(
        Document.status,
        func.count(Document.id).label("count")
    ).where(base_filter).group_by(Document.status)

    # Dokumenttyp-Gruppierung
    type_query = select(
        Document.document_type,
        func.count(Document.id).label("count")
    ).where(base_filter).group_by(Document.document_type)

    # PERFORMANCE: Alle 3 Queries parallel ausfuehren
    combined_result, status_result, type_result = await asyncio.gather(
        db.execute(combined_query),
        db.execute(status_query),
        db.execute(type_query),
    )

    # Ergebnisse verarbeiten
    combined_row = combined_result.fetchone()
    total = combined_row.total or 0
    avg_confidence = combined_row.avg_confidence or 0
    with_embeddings = combined_row.with_embeddings or 0

    by_status = {row.status: row.count for row in status_result.fetchall()}
    by_type = {row.document_type: row.count for row in type_result.fetchall()}

    return {
        "total_documents": total,
        "by_status": by_status,
        "by_document_type": by_type,
        "average_ocr_confidence": round(avg_confidence, 2) if avg_confidence else None,
        "documents_with_embeddings": with_embeddings,
        "embedding_coverage_percent": round(with_embeddings / total * 100, 1) if total > 0 else 0
    }


@router.get("/stats/summary")
async def get_document_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokumentstatistiken fuer den aktuellen Benutzer abrufen.

    Gibt aggregierte Statistiken ueber alle Dokumente zurueck:
    - Gesamtzahl Dokumente
    - Nach Status aufgeteilt
    - Nach Dokumenttyp aufgeteilt
    - Durchschnittliche OCR-Konfidenz
    - Anzahl mit Embeddings

    OPTIMIERT:
    - Verwendet kombinierte Queries (~80% schneller)
    - Redis Cache mit 2 Minuten TTL
    """
    from app.core.cache import CacheConfig

    user_id = str(current_user.id)
    cache_key = f"cache:stats:summary:user:{user_id}"

    # CACHING: Versuche aus Redis Cache zu laden
    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        cached = await redis_manager._redis.get(cache_key)
        if cached:
            import json
            logger.debug("document_stats_cache_hit", user_id=user_id)
            return json.loads(cached)

    except Exception as e:
        # Redis nicht verfuegbar - kein Caching
        logger.debug("document_stats_cache_unavailable", **safe_error_log(e))

    # Cache Miss - Daten aus DB holen
    result = await _fetch_document_stats_uncached(db, user_id)

    # Ergebnis cachen (2 Minuten TTL)
    try:
        import json
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        await redis_manager._redis.setex(
            cache_key,
            CacheConfig.STATS_TTL,  # 120 Sekunden
            json.dumps(result, default=str)
        )
        logger.debug("document_stats_cached", user_id=user_id, ttl=CacheConfig.STATS_TTL)

    except Exception as e:
        logger.debug("document_stats_cache_write_failed", **safe_error_log(e))

    return result


# ==================== Search Analytics ====================

@router.get("/stats/search-analytics")
async def get_search_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Such-Statistiken abrufen.

    Liefert aggregierte Statistiken ueber Suchanfragen:
    - Gesamtzahl der Suchen
    - Durchschnittliche Ergebnisse
    - Aufteilung nach Suchtyp
    - Top-Suchbegriffe
    - Filter-Nutzung
    """
    from app.services.search_analytics_service import get_search_analytics_service

    service = get_search_analytics_service()

    # Admin sieht alle Statistiken, normale Benutzer nur eigene
    user_filter = None if current_user.is_superuser else current_user.id

    return await service.get_search_statistics(
        db=db,
        days=days,
        user_id=user_filter
    )


@router.get("/stats/search-analytics/daily")
async def get_daily_search_analytics(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Taegliche Such-Statistiken abrufen.

    Liefert Statistiken pro Tag fuer Dashboard-Graphen:
    - Suchen pro Tag
    - Durchschnittliche Ausfuehrungszeit
    - Null-Ergebnis-Suchen
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren können tägliche Statistiken abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_daily_statistics(db=db, days=days)


@router.get("/stats/search-analytics/popular-terms")
async def get_popular_search_terms(
    days: int = Query(7, ge=1, le=90, description="Analysezeitraum in Tagen"),
    limit: int = Query(20, ge=1, le=100, description="Max. Anzahl Ergebnisse"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Beliebte Suchbegriffe abrufen.

    Nuetzlich fuer:
    - Verbesserung der Suchhilfe
    - Auto-Vervollstaendigung
    - Trend-Analyse
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren können beliebte Suchbegriffe abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_popular_search_terms(db=db, days=days, limit=limit)


@router.get("/stats/search-analytics/zero-results")
async def get_zero_result_queries(
    days: int = Query(7, ge=1, le=90, description="Analysezeitraum in Tagen"),
    limit: int = Query(20, ge=1, le=100, description="Max. Anzahl Ergebnisse"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Suchanfragen ohne Ergebnisse abrufen.

    Hilft bei der Identifikation von:
    - Fehlenden Dokumenten
    - Verbesserungsmoeglichkeiten bei der Suche
    - Haeufigen Tippfehlern
    """
    from app.services.search_analytics_service import get_search_analytics_service

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Nur Administratoren können Null-Ergebnis-Suchen abrufen"
        )

    service = get_search_analytics_service()
    return await service.get_zero_result_queries(db=db, days=days, limit=limit)


@router.post("/stats/search-analytics/click")
async def log_search_click(
    analytics_id: UUID = Query(..., description="ID des Such-Analytics-Eintrags"),
    position: int = Query(..., ge=1, description="Position des geklickten Ergebnisses"),
    is_download: bool = Query(False, description="Wurde das Dokument heruntergeladen?"),
    current_user: User = Depends(check_rate_limit),  # Rate limiting hinzugefuegt
    db: AsyncSession = Depends(get_db)
):
    """Klick auf Suchergebnis protokollieren.

    Wird vom Frontend aufgerufen wenn ein Benutzer auf
    ein Suchergebnis klickt oder es herunterlädt.
    """
    from app.services.search_analytics_service import get_search_analytics_service

    service = get_search_analytics_service()
    await service.log_click(
        db=db,
        analytics_id=analytics_id,
        result_position=position,
        is_download=is_download
    )

    return {"status": "ok"}


# ==================== Document Access Log (Audit Trail) ====================

@router.get("/{document_id}/access-log")
async def get_document_access_log(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Eintraege"),
    offset: int = Query(0, ge=0, description="Offset fuer Paginierung"),
    action_filter: Optional[str] = Query(None, description="Nach Aktionstyp filtern"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Zugriffs-Log fuer ein Dokument abrufen (Audit Trail).

    Zeigt alle Zugriffe und Aktionen auf dieses Dokument:
    - Views (Dokument angesehen)
    - Downloads
    - OCR-Verarbeitungen
    - Metadaten-Aenderungen
    - Sharing-Aktivitaeten

    **Beispiel-Aktionen:**
    - document_viewed
    - document_downloaded
    - document_updated
    - document_shared
    - ocr_started
    - ocr_completed

    **Hinweis:** Nur der Dokumenteigentuemer oder Admins
    koennen das Access-Log einsehen.
    """
    from sqlalchemy import select, and_, or_
    from app.db.models import Document, AuditLog

    # Dokument laden und Berechtigung pruefen
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden"
        )

    # Nur Eigentuemer oder Admin darf Access-Log sehen
    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung zum Abrufen des Zugriffs-Logs"
        )

    try:
        # Audit-Log-Eintraege fuer dieses Dokument abrufen
        audit_query = select(AuditLog).where(
            and_(
                AuditLog.resource_type == "document",
                AuditLog.resource_id == str(document_id)
            )
        )

        # Optional nach Aktion filtern
        if action_filter:
            audit_query = audit_query.where(
                AuditLog.action.ilike(f"%{action_filter}%")
            )

        # Sortierung und Paginierung
        audit_query = audit_query.order_by(AuditLog.created_at.desc())
        audit_query = audit_query.offset(offset).limit(limit)

        result = await db.execute(audit_query)
        audit_entries = result.scalars().all()

        # Gesamtzahl fuer Paginierung
        count_query = select(func.count(AuditLog.id)).where(
            and_(
                AuditLog.resource_type == "document",
                AuditLog.resource_id == str(document_id)
            )
        )
        if action_filter:
            count_query = count_query.where(
                AuditLog.action.ilike(f"%{action_filter}%")
            )

        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Eintraege formatieren
        access_log = []
        for entry in audit_entries:
            log_entry = {
                "id": str(entry.id),
                "action": entry.action,
                "timestamp": entry.created_at.isoformat() if entry.created_at else None,
                "user_id": str(entry.user_id) if entry.user_id else None,
                "ip_address": entry.ip_address,
                "success": entry.success if hasattr(entry, 'success') else True,
                "details": entry.activity_metadata if hasattr(entry, 'activity_metadata') else None,
            }
            access_log.append(log_entry)

        logger.debug(
            "document_access_log_retrieved",
            document_id=str(document_id),
            user_id=str(current_user.id),
            entries=len(access_log)
        )

        return {
            "document_id": str(document_id),
            "access_log": access_log,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(access_log) < total_count
        }

    except Exception as e:
        logger.error(
            "document_access_log_error",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Abrufen des Zugriffs-Logs"
        )


@router.post("/bulk/download-zip")
async def bulk_download_zip(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente als ZIP-Archiv herunterladen.

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "filename": "optional_name.zip"
    }
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import BulkDownloadZipRequest

    body = await request.json()

    try:
        req = BulkDownloadZipRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        zip_bytes, filename = await ablage_service.bulk_download_zip(
            db=db,
            user_id=current_user.id,
            document_ids=req.document_ids,
            filename=req.filename,
        )

        logger.info(
            "bulk_zip_download",
            user_id=str(current_user.id),
            document_count=len(req.document_ids),
            filename=filename
        )

        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "Content-Length": str(len(zip_bytes)),
            }
        )

    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="ZIP-Download fehlgeschlagen. Bitte Eingaben pruefen.")
    except Exception as e:
        logger.error(
            "bulk_zip_download_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Erstellen des ZIP-Archivs"
        )


@router.post("/bulk/export-csv")
async def bulk_export_csv(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Dokument-Metadaten als CSV exportieren.

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "columns": ["dateiname", "gesamtbetrag", ...],
        "include_amounts": true,
        "include_dates": true,
        "delimiter": ";"
    }
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import BulkExportCsvRequest

    body = await request.json()

    try:
        req = BulkExportCsvRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        csv_bytes, filename = await ablage_service.bulk_export_csv(
            db=db,
            user_id=current_user.id,
            document_ids=req.document_ids,
            columns=req.columns,
            include_amounts=req.include_amounts,
            include_dates=req.include_dates,
            delimiter=req.delimiter,
        )

        logger.info(
            "bulk_csv_export",
            user_id=str(current_user.id),
            document_count=len(req.document_ids),
            filename=filename
        )

        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv; charset=utf-8",
            headers={
                # SECURITY: Use sanitized Content-Disposition (Phase 10.1)
                "Content-Disposition": build_content_disposition(filename, "attachment"),
                "Content-Length": str(len(csv_bytes)),
            }
        )

    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="CSV-Export fehlgeschlagen. Bitte Eingaben pruefen.")
    except Exception as e:
        logger.error(
            "bulk_csv_export_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim CSV-Export"
        )


@router.patch("/{document_id}/payment-status", response_model=None)
async def update_payment_status(
    document_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Zahlungsstatus eines Dokuments aktualisieren.

    **Request Body:**
    ```json
    {
        "status": "bezahlt",
        "paid_amount": 1234.56,
        "payment_date": "2024-01-15T10:30:00Z"
    }
    ```

    **Status-Werte:**
    - `offen`: Noch nicht bezahlt
    - `bezahlt`: Vollstaendig bezahlt
    - `ueberfaellig`: Faelligkeitsdatum ueberschritten
    - `teilbezahlt`: Teilweise bezahlt (paid_amount erforderlich)
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import UpdatePaymentStatusRequest, DocumentPaymentStatus

    body = await request.json()

    try:
        req = UpdatePaymentStatusRequest(**body)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.update_payment_status(
            db=db,
            user_id=current_user.id,
            document_id=document_id,
            status=req.status,
            paid_amount=req.paid_amount,
            payment_date=req.payment_date,
        )

        logger.info(
            "payment_status_updated",
            user_id=str(current_user.id),
            document_id=str(document_id),
            new_status=req.status.value
        )

        return result

    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden.")
    except Exception as e:
        logger.error(
            "payment_status_update_error",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Aktualisieren des Zahlungsstatus"
        )


@router.post("/bulk/mark-as-paid", response_model=None)
async def bulk_mark_as_paid(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente als bezahlt markieren.

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "payment_date": "2024-01-15T10:30:00Z"
    }
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import BulkMarkAsPaidRequest

    body = await request.json()

    try:
        req = BulkMarkAsPaidRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.bulk_mark_as_paid(
            db=db,
            user_id=current_user.id,
            document_ids=req.document_ids,
            payment_date=req.payment_date,
        )

        logger.info(
            "bulk_mark_as_paid",
            user_id=str(current_user.id),
            success_count=result.success_count,
            failed_count=result.failed_count
        )

        return result

    except Exception as e:
        logger.error(
            "bulk_mark_as_paid_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Markieren als bezahlt"
        )


@router.post("/bulk/move-category", response_model=None)
async def bulk_move_category(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Dokumente in andere Kategorie verschieben.

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "target_category": "vertraege"
    }
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import BulkMoveCategoryRequest

    body = await request.json()

    try:
        req = BulkMoveCategoryRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.bulk_move_category(
            db=db,
            user_id=current_user.id,
            document_ids=req.document_ids,
            target_category=req.target_category,
        )

        logger.info(
            "bulk_move_category",
            user_id=str(current_user.id),
            target_category=req.target_category,
            success_count=result.success_count
        )

        return result

    except ValueError as e:
        # SECURITY FIX 28-27: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="Kategoriewechsel fehlgeschlagen. Bitte Eingaben pruefen.")
    except Exception as e:
        logger.error(
            "bulk_move_category_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Verschieben der Dokumente"
        )


@router.post("/bulk/set-tags", response_model=None)
async def bulk_set_tags(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Tags fuer mehrere Dokumente setzen/entfernen.

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "tags": ["wichtig", "archiv"],
        "mode": "add"
    }
    ```

    **Mode-Werte:**
    - `add`: Tags hinzufuegen
    - `remove`: Tags entfernen
    - `set`: Alle Tags ersetzen
    """
    from app.services.document_services.ablage_service import get_ablage_service
    from app.db.schemas import BulkSetTagsRequest

    body = await request.json()

    try:
        req = BulkSetTagsRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.bulk_set_tags(
            db=db,
            user_id=current_user.id,
            document_ids=req.document_ids,
            tags=req.tags,
            mode=req.mode,
        )

        logger.info(
            "bulk_set_tags",
            user_id=str(current_user.id),
            mode=req.mode.value,
            tags=req.tags,
            success_count=result.success_count
        )

        return result

    except Exception as e:
        logger.error(
            "bulk_set_tags_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Setzen der Tags"
        )


@router.delete("/bulk/delete", response_model=None)
async def bulk_delete_documents(
    request: Request,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db)
):
    """Mehrere Dokumente soft-loeschen (GDPR-konform).

    **Request Body:**
    ```json
    {
        "document_ids": ["uuid1", "uuid2", ...],
        "reason": "Nicht mehr benoetigt"
    }
    ```
    """
    from app.services.document_services.ablage_service import get_ablage_service

    body = await request.json()
    document_ids = body.get("document_ids", [])
    reason = body.get("reason")

    if not document_ids:
        raise HTTPException(
            status_code=400,
            detail="document_ids erforderlich"
        )

    # UUIDs validieren
    try:
        parsed_ids = [UUID(str(doc_id)) for doc_id in document_ids]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Ungueltige document_id(s)"
        )

    ablage_service = get_ablage_service()

    try:
        result = await ablage_service.bulk_delete(
            db=db,
            user_id=current_user.id,
            document_ids=parsed_ids,
            reason=reason,
        )

        logger.info(
            "bulk_delete",
            user_id=str(current_user.id),
            success_count=result.success_count,
            failed_count=result.failed_count
        )

        return result

    except Exception as e:
        logger.error(
            "bulk_delete_error",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Loeschen der Dokumente"
        )


# =============================================================================
# UNIFIED BULK OPERATIONS ENDPOINT
# =============================================================================

class BulkOperationAction(str, Enum):
    """Supported bulk operation actions."""
    TAG = "tag"
    MOVE = "move"
    DELETE = "delete"
    EXPORT = "export"
    CATEGORIZE = "categorize"


class UnifiedBulkOperationRequest(BaseModel):
    """Unified request for all bulk operations on documents.

    Allows performing multiple types of bulk actions through a single endpoint.
    """
    document_ids: List[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der Dokument-IDs (max. 100)"
    )
    action: BulkOperationAction = Field(
        ...,
        description="Auszufuehrende Aktion: tag, move, delete, export, categorize"
    )
    params: Optional[Dict[str, Any]] = Field(
        None,
        description="Aktions-spezifische Parameter"
    )

    model_config = ConfigDict(use_enum_values=True)


class UnifiedBulkOperationResponse(BaseModel):
    """Response for unified bulk operations."""
    success: bool
    action: str
    total_requested: int
    processed: int
    failed: int
    errors: List[Dict[str, str]] = Field(default_factory=list)
    message: str
    task_id: Optional[str] = Field(
        None,
        description="Task-ID fuer asynchrone Operationen (z.B. Export)"
    )
    download_url: Optional[str] = Field(
        None,
        description="Download-URL fuer Export-Operationen"
    )


@router.post(
    "/bulk",
    response_model=UnifiedBulkOperationResponse,
    summary="Einheitliche Bulk-Operationen",
    description="""
    Fuehrt Massenaktionen auf mehreren Dokumenten aus.

    **Unterstuetzte Aktionen:**

    1. **tag** - Tags hinzufuegen/entfernen
       - `params.tags`: Liste der Tags (string[])
       - `params.operation`: "add" | "remove" | "set" (Standard: "add")

    2. **move** - In Ordner verschieben
       - `params.folder_id`: Zielordner-UUID (erforderlich)

    3. **delete** - Soft-Delete (GDPR-konform)
       - `params.reason`: Loeschgrund (optional)

    4. **export** - Dokumente exportieren
       - `params.format`: "zip" | "pdf" | "csv" (Standard: "zip")
       - `params.include_metadata`: Boolean (Standard: true)

    5. **categorize** - Kategorie setzen
       - `params.category`: Zielkategorie (erforderlich)

    **Limits:** Maximal 100 Dokumente pro Request

    **Beispiel (Tags):**
    ```json
    {
      "document_ids": ["uuid1", "uuid2"],
      "action": "tag",
      "params": {"tags": ["wichtig", "archiv"], "operation": "add"}
    }
    ```
    """,
    responses={
        200: {"description": "Operation erfolgreich ausgefuehrt"},
        400: {"description": "Ungueltige Anfrage"},
        404: {"description": "Dokument(e) nicht gefunden"},
        429: {"description": "Rate Limit ueberschritten"},
    }
)
async def unified_bulk_operation(
    request: UnifiedBulkOperationRequest,
    current_user: User = Depends(check_batch_rate_limit),
    db: AsyncSession = Depends(get_db),
    company: Company = Depends(require_company),
) -> UnifiedBulkOperationResponse:
    """Einheitlicher Endpoint fuer alle Bulk-Operationen."""
    from app.services.document_services.ablage_service import get_ablage_service
    from app.services.document_services.batch_service import get_batch_service

    ablage_service = get_ablage_service()
    batch_service = get_batch_service()
    params = request.params or {}

    try:
        if request.action == BulkOperationAction.TAG:
            # Tag operation
            tags = params.get("tags", [])
            if not tags or not isinstance(tags, list):
                raise HTTPException(
                    status_code=400,
                    detail="params.tags erforderlich (Liste von Strings)"
                )

            # Validate tags
            for tag in tags:
                if not isinstance(tag, str) or len(tag) > 50:
                    raise HTTPException(
                        status_code=400,
                        detail="Tags muessen Strings mit max. 50 Zeichen sein"
                    )

            operation_str = params.get("operation", "add")
            try:
                tag_operation = TagOperation(operation_str)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungueltige Tag-Operation: {operation_str}. Erlaubt: add, remove, set"
                )

            result = await batch_service.batch_tag(
                db=db,
                document_ids=request.document_ids,
                tags=tags,
                user_id=current_user.id,
                operation=tag_operation,
            )

            logger.info(
                "unified_bulk_tag",
                user_id=str(current_user.id),
                operation=tag_operation.value,
                tags=tags,
                processed=result.processed
            )

            return UnifiedBulkOperationResponse(
                success=result.success,
                action="tag",
                total_requested=result.total_requested,
                processed=result.processed,
                failed=result.failed,
                errors=[{"id": str(e.document_id), "error": e.error} for e in result.errors],
                message=result.message,
            )

        elif request.action == BulkOperationAction.MOVE:
            # Move to folder
            folder_id_str = params.get("folder_id")
            if not folder_id_str:
                raise HTTPException(
                    status_code=400,
                    detail="params.folder_id erforderlich"
                )

            try:
                folder_id = UUID(str(folder_id_str))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="params.folder_id muss eine gueltige UUID sein"
                )

            # Verify folder exists and user has access
            from sqlalchemy import select, update, and_
            from app.db.models import Document, Folder

            folder_query = select(Folder).where(
                and_(
                    Folder.id == folder_id,
                    Folder.owner_id == current_user.id
                )
            )
            folder_result = await db.execute(folder_query)
            target_folder = folder_result.scalar_one_or_none()

            if not target_folder:
                raise HTTPException(
                    status_code=404,
                    detail="Zielordner nicht gefunden oder keine Berechtigung"
                )

            # Execute bulk move
            update_stmt = update(Document).where(
                and_(
                    Document.id.in_(request.document_ids),
                    Document.owner_id == current_user.id,
                    Document.company_id == company.id,
                )
            ).values(folder_id=folder_id)

            result = await db.execute(update_stmt)
            await db.commit()

            processed = result.rowcount
            failed = len(request.document_ids) - processed

            logger.info(
                "unified_bulk_move",
                user_id=str(current_user.id),
                folder_id=str(folder_id),
                processed=processed
            )

            return UnifiedBulkOperationResponse(
                success=failed == 0,
                action="move",
                total_requested=len(request.document_ids),
                processed=processed,
                failed=failed,
                errors=[],
                message=f"{processed} Dokument(e) verschoben" if failed == 0
                       else f"{processed} von {len(request.document_ids)} Dokument(en) verschoben",
            )

        elif request.action == BulkOperationAction.DELETE:
            # Soft delete
            reason = params.get("reason")

            result = await ablage_service.bulk_delete(
                db=db,
                user_id=current_user.id,
                document_ids=request.document_ids,
                reason=reason,
            )

            logger.info(
                "unified_bulk_delete",
                user_id=str(current_user.id),
                success_count=result.success_count
            )

            return UnifiedBulkOperationResponse(
                success=result.failed_count == 0,
                action="delete",
                total_requested=result.success_count + result.failed_count,
                processed=result.success_count,
                failed=result.failed_count,
                errors=[{"id": e.document_id if hasattr(e, 'document_id') else 'unknown', "error": str(e.error) if hasattr(e, 'error') else str(e)} for e in result.errors],
                message=result.message,
            )

        elif request.action == BulkOperationAction.EXPORT:
            # Export documents
            from app.workers.tasks import document_bulk_export_task

            export_format = params.get("format", "zip")
            if export_format not in ["zip", "pdf", "csv"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungueltiges Export-Format: {export_format}. Erlaubt: zip, pdf, csv"
                )

            include_metadata = params.get("include_metadata", True)

            # Start Celery task
            task = document_bulk_export_task.delay(
                document_ids=[str(doc_id) for doc_id in request.document_ids],
                user_id=str(current_user.id),
                export_format=export_format,
                include_metadata=include_metadata,
            )

            logger.info(
                "unified_bulk_export_started",
                user_id=str(current_user.id),
                task_id=task.id,
                format=export_format,
                document_count=len(request.document_ids)
            )

            return UnifiedBulkOperationResponse(
                success=True,
                action="export",
                total_requested=len(request.document_ids),
                processed=len(request.document_ids),
                failed=0,
                errors=[],
                message=f"Export von {len(request.document_ids)} Dokumenten gestartet",
                task_id=task.id,
            )

        elif request.action == BulkOperationAction.CATEGORIZE:
            # Set category
            category = params.get("category")
            if not category:
                raise HTTPException(
                    status_code=400,
                    detail="params.category erforderlich"
                )

            # Validate category
            valid_categories = list(CATEGORY_TO_DOCTYPE.keys())
            if category not in valid_categories:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungueltige Kategorie: {category}. Erlaubt: {', '.join(valid_categories)}"
                )

            result = await ablage_service.bulk_move_category(
                db=db,
                user_id=current_user.id,
                document_ids=request.document_ids,
                target_category=category,
            )

            logger.info(
                "unified_bulk_categorize",
                user_id=str(current_user.id),
                category=category,
                success_count=result.success_count
            )

            return UnifiedBulkOperationResponse(
                success=result.failed_count == 0,
                action="categorize",
                total_requested=result.success_count + result.failed_count,
                processed=result.success_count,
                failed=result.failed_count,
                errors=[{"id": e.document_id if hasattr(e, 'document_id') else 'unknown', "error": str(e.error) if hasattr(e, 'error') else str(e)} for e in result.errors],
                message=result.message,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unbekannte Aktion: {request.action}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "unified_bulk_operation_error",
            user_id=str(current_user.id),
            action=request.action,
            **safe_error_log(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler bei der Bulk-Operation"
        )
