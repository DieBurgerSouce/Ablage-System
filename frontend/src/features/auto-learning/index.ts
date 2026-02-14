/**
 * Auto-Learning Feature - Barrel Exports
 *
 * KI-Entscheidungen, Review-Batch, Lernfortschritt-Statistiken
 */

export { RecentActionsPanel } from './components/RecentActionsPanel'
export { DailyReviewBatch } from './components/DailyReviewBatch'
export { LearningStatsCard } from './components/LearningStatsCard'
export {
    useRecentAutoActions,
    useReviewBatch,
    useLearningStats,
    usePendingReviewCount,
    useReviewDecision,
    autoLearningQueryKeys,
} from './hooks/use-auto-learning'
export type { AIDecision, AccuracyStats, ReviewActionType, ReviewPayload } from './types'
