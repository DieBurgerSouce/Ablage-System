import { useMemo } from 'react'
import { cn } from '@/lib/utils'

interface DiffViewProps {
    original: string
    modified: string
    className?: string
}

interface DiffSegment {
    type: 'equal' | 'insert' | 'delete' | 'replace'
    original: string
    modified: string
}

/**
 * Berechnet den Levenshtein-Diff zwischen zwei Strings auf Wortebene.
 */
function computeWordDiff(original: string, modified: string): DiffSegment[] {
    const originalWords = original.split(/(\s+)/)
    const modifiedWords = modified.split(/(\s+)/)

    const segments: DiffSegment[] = []
    let i = 0
    let j = 0

    while (i < originalWords.length || j < modifiedWords.length) {
        const origWord = originalWords[i] ?? ''
        const modWord = modifiedWords[j] ?? ''

        if (origWord === modWord) {
            // Gleiche Woerter
            if (origWord) {
                segments.push({ type: 'equal', original: origWord, modified: modWord })
            }
            i++
            j++
        } else if (i >= originalWords.length) {
            // Insertion
            segments.push({ type: 'insert', original: '', modified: modWord })
            j++
        } else if (j >= modifiedWords.length) {
            // Deletion
            segments.push({ type: 'delete', original: origWord, modified: '' })
            i++
        } else {
            // Replacement oder komplexerer Diff
            // Einfache Heuristik: Wenn das naechste Wort uebereinstimmt, ist es ein Replace
            const nextOrigMatch = modifiedWords.indexOf(originalWords[i + 1], j)
            const nextModMatch = originalWords.indexOf(modifiedWords[j + 1], i)

            if (nextOrigMatch === j + 1) {
                // Delete original word
                segments.push({ type: 'delete', original: origWord, modified: '' })
                i++
            } else if (nextModMatch === i + 1) {
                // Insert modified word
                segments.push({ type: 'insert', original: '', modified: modWord })
                j++
            } else {
                // Replace
                segments.push({ type: 'replace', original: origWord, modified: modWord })
                i++
                j++
            }
        }
    }

    return segments
}

/**
 * Prueft ob ein Wort einen Umlaut-Fehler enthaelt.
 */
function isUmlautError(original: string, modified: string): boolean {
    // Check if one could be converted to the other through umlaut substitution
    const normalizeUmlauts = (s: string): string => {
        return s
            .replace(/ä/g, 'ae')
            .replace(/ö/g, 'oe')
            .replace(/ü/g, 'ue')
            .replace(/Ä/g, 'Ae')
            .replace(/Ö/g, 'Oe')
            .replace(/Ü/g, 'Ue')
            .replace(/ß/g, 'ss')
    }

    return normalizeUmlauts(original.toLowerCase()) === normalizeUmlauts(modified.toLowerCase()) &&
           original.toLowerCase() !== modified.toLowerCase()
}

export function DiffView({ original, modified, className }: DiffViewProps) {
    const diff = useMemo(() => computeWordDiff(original, modified), [original, modified])

    if (original === modified) {
        return (
            <div className={cn('font-mono text-sm whitespace-pre-wrap', className)}>
                <span className="text-green-600">{original}</span>
            </div>
        )
    }

    return (
        <div className={cn('font-mono text-sm whitespace-pre-wrap leading-relaxed', className)}>
            {diff.map((segment, index) => {
                const key = `${index}-${segment.type}`

                switch (segment.type) {
                    case 'equal':
                        return <span key={key}>{segment.original}</span>

                    case 'delete':
                        return (
                            <span
                                key={key}
                                className="bg-red-100 text-red-800 line-through"
                                title="Gelöscht"
                            >
                                {segment.original}
                            </span>
                        )

                    case 'insert':
                        return (
                            <span
                                key={key}
                                className="bg-green-100 text-green-800"
                                title="Eingefügt"
                            >
                                {segment.modified}
                            </span>
                        )

                    case 'replace': {
                        const isUmlaut = isUmlautError(segment.original, segment.modified)
                        return (
                            <span key={key}>
                                <span
                                    className={cn(
                                        'line-through',
                                        isUmlaut
                                            ? 'bg-yellow-100 text-yellow-800'
                                            : 'bg-red-100 text-red-800'
                                    )}
                                    title={isUmlaut ? 'Umlaut-Fehler' : 'Ersetzt'}
                                >
                                    {segment.original}
                                </span>
                                <span
                                    className={cn(
                                        isUmlaut
                                            ? 'bg-yellow-100 text-yellow-800 font-bold'
                                            : 'bg-green-100 text-green-800'
                                    )}
                                    title={isUmlaut ? 'Umlaut-Korrektur' : 'Neuer Text'}
                                >
                                    {segment.modified}
                                </span>
                            </span>
                        )
                    }

                    default:
                        return null
                }
            })}
        </div>
    )
}

/**
 * Kompakte Diff-Statistik Anzeige
 */
interface DiffStatsProps {
    original: string
    modified: string
}

export function DiffStats({ original, modified }: DiffStatsProps) {
    const stats = useMemo(() => {
        const diff = computeWordDiff(original, modified)

        let insertions = 0
        let deletions = 0
        let replacements = 0
        let umlautErrors = 0

        for (const segment of diff) {
            switch (segment.type) {
                case 'insert':
                    insertions++
                    break
                case 'delete':
                    deletions++
                    break
                case 'replace':
                    replacements++
                    if (isUmlautError(segment.original, segment.modified)) {
                        umlautErrors++
                    }
                    break
            }
        }

        return { insertions, deletions, replacements, umlautErrors }
    }, [original, modified])

    if (stats.insertions === 0 && stats.deletions === 0 && stats.replacements === 0) {
        return (
            <span className="text-green-600 text-xs">
                Keine Fehler
            </span>
        )
    }

    return (
        <div className="flex gap-2 text-xs">
            {stats.umlautErrors > 0 && (
                <span className="text-yellow-600">
                    {stats.umlautErrors} Umlaut
                </span>
            )}
            {stats.replacements - stats.umlautErrors > 0 && (
                <span className="text-orange-600">
                    {stats.replacements - stats.umlautErrors} Ersetzt
                </span>
            )}
            {stats.deletions > 0 && (
                <span className="text-red-600">
                    {stats.deletions} Gelöscht
                </span>
            )}
            {stats.insertions > 0 && (
                <span className="text-green-600">
                    {stats.insertions} Eingefügt
                </span>
            )}
        </div>
    )
}
