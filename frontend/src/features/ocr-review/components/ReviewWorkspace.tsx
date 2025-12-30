/**
 * Review Workspace Komponente
 * Vollbild-Review mit Sample-Anzeige, strukturierter Datenansicht und OCR-Text Editor
 *
 * NEU: Tab-System mit "Strukturiert" (Default) und "OCR-Text"
 */

import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '@/lib/api/client'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
    ChevronRight,
    LayoutGrid,
    AlignLeft,
    ZoomIn,
    ZoomOut,
    RotateCcw,
} from 'lucide-react'

import { useNextSample, useSampleDetail, useLLMReview, useVerifySample, useSubmitCorrection } from '../hooks/use-review-queries'
import { useKeyboardShortcuts, type ReviewAction } from '../hooks/use-keyboard-shortcuts'
import { useExtractedDataForReview } from '../hooks/use-extracted-data-review'
import { useFieldCorrections } from '../hooks/use-field-corrections'
import { CorrectionEditor } from './CorrectionEditor'
import { KeyboardShortcutsHelp, ShortcutHint } from './KeyboardShortcutsHelp'
import { StructuredReviewPanel } from './StructuredReviewPanel'
import type { CorrectionType } from '../types'
import type { ExtractedInvoiceData } from '@/features/extracted-data/types/extracted-data.types'

/**
 * Extrahiert alle Feldnamen aus InvoiceData für Batch-Bestätigung.
 */
