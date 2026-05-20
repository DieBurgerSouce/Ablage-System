/**
 * Custom Fields API
 *
 * TanStack Query Hooks fuer benutzerdefinierte Felder.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  CustomFieldDefinitionCreate,
  CustomFieldDefinitionUpdate,
  CustomFieldDefinitionResponse,
  CustomFieldDefinitionListResponse,
  CustomFieldValueSet,
  CustomFieldValueResponse,
} from './types'

// =============================================================================
// Query Keys
// =============================================================================

export const CUSTOM_FIELD_KEYS = {
  all: ['custom-fields'] as const,
  definitions: (params?: { document_type?: string; include_inactive?: boolean }) =>
    [...CUSTOM_FIELD_KEYS.all, 'definitions', params] as const,
  documentValues: (documentId: string) =>
    [...CUSTOM_FIELD_KEYS.all, 'values', documentId] as const,
}

// =============================================================================
// Definition Queries
// =============================================================================

/**
 * Felddefinitionen auflisten
 */
export function useCustomFieldDefinitions(params?: {
  document_type?: string
  include_inactive?: boolean
}) {
  return useQuery({
    queryKey: CUSTOM_FIELD_KEYS.definitions(params),
    queryFn: async () => {
      const response = await api.get<CustomFieldDefinitionListResponse>(
        '/api/v1/custom-fields/definitions',
        { params }
      )
      return response.data
    },
    staleTime: 30_000,
  })
}

// =============================================================================
// Definition Mutations
// =============================================================================

/**
 * Felddefinition erstellen
 */
export function useCreateFieldDefinition() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CustomFieldDefinitionCreate) => {
      const response = await api.post<CustomFieldDefinitionResponse>(
        '/api/v1/custom-fields/definitions',
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CUSTOM_FIELD_KEYS.all })
    },
  })
}

/**
 * Felddefinition aktualisieren
 */
export function useUpdateFieldDefinition() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string
      data: CustomFieldDefinitionUpdate
    }) => {
      const response = await api.put<CustomFieldDefinitionResponse>(
        `/api/v1/custom-fields/definitions/${id}`,
        data
      )
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CUSTOM_FIELD_KEYS.all })
    },
  })
}

/**
 * Felddefinition loeschen (Soft-Delete)
 */
export function useDeleteFieldDefinition() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/v1/custom-fields/definitions/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CUSTOM_FIELD_KEYS.all })
    },
  })
}

// =============================================================================
// Document Value Queries & Mutations
// =============================================================================

/**
 * Feldwerte eines Dokuments lesen
 */
export function useDocumentFieldValues(documentId: string) {
  return useQuery({
    queryKey: CUSTOM_FIELD_KEYS.documentValues(documentId),
    queryFn: async () => {
      const response = await api.get<CustomFieldValueResponse>(
        `/api/v1/custom-fields/documents/${documentId}/values`
      )
      return response.data
    },
    enabled: !!documentId,
    staleTime: 15_000,
  })
}

/**
 * Feldwerte auf Dokument setzen
 */
export function useSetDocumentFieldValues() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      documentId,
      data,
    }: {
      documentId: string
      data: CustomFieldValueSet
    }) => {
      const response = await api.put<CustomFieldValueResponse>(
        `/api/v1/custom-fields/documents/${documentId}/values`,
        data
      )
      return response.data
    },
    onSuccess: (_, { documentId }) => {
      queryClient.invalidateQueries({
        queryKey: CUSTOM_FIELD_KEYS.documentValues(documentId),
      })
    },
  })
}
