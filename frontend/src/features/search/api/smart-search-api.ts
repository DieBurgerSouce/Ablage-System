import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface SmartSearchFilters {
    document_types?: string[];
    date_from?: string;
    date_to?: string;
    status?: string[];
    entity_id?: string;
    amount_min?: number;
    amount_max?: number;
}

export interface SmartSearchRequest {
    query: string;
    filters?: SmartSearchFilters;
    limit?: number;
    include_suggestions?: boolean;
    force_mode?: 'nlq' | 'keyword' | null;
}

export interface EntityMatch {
    entity_id: string;
    entity_name: string;
    entity_type: 'customer' | 'supplier' | 'other';
    match_type: 'exact' | 'fuzzy' | 'semantic';
    match_confidence: number;
    customer_number?: string | null;
    supplier_number?: string | null;
}

export interface QueryInterpretation {
    original_query: string;
    interpreted_as: string;
    search_mode: 'nlq' | 'keyword';
    detected_entities: string[];
    detected_filters: Record<string, unknown>;
    confidence: number;
}

export interface QuerySuggestion {
    suggestion_type: 'refine' | 'similar' | 'related';
    text: string;
    description?: string;
    filters?: SmartSearchFilters;
}

export interface SearchFacets {
    document_types: Array<{ value: string; count: number; label: string }>;
    statuses: Array<{ value: string; count: number; label: string }>;
    entities: Array<{ value: string; count: number; label: string }>;
    date_ranges: Array<{ value: string; count: number; label: string }>;
}

export interface SmartSearchResult {
    document_id: string;
    filename: string;
    document_type: string;
    status: string;
    created_at: string;
    relevance_score: number;
    matched_text?: string;
    highlight?: string;
    entity_match?: EntityMatch;
}

export interface SmartSearchResponse {
    results: SmartSearchResult[];
    entities: EntityMatch[];
    interpretation: QueryInterpretation;
    suggestions: QuerySuggestion[];
    facets: SearchFacets;
    total: number;
    search_time_ms: number;
    search_mode: 'nlq' | 'keyword';
    /** Rechtschreibkorrektur-Vorschlag vom Backend (optional) */
    spelling_suggestion?: string;
}

export interface AutocompleteResult {
    text: string;
    type: 'entity' | 'document_type' | 'recent' | 'suggestion';
    confidence?: number;
    entity_type?: string;
}

export interface AutocompleteResponse {
    suggestions: AutocompleteResult[];
}

// Backend response types (snake_case)
interface EntityMatchBackend {
    entity_id: string;
    entity_name: string;
    entity_type: string;
    match_type: string;
    match_confidence: number;
    customer_number?: string | null;
    supplier_number?: string | null;
}

interface QueryInterpretationBackend {
    original_query: string;
    interpreted_as: string;
    search_mode: string;
    detected_entities: string[];
    detected_filters: Record<string, unknown>;
    confidence: number;
}

interface QuerySuggestionBackend {
    suggestion_type: string;
    text: string;
    description?: string;
    filters?: Record<string, unknown>;
}

interface FacetValueBackend {
    value: string;
    count: number;
    label: string;
}

interface SearchFacetsBackend {
    document_types: FacetValueBackend[];
    statuses: FacetValueBackend[];
    entities: FacetValueBackend[];
    date_ranges: FacetValueBackend[];
}

interface SmartSearchResultBackend {
    document_id: string;
    filename: string;
    document_type: string;
    status: string;
    created_at: string;
    relevance_score: number;
    matched_text?: string;
    highlight?: string;
    entity_match?: EntityMatchBackend;
}

interface SmartSearchResponseBackend {
    results: SmartSearchResultBackend[];
    entities: EntityMatchBackend[];
    interpretation: QueryInterpretationBackend;
    suggestions: QuerySuggestionBackend[];
    facets: SearchFacetsBackend;
    total: number;
    search_time_ms: number;
    search_mode: string;
    spelling_suggestion?: string;
}

interface AutocompleteResultBackend {
    text: string;
    type: string;
    confidence?: number;
    entity_type?: string;
}

interface AutocompleteResponseBackend {
    suggestions: AutocompleteResultBackend[];
}

