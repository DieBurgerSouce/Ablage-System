/**
 * Business Intelligence API
 *
 * REST API client for business intelligence operations.
 * Enables natural language queries for:
 * - Document searches
 * - Invoice analysis
 * - Entity statistics
 * - Payment predictions
 * - Trend analysis
 */

import { csrfHeaders } from '@/lib/auth/csrf';

// ==================== Types ====================

export type BIQueryType =
  | 'document_search'
  | 'invoice_analysis'
  | 'entity_statistics'
  | 'payment_prediction'
  | 'trend_analysis'
  | 'summary';

export type BITimeRange =
  | 'last_7_days'
  | 'last_30_days'
  | 'last_quarter'
  | 'last_year'
  | 'this_month'
  | 'this_quarter'
  | 'this_year'
  | 'all_time'
  | 'custom';

export interface BIQueryRequest {
  query: string;
  time_range?: BITimeRange;
  custom_start_date?: string;
  custom_end_date?: string;
  entity_id?: string;
  entity_name?: string;
  include_suggestions?: boolean;
}

export interface BIQueryResponse {
  query_type: BIQueryType;
  summary: string;
  data: unknown;
  suggestions: string[];
  query_time_ms: number;
}

export interface BIDocumentResult {
  document_id: string;
  filename: string;
  document_type: string | null;
  entity_name: string | null;
  created_at: string;
  match_reason: string;
  relevance_score: number;
}

export interface BIInvoiceAnalysis {
  total_count: number;
  total_amount: number;
  paid_count: number;
  paid_amount: number;
  open_count: number;
  open_amount: number;
  overdue_count: number;
  overdue_amount: number;
  average_payment_days: number | null;
  by_month: Array<{ month: string; count: number; amount: number }>;
  by_entity: Array<{ entity_id: string | null; count: number; amount: number }>;
}

export interface BIEntityStatistics {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  document_count: number;
  invoice_count: number;
  total_revenue: number;
  total_open: number;
  average_payment_days: number | null;
  risk_score: number | null;
  last_activity: string | null;
}

export interface BIPaymentPrediction {
  entity_id: string | null;
  entity_name: string | null;
  predicted_days: number;
  confidence: number;
  historical_avg_days: number;
  recent_trend: 'improving' | 'stable' | 'worsening' | 'unknown';
  factors: string[];
}

export interface BITrendDataPoint {
  period: string;
  value: number;
  count: number;
  change_percent: number | null;
}

export interface BITrendAnalysis {
  metric: string;
  time_range: string;
  total: number;
  average: number;
  trend_direction: 'up' | 'down' | 'stable';
  change_percent: number;
  data_points: BITrendDataPoint[];
}

export interface BIChatRequest {
  message: string;
  session_id?: string;
  context_type?: 'general' | 'customer' | 'document' | 'report';
  context_id?: string;
  enable_bi?: boolean;
  time_range?: BITimeRange;
  realtime?: boolean;
}

export interface BIChatSource {
  chunk_id: string;
  document_id: string;
  chunk_text: string;
  chunk_index: number;
  page_number: number | null;
  section_type: string | null;
  similarity: number;
  rerank_score: number | null;
}

export interface BIChatResponse {
  session_id: string;
  message: string;
  thinking_content: string | null;
  sources: BIChatSource[];
  bi_insights: BIQueryResponse | null;
  model_used: string;
  tokens_input: number;
  tokens_output: number;
  generation_time_ms: number;
}

// ==================== API Functions ====================

const API_BASE = '/api/v1/rag/bi';

/**
 * Make authenticated API request.
 *
 * G03: Cookie-Auth + CSRF. Der httpOnly-Auth-Cookie wird vom Browser
 * automatisch mitgesendet (credentials: 'include'). Bei state-changing
 * Requests wird zusaetzlich das CSRF-Double-Submit-Token gespiegelt.
 */
