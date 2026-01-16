/**
 * Report-Builder API Client
 *
 * API-Funktionen fuer Report-Templates, Spalten, Filter, Charts,
 * Ausfuehrungen, Sharing und Scheduling.
 */

import { apiClient as api } from '@/lib/api/client';
import type {
  ReportTemplate,
  ReportTemplateCreate,
  ReportTemplateUpdate,
  ReportColumn,
  ReportColumnCreate,
  ReportColumnReorder,
  ReportFilter,
  ReportFilterCreate,
  ReportChart,
  ReportChartCreate,
  ReportExecution,
  ExecutionFilters,
  ReportShare,
  ReportShareCreate,
  DataSourceInfo,
  FieldDefinition,
  OperatorInfo,
  AggregationInfo,
  FormatInfo,
  SchedulePreset,
  ReportPreview,
  SuccessResponse,
  ScheduleEnableRequest,
  ExecuteReportRequest,
  ExecuteReportResponse,
  CatalogListResponse,
  CatalogTemplate,
  InstantiateTemplateRequest,
} from '../types';

const BASE_URL = '/reports';

// =============================================================================
// Template CRUD
// =============================================================================

/**
 * Liste alle Report-Templates (eigene + oeffentliche + geteilte).
 */
export async function listTemplates(
  includePublic = true,
  includeShared = true
): Promise<ReportTemplate[]> {
  const response = await api.get<ReportTemplate[]>(`${BASE_URL}/templates`, {
    params: {
      include_public: includePublic,
      include_shared: includeShared,
    },
  });
  return response.data;
}

/**
 * Hole ein spezifisches Report-Template.
 */
export async function getTemplate(templateId: string): Promise<ReportTemplate> {
  const response = await api.get<ReportTemplate>(`${BASE_URL}/templates/${templateId}`);
  return response.data;
}

/**
 * Erstelle ein neues Report-Template.
 */
export async function createTemplate(data: ReportTemplateCreate): Promise<ReportTemplate> {
  const response = await api.post<ReportTemplate>(`${BASE_URL}/templates`, data);
  return response.data;
}

/**
 * Aktualisiere ein Report-Template.
 */
export async function updateTemplate(
  templateId: string,
  data: ReportTemplateUpdate
): Promise<ReportTemplate> {
  const response = await api.put<ReportTemplate>(`${BASE_URL}/templates/${templateId}`, data);
  return response.data;
}

/**
 * Loesche ein Report-Template.
 */
export async function deleteTemplate(templateId: string): Promise<void> {
  await api.delete(`${BASE_URL}/templates/${templateId}`);
}

/**
 * Klone ein Report-Template.
 */
export async function cloneTemplate(
  templateId: string,
  newName?: string
): Promise<ReportTemplate> {
  const response = await api.post<ReportTemplate>(
    `${BASE_URL}/templates/${templateId}/clone`,
    null,
    { params: newName ? { new_name: newName } : undefined }
  );
  return response.data;
}

// =============================================================================
// Column Management
// =============================================================================

/**
 * Liste alle Spalten eines Templates.
 */
export async function listColumns(templateId: string): Promise<ReportColumn[]> {
  const response = await api.get<ReportColumn[]>(`${BASE_URL}/templates/${templateId}/columns`);
  return response.data;
}

/**
 * Fuege eine Spalte zu einem Template hinzu.
 */
export async function addColumn(
  templateId: string,
  data: ReportColumnCreate
): Promise<ReportColumn> {
  const response = await api.post<ReportColumn>(
    `${BASE_URL}/templates/${templateId}/columns`,
    data
  );
  return response.data;
}

/**
 * Aktualisiere die Spaltenreihenfolge.
 */
export async function reorderColumns(
  templateId: string,
  columns: ReportColumnReorder[]
): Promise<SuccessResponse> {
  const response = await api.put<SuccessResponse>(
    `${BASE_URL}/templates/${templateId}/columns/reorder`,
    { columns }
  );
  return response.data;
}

/**
 * Loesche eine Spalte.
 */
export async function deleteColumn(templateId: string, columnId: string): Promise<void> {
  await api.delete(`${BASE_URL}/templates/${templateId}/columns/${columnId}`);
}

// =============================================================================
// Filter Management
// =============================================================================

/**
 * Liste alle Filter eines Templates.
 */
export async function listFilters(templateId: string): Promise<ReportFilter[]> {
  const response = await api.get<ReportFilter[]>(`${BASE_URL}/templates/${templateId}/filters`);
  return response.data;
}

