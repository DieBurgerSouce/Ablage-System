/**
 * Liquiditätsprognose Komponente
 * Zeigt Rolling-Window Prognosen (30/60/90 Tage), Wasserfall-Chart,
 * Engpass-Warnungen und Anomalie-Erkennung
 *
 * Teil von Phase 1.4: LiquidityForecastService
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
    ReferenceLine,
    type TooltipProps,
} from 'recharts';
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent';
import {
    useLiquidityForecast,
    useLiquidityBottlenecks,
    useWaterfallChart,
    usePaymentAnomalies,
} from '../hooks/use-banking-queries';
import { formatCurrency, formatDate, formatPercent } from '../utils/format';
import {
    AlertTriangle,
    TrendingUp,
    TrendingDown,
    Shield,
    AlertCircle,
    Activity,
    ChevronRight,
    RefreshCw,
    Info,
} from 'lucide-react';
import { useTheme } from '@/lib/theme/ThemeContext';
import type {
    LiquidityRiskLevel,
    RollingForecast,
    LiquidityBottleneck,
    PaymentAnomaly,
    WaterfallChartData,
} from '@/lib/api/services/banking';

// ==================== Risk Level Styling ====================

const RISK_LEVEL_CONFIG: Record<LiquidityRiskLevel, {
    label: string;
    icon: typeof Shield;
    color: string;
    bgColor: string;
    borderColor: string;
    textColor: string;
}> = {
    healthy: {
        label: 'Gesund',
        icon: Shield,
        color: '#22c55e',
        bgColor: 'bg-green-50 dark:bg-green-950',
        borderColor: 'border-green-200 dark:border-green-800',
        textColor: 'text-green-700 dark:text-green-400',
    },
    adequate: {
        label: 'Ausreichend',
        icon: TrendingUp,
        color: '#84cc16',
        bgColor: 'bg-lime-50 dark:bg-lime-950',
        borderColor: 'border-lime-200 dark:border-lime-800',
        textColor: 'text-lime-700 dark:text-lime-400',
    },
    caution: {
        label: 'Vorsicht',
        icon: AlertCircle,
        color: '#eab308',
        bgColor: 'bg-yellow-50 dark:bg-yellow-950',
        borderColor: 'border-yellow-200 dark:border-yellow-800',
        textColor: 'text-yellow-700 dark:text-yellow-400',
    },
    warning: {
        label: 'Warnung',
        icon: AlertTriangle,
        color: '#f97316',
        bgColor: 'bg-orange-50 dark:bg-orange-950',
        borderColor: 'border-orange-200 dark:border-orange-800',
        textColor: 'text-orange-700 dark:text-orange-400',
    },
    critical: {
        label: 'Kritisch',
        icon: TrendingDown,
        color: '#ef4444',
        bgColor: 'bg-red-50 dark:bg-red-950',
        borderColor: 'border-red-200 dark:border-red-800',
        textColor: 'text-red-700 dark:text-red-400',
    },
};

// ==================== Chart Colors Hook ====================

function useChartColors() {
    const { displayMode } = useTheme();

    return useMemo(() => {
        const computedStyle = getComputedStyle(document.documentElement);
        const getColor = (varName: string, fallback: string): string => {
            const value = computedStyle.getPropertyValue(varName).trim();
            return value || fallback;
        };

        return {
            inflow: getColor('--chart-2', '#22c55e'),
            outflow: getColor('--chart-4', '#ef4444'),
            balance: getColor('--chart-1', '#3b82f6'),
            warning: getColor('--chart-3', '#f97316'),
            neutral: getColor('--muted-foreground', '#6b7280'),
        };
    }, [displayMode]);
}

// ==================== Waterfall Chart Custom Tooltip ====================

interface WaterfallTooltipProps extends TooltipProps<ValueType, NameType> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    payload?: any[];
    label?: string;
}

function WaterfallTooltip({ active, payload, label }: WaterfallTooltipProps) {
    if (!active || !payload || !label) return null;

    const data = payload[0]?.payload as WaterfallChartData | undefined;
    if (!data) return null;

    return (
        <div className="rounded-lg border bg-background p-3 shadow-md">
            <p className="font-medium mb-2">{data.label || formatDate(data.date)}</p>
            <div className="space-y-1 text-sm">
                <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">Anfangssaldo:</span>
                    <span className="font-medium">{formatCurrency(data.starting_balance)}</span>
                </div>
                {data.inflow > 0 && (
                    <div className="flex justify-between gap-4">
                        <span className="text-green-600">+ Einnahmen:</span>
                        <span className="font-medium text-green-600">{formatCurrency(data.inflow)}</span>
                    </div>
                )}
                {data.outflow > 0 && (
                    <div className="flex justify-between gap-4">
                        <span className="text-red-600">- Ausgaben:</span>
                        <span className="font-medium text-red-600">{formatCurrency(data.outflow)}</span>
                    </div>
                )}
                <div className="flex justify-between gap-4 pt-1 border-t">
                    <span className="text-muted-foreground">Endsaldo:</span>
                    <span className={`font-medium ${data.ending_balance < 0 ? 'text-red-600' : ''}`}>
                        {formatCurrency(data.ending_balance)}
                    </span>
                </div>
            </div>
        </div>
    );
}

// ==================== Risk Level Badge ====================

function RiskLevelBadge({ level }: { level: LiquidityRiskLevel }) {
    const config = RISK_LEVEL_CONFIG[level];
    const Icon = config.icon;

    return (
        <Badge
            variant="outline"
            className={`${config.bgColor} ${config.borderColor} ${config.textColor} gap-1`}
        >
            <Icon className="h-3 w-3" />
            {config.label}
        </Badge>
    );
}

// ==================== Forecast Card Component ====================

interface ForecastCardProps {
    forecast: RollingForecast;
    periodLabel: string;
}

function ForecastCard({ forecast, periodLabel }: ForecastCardProps) {
    const config = RISK_LEVEL_CONFIG[forecast.risk_level];
    const Icon = config.icon;
    const netFlow = forecast.expected_net_flow;
    const isPositive = netFlow >= 0;

    return (
        <div className={`p-4 rounded-lg border ${config.borderColor} ${config.bgColor}`}>
            <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-muted-foreground">{periodLabel}</span>
                <RiskLevelBadge level={forecast.risk_level} />
            </div>

            <div className="space-y-2">
                <div className="flex items-center gap-2">
                    <Icon className={`h-5 w-5 ${config.textColor}`} />
                    <span className={`text-2xl font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                        {isPositive ? '+' : ''}{formatCurrency(netFlow)}
                    </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                        <span className="text-muted-foreground">Einnahmen:</span>
                        <span className="ml-1 font-medium text-green-600">
                            {formatCurrency(forecast.expected_inflow)}
                        </span>
                    </div>
                    <div>
                        <span className="text-muted-foreground">Ausgaben:</span>
                        <span className="ml-1 font-medium text-red-600">
                            {formatCurrency(forecast.expected_outflow)}
                        </span>
                    </div>
                </div>

                {forecast.probability_of_shortfall > 0 && (
                    <div className="flex items-center gap-1 text-sm text-orange-600 dark:text-orange-400">
                        <AlertTriangle className="h-3 w-3" />
                        <span>Engpass-Wahrscheinlichkeit: {formatPercent(forecast.probability_of_shortfall * 100)}</span>
                    </div>
                )}

                {forecast.bottlenecks.length > 0 && (
                    <div className="text-xs text-muted-foreground">
                        {forecast.bottlenecks.length} potenzielle{forecast.bottlenecks.length === 1 ? 'r' : ''} Engpass{forecast.bottlenecks.length === 1 ? '' : 'e'}
                    </div>
                )}

                <div className="text-xs text-muted-foreground mt-2 pt-2 border-t border-current/10">
                    Konfidenzintervall: {formatCurrency(forecast.confidence_interval.lower_bound)} - {formatCurrency(forecast.confidence_interval.upper_bound)}
                    <span className="ml-1">({formatPercent(forecast.confidence_interval.confidence_level * 100)})</span>
                </div>
            </div>
        </div>
    );
}

// ==================== Bottleneck Alert Component ====================

function BottleneckAlert({ bottleneck }: { bottleneck: LiquidityBottleneck }) {
    const config = RISK_LEVEL_CONFIG[bottleneck.severity];

    return (
        <Alert variant={bottleneck.severity === 'critical' ? 'destructive' : 'default'} className="mb-2">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle className="flex items-center gap-2">
                Engpass am {formatDate(bottleneck.date)}
                <RiskLevelBadge level={bottleneck.severity} />
            </AlertTitle>
            <AlertDescription className="mt-2 space-y-2">
                <div className="flex justify-between">
                    <span>Prognostizierter Saldo:</span>
                    <span className="font-medium text-red-600">
                        {formatCurrency(bottleneck.projected_balance)}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span>Fehlbetrag:</span>
                    <span className="font-medium">{formatCurrency(bottleneck.shortfall_amount)}</span>
                </div>
                {bottleneck.contributing_factors.length > 0 && (
                    <div className="text-sm">
                        <span className="font-medium">Ursachen:</span>
                        <ul className="list-disc list-inside mt-1 text-muted-foreground">
                            {bottleneck.contributing_factors.map((factor, idx) => (
                                <li key={idx}>{factor}</li>
                            ))}
                        </ul>
                    </div>
                )}
                {bottleneck.recommendation && (
                    <div className="text-sm pt-2 border-t">
                        <span className="font-medium">Empfehlung:</span>
                        <p className="text-muted-foreground mt-1">{bottleneck.recommendation}</p>
                    </div>
                )}
            </AlertDescription>
        </Alert>
    );
}

// ==================== Anomaly Item Component ====================

function AnomalyItem({ anomaly }: { anomaly: PaymentAnomaly }) {
    const anomalyTypeLabels: Record<string, string> = {
        unusual_amount: 'Ungewöhnlicher Betrag',
        unexpected_timing: 'Unerwarteter Zeitpunkt',
        missing_recurring: 'Fehlende Wiederkehrende',
        duplicate_payment: 'Mögliche Duplikatzahlung',
        pattern_deviation: 'Musterabweichung',
    };

    return (
        <div className="flex items-start gap-3 p-3 rounded-lg border bg-muted/30">
            <Activity className="h-4 w-4 mt-0.5 text-orange-500" />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm">
                        {anomalyTypeLabels[anomaly.anomaly_type] || anomaly.anomaly_type}
                    </span>
                    <Badge variant="outline" className="text-xs">
                        {formatPercent(anomaly.confidence * 100)} Konfidenz
                    </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span>{formatDate(anomaly.date)}</span>
                    <span className="font-medium">{formatCurrency(anomaly.amount)}</span>
                    {anomaly.expected_amount && (
                        <span>Erwartet: {formatCurrency(anomaly.expected_amount)}</span>
                    )}
                    {anomaly.deviation_percent && (
                        <span className="text-orange-600">
                            {anomaly.deviation_percent > 0 ? '+' : ''}{formatPercent(anomaly.deviation_percent)}
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}

// ==================== Waterfall Chart Component ====================

interface WaterfallChartSectionProps {
    bankAccountId?: string;
}

function WaterfallChartSection({ bankAccountId }: WaterfallChartSectionProps) {
    const [days, setDays] = useState(30);
    const [granularity, setGranularity] = useState<'daily' | 'weekly' | 'monthly'>('weekly');
    const { data, isLoading, error, refetch } = useWaterfallChart({
        bank_account_id: bankAccountId,
        days,
        granularity,
    });
    const chartColors = useChartColors();

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-4 w-64" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-[350px] w-full" />
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Liquiditäts-Wasserfall</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Daten
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Button variant="outline" size="sm" onClick={() => refetch()}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Erneut versuchen
                    </Button>
                </CardContent>
            </Card>
        );
    }

    const chartData = data?.entries.map((entry) => {
        // For waterfall chart, calculate the bar values
        const netChange = entry.inflow - entry.outflow;
        return {
            ...entry,
            netChange,
            // The bar shows from starting_balance to ending_balance
            barStart: Math.min(entry.starting_balance, entry.ending_balance),
            barHeight: Math.abs(netChange),
            isPositive: netChange >= 0,
        };
    }) ?? [];

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                <div>
                    <CardTitle>Liquiditäts-Wasserfall</CardTitle>
                    <CardDescription>
                        Visualisierung der Geldstroeme über Zeit
                    </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                    <Select value={granularity} onValueChange={(v) => setGranularity(v as typeof granularity)}>
                        <SelectTrigger className="w-[120px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="daily">Täglich</SelectItem>
                            <SelectItem value="weekly">Wöchentlich</SelectItem>
                            <SelectItem value="monthly">Monatlich</SelectItem>
                        </SelectContent>
                    </Select>
                    <Select value={days.toString()} onValueChange={(v) => setDays(parseInt(v))}>
                        <SelectTrigger className="w-[100px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="14">14 Tage</SelectItem>
                            <SelectItem value="30">30 Tage</SelectItem>
                            <SelectItem value="60">60 Tage</SelectItem>
                            <SelectItem value="90">90 Tage</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </CardHeader>
            <CardContent>
                {/* Summary Stats */}
                {data && (
                    <div className="grid grid-cols-4 gap-4 mb-6">
                        <div className="text-center">
                            <div className="text-sm text-muted-foreground">Startsaldo</div>
                            <div className="text-lg font-semibold">{formatCurrency(data.starting_balance)}</div>
                        </div>
                        <div className="text-center">
                            <div className="text-sm text-muted-foreground">Einnahmen</div>
                            <div className="text-lg font-semibold text-green-600">+{formatCurrency(data.total_inflow)}</div>
                        </div>
                        <div className="text-center">
                            <div className="text-sm text-muted-foreground">Ausgaben</div>
                            <div className="text-lg font-semibold text-red-600">-{formatCurrency(data.total_outflow)}</div>
                        </div>
                        <div className="text-center">
                            <div className="text-sm text-muted-foreground">Endsaldo</div>
                            <div className={`text-lg font-semibold ${data.ending_balance < 0 ? 'text-red-600' : ''}`}>
                                {formatCurrency(data.ending_balance)}
                            </div>
                        </div>
                    </div>
                )}

                {/* Waterfall Chart */}
                <div
                    className="h-[350px]"
                    role="img"
                    aria-label={`Wasserfall-Diagramm der Liquidität für ${days} Tage`}
                >
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                            <XAxis
                                dataKey="label"
                                tick={{ fontSize: 11 }}
                                tickMargin={8}
                                angle={-45}
                                textAnchor="end"
                                height={60}
                            />
                            <YAxis
                                tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                                tick={{ fontSize: 12 }}
                                tickMargin={8}
                            />
                            <Tooltip content={<WaterfallTooltip />} />
                            <ReferenceLine y={0} stroke={chartColors.neutral} strokeDasharray="3 3" />

                            {/* Invisible bar for positioning */}
                            <Bar dataKey="barStart" stackId="stack" fill="transparent" />

                            {/* Visible bar showing the change */}
                            <Bar dataKey="barHeight" stackId="stack" radius={[4, 4, 0, 0]}>
                                {chartData.map((entry, index) => (
                                    <Cell
                                        key={index}
                                        fill={entry.is_running_total
                                            ? chartColors.balance
                                            : entry.isPositive
                                                ? chartColors.inflow
                                                : chartColors.outflow
                                        }
                                        fillOpacity={0.8}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Legend */}
                <div className="flex items-center justify-center gap-6 mt-4 text-sm">
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded" style={{ backgroundColor: chartColors.inflow }} />
                        <span>Einnahmen</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded" style={{ backgroundColor: chartColors.outflow }} />
                        <span>Ausgaben</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded" style={{ backgroundColor: chartColors.balance }} />
                        <span>Saldo</span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

// ==================== Main Component ====================

export interface LiquidityForecastProps {
    bankAccountId?: string;
    showWaterfall?: boolean;
    showAnomalies?: boolean;
    showBottlenecks?: boolean;
}

export function LiquidityForecast({
    bankAccountId,
    showWaterfall = true,
    showAnomalies = true,
    showBottlenecks = true,
}: LiquidityForecastProps) {
    const {
        data: forecastData,
        isLoading: forecastLoading,
        error: forecastError,
        refetch: refetchForecast,
    } = useLiquidityForecast({ bank_account_id: bankAccountId });

    const {
        data: bottleneckData,
        isLoading: bottleneckLoading,
    } = useLiquidityBottlenecks({
        bank_account_id: bankAccountId,
        days_ahead: 90,
    });

    const {
        data: anomalyData,
        isLoading: anomalyLoading,
    } = usePaymentAnomalies({
        bank_account_id: bankAccountId,
        days_back: 30,
    });

    if (forecastLoading) {
        return (
            <div className="space-y-6">
                <Card>
                    <CardHeader>
                        <Skeleton className="h-6 w-64" />
                        <Skeleton className="h-4 w-96" />
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <Skeleton className="h-48" />
                            <Skeleton className="h-48" />
                            <Skeleton className="h-48" />
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    if (forecastError) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Liquiditätsprognose</CardTitle>
                    <CardDescription className="text-destructive">
                        Fehler beim Laden der Prognose
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Button variant="outline" size="sm" onClick={() => refetchForecast()}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Erneut versuchen
                    </Button>
                </CardContent>
            </Card>
        );
    }

    if (!forecastData) {
        return null;
    }

    const hasCriticalBottleneck = bottleneckData?.has_critical_bottleneck ?? false;
    const bottleneckCount = bottleneckData?.bottlenecks.length ?? 0;
    const anomalyCount = anomalyData?.anomaly_count ?? 0;

    return (
        <div className="space-y-6">
            {/* Critical Alert */}
            {hasCriticalBottleneck && (
                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Kritischer Liquiditätsengpass erkannt</AlertTitle>
                    <AlertDescription>
                        Es wurde ein kritischer Engpass am {formatDate(bottleneckData?.earliest_bottleneck_date ?? null)} prognostiziert.
                        Geschätzter Fehlbetrag: {formatCurrency(bottleneckData?.total_shortfall ?? 0)}
                    </AlertDescription>
                </Alert>
            )}

            {/* Main Forecast Card */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                Liquiditätsprognose
                                <RiskLevelBadge level={forecastData.current_risk_level} />
                            </CardTitle>
                            <CardDescription>
                                Rolling-Window Prognosen mit Konfidenzintervallen | Stand: {formatDate(forecastData.forecast_date)}
                            </CardDescription>
                        </div>
                        <div className="text-right">
                            <div className="text-sm text-muted-foreground">Aktueller Saldo</div>
                            <div className={`text-2xl font-bold ${forecastData.starting_balance < 0 ? 'text-red-600' : ''}`}>
                                {formatCurrency(forecastData.starting_balance)}
                            </div>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {/* Forecast Cards Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                        <ForecastCard
                            forecast={forecastData.forecasts.days_30}
                            periodLabel="30 Tage"
                        />
                        <ForecastCard
                            forecast={forecastData.forecasts.days_60}
                            periodLabel="60 Tage"
                        />
                        <ForecastCard
                            forecast={forecastData.forecasts.days_90}
                            periodLabel="90 Tage"
                        />
                    </div>

                    {/* Recommendations */}
                    {forecastData.recommendations.length > 0 && (
                        <div className="p-4 rounded-lg bg-muted/30 border">
                            <div className="flex items-center gap-2 mb-2">
                                <Info className="h-4 w-4 text-blue-500" />
                                <span className="font-medium">Empfehlungen</span>
                            </div>
                            <ul className="space-y-1 text-sm text-muted-foreground">
                                {forecastData.recommendations.map((rec, idx) => (
                                    <li key={idx} className="flex items-start gap-2">
                                        <ChevronRight className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                        {rec}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Confidence Badge */}
                    <div className="flex items-center justify-end mt-4 text-sm text-muted-foreground">
                        <span>Gesamtvertrauen: </span>
                        <Badge variant="outline" className="ml-2">
                            {forecastData.overall_confidence === 'high' ? 'Hoch' :
                                forecastData.overall_confidence === 'medium' ? 'Mittel' : 'Niedrig'}
                        </Badge>
                    </div>
                </CardContent>
            </Card>

            {/* Tabs for Details */}
            <Tabs defaultValue="waterfall" className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="waterfall" disabled={!showWaterfall}>
                        Wasserfall-Chart
                    </TabsTrigger>
                    <TabsTrigger value="bottlenecks" disabled={!showBottlenecks}>
                        Engpässe ({bottleneckCount})
                    </TabsTrigger>
                    <TabsTrigger value="anomalies" disabled={!showAnomalies}>
                        Anomalien ({anomalyCount})
                    </TabsTrigger>
                </TabsList>

                {showWaterfall && (
                    <TabsContent value="waterfall" className="mt-4">
                        <WaterfallChartSection bankAccountId={bankAccountId} />
                    </TabsContent>
                )}

                {showBottlenecks && (
                    <TabsContent value="bottlenecks" className="mt-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    Prognostizierte Engpässe
                                    {hasCriticalBottleneck && (
                                        <Badge variant="destructive">Kritisch</Badge>
                                    )}
                                </CardTitle>
                                <CardDescription>
                                    Potenzielle Liquiditätsengpässe in den nächsten 90 Tagen
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                {bottleneckLoading ? (
                                    <div className="space-y-2">
                                        <Skeleton className="h-24" />
                                        <Skeleton className="h-24" />
                                    </div>
                                ) : bottleneckData && bottleneckData.bottlenecks.length > 0 ? (
                                    <div className="space-y-2">
                                        {bottleneckData.bottlenecks.map((bottleneck, idx) => (
                                            <BottleneckAlert key={idx} bottleneck={bottleneck} />
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-center py-8 text-muted-foreground">
                                        <Shield className="h-12 w-12 mx-auto mb-4 text-green-500" />
                                        <p>Keine Engpässe prognostiziert</p>
                                        <p className="text-sm">Ihre Liquidität sieht für die nächsten 90 Tage stabil aus.</p>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                )}

                {showAnomalies && (
                    <TabsContent value="anomalies" className="mt-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    Zahlungsanomalien
                                    {anomalyData && anomalyData.high_confidence_count > 0 && (
                                        <Badge variant="secondary">
                                            {anomalyData.high_confidence_count} hohe Konfidenz
                                        </Badge>
                                    )}
                                </CardTitle>
                                <CardDescription>
                                    Ungewöhnliche Zahlungsmuster der letzten 30 Tage
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                {anomalyLoading ? (
                                    <div className="space-y-2">
                                        <Skeleton className="h-20" />
                                        <Skeleton className="h-20" />
                                    </div>
                                ) : anomalyData && anomalyData.anomalies.length > 0 ? (
                                    <div className="space-y-2">
                                        {anomalyData.anomalies.map((anomaly, idx) => (
                                            <AnomalyItem key={idx} anomaly={anomaly} />
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-center py-8 text-muted-foreground">
                                        <Activity className="h-12 w-12 mx-auto mb-4 text-green-500" />
                                        <p>Keine Anomalien erkannt</p>
                                        <p className="text-sm">Ihre Zahlungsmuster sind im erwarteten Bereich.</p>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                )}
            </Tabs>
        </div>
    );
}
