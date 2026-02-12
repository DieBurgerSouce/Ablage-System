/**
 * Import Query Hooks
 *
 * TanStack Query Hooks für Email-, Folder-Import und Import-Regeln.
 */

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  emailConfigService,
  folderConfigService,
  importRulesService,
  importLogsService,
  ImportApiError,
} from '../api/imports-api';
import type {
  EmailConfigCreate,
  EmailConfigUpdate,
  FolderConfigCreate,
  FolderConfigUpdate,
  ImportRuleCreate,
  ImportRuleUpdate,
  ImportLogFilter,
} from '../types/import-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  configs: 60 * 1000,        // 1 Minute
  rules: 60 * 1000,          // 1 Minute
  logs: 30 * 1000,           // 30 Sekunden
  stats: 5 * 60 * 1000,      // 5 Minuten
  schema: 30 * 60 * 1000,    // 30 Minuten - Schema ändert sich selten
} as const;

const GC_TIMES = {
  configs: 10 * 60 * 1000,
  rules: 10 * 60 * 1000,
  logs: 5 * 60 * 1000,
  stats: 30 * 60 * 1000,
  schema: 60 * 60 * 1000,
} as const;

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    if (error instanceof ImportApiError && error.statusCode) {
      if (error.statusCode >= 400 && error.statusCode < 500) {
        return false;
      }
    }
    return failureCount < 3;
  },
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
} as const;

// ==================== Query Keys ====================

export const importQueryKeys = {
  all: ['imports'] as const,

  // Email Configs
  emailConfigs: () => [...importQueryKeys.all, 'email', 'configs'] as const,
  emailConfig: (id: string) => [...importQueryKeys.emailConfigs(), id] as const,

  // Folder Configs
  folderConfigs: () => [...importQueryKeys.all, 'folder', 'configs'] as const,
  folderConfig: (id: string) => [...importQueryKeys.folderConfigs(), id] as const,

  // Rules
  rules: () => [...importQueryKeys.all, 'rules'] as const,
  rule: (id: string) => [...importQueryKeys.rules(), id] as const,
  ruleSchema: () => [...importQueryKeys.all, 'rules', 'schema'] as const,

  // Logs
  logs: () => [...importQueryKeys.all, 'logs'] as const,
  logsFiltered: (filter: ImportLogFilter) => [...importQueryKeys.logs(), filter] as const,
  log: (id: string) => [...importQueryKeys.logs(), id] as const,
  stats: (dateFrom?: string, dateTo?: string) =>
    [...importQueryKeys.all, 'stats', dateFrom, dateTo] as const,
};

// ==================== Email Config Hooks ====================

/**
 * Liste aller Email-Konfigurationen
 */
export function useEmailConfigs(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.emailConfigs(),
    queryFn: () => emailConfigService.listConfigs(),
    staleTime: STALE_TIMES.configs,
    gcTime: GC_TIMES.configs,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelne Email-Konfiguration
 */
export function useEmailConfig(configId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.emailConfig(configId),
    queryFn: () => emailConfigService.getConfig(configId),
    staleTime: STALE_TIMES.configs,
    gcTime: GC_TIMES.configs,
    enabled: options?.enabled !== false && !!configId,
    ...RETRY_CONFIG,
  });
}

/**
 * Email-Konfiguration erstellen
 */
export function useCreateEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EmailConfigCreate) => emailConfigService.createConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importQueryKeys.emailConfigs() });
    },
  });
}

/**
 * Email-Konfiguration aktualisieren
 */
export function useUpdateEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      configId,
      data,
    }: {
      configId: string;
      data: EmailConfigUpdate;
    }) => emailConfigService.updateConfig(configId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.emailConfig(variables.configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.emailConfigs() });
    },
  });
}

/**
 * Email-Konfiguration löschen
 */
export function useDeleteEmailConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => emailConfigService.deleteConfig(configId),
    onSuccess: (_, configId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.emailConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.emailConfigs() });
    },
  });
}

/**
 * Verbindung testen
 */
export function useTestEmailConnection() {
  return useMutation({
    mutationFn: (configId: string) => emailConfigService.testConnection(configId),
  });
}

