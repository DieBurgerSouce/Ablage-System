# -*- coding: utf-8 -*-
"""
OCR Service Utilities.

Provides quick OCR preview functionality for document classification.
"""

from typing import Optional
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


async def quick_ocr_preview(
    file_path: Path,
    max_pages: int = 1,
    max_chars: int = 1000
) -> str:
    """
    Extract a quick text preview from a document for classification.

    Uses lightweight OCR to get a text sample without full processing.

    Args:
        file_path: Path to the document
        max_pages: Maximum number of pages to extract
        max_chars: Maximum number of characters to return

    Returns:
        Extracted text preview
    """
    logger.info(
        "quick_ocr_preview",
        file_path=str(file_path),
        max_pages=max_pages,
        max_chars=max_chars
    )

    # For now, return empty string - actual OCR implementation would go here
    # This is a stub for the Execution_Layer.Agents.document_classifier_agent
    return ""
