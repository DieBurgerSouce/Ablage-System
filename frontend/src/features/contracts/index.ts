/**
 * Contracts Feature - Vertragsmanagement
 *
 * B2B-Vertragsverwaltung mit:
 * - Vertragslaufzeiten
 * - Kuendigungsfristen
 * - Verlaengerungsoptionen
 * - Meilensteine
 * - Nachtraege
 */

// Pages
export { ContractsPage } from './pages/ContractsPage';

// Components
export { ContractStatsCards } from './components/ContractStatsCards';
export { ContractDeadlineAlerts } from './components/ContractDeadlineAlerts';
export { ContractTable } from './components/ContractTable';
export { ContractFilters } from './components/ContractFilters';
export { ContractDetailSheet } from './components/ContractDetailSheet';
export { ContractFormDialog } from './components/ContractFormDialog';

// API
export * from './api/contracts-api';

// Types
export * from './types/contract-types';
