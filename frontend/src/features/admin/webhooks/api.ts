/**
 * Webhook API
 *
 * TanStack Query Hooks fuer Outbound-Webhook-Management.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  WebhookEndpointCreate,
  WebhookEndpointUpdate,
  WebhookEndpointListResponse,
  WebhookEndpointWithSecret,
  WebhookEndpointResponse,
  WebhookDeliveryListResponse,
  WebhookDeliveryResponse,
  WebhookEventLogListResponse,
  WebhookTestRequest,
  WebhookTestResponse,
  BulkReplayRequest,
} from './types'

// =============================================================================
// Query Keys
// =============================================================================

export const WEBHOOK_KEYS = {
  all: ['webhooks'] as const,
  endpoints: (params?: { page?: number; per_page?: number; include_inactive?: boolean }) =>
    [...WEBHOOK_KEYS.all, 'endpoints', params] as const,
  deliveries: (endpointId: string, params?: { page?: number; per_page?: number }) =>
    [...WEBHOOK_KEYS.all, 'deliveries', endpointId, params] as const,
  dlq: (params?: { page?: number; per_page?: number }) =>
    [...WEBHOOK_KEYS.all, 'dlq', params] as const,
  events: (params?: { page?: number; per_page?: number; event_type?: string; from_date?: string; to_date?: string }) =>
    [...WEBHOOK_KEYS.all, 'events', params] as const,
}

const BASE = '/api/v1/webhooks/outbound'

// =============================================================================
// Endpoint Queries
// =============================================================================

export function useWebhookEndpoints(params?: {
  page?: number
  per_page?: number
  include_inactive?: boolean
}) {
  return useQuery({
    queryKey: WEBHOOK_KEYS.endpoints(params),
    queryFn: async () => {
      const response = await api.get<WebhookEndpointListResponse>(
        `${BASE}/endpoints`,
        { params }
      )
      return response.data
    },
    staleTime: 15_000,
  })
}

// =============================================================================
// Endpoint Mutations
// =============================================================================

export function useCreateEndpoint() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: WebhookEndpointCreate) => {
      const response = await api.post<WebhookEndpointWithSecret>(
        `${BASE}/endpoints`,
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

export function useUpdateEndpoint() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: WebhookEndpointUpdate }) => {
      const response = await api.put<WebhookEndpointResponse>(
        `${BASE}/endpoints/${id}`,
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

export function useDeleteEndpoint() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${BASE}/endpoints/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

// =============================================================================
// Test
// =============================================================================

export function useTestEndpoint() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: WebhookTestRequest }) => {
      const response = await api.post<WebhookTestResponse>(
        `${BASE}/endpoints/${id}/test`,
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

// =============================================================================
// Deliveries
// =============================================================================

export function useEndpointDeliveries(
  endpointId: string,
  params?: { page?: number; per_page?: number }
) {
  return useQuery({
    queryKey: WEBHOOK_KEYS.deliveries(endpointId, params),
    queryFn: async () => {
      const response = await api.get<WebhookDeliveryListResponse>(
        `${BASE}/endpoints/${endpointId}/deliveries`,
        { params }
      )
      return response.data
    },
    enabled: !!endpointId,
    staleTime: 10_000,
  })
}

// =============================================================================
// Dead Letter Queue
// =============================================================================

export function useDLQ(params?: { page?: number; per_page?: number }) {
  return useQuery({
    queryKey: WEBHOOK_KEYS.dlq(params),
    queryFn: async () => {
      const response = await api.get<WebhookDeliveryListResponse>(
        `${BASE}/dlq`,
        { params }
      )
      return response.data
    },
    staleTime: 10_000,
  })
}

export function useRetryDLQ() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (deliveryId: string) => {
      const response = await api.post<WebhookDeliveryResponse>(
        `${BASE}/dlq/${deliveryId}/retry`
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

// =============================================================================
// Event Log & Replay
// =============================================================================

export function useEventLog(params?: {
  page?: number
  per_page?: number
  event_type?: string
  from_date?: string
  to_date?: string
}) {
  return useQuery({
    queryKey: WEBHOOK_KEYS.events(params),
    queryFn: async () => {
      const response = await api.get<WebhookEventLogListResponse>(
        `${BASE}/events`,
        { params }
      )
      return response.data
    },
    staleTime: 10_000,
  })
}

export function useReplayEvent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (eventId: string) => {
      const response = await api.post<{ event_id: string; dispatched: number; message: string }>(
        `${BASE}/events/${eventId}/replay`
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}

export function useBulkReplay() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: BulkReplayRequest) => {
      const response = await api.post<{
        event_type: string
        total_dispatched: number
        message: string
      }>(
        `${BASE}/events/replay/bulk`,
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WEBHOOK_KEYS.all })
    },
  })
}
