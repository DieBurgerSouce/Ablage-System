"""
Document Upload Validator

Comprehensive validation for document uploads including file type, size,
security scanning, and German text validation.

Validation checks:
- File type (PDF, PNG, JPG, TIFF only)
- File size (max 50 MB)
- Virus scanning (ClamAV)
- German text encoding (UTF-8)
- Image quality (min DPI for OCR)
- PDF corruption check
"""

import magic
import hashlib
from pathlib import Path
from typing import List, Optional
from PIL import Image
import PyPDF2

import structlog
from pydantic import BaseModel, Field

from app.core.config import settings


logger = structlog.get_logger(__name__)


# ============================================================================
# Validation Result Models
# ============================================================================

class ValidationIssue(BaseModel):
    """Single validation issue."""
    severity: str = Field(..., description="error, warning, info")
    code: str = Field(..., description="Unique error code")
    message: str = Field(..., description="Human-readable message (German)")
    field: Optional[str] = Field(None, description="Affected field")
    suggestion: Optional[str] = Field(None, description="How to fix")


class DocumentValidationResult(BaseModel):
    """Result of document validation."""
    is_valid: bool = Field(..., description="Overall validation status")
    issues: List[ValidationIssue] = Field(default_factory=list)
    warnings: List[ValidationIssue] = Field(default_factory=list)
    file_hash: Optional[str] = Field(None, description="SHA-256 hash")
    detected_mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(issue.severity == "warning" for issue in self.issues + self.warnings)


# ============================================================================
# Document Upload Validator
# ============================================================================

