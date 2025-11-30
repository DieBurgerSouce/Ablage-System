"""
Erweiterte Datei-Validierung für Sicherheit.

Schützt vor:
- PDF Decompression Bombs (übermäßig komprimierte Streams)
- Image Bombs (übermäßig große Pixel-Dimensionen)
- Übermäßige Seitenzahl in PDFs
- Malformed Files

Feinpoliert und durchdacht - Enterprise-grade File Validation.
"""

import io
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)

# ==================== Konfiguration ====================

# PDF Limits
MAX_PDF_PAGES = 500  # Maximale Seitenzahl
MAX_PDF_STREAM_RATIO = 100  # Max Dekomprimierungs-Verhältnis (100:1)
MAX_PDF_DECOMPRESSED_SIZE_MB = 500  # Max dekomprimierte Größe pro Stream

# Image Limits
MAX_IMAGE_PIXELS = 178956970  # ~13400x13400 (PIL Default)
MAX_IMAGE_WIDTH = 20000  # Maximale Breite in Pixeln
MAX_IMAGE_HEIGHT = 20000  # Maximale Höhe in Pixeln

# General Limits
MAX_FILE_SIZE_MB = 100  # Maximale Dateigröße


class FileValidationError(Exception):
    """Fehler bei der Datei-Validierung."""

    def __init__(self, message: str, user_message_de: str):
        super().__init__(message)
        self.user_message_de = user_message_de


class DecompressionBombError(FileValidationError):
    """Dekomprimierungs-Bombe erkannt."""

    def __init__(self, ratio: float):
        super().__init__(
            f"Decompression bomb detected: ratio {ratio:.1f}:1",
            f"Sicherheitswarnung: Datei hat ungewöhnlich hohe Komprimierung ({ratio:.0f}:1). "
            "Mögliche Dekompressions-Bombe."
        )
        self.ratio = ratio


class ImageBombError(FileValidationError):
    """Image-Bombe erkannt (übermäßige Pixel-Dimensionen)."""

    def __init__(self, width: int, height: int):
        super().__init__(
            f"Image bomb detected: {width}x{height} pixels",
            f"Sicherheitswarnung: Bild zu groß ({width}x{height} Pixel). "
            f"Maximum: {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}."
        )
        self.width = width
        self.height = height


class TooManyPagesError(FileValidationError):
    """Zu viele Seiten in PDF."""

    def __init__(self, page_count: int):
        super().__init__(
            f"PDF has too many pages: {page_count}",
            f"PDF hat zu viele Seiten ({page_count}). Maximum: {MAX_PDF_PAGES}."
        )
        self.page_count = page_count


# ==================== PDF Validierung ====================

