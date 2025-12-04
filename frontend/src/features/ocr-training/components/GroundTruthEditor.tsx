/**
 * Ground Truth Editor Komponente
 *
 * Enterprise-grade Editor fuer Ground Truth Annotation mit:
 * - 4-Way Side-by-Side Backend-Vergleich
 * - Editierbarer Ground Truth mit Diff-Highlighting
 * - Umlaut-Validierung und automatische Korrektur
 * - Strukturierte Feld-Extraktion (Rechnungsnummer, Datum, Betrag, IBAN)
 */

import { useState, useMemo, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
    CheckCircle2,
    AlertTriangle,
    Copy,
    Save,
    Wand2,
    FileText,
    Hash,
    Calendar,
    Euro,
    CreditCard,
    RotateCcw,
    Eye,
    EyeOff,
    Sparkles,
    Check,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TrainingSample, BenchmarkResult } from '@/lib/api/services/training'
import { DiffView } from './DiffView'
import { BACKEND_CONFIG, BACKEND_IDS, type BackendId } from '../constants/backend-config'

// Types
interface ExtractedFields {
    invoice_number?: string
    date?: string
    amount?: string
    iban?: string
    vat_id?: string
    customer_name?: string
}

interface UmlautSuggestion {
    original: string
    suggested: string
    position: number
    context: string
}

interface GroundTruthEditorProps {
    sample: TrainingSample
    benchmarks: Record<string, BenchmarkResult>
    onSave: (groundTruth: string, fields: ExtractedFields) => Promise<void>
    onSelectBackend: (backendId: string) => void
    isSaving?: boolean
}

// Umlaut Validation
const KNOWN_UMLAUT_WORDS: Record<string, string> = {
    'fuer': 'fuer',
    'ueber': 'ueber',
    'koennen': 'koennen',
    'moechten': 'moechten',
    'waehrend': 'waehrend',
    'naechste': 'naechste',
    'aendern': 'aendern',
    'oeffnen': 'oeffnen',
    'groesse': 'Groesse',
    'strasse': 'Strasse',
    'schliessen': 'schliessen',
    'gebuehr': 'Gebuehr',
    'pruefung': 'Pruefung',
    'loeschen': 'loeschen',
    'bestaetigen': 'bestaetigen',
    'verfuegbar': 'verfuegbar',
    'zurueck': 'zurueck',
    'aehnlich': 'aehnlich',
}

function detectUmlautIssues(text: string): UmlautSuggestion[] {
    const suggestions: UmlautSuggestion[] = []
    Object.entries(KNOWN_UMLAUT_WORDS).forEach(([wrongSpelling, correctSpelling]) => {
        const regex = new RegExp(`\\b${wrongSpelling}\\b`, 'gi')
        let match
        while ((match = regex.exec(text)) !== null) {
            const context = text.slice(Math.max(0, match.index - 20), match.index + wrongSpelling.length + 20)
            suggestions.push({
                original: match[0],
                suggested: correctSpelling,
                position: match.index,
                context,
            })
        }
    })
    return suggestions
}

function autoCorrectUmlauts(text: string): string {
    let corrected = text
    const corrections: [RegExp, string][] = [
        [/\bfuer\b/gi, 'fuer'],
        [/\bueber\b/gi, 'ueber'],
        [/\bkoennen\b/gi, 'koennen'],
        [/\bmoechten\b/gi, 'moechten'],
        [/\bwaehrend\b/gi, 'waehrend'],
        [/\bnaechste\b/gi, 'naechste'],
        [/\baendern\b/gi, 'aendern'],
        [/\boeffnen\b/gi, 'oeffnen'],
        [/\bgroesse\b/gi, 'Groesse'],
        [/\bstrasse\b/gi, 'Strasse'],
        [/\bschliessen\b/gi, 'schliessen'],
        [/\bgebuehr\b/gi, 'Gebuehr'],
        [/\bpruefung\b/gi, 'Pruefung'],
        [/\bloeschen\b/gi, 'loeschen'],
        [/\bbestaetigen\b/gi, 'bestaetigen'],
        [/\bverfuegbar\b/gi, 'verfuegbar'],
        [/\bzurueck\b/gi, 'zurueck'],
        [/\baehnlich\b/gi, 'aehnlich'],
    ]
    for (const [pattern, replacement] of corrections) {
        corrected = corrected.replace(pattern, replacement)
    }
    return corrected
}

