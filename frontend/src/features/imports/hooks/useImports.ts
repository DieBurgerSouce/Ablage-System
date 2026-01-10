/**
 * Import System React Query Hooks
 *
 * Custom Hooks fuer E-Mail-Import, Ordner-Import und Import-Regeln.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  // Email configs
  listEmailConfigs,
  getEmailConfig,
  createEmailConfig,
  updateEmailConfig,
  deleteEmailConfig,
  testEmailConnection,
  syncEmailConfig,
  // Folder configs
  listFolderConfigs,
  getFolderConfig,
  createFolderConfig,
  updateFolderConfig,
  deleteFolderConfig,
  startFolderWatcher,
  stopFolderWatcher,
  pollFolderConfig,
  // Rules
  listImportRules,
  getImportRule,
  createImportRule,
  updateImportRule,
  deleteImportRule,
  reorderImportRules,
  testImportRule,
  testAllImportRules,
  // Logs
  listImportLogs,
  getImportLog,
  retryImport,
  getImportStats,
  // Keys
  importKeys,
} from '../api';
import type {
  EmailImportConfigCreate,
  EmailImportConfigUpdate,
  FolderImportConfigCreate,
  FolderImportConfigUpdate,
  ImportRuleCreate,
  ImportRuleUpdate,
  ImportRuleReorderItem,
  RuleTestRequest,
  ImportLogFilters,
} from '../types';

// =============================================================================
// Email Config Hooks
// =============================================================================

/**
 * Hook to list all email import configurations.
 */
export function useEmailConfigs() {
  return useQuery({
    queryKey: importKeys.emailConfigs(),
    queryFn: listEmailConfigs,
  });
}

/**
 * Hook to get a specific email import configuration.
 */
export function useEmailConfig(configId: string | undefined) {
  return useQuery({
    queryKey: importKeys.emailConfig(configId ?? ''),
    queryFn: () => getEmailConfig(configId!),
    enabled: !!configId,
  });
}

/**
 * Hook to create an email import configuration.
 */
export function useCreateEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EmailImportConfigCreate) => createEmailConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.emailConfigs() });
      toast.success('E-Mail-Import-Konfiguration erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook to update an email import configuration.
 */
export function useUpdateEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      configId,
      data,
    }: {
      configId: string;
      data: EmailImportConfigUpdate;
    }) => updateEmailConfig(configId, data),
    onSuccess: (_, { configId }) => {
      queryClient.invalidateQueries({ queryKey: importKeys.emailConfigs() });
      queryClient.invalidateQueries({ queryKey: importKeys.emailConfig(configId) });
      toast.success('E-Mail-Import-Konfiguration aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook to delete an email import configuration.
 */
export function useDeleteEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => deleteEmailConfig(configId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.emailConfigs() });
      toast.success('E-Mail-Import-Konfiguration gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Hook to test an email connection.
 */
export function useTestEmailConnection() {
  return useMutation({
    mutationFn: (configId: string) => testEmailConnection(configId),
    onSuccess: (result) => {
      if (result.success) {
        toast.success(
          `Verbindung erfolgreich! ${result.message_count ?? 0} Nachrichten gefunden`
        );
      } else {
        toast.error(`Verbindung fehlgeschlagen: ${result.error}`);
      }
    },
    onError: (error: Error) => {
      toast.error(`Verbindungstest fehlgeschlagen: ${error.message}`);
    },
  });
}

/**
 * Hook to trigger manual email sync.
 */
export function useSyncEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => syncEmailConfig(configId),
    onSuccess: (result, configId) => {
      queryClient.invalidateQueries({ queryKey: importKeys.emailConfig(configId) });
      queryClient.invalidateQueries({ queryKey: importKeys.logs() });
      toast.success(`Synchronisation gestartet (Task: ${result.task_id})`);
    },
    onError: (error: Error) => {
      toast.error(`Sync-Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Folder Config Hooks
// =============================================================================

/**
 * Hook to list all folder import configurations.
 */
export function useFolderConfigs() {
  return useQuery({
    queryKey: importKeys.folderConfigs(),
    queryFn: listFolderConfigs,
  });
}

/**
 * Hook to get a specific folder import configuration.
 */
export function useFolderConfig(configId: string | undefined) {
  return useQuery({
    queryKey: importKeys.folderConfig(configId ?? ''),
    queryFn: () => getFolderConfig(configId!),
    enabled: !!configId,
  });
}

/**
 * Hook to create a folder import configuration.
 */
export function useCreateFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FolderImportConfigCreate) => createFolderConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfigs() });
      toast.success('Ordner-Import-Konfiguration erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook to update a folder import configuration.
 */
export function useUpdateFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      configId,
      data,
    }: {
      configId: string;
      data: FolderImportConfigUpdate;
    }) => updateFolderConfig(configId, data),
    onSuccess: (_, { configId }) => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfigs() });
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfig(configId) });
      toast.success('Ordner-Import-Konfiguration aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook to delete a folder import configuration.
 */
export function useDeleteFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => deleteFolderConfig(configId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfigs() });
      toast.success('Ordner-Import-Konfiguration gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Hook to start folder watcher.
 */
export function useStartFolderWatcher() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => startFolderWatcher(configId),
    onSuccess: (result, configId) => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfig(configId) });
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfigs() });
      if (result.success) {
        toast.success('Ordner-Watcher gestartet');
      } else {
        toast.warning(result.message);
      }
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Starten: ${error.message}`);
    },
  });
}

