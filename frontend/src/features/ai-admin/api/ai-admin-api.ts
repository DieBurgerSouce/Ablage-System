/**
 * AI Admin API Client
 *
 * API-Funktionen fuer AI Autonomy Verwaltung.
 */

import { apiClient as api } from '@/lib/api/client';
import type {
  ThresholdConfig,
  ThresholdUpdateRequest,
  Decision,
  ReviewRequest,
  AccuracyStats,
  ThresholdSuggestion,
  PendingReviewCount,
  LearningProgressReport,
  DecisionType,
} from '../types';

const BASE_URL = '/ai';

// =============================================================================
// Threshold Management
// =============================================================================

export async function listThresholds(): Promise<ThresholdConfig[]> {
  const response = await api.get<ThresholdConfig[]>(`${BASE_URL}/thresholds`);
  return response.data;
}

export async function updateThreshold(
  decisionType: DecisionType,
  data: ThresholdUpdateRequest
): Promise<{ success: boolean; message: string }> {
  const response = await api.put<{ success: boolean; message: string }>(
    `${BASE_URL}/thresholds/${decisionType}`,
    data
  );
  return response.data;
}

// =============================================================================
// Decision Management
// =============================================================================

export async function listDecisions(params: {
  decision_type?: DecisionType;
  requires_review?: boolean;
  limit?: number;
  offset?: number;
}): Promise<Decision[]> {
  const response = await api.get<Decision[]>(`${BASE_URL}/decisions`, {
    params,
  });
  return response.data;
}

export async function getDecision(decisionId: string): Promise<Decision> {
  const response = await api.get<Decision>(`${BASE_URL}/decisions/${decisionId}`);
  return response.data;
}

export async function reviewDecision(
  decisionId: string,
  request: ReviewRequest
): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(
    `${BASE_URL}/decisions/${decisionId}/review`,
    request
  );
  return response.data;
}

export async function getPendingReviewCount(): Promise<PendingReviewCount> {
  const response = await api.get<PendingReviewCount>(
    `${BASE_URL}/pending-review-count`
  );
  return response.data;
}

// =============================================================================
// Statistics
// =============================================================================

export async function getAccuracyStats(days: number = 30): Promise<AccuracyStats[]> {
  const response = await api.get<AccuracyStats[]>(`${BASE_URL}/stats/accuracy`, {
    params: { days },
  });
  return response.data;
}

export async function getLearningProgress(
  days: number = 30
): Promise<LearningProgressReport> {
  const response = await api.get<LearningProgressReport>(
    `${BASE_URL}/stats/learning`,
    {
      params: { days },
    }
  );
  return response.data;
}

export async function getThresholdSuggestions(
  days: number = 30
): Promise<ThresholdSuggestion[]> {
  const response = await api.get<ThresholdSuggestion[]>(
    `${BASE_URL}/stats/threshold-suggestions`,
    {
      params: { days },
    }
  );
  return response.data;
}

export async function applyThresholdSuggestion(
  decisionType: DecisionType
): Promise<{ success: boolean; message: string }> {
  const response = await api.post<{ success: boolean; message: string }>(
    `${BASE_URL}/stats/threshold-suggestions/${decisionType}/apply`
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const aiAdminKeys = {
  all: ['ai-admin'] as const,
  thresholds: () => [...aiAdminKeys.all, 'thresholds'] as const,
  decisions: (filters?: {
    decision_type?: DecisionType;
    requires_review?: boolean;
    limit?: number;
    offset?: number;
  }) => [...aiAdminKeys.all, 'decisions', filters] as const,
  decision: (id: string) => [...aiAdminKeys.all, 'decision', id] as const,
  pendingCount: () => [...aiAdminKeys.all, 'pending-count'] as const,
  accuracyStats: (days: number) =>
    [...aiAdminKeys.all, 'accuracy-stats', days] as const,
  learningProgress: (days: number) =>
    [...aiAdminKeys.all, 'learning-progress', days] as const,
  thresholdSuggestions: (days: number) =>
    [...aiAdminKeys.all, 'threshold-suggestions', days] as const,
};
