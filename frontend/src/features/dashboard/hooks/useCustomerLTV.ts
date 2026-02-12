/**
 * Customer Lifetime Value Hook
 *
 * React Query Hook für Customer LTV-Metriken.
 * Liefert Kundenwert, Trend und Churn-Risiko.
 *
 * Phase 7: Dashboard Widgets
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCustomerLTV,
  dashboardWidgetKeys,
  type CustomerLTVData,
} from '../api/dashboard-widgets';

interface UseCustomerLTVOptions {
  periodDays?: number;
  enabled?: boolean;
  staleTime?: number;
}

/**
 * Hook für Customer LTV-Daten
 */
export function useCustomerLTV(options: UseCustomerLTVOptions = {}) {
  const { periodDays = 365, enabled = true, staleTime = 5 * 60 * 1000 } = options;

  return useQuery<CustomerLTVData, Error>({
    queryKey: dashboardWidgetKeys.customerLTV(periodDays),
    queryFn: () => getCustomerLTV(periodDays),
    enabled,
    staleTime,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}

/**
 * Hole Churn-Risiko Farbe
 */
export function getChurnRiskColor(risk: 'low' | 'medium' | 'high' | 'critical'): string {
  switch (risk) {
    case 'low':
      return 'text-green-600';
    case 'medium':
      return 'text-amber-600';
    case 'high':
      return 'text-orange-600';
    case 'critical':
      return 'text-red-600';
    default:
      return 'text-muted-foreground';
  }
}

/**
 * Hole Churn-Risiko Badge-Variante
 */
export function getChurnRiskBadgeVariant(
  risk: 'low' | 'medium' | 'high' | 'critical'
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (risk) {
    case 'low':
      return 'secondary';
    case 'medium':
      return 'outline';
    case 'high':
      return 'default';
    case 'critical':
      return 'destructive';
    default:
      return 'outline';
  }
}

/**
 * Hole Trend-Icon Klasse
 */
export function getTrendIconClass(trend: 'growing' | 'stable' | 'declining'): string {
  switch (trend) {
    case 'growing':
      return 'text-green-600';
    case 'declining':
      return 'text-red-600';
    default:
      return 'text-muted-foreground';
  }
}

/**
 * Formatiere LTV als kompakte Zahl
 */
export function formatLTVCompact(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M EUR`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k EUR`;
  }
  return `${value.toFixed(0)} EUR`;
}

/**
 * Formatiere Tage seit letzter Bestellung
 */
export function formatDaysSince(days: number): string {
  if (days === 0) return 'Heute';
  if (days === 1) return 'Gestern';
  if (days < 7) return `Vor ${days} Tagen`;
  if (days < 30) return `Vor ${Math.floor(days / 7)} Wochen`;
  if (days < 365) return `Vor ${Math.floor(days / 30)} Monaten`;
  return `Vor ${Math.floor(days / 365)} Jahren`;
}
