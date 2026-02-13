/**
 * Knowledge Graph API Service
 * API-Funktionen für die Wissens-Graph-Visualisierung
 */

import { apiClient } from '@/lib/api/client';
import type { GraphData, SearchResult, GraphCommunity } from '../types';

const BASE_URL = '/knowledge-graph';

export const knowledgeGraphApi = {
  /**
   * Lädt den Entity-Graph mit konfigurierbarer Tiefe
   */
  async getEntityGraph(entityId: string, depth: number = 2): Promise<GraphData> {
    const response = await apiClient.get<GraphData>(
      `${BASE_URL}/entity/${entityId}`,
      {
        params: { depth },
      }
    );
    return response.data;
  },

  /**
   * Sucht nach Entitäten und Dokumenten im Graph
   */
  async searchGraph(
    query: string,
    types: string[] = ['entity', 'document'],
    limit: number = 20
  ): Promise<SearchResult[]> {
    const response = await apiClient.get<SearchResult[]>(`${BASE_URL}/search`, {
      params: {
        q: query,
        types: types.join(','),
        limit,
      },
    });
    return response.data;
  },

  /**
   * Findet den kürzesten Pfad zwischen zwei Knoten
   */
  async getShortestPath(fromId: string, toId: string): Promise<GraphData> {
    const response = await apiClient.get<GraphData>(`${BASE_URL}/shortest-path`, {
      params: {
        from: fromId,
        to: toId,
      },
    });
    return response.data;
  },

  /**
   * Lädt Community-Erkennungsergebnisse
   */
  async getCommunities(): Promise<GraphCommunity[]> {
    const response = await apiClient.get<GraphCommunity[]>(`${BASE_URL}/communities`);
    return response.data;
  },
};
