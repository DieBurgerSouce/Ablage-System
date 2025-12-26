/**
 * Match Suggestion Card
 * Zeigt einen Matching-Vorschlag zwischen Transaktion und Rechnung
 */

import { CheckCircle, XCircle, ExternalLink, ArrowRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import type { BankTransaction } from '@/lib/api/services/banking';

// Lokaler Type für Match-Vorschlaege
interface MatchSuggestion {
    id: string;
    transaction: BankTransaction;
    document: {
        id: string;
        vendor_name: string | null;
        invoice_number: string | null;
        invoice_date: string | null;
        total_amount: number;
        currency: string | null;
    };
    confidence_score: number;
    match_type: string;
}

interface MatchSuggestionCardProps {
    suggestion: MatchSuggestion;
    onAccept: (suggestionId: string) => void;
    onReject: (suggestionId: string) => void;
    isLoading?: boolean;
}

const MATCH_TYPE_LABELS: Record<string, string> = {
    exact_amount: 'Exakter Betrag',
    reference_match: 'Referenz gefunden',
    fuzzy_amount: 'Aehnlicher Betrag',
    date_proximity: 'Zeitliche Naehe',
    combined: 'Kombiniert',
};

export function MatchSuggestionCard({
    suggestion,
    onAccept,
    onReject,
    isLoading,
}: MatchSuggestionCardProps) {
    const confidencePercent = Math.round(suggestion.confidence_score * 100);
    const confidenceColor =
        confidencePercent >= 90
            ? 'text-green-600'
            : confidencePercent >= 70
              ? 'text-yellow-600'
              : 'text-orange-600';

    return (
        <Card className="overflow-hidden">
            <CardContent className="p-4">
                <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr_auto]">
                    {/* Transaction Side */}
                    <div className="space-y-2">
                        <p className="text-xs text-muted-foreground uppercase tracking-wide">
                            Transaktion
                        </p>
                        <p className="font-medium">{suggestion.transaction.counterparty_name || '-'}</p>
                        <p className="text-sm text-muted-foreground line-clamp-2">
                            {suggestion.transaction.reference_text}
                        </p>
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                {formatDate(suggestion.transaction.booking_date)}
                            </span>
                            <span
                                className={`font-mono font-medium ${
                                    suggestion.transaction.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}
                            >
                                {suggestion.transaction.amount >= 0 ? '+' : ''}
                                {formatCurrency(suggestion.transaction.amount, {
                                    currency: suggestion.transaction.currency,
                                })}
                            </span>
                        </div>
                    </div>

                    {/* Match Indicator */}
                    <div className="flex flex-col items-center justify-center px-4">
                        <ArrowRight className="h-6 w-6 text-muted-foreground" />
                        <Badge variant="outline" className="mt-2">
                            {MATCH_TYPE_LABELS[suggestion.match_type] || suggestion.match_type}
                        </Badge>
                        <span className={`text-sm font-medium mt-1 ${confidenceColor}`}>
                            {confidencePercent}% Match
                        </span>
                    </div>

                    {/* Document Side */}
                    <div className="space-y-2">
                        <p className="text-xs text-muted-foreground uppercase tracking-wide">
                            Rechnung
                        </p>
                        <p className="font-medium">{suggestion.document.vendor_name || '-'}</p>
                        <p className="text-sm text-muted-foreground">
                            {suggestion.document.invoice_number
                                ? `Nr. ${suggestion.document.invoice_number}`
                                : 'Keine Rechnungsnr.'}
                        </p>
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                {suggestion.document.invoice_date
                                    ? formatDate(suggestion.document.invoice_date)
                                    : '-'}
                            </span>
                            <span className="font-mono font-medium">
                                {formatCurrency(suggestion.document.total_amount, {
                                    currency: suggestion.document.currency || 'EUR',
                                })}
                            </span>
                            <Button variant="ghost" size="sm" asChild>
                                <a href={`/documents/${suggestion.document.id}`}>
                                    <ExternalLink className="h-4 w-4" />
                                </a>
                            </Button>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col justify-center gap-2">
                        <Button
                            size="sm"
                            onClick={() => onAccept(suggestion.id)}
                            disabled={isLoading}
                        >
                            <CheckCircle className="h-4 w-4 mr-1" />
                            Akzeptieren
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onReject(suggestion.id)}
                            disabled={isLoading}
                        >
                            <XCircle className="h-4 w-4 mr-1" />
                            Ablehnen
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
