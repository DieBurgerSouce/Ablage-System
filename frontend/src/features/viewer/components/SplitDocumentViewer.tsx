import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ScrollSync, ScrollSyncPane } from 'react-scroll-sync';
import SplitPane from 'react-split-pane';
import { FileText, ScanLine, FileCode, Loader2, AlertTriangle, Edit, MessageSquare, Diff, Link2, History, ClipboardList, Pencil } from 'lucide-react';
import { ViewerToolbar } from './ViewerToolbar';
import { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
import { ImageViewer } from './ImageViewer';
import { OCRTextPanel } from './OCRTextPanel';
import { InlineMetadataEditor } from './InlineMetadataEditor';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ExtractedDataPanel } from '@/features/extracted-data';
import { EInvoicePanel } from '@/features/einvoice';
import { CommentsPanel, ActivityStream } from '@/features/collaboration';
import { TypingIndicator } from '@/features/collaboration/components/TypingIndicator';
import { useTypingIndicator } from '@/features/collaboration/hooks/useTypingIndicator';
import { AnnotationOverlay } from '@/features/collaboration/components/AnnotationOverlay';
import { AnnotationSidebar } from '@/features/collaboration/components/AnnotationSidebar';
import { useAnnotations } from '@/features/collaboration/hooks/use-annotations';
import { Button } from '@/components/ui/button';
import { DocumentTasksPanel } from '@/features/collaboration/components/DocumentTasksPanel';
import { OCRDiffViewer } from '@/features/ocr-review/components/OCRDiffViewer';
import { DocumentContextPanel } from './DocumentContextPanel';
import { DocumentLifecycleTab } from './DocumentLifecycleTab';
import { DocumentCustomFields } from '@/features/admin/custom-fields';
import { apiClient } from '@/lib/api/client';
import { AnnotationLayer } from './AnnotationLayer';
import { ViewerErrorBoundary } from '@/components/errors';
import { useViewerShortcuts } from '../hooks/useViewerShortcuts';
import { logger } from '@/lib/logger';
import { usePaperDimming } from '../hooks/usePaperDimming';
import { useTheme } from '@/lib/theme/ThemeContext';

// Lazy load Office/Email viewers
const DocxViewer = lazy(() => import('./DocxViewer'));
const XlsxViewer = lazy(() => import('./XlsxViewer'));
const EmailViewer = lazy(() => import('./EmailViewer'));

// Use CDN for PDF.js worker to avoid Vite bundling issues
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * Hook um Dokument-Preview mit Auth-Token zu laden.
 * Erstellt Object-URL aus Blob für PDF.js/img-Tags.
 */
function useAuthenticatedPreview(documentId: string) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let objectUrl: string | null = null;
        let cancelled = false;

        async function loadPreview() {
            setIsLoading(true);
            setError(null);

            try {
                const response = await apiClient.get(`/documents/${documentId}/preview`, {
                    responseType: 'blob',
                });

                if (cancelled) return;

                const blob = response.data;
                objectUrl = URL.createObjectURL(blob);
                setBlobUrl(objectUrl);
            } catch (err) {
                if (cancelled) return;
                const message = err instanceof Error ? err.message : 'Vorschau konnte nicht geladen werden';
                setError(message);
                logger.error('[Vorschau] Fehler beim Laden:', err);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        }

        loadPreview();

        return () => {
            cancelled = true;
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
            }
        };
    }, [documentId]);

    // Cleanup bei unmount
    useEffect(() => {
        return () => {
            if (blobUrl) {
                URL.revokeObjectURL(blobUrl);
            }
        };
    }, [blobUrl]);

    return { blobUrl, isLoading, error };
}

interface SplitDocumentViewerProps {
    documentId: string;
    ocrResults: import('@/lib/api/services/documents').Document['ocrResults'];
    mimeType?: string;
    extractedText?: string;
}

// Helper to determine if MIME type is an image
function isImageMimeType(mimeType?: string): boolean {
    if (!mimeType) return false;
    return mimeType.startsWith('image/');
}

// Helper to determine file type category
type FileCategory = 'pdf' | 'image' | 'docx' | 'xlsx' | 'email' | 'unknown';

function categorizeFileType(mimeType?: string): FileCategory {
    if (!mimeType) return 'unknown';
    const mime = mimeType.toLowerCase();

    if (mime === 'application/pdf') return 'pdf';
    if (mime.startsWith('image/')) return 'image';
    if (
        mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
        mime === 'application/msword'
    ) {
        return 'docx';
    }
    if (
        mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
        mime === 'application/vnd.ms-excel'
    ) {
        return 'xlsx';
    }
    if (mime === 'message/rfc822') return 'email';

    return 'unknown';
}

