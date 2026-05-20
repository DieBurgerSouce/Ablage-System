/**
 * Command Center API Service
 *
 * Kommuniziert mit den /api/v1/command-center Endpoints
 * für das zentrale Steuerungs-Dashboard.
 *
 * Verfügbare Endpoints:
 * - GET /command-center          – Vollständige Command-Center-Daten
 * - GET /command-center/kpis     – Nur KPI-Widgets
 * - GET /command-center/tasks    – Nur priorisierte Aufgaben
 * - GET /command-center/insights – Nur proaktive Hinweise
 * - GET /command-center/alerts   – Nur aktive Alarme
 */

import { apiClient } from '../client';

// ============================================================================
// Types
// ============================================================================

/** KPI-Widget mit Trend-Indikator und Darstellungsvariante */
export interface KPIWidget {
  id: string;
  label: string;
  value: string;
  raw_value: number;
  unit: string;
  trend: 'up' | 'down' | 'stable' | null;
  trend_value: string | null;
  variant: 'default' | 'success' | 'warning' | 'danger';
  icon: string | null;
}

/** Proaktiver Hinweis mit optionaler Aktion */
export interface ProactiveInsight {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  description: string;
  category: string;
  action_label: string | null;
  action_route: string | null;
  created_at: string;
}

/** Priorisierte Aufgabe mit finanziellem Einfluss */
export interface TaskItem {
  id: string;
  title: string;
  description: string | null;
  /** Prioritätsstufe 1 (niedrigste) bis 5 (höchste) */
  priority: number;
  action_type: string;
  category: string;
  due_date: string | null;
  financial_impact: number | null;
  action_route: string | null;
}

/** Aktiver Alarm aus dem Alert-Center */
export interface AlertItem {
  id: string;
  severity: string;
  title: string;
  source: string;
  created_at: string;
}

/** Einzelner Punkt in der Cashflow-Zeitreihe */
export interface CashflowPoint {
  date: string;
  inflow: number;
  outflow: number;
  balance: number;
}

/** Fortschrittsanzeige für erledigte Aufgaben */
export interface CommandCenterProgress {
  completed: number;
  total: number;
  percentage: number;
}

/** Vollständige Antwort des Command-Center-Endpoints */
export interface CommandCenterResponse {
  kpis: KPIWidget[];
  tasks: TaskItem[];
  task_progress: CommandCenterProgress;
  insights: ProactiveInsight[];
  alerts: AlertItem[];
  alert_count: number;
  cashflow: CashflowPoint[];
  generated_at: string;
  ai_status: 'operational' | 'degraded' | 'offline';
}

// ============================================================================
// Service-Funktionen
// ============================================================================

/**
 * Lädt alle Command-Center-Daten in einem einzigen Aufruf.
 *
 * Enthält KPIs, Aufgaben, Hinweise, Alarme und Cashflow-Verlauf.
 */
export async function getCommandCenter(): Promise<CommandCenterResponse> {
  const response = await apiClient.get<CommandCenterResponse>('/command-center');
  return response.data;
}

/**
 * Lädt ausschließlich die KPI-Widgets des Command Centers.
 */
export async function getKPIs(): Promise<KPIWidget[]> {
  const response = await apiClient.get<KPIWidget[]>('/command-center/kpis');
  return response.data;
}

/**
 * Lädt die priorisierten Aufgaben des Command Centers.
 *
 * @param limit – Maximale Anzahl zurückgegebener Aufgaben (optional)
 */
export async function getTasks(limit?: number): Promise<TaskItem[]> {
  const url =
    limit !== undefined
      ? `/command-center/tasks?limit=${limit}`
      : '/command-center/tasks';
  const response = await apiClient.get<TaskItem[]>(url);
  return response.data;
}

/**
 * Lädt die proaktiven Hinweise des Command Centers.
 */
export async function getInsights(): Promise<ProactiveInsight[]> {
  const response = await apiClient.get<ProactiveInsight[]>('/command-center/insights');
  return response.data;
}

/**
 * Lädt die aktiven Alarme des Command Centers.
 */
export async function getAlerts(): Promise<AlertItem[]> {
  const response = await apiClient.get<AlertItem[]>('/command-center/alerts');
  return response.data;
}
