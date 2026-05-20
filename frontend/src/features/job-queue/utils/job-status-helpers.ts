/**
 * Job Status Helpers
 *
 * Utility-Funktionen für Job-Status Darstellung.
 * Zentralisiert für Wiederverwendbarkeit in allen Job-Queue Komponenten.
 */

import type { JobStatus, JobType } from '../types/job-types';

// ==================== Status Icons ====================

export type StatusIconName =
  | 'clock'
  | 'loader'
  | 'check-circle'
  | 'x-circle'
  | 'ban'
  | 'pause';

export function getStatusIconName(status: JobStatus): StatusIconName {
  const iconMap: Record<JobStatus, StatusIconName> = {
    pending: 'clock',
    queued: 'clock',
    processing: 'loader',
    completed: 'check-circle',
    failed: 'x-circle',
    cancelled: 'ban',
  };
  return iconMap[status] || 'clock';
}

// ==================== Status Variants ====================

export type StatusVariant = 'default' | 'secondary' | 'destructive' | 'outline';

export function getStatusVariant(status: JobStatus): StatusVariant {
  const variantMap: Record<JobStatus, StatusVariant> = {
    pending: 'secondary',
    queued: 'secondary',
    processing: 'default',
    completed: 'outline',
    failed: 'destructive',
    cancelled: 'outline',
  };
  return variantMap[status] || 'default';
}

// ==================== Status Colors ====================

export interface StatusColors {
  bg: string;
  text: string;
  border: string;
}

export function getStatusColors(status: JobStatus): StatusColors {
  const colorMap: Record<JobStatus, StatusColors> = {
    pending: {
      bg: 'bg-gray-100 dark:bg-gray-800',
      text: 'text-gray-700 dark:text-gray-300',
      border: 'border-gray-300 dark:border-gray-600',
    },
    queued: {
      bg: 'bg-blue-100 dark:bg-blue-900/30',
      text: 'text-blue-700 dark:text-blue-300',
      border: 'border-blue-300 dark:border-blue-600',
    },
    processing: {
      bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      text: 'text-yellow-700 dark:text-yellow-300',
      border: 'border-yellow-300 dark:border-yellow-600',
    },
    completed: {
      bg: 'bg-green-100 dark:bg-green-900/30',
      text: 'text-green-700 dark:text-green-300',
      border: 'border-green-300 dark:border-green-600',
    },
    failed: {
      bg: 'bg-red-100 dark:bg-red-900/30',
      text: 'text-red-700 dark:text-red-300',
      border: 'border-red-300 dark:border-red-600',
    },
    cancelled: {
      bg: 'bg-gray-100 dark:bg-gray-800',
      text: 'text-gray-500 dark:text-gray-400',
      border: 'border-gray-300 dark:border-gray-600',
    },
  };
  return colorMap[status] || colorMap.pending;
}

// ==================== Status Labels ====================

export function getStatusLabel(status: JobStatus): string {
  const labelMap: Record<JobStatus, string> = {
    pending: 'Wartend',
    queued: 'In Warteschlange',
    processing: 'In Bearbeitung',
    completed: 'Abgeschlossen',
    failed: 'Fehlgeschlagen',
    cancelled: 'Abgebrochen',
  };
  return labelMap[status] || status;
}

// ==================== Status Checks ====================

export function isTerminalStatus(status: JobStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}

export function isActiveStatus(status: JobStatus): boolean {
  return status === 'processing' || status === 'queued' || status === 'pending';
}

export function canRetry(status: JobStatus): boolean {
  return status === 'failed' || status === 'cancelled';
}

export function canCancel(status: JobStatus): boolean {
  return status === 'processing' || status === 'queued' || status === 'pending';
}

export function canPause(status: JobStatus): boolean {
  return status === 'processing';
}

// ==================== Priority Helpers ====================

export type PriorityLevel = 'critical' | 'high' | 'normal' | 'low';

