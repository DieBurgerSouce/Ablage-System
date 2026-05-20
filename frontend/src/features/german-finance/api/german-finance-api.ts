/**
 * German Finance API Service
 *
 * Service methods for USt, BWA, and Cashflow endpoints
 */

import { apiClient } from '@/lib/api/client';
import type {
  UStReportBackend,
  BWAReportBackend,
  CashflowForecastBackend,
  LiquidityWarningBackend,
  CashflowScenarioBackend,
  CashflowHistoryBackend,
  GenerateUStRequest,
  GenerateBWARequest,
  UpdateCashflowRequest,
  RunScenarioRequest,
} from '../types/german-finance-types';

// ============================================================================
// USt-Voranmeldung (VAT)
// ============================================================================

export async function generateUStReport(data: GenerateUStRequest): Promise<UStReportBackend> {
  try {
    const response = await apiClient.post<UStReportBackend>('/finance/de/ust/generate', data);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Erstellen der USt-Voranmeldung');
  }
}

export async function getUStReports(params?: {
  year?: number;
  status?: 'draft' | 'submitted' | 'approved';
}): Promise<UStReportBackend[]> {
  try {
    const response = await apiClient.get<UStReportBackend[]>('/finance/de/ust/reports', {
      params,
    });
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der USt-Voranmeldungen');
  }
}

export async function getUStReport(reportId: string): Promise<UStReportBackend> {
  try {
    const response = await apiClient.get<UStReportBackend>(`/finance/de/ust/reports/${reportId}`);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der USt-Voranmeldung');
  }
}

// ============================================================================
// BWA (Business Report)
// ============================================================================

export async function generateBWAReport(data: GenerateBWARequest): Promise<BWAReportBackend> {
  try {
    const response = await apiClient.post<BWAReportBackend>('/finance/de/bwa/generate', data);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Erstellen der BWA');
  }
}

export async function getBWAReports(params?: {
  year?: number;
  month?: number;
}): Promise<BWAReportBackend[]> {
  try {
    const response = await apiClient.get<BWAReportBackend[]>('/finance/de/bwa/reports', {
      params,
    });
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der BWA-Berichte');
  }
}

export async function getBWAReport(reportId: string): Promise<BWAReportBackend> {
  try {
    const response = await apiClient.get<BWAReportBackend>(`/finance/de/bwa/reports/${reportId}`);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der BWA');
  }
}

export async function getBWAComparison(params: {
  report1_id: string;
  report2_id: string;
}): Promise<{
  report1: BWAReportBackend;
  report2: BWAReportBackend;
  differences: Array<{
    section: string;
    amount1: number;
    amount2: number;
    change: number;
    change_percent: number;
  }>;
}> {
  try {
    const response = await apiClient.get('/finance/de/bwa/comparison', { params });
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden des BWA-Vergleichs');
  }
}

// ============================================================================
// Cashflow
// ============================================================================

export async function updateCashflow(data: UpdateCashflowRequest): Promise<{ success: boolean }> {
  try {
    const response = await apiClient.post<{ success: boolean }>('/finance/de/cashflow/update', data);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Aktualisieren des Cashflows');
  }
}

export async function getCashflowForecast(params?: {
  days?: 30 | 60 | 90;
}): Promise<CashflowForecastBackend[]> {
  try {
    const response = await apiClient.get<CashflowForecastBackend[]>('/finance/de/cashflow/forecast', {
      params,
    });
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der Cashflow-Prognose');
  }
}

export async function getLiquidityWarnings(): Promise<LiquidityWarningBackend[]> {
  try {
    const response = await apiClient.get<LiquidityWarningBackend[]>('/finance/de/cashflow/warnings');
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der Liquiditätswarnungen');
  }
}

export async function runCashflowScenario(data: RunScenarioRequest): Promise<CashflowScenarioBackend> {
  try {
    const response = await apiClient.post<CashflowScenarioBackend>('/finance/de/cashflow/scenario', data);
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Erstellen des Szenarios');
  }
}

export async function getCashflowScenarios(): Promise<CashflowScenarioBackend[]> {
  try {
    const response = await apiClient.get<CashflowScenarioBackend[]>('/finance/de/cashflow/scenarios');
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der Szenarien');
  }
}

export async function getCashflowHistory(params?: {
  start_date?: string;
  end_date?: string;
}): Promise<CashflowHistoryBackend[]> {
  try {
    const response = await apiClient.get<CashflowHistoryBackend[]>('/finance/de/cashflow/history', {
      params,
    });
    return response.data;
  } catch (error) {
    throw new Error('Fehler beim Laden der Cashflow-Historie');
  }
}
