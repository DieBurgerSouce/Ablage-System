// Analytics Dashboard Type Definitions
// Backend snake_case responses + Frontend camelCase types + Transform functions

import { TrendingUp, TrendingDown } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case from API)
// ============================================================================

export interface BackendOperationsData {
  documents_processed: { today: number; week: number; month: number };
  ocr_accuracy_percent: number;
  ocr_accuracy_trend: 'up' | 'down' | 'neutral';
  pending_approvals: number;
  oldest_approval_days: number;
  error_rate_percent: number;
  top_errors: Array<{ error_type: string; count: number }>;
  avg_processing_time_ms: number;
  p95_processing_time_ms: number;
  auto_process_rate: number;
}

export interface BackendFinanceData {
  open_items_count: number;
  open_items_amount: number;
  cashflow_trend: Array<{ date: string; amount: number }>;
  skonto_realized: number;
  skonto_missed: number;
  overdue_count: number;
  overdue_amount: number;
  aging_buckets: Array<{ bucket: string; count: number; amount: number }>;
  dunning_stages: Array<{ stage: number; count: number }>;
}

export interface BackendTeamStats {
  user_stats: Array<{
    user_id: string;
    username: string;
    documents_processed: number;
    avg_approval_time_hours: number;
    ocr_corrections: number;
    quality_score: number;
  }>;
  period: string;
  total_documents: number;
}

export interface BackendWorkloadRow {
  user_id: string;
  username: string;
  day_of_week: number;  // 0=Mo..6=So
  hour: number;         // 0-23
  count: number;
}

export interface BackendWorkloadData {
  rows: BackendWorkloadRow[];
}

// ============================================================================
// FRONTEND TYPES (camelCase for UI)
// ============================================================================

export type AnalyticsTabKey = 'betrieb' | 'finanzen' | 'team';

export type AnalyticsPeriod = 'heute' | 'woche' | 'monat' | 'quartal' | 'custom';

export interface CustomDateRange {
  startDate: string;
  endDate: string;
}

export interface OperationsData {
  documentsProcessed: { today: number; week: number; month: number };
  ocrAccuracyPercent: number;
  ocrAccuracyTrend: 'up' | 'down' | 'neutral';
  pendingApprovals: number;
  oldestApprovalDays: number;
  errorRatePercent: number;
  topErrors: Array<{ errorType: string; count: number }>;
  avgProcessingTimeMs: number;
  p95ProcessingTimeMs: number;
  autoProcessRate: number;
}

export interface FinanceData {
  openItemsCount: number;
  openItemsAmount: number;
  cashflowTrend: Array<{ date: string; amount: number }>;
  skontoRealized: number;
  skontoMissed: number;
  overdueCount: number;
  overdueAmount: number;
  agingBuckets: Array<{ bucket: string; count: number; amount: number }>;
  dunningStages: Array<{ stage: number; count: number }>;
}

export interface UserStat {
  userId: string;
  username: string;
  documentsProcessed: number;
  avgApprovalTimeHours: number;
  ocrCorrections: number;
  qualityScore: number;
}

export interface TeamStats {
  userStats: UserStat[];
  period: string;
  totalDocuments: number;
}

export interface WorkloadRow {
  userId: string;
  username: string;
  dayOfWeek: number;
  hour: number;
  count: number;
}

export interface WorkloadData {
  rows: WorkloadRow[];
}

export interface StatCardData {
  label: string;
  value: number | string;
  unit?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  color?: 'green' | 'red' | 'blue' | 'yellow';
}

// ============================================================================
// TRANSFORM FUNCTIONS (Backend -> Frontend)
// ============================================================================

export function transformOperationsData(backend: BackendOperationsData): OperationsData {
  return {
    documentsProcessed: backend.documents_processed,
    ocrAccuracyPercent: backend.ocr_accuracy_percent,
    ocrAccuracyTrend: backend.ocr_accuracy_trend,
    pendingApprovals: backend.pending_approvals,
    oldestApprovalDays: backend.oldest_approval_days,
    errorRatePercent: backend.error_rate_percent,
    topErrors: backend.top_errors.map((e) => ({
      errorType: e.error_type,
      count: e.count,
    })),
    avgProcessingTimeMs: backend.avg_processing_time_ms,
    p95ProcessingTimeMs: backend.p95_processing_time_ms,
    autoProcessRate: backend.auto_process_rate,
  };
}

export function transformFinanceData(backend: BackendFinanceData): FinanceData {
  return {
    openItemsCount: backend.open_items_count,
    openItemsAmount: backend.open_items_amount,
    cashflowTrend: backend.cashflow_trend,
    skontoRealized: backend.skonto_realized,
    skontoMissed: backend.skonto_missed,
    overdueCount: backend.overdue_count,
    overdueAmount: backend.overdue_amount,
    agingBuckets: backend.aging_buckets,
    dunningStages: backend.dunning_stages,
  };
}

export function transformWorkloadData(backend: BackendWorkloadData): WorkloadData {
  return {
    rows: backend.rows.map((r) => ({
      userId: r.user_id,
      username: r.username,
      dayOfWeek: r.day_of_week,
      hour: r.hour,
      count: r.count,
    })),
  };
}

export function transformTeamStats(backend: BackendTeamStats): TeamStats {
  return {
    userStats: backend.user_stats.map((u) => ({
      userId: u.user_id,
      username: u.username,
      documentsProcessed: u.documents_processed,
      avgApprovalTimeHours: u.avg_approval_time_hours,
      ocrCorrections: u.ocr_corrections,
      qualityScore: u.quality_score,
    })),
    period: backend.period,
    totalDocuments: backend.total_documents,
  };
}

