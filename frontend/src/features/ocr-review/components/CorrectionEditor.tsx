/**
 * Correction Editor Komponente
 * Text-Editor mit Diff-Highlighting und Umlaut-Korrektur
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
    Wand2,
    AlertTriangle,
    Check,
    Hash,
    Calendar,
    Euro,
    CreditCard,
    FileText,
    Sparkles,
} from 'lucide-react'
import type { CorrectionType } from '../types'

// Umlaut-Korrektur-Logik (aus GroundTruthEditor übernommen)
const KNOWN_UMLAUT_WORDS: Record<string, string> = {
    'für': 'für',
    'ueber': 'über',
    'können': 'können',
    'möchten': 'möchten',
    'waehrend': 'während',
    'naechste': 'nächste',
    'ändern': 'ändern',
    'öffnen': 'öffnen',
    'groesse': 'Größe',
    'strasse': 'Straße',
    'schliessen': 'schließen',
    'gebuehr': 'Gebühr',
    'prüfung': 'Prüfung',
    'löschen': 'löschen',
    'bestaetigen': 'bestätigen',
    'verfuegbar': 'verfügbar',
    'zurück': 'zurück',
    'aehnlich': 'ähnlich',
    'muenchen': 'München',
    'nuernberg': 'Nürnberg',
    'koeln': 'Köln',
    'duesseldorf': 'Düsseldorf',
    'wuerzburg': 'Würzburg',
}

interface UmlautIssue {
    original: string
    suggested: string
    position: number
}

function detectUmlautIssues(text: string): UmlautIssue[] {
    const issues: UmlautIssue[] = []
    Object.entries(KNOWN_UMLAUT_WORDS).forEach(([wrong, correct]) => {
        const regex = new RegExp(`\\b${wrong}\\b`, 'gi')
        const matches = text.matchAll(regex)
        for (const match of matches) {
            issues.push({
                original: match[0],
                suggested: correct,
                position: match.index ?? 0,
            })
        }
    })
    return issues
}

function autoCorrectUmlauts(text: string): string {
    let corrected = text
    Object.entries(KNOWN_UMLAUT_WORDS).forEach(([wrong, correct]) => {
        const regex = new RegExp(`\\b${wrong}\\b`, 'gi')
        corrected = corrected.replace(regex, correct)
    })
    return corrected
}

// Feld-Extraktion
interface ExtractedFields {
    invoice_number?: string
    date?: string
    amount?: string
    iban?: string
    vat_id?: string
}

function extractFields(text: string): ExtractedFields {
    const fields: ExtractedFields = {}
    const invoiceMatch = text.match(/(?:Rechnungs?-?(?:nummer|nr\.?)?|Invoice(?:\s+No\.?)?|RE-?(?:Nr\.?)?)[:\s]*([A-Z0-9\-/]+)/i)
    if (invoiceMatch) fields.invoice_number = invoiceMatch[1].trim()
    const dateMatch = text.match(/(?:Datum|Date|vom)[:\s]*(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})/i)
    if (dateMatch) fields.date = dateMatch[1].trim()
    const amountMatch = text.match(/(?:Gesamt|Total|Betrag|Summe|Endbetrag)[:\s]*€?\s*([\d.,]+)\s*€?/i)
    if (amountMatch) fields.amount = amountMatch[1].replace(/\./g, '').replace(',', '.').trim()
    const ibanMatch = text.match(/(?:IBAN)[:\s]*([A-Z]{2}\s*\d{2}\s*(?:\d{4}\s*){4,}\d{0,4})/i)
    if (ibanMatch) fields.iban = ibanMatch[1].replace(/\s+/g, '').trim()
    const vatMatch = text.match(/(?:USt\.?-?(?:IdNr\.?|ID)|VAT\s*ID)[:\s]*([A-Z]{2}\d{9,})/i)
    if (vatMatch) fields.vat_id = vatMatch[1].trim()
    return fields
}

// Korrekturtyp erkennen
function detectCorrectionType(original: string, corrected: string): CorrectionType {
    const originalLower = original.toLowerCase()
    const correctedLower = corrected.toLowerCase()

    // Umlaut-Änderungen
    const umlautPatterns = [
        /ae/g, /oe/g, /ue/g, /ss/g,
        /ä/g, /ö/g, /ü/g, /ß/g,
    ]
    for (const pattern of umlautPatterns) {
        const origCount = (originalLower.match(pattern) || []).length
        const corrCount = (correctedLower.match(pattern) || []).length
        if (origCount !== corrCount) return 'UMLAUT'
    }

    // Datum-Änderungen
    const datePattern = /\d{1,2}[./-]\d{1,2}[./-]\d{2,4}/
    if (datePattern.test(original) || datePattern.test(corrected)) {
        const origDates = original.match(datePattern)
        const corrDates = corrected.match(datePattern)
        if (JSON.stringify(origDates) !== JSON.stringify(corrDates)) return 'DATE'
    }

    // Betrags-Änderungen
    const amountPattern = /\d+[,.]\d{2}/
    if (amountPattern.test(original) || amountPattern.test(corrected)) {
        const origAmounts = original.match(amountPattern)
        const corrAmounts = corrected.match(amountPattern)
        if (JSON.stringify(origAmounts) !== JSON.stringify(corrAmounts)) return 'AMOUNT'
    }

    // IBAN-Änderungen
    if (/[A-Z]{2}\d{2}/.test(original) || /[A-Z]{2}\d{2}/.test(corrected)) {
        return 'IBAN'
    }

    return 'GENERAL'
}

interface CorrectionEditorProps {
    originalText: string
    initialText?: string
    llmSuggestion?: string
    onTextChange: (text: string, correctionType: CorrectionType, isDirty: boolean) => void
    onFieldsChange?: (fields: ExtractedFields) => void
    disabled?: boolean
}

export function CorrectionEditor({
    originalText,
    initialText,
    llmSuggestion,
    onTextChange,
    onFieldsChange,
    disabled = false,
}: CorrectionEditorProps) {
    const [text, setText] = useState(initialText || originalText)
    const [fields, setFields] = useState<ExtractedFields>({})

    // Umlaut-Probleme erkennen
    const umlautIssues = useMemo(() => detectUmlautIssues(text), [text])
    const hasUmlautIssues = umlautIssues.length > 0

    // Änderungen erkennen
    const isDirty = text !== originalText
    const correctionType = useMemo(
        () => (isDirty ? detectCorrectionType(originalText, text) : 'GENERAL'),
        [originalText, text, isDirty]
    )

    // Callback bei Änderungen
    useEffect(() => {
        onTextChange(text, correctionType, isDirty)
    }, [text, correctionType, isDirty, onTextChange])

    const handleTextChange = useCallback((value: string) => {
        setText(value)
    }, [])

    const handleAutoCorrectUmlauts = useCallback(() => {
        const corrected = autoCorrectUmlauts(text)
        setText(corrected)
    }, [text])

    const handleApplyLLMSuggestion = useCallback(() => {
        if (llmSuggestion) {
            setText(llmSuggestion)
        }
    }, [llmSuggestion])

    const handleExtractFields = useCallback(() => {
        const extracted = extractFields(text)
        setFields(extracted)
        onFieldsChange?.(extracted)
    }, [text, onFieldsChange])

    const handleFieldChange = useCallback((field: keyof ExtractedFields, value: string) => {
        const updated = { ...fields, [field]: value }
        setFields(updated)
        onFieldsChange?.(updated)
    }, [fields, onFieldsChange])

    return (
        <div className="space-y-4">
            {/* Umlaut-Warnung */}
            {hasUmlautIssues && (
                <Alert variant="destructive" className="py-2">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span>Mögliche Umlaut-Fehler:</span>
                            {umlautIssues.slice(0, 3).map((issue, i) => (
                                <Badge key={i} variant="outline" className="font-mono text-xs">
                                    {issue.original} → {issue.suggested}
                                </Badge>
                            ))}
                            {umlautIssues.length > 3 && (
                                <Badge variant="secondary" className="text-xs">
                                    +{umlautIssues.length - 3}
                                </Badge>
                            )}
                        </div>
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handleAutoCorrectUmlauts}
                            disabled={disabled}
                        >
                            <Wand2 className="h-3 w-3 mr-1" />
                            Korrigieren
                        </Button>
                    </AlertDescription>
                </Alert>
            )}

            {/* Text-Editor */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center justify-between">
                        <span className="flex items-center gap-2">
                            <FileText className="h-4 w-4" />
                            OCR Text bearbeiten
                        </span>
                        <div className="flex items-center gap-2">
                            {isDirty && (
                                <Badge variant="outline" className="text-yellow-600">
                                    Geändert ({correctionType})
                                </Badge>
                            )}
                            {!hasUmlautIssues && text && (
                                <Badge className="bg-green-600">
                                    <Check className="h-3 w-3 mr-1" />
                                    Umlaute OK
                                </Badge>
                            )}
                        </div>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <Textarea
                        value={text}
                        onChange={(e) => handleTextChange(e.target.value)}
                        placeholder="OCR Text..."
                        className="min-h-[200px] font-mono text-sm"
                        disabled={disabled}
                    />

                    <div className="flex items-center justify-between">
                        <div className="flex gap-2">
                            {llmSuggestion && llmSuggestion !== text && (
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={handleApplyLLMSuggestion}
                                    disabled={disabled}
                                >
                                    <Sparkles className="h-3 w-3 mr-1" />
                                    LLM-Vorschlag
                                </Button>
                            )}
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={handleExtractFields}
                                disabled={disabled}
                            >
                                <Hash className="h-3 w-3 mr-1" />
                                Felder extrahieren
                            </Button>
                        </div>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setText(originalText)}
                            disabled={disabled || !isDirty}
                        >
                            Zurücksetzen
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Extrahierte Felder */}
            {Object.keys(fields).length > 0 && (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm flex items-center gap-2">
                            <Hash className="h-4 w-4" />
                            Extrahierte Felder
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-3">
                            {fields.invoice_number && (
                                <div className="space-y-1">
                                    <Label className="text-xs flex items-center gap-1">
                                        <Hash className="h-3 w-3" />
                                        Rechnungsnr.
                                    </Label>
                                    <Input
                                        value={fields.invoice_number}
                                        onChange={(e) => handleFieldChange('invoice_number', e.target.value)}
                                        className="h-8 text-sm"
                                        disabled={disabled}
                                    />
                                </div>
                            )}
                            {fields.date && (
                                <div className="space-y-1">
                                    <Label className="text-xs flex items-center gap-1">
                                        <Calendar className="h-3 w-3" />
                                        Datum
                                    </Label>
                                    <Input
                                        value={fields.date}
                                        onChange={(e) => handleFieldChange('date', e.target.value)}
                                        className="h-8 text-sm"
                                        disabled={disabled}
                                    />
                                </div>
                            )}
                            {fields.amount && (
                                <div className="space-y-1">
                                    <Label className="text-xs flex items-center gap-1">
                                        <Euro className="h-3 w-3" />
                                        Betrag
                                    </Label>
                                    <Input
                                        value={fields.amount}
                                        onChange={(e) => handleFieldChange('amount', e.target.value)}
                                        className="h-8 text-sm"
                                        disabled={disabled}
                                    />
                                </div>
                            )}
                            {fields.iban && (
                                <div className="space-y-1">
                                    <Label className="text-xs flex items-center gap-1">
                                        <CreditCard className="h-3 w-3" />
                                        IBAN
                                    </Label>
                                    <Input
                                        value={fields.iban}
                                        onChange={(e) => handleFieldChange('iban', e.target.value)}
                                        className="h-8 text-sm"
                                        disabled={disabled}
                                    />
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    )
}
