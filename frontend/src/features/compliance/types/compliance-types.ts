/**
 * Compliance Cockpit Types
 *
 * TypeScript Definitionen für das Compliance Cockpit System (GoBD, GDPR, Retention, Audit).
 */

// ============================================================================
// ENUMS
// ============================================================================

export type ComplianceStatus = 'compliant' | 'warning' | 'non_compliant' | 'unknown';
export type CheckStatus = 'passed' | 'warning' | 'failed';
export type CheckCategory =
  | 'gobd'
  | 'gdpr'
  | 'retention'
  | 'audit_trail'
  | 'archival'
  | 'access_control'
  | 'data_protection';

export type RetentionDocumentType =
  | 'invoice'
  | 'receipt'
  | 'contract'
  | 'tax_document'
  | 'payroll'
  | 'other';

export type AuditEventType =
  | 'create'
  | 'read'
  | 'update'
  | 'delete'
  | 'archive'
  | 'restore'
  | 'share'
  | 'export';

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case)
// ============================================================================

export interface ComplianceReportResponse {
  report_id: string;
  company_id: number;
  report_date: string; // ISO date
  generated_at: string; // ISO datetime
  overall_status: ComplianceStatus;
  overall_score: number; // 0-100
  score_description: string; // "Sehr gut" | "Gut" | "Befriedigend" | "Mangelhaft"
  summary: string;
  recommendations: string[];
  legal_basis: string[];
  details: {
    gobd_compliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    gdpr_compliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    retention_compliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    audit_trail_health: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
  };
}

export interface QuickComplianceStatusResponse {
  overall_status: ComplianceStatus;
  overall_score: number;
  last_check: string; // ISO datetime
  critical_issues_count: number;
  warnings_count: number;
}

export interface ComplianceScanResultResponse {
  scan_id: string;
  timestamp: string; // ISO datetime
  total_checks: number;
  passed: number;
  warnings: number;
  failures: number;
  score: number; // 0-100
  items: ComplianceScanItemResponse[];
}

export interface ComplianceScanItemResponse {
  check_name: string;
  category: CheckCategory;
  status: CheckStatus;
  description: string;
  recommendation: string;
  details: Record<string, unknown>;
}

export interface RetentionReportResponse {
  documents_total: number;
  documents_expired: number;
  documents_expiring_soon: number;
  expired_document_ids: number[];
  expiring_soon_ids: number[];
  retention_by_type: Record<RetentionDocumentType, {
    total: number;
    expired: number;
    expiring_soon: number;
  }>;
}

export interface RetentionAlertResponse {
  alert_id: string;
  document_id: number;
  document_name: string;
  retention_type: RetentionDocumentType;
  expiry_date: string; // ISO date
  days_until_expiry: number;
  severity: 'low' | 'medium' | 'high';
}

export interface RetentionStatsResponse {
  total_documents: number;
  documents_with_retention: number;
  documents_expired: number;
  documents_expiring_soon: number;
  average_retention_days: number;
  retention_by_type: Record<RetentionDocumentType, number>;
}

export interface RetentionPolicyResponse {
  policy_id: string;
  document_type: RetentionDocumentType;
  retention_period_days: number;
  description: string;
  legal_basis: string;
  created_at: string;
  updated_at: string;
}

export interface AuditChainStatsResponse {
  total_entries: number;
  entries_last_24h: number;
  entries_last_7d: number;
  unverified_entries: number;
  chain_integrity: boolean;
  last_verification: string; // ISO datetime
  events_by_type: Record<AuditEventType, number>;
}

export interface AuditChainEntryResponse {
  entry_id: string;
  timestamp: string;
  event_type: AuditEventType;
  document_id: number | null;
  user_id: number;
  user_email: string;
  action: string;
  details: Record<string, unknown>;
  hash: string;
  previous_hash: string | null;
  verified: boolean;
}

export interface GdprCheckResponse {
  compliant: boolean;
  issues: string[];
  recommendations: string[];
  personal_data_count: number;
  deletion_candidates: number;
  details: {
    data_minimization: {
      status: ComplianceStatus;
      findings: string[];
    };
    consent_management: {
      status: ComplianceStatus;
      findings: string[];
    };
    access_rights: {
      status: ComplianceStatus;
      findings: string[];
    };
    data_portability: {
      status: ComplianceStatus;
      findings: string[];
    };
  };
}

