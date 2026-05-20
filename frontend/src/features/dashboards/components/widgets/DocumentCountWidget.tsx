/**
 * Document Count Widget
 *
 * Zeigt Dokumenten-Statistiken an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { FileText, TrendingUp, TrendingDown } from 'lucide-react';
import type { Widget } from '../../types';

interface DocumentCountWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface DocumentStats {
  total: number;
  this_month: number;
  last_month: number;
  change_percent: number;
}

export function DocumentCountWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: DocumentCountWidgetProps) {
  const { data, isLoading } = useQuery<DocumentStats>({
    queryKey: ['widget-data', 'document-count', widget.id],
    queryFn: async () => {
      const response = await fetch('/api/v1/documents/stats', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Fehler beim Laden der Statistiken');
      return response.json();
    },
  });

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
        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-primary/10">
              <FileText className="h-8 w-8 text-primary" />
            </div>
            <div>
              <div className="text-3xl font-bold">{data.total}</div>
              <div className="text-sm text-muted-foreground">
                Dokumente gesamt
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 pt-4 border-t">
            <div>
              <div className="text-2xl font-semibold">{data.this_month}</div>
              <div className="text-xs text-muted-foreground">Dieser Monat</div>
            </div>
            <div>
              <div className="text-2xl font-semibold">{data.last_month}</div>
              <div className="text-xs text-muted-foreground">Letzter Monat</div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            {data.change_percent >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-500" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-500" />
            )}
            <span
              className={`text-sm font-medium ${
                data.change_percent >= 0 ? 'text-green-500' : 'text-red-500'
              }`}
            >
              {data.change_percent >= 0 ? '+' : ''}
              {data.change_percent.toFixed(1)}%
            </span>
            <span className="text-xs text-muted-foreground">
              vs. letzter Monat
            </span>
          </div>
        </div>
      ) : null}
    </WidgetWrapper>
  );
}
