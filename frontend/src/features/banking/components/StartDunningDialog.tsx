/**
 * StartDunningDialog - Dialog zum Starten eines Mahnvorgangs
 *
 * Ermöglicht das manuelle Starten einer Mahnung für überfällige Rechnungen.
 * - Auswahl der initialen Mahnstufe
 * - Optionale Notizen
 * - Bestätigung vor dem Start
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useToast } from '@/components/ui/use-toast'
import {
    AlertTriangle,
    FileWarning,
    Mail,
    Phone,
    Gavel,
    Loader2,
    CheckCircle2,
} from 'lucide-react'
import { bankingService } from '@/lib/api/services/banking'

// ==================== Types ====================

interface StartDunningDialogProps {
    /** ID des Dokuments/der Rechnung */
    documentId: string
    /** Rechnungsnummer zur Anzeige */
    invoiceNumber?: string
    /** Debitorname zur Anzeige */
    debtorName?: string
    /** Offener Betrag zur Anzeige */
    outstandingAmount?: number
    /** Dialog offen/geschlossen */
    open: boolean
    /** Callback wenn Dialog geschlossen wird */
    onOpenChange: (open: boolean) => void
    /** Callback nach erfolgreichem Start */
    onSuccess?: (dunningId: string) => void
}

interface DunningLevel {
    value: string
    label: string
    description: string
    icon: React.ReactNode
}

// ==================== Configuration ====================

const DUNNING_LEVELS: DunningLevel[] = [
    {
        value: '0',
        label: 'Zahlungserinnerung',
        description: 'Freundliche Erinnerung ohne Gebühren',
        icon: <Mail className="h-4 w-4" />,
    },
    {
        value: '1',
        label: '1. Mahnung',
        description: 'Erste formelle Mahnung',
        icon: <FileWarning className="h-4 w-4" />,
    },
    {
        value: '2',
        label: '2. Mahnung',
        description: 'Mit Mahngebühren und Fristsetzung',
        icon: <Phone className="h-4 w-4" />,
    },
    {
        value: '3',
        label: 'Letzte Mahnung',
        description: 'Androhung rechtlicher Schritte',
        icon: <AlertTriangle className="h-4 w-4" />,
    },
    {
        value: '4',
        label: 'Inkassoandrohung',
        description: 'Letzte Warnung vor Inkasso-Übergabe',
        icon: <Gavel className="h-4 w-4" />,
    },
]

// ==================== Component ====================

