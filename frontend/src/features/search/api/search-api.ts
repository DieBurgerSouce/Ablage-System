import { apiClient } from '@/lib/api/client';
import type { SearchResultItem } from '../components/SearchResultCard';

// Search Types
export type SearchType = 'fts' | 'semantic' | 'hybrid';
export type SortField = 'relevance' | 'created_at' | 'filename' | 'ocr_confidence';
export type SortOrder = 'asc' | 'desc';

export interface SearchFilters {
    documentType?: string;
    status?: string;
    dateFrom?: string;
    dateTo?: string;
    confidenceMin?: number;
    hasEmbedding?: boolean;
    tags?: string[];
}

export interface SearchParams {
    query: string;
    searchType?: SearchType;
    page?: number;
    perPage?: number;
    filters?: SearchFilters;
    sortBy?: SortField;
    sortOrder?: SortOrder;
    highlight?: boolean;
    similarityThreshold?: number;
    useSynonyms?: boolean;
}

// Backend response (snake_case)
interface SynonymExpansionBackend {
    original: string;
    synonyms: string[];
}

interface SearchResponseBackend {
    results: SearchResultItemBackend[];
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
    query: string;
    search_type: string;
    execution_time_ms: number;
    synonym_expansions?: SynonymExpansionBackend[];
    did_you_mean?: string | null;
}

interface MatchedEntityBackend {
    entity_id: string;
    entity_name: string;
    entity_type: string;
    match_type: string;
    match_confidence: number;
    customer_number?: string | null;
    supplier_number?: string | null;
}

interface SearchResultItemBackend {
    document_id: string;
    filename: string;
    original_filename: string;
    document_type: string;
    status: string;
    created_at: string;
    updated_at: string;
    file_size: number;
    page_count?: number | null;
    ocr_confidence?: number | null;
    score: number;
    fts_rank?: number | null;
    semantic_similarity?: number | null;
    highlight?: string | null;
    text_preview?: string | null;
    tags: string[];
    owner_id: string;
    matched_entity?: MatchedEntityBackend | null;
}

// Frontend types
export interface SynonymExpansion {
    original: string;
    synonyms: string[];
}

// Frontend response (camelCase)
export interface SearchResponse {
    results: SearchResultItem[];
    total: number;
    page: number;
    perPage: number;
    totalPages: number;
    query: string;
    searchType: string;
    executionTimeMs: number;
    synonymExpansions?: SynonymExpansion[];
    didYouMean?: string | null;
}

function transformSearchResult(item: SearchResultItemBackend): SearchResultItem {
    return {
        documentId: item.document_id,
        filename: item.filename,
        originalFilename: item.original_filename,
        documentType: item.document_type,
        status: item.status,
        createdAt: item.created_at,
        updatedAt: item.updated_at,
        fileSize: item.file_size,
        pageCount: item.page_count,
        ocrConfidence: item.ocr_confidence,
        score: item.score,
        ftsRank: item.fts_rank,
        semanticSimilarity: item.semantic_similarity,
        highlight: item.highlight,
        textPreview: item.text_preview,
        tags: item.tags,
        matchedEntity: item.matched_entity ? {
            entityId: item.matched_entity.entity_id,
            entityName: item.matched_entity.entity_name,
            entityType: item.matched_entity.entity_type,
            matchType: item.matched_entity.match_type,
            matchConfidence: item.matched_entity.match_confidence,
            customerNumber: item.matched_entity.customer_number,
            supplierNumber: item.matched_entity.supplier_number,
        } : undefined,
    };
}

function transformSearchResponse(response: SearchResponseBackend): SearchResponse {
    return {
        results: response.results.map(transformSearchResult),
        total: response.total,
        page: response.page,
        perPage: response.per_page,
        totalPages: response.total_pages,
        query: response.query,
        searchType: response.search_type,
        executionTimeMs: response.execution_time_ms,
        synonymExpansions: response.synonym_expansions,
        didYouMean: response.did_you_mean ?? undefined,
    };
}

/**
 * Search API Service
 */
