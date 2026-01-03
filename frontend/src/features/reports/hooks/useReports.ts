/**
 * Report-Builder React Query Hooks
 *
 * React Query Hooks fuer Report-Templates, Spalten, Filter, Charts,
 * Ausfuehrungen, Sharing und Scheduling.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  reportKeys,
  listTemplates,
  getTemplate,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  cloneTemplate,
  listColumns,
  addColumn,
  reorderColumns,
  deleteColumn,
  listFilters,
  addFilter,
  deleteFilter,
  addChart,
  deleteChart,
  previewReport,
  executeReport,
  listExecutions,
  getExecution,
  cancelExecution,
  shareTemplate,
  revokeShare,
  listSharedWithMe,
  enableSchedule,
  disableSchedule,
  getSchedulePresets,
  getDataSources,
  getFields,
  getOperators,
  getAggregations,
  getFormats,
} from '../api';
import type {
  ReportTemplateCreate,
  ReportTemplateUpdate,
  ReportColumnCreate,
  ReportColumnReorder,
  ReportFilterCreate,
  ReportChartCreate,
  ExecutionFilters,
  ReportShareCreate,
  ScheduleEnableRequest,
  ExecuteReportRequest,
} from '../types';

// =============================================================================
// Template Hooks
// =============================================================================

/**
 * Hole alle Report-Templates.
 */
export function useTemplates(includePublic = true, includeShared = true) {
  return useQuery({
    queryKey: reportKeys.templatesList(includePublic, includeShared),
    queryFn: () => listTemplates(includePublic, includeShared),
  });
}

/**
 * Hole ein spezifisches Template.
 */
export function useTemplate(templateId: string | undefined) {
  return useQuery({
    queryKey: reportKeys.template(templateId || ''),
    queryFn: () => getTemplate(templateId!),
    enabled: !!templateId,
  });
}

/**
 * Erstelle ein neues Template.
 */
export function useCreateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ReportTemplateCreate) => createTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Report-Template erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

/**
 * Aktualisiere ein Template.
 */
export function useUpdateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReportTemplateUpdate }) =>
      updateTemplate(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Report-Template aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Loesche ein Template.
 */
export function useDeleteTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (templateId: string) => deleteTemplate(templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Report-Template geloescht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Loeschen: ${error.message}`);
    },
  });
}

/**
 * Klone ein Template.
 */
export function useCloneTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, newName }: { templateId: string; newName?: string }) =>
      cloneTemplate(templateId, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Report-Template geklont');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Klonen: ${error.message}`);
    },
  });
}

// =============================================================================
// Column Hooks
// =============================================================================

/**
 * Hole alle Spalten eines Templates.
 */
export function useColumns(templateId: string | undefined) {
  return useQuery({
    queryKey: reportKeys.columns(templateId || ''),
    queryFn: () => listColumns(templateId!),
    enabled: !!templateId,
  });
}

/**
 * Fuege eine Spalte hinzu.
 */
