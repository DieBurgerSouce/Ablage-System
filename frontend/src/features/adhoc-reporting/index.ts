/**
 * Ad-Hoc Reporting Feature Module
 * German Enterprise Document Platform
 */

// Types
export type {
  DataSource,
  Column,
  ReportDefinition,
  ReportConfig,
  Filter,
  Aggregation,
  ExecutionResult,
  ExportFormat,
  ShareInfo,
  Schedule,
  FilterOperator,
  AggregationFunction,
} from './types/adhoc-reporting-types';

export {
  FILTER_OPERATOR_LABELS,
  AGGREGATION_FUNCTION_LABELS,
  DATA_SOURCE_LABELS,
  FREQUENCY_LABELS,
  PERMISSION_LABELS,
  EXPORT_FORMAT_LABELS,
  toBackendReportDefinition,
  fromBackendReportDefinition,
} from './types/adhoc-reporting-types';

// API
export { adhocReportingApi } from './api/adhoc-reporting-api';

// Hooks
export {
  useDataSources,
  useDataSourceColumns,
  useReports,
  useReport,
  useCreateReport,
  useUpdateReport,
  useDeleteReport,
  useExecuteReport,
  useExecuteReportMutation,
  useExportReport,
  useShareReport,
  useRemoveShare,
  useSchedules,
  useScheduleReport,
  useUpdateSchedule,
  useDeleteSchedule,
  adhocReportingKeys,
} from './hooks/use-adhoc-reporting-queries';

// Components
export {
  DataSourceSelector,
  ColumnConfigurator,
  FilterBuilder,
  GroupingAggregation,
  ReportPreview,
  ReportList,
  ScheduleEditor,
  ShareDialog,
  ExportButtons,
  ReportBuilder,
} from './components';

// Pages
export { ReportListPage } from './pages/ReportListPage';
export { ReportBuilderPage } from './pages/ReportBuilderPage';
export { ReportViewPage } from './pages/ReportViewPage';
