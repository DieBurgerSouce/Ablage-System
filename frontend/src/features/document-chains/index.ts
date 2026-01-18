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
  // Individual Hooks
  useChains,
  useChain,
  useDocumentChain,
  useAutoMatch,
  useDiscrepancies,
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

// Components
export { ChainCard, ChainCardCompact } from './components/ChainCard';
export { ChainVisualization } from './components/ChainVisualization';
export { DiscrepancyPanel } from './components/DiscrepancyPanel';
export { AutoMatchDialog } from './components/AutoMatchDialog';
export { CreateChainDialog } from './components/CreateChainDialog';
export { ChainListPage } from './components/ChainListPage';
export { ChainDetailPage } from './components/ChainDetailPage';
