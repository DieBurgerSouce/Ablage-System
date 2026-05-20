/**
 * Invoices Feature - Barrel Exports
 *
 * Rechnungsverfolgung mit Mahnstufen-Management
 */

// Types
export * from './types/invoice-types';

// API
export { invoiceService, InvoiceApiError, computeKPIs } from './api/invoice-api';

// Hooks
export {
  // Query Keys
  invoiceQueryKeys,
  // Individual Hooks
  useInvoices,
  useInvoiceStatistics,
  useInvoice,
  // Mutations
  useCreateInvoice,
  useUpdateInvoice,
  useMarkInvoicePaid,
  useIncreaseDunning,
  useDeleteInvoice,
  // Skonto Hooks (NEU)
  useSkonto,
  useUpcomingSkontoDeadlines,
  useUpdateSkonto,
  useApplySkonto,
  // Teilzahlung Hooks (NEU)
  usePayments,
  useAddPayment,
  useDeletePayment,
  // Combined Hooks
  useInvoicePage,
  useInvoiceMutations,
  // Prefetch Hooks
  usePrefetchInvoices,
  usePrefetchInvoicePage,
  // Utility
  useInvalidateInvoiceQueries,
} from './hooks/use-invoice-queries';

// Components
export { DunningLevelBadge, DunningLevelBadgeCompact } from './components/DunningLevelBadge';
export { InvoiceStatsCards } from './components/InvoiceStatsCards';
// Skonto Components (NEU)
export {
  SkontoAlertBadge,
  SkontoAlertBadgeCompact,
  SkontoExpiringAlert,
} from './components/SkontoAlertBadge';
export { SkontoDetailPanel } from './components/SkontoDetailPanel';
// Teilzahlung Components (NEU)
export { PaymentHistoryPanel } from './components/PaymentHistoryPanel';
export { InvoiceFilterBar } from './components/InvoiceFilterBar';
export { InvoiceTable } from './components/InvoiceTable';
export { InvoiceActions } from './components/InvoiceActions';
export { InvoiceDetailSheet } from './components/InvoiceDetailSheet';
export { InvoiceStatusChart } from './components/InvoiceStatusChart';
export { InvoicePagination } from './components/InvoicePagination';
export { InvoiceListPage } from './components/InvoiceListPage';
export { InvoiceOverviewPage } from './components/InvoiceOverviewPage';
