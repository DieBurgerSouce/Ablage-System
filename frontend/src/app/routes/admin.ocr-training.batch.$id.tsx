import { useState, useEffect, useCallback, useMemo } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
    ArrowLeft,
    ArrowRight,
    SkipForward,
    Save,
    Clock,
    CheckCircle2,
    FileText,
    Keyboard,
    Loader2,
    AlertTriangle,
    Languages,
    Type,
    Image,
    Trophy,
} from 'lucide-react'
import { trainingService, type TrainingSample } from '@/lib/api/services/training'
import { DiffView } from '@/features/ocr-training/components/DiffView'

export const Route = createFileRoute('/admin/ocr-training/batch/$id')({
    component: BatchWorkflowPage,
})

// Tastaturkürzel-Konfiguration
const KEYBOARD_SHORTCUTS = {
    save: { key: 'Enter', modifier: 'ctrl', label: 'Strg + Enter' },
    skip: { key: 's', modifier: 'ctrl', label: 'Strg + S' },
    previous: { key: 'ArrowLeft', modifier: 'alt', label: 'Alt + Links' },
    next: { key: 'ArrowRight', modifier: 'alt', label: 'Alt + Rechts' },
} as const

// Fehlertypen für Markierungen
const ERROR_TYPES = [
    { id: 'umlaut', label: 'Umlaut-Fehler', icon: Languages, description: 'ae->ä, oe->ö, ue->ü, ss->ß' },
    { id: 'capitalization', label: 'Groß-/Kleinschreibung', icon: Type, description: 'Falsche Großschreibung' },
    { id: 'ocr_noise', label: 'OCR-Rauschen', icon: Image, description: 'Unlesbare oder falsche Zeichen' },
    { id: 'missing_text', label: 'Fehlender Text', icon: FileText, description: 'Text wurde nicht erkannt' },
] as const

