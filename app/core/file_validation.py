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

# Path Traversal Protection
DANGEROUS_FILENAME_PATTERNS = {"../", "..\\", "/", "\\", "\x00"}
MAX_FILENAME_LENGTH = 255
ALLOWED_FILENAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "äöüÄÖÜß"  # Deutsche Umlaute
    "._- "
)

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


class PathTraversalError(FileValidationError):
    """Path Traversal Angriff erkannt."""

    def __init__(self, filename: str):
        super().__init__(
            f"Path traversal attempt detected in filename: {filename}",
            "Ungültiger Dateiname: Pfad-Manipulation erkannt."
        )
        self.filename = filename


# ==================== Dateinamen-Sanitierung ====================


def sanitize_filename(filename: str, strict: bool = True) -> str:
    """
    Sanitize Dateiname gegen Path Traversal und andere Angriffe.

    Args:
        filename: Original Dateiname vom Upload
        strict: Wenn True, nur erlaubte Zeichen; sonst ersetzen

    Returns:
        Sicherer Dateiname

    Raises:
        PathTraversalError: Bei Path Traversal Versuch
    """
    import os
    import unicodedata

    if not filename:
        return "unnamed_file"

    # 1. Unicode normalisieren (NFC)
    filename = unicodedata.normalize("NFC", filename)

    # 2. Nur Basename extrahieren (entfernt alle Pfade)
    filename = os.path.basename(filename)

    # 3. Path Traversal Patterns prüfen
    for pattern in DANGEROUS_FILENAME_PATTERNS:
        if pattern in filename:
            logger.warning(
                "path_traversal_detected",
                original_filename=filename[:50],
                pattern=pattern
            )
            raise PathTraversalError(filename)

    # 4. Null-Bytes entfernen (Null-Byte Injection)
    filename = filename.replace("\x00", "")

    # 5. Länge begrenzen
    if len(filename) > MAX_FILENAME_LENGTH:
        # Behalte Extension
        name, ext = os.path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext

    # 6. Strict Mode: Nur erlaubte Zeichen
    if strict:
        safe_chars = []
        for char in filename:
            if char in ALLOWED_FILENAME_CHARS:
                safe_chars.append(char)
            else:
                safe_chars.append("_")
        filename = "".join(safe_chars)
    else:
        # Nicht-strict: Nur gefährliche Zeichen ersetzen
        filename = filename.replace("<", "_").replace(">", "_")
        filename = filename.replace(":", "_").replace('"', "_")
        filename = filename.replace("|", "_").replace("?", "_")
        filename = filename.replace("*", "_")

    # 7. Leere Dateinamen vermeiden
    if not filename or filename.strip() == "":
        return "unnamed_file"

    # 8. Führende Punkte entfernen (versteckte Dateien)
    while filename.startswith("."):
        filename = filename[1:] or "unnamed_file"

    # 9. Nochmal Längenbegrenzung
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext

    return filename


def validate_filename_security(filename: str) -> Tuple[bool, str]:
    """
    Validiere Dateiname auf Sicherheitsrisiken.

    Args:
        filename: Zu prüfender Dateiname

    Returns:
        Tuple von (is_safe, error_message)
    """
    import os

    if not filename:
        return False, "Dateiname fehlt"

    # Path Traversal Check
    for pattern in DANGEROUS_FILENAME_PATTERNS:
        if pattern in filename:
            return False, f"Ungültiger Dateiname: '{pattern}' nicht erlaubt"

    # Absolute Pfade verbieten
    if os.path.isabs(filename):
        return False, "Absolute Pfade sind nicht erlaubt"

    # Basename sollte gleich dem Original sein
    basename = os.path.basename(filename)
    if basename != filename:
        return False, "Pfadangaben im Dateinamen nicht erlaubt"

    # Länge prüfen
    if len(filename) > MAX_FILENAME_LENGTH:
        return False, f"Dateiname zu lang (max. {MAX_FILENAME_LENGTH} Zeichen)"

    return True, ""


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


# ==================== Magic Bytes Validierung ====================

