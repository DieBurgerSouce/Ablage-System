/**
 * Cash-Flow Szenario-Vergleich
 * Zeigt Optimistisch/Realistisch/Pessimistisch als RadarChart
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    Radar,
    Legend,
    ResponsiveContainer,
    Tooltip,
} from 'recharts';
import { useCashFlowScenarios } from '../hooks/use-banking-queries';
import { TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import { formatCurrency } from '../utils/format';

interface CashFlowScenariosProps {
    daysAhead?: number;
}

export function CashFlowScenarios({ daysAhead = 90 }: CashFlowScenariosProps) {
    const { data, isLoading, error } = useCashFlowScenarios(daysAhead);

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
                    <CardTitle>Szenario-Vergleich</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    // Normalisiere Werte für RadarChart (auf 0-100 Skala)
    // NaN-Protection: Falls alle Werte 0 sind, verwende Fallback
    const maxInflow = Math.max(
        data.optimistic.total_inflow,
        data.realistic.total_inflow,
        data.pessimistic.total_inflow,
        1 // Fallback um Division durch 0 zu verhindern
    );
    const maxOutflow = Math.max(
        data.optimistic.total_outflow,
        data.realistic.total_outflow,
        data.pessimistic.total_outflow,
        1 // Fallback um Division durch 0 zu verhindern
    );
    const maxBalance = Math.max(
        Math.abs(data.optimistic.min_balance),
        Math.abs(data.realistic.min_balance),
        Math.abs(data.pessimistic.min_balance),
        1 // Fallback um Division durch 0 zu verhindern
    );

    // Sichere Normalisierung mit NaN-Schutz
    const safeNormalize = (value: number, max: number): number => {
        if (max === 0 || !isFinite(value) || !isFinite(max)) return 50;
        return (value / max) * 100;
    };

    const chartData = [
        {
            metric: 'Einnahmen',
            Optimistisch: safeNormalize(data.optimistic.total_inflow, maxInflow),
            Realistisch: safeNormalize(data.realistic.total_inflow, maxInflow),
            Pessimistisch: safeNormalize(data.pessimistic.total_inflow, maxInflow),
        },
        {
            metric: 'Ausgaben',
            Optimistisch: safeNormalize(data.optimistic.total_outflow, maxOutflow),
            Realistisch: safeNormalize(data.realistic.total_outflow, maxOutflow),
            Pessimistisch: safeNormalize(data.pessimistic.total_outflow, maxOutflow),
        },
        {
            metric: 'Min. Saldo',
            Optimistisch: maxBalance > 0 ? ((data.optimistic.min_balance + maxBalance) / (2 * maxBalance)) * 100 : 50,
            Realistisch: maxBalance > 0 ? ((data.realistic.min_balance + maxBalance) / (2 * maxBalance)) * 100 : 50,
            Pessimistisch: maxBalance > 0 ? ((data.pessimistic.min_balance + maxBalance) / (2 * maxBalance)) * 100 : 50,
        },
        {
            metric: 'Risikotage',
            Optimistisch: daysAhead > 0 ? 100 - (data.optimistic.days_negative / daysAhead) * 100 : 100,
            Realistisch: daysAhead > 0 ? 100 - (data.realistic.days_negative / daysAhead) * 100 : 100,
            Pessimistisch: daysAhead > 0 ? 100 - (data.pessimistic.days_negative / daysAhead) * 100 : 100,
        },
    ];

    return (
        <Card>
            <CardHeader>
                <CardTitle>Szenario-Vergleich</CardTitle>
                <CardDescription>
                    Prognose für die nächsten {daysAhead} Tage in drei Szenarien
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* RadarChart */}
                    <div className="h-[250px] sm:h-[300px] min-h-[250px]" role="img" aria-label="Radar-Chart Szenario-Vergleich">
                        <ResponsiveContainer width="100%" height="100%">
                            <RadarChart data={chartData}>
                                <PolarGrid className="stroke-muted" />
                                <PolarAngleAxis
                                    dataKey="metric"
                                    tick={{ fontSize: 12 }}
                                />
                                <PolarRadiusAxis
                                    angle={30}
                                    domain={[0, 100]}
                                    tick={false}
                                />
                                <Radar
                                    name="Optimistisch"
                                    dataKey="Optimistisch"
                                    stroke="#22c55e"
                                    fill="#22c55e"
                                    fillOpacity={0.2}
                                />
                                <Radar
                                    name="Realistisch"
                                    dataKey="Realistisch"
                                    stroke="#3b82f6"
                                    fill="#3b82f6"
                                    fillOpacity={0.2}
                                />
                                <Radar
                                    name="Pessimistisch"
                                    dataKey="Pessimistisch"
                                    stroke="#ef4444"
                                    fill="#ef4444"
                                    fillOpacity={0.2}
                                />
                                <Tooltip />
                                <Legend />
                            </RadarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Szenario-Details */}
                    <div className="space-y-4">
                        {/* Optimistisch */}
                        <div className="p-4 rounded-lg border border-green-200 bg-green-50 dark:bg-green-950 dark:border-green-800">
                            <div className="flex items-center gap-2 mb-2">
                                <TrendingUp className="h-4 w-4 text-green-600" />
                                <span className="font-medium text-green-700 dark:text-green-400">Optimistisch</span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                                <div>
                                    <span className="text-muted-foreground">Netto:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.optimistic.net_flow)}</span>
                                </div>
                                <div>
                                    <span className="text-muted-foreground">Min. Saldo:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.optimistic.min_balance)}</span>
                                </div>
                            </div>
                            {data.optimistic.days_negative > 0 && (
                                <Badge variant="outline" className="mt-2">
                                    {data.optimistic.days_negative} Tage negativ
                                </Badge>
                            )}
                        </div>

                        {/* Realistisch */}
                        <div className="p-4 rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-800">
                            <div className="flex items-center gap-2 mb-2">
                                <TrendingUp className="h-4 w-4 text-blue-600 rotate-[-15deg]" />
                                <span className="font-medium text-blue-700 dark:text-blue-400">Realistisch</span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                                <div>
                                    <span className="text-muted-foreground">Netto:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.realistic.net_flow)}</span>
                                </div>
                                <div>
                                    <span className="text-muted-foreground">Min. Saldo:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.realistic.min_balance)}</span>
                                </div>
                            </div>
                            {data.realistic.days_negative > 0 && (
                                <Badge variant="secondary" className="mt-2">
                                    {data.realistic.days_negative} Tage negativ
                                </Badge>
                            )}
                        </div>

                        {/* Pessimistisch */}
                        <div className="p-4 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950 dark:border-red-800">
                            <div className="flex items-center gap-2 mb-2">
                                <TrendingDown className="h-4 w-4 text-red-600" />
                                <span className="font-medium text-red-700 dark:text-red-400">Pessimistisch</span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                                <div>
                                    <span className="text-muted-foreground">Netto:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.pessimistic.net_flow)}</span>
                                </div>
                                <div>
                                    <span className="text-muted-foreground">Min. Saldo:</span>
                                    <span className="ml-2 font-medium">{formatCurrency(data.pessimistic.min_balance)}</span>
                                </div>
                            </div>
                            {data.pessimistic.days_negative > 0 && (
                                <Badge variant="destructive" className="mt-2">
                                    <AlertTriangle className="h-3 w-3 mr-1" />
                                    {data.pessimistic.days_negative} Tage negativ
                                </Badge>
                            )}
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
