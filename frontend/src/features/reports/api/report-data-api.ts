import { logger } from '@/lib/logger';
/**
 * Report Data API Client
 *
 * API-Client für Report-Ausführung und Daten-Fetching
 */

import { apiClient } from '@/lib/api/client'

// =============================================================================
// Types
// =============================================================================

export interface ReportParams {
  period?: string
  comparison?: boolean
  date_from?: string
  date_to?: string
  category?: string
  supplier_limit?: number
}

export interface CostAnalysisData {
  categories: Array<{
    kategorie: string
    betrag: number
    anteil: number
  }>
  topSuppliers: Array<{
    lieferant: string
    betrag: number
    anteil: number
  }>
  costCenters: Array<{
    kostenstelle: string
    betrag: number
    anteil: number
  }>
  comparison?: {
    period: string
    change: number
    changePercent: number
  }
}

export interface CashflowForecastData {
  projectedPosition: Array<{
    date: string
    position: number
    forderungen: number
    verbindlichkeiten: number
  }>
  summary: {
    forderungen: number
    verbindlichkeiten: number
    nettoPosition: number
  }
  offeneForderungen: Array<{
    belegnummer: string
    kunde: string
    betrag: number
    fälligkeitsdatum: string
    überfällig: boolean
    tageÜberfällig?: number
  }>
  offeneVerbindlichkeiten: Array<{
    belegnummer: string
    lieferant: string
    betrag: number
    fälligkeitsdatum: string
    überfällig: boolean
    tageÜberfällig?: number
  }>
}

export interface DocumentVolumeData {
  volumeTrend: Array<{
    monat: string
    anzahl: number
  }>
  categoryBreakdown: Array<{
    kategorie: string
    anzahl: number
  }>
  kpis: {
    avgVerarbeitungszeit: number
    slaEinhaltung: number
    dokumenteDiesenMonat: number
  }
  processingTimes: Array<{
    kategorie: string
    avgZeit: number
    slaZeit: number
    slaEingehalten: boolean
  }>
}

// =============================================================================
// Errors
// =============================================================================

/**
 * Wird geworfen, wenn fuer eine Report-Vorlage keine echten Backend-Daten
 * verfuegbar sind. Es werden bewusst KEINE synthetischen Daten geliefert.
 */
export class ReportDataUnavailableError extends Error {
  readonly templateId: string

  constructor(templateId: string) {
    super(`Berichtsdaten fuer "${templateId}" sind derzeit nicht verfuegbar.`)
    this.name = 'ReportDataUnavailableError'
    this.templateId = templateId
  }
}

// =============================================================================
// API Functions
// =============================================================================

export async function fetchReportData(
  templateId: string,
  params: ReportParams
): Promise<CostAnalysisData | CashflowForecastData | DocumentVolumeData> {
  try {
    // Primaer: Prebuilt-Report-Daten vom Backend laden
    const response = await apiClient.post(`/reports/prebuilt/${templateId}/data`, params)
    return response.data
  } catch {
    try {
      // Alternativ: GET-Endpunkt versuchen
      const response = await apiClient.get(`/reports/data/${templateId}`, { params })
      return response.data
    } catch {
      // Beide Backend-Endpunkte nicht erreichbar -> KEINE synthetischen Daten mehr.
      // Telemetrie behalten (nur templateId, keine Nutzdaten gemaess Rule 1/8).
      logger.warn(
        `[Reports] Backend-Endpunkt fuer "${templateId}" nicht erreichbar.`
      )
      throw new ReportDataUnavailableError(templateId)
    }
  }
}

export async function getPrebuiltTemplates() {
  const response = await apiClient.get('/reports/templates/prebuilt')
  return response.data
}

export async function exportReport(
  templateId: string,
  format: 'pdf' | 'excel' | 'csv',
  params: ReportParams
): Promise<Blob> {
  const response = await apiClient.get(`/reports/export/${templateId}`, {
    params: { ...params, format },
    responseType: 'blob',
  })
  return response.data
}
