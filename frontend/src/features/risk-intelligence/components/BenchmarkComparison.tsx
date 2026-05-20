/**
 * Benchmark Comparison Component
 *
 * Vergleicht Entity-Performance mit Branchen-Benchmark.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ArrowUp, ArrowDown, Equal, Building2 } from 'lucide-react';
import type { BenchmarkComparison as BenchmarkComparisonType } from '../api/risk-intelligence-api';

interface BenchmarkComparisonProps {
  benchmark: BenchmarkComparisonType;
  className?: string;
}

export function BenchmarkComparison({ benchmark, className }: BenchmarkComparisonProps) {
  const getPerformanceBadge = () => {
    const variants: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string; color: string }> = {
      excellent: { variant: 'default', label: 'Hervorragend', color: 'text-green-500' },
      good: { variant: 'default', label: 'Gut', color: 'text-green-400' },
      average: { variant: 'secondary', label: 'Durchschnittlich', color: 'text-yellow-500' },
      below_average: { variant: 'outline', label: 'Unterdurchschnittlich', color: 'text-orange-500' },
      poor: { variant: 'destructive', label: 'Schlecht', color: 'text-red-500' },
    };
    const { variant, label } = variants[benchmark.performance] || variants.average;
    return <Badge variant={variant}>{label}</Badge>;
  };

  const getDeviationIndicator = (deviation: number, invertColors = false) => {
    const isPositive = invertColors ? deviation < 0 : deviation > 0;
    const isNegative = invertColors ? deviation > 0 : deviation < 0;

    if (Math.abs(deviation) < 0.1) {
      return <Equal className="w-4 h-4 text-gray-500" />;
    }
    if (isPositive) {
      return <ArrowUp className="w-4 h-4 text-green-500" />;
    }
    if (isNegative) {
      return <ArrowDown className="w-4 h-4 text-red-500" />;
    }
    return null;
  };

  const getIndustryLabel = (industry: string) => {
    const labels: Record<string, string> = {
      retail: 'Einzelhandel',
      manufacturing: 'Fertigung',
      services: 'Dienstleistungen',
      construction: 'Bauwesen',
      technology: 'Technologie',
      default: 'Allgemein',
    };
    return labels[industry] || industry;
  };

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-muted-foreground" />
            <div>
              <CardTitle className="text-lg">Branchen-Benchmark</CardTitle>
              <CardDescription>{getIndustryLabel(benchmark.industry)}</CardDescription>
            </div>
          </div>
          {getPerformanceBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Benchmark Score */}
        <div className="text-center p-4 bg-muted rounded-lg">
          <p className="text-sm text-muted-foreground mb-2">Benchmark-Score</p>
          <p className="text-3xl font-bold">{benchmark.benchmark_score.toFixed(0)}</p>
          <Progress
            value={benchmark.benchmark_score}
            className="mt-2 h-2"
          />
        </div>

        {/* Comparison Grid */}
        <div className="space-y-4">
          {/* Payment Delay */}
          <div className="grid grid-cols-3 gap-2 items-center">
            <div>
              <p className="text-xs text-muted-foreground">Branche</p>
              <p className="font-medium">{benchmark.benchmark.avg_payment_delay} Tage</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Zahlungsverzögerung</p>
              <div className="flex items-center justify-center gap-1">
                {getDeviationIndicator(benchmark.delay_deviation, true)}
                <span className={benchmark.delay_deviation > 0 ? 'text-red-500' : 'text-green-500'}>
                  {benchmark.delay_deviation > 0 ? '+' : ''}{benchmark.delay_deviation.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Aktuell</p>
              <p className="font-medium">{benchmark.actual_payment_delay.toFixed(0)} Tage</p>
            </div>
          </div>

          {/* Default Rate */}
          <div className="grid grid-cols-3 gap-2 items-center">
            <div>
              <p className="text-xs text-muted-foreground">Branche</p>
              <p className="font-medium">{(benchmark.benchmark.default_rate * 100).toFixed(1)}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-muted-foreground">Ausfallrate</p>
              <div className="flex items-center justify-center gap-1">
                {getDeviationIndicator(benchmark.default_deviation, true)}
                <span className={benchmark.default_deviation > 0 ? 'text-red-500' : 'text-green-500'}>
                  {benchmark.default_deviation > 0 ? '+' : ''}{benchmark.default_deviation.toFixed(1)}%
                </span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Aktuell</p>
              <p className="font-medium">{(benchmark.actual_default_rate * 100).toFixed(1)}%</p>
            </div>
          </div>
        </div>

        {/* Risk Factor Info */}
        <div className="pt-2 border-t">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Branchen-Risikofaktor</span>
            <Badge variant="outline">
              {benchmark.benchmark.industry_risk_factor.toFixed(1)}x
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
