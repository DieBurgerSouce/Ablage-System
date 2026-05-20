"""DEPRECATED: Verwende app.services.document_services.export_service stattdessen.

Dieser Wrapper existiert für Rückwärtskompatibilität und wird in einer zukünftigen
Version entfernt.

Migration:
    ALT:  from app.services.document_export_service import DocumentExportService
    NEU:  from app.services.document_services.export_service import DocumentExportService
"""

import warnings

# Re-export from consolidated module for backwards compatibility
from app.services.document_services.export_service import (
    DocumentExportService,
    get_export_service,
)

# Deprecation warning on import
warnings.warn(
    "document_export_service ist deprecated. "
    "Verwende stattdessen: from app.services.document_services.export_service import DocumentExportService",
    DeprecationWarning,
    stacklevel=2
)


def get_document_export_service() -> DocumentExportService:
    """DEPRECATED: Verwende get_export_service() stattdessen."""
    warnings.warn(
        "get_document_export_service() ist deprecated. "
        "Verwende stattdessen: get_export_service()",
        DeprecationWarning,
        stacklevel=2
    )
    return get_export_service()


__all__ = ["DocumentExportService", "get_document_export_service"]
