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

// Voice Search Hook
export { useVoiceSearch } from './use-voice-search';

// Re-export types (aus den Modulen, die sie tatsaechlich deklarieren)
export type { UseSearchOptions } from './useSearch';
export type { UseSmartAutocompleteOptions } from './useSmartAutocomplete';
export type { UseSmartSearchOptions, UseSmartSearchReturn } from './useSmartSearch';
export type { SmartSearchFilters } from '../api/smart-search-api';
export type { UseVoiceSearchOptions, UseVoiceSearchReturn } from './use-voice-search';
