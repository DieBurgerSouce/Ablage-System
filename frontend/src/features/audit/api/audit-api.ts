/**
 * Audit Trail API Client
 *
 * API-Funktionen fuer das Audit-Protokoll.
 */

import { useQuery } from "@tanstack/react-query";

const ADMIN_API_BASE = "/api/v1/admin/audit";
const AUDIT_API_BASE = "/api/v1/audit-trail";

// =============================================================================
// Types
// =============================================================================

export interface AuditLogView {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  success: boolean;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogView[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface AuditStats {
  total_events: number;
  unique_actors: number;
  events_by_type: Record<string, number>;
  events_by_day: Record<string, number>;
  most_active_users: Array<{
    user_id: string;
    user_email: string;
    count: number;
  }>;
}

export interface EventTypeConfig {
  [eventType: string]: {
    label: string;
    description: string;
    severity: string;
  };
}

export interface AuditFilters {
  page?: number;
  per_page?: number;
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  ip_address?: string;
  from_date?: string;
  to_date?: string;
  success?: boolean;
  sort_by?: "created_at" | "action" | "user_id";
  sort_order?: "asc" | "desc";
}

// =============================================================================
// API Functions
// =============================================================================

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    credentials: "include",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchAuditLogs(
  filters: AuditFilters = {}
): Promise<AuditLogListResponse> {
  const params = new URLSearchParams();

  if (filters.page) params.set("page", String(filters.page));
  if (filters.per_page) params.set("per_page", String(filters.per_page));
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.action) params.set("action", filters.action);
  if (filters.resource_type)
    params.set("resource_type", filters.resource_type);
  if (filters.resource_id) params.set("resource_id", filters.resource_id);
  if (filters.ip_address) params.set("ip_address", filters.ip_address);
  if (filters.from_date) params.set("from_date", filters.from_date);
  if (filters.to_date) params.set("to_date", filters.to_date);
  if (filters.success !== undefined)
    params.set("success", String(filters.success));
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);

  const queryString = params.toString();
  const url = queryString
    ? `${ADMIN_API_BASE}/logs?${queryString}`
    : `${ADMIN_API_BASE}/logs`;

  return fetchJson<AuditLogListResponse>(url);
}

export async function fetchAuditStats(days?: number): Promise<AuditStats> {
  const params = days ? `?days=${days}` : "";
  return fetchJson<AuditStats>(`${AUDIT_API_BASE}/stats${params}`);
}

export async function fetchEventTypes(): Promise<EventTypeConfig> {
  return fetchJson<EventTypeConfig>(`${AUDIT_API_BASE}/event-types`);
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useAuditLogs(filters: AuditFilters = {}) {
  return useQuery({
    queryKey: ["audit-logs", filters],
    queryFn: () => fetchAuditLogs(filters),
    refetchInterval: 60000, // Auto-refresh every 60s
  });
}

export function useAuditStats(days?: number) {
  return useQuery({
    queryKey: ["audit-stats", days],
    queryFn: () => fetchAuditStats(days),
    refetchInterval: 60000,
  });
}

export function useEventTypes() {
  return useQuery({
    queryKey: ["audit-event-types"],
    queryFn: fetchEventTypes,
    staleTime: 300000, // 5 minutes - event types rarely change
  });
}
