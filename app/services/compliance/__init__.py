"""GoBD & GDPR Compliance Services.

Dieses Modul stellt Services für GoBD- und DSGVO-konforme Dokumentenverarbeitung bereit:
- AuditChainService: Blockchain-ähnliche Hash-Kette
- RetentionService: Aufbewahrungsfristen-Management
- ArchiveService: Revisionssichere Archivierung mit TSA
- ConsentManagementService: DSGVO Einwilligungsverwaltung (Phase 7)

GoBD = Grundsätze zur ordnungsmaessigen Führung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff

DSGVO = Datenschutz-Grundverordnung (Art. 6, 7, 15-21)
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
from app.services.compliance.consent_management_service import (
    ConsentManagementService,
    consent_management_service,
    get_consent_management_service,
    ConsentScope,
    ConsentMethod,
    ConsentStatus,
    ConsentHistoryAction,
    ConsentRecord,
    ConsentVersionInfo,
    ConsentGrantResult,
    ConsentWithdrawalResult,
    ConsentCheckResult,
    ConsentHistoryEntry,
    ConsentSummary,
)
from app.services.compliance.data_subject_rights_service import (
    DataSubjectRightsService,
    data_subject_rights_service,
    get_data_subject_rights_service,
    DSRType,
    DSRStatus,
    DataCategory,
    DSRRequest,
    DSRCreateResult,
    DSRVerificationResult,
    PersonalDataExport,
    PersonalDataSummary,
    ErasureResult,
    RectificationResult,
)
from app.services.compliance.audit_archive_service import (
    AuditArchiveService,
    audit_archive_service,
    archive_monthly_audit_logs,
    verify_all_archives,
    ArchiveStatus,
    ArchiveResult,
    ArchiveVerificationResult,
)
from app.services.compliance.breach_notification_service import (
    BreachNotificationService,
    breach_notification_service,
    get_breach_notification_service,
    BreachSeverity,
    BreachType,
    BreachStatus,
    NotificationStatus,
    BreachReport,
    AffectedDataCategory,
    AuthorityNotificationTemplate,
    SubjectNotificationTemplate,
    CreateBreachResult,
    SUPERVISORY_AUTHORITIES,
)
from app.services.compliance.tax_authority_export_service import (
    TaxAuthorityExportService,
    get_tax_authority_export_service,
    ExportFormat,
    DataCategory as TaxDataCategory,
    ExportField,
    ExportTable,
    ExportStatistics,
    ExportResult,
    get_invoice_table_definition,
    get_bank_transaction_table_definition,
    get_document_table_definition,
    get_audit_log_table_definition,
    ENCODING,
    MAX_FIELD_LENGTH,
    GDPDU_NAMESPACE,
)
from app.services.compliance.document_completeness_service import (
    DocumentCompletenessService,
    document_completeness_service,
)
from app.services.compliance.gobd_service import (
    GoBDComplianceService,
    gobd_compliance_service,
    CheckResult,
    ComplianceDashboard,
    RemediationAction,
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
    # GDPR Consent Management (Phase 7)
    "ConsentManagementService",
    "consent_management_service",
    "get_consent_management_service",
    "ConsentScope",
    "ConsentMethod",
    "ConsentStatus",
    "ConsentHistoryAction",
    "ConsentRecord",
    "ConsentVersionInfo",
    "ConsentGrantResult",
    "ConsentWithdrawalResult",
    "ConsentCheckResult",
    "ConsentHistoryEntry",
    "ConsentSummary",
    # GDPR Data Subject Rights (Phase 7)
    "DataSubjectRightsService",
    "data_subject_rights_service",
    "get_data_subject_rights_service",
    "DSRType",
    "DSRStatus",
    "DataCategory",
    "DSRRequest",
    "DSRCreateResult",
    "DSRVerificationResult",
    "PersonalDataExport",
    "ErasureResult",
    "RectificationResult",
    # Audit Archive (Phase 1.4)
    "AuditArchiveService",
    "audit_archive_service",
    "archive_monthly_audit_logs",
    "verify_all_archives",
    "ArchiveStatus",
    "ArchiveResult",
    "ArchiveVerificationResult",
    # GDPR Breach Notification (Art. 33-34)
    "BreachNotificationService",
    "breach_notification_service",
    "get_breach_notification_service",
    "BreachSeverity",
    "BreachType",
    "BreachStatus",
    "NotificationStatus",
    "BreachReport",
    "AffectedDataCategory",
    "AuthorityNotificationTemplate",
    "SubjectNotificationTemplate",
    "CreateBreachResult",
    "SUPERVISORY_AUTHORITIES",
    # Tax Authority Export (§90 III AO)
    "TaxAuthorityExportService",
    "get_tax_authority_export_service",
    "ExportFormat",
    "TaxDataCategory",
    "ExportField",
    "ExportTable",
    "ExportStatistics",
    "ExportResult",
    "get_invoice_table_definition",
    "get_bank_transaction_table_definition",
    "get_document_table_definition",
    "get_audit_log_table_definition",
    "ENCODING",
    "MAX_FIELD_LENGTH",
    "GDPDU_NAMESPACE",
    # Document Completeness
    "DocumentCompletenessService",
    "document_completeness_service",
    # GoBD Compliance Checks (Vision 2026)
    "GoBDComplianceService",
    "gobd_compliance_service",
    "CheckResult",
    "ComplianceDashboard",
    "RemediationAction",
]
