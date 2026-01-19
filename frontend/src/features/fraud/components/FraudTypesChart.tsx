/**
 * Fraud Types Distribution Chart
 *
 * Zeigt Verteilung der Fraud-Typen als Pie/Bar Chart.
 */

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
import { PieChart } from 'lucide-react';

interface FraudTypesChartProps {
  data: Array<{ type: string; count: number }>;
}

const fraudTypeLabels: Record<string, string> = {
  duplicate_invoice: 'Duplikat',
  price_anomaly: 'Preis-Anomalie',
  phantom_supplier: 'Phantom-Lieferant',
  expense_fraud: 'Spesen-Betrug',
  kickback: 'Kickback',
  shell_company: 'Shell-Company',
  round_amount: 'Runde Betraege',
  split_invoice: 'Invoice-Split',
  weekend_invoice: 'Wochenend',
};

const COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
];

export function FraudTypesChart({ data }: FraudTypesChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="h-5 w-5" />
            Fraud-Typen Verteilung
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[200px] flex items-center justify-center text-muted-foreground">
            Keine Daten verfuegbar
          </div>
        </CardContent>
      </Card>
    );
  }

  // Daten mit Labels aufbereiten
  const chartData = data.map((item) => ({
    ...item,
    label: fraudTypeLabels[item.type] || item.type,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PieChart className="h-5 w-5" />
          Fraud-Typen Verteilung
        </CardTitle>
        <CardDescription>
          Haeufigkeit nach Betrugsart
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis
                dataKey="label"
                type="category"
                tick={{ fontSize: 12 }}
                width={75}
              />
              <Tooltip
                formatter={(value: number) => [value, 'Anzahl']}
                labelFormatter={(label) => `Typ: ${label}`}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {chartData.map((_, index) => (
                  <Cell key={index} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
