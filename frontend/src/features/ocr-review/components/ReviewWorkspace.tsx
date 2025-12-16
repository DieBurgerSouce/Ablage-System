/**
 * Review Workspace Komponente
 * Vollbild-Review mit Sample-Anzeige, Editor und Aktionen
 */

import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '@/lib/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
    ArrowLeft,
    Check,
    X,
    SkipForward,
    Loader2,
    FileText,
    AlertCircle,
    Sparkles,
    Keyboard,
    Image as ImageIcon,
    ChevronRight,
} from 'lucide-react'

import { useNextSample, useSampleDetail, useLLMReview, useVerifySample, useSubmitCorrection } from '../hooks/use-review-queries'
import { useKeyboardShortcuts, type ReviewAction } from '../hooks/use-keyboard-shortcuts'
import { CorrectionEditor } from './CorrectionEditor'
import { KeyboardShortcutsHelp, ShortcutHint } from './KeyboardShortcutsHelp'
import type { CorrectionType } from '../types'

interface ReviewWorkspaceProps {
    onComplete: (wasCorrection: boolean) => void
    onExit: () => void
    sessionStats: {
        reviewed_today: number
        corrections_today: number
    }
}

export function ReviewWorkspace({
    onComplete,
    onExit,
    sessionStats,
}: ReviewWorkspaceProps) {
    // State
    const [showShortcutsHelp, setShowShortcutsHelp] = useState(false)
    const [currentText, setCurrentText] = useState('')
    const [correctionType, setCorrectionType] = useState<CorrectionType>('GENERAL')
    const [isDirty, setIsDirty] = useState(false)
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null)
    const [previewLoading, setPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState(false)

    // Queries
    const {
        data: nextSampleData,
        isLoading: sampleLoading,
        error: sampleError,
        refetch: refetchNext,
    } = useNextSample()

    const nextSample = nextSampleData?.item
    const sampleId = nextSample?.sample_id

    const {
        data: sampleDetail,
        isLoading: detailLoading,
    } = useSampleDetail(sampleId)

    const {
        data: llmReview,
        isLoading: llmLoading,
        refetch: refetchLLM,
    } = useLLMReview(sampleId)

    // Mutations
    const verifyMutation = useVerifySample()
    const correctionMutation = useSubmitCorrection()

    // Text bei Sample-Wechsel initialisieren
    useEffect(() => {
        if (sampleDetail?.ground_truth_text) {
            setCurrentText(sampleDetail.ground_truth_text)
            setIsDirty(false)
        } else if (nextSample?.ocr_text_preview) {
            setCurrentText(nextSample.ocr_text_preview)
            setIsDirty(false)
        }
    }, [sampleDetail?.ground_truth_text, nextSample?.ocr_text_preview])

    // Preview-Bild mit Auth laden
    useEffect(() => {
        if (!sampleId) {
            setPreviewImageUrl(null)
            return
        }

        let cancelled = false
        const controller = new AbortController()

        async function fetchPreview() {
            setPreviewLoading(true)
            setPreviewError(false)

            try {
                const response = await apiClient.get(
                    `/training/samples/${sampleId}/preview?page=0`,
                    {
                        responseType: 'blob',
                        signal: controller.signal,
                    }
                )

                if (cancelled) return

                // Blob URL erstellen
                const blob = new Blob([response.data], { type: 'image/png' })
                const url = URL.createObjectURL(blob)
                setPreviewImageUrl(url)
            } catch (err) {
                if (!cancelled) {
                    console.error('Preview laden fehlgeschlagen:', err)
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
            // Alte Blob URL aufräumen
            if (previewImageUrl) {
                URL.revokeObjectURL(previewImageUrl)
            }
        }
    }, [sampleId])

    // Aktionen
    const handleAccept = useCallback(async () => {
        if (!sampleId || isSubmitting) return
        setIsSubmitting(true)
        try {
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: true, corrected_text: undefined },
            })
            onComplete(false)
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, verifyMutation, onComplete, refetchNext])

    const handleCorrect = useCallback(async () => {
        if (!sampleId || isSubmitting || !isDirty) return
        setIsSubmitting(true)
        try {
            const originalText = sampleDetail?.ground_truth_text || nextSample?.ocr_text_preview || ''
            // Korrektur einreichen
            await correctionMutation.mutateAsync({
                training_sample_id: sampleId,
                original_text: originalText,
                corrected_text: currentText,
                correction_type: correctionType,
                backend_used: 'unknown',
                applies_to_training: true,
            })
            // Sample als verifiziert markieren
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: true, corrected_text: currentText },
            })
            onComplete(true)
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, isDirty, currentText, correctionType, sampleDetail, nextSample, correctionMutation, verifyMutation, onComplete, refetchNext])

    const handleSkip = useCallback(async () => {
        if (isSubmitting) return
        setIsSubmitting(true)
        try {
            // Einfach nächstes Sample laden ohne Aktion
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [isSubmitting, refetchNext])

    const handleReject = useCallback(async () => {
        if (!sampleId || isSubmitting) return
        setIsSubmitting(true)
        try {
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: false, correction_notes: 'Rejected by reviewer' },
            })
            onComplete(false)
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, verifyMutation, onComplete, refetchNext])

    const handleApplyLLMSuggestion = useCallback(() => {
        if (llmReview?.corrected_text) {
            setCurrentText(llmReview.corrected_text)
            setIsDirty(true)
        }
    }, [llmReview])

    // Keyboard Shortcuts Handler
    const handleKeyboardAction = useCallback((action: ReviewAction) => {
        switch (action.type) {
            case 'accept':
                handleAccept()
                break
            case 'correct':
                handleCorrect()
                break
            case 'skip':
                handleSkip()
                break
            case 'reject':
                handleReject()
                break
            case 'llm':
                handleApplyLLMSuggestion()
                break
            case 'help':
                setShowShortcutsHelp(true)
                break
            case 'escape':
                if (showShortcutsHelp) {
                    setShowShortcutsHelp(false)
                } else {
                    onExit()
                }
                break
        }
    }, [handleAccept, handleCorrect, handleSkip, handleReject, handleApplyLLMSuggestion, showShortcutsHelp, onExit])

    // Keyboard Shortcuts
    useKeyboardShortcuts({
        onAction: handleKeyboardAction,
        enabled: !isSubmitting,
    })

    // Text-Änderungen verarbeiten
    const handleTextChange = useCallback((text: string, type: CorrectionType, dirty: boolean) => {
        setCurrentText(text)
        setCorrectionType(type)
        setIsDirty(dirty)
    }, [])

    // Loading-State
    if (sampleLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center space-y-4">
                    <Loader2 className="h-12 w-12 animate-spin mx-auto text-primary" />
                    <p className="text-muted-foreground">Lade nächstes Sample...</p>
                </div>
            </div>
        )
    }

    // Fehler-State
    if (sampleError) {
        return (
            <div className="space-y-4">
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler beim Laden</AlertTitle>
                    <AlertDescription>
                        {sampleError instanceof Error ? sampleError.message : 'Unbekannter Fehler'}
                    </AlertDescription>
                </Alert>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={onExit}>
                        <ArrowLeft className="h-4 w-4 mr-2" />
                        Zurück
                    </Button>
                    <Button onClick={() => refetchNext()}>
                        Erneut versuchen
                    </Button>
                </div>
            </div>
        )
    }

    // Keine Samples mehr
    if (!nextSample) {
        return (
            <div className="space-y-4">
                <Alert>
                    <Check className="h-4 w-4" />
                    <AlertTitle>Keine Samples ausstehend</AlertTitle>
                    <AlertDescription>
                        Alle Training-Samples wurden überprüft. Neue Samples werden automatisch
                        hinzugefügt, wenn Dokumente verarbeitet werden.
                    </AlertDescription>
                </Alert>
                <Button onClick={onExit}>
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Zurück zum Dashboard
                </Button>
            </div>
        )
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="sm" onClick={onExit}>
                        <ArrowLeft className="h-4 w-4 mr-1" />
                        Zurück
                    </Button>
                    <div>
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                Sample #{sessionStats.reviewed_today + 1}
                            </span>
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                            <Badge variant="outline">{nextSample.document_type}</Badge>
                            <Badge
                                variant={
                                    nextSample.priority === 'CRITICAL'
                                        ? 'destructive'
                                        : nextSample.priority === 'HIGH'
                                        ? 'default'
                                        : 'secondary'
                                }
                            >
                                {nextSample.reason || nextSample.priority}
                            </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            Konfidenz: {((nextSample.confidence ?? 0) * 100).toFixed(0)}%
                            {nextSample.is_spot_check && ' | Stichprobe'}
                        </p>
                    </div>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowShortcutsHelp(true)}
                >
                    <Keyboard className="h-4 w-4 mr-1" />
                    Shortcuts
                </Button>
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Linke Spalte: Dokument-Vorschau + LLM */}
                <div className="space-y-4">
                    {/* Dokument-Vorschau */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center gap-2">
                                <ImageIcon className="h-4 w-4" />
                                Dokument-Vorschau
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {(detailLoading || previewLoading) ? (
                                <Skeleton className="h-64 w-full" />
                            ) : previewImageUrl && !previewError ? (
                                <img
                                    src={previewImageUrl}
                                    alt="Dokument-Vorschau"
                                    className="max-h-96 w-full object-contain border rounded bg-white"
                                />
                            ) : (
                                <div className="h-64 flex items-center justify-center bg-muted rounded border">
                                    <div className="text-center text-muted-foreground">
                                        <FileText className="h-12 w-12 mx-auto mb-2" />
                                        <p>{previewError ? 'Vorschau konnte nicht geladen werden' : 'Keine Vorschau verfuegbar'}</p>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Extrahierte Felder */}
                    {sampleDetail?.extracted_fields && Object.keys(sampleDetail.extracted_fields).length > 0 && (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm flex items-center gap-2">
                                    <FileText className="h-4 w-4" />
                                    Extrahierte Felder
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2 text-sm">
                                    {Object.entries(sampleDetail.extracted_fields).map(([key, value]) => (
                                        <div key={key} className="flex justify-between items-start border-b border-border/50 pb-1">
                                            <span className="text-muted-foreground capitalize">{key.replace(/_/g, ' ')}:</span>
                                            <span className="font-mono text-right max-w-[60%] break-words">{String(value)}</span>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* LLM-Vorschlag */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm flex items-center justify-between">
                                <span className="flex items-center gap-2">
                                    <Sparkles className="h-4 w-4" />
                                    LLM-Analyse
                                </span>
                                {llmLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {llmLoading ? (
                                <div className="space-y-2">
                                    <Skeleton className="h-4 w-24" />
                                    <Skeleton className="h-16 w-full" />
                                </div>
                            ) : llmReview ? (
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm">Qualität:</span>
                                            <Badge
                                                variant={
                                                    (llmReview.quality_score ?? 0) >= 8
                                                        ? 'default'
                                                        : (llmReview.quality_score ?? 0) >= 5
                                                        ? 'secondary'
                                                        : 'destructive'
                                                }
                                            >
                                                {(llmReview.quality_score ?? 0).toFixed(1)}/10
                                            </Badge>
                                        </div>
                                        <Badge
                                            variant={
                                                llmReview.recommendation === 'accept'
                                                    ? 'default'
                                                    : llmReview.recommendation === 'needs_human'
                                                    ? 'secondary'
                                                    : 'destructive'
                                            }
                                        >
                                            {llmReview.recommendation === 'accept'
                                                ? 'Akzeptieren'
                                                : llmReview.recommendation === 'needs_human'
                                                ? 'Prüfung nötig'
                                                : 'Ablehnen'}
                                        </Badge>
                                    </div>

                                    {llmReview.issues_found && llmReview.issues_found.length > 0 && (
                                        <div className="space-y-1">
                                            <p className="text-xs font-medium">Erkannte Probleme:</p>
                                            <ul className="text-xs text-muted-foreground space-y-0.5">
                                                {llmReview.issues_found.slice(0, 3).map((issue: string, i: number) => (
                                                    <li key={i} className="flex items-start gap-1">
                                                        <span className="text-yellow-500">•</span>
                                                        {issue}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}

                                    {llmReview.corrected_text && llmReview.corrected_text !== currentText && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={handleApplyLLMSuggestion}
                                            className="w-full"
                                        >
                                            <Sparkles className="h-3 w-3 mr-1" />
                                            LLM-Vorschlag übernehmen
                                            <ShortcutHint shortcut="L" />
                                        </Button>
                                    )}
                                </div>
                            ) : (
                                <div className="text-center text-muted-foreground py-4">
                                    <p className="text-sm">Kein LLM-Review verfügbar</p>
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        onClick={() => refetchLLM()}
                                        className="mt-2"
                                    >
                                        Erneut anfordern
                                    </Button>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Rechte Spalte: Editor */}
                <div>
                    <CorrectionEditor
                        originalText={sampleDetail?.ground_truth_text || nextSample.ocr_text_preview || ''}
                        initialText={currentText}
                        llmSuggestion={llmReview?.corrected_text}
                        onTextChange={handleTextChange}
                        disabled={isSubmitting}
                    />
                </div>
            </div>

            {/* Action Buttons */}
            <Card className="sticky bottom-4">
                <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Button
                                size="lg"
                                onClick={handleAccept}
                                disabled={isSubmitting || isDirty}
                                className="bg-green-600 hover:bg-green-700"
                            >
                                {isSubmitting ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <Check className="h-4 w-4 mr-2" />
                                )}
                                Akzeptieren
                                <ShortcutHint shortcut="A" />
                            </Button>

                            <Button
                                size="lg"
                                onClick={handleCorrect}
                                disabled={isSubmitting || !isDirty}
                                variant="default"
                            >
                                {isSubmitting ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <Check className="h-4 w-4 mr-2" />
                                )}
                                Korrigieren
                                <ShortcutHint shortcut="C" />
                            </Button>
                        </div>

                        <div className="flex items-center gap-2">
                            <Button
                                size="lg"
                                variant="outline"
                                onClick={handleSkip}
                                disabled={isSubmitting}
                            >
                                <SkipForward className="h-4 w-4 mr-2" />
                                Überspringen
                                <ShortcutHint shortcut="S" />
                            </Button>

                            <Button
                                size="lg"
                                variant="destructive"
                                onClick={handleReject}
                                disabled={isSubmitting}
                            >
                                <X className="h-4 w-4 mr-2" />
                                Ablehnen
                                <ShortcutHint shortcut="R" />
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Keyboard Shortcuts Dialog */}
            <KeyboardShortcutsHelp
                open={showShortcutsHelp}
                onOpenChange={setShowShortcutsHelp}
            />
        </div>
    )
}
