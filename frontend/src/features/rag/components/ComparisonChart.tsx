/**
 * Comparison Chart Component
 *
 * Zeigt einen Ausgabenvergleich als Balkendiagramm an.
 */

import { memo } from 'react';
import { motion } from 'framer-motion';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Tooltip as RechartsTooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import { TrendingDown, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ComparisonData } from '../types/chat-types';

interface ComparisonChartProps {
    data: ComparisonData;
}

const currencyFormatter = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
});

const formatAxisValue = (value: number): string => {
    if (value >= 1000) {
        return `${(value / 1000).toFixed(0)}k`;
    }
    return String(value);
};

const CustomTooltip = ({
    active,
    payload,
    label,
}: {
    active?: boolean;
    payload?: Array<{ name: string; value: number; color: string }>;
    label?: string;
}) => {
    if (!active || !payload || payload.length === 0) return null;

    return (
        <div className="bg-popover border rounded-md p-2 shadow-md text-sm">
            <p className="font-medium mb-1">{label}</p>
            {payload.map((entry) => (
                <div key={entry.name} className="flex items-center gap-2">
                    <span
                        className="w-2.5 h-2.5 rounded-full"
                        style={{ backgroundColor: entry.color }}
                    />
                    <span className="text-muted-foreground">{entry.name}:</span>
                    <span className="font-mono">{currencyFormatter.format(entry.value)}</span>
                </div>
            ))}
        </div>
    );
};

export const ComparisonChart = memo(function ComparisonChart({
    data,
}: ComparisonChartProps) {
    const chartData = data.categories.map((cat) => ({
        name: cat.name,
        [data.period_1_label]: cat.period_1_value,
        [data.period_2_label]: cat.period_2_value,
    }));

    const isDecrease = data.total_change_percent < 0;
    const changeColor = isDecrease ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
    const changeBg = isDecrease ? 'bg-green-100 dark:bg-green-950/30' : 'bg-red-100 dark:bg-red-950/30';

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
        >
            <Card className="max-w-[500px]">
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center gap-2">
                        Ausgabenvergleich
                        <Badge
                            variant="outline"
                            className={cn('ml-auto gap-1', changeBg, changeColor)}
                        >
                            {isDecrease ? (
                                <TrendingDown className="h-3 w-3" />
                            ) : (
                                <TrendingUp className="h-3 w-3" />
                            )}
                            {data.total_change_percent > 0 ? '+' : ''}
                            {data.total_change_percent.toFixed(1)}%
                        </Badge>
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Chart */}
                    <div className="w-full h-52">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
                                <XAxis
                                    dataKey="name"
                                    tick={{ fontSize: 11 }}
                                    tickLine={false}
                                    axisLine={false}
                                />
                                <YAxis
                                    tickFormatter={formatAxisValue}
                                    tick={{ fontSize: 11 }}
                                    tickLine={false}
                                    axisLine={false}
                                    width={45}
                                />
                                <RechartsTooltip content={<CustomTooltip />} />
                                <Legend
                                    wrapperStyle={{ fontSize: '11px' }}
                                />
                                <Bar
                                    dataKey={data.period_1_label}
                                    fill="hsl(var(--muted-foreground) / 0.4)"
                                    radius={[3, 3, 0, 0]}
                                />
                                <Bar
                                    dataKey={data.period_2_label}
                                    fill="hsl(var(--primary))"
                                    radius={[3, 3, 0, 0]}
                                />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Total Row */}
                    <div className="flex items-center justify-between pt-3 border-t text-sm">
                        <div className="space-y-0.5">
                            <div className="text-muted-foreground">
                                {data.period_1_label}: <span className="font-mono">{currencyFormatter.format(data.total_period_1)}</span>
                            </div>
                            <div className="text-muted-foreground">
                                {data.period_2_label}: <span className="font-mono">{currencyFormatter.format(data.total_period_2)}</span>
                            </div>
                        </div>
                        <div className="text-right space-y-0.5">
                            <div className="font-medium">
                                Differenz: <span className={cn('font-mono', changeColor)}>
                                    {data.total_difference > 0 ? '+' : ''}
                                    {currencyFormatter.format(data.total_difference)}
                                </span>
                            </div>
                            <div className={cn('text-xs', changeColor)}>
                                {isDecrease ? 'Einsparung' : 'Mehrausgaben'}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </motion.div>
    );
});

export default ComparisonChart;
