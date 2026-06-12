/**
 * Saved Filters API - Server-side Filter Persistence with Sharing
 *
 * Phase 4.5: Frontend UX Enhancement
 */
import { apiClient } from "@/lib/api"

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
 * Liste alle gespeicherten Filter für ein Feature
 */
export async function getSavedFilters(
  feature: string,
  includeShared = true
): Promise<SavedFilterListResponse> {
  const params = new URLSearchParams({
    feature,
    include_shared: String(includeShared),
  })
  return (
    await apiClient.get<SavedFilterListResponse>(`/api/v1/saved-filters?${params}`)
  ).data
}

/**
 * Hole einen einzelnen Filter
 */
export async function getSavedFilter(filterId: string): Promise<SavedFilter> {
  return (await apiClient.get<SavedFilter>(`/api/v1/saved-filters/${filterId}`)).data
}

/**
 * Erstelle einen neuen Filter
 */
export async function createSavedFilter(
  data: CreateSavedFilterRequest
): Promise<SavedFilter> {
  return (await apiClient.post<SavedFilter>("/api/v1/saved-filters", data)).data
}

/**
 * Aktualisiere einen Filter
 */
export async function updateSavedFilter(
  filterId: string,
  data: UpdateSavedFilterRequest
): Promise<SavedFilter> {
  return (await apiClient.patch<SavedFilter>(`/api/v1/saved-filters/${filterId}`, data)).data
}

/**
 * Loesche einen Filter
 */
export async function deleteSavedFilter(
  filterId: string,
  hardDelete = false
): Promise<void> {
  const params = hardDelete ? "?hard_delete=true" : ""
  await apiClient.delete(`/api/v1/saved-filters/${filterId}${params}`)
}

/**
 * Zeichne Nutzung eines Filters auf
 */
export async function recordFilterUsage(filterId: string): Promise<void> {
  await apiClient.post(`/api/v1/saved-filters/${filterId}/use`, {})
}

/**
 * Dupliziere einen Filter
 */
export async function duplicateSavedFilter(
  filterId: string,
  data?: DuplicateFilterRequest
): Promise<SavedFilter> {
  return (
    await apiClient.post<SavedFilter>(
      `/api/v1/saved-filters/${filterId}/duplicate`,
      data || {}
    )
  ).data
}

/**
 * Setze einen Filter als Standard
 */
export async function setDefaultFilter(filterId: string): Promise<SavedFilter> {
  return (
    await apiClient.post<SavedFilter>(
      `/api/v1/saved-filters/${filterId}/set-default`,
      {}
    )
  ).data
}

/**
 * Entferne den Standard-Filter für ein Feature
 */
export async function clearDefaultFilter(feature: string): Promise<void> {
  await apiClient.delete(`/api/v1/saved-filters/default/${feature}`)
}

/**
 * Liste verfügbare Features
 */
export async function getAvailableFeatures(): Promise<string[]> {
  return (await apiClient.get<string[]>("/api/v1/saved-filters/features/list")).data
}
