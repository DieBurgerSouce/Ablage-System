/**
 * GoBD API Client
 *
 * API-Funktionen fuer GoBD-konforme Archivierung, Verfahrensdokumentation
 * und Steuerberater-Zugang.
 */

import { apiClient } from '@/lib/api/client'
import type {
  ArchiveEntry,
  ArchiveDocumentRequest,
  ArchiveStatistics,
  ExpiringArchive,
  VerificationResult,
  RetentionSetting,
  RetentionSettingUpdate,
  ProcedureDocumentation,
  ProcedureDocVersion,
  GDPdUExportOptions,
  GDPdUExportResult,
  TaxAdvisorInvite,
  CreateTaxAdvisorInviteRequest,
  TaxAdvisorAccessLog,
} from '../types'

// ==================================================
// Archive API
// ==================================================

/**
 * Dokument archivieren
 */
export async function archiveDocument(request: ArchiveDocumentRequest): Promise<ArchiveEntry> {
  const response = await apiClient.post<ArchiveEntry>('/archive/documents', request)
  return response.data
}

/**
 * Archive-Eintrag abrufen
 */
export async function getArchiveEntry(documentId: string): Promise<ArchiveEntry> {
  const response = await apiClient.get<ArchiveEntry>(`/api/v1/archive/documents/${documentId}`)
  return response.data
}

/**
 * Alle archivierten Dokumente auflisten
 */
export async function listArchivedDocuments(params?: {
  category?: string
  expiring_within_days?: number
  page?: number
  page_size?: number
}): Promise<{ items: ArchiveEntry[]; total: number }> {
  const response = await apiClient.get<{ items: ArchiveEntry[]; total: number }>(
    '/archive/documents',
    { params }
  )
  return response.data
}

/**
 * Dokumentintegritaet verifizieren
 */
export async function verifyDocumentIntegrity(documentId: string): Promise<VerificationResult> {
  const response = await apiClient.post<VerificationResult>(
    `/api/v1/archive/documents/${documentId}/verify`
  )
  return response.data
}

/**
 * Alle Archive verifizieren (Batch)
 */
export async function verifyAllArchives(): Promise<{
  total: number
  valid: number
  invalid: number
  errors: string[]
}> {
  const response = await apiClient.post<{
    total: number
    valid: number
    invalid: number
    errors: string[]
  }>('/archive/verify-all')
  return response.data
}

/**
 * Archiv-Statistiken abrufen
 */
export async function getArchiveStatistics(): Promise<ArchiveStatistics> {
  const response = await apiClient.get<ArchiveStatistics>('/archive/statistics')
  return response.data
}

/**
 * Bald ablaufende Archive abrufen
 */
export async function getExpiringArchives(days: number = 90): Promise<ExpiringArchive[]> {
  const response = await apiClient.get<ExpiringArchive[]>('/archive/expiring', {
    params: { days },
  })
  return response.data
}

// ==================================================
// Retention Settings API
// ==================================================

/**
 * Aufbewahrungseinstellungen abrufen
 */
export async function getRetentionSettings(): Promise<RetentionSetting[]> {
  const response = await apiClient.get<RetentionSetting[]>('/archive/retention-settings')
  return response.data
}

/**
 * Aufbewahrungseinstellung aktualisieren
 */
export async function updateRetentionSetting(
  category: string,
  update: RetentionSettingUpdate
): Promise<RetentionSetting> {
  const response = await apiClient.patch<RetentionSetting>(
    `/api/v1/archive/retention-settings/${category}`,
    update
  )
  return response.data
}

/**
 * Aufbewahrungseinstellung auf Standard zuruecksetzen
 */
export async function resetRetentionSetting(category: string): Promise<RetentionSetting> {
  const response = await apiClient.post<RetentionSetting>(
    `/api/v1/archive/retention-settings/${category}/reset`
  )
  return response.data
}

// ==================================================
// Procedure Documentation API
// ==================================================

/**
 * Verfahrensdokumentation abrufen
 */
