/**
 * Manual Match Dialog
 * Dialog für manuelles Matching von Transaktion zu Dokument
 *
 * Features:
 * - Automatische Match-Vorschläge mit Confidence-Anzeige
 * - Manuelles Matching mit Suche
 * - Visuelle Hervorhebung der besten Matches
 */

import { useState, useMemo, useRef, useEffect } from 'react';
import { Search, FileText, Loader2, Sparkles, Star, Check } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { logger } from '@/lib/logger';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { useMatchSuggestions } from '@/features/banking/hooks/use-banking-queries';
import type { BankTransaction, MatchCandidate } from '@/lib/api/services/banking';
import { cn } from '@/lib/utils';

interface Document {
    id: string;
    vendor_name: string | null;
    invoice_number: string | null;
    invoice_date: string | null;
    total_amount: number;
    currency: string | null;
}

interface ManualMatchDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    transaction: BankTransaction | null;
    documents: Document[];
    isLoading?: boolean;
    onMatch: (transactionId: string, documentId: string) => Promise<void>;
}

// ==================== Helper Components ====================

function ConfidenceBadge({ confidence }: { confidence: number }) {
    // Security: Bounds-Check für Confidence (0-1 Range)
    const safeConfidence = Math.max(0, Math.min(1, confidence || 0));
    const percent = Math.round(safeConfidence * 100);
    const getColor = () => {
        if (percent >= 90) return 'bg-green-100 text-green-800 border-green-200';
        if (percent >= 70) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
        return 'bg-orange-100 text-orange-800 border-orange-200';
    };

    return (
        <Badge variant="outline" className={cn('gap-1 font-mono text-xs', getColor())}>
            {percent >= 90 && <Star className="h-3 w-3" aria-hidden="true" />}
            {percent}%
        </Badge>
    );
}

function SuggestionCard({
    suggestion,
    isSelected,
    onSelect,
}: {
    suggestion: MatchCandidate;
    isSelected: boolean;
    onSelect: () => void;
}) {
    const confidence = suggestion.confidence;
    const isHighConfidence = confidence >= 0.9;

    return (
        <div
            role="button"
            tabIndex={0}
            aria-label={`Match-Vorschlag: ${suggestion.counterparty_name || 'Unbekannt'}, Konfidenz ${Math.round(confidence * 100)}%`}
            aria-pressed={isSelected}
            className={cn(
                'relative p-4 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md',
                isSelected
                    ? 'border-primary bg-primary/5 shadow-md'
                    : isHighConfidence
                        ? 'border-green-300 bg-green-50/50 hover:border-green-400'
                        : 'border-border hover:border-primary/50'
            )}
            onClick={onSelect}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect();
                }
            }}
        >
            {/* Selection Indicator */}
            {isSelected && (
                <div className="absolute top-2 right-2">
                    <Check className="h-5 w-5 text-primary" aria-hidden="true" />
                </div>
            )}

            {/* High Confidence Indicator */}
            {isHighConfidence && !isSelected && (
                <div className="absolute top-2 right-2">
                    <Sparkles className="h-4 w-4 text-green-500" aria-hidden="true" />
                </div>
            )}

            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium truncate">
                            {suggestion.counterparty_name || 'Unbekannter Lieferant'}
                        </span>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                        {suggestion.invoice_number && (
                            <span className="font-mono">{suggestion.invoice_number}</span>
                        )}
                        {suggestion.invoice_date && (
                            <span>{formatDate(suggestion.invoice_date)}</span>
                        )}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                        <span className="font-mono font-medium text-lg">
                            {formatCurrency(suggestion.gross_amount)}
                        </span>
                        <ConfidenceBadge confidence={confidence} />
                    </div>
                    {suggestion.match_method && (
                        <p className="text-xs text-muted-foreground mt-1">
                            Methode: {suggestion.match_method}
                        </p>
                    )}
                </div>
            </div>

            {/* Confidence Progress Bar */}
            <div className="mt-3">
                <Progress
                    value={confidence * 100}
                    className="h-1.5"
                    aria-label={`Konfidenz: ${Math.round(confidence * 100)}%`}
                />
            </div>
        </div>
    );
}

// ==================== Main Component ====================