// ============================================================================
// UI LABELS & CONSTANTS (German)
// ============================================================================

export const UI_LABELS = {
  PAGE_TITLE: 'Analyse & Berichte',
  PAGE_SUBTITLE: 'Betrieb, Finanzen und Team im Überblick',

  // Tabs
  TAB_OPERATIONS: 'Betrieb',
  TAB_FINANCE: 'Finanzen',
  TAB_TEAM: 'Team',

  // Period filter
  PERIOD_TODAY: 'Heute',
  PERIOD_WEEK: 'Woche',
  PERIOD_MONTH: 'Monat',
  PERIOD_QUARTER: 'Quartal',
  PERIOD_CUSTOM: 'Benutzerdefiniert',

  // Operations labels
  DOCS_PROCESSED: 'Verarbeitete Dokumente',
  DOCS_TODAY: 'Heute',
  DOCS_WEEK: 'Diese Woche',
  DOCS_MONTH: 'Dieser Monat',
  OCR_ACCURACY: 'OCR-Genauigkeit',
  PENDING_APPROVALS: 'Ausstehende Freigaben',
  OLDEST_APPROVAL: 'Älteste Freigabe',
  ERROR_RATE: 'Fehlerquote',
  TOP_ERRORS: 'Häufigste Fehler',
  AVG_PROCESSING_TIME: 'Ø Verarbeitungszeit',
  P95_PROCESSING_TIME: 'P95 Verarbeitungszeit',
  AUTO_PROCESS_RATE: 'Automatisierungsrate',

  // Finance labels
  OPEN_ITEMS: 'Offene Posten',
  OVERDUE_ITEMS: 'Überfällige Posten',
  SKONTO_REALIZED: 'Skonto realisiert',
  SKONTO_MISSED: 'Skonto verpasst',
  CASHFLOW_TREND: 'Cashflow-Trend',
  AGING_BUCKETS: 'Altersstruktur',
  DUNNING_STAGES: 'Mahnstufen',

  // Team labels
  TEAM_OVERVIEW: 'Team-Übersicht',
  USERNAME: 'Benutzer',
  DOCS_COUNT: 'Dokumente',
  AVG_APPROVAL_TIME: 'Ø Freigabezeit',
  OCR_CORRECTIONS: 'OCR-Korrekturen',
  QUALITY_SCORE: 'Qualität',
  TOTAL_DOCUMENTS: 'Gesamt-Dokumente',
  WORKLOAD_HEATMAP: 'Workload-Verteilung',
  WORKLOAD_DESCRIPTION: 'Dokumentenverarbeitung nach Wochentag und Uhrzeit',
  ALL_USERS: 'Alle Benutzer',

  // Actions
  ACTION_REFRESH: 'Aktualisieren',
  ACTION_EXPORT_CSV: 'CSV Export',
  ACTION_EXPORT_PDF: 'PDF Export',

  // States
  LOADING: 'Lädt...',
  ERROR: 'Fehler beim Laden',
  NO_DATA: 'Keine Daten verfügbar',

  // Trends
  TREND_UP: 'Aufwärts',
  TREND_DOWN: 'Abwärts',
  TREND_NEUTRAL: 'Unverändert',

  // Units
  DAYS: 'Tage',
  HOURS: 'Std.',
  MS: 'ms',
  PERCENT: '%',
} as const;

export const TAB_CONFIG: Record<AnalyticsTabKey, { label: string }> = {
  betrieb: { label: UI_LABELS.TAB_OPERATIONS },
  finanzen: { label: UI_LABELS.TAB_FINANCE },
  team: { label: UI_LABELS.TAB_TEAM },
};

export const PERIOD_OPTIONS: Array<{ value: AnalyticsPeriod; label: string; apiValue: string }> = [
  { value: 'heute', label: UI_LABELS.PERIOD_TODAY, apiValue: 'day' },
  { value: 'woche', label: UI_LABELS.PERIOD_WEEK, apiValue: 'week' },
  { value: 'monat', label: UI_LABELS.PERIOD_MONTH, apiValue: 'month' },
  { value: 'quartal', label: UI_LABELS.PERIOD_QUARTER, apiValue: 'quarter' },
  { value: 'custom', label: UI_LABELS.PERIOD_CUSTOM, apiValue: 'custom' },
];

// ============================================================================
// FORMATTING HELPERS
// ============================================================================

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('de-DE').format(value);
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatMs(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  return `${Math.round(value)}ms`;
}

export function formatHours(value: number): string {
  if (value < 1) {
    return `${Math.round(value * 60)}min`;
  }
  return `${value.toFixed(1)}h`;
}

export function getTrendIcon(trend?: 'up' | 'down' | 'neutral'): LucideIcon | null {
  if (trend === 'up') return TrendingUp;
  if (trend === 'down') return TrendingDown;
  return null;
}

export function getTrendColor(trend?: 'up' | 'down' | 'neutral', invertColors?: boolean): string {
  const upColor = invertColors ? 'text-red-600' : 'text-green-600';
  const downColor = invertColors ? 'text-green-600' : 'text-red-600';

  if (trend === 'up') return upColor;
  if (trend === 'down') return downColor;
  return 'text-muted-foreground';
}