// Field Extraction
function extractFields(text: string): ExtractedFields {
    const fields: ExtractedFields = {}
    const invoiceMatch = text.match(/(?:Rechnungs?-?(?:nummer|nr\.?)?|Invoice(?:\s+No\.?)?|RE-?(?:Nr\.?)?)[:\s]*([A-Z0-9\-\/]+)/i)
    if (invoiceMatch) fields.invoice_number = invoiceMatch[1].trim()
    const dateMatch = text.match(/(?:Datum|Date|vom)[:\s]*(\d{1,2}[\.\/]\d{1,2}[\.\/]\d{2,4}|\d{4}-\d{2}-\d{2})/i)
    if (dateMatch) fields.date = dateMatch[1].trim()
    const amountMatch = text.match(/(?:Gesamt|Total|Betrag|Summe|Endbetrag)[:\s]*€?\s*([\d\.,]+)\s*€?/i)
    if (amountMatch) fields.amount = amountMatch[1].replace(/\./g, '').replace(',', '.').trim()
    const ibanMatch = text.match(/(?:IBAN)[:\s]*([A-Z]{2}\s*\d{2}\s*(?:\d{4}\s*){4,}\d{0,4})/i)
    if (ibanMatch) fields.iban = ibanMatch[1].replace(/\s+/g, '').trim()
    const vatMatch = text.match(/(?:USt\.?-?(?:IdNr\.?|ID)|VAT\s*ID)[:\s]*([A-Z]{2}\d{9,})/i)
    if (vatMatch) fields.vat_id = vatMatch[1].trim()
    return fields
}

