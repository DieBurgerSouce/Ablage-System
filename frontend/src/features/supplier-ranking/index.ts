/**
 * Supplier Ranking Feature Module
 *
 * Public exports für das Lieferanten-Ranking System.
 */

// Types
export * from './types/supplier-ranking-types';

// API
export { supplierRankingService, SupplierRankingApiError } from './api/supplier-ranking-api';

// Hooks
export {
  supplierRankingKeys,
  useSupplierRankingReport,
  useSupplierRanking,
  useTierDistribution,
  useSupplierComparison,
  useCompareSuppliersMutation,
  useSupplierRankingDashboard,
} from './hooks/use-supplier-ranking-queries';

// Components
export {
  SupplierScoreCard,
  ScoreBadge,
  TierBadge,
} from './components/SupplierScoreCard';

export {
  RankingFactors,
  CategoryComparisonChart,
  CategoryScoreSummary,
} from './components/RankingFactors';

export { SupplierRankingTable } from './components/SupplierRankingTable';

export { SupplierRankingDashboard } from './components/SupplierRankingDashboard';
