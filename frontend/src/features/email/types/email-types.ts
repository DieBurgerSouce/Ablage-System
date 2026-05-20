/**
 * TypeScript-Typen für den E-Mail-Import.
 */

export interface EmlAttachmentInfo {
  index: number;
  filename: string;
  size: number;
  mime_type: string;
  is_importable: boolean;
}

export interface EmlParseResponse {
  file_id: string;
  subject: string;
  sender: string;
  sender_name: string;
  date: string | null;
  body_preview: string;
  attachments: EmlAttachmentInfo[];
  message_id: string | null;
}

export interface EmlImportRequest {
  file_id: string;
  selected_attachment_indices: number[];
  target_folder_id?: string;
  auto_ocr: boolean;
  auto_classify: boolean;
}

export interface EmlImportResponse {
  imported_count: number;
  document_ids: string[];
  skipped: string[];
}

export interface EmailConfig {
  id: string;
  name: string;
  host: string;
  port: number;
  use_ssl: boolean;
  username: string;
  last_sync_at: string | null;
  is_active: boolean;
  sync_interval_minutes: number;
  folder_inbox: string;
  folder_processed: string;
  folder_error: string;
}

export interface ImportLog {
  id: string;
  config_name: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'completed' | 'failed';
  emails_processed: number;
  documents_created: number;
  errors: number;
  error_details: string[];
}

export interface ImportStats {
  today_emails: number;
  today_documents: number;
  today_errors: number;
  total_configs: number;
  active_configs: number;
  last_sync_at: string | null;
}

export interface RuleCondition {
  field: string;
  operator: string;
  value: string;
}

export interface RuleAction {
  type: string;
  value: string;
}

export interface ImportRule {
  id?: string;
  name: string;
  is_active: boolean;
  logic: 'AND' | 'OR';
  conditions: RuleCondition[];
  actions: RuleAction[];
  priority: number;
}