export const searchApi = {
    /**
     * Durchsucht Dokumente mit Volltext-, semantischer oder hybrider Suche.
     */
    search: async (params: SearchParams): Promise<SearchResponse> => {
        const queryParams: Record<string, unknown> = {
            q: params.query,
        };

        if (params.searchType) queryParams.search_type = params.searchType;
        if (params.page) queryParams.page = params.page;
        if (params.perPage) queryParams.per_page = params.perPage;
        if (params.sortBy) queryParams.sort_by = params.sortBy;
        if (params.sortOrder) queryParams.sort_order = params.sortOrder;
        if (params.highlight !== undefined) queryParams.highlight = params.highlight;
        if (params.similarityThreshold) queryParams.similarity_threshold = params.similarityThreshold;
        if (params.useSynonyms !== undefined) queryParams.use_synonyms = params.useSynonyms;

        // Filters
        if (params.filters?.documentType) queryParams.document_type = params.filters.documentType;
        if (params.filters?.status) queryParams.status = params.filters.status;
        if (params.filters?.dateFrom) queryParams.date_from = params.filters.dateFrom;
        if (params.filters?.dateTo) queryParams.date_to = params.filters.dateTo;
        if (params.filters?.confidenceMin) queryParams.confidence_min = params.filters.confidenceMin;
        if (params.filters?.hasEmbedding !== undefined) queryParams.has_embedding = params.filters.hasEmbedding;
        if (params.filters?.tags?.length) queryParams.tags = params.filters.tags;

        const response = await apiClient.get<SearchResponseBackend>('/documents/search/', {
            params: queryParams,
        });

        return transformSearchResponse(response.data);
    },
};

// ==================== Unified Search Types ====================

export type UnifiedSearchMode = 'document' | 'chunk' | 'combined';

export interface UnifiedChunkResult {
    chunkId: string;
    documentId: string;
    content: string;
    sectionType?: string | null;
    score: number;
    highlight?: string | null;
}

export interface UnifiedDocumentResult {
    documentId: string;
    filename: string;
    originalFilename?: string | null;
    score: number;
    documentType?: string | null;
    status?: string | null;
    createdAt?: string | null;
    mimeType?: string | null;
    pageCount?: number | null;
    extractedTextPreview?: string | null;
    matchedChunks: UnifiedChunkResult[];
    ftsScore?: number | null;
    semanticScore?: number | null;
    rerankScore?: number | null;
}

export interface UnifiedSearchResponse {
    query: string;
    mode: string;
    documents: UnifiedDocumentResult[];
    totalDocuments: number;
    chunkResults: UnifiedChunkResult[];
    totalChunks: number;
    searchTimeMs: number;
    documentSearchTimeMs?: number | null;
    chunkSearchTimeMs?: number | null;
    synonymsUsed: string[];
}

export interface UnifiedSearchParams {
    query: string;
    mode?: UnifiedSearchMode;
    searchType?: SearchType;
    page?: number;
    perPage?: number;
    expandSynonyms?: boolean;
    chunkLimit?: number;
    chunkThreshold?: number;
    rerank?: boolean;
    documentIds?: string[];
    documentType?: string;
    status?: string;
}

// Backend response types (snake_case)
interface UnifiedChunkResultBackend {
    chunk_id: string;
    document_id: string;
    content: string;
    section_type?: string | null;
    score: number;
    highlight?: string | null;
}

interface UnifiedDocumentResultBackend {
    document_id: string;
    filename: string;
    original_filename?: string | null;
    score: number;
    document_type?: string | null;
    status?: string | null;
    created_at?: string | null;
    mime_type?: string | null;
    page_count?: number | null;
    extracted_text_preview?: string | null;
    matched_chunks: UnifiedChunkResultBackend[];
    fts_score?: number | null;
    semantic_score?: number | null;
    rerank_score?: number | null;
}

interface UnifiedSearchResponseBackend {
    query: string;
    mode: string;
    documents: UnifiedDocumentResultBackend[];
    total_documents: number;
    chunk_results: UnifiedChunkResultBackend[];
    total_chunks: number;
    search_time_ms: number;
    document_search_time_ms?: number | null;
    chunk_search_time_ms?: number | null;
    synonyms_used: string[];
}

