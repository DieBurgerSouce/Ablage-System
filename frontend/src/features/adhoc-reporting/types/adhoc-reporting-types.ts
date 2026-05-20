/**
 * Ad-Hoc Reporting Types
 * German Enterprise Document Platform
 */

// Backend Types
export interface DataSource {
  key: string;
  name: string;
  description: string;
  icon?: string;
  available_columns?: Column[];
}

export interface Column {
  key: string;
  name: string;
  data_type: 'string' | 'number' | 'date' | 'boolean';
  filterable: boolean;
  sortable: boolean;
  aggregatable: boolean;
}

export type FilterOperator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'in';
export type AggregationFunction = 'count' | 'sum' | 'avg' | 'min' | 'max';
export type SortOrder = 'asc' | 'desc';
export type ExportFormat = 'pdf' | 'excel' | 'csv';

export interface Filter {
  field: string;
  operator: FilterOperator;
  value: string | number | boolean | string[];
}

export interface Aggregation {
  field: string;
  function: AggregationFunction;
  alias?: string;
}

export interface ReportDefinition {
  id?: number;
  name: string;
  description?: string;
  data_source: string;
  columns: string[];
  filters?: Filter[];
  group_by?: string[];
  aggregations?: Aggregation[];
  sort_by?: string;
  sort_order?: SortOrder;
  limit?: number;
  created_at?: string;
  updated_at?: string;
  created_by?: number;
  last_executed_at?: string;
}

export interface ExecutionResult {
  columns: string[];
  rows: Record<string, unknown>[];
  total_rows: number;
  execution_time_ms: number;
}

export interface ShareInfo {
  id: number;
  user_id: number;
  user_name?: string;
  permission: 'read' | 'write';
  shared_at: string;
}

export interface Schedule {
  id: number;
  report_id: number;
  frequency: 'daily' | 'weekly' | 'monthly';
  time: string; // HH:MM format
  recipients: string[];
  active: boolean;
  next_execution?: string;
  created_at: string;
  updated_at: string;
}

// Frontend Types
export interface ReportConfig extends Omit<ReportDefinition, 'id' | 'created_at' | 'updated_at' | 'created_by' | 'last_executed_at'> {
  // Enhanced config for UI
}

export interface ColumnConfig {
  key: string;
  alias?: string;
  order: number;
}

export interface FilterConfig extends Filter {
  id: string; // Frontend-only ID for key tracking
}

export interface AggregationConfig extends Aggregation {
  id: string; // Frontend-only ID for key tracking
}

// Transform Functions
export function toBackendReportDefinition(config: ReportConfig): Omit<ReportDefinition, 'id' | 'created_at' | 'updated_at' | 'created_by' | 'last_executed_at'> {
  return {
    name: config.name,
    description: config.description,
    data_source: config.data_source,
    columns: config.columns,
    filters: config.filters,
    group_by: config.group_by,
    aggregations: config.aggregations,
    sort_by: config.sort_by,
    sort_order: config.sort_order,
    limit: config.limit,
  };
}

export function fromBackendReportDefinition(definition: ReportDefinition): ReportDefinition {
  return definition;
}

// UI Labels
export const FILTER_OPERATOR_LABELS: Record<FilterOperator, string> = {
  eq: 'gleich',
  neq: 'ungleich',
  gt: 'größer als',
  gte: 'größer gleich',
  lt: 'kleiner als',
  lte: 'kleiner gleich',
  contains: 'enthält',
  in: 'enthalten in',
};

export const AGGREGATION_FUNCTION_LABELS: Record<AggregationFunction, string> = {
  count: 'Anzahl',
  sum: 'Summe',
  avg: 'Durchschnitt',
  min: 'Minimum',
  max: 'Maximum',
};

export const DATA_SOURCE_LABELS: Record<string, string> = {
  rechnungen: 'Rechnungen',
  dokumente: 'Dokumente',
  lieferanten: 'Lieferanten',
  kunden: 'Kunden',
  zahlungen: 'Zahlungen',
  genehmigungen: 'Genehmigungen',
};

export const FREQUENCY_LABELS: Record<Schedule['frequency'], string> = {
  daily: 'Täglich',
  weekly: 'Wöchentlich',
  monthly: 'Monatlich',
};

export const PERMISSION_LABELS: Record<ShareInfo['permission'], string> = {
  read: 'Lesen',
  write: 'Bearbeiten',
};

export const EXPORT_FORMAT_LABELS: Record<ExportFormat, string> = {
  pdf: 'PDF',
  excel: 'Excel',
  csv: 'CSV',
};
