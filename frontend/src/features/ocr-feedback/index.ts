/**
 * OCR Feedback Module
 *
 * Exports fuer das OCR Feedback System mit Gamification.
 * Leaderboard, Punkte, Achievements und Korrektur-Queue.
 */

// Main Page
export { OCRFeedbackPage } from './OCRFeedbackPage';

// Components
export {
  StreakBadge,
  LeaderboardTable,
  UserStatsCard,
  CorrectionQueue,
  CorrectionDialog,
} from './components';

// Hooks
export {
  useLeaderboard,
  useUserStats,
  useUserStatsById,
  useCorrectionQueue,
  useCorrectionQueueInfinite,
  useClaimQueueItem,
  useSubmitCorrection,
  useSubmitBatchCorrections,
  useAchievements,
  ocrFeedbackKeys,
} from './hooks/use-ocr-feedback';

// API Functions
export {
  getLeaderboard,
  getUserStats,
  getUserStatsById,
  getCorrectionQueue,
  claimQueueItem,
  submitCorrection,
  submitBatchCorrections,
  getAchievements,
} from './api/ocr-feedback-api';

// Types
export type {
  LeaderboardEntry,
  LeaderboardResponse,
  UserStats,
  RecentCorrection,
  QueueItem,
  QueueResponse,
  CorrectionRequest,
  CorrectionResult,
  Achievement,
  AchievementsResponse,
  LeaderboardPeriod,
  QueuePriority,
} from './api/ocr-feedback-api';
