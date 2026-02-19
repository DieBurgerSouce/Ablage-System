/**
 * Knowledge Graph API Service
 * API-Funktionen für die Wissens-Graph-Visualisierung
 */

import { apiClient } from '@/lib/api/client';
import type { GraphData, SearchResult, GraphCommunity, FinancialChainData, RiskNetworkData, DocumentFamilyData, TimelineData } from '../types';

// ---------------------------------------------------------------------------
// Internal response types for timeline endpoints
// ---------------------------------------------------------------------------

interface DocumentTimelineEventRaw {
  event_type: string;
  timestamp: string | null;
  user_id?: string | null;
  details: Record<string, unknown>;
  description: string;
}

interface DocumentTimelineResponseRaw {
  document_id: string;
  events: DocumentTimelineEventRaw[];
  total_events: number;
}

interface ActivityItemRaw {
  id: string;
  activity_type: string;
  title: string;
  description?: string | null;
  target_id?: string | null;
  target_name?: string | null;
  related_id?: string | null;
  related_name?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface ActivityTimelineResponseRaw {
  items: ActivityItemRaw[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

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

  /**
   * Laedt Timeline-Ereignisse fuer ein Dokument.
   * Verwendet /api/v1/documents/{documentId}/timeline (Document Timeline API).
   * Mappt backend event_type-Strings auf frontend TimelineEvent-Format.
   */
  async getDocumentTimeline(documentId: string): Promise<TimelineData> {
    const response = await apiClient.get<DocumentTimelineResponseRaw>(
      `/documents/${documentId}/timeline`
    );
    const raw = response.data;
    return {
      events: raw.events.map((evt, idx) => ({
        id: `${raw.document_id}-${idx}-${evt.event_type}`,
        timestamp: evt.timestamp ?? new Date().toISOString(),
        eventType: evt.event_type,
        description: evt.description,
        documentId: raw.document_id,
        documentName: (evt.details['filename'] as string | undefined) ?? undefined,
        metadata: evt.details,
      })),
      totalCount: raw.total_events,
    };
  },

  /**
   * Laedt Activity-Timeline fuer ein Dokument.
   * Verwendet /api/v1/activity/document/{documentId} (Activity Timeline API).
   * Wird als Fallback genutzt wenn die Dokument-Timeline leer ist.
   */
  async getActivityTimeline(documentId: string, limit: number = 100): Promise<TimelineData> {
    const response = await apiClient.get<ActivityTimelineResponseRaw>(
      `/activity/document/${documentId}`,
      { params: { limit } }
    );
    const raw = response.data;
    return {
      events: raw.items.map((item) => ({
        id: item.id,
        timestamp: item.created_at,
        eventType: item.activity_type,
        description: item.description ?? item.title,
        documentId: item.target_id ?? undefined,
        documentName: item.target_name ?? undefined,
        metadata: item.metadata,
      })),
      totalCount: raw.total,
    };
  },
};
