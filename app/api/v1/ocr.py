# -*- coding: utf-8 -*-
"""
API-Endpunkte fuer OCR-Operationen.

Bietet schnelle OCR-Vorschau fuer Dokument-Klassifikation
und Text-Extraktion ohne vollstaendige Verarbeitung.

Feinpoliert und durchdacht - Enterprise OCR API.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.services.ocr import quick_ocr_preview
from app.core.file_validation import sanitize_filename, PathTraversalError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ocr", tags=["ocr"])


# =============================================================================
# Response Models
# =============================================================================


class OCRPreviewResponse(BaseModel):
    """Antwort fuer OCR-Vorschau."""

    erfolg: bool = Field(..., description="War Extraktion erfolgreich?")
    text: str = Field(..., description="Extrahierter Text")
    zeichen_anzahl: int = Field(..., description="Anzahl extrahierter Zeichen")
    abgeschnitten: bool = Field(False, description="Wurde Text gekuerzt?")
    dateiname: Optional[str] = Field(None, description="Original-Dateiname")
    methode: str = Field("unbekannt", description="Verwendete Extraktionsmethode")
    fehler: Optional[str] = Field(None, description="Fehlermeldung bei Misserfolg")


class OCRPreviewRequest(BaseModel):
    """Anfrage fuer OCR-Vorschau mit Dokument-ID."""

    dokument_id: UUID = Field(..., description="ID des Dokuments")
    max_pages: int = Field(1, ge=1, le=5, description="Max. Seiten zu extrahieren")
    max_chars: int = Field(1000, ge=100, le=10000, description="Max. Zeichen")


class OCRStatusResponse(BaseModel):
    """Status des OCR-Systems."""

    verfuegbar: bool = Field(..., description="Ist OCR-System verfuegbar?")
    backends: Dict[str, Any] = Field(..., description="Status der OCR-Backends")
    gpu_verfuegbar: bool = Field(..., description="Ist GPU verfuegbar?")
    pymupdf_verfuegbar: bool = Field(..., description="Ist PyMuPDF verfuegbar?")
    tesseract_verfuegbar: bool = Field(..., description="Ist Tesseract verfuegbar?")


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/preview/upload",
    response_model=OCRPreviewResponse,
    summary="OCR-Vorschau aus Upload",
    description="Extrahiert schnelle Text-Vorschau aus hochgeladener Datei.",
)
async def ocr_preview_upload(
    file: UploadFile = File(..., description="Dokument (PDF, PNG, JPG, TIFF)"),
    max_pages: int = Query(1, ge=1, le=5, description="Max. Seiten"),
    max_chars: int = Query(1000, ge=100, le=10000, description="Max. Zeichen"),
    current_user: User = Depends(get_current_active_user),
) -> OCRPreviewResponse:
    """Schnelle OCR-Vorschau aus hochgeladener Datei.

    Ideal fuer:
    - Dokument-Klassifikation vor vollstaendiger Verarbeitung
    - Schnelle Inhalts-Ueberpruefung
    - Sprach-Erkennung

    Unterstuetzte Formate: PDF, PNG, JPG, JPEG, TIFF, BMP
    """
    logger.info(
        "ocr_preview_upload_angefordert",
        user_id=str(current_user.id),
        filename=file.filename,
        content_type=file.content_type,
        max_pages=max_pages,
        max_chars=max_chars,
    )

    # Dateiformat validieren
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dateiname fehlt",
        )

    # Path Traversal Schutz: Dateiname sanitieren
    try:
        safe_filename = sanitize_filename(file.filename, strict=False)
    except PathTraversalError:
        logger.warning(
            "path_traversal_attempt",
            user_id=str(current_user.id),
            original_filename=file.filename[:100] if file.filename else None,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiger Dateiname: Pfad-Manipulation erkannt",
        )

    suffix = Path(safe_filename).suffix.lower()
    allowed_formats = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

    if suffix not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format {suffix} nicht unterstuetzt. Erlaubt: {', '.join(allowed_formats)}",
        )

    # Temporaere Datei erstellen
    import tempfile
    import aiofiles

    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, prefix="ocr_preview_"
        ) as tmp:
            tmp_path = Path(tmp.name)

        # Datei async schreiben
        content = await file.read()
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(content)

        # OCR-Vorschau durchfuehren
        text = await quick_ocr_preview(
            file_path=tmp_path,
            max_pages=max_pages,
            max_chars=max_chars,
        )

        # Methode bestimmen
        if suffix == ".pdf":
            methode = "pdf_embedded_text"
        else:
            methode = "tesseract_ocr"

        abgeschnitten = len(text) >= max_chars

        logger.info(
            "ocr_preview_upload_erfolgreich",
            user_id=str(current_user.id),
            filename=file.filename,
            zeichen_anzahl=len(text),
            abgeschnitten=abgeschnitten,
        )

        return OCRPreviewResponse(
            erfolg=True,
            text=text,
            zeichen_anzahl=len(text),
            abgeschnitten=abgeschnitten,
            dateiname=file.filename,
            methode=methode,
            fehler=None,
        )

    except Exception as e:
        logger.exception(
            "ocr_preview_upload_fehler",
            user_id=str(current_user.id),
            filename=file.filename,
            error=str(e),
        )
        # SECURITY FIX 30: Generic error message - no exception details to client
        return OCRPreviewResponse(
            erfolg=False,
            text="",
            zeichen_anzahl=0,
            abgeschnitten=False,
            dateiname=file.filename,
            methode="fehler",
            fehler="OCR-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.",
        )

    finally:
        # Temporaere Datei loeschen
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError as e:
                logger.debug("temp_file_cleanup_failed", path=str(tmp_path), error=str(e))


@router.post(
    "/preview/document",
    response_model=OCRPreviewResponse,
    summary="OCR-Vorschau aus Dokument",
    description="Extrahiert schnelle Text-Vorschau aus gespeichertem Dokument.",
)
async def ocr_preview_document(
    request: OCRPreviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OCRPreviewResponse:
    """OCR-Vorschau fuer bereits hochgeladenes Dokument.

    Verwendet das in MinIO gespeicherte Original-Dokument.
    """
    from app.services.document_service import get_document_service

    logger.info(
        "ocr_preview_document_angefordert",
        user_id=str(current_user.id),
        dokument_id=str(request.dokument_id),
        max_pages=request.max_pages,
        max_chars=request.max_chars,
    )

    # Dokument laden
    service = get_document_service()

    try:
        document = await service.get_document(
            db=db,
            document_id=request.dokument_id,
            user_id=current_user.id,
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument nicht gefunden",
            )

        # Datei aus MinIO laden
        from app.services.storage_service import get_storage_service

        storage = get_storage_service()
        file_path = await storage.download_temp(document.storage_path)

        if not file_path or not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dokument-Datei nicht gefunden",
            )

        # OCR-Vorschau durchfuehren
        text = await quick_ocr_preview(
            file_path=file_path,
            max_pages=request.max_pages,
            max_chars=request.max_chars,
        )

        # Methode bestimmen
        suffix = Path(document.original_filename or "").suffix.lower()
        if suffix == ".pdf":
            methode = "pdf_embedded_text"
        else:
            methode = "tesseract_ocr"

        abgeschnitten = len(text) >= request.max_chars

        logger.info(
            "ocr_preview_document_erfolgreich",
            user_id=str(current_user.id),
            dokument_id=str(request.dokument_id),
            zeichen_anzahl=len(text),
            abgeschnitten=abgeschnitten,
        )

        return OCRPreviewResponse(
            erfolg=True,
            text=text,
            zeichen_anzahl=len(text),
            abgeschnitten=abgeschnitten,
            dateiname=document.original_filename,
            methode=methode,
            fehler=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "ocr_preview_document_fehler",
            user_id=str(current_user.id),
            dokument_id=str(request.dokument_id),
            error=str(e),
        )
        # SECURITY FIX 30: Generic error message - no exception details to client
        return OCRPreviewResponse(
            erfolg=False,
            text="",
            zeichen_anzahl=0,
            abgeschnitten=False,
            dateiname=None,
            methode="fehler",
            fehler="OCR-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.",
        )

    finally:
        # Temporaere Datei loeschen
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except OSError as e:
                logger.debug("temp_file_cleanup_failed", path=str(file_path), error=str(e))


@router.get(
    "/status",
    response_model=OCRStatusResponse,
    summary="OCR-System Status",
    description="Zeigt Status und Verfuegbarkeit des OCR-Systems.",
)
async def ocr_status(
    current_user: User = Depends(get_current_active_user),
) -> OCRStatusResponse:
    """Pruefe OCR-System Verfuegbarkeit."""
    logger.info(
        "ocr_status_angefordert",
        user_id=str(current_user.id),
    )

    # PyMuPDF pruefen
    try:
        import fitz  # noqa: F401

        pymupdf_verfuegbar = True
    except ImportError:
        pymupdf_verfuegbar = False

    # Tesseract pruefen
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        tesseract_verfuegbar = True
    except (ImportError, OSError) as e:
        logger.debug("tesseract_not_available", error=str(e))
        tesseract_verfuegbar = False

    # GPU pruefen
    try:
        import torch

        gpu_verfuegbar = torch.cuda.is_available()
    except ImportError:
        gpu_verfuegbar = False

    # Backend-Status sammeln
    backends: Dict[str, Any] = {
        "pymupdf": {
            "verfuegbar": pymupdf_verfuegbar,
            "beschreibung": "PDF-Text-Extraktion (schnell)",
        },
        "tesseract": {
            "verfuegbar": tesseract_verfuegbar,
            "beschreibung": "Bild-OCR (universell)",
        },
    }

    # DeepSeek Backend pruefen (optional)
    try:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent

        # DeepSeek erfordert GPU - Verfuegbarkeit basiert auf CUDA
        deepseek_verfuegbar = gpu_verfuegbar
        backends["deepseek"] = {
            "verfuegbar": deepseek_verfuegbar,
            "beschreibung": "GPU-OCR (beste Qualitaet)" if deepseek_verfuegbar else "GPU-OCR (GPU nicht verfuegbar)",
            "gpu_erforderlich": True,
        }
    except ImportError as e:
        logger.warning("deepseek_import_failed", error=str(e))
        backends["deepseek"] = {
            "verfuegbar": False,
            "beschreibung": "GPU-OCR (nicht installiert)",
            "gpu_erforderlich": True,
        }

    verfuegbar = pymupdf_verfuegbar or tesseract_verfuegbar

    return OCRStatusResponse(
        verfuegbar=verfuegbar,
        backends=backends,
        gpu_verfuegbar=gpu_verfuegbar,
        pymupdf_verfuegbar=pymupdf_verfuegbar,
        tesseract_verfuegbar=tesseract_verfuegbar,
    )


# =============================================================================
# OCR Control Endpoints (Document-specific)
# =============================================================================


class OCRStartRequest(BaseModel):
    """Anfrage zum Starten der OCR-Verarbeitung."""
    backend: str = Field(
        "auto",
        description="OCR-Backend: auto, deepseek, got_ocr, surya"
    )
    priority: int = Field(
        5,
        ge=1,
        le=10,
        description="Verarbeitungspriorität (1=niedrig, 10=hoch)"
    )
    force_reprocess: bool = Field(
        False,
        description="OCR auch bei bereits verarbeiteten Dokumenten neu starten"
    )


class OCRStartResponse(BaseModel):
    """Antwort nach OCR-Start."""
    job_id: str = Field(..., description="Job-ID für Status-Abfrage")
    document_id: UUID = Field(..., description="Dokument-ID")
    backend: str = Field(..., description="Ausgewähltes Backend")
    status: str = Field(..., description="aktueller Status")
    message: str = Field(..., description="Statusmeldung")


class OCRCancelResponse(BaseModel):
    """Antwort nach OCR-Abbruch."""
    document_id: UUID
    cancelled: bool
    message: str


class OCRBackendChangeRequest(BaseModel):
    """Anfrage zum Ändern des OCR-Backends."""
    backend: str = Field(
        ...,
        description="Neues OCR-Backend: deepseek, got_ocr, surya"
    )
    reprocess: bool = Field(
        False,
        description="Dokument sofort neu verarbeiten"
    )


@router.post(
    "/documents/{document_id}/start",
    response_model=OCRStartResponse,
    # HTTP 202 Accepted: Async-Verarbeitung gestartet, Ergebnis noch nicht verfügbar
    status_code=202,
    summary="OCR-Verarbeitung starten",
    description="Startet die OCR-Verarbeitung für ein Dokument."
)
async def start_ocr_processing(
    document_id: UUID,
    request: OCRStartRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> OCRStartResponse:
    """Startet die OCR-Verarbeitung für ein Dokument.

    **Parameter:**
    - backend: OCR-Backend (auto wählt automatisch basierend auf Dokumenttyp)
    - priority: Verarbeitungspriorität (höher = schneller)
    - force_reprocess: Bei True wird auch bereits verarbeitetes Dokument neu verarbeitet

    **Backends:**
    - auto: Automatische Auswahl (empfohlen)
    - deepseek: DeepSeek-Janus-Pro (beste Qualität für Deutsch)
    - got_ocr: GOT-OCR 2.0 (schnell, gut für Tabellen)
    - surya: Surya + Docling (CPU-Fallback, Layout-Analyse)

    **Beispiel:**
    ```
    POST /api/v1/ocr/documents/{id}/start
    {"backend": "deepseek", "priority": 8}
    ```
    """
    from sqlalchemy import select
    from app.db.models import Document, ProcessingJob

    # Dokument laden und Berechtigung prüfen
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für dieses Dokument"
        )

    if document.is_deleted:
        raise HTTPException(status_code=410, detail="Dokument wurde gelöscht")

    # Prüfe ob bereits in Verarbeitung
    job_query = select(ProcessingJob).where(
        ProcessingJob.document_id == document_id,
        ProcessingJob.status.in_(["queued", "processing"])
    )
    result = await db.execute(job_query)
    existing_job = result.scalar_one_or_none()

    if existing_job:
        raise HTTPException(
            status_code=409,
            detail=f"Dokument wird bereits verarbeitet (Job: {existing_job.id})"
        )

    # Prüfe ob bereits verarbeitet
    if document.status == "completed" and not request.force_reprocess:
        raise HTTPException(
            status_code=400,
            detail="Dokument bereits verarbeitet. Setze force_reprocess=true für Neuverarbeitung."
        )

    # Backend validieren
    valid_backends = ["auto", "deepseek", "got_ocr", "surya"]
    if request.backend not in valid_backends:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Backend. Erlaubt: {', '.join(valid_backends)}"
        )

    # OCR-Job erstellen
    try:
        from app.workers.celery_app import celery_app
        from uuid import uuid4
        import json

        job_id = str(uuid4())

        # ProcessingJob in DB anlegen
        processing_job = ProcessingJob(
            id=UUID(job_id),
            document_id=document_id,
            job_type="ocr",
            status="queued",
            priority=request.priority,
            config={"backend": request.backend, "force_reprocess": request.force_reprocess}
        )
        db.add(processing_job)

        # Dokument-Status aktualisieren
        document.status = "queued"
        document.ocr_backend_used = request.backend if request.backend != "auto" else None

        await db.commit()

        # Celery Task starten
        celery_app.send_task(
            "app.workers.tasks.ocr_tasks.process_document_ocr",
            args=[str(document_id), request.backend, request.priority],
            task_id=job_id,
            priority=10 - request.priority  # Celery: niedrigere Zahl = höhere Priorität
        )

        logger.info(
            "ocr_processing_started",
            document_id=str(document_id),
            job_id=job_id,
            backend=request.backend,
            user_id=str(current_user.id)
        )

        return OCRStartResponse(
            job_id=job_id,
            document_id=document_id,
            backend=request.backend,
            status="queued",
            message="OCR-Verarbeitung wurde gestartet"
        )

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error(
            "ocr_start_failed",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Starten der OCR-Verarbeitung. Bitte erneut versuchen."
        )


@router.post(
    "/documents/{document_id}/cancel",
    response_model=OCRCancelResponse,
    summary="OCR-Verarbeitung abbrechen",
    description="Bricht eine laufende OCR-Verarbeitung ab."
)
async def cancel_ocr_processing(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> OCRCancelResponse:
    """Bricht eine laufende OCR-Verarbeitung ab.

    Kann nur für eigene Dokumente verwendet werden.
    Bereits abgeschlossene Verarbeitungen können nicht abgebrochen werden.
    """
    from sqlalchemy import select
    from app.db.models import Document, ProcessingJob

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für dieses Dokument"
        )

    # Aktiven Job finden
    job_query = select(ProcessingJob).where(
        ProcessingJob.document_id == document_id,
        ProcessingJob.status.in_(["queued", "processing"])
    )
    result = await db.execute(job_query)
    job = result.scalar_one_or_none()

    if not job:
        return OCRCancelResponse(
            document_id=document_id,
            cancelled=False,
            message="Keine aktive OCR-Verarbeitung gefunden"
        )

    try:
        from app.workers.celery_app import celery_app

        # Celery Task abbrechen
        celery_app.control.revoke(str(job.id), terminate=True)

        # Job-Status aktualisieren
        job.status = "cancelled"
        document.status = "cancelled"

        await db.commit()

        logger.info(
            "ocr_processing_cancelled",
            document_id=str(document_id),
            job_id=str(job.id),
            user_id=str(current_user.id)
        )

        return OCRCancelResponse(
            document_id=document_id,
            cancelled=True,
            message="OCR-Verarbeitung wurde abgebrochen"
        )

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error(
            "ocr_cancel_failed",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail="Fehler beim Abbrechen. Bitte erneut versuchen."
        )


@router.put(
    "/documents/{document_id}/backend",
    summary="OCR-Backend ändern",
    description="Ändert das bevorzugte OCR-Backend für ein Dokument."
)
async def change_ocr_backend(
    document_id: UUID,
    request: OCRBackendChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Ändert das OCR-Backend für ein Dokument.

    Wenn reprocess=true, wird das Dokument sofort mit dem neuen Backend
    neu verarbeitet. Andernfalls wird das Backend nur für zukünftige
    Verarbeitungen gespeichert.

    **Anwendungsfall:**
    - Qualität war mit automatischer Auswahl nicht optimal
    - Spezifisches Backend für bestimmte Dokumenttypen erzwingen
    """
    from sqlalchemy import select
    from app.db.models import Document

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung für dieses Dokument"
        )

    # Backend validieren
    valid_backends = ["deepseek", "got_ocr", "surya"]
    if request.backend not in valid_backends:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Backend. Erlaubt: {', '.join(valid_backends)}"
        )

    # Backend speichern
    old_backend = document.ocr_backend_used
    document.ocr_backend_used = request.backend

    await db.commit()

    logger.info(
        "ocr_backend_changed",
        document_id=str(document_id),
        old_backend=old_backend,
        new_backend=request.backend,
        user_id=str(current_user.id)
    )

    result_message = f"OCR-Backend auf '{request.backend}' geändert"

    # Optional: Neu verarbeiten
    if request.reprocess:
        try:
            # Start OCR mit neuem Backend
            start_request = OCRStartRequest(
                backend=request.backend,
                force_reprocess=True
            )
            start_response = await start_ocr_processing(
                document_id=document_id,
                request=start_request,
                current_user=current_user,
                db=db
            )
            result_message += f". Neuverarbeitung gestartet (Job: {start_response.job_id})"
        except HTTPException as e:
            result_message += f". Neuverarbeitung fehlgeschlagen: {e.detail}"

    return {
        "document_id": str(document_id),
        "old_backend": old_backend,
        "new_backend": request.backend,
        "reprocess_started": request.reprocess,
        "message": result_message
    }


