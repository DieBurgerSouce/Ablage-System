"""DEPRECATED: Verwende app.services.document_services.gdpr_service stattdessen.

Dieser Wrapper existiert für Rückwärtskompatibilität und wird in einer zukünftigen
Version entfernt.

Migration:
    ALT:  from app.services.document_gdpr_service import DocumentGDPRService
    NEU:  from app.services.document_services.gdpr_service import DocumentGDPRService
"""

import warnings

# Re-export from consolidated module for backwards compatibility
from app.services.document_services.gdpr_service import (
    DocumentGDPRService,
    get_gdpr_service,
)

# Deprecation warning on import
warnings.warn(
    "document_gdpr_service ist deprecated. "
    "Verwende stattdessen: from app.services.document_services.gdpr_service import DocumentGDPRService",
    DeprecationWarning,
    stacklevel=2
)


def get_document_gdpr_service() -> DocumentGDPRService:
    """DEPRECATED: Verwende get_gdpr_service() stattdessen."""
    warnings.warn(
        "get_document_gdpr_service() ist deprecated. "
        "Verwende stattdessen: get_gdpr_service()",
        DeprecationWarning,
        stacklevel=2
    )
    return get_gdpr_service()


__all__ = ["DocumentGDPRService", "get_document_gdpr_service"]
