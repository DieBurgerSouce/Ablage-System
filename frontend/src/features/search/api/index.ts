/**
 * Search API - Export Index
 */

export { searchApi, searchQueryKeys, unifiedSearch, getSearchModes } from './search-api';
export { smartSearchApi, smartSearchQueryKeys } from './smart-search-api';

// Re-export types
export type {
    SearchParams,
    SearchResponse,
    SearchType,
    SearchFilters,
    UnifiedSearchParams,
    UnifiedSearchResponse,
    UnifiedSearchMode,
} from './search-api';

export type {
    SmartSearchRequest,
    SmartSearchResponse,
    SmartSearchFilters,
    EntityMatch,
    QueryInterpretation,
    QuerySuggestion,
    SearchFacets,
    SmartSearchResult,
    AutocompleteResponse,
    AutocompleteResult,
} from './smart-search-api';
