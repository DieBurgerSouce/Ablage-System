/**
 * Activity Timeline Hooks
 *
 * TanStack Query Hooks fuer das Activity Timeline Feature.
 */

import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import {
  getMyActivities,
  getTeamTimeline,
  getDocumentTimeline,
  getChainTimeline,
  getCompanyTimeline,
  getActivityStatistics,
  filterTimeline,
  type GetMyActivitiesParams,
  type GetTeamTimelineParams,
  type GetDocumentTimelineParams,
  type GetChainTimelineParams,
  type GetCompanyTimelineParams,
  type GetActivityStatsParams,
} from './api';
import type { TimelineFilter, ActivitySource } from './types';

// =============================================================================
// Query Keys
// =============================================================================

export const activityKeys = {
  all: ['activity'] as const,
  my: (params?: GetMyActivitiesParams) =>
    [...activityKeys.all, 'my', params] as const,
  team: (teamId: string, params?: Omit<GetTeamTimelineParams, 'teamId'>) =>
    [...activityKeys.all, 'team', teamId, params] as const,
  document: (documentId: string, params?: Omit<GetDocumentTimelineParams, 'documentId'>) =>
    [...activityKeys.all, 'document', documentId, params] as const,
  chain: (chainId: string, params?: Omit<GetChainTimelineParams, 'chainId'>) =>
    [...activityKeys.all, 'chain', chainId, params] as const,
  company: (params?: GetCompanyTimelineParams) =>
    [...activityKeys.all, 'company', params] as const,
  stats: (params?: GetActivityStatsParams) =>
    [...activityKeys.all, 'stats', params] as const,
  filtered: (filter: TimelineFilter) =>
    [...activityKeys.all, 'filtered', filter] as const,
};

// =============================================================================
// My Activities Hook
// =============================================================================

export function useMyActivities(params: GetMyActivitiesParams = {}, enabled = true) {
  return useQuery({
    queryKey: activityKeys.my(params),
    queryFn: () => getMyActivities(params),
    enabled,
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useMyActivitiesInfinite(
  params: Omit<GetMyActivitiesParams, 'offset'> = {}
) {
  const limit = params.limit ?? 20;

  return useInfiniteQuery({
    queryKey: activityKeys.my({ ...params, limit }),
    queryFn: ({ pageParam = 0 }) =>
      getMyActivities({ ...params, limit, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.hasMore) return undefined;
      return allPages.length * limit;
    },
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Team Timeline Hook
// =============================================================================

export function useTeamTimeline(
  teamId: string,
  params: Omit<GetTeamTimelineParams, 'teamId'> = {},
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.team(teamId, params),
    queryFn: () => getTeamTimeline({ teamId, ...params }),
    enabled: enabled && !!teamId,
    staleTime: 30 * 1000,
  });
}

export function useTeamTimelineInfinite(
  teamId: string,
  params: Omit<GetTeamTimelineParams, 'teamId' | 'offset'> = {}
) {
  const limit = params.limit ?? 20;

  return useInfiniteQuery({
    queryKey: activityKeys.team(teamId, { ...params, limit }),
    queryFn: ({ pageParam = 0 }) =>
      getTeamTimeline({ teamId, ...params, limit, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.hasMore) return undefined;
      return allPages.length * limit;
    },
    enabled: !!teamId,
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Document Timeline Hook
// =============================================================================

export function useDocumentTimeline(
  documentId: string,
  params: Omit<GetDocumentTimelineParams, 'documentId'> = {},
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.document(documentId, params),
    queryFn: () => getDocumentTimeline({ documentId, ...params }),
    enabled: enabled && !!documentId,
    staleTime: 30 * 1000,
  });
}

export function useDocumentTimelineInfinite(
  documentId: string,
  params: Omit<GetDocumentTimelineParams, 'documentId' | 'offset'> = {}
) {
  const limit = params.limit ?? 20;

  return useInfiniteQuery({
    queryKey: activityKeys.document(documentId, { ...params, limit }),
    queryFn: ({ pageParam = 0 }) =>
      getDocumentTimeline({ documentId, ...params, limit, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.hasMore) return undefined;
      return allPages.length * limit;
    },
    enabled: !!documentId,
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Chain Timeline Hook
// =============================================================================

export function useChainTimeline(
  chainId: string,
  params: Omit<GetChainTimelineParams, 'chainId'> = {},
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.chain(chainId, params),
    queryFn: () => getChainTimeline({ chainId, ...params }),
    enabled: enabled && !!chainId,
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Company Timeline Hook
// =============================================================================

export function useCompanyTimeline(
  params: GetCompanyTimelineParams = {},
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.company(params),
    queryFn: () => getCompanyTimeline(params),
    enabled,
    staleTime: 30 * 1000,
  });
}

export function useCompanyTimelineInfinite(
  params: Omit<GetCompanyTimelineParams, 'offset'> = {}
) {
  const limit = params.limit ?? 20;

  return useInfiniteQuery({
    queryKey: activityKeys.company({ ...params, limit }),
    queryFn: ({ pageParam = 0 }) =>
      getCompanyTimeline({ ...params, limit, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage.hasMore) return undefined;
      return allPages.length * limit;
    },
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Statistics Hook
// =============================================================================

export function useActivityStatistics(
  params: GetActivityStatsParams = {},
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.stats(params),
    queryFn: () => getActivityStatistics(params),
    enabled,
    staleTime: 60 * 1000, // 1 minute
  });
}

// =============================================================================
// Filtered Timeline Hook
// =============================================================================

export function useFilteredTimeline(
  filter: TimelineFilter,
  limit?: number,
  offset?: number,
  enabled = true
) {
  return useQuery({
    queryKey: activityKeys.filtered(filter),
    queryFn: () => filterTimeline(filter, limit, offset),
    enabled,
    staleTime: 30 * 1000,
  });
}

// =============================================================================
// Helper Hook: Activity Type Options
// =============================================================================

export function useActivityTypeOptions() {
  const options: Array<{ value: string; label: string }> = [
    { value: 'document_created', label: 'Dokument erstellt' },
    { value: 'document_uploaded', label: 'Dokument hochgeladen' },
    { value: 'document_viewed', label: 'Dokument angesehen' },
    { value: 'document_downloaded', label: 'Dokument heruntergeladen' },
    { value: 'document_edited', label: 'Dokument bearbeitet' },
    { value: 'document_deleted', label: 'Dokument geloescht' },
    { value: 'document_shared', label: 'Dokument geteilt' },
    { value: 'ocr_started', label: 'OCR gestartet' },
    { value: 'ocr_completed', label: 'OCR abgeschlossen' },
    { value: 'ocr_failed', label: 'OCR fehlgeschlagen' },
    { value: 'approval_requested', label: 'Genehmigung angefordert' },
    { value: 'approval_granted', label: 'Genehmigung erteilt' },
    { value: 'approval_rejected', label: 'Genehmigung abgelehnt' },
    { value: 'comment_added', label: 'Kommentar hinzugefuegt' },
  ];

  return options;
}

export function useActivitySourceOptions() {
  const options: Array<{ value: ActivitySource; label: string }> = [
    { value: 'document', label: 'Dokument' },
    { value: 'team', label: 'Team' },
    { value: 'chain', label: 'Vorgang' },
    { value: 'workflow', label: 'Workflow' },
    { value: 'approval', label: 'Genehmigung' },
    { value: 'comment', label: 'Kommentar' },
    { value: 'system', label: 'System' },
  ];

  return options;
}
