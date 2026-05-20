/**
 * Cash Flow Chart
 *
 * Zeigt Ein-/Auszahlungen pro Firma als Stacked Bar Chart.
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { CashFlowOverview } from '../api/holding-api';

interface CashFlowChartProps {
  cashflow: CashFlowOverview;
}

const PERIOD_LABELS: Record<string, string> = {
  daily: 'Heute',
  weekly: 'Diese Woche',
  monthly: 'Dieser Monat',
};

export function CashFlowChart({ cashflow }: CashFlowChartProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const data = useMemo(() => {
    return cashflow.by_company.map((item) => ({
      name: item.company_name,
      inflows: item.inflows,
      outflows: -item.outflows, // Negativ für visuelle Darstellung
      net: item.net_flow,
    }));
  }, [cashflow.by_company]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cashflow: {PERIOD_LABELS[cashflow.period_type]}</CardTitle>
        <CardDescription>
          Netto: {formatCurrency(cashflow.total_net_flow)} (Ein:{' '}
          {formatCurrency(cashflow.total_inflows)}, Aus:{' '}
          {formatCurrency(cashflow.total_outflows)})
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => formatCurrency(Math.abs(v))} />
              <Tooltip
                formatter={(value: number, name: string) => [
                  formatCurrency(Math.abs(value)),
                  name === 'inflows'
                    ? 'Einzahlungen'
                    : name === 'outflows'
                    ? 'Auszahlungen'
                    : 'Netto',
                ]}
              />
              <Legend
                formatter={(value) =>
                  value === 'inflows'
                    ? 'Einzahlungen'
                    : value === 'outflows'
                    ? 'Auszahlungen'
                    : 'Netto'
                }
              />
              <ReferenceLine y={0} stroke="#666" />
              <Bar dataKey="inflows" stackId="stack" fill="hsl(142, 71%, 45%)" name="inflows" />
              <Bar dataKey="outflows" stackId="stack" fill="hsl(0, 72%, 51%)" name="outflows" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
