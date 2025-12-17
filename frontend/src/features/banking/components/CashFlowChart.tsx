/**
 * Cash-Flow Chart Komponente
 * Zeigt taegliche Einnahmen, Ausgaben und Netto als AreaChart
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from 'recharts';
import { useCashFlowDaily } from '../hooks/use-banking-queries';

interface CashFlowChartProps {
    defaultDays?: number;
    showControls?: boolean;
}

function formatCurrency(value: number): string {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
}

function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat('de-DE', {
        day: '2-digit',
        month: '2-digit',
    }).format(date);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload) return null;

    return (
        <div className="rounded-lg border bg-background p-3 shadow-md">
            <p className="font-medium mb-2">{formatDate(label)}</p>
            {payload.map((entry: { name: string; value: number; color: string }, index: number) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                    <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-muted-foreground">{entry.name}:</span>
                    <span className="font-medium">{formatCurrency(entry.value)}</span>
                </div>
            ))}
        </div>
    );
}

export function CashFlowChart({ defaultDays = 30, showControls = true }: CashFlowChartProps) {
    const [days, setDays] = useState(defaultDays);
    const { data, isLoading, error } = useCashFlowDaily(days);

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

    if (error) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Liquiditätsprognose</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    const chartData = data?.map((entry) => ({
        date: entry.date,
        Einnahmen: entry.inflow,
        Ausgaben: entry.outflow,
        Netto: entry.net,
        Kumuliert: entry.cumulative,
    })) ?? [];

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>Liquiditätsprognose</CardTitle>
                    <CardDescription>
                        Tägliche Ein- und Ausgaben der nächsten {days} Tage
                    </CardDescription>
                </div>
                {showControls && (
                    <Select value={days.toString()} onValueChange={(v) => setDays(parseInt(v))}>
                        <SelectTrigger className="w-[120px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="7">7 Tage</SelectItem>
                            <SelectItem value="14">14 Tage</SelectItem>
                            <SelectItem value="30">30 Tage</SelectItem>
                            <SelectItem value="60">60 Tage</SelectItem>
                            <SelectItem value="90">90 Tage</SelectItem>
                        </SelectContent>
                    </Select>
                )}
            </CardHeader>
            <CardContent>
                <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                            <defs>
                                <linearGradient id="colorInflow" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorOutflow" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorNet" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis
                                dataKey="date"
                                tickFormatter={formatDate}
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
                            <Area
                                type="monotone"
                                dataKey="Einnahmen"
                                stroke="#22c55e"
                                fill="url(#colorInflow)"
                                strokeWidth={2}
                            />
                            <Area
                                type="monotone"
                                dataKey="Ausgaben"
                                stroke="#ef4444"
                                fill="url(#colorOutflow)"
                                strokeWidth={2}
                            />
                            <Area
                                type="monotone"
                                dataKey="Kumuliert"
                                stroke="#3b82f6"
                                fill="url(#colorNet)"
                                strokeWidth={2}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    );
}
