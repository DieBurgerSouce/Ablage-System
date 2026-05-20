/**
 * Finanzen Feature Hooks - Barrel Export
 */

// Query Hooks
export {
  finanzenQueryKeys,
  useFinanceYears,
  useFinanceYear,
  useFinanceYearPage,
  useFinanceCategoryDocuments,
  useFinanceCategoryAggregations,
  useFinanceCategoryPage,
  useFinanceDocument,
  useFinanceOverallAggregations,
  useFinanceYearAggregations,
  useFinanceDeadlines,
  useFinanceDashboard,
  useInvalidateFinanceQueries,
  useUploadFinanceDocument,
  useUpdateFinanceDocument,
  useDeleteFinanceDocument,
  useFinanceDocumentHistory,
  useFinanceDocumentVersions,
  useFinanceDocumentVersion,
  useFinanceVersionCompare,
  useRollbackToVersion,
} from './use-finanzen-queries'

// WebSocket Hook
export {
  useFinanceWebSocket,
  type FinanceEventType,
  type FinanceWebSocketEvent,
  type UseFinanceWebSocketOptions,
  type UseFinanceWebSocketReturn,
} from './use-finance-websocket'