/**
 * Manuellen Sync auslösen
 */
export function useTriggerEmailSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => emailConfigService.triggerSync(configId),
    onSuccess: (_, configId) => {
      // Refresh config to update last_sync_at
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.emailConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.logs() });
    },
  });
}

// ==================== Folder Config Hooks ====================

/**
 * Liste aller Folder-Konfigurationen
 */
export function useFolderConfigs(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.folderConfigs(),
    queryFn: () => folderConfigService.listConfigs(),
    staleTime: STALE_TIMES.configs,
    gcTime: GC_TIMES.configs,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelne Folder-Konfiguration
 */
export function useFolderConfig(configId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.folderConfig(configId),
    queryFn: () => folderConfigService.getConfig(configId),
    staleTime: STALE_TIMES.configs,
    gcTime: GC_TIMES.configs,
    enabled: options?.enabled !== false && !!configId,
    ...RETRY_CONFIG,
  });
}

/**
 * Folder-Konfiguration erstellen
 */
export function useCreateFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FolderConfigCreate) => folderConfigService.createConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importQueryKeys.folderConfigs() });
    },
  });
}

/**
 * Folder-Konfiguration aktualisieren
 */
export function useUpdateFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      configId,
      data,
    }: {
      configId: string;
      data: FolderConfigUpdate;
    }) => folderConfigService.updateConfig(configId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.folderConfig(variables.configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.folderConfigs() });
    },
  });
}

/**
 * Folder-Konfiguration löschen
 */
export function useDeleteFolderConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => folderConfigService.deleteConfig(configId),
    onSuccess: (_, configId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.folderConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.folderConfigs() });
    },
  });
}

/**
 * Watcher starten
 */
export function useStartFolderWatcher() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => folderConfigService.startWatcher(configId),
    onSuccess: (_, configId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.folderConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.folderConfigs() });
    },
  });
}

/**
 * Watcher stoppen
 */
export function useStopFolderWatcher() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => folderConfigService.stopWatcher(configId),
    onSuccess: (_, configId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.folderConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.folderConfigs() });
    },
  });
}

/**
 * Manuellen Poll auslösen
 */
export function useTriggerFolderPoll() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (configId: string) => folderConfigService.triggerPoll(configId),
    onSuccess: (_, configId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.folderConfig(configId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.logs() });
    },
  });
}

// ==================== Import Rules Hooks ====================

/**
 * Liste aller Import-Regeln
 */
export function useImportRules(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.rules(),
    queryFn: () => importRulesService.listRules(),
    staleTime: STALE_TIMES.rules,
    gcTime: GC_TIMES.rules,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelne Import-Regel
 */
export function useImportRule(ruleId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.rule(ruleId),
    queryFn: () => importRulesService.getRule(ruleId),
    staleTime: STALE_TIMES.rules,
    gcTime: GC_TIMES.rules,
    enabled: options?.enabled !== false && !!ruleId,
    ...RETRY_CONFIG,
  });
}

/**
 * Import-Regel erstellen
 */
export function useCreateImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ImportRuleCreate) => importRulesService.createRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importQueryKeys.rules() });
    },
  });
}

/**
 * Import-Regel aktualisieren
 */
export function useUpdateImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      ruleId,
      data,
    }: {
      ruleId: string;
      data: ImportRuleUpdate;
    }) => importRulesService.updateRule(ruleId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.rule(variables.ruleId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.rules() });
    },
  });
}

/**
 * Import-Regel löschen
 */
export function useDeleteImportRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: string) => importRulesService.deleteRule(ruleId),
    onSuccess: (_, ruleId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.rule(ruleId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.rules() });
    },
  });
}

/**
 * Regeln neu ordnen
 */
export function useReorderImportRules() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (priorities: Array<{ ruleId: string; priority: number }>) =>
      importRulesService.reorderRules(priorities),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: importQueryKeys.rules() });
    },
  });
}

/**
 * Regel testen
 */
