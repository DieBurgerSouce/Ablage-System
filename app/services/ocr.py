# -*- coding: utf-8 -*-
"""
OCR Service Utilities.

Provides quick OCR preview functionality for document classification.
"""

from typing import Optional
from pathlib import Path
import asyncio

import structlog

logger = structlog.get_logger(__name__)

# Optional imports for text extraction
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

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
        # PDF files - try embedded text extraction first (very fast)
        if suffix == ".pdf" and PYMUPDF_AVAILABLE:
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
    Extract text from PDF using PyMuPDF (fast, for embedded text).

    Args:
        file_path: Path to PDF file
        max_pages: Maximum pages to process
        max_chars: Maximum characters to extract

    Returns:
        Extracted text
    """
    if not PYMUPDF_AVAILABLE:
        logger.warning("pymupdf_not_available")
        return ""

    def _extract() -> str:
        text_parts = []
        try:
            doc = fitz.open(str(file_path))
            pages_to_process = min(len(doc), max_pages)

            for page_num in range(pages_to_process):
                page = doc[page_num]
                page_text = page.get_text("text")
                text_parts.append(page_text)

                # Early exit if we have enough text
                if sum(len(t) for t in text_parts) >= max_chars:
                    break

            doc.close()
        except Exception as e:
            logger.error("pdf_text_extraction_failed", error=str(e))
            return ""

        return "\n".join(text_parts).strip()

    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _extract)

    # If no embedded text found, try OCR on first page
    if not text.strip():
        logger.info("no_embedded_text_trying_ocr", file_path=str(file_path))
        text = await _ocr_pdf_first_page(file_path, max_chars)

    return text


async def _ocr_pdf_first_page(file_path: Path, max_chars: int) -> str:
    """
    OCR the first page of a PDF when no embedded text is available.

    Args:
        file_path: Path to PDF file
        max_chars: Maximum characters to extract

    Returns:
        OCR-extracted text
    """
    if not PYMUPDF_AVAILABLE or not PILLOW_AVAILABLE:
        return ""

    try:
        # Extract first page as image
        doc = fitz.open(str(file_path))
        if len(doc) == 0:
            doc.close()
            return ""

        page = doc[0]
        # Render at 150 DPI for balance between speed and quality
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()

        # Use Surya for OCR
        return await _ocr_image(img, max_chars)

    except Exception as e:
        logger.error("pdf_ocr_failed", error=str(e))
        return ""


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
    Perform OCR on a PIL Image using Surya (CPU mode for speed).

    Args:
        img: PIL Image object
        max_chars: Maximum characters to extract

    Returns:
        OCR-extracted text
    """
    try:
        # Import Surya components (lazy import to reduce startup time)
        from surya.recognition import RecognitionPredictor
        from surya.detection import DetectionPredictor
        from surya.foundation import FoundationPredictor
        from surya.common.surya.schema import TaskNames

        def _run_ocr() -> str:
            # Initialize predictors
            foundation = FoundationPredictor()
            det_predictor = DetectionPredictor()
            rec_predictor = RecognitionPredictor(foundation)

            # Detect text regions
            det_results = det_predictor([img])

            # Recognize text
            rec_results = rec_predictor(
                [img],
                det_results,
                TaskNames.ocr_with_boxes,
                langs=[["de", "en"]]  # German primary
            )

            # Extract text from results
            text_lines = []
            for result in rec_results:
                for line in result.text_lines:
                    text_lines.append(line.text)

            return " ".join(text_lines)

        # Run in thread pool
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _run_ocr)

        return text[:max_chars] if len(text) > max_chars else text

    except ImportError:
        logger.warning("surya_not_available_for_preview")
        return ""
    except Exception as e:
        logger.error("surya_ocr_failed", error=str(e))
        return ""
