/**
 * API client for Autonomous Trust System
 */

import type {
  TrustLevelResponse,
  TrustMetricsResponse,
  TrustRecommendationResponse,
  PendingApprovalResponse,
  ProposalHistoryResponse,
  ProposalStatistics,
  UpdateTrustLevelRequest,
  ApproveProposalResponse,
  RejectProposalRequest,
  RollbackProposalResponse,
  PendingApprovalsFilters,
  ProposalHistoryFilters,
} from '../types/autonomous-types';

const API_BASE = '/api/v1/autonomous';

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      detail: 'Unbekannter Fehler',
    }));
    throw new Error(error.detail || `API Fehler: ${response.status}`);
  }

  return response.json();
}

export const autonomousApi = {
  getTrustLevel: async (): Promise<TrustLevelResponse> => {
    return apiRequest<TrustLevelResponse>('/trust-level');
  },

  updateTrustLevel: async (
    data: UpdateTrustLevelRequest
  ): Promise<TrustLevelResponse> => {
    return apiRequest<TrustLevelResponse>('/trust-level', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  getTrustMetrics: async (days: number = 30): Promise<TrustMetricsResponse> => {
    return apiRequest<TrustMetricsResponse>(`/trust-level/metrics?days=${days}`);
  },

  getTrustRecommendation: async (): Promise<TrustRecommendationResponse> => {
    return apiRequest<TrustRecommendationResponse>('/trust-level/recommendation');
  },

  listTrustLevels: async (): Promise<TrustLevelResponse[]> => {
    return apiRequest<TrustLevelResponse[]>('/trust-level/levels');
  },

  getPendingApprovals: async (
    filters: PendingApprovalsFilters = {}
  ): Promise<PendingApprovalResponse[]> => {
    const params = new URLSearchParams();
    if (filters.proposal_type) params.append('proposal_type', filters.proposal_type);
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters.offset !== undefined) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = queryString ? `/pending-approvals?${queryString}` : '/pending-approvals';
    return apiRequest<PendingApprovalResponse[]>(endpoint);
  },

  approveProposal: async (proposalId: string): Promise<ApproveProposalResponse> => {
    return apiRequest<ApproveProposalResponse>(`/approve/${proposalId}`, {
      method: 'POST',
    });
  },

  rejectProposal: async (
    proposalId: string,
    data?: RejectProposalRequest
  ): Promise<void> => {
    await apiRequest<void>(`/reject/${proposalId}`, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  },

  rollbackProposal: async (proposalId: string): Promise<RollbackProposalResponse> => {
    return apiRequest<RollbackProposalResponse>(`/rollback/${proposalId}`, {
      method: 'POST',
    });
  },

  getHistory: async (
    filters: ProposalHistoryFilters = {}
  ): Promise<ProposalHistoryResponse[]> => {
    const params = new URLSearchParams();
    if (filters.target_id) params.append('target_id', filters.target_id);
    if (filters.proposal_type) params.append('proposal_type', filters.proposal_type);
    if (filters.status) params.append('status', filters.status);
    if (filters.days !== undefined) params.append('days', filters.days.toString());
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());

    const queryString = params.toString();
    const endpoint = queryString ? `/history?${queryString}` : '/history';
    return apiRequest<ProposalHistoryResponse[]>(endpoint);
  },

  getStatistics: async (days: number = 30): Promise<ProposalStatistics> => {
    return apiRequest<ProposalStatistics>(`/statistics?days=${days}`);
  },
};
