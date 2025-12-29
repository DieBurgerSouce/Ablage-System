/**
 * Skonto Page
 * Skonto-Möglichkeiten anzeigen und nutzen
 */

import { useState, useMemo } from 'react';
import { Percent, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useSkontoOpportunities } from '@/features/banking/hooks/use-banking-queries';
import { formatCurrency } from '@/features/banking/utils/format';
import { SkontoOpportunityCard } from './SkontoOpportunityCard';
import { CreatePaymentDialog } from '../payments/CreatePaymentDialog';
import type { SkontoOpportunity } from '@/lib/api/services/banking';

type SortOption = 'deadline' | 'amount' | 'percent';

export function SkontoPage() {
    const [sortBy, setSortBy] = useState<SortOption>('deadline');
    const [showExpired, setShowExpired] = useState(false);
    const [createPaymentOpen, setCreatePaymentOpen] = useState(false);
    const [selectedOpportunity, setSelectedOpportunity] = useState<SkontoOpportunity | null>(null);

    const { data: opportunities, isLoading, error } = useSkontoOpportunities({
        include_expired: showExpired,
    });

    // Calculate summary stats
    const stats = useMemo(() => {
        if (!opportunities?.length) {
            return { total: 0, totalSavings: 0, urgent: 0, expiringSoon: 0 };
        }

        let totalSavings = 0;
        let urgent = 0;
        let expiringSoon = 0;

        opportunities.forEach((opp) => {
            const daysRemaining = opp.skonto_days_remaining ?? 0;

            if (daysRemaining >= 0 && opp.skonto_amount) {
                totalSavings += opp.skonto_amount;
                if (daysRemaining <= 3) urgent++;
                if (daysRemaining <= 7) expiringSoon++;
            }
        });

        return {
            total: opportunities.length,
            totalSavings,
            urgent,
            expiringSoon,
        };
    }, [opportunities]);

    // Sort and filter opportunities
    const sortedOpportunities = useMemo(() => {
        if (!opportunities) return [];

        let filtered = [...opportunities];

        // Filter expired if needed
        if (!showExpired) {
            filtered = filtered.filter(
                (opp) => (opp.skonto_days_remaining ?? 0) >= 0
            );
        }

        // Sort
        filtered.sort((a, b) => {
            switch (sortBy) {
                case 'deadline':
                    return (a.skonto_days_remaining ?? 0) - (b.skonto_days_remaining ?? 0);
                case 'amount':
                    return (b.skonto_amount ?? 0) - (a.skonto_amount ?? 0);
                case 'percent':
                    return (b.skonto_percent ?? 0) - (a.skonto_percent ?? 0);
                default:
                    return 0;
            }
        });

        return filtered;
    }, [opportunities, sortBy, showExpired]);

    const handleCreatePayment = (opportunity: SkontoOpportunity) => {
        setSelectedOpportunity(opportunity);
        setCreatePaymentOpen(true);
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-8">
                    <p className="text-center text-destructive">
                        Fehler beim Laden der Skonto-Möglichkeiten: {error.message}
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold tracking-tight">Skonto-Möglichkeiten</h2>
                <p className="text-muted-foreground">
                    Nutzen Sie Frühzahlerrabatte und sparen Sie bares Geld.
                </p>
            </div>

            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Offene Skonto</CardDescription>
                        <CardTitle className="text-2xl">{stats.total}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Mögliche Ersparnis</CardDescription>
                        <CardTitle className="text-2xl text-green-600">
                            {formatCurrency(stats.totalSavings)}
                        </CardTitle>
                    </CardHeader>
                </Card>
                <Card className={stats.urgent > 0 ? 'border-orange-500' : ''}>
                    <CardHeader className="pb-2">
                        <CardDescription>Dringend (&le; 3 Tage)</CardDescription>
                        <CardTitle className="text-2xl text-orange-600">{stats.urgent}</CardTitle>
                    </CardHeader>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardDescription>Diese Woche</CardDescription>
                        <CardTitle className="text-2xl">{stats.expiringSoon}</CardTitle>
                    </CardHeader>
                </Card>
            </div>

            {/* Urgent Alert */}
            {stats.urgent > 0 && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Dringende Skonto-Fristen</AlertTitle>
                    <AlertDescription>
                        {stats.urgent} Skonto-Möglichkeit{stats.urgent > 1 ? 'en' : ''} lauf{stats.urgent > 1 ? 'en' : 't'}{' '}
                        in den nächsten 3 Tagen ab. Handeln Sie jetzt, um die Ersparnis zu sichern!
                    </AlertDescription>
                </Alert>
            )}

            {/* Filter & Sort */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base">Filter & Sortierung</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex flex-wrap gap-4">
                        <div className="space-y-2">
                            <Label>Sortieren nach</Label>
                            <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortOption)}>
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="deadline">Frist (nächste zuerst)</SelectItem>
                                    <SelectItem value="amount">Ersparnis (höchste zuerst)</SelectItem>
                                    <SelectItem value="percent">Prozent (höchste zuerst)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Anzeige</Label>
                            <Select
                                value={showExpired ? 'all' : 'active'}
                                onValueChange={(v) => setShowExpired(v === 'all')}
                            >
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="active">Nur aktive</SelectItem>
                                    <SelectItem value="all">Inkl. abgelaufene</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Opportunities List */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Percent className="h-5 w-5" />
                        Skonto-Möglichkeiten ({sortedOpportunities.length})
                    </CardTitle>
                    <CardDescription>
                        Rechnungen mit Skonto-Option nach Frist sortiert.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-4">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-24 w-full" />
                            ))}
                        </div>
                    ) : sortedOpportunities.length === 0 ? (
                        <div className="py-8 text-center">
                            <Percent className="mx-auto h-12 w-12 text-muted-foreground/50" />
                            <h3 className="mt-4 text-lg font-semibold">Keine Skonto-Möglichkeiten</h3>
                            <p className="text-muted-foreground">
                                Aktuell gibt es keine offenen Rechnungen mit Skonto-Option.
                            </p>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            {sortedOpportunities.map((opportunity) => (
                                <SkontoOpportunityCard
                                    key={opportunity.document_id}
                                    opportunity={opportunity}
                                    onCreatePayment={handleCreatePayment}
                                />
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Create Payment Dialog */}
            {selectedOpportunity && (
                <CreatePaymentDialog
                    open={createPaymentOpen}
                    onOpenChange={setCreatePaymentOpen}
                    linkedDocumentId={selectedOpportunity.document_id}
                    prefillData={{
                        beneficiary_name: selectedOpportunity.beneficiary_name || '',
                        beneficiary_iban: selectedOpportunity.beneficiary_iban || '',
                        amount: selectedOpportunity.amount_with_skonto ?? selectedOpportunity.gross_amount,
                        reference: selectedOpportunity.invoice_number
                            ? `Rechnung ${selectedOpportunity.invoice_number} abzgl. ${selectedOpportunity.skonto_percent}% Skonto`
                            : `Zahlung abzgl. ${selectedOpportunity.skonto_percent}% Skonto`,
                    }}
                />
            )}
        </div>
    );
}
