/**
 * OCR Review Feature
 * Self-Learning OCR Verification und Korrektur-System
 */

// Components
export { ReviewDashboard } from './components/ReviewDashboard'
export { ReviewWorkspace } from './components/ReviewWorkspace'
export { CorrectionEditor } from './components/CorrectionEditor'
export { QueueStatsCards, CoverageByType, PriorityBreakdown } from './components/QueueStatsCards'
export { LearningProgressPanel } from './components/LearningProgressPanel'
export { KeyboardShortcutsHelp, ShortcutHint } from './components/KeyboardShortcutsHelp'

// Hooks
export {
    useQueueStats,
    useNextSample,
    useSampleDetail,
    useLLMReview,
    useLearnedWeights,
    useVerifySample,
    useSubmitCorrection,
} from './hooks/use-review-queries'
export { useKeyboardShortcuts, KEYBOARD_SHORTCUTS } from './hooks/use-keyboard-shortcuts'

// API
export * from './api/review-api'

// Types
export * from './types'
