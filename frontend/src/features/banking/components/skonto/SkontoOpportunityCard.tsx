/**
 * Skonto Opportunity Card
 * Zeigt eine Skonto-Gelegenheit mit Details und Aktionen
 */

import { Calendar, Percent, ExternalLink, Send } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatCurrency } from '@/features/banking/utils/format';
import type { SkontoOpportunity } from '@/lib/api/services/banking';

interface SkontoOpportunityCardProps {
    opportunity: SkontoOpportunity;
    onCreatePayment: (opportunity: SkontoOpportunity) => void;
}

export function SkontoOpportunityCard({ opportunity, onCreatePayment }: SkontoOpportunityCardProps) {
    const daysRemaining = opportunity.skonto_days_remaining ?? 0;
    const isUrgent = daysRemaining <= 3 && daysRemaining >= 0;
    const isExpired = daysRemaining < 0;

    // Progress bar based on days remaining
    const progressPercent = Math.max(0, Math.min(100, (daysRemaining / 14) * 100));

    return (
        <Card className={isExpired ? 'opacity-60' : isUrgent ? 'border-orange-500' : ''}>
            <CardContent className="p-4">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    {/* Left: Document Info */}
                    <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                            <span className="font-medium truncate">{opportunity.beneficiary_name || 'Unbekannt'}</span>
                            {opportunity.invoice_number && (
                                <Badge variant="outline" className="shrink-0">
                                    {opportunity.invoice_number}
                                </Badge>
                            )}
                            {isUrgent && !isExpired && (
                                <Badge variant="destructive" className="shrink-0">
                                    Dringend
                                </Badge>
                            )}
                            {isExpired && (
                                <Badge variant="secondary" className="shrink-0">
                                    Abgelaufen
                                </Badge>
                            )}
                        </div>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                            {opportunity.skonto_deadline && (
                                <span className="flex items-center gap-1">
                                    <Calendar className="h-3 w-3" />
                                    Frist: {new Date(opportunity.skonto_deadline).toLocaleDateString('de-DE')}
                                </span>
                            )}
                            {opportunity.skonto_percent != null && (
                                <span className="flex items-center gap-1">
                                    <Percent className="h-3 w-3" />
                                    {opportunity.skonto_percent}% Skonto
                                </span>
                            )}
                        </div>

                        {/* Progress Bar */}
                        <div className="space-y-1">
                            <Progress
                                value={progressPercent}
                                className={`h-2 ${isUrgent ? '[&>div]:bg-orange-500' : ''}`}
                            />
                            <p className="text-xs text-muted-foreground">
                                {isExpired
                                    ? 'Skonto-Frist abgelaufen'
                                    : daysRemaining === 0
                                      ? 'Letzer Tag für Skonto!'
                                      : daysRemaining === 1
                                        ? 'Noch 1 Tag'
                                        : `Noch ${daysRemaining} Tage`}
                            </p>
                        </div>
                    </div>

                    {/* Middle: Amounts */}
                    <div className="flex items-center gap-6 text-sm">
                        <div className="text-center">
                            <p className="text-muted-foreground">Rechnungsbetrag</p>
                            <p className="font-mono font-medium">
                                {formatCurrency(opportunity.gross_amount, { currency: opportunity.currency })}
                            </p>
                        </div>
                        {opportunity.skonto_amount != null && (
                            <div className="text-center">
                                <p className="text-muted-foreground">Skonto-Betrag</p>
                                <p className="font-mono font-medium text-green-600">
                                    -{formatCurrency(opportunity.skonto_amount, { currency: opportunity.currency })}
                                </p>
                            </div>
                        )}
                        {opportunity.amount_with_skonto != null && (
                            <div className="text-center">
                                <p className="text-muted-foreground">Zu zahlen</p>
                                <p className="font-mono font-bold">
                                    {formatCurrency(opportunity.amount_with_skonto, { currency: opportunity.currency })}
                                </p>
                            </div>
                        )}
                    </div>

                    {/* Right: Actions */}
                    <div className="flex items-center gap-2 shrink-0">
                        <Button variant="ghost" size="sm" asChild>
                            <a href={`/documents/${opportunity.document_id}`}>
                                <ExternalLink className="h-4 w-4 mr-1" />
                                Dokument
                            </a>
                        </Button>
                        {!isExpired && (
                            <Button
                                size="sm"
                                onClick={() => onCreatePayment(opportunity)}
                            >
                                <Send className="h-4 w-4 mr-1" />
                                Zahlung erstellen
                            </Button>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
