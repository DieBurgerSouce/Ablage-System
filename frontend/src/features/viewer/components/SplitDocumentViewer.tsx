import { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ScrollSync, ScrollSyncPane } from 'react-scroll-sync';
import SplitPane from 'react-split-pane';
import { FileText, ScanLine } from 'lucide-react';
import { ViewerToolbar } from './ViewerToolbar';
import { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
import { ImageViewer } from './ImageViewer';
import { OCRTextPanel } from './OCRTextPanel';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ExtractedDataPanel } from '@/features/extracted-data';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
).toString();

interface SplitDocumentViewerProps {
    documentId: string;
    ocrResults: import('@/lib/api/services/documents').Document['ocrResults'];
    fileUrl?: string;
    mimeType?: string;
    extractedText?: string;
}

// Helper to determine if MIME type is an image
function isImageMimeType(mimeType?: string): boolean {
    if (!mimeType) return false;
    return mimeType.startsWith('image/');
}

export function SplitDocumentViewer({ documentId, ocrResults, fileUrl, mimeType, extractedText }: SplitDocumentViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedBox, setSelectedBox] = useState<BoundingBox | null>(null);

    const resolvedFileUrl = fileUrl || `/documents/${documentId}/preview`;
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
                            {isImage ? (
                                <ImageViewer
                                    fileUrl={resolvedFileUrl}
                                    scale={scale}
                                    boxes={ocrResults?.pages?.[0]?.boxes || []}
                                    selectedBox={selectedBox}
                                    onBoxClick={setSelectedBox}
                                />
                            ) : (
                            <div className="h-full overflow-auto bg-muted/30 flex justify-center p-4">
                                    <Document
                                        file={resolvedFileUrl}
                                        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
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
                            )}
                        </ScrollSyncPane>

                        <ScrollSyncPane>
                            <div className="h-full overflow-auto bg-background">
                                <Tabs defaultValue="extracted" className="h-full flex flex-col">
                                    <div className="px-4 pt-4 pb-2 border-b bg-background sticky top-0 z-10">
                                        <TabsList className="grid w-full grid-cols-2 max-w-sm">
                                            <TabsTrigger value="extracted" className="gap-2">
                                                <FileText className="h-4 w-4" />
                                                Extrahiert
                                            </TabsTrigger>
                                            <TabsTrigger value="ocr" className="gap-2">
                                                <ScanLine className="h-4 w-4" />
                                                OCR-Text
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
                                </Tabs>
                            </div>
                        </ScrollSyncPane>
                    </SplitPane>
                </div>
            </ScrollSync>
        </div>
    );
}
