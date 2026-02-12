/**
 * React Query Hooks für Steueroptimierung
 *
 * Bietet:
 * - useTaxOptimization: Vollständige Steueranalyse
 * - useTaxDeductions: Abzuege nach Kategorie
 * - useTaxDeadlines: Steuerfristen
 * - useCheckDeductibility: Absetzbarkeitsprüfung
 * - useDATEVExport: DATEV-Export Mutation
 * - useYearComparison: Jahresvergleich
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import {
  taxOptimizationService,
  type TaxOptimizationResult,
  type TaxDeductionSummary,
  type TaxDeadline,
  type DeductibilityCheckResult,
  type DATEVExportData,
  type TaxYearComparison,
  type TaxCategory,
} from '@/lib/api/services/tax-optimization';

// ==================== Query Keys ====================

export const taxQueryKeys = {
  all: ['tax-optimization'] as const,
  optimization: (spaceId: string, taxYear?: number) =>
    [...taxQueryKeys.all, 'optimization', spaceId, taxYear] as const,
  deductions: (spaceId: string, category: TaxCategory, taxYear?: number) =>
    [...taxQueryKeys.all, 'deductions', spaceId, category, taxYear] as const,
  deadlines: (spaceId: string, taxYear?: number) =>
    [...taxQueryKeys.all, 'deadlines', spaceId, taxYear] as const,
  yearComparison: (spaceId: string, currentYear?: number) =>
    [...taxQueryKeys.all, 'year-comparison', spaceId, currentYear] as const,
  tips: (spaceId: string, taxYear?: number) => [...taxQueryKeys.all, 'tips', spaceId, taxYear] as const,
};

// ==================== Steueroptimierung Hooks ====================

/**
 * Hook für vollständige Steueroptimierungs-Analyse
 */
export function useTaxOptimization(
  spaceId: string,
  options?: {
    taxYear?: number;
    estimatedGrossIncome?: number;
    isMarried?: boolean;
  },
  queryOptions?: Omit<UseQueryOptions<TaxOptimizationResult>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: taxQueryKeys.optimization(spaceId, options?.taxYear),
    queryFn: () => taxOptimizationService.analyzeTaxOptimization(spaceId, options),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000, // 5 Minuten
    ...queryOptions,
  });
}

/**
 * Hook für Steuerabzuege nach Kategorie
 */
export function useTaxDeductions(
  spaceId: string,
  category: TaxCategory,
  taxYear?: number,
  queryOptions?: Omit<UseQueryOptions<TaxDeductionSummary>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: taxQueryKeys.deductions(spaceId, category, taxYear),
    queryFn: () => taxOptimizationService.getDeductionsByCategory(spaceId, category, taxYear),
    enabled: !!spaceId,
    staleTime: 5 * 60 * 1000,
    ...queryOptions,
  });
}

/**
 * Hook für Steuerfristen
 */
export function useTaxDeadlines(
  spaceId: string,
  taxYear?: number,
  queryOptions?: Omit<UseQueryOptions<{ upcoming: TaxDeadline[]; overdue: TaxDeadline[] }>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: taxQueryKeys.deadlines(spaceId, taxYear),
    queryFn: () => taxOptimizationService.getTaxDeadlines(spaceId, taxYear),
    enabled: !!spaceId,
    staleTime: 60 * 1000, // 1 Minute (Fristen ändern sich)
    ...queryOptions,
  });
}

/**
 * Hook für Jahresvergleich
 */
export function useYearComparison(
  spaceId: string,
  currentYear?: number,
  queryOptions?: Omit<UseQueryOptions<TaxYearComparison>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: taxQueryKeys.yearComparison(spaceId, currentYear),
    queryFn: () => taxOptimizationService.getYearComparison(spaceId, currentYear),
    enabled: !!spaceId,
    staleTime: 10 * 60 * 1000, // 10 Minuten
    ...queryOptions,
  });
}

/**
 * Hook für Optimierungstipps
 */
export function useTaxTips(
  spaceId: string,
  taxYear?: number,
  queryOptions?: Omit<UseQueryOptions<string[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: taxQueryKeys.tips(spaceId, taxYear),
    queryFn: () => taxOptimizationService.getOptimizationTips(spaceId, taxYear),
    enabled: !!spaceId,
    staleTime: 10 * 60 * 1000,
    ...queryOptions,
  });
}

// ==================== Mutations ====================

/**
 * Hook für Absetzbarkeitsprüfung
 */
export function useCheckDeductibility() {
  return useMutation({
    mutationFn: ({
      documentId,
      options,
    }: {
      documentId: string;
      options?: {
        documentText?: string;
        documentType?: string;
        amount?: number;
      };
    }) => taxOptimizationService.checkDeductibility(documentId, options),
  });
}

/**
 * Hook für DATEV-Export Generierung
 */
export function useDATEVExport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ spaceId, taxYear }: { spaceId: string; taxYear: number }) =>
      taxOptimizationService.generateDATEVExport(spaceId, taxYear),
    onSuccess: (_, { spaceId, taxYear }) => {
      // Invalidiere Steueroptimierungs-Cache
      queryClient.invalidateQueries({ queryKey: taxQueryKeys.optimization(spaceId, taxYear) });
    },
  });
}

/**
 * Hook für DATEV-Export Download
 */
export function useDATEVExportDownload() {
  return useMutation({
    mutationFn: async ({ spaceId, taxYear }: { spaceId: string; taxYear: number }) => {
      const blob = await taxOptimizationService.downloadDATEVExport(spaceId, taxYear);

      // Datei herunterladen
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `DATEV_Export_${taxYear}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      return blob;
    },
  });
}
