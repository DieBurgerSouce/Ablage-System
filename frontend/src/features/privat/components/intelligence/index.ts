/**
 * Intelligence Components - Enterprise-Level Privat-Modul
 *
 * Diese Komponenten bieten erweiterte Finanz-Intelligence:
 * - Financial Health Dashboard (6-Dimensionen Score)
 * - Smart Recommendations Panel
 * - Loan Scenario Simulator (What-If Analysen)
 * - Net Worth Chart (Vermögensaufstellung)
 *
 * Alle Komponenten sind mit Error Boundaries gewrappt für
 * robuste Fehlerbehandlung im Enterprise-Umfeld.
 */

import { withIntelligenceErrorBoundary } from './IntelligenceErrorBoundary';
import { FinancialHealthDashboard as FinancialHealthDashboardBase } from './FinancialHealthDashboard';
import { RecommendationsPanel as RecommendationsPanelBase } from './RecommendationsPanel';
import { LoanScenarioSimulator as LoanScenarioSimulatorBase } from './LoanScenarioSimulator';
import { NetWorthChart as NetWorthChartBase } from './NetWorthChart';

// Wrapped components with Error Boundaries
export const FinancialHealthDashboard = withIntelligenceErrorBoundary(
  FinancialHealthDashboardBase,
  'Financial Health Dashboard'
);

export const RecommendationsPanel = withIntelligenceErrorBoundary(
  RecommendationsPanelBase,
  'Smart Empfehlungen'
);

export const LoanScenarioSimulator = withIntelligenceErrorBoundary(
  LoanScenarioSimulatorBase,
  'Kredit-Simulator'
);

export const NetWorthChart = withIntelligenceErrorBoundary(
  NetWorthChartBase,
  'Nettovermögen'
);

// Re-export Error Boundary for direct usage if needed
export { IntelligenceErrorBoundary, withIntelligenceErrorBoundary } from './IntelligenceErrorBoundary';

// Export base components for cases where error boundary is not desired
export {
  FinancialHealthDashboardBase,
  RecommendationsPanelBase,
  LoanScenarioSimulatorBase,
  NetWorthChartBase,
};
