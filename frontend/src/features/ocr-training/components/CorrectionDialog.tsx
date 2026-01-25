/**
 * CorrectionDialog
 *
 * Dialog für OCR-Korrektur mit Text-Vergleich und Korrektur-Eingabe.
 * Ermöglicht das Einreichen von Korrekturen für das Self-Learning System.
 */

import { useState, useCallback, useMemo } from 'react'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Edit3,
    Eye,
    FileText,
    AlertCircle,
    Loader2,
} from 'lucide-react'
import { DiffView, DiffStats } from './DiffView'
import { cn } from '@/lib/utils'

export interface CorrectionDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    originalText: string
    groundTruthText?: string
    backendName: string
    documentId: string
    documentName: string
    onSubmit: (data: CorrectionSubmitData) => Promise<void>
    isSubmitting?: boolean
}

export interface CorrectionSubmitData {
    document_id: string
    original_text: string
    corrected_text: string
    correction_type: string
    backend_used: string
    notes?: string
}

const CORRECTION_TYPES = [
    { value: 'umlaut', label: 'Umlaut-Fehler', description: 'ä, ö, ü, ß Fehler' },
    { value: 'date', label: 'Datumsfehler', description: 'Falsch erkanntes Datum' },
    { value: 'amount', label: 'Betragsfehler', description: 'Zahlen/Währung falsch' },
    { value: 'name', label: 'Namensfehler', description: 'Namen falsch erkannt' },
    { value: 'iban', label: 'IBAN-Fehler', description: 'IBAN/Bankdaten falsch' },
    { value: 'general', label: 'Allgemein', description: 'Sonstige Fehler' },
] as const

