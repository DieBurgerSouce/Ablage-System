/**
 * Daily Briefing API Client
 *
 * API-Funktionen fuer das Tagesbriefing (AI Daily Insights).
 * Endpoint: /api/v1/daily-insights
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

// =============================================================================
// Types
// =============================================================================

export interface InsightFactor {
  name: string;
  contribution: number;
  value: string;
  explanation: string;
}

export interface DailyInsight {
  id: string;
  insight_type: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  message: string;
  explanation: string;
  recommendation: string;
  factors: InsightFactor[];
  confidence: number;
  impact_value: number | null;
  deadline: string | null;
  related_entity_id: string | null;
  related_entity_name: string | null;
  related_document_id: string | null;
  action_url: string | null;
  created_at: string;
}

export interface DailyInsightListResponse {
  insights: DailyInsight[];
  total_count: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  generated_at: string | null;
}

export interface InsightGenerationResponse {
  success: boolean;
  total_generated: number;
  by_type: Record<string, number>;
  duration_ms: number;
}

export interface GeneratorConfig {
  name: string;
  enabled: boolean;
  priority: number;
  max_insights: number;
  description: string;
}

// =============================================================================
// Insight Type Constants
// =============================================================================

export const INSIGHT_TYPES = [
  "cashflow_warning",
  "contract_expiring",
  "payment_risk",
  "skonto_deadline",
  "compliance_reminder",
  "overdue_invoice",
] as const;

export type InsightType = (typeof INSIGHT_TYPES)[number];

export const INSIGHT_TYPE_LABELS: Record<InsightType, string> = {
  cashflow_warning: "Cashflow",
  contract_expiring: "Vertraege",
  payment_risk: "Zahlungen",
  skonto_deadline: "Skonto",
  compliance_reminder: "Compliance",
  overdue_invoice: "Ueberfaellig",
};

export const INSIGHT_TYPE_ENDPOINTS: Record<InsightType, string> = {
  cashflow_warning: "cashflow",
  contract_expiring: "contracts",
  payment_risk: "payments",
  skonto_deadline: "skonto",
  compliance_reminder: "compliance",
  overdue_invoice: "overdue",
};

// =============================================================================
// API Functions
// =============================================================================

const API_BASE = "/daily-insights";

async function fetchAllInsights(
  severity?: string
): Promise<DailyInsightListResponse> {
  const params: Record<string, string> = {};
  if (severity) params.severity = severity;
  const response = await apiClient.get<DailyInsightListResponse>(API_BASE, {
    params,
  });
  return response.data;
}

async function fetchInsightsByType(
  type: InsightType
): Promise<DailyInsightListResponse> {
  const endpoint = INSIGHT_TYPE_ENDPOINTS[type];
  const response = await apiClient.get<DailyInsightListResponse>(
    `${API_BASE}/${endpoint}`
  );
  return response.data;
}

async function generateInsights(): Promise<InsightGenerationResponse> {
  const response = await apiClient.post<InsightGenerationResponse>(
    `${API_BASE}/generate`,
    { days_ahead: 30 }
  );
  return response.data;
}

async function fetchGeneratorConfig(): Promise<GeneratorConfig[]> {
  const response = await apiClient.get<GeneratorConfig[]>(
    `${API_BASE}/config`
  );
  return response.data;
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useDailyInsights(severity?: string) {
  return useQuery({
    queryKey: ["daily-insights", severity],
    queryFn: () => fetchAllInsights(severity),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

export function useDailyInsightsByType(type: InsightType) {
  return useQuery({
    queryKey: ["daily-insights", "type", type],
    queryFn: () => fetchInsightsByType(type),
    staleTime: 5 * 60 * 1000,
  });
}

export function useGenerateDailyInsights() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: generateInsights,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["daily-insights"] });
    },
  });
}

export function useGeneratorConfig() {
  return useQuery({
    queryKey: ["daily-insights", "config"],
    queryFn: fetchGeneratorConfig,
    staleTime: 5 * 60 * 1000,
  });
}
