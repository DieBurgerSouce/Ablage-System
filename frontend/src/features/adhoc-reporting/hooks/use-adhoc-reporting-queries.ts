/**
 * Ad-Hoc Reporting React Query Hooks
 * German Enterprise Document Platform
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adhocReportingApi } from '../api/adhoc-reporting-api';
import type {
  CreateReportRequest,
  UpdateReportRequest,
  ShareReportRequest,
  ScheduleReportRequest,
  UpdateScheduleRequest,
} from '../api/adhoc-reporting-api';
import type { ExportFormat } from '../types/adhoc-reporting-types';

// Query Keys
export const adhocReportingKeys = {
  all: ['adhoc-reporting'] as const,
  dataSources: () => [...adhocReportingKeys.all, 'data-sources'] as const,
  columns: (sourceKey: string) => [...adhocReportingKeys.all, 'columns', sourceKey] as const,
  reports: (filters?: { search?: string; data_source?: string }) =>
    [...adhocReportingKeys.all, 'reports', filters] as const,
  report: (reportId: number) => [...adhocReportingKeys.all, 'report', reportId] as const,
  execution: (reportId: number, params?: { limit?: number; offset?: number }) =>
    [...adhocReportingKeys.all, 'execution', reportId, params] as const,
  schedules: (filters?: { report_id?: number }) =>
    [...adhocReportingKeys.all, 'schedules', filters] as const,
};

// Data Sources
export function useDataSources() {
  return useQuery({
    queryKey: adhocReportingKeys.dataSources(),
    queryFn: () => adhocReportingApi.getDataSources(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useDataSourceColumns(sourceKey: string | null) {
  return useQuery({
    queryKey: sourceKey ? adhocReportingKeys.columns(sourceKey) : ['disabled'],
    queryFn: () => (sourceKey ? adhocReportingApi.getDataSourceColumns(sourceKey) : Promise.resolve([])),
    enabled: !!sourceKey,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Reports
export function useReports(filters?: { search?: string; data_source?: string }) {
  return useQuery({
    queryKey: adhocReportingKeys.reports(filters),
    queryFn: () => adhocReportingApi.getReports(filters),
  });
}

export function useReport(reportId: number | null) {
  return useQuery({
    queryKey: reportId ? adhocReportingKeys.report(reportId) : ['disabled'],
    queryFn: () => (reportId ? adhocReportingApi.getReport(reportId) : Promise.reject()),
    enabled: !!reportId,
  });
}

export function useCreateReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CreateReportRequest) => adhocReportingApi.createReport(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.reports() });
    },
  });
}

export function useUpdateReport(reportId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: UpdateReportRequest) => adhocReportingApi.updateReport(reportId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.report(reportId) });
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.reports() });
    },
  });
}

export function useDeleteReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reportId: number) => adhocReportingApi.deleteReport(reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.reports() });
    },
  });
}

// Execution
export function useExecuteReport(
  reportId: number | null,
  params?: { limit?: number; offset?: number },
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: reportId ? adhocReportingKeys.execution(reportId, params) : ['disabled'],
    queryFn: () => (reportId ? adhocReportingApi.executeReport(reportId, params) : Promise.reject()),
    enabled: !!reportId && (options?.enabled ?? true),
    staleTime: 0, // Always refetch
  });
}

export function useExecuteReportMutation() {
  return useMutation({
    mutationFn: ({
      reportId,
      params,
    }: {
      reportId: number;
      params?: { limit?: number; offset?: number };
    }) => adhocReportingApi.executeReport(reportId, params),
  });
}

// Export
export function useExportReport() {
  return useMutation({
    mutationFn: ({ reportId, format }: { reportId: number; format: ExportFormat }) =>
      adhocReportingApi.exportReport(reportId, format),
    onSuccess: (blob, variables) => {
      // Trigger download
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `report-${variables.reportId}.${variables.format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },
  });
}

// Sharing
export function useShareReport(reportId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ShareReportRequest) => adhocReportingApi.shareReport(reportId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.report(reportId) });
    },
  });
}

export function useRemoveShare(reportId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (shareId: number) => adhocReportingApi.removeShare(reportId, shareId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.report(reportId) });
    },
  });
}

// Scheduling
export function useSchedules(filters?: { report_id?: number }) {
  return useQuery({
    queryKey: adhocReportingKeys.schedules(filters),
    queryFn: () => adhocReportingApi.getSchedules(filters),
  });
}

export function useScheduleReport(reportId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ScheduleReportRequest) => adhocReportingApi.scheduleReport(reportId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.schedules() });
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.schedules({ report_id: reportId }) });
    },
  });
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ scheduleId, request }: { scheduleId: number; request: UpdateScheduleRequest }) =>
      adhocReportingApi.updateSchedule(scheduleId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.schedules() });
    },
  });
}

export function useDeleteSchedule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (scheduleId: number) => adhocReportingApi.deleteSchedule(scheduleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adhocReportingKeys.schedules() });
    },
  });
}
