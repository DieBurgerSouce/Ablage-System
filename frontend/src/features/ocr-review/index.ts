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

// OCR Diff Viewer (Side-by-Side Confidence Comparison)
export { OCRDiffViewer } from './components/OCRDiffViewer'
export { ConfidenceHighlighter } from './components/ConfidenceHighlighter'
export { DocumentOverlay } from './components/DocumentOverlay'
export { ConfidenceLegend } from './components/ConfidenceLegend'
export { ConfidenceStats } from './components/ConfidenceStats'

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
export { useDocumentConfidence, useConfidenceSummary } from './hooks/use-confidence-data'

// API
export * from './api/review-api'
export * from './api/confidence-api'

// Types
export * from './types'
