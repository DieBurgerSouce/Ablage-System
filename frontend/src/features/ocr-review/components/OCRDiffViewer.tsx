/**
 * OCRDiffViewer - Side-by-Side Vergleich von Original-Dokument und OCR-Text
 *
 * Zeigt links das Original-Dokument mit Confidence-Overlay und rechts den
 * erkannten OCR-Text mit farblichen Confidence-Markierungen.
 *
 * Features:
 * - Resizable Split-Layout
 * - Confidence-Farbmarkierungen (Gruen/Gelb/Orange/Rot)
 * - Seitenwechsel-Steuerung
 * - Confidence-Schwellwert-Slider (Filter)
 * - Bounding-Box Overlay auf dem Dokument
 * - Sync: Hover auf Text hebt Box hervor und umgekehrt
 * - Tastaturnavigation durch niedrig-confidence Woerter (Tab)
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/logger'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Slider } from '@/components/ui/slider'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import {
    ChevronLeft,
    ChevronRight,
    Eye,
    EyeOff,
    Loader2,
    FileText,
    GripVertical,
} from 'lucide-react'

import { useDocumentConfidence } from '../hooks/use-confidence-data'
import { ConfidenceHighlighter } from './ConfidenceHighlighter'
import { DocumentOverlay } from './DocumentOverlay'
import { ConfidenceLegend } from './ConfidenceLegend'
import { ConfidenceStats } from './ConfidenceStats'

interface OCRDiffViewerProps {
    documentId: string
    pageNumber?: number
}

export function OCRDiffViewer({ documentId, pageNumber: initialPage }: OCRDiffViewerProps) {
    // State
    const [currentPage, setCurrentPage] = useState(initialPage ?? 1)
    const [showOverlay, setShowOverlay] = useState(true)
    const [thresholdValue, setThresholdValue] = useState(0) // 0 = alle anzeigen
    const [highlightedWordIndex, setHighlightedWordIndex] = useState<number | null>(null)
    const [splitPosition, setSplitPosition] = useState(50) // Prozent
    const [isDragging, setIsDragging] = useState(false)
    const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState(false)
    const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 })

    // Refs
    const containerRef = useRef<HTMLDivElement>(null)
    const imageContainerRef = useRef<HTMLDivElement>(null)
    const imageRef = useRef<HTMLImageElement>(null)

    // Confidence-Daten laden
    const {
        data: confidenceData,
        isLoading: confidenceLoading,
        error: confidenceError,
    } = useDocumentConfidence(documentId, currentPage)

    // Aktuelle Seiten-Daten
    const currentPageData = useMemo(() => {
        if (!confidenceData?.pages) return null
        return confidenceData.pages.find((p) => p.page_number === currentPage) ?? confidenceData.pages[0] ?? null
    }, [confidenceData, currentPage])

    const words = useMemo(() => currentPageData?.words ?? [], [currentPageData])
    const totalPages = confidenceData?.total_pages ?? 1

    // Low-confidence word indices for Tab-navigation
    const lowConfidenceIndices = useMemo(() => {
        return words
            .map((w, i) => ({ index: i, confidence: w.confidence }))
            .filter((w) => w.confidence < 0.8)
            .map((w) => w.index)
    }, [words])

    // Keyboard navigation: Tab through low-confidence words
    const handleKeyDown = useCallback(
        (event: KeyboardEvent) => {
            if (lowConfidenceIndices.length === 0) return

            if (event.key === 'Tab' && !event.ctrlKey && !event.altKey) {
                const target = event.target as HTMLElement
                // Only handle if not in input/textarea
                if (
                    target.tagName === 'INPUT' ||
                    target.tagName === 'TEXTAREA' ||
                    target.isContentEditable
                ) {
                    return
                }

                event.preventDefault()

                if (highlightedWordIndex === null) {
                    setHighlightedWordIndex(lowConfidenceIndices[0])
                    return
                }

                const currentIdx = lowConfidenceIndices.indexOf(highlightedWordIndex)
                if (event.shiftKey) {
                    // Previous
                    const prevIdx = currentIdx <= 0 ? lowConfidenceIndices.length - 1 : currentIdx - 1
                    setHighlightedWordIndex(lowConfidenceIndices[prevIdx])
                } else {
                    // Next
                    const nextIdx = currentIdx >= lowConfidenceIndices.length - 1 ? 0 : currentIdx + 1
                    setHighlightedWordIndex(lowConfidenceIndices[nextIdx])
                }
            }
        },
        [lowConfidenceIndices, highlightedWordIndex]
    )

    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [handleKeyDown])

    // Lade Dokument-Preview mit Auth
    useEffect(() => {
        let cancelled = false
        const controller = new AbortController()
        let currentBlobUrl: string | null = null

        async function fetchPreview() {
            setPreviewLoading(true)
            setPreviewError(false)

            try {
                const response = await apiClient.get(
                    `/documents/${documentId}/preview?page=${currentPage - 1}`,
                    {
                        responseType: 'blob',
                        signal: controller.signal,
                    }
                )

                if (cancelled) return

                const blob = new Blob([response.data], { type: 'image/png' })
                currentBlobUrl = URL.createObjectURL(blob)
                setPreviewBlobUrl(currentBlobUrl)
            } catch (err) {
                if (!cancelled) {
                    logger.error('Dokument-Vorschau konnte nicht geladen werden', err)
                    setPreviewError(true)
                }
            } finally {
                if (!cancelled) {
                    setPreviewLoading(false)
                }
            }
        }

        fetchPreview()

        return () => {
            cancelled = true
            controller.abort()
            if (currentBlobUrl) {
                URL.revokeObjectURL(currentBlobUrl)
            }
        }
    }, [documentId, currentPage])

    // Track image container size for overlay scaling
    useEffect(() => {
        const container = imageContainerRef.current
        if (!container) return

        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) {
                setImageDimensions({
                    width: entry.contentRect.width,
                    height: entry.contentRect.height,
                })
            }
        })

        observer.observe(container)
        return () => observer.disconnect()
    }, [])

    // Drag-handle fuer Split
    const handleMouseDown = useCallback(() => {
        setIsDragging(true)
    }, [])

    useEffect(() => {
        if (!isDragging) return

        const handleMouseMove = (e: MouseEvent) => {
            const container = containerRef.current
            if (!container) return
            const rect = container.getBoundingClientRect()
            const x = e.clientX - rect.left
            const percent = Math.min(Math.max((x / rect.width) * 100, 20), 80)
            setSplitPosition(percent)
        }

        const handleMouseUp = () => {
            setIsDragging(false)
        }

        document.addEventListener('mousemove', handleMouseMove)
        document.addEventListener('mouseup', handleMouseUp)
        return () => {
            document.removeEventListener('mousemove', handleMouseMove)
            document.removeEventListener('mouseup', handleMouseUp)
        }
    }, [isDragging])

    // Seiten-Navigation
    const goToPreviousPage = useCallback(() => {
        setCurrentPage((p) => Math.max(1, p - 1))
        setHighlightedWordIndex(null)
    }, [])

    const goToNextPage = useCallback(() => {
        setCurrentPage((p) => Math.min(totalPages, p + 1))
        setHighlightedWordIndex(null)
    }, [totalPages])

    // Threshold als echte Prozentzahl (Slider gibt 0-100)
    const thresholdDecimal = thresholdValue / 100

    return (
        <div className="flex flex-col h-full">
            {/* Header Bar */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30 flex-shrink-0">
                <div className="flex items-center gap-3">
                    {/* Page Navigation */}
                    <div className="flex items-center gap-1">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={goToPreviousPage}
                            disabled={currentPage <= 1}
                        >
                            <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <span className="text-sm tabular-nums min-w-[80px] text-center">
                            Seite {currentPage} / {totalPages}
                        </span>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={goToNextPage}
                            disabled={currentPage >= totalPages}
                        >
                            <ChevronRight className="h-4 w-4" />
                        </Button>
                    </div>

                    {/* Confidence Summary */}
                    {confidenceData && (
                        <ConfidenceStats
                            overallConfidence={confidenceData.overall_confidence}
                            pages={confidenceData.pages}
                            backend={confidenceData.backend}
                        />
                    )}
                </div>

                <div className="flex items-center gap-3">
                    {/* Threshold Slider */}
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                                        Filter:
                                    </span>
                                    <Slider
                                        value={[thresholdValue]}
                                        onValueChange={([val]) => setThresholdValue(val)}
                                        min={0}
                                        max={100}
                                        step={5}
                                        className="w-24"
                                    />
                                    <span className="text-xs tabular-nums w-8 text-right">
                                        {thresholdValue > 0 ? `<${thresholdValue}%` : 'Alle'}
                                    </span>
                                </div>
                            </TooltipTrigger>
                            <TooltipContent>
                                Nur Woerter unter diesem Schwellwert hervorheben
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>

                    {/* Toggle Overlay */}
                    <Button
                        variant={showOverlay ? 'default' : 'outline'}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => setShowOverlay((v) => !v)}
                    >
                        {showOverlay ? (
                            <Eye className="h-3.5 w-3.5 mr-1" />
                        ) : (
                            <EyeOff className="h-3.5 w-3.5 mr-1" />
                        )}
                        Markierungen
                    </Button>
                </div>
            </div>

            {/* Loading */}
            {confidenceLoading && (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    <span className="ml-3 text-sm text-muted-foreground">
                        Lade Confidence-Daten...
                    </span>
                </div>
            )}

            {/* Error */}
            {confidenceError && (
                <div className="p-6 text-center text-sm text-destructive">
                    Confidence-Daten konnten nicht geladen werden.
                </div>
            )}

            {/* Main Split Layout */}
            {!confidenceLoading && !confidenceError && (
                <div
                    ref={containerRef}
                    className="flex-1 flex overflow-hidden relative"
                    style={{ cursor: isDragging ? 'col-resize' : 'default' }}
                >
                    {/* LEFT: Document Image with Overlay */}
                    <div
                        className="overflow-auto bg-zinc-100 dark:bg-zinc-900 relative"
                        style={{ width: `${splitPosition}%` }}
                    >
                        {previewLoading ? (
                            <div className="h-full flex items-center justify-center">
                                <Skeleton className="w-3/4 h-3/4" />
                            </div>
                        ) : previewError || !previewBlobUrl ? (
                            <div className="h-full flex items-center justify-center text-muted-foreground">
                                <div className="text-center">
                                    <FileText className="h-12 w-12 mx-auto mb-2 opacity-40" />
                                    <p className="text-sm">
                                        {previewError ? 'Vorschau nicht verfuegbar' : 'Lade...'}
                                    </p>
                                </div>
                            </div>
                        ) : (
                            <div ref={imageContainerRef} className="relative inline-block min-w-full">
                                <img
                                    ref={imageRef}
                                    src={previewBlobUrl}
                                    alt={`Dokument Seite ${currentPage}`}
                                    className="w-full h-auto block"
                                    onLoad={(e) => {
                                        const img = e.currentTarget
                                        setImageDimensions({
                                            width: img.clientWidth,
                                            height: img.clientHeight,
                                        })
                                    }}
                                />
                                <DocumentOverlay
                                    words={words}
                                    containerWidth={imageDimensions.width}
                                    containerHeight={imageDimensions.height}
                                    threshold={thresholdDecimal}
                                    highlightedWordIndex={highlightedWordIndex}
                                    visible={showOverlay}
                                    onWordHover={setHighlightedWordIndex}
                                    onWordClick={setHighlightedWordIndex}
                                />
                            </div>
                        )}
                    </div>

                    {/* Drag Handle */}
                    <div
                        className="flex-shrink-0 w-2 bg-border hover:bg-primary/30 cursor-col-resize flex items-center justify-center group transition-colors"
                        onMouseDown={handleMouseDown}
                    >
                        <GripVertical className="h-6 w-6 text-muted-foreground/50 group-hover:text-primary/70" />
                    </div>

                    {/* RIGHT: OCR Text with Confidence Highlighting */}
                    <div
                        className="overflow-auto bg-background flex flex-col"
                        style={{ width: `${100 - splitPosition}%` }}
                    >
                        {/* Legend */}
                        {words.length > 0 && (
                            <div className="px-4 pt-3 pb-2 border-b flex-shrink-0">
                                <ConfidenceLegend words={words} />
                            </div>
                        )}

                        {/* Low-Confidence Navigation Hint */}
                        {lowConfidenceIndices.length > 0 && (
                            <div className="px-4 py-1.5 bg-muted/30 border-b flex-shrink-0">
                                <span className="text-[11px] text-muted-foreground">
                                    Tab: naechstes unsicheres Wort ({lowConfidenceIndices.length} Treffer)
                                </span>
                            </div>
                        )}

                        {/* Highlighted Text */}
                        <div className="flex-1 overflow-auto">
                            <ConfidenceHighlighter
                                words={words}
                                threshold={thresholdDecimal}
                                highlightedWordIndex={highlightedWordIndex}
                                onWordClick={setHighlightedWordIndex}
                                onWordHover={setHighlightedWordIndex}
                            />
                        </div>

                        {/* Page confidence */}
                        {currentPageData && (
                            <div className="px-4 py-2 border-t text-xs text-muted-foreground flex items-center justify-between flex-shrink-0">
                                <span>
                                    Seiten-Confidence: {Math.round(currentPageData.overall_confidence * 100)}%
                                </span>
                                <Badge variant="outline" className="text-[10px]">
                                    {currentPageData.backend}
                                </Badge>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
