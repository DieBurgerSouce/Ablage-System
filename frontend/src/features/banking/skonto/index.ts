/**
 * Skonto Feature Barrel Export
 *
 * Exportiert alle öffentlichen APIs des Skonto-Features.
 */

// Types
export type {
  SkontoInfo,
  SkontoOpportunity,
  MissedSkontoItem,
  MissedSkontoResponse,
  SkontoStatistics,
  MonthlySkontoSummary,
  ApplySkontoRequest,
  SetSkontoRequest,
  MissedSkontoFilter,
} from './types';

export { SKONTO_LABELS, SKONTO_COLORS } from './types';

// API
export {
  getSkontoInfo,
  setSkonto,
  applySkonto,
  getUpcomingSkonto,
  getMissedSkonto,
  getSkontoStatistics,
  getMonthlySkontoSummary,
  exportMissedSkonto,
} from './api';

// Hooks
export {
  skontoKeys,
  useSkontoInfo,
  useSetSkonto,
  useApplySkonto,
  useUpcomingSkonto,
  useMissedSkonto,
  useSkontoStatistics,
  useMonthlySkontoSummary,
  useExportMissedSkonto,
} from './hooks';

// Components
export {
  SkontoDeadlineCounter,
  ApplySkontoDialog,
  SkontoAlertBanner,
  SkontoOpportunityWidget,
} from './components';

// Pages
export { MissedSkontoDashboard } from './MissedSkontoDashboard';
