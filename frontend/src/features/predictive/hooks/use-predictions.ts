/**
 * Predictive Hooks - TanStack Query Hooks fuer Vorhersagen
 *
 * Stellt reaktive Datenhooks bereit fuer:
 * - Cashflow-Prognosen (5 Min. Cache)
 * - Zahlungsvorhersagen (5 Min. Cache)
 * - System-Gesundheit (15 Sek. Cache, 30 Sek. Refetch)
 * - Proaktive Alerts (30 Sek. Cache, 60 Sek. Refetch)
 */

import { useQuery } from '@tanstack/react-query';
import {
  getCashflowForecast,
  getPaymentPredictions,
  getSystemHealthPredictions,
  getPredictiveAlerts,
} from '../api/predictive-api';
import type { ForecastPeriod } from '../types/predictive-types';

export const predictiveKeys = {
  all: ['predictive'] as const,
  cashflow: (days: ForecastPeriod) =>
    [...predictiveKeys.all, 'cashflow', days] as const,
  payments: () => [...predictiveKeys.all, 'payments'] as const,
  health: () => [...predictiveKeys.all, 'health'] as const,
  alerts: () => [...predictiveKeys.all, 'alerts'] as const,
};

export function useCashflowForecast(days: ForecastPeriod = '30') {
  return useQuery({
    queryKey: predictiveKeys.cashflow(days),
    queryFn: () => getCashflowForecast(days),
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
  });
}

export function usePaymentPredictions() {
  return useQuery({
    queryKey: predictiveKeys.payments(),
    queryFn: getPaymentPredictions,
    staleTime: 1000 * 60 * 5,
    refetchInterval: 1000 * 60 * 5,
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: predictiveKeys.health(),
    queryFn: getSystemHealthPredictions,
    staleTime: 1000 * 15,
    refetchInterval: 1000 * 30,
  });
}

export function usePredictiveAlerts() {
  return useQuery({
    queryKey: predictiveKeys.alerts(),
    queryFn: getPredictiveAlerts,
    staleTime: 1000 * 30,
    refetchInterval: 1000 * 60,
  });
}
