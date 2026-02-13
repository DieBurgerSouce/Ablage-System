/**
 * Knowledge Graph Query Hooks
 * TanStack Query hooks für Wissens-Graph-Daten
 */

import { useQuery } from '@tanstack/react-query';
import { useMemo, useState, useEffect } from 'react';
import { knowledgeGraphApi } from '../api';
import type { GraphData, SearchResult, GraphCommunity } from '../types';

/**
 * Hook zum Laden des Entity-Graphs
 */
export function useEntityGraph(entityId: string | undefined, depth: number = 2) {
  return useQuery<GraphData>({
    queryKey: ['knowledge-graph', 'entity', entityId, depth],
    queryFn: () => knowledgeGraphApi.getEntityGraph(entityId!, depth),
    enabled: Boolean(entityId),
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook für Graph-Suche mit Debouncing
 */
export function useGraphSearch(query: string) {
  const [debouncedQuery, setDebouncedQuery] = useState(query);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  return useQuery<SearchResult[]>({
    queryKey: ['knowledge-graph', 'search', debouncedQuery],
    queryFn: () => knowledgeGraphApi.searchGraph(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
    staleTime: 2 * 60 * 1000, // 2 Minuten
  });
}

/**
 * Hook zum Finden des kürzesten Pfads zwischen zwei Knoten
 */
export function useShortestPath(fromId: string | undefined, toId: string | undefined) {
  return useQuery<GraphData>({
    queryKey: ['knowledge-graph', 'shortest-path', fromId, toId],
    queryFn: () => knowledgeGraphApi.getShortestPath(fromId!, toId!),
    enabled: Boolean(fromId && toId),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook zum Laden der Communities
 */
export function useCommunities() {
  return useQuery<GraphCommunity[]>({
    queryKey: ['knowledge-graph', 'communities'],
    queryFn: () => knowledgeGraphApi.getCommunities(),
    staleTime: 10 * 60 * 1000, // 10 Minuten
  });
}