export async function getProcedureDocumentation(): Promise<ProcedureDocumentation> {
  const response = await apiClient.get<ProcedureDocumentation>(
    '/archive/procedure-documentation'
  )
  return response.data
}

/**
 * Verfahrensdokumentation generieren
 */
export async function generateProcedureDocumentation(): Promise<ProcedureDocVersion> {
  const response = await apiClient.post<ProcedureDocVersion>(
    '/archive/procedure-documentation/generate'
  )
  return response.data
}

/**
 * Verfahrensdokumentation als PDF exportieren
 */
export async function exportProcedureDocumentation(versionId?: string): Promise<Blob> {
  const response = await apiClient.get('/archive/procedure-documentation/export', {
    params: { version_id: versionId },
    responseType: 'blob',
  })
  return response.data
}

/**
 * Versionshistorie der Verfahrensdokumentation
 */
export async function getProcedureDocVersions(): Promise<ProcedureDocVersion[]> {
  const response = await apiClient.get<ProcedureDocVersion[]>(
    '/archive/procedure-documentation/versions'
  )
  return response.data
}

// ==================================================
// GDPdU Export API
// ==================================================

/**
 * GDPdU-Export starten
 */
export async function startGDPdUExport(options: GDPdUExportOptions): Promise<GDPdUExportResult> {
  const response = await apiClient.post<GDPdUExportResult>('/archive/gdpdu/export', options)
  return response.data
}

/**
 * GDPdU-Export-Status abrufen
 */
export async function getGDPdUExportStatus(exportId: string): Promise<GDPdUExportResult> {
  const response = await apiClient.get<GDPdUExportResult>(`/api/v1/archive/gdpdu/export/${exportId}`)
  return response.data
}

/**
 * GDPdU-Export herunterladen
 */
export async function downloadGDPdUExport(exportId: string): Promise<Blob> {
  const response = await apiClient.get(`/api/v1/archive/gdpdu/export/${exportId}/download`, {
    responseType: 'blob',
  })
  return response.data
}

/**
 * Vergangene GDPdU-Exporte auflisten
 */
export async function listGDPdUExports(): Promise<GDPdUExportResult[]> {
  const response = await apiClient.get<GDPdUExportResult[]>('/archive/gdpdu/exports')
  return response.data
}

// ==================================================
// Tax Advisor API
// ==================================================

/**
 * Steuerberater einladen
 */
export async function createTaxAdvisorInvite(
  request: CreateTaxAdvisorInviteRequest
): Promise<TaxAdvisorInvite> {
  const response = await apiClient.post<TaxAdvisorInvite>('/tax-advisor/invites', request)
  return response.data
}

/**
 * Aktive Steuerberater-Einladungen auflisten
 */
export async function listTaxAdvisorInvites(): Promise<TaxAdvisorInvite[]> {
  const response = await apiClient.get<TaxAdvisorInvite[]>('/tax-advisor/invites')
  return response.data
}

/**
 * Steuerberater-Einladung widerrufen
 */
export async function revokeTaxAdvisorInvite(inviteId: string): Promise<void> {
  await apiClient.delete(`/api/v1/tax-advisor/invites/${inviteId}`)
}

/**
 * Steuerberater-Zugang verlaengern
 */
export async function extendTaxAdvisorAccess(
  inviteId: string,
  additionalDays: number
): Promise<TaxAdvisorInvite> {
  const response = await apiClient.patch<TaxAdvisorInvite>(
    `/api/v1/tax-advisor/invites/${inviteId}/extend`,
    { additional_days: additionalDays }
  )
  return response.data
}

/**
 * Steuerberater-Zugriffslog abrufen
 */
export async function getTaxAdvisorAccessLog(
  inviteId?: string,
  params?: { page?: number; page_size?: number }
): Promise<{ items: TaxAdvisorAccessLog[]; total: number }> {
  const response = await apiClient.get<{ items: TaxAdvisorAccessLog[]; total: number }>(
    '/tax-advisor/access-log',
    { params: { invite_id: inviteId, ...params } }
  )
  return response.data
}