export function useAddColumn() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReportColumnCreate }) =>
      addColumn(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.columns(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Spalte hinzugefuegt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Sortiere Spalten um.
 */
export function useReorderColumns() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      templateId,
      columns,
    }: {
      templateId: string;
      columns: ReportColumnReorder[];
    }) => reorderColumns(templateId, columns),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.columns(variables.templateId) });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Sortieren: ${error.message}`);
    },
  });
}

/**
 * Loesche eine Spalte.
 */
export function useDeleteColumn() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, columnId }: { templateId: string; columnId: string }) =>
      deleteColumn(templateId, columnId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.columns(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Spalte entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Filter Hooks
// =============================================================================

/**
 * Hole alle Filter eines Templates.
 */
export function useFilters(templateId: string | undefined) {
  return useQuery({
    queryKey: reportKeys.filters(templateId || ''),
    queryFn: () => listFilters(templateId!),
    enabled: !!templateId,
  });
}

/**
 * Fuege einen Filter hinzu.
 */
export function useAddFilter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReportFilterCreate }) =>
      addFilter(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.filters(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Filter hinzugefuegt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Loesche einen Filter.
 */
export function useDeleteFilter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, filterId }: { templateId: string; filterId: string }) =>
      deleteFilter(templateId, filterId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.filters(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Filter entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Chart Hooks
// =============================================================================

/**
 * Fuege ein Chart hinzu.
 */
export function useAddChart() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReportChartCreate }) =>
      addChart(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Chart hinzugefuegt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Loesche ein Chart.
 */
export function useDeleteChart() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, chartId }: { templateId: string; chartId: string }) =>
      deleteChart(templateId, chartId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Chart entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Execution Hooks
// =============================================================================

/**
 * Hole Report-Vorschau.
 */
export function usePreview(templateId: string | undefined, limit = 10) {
  return useQuery({
    queryKey: reportKeys.preview(templateId || ''),
    queryFn: () => previewReport(templateId!, limit),
    enabled: !!templateId,
    staleTime: 30000, // 30 Sekunden
  });
}

/**
 * Fuehre einen Report aus.
 */
export function useExecuteReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data?: ExecuteReportRequest }) =>
      executeReport(templateId, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.executions() });
      if (result.status === 'completed') {
        toast.success('Report erfolgreich generiert');
      } else {
        toast.info('Report wird generiert...');
      }
    },
    onError: (error: Error) => {
      toast.error(`Fehler bei der Ausfuehrung: ${error.message}`);
    },
  });
}

/**
 * Liste Ausfuehrungen.
 */
export function useExecutions(filters?: ExecutionFilters) {
  return useQuery({
    queryKey: reportKeys.executionsList(filters),
    queryFn: () => listExecutions(filters),
  });
}

/**
 * Hole eine spezifische Ausfuehrung.
 */
export function useExecution(executionId: string | undefined) {
  return useQuery({
    queryKey: reportKeys.execution(executionId || ''),
    queryFn: () => getExecution(executionId!),
    enabled: !!executionId,
    refetchInterval: (data) => {
      // Polling fuer laufende Ausfuehrungen
      if (data?.state?.data?.status === 'pending' || data?.state?.data?.status === 'running') {
        return 2000; // 2 Sekunden
      }
      return false;
    },
  });
}

/**
 * Breche eine Ausfuehrung ab.
 */
export function useCancelExecution() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (executionId: string) => cancelExecution(executionId),
    onSuccess: (_, executionId) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.execution(executionId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.executions() });
      toast.success('Ausfuehrung abgebrochen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Abbrechen: ${error.message}`);
    },
  });
}

// =============================================================================
// Sharing Hooks
// =============================================================================

/**
 * Liste mit mir geteilte Reports.
 */
export function useSharedWithMe() {
  return useQuery({
    queryKey: reportKeys.shared(),
    queryFn: () => listSharedWithMe(),
  });
}

/**
 * Teile ein Template.
 */
export function useShareTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ReportShareCreate }) =>
      shareTemplate(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Report geteilt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Teilen: ${error.message}`);
    },
  });
}

/**
 * Entferne eine Freigabe.
 */
export function useRevokeShare() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, userId }: { templateId: string; userId: string }) =>
      revokeShare(templateId, userId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      toast.success('Freigabe entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Schedule Hooks
// =============================================================================

/**
 * Hole Zeitplan-Presets.
 */
export function useSchedulePresets() {
  return useQuery({
    queryKey: reportKeys.schedulePresets(),
    queryFn: () => getSchedulePresets(),
    staleTime: Infinity, // Aendert sich nicht
  });
}

/**
 * Aktiviere Zeitplan.
 */
export function useEnableSchedule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: ScheduleEnableRequest }) =>
      enableSchedule(templateId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(variables.templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Zeitplan aktiviert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Deaktiviere Zeitplan.
 */
export function useDisableSchedule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (templateId: string) => disableSchedule(templateId),
    onSuccess: (_, templateId) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.template(templateId) });
      queryClient.invalidateQueries({ queryKey: reportKeys.templates() });
      toast.success('Zeitplan deaktiviert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// =============================================================================
// Metadata Hooks
// =============================================================================

/**
 * Hole verfuegbare Datenquellen.
 */
export function useDataSources() {
  return useQuery({
    queryKey: reportKeys.dataSources(),
    queryFn: () => getDataSources(),
    staleTime: Infinity,
  });
}

/**
 * Hole verfuegbare Felder fuer eine Datenquelle.
 */
export function useFields(dataSource: string | undefined) {
  return useQuery({
    queryKey: reportKeys.fields(dataSource || ''),
    queryFn: () => getFields(dataSource!),
    enabled: !!dataSource,
    staleTime: Infinity,
  });
}

/**
 * Hole verfuegbare Filter-Operatoren.
 */
export function useOperators() {
  return useQuery({
    queryKey: reportKeys.operators(),
    queryFn: () => getOperators(),
    staleTime: Infinity,
  });
}

/**
 * Hole verfuegbare Aggregationen.
 */
export function useAggregations() {
  return useQuery({
    queryKey: reportKeys.aggregations(),
    queryFn: () => getAggregations(),
    staleTime: Infinity,
  });
}

/**
 * Hole verfuegbare Export-Formate.
 */
export function useFormats() {
  return useQuery({
    queryKey: reportKeys.formats(),
    queryFn: () => getFormats(),
    staleTime: Infinity,
  });
}
