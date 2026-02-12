/**
 * Import System TypeScript Types
 *
 * Type-Definitionen für E-Mail-Import, Ordner-Import und Import-Regeln.
 */

// =============================================================================
// Email Import Types
// =============================================================================

export interface EmailImportConfig {
  id: string;
  company_id?: string;
  user_id: string;
  name: string;
  imap_server: string;
  imap_port: number;
  username: string;
  use_ssl: boolean;
  use_starttls: boolean;
  folder_to_watch: string;
  processed_folder?: string;
  error_folder?: string;
  is_active: boolean;
  sync_interval_minutes: number;
  last_sync_at?: string;
  last_sync_status?: 'success' | 'error' | 'partial';
  last_sync_error?: string;
  filter_sender?: string;
  filter_subject_pattern?: string;
  filter_has_attachment: boolean;
  allowed_attachment_types?: string[];
  max_attachment_size_mb?: number;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  process_inline_images: boolean;
  skip_read_emails: boolean;
  mark_as_read_after_processing: boolean;
  delete_after_processing: boolean;
  enable_ocr: boolean;
  ocr_backend?: string;
  total_emails_processed: number;
  total_attachments_imported: number;
  total_errors: number;
  created_at: string;
  updated_at: string;
}

export interface EmailImportConfigCreate {
  company_id?: string;
  name: string;
  imap_server: string;
  imap_port?: number;
  username: string;
  password: string;
  use_ssl?: boolean;
  use_starttls?: boolean;
  folder_to_watch?: string;
  processed_folder?: string;
  error_folder?: string;
  sync_interval_minutes?: number;
  filter_sender?: string;
  filter_subject_pattern?: string;
  filter_has_attachment?: boolean;
  allowed_attachment_types?: string[];
  max_attachment_size_mb?: number;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  process_inline_images?: boolean;
  skip_read_emails?: boolean;
  mark_as_read_after_processing?: boolean;
  delete_after_processing?: boolean;
  enable_ocr?: boolean;
  ocr_backend?: string;
}

export interface EmailImportConfigUpdate {
  name?: string;
  imap_server?: string;
  imap_port?: number;
  username?: string;
  password?: string;
  use_ssl?: boolean;
  use_starttls?: boolean;
  folder_to_watch?: string;
  processed_folder?: string;
  error_folder?: string;
  is_active?: boolean;
  sync_interval_minutes?: number;
  filter_sender?: string;
  filter_subject_pattern?: string;
  filter_has_attachment?: boolean;
  allowed_attachment_types?: string[];
  max_attachment_size_mb?: number;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  process_inline_images?: boolean;
  skip_read_emails?: boolean;
  mark_as_read_after_processing?: boolean;
  delete_after_processing?: boolean;
  enable_ocr?: boolean;
  ocr_backend?: string;
}

export interface EmailConnectionTestResult {
  success: boolean;
  server: string;
  folders?: string[];
  message_count?: number;
  error?: string;
}

export interface EmailSyncResult {
  success: boolean;
  task_id: string;
  message: string;
}

// =============================================================================
// Folder Import Types
// =============================================================================

export interface FolderImportConfig {
  id: string;
  company_id?: string;
  user_id: string;
  name: string;
  watch_path: string;
  is_network_path: boolean;
  is_active: boolean;
  is_watcher_running: boolean;
  use_polling: boolean;
  poll_interval_seconds: number;
  last_poll_at?: string;
  last_poll_status?: 'success' | 'error' | 'partial';
  last_poll_error?: string;
  include_patterns?: string[];
  exclude_patterns?: string[];
  recursive: boolean;
  min_file_age_seconds: number;
  process_existing_files: boolean;
  move_to_folder?: string;
  delete_after_processing: boolean;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  enable_ocr: boolean;
  ocr_backend?: string;
  total_files_processed: number;
  total_files_today: number;
  total_errors: number;
  daily_limit?: number;
  created_at: string;
  updated_at: string;
}

export interface FolderImportConfigCreate {
  company_id?: string;
  name: string;
  watch_path: string;
  is_network_path?: boolean;
  use_polling?: boolean;
  poll_interval_seconds?: number;
  include_patterns?: string[];
  exclude_patterns?: string[];
  recursive?: boolean;
  min_file_age_seconds?: number;
  process_existing_files?: boolean;
  move_to_folder?: string;
  delete_after_processing?: boolean;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  enable_ocr?: boolean;
  ocr_backend?: string;
  daily_limit?: number;
}

