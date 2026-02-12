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
// API Functions
// =============================================================================

export async function fetchReportData(
  templateId: string,
  params: ReportParams
): Promise<CostAnalysisData | CashflowForecastData | DocumentVolumeData> {
  // TODO: Replace with actual API endpoint when backend implements /reports/execute
  // For now, return mock data based on templateId

  if (templateId === 'cost-analysis') {
    return getMockCostAnalysis(params)
  } else if (templateId === 'cashflow-forecast') {
    return getMockCashflowForecast(params)
  } else if (templateId === 'document-volume') {
    return getMockDocumentVolume(params)
  }

  throw new Error(`Unknown template ID: ${templateId}`)
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

// =============================================================================
// Mock Data Generators (TODO: Remove when backend is ready)
// =============================================================================

function getMockCostAnalysis(_params: ReportParams): CostAnalysisData {
  return {
    categories: [
      { kategorie: 'Bürobedarf', betrag: 15420, anteil: 25.3 },
      { kategorie: 'IT & Software', betrag: 12800, anteil: 21.0 },
      { kategorie: 'Marketing', betrag: 9500, anteil: 15.6 },
      { kategorie: 'Reisekosten', betrag: 8200, anteil: 13.5 },
      { kategorie: 'Versicherungen', betrag: 7100, anteil: 11.7 },
      { kategorie: 'Sonstige', betrag: 7880, anteil: 12.9 },
    ],
    topSuppliers: [
      { lieferant: 'Office Depot GmbH', betrag: 8500, anteil: 13.9 },
      { lieferant: 'Microsoft Deutschland', betrag: 7200, anteil: 11.8 },
      { lieferant: 'Amazon Business', betrag: 6800, anteil: 11.2 },
      { lieferant: 'Telekom AG', betrag: 5400, anteil: 8.9 },
      { lieferant: 'Google Workspace', betrag: 4300, anteil: 7.1 },
    ],
    costCenters: [
      { kostenstelle: 'Verwaltung', betrag: 18200, anteil: 29.9 },
      { kostenstelle: 'Vertrieb', betrag: 15600, anteil: 25.6 },
      { kostenstelle: 'Produktion', betrag: 14800, anteil: 24.3 },
      { kostenstelle: 'IT', betrag: 12300, anteil: 20.2 },
    ],
    comparison: {
      period: 'Vorjahr',
      change: -2400,
      changePercent: -3.8,
    },
  }
}

function getMockCashflowForecast(_params: ReportParams): CashflowForecastData {
  const today = new Date()
  const projectedPosition = []
  let position = 45000

  for (let i = 0; i < 90; i++) {
    const date = new Date(today)
    date.setDate(date.getDate() + i)

    const forderungen = Math.random() * 5000 + 2000
    const verbindlichkeiten = Math.random() * 4000 + 1500
    position += forderungen - verbindlichkeiten

    projectedPosition.push({
      date: date.toISOString().split('T')[0],
      position: Math.round(position),
      forderungen: Math.round(forderungen),
      verbindlichkeiten: Math.round(verbindlichkeiten),
    })
  }

  return {
    projectedPosition,
    summary: {
      forderungen: 78400,
      verbindlichkeiten: 52300,
      nettoPosition: 26100,
    },
    offeneForderungen: [
      {
        belegnummer: 'RE-2024-0123',
        kunde: 'Müller GmbH',
        betrag: 12500,
        fälligkeitsdatum: '2024-12-15',
        überfällig: false,
      },
      {
        belegnummer: 'RE-2024-0098',
        kunde: 'Schmidt AG',
        betrag: 8900,
        fälligkeitsdatum: '2024-11-28',
        überfällig: true,
        tageÜberfällig: 15,
      },
      {
        belegnummer: 'RE-2024-0145',
        kunde: 'Wagner KG',
        betrag: 15600,
        fälligkeitsdatum: '2024-12-20',
        überfällig: false,
      },
    ],
    offeneVerbindlichkeiten: [
      {
        belegnummer: 'ER-2024-0456',
        lieferant: 'Office Depot GmbH',
        betrag: 3200,
        fälligkeitsdatum: '2024-12-10',
        überfällig: false,
      },
      {
        belegnummer: 'ER-2024-0401',
        lieferant: 'Telekom AG',
        betrag: 1800,
        fälligkeitsdatum: '2024-12-05',
        überfällig: false,
      },
    ],
  }
}

function getMockDocumentVolume(_params: ReportParams): DocumentVolumeData {
  const months = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

  return {
    volumeTrend: months.map((monat, idx) => ({
      monat,
      anzahl: Math.floor(Math.random() * 200 + 300 + idx * 10),
    })),
    categoryBreakdown: [
      { kategorie: 'Eingangsrechnung', anzahl: 1250 },
      { kategorie: 'Ausgangsrechnung', anzahl: 980 },
      { kategorie: 'Lieferschein', anzahl: 720 },
      { kategorie: 'Auftragsbestätigung', anzahl: 650 },
      { kategorie: 'Vertrag', anzahl: 320 },
      { kategorie: 'Sonstige', anzahl: 480 },
    ],
    kpis: {
      avgVerarbeitungszeit: 3.2,
      slaEinhaltung: 94.5,
      dokumenteDiesenMonat: 425,
    },
    processingTimes: [
      { kategorie: 'Eingangsrechnung', avgZeit: 2.8, slaZeit: 4.0, slaEingehalten: true },
      { kategorie: 'Ausgangsrechnung', avgZeit: 1.5, slaZeit: 2.0, slaEingehalten: true },
      { kategorie: 'Lieferschein', avgZeit: 4.2, slaZeit: 4.0, slaEingehalten: false },
      { kategorie: 'Auftragsbestätigung', avgZeit: 3.1, slaZeit: 3.5, slaEingehalten: true },
      { kategorie: 'Vertrag', avgZeit: 5.8, slaZeit: 6.0, slaEingehalten: true },
    ],
  }
}
