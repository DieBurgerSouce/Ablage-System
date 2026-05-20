/**
 * Disaster Recovery API Client
 *
 * API-Funktionen für Backup und Disaster Recovery Management.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface BackupStatus {
  service_aktiv: boolean;
  encryption_aktiv: boolean;
  storage_pfad: string;
  letzte_vollsicherung?: string;
  nächste_geplante_sicherung?: string;
  verfügbarer_speicherplatz_gb?: number;
  gesamt_backup_größe_gb?: number;
}

export interface Backup {
  typ: 'full' | 'incremental' | 'differential';
  name: string;
  pfad: string;
  größe: number;
  erstellt: string;
  verschluesselt: boolean;
  validiert?: boolean;
  validiert_am?: string;
  validation_status?: 'success' | 'failed' | 'pending';
  validation_errors?: string[];
}

export interface BackupValidationResult {
  backup_name: string;
  valid: boolean;
  checked_at: string;
  errors?: string[];
  warnings?: string[];
  file_count?: number;
  total_size?: number;
}

export interface RestoreTestResult {
  id: string;
  test_type: 'full' | 'partial' | 'database' | 'files';
  started_at: string;
  completed_at?: string;
  status: 'running' | 'success' | 'failed' | 'aborted';
  duration_seconds?: number;
  backup_name: string;
  restore_target: string;
  validation_steps: RestoreValidationStep[];
  errors?: string[];
  warnings?: string[];
  rto_achieved: boolean;
  rpo_achieved: boolean;
  rto_target_seconds: number;
  rto_actual_seconds?: number;
  rpo_target_seconds: number;
  data_loss_seconds?: number;
}

export interface RestoreValidationStep {
  step_name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped';
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  error?: string;
  details?: string;
}

export interface RTOMetrics {
  target_rto_seconds: number;
  target_rpo_seconds: number;
  last_test_rto_seconds?: number;
  last_test_rpo_seconds?: number;
  average_rto_seconds?: number;
  average_rpo_seconds?: number;
  rto_compliance_rate: number;
  rpo_compliance_rate: number;
  last_test_date?: string;
  tests_in_last_90_days: number;
}

export interface RecoveryPlaybookStep {
  step_number: number;
  title: string;
  description: string;
  category: 'preparation' | 'execution' | 'validation' | 'communication';
  estimated_duration_minutes: number;
  responsible_role: string;
  prerequisites: string[];
  commands?: string[];
  validation_criteria: string[];
  rollback_steps?: string[];
}

export interface RecoveryPlaybook {
  disaster_type: 'hardware_failure' | 'data_corruption' | 'ransomware' | 'natural_disaster' | 'human_error';
  severity_level: 'critical' | 'high' | 'medium' | 'low';
  total_estimated_duration_minutes: number;
  generated_at: string;
  steps: RecoveryPlaybookStep[];
  emergency_contacts: Array<{
    role: string;
    name?: string;
    phone?: string;
    email?: string;
  }>;
  additional_resources: string[];
}

export interface RestoreTestHistory {
  total_tests: number;
  tests: RestoreTestResult[];
  success_rate: number;
  average_duration_seconds: number;
  latest_test?: RestoreTestResult;
}

// ==================== API Functions ====================

/**
 * Hole Backup-Systemstatus
 */
export async function getBackupStatus(): Promise<BackupStatus> {
  const response = await apiClient.get<BackupStatus>('/backup/status');
  return response.data;
}

/**
 * Liste alle Backups auf
 */
export async function listBackups(): Promise<Backup[]> {
  const response = await apiClient.get<Backup[]>('/backup/list');
  return response.data;
}

/**
 * Validiere einzelnes Backup
 */
export async function validateBackup(backupName: string): Promise<BackupValidationResult> {
  const response = await apiClient.post<BackupValidationResult>('/backup/validate', {
    backup_name: backupName,
  });
  return response.data;
}

/**
 * Validiere alle Backups
 */
export async function validateAllBackups(): Promise<BackupValidationResult[]> {
  const response = await apiClient.post<BackupValidationResult[]>('/backup/validate-all');
  return response.data;
}

/**
 * Erstelle vollständiges Backup
 */
export async function createFullBackup(): Promise<{ message: string; backup_pfad: string }> {
  const response = await apiClient.post<{ message: string; backup_pfad: string }>(
    '/backup/full'
  );
  return response.data;
}

/**
 * Führe Restore-Test durch
 */
export async function runRestoreTest(params: {
  test_type?: 'full' | 'partial' | 'database' | 'files';
  dry_run?: boolean;
}): Promise<RestoreTestResult> {
  const response = await apiClient.post<RestoreTestResult>('/backup/restore/test', params);
  return response.data;
}

/**
 * Hole Restore-Test History
 */
export async function getRestoreTestHistory(days = 90): Promise<RestoreTestHistory> {
  const response = await apiClient.get<RestoreTestHistory>(
    `/backup/restore/test-history?days=${days}`
  );
  return response.data;
}

/**
 * Hole RTO/RPO Metriken
 */
export async function getRTOMetrics(): Promise<RTOMetrics> {
  const response = await apiClient.get<RTOMetrics>('/backup/metrics/rto-rpo');
  return response.data;
}

/**
 * Generiere Recovery-Playbook
 */
export async function generateRecoveryPlaybook(params: {
  disaster_type: RecoveryPlaybook['disaster_type'];
  severity_level: RecoveryPlaybook['severity_level'];
}): Promise<RecoveryPlaybook> {
  const response = await apiClient.post<RecoveryPlaybook>('/backup/playbook/generate', params);
  return response.data;
}

/**
 * Exportiere Playbook als PDF
 */
export async function exportPlaybookPDF(playbook: RecoveryPlaybook): Promise<Blob> {
  const response = await apiClient.post<Blob>(
    '/backup/playbook/export',
    playbook,
    { responseType: 'blob' }
  );
  return response.data;
}
