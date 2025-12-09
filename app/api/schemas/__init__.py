"""
API Response Schemas.

Standardisierte Schemas für konsistente API-Antworten.
"""

from app.api.schemas.responses import (
    ErrorResponse,
    ValidationErrorResponse,
    ValidationErrorDetail,
    SuccessResponse,
    PaginatedResponse,
    HealthResponse,
    OCRResultResponse,
    COMMON_RESPONSES,
    ERROR_CODES,
)

from app.api.schemas.extracted_data import (
    # Enums
    ExtractedDocumentType,
    Currency,
    # Basismodelle
    ExtractedAddress,
    ExtractedBankAccount,
    ExtractedLineItem,
    # Dokumenttypen
    ExtractedInvoiceData,
    ExtractedOrderData,
    ExtractedContractData,
    # Klassifizierung
    DocumentClassificationResult,
    # Wrapper
    ExtractedDocumentData,
)

__all__ = [
    # Response Schemas
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "SuccessResponse",
    "PaginatedResponse",
    "HealthResponse",
    "OCRResultResponse",
    "COMMON_RESPONSES",
    "ERROR_CODES",
    # Extracted Data Schemas
    "ExtractedDocumentType",
    "Currency",
    "ExtractedAddress",
    "ExtractedBankAccount",
    "ExtractedLineItem",
    "ExtractedInvoiceData",
    "ExtractedOrderData",
    "ExtractedContractData",
    "DocumentClassificationResult",
    "ExtractedDocumentData",
]
