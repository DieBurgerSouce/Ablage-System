/**
 * Split View Layout für OCR Review
 * Zeigt PDF-Vorschau links und Daten/OCR-Text rechts nebeneinander
 * mit verlinkter Hervorhebung.
 */

import {
    ResizablePanelGroup,
    ResizablePanel,
    ResizableHandle,
} from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
    FileText,
    LayoutGrid,
    AlignLeft,
    ZoomIn,
    ZoomOut,
    RotateCcw,
} from 'lucide-react'

import { StructuredReviewPanel } from './StructuredReviewPanel'
import { CorrectionEditor } from './CorrectionEditor'
import type { CorrectionType, QueueItem } from '../types'
import type { UseExtractedDataForReviewReturn } from '../hooks/use-extracted-data-review'
import type { UseFieldCorrectionsReturn } from '../hooks/use-field-corrections'

interface SplitViewLayoutProps {
    // Document preview
    previewImageUrl: string | null
    previewLoading: boolean
    previewError: boolean
    detailLoading: boolean
    // Zoom
    zoomLevel: number
    onZoomIn: () => void
    onZoomOut: () => void
    onZoomReset: () => void
    // Data panel
    queueItem: QueueItem | null | undefined
    extractedDataReview: UseExtractedDataForReviewReturn
    corrections: UseFieldCorrectionsReturn
    isSubmitting: boolean
    structuredPanelRef: React.RefObject<HTMLDivElement>
    // OCR text
    originalText: string
    currentText: string
    llmSuggestion?: string
    onTextChange: (text: string, type: CorrectionType, dirty: boolean) => void
    // Active tab (for right panel)
    activeTab: 'structured' | 'ocr-text'
    onTabChange: (tab: string) => void
    // Linked highlighting
    onBoundingBoxClick?: (fieldName: string) => void
}

export function SplitViewLayout({
    previewImageUrl,
    previewLoading,
    previewError,
    detailLoading,
    zoomLevel,
    onZoomIn,
    onZoomOut,
    onZoomReset,
    queueItem,
    extractedDataReview,
    corrections,
    isSubmitting,
    structuredPanelRef,
    originalText,
    currentText,
    llmSuggestion,
    onTextChange,
    activeTab,
    onTabChange,
}: SplitViewLayoutProps) {


    return (
        <ResizablePanelGroup
            orientation="horizontal"
            className="min-h-[calc(100vh-280px)] rounded-lg border"
        >
            {/* Linkes Panel: PDF/Bild-Vorschau */}
            <ResizablePanel defaultSize={55} minSize={30}>
                <div className="h-full flex flex-col">
                    {/* Zoom-Kontrollen */}
                    <div className="flex items-center gap-1 p-2 border-b bg-muted/30">
                        <div className="flex items-center gap-1 bg-muted/50 rounded-md p-0.5">
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={onZoomOut}
                                disabled={zoomLevel <= 50}
                                title="Verkleinern"
                            >
                                <ZoomOut className="h-3.5 w-3.5" />
                            </Button>
                            <span className="text-xs font-mono w-12 text-center">
                                {zoomLevel}%
                            </span>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={onZoomIn}
                                disabled={zoomLevel >= 300}
                                title="Vergrößern"
                            >
                                <ZoomIn className="h-3.5 w-3.5" />
                            </Button>
                            {zoomLevel !== 100 && (
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={onZoomReset}
                                    title="Zurücksetzen"
                                >
                                    <RotateCcw className="h-3.5 w-3.5" />
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* Dokument-Anzeige */}
                    <div className="flex-1 overflow-auto">
                        {(detailLoading || previewLoading) ? (
                            <Skeleton className="h-full w-full min-h-[500px]" />
                        ) : previewImageUrl && !previewError ? (
                            <div
                                className="h-full w-full bg-zinc-100 dark:bg-zinc-900"
                                style={{ cursor: zoomLevel > 100 ? 'grab' : 'default' }}
                            >
                                <img
                                    src={previewImageUrl}
                                    alt="Dokument-Vorschau"
                                    className="transition-transform duration-150"
                                    style={{
                                        transform: `scale(${zoomLevel / 100})`,
                                        transformOrigin: 'top left',
                                        minHeight: '100%',
                                        width: zoomLevel > 100 ? 'auto' : '100%',
                                    }}
                                />
                            </div>
                        ) : (
                            <div className="h-full min-h-[500px] flex items-center justify-center bg-muted/30">
                                <div className="text-center text-muted-foreground">
                                    <FileText className="h-12 w-12 mx-auto mb-2 opacity-40" />
                                    <p className="text-sm">
                                        {previewError ? 'Vorschau nicht verfügbar' : 'Kein Dokument'}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Rechtes Panel: Daten / OCR-Text */}
            <ResizablePanel defaultSize={45} minSize={25}>
                <div className="h-full flex flex-col">
                    <Tabs
                        value={activeTab}
                        onValueChange={onTabChange}
                        className="flex-1 flex flex-col"
                    >
                        <TabsList className="grid w-full grid-cols-2 m-2 mb-0">
                            <TabsTrigger
                                value="structured"
                                className="flex items-center gap-1.5 text-sm"
                            >
                                <LayoutGrid className="h-3.5 w-3.5" />
                                Daten
                            </TabsTrigger>
                            <TabsTrigger
                                value="ocr-text"
                                className="flex items-center gap-1.5 text-sm"
                            >
                                <AlignLeft className="h-3.5 w-3.5" />
                                OCR-Text
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent
                            value="structured"
                            className="flex-1 mt-0 p-2 overflow-auto"
                        >
                            <div ref={structuredPanelRef} className="h-full">
                                <StructuredReviewPanel
                                    queueItem={queueItem}
                                    extractedDataReview={extractedDataReview}
                                    corrections={corrections}
                                    disabled={isSubmitting}
                                    className="h-full"
                                />
                            </div>
                        </TabsContent>

                        <TabsContent
                            value="ocr-text"
                            className="flex-1 mt-0 p-2"
                        >
                            <CorrectionEditor
                                originalText={originalText}
                                initialText={currentText}
                                llmSuggestion={llmSuggestion}
                                onTextChange={onTextChange}
                                disabled={isSubmitting}
                            />
                        </TabsContent>
                    </Tabs>
                </div>
            </ResizablePanel>
        </ResizablePanelGroup>
    )
}