export function StartDunningDialog({
    documentId,
    invoiceNumber,
    debtorName,
    outstandingAmount,
    open,
    onOpenChange,
    onSuccess,
}: StartDunningDialogProps) {
    const { toast } = useToast()
    const queryClient = useQueryClient()

    const [selectedLevel, setSelectedLevel] = useState<string>('0')
    const [notes, setNotes] = useState('')
    // Double-Submit Protection
    const [isSubmitLocked, setIsSubmitLocked] = useState(false)

    // Mutation für das Erstellen des Mahnvorgangs
    const createDunning = useMutation({
        mutationFn: async () => {
            const response = await bankingService.createDunning({
                document_id: documentId,
                level: selectedLevel,
                notes: notes.trim() || undefined,
            })
            return response
        },
        onSuccess: (data) => {
            // Queries invalidieren
            queryClient.invalidateQueries({ queryKey: ['dunning-records'] })
            queryClient.invalidateQueries({ queryKey: ['dunning-stats'] })
            queryClient.invalidateQueries({ queryKey: ['overdue-invoices'] })

            toast({
                title: 'Mahnvorgang gestartet',
                description: `Mahnung für ${invoiceNumber || 'Rechnung'} wurde erfolgreich angelegt.`,
            })

            // Reset und schließen
            setSelectedLevel('0')
            setNotes('')
            onOpenChange(false)
            onSuccess?.(data?.id || documentId)
        },
        onError: (error: Error) => {
            // Security: Zeige generische Nachricht statt error.message (XSS-Prevention)
            console.error('[StartDunningDialog] createDunning failed:', error)
            toast({
                title: 'Mahnvorgang konnte nicht gestartet werden',
                description: 'Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.',
                variant: 'destructive',
            })
        },
    })

    const handleSubmit = () => {
        // Double-Submit Protection: Verhindere doppelte Mahngebühren
        if (isSubmitLocked || createDunning.isPending) return
        setIsSubmitLocked(true)
        createDunning.mutate(undefined, {
            onSettled: () => setIsSubmitLocked(false),
        })
    }

    const handleClose = () => {
        if (!createDunning.isPending) {
            setSelectedLevel('0')
            setNotes('')
            onOpenChange(false)
        }
    }

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: 'EUR',
        }).format(amount)
    }

    const selectedLevelInfo = DUNNING_LEVELS.find((l) => l.value === selectedLevel)

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileWarning className="h-5 w-5 text-orange-500" />
                        Mahnung starten
                    </DialogTitle>
                    <DialogDescription>
                        Starten Sie einen Mahnvorgang für diese überfällige Rechnung.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Rechnungs-Info */}
                    {(invoiceNumber || debtorName || outstandingAmount) && (
                        <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                            {invoiceNumber && (
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Rechnung:</span>
                                    <span className="font-medium">{invoiceNumber}</span>
                                </div>
                            )}
                            {debtorName && (
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Debitor:</span>
                                    <span className="font-medium">{debtorName}</span>
                                </div>
                            )}
                            {outstandingAmount !== undefined && (
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Offener Betrag:</span>
                                    <span className="font-mono font-medium text-red-600">
                                        {formatCurrency(outstandingAmount)}
                                    </span>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Mahnstufe Auswahl */}
                    <div className="space-y-2">
                        <Label htmlFor="dunning-level">
                            Mahnstufe <span className="text-destructive">*</span>
                        </Label>
                        <Select
                            value={selectedLevel}
                            onValueChange={setSelectedLevel}
                        >
                            <SelectTrigger
                                id="dunning-level"
                                aria-describedby="dunning-level-description"
                            >
                                <SelectValue placeholder="Mahnstufe auswählen" />
                            </SelectTrigger>
                            <SelectContent>
                                {DUNNING_LEVELS.map((level) => (
                                    <SelectItem key={level.value} value={level.value}>
                                        <div className="flex items-center gap-2">
                                            {level.icon}
                                            <span>{level.label}</span>
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {selectedLevelInfo && (
                            <p
                                id="dunning-level-description"
                                className="text-xs text-muted-foreground"
                            >
                                {selectedLevelInfo.description}
                            </p>
                        )}
                    </div>

                    {/* Notizen */}
                    <div className="space-y-2">
                        <Label htmlFor="dunning-notes">Notizen (optional)</Label>
                        <Textarea
                            id="dunning-notes"
                            placeholder="z.B. Grund für das manuelle Starten, besondere Umstände..."
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={3}
                        />
                    </div>

                    {/* Warnung bei höheren Stufen */}
                    {parseInt(selectedLevel) >= 2 && (
                        <Alert variant="default" className="border-orange-200 bg-orange-50">
                            <AlertTriangle className="h-4 w-4 text-orange-600" />
                            <AlertDescription className="text-orange-800">
                                {parseInt(selectedLevel) >= 3
                                    ? 'Bei dieser Mahnstufe werden rechtliche Schritte angedroht. Stellen Sie sicher, dass alle vorherigen Mahnungen dokumentiert sind.'
                                    : 'Ab dieser Mahnstufe werden Mahngebühren und Verzugszinsen berechnet.'}
                            </AlertDescription>
                        </Alert>
                    )}
                </div>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={handleClose}
                        disabled={createDunning.isPending}
                    >
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={createDunning.isPending}
                        className="bg-orange-600 hover:bg-orange-700"
                    >
                        {createDunning.isPending ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Wird gestartet...
                            </>
                        ) : (
                            <>
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                                Mahnung starten
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

export default StartDunningDialog
