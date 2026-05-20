// Components
export { OcrFeedbackViewer } from './components/OcrFeedbackViewer';
export { DocumentDiffViewer } from './components/DocumentDiffViewer';
export { SelfLearningDashboard } from './components/SelfLearningDashboard';
export { OcrTemplateEditor } from './components/OcrTemplateEditor';

// Pages
export { OcrSuitePage } from './pages/OcrSuitePage';

// Hooks
export {
  useOcrRegions,
  useSubmitOcrFeedback,
  useSelfLearningStats,
  useDocumentVersions,
  ocrSuiteKeys,
} from './hooks/use-ocr-suite-queries';

// API
export {
  getOcrRegions,
  submitOcrFeedback,
  getSelfLearningStats,
  getDocumentVersions,
  getDocumentVersion,
} from './api';

// Types
export type {
  OcrRegion,
  OcrRegionBackend,
  OcrFeedbackRequest,
  OcrFeedbackBackend,
  SelfLearningStats,
  SelfLearningStatsBackend,
  DocumentVersion,
  DocumentVersionBackend,
  TemplateZone,
  TemplateZoneBackend,
  OcrTemplate,
  OcrTemplateBackend,
} from './types';

export {
  transformOcrRegion,
  transformOcrFeedback,
  transformSelfLearningStats,
  transformDocumentVersion,
  transformTemplateZone,
  transformOcrTemplate,
} from './types';
