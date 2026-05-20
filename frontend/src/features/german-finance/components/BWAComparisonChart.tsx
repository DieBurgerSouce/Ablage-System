/**
 * BWAComparisonChart Component
 *
 * Side-by-side comparison of two BWA reports
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface BWAComparisonData {
  report1: {
    year: number;
    month: number;
    revenue: number;
    expenses: number;
    profit: number;
  };
  report2: {
    year: number;
    month: number;
    revenue: number;
    expenses: number;
    profit: number;
  };
  differences: Array<{
    section: string;
    amount1: number;
    amount2: number;
    change: number;
    change_percent: number;
  }>;
}

interface BWAComparisonChartProps {
  data: BWAComparisonData;
}

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatPercent = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: 'always',
  }).format(value / 100);
};

const formatPeriod = (year: number, month: number): string => {
  const monthNames = [
    'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
    'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
  ];
  return `${monthNames[month - 1]} ${year}`;
};

function ComparisonBar({
  label,
  value1,
  value2,
  maxValue,
  type = 'normal',
}: {
  label: string;
  value1: number;
  value2: number;
  maxValue: number;
  type?: 'normal' | 'revenue' | 'expense';
}) {
  const percent1 = Math.min((Math.abs(value1) / maxValue) * 100, 100);
  const percent2 = Math.min((Math.abs(value2) / maxValue) * 100, 100);
  const change = value2 - value1;
  const changePercent = value1 !== 0 ? (change / Math.abs(value1)) * 100 : 0;

  const getColor = () => {
    if (type === 'revenue') return 'bg-green-500';
    if (type === 'expense') return 'bg-red-500';
    return 'bg-blue-500';
  };

  const getTrendIcon = () => {
    if (Math.abs(changePercent) < 0.1) return <Minus className="h-3 w-3" />;
    if (changePercent > 0) return <TrendingUp className="h-3 w-3" />;
    return <TrendingDown className="h-3 w-3" />;
  };

  const getTrendColor = () => {
    if (Math.abs(changePercent) < 0.1) return 'text-muted-foreground';
    if (type === 'expense') {
      // For expenses, decrease is good
      return changePercent < 0 ? 'text-green-600' : 'text-red-600';
    }
    // For revenue and normal, increase is good
    return changePercent > 0 ? 'text-green-600' : 'text-red-600';
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <div className={`flex items-center gap-1 text-xs ${getTrendColor()}`}>
          {getTrendIcon()}
          <span>{formatPercent(changePercent)}</span>
        </div>
      </div>

      {/* Period 1 Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Periode 1</span>
          <span className="font-medium text-foreground">{formatEuro(value1)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full ${getColor()} opacity-60`}
            style={{ width: `${percent1}%` }}
          />
        </div>
      </div>

      {/* Period 2 Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Periode 2</span>
          <span className="font-medium text-foreground">{formatEuro(value2)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full ${getColor()}`}
            style={{ width: `${percent2}%` }}
          />
        </div>
      </div>

      {/* Change */}
      <div className="text-xs">
        <span className="text-muted-foreground">Veränderung: </span>
        <span className={`font-semibold ${getTrendColor()}`}>
          {change > 0 ? '+' : ''}
          {formatEuro(change)}
        </span>
      </div>
    </div>
  );
}

export function BWAComparisonChart({ data }: BWAComparisonChartProps) {
  const maxRevenue = Math.max(data.report1.revenue, data.report2.revenue);
  const maxExpenses = Math.max(data.report1.expenses, data.report2.expenses);
  const maxProfit = Math.max(
    Math.abs(data.report1.profit),
    Math.abs(data.report2.profit)
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>BWA-Vergleich</CardTitle>
            <CardDescription>
              Vergleich von zwei Zeiträumen
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">
              {formatPeriod(data.report1.year, data.report1.month)}
            </Badge>
            <span className="text-muted-foreground">vs</span>
            <Badge variant="outline">
              {formatPeriod(data.report2.year, data.report2.month)}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Key Metrics Comparison */}
        <div className="space-y-6">
          <ComparisonBar
            label="Erlöse"
            value1={data.report1.revenue}
            value2={data.report2.revenue}
            maxValue={maxRevenue}
            type="revenue"
          />

          <Separator />

          <ComparisonBar
            label="Aufwendungen"
            value1={data.report1.expenses}
            value2={data.report2.expenses}
            maxValue={maxExpenses}
            type="expense"
          />

          <Separator />

          <ComparisonBar
            label="Betriebsergebnis"
            value1={data.report1.profit}
            value2={data.report2.profit}
            maxValue={maxProfit}
          />
        </div>

        {/* Detailed Section Differences */}
        {data.differences && data.differences.length > 0 && (
          <>
            <Separator />
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">Detaillierte Änderungen</h3>
              <div className="space-y-3">
                {data.differences
                  .filter((diff) => Math.abs(diff.change_percent) >= 5) // Only show significant changes
                  .sort((a, b) => Math.abs(b.change_percent) - Math.abs(a.change_percent))
                  .slice(0, 5) // Top 5 changes
                  .map((diff, index) => {
                    const isIncrease = diff.change > 0;
                    return (
                      <div
                        key={index}
                        className="flex items-center justify-between rounded-md border p-3"
                      >
                        <span className="text-sm font-medium">{diff.section}</span>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={isIncrease ? 'default' : 'secondary'}
                            className="font-mono text-xs"
                          >
                            {isIncrease ? '+' : ''}
                            {formatPercent(diff.change_percent)}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatEuro(diff.change)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
