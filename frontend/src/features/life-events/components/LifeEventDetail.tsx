/**
 * LifeEventDetail - Detailansicht eines Lebensereignisses
 *
 * Zeigt Checkliste, Fortschritt, finanzielle Auswirkungen und Empfehlungen.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import {
  ArrowLeft,
  CheckCircle2,
  Euro,
  Lightbulb,
  Loader2,
} from 'lucide-react';
import {
  useLifeEvent,
  useToggleChecklistItem,
  useCompleteLifeEvent,
} from '../api/life-events-api';
import { EVENT_TYPE_CONFIG } from './LifeEventCard';

// =============================================================================
// Priority Configuration
// =============================================================================

const PRIORITY_CONFIG: Record<string, { label: string; variant: 'destructive' | 'default' | 'secondary' }> = {
  high: { label: 'Hoch', variant: 'destructive' },
  medium: { label: 'Mittel', variant: 'default' },
  low: { label: 'Niedrig', variant: 'secondary' },
};

const STATUS_LABELS: Record<string, string> = {
  pending: 'Ausstehend',
  confirmed: 'Bestaetigt',
  in_progress: 'In Bearbeitung',
  completed: 'Abgeschlossen',
};

// =============================================================================
// Component
// =============================================================================

interface LifeEventDetailProps {
  eventId: string;
  onBack: () => void;
}

export function LifeEventDetail({ eventId, onBack }: LifeEventDetailProps) {
  const { data: event, isLoading, error } = useLifeEvent(eventId);
  const toggleItem = useToggleChecklistItem();
  const completeEvent = useCompleteLifeEvent();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Laden...</span>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Lebensereignis nicht gefunden.</p>
        <Button variant="outline" className="mt-4" onClick={onBack}>
          Zurueck
        </Button>
      </div>
    );
  }

  const config = EVENT_TYPE_CONFIG[event.event_type];
  const Icon = config?.icon;
  const completedItems = event.checklist.filter((item) => item.done).length;
  const totalItems = event.checklist.length;
  const progressPercent = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0;
  const allDone = totalItems > 0 && completedItems === totalItems;

  function handleToggle(itemId: string, currentDone: boolean) {
    toggleItem.mutate({
      eventId: event.id,
      itemId,
      done: !currentDone,
    });
  }

  function handleComplete() {
    completeEvent.mutate(event.id, {
      onSuccess: () => onBack(),
    });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="w-4 h-4 mr-1" />
          Zurueck
        </Button>
      </div>

      <div className="flex items-center gap-4">
        {Icon && (
          <div className={`rounded-lg p-3 ${config.color}`}>
            <Icon className="w-8 h-8" />
          </div>
        )}
        <div>
          <h2 className="text-2xl font-bold">{event.title}</h2>
          {event.description && (
            <p className="text-muted-foreground mt-1">{event.description}</p>
          )}
        </div>
        <Badge variant="outline" className="ml-auto">
          {STATUS_LABELS[event.status] ?? event.status}
        </Badge>
      </div>

      {/* Progress */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Fortschritt</span>
            <span className="text-sm text-muted-foreground">
              {completedItems} von {totalItems} erledigt ({progressPercent}%)
            </span>
          </div>
          <Progress value={progressPercent} className="h-3" />
        </CardContent>
      </Card>

      {/* Checklist */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5" />
            Checkliste
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {event.checklist.map((item) => {
              const priorityCfg = item.priority ? PRIORITY_CONFIG[item.priority] : undefined;
              return (
                <div
                  key={item.id}
                  className="flex items-center gap-3 py-2 border-b last:border-0"
                >
                  <Checkbox
                    checked={item.done}
                    onCheckedChange={() => handleToggle(item.id, item.done)}
                    disabled={toggleItem.isPending}
                    aria-label={item.task}
                  />
                  <span
                    className={`flex-1 text-sm ${item.done ? 'line-through text-muted-foreground' : ''}`}
                  >
                    {item.task}
                  </span>
                  {priorityCfg && (
                    <Badge variant={priorityCfg.variant} className="text-xs">
                      {priorityCfg.label}
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-xs">
                    {item.category}
                  </Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Financial Impact */}
      {event.financial_impact && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Euro className="w-5 h-5" />
              Finanzielle Auswirkungen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Geschaetzte Kosten</p>
                <p className="text-lg font-semibold">
                  {event.financial_impact.estimated_cost}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Steuerlich absetzbar</p>
                <p className="text-lg font-semibold">
                  {event.financial_impact.tax_deductible ? 'Ja' : 'Nein'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      {event.recommendations && event.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="w-5 h-5" />
              Empfehlungen
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {event.recommendations.map((rec, index) => (
                <div key={index} className="flex items-start gap-3 py-2 border-b last:border-0">
                  <Lightbulb className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium">{rec.title}</p>
                    <p className="text-sm text-muted-foreground">{rec.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Complete Button */}
      {event.status !== 'completed' && allDone && (
        <div className="flex justify-end">
          <Button
            onClick={handleComplete}
            disabled={completeEvent.isPending}
          >
            {completeEvent.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4 mr-2" />
            )}
            Ereignis abschliessen
          </Button>
        </div>
      )}
    </div>
  );
}
