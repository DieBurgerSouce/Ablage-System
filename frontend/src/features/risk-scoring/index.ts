/**
 * Risk Scoring Feature Module
 *
 * Public exports fuer das Risk Scoring System.
 */

// Types
export * from './types/risk-types';

// API
export { riskService, RiskApiError } from './api/risk-api';

// Hooks
export {
  riskKeys,
  useRiskStatistics,
  useEntitiesWithRisk,
  useHighRiskEntities,
  useEntityRisk,
  useEntityRiskTrend,
  useCalculateEntityRisk,
  useCalculateAllRisks,
  useRiskDashboard,
  useRiskMutations,
} from './hooks/use-risk-queries';

// Components
export {
  RiskScoreGauge,
  RiskScoreBadge,
  RiskIndicator,
} from './components/RiskScoreGauge';

export {
  RiskFactorBreakdown,
  FactorContributionChart,
} from './components/RiskFactorBreakdown';

export {
  HighRiskEntitiesTable,
  RiskEntityList,
} from './components/HighRiskEntitiesTable';

export {
  RiskTrendChart,
  RiskDistributionChart,
  EntityRiskMiniChart,
} from './components/RiskTrendChart';

export { RiskDashboard } from './components/RiskDashboard';
