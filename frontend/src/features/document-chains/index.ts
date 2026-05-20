/**
 * Document Chains Feature - Barrel Exports
 *
 * Auftragsketten-Tracking: Angebot → Auftrag → Lieferschein → Rechnung
 */

// Types
export * from './types/chain-types';

// API
export { chainService, ChainApiError } from './api/chain-api';

// Hooks
export {
  // Query Keys
  chainQueryKeys,
  chainIntelligenceQueryKeys,
  // Individual Hooks
  useChains,
  useChain,
  useDocumentChain,
  useAutoMatch,
  useDiscrepancies,
  // Intelligence Hooks
  useChainGaps,
  useOrphanDocuments,
  useChainSuggestions,
  // Mutations
  useCreateChain,
  useLinkDocuments,
  useRemoveLink,
  useResolveDiscrepancy,
  // Combined Hooks
  useChainPage,
  useChainMutations,
  // Prefetch Hooks
  usePrefetchChain,
  // Utility
  useInvalidateChainQueries,
} from './hooks/use-chain-queries';

// Intelligence API
export {
  chainIntelligenceService,
  type ChainGap,
  type GapSeverity,
  type OrphanDocument,
  type ChainIntelligenceReport,
  type ChainSuggestionsResponse,
} from './api/chain-intelligence-api';

// Components
export { ChainCard, ChainCardCompact } from './components/ChainCard';
export { ChainVisualization } from './components/ChainVisualization';
export { DiscrepancyPanel } from './components/DiscrepancyPanel';
export { AutoMatchDialog } from './components/AutoMatchDialog';
export { CreateChainDialog } from './components/CreateChainDialog';
export { ChainListPage } from './components/ChainListPage';
export { ChainDetailPage } from './components/ChainDetailPage';
export { ChainGapAlerts } from './components/ChainGapAlerts';
export { ChainCompletenessBar } from './components/ChainCompletenessBar';
