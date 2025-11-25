"""
Custom exceptions for Ablage-System OCR
Structured error handling for production reliability
Created: 2024-11-22
"""

from typing import Optional, Dict, Any


class AblageSystemException(Exception):
    """Base exception for all Ablage-System errors"""

    def __init__(
        self,
        message: str,
        error_code: str,
        details: Optional[Dict[str, Any]] = None,
        user_message_de: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.user_message_de = user_message_de or message

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message_de": self.user_message_de,
            "details": self.details
        }


# GPU-Related Exceptions
class GPUException(AblageSystemException):
    """Base class for GPU-related errors"""
    pass


class GPUOutOfMemoryError(GPUException):
    """GPU VRAM exceeded"""

    def __init__(self, message: str, required_gb: float, available_gb: float):
        super().__init__(
            message=message,
            error_code="E001",
            details={
                "required_gb": required_gb,
                "available_gb": available_gb
            },
            user_message_de=f"GPU-Speicher nicht ausreichend: {required_gb:.1f}GB benötigt, {available_gb:.1f}GB verfügbar"
        )


class GPUNotAvailableError(GPUException):
    """GPU not detected or not accessible"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"GPU not available: {reason}",
            error_code="E002",
            details={"reason": reason},
            user_message_de=f"GPU nicht verfügbar: {reason}"
        )


# OCR-Related Exceptions
class OCRException(AblageSystemException):
    """Base class for OCR processing errors"""
    pass


class OCRProcessingError(OCRException):
    """OCR processing failed"""

    def __init__(self, document_id: str, backend: str, reason: str):
        super().__init__(
            message=f"OCR failed for document {document_id} with {backend}: {reason}",
            error_code="E004",
            details={
                "document_id": document_id,
                "backend": backend,
                "reason": reason
            },
            user_message_de=f"OCR-Verarbeitung fehlgeschlagen: {reason}"
        )


class OCRBackendTimeoutError(OCRException):
    """OCR backend timeout"""

    def __init__(self, backend: str, timeout_seconds: int):
        super().__init__(
            message=f"OCR backend {backend} timed out after {timeout_seconds}s",
            error_code="E004",
            details={
                "backend": backend,
                "timeout_seconds": timeout_seconds
            },
            user_message_de=f"OCR-Verarbeitung dauerte zu lange (>{timeout_seconds}s)"
        )


class BackendSelectionError(OCRException):
    """Failed to select appropriate OCR backend"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Backend selection failed: {reason}",
            error_code="E010",
            details={"reason": reason},
            user_message_de="Kein geeignetes OCR-System verfügbar"
        )


# German Text Processing Exceptions
class GermanTextException(AblageSystemException):
    """Base class for German text processing errors"""
    pass


class InvalidGermanEncodingError(GermanTextException):
    """German text encoding error (umlauts corrupted)"""

    def __init__(self, text_sample: str):
        super().__init__(
            message=f"Invalid German encoding detected in: {text_sample[:50]}...",
            error_code="E003",
            details={"text_sample": text_sample[:100]},
            user_message_de="Ungültige Textcodierung erkannt (Umlaute fehlerhaft)"
        )


# Document Processing Exceptions
class DocumentException(AblageSystemException):
    """Base class for document processing errors"""
    pass


class DocumentNotFoundError(DocumentException):
    """Document not found in storage"""

    def __init__(self, document_id: str):
        super().__init__(
            message=f"Document not found: {document_id}",
            error_code="E007",
            details={"document_id": document_id},
            user_message_de="Dokument nicht gefunden"
        )


class InvalidDocumentFormatError(DocumentException):
    """Document format not supported"""

    def __init__(self, filename: str, format_detected: str):
        super().__init__(
            message=f"Invalid document format: {format_detected} in {filename}",
            error_code="E007",
            details={
                "filename": filename,
                "format_detected": format_detected
            },
            user_message_de=f"Ungültiges Dateiformat: {format_detected}"
        )


class FileSizeExceededError(DocumentException):
    """File size exceeds limit"""

    def __init__(self, size_mb: float, max_size_mb: float):
        super().__init__(
            message=f"File size {size_mb:.1f}MB exceeds limit of {max_size_mb:.1f}MB",
            error_code="E008",
            details={
                "size_mb": size_mb,
                "max_size_mb": max_size_mb
            },
            user_message_de=f"Datei zu groß: {size_mb:.1f}MB (max: {max_size_mb:.1f}MB)"
        )


# Database Exceptions
class DatabaseException(AblageSystemException):
    """Base class for database errors"""
    pass


class DatabaseConnectionError(DatabaseException):
    """Database connection failed"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Database connection failed: {reason}",
            error_code="E005",
            details={"reason": reason},
            user_message_de="Datenbankverbindung fehlgeschlagen"
        )


# GDPR/Compliance Exceptions
class ComplianceException(AblageSystemException):
    """Base class for GDPR/compliance violations"""
    pass


class GDPRViolationError(ComplianceException):
    """GDPR compliance violation detected"""

    def __init__(self, violation_type: str, details: str):
        super().__init__(
            message=f"GDPR violation: {violation_type} - {details}",
            error_code="E009",
            details={
                "violation_type": violation_type,
                "violation_details": details
            },
            user_message_de="DSGVO-Verstoß erkannt"
        )


# Error Code Registry (from ERROR_PATTERNS.md)
ERROR_CODE_REGISTRY = {
    "E001": "GPU Out of Memory",
    "E002": "GPU Not Available",
    "E003": "Invalid German Text Encoding",
    "E004": "OCR Backend Timeout",
    "E005": "Database Connection Failed",
    "E006": "Redis Connection Failed",
    "E007": "Document Format Invalid",
    "E008": "File Size Exceeded",
    "E009": "GDPR Violation Detected",
    "E010": "Backend Selection Failed"
}


def get_error_description(error_code: str) -> str:
    """Get human-readable error description"""
    return ERROR_CODE_REGISTRY.get(error_code, "Unknown Error")
