/**
 * Contracts Feature - Vertragsmanagement
 *
 * B2B-Vertragsverwaltung mit:
 * - Vertragslaufzeiten
 * - Kuendigungsfristen
 * - Verlaengerungsoptionen
 * - Meilensteine
 * - Nachtraege
 * - iCal Kalender-Export
 * - Kalenderansicht fuer Fristen
 * - Schnellaktionen
 */

// Pages
export { ContractsPage } from './pages/ContractsPage';

// Components
export { ContractStatsCards } from './components/ContractStatsCards';
export { ContractDeadlineAlerts } from './components/ContractDeadlineAlerts';
export { ContractDeadlineCalendar } from './components/ContractDeadlineCalendar';
export { ContractQuickActions } from './components/ContractQuickActions';
export { ContractTable } from './components/ContractTable';
export { ContractFilters } from './components/ContractFilters';
export { ContractDetailSheet } from './components/ContractDetailSheet';
export { ContractFormDialog } from './components/ContractFormDialog';
export { ContractTimeline } from './components/ContractTimeline';
export { ContractCalendarExport } from './components/ContractCalendarExport';

// Hooks
export {
  // Query Keys
  contractQueryKeys,
  // List Queries
  useContracts,
  useContractsInfinite,
  // Detail Queries
  useContract,
  useContractTimeline,
  // Summary & Statistics
  useContractSummary,
  useUpcomingDeadlines,
  useRenewalOptions,
  // Contract Mutations
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
  // Milestone Mutations
  useCreateMilestone,
  useUpdateMilestone,
  useCompleteMilestone,
  useDeleteMilestone,
  // Renewal Decision
  useRenewalDecision,
  // Amendment Mutations
  useCreateAmendment,
  useUpdateAmendment,
  useDeleteAmendment,
  useApproveAmendment,
  // iCal Export
  useICalExport,
  // Bulk Operations
  useBulkExport,
  useBulkSendReminders,
  // Utility Hooks
  useInvalidateContractQueries,
  // Combined Hooks
  useContractsPage,
  useContractDetail,
  useContractMutations,
} from './hooks/useContracts';

// API (Legacy - use hooks instead)
export * from './api/contracts-api';

// Types
export * from './types/contract-types';
