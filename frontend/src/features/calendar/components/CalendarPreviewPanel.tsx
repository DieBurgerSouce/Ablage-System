/**
 * Kalender-Vorschau Panel
 *
 * Zeigt eine Vorschau der zu synchronisierenden Kalender-Events,
 * gruppiert nach Kategorie mit Dringlichkeits-Badges.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Calendar,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Loader2,
  CalendarDays,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { calendarSyncKeys, getCalendarPreview } from '../api/calendar-sync-api';
import type { CalendarEventPreview, CalendarEventCategory, EventUrgency } from '../types/calendar-types';

const CATEGORY_CONFIG: Record<
  CalendarEventCategory,
  { label: string; colorClass: string; bgClass: string }
> = {
  skonto: {
    label: 'Skonto-Fristen',
    colorClass: 'text-yellow-700',
    bgClass: 'bg-yellow-50 border-yellow-200',
  },
  zahlung_ein: {
    label: 'Zahlungseingänge',
    colorClass: 'text-green-700',
    bgClass: 'bg-green-50 border-green-200',
  },
  zahlung_aus: {
    label: 'Zahlungsausgänge',
    colorClass: 'text-red-700',
    bgClass: 'bg-red-50 border-red-200',
  },
  steuer: {
    label: 'Steuertermine',
    colorClass: 'text-purple-700',
    bgClass: 'bg-purple-50 border-purple-200',
  },
  vertrag: {
    label: 'Vertragsfristen',
    colorClass: 'text-blue-700',
    bgClass: 'bg-blue-50 border-blue-200',
  },
  mahnung: {
    label: 'Mahnungen',
    colorClass: 'text-orange-700',
    bgClass: 'bg-orange-50 border-orange-200',
  },
};

const URGENCY_CONFIG: Record<EventUrgency, { label: string; variant: 'destructive' | 'default' | 'secondary' }> = {
  high: { label: 'Dringend', variant: 'destructive' },
  medium: { label: 'Mittel', variant: 'default' },
  low: { label: 'Normal', variant: 'secondary' },
};

const DAYS_OPTIONS = [
  { value: '7', label: '7 Tage' },
  { value: '14', label: '14 Tage' },
  { value: '30', label: '30 Tage' },
  { value: '60', label: '60 Tage' },
  { value: '90', label: '90 Tage' },
];

function formatDateDE(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function groupEventsByCategory(
  events: CalendarEventPreview[]
): Record<CalendarEventCategory, CalendarEventPreview[]> {
  const groups: Record<CalendarEventCategory, CalendarEventPreview[]> = {
    skonto: [],
    zahlung_ein: [],
    zahlung_aus: [],
    steuer: [],
    vertrag: [],
    mahnung: [],
  };
  for (const event of events) {
    if (groups[event.category]) {
      groups[event.category].push(event);
    }
  }
  return groups;
}

interface CategorySectionProps {
  category: CalendarEventCategory;
  events: CalendarEventPreview[];
}

function CategorySection({ category, events }: CategorySectionProps) {
  const [open, setOpen] = useState(events.length > 0);
  const config = CATEGORY_CONFIG[category];

  if (events.length === 0) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className={cn(
            'w-full justify-between p-3 h-auto border rounded-lg',
            config.bgClass
          )}
        >
          <div className="flex items-center gap-2">
            {open ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
            <span className={cn('font-medium text-sm', config.colorClass)}>
              {config.label}
            </span>
          </div>
          <Badge variant="secondary" className="ml-2">
            {events.length}
          </Badge>
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1 space-y-1 pl-4">
        {events.map((event) => {
          const urgency = URGENCY_CONFIG[event.urgency];
          return (
            <div
              key={event.uid}
              className="flex items-center justify-between p-2 rounded-md hover:bg-muted/50"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{event.title}</p>
                <p className="text-xs text-muted-foreground">
                  {formatDateDE(event.start)}
                  {event.end !== event.start && ` - ${formatDateDE(event.end)}`}
                </p>
              </div>
              <Badge variant={urgency.variant} className="ml-2 flex-shrink-0 text-xs">
                {urgency.label}
              </Badge>
            </div>
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function CalendarPreviewPanel() {
  const [daysAhead, setDaysAhead] = useState(30);

  const {
    data: events,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: calendarSyncKeys.preview(daysAhead),
    queryFn: () => getCalendarPreview(daysAhead),
  });

  const grouped = events ? groupEventsByCategory(events) : null;
  const totalCount = events?.length ?? 0;
  const categoryOrder: CalendarEventCategory[] = [
    'skonto',
    'zahlung_ein',
    'zahlung_aus',
    'steuer',
    'vertrag',
    'mahnung',
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <CalendarDays className="h-5 w-5" />
              Termin-Vorschau
            </CardTitle>
            <CardDescription>
              Termine, die mit dem Kalender synchronisiert werden
            </CardDescription>
          </div>
          <Badge variant="outline" className="text-lg px-3 py-1">
            {totalCount}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 flex-1">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Tage voraus:</span>
            <Select
              value={String(daysAhead)}
              onValueChange={(v) => setDaysAhead(Number(v))}
            >
              <SelectTrigger className="w-[120px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAYS_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-1">Aktualisieren</span>
          </Button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : totalCount === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertTriangle className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              Keine anstehenden Termine für die nächsten {daysAhead} Tage
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {grouped &&
              categoryOrder.map((cat) => (
                <CategorySection
                  key={cat}
                  category={cat}
                  events={grouped[cat]}
                />
              ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
