/**
 * Data Quality Query Hooks
 *
 * TanStack Query hooks for Data Quality data fetching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dataQualityApi } from '../api/data-quality-api';
import type {
  QualityReport,
  QualityTrend,
  FixResult,
  QualityCategory,
} from '../types/data-quality-types';
import { toast } from 'sonner';

const QUERY_KEYS = {
  qualityReport: ['data-quality', 'report'] as const,
  qualityTrend: (months: number) => ['data-quality', 'trend', months] as const,
};

/**
 * Hook to fetch data quality report
 * Auto-refreshes every 5 minutes
 */
export function useQualityReport() {
  return useQuery<QualityReport, Error>({
    queryKey: QUERY_KEYS.qualityReport,
    queryFn: dataQualityApi.getQualityReport,
    refetchInterval: 300000, // 5 minutes
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to fetch quality trend
 * @param months - Number of months to include (default: 6)
 */
export function useQualityTrend(months: number = 6) {
  return useQuery<QualityTrend, Error>({
    queryKey: QUERY_KEYS.qualityTrend(months),
    queryFn: () => dataQualityApi.getQualityTrend(months),
    staleTime: 300000, // 5 minutes
  });
}

/**
 * Hook to execute quality fix action
 */
export function useFixQualityIssue() {
  const queryClient = useQueryClient();

  return useMutation<FixResult, Error, QualityCategory>({
    mutationFn: (category: QualityCategory) =>
      dataQualityApi.fixQualityIssue(category),
    onSuccess: (data) => {
      // Invalidate quality report to refetch
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.qualityReport });
      queryClient.invalidateQueries({
        queryKey: ['data-quality', 'trend'],
      });

      // Show success toast
      if (data.success) {
        toast.success('Bereinigung erfolgreich', {
          description: `${data.fixedCount} Dokument(e) wurden bereinigt.`,
        });
      } else {
        toast.error('Bereinigung fehlgeschlagen', {
          description: data.message,
        });
      }
    },
    onError: (error) => {
      toast.error('Bereinigung fehlgeschlagen', {
        description: error.message || 'Ein unbekannter Fehler ist aufgetreten.',
      });
    },
  });
}
