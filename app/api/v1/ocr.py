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

    suffix = Path(file.filename).suffix.lower()
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
            except Exception:
                pass


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
            except Exception:
                pass


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
    except Exception:
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
        from app.agents.ocr.deepseek_backend import DeepseekBackend

        deepseek = DeepseekBackend()
        backends["deepseek"] = {
            "verfuegbar": deepseek.is_available(),
            "beschreibung": "GPU-OCR (beste Qualitaet)",
            "gpu_erforderlich": True,
        }
    except Exception:
        backends["deepseek"] = {
            "verfuegbar": False,
            "beschreibung": "GPU-OCR (nicht geladen)",
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