export function ManualMatchDialog({
    open,
    onOpenChange,
    transaction,
    documents,
    isLoading,
    onMatch,
}: ManualMatchDialogProps) {
    const [activeTab, setActiveTab] = useState<string>('suggestions');
    const [searchText, setSearchText] = useState('');
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
    const [isMatching, setIsMatching] = useState(false);
    const { toast } = useToast();

    // AbortController für Memory Leak Prevention
    const abortControllerRef = useRef<AbortController | null>(null);

    // Cleanup bei Unmount
    useEffect(() => {
        return () => {
            abortControllerRef.current?.abort();
        };
    }, []);

    // Fetch match suggestions
    const {
        data: suggestions,
        isLoading: suggestionsLoading,
    } = useMatchSuggestions(transaction?.id || '', 10, open && !!transaction);

    // Filter documents by search text
    const filteredDocs = useMemo(() => {
        if (!searchText.trim()) return documents;
        const search = searchText.toLowerCase();
        return documents.filter(
            (doc) =>
                doc.vendor_name?.toLowerCase().includes(search) ||
                doc.invoice_number?.toLowerCase().includes(search)
        );
    }, [documents, searchText]);

    // Best suggestion (highest confidence)
    const bestSuggestion = useMemo(() => {
        if (!suggestions || suggestions.length === 0) return null;
        return suggestions.reduce((best, current) =>
            current.confidence > best.confidence ? current : best
        );
    }, [suggestions]);

    const handleMatch = async () => {
        if (!transaction || !selectedDocId || isMatching) return;

        // Vorherigen Request abbrechen
        abortControllerRef.current?.abort();
        const controller = new AbortController();
        abortControllerRef.current = controller;

        setIsMatching(true);
        try {
            await onMatch(transaction.id, selectedDocId);

            // Nach Erfolg nur wenn nicht aborted
            if (!controller.signal.aborted) {
                toast({
                    title: 'Erfolgreich verknüpft',
                    description: 'Transaktion wurde dem Dokument zugeordnet.',
                });
                onOpenChange(false);
                setSelectedDocId(null);
                setSearchText('');
                setActiveTab('suggestions');
            }
        } catch (error) {
            // Error Handling nur wenn nicht aborted
            if (!controller.signal.aborted) {
                logger.error('Verknüpfung fehlgeschlagen', error);
                toast({
                    title: 'Verknüpfung fehlgeschlagen',
                    description: 'Die Zuordnung konnte nicht gespeichert werden. Bitte versuchen Sie es erneut.',
                    variant: 'destructive',
                });
            }
        } finally {
            if (!controller.signal.aborted) {
                setIsMatching(false);
            }
        }
    };

    const handleClose = () => {
        onOpenChange(false);
        setSelectedDocId(null);
        setSearchText('');
        setActiveTab('suggestions');
    };

    const handleQuickMatch = () => {
        if (bestSuggestion && bestSuggestion.confidence >= 0.9) {
            setSelectedDocId(bestSuggestion.document_id);
        }
    };

    if (!transaction) return null;

    const hasSuggestions = suggestions && suggestions.length > 0;
    const hasHighConfidenceMatch = bestSuggestion && bestSuggestion.confidence >= 0.9;

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        Transaktion zuordnen
                        {hasHighConfidenceMatch && (
                            <Badge className="bg-green-500 text-white gap-1">
                                <Sparkles className="h-3 w-3" aria-hidden="true" />
                                Hohe Übereinstimmung gefunden
                            </Badge>
                        )}
                    </DialogTitle>
                    <DialogDescription>
                        Ordnen Sie diese Transaktion einem Dokument zu.
                    </DialogDescription>
                </DialogHeader>

                {/* Transaction Info */}
                <div className="rounded-lg border p-4 bg-muted/50">
                    <p className="text-sm text-muted-foreground mb-2">Transaktion</p>
                    <div className="grid gap-2 md:grid-cols-4">
                        <div>
                            <p className="text-xs text-muted-foreground">Datum</p>
                            <p className="font-medium">{formatDate(transaction.booking_date)}</p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Betrag</p>
                            <p
                                className={`font-mono font-medium ${
                                    transaction.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}
                            >
                                {formatCurrency(transaction.amount, { currency: transaction.currency })}
                            </p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Gegenpartei</p>
                            <p className="font-medium truncate">
                                {transaction.counterparty_name || '-'}
                            </p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Verwendungszweck</p>
                            <p className="text-sm truncate">
                                {transaction.reference_text || '-'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Quick Match Button for high confidence */}
                {hasHighConfidenceMatch && !selectedDocId && (
                    <div className="flex items-center gap-3 p-3 rounded-lg bg-green-50 border border-green-200">
                        <Sparkles className="h-5 w-5 text-green-600 flex-shrink-0" aria-hidden="true" />
                        <div className="flex-1">
                            <p className="text-sm font-medium text-green-800">
                                Beste Übereinstimmung: {bestSuggestion.counterparty_name || bestSuggestion.invoice_number}
                            </p>
                            <p className="text-xs text-green-600">
                                {Math.round(bestSuggestion.confidence * 100)}% Konfidenz
                            </p>
                        </div>
                        <Button
                            size="sm"
                            className="bg-green-600 hover:bg-green-700"
                            onClick={handleQuickMatch}
                        >
                            <Check className="h-4 w-4 mr-1" aria-hidden="true" />
                            Übernehmen
                        </Button>
                    </div>
                )}

                {/* Tabs: Suggestions vs Manual Search */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="suggestions" className="gap-2">
                            <Sparkles className="h-4 w-4" aria-hidden="true" />
                            Vorschläge
                            {hasSuggestions && (
                                <Badge variant="secondary" className="ml-1 h-5 text-xs">
                                    {suggestions.length}
                                </Badge>
                            )}
                        </TabsTrigger>
                        <TabsTrigger value="manual" className="gap-2">
                            <Search className="h-4 w-4" aria-hidden="true" />
                            Manuelle Suche
                        </TabsTrigger>
                    </TabsList>

                    {/* Suggestions Tab */}
                    <TabsContent value="suggestions" className="flex-1 mt-4">
                        <ScrollArea className="h-[300px]">
                            {suggestionsLoading ? (
                                <div className="flex items-center justify-center h-full">
                                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                </div>
                            ) : !hasSuggestions ? (
                                <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                    <FileText className="h-12 w-12 mb-2" aria-hidden="true" />
                                    <p className="font-medium">Keine automatischen Vorschläge</p>
                                    <p className="text-sm mt-1">Nutzen Sie die manuelle Suche</p>
                                    <Button
                                        variant="outline"
                                        className="mt-4"
                                        onClick={() => setActiveTab('manual')}
                                    >
                                        <Search className="h-4 w-4 mr-2" aria-hidden="true" />
                                        Zur manuellen Suche
                                    </Button>
                                </div>
                            ) : (
                                <div className="space-y-3 pr-4">
                                    {suggestions.map((suggestion) => (
                                        <SuggestionCard
                                            key={suggestion.document_id}
                                            suggestion={suggestion}
                                            isSelected={selectedDocId === suggestion.document_id}
                                            onSelect={() => setSelectedDocId(suggestion.document_id)}
                                        />
                                    ))}
                                </div>
                            )}
                        </ScrollArea>
                    </TabsContent>

                    {/* Manual Search Tab */}
                    <TabsContent value="manual" className="flex-1 mt-4 flex flex-col min-h-0">
                        {/* Search Input */}
                        <div className="space-y-2 mb-4">
                            <Label htmlFor="doc-search">Dokument suchen</Label>
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
                                <Input
                                    id="doc-search"
                                    placeholder="Nach Lieferant oder Rechnungsnummer suchen..."
                                    className="pl-9"
                                    value={searchText}
                                    onChange={(e) => setSearchText(e.target.value)}
                                />
                            </div>
                        </div>

                        {/* Document List */}
                        <ScrollArea className="flex-1 border rounded-md">
                            {isLoading ? (
                                <div className="flex items-center justify-center h-[250px]">
                                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                </div>
                            ) : filteredDocs.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-[250px] text-muted-foreground">
                                    <FileText className="h-12 w-12 mb-2" aria-hidden="true" />
                                    <p>Keine passenden Dokumente gefunden</p>
                                </div>
                            ) : (
                                <RadioGroup
                                    value={selectedDocId || undefined}
                                    onValueChange={setSelectedDocId}
                                >
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead className="w-[50px]"></TableHead>
                                                <TableHead>Lieferant</TableHead>
                                                <TableHead>Rechnungsnr.</TableHead>
                                                <TableHead>Datum</TableHead>
                                                <TableHead className="text-right">Betrag</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {filteredDocs.map((doc) => (
                                                <TableRow
                                                    key={doc.id}
                                                    className="cursor-pointer"
                                                    onClick={() => setSelectedDocId(doc.id)}
                                                >
                                                    <TableCell>
                                                        <RadioGroupItem value={doc.id} aria-label={`Dokument ${doc.invoice_number || doc.vendor_name} auswählen`} />
                                                    </TableCell>
                                                    <TableCell className="font-medium">
                                                        {doc.vendor_name || '-'}
                                                    </TableCell>
                                                    <TableCell>{doc.invoice_number || '-'}</TableCell>
                                                    <TableCell>
                                                        {doc.invoice_date
                                                            ? formatDate(doc.invoice_date)
                                                            : '-'}
                                                    </TableCell>
                                                    <TableCell className="text-right font-mono">
                                                        {formatCurrency(doc.total_amount, {
                                                            currency: doc.currency || 'EUR',
                                                        })}
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </RadioGroup>
                            )}
                        </ScrollArea>
                    </TabsContent>
                </Tabs>

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose}>
                        Abbrechen
                    </Button>
                    <Button onClick={handleMatch} disabled={!selectedDocId || isMatching}>
                        {isMatching ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                                Verknüpfe...
                            </>
                        ) : (
                            <>
                                <Check className="mr-2 h-4 w-4" aria-hidden="true" />
                                Verknüpfen
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
