/**
 * Validation Queue Feature Types
 *
 * TypeScript-Definitionen fuer das Enterprise-Grade Validierungs-Queue-System.
 * Vollstaendige Type-Safety fuer Queue-Management, Field Reviews und Analytics.
 */

// ==================== Enums ====================

export enum ValidationStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  APPROVED = 'approved',
  REJECTED = 'rejected',
}

export enum SampleSource {
  AUTOMATIC = 'automatic',
  RULE_BASED = 'rule_based',
  LOW_CONFIDENCE = 'low_confidence',
  MANUAL = 'manual',
}

export enum ValidationRuleType {
  CONFIDENCE_THRESHOLD = 'confidence_threshold',
  FIELD_PATTERN = 'field_pattern',
  DOCUMENT_TYPE = 'document_type',
  ERROR_PATTERN = 'error_pattern',
}

export enum RejectionCategory {
  OCR_ERROR = 'ocr_error',
  EXTRACTION_ERROR = 'extraction_error',
  DOCUMENT_QUALITY = 'document_quality',
  WRONG_DOCUMENT_TYPE = 'wrong_document_type',
  INCOMPLETE_DATA = 'incomplete_data',
  OTHER = 'other',
}

// ==================== Label Maps (Deutsche UI) ====================

export const VALIDATION_STATUS_LABELS: Record<ValidationStatus, string> = {
  [ValidationStatus.PENDING]: 'Ausstehend',
  [ValidationStatus.IN_PROGRESS]: 'In Bearbeitung',
  [ValidationStatus.APPROVED]: 'Genehmigt',
  [ValidationStatus.REJECTED]: 'Abgelehnt',
};

export const SAMPLE_SOURCE_LABELS: Record<SampleSource, string> = {
  [SampleSource.AUTOMATIC]: 'Automatisch',
  [SampleSource.RULE_BASED]: 'Regelbasiert',
  [SampleSource.LOW_CONFIDENCE]: 'Niedrige Konfidenz',
  [SampleSource.MANUAL]: 'Manuell',
};

export const RULE_TYPE_LABELS: Record<ValidationRuleType, string> = {
  [ValidationRuleType.CONFIDENCE_THRESHOLD]: 'Konfidenz-Schwellenwert',
  [ValidationRuleType.FIELD_PATTERN]: 'Feld-Muster',
  [ValidationRuleType.DOCUMENT_TYPE]: 'Dokumenttyp',
  [ValidationRuleType.ERROR_PATTERN]: 'Fehler-Muster',
};

export const REJECTION_CATEGORY_LABELS: Record<RejectionCategory, string> = {
  [RejectionCategory.OCR_ERROR]: 'OCR-Fehler',
  [RejectionCategory.EXTRACTION_ERROR]: 'Extraktionsfehler',
  [RejectionCategory.DOCUMENT_QUALITY]: 'Dokumentqualitaet',
  [RejectionCategory.WRONG_DOCUMENT_TYPE]: 'Falscher Dokumenttyp',
  [RejectionCategory.INCOMPLETE_DATA]: 'Unvollstaendige Daten',
  [RejectionCategory.OTHER]: 'Sonstiges',
};

// ==================== Queue Item Types ====================

export interface ValidationQueueItem {
  id: string;
  document_id: string;
  status: ValidationStatus;
  sample_source: SampleSource;
  priority: number;
  triggered_by_rule_id: string | null;
  assigned_to_id: string | null;
  assigned_at: string | null;
  validated_by_id: string | null;
  validated_at: string | null;
  min_field_confidence: number | null;
  avg_field_confidence: number | null;
  fields_below_threshold: number;
  total_fields: number;
  rejection_reason: string | null;
  rejection_category: RejectionCategory | null;
  validation_notes: string | null;
  time_to_validate_seconds: number | null;
  corrections_made: number;
  created_at: string;
  updated_at: string;
  // Joined data
  document_name?: string;
  document_type?: string;
  assigned_to_name?: string;
  validated_by_name?: string;
  rule_name?: string;
}

