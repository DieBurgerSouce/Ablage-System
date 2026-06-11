/**
 * OCR Feedback React Query Hooks
 *
 * Hooks für Leaderboard, Statistiken, Queue und Korrekturen.
 */

import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { getLeaderboard, getUserStats, getUserStatsById, getCorrectionQueue, claimQueueItem, submitCorrection, submitBatchCorrections, getAchievements, type LeaderboardPeriod, type QueuePriority, type CorrectionRequest } from '../api/ocr-feedback-api';

// ==================== Query Keys ====================

export const ocrFeedbackKeys = {
  all: ['ocr-feedback'] as const,
  leaderboard: (period: LeaderboardPeriod) => [...ocrFeedbackKeys.all, 'leaderboard', period] as const,
  userStats: () => [...ocrFeedbackKeys.all, 'user-stats'] as const,
  userStatsById: (userId: string) => [...ocrFeedbackKeys.all, 'user-stats', userId] as const,
  queue: (priority?: QueuePriority, documentType?: string) =>
    [...ocrFeedbackKeys.all, 'queue', priority, documentType] as const,
  achievements: () => [...ocrFeedbackKeys.all, 'achievements'] as const,
};

// ==================== Leaderboard Hooks ====================

/**
 * Hook für Leaderboard
 */
export function useLeaderboard(period: LeaderboardPeriod = 'weekly', limit: number = 10) {
  return useQuery({
    queryKey: ocrFeedbackKeys.leaderboard(period),
    queryFn: () => getLeaderboard(period, limit),
    staleTime: 30 * 1000, // 30 Sekunden
    refetchInterval: 60 * 1000, // Jede Minute
  });
}

// ==================== User Stats Hooks ====================

/**
 * Hook für eigene Statistiken
 */
export function useUserStats() {
  return useQuery({
    queryKey: ocrFeedbackKeys.userStats(),
    queryFn: getUserStats,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

/**
 * Hook für Statistiken eines bestimmten Benutzers
 */
export function useUserStatsById(userId: string | undefined) {
  return useQuery({
    queryKey: ocrFeedbackKeys.userStatsById(userId || ''),
    queryFn: () => getUserStatsById(userId!),
    enabled: !!userId,
    staleTime: 30 * 1000,
  });
}

// ==================== Queue Hooks ====================

/**
 * Hook für Korrektur-Queue
 */
export function useCorrectionQueue(params?: {
  priority?: QueuePriority;
  document_type?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ocrFeedbackKeys.queue(params?.priority, params?.document_type),
    queryFn: () => getCorrectionQueue(params),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

/**
 * Hook für Korrektur-Queue mit Infinite Scroll
 */
export function useCorrectionQueueInfinite(params?: {
  priority?: QueuePriority;
  document_type?: string;
  limit?: number;
}) {
  const limit = params?.limit || 20;

  return useInfiniteQuery({
    queryKey: [...ocrFeedbackKeys.queue(params?.priority, params?.document_type), 'infinite'],
    queryFn: ({ pageParam = 0 }) =>
      getCorrectionQueue({
        ...params,
        limit,
        offset: pageParam,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const totalLoaded = allPages.reduce((sum, page) => sum + page.items.length, 0);
      if (totalLoaded >= lastPage.total) return undefined;
      return totalLoaded;
    },
    staleTime: 30 * 1000,
  });
}

/**
 * Mutation Hook zum Reservieren eines Queue-Items
 */
export function useClaimQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => claimQueueItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ocrFeedbackKeys.all });
    },
  });
}

// ==================== Correction Hooks ====================

/**
 * Mutation Hook zum Einreichen einer Korrektur
 */
export function useSubmitCorrection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: CorrectionRequest) => submitCorrection(request),
    onSuccess: () => {
      // Invalidate alle relevanten Queries
      queryClient.invalidateQueries({ queryKey: ocrFeedbackKeys.all });
    },
  });
}

/**
 * Mutation Hook zum Einreichen von Batch-Korrekturen
 */
export function useSubmitBatchCorrections() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (corrections: CorrectionRequest[]) => submitBatchCorrections(corrections),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ocrFeedbackKeys.all });
    },
  });
}

// ==================== Achievements Hooks ====================

/**
 * Hook für Achievements
 */
export function useAchievements() {
  return useQuery({
    queryKey: ocrFeedbackKeys.achievements(),
    queryFn: getAchievements,
    staleTime: 60 * 1000,
  });
}
