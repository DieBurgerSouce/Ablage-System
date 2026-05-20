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
} from './ocr-suite-types';

export {
  transformOcrRegion,
  transformOcrFeedback,
  transformSelfLearningStats,
  transformDocumentVersion,
  transformTemplateZone,
  transformOcrTemplate,
} from './ocr-suite-types';
