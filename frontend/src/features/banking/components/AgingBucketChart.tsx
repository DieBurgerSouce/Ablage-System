/**
 * Aging Bucket Chart
 * Zeigt Altersstruktur als BarChart mit 5 Buckets
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
    type TooltipProps,
} from 'recharts';
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent';
import { useAgingSummary } from '../hooks/use-banking-queries';
import { formatCurrency } from '../utils/format';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RechartsTooltipProps = TooltipProps<ValueType, NameType> & { payload?: any[]; label?: string };

const BUCKET_LABELS: Record<string, string> = {
    'current': 'Aktuell',
    '1-30': '1-30 Tage',
    '31-60': '31-60 Tage',
    '61-90': '61-90 Tage',
    '90+': '90+ Tage',
};

function CustomTooltip({ active, payload, label }: RechartsTooltipProps) {
    if (!active || !payload || !label) return null;

    return (
        <div className="rounded-lg border bg-background p-3 shadow-md">
            <p className="font-medium mb-2">{String(label)}</p>
            {payload.map((entry: { name?: string; value?: number; color?: string }, index: number) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                    <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-muted-foreground">{entry.name}:</span>
                    <span className="font-medium">{formatCurrency(Number(entry.value))}</span>
                </div>
            ))}
        </div>
    );
}

export function AgingBucketChart() {
    const { data, isLoading, error } = useAgingSummary();

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[300px] w-full" />
                </CardContent>
            </Card>
        );
    }

    if (error || !data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Altersstruktur</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    // Kombiniere Forderungen und Verbindlichkeiten nach Bucket
    const bucketOrder = ['current', '1-30', '31-60', '61-90', '90+'];
    const receivablesMap = new Map(data.receivables.buckets.map((b) => [b.bucket, b.amount]));
    const payablesMap = new Map(data.payables.buckets.map((b) => [b.bucket, b.amount]));

    const chartData = bucketOrder.map((bucket) => ({
        bucket: BUCKET_LABELS[bucket] || bucket,
        Forderungen: receivablesMap.get(bucket) ?? 0,
        Verbindlichkeiten: payablesMap.get(bucket) ?? 0,
    }));

    return (
        <Card>
            <CardHeader>
                <CardTitle>Altersstruktur</CardTitle>
                <CardDescription>
                    Forderungen und Verbindlichkeiten nach Überfälligkeit
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="h-[300px]" role="img" aria-label="Balkendiagramm: Forderungen und Verbindlichkeiten nach Altersstruktur">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis
                                dataKey="bucket"
                                tick={{ fontSize: 12 }}
                                tickMargin={8}
                            />
                            <YAxis
                                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                                tick={{ fontSize: 12 }}
                                tickMargin={8}
                            />
                            <Tooltip content={<CustomTooltip />} />
                            <Legend />
                            <Bar
                                dataKey="Forderungen"
                                fill="#22c55e"
                                radius={[4, 4, 0, 0]}
                            />
                            <Bar
                                dataKey="Verbindlichkeiten"
                                fill="#ef4444"
                                radius={[4, 4, 0, 0]}
                            />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    );
}
