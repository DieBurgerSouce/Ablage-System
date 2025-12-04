import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
    CheckCircle2,
    XCircle,
    FileText,
    Clock,
    Cpu,
    Languages,
    Loader2,
} from 'lucide-react'
import type { TrainingSample, BenchmarkResult } from '@/lib/api/services/training'
import { DiffView, DiffStats } from './DiffView'
import { BACKEND_CONFIG, BACKEND_IDS } from '../constants/backend-config'
import {
    useSampleBenchmarks,
    useVerifySample,
    useCreateCorrection,
} from '../hooks/use-training-queries'

interface SampleDetailModalProps {
    sample: TrainingSample | null
    benchmarks?: BenchmarkResult[]
    open: boolean
    onOpenChange: (open: boolean) => void
}

export function SampleDetailModal({ sample, benchmarks: propBenchmarks, open, onOpenChange }: SampleDetailModalProps) {
    // Hole Benchmark-Ergebnisse für dieses Sample (falls nicht als Prop übergeben)
    const { data: fetchedBenchmarks, isLoading: isLoadingBenchmarks } = useSampleBenchmarks(
        sample?.id ?? '',
        !!sample?.id && open && !propBenchmarks
    )

    const benchmarks = propBenchmarks ?? fetchedBenchmarks

    // Mutations für Aktionen
    const verifyMutation = useVerifySample()
    const correctionMutation = useCreateCorrection()

    if (!sample) return null

    const groundTruth = sample.ground_truth_text || ''
    const filename = sample.file_path.split('/').pop() || sample.file_path

    // Gruppiere Benchmarks nach Backend
    const benchmarksByBackend: Record<string, BenchmarkResult> = {}
    benchmarks?.forEach((b) => {
        if (!benchmarksByBackend[b.backend_name]) {
            benchmarksByBackend[b.backend_name] = b
        }
    })

    // Finde besten Backend basierend auf CER
    let bestBackend: string | null = null
    let bestCER = Infinity
    Object.entries(benchmarksByBackend).forEach(([name, b]) => {
        if (b.cer !== undefined && b.cer < bestCER) {
            bestCER = b.cer
            bestBackend = name
        }
    })

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-6xl max-h-[90vh]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5" />
                        {filename}
                    </DialogTitle>
                    <DialogDescription className="flex items-center gap-4">
                        <Badge
                            variant={
                                sample.status === 'verified'
                                    ? 'default'
                                    : sample.status === 'pending'
                                      ? 'secondary'
                                      : 'outline'
                            }
                        >
                            {sample.status}
                        </Badge>
                        <span className="flex items-center gap-1">
                            <Languages className="h-4 w-4" />
                            {sample.language.toUpperCase()}
                        </span>
                        {sample.has_umlauts && (
                            <Badge variant="outline">Enthaelt Umlaute</Badge>
                        )}
                        {sample.has_tables && (
                            <Badge variant="outline">Enthaelt Tabellen</Badge>
                        )}
                        {sample.has_fraktur && (
                            <Badge variant="outline">Fraktur</Badge>
                        )}
                    </DialogDescription>
                </DialogHeader>

                <ScrollArea className="max-h-[calc(90vh-120px)]">
                    <Tabs defaultValue="comparison" className="space-y-4">
                        <TabsList className="grid w-full grid-cols-3">
                            <TabsTrigger value="comparison">Backend-Vergleich</TabsTrigger>
                            <TabsTrigger value="ground-truth">Ground Truth</TabsTrigger>
                            <TabsTrigger value="details">Details</TabsTrigger>
                        </TabsList>

                        {/* Backend-Vergleich Tab */}
                        <TabsContent value="comparison" className="space-y-4">
                            {/* Ground Truth Reference */}
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                                        Ground Truth (Referenz)
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="bg-muted/50 rounded-md p-3 font-mono text-sm whitespace-pre-wrap max-h-32 overflow-y-auto">
                                        {groundTruth || (
                                            <span className="text-muted-foreground italic">
                                                Kein Ground Truth vorhanden
                                            </span>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>

                            {/* 4-Way Comparison Grid */}
                            {isLoadingBenchmarks ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    Lade Benchmark-Ergebnisse...
                                </div>
                            ) : Object.keys(benchmarksByBackend).length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    Keine Benchmark-Ergebnisse vorhanden.
                                    Starten Sie einen Benchmark fuer dieses Sample.
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {BACKEND_IDS.map((backendId) => {
                                        const benchmark = benchmarksByBackend[backendId]
                                        const config = BACKEND_CONFIG[backendId]
                                        const isBest = backendId === bestBackend

                                        return (
                                            <Card
                                                key={backendId}
                                                className={isBest ? 'ring-2 ring-green-500/30' : ''}
                                            >
                                                <CardHeader className="pb-2">
                                                    <CardTitle className="text-sm flex items-center justify-between">
                                                        <div className="flex items-center gap-2">
                                                            <div
                                                                className="w-3 h-3 rounded-full"
                                                                style={{ backgroundColor: config.color }}
                                                            />
                                                            {config.displayName}
                                                        </div>
                                                        {isBest && (
                                                            <Badge className="bg-green-600 text-xs">
                                                                Bester
                                                            </Badge>
                                                        )}
                                                    </CardTitle>
                                                </CardHeader>
                                                <CardContent className="space-y-3">
                                                    {benchmark ? (
                                                        <>
                                                            {/* Metriken */}
                                                            <div className="grid grid-cols-3 gap-2 text-xs">
                                                                <div>
                                                                    <span className="text-muted-foreground block">
                                                                        CER
                                                                    </span>
                                                                    <span
                                                                        className={`font-semibold ${
                                                                            (benchmark.cer ?? 0) < 0.05
                                                                                ? 'text-green-600'
                                                                                : (benchmark.cer ?? 0) < 0.1
                                                                                  ? 'text-yellow-600'
                                                                                  : 'text-red-600'
                                                                        }`}
                                                                    >
                                                                        {benchmark.cer !== undefined
                                                                            ? `${(benchmark.cer * 100).toFixed(2)}%`
                                                                            : '-'}
                                                                    </span>
                                                                </div>
                                                                <div>
                                                                    <span className="text-muted-foreground block">
                                                                        WER
                                                                    </span>
                                                                    <span className="font-semibold">
                                                                        {benchmark.wer !== undefined
                                                                            ? `${(benchmark.wer * 100).toFixed(2)}%`
                                                                            : '-'}
                                                                    </span>
                                                                </div>
                                                                <div>
                                                                    <span className="text-muted-foreground block">
                                                                        Umlaut
                                                                    </span>
                                                                    <span
                                                                        className={`font-semibold ${
                                                                            (benchmark.umlaut_accuracy ?? 0) >= 0.99
                                                                                ? 'text-green-600'
                                                                                : (benchmark.umlaut_accuracy ?? 0) >= 0.95
                                                                                  ? 'text-yellow-600'
                                                                                  : 'text-red-600'
                                                                        }`}
                                                                    >
                                                                        {benchmark.umlaut_accuracy !== undefined
                                                                            ? `${(benchmark.umlaut_accuracy * 100).toFixed(0)}%`
                                                                            : '-'}
                                                                    </span>
                                                                </div>
                                                            </div>

                                                            {/* Diff-Statistik */}
                                                            {benchmark.raw_text && groundTruth && (
                                                                <div className="pt-2 border-t">
                                                                    <DiffStats
                                                                        original={groundTruth}
                                                                        modified={benchmark.raw_text}
                                                                    />
                                                                </div>
                                                            )}

                                                            {/* OCR-Text Preview */}
                                                            <div className="bg-muted/30 rounded-md p-2 max-h-24 overflow-y-auto">
                                                                {benchmark.raw_text ? (
                                                                    <DiffView
                                                                        original={groundTruth}
                                                                        modified={benchmark.raw_text}
                                                                        className="text-xs"
                                                                    />
                                                                ) : (
                                                                    <span className="text-muted-foreground text-xs italic">
                                                                        Kein Text extrahiert
                                                                    </span>
                                                                )}
                                                            </div>

                                                            {/* Processing Info */}
                                                            <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                                                {benchmark.processing_time_ms !== undefined && (
                                                                    <span className="flex items-center gap-1">
                                                                        <Clock className="h-3 w-3" />
                                                                        {benchmark.processing_time_ms}ms
                                                                    </span>
                                                                )}
                                                                {benchmark.gpu_memory_mb !== undefined && (
                                                                    <span className="flex items-center gap-1">
                                                                        <Cpu className="h-3 w-3" />
                                                                        {benchmark.gpu_memory_mb}MB
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <div className="text-center py-4 text-muted-foreground text-sm">
                                                            Kein Benchmark-Ergebnis
                                                        </div>
                                                    )}
                                                </CardContent>
                                            </Card>
                                        )
                                    })}
                                </div>
                            )}

                            {/* Aktionen */}
                            <div className="flex justify-end gap-2 pt-4 border-t">
                                <Button
                                    variant="outline"
                                    disabled={correctionMutation.isPending}
                                    onClick={() => {
                                        // TODO: Korrektur-Dialog öffnen
                                        // Für jetzt: Dummy-Korrektur erstellen
                                        if (sample && bestBackend && benchmarksByBackend[bestBackend]?.raw_text) {
                                            correctionMutation.mutate({
                                                document_id: sample.id,
                                                original_text: benchmarksByBackend[bestBackend].raw_text || '',
                                                corrected_text: groundTruth,
                                                correction_type: 'manual',
                                                backend_used: bestBackend,
                                            })
                                        }
                                    }}
                                >
                                    {correctionMutation.isPending && (
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    )}
                                    Korrektur einreichen
                                </Button>
                                <Button
                                    disabled={verifyMutation.isPending || sample.status === 'verified'}
                                    onClick={() => {
                                        if (sample) {
                                            verifyMutation.mutate({
                                                id: sample.id,
                                                approved: true,
                                            })
                                        }
                                    }}
                                >
                                    {verifyMutation.isPending && (
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    )}
                                    {sample.status === 'verified' ? 'Bereits verifiziert' : 'Als verifiziert markieren'}
                                </Button>
                            </div>
                        </TabsContent>

                        {/* Ground Truth Tab */}
                        <TabsContent value="ground-truth">
                            <Card>
                                <CardHeader>
                                    <CardTitle>Ground Truth Text</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="bg-muted/50 rounded-md p-4 font-mono text-sm whitespace-pre-wrap min-h-[200px]">
                                        {groundTruth || (
                                            <span className="text-muted-foreground italic">
                                                Kein Ground Truth vorhanden. Annotieren Sie dieses Sample.
                                            </span>
                                        )}
                                    </div>

                                    {sample.umlaut_words && sample.umlaut_words.length > 0 && (
                                        <div className="mt-4">
                                            <h4 className="text-sm font-medium mb-2">
                                                Erkannte Umlaut-Woerter
                                            </h4>
                                            <div className="flex flex-wrap gap-2">
                                                {sample.umlaut_words.map((word, i) => (
                                                    <Badge key={i} variant="outline">
                                                        {word}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </TabsContent>

                        {/* Details Tab */}
                        <TabsContent value="details">
                            <div className="grid grid-cols-2 gap-4">
                                <Card>
                                    <CardHeader>
                                        <CardTitle className="text-sm">Sample-Informationen</CardTitle>
                                    </CardHeader>
                                    <CardContent className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">ID</span>
                                            <span className="font-mono">{sample.id.slice(0, 8)}...</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Datei</span>
                                            <span className="truncate max-w-[200px]">{filename}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Sprache</span>
                                            <span>{sample.language.toUpperCase()}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Typ</span>
                                            <span>{sample.document_type || '-'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Schwierigkeit</span>
                                            <span>{sample.difficulty}</span>
                                        </div>
                                    </CardContent>
                                </Card>

                                <Card>
                                    <CardHeader>
                                        <CardTitle className="text-sm">Merkmale</CardTitle>
                                    </CardHeader>
                                    <CardContent className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Umlaute</span>
                                            {sample.has_umlauts ? (
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            ) : (
                                                <XCircle className="h-4 w-4 text-muted-foreground" />
                                            )}
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Tabellen</span>
                                            {sample.has_tables ? (
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            ) : (
                                                <XCircle className="h-4 w-4 text-muted-foreground" />
                                            )}
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Fraktur</span>
                                            {sample.has_fraktur ? (
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            ) : (
                                                <XCircle className="h-4 w-4 text-muted-foreground" />
                                            )}
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Handschrift</span>
                                            {sample.has_handwriting ? (
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            ) : (
                                                <XCircle className="h-4 w-4 text-muted-foreground" />
                                            )}
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Stempel</span>
                                            {sample.has_stamps ? (
                                                <CheckCircle2 className="h-4 w-4 text-green-500" />
                                            ) : (
                                                <XCircle className="h-4 w-4 text-muted-foreground" />
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>

                                <Card className="col-span-2">
                                    <CardHeader>
                                        <CardTitle className="text-sm">Zeitstempel</CardTitle>
                                    </CardHeader>
                                    <CardContent className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Erstellt</span>
                                            <span>
                                                {new Date(sample.created_at).toLocaleString('de-DE')}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Aktualisiert</span>
                                            <span>
                                                {new Date(sample.updated_at).toLocaleString('de-DE')}
                                            </span>
                                        </div>
                                        {sample.annotated_at && (
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Annotiert</span>
                                                <span>
                                                    {new Date(sample.annotated_at).toLocaleString('de-DE')}
                                                </span>
                                            </div>
                                        )}
                                        {sample.verified_at && (
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">Verifiziert</span>
                                                <span>
                                                    {new Date(sample.verified_at).toLocaleString('de-DE')}
                                                </span>
                                            </div>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>
                        </TabsContent>
                    </Tabs>
                </ScrollArea>
            </DialogContent>
        </Dialog>
    )
}
