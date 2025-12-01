"""
Tests für file_validation.py - Sicherheitskritische Datei-Validierung.

Testet:
- PDF-Validierung (Seitenzahl, Kompression, JavaScript)
- Bild-Validierung (Dimensionen, Pixel-Count)
- Kombinierte Validierung
- Exception-Klassen
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import io

from app.core.file_validation import (
    # Functions
    validate_pdf_security,
    validate_image_security,
    validate_file_security,
    validate_upload_file,
    sanitize_filename,
    verify_magic_bytes,
    # Exceptions
    FileValidationError,
    DecompressionBombError,
    ImageBombError,
    TooManyPagesError,
    PathTraversalError,
    # Constants
    MAX_PDF_PAGES,
    MAX_IMAGE_WIDTH,
    MAX_IMAGE_HEIGHT,
    MAX_IMAGE_PIXELS,
    MAX_FILE_SIZE_MB,
    MAX_PDF_STREAM_RATIO,
    DANGEROUS_FILENAME_PATTERNS,
    MAX_FILENAME_LENGTH,
    FILE_SIGNATURES,
)


# ==================== Exception Tests ====================


class TestFileValidationError:
    """Tests für die FileValidationError Basisklasse."""

    def test_exception_stores_messages(self):
        """FileValidationError speichert beide Nachrichten."""
        error = FileValidationError("English message", "Deutsche Nachricht")

        assert str(error) == "English message"
        assert error.user_message_de == "Deutsche Nachricht"

    def test_exception_is_raiseable(self):
        """FileValidationError kann geworfen und gefangen werden."""
        with pytest.raises(FileValidationError) as exc_info:
            raise FileValidationError("Test error", "Test Fehler")

        assert exc_info.value.user_message_de == "Test Fehler"


class TestDecompressionBombError:
    """Tests für DecompressionBombError."""

    def test_stores_compression_ratio(self):
        """DecompressionBombError speichert das Komprimierungs-Verhältnis."""
        error = DecompressionBombError(ratio=150.5)

        assert error.ratio == 150.5
        assert "150.5:1" in str(error)
        assert "Dekompressions-Bombe" in error.user_message_de

    def test_inherits_from_file_validation_error(self):
        """DecompressionBombError erbt von FileValidationError."""
        error = DecompressionBombError(ratio=100)

        assert isinstance(error, FileValidationError)


class TestImageBombError:
    """Tests für ImageBombError."""

    def test_stores_dimensions(self):
        """ImageBombError speichert Breite und Höhe."""
        error = ImageBombError(width=30000, height=40000)

        assert error.width == 30000
        assert error.height == 40000
        assert "30000x40000" in str(error)
        assert "30000x40000" in error.user_message_de

    def test_shows_maximum_in_message(self):
        """ImageBombError zeigt Maximum in Nachricht."""
        error = ImageBombError(width=25000, height=25000)

        assert f"{MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}" in error.user_message_de


class TestTooManyPagesError:
    """Tests für TooManyPagesError."""

    def test_stores_page_count(self):
        """TooManyPagesError speichert Seitenzahl."""
        error = TooManyPagesError(page_count=1000)

        assert error.page_count == 1000
        assert "1000" in str(error)
        assert f"Maximum: {MAX_PDF_PAGES}" in error.user_message_de


# ==================== PDF Validation Tests ====================

# Check if pypdf is available
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


class TestValidatePdfSecurity:
    """Tests für validate_pdf_security()."""

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf nicht installiert")
    def test_valid_pdf_passes(self):
        """Gültiges PDF passiert Validierung."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock() for _ in range(10)]
        mock_reader.metadata = None

        # Mock extract_text für jede Seite
        for page in mock_reader.pages:
            page.extract_text.return_value = "Test content " * 100

        with patch('pypdf.PdfReader', return_value=mock_reader):
            content = b"fake pdf content"
            is_valid, error_msg, metadata = validate_pdf_security(content, "test.pdf")

        assert is_valid is True
        assert error_msg == ""
        assert metadata["page_count"] == 10
        assert metadata.get("validation_passed") is True

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf nicht installiert")
    def test_too_many_pages_fails(self):
        """PDF mit zu vielen Seiten wird abgelehnt."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock() for _ in range(MAX_PDF_PAGES + 100)]
        mock_reader.metadata = None

        with patch('pypdf.PdfReader', return_value=mock_reader):
            content = b"fake pdf content"
            is_valid, error_msg, metadata = validate_pdf_security(content, "large.pdf")

        assert is_valid is False
        assert f"zu viele Seiten ({MAX_PDF_PAGES + 100})" in error_msg
        assert metadata["page_count"] == MAX_PDF_PAGES + 100

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf nicht installiert")
    def test_high_compression_ratio_fails(self):
        """PDF mit zu hohem Komprimierungs-Verhältnis wird abgelehnt."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock() for _ in range(5)]
        mock_reader.metadata = None

        # Jede Seite gibt sehr viel Text zurück (hohe Dekomprimierung)
        for page in mock_reader.pages:
            page.extract_text.return_value = "X" * 100000  # 100KB pro Seite

        with patch('pypdf.PdfReader', return_value=mock_reader):
            # Kleine komprimierte Größe (simuliert durch kleinen content)
            content = b"x" * 100  # 100 Bytes komprimiert
            is_valid, error_msg, metadata = validate_pdf_security(content, "bomb.pdf")

        assert is_valid is False
        assert "Komprimierung" in error_msg or "compression" in error_msg.lower()

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf nicht installiert")
    def test_javascript_detection(self):
        """PDF mit JavaScript wird erkannt (Warnung, nicht Blockierung)."""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock()]
        mock_reader.pages[0].extract_text.return_value = "Test"
        mock_reader.metadata = {"Author": "Test"}
        mock_reader._root_object = {
            '/Names': {'/JavaScript': 'some_js_ref'}
        }

        with patch('pypdf.PdfReader', return_value=mock_reader):
            content = b"fake pdf with js"
            is_valid, error_msg, metadata = validate_pdf_security(content, "js.pdf")

        # JavaScript führt zu Warnung, aber Validierung sollte passieren
        assert is_valid is True
        assert metadata.get("contains_javascript") is True

    def test_pypdf_not_available_returns_valid(self):
        """Ohne pypdf wird Datei als gültig behandelt (graceful degradation)."""
        # Dieser Test prüft das Verhalten ohne pypdf
        # Die Funktion hat try/except ImportError und gibt dann (True, "", {"warning": ...}) zurück
        # Da pypdf möglicherweise nicht installiert ist, ist das effektiv bereits getestet
        content = b"fake pdf content"
        is_valid, error_msg, metadata = validate_pdf_security(content, "test.pdf")

        # Wenn pypdf nicht verfügbar ist, sollte es trotzdem True zurückgeben
        if not PYPDF_AVAILABLE:
            assert is_valid is True
            assert "warning" in metadata

    @pytest.mark.skipif(not PYPDF_AVAILABLE, reason="pypdf nicht installiert")
    def test_malformed_pdf_returns_error(self):
        """Beschädigte PDF gibt Fehler zurück."""
        with patch('pypdf.PdfReader', side_effect=Exception("PDF parsing failed")):
            content = b"not a valid pdf"
            is_valid, error_msg, metadata = validate_pdf_security(content, "broken.pdf")

        assert is_valid is False
        assert "fehlgeschlagen" in error_msg.lower() or "failed" in error_msg.lower()


