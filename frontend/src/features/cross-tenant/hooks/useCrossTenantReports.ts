/**
 * Cross-Tenant Reports Hooks
 *
 * React Query Hooks fuer mandantenuebergreifende Berichte.
 */

import { useQuery } from '@tanstack/react-query';
import {
  fetchCompanyOverview,
  fetchCompanyFinancials,
  crossTenantKeys,
} from '../api/cross-tenant-api';

/**
 * Hook fuer die mandantenuebergreifende Firmen-Uebersicht
 */
export function useCompanyOverview() {
  return useQuery({
    queryKey: crossTenantKeys.overview(),
    queryFn: fetchCompanyOverview,
    staleTime: 60_000,
  });
}

/**
 * Hook fuer die mandantenuebergreifende Finanz-Zusammenfassung
 */
export function useCompanyFinancials() {
  return useQuery({
    queryKey: crossTenantKeys.financials(),
    queryFn: fetchCompanyFinancials,
    staleTime: 60_000,
  });
}
