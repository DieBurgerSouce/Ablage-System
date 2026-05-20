// Smart Dashboard Type Definitions
// Backend snake_case responses + Frontend camelCase types + Transform functions

import { TrendingUp, TrendingDown, FileText, Clock, CheckCircle, AlertCircle, DollarSign, Folder, Zap, Settings } from 'lucide-react';

type LucideIcon = React.ComponentType<{ className?: string }>;

// ============================================================================
// BACKEND RESPONSE TYPES (snake_case from API)
// ============================================================================

export interface BackendKPIData {
  key: string;
  label: string;
  value: number | string;
  unit?: string;
  trend?: 'up' | 'down' | 'neutral';
  trend_percentage?: number;
  sparkline_data?: number[];
  color?: 'green' | 'red' | 'blue' | 'yellow';
}

export interface BackendTabData {
  tab: DashboardTabKey;
  widgets: BackendWidgetData[];
  kpis?: BackendKPIData[];
}

export interface BackendWidgetData {
  widget_id: string;
  widget_type: string;
  title: string;
  data: Record<string, any>;
  position?: { x: number; y: number; w: number; h: number };
}

export interface BackendProgressStep {
  step_name: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  timestamp?: string;
  message?: string;
}

export interface BackendDocumentProgress {
  document_id: number;
  steps: BackendProgressStep[];
  current_step: string;
  overall_status: 'in_progress' | 'completed' | 'failed';
}

export interface BackendBatchProgress {
  batch_id: string;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
  estimated_time_remaining_seconds?: number;
}

export interface BackendTrendData {
  kpi_key: string;
  data_points: Array<{ timestamp: string; value: number }>;
}

// ============================================================================
// FRONTEND TYPES (camelCase for UI)
// ============================================================================

export type DashboardTabKey = 'uebersicht' | 'finanzen' | 'dokumente' | 'workflows' | 'system';

export interface KPIData {
  key: string;
  label: string;
  value: number | string;
  unit?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendPercentage?: number;
  sparklineData?: number[];
  color?: 'green' | 'red' | 'blue' | 'yellow';
}

export interface TabData {
  tab: DashboardTabKey;
  widgets: WidgetData[];
  kpis?: KPIData[];
}

export interface WidgetData {
  widgetId: string;
  widgetType: string;
  title: string;
  data: Record<string, any>;
  position?: { x: number; y: number; w: number; h: number };
}

export interface ProgressStep {
  stepName: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  timestamp?: string;
  message?: string;
}

export interface DocumentProgress {
  documentId: number;
  steps: ProgressStep[];
  currentStep: string;
  overallStatus: 'in_progress' | 'completed' | 'failed';
}

export interface BatchProgress {
  batchId: string;
  totalDocuments: number;
  processedDocuments: number;
  failedDocuments: number;
  estimatedTimeRemainingSeconds?: number;
}

export interface TrendData {
  kpiKey: string;
  dataPoints: Array<{ timestamp: string; value: number }>;
}

export interface WidgetLayout {
  widgetId: string;
  position: { x: number; y: number; w: number; h: number };
}

// ============================================================================
// TRANSFORM FUNCTIONS (Backend -> Frontend)
// ============================================================================

export function transformKPIData(backend: BackendKPIData): KPIData {
  return {
    key: backend.key,
    label: backend.label,
    value: backend.value,
    unit: backend.unit,
    trend: backend.trend,
    trendPercentage: backend.trend_percentage,
    sparklineData: backend.sparkline_data,
    color: backend.color,
  };
}

export function transformTabData(backend: BackendTabData): TabData {
  return {
    tab: backend.tab,
    widgets: backend.widgets.map(transformWidgetData),
    kpis: backend.kpis?.map(transformKPIData),
  };
}

export function transformWidgetData(backend: BackendWidgetData): WidgetData {
  return {
    widgetId: backend.widget_id,
    widgetType: backend.widget_type,
    title: backend.title,
    data: backend.data,
    position: backend.position,
  };
}

export function transformDocumentProgress(backend: BackendDocumentProgress): DocumentProgress {
  return {
    documentId: backend.document_id,
    steps: backend.steps.map(step => ({
      stepName: step.step_name,
      status: step.status,
      timestamp: step.timestamp,
      message: step.message,
    })),
    currentStep: backend.current_step,
    overallStatus: backend.overall_status,
  };
}

export function transformBatchProgress(backend: BackendBatchProgress): BatchProgress {
  return {
    batchId: backend.batch_id,
    totalDocuments: backend.total_documents,
    processedDocuments: backend.processed_documents,
    failedDocuments: backend.failed_documents,
    estimatedTimeRemainingSeconds: backend.estimated_time_remaining_seconds,
  };
}

