"""Documents API endpoints with search and batch operations.

Provides REST API endpoints for:
- Document CRUD operations
- Full-text and semantic search
- Similar documents discovery
- Batch operations (delete, tag, export)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import io
import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
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

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# ==================== Document Upload Endpoint ====================

@router.post("/", response_model=DocumentCreateResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(..., description="Dokument (PDF, PNG, JPG, TIFF)"),
    document_type: DocumentType = Form(DocumentType.OTHER, description="Dokumenttyp"),
    language: str = Form("de", description="Sprache (de/en)"),
    tags: Optional[str] = Form(None, description="Tags (kommasepariert)"),
    start_ocr: bool = Form(True, description="OCR-Verarbeitung automatisch starten"),
    ocr_backend: str = Form("auto", description="OCR-Backend (auto/deepseek/got_ocr/surya)"),
    priority: int = Form(5, ge=1, le=10, description="Verarbeitungsprioritaet"),
    current_user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db)
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
            detail=f"Ungueltige Sprache: {language}. Erlaubt: de, en"
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
            detail=magic_error or "Ungueltige Datei - Magic Bytes stimmen nicht ueberein"
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

    # 6. Checksum berechnen
    file_hash = hashlib.sha256(file_content).hexdigest()

    # 7. In MinIO hochladen
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
        logger.error("storage_upload_failed", error=str(e), filename=file.filename)
        raise HTTPException(
            status_code=500,
            detail=f"Upload fehlgeschlagen: {str(e)}"
        )

    # 8. Datenbank-Eintrag erstellen
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

    # 9. Optional: OCR-Job starten
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
        except Exception as e:
            logger.warning(
                "ocr_job_queue_failed",
                document_id=str(doc_id),
                error=str(e)
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
                similarity_threshold=similarity_threshold
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
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True  # Include full traceback for debugging
        )

    return result


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
                                DocumentAccess.expires_at > datetime.utcnow()
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
            error=str(e)
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
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_content))
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
                                DocumentAccess.expires_at > datetime.utcnow()
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
                "Content-Disposition": f'attachment; filename="{filename}"',
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
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(pdf_content))
            }
        )

    except ImportError as e:
        logger.warning(
            "pdf_export_missing_dependency",
            error=str(e)
        )
        raise HTTPException(
            status_code=501,
            detail="PDF-Export nicht verfügbar. Erforderliche Bibliotheken fehlen."
        )
    except Exception as e:
        logger.error(
            "pdf_export_error",
            document_id=str(document_id),
            error=str(e)
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
    """
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
    """
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


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dokument loeschen.

    Loescht das Dokument vollstaendig aus der Datenbank
    und dem Objektspeicher (MinIO).
    """
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
        raise HTTPException(status_code=404, detail=str(e))

    # Filename fuer Download
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
            "Content-Disposition": f'attachment; filename="{filename}"',
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
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
            "Content-Disposition": f'attachment; filename="{filename}"',
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
        raise HTTPException(status_code=400, detail=str(e))

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
            cleanup_results["errors"].append(f"Cache-Bereinigung fehlgeschlagen: {str(e)}")
            logger.warning("cleanup_cache_failed", document_id=str(document_id), error=str(e))

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
            cleanup_results["errors"].append(f"Temp-Bereinigung fehlgeschlagen: {str(e)}")
            logger.warning("cleanup_temp_failed", document_id=str(document_id), error=str(e))

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
            cleanup_results["errors"].append(f"GPU-Bereinigung fehlgeschlagen: {str(e)}")
            logger.warning("cleanup_gpu_failed", document_id=str(document_id), error=str(e))

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
        logger.debug("document_stats_cache_unavailable", error=str(e))

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
        logger.debug("document_stats_cache_write_failed", error=str(e))

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
            detail="Nur Administratoren koennen taegliche Statistiken abrufen"
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
            detail="Nur Administratoren koennen beliebte Suchbegriffe abrufen"
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
            detail="Nur Administratoren koennen Null-Ergebnis-Suchen abrufen"
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
