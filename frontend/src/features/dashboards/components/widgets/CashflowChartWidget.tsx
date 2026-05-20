/**
 * Cashflow Chart Widget
 *
 * Zeigt Cashflow-Diagramm an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { TrendingUp, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import type { Widget } from '../../types';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface CashflowChartWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface CashflowData {
  date: string;
  inflow: number;
  outflow: number;
  balance: number;
}

export function CashflowChartWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: CashflowChartWidgetProps) {
  const { data, isLoading } = useQuery<CashflowData[]>({
    queryKey: ['widget-data', 'cashflow-chart', widget.id],
    queryFn: async () => {
      const response = await fetch('/api/v1/cashflow/chart', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Fehler beim Laden der Daten');
      return response.json();
    },
  });

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const totalInflow = data?.reduce((sum, d) => sum + d.inflow, 0) ?? 0;
  const totalOutflow = data?.reduce((sum, d) => sum + d.outflow, 0) ?? 0;
  const netCashflow = totalInflow - totalOutflow;

  return (
    <WidgetWrapper
      title={widget.title}
      onRemove={onRemove}
      onSettings={onSettings}
      isEditing={isEditing}
    >
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-sm text-muted-foreground">Lädt...</div>
        </div>
      ) : data && data.length > 0 ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-2 rounded-lg bg-green-50 dark:bg-green-950/20">
              <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-1">
                <ArrowUpRight className="h-3 w-3" />
                Einnahmen
              </div>
              <div className="font-semibold text-green-600 dark:text-green-400">
                {formatCurrency(totalInflow)}
              </div>
            </div>
            <div className="text-center p-2 rounded-lg bg-red-50 dark:bg-red-950/20">
              <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-1">
                <ArrowDownRight className="h-3 w-3" />
                Ausgaben
              </div>
              <div className="font-semibold text-red-600 dark:text-red-400">
                {formatCurrency(totalOutflow)}
              </div>
            </div>
            <div className="text-center p-2 rounded-lg bg-muted">
              <div className="flex items-center justify-center gap-1 text-xs text-muted-foreground mb-1">
                <TrendingUp className="h-3 w-3" />
                Netto
              </div>
              <div
                className={`font-semibold ${
                  netCashflow >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {formatCurrency(netCashflow)}
              </div>
            </div>
          </div>

          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value) => {
                    const date = new Date(value);
                    return `${date.getDate()}.${date.getMonth() + 1}`;
                  }}
                />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={formatCurrency} />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  labelFormatter={(label) => {
                    const date = new Date(label);
                    return date.toLocaleDateString('de-DE');
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="inflow"
                  stroke="#22c55e"
                  strokeWidth={2}
                  name="Einnahmen"
                />
                <Line
                  type="monotone"
                  dataKey="outflow"
                  stroke="#ef4444"
                  strokeWidth={2}
                  name="Ausgaben"
                />
                <Line
                  type="monotone"
                  dataKey="balance"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  name="Saldo"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Keine Daten verfügbar
        </div>
      )}
    </WidgetWrapper>
  );
}