export function transformTrendData(backend: BackendTrendData): TrendData {
  return {
    kpiKey: backend.kpi_key,
    dataPoints: backend.data_points,
  };
}

// ============================================================================
// UI LABELS & CONSTANTS (German)
// ============================================================================

export const UI_LABELS = {
  PAGE_TITLE: 'Smart Dashboard',
  PAGE_SUBTITLE: 'Echtzeit-Übersicht aller Geschäftsprozesse',

  // Tabs
  TAB_UEBERSICHT: 'Übersicht',
  TAB_FINANZEN: 'Finanzen',
  TAB_DOKUMENTE: 'Dokumente',
  TAB_WORKFLOWS: 'Workflows',
  TAB_SYSTEM: 'System',

  // Progress Steps
  STEP_HOCHGELADEN: 'Hochgeladen',
  STEP_OCR: 'OCR',
  STEP_VALIDIERUNG: 'Validierung',
  STEP_FREIGABE: 'Freigabe',
  STEP_ARCHIVIERT: 'Archiviert',

  // Batch Progress
  BATCH_PROGRESS_LABEL: 'Fortschritt',
  BATCH_DOCUMENTS_LABEL: 'Dokumente',
  BATCH_ESTIMATED_TIME: 'Geschätzte Zeit',

  // Actions
  ACTION_MAXIMIZE: 'Maximieren',
  ACTION_CONFIGURE: 'Konfigurieren',
  ACTION_REMOVE: 'Entfernen',
  ACTION_REFRESH: 'Aktualisieren',

  // States
  LOADING: 'Lädt...',
  ERROR: 'Fehler beim Laden',
  NO_DATA: 'Keine Daten verfügbar',

  // KPI Trends
  TREND_UP: 'Aufwärts',
  TREND_DOWN: 'Abwärts',
  TREND_NEUTRAL: 'Unverändert',
} as const;

export const TAB_CONFIG: Record<DashboardTabKey, { label: string; icon: LucideIcon }> = {
  uebersicht: { label: UI_LABELS.TAB_UEBERSICHT, icon: Zap },
  finanzen: { label: UI_LABELS.TAB_FINANZEN, icon: DollarSign },
  dokumente: { label: UI_LABELS.TAB_DOKUMENTE, icon: FileText },
  workflows: { label: UI_LABELS.TAB_WORKFLOWS, icon: Clock },
  system: { label: UI_LABELS.TAB_SYSTEM, icon: Settings },
};

export const PROGRESS_STEP_CONFIG: Record<string, { label: string; icon: LucideIcon }> = {
  hochgeladen: { label: UI_LABELS.STEP_HOCHGELADEN, icon: FileText },
  ocr: { label: UI_LABELS.STEP_OCR, icon: Clock },
  validierung: { label: UI_LABELS.STEP_VALIDIERUNG, icon: AlertCircle },
  freigabe: { label: UI_LABELS.STEP_FREIGABE, icon: CheckCircle },
  archiviert: { label: UI_LABELS.STEP_ARCHIVIERT, icon: Folder },
};

// ============================================================================
// KPI FORMATTING HELPERS
// ============================================================================

export function formatKPIValue(value: number | string, unit?: string): string {
  if (typeof value === 'string') return value;

  if (unit === 'currency' || unit === 'EUR') {
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(value);
  }

  if (unit === 'percent' || unit === '%') {
    return `${value.toFixed(1)}%`;
  }

  if (unit === 'count') {
    return new Intl.NumberFormat('de-DE').format(value);
  }

  if (unit) {
    return `${new Intl.NumberFormat('de-DE').format(value)} ${unit}`;
  }

  return new Intl.NumberFormat('de-DE').format(value);
}

export function formatEstimatedTime(seconds?: number): string {
  if (!seconds) return UI_LABELS.NO_DATA;

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

export function getTrendIcon(trend?: 'up' | 'down' | 'neutral'): LucideIcon | null {
  if (trend === 'up') return TrendingUp;
  if (trend === 'down') return TrendingDown;
  return null;
}

export function getTrendColor(trend?: 'up' | 'down' | 'neutral', color?: string): string {
  // If explicit color is set, use it
  if (color === 'green') return 'text-green-600';
  if (color === 'red') return 'text-red-600';
  if (color === 'blue') return 'text-blue-600';
  if (color === 'yellow') return 'text-yellow-600';

  // Otherwise, derive from trend
  if (trend === 'up') return 'text-green-600';
  if (trend === 'down') return 'text-red-600';
  return 'text-muted-foreground';
}