export function useTestImportRule() {
  return useMutation({
    mutationFn: ({
      ruleId,
      metadata,
      sourceType,
    }: {
      ruleId: string;
      metadata: Record<string, unknown>;
      sourceType?: 'email' | 'folder';
    }) => importRulesService.testRule(ruleId, metadata, sourceType),
  });
}

/**
 * Alle Regeln testen
 */
export function useTestAllImportRules() {
  return useMutation({
    mutationFn: ({
      metadata,
      sourceType,
    }: {
      metadata: Record<string, unknown>;
      sourceType?: 'email' | 'folder';
    }) => importRulesService.testAllRules(metadata, sourceType),
  });
}

/**
 * Regel-Schema (Felder, Operatoren, Actions)
 */
export function useRuleSchema(options?: { enabled?: boolean }) {
  const fieldsQuery = useQuery({
    queryKey: [...importQueryKeys.ruleSchema(), 'fields'] as const,
    queryFn: () => importRulesService.getFields(),
    staleTime: STALE_TIMES.schema,
    gcTime: GC_TIMES.schema,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });

  const operatorsQuery = useQuery({
    queryKey: [...importQueryKeys.ruleSchema(), 'operators'] as const,
    queryFn: () => importRulesService.getOperators(),
    staleTime: STALE_TIMES.schema,
    gcTime: GC_TIMES.schema,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });

  const actionsQuery = useQuery({
    queryKey: [...importQueryKeys.ruleSchema(), 'actions'] as const,
    queryFn: () => importRulesService.getActions(),
    staleTime: STALE_TIMES.schema,
    gcTime: GC_TIMES.schema,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });

  return {
    fields: fieldsQuery.data ?? [],
    operators: operatorsQuery.data ?? [],
    actions: actionsQuery.data ?? [],
    isLoading: fieldsQuery.isLoading || operatorsQuery.isLoading || actionsQuery.isLoading,
    isError: fieldsQuery.isError || operatorsQuery.isError || actionsQuery.isError,
  };
}

// ==================== Import Logs Hooks ====================

/**
 * Import-Logs mit Filter
 */
export function useImportLogs(
  filter: ImportLogFilter = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: importQueryKeys.logsFiltered(filter),
    queryFn: () => importLogsService.listLogs(filter),
    staleTime: STALE_TIMES.logs,
    gcTime: GC_TIMES.logs,
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelnes Import-Log
 */
export function useImportLog(logId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: importQueryKeys.log(logId),
    queryFn: () => importLogsService.getLog(logId),
    staleTime: STALE_TIMES.logs,
    gcTime: GC_TIMES.logs,
    enabled: options?.enabled !== false && !!logId,
    ...RETRY_CONFIG,
  });
}

/**
 * Import wiederholen
 */
export function useRetryImport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (logId: string) => importLogsService.retryImport(logId),
    onSuccess: (_, logId) => {
      queryClient.invalidateQueries({
        queryKey: importQueryKeys.log(logId),
      });
      queryClient.invalidateQueries({ queryKey: importQueryKeys.logs() });
    },
  });
}

/**
 * Frontend Stats Response für ImportsPage
 */
export interface ImportDashboardStats {
  documentsImportedToday: number;
  documentsImportedThisWeek: number;
  pendingImports: number;
  failedImportsLast24h: number;
  totalImports: number;
  successfulImports: number;
  avgProcessingTimeMs: number;
}

/**
 * Import-Statistiken (transformiert für Dashboard)
 */
