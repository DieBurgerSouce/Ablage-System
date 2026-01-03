/**
 * Import System API Client
 *
 * API-Funktionen fuer E-Mail-Import, Ordner-Import und Import-Regeln.
 */

import { apiClient as api } from '@/lib/api/client';
import type {
  EmailImportConfig,
  EmailImportConfigCreate,
  EmailImportConfigUpdate,
  EmailConnectionTestResult,
  EmailSyncResult,
  FolderImportConfig,
  FolderImportConfigCreate,
  FolderImportConfigUpdate,
  FolderWatcherStatusResult,
  FolderPollResult,
  ImportRule,
  ImportRuleCreate,
  ImportRuleUpdate,
  ImportRuleReorderItem,
  RuleTestRequest,
  RuleTestResult,
  RuleTestAllResult,
  ImportLog,
  ImportLogFilters,
  ImportLogRetryResult,
  ImportLogStats,
  PaginatedResponse,
} from '../types';

const BASE_URL = '/api/v1/imports';

// =============================================================================
// Email Import Config CRUD
// =============================================================================

/**
 * Liste alle E-Mail-Import-Konfigurationen.
 */
export async function listEmailConfigs(): Promise<EmailImportConfig[]> {
  const response = await api.get<EmailImportConfig[]>(`${BASE_URL}/email/configs`);
  return response.data;
}

/**
 * Hole eine spezifische E-Mail-Import-Konfiguration.
 */
export async function getEmailConfig(configId: string): Promise<EmailImportConfig> {
  const response = await api.get<EmailImportConfig>(`${BASE_URL}/email/configs/${configId}`);
  return response.data;
}

/**
 * Erstelle eine neue E-Mail-Import-Konfiguration.
 */
export async function createEmailConfig(
  data: EmailImportConfigCreate
): Promise<EmailImportConfig> {
  const response = await api.post<EmailImportConfig>(`${BASE_URL}/email/configs`, data);
  return response.data;
}

/**
 * Aktualisiere eine E-Mail-Import-Konfiguration.
 */
export async function updateEmailConfig(
  configId: string,
  data: EmailImportConfigUpdate
): Promise<EmailImportConfig> {
  const response = await api.put<EmailImportConfig>(
    `${BASE_URL}/email/configs/${configId}`,
    data
  );
  return response.data;
}

/**
 * Loesche eine E-Mail-Import-Konfiguration.
 */
export async function deleteEmailConfig(configId: string): Promise<void> {
  await api.delete(`${BASE_URL}/email/configs/${configId}`);
}

/**
 * Teste die IMAP-Verbindung einer E-Mail-Import-Konfiguration.
 */
export async function testEmailConnection(
  configId: string
): Promise<EmailConnectionTestResult> {
  const response = await api.post<EmailConnectionTestResult>(
    `${BASE_URL}/email/configs/${configId}/test`
  );
  return response.data;
}

/**
 * Starte manuellen Sync fuer eine E-Mail-Import-Konfiguration.
 */
export async function syncEmailConfig(configId: string): Promise<EmailSyncResult> {
  const response = await api.post<EmailSyncResult>(
    `${BASE_URL}/email/configs/${configId}/sync`
  );
  return response.data;
}

// =============================================================================
// Folder Import Config CRUD
// =============================================================================

/**
 * Liste alle Ordner-Import-Konfigurationen.
 */
export async function listFolderConfigs(): Promise<FolderImportConfig[]> {
  const response = await api.get<FolderImportConfig[]>(`${BASE_URL}/folder/configs`);
  return response.data;
}

/**
 * Hole eine spezifische Ordner-Import-Konfiguration.
 */
export async function getFolderConfig(configId: string): Promise<FolderImportConfig> {
  const response = await api.get<FolderImportConfig>(
    `${BASE_URL}/folder/configs/${configId}`
  );
  return response.data;
}

/**
 * Erstelle eine neue Ordner-Import-Konfiguration.
 */
export async function createFolderConfig(
  data: FolderImportConfigCreate
): Promise<FolderImportConfig> {
  const response = await api.post<FolderImportConfig>(`${BASE_URL}/folder/configs`, data);
  return response.data;
}

/**
 * Aktualisiere eine Ordner-Import-Konfiguration.
 */
export async function updateFolderConfig(
  configId: string,
  data: FolderImportConfigUpdate
): Promise<FolderImportConfig> {
  const response = await api.put<FolderImportConfig>(
    `${BASE_URL}/folder/configs/${configId}`,
    data
  );
  return response.data;
}

/**
 * Loesche eine Ordner-Import-Konfiguration.
 */
export async function deleteFolderConfig(configId: string): Promise<void> {
  await api.delete(`${BASE_URL}/folder/configs/${configId}`);
}

/**
 * Starte den Watcher fuer eine Ordner-Import-Konfiguration.
 */
export async function startFolderWatcher(
  configId: string
): Promise<FolderWatcherStatusResult> {
  const response = await api.post<FolderWatcherStatusResult>(
    `${BASE_URL}/folder/configs/${configId}/start`
  );
  return response.data;
}

