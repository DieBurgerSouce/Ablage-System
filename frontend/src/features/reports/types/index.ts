/**
 * Report-Builder TypeScript Types
 *
 * Typen für Report-Templates, Spalten, Filter, Charts, Ausführungen und Sharing.
 */

// =============================================================================
// Enums
// =============================================================================

export type ReportType = 'document' | 'finance' | 'ocr' | 'custom';
export type DataSource = 'documents' | 'invoices' | 'entities' | 'ocr_results';
export type ExportFormat = 'pdf' | 'excel' | 'csv' | 'json';
export type DataType = 'string' | 'number' | 'date' | 'currency' | 'boolean';
export type AggregationType = 'none' | 'sum' | 'avg' | 'count' | 'min' | 'max';
export type ChartType = 'bar' | 'line' | 'pie' | 'area' | 'stacked_bar';
export type ExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TriggerType = 'manual' | 'scheduled' | 'api';
export type SchedulePresetId =
  | 'daily_morning'
  | 'daily_evening'
  | 'weekly_monday'
  | 'weekly_friday'
  | 'monthly_first'
  | 'monthly_last_workday'
  | 'quarterly';

export type FilterOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'starts_with'
  | 'ends_with'
  | 'greater_than'
  | 'greater_equal'
  | 'less_than'
  | 'less_equal'
  | 'between'
  | 'in'
  | 'not_in'
  | 'is_null'
  | 'is_not_null';

// =============================================================================
// Report Template
// =============================================================================

export interface ScheduleConfig {
  cron_expression: string;
  timezone: string;
  recipients: string[];
  format: ExportFormat;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
}

export interface LayoutConfig {
  page_orientation?: 'portrait' | 'landscape';
  page_size?: 'A4' | 'A3' | 'Letter';
  margins?: { top: number; right: number; bottom: number; left: number };
  header_text?: string;
  footer_text?: string;
  show_page_numbers?: boolean;
}

export interface ReportTemplate {
  id: string;
  user_id: string;
  company_id?: string;
  name: string;
  description?: string;
  report_type: ReportType;
  data_source: DataSource;
  default_format: ExportFormat;
  default_filters?: Record<string, unknown>;
  is_public: boolean;
  is_scheduled: boolean;
  schedule_config?: ScheduleConfig;
  layout_config?: LayoutConfig;
  row_limit?: number;
  enable_aggregations: boolean;
  created_at: string;
  updated_at: string;
  last_executed_at?: string;
  columns?: ReportColumn[];
  filters?: ReportFilter[];
  charts?: ReportChart[];
}

export interface ReportTemplateCreate {
  name: string;
  description?: string;
  report_type: ReportType;
  data_source: DataSource;
  default_format?: ExportFormat;
  default_filters?: Record<string, unknown>;
  is_public?: boolean;
  layout_config?: LayoutConfig;
  row_limit?: number;
  enable_aggregations?: boolean;
}

export interface ReportTemplateUpdate {
  name?: string;
  description?: string;
  report_type?: ReportType;
  data_source?: DataSource;
  default_format?: ExportFormat;
  default_filters?: Record<string, unknown>;
  is_public?: boolean;
  layout_config?: LayoutConfig;
  row_limit?: number;
  enable_aggregations?: boolean;
}

// =============================================================================
// Report Column
// =============================================================================

export interface ReportColumn {
  id: string;
  template_id: string;
  field_path: string;
  display_name: string;
  data_type: DataType;
  format_pattern?: string;
  width?: number;
  sort_order: number;
  is_visible: boolean;
  is_sortable: boolean;
  default_sort?: 'asc' | 'desc';
  aggregation: AggregationType;
  formula?: string;
}

export interface ReportColumnCreate {
  field_path: string;
  display_name: string;
  data_type: DataType;
  format_pattern?: string;
  width?: number;
  is_visible?: boolean;
  is_sortable?: boolean;
  default_sort?: 'asc' | 'desc';
  aggregation?: AggregationType;
  formula?: string;
}

export interface ReportColumnReorder {
  column_id: string;
  sort_order: number;
}

// =============================================================================
// Report Filter
// =============================================================================

export interface ReportFilter {
  id: string;
  template_id: string;
  field_path: string;
  operator: FilterOperator;
  value?: string | number | boolean | string[] | number[];
  value_type: DataType;
  is_required: boolean;
  allow_user_input: boolean;
  default_value?: string | number | boolean;
  dynamic_source?: 'today' | 'last_7_days' | 'last_30_days' | 'current_user' | 'current_company';
  logic_operator: 'AND' | 'OR';
  group_id?: number;
  sort_order: number;
}

export interface ReportFilterCreate {
  field_path: string;
  operator: FilterOperator;
  value?: string | number | boolean | string[] | number[];
  value_type: DataType;
  is_required?: boolean;
  allow_user_input?: boolean;
  default_value?: string | number | boolean;
  dynamic_source?: string;
  logic_operator?: 'AND' | 'OR';
  group_id?: number;
}