# =============================================================================
# OCR Cache Management
# =============================================================================


@router.get(
    "/documents/{document_id}/cache",
    summary="OCR-Cache Status",
    description="Zeigt den Cache-Status fuer ein Dokument."
)
async def get_ocr_cache_status(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Zeigt den OCR-Cache-Status fuer ein Dokument.

    Gibt Informationen ueber gecachte OCR-Ergebnisse zurueck:
    - Ob ein Cache-Eintrag existiert
    - Wann der Cache erstellt wurde
    - Welches Backend verwendet wurde
    - Cache-Groesse

    Nuetzlich fuer:
    - Debugging von OCR-Problemen
    - Verstaendnis warum bestimmte Ergebnisse zurueckgegeben werden
    - Cache-Management und Invalidierung
    """
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.ocr_cache_service import get_ocr_cache_service

    # Dokument laden und Berechtigung pruefen
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    cache_service = get_ocr_cache_service()

    cache_status = {
        "document_id": str(document_id),
        "cache_entries": [],
        "total_cached": 0
    }

    try:
        # Cache-Keys fuer dieses Dokument abrufen
        # Format: ocr_cache:{file_hash}:{backend}:{language}
        # Wir pruefen auch den document_id basierten Cache

        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        # Suche nach Cache-Eintraegen fuer dieses Dokument
        pattern = f"ocr_result:{document_id}:*"
        cursor = 0
        cache_keys = []

        while True:
            cursor, keys = await redis_manager._redis.scan(cursor=cursor, match=pattern, count=100)
            cache_keys.extend(keys)
            if cursor == 0:
                break

        for key in cache_keys:
            try:
                ttl = await redis_manager._redis.ttl(key)
                entry = {
                    "key": key.decode() if isinstance(key, bytes) else key,
                    "ttl_seconds": ttl if ttl > 0 else None,
                    "expires_in_hours": round(ttl / 3600, 1) if ttl > 0 else None
                }
                cache_status["cache_entries"].append(entry)
            except Exception as e:
                logger.warning("cache_key_inspection_failed", key=str(key), error=str(e))

        cache_status["total_cached"] = len(cache_keys)

        # Zusaetzlich: File-Hash basierten Cache pruefen
        if document.file_hash:
            hash_pattern = f"ocr_cache:{document.file_hash}:*"
            cursor = 0

            while True:
                cursor, keys = await redis_manager._redis.scan(cursor=cursor, match=hash_pattern, count=100)
                for key in keys:
                    try:
                        ttl = await redis_manager._redis.ttl(key)
                        key_str = key.decode() if isinstance(key, bytes) else key
                        # Backend aus Key extrahieren
                        parts = key_str.split(":")
                        backend = parts[2] if len(parts) > 2 else "unknown"
                        language = parts[3] if len(parts) > 3 else "unknown"

                        entry = {
                            "key": key_str,
                            "backend": backend,
                            "language": language,
                            "ttl_seconds": ttl if ttl > 0 else None,
                            "expires_in_hours": round(ttl / 3600, 1) if ttl > 0 else None,
                            "type": "file_hash_cache"
                        }
                        cache_status["cache_entries"].append(entry)
                        cache_status["total_cached"] += 1
                    except Exception as e:
                        logger.warning("hash_cache_inspection_failed", key=str(key), error=str(e))
                if cursor == 0:
                    break

    except Exception as e:
        logger.warning("cache_status_error", document_id=str(document_id), error=str(e))
        cache_status["error"] = f"Cache-Abfrage fehlgeschlagen: {str(e)}"

    # Dokument-Metadaten hinzufuegen
    cache_status["document_info"] = {
        "filename": document.original_filename,
        "status": document.status,
        "ocr_backend_used": document.ocr_backend_used,
        "has_extracted_text": bool(document.extracted_text),
        "file_hash": document.file_hash[:16] + "..." if document.file_hash else None
    }

    logger.debug(
        "ocr_cache_status_retrieved",
        document_id=str(document_id),
        cache_entries=cache_status["total_cached"]
    )

    return cache_status


@router.delete(
    "/documents/{document_id}/cache",
    summary="OCR-Cache loeschen",
    description="Loescht den OCR-Cache fuer ein Dokument."
)
async def invalidate_ocr_cache(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Loescht den OCR-Cache fuer ein Dokument.

    Nuetzlich wenn:
    - OCR-Ergebnisse fehlerhaft waren
    - Dokument aktualisiert wurde
    - Neuverarbeitung mit anderem Backend gewuenscht
    """
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.ocr_cache_service import get_ocr_cache_service

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    deleted_count = 0

    try:
        from app.core.redis_state import RedisStateManager
        redis_manager = RedisStateManager.get_instance()
        await redis_manager._ensure_connection()

        # Document-ID basierte Cache-Keys loeschen
        pattern = f"ocr_result:{document_id}:*"
        cursor = 0

        while True:
            cursor, keys = await redis_manager._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await redis_manager._redis.delete(*keys)
                deleted_count += len(keys)
            if cursor == 0:
                break

        # File-Hash basierte Cache-Keys loeschen
        if document.file_hash:
            hash_pattern = f"ocr_cache:{document.file_hash}:*"
            cursor = 0

            while True:
                cursor, keys = await redis_manager._redis.scan(cursor=cursor, match=hash_pattern, count=100)
                if keys:
                    await redis_manager._redis.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break

        # OCR Cache Service auch invalidieren
        cache_service = get_ocr_cache_service()
        await cache_service.invalidate_document_cache(str(document_id))

    except Exception as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.error("cache_invalidation_error", document_id=str(document_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Cache-Invalidierung fehlgeschlagen. Bitte erneut versuchen."
        )

    logger.info(
        "ocr_cache_invalidated",
        document_id=str(document_id),
        deleted_count=deleted_count,
        user_id=str(current_user.id)
    )

    return {
        "document_id": str(document_id),
        "cache_cleared": True,
        "entries_deleted": deleted_count,
        "message": f"OCR-Cache geloescht ({deleted_count} Eintraege)"
    }


# =============================================================================
# Batch OCR Operations
# =============================================================================


class BatchReprocessRequest(BaseModel):
    """Anfrage fuer Batch-OCR-Neuverarbeitung."""
    document_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der Dokument-IDs (max. 100)"
    )
    backend: str = Field(
        "auto",
        description="OCR-Backend: auto, deepseek, got_ocr, surya"
    )
    priority: int = Field(
        5,
        ge=1,
        le=10,
        description="Verarbeitungsprioritaet (1=niedrig, 10=hoch)"
    )
    force: bool = Field(
        False,
        description="Auch bereits verarbeitete Dokumente neu verarbeiten"
    )


class BatchReprocessResponse(BaseModel):
    """Antwort auf Batch-OCR-Neuverarbeitung."""
    total_requested: int = Field(..., description="Anzahl angeforderter Dokumente")
    jobs_created: int = Field(..., description="Anzahl erstellter Jobs")
    skipped: int = Field(..., description="Anzahl uebersprungener Dokumente")
    failed: int = Field(..., description="Anzahl fehlgeschlagener Dokumente")
    job_ids: list[str] = Field(default=[], description="Liste der Job-IDs")
    details: list[dict] = Field(default=[], description="Details pro Dokument")


@router.post(
    "/documents/batch/reprocess",
    response_model=BatchReprocessResponse,
    summary="Batch-OCR-Neuverarbeitung",
    description="Startet die OCR-Verarbeitung fuer mehrere Dokumente gleichzeitig."
)
async def batch_reprocess_ocr(
    request: BatchReprocessRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> BatchReprocessResponse:
    """Batch-OCR-Neuverarbeitung fuer mehrere Dokumente.

    **Anwendungsfaelle:**
    - Neuverarbeitung nach Backend-Update
    - Qualitaetsverbesserung mit anderem Backend
    - Massenneuverarbeitung nach Fehler

    **Limits:**
    - Maximal 100 Dokumente pro Anfrage
    - Rate-Limiting gilt fuer jeden erstellten Job

    **Beispiel:**
    ```
    POST /api/v1/ocr/documents/batch/reprocess
    {
        "document_ids": ["uuid1", "uuid2", "uuid3"],
        "backend": "deepseek",
        "priority": 8,
        "force": true
    }
    ```

    **Rueckgabe:**
    - job_ids: Liste der erstellten Celery-Job-IDs
    - details: Status pro Dokument (created, skipped, failed)
    """
    from sqlalchemy import select
    from app.db.models import Document, ProcessingJob
    from app.workers.celery_app import celery_app
    from uuid import uuid4

    # Backend validieren
    valid_backends = ["auto", "deepseek", "got_ocr", "surya"]
    if request.backend not in valid_backends:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiges Backend. Erlaubt: {', '.join(valid_backends)}"
        )

    jobs_created = 0
    skipped = 0
    failed = 0
    job_ids = []
    details = []

    logger.info(
        "batch_ocr_reprocess_started",
        user_id=str(current_user.id),
        document_count=len(request.document_ids),
        backend=request.backend,
        force=request.force
    )

    for doc_id in request.document_ids:
        try:
            # Dokument laden
            doc_query = select(Document).where(Document.id == doc_id)
            result = await db.execute(doc_query)
            document = result.scalar_one_or_none()

            # Validierungen
            if not document:
                details.append({
                    "document_id": str(doc_id),
                    "status": "failed",
                    "reason": "Dokument nicht gefunden"
                })
                failed += 1
                continue

            if document.owner_id != current_user.id and not current_user.is_superuser:
                details.append({
                    "document_id": str(doc_id),
                    "status": "failed",
                    "reason": "Keine Berechtigung"
                })
                failed += 1
                continue

            if document.is_deleted:
                details.append({
                    "document_id": str(doc_id),
                    "status": "skipped",
                    "reason": "Dokument geloescht"
                })
                skipped += 1
                continue

            # Pruefen ob bereits in Verarbeitung
            job_query = select(ProcessingJob).where(
                ProcessingJob.document_id == doc_id,
                ProcessingJob.status.in_(["queued", "processing"])
            )
            result = await db.execute(job_query)
            existing_job = result.scalar_one_or_none()

            if existing_job:
                details.append({
                    "document_id": str(doc_id),
                    "status": "skipped",
                    "reason": f"Bereits in Verarbeitung (Job: {existing_job.id})"
                })
                skipped += 1
                continue

            # Pruefen ob bereits verarbeitet (wenn force=false)
            if document.status == "completed" and not request.force:
                details.append({
                    "document_id": str(doc_id),
                    "status": "skipped",
                    "reason": "Bereits verarbeitet (force=false)"
                })
                skipped += 1
                continue

            # OCR-Job erstellen
            job_id = str(uuid4())

            processing_job = ProcessingJob(
                id=UUID(job_id),
                document_id=doc_id,
                job_type="ocr",
                status="queued",
                priority=request.priority,
                config={
                    "backend": request.backend,
                    "force_reprocess": request.force,
                    "batch_job": True
                }
            )
            db.add(processing_job)

            # Dokument-Status aktualisieren
            document.status = "queued"
            if request.backend != "auto":
                document.ocr_backend_used = request.backend

            # Celery Task starten
            celery_app.send_task(
                "app.workers.tasks.ocr_tasks.process_document_ocr",
                args=[str(doc_id), request.backend, request.priority],
                task_id=job_id,
                priority=10 - request.priority
            )

            job_ids.append(job_id)
            details.append({
                "document_id": str(doc_id),
                "status": "created",
                "job_id": job_id
            })
            jobs_created += 1

        except Exception as e:
            logger.error(
                "batch_ocr_document_error",
                document_id=str(doc_id),
                error=str(e)
            )
            details.append({
                "document_id": str(doc_id),
                "status": "failed",
                "reason": f"Fehler: {str(e)}"
            })
            failed += 1

    # Alle Aenderungen speichern
    await db.commit()

    logger.info(
        "batch_ocr_reprocess_completed",
        user_id=str(current_user.id),
        jobs_created=jobs_created,
        skipped=skipped,
        failed=failed
    )

    return BatchReprocessResponse(
        total_requested=len(request.document_ids),
        jobs_created=jobs_created,
        skipped=skipped,
        failed=failed,
        job_ids=job_ids,
        details=details
    )


@router.get(
    "/documents/batch/status",
    summary="Batch-Job-Status abfragen",
    description="Gibt den Status mehrerer OCR-Jobs zurueck."
)
async def batch_job_status(
    job_ids: str = Query(
        ...,
        description="Komma-separierte Liste von Job-IDs"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Status mehrerer OCR-Jobs abfragen.

    **Eingabe:** Komma-separierte Job-IDs aus batch/reprocess

    **Beispiel:**
    ```
    GET /api/v1/ocr/documents/batch/status?job_ids=uuid1,uuid2,uuid3
    ```
    """
    from sqlalchemy import select
    from app.db.models import ProcessingJob

    # Job-IDs parsen
    job_id_list = [jid.strip() for jid in job_ids.split(",") if jid.strip()]

    if not job_id_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens eine Job-ID erforderlich"
        )

    if len(job_id_list) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximal 100 Jobs pro Anfrage"
        )

    jobs_status = []
    completed = 0
    processing = 0
    queued = 0
    failed_count = 0

    for job_id in job_id_list:
        try:
            job_uuid = UUID(job_id)
            job_query = select(ProcessingJob).where(ProcessingJob.id == job_uuid)
            result = await db.execute(job_query)
            job = result.scalar_one_or_none()

            if not job:
                jobs_status.append({
                    "job_id": job_id,
                    "status": "not_found"
                })
                continue

            job_status = {
                "job_id": job_id,
                "document_id": str(job.document_id),
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if hasattr(job, 'completed_at') and job.completed_at else None,
            }

            if job.status == "completed":
                completed += 1
            elif job.status == "processing":
                processing += 1
            elif job.status == "queued":
                queued += 1
            elif job.status == "failed":
                failed_count += 1
                job_status["error"] = job.error_message if hasattr(job, 'error_message') else None

            jobs_status.append(job_status)

        except ValueError:
            jobs_status.append({
                "job_id": job_id,
                "status": "invalid_id"
            })

    return {
        "total": len(job_id_list),
        "summary": {
            "completed": completed,
            "processing": processing,
            "queued": queued,
            "failed": failed_count,
            "not_found": len(job_id_list) - completed - processing - queued - failed_count
        },
        "jobs": jobs_status
    }


# =============================================================================
# Semantic Validation (Phase 2.1)
# =============================================================================


@router.post(
    "/documents/{document_id}/semantic-validate",
    summary="Semantische Validierung durchfuehren",
    description="Validiert OCR-Ergebnisse gegen Stammdaten und Business Rules.",
)
async def semantic_validate_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Fuehrt semantische Validierung fuer ein Dokument durch.

    **Phase 2.1: OCR Evolution - Semantic Validation**

    Validiert gegen:
    - **Lexware Master Data**: Kundennummern, Lieferantennamen, IBANs
    - **Betragsplausibilitaet**: Negative Betraege, ungewoehnlich hohe Werte
    - **Betragskonsistenz**: Brutto = Netto + MwSt
    - **MwSt-Berechnung**: Korrekte Steuerberechnung
    - **Formatvalidierung**: IBAN-Pruefsumme, USt-ID Format, Datumsformate

    **Rueckgabe:**
    - overall_score: Gesamtbewertung (0.0 - 1.0)
    - errors/warnings/passed: Anzahl der jeweiligen Validierungen
    - results: Detaillierte Validierungsergebnisse
    - matched_entity: Gefundene Entity aus Stammdaten
    - suggestions: Verbesserungsvorschlaege

    **Anwendungsfaelle:**
    - Automatische Qualitaetspruefung nach OCR
    - Entity-Linking Vorschlaege
    - Compliance-Checks vor Buchung
    """
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.ocr.semantic_validation_service import SemanticValidationService

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    # Semantische Validierung durchfuehren
    service = SemanticValidationService(db)
    report = await service.validate_document(str(document_id))

    logger.info(
        "semantic_validation_completed",
        document_id=str(document_id),
        overall_score=report.overall_score,
        errors=report.errors,
        warnings=report.warnings,
        user_id=str(current_user.id),
    )

    return report.model_dump()


@router.get(
    "/documents/{document_id}/validation-report",
    summary="Validierungsbericht abrufen",
    description="Ruft den letzten semantischen Validierungsbericht ab.",
)
async def get_validation_report(
    document_id: UUID,
    revalidate: bool = Query(
        False, description="Wenn True, wird Validierung erneut durchgefuehrt"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Ruft den Validierungsbericht fuer ein Dokument ab.

    **Parameter:**
    - revalidate: Bei True wird eine neue Validierung durchgefuehrt

    **Anwendungsfaelle:**
    - Anzeige des Validierungsstatus in der UI
    - Pruefung vor Freigabe/Buchung
    - Qualitaetsuebersicht
    """
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.ocr.semantic_validation_service import SemanticValidationService

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Keine Berechtigung fuer dieses Dokument"
        )

    # Validierung durchfuehren (cached oder neu)
    service = SemanticValidationService(db)
    report = await service.validate_document(str(document_id))

    return {
        "document_id": str(document_id),
        "document_filename": document.original_filename,
        "document_status": document.status,
        "validation": report.model_dump(),
    }


@router.post(
    "/documents/batch/semantic-validate",
    summary="Batch-Semantische-Validierung",
    description="Validiert mehrere Dokumente gleichzeitig.",
)
async def batch_semantic_validate(
    document_ids: list[UUID] = Query(
        ...,
        description="Liste der Dokument-IDs (max. 50)"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch-Validierung fuer mehrere Dokumente.

    **Limit:** Maximal 50 Dokumente pro Anfrage.

    **Rueckgabe:**
    - summary: Zusammenfassung ueber alle Dokumente
    - results: Validierungsergebnisse pro Dokument

    **Anwendungsfaelle:**
    - Qualitaetspruefung einer Dokumentencharge
    - Uebersicht vor Batch-Freigabe
    """
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.ocr.semantic_validation_service import SemanticValidationService

    if len(document_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximal 50 Dokumente pro Anfrage"
        )

    service = SemanticValidationService(db)
    results = []
    total_score = 0.0
    total_errors = 0
    total_warnings = 0
    valid_count = 0

    for doc_id in document_ids:
        try:
            # Dokument pruefen
            doc_query = select(Document).where(Document.id == doc_id)
            result = await db.execute(doc_query)
            document = result.scalar_one_or_none()

            if not document:
                results.append({
                    "document_id": str(doc_id),
                    "status": "not_found",
                })
                continue

            if document.owner_id != current_user.id and not current_user.is_superuser:
                results.append({
                    "document_id": str(doc_id),
                    "status": "no_permission",
                })
                continue

            # Validierung
            report = await service.validate_document(str(doc_id))

            results.append({
                "document_id": str(doc_id),
                "filename": document.original_filename,
                "status": "validated",
                "overall_score": report.overall_score,
                "errors": report.errors,
                "warnings": report.warnings,
                "passed": report.passed,
                "matched_entity": report.matched_entity,
            })

            total_score += report.overall_score
            total_errors += report.errors
            total_warnings += report.warnings
            valid_count += 1

        except Exception as e:
            logger.error(
                "batch_validation_error",
                document_id=str(doc_id),
                error=str(e)
            )
            results.append({
                "document_id": str(doc_id),
                "status": "error",
                "message": "Validierung fehlgeschlagen",
            })

    avg_score = total_score / valid_count if valid_count > 0 else 0.0

    return {
        "total_requested": len(document_ids),
        "validated": valid_count,
        "summary": {
            "average_score": round(avg_score, 3),
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "high_quality_count": sum(
                1 for r in results
                if r.get("status") == "validated" and r.get("overall_score", 0) >= 0.9
            ),
            "needs_review_count": sum(
                1 for r in results
                if r.get("status") == "validated" and r.get("errors", 0) > 0
            ),
        },
        "results": results,
    }


# =============================================================================
# Handwriting Detection Endpoints
# =============================================================================


class HandwritingRegionResponse(BaseModel):
    """Eine erkannte handschriftliche Region."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    region_type: str
    features: list[str]
    area: int


class HandwritingAnalysisResponse(BaseModel):
    """Antwort der Handschrift-Analyse."""
    document_id: str
    has_handwriting: bool
    handwriting_percentage: float
    primary_type: str
    confidence: float
    confidence_level: str
    regions: list[HandwritingRegionResponse]
    recommended_backend: str
    confidence_penalty: float
    analysis_details: Dict[str, Any]


@router.post(
    "/documents/{document_id}/analyze-handwriting",
    response_model=HandwritingAnalysisResponse,
    summary="Handschrift-Analyse",
    description="Analysiert ein Dokument auf handschriftliche Inhalte.",
)
async def analyze_document_handwriting(
    document_id: UUID,
    detect_signatures: bool = Query(True, description="Unterschriften erkennen"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> HandwritingAnalysisResponse:
    """
    Analysiert ein Dokument auf handschriftliche Inhalte.

    Erkennt:
    - Unterschriften auf Vertraegen
    - Handschriftliche Notizen/Anmerkungen
    - Formular-Ausfuellungen
    - Komplett handgeschriebene Dokumente

    Gibt ausserdem eine Confidence-Penalty zurueck, die bei der OCR-Verarbeitung
    beruecksichtigt werden sollte (Handschrift ist schwerer zu erkennen).
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.db.models import Document
    from app.agents.preprocessing.handwriting_detector import (
        detect_handwriting,
        HandwritingAnalysis,
    )

    logger.info(
        "handwriting_analysis_requested",
        document_id=str(document_id),
        user_id=str(current_user.id),
        detect_signatures=detect_signatures,
    )

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden"
        )

    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Kein Zugriff auf dieses Dokument"
        )

    # Dokument-Bild laden
    try:
        # Versuche Bild zu laden (bei PDF erste Seite konvertieren)
        from app.services.storage_service import StorageService
        import numpy as np
        from PIL import Image
        import io

        storage = StorageService()
        file_content = await storage.get_file(str(document.storage_path))

        if not file_content:
            raise HTTPException(
                status_code=404,
                detail="Dokument-Datei nicht gefunden"
            )

        # Format bestimmen
        file_ext = Path(document.storage_path).suffix.lower() if document.storage_path else ""

        if file_ext == ".pdf":
            # PDF: Erste Seite als Bild
            try:
                import fitz  # PyMuPDF
                pdf_doc = fitz.open(stream=file_content, filetype="pdf")
                page = pdf_doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))  # 2x Zoom fuer bessere Qualitaet
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pdf_doc.close()
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="PyMuPDF nicht verfuegbar fuer PDF-Analyse"
                )
        else:
            # Bild direkt laden
            image = Image.open(io.BytesIO(file_content))

        # Zu numpy array konvertieren
        image_array = np.array(image)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "handwriting_image_load_error",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Laden des Dokument-Bildes: {str(e)}"
        )

    # Handschrift-Analyse durchfuehren
    try:
        analysis: HandwritingAnalysis = await detect_handwriting(
            image_array,
            metadata={"document_id": str(document_id), "filename": document.original_filename},
            detect_signatures=detect_signatures,
        )
    except Exception as e:
        logger.error(
            "handwriting_analysis_error",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Handschrift-Analyse fehlgeschlagen: {str(e)}"
        )

    # Ergebnis in metadata speichern
    if document.metadata is None:
        document.metadata = {}
    document.metadata["handwriting_analysis"] = {
        "has_handwriting": analysis.has_handwriting,
        "handwriting_percentage": analysis.handwriting_percentage,
        "primary_type": analysis.primary_type.value,
        "confidence": analysis.confidence,
        "confidence_penalty": analysis.confidence_penalty,
        "recommended_backend": analysis.recommended_backend,
        "region_count": len(analysis.regions),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.commit()

    logger.info(
        "handwriting_analysis_complete",
        document_id=str(document_id),
        has_handwriting=analysis.has_handwriting,
        handwriting_percentage=round(analysis.handwriting_percentage, 1),
        primary_type=analysis.primary_type.value,
    )

    return HandwritingAnalysisResponse(
        document_id=str(document_id),
        has_handwriting=analysis.has_handwriting,
        handwriting_percentage=analysis.handwriting_percentage,
        primary_type=analysis.primary_type.value,
        confidence=analysis.confidence,
        confidence_level=analysis.confidence_level.value,
        regions=[
            HandwritingRegionResponse(
                x=r.x,
                y=r.y,
                width=r.width,
                height=r.height,
                confidence=r.confidence,
                region_type=r.region_type.value,
                features=[f.value for f in r.features],
                area=r.area,
            )
            for r in analysis.regions
        ],
        recommended_backend=analysis.recommended_backend,
        confidence_penalty=analysis.confidence_penalty,
        analysis_details=analysis.analysis_details,
    )


@router.get(
    "/documents/{document_id}/handwriting-report",
    response_model=Dict[str, Any],
    summary="Handschrift-Report abrufen",
    description="Ruft den letzten Handschrift-Analyse-Report ab.",
)
async def get_handwriting_report(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ruft den letzten Handschrift-Analyse-Report fuer ein Dokument ab.

    Falls keine Analyse vorhanden ist, wird eine neue durchgefuehrt.
    """
    from sqlalchemy import select
    from app.db.models import Document

    # Dokument laden
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Dokument nicht gefunden"
        )

    if document.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Kein Zugriff auf dieses Dokument"
        )

    # Gespeicherten Report holen
    if document.metadata and "handwriting_analysis" in document.metadata:
        analysis_data = document.metadata["handwriting_analysis"]
        return {
            "document_id": str(document_id),
            "filename": document.original_filename,
            "from_cache": True,
            "analysis": analysis_data,
        }

    # Keine Analyse vorhanden
    return {
        "document_id": str(document_id),
        "filename": document.original_filename,
        "from_cache": False,
        "analysis": None,
        "message": "Keine Handschrift-Analyse vorhanden. Nutzen Sie POST /analyze-handwriting.",
    }


@router.post(
    "/upload/analyze-handwriting",
    response_model=Dict[str, Any],
    summary="Handschrift-Analyse aus Upload",
    description="Analysiert eine hochgeladene Datei auf Handschrift ohne Dokument-Erstellung.",
)
async def analyze_upload_handwriting(
    file: UploadFile = File(..., description="Dokument (PDF, PNG, JPG, TIFF)"),
    detect_signatures: bool = Query(True, description="Unterschriften erkennen"),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Analysiert eine hochgeladene Datei auf handschriftliche Inhalte.

    Diese Methode speichert das Dokument nicht in der Datenbank,
    sondern fuehrt nur eine temporaere Analyse durch.
    """
    from app.agents.preprocessing.handwriting_detector import detect_handwriting
    import numpy as np
    from PIL import Image
    import io

    logger.info(
        "handwriting_upload_analysis_requested",
        user_id=str(current_user.id),
        filename=file.filename,
        content_type=file.content_type,
    )

    # Dateiformat validieren
    if file.filename:
        try:
            sanitized = sanitize_filename(file.filename)
            file_ext = Path(sanitized).suffix.lower()
        except PathTraversalError:
            raise HTTPException(
                status_code=400,
                detail="Ungueltiger Dateiname"
            )
    else:
        file_ext = ""

    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Nicht unterstuetztes Format. Erlaubt: {', '.join(allowed_extensions)}"
        )

    # Datei lesen
    try:
        file_content = await file.read()

        if file_ext == ".pdf":
            try:
                import fitz
                pdf_doc = fitz.open(stream=file_content, filetype="pdf")
                page = pdf_doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pdf_doc.close()
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="PyMuPDF nicht verfuegbar fuer PDF-Analyse"
                )
        else:
            image = Image.open(io.BytesIO(file_content))

        image_array = np.array(image)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Fehler beim Laden der Datei: {str(e)}"
        )

    # Analyse durchfuehren
    try:
        analysis = await detect_handwriting(
            image_array,
            metadata={"filename": file.filename, "upload_analysis": True},
            detect_signatures=detect_signatures,
        )
    except Exception as e:
        logger.error(
            "handwriting_upload_analysis_error",
            filename=file.filename,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Handschrift-Analyse fehlgeschlagen: {str(e)}"
        )

    logger.info(
        "handwriting_upload_analysis_complete",
        filename=file.filename,
        has_handwriting=analysis.has_handwriting,
        handwriting_percentage=round(analysis.handwriting_percentage, 1),
    )

    return {
        "filename": file.filename,
        "has_handwriting": analysis.has_handwriting,
        "handwriting_percentage": analysis.handwriting_percentage,
        "primary_type": analysis.primary_type.value,
        "confidence": analysis.confidence,
        "confidence_level": analysis.confidence_level.value,
        "region_count": len(analysis.regions),
        "regions": [
            {
                "x": r.x,
                "y": r.y,
                "width": r.width,
                "height": r.height,
                "confidence": r.confidence,
                "region_type": r.region_type.value,
                "features": [f.value for f in r.features],
            }
            for r in analysis.regions
        ],
        "recommended_backend": analysis.recommended_backend,
        "confidence_penalty": analysis.confidence_penalty,
        "recommendation": (
            "Dieses Dokument enthaelt handschriftliche Inhalte. "
            f"Empfohlenes Backend: {analysis.recommended_backend}. "
            f"Die OCR-Confidence sollte um {abs(analysis.confidence_penalty)*100:.0f}% reduziert werden."
            if analysis.has_handwriting
            else "Keine signifikanten handschriftlichen Inhalte erkannt."
        ),
    }


