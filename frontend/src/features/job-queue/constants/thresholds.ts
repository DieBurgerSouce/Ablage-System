/**
 * UI Threshold Constants for Job Queue
 *
 * Zentrale Definition aller UI-relevanten Schwellenwerte.
 * Diese Werte sind rein kosmetisch/UX-bezogen und haben keine Security-Auswirkungen.
 */

// ==================== Job Status Thresholds ====================

/**
 * Erfolgsrate-Schwellenwerte (Prozent)
 * Bestimmt die Farbgebung der Erfolgsrate-Anzeige
 */
export const SUCCESS_RATE_THRESHOLDS = {
  /** Ab diesem Wert wird "Ausgezeichnet" (gruen) angezeigt */
  EXCELLENT: 95,
  /** Ab diesem Wert wird "Gut" (gelb) angezeigt, darunter "Kritisch" (rot) */
  GOOD: 80,
} as const;

/**
 * Queue-Auslastung Schwellenwerte (Anzahl Jobs)
 * Bestimmt die Farbgebung der Queue-Balken im Chart
 */
export const QUEUE_UTILIZATION_THRESHOLDS = {
  /** Ab diesem Wert wird die Queue als "Kritisch" (rot) markiert */
  CRITICAL: 80,
  /** Ab diesem Wert wird die Queue als "Warnung" (gelb) markiert */
  WARNING: 30,
} as const;

/**
 * Queue-Auslastung Prozent-Schwellenwerte
 * Bestimmt die Farbgebung der Auslastungs-Prozentanzeige
 */
export const QUEUE_UTILIZATION_PERCENT_THRESHOLDS = {
  /** Ab diesem Wert wird die Auslastung als "Kritisch" (rot) angezeigt */
  CRITICAL: 80,
  /** Ab diesem Wert wird die Auslastung als "Warnung" (gelb) angezeigt */
  WARNING: 50,
} as const;

// ==================== Job Priority Thresholds ====================

/**
 * Job-Prioritaet Schwellenwerte
 * Bestimmt die visuelle Hervorhebung von Jobs nach Prioritaet
 */
export const JOB_PRIORITY_THRESHOLDS = {
  /** Ab diesem Wert wird die Prioritaet als "Hoch" (rot) hervorgehoben */
  HIGH: 8,
} as const;

// ==================== Dashboard KPI Thresholds ====================

/**
 * Dashboard-KPI Schwellenwerte
 * Bestimmt die Farbgebung der KPI-Karten auf dem Dashboard
 */
export const DASHBOARD_KPI_THRESHOLDS = {
  /** Ab dieser Anzahl fehlgeschlagener Jobs wird die KPI rot */
  FAILED_JOBS_ERROR: 10,
  /** Ab dieser Anzahl aktiver Jobs wird die KPI als Warnung markiert */
  ACTIVE_JOBS_WARNING: 50,
} as const;

// ==================== Type Exports ====================

export type SuccessRateStatus = 'success' | 'warning' | 'error' | 'default';
export type QueueStatus = 'critical' | 'warning' | 'normal';

// ==================== Helper Functions ====================

/**
 * Ermittelt den Status basierend auf der Erfolgsrate
 */
export function getSuccessRateStatus(rate: number): SuccessRateStatus {
  if (rate >= SUCCESS_RATE_THRESHOLDS.EXCELLENT) return 'success';
  if (rate >= SUCCESS_RATE_THRESHOLDS.GOOD) return 'warning';
  return 'error';
}

/**
 * Ermittelt den Status basierend auf der Queue-Auslastung
 */
export function getQueueStatus(length: number): QueueStatus {
  if (length >= QUEUE_UTILIZATION_THRESHOLDS.CRITICAL) return 'critical';
  if (length >= QUEUE_UTILIZATION_THRESHOLDS.WARNING) return 'warning';
  return 'normal';
}

/**
 * Ermittelt die Farbe für eine Queue basierend auf der Laenge
 */
export function getQueueBarColor(length: number): string {
  if (length >= QUEUE_UTILIZATION_THRESHOLDS.CRITICAL) return '#ef4444'; // red
  if (length >= QUEUE_UTILIZATION_THRESHOLDS.WARNING) return '#eab308'; // yellow
  return '#22c55e'; // green
}

/**
 * Ermittelt ob eine Job-Prioritaet als "hoch" gilt
 */
export function isHighPriority(priority: number): boolean {
  return priority >= JOB_PRIORITY_THRESHOLDS.HIGH;
}
