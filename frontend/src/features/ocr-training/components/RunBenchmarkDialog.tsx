import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTaskWebSocket } from '@/lib/hooks/use-task-websocket'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
    Play,
    Cpu,
    Loader2,
    CheckCircle2,
    AlertTriangle,
    Info,
} from 'lucide-react'
import { trainingService } from '@/lib/api/services/training'
import { cn } from '@/lib/utils'

// Backend-Konfiguration mit VRAM und GPU-Requirements
const BACKENDS = [
    {
        id: 'deepseek-janus-pro',
        name: 'DeepSeek-Janus-Pro',
        vram: 12,
        requiresGpu: true,
        color: '#8884d8',
        description: 'Beste Qualität für komplexe Dokumente',
    },
    {
        id: 'got-ocr-2.0',
        name: 'GOT-OCR 2.0',
        vram: 10,
        requiresGpu: true,
        color: '#82ca9d',
        description: 'Schnell bei Tabellen und Formeln',
    },
    {
        id: 'surya-gpu',
        name: 'Surya GPU',
        vram: 4,
        requiresGpu: true,
        color: '#ffc658',
        description: 'Schnelle GPU-Variante',
    },
    {
        id: 'surya',
        name: 'Surya (CPU)',
        vram: 0,
        requiresGpu: false,
        color: '#ff8042',
        description: 'CPU-Fallback, keine GPU erforderlich',
    },
] as const

type SampleSelection = 'all_verified' | 'random' | 'new_only'

interface RunBenchmarkDialogProps {
    trigger?: React.ReactNode
    preselectedSampleIds?: string[]
    preselectedBackend?: string
}