/**
 * Stoppe den Watcher fuer eine Ordner-Import-Konfiguration.
 */
export async function stopFolderWatcher(
  configId: string
): Promise<FolderWatcherStatusResult> {
  const response = await api.post<FolderWatcherStatusResult>(
    `${BASE_URL}/folder/configs/${configId}/stop`
  );
  return response.data;
}

/**
 * Starte manuelles Polling fuer eine Ordner-Import-Konfiguration.
 */
export async function pollFolderConfig(configId: string): Promise<FolderPollResult> {
  const response = await api.post<FolderPollResult>(
    `${BASE_URL}/folder/configs/${configId}/poll`
  );
  return response.data;
}

// =============================================================================
// Import Rules CRUD
// =============================================================================

/**
 * Liste alle Import-Regeln.
 */
export async function listImportRules(sourceType?: 'email' | 'folder' | 'all'): Promise<ImportRule[]> {
  const params = sourceType ? { source_type: sourceType } : undefined;
  const response = await api.get<ImportRule[]>(`${BASE_URL}/rules`, { params });
  return response.data;
}

/**
 * Hole eine spezifische Import-Regel.
 */
export async function getImportRule(ruleId: string): Promise<ImportRule> {
  const response = await api.get<ImportRule>(`${BASE_URL}/rules/${ruleId}`);
  return response.data;
}

/**
 * Erstelle eine neue Import-Regel.
 */
export async function createImportRule(data: ImportRuleCreate): Promise<ImportRule> {
  const response = await api.post<ImportRule>(`${BASE_URL}/rules`, data);
  return response.data;
}

/**
 * Aktualisiere eine Import-Regel.
 */
export async function updateImportRule(
  ruleId: string,
  data: ImportRuleUpdate
): Promise<ImportRule> {
  const response = await api.put<ImportRule>(`${BASE_URL}/rules/${ruleId}`, data);
  return response.data;
}

/**
 * Loesche eine Import-Regel.
 */
export async function deleteImportRule(ruleId: string): Promise<void> {
  await api.delete(`${BASE_URL}/rules/${ruleId}`);
}

/**
 * Aendere die Prioritaeten mehrerer Import-Regeln.
 */
export async function reorderImportRules(
  rules: ImportRuleReorderItem[]
): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(
    `${BASE_URL}/rules/reorder`,
    { rules }
  );
  return response.data;
}

/**
 * Teste eine Import-Regel gegen Metadaten.
 */
export async function testImportRule(data: RuleTestRequest): Promise<RuleTestResult> {
  const response = await api.post<RuleTestResult>(`${BASE_URL}/rules/test`, data);
  return response.data;
}

/**
 * Teste alle aktiven Regeln gegen Metadaten.
 */
export async function testAllImportRules(
  metadata: Record<string, unknown>
): Promise<RuleTestAllResult> {
  const response = await api.post<RuleTestAllResult>(`${BASE_URL}/rules/test-all`, {
    metadata,
  });
  return response.data;
}

// =============================================================================
// Import Logs
// =============================================================================

/**
 * Liste Import-Logs mit Filtern.
 */
export async function listImportLogs(
  filters?: ImportLogFilters
): Promise<PaginatedResponse<ImportLog>> {
  const response = await api.get<PaginatedResponse<ImportLog>>(`${BASE_URL}/logs`, {
    params: filters,
  });
  return response.data;
}

/**
 * Hole ein spezifisches Import-Log.
 */
export async function getImportLog(logId: string): Promise<ImportLog> {
  const response = await api.get<ImportLog>(`${BASE_URL}/logs/${logId}`);
  return response.data;
}

/**
 * Wiederhole einen fehlgeschlagenen Import.
 */
export async function retryImport(logId: string): Promise<ImportLogRetryResult> {
  const response = await api.post<ImportLogRetryResult>(`${BASE_URL}/logs/${logId}/retry`);
  return response.data;
}

/**
 * Hole Import-Statistiken.
 */
export async function getImportStats(): Promise<ImportLogStats> {
  const response = await api.get<ImportLogStats>(`${BASE_URL}/logs/stats`);
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const importKeys = {
  all: ['imports'] as const,

  // Email configs
  emailConfigs: () => [...importKeys.all, 'email', 'configs'] as const,
  emailConfig: (id: string) => [...importKeys.emailConfigs(), id] as const,

  // Folder configs
  folderConfigs: () => [...importKeys.all, 'folder', 'configs'] as const,
  folderConfig: (id: string) => [...importKeys.folderConfigs(), id] as const,

  // Rules
  rules: (sourceType?: string) => [...importKeys.all, 'rules', sourceType] as const,
  rule: (id: string) => [...importKeys.all, 'rules', 'detail', id] as const,

  // Logs
  logs: (filters?: ImportLogFilters) => [...importKeys.all, 'logs', filters] as const,
  log: (id: string) => [...importKeys.all, 'logs', 'detail', id] as const,
  logStats: () => [...importKeys.all, 'logs', 'stats'] as const,
};
