/**
 * SmartUploadResults - Kompakte Ergebnisanzeige nach Smart Upload
 *
 * Zeigt pro Datei: Dateiname, erkannter Typ, Konfidenz-Badge, Tags.
 * Fehlerhafte Dateien werden rot hervorgehoben.
 */

import { CheckCircle2, AlertCircle, FileCheck, Tag as TagIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { OcrConfidenceBadge } from '@/features/ocr-batch'
import { cn } from '@/lib/utils'
import { FilingSuggestionCard } from './FilingSuggestionCard'

interface SmartUploadResultTag {
    name: string
    displayName: string
    confidence: number
    color: string
}

interface SmartUploadResultItem {
    filename: string
    documentId: string
    category?: string
    categoryConfidence?: number
    tags: Array<SmartUploadResultTag>
    error?: string
}

interface SmartUploadResultsProps {
    results: Array<SmartUploadResultItem>
    onClose: () => void
    onConfirmAll: () => void
    /**
     * F1 Vertrauens-Loop: zeigt pro erfolgreichem Dokument einen
     * Ablage-Vorschlag zum Bestätigen/Korrigieren. Default aus, damit
     * bestehende Aufrufer unverändert bleiben.
     */
    showFilingSuggestions?: boolean
}

export function SmartUploadResults({
    results,
    onClose,
    onConfirmAll,
    showFilingSuggestions = false,
}: SmartUploadResultsProps) {
    const successCount = results.filter((r) => !r.error).length
    const errorCount = results.filter((r) => r.error).length

    return (
        <Card className="w-full max-w-2xl mx-auto border-border/50 bg-card/95 backdrop-blur-sm shadow-lg">
            <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2 text-lg">
                    {errorCount === 0 ? (
                        <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
                    ) : (
                        <AlertCircle className="h-5 w-5 text-yellow-500 flex-shrink-0" />
                    )}
                    <span>
                        {successCount} {successCount === 1 ? 'Dokument' : 'Dokumente'} verarbeitet
                        {errorCount > 0 && (
                            <span className="text-destructive font-normal text-sm ml-2">
                                ({errorCount} {errorCount === 1 ? 'Fehler' : 'Fehler'})
                            </span>
                        )}
                    </span>
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {/* Result rows */}
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                    {results.map((result) => (
                        <div
                            key={result.documentId || result.filename}
                            className={cn(
                                'flex items-start gap-3 p-3 rounded-lg border transition-colors',
                                result.error
                                    ? 'border-destructive/30 bg-destructive/5'
                                    : 'border-border/50 bg-muted/30'
                            )}
                        >
                            {/* Icon */}
                            <div className="flex-shrink-0 mt-0.5">
                                {result.error ? (
                                    <AlertCircle className="h-4 w-4 text-destructive" />
                                ) : (
                                    <FileCheck className="h-4 w-4 text-green-500" />
                                )}
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0 space-y-1.5">
                                {/* Filename */}
                                <p className="text-sm font-medium truncate" title={result.filename}>
                                    {result.filename}
                                </p>

                                {result.error ? (
                                    <p className="text-xs text-destructive">{result.error}</p>
                                ) : (
                                    <div className="flex flex-wrap items-center gap-1.5">
                                        {/* Category badge */}
                                        {result.category && (
                                            <Badge variant="secondary" className="text-xs">
                                                {result.category}
                                            </Badge>
                                        )}

                                        {/* Confidence */}
                                        {result.categoryConfidence != null && (
                                            <OcrConfidenceBadge
                                                confidence={result.categoryConfidence}
                                                showPercent
                                                className="text-xs"
                                            />
                                        )}

                                        {/* Tags */}
                                        {result.tags.length > 0 && (
                                            <>
                                                <span className="w-px h-3 bg-border mx-0.5" />
                                                <TagIcon className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                                                {result.tags.map((tag) => (
                                                    <Badge
                                                        key={tag.name}
                                                        variant="outline"
                                                        className="text-xs"
                                                        style={
                                                            tag.color
                                                                ? {
                                                                      borderColor: tag.color,
                                                                      color: tag.color,
                                                                  }
                                                                : undefined
                                                        }
                                                    >
                                                        {tag.displayName}
                                                    </Badge>
                                                ))}
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>

                {/* F1: Ablage-Vorschläge zum Bestätigen/Korrigieren */}
                {showFilingSuggestions && successCount > 0 && (
                    <div className="space-y-2 border-t border-border/50 pt-3">
                        {results
                            .filter((r) => !r.error && r.documentId)
                            .map((r) => (
                                <FilingSuggestionCard
                                    key={`filing-${r.documentId}`}
                                    documentId={r.documentId}
                                    filename={r.filename}
                                />
                            ))}
                    </div>
                )}

                {/* Actions */}
                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/50">
                    <Button variant="ghost" size="sm" onClick={onClose}>
                        Schliessen
                    </Button>
                    {successCount > 0 && (
                        <Button size="sm" onClick={onConfirmAll}>
                            <CheckCircle2 className="h-4 w-4 mr-1.5" />
                            Alles korrekt
                        </Button>
                    )}
                </div>
            </CardContent>
        </Card>
    )
}
