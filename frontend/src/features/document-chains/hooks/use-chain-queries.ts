/**
 * Document Chain React Query Hooks
 *
 * TanStack Query Hooks fuer Auftragsketten-Tracking.
 * Caching, Invalidierung und optimistic Updates.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chainService, ChainApiError } from '../api/chain-api';
import type {
  DocumentChainInfo,
  ChainDiscrepancy,
  ChainRelationship,
  ChainCreate,
  LinkDocumentsRequest,
  ResolveDiscrepancyRequest,
  ChainFilter,
} from '../types/chain-types';

// ==================== Query Keys ====================

export const chainQueryKeys = {
  all: ['chains'] as const,
  lists: () => [...chainQueryKeys.all, 'list'] as const,
  list: (filter: Partial<ChainFilter>) =>
    [...chainQueryKeys.lists(), filter] as const,
  details: () => [...chainQueryKeys.all, 'detail'] as const,
  detail: (id: string) => [...chainQueryKeys.details(), id] as const,
  discrepancies: (chainId: string) =>
    [...chainQueryKeys.detail(chainId), 'discrepancies'] as const,
  byDocument: (documentId: string) =>
    [...chainQueryKeys.all, 'by-document', documentId] as const,
  autoMatch: (documentId: string) =>
    [...chainQueryKeys.all, 'auto-match', documentId] as const,
};

// ==================== List Chains ====================

export function useChains(
  filter: Partial<ChainFilter> = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: chainQueryKeys.list(filter),
    queryFn: () => chainService.listChains(filter),
    staleTime: 30 * 1000, // 30 Sekunden
    enabled: options?.enabled ?? true,
  });
}

// ==================== Get Single Chain ====================

export function useChain(chainId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: chainQueryKeys.detail(chainId),
    queryFn: () => chainService.getChain(chainId),
    staleTime: 30 * 1000,
    enabled: (options?.enabled ?? true) && !!chainId,
  });
}

// ==================== Get Chain by Document ====================

export function useDocumentChain(
  documentId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: chainQueryKeys.byDocument(documentId),
    queryFn: () => chainService.getDocumentChain(documentId),
    staleTime: 30 * 1000,
    enabled: (options?.enabled ?? true) && !!documentId,
  });
}

// ==================== Auto-Match ====================

export function useAutoMatch(
  documentId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: chainQueryKeys.autoMatch(documentId),
    queryFn: () => chainService.autoMatch(documentId),
    staleTime: 60 * 1000, // 1 Minute
    enabled: (options?.enabled ?? false) && !!documentId,
  });
}

// ==================== Discrepancies ====================

export function useDiscrepancies(
  chainId: string,
  includeResolved: boolean = false,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: chainQueryKeys.discrepancies(chainId),
    queryFn: () => chainService.getDiscrepancies(chainId, includeResolved),
    staleTime: 30 * 1000,
    enabled: (options?.enabled ?? true) && !!chainId,
  });
}

// ==================== Create Chain ====================

export function useCreateChain() {
  const queryClient = useQueryClient();

  return useMutation<DocumentChainInfo, ChainApiError, ChainCreate>({
    mutationFn: (data) => chainService.createChain(data),
    onSuccess: (newChain) => {
      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.lists() });

      // Add to cache
      queryClient.setQueryData(
        chainQueryKeys.detail(newChain.chainId),
        newChain
      );

      // Invalidate document chain lookups for affected documents
      newChain.documents.forEach((doc) => {
        queryClient.invalidateQueries({
          queryKey: chainQueryKeys.byDocument(doc.id),
        });
      });
    },
  });
}

// ==================== Link Documents ====================

export function useLinkDocuments() {
  const queryClient = useQueryClient();

  return useMutation<ChainRelationship, ChainApiError, LinkDocumentsRequest>({
    mutationFn: (data) => chainService.linkDocuments(data),
    onSuccess: (_relationship, variables) => {
      // Invalidate chain if specified
      if (variables.chainId) {
        queryClient.invalidateQueries({
          queryKey: chainQueryKeys.detail(variables.chainId),
        });
      }

      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.lists() });

      // Invalidate document lookups
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.byDocument(variables.sourceDocumentId),
      });
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.byDocument(variables.targetDocumentId),
      });

      // Invalidate auto-match
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.autoMatch(variables.sourceDocumentId),
      });
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.autoMatch(variables.targetDocumentId),
      });
    },
  });
}

// ==================== Remove Link ====================

export function useRemoveLink() {
  const queryClient = useQueryClient();

  return useMutation<void, ChainApiError, { relationshipId: string; chainId?: string }>({
    mutationFn: ({ relationshipId }) => chainService.removeLink(relationshipId),
    onSuccess: (_data, variables) => {
      // Invalidate chain
      if (variables.chainId) {
        queryClient.invalidateQueries({
          queryKey: chainQueryKeys.detail(variables.chainId),
        });
      }

      // Invalidate lists
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.lists() });
    },
  });
}

// ==================== Resolve Discrepancy ====================

export function useResolveDiscrepancy() {
  const queryClient = useQueryClient();

  return useMutation<
    ChainDiscrepancy,
    ChainApiError,
    { discrepancyId: string; chainId: string; data: ResolveDiscrepancyRequest }
  >({
    mutationFn: ({ discrepancyId, data }) =>
      chainService.resolveDiscrepancy(discrepancyId, data),
    onSuccess: (_resolved, variables) => {
      // Invalidate chain detail
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.detail(variables.chainId),
      });

      // Invalidate discrepancies
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.discrepancies(variables.chainId),
      });

      // Invalidate lists (status may change)
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.lists() });
    },
  });
}

// ==================== Combined Hooks ====================

/**
 * Hook fuer Chain-Page mit allen noetigen Daten
 */
