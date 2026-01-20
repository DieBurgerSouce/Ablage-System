/**
 * Invoice Summary Widget
 *
 * Zeigt Rechnungs-Übersicht an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { Receipt, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import type { Widget } from '../../types';

interface InvoiceSummaryWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface InvoiceStats {
  total_count: number;
  total_amount: number;
  paid_count: number;
  paid_amount: number;
  overdue_count: number;
  overdue_amount: number;
  pending_count: number;
  pending_amount: number;
}

export function InvoiceSummaryWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: InvoiceSummaryWidgetProps) {
  const { data, isLoading } = useQuery<InvoiceStats>({
    queryKey: ['widget-data', 'invoice-summary', widget.id],
    queryFn: async () => {
      const response = await fetch('/api/v1/invoices/stats', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Fehler beim Laden der Statistiken');
      return response.json();
    },
  });

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  };

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
      ) : data ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
            <Receipt className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1">
              <div className="text-sm font-medium">Gesamt</div>
              <div className="text-xs text-muted-foreground">
                {data.total_count} Rechnungen
              </div>
            </div>
            <div className="text-right">
              <div className="font-semibold">
                {formatCurrency(data.total_amount)}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 rounded-lg border border-green-200 bg-green-50 dark:bg-green-950/20">
            <CheckCircle className="h-5 w-5 text-green-500" />
            <div className="flex-1">
              <div className="text-sm font-medium">Bezahlt</div>
              <div className="text-xs text-muted-foreground">
                {data.paid_count} Rechnungen
              </div>
            </div>
            <div className="text-right">
              <div className="font-semibold text-green-600 dark:text-green-400">
                {formatCurrency(data.paid_amount)}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/20">
            <AlertCircle className="h-5 w-5 text-red-500" />
            <div className="flex-1">
              <div className="text-sm font-medium">Überfällig</div>
              <div className="text-xs text-muted-foreground">
                {data.overdue_count} Rechnungen
              </div>
            </div>
            <div className="text-right">
              <div className="font-semibold text-red-600 dark:text-red-400">
                {formatCurrency(data.overdue_amount)}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 rounded-lg border">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1">
              <div className="text-sm font-medium">Offen</div>
              <div className="text-xs text-muted-foreground">
                {data.pending_count} Rechnungen
              </div>
            </div>
            <div className="text-right">
              <div className="font-semibold">
                {formatCurrency(data.pending_amount)}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </WidgetWrapper>
  );
}
