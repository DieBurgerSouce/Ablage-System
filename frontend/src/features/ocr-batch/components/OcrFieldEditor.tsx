/**
 * OcrFieldEditor - Side-by-side Ansicht Original vs. Korrektur
 *
 * Zeigt extrahierte Felder eines Dokuments mit Bearbeitungsmoeglichkeit.
 * Links: Original (read-only), Rechts: Korrektur (editierbar).
 * Aenderungen werden farblich hervorgehoben.
 */

import { useState, useCallback } from 'react'
import { Check, X, RotateCcw, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useDocumentExtractedFields, useSaveCorrections } from '../hooks/use-ocr-batch'
import { OcrConfidenceBadge } from './OcrConfidenceBadge'

// Feld-Labels (deutsch)
const FIELD_LABELS: Record<string, string> = {
    invoice_number: 'Rechnungsnummer',
    invoice_date: 'Rechnungsdatum',
    due_date: 'Faelligkeitsdatum',
    net_amount: 'Nettobetrag',
    vat_amount: 'MwSt-Betrag',
    gross_amount: 'Bruttobetrag',
    vat_rate: 'MwSt-Satz',
    sender_company: 'Absender Firma',
    sender_street: 'Absender Strasse',
    sender_zip_code: 'Absender PLZ',
    sender_city: 'Absender Stadt',
    recipient_company: 'Empfaenger Firma',
    recipient_street: 'Empfaenger Strasse',
    recipient_zip_code: 'Empfaenger PLZ',
    recipient_city: 'Empfaenger Stadt',
    sender_vat_id: 'USt-IdNr Absender',
    recipient_vat_id: 'USt-IdNr Empfaenger',
    sender_iban: 'IBAN',
    order_number: 'Bestellnummer',
    customer_number: 'Kundennummer',
}

// Feld-Reihenfolge fuer Anzeige
const FIELD_ORDER = [
    'invoice_number', 'invoice_date', 'due_date',
    'gross_amount', 'net_amount', 'vat_amount', 'vat_rate',
    'sender_company', 'recipient_company',
    'sender_vat_id', 'recipient_vat_id',
    'sender_iban', 'order_number', 'customer_number',
]

interface OcrFieldEditorProps {
    documentId: string
    filename: string
    onSaved: () => void
    onSkip: () => void
    onConfirmCorrect: () => void
    onClose: () => void
}

export function OcrFieldEditor({
    documentId,
    filename,
    onSaved,
    onSkip,
    onConfirmCorrect,
    onClose,
}: OcrFieldEditorProps) {
    const { data: fields, isLoading } = useDocumentExtractedFields(documentId)
    const saveMutation = useSaveCorrections()

    // Local state: corrected values keyed by field name
    const [corrections, setCorrections] = useState<Record<string, string>>({})

    const handleFieldChange = useCallback((field: string, value: string) => {
        setCorrections(prev => ({ ...prev, [field]: value }))
    }, [])

    const handleResetField = useCallback((field: string) => {
        setCorrections(prev => {
            const next = { ...prev }
            delete next[field]
            return next
        })
    }, [])

    const handleSave = useCallback(async () => {
        if (!fields) return

        const correctionEntries = Object.entries(corrections)
            .filter(([field]) => {
                const original = String(fields[field]?.value ?? '')
                return corrections[field] !== original
            })
            .map(([field, correctedValue]) => ({
                field,
                original_value: String(fields[field]?.value ?? ''),
                corrected_value: correctedValue,
                correction_type: 'GENERAL',
            }))

        if (correctionEntries.length === 0) {
            onConfirmCorrect()
            return
        }

        await saveMutation.mutateAsync({
            document_id: documentId,
            corrections: correctionEntries,
        })
        onSaved()
    }, [corrections, fields, documentId, saveMutation, onSaved, onConfirmCorrect])

    // Sort fields: show known fields first in order, then remaining
    const sortedFields = fields
        ? [
            ...FIELD_ORDER.filter(f => f in fields),
            ...Object.keys(fields).filter(f => !FIELD_ORDER.includes(f)),
        ]
        : []

    if (isLoading) {
        return (
            <Card className="border-primary/20">
                <CardContent className="flex items-center justify-center h-32">
                    <div className="flex items-center gap-3 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>Lade Felder...</span>
                    </div>
                </CardContent>
            </Card>
        )
    }

    if (!fields || sortedFields.length === 0) {
        return (
            <Card className="border-primary/20">
                <CardContent className="p-6 text-center text-muted-foreground">
                    Keine extrahierten Felder vorhanden.
                </CardContent>
            </Card>
        )
    }

    return (
        <Card className="border-primary/20">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{filename}</CardTitle>
                    <Button variant="ghost" size="sm" onClick={onClose}>
                        <X className="h-4 w-4" />
                        <span className="sr-only">Schliessen</span>
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Side-by-side header */}
                <div className="grid grid-cols-2 gap-4 text-sm font-medium text-muted-foreground">
                    <div>Original OCR</div>
                    <div>Korrektur</div>
                </div>
                <Separator />

                {/* Field rows */}
                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
                    {sortedFields.map(field => {
                        const data = fields[field]
                        if (!data) return null

                        const originalValue = String(data.value ?? '')
                        const correctedValue = corrections[field] ?? originalValue
                        const isModified = field in corrections && corrections[field] !== originalValue
                        const label = FIELD_LABELS[field] || field

                        return (
                            <div key={field} className="grid grid-cols-2 gap-4 items-start">
                                {/* Original (read-only) */}
                                <div className="space-y-1">
                                    <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                                        {label}
                                        <OcrConfidenceBadge
                                            confidence={data.confidence}
                                            className="text-[10px] px-1.5 py-0"
                                        />
                                    </label>
                                    <div className={cn(
                                        'text-sm rounded border px-2 py-1.5 bg-muted/50 min-h-[34px]',
                                        isModified && 'line-through text-muted-foreground'
                                    )}>
                                        {originalValue || <span className="text-muted-foreground italic">-</span>}
                                    </div>
                                </div>

                                {/* Corrected (editable) */}
                                <div className="space-y-1">
                                    <label className="text-xs font-medium text-muted-foreground">
                                        {label}
                                    </label>
                                    <div className="flex items-center gap-1">
                                        <Input
                                            value={correctedValue}
                                            onChange={(e) => handleFieldChange(field, e.target.value)}
                                            className={cn(
                                                'h-[34px] text-sm',
                                                isModified && 'border-blue-400 dark:border-blue-600'
                                            )}
                                        />
                                        {isModified && (
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-[34px] w-[34px] shrink-0"
                                                onClick={() => handleResetField(field)}
                                                title="Zuruecksetzen"
                                            >
                                                <RotateCcw className="h-3.5 w-3.5" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>

                <Separator />

                {/* Action buttons */}
                <div className="flex items-center justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={onSkip}>
                        Ueberspringen
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={onConfirmCorrect}
                    >
                        <Check className="h-4 w-4 mr-1" />
                        Als korrekt markieren
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleSave}
                        disabled={saveMutation.isPending}
                    >
                        {saveMutation.isPending ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                Speichere...
                            </>
                        ) : (
                            'Korrektur speichern'
                        )}
                    </Button>
                </div>
            </CardContent>
        </Card>
    )
}
