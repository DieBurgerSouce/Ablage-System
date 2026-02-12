/**
 * Revenue Trend Hook
 *
 * React Query Hook für Umsatzentwicklungs-Daten.
 * Nutzt den globalen DateRange-Filter für zeitraumbasierte Abfragen.
 *
 * Phase C: Business KPIs
 */

import { useQuery } from '@tanstack/react-query';
import {
  getRevenueTrend,
  dashboardWidgetKeys,
  type RevenueTrendData,
} from '../api/dashboard-widgets';
import { useDateRange } from './useDateRange';

export function useRevenueTrend() {
  const { dateRange, comparePeriod } = useDateRange();

  return useQuery<RevenueTrendData, Error>({
    queryKey: [
      ...dashboardWidgetKeys.all,
      'revenue-trend',
      dateRange.from?.toISOString(),
      dateRange.to?.toISOString(),
      comparePeriod,
    ],
    queryFn: () =>
      getRevenueTrend(
        dateRange.from?.toISOString().split('T')[0],
        dateRange.to?.toISOString().split('T')[0],
        comparePeriod,
      ),
    staleTime: 5 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

/**
 * Formatiere Währungsbetrag (EUR)
 */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Formatiere Prozent
 */
export function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}
