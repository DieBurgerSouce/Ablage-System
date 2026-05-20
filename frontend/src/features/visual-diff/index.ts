/**
 * Visual Diff Feature - Exports
 *
 * Feature #11: Visual Diff + Timeline
 */

// API
export * from './api/visual-diff-api';

// Hooks
export * from './hooks/use-visual-diff';

// Components
export { VisualDiffPage } from './components/VisualDiffPage';
export { DocumentTimeline } from './components/DocumentTimeline';
export type { TimelineStage } from './components/DocumentTimeline';
export { ImageDiffViewer } from './components/ImageDiffViewer';
