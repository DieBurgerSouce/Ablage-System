/**
 * Import Types
 *
 * TypeScript Typen für Email- und Folder-Import-Feature.
 */

// ==================== Enums ====================

export type ConnectionStatus = 'connected' | 'disconnected' | 'error' | 'unknown';
export type WatcherStatus = 'running' | 'stopped' | 'error' | 'unknown';
export type ImportStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'skipped' | 'duplicate';
export type SourceType = 'email' | 'folder';
export type RuleOperator = 'AND' | 'OR';

// ==================== Email Config Types ====================

export interface EmailConfigBackend {
  id: string;
  name: string;
  imap_server: string;
  imap_port: number;
  use_ssl: boolean;
  use_starttls: boolean;
  imap_folder: string;
  processed_folder: string | null;
  error_folder: string | null;
  sync_interval_minutes: number;
  filter_from_addresses: string[];
  filter_subject_patterns: string[];
  filter_attachment_types: string[];
  extract_attachments_only: boolean;
  include_email_body_as_document: boolean;
  auto_classify: boolean;
  auto_ocr: boolean;
  default_folder_id: string | null;
  company_id: string | null;
  is_active: boolean;
  connection_status: ConnectionStatus;
  last_sync_at: string | null;
  total_emails_processed: number;
  total_documents_created: number;
  last_error: string | null;
  error_count: number;
  created_at: string;
  updated_at: string;
}