export function getPriorityLevel(priority: number): PriorityLevel {
  if (priority <= 2) return 'critical';
  if (priority <= 4) return 'high';
  if (priority <= 6) return 'normal';
  return 'low';
}

export function getPriorityLabel(priority: number): string {
  const level = getPriorityLevel(priority);
  const labels: Record<PriorityLevel, string> = {
    critical: 'Kritisch',
    high: 'Hoch',
    normal: 'Normal',
    low: 'Niedrig',
  };
  return labels[level];
}

export function getPriorityColors(priority: number): StatusColors {
  const level = getPriorityLevel(priority);
  const colorMap: Record<PriorityLevel, StatusColors> = {
    critical: {
      bg: 'bg-red-100 dark:bg-red-900/30',
      text: 'text-red-700 dark:text-red-300',
      border: 'border-red-300 dark:border-red-600',
    },
    high: {
      bg: 'bg-orange-100 dark:bg-orange-900/30',
      text: 'text-orange-700 dark:text-orange-300',
      border: 'border-orange-300 dark:border-orange-600',
    },
    normal: {
      bg: 'bg-blue-100 dark:bg-blue-900/30',
      text: 'text-blue-700 dark:text-blue-300',
      border: 'border-blue-300 dark:border-blue-600',
    },
    low: {
      bg: 'bg-gray-100 dark:bg-gray-800',
      text: 'text-gray-600 dark:text-gray-400',
      border: 'border-gray-300 dark:border-gray-600',
    },
  };
  return colorMap[level];
}

// ==================== Job Type Helpers ====================

export function getJobTypeLabel(jobType: JobType): string {
  const labelMap: Record<JobType, string> = {
    ocr: 'OCR',
    embedding: 'Embedding',
    validation: 'Validierung',
    export: 'Export',
    backup: 'Backup',
    gdpr: 'GDPR',
    rag: 'RAG',
    maintenance: 'Wartung',
  };
  return labelMap[jobType] || jobType;
}

export function getJobTypeColors(jobType: JobType): StatusColors {
  const colorMap: Record<JobType, StatusColors> = {
    ocr: {
      bg: 'bg-purple-100 dark:bg-purple-900/30',
      text: 'text-purple-700 dark:text-purple-300',
      border: 'border-purple-300 dark:border-purple-600',
    },
    embedding: {
      bg: 'bg-indigo-100 dark:bg-indigo-900/30',
      text: 'text-indigo-700 dark:text-indigo-300',
      border: 'border-indigo-300 dark:border-indigo-600',
    },
    validation: {
      bg: 'bg-cyan-100 dark:bg-cyan-900/30',
      text: 'text-cyan-700 dark:text-cyan-300',
      border: 'border-cyan-300 dark:border-cyan-600',
    },
    export: {
      bg: 'bg-teal-100 dark:bg-teal-900/30',
      text: 'text-teal-700 dark:text-teal-300',
      border: 'border-teal-300 dark:border-teal-600',
    },
    backup: {
      bg: 'bg-emerald-100 dark:bg-emerald-900/30',
      text: 'text-emerald-700 dark:text-emerald-300',
      border: 'border-emerald-300 dark:border-emerald-600',
    },
    gdpr: {
      bg: 'bg-rose-100 dark:bg-rose-900/30',
      text: 'text-rose-700 dark:text-rose-300',
      border: 'border-rose-300 dark:border-rose-600',
    },
    rag: {
      bg: 'bg-amber-100 dark:bg-amber-900/30',
      text: 'text-amber-700 dark:text-amber-300',
      border: 'border-amber-300 dark:border-amber-600',
    },
    maintenance: {
      bg: 'bg-slate-100 dark:bg-slate-800',
      text: 'text-slate-700 dark:text-slate-300',
      border: 'border-slate-300 dark:border-slate-600',
    },
  };
  return colorMap[jobType] || colorMap.maintenance;
}
