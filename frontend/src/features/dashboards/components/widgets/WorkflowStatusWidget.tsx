/**
 * Workflow Status Widget
 *
 * Zeigt Workflow-Status-Übersicht an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { Workflow, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import type { Widget } from '../../types';
import { Progress } from '@/components/ui/progress';

interface WorkflowStatusWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface WorkflowStats {
  total: number;
  completed: number;
  in_progress: number;
  pending: number;
  failed: number;
  completion_rate: number;
}

export function WorkflowStatusWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: WorkflowStatusWidgetProps) {
  const { data, isLoading } = useQuery<WorkflowStats>({
    queryKey: ['widget-data', 'workflow-status', widget.id],
    queryFn: async () => {
      const response = await fetch('/api/v1/workflows/stats', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Fehler beim Laden der Workflow-Daten');
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
              <Workflow className="h-8 w-8 text-primary" />
            </div>
            <div>
              <div className="text-3xl font-bold">{data.total}</div>
              <div className="text-sm text-muted-foreground">
                Workflows gesamt
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Abschlussrate</span>
              <span className="text-sm font-bold text-green-600">
                {data.completion_rate.toFixed(1)}%
              </span>
            </div>
            <Progress value={data.completion_rate} className="h-2" />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between p-2 rounded-lg bg-green-50 dark:bg-green-950/20">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm">Abgeschlossen</span>
              </div>
              <span className="font-semibold text-green-600">
                {data.completed}
              </span>
            </div>

            <div className="flex items-center justify-between p-2 rounded-lg bg-blue-50 dark:bg-blue-950/20">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-blue-500" />
                <span className="text-sm">In Bearbeitung</span>
              </div>
              <span className="font-semibold text-blue-600">
                {data.in_progress}
              </span>
            </div>

            <div className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-950/20">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-gray-500" />
                <span className="text-sm">Wartend</span>
              </div>
              <span className="font-semibold text-gray-600">
                {data.pending}
              </span>
            </div>

            {data.failed > 0 && (
              <div className="flex items-center justify-between p-2 rounded-lg bg-red-50 dark:bg-red-950/20">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  <span className="text-sm">Fehlgeschlagen</span>
                </div>
                <span className="font-semibold text-red-600">
                  {data.failed}
                </span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-center p-4">
          <Workflow className="h-8 w-8 text-muted-foreground mb-2" />
          <div className="text-sm text-muted-foreground">
            Keine Workflow-Daten verfügbar
          </div>
        </div>
      )}
    </WidgetWrapper>
  );
}
