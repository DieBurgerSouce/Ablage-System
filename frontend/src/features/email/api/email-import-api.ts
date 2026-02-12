/**
 * E-Mail Import API Service
 *
 * TanStack Query API-Layer für den E-Mail-Drag-and-Drop-Import.
 */

import { apiClient } from '@/lib/api/client';
import type {
  EmlParseResponse,
  EmlImportRequest,
  EmlImportResponse,
  EmailConfig,
  ImportLog,
  ImportStats,
  ImportRule,
} from '../types/email-types';

// Query key factory
export const emailImportKeys = {
  all: ['email-import'] as const,
  configs: () => [...emailImportKeys.all, 'configs'] as const,
  logs: (params?: Record<string, string>) => [...emailImportKeys.all, 'logs', params] as const,
  stats: () => [...emailImportKeys.all, 'stats'] as const,
  ruleSchema: (type: string) => [...emailImportKeys.all, 'rule-schema', type] as const,
};

/** .eml-Datei hochladen und parsen */
export async function uploadEmlFile(file: File): Promise<EmlParseResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<EmlParseResponse>(
    '/imports/email/upload-eml',
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return response.data;
}

/** Ausgewählte Anhänge importieren */
export async function importEmlAttachments(
  request: EmlImportRequest,
): Promise<EmlImportResponse> {
  const response = await apiClient.post<EmlImportResponse>(
    '/imports/email/import-eml',
    request,
  );
  return response.data;
}

/** Alle E-Mail-Konfigurationen abrufen */
export async function getEmailConfigs(): Promise<EmailConfig[]> {
  const response = await apiClient.get<EmailConfig[]>('/imports/email/configs');
  return response.data;
}

/** Import-Protokolle abrufen */
export async function getImportLogs(
  params?: { limit?: number; offset?: number },
): Promise<ImportLog[]> {
  const response = await apiClient.get<ImportLog[]>('/imports/email/logs', {
    params,
  });
  return response.data;
}

/** Import-Statistiken abrufen */
export async function getImportStats(): Promise<ImportStats> {
  const response = await apiClient.get<ImportStats>('/imports/email/stats');
  return response.data;
}

/** Regel-Schema (Felder, Operatoren, Aktionen) abrufen */
export async function getRuleSchema(
  type: string,
): Promise<{ fields: string[]; operators: string[]; actions: string[] }> {
  const response = await apiClient.get<{
    fields: string[];
    operators: string[];
    actions: string[];
  }>(`/imports/rules/schema/${encodeURIComponent(type)}`);
  return response.data;
}

/** Import-Regel gegen Beispieldaten testen */
export async function testImportRule(
  rule: ImportRule,
): Promise<{ matches: number; sample_results: string[] }> {
  const response = await apiClient.post<{
    matches: number;
    sample_results: string[];
  }>('/imports/rules/test', rule);
  return response.data;
}

/** IMAP-Verbindung testen */
export async function testImapConnection(params: {
  host: string;
  port: number;
  use_ssl: boolean;
  username: string;
  password: string;
}): Promise<{ success: boolean; folders: string[]; message: string }> {
  const response = await apiClient.post<{
    success: boolean;
    folders: string[];
    message: string;
  }>('/imports/email/test-connection', params);
  return response.data;
}

/** E-Mail-Konfiguration erstellen */
export async function createEmailConfig(
  config: Omit<EmailConfig, 'id' | 'last_sync_at'> & { password: string },
): Promise<EmailConfig> {
  const response = await apiClient.post<EmailConfig>(
    '/imports/email/configs',
    config,
  );
  return response.data;
}
