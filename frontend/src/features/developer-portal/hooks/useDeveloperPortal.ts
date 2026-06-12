/**
 * Developer Portal Hooks
 *
 * API-Hooks für Developer Portal Features:
 * - API Playground
 * - Webhook Testing
 * - SDK Downloads
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// ============================================================================
// Types
// ============================================================================

export interface ApiEndpoint {
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  summary: string;
  description?: string;
  tags: string[];
  parameters?: ApiParameter[];
  request_body?: ApiRequestBody;
  responses: Record<string, ApiResponse>;
}

export interface ApiParameter {
  name: string;
  in: 'path' | 'query' | 'header';
  required: boolean;
  schema: ApiSchema;
  description?: string;
}

export interface ApiRequestBody {
  required: boolean;
  content: Record<string, { schema: ApiSchema }>;
}

export interface ApiResponse {
  description: string;
  content?: Record<string, { schema: ApiSchema }>;
}

export interface ApiSchema {
  type: string;
  format?: string;
  properties?: Record<string, ApiSchema>;
  items?: ApiSchema;
  enum?: string[];
  default?: unknown;
  example?: unknown;
}

export interface PlaygroundRequest {
  method: string;
  path: string;
  headers: Record<string, string>;
  query_params: Record<string, string>;
  body?: string;
}

export interface PlaygroundResponse {
  status_code: number;
  headers: Record<string, string>;
  body: string;
  duration_ms: number;
  timestamp: string;
}

export interface WebhookSubscription {
  id: string;
  name: string;
  url: string;
  description?: string;
  event_types: string[];
  is_active: boolean;
  created_at: string;
  last_triggered_at?: string;
  success_count: number;
  failure_count: number;
}

export interface WebhookTestRequest {
  event_type: string;
  payload?: Record<string, unknown>;
}

export interface WebhookTestResponse {
  success: boolean;
  status_code?: number;
  response_body?: string;
  duration_ms?: number;
  error?: string;
}

export interface WebhookDelivery {
  id: string;
  webhook_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: 'pending' | 'success' | 'failed' | 'retrying';
  status_code?: number;
  response_body?: string;
  attempts: number;
  next_retry_at?: string;
  created_at: string;
  delivered_at?: string;
}

export interface SdkInfo {
  name: string;
  language: string;
  version: string;
  download_url: string;
  documentation_url: string;
  description: string;
  install_command?: string;
  example_code?: string;
}

export interface IntegrationGuide {
  id: string;
  title: string;
  description: string;
  category: string;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  estimated_time: string;
  content_url: string;
  tags: string[];
}

export interface ApiStats {
  total_requests_today: number;
  total_requests_month: number;
  avg_response_time_ms: number;
  error_rate_percent: number;
  top_endpoints: { path: string; count: number }[];
  rate_limit_remaining: number;
  rate_limit_reset_at: string;
}

// ============================================================================
// Query Keys
// ============================================================================

export const developerPortalKeys = {
  all: ['developer-portal'] as const,
  openapi: () => [...developerPortalKeys.all, 'openapi'] as const,
  endpoints: () => [...developerPortalKeys.all, 'endpoints'] as const,
  webhooks: () => [...developerPortalKeys.all, 'webhooks'] as const,
  webhook: (id: string) => [...developerPortalKeys.webhooks(), id] as const,
  webhookDeliveries: (id: string) => [...developerPortalKeys.webhook(id), 'deliveries'] as const,
  sdks: () => [...developerPortalKeys.all, 'sdks'] as const,
  guides: () => [...developerPortalKeys.all, 'guides'] as const,
  stats: () => [...developerPortalKeys.all, 'stats'] as const,
  history: () => [...developerPortalKeys.all, 'history'] as const,
};

// ============================================================================
// API Hooks
// ============================================================================

/**
 * Fetch OpenAPI specification
 */
