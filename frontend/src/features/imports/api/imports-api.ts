/**
 * Imports API Service
 *
 * Kommuniziert mit den /api/v1/imports Endpoints
 * fuer Email-Import, Folder-Import und Import-Regeln.
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type {
  // Email Config
  EmailConfigBackend,
  EmailConfigResponse,
  EmailConfigListItem,
  EmailConfigCreate,
  EmailConfigUpdate,
  // Folder Config
  FolderConfigBackend,
  FolderConfigResponse,
  FolderConfigListItem,
  FolderConfigCreate,
  FolderConfigUpdate,
  // Rules
  ImportRuleBackend,
  ImportRuleResponse,
  ImportRuleListItem,
  ImportRuleCreate,
  ImportRuleUpdate,
  RuleConditions,
  RuleActions,
  RuleFieldSchema,
  RuleOperatorSchema,
  RuleActionSchema,
  // Logs
  ImportLogBackend,
  ImportLogResponse,
  ImportLogFilter,
  // Stats
  ImportStatsBackend,
  ImportStatsResponse,
} from '../types/import-types';

// ==================== Error Classes ====================

export class ImportApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'ImportApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformEmailConfig(cfg: EmailConfigBackend): EmailConfigResponse {
  return {
    id: cfg.id,
    name: cfg.name,
    imapServer: cfg.imap_server,
    imapPort: cfg.imap_port,
    useSsl: cfg.use_ssl,
    useStarttls: cfg.use_starttls,
    imapFolder: cfg.imap_folder,
    processedFolder: cfg.processed_folder,
    errorFolder: cfg.error_folder,
    syncIntervalMinutes: cfg.sync_interval_minutes,
    filterFromAddresses: cfg.filter_from_addresses ?? [],
    filterSubjectPatterns: cfg.filter_subject_patterns ?? [],
    filterAttachmentTypes: cfg.filter_attachment_types ?? [],
    extractAttachmentsOnly: cfg.extract_attachments_only,
    includeEmailBodyAsDocument: cfg.include_email_body_as_document,
    autoClassify: cfg.auto_classify,
    autoOcr: cfg.auto_ocr,
    defaultFolderId: cfg.default_folder_id,
    companyId: cfg.company_id,
    isActive: cfg.is_active,
    connectionStatus: cfg.connection_status,
    lastSyncAt: cfg.last_sync_at,
    totalEmailsProcessed: cfg.total_emails_processed,
    totalDocumentsCreated: cfg.total_documents_created,
    lastError: cfg.last_error,
    errorCount: cfg.error_count,
    createdAt: cfg.created_at,
    updatedAt: cfg.updated_at,
  };
}

function transformEmailConfigListItem(cfg: {
  id: string;
  name: string;
  imap_server: string;
  imap_folder: string;
  is_active: boolean;
  connection_status: string;
  last_sync_at: string | null;
  total_documents_created: number;
}): EmailConfigListItem {
  return {
    id: cfg.id,
    name: cfg.name,
    imapServer: cfg.imap_server,
    imapFolder: cfg.imap_folder,
    isActive: cfg.is_active,
    connectionStatus: cfg.connection_status as EmailConfigListItem['connectionStatus'],
    lastSyncAt: cfg.last_sync_at,
    totalDocumentsCreated: cfg.total_documents_created,
  };
}

function transformFolderConfig(cfg: FolderConfigBackend): FolderConfigResponse {
  return {
    id: cfg.id,
    name: cfg.name,
    watchPath: cfg.watch_path,
    isNetworkPath: cfg.is_network_path,
    recursive: cfg.recursive,
    includePatterns: cfg.include_patterns ?? [],
    excludePatterns: cfg.exclude_patterns ?? [],
    moveAfterProcessing: cfg.move_after_processing,
    processedSubfolder: cfg.processed_subfolder,
    errorSubfolder: cfg.error_subfolder,
    deleteAfterProcessing: cfg.delete_after_processing,
    autoClassify: cfg.auto_classify,
    autoOcr: cfg.auto_ocr,
    defaultFolderId: cfg.default_folder_id,
    preserveFilename: cfg.preserve_filename,
    pollIntervalSeconds: cfg.poll_interval_seconds,
    companyId: cfg.company_id,
    isActive: cfg.is_active,
    watcherStatus: cfg.watcher_status,
    lastPollAt: cfg.last_poll_at,
    filesProcessedToday: cfg.files_processed_today,
    totalFilesProcessed: cfg.total_files_processed,
    totalDocumentsCreated: cfg.total_documents_created,
    lastError: cfg.last_error,
    createdAt: cfg.created_at,
    updatedAt: cfg.updated_at,
  };
}

function transformFolderConfigListItem(cfg: {
  id: string;
  name: string;
  watch_path: string;
  is_active: boolean;
  watcher_status: string;
  last_poll_at: string | null;
  total_documents_created: number;
}): FolderConfigListItem {
  return {
    id: cfg.id,
    name: cfg.name,
    watchPath: cfg.watch_path,
    isActive: cfg.is_active,
    watcherStatus: cfg.watcher_status as FolderConfigListItem['watcherStatus'],
    lastPollAt: cfg.last_poll_at,
    totalDocumentsCreated: cfg.total_documents_created,
  };
}

function transformImportRule(rule: ImportRuleBackend): ImportRuleResponse {
  return {
    id: rule.id,
    name: rule.name,
    description: rule.description,
    priority: rule.priority,
    appliesToEmailConfigs: rule.applies_to_email_configs ?? [],
    appliesToFolderConfigs: rule.applies_to_folder_configs ?? [],
    appliesToAll: rule.applies_to_all,
    conditions: rule.conditions,
    actions: rule.actions,
    isActive: rule.is_active,
    matchCount: rule.match_count,
    lastMatchedAt: rule.last_matched_at,
    createdAt: rule.created_at,
    updatedAt: rule.updated_at,
  };
}

function transformImportRuleListItem(rule: {
  id: string;
  name: string;
  priority: number;
  is_active: boolean;
  match_count: number;
  last_matched_at: string | null;
  applies_to_all: boolean;
}): ImportRuleListItem {
  return {
    id: rule.id,
    name: rule.name,
    priority: rule.priority,
    isActive: rule.is_active,
    matchCount: rule.match_count,
    lastMatchedAt: rule.last_matched_at,
    appliesToAll: rule.applies_to_all,
  };
}

function transformImportLog(log: ImportLogBackend): ImportLogResponse {
  return {
    id: log.id,
    userId: log.user_id,
    sourceType: log.source_type,
    emailConfigId: log.email_config_id,
    folderConfigId: log.folder_config_id,
    batchId: log.batch_id,
    emailFrom: log.email_from,
    emailSubject: log.email_subject,
    emailDate: log.email_date,
    originalPath: log.original_path,
    originalFilename: log.original_filename,
    status: log.status,
    documentId: log.document_id,
    fileHash: log.file_hash,
    fileSize: log.file_size,
    mimeType: log.mime_type,
    matchedRuleId: log.matched_rule_id,
    appliedActions: log.applied_actions,
    errorMessage: log.error_message,
    errorCode: log.error_code,
    retryCount: log.retry_count,
    startedAt: log.started_at,
    completedAt: log.completed_at,
    processingDurationMs: log.processing_duration_ms,
  };
}

function transformImportStats(stats: ImportStatsBackend): ImportStatsResponse {
  return {
    totalImports: stats.total_imports,
    successfulImports: stats.successful_imports,
    failedImports: stats.failed_imports,
    skippedImports: stats.skipped_imports,
    documentsCreated: stats.documents_created,
    avgProcessingTimeMs: stats.avg_processing_time_ms,
    importsBySource: stats.imports_by_source,
    importsByDay: stats.imports_by_day,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new ImportApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 409) {
      throw new ImportApiError(`${context}: ${message}`, 409, error);
    }

    if (statusCode === 400) {
      throw new ImportApiError(`${context}: ${message}`, 400, error);
    }

    throw new ImportApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new ImportApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Email Config Service ====================

export const emailConfigService = {
  /**
   * Listet alle Email-Konfigurationen
   */
  listConfigs: async (): Promise<EmailConfigListItem[]> => {
    try {
      const response = await apiClient.get<Array<{
        id: string;
        name: string;
        imap_server: string;
        imap_folder: string;
        is_active: boolean;
        connection_status: string;
        last_sync_at: string | null;
        total_documents_created: number;
      }>>('/imports/email/configs');

      return response.data.map(transformEmailConfigListItem);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Email-Konfigurationen laden');
    }
  },

  /**
   * Ruft eine einzelne Email-Konfiguration ab
   */
  getConfig: async (configId: string): Promise<EmailConfigResponse> => {
    try {
      const response = await apiClient.get<EmailConfigBackend>(
        `/imports/email/configs/${configId}`
      );

      return transformEmailConfig(response.data);
    } catch (error) {
      handleApiError(error, 'Email-Konfiguration laden');
    }
  },

  /**
   * Erstellt eine neue Email-Konfiguration
   */
  createConfig: async (data: EmailConfigCreate): Promise<{ id: string }> => {
    try {
      const response = await apiClient.post<{ id: string; message: string }>(
        '/imports/email/configs',
        {
          name: data.name,
          imap_server: data.imapServer,
          imap_port: data.imapPort ?? 993,
          username: data.username,
          password: data.password,
          use_ssl: data.useSsl ?? true,
          use_starttls: data.useStarttls ?? false,
          imap_folder: data.imapFolder ?? 'INBOX',
          processed_folder: data.processedFolder,
          error_folder: data.errorFolder,
          sync_interval_minutes: data.syncIntervalMinutes ?? 15,
          filter_from_addresses: data.filterFromAddresses,
          filter_subject_patterns: data.filterSubjectPatterns,
          filter_attachment_types: data.filterAttachmentTypes,
          extract_attachments_only: data.extractAttachmentsOnly ?? true,
          include_email_body_as_document: data.includeEmailBodyAsDocument ?? false,
          auto_classify: data.autoClassify ?? true,
          auto_ocr: data.autoOcr ?? true,
          default_folder_id: data.defaultFolderId,
          company_id: data.companyId,
        }
      );

      return { id: response.data.id };
    } catch (error) {
      handleApiError(error, 'Email-Konfiguration erstellen');
    }
  },

  /**
   * Aktualisiert eine Email-Konfiguration
   */
  updateConfig: async (
    configId: string,
    data: EmailConfigUpdate
  ): Promise<EmailConfigResponse> => {
    try {
      const payload: Record<string, unknown> = {};

      if (data.name !== undefined) payload.name = data.name;
      if (data.imapServer !== undefined) payload.imap_server = data.imapServer;
      if (data.imapPort !== undefined) payload.imap_port = data.imapPort;
      if (data.username !== undefined) payload.username = data.username;
      if (data.password !== undefined) payload.password = data.password;
      if (data.useSsl !== undefined) payload.use_ssl = data.useSsl;
      if (data.useStarttls !== undefined) payload.use_starttls = data.useStarttls;
      if (data.imapFolder !== undefined) payload.imap_folder = data.imapFolder;
      if (data.processedFolder !== undefined) payload.processed_folder = data.processedFolder;
      if (data.errorFolder !== undefined) payload.error_folder = data.errorFolder;
      if (data.syncIntervalMinutes !== undefined) payload.sync_interval_minutes = data.syncIntervalMinutes;
      if (data.filterFromAddresses !== undefined) payload.filter_from_addresses = data.filterFromAddresses;
      if (data.filterSubjectPatterns !== undefined) payload.filter_subject_patterns = data.filterSubjectPatterns;
      if (data.filterAttachmentTypes !== undefined) payload.filter_attachment_types = data.filterAttachmentTypes;
      if (data.extractAttachmentsOnly !== undefined) payload.extract_attachments_only = data.extractAttachmentsOnly;
      if (data.includeEmailBodyAsDocument !== undefined) payload.include_email_body_as_document = data.includeEmailBodyAsDocument;
      if (data.autoClassify !== undefined) payload.auto_classify = data.autoClassify;
      if (data.autoOcr !== undefined) payload.auto_ocr = data.autoOcr;
      if (data.defaultFolderId !== undefined) payload.default_folder_id = data.defaultFolderId;
      if (data.isActive !== undefined) payload.is_active = data.isActive;

      const response = await apiClient.patch<EmailConfigBackend>(
        `/imports/email/configs/${configId}`,
        payload
      );

      return transformEmailConfig(response.data);
    } catch (error) {
      handleApiError(error, 'Email-Konfiguration aktualisieren');
    }
  },

  /**
   * Loescht eine Email-Konfiguration
   */
  deleteConfig: async (configId: string): Promise<void> => {
    try {
      await apiClient.delete(`/imports/email/configs/${configId}`);
    } catch (error) {
      handleApiError(error, 'Email-Konfiguration loeschen');
    }
  },

  /**
   * Testet die Verbindung einer Email-Konfiguration
   */
  testConnection: async (configId: string): Promise<{ success: boolean; message: string }> => {
    try {
      const response = await apiClient.post<{ success: boolean; message: string }>(
        `/imports/email/configs/${configId}/test`
      );

      return response.data;
    } catch (error) {
      handleApiError(error, 'Verbindungstest');
    }
  },

  /**
   * Startet manuellen Sync
   */
  triggerSync: async (configId: string): Promise<{ task_id: string }> => {
    try {
      const response = await apiClient.post<{ task_id: string; message: string }>(
        `/imports/email/configs/${configId}/sync`
      );

      return { task_id: response.data.task_id };
    } catch (error) {
      handleApiError(error, 'Sync starten');
    }
  },
};

