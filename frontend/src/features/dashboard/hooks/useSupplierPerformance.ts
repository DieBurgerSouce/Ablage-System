/**
 * Supplier Performance Hook
 *
 * React Query Hook für Lieferanten-Performance-Metriken.
 * Liefert Pünktlichkeit, Genauigkeit und Preistrend.
 *
 * Phase 7: Dashboard Widgets
 */

import { useQuery } from '@tanstack/react-query';
import {
  getSupplierPerformance,
  dashboardWidgetKeys,
  type SupplierPerformanceData,
} from '../api/dashboard-widgets';

interface UseSupplierPerformanceOptions {
  periodDays?: number;
  enabled?: boolean;
  staleTime?: number;
}

/**
 * Hook für Lieferanten-Performance-Daten
 */
export function useSupplierPerformance(options: UseSupplierPerformanceOptions = {}) {
  const { periodDays = 90, enabled = true, staleTime = 5 * 60 * 1000 } = options;

  return useQuery<SupplierPerformanceData, Error>({
    queryKey: dashboardWidgetKeys.supplierPerformance(periodDays),
    queryFn: () => getSupplierPerformance(periodDays),
    enabled,
    staleTime,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

/**
 * Formatiere Trend-Richtung als Icon-Klasse
 */
export function getTrendIconClass(direction: 'up' | 'down' | 'stable'): string {
  switch (direction) {
    case 'up':
      return 'text-red-500'; // Steigende Preise = schlecht
    case 'down':
      return 'text-green-500'; // Sinkende Preise = gut
    default:
      return 'text-muted-foreground';
  }
}

/**
 * Formatiere Pünktlichkeit/Genauigkeit als Farbe
 */
export function getScoreColor(score: number): string {
  if (score >= 90) return 'text-green-600';
  if (score >= 75) return 'text-amber-600';
  return 'text-red-600';
}

/**
 * Formatiere Preistrend als Text
 */
export function formatPriceTrend(value: number): string {
  if (value > 0) return `+${value.toFixed(1)}%`;
  if (value < 0) return `${value.toFixed(1)}%`;
  return '0%';
}
