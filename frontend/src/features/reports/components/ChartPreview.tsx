/**
 * ChartPreview Component
 *
 * Rendert verschiedene Chart-Typen basierend auf Report-Daten.
 * Unterstützt: Bar, Line, Pie, Area, Stacked Bar
 */

import { useMemo } from 'react';
import {
    BarChart,
    Bar,
    LineChart,
    Line,
    PieChart,
    Pie,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Cell,
    type TooltipProps,
} from 'recharts';
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useTheme } from '@/lib/theme/ThemeContext';
import type { ReportChart, ReportPreview } from '../types';

// =============================================================================
// Types
// =============================================================================

interface ChartPreviewProps {
    chart: ReportChart;
    data: ReportPreview | undefined;
    isLoading?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RechartsTooltipProps = TooltipProps<ValueType, NameType> & { payload?: any[]; label?: string };

// =============================================================================
// Default Colors
// =============================================================================

const DEFAULT_COLORS = [
    'oklch(0.55 0.18 250)',   // blue
    'oklch(0.72 0.17 145)',   // green
    'oklch(0.55 0.22 25)',    // red
    'oklch(0.70 0.15 65)',    // orange
    'oklch(0.60 0.16 290)',   // purple
    'oklch(0.65 0.12 180)',   // teal
    'oklch(0.75 0.14 80)',    // yellow
    'oklch(0.50 0.20 320)',   // pink
];

// =============================================================================
// Chart Colors Hook
// =============================================================================

function useChartColors() {
    // displayMode used to trigger recompute when theme changes
    useTheme();

    return useMemo(() => {
        const computedStyle = getComputedStyle(document.documentElement);

        const getColor = (varName: string, fallback: string): string => {
            const value = computedStyle.getPropertyValue(varName).trim();
            return value || fallback;
        };

        return {
            primary: getColor('--chart-1', DEFAULT_COLORS[0]),
            secondary: getColor('--chart-2', DEFAULT_COLORS[1]),
            accent: getColor('--chart-3', DEFAULT_COLORS[2]),
            muted: getColor('--chart-4', DEFAULT_COLORS[3]),
            palette: DEFAULT_COLORS,
        };
    }, []);
}

// =============================================================================
// Custom Tooltip
// =============================================================================

function CustomTooltip({ active, payload, label }: RechartsTooltipProps) {
    if (!active || !payload) return null;

    return (
        <div className="rounded-lg border bg-background p-3 shadow-md">
            {label && <p className="font-medium mb-2">{String(label)}</p>}
            {payload.map((entry: { name?: string; value?: number; color?: string }, index: number) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                    <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-muted-foreground">{entry.name}:</span>
                    <span className="font-medium">
                        {typeof entry.value === 'number'
                            ? entry.value.toLocaleString('de-DE')
                            : entry.value}
                    </span>
                </div>
            ))}
        </div>
    );
}

// =============================================================================
// Data Transformation
// =============================================================================

function transformChartData(
    chart: ReportChart,
    preview: ReportPreview | undefined
): Record<string, unknown>[] {
    if (!preview?.data || !chart.x_axis_field) return [];

    const xField = chart.x_axis_field;
    const yField = chart.y_axis_field;
    const groupField = chart.group_by_field;

    if (groupField) {
        // Gruppierte Daten für gestapelte Charts
        const grouped = new Map<string, Record<string, unknown>>();

        preview.data.forEach(row => {
            const xValue = String(row[xField] ?? 'Unbekannt');
            const groupValue = String(row[groupField] ?? 'Sonstige');
            const yValue = yField ? Number(row[yField]) || 0 : 1;

            if (!grouped.has(xValue)) {
                grouped.set(xValue, { name: xValue });
            }

            const existing = grouped.get(xValue)!;
            const currentValue = (existing[groupValue] as number) || 0;
            existing[groupValue] = currentValue + yValue;
        });

        return Array.from(grouped.values());
    }

    // Einfache Aggregation
    if (chart.aggregation && chart.aggregation !== 'none') {
        const aggregated = new Map<string, { sum: number; count: number; min: number; max: number }>();

        preview.data.forEach(row => {
            const xValue = String(row[xField] ?? 'Unbekannt');
            const yValue = yField ? Number(row[yField]) || 0 : 1;

            if (!aggregated.has(xValue)) {
                aggregated.set(xValue, { sum: 0, count: 0, min: Infinity, max: -Infinity });
            }

            const agg = aggregated.get(xValue)!;
            agg.sum += yValue;
            agg.count += 1;
            agg.min = Math.min(agg.min, yValue);
            agg.max = Math.max(agg.max, yValue);
        });

        return Array.from(aggregated.entries()).map(([name, agg]) => {
            let value: number;
            switch (chart.aggregation) {
                case 'sum':
                    value = agg.sum;
                    break;
                case 'avg':
                    value = agg.count > 0 ? agg.sum / agg.count : 0;
                    break;
                case 'count':
                    value = agg.count;
                    break;
                case 'min':
                    value = agg.min === Infinity ? 0 : agg.min;
                    break;
                case 'max':
                    value = agg.max === -Infinity ? 0 : agg.max;
                    break;
                default:
                    value = agg.sum;
            }
            return { name, value };
        });
    }

    // Direktes Mapping ohne Aggregation
    return preview.data.map(row => ({
        name: String(row[xField] ?? ''),
        value: yField ? Number(row[yField]) || 0 : 1,
    }));
}

