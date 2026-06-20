/**
 * Compliance Cockpit API Layer
 *
 * API-Funktionen für das Compliance Cockpit System.
 */

import { apiClient } from '@/lib/api/client';
import type {
  ComplianceReportResponse,
  QuickComplianceStatusResponse,
  ComplianceScanResultResponse,
  RetentionReportResponse,
  RetentionAlertResponse,
  RetentionStatsResponse,
  RetentionPolicyResponse,
  AuditChainStatsResponse,
  AuditChainEntryResponse,
  GdprCheckResponse,
  ProcedureDocumentationResponse,
  ComplianceReport,
  QuickComplianceStatus,
  ComplianceScanResult,
  RetentionReport,
  RetentionAlert,
  RetentionStats,
  RetentionPolicy,
  AuditChainStats,
  AuditChainEntry,
  GdprCheck,
  ProcedureDocumentation,
  RetentionDocumentType,
} from '../types/compliance-types';
import {
  transformComplianceReport,
  transformQuickComplianceStatus,
  transformComplianceScanResult,
  transformRetentionReport,
  transformRetentionAlert,
  transformRetentionStats,
  transformRetentionPolicy,
  transformAuditChainStats,
  transformAuditChainEntry,
  transformGdprCheck,
  transformProcedureDocumentation,
} from '../types/compliance-types';

// Error class for Compliance API
export class ComplianceApiError extends Error {
  status?: number;
  code?: string;

  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = 'ComplianceApiError';
    this.status = status;
    this.code = code;
  }
}

// Pagination parameters
export interface PaginationParams {
  page?: number;
  per_page?: number;
}

// Paginated response wrapper
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

/**
 * Compliance Service
 */
export const complianceService = {
  /**
   * Get full GoBD compliance report with score 0-100
   */
  async getComplianceReport(): Promise<ComplianceReport> {
    const response = await apiClient.get<ComplianceReportResponse>('/compliance/report');
    return transformComplianceReport(response.data);
  },

  /**
   * Get quick compliance status for dashboard widget
   */
  async getQuickComplianceStatus(): Promise<QuickComplianceStatus> {
    const response = await apiClient.get<QuickComplianceStatusResponse>(
      '/compliance/quick-status'
    );
    return transformQuickComplianceStatus(response.data);
  },

  /**
   * Archive a document (GoBD-compliant)
   */
  async archiveDocument(documentId: number): Promise<{ archive_id: string; message: string }> {
    const response = await apiClient.post<{ archive_id: string; message: string }>(
      '/compliance/archive',
      { document_id: documentId }
    );
    return response.data;
  },

  /**
   * Verify integrity of an archived document
   */
  async verifyArchive(archiveId: string): Promise<{ valid: boolean; message: string }> {
    const response = await apiClient.post<{ valid: boolean; message: string }>(
      `/compliance/archive/${archiveId}/verify`
    );
    return response.data;
  },

  /**
   * Get audit chain entries
   */
  async getAuditChain(params?: PaginationParams): Promise<PaginatedResponse<AuditChainEntry>> {
    const response = await apiClient.get<PaginatedResponse<AuditChainEntryResponse>>(
      '/compliance/audit-chain',
      { params }
    );

    return {
      items: response.data.items.map(transformAuditChainEntry),
      total: response.data.total,
      page: response.data.page,
      per_page: response.data.per_page,
      pages: response.data.pages,
    };
  },

  /**
   * Get audit chain statistics
   */
  async getAuditChainStats(): Promise<AuditChainStats> {
    const response = await apiClient.get<AuditChainStatsResponse>(
      '/compliance/audit-chain/statistics'
    );
    return transformAuditChainStats(response.data);
  },

  /**
   * Verify entire audit chain integrity
   */
  async verifyAuditChain(): Promise<{ valid: boolean; message: string; issues?: string[] }> {
    const response = await apiClient.get<{ valid: boolean; message: string; issues?: string[] }>(
      '/compliance/audit-chain/verify-chain'
    );
    return response.data;
  },

  /**
   * Get retention alerts (documents expiring soon)
   */
  async getRetentionAlerts(): Promise<RetentionAlert[]> {
    const response = await apiClient.get<RetentionAlertResponse[]>(
      '/compliance/retention/alerts'
    );
    return response.data.map(transformRetentionAlert);
  },

  /**
   * Get retention statistics
   */
  async getRetentionStats(): Promise<RetentionStats> {
    const response = await apiClient.get<RetentionStatsResponse>('/compliance/retention/stats');
    return transformRetentionStats(response.data);
  },

  /**
   * List retention policies
   */
  async getRetentionPolicies(): Promise<RetentionPolicy[]> {
    const response = await apiClient.get<RetentionPolicyResponse[]>(
      '/compliance/retention/policies'
    );
    return response.data.map(transformRetentionPolicy);
  },

  /**
   * Create a new retention policy
   */
  async createRetentionPolicy(
    documentType: RetentionDocumentType,
    retentionPeriodDays: number,
    description: string,
    legalBasis: string
  ): Promise<RetentionPolicy> {
    const response = await apiClient.post<RetentionPolicyResponse>(
      '/compliance/retention/policies',
      {
        document_type: documentType,
        retention_period_days: retentionPeriodDays,
        description,
        legal_basis: legalBasis,
      }
    );
    return transformRetentionPolicy(response.data);
  },

  /**
   * Get GoBD procedure documentation (Verfahrensdokumentation)
   */
  async getProcedureDocumentation(): Promise<ProcedureDocumentation> {
    const response = await apiClient.get<ProcedureDocumentationResponse>(
      '/compliance/procedure-documentation'
    );
    return transformProcedureDocumentation(response.data);
  },

  /**
   * Download GoBD procedure documentation as PDF
   */
  async downloadProcedureDocumentationPdf(): Promise<Blob> {
    const response = await apiClient.get<Blob>('/compliance/procedure-documentation/pdf', {
      responseType: 'blob',
    });
    return response.data;
  },
};

/**
 * Compliance Autopilot Service
 */
export const complianceAutopilotService = {
  /**
   * Run a full compliance scan
   */
  async runComplianceScan(): Promise<ComplianceScanResult> {
    const response = await apiClient.post<ComplianceScanResultResponse>(
      '/compliance-autopilot/scan'
    );
    return transformComplianceScanResult(response.data);
  },

  /**
   * Get retention report (expired and expiring documents)
   */
  async getRetentionReport(): Promise<RetentionReport> {
    const response = await apiClient.get<RetentionReportResponse>(
      '/compliance-autopilot/retention'
    );
    return transformRetentionReport(response.data);
  },

  /**
   * Run GDPR compliance check
   */
  async runGdprCheck(): Promise<GdprCheck> {
    const response = await apiClient.post<GdprCheckResponse>('/compliance-autopilot/gdpr-check');
    return transformGdprCheck(response.data);
  },

  /**
   * Prepare and download audit package (ZIP)
   */
  async downloadAuditPackage(): Promise<Blob> {
    const response = await apiClient.post<Blob>('/compliance-autopilot/audit-preparation', null, {
      responseType: 'blob',
    });
    return response.data;
  },
};