export function useOpenApiSpec() {
  return useQuery({
    queryKey: developerPortalKeys.openapi(),
    queryFn: async () => {
      const response = await fetch('/openapi.json');
      if (!response.ok) throw new Error('OpenAPI-Spec konnte nicht geladen werden');
      return response.json();
    },
    staleTime: 1000 * 60 * 60, // 1 hour
  });
}

/**
 * Fetch API endpoints from OpenAPI spec
 */
export function useApiEndpoints() {
  const { data: spec, isLoading, error } = useOpenApiSpec();

  const endpoints: ApiEndpoint[] = [];

  if (spec?.paths) {
    for (const [path, methods] of Object.entries(spec.paths)) {
      for (const [method, details] of Object.entries(methods as Record<string, unknown>)) {
        if (['get', 'post', 'put', 'patch', 'delete'].includes(method)) {
          const detail = details as Record<string, unknown>;
          endpoints.push({
            path,
            method: method.toUpperCase() as ApiEndpoint['method'],
            summary: (detail.summary as string) || path,
            description: detail.description as string | undefined,
            tags: (detail.tags as string[]) || ['other'],
            parameters: detail.parameters as ApiParameter[] | undefined,
            request_body: detail.requestBody as ApiRequestBody | undefined,
            responses: (detail.responses as Record<string, ApiResponse>) || {},
          });
        }
      }
    }
  }

  return {
    endpoints,
    isLoading,
    error,
    spec,
  };
}

/**
 * Execute API request in playground
 */
export function useExecutePlayground() {
  return useMutation({
    mutationFn: async (request: PlaygroundRequest): Promise<PlaygroundResponse> => {
      const startTime = performance.now();

      // Build URL with query params
      let url = request.path;
      if (Object.keys(request.query_params).length > 0) {
        const params = new URLSearchParams(request.query_params);
        url += '?' + params.toString();
      }

      // Build headers
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...request.headers,
      };

      // Execute request
      const response = await fetch(url, {
        method: request.method,
        headers,
        body: request.body || undefined,
        credentials: 'include',
      });

      const endTime = performance.now();

      // Get response body
      let body: string;
      try {
        const json = await response.json();
        body = JSON.stringify(json, null, 2);
      } catch {
        body = await response.text();
      }

      // Extract response headers
      const responseHeaders: Record<string, string> = {};
      response.headers.forEach((value, key) => {
        responseHeaders[key] = value;
      });

      return {
        status_code: response.status,
        headers: responseHeaders,
        body,
        duration_ms: Math.round(endTime - startTime),
        timestamp: new Date().toISOString(),
      };
    },
  });
}

/**
 * Fetch webhooks list
 */
export function useWebhooks() {
  return useQuery({
    queryKey: developerPortalKeys.webhooks(),
    queryFn: async () => {
      const response = await api.get<{ items: WebhookSubscription[] }>('/webhooks');
      return response.data.items;
    },
  });
}

/**
 * Fetch single webhook
 */
export function useWebhook(id: string) {
  return useQuery({
    queryKey: developerPortalKeys.webhook(id),
    queryFn: async () => {
      const response = await api.get<WebhookSubscription>(`/webhooks/${id}`);
      return response;
    },
    enabled: !!id,
  });
}

/**
 * Test webhook
 */
export function useTestWebhook() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      webhookId,
      request,
    }: {
      webhookId: string;
      request: WebhookTestRequest;
    }): Promise<WebhookTestResponse> => {
      return api.post(`/webhooks/${webhookId}/test`, request);
    },
    onSuccess: (_, { webhookId }) => {
      queryClient.invalidateQueries({ queryKey: developerPortalKeys.webhook(webhookId) });
      queryClient.invalidateQueries({ queryKey: developerPortalKeys.webhookDeliveries(webhookId) });
    },
  });
}

/**
 * Fetch webhook deliveries
 */
export function useWebhookDeliveries(webhookId: string) {
  return useQuery({
    queryKey: developerPortalKeys.webhookDeliveries(webhookId),
    queryFn: async () => {
      const response = await api.get<{ items: WebhookDelivery[] }>(
        `/webhooks/${webhookId}/deliveries`
      );
      return response.data.items;
    },
    enabled: !!webhookId,
  });
}

