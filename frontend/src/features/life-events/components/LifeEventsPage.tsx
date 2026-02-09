/**
 * LifeEventsPage - Hauptseite des Lebenslagen-Assistenten
 *
 * Zeigt Uebersicht der Event-Typen, aktive Ereignisse und Detail-Ansicht.
 */

import { useState } from 'react';
import { Heart, Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useLifeEvents,
  useCreateLifeEvent,
  type LifeEventType,
} from '../api/life-events-api';
import { LifeEventCard, EVENT_TYPE_CONFIG } from './LifeEventCard';
import { LifeEventDetail } from './LifeEventDetail';

// =============================================================================
// All event types in display order
// =============================================================================

const EVENT_TYPES: LifeEventType[] = [
  'umzug',
  'heirat',
  'kind',
  'jobwechsel',
  'ruhestand',
  'todesfall',
  'immobilienkauf',
  'scheidung',
];

// =============================================================================
// Component
// =============================================================================

export function LifeEventsPage() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createType, setCreateType] = useState<LifeEventType | null>(null);
  const [notes, setNotes] = useState('');

  const { data: events = [], isLoading } = useLifeEvents();
  const createEvent = useCreateLifeEvent();

  // Active events (not completed) mapped by type
  const activeEventByType = new Map(
    events
      .filter((e) => e.status !== 'completed')
      .map((e) => [e.event_type, e])
  );

  // If viewing detail
  if (selectedEventId) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <LifeEventDetail
          eventId={selectedEventId}
          onBack={() => setSelectedEventId(null)}
        />
      </div>
    );
  }

  function handleStartEvent(eventType: LifeEventType) {
    setCreateType(eventType);
    setNotes('');
    setCreateDialogOpen(true);
  }

  function handleCreateSubmit() {
    if (!createType) return;

    createEvent.mutate(
      { event_type: createType, notes: notes || undefined },
      {
        onSuccess: (newEvent) => {
          setCreateDialogOpen(false);
          setSelectedEventId(newEvent.id);
        },
      }
    );
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <Heart className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold">Lebenslagen-Assistent</h1>
        </div>
        <p className="text-muted-foreground mt-1">
          Ihr persoenlicher Begleiter fuer wichtige Lebensereignisse
        </p>
      </div>

      {/* Event Type Grid */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Lebensereignis waehlen</h2>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Laden...</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {EVENT_TYPES.map((type) => (
              <LifeEventCard
                key={type}
                eventType={type}
                activeEvent={activeEventByType.get(type)}
                onStart={handleStartEvent}
                onOpen={setSelectedEventId}
              />
            ))}
          </div>
        )}
      </div>

      {/* Active Events */}
      {events.filter((e) => e.status !== 'completed').length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Aktive Ereignisse</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {events
              .filter((e) => e.status !== 'completed')
              .map((event) => {
                const config = EVENT_TYPE_CONFIG[event.event_type];
                const Icon = config?.icon;
                const completedItems = event.checklist.filter((i) => i.done).length;
                const totalItems = event.checklist.length;
                const percent = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0;

                return (
                  <Card
                    key={event.id}
                    className="cursor-pointer hover:shadow-md transition-shadow"
                    onClick={() => setSelectedEventId(event.id)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-center gap-3">
                        {Icon && (
                          <div className={`rounded-lg p-2 ${config.color}`}>
                            <Icon className="w-5 h-5" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-medium">{event.title}</p>
                          <p className="text-sm text-muted-foreground">
                            {completedItems}/{totalItems} Aufgaben erledigt ({percent}%)
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
          </div>
        </div>
      )}

      {/* Completed Events */}
      {events.filter((e) => e.status === 'completed').length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Abgeschlossene Ereignisse</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {events
              .filter((e) => e.status === 'completed')
              .map((event) => {
                const config = EVENT_TYPE_CONFIG[event.event_type];
                const Icon = config?.icon;

                return (
                  <Card
                    key={event.id}
                    className="cursor-pointer hover:shadow-md transition-shadow opacity-75"
                    onClick={() => setSelectedEventId(event.id)}
                  >
                    <CardContent className="p-4">
                      <div className="flex items-center gap-3">
                        {Icon && (
                          <div className={`rounded-lg p-2 ${config.color}`}>
                            <Icon className="w-5 h-5" />
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-medium line-through">{event.title}</p>
                          <p className="text-sm text-muted-foreground">Abgeschlossen</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
          </div>
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Neues Lebensereignis starten
            </DialogTitle>
            <DialogDescription>
              {createType && EVENT_TYPE_CONFIG[createType]
                ? `${EVENT_TYPE_CONFIG[createType].label}: ${EVENT_TYPE_CONFIG[createType].description}`
                : 'Waehlen Sie ein Lebensereignis aus.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="notes">Notizen (optional)</Label>
              <Textarea
                id="notes"
                placeholder="Zusaetzliche Informationen zu Ihrem Ereignis..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
            >
              Abbrechen
            </Button>
            <Button
              onClick={handleCreateSubmit}
              disabled={createEvent.isPending}
            >
              {createEvent.isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Plus className="w-4 h-4 mr-2" />
              )}
              Ereignis starten
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
