/**
 * Fraud Detection Feature Module
 *
 * KI-gestuetzte Betrugserkennung und Risikoanalyse.
 */

// Main Dashboard
export { FraudDashboard } from './FraudDashboard';

// Components
export { FraudStatsCards } from './components/FraudStatsCards';
export { FraudAlertsTable } from './components/FraudAlertsTable';
export { FraudTypesChart } from './components/FraudTypesChart';
export { RiskLevelDistribution } from './components/RiskLevelDistribution';

// Hooks
export {
  useFraudAnalysis,
  useFraudDashboard,
  useFraudAlerts,
  useFraudConfig,
  useUpdateFraudConfig,
  useFraudTypes,
  useRiskLevels,
  useEntityRiskProfile,
  fraudKeys,
} from './hooks/use-fraud';

// API
export {
  analyzeFraud,
  getFraudDashboard,
  getFraudAlerts,
  getFraudConfig,
  updateFraudConfig,
  getFraudTypes,
  getRiskLevels,
  getEntityRiskProfile,
} from './api/fraud-api';

// Types
export type {
  FraudAlert,
  FraudSummary,
  FraudAnalysis,
  FraudDashboardStats,
  FraudConfig,
  FraudType,
  RiskLevel,
  EntityRiskProfile,
} from './api/fraud-api';