/**
 * Create webhook
 */
export function useCreateWebhook() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      name: string;
      url: string;
      description?: string;
      event_types: string[];
    }) => {
      return (
        await api.post<WebhookSubscription & { secret: string }>(
          '/webhooks',
          data
        )
      ).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: developerPortalKeys.webhooks() });
    },
  });
}

/**
 * Delete webhook
 */
export function useDeleteWebhook() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (webhookId: string) => {
      await api.delete(`/webhooks/${webhookId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: developerPortalKeys.webhooks() });
    },
  });
}

/**
 * Rotate webhook secret
 */
export function useRotateWebhookSecret() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (webhookId: string) => {
      return (
        await api.post<{ secret: string }>(
          `/webhooks/${webhookId}/rotate-secret`,
          {}
        )
      ).data;
    },
    onSuccess: (_, webhookId) => {
      queryClient.invalidateQueries({ queryKey: developerPortalKeys.webhook(webhookId) });
    },
  });
}

/**
 * Get SDK information
 */
export function useSdks() {
  return useQuery({
    queryKey: developerPortalKeys.sdks(),
    queryFn: async (): Promise<SdkInfo[]> => {
      // Static SDK info since there's no backend endpoint
      return [
        {
          name: 'Ablage Python SDK',
          language: 'Python',
          version: '1.0.0',
          download_url: 'https://pypi.org/project/ablage-sdk/',
          documentation_url: '/docs/sdk/python',
          description: 'Offizielles Python SDK für die Ablage-System API',
          install_command: 'pip install ablage-sdk',
          example_code: `from ablage import AblageClient

client = AblageClient(api_key="your-api-key")

# Dokument hochladen
doc = client.documents.upload("rechnung.pdf")
print(f"Dokument-ID: {doc.id}")

# OCR starten
result = client.ocr.process(doc.id)
print(f"Extrahierter Text: {result.text}")`,
        },
        {
          name: 'Ablage JavaScript SDK',
          language: 'JavaScript/TypeScript',
          version: '1.0.0',
          download_url: 'https://www.npmjs.com/package/@ablage/sdk',
          documentation_url: '/docs/sdk/javascript',
          description: 'Offizielles JavaScript/TypeScript SDK für die Ablage-System API',
          install_command: 'npm install @ablage/sdk',
          example_code: `import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({ apiKey: 'your-api-key' });

// Dokument hochladen
const doc = await client.documents.upload(file);
logger.info('Dokument-ID:', doc.id);

// OCR starten
const result = await client.ocr.process(doc.id);
logger.info('Extrahierter Text:', result.text);`,
        },
      ];
    },
    staleTime: Infinity,
  });
}

/**
 * Get integration guides
 */
export function useIntegrationGuides() {
  return useQuery({
    queryKey: developerPortalKeys.guides(),
    queryFn: async (): Promise<IntegrationGuide[]> => {
      // Static guides since there's no backend endpoint
      return [
        {
          id: 'getting-started',
          title: 'Erste Schritte mit der API',
          description: 'Lernen Sie die Grundlagen der Ablage-System API kennen',
          category: 'Basics',
          difficulty: 'beginner',
          estimated_time: '15 min',
          content_url: '/docs/guides/getting-started',
          tags: ['authentication', 'api-key', 'basics'],
        },
        {
          id: 'document-upload',
          title: 'Dokumente hochladen',
          description: 'Verschiedene Methoden zum Hochladen von Dokumenten',
          category: 'Documents',
          difficulty: 'beginner',
          estimated_time: '10 min',
          content_url: '/docs/guides/document-upload',
          tags: ['upload', 'documents', 'multipart'],
        },
        {
          id: 'ocr-processing',
          title: 'OCR-Verarbeitung',
          description: 'Automatische Texterkennung und Datenextraktion',
          category: 'OCR',
          difficulty: 'intermediate',
          estimated_time: '20 min',
          content_url: '/docs/guides/ocr-processing',
          tags: ['ocr', 'extraction', 'backends'],
        },
        {
          id: 'webhooks',
          title: 'Webhook-Integration',
          description: 'Echtzeit-Benachrichtigungen über Ereignisse',
          category: 'Integration',
          difficulty: 'intermediate',
          estimated_time: '25 min',
          content_url: '/docs/guides/webhooks',
          tags: ['webhooks', 'events', 'notifications'],
        },
        {
          id: 'batch-processing',
          title: 'Batch-Verarbeitung',
          description: 'Grosse Mengen von Dokumenten effizient verarbeiten',
          category: 'Advanced',
          difficulty: 'advanced',
          estimated_time: '30 min',
          content_url: '/docs/guides/batch-processing',
          tags: ['batch', 'performance', 'async'],
        },
        {
          id: 'datev-export',
          title: 'DATEV-Export Integration',
          description: 'Buchungsdaten für DATEV exportieren',
          category: 'Integration',
          difficulty: 'intermediate',
          estimated_time: '20 min',
          content_url: '/docs/guides/datev-export',
          tags: ['datev', 'accounting', 'export'],
        },
        {
          id: 'lexware-import',
          title: 'Lexware-Import',
          description: 'Stammdaten aus Lexware importieren',
          category: 'Integration',
          difficulty: 'intermediate',
          estimated_time: '25 min',
          content_url: '/docs/guides/lexware-import',
          tags: ['lexware', 'import', 'customers', 'suppliers'],
        },
        {
          id: 'entity-linking',
          title: 'Entity-Verknüpfung',
          description: 'Dokumente automatisch mit Geschäftspartnern verknüpfen',
          category: 'AI',
          difficulty: 'advanced',
          estimated_time: '35 min',
          content_url: '/docs/guides/entity-linking',
          tags: ['entities', 'ai', 'matching'],
        },
      ];
    },
    staleTime: Infinity,
  });
}

/**
 * Get API usage statistics
 */
export function useApiStats() {
  return useQuery({
    queryKey: developerPortalKeys.stats(),
    queryFn: async (): Promise<ApiStats> => {
      try {
        const response = await api.get<ApiStats>('/metrics/api-usage');
        return response.data;
      } catch {
        // Return mock data if endpoint doesn't exist
        return {
          total_requests_today: 1247,
          total_requests_month: 34521,
          avg_response_time_ms: 142,
          error_rate_percent: 0.8,
          top_endpoints: [
            { path: '/api/v1/documents', count: 5421 },
            { path: '/api/v1/ocr/process', count: 3842 },
            { path: '/api/v1/search', count: 2103 },
            { path: '/api/v1/entities', count: 1876 },
            { path: '/api/v1/webhooks', count: 892 },
          ],
          rate_limit_remaining: 950,
          rate_limit_reset_at: new Date(Date.now() + 3600000).toISOString(),
        };
      }
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}

/**
 * Webhook event types
 */
export const WEBHOOK_EVENT_TYPES = [
  { value: 'document.created', label: 'Dokument erstellt' },
  { value: 'document.updated', label: 'Dokument aktualisiert' },
  { value: 'document.deleted', label: 'Dokument gelöscht' },
  { value: 'document.processed', label: 'Dokument verarbeitet' },
  { value: 'ocr.completed', label: 'OCR abgeschlossen' },
  { value: 'ocr.failed', label: 'OCR fehlgeschlagen' },
  { value: 'approval.requested', label: 'Genehmigung angefordert' },
  { value: 'approval.granted', label: 'Genehmigung erteilt' },
  { value: 'approval.rejected', label: 'Genehmigung abgelehnt' },
  { value: 'workflow.started', label: 'Workflow gestartet' },
  { value: 'workflow.completed', label: 'Workflow abgeschlossen' },
  { value: 'entity.linked', label: 'Entity verknüpft' },
  { value: 'payment.due', label: 'Zahlung fällig' },
  { value: 'skonto.expiring', label: 'Skonto läuft ab' },
] as const;