function getAllInvoiceFields(invoice: ExtractedInvoiceData): string[] {
    const fields: string[] = []

    // Identifikation
    if (invoice.invoice_number) fields.push('invoice_number')
    if (invoice.invoice_date) fields.push('invoice_date')
    if (invoice.due_date) fields.push('due_date')
    if (invoice.order_number) fields.push('order_number')
    if (invoice.customer_number) fields.push('customer_number')
    if (invoice.supplier_number) fields.push('supplier_number')

    // Absender
    if (invoice.sender?.company) fields.push('sender_company')
    if (invoice.sender?.street) fields.push('sender_street')
    if (invoice.sender?.zip_code) fields.push('sender_zip_code')
    if (invoice.sender?.city) fields.push('sender_city')
    if (invoice.sender?.country) fields.push('sender_country')
    if (invoice.sender_vat_id) fields.push('sender_vat_id')
    if (invoice.sender_tax_number) fields.push('sender_tax_number')

    // Empfänger
    if (invoice.recipient?.company) fields.push('recipient_company')
    if (invoice.recipient?.street) fields.push('recipient_street')
    if (invoice.recipient?.zip_code) fields.push('recipient_zip_code')
    if (invoice.recipient?.city) fields.push('recipient_city')
    if (invoice.recipient?.country) fields.push('recipient_country')
    if (invoice.recipient_vat_id) fields.push('recipient_vat_id')

    // Beträge
    if (invoice.net_amount) fields.push('net_amount')
    if (invoice.vat_amount) fields.push('vat_amount')
    if (invoice.gross_amount) fields.push('gross_amount')
    if (invoice.vat_rate) fields.push('vat_rate')
    if (invoice.currency) fields.push('currency')

    // Zahlungsbedingungen
    if (invoice.payment_terms) fields.push('payment_terms')
    if (invoice.payment_terms_days) fields.push('payment_terms_days')
    if (invoice.discount_percent) fields.push('discount_percent')
    if (invoice.discount_days) fields.push('discount_days')

    // Bank
    if (invoice.sender_bank?.iban) fields.push('sender_iban')
    if (invoice.sender_bank?.bic) fields.push('sender_bic')
    if (invoice.sender_bank?.bank_name) fields.push('sender_bank_name')
    // account_holder is on ExtractedBankAccount type
    const bankAccount = invoice.sender_bank as { account_holder?: string } | undefined
    if (bankAccount?.account_holder) fields.push('sender_account_holder')

    return fields
}

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
    const [activeTab, setActiveTab] = useState<'structured' | 'ocr-text'>('structured')
    const [zoomLevel, setZoomLevel] = useState(100) // Zoom in Prozent

    // Zoom-Funktionen
    const handleZoomIn = useCallback(() => {
        setZoomLevel(prev => Math.min(prev + 25, 300))
    }, [])

    const handleZoomOut = useCallback(() => {
        setZoomLevel(prev => Math.max(prev - 25, 50))
    }, [])

    const handleZoomReset = useCallback(() => {
        setZoomLevel(100)
    }, [])

    // Queries
    const {
        data: nextSampleData,
        isLoading: sampleLoading,
        error: sampleError,
        refetch: refetchNext,
    } = useNextSample()

    const nextSample = nextSampleData?.item
    const sampleId = nextSample?.sample_id
    const documentId = nextSample?.document_id

    const {
        data: sampleDetail,
        isLoading: detailLoading,
    } = useSampleDetail(sampleId)

    const {
        data: llmReview,
        isLoading: _llmLoading,
        refetch: _refetchLLM,
    } = useLLMReview(sampleId)

    // NEU: ExtractedData Hook
    const extractedDataReview = useExtractedDataForReview(documentId, nextSample)

    // NEU: Field Corrections Hook
    const corrections = useFieldCorrections({
        sampleId,
        documentId,
        backendUsed: sampleDetail?.benchmarks ? Object.keys(sampleDetail.benchmarks)[0] : 'unknown',
    })

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
        // Reset corrections bei Sample-Wechsel
        corrections.reset()
    }, [sampleDetail?.ground_truth_text, nextSample?.ocr_text_preview, sampleId])

    // Preview-Bild mit Auth laden
    useEffect(() => {
        if (!sampleId) {
            setPreviewImageUrl(null)
            return
        }

        let cancelled = false
        const controller = new AbortController()
        // FIX: Lokale Variable für Cleanup statt State (verhindert stale closure)
        let currentBlobUrl: string | null = null

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
                currentBlobUrl = URL.createObjectURL(blob)
                setPreviewImageUrl(currentBlobUrl)
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
            // FIX: Lokale Variable für Cleanup (nicht stale State)
            if (currentBlobUrl) {
                URL.revokeObjectURL(currentBlobUrl)
            }
        }
    }, [sampleId])

    // Hat Änderungen (OCR-Text oder strukturierte Felder)?
    const hasAnyChanges = isDirty || corrections.hasCorrections

    // Aktionen
    const handleAccept = useCallback(async () => {
        if (!sampleId || isSubmitting) return
        setIsSubmitting(true)
        try {
            // Wenn strukturierte Korrekturen vorhanden, diese auch submitten
            if (corrections.hasCorrections) {
                await corrections.submitCorrections()
            }
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: true, corrected_text: undefined },
            })
            onComplete(corrections.hasCorrections)
            corrections.reset()
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, corrections, verifyMutation, onComplete, refetchNext])

    const handleCorrect = useCallback(async () => {
        if (!sampleId || isSubmitting || !hasAnyChanges) return
        setIsSubmitting(true)
        try {
            // OCR-Text Korrektur (falls dirty)
            if (isDirty) {
                const originalText = sampleDetail?.ground_truth_text || nextSample?.ocr_text_preview || ''
                await correctionMutation.mutateAsync({
                    training_sample_id: sampleId,
                    original_text: originalText,
                    corrected_text: currentText,
                    correction_type: correctionType,
                    backend_used: 'unknown',
                    applies_to_training: true,
                })
            }

            // Strukturierte Feld-Korrekturen (falls vorhanden)
            if (corrections.hasCorrections) {
                await corrections.submitCorrections()
            }

            // Sample als verifiziert markieren
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: true, corrected_text: isDirty ? currentText : undefined },
            })
            onComplete(true)
            corrections.reset()
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, hasAnyChanges, isDirty, currentText, correctionType, sampleDetail, nextSample, correctionMutation, verifyMutation, corrections, onComplete, refetchNext])

    const handleSkip = useCallback(async () => {
        if (isSubmitting) return
        setIsSubmitting(true)
        try {
            corrections.reset()
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [isSubmitting, corrections, refetchNext])

    const handleReject = useCallback(async () => {
        if (!sampleId || isSubmitting) return
        setIsSubmitting(true)
        try {
            await verifyMutation.mutateAsync({
                sampleId,
                data: { approved: false, correction_notes: 'Rejected by reviewer' },
            })
            onComplete(false)
            corrections.reset()
            refetchNext()
        } finally {
            setIsSubmitting(false)
        }
    }, [sampleId, isSubmitting, verifyMutation, onComplete, corrections, refetchNext])

    const handleApplyLLMSuggestion = useCallback(() => {
        if (llmReview?.corrected_text) {
            setCurrentText(llmReview.corrected_text)
            setIsDirty(true)
        }
    }, [llmReview])

    // Tab-Wechsel
    const handleTabChange = useCallback((tab: string) => {
        setActiveTab(tab as 'structured' | 'ocr-text')
    }, [])

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
            case 'tab1':
                setActiveTab('structured')
                break
            case 'tab2':
                setActiveTab('ocr-text')
                break
            case 'nextField':
            case 'prevField':
                // TODO: Implement field navigation in StructuredReviewPanel
                // For now, these are handled by browser's native Tab behavior
                break
            case 'confirmField':
                // TODO: Confirm currently focused field
                // Would need field focus tracking in StructuredReviewPanel
                break
            case 'confirmAll':
                // Bestätigt alle sichtbaren Felder (nur im Strukturiert-Tab)
                if (activeTab === 'structured' && extractedDataReview.invoiceData) {
                    const allFields = getAllInvoiceFields(extractedDataReview.invoiceData)
                    corrections.confirmAllFields(allFields)
                }
                break
        }
    }, [handleAccept, handleCorrect, handleSkip, handleReject, handleApplyLLMSuggestion, showShortcutsHelp, onExit, activeTab, extractedDataReview.invoiceData, corrections])

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
        <div className="space-y-3 -mx-4 px-4">
            {/* Header - kompakt */}
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
                            <Badge variant="outline">
                                {nextSample.document_type === 'invoice'
                                    ? extractedDataReview.invoiceData?.invoice_direction === 'incoming'
                                        ? 'Eingangsrechnung'
                                        : extractedDataReview.invoiceData?.invoice_direction === 'outgoing'
                                        ? 'Ausgangsrechnung'
                                        : 'Rechnung'
                                    : nextSample.document_type === 'order'
                                    ? 'Bestellung'
                                    : nextSample.document_type === 'contract'
                                    ? 'Vertrag'
                                    : nextSample.document_type}
                            </Badge>
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
                            Konfidenz: {(Number(nextSample.confidence ?? 0) * 100).toFixed(0)}%
                            {nextSample.is_spot_check && ' | Stichprobe'}
                            {corrections.hasCorrections && ` | ${corrections.correctionCount} Korrekturen`}
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

            {/* Main Content - Volle Breite, optimiertes Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[calc(100vh-240px)]">
                {/* Linke Spalte: Dokument-Vorschau (8/12 = 66% Breite) */}
                <div className="lg:col-span-8 flex flex-col">
                    <Card className="flex-1 flex flex-col border-0 shadow-none bg-transparent">
                        <CardHeader className="pb-1 pt-0 px-0 flex-shrink-0">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    {/* Zoom Controls */}
                                    <div className="flex items-center gap-1 bg-muted/50 rounded-md p-0.5">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-7 w-7"
                                            onClick={handleZoomOut}
                                            disabled={zoomLevel <= 50}
                                            title="Verkleinern"
                                        >
                                            <ZoomOut className="h-3.5 w-3.5" />
                                        </Button>
                                        <span className="text-xs font-mono w-12 text-center">{zoomLevel}%</span>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-7 w-7"
                                            onClick={handleZoomIn}
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
                                                onClick={handleZoomReset}
                                                title="Zurücksetzen"
                                            >
                                                <RotateCcw className="h-3.5 w-3.5" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                                {/* LLM-Status kompakt */}
                                {llmReview && (
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-muted-foreground">
                                            LLM: {Number(llmReview.quality_score ?? 0).toFixed(0)}/10
                                        </span>
                                        {llmReview.corrected_text && llmReview.corrected_text !== currentText && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                onClick={handleApplyLLMSuggestion}
                                                className="h-7 px-2 text-xs"
                                            >
                                                <Sparkles className="h-3 w-3 mr-1" />
                                                Vorschlag
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="flex-1 overflow-hidden p-0">
                            {(detailLoading || previewLoading) ? (
                                <Skeleton className="h-full w-full min-h-[500px]" />
                            ) : previewImageUrl && !previewError ? (
                                <div
                                    className="h-full w-full bg-zinc-100 dark:bg-zinc-900 rounded border overflow-auto"
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
                                <div className="h-full min-h-[500px] flex items-center justify-center bg-muted/30 rounded border">
                                    <div className="text-center text-muted-foreground">
                                        <FileText className="h-12 w-12 mx-auto mb-2 opacity-40" />
                                        <p className="text-sm">{previewError ? 'Vorschau nicht verfügbar' : 'Kein Dokument'}</p>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Rechte Spalte: Daten-Panel (4/12 = 33% Breite) */}
                <div className="lg:col-span-4 flex flex-col">
                    <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col">
                        <TabsList className="grid w-full grid-cols-2 flex-shrink-0">
                            <TabsTrigger value="structured" className="flex items-center gap-1.5 text-sm">
                                <LayoutGrid className="h-3.5 w-3.5" />
                                Daten
                            </TabsTrigger>
                            <TabsTrigger value="ocr-text" className="flex items-center gap-1.5 text-sm">
                                <AlignLeft className="h-3.5 w-3.5" />
                                OCR-Text
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="structured" className="flex-1 mt-3 overflow-hidden">
                            <StructuredReviewPanel
                                queueItem={nextSample}
                                extractedDataReview={extractedDataReview}
                                corrections={corrections}
                                disabled={isSubmitting}
                                className="h-full"
                            />
                        </TabsContent>

                        <TabsContent value="ocr-text" className="flex-1 mt-3">
                            <CorrectionEditor
                                originalText={sampleDetail?.ground_truth_text || nextSample.ocr_text_preview || ''}
                                initialText={currentText}
                                llmSuggestion={llmReview?.corrected_text}
                                onTextChange={handleTextChange}
                                disabled={isSubmitting}
                            />
                        </TabsContent>
                    </Tabs>
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
                                disabled={isSubmitting || hasAnyChanges}
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
                                disabled={isSubmitting || !hasAnyChanges}
                                variant="default"
                            >
                                {isSubmitting ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <Check className="h-4 w-4 mr-2" />
                                )}
                                Korrigieren
                                {corrections.hasCorrections && (
                                    <Badge variant="secondary" className="ml-2 text-xs">
                                        {corrections.correctionCount}
                                    </Badge>
                                )}
                                <ShortcutHint shortcut="C" />
                            </Button>
                        </div>

                        <div className="flex items-center gap-4">
                            <span className="text-xs text-muted-foreground">
                                {sessionStats.reviewed_today} heute | {sessionStats.corrections_today} Korrekturen
                            </span>

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
