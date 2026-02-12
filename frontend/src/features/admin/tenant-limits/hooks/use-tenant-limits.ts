/**
 * Tenant Rate Limits - React Query Hooks
 *
 * API Hooks für die Verwaltung von Tenant-spezifischen Rate Limits.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { UUID } from '@/types';

// ==================== Types ====================

export interface TierDefaultsResponse {
  requests_per_minute: number;
  requests_per_hour: number;
  requests_per_day: number;
  ocr_requests_per_hour: number;
  batch_requests_per_hour: number;
  burst_limit: number;
  max_users: number;
  max_documents_per_month: number;
  max_storage_gb: number;
  features: string[];
}

export interface CustomLimitResponse {
  id: string;
  endpoint_pattern: string;
  requests_per_minute: number;
  requests_per_hour: number;
  requests_per_day: number;
  burst_limit: number;
  is_custom: boolean;
}

export interface CompanyLimitsResponse {
  company_id: string;
  company_name: string;
  subscription_tier: 'free' | 'basic' | 'professional' | 'enterprise';
  subscription_expires_at: string | null;
  tier_defaults: TierDefaultsResponse;
  custom_limits: CustomLimitResponse[];
  max_users: number;
  max_documents_per_month: number;
  max_storage_gb: number;
  features_enabled: string[];
}

export interface UsageTimelineItem {
  period_start: string;
  total_requests: number;
  rate_limited: number;
  documents_processed: number;
}

export interface UsageSummaryResponse {
  company_id: string;
  period_type: 'hourly' | 'daily' | 'monthly';
  data_points: number;
  total_requests: number;
  rate_limited_requests: number;
  rate_limit_percentage: number;
  avg_response_time_ms: number | null;
  documents_processed: number;
  pages_processed: number;
  storage_used_bytes: number;
  active_users: number;
  timeline: UsageTimelineItem[];
}

export interface ViolationResponse {
  id: string;
  endpoint: string;
  method: string;
  ip_address: string;
  limit_type: string;
  limit_value: number;
  current_count: number;
  occurred_at: string;
}

export interface UpdateLimitRequest {
  endpoint_pattern: string;
  requests_per_minute?: number;
  requests_per_hour?: number;
  requests_per_day?: number;
  burst_limit?: number;
}

// ==================== Query Keys ====================

export const tenantLimitKeys = {
  all: ['tenant-limits'] as const,
  own: () => [...tenantLimitKeys.all, 'own'] as const,
  company: (companyId: UUID) => [...tenantLimitKeys.all, 'company', companyId] as const,
  usage: (companyId: UUID, periodType: string, daysBack: number) =>
    [...tenantLimitKeys.all, 'usage', companyId, periodType, daysBack] as const,
  violations: (companyId: UUID, hoursBack: number) =>
    [...tenantLimitKeys.all, 'violations', companyId, hoursBack] as const,
};

// ==================== API Functions ====================

async function fetchOwnLimits(): Promise<CompanyLimitsResponse> {
  const response = await api.get('/tenant-limits');
  return response.data;
}

async function fetchCompanyLimits(companyId: UUID): Promise<CompanyLimitsResponse> {
  const response = await api.get(`/tenant-limits/${companyId}`);
  return response.data;
}

async function fetchUsageMetrics(
  companyId: UUID,
  periodType: string = 'daily',
  daysBack: number = 30
): Promise<UsageSummaryResponse> {
  const response = await api.get(`/tenant-limits/${companyId}/usage`, {
    params: { period_type: periodType, days_back: daysBack },
  });
  return response.data;
}

async function fetchViolations(
  companyId: UUID,
  hoursBack: number = 24,
  limit: number = 100
): Promise<ViolationResponse[]> {
  const response = await api.get(`/tenant-limits/${companyId}/violations`, {
    params: { hours_back: hoursBack, limit },
  });
  return response.data;
}

async function updateCompanyLimit(
  companyId: UUID,
  data: UpdateLimitRequest
): Promise<CustomLimitResponse> {
  const response = await api.patch(`/tenant-limits/${companyId}`, data);
  return response.data;
}

async function resetCompanyLimits(companyId: UUID): Promise<{ message: string }> {
  const response = await api.delete(`/tenant-limits/${companyId}/custom`);
  return response.data;
}

// ==================== Query Hooks ====================

/**
 * Hook für eigene Company-Limits (normaler User)
 */
export function useOwnLimits() {
  return useQuery({
    queryKey: tenantLimitKeys.own(),
    queryFn: fetchOwnLimits,
    staleTime: 30 * 1000, // 30 Sekunden
  });
}

/**
 * Hook für Company-Limits (Admin)
 */
export function useCompanyLimits(companyId: UUID | undefined) {
  return useQuery({
    queryKey: tenantLimitKeys.company(companyId!),
    queryFn: () => fetchCompanyLimits(companyId!),
    enabled: !!companyId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook für Usage-Metriken
 */
export function useUsageMetrics(
  companyId: UUID | undefined,
  periodType: 'hourly' | 'daily' | 'monthly' = 'daily',
  daysBack: number = 30
) {
  return useQuery({
    queryKey: tenantLimitKeys.usage(companyId!, periodType, daysBack),
    queryFn: () => fetchUsageMetrics(companyId!, periodType, daysBack),
    enabled: !!companyId,
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Hook für Rate-Limit-Violations
 */
export function useViolations(
  companyId: UUID | undefined,
  hoursBack: number = 24
) {
  return useQuery({
    queryKey: tenantLimitKeys.violations(companyId!, hoursBack),
    queryFn: () => fetchViolations(companyId!, hoursBack),
    enabled: !!companyId,
    staleTime: 30 * 1000,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Hook zum Aktualisieren von Custom-Limits
 */
export function useUpdateLimit(companyId: UUID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateLimitRequest) => updateCompanyLimit(companyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tenantLimitKeys.company(companyId) });
    },
  });
}

/**
 * Hook zum Zurücksetzen auf Tier-Defaults
 */
export function useResetLimits(companyId: UUID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => resetCompanyLimits(companyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tenantLimitKeys.company(companyId) });
    },
  });
}