export function useChainPage(chainId: string) {
  const chainQuery = useChain(chainId);
  const discrepanciesQuery = useDiscrepancies(chainId, false, {
    enabled: !!chainQuery.data,
  });

  return {
    chain: chainQuery.data,
    discrepancies: discrepanciesQuery.data ?? [],
    isLoading: chainQuery.isLoading,
    isError: chainQuery.isError || discrepanciesQuery.isError,
    error: chainQuery.error || discrepanciesQuery.error,
    refetch: () => {
      chainQuery.refetch();
      discrepanciesQuery.refetch();
    },
  };
}

/**
 * Hook fuer Chain-Mutations
 */
export function useChainMutations() {
  const createChain = useCreateChain();
  const linkDocuments = useLinkDocuments();
  const removeLink = useRemoveLink();
  const resolveDiscrepancy = useResolveDiscrepancy();

  return {
    createChain,
    linkDocuments,
    removeLink,
    resolveDiscrepancy,
    isLoading:
      createChain.isPending ||
      linkDocuments.isPending ||
      removeLink.isPending ||
      resolveDiscrepancy.isPending,
  };
}

// ==================== Prefetch Hooks ====================

export function usePrefetchChain() {
  const queryClient = useQueryClient();

  return (chainId: string) => {
    queryClient.prefetchQuery({
      queryKey: chainQueryKeys.detail(chainId),
      queryFn: () => chainService.getChain(chainId),
      staleTime: 30 * 1000,
    });
  };
}

// ==================== Utility Hook ====================

export function useInvalidateChainQueries() {
  const queryClient = useQueryClient();

  return {
    invalidateAll: () =>
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.all }),
    invalidateLists: () =>
      queryClient.invalidateQueries({ queryKey: chainQueryKeys.lists() }),
    invalidateChain: (chainId: string) =>
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.detail(chainId),
      }),
    invalidateDocumentChain: (documentId: string) =>
      queryClient.invalidateQueries({
        queryKey: chainQueryKeys.byDocument(documentId),
      }),
  };
}

// ==================== Chain Intelligence Hooks ====================

import {
  chainIntelligenceService,
  type ChainIntelligenceReport,
  type OrphanDocument,
  type ChainSuggestionsResponse,
} from '../api/chain-intelligence-api';

export const chainIntelligenceQueryKeys = {
  all: ['chain-intelligence'] as const,
  gaps: () => [...chainIntelligenceQueryKeys.all, 'gaps'] as const,
  orphans: () => [...chainIntelligenceQueryKeys.all, 'orphans'] as const,
  suggestions: (chainId: string) =>
    [...chainIntelligenceQueryKeys.all, 'suggestions', chainId] as const,
};

/**
 * Hook fuer Ketten-Intelligenz-Bericht (Luecken + Statistiken)
 */
export function useChainGaps(options?: { enabled?: boolean }) {
  return useQuery<ChainIntelligenceReport>({
    queryKey: chainIntelligenceQueryKeys.gaps(),
    queryFn: () => chainIntelligenceService.getChainGaps(),
    staleTime: 5 * 60 * 1000, // 5 Minuten
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook fuer verwaiste Dokumente
 */
export function useOrphanDocuments(options?: { enabled?: boolean }) {
  return useQuery<OrphanDocument[]>({
    queryKey: chainIntelligenceQueryKeys.orphans(),
    queryFn: () => chainIntelligenceService.getOrphanDocuments(),
    staleTime: 5 * 60 * 1000, // 5 Minuten
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook fuer Vervollstaendigungs-Vorschlaege einer Kette
 */
export function useChainSuggestions(
  chainId: string,
  options?: { enabled?: boolean }
) {
  return useQuery<ChainSuggestionsResponse>({
    queryKey: chainIntelligenceQueryKeys.suggestions(chainId),
    queryFn: () => chainIntelligenceService.getChainSuggestions(chainId),
    staleTime: 60 * 1000, // 1 Minute
    enabled: (options?.enabled ?? true) && !!chainId,
  });
}
