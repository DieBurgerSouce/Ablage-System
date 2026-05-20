/**
 * Admin Mahnungen - Eskalation
 *
 * Zeigt Mahnvorgänge gruppiert nach Eskalationsstufe
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    TrendingUp,
    Mail,
    FileWarning,
    AlertTriangle,
    Gavel,
    Phone,
} from 'lucide-react';
import { DunningTable } from '@/features/banking/components/DunningTable';
import { useDunningRecords, useDunningStats } from '@/features/banking/hooks/use-banking-queries';
import { formatCurrency } from '@/features/banking/utils/format';

export const Route = createFileRoute('/admin/mahnungen/eskalation')({
    component: EskalationPage,
});

const LEVEL_CONFIG = [
    { level: 0, label: 'Neu', icon: Mail, color: 'bg-gray-100 text-gray-700' },
    { level: 1, label: 'Erinnerung', icon: Mail, color: 'bg-blue-100 text-blue-700' },
    { level: 2, label: '1. Mahnung', icon: FileWarning, color: 'bg-yellow-100 text-yellow-700' },
    { level: 3, label: '2. Mahnung', icon: Phone, color: 'bg-orange-100 text-orange-700' },
    { level: 4, label: 'Letzte Mahnung', icon: AlertTriangle, color: 'bg-red-100 text-red-700' },
    { level: 5, label: 'Inkasso', icon: Gavel, color: 'bg-red-200 text-red-800' },
];

function EskalationPage() {
    const { data: stats, isLoading: statsLoading } = useDunningStats();
    const { data: allRecords, isLoading: recordsLoading } = useDunningRecords({});

    const isLoading = statsLoading || recordsLoading;

    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-6">
                    {LEVEL_CONFIG.map((l) => (
                        <Skeleton key={l.level} className="h-24" />
                    ))}
                </div>
                <Skeleton className="h-[400px]" />
            </div>
        );
    }

    const byLevel = stats?.by_level ?? {};
    const records = allRecords?.items ?? [];

    return (
        <div className="space-y-6">
            {/* Level Overview Cards */}
            <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-6">
                {LEVEL_CONFIG.map((config) => {
                    const count = byLevel[config.level] ?? 0;
                    const levelRecords = records.filter((r) => r.dunning_level === config.level);
                    const totalAmount = levelRecords.reduce(
                        (sum, r) => sum + (r.outstanding_amount ?? 0),
                        0
                    );

                    return (
                        <Card key={config.level}>
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-2 mb-2">
                                    <div className={`p-2 rounded-lg ${config.color}`}>
                                        <config.icon className="h-4 w-4" />
                                    </div>
                                    <span className="font-medium text-sm">{config.label}</span>
                                </div>
                                <div className="text-2xl font-bold">{count}</div>
                                <div className="text-xs text-muted-foreground">
                                    {formatCurrency(totalAmount)}
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>

            {/* Tabs by Level */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <TrendingUp className="h-5 w-5" />
                        Eskalationsstufen
                    </CardTitle>
                    <CardDescription>
                        Mahnvorgänge nach Eskalationsstufe filtern
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs defaultValue="all">
                        <TabsList className="mb-4 flex-wrap">
                            <TabsTrigger value="all">
                                Alle
                                <Badge variant="secondary" className="ml-1.5">
                                    {records.length}
                                </Badge>
                            </TabsTrigger>
                            {LEVEL_CONFIG.map((config) => {
                                const count = byLevel[config.level] ?? 0;
                                if (count === 0) return null;
                                return (
                                    <TabsTrigger key={config.level} value={String(config.level)}>
                                        <config.icon className="h-3 w-3 mr-1" />
                                        {config.label}
                                        <Badge variant="secondary" className="ml-1.5">
                                            {count}
                                        </Badge>
                                    </TabsTrigger>
                                );
                            })}
                        </TabsList>

                        <TabsContent value="all">
                            <DunningTable data={records} />
                        </TabsContent>

                        {LEVEL_CONFIG.map((config) => (
                            <TabsContent key={config.level} value={String(config.level)}>
                                <DunningTable
                                    data={records.filter((r) => r.dunning_level === config.level)}
                                />
                            </TabsContent>
                        ))}
                    </Tabs>
                </CardContent>
            </Card>
        </div>
    );
}