export function useImportStats(
  dateFrom?: string,
  dateTo?: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: importQueryKeys.stats(dateFrom, dateTo),
    queryFn: async (): Promise<ImportDashboardStats> => {
      const stats = await importLogsService.getStats(dateFrom, dateTo);
      // Transformiere Backend-Stats zu Frontend-Dashboard-Stats
      return {
        documentsImportedToday: stats.documentsCreated ?? stats.successfulImports ?? 0,
        documentsImportedThisWeek: stats.totalImports ?? 0,
        pendingImports: 0, // Backend liefert dies nicht direkt, wird aus Logs berechnet
        failedImportsLast24h: stats.failedImports ?? 0,
        totalImports: stats.totalImports ?? 0,
        successfulImports: stats.successfulImports ?? 0,
        avgProcessingTimeMs: stats.avgProcessingTimeMs ?? 0,
      };
    },
    staleTime: STALE_TIMES.stats,
    gcTime: GC_TIMES.stats,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

// ==================== Combined Hooks ====================

/**
 * Kombinierter Hook für Import-Dashboard
 */
export function useImportDashboard(options?: { enabled?: boolean }) {
  const isEnabled = options?.enabled !== false;

  const emailConfigsQuery = useEmailConfigs({ enabled: isEnabled });
  const folderConfigsQuery = useFolderConfigs({ enabled: isEnabled });
  const statsQuery = useImportStats(undefined, undefined, { enabled: isEnabled });

  return {
    emailConfigs: emailConfigsQuery.data ?? [],
    folderConfigs: folderConfigsQuery.data ?? [],
    stats: statsQuery.data,
    isLoading:
      emailConfigsQuery.isLoading ||
      folderConfigsQuery.isLoading ||
      statsQuery.isLoading,
    isError:
      emailConfigsQuery.isError ||
      folderConfigsQuery.isError ||
      statsQuery.isError,
    refetch: () => {
      emailConfigsQuery.refetch();
      folderConfigsQuery.refetch();
      statsQuery.refetch();
    },
  };
}

/**
 * Hook für alle Email-Config-Mutationen
 */
export function useEmailConfigMutations() {
  const createConfig = useCreateEmailConfig();
  const updateConfig = useUpdateEmailConfig();
  const deleteConfig = useDeleteEmailConfig();
  const testConnection = useTestEmailConnection();
  const triggerSync = useTriggerEmailSync();

  const isAnyMutating =
    createConfig.isPending ||
    updateConfig.isPending ||
    deleteConfig.isPending ||
    testConnection.isPending ||
    triggerSync.isPending;

  return {
    createConfig,
    updateConfig,
    deleteConfig,
    testConnection,
    triggerSync,
    isAnyMutating,
  };
}

/**
 * Hook für alle Folder-Config-Mutationen
 */
export function useFolderConfigMutations() {
  const createConfig = useCreateFolderConfig();
  const updateConfig = useUpdateFolderConfig();
  const deleteConfig = useDeleteFolderConfig();
  const startWatcher = useStartFolderWatcher();
  const stopWatcher = useStopFolderWatcher();
  const triggerPoll = useTriggerFolderPoll();

  const isAnyMutating =
    createConfig.isPending ||
    updateConfig.isPending ||
    deleteConfig.isPending ||
    startWatcher.isPending ||
    stopWatcher.isPending ||
    triggerPoll.isPending;

  return {
    createConfig,
    updateConfig,
    deleteConfig,
    startWatcher,
    stopWatcher,
    triggerPoll,
    isAnyMutating,
  };
}

/**
 * Hook für alle Import-Rule-Mutationen
 */
export function useImportRuleMutations() {
  const createRule = useCreateImportRule();
  const updateRule = useUpdateImportRule();
  const deleteRule = useDeleteImportRule();
  const reorderRules = useReorderImportRules();

  const isAnyMutating =
    createRule.isPending ||
    updateRule.isPending ||
    deleteRule.isPending ||
    reorderRules.isPending;

  return {
    createRule,
    updateRule,
    deleteRule,
    reorderRules,
    isAnyMutating,
  };
}

// ==================== Prefetch Helpers ====================

/**
 * Prefetch Email-Configs
 */
export function usePrefetchEmailConfigs() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: importQueryKeys.emailConfigs(),
      queryFn: () => emailConfigService.listConfigs(),
      staleTime: STALE_TIMES.configs,
    });
  }, [queryClient]);
}

/**
 * Prefetch Folder-Configs
 */
export function usePrefetchFolderConfigs() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: importQueryKeys.folderConfigs(),
      queryFn: () => folderConfigService.listConfigs(),
      staleTime: STALE_TIMES.configs,
    });
  }, [queryClient]);
}

/**
 * Invalidiert alle Import-relevanten Queries
 */
export function useInvalidateImportQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: importQueryKeys.all });
  }, [queryClient]);
}
