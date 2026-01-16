/**
 * TrendChart Component
 *
 * Zeigt einen Trend-Chart fuer Dokument-Aktivitaet ueber Zeit.
 * Verwendet Recharts fuer die Visualisierung.
 */

import { useMemo } from 'react';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp } from 'lucide-react';
import type { TrendDataPoint } from '../api/relationships-api';

// ==================== Types ====================

interface TrendChartProps {
    data: TrendDataPoint[];
    title?: string;
    description?: string;
    height?: number;
}

// ==================== Helper Functions ====================

function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
    });
}

function formatTooltipDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString('de-DE', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    });
}

// ==================== Custom Tooltip ====================

interface CustomTooltipProps {
    active?: boolean;
    payload?: Array<{ value: number }>;
    label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
    if (!active || !payload || !payload.length) {
        return null;
    }

    return (
        <div className="bg-background border rounded-lg shadow-lg p-3">
            <p className="text-sm font-medium">{label ? formatTooltipDate(label) : ''}</p>
            <p className="text-sm text-muted-foreground">
                <span className="font-semibold text-primary">{payload[0].value}</span> Dokumente
            </p>
        </div>
    );
}

// ==================== Component ====================

export function TrendChart({
    data,
    title = 'Dokument-Trend',
    description = 'Verknuepfte Dokumente pro Tag',
    height = 300,
}: TrendChartProps) {
    // Prepare chart data with formatted labels
    const chartData = useMemo(() => {
        return data.map((point) => ({
            ...point,
            label: formatDate(point.date),
        }));
    }, [data]);

    // Calculate summary stats
    const stats = useMemo(() => {
        if (!data.length) return { total: 0, avg: 0, max: 0 };

        const counts = data.map((d) => d.count);
        const total = counts.reduce((a, b) => a + b, 0);
        const avg = Math.round(total / counts.length);
        const max = Math.max(...counts);

        return { total, avg, max };
    }, [data]);

    if (!data.length) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                        <TrendingUp className="h-5 w-5" />
                        {title}
                    </CardTitle>
                    <CardDescription>{description}</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-center h-[200px] text-muted-foreground">
                        Keine Trend-Daten verfuegbar
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                    <div>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <TrendingUp className="h-5 w-5" />
                            {title}
                        </CardTitle>
                        <CardDescription>{description}</CardDescription>
                    </div>
                    <div className="flex gap-4 text-sm">
                        <div className="text-right">
                            <p className="text-muted-foreground text-xs">Gesamt</p>
                            <p className="font-semibold">{stats.total}</p>
                        </div>
                        <div className="text-right">
                            <p className="text-muted-foreground text-xs">Durchschnitt</p>
                            <p className="font-semibold">{stats.avg}/Tag</p>
                        </div>
                        <div className="text-right">
                            <p className="text-muted-foreground text-xs">Maximum</p>
                            <p className="font-semibold">{stats.max}</p>
                        </div>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pt-0">
                <ResponsiveContainer width="100%" height={height}>
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid
                            strokeDasharray="3 3"
                            vertical={false}
                            stroke="hsl(var(--border))"
                        />
                        <XAxis
                            dataKey="date"
                            tickFormatter={formatDate}
                            tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                            tickLine={false}
                            axisLine={false}
                            interval="preserveStartEnd"
                        />
                        <YAxis
                            tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                            tickLine={false}
                            axisLine={false}
                            width={40}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Area
                            type="monotone"
                            dataKey="count"
                            stroke="hsl(var(--primary))"
                            strokeWidth={2}
                            fill="url(#colorCount)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}

export default TrendChart;
