/**
 * Contract Lifecycle API
 *
 * API client and React Query hooks for contract lifecycle dashboard,
 * cost aggregation, and renewal tracking.
 */

import { useQuery } from '@tanstack/react-query';
import type { UseQueryOptions } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';
import { contractKeys } from './contracts-api';

const API_BASE = '/contracts';

// =============================================================================
// Types
// =============================================================================

export interface ContractCostByCategory {
  category: string;
  annual_cost: number;
  contract_count: number;
}

export interface ContractCostBySupplier {
  supplier_name: string;
  annual_cost: number;
  contract_count: number;
}

export interface ContractCostTrend {
  month: string;
  total_cost: number;
}

export interface ContractCostSummary {
  total_annual_cost: number;
  total_monthly_cost: number;
  by_category: ContractCostByCategory[];
  by_supplier: ContractCostBySupplier[];
  trend_last_12_months: ContractCostTrend[];
}

export interface ContractRenewalItem {
  contract_id: string;
  contract_name: string;
  partner_name: string;
  expires_at: string;
  auto_renewal: boolean;
  notice_deadline: string | null;
  days_until_expiry: number;
  annual_cost: number;
  action_required: boolean;
}

export interface ContractLifecycleOverview {
  total_contracts: number;
  active_contracts: number;
  expiring_soon: number;
  pending_renewal_decision: number;
  cost_summary: ContractCostSummary;
  upcoming_renewals: ContractRenewalItem[];
}

// =============================================================================
// Query Keys
// =============================================================================

export const lifecycleKeys = {
  all: [...contractKeys.all, 'lifecycle'] as const,
  overview: () => [...lifecycleKeys.all, 'overview'] as const,
  costSummary: (period?: string) => [...lifecycleKeys.all, 'costs', period ?? 'default'] as const,
  renewals: (days?: number) => [...lifecycleKeys.all, 'renewals', days ?? 90] as const,
};

// =============================================================================
// API Functions
// =============================================================================

export async function getContractLifecycleOverview(): Promise<ContractLifecycleOverview> {
  return fetchWithAuth<ContractLifecycleOverview>(`${API_BASE}/lifecycle/overview`);
}

export async function getContractCostSummary(period?: string): Promise<ContractCostSummary> {
  const query = period ? `?period=${encodeURIComponent(period)}` : '';
  return fetchWithAuth<ContractCostSummary>(`${API_BASE}/lifecycle/costs${query}`);
}

export async function getUpcomingRenewals(days?: number): Promise<ContractRenewalItem[]> {
  const query = days ? `?days=${days}` : '';
  return fetchWithAuth<ContractRenewalItem[]>(`${API_BASE}/lifecycle/renewals${query}`);
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useContractLifecycle(
  options?: Omit<UseQueryOptions<ContractLifecycleOverview>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: lifecycleKeys.overview(),
    queryFn: getContractLifecycleOverview,
    staleTime: 1000 * 60 * 5,
    ...options,
  });
}

export function useContractCostSummary(
  period?: string,
  options?: Omit<UseQueryOptions<ContractCostSummary>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: lifecycleKeys.costSummary(period),
    queryFn: () => getContractCostSummary(period),
    staleTime: 1000 * 60 * 5,
    ...options,
  });
}

export function useUpcomingRenewals(
  days?: number,
  options?: Omit<UseQueryOptions<ContractRenewalItem[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: lifecycleKeys.renewals(days),
    queryFn: () => getUpcomingRenewals(days),
    staleTime: 1000 * 60 * 5,
    ...options,
  });
}