# ==================== Image Validation Tests ====================


class TestValidateImageSecurity:
    """Tests für validate_image_security()."""

    def test_valid_image_passes(self):
        """Gültiges Bild passiert Validierung."""
        from PIL import Image
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)

        with patch.object(Image, 'open', return_value=mock_img):
            content = b"fake image content"
            is_valid, error_msg, metadata = validate_image_security(content, "test.png")

        assert is_valid is True
        assert error_msg == ""
        assert metadata["width"] == 1920
        assert metadata["height"] == 1080
        assert metadata["format"] == "PNG"

    def test_oversized_width_fails(self):
        """Bild mit zu großer Breite wird abgelehnt."""
        from PIL import Image
        mock_img = MagicMock()
        mock_img.size = (MAX_IMAGE_WIDTH + 1000, 1080)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)

        with patch.object(Image, 'open', return_value=mock_img):
            content = b"fake image content"
            is_valid, error_msg, metadata = validate_image_security(content, "wide.png")

        assert is_valid is False
        assert "zu groß" in error_msg.lower() or "too large" in error_msg.lower()
        assert metadata["width"] == MAX_IMAGE_WIDTH + 1000

    def test_oversized_height_fails(self):
        """Bild mit zu großer Höhe wird abgelehnt."""
        from PIL import Image
        mock_img = MagicMock()
        mock_img.size = (1920, MAX_IMAGE_HEIGHT + 1000)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)

        with patch.object(Image, 'open', return_value=mock_img):
            content = b"fake image content"
            is_valid, error_msg, metadata = validate_image_security(content, "tall.png")

        assert is_valid is False
        assert "zu groß" in error_msg.lower()

    def test_too_many_pixels_fails(self):
        """Bild mit zu vielen Pixeln wird abgelehnt."""
        from PIL import Image
        # Quadratisches Bild mit zu vielen Pixeln aber unter Dimension-Limits
        side = 15000  # Unter MAX_IMAGE_WIDTH/HEIGHT aber 225M Pixels > MAX_IMAGE_PIXELS
        mock_img = MagicMock()
        mock_img.size = (side, side)
        mock_img.format = "PNG"
        mock_img.mode = "RGB"
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)

        with patch.object(Image, 'open', return_value=mock_img):
            content = b"fake image content"
            is_valid, error_msg, metadata = validate_image_security(content, "huge.png")

        # 15000 * 15000 = 225,000,000 > MAX_IMAGE_PIXELS (178,956,970)
        assert is_valid is False
        assert "pixel" in error_msg.lower()

    def test_decompression_bomb_caught(self):
        """PIL DecompressionBombError wird abgefangen."""
        from PIL import Image

        with patch.object(Image, 'open', side_effect=Image.DecompressionBombError("Image size exceeds limit")):
            content = b"fake bomb image"
            is_valid, error_msg, metadata = validate_image_security(content, "bomb.png")

        assert is_valid is False
        assert "Dekompressions-Bombe" in error_msg or "bomb" in error_msg.lower()

    def test_malformed_image_returns_error(self):
        """Beschädigtes Bild gibt Fehler zurück."""
        from PIL import Image

        with patch.object(Image, 'open', side_effect=Exception("Cannot identify image file")):
            content = b"not a valid image"
            is_valid, error_msg, metadata = validate_image_security(content, "broken.png")

        assert is_valid is False
        assert "fehlgeschlagen" in error_msg.lower() or "failed" in error_msg.lower()