export interface EmailConfigResponse {
  id: string;
  name: string;
  imapServer: string;
  imapPort: number;
  useSsl: boolean;
  useStarttls: boolean;
  imapFolder: string;
  processedFolder: string | null;
  errorFolder: string | null;
  syncIntervalMinutes: number;
  filterFromAddresses: string[];
  filterSubjectPatterns: string[];
  filterAttachmentTypes: string[];
  extractAttachmentsOnly: boolean;
  includeEmailBodyAsDocument: boolean;
  autoClassify: boolean;
  autoOcr: boolean;
  defaultFolderId: string | null;
  companyId: string | null;
  isActive: boolean;
  connectionStatus: ConnectionStatus;
  lastSyncAt: string | null;
  totalEmailsProcessed: number;
  totalDocumentsCreated: number;
  lastError: string | null;
  errorCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface EmailConfigListItem {
  id: string;
  name: string;
  imapServer: string;
  imapFolder: string;
  isActive: boolean;
  connectionStatus: ConnectionStatus;
  lastSyncAt: string | null;
  totalDocumentsCreated: number;
}

export interface EmailConfigCreate {
  name: string;
  imapServer: string;
  imapPort?: number;
  username: string;
  password: string;
  useSsl?: boolean;
  useStarttls?: boolean;
  imapFolder?: string;
  processedFolder?: string | null;
  errorFolder?: string | null;
  syncIntervalMinutes?: number;
  filterFromAddresses?: string[];
  filterSubjectPatterns?: string[];
  filterAttachmentTypes?: string[];
  extractAttachmentsOnly?: boolean;
  includeEmailBodyAsDocument?: boolean;
  autoClassify?: boolean;
  autoOcr?: boolean;
  defaultFolderId?: string | null;
  companyId?: string | null;
}

export interface EmailConfigUpdate {
  name?: string;
  imapServer?: string;
  imapPort?: number;
  username?: string;
  password?: string;
  useSsl?: boolean;
  useStarttls?: boolean;
  imapFolder?: string;
  processedFolder?: string | null;
  errorFolder?: string | null;
  syncIntervalMinutes?: number;
  filterFromAddresses?: string[];
  filterSubjectPatterns?: string[];
  filterAttachmentTypes?: string[];
  extractAttachmentsOnly?: boolean;
  includeEmailBodyAsDocument?: boolean;
  autoClassify?: boolean;
  autoOcr?: boolean;
  defaultFolderId?: string | null;
  isActive?: boolean;
}

// ==================== Folder Config Types ====================

export interface FolderConfigBackend {
  id: string;
  name: string;
  watch_path: string;
  is_network_path: boolean;
  recursive: boolean;
  include_patterns: string[];
  exclude_patterns: string[];
  move_after_processing: boolean;
  processed_subfolder: string;
  error_subfolder: string;
  delete_after_processing: boolean;
  auto_classify: boolean;
  auto_ocr: boolean;
  default_folder_id: string | null;
  preserve_filename: boolean;
  poll_interval_seconds: number;
  company_id: string | null;
  is_active: boolean;
  watcher_status: WatcherStatus;
  last_poll_at: string | null;
  files_processed_today: number;
  total_files_processed: number;
  total_documents_created: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface FolderConfigResponse {
  id: string;
  name: string;
  watchPath: string;
  isNetworkPath: boolean;
  recursive: boolean;
  includePatterns: string[];
  excludePatterns: string[];
  moveAfterProcessing: boolean;
  processedSubfolder: string;
  errorSubfolder: string;
  deleteAfterProcessing: boolean;
  autoClassify: boolean;
  autoOcr: boolean;
  defaultFolderId: string | null;
  preserveFilename: boolean;
  pollIntervalSeconds: number;
  companyId: string | null;
  isActive: boolean;
  watcherStatus: WatcherStatus;
  lastPollAt: string | null;
  filesProcessedToday: number;
  totalFilesProcessed: number;
  totalDocumentsCreated: number;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface FolderConfigListItem {
  id: string;
  name: string;
  watchPath: string;
  isActive: boolean;
  watcherStatus: WatcherStatus;
  lastPollAt: string | null;
  totalDocumentsCreated: number;
}

export interface FolderConfigCreate {
  name: string;
  watchPath: string;
  isNetworkPath?: boolean;
  networkCredentials?: string | null;
  recursive?: boolean;
  includePatterns?: string[];
  excludePatterns?: string[];
  moveAfterProcessing?: boolean;
  processedSubfolder?: string;
  errorSubfolder?: string;
  deleteAfterProcessing?: boolean;
  autoClassify?: boolean;
  autoOcr?: boolean;
  defaultFolderId?: string | null;
  preserveFilename?: boolean;
  pollIntervalSeconds?: number;
  companyId?: string | null;
}

export interface FolderConfigUpdate {
  name?: string;
  watchPath?: string;
  isNetworkPath?: boolean;
  networkCredentials?: string | null;
  recursive?: boolean;
  includePatterns?: string[];
  excludePatterns?: string[];
  moveAfterProcessing?: boolean;
  processedSubfolder?: string;
  errorSubfolder?: string;
  deleteAfterProcessing?: boolean;
  autoClassify?: boolean;
  autoOcr?: boolean;
  defaultFolderId?: string | null;
  preserveFilename?: boolean;
  pollIntervalSeconds?: number;
  isActive?: boolean;
}

// ==================== Import Rule Types ====================

export interface RuleCondition {
  field: string;
  operator: string;
  value: string | null;
}

export interface RuleConditions {
  operator: RuleOperator;
  rules: RuleCondition[];
}

export interface RuleActions {
  setFolder?: string;
  setDocumentType?: string;
  addTags?: string[];
  setMetadata?: Record<string, string>;
  skipProcessing?: boolean;
  markAsUrgent?: boolean;
}

export interface ImportRuleBackend {
  id: string;
  name: string;
  description: string | null;
  priority: number;
  applies_to_email_configs: string[];
  applies_to_folder_configs: string[];
  applies_to_all: boolean;
  conditions: RuleConditions;
  actions: RuleActions;
  is_active: boolean;
  match_count: number;
  last_matched_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImportRuleResponse {
  id: string;
  name: string;
  description: string | null;
  priority: number;
  appliesToEmailConfigs: string[];
  appliesToFolderConfigs: string[];
  appliesToAll: boolean;
  conditions: RuleConditions;
  actions: RuleActions;
  isActive: boolean;
  matchCount: number;
  lastMatchedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ImportRuleListItem {
  id: string;
  name: string;
  priority: number;
  isActive: boolean;
  matchCount: number;
  lastMatchedAt: string | null;
  appliesToAll: boolean;
}

export interface ImportRuleCreate {
  name: string;
  description?: string | null;
  priority?: number;
  conditions?: RuleConditions;
  actions?: RuleActions;
  appliesToEmailConfigs?: string[];
  appliesToFolderConfigs?: string[];
  appliesToAll?: boolean;
  isActive?: boolean;
}

export interface ImportRuleUpdate {
  name?: string;
  description?: string | null;
  priority?: number;
  conditions?: RuleConditions;
  actions?: RuleActions;
  appliesToEmailConfigs?: string[];
  appliesToFolderConfigs?: string[];
  appliesToAll?: boolean;
  isActive?: boolean;
}

// ==================== Import Log Types ====================

export interface ImportLogBackend {
  id: string;
  user_id: string;
  source_type: SourceType;
  email_config_id: string | null;
  folder_config_id: string | null;
  batch_id: string;
  email_from: string | null;
  email_subject: string | null;
  email_date: string | null;
  original_path: string | null;
  original_filename: string | null;
  status: ImportStatus;
  document_id: string | null;
  file_hash: string | null;
  file_size: number | null;
  mime_type: string | null;
  matched_rule_id: string | null;
  applied_actions: Record<string, unknown>;
  error_message: string | null;
  error_code: string | null;
  retry_count: number;
  started_at: string;
  completed_at: string | null;
  processing_duration_ms: number | null;
}

export interface ImportLogResponse {
  id: string;
  userId: string;
  sourceType: SourceType;
  emailConfigId: string | null;
  folderConfigId: string | null;
  batchId: string;
  emailFrom: string | null;
  emailSubject: string | null;
  emailDate: string | null;
  originalPath: string | null;
  originalFilename: string | null;
  status: ImportStatus;
  documentId: string | null;
  fileHash: string | null;
  fileSize: number | null;
  mimeType: string | null;
  matchedRuleId: string | null;
  appliedActions: Record<string, unknown>;
  errorMessage: string | null;
  errorCode: string | null;
  retryCount: number;
  startedAt: string;
  completedAt: string | null;
  processingDurationMs: number | null;
}

// ==================== Import Run Types (F2 Live-Status) ====================

/** Ein Import-Lauf (alle Logs eines batch_id), wie vom Backend geliefert. */
export interface ImportRunBackend {
  batch_id: string;
  source_type: SourceType;
  config_id: string | null;
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  pending: number;
  documents_created: number;
  is_running: boolean;
  started_at: string;
  last_update: string | null;
}

/** Ein Import-Lauf (camelCase fuer das Frontend). */
export interface ImportRun {
  batchId: string;
  sourceType: SourceType;
  configId: string | null;
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  pending: number;
  documentsCreated: number;
  isRunning: boolean;
  startedAt: string;
  lastUpdate: string | null;
}

// ==================== Statistics Types ====================

export interface ImportStatsBackend {
  total_imports: number;
  successful_imports: number;
  failed_imports: number;
  skipped_imports: number;
  documents_created: number;
  avg_processing_time_ms: number;
  imports_by_source: Record<string, number>;
  imports_by_day: Array<{
    date: string;
    count: number;
    successful: number;
    failed: number;
  }>;
}

export interface ImportStatsResponse {
  totalImports: number;
  successfulImports: number;
  failedImports: number;
  skippedImports: number;
  documentsCreated: number;
  avgProcessingTimeMs: number;
  importsBySource: Record<string, number>;
  importsByDay: Array<{
    date: string;
    count: number;
    successful: number;
    failed: number;
  }>;
}

// ==================== Filter Types ====================

export interface ImportLogFilter {
  sourceType?: SourceType;
  status?: ImportStatus;
  emailConfigId?: string;
  folderConfigId?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  perPage?: number;
}

// ==================== Schema Types (für Rule Builder) ====================

export interface RuleFieldSchema {
  name: string;
  label: string;
  type: 'string' | 'number' | 'date' | 'boolean' | 'array';
  description?: string;
}

export interface RuleOperatorSchema {
  name: string;
  label: string;
  applicableTypes: Array<'string' | 'number' | 'date' | 'boolean' | 'array'>;
  needsValue: boolean;
}

export interface RuleActionSchema {
  name: string;
  label: string;
  type: 'folder' | 'document_type' | 'tags' | 'metadata' | 'boolean';
  description?: string;
}
