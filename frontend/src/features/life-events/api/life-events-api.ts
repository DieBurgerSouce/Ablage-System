/**
 * Life Events API Client
 *
 * API-Funktionen für den Lebenslagen-Assistenten.
 * Verwendet apiClient für automatische Retry-Logik und Token-Refresh.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';

// =============================================================================
// Types
// =============================================================================

export type LifeEventType =
  | 'umzug'
  | 'heirat'
  | 'kind'
  | 'jobwechsel'
  | 'ruhestand'
  | 'todesfall'
  | 'immobilienkauf'
  | 'scheidung';

export type LifeEventStatus = 'pending' | 'confirmed' | 'in_progress' | 'completed';

export type ChecklistPriority = 'high' | 'medium' | 'low';

export interface ChecklistItem {
  id: string;
  task: string;
  category: string;
  done: boolean;
  priority?: ChecklistPriority;
}

export interface FinancialImpact {
  estimated_cost: string;
  tax_deductible: boolean;
}

export interface Recommendation {
  title: string;
  description: string;
  priority?: ChecklistPriority;
}

export interface LifeEvent {
  id: string;
  event_type: LifeEventType;
  title: string;
  description: string | null;
  event_date: string;
  status: LifeEventStatus;
  detection_source: string;
  checklist: ChecklistItem[];
  recommendations: Recommendation[];
  financial_impact: FinancialImpact;
  created_at: string;
}

export interface LifeEventTypeInfo {
  title: string;
  description: string;
}

export interface LifeEventCreate {
  event_type: LifeEventType;
  event_date?: string;
  notes?: string;
}

export interface ChecklistItemUpdate {
  item_id: string;
  done: boolean;
}

// =============================================================================
// Constants
// =============================================================================

const BASE_URL = '/privat/life-events';

export const lifeEventQueryKeys = {
  all: ['life-events'] as const,
  types: () => [...lifeEventQueryKeys.all, 'types'] as const,
  list: (statusFilter?: string) => [...lifeEventQueryKeys.all, 'list', statusFilter] as const,
  detail: (id: string) => [...lifeEventQueryKeys.all, 'detail', id] as const,
  activeCount: () => [...lifeEventQueryKeys.all, 'active-count'] as const,
};

// =============================================================================
// API Functions
// =============================================================================

async function fetchEventTypes(): Promise<Record<string, LifeEventTypeInfo>> {
  const response = await apiClient.get<Record<string, LifeEventTypeInfo>>(`${BASE_URL}/types`);
  return response.data;
}

async function fetchLifeEvents(statusFilter?: string): Promise<LifeEvent[]> {
  const params: Record<string, string> = {};
  if (statusFilter) {
    params.status_filter = statusFilter;
  }
  const response = await apiClient.get<LifeEvent[]>(BASE_URL, { params });
  return response.data;
}

async function fetchLifeEvent(eventId: string): Promise<LifeEvent> {
  const response = await apiClient.get<LifeEvent>(`${BASE_URL}/${eventId}`);
  return response.data;
}

async function createLifeEvent(data: LifeEventCreate): Promise<LifeEvent> {
  const response = await apiClient.post<LifeEvent>(BASE_URL, data);
  return response.data;
}

async function updateChecklistItem(
  eventId: string,
  data: ChecklistItemUpdate
): Promise<LifeEvent> {
  const response = await apiClient.patch<LifeEvent>(
    `${BASE_URL}/${eventId}/checklist`,
    data
  );
  return response.data;
}

async function completeLifeEvent(eventId: string): Promise<LifeEvent> {
  const response = await apiClient.post<LifeEvent>(`${BASE_URL}/${eventId}/complete`);
  return response.data;
}

async function fetchActiveCount(): Promise<number> {
  const response = await apiClient.get<{ active_count: number }>(`${BASE_URL}/stats/active-count`);
  return response.data.active_count;
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useLifeEventTypes() {
  return useQuery({
    queryKey: lifeEventQueryKeys.types(),
    queryFn: fetchEventTypes,
    staleTime: 5 * 60 * 1000, // Types rarely change
  });
}

export function useLifeEvents(statusFilter?: string) {
  return useQuery({
    queryKey: lifeEventQueryKeys.list(statusFilter),
    queryFn: () => fetchLifeEvents(statusFilter),
  });
}

export function useLifeEvent(eventId: string) {
  return useQuery({
    queryKey: lifeEventQueryKeys.detail(eventId),
    queryFn: () => fetchLifeEvent(eventId),
    enabled: !!eventId,
  });
}

export function useActiveEventsCount() {
  return useQuery({
    queryKey: lifeEventQueryKeys.activeCount(),
    queryFn: fetchActiveCount,
  });
}

export function useCreateLifeEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createLifeEvent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: lifeEventQueryKeys.all });
    },
  });
}

export function useToggleChecklistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ eventId, itemId, done }: { eventId: string; itemId: string; done: boolean }) =>
      updateChecklistItem(eventId, { item_id: itemId, done }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: lifeEventQueryKeys.detail(variables.eventId),
      });
      queryClient.invalidateQueries({
        queryKey: lifeEventQueryKeys.list(),
      });
    },
  });
}

export function useCompleteLifeEvent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: completeLifeEvent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: lifeEventQueryKeys.all });
    },
  });
}