export interface FolderImportConfigUpdate {
  name?: string;
  watch_path?: string;
  is_network_path?: boolean;
  is_active?: boolean;
  use_polling?: boolean;
  poll_interval_seconds?: number;
  include_patterns?: string[];
  exclude_patterns?: string[];
  recursive?: boolean;
  min_file_age_seconds?: number;
  process_existing_files?: boolean;
  move_to_folder?: string;
  delete_after_processing?: boolean;
  target_folder_id?: string;
  auto_tag_ids?: string[];
  enable_ocr?: boolean;
  ocr_backend?: string;
  daily_limit?: number;
}

export interface FolderWatcherStatusResult {
  success: boolean;
  is_running: boolean;
  message: string;
}

export interface FolderPollResult {
  success: boolean;
  task_id: string;
  message: string;
}

// =============================================================================
// Import Rules Types
// =============================================================================

export type ImportRuleOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'regex'
  | 'gt'
  | 'lt'
  | 'gte'
  | 'lte'
  | 'in_list'
  | 'not_in_list'
  | 'is_empty'
  | 'is_not_empty';

export type ImportRuleLogic = 'AND' | 'OR';

export interface ImportRuleCondition {
  field: string;
  operator: ImportRuleOperator;
  value: string | number | boolean | string[];
  case_sensitive?: boolean;
}

export type ImportRuleActionType =
  | 'assign_folder'
  | 'assign_tags'
  | 'set_priority'
  | 'enable_ocr'
  | 'disable_ocr'
  | 'set_ocr_backend'
  | 'skip_processing'
  | 'send_notification'
  | 'add_metadata';

export interface ImportRuleAction {
  action: ImportRuleActionType;
  value: string | number | boolean | string[] | Record<string, unknown>;
}

export interface ImportRule {
  id: string;
  company_id?: string;
  user_id: string;
  name: string;
  description?: string;
  is_active: boolean;
  priority: number;
  source_type?: 'email' | 'folder' | 'all';
  logic: ImportRuleLogic;
  conditions: ImportRuleCondition[];
  actions: ImportRuleAction[];
  stop_processing_on_match: boolean;
  times_matched: number;
  last_matched_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ImportRuleCreate {
  company_id?: string;
  name: string;
  description?: string;
  priority?: number;
  source_type?: 'email' | 'folder' | 'all';
  logic?: ImportRuleLogic;
  conditions: ImportRuleCondition[];
  actions: ImportRuleAction[];
  stop_processing_on_match?: boolean;
}

export interface ImportRuleUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
  priority?: number;
  source_type?: 'email' | 'folder' | 'all';
  logic?: ImportRuleLogic;
  conditions?: ImportRuleCondition[];
  actions?: ImportRuleAction[];
  stop_processing_on_match?: boolean;
}

export interface ImportRuleReorderItem {
  id: string;
  priority: number;
}

export interface RuleTestRequest {
  metadata: Record<string, unknown>;
  rule_id?: string;
}

export interface RuleTestResult {
  matched: boolean;
  rule_id?: string;
  rule_name?: string;
  matched_conditions?: string[];
  applied_actions?: ImportRuleAction[];
}

export interface RuleTestAllResult {
  tested_rules: number;
  matched_rules: RuleTestResult[];
}

// =============================================================================
// Import Log Types
// =============================================================================

export type ImportLogStatus =
  | 'pending'
  | 'processing'
  | 'success'
  | 'error'
  | 'skipped'
  | 'duplicate';

export type ImportLogSourceType = 'email' | 'folder' | 'manual' | 'api';

export interface ImportLog {
  id: string;
  company_id?: string;
  user_id?: string;
  source_type: ImportLogSourceType;
  source_config_id?: string;
  source_details: Record<string, unknown>;
  file_name?: string;
  file_size_bytes?: number;
  file_hash?: string;
  mime_type?: string;
  status: ImportLogStatus;
  document_id?: string;
  error_message?: string;
  error_details?: Record<string, unknown>;
  processing_started_at?: string;
  processing_completed_at?: string;
  processing_duration_ms?: number;
  rules_evaluated: number;
  rules_matched: number;
  applied_rule_ids?: string[];
  retry_count: number;
  max_retries: number;
  next_retry_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ImportLogFilters {
  source_type?: ImportLogSourceType;
  status?: ImportLogStatus;
  source_config_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface ImportLogRetryResult {
  success: boolean;
  task_id?: string;
  message: string;
}

export interface ImportLogStats {
  total_imports: number;
  successful_imports: number;
  failed_imports: number;
  pending_imports: number;
  imports_today: number;
  imports_this_week: number;
  imports_this_month: number;
  by_source_type: Record<ImportLogSourceType, number>;
  by_status: Record<ImportLogStatus, number>;
  average_processing_time_ms?: number;
}

// =============================================================================
// Paginated Response Type
// =============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