// ==================== Transformers ====================

function transformEntityMatch(entity: EntityMatchBackend): EntityMatch {
    return {
        entity_id: entity.entity_id,
        entity_name: entity.entity_name,
        entity_type: entity.entity_type as 'customer' | 'supplier' | 'other',
        match_type: entity.match_type as 'exact' | 'fuzzy' | 'semantic',
        match_confidence: entity.match_confidence,
        customer_number: entity.customer_number,
        supplier_number: entity.supplier_number,
    };
}

function transformQueryInterpretation(interp: QueryInterpretationBackend): QueryInterpretation {
    return {
        original_query: interp.original_query,
        interpreted_as: interp.interpreted_as,
        search_mode: interp.search_mode as 'nlq' | 'keyword',
        detected_entities: interp.detected_entities,
        detected_filters: interp.detected_filters,
        confidence: interp.confidence,
    };
}

function transformQuerySuggestion(sugg: QuerySuggestionBackend): QuerySuggestion {
    return {
        suggestion_type: sugg.suggestion_type as 'refine' | 'similar' | 'related',
        text: sugg.text,
        description: sugg.description,
        filters: sugg.filters as SmartSearchFilters,
    };
}

function transformSearchFacets(facets: SearchFacetsBackend): SearchFacets {
    return {
        document_types: facets.document_types,
        statuses: facets.statuses,
        entities: facets.entities,
        date_ranges: facets.date_ranges,
    };
}

function transformSmartSearchResult(result: SmartSearchResultBackend): SmartSearchResult {
    return {
        document_id: result.document_id,
        filename: result.filename,
        document_type: result.document_type,
        status: result.status,
        created_at: result.created_at,
        relevance_score: result.relevance_score,
        matched_text: result.matched_text,
        highlight: result.highlight,
        entity_match: result.entity_match ? transformEntityMatch(result.entity_match) : undefined,
    };
}

function transformSmartSearchResponse(response: SmartSearchResponseBackend): SmartSearchResponse {
    return {
        results: response.results.map(transformSmartSearchResult),
        entities: response.entities.map(transformEntityMatch),
        interpretation: transformQueryInterpretation(response.interpretation),
        suggestions: response.suggestions.map(transformQuerySuggestion),
        facets: transformSearchFacets(response.facets),
        total: response.total,
        search_time_ms: response.search_time_ms,
        search_mode: response.search_mode as 'nlq' | 'keyword',
        spelling_suggestion: response.spelling_suggestion,
    };
}

function transformAutocompleteResponse(response: AutocompleteResponseBackend): AutocompleteResponse {
    return {
        suggestions: response.suggestions.map((s) => ({
            text: s.text,
            type: s.type as 'entity' | 'document_type' | 'recent' | 'suggestion',
            confidence: s.confidence,
            entity_type: s.entity_type,
        })),
    };
}

// ==================== API Functions ====================

/**
 * Smart Search API Service
 */
export const smartSearchApi = {
    /**
     * Durchsucht Dokumente mit NLQ/Keyword-Erkennung und Entity-Linking.
     */
    search: async (request: SmartSearchRequest): Promise<SmartSearchResponse> => {
        const response = await apiClient.post<SmartSearchResponseBackend>(
            '/smart-search',
            {
                query: request.query,
                filters: request.filters,
                limit: request.limit || 20,
                include_suggestions: request.include_suggestions !== false,
                force_mode: request.force_mode,
            }
        );

        return transformSmartSearchResponse(response.data);
    },

    /**
     * Autocomplete-Vorschläge während der Eingabe.
     */
    autocomplete: async (partial: string): Promise<AutocompleteResponse> => {
        const response = await apiClient.get<AutocompleteResponseBackend>(
            '/smart-search/autocomplete',
            {
                params: { q: partial },
            }
        );

        return transformAutocompleteResponse(response.data);
    },
};

/**
 * Query Keys für React Query
 */
export const smartSearchQueryKeys = {
    all: ['smart-search'] as const,
    search: (request: SmartSearchRequest) => ['smart-search', request] as const,
    autocomplete: (partial: string) => ['smart-search', 'autocomplete', partial] as const,
};
