/**
 * Document Chain API Service
 *
 * Kommuniziert mit den /api/v1/document-chains Endpoints
 * fuer Auftragsketten-Tracking.
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type {
  DocumentChainInfo,
  DocumentChainInfoBackend,
  ChainDocument,
  ChainDocumentBackend,
  ChainRelationship,
  ChainRelationshipBackend,
  ChainDiscrepancy,
  ChainDiscrepancyBackend,
  ChainMatchResult,
  ChainMatchResultBackend,
  ChainCreate,
  LinkDocumentsRequest,
  ResolveDiscrepancyRequest,
  ChainFilter,
} from '../types/chain-types';

// ==================== Error Class ====================

export class ChainApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'ChainApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformDocument(doc: ChainDocumentBackend): ChainDocument {
  return {
    id: doc.id,
    documentType: doc.document_type,
    filename: doc.filename,
    displayName: doc.display_name,
    referenceNumber: doc.reference_number,
    totalAmount: doc.total_amount,
    documentDate: doc.document_date,
    businessEntityId: doc.business_entity_id,
    businessEntityName: doc.business_entity_name,
    createdAt: doc.created_at,
  };
}

function transformRelationship(rel: ChainRelationshipBackend): ChainRelationship {
  return {
    id: rel.id,
    sourceDocumentId: rel.source_document_id,
    targetDocumentId: rel.target_document_id,
    relationshipType: rel.relationship_type,
    confidence: rel.confidence,
    createdAt: rel.created_at,
  };
}

function transformDiscrepancy(disc: ChainDiscrepancyBackend): ChainDiscrepancy {
  return {
    id: disc.id,
    chainId: disc.chain_id,
    sourceDocumentId: disc.source_document_id,
    targetDocumentId: disc.target_document_id,
    discrepancyType: disc.discrepancy_type,
    severity: disc.severity,
    description: disc.description,
    sourceValue: disc.source_value,
    targetValue: disc.target_value,
    differencePercentage: disc.difference_percentage,
    isResolved: disc.is_resolved,
    resolvedAt: disc.resolved_at,
    resolvedByUserId: disc.resolved_by_user_id,
    resolutionNotes: disc.resolution_notes,
    createdAt: disc.created_at,
  };
}

function transformChainInfo(chain: DocumentChainInfoBackend): DocumentChainInfo {
  return {
    chainId: chain.chain_id,
    name: chain.name,
    documents: chain.documents.map(transformDocument),
    relationships: chain.relationships.map(transformRelationship),
    discrepancies: chain.discrepancies.map(transformDiscrepancy),
    totalValue: chain.total_value,
    status: chain.status,
    createdAt: chain.created_at,
    updatedAt: chain.updated_at,
  };
}

function transformMatchResult(result: ChainMatchResultBackend): ChainMatchResult {
  return {
    candidateDocumentId: result.candidate_document_id,
    candidateDocument: transformDocument(result.candidate_document),
    confidence: result.confidence,
    matchReasons: result.match_reasons,
    suggestedRelationshipType: result.suggested_relationship_type,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new ChainApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 409) {
      throw new ChainApiError(`${context}: ${message}`, 409, error);
    }

    if (statusCode === 400) {
      throw new ChainApiError(`${context}: ${message}`, 400, error);
    }

    throw new ChainApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new ChainApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Chain Service ====================

export const chainService = {
  // ==================== List Chains ====================

  /**
   * Listet alle Auftragsketten
   */
  listChains: async (
    filter: Partial<ChainFilter> = {}
  ): Promise<DocumentChainInfo[]> => {
    try {
      const params: Record<string, string | number | boolean> = {
        page: filter.page ?? 1,
        per_page: filter.perPage ?? 20,
      };

      if (filter.status) {
        params.status = filter.status;
      }
      if (filter.businessEntityId) {
        params.business_entity_id = filter.businessEntityId;
      }
      if (filter.hasDiscrepancies !== undefined) {
        params.has_discrepancies = filter.hasDiscrepancies;
      }

      const response = await apiClient.get<DocumentChainInfoBackend[]>(
        '/document-chains',
        { params }
      );

      return response.data.map(transformChainInfo);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Auftragsketten laden');
    }
  },

  // ==================== Get Single Chain ====================

  /**
   * Ruft eine einzelne Kette ab
   */
  getChain: async (chainId: string): Promise<DocumentChainInfo> => {
    try {
      const response = await apiClient.get<DocumentChainInfoBackend>(
        `/document-chains/${chainId}`
      );

      return transformChainInfo(response.data);
    } catch (error) {
      handleApiError(error, 'Auftragskette laden');
    }
  },

  // ==================== Create Chain ====================

  /**
   * Erstellt eine neue Auftragskette
   */
  createChain: async (data: ChainCreate): Promise<DocumentChainInfo> => {
    try {
      const response = await apiClient.post<DocumentChainInfoBackend>(
        '/document-chains',
        {
          name: data.name,
          document_ids: data.documentIds,
        }
      );

      return transformChainInfo(response.data);
    } catch (error) {
      handleApiError(error, 'Auftragskette erstellen');
    }
  },

  // ==================== Link Documents ====================

  /**
   * Verknuepft zwei Dokumente
   */
  linkDocuments: async (
    data: LinkDocumentsRequest
  ): Promise<ChainRelationship> => {
    try {
      const response = await apiClient.post<ChainRelationshipBackend>(
        '/document-chains/link',
        {
          source_document_id: data.sourceDocumentId,
          target_document_id: data.targetDocumentId,
          relationship_type: data.relationshipType,
          chain_id: data.chainId,
        }
      );

      return transformRelationship(response.data);
    } catch (error) {
      handleApiError(error, 'Dokumente verknuepfen');
    }
  },

  // ==================== Auto-Match ====================

  /**
   * Findet automatisch passende Dokumente fuer ein Dokument
   */
  autoMatch: async (documentId: string): Promise<ChainMatchResult[]> => {
    try {
      const response = await apiClient.get<ChainMatchResultBackend[]>(
        `/document-chains/auto-match/${documentId}`
      );

      return response.data.map(transformMatchResult);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Automatisches Matching');
    }
  },

  // ==================== Discrepancies ====================

  /**
   * Ruft Abweichungen einer Kette ab
   */
  getDiscrepancies: async (
    chainId: string,
    includeResolved: boolean = false
  ): Promise<ChainDiscrepancy[]> => {
    try {
      const response = await apiClient.get<ChainDiscrepancyBackend[]>(
        `/document-chains/${chainId}/discrepancies`,
        { params: { include_resolved: includeResolved } }
      );

      return response.data.map(transformDiscrepancy);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Abweichungen laden');
    }
  },

  /**
   * Loest eine Abweichung auf
   */
  resolveDiscrepancy: async (
    discrepancyId: string,
    data: ResolveDiscrepancyRequest
  ): Promise<ChainDiscrepancy> => {
    try {
      const response = await apiClient.post<ChainDiscrepancyBackend>(
        `/document-chains/discrepancies/${discrepancyId}/resolve`,
        { resolution_notes: data.resolutionNotes }
      );

      return transformDiscrepancy(response.data);
    } catch (error) {
      handleApiError(error, 'Abweichung aufloesen');
    }
  },

  // ==================== Remove Link ====================

  /**
   * Entfernt eine Verknuepfung zwischen Dokumenten
   */
  removeLink: async (relationshipId: string): Promise<void> => {
    try {
      await apiClient.delete(`/document-chains/relationships/${relationshipId}`);
    } catch (error) {
      handleApiError(error, 'Verknuepfung entfernen');
    }
  },

  // ==================== Get Document Chain ====================

  /**
   * Ruft die Kette ab, zu der ein Dokument gehoert
   */
  getDocumentChain: async (documentId: string): Promise<DocumentChainInfo | null> => {
    try {
      const response = await apiClient.get<DocumentChainInfoBackend>(
        `/document-chains/by-document/${documentId}`
      );

      return transformChainInfo(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return null;
      }
      handleApiError(error, 'Dokumentkette laden');
    }
  },
};
