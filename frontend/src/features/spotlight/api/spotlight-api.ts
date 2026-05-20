/**
 * Spotlight API Service
 *
 * Kommuniziert mit dem /api/v1/spotlight Endpoint
 * fuer Volltext-Suche, Entity-Matching und NLQ.
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type {
  SpotlightResponseBackend,
  SpotlightResultsResponse,
  SpotlightSuggestionBackend,
  SpotlightSuggestionResponse,
  SpotlightDocumentBackend,
  SpotlightDocumentResponse,
  SpotlightEntityBackend,
  SpotlightEntityResponse,
  SpotlightInterpretationBackend,
  SpotlightInterpretationResponse,
} from '../types/spotlight-types';

// ==================== Error Classes ====================

export class SpotlightApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'SpotlightApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformSuggestion(item: SpotlightSuggestionBackend): SpotlightSuggestionResponse {
  return {
    text: item.text,
    suggestionType: item.suggestion_type,
    confidence: item.confidence,
    entityType: item.entity_type,
  };
}

function transformDocument(item: SpotlightDocumentBackend): SpotlightDocumentResponse {
  return {
    documentId: item.document_id,
    filename: item.filename,
    documentType: item.document_type,
    status: item.status,
    createdAt: item.created_at,
    ocrConfidence: item.ocr_confidence,
    relevanceScore: item.relevance_score,
    highlight: item.highlight,
    textPreview: item.text_preview,
  };
}

function transformEntity(item: SpotlightEntityBackend): SpotlightEntityResponse {
  return {
    entityId: item.entity_id,
    entityName: item.entity_name,
    entityType: item.entity_type,
    customerNumber: item.customer_number,
    supplierNumber: item.supplier_number,
    matchConfidence: item.match_confidence,
  };
}

function transformInterpretation(
  item: SpotlightInterpretationBackend
): SpotlightInterpretationResponse {
  return {
    originalQuery: item.original_query,
    interpretedAs: item.interpreted_as,
    searchMode: item.search_mode,
    confidence: item.confidence,
  };
}

function transformSpotlightResponse(
  response: SpotlightResponseBackend
): SpotlightResultsResponse {
  return {
    suggestions: response.suggestions.map(transformSuggestion),
    documents: response.documents.map(transformDocument),
    entities: response.entities.map(transformEntity),
    interpretation: response.interpretation
      ? transformInterpretation(response.interpretation)
      : null,
    searchTimeMs: response.search_time_ms,
    totalDocuments: response.total_documents,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new SpotlightApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new SpotlightApiError(`${context}: ${message}`, 400, error);
    }

    throw new SpotlightApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new SpotlightApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Spotlight Service ====================

export const spotlightService = {
  /**
   * Fuehrt eine Spotlight-Suche durch
   */
  search: async (
    query: string,
    limit?: number
  ): Promise<SpotlightResultsResponse> => {
    try {
      const params: Record<string, string | number> = { q: query };
      if (limit !== undefined) {
        params.limit = limit;
      }

      const response = await apiClient.get<SpotlightResponseBackend>(
        '/spotlight',
        { params }
      );

      return transformSpotlightResponse(response.data);
    } catch (error) {
      handleApiError(error, 'Spotlight-Suche');
    }
  },
};
