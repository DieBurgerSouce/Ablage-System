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


# Generic HTTP-Style Exceptions
class NotFoundError(AblageSystemException):
    """Resource not found error"""

    def __init__(self, message: str = "Ressource nicht gefunden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E404",
            details=details,
            user_message_de=message
        )


class ForbiddenError(AblageSystemException):
    """Access forbidden error"""

    def __init__(self, message: str = "Zugriff verweigert", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E403",
            details=details,
            user_message_de=message
        )


class ValidationError(AblageSystemException):
    """Input validation error"""

    def __init__(self, message: str = "Validierungsfehler", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E400",
            details=details,
            user_message_de=message
        )


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


class InferenceTimeoutError(OCRException):
    """OCR inference timed out during generation"""

    def __init__(self, backend: str, timeout_seconds: float, document_id: Optional[str] = None):
        super().__init__(
            message=f"Inference timed out for {backend} after {timeout_seconds}s",
            error_code="E004",
            details={
                "backend": backend,
                "timeout_seconds": timeout_seconds,
                "document_id": document_id,
                "fallback_available": True
            },
            user_message_de=f"OCR-Inferenz Timeout nach {timeout_seconds:.0f}s"
        )
        self.backend = backend
        self.timeout_seconds = timeout_seconds
        self.document_id = document_id


class OCRGPUOutOfMemoryError(OCRException):
    """GPU out of memory during OCR processing - signals fallback availability"""

    def __init__(
        self,
        backend: str,
        document_id: Optional[str] = None,
        required_gb: Optional[float] = None,
        available_gb: Optional[float] = None,
        fallback_backends: Optional[list] = None
    ):
        fallback_backends = fallback_backends or ["surya"]
        super().__init__(
            message=f"GPU OOM in {backend}. Fallback backends available: {fallback_backends}",
            error_code="E001",
            details={
                "backend": backend,
                "document_id": document_id,
                "required_gb": required_gb,
                "available_gb": available_gb,
                "fallback_available": True,
                "fallback_backends": fallback_backends
            },
            user_message_de=f"GPU-Speicher erschoepft bei {backend}. Fallback verfuegbar."
        )
        self.backend = backend
        self.document_id = document_id
        self.fallback_backends = fallback_backends


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


class GDPRError(ComplianceException):
    """General GDPR operation error"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E011",
            details=details or {},
            user_message_de=message
        )


class UserNotFoundError(AblageSystemException):
    """User not found in database"""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User not found: {user_id}",
            error_code="E012",
            details={"user_id": user_id},
            user_message_de="Benutzer nicht gefunden"
        )


class ExportError(AblageSystemException):
    """Data export operation error"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E013",
            details=details or {},
            user_message_de=message
        )


class EmailVerificationError(AblageSystemException):
    """Email verification operation error"""

    def __init__(self, message: str, user_message_de: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E014",
            details=details or {},
            user_message_de=user_message_de
        )


# ==================== Storage Exceptions (E015) ====================

class StorageError(AblageSystemException):
    """Base class for storage-related errors (MinIO/S3)"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E015",
            details=details or {},
            user_message_de="Speicherfehler aufgetreten"
        )


class S3UploadError(StorageError):
    """S3/MinIO upload failed"""

    def __init__(self, bucket: str, key: str, reason: str):
        super().__init__(
            message=f"Failed to upload to {bucket}/{key}: {reason}",
            details={
                "bucket": bucket,
                "key": key,
                "reason": reason
            }
        )
        self.user_message_de = f"Upload fehlgeschlagen: {reason}"


class BucketNotFoundError(StorageError):
    """S3/MinIO bucket not found"""

    def __init__(self, bucket: str):
        super().__init__(
            message=f"Bucket not found: {bucket}",
            details={"bucket": bucket}
        )
        self.user_message_de = f"Speicher-Bucket nicht gefunden: {bucket}"


class StorageQuotaExceededError(StorageError):
    """Storage quota exceeded"""

    def __init__(self, used_gb: float, quota_gb: float):
        super().__init__(
            message=f"Storage quota exceeded: {used_gb:.1f}GB used of {quota_gb:.1f}GB",
            details={
                "used_gb": used_gb,
                "quota_gb": quota_gb
            }
        )
        self.user_message_de = f"Speicherkontingent erschoepft: {used_gb:.1f}GB von {quota_gb:.1f}GB genutzt"


# ==================== Webhook Exceptions (E016) ====================

class WebhookError(AblageSystemException):
    """Base class for webhook-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E016",
            details=details or {},
            user_message_de="Webhook-Fehler aufgetreten"
        )