async function fetchWithAuth<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const isStateChanging =
    method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS';

  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(isStateChanging ? csrfHeaders() : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Anfrage fehlgeschlagen: ${response.status}`);
  }

  return response.json();
}

/**
 * Execute a natural language business intelligence query.
 *
 * @example
 * const result = await queryBI({ query: "Zeige alle offenen Rechnungen" });
 */
export async function queryBI(request: BIQueryRequest): Promise<BIQueryResponse> {
  return fetchWithAuth<BIQueryResponse>(`${API_BASE}/query`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Analyze invoices with aggregations.
 *
 * @example
 * const analysis = await analyzeInvoices({ time_range: 'this_year' });
 */
export async function analyzeInvoices(params: {
  time_range?: BITimeRange;
  entity_id?: string;
}): Promise<BIQueryResponse> {
  const searchParams = new URLSearchParams();
  if (params.time_range) searchParams.set('time_range', params.time_range);
  if (params.entity_id) searchParams.set('entity_id', params.entity_id);

  return fetchWithAuth<BIQueryResponse>(
    `${API_BASE}/invoices?${searchParams.toString()}`,
    { method: 'POST' }
  );
}

/**
 * Get statistics for a specific entity by ID.
 *
 * @example
 * const stats = await getEntityStatistics('entity-uuid');
 */
export async function getEntityStatistics(
  entityId: string
): Promise<BIQueryResponse> {
  return fetchWithAuth<BIQueryResponse>(`${API_BASE}/entity/${entityId}`);
}

/**
 * Search for entity and get statistics by name.
 *
 * @example
 * const stats = await searchEntityStatistics('Mueller GmbH');
 */
export async function searchEntityStatistics(
  name: string
): Promise<BIQueryResponse> {
  return fetchWithAuth<BIQueryResponse>(
    `${API_BASE}/entity/search/${encodeURIComponent(name)}`
  );
}

/**
 * Get payment prediction for an entity.
 *
 * @example
 * const prediction = await predictPayment('entity-uuid');
 */
export async function predictPayment(
  entityId: string
): Promise<BIQueryResponse> {
  return fetchWithAuth<BIQueryResponse>(
    `${API_BASE}/payment-prediction/${entityId}`
  );
}

/**
 * Analyze trends for a given metric.
 *
 * @example
 * const trends = await analyzeTrends({
 *   metric: 'revenue',
 *   time_range: 'last_year',
 *   group_by: 'month'
 * });
 */
export async function analyzeTrends(params: {
  metric?: 'revenue' | 'invoice_count';
  time_range?: BITimeRange;
  group_by?: 'month' | 'quarter' | 'year';
}): Promise<BIQueryResponse> {
  const searchParams = new URLSearchParams();
  if (params.metric) searchParams.set('metric', params.metric);
  if (params.time_range) searchParams.set('time_range', params.time_range);
  if (params.group_by) searchParams.set('group_by', params.group_by);

  return fetchWithAuth<BIQueryResponse>(
    `${API_BASE}/trends?${searchParams.toString()}`,
    { method: 'POST' }
  );
}

/**
 * Chat with combined RAG and Business Intelligence context.
 *
 * @example
 * const response = await biChat({
 *   message: "Wie entwickelt sich der Umsatz bei Mueller GmbH?",
 *   enable_bi: true,
 * });
 */
export async function biChat(request: BIChatRequest): Promise<BIChatResponse> {
  return fetchWithAuth<BIChatResponse>(`${API_BASE}/chat`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// ==================== React Query Keys ====================

export const biKeys = {
  all: ['bi'] as const,
  query: (query: string) => [...biKeys.all, 'query', query] as const,
  invoices: (timeRange?: string, entityId?: string) =>
    [...biKeys.all, 'invoices', timeRange, entityId] as const,
  entity: (id: string) => [...biKeys.all, 'entity', id] as const,
  entitySearch: (name: string) => [...biKeys.all, 'entity-search', name] as const,
  payment: (entityId: string) => [...biKeys.all, 'payment', entityId] as const,
  trends: (metric?: string, timeRange?: string, groupBy?: string) =>
    [...biKeys.all, 'trends', metric, timeRange, groupBy] as const,
  chat: () => [...biKeys.all, 'chat'] as const,
};

// ==================== React Query Hooks ====================

import { useQuery, useMutation, type UseQueryOptions } from '@tanstack/react-query';

/**
 * Hook for executing BI queries.
 */
export function useBIQuery(
  request: BIQueryRequest | null,
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.query(request?.query || ''),
    queryFn: () => {
      if (!request) throw new Error('Keine Anfrage');
      return queryBI(request);
    },
    enabled: !!request?.query,
    ...options,
  });
}

/**
 * Hook for invoice analysis.
 */
export function useInvoiceAnalysis(
  params: { time_range?: BITimeRange; entity_id?: string } = {},
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.invoices(params.time_range, params.entity_id),
    queryFn: () => analyzeInvoices(params),
    ...options,
  });
}

/**
 * Hook for entity statistics by ID.
 */
export function useEntityStatistics(
  entityId: string | null,
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.entity(entityId || ''),
    queryFn: () => {
      if (!entityId) throw new Error('Keine Entity-ID');
      return getEntityStatistics(entityId);
    },
    enabled: !!entityId,
    ...options,
  });
}

/**
 * Hook for entity statistics by name search.
 */
export function useEntitySearch(
  name: string | null,
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.entitySearch(name || ''),
    queryFn: () => {
      if (!name) throw new Error('Kein Name');
      return searchEntityStatistics(name);
    },
    enabled: !!name && name.length >= 2,
    ...options,
  });
}

/**
 * Hook for payment predictions.
 */
export function usePaymentPrediction(
  entityId: string | null,
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.payment(entityId || ''),
    queryFn: () => {
      if (!entityId) throw new Error('Keine Entity-ID');
      return predictPayment(entityId);
    },
    enabled: !!entityId,
    ...options,
  });
}

/**
 * Hook for trend analysis.
 */
export function useTrendAnalysis(
  params: {
    metric?: 'revenue' | 'invoice_count';
    time_range?: BITimeRange;
    group_by?: 'month' | 'quarter' | 'year';
  } = {},
  options?: Omit<UseQueryOptions<BIQueryResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: biKeys.trends(params.metric, params.time_range, params.group_by),
    queryFn: () => analyzeTrends(params),
    ...options,
  });
}

/**
 * Mutation hook for BI chat.
 */
export function useBIChat() {
  return useMutation({
    mutationFn: biChat,
  });
}

/**
 * Mutation hook for ad-hoc BI queries.
 */
export function useBIQueryMutation() {
  return useMutation({
    mutationFn: queryBI,
  });
}
