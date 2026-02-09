/**
 * Report-Builder API Client
 *
 * Zusaetzliche API-Funktionen und TanStack Query Hooks fuer den
 * visuellen Report-Builder und Scheduled Exports.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiClient as api } from '@/lib/api/client';

// =============================================================================
// Types (re-exports + additions)
// =============================================================================

export type {
  ReportTemplate,
  ReportTemplateCreate,
  ChartType,
  AggregationType,
  FilterOperator,
  ExportFormat,
  ReportFilter,
  ReportFilterCreate,
  DataSource,
  ReportType,
  FieldDefinition,
  DataSourceInfo,
  ScheduleConfig,
  ReportPreview,
  ReportExecution,
  ExecutionStatus,
} from '../types';

export interface ScheduledExport {
  id: string;
  name: string;
  description: string | null;
  cron_expression: string;
  timezone: string;
  export_type: string;
  export_format: string;
  filter_config: Record<string, unknown> | null;
  include_text: boolean;
  include_metadata: boolean;
  notify_email: boolean;
  notify_on_failure_only: boolean;
  notification_email: string | null;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  run_count: number;
  created_at: string;
  updated_at: string;
}

export interface ScheduledExportCreate {
  name: string;
  description?: string;
  cron_expression: string;
  timezone?: string;
  export_type: string;
  export_format: string;
  filter_config?: Record<string, unknown>;
  include_text?: boolean;
  include_metadata?: boolean;
  notify_email?: boolean;
  notify_on_failure_only?: boolean;
  notification_email?: string;
}

export interface ScheduledExportUpdate {
  name?: string;
  description?: string;
  cron_expression?: string;
  timezone?: string;
  export_format?: string;
  filter_config?: Record<string, unknown>;
  notify_email?: boolean;
  notification_email?: string;
}

// =============================================================================
// Scheduled Exports API Functions
// =============================================================================

const EXPORTS_BASE = '/scheduled-exports';

export async function getScheduledExports(): Promise<ScheduledExport[]> {
  const response = await api.get<ScheduledExport[]>(EXPORTS_BASE);
  return response.data;
}

export async function getScheduledExport(exportId: string): Promise<ScheduledExport> {
  const response = await api.get<ScheduledExport>(`${EXPORTS_BASE}/${exportId}`);
  return response.data;
}

export async function createScheduledExport(
  data: ScheduledExportCreate
): Promise<ScheduledExport> {
  const response = await api.post<ScheduledExport>(EXPORTS_BASE, data);
  return response.data;
}

export async function updateScheduledExport(
  exportId: string,
  data: ScheduledExportUpdate
): Promise<ScheduledExport> {
  const response = await api.patch<ScheduledExport>(
    `${EXPORTS_BASE}/${exportId}`,
    data
  );
  return response.data;
}

export async function deleteScheduledExport(exportId: string): Promise<void> {
  await api.delete(`${EXPORTS_BASE}/${exportId}`);
}

export async function toggleScheduledExport(
  exportId: string,
  active: boolean
): Promise<ScheduledExport> {
  const response = await api.post<ScheduledExport>(
    `${EXPORTS_BASE}/${exportId}/${active ? 'activate' : 'deactivate'}`
  );
  return response.data;
}

export async function runScheduledExportNow(exportId: string): Promise<{ job_id: string }> {
  const response = await api.post<{ job_id: string }>(
    `${EXPORTS_BASE}/${exportId}/run`
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const scheduledExportKeys = {
  all: ['scheduled-exports'] as const,
  list: () => [...scheduledExportKeys.all, 'list'] as const,
  detail: (id: string) => [...scheduledExportKeys.all, 'detail', id] as const,
};

// =============================================================================
// React Query Hooks
// =============================================================================

export function useScheduledExports() {
  return useQuery({
    queryKey: scheduledExportKeys.list(),
    queryFn: getScheduledExports,
  });
}

export function useScheduledExport(exportId: string | undefined) {
  return useQuery({
    queryKey: scheduledExportKeys.detail(exportId || ''),
    queryFn: () => getScheduledExport(exportId!),
    enabled: !!exportId,
  });
}

export function useCreateScheduledExport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ScheduledExportCreate) => createScheduledExport(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduledExportKeys.all });
      toast.success('Geplanter Export erfolgreich erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen: ${error.message}`);
    },
  });
}

export function useToggleScheduledExport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ exportId, active }: { exportId: string; active: boolean }) =>
      toggleScheduledExport(exportId, active),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: scheduledExportKeys.all });
      toast.success(
        variables.active ? 'Export aktiviert' : 'Export deaktiviert'
      );
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

export function useRunScheduledExportNow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (exportId: string) => runScheduledExportNow(exportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduledExportKeys.all });
      toast.success('Export wird ausgefuehrt...');
    },
    onError: (error: Error) => {
      toast.error(`Fehler bei der Ausfuehrung: ${error.message}`);
    },
  });
}

export function useDeleteScheduledExport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (exportId: string) => deleteScheduledExport(exportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scheduledExportKeys.all });
      toast.success('Geplanter Export geloescht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Loeschen: ${error.message}`);
    },
  });
}