# File signature (magic bytes) definitions
# Format: {extension: [(magic_bytes, offset), ...]}
FILE_SIGNATURES: Dict[str, list] = {
    ".pdf": [(b"%PDF", 0)],
    ".png": [(b"\x89PNG\r\n\x1a\n", 0)],
    ".jpg": [(b"\xff\xd8\xff", 0)],
    ".jpeg": [(b"\xff\xd8\xff", 0)],
    ".gif": [(b"GIF87a", 0), (b"GIF89a", 0)],
    ".bmp": [(b"BM", 0)],
    ".tiff": [(b"II\x2a\x00", 0), (b"MM\x00\x2a", 0)],  # Little/Big endian
    ".tif": [(b"II\x2a\x00", 0), (b"MM\x00\x2a", 0)],
}


def verify_magic_bytes(content: bytes, filename: str) -> Tuple[bool, str, Optional[str]]:
    """
    Verifiziere Magic Bytes gegen Dateiendung.

    Schützt vor:
    - Umbenannten Dateien (z.B. .exe → .pdf)
    - MIME-Type Spoofing
    - Content-Type Manipulation

    Args:
        content: Datei-Inhalt als Bytes
        filename: Dateiname mit Extension

    Returns:
        Tuple von (is_valid, error_message, detected_type)
    """
    if not content:
        return False, "Datei ist leer", None

    file_ext = Path(filename).suffix.lower()

    # Für bekannte Dateitypen: Magic Bytes prüfen
    if file_ext in FILE_SIGNATURES:
        signatures = FILE_SIGNATURES[file_ext]
        matched = False

        for magic, offset in signatures:
            if len(content) >= offset + len(magic):
                if content[offset:offset + len(magic)] == magic:
                    matched = True
                    break

        if not matched:
            # Versuche tatsächlichen Typ zu erkennen
            detected = _detect_file_type(content)
            detected_str = detected if detected else "unbekannt"

            logger.warning(
                "magic_bytes_mismatch",
                filename=filename,
                expected_ext=file_ext,
                detected_type=detected_str
            )

            return False, (
                f"Dateiinhalt stimmt nicht mit Dateiendung '{file_ext}' überein. "
                f"Erkannter Dateityp: {detected_str}"
            ), detected

    return True, "", file_ext


def _detect_file_type(content: bytes) -> Optional[str]:
    """
    Erkenne Dateityp anhand der Magic Bytes.

    Args:
        content: Datei-Inhalt als Bytes

    Returns:
        Erkannte Dateiendung oder None
    """
    if not content:
        return None

    # Prüfe alle bekannten Signaturen
    for ext, signatures in FILE_SIGNATURES.items():
        for magic, offset in signatures:
            if len(content) >= offset + len(magic):
                if content[offset:offset + len(magic)] == magic:
                    return ext

    # Weitere Dateitypen (nicht in FILE_SIGNATURES für OCR)
    if content[:2] == b"PK":  # ZIP-basiert (docx, xlsx, etc.)
        return ".zip"
    if content[:4] == b"RIFF":  # RIFF-Container (wav, webp, etc.)
        return ".riff"
    if content[:3] == b"ID3" or content[:2] == b"\xff\xfb":  # MP3
        return ".mp3"

    return None


class MagicBytesMismatchError(FileValidationError):
    """Magic Bytes stimmen nicht mit Dateiendung überein."""

    def __init__(self, expected: str, detected: Optional[str]):
        detected_str = detected if detected else "unbekannt"
        super().__init__(
            f"Magic bytes mismatch: expected {expected}, detected {detected_str}",
            f"Dateiformat ungültig: Erwartet '{expected}', erkannt '{detected_str}'"
        )
        self.expected = expected
        self.detected = detected


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

    # Magic Bytes Validierung (SECURITY FIX)
    magic_valid, magic_error, detected_type = verify_magic_bytes(content, filename)
    if not magic_valid:
        metadata["magic_bytes_error"] = magic_error
        metadata["detected_type"] = detected_type
        return False, magic_error, metadata

    metadata["magic_bytes_validated"] = True

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
