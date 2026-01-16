/**
 * Lexware Admin API
 *
 * API-Funktionen fuer den Lexware Excel-Import
 *
 * WICHTIG: Backend erwartet ZWEI Dateien gleichzeitig (Folie + Messer)
 * und verwendet snake_case in Response-Feldern.
 */

import { apiClient } from '@/lib/api/client'

// ==================== Types (ALIGNED WITH BACKEND) ====================

export type EntityType = 'customer' | 'supplier'

/**
 * Konflikt-Info - EXAKT wie im Backend definiert
 * @see app/api/v1/lexware.py:ConflictInfo
 */
export interface ConflictInfo {
  identifier: string
  conflict_type: 'critical' | 'harmless' | 'duplicate'
  reason: string
  folie_value: string | null
  messer_value: string | null
}

/**
 * Import Response - EXAKT wie im Backend definiert
 * @see app/api/v1/lexware.py:LexwareImportResponse
 */
export interface LexwareImportResponse {
  success: boolean
  imported_count: number
  updated_count: number
  skipped_count: number
  error_count: number
  conflicts: ConflictInfo[]
  message: string
  task_id: string | null
}

/**
 * Linking Statistics - EXAKT wie im Backend definiert
 * @see app/api/v1/lexware.py:LinkingStatistics
 */
export interface LinkingStatistics {
  total_documents: number
  linked_documents: number
  unlinked_documents: number
  linked_percentage: number
  by_match_type: Record<string, number>
  by_confidence: Record<string, number>
  by_entity_type: Record<string, number>
}

/**
 * Entity Linking Request
 * @see app/api/v1/lexware.py:EntityLinkingRequest
 */
export interface EntityLinkingRequest {
  min_confidence?: number
  only_unlinked?: boolean
  batch_size?: number
  async_mode?: boolean
}

/**
 * Entity Linking Response
 * @see app/api/v1/lexware.py:EntityLinkingResponse
 */
export interface EntityLinkingResponse {
  success: boolean
  linked_count: number
  unlinked_count: number
  low_confidence_count: number
  error_count: number
  already_linked_count: number
  message: string
  task_id: string | null
}

// ==================== API Functions ====================

/**
 * Importiert Kunden aus ZWEI Lexware Excel-Dateien (Folie + Messer)
 *
 * WICHTIG: Backend erwartet beide Dateien gleichzeitig!
 * @see app/api/v1/lexware.py:import_customers
 */
export async function importCustomers(
  folieFile: File,
  messerFile: File,
  skipConflicts = true,
  dryRun = false
): Promise<LexwareImportResponse> {
  const formData = new FormData()
  formData.append('folie_file', folieFile)
  formData.append('messer_file', messerFile)

  const params = new URLSearchParams()
  params.append('skip_conflicts', String(skipConflicts))
  params.append('dry_run', String(dryRun))

  const response = await apiClient.post<LexwareImportResponse>(
    `/api/v1/lexware/import/customers?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  )
  return response.data
}

/**
 * Importiert Lieferanten aus ZWEI Lexware Excel-Dateien (Folie + Messer)
 *
 * WICHTIG: Backend erwartet beide Dateien gleichzeitig!
 * @see app/api/v1/lexware.py:import_suppliers
 */
export async function importSuppliers(
  folieFile: File,
  messerFile: File,
  skipConflicts = true,
  dryRun = false
): Promise<LexwareImportResponse> {
  const formData = new FormData()
  formData.append('folie_file', folieFile)
  formData.append('messer_file', messerFile)

  const params = new URLSearchParams()
  params.append('skip_conflicts', String(skipConflicts))
  params.append('dry_run', String(dryRun))

  const response = await apiClient.post<LexwareImportResponse>(
    `/api/v1/lexware/import/suppliers?${params.toString()}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  )
  return response.data
}

/**
 * Holt Verknuepfungs-Statistiken
 *
 * ACHTUNG: Endpoint ist /linking-statistics, NICHT /statistics!
 * @see app/api/v1/lexware.py:get_linking_statistics
 */
export async function fetchLinkingStatistics(): Promise<LinkingStatistics> {
  const response = await apiClient.get<LinkingStatistics>(
    '/api/v1/lexware/linking-statistics'
  )
  return response.data
}

/**
 * Startet das automatische Verknuepfen aller Dokumente
 * @see app/api/v1/lexware.py:link_documents
 */
export async function triggerDocumentLinking(
  options: EntityLinkingRequest = {}
): Promise<EntityLinkingResponse> {
  const response = await apiClient.post<EntityLinkingResponse>(
    '/api/v1/lexware/link-documents',
    {
      min_confidence: options.min_confidence ?? 0.75,
      only_unlinked: options.only_unlinked ?? true,
      batch_size: options.batch_size ?? 100,
      async_mode: options.async_mode ?? true,
    }
  )
  return response.data
}
