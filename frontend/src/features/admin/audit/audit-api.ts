/**
 * Audit Log API Hooks
 *
 * TanStack Query hooks fuer Audit-Log Administration.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

// ==================== Types ====================

export interface AuditLogView {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  request_method: string | null;
  request_path: string | null;
  success: boolean;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogListResponse {
  logs: AuditLogView[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface AuditLogFilters {
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  ip_address?: string;
  success?: boolean;
  from_date?: string;
  to_date?: string;
}

export interface AuditStatsResponse {
  total_actions: number;
  unique_users: number;
  actions_by_type: Record<string, number>;
  actions_by_user: Array<{ user_email: string; count: number }>;
  success_rate: number;
  error_count: number;
  period_days: number;
}

export type AuditSortField = 'created_at' | 'action' | 'user_email' | 'resource_type';
export type SortOrder = 'asc' | 'desc';

export interface AuditQueryParams extends AuditLogFilters {
  page?: number;
  per_page?: number;
  sort_by?: AuditSortField;
  sort_order?: SortOrder;
}

// ==================== Query Keys ====================

export const auditKeys = {
  all: ['admin', 'audit'] as const,
  logs: (params: AuditQueryParams) => [...auditKeys.all, 'logs', params] as const,
  log: (id: string) => [...auditKeys.all, 'log', id] as const,
  stats: (days: number) => [...auditKeys.all, 'stats', days] as const,
  userTrail: (userId: string) => [...auditKeys.all, 'user-trail', userId] as const,
};

// ==================== API Functions ====================

async function fetchAuditLogs(params: AuditQueryParams): Promise<AuditLogListResponse> {
  const searchParams = new URLSearchParams();

  if (params.page) searchParams.set('page', String(params.page));
  if (params.per_page) searchParams.set('per_page', String(params.per_page));
  if (params.user_id) searchParams.set('user_id', params.user_id);
  if (params.action) searchParams.set('action', params.action);
  if (params.resource_type) searchParams.set('resource_type', params.resource_type);
  if (params.resource_id) searchParams.set('resource_id', params.resource_id);
  if (params.ip_address) searchParams.set('ip_address', params.ip_address);
  if (params.success !== undefined) searchParams.set('success', String(params.success));
  if (params.from_date) searchParams.set('from_date', params.from_date);
  if (params.to_date) searchParams.set('to_date', params.to_date);
  if (params.sort_by) searchParams.set('sort_by', params.sort_by);
  if (params.sort_order) searchParams.set('sort_order', params.sort_order);

  return apiClient.get(`/admin/audit/logs?${searchParams.toString()}`);
}

async function fetchAuditLog(id: string): Promise<AuditLogView> {
  return apiClient.get(`/admin/audit/logs/${id}`);
}

async function fetchAuditStats(days: number): Promise<AuditStatsResponse> {
  return apiClient.get(`/admin/audit/stats?days=${days}`);
}

async function fetchUserAuditTrail(
  userId: string,
  limit: number = 100
): Promise<{ actions: AuditLogView[]; admin_actions: AuditLogView[] }> {
  return apiClient.get(`/admin/audit/users/${userId}/trail?limit=${limit}`);
}

async function exportAuditLogs(
  format: 'csv' | 'json',
  filters: AuditLogFilters
): Promise<Blob> {
  const searchParams = new URLSearchParams();
  searchParams.set('format', format);

  if (filters.user_id) searchParams.set('user_id', filters.user_id);
  if (filters.action) searchParams.set('action', filters.action);
  if (filters.resource_type) searchParams.set('resource_type', filters.resource_type);
  if (filters.success !== undefined) searchParams.set('success', String(filters.success));
  if (filters.from_date) searchParams.set('from_date', filters.from_date);
  if (filters.to_date) searchParams.set('to_date', filters.to_date);

  const response = await fetch(`/api/v1/admin/audit/export?${searchParams.toString()}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error('Export fehlgeschlagen');
  }

  return response.blob();
}

// ==================== Hooks ====================

export function useAuditLogs(params: AuditQueryParams = {}) {
  return useQuery({
    queryKey: auditKeys.logs(params),
    queryFn: () => fetchAuditLogs(params),
    staleTime: 30_000, // 30 seconds
  });
}

export function useAuditLog(id: string | undefined) {
  return useQuery({
    queryKey: auditKeys.log(id ?? ''),
    queryFn: () => fetchAuditLog(id!),
    enabled: !!id,
  });
}

export function useAuditStats(days: number = 30) {
  return useQuery({
    queryKey: auditKeys.stats(days),
    queryFn: () => fetchAuditStats(days),
    staleTime: 60_000, // 1 minute
  });
}

export function useUserAuditTrail(userId: string | undefined, limit: number = 100) {
  return useQuery({
    queryKey: auditKeys.userTrail(userId ?? ''),
    queryFn: () => fetchUserAuditTrail(userId!, limit),
    enabled: !!userId,
  });
}

export function useExportAuditLogs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ format, filters }: { format: 'csv' | 'json'; filters: AuditLogFilters }) =>
      exportAuditLogs(format, filters),
    onSuccess: (blob, { format }) => {
      // Trigger download
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit_logs_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
  });
}
