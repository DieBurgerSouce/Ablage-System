/**
 * Viewer Components - Export Index
 *
 * Exportiert alle Viewer-Komponenten für die Dokumentenvorschau.
 */

// Core viewers
export { SplitDocumentViewer } from './SplitDocumentViewer';
export { ImageViewer } from './ImageViewer';
export { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
export { OCRTextPanel } from './OCRTextPanel';
export { ViewerToolbar } from './ViewerToolbar';
export { AnnotationLayer } from './AnnotationLayer';
export { SimilarDocumentsDrawer } from './SimilarDocumentsDrawer';

// Office document viewers
export { DocxViewer } from './DocxViewer';
export { XlsxViewer } from './XlsxViewer';

// Email viewer
export { EmailViewer } from './EmailViewer';

// File preview router
export {
    FilePreviewRouter,
    categorizeFileType,
    getFileTypeName,
    type FileCategory,
    type SupportedMimeType,
} from './FilePreviewRouter';
