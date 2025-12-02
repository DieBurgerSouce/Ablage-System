# -*- coding: utf-8 -*-
"""
API-Endpunkte fuer OCR-Operationen.

Bietet schnelle OCR-Vorschau fuer Dokument-Klassifikation
und Text-Extraktion ohne vollstaendige Verarbeitung.

Feinpoliert und durchdacht - Enterprise OCR API.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
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
    max_seiten: int = Field(1, ge=1, le=5, description="Max. Seiten zu extrahieren")
    max_zeichen: int = Field(1000, ge=100, le=10000, description="Max. Zeichen")


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
    max_seiten: int = Query(1, ge=1, le=5, description="Max. Seiten"),
    max_zeichen: int = Query(1000, ge=100, le=10000, description="Max. Zeichen"),
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
        max_seiten=max_seiten,
        max_zeichen=max_zeichen,
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
            max_pages=max_seiten,
            max_chars=max_zeichen,
        )

        # Methode bestimmen
        if suffix == ".pdf":
            methode = "pdf_embedded_text"
        else:
            methode = "tesseract_ocr"

        abgeschnitten = len(text) >= max_zeichen

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
        return OCRPreviewResponse(
            erfolg=False,
            text="",
            zeichen_anzahl=0,
            abgeschnitten=False,
            dateiname=file.filename,
            methode="fehler",
            fehler=str(e),
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
        max_seiten=request.max_seiten,
        max_zeichen=request.max_zeichen,
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
            max_pages=request.max_seiten,
            max_chars=request.max_zeichen,
        )

        # Methode bestimmen
        suffix = Path(document.original_filename or "").suffix.lower()
        if suffix == ".pdf":
            methode = "pdf_embedded_text"
        else:
            methode = "tesseract_ocr"

        abgeschnitten = len(text) >= request.max_zeichen

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
        return OCRPreviewResponse(
            erfolg=False,
            text="",
            zeichen_anzahl=0,
            abgeschnitten=False,
            dateiname=None,
            methode="fehler",
            fehler=str(e),
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
        logger.error(
            "ocr_start_failed",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Starten der OCR-Verarbeitung: {str(e)}"
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
        logger.error(
            "ocr_cancel_failed",
            document_id=str(document_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Abbrechen: {str(e)}"
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
        logger.error("cache_invalidation_error", document_id=str(document_id), error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Cache-Invalidierung fehlgeschlagen: {str(e)}"
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