function BatchWorkflowPage() {
    const { id: batchId } = Route.useParams()
    const navigate = useNavigate()
    const queryClient = useQueryClient()

    // State
    const [correctedText, setCorrectedText] = useState('')
    const [selectedErrorTypes, setSelectedErrorTypes] = useState<string[]>([])
    const [notes, setNotes] = useState('')
    const [startTime, setStartTime] = useState<number>(() => Date.now())
    const [elapsedSeconds, setElapsedSeconds] = useState(0)
    const [showKeyboardHelp, setShowKeyboardHelp] = useState(false)
    const [autoSaveEnabled] = useState(true)
    const [lastAutoSave, setLastAutoSave] = useState<Date | null>(null)

    // Queries
    const { data: batch, isLoading: isLoadingBatch } = useQuery({
        queryKey: ['training', 'batch', batchId],
        queryFn: () => trainingService.getBatch(batchId),
    })

    const { data: currentItem, isLoading: isLoadingItem, refetch: refetchItem } = useQuery({
        queryKey: ['training', 'batch', batchId, 'next-item'],
        queryFn: () => trainingService.getNextBatchItem(batchId),
        enabled: !!batch,
    })

    const { data: currentSample, isLoading: isLoadingSample } = useQuery({
        queryKey: ['training', 'sample', currentItem?.training_sample_id],
        queryFn: () => trainingService.getSample(currentItem!.training_sample_id),
        enabled: !!currentItem?.training_sample_id,
    })

    const { data: sampleBenchmarks } = useQuery({
        queryKey: ['training', 'sample', currentItem?.training_sample_id, 'benchmarks'],
        queryFn: () => trainingService.getSampleBenchmarks(currentItem!.training_sample_id),
        enabled: !!currentItem?.training_sample_id,
    })

    // Beste OCR-Text ermitteln
    const bestOcrText = useMemo(() => {
        if (!sampleBenchmarks?.length) return ''
        // Sortiere nach CER (niedriger = besser)
        const sorted = [...sampleBenchmarks].sort((a, b) => (a.cer ?? 1) - (b.cer ?? 1))
        return sorted[0]?.raw_text || ''
    }, [sampleBenchmarks])

    // Initialisiere Form-State wenn neues Sample geladen wird (legitimes Pattern für Form-Reset)
    /* eslint-disable react-hooks/set-state-in-effect */
    useEffect(() => {
        if (currentSample) {
            setCorrectedText(currentSample.ground_truth_text || bestOcrText || '')
            setSelectedErrorTypes([])
            setNotes('')
            setStartTime(Date.now())
            setElapsedSeconds(0)
        }
    }, [currentSample, bestOcrText])
    /* eslint-enable react-hooks/set-state-in-effect */

    // Timer für verstrichene Zeit
    useEffect(() => {
        const interval = setInterval(() => {
            setElapsedSeconds(Math.round((Date.now() - startTime) / 1000))
        }, 1000)
        return () => clearInterval(interval)
    }, [startTime])

    // Mutations
    const updateItemMutation = useMutation({
        mutationFn: (data: {
            status: string
            validation_notes?: string
            validation_time_seconds?: number
        }) => trainingService.updateBatchItem(batchId, currentItem!.id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'batch', batchId] })
            refetchItem()
        },
    })

    const updateSampleMutation = useMutation({
        mutationFn: (data: Partial<TrainingSample>) =>
            trainingService.updateSample(currentSample!.id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'sample', currentSample!.id] })
        },
    })

    // Handler (müssen vor handleKeyDown definiert werden)
    const handleSaveAndNext = useCallback(async () => {
        if (!currentItem || !currentSample) return

        const validationTime = Math.round((Date.now() - startTime) / 1000)

        // Speichere korrigierten Text
        await updateSampleMutation.mutateAsync({
            ground_truth_text: correctedText,
            annotation_notes: notes || undefined,
            status: 'annotated',
        })

        // Markiere Item als abgeschlossen
        await updateItemMutation.mutateAsync({
            status: 'completed',
            validation_notes: selectedErrorTypes.length > 0
                ? `Fehlertypen: ${selectedErrorTypes.join(', ')}${notes ? ` | ${notes}` : ''}`
                : notes || undefined,
            validation_time_seconds: validationTime,
        })
    }, [currentItem, currentSample, startTime, correctedText, notes, selectedErrorTypes, updateSampleMutation, updateItemMutation])

    const handleSkip = useCallback(async () => {
        if (!currentItem) return

        await updateItemMutation.mutateAsync({
            status: 'skipped',
            validation_notes: notes || 'Übersprungen',
        })
    }, [currentItem, notes, updateItemMutation])

    // Keyboard Shortcuts
    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        // Strg + Enter: Speichern
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault()
            handleSaveAndNext()
        }
        // Strg + S: Überspringen
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault()
            handleSkip()
        }
        // Alt + Links: Zurück
        if (e.altKey && e.key === 'ArrowLeft') {
            e.preventDefault()
            // TODO: Previous item navigation
        }
        // Alt + Rechts: Weiter
        if (e.altKey && e.key === 'ArrowRight') {
            e.preventDefault()
            handleSaveAndNext()
        }
        // ESC: Keyboard-Hilfe toggle
        if (e.key === 'Escape') {
            setShowKeyboardHelp((prev) => !prev)
        }
    }, [handleSaveAndNext, handleSkip])

    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [handleKeyDown])

    // Auto-Save
    useEffect(() => {
        if (!autoSaveEnabled || !currentSample || !correctedText) return

        const interval = setInterval(() => {
            if (correctedText !== currentSample.ground_truth_text) {
                updateSampleMutation.mutate({
                    ground_truth_text: correctedText,
                    annotation_notes: notes || undefined,
                })
                setLastAutoSave(new Date())
            }
        }, 30000) // Alle 30 Sekunden

        return () => clearInterval(interval)
    }, [autoSaveEnabled, currentSample, correctedText, notes, updateSampleMutation])

    // Loading State
    if (isLoadingBatch || isLoadingItem || isLoadingSample) {
        return (
            <div className="flex items-center justify-center h-[60vh]">
                <div className="text-center space-y-4">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                    <p className="text-muted-foreground">Lade Batch...</p>
                </div>
            </div>
        )
    }

    // Batch completed
    if (batch && !currentItem) {
        return (
            <div className="max-w-2xl mx-auto py-12">
                <Card className="text-center">
                    <CardHeader>
                        <div className="mx-auto mb-4 w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
                            <Trophy className="h-8 w-8 text-green-600" />
                        </div>
                        <CardTitle className="text-2xl">Batch abgeschlossen!</CardTitle>
                        <CardDescription>
                            Alle Items in "{batch.name}" wurden bearbeitet.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="grid grid-cols-3 gap-4 text-center">
                            <div>
                                <div className="text-3xl font-bold text-green-600">
                                    {batch.items_completed}
                                </div>
                                <div className="text-sm text-muted-foreground">Abgeschlossen</div>
                            </div>
                            <div>
                                <div className="text-3xl font-bold text-yellow-600">
                                    {batch.actual_size - batch.items_completed - batch.items_pending}
                                </div>
                                <div className="text-sm text-muted-foreground">Übersprungen</div>
                            </div>
                            <div>
                                <div className="text-3xl font-bold">
                                    {batch.actual_size}
                                </div>
                                <div className="text-sm text-muted-foreground">Gesamt</div>
                            </div>
                        </div>
                        <Button onClick={() => navigate({ to: '/admin/ocr-training' })}>
                            Zurück zum Dashboard
                        </Button>
                    </CardContent>
                </Card>
            </div>
        )
    }

    if (!batch || !currentItem || !currentSample) {
        return (
            <div className="flex items-center justify-center h-[60vh]">
                <div className="text-center space-y-4">
                    <AlertTriangle className="h-8 w-8 mx-auto text-yellow-500" />
                    <p className="text-muted-foreground">Batch oder Sample nicht gefunden</p>
                    <Button variant="outline" onClick={() => navigate({ to: '/admin/ocr-training' })}>
                        Zurück
                    </Button>
                </div>
            </div>
        )
    }

    const progress = ((batch.items_completed / batch.actual_size) * 100)
    const filename = currentSample.file_path.split(/[/\\]/).pop() || currentSample.file_path

    return (
        <div className="space-y-4">
            {/* Header mit Progress */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate({ to: '/admin/ocr-training' })}
                    >
                        <ArrowLeft className="mr-2 h-4 w-4" />
                        Zurück
                    </Button>
                    <div>
                        <h1 className="text-xl font-bold">{batch.name}</h1>
                        <p className="text-sm text-muted-foreground">
                            {batch.items_completed + 1} / {batch.actual_size} Items
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowKeyboardHelp(!showKeyboardHelp)}
                    >
                        <Keyboard className="mr-2 h-4 w-4" />
                        Tastenkürzel
                    </Button>
                    {lastAutoSave && (
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Save className="h-3 w-3" />
                            Gespeichert: {lastAutoSave.toLocaleTimeString('de-DE')}
                        </span>
                    )}
                </div>
            </div>

            {/* Progress Bar */}
            <div className="space-y-1">
                <Progress value={progress} className="h-2" />
                <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{batch.items_completed} erledigt</span>
                    <span>{batch.items_pending} verbleibend</span>
                </div>
            </div>

            {/* Keyboard Shortcuts Help */}
            {showKeyboardHelp && (
                <Card className="bg-muted/50">
                    <CardContent className="py-3">
                        <div className="flex flex-wrap gap-4 text-sm">
                            {Object.entries(KEYBOARD_SHORTCUTS).map(([action, config]) => (
                                <div key={action} className="flex items-center gap-2">
                                    <Badge variant="outline" className="font-mono">
                                        {config.label}
                                    </Badge>
                                    <span className="text-muted-foreground capitalize">{action}</span>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Main Content */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Linke Spalte: Original + OCR */}
                <div className="space-y-4">
                    {/* Sample Info */}
                    <Card>
                        <CardHeader className="pb-2">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-sm flex items-center gap-2">
                                    <FileText className="h-4 w-4" />
                                    {filename}
                                </CardTitle>
                                <div className="flex gap-1">
                                    {currentSample.has_umlauts && (
                                        <Badge variant="secondary" className="text-xs">Umlaute</Badge>
                                    )}
                                    {currentSample.has_tables && (
                                        <Badge variant="secondary" className="text-xs">Tabellen</Badge>
                                    )}
                                    {currentSample.has_fraktur && (
                                        <Badge variant="secondary" className="text-xs">Fraktur</Badge>
                                    )}
                                </div>
                            </div>
                            <CardDescription>
                                Sprache: {currentSample.language.toUpperCase()} |
                                Typ: {currentSample.document_type || 'Unbekannt'}
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {/* Thumbnail */}
                            {currentSample.thumbnail_path && (
                                <div className="mb-4 rounded-lg border bg-muted/30 p-2">
                                    <img
                                        src={`/api/v1/files/${currentSample.thumbnail_path}`}
                                        alt="Document preview"
                                        className="max-h-[200px] mx-auto object-contain"
                                    />
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* OCR-Ergebnisse */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm">OCR-Ergebnisse</CardTitle>
                            <CardDescription>
                                {sampleBenchmarks?.length || 0} Backend(s) verfügbar
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {sampleBenchmarks?.length ? (
                                <div className="space-y-3">
                                    {sampleBenchmarks.map((result) => (
                                        <div
                                            key={result.id}
                                            className="rounded-lg border p-3 space-y-2"
                                        >
                                            <div className="flex items-center justify-between">
                                                <span className="font-medium text-sm">
                                                    {result.backend_name}
                                                </span>
                                                <div className="flex gap-2">
                                                    {result.cer !== undefined && (
                                                        <Badge variant="outline" className="text-xs">
                                                            CER: {(Number(result.cer) * 100).toFixed(1)}%
                                                        </Badge>
                                                    )}
                                                    {result.umlaut_accuracy !== undefined && (
                                                        <Badge
                                                            variant={Number(result.umlaut_accuracy) >= 0.95 ? 'default' : 'secondary'}
                                                            className="text-xs"
                                                        >
                                                            Umlaut: {(Number(result.umlaut_accuracy) * 100).toFixed(0)}%
                                                        </Badge>
                                                    )}
                                                </div>
                                            </div>
                                            <pre className="text-xs bg-muted/50 p-2 rounded max-h-[100px] overflow-auto whitespace-pre-wrap">
                                                {result.raw_text || 'Kein Text'}
                                            </pre>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="w-full text-xs"
                                                onClick={() => setCorrectedText(result.raw_text || '')}
                                            >
                                                Als Basis verwenden
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-sm text-muted-foreground text-center py-4">
                                    Noch keine OCR-Ergebnisse
                                </p>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Rechte Spalte: Korrektur */}
                <div className="space-y-4">
                    {/* Korrektur-Editor */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm">Ihre Korrektur</CardTitle>
                            <CardDescription>
                                Korrigieren Sie den OCR-Text oder bestätigen Sie ihn
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <Textarea
                                value={correctedText}
                                onChange={(e) => setCorrectedText(e.target.value)}
                                className="min-h-[200px] font-mono text-sm"
                                placeholder="Korrigierten Text hier eingeben..."
                            />

                            {/* Diff-Anzeige wenn Text geändert */}
                            {bestOcrText && correctedText !== bestOcrText && (
                                <div className="rounded-lg border p-3">
                                    <h4 className="text-xs font-medium mb-2 text-muted-foreground">
                                        Änderungen:
                                    </h4>
                                    <DiffView
                                        original={bestOcrText}
                                        modified={correctedText}
                                    />
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Fehlertypen */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm">Fehler-Kategorien</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 gap-2">
                                {ERROR_TYPES.map((errorType) => {
                                    const Icon = errorType.icon
                                    const isSelected = selectedErrorTypes.includes(errorType.id)

                                    return (
                                        <div
                                            key={errorType.id}
                                            className={`flex items-center space-x-2 rounded-lg border p-2 cursor-pointer transition-colors ${
                                                isSelected ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
                                            }`}
                                            onClick={() => {
                                                setSelectedErrorTypes((prev) =>
                                                    isSelected
                                                        ? prev.filter((id) => id !== errorType.id)
                                                        : [...prev, errorType.id]
                                                )
                                            }}
                                        >
                                            <Checkbox
                                                checked={isSelected}
                                                onCheckedChange={() => {
                                                    setSelectedErrorTypes((prev) =>
                                                        isSelected
                                                            ? prev.filter((id) => id !== errorType.id)
                                                            : [...prev, errorType.id]
                                                    )
                                                }}
                                            />
                                            <Icon className="h-4 w-4 text-muted-foreground" />
                                            <div className="flex-1 min-w-0">
                                                <Label className="text-xs font-medium cursor-pointer">
                                                    {errorType.label}
                                                </Label>
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Notizen */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm">Notizen (optional)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <Textarea
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                className="min-h-[60px] text-sm"
                                placeholder="Optionale Anmerkungen..."
                            />
                        </CardContent>
                    </Card>

                    {/* Aktions-Buttons */}
                    <div className="flex justify-between gap-4">
                        <Button
                            variant="outline"
                            onClick={handleSkip}
                            disabled={updateItemMutation.isPending}
                        >
                            <SkipForward className="mr-2 h-4 w-4" />
                            Überspringen
                        </Button>
                        <div className="flex gap-2">
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {elapsedSeconds}s
                            </div>
                            <Button
                                onClick={handleSaveAndNext}
                                disabled={updateItemMutation.isPending || updateSampleMutation.isPending}
                            >
                                {updateItemMutation.isPending || updateSampleMutation.isPending ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Speichere...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle2 className="mr-2 h-4 w-4" />
                                        Speichern & Weiter
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
