/**
 * Digital Twin Feature - Exports
 *
 * 360° Business Snapshot mit Echtzeit-Monitoring
 */

// Types
export type {
  FinancialHealth,
  RiskEntity,
  RiskOverview,
  DocumentPipeline,
  ComplianceStatus,
  KeyMetrics,
  TrendIndicator,
  Trends,
  DigitalTwinSnapshot,
} from './api/digital-twin-api';

// API
export {
  getDigitalTwinSnapshot,
  getDigitalTwinSection,
  digitalTwinKeys,
} from './api/digital-twin-api';

// Hooks
export {
  useDigitalTwinSnapshot,
  useDigitalTwinSection,
} from './hooks/use-digital-twin';

// Components
export { DigitalTwinDashboard } from './components/DigitalTwinDashboard';
