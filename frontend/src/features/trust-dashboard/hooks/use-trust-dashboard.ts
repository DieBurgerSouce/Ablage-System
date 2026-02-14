/**
 * Trust Dashboard Hooks - TanStack Query Integration
 *
 * React Hooks für das Trust Dashboard mit Sicherheitsüberwachung
 */

import { useQuery } from '@tanstack/react-query';
import {
  getTrustDashboardSnapshot,
  getAccessLog,
  getExportLog,
  getAnomalies,
  trustDashboardKeys,
} from '../api/trust-dashboard-api';

/**
 * Hook für den Trust Dashboard Snapshot
 *
 * @param days - Anzahl der Tage für die Auswertung (default: 30)
 */
export function useTrustDashboard(days = 30) {
  return useQuery({
    queryKey: trustDashboardKeys.snapshot(days),
    queryFn: () => getTrustDashboardSnapshot(days),
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  });
}

/**
 * Hook für das Zugriffsprotokolle
 */
export function useAccessLog(days = 30, limit = 100, offset = 0) {
  return useQuery({
    queryKey: trustDashboardKeys.accessLog(days, limit, offset),
    queryFn: () => getAccessLog(days, limit, offset),
    staleTime: 30000,
    retry: 2,
  });
}

/**
 * Hook für das Export-Protokolle
 */
export function useExportLog(days = 30, limit = 100, offset = 0) {
  return useQuery({
    queryKey: trustDashboardKeys.exportLog(days, limit, offset),
    queryFn: () => getExportLog(days, limit, offset),
    staleTime: 30000,
    retry: 2,
  });
}

/**
 * Hook für erkannte Anomalien
 */
export function useAnomalies(days = 7, limit = 50) {
  return useQuery({
    queryKey: trustDashboardKeys.anomalies(days, limit),
    queryFn: () => getAnomalies(days, limit),
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  });
}
