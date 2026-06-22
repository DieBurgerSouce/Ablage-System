# -*- coding: utf-8 -*-
"""
OCR Service Utilities.

Provides quick OCR preview functionality for document classification.
Uses pypdfium2 for PDF rendering and Tesseract for OCR.
"""

from typing import Optional
from pathlib import Path
import asyncio

import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Check available libraries
try:
    import pypdfium2 as pdfium
    PDFIUM_AVAILABLE = True
except ImportError:
    PDFIUM_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


# DoS-Haertung (2026-06-22): quick_ocr_preview verarbeitet HOCHGELADENE (potenziell
# boesartige/gefuzzte) Dateien im Threadpool. Ohne Schranken kann ein malformed
# File Tesseract/pdfium/PIL in einen Endlos-/Riesen-Spin treiben -> Backend-CPU-
# Spin, Request haengt ~unbegrenzt (async-Loop bleibt frei, daher /health ok).
# Ein endlos-spinnender Python-Thread ist nicht von aussen stoppbar -> die Arbeit
# selbst MUSS beschraenkt werden: Tesseract via eingebautem `timeout=` (killt den
# Tesseract-Subprozess), Renderskalierung + Bildgroesse via Pixel-Caps, Dateien
# via Groessen-Guard. Konfigurierbar per ENV.
import os as _os

OCR_PREVIEW_TIMEOUT_SECONDS = int(_os.getenv("OCR_PREVIEW_TIMEOUT_SECONDS", "30"))
OCR_MAX_FILE_BYTES = int(_os.getenv("OCR_MAX_FILE_BYTES", str(50 * 1024 * 1024)))
OCR_MAX_IMAGE_PIXELS = int(_os.getenv("OCR_MAX_IMAGE_PIXELS", str(40_000_000)))
OCR_MAX_RENDER_PIXELS = int(_os.getenv("OCR_MAX_RENDER_PIXELS", str(25_000_000)))


async def quick_ocr_preview(
    file_path: Path,
    max_pages: int = 1,
    max_chars: int = 1000
) -> str:
    """
    Extract a quick text preview from a document for classification.

    Uses lightweight text extraction methods:
    1. For PDFs: Try to extract embedded text first (fast)
    2. For images or PDFs without text: Use OCR as fallback

    Args:
        file_path: Path to the document
        max_pages: Maximum number of pages to extract
        max_chars: Maximum number of characters to return

    Returns:
        Extracted text preview (may be empty if extraction fails)
    """
    logger.info(
        "quick_ocr_preview_start",
        file_path=str(file_path),
        max_pages=max_pages,
        max_chars=max_chars
    )

    if not file_path.exists():
        logger.warning("file_not_found", file_path=str(file_path))
        return ""

    # DoS-Haertung: uebergrosse Dateien gar nicht erst in den OCR-Pfad lassen.
    try:
        _size = file_path.stat().st_size
        if _size > OCR_MAX_FILE_BYTES:
            logger.warning(
                "ocr_preview_file_too_large",
                file_path=str(file_path),
                size=_size,
                cap=OCR_MAX_FILE_BYTES,
            )
            return ""
    except OSError as e:
        logger.warning("ocr_preview_stat_failed", **safe_error_log(e))
        return ""

    text = ""
    suffix = file_path.suffix.lower()

    try:
        # PDF files
        if suffix == ".pdf":
            text = await _extract_pdf_text(file_path, max_pages, max_chars)

        # Image files - use OCR
        elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
            text = await _extract_image_text(file_path, max_chars)

        # Unsupported format
        else:
            logger.warning(
                "unsupported_format_for_preview",
                file_path=str(file_path),
                suffix=suffix
            )
            return ""

    except Exception as e:
        logger.error(
            "quick_ocr_preview_failed",
            file_path=str(file_path),
            **safe_error_log(e)
        )
        return ""

    # Truncate if needed
    if len(text) > max_chars:
        text = text[:max_chars]

    logger.info(
        "quick_ocr_preview_complete",
        file_path=str(file_path),
        extracted_chars=len(text)
    )

    return text


async def _extract_pdf_text(
    file_path: Path,
    max_pages: int,
    max_chars: int
) -> str:
    """
    Extract text from PDF - try embedded text first, then OCR.

    Args:
        file_path: Path to PDF file
        max_pages: Maximum pages to process
        max_chars: Maximum characters to extract

    Returns:
        Extracted text
    """
    # First try: Extract embedded text with pdfplumber (fast)
    if PDFPLUMBER_AVAILABLE:
        def _extract_with_pdfplumber() -> str:
            text_parts = []
            try:
                with pdfplumber.open(str(file_path)) as pdf:
                    pages_to_process = min(len(pdf.pages), max_pages)
                    for i in range(pages_to_process):
                        page_text = pdf.pages[i].extract_text() or ""
                        text_parts.append(page_text)
                        if sum(len(t) for t in text_parts) >= max_chars:
                            break
            except Exception as e:
                logger.warning("pdfplumber_extraction_failed", **safe_error_log(e))
                return ""
            return "\n".join(text_parts).strip()

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _extract_with_pdfplumber)

        if text and len(text.strip()) > 50:
            logger.info("pdf_embedded_text_found", chars=len(text))
            return text

    # Second try: OCR with pypdfium2 + Tesseract
    logger.info("no_embedded_text_trying_ocr", file_path=str(file_path))
    return await _ocr_pdf_first_page(file_path, max_chars)


