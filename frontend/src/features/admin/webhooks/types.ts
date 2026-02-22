/**
 * Webhook Types
 *
 * TypeScript-Typen fuer Outbound-Webhooks.
 * Abgeleitet von Backend-Schemas (app/api/v1/webhooks_outbound.py).
 */

// =============================================================================
// Sub-Types
// =============================================================================

export interface RetryPolicy {
  max_retries: number
  backoff_factor: number
  timeout_seconds: number
}

export const DEFAULT_RETRY_POLICY: RetryPolicy = {
  max_retries: 3,
  backoff_factor: 2,
  timeout_seconds: 30,
}

// =============================================================================
// API Request Types
// =============================================================================

export interface WebhookEndpointCreate {
  url: string
  description?: string
  event_types: string[]
  headers?: Record<string, string>
  retry_policy?: RetryPolicy
}

export interface WebhookEndpointUpdate {
  url?: string
  description?: string
  secret?: string
  event_types?: string[]
  headers?: Record<string, string>
  retry_policy?: RetryPolicy
  is_active?: boolean
}

export interface WebhookTestRequest {
  event_type: string
  payload?: Record<string, unknown>
}

export interface BulkReplayRequest {
  event_type: string
  from_date: string
  to_date: string
}

// =============================================================================
// API Response Types
// =============================================================================

export interface WebhookEndpointResponse {
  id: string
  company_id: string
  url: string
  description: string | null
  event_types: string[]
  is_active: boolean
  headers: Record<string, string> | null
  retry_policy: RetryPolicy
  created_at: string
  updated_at: string
}

export interface WebhookEndpointWithSecret extends WebhookEndpointResponse {
  secret: string
}

export type DeliveryStatus = 'pending' | 'delivered' | 'failed' | 'dlq'

export interface WebhookDeliveryResponse {
  id: string
  endpoint_id: string
  company_id: string
  event_type: string
  event_id: string
  status: DeliveryStatus
  attempts: number
  max_attempts: number
  response_status_code: number | null
  response_body: string | null
  last_attempt_at: string | null
  next_retry_at: string | null
  delivered_at: string | null
  created_at: string
}

export interface WebhookEventLogResponse {
  id: string
  company_id: string
  event_type: string
  source_table: string
  source_id: string
  created_at: string
}

export interface WebhookTestResponse {
  delivery_id: string
  status: string
  message: string
}

export interface PaginatedResponse {
  total: number
  page: number
  per_page: number
  has_more: boolean
}

export interface WebhookEndpointListResponse extends PaginatedResponse {
  items: WebhookEndpointResponse[]
}

export interface WebhookDeliveryListResponse extends PaginatedResponse {
  items: WebhookDeliveryResponse[]
}

export interface WebhookEventLogListResponse extends PaginatedResponse {
  items: WebhookEventLogResponse[]
}

// =============================================================================
// UI Constants
// =============================================================================

export const DELIVERY_STATUS_LABELS: Record<DeliveryStatus, string> = {
  pending: 'Ausstehend',
  delivered: 'Zugestellt',
  failed: 'Fehlgeschlagen',
  dlq: 'Dead Letter',
}

export const DELIVERY_STATUS_COLORS: Record<DeliveryStatus, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  delivered: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  dlq: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
}

export const COMMON_EVENT_TYPES = [
  'document.created',
  'document.updated',
  'document.deleted',
  'document.processed',
  'invoice.created',
  'invoice.updated',
  'invoice.paid',
  'entity.created',
  'entity.updated',
  'workflow.completed',
  'ocr.completed',
  'webhook.test',
]
