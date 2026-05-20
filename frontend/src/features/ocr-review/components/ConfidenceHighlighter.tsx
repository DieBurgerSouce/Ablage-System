/**
 * ConfidenceHighlighter - OCR-Text mit farblicher Confidence-Markierung
 *
 * Rendert erkannten Text, wobei jedes Wort je nach Confidence eingefaerbt wird:
 * - Grün (>=0.95): Sehr sicher
 * - Gelb (0.8-0.95): Unsicher
 * - Orange (0.6-0.8): Niedrig
 * - Rot (<0.6): Kritisch
 *
 * Hovering zeigt Tooltip mit exaktem Prozent-Wert.
 * Klick auf niedrig-confidence Wörter selektiert sie.
 */

import { useCallback, useRef, useEffect } from 'react'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import type { WordConfidence } from '../api/confidence-api'
import {
    getConfidenceLevel,
    getConfidenceLevelLabel,
    getConfidenceBgColor,
    getConfidenceLevelColor,
} from '../api/confidence-api'

interface ConfidenceHighlighterProps {
    words: WordConfidence[]
    /** Confidence-Schwelle: Wörter darunter werden unterstrichen */
    threshold: number
    /** Aktuell hervorgehobenes Wort (Sync mit Overlay) */
    highlightedWordIndex: number | null
    /** Callback wenn Wort angeklickt wird */
    onWordClick: (index: number) => void
    /** Callback wenn Maus über Wort faehrt */
    onWordHover: (index: number | null) => void
    className?: string
}

export function ConfidenceHighlighter({
    words,
    threshold,
    highlightedWordIndex,
    onWordClick,
    onWordHover,
    className,
}: ConfidenceHighlighterProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const wordRefs = useRef<Map<number, HTMLElement>>(new Map())

    // Scroll highlighted word into view
    useEffect(() => {
        if (highlightedWordIndex !== null) {
            const element = wordRefs.current.get(highlightedWordIndex)
            if (element) {
                element.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
            }
        }
    }, [highlightedWordIndex])

    const setWordRef = useCallback(
        (index: number, el: HTMLSpanElement | null) => {
            if (el) {
                wordRefs.current.set(index, el)
            } else {
                wordRefs.current.delete(index)
            }
        },
        []
    )

    if (words.length === 0) {
        return (
            <div className="p-6 text-center text-muted-foreground text-sm">
                Keine Wort-Level Daten verfügbar.
            </div>
        )
    }

    return (
        <TooltipProvider delayDuration={200}>
            <div
                ref={containerRef}
                className={`p-4 leading-relaxed text-sm font-mono ${className ?? ''}`}
            >
                {words.map((word, index) => {
                    const level = getConfidenceLevel(word.confidence)
                    const levelLabel = getConfidenceLevelLabel(level)
                    const colorClass = getConfidenceLevelColor(level)
                    const bgClass = getConfidenceBgColor(level)
                    const isHighlighted = highlightedWordIndex === index
                    const isBelowThreshold = word.confidence < threshold
                    const confidencePercent = Math.round(word.confidence * 100)

                    return (
                        <Tooltip key={index}>
                            <TooltipTrigger asChild>
                                <span
                                    ref={(el) => setWordRef(index, el)}
                                    className={[
                                        'inline cursor-pointer rounded-sm px-0.5 transition-all duration-150',
                                        colorClass,
                                        isHighlighted
                                            ? `${bgClass} ring-2 ring-primary/50 font-semibold`
                                            : level !== 'high'
                                              ? bgClass
                                              : '',
                                        isBelowThreshold ? 'underline decoration-wavy decoration-1' : '',
                                    ].join(' ')}
                                    onClick={() => onWordClick(index)}
                                    onMouseEnter={() => onWordHover(index)}
                                    onMouseLeave={() => onWordHover(null)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault()
                                            onWordClick(index)
                                        }
                                    }}
                                    tabIndex={isBelowThreshold ? 0 : -1}
                                    role="button"
                                    aria-label={`${word.text} - ${confidencePercent}% ${levelLabel}`}
                                >
                                    {word.text}
                                </span>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                                <div className="flex flex-col gap-0.5">
                                    <span className="font-medium">
                                        {confidencePercent}% - {levelLabel}
                                    </span>
                                    <span className="text-muted-foreground">
                                        Seite {word.page} | Position ({Math.round(word.x * 100)}%, {Math.round(word.y * 100)}%)
                                    </span>
                                </div>
                            </TooltipContent>
                        </Tooltip>
                    )
                })}
            </div>
        </TooltipProvider>
    )
}
