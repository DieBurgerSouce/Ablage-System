/**
 * Finanzen Feature Components - Barrel Export
 *
 * Alle Komponenten fuer das Finanzen-Modul
 */

// Main Pages
export { FinanzenPage } from './FinanzenPage'
export { FinanceCategoryDocumentList } from './FinanceCategoryDocumentList'
export { FinanzenYearCategoriesView } from './FinanzenYearCategoriesView'

// Dashboard Components
export { FinanzenAggregations } from './FinanzenAggregations'
export { FinanceDeadlineAlert } from './FinanceDeadlineAlert'
export { FinanceDeadlineCalendar } from './FinanceDeadlineCalendar'

// Document Components
export { FinanceDocumentCard } from './FinanceDocumentCard'
export { FinanceDocumentUploadDialog } from './FinanceDocumentUploadDialog'
export { FinanceDocumentEditDialog } from './FinanceDocumentEditDialog'
export { FinanceMultiFileUpload } from './FinanceMultiFileUpload'

// Dialogs
export { FinanceFilterDialog } from './FinanceFilterDialog'
export { AccessibleDialog, AccessibleFormField, LiveRegion } from './AccessibleDialog'

// History / Audit Trail
export { FinanceDocumentHistory } from './FinanceDocumentHistory'

// Versioning
export { FinanceDocumentVersions } from './FinanceDocumentVersions'

// Reports & Export
export { FinanceExportDialog } from './FinanceExportDialog'
export { FinanceReportPanel } from './FinanceReportPanel'

// Bulk Actions
export { FinanceBulkActionsBar } from './FinanceBulkActionsBar'

// Real-time Status
export { FinanceWebSocketStatus, FinanceWebSocketDot } from './FinanceWebSocketStatus'

// Error & Loading
export { FinanceErrorBoundary, FinanceErrorCard, FinanceErrorAlert, useFinanceError, classifyError } from './FinanceErrorBoundary'
export {
  FinanceDashboardSkeleton,
  FinanceCategoryGridSkeleton,
  FinanceDocumentTableSkeleton,
  FinanceDocumentCardSkeleton,
  FinanceAggregationsSkeleton,
  FinanceKPICardSkeleton,
  FinanceYearCardSkeleton,
  FinanceCategoryCardSkeleton,
  FinanceLoadingSpinner,
  FinanceFullPageLoader,
} from './FinanceSkeleton'
