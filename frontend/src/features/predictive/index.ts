/**
 * Predictive Intelligence Feature Module
 *
 * KI-basierte Vorhersagen und Prognosen:
 * - Cashflow-Prognose mit 30/60/90 Tage Ansicht
 * - Zahlungsvorhersagen mit Risikobewertung
 * - System-Gesundheitsvorhersagen (VRAM, Queue, Disk)
 * - Proaktive Alerts
 */

// Pages
export { PredictiveDashboardPage } from './pages/PredictiveDashboardPage';

// Components
export { CashflowForecast } from './components/CashflowForecast';
export { PaymentPredictions } from './components/PaymentPredictions';
export { SystemHealthDashboard } from './components/SystemHealthDashboard';

// Hooks
export {
  useCashflowForecast,
  usePaymentPredictions,
  useSystemHealth,
  usePredictiveAlerts,
  predictiveKeys,
} from './hooks/use-predictions';

// Types
export type {
  CashflowForecast as CashflowForecastType,
  ForecastDay,
  PaymentPrediction,
  SystemHealthMetric,
  PredictiveAlert,
  ForecastPeriod,
  LiquidityWarning,
} from './types/predictive-types';
