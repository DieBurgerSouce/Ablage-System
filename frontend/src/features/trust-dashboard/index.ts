/**
 * Trust Dashboard Feature - Exports
 *
 * Security & Compliance Monitoring
 */

// Types
export type {
  MetricsResponse,
  SecurityEvent,
  Anomaly,
  TrustDashboardSnapshot,
  SecurityEventsResponse,
  AnomaliesResponse,
} from './api/trust-dashboard-api';

// API
export {
  getTrustDashboardSnapshot,
  getAccessLog,
  getExportLog,
  getAnomalies,
  trustDashboardKeys,
} from './api/trust-dashboard-api';

// Hooks
export {
  useTrustDashboard,
  useAccessLog,
  useExportLog,
  useAnomalies,
} from './hooks/use-trust-dashboard';

// Components
export { TrustDashboardPage } from './components/TrustDashboardPage';
