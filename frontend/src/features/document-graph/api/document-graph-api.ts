/**
 * Document Graph API Service
 *
 * API-Calls fuer Dokumenten-Ketten (Chains) und Lineage.
 * Nutzt bestehende Backend-Endpoints.
 */

import { apiClient } from '@/lib/api/client';
import type {
  DocumentChain,
  ChainByDocumentResponse,
  DocumentChainBackend,
  ChainDocumentBackend,
  ChainDocument,
} from '../types/document-graph-types';

// ==================== Transform Functions ====================

function transformChainDocument(doc: ChainDocumentBackend): ChainDocument {
  return {
    id: doc.id,
    documentType: doc.document_type,
    chainPosition: doc.chain_position,
    filename: doc.filename,
    documentDate: doc.document_date,
    amount: doc.amount,
    referenceNumbers: doc.reference_numbers,
    createdAt: doc.created_at,
  };
}

function transformChain(chain: DocumentChainBackend): DocumentChain {
  return {
    chainId: chain.chain_id,
    documentCount: chain.document_count,
    chainStartedAt: chain.chain_started_at,
    chainUpdatedAt: chain.chain_updated_at,
    hasQuote: chain.has_quote,
    hasOrder: chain.has_order,
    hasDeliveryNote: chain.has_delivery_note,
    hasInvoice: chain.has_invoice,
    hasCreditNote: chain.has_credit_note,
    openDiscrepancies: chain.open_discrepancies,
    isComplete: chain.is_complete,
    documents: chain.documents.map(transformChainDocument),
  };
}

// ==================== API Service ====================

export const documentGraphApi = {
  /**
   * Ruft eine Auftragskette nach ID ab.
   */
  getChain: async (chainId: string): Promise<DocumentChain> => {
    const response = await apiClient.get<DocumentChainBackend>(
      `/document-chains/${chainId}`
    );
    return transformChain(response.data);
  },

  /**
   * Findet die Kette zu der ein Dokument gehoert.
   */
  getChainByDocument: async (documentId: string): Promise<ChainByDocumentResponse> => {
    const response = await apiClient.get(`/document-chains/by-document/${documentId}`);
    const data = response.data;
    return {
      documentId: data.document_id,
      chainId: data.chain_id,
      documentCount: data.document_count,
      isComplete: data.is_complete,
      openDiscrepancies: data.open_discrepancies,
      message: data.message,
    };
  },

  /**
   * Listet alle Ketten eines Geschaeftspartners.
   */
  getChainsByEntity: async (params: {
    entityId?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ chains: DocumentChain[]; total: number }> => {
    const queryParams: Record<string, string | number> = {};
    if (params.entityId) queryParams.entity_id = params.entityId;
    if (params.limit) queryParams.limit = params.limit;
    if (params.offset) queryParams.offset = params.offset;

    const response = await apiClient.get('/document-chains', {
      params: queryParams,
    });

    const data = response.data;
    return {
      chains: (data.chains || data.items || []).map(transformChain),
      total: data.total || 0,
    };
  },
};
