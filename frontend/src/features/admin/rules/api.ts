/**
 * Business Rules API
 *
 * TanStack Query Hooks für Business Rules.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  BusinessRule,
  RuleListResponse,
  RuleCreateRequest,
  RuleUpdateRequest,
  RuleTestRequest,
  RuleTestResponse,
  OperatorsResponse,
  ExecutionLog,
} from './types'

const RULES_KEYS = {
  all: ['rules'] as const,
  list: (params?: { category?: string; is_active?: boolean; search?: string }) =>
    [...RULES_KEYS.all, 'list', params] as const,
  detail: (id: string) => [...RULES_KEYS.all, 'detail', id] as const,
  operators: () => [...RULES_KEYS.all, 'operators'] as const,
  logs: (params?: { rule_id?: string; document_id?: string }) =>
    [...RULES_KEYS.all, 'logs', params] as const,
}

/**
 * Regeln auflisten
 */
export function useRulesList(params?: {
  category?: string
  is_active?: boolean
  search?: string
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: RULES_KEYS.list(params),
    queryFn: async () => {
      const response = await api.get<RuleListResponse>('/api/v1/rules', {
        params,
      })
      return response.data
    },
    staleTime: 30_000,
  })
}

/**
 * Einzelne Regel abrufen
 */
export function useRule(id: string) {
  return useQuery({
    queryKey: RULES_KEYS.detail(id),
    queryFn: async () => {
      const response = await api.get<BusinessRule>(`/api/v1/rules/${id}`)
      return response.data
    },
    enabled: !!id,
  })
}

/**
 * Verfügbare Operatoren abrufen
 */
export function useOperators() {
  return useQuery({
    queryKey: RULES_KEYS.operators(),
    queryFn: async () => {
      const response = await api.get<OperatorsResponse>('/api/v1/rules/schema/operators')
      return response.data
    },
    staleTime: Infinity, // Schema ändert sich nicht
  })
}

/**
 * Regel erstellen
 */
export function useCreateRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: RuleCreateRequest) => {
      const response = await api.post<BusinessRule>('/api/v1/rules', data)
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: RULES_KEYS.all })
    },
  })
}

/**
 * Regel aktualisieren
 */
export function useUpdateRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: RuleUpdateRequest }) => {
      const response = await api.patch<BusinessRule>(`/api/v1/rules/${id}`, data)
      return response.data
    },
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: RULES_KEYS.all })
      queryClient.invalidateQueries({ queryKey: RULES_KEYS.detail(id) })
    },
  })
}

/**
 * Regel löschen
 */
export function useDeleteRule() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/rules/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: RULES_KEYS.all })
    },
  })
}

/**
 * Regel testen (Dry-Run)
 */
export function useTestRule() {
  return useMutation({
    mutationFn: async (data: RuleTestRequest) => {
      const response = await api.post<RuleTestResponse>('/api/v1/rules/test', data)
      return response.data
    },
  })
}

/**
 * Execution-Logs abrufen
 */
export function useExecutionLogs(params?: {
  rule_id?: string
  document_id?: string
  matched_only?: boolean
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: RULES_KEYS.logs(params),
    queryFn: async () => {
      const response = await api.get<ExecutionLog[]>('/api/v1/rules/logs', {
        params,
      })
      return response.data
    },
    staleTime: 10_000,
  })
}

// ===== AI Rule Generation =====

interface GeneratedRule {
  name: string
  description: string
  code: string | null
  category: string
  priority: number
  condition: Record<string, unknown>
  actions: Array<{ type: string; params: Record<string, unknown> }>
  else_actions: Array<{ type: string; params: Record<string, unknown> }> | null
  confidence: number
  explanation: string
}

/**
 * Regel aus natürlicher Sprache generieren
 */
export function useGenerateRule() {
  return useMutation({
    mutationFn: async (prompt: string): Promise<GeneratedRule> => {
      const response = await api.post<GeneratedRule>('/api/v1/rules/generate', {
        prompt,
      })
      return response.data
    },
  })
}
