/**
 * OCR Self-Learning Module
 *
 * Exports für das selbstlernende OCR-System.
 */

// Main Dashboard
export { OCRLearningDashboard } from './OCRLearningDashboard';

// Components
export {
  LearningStatsCards,
  ConfidenceAdjustmentsChart,
  ABTestCard,
  FieldAdjustmentsTable,
  LearningModeSelector,
  ModelMetricsCard,
} from './components';

// Hooks
export {
  useLearningStats,
  useConfidenceStats,
  useABTestResult,
  useCurrentModelVersion,
  useSubmitCorrectionFeedback,
  useCalibrateConfidence,
  useStartABTest,
  useEndABTest,
  useSetLearningMode,
  ocrLearningKeys,
} from './hooks/use-ocr-learning';

// API Functions
export {
  submitCorrectionFeedback,
  getCalibratedConfidence,
  getConfidenceStats,
  startABTest,
  getABTestResult,
  endABTest,
  getLearningStats,
  setLearningMode,
  getCurrentModelVersion,
} from './api/ocr-learning-api';

// Types
export type {
  CorrectionFeedbackRequest,
  CorrectionFeedbackResponse,
  CalibratedConfidenceRequest,
  CalibratedConfidenceResponse,
  ConfidenceStats,
  ABTestStartRequest,
  ABTestConfig,
  ABTestResult,
  LearningStats,
  ModelVersionResponse,
} from './api/ocr-learning-api';
