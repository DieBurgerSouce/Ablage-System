/**
 * Ad-Hoc Reporting API Service
 * German Enterprise Document Platform
 */

import { apiClient } from '@/lib/api/client';
import type {
  DataSource,
  Column,
  ReportDefinition,
  ExecutionResult,
  ShareInfo,
  Schedule,
  ExportFormat,
} from '../types/adhoc-reporting-types';

const BASE_PATH = '/reports/adhoc';

export interface CreateReportRequest {
  name: string;
  description?: string;
  data_source: string;
  columns: string[];
  filters?: Array<{ field: string; operator: string; value: unknown }>;
  group_by?: string[];
  aggregations?: Array<{ field: string; function: string; alias?: string }>;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  limit?: number;
}

export interface UpdateReportRequest extends Partial<CreateReportRequest> {}

export interface ShareReportRequest {
  user_ids: number[];
  permission: 'read' | 'write';
}

export interface ScheduleReportRequest {
  frequency: 'daily' | 'weekly' | 'monthly';
  time: string;
  recipients: string[];
  active?: boolean;
}

export interface UpdateScheduleRequest extends Partial<ScheduleReportRequest> {}

export const adhocReportingApi = {
  // Data Sources
  async getDataSources(): Promise<DataSource[]> {
    try {
      const response = await apiClient.get<DataSource[]>(`${BASE_PATH}/data-sources`);
      return response.data;
    } catch (error) {
      throw new Error('Datenquellen konnten nicht geladen werden');
    }
  },

  async getDataSourceColumns(sourceKey: string): Promise<Column[]> {
    try {
      const response = await apiClient.get<Column[]>(`${BASE_PATH}/data-sources/${sourceKey}/columns`);
      return response.data;
    } catch (error) {
      throw new Error('Spalten konnten nicht geladen werden');
    }
  },

  // Report CRUD
  async createReport(request: CreateReportRequest): Promise<ReportDefinition> {
    try {
      const response = await apiClient.post<ReportDefinition>(BASE_PATH, request);
      return response.data;
    } catch (error) {
      throw new Error('Report konnte nicht erstellt werden');
    }
  },

  async getReports(params?: { search?: string; data_source?: string }): Promise<ReportDefinition[]> {
    try {
      const response = await apiClient.get<ReportDefinition[]>(BASE_PATH, { params });
      return response.data;
    } catch (error) {
      throw new Error('Reports konnten nicht geladen werden');
    }
  },

  async getReport(reportId: number): Promise<ReportDefinition> {
    try {
      const response = await apiClient.get<ReportDefinition>(`${BASE_PATH}/${reportId}`);
      return response.data;
    } catch (error) {
      throw new Error('Report konnte nicht geladen werden');
    }
  },

  async updateReport(reportId: number, request: UpdateReportRequest): Promise<ReportDefinition> {
    try {
      const response = await apiClient.put<ReportDefinition>(`${BASE_PATH}/${reportId}`, request);
      return response.data;
    } catch (error) {
      throw new Error('Report konnte nicht aktualisiert werden');
    }
  },

  async deleteReport(reportId: number): Promise<void> {
    try {
      await apiClient.delete(`${BASE_PATH}/${reportId}`);
    } catch (error) {
      throw new Error('Report konnte nicht gelöscht werden');
    }
  },

  // Execution
  async executeReport(reportId: number, params?: { limit?: number; offset?: number }): Promise<ExecutionResult> {
    try {
      const response = await apiClient.post<ExecutionResult>(`${BASE_PATH}/${reportId}/execute`, params || {});
      return response.data;
    } catch (error) {
      throw new Error('Report konnte nicht ausgeführt werden');
    }
  },

  // Export
  async exportReport(reportId: number, format: ExportFormat): Promise<Blob> {
    try {
      const response = await apiClient.get(`${BASE_PATH}/${reportId}/export/${format}`, {
        responseType: 'blob',
      });
      return response.data;
    } catch (error) {
      throw new Error('Export fehlgeschlagen');
    }
  },

  // Sharing
  async shareReport(reportId: number, request: ShareReportRequest): Promise<ShareInfo[]> {
    try {
      const response = await apiClient.post<ShareInfo[]>(`${BASE_PATH}/${reportId}/share`, request);
      return response.data;
    } catch (error) {
      throw new Error('Freigabe fehlgeschlagen');
    }
  },

  async removeShare(reportId: number, shareId: number): Promise<void> {
    try {
      await apiClient.delete(`${BASE_PATH}/${reportId}/shares/${shareId}`);
    } catch (error) {
      throw new Error('Freigabe konnte nicht entfernt werden');
    }
  },

  // Scheduling
  async scheduleReport(reportId: number, request: ScheduleReportRequest): Promise<Schedule> {
    try {
      const response = await apiClient.post<Schedule>(`${BASE_PATH}/${reportId}/schedule`, request);
      return response.data;
    } catch (error) {
      throw new Error('Zeitplan konnte nicht erstellt werden');
    }
  },

  async updateSchedule(scheduleId: number, request: UpdateScheduleRequest): Promise<Schedule> {
    try {
      const response = await apiClient.put<Schedule>(`${BASE_PATH}/schedules/${scheduleId}`, request);
      return response.data;
    } catch (error) {
      throw new Error('Zeitplan konnte nicht aktualisiert werden');
    }
  },

  async deleteSchedule(scheduleId: number): Promise<void> {
    try {
      await apiClient.delete(`${BASE_PATH}/schedules/${scheduleId}`);
    } catch (error) {
      throw new Error('Zeitplan konnte nicht gelöscht werden');
    }
  },

  async getSchedules(params?: { report_id?: number }): Promise<Schedule[]> {
    try {
      const response = await apiClient.get<Schedule[]>(`${BASE_PATH}/schedules`, { params });
      return response.data;
    } catch (error) {
      throw new Error('Zeitpläne konnten nicht geladen werden');
    }
  },
};