function getUniqueGroups(
    chart: ReportChart,
    preview: ReportPreview | undefined
): string[] {
    if (!preview?.data || !chart.group_by_field) return [];

    const groups = new Set<string>();
    preview.data.forEach(row => {
        const groupValue = String(row[chart.group_by_field!] ?? 'Sonstige');
        groups.add(groupValue);
    });

    return Array.from(groups);
}

// =============================================================================
// Chart Renderers
// =============================================================================

interface ChartRendererProps {
    data: Record<string, unknown>[];
    chart: ReportChart;
    colors: ReturnType<typeof useChartColors>;
    groups?: string[];
}

function BarChartRenderer({ data, chart, colors, groups }: ChartRendererProps) {
    const isStacked = chart.chart_type === 'stacked_bar';
    const showLegend = chart.styling?.show_legend !== false;
    const colorPalette = chart.styling?.colors || colors.palette;

    return (
        <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                />
                <YAxis
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                    tickFormatter={(v) => v.toLocaleString('de-DE')}
                />
                <Tooltip content={<CustomTooltip />} />
                {showLegend && <Legend />}

                {groups && groups.length > 0 ? (
                    groups.map((group, index) => (
                        <Bar
                            key={group}
                            dataKey={group}
                            stackId={isStacked ? 'stack' : undefined}
                            fill={colorPalette[index % colorPalette.length]}
                        />
                    ))
                ) : (
                    <Bar dataKey="value" fill={colors.primary}>
                        {chart.styling?.show_data_labels && data.map((_, index) => (
                            <Cell key={index} fill={colorPalette[index % colorPalette.length]} />
                        ))}
                    </Bar>
                )}
            </BarChart>
        </ResponsiveContainer>
    );
}

function LineChartRenderer({ data, chart, colors, groups }: ChartRendererProps) {
    const showLegend = chart.styling?.show_legend !== false;
    const colorPalette = chart.styling?.colors || colors.palette;

    return (
        <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                />
                <YAxis
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                    tickFormatter={(v) => v.toLocaleString('de-DE')}
                />
                <Tooltip content={<CustomTooltip />} />
                {showLegend && <Legend />}

                {groups && groups.length > 0 ? (
                    groups.map((group, index) => (
                        <Line
                            key={group}
                            type="monotone"
                            dataKey={group}
                            stroke={colorPalette[index % colorPalette.length]}
                            strokeWidth={2}
                            dot={{ r: 4 }}
                        />
                    ))
                ) : (
                    <Line
                        type="monotone"
                        dataKey="value"
                        stroke={colors.primary}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                    />
                )}
            </LineChart>
        </ResponsiveContainer>
    );
}

