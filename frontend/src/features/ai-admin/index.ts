/**
 * AI Admin Feature Module
 *
 * Exports fuer AI Autonomy Verwaltung.
 */

// Pages
export { AIAdminPage } from './pages/AIAdminPage';

// Components
export { AISettingsPanel } from './components/AISettingsPanel';
export { AIStatsOverview } from './components/AIStatsOverview';
export { FeedbackQueue } from './components/FeedbackQueue';

// Hooks
export {
  useThresholds,
  useUpdateThreshold,
  useDecisions,
  useDecision,
  useReviewDecision,
  usePendingReviewCount,
  useAccuracyStats,
  useLearningProgress,
  useThresholdSuggestions,
  useApplyThresholdSuggestion,
} from './hooks/useAIAdmin';

// API
export {
  listThresholds,
  updateThreshold,
  listDecisions,
  getDecision,
  reviewDecision,
  getPendingReviewCount,
  getAccuracyStats,
  getLearningProgress,
  getThresholdSuggestions,
  applyThresholdSuggestion,
  aiAdminKeys,
} from './api/ai-admin-api';

// Types
export type {
  DecisionType,
  ConfidenceLevel,
  ReviewAction,
  ThresholdConfig,
  ThresholdUpdateRequest,
  Decision,
  ReviewRequest,
  AccuracyStats,
  ThresholdSuggestion,
  PendingReviewCount,
  LearningProgressReport,
} from './types';
