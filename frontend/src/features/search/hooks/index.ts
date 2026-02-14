/**
 * Search Hooks - Export Index
 */

export { useSearch, defaultSearchParams } from './useSearch';
export { useFacets } from './useFacets';
export { useSearchSuggestions } from './use-search-suggestions';
export { useRecentSearches } from './use-recent-searches';
export { useSavedSearches } from './use-saved-searches';

// Smart Search Hooks
export { useSmartSearch, defaultSmartSearchOptions } from './useSmartSearch';
export { useSmartAutocomplete } from './useSmartAutocomplete';
export { useSpotlightSearch } from './use-spotlight-search';

// Re-export types
export type { UseSearchOptions, UseSmartSearchOptions, UseSmartAutocompleteOptions } from './useSmartSearch';
export type { SmartSearchFilters } from '../api/smart-search-api';
