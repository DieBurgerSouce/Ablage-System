/**
 * Margin Analyzer Hook
 *
 * React Query Hook fuer Margenanalyse-Daten.
 * Nutzt den globalen DateRange-Filter fuer zeitraumbasierte Abfragen.
 *
 * Phase C: Business KPIs
 */

import { useQuery } from '@tanstack/react-query';
import {
  getMarginAnalyzer,
  dashboardWidgetKeys,
  type MarginAnalyzerData,
} from '../api/dashboard-widgets';
import { useDateRange } from './useDateRange';

export function useMarginAnalyzer() {
  const { dateRange } = useDateRange();

  return useQuery<MarginAnalyzerData, Error>({
    queryKey: [
      ...dashboardWidgetKeys.all,
      'margin-analyzer',
      dateRange.from?.toISOString(),
      dateRange.to?.toISOString(),
    ],
    queryFn: () =>
      getMarginAnalyzer(
        dateRange.from?.toISOString().split('T')[0],
        dateRange.to?.toISOString().split('T')[0],
      ),
    staleTime: 5 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}
