/**
 * Spotlight Feature - Barrel Export
 *
 * Exportiert alle oeffentlichen APIs des Spotlight (Cmd+K) Moduls.
 */

// Types
export type {
  SpotlightSuggestionType,
  SpotlightSearchMode,
  SpotlightEntityType,
  SpotlightSuggestionResponse,
  SpotlightDocumentResponse,
  SpotlightEntityResponse,
  SpotlightInterpretationResponse,
  SpotlightResultsResponse,
  RecentSearch,
  RecentSearchEntry,
} from './types/spotlight-types';

// API
export { spotlightService, SpotlightApiError } from './api/spotlight-api';

// Hooks
export { useSpotlight, spotlightQueryKeys } from './hooks/use-spotlight';
export { useRecentSearches } from './hooks/use-recent-searches';

// Components
export { SpotlightDialog } from './components/SpotlightDialog';