export interface ProcedureDocumentationResponse {
  documentation_id: string;
  company_id: number;
  generated_at: string;
  version: string;
  sections: {
    overview: string;
    system_description: string;
    data_processing: string;
    access_control: string;
    archival_process: string;
    data_protection: string;
  };
}

// ============================================================================
// FRONTEND TYPES (camelCase)
// ============================================================================

export interface ComplianceReport {
  reportId: string;
  companyId: number;
  reportDate: Date;
  generatedAt: Date;
  overallStatus: ComplianceStatus;
  overallScore: number;
  scoreDescription: string;
  summary: string;
  recommendations: string[];
  legalBasis: string[];
  details: {
    gobdCompliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    gdprCompliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    retentionCompliance: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
    auditTrailHealth: {
      status: ComplianceStatus;
      score: number;
      findings: string[];
    };
  };
}

export interface QuickComplianceStatus {
  overallStatus: ComplianceStatus;
  overallScore: number;
  lastCheck: Date;
  criticalIssuesCount: number;
  warningsCount: number;
}

export interface ComplianceScanResult {
  scanId: string;
  timestamp: Date;
  totalChecks: number;
  passed: number;
  warnings: number;
  failures: number;
  score: number;
  items: ComplianceScanItem[];
}

export interface ComplianceScanItem {
  checkName: string;
  category: CheckCategory;
  status: CheckStatus;
  description: string;
  recommendation: string;
  details: Record<string, unknown>;
}

export interface RetentionReport {
  documentsTotal: number;
  documentsExpired: number;
  documentsExpiringSoon: number;
  expiredDocumentIds: number[];
  expiringSoonIds: number[];
  retentionByType: Record<RetentionDocumentType, {
    total: number;
    expired: number;
    expiringSoon: number;
  }>;
}

export interface RetentionAlert {
  alertId: string;
  documentId: number;
  documentName: string;
  retentionType: RetentionDocumentType;
  expiryDate: Date;
  daysUntilExpiry: number;
  severity: 'low' | 'medium' | 'high';
}

export interface RetentionStats {
  totalDocuments: number;
  documentsWithRetention: number;
  documentsExpired: number;
  documentsExpiringSoon: number;
  averageRetentionDays: number;
  retentionByType: Record<RetentionDocumentType, number>;
}

