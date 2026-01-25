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

// Components (use barrel export)
export * from './components';

// Pages
export { RiskProfilePage } from './pages/RiskProfilePage';
