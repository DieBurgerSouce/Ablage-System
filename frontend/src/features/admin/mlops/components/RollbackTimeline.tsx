/**
 * Rollback Timeline Component
 *
 * Vision 2.0 Phase 3: MLOps Dashboard Enhancement
 * Zeigt die Historie von Modell-Rollbacks.
 */

import {
  RotateCcw,
  AlertTriangle,
  CheckCircle,
  Bot,
  User,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useRollbackHistory, type RollbackEvent, type ModelType } from '../hooks/useMLOps';

const MODEL_TYPE_LABELS: Record<ModelType, string> = {
  ocr_confidence: 'OCR Confidence',
  ocr_backend_router: 'Backend Router',
  document_classifier: 'Dokumentenklassifikation',
  entity_matcher: 'Entity Matching',
  extraction_model: 'Feldextraktion',
};

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function RollbackEventItem({ event, isLast }: { event: RollbackEvent; isLast: boolean }) {
  const accuracyChange =
    event.accuracy_before !== null && event.accuracy_after !== null
      ? event.accuracy_after - event.accuracy_before
      : null;

  return (
    <div className="relative pb-6">
      {/* Timeline Line */}
      {!isLast && (
        <span
          className="absolute left-4 top-10 -ml-px h-full w-0.5 bg-border"
          aria-hidden="true"
        />
      )}

      <div className="relative flex items-start gap-4">
        {/* Timeline Dot */}
        <div
          className={`relative flex h-8 w-8 items-center justify-center rounded-full ${
            event.auto_triggered
              ? 'bg-yellow-100 dark:bg-yellow-900/30'
              : 'bg-blue-100 dark:bg-blue-900/30'
          }`}
        >
          {event.auto_triggered ? (
            <Bot className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
          ) : (
            <User className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline">{MODEL_TYPE_LABELS[event.model_type]}</Badge>
            {event.auto_triggered && (
              <Badge variant="secondary" className="text-xs">
                <AlertTriangle className="h-3 w-3 mr-1" />
                Automatisch
              </Badge>
            )}
          </div>

          <div className="mt-2 flex items-center gap-2 text-sm">
            <code className="px-1.5 py-0.5 bg-muted rounded text-xs">
              {event.from_version}
            </code>
            <RotateCcw className="h-3 w-3 text-muted-foreground" />
            <code className="px-1.5 py-0.5 bg-muted rounded text-xs">
              {event.to_version}
            </code>
          </div>

          {/* Accuracy Change */}
          {accuracyChange !== null && (
            <div className="mt-2 flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Accuracy:</span>
              <span>{((event.accuracy_before ?? 0) * 100).toFixed(1)}%</span>
              <span className="text-muted-foreground">→</span>
              <span
                className={`flex items-center gap-1 ${
                  accuracyChange > 0 ? 'text-green-500' : 'text-muted-foreground'
                }`}
              >
                {accuracyChange > 0 ? (
                  <TrendingUp className="h-3 w-3" />
                ) : (
                  <TrendingDown className="h-3 w-3" />
                )}
                {((event.accuracy_after ?? 0) * 100).toFixed(1)}%
              </span>
            </div>
          )}

          {/* Reason */}
          <p className="mt-2 text-sm text-muted-foreground">{event.reason}</p>

          {/* Footer */}
          <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground">
            <span>{formatDate(event.rolled_back_at)}</span>
            {event.rolled_back_by && (
              <span className="flex items-center gap-1">
                <User className="h-3 w-3" />
                {event.rolled_back_by}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function RollbackTimeline() {
  const { data: events, isLoading } = useRollbackHistory(undefined, 10);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex gap-4">
                <Skeleton className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RotateCcw className="h-5 w-5" />
          Rollback-Historie
        </CardTitle>
        <CardDescription>
          Verlauf von Modell-Rollbacks mit Gruenden und Auswirkungen
        </CardDescription>
      </CardHeader>
      <CardContent>
        {events && events.length > 0 ? (
          <div className="flow-root">
            {events.map((event, index) => (
              <RollbackEventItem
                key={event.id}
                event={event}
                isLast={index === events.length - 1}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine Rollbacks bisher</p>
            <p className="text-sm mt-1">
              Alle Modellversionen laufen stabil
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