export interface RetentionPolicy {
  policyId: string;
  documentType: RetentionDocumentType;
  retentionPeriodDays: number;
  description: string;
  legalBasis: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface AuditChainStats {
  totalEntries: number;
  entriesLast24h: number;
  entriesLast7d: number;
  unverifiedEntries: number;
  chainIntegrity: boolean;
  lastVerification: Date;
  eventsByType: Record<AuditEventType, number>;
}

export interface AuditChainEntry {
  entryId: string;
  timestamp: Date;
  eventType: AuditEventType;
  documentId: number | null;
  userId: number;
  userEmail: string;
  action: string;
  details: Record<string, unknown>;
  hash: string;
  previousHash: string | null;
  verified: boolean;
}

export interface GdprCheck {
  compliant: boolean;
  issues: string[];
  recommendations: string[];
  personalDataCount: number;
  deletionCandidates: number;
  details: {
    dataMinimization: {
      status: ComplianceStatus;
      findings: string[];
    };
    consentManagement: {
      status: ComplianceStatus;
      findings: string[];
    };
    accessRights: {
      status: ComplianceStatus;
      findings: string[];
    };
    dataPortability: {
      status: ComplianceStatus;
      findings: string[];
    };
  };
}

export interface ProcedureDocumentation {
  documentationId: string;
  companyId: number;
  generatedAt: Date;
  version: string;
  sections: {
    overview: string;
    systemDescription: string;
    dataProcessing: string;
    accessControl: string;
    archivalProcess: string;
    dataProtection: string;
  };
}

// ============================================================================
// TRANSFORMER FUNCTIONS
// ============================================================================

export function transformComplianceReport(response: ComplianceReportResponse): ComplianceReport {
  return {
    reportId: response.report_id,
    companyId: response.company_id,
    reportDate: new Date(response.report_date),
    generatedAt: new Date(response.generated_at),
    overallStatus: response.overall_status,
    overallScore: response.overall_score,
    scoreDescription: response.score_description,
    summary: response.summary,
    recommendations: response.recommendations,
    legalBasis: response.legal_basis,
    details: {
      gobdCompliance: {
        status: response.details.gobd_compliance.status,
        score: response.details.gobd_compliance.score,
        findings: response.details.gobd_compliance.findings,
      },
      gdprCompliance: {
        status: response.details.gdpr_compliance.status,
        score: response.details.gdpr_compliance.score,
        findings: response.details.gdpr_compliance.findings,
      },
      retentionCompliance: {
        status: response.details.retention_compliance.status,
        score: response.details.retention_compliance.score,
        findings: response.details.retention_compliance.findings,
      },
      auditTrailHealth: {
        status: response.details.audit_trail_health.status,
        score: response.details.audit_trail_health.score,
        findings: response.details.audit_trail_health.findings,
      },
    },
  };
}

export function transformQuickComplianceStatus(
  response: QuickComplianceStatusResponse
): QuickComplianceStatus {
  return {
    overallStatus: response.overall_status,
    overallScore: response.overall_score,
    lastCheck: new Date(response.last_check),
    criticalIssuesCount: response.critical_issues_count,
    warningsCount: response.warnings_count,
  };
}

export function transformComplianceScanResult(
  response: ComplianceScanResultResponse
): ComplianceScanResult {
  return {
    scanId: response.scan_id,
    timestamp: new Date(response.timestamp),
    totalChecks: response.total_checks,
    passed: response.passed,
    warnings: response.warnings,
    failures: response.failures,
    score: response.score,
    items: response.items.map(transformComplianceScanItem),
  };
}

export function transformComplianceScanItem(
  response: ComplianceScanItemResponse
): ComplianceScanItem {
  return {
    checkName: response.check_name,
    category: response.category,
    status: response.status,
    description: response.description,
    recommendation: response.recommendation,
    details: response.details,
  };
}

export function transformRetentionReport(response: RetentionReportResponse): RetentionReport {
  return {
    documentsTotal: response.documents_total,
    documentsExpired: response.documents_expired,
    documentsExpiringSoon: response.documents_expiring_soon,
    expiredDocumentIds: response.expired_document_ids,
    expiringSoonIds: response.expiring_soon_ids,
    retentionByType: Object.fromEntries(
      Object.entries(response.retention_by_type).map(([key, value]) => [
        key,
        { total: value.total, expired: value.expired, expiringSoon: value.expiring_soon },
      ])
    ) as RetentionStats['retentionByType'],
  };
}

export function transformRetentionAlert(response: RetentionAlertResponse): RetentionAlert {
  return {
    alertId: response.alert_id,
    documentId: response.document_id,
    documentName: response.document_name,
    retentionType: response.retention_type,
    expiryDate: new Date(response.expiry_date),
    daysUntilExpiry: response.days_until_expiry,
    severity: response.severity,
  };
}

export function transformRetentionStats(response: RetentionStatsResponse): RetentionStats {
  return {
    totalDocuments: response.total_documents,
    documentsWithRetention: response.documents_with_retention,
    documentsExpired: response.documents_expired,
    documentsExpiringSoon: response.documents_expiring_soon,
    averageRetentionDays: response.average_retention_days,
    retentionByType: Object.fromEntries(
      Object.entries(response.retention_by_type).map(([key, value]) => [
        key,
        { total: value.total, expired: value.expired, expiringSoon: value.expiring_soon },
      ])
    ) as RetentionStats['retentionByType'],
  };
}

export function transformRetentionPolicy(response: RetentionPolicyResponse): RetentionPolicy {
  return {
    policyId: response.policy_id,
    documentType: response.document_type,
    retentionPeriodDays: response.retention_period_days,
    description: response.description,
    legalBasis: response.legal_basis,
    createdAt: new Date(response.created_at),
    updatedAt: new Date(response.updated_at),
  };
}

export function transformAuditChainStats(response: AuditChainStatsResponse): AuditChainStats {
  return {
    totalEntries: response.total_entries,
    entriesLast24h: response.entries_last_24h,
    entriesLast7d: response.entries_last_7d,
    unverifiedEntries: response.unverified_entries,
    chainIntegrity: response.chain_integrity,
    lastVerification: new Date(response.last_verification),
    eventsByType: response.events_by_type,
  };
}

export function transformAuditChainEntry(response: AuditChainEntryResponse): AuditChainEntry {
  return {
    entryId: response.entry_id,
    timestamp: new Date(response.timestamp),
    eventType: response.event_type,
    documentId: response.document_id,
    userId: response.user_id,
    userEmail: response.user_email,
    action: response.action,
    details: response.details,
    hash: response.hash,
    previousHash: response.previous_hash,
    verified: response.verified,
  };
}

export function transformGdprCheck(response: GdprCheckResponse): GdprCheck {
  return {
    compliant: response.compliant,
    issues: response.issues,
    recommendations: response.recommendations,
    personalDataCount: response.personal_data_count,
    deletionCandidates: response.deletion_candidates,
    details: {
      dataMinimization: {
        status: response.details.data_minimization.status,
        findings: response.details.data_minimization.findings,
      },
      consentManagement: {
        status: response.details.consent_management.status,
        findings: response.details.consent_management.findings,
      },
      accessRights: {
        status: response.details.access_rights.status,
        findings: response.details.access_rights.findings,
      },
      dataPortability: {
        status: response.details.data_portability.status,
        findings: response.details.data_portability.findings,
      },
    },
  };
}

export function transformProcedureDocumentation(
  response: ProcedureDocumentationResponse
): ProcedureDocumentation {
  return {
    documentationId: response.documentation_id,
    companyId: response.company_id,
    generatedAt: new Date(response.generated_at),
    version: response.version,
    sections: {
      overview: response.sections.overview,
      systemDescription: response.sections.system_description,
      dataProcessing: response.sections.data_processing,
      accessControl: response.sections.access_control,
      archivalProcess: response.sections.archival_process,
      dataProtection: response.sections.data_protection,
    },
  };
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

export function getComplianceStatusColor(status: ComplianceStatus): string {
  switch (status) {
    case 'compliant':
      return 'text-green-600';
    case 'warning':
      return 'text-yellow-600';
    case 'non_compliant':
      return 'text-red-600';
    case 'unknown':
    default:
      return 'text-gray-600';
  }
}

export function getComplianceStatusBadgeVariant(
  status: ComplianceStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'compliant':
      return 'default';
    case 'warning':
      return 'secondary';
    case 'non_compliant':
      return 'destructive';
    case 'unknown':
    default:
      return 'outline';
  }
}

export function getCheckStatusColor(status: CheckStatus): string {
  switch (status) {
    case 'passed':
      return 'text-green-600';
    case 'warning':
      return 'text-yellow-600';
    case 'failed':
      return 'text-red-600';
    default:
      return 'text-gray-600';
  }
}

export function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

export function getScoreBackgroundColor(score: number): string {
  if (score >= 80) return 'bg-green-50';
  if (score >= 60) return 'bg-yellow-50';
  return 'bg-red-50';
}

export function getCategoryLabel(category: CheckCategory): string {
  const labels: Record<CheckCategory, string> = {
    gobd: 'GoBD',
    gdpr: 'DSGVO',
    retention: 'Aufbewahrung',
    audit_trail: 'Audit-Trail',
    archival: 'Archivierung',
    access_control: 'Zugriffskontrolle',
    data_protection: 'Datenschutz',
  };
  return labels[category] || category;
}

export function getRetentionTypeLabel(type: RetentionDocumentType): string {
  const labels: Record<RetentionDocumentType, string> = {
    invoice: 'Rechnung',
    receipt: 'Beleg',
    contract: 'Vertrag',
    tax_document: 'Steuerdokument',
    payroll: 'Lohnabrechnung',
    other: 'Sonstige',
  };
  return labels[type] || type;
}
