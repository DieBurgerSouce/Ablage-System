import { useQuery } from '@tanstack/react-query'
import { groupsService, type DocumentGroupType } from '@/lib/api/services/groups'
import { QUERY_VOLATILE, QUERY_STANDARD } from '@/lib/api/query-config'

// ==================== QUERY KEYS ====================

export const documentGroupQueryKeys = {
  all: ['document-groups'] as const,
  list: (params?: { group_type?: DocumentGroupType; limit?: number; offset?: number }) =>
    [...documentGroupQueryKeys.all, 'list', params] as const,
  detail: (groupId: string) =>
    [...documentGroupQueryKeys.all, 'detail', groupId] as const,
}

// ==================== STALE TIMES ====================

const STALE_TIMES = {
  list: QUERY_STANDARD.staleTime,     // 60s
  detail: QUERY_VOLATILE.staleTime,   // 30s
}

// ==================== QUERIES ====================

/**
 * Hook: Alle Dokumentgruppen abrufen
 */
export function useDocumentGroups(params?: {
  group_type?: DocumentGroupType
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: documentGroupQueryKeys.list(params),
    queryFn: () => groupsService.getAll(params),
    staleTime: STALE_TIMES.list,
  })
}

/**
 * Hook: Einzelne Dokumentgruppe nach ID abrufen
 */
export function useDocumentGroup(groupId: string | undefined) {
  return useQuery({
    queryKey: documentGroupQueryKeys.detail(groupId ?? ''),
    queryFn: () => groupsService.getById(groupId!),
    enabled: !!groupId,
    staleTime: STALE_TIMES.detail,
  })
}
