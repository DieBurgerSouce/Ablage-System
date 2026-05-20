import { useMemo } from 'react';
import { format, parseISO, startOfDay } from 'date-fns';
import { de } from 'date-fns/locale';
import { Check, Circle } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { type LifecycleEvent as LifecycleEventType } from '../api/lifecycle-api';
import { LifecycleEvent } from './LifecycleEvent';

interface LifecycleTimelineProps {
  events: LifecycleEventType[];
}

interface MilestonePhase {
  id: string;
  label: string;
  eventTypes: string[];
}

const MILESTONE_PHASES: MilestonePhase[] = [
  { id: 'upload', label: 'Upload', eventTypes: ['IMPORT'] },
  { id: 'ocr', label: 'OCR', eventTypes: ['OCR_COMPLETE'] },
  { id: 'validation', label: 'Validierung', eventTypes: ['CLASSIFICATION', 'EXTRACTION'] },
  { id: 'assignment', label: 'Zuordnung', eventTypes: ['ENTITY_LINK'] },
  { id: 'approval', label: 'Freigabe', eventTypes: ['APPROVAL'] },
  { id: 'archive', label: 'Archivierung', eventTypes: ['ARCHIVE'] },
];

export function LifecycleTimeline({ events }: LifecycleTimelineProps) {
  // Gruppiere Events nach Datum
  const eventsByDate = useMemo(() => {
    const grouped = new Map<string, LifecycleEventType[]>();

    events.forEach((event) => {
      const date = startOfDay(parseISO(event.timestamp));
      const dateKey = date.toISOString();

      if (!grouped.has(dateKey)) {
        grouped.set(dateKey, []);
      }
      grouped.get(dateKey)!.push(event);
    });

    // Sortiere Daten absteigend (neueste zuerst)
    return Array.from(grouped.entries())
      .sort(([dateA], [dateB]) => new Date(dateB).getTime() - new Date(dateA).getTime())
      .map(([dateKey, dateEvents]) => ({
        date: parseISO(dateKey),
        events: dateEvents.sort(
          (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        ),
      }));
  }, [events]);

  // Berechne abgeschlossene Phasen
  const completedPhases = useMemo(() => {
    const eventTypes = new Set(events.map((e) => e.event_type));
    return MILESTONE_PHASES.map((phase) => ({
      ...phase,
      completed: phase.eventTypes.some((type) => eventTypes.has(type)),
    }));
  }, [events]);

  // Finde aktuelle Phase (erste nicht-abgeschlossene Phase)
  const currentPhaseIndex = completedPhases.findIndex((phase) => !phase.completed);

  return (
    <div className="space-y-6">
      {/* Milestone Progress Bar */}
      <div className="border-b pb-6">
        <h3 className="text-sm font-medium mb-4 text-muted-foreground">
          Verarbeitungsstatus
        </h3>
        <div className="flex items-center justify-between gap-2">
          {completedPhases.map((phase, index) => {
            const isCompleted = phase.completed;
            const isCurrent = index === currentPhaseIndex;
            const isLast = index === completedPhases.length - 1;

            return (
              <div key={phase.id} className="flex items-center flex-1">
                {/* Phase Marker */}
                <div className="flex flex-col items-center gap-1">
                  <div
                    className={`
                      flex items-center justify-center w-8 h-8 rounded-full border-2 transition-all
                      ${
                        isCompleted
                          ? 'bg-green-500 border-green-500 text-white'
                          : isCurrent
                            ? 'bg-blue-500 border-blue-500 text-white animate-pulse'
                            : 'bg-muted border-border text-muted-foreground'
                      }
                    `}
                  >
                    {isCompleted ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Circle className="h-3 w-3" fill="currentColor" />
                    )}
                  </div>
                  <span
                    className={`
                      text-xs font-medium text-center
                      ${isCompleted || isCurrent ? 'text-foreground' : 'text-muted-foreground'}
                    `}
                  >
                    {phase.label}
                  </span>
                </div>

                {/* Connecting Line */}
                {!isLast && (
                  <div
                    className={`
                      flex-1 h-0.5 mx-2 transition-all
                      ${isCompleted ? 'bg-green-500' : 'bg-border'}
                    `}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Event Timeline */}
      <div>
        <h3 className="text-sm font-medium mb-4 text-muted-foreground">
          Ereignisverlauf
        </h3>
        <ScrollArea className="h-[500px] pr-4">
          <div className="space-y-6">
            {eventsByDate.map(({ date, events: dateEvents }) => (
              <div key={date.toISOString()} className="space-y-2">
                {/* Date Header (sticky) */}
                <div className="sticky top-0 z-10 bg-background/95 backdrop-blur-sm py-2 -mx-2 px-2 border-b">
                  <h4 className="text-sm font-semibold">
                    {format(date, 'EEEE, d. MMMM yyyy', { locale: de })}
                  </h4>
                </div>

                {/* Events for this date */}
                <div className="relative pl-4 border-l-2 border-border ml-4">
                  {dateEvents.map((event) => (
                    <LifecycleEvent key={event.id} event={event} />
                  ))}
                </div>
              </div>
            ))}

            {eventsByDate.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <p>Keine Ereignisse vorhanden</p>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