class DocumentUploadValidator:
    """
    Comprehensive document upload validator.

    Validates documents before accepting upload to ensure quality and security.
    """

    # Allowed MIME types
    ALLOWED_MIME_TYPES = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
    ]

    # Allowed file extensions
    ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]

    # File size limits
    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
    MIN_FILE_SIZE_BYTES = 1024  # 1 KB

    # Image quality requirements
    MIN_DPI = 150  # Minimum DPI for good OCR
    RECOMMENDED_DPI = 300

    def __init__(self):
        logger.info("document_validator_initialized")

    async def validate(
        self,
        file_path: str,
        original_filename: str,
        skip_virus_scan: bool = False
    ) -> DocumentValidationResult:
        """
        Validate uploaded document.

        Args:
            file_path: Path to uploaded file
            original_filename: Original filename from upload
            skip_virus_scan: Skip virus scanning (for testing)

        Returns:
            DocumentValidationResult with validation status and issues
        """
        result = DocumentValidationResult(is_valid=True)
        file_path_obj = Path(file_path)

        logger.info(
            "validating_document",
            filename=original_filename,
            path=file_path
        )

        try:
            # 1. File existence check
            if not file_path_obj.exists():
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="FILE_NOT_FOUND",
                        message="Datei nicht gefunden",
                        suggestion="Stellen Sie sicher, dass die Datei hochgeladen wurde"
                    )
                )
                result.is_valid = False
                return result

            # 2. File size validation
            file_size = file_path_obj.stat().st_size
            result.file_size_bytes = file_size

            if file_size < self.MIN_FILE_SIZE_BYTES:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="FILE_TOO_SMALL",
                        message=f"Datei zu klein ({file_size} Bytes). Mindestgröße: {self.MIN_FILE_SIZE_BYTES} Bytes",
                        suggestion="Laden Sie eine gültige Datei hoch"
                    )
                )
                result.is_valid = False

            if file_size > self.MAX_FILE_SIZE_BYTES:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="FILE_TOO_LARGE",
                        message=f"Datei zu groß ({file_size / 1024 / 1024:.2f} MB). Maximalgröße: {self.MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB",
                        suggestion="Komprimieren Sie die Datei oder teilen Sie sie auf"
                    )
                )
                result.is_valid = False

            # 3. File type validation (MIME type detection)
            mime_type = magic.from_file(file_path, mime=True)
            result.detected_mime_type = mime_type

            if mime_type not in self.ALLOWED_MIME_TYPES:
                result.issues.append(
                    ValidationIssue(
                        severity="error",
                        code="INVALID_FILE_TYPE",
                        message=f"Dateityp '{mime_type}' nicht unterstützt",
                        suggestion=f"Erlaubte Dateitypen: {', '.join(self.ALLOWED_MIME_TYPES)}"
                    )
                )
                result.is_valid = False

            # 4. Extension validation
            extension = file_path_obj.suffix.lower()
            if extension not in self.ALLOWED_EXTENSIONS:
                result.issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="UNUSUAL_EXTENSION",
                        message=f"Ungewöhnliche Dateiendung: {extension}",
                        suggestion=f"Empfohlene Endungen: {', '.join(self.ALLOWED_EXTENSIONS)}"
                    )
                )

            # 5. Calculate file hash (for deduplication)
            result.file_hash = await self._calculate_hash(file_path)

            # 6. File-type-specific validation
            if mime_type == "application/pdf":
                pdf_issues = await self._validate_pdf(file_path)
                result.issues.extend(pdf_issues)

            elif mime_type.startswith("image/"):
                image_issues = await self._validate_image(file_path)
                result.issues.extend(image_issues)

            # 7. Virus scanning (if enabled)
            if not skip_virus_scan:
                virus_issues = await self._scan_for_viruses(file_path)
                result.issues.extend(virus_issues)

            # 8. German text encoding validation (sample check)
            encoding_issues = await self._validate_encoding(file_path, mime_type)
            result.issues.extend(encoding_issues)

            # Update overall validity
            result.is_valid = not result.has_errors

            logger.info(
                "validation_complete",
                filename=original_filename,
                is_valid=result.is_valid,
                errors=len([i for i in result.issues if i.severity == "error"]),
                warnings=len([i for i in result.issues if i.severity == "warning"])
            )

            return result

        except Exception as e:
            logger.exception("validation_failed", filename=original_filename, error=str(e))

            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="VALIDATION_ERROR",
                    message=f"Validierungsfehler: {str(e)}",
                    suggestion="Kontaktieren Sie den Support"
                )
            )
            result.is_valid = False
            return result

    async def _calculate_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file."""
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in 8KB chunks
            for byte_block in iter(lambda: f.read(8192), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    async def _validate_pdf(self, file_path: str) -> List[ValidationIssue]:
        """Validate PDF file."""
        issues = []

        try:
            with open(file_path, "rb") as f:
                pdf = PyPDF2.PdfReader(f)

                # Check if PDF is encrypted
                if pdf.is_encrypted:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="PDF_ENCRYPTED",
                            message="PDF ist passwortgeschützt",
                            suggestion="Entfernen Sie den Passwortschutz vor dem Upload"
                        )
                    )

                # Check page count
                page_count = len(pdf.pages)
                if page_count == 0:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="PDF_NO_PAGES",
                            message="PDF enthält keine Seiten",
                            suggestion="Laden Sie ein gültiges PDF hoch"
                        )
                    )

                if page_count > 100:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="PDF_MANY_PAGES",
                            message=f"PDF enthält {page_count} Seiten",
                            suggestion="OCR-Verarbeitung kann länger dauern"
                        )
                    )

                # Try to extract text from first page (corruption check)
                try:
                    first_page_text = pdf.pages[0].extract_text()
                except Exception as e:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="PDF_CORRUPTED",
                            message="PDF scheint beschädigt zu sein",
                            suggestion="Öffnen und erneut speichern Sie das PDF"
                        )
                    )

        except PyPDF2.errors.PdfReadError as e:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="PDF_INVALID",
                    message=f"Ungültiges PDF-Format: {str(e)}",
                    suggestion="Stellen Sie sicher, dass die Datei ein gültiges PDF ist"
                )
            )
        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="PDF_VALIDATION_ERROR",
                    message=f"PDF-Validierung fehlgeschlagen: {str(e)}",
                    suggestion="Versuchen Sie es mit einer anderen Datei"
                )
            )

        return issues

    async def _validate_image(self, file_path: str) -> List[ValidationIssue]:
        """Validate image file."""
        issues = []

        try:
            with Image.open(file_path) as img:
                # Check image dimensions
                width, height = img.size

                if width < 100 or height < 100:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="IMAGE_TOO_SMALL",
                            message=f"Bild zu klein ({width}x{height} Pixel)",
                            suggestion="Mindestgröße: 100x100 Pixel"
                        )
                    )

                # Check DPI (if available)
                if "dpi" in img.info:
                    dpi = img.info["dpi"]
                    avg_dpi = (dpi[0] + dpi[1]) / 2

                    if avg_dpi < self.MIN_DPI:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                code="IMAGE_LOW_DPI",
                                message=f"Niedrige Bildauflösung ({avg_dpi:.0f} DPI)",
                                suggestion=f"Empfohlen: {self.RECOMMENDED_DPI} DPI für beste OCR-Ergebnisse"
                            )
                        )

                # Check color mode
                if img.mode not in ["RGB", "L", "RGBA"]:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="IMAGE_UNUSUAL_MODE",
                            message=f"Ungewöhnlicher Farbmodus: {img.mode}",
                            suggestion="Konvertieren Sie zu RGB oder Graustufen"
                        )
                    )

        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="IMAGE_INVALID",
                    message=f"Ungültiges Bildformat: {str(e)}",
                    suggestion="Stellen Sie sicher, dass die Datei ein gültiges Bild ist"
                )
            )

        return issues

    async def _scan_for_viruses(self, file_path: str) -> List[ValidationIssue]:
        """
        Scan file for viruses using ClamAV.

        Note: Requires ClamAV to be installed and running.
        """
        issues = []

        try:
            import pyclamd

            # Connect to ClamAV daemon
            cd = pyclamd.ClamdUnixSocket()

            # Check if ClamAV is available
            if not cd.ping():
                logger.warning("clamav_not_available")
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="VIRUS_SCAN_UNAVAILABLE",
                        message="Virenscanner nicht verfügbar",
                        suggestion="ClamAV wird empfohlen"
                    )
                )
                return issues

            # Scan file
            scan_result = cd.scan_file(file_path)

            if scan_result:
                # Virus found!
                virus_name = scan_result[file_path][1]
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="VIRUS_DETECTED",
                        message=f"Virus erkannt: {virus_name}",
                        suggestion="Datei in Quarantäne verschieben"
                    )
                )
                logger.error("virus_detected", file=file_path, virus=virus_name)

        except ImportError:
            logger.warning("pyclamd_not_installed")
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="VIRUS_SCAN_SKIPPED",
                    message="Virenscanner nicht konfiguriert",
                    suggestion="Installieren Sie pyclamd für Viruscanning"
                )
            )
        except Exception as e:
            logger.error("virus_scan_failed", error=str(e))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="VIRUS_SCAN_ERROR",
                    message=f"Virenscan fehlgeschlagen: {str(e)}",
                    suggestion="Überprüfen Sie ClamAV-Konfiguration"
                )
            )

        return issues

    async def _validate_encoding(
        self,
        file_path: str,
        mime_type: str
    ) -> List[ValidationIssue]:
        """
        Validate file encoding (UTF-8 for text content).

        For PDFs, check if text extraction works with German characters.
        """
        issues = []

        if mime_type == "application/pdf":
            try:
                with open(file_path, "rb") as f:
                    pdf = PyPDF2.PdfReader(f)
                    if len(pdf.pages) > 0:
                        text = pdf.pages[0].extract_text()

                        # Check for German umlauts
                        has_umlauts = any(c in text for c in "äöüÄÖÜß")

                        # Check for encoding issues (mojibake)
                        if "Ã¤" in text or "Ã¶" in text or "Ã¼" in text:
                            issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    code="ENCODING_ISSUE",
                                    message="Mögliches Encoding-Problem (Umlaute fehlerhaft)",
                                    suggestion="PDF mit korrekter UTF-8 Kodierung neu erstellen"
                                )
                            )

            except Exception as e:
                logger.debug("encoding_validation_failed", error=str(e))

        return issues


# ============================================================================
# Convenience Functions
# ============================================================================

async def validate_document(
    file_path: str,
    original_filename: str,
    skip_virus_scan: bool = False
) -> DocumentValidationResult:
    """
    Convenience function for document validation.

    Args:
        file_path: Path to file
        original_filename: Original filename
        skip_virus_scan: Skip virus scanning

    Returns:
        DocumentValidationResult
    """
    validator = DocumentUploadValidator()
    return await validator.validate(file_path, original_filename, skip_virus_scan)


# ============================================================================
# CLI for Testing
# ============================================================================

async def main():
    """CLI for testing document validation."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python document_upload_validator.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    original_filename = Path(file_path).name

    # Validate
    result = await validate_document(file_path, original_filename, skip_virus_scan=True)

    # Print results
    print(f"\n=== Validation Result ===")
    print(f"Valid: {result.is_valid}")
    print(f"File Hash: {result.file_hash}")
    print(f"MIME Type: {result.detected_mime_type}")
    print(f"File Size: {result.file_size_bytes / 1024:.2f} KB")

    if result.issues:
        print(f"\n=== Issues ({len(result.issues)}) ===")
        for issue in result.issues:
            print(f"\n[{issue.severity.upper()}] {issue.code}")
            print(f"  Message: {issue.message}")
            if issue.suggestion:
                print(f"  Suggestion: {issue.suggestion}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
