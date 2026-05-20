// Smart Dashboard API Service
// All backend calls with German error messages

import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';
import {
  BackendKPIData,
  BackendTabData,
  BackendWidgetData,
  BackendDocumentProgress,
  BackendBatchProgress,
  BackendTrendData,
  DashboardTabKey,
  WidgetLayout,
} from '../types/smart-dashboard-types';

// ============================================================================
// ERROR MESSAGES (German)
// ============================================================================

const ERROR_MESSAGES = {
  FETCH_KPIS_FAILED: 'Fehler beim Laden der KPI-Daten',
  FETCH_TAB_FAILED: 'Fehler beim Laden der Tab-Daten',
  FETCH_WIDGETS_FAILED: 'Fehler beim Laden der Widget-Konfiguration',
  SAVE_LAYOUT_FAILED: 'Fehler beim Speichern des Layouts',
  FETCH_TRENDS_FAILED: 'Fehler beim Laden der Trend-Daten',
  FETCH_PROGRESS_FAILED: 'Fehler beim Laden des Fortschritts',
  FETCH_BATCH_PROGRESS_FAILED: 'Fehler beim Laden des Batch-Fortschritts',
} as const;

// ============================================================================
// API SERVICE
// ============================================================================

export const smartDashboardApi = {
  /**
   * Get real-time KPI values
   */
  async getKPIs(): Promise<BackendKPIData[]> {
    try {
      const response = await apiClient.get<BackendKPIData[]>('/smart-dashboard/kpis');
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch KPIs:', error);
      throw new Error(ERROR_MESSAGES.FETCH_KPIS_FAILED);
    }
  },

  /**
   * Get tab-specific data
   * @param tab - Dashboard tab key ('uebersicht' | 'finanzen' | 'dokumente' | 'workflows' | 'system')
   * @param role - Optional user role for filtering
   */
  async getTabData(tab: DashboardTabKey, role?: string): Promise<BackendTabData> {
    try {
      const params = role ? { role } : undefined;
      const response = await apiClient.get<BackendTabData>(`/smart-dashboard/tabs/${tab}`, { params });
      return response.data;
    } catch (error) {
      logger.error(`Failed to fetch tab data for ${tab}:`, error);
      throw new Error(ERROR_MESSAGES.FETCH_TAB_FAILED);
    }
  },

  /**
   * Get role-based widget list
   * @param role - User role for widget filtering
   */
  async getWidgets(role?: string): Promise<BackendWidgetData[]> {
    try {
      const params = role ? { role } : undefined;
      const response = await apiClient.get<BackendWidgetData[]>('/smart-dashboard/widgets', { params });
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch widgets:', error);
      throw new Error(ERROR_MESSAGES.FETCH_WIDGETS_FAILED);
    }
  },

  /**
   * Save custom widget layout
   * @param layout - Array of widget positions
   */
  async saveLayout(layout: WidgetLayout[]): Promise<void> {
    try {
      await apiClient.put('/smart-dashboard/layout', { layout });
    } catch (error) {
      logger.error('Failed to save layout:', error);
      throw new Error(ERROR_MESSAGES.SAVE_LAYOUT_FAILED);
    }
  },

  /**
   * Get KPI trend data for sparklines
   * @param kpiKey - KPI identifier
   */
  async getTrends(kpiKey?: string): Promise<BackendTrendData[]> {
    try {
      const params = kpiKey ? { kpi_key: kpiKey } : undefined;
      const response = await apiClient.get<BackendTrendData[]>('/smart-dashboard/trends', { params });
      return response.data;
    } catch (error) {
      logger.error('Failed to fetch trends:', error);
      throw new Error(ERROR_MESSAGES.FETCH_TRENDS_FAILED);
    }
  },

  /**
   * Get document progress (DHL-style tracking)
   * @param documentId - Document ID
   */
  async getDocumentProgress(documentId: number): Promise<BackendDocumentProgress> {
    try {
      const response = await apiClient.get<BackendDocumentProgress>(
        `/smart-dashboard/progress/${documentId}`
      );
      return response.data;
    } catch (error) {
      logger.error(`Failed to fetch progress for document ${documentId}:`, error);
      throw new Error(ERROR_MESSAGES.FETCH_PROGRESS_FAILED);
    }
  },

  /**
   * Get batch processing progress
   * @param batchId - Batch identifier
   */
  async getBatchProgress(batchId: string): Promise<BackendBatchProgress> {
    try {
      const response = await apiClient.get<BackendBatchProgress>(
        '/smart-dashboard/progress/batch',
        { params: { batch_id: batchId } }
      );
      return response.data;
    } catch (error) {
      logger.error(`Failed to fetch batch progress for ${batchId}:`, error);
      throw new Error(ERROR_MESSAGES.FETCH_BATCH_PROGRESS_FAILED);
    }
  },
};
