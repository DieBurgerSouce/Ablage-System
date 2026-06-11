// Proactive Assistant API Service

import { apiClient } from '@/lib/api/client';
import type {
  DashboardSummaryResponse,
  HintListResponse,
  HintResponse,
  StatisticsResponse,
  HintRuleResponse,
  HintStatus,
  HintCategory,
  HintPriority,
} from '../types/proactive-assistant-types';

// ============================================================================
// Error Class
// ============================================================================

export class ProactiveAssistantApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'ProactiveAssistantApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ============================================================================
// API Service
// ============================================================================

export const proactiveAssistantApi = {
  /**
   * Get dashboard summary with hint counts by category
   */
  async getDashboard(): Promise<DashboardSummaryResponse> {
    try {
      const response = await apiClient.get<DashboardSummaryResponse>(
        '/proactive-assistant/dashboard'
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Laden des Dashboards',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Get filtered hint list with pagination
   */
  async getHints(params?: {
    category?: HintCategory;
    priority?: HintPriority;
    status?: HintStatus;
    limit?: number;
    offset?: number;
  }): Promise<HintListResponse> {
    try {
      const response = await apiClient.get<HintListResponse>(
        '/proactive-assistant/hints',
        { params }
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Laden der Hinweise',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Update hint status
   */
  async updateHintStatus(
    hintId: string,
    status: HintStatus
  ): Promise<HintResponse> {
    try {
      const response = await apiClient.patch<HintResponse>(
        `/proactive-assistant/hints/${hintId}/status`,
        { status }
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Aktualisieren des Status',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Get context hints for specific entity
   */
  async getContextHints(params: {
    entity_type: string;
    entity_id: string;
  }): Promise<HintResponse[]> {
    try {
      const response = await apiClient.get<HintResponse[]>(
        '/proactive-assistant/hints/context',
        { params }
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Laden der kontextbezogenen Hinweise',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Get statistics
   */
  async getStatistics(): Promise<StatisticsResponse> {
    try {
      const response = await apiClient.get<StatisticsResponse>(
        '/proactive-assistant/statistics'
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Laden der Statistiken',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Generate new hints
   */
  async generateHints(): Promise<{ message: string; hints_generated: number }> {
    try {
      const response = await apiClient.post<{
        message: string;
        hints_generated: number;
      }>('/proactive-assistant/generate');
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Generieren der Hinweise',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Get all hint rules
   */
  async getRules(): Promise<HintRuleResponse[]> {
    try {
      const response = await apiClient.get<HintRuleResponse[]>(
        '/proactive-assistant/rules'
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Laden der Regeln',
        axiosError?.response?.status,
        error
      );
    }
  },

  /**
   * Update a hint rule
   */
  async updateRule(
    ruleId: string,
    data: {
      name?: string;
      enabled?: boolean;
      conditions?: Record<string, unknown>;
      template?: string;
      priority?: HintPriority;
    }
  ): Promise<HintRuleResponse> {
    try {
      const response = await apiClient.put<HintRuleResponse>(
        `/proactive-assistant/rules/${ruleId}`,
        data
      );
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { status: number } };
      throw new ProactiveAssistantApiError(
        'Fehler beim Aktualisieren der Regel',
        axiosError?.response?.status,
        error
      );
    }
  },
};
