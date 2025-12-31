# -*- coding: utf-8 -*-
"""
Custom exceptions for Streckengeschaeft (Drop Shipment) module.

Enterprise-grade exception hierarchy for:
- Clear error categorization
- German user-facing messages
- Structured error codes for API responses
- Proper exception chaining

Feinpoliert und durchdacht.
"""

from typing import Optional


class DropShipmentError(Exception):
    """Base exception for all Streckengeschaeft operations.

    Attributes:
        message: Technical error message (English, for logs)
        error_code: Machine-readable error code
        user_message: User-facing message (German)
        details: Additional context for debugging
    """

    def __init__(
        self,
        message: str,
        error_code: str = "DROPSHIP_ERROR",
        user_message: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.user_message = user_message or message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        """Convert exception to API response format."""
        return {
            "error_code": self.error_code,
            "message": self.user_message,
            "details": self.details,
        }


class ClassificationNotFoundError(DropShipmentError):
    """Raised when a classification cannot be found."""

    def __init__(self, classification_id: Optional[str] = None):
        details = {"classification_id": classification_id} if classification_id else {}
        super().__init__(
            message=f"Classification not found: {classification_id}",
            error_code="CLASSIFICATION_NOT_FOUND",
            user_message="Klassifikation nicht gefunden",
            details=details,
        )


class DocumentNotFoundError(DropShipmentError):
    """Raised when a document cannot be found."""

    def __init__(self, document_id: Optional[str] = None):
        details = {"document_id": document_id} if document_id else {}
        super().__init__(
            message=f"Document not found: {document_id}",
            error_code="DOCUMENT_NOT_FOUND",
            user_message="Dokument nicht gefunden",
            details=details,
        )


class AccessDeniedError(DropShipmentError):
    """Raised when user lacks permission to access a resource."""

    def __init__(self, resource_type: str = "resource", resource_id: Optional[str] = None):
        details = {"resource_type": resource_type}
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(
            message=f"Access denied to {resource_type}: {resource_id}",
            error_code="ACCESS_DENIED",
            user_message="Zugriff verweigert",
            details=details,
        )


class ValidationConflictError(DropShipmentError):
    """Raised when optimistic locking detects concurrent modification."""

    def __init__(self, classification_id: Optional[str] = None):
        details = {"classification_id": classification_id} if classification_id else {}
        super().__init__(
            message=f"Concurrent modification detected for classification: {classification_id}",
            error_code="CONCURRENT_MODIFICATION",
            user_message="Klassifikation wurde zwischenzeitlich geaendert. Bitte Seite neu laden.",
            details=details,
        )


class DatevExportError(DropShipmentError):
    """Raised when DATEV export fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=f"DATEV export failed: {message}",
            error_code="DATEV_EXPORT_FAILED",
            user_message=f"DATEV-Export fehlgeschlagen: {message}",
            details=details or {},
        )


class ViesServiceError(DropShipmentError):
    """Raised when VIES VAT ID validation service is unavailable."""

    def __init__(self, vat_id: Optional[str] = None, original_error: Optional[str] = None):
        details = {}
        if vat_id:
            details["vat_id"] = vat_id
        if original_error:
            details["original_error"] = original_error
        super().__init__(
            message=f"VIES service unavailable for VAT ID: {vat_id}",
            error_code="VIES_SERVICE_UNAVAILABLE",
            user_message="USt-IdNr.-Validierungsdienst nicht erreichbar. Bitte spaeter erneut versuchen.",
            details=details,
        )


class InvalidVatIdError(DropShipmentError):
    """Raised when VAT ID format is invalid."""

    def __init__(self, vat_id: str, reason: Optional[str] = None):
        details = {"vat_id": vat_id}
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"Invalid VAT ID format: {vat_id}",
            error_code="INVALID_VAT_ID",
            user_message=f"Ungueltiges USt-IdNr.-Format: {vat_id}",
            details=details,
        )


class BulkOperationError(DropShipmentError):
    """Raised when bulk operation partially or fully fails."""

    def __init__(
        self,
        total: int,
        successful: int,
        failed: int,
        errors: Optional[list] = None,
    ):
        details = {
            "total": total,
            "successful": successful,
            "failed": failed,
            "errors": errors or [],
        }
        super().__init__(
            message=f"Bulk operation partially failed: {failed}/{total} items failed",
            error_code="BULK_OPERATION_PARTIAL_FAILURE",
            user_message=f"Massenoperation teilweise fehlgeschlagen: {failed} von {total} Dokumenten konnten nicht verarbeitet werden",
            details=details,
        )


class ClassificationAlreadyExistsError(DropShipmentError):
    """Raised when trying to create classification for already classified document."""

    def __init__(self, document_id: str, existing_classification_id: str):
        details = {
            "document_id": document_id,
            "existing_classification_id": existing_classification_id,
        }
        super().__init__(
            message=f"Document {document_id} already has classification {existing_classification_id}",
            error_code="CLASSIFICATION_ALREADY_EXISTS",
            user_message="Dokument wurde bereits klassifiziert. Verwenden Sie force_reclassify=true um erneut zu klassifizieren.",
            details=details,
        )


class ProofDocumentError(DropShipmentError):
    """Raised when proof document operation fails."""

    def __init__(self, message: str, proof_id: Optional[str] = None, classification_id: Optional[str] = None):
        details = {}
        if proof_id:
            details["proof_id"] = proof_id
        if classification_id:
            details["classification_id"] = classification_id
        super().__init__(
            message=f"Proof document error: {message}",
            error_code="PROOF_DOCUMENT_ERROR",
            user_message=f"Fehler bei Belegdokument: {message}",
            details=details,
        )


class RateLimitExceededError(DropShipmentError):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, window_seconds: int, retry_after: int):
        details = {
            "limit": limit,
            "window_seconds": window_seconds,
            "retry_after": retry_after,
        }
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            error_code="RATE_LIMIT_EXCEEDED",
            user_message=f"Anfragelimit ueberschritten. Bitte warten Sie {retry_after} Sekunden.",
            details=details,
        )