// ==================== Folder Config Service ====================

export const folderConfigService = {
  /**
   * Listet alle Folder-Konfigurationen
   */
  listConfigs: async (): Promise<FolderConfigListItem[]> => {
    try {
      const response = await apiClient.get<Array<{
        id: string;
        name: string;
        watch_path: string;
        is_active: boolean;
        watcher_status: string;
        last_poll_at: string | null;
        total_documents_created: number;
      }>>('/imports/folder/configs');

      return response.data.map(transformFolderConfigListItem);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Folder-Konfigurationen laden');
    }
  },

  /**
   * Ruft eine einzelne Folder-Konfiguration ab
   */
  getConfig: async (configId: string): Promise<FolderConfigResponse> => {
    try {
      const response = await apiClient.get<FolderConfigBackend>(
        `/imports/folder/configs/${configId}`
      );

      return transformFolderConfig(response.data);
    } catch (error) {
      handleApiError(error, 'Folder-Konfiguration laden');
    }
  },

  /**
   * Erstellt eine neue Folder-Konfiguration
   */
  createConfig: async (data: FolderConfigCreate): Promise<{ id: string }> => {
    try {
      const response = await apiClient.post<{ id: string; message: string }>(
        '/imports/folder/configs',
        {
          name: data.name,
          watch_path: data.watchPath,
          is_network_path: data.isNetworkPath ?? false,
          network_credentials: data.networkCredentials,
          recursive: data.recursive ?? false,
          include_patterns: data.includePatterns,
          exclude_patterns: data.excludePatterns,
          move_after_processing: data.moveAfterProcessing ?? true,
          processed_subfolder: data.processedSubfolder ?? 'processed',
          error_subfolder: data.errorSubfolder ?? 'error',
          delete_after_processing: data.deleteAfterProcessing ?? false,
          auto_classify: data.autoClassify ?? true,
          auto_ocr: data.autoOcr ?? true,
          default_folder_id: data.defaultFolderId,
          preserve_filename: data.preserveFilename ?? true,
          poll_interval_seconds: data.pollIntervalSeconds ?? 60,
          company_id: data.companyId,
        }
      );

      return { id: response.data.id };
    } catch (error) {
      handleApiError(error, 'Folder-Konfiguration erstellen');
    }
  },

  /**
   * Aktualisiert eine Folder-Konfiguration
   */
  updateConfig: async (
    configId: string,
    data: FolderConfigUpdate
  ): Promise<FolderConfigResponse> => {
    try {
      const payload: Record<string, unknown> = {};

      if (data.name !== undefined) payload.name = data.name;
      if (data.watchPath !== undefined) payload.watch_path = data.watchPath;
      if (data.isNetworkPath !== undefined) payload.is_network_path = data.isNetworkPath;
      if (data.networkCredentials !== undefined) payload.network_credentials = data.networkCredentials;
      if (data.recursive !== undefined) payload.recursive = data.recursive;
      if (data.includePatterns !== undefined) payload.include_patterns = data.includePatterns;
      if (data.excludePatterns !== undefined) payload.exclude_patterns = data.excludePatterns;
      if (data.moveAfterProcessing !== undefined) payload.move_after_processing = data.moveAfterProcessing;
      if (data.processedSubfolder !== undefined) payload.processed_subfolder = data.processedSubfolder;
      if (data.errorSubfolder !== undefined) payload.error_subfolder = data.errorSubfolder;
      if (data.deleteAfterProcessing !== undefined) payload.delete_after_processing = data.deleteAfterProcessing;
      if (data.autoClassify !== undefined) payload.auto_classify = data.autoClassify;
      if (data.autoOcr !== undefined) payload.auto_ocr = data.autoOcr;
      if (data.defaultFolderId !== undefined) payload.default_folder_id = data.defaultFolderId;
      if (data.preserveFilename !== undefined) payload.preserve_filename = data.preserveFilename;
      if (data.pollIntervalSeconds !== undefined) payload.poll_interval_seconds = data.pollIntervalSeconds;
      if (data.isActive !== undefined) payload.is_active = data.isActive;

      const response = await apiClient.patch<FolderConfigBackend>(
        `/imports/folder/configs/${configId}`,
        payload
      );

      return transformFolderConfig(response.data);
    } catch (error) {
      handleApiError(error, 'Folder-Konfiguration aktualisieren');
    }
  },

  /**
   * Loescht eine Folder-Konfiguration
   */
  deleteConfig: async (configId: string): Promise<void> => {
    try {
      await apiClient.delete(`/imports/folder/configs/${configId}`);
    } catch (error) {
      handleApiError(error, 'Folder-Konfiguration loeschen');
    }
  },

  /**
   * Startet den Folder-Watcher
   */
  startWatcher: async (configId: string): Promise<void> => {
    try {
      await apiClient.post(`/imports/folder/configs/${configId}/start`);
    } catch (error) {
      handleApiError(error, 'Watcher starten');
    }
  },

  /**
   * Stoppt den Folder-Watcher
   */
  stopWatcher: async (configId: string): Promise<void> => {
    try {
      await apiClient.post(`/imports/folder/configs/${configId}/stop`);
    } catch (error) {
      handleApiError(error, 'Watcher stoppen');
    }
  },

  /**
   * Triggert manuellen Poll
   */
  triggerPoll: async (configId: string): Promise<{ task_id: string }> => {
    try {
      const response = await apiClient.post<{ task_id: string; message: string }>(
        `/imports/folder/configs/${configId}/poll`
      );

      return { task_id: response.data.task_id };
    } catch (error) {
      handleApiError(error, 'Poll starten');
    }
  },
};

