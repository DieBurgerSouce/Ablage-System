"""DEPRECATED: Verwende app.services.document_services.batch_service stattdessen.

Dieser Wrapper existiert für Rückwärtskompatibilität und wird in einer zukünftigen
Version entfernt.

Migration:
    ALT:  from app.services.document_batch_service import DocumentBatchService
    NEU:  from app.services.document_services.batch_service import DocumentBatchService

    ALT:  from app.services.document_batch_service import get_document_batch_service
    NEU:  from app.services.document_services.batch_service import get_batch_service
"""

import warnings

# Re-export from consolidated module for backwards compatibility
from app.services.document_services.batch_service import (
    DocumentBatchService,
    get_batch_service,
)

# Deprecation warning on import
warnings.warn(
    "document_batch_service ist deprecated. "
    "Verwende stattdessen: from app.services.document_services.batch_service import DocumentBatchService",
    DeprecationWarning,
    stacklevel=2
)


def get_document_batch_service() -> DocumentBatchService:
    """DEPRECATED: Verwende get_batch_service() stattdessen."""
    warnings.warn(
        "get_document_batch_service() ist deprecated. "
        "Verwende stattdessen: get_batch_service()",
        DeprecationWarning,
        stacklevel=2
    )
    return get_batch_service()


__all__ = ["DocumentBatchService", "get_document_batch_service"]