def validate_pdf_security(
    content: bytes,
    filename: str = "document.pdf"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validiere PDF auf Sicherheitsrisiken.

    Prüft:
    - Seitenzahl
    - Komprimierungs-Verhältnis (Decompression Bomb)
    - Embedded JavaScript (Sicherheitsrisiko)

    Args:
        content: PDF-Inhalt als Bytes
        filename: Dateiname für Logging

    Returns:
        Tuple von (is_valid, error_message, metadata)
    """
    try:
        import pypdf
    except ImportError:
        logger.warning("pypdf_not_available", filename=filename)
        return True, "", {"warning": "pypdf nicht verfügbar für erweiterte Validierung"}

    metadata: Dict[str, Any] = {}

    try:
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))

        # 1. Seitenzahl prüfen
        page_count = len(pdf_reader.pages)
        metadata["page_count"] = page_count

        if page_count > MAX_PDF_PAGES:
            logger.warning(
                "pdf_too_many_pages",
                filename=filename,
                page_count=page_count,
                max_pages=MAX_PDF_PAGES
            )
            return False, f"PDF hat zu viele Seiten ({page_count}). Maximum: {MAX_PDF_PAGES}.", metadata

        # 2. JavaScript prüfen (Sicherheitsrisiko)
        if pdf_reader.metadata:
            # Check for JavaScript in document catalog
            if hasattr(pdf_reader, '_root_object'):
                root = pdf_reader._root_object
                if '/Names' in root and root['/Names']:
                    names = root['/Names']
                    if '/JavaScript' in names or '/JS' in names:
                        logger.warning(
                            "pdf_contains_javascript",
                            filename=filename
                        )
                        metadata["contains_javascript"] = True
                        # Warnung, aber nicht blockieren (OCR funktioniert trotzdem)

        # 3. Komprimierungs-Analyse (Sample erste 10 Seiten)
        total_compressed = len(content)
        estimated_decompressed = 0

        for i, page in enumerate(pdf_reader.pages[:10]):
            try:
                # Extrahiere Text um dekomprimierte Größe zu schätzen
                text = page.extract_text() or ""
                estimated_decompressed += len(text.encode('utf-8'))
            except Exception:
                pass

        if estimated_decompressed > 0 and total_compressed > 0:
            # Schätze Verhältnis basierend auf Sample
            sample_ratio = (estimated_decompressed * page_count / min(10, page_count)) / total_compressed

            if sample_ratio > MAX_PDF_STREAM_RATIO:
                logger.warning(
                    "pdf_high_compression_ratio",
                    filename=filename,
                    ratio=sample_ratio,
                    max_ratio=MAX_PDF_STREAM_RATIO
                )
                metadata["compression_ratio"] = sample_ratio
                return False, (
                    f"PDF hat ungewöhnlich hohe Komprimierung ({sample_ratio:.0f}:1). "
                    f"Mögliche Dekompressions-Bombe."
                ), metadata

        metadata["validation_passed"] = True
        logger.debug(
            "pdf_validation_passed",
            filename=filename,
            page_count=page_count
        )

        return True, "", metadata

    except Exception as e:
        logger.error(
            "pdf_validation_error",
            filename=filename,
            error=str(e)
        )
        return False, f"PDF-Validierung fehlgeschlagen: {str(e)}", metadata


# ==================== Image Validierung ====================

def validate_image_security(
    content: bytes,
    filename: str = "image.png"
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validiere Bild auf Sicherheitsrisiken.

    Prüft:
    - Pixel-Dimensionen (Image Bomb)
    - Tatsächliche Bildgröße vs. Header

    Args:
        content: Bild-Inhalt als Bytes
        filename: Dateiname für Logging

    Returns:
        Tuple von (is_valid, error_message, metadata)
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("pillow_not_available", filename=filename)
        return True, "", {"warning": "Pillow nicht verfügbar für erweiterte Validierung"}

    metadata: Dict[str, Any] = {}

    try:
        # PIL Decompression Bomb Schutz aktivieren
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
            metadata["width"] = width
            metadata["height"] = height
            metadata["format"] = img.format
            metadata["mode"] = img.mode

            # Dimensionen prüfen
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                logger.warning(
                    "image_too_large",
                    filename=filename,
                    width=width,
                    height=height,
                    max_width=MAX_IMAGE_WIDTH,
                    max_height=MAX_IMAGE_HEIGHT
                )
                return False, (
                    f"Bild zu groß ({width}x{height} Pixel). "
                    f"Maximum: {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}."
                ), metadata

            # Pixel-Count prüfen
            pixel_count = width * height
            metadata["pixel_count"] = pixel_count

            if pixel_count > MAX_IMAGE_PIXELS:
                logger.warning(
                    "image_too_many_pixels",
                    filename=filename,
                    pixel_count=pixel_count,
                    max_pixels=MAX_IMAGE_PIXELS
                )
                return False, (
                    f"Bild hat zu viele Pixel ({pixel_count:,}). "
                    f"Maximum: {MAX_IMAGE_PIXELS:,}."
                ), metadata

        metadata["validation_passed"] = True
        logger.debug(
            "image_validation_passed",
            filename=filename,
            width=width,
            height=height
        )

        return True, "", metadata

    except Image.DecompressionBombError as e:
        logger.warning(
            "image_decompression_bomb",
            filename=filename,
            error=str(e)
        )
        return False, "Sicherheitswarnung: Mögliche Bild-Dekompressions-Bombe erkannt.", metadata

    except Exception as e:
        logger.error(
            "image_validation_error",
            filename=filename,
            error=str(e)
        )
        return False, f"Bild-Validierung fehlgeschlagen: {str(e)}", metadata


# ==================== Kombinierte Validierung ====================

def validate_file_security(
    content: bytes,
    filename: str,
    mime_type: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Kombinierte Sicherheits-Validierung für alle Dateitypen.

    Args:
        content: Datei-Inhalt als Bytes
        filename: Dateiname
        mime_type: Optional erkannter MIME-Type

    Returns:
        Tuple von (is_valid, error_message, metadata)
    """
    file_ext = Path(filename).suffix.lower()
    metadata: Dict[str, Any] = {
        "filename": filename,
        "size_bytes": len(content),
        "mime_type": mime_type
    }

    # Grundlegende Größenprüfung
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return False, (
            f"Datei zu groß ({size_mb:.1f} MB). "
            f"Maximum: {MAX_FILE_SIZE_MB} MB."
        ), metadata

    # Typ-spezifische Validierung
    if file_ext == ".pdf" or mime_type == "application/pdf":
        return validate_pdf_security(content, filename)

    elif file_ext in [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"] or \
         (mime_type and mime_type.startswith("image/")):
        return validate_image_security(content, filename)

    # Andere Dateitypen: Nur Basisvalidierung
    metadata["validation_passed"] = True
    return True, "", metadata


# ==================== Synchrone Wrapper ====================

def validate_upload_file(
    content: bytes,
    filename: str,
    mime_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validiere Upload-Datei und gebe strukturiertes Ergebnis zurück.

    Args:
        content: Datei-Inhalt
        filename: Dateiname
        mime_type: MIME-Type

    Returns:
        Dict mit Validierungsergebnis

    Raises:
        FileValidationError: Bei Sicherheitsproblemen
    """
    is_valid, error_msg, metadata = validate_file_security(content, filename, mime_type)

    if not is_valid:
        logger.warning(
            "file_validation_failed",
            filename=filename,
            error=error_msg,
            metadata=metadata
        )
        raise FileValidationError(error_msg, error_msg)

    logger.info(
        "file_validation_passed",
        filename=filename,
        size_bytes=len(content),
        mime_type=mime_type
    )

    return metadata