// =============================================================================
// Report Chart
// =============================================================================

export interface ChartStyling {
  colors?: string[];
  show_legend?: boolean;
  legend_position?: 'top' | 'bottom' | 'left' | 'right';
  show_data_labels?: boolean;
  stacked?: boolean;
}

export interface ReportChart {
  id: string;
  template_id: string;
  chart_type: ChartType;
  title?: string;
  description?: string;
  x_axis_field?: string;
  y_axis_field?: string;
  group_by_field?: string;
  aggregation: AggregationType;
  sort_order: number;
  styling?: ChartStyling;
  filters?: Record<string, unknown>;
}

export interface ReportChartCreate {
  chart_type: ChartType;
  title?: string;
  description?: string;
  x_axis_field?: string;
  y_axis_field?: string;
  group_by_field?: string;
  aggregation?: AggregationType;
  styling?: ChartStyling;
  filters?: Record<string, unknown>;
}

// =============================================================================
// Report Execution
// =============================================================================

export interface ReportExecution {
  id: string;
  template_id: string;
  template_name?: string;
  executed_by_id?: string;
  status: ExecutionStatus;
  format: ExportFormat;
  trigger_type: TriggerType;
  filter_snapshot?: Record<string, unknown>;
  row_count?: number;
  file_size_bytes?: number;
  file_path?: string;
  download_url?: string;
  download_expires_at?: string;
  error_message?: string;
  error_details?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  created_at: string;
}

export interface ExecutionFilters {
  template_id?: string;
  status?: ExecutionStatus;
  trigger_type?: TriggerType;
  limit?: number;
  offset?: number;
}

// =============================================================================
// Report Sharing
// =============================================================================

export interface ReportShare {
  id: string;
  template_id: string;
  template_name?: string;
  shared_with_id: string;
  shared_with_name?: string;
  shared_with_email?: string;
  can_view: boolean;
  can_execute: boolean;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  expires_at?: string;
}

export interface ReportShareCreate {
  user_id: string;
  can_view?: boolean;
  can_execute?: boolean;
  can_edit?: boolean;
  can_delete?: boolean;
  expires_at?: string;
}

// =============================================================================
// Metadata Types
// =============================================================================

export interface FieldDefinition {
  path: string;
  display_name: string;
  data_type: DataType;
  category?: string;
}

export interface DataSourceInfo {
  source: DataSource;
  name: string;
  description: string;
  fields: FieldDefinition[];
}

export interface OperatorInfo {
  operator: FilterOperator;
  name: string;
  description: string;
  requires_value: boolean;
  allowed_types: DataType[];
}

export interface AggregationInfo {
  aggregation: AggregationType;
  name: string;
  description: string;
  allowed_types: DataType[];
}

export interface FormatInfo {
  format: ExportFormat;
  name: string;
  mime_type: string;
  extension: string;
  available: boolean;
}

export interface SchedulePreset {
  id: SchedulePresetId;
  name: string;
  cron: string;
}

// =============================================================================
// Preview Types
// =============================================================================

export interface ReportPreview {
  columns: string[];
  data: Record<string, unknown>[];
  total_available: number;
  preview_limit: number;
}

// =============================================================================
// API Response Types
// =============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SuccessResponse {
  success: boolean;
  message: string;
}

export interface ScheduleEnableRequest {
  cron_expression: string;
  timezone?: string;
  recipients?: string[];
  format?: ExportFormat;
}

export interface ExecuteReportRequest {
  format?: ExportFormat;
  filters?: Record<string, unknown>;
  async_execution?: boolean;
}

export interface ExecuteReportResponse {
  execution_id: string;
  status: ExecutionStatus;
  message: string;
  download_url?: string;
}

// =============================================================================
// Catalog Types
// =============================================================================

export interface CatalogColumnDefinition {
  field_path: string;
  display_name: string;
  data_type: string;
}

export interface CatalogChartDefinition {
  chart_type: string;
  title?: string;
  x_axis_field?: string;
  y_axis_fields: string[];
}

export interface CatalogFilterDefinition {
  field_path: string;
  operator: string;
  value?: unknown;
}

export interface CatalogTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  report_type: ReportType;
  data_source: DataSource;
  icon: string;
  default_columns: CatalogColumnDefinition[];
  default_filters?: CatalogFilterDefinition[];
  default_charts?: CatalogChartDefinition[];
  tags: string[];
}

export interface CatalogCategory {
  id: string;
  name: string;
  description: string;
  template_count: number;
}

export interface CatalogListResponse {
  templates: CatalogTemplate[];
  categories: CatalogCategory[];
  total: number;
}

export interface InstantiateTemplateRequest {
  name?: string;
}
