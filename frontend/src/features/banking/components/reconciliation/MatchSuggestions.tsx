/**
 * Match Suggestions Panel
 *
 * Zeigt Match-Vorschläge für eine Transaktion mit:
 * - Konfidenz-basierte Sortierung
 * - Detaillierte Match-Gründe
 * - Seite-an-Seite Vergleich
 * - Quick-Actions (Akzeptieren/Ablehnen)
 */

import { useState } from 'react';
import {
    AlertTriangle,
    ArrowRight,
    Check,
    CheckCircle2,
    ExternalLink,
    Info,
    Loader2,
    Sparkles,
    Star,
    X,
    XCircle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { useMatchSuggestions, useManualMatch } from '@/features/banking/hooks/use-banking-queries';
import type { BankTransaction, MatchCandidate } from '@/lib/api/services/banking';
import { cn } from '@/lib/utils';

interface MatchSuggestionsProps {
    transaction: BankTransaction;
    onMatchSuccess?: () => void;
    onClose?: () => void;
}

// Match-Typ Labels (Deutsch)
const MATCH_TYPE_LABELS: Record<string, { label: string; description: string }> = {
    iban_amount: {
        label: 'IBAN + Betrag',
        description: 'IBAN und Rechnungsbetrag stimmen exakt überein',
    },
    invoice_number: {
        label: 'Rechnungsnummer',
        description: 'Rechnungsnummer im Verwendungszweck gefunden',
    },
    customer_number: {
        label: 'Kundennummer',
        description: 'Kundennummer erkannt und zugeordnet',
    },
    amount_date: {
        label: 'Betrag + Datum',
        description: 'Betrag und Datum nahe am Fälligkeitsdatum',
    },
    fuzzy_name: {
        label: 'Name ähnlich',
        description: 'Namensähnlichkeit erkannt',
    },
};

// Konfidenz-Level Konfiguration
function getConfidenceLevel(confidence: number) {
    if (confidence >= 0.95) {
        return {
            label: 'Exakt',
            color: 'text-green-600',
            bgColor: 'bg-green-100',
            borderColor: 'border-green-300',
            icon: Star,
        };
    }
    if (confidence >= 0.85) {
        return {
            label: 'Sehr gut',
            color: 'text-green-600',
            bgColor: 'bg-green-50',
            borderColor: 'border-green-200',
            icon: CheckCircle2,
        };
    }
    if (confidence >= 0.70) {
        return {
            label: 'Gut',
            color: 'text-yellow-600',
            bgColor: 'bg-yellow-50',
            borderColor: 'border-yellow-200',
            icon: Sparkles,
        };
    }
    if (confidence >= 0.50) {
        return {
            label: 'Möglich',
            color: 'text-orange-600',
            bgColor: 'bg-orange-50',
            borderColor: 'border-orange-200',
            icon: Info,
        };
    }
    return {
        label: 'Unsicher',
        color: 'text-red-600',
        bgColor: 'bg-red-50',
        borderColor: 'border-red-200',
        icon: AlertTriangle,
    };
}

// Einzelner Vorschlag
function SuggestionItem({
    suggestion,
    transaction,
    isSelected,
    onSelect,
    onAccept,
    onReject,
    isAccepting,
}: {
    suggestion: MatchCandidate;
    transaction: BankTransaction;
    isSelected: boolean;
    onSelect: () => void;
    onAccept: () => void;
    onReject: () => void;
    isAccepting: boolean;
}) {
    const confidence = suggestion.confidence;
    const level = getConfidenceLevel(confidence);
    const Icon = level.icon;
    const percent = Math.round(confidence * 100);

    // Betragsabweichung berechnen
    const txAmount = Math.abs(transaction.amount);
    const docAmount = suggestion.gross_amount;
    const discrepancy = Math.abs(docAmount - txAmount);
    const hasDiscrepancy = discrepancy > 0.01;

    const methodInfo = MATCH_TYPE_LABELS[suggestion.match_method] || {
        label: suggestion.match_method,
        description: 'Automatisch erkannt',
    };

    return (
        <div
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            className={cn(
                'relative p-4 rounded-lg border-2 transition-all cursor-pointer',
                isSelected
                    ? 'border-primary bg-primary/5 shadow-md'
                    : cn('hover:shadow-md', level.borderColor, level.bgColor)
            )}
            onClick={onSelect}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect();
                }
            }}
        >
            {/* Header mit Konfidenz */}
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Icon className={cn('h-5 w-5', level.color)} />
                    <div>
                        <div className="flex items-center gap-2">
                            <span className={cn('font-semibold', level.color)}>
                                {percent}% {level.label}
                            </span>
                            <Badge variant="secondary" className="text-xs">
                                {methodInfo.label}
                            </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {methodInfo.description}
                        </p>
                    </div>
                </div>

                {/* Quick Actions */}
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-8 w-8 p-0 text-green-600 hover:text-green-700 hover:bg-green-50"
                                    onClick={onAccept}
                                    disabled={isAccepting}
                                >
                                    {isAccepting ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Check className="h-4 w-4" />
                                    )}
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Akzeptieren</TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                                    onClick={onReject}
                                >
                                    <X className="h-4 w-4" />
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>Ablehnen</TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            </div>

            {/* Konfidenz-Balken */}
            <Progress value={percent} className="h-1.5 mb-3" />

            {/* Seite-an-Seite Vergleich */}
            <div className="grid grid-cols-[1fr_auto_1fr] gap-3 items-center">
                {/* Transaktion */}
                <div className="text-sm">
                    <p className="text-xs text-muted-foreground mb-1">Transaktion</p>
                    <p className="font-mono font-medium">
                        {formatCurrency(txAmount, { currency: transaction.currency })}
                    </p>
                    <p className="text-muted-foreground truncate">
                        {transaction.counterparty_name || '-'}
                    </p>
                </div>

                {/* Pfeil */}
                <ArrowRight className="h-5 w-5 text-muted-foreground" />

                {/* Dokument */}
                <div className="text-sm">
                    <p className="text-xs text-muted-foreground mb-1">Rechnung</p>
                    <p className="font-mono font-medium">
                        {formatCurrency(docAmount, { currency: 'EUR' })}
                    </p>
                    <p className="text-muted-foreground truncate">
                        {suggestion.invoice_number || suggestion.counterparty_name || '-'}
                    </p>
                </div>
            </div>

            {/* Betragsabweichung Warnung */}
            {hasDiscrepancy && (
                <div className="mt-3 flex items-center gap-2 text-sm text-yellow-600 bg-yellow-50 p-2 rounded">
                    <AlertTriangle className="h-4 w-4" />
                    <span>
                        Abweichung: {formatCurrency(discrepancy, { currency: 'EUR' })}
                    </span>
                </div>
            )}

            {/* Details */}
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
                {suggestion.invoice_date && (
                    <div>
                        <span className="block text-[10px] uppercase">Rechnungsdatum</span>
                        {formatDate(suggestion.invoice_date)}
                    </div>
                )}
                {suggestion.due_date && (
                    <div>
                        <span className="block text-[10px] uppercase">Fällig</span>
                        {formatDate(suggestion.due_date)}
                    </div>
                )}
                {suggestion.customer_number && (
                    <div>
                        <span className="block text-[10px] uppercase">Kundennr.</span>
                        {suggestion.customer_number}
                    </div>
                )}
            </div>

            {/* Auswahl-Indikator */}
            {isSelected && (
                <div className="absolute top-2 right-2">
                    <div className="h-6 w-6 rounded-full bg-primary flex items-center justify-center">
                        <Check className="h-4 w-4 text-primary-foreground" />
                    </div>
                </div>
            )}
        </div>
    );
}

