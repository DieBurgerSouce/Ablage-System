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
            error=str(e)
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
                logger.warning("pdfplumber_extraction_failed", error=str(e))
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
            bitmap = page.render(scale=scale)

            # Convert to PIL Image
            img = bitmap.to_pil()

            # OCR with Tesseract
            text = pytesseract.image_to_string(img, lang='deu+eng')

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
            logger.error("pdf_ocr_failed", error=str(e))
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
        return await _ocr_image(img, max_chars)
    except Exception as e:
        logger.error("image_ocr_failed", error=str(e))
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
            # German + English for best results on German documents
            text = pytesseract.image_to_string(img, lang='deu+eng')
            return text.strip()

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _run_ocr)

        return text[:max_chars] if len(text) > max_chars else text

    except ImportError:
        logger.warning("tesseract_not_available_for_preview")
        return ""
    except Exception as e:
        logger.error("tesseract_ocr_failed", error=str(e))
        return ""