// ==================== Import Rules Service ====================

export const importRulesService = {
  /**
   * Listet alle Import-Regeln
   */
  listRules: async (): Promise<ImportRuleListItem[]> => {
    try {
      const response = await apiClient.get<Array<{
        id: string;
        name: string;
        priority: number;
        is_active: boolean;
        match_count: number;
        last_matched_at: string | null;
        applies_to_all: boolean;
      }>>('/imports/rules');

      return response.data.map(transformImportRuleListItem);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Import-Regeln laden');
    }
  },

  /**
   * Ruft eine einzelne Regel ab
   */
  getRule: async (ruleId: string): Promise<ImportRuleResponse> => {
    try {
      const response = await apiClient.get<ImportRuleBackend>(
        `/imports/rules/${ruleId}`
      );

      return transformImportRule(response.data);
    } catch (error) {
      handleApiError(error, 'Import-Regel laden');
    }
  },

  /**
   * Erstellt eine neue Regel
   */
  createRule: async (data: ImportRuleCreate): Promise<{ id: string }> => {
    try {
      const response = await apiClient.post<{ id: string; message: string }>(
        '/imports/rules',
        {
          name: data.name,
          description: data.description,
          priority: data.priority ?? 100,
          conditions: data.conditions ?? { operator: 'AND', rules: [] },
          actions: data.actions ?? {},
          applies_to_email_configs: data.appliesToEmailConfigs,
          applies_to_folder_configs: data.appliesToFolderConfigs,
          applies_to_all: data.appliesToAll ?? false,
          is_active: data.isActive ?? true,
        }
      );

      return { id: response.data.id };
    } catch (error) {
      handleApiError(error, 'Import-Regel erstellen');
    }
  },

  /**
   * Aktualisiert eine Regel
   */
  updateRule: async (
    ruleId: string,
    data: ImportRuleUpdate
  ): Promise<ImportRuleResponse> => {
    try {
      const payload: Record<string, unknown> = {};

      if (data.name !== undefined) payload.name = data.name;
      if (data.description !== undefined) payload.description = data.description;
      if (data.priority !== undefined) payload.priority = data.priority;
      if (data.conditions !== undefined) payload.conditions = data.conditions;
      if (data.actions !== undefined) payload.actions = data.actions;
      if (data.appliesToEmailConfigs !== undefined) payload.applies_to_email_configs = data.appliesToEmailConfigs;
      if (data.appliesToFolderConfigs !== undefined) payload.applies_to_folder_configs = data.appliesToFolderConfigs;
      if (data.appliesToAll !== undefined) payload.applies_to_all = data.appliesToAll;
      if (data.isActive !== undefined) payload.is_active = data.isActive;

      const response = await apiClient.patch<ImportRuleBackend>(
        `/imports/rules/${ruleId}`,
        payload
      );

      return transformImportRule(response.data);
    } catch (error) {
      handleApiError(error, 'Import-Regel aktualisieren');
    }
  },

  /**
   * Loescht eine Regel
   */
  deleteRule: async (ruleId: string): Promise<void> => {
    try {
      await apiClient.delete(`/imports/rules/${ruleId}`);
    } catch (error) {
      handleApiError(error, 'Import-Regel loeschen');
    }
  },

  /**
   * Ordnet Regeln neu (Prioritaeten)
   */
  reorderRules: async (
    priorities: Array<{ ruleId: string; priority: number }>
  ): Promise<void> => {
    try {
      await apiClient.post('/imports/rules/reorder', {
        priorities: priorities.map((p) => ({
          rule_id: p.ruleId,
          priority: p.priority,
        })),
      });
    } catch (error) {
      handleApiError(error, 'Regeln neu ordnen');
    }
  },

  /**
   * Testet eine Regel gegen Metadata
   */
  testRule: async (
    ruleId: string,
    metadata: Record<string, unknown>,
    sourceType: 'email' | 'folder' = 'email'
  ): Promise<{ matches: boolean; actions: RuleActions | null }> => {
    try {
      const response = await apiClient.post<{
        matches: boolean;
        actions: RuleActions | null;
      }>(`/imports/rules/${ruleId}/test`, {
        metadata,
        source_type: sourceType,
      });

      return response.data;
    } catch (error) {
      handleApiError(error, 'Regel testen');
    }
  },

  /**
   * Testet alle Regeln gegen Metadata
   */
  testAllRules: async (
    metadata: Record<string, unknown>,
    sourceType: 'email' | 'folder' = 'email'
  ): Promise<Array<{ ruleId: string; ruleName: string; matches: boolean; actions: RuleActions | null }>> => {
    try {
      const response = await apiClient.post<Array<{
        rule_id: string;
        rule_name: string;
        matches: boolean;
        actions: RuleActions | null;
      }>>('/imports/rules/test-all', {
        metadata,
        source_type: sourceType,
      });

      return response.data.map((r) => ({
        ruleId: r.rule_id,
        ruleName: r.rule_name,
        matches: r.matches,
        actions: r.actions,
      }));
    } catch (error) {
      handleApiError(error, 'Alle Regeln testen');
    }
  },

  /**
   * Ruft verfuegbare Felder fuer Regeln ab
   */
  getFields: async (): Promise<RuleFieldSchema[]> => {
    try {
      const response = await apiClient.get<RuleFieldSchema[]>(
        '/imports/rules/schema/fields'
      );

      return response.data;
    } catch (error) {
      handleApiError(error, 'Regel-Felder laden');
    }
  },

  /**
   * Ruft verfuegbare Operatoren fuer Regeln ab
   */
  getOperators: async (): Promise<RuleOperatorSchema[]> => {
    try {
      const response = await apiClient.get<RuleOperatorSchema[]>(
        '/imports/rules/schema/operators'
      );

      return response.data;
    } catch (error) {
      handleApiError(error, 'Regel-Operatoren laden');
    }
  },

  /**
   * Ruft verfuegbare Actions fuer Regeln ab
   */
  getActions: async (): Promise<RuleActionSchema[]> => {
    try {
      const response = await apiClient.get<RuleActionSchema[]>(
        '/imports/rules/schema/actions'
      );

      return response.data;
    } catch (error) {
      handleApiError(error, 'Regel-Actions laden');
    }
  },
};