function transformUnifiedChunk(chunk: UnifiedChunkResultBackend): UnifiedChunkResult {
    return {
        chunkId: chunk.chunk_id,
        documentId: chunk.document_id,
        content: chunk.content,
        sectionType: chunk.section_type,
        score: chunk.score,
        highlight: chunk.highlight,
    };
}

function transformUnifiedDocument(doc: UnifiedDocumentResultBackend): UnifiedDocumentResult {
    return {
        documentId: doc.document_id,
        filename: doc.filename,
        originalFilename: doc.original_filename,
        score: doc.score,
        documentType: doc.document_type,
        status: doc.status,
        createdAt: doc.created_at,
        mimeType: doc.mime_type,
        pageCount: doc.page_count,
        extractedTextPreview: doc.extracted_text_preview,
        matchedChunks: doc.matched_chunks.map(transformUnifiedChunk),
        ftsScore: doc.fts_score,
        semanticScore: doc.semantic_score,
        rerankScore: doc.rerank_score,
    };
}

function transformUnifiedSearchResponse(response: UnifiedSearchResponseBackend): UnifiedSearchResponse {
    return {
        query: response.query,
        mode: response.mode,
        documents: response.documents.map(transformUnifiedDocument),
        totalDocuments: response.total_documents,
        chunkResults: response.chunk_results.map(transformUnifiedChunk),
        totalChunks: response.total_chunks,
        searchTimeMs: response.search_time_ms,
        documentSearchTimeMs: response.document_search_time_ms,
        chunkSearchTimeMs: response.chunk_search_time_ms,
        synonymsUsed: response.synonyms_used,
    };
}

/**
 * Unified Search API Function
 */
export async function unifiedSearch(params: UnifiedSearchParams): Promise<UnifiedSearchResponse> {
    const requestBody = {
        query: params.query,
        mode: params.mode || 'combined',
        search_type: params.searchType || 'hybrid',
        page: params.page || 1,
        per_page: params.perPage || 20,
        expand_synonyms: params.expandSynonyms !== false,
        chunk_limit: params.chunkLimit || 10,
        chunk_threshold: params.chunkThreshold || 0.5,
        rerank: params.rerank !== false,
        document_ids: params.documentIds,
        document_type: params.documentType,
        status: params.status,
    };

    const response = await apiClient.post<UnifiedSearchResponseBackend>(
        '/unified-search',
        requestBody
    );

    return transformUnifiedSearchResponse(response.data);
}

/**
 * Get available search modes
 */
export interface SearchModeInfo {
    id: string;
    name: string;
    description: string;
    supportsPagination: boolean;
    supportsFilters: boolean;
}

export interface SearchTypeInfo {
    id: string;
    name: string;
    description: string;
}

export interface SearchModesResponse {
    modes: SearchModeInfo[];
    searchTypes: SearchTypeInfo[];
}

export async function getSearchModes(): Promise<SearchModesResponse> {
    const response = await apiClient.get<{
        modes: Array<{
            id: string;
            name: string;
            description: string;
            supports_pagination: boolean;
            supports_filters: boolean;
        }>;
        search_types: Array<{
            id: string;
            name: string;
            description: string;
        }>;
    }>('/unified-search/modes');

    return {
        modes: response.data.modes.map((m) => ({
            id: m.id,
            name: m.name,
            description: m.description,
            supportsPagination: m.supports_pagination,
            supportsFilters: m.supports_filters,
        })),
        searchTypes: response.data.search_types.map((t) => ({
            id: t.id,
            name: t.name,
            description: t.description,
        })),
    };
}

/**
 * Query Keys für React Query
 */
export const searchQueryKeys = {
    all: ['search'] as const,
    search: (params: SearchParams) => ['search', params] as const,
    unified: (params: UnifiedSearchParams) => ['search', 'unified', params] as const,
    modes: () => ['search', 'modes'] as const,
};
