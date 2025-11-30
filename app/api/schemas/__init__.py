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

__all__ = [
    "ErrorResponse",
    "ValidationErrorResponse",
    "ValidationErrorDetail",
    "SuccessResponse",
    "PaginatedResponse",
    "HealthResponse",
    "OCRResultResponse",
    "COMMON_RESPONSES",
    "ERROR_CODES",
]