function AreaChartRenderer({ data, chart, colors, groups }: ChartRendererProps) {
    const showLegend = chart.styling?.show_legend !== false;
    const isStacked = chart.styling?.stacked !== false;
    const colorPalette = chart.styling?.colors || colors.palette;

    return (
        <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
                <defs>
                    {(groups || ['value']).map((key, index) => (
                        <linearGradient key={key} id={`gradient-${key}`} x1="0" y1="0" x2="0" y2="1">
                            <stop
                                offset="5%"
                                stopColor={colorPalette[index % colorPalette.length]}
                                stopOpacity={0.3}
                            />
                            <stop
                                offset="95%"
                                stopColor={colorPalette[index % colorPalette.length]}
                                stopOpacity={0}
                            />
                        </linearGradient>
                    ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                    dataKey="name"
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                />
                <YAxis
                    tick={{ fontSize: 12 }}
                    tickMargin={8}
                    tickFormatter={(v) => v.toLocaleString('de-DE')}
                />
                <Tooltip content={<CustomTooltip />} />
                {showLegend && <Legend />}

                {groups && groups.length > 0 ? (
                    groups.map((group, index) => (
                        <Area
                            key={group}
                            type="monotone"
                            dataKey={group}
                            stackId={isStacked ? 'stack' : undefined}
                            stroke={colorPalette[index % colorPalette.length]}
                            fill={`url(#gradient-${group})`}
                            strokeWidth={2}
                        />
                    ))
                ) : (
                    <Area
                        type="monotone"
                        dataKey="value"
                        stroke={colors.primary}
                        fill="url(#gradient-value)"
                        strokeWidth={2}
                    />
                )}
            </AreaChart>
        </ResponsiveContainer>
    );
}

function PieChartRenderer({ data, chart, colors }: ChartRendererProps) {
    const showLegend = chart.styling?.show_legend !== false;
    const showLabels = chart.styling?.show_data_labels !== false;
    const colorPalette = chart.styling?.colors || colors.palette;
    const legendPosition = chart.styling?.legend_position || 'right';

    return (
        <ResponsiveContainer width="100%" height="100%">
            <PieChart>
                <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={showLabels ? ({ name, percent }) =>
                        `${name}: ${((percent ?? 0) * 100).toFixed(0)}%` : undefined
                    }
                    labelLine={showLabels}
                >
                    {data.map((_, index) => (
                        <Cell
                            key={`cell-${index}`}
                            fill={colorPalette[index % colorPalette.length]}
                        />
                    ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
                {showLegend && (
                    <Legend
                        layout={legendPosition === 'top' || legendPosition === 'bottom' ? 'horizontal' : 'vertical'}
                        align={legendPosition === 'left' ? 'left' : legendPosition === 'right' ? 'right' : 'center'}
                        verticalAlign={legendPosition === 'top' ? 'top' : legendPosition === 'bottom' ? 'bottom' : 'middle'}
                    />
                )}
            </PieChart>
        </ResponsiveContainer>
    );
}

// =============================================================================
// Main Component
// =============================================================================

export function ChartPreview({ chart, data, isLoading }: ChartPreviewProps) {
    const colors = useChartColors();

    const chartData = useMemo(
        () => transformChartData(chart, data),
        [chart, data]
    );

    const groups = useMemo(
        () => getUniqueGroups(chart, data),
        [chart, data]
    );

    if (isLoading) {
        return (
            <Card>
                <CardHeader className="pb-2">
                    <Skeleton className="h-5 w-32" />
                    <Skeleton className="h-4 w-48" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[250px] w-full" />
                </CardContent>
            </Card>
        );
    }

    if (!data || chartData.length === 0) {
        return (
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm">{chart.title || 'Chart'}</CardTitle>
                    {chart.description && (
                        <CardDescription>{chart.description}</CardDescription>
                    )}
                </CardHeader>
                <CardContent>
                    <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                        Keine Daten verfügbar
                    </div>
                </CardContent>
            </Card>
        );
    }

    const rendererProps: ChartRendererProps = {
        data: chartData,
        chart,
        colors,
        groups: groups.length > 0 ? groups : undefined,
    };

    return (
        <Card>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm">{chart.title || 'Chart'}</CardTitle>
                {chart.description && (
                    <CardDescription>{chart.description}</CardDescription>
                )}
            </CardHeader>
            <CardContent>
                <div
                    className="h-[250px]"
                    role="img"
                    aria-label={`${chart.chart_type} Chart: ${chart.title || 'Datenvisualisierung'}`}
                >
                    {chart.chart_type === 'bar' && <BarChartRenderer {...rendererProps} />}
                    {chart.chart_type === 'stacked_bar' && <BarChartRenderer {...rendererProps} />}
                    {chart.chart_type === 'line' && <LineChartRenderer {...rendererProps} />}
                    {chart.chart_type === 'area' && <AreaChartRenderer {...rendererProps} />}
                    {chart.chart_type === 'pie' && <PieChartRenderer {...rendererProps} />}
                </div>
            </CardContent>
        </Card>
    );
}

export default ChartPreview;
