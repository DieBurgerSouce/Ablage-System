/**
 * Smart Inbox API Service
 *
 * Kommuniziert mit den /api/v1/smart-inbox Endpoints
 * für priorisierte Inbox-Items, Actions und AI-Insights.
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type { SmartInboxItemBackend, SmartInboxItemResponse, InboxListResponseBackend, InboxListResponse, InboxActionRequest, InsightsResponseBackend, InsightsResponse, AIInsightBackend, AIInsightResponse, InboxStatsBackend, InboxStatsResponse, AggregationResponseBackend, AggregationResponse, InboxFilter, InboxActionType } from '../types/smart-inbox-types';

// ==================== Error Classes ====================

export class SmartInboxApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'SmartInboxApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformSmartInboxItem(item: SmartInboxItemBackend): SmartInboxItemResponse {
  return {
    id: item.id,
    sourceType: item.source_type,
    sourceId: item.source_id,
    title: item.title,
    description: item.description,
    category: item.category,
    rawPriority: item.raw_priority,
    mlPriority: item.ml_priority,
    status: item.status,
    deadline: item.deadline,
    recommendedActions: item.recommended_actions ?? [],
    contextData: item.context_data ?? {},
    documentId: item.document_id,
    entityId: item.entity_id,
    createdAt: item.created_at,
  };
}

function transformInboxListResponse(response: InboxListResponseBackend): InboxListResponse {
  return {
    items: response.items.map(transformSmartInboxItem),
    total: response.total,
    hasMore: response.has_more,
  };
}

function transformAIInsight(insight: AIInsightBackend): AIInsightResponse {
  return {
    title: insight.title,
    description: insight.description,
    metric: insight.metric,
    value: insight.value,
    trend: insight.trend,
  };
}

function transformInsightsResponse(response: InsightsResponseBackend): InsightsResponse {
  return {
    insights: response.insights.map(transformAIInsight),
  };
}

function transformInboxStats(stats: InboxStatsBackend): InboxStatsResponse {
  return {
    total: stats.total,
    pending: stats.pending,
    inProgress: stats.in_progress,
    completedToday: stats.completed_today,
    dismissedToday: stats.dismissed_today,
    avgResponseTimeMs: stats.avg_response_time_ms,
    byCategory: stats.by_category,
    bySource: stats.by_source,
  };
}

function transformAggregationResponse(response: AggregationResponseBackend): AggregationResponse {
  return {
    message: response.message,
    taskId: response.task_id,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new SmartInboxApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 409) {
      throw new SmartInboxApiError(`${context}: ${message}`, 409, error);
    }

    if (statusCode === 400) {
      throw new SmartInboxApiError(`${context}: ${message}`, 400, error);
    }

    throw new SmartInboxApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new SmartInboxApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Smart Inbox Service ====================

export const smartInboxService = {
  /**
   * Ruft priorisierte Inbox-Items ab
   */
  getItems: async (params?: InboxFilter): Promise<InboxListResponse> => {
    try {
      const queryParams: Record<string, string | number> = {};

      if (params?.limit !== undefined) queryParams.limit = params.limit;
      if (params?.offset !== undefined) queryParams.offset = params.offset;
      if (params?.status) queryParams.status = params.status;
      if (params?.category) queryParams.category = params.category;

      const response = await apiClient.get<InboxListResponseBackend>(
        '/smart-inbox',
        { params: queryParams }
      );

      return transformInboxListResponse(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { items: [], total: 0, hasMore: false };
      }
      handleApiError(error, 'Inbox-Items laden');
    }
  },

  /**
   * Führt eine Action auf einem Inbox-Item aus
   */
  performAction: async (
    itemId: string,
    action: InboxActionType,
    data?: Record<string, unknown>
  ): Promise<void> => {
    try {
      const payload: InboxActionRequest = {
        action,
        data,
      };

      await apiClient.post(`/smart-inbox/${itemId}/act`, payload);
    } catch (error) {
      handleApiError(error, 'Action ausführen');
    }
  },

  /**
   * Snoozt ein Inbox-Item
   */
  snoozeItem: async (itemId: string, snoozeUntil: string): Promise<void> => {
    try {
      const payload: { snooze_until: string } = {
        snooze_until: snoozeUntil,
      };

      await apiClient.post(`/smart-inbox/${itemId}/snooze`, payload);
    } catch (error) {
      handleApiError(error, 'Item snoozen');
    }
  },

  /**
   * Dismisst ein Inbox-Item
   */
  dismissItem: async (itemId: string): Promise<void> => {
    try {
      await apiClient.post(`/smart-inbox/${itemId}/dismiss`);
    } catch (error) {
      handleApiError(error, 'Item verwerfen');
    }
  },

  /**
   * Ruft AI-generierte Insights ab
   */
  getInsights: async (): Promise<InsightsResponse> => {
    try {
      const response = await apiClient.get<InsightsResponseBackend>(
        '/smart-inbox/insights'
      );

      return transformInsightsResponse(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { insights: [] };
      }
      handleApiError(error, 'Insights laden');
    }
  },

  /**
   * Triggert manuelle Aggregation
   */
  triggerAggregation: async (): Promise<AggregationResponse> => {
    try {
      const response = await apiClient.post<AggregationResponseBackend>(
        '/smart-inbox/aggregate'
      );

      return transformAggregationResponse(response.data);
    } catch (error) {
      handleApiError(error, 'Aggregation starten');
    }
  },

  /**
   * Ruft Inbox-Statistiken ab
   */
  getStats: async (): Promise<InboxStatsResponse> => {
    try {
      const response = await apiClient.get<InboxStatsBackend>(
        '/smart-inbox/stats'
      );

      return transformInboxStats(response.data);
    } catch (error) {
      handleApiError(error, 'Statistiken laden');
    }
  },
};
