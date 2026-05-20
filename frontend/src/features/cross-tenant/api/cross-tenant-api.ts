/**
 * Cross-Tenant Reports API
 *
 * API-Funktionen für mandantenübergreifende Berichte.
 * Erfordert Superuser-Berechtigung.
 */

import { apiClient } from '@/lib/api/client';
import type {
  CrossTenantOverviewResponse,
  CrossTenantFinancialResponse,
} from '../types/cross-tenant-types';

const BASE_URL = '/cross-tenant';

// =============================================================================
// API Functions
// =============================================================================

/**
 * Hole mandantenübergreifende Übersicht (nur Admin)
 */
export async function fetchCompanyOverview(): Promise<CrossTenantOverviewResponse> {
  const response = await apiClient.get<CrossTenantOverviewResponse>(
    `${BASE_URL}/overview`
  );
  return response.data;
}

/**
 * Hole mandantenübergreifende Finanz-Zusammenfassung (nur Admin)
 */
export async function fetchCompanyFinancials(): Promise<CrossTenantFinancialResponse> {
  const response = await apiClient.get<CrossTenantFinancialResponse>(
    `${BASE_URL}/financial-summary`
  );
  return response.data;
}

// =============================================================================
// Query Keys
// =============================================================================

export const crossTenantKeys = {
  all: ['cross-tenant'] as const,
  overview: () => [...crossTenantKeys.all, 'overview'] as const,
  financials: () => [...crossTenantKeys.all, 'financials'] as const,
};