class WebhookDeliveryError(WebhookError):
    """Webhook delivery failed after retries"""

    def __init__(self, webhook_id: str, url: str, status_code: int, retries: int):
        super().__init__(
            message=f"Webhook delivery failed to {url}: HTTP {status_code} after {retries} retries",
            details={
                "webhook_id": webhook_id,
                "url": url,
                "status_code": status_code,
                "retries": retries
            }
        )
        self.user_message_de = f"Webhook-Zustellung fehlgeschlagen (HTTP {status_code})"


class WebhookValidationError(WebhookError):
    """Webhook URL or payload validation failed"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Webhook validation failed: {reason}",
            details={"reason": reason}
        )
        self.user_message_de = f"Webhook-Validierung fehlgeschlagen: {reason}"


# ==================== Backup Exceptions (E017) ====================

class BackupError(AblageSystemException):
    """Base class for backup-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E017",
            details=details or {},
            user_message_de="Backup-Fehler aufgetreten"
        )


class BackupCreationError(BackupError):
    """Backup creation failed"""

    def __init__(self, backup_type: str, reason: str):
        super().__init__(
            message=f"Backup creation failed for {backup_type}: {reason}",
            details={
                "backup_type": backup_type,
                "reason": reason
            }
        )
        self.user_message_de = f"Backup-Erstellung fehlgeschlagen: {reason}"


class BackupRestoreError(BackupError):
    """Backup restoration failed"""

    def __init__(self, backup_id: str, reason: str):
        super().__init__(
            message=f"Backup restore failed for {backup_id}: {reason}",
            details={
                "backup_id": backup_id,
                "reason": reason
            }
        )
        self.user_message_de = f"Backup-Wiederherstellung fehlgeschlagen: {reason}"


# ==================== ML/AI Exceptions (E018) ====================

class MLError(AblageSystemException):
    """Base class for ML/AI-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E018",
            details=details or {},
            user_message_de="ML-Verarbeitungsfehler aufgetreten"
        )


class DriftDetectionError(MLError):
    """Model drift detection failed"""

    def __init__(self, model_name: str, reason: str):
        super().__init__(
            message=f"Drift detection failed for model {model_name}: {reason}",
            details={
                "model_name": model_name,
                "reason": reason
            }
        )
        self.user_message_de = f"Modell-Drift-Erkennung fehlgeschlagen: {reason}"


class ModelLoadError(MLError):
    """ML model loading failed"""

    def __init__(self, model_name: str, reason: str):
        super().__init__(
            message=f"Failed to load model {model_name}: {reason}",
            details={
                "model_name": model_name,
                "reason": reason
            }
        )
        self.user_message_de = f"Modell konnte nicht geladen werden: {reason}"


# ==================== Search Exceptions (E019) ====================

class SearchError(AblageSystemException):
    """Base class for search-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E019",
            details=details or {},
            user_message_de="Suchfehler aufgetreten"
        )


class SearchIndexError(SearchError):
    """Search index operation failed"""

    def __init__(self, index_name: str, operation: str, reason: str):
        super().__init__(
            message=f"Search index {operation} failed for {index_name}: {reason}",
            details={
                "index_name": index_name,
                "operation": operation,
                "reason": reason
            }
        )
        self.user_message_de = f"Suchindex-Operation fehlgeschlagen: {reason}"


class SearchQueryError(SearchError):
    """Search query parsing or execution failed"""

    def __init__(self, query: str, reason: str):
        super().__init__(
            message=f"Search query failed: {reason}",
            details={
                "query": query[:100] if query else "",  # Truncate for safety
                "reason": reason
            }
        )
        self.user_message_de = f"Suchanfrage fehlgeschlagen: {reason}"


# ==================== Embedding Exceptions (E020) ====================

class EmbeddingError(AblageSystemException):
    """Base class for embedding-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E020",
            details=details or {},
            user_message_de="Embedding-Fehler aufgetreten"
        )


class EmbeddingGenerationError(EmbeddingError):
    """Embedding generation failed"""

    def __init__(self, document_id: str, reason: str):
        super().__init__(
            message=f"Embedding generation failed for document {document_id}: {reason}",
            details={
                "document_id": document_id,
                "reason": reason
            }
        )
        self.user_message_de = f"Embedding-Erzeugung fehlgeschlagen: {reason}"


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Embedding dimension mismatch"""

    def __init__(self, expected: int, actual: int):
        super().__init__(
            message=f"Embedding dimension mismatch: expected {expected}, got {actual}",
            details={
                "expected_dimension": expected,
                "actual_dimension": actual
            }
        )
        self.user_message_de = f"Embedding-Dimensionen stimmen nicht ueberein"


# ==================== Notification Exceptions (E021) ====================