export interface ValidationFieldReview {
  id: string;
  queue_item_id: string;
  field_key: string;
  field_label: string;
  field_type: string | null;
  original_value: string | null;
  corrected_value: string | null;
  was_corrected: boolean;
  confidence_score: number | null;
  confidence_threshold: number;
  is_below_threshold: boolean;
  bounding_box: BoundingBox | null;
  ocr_backend: string | null;
  validation_errors: ValidationError[];
  umlaut_issues: UmlautIssue[];
  format_issues: FormatIssue[];
  validation_status: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BoundingBox {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ValidationError {
  type: string;
  message?: string;
  field?: string;
  [key: string]: unknown;
}

export interface UmlautIssue {
  type: string;
  position?: number;
  original?: string;
  suggested?: string;
  confidence?: number;
}

export interface FormatIssue {
  field: string;
  message: string;
  expected_format?: string;
}

export interface ValidationQueueItemDetail extends ValidationQueueItem {
  fields: ValidationFieldReview[];
}

// ==================== Rule Types ====================

export interface ValidationRule {
  id: string;
  name: string;
  description: string | null;
  rule_type: ValidationRuleType;
  conditions: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  is_system: boolean;
  documents_matched: number;
  last_triggered_at: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationRuleCreate {
  name: string;
  description?: string;
  rule_type: ValidationRuleType;
  conditions: Record<string, unknown>;
  priority?: number;
  is_active?: boolean;
}

export interface ValidationRuleUpdate {
  name?: string;
  description?: string;
  conditions?: Record<string, unknown>;
  priority?: number;
  is_active?: boolean;
}

// ==================== Sample Config Types ====================

export interface ValidationSampleConfig {
  id: string;
  sample_percentage: number;
  min_confidence_threshold: number;
  stratify_by_document_type: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ValidationSampleConfigUpdate {
  sample_percentage?: number;
  min_confidence_threshold?: number;
  stratify_by_document_type?: boolean;
  is_active?: boolean;
}

// ==================== Batch Operation Types ====================

export interface BatchApproveRequest {
  item_ids: string[];
  notes?: string;
}

export interface BatchRejectRequest {
  item_ids: string[];
  reason: string;
  rejection_category?: RejectionCategory;
}

export interface BatchAssignRequest {
  item_ids: string[];
  editor_id: string;
}

export interface BatchOperationResult {
  success_count: number;
  failure_count: number;
  failed_ids: string[];
  errors: string[];
}

// ==================== Analytics Types ====================

export interface ValidationAnalyticsOverview {
  total_items: number;
  pending_items: number;
  in_progress_items: number;
  approved_items: number;
  rejected_items: number;
  avg_time_to_validate_seconds: number | null;
  avg_corrections_per_item: number | null;
  approval_rate: number | null;
  items_validated_today: number;
  items_validated_this_week: number;
  items_validated_this_month: number;
}

export interface EditorStats {
  editor_id: string;
  editor_name: string;
  items_validated: number;
  items_approved: number;
  items_rejected: number;
  avg_time_per_item_seconds: number | null;
  total_corrections_made: number;
  accuracy_rate: number | null;
}

export interface TrendDataPoint {
  date: string;
  validated_count: number;
  approved_count: number;
  rejected_count: number;
  avg_time_seconds: number | null;
}

export interface DocumentTypeStats {
  document_type: string;
  total_count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  avg_confidence: number | null;
  avg_corrections: number | null;
}

export interface ConfidenceDistribution {
  buckets: ConfidenceBucket[];
  avg_confidence: number | null;
  median_confidence: number | null;
  min_confidence: number | null;
  max_confidence: number | null;
}

export interface ConfidenceBucket {
  range_start: number;
  range_end: number;
  count: number;
  percentage: number;
}

// ==================== Filter Types ====================

export interface ValidationQueueFilters {
  status?: ValidationStatus;
  document_type?: string;
  priority_min?: number;
  priority_max?: number;
  confidence_min?: number;
  confidence_max?: number;
  assigned_to_id?: string;
  sample_source?: SampleSource;
  created_from?: string;
  created_to?: string;
}

export interface ValidationQueueSortOptions {
  sort_by?: 'created_at' | 'priority' | 'avg_field_confidence' | 'status';
  sort_order?: 'asc' | 'desc';
}

export interface ValidationQueuePagination {
  limit: number;
  offset: number;
}

// ==================== List Response Types ====================

export interface ValidationQueueListResponse {
  items: ValidationQueueItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ValidationRuleListResponse {
  rules: ValidationRule[];
  total: number;
}

export interface EditorStatsListResponse {
  editors: EditorStats[];
}

export interface TrendDataResponse {
  data_points: TrendDataPoint[];
  group_by: 'day' | 'week' | 'month';
}

export interface DocumentTypeStatsResponse {
  document_types: DocumentTypeStats[];
}

// ==================== Request Types ====================

export interface ValidationQueueItemCreate {
  document_id: string;
  sample_source?: SampleSource;
  priority?: number;
  notes?: string;
  triggered_by_rule_id?: string;
}

export interface ValidationQueueItemUpdate {
  priority?: number;
  notes?: string;
}

export interface ValidationQueueItemAssign {
  editor_id: string;
}

export interface ValidationQueueItemApprove {
  notes?: string;
  apply_corrections?: boolean;
}

export interface ValidationQueueItemReject {
  reason: string;
  rejection_category?: RejectionCategory;
}

export interface ValidationFieldUpdate {
  corrected_value: string;
}

export interface ValidationFieldValidateResult {
  field_id: string;
  field_key: string;
  is_valid: boolean;
  errors: ValidationError[];
  umlaut_issues: UmlautIssue[];
  format_issues: FormatIssue[];
  suggested_correction?: string;
}

// ==================== Color Utilities ====================

export function getValidationStatusColor(status: ValidationStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  const colors: Record<ValidationStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
    [ValidationStatus.PENDING]: 'outline',
    [ValidationStatus.IN_PROGRESS]: 'secondary',
    [ValidationStatus.APPROVED]: 'default',
    [ValidationStatus.REJECTED]: 'destructive',
  };
  return colors[status];
}

export function getValidationStatusBgColor(status: ValidationStatus): string {
  const colors: Record<ValidationStatus, string> = {
    [ValidationStatus.PENDING]: 'bg-gray-100 dark:bg-gray-800',
    [ValidationStatus.IN_PROGRESS]: 'bg-blue-100 dark:bg-blue-900/30',
    [ValidationStatus.APPROVED]: 'bg-green-100 dark:bg-green-900/30',
    [ValidationStatus.REJECTED]: 'bg-red-100 dark:bg-red-900/30',
  };
  return colors[status];
}

export function getSampleSourceColor(source: SampleSource): string {
  const colors: Record<SampleSource, string> = {
    [SampleSource.AUTOMATIC]: 'text-blue-600 dark:text-blue-400',
    [SampleSource.RULE_BASED]: 'text-purple-600 dark:text-purple-400',
    [SampleSource.LOW_CONFIDENCE]: 'text-orange-600 dark:text-orange-400',
    [SampleSource.MANUAL]: 'text-gray-600 dark:text-gray-400',
  };
  return colors[source];
}

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.9) return 'text-green-600 dark:text-green-400';
  if (confidence >= 0.7) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-red-600 dark:text-red-400';
}

export function getConfidenceBgColor(confidence: number): string {
  if (confidence >= 0.9) return 'bg-green-100 dark:bg-green-900/30';
  if (confidence >= 0.7) return 'bg-yellow-100 dark:bg-yellow-900/30';
  return 'bg-red-100 dark:bg-red-900/30';
}

export function getPriorityColor(priority: number): string {
  if (priority >= 80) return 'text-red-600 dark:text-red-400';
  if (priority >= 50) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-gray-600 dark:text-gray-400';
}
