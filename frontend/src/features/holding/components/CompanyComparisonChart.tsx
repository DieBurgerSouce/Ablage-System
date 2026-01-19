/**
 * Company Comparison Chart
 *
 * Horizontales Balkendiagramm zum Firmenvergleich.
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { CompanyComparison } from '../api/holding-api';

interface CompanyComparisonChartProps {
  comparison: CompanyComparison;
}

const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  '#8884d8',
  '#82ca9d',
  '#ffc658',
];

const METRIC_LABELS: Record<string, string> = {
  documents: 'Dokumente',
  receivables: 'Forderungen',
  payables: 'Verbindlichkeiten',
  balance: 'Kontostand',
};

const METRIC_FORMATS: Record<string, (v: number) => string> = {
  documents: (v) => v.toLocaleString('de-DE'),
  receivables: (v) =>
    new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(v),
  payables: (v) =>
    new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(v),
  balance: (v) =>
    new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(v),
};

export function CompanyComparisonChart({ comparison }: CompanyComparisonChartProps) {
  const formatValue = METRIC_FORMATS[comparison.metric] || ((v: number) => v.toString());

  const data = useMemo(() => {
    return comparison.companies.map((c) => ({
      name: c.company_name,
      value: c.value,
    }));
  }, [comparison.companies]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Firmenvergleich: {METRIC_LABELS[comparison.metric]}</CardTitle>
        <CardDescription>
          Stand: {new Date(comparison.comparison_date).toLocaleDateString('de-DE')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
              <XAxis type="number" tickFormatter={(v) => formatValue(v)} />
              <YAxis
                type="category"
                dataKey="name"
                width={90}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                formatter={(value: number) => [formatValue(value), METRIC_LABELS[comparison.metric]]}
                labelFormatter={(label) => label}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