// Component
export function GroundTruthEditor({
    sample,
    benchmarks,
    onSave,
    onSelectBackend,
    isSaving = false,
}: GroundTruthEditorProps) {
    const [groundTruth, setGroundTruth] = useState(sample.ground_truth_text || '')
    const [extractedFields, setExtractedFields] = useState<ExtractedFields>(
        sample.extracted_fields as ExtractedFields || {}
    )
    const [selectedBackend, setSelectedBackend] = useState<BackendId | null>(null)
    const [showDiff, setShowDiff] = useState(true)
    const [isDirty, setIsDirty] = useState(false)

    const umlautIssues = useMemo(() => detectUmlautIssues(groundTruth), [groundTruth])
    const hasUmlautIssues = umlautIssues.length > 0

    const bestBackend = useMemo(() => {
        let best: string | null = null
        let bestCER = Infinity
        Object.entries(benchmarks).forEach(([name, b]) => {
            if (b.cer !== undefined && b.cer < bestCER) {
                bestCER = b.cer
                best = name
            }
        })
        return best
    }, [benchmarks])

    const handleGroundTruthChange = useCallback((value: string) => {
        setGroundTruth(value)
        setIsDirty(true)
    }, [])

    const handleCopyFromBackend = useCallback((backendId: string) => {
        const benchmark = benchmarks[backendId]
        if (benchmark?.raw_text) {
            setGroundTruth(benchmark.raw_text)
            setIsDirty(true)
            const fields = extractFields(benchmark.raw_text)
            setExtractedFields(prev => ({ ...prev, ...fields }))
        }
        setSelectedBackend(backendId as BackendId)
        onSelectBackend(backendId)
    }, [benchmarks, onSelectBackend])

    const handleAutoCorrectUmlauts = useCallback(() => {
        const corrected = autoCorrectUmlauts(groundTruth)
        setGroundTruth(corrected)
        setIsDirty(true)
    }, [groundTruth])

    const handleExtractFields = useCallback(() => {
        const fields = extractFields(groundTruth)
        setExtractedFields(prev => ({ ...prev, ...fields }))
        setIsDirty(true)
    }, [groundTruth])

    const handleFieldChange = useCallback((field: keyof ExtractedFields, value: string) => {
        setExtractedFields(prev => ({ ...prev, [field]: value }))
        setIsDirty(true)
    }, [])

    const handleSave = useCallback(async () => {
        await onSave(groundTruth, extractedFields)
        setIsDirty(false)
    }, [groundTruth, extractedFields, onSave])

    const handleReset = useCallback(() => {
        setGroundTruth(sample.ground_truth_text || '')
        setExtractedFields(sample.extracted_fields as ExtractedFields || {})
        setIsDirty(false)
    }, [sample])

    return (
        <div className="space-y-6">
            {hasUmlautIssues && (
                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Moegliche Umlaut-Fehler erkannt</AlertTitle>
                    <AlertDescription className="mt-2">
                        <div className="flex flex-wrap gap-2 mb-2">
                            {umlautIssues.slice(0, 5).map((issue, i) => (
                                <Badge key={i} variant="outline" className="font-mono">
                                    {issue.original} -&gt; {issue.suggested}
                                </Badge>
                            ))}
                            {umlautIssues.length > 5 && (
                                <Badge variant="secondary">+{umlautIssues.length - 5} weitere</Badge>
                            )}
                        </div>
                        <Button size="sm" variant="outline" onClick={handleAutoCorrectUmlauts} className="mt-1">
                            <Wand2 className="mr-2 h-3 w-3" />
                            Automatisch korrigieren
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                        <span className="flex items-center gap-2">
                            <FileText className="h-5 w-5" />
                            Backend-Vergleich
                        </span>
                        <Button variant="ghost" size="sm" onClick={() => setShowDiff(!showDiff)}>
                            {showDiff ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                            <span className="ml-1">Diff</span>
                        </Button>
                    </CardTitle>
                    <CardDescription>Waehlen Sie das beste Backend-Ergebnis als Ausgangspunkt</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {BACKEND_IDS.map((backendId) => {
                            const benchmark = benchmarks[backendId]
                            const config = BACKEND_CONFIG[backendId]
                            const isBest = backendId === bestBackend
                            const isSelected = backendId === selectedBackend

                            return (
                                <Card
                                    key={backendId}
                                    className={cn(
                                        'cursor-pointer transition-all',
                                        isBest && 'ring-2 ring-green-500/30',
                                        isSelected && 'ring-2 ring-blue-500',
                                    )}
                                    onClick={() => handleCopyFromBackend(backendId)}
                                >
                                    <CardHeader className="pb-2">
                                        <CardTitle className="text-sm flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: config.color }} />
                                                {config.displayName}
                                            </div>
                                            <div className="flex items-center gap-1">
                                                {isBest && <Badge className="bg-green-600 text-xs">Bester</Badge>}
                                                {isSelected && <Badge variant="secondary" className="text-xs">Ausgewaehlt</Badge>}
                                            </div>
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        {benchmark?.raw_text ? (
                                            <>
                                                <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                                                    <div>
                                                        <span className="text-muted-foreground">CER</span>
                                                        <span className={cn('ml-1 font-semibold', (benchmark.cer ?? 0) < 0.05 ? 'text-green-600' : (benchmark.cer ?? 0) < 0.1 ? 'text-yellow-600' : 'text-red-600')}>
                                                            {benchmark.cer !== undefined ? `${(benchmark.cer * 100).toFixed(1)}%` : '-'}
                                                        </span>
                                                    </div>
                                                    <div>
                                                        <span className="text-muted-foreground">WER</span>
                                                        <span className="ml-1 font-semibold">{benchmark.wer !== undefined ? `${(benchmark.wer * 100).toFixed(1)}%` : '-'}</span>
                                                    </div>
                                                    <div>
                                                        <span className="text-muted-foreground">Umlaut</span>
                                                        <span className={cn('ml-1 font-semibold', (benchmark.umlaut_accuracy ?? 0) >= 0.99 ? 'text-green-600' : (benchmark.umlaut_accuracy ?? 0) >= 0.95 ? 'text-yellow-600' : 'text-red-600')}>
                                                            {benchmark.umlaut_accuracy !== undefined ? `${(benchmark.umlaut_accuracy * 100).toFixed(0)}%` : '-'}
                                                        </span>
                                                    </div>
                                                </div>
                                                <ScrollArea className="h-24">
                                                    <div className="text-xs font-mono">
                                                        {showDiff && groundTruth ? (
                                                            <DiffView original={groundTruth} modified={benchmark.raw_text} className="text-xs" />
                                                        ) : (
                                                            <pre className="whitespace-pre-wrap">{benchmark.raw_text.slice(0, 300)}{benchmark.raw_text.length > 300 && '...'}</pre>
                                                        )}
                                                    </div>
                                                </ScrollArea>
                                                <Button variant="ghost" size="sm" className="w-full mt-2" onClick={(e) => { e.stopPropagation(); handleCopyFromBackend(backendId) }}>
                                                    <Copy className="mr-2 h-3 w-3" />
                                                    Als Ground Truth uebernehmen
                                                </Button>
                                            </>
                                        ) : (
                                            <div className="text-center py-8 text-muted-foreground text-sm">Kein Benchmark-Ergebnis</div>
                                        )}
                                    </CardContent>
                                </Card>
                            )
                        })}
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                        <span className="flex items-center gap-2">
                            <CheckCircle2 className="h-5 w-5 text-green-500" />
                            Ground Truth Editor
                        </span>
                        <div className="flex items-center gap-2">
                            {isDirty && <Badge variant="outline" className="text-yellow-600">Ungespeichert</Badge>}
                            {!hasUmlautIssues && groundTruth && <Badge className="bg-green-600"><Check className="h-3 w-3 mr-1" />Umlaute OK</Badge>}
                        </div>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <Textarea value={groundTruth} onChange={(e) => handleGroundTruthChange(e.target.value)} placeholder="Ground Truth Text hier eingeben oder aus einem Backend uebernehmen..." className="min-h-[200px] font-mono text-sm" />
                    <div className="flex justify-between">
                        <div className="flex gap-2">
                            <Button variant="outline" size="sm" onClick={handleAutoCorrectUmlauts} disabled={!hasUmlautIssues}>
                                <Wand2 className="mr-2 h-4 w-4" />Umlaute korrigieren
                            </Button>
                            <Button variant="outline" size="sm" onClick={handleExtractFields}>
                                <Sparkles className="mr-2 h-4 w-4" />Felder extrahieren
                            </Button>
                        </div>
                        <div className="flex gap-2">
                            <Button variant="ghost" size="sm" onClick={handleReset} disabled={!isDirty}>
                                <RotateCcw className="mr-2 h-4 w-4" />Zuruecksetzen
                            </Button>
                            <Button size="sm" onClick={handleSave} disabled={isSaving || !isDirty}>
                                <Save className="mr-2 h-4 w-4" />{isSaving ? 'Speichert...' : 'Speichern'}
                            </Button>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2"><Hash className="h-5 w-5" />Extrahierte Felder</CardTitle>
                    <CardDescription>Strukturierte Daten aus dem Dokument</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="invoice_number" className="flex items-center gap-2"><Hash className="h-4 w-4" />Rechnungsnummer</Label>
                            <Input id="invoice_number" value={extractedFields.invoice_number || ''} onChange={(e) => handleFieldChange('invoice_number', e.target.value)} placeholder="z.B. RE-2024-001234" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="date" className="flex items-center gap-2"><Calendar className="h-4 w-4" />Datum</Label>
                            <Input id="date" value={extractedFields.date || ''} onChange={(e) => handleFieldChange('date', e.target.value)} placeholder="z.B. 15.12.2024" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="amount" className="flex items-center gap-2"><Euro className="h-4 w-4" />Betrag</Label>
                            <Input id="amount" value={extractedFields.amount || ''} onChange={(e) => handleFieldChange('amount', e.target.value)} placeholder="z.B. 1234.56" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="iban" className="flex items-center gap-2"><CreditCard className="h-4 w-4" />IBAN</Label>
                            <Input id="iban" value={extractedFields.iban || ''} onChange={(e) => handleFieldChange('iban', e.target.value)} placeholder="z.B. DE89370400440532013000" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="vat_id" className="flex items-center gap-2"><FileText className="h-4 w-4" />USt-IdNr.</Label>
                            <Input id="vat_id" value={extractedFields.vat_id || ''} onChange={(e) => handleFieldChange('vat_id', e.target.value)} placeholder="z.B. DE123456789" />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="customer_name" className="flex items-center gap-2"><FileText className="h-4 w-4" />Kundenname</Label>
                            <Input id="customer_name" value={extractedFields.customer_name || ''} onChange={(e) => handleFieldChange('customer_name', e.target.value)} placeholder="z.B. Max Mustermann GmbH" />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
