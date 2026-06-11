/**
 * Compliance Cockpit TanStack Query Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { complianceService, complianceAutopilotService } from '../api/compliance-api';
import type { ComplianceReport, QuickComplianceStatus, ComplianceScanResult, RetentionReport, RetentionAlert, RetentionStats, RetentionPolicy, AuditChainStats, GdprCheck, ProcedureDocumentation, RetentionDocumentType } from '../types/compliance-types';

// Query keys
export const complianceKeys = {
  all: ['compliance'] as const,
  report: () => [...complianceKeys.all, 'report'] as const,
  quickStatus: () => [...complianceKeys.all, 'quick-status'] as const,
  auditChainStats: () => [...complianceKeys.all, 'audit-chain-stats'] as const,
  auditChain: (page?: number) => [...complianceKeys.all, 'audit-chain', page] as const,
  retentionStats: () => [...complianceKeys.all, 'retention-stats'] as const,
  retentionAlerts: () => [...complianceKeys.all, 'retention-alerts'] as const,
  retentionPolicies: () => [...complianceKeys.all, 'retention-policies'] as const,
  procedureDoc: () => [...complianceKeys.all, 'procedure-documentation'] as const,
};

/**
 * Get full compliance report
 * Stale time: 5 minutes (report is expensive to generate)
 */
export function useComplianceReport() {
  return useQuery<ComplianceReport, Error>({
    queryKey: complianceKeys.report(),
    queryFn: () => complianceService.getComplianceReport(),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Get quick compliance status for dashboard widget
 * Stale time: 30 seconds (for real-time updates)
 */
export function useQuickComplianceStatus() {
  return useQuery<QuickComplianceStatus, Error>({
    queryKey: complianceKeys.quickStatus(),
    queryFn: () => complianceService.getQuickComplianceStatus(),
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 2 * 60 * 1000, // 2 minutes
    refetchInterval: 60 * 1000, // Refetch every minute
  });
}

/**
 * Get audit chain statistics
 */
export function useAuditChainStats() {
  return useQuery<AuditChainStats, Error>({
    queryKey: complianceKeys.auditChainStats(),
    queryFn: () => complianceService.getAuditChainStats(),
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}

/**
 * Get audit chain entries with pagination
 */
export function useAuditChain(page: number = 1, perPage: number = 50) {
  return useQuery({
    queryKey: complianceKeys.auditChain(page),
    queryFn: () => complianceService.getAuditChain({ page, per_page: perPage }),
    staleTime: 1 * 60 * 1000, // 1 minute
  });
}

/**
 * Get retention statistics
 */
export function useRetentionStats() {
  return useQuery<RetentionStats, Error>({
    queryKey: complianceKeys.retentionStats(),
    queryFn: () => complianceService.getRetentionStats(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get retention alerts (expiring documents)
 */
export function useRetentionAlerts() {
  return useQuery<RetentionAlert[], Error>({
    queryKey: complianceKeys.retentionAlerts(),
    queryFn: () => complianceService.getRetentionAlerts(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Get retention policies
 */
export function useRetentionPolicies() {
  return useQuery<RetentionPolicy[], Error>({
    queryKey: complianceKeys.retentionPolicies(),
    queryFn: () => complianceService.getRetentionPolicies(),
    staleTime: 10 * 60 * 1000, // 10 minutes (policies change rarely)
  });
}

/**
 * Get GoBD procedure documentation
 */
export function useProcedureDocumentation() {
  return useQuery<ProcedureDocumentation, Error>({
    queryKey: complianceKeys.procedureDoc(),
    queryFn: () => complianceService.getProcedureDocumentation(),
    staleTime: 30 * 60 * 1000, // 30 minutes (rarely changes)
  });
}

/**
 * Mutation: Run full compliance scan
 */
export function useRunComplianceScan() {
  const queryClient = useQueryClient();

  return useMutation<ComplianceScanResult, Error>({
    mutationFn: () => complianceAutopilotService.runComplianceScan(),
    onSuccess: () => {
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: complianceKeys.report() });
      queryClient.invalidateQueries({ queryKey: complianceKeys.quickStatus() });
    },
  });
}

/**
 * Mutation: Run GDPR compliance check
 */
export function useRunGdprCheck() {
  const queryClient = useQueryClient();

  return useMutation<GdprCheck, Error>({
    mutationFn: () => complianceAutopilotService.runGdprCheck(),
    onSuccess: () => {
      // Invalidate compliance status
      queryClient.invalidateQueries({ queryKey: complianceKeys.report() });
      queryClient.invalidateQueries({ queryKey: complianceKeys.quickStatus() });
    },
  });
}

/**
 * Mutation: Get retention report
 */
export function useGetRetentionReport() {
  return useMutation<RetentionReport, Error>({
    mutationFn: () => complianceAutopilotService.getRetentionReport(),
  });
}

/**
 * Mutation: Verify audit chain integrity
 */
export function useVerifyAuditChain() {
  const queryClient = useQueryClient();

  return useMutation<{ valid: boolean; message: string; issues?: string[] }, Error>({
    mutationFn: () => complianceService.verifyAuditChain(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: complianceKeys.auditChainStats() });
    },
  });
}

/**
 * Mutation: Archive a document
 */
export function useArchiveDocument() {
  const queryClient = useQueryClient();

  return useMutation<{ archive_id: string; message: string }, Error, number>({
    mutationFn: (documentId: number) => complianceService.archiveDocument(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: complianceKeys.auditChainStats() });
      queryClient.invalidateQueries({ queryKey: complianceKeys.retentionStats() });
    },
  });
}

/**
 * Mutation: Create retention policy
 */
export function useCreateRetentionPolicy() {
  const queryClient = useQueryClient();

  return useMutation<
    RetentionPolicy,
    Error,
    {
      documentType: RetentionDocumentType;
      retentionPeriodDays: number;
      description: string;
      legalBasis: string;
    }
  >({
    mutationFn: ({ documentType, retentionPeriodDays, description, legalBasis }) =>
      complianceService.createRetentionPolicy(
        documentType,
        retentionPeriodDays,
        description,
        legalBasis
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: complianceKeys.retentionPolicies() });
    },
  });
}

/**
 * Mutation: Download audit package
 */
export function useDownloadAuditPackage() {
  return useMutation<Blob, Error>({
    mutationFn: () => complianceAutopilotService.downloadAuditPackage(),
    onSuccess: (blob) => {
      // Auto-download the ZIP file
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-package-${new Date().toISOString().split('T')[0]}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
  });
}

/**
 * Mutation: Download procedure documentation PDF
 */
export function useDownloadProcedureDocPdf() {
  return useMutation<Blob, Error>({
    mutationFn: () => complianceService.downloadProcedureDocumentationPdf(),
    onSuccess: (blob) => {
      // Auto-download the PDF
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GoBD-Verfahrensdokumentation-${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
  });
}
