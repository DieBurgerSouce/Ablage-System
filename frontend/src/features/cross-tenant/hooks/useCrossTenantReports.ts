/**
 * Cross-Tenant Reports Hooks
 *
 * React Query Hooks für mandantenübergreifende Berichte.
 */

import { useQuery } from '@tanstack/react-query';
import {
  fetchCompanyOverview,
  fetchCompanyFinancials,
  crossTenantKeys,
} from '../api/cross-tenant-api';

/**
 * Hook für die mandantenübergreifende Firmen-Übersicht
 */
export function useCompanyOverview() {
  return useQuery({
    queryKey: crossTenantKeys.overview(),
    queryFn: fetchCompanyOverview,
    staleTime: 60_000,
  });
}

/**
 * Hook für die mandantenübergreifende Finanz-Zusammenfassung
 */
export function useCompanyFinancials() {
  return useQuery({
    queryKey: crossTenantKeys.financials(),
    queryFn: fetchCompanyFinancials,
    staleTime: 60_000,
  });
}
