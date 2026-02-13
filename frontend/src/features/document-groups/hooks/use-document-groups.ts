import { useQuery } from '@tanstack/react-query'
import { groupsService, type DocumentGroupType } from '@/lib/api/services/groups'

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
  list: 60 * 1000,      // 1 Minute
  detail: 30 * 1000,    // 30 Sekunden
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
