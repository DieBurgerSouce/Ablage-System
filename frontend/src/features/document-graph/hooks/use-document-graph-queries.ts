/**
 * Document Graph Query Hooks
 *
 * TanStack Query Hooks fuer Dokumenten-Graph und Timeline.
 * Folgt dem Query Key Factory Pattern.
 */

import { useQuery } from '@tanstack/react-query';
import { QUERY_STANDARD, QUERY_VOLATILE } from '@/lib/api/query-config';
import { documentGraphApi } from '../api/document-graph-api';
import { lineageService } from '@/lib/api/services/lineage';
import type { LineageEventType } from '@/lib/api/services/lineage';

// ==================== Query Keys ====================

export const documentGraphKeys = {
  all: ['document-graph'] as const,
  chains: () => [...documentGraphKeys.all, 'chains'] as const,
  chain: (chainId: string) => [...documentGraphKeys.chains(), chainId] as const,
  chainByDocument: (documentId: string) =>
    [...documentGraphKeys.all, 'chain-by-document', documentId] as const,
  entityChains: (entityId: string) =>
    [...documentGraphKeys.chains(), 'entity', entityId] as const,
  timeline: (documentId: string) =>
    [...documentGraphKeys.all, 'timeline', documentId] as const,
  lineageStats: (documentId: string) =>
    [...documentGraphKeys.all, 'lineage-stats', documentId] as const,
  eventTypes: () => [...documentGraphKeys.all, 'event-types'] as const,
} as const;

// ==================== Chain Hooks ====================

export function useDocumentChain(chainId: string | null) {
  return useQuery({
    queryKey: documentGraphKeys.chain(chainId ?? ''),
    queryFn: () => documentGraphApi.getChain(chainId!),
    enabled: !!chainId,
    ...QUERY_STANDARD,
  });
}

export function useChainByDocument(documentId: string | null) {
  return useQuery({
    queryKey: documentGraphKeys.chainByDocument(documentId ?? ''),
    queryFn: () => documentGraphApi.getChainByDocument(documentId!),
    enabled: !!documentId,
    ...QUERY_STANDARD,
  });
}

export function useEntityChains(entityId: string | null, limit = 50) {
  return useQuery({
    queryKey: documentGraphKeys.entityChains(entityId ?? ''),
    queryFn: () => documentGraphApi.getChainsByEntity({ entityId: entityId!, limit }),
    enabled: !!entityId,
    ...QUERY_VOLATILE,
  });
}

// ==================== Timeline/Lineage Hooks ====================

export function useDocumentTimeline(
  documentId: string | null,
  params?: { limit?: number; offset?: number; eventTypes?: LineageEventType[] }
) {
  return useQuery({
    queryKey: documentGraphKeys.timeline(documentId ?? ''),
    queryFn: () => lineageService.getTimeline(documentId!, params),
    enabled: !!documentId,
    ...QUERY_STANDARD,
  });
}

export function useDocumentLineageStats(documentId: string | null) {
  return useQuery({
    queryKey: documentGraphKeys.lineageStats(documentId ?? ''),
    queryFn: () => lineageService.getStats(documentId!),
    enabled: !!documentId,
    ...QUERY_STANDARD,
  });
}

export function useLineageEventTypes() {
  return useQuery({
    queryKey: documentGraphKeys.eventTypes(),
    queryFn: () => lineageService.getEventTypes(),
    staleTime: 60 * 60 * 1000, // 1h - selten aendernd
    gcTime: 2 * 60 * 60 * 1000,
  });
}
