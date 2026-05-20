/**
 * Digital Twin Hooks - TanStack Query Integration
 *
 * React Hooks für das Digital Twin Dashboard mit automatischer
 * Aktualisierung alle 60 Sekunden.
 */

import { useQuery } from '@tanstack/react-query';
import {
  getDigitalTwinSnapshot,
  getDigitalTwinSection,
  digitalTwinKeys,
  type DigitalTwinSnapshot,
} from '../api/digital-twin-api';

/**
 * Hook für den vollständigen Digital Twin Snapshot
 *
 * Aktualisiert sich automatisch alle 60 Sekunden.
 */
export function useDigitalTwinSnapshot() {
  return useQuery({
    queryKey: digitalTwinKeys.snapshot(),
    queryFn: getDigitalTwinSnapshot,
    staleTime: 30000, // 30 Sekunden
    refetchInterval: 60000, // 60 Sekunden Auto-Refresh
    retry: 2,
  });
}

/**
 * Hook für eine spezifische Sektion des Digital Twin
 *
 * @param section - Name der Sektion (financial_health, risk_overview, etc.)
 */
export function useDigitalTwinSection<T = unknown>(section: string) {
  return useQuery({
    queryKey: digitalTwinKeys.section(section),
    queryFn: () => getDigitalTwinSection<T>(section),
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
    enabled: !!section,
  });
}