async def _ocr_pdf_first_page(file_path: Path, max_chars: int) -> str:
    """
    OCR the first page of a PDF using pypdfium2 + Tesseract.

    Args:
        file_path: Path to PDF file
        max_chars: Maximum characters to extract

    Returns:
        OCR-extracted text
    """
    if not PDFIUM_AVAILABLE or not PILLOW_AVAILABLE:
        logger.warning(
            "pdf_ocr_missing_deps",
            pdfium=PDFIUM_AVAILABLE,
            pillow=PILLOW_AVAILABLE
        )
        return ""

    def _render_and_ocr() -> str:
        try:
            import pytesseract

            # Open PDF with pypdfium2
            pdf = pdfium.PdfDocument(str(file_path))
            if len(pdf) == 0:
                return ""

            # Render first page at 150 DPI
            page = pdf[0]
            # scale = DPI / 72 (PDF default is 72 DPI)
            scale = 150 / 72
            # DoS-Haertung: bei pathologisch grosser Seite (malformed MediaBox)
            # die Skalierung kappen, damit die Bitmap OCR_MAX_RENDER_PIXELS nicht
            # uebersteigt (sonst Riesen-Allokation / CPU-Spin beim Render/OCR).
            try:
                pw, ph = page.get_size()
                if pw > 0 and ph > 0 and (pw * scale) * (ph * scale) > OCR_MAX_RENDER_PIXELS:
                    import math
                    scale = math.sqrt(OCR_MAX_RENDER_PIXELS / (pw * ph))
                    logger.warning(
                        "ocr_render_scale_capped",
                        page_w=pw, page_h=ph, capped_scale=round(scale, 4)
                    )
            except Exception as _e:
                logger.warning("ocr_render_size_check_failed", **safe_error_log(_e))
            bitmap = page.render(scale=scale)

            # Convert to PIL Image
            img = bitmap.to_pil()

            # OCR with Tesseract (timeout kappt den Tesseract-Subprozess bei
            # pathologischen Bildern -> kein unbegrenzter Spin)
            text = pytesseract.image_to_string(
                img, lang='deu+eng', timeout=OCR_PREVIEW_TIMEOUT_SECONDS
            )

            logger.info(
                "pdf_ocr_success",
                file_path=str(file_path),
                chars=len(text)
            )
            return text.strip()

        except ImportError:
            logger.warning("tesseract_not_available")
            return ""
        except Exception as e:
            logger.error("pdf_ocr_failed", **safe_error_log(e))
            return ""

    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _render_and_ocr)

    return text[:max_chars] if len(text) > max_chars else text


async def _extract_image_text(file_path: Path, max_chars: int) -> str:
    """
    Extract text from image using OCR.

    Args:
        file_path: Path to image file
        max_chars: Maximum characters to extract

    Returns:
        OCR-extracted text
    """
    if not PILLOW_AVAILABLE:
        logger.warning("pillow_not_available")
        return ""

    try:
        img = Image.open(str(file_path))
        # DoS-Haertung: Decompression-Bomb / Riesenbild abfangen, BEVOR Tesseract
        # darauf laeuft (img.size liest nur den Header, dekodiert nicht voll).
        w, h = img.size
        if w * h > OCR_MAX_IMAGE_PIXELS:
            logger.warning(
                "ocr_image_too_large",
                width=w, height=h, pixels=w * h, cap=OCR_MAX_IMAGE_PIXELS,
            )
            return ""
        return await _ocr_image(img, max_chars)
    except Exception as e:
        logger.error("image_ocr_failed", **safe_error_log(e))
        return ""


async def _ocr_image(img: "Image.Image", max_chars: int) -> str:
    """
    Perform OCR on a PIL Image using Tesseract (CPU-friendly).

    Uses Tesseract instead of Surya because:
    - Tesseract works on CPU (backend container has no GPU)
    - Fast enough for quick preview extraction
    - German language pack (deu) available

    Args:
        img: PIL Image object
        max_chars: Maximum characters to extract

    Returns:
        OCR-extracted text
    """
    try:
        import pytesseract


        def _run_ocr() -> str:
            # German + English; timeout kappt Tesseract bei pathologischen Bildern
            text = pytesseract.image_to_string(
                img, lang='deu+eng', timeout=OCR_PREVIEW_TIMEOUT_SECONDS
            )
            return text.strip()

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _run_ocr)

        return text[:max_chars] if len(text) > max_chars else text

    except ImportError:
        logger.warning("tesseract_not_available_for_preview")
        return ""
    except Exception as e:
        logger.error("tesseract_ocr_failed", **safe_error_log(e))
        return ""
