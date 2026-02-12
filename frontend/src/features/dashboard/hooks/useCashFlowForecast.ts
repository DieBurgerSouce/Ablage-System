/**
 * Cash-Flow Forecast Hook
 *
 * React Query Hook für Cash-Flow Prognose-Daten.
 * Liefert 30/60/90 Tage Liquiditätsprognose.
 *
 * Phase 7: Dashboard Widgets
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCashFlowForecast,
  getCashFlowChartData,
  dashboardWidgetKeys,
  type CashFlowForecastData,
  type ForecastDataPoint,
} from '../api/dashboard-widgets';

interface UseCashFlowForecastOptions {
  startingBalance?: number;
  enabled?: boolean;
  staleTime?: number;
}

/**
 * Hook für vollständige Cash-Flow Prognose
 */
export function useCashFlowForecast(options: UseCashFlowForecastOptions = {}) {
  const { startingBalance, enabled = true, staleTime = 5 * 60 * 1000 } = options;

  return useQuery<CashFlowForecastData, Error>({
    queryKey: dashboardWidgetKeys.cashFlowForecast(),
    queryFn: () => getCashFlowForecast(startingBalance),
    enabled,
    staleTime,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

interface UseCashFlowChartOptions {
  days?: number;
  enabled?: boolean;
  staleTime?: number;
}

/**
 * Hook für Cash-Flow Chart-Daten
 */
export function useCashFlowChartData(options: UseCashFlowChartOptions = {}) {
  const { days = 30, enabled = true, staleTime = 5 * 60 * 1000 } = options;

  return useQuery<ForecastDataPoint[], Error>({
    queryKey: dashboardWidgetKeys.cashFlowChart(days),
    queryFn: () => getCashFlowChartData(days),
    enabled,
    staleTime,
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
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

/**
 * Formatiere kurzes Datum (TT.MM)
 */
export function formatDateShort(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
  });
}