/**
 * Fuege einen Filter zu einem Template hinzu.
 */
export async function addFilter(
  templateId: string,
  data: ReportFilterCreate
): Promise<ReportFilter> {
  const response = await api.post<ReportFilter>(
    `${BASE_URL}/templates/${templateId}/filters`,
    data
  );
  return response.data;
}

/**
 * Loesche einen Filter.
 */
export async function deleteFilter(templateId: string, filterId: string): Promise<void> {
  await api.delete(`${BASE_URL}/templates/${templateId}/filters/${filterId}`);
}

// =============================================================================
// Chart Management
// =============================================================================

/**
 * Fuege ein Chart zu einem Template hinzu.
 */
export async function addChart(
  templateId: string,
  data: ReportChartCreate
): Promise<ReportChart> {
  const response = await api.post<ReportChart>(
    `${BASE_URL}/templates/${templateId}/charts`,
    data
  );
  return response.data;
}

/**
 * Loesche ein Chart.
 */
export async function deleteChart(templateId: string, chartId: string): Promise<void> {
  await api.delete(`${BASE_URL}/templates/${templateId}/charts/${chartId}`);
}

// =============================================================================
// Execution
// =============================================================================

/**
 * Zeige eine Vorschau des Reports (limitierte Daten).
 */
export async function previewReport(
  templateId: string,
  limit = 10
): Promise<ReportPreview> {
  const response = await api.post<ReportPreview>(
    `${BASE_URL}/templates/${templateId}/preview`,
    null,
    { params: { limit } }
  );
  return response.data;
}

/**
 * Fuehre einen Report aus.
 */
export async function executeReport(
  templateId: string,
  data?: ExecuteReportRequest
): Promise<ExecuteReportResponse> {
  const response = await api.post<ExecuteReportResponse>(
    `${BASE_URL}/templates/${templateId}/execute`,
    data || {}
  );
  return response.data;
}

/**
 * Liste alle Ausfuehrungen.
 */
export async function listExecutions(
  filters?: ExecutionFilters
): Promise<ReportExecution[]> {
  const response = await api.get<ReportExecution[]>(`${BASE_URL}/executions`, {
    params: filters,
  });
  return response.data;
}

/**
 * Hole eine spezifische Ausfuehrung.
 */
export async function getExecution(executionId: string): Promise<ReportExecution> {
  const response = await api.get<ReportExecution>(`${BASE_URL}/executions/${executionId}`);
  return response.data;
}

/**
 * Lade einen generierten Report herunter.
 */
export function getDownloadUrl(executionId: string): string {
  return `${BASE_URL}/executions/${executionId}/download`;
}

/**
 * Breche eine laufende Ausfuehrung ab.
 */
export async function cancelExecution(executionId: string): Promise<SuccessResponse> {
  const response = await api.post<SuccessResponse>(
    `${BASE_URL}/executions/${executionId}/cancel`
  );
  return response.data;
}

// =============================================================================
// Sharing
// =============================================================================

/**
 * Teile ein Template mit einem User.
 */
export async function shareTemplate(
  templateId: string,
  data: ReportShareCreate
): Promise<ReportShare> {
  const response = await api.post<ReportShare>(
    `${BASE_URL}/templates/${templateId}/share`,
    data
  );
  return response.data;
}

/**
 * Entferne eine Freigabe.
 */
export async function revokeShare(templateId: string, userId: string): Promise<void> {
  await api.delete(`${BASE_URL}/templates/${templateId}/share/${userId}`);
}

/**
 * Liste mit mir geteilte Reports.
 */
export async function listSharedWithMe(): Promise<ReportShare[]> {
  const response = await api.get<ReportShare[]>(`${BASE_URL}/shared`);
  return response.data;
}

// =============================================================================
// Scheduling
// =============================================================================

/**
 * Aktiviere einen Zeitplan fuer ein Template.
 */
export async function enableSchedule(
  templateId: string,
  data: ScheduleEnableRequest
): Promise<ReportTemplate> {
  const response = await api.post<ReportTemplate>(
    `${BASE_URL}/templates/${templateId}/schedule`,
    data
  );
  return response.data;
}

/**
 * Deaktiviere einen Zeitplan.
 */
export async function disableSchedule(templateId: string): Promise<SuccessResponse> {
  const response = await api.delete<SuccessResponse>(
    `${BASE_URL}/templates/${templateId}/schedule`
  );
  return response.data;
}

