/**
 * Cash-Flow Chart Komponente
 * Zeigt tägliche Einnahmen, Ausgaben und Netto als AreaChart
 *
 * WICHTIG: Verwendet CSS-Variablen fuer Display-Mode-Unterstuetzung:
 * - --chart-2: Einnahmen (gruen/success)
 * - --chart-4: Ausgaben (rot/destructive)
 * - --chart-1: Kumuliert (blau/primary)
 */

import { useState, useMemo } from 'react';
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
    type TooltipProps,
} from 'recharts';
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent';
import { useCashFlowDaily } from '../hooks/use-banking-queries';
import { formatCurrency, formatDateShort } from '../utils/format';

import { useTheme } from '@/lib/theme/ThemeContext';

/**
 * Hook to get computed CSS variable values for charts
 * This ensures chart colors adapt to display mode changes
 */
function useChartColors() {
    const { displayMode } = useTheme();

    return useMemo(() => {
        // Read CSS variables from the document root
        const computedStyle = getComputedStyle(document.documentElement);

        // Get chart colors, with fallbacks for safety
        const getColor = (varName: string, fallback: string): string => {
            const value = computedStyle.getPropertyValue(varName).trim();
            return value || fallback;
        };

        return {
            inflow: getColor('--chart-2', 'oklch(0.72 0.17 145)'),   // Green for income
            outflow: getColor('--chart-4', 'oklch(0.55 0.22 25)'),   // Red for expenses
            cumulative: getColor('--chart-1', 'oklch(0.55 0.18 250)'), // Blue for cumulative
        };
    }, [displayMode]); // Re-compute when display mode changes
}

interface CashFlowChartProps {
    defaultDays?: number;
    showControls?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RechartsTooltipProps = TooltipProps<ValueType, NameType> & { payload?: any[]; label?: string };

function CustomTooltip({ active, payload, label }: RechartsTooltipProps) {
    if (!active || !payload || !label) return null;

    return (
        <div className="rounded-lg border bg-background p-3 shadow-md">
            <p className="font-medium mb-2">{formatDateShort(String(label))}</p>
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

export function CashFlowChart({ defaultDays = 30, showControls = true }: CashFlowChartProps) {
    const [days, setDays] = useState(defaultDays);
    const { data, isLoading, error } = useCashFlowDaily(days);
    const chartColors = useChartColors();

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
                <div
                    className="h-[300px]"
                    role="img"
                    aria-label={`Liquiditaetsprognose fuer ${days} Tage. Zeigt Einnahmen, Ausgaben und kumulierten Saldo als Flaechendiagramm.`}
                >
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                            <defs>
                                <linearGradient id="colorInflow" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor={chartColors.inflow} stopOpacity={0.3} />
                                    <stop offset="95%" stopColor={chartColors.inflow} stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorOutflow" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor={chartColors.outflow} stopOpacity={0.3} />
                                    <stop offset="95%" stopColor={chartColors.outflow} stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorNet" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor={chartColors.cumulative} stopOpacity={0.3} />
                                    <stop offset="95%" stopColor={chartColors.cumulative} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis
                                dataKey="date"
                                tickFormatter={formatDateShort}
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
                                stroke={chartColors.inflow}
                                fill="url(#colorInflow)"
                                strokeWidth={2}
                            />
                            <Area
                                type="monotone"
                                dataKey="Ausgaben"
                                stroke={chartColors.outflow}
                                fill="url(#colorOutflow)"
                                strokeWidth={2}
                            />
                            <Area
                                type="monotone"
                                dataKey="Kumuliert"
                                stroke={chartColors.cumulative}
                                fill="url(#colorNet)"
                                strokeWidth={2}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
                {/* Screen Reader Only: Data Table Alternative */}
                <table className="sr-only" aria-label="Liquiditaetsdaten als Tabelle">
                    <caption>Tagesweise Einnahmen, Ausgaben und kumulierter Saldo</caption>
                    <thead>
                        <tr>
                            <th scope="col">Datum</th>
                            <th scope="col">Einnahmen</th>
                            <th scope="col">Ausgaben</th>
                            <th scope="col">Kumuliert</th>
                        </tr>
                    </thead>
                    <tbody>
                        {chartData.map((entry, index) => (
                            <tr key={index}>
                                <td>{formatDateShort(entry.date)}</td>
                                <td>{formatCurrency(entry.Einnahmen)}</td>
                                <td>{formatCurrency(entry.Ausgaben)}</td>
                                <td>{formatCurrency(entry.Kumuliert)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </CardContent>
        </Card>
    );
}
