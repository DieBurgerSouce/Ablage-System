/**
 * Privat Module - Main Export
 *
 * Personal Document Management Feature
 */

// Components
export * from './components';

// Pages
export * from './pages';

// API
export * from './api/privat-api';

// React Query Hooks
export * from './hooks/use-privat-queries';

// Explizite Re-Exports (Mehrdeutigkeit Komponenten- vs. API-Typen aufgeloest)
export type { FinancialGoal, PortfolioSnapshot } from './api/privat-api';