# =============================================================================
# Table Extraction Endpoints (Phase 2.3)
# =============================================================================


class TableCellResponse(BaseModel):
    """Response-Model fuer eine Tabellenzelle."""
    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    confidence: float
    data_type: str
    normalized_value: Optional[str] = None


class TableColumnResponse(BaseModel):
    """Response-Model fuer Spalten-Metadaten."""
    index: int
    header_text: str
    data_type: str
    alignment: str
    is_numeric: bool
    contains_currency: bool
    avg_confidence: float


class ExtractedTableResponse(BaseModel):
    """Response-Model fuer eine extrahierte Tabelle."""
    table_id: str
    page_number: int
    num_rows: int
    num_cols: int
    has_header: bool
    header_row_count: int
    table_type: str
    caption: Optional[str] = None
    overall_confidence: float
    cells: List[TableCellResponse]
    columns: List[TableColumnResponse]


class TableExtractionResultResponse(BaseModel):
    """Response-Model fuer Table Extraction Ergebnis."""
    document_id: str
    total_tables: int
    page_count: int
    extraction_timestamp: str
    processing_time_ms: int
    tables: List[ExtractedTableResponse]
    metadata: Dict[str, Any]


@router.post(
    "/documents/{document_id}/extract-tables",
    response_model=TableExtractionResultResponse,
    summary="Tabellen aus Dokument extrahieren",
    description="Extrahiert alle Tabellen aus einem Dokument mit Cell-Level Confidence.",
)
async def extract_document_tables(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Extrahiert Tabellen aus einem Dokument.

    - Cell-Level Confidence Tracking
    - Spanning Cell Detection (row_span, col_span)
    - Header-Row Erkennung
    - Automatische Typ-Erkennung
    """
    from app.services.ocr.table_extraction_service import (
        TableExtractionService,
        get_table_extraction_service,
    )

    # Dokument laden und Berechtigung pruefen
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    # Berechtigung pruefen
    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    # Table Extraction Service
    service = get_table_extraction_service(db)

    # Layout aus Metadata laden falls vorhanden
    layout = None
    if document.metadata and document.metadata.get("layout"):
        from app.agents.ocr.models.layout_models import DocumentLayout
        try:
            layout_data = document.metadata.get("layout")
            if isinstance(layout_data, dict):
                layout = DocumentLayout.from_dict(layout_data)
        except Exception as e:
            logger.warning(
                "layout_parse_error",
                document_id=str(document_id),
                error=str(e),
            )

    # Tabellen extrahieren
    extraction_result = await service.extract_tables_from_document(
        document_id=str(document_id),
        layout=layout,
    )

    # In Metadata speichern fuer spaetere Abfragen
    if document.metadata is None:
        document.metadata = {}
    document.metadata["tables_extracted"] = True
    document.metadata["table_extraction_result"] = extraction_result.to_dict()
    document.metadata["tables_extraction_timestamp"] = datetime.now(timezone.utc).isoformat()

    await db.commit()

    logger.info(
        "tables_extracted",
        document_id=str(document_id),
        table_count=extraction_result.total_tables,
        user_id=str(current_user.id),
    )

    return extraction_result.to_dict()


@router.get(
    "/documents/{document_id}/tables",
    response_model=TableExtractionResultResponse,
    summary="Extrahierte Tabellen abrufen",
    description="Ruft gecachte Tabellen-Extraktion eines Dokuments ab.",
)
async def get_document_tables(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Ruft bereits extrahierte Tabellen aus einem Dokument ab.
    """
    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    # Gecachte Extraktion pruefen
    if not document.metadata or not document.metadata.get("table_extraction_result"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Tabellen-Extraktion vorhanden. Bitte zuerst /extract-tables aufrufen.",
        )

    return document.metadata["table_extraction_result"]


@router.get(
    "/documents/{document_id}/tables/{table_index}/export",
    summary="Tabelle exportieren",
    description="Exportiert eine spezifische Tabelle in verschiedenen Formaten.",
)
async def export_document_table(
    document_id: UUID,
    table_index: int,
    format: str = Query(
        default="markdown",
        description="Export-Format: markdown, csv, json, json_ld, html, excel_compatible",
    ),
    include_metadata: bool = Query(
        default=False,
        description="Metadaten im Export inkludieren",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Exportiert eine Tabelle in das gewuenschte Format.

    Unterstuetzte Formate:
    - markdown: Markdown-Tabelle
    - csv: CSV mit Semikolon-Trenner
    - json: JSON-Array
    - json_ld: Schema.org JSON-LD
    - html: HTML-Tabelle
    - excel_compatible: CSV mit BOM fuer Excel
    """
    from app.services.ocr.table_extraction_service import (
        TableExportFormat,
        TableExtractionService,
        ExtractedTable,
        get_table_extraction_service,
    )

    # Format validieren
    valid_formats = ["markdown", "csv", "json", "json_ld", "html", "excel_compatible"]
    if format not in valid_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiges Format. Erlaubt: {', '.join(valid_formats)}",
        )

    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    # Gecachte Extraktion pruefen
    if not document.metadata or not document.metadata.get("table_extraction_result"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Tabellen-Extraktion vorhanden.",
        )

    extraction_data = document.metadata["table_extraction_result"]
    tables_data = extraction_data.get("tables", [])

    if table_index < 0 or table_index >= len(tables_data):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tabelle {table_index} nicht gefunden. Verfuegbar: 0-{len(tables_data)-1}",
        )

    # Tabelle rekonstruieren
    from app.services.ocr.table_extraction_service import (
        EnhancedTableCell,
        TableColumn,
        CellDataType,
        TableType,
    )

    table_data = tables_data[table_index]

    # Cells rekonstruieren
    cells = []
    for c in table_data.get("cells", []):
        cells.append(EnhancedTableCell(
            row=c["row"],
            col=c["col"],
            text=c["text"],
            row_span=c.get("row_span", 1),
            col_span=c.get("col_span", 1),
            is_header=c.get("is_header", False),
            confidence=c.get("confidence", 0.0),
            data_type=CellDataType(c.get("data_type", "text")),
            normalized_value=c.get("normalized_value"),
        ))

    # Columns rekonstruieren
    columns = []
    for col in table_data.get("columns", []):
        columns.append(TableColumn(
            index=col["index"],
            header_text=col.get("header_text", ""),
            data_type=CellDataType(col.get("data_type", "text")),
            alignment=col.get("alignment", "left"),
            is_numeric=col.get("is_numeric", False),
            contains_currency=col.get("contains_currency", False),
            avg_confidence=col.get("avg_confidence", 0.0),
        ))

    table = ExtractedTable(
        table_id=table_data["table_id"],
        page_number=table_data["page_number"],
        num_rows=table_data["num_rows"],
        num_cols=table_data["num_cols"],
        cells=cells,
        columns=columns,
        has_header=table_data.get("has_header", False),
        header_row_count=table_data.get("header_row_count", 0),
        table_type=TableType(table_data.get("table_type", "generic")),
        caption=table_data.get("caption"),
        overall_confidence=table_data.get("overall_confidence", 0.0),
    )

    # Export durchfuehren
    service = get_table_extraction_service()
    export_format = TableExportFormat(format)
    exported = service.export_table(table, export_format, include_metadata)

    # Content-Type und Filename bestimmen
    content_types = {
        "markdown": "text/markdown",
        "csv": "text/csv",
        "json": "application/json",
        "json_ld": "application/ld+json",
        "html": "text/html",
        "excel_compatible": "text/csv",
    }

    extensions = {
        "markdown": "md",
        "csv": "csv",
        "json": "json",
        "json_ld": "json",
        "html": "html",
        "excel_compatible": "csv",
    }

    content_type = content_types.get(format, "text/plain")
    extension = extensions.get(format, "txt")
    filename = f"table_{table_index}_doc_{document_id}.{extension}"

    return Response(
        content=exported,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/upload/extract-tables",
    summary="Tabellen aus Upload extrahieren",
    description="Extrahiert Tabellen aus einer hochgeladenen Datei ohne Speicherung.",
)
async def extract_upload_tables(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Extrahiert Tabellen aus einer hochgeladenen Datei.

    Die Datei wird nicht gespeichert - nur temporaer verarbeitet.
    Unterstuetzt: PDF, PNG, JPG
    """
    from app.services.ocr.table_extraction_service import (
        TableExtractionService,
        get_table_extraction_service,
    )
    from app.agents.ocr.docling_layout_analyzer import get_docling_layout_analyzer
    import time

    # Dateiformat pruefen
    allowed_extensions = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"]
    file_ext = "." + file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nicht unterstuetztes Dateiformat. Erlaubt: {', '.join(allowed_extensions)}",
        )

    # Datei lesen
    content = await file.read()

    if len(content) > 50 * 1024 * 1024:  # 50MB Limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Datei zu gross. Maximum: 50MB.",
        )

    start_time = time.time()

    # Layout-Analyse durchfuehren
    try:
        layout_analyzer = get_docling_layout_analyzer()
        layout = await layout_analyzer.analyze_layout(content)
    except Exception as e:
        logger.error(
            "layout_analysis_failed",
            filename=file.filename,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Layout-Analyse fehlgeschlagen.",
        )

    # Tabellen extrahieren
    service = get_table_extraction_service()
    temp_doc_id = f"upload_{current_user.id}_{int(time.time())}"

    extraction_result = await service.extract_tables_from_document(
        document_id=temp_doc_id,
        layout=layout,
    )

    processing_time = int((time.time() - start_time) * 1000)

    logger.info(
        "upload_tables_extracted",
        filename=file.filename,
        table_count=extraction_result.total_tables,
        processing_time_ms=processing_time,
        user_id=str(current_user.id),
    )

    result_dict = extraction_result.to_dict()
    result_dict["filename"] = file.filename
    result_dict["processing_time_ms"] = processing_time

    return result_dict


@router.get(
    "/documents/{document_id}/tables/export-all",
    summary="Alle Tabellen exportieren",
    description="Exportiert alle Tabellen eines Dokuments in einem Format.",
)
async def export_all_document_tables(
    document_id: UUID,
    format: str = Query(
        default="markdown",
        description="Export-Format: markdown, csv, json, json_ld, html",
    ),
    include_metadata: bool = Query(
        default=False,
        description="Metadaten im Export inkludieren",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Response:
    """
    Exportiert alle Tabellen eines Dokuments.
    """
    from app.services.ocr.table_extraction_service import (
        TableExportFormat,
        TableExtractionResult,
        ExtractedTable,
        EnhancedTableCell,
        TableColumn,
        CellDataType,
        TableType,
        get_table_extraction_service,
    )

    # Format validieren
    valid_formats = ["markdown", "csv", "json", "json_ld", "html"]
    if format not in valid_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiges Format. Erlaubt: {', '.join(valid_formats)}",
        )

    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    # Gecachte Extraktion pruefen
    if not document.metadata or not document.metadata.get("table_extraction_result"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine Tabellen-Extraktion vorhanden.",
        )

    extraction_data = document.metadata["table_extraction_result"]

    # TableExtractionResult rekonstruieren
    tables: List[ExtractedTable] = []
    for table_data in extraction_data.get("tables", []):
        cells = []
        for c in table_data.get("cells", []):
            cells.append(EnhancedTableCell(
                row=c["row"],
                col=c["col"],
                text=c["text"],
                row_span=c.get("row_span", 1),
                col_span=c.get("col_span", 1),
                is_header=c.get("is_header", False),
                confidence=c.get("confidence", 0.0),
                data_type=CellDataType(c.get("data_type", "text")),
                normalized_value=c.get("normalized_value"),
            ))

        columns = []
        for col in table_data.get("columns", []):
            columns.append(TableColumn(
                index=col["index"],
                header_text=col.get("header_text", ""),
                data_type=CellDataType(col.get("data_type", "text")),
                alignment=col.get("alignment", "left"),
                is_numeric=col.get("is_numeric", False),
                contains_currency=col.get("contains_currency", False),
                avg_confidence=col.get("avg_confidence", 0.0),
            ))

        tables.append(ExtractedTable(
            table_id=table_data["table_id"],
            page_number=table_data["page_number"],
            num_rows=table_data["num_rows"],
            num_cols=table_data["num_cols"],
            cells=cells,
            columns=columns,
            has_header=table_data.get("has_header", False),
            header_row_count=table_data.get("header_row_count", 0),
            table_type=TableType(table_data.get("table_type", "generic")),
            caption=table_data.get("caption"),
            overall_confidence=table_data.get("overall_confidence", 0.0),
        ))

    extraction_result = TableExtractionResult(
        document_id=extraction_data["document_id"],
        tables=tables,
        total_tables=extraction_data["total_tables"],
        page_count=extraction_data["page_count"],
        extraction_timestamp=extraction_data["extraction_timestamp"],
        processing_time_ms=extraction_data["processing_time_ms"],
        metadata=extraction_data.get("metadata", {}),
    )

    # Export durchfuehren
    service = get_table_extraction_service()
    export_format = TableExportFormat(format)
    exported = service.export_all_tables(extraction_result, export_format, include_metadata)

    # Content-Type bestimmen
    content_types = {
        "markdown": "text/markdown",
        "csv": "text/csv",
        "json": "application/json",
        "json_ld": "application/ld+json",
        "html": "text/html",
    }

    extensions = {
        "markdown": "md",
        "csv": "csv",
        "json": "json",
        "json_ld": "json",
        "html": "html",
    }

    content_type = content_types.get(format, "text/plain")
    extension = extensions.get(format, "txt")
    filename = f"tables_doc_{document_id}.{extension}"

    return Response(
        content=exported,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# =============================================================================
# Cross-Backend Consistency Endpoints (Phase 2.4)
# =============================================================================


class InconsistentRegionResponse(BaseModel):
    """Response-Model fuer inkonsistente Region."""
    region_id: str
    region_type: str
    start_position: int
    end_position: int
    backend_values: Dict[str, str]
    backend_confidences: Dict[str, float]
    agreement_score: float
    consistency_level: str
    review_priority: str
    suggested_value: str
    suggestion_confidence: float
    context_before: str
    context_after: str
    is_critical_field: bool


class ConsistencyReportResponse(BaseModel):
    """Response-Model fuer Consistency Report."""
    document_id: str
    backends_used: List[str]
    overall_agreement: float
    consistency_level: str
    total_regions_analyzed: int
    inconsistent_region_count: int
    inconsistent_regions: List[InconsistentRegionResponse]
    high_priority_count: int
    needs_third_backend: bool
    third_backend_triggered: bool
    third_backend_name: Optional[str] = None
    final_text: str
    final_confidence: float
    processing_time_ms: int
    recommendations: List[str]
    analysis_timestamp: str


@router.post(
    "/documents/{document_id}/check-consistency",
    response_model=ConsistencyReportResponse,
    summary="Cross-Backend Konsistenz pruefen",
    description="Vergleicht OCR-Ergebnisse verschiedener Backends und identifiziert Inkonsistenzen.",
)
async def check_document_consistency(
    document_id: UUID,
    trigger_third_backend: bool = Query(
        default=False,
        description="Drittes Backend bei niedriger Konsistenz automatisch triggern",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Prueft die Konsistenz zwischen OCR-Backend-Ergebnissen.

    - Token-Level Vergleich zwischen Backends
    - Identifiziert inkonsistente Regionen
    - Flaggt kritische Felder (Betraege, Daten)
    - Optional: Triggert drittes Backend bei niedriger Konsistenz
    """
    from app.services.ocr.cross_backend_consistency_service import (
        get_cross_backend_consistency_service,
    )
    from app.services.ensemble_voting import OCRResult

    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    # OCR-Ergebnisse aus Metadata laden
    if not document.metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine OCR-Ergebnisse vorhanden.",
        )

    ocr_results_data = document.metadata.get("ocr_results", [])
    if not ocr_results_data:
        # Fallback: Einzelnes Ergebnis
        if document.metadata.get("ocr_text"):
            ocr_results_data = [{
                "backend": document.metadata.get("ocr_backend", "unknown"),
                "text": document.metadata.get("ocr_text", ""),
                "confidence": document.metadata.get("ocr_confidence", 0.0),
            }]

    if len(ocr_results_data) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens 2 OCR-Ergebnisse von verschiedenen Backends erforderlich.",
        )

    # Konvertiere zu OCRResult
    ocr_results = [
        OCRResult(
            backend=r.get("backend", "unknown"),
            text=r.get("text", ""),
            confidence=r.get("confidence", 0.0),
        )
        for r in ocr_results_data
    ]

    # Consistency Service
    service = get_cross_backend_consistency_service(db=db)

    # Analyse durchfuehren
    report = await service.analyze_consistency(
        document_id=str(document_id),
        results=ocr_results,
        trigger_third_backend=trigger_third_backend,
    )

    # Report in Metadata speichern
    if document.metadata is None:
        document.metadata = {}
    document.metadata["consistency_report"] = report.to_dict()
    document.metadata["consistency_checked_at"] = datetime.now(timezone.utc).isoformat()

    await db.commit()

    logger.info(
        "consistency_check_complete",
        document_id=str(document_id),
        agreement=round(report.overall_agreement, 3),
        level=report.consistency_level.value,
        inconsistent_count=len(report.inconsistent_regions),
        user_id=str(current_user.id),
    )

    return report.to_dict()


@router.get(
    "/documents/{document_id}/consistency-report",
    response_model=ConsistencyReportResponse,
    summary="Konsistenz-Report abrufen",
    description="Ruft den gecachten Konsistenz-Report eines Dokuments ab.",
)
async def get_consistency_report(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Ruft bereits erstellten Konsistenz-Report ab."""
    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    if not document.metadata or not document.metadata.get("consistency_report"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Konsistenz-Report vorhanden. Bitte zuerst /check-consistency aufrufen.",
        )

    return document.metadata["consistency_report"]


@router.get(
    "/documents/{document_id}/inconsistent-regions",
    summary="Inkonsistente Regionen abrufen",
    description="Ruft Regionen mit Inkonsistenzen fuer manuelles Review ab.",
)
async def get_inconsistent_regions(
    document_id: UUID,
    min_priority: str = Query(
        default="normal",
        description="Minimale Prioritaet: immediate, high, normal, low",
    ),
    critical_only: bool = Query(
        default=False,
        description="Nur kritische Felder (Betraege, Daten)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Ruft inkonsistente Regionen fuer Review ab.

    Filtert nach:
    - Minimale Prioritaet (immediate > high > normal > low)
    - Kritische Felder (Betraege, Daten, IBANs)
    """
    from app.services.ocr.cross_backend_consistency_service import ReviewPriority

    # Prioritaet validieren
    valid_priorities = ["immediate", "high", "normal", "low"]
    if min_priority not in valid_priorities:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige Prioritaet. Erlaubt: {', '.join(valid_priorities)}",
        )

    # Dokument laden
    doc_query = select(Document).where(Document.id == str(document_id))
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden.",
        )

    if document.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung fuer dieses Dokument.",
        )

    if not document.metadata or not document.metadata.get("consistency_report"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Konsistenz-Report vorhanden.",
        )

    report = document.metadata["consistency_report"]
    regions = report.get("inconsistent_regions", [])

    # Nach Prioritaet filtern
    priority_order = ["immediate", "high", "normal", "low"]
    min_idx = priority_order.index(min_priority)
    allowed_priorities = set(priority_order[:min_idx + 1])

    filtered = [
        r for r in regions
        if r.get("review_priority") in allowed_priorities
    ]

    # Optional: Nur kritische Felder
    if critical_only:
        filtered = [r for r in filtered if r.get("is_critical_field", False)]

    return {
        "document_id": str(document_id),
        "total_inconsistent": len(report.get("inconsistent_regions", [])),
        "filtered_count": len(filtered),
        "filter_applied": {
            "min_priority": min_priority,
            "critical_only": critical_only,
        },
        "regions": filtered,
    }


@router.post(
    "/compare-backends",
    summary="Backend-Texte vergleichen",
    description="Vergleicht Texte verschiedener Backends direkt.",
)
async def compare_backend_texts(
    texts: List[str] = Body(
        ...,
        description="Liste von 2-4 Texten verschiedener Backends",
        min_length=2,
        max_length=4,
    ),
    backend_names: Optional[List[str]] = Body(
        default=None,
        description="Optionale Backend-Namen",
    ),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Vergleicht OCR-Texte verschiedener Backends.

    Nuetzlich fuer:
    - Schnelle Konsistenzpruefung ohne Dokument-Upload
    - Testing und Debugging
    - API-Integration
    """
    from app.services.ocr.cross_backend_consistency_service import (
        get_cross_backend_consistency_service,
        calculate_backend_agreement,
    )
    from app.services.ensemble_voting import OCRResult

    if len(texts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens 2 Texte erforderlich.",
        )

    # Backend-Namen generieren falls nicht angegeben
    if not backend_names:
        backend_names = [f"backend_{i}" for i in range(len(texts))]
    elif len(backend_names) != len(texts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anzahl der Backend-Namen muss der Anzahl der Texte entsprechen.",
        )

    # OCRResults erstellen
    results = [
        OCRResult(
            backend=name,
            text=text,
            confidence=1.0,  # Keine Confidence-Info verfuegbar
        )
        for name, text in zip(backend_names, texts)
    ]

    # Analyse durchfuehren
    service = get_cross_backend_consistency_service()
    report = await service.analyze_consistency(
        document_id="direct_comparison",
        results=results,
        trigger_third_backend=False,
    )

    return {
        "overall_agreement": round(report.overall_agreement, 3),
        "consistency_level": report.consistency_level.value,
        "backends_compared": backend_names,
        "inconsistent_count": len(report.inconsistent_regions),
        "final_text": report.final_text,
        "recommendations": report.recommendations,
        "inconsistent_regions": [r.to_dict() for r in report.inconsistent_regions[:20]],
    }


@router.get(
    "/consistency/statistics",
    summary="Konsistenz-Statistiken",
    description="Globale Statistiken ueber Backend-Konsistenz.",
)
async def get_consistency_statistics(
    days: int = Query(
        default=7,
        ge=1,
        le=90,
        description="Zeitraum in Tagen",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Ruft Konsistenz-Statistiken fuer den Mandanten ab.

    Zeigt:
    - Durchschnittliche Agreement-Scores
    - Haeufige Inkonsistenz-Typen
    - Backend-Performance-Vergleich
    """
    from datetime import timedelta

    # Zeitbereich
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Dokumente mit Konsistenz-Reports laden
    doc_query = select(Document).where(
        Document.company_id == current_user.company_id,
        Document.created_at >= start_date,
    )
    result = await db.execute(doc_query)
    documents = result.scalars().all()

    # Statistiken berechnen
    total_checks = 0
    agreement_scores: List[float] = []
    level_counts: Dict[str, int] = {"high": 0, "medium": 0, "low": 0, "critical": 0}
    region_type_counts: Dict[str, int] = {}
    third_backend_triggers = 0

    for doc in documents:
        if doc.metadata and doc.metadata.get("consistency_report"):
            report = doc.metadata["consistency_report"]
            total_checks += 1
            agreement_scores.append(report.get("overall_agreement", 0))

            level = report.get("consistency_level", "unknown")
            if level in level_counts:
                level_counts[level] += 1

            if report.get("third_backend_triggered"):
                third_backend_triggers += 1

            for region in report.get("inconsistent_regions", []):
                rt = region.get("region_type", "unknown")
                region_type_counts[rt] = region_type_counts.get(rt, 0) + 1

    avg_agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 0.0

    return {
        "period_days": days,
        "total_checks": total_checks,
        "average_agreement": round(avg_agreement, 3),
        "consistency_levels": level_counts,
        "third_backend_triggers": third_backend_triggers,
        "common_region_types": dict(sorted(
            region_type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]),
        "documents_needing_review": level_counts.get("critical", 0) + level_counts.get("low", 0),
    }


# =============================================================================
# Formula Extraction Endpoints (Feature 19: LaTeX Formula Parsing)
# =============================================================================


class FormulaExtractionRequest(BaseModel):
    """Anfrage fuer Formelextraktion aus Text."""

    text: str = Field(..., min_length=1, max_length=50000, description="OCR-Text mit Formeln")
    include_mathml: bool = Field(False, description="MathML-Konvertierung einschliessen")


class FormulaParsRequest(BaseModel):
    """Anfrage zum Parsen einer einzelnen Formel."""

    formula: str = Field(..., min_length=1, max_length=2000, description="LaTeX-Formel")
    context: Optional[str] = Field(None, description="Kontext-Hinweis (financial, scientific, etc.)")


class FormulaValidationRequest(BaseModel):
    """Anfrage zur Formel-Validierung."""

    formula: str = Field(..., min_length=1, max_length=2000, description="LaTeX-Formel zum Validieren")


class ExtractedFormulaResponse(BaseModel):
    """Einzelne extrahierte Formel."""

    original: str = Field(..., description="Original LaTeX-String")
    formula_type: str = Field(..., description="Typ: equation, fraction, sum, integral, etc.")
    context: str = Field(..., description="Kontext: financial, scientific, general")
    is_valid: bool = Field(..., description="Syntax valide?")
    confidence: float = Field(..., ge=0, le=1, description="Confidence-Score")
    extracted_values: List[Dict[str, Any]] = Field(default_factory=list, description="Extrahierte Zahlen/Einheiten")
    variables: List[str] = Field(default_factory=list, description="Erkannte Variablen")
    validation_issues: List[Dict[str, Any]] = Field(default_factory=list, description="Validierungsprobleme")
    mathml: Optional[str] = Field(None, description="MathML-Repraesentation")


class FormulaExtractionResponse(BaseModel):
    """Antwort fuer Formelextraktion."""

    erfolg: bool = Field(..., description="War Extraktion erfolgreich?")
    formeln_gefunden: int = Field(..., description="Anzahl gefundener Formeln")
    formeln: List[ExtractedFormulaResponse] = Field(default_factory=list, description="Extrahierte Formeln")
    fehler: Optional[str] = Field(None, description="Fehlermeldung bei Misserfolg")


class FormulaValidationResponse(BaseModel):
    """Antwort fuer Formel-Validierung."""

    is_valid: bool = Field(..., description="Formel syntaktisch korrekt?")
    issues: List[Dict[str, Any]] = Field(default_factory=list, description="Gefundene Probleme")
    severity: str = Field(..., description="Hoechster Schweregrad: error, warning, info")
    suggestions: List[str] = Field(default_factory=list, description="Korrekturvorschlaege")


@router.post(
    "/formulas/extract",
    response_model=FormulaExtractionResponse,
    summary="Formeln aus Text extrahieren",
    description="Extrahiert LaTeX-Formeln aus OCR-Text und parst diese.",
)
async def extract_formulas(
    request: FormulaExtractionRequest,
    current_user: User = Depends(get_current_active_user),
) -> FormulaExtractionResponse:
    """
    Extrahiert mathematische Formeln aus OCR-Text.

    Erkennt:
    - Inline-Formeln: $...$
    - Display-Formeln: $$...$$
    - equation-Umgebungen: \\begin{equation}...\\end{equation}

    Analysiert:
    - Formeltyp (Gleichung, Bruch, Summe, Integral, Matrix)
    - Kontext (finanziell, wissenschaftlich, statistisch)
    - Numerische Werte und Einheiten
    - Syntax-Validierung
    """
    logger.info(
        "formula_extraction_angefordert",
        user_id=str(current_user.id),
        text_length=len(request.text),
        include_mathml=request.include_mathml,
    )

    try:
        from app.services.ocr.formula_extraction_service import get_formula_extraction_service

        service = get_formula_extraction_service()

        # Formeln extrahieren
        results = service.extract_formulas(request.text)

        formeln: List[ExtractedFormulaResponse] = []
        for result in results:
            mathml = None
            if request.include_mathml:
                mathml = service.to_mathml(result.original)

            formeln.append(ExtractedFormulaResponse(
                original=result.original,
                formula_type=result.formula_type.value,
                context=result.context.value,
                is_valid=result.is_valid,
                confidence=result.confidence,
                extracted_values=[v.to_dict() for v in result.extracted_values],
                variables=list(result.variables),
                validation_issues=[i.to_dict() for i in result.validation_issues],
                mathml=mathml,
            ))

        logger.info(
            "formula_extraction_erfolgreich",
            user_id=str(current_user.id),
            formeln_gefunden=len(formeln),
        )

        return FormulaExtractionResponse(
            erfolg=True,
            formeln_gefunden=len(formeln),
            formeln=formeln,
            fehler=None,
        )

    except Exception as e:
        logger.exception(
            "formula_extraction_fehler",
            user_id=str(current_user.id),
            error=str(e),
        )
        return FormulaExtractionResponse(
            erfolg=False,
            formeln_gefunden=0,
            formeln=[],
            fehler="Formelextraktion fehlgeschlagen. Bitte erneut versuchen.",
        )


@router.post(
    "/formulas/parse",
    response_model=ExtractedFormulaResponse,
    summary="Einzelne Formel parsen",
    description="Parst und analysiert eine einzelne LaTeX-Formel.",
)
async def parse_formula(
    request: FormulaParsRequest,
    current_user: User = Depends(get_current_active_user),
) -> ExtractedFormulaResponse:
    """
    Parst eine einzelne LaTeX-Formel.

    Analysiert:
    - Formeltyp (Gleichung, Bruch, Summe, Integral, Matrix)
    - Kontext (finanziell, wissenschaftlich, statistisch)
    - Numerische Werte mit Einheiten
    - Variablen
    - Syntax-Validierung
    """
    logger.info(
        "formula_parse_angefordert",
        user_id=str(current_user.id),
        formula_length=len(request.formula),
    )

    try:
        from app.services.ocr.formula_extraction_service import get_formula_extraction_service

        service = get_formula_extraction_service()
        result = service.parse_formula(request.formula)
        mathml = service.to_mathml(request.formula)

        return ExtractedFormulaResponse(
            original=result.original,
            formula_type=result.formula_type.value,
            context=result.context.value,
            is_valid=result.is_valid,
            confidence=result.confidence,
            extracted_values=[v.to_dict() for v in result.extracted_values],
            variables=list(result.variables),
            validation_issues=[i.to_dict() for i in result.validation_issues],
            mathml=mathml,
        )

    except Exception as e:
        logger.exception(
            "formula_parse_fehler",
            user_id=str(current_user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formel konnte nicht geparst werden.",
        )


@router.post(
    "/formulas/validate",
    response_model=FormulaValidationResponse,
    summary="Formel-Syntax validieren",
    description="Validiert die Syntax einer LaTeX-Formel.",
)
async def validate_formula(
    request: FormulaValidationRequest,
    current_user: User = Depends(get_current_active_user),
) -> FormulaValidationResponse:
    """
    Validiert LaTeX-Formel-Syntax.

    Prueft:
    - Ausgeglichene Klammern
    - Bekannte LaTeX-Befehle
    - Typische OCR-Fehler (z.B. l statt f in \\frac)
    - Strukturelle Integritaet
    """
    logger.info(
        "formula_validate_angefordert",
        user_id=str(current_user.id),
        formula_length=len(request.formula),
    )

    try:
        from app.services.ocr.formula_extraction_service import get_formula_extraction_service

        service = get_formula_extraction_service()
        is_valid, issues = service.validate_formula(request.formula)

        # Hoechsten Schweregrad bestimmen
        severity = "info"
        for issue in issues:
            if issue.severity.value == "error":
                severity = "error"
                break
            elif issue.severity.value == "warning" and severity != "error":
                severity = "warning"

        # Korrekturvorschlaege generieren
        suggestions: List[str] = []
        for issue in issues:
            if "OCR" in issue.message:
                suggestions.append("Moeglicherweise OCR-Fehler - bitte Originaltext pruefen")
            if "Klammer" in issue.message:
                suggestions.append("Klammern pruefen und ergaenzen")
            if "Unbekannter LaTeX-Befehl" in issue.message:
                suggestions.append(f"Befehl pruefen: {issue.message}")

        return FormulaValidationResponse(
            is_valid=is_valid,
            issues=[i.to_dict() for i in issues],
            severity=severity,
            suggestions=list(set(suggestions)),  # Deduplizieren
        )

    except Exception as e:
        logger.exception(
            "formula_validate_fehler",
            user_id=str(current_user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formel-Validierung fehlgeschlagen.",
        )
