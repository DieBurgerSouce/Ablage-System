import { useState, useEffect } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ScrollSync, ScrollSyncPane } from 'react-scroll-sync';
import SplitPane from 'react-split-pane';
import { FileText, ScanLine, FileCode, Loader2, AlertTriangle } from 'lucide-react';
import { ViewerToolbar } from './ViewerToolbar';
import { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
import { ImageViewer } from './ImageViewer';
import { OCRTextPanel } from './OCRTextPanel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ExtractedDataPanel } from '@/features/extracted-data';
import { EInvoicePanel } from '@/features/einvoice';
import { apiClient } from '@/lib/api/client';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
).toString();

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
                console.error('[Preview] Load error:', err);
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

export function SplitDocumentViewer({ documentId, ocrResults, mimeType, extractedText }: SplitDocumentViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedBox, setSelectedBox] = useState<BoundingBox | null>(null);

    // Lade Preview mit Auth-Token
    const { blobUrl, isLoading: previewLoading, error: previewError } = useAuthenticatedPreview(documentId);
    const isImage = isImageMimeType(mimeType);

    // For images, we only have 1 "page"
    const effectiveNumPages = isImage ? 1 : numPages;

    return (
        <div className="h-full flex flex-col">
            <ViewerToolbar
                currentPage={currentPage}
                numPages={effectiveNumPages}
                scale={scale}
                onPageChange={setCurrentPage}
                onZoomIn={() => setScale(s => Math.min(s + 0.25, 3))}
                onZoomOut={() => setScale(s => Math.max(s - 0.25, 0.5))}
            />

            <ScrollSync>
                <div className="flex-1 relative overflow-hidden">
                    {/* @ts-expect-error: SplitPane types are not compatible with React 18 children */}
                    <SplitPane split="vertical" minSize={300} defaultSize="50%" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}>
                        <ScrollSyncPane>
                            {previewLoading ? (
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
                            ) : blobUrl && isImage ? (
                                <ImageViewer
                                    fileUrl={blobUrl}
                                    scale={scale}
                                    boxes={ocrResults?.pages?.[0]?.boxes || []}
                                    selectedBox={selectedBox}
                                    onBoxClick={setSelectedBox}
                                />
                            ) : blobUrl ? (
                                <div className="h-full overflow-auto bg-muted/30 flex justify-center p-4">
                                    <Document
                                        file={blobUrl}
                                        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
                                        onLoadError={(err) => console.error('[PDF] Load error:', err)}
                                        className="shadow-lg"
                                    >
                                        <div className="relative">
                                            <Page
                                                pageNumber={currentPage}
                                                scale={scale}
                                                renderTextLayer={true}
                                                renderAnnotationLayer={true}
                                            />
                                            <BoundingBoxOverlay
                                                boxes={ocrResults?.pages?.[currentPage - 1]?.boxes || []}
                                                scale={scale}
                                                selectedBox={selectedBox}
                                                onBoxClick={setSelectedBox}
                                            />
                                        </div>
                                    </Document>
                                </div>
                            ) : (
                                <div className="h-full bg-muted/30" />
                            )}
                        </ScrollSyncPane>

                        <ScrollSyncPane>
                            <div className="h-full overflow-auto bg-background">
                                <Tabs defaultValue="extracted" className="h-full flex flex-col">
                                    <div className="px-4 pt-4 pb-2 border-b bg-background sticky top-0 z-10">
                                        <TabsList className="grid w-full grid-cols-3 max-w-md">
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
                                        </TabsList>
                                    </div>
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
                                </Tabs>
                            </div>
                        </ScrollSyncPane>
                    </SplitPane>
                </div>
            </ScrollSync>
        </div>
    );
}