export function CorrectionDialog({
    open,
    onOpenChange,
    originalText,
    groundTruthText,
    backendName,
    documentId,
    documentName,
    onSubmit,
    isSubmitting = false,
}: CorrectionDialogProps) {
    // Korrigierter Text - initialisiert mit Ground Truth oder Original
    const [correctedText, setCorrectedText] = useState(groundTruthText || originalText)
    const [correctionType, setCorrectionType] = useState<string>('general')
    const [notes, setNotes] = useState('')
    const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit')

    // Reset state when dialog opens
    const handleOpenChange = useCallback((newOpen: boolean) => {
        if (newOpen) {
            setCorrectedText(groundTruthText || originalText)
            setCorrectionType('general')
            setNotes('')
            setActiveTab('edit')
        }
        onOpenChange(newOpen)
    }, [groundTruthText, originalText, onOpenChange])

    // Check if there are actual changes
    const hasChanges = useMemo(() => {
        return correctedText.trim() !== originalText.trim()
    }, [correctedText, originalText])

    // Auto-detect correction type based on changes
    const detectedType = useMemo(() => {
        if (!hasChanges) return null

        // Check for umlaut changes
        const umlautPattern = /[äöüÄÖÜß]|ae|oe|ue|ss/g
        const origUmlauts = originalText.match(umlautPattern) || []
        const corrUmlauts = correctedText.match(umlautPattern) || []
        if (origUmlauts.length !== corrUmlauts.length ||
            origUmlauts.some((u, i) => u !== corrUmlauts[i])) {
            return 'umlaut'
        }

        // Check for date changes
        const datePattern = /\d{1,2}[./-]\d{1,2}[./-]\d{2,4}/g
        const origDates = originalText.match(datePattern) || []
        const corrDates = correctedText.match(datePattern) || []
        if (origDates.length !== corrDates.length ||
            origDates.some((d, i) => d !== corrDates[i])) {
            return 'date'
        }

        // Check for amount/number changes
        const amountPattern = /\d+[.,]\d{2}\s*(€|EUR)?/g
        const origAmounts = originalText.match(amountPattern) || []
        const corrAmounts = correctedText.match(amountPattern) || []
        if (origAmounts.length !== corrAmounts.length ||
            origAmounts.some((a, i) => a !== corrAmounts[i])) {
            return 'amount'
        }

        // Check for IBAN changes
        const ibanPattern = /[A-Z]{2}\d{2}[A-Z0-9]{4,}/g
        const origIbans = originalText.match(ibanPattern) || []
        const corrIbans = correctedText.match(ibanPattern) || []
        if (origIbans.length !== corrIbans.length ||
            origIbans.some((iban, i) => iban !== corrIbans[i])) {
            return 'iban'
        }

        return 'general'
    }, [originalText, correctedText, hasChanges])

    // Handle submit
    const handleSubmit = useCallback(async () => {
        if (!hasChanges) return

        await onSubmit({
            document_id: documentId,
            original_text: originalText,
            corrected_text: correctedText.trim(),
            correction_type: correctionType,
            backend_used: backendName,
            notes: notes.trim() || undefined,
        })

        handleOpenChange(false)
    }, [
        hasChanges,
        documentId,
        originalText,
        correctedText,
        correctionType,
        backendName,
        notes,
        onSubmit,
        handleOpenChange,
    ])

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="max-w-4xl max-h-[90vh]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Edit3 className="h-5 w-5" />
                        OCR-Korrektur einreichen
                    </DialogTitle>
                    <DialogDescription className="flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        {documentName}
                        <Badge variant="outline" className="ml-2">
                            {backendName}
                        </Badge>
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    {/* Tabs für Edit/Preview */}
                    <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'edit' | 'preview')}>
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="edit" className="gap-2">
                                <Edit3 className="h-4 w-4" />
                                Bearbeiten
                            </TabsTrigger>
                            <TabsTrigger value="preview" className="gap-2">
                                <Eye className="h-4 w-4" />
                                Vergleich
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="edit" className="space-y-4">
                            {/* Original Text (readonly) */}
                            <div className="space-y-2">
                                <Label className="flex items-center gap-2">
                                    OCR-Ergebnis
                                    <Badge variant="secondary" className="text-xs">
                                        Original
                                    </Badge>
                                </Label>
                                <ScrollArea className="h-40 rounded-md border bg-muted/50">
                                    <div className="p-4 font-mono text-sm whitespace-pre-wrap">
                                        {originalText || (
                                            <span className="text-muted-foreground italic">
                                                Kein OCR-Text vorhanden
                                            </span>
                                        )}
                                    </div>
                                </ScrollArea>
                            </div>

                            {/* Corrected Text (editable) */}
                            <div className="space-y-2">
                                <Label htmlFor="corrected-text" className="flex items-center gap-2">
                                    Korrigierter Text
                                    {hasChanges && (
                                        <Badge variant="default" className="text-xs bg-green-600">
                                            Geändert
                                        </Badge>
                                    )}
                                </Label>
                                <Textarea
                                    id="corrected-text"
                                    value={correctedText}
                                    onChange={(e) => setCorrectedText(e.target.value)}
                                    className="font-mono text-sm min-h-[160px]"
                                    placeholder="Korrigierten Text hier eingeben..."
                                />
                            </div>
                        </TabsContent>

                        <TabsContent value="preview" className="space-y-4">
                            {/* Diff View */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label>Änderungsvergleich</Label>
                                    <DiffStats original={originalText} modified={correctedText} />
                                </div>
                                <ScrollArea className="h-64 rounded-md border">
                                    <div className="p-4">
                                        {hasChanges ? (
                                            <DiffView
                                                original={originalText}
                                                modified={correctedText}
                                            />
                                        ) : (
                                            <div className="text-center py-8 text-muted-foreground">
                                                <AlertCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                                Keine Änderungen vorgenommen
                                            </div>
                                        )}
                                    </div>
                                </ScrollArea>
                            </div>
                        </TabsContent>
                    </Tabs>

                    {/* Correction Type Selection */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="correction-type">Korrektur-Typ</Label>
                            <Select
                                value={correctionType}
                                onValueChange={setCorrectionType}
                            >
                                <SelectTrigger id="correction-type">
                                    <SelectValue placeholder="Typ auswählen..." />
                                </SelectTrigger>
                                <SelectContent>
                                    {CORRECTION_TYPES.map((type) => (
                                        <SelectItem key={type.value} value={type.value}>
                                            <div className="flex items-center gap-2">
                                                <span>{type.label}</span>
                                                {detectedType === type.value && (
                                                    <Badge variant="outline" className="text-xs">
                                                        Erkannt
                                                    </Badge>
                                                )}
                                            </div>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground">
                                {CORRECTION_TYPES.find(t => t.value === correctionType)?.description}
                            </p>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="correction-notes">Notizen (optional)</Label>
                            <Textarea
                                id="correction-notes"
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                placeholder="Zusätzliche Hinweise zur Korrektur..."
                                rows={3}
                            />
                        </div>
                    </div>
                </div>

                <DialogFooter className="gap-2 sm:gap-0">
                    <Button
                        variant="outline"
                        onClick={() => handleOpenChange(false)}
                        disabled={isSubmitting}
                    >
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={!hasChanges || isSubmitting}
                        className={cn(
                            hasChanges && 'bg-green-600 hover:bg-green-700'
                        )}
                    >
                        {isSubmitting ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Wird eingereicht...
                            </>
                        ) : (
                            'Korrektur einreichen'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
