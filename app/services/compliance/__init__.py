"""GoBD Compliance Services.

Dieses Modul stellt Services fuer GoBD-konforme Dokumentenverarbeitung bereit:
- AuditChainService: Blockchain-aehnliche Hash-Kette
- RetentionService: Aufbewahrungsfristen-Management
- ArchiveService: Revisionssichere Archivierung mit TSA

GoBD = Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff
"""

from app.services.compliance.audit_chain_service import (
    AuditChainService,
    audit_chain_service,
)
from app.services.compliance.retention_service import (
    RetentionService,
    retention_service,
)
from app.services.compliance.archive_service import (
    GoBDArchiveService,
    gobd_archive_service,
)
from app.services.compliance.tsa_service import (
    TimestampAuthorityService,
    tsa_service,
    timestamp_document,
    timestamp_audit_chain_entry,
    TSAStatus,
    TimestampRequest,
    TimestampResponse,
)
from app.services.compliance.procedure_documentation_service import (
    ProcedureDocumentationService,
    procedure_documentation_service,
    generate_procedure_documentation,
    DocumentFormat,
    DocumentSection,
    ProcedureDocumentation,
)

__all__ = [
    # Audit Chain
    "AuditChainService",
    "audit_chain_service",
    # Retention
    "RetentionService",
    "retention_service",
    # Archive
    "GoBDArchiveService",
    "gobd_archive_service",
    # TSA (RFC 3161 Timestamps)
    "TimestampAuthorityService",
    "tsa_service",
    "timestamp_document",
    "timestamp_audit_chain_entry",
    "TSAStatus",
    "TimestampRequest",
    "TimestampResponse",
    # Procedure Documentation
    "ProcedureDocumentationService",
    "procedure_documentation_service",
    "generate_procedure_documentation",
    "DocumentFormat",
    "DocumentSection",
    "ProcedureDocumentation",
]
