/**
 * Document Template Types
 *
 * TypeScript types for document template management.
 */

// =============================================================================
// Enums
// =============================================================================

export enum TemplateCategory {
  INVOICE = 'invoice',
  OFFER = 'offer',
  CONTRACT = 'contract',
  LETTER = 'letter',
  REMINDER = 'reminder',
  DUNNING = 'dunning',
  CONFIRMATION = 'confirmation',
  REPORT = 'report',
  CERTIFICATE = 'certificate',
  OTHER = 'other',
}

export enum TemplateOutputFormat {
  PDF = 'pdf',
  DOCX = 'docx',
  HTML = 'html',
  MARKDOWN = 'markdown',
}

export enum VariableType {
  TEXT = 'text',
  NUMBER = 'number',
  CURRENCY = 'currency',
  DATE = 'date',
  DATETIME = 'datetime',
  BOOLEAN = 'boolean',
  SELECT = 'select',
  ENTITY = 'entity',
  DOCUMENT = 'document',
}

// =============================================================================
// Display Labels (German)
// =============================================================================

export const TEMPLATE_CATEGORY_LABELS: Record<TemplateCategory, string> = {
  [TemplateCategory.INVOICE]: 'Rechnung',
  [TemplateCategory.OFFER]: 'Angebot',
  [TemplateCategory.CONTRACT]: 'Vertrag',
  [TemplateCategory.LETTER]: 'Brief',
  [TemplateCategory.REMINDER]: 'Erinnerung',
  [TemplateCategory.DUNNING]: 'Mahnung',
  [TemplateCategory.CONFIRMATION]: 'Bestätigung',
  [TemplateCategory.REPORT]: 'Bericht',
  [TemplateCategory.CERTIFICATE]: 'Zertifikat',
  [TemplateCategory.OTHER]: 'Sonstiges',
};

export const OUTPUT_FORMAT_LABELS: Record<TemplateOutputFormat, string> = {
  [TemplateOutputFormat.PDF]: 'PDF',
  [TemplateOutputFormat.DOCX]: 'Word (DOCX)',
  [TemplateOutputFormat.HTML]: 'HTML',
  [TemplateOutputFormat.MARKDOWN]: 'Markdown',
};

export const VARIABLE_TYPE_LABELS: Record<VariableType, string> = {
  [VariableType.TEXT]: 'Text',
  [VariableType.NUMBER]: 'Zahl',
  [VariableType.CURRENCY]: 'Währung',
  [VariableType.DATE]: 'Datum',
  [VariableType.DATETIME]: 'Datum & Zeit',
  [VariableType.BOOLEAN]: 'Ja/Nein',
  [VariableType.SELECT]: 'Auswahl',
  [VariableType.ENTITY]: 'Geschäftspartner',
  [VariableType.DOCUMENT]: 'Dokument',
};

// =============================================================================
// Variable Schema
// =============================================================================

export interface TemplateVariable {
  name: string;
  type: VariableType;
  label: string;
  description?: string;
  required: boolean;
  default?: unknown;
  options?: string[];
  entity_type?: string;
}

// =============================================================================
// Template Entity Types
// =============================================================================

export interface Template {
  id: string;
  company_id: string;
  name: string;
  code: string;
  description?: string;
  category: TemplateCategory;
  content: string;
  header_content?: string;
  footer_content?: string;
  css_styles?: string;
  page_size: string;
  orientation: string;
  margins: {
    top: number;
    right: number;
    bottom: number;
    left: number;
  };
  output_format: TemplateOutputFormat;
  variables: TemplateVariable[];
  version: number;
  is_latest: boolean;
  is_active: boolean;
  is_default: boolean;
  usage_count: number;
  last_used_at?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  created_by_id?: string;
}

export interface TemplateBrief {
  id: string;
  name: string;
  code: string;
  description?: string;
  category: TemplateCategory;
  output_format: TemplateOutputFormat;
  version: number;
  is_default: boolean;
  usage_count: number;
  variable_count: number;
}

export interface GeneratedDocument {
  id: string;
  company_id: string;
  template_id: string;
  title: string;
  filename: string;
  storage_path?: string;
  file_size?: number;
  variable_values: Record<string, unknown>;
  template_version: number;
  linked_entity_id?: string;
  linked_document_id?: string;
  is_finalized: boolean;
  is_sent: boolean;
  sent_at?: string;
  sent_to: string[];
  created_at: string;
  created_by_id?: string;
}

export interface TemplateSnippet {
  id: string;
  company_id: string;
  name: string;
  code: string;
  description?: string;
  category: string;
  content: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CategorySummary {
  category: TemplateCategory;
  count: number;
  default_template_id?: string;
  default_template_name?: string;
}

// =============================================================================
// Request/Response Types
// =============================================================================

export interface TemplateListResponse {
  items: Template[];
  total: number;
  offset: number;
  limit: number;
}

export interface GeneratedDocumentListResponse {
  items: GeneratedDocument[];
  total: number;
  offset: number;
  limit: number;
}

// =============================================================================
// Form Types
// =============================================================================

export interface TemplateCreateRequest {
  name: string;
  code: string;
  description?: string;
  category?: TemplateCategory;
  content: string;
  header_content?: string;
  footer_content?: string;
  css_styles?: string;
  page_size?: string;
  orientation?: string;
  margins?: {
    top: number;
    right: number;
    bottom: number;
    left: number;
  };
  output_format?: TemplateOutputFormat;
  variables?: TemplateVariable[];
  tags?: string[];
  is_default?: boolean;
}

export interface TemplateUpdateRequest {
  name?: string;
  description?: string;
  category?: TemplateCategory;
  content?: string;
  header_content?: string;
  footer_content?: string;
  css_styles?: string;
  page_size?: string;
  orientation?: string;
  margins?: {
    top: number;
    right: number;
    bottom: number;
    left: number;
  };
  output_format?: TemplateOutputFormat;
  variables?: TemplateVariable[];
  tags?: string[];
  is_active?: boolean;
  is_default?: boolean;
  create_new_version?: boolean;
}

export interface GenerateDocumentRequest {
  template_id: string;
  title: string;
  variables?: Record<string, unknown>;
  linked_entity_id?: string;
  linked_document_id?: string;
  save_to_storage?: boolean;
}

export interface PreviewRequest {
  variables?: Record<string, unknown>;
}

export interface SnippetCreateRequest {
  name: string;
  code: string;
  description?: string;
  category?: string;
  content: string;
}

export interface SnippetUpdateRequest {
  name?: string;
  description?: string;
  category?: string;
  content?: string;
  is_active?: boolean;
}

// =============================================================================
// Query Parameters
// =============================================================================

export interface TemplateListParams {
  category?: TemplateCategory;
  is_active?: boolean;
  is_default?: boolean;
  search?: string;
  tags?: string[];
  offset?: number;
  limit?: number;
}

export interface GeneratedDocumentListParams {
  template_id?: string;
  entity_id?: string;
  search?: string;
  offset?: number;
  limit?: number;
}

export interface SnippetListParams {
  category?: string;
  is_active?: boolean;
  search?: string;
  offset?: number;
  limit?: number;
}
