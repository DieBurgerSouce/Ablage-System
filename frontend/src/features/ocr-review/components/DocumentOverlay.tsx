/**
 * DocumentOverlay - Bounding-Box Overlay für Dokument-Bild
 *
 * Rendert semi-transparente farbige Rechtecke über dem Dokument-Bild.
 * Jedes Rechteck entspricht einem WordConfidence-Eintrag mit Positionsdaten.
 * Farbe korrespondiert zum Confidence-Level.
 *
 * Verwendet normalisierte Koordinaten (0-1) die auf die tatsächlichen
 * Bild-Dimensionen skaliert werden.
 */

import { useMemo } from 'react'
import type { WordConfidence } from '../api/confidence-api'
import { getConfidenceOverlayColor, getConfidenceStrokeColor } from '../api/confidence-api'

interface DocumentOverlayProps {
    words: WordConfidence[]
    /** Breite des Bild-Containers in Pixeln */
    containerWidth: number
    /** Höhe des Bild-Containers in Pixeln */
    containerHeight: number
    /** Confidence-Schwelle: nur Wörter <= threshold werden gezeichnet (0 = alle) */
    threshold: number
    /** Aktuell hervorgehobenes Wort (Sync mit Text-Panel) */
    highlightedWordIndex: number | null
    /** Overlay anzeigen? */
    visible: boolean
    /** Callback wenn Wort per Hover selektiert wird */
    onWordHover: (index: number | null) => void
    /** Callback wenn Wort angeklickt wird */
    onWordClick: (index: number) => void
}

export function DocumentOverlay({
    words,
    containerWidth,
    containerHeight,
    threshold,
    highlightedWordIndex,
    visible,
    onWordHover,
    onWordClick,
}: DocumentOverlayProps) {
    // Filter words by threshold (0 means show all)
    const filteredWords = useMemo(() => {
        if (threshold <= 0) return words.map((w, i) => ({ word: w, originalIndex: i }))
        return words
            .map((w, i) => ({ word: w, originalIndex: i }))
            .filter(({ word }) => word.confidence <= threshold)
    }, [words, threshold])

    if (!visible || containerWidth === 0 || containerHeight === 0) {
        return null
    }

    return (
        <svg
            className="absolute top-0 left-0 pointer-events-none"
            width={containerWidth}
            height={containerHeight}
            style={{ zIndex: 10 }}
        >
            {filteredWords.map(({ word, originalIndex }) => {
                const x = word.x * containerWidth
                const y = word.y * containerHeight
                const w = word.width * containerWidth
                const h = word.height * containerHeight
                const isHighlighted = highlightedWordIndex === originalIndex
                const fillColor = getConfidenceOverlayColor(word.confidence)
                const strokeColor = getConfidenceStrokeColor(word.confidence)

                return (
                    <g key={originalIndex}>
                        <rect
                            x={x}
                            y={y}
                            width={w}
                            height={h}
                            fill={fillColor}
                            fillOpacity={isHighlighted ? 0.5 : 0.25}
                            stroke={strokeColor}
                            strokeWidth={isHighlighted ? 2.5 : 1}
                            style={{ pointerEvents: 'all', cursor: 'pointer' }}
                            onMouseEnter={() => onWordHover(originalIndex)}
                            onMouseLeave={() => onWordHover(null)}
                            onClick={() => onWordClick(originalIndex)}
                        />
                        {isHighlighted && (
                            <text
                                x={x}
                                y={y - 3}
                                fontSize={11}
                                fontWeight="bold"
                                fill={strokeColor}
                                style={{ pointerEvents: 'none' }}
                            >
                                {Math.round(word.confidence * 100)}%
                            </text>
                        )}
                    </g>
                )
            })}
        </svg>
    )
}
