"""
Data Loss Prevention (DLP) Services.

Schuetzt sensible Dokumente durch:
- Zugriffskontrolle basierend auf Policies
- Automatische Wasserzeichen
- Erkennung sensibler Daten
- Audit-Logging
"""

from app.services.dlp.dlp_service import (
    DLPService,
    DLPServiceError,
    DLPAccessDeniedError,
    DLPAction,
    DLPPolicy,
    DLPCheckResult,
    SensitiveDataType,
    WatermarkConfig,
    WatermarkPosition,
    get_dlp_service,
)

__all__ = [
    "DLPService",
    "DLPServiceError",
    "DLPAccessDeniedError",
    "DLPAction",
    "DLPPolicy",
    "DLPCheckResult",
    "SensitiveDataType",
    "WatermarkConfig",
    "WatermarkPosition",
    "get_dlp_service",
]