/**
 * Hook to stop folder watcher.
 */
export function useStopFolderWatcher() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => stopFolderWatcher(configId),
    onSuccess: (result, configId) => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfig(configId) });
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfigs() });
      if (result.success) {
        toast.success('Ordner-Watcher gestoppt');
      } else {
        toast.warning(result.message);
      }
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Stoppen: ${error.message}`);
    },
  });
}

/**
 * Hook to trigger manual folder poll.
 */
export function usePollFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => pollFolderConfig(configId),
    onSuccess: (result, configId) => {
      queryClient.invalidateQueries({ queryKey: importKeys.folderConfig(configId) });
      queryClient.invalidateQueries({ queryKey: importKeys.logs() });
      toast.success(`Ordner-Scan gestartet (Task: ${result.task_id})`);
    },
    onError: (error: Error) => {
      toast.error(`Scan-Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Import Rules Hooks
// =============================================================================

/**
 * Hook to list all import rules.
 */
export function useImportRules(sourceType?: 'email' | 'folder' | 'all') {
  return useQuery({
    queryKey: importKeys.rules(sourceType),
    queryFn: () => listImportRules(sourceType),
  });
}

/**
 * Hook to get a specific import rule.
 */
export function useImportRule(ruleId: string | undefined) {
  return useQuery({
    queryKey: importKeys.rule(ruleId ?? ''),
    queryFn: () => getImportRule(ruleId!),
    enabled: !!ruleId,
  });
}

/**
 * Hook to create an import rule.
 */
export function useCreateImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ImportRuleCreate) => createImportRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.rules() });
      toast.success('Import-Regel erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Hook to update an import rule.
 */
export function useUpdateImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ruleId, data }: { ruleId: string; data: ImportRuleUpdate }) =>
      updateImportRule(ruleId, data),
    onSuccess: (_, { ruleId }) => {
      queryClient.invalidateQueries({ queryKey: importKeys.rules() });
      queryClient.invalidateQueries({ queryKey: importKeys.rule(ruleId) });
      toast.success('Import-Regel aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook to delete an import rule.
 */
export function useDeleteImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: string) => deleteImportRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.rules() });
      toast.success('Import-Regel gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Löschen: ${error.message}`);
    },
  });
}

/**
 * Hook to reorder import rules.
 */
export function useReorderImportRules() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (rules: ImportRuleReorderItem[]) => reorderImportRules(rules),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importKeys.rules() });
      toast.success('Regel-Reihenfolge aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Neuordnen: ${error.message}`);
    },
  });
}

/**
 * Hook to test an import rule.
 */
export function useTestImportRule() {
  return useMutation({
    mutationFn: (data: RuleTestRequest) => testImportRule(data),
    onSuccess: (result) => {
      if (result.matched) {
        toast.success(`Regel "${result.rule_name}" trifft zu!`);
      } else {
        toast.info('Regel trifft nicht zu');
      }
    },
    onError: (error: Error) => {
      toast.error(`Test fehlgeschlagen: ${error.message}`);
    },
  });
}

/**
 * Hook to test all import rules.
 */
export function useTestAllImportRules() {
  return useMutation({
    mutationFn: (metadata: Record<string, unknown>) => testAllImportRules(metadata),
    onSuccess: (result) => {
      if (result.matched_rules.length > 0) {
        toast.success(
          `${result.matched_rules.length} von ${result.tested_rules} Regeln treffen zu`
        );
      } else {
        toast.info('Keine Regel trifft zu');
      }
    },
    onError: (error: Error) => {
      toast.error(`Test fehlgeschlagen: ${error.message}`);
    },
  });
}

// =============================================================================
// Import Logs Hooks
// =============================================================================

/**
 * Hook to list import logs with filters.
 */
export function useImportLogs(filters?: ImportLogFilters) {
  return useQuery({
    queryKey: importKeys.logs(filters),
    queryFn: () => listImportLogs(filters),
    refetchInterval: 30000, // Alle 30 Sekunden aktualisieren
  });
}

/**
 * Hook to get a specific import log.
 */
export function useImportLog(logId: string | undefined) {
  return useQuery({
    queryKey: importKeys.log(logId ?? ''),
    queryFn: () => getImportLog(logId!),
    enabled: !!logId,
  });
}

/**
 * Hook to retry a failed import.
 */
export function useRetryImport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (logId: string) => retryImport(logId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: importKeys.logs() });
      queryClient.invalidateQueries({ queryKey: importKeys.logStats() });
      if (result.success) {
        toast.success(`Wiederholung gestartet (Task: ${result.task_id})`);
      } else {
        toast.warning(result.message);
      }
    },
    onError: (error: Error) => {
      toast.error(`Wiederholung fehlgeschlagen: ${error.message}`);
    },
  });
}

/**
 * Hook to get import statistics.
 */
export function useImportStats() {
  return useQuery({
    queryKey: importKeys.logStats(),
    queryFn: getImportStats,
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}
