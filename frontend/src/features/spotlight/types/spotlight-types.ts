/**
 * Spotlight Types
 *
 * TypeScript Typen fuer das Spotlight (Cmd+K) Feature.
 * Backend-Typen (snake_case) und Frontend-Typen (camelCase).
 */

// ==================== Suggestion Types ====================

export type SpotlightSuggestionType =
  | 'entity'
  | 'document_type'
  | 'recent'
  | 'suggestion'
  | 'navigation';

export type SpotlightSearchMode = 'nlq' | 'keyword';

export type SpotlightEntityType = 'customer' | 'supplier';

// ==================== Backend Types (snake_case) ====================

export interface SpotlightSuggestionBackend {
  text: string;
  suggestion_type: SpotlightSuggestionType;
  confidence: number | null;
  entity_type: string | null;
}

export interface SpotlightDocumentBackend {
  document_id: string;
  filename: string;
  document_type: string;
  status: string;
  created_at: string | null;
  ocr_confidence: number | null;
  relevance_score: number;
  highlight: string | null;
  text_preview: string | null;
}

export interface SpotlightEntityBackend {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  customer_number: string | null;
  supplier_number: string | null;
  match_confidence: number;
}

export interface SpotlightInterpretationBackend {
  original_query: string;
  interpreted_as: string;
  search_mode: SpotlightSearchMode;
  confidence: number;
}

export interface SpotlightResponseBackend {
  suggestions: SpotlightSuggestionBackend[];
  documents: SpotlightDocumentBackend[];
  entities: SpotlightEntityBackend[];
  interpretation: SpotlightInterpretationBackend | null;
  search_time_ms: number;
  total_documents: number;
}

// ==================== Frontend Types (camelCase) ====================

export interface SpotlightSuggestionResponse {
  text: string;
  suggestionType: SpotlightSuggestionType;
  confidence: number | null;
  entityType: string | null;
}

export interface SpotlightDocumentResponse {
  documentId: string;
  filename: string;
  documentType: string;
  status: string;
  createdAt: string | null;
  ocrConfidence: number | null;
  relevanceScore: number;
  highlight: string | null;
  textPreview: string | null;
}

export interface SpotlightEntityResponse {
  entityId: string;
  entityName: string;
  entityType: string;
  customerNumber: string | null;
  supplierNumber: string | null;
  matchConfidence: number;
}

export interface SpotlightInterpretationResponse {
  originalQuery: string;
  interpretedAs: string;
  searchMode: SpotlightSearchMode;
  confidence: number;
}

export interface SpotlightResultsResponse {
  suggestions: SpotlightSuggestionResponse[];
  documents: SpotlightDocumentResponse[];
  entities: SpotlightEntityResponse[];
  interpretation: SpotlightInterpretationResponse | null;
  searchTimeMs: number;
  totalDocuments: number;
}

// ==================== Recent Search Types ====================

export interface RecentSearch {
  query: string;
  timestamp: number;
  frequency: number;
}

export interface RecentSearchEntry {
  query: string;
  timestamp: number;
  frequency: number;
  score: number;
}
