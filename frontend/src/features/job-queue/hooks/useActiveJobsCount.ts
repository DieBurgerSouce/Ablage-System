/**
 * useActiveJobsCount Hook
 *
 * Leichtgewichtiger Hook für Sidebar Badge Counter.
 * Pollt alle 30 Sekunden die aktiven Jobs für den Badge.
 */

import { useQuery } from '@tanstack/react-query';
import { getJobStats } from '../api/job-queue-api';
import { jobQueueKeys } from '../api/query-keys';

interface ActiveJobsCountResult {
  /** Anzahl der aktiven Jobs (in Bearbeitung) */
  activeCount: number;
  /** Anzahl der wartenden Jobs (in Queue) */
  queuedCount: number;
  /** Gesamtzahl (aktiv + wartend) */
  totalPending: number;
  /** Ob die Daten geladen werden */
  isLoading: boolean;
  /** Ob ein Fehler aufgetreten ist */
  isError: boolean;
}

/**
 * Hook für aktive Jobs Counter (Sidebar Badge).
 *
 * Features:
 * - Pollt alle 30 Sekunden
 * - Cached im Hintergrund
 * - Nur aktiviert wenn gemountet
 * - Leichtgewichtig (nur Stats-Endpoint)
 *
 * @example
 * ```tsx
 * const { totalPending, isLoading } = useActiveJobsCount();
 *
 * return (
 *   <div>
 *     Job Queue
 *     {totalPending > 0 && <Badge>{totalPending}</Badge>}
 *   </div>
 * );
 * ```
 */
export function useActiveJobsCount(): ActiveJobsCountResult {
  const { data, isLoading, isError } = useQuery({
    queryKey: jobQueueKeys.statsSummary(),
    queryFn: getJobStats,
    // Polling alle 30 Sekunden
    refetchInterval: 30_000,
    // Im Hintergrund refetchen
    refetchIntervalInBackground: false,
    // Stale nach 20 Sekunden
    staleTime: 20_000,
    // Retry bei Fehler
    retry: 2,
    retryDelay: 5000,
  });

  return {
    activeCount: data?.activeJobs ?? 0,
    queuedCount: data?.queuedJobs ?? 0,
    totalPending: (data?.activeJobs ?? 0) + (data?.queuedJobs ?? 0),
    isLoading,
    isError,
  };
}

export default useActiveJobsCount;