export function MatchSuggestions({
    transaction,
    onMatchSuccess,
    onClose,
}: MatchSuggestionsProps) {
    const [selectedSuggestion, setSelectedSuggestion] = useState<string | null>(null);
    const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
    const [rejectReason, setRejectReason] = useState('');
    const [neverSuggestAgain, setNeverSuggestAgain] = useState(false);
    const [rejectingDocId, setRejectingDocId] = useState<string | null>(null);

    // Data
    const {
        data: suggestions,
        isLoading,
        error,
    } = useMatchSuggestions(transaction.id, 10, true);

    // Mutations
    const manualMatch = useManualMatch();

    const handleAccept = async (documentId: string) => {
        try {
            await manualMatch.mutateAsync({
                transactionId: transaction.id,
                documentId,
            });
            onMatchSuccess?.();
        } catch {
            // Error wird durch Query-Hook behandelt
        }
    };

    const handleRejectClick = (documentId: string) => {
        setRejectingDocId(documentId);
        setRejectDialogOpen(true);
    };

    const handleRejectConfirm = async () => {
        if (!rejectingDocId) return;

        // TODO: Backend-Call zum Speichern der Ablehnung
        console.log('Rejecting match:', {
            transactionId: transaction.id,
            documentId: rejectingDocId,
            reason: rejectReason,
            neverSuggestAgain,
        });

        setRejectDialogOpen(false);
        setRejectReason('');
        setNeverSuggestAgain(false);
        setRejectingDocId(null);
    };

    const bestSuggestion = suggestions?.[0];
    const hasHighConfidence = bestSuggestion && bestSuggestion.confidence >= 0.9;

    return (
        <>
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                Match-Vorschläge
                                {suggestions && suggestions.length > 0 && (
                                    <Badge variant="outline">{suggestions.length}</Badge>
                                )}
                                {hasHighConfidence && (
                                    <Badge className="bg-green-500 text-white gap-1">
                                        <Sparkles className="h-3 w-3" />
                                        Hohe Übereinstimmung
                                    </Badge>
                                )}
                            </CardTitle>
                            <CardDescription>
                                Mögliche Dokumente für diese Transaktion
                            </CardDescription>
                        </div>
                        {onClose && (
                            <Button variant="ghost" size="sm" onClick={onClose}>
                                <X className="h-4 w-4" />
                            </Button>
                        )}
                    </div>

                    {/* Transaktions-Info */}
                    <div className="mt-3 p-3 bg-muted/50 rounded-lg">
                        <div className="grid grid-cols-4 gap-3 text-sm">
                            <div>
                                <span className="text-xs text-muted-foreground">Datum</span>
                                <p className="font-medium">{formatDate(transaction.booking_date)}</p>
                            </div>
                            <div>
                                <span className="text-xs text-muted-foreground">Betrag</span>
                                <p
                                    className={cn(
                                        'font-mono font-medium',
                                        transaction.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                    )}
                                >
                                    {formatCurrency(transaction.amount, { currency: transaction.currency })}
                                </p>
                            </div>
                            <div>
                                <span className="text-xs text-muted-foreground">Gegenpartei</span>
                                <p className="font-medium truncate">
                                    {transaction.counterparty_name || '-'}
                                </p>
                            </div>
                            <div>
                                <span className="text-xs text-muted-foreground">Referenz</span>
                                <p className="truncate">{transaction.reference_text || '-'}</p>
                            </div>
                        </div>
                    </div>
                </CardHeader>

                <CardContent>
                    {isLoading ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : error ? (
                        <div className="py-8 text-center text-muted-foreground">
                            <XCircle className="mx-auto h-12 w-12 text-red-500/50" />
                            <p className="mt-4">Fehler beim Laden der Vorschläge</p>
                        </div>
                    ) : !suggestions || suggestions.length === 0 ? (
                        <div className="py-8 text-center text-muted-foreground">
                            <Info className="mx-auto h-12 w-12 text-muted-foreground/50" />
                            <h3 className="mt-4 text-lg font-medium">
                                Keine automatischen Vorschläge
                            </h3>
                            <p className="text-sm">
                                Nutzen Sie die manuelle Suche zum Verknüpfen.
                            </p>
                        </div>
                    ) : (
                        <ScrollArea className="h-[400px] pr-4">
                            <div className="space-y-3">
                                {suggestions.map((suggestion) => (
                                    <SuggestionItem
                                        key={suggestion.document_id}
                                        suggestion={suggestion}
                                        transaction={transaction}
                                        isSelected={selectedSuggestion === suggestion.document_id}
                                        onSelect={() => setSelectedSuggestion(suggestion.document_id)}
                                        onAccept={() => handleAccept(suggestion.document_id)}
                                        onReject={() => handleRejectClick(suggestion.document_id)}
                                        isAccepting={manualMatch.isPending}
                                    />
                                ))}
                            </div>
                        </ScrollArea>
                    )}

                    {/* Footer mit Aktionen */}
                    {suggestions && suggestions.length > 0 && selectedSuggestion && (
                        <>
                            <Separator className="my-4" />
                            <div className="flex items-center justify-between">
                                <Button variant="outline" onClick={() => setSelectedSuggestion(null)}>
                                    Auswahl aufheben
                                </Button>
                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="outline"
                                        asChild
                                    >
                                        <a href={`/documents/${selectedSuggestion}`} target="_blank" rel="noopener noreferrer">
                                            <ExternalLink className="h-4 w-4 mr-1" />
                                            Dokument öffnen
                                        </a>
                                    </Button>
                                    <Button
                                        onClick={() => handleAccept(selectedSuggestion)}
                                        disabled={manualMatch.isPending}
                                    >
                                        {manualMatch.isPending ? (
                                            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                        ) : (
                                            <Check className="h-4 w-4 mr-1" />
                                        )}
                                        Verknüpfen
                                    </Button>
                                </div>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Ablehnung-Dialog */}
            <AlertDialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Match ablehnen</AlertDialogTitle>
                        <AlertDialogDescription>
                            Bitte geben Sie einen Grund für die Ablehnung an.
                            Dies hilft bei der Verbesserung zukünftiger Vorschläge.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <div className="space-y-4 py-4">
                        <Textarea
                            placeholder="Grund für Ablehnung eingeben..."
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            className="min-h-[100px]"
                        />
                        <div className="flex items-center gap-2">
                            <Checkbox
                                id="never-suggest"
                                checked={neverSuggestAgain}
                                onCheckedChange={(checked) => setNeverSuggestAgain(checked === true)}
                            />
                            <label htmlFor="never-suggest" className="text-sm">
                                Dieses Dokument nie wieder für diese Transaktion vorschlagen
                            </label>
                        </div>
                    </div>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={() => {
                            setRejectReason('');
                            setNeverSuggestAgain(false);
                        }}>
                            Abbrechen
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleRejectConfirm}
                            disabled={rejectReason.trim().length < 3}
                            className="bg-red-600 hover:bg-red-700"
                        >
                            Ablehnen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}
