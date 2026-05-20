/**
 * InvoiceStatusChart - Status-Verteilung als Chart
 *
 * Zeigt die Verteilung der Rechnungen nach Status als Doughnut-Chart.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PieChart } from 'lucide-react';
import type { InvoiceStatisticsResponse } from '../types/invoice-types';
import { STATUS_STYLES } from '../types/invoice-types';

interface InvoiceStatusChartProps {
  statistics?: InvoiceStatisticsResponse;
  isLoading: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  open: '#64748b',      // Slate
  sent: '#8b5cf6',      // Violet
  paid: '#22c55e',      // Green
  overdue: '#ef4444',   // Red
  dunning: '#f97316',   // Orange
  cancelled: '#9ca3af', // Gray
  partial: '#eab308',   // Yellow
};

export function InvoiceStatusChart({
  statistics,
  isLoading,
}: InvoiceStatusChartProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <PieChart className="h-4 w-4" />
            Status-Verteilung
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[200px]">
            <Skeleton className="h-40 w-40 rounded-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!statistics || Object.keys(statistics.statusDistribution).length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <PieChart className="h-4 w-4" />
            Status-Verteilung
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[200px] text-muted-foreground">
            Keine Daten verfügbar
          </div>
        </CardContent>
      </Card>
    );
  }

  // Berechne Gesamtzahl und Prozentsätze
  const total = statistics.totalInvoices;
  const entries = Object.entries(statistics.statusDistribution)
    .filter(([_, data]) => data.count > 0)
    .sort((a, b) => b[1].count - a[1].count);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <PieChart className="h-4 w-4" />
          Status-Verteilung
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Einfache Balkenvisualisierung statt komplexem Chart */}
          <div className="space-y-3">
            {entries.map(([status, data]) => {
              const percentage = total > 0 ? (data.count / total) * 100 : 0;
              const style = STATUS_STYLES[status as keyof typeof STATUS_STYLES];
              const color = STATUS_COLORS[status] ?? '#9ca3af';

              return (
                <div key={status} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">
                      {style?.label ?? status}
                    </span>
                    <span className="text-muted-foreground">
                      {data.count} ({percentage.toFixed(0)}%)
                    </span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${percentage}%`,
                        backgroundColor: color,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Zusammenfassung */}
          <div className="pt-3 border-t text-sm text-muted-foreground">
            <div className="flex justify-between">
              <span>Gesamt</span>
              <span className="font-medium">{total} Rechnungen</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