class NotificationError(AblageSystemException):
    """Base class for notification-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E021",
            details=details or {},
            user_message_de="Benachrichtigungsfehler aufgetreten"
        )


class NotificationDeliveryError(NotificationError):
    """Notification delivery failed"""

    def __init__(self, notification_type: str, recipient: str, reason: str):
        super().__init__(
            message=f"Notification delivery failed to {recipient}: {reason}",
            details={
                "notification_type": notification_type,
                "recipient": recipient,
                "reason": reason
            }
        )
        self.user_message_de = f"Benachrichtigung konnte nicht zugestellt werden: {reason}"


class NotificationConfigError(NotificationError):
    """Notification configuration error"""

    def __init__(self, channel: str, reason: str):
        super().__init__(
            message=f"Notification config error for {channel}: {reason}",
            details={
                "channel": channel,
                "reason": reason
            }
        )
        self.user_message_de = f"Benachrichtigungskonfiguration fehlerhaft: {reason}"


# ==================== Authentication Exceptions (E022) ====================

class AuthenticationError(AblageSystemException):
    """Base class for authentication-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E022",
            details=details or {},
            user_message_de="Authentifizierungsfehler"
        )


class InvalidCredentialsError(AuthenticationError):
    """Invalid username or password"""

    def __init__(self):
        super().__init__(
            message="Invalid credentials provided",
            details={}
        )
        self.user_message_de = "Ungueltige Anmeldedaten"


class TokenExpiredError(AuthenticationError):
    """JWT token has expired"""

    def __init__(self):
        super().__init__(
            message="Token has expired",
            details={}
        )
        self.user_message_de = "Sitzung abgelaufen. Bitte erneut anmelden."


class InsufficientPermissionsError(AuthenticationError):
    """User lacks required permissions"""

    def __init__(self, required_permission: str):
        super().__init__(
            message=f"Insufficient permissions: {required_permission} required",
            details={"required_permission": required_permission}
        )
        self.user_message_de = f"Fehlende Berechtigung: {required_permission}"


# ==================== GoBD/Archive Exceptions (E024) ====================

class ArchiveError(AblageSystemException):
    """Base class for archive-related errors"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E024",
            details=details or {},
            user_message_de="Archivierungsfehler aufgetreten"
        )


class VerificationError(ArchiveError):
    """Document verification failed - integrity compromised"""

    def __init__(self, document_id: str, expected_hash: str, actual_hash: str):
        super().__init__(
            message=f"Document verification failed for {document_id}: hash mismatch",
            details={
                "document_id": document_id,
                "expected_hash": expected_hash[:16] + "...",
                "actual_hash": actual_hash[:16] + "..."
            }
        )
        self.user_message_de = "Dokumentverifikation fehlgeschlagen - Integritaet moeglicherweise kompromittiert"


class ImmutabilityViolationError(ArchiveError):
    """Attempt to modify an archived (immutable) document"""

    def __init__(self, document_id: str):
        super().__init__(
            message=f"Immutability violation: Document {document_id} is archived and cannot be modified",
            details={"document_id": document_id}
        )
        self.user_message_de = "Aenderung nicht moeglich: Dokument ist revisionssicher archiviert (GoBD)"


class RetentionPolicyError(ArchiveError):
    """Retention policy violation"""

    def __init__(self, document_id: str, retention_expires_at: str, reason: str):
        super().__init__(
            message=f"Retention policy violation for {document_id}: {reason}",
            details={
                "document_id": document_id,
                "retention_expires_at": retention_expires_at,
                "reason": reason
            }
        )
        self.user_message_de = f"Aufbewahrungsfrist-Verletzung: {reason}"


# ==================== Rate Limiting Exceptions (E023) ====================

class RateLimitError(AblageSystemException):
    """Base class for rate limiting errors"""

    def __init__(self, message: str, retry_after: int, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="E023",
            details={**(details or {}), "retry_after_seconds": retry_after},
            user_message_de=f"Ratenlimit erreicht. Bitte in {retry_after} Sekunden erneut versuchen."
        )
        self.retry_after = retry_after


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
    "E010": "Backend Selection Failed",
    "E011": "GDPR Operation Error",
    "E012": "User Not Found",
    "E013": "Data Export Error",
    "E014": "Email Verification Error",
    "E015": "Storage Error (MinIO/S3)",
    "E016": "Webhook Error",
    "E017": "Backup Error",
    "E018": "ML/AI Processing Error",
    "E019": "Search Error",
    "E020": "Embedding Error",
    "E021": "Notification Error",
    "E022": "Authentication Error",
    "E023": "Rate Limit Exceeded",
    "E024": "GoBD Archive Error",
}


def get_error_description(error_code: str) -> str:
    """Get human-readable error description"""
    return ERROR_CODE_REGISTRY.get(error_code, "Unknown Error")
