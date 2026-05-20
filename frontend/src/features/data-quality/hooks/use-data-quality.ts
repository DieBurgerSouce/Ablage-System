/**
 * Data Quality Hooks - TanStack Query Integration
 *
 * React Hooks für das Data Quality Dashboard
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDataQualityReport,
  getDataQualityTrend,
  fixDataQualityIssue,
  dataQualityKeys,
} from '../api/data-quality-api';
import { toast } from 'sonner';

/**
 * Hook für den Datenqualitätsbericht
 */
export function useDataQualityReport() {
  return useQuery({
    queryKey: dataQualityKeys.report(),
    queryFn: getDataQualityReport,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  });
}

/**
 * Hook für den historischen Qualitätstrend
 *
 * @param months - Anzahl der Monate (default: 6)
 */
export function useDataQualityTrend(months = 6) {
  return useQuery({
    queryKey: dataQualityKeys.trend(months),
    queryFn: () => getDataQualityTrend(months),
    staleTime: 60000,
    retry: 2,
  });
}

/**
 * Mutation für Cleanup-Aktionen
 */
export function useFixDataQualityIssue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ category, action }: { category: string; action: string }) =>
      fixDataQualityIssue(category, action),
    onSuccess: (data) => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: dataQualityKeys.report() });
      queryClient.invalidateQueries({ queryKey: dataQualityKeys.trend(6) });

      toast.success('Bereinigung erfolgreich', {
        description: data.message,
      });
    },
    onError: (error: Error) => {
      toast.error('Bereinigung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}