export function RunBenchmarkDialog({
    trigger,
    preselectedSampleIds,
    preselectedBackend,
}: RunBenchmarkDialogProps) {
    const [open, setOpen] = useState(false)
    const [selectedBackends, setSelectedBackends] = useState<string[]>(
        preselectedBackend ? [preselectedBackend] : ['deepseek-janus-pro', 'got-ocr-2.0']
    )
    const [sampleSelection, setSampleSelection] = useState<SampleSelection>(
        preselectedSampleIds ? 'all_verified' : 'all_verified'
    )
    const [randomSampleCount, setRandomSampleCount] = useState(50)
    const [forceReprocess, setForceReprocess] = useState(false)
    const [taskId, setTaskId] = useState<string | null>(null)
    const queryClient = useQueryClient()

    // WebSocket für Live-Updates
    const {
        status: taskStatus,
        isConnected,
        progress: wsProgress,
        isComplete: taskComplete,
        error: wsError,
    } = useTaskWebSocket(taskId, {
        onComplete: (_result) => {
            // Invalidate relevante Queries nach Task-Abschluss
            queryClient.invalidateQueries({ queryKey: ['training', 'samples'] })
            queryClient.invalidateQueries({ queryKey: ['training', 'benchmarks'] })
            queryClient.invalidateQueries({ queryKey: ['training', 'stats'] })
            queryClient.invalidateQueries({ queryKey: ['training', 'overview'] })
        },
    })

    // Hole Overview-Stats für Sample-Anzahlen
    const { data: overview } = useQuery({
        queryKey: ['training', 'overview'],
        queryFn: trainingService.getOverviewStats,
        enabled: open,
    })

    // Hole verfügbare Backends
    const { data: availableBackends } = useQuery({
        queryKey: ['training', 'available-backends'],
        queryFn: trainingService.getAvailableBackends,
        enabled: open,
    })

    // Benchmark-Mutation
    const benchmarkMutation = useMutation({
        mutationFn: async () => {
            let sampleIds: string[] = []

            if (preselectedSampleIds?.length) {
                sampleIds = preselectedSampleIds
            } else {
                // Hole Sample-IDs basierend auf Auswahl
                const response = await trainingService.listSamples({
                    verified_only: sampleSelection === 'all_verified',
                    has_ground_truth: true,
                    limit: sampleSelection === 'random' ? randomSampleCount : 1000,
                })
                sampleIds = response.samples.map((s) => s.id)

                // Bei random: zufällige Auswahl
                if (sampleSelection === 'random' && sampleIds.length > randomSampleCount) {
                    sampleIds = shuffleArray(sampleIds).slice(0, randomSampleCount)
                }
            }

            return trainingService.runBenchmark({
                sample_ids: sampleIds,
                backends: selectedBackends,
                force_reprocess: forceReprocess,
            })
        },
        onSuccess: (data) => {
            // Task-ID speichern für WebSocket-Verbindung
            if (data?.task_id) {
                setTaskId(data.task_id)
            } else {
                // Fallback: Queries sofort invalidieren wenn keine task_id
                queryClient.invalidateQueries({ queryKey: ['training', 'samples'] })
                queryClient.invalidateQueries({ queryKey: ['training', 'benchmarks'] })
                queryClient.invalidateQueries({ queryKey: ['training', 'stats'] })
                queryClient.invalidateQueries({ queryKey: ['training', 'overview'] })
                setTimeout(() => setOpen(false), 2000)
            }
        },
    })

    // Berechne geschätzte VRAM-Nutzung
    const estimatedVram = selectedBackends.reduce((total, backendId) => {
        const backend = BACKENDS.find((b) => b.id === backendId)
        return total + (backend?.vram || 0)
    }, 0)

    const vramPercentage = (estimatedVram / 16) * 100 // RTX 4080 = 16GB

    // Toggle Backend-Auswahl
    const toggleBackend = (backendId: string) => {
        setSelectedBackends((prev) =>
            prev.includes(backendId)
                ? prev.filter((id) => id !== backendId)
                : [...prev, backendId]
        )
    }

    // Prüfe ob Backend verfügbar ist
    const isBackendAvailable = (backendId: string) => {
        if (!availableBackends) return true
        return availableBackends.some((b) => b.name === backendId && b.available)
    }

    // Reset state beim Schließen des Dialogs
    const handleOpenChange = (newOpen: boolean) => {
        // Verhindere Schließen während Task läuft (aber nicht abgeschlossen)
        if (!newOpen && taskId && !taskComplete) {
            // Task läuft noch - Dialog NICHT schließen
            return
        }

        if (!newOpen) {
            // Sofort resetten, kein setTimeout (vermeidet Race Condition)
            setTaskId(null)
            benchmarkMutation.reset()
        }
        setOpen(newOpen)
    }

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogTrigger asChild>
                {trigger || (
                    <Button>
                        <Play className="mr-2 h-4 w-4" />
                        Benchmark starten
                    </Button>
                )}
            </DialogTrigger>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Cpu className="h-5 w-5" />
                        Benchmark starten
                    </DialogTitle>
                    <DialogDescription>
                        Vergleiche die OCR-Qualität verschiedener Backends
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-6 py-4">
                    {/* Backend-Auswahl */}
                    <div className="space-y-3">
                        <Label className="text-sm font-medium">Backends auswählen</Label>
                        <div className="grid grid-cols-2 gap-3">
                            {BACKENDS.map((backend) => {
                                const isSelected = selectedBackends.includes(backend.id)
                                const isAvailable = isBackendAvailable(backend.id)

                                return (
                                    <div
                                        key={backend.id}
                                        className={cn(
                                            'relative flex items-start space-x-3 rounded-lg border p-3 cursor-pointer transition-colors',
                                            isSelected
                                                ? 'border-primary bg-primary/5'
                                                : 'border-border hover:bg-muted/50',
                                            !isAvailable && 'opacity-50 cursor-not-allowed'
                                        )}
                                        onClick={() => isAvailable && toggleBackend(backend.id)}
                                    >
                                        <Checkbox
                                            checked={isSelected}
                                            disabled={!isAvailable}
                                            onCheckedChange={() => isAvailable && toggleBackend(backend.id)}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <div
                                                    className="w-2 h-2 rounded-full"
                                                    style={{ backgroundColor: backend.color }}
                                                />
                                                <span className="text-sm font-medium truncate">
                                                    {backend.name}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Badge variant="outline" className="text-xs">
                                                    {backend.vram}GB
                                                </Badge>
                                                {backend.requiresGpu && (
                                                    <Badge variant="secondary" className="text-xs">
                                                        GPU
                                                    </Badge>
                                                )}
                                            </div>
                                            {!isAvailable && (
                                                <span className="text-xs text-destructive mt-1 block">
                                                    Nicht verfügbar
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>

                    {/* VRAM-Warnung */}
                    {vramPercentage > 85 && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
                            <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-yellow-600">Hohe GPU-Auslastung</p>
                                <p className="text-muted-foreground">
                                    Geschätzter VRAM: {estimatedVram}GB ({Number(vramPercentage).toFixed(0)}%).
                                    Backends werden sequenziell verarbeitet.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* VRAM-Anzeige */}
                    <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                            <span className="text-muted-foreground">Geschätzter VRAM</span>
                            <span className="font-medium">{estimatedVram}GB / 16GB</span>
                        </div>
                        <Progress
                            value={vramPercentage}
                            className={cn(
                                'h-2',
                                vramPercentage > 85
                                    ? '[&>div]:bg-yellow-500'
                                    : '[&>div]:bg-green-500'
                            )}
                        />
                    </div>

                    {/* Sample-Auswahl (nur wenn keine preselected) */}
                    {!preselectedSampleIds?.length && (
                        <div className="space-y-3">
                            <Label className="text-sm font-medium">Sample-Auswahl</Label>
                            <div className="space-y-2">
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sample-selection"
                                        checked={sampleSelection === 'all_verified'}
                                        onChange={() => setSampleSelection('all_verified')}
                                        className="text-primary"
                                    />
                                    <span className="text-sm">
                                        Alle verifizierten Samples
                                        <span className="text-muted-foreground ml-1">
                                            ({overview?.verified_samples || 0})
                                        </span>
                                    </span>
                                </label>

                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sample-selection"
                                        checked={sampleSelection === 'random'}
                                        onChange={() => setSampleSelection('random')}
                                        className="text-primary"
                                    />
                                    <span className="text-sm">Zufällige Stichprobe</span>
                                </label>

                                {sampleSelection === 'random' && (
                                    <div className="ml-6 flex items-center gap-2">
                                        <Input
                                            type="number"
                                            value={randomSampleCount}
                                            onChange={(e) =>
                                                setRandomSampleCount(
                                                    Math.max(1, Math.min(500, parseInt(e.target.value) || 50))
                                                )
                                            }
                                            className="w-20 h-8"
                                            min={1}
                                            max={500}
                                        />
                                        <span className="text-sm text-muted-foreground">Samples</span>
                                    </div>
                                )}

                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="sample-selection"
                                        checked={sampleSelection === 'new_only'}
                                        onChange={() => setSampleSelection('new_only')}
                                        className="text-primary"
                                    />
                                    <span className="text-sm">
                                        Nur neue Samples (seit letztem Benchmark)
                                    </span>
                                </label>
                            </div>
                        </div>
                    )}

                    {/* Preselected Samples Info */}
                    {preselectedSampleIds?.length && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-blue-500/10 border border-blue-500/30">
                            <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-blue-600">
                                    {preselectedSampleIds.length} Sample(s) ausgewählt
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Force Reprocess Option */}
                    <div className="flex items-center space-x-2">
                        <Checkbox
                            id="force-reprocess"
                            checked={forceReprocess}
                            onCheckedChange={(checked) => setForceReprocess(checked as boolean)}
                        />
                        <label
                            htmlFor="force-reprocess"
                            className="text-sm cursor-pointer"
                        >
                            Existierende Ergebnisse überschreiben
                        </label>
                    </div>

                    {/* WebSocket Live-Status */}
                    {taskId && !taskComplete && (
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                                    <span className="text-sm font-medium">
                                        {taskStatus?.message || 'Benchmark läuft...'}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    {isConnected ? (
                                        <Badge variant="outline" className="text-xs bg-green-500/10 text-green-600 border-green-500/30">
                                            Live
                                        </Badge>
                                    ) : (
                                        <Badge variant="outline" className="text-xs bg-yellow-500/10 text-yellow-600 border-yellow-500/30">
                                            Verbinde...
                                        </Badge>
                                    )}
                                </div>
                            </div>
                            <Progress value={wsProgress} className="h-2" />
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>
                                    {taskStatus?.current ?? 0} / {taskStatus?.total ?? '?'} Samples
                                </span>
                                <span>{Number(wsProgress).toFixed(0)}%</span>
                            </div>
                        </div>
                    )}

                    {/* Task abgeschlossen */}
                    {taskComplete && taskStatus?.state === 'SUCCESS' && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/30">
                            <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-green-600">Benchmark abgeschlossen!</p>
                                <p className="text-muted-foreground">
                                    {taskStatus.total} Samples verarbeitet
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Task fehlgeschlagen */}
                    {taskComplete && taskStatus?.state === 'FAILURE' && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                            <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-red-600">Benchmark fehlgeschlagen</p>
                                <p className="text-muted-foreground">
                                    {taskStatus.error || 'Unbekannter Fehler'}
                                </p>
                            </div>
                        </div>
                    )}

                    {/* WebSocket Fehler */}
                    {wsError && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
                            <AlertTriangle className="h-4 w-4 text-yellow-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-yellow-600">Verbindungsproblem</p>
                                <p className="text-muted-foreground">{wsError}</p>
                            </div>
                        </div>
                    )}

                    {/* Fallback: Erfolgs-/Fehler-Anzeige ohne WebSocket */}
                    {benchmarkMutation.isSuccess && !taskId && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/30">
                            <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-green-600">Benchmark gestartet!</p>
                                <p className="text-muted-foreground">
                                    {benchmarkMutation.data?.samples_processed} Samples verarbeitet,{' '}
                                    {benchmarkMutation.data?.backends_used?.length} Backends verwendet
                                </p>
                            </div>
                        </div>
                    )}

                    {benchmarkMutation.isError && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
                            <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                            <div className="text-sm">
                                <p className="font-medium text-red-600">Fehler beim Starten</p>
                                <p className="text-muted-foreground">
                                    {(benchmarkMutation.error as Error)?.message || 'Unbekannter Fehler'}
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                <DialogFooter>
                    {taskComplete ? (
                        <Button onClick={() => setOpen(false)}>
                            <CheckCircle2 className="mr-2 h-4 w-4" />
                            Schließen
                        </Button>
                    ) : (
                        <>
                            <Button
                                variant="outline"
                                onClick={() => setOpen(false)}
                                disabled={benchmarkMutation.isPending || !!(taskId && !taskComplete)}
                            >
                                Abbrechen
                            </Button>
                            <Button
                                onClick={() => benchmarkMutation.mutate()}
                                disabled={
                                    selectedBackends.length === 0 ||
                                    benchmarkMutation.isPending ||
                                    !!taskId
                                }
                            >
                                {benchmarkMutation.isPending ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Starte...
                                    </>
                                ) : taskId ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Läuft...
                                    </>
                                ) : (
                                    <>
                                        <Play className="mr-2 h-4 w-4" />
                                        Benchmark starten
                                    </>
                                )}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

// Hilfsfunktion zum Mischen eines Arrays
function shuffleArray<T>(array: T[]): T[] {
    const shuffled = [...array]
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    return shuffled
}
