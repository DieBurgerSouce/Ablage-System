/**
 * Holding Feature Module
 *
 * Multi-Company Holding-Dashboard mit konsolidierten KPIs.
 */

// Main Component
export { HoldingDashboard } from './HoldingDashboard';

// Components
export { FinancialsCard } from './components/FinancialsCard';
export { CompanyComparisonChart } from './components/CompanyComparisonChart';
export { CashFlowChart } from './components/CashFlowChart';
export { IntercompanyCard } from './components/IntercompanyCard';
export { HoldingStatsCards } from './components/HoldingStatsCards';
export { CompanySelector } from './components/CompanySelector';

// Hooks
export {
  useHoldingOverview,
  useHoldingCompanies,
  useCompanyComparison,
  useIntercompanyMetrics,
  useCashFlowOverview,
  holdingKeys,
} from './hooks/use-holding';

// API
export * from './api/holding-api';