// Loading fallback for lazy-loaded viewers
function ViewerLoadingFallback() {
    return (
        <div className="h-full flex items-center justify-center bg-muted/30">
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
                <Loader2 className="h-8 w-8 animate-spin" />
                <span>Lade Viewer...</span>
            </div>
        </div>
    );
}

export function SplitDocumentViewer({ documentId, ocrResults, mimeType, extractedText }: SplitDocumentViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedBox, setSelectedBox] = useState<BoundingBox | null>(null);
    const [pageDimensions, setPageDimensions] = useState<{ width: number; height: number } | null>(null);
    const [activeRightTab, setActiveRightTab] = useState('cockpit');
    const [rotation, setRotation] = useState(0);
    const [isFocusMode, setIsFocusMode] = useState(false);
    const [annotationMode, setAnnotationMode] = useState(false);
    const { data: annotationsData } = useAnnotations(documentId);
    const annotations = annotationsData ?? [];
    const { typingUsers } = useTypingIndicator({ documentId });

    const { enabled, autoActivate, getFilterStyle } = usePaperDimming();
    const { displayMode } = useTheme();

    // Auto-activate paper dimming in dark modes
    const isDarkMode = displayMode === 'dark' || displayMode === 'blackscreen';
    const shouldDim = enabled || (autoActivate && isDarkMode);
    const dimmingStyle = shouldDim ? getFilterStyle() : {};

    // Lade Preview mit Auth-Token
    const { blobUrl, isLoading: previewLoading, error: previewError } = useAuthenticatedPreview(documentId);
    const isImage = isImageMimeType(mimeType);
    const fileCategory = categorizeFileType(mimeType);

    const handleRotate = useCallback(() => {
        setRotation(r => (r + 90) % 360);
    }, []);

    const handleDownload = useCallback(async () => {
        if (!blobUrl) return;
        try {
            const response = await fetch(blobUrl);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dokument-${documentId}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            logger.error('[Viewer] Download fehlgeschlagen:', err);
        }
    }, [blobUrl, documentId]);

    const handlePrint = useCallback(() => {
        window.print();
    }, []);

    const handleToggleFocusMode = useCallback(() => {
        setIsFocusMode(prev => !prev);
    }, []);

    // For images and office docs, we only have 1 "page"
    const effectiveNumPages = isImage || fileCategory === 'docx' || fileCategory === 'xlsx' || fileCategory === 'email'
        ? 1
        : numPages;

    // Keyboard shortcuts für Zoom und Seiten-Navigation
    useViewerShortcuts({
        scale,
        onScaleChange: setScale,
        currentPage,
        numPages: effectiveNumPages,
        onPageChange: setCurrentPage,
        minScale: 0.5,
        maxScale: 3,
        scaleStep: 0.25,
    });

    // Check if this is an Office/Email document that uses a specialized viewer

    // When OCR-Diff tab is active, render full-width diff viewer
    if (activeRightTab === 'ocr-diff') {
        return (
            <div className="h-full flex flex-col">
                <div className="px-4 pt-3 pb-2 border-b bg-background sticky top-0 z-10 flex items-center justify-between">
                    <Tabs value="ocr-diff" onValueChange={setActiveRightTab}>
                        <TabsList className="grid grid-cols-9 max-w-5xl">
                            <TabsTrigger value="cockpit" className="gap-2">
                                <Edit className="h-4 w-4" />
                                Cockpit
                            </TabsTrigger>
                            <TabsTrigger value="extracted" className="gap-2">
                                <FileText className="h-4 w-4" />
                                Extrahiert
                            </TabsTrigger>
                            <TabsTrigger value="ocr" className="gap-2">
                                <ScanLine className="h-4 w-4" />
                                OCR-Text
                            </TabsTrigger>
                            <TabsTrigger value="einvoice" className="gap-2">
                                <FileCode className="h-4 w-4" />
                                E-Rechnung
                            </TabsTrigger>
                            <TabsTrigger value="collaboration" className="gap-2">
                                <MessageSquare className="h-4 w-4" />
                                Diskussion
                            </TabsTrigger>
                            <TabsTrigger value="ocr-diff" className="gap-2">
                                <Diff className="h-4 w-4" />
                                OCR Vergleich
                            </TabsTrigger>
                            <TabsTrigger value="context" className="gap-2">
                                <Link2 className="h-4 w-4" />
                                Kontext
                            </TabsTrigger>
                            <TabsTrigger value="lifecycle" className="gap-2">
                                <History className="h-4 w-4" />
                                Lebenszyklus
                            </TabsTrigger>
                            <TabsTrigger value="tasks" className="gap-2">
                                <ClipboardList className="h-4 w-4" />
                                Aufgaben
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>
                </div>
                <div className="flex-1 overflow-hidden">
                    <OCRDiffViewer documentId={documentId} pageNumber={currentPage} />
                </div>
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col">
            <div className="relative">
                <ViewerToolbar
                    documentId={documentId}
                    currentPage={currentPage}
                    numPages={effectiveNumPages}
                    scale={scale}
                    rotation={rotation}
                    onPageChange={setCurrentPage}
                    onZoomIn={() => setScale(s => Math.min(s + 0.25, 3))}
                    onZoomOut={() => setScale(s => Math.max(s - 0.25, 0.5))}
                    onRotate={handleRotate}
                    onDownload={handleDownload}
                    onPrint={handlePrint}
                    isFocusMode={isFocusMode}
                    onToggleFocusMode={handleToggleFocusMode}
                />
                <div className="absolute top-2 right-4 z-20">
                    <Button
                        variant={annotationMode ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setAnnotationMode(!annotationMode)}
                        title={annotationMode ? 'Annotationsmodus deaktivieren' : 'Annotationsmodus aktivieren'}
                        className="gap-1.5"
                    >
                        <Pencil className="h-4 w-4" />
                        Annotieren
                    </Button>
                </div>
            </div>

            {(() => {
                const documentPane = previewLoading ? (
                    <div className="h-full flex items-center justify-center bg-muted/30">
                        <div className="flex flex-col items-center gap-3 text-muted-foreground">
                            <Loader2 className="h-8 w-8 animate-spin" />
                            <span>Lade Vorschau...</span>
                        </div>
                    </div>
                ) : previewError ? (
                    <div className="h-full flex items-center justify-center bg-muted/30">
                        <div className="flex flex-col items-center gap-3 text-destructive">
                            <AlertTriangle className="h-8 w-8" />
                            <span>Vorschau konnte nicht geladen werden</span>
                            <span className="text-xs text-muted-foreground">{previewError}</span>
                        </div>
                    </div>
                ) : blobUrl && fileCategory === 'docx' ? (
                    <ViewerErrorBoundary fileType="docx">
                        <Suspense fallback={<ViewerLoadingFallback />}>
                            <DocxViewer fileData={blobUrl} className="h-full" />
                        </Suspense>
                    </ViewerErrorBoundary>
                ) : blobUrl && fileCategory === 'xlsx' ? (
                    <ViewerErrorBoundary fileType="xlsx">
                        <Suspense fallback={<ViewerLoadingFallback />}>
                            <XlsxViewer fileData={blobUrl} className="h-full" />
                        </Suspense>
                    </ViewerErrorBoundary>
                ) : blobUrl && fileCategory === 'email' ? (
                    <ViewerErrorBoundary fileType="email">
                        <Suspense fallback={<ViewerLoadingFallback />}>
                            <EmailViewer fileData={blobUrl} className="h-full" />
                        </Suspense>
                    </ViewerErrorBoundary>
                ) : blobUrl && isImage ? (
                    <ViewerErrorBoundary fileType="image">
                        <div className="relative" style={{ ...dimmingStyle, transform: `rotate(${rotation}deg)` }}>
                            <ImageViewer
                                fileUrl={blobUrl}
                                scale={scale}
                                boxes={ocrResults?.pages?.[0]?.boxes || []}
                                selectedBox={selectedBox}
                                onBoxClick={setSelectedBox}
                            />
                            <AnnotationOverlay
                                documentId={documentId}
                                page={1}
                                annotations={annotations}
                                annotationMode={annotationMode}
                                onAnnotationClick={() => {
                                    setActiveRightTab('collaboration');
                                }}
                            />
                        </div>
                    </ViewerErrorBoundary>
                ) : blobUrl ? (
                    <ViewerErrorBoundary fileType="pdf">
                        <div className="h-full overflow-auto bg-muted/30 flex justify-center p-4">
                            <div style={dimmingStyle}>
                                <Document
                                    file={blobUrl}
                                    onLoadSuccess={({ numPages }) => setNumPages(numPages)}
                                    onLoadError={(err) => logger.error('[PDF] Fehler beim Laden:', err)}
                                    className="shadow-lg"
                                >
                                    <div className="relative" style={{ transform: `rotate(${rotation}deg)` }}>
                                        <Page
                                            pageNumber={currentPage}
                                            scale={scale}
                                            renderTextLayer={true}
                                            renderAnnotationLayer={true}
                                            onLoadSuccess={({ width, height }) => setPageDimensions({ width, height })}
                                        />
                                        <BoundingBoxOverlay
                                            boxes={ocrResults?.pages?.[currentPage - 1]?.boxes || []}
                                            scale={scale}
                                            selectedBox={selectedBox}
                                            onBoxClick={setSelectedBox}
                                        />
                                        {pageDimensions && (
                                            <AnnotationLayer
                                                pageNumber={currentPage}
                                                scale={scale}
                                                width={pageDimensions.width}
                                                height={pageDimensions.height}
                                            />
                                        )}
                                        <AnnotationOverlay
                                            documentId={documentId}
                                            page={currentPage}
                                            annotations={annotations}
                                            annotationMode={annotationMode}
                                            onAnnotationClick={() => {
                                                setActiveRightTab('collaboration');
                                            }}
                                        />
                                    </div>
                                </Document>
                            </div>
                        </div>
                    </ViewerErrorBoundary>
                ) : (
                    <div className="h-full bg-muted/30" />
                );

                if (isFocusMode) {
                    return (
                        <div className="flex-1 overflow-auto">
                            {documentPane}
                        </div>
                    );
                }

                return (
                <ScrollSync>
                <div className="flex-1 relative overflow-hidden">
                    {/* @ts-expect-error: SplitPane types are not compatible with React 18 children */}
                    <SplitPane split="vertical" minSize={300} defaultSize="50%" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
                        <ScrollSyncPane>
                            {documentPane}
                        </ScrollSyncPane>

                        <ScrollSyncPane>
                            <div className="h-full overflow-auto bg-background">
                                <Tabs value={activeRightTab} onValueChange={setActiveRightTab} className="h-full flex flex-col">
                                    <div className="px-4 pt-4 pb-2 border-b bg-background sticky top-0 z-10">
                                        <TabsList className="grid w-full grid-cols-9 max-w-5xl">
                                            <TabsTrigger value="cockpit" className="gap-2">
                                                <Edit className="h-4 w-4" />
                                                Cockpit
                                            </TabsTrigger>
                                            <TabsTrigger value="extracted" className="gap-2">
                                                <FileText className="h-4 w-4" />
                                                Extrahiert
                                            </TabsTrigger>
                                            <TabsTrigger value="ocr" className="gap-2">
                                                <ScanLine className="h-4 w-4" />
                                                OCR-Text
                                            </TabsTrigger>
                                            <TabsTrigger value="einvoice" className="gap-2">
                                                <FileCode className="h-4 w-4" />
                                                E-Rechnung
                                            </TabsTrigger>
                                            <TabsTrigger value="collaboration" className="gap-2">
                                                <MessageSquare className="h-4 w-4" />
                                                Diskussion
                                            </TabsTrigger>
                                            <TabsTrigger value="ocr-diff" className="gap-2">
                                                <Diff className="h-4 w-4" />
                                                OCR Vergleich
                                            </TabsTrigger>
                                            <TabsTrigger value="context" className="gap-2">
                                                <Link2 className="h-4 w-4" />
                                                Kontext
                                            </TabsTrigger>
                                            <TabsTrigger value="lifecycle" className="gap-2">
                                                <History className="h-4 w-4" />
                                                Lebenszyklus
                                            </TabsTrigger>
                                            <TabsTrigger value="tasks" className="gap-2">
                                                <ClipboardList className="h-4 w-4" />
                                                Aufgaben
                                            </TabsTrigger>
                                        </TabsList>
                                    </div>
                                    <TabsContent value="cockpit" className="flex-1 overflow-auto mt-0">
                                        <InlineMetadataEditor documentId={documentId} />
                                        <DocumentCustomFields documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="extracted" className="flex-1 p-4 overflow-auto mt-0">
                                        <ExtractedDataPanel documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="ocr" className="flex-1 p-6 overflow-auto mt-0">
                                        <OCRTextPanel
                                            ocrData={ocrResults?.pages?.[currentPage - 1]}
                                            selectedBox={selectedBox}
                                            extractedText={extractedText}
                                        />
                                    </TabsContent>
                                    <TabsContent value="einvoice" className="flex-1 p-4 overflow-auto mt-0">
                                        <EInvoicePanel documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="collaboration" className="flex-1 p-4 overflow-auto mt-0 space-y-6">
                                        <AnnotationSidebar
                                            documentId={documentId}
                                            onAnnotationClick={(annotation) => {
                                                if (annotation.page) {
                                                    setCurrentPage(annotation.page);
                                                }
                                            }}
                                        />
                                        <TypingIndicator typingUsers={typingUsers} className="mb-2" />
                                        <CommentsPanel documentId={documentId} />
                                        <ActivityStream documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="context" className="flex-1 p-4 overflow-auto mt-0">
                                        <DocumentContextPanel documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="lifecycle" className="flex-1 p-4 overflow-auto mt-0">
                                        <DocumentLifecycleTab documentId={documentId} />
                                    </TabsContent>
                                    <TabsContent value="tasks" className="flex-1 p-4 overflow-auto mt-0">
                                        <DocumentTasksPanel documentId={documentId} />
                                    </TabsContent>
                                    {/* ocr-diff tab triggers full-width mode via early return above */}
                                </Tabs>
                            </div>
                        </ScrollSyncPane>
                    </SplitPane>
                </div>
                </ScrollSync>
                );
            })()}
        </div>
    );
}