/**
 * Hole Zeitplan-Presets.
 */
export async function getSchedulePresets(): Promise<SchedulePreset[]> {
  const response = await api.get<SchedulePreset[]>(`${BASE_URL}/schedule/presets`);
  return response.data;
}

// =============================================================================
// Metadata
// =============================================================================

/**
 * Hole verfuegbare Datenquellen.
 */
export async function getDataSources(): Promise<DataSourceInfo[]> {
  const response = await api.get<DataSourceInfo[]>(`${BASE_URL}/data-sources`);
  return response.data;
}

/**
 * Hole verfuegbare Felder fuer eine Datenquelle.
 */
export async function getFields(dataSource: string): Promise<FieldDefinition[]> {
  const response = await api.get<FieldDefinition[]>(
    `${BASE_URL}/data-sources/${dataSource}/fields`
  );
  return response.data;
}

/**
 * Hole verfuegbare Filter-Operatoren.
 */
export async function getOperators(): Promise<OperatorInfo[]> {
  const response = await api.get<OperatorInfo[]>(`${BASE_URL}/operators`);
  return response.data;
}

/**
 * Hole verfuegbare Aggregationen.
 */
export async function getAggregations(): Promise<AggregationInfo[]> {
  const response = await api.get<AggregationInfo[]>(`${BASE_URL}/aggregations`);
  return response.data;
}

/**
 * Hole verfuegbare Export-Formate.
 */
export async function getFormats(): Promise<FormatInfo[]> {
  const response = await api.get<FormatInfo[]>(`${BASE_URL}/formats`);
  return response.data;
}

// =============================================================================
// Catalog
// =============================================================================

/**
 * Hole den Template-Katalog.
 */
export async function getCatalog(category?: string): Promise<CatalogListResponse> {
  const response = await api.get<CatalogListResponse>(`${BASE_URL}/catalog`, {
    params: category ? { category } : undefined,
  });
  return response.data;
}

/**
 * Hole ein spezifisches Katalog-Template.
 */
export async function getCatalogTemplate(templateId: string): Promise<CatalogTemplate> {
  const response = await api.get<CatalogTemplate>(`${BASE_URL}/catalog/${templateId}`);
  return response.data;
}

/**
 * Erstelle einen neuen Report aus einem Katalog-Template.
 */
export async function instantiateTemplate(
  templateId: string,
  data?: InstantiateTemplateRequest
): Promise<ReportTemplate> {
  const response = await api.post<ReportTemplate>(
    `${BASE_URL}/catalog/${templateId}/instantiate`,
    data || {}
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const reportKeys = {
  all: ['reports'] as const,

  // Templates
  templates: () => [...reportKeys.all, 'templates'] as const,
  templatesList: (includePublic?: boolean, includeShared?: boolean) =>
    [...reportKeys.templates(), 'list', { includePublic, includeShared }] as const,
  template: (id: string) => [...reportKeys.templates(), 'detail', id] as const,

  // Columns
  columns: (templateId: string) => [...reportKeys.template(templateId), 'columns'] as const,

  // Filters
  filters: (templateId: string) => [...reportKeys.template(templateId), 'filters'] as const,

  // Executions
  executions: () => [...reportKeys.all, 'executions'] as const,
  executionsList: (filters?: ExecutionFilters) =>
    [...reportKeys.executions(), 'list', filters] as const,
  execution: (id: string) => [...reportKeys.executions(), 'detail', id] as const,

  // Sharing
  shared: () => [...reportKeys.all, 'shared'] as const,

  // Metadata
  dataSources: () => [...reportKeys.all, 'data-sources'] as const,
  fields: (dataSource: string) => [...reportKeys.dataSources(), dataSource, 'fields'] as const,
  operators: () => [...reportKeys.all, 'operators'] as const,
  aggregations: () => [...reportKeys.all, 'aggregations'] as const,
  formats: () => [...reportKeys.all, 'formats'] as const,
  schedulePresets: () => [...reportKeys.all, 'schedule-presets'] as const,

  // Preview
  preview: (templateId: string) => [...reportKeys.template(templateId), 'preview'] as const,

  // Catalog
  catalog: () => [...reportKeys.all, 'catalog'] as const,
  catalogList: (category?: string) => [...reportKeys.catalog(), 'list', { category }] as const,
  catalogTemplate: (id: string) => [...reportKeys.catalog(), 'template', id] as const,
};
