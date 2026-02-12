/**
 * Alert Center API Client
 *
 * API-Funktionen für das zentrale Alert-Management.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API_BASE = "/api/v1/alerts";

// =============================================================================
// Types
// =============================================================================

export type AlertCategory =
  | "fraud"
  | "risk"
  | "compliance"
  | "deadline"
  | "system"
  | "security"
  | "quality"
  | "workflow";

export type AlertSeverity = "info" | "low" | "medium" | "high" | "critical";

export type AlertStatus =
  | "new"
  | "acknowledged"
  | "in_progress"
  | "resolved"
  | "dismissed"
  | "escalated";

export interface Alert {
  id: string;
  alert_code: string;
  title: string;
  message: string;
  category: AlertCategory;
  severity: AlertSeverity;
  status: AlertStatus;
  source_type: string | null;
  source_id: string | null;
  document_id: string | null;
  entity_id: string | null;
  company_id: string;
  assigned_to_id: string | null;
  metadata: Record<string, unknown>;
  context: Record<string, unknown>;
  available_actions: string[];
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  escalation_level: number;
  email_sent: boolean;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlertStats {
  total_active: number;
  new_count: number;
  acknowledged_count: number;
  in_progress_count: number;
  resolved_count: number;
  critical_count: number;
  recent_24h_count: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
}

export interface AlertFilters {
  category?: AlertCategory;
  severity?: AlertSeverity;
  status?: AlertStatus;
  assigned_to_id?: string;
  source_type?: string;
  unread_only?: boolean;
  limit?: number;
  offset?: number;
  order_by?: string;
  order_desc?: boolean;
}

export interface BulkActionRequest {
  alert_ids: string[];
  action: "acknowledge" | "dismiss" | "resolve";
  resolution_note?: string;
  reason?: string;
}

export interface BulkActionResponse {
  success_count: number;
  error_count: number;
  total: number;
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

export async function fetchAlerts(
  filters: AlertFilters = {}
): Promise<AlertListResponse> {
  const params = new URLSearchParams();

  if (filters.category) params.set("category", filters.category);
  if (filters.severity) params.set("severity", filters.severity);
  if (filters.status) params.set("status", filters.status);
  if (filters.assigned_to_id)
    params.set("assigned_to_id", filters.assigned_to_id);
  if (filters.source_type) params.set("source_type", filters.source_type);
  if (filters.unread_only) params.set("unread_only", "true");
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  if (filters.order_by) params.set("order_by", filters.order_by);
  if (filters.order_desc !== undefined)
    params.set("order_desc", String(filters.order_desc));

  const queryString = params.toString();
  const url = queryString ? `${API_BASE}?${queryString}` : API_BASE;

  return fetchJson<AlertListResponse>(url);
}

export async function fetchAlertStats(): Promise<AlertStats> {
  return fetchJson<AlertStats>(`${API_BASE}/stats`);
}

export async function fetchAlert(alertId: string): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}`);
}

export async function acknowledgeAlert(alertId: string): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}/acknowledge`, {
    method: "POST",
  });
}

export async function dismissAlert(
  alertId: string,
  reason?: string
): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}/dismiss`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function resolveAlert(
  alertId: string,
  resolutionNote?: string,
  resolutionAction?: string
): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      resolution_note: resolutionNote,
      resolution_action: resolutionAction,
    }),
  });
}

export async function escalateAlert(
  alertId: string,
  escalateToId: string,
  reason?: string
): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}/escalate`, {
    method: "POST",
    body: JSON.stringify({
      escalate_to_id: escalateToId,
      reason,
    }),
  });
}

export async function assignAlert(
  alertId: string,
  assignedToId: string
): Promise<Alert> {
  return fetchJson<Alert>(`${API_BASE}/${alertId}/assign`, {
    method: "POST",
    body: JSON.stringify({ assigned_to_id: assignedToId }),
  });
}

export async function bulkAction(
  request: BulkActionRequest
): Promise<BulkActionResponse> {
  return fetchJson<BulkActionResponse>(`${API_BASE}/bulk`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => fetchAlerts(filters),
    refetchInterval: 30000, // Auto-refresh every 30s
  });
}

export function useAlertStats() {
  return useQuery({
    queryKey: ["alerts", "stats"],
    queryFn: fetchAlertStats,
    refetchInterval: 30000,
  });
}

export function useAlert(alertId: string) {
  return useQuery({
    queryKey: ["alerts", alertId],
    queryFn: () => fetchAlert(alertId),
    enabled: !!alertId,
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useDismissAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ alertId, reason }: { alertId: string; reason?: string }) =>
      dismissAlert(alertId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useResolveAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      alertId,
      resolutionNote,
      resolutionAction,
    }: {
      alertId: string;
      resolutionNote?: string;
      resolutionAction?: string;
    }) => resolveAlert(alertId, resolutionNote, resolutionAction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useEscalateAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      alertId,
      escalateToId,
      reason,
    }: {
      alertId: string;
      escalateToId: string;
      reason?: string;
    }) => escalateAlert(alertId, escalateToId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useBulkAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bulkAction,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}
