/**
 * Predictive Cash-Flow Feature Module
 *
 * KI-gestuetzte Liquiditaetsprognose und Zahlungsoptimierung.
 */

// Main Dashboard
export { CashflowDashboard } from './CashflowDashboard';

// Components
export { LiquidityChart } from './components/LiquidityChart';
export { RecommendationsTable } from './components/RecommendationsTable';
export { CashflowSummaryCards } from './components/CashflowSummaryCards';

// Hooks
export {
  useLiquidityForecast,
  usePaymentPrediction,
  usePaymentRecommendations,
  useCashflowSummary,
  useRunScenario,
  cashflowKeys,
} from './hooks/use-cashflow';

// API
export {
  getLiquidityForecast,
  predictPayment,
  getPaymentRecommendations,
  runScenario,
  getCashflowSummary,
} from './api/cashflow-api';

// Types
export type {
  PaymentPrediction,
  ForecastDay,
  LiquidityWarning,
  LiquidityForecast,
  PaymentRecommendation,
  ScenarioRequest,
  ScenarioResponse,
  CashflowSummary,
} from './api/cashflow-api';
