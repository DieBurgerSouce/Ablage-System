/**
 * Saved Filters API - Server-side Filter Persistence with Sharing
 *
 * Phase 4.5: Frontend UX Enhancement
 */
import { apiClient } from "@/lib/api-client"

export interface SavedFilter {
  id: string
  name: string
  description: string | null
  feature: string
  filter_config: Record<string, unknown>
  is_shared: boolean
  is_default: boolean
  use_count: number
  last_used_at: string | null
  created_at: string
  updated_at: string
  is_own: boolean
}

export interface SavedFilterListResponse {
  filters: SavedFilter[]
  total: number
}

export interface CreateSavedFilterRequest {
  name: string
  feature: string
  filter_config: Record<string, unknown>
  description?: string
  is_shared?: boolean
  is_default?: boolean
}

export interface UpdateSavedFilterRequest {
  name?: string
  filter_config?: Record<string, unknown>
  description?: string
  is_shared?: boolean
  is_default?: boolean
}

export interface DuplicateFilterRequest {
  new_name?: string
}

/**
 * Liste alle gespeicherten Filter fuer ein Feature
 */
export async function getSavedFilters(
  feature: string,
  includeShared = true
): Promise<SavedFilterListResponse> {
  const params = new URLSearchParams({
    feature,
    include_shared: String(includeShared),
  })
  return apiClient.get<SavedFilterListResponse>(
    `/api/v1/saved-filters?${params}`
  )
}

/**
 * Hole einen einzelnen Filter
 */
export async function getSavedFilter(filterId: string): Promise<SavedFilter> {
  return apiClient.get<SavedFilter>(`/api/v1/saved-filters/${filterId}`)
}

/**
 * Erstelle einen neuen Filter
 */
export async function createSavedFilter(
  data: CreateSavedFilterRequest
): Promise<SavedFilter> {
  return apiClient.post<SavedFilter>("/api/v1/saved-filters", data)
}

/**
 * Aktualisiere einen Filter
 */
export async function updateSavedFilter(
  filterId: string,
  data: UpdateSavedFilterRequest
): Promise<SavedFilter> {
  return apiClient.patch<SavedFilter>(`/api/v1/saved-filters/${filterId}`, data)
}

/**
 * Loesche einen Filter
 */
export async function deleteSavedFilter(
  filterId: string,
  hardDelete = false
): Promise<void> {
  const params = hardDelete ? "?hard_delete=true" : ""
  return apiClient.delete(`/api/v1/saved-filters/${filterId}${params}`)
}

/**
 * Zeichne Nutzung eines Filters auf
 */
export async function recordFilterUsage(filterId: string): Promise<void> {
  return apiClient.post(`/api/v1/saved-filters/${filterId}/use`, {})
}

/**
 * Dupliziere einen Filter
 */
export async function duplicateSavedFilter(
  filterId: string,
  data?: DuplicateFilterRequest
): Promise<SavedFilter> {
  return apiClient.post<SavedFilter>(
    `/api/v1/saved-filters/${filterId}/duplicate`,
    data || {}
  )
}

/**
 * Setze einen Filter als Standard
 */
export async function setDefaultFilter(filterId: string): Promise<SavedFilter> {
  return apiClient.post<SavedFilter>(
    `/api/v1/saved-filters/${filterId}/set-default`,
    {}
  )
}

/**
 * Entferne den Standard-Filter fuer ein Feature
 */
export async function clearDefaultFilter(feature: string): Promise<void> {
  return apiClient.delete(`/api/v1/saved-filters/default/${feature}`)
}

/**
 * Liste verfuegbare Features
 */
export async function getAvailableFeatures(): Promise<string[]> {
  return apiClient.get<string[]>("/api/v1/saved-filters/features/list")
}