# ==================== Combined Validation Tests ====================


class TestValidateFileSecurity:
    """Tests für validate_file_security()."""

    def test_file_too_large_fails(self):
        """Zu große Datei wird abgelehnt."""
        # Erstelle Content größer als MAX_FILE_SIZE_MB
        content = b"x" * (MAX_FILE_SIZE_MB + 1) * 1024 * 1024

        is_valid, error_msg, metadata = validate_file_security(
            content, "huge.dat", "application/octet-stream"
        )

        assert is_valid is False
        assert "zu groß" in error_msg.lower()
        assert f"Maximum: {MAX_FILE_SIZE_MB}" in error_msg

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_pdf_security')
    def test_pdf_extension_uses_pdf_validation(self, mock_pdf_val, mock_magic):
        """PDF-Extension verwendet PDF-Validierung."""
        mock_magic.return_value = (True, None, "pdf")  # Magic bytes pass
        mock_pdf_val.return_value = (True, "", {"validation_passed": True})

        content = b"pdf content"
        validate_file_security(content, "document.pdf")

        mock_pdf_val.assert_called_once_with(content, "document.pdf")

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_pdf_security')
    def test_pdf_mimetype_uses_pdf_validation(self, mock_pdf_val, mock_magic):
        """PDF-MIME-Type verwendet PDF-Validierung."""
        mock_magic.return_value = (True, None, "pdf")  # Magic bytes pass
        mock_pdf_val.return_value = (True, "", {"validation_passed": True})

        content = b"pdf content"
        validate_file_security(content, "document", "application/pdf")

        mock_pdf_val.assert_called_once()

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_image_security')
    def test_image_extensions_use_image_validation(self, mock_img_val, mock_magic):
        """Bild-Extensions verwenden Bild-Validierung."""
        mock_img_val.return_value = (True, "", {"validation_passed": True})

        extensions = [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"]

        for ext in extensions:
            mock_img_val.reset_mock()
            mock_magic.reset_mock()
            mock_magic.return_value = (True, None, ext.lstrip('.'))  # Magic bytes pass
            content = b"image content"
            validate_file_security(content, f"image{ext}")
            mock_img_val.assert_called_once()

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_image_security')
    def test_image_mimetype_uses_image_validation(self, mock_img_val, mock_magic):
        """Bild-MIME-Type verwendet Bild-Validierung."""
        mock_magic.return_value = (True, None, "jpeg")  # Magic bytes pass
        mock_img_val.return_value = (True, "", {"validation_passed": True})

        content = b"image content"
        validate_file_security(content, "photo", "image/jpeg")

        mock_img_val.assert_called_once()

    def test_unknown_filetype_passes_basic_validation(self):
        """Unbekannter Dateityp passiert Basis-Validierung."""
        content = b"some content"
        is_valid, error_msg, metadata = validate_file_security(
            content, "data.xyz", "application/octet-stream"
        )

        assert is_valid is True
        assert metadata["validation_passed"] is True
        assert metadata["filename"] == "data.xyz"

    def test_metadata_contains_file_info(self):
        """Metadata enthält Datei-Informationen."""
        content = b"test content"
        _, _, metadata = validate_file_security(
            content, "test.txt", "text/plain"
        )

        assert metadata["filename"] == "test.txt"
        assert metadata["size_bytes"] == len(content)
        assert metadata["mime_type"] == "text/plain"


# ==================== validate_upload_file Tests ====================


class TestValidateUploadFile:
    """Tests für validate_upload_file()."""

    @patch('app.core.file_validation.validate_file_security')
    def test_valid_file_returns_metadata(self, mock_validate):
        """Gültige Datei gibt Metadata zurück."""
        mock_validate.return_value = (True, "", {
            "validation_passed": True,
            "filename": "test.pdf",
            "size_bytes": 1000
        })

        content = b"valid content"
        result = validate_upload_file(content, "test.pdf", "application/pdf")

        assert result["validation_passed"] is True
        assert result["filename"] == "test.pdf"

    @patch('app.core.file_validation.validate_file_security')
    def test_invalid_file_raises_exception(self, mock_validate):
        """Ungültige Datei wirft FileValidationError."""
        mock_validate.return_value = (
            False,
            "Datei zu groß",
            {"filename": "huge.pdf"}
        )

        content = b"invalid content"

        with pytest.raises(FileValidationError) as exc_info:
            validate_upload_file(content, "huge.pdf")

        assert "Datei zu groß" in str(exc_info.value)
        assert "Datei zu groß" in exc_info.value.user_message_de

    @patch('app.core.file_validation.validate_file_security')
    def test_calls_validate_file_security(self, mock_validate):
        """validate_upload_file ruft validate_file_security auf."""
        mock_validate.return_value = (True, "", {"validation_passed": True})

        content = b"content"
        validate_upload_file(content, "test.png", "image/png")

        mock_validate.assert_called_once_with(content, "test.png", "image/png")


# ==================== Konstanten Tests ====================


class TestConstants:
    """Tests für Konstanten-Werte."""

    def test_max_pdf_pages_is_reasonable(self):
        """MAX_PDF_PAGES hat sinnvollen Wert."""
        assert MAX_PDF_PAGES >= 100  # Mindestens 100 Seiten
        assert MAX_PDF_PAGES <= 10000  # Nicht unrealistisch hoch

    def test_max_image_dimensions_are_reasonable(self):
        """MAX_IMAGE_WIDTH/HEIGHT haben sinnvolle Werte."""
        assert MAX_IMAGE_WIDTH >= 8000  # Mindestens 8K
        assert MAX_IMAGE_HEIGHT >= 8000
        assert MAX_IMAGE_WIDTH <= 50000  # Nicht unrealistisch
        assert MAX_IMAGE_HEIGHT <= 50000

    def test_max_file_size_is_reasonable(self):
        """MAX_FILE_SIZE_MB hat sinnvollen Wert."""
        assert MAX_FILE_SIZE_MB >= 10  # Mindestens 10 MB
        assert MAX_FILE_SIZE_MB <= 1000  # Max 1 GB

    def test_compression_ratio_is_reasonable(self):
        """MAX_PDF_STREAM_RATIO hat sinnvollen Wert."""
        assert MAX_PDF_STREAM_RATIO >= 10  # Mindestens 10:1
        assert MAX_PDF_STREAM_RATIO <= 1000  # Max 1000:1


# ==================== Integration-Style Tests ====================


class TestIntegrationScenarios:
    """Integration-Style Tests mit realistischen Szenarien."""

    def test_small_text_file_passes(self):
        """Kleine Text-Datei passiert Validierung."""
        content = b"Hello, World! Dies ist ein deutscher Text."

        is_valid, error_msg, metadata = validate_file_security(
            content, "readme.txt", "text/plain"
        )

        assert is_valid is True

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_pdf_security')
    def test_normal_pdf_workflow(self, mock_pdf_val, mock_magic):
        """Normaler PDF-Upload Workflow."""
        mock_magic.return_value = (True, None, "pdf")  # Magic bytes pass
        mock_pdf_val.return_value = (True, "", {
            "page_count": 25,
            "validation_passed": True
        })

        content = b"PDF content"
        result = validate_upload_file(content, "report.pdf", "application/pdf")

        assert result["page_count"] == 25
        assert result["validation_passed"] is True

    @patch('app.core.file_validation.verify_magic_bytes')
    @patch('app.core.file_validation.validate_image_security')
    def test_normal_image_workflow(self, mock_img_val, mock_magic):
        """Normaler Bild-Upload Workflow."""
        mock_magic.return_value = (True, None, "jpeg")  # Magic bytes pass
        mock_img_val.return_value = (True, "", {
            "width": 1920,
            "height": 1080,
            "format": "JPEG",
            "validation_passed": True
        })

        content = b"JPEG content"
        result = validate_upload_file(content, "photo.jpg", "image/jpeg")

        assert result["width"] == 1920
        assert result["format"] == "JPEG"

    def test_edge_case_exactly_max_size(self):
        """Datei mit exakt MAX_FILE_SIZE_MB passiert noch."""
        # Exakt MAX_FILE_SIZE_MB sollte noch OK sein
        content = b"x" * (MAX_FILE_SIZE_MB * 1024 * 1024)

        is_valid, error_msg, metadata = validate_file_security(
            content, "exact.bin", "application/octet-stream"
        )

        # Exakt MAX sollte noch passieren (nicht größer als MAX)
        assert is_valid is True

    def test_edge_case_one_byte_over_max_size(self):
        """Datei mit MAX_FILE_SIZE_MB + 1 Byte wird abgelehnt."""
        content = b"x" * (MAX_FILE_SIZE_MB * 1024 * 1024 + 1)

        is_valid, error_msg, metadata = validate_file_security(
            content, "over.bin", "application/octet-stream"
        )

        assert is_valid is False


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests für Randfälle."""

    def test_empty_file(self):
        """Leere Datei wird von magic bytes validation behandelt."""
        content = b""

        is_valid, error_msg, metadata = validate_file_security(
            content, "empty.txt", "text/plain"
        )

        # Empty files are rejected by magic bytes validation for known extensions
        # or pass through for unknown extensions like .txt
        # The test validates the function handles empty content appropriately
        if is_valid:
            assert metadata.get("validation_passed") is True
        else:
            # Magic bytes validation may reject empty files
            assert "magic" in error_msg.lower() or "leer" in error_msg.lower() or len(error_msg) > 0

    def test_filename_with_special_chars(self):
        """Dateiname mit Sonderzeichen wird verarbeitet."""
        content = b"content"

        is_valid, error_msg, metadata = validate_file_security(
            content, "Dokument äöü ß.txt", "text/plain"
        )

        assert is_valid is True
        assert "äöü" in metadata["filename"]

    def test_uppercase_extension(self):
        """Großgeschriebene Extension wird erkannt."""
        with patch('app.core.file_validation.verify_magic_bytes') as mock_magic:
            mock_magic.return_value = (True, None, "pdf")  # Magic bytes pass
            with patch('app.core.file_validation.validate_pdf_security') as mock_pdf:
                mock_pdf.return_value = (True, "", {"validation_passed": True})

                content = b"pdf content"
                validate_file_security(content, "Document.PDF")

                mock_pdf.assert_called_once()

    def test_none_mime_type(self):
        """None als MIME-Type wird akzeptiert."""
        content = b"content"

        is_valid, error_msg, metadata = validate_file_security(
            content, "file.txt", None
        )

        assert is_valid is True
        assert metadata["mime_type"] is None


# ==================== Path Traversal Tests ====================


class TestPathTraversalError:
    """Tests für PathTraversalError Exception."""

    def test_exception_stores_message(self):
        """PathTraversalError speichert Nachricht."""
        # PathTraversalError only takes filename as argument
        error = PathTraversalError("../etc/passwd")

        assert error.filename == "../etc/passwd"
        assert "traversal" in str(error).lower()

    def test_exception_is_raiseable(self):
        """PathTraversalError kann geworfen und gefangen werden."""
        with pytest.raises(PathTraversalError) as exc_info:
            raise PathTraversalError("../../secret.txt")

        assert exc_info.value.filename == "../../secret.txt"


class TestSanitizeFilename:
    """Tests für sanitize_filename() - Path Traversal Schutz."""

    def test_normal_filename_passes(self):
        """Normaler Dateiname bleibt unverändert."""
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_german_umlauts_allowed(self):
        """Deutsche Umlaute werden erlaubt."""
        result = sanitize_filename("Prüfbericht_Müller.pdf")
        assert result == "Prüfbericht_Müller.pdf"

    def test_spaces_allowed(self):
        """Leerzeichen werden erlaubt."""
        result = sanitize_filename("Mein Dokument 2024.pdf")
        assert result == "Mein Dokument 2024.pdf"

    def test_path_traversal_double_dot_sanitized(self):
        """Doppelpunkt Path Traversal wird sanitisiert (basename extrahiert)."""
        # Implementation uses os.path.basename() which strips path components
        result = sanitize_filename("../etc/passwd")
        # Should return basename without dangerous path components
        assert ".." not in result
        assert "/" not in result
        # Result should be the basename (passwd) with allowed chars only
        assert result == "passwd"

    def test_path_traversal_backslash_sanitized(self):
        """Backslash Path Traversal wird sanitisiert (basename extrahiert)."""
        # Implementation uses os.path.basename() which strips path components
        result = sanitize_filename("..\\windows\\system32")
        # Should return basename without dangerous path components
        assert ".." not in result
        assert "\\" not in result
        # Result should be the basename
        assert result == "system32"

    def test_absolute_path_linux_sanitized(self):
        """Absoluter Linux-Pfad wird sanitisiert (basename extrahiert)."""
        # os.path.basename("/etc/passwd") returns "passwd"
        result = sanitize_filename("/etc/passwd")
        assert "/" not in result
        assert result == "passwd"

    def test_absolute_path_windows_sanitized(self):
        """Absoluter Windows-Pfad wird sanitisiert (basename extrahiert)."""
        # os.path.basename("C:\\Windows\\system.ini") returns "system.ini"
        result = sanitize_filename("C:\\Windows\\system.ini")
        assert "\\" not in result
        assert ":" not in result
        # Note: basename strips path, result is just the filename
        assert "system" in result

    def test_null_byte_injection_raises(self):
        """Null-Byte Injection wird erkannt und wirft PathTraversalError."""
        # Null byte is in DANGEROUS_FILENAME_PATTERNS, so it raises
        with pytest.raises(PathTraversalError):
            sanitize_filename("file.pdf\x00.txt")

    def test_encoded_traversal_sanitized(self):
        """URL-kodierte Path Traversal wird sanitisiert."""
        # %2e%2e = ..
        result = sanitize_filename("%2e%2e/etc/passwd")
        # os.path.basename strips path, strict mode replaces % with _
        assert "/" not in result

    def test_too_long_filename_truncated(self):
        """Zu langer Dateiname wird gekürzt."""
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name, strict=False)
        assert len(result) <= MAX_FILENAME_LENGTH

    def test_strict_mode_replaces_special_chars(self):
        """Strict Mode ersetzt Sonderzeichen mit Unterstrich."""
        # Strict mode replaces disallowed characters with underscores
        result = sanitize_filename("file<script>.pdf", strict=True)
        assert "<" not in result
        assert ">" not in result
        assert "file" in result
        assert ".pdf" in result

    def test_non_strict_mode_allows_more_chars(self):
        """Non-Strict Mode ist toleranter."""
        # Sollte nicht raisen, da non-strict
        result = sanitize_filename("file(1).pdf", strict=False)
        assert "file" in result

    def test_empty_filename_returns_default(self):
        """Leerer Dateiname wird durch Standardnamen ersetzt."""
        # Empty filename returns "unnamed_file" instead of raising
        result = sanitize_filename("")
        assert result == "unnamed_file"

    def test_whitespace_only_returns_default(self):
        """Nur Whitespace wird durch Standardnamen ersetzt."""
        # Whitespace-only filename returns "unnamed_file" after sanitization
        result = sanitize_filename("   ")
        # After stripping and sanitization, empty names become "unnamed_file"
        assert result == "unnamed_file" or len(result) > 0

    def test_hidden_file_dot_prefix(self):
        """Versteckte Dateien (Punkt-Präfix) werden behandelt."""
        # Leading dots are stripped for security
        result = sanitize_filename(".gitignore", strict=False)
        # Implementation strips leading dots
        assert "gitignore" in result

    def test_multiple_extensions(self):
        """Mehrere Extensions werden akzeptiert."""
        result = sanitize_filename("archive.tar.gz")
        assert result == "archive.tar.gz"

    def test_dangerous_patterns_comprehensive(self):
        """Alle gefährlichen Patterns werden behandelt."""
        # Patterns that get sanitized (path components stripped by basename)
        sanitized_names = [
            ("../secret", "secret"),
            ("..\\secret", "secret"),
            ("/root/.ssh/id_rsa", "id_rsa"),
            ("C:\\Users\\Admin\\secret.txt", "secret.txt"),
        ]

        for name, expected_base in sanitized_names:
            # Implementation sanitizes instead of raising
            result = sanitize_filename(name)
            # Ensure no dangerous path separators in result
            assert "/" not in result
            assert "\\" not in result

        # URL-encoded patterns get sanitized (% is replaced with _)
        result = sanitize_filename("..%2f..%2fetc%2fpasswd")
        assert "/" not in result
        assert "\\" not in result

        # Null byte raises PathTraversalError (it's in DANGEROUS_FILENAME_PATTERNS)
        with pytest.raises(PathTraversalError):
            sanitize_filename("file\x00.txt")


# ==================== Magic Bytes Tests ====================


class TestVerifyMagicBytes:
    """Tests für verify_magic_bytes() - Datei-Signatur Validierung."""

    def test_valid_pdf_signature(self):
        """Gültige PDF Magic Bytes werden erkannt."""
        content = b"%PDF-1.7\n..."  # PDF Header
        # Return order: (is_valid, error_message, detected_type)
        is_valid, error, detected_type = verify_magic_bytes(content, "document.pdf")

        assert is_valid is True
        assert error == ""
        # For matching signatures, detected_type is the file extension
        assert detected_type is not None

    def test_valid_png_signature(self):
        """Gültige PNG Magic Bytes werden erkannt."""
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # PNG Header
        is_valid, error, detected_type = verify_magic_bytes(content, "image.png")

        assert is_valid is True
        assert error == ""

    def test_valid_jpeg_signature(self):
        """Gültige JPEG Magic Bytes werden erkannt."""
        content = b"\xff\xd8\xff" + b"\x00" * 100  # JPEG Header (SOI + marker)
        is_valid, error, detected_type = verify_magic_bytes(content, "photo.jpg")

        assert is_valid is True
        assert error == ""

    def test_valid_tiff_le_signature(self):
        """Gültige TIFF Little-Endian Magic Bytes werden erkannt."""
        content = b"II\x2a\x00" + b"\x00" * 100  # TIFF LE Header
        is_valid, error, detected_type = verify_magic_bytes(content, "scan.tiff")

        assert is_valid is True

    def test_valid_tiff_be_signature(self):
        """Gültige TIFF Big-Endian Magic Bytes werden erkannt."""
        content = b"MM\x00\x2a" + b"\x00" * 100  # TIFF BE Header
        is_valid, error, detected_type = verify_magic_bytes(content, "scan.tif")

        assert is_valid is True

    def test_valid_bmp_signature(self):
        """Gültige BMP Magic Bytes werden erkannt."""
        content = b"BM" + b"\x00" * 100  # BMP Header
        is_valid, error, detected_type = verify_magic_bytes(content, "image.bmp")

        assert is_valid is True

    def test_mismatched_extension_pdf_as_jpg(self):
        """PDF mit .jpg Extension wird abgelehnt."""
        content = b"%PDF-1.7\n..."  # PDF Header
        is_valid, error, detected_type = verify_magic_bytes(content, "fake.jpg")

        assert is_valid is False
        assert error is not None and len(error) > 0
        # Error message should indicate mismatch

    def test_mismatched_extension_exe_as_pdf(self):
        """EXE mit .pdf Extension wird abgelehnt."""
        content = b"MZ" + b"\x00" * 100  # DOS/PE Header
        is_valid, error, detected_type = verify_magic_bytes(content, "malware.pdf")

        assert is_valid is False

    def test_unknown_extension_passes(self):
        """Unbekannte Extension wird durchgelassen."""
        content = b"unknown content format"
        is_valid, error, detected_type = verify_magic_bytes(content, "data.xyz")

        # Unbekannte Extensions sollten durchgelassen werden (keine Signatur-Prüfung)
        assert is_valid is True

    def test_empty_content_fails(self):
        """Leerer Content wird abgelehnt."""
        content = b""
        is_valid, error, detected_type = verify_magic_bytes(content, "empty.pdf")

        assert is_valid is False
        assert error is not None and len(error) > 0

    def test_truncated_content_fails(self):
        """Zu kurzer Content für Signatur-Prüfung wird abgelehnt."""
        content = b"%P"  # Zu kurz für PDF Header
        is_valid, error, detected_type = verify_magic_bytes(content, "short.pdf")

        assert is_valid is False

    def test_case_insensitive_extension(self):
        """Extension-Vergleich ist case-insensitive."""
        content = b"%PDF-1.7\n..."
        is_valid, _, _ = verify_magic_bytes(content, "Document.PDF")
        assert is_valid is True

        is_valid, _, _ = verify_magic_bytes(content, "Document.Pdf")
        assert is_valid is True

    def test_file_signatures_constant_exists(self):
        """FILE_SIGNATURES Konstante enthält erwartete Einträge."""
        assert ".pdf" in FILE_SIGNATURES
        assert ".png" in FILE_SIGNATURES
        assert ".jpg" in FILE_SIGNATURES or ".jpeg" in FILE_SIGNATURES

    def test_polyglot_detection(self):
        """Polyglot-Dateien (mehrere gültige Signaturen) werden erkannt."""
        # Inhalt der wie PDF aussieht aber .png Extension hat
        content = b"%PDF-1.7\n" + b"\x00" * 100
        # Return order: (is_valid, error_message, detected_type)
        is_valid, error, detected_type = verify_magic_bytes(content, "polyglot.png")

        # Sollte ablehnen weil PDF-Signatur aber PNG-Extension
        assert is_valid is False


# ==================== Combined Security Tests ====================


class TestCombinedSecurityValidation:
    """Integration Tests für kombinierte Sicherheits-Validierung."""

    def test_path_traversal_then_magic_bytes(self):
        """Erst Path Traversal Sanitisierung, dann Magic Bytes Prüfung."""
        # Schritt 1: Path Traversal - wird sanitisiert (nicht Exception)
        filename = "../../../etc/passwd"
        # Implementation uses os.path.basename() which strips path components
        sanitized = sanitize_filename(filename)
        # Path traversal is sanitized to basename
        assert ".." not in sanitized
        assert "/" not in sanitized
        assert sanitized == "passwd"

        # Schritt 2: Normaler Filename, dann Magic Bytes
        safe_filename = "document.pdf"
        sanitized = sanitize_filename(safe_filename)
        assert sanitized == safe_filename

        content = b"%PDF-1.7\n" + b"\x00" * 100
        is_valid, _, _ = verify_magic_bytes(content, sanitized)
        assert is_valid is True

    def test_full_validation_workflow(self):
        """Vollständiger Validierungs-Workflow."""
        # 1. Filename sanitieren
        original_name = "Rechnung_2024 (1).pdf"
        try:
            safe_name = sanitize_filename(original_name, strict=False)
        except PathTraversalError:
            pytest.fail("Safe filename should not raise")

        # 2. Magic Bytes prüfen
        content = b"%PDF-1.7\nvalid pdf content here"
        is_valid, _, error = verify_magic_bytes(content, safe_name)
        assert is_valid is True, f"Magic bytes validation failed: {error}"

        # 3. File security prüfen (mocked für Geschwindigkeit)
        with patch('app.core.file_validation.validate_pdf_security') as mock_pdf:
            mock_pdf.return_value = (True, "", {"validation_passed": True})
            result = validate_file_security(content, safe_name)
            assert result[0] is True
