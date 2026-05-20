/**
 * DSO Tracker Hook
 *
 * React Query Hook für Forderungslaufzeit (Days Sales Outstanding).
 * Nutzt den globalen DateRange-Filter für zeitraumbasierte Abfragen.
 *
 * Phase C: Business KPIs
 */

import { useQuery } from '@tanstack/react-query';
import {
  getDSOTracker,
  dashboardWidgetKeys,
  type DSOTrackerData,
} from '../api/dashboard-widgets';
import { useDateRange } from './useDateRange';

export function useDSOTracker() {
  const { dateRange } = useDateRange();

  return useQuery<DSOTrackerData, Error>({
    queryKey: [
      ...dashboardWidgetKeys.all,
      'dso-tracker',
      dateRange.from?.toISOString(),
      dateRange.to?.toISOString(),
    ],
    queryFn: () =>
      getDSOTracker(
        dateRange.from?.toISOString().split('T')[0],
        dateRange.to?.toISOString().split('T')[0],
      ),
    staleTime: 5 * 60 * 1000,
    retry: 2,
    refetchOnWindowFocus: false,
  });
}
