import { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { ScrollSync, ScrollSyncPane } from 'react-scroll-sync';
import SplitPane from 'react-split-pane';
import { ViewerToolbar } from './ViewerToolbar';
import { BoundingBoxOverlay, type BoundingBox } from './BoundingBoxOverlay';
import { OCRTextPanel } from './OCRTextPanel';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
).toString();

interface SplitDocumentViewerProps {
    documentId: string;
    ocrResults: any;
    fileUrl?: string;
}

export function SplitDocumentViewer({ documentId, ocrResults, fileUrl }: SplitDocumentViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedBox, setSelectedBox] = useState<BoundingBox | null>(null);

    const handleTextEdit = (id: string, text: string) => {
        console.log('Edit text', id, text);
    };

    return (
        <div className="h-full flex flex-col">
            <ViewerToolbar
                currentPage={currentPage}
                numPages={numPages}
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
                            <div className="h-full overflow-auto bg-muted/30 flex justify-center p-4">
                                <Document
                                    file={fileUrl || `/api/documents/${documentId}/file`}
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
                        </ScrollSyncPane>

                        <ScrollSyncPane>
                            <div className="h-full overflow-auto p-6 bg-background">
                                <OCRTextPanel
                                    ocrData={ocrResults?.pages?.[currentPage - 1]}
                                    selectedBox={selectedBox}
                                    onBoxSelect={setSelectedBox}
                                    onTextEdit={handleTextEdit}
                                />
                            </div>
                        </ScrollSyncPane>
                    </SplitPane>
                </div>
            </ScrollSync>
        </div>
    );
}