// ==================== Import Logs Service ====================

export const importLogsService = {
  /**
   * Listet Import-Logs mit Filter
   */
  listLogs: async (filter: ImportLogFilter = {}): Promise<ImportLogResponse[]> => {
    try {
      const params: Record<string, string | number> = {
        page: filter.page ?? 1,
        per_page: filter.perPage ?? 50,
      };

      if (filter.sourceType) params.source_type = filter.sourceType;
      if (filter.status) params.status = filter.status;
      if (filter.emailConfigId) params.email_config_id = filter.emailConfigId;
      if (filter.folderConfigId) params.folder_config_id = filter.folderConfigId;
      if (filter.dateFrom) params.date_from = filter.dateFrom;
      if (filter.dateTo) params.date_to = filter.dateTo;

      const response = await apiClient.get<ImportLogBackend[]>(
        '/imports/logs',
        { params }
      );

      return response.data.map(transformImportLog);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Import-Logs laden');
    }
  },

  /**
   * Ruft ein einzelnes Log ab
   */
  getLog: async (logId: string): Promise<ImportLogResponse> => {
    try {
      const response = await apiClient.get<ImportLogBackend>(
        `/imports/logs/${logId}`
      );

      return transformImportLog(response.data);
    } catch (error) {
      handleApiError(error, 'Import-Log laden');
    }
  },

  /**
   * Wiederholt einen fehlgeschlagenen Import
   */
  retryImport: async (logId: string): Promise<{ task_id: string }> => {
    try {
      const response = await apiClient.post<{ task_id: string; message: string }>(
        `/imports/logs/${logId}/retry`
      );

      return { task_id: response.data.task_id };
    } catch (error) {
      handleApiError(error, 'Import wiederholen');
    }
  },

  /**
   * Ruft Import-Statistiken ab
   */
  getStats: async (
    dateFrom?: string,
    dateTo?: string
  ): Promise<ImportStatsResponse> => {
    try {
      const params: Record<string, string> = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const response = await apiClient.get<ImportStatsBackend>(
        '/imports/logs/stats',
        { params }
      );

      return transformImportStats(response.data);
    } catch (error) {
      handleApiError(error, 'Import-Statistiken laden');
    }
  },
};
