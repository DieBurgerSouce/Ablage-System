/**
 * TanStack Query hooks for Autonomous Trust System
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autonomousApi } from '../api/autonomous-api';
import type {
  UpdateTrustLevelRequest,
  RejectProposalRequest,
  PendingApprovalsFilters,
  ProposalHistoryFilters,
} from '../types/autonomous-types';

// Query key factory
export const autonomousKeys = {
  all: ['autonomous'] as const,
  trustLevel: () => [...autonomousKeys.all, 'trust-level'] as const,
  trustMetrics: (days?: number) => [...autonomousKeys.all, 'trust-metrics', days] as const,
  trustRecommendation: () => [...autonomousKeys.all, 'trust-recommendation'] as const,
  trustLevels: () => [...autonomousKeys.all, 'trust-levels'] as const,
  pendingApprovals: (filters?: PendingApprovalsFilters) =>
    [...autonomousKeys.all, 'pending-approvals', filters] as const,
  history: (filters?: ProposalHistoryFilters) =>
    [...autonomousKeys.all, 'history', filters] as const,
  statistics: (days?: number) => [...autonomousKeys.all, 'statistics', days] as const,
};

// Queries
export function useTrustLevel() {
  return useQuery({
    queryKey: autonomousKeys.trustLevel(),
    queryFn: autonomousApi.getTrustLevel,
    staleTime: 30000, // 30 seconds
  });
}

export function useTrustMetrics(days: number = 30) {
  return useQuery({
    queryKey: autonomousKeys.trustMetrics(days),
    queryFn: () => autonomousApi.getTrustMetrics(days),
    staleTime: 60000, // 1 minute
  });
}

export function useTrustRecommendation() {
  return useQuery({
    queryKey: autonomousKeys.trustRecommendation(),
    queryFn: autonomousApi.getTrustRecommendation,
    staleTime: 60000, // 1 minute
  });
}

export function useTrustLevels() {
  return useQuery({
    queryKey: autonomousKeys.trustLevels(),
    queryFn: autonomousApi.listTrustLevels,
    staleTime: 300000, // 5 minutes
  });
}

export function usePendingApprovals(filters?: PendingApprovalsFilters) {
  return useQuery({
    queryKey: autonomousKeys.pendingApprovals(filters),
    queryFn: () => autonomousApi.getPendingApprovals(filters),
    staleTime: 10000, // 10 seconds
    refetchInterval: 30000, // Auto-refetch every 30 seconds
  });
}

export function useProposalHistory(filters?: ProposalHistoryFilters) {
  return useQuery({
    queryKey: autonomousKeys.history(filters),
    queryFn: () => autonomousApi.getHistory(filters),
    staleTime: 30000, // 30 seconds
  });
}

export function useProposalStatistics(days: number = 30) {
  return useQuery({
    queryKey: autonomousKeys.statistics(days),
    queryFn: () => autonomousApi.getStatistics(days),
    staleTime: 60000, // 1 minute
  });
}

// Mutations
export function useUpdateTrustLevel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UpdateTrustLevelRequest) => autonomousApi.updateTrustLevel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autonomousKeys.trustLevel() });
      queryClient.invalidateQueries({ queryKey: autonomousKeys.trustRecommendation() });
    },
  });
}

export function useApproveProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: string) => autonomousApi.approveProposal(proposalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autonomousKeys.all });
    },
  });
}

export function useRejectProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ proposalId, data }: { proposalId: string; data?: RejectProposalRequest }) =>
      autonomousApi.rejectProposal(proposalId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autonomousKeys.all });
    },
  });
}

export function useRollbackProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: string) => autonomousApi.rollbackProposal(proposalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: autonomousKeys.all });
    },
  });
}
