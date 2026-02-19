/**
 * Knowledge Graph API Service
 * API-Funktionen für die Wissens-Graph-Visualisierung
 */

import { apiClient } from '@/lib/api/client';
import type { GraphData, SearchResult, GraphCommunity, FinancialChainData, RiskNetworkData, DocumentFamilyData } from '../types';

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

  /**
   * Laedt Finanzketten fuer eine Entity
   */
  async getFinancialChain(entityId: string): Promise<FinancialChainData> {
    const response = await apiClient.get<FinancialChainData>(
      `${BASE_URL}/financial-chain/${entityId}`
    );
    return response.data;
  },

  /**
   * Laedt Risiko-Netzwerk mit Communities
   */
  async getRiskNetwork(entityId?: string): Promise<RiskNetworkData> {
    const response = await apiClient.get<RiskNetworkData>(
      `${BASE_URL}/risk-network`,
      { params: entityId ? { entity_id: entityId } : undefined }
    );
    return response.data;
  },

  /**
   * Laedt Dokumentenfamilie
   */
  async getDocumentFamily(documentId: string): Promise<DocumentFamilyData> {
    const response = await apiClient.get<DocumentFamilyData>(
      `${BASE_URL}/document-family/${documentId}`
    );
    return response.data;
  },
};
